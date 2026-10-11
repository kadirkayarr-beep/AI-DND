"""Isolated live combat gate for the existing courtyard encounter.

Run from ``ai-dnd``:

    python -m api.tests.live_neverwinter_combat_gate

The player opts into the already authored courtyard commoner. This runner does
not insert an NPC, patch dice, or change the 20-turn Neverwinter smoke.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid

import httpx

from api.tests.live_neverwinter_canon_smoke import (
    MODEL_NAME,
    START_SELECTION,
    SmokeFailure,
    _free_port,
    _latest_audit,
    _post_turn,
    _require,
    _start_api,
    _stop_api,
    _wait_ready,
)


EVIDENCE = (
    Path(__file__).resolve().parents[3]
    / ".local"
    / "evidence"
    / "stage10a-live-combat-20261009"
)
ENTER = "Avlu karşılaşmasına gir"
START = "Avlu çatışmasını başlat"
END_TURN = "Turumu bitiriyorum"
ATTACK = "Saldırıyorum."


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _attack_rolls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for item in _walk(payload):
        roll = item.get("attack_roll")
        if type(roll) is int:
            found.append({
                "attack_roll": roll,
                "hit": item.get("hit"),
                "damage": item.get("damage"),
                "target_id": item.get("target_id"),
                "attacker_id": item.get("attacker_id") or item.get("actor_id"),
            })
    return found


def _hp_map(state: dict[str, Any]) -> dict[str, int | None]:
    found: dict[str, int | None] = {}
    character = state.get("character")
    if isinstance(character, dict):
        found["player"] = character.get("current_hp")
    for npc in state.get("npcs", []):
        if isinstance(npc, dict) and isinstance(npc.get("id"), str):
            found[npc["id"]] = npc.get("current_hp")
    combat = state.get("combat")
    if isinstance(combat, dict):
        for record in combat.get("participant_records", []):
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                found[record["id"]] = record.get("current_hp")
    return found


def run_gate() -> dict[str, Any]:
    turns: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "status": "FAIL",
        "model": MODEL_NAME,
        "campaign_database": "temporary_disposable",
        "dice_control": "session RNG; no predetermined rolls",
        "encounter_origin": "bounded_encounter.open_courtyard_commoner_v1",
        "turns": turns,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ai-dnd-live-combat-") as temp:
        temp_path = Path(temp)
        database_path = temp_path / "campaigns.sqlite3"
        audit_path = temp_path / "turn-audit.jsonl"
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = None
        log_handle = None

        def play(client: httpx.Client, session_id: str, label: str, message: str, *, target_id: str | None = None) -> dict[str, Any]:
            payload = _post_turn(client, base_url, session_id, message, target_id=target_id)
            audit = _latest_audit(audit_path)
            calls = audit.get("model_calls")
            _require(type(calls) is int and 0 <= calls <= 2, f"{label}: model calls outside 0..2.")
            trace = audit.get("model_call_trace", [])
            observed = [event for event in trace if event.get("event") == "model_call"]
            _require(len(observed) == calls, f"{label}: call trace disagrees with the adapter count.")
            _require(
                sum(event.get("phase") == "narration" for event in observed) <= 1,
                f"{label}: narration was retried.",
            )
            finalized = [index for index, event in enumerate(trace) if event.get("event") == "narration_finalized"]
            if finalized:
                _require(
                    not any(event.get("event") == "model_call" for event in trace[finalized[-1] + 1:]),
                    f"{label}: a model call followed the narration gate.",
                )
            row = {
                "turn": len(turns) + 1,
                "label": label,
                "player_message": message,
                "target_id": target_id,
                "narration": payload.get("narration"),
                "model_calls": calls,
                "model_call_trace": trace,
                "narrative_safety_action": audit.get("narrative_safety_action"),
                "attack_rolls": _attack_rolls(payload),
                "state": payload.get("state"),
            }
            turns.append(row)
            return payload

        try:
            process, log_handle = _start_api(port, database_path, audit_path, temp_path / "api-first.log")
            health = _wait_ready(process, base_url, temp_path / "api-first.log")
            _require(health.get("model") == MODEL_NAME, "Isolated API did not report qwen3:8b.")
            with httpx.Client(timeout=30) as client:
                created = client.post(
                    f"{base_url}/api/campaigns",
                    json={"name": f"Live combat gate {uuid.uuid4().hex[:8]}", "campaign_start": START_SELECTION},
                )
                _require(created.status_code == 200, f"Campaign creation failed: HTTP {created.status_code}.")
                created_body = created.json()
                session_id = created_body["session_id"]
                campaign_id = created_body["campaign_id"]
                before = created_body["state"]
                _require(not before.get("combat", {}).get("active"), "Combat was already active at campaign start.")
                _require(not before.get("bounded_encounter"), "The courtyard was already materialized.")

                entered = play(client, session_id, "Enter authored courtyard", ENTER)
                opponent = (entered.get("state") or {}).get("bounded_encounter", {}).get("visible_opponent") or {}
                npc_id = opponent.get("npc_id")
                _require(
                    entered["state"]["combat"]["active"] is False
                    and opponent.get("statblock_id") == "mm2024.commoner"
                    and opponent.get("distance_ft") == 60
                    and isinstance(npc_id, str)
                    and "printed p.77" in str(opponent.get("source", "")),
                    "Courtyard entry did not reveal the authored commoner at 60 feet.",
                )
                _require(
                    sum(npc.get("id") == npc_id for npc in entered["state"].get("npcs", []) if isinstance(npc, dict)) == 1,
                    "Courtyard entry did not keep one stable participant ID.",
                )

                started = play(client, session_id, "Start courtyard combat", START)
                combat = started["state"]["combat"]
                participants = combat.get("participants")
                order = combat.get("initiative_order")
                _require(
                    combat.get("active") is True
                    and isinstance(combat.get("combat_id"), str)
                    and combat["combat_id"]
                    and isinstance(participants, list)
                    and set(participants) == {"player", npc_id}
                    and isinstance(order, list)
                    and set(order) == {"player", npc_id}
                    and order[combat.get("current_turn_index", 0)] == combat.get("current_actor_id"),
                    "Combat start did not publish authoritative participants and initiative order.",
                )
                result["combat_id"] = combat["combat_id"]
                result["participant_ids"] = participants
                result["initiative_order"] = order

                state = started["state"]
                if (state.get("bounded_encounter") or {}).get("visible_opponent", {}).get("distance_ft") != 5:
                    ended = play(client, session_id, "End turn so the commoner can close", END_TURN)
                    state = ended["state"]
                opponent = (state.get("bounded_encounter") or {}).get("visible_opponent") or {}
                _require(opponent.get("distance_ft") == 5 and opponent.get("npc_id") == npc_id,
                         "The authored route did not bring the same commoner to 5 feet.")

                if state.get("combat", {}).get("current_actor_id") != "player":
                    yielded = play(client, session_id, "Yield until the player turn", END_TURN)
                    state = yielded["state"]
                hp_before = _hp_map(state)
                attacked = play(client, session_id, "Player melee attack", ATTACK, target_id=npc_id)
                rolls = _attack_rolls(attacked)
                hp_after = _hp_map(attacked["state"])
                changed = {key: (hp_before.get(key), hp_after.get(key)) for key in hp_after if hp_before.get(key) != hp_after.get(key)}
                if not rolls or not changed:
                    follow = play(client, session_id, "Continue the same encounter", ATTACK, target_id=npc_id)
                    rolls = rolls + _attack_rolls(follow)
                    hp_after = _hp_map(follow["state"])
                    changed = {key: (hp_before.get(key), hp_after.get(key)) for key in hp_after if hp_before.get(key) != hp_after.get(key)}
                result["attack_rolls"] = rolls
                result["hp_changes"] = changed
                _require(bool(rolls), "No authoritative attack roll was returned.")
                _require(bool(changed), "No participant HP changed after the recorded attack rolls.")

                final_state = turns[-1]["state"]
                _require(final_state.get("quests") in ([], None), "Combat created a quest.")
                _require(final_state.get("character", {}).get("xp") == before.get("character", {}).get("xp"),
                         "Combat changed XP.")
                _require(final_state.get("inventory") == before.get("inventory"), "Combat changed inventory.")
                _require(final_state.get("currency") == before.get("currency"), "Combat changed currency.")

                saved = client.post(f"{base_url}/api/campaigns/{campaign_id}/save")
                _require(saved.status_code == 200, "Combat campaign save failed.")
            _stop_api(process, log_handle)
            process = None
            log_handle = None
            process, log_handle = _start_api(port, database_path, audit_path, temp_path / "api-after-restart.log")
            _wait_ready(process, base_url, temp_path / "api-after-restart.log")
            with httpx.Client(timeout=30) as client:
                resumed = client.post(f"{base_url}/api/campaigns/{campaign_id}/resume")
                _require(resumed.status_code == 200, "Combat campaign did not resume.")
                resumed_body = resumed.json()
                _require(resumed_body.get("campaign_id") == campaign_id, "Resume changed the campaign ID.")
                resumed_combat = resumed_body["state"]["combat"]
                _require(
                    resumed_combat.get("combat_id") == result["combat_id"] or resumed_combat.get("active") is False,
                    "Resume lost the combat identity without ending it.",
                )
                result["resumed_combat_active"] = resumed_combat.get("active")
                result["resumed_hp"] = _hp_map(resumed_body["state"])
                other = client.post(
                    f"{base_url}/api/campaigns",
                    json={"name": f"Isolation {uuid.uuid4().hex[:8]}", "campaign_start": START_SELECTION},
                )
                _require(other.status_code == 200, "Isolation campaign creation failed.")
                other_state = other.json()["state"]
                _require(
                    not other_state.get("combat", {}).get("active") and not other_state.get("bounded_encounter"),
                    "A second campaign inherited the courtyard or combat.",
                )
            result["status"] = "MECHANICAL_PASS_NEEDS_MANUAL_NARRATION_REVIEW"
        except Exception as error:
            result["error_type"] = type(error).__name__
            result["error"] = str(error)[:1000]
        finally:
            if process is not None:
                _stop_api(process, log_handle)
            for name in ("api-first.log", "api-after-restart.log"):
                source = temp_path / name
                if source.is_file():
                    shutil.copyfile(source, EVIDENCE / name)
    (EVIDENCE / "live-combat-gate.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def main() -> int:
    result = run_gate()
    print(json.dumps({
        "status": result.get("status"),
        "error": result.get("error"),
        "turns": len(result.get("turns", [])),
        "combat_id": result.get("combat_id"),
        "initiative_order": result.get("initiative_order"),
        "hp_changes": result.get("hp_changes"),
        "attack_rolls": result.get("attack_rolls"),
    }, ensure_ascii=False, indent=2))
    return 0 if str(result.get("status", "")).startswith("MECHANICAL_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
