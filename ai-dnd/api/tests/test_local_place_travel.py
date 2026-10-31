"""An unknown local place in a city can be reached through a validated create_locations proposal."""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import game
import timed_gameplay
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_free_attempts import NarratingClient

GO = "Şehrin en zengin mahallesine gidiyorum."
REFERENCE = "Şehrin en zengin mahallesi"
PLACE = {"proposal_key": "l1", "name": REFERENCE, "type": "district",
         "description": "Taş konakların sıralandığı sakin bir semt.", "aliases": []}


class TravellingClient(NarratingClient):
    def __init__(self, updates=None, reference=REFERENCE, **kwargs):
        super().__init__(narration="Geniş sokaklarda yürüyorsun; taş konaklar sıralanıyor.", **kwargs)
        self.updates, self.reference = updates or {}, reference

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties", {})
        answer = super().chat(*args, **kwargs)
        if "intent" in properties:
            return {"message": {"content": json.dumps({
                "intent": "travel", "action": "travel",
                "target": {"type": "location", "reference": self.reference},
                "completion": "completed", "confidence": 1.0,
            }, ensure_ascii=False)}}
        if "narration" in properties:
            body = json.loads(answer["message"]["content"])
            body["world_updates"] = self.updates
            return {"message": {"content": json.dumps(body, ensure_ascii=False)}}
        return answer


class LocalPlaceTravelTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def scene(self):
        self.city, _, self.session, self.turn_url, _ = await self.campaign_with_npc(experimental=False)
        self.world = self.session.world_state
        self.before = copy.deepcopy(self.world["locations"])

    async def go(self, client, message=GO):
        # A road encounter is a separate rule; these tests are about reaching the place.
        with patch.object(timed_gameplay, "travel_dice", return_value=(None, {"occurrence": 6, "type": None, "disposition": None})):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, self.turn_url, client, {"message": message, "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def new_places(self):
        return [record for key, record in self.world["locations"].items() if key not in self.before]

    async def test_a_plausible_place_is_created_and_reached(self):
        await self.scene()
        result = await self.go(TravellingClient({"create_locations": [PLACE]}))
        places = self.new_places()
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["name"], REFERENCE)
        self.assertEqual(places[0]["parent_location_id"], self.city)
        self.assertEqual(places[0]["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertRegex(places[0]["id"], r"^location_\d+$")
        self.assertEqual(self.world["location"], places[0]["id"], (result["narration"], self.world.get("journey"), self.session.last_narration_safety))
        self.assertIn("taş konaklar", result["narration"], self.session.last_narration_safety)

    async def test_python_keeps_the_players_words_as_the_name(self):
        await self.scene()
        await self.go(TravellingClient({"create_locations": [{**PLACE, "name": "Altın Konaklar", "id": "forged"}]}))
        self.assertEqual([place["name"] for place in self.new_places()], [REFERENCE])

    async def test_a_part_of_the_city_may_be_called_a_bolge(self):
        await self.scene()
        await self.go(TravellingClient({"create_locations": [{**PLACE, "name": "Zengin Mahalle", "type": "Bölge"}]}))
        places = self.new_places()
        self.assertEqual([place["name"] for place in places], [REFERENCE])
        self.assertIn("Zengin Mahalle", places[0]["aliases"])
        self.assertTrue(game.living_world.on_open_street(self.world))

    async def test_a_new_district_reads_as_street_for_later_turns(self):
        await self.scene()
        await self.go(TravellingClient({"create_locations": [PLACE]}))
        self.assertTrue(game.living_world.on_open_street(self.world))

    async def test_a_road_encounter_keeps_the_player_and_drops_the_arrival_text(self):
        await self.scene()
        class LowDice:
            def randint(self, low, high):
                return low

        real_dice = timed_gameplay.travel_dice
        client = TravellingClient({"create_locations": [PLACE]})
        with patch.object(timed_gameplay, "travel_dice", side_effect=lambda rng, recent: real_dice(LowDice(), recent)):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, self.turn_url, client, {"message": GO, "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertEqual(self.world["location"], self.city)
        self.assertIn(timed_gameplay.TRAVEL_CATALOG[0]["text"], shown)
        self.assertNotIn("taş konaklar", shown)

    async def test_a_far_place_is_a_plausible_failure_not_a_new_city(self):
        await self.scene()
        client = TravellingClient({"create_locations": [{**PLACE, "name": "Uzak Çöl", "type": "wilderness"}]}, reference="Uzak Çöl")
        result = await self.go(client, "Uzak Çöl'e gidiyorum.")
        self.assertEqual(self.new_places(), [])
        self.assertEqual(self.world["location"], self.city)
        self.assertIn("olduğun yerdesin", result["narration"])

    async def test_no_proposal_stays_a_plausible_failure(self):
        await self.scene()
        result = await self.go(TravellingClient())
        self.assertEqual(self.new_places(), [])
        self.assertEqual(self.world["location"], self.city)
        self.assertIn("olduğun yerdesin", result["narration"])

    async def test_only_the_place_is_taken_from_the_packet(self):
        await self.scene()
        npcs, features = copy.deepcopy(self.world["npcs"]), copy.deepcopy(self.world["features"])
        await self.go(TravellingClient({
            "create_locations": [PLACE],
            "create_npcs": [{"name": "Model Kişi", "location": self.city}],
            "create_features": [{"name": "Model Ayrıntı", "location": self.city}],
        }))
        self.assertNotIn("Model Kişi", [npc["name"] for npc in self.world["npcs"]])
        self.assertEqual(self.world["features"], features)
        self.assertTrue({npc["id"] for npc in npcs} <= {npc["id"] for npc in self.world["npcs"]})

    async def test_inside_a_room_the_narrator_cannot_create_a_place(self):
        await self.scene()
        self.world["locations"][self.city]["scene_kind"] = "tavern"
        await self.go(TravellingClient({"create_locations": [PLACE]}))
        self.assertEqual(self.new_places(), [])


if __name__ == "__main__":
    unittest.main()
