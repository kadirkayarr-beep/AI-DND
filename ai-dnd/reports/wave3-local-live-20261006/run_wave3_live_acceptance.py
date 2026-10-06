"""Wave3 first-slice local live acceptance (temp DB). Does not modify product code."""

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
BUDGET_MAX = 7  # remaining after one Replit model-requiring turn already used
START = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}


def _log_sizes() -> dict[str, int]:
    return {str(path): (path.stat().st_size if path.exists() else 0) for path in LOGS}


def _tail_model_calls(before: dict[str, int]) -> tuple[int, list[str]]:
    chunks: list[str] = []
    for path in LOGS:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        chunks.append(text[before.get(str(path), 0) :])
    new = "\n".join(chunks)
    matches = re.findall(r"model_calls=(\d+)", new)
    started = len(re.findall(r"Ollama chat request started", new))
    return (int(matches[-1]) if matches else started), [
        line.strip() for line in new.splitlines() if "model_calls=" in line or "Ollama chat" in line
    ]


def _snap(state: dict[str, Any]) -> dict[str, Any]:
    worldish = state if "npcs" in state else state.get("world", state)
    if not isinstance(worldish, dict):
        worldish = state
    npcs = []
    for npc in worldish.get("npcs", []) or []:
        if not isinstance(npc, dict):
            continue
        npcs.append(
            {
                "id": npc.get("id"),
                "name": npc.get("name"),
                "role": npc.get("role"),
                "location": npc.get("location"),
                "reality_layer": npc.get("reality_layer"),
                "name_known_to_player": npc.get("name_known_to_player"),
            }
        )
    inventory = worldish.get("inventory") or state.get("inventory") or []
    if isinstance(state.get("character"), dict):
        inventory = state["character"].get("inventory", inventory)
    return {
        "location": worldish.get("location") or state.get("location"),
        "conversation": state.get("conversation") or worldish.get("conversation"),
        "combat_active": bool((worldish.get("combat") or state.get("combat") or {}).get("active")),
        "npcs": npcs,
        "inventory_labels": [
            (item.get("id") if isinstance(item, dict) else None)
            for item in (inventory if isinstance(inventory, list) else [])
        ][:20],
        "flags": {
            "active_npc_id": (worldish.get("flags") or {}).get("active_npc_id"),
            "turn_index": (worldish.get("flags") or {}).get("turn_index"),
        },
    }


