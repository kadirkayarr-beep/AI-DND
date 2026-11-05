"""Task 18: player memory supports only that player's overlapping words."""
import unittest

import game
import npc_statements
import npc_told
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_npc_told import FACT, ChoosingClient


class ClaimOwnership(unittest.TestCase):
    def test_claim_about_sorts_with_the_existing_patterns(self):
        for text, expected in (
            ("Babamın işini sana söylemiştim", "own_words"),
            ("Sen bana dün bir hazine haritasından bahsetmiştin.", "npc_words"),
            ("Elaris bana ejderha hazinesinden bahsetmişti.", "npc_words"),
            ("Babamın ne iş yaptığını hatırlıyor musun?", "memory"),
        ):
            with self.subTest(text=text):
                self.assertEqual(npc_statements.claim_about(text), expected)

    def test_a_mixed_sentence_is_npc_words(self):
        self.assertEqual(npc_statements.claim_about(
            "Ben sana babamı söylemiştim, sen de bana yardım edeceğine söz vermiştin."), "npc_words")


class ToldClaims(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def setup_source(self, text=FACT):
        _, _, self.session, self.url, self.npc = await self.campaign_with_npc()
        client = ChoosingClient(True)
        response = await api.CampaignApiTests.post_scene_turn(self, self.url, client,
            speech.ExperimentalNpcDialogueTests.request(self.npc, message=text))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(npc_told.context_rows(self.session.world_state, self.npc["id"]), [text])

    async def claim(self, text, reply="Evet, söylediğin her şeyi hatırlıyorum."):
        client = speech.ScriptedNpcSpeechClient(narration=reply)
        response = await api.CampaignApiTests.post_scene_turn(self, self.url, client,
            speech.ExperimentalNpcDialogueTests.request(self.npc, message=text))
        self.assertEqual(response.status_code, 200, response.text)
        messages = "\n".join(m["content"] for batch in client.message_batches for m in batch)
        return response.json()["narration"], messages

    def assert_denied(self, narration):
        self.assertTrue(any(line.format(n=self.npc["name"]) in narration for line in game._CLAIM_DENIAL_LINES), narration)

    async def test_a_recall_backed_by_what_was_told_is_not_denied_or_replaced(self):
        await self.setup_source()
        reply = "Baban değirmenciydi, Yeşilova'da."
        narration, messages = await self.claim("Babamın ne iş yaptığını hatırlıyor musun?", reply)
        self.assertIn(reply, narration)
        self.assertIn(FACT, messages)
        self.assertFalse(any(line.format(n=self.npc["name"]) in narration for line in game._CLAIM_DENIAL_LINES))

    async def test_an_own_words_claim_with_no_overlap_keeps_the_denial(self):
        await self.setup_source()
        narration, messages = await self.claim("Sana ejderhanın yerini söylemiştim", "Evet, ejderhanın yerini söylemiştin.")
        self.assert_denied(narration)
        self.assertIn("Oyuncunun sana son söyledikleri (yalnız bağlam; bu sözle ilgisi belli değil):", messages)
        self.assertIn(FACT, messages)

    async def test_a_claim_sharing_one_generic_stem_shows_only_the_real_row(self):
        await self.setup_source()
        reply = "Babanın değirmenci olduğunu söylemiştin, ejderhayı değil."
        narration, messages = await self.claim("Sana babamın ejderha avladığını söylemiştim", reply)
        self.assertIn(reply, narration)
        header = "Oyuncunun sana daha önce söyledikleri (söylendi; doğruluğunu bilmezsin):"
        block = messages.split(header, 1)[1].split("»", 1)[0]
        self.assertIn(FACT, block)
        self.assertNotIn("ejderha", block)

    async def test_a_negated_row_reaches_the_npc_whole(self):
        fact = "Babam değirmenci değil, demirci."
        await self.setup_source(fact)
        narration, messages = await self.claim("Babamın işini sana söylemiştim", "Baban demirciydi.")
        self.assertIn(fact, messages)
        self.assertIn("Baban demirciydi.", narration)

    async def test_a_made_up_you_told_me_is_still_denied_even_when_my_words_overlap(self):
        await self.setup_source("Babam ejderha hazinesinden korkardı.")
        narration, _ = await self.claim("Sen bana dün bir ejderha hazinesinden bahsetmiştin.", "Evet, ejderha hazinesinden bahsetmiştim.")
        self.assert_denied(narration)

    async def test_a_mixed_claim_is_denied(self):
        await self.setup_source()
        narration, _ = await self.claim("Ben sana babamı söylemiştim, sen de bana yardım edeceğine söz vermiştin.",
                                        "Evet, babana yardım edeceğime söz vermiştim.")
        self.assert_denied(narration)

    async def test_a_general_what_did_i_say_question_keeps_the_denial(self):
        await self.setup_source()
        narration, _ = await self.claim("Geçen sefer ne demiştim?", "Babanın değirmenci olduğunu söylemiştin.")
        self.assert_denied(narration)

    async def test_a_made_up_claim_to_someone_with_no_record_is_denied(self):
        _, _, self.session, self.url, self.npc = await self.campaign_with_npc()
        narration, _ = await self.claim("Babamın ne iş yaptığını hatırlıyor musun?", "Baban değirmenciydi.")
        self.assert_denied(narration)
