"""The class_progression registry: one module and one registration line add a class; the shared flow names no class."""
import ast
import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import character_progression as cp
import class_progression
from class_progression.base import ClassProgression


class NewClass(ClassProgression):
    name = "Newclass"
    supported_level = 3

    def validate_class_fields(self, player):
        if "newclass_field" in player and player.get("class") != self.name:
            raise ValueError("Unearned Newclass field.")

    def disclosure(self, level, *, focus_adopted=None, **_):
        return {"supported": [f"level {level}"], "pending": [f"focus {focus_adopted}"]}

    def attacks_per_attack_action(self, character):
        return 3

    def speed_bonus_ft(self, character, world):
        return 15


class ClassRegistry(unittest.TestCase):
    def test_every_listed_module_is_registered_under_its_class_name(self):
        self.assertLessEqual({"barbarian", "sorcerer"}, set(class_progression.CLASS_MODULES))
        self.assertLessEqual({"Barbarian", "Sorcerer"}, {handler.name for handler in class_progression.registered()})
        self.assertEqual(len(class_progression.registered()), len(class_progression.CLASS_MODULES))
        for name in ("Barbarian", "Sorcerer"):
            self.assertIs(class_progression.for_class(name), class_progression._REGISTRY[name])

    def test_registration_refuses_a_duplicate_or_a_non_string_class_name(self):
        for name in ("Barbarian", None, 7, ""):
            with self.subTest(name), patch.dict(class_progression._REGISTRY):
                handler = ClassProgression()
                handler.name = name
                with self.assertRaises(ValueError):
                    class_progression._register(handler)

    def test_unregistered_and_malformed_classes_get_the_level_one_defaults(self):
        for name in ("Wizard", "", None, 7, ["Barbarian"]):
            handler = class_progression.for_class(name)
            self.assertEqual(handler.supported_level, 1)
            self.assertFalse(handler.selected_asi)
            self.assertEqual(handler.disclosure(1), {"supported": [], "pending": []})
            with self.assertRaisesRegex(ValueError, "starting_level_class_not_supported"):
                handler.validate_start_choices(2, {})

    def test_a_registered_class_reaches_the_shared_owners_without_touching_them(self):
        with patch.dict(class_progression._REGISTRY, {"Newclass": NewClass()}):
            character = {"class": "Newclass"}
            self.assertEqual(cp._supported_level("Newclass"), 3)
            self.assertEqual(cp.progression_disclosure("Newclass", 2, focus_adopted=True),
                             {"supported": ["level 2"], "pending": ["focus True"]})
            self.assertEqual(cp.progression_effects_pending("Newclass", 2), ["focus None"])
            self.assertEqual(cp.attacks_per_attack_action(character), 3)
            self.assertEqual(cp.fast_movement_bonus_ft(character, {}), 15)
            with self.assertRaisesRegex(ValueError, "Unearned Newclass field"):
                cp.validate_saved({"class": "Sorcerer", "newclass_field": 1}, {})

    def test_a_tabled_class_without_applied_rules_refuses_subclass_and_metamagic_claims(self):
        with patch.dict(class_progression._REGISTRY, {"Newclass": NewClass()}), patch.object(cp, "table", return_value={"levels": {}}):
            for claim in ({"subclass_id": "x"}, {"metamagic": ["quickened_spell"]}):
                with self.subTest(claim), self.assertRaisesRegex(ValueError, "ilerleme"):
                    cp.validate_saved({"class": "Newclass", "level": 1, "progression_level": 1, **claim}, {})
            cp.validate_saved({"class": "Newclass", "level": 1, "progression_level": 1}, {})

    def test_a_misspelt_disclosure_keyword_is_refused_and_other_class_keywords_are_ignored(self):
        with self.assertRaisesRegex(TypeError, "rage_adoptd"):
            cp.progression_disclosure("Barbarian", 2, rage_adoptd=False)
        with self.assertRaisesRegex(TypeError, "rage_adoptd"):
            cp.progression_effects_pending("Barbarian", 2, rage_adoptd=False)
        self.assertEqual(cp.progression_disclosure("Barbarian", 2, points_adopted=False, rage_adopted=False),
                         cp.progression_disclosure("Barbarian", 2, rage_adopted=False))

    def test_moved_names_stay_readable_on_character_progression(self):
        from class_progression import barbarian, sorcerer
        for name in ("BARBARIAN_SKILLS", "EXTRA_ATTACK_ATTACKS", "FAST_MOVEMENT_FT", "_barbarian_asi_options",
                     "_validate_primal_knowledge", "barbarian_level_five_applied", "barbarian_starting_creation_options",
                     "berserker_eligible"):
            self.assertIs(getattr(cp, name), getattr(barbarian, name))
        self.assertIs(cp.sorcerer_starting_creation_options, sorcerer.sorcerer_starting_creation_options)

    def test_either_side_of_the_cycle_can_be_imported_first(self):
        fresh = [name for name in sys.modules if name.split(".")[0] in ("character_progression", "class_progression")]
        for first in ("character_progression", "class_progression", "class_progression.barbarian", "class_progression.sorcerer"):
            with self.subTest(first=first), patch.dict(sys.modules):
                for name in fresh:
                    sys.modules.pop(name, None)
                importlib.import_module(first)
                self.assertLessEqual({"Barbarian", "Sorcerer"}, {h.name for h in sys.modules["class_progression"].registered()})
                self.assertIs(sys.modules["character_progression"].berserker_eligible,
                              sys.modules["class_progression.barbarian"].berserker_eligible)

    def test_the_shared_flow_has_no_class_name_branch(self):
        source = Path(cp.__file__).read_text(encoding="utf-8")
        strings = [node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant)]
        self.assertFalse({"Barbarian", "Fighter", "Sorcerer"} & {value for value in strings if isinstance(value, str)})


if __name__ == "__main__":
    unittest.main()
