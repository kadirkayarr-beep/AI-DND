"""World threads and reserved residents: real places, real names, a town that moves."""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import campaign_time
import living_world
import local_places
import npc_statements
import world_threads

HOUR = 3600
DAY = 86400


def city(seed="seed-a"):
    world = {
        "location": "city",
        "locations": {"city": {"id": "city", "name": "Neverwinter", "type": "city", "scene_kind": "city"}},
        "npcs": [],
        "flags": {"turn_index": 1},
        "scene_state": {"campaign_seed": seed},
    }
    campaign_time.initialize(world)
    return world


def shape(world):
    """What a campaign's threads are, with every name taken out."""
    places = world["locations"]
    return sorted(
        (t["template_id"], places[t["place_id"]]["place_kind"],
         places[t["target_place_id"]]["place_kind"] if t["target_place_id"] else None)
        for t in world_threads.active(world)
    )


class ReservedResidents(unittest.TestCase):
    def test_an_estate_is_an_ordinary_place_kind(self):
        world = city()
        record = local_places.create_local_place(world, "city", "estate")
        self.assertTrue(record["name"].endswith("Konağı"))
        self.assertEqual(local_places.is_local_place_visit("Konağa gidiyorum."), "estate")
        self.assertEqual(npc_statements.place_kind_of("konagina")[1], "estate")

    def test_a_person_met_keeps_the_name_said_before(self):
        world = city()
        record = local_places.create_local_place(world, "city", "smithy")
        record["resident_name"] = "Serenna"
        made = []

        def create_npc(fields):
            made.append(fields)
            return dict(fields, id="npc_001")

        local_places.furnish(world, record, create_npc=create_npc,
                             create_feature=lambda fields: dict(fields, id="f"))
        self.assertEqual(made[0]["name"], "Serenna")

    def test_a_reserved_name_is_not_given_to_anyone_else(self):
        world = city()
        first = living_world.stable_local_name(world, "place", "Demirci")
        world["locations"]["city"]["resident_name"] = first
        self.assertNotEqual(living_world.stable_local_name(world, "place", "Demirci"), first)


class Seeding(unittest.TestCase):
    def test_threads_stand_on_real_places_with_reserved_people(self):
        world = city()
        world_threads.ensure(world)
        threads = world_threads.active(world)
        self.assertGreaterEqual(len(threads), 3)
        for thread in threads:
            place = world["locations"][thread["place_id"]]
            self.assertEqual(place["parent_location_id"], "city")
            self.assertEqual(place["resident_name"], thread["owner_name"])
            self.assertIn(place["name"].split()[-1], json.dumps(thread, ensure_ascii=False) + place["name"])
            self.assertLessEqual(len(thread["public_line"]), world_threads.MAX_PUBLIC_LINE)
            self.assertLessEqual(len(thread["owner_line"]), world_threads.MAX_OWNER_LINE)
            self.assertNotIn("{", thread["public_line"] + thread["owner_line"])
            if thread["target_place_id"]:
                self.assertIn(thread["target_place_id"], world["locations"])
                self.assertNotEqual(thread["target_place_id"], thread["place_id"])

    def test_the_same_campaign_seeds_the_same_threads(self):
        one, two = city("same"), city("same")
        world_threads.ensure(one)
        world_threads.ensure(two)
        self.assertEqual(one[world_threads.KEY], two[world_threads.KEY])

    def test_seeding_twice_changes_nothing(self):
        world = city()
        world_threads.ensure(world)
        before = copy.deepcopy(world)
        world_threads.ensure(world)
        self.assertEqual(world, before)

    def test_campaigns_differ_in_shape_not_only_in_names(self):
        shapes = set()
        counts = set()
        for index in range(12):
            world = city(f"campaign-{index}")
            world_threads.ensure(world)
            shapes.add(tuple(shape(world)))
            counts.add(len(world_threads.active(world)))
        self.assertGreaterEqual(len(shapes), 11, shapes)
        self.assertGreater(len(counts), 1)

    def test_some_campaigns_tie_threads_together_and_some_do_not(self):
        tied = []
        for index in range(20):
            world = city(f"knot-{index}")
            world_threads.ensure(world)
            places = [p for t in world_threads.active(world) for p in (t["place_id"], t["target_place_id"]) if p]
            tied.append(len(places) != len(set(places)))
        self.assertIn(True, tied)
        self.assertIn(False, tied)

    def test_a_town_never_has_only_one_sort_of_need(self):
        for index in range(20):
            world = city(f"mix-{index}")
            world_threads.ensure(world)
            kinds = [t["type"] for t in world_threads.active(world)]
            self.assertGreater(len(set(kinds)), 1, kinds)

    def test_nothing_in_the_data_names_a_character_or_background(self):
        text = world_threads.DATA_PATH.read_text(encoding="utf-8").casefold()
        for word in ("carius", "soldier", "fighter", "kefalet"):
            self.assertNotIn(word, text)

    def test_an_old_save_gains_threads_lazily_and_outside_a_town_nothing_happens(self):
        world = city()
        self.assertNotIn(world_threads.KEY, world)
        world_threads.ensure(world)
        self.assertIn(world_threads.KEY, world)
        road = city()
        road["locations"]["road"] = {"id": "road", "name": "Yol", "type": "wilderness"}
        road["location"] = "road"
        self.assertIsNone(world_threads.ensure(road))
        self.assertNotIn(world_threads.KEY, road)

    def test_a_world_without_a_seed_is_left_alone(self):
        world = city("")
        self.assertIsNone(world_threads.ensure(world))
        self.assertEqual(len(world["locations"]), 1)

    def test_a_failure_leaves_the_world_as_it_was(self):
        world = city()
        before = copy.deepcopy(world)
        with patch.object(world_threads, "validate", side_effect=ValueError("boom")):
            self.assertIsNone(world_threads.ensure(world))
        self.assertEqual(world, before)

    def test_an_unreadable_catalog_gives_no_threads_and_no_error(self):
        world = city()
        with patch.object(world_threads, "_catalog_cache", {"templates": []}):
            self.assertIsNone(world_threads.ensure(world))
        self.assertNotIn(world_threads.KEY, world)

    def test_the_place_ceiling_is_respected(self):
        world = city()
        for kind in list(local_places.PLACE_KINDS)[:local_places.MAX_LOCAL_PLACES_PER_SETTLEMENT]:
            local_places.create_local_place(world, "city", kind)
        world_threads.ensure(world)
        places = [r for r in world["locations"].values() if r.get("place_kind")]
        self.assertLessEqual(len(places), local_places.MAX_LOCAL_PLACES_PER_SETTLEMENT)


