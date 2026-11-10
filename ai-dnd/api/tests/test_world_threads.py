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
        # Closed when each window ran out, not when the clock happened to be read.
        self.assertTrue(all(t["closed_at"] == t["expires_at"] <= late for t in state["history"]))
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
    def test_a_package_name_starts_with_a_turkish_capital(self):
        package = thread_catalog._package("{place_name} üzerinden iade eşyası gönderilecek.")
        self.assertEqual(package, "İade eşyası")
        self.assertEqual(thread_catalog._package("{place_name} üzerinden ılık su gönderilecek."), "Ilık su")

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
                   "offer_hours", "pay", "work_days", "pay_basis", "item_noun", "status_lines", "group"}
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

    def test_a_job_line_is_said_the_way_a_person_says_it(self):
        """'Ölçü gereci, X kişisine Y üzerinde gidecek. Ücret 29 bakır.' was the catalog's form, not speech (Task 29)."""
        by_id = {item["id"]: item for item in self.raw}
        checked = set()
        for template in thread_catalog.load():
            public = by_id[template["id"]]["public_line_template"]
            if template["type"] == "errand":
                thing = thread_catalog._package(public)
                thing = ("i" if thing[0] == "İ" else "ı" if thing[0] == "I" else thing[0].lower()) + thing[1:]
                self.assertEqual(template["owner_lines"],
                                 [f"{{recipient}}, {{target}} içinde {thing} bekliyor. Teslim edene {{pay}} bakır."])
            elif template["type"] == "hiring":
                topic = public.rstrip(" .").replace("{place_name}", "{place}")
                self.assertEqual(template["owner_lines"], [f"{topic}. {{days}} günlük iş; toplam {{pay}} bakır."])
            else:
                continue
            checked.add(template["type"])
        self.assertEqual(checked, {"errand", "hiring"})

    def test_a_missing_catalog_leaves_the_starter_kinds(self):
        with patch.object(thread_catalog, "CATALOG_DIR", thread_catalog.CATALOG_DIR / "absent"):
            self.assertEqual(thread_catalog.load(), [])


def walled(seed="seed-job"):
    """A town with threads, before anyone has answered anything."""
    world = city(seed)
    world_threads.ensure(world)
    return world, world[world_threads.KEY]


def stage(world, status, **fields):
    """The first thread, moved to a status the way a played turn leaves it."""
    thread = world[world_threads.KEY]["threads"][0]
    thread.update(status=status, type=fields.pop("type", "hiring"), offered_at=fields.pop("offered_at", 0),
                  offered_turn=1, **fields)
    return thread


def person(world, npc_id, place_id, **fields):
    npc = dict(id=npc_id, name=npc_id.title(), role="usta", location=place_id, place_role_of=place_id, **fields)
    world["npcs"].append(npc)
    return npc


