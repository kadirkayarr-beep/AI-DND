"""Safety net: a place an NPC named aloud (no `mentions` record) becomes a real place when the player follows it."""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import heard_rumours
import local_dialogue
import local_places
import timed_gameplay
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_local_place_travel import TravellingClient

SPOKEN = "Kuzeyde Eski Mahzen diye bir yer varmış, öyle duydum."
NAME = "Eski Mahzen"
GO = "Eski Mahzen'e gidiyorum."
PLACE = {"proposal_key": "l1", "name": NAME, "type": "building",
         "description": "Kuyunun altında kalmış eski bir depo.", "aliases": []}


class HeardInSpeech(unittest.TestCase):
    def world(self, location="city_a", *, said=SPOKEN):
        world = {
            "locations": {"city_a": {"id": "city_a", "name": "A", "type": "city", "scene_kind": "city"},
                          "city_b": {"id": "city_b", "name": "B", "type": "city", "scene_kind": "city"}},
            "npcs": [{"id": "npc_x", "name": "Edric", "location": location}],
        }
        local_dialogue.remember_speech_exchange(world, "npc_x", "Ne var?", said)
        return world

    def test_returns_the_speaking_npc(self):
        self.assertEqual(heard_rumours.heard_in_speech(self.world(), "city_a", NAME), "npc_x")

    def test_the_turkish_suffix_on_the_reference_does_not_matter(self):
        self.assertEqual(heard_rumours.heard_in_speech(self.world(), "city_a", "Eski Mahzen'e"), "npc_x")

    def test_another_settlement_does_not_count(self):
        self.assertIsNone(heard_rumours.heard_in_speech(self.world("city_b"), "city_a", NAME))

    def test_a_name_nobody_said_is_none(self):
        self.assertIsNone(heard_rumours.heard_in_speech(self.world(), "city_a", "Kara Kule"))

    def test_bad_input_is_none(self):
        self.assertIsNone(heard_rumours.heard_in_speech({"npc_speech_log": "x"}, "city_a", NAME))
        self.assertIsNone(heard_rumours.heard_in_speech(self.world(), "city_a", None))
        self.assertIsNone(heard_rumours.heard_in_speech(self.world(), "", NAME))

    def test_the_lane_switch_turns_it_off(self):
        with patch.dict("os.environ", {"AI_DND_RUMOUR_LANE": "off"}):
            self.assertIsNone(heard_rumours.heard_in_speech(self.world(), "city_a", NAME))


class FollowTheName(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def scene(self, said=SPOKEN):
        self.city, _, self.session, self.turn_url, _ = await self.campaign_with_npc(experimental=False)
        self.world = self.session.world_state
        # Indoors: the narrator may not propose a place on its own here.
        self.start = self.world["location"] = local_places.create_local_place(self.world, self.city, "smithy")["id"]
        npc = next(item for item in self.world["npcs"] if item.get("location") == self.city)
        local_dialogue.remember_speech_exchange(self.world, npc["id"], "Duyduğun bir şey var mı?", said)
        self.npc_id = npc["id"]
        self.before = copy.deepcopy(self.world["locations"])

    async def go(self, client, message=GO):
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {"occurrence": 6, "type": None, "disposition": None})):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, self.turn_url, client, {"message": message, "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def new_places(self):
        return [record for key, record in self.world["locations"].items() if key not in self.before]

    async def test_unrecorded_name_said_by_npc_becomes_a_place_when_followed(self):
        await self.scene()
        await self.go(TravellingClient({"create_locations": [PLACE]}, reference=NAME))
        places = self.new_places()
        self.assertEqual(len(places), 1)
        place = places[0]
        self.assertEqual(place["name"], NAME)
        self.assertEqual(place["parent_location_id"], self.city)
        self.assertNotIn("rumoured", place)
        self.assertEqual(place["provenance"], {"source": "npc_rumour", "said_by": self.npc_id,
                                               "turn": place["provenance"]["turn"]})
        self.assertIsInstance(place["provenance"]["turn"], int)
        self.assertEqual(self.world["location"], place["id"])

    async def test_a_reference_with_a_suffix_still_names_the_place_without_it(self):
        await self.scene()
        await self.go(TravellingClient({"create_locations": [PLACE]}, reference="Eski Mahzen'e"))
        places = self.new_places()
        self.assertEqual([place["name"] for place in places], [NAME])
        self.assertEqual(places[0]["provenance"]["source"], "npc_rumour")
        self.assertEqual(self.world["location"], places[0]["id"])

    async def test_name_nobody_said_keeps_todays_behaviour(self):
        await self.scene(said="Kuzeyde bir yer varmış, öyle duydum.")
        result = await self.go(TravellingClient({"create_locations": [PLACE]}, reference=NAME))
        self.assertEqual(self.new_places(), [])
        self.assertEqual(self.world["location"], self.start)
        self.assertIn("olduğun yerdesin", result["narration"])

    async def test_speech_in_another_settlement_does_not_count(self):
        await self.scene()
        self.world["locations"]["city_far"] = {"id": "city_far", "name": "Uzak Şehir", "type": "city",
                                               "scene_kind": "city"}
        next(item for item in self.world["npcs"] if item["id"] == self.npc_id)["location"] = "city_far"
        self.before = copy.deepcopy(self.world["locations"])
        await self.go(TravellingClient({"create_locations": [PLACE]}, reference=NAME))
        self.assertEqual(self.new_places(), [])
        self.assertEqual(self.world["location"], self.start)


if __name__ == "__main__":
    unittest.main()
