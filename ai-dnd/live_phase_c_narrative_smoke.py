#!/usr/bin/env python3
"""Disposable real-Qwen smoke for the Phase C narrator and continuity adapter.

Run from the workspace root with the authenticated Ollama environment available:
    python ai-dnd/live_phase_c_narrative_smoke.py
All campaign/session state stays in memory and is discarded at process exit.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from unittest.mock import patch


AI_DND_DIR = Path(__file__).resolve().parent
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
import ollama
from api.narrative_director import (
    install_narrative_context_adapter,
    narrative_turn_context,
)
from api.narrative_memory import (
    empty_narrative_memory,
    update_narrative_memory,
)


TURNS = (
    ("tavern_intro", "Gromm, benim adım Arven. Kendimi tanıtıyorum."),
    ("tavern_exploration", "Etrafıma bakıyorum."),
    ("inventory_query", "Envanterimde neler var?"),
    ("npc_small_talk", "Gromm, işler nasıl gidiyor?"),
    ("perception_check", "Tavernayı dikkatlice gözlemliyorum."),
    ("travel_away", "Ormana gidiyorum."),
    ("forest_exploration", "Etrafımda neler var?"),
    ("forest_skill_check", "Ormandaki izleri takip etmeye çalışıyorum."),
    ("location_query", "Neredeyim?"),
    ("quiet_action", "Bir süre sessizce bekliyorum."),
    ("return_visit", "Tavernaya geri dönüyorum."),
    ("old_memory_callback", "Gromm, daha önce sana adımı söylemiş miydim?"),
    ("combat_attack", "Sentinel'a kılıcımla saldırıyorum."),
    ("combat_aftermath", "Savaşın ardından çevreyi gözlemliyorum."),
)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _state_summary(
    world: dict[str, Any], character: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "location": world.get("location"),
        "inventory": copy.deepcopy(world.get("inventory", [])),
        "player": {
            "current_hp": (character or {}).get("current_hp"),
            "max_hp": (character or {}).get("max_hp"),
            "combat_status": world.get("player_combat_status"),
        },
        "combat": {
            key: copy.deepcopy(world.get("combat", {}).get(key))
            for key in ("active", "status", "round", "current_actor_id", "end_reason")
        },
        "npcs": [
            {
                "id": npc.get("id"),
                "name": npc.get("name"),
                "location": npc.get("location"),
                "current_hp": npc.get("current_hp"),
                "combat_status": npc.get("combat_status"),
            }
            for npc in world.get("npcs", [])
            if isinstance(npc, dict)
        ],
    }


def main() -> int:
    game_file = Path(game.__file__).resolve()
    digest = hashlib.sha256(game_file.read_bytes()).hexdigest()
    host = os.environ.get("OLLAMA_HOST")
    token = os.environ.get("OLLAMA_PROXY_TOKEN")
    if not host or not token:
        print(json.dumps({
            "status": "BLOCKED",
            "reason": "Authenticated Ollama preflight is unavailable.",
            "game_sha256": digest,
            "turns_run": 0,
            "model_calls": 0,
        }, ensure_ascii=False, indent=2))
        return 2

    try:
        client = ollama.Client(
            host=host,
            headers={"Authorization": f"Bearer {token}"},
        )
        available = client.list()
        models = _field(available, "models") or []
        model_names = [str(_field(model, "model") or "") for model in models]
        if not any(
            name == "qwen3:8b" or name.startswith("qwen3:8b-")
            for name in model_names
        ):
            raise RuntimeError("required model is not listed")
    except Exception as error:
        print(json.dumps({
            "status": "BLOCKED",
            "reason_type": type(error).__name__,
            "game_sha256": digest,
            "turns_run": 0,
            "model_calls": 0,
        }, ensure_ascii=False, indent=2))
        return 2

    game.ollama.list = client.list
    game.ollama.chat = client.chat
    install_narrative_context_adapter(game)

    session = game.create_session(seed=208)
    session.world_state["location"] = "tavern"
    session.world_state["npcs"] = [{
        "id": "npc_001",
        "name": "Gromm",
        "role": "Barmen",
        "location": "tavern",
        "personality": "sakin ve dikkatli",
        "appearance": "",
        "relationship": "neutral",
        "knowledge": [],
        "memory": [],
        "backstory": "",
    }]

    memory = empty_narrative_memory()
    original_chat = client.chat
    original_finalize = game.finalize_narration
    original_ask = game.ask_dungeon_master
    records: list[dict[str, Any]] = []
    issues: list[str] = []

    for label, player_message in TURNS:
        combat_target = None
        if label == "combat_attack":
            combat_target = {
                "id": "npc_combat_smoke",
                "name": "Sentinel",
                "role": "muhafız",
                "location": session.world_state.get("location"),
                "max_hp": 1,
                "current_hp": 1,
                "armor_class": 10,
                "combat_status": "active",
                "attack_bonus": 2,
                "damage_die": 6,
                "damage_dice": 1,
                "damage_modifier": 3,
                "memory": [],
            }
            session.world_state.setdefault("npcs", []).append(combat_target)
            session.character.update(
                current_hp=30,
                max_hp=30,
                armor_class=12,
                strength_mod=2,
                dexterity_mod=2,
                proficiency_bonus=2,
            )
            session.world_state["player_combat_status"] = "active"
            with patch.object(session.rng, "randint", side_effect=[20, 1]):
                combat_start = session.start_combat(combat_target)
            if (
                not combat_start.get("combat_started")
                or session.world_state["combat"].get("current_actor_id") != "player"
            ):
                issues.append("Controlled combat fixture did not grant the player initiative.")

        calls: list[dict[str, Any]] = []
        trace: dict[str, Any] = {
            "label": label,
            "input": player_message,
            "state_before": _state_summary(
                session.world_state, session.character
            ),
        }
        if combat_target:
            trace["fixture"] = {
                "combat_target_id": combat_target["id"],
                "note": "Disposable controlled combat fixture; not saved to campaign data.",
            }
        before_world = copy.deepcopy(session.world_state)
        started = time.perf_counter()
        session.last_narration_safety = None
        trace["world_updates_proposed"] = None

        def chat(*args: Any, **kwargs: Any) -> Any:
            call: dict[str, Any] = {
                "stage": (
                    "intent"
                    if kwargs.get("format") == game.INTENT_SCHEMA
                    else "narration"
                ),
                "model": kwargs.get("model"),
            }
            call_started = time.perf_counter()
            try:
                response = original_chat(*args, **kwargs)
            except Exception as error:
                call["error_type"] = type(error).__name__
                raise
            finally:
                call["duration_ms"] = round(
                    (time.perf_counter() - call_started) * 1000
                )
            for field_name in (
                "prompt_eval_count",
                "eval_count",
                "done_reason",
                "total_duration",
            ):
                value = _field(response, field_name)
                if isinstance(value, (int, float, str)):
                    call[field_name] = value
            calls.append(call)
            return response

        def finalize(narration: Any, *args: Any, **kwargs: Any) -> str:
            trace["model_narration"] = narration
            result = original_finalize(narration, *args, **kwargs)
            trace["narration_replaced"] = (
                result != game.clean_dm_response(narration)
                if isinstance(narration, str) and narration.strip()
                else True
            )
            trace["narration_safety"] = copy.deepcopy(
                session.last_narration_safety
            )
            return result

        def ask(*args: Any, **kwargs: Any) -> Any:
            packet = original_ask(*args, **kwargs)
            if isinstance(packet, dict):
                updates = packet.get("world_updates")
                if not isinstance(updates, dict):
                    updates = {}
                trace["world_updates_proposed"] = {
                    "keys": sorted(str(key) for key in updates),
                    "npc_count": len(updates.get("create_npcs", []))
                    if isinstance(updates.get("create_npcs", []), (list, dict))
                    else 0,
                    "feature_count": len(updates.get("create_features", []))
                    if isinstance(updates.get("create_features", []), (list, dict))
                    else 0,
                    "location_count": len(updates.get("create_locations", []))
                    if isinstance(updates.get("create_locations", []), (list, dict))
                    else 0,
                    "event_count": len(updates.get("events", []))
                    if isinstance(updates.get("events", []), (list, dict))
                    else 0,
                }
            return packet

        try:
            with narrative_turn_context(memory, player_message) as frame:
                with patch.object(game.ollama, "chat", chat), patch.object(
                    game, "finalize_narration", finalize
                ), patch.object(game, "ask_dungeon_master", ask):
                    if label == "combat_attack":
                        with patch.object(session.rng, "randint", side_effect=[20, 1, 1]):
                            result = session.run_player_turn(
                                player_message, target_id=combat_target["id"]
                            )
                    else:
                        result = session.run_player_turn(player_message)
                trace["continuity"] = copy.deepcopy(frame.diagnostics)
                trace["continuity_player_claims"] = [
                    {
                        "npc_id": claim.get("npc_id"),
                        "text_length": len(claim.get("text", "")),
                    }
                    for claim in frame.selected_player_claims
                ]
            trace["action_result"] = copy.deepcopy(result.get("action_result", {}))
            trace["narration"] = result.get("narration", "")
            trace["scene_type"] = session._narration_scene_type(
                trace["action_result"]
            )
            if trace.get("narration_safety") is None:
                trace["narration_safety"] = copy.deepcopy(
                    session.last_narration_safety
                )
            memory = update_narrative_memory(
                memory,
                player_message=player_message,
                narration=trace["narration"],
                action_result=trace["action_result"],
                world_state_before=before_world,
                world_state_after=copy.deepcopy(session.world_state),
            )
        except Exception as error:
            trace["error_type"] = type(error).__name__
            issues.append(f"{label}: turn raised {type(error).__name__}")

        trace["state_after"] = _state_summary(
            session.world_state, session.character
        )
        trace["duration_ms"] = round((time.perf_counter() - started) * 1000)
        trace["calls"] = calls
        trace["model_call_count"] = len(calls)
        if not str(trace.get("narration", "")).strip():
            issues.append(f"{label}: empty narration")
        if len(calls) > 2:
            issues.append(f"{label}: more than two model calls")
        if any("error_type" in call for call in calls):
            issues.append(f"{label}: model call failed")
        continuity = trace.get("continuity", {})
        if continuity:
            if continuity.get("estimated_total_tokens", 0) > 32768:
                issues.append(f"{label}: Narrative Director budget exceeded")
        records.append(trace)

    by_label = {record["label"]: record for record in records}
    return_location = by_label.get("return_visit", {}).get("state_after", {}).get(
        "location"
    )
    if return_location != "tavern":
        issues.append("Location revisit did not restore the canonical tavern location.")

    skill_turn = by_label.get("forest_skill_check", {})
    if skill_turn.get("action_result", {}).get("action") != "skill_check":
        issues.append("Forest tracking did not resolve through the Python skill-check route.")
    combat_turn = by_label.get("combat_attack", {})
    combat_result = combat_turn.get("action_result", {})
    combat_after = combat_turn.get("state_after", {}).get("combat", {})
    if (
        combat_result.get("outcome") != "critical_hit"
        or combat_result.get("end_reason") != "target_defeated"
        or combat_after.get("active") is not False
    ):
        issues.append("Controlled combat attack did not finish with the authoritative defeat.")
    defeated_sentinel = next(
        (
            npc for npc in combat_turn.get("state_after", {}).get("npcs", [])
            if npc.get("id") == "npc_combat_smoke"
        ),
        {},
    )
    if (
        defeated_sentinel.get("current_hp") != 0
        or defeated_sentinel.get("combat_status") != "unconscious"
        or combat_turn.get("state_after", {}).get("player", {}).get("current_hp") != 30
    ):
        issues.append("Combat state summary did not preserve the defeated NPC and player HP.")
    aftermath = by_label.get("combat_aftermath", {})
    if aftermath.get("action_result", {}).get("action") == "attack":
        issues.append("Post-combat observation unexpectedly advanced combat.")

    callback = by_label.get("old_memory_callback", {})
    selected = callback.get("continuity", {}).get("selected_counts", {})
    callback_narration = str(callback.get("narration", ""))
    memory_callback_context = selected.get("npc_interactions", 0) > 0
    memory_callback_text = "Arven" in callback_narration
    if not memory_callback_context:
        issues.append("Old-memory callback did not select a relevant NPC interaction.")
    if not memory_callback_text:
        issues.append("Old-memory callback did not preserve the supported player name.")

    call_records = [call for row in records for call in row.get("calls", [])]
    prompt_counts = [
        call["prompt_eval_count"]
        for call in call_records
        if isinstance(call.get("prompt_eval_count"), int)
    ]
    output_counts = [
        call["eval_count"]
        for call in call_records
        if isinstance(call.get("eval_count"), int)
    ]
    estimated_totals = [
        row["continuity"]["estimated_total_tokens"]
        for row in records
        if row.get("continuity", {}).get("estimated_total_tokens") is not None
    ]
    output = {
        "status": "PASS" if not issues else "FAIL",
        "game_sha256": digest,
        "model": "qwen3:8b",
        "turns_run": len(records),
        "model_calls": len(call_records),
        "maximum_calls_per_turn": max(
            (row["model_call_count"] for row in records), default=0
        ),
        "maximum_prompt_eval_tokens": max(prompt_counts, default=None),
        "maximum_output_eval_tokens": max(output_counts, default=None),
        "maximum_narrative_director_estimated_total_tokens": max(
            estimated_totals, default=None
        ),
        "reserved_output_cap": 700,
        "narration_replacements": sum(
            bool(row.get("narration_replaced")) for row in records
        ),
        "narration_safety_reasons": {
            code: sum(
                row.get("narration_safety", {}).get("reason_code") == code
                for row in records
                if isinstance(row.get("narration_safety"), dict)
            )
            for code in sorted({
                row.get("narration_safety", {}).get("reason_code")
                for row in records
                if isinstance(row.get("narration_safety"), dict)
                and row.get("narration_safety", {}).get("reason_code")
            })
        },
        "memory_callback_context_selected": memory_callback_context,
        "memory_callback_mentions_player_name": memory_callback_text,
        "memory_callback_selected_counts": selected,
        "average_turn_latency_ms": round(
            sum(row.get("duration_ms", 0) for row in records)
            / max(1, len(records))
        ),
        "issues": issues,
        "turns": records,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())