"""Review fixes for task/d4-npc: a question about a woman is not a name question; "Allah'a emanet olun" is swapped
whole; the speech rules keep a space between sentences."""
import re
import unittest

import game
from api.tests import test_npc_never_bare_unknown as base


class ReviewFixes(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = base.NoBareUnknown.asyncSetUp
    asyncTearDown = base.NoBareUnknown.asyncTearDown
    campaign_with_npc = base.NoBareUnknown.campaign_with_npc
    start = base.NoBareUnknown.start
    say = base.NoBareUnknown.say
    ready = base.NoBareUnknown.ready
    assert_not_bare = base.NoBareUnknown.assert_not_bare

    async def test_asked_who_a_woman_is_a_person_passes_on_a_real_lead(self):
        await self.ready()
        for line in ("Bu kadın kim?", "Bu kadin kim?"):
            with self.subTest(line=line):
                text = await self.say(line)
                self.assert_not_bare(text)
                self.assertIn("Duyduğuma göre", text)

    def test_a_name_question_still_matches_as_a_whole_word(self):
        for line in ("adin ne", "kimsin sen", "ismin ne"):
            self.assertTrue(game._ASKS_WHO_YOU_ARE.search(line), line)
        for line in ("bu kadin kim", "kral adina geldim", "madin nerede"):
            self.assertFalse(game._ASKS_WHO_YOU_ARE.search(line), line)

    def test_a_real_world_farewell_is_swapped_whole(self):
        for said in ("Allah'a emanet olun.", "Allah’a emanet olun.", "Allah'a emanet ol."):
            with self.subTest(said=said):
                self.assertEqual(game._without_real_world_faith(said), "Tymora yar olsun.")

    def test_the_speech_rules_keep_a_space_between_sentences(self):
        self.assertIsNone(re.search(r"[a-zçğıöşü][.!?][A-ZÇĞİÖŞÜ]", game._SPEECH_ANSWER_RULES))


if __name__ == "__main__":
    unittest.main()
