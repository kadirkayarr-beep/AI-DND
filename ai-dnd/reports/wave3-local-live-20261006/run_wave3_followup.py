"""Follow-up: end-conversation via DO, ambiguous pronoun, approach+attack. Reuses session."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

BASE = "http://127.0.0.1:8008"
VAL = Path(__file__).resolve().parent
LOGS = (VAL / "api.out.log", VAL / "api.err.log")
EVIDENCE = VAL / "evidence.json"
FOLLOW = VAL / "evidence_followup.json"
BUDGET_ALREADY = 1
BUDGET_MAX = 7


def _log_sizes() -> dict[str, int]:
    return {str(path): (path.stat().st_size if path.exists() else 0) for path in LOGS}


def _tail_model_calls(before: dict[str, int]) -> tuple[int, list[str]]:
    chunks = []
    for path in LOGS:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        chunks.append(text[before.get(str(path), 0) :])
    new = "\n".join(chunks)
    matches = re.findall(r"model_calls=(\d+)", new)
    started = len(re.findall(r"Ollama chat request started", new))
    return (int(matches[-1]) if matches else started), [
        line.strip() for line in new.splitlines() if "model_calls=" in line or "Ollama chat" in line
    ]


def main() -> None:
    prior = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    sid = prior["session_id"]
    budget_used = int(prior.get("budget_used") or BUDGET_ALREADY)
    out: dict[str, Any] = {
        "session_id": sid,
        "budget_used_start": budget_used,
        "turns": [],
        "scenarios": {},
    }

    with httpx.Client(timeout=300.0) as client:
        def turn(message: str, mode: str | None, target_id: str | None = None, label: str = "") -> dict[str, Any]:
            nonlocal budget_used
            before = _log_sizes()
            before_state = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
            action_id = str(uuid.uuid4())
            payload: dict[str, Any] = {"message": message, "action_id": action_id}
            if mode is not None:
                payload["interaction_mode"] = mode
            if target_id is not None:
                payload["target_id"] = target_id
            t0 = time.time()
            resp = client.post(f"{BASE}/api/game/sessions/{sid}/turn", json=payload)
            elapsed = time.time() - t0
            calls, log_lines = _tail_model_calls(before)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:2000]}
            after = data.get("state") if isinstance(data, dict) else None
            if not isinstance(after, dict) and resp.status_code == 200:
                after = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
            if calls > 0:
                budget_used += 1
            row = {
                "label": label,
                "message": message,
                "interaction_mode": mode,
                "target_id": target_id,
                "action_id": action_id,
                "http_status": resp.status_code,
                "elapsed_s": round(elapsed, 3),
                "model_calls": calls,
                "model_requiring_turn": calls > 0,
                "budget_used_after": budget_used,
                "log_lines": log_lines[-8:],
                "before_conversation": (before_state or {}).get("conversation") if isinstance(before_state, dict) else None,
                "after_conversation": (after or {}).get("conversation") if isinstance(after, dict) else None,
                "after_combat": bool(((after or {}).get("combat") or {}).get("active")) if isinstance(after, dict) else False,
                "narration": (data or {}).get("narration") if isinstance(data, dict) else None,
                "detail": (data or {}).get("detail") if isinstance(data, dict) else None,
                "combat_result": (data or {}).get("combat_result") if isinstance(data, dict) else None,
            }
            out["turns"].append(row)
            out["budget_used"] = budget_used
            FOLLOW.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            if budget_used > BUDGET_MAX:
                raise RuntimeError("budget exceeded")
            return row

        # Contract: end conversation is DO (not SAY/ASK_DM) — unit test confirms
        end = turn("Konuşmayı bitiriyorum.", "do", label="do_end_conversation")
        conv = end.get("after_conversation") or {}
        out["scenarios"]["end_conversation_do"] = {
            "status": "PASS"
            if end["http_status"] == 200 and conv.get("active") is False and conv.get("interlocutor") is None
            else "FAIL",
            "conversation": conv,
            "narration": end.get("narration"),
            "model_calls": end["model_calls"],
            "note": "Wave3 contract clears interlocutor via DO/default, not SAY.",
        }

        ona = turn("Ona el sallarım.", "do", label="do_ona_after_real_end")
        bound = (ona.get("after_conversation") or {}).get("interlocutor")
        out["scenarios"]["ambiguous_ona_after_end"] = {
            "status": "PASS" if not (ona.get("after_conversation") or {}).get("active") else "FAIL",
            "conversation": ona.get("after_conversation"),
            "narration": ona.get("narration"),
            "model_calls": ona["model_calls"],
            "bound_interlocutor": bound,
        }

        # Approach then attack — sets authoritative distance_ft
        approach = turn(
            "Marek'e yaklaşıyorum.",
            "do",
            target_id="npc_001",
            label="do_approach_marek",
        )
        attack = turn(
            "Ona kılıcımla saldırıyorum.",
            "do",
            target_id="npc_001",
            label="do_attack_after_approach",
        )
        out["scenarios"]["combat_from_conversation_after_approach"] = {
            "status": "PASS"
            if (
                attack["http_status"] == 200
                and attack.get("after_combat") is True
                and (attack.get("after_conversation") or {}).get("active") is False
            )
            else "FAIL",
            "approach_http": approach["http_status"],
            "approach_narration": approach.get("narration"),
            "approach_conversation": approach.get("after_conversation"),
            "attack_http": attack["http_status"],
            "attack_detail": attack.get("detail"),
            "attack_combat": attack.get("after_combat"),
            "attack_conversation": attack.get("after_conversation"),
            "attack_combat_result": attack.get("combat_result"),
            "attack_narration": attack.get("narration"),
            "attack_model_calls": attack["model_calls"],
        }

    out["budget_used"] = budget_used
    out["budget_remaining"] = BUDGET_MAX - budget_used
    FOLLOW.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # Merge summary into main evidence
    prior["followup"] = out
    prior["budget_used"] = budget_used
    prior["budget_remaining"] = BUDGET_MAX - budget_used
    for key, value in out["scenarios"].items():
        prior["scenarios"][key] = value
    # Correct prior mis-mode results
    prior["scenarios"]["end_conversation"] = {
        "status": "RETESTED_WITH_DO",
        "prior_say_result": "FAIL_expected_under_contract",
        "do_result": out["scenarios"]["end_conversation_do"]["status"],
        "contract": "end conversation owner is DO/default path in _dispatch_player_turn",
    }
    prior["scenarios"]["combat_from_active_conversation"] = {
        "status": "RETESTED_AFTER_APPROACH",
        "prior_without_distance": "FAIL distance_unknown",
        "after_approach": out["scenarios"]["combat_from_conversation_after_approach"]["status"],
        "note": "Authoritative distance required; approach sets npc distance_ft=5",
    }
    EVIDENCE.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "budget_used": budget_used,
                "budget_remaining": BUDGET_MAX - budget_used,
                "scenarios": {k: v.get("status") for k, v in out["scenarios"].items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
