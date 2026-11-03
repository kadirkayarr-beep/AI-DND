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
    def test_close_effect_failure_changes_nothing(self):
        world, thread, _owner = failing_job()
        before_close = copy.deepcopy(world)
        with mock.patch.object(world_reactions, "promise_broken", side_effect=RuntimeError("second effect")):
            world_threads.tick(world, 2 * DAY)
        state_after_failed_close = world
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


if __name__ == "__main__":
    unittest.main()
