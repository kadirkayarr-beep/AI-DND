"""Controlled live evidence: rejected narration -> deterministic fallback, no model retry.

Budget: at most 4 model-requiring player turns. Per-turn max 2 real model calls.
Does not spam turns hoping for rejection; uses known rejection-prone SAY paths once each.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8008"
VAL = Path(__file__).resolve().parent
LOGS = (VAL / "api_fix.out.log", VAL / "api_fix.err.log", VAL / "api.out.log", VAL / "api.err.log")
START = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}
BUDGET_CAP = 4
FALLBACK_MARKERS = (
    "kendi gözlerimle görmedim",
    "şu ana kadar gördüklerin bu düşünceyi doğrulamıyor",
    "bu konuda güvenilir bir doğrulamam yok",
)


def sizes() -> dict[str, int]:
    return {str(p): (p.stat().st_size if p.exists() else 0) for p in LOGS}


def call_stats(before: dict[str, int]) -> dict:
    chunks = []
    for path in LOGS:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        chunks.append(text[before.get(str(path), 0) :])
    new = "\n".join(chunks)
    started = len(re.findall(r"Ollama chat request started", new))
    completed = re.findall(r"model_calls=(\d+)", new)
    return {
        "ollama_chat_started": started,
        "logged_model_calls": int(completed[-1]) if completed else started,
        "log_snippets": [
            line.strip()
            for line in new.splitlines()
            if "Ollama chat" in line or "model_calls=" in line
        ][-12:],
    }


def looks_like_fallback(narration: str | None) -> bool:
    text = (narration or "").casefold()
    return any(marker in text for marker in FALLBACK_MARKERS)


def main() -> None:
    budget_used = 0
    rows: list[dict] = []
    with httpx.Client(timeout=300.0) as client:
        health = client.get(f"{BASE}/api/game/health").json()
        created = client.post(
            f"{BASE}/api/game/campaigns",
            json={
                "name": f"rejected narration live {uuid.uuid4().hex[:6]}",
                "campaign_start": START,
            },
        )
        created.raise_for_status()
        sid = created.json()["session_id"]

        def turn(message: str, mode: str, target_id: str | None = None, label: str = "") -> dict:
            nonlocal budget_used
            before = sizes()
            payload = {
                "message": message,
                "interaction_mode": mode,
                "action_id": str(uuid.uuid4()),
            }
            if target_id is not None:
                payload["target_id"] = target_id
            resp = client.post(f"{BASE}/api/game/sessions/{sid}/turn", json=payload)
            stats = call_stats(before)
            requiring = stats["ollama_chat_started"] > 0 or stats["logged_model_calls"] > 0
            if requiring:
                budget_used += 1
            data = resp.json()
            after = data.get("state")
            if resp.status_code == 200 and not isinstance(after, dict):
                after = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
            narration = data.get("narration") if isinstance(data, dict) else None
            row = {
                "label": label,
                "message": message,
                "mode": mode,
                "target_id": target_id,
                "action_id": payload["action_id"],
                "http": resp.status_code,
                "model_requiring_turn": requiring,
                "budget_used_after": budget_used,
                "call_stats": stats,
                "per_turn_call_limit_ok": stats["ollama_chat_started"] <= 2
                and stats["logged_model_calls"] <= 2,
                "no_retry_ok": stats["ollama_chat_started"] <= 2,
                "narration": (narration or "")[:300],
                "fallback_marker_hit": looks_like_fallback(narration),
                "conversation": (after or {}).get("conversation")
                if isinstance(after, dict)
                else None,
                "detail": data.get("detail") if isinstance(data, dict) else None,
            }
            rows.append(row)
            if budget_used > BUDGET_CAP:
                raise RuntimeError(f"budget exceeded: {budget_used}")
            return row

        # Setup: 0-call paths
        turn("Etrafıma bakıyorum.", "ask_dm", label="setup_look")
        state = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
        npcs = state.get("npcs") or []
        if not npcs:
            raise RuntimeError("No NPC after look")
        primary = npcs[0]
        turn(
            f"{primary.get('name', 'kişi')} kişisine yaklaşıyorum.",
            "do",
            primary["id"],
            label="setup_approach",
        )

        # Controlled rejection-prone SAY turns (known Wave3/blocker paths).
        # Stop early when we have clear rejection + no-retry evidence.
        candidates = [
            (
                "Ona sembol hakkında fısıldıyorum.",
                "say_whisper_symbol",
            ),
            (
                "Dün bana söylediğin gizli ismi hatırlıyor musun?",
                "say_unsupported_history",
            ),
            (
                "Neverwinter'ın gizli lordunun gerçek adını ve yayınlanmamış geçmişini anlat.",
                "say_unverifiable_lore_prompt",
            ),
        ]
        evidence_hit = None
        for message, label in candidates:
            if budget_used >= BUDGET_CAP:
                break
            row = turn(message, "say", primary["id"], label=label)
            rejected = row["fallback_marker_hit"]
            no_retry = row["no_retry_ok"] and row["call_stats"]["ollama_chat_started"] <= 2
            if rejected and no_retry and row["model_requiring_turn"]:
                evidence_hit = {
                    "status": "PASS",
                    "label": label,
                    "message": message,
                    "ollama_chat_started": row["call_stats"]["ollama_chat_started"],
                    "logged_model_calls": row["call_stats"]["logged_model_calls"],
                    "narration": row["narration"],
                    "interpretation": (
                        "Live SAY turn used real Ollama; narration matched deterministic "
                        "fallback marker; chat starts <=2 so no narration retry storm."
                    ),
                }
                break
            if (
                row["model_requiring_turn"]
                and no_retry
                and row["call_stats"]["ollama_chat_started"] == 1
                and rejected
            ):
                evidence_hit = {
                    "status": "PASS",
                    "label": label,
                    "message": message,
                    "ollama_chat_started": 1,
                    "logged_model_calls": row["call_stats"]["logged_model_calls"],
                    "narration": row["narration"],
                }
                break

        # Contract probe without extra spam: if no natural rejection, record OPEN
        # plus offline-owner proof pointer rather than burning remaining budget.
        out = {
            "source": "f74 + working tree (weapon fix present; narration path unchanged)",
            "not_clean_f74": True,
            "health": health,
            "session_id": sid,
            "budget_used_model_requiring_turns": budget_used,
            "budget_cap": BUDGET_CAP,
            "budget_remaining": BUDGET_CAP - budget_used,
            "rejected_narration_fallback_no_retry": evidence_hit
            or {
                "status": "OPEN",
                "detail": (
                    "No live turn in this controlled set both hit a deterministic "
                    "fallback marker and proved rejection under real Qwen within budget. "
                    "Did not spam additional model turns. Offline owner tests still cover "
                    "no-retry (e.g. test_checkpoint_blockers / interaction adventure)."
                ),
            },
            "all_turns_respect_per_turn_cap": all(r["per_turn_call_limit_ok"] for r in rows),
            "turns": rows,
        }
        path = VAL / "evidence_rejected_narration_live.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": out["rejected_narration_fallback_no_retry"]["status"],
                    "budget_used": budget_used,
                    "budget_remaining": BUDGET_CAP - budget_used,
                    "per_turn_cap_ok": out["all_turns_respect_per_turn_cap"],
                    "evidence": str(path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
