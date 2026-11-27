"""G2.26: dead code stays deleted (D-512, D-544, D-509, D-513, D-580, D-601)."""

from __future__ import annotations

import importlib.util
import unittest

import local_exploration
import spells
from api.lore_authority import freeze_admission
from incidents import categories
import interaction_adventure


class DeadCodeStaysDeletedTests(unittest.TestCase):
    def test_removed_names_are_gone(self):
        removed = (
            (interaction_adventure, "bind_deadline"),
            (categories, "combat_bind_allowed"),
            (local_exploration, "LEVER"),
            (freeze_admission, "admit_public_batch"),
            (freeze_admission, "projection_is_transform_ready"),
            (spells, "legality"),
            (categories, "SOCIAL"),
            (categories, "URBAN_THEFT"),
            (categories, "LOST_PROPERTY"),
            (categories, "TRAVEL"),
            (categories, "WILDERNESS"),
            (categories, "DISTURBANCE"),
        )
        for module, name in removed:
            with self.subTest(name=name):
                self.assertFalse(hasattr(module, name))

    def test_intent_contract_module_is_gone(self):
        self.assertIsNone(importlib.util.find_spec("intent_contract"))

    def test_live_category_names_stay(self):
        self.assertEqual(categories.COMBAT, "combat")
        self.assertEqual(categories.GAMBLING, "gambling")


if __name__ == "__main__":
    unittest.main()
