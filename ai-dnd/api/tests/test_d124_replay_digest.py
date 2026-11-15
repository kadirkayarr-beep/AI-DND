"""D-124 (ORTA-03): a retried action must not replay a stored reply whose text no longer matches its recorded digest.

Real FastAPI app, real SessionManager, temporary SQLite store; only the model boundary is the FakeOllamaClient.
The stored reply is edited behind the store's back (valid JSON, same action id) while its recorded digest stays.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

import httpx

from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignCorruptError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from api.tests.town_seed import fixed_town


class ReplayDigestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "campaigns.sqlite3"
        self.store = CampaignStore(self.db_path, bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")
        with fixed_town(self, 124_000):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.cid = self.created["campaign_id"]
        session = self.manager.get(self.created["session_id"]).game_session

        def turn(_message, **_kwargs):
            session.character["current_hp"] = session.character["current_hp"] - 1
            return {"narration": "Kapıdan hafif bir ses geliyor.",
                    "action_result": {"action": "world_interaction", "status": "resolved", "success": True,
                                      "state_changes": []}}

        session.run_player_turn = turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def post(self, action_id):
        return self.http.post(f"/api/game/sessions/{self.created['session_id']}/turn",
                              json={"message": "Kapıyı dinliyorum.", "action_id": action_id})

    def revision(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            return db.execute("SELECT revision FROM campaigns WHERE campaign_id = ?", (self.cid,)).fetchone()[0]

    def stored_row(self, action_id):
        with closing(sqlite3.connect(self.db_path)) as db:
            return db.execute(
                "SELECT response_json, result_digest FROM campaign_turn_actions WHERE campaign_id = ? AND action_id = ?",
                (self.cid, action_id),
            ).fetchone()

    def rewrite_reply(self, action_id, edit):
        response_json, digest = self.stored_row(action_id)
        response = json.loads(response_json)
        edit(response)
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE campaign_turn_actions SET response_json = ? WHERE campaign_id = ? AND action_id = ?",
                       (json.dumps(response, ensure_ascii=False, separators=(",", ":")), self.cid, action_id))
            db.commit()
        return digest

    async def test_retry_refuses_a_reply_that_no_longer_matches_its_digest(self):
        action_id = str(uuid.uuid4())
        ok = await self.post(action_id)
        self.assertEqual(ok.status_code, 200, ok.text)
        revision_before = self.revision()
        hp_before = ok.json()["state"]["character"]["current_hp"]

        def inflate_hp(response):
            response["state"]["character"]["current_hp"] = hp_before + 50
            response["narration"] = "Değiştirilmiş anlatı."

        digest = self.rewrite_reply(action_id, inflate_hp)
        self.assertIsNotNone(digest, "the receipt was written with its digest")

        with self.assertRaises(CampaignCorruptError):
            self.store.get_turn_action(self.cid, action_id)

        retried = await self.post(action_id)
        self.assertEqual(retried.status_code, 409, retried.text)
        self.assertEqual(retried.json()["detail"]["code"], "campaign_unavailable")
        self.assertNotIn("Değiştirilmiş anlatı.", retried.text)
        self.assertEqual(self.revision(), revision_before, "a refused retry commits nothing")
        self.assertEqual(self.stored_row(action_id)[1], digest, "the recorded digest is never rewritten to fit")

        # A different request under the same id is refused too: the damaged receipt still reserves its id.
        changed = await self.http.post(f"/api/game/sessions/{self.created['session_id']}/turn",
                                       json={"message": "Başka bir şey yapıyorum.", "action_id": action_id})
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["detail"]["code"], "campaign_unavailable")
        self.assertEqual(self.revision(), revision_before)

    async def test_untouched_reply_and_legacy_reply_without_digest_still_replay(self):
        action_id = str(uuid.uuid4())
        ok = await self.post(action_id)
        self.assertEqual(ok.status_code, 200, ok.text)
        replay = await self.post(action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), ok.json())

        # A row from before digests were recorded keeps NULL: nothing to compare, the other checks still apply.
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE campaign_turn_actions SET result_digest = NULL WHERE campaign_id = ? AND action_id = ?",
                       (self.cid, action_id))
            db.commit()
        self.assertEqual(self.store.get_turn_action(self.cid, action_id)["response"], ok.json())
        legacy = await self.post(action_id)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json(), ok.json())


if __name__ == "__main__":
    unittest.main()
