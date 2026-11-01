"""Threads that touch: a trouble comes to something on the clock, and what the player did changes what comes.

No model is called anywhere in here. Same seed, different choices, different story.
"""
import unittest

import campaign_time
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


if __name__ == "__main__":
    unittest.main()
