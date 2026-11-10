"""Task 39: the clock and the place say what the line did (H23/H108, H136/H250, H11/H203, H116, H36)."""
import unittest
from unittest.mock import patch

import campaign_time
import combat_lifecycle
import timed_gameplay
from api.tests import test_campaign_time as v1
from api.tests.test_combat_lifecycle import ready
from api.tests import test_front_proposal as front_tests
from api.tests.town_seed import fixed_town

SUCCESS = {"result": "BAŞARILI", "roll": 20, "total": 25, "dc": 12}


def _at(world, hour, minute=0):
    """Move the clock forward to the next hour:minute (never back)."""
    world["campaign_time"]["elapsed_seconds"] += campaign_time._until_hour(world, hour) % campaign_time.DAY + minute * 60
    now = campaign_time.public_time(world)
    assert (now["hour"], now["minute"]) == (hour, minute), now


class TheNamedPartOfTheDay(unittest.TestCase):
    def scene_at(self, hour, minute=0):
        session = v1.scene()
        _at(session.world_state, hour, minute)
        return session, session.world_state["campaign_time"]["elapsed_seconds"]

    def test_until_evening_said_in_the_evening_passes_no_day(self):
        for owner in (timed_gameplay.resolve_input, timed_gameplay.pass_time):
            for hour, minute in ((18, 30), (20, 0)):
                with self.subTest(owner=owner.__name__, at=(hour, minute)):
                    session, before = self.scene_at(hour, minute)
                    result = owner(session, "akşama kadar bekliyorum")
                    self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before)
                    self.assertEqual(result["action"], "wait")
                    self.assertIn("Söylediğin vakit zaten geldi", result["direct_response"])

    def test_until_evening_said_in_the_afternoon_waits_until_six(self):
        for owner in (timed_gameplay.resolve_input, timed_gameplay.pass_time):
            with self.subTest(owner=owner.__name__):
                session, before = self.scene_at(15)
                owner(session, "akşama kadar bekliyorum")
                self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before + 3 * 3600)

    def test_until_morning_said_in_the_morning_is_the_next_morning(self):
        session, before = self.scene_at(9)
        timed_gameplay.resolve_input(session, "sabaha kadar bekliyorum")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before + 22 * 3600)

    def test_until_morning_said_in_the_night_waits_until_seven(self):
        session, before = self.scene_at(3)
        timed_gameplay.resolve_input(session, "sabaha kadar bekliyorum")
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], before + 4 * 3600)


class AFlightTakesTheWayOutsTime(unittest.TestCase):
    def setUp(self):
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def flee_from(self, walk_seconds):
        session, _ = ready(v1.scene())
        world = session.world_state
        here = world["locations"][world["location"]]
        here.pop("parent_location_id", None)
        here["exit_location_id"] = "forest"
        if walk_seconds:
            here["walk_seconds"] = walk_seconds
        before = world["campaign_time"]["elapsed_seconds"]
        with patch.object(session, "perform_skill_check", create=True, return_value=dict(SUCCESS)):
            result = combat_lifecycle.flee(session)
        self.assertIs(result["action_result"]["success"], True)
        self.assertEqual(world["location"], "forest")
        return world["campaign_time"]["elapsed_seconds"] - before, result

    def test_running_off_a_long_road_takes_the_road(self):
        spent, result = self.flee_from(3600)
        self.assertEqual(spent, 3600)
        self.assertIn("campaign_time", result["action_result"]["state_changes"])

    def test_running_out_of_a_door_takes_no_hour(self):
        spent, _ = self.flee_from(None)
        self.assertEqual(spent, 0)


class TheWalkIsWhatTheLineDid(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = front_tests.FrontTable.asyncSetUp, front_tests.FrontTable.asyncTearDown
    campaign_with_npc, open_job, line = front_tests.FrontTable.campaign_with_npc, front_tests.FrontTable.open_job, front_tests.FrontTable.line
    begin, routes, the_inn = front_tests.FrontTable.begin, front_tests.FrontTable.routes, front_tests.FrontTable.the_inn

    async def town(self):
        with fixed_town(self, 2701):
            await self.begin()
        self.city, self.inn = self.world["location"], self.the_inn()
        for door in self.world.get("doors", []):
            door.update(locked=False, open=True)

    async def test_going_out_then_looking_goes_out_whatever_the_reading_picked(self):
        await self.town()
        for front in ({"kind": "look"}, {"kind": "sit"}):
            with self.subTest(front=front["kind"]):
                self.session.commit_location_change(self.inn)
                self.client.front = front
                reply = await self.line("dışarı çıkıp etrafa bakıyorum")
                self.assertEqual(self.world["location"], self.city, reply["narration"])

    async def test_looking_around_inside_stays_inside(self):
        await self.town()
        self.session.commit_location_change(self.inn)
        self.client.front = {"kind": "look"}
        await self.line("etrafa bakıyorum")
        self.assertEqual(self.world["location"], self.inn)

    async def test_standing_outside_the_door_does_not_go_in(self):
        await self.town()
        for line in ("hanın kapısının dışında duruyorum", "hanın kapısının önünde bekliyorum", "hanın önüne geliyorum"):
            with self.subTest(line=line):
                self.session.commit_location_change(self.city)
                self.client.front = {"kind": "go_to", "place_id": self.inn, "inside": False}
                reply = await self.line(line)
                self.assertEqual(self.world["location"], self.city, reply["narration"])

    async def test_going_to_the_inn_still_goes_in_and_an_inside_reading_goes_in(self):
        await self.town()
        for line, inside in (("hana gidiyorum", False), ("hanın kapısının dışında duruyorum", True),
                             # review I2: walk words Python does not read, or no verb at all, still walk in
                             ("hana uğruyorum", False), ("hana yollanıyorum", False), ("hanı ziyaret ediyorum", False),
                             ("Hana.", False)):
            with self.subTest(line=line, inside=inside):
                self.session.commit_location_change(self.city)
                self.client.front = {"kind": "go_to", "place_id": self.inn, "inside": inside}
                reply = await self.line(line)
                self.assertEqual(self.world["location"], self.inn, reply["narration"])

    async def test_going_to_talk_to_someone_at_their_place_is_the_walk_there(self):
        await self.town()
        place_id, record = next((key, value) for key, value in self.world["locations"].items()
                                if isinstance(value, dict) and value.get("resident_name")
                                and value.get("parent_location_id") == self.city)
        name = record["resident_name"]
        for front in ({"kind": "unclear"}, {"kind": "speak_to", "person_id": self.npc["id"]}):
            with self.subTest(front=front["kind"]):
                self.session.commit_location_change(self.city)
                clock = self.world["campaign_time"]["elapsed_seconds"]
                self.client.front = front
                reply = await self.line(f"{name} ile konuşmaya gidiyorum")
                self.assertIn(self.world["location"], {place_id, *[
                    key for key, value in self.world["locations"].items()
                    if isinstance(value, dict) and value.get("parent_location_id") == place_id]}, reply["narration"])
                self.assertGreater(self.world["campaign_time"]["elapsed_seconds"], clock)

    async def test_going_to_talk_to_someone_here_is_still_the_talk(self):
        await self.town()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"]}
        await self.line(f"{self.npc['name']} ile konuşmaya gidiyorum")
        self.assertEqual(self.world["location"], self.city)


if __name__ == "__main__":
    unittest.main()
