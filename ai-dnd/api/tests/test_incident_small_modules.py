"""Direct tests for the small pure branches of incidents.arbiter, incidents.faction and adventure.deadlines."""

import unittest
from unittest.mock import patch

from adventure import deadlines
from incidents import arbiter, faction


class ArbiterDecideTests(unittest.TestCase):
    def test_propose_only_when_a_slot_stays_free_after_reserving(self):
        with patch.object(arbiter, "ceiling", return_value=4):
            self.assertEqual(arbiter.decide(calls_used=0, narration_needed=True), arbiter.PROPOSE)
            self.assertEqual(arbiter.decide(calls_used=2, narration_needed=True, intent_pending=True), arbiter.DEFER)
            self.assertEqual(arbiter.decide(calls_used=1, narration_needed=True, intent_pending=True), arbiter.PROPOSE)

    def test_bad_counter_or_incident_action_defers(self):
        with patch.object(arbiter, "ceiling", return_value=4):
            self.assertEqual(arbiter.decide(calls_used=-1, narration_needed=False), arbiter.DEFER)
            self.assertEqual(arbiter.decide(calls_used=True, narration_needed=False), arbiter.DEFER)
            self.assertEqual(arbiter.decide(calls_used=0, narration_needed=False, incident_action=True), arbiter.DEFER)


class FactionTests(unittest.TestCase):
    def test_rank_allowed_compares_by_order_and_rejects_unknown(self):
        self.assertTrue(faction.rank_allowed("member", "officer"))
        self.assertTrue(faction.rank_allowed("officer", "officer"))
        self.assertFalse(faction.rank_allowed("leader", "officer"))
        self.assertFalse(faction.rank_allowed("nobody", "officer"))
        self.assertFalse(faction.rank_allowed("member", "nobody"))

    def test_apply_returns_state_unchanged_when_refused(self):
        self.assertIsNone(faction.apply(None, faction_id="f", rank="member", source_action_id="a", turn_index=1, evidence=()))
        marker = object()
        self.assertIs(faction.apply(marker, faction_id="f", rank="leader", source_action_id="a", turn_index=1, evidence=()), marker)
        self.assertIs(faction.apply(marker, faction_id="f", rank="member", source_action_id="a", turn_index=1, evidence=()), marker)


class DeadlineTests(unittest.TestCase):
    def test_arm_ignores_hidden_or_unplaced_quests(self):
        world = {"location": "x", "locations": {}}
        self.assertIsNone(deadlines.arm(world, {"status": "HIDDEN", "quest_id": "q"}))
        self.assertIsNone(deadlines.arm(world, {"status": "ACTIVE", "quest_id": "q"}))

    def test_arm_keeps_an_existing_deadline(self):
        quest = {"status": "ACTIVE", "quest_id": "q", "deadline": "e1"}
        self.assertEqual(deadlines.arm({}, quest), "e1")

    def test_close_missed_needs_a_missed_event(self):
        world = {"scheduled_events": [{"event_id": "e1", "encounter_status": "PENDING"}]}
        quest = {"status": "ACTIVE", "deadline": "e1", "updated_turn": 1}
        self.assertFalse(deadlines.close_missed(world, quest))
        self.assertFalse(deadlines.close_missed(world, {"status": "FAILED"}))
        self.assertFalse(deadlines.close_missed(world, {"status": "ACTIVE", "updated_turn": 1}))


if __name__ == "__main__":
    unittest.main()
