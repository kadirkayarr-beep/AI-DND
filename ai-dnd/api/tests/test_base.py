"""Direct unit tests for class_progression.base: an unregistered class gets level 1 and no effects."""

import unittest

import class_progression
from class_progression.base import EXTRA_ATTACK_ATTACKS, ClassProgression


class _Marked(ClassProgression):
    name = "Marked"
    extra_attack_level = 5


def _character(**over):
    character = {"class": "Marked", "level": 5, "progression_level": 5}
    character.update(over)
    return character


class DefaultHooksTests(unittest.TestCase):
    def setUp(self):
        self.handler = ClassProgression()

    def test_defaults_describe_a_level_one_class_without_effects(self):
        self.assertIsNone(self.handler.name)
        self.assertEqual(self.handler.supported_level, 1)
        self.assertFalse(self.handler.selected_asi)
        self.assertEqual(self.handler.disclosure(3), {"supported": [], "pending": []})
        self.assertEqual(self.handler.adoption({}), {})
        self.assertIsNone(self.handler.capacity({}))
        self.assertEqual(self.handler.extra_spell_ids({}, "cantrips"), set())
        self.assertTrue(self.handler.progression_path_verified({}))
        self.assertEqual(self.handler.speed_bonus_ft({}, None), 0)
        self.assertIsNone(self.handler.level_prerequisite(None, 2))
        self.assertEqual(self.handler.preview_options(None, 2), {})

    def test_a_class_without_rules_claims_no_progression_choices(self):
        self.handler.validate_applied({}, {}, 1)
        for player in ({"metamagic": ["twinned"]}, {"subclass_id": "x"}):
            with self.subTest(player=player), self.assertRaises(ValueError):
                self.handler.validate_applied(player, {}, 1)

    def test_default_start_refuses_a_higher_level(self):
        with self.assertRaises(ValueError):
            self.handler.validate_start_choices(2, {})

    def test_required_level_up_hooks_are_not_implemented_by_default(self):
        with self.assertRaises(NotImplementedError):
            self.handler.choices_required({}, 1, 2, {}, {})
        with self.assertRaises(NotImplementedError):
            self.handler.check_choices(None, {}, {})
        with self.assertRaises(NotImplementedError):
            self.handler.apply_level(None, {}, {})


class ExtraAttackTests(unittest.TestCase):
    def test_class_without_extra_attack_attacks_once(self):
        self.assertFalse(ClassProgression().extra_attack_applied(_character()))
        self.assertEqual(ClassProgression().attacks_per_attack_action(_character()), 1)

    def test_extra_attack_needs_applied_and_numeric_level(self):
        handler = _Marked()
        self.assertTrue(handler.extra_attack_applied(_character()))
        self.assertEqual(handler.attacks_per_attack_action(_character()), EXTRA_ATTACK_ATTACKS)
        for over in ({"progression_level": 4}, {"level": 4}, {"class": "Other"}, {"level": "5"}, {"progression_level": None}):
            with self.subTest(over=over):
                self.assertFalse(handler.extra_attack_applied(_character(**over)))
        self.assertFalse(handler.extra_attack_applied("not a character"))


class RegistryTests(unittest.TestCase):
    def test_unknown_or_non_text_class_gets_the_default_handler(self):
        self.assertIsNone(class_progression.for_class("Bard").name)
        self.assertIsNone(class_progression.for_class(None).name)

    def test_registered_classes_resolve_by_name_and_names_are_unique(self):
        names = [handler.name for handler in class_progression.registered()]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("Wizard", names)
        self.assertEqual(class_progression.for_class("Wizard").name, "Wizard")

    def test_bad_or_duplicate_names_are_refused(self):
        with self.assertRaises(ValueError):
            class_progression._register(ClassProgression())
        with self.assertRaises(ValueError):
            class_progression._register(class_progression.for_class("Wizard"))


if __name__ == "__main__":
    unittest.main()
