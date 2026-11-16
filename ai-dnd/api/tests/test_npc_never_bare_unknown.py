"""D-237 / D-247 (K7, Kadir): a person whose reply could not be used does not end on a bare "I don't know".

They pass on a real lead the town has, or point at the place to ask; a stock "I don't know" and the job's
terms never sit in one answer.
"""
import unittest
from unittest.mock import patch

import interaction_adventure
import town_knowledge
from api.tests import test_town_knowledge as cases
from api.tests.town_seed import fixed_town

_BARE = tuple(line.split("“", 1)[1].rstrip("”") for line in interaction_adventure._UNKNOWN_LINES)


class NoBareUnknown(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = cases.ThroughTheRealTurn.asyncSetUp
    asyncTearDown = cases.ThroughTheRealTurn.asyncTearDown
    campaign_with_npc = cases.ThroughTheRealTurn.campaign_with_npc
    start = cases.ThroughTheRealTurn.start
    say = cases.ThroughTheRealTurn.say

    async def ready(self):
        with fixed_town(self, 2718):
            await self.start()
        await self.say("Selam.", "Selam.")
        self.client.narration = ""  # the model's reply cannot be used this turn

    def assert_not_bare(self, text):
        for bare in _BARE:
            self.assertNotIn(bare, text)

    async def test_asked_about_the_town_a_person_passes_on_a_real_lead(self):
        await self.ready()
        text = await self.say("Bu nasıl şehir, bana anlatır mısın?")
        self.assert_not_bare(text)
        self.assertIn("Duyduğuma göre", text)

    async def test_a_closed_mouthed_person_still_points_at_a_place_to_ask(self):
        await self.ready()
        world = self.session.world_state
        with patch.object(town_knowledge, "is_closed_mouthed", return_value=True):
            place = town_knowledge._brush_off_place(world, self.npc)
            self.assertTrue(place)
            text = await self.say("Burada ilginç bir şey duydun mu?")
        self.assert_not_bare(text)
        self.assertIn(place, text)

    async def test_a_speech_the_safety_check_rejects_still_passes_on_a_lead(self):
        with fixed_town(self, 2718):
            await self.start()
        await self.say("Selam.", "Selam.")
        text = await self.say("Burada ilginç bir söylenti var mı?",
                              "Eski mahzende kilitli bir sandık duruyor.")
        self.assert_not_bare(text)
        self.assertIn("Duyduğuma göre", text)

    async def test_a_question_about_the_person_is_not_answered_with_town_news(self):
        await self.ready()
        text = await self.say("Adın ne senin?")
        self.assertNotIn("Duyduğuma göre", text)

    async def test_the_job_terms_never_follow_a_stock_i_dont_know(self):
        await self.ready()
        terms = "Mektubu Ruvçina'ya götürürsün; ücret 14 bakır."
        with patch.object(town_knowledge, "is_closed_mouthed", return_value=True), \
                patch.object(town_knowledge, "_brush_off_place", return_value=""), \
                patch.object(town_knowledge, "terms_to_add", return_value=terms):
            text = await self.say("Bir mektup için birini arıyor musunuz?")
        self.assertIn(terms, text)
        self.assert_not_bare(text)


class ThePromptPointsOnward(unittest.IsolatedAsyncioTestCase):
    """D-248 (K7): the prompt no longer tells a person to stop at "I don't know"."""
    asyncSetUp = cases.ThroughTheRealTurn.asyncSetUp
    asyncTearDown = cases.ThroughTheRealTurn.asyncTearDown
    campaign_with_npc = cases.ThroughTheRealTurn.campaign_with_npc
    start = cases.ThroughTheRealTurn.start
    say = cases.ThroughTheRealTurn.say
    prompt_text = cases.ThroughTheRealTurn.prompt_text

    async def prompt_for(self, line):
        with fixed_town(self, 2718):
            await self.start()
        await self.say(line, "Bir bakayım.")
        return self.prompt_text()

    async def test_the_speech_prompt_asks_for_a_lead_not_a_bare_no(self):
        prompt = await self.prompt_for("Bu nasıl şehir, bana anlatır mısın?")
        for old in ("bilmiyorsan bilmediğini", "sorulursa bilmediğini söyle", "Bunlar sorulursa bilmediğini"):
            self.assertNotIn(old, prompt)
        self.assertIn("çıplak bir “bilmiyorum” ile bitirme", prompt)
        # the role's unknown topics no longer cover the town as a whole
        self.assertIn("Kentin genel hâli", prompt)

    async def test_a_person_who_heard_nothing_still_names_where_to_ask(self):
        with patch.object(town_knowledge, "public_knowledge", return_value=[]):
            prompt = await self.prompt_for("Burada ilginç bir şey duydun mu?")
        self.assertNotIn("sorulursa bilmediğini söyle", prompt)
        self.assertIn("kimin ya da nerenin bilebileceğini", prompt)

    async def test_a_job_seeker_is_sent_onward_not_told_no(self):
        prompt = await self.prompt_for("Burada nerede iş bulabilirim?")
        self.assertNotIn("yoksa bilmediğini söyle", prompt)
        self.assertIn("kimin ya da nerenin bilebileceğini", prompt)


if __name__ == "__main__":
    unittest.main()
