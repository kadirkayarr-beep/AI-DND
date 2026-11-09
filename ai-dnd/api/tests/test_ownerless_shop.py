"""Dilim 3 Task 25: a shop with no one in it, and words with no one to say them.

A shop the engine makes has an owner the engine names (the person is the engine's, not the model's); a removed
sentence never cuts a quoted line in half, and a line left with only a closing quote nobody opened is dropped;
a registered person who is not here does not speak here: the one who is here speaks, by what can be seen of them.
"""

import unittest
from unittest.mock import patch

import game
import grounded_action
import local_places
from api.tests.journeys.runner import _campaign_seeded
from api.tests.test_three_plays import ThreePlaysTests


class ShopOwnerTests(ThreePlaysTests):
    async def town(self):
        with _campaign_seeded({"campaign_seed": 2400}):
            await self.begin()
        self.settlement = self.world["location"]
        self.world["npcs"] = [npc for npc in self.world.get("npcs", []) if npc.get("location") != self.settlement]

    def shop(self, name="Kavaf Dükkânı"):
        run = grounded_action._Run(self.session, "")
        return grounded_action._create_venue(run, self.settlement, name=name, kind="generic", noun="dukkan",
                                             provenance={"source": "test"})

    async def test_a_shop_the_engine_makes_has_its_owner_in_it(self):
        await self.town()
        record = self.shop()
        self.assertTrue(record.get("resident_name"), record)
        self.assertIn(record["resident_name"], record["aliases"])
        owners = [npc for npc in self.world["npcs"] if npc.get("place_role_of") == record["id"]]
        self.assertEqual([(npc["name"], npc["location"]) for npc in owners], [(record["resident_name"], record["id"])])

    async def test_a_store_room_reserves_no_one(self):
        await self.town()
        run = grounded_action._Run(self.session, "")
        record = grounded_action._create_venue(run, self.settlement, name="Eski Depo", kind="generic",
                                               noun="depo", provenance={"source": "test"})
        self.assertFalse(record.get("resident_name"))
        self.assertEqual([npc for npc in self.world["npcs"] if npc.get("location") == record["id"]], [])

    async def test_walking_in_the_owner_is_there(self):
        await self.town()
        record = self.shop()
        with patch.object(grounded_action, "_campaign_hour", return_value=12):
            out = await self.say("Kavaf Dükkânı'na giriyorum")
        self.assertEqual(self.world["location"], record["id"], out["narration"])
        owners = [npc for npc in self.world["npcs"] if npc.get("place_role_of") == record["id"]]
        self.assertEqual([npc["name"] for npc in owners], [record["resident_name"]], out["narration"])
        self.assertEqual(owners[0]["location"], record["id"])
        self.assertNotIn("İçerisi sessiz", out["narration"])

    async def test_the_owners_name_leads_to_the_shop(self):
        """Task 24: a place's resident name is one of its names ("X'in dükkanına")."""
        await self.town()
        record = self.shop()
        with patch.object(grounded_action, "_campaign_hour", return_value=12):
            out = await self.say(f"{record['resident_name']}'in dükkanına gidiyorum")
        self.assertEqual(self.world["location"], record["id"], out["narration"])


class SentenceRemovalTests(unittest.TestCase):
    def test_a_removed_sentence_takes_its_whole_quoted_line(self):
        text = "Fırın sıcak. Nissa der ki: 'Kapı açık. Brom burada.'"
        repaired = game._remove_trigger_sentence(text, {"reason_code": "UNREGISTERED_NAMED_ENTITY",
                                                        "trigger_span": "Brom"})
        self.assertEqual(repaired, "Fırın sıcak.")

    def test_only_an_unopened_quote_left_is_nothing_left(self):
        text = "Brom kapıda durur. O zaman rahat nefes alırız.'"
        repaired = game._remove_trigger_sentence(text, {"reason_code": "UNREGISTERED_NAMED_ENTITY",
                                                        "trigger_span": "Brom"})
        self.assertFalse(repaired)
        self.assertEqual(game._trim_dangling_quote("Yalnızca bir cümle.'"), "")


