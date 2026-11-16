"""D-060 (Kadir kararı 2026-11-15): a catalog quest's XP goes through the same forfeit boundary as every other award.
A refused award (full receipt list, level-5 crossing the save admission refuses) must not reject the turn: the quest
still completes, the XP is put back, one "kaydedilemedi" line is left, and the same quest never pays twice.
"""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import game
import quest_catalog
import xp
from api.tests import test_dilim4b_job_xp as jobs
from api.tests.test_d061_unrecorded_xp_line import _refuses_level_five
from api.tests.test_dilim4b_combat_xp import fighter

QUEST = {
    "quest_id": "quest.xp",
    "title": "Road",
    "description": "Walk to the forest.",
    "objectives": [{"objective_id": "visit", "description": "Visit the forest",
                    "type": "visit_location", "target": "forest"}],
    "xp": 300,
}


def _finish(session):
    session.accept_quest("quest.xp")
    before = copy.deepcopy(session.world_state)
    session.world_state["location"] = "forest"
    return session.evaluate_quest_events(before, {"action": "travel"})


class QuestXpBoundary(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(quest_catalog, "CATALOG", (QUEST,))
        patcher.start()
        self.addCleanup(patcher.stop)

    def session(self, seed):
        session = game.create_session(seed=seed)
        fighter(session)
        session.world_state["locations"].setdefault("forest", {"name": "forest"})
        return session

    def test_a_full_receipt_list_leaves_a_line_and_the_quest_completes(self):
        session = self.session(6001)
        session.world_state["xp_awarded_event_ids"] = jobs._filler_ids(xp.MAX_AWARD_IDS)
        receipts = list(session.world_state["xp_awarded_event_ids"])
        outcomes = _finish(session)
        self.assertEqual(outcomes[-1]["transition"], "completed")
        self.assertEqual(session.character["xp"], 0)
        self.assertEqual(session.world_state["xp_awarded_event_ids"], receipts)
        self.assertEqual(session._take_xp_unrecorded(),
                         ["300 XP kaydedilemedi: kampanyanın ödül kaydı doldu."])

    def test_a_level_five_crossing_the_admission_refuses_does_not_reject_the_turn(self):
        session = self.session(6002)
        session.character.update(level=4, xp=2700, max_hp=40, current_hp=40)
        quest = dict(QUEST, xp=9000)
        with patch.object(quest_catalog, "CATALOG", (quest,)), \
                patch.object(game, "_validate_save_payload", _refuses_level_five):
            outcomes = _finish(session)
        self.assertEqual(outcomes[-1]["transition"], "completed")
        self.assertEqual((session.character["xp"], session.character["level"]), (2700, 4))
        self.assertNotIn("quest:quest.xp", session.world_state["xp_awarded_event_ids"])
        self.assertEqual(len(session._take_xp_unrecorded()), 1)

    def test_a_recorded_award_pays_once_and_leaves_no_line(self):
        session = self.session(6003)
        _finish(session)
        self.assertEqual(session.character["xp"], 300)
        self.assertEqual(session.world_state["xp_awarded_event_ids"].count("quest:quest.xp"), 1)
        self.assertEqual(session._take_xp_unrecorded(), [])
        again = session.evaluate_quest_events(copy.deepcopy(session.world_state), {"action": "travel"})
        self.assertEqual((again, session.character["xp"]), ([], 300))

    def test_undo_restores_the_xp_before_the_quest_award(self):
        session = self.session(6004)
        snapshot = session._capture_runtime_snapshot()
        _finish(session)
        self.assertEqual(session.character["xp"], 300)
        session._restore_runtime_snapshot(snapshot)
        self.assertEqual(session.character["xp"], 0)
        self.assertNotIn("quest:quest.xp", session.world_state["xp_awarded_event_ids"])


if __name__ == "__main__":
    unittest.main()
