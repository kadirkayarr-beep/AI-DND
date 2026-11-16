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

    def test_a_longer_name_shown_is_not_the_shorter_one(self):
        # fourth review 2026-11-16: "kılıç" matched inside "büyük kılıç", so a shown greatsword also showed a longsword
        for told, shown, not_shown in (("Askıda tek bir büyük kılıç asılı.", "Büyük Kılıç", "Kılıç"),
                                       ("Askıda tek bir kısa kılıç asılı.", "Kısa Kılıç", "Kılıç"),
                                       ("Askıda bir uzun kılıç asılı.", "Uzun Kılıç", "Kılıç")):
            with self.subTest(told=told):
                self.assertEqual(bold_acts._shown(session(told), shown), told)
                self.assertIsNone(bold_acts._shown(session(told), not_shown))
        both = "Masada bir kılıç, duvarda bir büyük kılıç var."
        self.assertEqual(bold_acts._shown(session(both), "Kılıç"), both)

    def test_a_narration_that_says_there_is_none_shows_none(self):
        # third review 2026-11-16: "burada hiç mızrak yok" counted as a showing and made a spear
        for told in ("Burada hiç mızrak yok.", "Askıdaki mızrak artık yok.", "Elindeki şey mızrak değil, bir sopa.",
                     "Mızrak askısı boş.", "Askıda mızrak kalmadı.", "Mızraktan eser yoktu.",
                     # fourth review 2026-11-16
                     "Askıda tek bir mızrak bile bulunmuyor.", "Hiçbir mızrak göremiyorsun.", "Mızraklar çoktan gitmiş.",
                     "Mızrak satılmış, askı artık bomboş.", "Mızrak satılmış ve askı artık bomboş duruyor.",
                     "Mızraksız bir askı duruyor.", "Askıda mızrak görmüyorsun.", "Hiç mızrak kalmamış."):
            with self.subTest(told=told):
                self.assertIsNone(bold_acts._shown(session(told), "Mızrak"))
                # the newest word about the spear decides: an older showing is gone once it is said to be gone
                self.assertIsNone(bold_acts._shown(session("askıda bir mızrak asılı.", told), "Mızrak"))

    def test_a_none_in_another_clause_does_not_hide_the_shown_one(self):
        for told in ("Askıda bir mızrak asılı, ama kese yok.", "Kese boş; askıda bir mızrak duruyor.",
                     "Kimse bakmıyor değil, askıda bir mızrak var.",
                     # fourth review: words that only begin like a none ("yokuş", "bostan", "boşluk", "değirmen")
                     "Yokuşta bir mızrak duruyor.", "Bostan korkuluğuna dayalı bir mızrak var.",
                     "Duvardaki boşlukta bir mızrak duruyor.", "Değirmenin kapısında bir mızrak asılı."):
            with self.subTest(told=told):
                self.assertEqual(bold_acts._shown(session(told), "Mızrak"), told)


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

    def person(self, role, name="Kavşim"):
        npc = self.session.create_npc_from_ai({"name": name, "role": role, "location": self.world["location"]})
        npc["inventory"] = []
        return npc

    def steal(self, victim, line=None):
        from unittest.mock import patch
        won = {"result": "BAŞARILI", "skill": "Sleight of Hand"}
        with patch.object(bold_acts, "_check", return_value=won), \
                patch.object(bold_acts, "_hand_to_whom", return_value=victim):
            return bold_acts._steal(self.session, line or self.LINE)

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

    def test_one_showing_makes_one_spear_whoever_is_robbed(self):
        # re-review 2026-11-16: the mark was per person, so four guards gave four spears from one narration
        for name in ("Kavşim", "Arven", "Tolun", "Melis"):
            self.steal(self.person("Muhafız", name))
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)

    def test_a_carried_shown_weapon_taken_once_makes_no_second(self):
        # re-review: the guard's own spear went first, unmarked; the next good roll made a new one
        guard = self.person("Muhafız")
        guard["inventory"] = [{"item_id": "gear_kavsim", "name": "Mızrak", "weapon_id": "spear"}]
        for _ in range(3):
            self.steal(guard)
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)
        self.assertEqual(self.spears(guard["inventory"]), [])

    def test_a_stat_block_foe_gets_no_made_spear(self):
        for key, name in (("statblock", "Yaban"), ("monster_stat_block", "Haydut")):
            with self.subTest(key=key):
                foe = self.person("Muhafız", name)
                foe[key] = {"x": 1}
                self.steal(foe)
                self.assertEqual(self.spears(foe["inventory"]), [])
                self.assertEqual(self.spears(self.world["inventory"]), [])

    def test_the_keeper_of_a_shop_gets_no_made_spear_whatever_the_role(self):
        keeper = self.person("Muhafız")
        self.world.setdefault("shops", []).append({"id": "shop_x", "shopkeeper_id": keeper["id"]})
        self.steal(keeper)
        self.assertEqual(self.spears(keeper["inventory"]), [])
        self.assertEqual(self.spears(self.world["inventory"]), [])

    def test_a_broken_mark_never_crashes_and_a_string_never_counts(self):
        for broken in (None, 5, {"x": 1}, "spear", ["junk", 3, None]):
            with self.subTest(broken=broken):
                self.setUp()
                self.world[bold_acts.SHOWN_GEAR_MADE] = broken
                self.steal(self.person("Muhafız"))
                self.assertEqual(len(self.spears(self.world["inventory"])), 1)
        self.setUp()
        self.steal(self.person("Muhafız"))
        made = self.world[bold_acts.SHOWN_GEAR_MADE]
        self.setUp()
        self.world[bold_acts.SHOWN_GEAR_MADE] = made[0]  # the right key, but a string, not a list
        self.steal(self.person("Muhafız"))
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)

    def test_a_new_narration_of_the_same_place_makes_no_second(self):
        # third review 2026-11-16: the narration's words were in the mark, so a model that described the rack again (one
        # dot more, or "mızrak hâlâ yerinde") made a new spear every turn; one weapon kind per place, ever
        guard = self.person("Muhafız")
        self.steal(guard)
        self.session.recent_dm_narrations.append("kavşim omuz silkiyor; askıdaki mızrak hâlâ yerinde duruyor.")
        self.steal(guard)
        self.session.recent_dm_narrations.append("arven'in sırtında da bir mızrak var.")
        self.steal(self.person("Muhafız", "Arven"))
        self.assertEqual(len(self.spears(self.world["inventory"])), 1)

    def made(self, before):
        """The things the player got beyond the ones held before."""
        return len(self.world["inventory"]) - before

    def test_a_shown_greatsword_gives_one_item_whatever_the_word(self):
        # fourth review: "kılıcı çalıyorum" took a longsword never shown, then "büyük kılıcı" the greatsword too
        self.session.recent_dm_narrations = ["kavşim'in arkasındaki askıda tek bir büyük kılıç asılı."]
        before = len(self.world["inventory"])
        guard = self.person("Muhafız")
        for line in ("askıdaki kılıcı çalıyorum", "askıdaki büyük kılıcı çalıyorum", "askıdaki uzun kılıcı çalıyorum"):
            guard["inventory"] = []  # the guard carries none of their own
            self.steal(guard, line)
        self.assertEqual(self.made(before), 1)

    def test_two_weapons_shown_in_one_place_give_one(self):
        # the cap that holds whatever word the next review finds: one narration-made item per place, ever
        self.session.recent_dm_narrations = ["askıda bir mızrak ile bir pala asılı."]
        before = len(self.world["inventory"])
        self.steal(self.person("Muhafız"), "askıdaki mızrağı çalıyorum")
        self.steal(self.person("Muhafız", "Arven"), "askıdaki palayı çalıyorum")
        self.assertEqual(self.made(before), 1)

    def test_another_place_may_show_its_own(self):
        self.steal(self.person("Muhafız"))
        self.world["location"] = "forest"
        self.session.recent_dm_narrations.append("arven'in sırtında bir mızrak var.")
        self.steal(self.person("Muhafız", "Arven"))
        self.assertEqual(len(self.spears(self.world["inventory"])), 2)

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
