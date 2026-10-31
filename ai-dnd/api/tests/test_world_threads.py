"""World threads and reserved residents: real places, real names, a town that moves."""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

import ambient_event_catalog
import campaign_time
import living_world
import local_places
import npc_statements
import thread_catalog
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


class TheAuthoredAmbientEvents(unittest.TestCase):
    def test_only_scenes_a_place_can_verify_and_only_to_look_at(self):
        authored = [e for e in ambient_event_catalog.EVENT_CATALOG if e["event_id"].startswith("evt")]
        self.assertGreaterEqual(len(authored), 30)
        self.assertEqual({e["event_type"] for e in authored}, {"GREEN"})
        self.assertLessEqual({kind for e in authored for kind in e["kinds"]}, {"city", "tavern"})
        self.assertLessEqual({time for e in authored for time in e["times"]}, {"day", "evening", "night"})

    def test_the_hour_still_decides(self):
        context = {"time_of_day": "night", "weather": "clear", "environment": "urban", "npc_density": 0}
        for turn in range(30):
            event = ambient_event_catalog.select_ambient_event(
                scene_kind="city", location_id="city", turn_index=turn, context=context, history=[],
                campaign_seed=f"seed-{turn}", allowed_types={"GREEN"})
            self.assertTrue(not event["times"] or "night" in event["times"], event)


class TheAuthoredCatalog(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((thread_catalog.CATALOG_DIR / "thread_templates.json").read_text(encoding="utf-8"))["items"]
        self.mapping = json.loads((thread_catalog.CATALOG_DIR / "mapping.json").read_text(encoding="utf-8"))

    def test_every_catalog_tag_and_background_has_an_explicit_decision(self):
        tags = {tag for item in self.raw for tag in item["location_types"]}
        self.assertEqual(tags - set(self.mapping["place_tags"]), set())
        labels = {hook["background"] for item in self.raw for hook in item["background_hooks"]}
        self.assertEqual(labels - set(self.mapping["background_labels"]), set())

    def test_a_tag_with_no_engine_kind_is_not_guessed(self):
        self.assertEqual(thread_catalog.place_kinds(["sokak", "han"], self.mapping), [])

    def test_most_of_the_catalog_can_be_bound_and_all_three_types_survive(self):
        loaded = thread_catalog.load()
        self.assertGreaterEqual(len(loaded), 45)
        self.assertEqual({t["type"] for t in loaded}, {"hiring", "errand", "trouble"})

    def test_offer_window_work_days_and_pay_stay_separate(self):
        hiring = next(t for t in thread_catalog.load() if t["type"] == "hiring")
        self.assertTrue({"offer_hours", "work_days", "pay"} <= set(hiring))
        self.assertNotEqual(hiring["offer_hours"], hiring["work_days"])

    def test_only_public_and_owner_words_are_read(self):
        allowed = {"id", "type", "place_kinds", "target_place_kinds", "public_lines", "owner_lines",
                   "offer_hours", "pay", "work_days"}
        for template in thread_catalog.load():
            self.assertLessEqual(set(template), allowed)

    def test_a_filled_catalog_line_fits_and_leaves_no_slot(self):
        seen = 0
        for index in range(60):
            world = city(f"catalog-{index}")
            world_threads.ensure(world)
            for thread in world_threads.active(world):
                seen += thread["template_id"].startswith("THR")
                self.assertLessEqual(len(thread["public_line"]), world_threads.MAX_PUBLIC_LINE)
                self.assertLessEqual(len(thread["owner_line"]), world_threads.MAX_OWNER_LINE)
                self.assertNotIn("{", thread["public_line"] + thread["owner_line"])
        self.assertGreater(seen, 60)

    def test_a_missing_catalog_leaves_the_starter_kinds(self):
        with patch.object(thread_catalog, "CATALOG_DIR", thread_catalog.CATALOG_DIR / "absent"):
            self.assertEqual(thread_catalog.load(), [])
