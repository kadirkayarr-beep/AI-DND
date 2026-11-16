"""D-100: a Faerûn guard does not answer "Aleykümselam". D-101: asked to describe the town, a person says more
than one thin sentence. Both are prompt and text fixes Kadir approved."""
import unittest

from api.tests import test_town_knowledge as cases
from api.tests.town_seed import fixed_town


class SpeechText(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = cases.ThroughTheRealTurn.asyncSetUp
    asyncTearDown = cases.ThroughTheRealTurn.asyncTearDown
    campaign_with_npc = cases.ThroughTheRealTurn.campaign_with_npc
    start = cases.ThroughTheRealTurn.start
    say = cases.ThroughTheRealTurn.say
    prompt_text = cases.ThroughTheRealTurn.prompt_text

    async def ready(self):
        with fixed_town(self, 2718):
            await self.start()

    async def test_a_real_world_religious_greeting_never_reaches_the_page(self):
        await self.ready()
        for reply in ("Aleykümselam, yolcu. Ne istiyorsun?", "Selamünaleyküm. Ne istiyorsun?",
                      "Ve aleyküm selam. İnşallah işin rast gider."):
            with self.subTest(reply=reply):
                text = await self.say("Selamünaleyküm!", reply)
                folded = text.replace("İ", "i").casefold()
                for word in ("aleyküm", "selamün", "inşallah"):
                    self.assertNotIn(word, folded)
                if "Ne istiyorsun?" in reply:  # the rest of the reply stays the person's own
                    self.assertIn("Ne istiyorsun?", text)

    async def test_the_prompt_names_the_words_this_world_does_not_use(self):
        await self.ready()
        await self.say("Selam.", "Selam.")
        prompt = self.prompt_text()
        for word in ("Aleykümselam", "inşallah"):
            self.assertIn(word, prompt)

    async def test_asked_to_describe_the_town_the_prompt_asks_for_more_than_one_line(self):
        await self.ready()
        await self.say("Bu nasıl şehir, bana anlatır mısın?", "Bir bakayım.")
        self.assertIn("iki ile dört cümle", self.prompt_text())


if __name__ == "__main__":
    unittest.main()
