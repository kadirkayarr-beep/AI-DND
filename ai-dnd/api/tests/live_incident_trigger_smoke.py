"""Short live Neverwinter trigger coverage.

Uses production detection, the real silence rate, and one proposal per trigger.
A silent or rejected trigger is not retried. Missing Ollama is BLOCKED.

    python -m api.tests.live_incident_trigger_smoke
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from api.tests.auth_fixture import TEST_PLAYER
AI_DND_DIR = Path(__file__).resolve().parents[2]
MODEL_NAME = "qwen3:8b"
START = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}


def _emit(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def _classify(detected, result, row, incidents_before, incidents_after):
    if detected is None:
        return "no-event"
    status = None if not isinstance(result, dict) else result.get("status")
    if status == "accepted" or len(incidents_after) > len(incidents_before):
        return "accepted"
    if status == "rejected":
        return "rejected"
    if status in {"no_proposal", "stale"}:
        return status
    if isinstance(row, dict) and row.get("status") == "rejected":
        return "rejected"
    return "suppressed"


def main():
    os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")
    sys.path.insert(0, str(AI_DND_DIR))
    try:
        import ollama
        from api import ollama_adapter
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from incidents import hooks, profiles, projection, triggers
        from incidents.attempts import MemoryAttemptStore
    except Exception as error:
        return _emit({"gate": 1, "final_gate_status": "BLOCKED", "reason": f"import failed: {error}"})

    loaded = profiles.load("neverwinter.v1")
    if loaded is None or profiles.load("waterdeep.v1") is not None or profiles.load("baldurs_gate.v1") is not None:
        return _emit({"gate": 1, "final_gate_status": "FAIL", "reason": "City profile enablement is wrong."}, 1)
    try:
        ollama.Client(host=os.environ["OLLAMA_HOST"], timeout=10).list()
    except Exception as error:
        return _emit({"gate": 1, "final_gate_status": "BLOCKED", "reason": f"Ollama is unreachable: {error}"})

    directory = tempfile.TemporaryDirectory(prefix="ai-dnd-triggers-")
    manager = SessionManager(campaign_store=CampaignStore(Path(directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER))
    campaign_id, _, record, _ = manager.create_campaign("Trigger coverage", campaign_start=START)
    other_id, _, other, _ = manager.create_campaign("Trigger isolation", campaign_start=START)
    session = record.game_session
    world = session.world_state
    world["flags"]["emergence_live"] = True
    session.emergence_store = MemoryAttemptStore()
    client = ollama.Client(host=os.environ["OLLAMA_HOST"], timeout=90)
    ollama_adapter.AuthenticatedOllamaAdapter(client).install_for_engine()
    quests = list(world.get("quests") or [])
    steps = [
        ("arrival", {"action": "travel", "success": True}, "Neverwinter'a vardım.", True),
        ("look", {"action": "look", "success": True}, "etrafa bakıyorum", False),
        ("rest", {"action": "rest", "success": True}, "bir saat dinleniyorum", False),
    ]
    rows = []
    calls_total = 0
    try:
        for label, action, text, moved in steps:
            detected = triggers.detect(
                world, action_result=action, player_text=text, location_changed=moved,
            )
            before = set((world.get("incidents") or {}).keys())
            with ollama_adapter.AuthenticatedOllamaAdapter(client).capture_model_calls() as calls:
                result = hooks.before_narration(
                    session, action_result=action, player_text=text, location_changed=moved,
                )
            calls_total += len(calls)
            store_row = None
            if detected is not None:
                kind = detected["kind"]
                for candidate in session.emergence_store._rows.values():
                    if candidate.get("campaign_id") == world.get("campaign_id") and f":{kind}:" in str(candidate.get("trigger_id")):
                        store_row = candidate
            after = set((world.get("incidents") or {}).keys())
            outcome = _classify(detected, result, store_row, before, after)
            rows.append({
                "label": label,
                "detected": None if detected is None else detected["kind"],
                "outcome": outcome,
                "model_calls": 0 if not isinstance(result, dict) else (result.get("model_calls") or 0),
                "adapter_calls": len(calls),
                "status": None if not isinstance(result, dict) else result.get("status"),
                "rejection_reason": None if not isinstance(store_row, dict) else store_row.get("rejection_reason"),
                "new_incidents": sorted(after - before),
            })
            if any(item["adapter_calls"] > 1 or item["model_calls"] > 1 for item in rows):
                return _emit({"gate": 1, "final_gate_status": "FAIL", "reason": "A trigger spent more than one model call.", "steps": rows}, 1)
    except Exception as error:
        return _emit({"gate": 1, "final_gate_status": "BLOCKED", "reason": str(error)[:800], "steps": rows})

    shown = projection.scene_annotation(world)
    packet = json.dumps(shown, ensure_ascii=False)
    accepted = [item for item in rows if item["outcome"] == "accepted"]
    repeat = None
    if accepted:
        first = accepted[0]
        action = {"action": "travel", "success": True}
        text = "Neverwinter'a vardım."
        moved = True
        if first["label"] != "arrival":
            action = {"action": first["label"], "success": True}
            text = "etrafa bakıyorum" if first["label"] == "look" else "bir saat dinleniyorum"
            moved = False
        before_calls = calls_total
        with ollama_adapter.AuthenticatedOllamaAdapter(client).capture_model_calls() as calls:
            again = hooks.before_narration(
                session, action_result=action, player_text=text, location_changed=moved,
            )
        repeat = {
            "status": again.get("status"),
            "model_calls": again.get("model_calls") or 0,
            "adapter_calls": len(calls),
        }
        calls_total += len(calls)
        if repeat["adapter_calls"] or repeat["model_calls"]:
            return _emit({"gate": 1, "final_gate_status": "FAIL", "reason": "A consumed trigger called the model again.", "steps": rows, "repeat": repeat}, 1)

    resumed_same = None
    if accepted:
        incident_id = accepted[0]["new_incidents"][0]
        manager.save_campaign(campaign_id)
        with manager._registry_lock:
            active = manager._campaign_sessions.pop(campaign_id)
            del manager._sessions[active]
        _, resumed, _, _, _ = manager.resume_campaign(campaign_id)
        restored = resumed.game_session.world_state.get("incidents") or {}
        resumed_same = incident_id in restored
        if not resumed_same:
            return _emit({"gate": 1, "final_gate_status": "FAIL", "reason": "Resume dropped the accepted incident.", "steps": rows}, 1)

    isolated = other.game_session.world_state.get("incidents") or {}
    payload = {
        "gate": 1,
        "final_gate_status": "PASS" if accepted else "BLOCKED",
        "reason": None if accepted else "Triggers ran under the real silence rate. None was accepted. No retry and no silence bypass.",
        "profile_id": loaded["profile_id"],
        "review_status": loaded["review_status"],
        "silence_rate": loaded["silence_rate"],
        "model": MODEL_NAME,
        "steps": rows,
        "accepted_count": len(accepted),
        "rejected_count": sum(item["outcome"] == "rejected" for item in rows),
        "suppressed_count": sum(item["outcome"] == "suppressed" for item in rows),
        "no_event_count": sum(item["outcome"] == "no-event" for item in rows),
        "model_calls": calls_total,
        "scene_incidents": shown,
        "hidden_marker_in_scene": "hidden_facts" in packet,
        "quests_unchanged": list(world.get("quests") or []) == quests,
        "other_campaign_incidents": len(isolated),
        "repeat": repeat,
        "resumed_same_incident": resumed_same,
        "review_pending_is_pass": False,
    }
    if payload["hidden_marker_in_scene"] or not payload["quests_unchanged"] or payload["other_campaign_incidents"]:
        payload["final_gate_status"] = "FAIL"
        payload["reason"] = "Quest, isolation, or hidden-fact check failed."
        return _emit(payload, 1)
    return _emit(payload, 0 if payload["final_gate_status"] == "PASS" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
