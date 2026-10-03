"""Deterministic tests for the shared Python d20 resolver."""

from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.schemas import TurnRequest
from api.core_resolution import (
    resolve_ability_check,
    resolve_attack_roll,
    resolve_saving_throw,
    resolve_skill_check,
    resolution_action_scope,
)


class SequenceRoll:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


class CoreResolutionTests(unittest.TestCase):
    def test_advantage_and_disadvantage_cancel_to_one_roll(self):
        result = resolve_ability_check(
            roll_fn=SequenceRoll(7),
            ability="dexterity",
            dc=10,
            ability_modifier=2,
            advantage=True,
            disadvantage=True,
        )
        self.assertEqual(result["raw_rolls"], [7])
        self.assertEqual(result["total"], 9)
        self.assertTrue(result["advantage_cancelled"])
        self.assertEqual(result["outcome"], "FAILURE")

    def test_advantage_uses_highest_and_disadvantage_uses_lowest(self):
        advantage = resolve_ability_check(
            roll_fn=SequenceRoll(4, 17),
            ability="wisdom",
            dc=15,
            ability_modifier=0,
            advantage=True,
        )
        disadvantage = resolve_ability_check(
            roll_fn=SequenceRoll(17, 4),
            ability="wisdom",
            dc=15,
            ability_modifier=0,
            disadvantage=True,
        )
        self.assertEqual(advantage["selected_roll"], 17)
        self.assertEqual(advantage["outcome"], "SUCCESS")
        self.assertEqual(disadvantage["selected_roll"], 4)
        self.assertEqual(disadvantage["outcome"], "FAILURE")

    def test_skill_and_ability_checks_do_not_treat_natural_twenty_as_auto_success(self):
        skill = resolve_skill_check(
            roll_fn=SequenceRoll(20),
            skill="Perception",
            ability="wisdom",
            dc=25,
            ability_modifier=1,
        )
        ability = resolve_ability_check(
            roll_fn=SequenceRoll(1),
            ability="strength",
            dc=10,
            ability_modifier=10,
        )
        self.assertEqual(skill["outcome"], "FAILURE")
        self.assertEqual(ability["outcome"], "SUCCESS")
        self.assertIsNone(skill["critical_state"])

    def test_saving_throw_uses_total_not_natural_roll_shortcuts(self):
        high_bonus_natural_one = resolve_saving_throw(
            roll_fn=SequenceRoll(1),
            ability="constitution",
            dc=15,
            ability_modifier=14,
        )
        insufficient_natural_twenty = resolve_saving_throw(
            roll_fn=SequenceRoll(20),
            ability="wisdom",
            dc=25,
            ability_modifier=0,
        )
        self.assertEqual(high_bonus_natural_one["outcome"], "SUCCESS")
        self.assertEqual(insufficient_natural_twenty["outcome"], "FAILURE")

    def test_attack_roll_keeps_natural_twenty_critical_and_natural_one_miss(self):
        critical = resolve_attack_roll(
            roll_fn=SequenceRoll(20),
            attack_bonus=-2,
            target_ac=30,
        )
        automatic_miss = resolve_attack_roll(
            roll_fn=SequenceRoll(1),
            attack_bonus=30,
            target_ac=5,
        )
        self.assertEqual(critical["outcome"], "CRITICAL_HIT")
        self.assertEqual(critical["critical_state"], "critical_hit")
        self.assertEqual(automatic_miss["outcome"], "MISS")
        self.assertEqual(automatic_miss["critical_state"], "automatic_miss")

    def test_action_scope_assigns_distinct_stable_child_resolution_ids(self):
        with resolution_action_scope(
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
        ):
            first = resolve_skill_check(
                roll_fn=SequenceRoll(12),
                skill="Perception",
                ability="wisdom",
                dc=10,
                ability_modifier=1,
            )
            second = resolve_skill_check(
                roll_fn=SequenceRoll(8),
                skill="Insight",
                ability="wisdom",
                dc=10,
                ability_modifier=1,
            )
        self.assertEqual(
            first["action_id"],
            "00000000-0000-4000-8000-000000000001",
        )
        self.assertEqual(
            first["session_id"],
            "00000000-0000-4000-8000-000000000002",
        )
        self.assertNotEqual(first["resolution_id"], second["resolution_id"])
        self.assertTrue(first["resolution_id"].endswith(":skill_check:1"))
        self.assertTrue(second["resolution_id"].endswith(":skill_check:2"))

    def test_expertise_doubles_the_supplied_proficiency_modifier(self):
        result = resolve_skill_check(
            roll_fn=SequenceRoll(10),
            skill="Stealth",
            ability="dexterity",
            dc=16,
            ability_modifier=2,
            proficiency_modifier=4,
            proficient=True,
            expertise=True,
        )
        self.assertEqual(result["modifier_breakdown"]["proficiency_modifier"], 4)
        self.assertEqual(result["total"], 16)
        self.assertEqual(result["outcome"], "SUCCESS")

    def test_engine_skill_check_uses_the_core_total_for_natural_twenty_and_one(self):
        with patch.object(game, "roll_d20", side_effect=[20, 1]):
            insufficient_natural_twenty = game.perform_skill_check(
                "Perception",
                25,
                {"wisdom": 1},
                [],
                2,
            )
            high_modifier_natural_one = game.perform_skill_check(
                "Perception",
                10,
                {"wisdom": 10},
                [],
                2,
            )
        self.assertEqual(insufficient_natural_twenty["result"], "BAŞARISIZ")
        self.assertEqual(high_modifier_natural_one["result"], "BAŞARILI")
        self.assertEqual(insufficient_natural_twenty["resolution"]["outcome"], "FAILURE")
        self.assertEqual(high_modifier_natural_one["resolution"]["outcome"], "SUCCESS")

    def test_turn_action_ids_must_be_uuid4(self):
        TurnRequest(message="Inspect the door.", action_id=uuid.uuid4())
        with self.assertRaises(ValueError):
            TurnRequest(message="Inspect the door.", action_id=uuid.uuid1())


if __name__ == "__main__":
    unittest.main()