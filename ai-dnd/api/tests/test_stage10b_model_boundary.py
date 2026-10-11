"""Fault-injected boundary evidence; never claimed as live Qwen."""
import copy
import io
import uuid
from unittest.mock import patch

import game
from api.model_phase import ModelFailure, only_resolved_narration_failures, resolved_narration_scope
from api.persistence.campaign_models import CampaignStorageError
from api.tests.test_explicit_shop_creation import ShopTransactionTests, REQUEST


class ModelBoundaryTests(ShopTransactionTests):
    async def test_resolved_transport_failure_persists_and_replays_without_retry(self):
        self.model.chat.side_effect = RuntimeError("private-sentinel")
        await self.test_creation_replay_duplicate_resume_and_session_isolation()
        receipt = self.store.get_campaign(self.created["campaign_id"])
        self.assertEqual(len(receipt.payload["engine_save"]["world_state"]["shops"]), 1)

    async def test_resolved_transport_failure_survives_windows_legacy_console(self):
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1254", errors="strict")
        with patch("sys.stdout", console):
            await self.test_resolved_transport_failure_persists_and_replays_without_retry()
        console.close()

    async def test_before_resolution_failure_restores_state_rng_and_has_no_receipt(self):
        self.model.chat.side_effect = RuntimeError("private-sentinel")
        session = self.record.game_session
        before = copy.deepcopy(session.serialize_game_state())
        rng = session.rng.getstate()
        body = {"message": "Mor bir düşünceyi yüksek sesle kuruyorum.", "action_id": str(uuid.uuid4())}
        reply = await self.http.post(self.url, json=body)
        self.assertEqual(reply.status_code, 503, reply.text)
        self.assertNotIn("private-sentinel", reply.text)
        self.assertEqual(session.serialize_game_state(), before)
        self.assertEqual(session.rng.getstate(), rng)
        self.assertIsNone(self.store.get_turn_action(self.created["campaign_id"], body["action_id"]))
        self.assertLessEqual(self.model.chat.call_count, 2)

    async def test_resolved_transport_failure_still_rolls_back_if_save_fails(self):
        self.model.chat.side_effect = RuntimeError("private-sentinel")
        await self.test_failed_autosave_restores_complete_state_and_has_no_receipt()

    async def test_malformed_shop_narration_reports_the_resolved_scene(self):
        self.model.chat.return_value = {"message": {"content": "not JSON"}}
        body = {"message": REQUEST, "action_id": str(uuid.uuid4())}
        reply = await self.http.post(self.url, json=body)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(reply.json()["narration"], "Burada küçük bir yerel dükkân var; başında bir dükkâncı duruyor.")
        self.assertEqual(len(self.record.game_session.world_state["shops"]), 1)
        self.assertEqual(self.model.chat.call_count, 1)

    def test_unknown_and_mixed_phases_fail_closed_and_scope_resets(self):
        unknown = ModelFailure("RuntimeError")
        with resolved_narration_scope(True):
            resolved = ModelFailure("RuntimeError")
        self.assertTrue(only_resolved_narration_failures([resolved]))
        for failures in ([unknown], [resolved, unknown], ["RuntimeError"], []):
            self.assertFalse(only_resolved_narration_failures(failures))
        self.assertEqual(ModelFailure("RuntimeError").phase, "unresolved")
