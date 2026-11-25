"""D-531 stage 4: the two autosave-failure sites of play_turn put every turn-owned field back.

The patched autosave first overwrites every field the turn owns and the world, then fails. The answer must be the
site's own body, and every field must be the pre-turn value again: a site that forgets one fails here. Real FastAPI
app, real SessionManager, temporary store, fixed town.
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import httpx

from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStaleError, CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from api.tests.town_seed import default_town

TOWN_SEED = 8560


class TurnAutosaveRollback(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        with default_town(self, TOWN_SEED):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.record = self.manager.get(self.created["session_id"])
        self.session = self.record.game_session

        def engine_turn(_message, **_kwargs):
            self.session.world_state.setdefault("flags", {})["d531_probe"] = True
            return {"narration": "Kapıdan hafif bir ses geliyor.",
                    "action_result": {"action": "world_interaction", "status": "resolved", "success": True,
                                      "state_changes": []}}

        self.session.run_player_turn = engine_turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def tamper_then_raise(self, error: Exception):
        """An autosave that overwrites every field the turn owns and the world, then fails."""
        def side_effect(*_args, **_kwargs):
            self.session.world_state.setdefault("flags", {})["d531_autosave"] = True
            self.session.campaign_lore_state = "TAMPERED_SESSION_LORE"
            self.session.world_metadata = {"tampered": True}
            self.record.journal = {"tampered": True}
            self.record.narrative_memory = {"tampered": True}
            self.record.lore_authority = "TAMPERED_RECORD_LORE"
            raise error
        return side_effect

    async def assert_site(self, error: Exception, status: int, detail: dict, *, receipt=None):
        lore = self.record.lore_authority
        metadata = copy.deepcopy(self.session.world_metadata)
        journal = copy.deepcopy(self.record.journal)
        memory = copy.deepcopy(self.record.narrative_memory)
        flags = copy.deepcopy(self.session.world_state.get("flags", {}))
        undo = self.record.undo_checkpoint
        body = {"message": "Kapının arkasından ses dinliyorum.", "action_id": str(uuid.uuid4())}
        with patch.object(self.manager, "autosave_turn", side_effect=self.tamper_then_raise(error)):
            if receipt is None:
                answer = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/turn", json=body)
            else:
                with patch.object(self.manager, "get_turn_action", side_effect=[None, receipt]):
                    answer = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/turn", json=body)
        self.assertEqual((answer.status_code, answer.json()["detail"]), (status, detail), answer.text)
        self.assertIs(self.session.campaign_lore_state, lore)
        self.assertEqual(self.session.world_metadata, metadata)
        self.assertEqual(self.record.journal, journal)
        self.assertEqual(self.record.narrative_memory, memory)
        self.assertIs(self.record.lore_authority, lore)
        self.assertEqual(self.session.world_state.get("flags", {}), flags, "the turn's world change was rolled back")
        self.assertIs(self.record.undo_checkpoint, undo, "a failed save keeps the Undo point")
        self.assertTrue(self.record.usable)
        self.assertEqual(len(self.store.get_campaign(self.created["campaign_id"]).history), 0)

    async def test_campaign_error_site_storage(self):
        await self.assert_site(CampaignStorageError("disk"), 503, {
            "code": "campaign_storage_unavailable", "message": "Macera kaydı şu anda güvenli biçimde saklanamıyor.",
        })

    async def test_campaign_error_site_stale(self):
        await self.assert_site(CampaignStaleError("stale"), 409, {"code": "campaign_stale", "message": "stale"})

    async def test_campaign_error_site_stale_with_other_receipt(self):
        await self.assert_site(CampaignStaleError("stale"), 409, {
            "code": "action_id_conflict", "message": "This action ID was already used for a different action.",
        }, receipt={"request_hash": "d531-other"})

    async def test_other_error_site(self):
        await self.assert_site(RuntimeError("disk"), 500, {
            "code": "persistence_error", "message": "The campaign turn could not be saved safely.",
        })


if __name__ == "__main__":
    unittest.main()