class TheJobMachine(unittest.TestCase):
    def test_the_edges_are_the_only_paths(self):
        expected = {
            "open": {"heard", "offered", "filled_by_other", "expired", "fired"},
            "heard": {"offered", "filled_by_other", "expired", "fired"},
            "offered": {"accepted", "declined", "expired", "fired"},
            "declined": {"accepted", "filled_by_other", "expired", "fired"},
            "accepted": {"done", "failed", "expired", "abandoned"},
        }
        self.assertEqual(world_threads.TRANSITIONS, expected)
        for status in world_threads.STATUSES:
            for wanted in world_threads.STATUSES:
                thread = {"status": status}
                self.assertEqual(world_threads.transition(thread, wanted), wanted in expected.get(status, ()))

    def test_a_refusal_has_no_way_back_to_the_public_list(self):
        self.assertFalse({"open", "heard", "offered"} & world_threads.TRANSITIONS["declined"])

    def test_the_lists_mean_what_they_say(self):
        self.assertEqual(world_threads.PUBLIC, ("open", "heard"))
        self.assertEqual(set(world_threads.OWNED), {"open", "heard", "offered", "accepted", "declined"})
        self.assertNotIn("accepted", world_threads.CLOSABLE_BY_TIME)

    def test_an_offer_nobody_answers_is_taken_back_within_a_day(self):
        world, _ = walled()
        thread = stage(world, "offered", expires_at=10 * DAY, offered_at=HOUR)
        tid = thread["thread_id"]
        world_threads.tick(world, HOUR + 24 * HOUR - 1)
        self.assertEqual(world_threads.by_id(world, tid)["status"], "offered")
        world_threads.tick(world, HOUR + 24 * HOUR)
        closed = world_threads.by_id(world, tid)
        self.assertEqual((closed["status"], closed["closed_at"]), ("expired", 25 * HOUR))

    def test_an_offer_also_ends_with_its_own_window(self):
        world, _ = walled()
        thread = stage(world, "offered", expires_at=5 * HOUR)
        world_threads.tick(world, 9 * HOUR)
        closed = world_threads.by_id(world, thread["thread_id"])
        self.assertEqual((closed["status"], closed["closed_at"]), ("expired", 5 * HOUR))

    def test_a_turned_down_job_nearly_always_goes_to_a_real_person(self):
        filled = 0
        for number in range(30):
            world, _ = walled(f"decline-{number}")
            thread = world[world_threads.KEY]["threads"][0]
            local = person(world, "neighbour", world[world_threads.KEY]["threads"][1]["place_id"])
            stage(world, "declined", expires_at=HOUR)
            world_threads.tick(world, 2 * HOUR)
            closed = world_threads.by_id(world, thread["thread_id"])
            if closed["status"] == "filled_by_other":
                filled += 1
                self.assertEqual(closed["filled_by_npc_id"], local["id"])
                self.assertEqual(closed["filled_by_name"], living_world.public_npc_name(local))
        self.assertGreaterEqual(filled, 24)

    def test_nobody_living_means_a_reserved_name_not_a_blank(self):
        for number in range(40):
            world, _ = walled(f"empty-{number}")
            thread = stage(world, "declined", expires_at=HOUR)
            world_threads.tick(world, 2 * HOUR)
            closed = world_threads.by_id(world, thread["thread_id"])
            if closed["status"] == "filled_by_other":
                self.assertTrue(closed["filled_by_name"])
                self.assertIsNone(closed["filled_by_npc_id"])
                return
        self.fail("no filled job in forty campaigns")

    def test_an_accepted_job_is_never_given_away(self):
        world, _ = walled()
        thread = stage(world, "accepted", type="errand", expires_at=HOUR, starts_at=0)
        world_threads.tick(world, 30 * DAY)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")

    def test_short_days_fail_a_hired_job_once_its_time_is_up(self):
        world, _ = walled()
        thread = stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=3 * DAY, days_worked=1)
        thread["terms"]["work_days"] = 2
        world_threads.tick(world, 3 * DAY)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")
        world_threads.tick(world, 3 * DAY + 1)
        closed = world_threads.by_id(world, thread["thread_id"])
        self.assertEqual((closed["status"], closed["closed_at"]), ("failed", 3 * DAY))

    def test_a_job_is_not_failed_while_the_shift_is_running(self):
        world, _ = walled()
        thread = stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=DAY, days_worked=0, shift_until=9 * DAY)
        thread["terms"]["work_days"] = 2
        world_threads.tick(world, 8 * DAY)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")

    def test_a_dead_owner_ends_the_job_without_blame(self):
        world, _ = walled()
        thread = stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=DAY)
        owner = person(world, "owner", thread["place_id"], combat_status="dead")
        world_threads.tick(world, HOUR)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "expired")
        self.assertNotIn(owner["id"], world.get("relationships", {}))

    def test_an_unconscious_owner_only_means_waiting(self):
        world, _ = walled()
        thread = stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=DAY)
        person(world, "owner", thread["place_id"], combat_status="unconscious")
        world_threads.tick(world, HOUR)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")

    def test_a_lost_place_ends_the_job_without_blame(self):
        world, _ = walled()
        thread = stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=DAY)
        place = world["locations"].pop(thread["place_id"])
        world_threads.tick(world, HOUR)
        world["locations"][thread["place_id"]] = place
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "expired")

    def test_one_seven_day_wait_is_seven_days_passing(self):
        def run(steps):
            world, _ = walled("week")
            thread = stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=2 * DAY, days_worked=0)
            thread["terms"]["work_days"] = 1
            for now in steps:
                world_threads.tick(world, now)
            return world_threads.by_id(world, thread["thread_id"])["closed_at"]
        self.assertEqual(run([7 * DAY]), run([d * DAY for d in range(1, 8)]))

    def test_one_broken_accepted_job_closes_alone(self):
        world, _ = walled()
        first, second = world[world_threads.KEY]["threads"][:2]
        stage(world, "accepted", expires_at=HOUR, starts_at="noon")
        world_threads.tick(world, HOUR)
        self.assertEqual(world_threads.by_id(world, first["thread_id"])["status"], "expired")
        self.assertEqual(world[world_threads.KEY]["last_tick"], HOUR)
        world_threads.validate(world[world_threads.KEY])
        self.assertIsNotNone(world_threads.by_id(world, second["thread_id"]))

    def test_nothing_outside_the_thread_is_written_when_the_state_cannot_be_kept(self):
        world, _ = walled()
        thread = stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=DAY)
        person(world, "owner", thread["place_id"], combat_status="dead")
        before = copy.deepcopy(world)
        with patch.object(world_threads, "validate", side_effect=ValueError("no")):
            world_threads.tick(world, HOUR)
        self.assertEqual(world, before)

    def test_a_save_without_the_new_fields_still_reads(self):
        world, state = walled()
        for thread in state["threads"]:
            thread["terms"] = {"pay": thread["terms"]["pay"], "work_days": thread["terms"]["work_days"]}
        world_threads.validate(state)
        world_threads.tick(world, HOUR)
        world_threads.validate(world[world_threads.KEY])

    def test_pay_basis_of_an_old_save_comes_from_its_kind(self):
        self.assertEqual(world_threads.pay_basis({"type": "hiring", "template_id": "hand_wanted", "terms": {}}), "daily")
        self.assertEqual(world_threads.pay_basis({"type": "hiring", "template_id": "gone", "terms": {}}), "total")
        self.assertEqual(world_threads.pay_basis({"type": "errand", "terms": {}}), "per_trip")

    def test_the_journal_closing_a_job_closes_the_thread_with_no_clock(self):
        world, _ = walled()
        thread = stage(world, "accepted", type="errand", expires_at=HOUR, starts_at=0, quest_id="job:one")
        owner = person(world, "owner", thread["place_id"])
        world["quests"] = [{"quest_id": "job:one", "status": "COMPLETED"}]
        world_threads.sync_from_quests(world)
        world_threads.sync_from_quests(world)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "done")
        self.assertEqual(world["relationships"][owner["id"]]["score"], 1)

    def test_a_job_the_player_touched_outlives_a_full_history(self):
        world, _ = walled()
        thread = stage(world, "accepted", type="errand", expires_at=HOUR, starts_at=0, quest_id="job:one")
        world["quests"] = [{"quest_id": "job:one", "status": "FAILED"}]
        world_threads.sync_from_quests(world)
        state = world[world_threads.KEY]
        for number in range(12):
            state["history"].append(dict(copy.deepcopy(thread), thread_id=f"later_{number}", offered_at=None,
                                         status="expired"))
        world_threads._trim_history(state)
        self.assertIsNotNone(world_threads.by_id(world, thread["thread_id"]))
        self.assertLessEqual(len(state["history"]), world_threads.MAX_HISTORY * 2)
        world_threads.validate(state)

    def test_a_reload_is_the_same_world(self):
        world, _ = walled()
        stage(world, "accepted", expires_at=HOUR, starts_at=0, work_until=DAY, days_worked=0)
        again = json.loads(json.dumps(world))
        self.assertEqual(again[world_threads.KEY], world[world_threads.KEY])
        world_threads.validate(again[world_threads.KEY])


