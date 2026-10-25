"""Surface mutations use the existing turn receipt. They do not get a second journal.

A mark committed under an action id replays without a second mark. A different
body conflicts. A failed save restores the candidate. A stale save checks the
receipt after rollback and does not run the turn again.
"""
import asyncio
import copy
import json
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import equipment_economy
import grounded_action
import scheduled_events
from api.persistence.campaign_models import CampaignStaleError, CampaignStorageError
from api.tests import test_campaign_api as fixtures
from api.tests.test_incident_gate_a import CAMPAIGN, _envelope, _world
from incidents import attempts


class SceneTransactionContractTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def prepared(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        self.assertTrue(session.commit_location_change("tavern", session=session))
        world = session.world_state
        table = session.create_local_feature({
            "name": "Kil masa", "location": "tavern", "kind": "table",
            "description": "Sağlam bir masa."}, session=session)
        self.assertIsNotNone(table, world.get("location"))
        self.manager.save_campaign(created["campaign_id"])
        return created, table

    def marks(self, session_id, feature_id):
        world = self.manager.get(session_id).game_session.world_state
        return list(world.get("feature_marks", {}).get(feature_id, []))

    async def post(self, created, message, action_id):
        return await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": message, "interaction_mode": "do", "action_id": action_id},
        )

    async def test_committed_response_loss_replays_without_second_effect(self):
        created, table = await self.prepared()
        action_id = str(uuid4())
        message = f'/item mark {table["id"]} "eski iz"'
        first = await self.post(created, message, action_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual([mark["text"] for mark in self.marks(created["session_id"], table["id"])], ["eski iz"])
        session = self.manager.get(created["session_id"]).game_session
        with patch.object(session, "run_player_turn", side_effect=AssertionError("replay ran the turn")):
            replay = await self.post(created, message, action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["narration"], first.json()["narration"])
        self.assertEqual(replay.json()["action_id"], action_id)
        self.assertEqual(len(self.marks(created["session_id"], table["id"])), 1)

    async def test_same_action_id_different_body_conflicts(self):
        created, table = await self.prepared()
        action_id = str(uuid4())
        first = await self.post(created, f'/item mark {table["id"]} "eski iz"', action_id)
        self.assertEqual(first.status_code, 200, first.text)
        conflict = await self.post(created, f'/item mark {table["id"]} "baska iz"', action_id)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
        self.assertEqual([mark["text"] for mark in self.marks(created["session_id"], table["id"])], ["eski iz"])

    async def test_unhandled_precommit_failure_restores_candidate(self):
        created, table = await self.prepared()
        action_id = str(uuid4())
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("disk")):
            failed = await self.post(created, f'/item mark {table["id"]} "eski iz"', action_id)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "campaign_storage_unavailable")
        self.assertEqual(self.marks(created["session_id"], table["id"]), [])
        saved = self.store.get_campaign(created["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertNotIn(table["id"], saved.get("feature_marks", {}))
        again = await self.post(created, f'/item mark {table["id"]} "eski iz"', str(uuid4()))
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(len(self.marks(created["session_id"], table["id"])), 1)

    async def test_uncertain_commit_checks_receipt_before_reexecution(self):
        created, table = await self.prepared()
        action_id = str(uuid4())
        session = self.manager.get(created["session_id"]).game_session
        lookups = {"count": 0}

        def lookup(record, requested):
            lookups["count"] += 1
            if lookups["count"] == 1:
                return None
            return {"request_hash": "0" * 64, "response": {"action_id": requested}}

        with (
            patch.object(session, "run_player_turn", wraps=session.run_player_turn) as turn,
            patch.object(self.store, "save_campaign", side_effect=CampaignStaleError("stale")),
            patch.object(self.manager, "get_turn_action", side_effect=lookup),
        ):
            failed = await self.post(created, f'/item mark {table["id"]} "eski iz"', action_id)
        self.assertEqual(failed.status_code, 409, failed.text)
        self.assertEqual(failed.json()["detail"]["code"], "action_id_conflict")
        self.assertEqual(turn.call_count, 1)
        self.assertGreaterEqual(lookups["count"], 2)
        self.assertEqual(self.marks(created["session_id"], table["id"]), [])

    async def test_resume_does_not_repeat_the_mark(self):
        created, table = await self.prepared()
        action_id = str(uuid4())
        message = f'/item mark {table["id"]} "eski iz"'
        first = await self.post(created, message, action_id)
        self.assertEqual(first.status_code, 200, first.text)
        resumed = await self.http.post(f"/api/game/campaigns/{created['campaign_id']}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        resumed_id = resumed.json()["session_id"]
        world = self.manager.get(resumed_id).game_session.world_state
        self.assertEqual([mark["text"] for mark in world.get("feature_marks", {}).get(table["id"], [])], ["eski iz"])
        replay = await self.http.post(
            f"/api/game/sessions/{resumed_id}/turn",
            json={"message": message, "interaction_mode": "do", "action_id": action_id},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["narration"], first.json()["narration"])
        world = self.manager.get(resumed_id).game_session.world_state
        self.assertEqual(len(world.get("feature_marks", {}).get(table["id"], [])), 1)

    async def test_late_campaign_result_cannot_write_other_campaign(self):
        first, table = await self.prepared()
        second = await self.create_campaign()
        action_id = str(uuid4())
        response = await self.post(first, f'/item mark {table["id"]} "eski iz"', action_id)
        self.assertEqual(response.status_code, 200, response.text)
        other = self.manager.get(second["session_id"]).game_session.world_state
        self.assertNotIn(table["id"], other.get("feature_marks", {}))
        saved = self.store.get_campaign(second["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertNotIn(table["id"], saved.get("feature_marks", {}))

    async def test_concurrent_same_action_id_commits_once(self):
        created, table = await self.prepared()
        action_id = str(uuid4())
        message = f'/item mark {table["id"]} "eski iz"'
        body = {"message": message, "interaction_mode": "do", "action_id": action_id}
        barrier = threading.Barrier(2)
        original = self.manager.get

        def rendezvous(session_id):
            record = original(session_id)
            barrier.wait(timeout=10)
            return record

        with patch.object(self.manager, "get", side_effect=rendezvous):
            left, right = await asyncio.wait_for(asyncio.gather(
                self.http.post(f"/api/game/sessions/{created['session_id']}/turn", json=body),
                self.http.post(f"/api/game/sessions/{created['session_id']}/turn", json=body),
            ), timeout=20)
        self.assertIn(left.status_code, {200, 409, 503}, left.text)
        self.assertIn(right.status_code, {200, 409, 503}, right.text)
        follow = await self.post(created, message, action_id)
        self.assertEqual(follow.status_code, 200, follow.text)
        self.assertEqual(len(self.marks(created["session_id"], table["id"])), 1)

    async def test_turn_snapshot_restores_mark_and_table_absence(self):
        created, table = await self.prepared()
        session = self.manager.get(created["session_id"]).game_session
        before = session._capture_runtime_snapshot()
        marked = equipment_economy.execute(session, f'/item mark {table["id"]} "eski iz"')
        self.assertTrue(marked["action_result"]["success"], marked["narration"])
        event = scheduled_events.arm_table_absence(session.world_state, session.world_state["location"])
        self.assertIsNotNone(event)
        session._restore_runtime_snapshot(before)
        restored = session.world_state
        self.assertNotIn(table["id"], restored.get("feature_marks", {}))
        self.assertFalse(any(
            item.get("event_id") == event["event_id"]
            for item in restored.get("scheduled_events", [])
        ))

    async def test_grounded_local_failure_defers_without_duplicate_effect(self):
        created, table = await self.prepared()
        session = self.manager.get(created["session_id"]).game_session
        before_marks = copy.deepcopy(session.world_state.get("feature_marks"))
        before_messages = list(session.messages)

        def explode(*_args):
            session.world_state["feature_marks"] = {
                "ghost": [{"mark_id": "mark_001", "text": "yarim", "turn": 0}],
            }
            session.messages.append({"role": "assistant", "content": "yarim"})
            raise RuntimeError("grounded bug")

        with (
            patch("grounded_action._decide", return_value=("act", (None, None, None))),
            patch("grounded_action._execute", side_effect=explode),
        ):
            deferred = grounded_action.resolve_turn(
                session, "masaya oturuyorum", interaction_mode="do")
        self.assertIsNone(deferred)
        self.assertEqual(session.world_state.get("feature_marks"), before_marks)
        self.assertEqual(session.messages, before_messages)
        action_id = str(uuid4())
        message = f'/item mark {table["id"]} "eski iz"'
        marked = await self.post(created, message, action_id)
        self.assertEqual(marked.status_code, 200, marked.text)
        replay = await self.post(created, message, action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(
            [mark["text"] for mark in self.marks(created["session_id"], table["id"])],
            ["eski iz"],
        )

    async def test_resolved_narrator_failure_keeps_safe_fallback(self):
        created, table = await self.prepared()
        action_id = str(uuid4())
        message = "Mor bir kılıç düşünüyorum."
        calls = []

        def chat(*_args, **kwargs):
            schema = kwargs.get("format") or {}
            properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
            calls.append("intent" if "intent" in properties else "narration")
            if "intent" in properties:
                return {"message": {"content": json.dumps({
                    "intent": "narrative", "action": "narrative",
                    "target": {"type": "none", "reference": ""},
                    "completion": "completed", "confidence": 1.0,
                }, ensure_ascii=False)}}
            raise TimeoutError("narrator down")

        client = self.app.state.ollama_adapter._client
        with patch.object(client, "chat", side_effect=chat):
            first = await self.post(created, message, action_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn("narration", calls)
        narration = first.json()["narration"]
        self.assertTrue(narration.strip())
        self.assertNotIn("narrator down", narration)
        self.assertEqual(self.marks(created["session_id"], table["id"]), [])
        with patch.object(client, "chat", side_effect=AssertionError("replay called the model")):
            replay = await self.post(created, message, action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["narration"], narration)

    def test_operational_attempt_record_not_misreported_as_rolled_back(self):
        _session, world = _world()
        before = copy.deepcopy(world)
        envelope = _envelope(world)
        store = attempts.MemoryAttemptStore()

        def propose(_packet):
            raise TimeoutError("provider")

        outcome = attempts.run(
            store, campaign_id=CAMPAIGN, envelope=envelope, world=world,
            propose=propose, model_id="qwen3:8b",
        )
        self.assertEqual(outcome.status, "no_proposal")
        self.assertNotEqual(outcome.status, "rolled_back")
        self.assertEqual(world, before)
        stored = store.get(CAMPAIGN, envelope["trigger_id"])
        self.assertEqual(stored["status"], "no_proposal")
        second = attempts.run(
            store, campaign_id=CAMPAIGN, envelope=envelope, world=world,
            propose=lambda _packet: self.fail("a failed attempt was generated again"),
            model_id="qwen3:8b",
        )
        self.assertEqual((second.status, second.model_calls), ("consumed", 0))
        self.assertEqual(world, before)
