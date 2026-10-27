"""Disposable backend for the R02 live-browser check (tests/r02-live-browser.test.mjs).

Real FastAPI app, real SessionManager, real SQLite store in the database named by AI_DND_CAMPAIGN_DB (a temporary file made
by the isolated runner), a fixed TEST principal and a deterministic turn engine. No model, no network beyond 127.0.0.1,
never the real game server or any personal save. A message containing OUTAGE raises the provider-outage error before any
effect (the 503 path that leaves an intent open).
"""
import os
import sys
from pathlib import Path

if not os.environ.get("AI_DND_CAMPAIGN_DB"):
    sys.exit("refusing to start: AI_DND_CAMPAIGN_DB must name a disposable database")
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "ai-dnd"))

import uvicorn  # noqa: E402

import game  # noqa: E402
from api.auth import FixedAuthenticator  # noqa: E402
from api.main import create_app  # noqa: E402
from api.ollama_adapter import AuthenticatedOllamaAdapter  # noqa: E402
from api.persistence.campaign_store import CampaignStore  # noqa: E402
from api.session_manager import SessionManager  # noqa: E402
from api.tests.auth_fixture import TEST_PLAYER  # noqa: E402
from api.tests.test_campaign_api import FakeOllamaClient  # noqa: E402
from dialogue_runtime import DialogueProviderError  # noqa: E402


def deterministic_turn(_self, message, **_kwargs):
    if "OUTAGE" in message:
        raise DialogueProviderError("synthetic provider outage")
    return {
        "narration": f"Yanıt: {message}",
        "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []},
    }


game.GameSession.run_player_turn = deterministic_turn

adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
with adapter.engine_binding():
    store = CampaignStore(Path(os.environ["AI_DND_CAMPAIGN_DB"]), bound_principal=TEST_PLAYER)
    application = create_app(
        session_manager=SessionManager(campaign_store=store),
        ollama_adapter=adapter,
        authenticator=FixedAuthenticator(TEST_PLAYER),
    )
    uvicorn.run(application, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
