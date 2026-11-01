"""Threads that touch: a trouble comes to something on the clock, and what the player did changes what comes.

No model is called anywhere in here. Same seed, different choices, different story.
"""
import unittest

import campaign_time
import town_knowledge
import world_happenings
import world_threads

from api.tests.test_world_threads import DAY, HOUR, city


def town(seed="seed-links"):
    world = city(seed)
    world_threads.ensure(world)
    return world, world[world_threads.KEY]


class TheClockComesFirst(unittest.TestCase):
    def test_a_long_wait_opens_new_threads_at_the_hour_it_ended(self):
        world, state = town()
        before = {t["thread_id"] for t in state["threads"]}
        campaign_time.advance(world, 7 * DAY, "rest", "test")
        now = world_threads._now(world)
        state = world[world_threads.KEY]
        fresh = [t for t in state["threads"] if t["thread_id"] not in before]
        self.assertTrue(fresh)
        for thread in fresh:
            self.assertEqual(thread["opened_at"], now)
            self.assertGreater(thread["expires_at"], now)

    def test_a_tick_on_its_own_says_what_time_it_is(self):
        world, state = town()
        before = {t["thread_id"] for t in state["threads"]}
        world_threads.tick(world, 7 * DAY)
        fresh = [t for t in world[world_threads.KEY]["threads"] if t["thread_id"] not in before]
        self.assertTrue(fresh)
        for thread in fresh:
            self.assertEqual(thread["opened_at"], 7 * DAY)


def thread_at(state, kind="trouble"):
    return next(t for t in state["threads"] if t["type"] == kind)


def resident(world, place_id, npc_id="sakin"):
    npc = {"id": npc_id, "name": npc_id.title(), "role": "usta", "location": place_id, "place_role_of": place_id}
    world["npcs"].append(npc)
    return npc


def town_with_trouble(start=0):
    """The first seed from here whose town opened with a trouble."""
    for number in range(start, start + 200):
        world, state = town(f"seed-trouble-{number}")
        if any(t["type"] == "trouble" for t in state["threads"]):
            return world, state
    raise AssertionError("no seed opened a trouble")


def fire(world, thread):
    """The clock reaches the moment. The record is read again by id: a step replaces the state."""
    world_threads.tick(world, thread["fires_at"])
    return world[world_threads.KEY], world_threads.by_id(world, thread["thread_id"])


class TheLedger(unittest.TestCase):
    def test_a_new_town_has_an_empty_ledger_and_an_old_save_gains_one(self):
        world, state = town()
        self.assertEqual(state["happenings"], [])
        del state["happenings"]
        world_threads.validate(state)
        world_threads.ensure(world)
        self.assertEqual(world[world_threads.KEY]["happenings"], [])

    def test_it_keeps_sixteen_and_refuses_a_damaged_row(self):
        world, state = town()
        thread = state["threads"][0]
        for at in range(20):
            world_happenings.write(state, thread, "visit", at, "Bir şey oldu.")
        self.assertEqual([row["at"] for row in state["happenings"]], list(range(4, 20)))
        world_threads.validate(state)
        state["happenings"][0]["kind"] = "savaş"
        with self.assertRaises(ValueError):
            world_threads.validate(state)
        state["happenings"][0].update(kind="visit", line="x" * 91)
        with self.assertRaises(ValueError):
            world_threads.validate(state)

    def test_it_is_not_a_deed_and_someone_nearby_says_it_with_its_label(self):
        world, state = town()
        thread = state["threads"][0]
        here = resident(world, thread["place_id"])
        world_happenings.write(state, thread, "closed", 0, "Dükkân kapanmış.")
        self.assertNotIn("deeds", world["flags"])
        self.assertEqual(town_knowledge.speech_note(world, here).count("Duyduğun: Dükkân kapanmış."), 1)

    def test_someone_across_town_does_not_hear_it_here(self):
        world, state = town()
        thread = state["threads"][0]
        other = next(t for t in state["threads"] if t["place_id"] != thread["place_id"])
        far = resident(world, other["place_id"])
        world_happenings.write(state, thread, "closed", 0, "Dükkân kapanmış.")
        self.assertNotIn("Duyduğun:", town_knowledge.speech_note(world, far))


