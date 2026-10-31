"""The narrator speaks to one player in present tense, in every prompt that writes narration."""

from __future__ import annotations

import unittest
import uuid

import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_free_attempts import NarratingClient


class SingularRepairTests(unittest.TestCase):
    def test_plural_address_turns_singular_in_narrator_text(self):
        for plural, singular in (
            ("Başlar size doğru dönüyor.", "Başlar sana doğru dönüyor."),
            ("Bakışlar sizi izliyor.", "Bakışlar seni izliyor."),
            ("Bakışlar üzerinizde kalıyor.", "Bakışlar üzerinde kalıyor."),
            ("Ayaklarınızın sesi yankılanıyor.", "Ayaklarının sesi yankılanıyor."),
            ("Şarkınız bitiyor.", "Şarkın bitiyor."),
            ("Çevrenizdeki sokak susuyor.", "Çevrendeki sokak susuyor."),
            ("Yakınınızda biri duruyor.", "Yakınında biri duruyor."),
            ("Hava üzerinize çöküyor.", "Hava üzerine çöküyor."),
            ("Kapıyı itiyorsunuz.", "Kapıyı itiyorsun."),
            ("Masaya tırmandınız.", "Masaya tırmandın."),
        ):
            with self.subTest(plural):
                self.assertEqual(game._singular_narrator(plural), singular)

    def test_an_npc_quote_keeps_its_own_address(self):
        text = "Görevli sana bakıyor: “Size yardım edebilirim, belgenizi görebilir miyim?” Üzerinizde durmuyor."
        self.assertEqual(
            game._singular_narrator(text),
            "Görevli sana bakıyor: “Size yardım edebilirim, belgenizi görebilir miyim?” Üzerinde durmuyor.",
        )

    def test_ordinary_words_stay(self):
        for text in ("Deniz sakin, yıldızlar parlıyor.", "Bir domuz sokaktan geçiyor.", "Kılavuz bekliyor.", "Yanıt yok."):
            with self.subTest(text):
                self.assertEqual(game._singular_narrator(text), text)


class NarratorVoiceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def play(self, client, message):
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, self.turn_url, client, {"message": message, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def narrator_systems(self, client):
        systems = []
        for batch, kind in zip(client.batches, client.kinds):
            if kind == "narration":
                systems.append(batch[0]["content"])
        return systems

    def test_the_paragraph_stays_short_and_keeps_npc_address_free(self):
        self.assertIn("tekil sen", game.NARRATOR_VOICE)
        self.assertIn("NPC hitabı serbesttir", game.NARRATOR_VOICE)
        self.assertLess(len(game.NARRATOR_VOICE.split()), 50, "measured at 113 Gemma tokens; the limit is 120")
        self.assertNotIn("hissediyorsun", game.NARRATOR_VOICE)

    def test_the_paragraph_names_the_forms_not_the_idea_of_a_tense(self):
        # Replayed on 8 real prompts: "şimdiki zamanda anlat" gave 31 past to 3 present lines, naming the forms 1 to 39.
        for form in ("-iyor", "-iyorsun", "-dı", "-mıştı", "-yordu"):
            self.assertIn(form, game.NARRATOR_VOICE)
        self.assertNotIn("geçmişi geçmiş zamanda", game.NARRATOR_VOICE)

    def test_the_paragraph_bars_the_third_person_word(self):
        self.assertIn("oyuncu kelimesini yazma", game.NARRATOR_VOICE)

    async def test_the_main_narration_prompt_carries_the_voice(self):
        _, _, self.session, self.turn_url, _ = await self.campaign_with_npc(experimental=False)
        client = NarratingClient()
        await self.play(client, "Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.")
        systems = self.narrator_systems(client)
        self.assertTrue(systems)
        self.assertTrue(all(game.NARRATOR_VOICE in text for text in systems))

    async def test_a_narrated_turn_is_repaired(self):
        _, _, self.session, self.turn_url, self.npc = await self.campaign_with_npc(experimental=False)
        client = NarratingClient(narration="Şarkınız sokakta yankılanıyor.")
        shown = (await self.play(client, "Yüksek sesle bir şarkı söylüyorum."))["narration"]
        self.assertIn("Şarkın sokakta", shown)
        self.assertNotIn("Şarkınız", shown)

    async def test_the_recorded_interaction_prompt_carries_the_voice(self):
        _, _, self.session, self.turn_url, _ = await self.campaign_with_npc(experimental=False)

        class Goal(NarratingClient):
            def chat(self, *args, **kwargs):
                properties = (kwargs.get("format") or {}).get("properties", {})
                if "intent" in properties:
                    self.kinds.append("classifier")
                    self.batches.append(list(kwargs.get("messages", [])))
                    return {"message": {"content": (
                        '{"intent":"interact","action":"search","target":{"type":"none","reference":""},'
                        '"completion":"intended","confidence":1.0,"interaction":{"operation":"goal",'
                        '"quote":"Sokakta önümde yürüyen adamın kesesine göz atıyorum.",'
                        '"thread_id":null,"evidence_id":null,"requested_item":null,"steps":[],"candidates":[]}}'
                    )}}
                return super().chat(*args, **kwargs)

        client = Goal(narration="Adamın kesesine göz atıyorsun.")
        await self.play(client, "Sokakta önümde yürüyen adamın kesesine göz atıyorum.")
        systems = self.narrator_systems(client)
        self.assertTrue(systems)
        self.assertTrue(all(game.NARRATOR_VOICE in text for text in systems), systems)


if __name__ == "__main__":
    unittest.main()
