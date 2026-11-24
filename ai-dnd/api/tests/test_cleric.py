"""Direct unit tests for class_progression.cleric: Life Domain is the one subclass offered at level 3."""

import unittest

from class_progression import cleric

HANDLER = cleric.HANDLER


class ClericTests(unittest.TestCase):
    def test_cleric_is_a_prepared_caster_with_the_life_domain(self):
        self.assertEqual(HANDLER.name, "Cleric")
        self.assertEqual(HANDLER.subclass[0], "life_domain")

    def test_start_shapes_name_what_each_level_must_choose(self):
        shapes = HANDLER.start_shapes()
        self.assertEqual(shapes["2"], set())
        self.assertEqual(shapes["3"], {"subclass_id"})
        self.assertEqual(shapes["4"], {"cantrips", "asi"})
        self.assertEqual(shapes["5"], set())

    def test_disclosure_grows_level_by_level(self):
        lines = {level: HANDLER.disclosure(level) for level in (1, 2, 3, 4, 5)}
        self.assertFalse(any("Channel Divinity" in text for text in lines[1]["pending"]))
        self.assertTrue(any("Channel Divinity" in text for text in lines[2]["pending"]))
        self.assertFalse(any("Life Domain" in text for text in lines[2]["supported"]))
        self.assertTrue(any("Life Domain" in text for text in lines[3]["supported"]))
        self.assertTrue(any("Ability Score Improvement" in text for text in lines[4]["supported"]))
        self.assertTrue(any("Sear Undead" in text for text in lines[5]["pending"]))
        self.assertGreater(len(lines[5]["pending"]), len(lines[1]["pending"]))


if __name__ == "__main__":
    unittest.main()
