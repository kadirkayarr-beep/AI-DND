"""4B.5: a plain English yes takes an offered job; refusals and questions do not; Turkish is unchanged."""

from __future__ import annotations

import unittest

import world_threads
from api.tests.test_thread_offer import offered

SEED = "4851"  # the town of this test is fixed: one world per call, from this id, never random
ENGLISH_OFFER = "Twenty copper, two days. The work is yours if you want it."


class EnglishJobAccept(unittest.TestCase):
    def offer(self, kind="hiring"):
        world, thread, npc = offered(SEED, kind=kind, last=ENGLISH_OFFER)
        return world, thread, npc

    def decide(self, line):
        world, thread, npc = self.offer()
        return world_threads.bind_player_decision(world, thread, line, npc)

    def test_english_yeses_take_the_job_and_write_it_to_the_journal(self):
        for line in ("Of course", "Yes, I'll do it", "Sure, I'll take the job", "Yes", "Sure", "I accept"):
            world, thread, npc = self.offer()
            self.assertEqual(world_threads.bind_player_decision(world, thread, line, npc), "accepted", line)
            self.assertTrue(world_threads.apply_decision(world, thread, "accepted", 4), line)
            self.assertEqual(thread["status"], "accepted", line)
            self.assertIn(thread["thread_id"], [t["thread_id"] for t in world[world_threads.KEY]["threads"]], line)

    def test_english_refusals_and_questions_take_nothing(self):
        for line in ("No thanks", "Of course not", "Is it dangerous?", "No"):
            world, thread, npc = self.offer()
            self.assertNotEqual(world_threads.bind_player_decision(world, thread, line, npc), "accepted", line)
            self.assertEqual(thread["status"], "offered", line)

    def test_a_refusal_is_not_mistaken_for_a_yes_by_the_yes_reader(self):
        for line in ("No thanks", "Of course not", "Is it dangerous?"):
            world, thread, npc = self.offer()
            self.assertFalse(world_threads.holds_a_yes(line, npc, thread), line)

    def test_turkish_is_unchanged(self):
        world, thread, npc = offered(SEED)
        self.assertEqual(world_threads.bind_player_decision(world, thread, "Tamam, yaparım", npc), "accepted")


if __name__ == "__main__":
    unittest.main()
