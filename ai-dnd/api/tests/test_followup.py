"""Direct unit tests for adventure.followup: one follow-up per closed adventure, one faction gate."""

import unittest
from unittest import mock

from adventure import followup

BINDINGS = {"source_npc_id": "npc.source"}


def _call(world, quest, **over):
    kwargs = dict(bindings=BINDINGS, rumor="r", evidence_id="e1", campaign_id="camp")
    kwargs.update(over)
    return followup.maybe_follow_up(world, quest, **kwargs)


class MaybeFollowUpTests(unittest.TestCase):
    def test_closed_adventure_gets_one_follow_up_and_remembers_it(self):
        quest = {"quest_id": "q1", "status": "COMPLETED"}
        with mock.patch.object(followup, "refresh", return_value={"opportunity_key": "opp:1"}) as refresh:
            created = _call({"quests": []}, quest)
        self.assertEqual(created, {"opportunity_key": "opp:1"})
        self.assertEqual(quest["follow_up_key"], "opp:1")
        kwargs = refresh.call_args.kwargs
        self.assertEqual(kwargs["reason"], "adventure_completed")
        self.assertEqual(kwargs["trigger"], "follow:q1")
        self.assertEqual(kwargs["source_id"], "npc.source")

    def test_failed_adventure_gives_the_failed_reason(self):
        with mock.patch.object(followup, "refresh", return_value={"opportunity_key": "k"}) as refresh:
            _call({"quests": []}, {"quest_id": "q1", "status": "FAILED"})
        self.assertEqual(refresh.call_args.kwargs["reason"], "adventure_failed")

    def test_no_second_follow_up_open_adventure_or_busy_board(self):
        with mock.patch.object(followup, "refresh") as refresh:
            self.assertIsNone(_call({"quests": []}, {"quest_id": "q", "status": "COMPLETED", "follow_up_key": "k"}))
            self.assertIsNone(_call({"quests": []}, {"quest_id": "q", "status": "ACTIVE"}))
            with mock.patch.object(followup, "active_count", return_value=2):
                self.assertIsNone(_call({"quests": []}, {"quest_id": "q", "status": "COMPLETED"}))
            refresh.assert_not_called()

    def test_refused_refresh_leaves_the_quest_unmarked(self):
        quest = {"quest_id": "q1", "status": "COMPLETED"}
        with mock.patch.object(followup, "refresh", return_value=None):
            self.assertIsNone(_call({"quests": []}, quest))
        self.assertNotIn("follow_up_key", quest)


class FactionGateTests(unittest.TestCase):
    def _gate(self, standing, threshold=2):
        return followup.faction_gate(
            {}, standing, threshold=threshold, bindings=BINDINGS, rumor="r", evidence_id="e", campaign_id="c"
        )

    def test_standing_below_threshold_or_not_an_int_opens_nothing(self):
        with mock.patch.object(followup, "refresh") as refresh:
            self.assertIsNone(self._gate(1))
            self.assertIsNone(self._gate("3"))
            self.assertIsNone(self._gate(True, threshold=2))
            refresh.assert_not_called()

    def test_standing_at_threshold_opens_a_faction_gate(self):
        with mock.patch.object(followup, "refresh", return_value="ROW") as refresh:
            self.assertEqual(self._gate(2), "ROW")
        self.assertEqual(refresh.call_args.kwargs["trigger"], "faction-gate")
        self.assertEqual(refresh.call_args.kwargs["reason"], "aftermath")


if __name__ == "__main__":
    unittest.main()
