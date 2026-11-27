"""The rules functions split for the complexity gate (DK2.B) answer exactly as before: same value, same refusal text."""

from __future__ import annotations

import unittest

import dnd_2024_rules as rules
from dnd_2024_rules import CharacterCreationError

SCORES = {"strength": 15, "dexterity": 14, "constitution": 13, "intelligence": 12, "wisdom": 10, "charisma": 8}
BUDGET_SCORES = {"strength": 15, "dexterity": 14, "constitution": 13, "intelligence": 8, "wisdom": 8, "charisma": 8}  # spends 21


class AbilityScoreValidationTests(unittest.TestCase):
    def refusal(self, method, scores, pool=None) -> str:
        with self.assertRaises(CharacterCreationError) as caught:
            rules.validate_ability_scores(method, scores, pool)
        return str(caught.exception)

    def test_every_refusal_keeps_its_words(self) -> None:
        self.assertEqual(self.refusal("manual", [1]), "Ability scores must be provided as a dictionary.")
        self.assertEqual(self.refusal("manual", {**SCORES, "wisdom": "10"}), "Missing or invalid ability score for wisdom.")
        self.assertEqual(self.refusal("manual", {k: v for k, v in SCORES.items() if k != "charisma"}),
                         "Missing or invalid ability score for charisma.")
        self.assertEqual(self.refusal("standard_array", {**SCORES, "wisdom": 9}),
                         f"Standard Array requires assigning exact values {rules.STANDARD_ARRAY}.")
        self.assertEqual(self.refusal("point_buy", {**SCORES, "wisdom": 16}), "Point buy scores must be between 8 and 15.")
        self.assertEqual(self.refusal("point_buy", {**SCORES, "wisdom": 7}), "Point buy scores must be between 8 and 15.")
        self.assertEqual(self.refusal("rolled", SCORES, [3, 4, 5, 6, 7, 8]), "Assigned scores do not match the rolled dice pool.")
        self.assertEqual(self.refusal("rolled", SCORES),
                         "Rolled scores require a verified dice pool from the game engine; arbitrary manual scores are not accepted.")
        self.assertEqual(self.refusal("manual", {**SCORES, "wisdom": 19}), "Manual scores must be between 3 and 18.")
        self.assertEqual(self.refusal("manual", {**SCORES, "wisdom": 2}), "Manual scores must be between 3 and 18.")
        self.assertEqual(self.refusal("dice", SCORES), "Unsupported ability score generation method: dice")

    def test_the_point_buy_refusal_names_the_spent_points(self) -> None:
        spent = sum(rules.POINT_BUY_COSTS[v] for v in BUDGET_SCORES.values())
        self.assertNotEqual(spent, rules.POINT_BUY_BUDGET)
        self.assertEqual(self.refusal("point_buy", BUDGET_SCORES),
                         f"Point buy must spend exactly {rules.POINT_BUY_BUDGET} points (spent {spent}).")

    def test_a_good_set_is_accepted_by_each_method(self) -> None:
        rules.validate_ability_scores("standard_array", SCORES)
        rules.validate_ability_scores("point_buy", {**BUDGET_SCORES, "dexterity": 15, "constitution": 15})
        rules.validate_ability_scores("rolled", SCORES, sorted(SCORES.values()))
        rules.validate_ability_scores("manual", {**SCORES, "wisdom": 3, "charisma": 18})


class BackgroundBonusValidationTests(unittest.TestCase):
    def refusal(self, background, bonuses, base=None) -> str:
        with self.assertRaises(CharacterCreationError) as caught:
            rules.validate_background_bonuses(background, bonuses, base)
        return str(caught.exception)

    def test_every_refusal_keeps_its_words(self) -> None:
        self.assertEqual(self.refusal("Nobody", {}), "Unsupported background: Nobody")
        self.assertEqual(self.refusal("Acolyte", {"strength": 1}),
                         "Ability 'strength' is not eligible for bonuses from background 'Acolyte'.")
        self.assertEqual(self.refusal("Acolyte", {"wisdom": 1}),
                         "Background bonuses must be either (+2 to one, +1 to another) or (+1 to three distinct abilities).")
        self.assertEqual(self.refusal("Acolyte", {"wisdom": 3}),
                         "Background bonuses must name only the six abilities, each with 0, 1 or 2.")
        self.assertEqual(self.refusal("Acolyte", {"wisdom": 2, "intelligence": 1}, {"wisdom": 19, "intelligence": 10}),
                         "Ability score for 'wisdom' cannot exceed 20 after background bonuses (score was 19 + 2).")

    def test_a_good_bonus_is_accepted_and_the_cap_is_twenty(self) -> None:
        rules.validate_background_bonuses("Acolyte", {"wisdom": 2, "intelligence": 1})
        rules.validate_background_bonuses("Acolyte", {"wisdom": 2, "intelligence": 1}, {"wisdom": 18, "intelligence": 19})
        rules.validate_background_bonuses("Acolyte", {"wisdom": 1, "intelligence": 1, "charisma": 1}, {"wisdom": 19})


