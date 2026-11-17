"""BM Task 9 (B7, K-BM-2): the road warning is said AND the walk happens in the same turn; said once only."""
from __future__ import annotations

import uuid

import front_proposal
import grounded_action
import living_world
import local_places
from api.tests.test_world_keeps_its_word import FrontScene


class RoadWarningDoesNotStopTheWalk(FrontScene):
    OUT = {"kind": "go_to", "place_id": front_proposal.WAY_OUT}
    ON = "duraktan geçip kuzey yoluna devam ediyorum, şehirden uzaklaşıyorum"

    async def at_the_stop(self):
        await self.begin()
        self.client.front = self.OUT
        await self.line("şehirden çıkıyorum, kuzey yoluna")
        return self.session.world_state["location"]

    def said_warnings(self, text, who):
        return [line for line in grounded_action._ROAD_ON if line.format(who=who) in text]

    async def test_first_go_on_walks_and_warns(self):
        stop = await self.at_the_stop()
        world = self.session.world_state
        who = living_world.public_npc_name(local_places.resident_of(world, stop))
        clock = world["campaign_time"]["elapsed_seconds"]
        out = await self.line(self.ON)
        world = self.session.world_state
        text = out["narration"]
        warned = self.said_warnings(text, who)
        self.assertEqual(len(warned), 1, text)
        self.assertTrue(text.startswith(warned[0].format(who=who)), text)
        self.assertGreater(len(text), len(warned[0].format(who=who)) + 10, text)  # the walk result follows
        self.assertNotEqual(world["location"], stop, text)
        self.assertGreater(world["campaign_time"]["elapsed_seconds"], clock)
        self.assertIs(world["locations"][stop]["road_warned"], True)

    async def test_second_go_on_no_warning(self):
        stop = await self.at_the_stop()
        who = living_world.public_npc_name(local_places.resident_of(self.session.world_state, stop))
        await self.line(self.ON)
        world = self.session.world_state
        world["location"] = stop  # back at the stop: the warning is already said here
        clock = world["campaign_time"]["elapsed_seconds"]
        out = await self.line(self.ON)
        world = self.session.world_state
        self.assertEqual(self.said_warnings(out["narration"], who), [], out["narration"])
        self.assertNotEqual(world["location"], stop, out["narration"])
        self.assertGreater(world["campaign_time"]["elapsed_seconds"], clock)

    async def test_undo_puts_location_time_and_warned_flag_back(self):
        stop = await self.at_the_stop()
        world = self.session.world_state
        clock = world["campaign_time"]["elapsed_seconds"]
        action_id = str(uuid.uuid4())
        walked = await self.http.post(self.turn_url, json={"message": self.ON, "action_id": action_id})
        self.assertEqual(walked.status_code, 200, walked.text)
        self.assertNotEqual(self.session.world_state["location"], stop)
        undo_url = self.turn_url.rsplit("/", 1)[0] + "/undo"
        undone = await self.http.post(undo_url, json={"action_id": str(uuid.uuid4()), "target_action_id": action_id})
        self.assertEqual(undone.status_code, 200, undone.text)
        world = self.session.world_state
        self.assertEqual(world["location"], stop)
        self.assertEqual(world["campaign_time"]["elapsed_seconds"], clock)
        self.assertFalse(world["locations"][stop].get("road_warned"))