class UnseenSpeakerTests(unittest.TestCase):
    def world(self):
        return {
            "location": "shop",
            "locations": {
                "city": {"name": "Neverwinter", "type": "city"},
                "shop": {"name": "Kavaf Dükkânı", "parent_location_id": "city", "resident_name": "Berk"},
                "estate": {"name": "Kelmaren Konağı", "parent_location_id": "city", "place_kind": "estate",
                           "resident_name": "Özpil", "aliases": ["konak", "Kelmaren Konağı", "Özpil"]},
                "inn": {"name": "Kızıl Han", "parent_location_id": "city", "scene_kind": "tavern"},
            },
            "npcs": [
                {"id": "npc_berk", "name": "Berk", "role": "Dükkâncı", "location": "shop",
                 "role_known_to_player": True, "name_known_to_player": False, "status": "active"},
                {"id": "npc_marek", "name": "Marek", "role": "Barmen", "location": "inn", "status": "active"},
            ],
        }

    def repair(self, text, world=None, target=None):
        world = world or self.world()
        return game._unseen_speaker_repaired(text, world, target)

    def test_a_reserved_name_speaking_here_is_the_one_who_is_here(self):
        repaired = self.repair("Özpil, “Hoş geldin, yolcu.” der.")
        self.assertNotIn("Özpil", repaired)
        self.assertTrue(repaired.startswith("Bir dükkâncı, “Hoş geldin, yolcu.”"), repaired)

    def test_a_person_elsewhere_approaching_is_the_one_who_is_here(self):
        repaired = self.repair("Tezgâhın ardında Marek yaklaşır.")
        self.assertEqual(repaired, "Tezgâhın ardında bir dükkâncı yaklaşır.")

    def test_a_name_said_inside_speech_is_only_a_mention(self):
        text = "Bir dükkâncı: “Özpil konakta olur, Marek sana bir iş verir.”"
        self.assertEqual(self.repair(text), text)

    def test_introducing_oneself_by_someone_elses_name_is_dropped(self):
        repaired = self.repair("Bir dükkâncı gülümser: “Ben Özpil. Ne lazım?”")
        self.assertEqual(repaired, "Bir dükkâncı gülümser: “Ne lazım?”")

    def test_with_no_one_here_nothing_is_rewritten(self):
        world = self.world()
        world["npcs"] = [npc for npc in world["npcs"] if npc["id"] != "npc_berk"]
        text = "Özpil, “Hoş geldin.” der."
        self.assertEqual(self.repair(text, world), text)

    def test_the_person_who_is_here_keeps_their_name(self):
        world = self.world()
        world["npcs"][0]["name_known_to_player"] = True
        text = "Berk, “Hoş geldin.” der."
        self.assertEqual(self.repair(text, world), text)


class UnseenNameCheckTests(unittest.TestCase):
    def setUp(self):
        self.session = game.GameSession()
        self.session.character["name"] = "Tester"
        token = game._ACTIVE_SESSION.set(self.session)
        self.addCleanup(game._ACTIVE_SESSION.reset, token)
        world = self.session.world_state
        world["locations"]["estate"] = {"name": "Kelmaren Konağı", "place_kind": "estate", "resident_name": "Özpil",
                                        "aliases": ["konak", "Kelmaren Konağı", "Özpil"]}
        world["npcs"].append({"id": "npc_marek", "name": "Marek", "role": "Barmen", "location": "estate",
                              "status": "active", "combat_status": "active", "current_hp": 8})

    def decide(self, text):
        return game._narration_safety_decision(text, "merhaba", None, {"action": "narrative"})

    def test_the_check_does_not_take_a_registered_name_elsewhere_as_a_speaker(self):
        decision = self.decide("Marek, “Hoş geldin, yolcu.”")
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(decision["trigger_span"], "Marek", decision)

    def test_the_check_does_not_take_a_reserved_name_as_a_speaker(self):
        decision = self.decide("Özpil, “Hoş geldin, yolcu.”")
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(decision["trigger_span"], "Özpil", decision)

    def test_a_registered_name_inside_speech_is_a_mention(self):
        for name in ("Marek", "Özpil"):
            with self.subTest(name=name):
                decision = self.decide(f"Sokak sakin. Bir satıcı: “{name} sana bir iş verir.”")
                self.assertNotEqual(decision.get("trigger_span"), name, decision)


if __name__ == "__main__":
    unittest.main()
