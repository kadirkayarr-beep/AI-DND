"""HTTP replay must reject damaged event replies without replaying gameplay."""
import copy
from contextlib import closing
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures
from api.tests import test_persistence_idempotency as idempotency


class AmbientReceiptCorruptionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign
    install_test_ambient_event = fixtures.CampaignApiTests.install_test_ambient_event
    snapshot = idempotency.PersistenceIdempotencyTests.snapshot

    def raw_rows(self, store, campaign_id):
        with closing(store._connect()) as db:
            return (
                [tuple(row) for row in db.execute(
                    "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,),
                )],
                [tuple(row) for row in db.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? ORDER BY action_id",
                    (campaign_id,),
                )],
            )

    async def check_reopened_receipt(self, mutate=None, legacy=None):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        event_id = self.install_test_ambient_event(record.game_session)
        command = {"action_id": str(uuid4()), "action": "interact"}
        endpoint = f"ambient-events/{event_id}/actions"
        before_apply = copy.deepcopy(record.game_session.serialize_game_state())
        accepted = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/{endpoint}", json=command,
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["result"]["status"], "APPLIED")
        self.assertNotEqual(record.game_session.serialize_game_state(), before_apply)
        committed = self.store.get_campaign(campaign_id)
        receipt = self.store.get_turn_action(campaign_id, command["action_id"])
        self.assertEqual(receipt["response"]["ambient_event_response"], accepted.json())
        damaged = copy.deepcopy(receipt["response"])
        if legacy == "imported":
            # Startup reserves old journal identities without inventing a reply.
            with self.store._transaction() as db:
                db.execute(
                    "DELETE FROM campaign_turn_actions WHERE campaign_id = ? AND action_id = ?",
                    (campaign_id, command["action_id"]),
                )
        else:
            if legacy == "empty":
                damaged = {"action_id": command["action_id"], "legacy_ambient_result": {}}
            elif mutate is not None:
                mutate(damaged)
            self.assertEqual(damaged["action_id"], command["action_id"])
            with self.store._transaction() as db:
                updated = db.execute(
                    "UPDATE campaign_turn_actions SET response_json = ? WHERE campaign_id = ? AND action_id = ?",
                    (json.dumps(damaged), campaign_id, command["action_id"]),
                )
                self.assertEqual(updated.rowcount, 1)
        self.assertEqual(self.store.get_campaign(campaign_id), committed)
        fresh_store = CampaignStore(self.store.path)
        if legacy is None:
            loaded = fresh_store.get_turn_action(campaign_id, command["action_id"])
            self.assertEqual(loaded["request_hash"], receipt["request_hash"])
            self.assertEqual(loaded["response"], damaged)
        fresh = SessionManager(campaign_store=fresh_store)
        app = create_app(session_manager=fresh, ollama_adapter=None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://reload",
        ) as client:
            resumed = await client.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()["session_id"]
            restored = fresh.get(sid)
            self.assertIsNot(restored.game_session, record.game_session)
            reopened = fresh_store.get_campaign(campaign_id)
            self.assertEqual(reopened.payload, committed.payload)
            self.assertEqual(reopened.history, committed.history)
            self.assertEqual(reopened.combat_history, committed.combat_history)
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertEqual(restored.game_session.serialize_game_state(),
                             record.game_session.serialize_game_state())
            self.assertEqual(restored.game_session.rng.getstate(),
                             record.game_session.rng.getstate())
            # Resume may update last-played metadata. Snapshot immediately before retry.
            before = self.snapshot(restored)
            auxiliary = copy.deepcopy((
                restored.game_session.messages, restored.game_session.world_metadata,
            ))
            rows = self.raw_rows(fresh_store, campaign_id)
            with patch.object(restored.game_session, "resolve_ambient_event_action",
                              side_effect=AssertionError("Replay executed mechanics")) as mechanics, \
                 patch.object(fresh, "save_campaign_locked",
                              side_effect=AssertionError("Replay attempted persistence")) as locked_save, \
                 patch.object(fresh, "autosave_turn",
                              side_effect=AssertionError("Replay attempted autosave")) as autosave, \
                 patch.object(fresh_store, "save_campaign",
                              side_effect=AssertionError("Replay saved campaign")) as save:
                retry = await client.post(
                    f"/api/game/sessions/{sid}/{endpoint}", json=command,
                )
            if mutate is not None:
                self.assertEqual(retry.status_code, 409, retry.text)
                self.assertEqual(retry.json()["detail"]["code"], "campaign_unavailable")
                self.assertIsInstance(retry.json()["detail"]["message"], str)
                self.assertTrue(retry.json()["detail"]["message"])
            else:
                self.assertEqual(retry.status_code, 200, retry.text)
                expected = copy.deepcopy(accepted.json()["result"])
                expected.update(status="ALREADY_APPLIED", reason_code="event_already_resolved")
                if legacy == "empty":
                    expected.update(transition_id=None, canonical_event_id=None)
                self.assertEqual(retry.json()["result"], expected)
                self.assertEqual(retry.json()["session_id"], sid)
            for spy in (mechanics, locked_save, autosave, save):
                spy.assert_not_called()
            self.assertEqual(self.snapshot(restored), before)
            self.assertEqual((
                restored.game_session.messages, restored.game_session.world_metadata,
            ), auxiliary)
            self.assertEqual(self.raw_rows(fresh_store, campaign_id), rows)
            self.assertEqual(fresh_store.get_campaign(campaign_id), reopened)

    async def test_incomplete_saved_event_replies_fail_safely_after_resume(self):
        paths = (
            ("ambient_event_response",),
            ("ambient_event_response", "session_id"),
            ("ambient_event_response", "state"),
            ("ambient_event_response", "result"),
            ("ambient_event_response", "result", "event_instance_id"),
            ("ambient_event_response", "result", "action_id"),
            ("ambient_event_response", "result", "status"),
        )
        for path in paths:
            with self.subTest(missing=path):
                def remove(response):
                    parent = response
                    for field in path[:-1]:
                        parent = parent[field]
                    del parent[path[-1]]
                await self.check_reopened_receipt(remove)

    async def test_wrongly_typed_saved_event_replies_fail_safely_after_resume(self):
        cases = (
            (("ambient_event_response",), None),
            (("ambient_event_response",), []),
            (("ambient_event_response",), "broken"),
            (("ambient_event_response", "session_id"), 17),
            (("ambient_event_response", "state"), []),
            (("ambient_event_response", "result"), None),
            (("ambient_event_response", "result"), []),
            (("ambient_event_response", "result"), "broken"),
            (("ambient_event_response", "result", "event_instance_id"), 17),
            (("ambient_event_response", "result", "action_id"), []),
            (("ambient_event_response", "result", "status"), "INVALID"),
            (("ambient_event_response", "result", "transition_id"), {}),
            (("ambient_event_response", "result", "canonical_event_id"), []),
            (("ambient_event_response", "result", "reason_code"), 17),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                def replace(response):
                    parent = response
                    for field in path[:-1]:
                        parent = parent[field]
                    parent[path[-1]] = value
                await self.check_reopened_receipt(replace)

    async def test_valid_saved_event_reply_retains_already_applied_projection(self):
        await self.check_reopened_receipt()

    async def test_imported_legacy_reservation_replays_without_full_response(self):
        await self.check_reopened_receipt(legacy="imported")

    async def test_empty_legacy_projection_does_not_require_modern_response_fields(self):
        await self.check_reopened_receipt(legacy="empty")