def main() -> None:
    evidence: dict[str, Any] = {
        "base": BASE,
        "budget_max_model_requiring_turns": BUDGET_MAX,
        "budget_used": 0,
        "turns": [],
        "scenarios": {},
        "notes": [],
    }
    budget_used = 0

    with httpx.Client(timeout=300.0) as client:
        health = client.get(f"{BASE}/api/game/health")
        health.raise_for_status()
        evidence["health"] = health.json()

        created = client.post(
            f"{BASE}/api/game/campaigns",
            json={
                "name": f"Wave3 local live {uuid.uuid4().hex[:8]}",
                "campaign_start": START,
            },
        )
        created.raise_for_status()
        body = created.json()
        sid = body["session_id"]
        cid = body["campaign_id"]
        evidence["campaign_id"] = cid
        evidence["session_id"] = sid
        evidence["create_state"] = _snap(body.get("state") or {})
        if evidence["create_state"].get("location") != "fr:city:neverwinter":
            evidence["scenarios"]["neverwinter_start"] = {
                "status": "FAIL",
                "detail": evidence["create_state"].get("location"),
            }
            EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            raise SystemExit(2)
        evidence["scenarios"]["neverwinter_start"] = {"status": "PASS"}

        def turn(message: str, mode: str | None, target_id: str | None = None, label: str = "") -> dict[str, Any]:
            nonlocal budget_used
            before = _log_sizes()
            before_state = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
            action_id = str(uuid.uuid4())
            payload: dict[str, Any] = {
                "message": message,
                "action_id": action_id,
            }
            if mode is not None:
                payload["interaction_mode"] = mode
            if target_id is not None:
                payload["target_id"] = target_id
            t0 = time.time()
            resp = client.post(f"{BASE}/api/game/sessions/{sid}/turn", json=payload)
            elapsed = time.time() - t0
            calls, log_lines = _tail_model_calls(before)
            data = None
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text[:2000]}
            after_state = data.get("state") if isinstance(data, dict) else None
            if not isinstance(after_state, dict) and resp.status_code == 200:
                after_state = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
            model_requiring = calls > 0
            if model_requiring:
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
                "model_requiring_turn": model_requiring,
                "budget_used_after": budget_used,
                "log_lines": log_lines[-8:],
                "before": _snap(before_state if isinstance(before_state, dict) else {}),
                "after": _snap(after_state if isinstance(after_state, dict) else {}),
                "narration": (data or {}).get("narration") if isinstance(data, dict) else None,
                "detail": (data or {}).get("detail") if isinstance(data, dict) else None,
                "combat_result": (data or {}).get("combat_result") if isinstance(data, dict) else None,
            }
            evidence["turns"].append(row)
            evidence["budget_used"] = budget_used
            EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            if budget_used > BUDGET_MAX:
                raise RuntimeError(f"Budget exceeded after {label}: {budget_used}>{BUDGET_MAX}")
            return row

        # 1) ASK_DM look / presence — ownership path; may be 0-call
        look = turn("Etrafıma bakıyorum.", "ask_dm", label="ask_dm_city_look")
        presence = turn("Burada kimler var?", "ask_dm", label="ask_dm_city_presence")
        npcs = [
            n
            for n in (presence["after"].get("npcs") or look["after"].get("npcs") or [])
            if n.get("location") == "fr:city:neverwinter"
        ]
        evidence["scenarios"]["neverwinter_npc_access"] = {
            "status": "PASS" if npcs else "BLOCKED",
            "npc_count": len(npcs),
            "npcs": npcs,
            "look_model_calls": look["model_calls"],
            "presence_model_calls": presence["model_calls"],
            "ownership_note": (
                "ASK_DM look/presence -> plan_living_world_turn -> "
                "living_world.materialize_scene (engine-owned; not direct API seed)"
            ),
        }

        if not npcs:
            evidence["notes"].append("No procedural NPC after look/presence; remaining conversation scenarios BLOCKED.")
            EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"blocked": True, "budget_used": budget_used, "evidence": str(EVIDENCE)}, indent=2))
            return

        # Prefer two distinct NPCs if available
        primary = npcs[0]
        secondary = npcs[1] if len(npcs) > 1 else None

        # Public-safe greeting using target_id (not internal name as authority)
        greet = turn(
            "Merhaba, nasılsın?",
            "say",
            target_id=primary["id"],
            label="say_greet_primary",
        )
        evidence["scenarios"]["unknown_name_on_greet"] = {
            "status": "PASS"
            if (
                greet["http_status"] == 200
                and (greet["after"].get("conversation") or {}).get("active")
                and (greet["after"].get("conversation") or {})
                .get("interlocutor", {})
                .get("id")
                == primary["id"]
            )
            else "FAIL",
            "public_interlocutor": (greet["after"].get("conversation") or {}).get("interlocutor"),
            "internal_name_known_flag": primary.get("name_known_to_player"),
            "narration_mentions_raw_internal_name": (
                isinstance(primary.get("name"), str)
                and bool(primary.get("name"))
                and primary["name"].casefold() in str(greet.get("narration") or "").casefold()
                and not primary.get("name_known_to_player")
            ),
        }

        ask_name = turn(
            "Adın ne?",
            "say",
            target_id=primary["id"],
            label="say_ask_name",
        )
        after_name_npc = next(
            (n for n in ask_name["after"].get("npcs", []) if n.get("id") == primary["id"]),
            {},
        )
        evidence["scenarios"]["explicit_name_learning"] = {
            "status": "PASS" if ask_name["http_status"] == 200 else "FAIL",
            "name_known_after": after_name_npc.get("name_known_to_player"),
            "public_interlocutor": (ask_name["after"].get("conversation") or {}).get("interlocutor"),
            "note": "Learning only via existing open rule; selecting target alone must not learn.",
        }

        if secondary is not None and budget_used < BUDGET_MAX:
            switch = turn(
                "Seninle konuşmak istiyorum.",
                "say",
                target_id=secondary["id"],
                label="say_switch_target",
            )
            interloc = (switch["after"].get("conversation") or {}).get("interlocutor") or {}
            evidence["scenarios"]["target_switch"] = {
                "status": "PASS"
                if interloc.get("id") == secondary["id"]
                else "FAIL",
                "from": primary["id"],
                "to": secondary["id"],
                "interlocutor": interloc,
            }
        else:
            evidence["scenarios"]["target_switch"] = {
                "status": "BLOCKED",
                "detail": "Second local NPC not available or budget tight",
            }

        # End conversation — separate scenario from combat
        end = turn("Konuşmayı bitiriyorum.", "say", label="say_end_conversation")
        conv_after_end = end["after"].get("conversation") or {}
        evidence["scenarios"]["end_conversation"] = {
            "status": "PASS"
            if (
                end["http_status"] == 200
                and conv_after_end.get("active") is False
                and conv_after_end.get("interlocutor") is None
            )
            else "FAIL",
            "conversation": conv_after_end,
            "model_calls": end["model_calls"],
        }

        # Ambiguous pronoun after end must not wrongly bind
        if budget_used < BUDGET_MAX:
            ona = turn("Ona el sallarım.", "do", label="do_ambiguous_ona_after_end")
            bound = (ona["after"].get("conversation") or {}).get("interlocutor")
            evidence["scenarios"]["ambiguous_ona_after_end"] = {
                "status": "PASS"
                if not (bound and bound.get("id") in {primary["id"], (secondary or {}).get("id")})
                else "FAIL",
                "conversation": ona["after"].get("conversation"),
                "narration": ona.get("narration"),
                "http_status": ona["http_status"],
                "detail": ona.get("detail"),
            }
        else:
            evidence["scenarios"]["ambiguous_ona_after_end"] = {
                "status": "BLOCKED",
                "detail": "budget",
            }

        # Supported DO that actually executes (not rest clarification)
        # Use a concrete local search / look-do path with clear state change or direct result.
        if budget_used < BUDGET_MAX:
            do_act = turn(
                "Yakınlarda bir yerel taverna veya han arıyorum.",
                "do",
                label="do_tavern_search",
            )
            locs_before = {n.get("id") for n in look["after"].get("npcs", [])}
            # Check location children via state endpoint raw
            raw_after = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
            locations = []
            if isinstance(raw_after, dict):
                locations = raw_after.get("locations") or (raw_after.get("world") or {}).get("locations") or []
            if isinstance(locations, dict):
                location_items = list(locations.values())
            else:
                location_items = locations if isinstance(locations, list) else []
            tavernish = [
                item
                for item in location_items
                if isinstance(item, dict)
                and item.get("parent_location_id") == "fr:city:neverwinter"
                and item.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
            ]
            evidence["scenarios"]["do_supported_action"] = {
                "status": "PASS"
                if do_act["http_status"] == 200
                and (
                    tavernish
                    or "han" in str(do_act.get("narration") or "").casefold()
                    or "tavern" in str(do_act.get("narration") or "").casefold()
                )
                else "FAIL",
                "model_calls": do_act["model_calls"],
                "narration": do_act.get("narration"),
                "procedural_children": [
                    {"id": i.get("id"), "name": i.get("name"), "reality_layer": i.get("reality_layer")}
                    for i in tavernish
                ],
                "note": "Rest clarification is not accepted as success.",
            }
        else:
            evidence["scenarios"]["do_supported_action"] = {"status": "BLOCKED", "detail": "budget"}

        # Combat transition via explicit DO attack — separate from end-conversation
        # Re-greet first to have an active interlocutor, then attack in DO.
        if budget_used < BUDGET_MAX - 1:
            reengage = turn(
                "Tekrar seninle konuşmak istiyorum.",
                "say",
                target_id=primary["id"],
                label="say_reengage_before_combat",
            )
            attack = turn(
                "Ona kılıcımla saldırıyorum.",
                "do",
                target_id=primary["id"],
                label="do_attack_into_combat",
            )
            evidence["scenarios"]["combat_from_active_conversation"] = {
                "status": "PASS"
                if (
                    attack["http_status"] == 200
                    and attack["after"].get("combat_active") is True
                    and (attack["after"].get("conversation") or {}).get("active") is False
                )
                else ("FAIL" if attack["http_status"] == 200 else "FAIL"),
                "http_status": attack["http_status"],
                "combat_active": attack["after"].get("combat_active"),
                "conversation": attack["after"].get("conversation"),
                "combat_result": attack.get("combat_result"),
                "model_calls": attack["model_calls"],
                "reengage_conversation": reengage["after"].get("conversation"),
                "detail": attack.get("detail"),
                "narration": attack.get("narration"),
            }
        else:
            evidence["scenarios"]["combat_from_active_conversation"] = {
                "status": "BLOCKED",
                "detail": "budget",
            }

        # Inventory UX observation via ASK_DM (often 0-call)
        inv = turn("Envanterimde neler var?", "ask_dm", label="ask_dm_inventory")
        evidence["scenarios"]["inventory_ask_dm"] = {
            "status": "PASS" if inv["http_status"] == 200 else "FAIL",
            "model_calls": inv["model_calls"],
            "narration": inv.get("narration"),
        }
        # Collect item_* style labels from state
        raw_state = client.get(f"{BASE}/api/game/sessions/{sid}/state").json()
        item_labels = []

        def walk(obj: Any) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in {"id", "item_id", "label"} and isinstance(v, str) and v.startswith("item_"):
                        item_labels.append(v)
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        walk(raw_state)
        evidence["ux_findings"] = {
            "inventory_item_star_labels": sorted(set(item_labels)),
            "note": (
                "item_* tags observed as UX finding only; internal ID / persistence / "
                "API targeting contracts preserved; no code change in this validation."
            ),
        }

        # Narration acceptance / rejected fallback evidence from this run
        narration_rows = [
            t
            for t in evidence["turns"]
            if t.get("model_calls", 0) > 0 and t.get("http_status") == 200 and t.get("narration")
        ]
        evidence["scenarios"]["real_qwen_narration"] = {
            "status": "PASS" if narration_rows else "OPEN",
            "sample_labels": [t["label"] for t in narration_rows],
            "note": "Fake-adapter tests are separate; these rows used live Ollama qwen3:8b.",
        }
        evidence["scenarios"]["rejected_narration_fallback_no_retry"] = {
            "status": "OPEN",
            "detail": (
                "No rejected narration observed in this budgeted live run; "
                "did not spam model calls to force rejection. "
                "Contract remains: rejected -> deterministic fallback, no model retry."
            ),
        }

    evidence["budget_used"] = budget_used
    evidence["budget_remaining"] = BUDGET_MAX - budget_used
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "budget_used": budget_used,
                "budget_remaining": BUDGET_MAX - budget_used,
                "scenarios": {k: v.get("status") for k, v in evidence["scenarios"].items()},
                "evidence": str(EVIDENCE),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