class TheWorkOnOffer(unittest.TestCase):
    def test_nobody_offers_work_that_needs_a_second_place_yet(self):
        for template in world_threads.catalog()["templates"]:
            if template["type"] == "hiring":
                self.assertFalse(template.get("target_place_kinds"), template["id"])

    def test_a_debt_promises_nobody_money(self):
        debt = next(t for t in world_threads.catalog()["templates"] if t["id"] == "unpaid_debt")
        self.assertNotIn("pay", debt)
        self.assertNotIn("{pay}", " ".join(debt["owner_lines"]))

    def test_the_answer_words_are_loaded_for_all_four_meanings(self):
        table = world_threads.answer_table()
        self.assertIn(npc_statements.fold("Anlaştık"), table["accept"])
        self.assertIn(npc_statements.fold("Teklifi reddediyorum"), table["decline"])
        self.assertIn(npc_statements.fold("Anlaşmadan vazgeçtim"), table["withdraw"])
        self.assertIn(npc_statements.fold("önce parayı görelim"), table["unclear"])

    def test_every_errand_knows_what_it_carries_and_every_job_how_it_pays(self):
        for template in world_threads.catalog()["templates"]:
            if template["type"] == "errand":
                self.assertTrue(template.get("item_noun"), template["id"])
            if template["type"] == "hiring":
                self.assertIn(template.get("pay_basis"), {"daily", "total"}, template["id"])

    def test_catalog_outcomes_lose_their_bookkeeping_or_stay_out(self):
        for template in world_threads.catalog()["templates"]:
            for line in (template.get("status_lines") or {}).values():
                self.assertNotIn("{", line)
                self.assertNotIn("önerisi", line)
                self.assertNotIn("oyuncu", line.casefold())
                for word in ("otomatik", "varsay", "sayılmaz", "oluşmaz", "kendiliğinden"):
                    self.assertNotIn(word, line.casefold(), template["id"])
                self.assertTrue(line.endswith("."), line)


