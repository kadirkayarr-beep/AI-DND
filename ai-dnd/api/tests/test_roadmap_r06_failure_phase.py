"""R06: a failure is answered by the PHASE the action had reached, never by guesswork.

Unit tests pin the decision table of api.failure_policy. Integration tests drive the real FastAPI app with a temporary
SQLite store and check that the production handlers answer through that table: a failure before anything resolved
creates no event; a durably committed result is never re-run or lost; speech that was not spoken is not saved; and
stale, storage and quarantine failures are distinguishable and carry a safe retry rule.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

import httpx

from api import failure_policy
from api.auth import FixedAuthenticator
from api.failure_policy import ActionPhase, classify_failure
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStaleError, CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient
from dialogue_runtime import DialogueProviderError


class ClassifyFailureTests(unittest.TestCase):
    def test_unresolved_failure_makes_no_event_and_is_safe_to_retry(self):
        decision = classify_failure(ActionPhase.UNRESOLVED, "none", RuntimeError("engine"))
        self.assertFalse(decision.emit_event)
        self.assertEqual(decision.outcome, "not_applied")
        self.assertTrue(decision.retry_safe)

    def test_commit_unknown_reconciles_the_receipt_before_anything_else(self):
        decision = classify_failure(ActionPhase.COMMIT_UNKNOWN, "unknown", CampaignStorageError("ack lost"))
        self.assertTrue(decision.reconcile_receipt_first)
        self.assertEqual(decision.outcome, "outcome_unknown")
        self.assertNotEqual(decision.outcome, "not_applied", "an uncertain commit never claims 'not applied'")
        self.assertTrue(decision.retry_safe and decision.same_id_required)

    def test_a_committed_result_survives_a_presentation_failure_with_the_same_evidence(self):
        decision = classify_failure(ActionPhase.COMMITTED_NARRATION, "committed", RuntimeError("narrator"))
        self.assertTrue(decision.keep_committed_result)
        self.assertTrue(decision.narration_fallback)
        self.assertFalse(decision.rerun_mechanics, "dice, source and time of the committed result are never recomputed")
        self.assertEqual(decision.outcome, "committed")

    def test_npc_speech_that_was_not_spoken_is_never_saved(self):
        decision = classify_failure(ActionPhase.NPC_SPEECH, "none", DialogueProviderError("down"))
        self.assertFalse(decision.persist_speech)
        self.assertFalse(decision.emit_event)

    def test_stale_storage_and_quarantine_are_three_different_answers(self):
        stale = classify_failure(ActionPhase.RESOLVED_UNCOMMITTED, "rolled_back", CampaignStaleError("stale"))
        storage = classify_failure(ActionPhase.RESOLVED_UNCOMMITTED, "rolled_back", CampaignStorageError("disk"))
        closed = classify_failure(ActionPhase.RESOLVED_UNCOMMITTED, "quarantined", RuntimeError("restore failed"))
        self.assertEqual(len({stale.code, storage.code, closed.code}), 3)
        self.assertTrue(stale.retry_safe and storage.retry_safe)
        self.assertFalse(closed.retry_safe, "a quarantined session is not retried until durable truth is resumed")
        for decision in (stale, storage):
            self.assertIsNone(decision.not_applied, "a rollback without a durable refusal makes no never-applied claim")

    def test_an_unknown_phase_is_outcome_unknown_never_a_guessed_success(self):
        for phase in ("mystery", None, 7):
            with self.subTest(phase=phase):
                decision = classify_failure(phase, "none", RuntimeError("?"))
                self.assertEqual(decision.outcome, "outcome_unknown")
                self.assertFalse(decision.emit_event)
                self.assertFalse(decision.keep_committed_result)
                self.assertNotEqual(decision.status_code, 200)

    def test_every_phase_has_a_decision(self):
        for phase in ActionPhase:
            self.assertIsNotNone(classify_failure(phase, "none", RuntimeError("x")))


class FailurePhaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
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
        self.calls = 0
        self.mode = "ok"

        def turn(_message, **_kwargs):
            self.calls += 1
            if self.mode == "unresolved":
                raise RuntimeError("engine failed before resolving")
            if self.mode == "speech":
                raise DialogueProviderError("dialogue provider down")
            self.session.character["current_hp"] = self.session.character["current_hp"] - 1
            return {"narration": "Kapıdan hafif bir ses geliyor.",
                    "action_result": {"action": "world_interaction", "status": "resolved", "success": True, "state_changes": []}}

        self.session.run_player_turn = turn

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    def post(self, action_id=None):
        return self.http.post(f"/api/game/sessions/{self.sid}/turn",
                              json={"message": "Kapıyı dinliyorum.", "action_id": action_id or str(uuid.uuid4())})

    def durable(self):
        campaign = self.store.get_campaign(self.cid)
        return {"revision": campaign.metadata["revision"], "history": len(campaign.history), "payload": campaign.payload}

    async def test_failure_phase_preserves_committed_result(self):
        before = self.durable()
        hp = self.session.character["current_hp"]

        # UNRESOLVED: no event, no receipt, no history; the answer is a certain "not applied".
        self.mode = "unresolved"
        unresolved = await self.post()
        self.assertEqual(unresolved.status_code, 500, unresolved.text)
        self.assertIs(unresolved.json()["detail"]["not_applied"], True)
        self.assertEqual(self.durable(), before)
        self.assertEqual(self.session.character["current_hp"], hp)

        # NPC_SPEECH: speech that could not be produced is not persisted and nothing else moves.
        self.mode = "speech"
        action_id = str(uuid.uuid4())  # the id stays unresolved after an uncertain failure; the same id is the way forward
        spoken = await self.post(action_id)
        self.assertGreaterEqual(spoken.status_code, 500, spoken.text)
        self.assertEqual(self.durable(), before)

        # RESOLVED_UNCOMMITTED (storage): rolled back, a retry with the SAME id commits exactly once, no never-applied claim.
        self.mode = "ok"
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("disk full")):
            storage = await self.post(action_id)
        self.assertEqual(storage.status_code, 503, storage.text)
        self.assertNotIn("not_applied", storage.json()["detail"])
        self.assertEqual(self.durable(), before)
        self.assertEqual(self.session.character["current_hp"], hp)

        # The retry with the same id commits once; the committed result is then never re-run.
        committed = await self.post(action_id)
        self.assertEqual(committed.status_code, 200, committed.text)
        calls_after_commit = self.calls
        replay = await self.post(action_id)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), committed.json(), "same dice, same source, same time")
        self.assertEqual(self.calls, calls_after_commit, "a committed result is replayed, never re-resolved")
        self.assertEqual(self.durable()["revision"], before["revision"] + 1)

    async def test_stale_storage_and_quarantine_answer_with_distinct_codes(self):
        codes = {}
        with patch.object(self.store, "save_campaign", side_effect=CampaignStaleError("another save won")):
            codes["stale"] = (await self.post()).json()["detail"]["code"]
        with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("disk full")):
            codes["storage"] = (await self.post()).json()["detail"]["code"]
        self.record.usable = False
        codes["quarantine"] = (await self.post()).json()["detail"]["code"]
        self.assertEqual(len(set(codes.values())), 3, codes)

    async def test_the_production_handlers_answer_through_the_failure_policy(self):
        # Real caller integration: the decision table is consumed, not just defined.
        with patch.object(failure_policy, "classify_failure", wraps=failure_policy.classify_failure) as spy:
            with patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("disk full")):
                response = await self.post()
        self.assertEqual(response.status_code, 503)
        self.assertTrue(spy.called, "the persistence failure must be classified by failure_policy.classify_failure")
        phase = spy.call_args.args[0]
        self.assertIs(phase, ActionPhase.RESOLVED_UNCOMMITTED)


    async def test_a_failed_reconciliation_is_outcome_unknown_and_closes_the_session_instead_of_guessing(self):
        before = self.durable()
        saved = {"failed": False}
        real_lookup = self.manager.get_turn_action

        def failing_save(*_args, **_kwargs):
            saved["failed"] = True
            raise CampaignStorageError("disk full")

        def lookup(*args, **kwargs):
            if saved["failed"]:  # only the reconciliation read after the failed save is down; the entry checks work
                raise CampaignStorageError("receipt unreadable")
            return real_lookup(*args, **kwargs)

        with patch.object(self.store, "save_campaign", side_effect=failing_save),                 patch.object(self.manager, "get_turn_action", side_effect=lookup):
            response = await self.post()
        self.assertEqual(response.status_code, 503, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "reconciliation_failed")
        self.assertEqual(detail["commit_status"], "outcome_unknown")
        self.assertNotIn("not_applied", detail)
        self.assertFalse(self.record.usable, "unknown outcome: the runtime is closed, not rolled back or trusted")
        self.assertEqual(self.durable(), before)


if __name__ == "__main__":
    unittest.main()
