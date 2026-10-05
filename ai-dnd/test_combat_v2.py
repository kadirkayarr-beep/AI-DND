#!/usr/bin/env python3
"""V2 turn-pipeline regressions, aligned with the authoritative exchange rules.

Initiative is rolled once and owns actor order. Plain attacks auto-complete the
player turn; all distance, equipment and perception are authored fixture facts.
All randomness is scripted on the owning session; no live model is called.
"""
import copy
import json
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game
import monster_combat
from combat_lifecycle import CombatRequestError


class CombatV2Turns(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=0)
        self.session.character.update(
            current_hp=30, max_hp=30, armor_class=12,
            strength_mod=2, dexterity_mod=2, proficiency_bonus=2,
            strength=14, dexterity=14, weapon_proficiencies=["longsword"],
            weapon_masteries=[], conditions=[],
        )
        self.world = self.session.world_state
        self.world.update(location="tavern", npcs=[], inventory=["Kılıç"],
                          player_combat_status="active")
        self.world["equipment"] = {"main_hand": "longsword", "off_hand": None}
        self.npc = {
            "id": "npc_001", "name": "Gromm", "role": "Barmen",
            "location": "tavern", "memory": [], "knowledge": [],
            "max_hp": 100, "current_hp": 100, "armor_class": 10,
            "combat_status": "active", "attack_bonus": 2,
            "damage_die": 6, "damage_dice": 1, "damage_modifier": 3,
            "distance_ft": 5, "attack_damage_type": "slashing",
        }
        self.world["npcs"].append(self.npc)
        self.world["monster_perception"] = {
            self.npc["id"]: {"player": {"visible": True}},
        }
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
        # A player attack is not a pulse for an enemy-owned initiative slot.
        with self.rolls():
            with self.assertRaises(CombatRequestError) as rejected:
                self.turn()
        self.assertEqual(rejected.exception.code, "out_of_turn")
        with self.rolls((20, 1)):
            pending = self.session.run_player_turn("Devam")["action_result"]
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

    def test_player_lethal_attack_kills_npc(self):
        self.npc["current_hp"] = 5
        with self.rolls((20, 15), (20, 5), (20, 20), (8, 3), (8, 4)):
            result = self.turn()
        self.assertEqual(result["target_status"], "dead")
        self.assertEqual(self.npc["current_hp"], 0)
        self.assertTrue(result["combat_ended"])
        self.assertEqual(result["end_reason"], "target_defeated")
        self.assertNotIn("enemy_action", result)
        self.assertFalse(result["combat"]["active"])
        self.assertEqual(result["combat"]["round"], 0)
        self.assert_snapshot(result)

    def test_npc_knocks_out_player(self):
        self.session.character["current_hp"] = 1
        # Zero HP retains the player's slot. Three successful death saves,
        # with intervening enemy misses, stabilize rather than end combat.
        original_turn = monster_combat.run_turn

        def enemy_turn(session, actor_id):
            # Observe the real owner, without skipping any legitimate turn.
            # A forbidden continuation fails clearly before unplanned dice.
            self.assertFalse(self.world["death_state"]["stable"],
                             "Enemy attacked again after stabilization")
            return original_turn(session, actor_id)

        with patch.object(monster_combat, "run_turn", side_effect=enemy_turn), self.rolls(
            (20, 15), (20, 5), (20, 1), (20, 20), (6, 3), (6, 4),
            (20, 10), (20, 1), (20, 1), (20, 10),
            (20, 1), (20, 1), (20, 10), (4, 2),
        ):
            result = self.turn()
        self.assertEqual(result["enemy_action"]["outcome"], "critical_hit")
        self.assertEqual(result["enemy_action"]["damage"], 10)
        saves = [action["death_save"] for action in result["enemy_actions"]
                 if action["action"] == "death_save"]
        self.assertEqual([save["roll"] for save in saves], [10, 10, 10])
        self.assertEqual(saves[-1]["outcome"], "stable")
        self.assertFalse(result.get("combat_ended", False))
        self.assertEqual(self.session.character["current_hp"], 0)
        self.assertEqual(self.world["player_combat_status"], "unconscious")
        self.assertTrue(result["combat"]["active"])
        self.assertEqual(result["combat"]["current_actor_id"], "player")
        self.assertTrue(self.world["death_state"]["stable"])
        self.assert_snapshot(result)
        attacks = [action for action in result["enemy_actions"]
                   if action["action"] == "enemy_attack"]
        self.assertEqual(len(attacks), 3, "Enemy attacked again after stabilization")

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
        payload = self.session.serialize_game_state()
        payload["version"] = 2
        payload["world_state"]["combat"] = {
            "active": False, "round": 0, "initiative_order": [],
            "current_turn_index": 0, "participants": [], "target_id": None,
        }
        rng_before = self.session.rng.getstate()
        # Exercise the real compatibility boundary, not a malformed native
        # world handed directly to the modern request validator.
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "legacy.json"
            save.write_text(json.dumps(payload), encoding="utf-8")
            self.session.load_game(save)
        self.assertEqual(self.session.rng.getstate(), rng_before)
        self.npc = self.world["npcs"][0]
        self.assertEqual(self.world["combat"]["schema_version"], 3)
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

    def test_explicitly_negated_attack_does_not_start_combat_or_roll(self):
        rng_before = self.session.rng.getstate()
        for phrase in (
            "Gromm'a saldırmak istemiyorum",
            "Gromm'a saldırmıyorum",
            "Gromm'a saldırmayacağım",
        ):
            with self.subTest(phrase=phrase):
                result = self.session.execute_intent(
                    {"intent": "attack"}, phrase
                )
                self.assertEqual(result["action"], "narrative")
                self.assertEqual(result["status"], "not_executed")
                self.assertEqual(result["outcome"], "negated_action")
                self.assertEqual(self.npc["current_hp"], 100)
                self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_targetless_attack_asks_before_resolving_combat(self):
        rng_before = self.session.rng.getstate()
        result = self.session.execute_intent(
            {"intent": "attack"}, "Saldırıyorum"
        )
        self.assertEqual(result["action"], "attack")
        self.assertEqual(result["status"], "clarification")
        self.assertEqual(result["outcome"], "missing_target")
        self.assertIn("Gromm", result["direct_response"])
        self.assertEqual(self.npc["current_hp"], 100)
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_ambiguous_pronoun_attack_does_not_choose_a_target(self):
        second_npc = dict(
            self.npc,
            id="npc_002",
            name="Lyra",
            role="Muhafız",
            current_hp=24,
            max_hp=24,
        )
        self.world["npcs"].append(second_npc)
        rng_before = self.session.rng.getstate()
        result = self.session.execute_intent(
            {"intent": "attack"}, "Ona saldırıyorum"
        )
        self.assertEqual(result["action"], "attack")
        self.assertEqual(result["status"], "clarification")
        self.assertEqual(result["outcome"], "ambiguous_target")
        self.assertIn("Gromm", result["direct_response"])
        self.assertIn("Lyra", result["direct_response"])
        self.assertNotIn("target_id", result)
        self.assertEqual(self.npc["current_hp"], 100)
        self.assertEqual(second_npc["current_hp"], 24)
        self.assertFalse(self.world["combat"]["active"])
        self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_ambiguous_attack_in_player_turn_is_rejected_before_resolution(self):
        second_npc = dict(
            self.npc,
            id="npc_002",
            name="Lyra",
            role="Muhafız",
            current_hp=24,
            max_hp=24,
        )
        self.world["npcs"].append(second_npc)
        before = self.session.serialize_game_state()
        rng_before = self.session.rng.getstate()
        with self.rolls():
            with self.assertRaises(CombatRequestError) as rejected:
                self.session.run_player_turn("Ona saldırıyorum", [])
        self.assertEqual(rejected.exception.code, "invalid_combat_target")
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertEqual(self.session.rng.getstate(), rng_before)
        game.parse_player_intent.assert_not_called()

    def test_wrong_location_blocked(self):
        self.npc["location"] = "forest"
        before = self.session.serialize_game_state()
        rng_before = self.session.rng.getstate()
        with self.rolls():
            with self.assertRaises(CombatRequestError) as rejected:
                self.turn()
        self.assertEqual(rejected.exception.code, "invalid_combat_target")
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertEqual(self.session.rng.getstate(), rng_before)
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