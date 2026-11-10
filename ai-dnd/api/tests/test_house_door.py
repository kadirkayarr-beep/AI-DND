"""A big house has a way in or a real reason it stays shut, and someone behind the door to meet."""
import copy
import unittest
from unittest.mock import patch

import campaign_time
import local_places
import relationships
import town_knowledge
import vouching
import world_happenings
import world_threads

from api.tests.test_said_is_real import ClassifiedClient, Table
from api.tests.test_story_links import resident, town
from api.tests.test_town_knowledge import ThroughTheRealTurn
from api.tests.test_world_threads import DAY


def stub_npc(world):
    def create(proposal):
        npc = {"id": f"npc_{len(world['npcs'])}", **proposal}
        world["npcs"].append(npc)
        return npc
    return create


def stub_feature(world):
    def create(proposal):
        feature = {"id": f"feature_{len(world.setdefault('features', []))}", **proposal}
        world["features"].append(feature)
        return feature
    return create


def a_house(seed="seed-house", kind="estate"):
    world, state = town(seed)
    settlement = state["seeded"][0]
    record = local_places.find_local_place(world, settlement, kind) or local_places.create_local_place(world, settlement, kind)
    steward, _ = local_places.furnish(world, record, create_npc=stub_npc(world), create_feature=stub_feature(world))
    return world, state, record, steward, local_places.inner_room_of(world, record["id"])


def door_of(world, room):
    return next(door for door in world["doors"] if door["id"] == f"venue-door:{room['id']}")


class TheHouseHasAnInside(unittest.TestCase):
    def test_a_room_behind_a_shut_door_comes_with_the_house_once(self):
        world, _, record, _, room = a_house()
        self.assertEqual(room["parent_location_id"], record["id"])
        self.assertEqual(room["exit_location_id"], record["id"])
        door = door_of(world, room)
        self.assertEqual((door["location"], door["locked"], door["open"]), (record["id"], True, False))
        local_places.furnish(world, record, create_npc=stub_npc(world), create_feature=stub_feature(world))
        self.assertEqual(sum(1 for r in world["locations"].values() if r.get("inner_of") == record["id"]), 1)

    def test_a_barracks_has_one_and_a_market_does_not(self):
        self.assertIsNotNone(a_house(kind="barracks")[4])
        self.assertIsNone(a_house(kind="market")[4])

    def test_the_room_is_in_the_same_town(self):
        world, state, _, _, room = a_house()
        self.assertEqual(local_places.settlement_of(world, room["id"]), state["seeded"][0])

    def test_the_street_does_not_talk_of_the_room_as_a_place(self):
        world, _, record, _, room = a_house()
        npc = {"id": "gecen", "role": "yolcu", "location": world["location"]}
        places = [item["location_id"] for item in town_knowledge._places(world, world["location"], npc)]
        self.assertNotIn(room["id"], places)
        self.assertIsNone(local_places.named_in(world, world["location"], room["name"].split()[-1]))

    def test_a_save_from_before_gains_it_on_the_next_visit(self):
        world, _, record, _, room = a_house()
        del world["locations"][room["id"]]
        world["doors"] = [door for door in world["doors"] if door["id"] != f"venue-door:{room['id']}"]
        local_places.furnish(world, record, create_npc=stub_npc(world), create_feature=stub_feature(world))
        self.assertIsNotNone(local_places.inner_room_of(world, record["id"]))

    def test_two_campaigns_open_on_different_days(self):
        days = {door_of(world, room)["opens_at"] for world, _, _, _, room in (a_house(f"seed-house-{n}") for n in range(16))}
        self.assertGreater(len(days), 1)


