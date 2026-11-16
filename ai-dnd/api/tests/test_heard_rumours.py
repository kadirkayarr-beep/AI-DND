"""Rumour lane core: what an NPC names in speech becomes a heard rumour, never a quest, reward or money."""

from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

import game
import heard_rumours
import local_places
from api.tests.test_world_threads import city

_WORDS = (
    "Karadut", "Aksu", "Demirkaya", "Yeşilvadi", "Sisli", "Kızılçam", "Taşkapı", "Gümüşdere", "Ayaz", "Bozkır",
    "Çatalhöyük", "Dumanlı", "Elmalı", "Fırtına", "Gölgeli", "Hancı", "Işıklı", "Kuzgun", "Lodos", "Mercan",
    "Nehirli", "Ormanlı", "Pusulu", "Rüzgâr", "Sarıkaya", "Tuzlu", "Uçurum", "Vadili", "Yıldız", "Zeybek",
)


def mention(name="Eski Mahzen", place_kind="archive", about="Kuyunun altında", kind="place"):
    return {"kind": kind, "name": name, "place_kind": place_kind, "about": about}


class RumourLane(unittest.TestCase):
    def setUp(self):
        self.world = city("rumour-lane")
        self.world["npcs"] = [
            {"id": "npc_001", "name": "Mira Dalgıç", "public_name": "Mira Dalgıç", "location": "city"},
        ]
        self.npc = self.world["npcs"][0]
        patcher = patch.object(game._DEFAULT_SESSION, "world_state", self.world)
        patcher.start()
        self.addCleanup(patcher.stop)

    def say(self, *args, turn=1, **kwargs):
        return heard_rumours.record_mention(game, self.world, self.npc, mention(*args, **kwargs), turn)

    def rumoured(self):
        return [r for r in self.world["locations"].values() if r.get("rumoured")]

    def test_place_mention_records_rumoured_place_under_current_settlement(self):
        before = len(self.world["locations"])
        entry = self.say()
        self.assertEqual(len(self.world["locations"]), before + 1)
        place = self.world["locations"][entry["place_id"]]
        self.assertIs(place["rumoured"], True)
        self.assertEqual(place["parent_location_id"], "city")
        self.assertEqual(place["name"], "Eski Mahzen")
        self.assertEqual(place["provenance"], {"source": "npc_rumour", "said_by": "npc_001", "turn": 1})
        self.assertEqual([e["place_id"] for e in self.world["heard_rumours"]], [place["id"]])
        self.assertEqual(entry["said_by"], "npc_001")
        self.assertEqual(entry["settlement_id"], "city")

    def test_money_claim_in_about_is_emptied_and_no_money_moves(self):
        self.world["gold"] = 7
        self.world["purse"] = {"gp": 7}
        before = copy.deepcopy({k: self.world[k] for k in ("gold", "purse")})
        entry = self.say(about="İçeride 50 altın var")
        self.assertIsNotNone(entry)
        self.assertNotIn("altın", self.world["locations"][entry["place_id"]]["description"].casefold())
        self.assertNotIn("altın", entry["text"].casefold())
        self.assertEqual({k: self.world[k] for k in ("gold", "purse")}, before)

    def test_figure_and_coin_claims_in_about_empty_it_but_the_place_stays(self):
        self.world["gold"] = 7
        self.world["purse"] = {"gp": 7}
        before = copy.deepcopy({k: self.world[k] for k in ("gold", "purse")})
        for index, about in enumerate(("İçeride 50 gümüş saklı.", "Girişi beş bakır.", "Hazinesi yüz sikke değerinde.")):
            with self.subTest(about=about):
                entry = self.say(name=f"{_WORDS[index]} Mahzeni", about=about)
                self.assertIsNotNone(entry)
                self.assertEqual(entry["text"], f"{_WORDS[index]} Mahzeni")
                place = self.world["locations"][entry["place_id"]]
                self.assertEqual(place["name"], f"{_WORDS[index]} Mahzeni")
                self.assertNotIn(about, place.get("description", ""))
        self.assertEqual({k: self.world[k] for k in ("gold", "purse")}, before)

    def test_a_figure_in_the_place_name_is_a_name_not_a_claim(self):
        entry = self.say(name="Yüz Altın Hanı", place_kind="archive", about="Köşede eski bir han.")
        self.assertEqual(self.world["locations"][entry["place_id"]]["name"], "Yüz Altın Hanı")
        self.assertEqual(entry["text"], "Yüz Altın Hanı: Köşede eski bir han.")

    def test_eviction_spares_places_a_thread_a_resident_or_a_destination_uses(self):
        import world_threads
        for turn in range(1, 25):
            self.say(name=f"{_WORDS[turn]} Mahzeni", turn=turn)
        by_turn = {r["provenance"]["turn"]: r for r in self.rumoured()}
        state = world_threads._new_state()
        state["threads"].append({"settlement_id": "city", "place_id": by_turn[1]["id"], "target_place_id": None})
        self.world[world_threads.KEY] = state
        by_turn[2]["resident_name"] = "Bekçi Alp"
        self.world["flags"]["pending_destination"] = by_turn[3]["id"]
        for turn in (25, 26, 27):
            self.say(name=f"{_WORDS[turn]} Mahzeni", turn=turn)
        for kept in (1, 2, 3):
            self.assertIn(by_turn[kept]["id"], self.world["locations"])
        self.assertNotIn(by_turn[4]["id"], self.world["locations"])
        self.assertNotIn(by_turn[5]["id"], self.world["locations"])
        self.assertEqual(world_threads._used_places(state, "city"), [by_turn[1]["id"]])

    def test_eviction_spares_a_place_an_npc_statement_points_at(self):
        import npc_statements
        for turn in range(1, 25):
            self.say(name=f"{_WORDS[turn]} Mahzeni", turn=turn)
        by_turn = {r["provenance"]["turn"]: r for r in self.rumoured()}
        npc_statements.ensure(self.world)["references"].append(
            {"id": "ref_0001", "kind": "place", "name": by_turn[1]["name"], "said_by": "npc_001",
             "settlement_id": "city", "location_id": by_turn[1]["id"], "status": "resolved"})
        for turn in (25, 26):
            self.say(name=f"{_WORDS[turn]} Mahzeni", turn=turn)
        self.assertIn(by_turn[1]["id"], self.world["locations"])
        self.assertNotIn(by_turn[2]["id"], self.world["locations"])
        self.assertNotIn(by_turn[3]["id"], self.world["locations"])

    def test_nothing_evictable_still_records_the_new_mention(self):
        for turn in range(1, 25):
            self.say(name=f"{_WORDS[turn]} Mahzeni", turn=turn)
        for record in self.rumoured():
            record["resident_name"] = "Bekçi"
        entry = self.say(name=f"{_WORDS[25]} Mahzeni", turn=25)
        self.assertIsNotNone(entry)
        self.assertIn(entry["place_id"], self.world["locations"])
        self.assertEqual(len(self.rumoured()), 25)

    def test_said_in_needs_word_edges(self):
        self.assertFalse(heard_rumours.said_in("Hanımlar toplandı.", "Han"))
        self.assertFalse(heard_rumours.said_in("Kuyucak yakında.", "Kuyu'ya"))
        self.assertTrue(heard_rumours.said_in("Eski Mahzen'e git.", "Eski Mahzen"))
        self.assertTrue(heard_rumours.said_in("Kuyu'ya in.", "Kuyu'ya"))
        self.assertTrue(heard_rumours.said_in("Git, Han.", "Han"))
        self.assertFalse(heard_rumours.said_in("Eski Mahzenin kapısı", "Eski Mahzen"))

    def test_existing_place_name_links_instead_of_creating(self):
        smithy = local_places.create_local_place(self.world, "city", "smithy")
        count = len(self.world["locations"])
        entry = self.say(name=smithy["name"], place_kind="smithy")
        self.assertEqual(len(self.world["locations"]), count)
        self.assertEqual(entry["place_id"], smithy["id"])
        self.assertNotIn("rumoured", smithy)

    def test_said_in_needs_the_folded_name_in_the_folded_text(self):
        self.assertTrue(heard_rumours.said_in("Eski Mahzen'de bir kuyu var.", "Eski Mahzen"))
        self.assertTrue(heard_rumours.said_in("ESKİ MAHZEN yakında.", "Eski Mahzen'de"))
        self.assertFalse(heard_rumours.said_in("Kuzeyde bir yer var.", "Eski Mahzen"))
        self.assertFalse(heard_rumours.said_in("Eski Mahzen", ""))
        self.assertFalse(heard_rumours.said_in(None, "Eski Mahzen"))

    def test_exact_alias_links_and_longer_or_shorter_names_do_not(self):
        smithy = local_places.create_local_place(self.world, "city", "smithy")
        smithy["aliases"] = ["Kızıl Örs"]
        count = len(self.world["locations"])
        self.assertEqual(self.say(name="kızıl örs'te", place_kind="smithy")["place_id"], smithy["id"])
        self.assertEqual(len(self.world["locations"]), count)
        longer = self.say(name=f"{smithy['name']} Mezarlığı", place_kind="graveyard")
        self.assertNotEqual(longer["place_id"], smithy["id"])
        self.assertEqual(len(self.world["locations"]), count + 1)

    def test_25th_rumoured_place_evicts_oldest_unvisited(self):
        for turn in range(1, 25):
            self.assertIsNotNone(self.say(name=f"{_WORDS[turn]} Mahzeni", turn=turn))
        self.assertEqual(len(self.rumoured()), 24)
        first = next(r for r in self.rumoured() if r["provenance"]["turn"] == 1)
        local_places.arrival_parts(self.world, first, None, None, first_visit=True)
        self.assertEqual(len(self.rumoured()), 23)
        self.say(name=f"{_WORDS[25]} Mahzeni", turn=25)
        self.assertEqual(len(self.rumoured()), 24)
        second = next(r for r in self.rumoured() if r["provenance"]["turn"] == 2)
        newest = self.say(name=f"{_WORDS[26]} Mahzeni", turn=26)
        self.assertNotIn(second["id"], self.world["locations"])
        self.assertIn(first["id"], self.world["locations"])
        self.assertIn(newest["place_id"], self.world["locations"])
        self.assertEqual(len(self.rumoured()), 24)
        evicted = [e for e in self.world["heard_rumours"] if e["turn"] == 2]
        self.assertEqual(len(evicted), 1)
        self.assertIsNone(evicted[0]["place_id"])

    def test_full_local_cap_still_records_rumoured_place(self):
        kinds = [k for k, spec in local_places.PLACE_KINDS.items() if not spec.get("outdoors")]
        for kind in kinds[:local_places.MAX_LOCAL_PLACES_PER_SETTLEMENT]:
            self.assertIsNotNone(local_places.create_local_place(self.world, "city", kind))
        entry = self.say(name="Sisli Hamam", place_kind=kinds[-1])
        self.assertIsNotNone(entry["place_id"])
        self.assertTrue(self.world["locations"][entry["place_id"]]["rumoured"])
        self.assertIsNone(local_places.create_local_place(self.world, "city", kinds[-1], name="Başka Yer"))

    def test_rumour_opens_no_thread_quest_or_reward(self):
        self.world.update({"world_threads": {"active": []}, "quests": [], "rewards": []})
        before = copy.deepcopy({k: self.world[k] for k in ("world_threads", "quests", "rewards")})
        self.say()
        self.say(name="Kuzey İzi", kind="trail", place_kind=None, about="Kervanlar o yoldan dönmedi")
        self.assertEqual({k: self.world[k] for k in ("world_threads", "quests", "rewards")}, before)

    def test_first_arrival_realizes_rumoured_place(self):
        entry = self.say()
        record = self.world["locations"][entry["place_id"]]
        local_places.arrival_parts(self.world, record, None, None, first_visit=False)
        self.assertNotIn("rumoured", record)
        self.assertIs(record["visited"], True)

    def test_person_name_is_not_a_place(self):
        before = copy.deepcopy(self.world)
        self.assertIsNone(self.say(name="Mira Dalgıç'a", place_kind="smithy"))
        self.assertEqual(self.world, before)

    def test_suffix_is_stripped_from_name(self):
        entry = self.say(name="Eski Mahzen'de")
        self.assertEqual(self.world["locations"][entry["place_id"]]["name"], "Eski Mahzen")
        self.assertEqual(heard_rumours.base_name("Eski Mahzen’e gittim"), "Eski Mahzen gittim")

    def test_repeated_mention_is_one_place_one_rumour(self):
        first = self.say(turn=1)
        count = len(self.world["locations"])
        again = self.say(name="Eski Mahzen'in", turn=2)
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(len(self.world["locations"]), count)
        self.assertEqual(len(self.world["heard_rumours"]), 1)

    def test_bad_names_and_kinds_are_rejected_silently(self):
        cases = {
            "empty": mention(name=""),
            "blank": mention(name="   "),
            "too long": mention(name="A" * 61),
            "bad place_kind": mention(place_kind="castle"),
            "bad kind": mention(kind="npc"),
            "not a dict": "Eski Mahzen",
            "name not text": {"kind": "place", "name": 5, "place_kind": "archive"},
        }
        before = copy.deepcopy(self.world)
        for label, bad in cases.items():
            with self.subTest(label):
                self.assertIsNone(heard_rumours.record_mention(game, self.world, self.npc, bad, 1))
        self.assertEqual(self.world, before)

    def test_trail_records_text_only(self):
        count = len(self.world["locations"])
        entry = self.say(name="Kuzey İzi", kind="trail", place_kind=None, about="Kervanlar dönmedi")
        self.assertIsNone(entry["place_id"])
        self.assertEqual(len(self.world["locations"]), count)
        self.assertEqual(entry["text"], "Kuzey İzi: Kervanlar dönmedi")

    def test_lane_off_records_nothing(self):
        before = copy.deepcopy(self.world)
        for value in ("0", "off", " OFF "):
            with self.subTest(value), patch.dict(os.environ, {"AI_DND_RUMOUR_LANE": value}):
                self.assertFalse(heard_rumours.lane_enabled())
                self.assertIsNone(self.say())
        self.assertEqual(self.world, before)
        self.assertTrue(heard_rumours.lane_enabled())

    def test_list_is_trimmed_to_max_heard(self):
        for turn in range(heard_rumours.MAX_HEARD + 5):
            self.say(name=f"Yol {turn:03d}", kind="trail", place_kind=None, turn=turn)
        self.assertEqual(len(self.world["heard_rumours"]), heard_rumours.MAX_HEARD)
        ids = [e["id"] for e in self.world["heard_rumours"]]
        self.assertEqual(len(set(ids)), len(ids))

    def test_new_world_has_an_empty_rumour_list(self):
        self.assertEqual(game.INITIAL_WORLD_STATE["heard_rumours"], [])


if __name__ == "__main__":
    unittest.main()
