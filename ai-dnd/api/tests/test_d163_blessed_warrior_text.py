"""D-163 (DÜŞ-06): the Paladin's Blessed Warrior line names every Cleric cantrip under its real support kind.

The old line said only Sacred Flame works; Toll the Dead also has a resolver and Light has the narrative owner outside a
fight. The line is now built from the support owners (spell_registry, spell_effects.NARRATIVE), so it follows them.
No campaign is started here (no town seed needed).
"""
import unittest

import spell_effects
import spell_registry
from api.dnd_2024_rules import SPELLS_CATALOG
from class_progression.paladin import Paladin


def blessed_line(level=2):
    lines = [line for line in Paladin().disclosure(level)["supported"] if line.startswith("Blessed Warrior:")]
    assert len(lines) == 1, lines
    return lines[0]


def kinds(line):
    """{"resolver": [...], "narrative outside combat": [...], "catalog-only": [...]} from the line's labelled parts."""
    found = {}
    for part in line.split("; ")[1:]:
        label, _, names = part.partition(": ")
        found[label] = names.split(", ")
    return found


def expected_kind(spell_id):
    if spell_registry.spell_state(spell_id) == "resolver":
        return "resolver"
    return "narrative outside combat" if spell_id in spell_effects.NARRATIVE else "catalog-only"


class BlessedWarriorLine(unittest.TestCase):
    def test_every_cleric_cantrip_is_named_once_under_its_real_support(self):
        found = kinds(blessed_line())
        named = [name for names in found.values() for name in names]
        cantrips = [spell["id"] for spell in SPELLS_CATALOG["Cleric"]["cantrips"]]
        self.assertEqual(sorted(named), sorted(cantrips))
        for spell_id in cantrips:
            self.assertIn(spell_id, found[expected_kind(spell_id)], spell_id)

    def test_the_audit_cases(self):
        found = kinds(blessed_line(5))
        self.assertIn("Sacred Flame", found["resolver"])
        self.assertIn("Toll the Dead", found["resolver"])
        self.assertIn("Light", found["narrative outside combat"])
        self.assertTrue(blessed_line().startswith("Blessed Warrior: two Cleric cantrips with Charisma; "))

    def test_no_line_below_level_two(self):
        self.assertFalse([line for line in Paladin().disclosure(1)["supported"] if "Blessed Warrior" in line])


if __name__ == "__main__":
    unittest.main()
