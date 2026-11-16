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


class AShownItemIsMadeOnce(unittest.TestCase):
    """Review 2026-11-16: the narration stays "shown" for turns, so a second good roll used to make a second spear;
    a shopkeeper's inventory is the shop's stock; a move the economy refuses left the made spear behind."""

    LINE = "askıdaki mızrağı gizlice çalmaya çalışıyorum"

    def setUp(self):
        from api.tests.test_species_traits import make_session
        self.session = make_session("Human")
        self.world = self.session.world_state
        self.session.recent_dm_narrations = ["kavşim dik duruyor; arkasındaki askıda bir mızrak asılı."]

    def person(self, role):
        npc = self.session.create_npc_from_ai({"name": "Kavşim", "role": role, "location": self.world["location"]})
        npc["inventory"] = []
        return npc

    def steal(self, victim):
        from unittest.mock import patch
        won = {"result": "BAŞARILI", "skill": "Sleight of Hand"}
        with patch.object(bold_acts, "_check", return_value=won), \
                patch.object(bold_acts, "_hand_to_whom", return_value=victim):
            return bold_acts._steal(self.session, self.LINE)

    def spears(self, items):
        return [item for item in items if (item.get("name") if isinstance(item, dict) else item) == "Mızrak"]

    def test_a_second_good_roll_makes_no_second_spear(self):
        guard = self.person("Muhafız")
        self.steal(guard)
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)
        self.steal(guard)
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)
        self.assertEqual(self.spears(guard["inventory"]), [])

    def test_the_made_mark_survives_a_reload(self):
        import tempfile
        from pathlib import Path
        from api.tests.test_species_traits import make_session
        self.steal(self.person("Muhafız"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            self.session.save_game(path)
            self.session = make_session("Human")
            self.session.load_game(path)
        self.world = self.session.world_state
        self.session.recent_dm_narrations = ["kavşim dik duruyor; arkasındaki askıda bir mızrak asılı."]
        guard = next(npc for npc in self.world["npcs"] if npc["name"] == "Kavşim")
        self.steal(guard)
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)

    def test_a_shopkeeper_gets_no_made_spear_in_the_stock(self):
        keeper = self.person("Shopkeeper")
        self.steal(keeper)
        self.assertEqual(self.spears(keeper["inventory"]), [])
        self.assertEqual(self.spears(self.world["inventory"]), [])

    def test_a_refused_move_takes_the_made_spear_back(self):
        import equipment_economy
        from unittest.mock import patch
        guard = self.person("Muhafız")
        with patch.object(equipment_economy, "move", side_effect=equipment_economy.EquipmentError("refused")):
            self.steal(guard)
        self.assertEqual(self.spears(guard["inventory"]), [])
        self.assertEqual(self.spears(self.world["inventory"]), [])
        self.steal(guard)  # the refused try made nothing, so a later good roll still finds the shown spear
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)


if __name__ == "__main__":
    unittest.main()