Q032 = "Of course, Father. Who is Haskula, where can I find them, and what exactly are the two groups asking for?"


class EnglishAnswers(unittest.TestCase):
    """Dilim 3D Task 3 (#032): an English yes or no to a shown offer reads like its Turkish twin."""

    def priest(self):
        return {"id": "npc_priest", "name": "Aldric", "role": "Rahip"}

    def meaning(self, line):
        return world_threads.read_answer(line, self.priest())["meaning"]

    def test_bare_english_answers(self):
        for line, meaning in (("Yes.", "accept"), ("Of course, Father.", "accept"), ("No.", "decline"),
                              ("Sure.", "accept"), ("I accept.", "accept"), ("I will do it.", "accept"),
                              ("I'll do it, sir.", "accept"), ("Agreed, madam.", "accept"),
                              ("No thanks.", "decline"), ("I decline.", "decline")):
            with self.subTest(line=line):
                self.assertEqual(self.meaning(line), meaning)

    def test_032_reads_like_its_turkish_twin(self):
        twin = "Tabii peder. Haskula kim, onu nerede bulurum, iki grup tam olarak ne istiyor?"
        self.assertEqual(self.meaning(twin), "accept")
        self.assertEqual(self.meaning(Q032), self.meaning(twin))

    def test_a_bare_yes_before_another_question_is_no_answer_in_either_tongue(self):
        self.assertIsNone(self.meaning("Evet. Haskula kim?"))
        self.assertIsNone(self.meaning("Yes. Where do I find Haskula?"))

    def test_not_sure_is_no_yes(self):
        self.assertIsNone(self.meaning("I'm not sure."))

    def test_address_words_leave_the_bare_turkish_answers_bare(self):
        table = world_threads.answer_table()
        for tokens in (["peki"], ["tamam"], ["evet"], ["peki", "father"], ["yes", "sir"]):
            with self.subTest(tokens=tokens):
                self.assertTrue(world_threads._bare_answer(tokens, table, frozenset()))
        self.assertFalse(world_threads._bare_answer(["of", "course"], table, frozenset()))
        self.assertFalse(world_threads._bare_answer(["tabii"], table, frozenset()))