class ArmorReadingTests(unittest.TestCase):
    def test_armor_and_shield_come_from_the_labels(self) -> None:
        self.assertEqual(rules.get_equipment_armor_and_shield(None), (None, False))
        self.assertEqual(rules.get_equipment_armor_and_shield([]), (None, False))
        self.assertEqual(rules.get_equipment_armor_and_shield(["Chain Mail", "Shield"]), ("Chain Mail", True))
        self.assertEqual(rules.get_equipment_armor_and_shield(["Leather Armor", "Studded Leather Armor"]),
                         ("Studded Leather Armor", False))
        self.assertEqual(rules.get_equipment_armor_and_shield(["Dagger", "kalkan"]), (None, True))

    def test_two_different_suits_are_refused(self) -> None:
        with self.assertRaises(CharacterCreationError) as caught:
            rules.get_equipment_armor_and_shield(["Leather Armor", "Chain Mail"])
        self.assertEqual(str(caught.exception), "Equipment lists more than one suit of armor; only one can be worn.")

    def test_the_dexterity_term_and_the_class_total_for_every_armor_kind(self) -> None:
        self.assertEqual(rules.armor_dexterity_term(None, 3), 3)
        self.assertEqual(rules.armor_dexterity_term("Chain Mail", 3), 0)
        self.assertEqual(rules.armor_dexterity_term("Scale Mail", 3), 2)
        self.assertEqual(rules.armor_dexterity_term("Leather Armor", 5), 5)
        mods = {"dexterity": 2, "constitution": 1, "wisdom": 3}
        self.assertEqual(rules.armor_class_total("Fighter", mods, "Chain Mail", True, "Defense"), 19)
        self.assertEqual(rules.armor_class_total("Barbarian", mods, None, False, None), 13)
        self.assertEqual(rules.armor_class_total("Monk", mods, None, False, None), 15)
        self.assertEqual(rules.armor_class_total("Monk", mods, None, True, None), 12)
        self.assertEqual(rules.armor_class_total("Wizard", mods, "Nonsense", False, "Defense"), 12)


class DerivedStatsTests(unittest.TestCase):
    def test_a_wizard_with_two_feats(self) -> None:
        stats = rules.calculate_derived_stats("Wizard", "Human", SCORES, "Alert", None, None, False, ["Tough"])
        self.assertEqual((stats["max_hp"], stats["armor_class"], stats["initiative"]), (9, 12, 4))
        self.assertEqual((stats["spell_save_dc"], stats["spell_attack_bonus"], stats["passive_perception"]), (11, 3, 10))
        self.assertEqual(stats["saving_throws"], ["intelligence", "wisdom"])
        self.assertEqual(stats["saving_throw_mods"]["intelligence"], 3)

    def test_a_barbarian_a_fighter_and_a_monk(self) -> None:
        barbarian = rules.calculate_derived_stats("Barbarian", "Dwarf", SCORES)
        self.assertEqual((barbarian["max_hp"], barbarian["armor_class"], barbarian["spell_save_dc"]), (14, 13, None))
        fighter = rules.calculate_derived_stats("Fighter", "Human", SCORES, "Tough", "Defense", "Chain Mail", True)
        self.assertEqual((fighter["max_hp"], fighter["armor_class"], fighter["saving_throw_mods"]["strength"]), (13, 19, 4))
        monk = rules.calculate_derived_stats("Monk", "Human", SCORES)
        self.assertEqual((monk["max_hp"], monk["armor_class"], monk["saving_throws"]), (9, 12, ["strength", "dexterity"]))

    def test_an_unknown_class_is_refused(self) -> None:
        with self.assertRaises(CharacterCreationError) as caught:
            rules.calculate_derived_stats("Nobody", "Human", SCORES)
        self.assertEqual(str(caught.exception), "Unsupported class: Nobody")


if __name__ == "__main__":
    unittest.main()
