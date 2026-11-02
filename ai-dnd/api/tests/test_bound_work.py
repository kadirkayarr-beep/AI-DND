"""A shift shows a line of that work in that place; the line moves no coin and no clock.

Real app, real engine; lines are typed the way the owner types them.
"""

from __future__ import annotations

import copy

import bound_text
import world_threads
from api.tests.test_front_proposal import FrontTable

HOUR = 3600


class Shifts(FrontTable):
    def lines(self, kind, place):
        return {row["text"]: row for row in bound_text.items("work_lines")
                if row["work_kind"] == kind and place in row["place_tags"]}

    async def a_job(self, template="THR041", place_kind="harbor"):
        await self.begin()
        self.world["locations"][self.place_id].update(place_kind=place_kind)
        self.thread.update(template_id=template, status="accepted", accepted_at=0, accepted_turn=0,
                           work_until=30 * 86400, owner_npc_id=self.npc["id"])
        self.client.front = {"kind": "work", "job_id": self.thread["thread_id"]}

    async def test_a_day_of_counting_at_the_harbor_shows_a_counting_line_of_the_harbor(self):
        await self.a_job()
        reply = await self.line("aksama kadar yukleri sayiyorum")
        self.assertTrue(any(line in reply["narration"] for line in self.lines("sayim", "liman")), reply["narration"])

    async def test_the_coin_is_the_job_s_and_the_line_says_none(self):
        await self.a_job()
        reply = await self.line("aksama kadar yukleri sayiyorum")
        self.assertEqual(world_threads.by_id(self.world, self.thread["thread_id"])["days_worked"], 1)
        self.assertIn("bakır", reply["narration"])
        self.assertFalse(any("bakır" in row["text"] for row in bound_text.items("work_lines")))

    async def test_two_days_show_two_lines(self):
        await self.a_job()
        first = bound_text.work_line(self.world, self.thread, 8 * HOUR, 0)
        second = bound_text.work_line(self.world, self.thread, 8 * HOUR, 1)
        self.assertNotEqual(first, second)
        self.assertEqual(bound_text.work_line(self.world, self.thread, 8 * HOUR, 0), first)

    async def test_a_short_stint_takes_a_short_line(self):
        await self.a_job(template="THR042")
        line = bound_text.work_line(self.world, self.thread, 2 * HOUR, 0)
        self.assertEqual(self.lines("tasima", "liman")[line]["time_phrase"], "kisa")

    async def test_a_job_with_no_line_for_its_place_keeps_the_old_words(self):
        await self.a_job(template="THR041", place_kind="bakery")
        reply = await self.line("aksama kadar yukleri sayiyorum")
        self.assertFalse(any(row["text"] in reply["narration"] for row in bound_text.items("work_lines")))
        self.assertTrue(reply["narration"].strip())

    async def test_choosing_a_line_writes_nothing(self):
        await self.a_job()
        before = copy.deepcopy(self.world)
        bound_text.work_line(self.world, self.thread, 8 * HOUR, 0)
        self.assertEqual(self.world, before)

    async def test_a_job_that_ended_mid_shift_shows_no_work_line(self):
        await self.a_job()
        self.thread["status"] = "fired"
        self.assertIsNone(bound_text.work_line(self.world, self.thread, 8 * HOUR, 0))

    async def test_no_time_passed_is_no_work_shown(self):
        await self.a_job()
        self.assertIsNone(bound_text.work_line(self.world, self.thread, 0, 0))

    async def test_every_job_done_on_the_spot_has_a_kind_of_work(self):
        await self.begin()
        table = bound_text.rules()["work_kinds"]
        for template in world_threads.catalog()["templates"]:
            spot = template["type"] == "hiring" or (template["type"] == "trouble" and not template.get("target_place_kinds"))
            if spot:
                self.assertIn(template["id"], table)