class ATroubleComesToSomething(unittest.TestCase):
    def test_it_has_a_moment_and_cannot_quietly_run_out_before_it(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        self.assertGreater(thread["fires_at"], thread["opened_at"])
        self.assertEqual(thread["expires_at"], thread["fires_at"])

    def test_no_other_kind_of_thread_has_one(self):
        for number in range(12):
            _, state = town(f"seed-other-{number}")
            for thread in state["threads"]:
                self.assertEqual("fires_at" in thread, thread["type"] == "trouble")

    def test_it_stays_quiet_until_its_moment(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        world_threads.tick(world, thread["fires_at"] - 1)
        self.assertNotIn(thread["thread_id"], [r["thread_id"] for r in world[world_threads.KEY]["happenings"]])
        self.assertIn(world_threads.by_id(world, thread["thread_id"])["status"], world_threads.PUBLIC)

    def test_at_its_moment_it_happens_and_no_deed_is_written(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        state, closed = fire(world, thread)
        self.assertEqual(closed["status"], "fired")
        self.assertEqual(closed["closed_at"], thread["fires_at"])
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        self.assertIn(row["kind"], {"visit", "closed", "lost"})
        self.assertEqual(row["at"], thread["fires_at"])
        self.assertEqual(row["place_id"], thread["place_id"])
        self.assertNotIn("deeds", world["flags"])
        world_threads.validate(state)

    def test_nobody_is_named_and_every_line_fits_and_all_three_endings_turn_up(self):
        kinds = set()
        for number in range(40):
            world, state = town(f"seed-end-{number}")
            for thread in [t for t in state["threads"] if t["type"] == "trouble"]:
                state, _ = fire(world, thread)
                row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
                kinds.add(row["kind"])
                self.assertLessEqual(len(row["line"].encode("utf-8")), 90)
                self.assertNotIn("{", row["line"])
                self.assertNotIn(thread["owner_name"], row["line"])
        self.assertEqual(kinds, {"visit", "closed", "lost"})

    def test_one_that_was_turned_down_still_happens(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        thread.update(status="declined", declined_turn=1)
        state, closed = fire(world, thread)
        self.assertEqual(closed["status"], "fired")

    def test_a_save_from_before_keeps_the_old_way_of_closing(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        del thread["fires_at"]
        world_threads.tick(world, thread["expires_at"])
        self.assertIn(world_threads.by_id(world, thread["thread_id"])["status"], {"filled_by_other", "expired"})
        self.assertNotIn(thread["thread_id"], [r["thread_id"] for r in world[world_threads.KEY]["happenings"]])

    def test_a_person_in_town_can_tell_it_as_news_and_the_telling_counts(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        here = resident(world, thread["place_id"])
        state, _ = fire(world, thread)
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        news = [item for item in town_knowledge.public_knowledge(world, here) if item["kind"] == "news"]
        self.assertEqual([item["text"] for item in news if item["thread_id"] == thread["thread_id"]], [row["line"]])
        self.assertEqual(town_knowledge.speech_note(world, here).count(row["line"]), 1)
        town_knowledge.note_mention(world, here, row["line"])
        self.assertTrue(row["known_to_player"])

    def test_walking_up_to_the_place_afterwards_shows_it_once(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        state, _ = fire(world, thread)
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        self.assertFalse(row["known_to_player"])
        self.assertEqual(world_threads.arrival_line(world, thread["place_id"]), row["line"])
        self.assertTrue(row["known_to_player"])
        self.assertIsNone(world_threads.arrival_line(world, thread["place_id"]))

    def test_standing_there_when_it_happens_you_see_it(self):
        world, state = town_with_trouble()
        thread = thread_at(state)
        world["location"] = thread["place_id"]
        state, _ = fire(world, thread)
        row = next(r for r in state["happenings"] if r["thread_id"] == thread["thread_id"])
        self.assertTrue(row["known_to_player"])
        self.assertIn({"place": thread["place_id"], "line": row["line"]}, world["flags"]["reaction_lines"])


if __name__ == "__main__":
    unittest.main()
