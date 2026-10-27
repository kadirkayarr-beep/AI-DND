"""R05: after a double fault (a mutation fails AND its restore fails) every route that could read or write the
runtime is refused, nothing dirty is persisted, and only a VERIFIED restore of a trusted snapshot makes a session usable.

Real FastAPI app, real SessionManager, temporary SQLite store; only the model boundary is the FakeOllamaClient.
The faults are injected at the real seams (the engine turn and session._restore_runtime_snapshot).
"""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import types
import unittest
import uuid
from unittest.mock import patch

import httpx

from api import runtime_recovery
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient


class FakeRuntime:
    def __init__(self, state, restore_effect="exact"):
        self.state = copy.deepcopy(state)
        self.restore_effect = restore_effect

    def serialize_game_state(self):
        return copy.deepcopy(self.state)

    def _restore_runtime_snapshot(self, snapshot):
        if self.restore_effect == "raise":
            raise RuntimeError("synthetic failed runtime restoration")
        if self.restore_effect == "exact":
            self.state = copy.deepcopy(snapshot["state"])
        # "silent": claims success but leaves the dirty state in place


class RestoreTrustedRuntimeTests(unittest.TestCase):
    def setup(self, effect):
        trusted = {"hp": 12, "inventory": ["Kısa kılıç"]}
        runtime = FakeRuntime({"hp": 3, "inventory": ["Kısa kılıç", "Hırsızlanmış mühür"]}, effect)
        record = types.SimpleNamespace(game_session=runtime, usable=False)
        snapshot = {"save": copy.deepcopy(trusted), "runtime": {"state": copy.deepcopy(trusted)}}
        return record, runtime, snapshot

    def test_a_verified_restore_is_the_only_way_a_quarantined_session_becomes_usable(self):
        record, runtime, snapshot = self.setup("exact")
        self.assertTrue(runtime_recovery.restore_trusted_runtime(record, snapshot))
        self.assertTrue(record.usable)
        self.assertEqual(runtime.state, snapshot["save"])

    def test_a_restore_that_raises_leaves_the_session_closed(self):
        record, _runtime, snapshot = self.setup("raise")
        self.assertFalse(runtime_recovery.restore_trusted_runtime(record, snapshot))
        self.assertFalse(record.usable)

    def test_a_restore_that_claims_success_but_does_not_match_the_snapshot_is_refused_and_closes_the_session(self):
        record, _runtime, snapshot = self.setup("silent")
        record.usable = True  # it looked healthy until the verification
        self.assertFalse(runtime_recovery.restore_trusted_runtime(record, snapshot))
        self.assertFalse(record.usable, "an unverified restore must never leave the session usable")