class WaysIn(unittest.TestCase):
    def test_a_stranger_finds_it_shut_and_the_steward_says_why_and_how(self):
        world, _, record, steward, room = a_house()
        self.assertEqual(vouching.open_doors(world), [])
        self.assertTrue(door_of(world, room)["locked"])
        note = town_knowledge.speech_note(world, steward)
        self.assertIn("kimseyi kabul etmiyor", note)
        self.assertNotRegex(note.split("kimseyi kabul etmiyor")[1][:60], r"\d")

    def test_the_house_comes_before_the_work_in_the_note_so_a_job_is_still_answered_as_a_job(self):
        world, state, record, steward, room = a_house()
        thread = state["threads"][0]
        thread.update(place_id=record["id"], type="errand", status="open", owner_line="Mektup var, altı bakır.")
        with patch.object(world_threads, "owner_mood", return_value="yes"):
            note = town_knowledge.speech_note(world, steward)
        self.assertLess(note.index("kabul etmiyor"), note.index("Mektup var"))

    def test_work_done_for_the_house_opens_it(self):
        world, _, record, steward, room = a_house()
        relationships.note(world, steward["id"], 1, "test")
        world["location"] = record["id"]
        lines = vouching.open_doors(world)
        self.assertFalse(door_of(world, room)["locked"])
        self.assertTrue(lines)
        self.assertEqual(vouching.open_doors(world), [])
        self.assertIn("içeri", town_knowledge.speech_note(world, steward))

    def test_a_word_from_a_place_that_can_speak_for_you_opens_it(self):
        for number in range(30):
            world, state, record, steward, room = a_house(f"seed-house-{number}")
            kinds = vouching.chosen_kinds(world, {}, "estate")
            spot = next((r for r in world["locations"].values() if r.get("place_kind") in kinds), None)
            if spot is not None:
                speaker = resident(world, spot["id"], "soz-eden")
                relationships.note(world, speaker["id"], 1, "test")
                vouching.open_doors(world)
                self.assertFalse(door_of(world, room)["locked"])
                return
        self.fail("no town had a place that can vouch")

    def test_the_day_the_house_receives_opens_it_for_anyone(self):
        world, _, record, steward, room = a_house()
        world_threads.tick(world, door_of(world, room)["opens_at"])
        world["campaign_time"]["elapsed_seconds"] = door_of(world, room)["opens_at"]
        vouching.open_doors(world)
        self.assertFalse(door_of(world, room)["locked"])

    def test_being_sent_for_opens_it(self):
        world, _, record, steward, room = a_house()
        link = world_happenings.tie(world, world_happenings.CALLER, "opened", steward, record["id"])
        vouching.summoned(world, link)
        vouching.open_doors(world)
        self.assertFalse(door_of(world, room)["locked"])

    def test_the_one_sent_says_who_wants_to_see_the_player(self):
        world, _, record, steward, room = a_house()
        link = world_happenings.tie(world, world_happenings.CALLER, "opened", steward, record["id"])
        link.update(caller_id="ulak")
        link.pop("fires_at")
        note = world_happenings.link_note(world, {"id": "ulak", "caller_of": link["thread_id"]})
        self.assertIn("görmek istiyor", note)
        self.assertIn(record["name"], note)

    def test_with_the_steward_gone_it_is_only_a_locked_door(self):
        world, _, record, steward, room = a_house()
        self.assertTrue(vouching.shut_line(world, door_of(world, room)))
        steward["combat_status"] = "dead"
        self.assertIsNone(vouching.shut_line(world, door_of(world, room)))

    def test_a_sealed_letter_of_the_house_is_the_masters(self):
        world, _, record, steward, room = a_house()
        link = world_happenings.tie(world, world_happenings.CALLER, "opened", steward, record["id"])
        self.assertIn("sahibi", world_happenings._link_owner(world, link))

    def test_the_master_hears_what_was_sent_in_their_name(self):
        world, state, record, steward, room = a_house()
        master = resident(world, room["id"], "efendi")
        master["role"] = local_places.PLACE_KINDS[room["place_kind"]]["role"]
        thread = state["threads"][0]
        thread["letter_line"] = "Aranan kayıt burada değil."
        link = world_happenings.tie(world, world_happenings.CALLER, "opened", steward, record["id"], about=thread["thread_id"])
        link.pop("fires_at")
        link["caller_id"] = "ulak"
        self.assertIn("Aranan kayıt", town_knowledge.speech_note(world, master))


