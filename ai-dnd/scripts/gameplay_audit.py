"""Read-only-in-practice, isolated AI-DND gameplay consistency audit.

Runs fresh in-memory test sessions. Never opens SQLite, player saves, or
calls a real model. JSON output is diagnostic, not campaign canon.
Usage (from ai-dnd/): python -B scripts/gameplay_audit.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import equipment_economy
from api.tests.test_stage10a_gameplay_repairs import city_session


SCENARIOS = (
    {"id": "drop_simple", "message": "Kılıcımı bırakıyorum.", "kind": "drop"},
    {"id": "drop_ground", "message": "Kılıcımı yere bırakıyorum.", "kind": "drop"},
    {"id": "drop_put", "message": "Kılıcımı yere koyuyorum.", "kind": "drop"},
    {"id": "drop_throw", "message": "Kılıcımı yere atıyorum.", "kind": "drop"},
    {"id": "pickup_ground", "message": "Kılıcı yerden alıyorum.", "kind": "pickup"},
)


def snapshot(world):
    location = world["location"]
    return {
        "inventory": equipment_economy.labels(world.get("inventory", [])),
        "ground": equipment_economy.labels(
            world.get("ground_items_by_location", {}).get(location, [])
        ),
    }


def classify(scenario, before, after, action, narration):
    """Only evidence-backed invariants; do not infer arbitrary story truth."""
    findings = []
    kind = scenario["kind"]
    if action != "inventory":
        findings.append("ACTION_ROUTING_MISMATCH")
    if kind == "drop":
        if after["inventory"].count("Kılıç") != before["inventory"].count("Kılıç") - 1:
            findings.append("INVENTORY_STATE_MISMATCH")
        if after["ground"].count("Kılıç") != before["ground"].count("Kılıç") + 1:
            findings.append("GROUND_STATE_MISMATCH")
        if "geri döner" in narration.casefold():
            findings.append("NARRATION_STATE_CONTRADICTION")
    if kind == "pickup":
        if after["inventory"].count("Kılıç") != before["inventory"].count("Kılıç") + 1:
            findings.append("INVENTORY_STATE_MISMATCH")
        if after["ground"].count("Kılıç") != before["ground"].count("Kılıç") - 1:
            findings.append("GROUND_STATE_MISMATCH")
    return findings


def run_audit():
    results = []
    for index, scenario in enumerate(SCENARIOS):
        session = city_session(seed=9100 + index)
        world = session.world_state
        if scenario["kind"] == "pickup":
            world["inventory"].remove("Kılıç")
            world.setdefault("ground_items_by_location", {}).setdefault(
                world["location"], []
            ).append("Kılıç")
        before = snapshot(copy.deepcopy(world))
        with patch("game.ollama.chat", return_value={"message": {"content": "{}"}}):
            turn = session.run_player_turn(scenario["message"], interaction_mode="do")
        after = snapshot(world)
        action = turn.get("action_result", {}).get("action")
        narration = turn.get("narration", "")
        findings = classify(scenario, before, after, action, narration)
        calls = (turn.get("_engine_event_evidence", {})
                 .get("telemetry", {}).get("total_model_calls"))
        if not isinstance(calls, int) or calls > 2:
            findings.append("MODEL_CALL_BUDGET_VIOLATION")
        results.append({
            "case": scenario["id"],
            "input": scenario["message"],
            "expected": scenario["kind"],
            "resolved_action": action,
            "inventory_before": before["inventory"],
            "inventory_after": after["inventory"],
            "ground_before": before["ground"],
            "ground_after": after["ground"],
            "narration": narration,
            "model_calls": calls,
            "findings": findings,
        })
    return {
        "scope": "isolated_in_memory_no_real_model_no_persistence",
        "total": len(results),
        "passed": sum(not r["findings"] for r in results),
        "cases": results,
    }


if __name__ == "__main__":
    print(json.dumps(run_audit(), ensure_ascii=False, indent=2))
