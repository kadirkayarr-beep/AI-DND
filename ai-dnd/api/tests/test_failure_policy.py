"""Direct unit tests for api.failure_policy: the phase an action reached decides how the API answers a failure."""

import unittest

from api.failure_policy import (
    QUARANTINE_MESSAGE,
    ActionPhase,
    RecoveryDecision,
    classify_failure,
)
from api.persistence.campaign_models import CampaignStaleError, CampaignStorageError


class OllamaUnavailableError(Exception):
    pass


class RequiredModelUnavailableError(Exception):
    pass


class ClassifyFailureTests(unittest.TestCase):
    def test_unnamed_phase_is_outcome_unknown_never_a_guessed_success(self):
        for phase in (None, "unresolved", 3):
            with self.subTest(phase=phase):
                decision = classify_failure(phase, "ok", RuntimeError())
                self.assertEqual((decision.code, decision.status_code, decision.outcome), ("outcome_unknown", 500, "outcome_unknown"))

    def test_unresolved_means_nothing_happened(self):
        decision = classify_failure(ActionPhase.UNRESOLVED, "ok", RuntimeError("boom"))
        self.assertEqual((decision.code, decision.status_code, decision.outcome), ("engine_error", 500, "not_applied"))
        self.assertIs(decision.not_applied, True)

    def test_model_down_is_a_503_and_still_not_applied(self):
        for error in (OllamaUnavailableError(), RequiredModelUnavailableError()):
            with self.subTest(error=type(error).__name__):
                decision = classify_failure(ActionPhase.UNRESOLVED, "ok", error)
                self.assertEqual((decision.code, decision.status_code), ("ollama_unavailable", 503))
                self.assertIs(decision.not_applied, True)

    def test_npc_speech_failure_saves_nothing(self):
        decision = classify_failure(ActionPhase.NPC_SPEECH, "ok", RuntimeError())
        self.assertEqual((decision.code, decision.status_code, decision.outcome), ("invalid_dialogue_response", 503, "not_applied"))
        self.assertIs(decision.not_applied, True)

    def test_resolved_uncommitted_is_rolled_back_by_cause(self):
        phase = ActionPhase.RESOLVED_UNCOMMITTED
        quarantined = classify_failure(phase, "quarantined", RuntimeError())
        self.assertEqual((quarantined.code, quarantined.status_code, quarantined.message), ("session_restore_failed", 409, QUARANTINE_MESSAGE))
        self.assertFalse(quarantined.retry_safe)
        self.assertFalse(quarantined.same_id_required)
        stale = classify_failure(phase, "ok", CampaignStaleError("stale"))
        self.assertEqual((stale.code, stale.status_code, stale.message), ("campaign_stale", 409, "stale"))
        storage = classify_failure(phase, "ok", CampaignStorageError("disk"))
        self.assertEqual((storage.code, storage.status_code), ("campaign_storage_unavailable", 503))
        other = classify_failure(phase, "ok", RuntimeError())
        self.assertEqual((other.code, other.status_code, other.outcome), ("persistence_error", 500, "rolled_back"))
        self.assertIsNot(other.not_applied, True)

    def test_lost_acknowledgement_is_unknown_until_the_receipt_is_read(self):
        decision = classify_failure(ActionPhase.COMMIT_UNKNOWN, "ok", RuntimeError())
        self.assertEqual((decision.code, decision.status_code, decision.outcome), ("persistence_error", 503, "outcome_unknown"))
        self.assertTrue(decision.reconcile_receipt_first)
        self.assertTrue(decision.retry_safe)
        self.assertTrue(decision.same_id_required)

    def test_committed_result_is_kept_and_never_recomputed(self):
        decision = classify_failure(ActionPhase.COMMITTED_NARRATION, "ok", RuntimeError())
        self.assertEqual((decision.code, decision.status_code, decision.outcome), ("narration_fallback", 200, "committed"))
        self.assertTrue(decision.keep_committed_result)
        self.assertTrue(decision.narration_fallback)
        self.assertTrue(decision.emit_event)
        self.assertFalse(decision.rerun_mechanics)
        self.assertFalse(decision.retry_safe)

    def test_reconciliation_failure_keeps_the_receipt_as_authority(self):
        decision = classify_failure(ActionPhase.RECONCILIATION, "ok", RuntimeError())
        self.assertEqual((decision.code, decision.status_code, decision.outcome), ("reconciliation_failed", 503, "outcome_unknown"))
        self.assertTrue(decision.reconcile_receipt_first)


class DetailTests(unittest.TestCase):
    def _decision(self, **over):
        fields = dict(code="c", status_code=500, outcome="not_applied", message="m")
        fields.update(over)
        return RecoveryDecision(**fields)

    def test_detail_has_code_and_message_plus_extras(self):
        self.assertEqual(self._decision().detail(), {"code": "c", "message": "m"})
        self.assertEqual(self._decision().detail(action_id="a1")["action_id"], "a1")

    def test_not_applied_is_shown_only_when_certain(self):
        self.assertTrue(self._decision(not_applied=True).detail()["not_applied"])
        self.assertNotIn("not_applied", self._decision(not_applied=False).detail())
        self.assertNotIn("not_applied", self._decision(not_applied=None).detail())

    def test_decision_is_frozen(self):
        with self.assertRaises(Exception):
            self._decision().code = "other"


if __name__ == "__main__":
    unittest.main()
