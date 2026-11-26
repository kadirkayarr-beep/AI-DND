"""DK1.A: pins for the functions split to bring their radon rank back (Dalga 1 gate growth fix).

`_nsd_door_open_claim`, `_dpt_front_gate`, `_dpt_out_of_combat_commands` and `_local_place_turn` answer what they answered
before they were split. Every owner is replaced by a recorder, so each test shows which owner took the line, with what,
and in which order. No model, no campaign: a bare `GameSession`.
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import adventure.play as adventure_play
import game

FALL = game._TURN_FALL_THROUGH
OWNERS = {"offer_answer": "_front_offer_gate", "consume": "_front_consume", "hand_over": "_front_hand_over",
          "work": "_front_work"}


def rejected(code, span=None):
    return ("rejected", code, span)


class TestDoorClaimsAgainstTheRealDoor(unittest.TestCase):
    def claim(self, door, text):
        return game._nsd_door_open_claim(door=door, reject=rejected, text=text)

    def test_each_claim_the_door_contradicts_is_rejected_with_its_words(self):
        closed = {"open": False, "locked": False, "broken": False}
        open_door = {"open": True, "locked": False, "broken": False}
        locked = {"open": False, "locked": True, "broken": False}
        self.assertEqual(self.claim(closed, "kapı açıldı."), rejected("DOOR_STATE_CONTRADICTION", "kapı açıldı"))
        self.assertEqual(self.claim(open_door, "kapı kapalı."), rejected("DOOR_STATE_CONTRADICTION", "kapı kapalı"))
        self.assertEqual(self.claim(open_door, "kapı parçalandı."),
                         rejected("DOOR_STATE_CONTRADICTION", "kapı parçalandı"))
        self.assertEqual(self.claim(locked, "kilit çözüldü."), rejected("DOOR_STATE_CONTRADICTION", "kilit çözüldü"))
        self.assertEqual(self.claim(closed, "kapı kilitli duruyor."),
                         rejected("DOOR_STATE_CONTRADICTION", "kapı kilitli"))

    def test_a_claim_the_door_agrees_with_falls_through(self):
        for door, text in (
            ({"open": True, "locked": False}, "kapı açıldı."),
            ({"open": False, "locked": False}, "kapı kapalı."),
            ({"open": True, "locked": False, "broken": True}, "kapı parçalandı."),
            ({"open": False, "locked": False}, "kilit çözüldü."),
            ({"open": False, "locked": True}, "kapı kilitli."),
        ):
            with self.subTest(text=text):
                self.assertIs(self.claim(door, text), FALL)

    def test_no_door_or_no_claim_falls_through(self):
        self.assertIs(self.claim(None, "kapı açıldı."), FALL)
        self.assertIs(self.claim({"open": False, "locked": False}, "orman sessiz."), FALL)


class TestTheFrontGateNamesItsOwner(unittest.TestCase):
    def run_gate(self, front, *, job=False):
        calls = []

        def owner(name):
            def call(*args, **kwargs):
                calls.append((name, args, kwargs))
                return ("from", name)
            return call

        patches = [
            patch.object(game, "_front_offer_gate", owner("_front_offer_gate")),
            patch.object(game, "_front_consume", owner("_front_consume")),
            patch.object(game, "_front_hand_over", owner("_front_hand_over")),
            patch.object(game, "_front_work", owner("_front_work")),
            patch.object(game, "_thread_gate", owner("_thread_gate")),
            patch.object(game, "_take_names_a_job", return_value=job),
        ]
        for each in patches:
            each.start()
            self.addCleanup(each.stop)
        result = game._dpt_front_gate(front=front, interaction_mode="do", player_input="line", target_id="t1")
        return result, calls

    def test_each_kind_goes_to_its_own_gate_with_the_front_and_the_line(self):
        for kind, name in OWNERS.items():
            with self.subTest(kind=kind):
                front = {"kind": kind}
                result, calls = self.run_gate(front)
                self.assertEqual(result, ("from", name))
                self.assertEqual(calls, [(name, (front, "line"), {})])

    def test_no_reading_and_every_other_kind_go_to_the_thread_gate(self):
        for front in (None, {"kind": "speak_to"}, {"kind": "go_to"}):
            with self.subTest(front=front):
                result, calls = self.run_gate(front)
                self.assertEqual(result, ("from", "_thread_gate"))
                self.assertEqual(calls, [("_thread_gate", ("line", "t1", "do"), {"front": front})])

    def test_a_dropped_reading_a_wield_and_a_job_take_have_no_gate(self):
        for front, job in (({"kind": "hand_over", "dropped": True}, False), ({"kind": "wield"}, False),
                           ({"kind": "take"}, True), ({"kind": "consume", "dropped": True}, False)):
            with self.subTest(front=front, job=job):
                result, calls = self.run_gate(front, job=job)
                self.assertIsNone(result)
                self.assertEqual(calls, [])


class TestOutOfCombatCommandsKeepTheirOrder(unittest.TestCase):
    def run_line(self, *, front=None, mode="do", combat_action=None, active=False, answers=()):
        """Every owner answers None unless named in `answers`; returns (result, the order the owners were asked in)."""
        order = []
        session = game.GameSession(seed=3)
        session.world_state["combat"] = {"active": active}

        def recorder(name, value=None):
            def call(*args, **kwargs):
                order.append(name)
                return value
            return call

        def spoken(grounded, *rest):
            order.append("spoken")
            return ("spoken", grounded)

        def answer(name):
            return ("answer", name) if name in answers else None

        with (
            patch.object(game, "_session", return_value=session),
            patch.object(adventure_play, "resolve_dungeon_turn", recorder("hideout", answer("hideout"))),
            patch.object(game, "_adventure_scene_turn", recorder("scene", answer("scene"))),
            patch.object(game, "_scene_observation_proposal_turn", recorder("observation", False)),
            patch("grounded_action.resolve_turn", recorder("grounded", {"narration": "g"} if "grounded" in answers else None)),
            patch.object(game, "_spoken_rest_of_turn", spoken),
            patch.object(game, "_local_place_turn", recorder("place", answer("place"))),
            patch.object(game, "_everyday_action_turn", recorder("everyday", answer("everyday"))),
        ):
            result = game._dpt_out_of_combat_commands(
                action_id=None, combat_action=combat_action, front=front, interaction_mode=mode,
                messages=[], player_input="line", session_id="s", target_id=None)
        return result, order

    def test_the_owners_are_asked_in_order_until_one_answers(self):
        self.assertEqual(self.run_line(), (FALL, ["hideout", "scene", "observation", "grounded", "place", "everyday"]))
        self.assertEqual(self.run_line(answers=("hideout",)), (("answer", "hideout"), ["hideout"]))
        self.assertEqual(self.run_line(answers=("scene",)), (("answer", "scene"), ["hideout", "scene"]))
        self.assertEqual(self.run_line(answers=("grounded",)),
                         (("spoken", {"narration": "g"}), ["hideout", "scene", "observation", "grounded", "spoken"]))
        self.assertEqual(self.run_line(answers=("place",))[0], ("answer", "place"))
        self.assertEqual(self.run_line(answers=("everyday",))[0], ("answer", "everyday"))

    def test_a_line_read_as_talk_walks_nowhere(self):
        for kind in ("talk_around", "look", "sit"):
            with self.subTest(kind=kind):
                result, order = self.run_line(front={"kind": kind})
                self.assertIs(result, FALL)
                self.assertEqual(order, ["hideout"])

    def test_the_everyday_words_wait_for_no_reading_or_an_unclear_one(self):
        self.assertIn("everyday", self.run_line(front={"kind": "unclear"})[1])
        self.assertNotIn("everyday", self.run_line(front={"kind": "go_to"})[1])

    def test_a_combat_action_a_say_line_and_a_fight_in_progress_are_not_this_owner(self):
        cases: list[dict[str, Any]] = [{"combat_action": {"x": 1}}, {"mode": "say"}, {"mode": "ask_dm"}, {"active": True}]
        for kwargs in cases:
            with self.subTest(**kwargs):
                self.assertEqual(self.run_line(**kwargs), (FALL, []))


if __name__ == "__main__":
    unittest.main()
