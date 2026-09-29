#!/usr/bin/env python3
"""V2 turn-pipeline regressions, aligned with the authoritative exchange rules.

Initiative is rolled once, before attacks. Each command resolves player then
enemy and advances one round, regardless of initiative metadata. All randomness
is scripted on the owning session, including damage; no live model is called.
"""
import copy
from contextlib import contextmanager
import unittest
from unittest.mock import patch

import game


class CombatV2Turns(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=0)
        self.session.character.update(
            current_hp=30, max_hp=30, armor_class=12,
            strength_mod=2, dexterity_mod=2, proficiency_bonus=2,
        )
        self.world = self.session.world_state
        self.world.update(location="tavern", npcs=[], inventory=["Kılıç"],
                          player_combat_status="active")
        self.npc = {
            "id": "npc_001", "name": "Gromm", "role": "Barmen",
            "location": "tavern", "memory": [], "knowledge": [],
            "max_hp": 100, "current_hp": 100, "armor_class": 10,
            "combat_status": "active", "attack_bonus": 2,
            "damage_die": 6, "damage_dice": 1, "damage_modifier": 3,
        }
        self.world["npcs"].append(self.npc)
        for name, result in (
            ("parse_player_intent", {"intent": "attack", "action": "attack",
                                    "target": {"type": "npc", "reference": "Gromm"},
                                    "completion": "completed", "confidence": 1.0}),
            ("ask_dungeon_master", {"narration": "", "world_updates": {},
                                   "valid_response": True}),
        ):
            mock = patch.object(game, name, return_value=result)
            mock.start()
            self.addCleanup(mock.stop)

    @contextmanager
    def rolls(self, *expected):
        """(die size, value) pairs; extra, missing or wrong dice fail the test."""
        remaining = iter(expected)

        def randint(low, high):
            roll = next(remaining, None)
            self.assertIsNotNone(roll, f"Unexpected d{high} roll")
            sides, value = roll
            self.assertEqual((low, high), (1, sides))
            self.assertTrue(low <= value <= high)
            return value

        with patch.object(self.session.rng, "randint", side_effect=randint):
            yield
            self.assertIsNone(next(remaining, None), "Unused scripted dice")

    def turn(self):
        return self.session.run_player_turn(
            "Gromm'a kılıcımla saldırıyorum", []
        )["action_result"]

    def assert_snapshot(self, result):
        expected = copy.deepcopy(self.world["combat"])
        expected.update(player_current_hp=self.session.character["current_hp"],
                        player_max_hp=self.session.character["max_hp"],
                        player_combat_status=self.world["player_combat_status"])
        self.assertEqual(result["combat"], expected)

    def test_combat_start(self):
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 1)):
            result = self.turn()
        self.assertEqual(result["action"], "attack")
        self.assertTrue(result["combat_started"])
        self.assertTrue(result["combat"]["active"])
        self.assertEqual(result["combat"]["round"], 2)
        self.assertEqual(result["combat"]["target_id"], self.npc["id"])
        self.assert_snapshot(result)

    def test_initiative_player_higher(self):
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 1)):
            result = self.turn()
        self.assertEqual(result["combat"]["initiative_order"], ["player", "npc_001"])
        self.assertEqual(result["combat"]["current_turn_index"], 0)

    def test_initiative_npc_higher(self):
        # A resumed NPC turn resolves first; the unspent player command can be retried.
        self.npc["current_hp"] = 1
        with self.rolls((20, 2), (20, 18)):
            self.session.start_combat(self.npc)
        self.assertEqual(self.world["combat"]["initiative_order"], ["npc_001", "player"])
        with self.rolls((20, 1)):
            pending = self.turn()
        self.assertEqual(pending["outcome"], "enemy_turn_resolved")
        self.assertEqual(self.world["combat"]["current_actor_id"], "player")
        with self.rolls((20, 15), (8, 4)):
            result = self.turn()
        self.assertEqual(result["end_reason"], "target_defeated")
        self.assertNotIn("enemy_action", result)

    def test_enemy_hit(self):
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 18), (6, 4)):
            result = self.turn()
        enemy = result["enemy_action"]
        self.assertEqual((enemy["outcome"], enemy["damage"]), ("hit", 7))
        self.assertEqual((enemy["target_hp_before"], enemy["target_hp_after"]), (30, 23))
        self.assertEqual(self.session.character["current_hp"], 23)
        self.assert_snapshot(result)

    def test_enemy_miss(self):
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 2)):
            result = self.turn()
        self.assertEqual(result["enemy_action"]["outcome"], "miss")
        self.assertEqual(result["enemy_action"]["damage"], 0)
        self.assertEqual(self.session.character["current_hp"], 30)

    def test_enemy_nat1(self):
        self.npc["attack_bonus"] = 100
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 1)):
            result = self.turn()
        enemy = result["enemy_action"]
        self.assertEqual((enemy["outcome"], enemy["critical"], enemy["damage"]),
                         ("miss", False, 0))
        self.assertEqual(self.session.character["current_hp"], 30)

    def test_enemy_nat20(self):
        self.session.character["armor_class"] = 100
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 20), (6, 3), (6, 4)):
            result = self.turn()
        enemy = result["enemy_action"]
        self.assertEqual((enemy["outcome"], enemy["critical"], enemy["damage"]),
                         ("critical_hit", True, 10))
        self.assertEqual(self.session.character["current_hp"], 20)

    def test_player_knocks_out_npc(self):
        self.npc["current_hp"] = 5
        with self.rolls((20, 15), (20, 5), (20, 20), (8, 3), (8, 4)):
            result = self.turn()
        self.assertEqual(result["target_status"], "unconscious")
        self.assertEqual(self.npc["current_hp"], 0)
        self.assertTrue(result["combat_ended"])
        self.assertEqual(result["end_reason"], "target_defeated")
        self.assertNotIn("enemy_action", result)
        self.assertFalse(result["combat"]["active"])
        self.assertEqual(result["combat"]["round"], 0)
        self.assert_snapshot(result)

    def test_npc_knocks_out_player(self):
        self.session.character["current_hp"] = 1
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 20), (6, 3), (6, 4)):
            result = self.turn()
        self.assertTrue(result["combat_ended"])
        self.assertEqual(result["end_reason"], "player_defeated")
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertEqual(self.world["player_combat_status"], "unconscious")
        self.assertFalse(result["combat"]["active"])
        self.assert_snapshot(result)

    def test_round_advance(self):
        # Initiative consumes two dice only once, then two misses per exchange.
        with self.rolls((20, 15), (20, 5), *([(20, 1), (20, 1)] * 4)):
            for expected_round in range(2, 6):
                result = self.turn()
                self.assertEqual(result["combat"]["round"], expected_round)
                self.assertTrue(result["combat"]["active"])
                self.assertEqual(result["combat"]["initiative_order"], ["player", "npc_001"])
                self.assertEqual(result["combat"]["current_turn_index"], 0)
                self.assert_snapshot(result)

    def test_combat_state_legacy(self):
        del self.world["combat"]
        del self.world["player_combat_status"]
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 1)):
            result = self.turn()
        self.assertTrue(result["combat"]["active"])
        self.assertEqual(result["combat"]["round"], 2)
        self.assertEqual(self.world["player_combat_status"], "active")
        self.assert_snapshot(result)

    def test_qwen_cannot_modify_player_hp(self):
        before = copy.deepcopy(self.session.character)
        updates = {"current_hp": 999, "max_hp": 999, "armor_class": 999,
                   "player_combat_status": "unconscious"}
        self.session.merge_world_updates(self.session.validate_world_updates(updates))
        self.assertEqual(self.session.character, before)
        self.assertEqual(self.world["player_combat_status"], "active")

    def test_qwen_cannot_modify_combat_state(self):
        with self.rolls((20, 15), (20, 5)):
            self.session.start_combat(self.npc)
        before = copy.deepcopy(self.world)
        updates = {"combat": {"active": False}, "round": 999,
                   "initiative_order": [], "current_turn_index": 999,
                   "participants": [], "target_id": "forged"}
        self.session.merge_world_updates(self.session.validate_world_updates(updates))
        self.assertEqual(self.world, before)

    def test_wrong_location_blocked(self):
        self.npc["location"] = "forest"
        with self.rolls():
            result = self.turn()
        self.assertEqual(result["outcome"], "no_target")
        self.assertEqual(self.npc["current_hp"], 100)
        self.assertEqual(self.session.character["current_hp"], 30)
        self.assertFalse(self.world["combat"]["active"])

    def test_forged_npc_blocked(self):
        forged = dict(self.npc, armor_class=0, current_hp=1)
        self.npc["armor_class"] = 100
        with self.rolls((20, 15), (20, 5), (20, 15), (20, 1)):
            result = self.session.execute_intent(
                {"intent": "attack"}, "Gromm'a kılıcımla saldırıyorum", forged)
        self.assertEqual(result["outcome"], "miss")
        self.assertEqual(result["target_ac"], 100)
        self.assertEqual(self.npc["current_hp"], 100)
        self.assertEqual(forged["current_hp"], 1)


def run_all_tests():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CombatV2Turns)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_all_tests() else 1)