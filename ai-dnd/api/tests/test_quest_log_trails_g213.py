"""G2.13 (D-336, D-337): who and once for a trail, offered jobs in the journal."""

from __future__ import annotations

import unittest
from typing import Any

import living_world
import quest_log
import world_threads
from api.tests.test_town_knowledge import person, seeded


def _heard_thread_world(seed: str) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    """Build a hand-made town with its first thread and that place's owner."""
    world = seeded(seed)
    thread = world_threads.active(world)[0]
    owner = person("npc_owner", "Esnaf", place_role_of=thread["place_id"])
    owner["name"] = owner["public_name"] = thread["owner_name"]
    world["npcs"].append(owner)
    return world, thread, owner


def _duyulan(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in quest_log.trails(world) if row["source"] == "duyulan"]


class TrailWhoAndTwice(unittest.TestCase):
    """D-336."""

    def test_a_trail_the_owner_told_names_the_owner(self) -> None:
        """The heard trail of a job's own trouble carries its owner."""
        world, thread, owner = _heard_thread_world("g213-who")
        world_threads.mark_heard(thread, 2)
        [row] = _duyulan(world)
        self.assertEqual(row["what"], thread["public_line"])
        self.assertEqual(row["who"], living_world.public_npc_name(owner))

    def test_the_same_words_are_one_trail_not_two(self) -> None:
        """A heard rumour and a heard thread with one wording show once."""
        world, thread, _owner = _heard_thread_world("g213-twice")
        world_threads.mark_heard(thread, 2)
        other = person("npc_other", "Barmen")
        world["npcs"].append(other)
        world["heard_rumours"] = [{
            "id": "rumour_001", "text": thread["public_line"],
            "said_by": other["id"], "speakers": [other["id"]],
            "place_id": thread["place_id"], "settlement_id": "city", "turn": 3,
        }]
        rows = _duyulan(world)
        self.assertEqual([row["what"] for row in rows], [thread["public_line"]])
        self.assertIsNotNone(rows[0]["who"])


class OfferedJobShows(unittest.TestCase):
    """D-337."""

    def test_an_offered_job_is_in_the_journal_with_pay_and_days(self) -> None:
        """The terms the owner put to the player show until it is taken."""
        world, _thread, owner = _heard_thread_world("g213-offered")
        job = next(
            (t for t in world_threads.active(world)
             if t["type"] in {"hiring", "errand"} and t["terms"].get("pay")),
            None,
        )
        self.assertIsNotNone(job)
        world_threads.mark_offered(world, job, owner, job["owner_line"], 2)
        self.assertEqual(job["status"], "offered")
        trails = quest_log.view(world)["trails"]
        shown = [row for row in trails if job["owner_line"] in row["what"]]
        self.assertEqual(len(shown), 1, trails)
        self.assertIn(str(job["terms"]["pay"]), shown[0]["what"])
        if job["terms"].get("work_days"):
            self.assertIn(str(job["terms"]["work_days"]), shown[0]["what"])
        self.assertTrue(shown[0]["followed"])


if __name__ == "__main__":
    unittest.main()
