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


if __name__ == "__main__":
    unittest.main()
