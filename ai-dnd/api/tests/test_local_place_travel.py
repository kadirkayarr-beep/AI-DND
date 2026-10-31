"""An unknown local place in a city can be reached through a validated create_locations proposal."""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import game
import local_places
import timed_gameplay
from api import world_metadata
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

    async def test_a_district_the_model_gave_an_odd_type_is_still_a_street(self):
        # The real model wrote "Lüks Konut Bölgesi", which fell to "other": no street wording, environment=unknown.
        await self.scene()
        await self.go(TravellingClient({"create_locations": [{**PLACE, "type": "Lüks Konut Bölgesi"}]}))
        place = self.new_places()[0]
        self.assertEqual(place["scene_kind"], "city")
        self.assertTrue(game.living_world.on_open_street(self.world))
        self.assertEqual(local_places.settlement_of(self.world, place["id"]), self.city)
        self.assertIn("sokaklarında", game.living_world.place_in_plain_words(self.world))

    async def test_a_district_answers_for_the_city_environment(self):
        await self.scene()
        await self.go(TravellingClient({"create_locations": [PLACE]}))
        self.assertEqual(world_metadata.infer_environment(self.world), "city")

    async def test_a_named_building_is_a_building_not_a_street(self):
        await self.scene()
        reference = "Kuzey Kemeri"
        await self.go(
            TravellingClient({"create_locations": [{**PLACE, "name": reference, "type": "Taş Kemer"}]}, reference=reference),
            "Kuzey Kemeri'ne gidiyorum.",
        )
        place = self.new_places()[0]
        self.assertEqual(place["scene_kind"], "building")
        self.assertEqual(self.world["location"], place["id"])
        self.assertFalse(game.living_world.on_open_street(self.world))

    async def test_a_new_district_reads_as_street_for_later_turns(self):
        await self.scene()
        await self.go(TravellingClient({"create_locations": [PLACE]}))
        self.assertTrue(game.living_world.on_open_street(self.world))

    async def test_a_short_walk_inside_the_city_meets_no_road_encounter(self):
        await self.scene()
        client = TravellingClient({"create_locations": [PLACE]})
        with patch.object(timed_gameplay, "travel_dice", side_effect=AssertionError("no roll on a local walk")):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, self.turn_url, client, {"message": GO, "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.world["location"], self.new_places()[0]["id"])
        self.assertEqual(self.world["journey"]["status"], "ARRIVED")

    async def test_a_walk_stopped_on_the_way_keeps_the_player_and_drops_the_arrival_text(self):
        # The road dice no longer reach this walk, which this test used; a scheduled event still can stop it.
        await self.scene()
        client = TravellingClient({"create_locations": [PLACE]})
        stopped = lambda session: timed_gameplay._result("travel", "Yolda karar vermen gereken bir durum oluştu.", status="interrupted")
        with patch.object(timed_gameplay, "continue_travel", side_effect=stopped):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, self.turn_url, client, {"message": GO, "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["narration"]
        self.assertEqual(self.world["location"], self.city)
        self.assertIn("durum oluştu", shown)
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


ENCOUNTER = {"pattern": "wagon", "text": "Yol kenarında yükünü düzenleyen bir arabacı var.", "disposition": "sakin",
             "dice": {"occurrence": 1, "type": 2, "disposition": 1}}
NO_ENCOUNTER = (None, {"occurrence": 6, "type": None, "disposition": None})


class RealJourneyTests(unittest.TestCase):
    """The road dice stay on real journeys, and the player can always go on after one."""

    def setUp(self):
        self.session = game.create_session(seed=11)
        self.session.commit_location_change("tavern")
        self.world = self.session.world_state
        self.world["locations"]["tavern"]["travel_routes"] = {"forest": [600, 600]}
        with patch.object(timed_gameplay, "travel_dice", return_value=(ENCOUNTER, ENCOUNTER["dice"])) as self.dice:
            self.stopped = timed_gameplay.start_travel(self.session, "forest")

    def test_a_real_journey_still_rolls_and_can_be_stopped(self):
        self.dice.assert_called_once()
        self.assertEqual(self.stopped["status"], "interrupted")
        self.assertEqual(self.world["journey"]["status"], "INTERRUPTED")
        self.assertIn(ENCOUNTER["text"], self.stopped["direct_response"])

    def walk_on(self, *messages):
        with patch.object(timed_gameplay, "travel_dice", return_value=NO_ENCOUNTER):
            return [timed_gameplay.resolve_input(self.session, message) for message in messages]

    def test_saying_go_on_finishes_the_walk(self):
        self.walk_on("Yoluma devam ediyorum.", "Devam ediyorum.")
        self.assertEqual(self.world["location"], "forest")
        self.assertEqual(self.world["journey"]["status"], "ARRIVED")

    def test_naming_the_same_place_again_goes_on_instead_of_turning_back(self):
        spent = self.world["campaign_time"]["elapsed_seconds"]
        result = self.walk_on("Forest konumuna gidiyorum.")[0]
        self.assertNotIn("geri dön", result["direct_response"])
        self.assertFalse(self.world["journey"].get("returning"))
        self.assertEqual(self.world["journey"]["destination"], "forest")
        self.assertLessEqual(self.world["campaign_time"]["elapsed_seconds"] - spent, 300, "only the rest of this stage")
