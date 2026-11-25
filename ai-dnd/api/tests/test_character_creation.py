"""Direct tests for the small creation rules in api.character_creation."""
import unittest

from api import character_creation as creation
from api.character_creation import CharacterCreationError


class WeaponProficiencyTests(unittest.TestCase):
    def test_martial_class_gets_simple_and_martial(self):
        self.assertEqual(creation._class_weapon_proficiencies("Fighter", 1, 1), ["simple", "martial"])

    def test_rogue_gets_its_own_list(self):
        granted = creation._class_weapon_proficiencies("Rogue", 3, 2)
        self.assertEqual(granted[0], "simple")
        self.assertIn("rapier", granted)
        self.assertNotIn("martial", granted)

    def test_bad_levels_are_refused(self):
        for raw, applied in ((1, 3), (1, 2), (21, 1), ("1", 1), (True, 1)):
            with self.subTest(raw=raw, applied=applied), self.assertRaises(CharacterCreationError):
                creation._class_weapon_proficiencies("Fighter", raw, applied)

    def test_a_class_without_the_martial_pair_is_refused(self):
        with self.assertRaises(CharacterCreationError):
            creation._class_weapon_proficiencies("Wizard", 1, 1)


class ArmorChoiceTests(unittest.TestCase):
    def test_armor_and_shield_are_read_from_the_choices(self):
        self.assertEqual(creation._detect_armor_and_shield(["Chain Mail", "Shield"]), ("Chain Mail", True))
        self.assertEqual(creation._detect_armor_and_shield(None), (None, False))


if __name__ == "__main__":
    unittest.main()