class DoubleFaultQuarantineTests(unittest.IsolatedAsyncioTestCase):
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
        created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        self.created = created.json()
        self.cid, self.sid = self.created["campaign_id"], self.created["session_id"]
        self.record = self.manager.get(self.sid)
        self.session = self.record.game_session
        self.engine_calls = 0
        self.hp_before = self.session.character["current_hp"]

        def failing_turn(_message, **_kwargs):
            self.engine_calls += 1
            self.session.character["current_hp"] = 1  # the mutation that must never survive
            raise RuntimeError("synthetic engine failure after mutation")

        self.session.run_player_turn = failing_turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def turn(self):
        return self.http.post(f"/api/game/sessions/{self.sid}/turn", json={"message": "Kapıyı itiyorum.", "action_id": str(uuid.uuid4())})

    def persisted(self):
        campaign = self.store.get_campaign(self.cid)
        return {"payload": campaign.payload, "revision": campaign.metadata["revision"], "history": len(campaign.history)}

    async def all_routes(self):
        base = f"/api/game/sessions/{self.sid}"
        return {
            "state": await self.http.get(f"{base}/state"),
            "turn": await self.turn(),
            "undo": await self.http.post(f"{base}/undo", json={"action_id": str(uuid.uuid4()), "target_action_id": str(uuid.uuid4())}),
            "quest accept": await self.http.post(f"{base}/quests/q-1/accept"),
            "quest cancel": await self.http.post(f"{base}/quests/q-1/cancel"),
            "species": await self.http.post(f"{base}/species-actions", json={"action": "short_rest", "action_id": str(uuid.uuid4())}),
            "ambient": await self.http.post(f"{base}/ambient-events/{uuid.uuid4()}/actions", json={"action": "observe", "action_id": str(uuid.uuid4())}),
            "save": await self.http.post(f"/api/game/campaigns/{self.cid}/save"),
        }

    def assert_quarantined(self, responses):
        for route, response in responses.items():
            self.assertEqual(response.status_code, 409, f"{route}: {response.status_code} {response.text}")
            # The save route reports the same closure through the manager's own error code.
            allowed = {"session_restore_failed", "campaign_not_active"} if route == "save" else {"session_restore_failed"}
            self.assertIn(response.json()["detail"]["code"], allowed, route)
        self.assertEqual(self.engine_calls, 1, "no route may reach the engine of a quarantined session")

    async def test_double_fault_quarantines_all_routes(self):
        before = self.persisted()
        with patch.object(self.session, "_restore_runtime_snapshot", side_effect=RuntimeError("synthetic failed runtime restoration")):
            first = await self.turn()
        self.assertEqual(first.status_code, 409, first.text)
        self.assertEqual(first.json()["detail"]["code"], "session_restore_failed")
        self.assertFalse(self.record.usable)
        self.assert_quarantined(await self.all_routes())
        # The dirty runtime was never persisted: durable truth is the pre-turn revision, and saving is refused.
        self.assertEqual(self.persisted(), before)
        with self.assertRaises(Exception):
            self.manager.save_campaign(self.cid)
        self.assertEqual(self.persisted(), before)

    async def test_a_restore_that_silently_does_not_restore_also_quarantines(self):
        # No exception: the restore "succeeds" but leaves the dirty state. That must be detected, not trusted.
        before = self.persisted()
        with patch.object(self.session, "_restore_runtime_snapshot", return_value=None):
            first = await self.turn()
        self.assertEqual(first.status_code, 409, first.text)
        self.assertEqual(first.json()["detail"]["code"], "session_restore_failed")
        self.assertFalse(self.record.usable)
        self.assert_quarantined(await self.all_routes())
        self.assertEqual(self.persisted(), before)

    async def test_a_new_process_resumes_clean_durable_truth_without_the_dirty_flag(self):
        before = self.persisted()
        with patch.object(self.session, "_restore_runtime_snapshot", side_effect=RuntimeError("synthetic failed runtime restoration")):
            await self.turn()
        restarted = SessionManager(campaign_store=CampaignStore(self.db_path, bound_principal=TEST_PLAYER))
        _sid, record, *_ = restarted.resume_campaign(self.cid)
        self.assertTrue(record.usable)
        self.assertEqual(record.game_session.character["current_hp"], self.hp_before)
        self.assertEqual(CampaignStore(self.db_path, bound_principal=TEST_PLAYER).get_campaign(self.cid).payload, before["payload"])


    async def test_a_request_queued_behind_the_failing_one_is_refused_when_the_lock_is_released(self):
        import asyncio

        base = f"/api/game/sessions/{self.sid}"
        requests = {
            "turn": lambda: self.turn(),
            "undo": lambda: self.http.post(f"{base}/undo", json={"action_id": str(uuid.uuid4()), "target_action_id": str(uuid.uuid4())}),
            "species": lambda: self.http.post(f"{base}/species-actions", json={"action": "short_rest", "action_id": str(uuid.uuid4())}),
        }
        for name, send in requests.items():
            with self.subTest(route=name):
                self.record.usable = True
                self.engine_calls = 0
                self.record.turn_lock.acquire()  # stands for the request that is still failing
                try:
                    queued = asyncio.ensure_future(send())
                    await asyncio.sleep(0.3)  # it passed the entry check (usable) and now waits for the lock
                    self.record.usable = False  # the holder's restore failed: the session is quarantined
                finally:
                    self.record.turn_lock.release()
                response = await queued
                self.assertEqual(response.status_code, 409, f"{name}: {response.text}")
                self.assertEqual(response.json()["detail"]["code"], "session_restore_failed", name)
                self.assertEqual(self.engine_calls, 0, f"{name} reached the engine of a quarantined session")


    async def test_a_double_fault_that_starts_in_the_ambient_route_quarantines_too(self):
        def failing_ambient(*_args, **_kwargs):
            self.session.character["current_hp"] = 1  # the mutation that must never survive
            raise RuntimeError("synthetic ambient failure after mutation")

        self.session.resolve_ambient_event_action = failing_ambient
        event_id = str(uuid.uuid4())
        with patch.object(self.session, "_restore_runtime_snapshot", side_effect=RuntimeError("synthetic failed runtime restoration")):
            first = await self.http.post(f"/api/game/sessions/{self.sid}/ambient-events/{event_id}/actions",
                                         json={"action": "observe", "action_id": str(uuid.uuid4())})
        self.assertEqual(first.status_code, 409, first.text)
        self.assertEqual(first.json()["detail"]["code"], "session_restore_failed")
        self.assertFalse(self.record.usable, "the ambient route must close the session on a double fault")
        self.assert_quarantined_after_other_origin(await self.all_routes())

    def assert_quarantined_after_other_origin(self, responses):
        for route, response in responses.items():
            allowed = {"session_restore_failed", "campaign_not_active"} if route == "save" else {"session_restore_failed"}
            self.assertEqual(response.status_code, 409, f"{route}: {response.text}")
            self.assertIn(response.json()["detail"]["code"], allowed, route)


if __name__ == "__main__":
    unittest.main()
