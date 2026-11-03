"""A job the clock closes is closed whole: every effect lands, or the town is as it was."""

from __future__ import annotations

import copy
import unittest
from unittest import mock

import bold_acts
import relationships
import world_reactions
import world_threads
from api.tests.test_world_threads import city, person, stage

HOUR = 3600
DAY = 86400


def failing_job():
    """An accepted shift job the player never worked, so the clock fails it and the owner minds."""
    world = city("close-atomic")
    world_threads.ensure(world)
    thread = stage(world, "accepted", type="hiring", accepted_at=0, work_until=HOUR, days_worked=0)
    thread["terms"]["work_days"] = 1
    owner = person(world, "owner", thread["place_id"])
    thread["owner_npc_id"] = owner["id"]
    return world, thread, owner


def close_effect_count(world, thread, owner):
    reason = f"thread:{thread['thread_id']}:failed"
    noted = (world.get(relationships.KEY) or {}).get(owner["id"], {}).get("events", []).count(reason)
    deeds = [d for d in bold_acts.deeds(world) if d.get("kind") == "broken_promise" and d.get("victim_id") == owner["id"]]
    return noted, len(deeds)


class ThreadCloseAtomic(unittest.TestCase):
    def test_close_effect_failure_changes_nothing_but_the_failure_count(self):
        world, thread, _owner = failing_job()
        before_close = copy.deepcopy(world)
        with mock.patch.object(world_reactions, "promise_broken", side_effect=RuntimeError("second effect")):
            world_threads.tick(world, 2 * DAY)
        state_after_failed_close = copy.deepcopy(world)
        marker = world_threads.by_id(state_after_failed_close, thread["thread_id"]).pop(world_threads.CLOSE_FAILED)
        self.assertEqual(marker, {"count": 1, "error": "RuntimeError"})
        self.assertEqual(state_after_failed_close, before_close)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")
        self.assertEqual(world[world_threads.KEY]["last_tick"], before_close[world_threads.KEY]["last_tick"])

    def test_retry_applies_close_effect_once(self):
        world, thread, owner = failing_job()
        with mock.patch.object(world_reactions, "promise_broken", side_effect=RuntimeError("second effect")):
            world_threads.tick(world, 2 * DAY)
        world_threads.tick(world, 2 * DAY)
        world_threads.tick(world, 2 * DAY + 1)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "failed")
        close_effect_count_after_retry = close_effect_count(world, thread, owner)
        self.assertEqual(close_effect_count_after_retry, (1, 1))
        self.assertEqual(world[world_threads.KEY]["last_tick"], 2 * DAY + 1)

    def test_retry_clears_the_failure_count(self):
        world, thread, _owner = failing_job()
        with mock.patch.object(world_reactions, "promise_broken", side_effect=RuntimeError("second effect")):
            world_threads.tick(world, 2 * DAY)
        world_threads.tick(world, 2 * DAY + 1)
        closed = world_threads.by_id(world, thread["thread_id"])
        self.assertEqual(closed["status"], "failed")
        self.assertNotIn(world_threads.CLOSE_FAILED, closed)


class ABrokenCloseHoldsNoOneElseUp(unittest.TestCase):
    """A close that fails every time is parked after three tries; the rest of the town moves on."""

    def test_a_permanently_failing_close_is_parked_and_the_others_expire(self):
        world, thread, _owner = failing_job()
        other = world[world_threads.KEY]["threads"][1]
        other.update(status="offered", offered_at=0, offered_turn=1, expires_at=HOUR)
        real = world_reactions.promise_broken
        start = world[world_threads.KEY]["last_tick"]

        def broken_for_one(world_, thread_, owner, status):
            if thread_.get("thread_id") == thread["thread_id"]:
                raise RuntimeError("this close never lands")
            return real(world_, thread_, owner, status)

        with mock.patch.object(world_reactions, "promise_broken", side_effect=broken_for_one),                 self.assertLogs("world_threads", level="WARNING") as logs:
            for step in (1, 2):
                world_threads.tick(world, 2 * DAY + step)
                self.assertEqual(world_threads.by_id(world, other["thread_id"])["status"], "offered")
                self.assertEqual(world[world_threads.KEY]["last_tick"], start)
                self.assertEqual(world_threads.by_id(world, thread["thread_id"])[world_threads.CLOSE_FAILED],
                                 {"count": step, "error": "RuntimeError"})
            world_threads.tick(world, 2 * DAY + 3)
        stuck = world_threads.by_id(world, thread["thread_id"])
        self.assertEqual(stuck["status"], "accepted")  # never reported as closed
        self.assertEqual(stuck[world_threads.CLOSE_FAILED], {"count": 3, "error": "RuntimeError", "parked": True})
        self.assertTrue(world_threads.parked(stuck))
        self.assertIn(stuck, world[world_threads.KEY]["threads"])
        self.assertEqual(world_threads.by_id(world, other["thread_id"])["status"], "expired")
        self.assertEqual(world[world_threads.KEY]["last_tick"], 2 * DAY + 3)
        self.assertTrue(any("held back" in line and thread["thread_id"] in line for line in logs.output))
        later = copy.deepcopy(world)
        world_threads.tick(world, 3 * DAY)
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "accepted")
        self.assertEqual(world[world_threads.KEY]["last_tick"], 3 * DAY)
        self.assertNotEqual(later, world)


if __name__ == "__main__":
    unittest.main()
