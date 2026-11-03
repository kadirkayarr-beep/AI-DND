"""C1: fleeing follows the movement rules and never claims a change of place that did not happen.

Speed comes from `action_economy.speed`; the way out is checked before the roll; the fight ends only with a
committed change of place. Controlled dice, no model call.
"""

import unittest
from unittest.mock import patch

import action_economy
import combat_lifecycle
from api.tests import test_campaign_time as v1
from api.tests.test_combat_lifecycle import ready

SUCCESS = {"result": "BAŞARILI", "roll": 20, "total": 25, "dc": 12}


class FleeMovementContract(unittest.TestCase):
    def setUp(self):
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def fight(self, way_out="forest"):
        session, npc = ready(v1.scene())
        world = session.world_state
        here = world["locations"][world["location"]]
        here.pop("parent_location_id", None)
        here["exit_location_id"] = way_out
        self.assertEqual(world["combat"]["current_actor_id"], "player")
        self.assertGreater(session.character["current_hp"], 0)
        return session, npc

    def flee(self, session, roll=SUCCESS):
        with patch.object(session, "perform_skill_check", create=True, return_value=dict(roll)) as check:
            result = combat_lifecycle.flee(session)
        return result, check

    def assert_nothing_moved(self, session, before_location, result):
        world = session.world_state
        self.assertEqual(world["location"], before_location)
        self.assertIs(world["combat"]["active"], True)
        self.assertIsNotNone(result)
        self.assertNotIn("location", result["action_result"]["state_changes"])

    def assert_turn_lost(self, session, round_before, result, reason_code):
        self.assertEqual(result["action_result"]["reason_code"], reason_code)
        self.assertGreater(session.world_state["combat"]["round"], round_before)

    def test_speed_zero_cannot_flee(self):
        for condition in ("paralyzed", "petrified", "grappled", "restrained"):
            with self.subTest(condition=condition):
                session, _ = self.fight()
                self.assertIn("forest", session.world_state["locations"])
                session.character["conditions"] = [condition]
                self.assertEqual(action_economy.speed(session, "player"), 0)
                before = session.world_state["location"]
                result, check = self.flee(session)
                self.assert_nothing_moved(session, before, result)
                self.assertIs(result["action_result"]["success"], False)
                self.assertEqual(result["action_result"]["reason_code"], "speed_zero")
                self.assertEqual(session.world_state["combat"]["current_actor_id"], "player")
                check.assert_not_called()

    def test_stunned_and_incapacitated_follow_the_speed_owner(self):
        for condition in ("stunned", "incapacitated"):
            with self.subTest(condition=condition):
                session, _ = self.fight()
                session.character["conditions"] = [condition]
                before = session.world_state["location"]
                can_move = action_economy.speed(session, "player") > 0
                result, _ = self.flee(session)
                if can_move:
                    self.assertEqual(session.world_state["location"], "forest")
                    self.assertIs(session.world_state["combat"]["active"], False)
                    self.assertIn("location", result["action_result"]["state_changes"])
                else:
                    self.assert_nothing_moved(session, before, result)

    def test_invalid_exit_does_not_end_combat(self):
        for way_out in ("nowhere", None):
            with self.subTest(way_out=way_out):
                session, _ = self.fight(way_out=way_out)
                before = session.world_state["location"]
                round_before = session.world_state["combat"]["round"]
                result, check = self.flee(session)
                self.assert_nothing_moved(session, before, result)
                self.assert_turn_lost(session, round_before, result, "no_exit")
                check.assert_not_called()

    def test_failed_location_commit_has_no_location_claim(self):
        session, _ = self.fight()
        before = session.world_state["location"]
        combat_id = session.world_state["combat"]["combat_id"]
        round_before = session.world_state["combat"]["round"]
        with patch.object(session, "commit_location_change", create=True, return_value=False) as commit:
            result, check = self.flee(session)
        commit.assert_called_once_with("forest")
        check.assert_called_once()
        self.assert_nothing_moved(session, before, result)
        self.assertEqual(session.world_state["combat"]["combat_id"], combat_id)
        self.assertIsNone(session.world_state["combat"].get("end_reason"))
        self.assert_turn_lost(session, round_before, result, "exit_blocked")

    def test_valid_exit_changes_location_once(self):
        session, _ = self.fight()
        original = session.commit_location_change
        with patch.object(session, "commit_location_change", create=True, side_effect=original) as commit:
            result, check = self.flee(session)
        check.assert_called_once()
        commit.assert_called_once_with("forest")
        world = session.world_state
        self.assertEqual(world["location"], "forest")
        self.assertIs(world["combat"]["active"], False)
        self.assertEqual(world["combat"]["end_reason"], "player_fled")
        self.assertIs(result["action_result"]["success"], True)
        self.assertEqual(result["action_result"]["state_changes"], ["combat", "location"])


if __name__ == "__main__":
    unittest.main()
