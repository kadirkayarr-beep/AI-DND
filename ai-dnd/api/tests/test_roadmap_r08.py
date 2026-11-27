"""R08: an archived receipt never lets an old action run twice.

An archived id keeps verified idempotency data (action id, request hash, result digest, revision) in the SAME campaign
store. A retry of it is refused (it was applied; its result was archived), never re-executed and never treated as new.
Nothing in the game writes the archive any more (D-536), so the rows are put there by the test fixture. Real FastAPI
app, real SessionManager and CampaignStore; only the model boundary is the FakeOllamaClient.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

import httpx

from api.auth import FixedAuthenticator, Principal
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.receipt_archive_fixture import archive_receipts
from api.tests.test_campaign_api import FakeOllamaClient
from api.tests.town_seed import default_town

TOWN_SEED = 8610


class ArchivedReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "campaigns.sqlite3"
        self.build()
        with default_town(self, TOWN_SEED):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.cid, self.sid = self.created["campaign_id"], self.created["session_id"]
        self.install_turn()

    def build(self, _resume_campaign_id=None):
        self.store = CampaignStore(self.db_path, bound_principal=TEST_PLAYER)
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")

    def install_turn(self):
        self.record = self.manager.get(self.sid)
        self.session = self.record.game_session
        self.calls = 0

        def turn(_message, **_kwargs):
            self.calls += 1
            self.session.character["current_hp"] -= 1  # a spend: running twice would show here
            return {"narration": "Kapıdan hafif bir ses geliyor.",
                    "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}

        self.session.run_player_turn = turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def post(self, action_id, message="Kapıyı dinliyorum."):
        return self.http.post(f"/api/game/sessions/{self.sid}/turn", json={"message": message, "action_id": action_id})

    def rows(self, table):
        with closing(sqlite3.connect(self.db_path)) as db:
            return db.execute(f"SELECT COUNT(*) FROM {table} WHERE campaign_id = ?", (self.cid,)).fetchone()[0]

    async def play(self, count):
        ids = []
        for index in range(count):
            action_id = str(uuid.uuid4())
            self.assertEqual((await self.post(action_id, f"Hamle {index}")).status_code, 200)
            ids.append(action_id)
        return ids

    async def test_archived_receipt_never_reexecutes_old_action(self):
        oldest, *_ = await self.play(3)
        hp = self.session.character["current_hp"]
        self.assertEqual(archive_receipts(self.db_path, self.cid), 3)
        self.assertEqual(self.rows("campaign_turn_actions"), 0)
        self.assertEqual(self.rows("campaign_turn_actions_archive"), 3)
        calls = self.calls

        # The oldest id, retried unchanged: refused as already applied, never re-run, never a new spend.
        again = await self.post(oldest, "Hamle 0")
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json()["detail"]["code"], "action_archived")
        self.assertNotIn("not_applied", again.json()["detail"], "it WAS applied; only its stored reply is archived")
        self.assertEqual((self.calls, self.session.character["current_hp"]), (calls, hp))
        # A different request under the same id is still a conflict.
        changed = await self.post(oldest, "Başka bir şey yapıyorum.")
        self.assertEqual(changed.json()["detail"]["code"], "action_id_conflict")
        status = await self.http.get(f"/api/game/sessions/{self.sid}/actions/{oldest}")
        self.assertEqual(status.json()["state"], "applied")

        # Reload and restart: a brand-new manager over the same file gives the same answer; nothing runs.
        await self.http.aclose()
        self.build()
        resumed = self.manager.resume_campaign(self.cid)
        self.sid = resumed[0]
        self.install_turn()
        restarted = await self.post(oldest, "Hamle 0")
        self.assertEqual(restarted.status_code, 409, restarted.text)
        self.assertEqual(restarted.json()["detail"]["code"], "action_archived")
        self.assertEqual(self.calls, 0, "after archiving + reload + restart the oldest id produced no new spend")

        # A genuinely new action is unaffected and spends exactly once.
        self.assertEqual((await self.post(str(uuid.uuid4()), "Yeni hamle")).status_code, 200)
        self.assertEqual(self.calls, 1)

        # Ownership does not change: another principal cannot read the tombstone.
        stranger = Principal("https://issuer.example", "someone-else")
        other = CampaignStore(self.db_path, bound_principal=stranger)
        try:
            self.assertIsNone(other.get_turn_action(self.cid, oldest), "another owner sees no tombstone")
        except CampaignError:
            pass  # refusing outright is equally acceptable

    async def test_an_unverifiable_archive_blocks_the_retry_instead_of_running_it(self):
        oldest, *_ = await self.play(2)
        archive_receipts(self.db_path, self.cid, keep_latest=1)
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE campaign_turn_actions_archive SET result_digest = 'not-a-digest' WHERE action_id = ?", (oldest,))
            db.commit()
        calls = self.calls
        blocked = await self.post(oldest, "Hamle 0")
        self.assertNotEqual(blocked.status_code, 200, blocked.text)
        self.assertEqual(self.calls, calls, "an old result that cannot be verified is never silently treated as a new action")


if __name__ == "__main__":
    unittest.main()
