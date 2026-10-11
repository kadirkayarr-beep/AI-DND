"""Stage 10B model-failure and negative-path observations.

These replace the model client. They are not the live Qwen evidence.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.serializers import serialize_session_state
from api.session_manager import SessionManager

EVIDENCE = Path(os.environ["AI_DND_STAGE10B_EVIDENCE_DIR"]) if os.environ.get("AI_DND_STAGE10B_EVIDENCE_DIR") else Path(__file__).resolve().parents[3] / ".local" / "evidence" / "stage10b-acceptance-v1-20261009"
SHOP = "Bu kampanya için burada küçük bir yerel dükkân ve onu işleten tek bir dükkâncı oluştur."


class FakeOllamaClient:
    def __init__(self, chat_error=None, content="not-json"):
        self.chat_error = chat_error
        self.content = content
        self.chat_calls = 0

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.chat_calls += 1
        if self.chat_error:
            raise RuntimeError(self.chat_error)
        return {"message": {"content": self.content}}


async def _campaign(http: httpx.AsyncClient) -> tuple[str, dict]:
    created = await http.post("/api/sessions")
    if created.status_code != 200:
        raise RuntimeError(f"session HTTP {created.status_code}: {created.text[:400]}")
    body = created.json()
    return body["session_id"], body.get("state") or {}


async def _observe_model_failures() -> dict:
    rows = []

    async def once(label: str, chat_error, content: str, message: str) -> None:
        fake = FakeOllamaClient(chat_error=chat_error, content=content)
        adapter = AuthenticatedOllamaAdapter(fake)
        with adapter.engine_binding():
            app = create_app(session_manager=SessionManager(), ollama_adapter=adapter)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
                session_id, before_state = await _campaign(http)
                session = app.state.session_manager.get(session_id).game_session
                if "tavern" in (session.world_state.get("locations") or {}):
                    session.world_state["location"] = "tavern"
                before = serialize_session_state(session)
                response = await http.post(
                    f"/api/sessions/{session_id}/turn",
                    json={"message": message},
                )
                after = serialize_session_state(session)
                shops_before = len(before_state.get("shops") or [])
                shops_after = len((after.get("shops") or []))
                rows.append({
                    "label": label,
                    "status": response.status_code,
                    "detail": response.json().get("detail") if response.status_code != 200 else None,
                    "chat_calls": fake.chat_calls,
                    "state_unchanged": before == after,
                    "shops_before": shops_before,
                    "shops_after": shops_after,
                    "narration": (response.json().get("narration") if response.status_code == 200 else None),
                })

    await once("before_resolution_exception", "down", "", "Mor bir düşünceyi yüksek sesle kuruyorum.")
    await once("after_resolution_exception", "down", "", SHOP)
    await once("after_resolution_invalid_text", None, "bu model cümlesi otoriter değildir", SHOP)
    return {"observations": rows}


def _negative_paths() -> dict:
    session = game.create_session(seed=2010)
    session.world_state["locations"]["fr:city:neverwinter"] = {
        "id": "fr:city:neverwinter",
        "name": "Neverwinter",
        "type": "city",
    }
    session.world_state["location"] = "fr:city:neverwinter"
    before_inventory = list(session.world_state.get("inventory") or [])
    before_quests = copy.deepcopy(session.world_state.get("quests") or [])
    before_events = copy.deepcopy(session.world_state.get("events") or [])
    with patch("game.ollama.chat", side_effect=AssertionError("model")):
        lore = session.run_player_turn("Xanathar'ın gizli hazinesi bu sokakta duruyor mu?")
        history = session.run_player_turn("Dün gece kral bana tahtı verdi, hatırlıyor musun?")
    missing = None
    missing_error = None
    try:
        with patch("game.ollama.chat", side_effect=AssertionError("model")):
            missing = session.run_player_turn("Saldırıyorum.", target_id="npc_does_not_exist")
    except Exception as error:
        missing_error = type(error).__name__
    return {
        "unsupported_lore": {
            "status": lore["action_result"].get("status"),
            "narration": lore.get("narration"),
            "inventory_unchanged": list(session.world_state.get("inventory") or []) == before_inventory,
            "quests_unchanged": session.world_state.get("quests") == before_quests,
            "calls": lore["_engine_event_evidence"]["telemetry"]["total_model_calls"],
        },
        "unverified_history": {
            "status": history["action_result"].get("status"),
            "events_unchanged": session.world_state.get("events") == before_events,
            "narration": history.get("narration"),
            "calls": history["_engine_event_evidence"]["telemetry"]["total_model_calls"],
        },
        "missing_target": {
            "error": missing_error,
            "narration": None if missing is None else missing.get("narration"),
            "status": None if missing is None else missing["action_result"].get("status"),
        },
    }


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    model_failure = asyncio.run(_observe_model_failures())
    negative = _negative_paths()
    (EVIDENCE / "model-failure.json").write_text(
        json.dumps(model_failure, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVIDENCE / "negative-paths.json").write_text(
        json.dumps(negative, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model": model_failure, "negative": negative}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
