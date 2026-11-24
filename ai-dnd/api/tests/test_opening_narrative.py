"""Direct unit tests for api.opening_narrative: tone, home line and catalog-line fit (no model, no campaign)."""

import unittest
from unittest import mock

from api import opening_narrative as opening


class ToneTests(unittest.TestCase):
    def test_storm_beats_everything(self):
        self.assertEqual(opening._tone({"personality": "neşeli"}, {"weather": "storm", "time_of_day": "night"}), "gergin")

    def test_night_or_fog_is_mysterious(self):
        self.assertEqual(opening._tone({}, {"time_of_day": "night", "weather": "clear"}), "gizemli")
        self.assertEqual(opening._tone({}, {"time_of_day": "day", "weather": "fog"}), "gizemli")

    def test_personality_then_backstory_then_daylight(self):
        clear_day = {"time_of_day": "day", "weather": "clear"}
        self.assertEqual(opening._tone({"personality": "Çok Şakacı"}, clear_day), "sıcak")
        self.assertEqual(opening._tone({"backstory": "Sürgün bir yolcu"}, clear_day), "melankolik")
        self.assertEqual(opening._tone({}, clear_day), "canlı")
        self.assertEqual(opening._tone({}, {"time_of_day": "evening", "weather": "clear"}), "sakin")

    def test_missing_character_text_is_tolerated(self):
        self.assertEqual(opening._tone({"personality": None, "backstory": None}, {}), "sakin")


class HomeElsewhereTests(unittest.TestCase):
    def test_blank_or_non_text_origin_has_no_home_line(self):
        for origin in (None, "", "   ", 4):
            with self.subTest(origin=origin):
                self.assertIsNone(opening._home_elsewhere(origin, "Neverwinter"))

    def test_known_city_spelling_is_restored(self):
        self.assertEqual(opening._home_elsewhere("baldursgate", "Neverwinter"), "Baldur's Gate")
        self.assertEqual(opening._home_elsewhere("Baldur's Gate", "Neverwinter"), "Baldur's Gate")

    def test_unknown_origin_is_capitalised_word_by_word(self):
        self.assertEqual(opening._home_elsewhere("kuzey vadisi", "Neverwinter"), "Kuzey Vadisi")

    def test_origin_equal_to_this_place_is_not_elsewhere(self):
        self.assertIsNone(opening._home_elsewhere("Neverwinter", "neverwinter"))


class LineFitsTests(unittest.TestCase):
    RULES = {"bound_slots": ["place"], "clear_sky_only": ["line.clear"]}

    def _item(self, **over):
        item = {
            "id": "line.a",
            "location_types": ["tavern"],
            "time_windows": [{"start_hour": 18, "end_hour": 24}],
            "required_bindings": ["place"],
        }
        item.update(over)
        return item

    def test_matching_tag_hour_and_bindings_fit(self):
        self.assertTrue(opening._line_fits(self._item(), "tavern", 20, "rain", self.RULES))

    def test_wrong_tag_or_hour_does_not_fit(self):
        self.assertFalse(opening._line_fits(self._item(), "market", 20, "rain", self.RULES))
        self.assertFalse(opening._line_fits(self._item(), "tavern", 24, "rain", self.RULES))
        self.assertFalse(opening._line_fits(self._item(), "tavern", 17, "rain", self.RULES))

    def test_unbound_slot_does_not_fit(self):
        self.assertFalse(opening._line_fits(self._item(required_bindings=["npc"]), "tavern", 20, "rain", self.RULES))

    def test_clear_sky_lines_need_clear_weather(self):
        item = self._item(id="line.clear")
        self.assertTrue(opening._line_fits(item, "tavern", 20, "clear", self.RULES))
        self.assertFalse(opening._line_fits(item, "tavern", 20, "rain", self.RULES))


class CatalogLineTests(unittest.TestCase):
    def test_no_catalog_means_no_line(self):
        with mock.patch.object(opening, "_catalog", return_value={}):
            self.assertIsNone(opening.catalog_line({"locations": {"a": {}}}, "a", "clear"))

    def test_unknown_place_means_no_line(self):
        data = {"rules": {}, "scene_tags": {}, "place_tags": {}, "items": []}
        with mock.patch.object(opening, "_catalog", return_value=data):
            self.assertIsNone(opening.catalog_line({"locations": {}}, "a", "clear"))
            self.assertIsNone(opening.catalog_line({"locations": {"a": "oops"}}, "a", "clear"))

    def test_same_seed_and_salt_draw_the_same_name_filled_line(self):
        rules = {"bound_slots": ["place"], "clear_sky_only": []}
        items = [
            {
                "id": f"line.{index}",
                "location_types": ["tavern"],
                "time_windows": [{"start_hour": 0, "end_hour": 24}],
                "required_bindings": ["place"],
                "opening_template": f"Variant {index} at {{place}}.",
            }
            for index in range(4)
        ]
        data = {"rules": rules, "scene_tags": {}, "place_tags": {"inn": "tavern"}, "items": items}
        world = {"locations": {"a": {"place_kind": "inn", "name": "The Rest"}}, "flags": {}}
        with mock.patch.object(opening, "_catalog", return_value=data), mock.patch.object(
            opening.living_world, "_campaign_seed", return_value="seed-1"
        ):
            first = opening.catalog_line(world, "a", "clear", "day")
            again = opening.catalog_line(world, "a", "clear", "day")
            salted = {opening.catalog_line(world, "a", "clear", "day", salt=n) for n in range(12)}
        self.assertEqual(first, again)
        self.assertIn("The Rest", first)
        self.assertNotIn("{place}", first)
        self.assertGreater(len(salted), 1)

    def test_catalog_that_cannot_be_read_is_empty(self):
        opening._catalog.cache_clear()
        self.addCleanup(opening._catalog.cache_clear)
        with mock.patch.object(opening.name_catalog, "CATALOG_DIR", opening.name_catalog.CATALOG_DIR / "missing-dir"):
            self.assertEqual(opening._catalog(), {})


if __name__ == "__main__":
    unittest.main()
