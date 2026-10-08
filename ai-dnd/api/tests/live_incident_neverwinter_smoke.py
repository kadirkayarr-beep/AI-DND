"""Live Neverwinter emergence smoke with real qwen3:8b.

Missing or unreachable Ollama is BLOCKED, not FAIL.

    python -m api.tests.live_incident_neverwinter_smoke
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

AI_DND_DIR = Path(__file__).resolve().parents[2]
MODEL_NAME = "qwen3:8b"
PROTECTED = ("Dagult Neverember", "Waterdeep", "Luskan", "Baldur")


def _blocked(reason, **extra):
    payload = {
        "final_gate_status": "BLOCKED",
        "live_generation": "unverified",
        "reason": reason,
        "model": MODEL_NAME,
        **extra,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _fail(reason, **extra):
    payload = {
        "final_gate_status": "FAIL",
        "live_generation": "failed",
        "reason": reason,
        "model": MODEL_NAME,
        **extra,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1


def _model_names(listing):
    models = getattr(listing, "models", None)
    if models is None and isinstance(listing, dict):
        models = listing.get("models")
    names = []
    if not isinstance(models, list):
        return names
    for row in models:
        if isinstance(row, str):
            names.append(row)
            continue
        name = getattr(row, "model", None) or getattr(row, "name", None)
        if name is None and isinstance(row, dict):
            name = row.get("name") or row.get("model")
        if isinstance(name, str):
            names.append(name)
    return names


def main():
    os.environ.setdefault("AI_DND_EMERGENCE_LIVE", "1")
    sys.path.insert(0, str(AI_DND_DIR))
    try:
        import game
        from api import ollama_adapter
        from incidents import hooks, profiles, projection
        from incidents.attempts import MemoryAttemptStore
    except Exception as error:
        return _blocked(f"import failed: {error}")

    loaded = profiles.load("neverwinter.v1")
    if loaded is None:
        return _blocked("Neverwinter profile did not load from the reviewed pack.")
    live_profile = dict(loaded, silence_rate=0.0)

    try:
        listing = game.ollama.list()
    except Exception as error:
        return _blocked(f"Ollama is unreachable: {error}")
    names = _model_names(listing)
    if MODEL_NAME not in names and not any(item.startswith(MODEL_NAME) for item in names):
        return _blocked(f"{MODEL_NAME} is not installed.", installed=names)

    attempts = []
    last = None
    for seed in (17, 29, 41):
        session = game.create_session(seed=seed)
        world = session.world_state
        world["campaign_id"] = f"campaign.neverwinter.live.{seed}"
        world["location"] = "tavern"
        world["flags"]["emergence_live"] = True
        world["npcs"] = [
            {"id": "npc.keeper", "name": "Hesk", "role": "innkeeper", "location": "tavern"},
        ]
        store = MemoryAttemptStore()
        session.emergence_store = store
        try:
            with ollama_adapter.AuthenticatedOllamaAdapter(object()).capture_model_calls():
                with patch("incidents.profiles.resolve", return_value=live_profile):
                    result = hooks.before_narration(
                        session,
                        action_result={"action": "travel", "success": True},
                        player_text="tavernaya gidiyorum",
                        location_changed=True,
                    )
        except Exception as error:
            return _blocked(f"live proposal failed: {error}")
        row = next(iter(store._rows.values()), None)
        last = (session, world, result, row)
        attempts.append({
            "seed": seed,
            "status": result.get("status"),
            "model_calls": result.get("model_calls") or 0,
            "rejection_reason": None if not isinstance(row, dict) else row.get("rejection_reason"),
            "gate_outcome": None if not isinstance(row, dict) else row.get("gate_outcome"),
        })
        if (result.get("model_calls") or 0) > 1:
            return _fail("Emergence spent more than one model call on a trigger.", attempts=attempts)
        if result.get("status") == "accepted":
            break

    session, world, result, row = last
    incidents = world.get("incidents") or {}
    quests = world.get("quests") or []
    shown = projection.scene_annotation(world)
    blob = json.dumps({"result": result, "incidents": incidents, "shown": shown}, ensure_ascii=False)

    if quests:
        return _fail("An incident was written onto the quest list.", quests=quests, attempts=attempts)
    if result.get("status") == "accepted":
        for name in PROTECTED:
            if name.casefold() in blob.casefold():
                return _fail(
                    f"Protected setting name {name} appeared in a committed incident.",
                    excerpt=blob[:800], attempts=attempts,
                )

    payload = {
        "final_gate_status": "PASS",
        "live_generation": "verified",
        "profile_id": loaded["profile_id"],
        "review_status": loaded["review_status"],
        "model": MODEL_NAME,
        "status": result.get("status"),
        "model_calls": result.get("model_calls") or 0,
        "incident_count": len(incidents),
        "quests": quests,
        "scene_incidents": shown,
        "attempts": attempts,
        "note": "Each arrival is a new campaign. Silence-rate is 0 so Qwen is called. No per-trigger retry.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
