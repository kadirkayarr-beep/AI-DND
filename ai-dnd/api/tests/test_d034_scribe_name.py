"""D-034: Kadir's decision 2026-11-15, the Scribe background is spelled "Kâtip" (TDK spelling)."""

import unittest

from api.dnd_2024_rules import BACKGROUND_DEFINITIONS


class ScribeName(unittest.TestCase):
    def test_scribe_is_katip_with_the_circumflex(self):
        self.assertEqual(BACKGROUND_DEFINITIONS["Scribe"]["name_tr"], "Kâtip")


if __name__ == "__main__":
    unittest.main()