class TimePasses(unittest.TestCase):
    def setUp(self):
        self.world = city("clock")
        world_threads.ensure(self.world)
        self.state = self.world[world_threads.KEY]
        self.first = self.state["threads"][0]

    def test_an_offer_stands_until_its_window_closes_and_not_at_its_end(self):
        due = self.first["expires_at"]
        world_threads.tick(self.world, due - 1)
        self.assertTrue(any(t["thread_id"] == self.first["thread_id"] for t in world_threads.active(self.world)))
        world_threads.tick(self.world, due)
        self.assertFalse(any(t["thread_id"] == self.first["thread_id"] for t in world_threads.active(self.world)))

    def test_the_town_moves_on_without_the_player(self):
        late = max(t["expires_at"] for t in self.state["threads"])
        world_threads.tick(self.world, late)
        state = self.world[world_threads.KEY]
        self.assertTrue(state["history"])
        self.assertTrue(all(t["status"] in world_threads.TERMINAL for t in state["history"]))
        self.assertEqual({t["closed_at"] for t in state["history"]}, {late})
        self.assertGreaterEqual(len(world_threads.active(self.world)), 1)

    def test_the_same_moment_twice_does_nothing(self):
        late = max(t["expires_at"] for t in self.state["threads"])
        world_threads.tick(self.world, late)
        once = copy.deepcopy(self.world[world_threads.KEY])
        world_threads.tick(self.world, late)
        self.assertEqual(self.world[world_threads.KEY], once)

    def test_many_cycles_stay_within_both_limits(self):
        now = 0
        for _ in range(40):
            now += 5 * DAY
            world_threads.tick(self.world, now)
            state = self.world[world_threads.KEY]
            self.assertLessEqual(len(state["threads"]), world_threads.MAX_ACTIVE)
            self.assertLessEqual(len(state["history"]), world_threads.MAX_HISTORY)
            world_threads.validate(state)

    def test_the_game_clock_drives_the_town(self):
        with patch.object(world_threads, "tick", wraps=world_threads.tick) as tick:
            campaign_time.advance(self.world, 3 * DAY, "rest", "test")
        tick.assert_called_once_with(self.world, 3 * DAY)

    def test_a_broken_tick_never_stops_the_clock(self):
        before = copy.deepcopy(self.world[world_threads.KEY])
        with patch.object(world_threads, "_close_due", side_effect=RuntimeError("boom")):
            campaign_time.advance(self.world, 3 * DAY, "rest", "test")
        self.assertEqual(self.world[world_threads.KEY], before)
        self.assertEqual(self.world["campaign_time"]["elapsed_seconds"], 3 * DAY)

    def test_a_world_without_threads_is_not_touched_by_time(self):
        world = city("quiet")
        campaign_time.advance(world, DAY, "rest", "test")
        self.assertNotIn(world_threads.KEY, world)


class Transitions(unittest.TestCase):
    def thread(self, status):
        return {"status": status, "heard_turn": None}

    def test_only_an_open_thread_becomes_heard(self):
        thread = self.thread("open")
        world_threads.mark_heard(thread, 4)
        self.assertEqual((thread["status"], thread["heard_turn"]), ("heard", 4))
        for status in ("heard", *world_threads.TERMINAL):
            thread = self.thread(status)
            world_threads.mark_heard(thread, 9)
            self.assertEqual(thread["status"], status)
            self.assertIsNone(thread["heard_turn"])

    def test_a_closed_thread_never_reopens(self):
        for status in world_threads.TERMINAL:
            for wanted in world_threads.STATUSES:
                thread = self.thread(status)
                self.assertFalse(world_threads.transition(thread, wanted))


class SavedState(unittest.TestCase):
    def test_a_save_round_trip_keeps_threads(self):
        world = city("save")
        world_threads.ensure(world)
        again = json.loads(json.dumps(world))
        self.assertEqual(again[world_threads.KEY], world[world_threads.KEY])
        world_threads.validate(again[world_threads.KEY])

    def test_a_damaged_record_is_refused(self):
        world = city("save")
        world_threads.ensure(world)
        state = copy.deepcopy(world[world_threads.KEY])
        state["threads"][0]["status"] = "paid"
        with self.assertRaises(ValueError):
            world_threads.validate(state)
