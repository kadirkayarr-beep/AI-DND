"""B1 (step 0): failures around the save boundary, proven one seam at a time before any fix.

Real FastAPI app, real SessionManager and a temporary SQLite campaign store; the model boundary is the
FakeOllamaClient and the engine turn is a small fake where a test needs one. Each seam is injected where it really is:
before the save (response build, save refused before its transaction), after the SQL commit but before the session's
revision token moves, and after the save has returned. The owner's real saves and keys are never read.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
import unittest
import uuid
from unittest.mock import patch

import httpx

import front_proposal
import game
import quest_catalog
import world_reactions
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient

_TRANSIENTS = ("_handed_note", "_coin_paid", "_front_coin", "_bribe_held_out", "_counter_held")
_FRONT_ON = {front_proposal.FLAG: "1", front_proposal.ROUTE_LOG: ""}


def runtime_facts(session: Any) -> dict[str, Any]:
    """Everything the rollback snapshot promises to give back, as plain data: no secrets, no logs."""
    return {
        "save": json.loads(json.dumps(session.serialize_game_state(), ensure_ascii=False, default=str)),
        "character": copy.deepcopy(session.character),
        "rng": session.rng.getstate(),
        "messages": copy.deepcopy(session.messages),
        "recent_narrations": copy.deepcopy(session.recent_dm_narrations),
        "pending_xp": copy.deepcopy(getattr(session, "_xp_level_up", None)),
        "persisted_engine_format": copy.deepcopy(session.__dict__.get("_persisted_engine_format")),
        "persistence_token": getattr(session, "_campaign_persistence_version", None),
    }


def record_facts(record: Any) -> dict[str, Any]:
    return {
        **runtime_facts(record.game_session),
        "journal": copy.deepcopy(record.journal),
        "narrative_memory": copy.deepcopy(record.narrative_memory),
        "lore_authority": record.lore_authority,
    }


class Step0CommitFailureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        # An unhandled server error must come back as a 500 the test can read, not as a raised exception.
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
                                      base_url="http://testserver")
        await self.new_campaign()

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    async def new_campaign(self):
        created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.cid, self.sid = body["campaign_id"], body["session_id"]
        self.record = self.manager.get(self.sid)
        self.session = self.record.game_session

    def durable(self) -> dict[str, Any]:
        stored = self.store.get_campaign(self.cid)
        return {"payload": stored.payload, "revision": stored.metadata["revision"], "history": len(stored.history)}

    def turn(self, message="Kapıyı itiyorum.", action_id=None):
        return self.http.post(f"/api/game/sessions/{self.sid}/turn",
                              json={"message": message, "action_id": action_id or str(uuid.uuid4())})

    def quest_definition(self) -> dict[str, Any]:
        return {
            "quest_id": "quest.step0-boundary",
            "title": "Orman Yolu",
            "description": "Ormana ulaş.",
            "objectives": [{"objective_id": "visit-forest", "description": "Ormana git.",
                            "type": "visit_location", "target": "forest"}],
        }

    def quest_url(self, command: str) -> str:
        return f"/api/game/sessions/{self.sid}/quests/quest.step0-boundary/{command}"

    @staticmethod
    def quest_status(engine_save: dict[str, Any]) -> str | None:
        quests = engine_save.get("world_state", {}).get("quests", [])
        found = [quest for quest in quests if quest.get("quest_id") == "quest.step0-boundary"]
        return found[0]["status"] if found else None

    # --- Step 1: the save boundary -------------------------------------------------------------------------------

    async def test_response_build_failure_restores_live_and_durable(self):
        trusted_before = record_facts(self.record)
        durable_before = self.durable()

        def engine_turn(_message, **_kwargs):
            self.session.rng.random()
            self.session.character["current_hp"] = 1  # the effect that must not outlive the failed answer
            return {"narration": "Kapı gıcırdayarak açılıyor.", "action_result": {}}

        self.session.run_player_turn = engine_turn
        with patch("api.main._turn_outcome", side_effect=RuntimeError("synthetic response build failure")):
            failed = await self.turn()

        self.assertEqual(failed.status_code, 500, failed.text)
        live_after_presave_failure = record_facts(self.record)
        durable_after_presave_failure = self.durable()
        self.assertEqual(live_after_presave_failure, trusted_before)
        self.assertEqual(durable_after_presave_failure, durable_before)
        self.assertTrue(self.record.usable, "a verified pre-commit restore keeps the session open")

    async def test_silent_rng_restore_error_quarantines(self):
        durable_before = self.durable()

        def failing_turn(_message, **_kwargs):
            for _ in range(5):
                self.session.rng.random()
            self.session.character["current_hp"] = 1
            raise RuntimeError("synthetic engine failure after dice were drawn")

        self.session.run_player_turn = failing_turn
        # The restore "succeeds" but leaves the dice where the failed turn put them.
        with patch.object(self.session.rng, "setstate", lambda _state: None):
            failed = await self.turn()

        self.assertGreaterEqual(failed.status_code, 400, failed.text)
        self.assertIs(self.record.usable, False, "an unverified dice restore must close the session")
        self.assertEqual(self.durable(), durable_before)


if __name__ == "__main__":
    unittest.main()
