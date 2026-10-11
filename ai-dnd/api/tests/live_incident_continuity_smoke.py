"""One live Neverwinter arrival, then the production talk path.

Missing qwen3:8b is BLOCKED, not FAIL. A rejected proposal is not retried.

    python -m api.tests.live_incident_continuity_smoke
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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


def main():
    os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")
    sys.path.insert(0, str(AI_DND_DIR))
    try:
        import ollama
        from api import ollama_adapter
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from incidents import hooks, profiles, projection
        from incidents.attempts import MemoryAttemptStore
    except Exception as error:
        return _emit({"final_gate_status": "BLOCKED", "reason": f"import failed: {error}"})

    loaded = profiles.load("neverwinter.v1")
    if loaded is None or profiles.load("waterdeep.v1") is not None:
        return _emit({"final_gate_status": "BLOCKED", "reason": "Neverwinter profile was not the only enabled city."})
    try:
        ollama.Client(host=os.environ["OLLAMA_HOST"], timeout=10).list()
    except Exception as error:
        return _emit({"final_gate_status": "BLOCKED", "reason": f"Ollama is unreachable: {error}"})

    directory = tempfile.TemporaryDirectory(prefix="ai-dnd-continuity-")
    manager = SessionManager(campaign_store=CampaignStore(Path(directory.name) / "campaigns.sqlite3"))
    campaign_id, _, record, _ = manager.create_campaign("Live continuity", campaign_start=START)
    session = record.game_session
    world = session.world_state
    world["flags"]["emergence_live"] = True
    session.emergence_store = MemoryAttemptStore()
    live_profile = dict(loaded, silence_rate=0.0)
    client = ollama.Client(host=os.environ["OLLAMA_HOST"], timeout=90)
    ollama_adapter.AuthenticatedOllamaAdapter(client).install_for_engine()

    talk_calls = None
    try:
        with ollama_adapter.AuthenticatedOllamaAdapter(client).capture_model_calls() as calls:
            with patch("incidents.profiles.resolve", return_value=live_profile):
                generated = hooks.before_narration(
                    session, action_result={"action": "travel", "success": True},
                    player_text="Neverwinter hanına vardım.", location_changed=True,
                )
        proposal_calls = len(calls)
    except Exception as error:
        return _emit({"final_gate_status": "BLOCKED", "reason": f"live proposal failed: {error}"})

    incidents = world.get("incidents") or {}
    shown = projection.scene_annotation(world)
    payload = {
        "profile_id": loaded["profile_id"],
        "review_status": loaded["review_status"],
        "model": MODEL_NAME,
        "proposal_status": generated.get("status"),
        "proposal_model_calls": generated.get("model_calls") or 0,
        "adapter_calls": proposal_calls,
        "incident_count": len(incidents),
        "quests_created": False,
        "scene_incidents": shown,
        "review_pending_is_pass": False,
    }
    if generated.get("model_calls", 0) > 1 or proposal_calls > 2:
        payload.update(final_gate_status="FAIL", reason="The arrival spent more than the turn budget.")
        return _emit(payload, 1)
    if generated.get("status") != "accepted" or not shown:
        payload.update(
            final_gate_status="BLOCKED",
            reason="Qwen did not produce an accepted visible incident. No retry.",
        )
        return _emit(payload)

    label = (shown[0].get("people") or [None])[0]
    if not isinstance(label, str) or not label.strip():
        payload.update(final_gate_status="BLOCKED", reason="The accepted incident has no visible person.")
        return _emit(payload)

    talk = {"action": "narrative", "success": True, "state_changes": []}
    with ollama_adapter.AuthenticatedOllamaAdapter(client).capture_model_calls() as talk_calls:
        hooks.before_narration(
            session, action_result=talk, player_text=f"Konuş: {label}", location_changed=False,
        )
        hooks.after_turn(session, {"location": world["location"]}, talk)
    npc_id = talk.get("npc_id")
    npc = next((row for row in world.get("npcs", []) if row.get("id") == npc_id), None)
    manager.save_campaign(campaign_id)
    with manager._registry_lock:
        active = manager._campaign_sessions.pop(campaign_id)
        del manager._sessions[active]
    _, resumed, _, _, _ = manager.resume_campaign(campaign_id)
    loaded_world = resumed.game_session.world_state
    resumed_npc = next((row for row in loaded_world.get("npcs", []) if row.get("id") == npc_id), None)
    payload.update(
        final_gate_status="PASS" if resumed_npc is not None else "FAIL",
        person_label=label,
        npc_id=npc_id,
        npc_name=None if npc is None else npc.get("name"),
        public_name=None,
        relationship_score=None,
        talk_model_calls=len(talk_calls),
        resumed_same_id=resumed_npc is not None and resumed_npc.get("id") == npc_id,
        quests_created=loaded_world.get("quests", []) != record.game_session.world_state.get("quests", []),
    )
    if resumed_npc is not None:
        import living_world
        import relationships
        payload["public_name"] = living_world.public_npc_name(resumed_npc)
        payload["relationship_score"] = relationships.score(loaded_world, npc_id)
        payload["hidden_in_scene"] = "hidden_facts" in json.dumps(projection.scene_annotation(loaded_world))
    if payload["final_gate_status"] != "PASS" or payload["talk_model_calls"] > 0:
        return _emit(payload, 1)
    return _emit(payload)


if __name__ == "__main__":
    raise SystemExit(main())