class ItLasts(ThroughTheRealTurn):
    async def test_the_room_and_a_link_on_the_clock_survive_a_save_and_a_new_process(self):
        await self.start()
        await self.say("Burada nerede iş bulabilirim?", "Bir bakayım.")
        world = self.session.world_state
        settlement = world_threads.view(world)["seeded"][0]
        record = local_places.find_local_place(world, settlement, "estate") or local_places.create_local_place(world, settlement, "estate")
        local_places._add_inner_room(world, record)
        world_happenings.tie(world, world_happenings.CALLER, "opened", self.npc, record["id"])
        await self.say("Peki sağ ol.", "Eyvallah.")
        kept_state = copy.deepcopy(world[world_threads.KEY])
        kept_doors = copy.deepcopy(world["doors"])
        again = await self.resume_in_a_new_process()
        self.assertEqual(again[world_threads.KEY], kept_state)
        self.assertEqual(again["doors"], kept_doors)
        self.assertIsNotNone(local_places.inner_room_of(again, record["id"]))


class AtTheTable(Table):
    async def house(self):
        await self.begin()
        self.client = ClassifiedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        settlement = world_threads.view(self.world)["seeded"][0]
        self.world["location"] = settlement
        self.record = local_places.find_local_place(self.world, settlement, "estate") or local_places.create_local_place(
            self.world, settlement, "estate")
        self.client.front = {"kind": "go_to", "place_id": self.record["id"], "inside": True}
        await self.line("konaga gidiyorum")
        self.assertEqual(self.world["location"], self.record["id"])
        self.room = local_places.inner_room_of(self.world, self.record["id"])
        self.client.front = {"kind": "go_to", "place_id": self.room["id"], "inside": True}

    async def test_walking_in_on_a_house_that_is_shut_is_stopped_by_a_reason_not_a_lock(self):
        await self.house()
        reply = await self.line("konagin icine dogru yuruyorum, efendinin odasini arayacagim")
        self.assertEqual(self.world["location"], self.record["id"])
        self.assertIn("kabul etmiyor", reply["narration"])

    async def test_a_reading_that_takes_the_room_for_the_street_still_goes_out(self):
        await self.house()
        await self.line("sokaga cikiyorum")
        self.assertEqual(self.world["location"], world_threads.view(self.world)["seeded"][0])

    async def test_once_it_is_open_the_master_is_there_to_meet(self):
        await self.house()
        steward = local_places.resident_of(self.world, self.record["id"])
        relationships.note(self.world, steward["id"], 1, "test")
        self.client.front = {"kind": "look"}
        reply = await self.line("etrafa bakayim")
        self.assertIn("kapı", reply["narration"].casefold())
        self.client.front = {"kind": "go_to", "place_id": self.room["id"], "inside": True}
        # Dilim 3D Task 5: the walk goes ahead only when the line names the person there; the role is public ("Konağın sahibi")
        reply = await self.line("konagin sahibinin yanina cikiyorum")
        self.assertEqual(self.world["location"], self.room["id"])
        master = local_places.resident_of(self.world, self.room["id"])
        self.assertEqual(master["role"], local_places.PLACE_KINDS[self.room["place_kind"]]["role"])
        self.assertIn(living_name(master), reply["narration"])

    async def test_the_way_back_out_is_the_courtyard(self):
        await self.test_once_it_is_open_the_master_is_there_to_meet()
        self.client.front = {"kind": "go_to", "place_id": self.record["id"]}
        await self.line("avluya cikiyorum")
        self.assertEqual(self.world["location"], self.record["id"])


def living_name(npc):
    import living_world
    return living_world.public_npc_name(npc)
