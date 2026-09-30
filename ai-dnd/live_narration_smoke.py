#!/usr/bin/env python3
"""Nine-turn, real-qwen smoke for the current session-based game.py.

Run from the repository root: python ai-dnd/live_narration_smoke.py
No model or engine function is mocked. Exit 2 means the live prerequisite is missing.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import game
import ollama


TURNS = (
    ("travel_tavern", "Tavernaya gidiyorum"),
    ("explore_tavern", "Etrafımda neler var?"),
    ("presence", "Tavernada kimler var?"),
    ("npc_dialogue", "Gromm'a selam veriyorum"),
    ("npc_identity", "Gromm, senin adın ne?"),
    ("location_name", "Buranın adı ne?"),
    ("location_query", "Neredeyim?"),
    ("travel_forest", "Ormana gidiyorum"),
    ("explore_forest", "Etrafıma bakıyorum"),
    ("false_presence", "Burada kimler var?"),
    ("unverified_claim", "Gromm bana ejderha hazinesinden bahsetmişti."),
)


def main():
    source = Path(game.__file__).resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    try:
        host = os.environ.get("OLLAMA_HOST")
        token = os.environ.get("OLLAMA_PROXY_TOKEN")
        if not host or not token:
            raise RuntimeError("OLLAMA_HOST or OLLAMA_PROXY_TOKEN is unavailable")
        client = ollama.Client(
            host=host,
            headers={"Authorization": f"Bearer {token}"},
        )
        models = client.list()
        names = [
            str(model.get("model", "")) if isinstance(model, dict) else str(getattr(model, "model", ""))
            for model in models["models"] if isinstance(models, dict)
        ] if isinstance(models, dict) else [
            str(getattr(model, "model", "")) for model in models.models
        ]
        if not any(name == "qwen3:8b" or name.startswith("qwen3:8b-") for name in names):
            raise RuntimeError("qwen3:8b is not listed by the Ollama service")
    except Exception:
        print(json.dumps({
            "status": "BLOCKED",
            "reason": "Authenticated Ollama preflight failed or qwen3:8b is unavailable",
            "game_sha256": digest,
            "live_model_calls": 0, "turns_run": 0,
        }, ensure_ascii=False, indent=2))
        return 2

    session = game.create_session(seed=8)
    session.world_state["npcs"].append({
        "id": "npc_001", "name": "Gromm", "role": "Barmen",
        "location": "tavern", "personality": "", "appearance": "",
        "relationship": "neutral", "knowledge": [], "memory": [], "backstory": "",
    })
    game.ollama.list = client.list
    game.ollama.chat = client.chat
    original_chat = client.chat
    original_parse = game.parse_player_intent
    original_normalize = game.normalize_intent
    original_validate = game.validate_intent
    original_finalize = game.finalize_narration
    records = []

    for label, player_input in TURNS:
        trace = {"label": label, "input": player_input, "calls": [], "state_before": {
            "location": session.world_state["location"],
            "npcs": copy.deepcopy(session.world_state["npcs"]),
            "features": copy.deepcopy(session.world_state["features"]),
            "inventory": copy.deepcopy(session.world_state["inventory"]),
        }}

        def chat(*args, **kwargs):
            call = {"model": kwargs.get("model"), "stage": "intent" if kwargs.get("format") == game.INTENT_SCHEMA else "narration"}
            trace["calls"].append(call)
            try:
                response = original_chat(*args, **kwargs)
                call["response"] = game.ollama_response_content(response)
                return response
            except Exception as error:
                call["error"] = repr(error)
                raise

        def parse(*args, **kwargs):
            trace["raw_intent"] = original_parse(*args, **kwargs)
            return trace["raw_intent"]

        def normalize(*args, **kwargs):
            trace["normalized_intent"] = original_normalize(*args, **kwargs)
            return trace["normalized_intent"]

        def validate(*args, **kwargs):
            trace["validated_intent"] = original_validate(*args, **kwargs)
            return trace["validated_intent"]

        def finalize(narration, *args, **kwargs):
            trace["model_narration"] = narration
            result = original_finalize(narration, *args, **kwargs)
            trace["narration_replaced"] = result != game.clean_dm_response(narration) if isinstance(narration, str) and narration.strip() else True
            return result

        try:
            with patch.object(game.ollama, "chat", chat), \
                 patch.object(game, "parse_player_intent", parse), \
                 patch.object(game, "normalize_intent", normalize), \
                 patch.object(game, "validate_intent", validate), \
                 patch.object(game, "finalize_narration", finalize):
                result = session.run_player_turn(player_input)
            trace["action_result"] = result["action_result"]
            trace["narration"] = result["narration"]
        except Exception as error:
            trace["error"] = repr(error)

        trace["state_after"] = {
            "location": session.world_state["location"],
            "npcs": copy.deepcopy(session.world_state["npcs"]),
            "features": copy.deepcopy(session.world_state["features"]),
            "inventory": copy.deepcopy(session.world_state["inventory"]),
        }
        trace["state_delta"] = {
            key: [value, trace["state_after"][key]]
            for key, value in trace["state_before"].items()
            if value != trace["state_after"][key]
        }
        trace["model_call_count"] = len(trace["calls"])
        trace["issues"] = []
        action = trace.get("action_result", {})
        narration = trace.get("narration", "")
        location = trace["state_after"]["location"]
        if label == "travel_tavern" and (action.get("status") != "completed" or location != "tavern"):
            trace["issues"].append("Tavern travel did not commit")
        if label == "travel_forest" and (action.get("status") != "completed" or location != "forest"):
            trace["issues"].append("Forest travel did not commit")
        if label.startswith("explore_") and action.get("action") != "explore":
            trace["issues"].append("Exploration misclassified")
        if label in ("presence", "npc_identity") and "Gromm" not in narration:
            trace["issues"].append("Known NPC omitted")
        if label in ("location_name", "location_query") and ("Taverna" not in narration or location != "tavern"):
            trace["issues"].append("Location answer contradicts state")
        if label == "false_presence" and ("Gromm" in narration or location != "forest"):
            trace["issues"].append("Remote NPC appears in forest")
        if label == "unverified_claim":
            if location != "forest":
                trace["issues"].append("Unverified claim changed location")
            denial_terms = (
                "kayıt yok", "kayit yok", "hatırlamıyor", "hatirlamiyor",
                "hatırlamıyorum", "doğrulanm", "dogrulanm", "belirsiz",
                "bulunmuyor", "böyle bir şey",
            )
            if not any(term in narration.casefold() for term in denial_terms):
                trace["issues"].append("Accepted narration affirmed unverified historical premise")
        if label in ("explore_tavern", "explore_forest") and trace["state_before"]["location"] != location:
            trace["issues"].append("Exploration moved the player")
        if label in ("travel_tavern", "explore_tavern", "npc_dialogue", "travel_forest", "explore_forest") and not any(
            call["stage"] == "narration" for call in trace["calls"]
        ):
            trace["issues"].append("Expected a live narration model call")
        if not narration.strip():
            trace["issues"].append("Empty narration")
        if action.get("action") == "travel" and action.get("status") != "completed" and "ulaştın" in narration.casefold():
            trace["issues"].append("Narration claims uncommitted arrival")
        if trace["model_call_count"] > 2:
            trace["issues"].append("More than two model calls in one turn")
        if any("error" in call for call in trace["calls"]):
            trace["issues"].append("Model call failed")
        if "error" in trace:
            trace["issues"].append("Turn raised an exception")
        records.append(trace)

    issues = sum(len(row["issues"]) for row in records)
    calls = sum(row["model_call_count"] for row in records)
    passed = not issues and calls > 0
    print(json.dumps({
        "status": "PASS" if passed else "FAIL",
        "game_sha256": digest, "model": "qwen3:8b", "turns_run": len(records),
        "live_model_calls": calls,
        "maximum_calls_per_turn": max(row["model_call_count"] for row in records),
        "observed_narration_replacements": sum(bool(row.get("narration_replaced")) for row in records),
        "issues": issues, "turns": records,
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
