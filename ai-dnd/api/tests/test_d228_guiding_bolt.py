"""D-228: Guiding Bolt (PHB 2024 PDF 281) is a spell the engine resolves, and the preparation view names what it cannot.

Rule: ranged spell attack, 120 ft; Hit: 4d6 Radiant and the next attack roll made against the target before the end of
the caster's next turn has Advantage; +1d6 per slot level above 1. Kadir 2026-11-15: add it to the engine; every
candidate the engine cannot resolve is marked "not yet" in the preparation view (API field `not_in_engine`).
Fixtures: test_dilim4c_spell_resolvers.cleric (fixed session seed 17; no campaign, no town)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import character_progression
import spell_preparation
import spell_registry
import spell_scope
import weapon_attack as attack
from api.tests.test_dilim4c_spell_resolvers import cleric, magic, next_turn, turn
from api.tests.test_weapon_attack import armed, resolve


def guiding_cleric():
    s, enemy = cleric(prepared=("Bless", "Healing Word", "Guiding Bolt"))
    return s, enemy


class GuidingBoltCast(unittest.TestCase):
    def test_the_engine_owns_it_as_a_level_one_ranged_attack(self):
        self.assertEqual(spell_registry.spell_state("Guiding Bolt"), "resolver")
        self.assertEqual(spell_scope.CATALOG["Guiding Bolt"], (1, 120, 6, "radiant"))
        self.assertEqual(spell_scope.SPELL_ATTACKS["Guiding Bolt"], "ranged")

    def test_a_hit_rolls_4d6_radiant_spends_a_slot_and_marks_the_target(self):
        s, enemy = guiding_cleric()
        with patch("game.roll_d20", return_value=12), patch.object(s.rng, "randint", return_value=3) as dice:
            result = spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        self.assertTrue(result["hit"])
        self.assertEqual((result["damage"], dice.call_count, result["damage_type"]), (12, 4, "radiant"))
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertEqual(result["rider"], "guiding_bolt")
        self.assertEqual([(e["kind"], e["target_id"], e["expires_boundary"]) for e in s.world_state["attack_effects"]],
                         [("guiding_bolt", enemy["id"], "end")])

    def test_a_critical_hit_rolls_8d6(self):
        s, enemy = guiding_cleric()
        with patch("game.roll_d20", return_value=20), patch.object(s.rng, "randint", return_value=3) as dice:
            result = spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        self.assertEqual((result["damage"], dice.call_count), (24, 8))

    def test_a_miss_costs_the_slot_and_marks_nothing(self):
        s, enemy = guiding_cleric()
        with patch("game.roll_d20", return_value=2), patch.object(s.rng, "randint", return_value=3):
            result = spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        self.assertFalse(result["hit"])
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertEqual(s.world_state.get("attack_effects", []), [])

    def test_a_higher_slot_adds_one_d6_a_level(self):
        s, enemy = guiding_cleric()
        s.character.update(level=3, progression_level=3, proficiency_bonus=2)
        s.world_state["spellcasting_v1"]["slots"] = character_progression.slot_capacity(s.character)
        result = turn(s, magic("Guiding Bolt", enemy["id"], slot_level=2), d20=12, dice=2)
        self.assertEqual(result["action_result"]["damage"], 10)  # 5d6, every die 2
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["2"], 1)

    def test_it_must_be_prepared(self):
        s, enemy = cleric()  # Bless and Healing Word only
        with self.assertRaises(Exception) as caught:
            spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        self.assertEqual(getattr(caught.exception, "code", None), "spell_not_available")

    def test_it_is_spoken_in_turkish_too(self):
        self.assertEqual(spell_scope.ALIASES.get("yol gösteren ışın"), "Guiding Bolt")


class GuidingBoltAdvantage(unittest.TestCase):
    def test_the_next_spell_attack_on_the_target_has_advantage_and_uses_the_mark_up(self):
        s, enemy = guiding_cleric()
        with patch("game.roll_d20", return_value=12), patch.object(s.rng, "randint", return_value=3):
            spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        s.world_state["spellcasting_v1"]["slots"]["1"] = 1
        next_turn(s)
        with patch("game.roll_d20", side_effect=[3, 15]), patch.object(s.rng, "randint", return_value=3):
            result = spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        self.assertTrue(result["hit"])  # advantage kept the 15
        self.assertEqual(result["resolution"]["selected_roll"], 15)

    def test_the_mark_is_used_up_by_one_attack_even_a_miss(self):
        s, enemy = guiding_cleric()
        with patch("game.roll_d20", return_value=12), patch.object(s.rng, "randint", return_value=3):
            spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        s.world_state["spellcasting_v1"]["slots"]["1"] = 1
        next_turn(s)
        with patch("game.roll_d20", side_effect=[3, 4]), patch.object(s.rng, "randint", return_value=3):
            result = spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        self.assertFalse(result["hit"])
        self.assertEqual(s.world_state["attack_effects"], [])

    def test_a_weapon_attack_on_the_target_has_advantage_and_uses_the_mark_up(self):
        s, n = armed("Longsword")
        attack.effect(s, "guiding_bolt", "player", n["id"])
        r = resolve(s, n, "Longsword", rolls=(3, 18))
        self.assertIn("guiding_bolt", r["advantage_sources"])
        self.assertTrue(r["hit"])
        self.assertEqual(s.world_state["attack_effects"], [])

    def test_the_mark_runs_out_at_the_end_of_the_casters_next_turn(self):
        s, n = armed("Longsword")
        attack.effect(s, "guiding_bolt", "player", n["id"])
        s.advance_combat_turn()
        s.advance_combat_turn()
        self.assertTrue(s.world_state["attack_effects"])
        s.advance_combat_turn()
        self.assertEqual(s.world_state["attack_effects"], [])

    def test_a_saved_mark_with_the_wrong_expiry_is_refused(self):
        s, enemy = guiding_cleric()
        with patch("game.roll_d20", return_value=12), patch.object(s.rng, "randint", return_value=3):
            spell_scope.cast(s, "Guiding Bolt", enemy["id"])
        spell_scope.validate_saved_riders(s.world_state)  # as written: fine
        s.world_state["attack_effects"][0]["expires_boundary"] = "begin"
        with self.assertRaises(ValueError):
            spell_scope.validate_saved_riders(s.world_state)


class PreparationNamesWhatTheEngineLacks(unittest.TestCase):
    def test_cleric_view_marks_the_candidates_without_a_resolver(self):
        s, _enemy = guiding_cleric()
        view = spell_preparation.view(s)
        self.assertEqual(view["not_in_engine"], ["Sanctuary", "Bane", "Command"])
        for spell in ("Cure Wounds", "Healing Word", "Bless", "Guiding Bolt"):
            self.assertNotIn(spell, view["not_in_engine"])

    def test_blocked_view_has_the_field_too(self):
        s, _enemy = guiding_cleric()
        s.character["class"] = "Fighter"
        s.world_state.pop("spellcasting_v1", None)
        view = spell_preparation.view(s)
        self.assertEqual(view["not_in_engine"], [])


if __name__ == "__main__":
    unittest.main()


class ReviewFixes(unittest.TestCase):
    def test_narration_says_the_casters_turn_not_the_targets(self):
        line = spell_scope.narration({"spell_id": "Guiding Bolt", "hit": True, "damage": 7, "rider": spell_scope.GUIDING_BOLT_EFFECT})
        self.assertIn("senin sıradaki turunun sonuna dek", line)

    def test_upcast_refusal_names_guiding_bolt_too(self):
        self.assertIn("Guiding Bolt", spell_scope.UPCAST_REFUSAL)
