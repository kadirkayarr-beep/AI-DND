"""Direct unit tests for class_progression.wizard: the spellbook grows by two spells per level (PDF 164)."""

import unittest

from class_progression import wizard

HANDLER = wizard.HANDLER


class SpellbookTests(unittest.TestCase):
    def test_book_starts_with_six_and_gains_two_per_level(self):
        self.assertEqual([HANDLER.book_size(level) for level in (1, 2, 3, 5)], [6, 8, 10, 14])

    def test_each_level_asks_for_two_book_spells(self):
        self.assertEqual(HANDLER.step_choices(2), {"spellbook_spells": 2})

    def test_check_step_accepts_exactly_the_offered_spells(self):
        preview = {"choices_required": {"spellbook_spells": 2}, "spellbook_spell_ids": ["a", "b", "c"]}
        self.assertIsNone(HANDLER.check_step(None, preview, {"spellbook_spells": ["a", "c"]}))

    def test_check_step_refuses_wrong_shape_count_repeat_or_unoffered(self):
        preview = {"choices_required": {"spellbook_spells": 2}, "spellbook_spell_ids": ["a", "b", "c"]}
        bad = ("a", ["a"], ["a", "a"], ["a", "z"], ["a", 5], None)
        for picked in bad:
            with self.subTest(picked=picked):
                self.assertEqual(HANDLER.check_step(None, preview, {"spellbook_spells": picked}), "spellbook_spells_invalid")

    def test_apply_step_appends_to_the_book_and_reports_it(self):
        state = {"spellbook": ["a"]}
        changes = HANDLER.apply_step(state, {"spellbook_spells": ["b", "c"]})
        self.assertEqual(state["spellbook"], ["a", "b", "c"])
        self.assertEqual(changes, [{"kind": "spellbook", "added": ["b", "c"]}])


class ShapeAndDisclosureTests(unittest.TestCase):
    def test_start_shapes_grow_with_the_level(self):
        shapes = HANDLER.start_shapes()
        self.assertEqual(sorted(shapes), ["2", "3", "4", "5"])
        self.assertIn("subclass_id", shapes["3"])
        self.assertTrue({"cantrips", "asi"} <= shapes["4"])

    def test_disclosure_adds_the_subclass_and_asi_lines_at_their_levels(self):
        low, mid, high = (HANDLER.disclosure(level) for level in (1, 3, 5))
        self.assertLess(len(low["supported"]), len(mid["supported"]))
        self.assertTrue(any("Evoker" in line for line in mid["supported"]))
        self.assertFalse(any("Evoker" in line for line in low["supported"]))
        self.assertTrue(any("Memorize Spell" in line for line in high["pending"]))
        self.assertFalse(any("Memorize Spell" in line for line in mid["pending"]))

    def test_wizard_is_registered_with_a_spellbook_and_the_evoker_subclass(self):
        self.assertEqual(HANDLER.name, "Wizard")
        self.assertTrue(HANDLER.keeps_spellbook)
        self.assertEqual(HANDLER.subclass[0], "evoker")


if __name__ == "__main__":
    unittest.main()
