"""What the last long play tripped over, replayed with the player's own lines.

Each test goes through the HTTP turn with a mocked model, so it proves what
Python does on its own: no raw error, no second reading of the player's words.
"""

from api.tests.test_three_plays import FIGHTER, PlayClient, ThreePlaysTests

HOUR = 3600


class SecondRestTests(ThreePlaysTests):
    def elapsed(self):
        return self.world["campaign_time"]["elapsed_seconds"]

    async def rested(self):
        await self.begin(FIGHTER)
        await self.say("sabaha kadar uyuyorum")
        self.assertIn("last_long_rest_completed_at", self.world)
        self.session.character["current_hp"] = 12

    async def test_a_second_sleep_too_soon_is_a_story_and_gives_nothing(self):
        await self.rested()
        before = self.elapsed()
        out = await self.say("8 saat uyuyorum")
        self.assertEqual(self.session.character["current_hp"], 12, out["narration"])
        self.assertEqual(self.elapsed() - before, 8 * HOUR, out["narration"])
        self.assertTrue(out["narration"].strip())
        self.assertNotIn("16", out["narration"])

    async def test_a_rest_long_enough_to_cover_the_gap_is_a_real_rest(self):
        await self.rested()
        self.world["campaign_time"]["start_second"] = 7 * HOUR  # morning, as in the play
        before = self.elapsed()
        out = await self.say("bi gün ortadan kayboluyum en iyisi, 24 saat dinleniyorum")
        self.assertEqual(self.elapsed() - before, 24 * HOUR, out["narration"])
        self.assertEqual(self.session.character["current_hp"], self.session.character["max_hp"], out["narration"])
        self.assertEqual(self.world["last_long_rest_completed_at"], self.elapsed())

    async def test_the_line_from_the_play_gets_a_reply(self):
        await self.rested()
        out = await self.say("bi gün ortadan kayboluyum en iyisi, ertesi sabaha kadar dinleniyorum")
        self.assertTrue(out["narration"].strip())
