"""Direct unit tests for incidents.categories: Python owns DCs, checks and payouts."""

import unittest

from incidents import categories


class CategoryTests(unittest.TestCase):
    def test_dc_comes_from_python_and_defaults_to_medium(self):
        self.assertEqual(categories.dc_for("easy"), 10)
        self.assertEqual(categories.dc_for("hard"), 20)
        self.assertEqual(categories.dc_for("legendary"), 15)
        self.assertEqual(categories.dc_for(None), 15)

    def test_skill_tokens_map_to_rule_names(self):
        self.assertEqual(categories.skill_for("sleight_of_hand"), "Sleight of Hand")
        self.assertIsNone(categories.skill_for("wish"))

    def test_check_owners_add_tool_and_spell(self):
        self.assertTrue({"insight", "tool", "spell"} <= categories.CHECK_OWNERS)
        self.assertNotIn("wish", categories.CHECK_OWNERS)

    def test_narrated_gambling_never_pays(self):
        self.assertFalse(categories.gambling_pays({"action": "gambling", "source": "narration"}))
        self.assertFalse(categories.gambling_pays({"action": "gambling", "source": "engine"}))
        self.assertFalse(categories.gambling_pays("win"))

    def test_motif_cooldown_blocks_a_third_repeat(self):
        world = {"emergence_state": {"recent_categories": ["a", "b", "b", "b"]}}
        self.assertFalse(categories.motif_allowed(world, "b"))
        self.assertTrue(categories.motif_allowed(world, "a"))
        self.assertTrue(categories.motif_allowed({}, "b"))
        self.assertTrue(categories.motif_allowed({"emergence_state": {"recent_categories": "bad"}}, "b"))


if __name__ == "__main__":
    unittest.main()
