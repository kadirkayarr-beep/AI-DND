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
    ("location_query", "Neredeyim?"),
    ("quiet_action", "Bir süre sessizce bekliyorum."),
    ("return_visit", "Tavernaya geri dönüyorum."),
    ("old_memory_callback", "Gromm, daha önce sana adımı söylemiş miydim?"),
)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _state_summary(world: dict[str, Any]) -> dict[str, Any]:
    return {
        "location": world.get("location"),
        "inventory": copy.deepcopy(world.get("inventory", [])),
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
    records: list[dict[str, Any]] = []
    issues: list[str] = []

    for label, player_message in TURNS:
        calls: list[dict[str, Any]] = []
        trace: dict[str, Any] = {
            "label": label,
            "input": player_message,
            "state_before": _state_summary(session.world_state),
        }
        before_world = copy.deepcopy(session.world_state)
        started = time.perf_counter()

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
            return result

        try:
            with narrative_turn_context(memory, player_message) as frame:
                with patch.object(game.ollama, "chat", chat), patch.object(
                    game, "finalize_narration", finalize
                ):
                    result = session.run_player_turn(player_message)
                trace["continuity"] = copy.deepcopy(frame.diagnostics)
            trace["action_result"] = copy.deepcopy(result.get("action_result", {}))
            trace["narration"] = result.get("narration", "")
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

        trace["state_after"] = _state_summary(session.world_state)
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

    callback = by_label.get("old_memory_callback", {})
    selected = callback.get("continuity", {}).get("selected_counts", {})
    callback_narration = str(callback.get("narration", ""))
    memory_callback_context = selected.get("npc_interactions", 0) > 0
    memory_callback_text = "Arven" in callback_narration
    if not memory_callback_context:
        issues.append("Old-memory callback did not select a relevant NPC interaction.")

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