"""D-229 (Kadir playtest 2026-11-15; owner decision K5 b): an item the narration showed to the player that is in the
equipment catalog becomes a real item of the person in the scene, and stealing it follows the normal theft rules. A
named item that cannot be taken never gets a money line. The turn (steal, undo, reload) is pinned by journey 53f.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import bold_acts
import game
import weapon_catalog


def session(*narrations):
    return SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos,
                           recent_dm_narrations=list(narrations))


class TheNamedCatalogItem(unittest.TestCase):
    def test_a_catalog_weapon_named_in_the_line_is_found_in_any_case(self):
        for line, label in (("askidaki mizragi gizlice calmaya calisiyorum", "Mızrak"),
                            ("duvardaki kisa kilici aliyorum", "Kısa Kılıç"),
                            ("el baltasini asiriyorum", "El Baltası"),
                            ("gurzunu yurutuyorum", "Gürz")):
            with self.subTest(line=line):
                self.assertEqual(bold_acts._named_gear(line), label)

    def test_every_label_is_the_catalog_weapon_of_its_word(self):
        for key, label in weapon_catalog.TURKISH_LABELS.items():
            with self.subTest(label=label):
                self.assertEqual(weapon_catalog.lookup(label)["weapon_id"], weapon_catalog.TURKISH_NAMES[key])

    def test_no_catalog_weapon_no_name(self):
        for line in ("kesesini caliyorum", "masadaki elmayi caliyorum", "mecburen bakiyorum"):
            with self.subTest(line=line):
                self.assertIsNone(bold_acts._named_gear(line))


class ShownInTheNarration(unittest.TestCase):
    def test_an_item_the_last_narrations_showed_counts(self):
        told = session("kavşim'in arkasındaki askıda bir mızrak asılı duruyor.")
        self.assertTrue(bold_acts._shown(told, "Mızrak"))

    def test_an_item_never_shown_does_not(self):
        self.assertFalse(bold_acts._shown(session("han kalabalık."), "Mızrak"))
        self.assertFalse(bold_acts._shown(SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos),
                                          "Mızrak"))

    def test_only_the_last_three_narrations_are_the_scene(self):
        old = session("askıda bir mızrak var.", "a", "b", "c")
        self.assertFalse(bold_acts._shown(old, "Mızrak"))


class ANamedItemNeverGetsAMoneyLine(unittest.TestCase):
    def test_every_no_such_item_line_names_the_item_and_no_coin(self):
        for line in (*bold_acts._NO_SUCH_THING, *bold_acts._WONT_LIFT):
            with self.subTest(line=line):
                text = line.format(t="kalkan")
                self.assertIn("kalkan", text)
                for coin in ("para", "bakır", "gümüş", "altın"):
                    self.assertNotIn(coin, text.casefold())

    def test_the_lines_keep_the_draw_count(self):
        # the same rng.choice draw as _NOTHING_THERE, so every seeded roll after it stays the same
        self.assertEqual(len(bold_acts._NO_SUCH_THING), len(bold_acts._NOTHING_THERE))
        self.assertEqual(len(bold_acts._WONT_LIFT), len(bold_acts._NOTHING_THERE))


if __name__ == "__main__":
    unittest.main()
