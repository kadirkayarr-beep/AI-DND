"""R08: receipt growth is bounded without ever letting an old action run twice.

Old receipts are compacted into verified idempotency tombstones (action id, request hash, result digest, revision) in
the SAME campaign store; the full reply is dropped. A retry of an archived id is refused (it was applied; its result was
archived), never re-executed and never treated as new. There is no blind TTL deletion. Real FastAPI app, real
SessionManager and CampaignStore; only the model boundary is the FakeOllamaClient.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import tracemalloc
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
from api.tests.test_campaign_api import FakeOllamaClient


class CompactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "campaigns.sqlite3"
        self.build()
        created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.cid, self.sid = self.created["campaign_id"], self.created["session_id"]
        self.install_turn()

    def build(self, resume_campaign_id=None):
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

    def revision(self):
        return self.store.get_campaign(self.cid).metadata["revision"]

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

    async def test_compaction_never_reexecutes_old_action(self):
        oldest, *_ = await self.play(3)
        hp = self.session.character["current_hp"]
        revision_before = self.revision()
        outcome = self.store.compact_receipts(self.cid, before_revision=self.revision() + 1)
        self.assertEqual(outcome["archived"], 3)
        self.assertEqual(self.rows("campaign_turn_actions"), 0)
        self.assertEqual(self.rows("campaign_turn_actions_archive"), 3)
        self.assertEqual(self.revision(), revision_before, "compaction is not a state change: the revision head is kept")
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
        self.assertEqual(self.calls, 0, "after compaction + reload + restart the oldest id produced no new spend")

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
        self.store.compact_receipts(self.cid, before_revision=self.revision() + 1)
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE campaign_turn_actions_archive SET result_digest = 'not-a-digest' WHERE action_id = ?", (oldest,))
            db.commit()
        calls = self.calls
        blocked = await self.post(oldest, "Hamle 0")
        self.assertNotEqual(blocked.status_code, 200, blocked.text)
        self.assertEqual(self.calls, calls, "an old result that cannot be verified is never silently treated as a new action")

    async def test_an_open_reaction_keeps_its_full_receipt(self):
        await self.play(2)
        self.session.world_state.setdefault("combat", {})["pending_reaction"] = {"actor_id": "npc-1", "kind": "opportunity_attack"}
        self.manager.save_campaign(self.cid)
        outcome = self.store.compact_receipts(self.cid, before_revision=self.revision() + 1)
        self.assertGreaterEqual(outcome["protected"], 1)
        self.assertGreaterEqual(self.rows("campaign_turn_actions"), 1, "the receipt of the turn that opened the reaction is kept whole")

    async def test_compaction_is_idempotent_and_never_touches_newer_revisions(self):
        ids = await self.play(3)
        head = self.revision()
        first = self.store.compact_receipts(self.cid, before_revision=head)  # strictly older than the head only
        second = self.store.compact_receipts(self.cid, before_revision=head)
        self.assertEqual(second["archived"], 0)
        self.assertEqual(self.rows("campaign_turn_actions") + self.rows("campaign_turn_actions_archive"), 3)
        self.assertEqual(self.rows("campaign_turn_actions_archive"), first["archived"])
        newest = ids[-1]
        self.assertEqual((await self.post(newest, "Hamle 2")).status_code, 200, "the newest receipt still replays its full reply")

    async def test_measure_growth_at_10_100_1000_10000_synthetic_actions(self):
        reply = {"session_id": "s", "narration": "x" * 1500, "state": {"character": {"current_hp": 10}}}
        measurements = []
        for count in (10, 100, 1000, 10000):
            with self.subTest(actions=count):
                created = await self.http.post("/api/game/campaigns", json={})
                cid = created.json()["campaign_id"]
                self.insert_synthetic(cid, count, reply)
                size_before = self.vacuumed_size()
                tracemalloc.start()
                started = time.perf_counter()
                outcome = self.store.compact_receipts(cid, before_revision=count + 1)
                elapsed = time.perf_counter() - started
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                size_after = self.vacuumed_size()
                oldest = self.synthetic_id(0)
                looked = time.perf_counter()
                stored = self.store.get_turn_action(cid, oldest)
                lookup_ms = (time.perf_counter() - looked) * 1000
                self.assertEqual(outcome["archived"], count)
                self.assertTrue(stored["archived"])
                measurements.append({"actions": count, "bytes_before": size_before, "bytes_after": size_after,
                                     "compaction_s": round(elapsed, 3), "peak_ram_kib": peak // 1024, "lookup_ms": round(lookup_ms, 2)})
                if count >= 100:
                    self.assertLess(size_after, size_before, "the archive is smaller than the full replies it replaced")
                self.assertLess(peak, 64 * 1024 * 1024, "compaction streams in batches; it does not load every reply at once")
                self.assertLess(lookup_ms, 250, "an archived id is still looked up by primary key")
        print("R08 measurements:", json.dumps(measurements))

    # -- helpers -----------------------------------------------------------------------------------------------
    @staticmethod
    def synthetic_id(index):
        return str(uuid.UUID(int=index + 1, version=4))

    def insert_synthetic(self, cid, count, reply):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("PRAGMA foreign_keys = ON")
            rows = []
            for index in range(count):
                action_id = self.synthetic_id(index)
                body = dict(reply, action_id=action_id)
                text = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                rows.append((cid, action_id, hashlib.sha256(action_id.encode()).hexdigest(), text,
                             "2026-10-27T00:00:00Z", index, index + 1, hashlib.sha256(text.encode("utf-8")).hexdigest()))
            db.executemany(
                "INSERT INTO campaign_turn_actions (campaign_id, action_id, request_hash, response_json, created_at, "
                "base_revision, committed_revision, result_digest) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            db.commit()

    def vacuumed_size(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("VACUUM")
        return os.path.getsize(self.db_path)


if __name__ == "__main__":
    unittest.main()
