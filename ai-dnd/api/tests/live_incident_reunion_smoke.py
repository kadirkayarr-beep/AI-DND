"""One live narration of a saved Neverwinter reunion.

The incident and the reward are already Python facts. Qwen receives only the
player-known context and its reply is not written back.

    python -m api.tests.live_incident_reunion_smoke
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

AI_DND_DIR = Path(__file__).resolve().parents[2]
MODEL_NAME = "qwen3:8b"


def _emit(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def main():
    os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")
    sys.path.insert(0, str(AI_DND_DIR))
    try:
        import ollama
        import game
        from api import ollama_adapter
        from api.tests.test_incident_continuity import ContinuityTests
    except Exception as error:
        return _emit({"gate": "2B", "final_gate_status": "BLOCKED", "reason": f"import failed: {error}"})
    try:
        ollama.Client(host=os.environ["OLLAMA_HOST"], timeout=10).list()
    except Exception as error:
        return _emit({"gate": "2B", "final_gate_status": "BLOCKED", "reason": f"Ollama is unreachable: {error}"})

    case = ContinuityTests()
    case.setUp()
    try:
        case.test_talk_promotes_once_and_the_same_npc_is_there_days_later()
    except Exception as error:
        return _emit({"gate": "2B", "final_gate_status": "FAIL", "reason": f"fixture failed: {error}"}, 1)
    active = case.manager._campaign_sessions.get(case.campaign_id)
    record = case.manager._sessions.get(active) if active else None
    if record is None:
        return _emit({"gate": "2B", "final_gate_status": "FAIL", "reason": "Resumed session was not kept."}, 1)
    session = record.game_session
    token = game._ACTIVE_SESSION.set(session)
    try:
        context = game.build_world_context()
    finally:
        game._ACTIVE_SESSION.reset(token)
    prompt = json.dumps(context, ensure_ascii=False)
    if "Mirel" in prompt or "The crate was kicked over on purpose." in prompt or "talk:" in prompt:
        return _emit({"gate": "2B", "final_gate_status": "FAIL", "reason": "The narrator packet leaked private continuity."}, 1)
    if "Elmalar tahtalara yuvarlanmış." not in prompt:
        return _emit({"gate": "2B", "final_gate_status": "FAIL", "reason": "The known surface fact was not in the narrator packet."}, 1)
    before = copy.deepcopy(session.world_state)
    client = ollama.Client(host=os.environ["OLLAMA_HOST"], timeout=90)
    adapter = ollama_adapter.AuthenticatedOllamaAdapter(client)
    adapter.install_for_engine()
    with adapter.capture_model_calls() as calls:
        response = game.ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Narrate only the supplied player-known context. Do not invent names, rewards, or quests."},
                {"role": "user", "content": prompt},
            ],
            think=False,
            options={"temperature": 0.2, "num_predict": 180},
        )
    text = game.ollama_response_content(response)
    after = session.world_state
    payload = {
        "gate": "2B",
        "final_gate_status": "PASS" if after == before and len(calls) == 1 else "FAIL",
        "model": MODEL_NAME,
        "model_calls": len(calls),
        "world_unchanged": after == before,
        "reply_mentions_private_name": isinstance(text, str) and "Mirel" in text,
        "reply_applied": False,
        "review_pending_is_pass": False,
    }
    case.directory.cleanup()
    return _emit(payload, 0 if payload["final_gate_status"] == "PASS" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
