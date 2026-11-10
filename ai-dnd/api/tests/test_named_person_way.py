"""Dilim 3 Task 24: the way to a person someone named.

A job line that names a contact says where they are; "Özpil'in dükkanına gidiyorum" goes to the place Özpil
lives in (no new shop is made); "Özpil nerede?" and a Konuş line with nobody to talk to read where the town
says that person is; a hint given inside a building says the player is inside it, not in its streets.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import game
import grounded_action
import local_places
import thread_catalog
import world_threads
from api.tests.journeys.runner import _give_job
from api.tests.test_three_plays import PlayClient, ThreePlaysTests


class ContactLineTests(unittest.TestCase):
    def test_a_job_line_that_names_a_contact_says_where_they_are(self):
        lines = [line for template in thread_catalog.load() for line in template["owner_lines"]
                 if "{recipient} ile konuş" in line]
        self.assertTrue(lines, "the catalog has no contact line: the case went untested")
        for line in lines:
            self.assertIn("{target}", line)


class PlaceHintTests(unittest.TestCase):
    def world(self, here):
        return {
            "location": here,
            "locations": {
                "city": {"name": "Neverwinter", "type": "city"},
                "inn": {"name": "Kızıl Han", "parent_location_id": "city", "scene_kind": "tavern"},
                "estate": {"name": "Kelmaren Konağı", "parent_location_id": "city", "place_kind": "estate"},
            },
            "doors": [],
        }

    def test_inside_a_building_the_hint_says_inside(self):
        text = grounded_action.place_hint(SimpleNamespace(world_state=self.world("inn")), "estate")
        self.assertIn("Kızıl Han içindesin", text)
        self.assertNotIn("sokaklarında", text)

    def test_in_the_street_the_hint_still_says_streets(self):
        text = grounded_action.place_hint(SimpleNamespace(world_state=self.world("city")), "estate")
        self.assertIn("Neverwinter sokaklarındasın", text)


class NamedPersonWayTests(ThreePlaysTests):
    async def town(self):
        await self.begin()  # ThreePlaysTests.begin fixes the town (test_three_plays.TOWN_SEED)
        self.settlement = self.world["location"]
        here = self.settlement
        self.world["npcs"] = [npc for npc in self.world.get("npcs", []) if npc.get("location") != here]

    async def town_with_errand(self):
        """Vobarin's errand names Özpil, who lives in an estate of the town."""
        await self.town()
        self.add_person("Vobarin", "Çömlekçi")
        _give_job(self.world, {"type": "errand", "owner": "npc_vobarin", "status": "offered", "pay": 12,
                               "noun": "iade takımı", "recipient": "Özpil", "target_kind": "estate",
                               "line": "İade takımını Özpil'e götür. On iki bakır."})
        thread = world_threads.view(self.world)["threads"][0]
        self.estate = self.world["locations"][thread["target_place_id"]]

    async def test_going_to_a_named_persons_shop_goes_where_they_live(self):
        await self.town()
        # One person of this name in town: the fixed town's own workshop already has an Özpil, and two places of one
        # resident name are rightly asked about, so this estate's resident has a name nobody else in town has.
        self.assertNotIn("Orsela", [place.get("resident_name") for place in self.world["locations"].values()])
        estate = local_places.create_local_place(self.world, self.settlement, "estate", name="Kelmaren Konağı")
        estate["resident_name"] = "Orsela"
        estate.setdefault("aliases", []).append("Orsela")
        before = set(self.world["locations"])
        out = await self.say("orselanın dükkanına gidiyorum")
        self.assertEqual(self.world["location"], estate["id"], out["narration"])
        # The estate's own inner hall opens on the first visit; nothing else (no shop) is made.
        new = [self.world["locations"][key] for key in set(self.world["locations"]) - before]
        self.assertEqual([place for place in new if place.get("inner_of") != estate["id"]], [])

    async def test_two_places_of_one_name_are_told_apart_by_the_kind_said(self):
        """Task 29: the 'which one' question only when the words leave it open."""
        await self.town()
        self.assertNotIn("Orsela", [place.get("resident_name") for place in self.world["locations"].values()])
        estate = local_places.create_local_place(self.world, self.settlement, "estate", name="Kelmaren Konağı")
        workshop = local_places.create_local_place(self.world, self.settlement, "workshop", name="Ozan Tezgâhı")
        estate["resident_name"] = workshop["resident_name"] = "Orsela"
        step = grounded_action.plan(self.session, "orselanın konağına gidiyorum")["steps"][0]
        self.assertEqual((step["target"] or {}).get("id"), estate["id"], step["ambiguous"])
        self.assertEqual(step["ambiguous"], [])
        # Task 41 (owner vocabulary, 2026-11-10): a "dükkân" is a workshop-type place or a market stall, never an
        # estate: it picks the workshop.
        for line in ("orselanın dükkanına gidiyorum", "Orsela'nın dükkânına gidiyorum"):
            with self.subTest(line=line):
                step = grounded_action.plan(self.session, line)["steps"][0]
                self.assertEqual((step["target"] or {}).get("id"), workshop["id"], step["ambiguous"])
                self.assertEqual(step["ambiguous"], [])
        # The words name no kind of either place: both are still offered.
        step = grounded_action.plan(self.session, "orselaya gidiyorum")["steps"][0]
        self.assertIsNone(step["target"])
        self.assertEqual({cand["id"] for cand in step["ambiguous"]}, {estate["id"], workshop["id"]})
        # Two places of the dükkân kinds: the word cannot pick one, so it is still asked.
        stall = local_places.create_local_place(self.world, self.settlement, "market", name="Ozan Pazarı")
        stall["resident_name"] = "Orsela"
        step = grounded_action.plan(self.session, "orselanın dükkanına gidiyorum")["steps"][0]
        self.assertIsNone(step["target"])
        # Task 41 review M1: "dükkân" is never an estate, so only the two shops are offered.
        self.assertEqual({cand["id"] for cand in step["ambiguous"]}, {workshop["id"], stall["id"]})

    async def test_asked_of_someone_here_where_a_named_person_is_the_town_tells_them(self):
        """Task 29: the person asked hears, as engine data, where the town says the named person is."""
        await self.town_with_errand()
        heard = []

        class Listening(PlayClient):
            def chat(self, *args, **kwargs):
                if "spoken_text" in ((kwargs.get("format") or {}).get("properties") or {}):
                    heard.append(str(kwargs.get("messages")))
                return super().chat(*args, **kwargs)

        self.world["npcs"] = [npc for npc in self.world["npcs"] if npc["id"] != "npc_vobarin"]
        self.add_person("Hedda", "Seyyar satıcı")  # a bystander: Özpil's job is not hers
        await self.say("Hedda, Özpil nerede?", client=Listening(spoken="Bilmem, sor bakalım."), mode="say")
        self.assertTrue(heard, "Hedda was not asked")
        self.assertIn(f"Özpil, {self.estate['name']} tarafında bulunur", heard[-1])

    async def test_a_person_not_named_brings_no_place_into_the_ask(self):
        await self.town_with_errand()
        heard = []

        class Listening(PlayClient):
            def chat(self, *args, **kwargs):
                if "spoken_text" in ((kwargs.get("format") or {}).get("properties") or {}):
                    heard.append(str(kwargs.get("messages")))
                return super().chat(*args, **kwargs)

        self.world["npcs"] = [npc for npc in self.world["npcs"] if npc["id"] != "npc_vobarin"]
        self.add_person("Hedda", "Seyyar satıcı")
        await self.say("Hedda, bugün hava nasıl?", client=Listening(spoken="Serin."), mode="say")
        self.assertTrue(heard, "Hedda was not asked")
        self.assertNotIn(f"{self.estate['name']} tarafında bulunur", heard[-1])

    async def test_a_resident_standing_here_is_the_person_not_their_place(self):
        await self.town()
        estate = local_places.create_local_place(self.world, self.settlement, "estate", name="Kelmaren Konağı")
        estate["resident_name"] = "Özpil"
        person = self.add_person("Özpil", "Kâhya")
        with patch.object(game, "active_npcs", return_value=[person]):
            step = grounded_action.plan(self.session, "Özpil'e yaklaşıyorum")["steps"][0]
        self.assertEqual((step["target"] or {}).get("id"), person["id"], step["ambiguous"])

    async def test_a_resident_name_is_not_guessed_from_a_near_word(self):
        await self.town()
        estate = local_places.create_local_place(self.world, self.settlement, "estate", name="Kelmaren Konağı")
        estate["resident_name"] = "Tamar"
        step = grounded_action.plan(self.session, "tamam, oraya gidiyorum")["steps"][0]
        self.assertNotEqual((step["target"] or {}).get("id"), estate["id"])
        self.assertFalse(step["named"])

    async def test_a_resident_name_is_not_the_start_of_another_word(self):
        await self.town()
        for resident, line in (("Yara", "yaralı adama yaklaşıyorum"), ("Pip", "pipolu adama yaklaşıyorum")):
            with self.subTest(resident=resident):
                estate = local_places.create_local_place(self.world, self.settlement, "estate")
                estate["resident_name"] = resident
                step = grounded_action.plan(self.session, line)["steps"][0]
                self.assertNotEqual((step["target"] or {}).get("id"), estate["id"])
                self.assertFalse(step["named"])
                estate["resident_name"] = None

    async def test_someone_standing_here_unintroduced_is_not_elsewhere(self):
        await self.town_with_errand()
        person = self.add_person("Özpil", "Kâhya", name_known_to_player=False)
        with patch.object(game, "active_npcs", return_value=[person]):
            self.assertIsNone(game._named_elsewhere_line(self.world, "Özpil nerede?"))

    async def test_inside_their_place_the_person_is_not_sent_there(self):
        await self.town_with_errand()
        with patch.object(game, "active_npcs", return_value=[]):
            self.assertIsNotNone(game._named_elsewhere_line(self.world, "Özpil nerede?"))
            self.world["location"] = self.estate["id"]
            self.assertIsNone(game._named_elsewhere_line(self.world, "Özpil nerede?"))
            self.world["locations"]["test_hall"] = {"id": "test_hall", "name": "Salon",
                                                    "parent_location_id": self.estate["id"]}
            self.world["location"] = "test_hall"
            self.assertIsNone(game._named_elsewhere_line(self.world, "Özpil nerede?"))

    async def test_where_is_a_named_person_reads_the_town(self):
        await self.town_with_errand()
        self.world["npcs"] = [npc for npc in self.world["npcs"] if npc["id"] != "npc_vobarin"]
        out = await self.say("Özpil nerede?")
        self.assertIn(f"Özpil burada değil; {self.estate['name']} tarafında", out["narration"])

    async def test_talk_with_nobody_here_reads_where_the_named_person_is(self):
        await self.town_with_errand()
        self.world["npcs"] = [npc for npc in self.world["npcs"] if npc["id"] != "npc_vobarin"]
        out = await self.say("Özpil'i arıyorum, onunla konuşmam lazım", mode="say")
        self.assertIn(f"Özpil burada değil; {self.estate['name']} tarafında", out["narration"])

    async def test_talk_with_nobody_here_says_nobody_is_here(self):
        await self.town()
        out = await self.say("merhaba, kimse var mı?", mode="say")
        self.assertNotIn("Kiminle konuşmak istiyorsun?", out["narration"])
        self.assertIn("kimse", out["narration"])


if __name__ == "__main__":
    unittest.main()
