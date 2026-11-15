"""D-067: a narrative cast moves no coin and no item, and the narrator may not say it did.

Three holes the 4C whole-branch review found: a line taking a thing off someone's body ("kolyeyi boynundan
çıkarıyorum") and a line cheating at dice were read as narrative casts (K2 sends money/item lines to today's paths);
a narrator line bringing a thing to the player ("El anahtarlığı sana getirir") passed the narrative-spell claim guard;
and the narrator's item_claims on a narrative cast were never settled, so the sentence the prompt promises to drop
stayed. On a narrative cast an item claim is never committed (the spell moves nothing): its sentence leaves the line.

Fixtures: test_dilim4c_5_narrative_spells (CampaignApiTests with `fixed_town`, a Wizard with Mage Hand and free hands);
the narrator is test_said_is_real.ClassifiedClient (its narration and item_claims are scripted)."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import spell_effects
from api.tests import test_dilim4c_5_narrative_spells as spell_tests
from api.tests.test_said_is_real import ClassifiedClient


class NoNarrativeCast(unittest.TestCase):
    def test_taking_off_a_body_and_cheating_at_dice_go_on_to_todays_paths(self):
        for line in ("Mage Hand ile kolyeyi boynundan çıkarıyorum", "Mage Hand ile yüzüğü parmağından çekiyorum",
                     "Mage Hand ile tılsımı kemerinden çözüyorum", "I use Mage Hand to lift the necklace off his neck",
                     "Prestidigitation ile zarları hileli yapıyorum", "Prestidigitation ile zarı altıya çeviriyorum",
                     "I cast Prestidigitation to cheat at dice"):
            with self.subTest(line):
                self.assertIsNone(spell_effects.named(line))

    def test_pure_effects_near_those_words_still_cast(self):
        for line, spell in (("Minor Illusion ile kulağına bir fısıltı gönderiyorum", "Minor Illusion"),
                            ("Minor Illusion ile bir kedi sesi çıkarıyorum", "Minor Illusion"),
                            ("Mage Hand ile kapının mandalını kaldırıyorum", "Mage Hand")):
            with self.subTest(line):
                self.assertEqual(spell_effects.named(line), ("narrative", spell))

    def test_a_body_or_a_name_with_no_taking_still_casts(self):
        # Review of D-067: 'göğsünden ışık', an arch ('kemerden') and the name 'Zara' take nothing and stake nothing.
        for line, spell in (("Minor Illusion ile göğsünden ışık yayılan bir hayalet yaratıyorum", "Minor Illusion"),
                            ("Minor Illusion ile kemerden sarkan bir fener yaratıyorum", "Minor Illusion"),
                            ("Prestidigitation ile Zara'nın saçını kurutuyorum", "Prestidigitation"),
                            ("I cast Minor Illusion to make light glow from his neck", "Minor Illusion")):
            with self.subTest(line):
                self.assertEqual(spell_effects.named(line), ("narrative", spell))

    def test_a_spark_brought_out_of_a_body_is_an_effect_not_a_theft(self):
        # Second review of D-067: 'çıkarmak' is also 'to make, to bring forth'; a spark, flame or smoke drawn from a
        # body takes nothing. A thing drawn from it ('bir kese') still goes on to today's paths.
        for line in ("Prestidigitation ile kemerinden bir kıvılcım çıkarıyorum",
                     "Prestidigitation ile parmağından bir alev çıkarıyorum",
                     "Prestidigitation ile kulağından duman çıkarıyorum"):
            with self.subTest(line):
                self.assertEqual(spell_effects.named(line), ("narrative", "Prestidigitation"))
        for line in ("Mage Hand ile kemerinden bir kese çıkarıyorum", "Mage Hand ile boynundan zinciri çıkarıyorum"):
            with self.subTest(theft=line):
                self.assertIsNone(spell_effects.named(line))


class NarratorBringsNothing(unittest.TestCase):
    def test_a_thing_brought_to_the_player_is_a_claim(self):
        for line in ("El anahtarlığı sana getirir.", "Hayalet el kolyeyi sana uzatır.", "El, yüzüğü sana bırakır.",
                     "Kolye artık sende.", "The spectral hand brings the key to you.",
                     "El kolyeyi sana doğru getirir.", "Anahtarlık artık elinde.", "Kolye sende kalır.",
                     "El, yerdeki ipi kucağına bırakır.", "El, kolyeyi getirip kucağına koyar."):
            with self.subTest(line):
                self.assertTrue(spell_effects.claims_state_change(line))

    def test_plain_effects_toward_the_player_pass(self):
        for line in ("Hayalet el sana el sallar ve kaybolur.", "Kulağına bir fısıltı süzülür.",
                     "Sana doğru tatlı bir ılıklık yayılır.", "The hand waves at you and fades.",
                     "Bütün gözler sende.", "Sende tuhaf bir ürperti var."):
            with self.subTest(line):
                self.assertFalse(spell_effects.claims_state_change(line))


class NarratorItemClaimOnACast(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = spell_tests.NarrativeSpellHttp.asyncSetUp
    asyncTearDown = spell_tests.NarrativeSpellHttp.asyncTearDown
    campaign = spell_tests.NarrativeSpellHttp.campaign
    post = spell_tests.NarrativeSpellHttp.post
    stored = spell_tests.NarrativeSpellHttp.stored
    ledger = spell_tests.NarrativeSpellHttp.ledger

    async def cast(self, seed, narration, claims):
        campaign, record = await self.campaign(seed)
        s = record.game_session
        # A rope really lies here: a committed claim would move it, so its staying here is the proof.
        s.world_state.setdefault("ground_items_by_location", {}).setdefault(s.world_state["location"], []).append(
            {"item_id": "item_ip", "name": "Ip"})
        self.client = ClassifiedClient(narration)
        self.client.narrator_extra = {"item_claims": claims} if claims is not None else {}
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        before = (self.ledger(s), copy.deepcopy(s.world_state["ground_items_by_location"]))
        reply = await self.post(campaign, {"message": "Mage Hand ile kapının mandalını kaldırıyorum",
                                           "action_id": str(uuid4())})
        self.assertEqual(reply.status_code, 200, reply.text)
        body = reply.json()
        self.assertEqual([fact["spell_id"] for fact in s.world_state[spell_effects.KEY]], ["Mage Hand"])
        self.assertEqual((self.ledger(s), s.world_state["ground_items_by_location"]), before)  # nothing moved
        self.assertNotIn("Ip", str(self.stored(campaign).get("inventory")))
        return body

    async def test_a_claimed_thing_leaves_the_line_and_is_never_committed(self):
        body = await self.cast(4601, "Hayalet el mandalı yukarı iter. El, yerdeki ipi kucağına bırakır.",
                               [{"item": "ip", "to": "player"}])
        self.assertNotIn("ipi", body["narration"])
        self.assertIn("mandalı yukarı iter", body["narration"])

    async def test_a_thing_told_as_given_away_leaves_the_line(self):
        body = await self.cast(4602, "Hayalet el mandalı yukarı iter. El, halkanı muhafıza götürür.",
                               [{"item": "halka", "to": "person"}])
        self.assertNotIn("halkan", body["narration"])
        self.assertIn("mandalı yukarı iter", body["narration"])

    async def test_a_line_that_was_all_claim_is_the_python_line(self):
        body = await self.cast(4603, "El, yerdeki ipi kucağına bırakır.", [{"item": "ip", "to": "player"}])
        self.assertIn("Büyücü Eli (Mage Hand)", body["narration"])
        self.assertNotIn("ipi", body["narration"])

    async def test_a_thing_brought_with_no_claim_is_the_python_line(self):
        body = await self.cast(4604, "Hayalet el mandalı kaldırır. El anahtarlığı sana getirir.", None)
        self.assertIn("Büyücü Eli (Mage Hand)", body["narration"])
        self.assertNotIn("anahtarlığı", body["narration"])

    async def test_a_true_line_with_no_claim_stays(self):
        body = await self.cast(4605, "Hayalet el süzülür ve mandalı yukarı iter.", [])
        self.assertIn("mandalı yukarı iter", body["narration"])


if __name__ == "__main__":
    unittest.main()
