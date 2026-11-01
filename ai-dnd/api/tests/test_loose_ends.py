"""What a town's work comes to when the player talks the way people talk.

Every line here is the kind of thing typed in play. No real model is called.
"""
import unittest
from unittest.mock import patch

import campaign_time
import living_world
import world_threads
from adventure import dialogue_jobs

from api.tests import test_play_consequences as consequences
from api.tests import test_story_links as links
from api.tests import test_thread_gate as gate_tests
from api.tests.test_world_threads import DAY


class ATroubleFromAnOldSave(unittest.TestCase):
    def test_taken_on_and_left_it_still_comes_to_an_end(self):
        world, state = links.town_with_trouble()
        thread = links.thread_at(state)
        thread.pop("fires_at", None)
        thread["terms"]["work_days"] = None
        links.resident(world, thread["place_id"])
        self.assertTrue(world_threads.transition(thread, "offered"))
        self.assertTrue(world_threads.accept_hired(world, thread, 0))
        self.assertEqual(thread["terms"]["work_days"], 1)
        campaign_time.advance(world, 3 * DAY, "wait", "test")
        self.assertEqual(world_threads.by_id(world, thread["thread_id"])["status"], "failed")


class ReadingIsSomethingYouDo(consequences.Sealed):
    """Same table as the sealed letter tests, and only the lines that are not reading."""

    async def test_a_line_that_is_not_reading_leaves_the_seal_alone(self):
        for line in ("mektubu okumadım, mühür duruyor", "Ne yazık ki mektup elimde değil", "mektubu okumak istemiyorum",
                     "mektubu okudum sanma", "mektubu okuyamam", "mektubu okumayacağım", "mektubu yazanı tanıyor musun",
                     "mektupta ne yazıyor", "mektupta ne yazıyor?", "mektubu okuyayım mı"):
            await self.carrying()
            out = await self.line(line, "Hmm.")
            self.assertIsNone(self.thread.get("seal_broken"), line)
            self.assertNotIn("Kâğıtta", out["narration"], line)

    async def test_reading_it_for_real_still_reads_it(self):
        for line in ("mektubu okuyom", "mührü kırıp mektubu okudum", "mektubu okuyayım", "mektubu açıp okuyorum"):
            await self.carrying()
            out = await self.line(line, "Hmm.")
            self.assertIs(self.thread.get("seal_broken"), True, line)
            self.assertIn("Kâğıtta", out["narration"], line)

    async def test_a_question_with_someone_in_front_of_you_is_theirs_even_for_an_open_note(self):
        await self.carrying(template="meeting_note", noun="not")
        out = await self.line("notta ne yazıyor?", "Bilmem, kapalıydı.")
        self.assertNotIn("Kâğıtta", out["narration"])


if __name__ == "__main__":
    unittest.main()
