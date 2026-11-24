"""Direct unit tests for adventure.transitions: the only writer of dynamic adventure state."""

import copy
import unittest

from adventure import templates, transitions
from adventure.transitions import TransitionError, transition


def _quest(status="AVAILABLE"):
    quest = templates.instantiate(
        "MISSING_PERSON",
        quest_id="adv.t",
        turn=1,
        opportunity_key="opportunity:t",
        creation_evidence="event:t",
        bindings=templates.prepared_bindings(
            source_npc_id="npc.source", target_npc_id="npc.missing", location_ids=["tavern"]
        ),
        rumor="Someone is missing.",
    )
    path = {"AVAILABLE": [], "DISCOVERED": ["DISCOVERED"], "ACTIVE": ["DISCOVERED", "ACTIVE"]}[status]
    turn = 1
    for step in path:
        turn += 1
        quest = transition(quest, step, turn)
    return quest


class TransitionTests(unittest.TestCase):
    def test_legal_move_returns_a_new_row_and_keeps_the_input(self):
        quest = _quest()
        before = copy.deepcopy(quest)
        moved = transition(quest, "DISCOVERED", 2)
        self.assertEqual(quest, before)
        self.assertEqual((moved["status"], moved["updated_turn"], moved["outcome"]), ("DISCOVERED", 2, None))

    def test_first_activation_stamps_the_accepted_turn_once(self):
        active = _quest("DISCOVERED")
        active = transition(active, "ACTIVE", 5)
        self.assertEqual(active["accepted_turn"], 5)
        blocked = transition(active, "BLOCKED", 6)
        again = transition(blocked, "ACTIVE", 7)
        self.assertEqual(again["accepted_turn"], 5)

    def test_illegal_jump_or_unknown_state_is_refused(self):
        with self.assertRaises(TransitionError):
            transition(_quest(), "COMPLETED", 2)
        with self.assertRaises(TransitionError):
            transition(_quest(), "FLYING", 2)

    def test_turn_cannot_go_backwards_or_be_a_non_int(self):
        quest = _quest("DISCOVERED")
        for turn in (0, "3", None, 2.5):
            with self.subTest(turn=turn), self.assertRaises(TransitionError):
                transition(quest, "ACTIVE", turn)

    def test_terminal_states_need_a_matching_outcome(self):
        quest = _quest("ACTIVE")
        with self.assertRaises(TransitionError):
            transition(quest, "COMPLETED", 5)
        with self.assertRaises(TransitionError):
            transition(quest, "COMPLETED", 5, outcome="abandoned")
        done = transition(quest, "COMPLETED", 5, outcome="success")
        self.assertEqual(done["outcome"], "success")

    def test_outcome_on_a_non_terminal_move_is_refused(self):
        with self.assertRaises(TransitionError):
            transition(_quest(), "DISCOVERED", 2, outcome="success")

    def test_finished_adventures_cannot_move_again(self):
        done = transition(_quest("ACTIVE"), "FAILED", 5, outcome="failed")
        for target in transitions.LEGAL:
            with self.subTest(target=target), self.assertRaises(TransitionError):
                transition(done, target, 6, outcome="failed")

    def test_broken_or_legacy_rows_are_refused(self):
        quest = _quest()
        quest["status"] = "WEIRD"
        with self.assertRaises(TransitionError):
            transition(quest, "DISCOVERED", 2)
        with self.assertRaises(TransitionError):
            transition({"quest_id": "old", "status": "accepted"}, "DISCOVERED", 2)

    def test_every_state_has_a_legal_table_row(self):
        from adventure.models import STATES

        self.assertEqual(set(transitions.LEGAL), set(STATES))


if __name__ == "__main__":
    unittest.main()
