"""Direct unit tests for incidents.arbiter: emergence only takes a call slot nobody else needs."""

import unittest
from unittest import mock

from api import ollama_adapter
from incidents import arbiter


class ArbiterDecideTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ollama_adapter, "MAX_MODEL_CALLS_PER_TURN", 2)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ceiling_reads_the_adapter_cap(self):
        self.assertEqual(arbiter.ceiling(), 2)
        with mock.patch.object(ollama_adapter, "MAX_MODEL_CALLS_PER_TURN", 5):
            self.assertEqual(arbiter.ceiling(), 5)

    def test_free_slot_after_reservations_proposes(self):
        self.assertEqual(arbiter.decide(calls_used=0, narration_needed=True), arbiter.PROPOSE)
        self.assertEqual(arbiter.decide(calls_used=0, narration_needed=False, intent_pending=True), arbiter.PROPOSE)
        self.assertEqual(arbiter.decide(calls_used=1, narration_needed=False), arbiter.PROPOSE)

    def test_narration_and_intent_keep_their_slots(self):
        self.assertEqual(arbiter.decide(calls_used=0, narration_needed=True, intent_pending=True), arbiter.DEFER)
        self.assertEqual(arbiter.decide(calls_used=1, narration_needed=True), arbiter.DEFER)
        self.assertEqual(arbiter.decide(calls_used=2, narration_needed=False), arbiter.DEFER)

    def test_incident_action_never_proposes(self):
        self.assertEqual(
            arbiter.decide(calls_used=0, narration_needed=False, incident_action=True), arbiter.DEFER
        )

    def test_bad_call_counts_defer(self):
        for bad in (-1, None, "0", 1.0, True):
            with self.subTest(calls_used=bad):
                self.assertEqual(arbiter.decide(calls_used=bad, narration_needed=False), arbiter.DEFER)


class ArbiterCallsUsedTests(unittest.TestCase):
    def test_no_counter_means_none(self):
        token = ollama_adapter._MODEL_CALLS.set(None)
        self.addCleanup(ollama_adapter._MODEL_CALLS.reset, token)
        self.assertIsNone(arbiter.calls_used())

    def test_counts_calls_recorded_this_turn(self):
        token = ollama_adapter._MODEL_CALLS.set(["intent", "narration"])
        self.addCleanup(ollama_adapter._MODEL_CALLS.reset, token)
        self.assertEqual(arbiter.calls_used(), 2)


if __name__ == "__main__":
    unittest.main()
