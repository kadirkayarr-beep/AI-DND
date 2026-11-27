"""G2.5: the road and the arrival tell the truth in one voice (D-301, D-338, D-309, D-296, D-498, D-303)."""
import json
import unittest

import grounded_action
import local_places
from api.tests.journeys.runner import call_kind
from api.tests.test_arrival_wiring import _ArrivalApi
from api.tests import test_town_portrait as portrait

FAR = portrait.FAR
HOME = portrait.HOME
CITY = "fr:city:neverwinter"
STREET_LINE = "Dışarı, Neverwinter sokaklarına çıkıyorsun."
NARRATED = "Gün ışığı yüzüne vurur, sokak seni karşılar."


class _Story(_ArrivalApi):
    TOWN_SEED = 4401
    script_extra: dict = {}

    async def asyncSetUp(self):
        await super().asyncSetUp()
        write = self.client.script_turn

        def script_turn(**kwargs):
            write(**kwargs)
            self.client.script["narration"] = NARRATED
            self.client.script.update(self.script_extra)

        self.client.script_turn = script_turn

    def stand_at(self, place_id):
        self.session().world_state["location"] = place_id


class TravelLineIsNarrated(_Story):
    async def test_going_to_a_known_place_is_told_by_the_narrator_not_by_python(self):  # D-301, Kadir K29
        await self.turn("demirhaneye gidiyorum", arrival="Ocak harlı yanıyor.")
        self.client.kinds.clear()
        reply = await self.turn("Neverwinter'a gidiyorum")
        self.assertEqual(reply.status_code, 200, reply.text)
        text = reply.json()["narration"]
        self.assertEqual(self.session().world_state["location"], CITY)
        self.assertIn(NARRATED, text)
        self.assertNotIn("konumuna vardın", text)
        self.assertIn("narration", self.client.kinds)


class ArrivalReasonIsSaved(_Story):
    async def test_the_reason_a_python_arrival_stands_survives_a_reload(self):  # D-309
        await self.turn("demirhaneye gidiyorum", arrival=RuntimeError("down"))
        stored = self.session().world_state["scene_state"]["arrival_text"]
        self.assertEqual((stored["source"], stored["reason_code"]), ("python", "model_error"))
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import TEST_PLAYER
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        fresh_id, *_ = fresh.resume_campaign(self.campaign_id)
        loaded = fresh.get(fresh_id).game_session.world_state["scene_state"]["arrival_text"]
        self.assertEqual((loaded["source"], loaded["reason_code"]), ("python", "model_error"))

    async def test_a_model_arrival_says_so(self):
        await self.turn("demirhaneye gidiyorum", arrival="Ocak harlı yanıyor.")
        stored = self.session().world_state["scene_state"]["arrival_text"]
        self.assertEqual((stored["source"], stored["reason_code"]), ("model", None))


class StreetLineOncePerVisit(_Story):
    def make_places(self):
        world = self.session().world_state
        second = local_places.create_local_place(world, CITY, "estate")
        third = local_places.create_local_place(world, CITY, "archive")
        self.assertIsNotNone(second)
        self.assertIsNotNone(third)
        return world, second, third

    async def test_leaving_two_buildings_into_the_same_street_says_it_once(self):  # D-498, S22
        _world, second, third = self.make_places()
        self.stand_at(self.place_of("smithy"))
        first = await self.turn(f"{second['name']}ne yaklaşıyorum")
        self.assertEqual(first.json()["narration"].count(STREET_LINE), 1, first.json()["narration"])
        self.stand_at(second["id"])
        again = await self.turn(f"{third['name']}ne yaklaşıyorum")
        self.assertEqual(again.status_code, 200, again.text)
        self.assertNotIn("Dışarı,", again.json()["narration"])

    async def test_a_new_visit_says_it_again(self):
        world, second, _third = self.make_places()
        world["locations"][FAR] = {"id": FAR, "name": "Karaduvar", "type": "town", "aliases": []}
        self.stand_at(self.place_of("smithy"))
        await self.turn(f"{second['name']}ne yaklaşıyorum")
        self.assertEqual(grounded_action._memory(world).get("street_line_town"), CITY)
        world["location"] = FAR
        grounded_action.clear_near(world)  # what commit_location_change calls on every move
        self.assertIsNone(grounded_action._memory(world).get("street_line_town"))


class RoadOnAlone(_Story):
    async def test_two_walks_on_in_a_row_do_not_repeat_the_same_line(self):  # D-338
        world = self.session().world_state
        grove = local_places.create_local_place(world, CITY, "grove")
        self.assertIsNotNone(grove)
        self.stand_at(grove["id"])
        lines = []
        for _ in range(2):
            walked = grounded_action.road_goes_on(self.session(), "yürümeye devam ediyorum")
            self.assertIsNotNone(walked)
            lines.append(walked["narration"])
        self.assertNotEqual(lines[0], lines[1])
        for line in lines:
            self.assertIn("Hâlâ yoldasın.", line)


class AttachedTargetName(_Story):
    """D-296: a place made from the words of a walk is named without the suffix and the punctuation the line carried."""

    async def test_the_new_place_is_named_without_the_attached_suffix(self):
        self.script_extra = {"intent": {"intent": "travel", "action": "travel", "completion": "completed",
                                        "target": {"type": "location", "reference": "Kuzey Mahzeni'ne.", "npc_id": "",
                                                   "evidence_quote": "Mahzeni'ne"}}}
        real = self.client.chat

        def chat(*args, **kwargs):
            reply = real(*args, **kwargs)
            if call_kind(kwargs.get("format")) != "narration":
                return reply
            packet = {"narration": "Kuzey Mahzeni kapısına ulaştın.", "lore_claims": [],
                      "world_updates": {"create_locations": [{"name": "Kuzey Mahzeni", "type": "building",
                                                              "description": "Nemli bir mahzen."}]}}
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        self.client.chat = chat
        reply = await self.turn("Kuzey Mahzeni'ne gidiyorum.")
        self.assertEqual(reply.status_code, 200, reply.text)
        names = [rec.get("name") for rec in self.session().world_state["locations"].values()]
        self.assertFalse([name for name in names if "'ne" in str(name)], names)
        self.assertIn("Kuzey Mahzeni", names)


class StartingTownKeepsItsOwnWords(unittest.IsolatedAsyncioTestCase):
    """D-303: the start settlement is recorded; coming home never writes it a portrait from the return line."""
    asyncSetUp = portrait.TownPortrait.asyncSetUp
    asyncTearDown = portrait.TownPortrait.asyncTearDown
    world = portrait.TownPortrait.world
    travel = portrait.TownPortrait.travel

    async def test_the_start_settlement_is_recorded_and_gets_no_portrait_on_return(self):
        self.assertEqual(self.world["flags"]["starting_settlement_id"], HOME)
        await self.travel(FAR, "Sis dağılırken Karaduvar'ın taş kapısı belirir.")
        await self.travel(HOME, "Eve dönüyorsun. Kapılar hâlâ açık.")
        self.assertNotIn("town_portrait", self.world["locations"][HOME])


if __name__ == "__main__":
    unittest.main()
