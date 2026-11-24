"""Direct unit tests for adventure.encounters: bounded recipes that bind existing entities only."""

import unittest

from adventure import encounters


class RecipeTests(unittest.TestCase):
    def test_every_recipe_is_well_formed(self):
        for recipe_id, recipe in encounters.RECIPES.items():
            with self.subTest(recipe=recipe_id):
                self.assertEqual(recipe["recipe_id"], recipe_id)
                self.assertIn(recipe["threat_band"], {"low", "moderate", "high"})
                self.assertLessEqual(recipe["min_level"], recipe["max_level"])
                self.assertTrue(recipe["allowed_resolution_kinds"])

    def test_families_follow_the_recipe_table(self):
        self.assertEqual(len(encounters.families()), len(encounters.RECIPES))
        self.assertIn("patrol", encounters.families())


class BindTests(unittest.TestCase):
    def test_bind_copies_the_recipe_onto_existing_entities(self):
        bound = encounters.bind("patrol", entities=["npc.a"], location="gate")
        self.assertEqual(bound["entities"], ["npc.a"])
        self.assertEqual(bound["location"], "gate")
        self.assertEqual(bound["threat_band"], "low")
        bound["allowed_resolution_kinds"].append("x")
        self.assertNotIn("x", encounters.RECIPES["patrol"]["allowed_resolution_kinds"])

    def test_bad_inputs_bind_nothing(self):
        self.assertIsNone(encounters.bind("nope", entities=[], location="gate"))
        self.assertIsNone(encounters.bind("patrol", entities=[], location=" "))
        self.assertIsNone(encounters.bind("patrol", entities=[], location=None))
        self.assertIsNone(encounters.bind("patrol", entities="npc.a", location="gate"))
        self.assertIsNone(encounters.bind("patrol", entities=[5], location="gate"))


class SelectTests(unittest.TestCase):
    def test_default_order_starts_with_the_ambush(self):
        self.assertEqual(encounters.select(1, [])["recipe_id"], "road_ambush")

    def test_combat_heavy_history_prefers_a_non_combat_recipe(self):
        self.assertEqual(encounters.select(2, ["combat", "social", "combat"])["recipe_id"], "wounded_traveler")

    def test_bad_level_falls_back_to_level_one_and_junk_history_is_ignored(self):
        self.assertEqual(encounters.select("x", [None, 5])["recipe_id"], "road_ambush")
        self.assertEqual(encounters.select(99, [])["recipe_id"], "road_ambush")

    def test_returned_recipe_is_a_copy(self):
        chosen = encounters.select(1, [])
        chosen["threat_band"] = "high"
        self.assertEqual(encounters.RECIPES["road_ambush"]["threat_band"], "low")


if __name__ == "__main__":
    unittest.main()
