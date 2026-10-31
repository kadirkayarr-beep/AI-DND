"""A name question is answered through Python state, and speech answers the question asked."""

from __future__ import annotations

import unittest
import uuid

import living_world
import relationships
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech

ScriptedNpcSpeechClient = speech.ScriptedNpcSpeechClient


class NameAnswerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def stranger(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc(experimental=False)
        npc["name_known_to_player"] = False
        npc["role_known_to_player"] = False
        return session, turn_url, npc

    async def say(self, turn_url, client, npc, message):
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client,
            {"message": message, "interaction_mode": "say", "target_id": npc["id"],
             "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"]

    @staticmethod
    def speech_prompt(client):
        return "\n".join(item["content"] for item in client.message_batches[-1])

    async def test_the_model_is_told_its_name_before_it_answers_a_name_question(self):
        session, turn_url, npc = await self.stranger()
        client = ScriptedNpcSpeechClient(narration="Adım Marek, hoş geldin.")
        shown = await self.say(turn_url, client, npc, "Selamlar, ismin nedir, bugün yorgun musun?")
        self.assertIn("Adın Marek", self.speech_prompt(client))
        self.assertTrue(npc["name_known_to_player"])
        self.assertEqual(shown, "Marek: “Adım Marek, hoş geldin.”")

    async def test_a_reply_that_dodges_the_name_is_repaired_by_python(self):
        for dodge in ("Benim adım yok, sadece burada işimi yapıyorum.", "Adım önemli değil.", "Adım... benim adım."):
            with self.subTest(dodge=dodge):
                session, turn_url, npc = await self.stranger()
                client = ScriptedNpcSpeechClient(narration=dodge)
                shown = await self.say(turn_url, client, npc, "Selamlar, ismin nedir, burada mı çalışıyorsun?")
                self.assertTrue(npc["name_known_to_player"])
                self.assertIn("Adım Marek", shown)
                self.assertNotIn("önemli değil", shown)
                self.assertNotIn("adım yok", shown)

    async def test_a_name_question_does_not_reveal_the_role(self):
        session, turn_url, npc = await self.stranger()
        await self.say(turn_url, ScriptedNpcSpeechClient(narration="Adım Marek."), npc, "Adın ne?")
        self.assertTrue(npc["name_known_to_player"])
        self.assertFalse(npc["role_known_to_player"])
        session, turn_url, npc = await self.stranger()
        shown = await self.say(turn_url, ScriptedNpcSpeechClient(narration="Adım Marek."), npc, "Bu arada adın ne, nerelisin?")
        self.assertFalse(npc["role_known_to_player"])
        self.assertNotIn("Kent sakini", shown)

    async def test_an_npc_with_a_reason_keeps_the_name_and_the_descriptive_label(self):
        for setup in (
            lambda s, n: n.__setitem__("name_withheld_reason", "seni tanımıyor ve kuşkulanıyor"),
            lambda s, n: relationships.note(s.world_state, n["id"], -2, "Oyuncu ona saldırdı."),
        ):
            session, turn_url, npc = await self.stranger()
            setup(session, npc)
            client = ScriptedNpcSpeechClient(narration="Bunu sana söyleyecek değilim.")
            for message in ("Selamlar, ismin nedir, bugün yorgun musun?", "Adın ne?"):
                shown = await self.say(turn_url, client, npc, message)
                self.assertFalse(npc["name_known_to_player"])
                self.assertNotIn("Marek", shown)
                self.assertNotIn("Marek", self.speech_prompt(client))
                self.assertIn("Adını söylemek istemiyorsun", self.speech_prompt(client))

    async def test_a_third_person_name_question_is_not_about_the_addressee(self):
        session, turn_url, npc = await self.stranger()
        client = ScriptedNpcSpeechClient(narration="Hangisini soruyorsun?")
        await self.say(turn_url, client, npc, "Peki ismi nedir?")
        self.assertFalse(npc["name_known_to_player"])

    async def test_the_prompt_says_who_speaks_and_to_answer_the_question_first(self):
        session, turn_url, npc = await self.stranger()
        client = ScriptedNpcSpeechClient(narration="Bilmiyorum, hanı sormayı dene.")
        await self.say(turn_url, client, npc, "Burada nerede iş bulabilirim?")
        prompt = self.speech_prompt(client)
        self.assertIn("Önce oyuncunun sorusunu cevapla", prompt)
        self.assertIn("kendine iş arıyor", prompt)
        self.assertNotIn("Arşivde kâtiplik yapıyorum", prompt)
        self.assertLess(prompt.index("Önce oyuncunun sorusunu cevapla"), prompt.index("Current player message"))

    async def test_an_unasked_stranger_is_told_not_to_introduce_itself(self):
        session, turn_url, npc = await self.stranger()
        client = ScriptedNpcSpeechClient(narration="Güzel bir gün.")
        await self.say(turn_url, client, npc, "Hava nasıl sence?")
        prompt = self.speech_prompt(client)
        self.assertNotIn("Marek", prompt)
        self.assertIn("kendine ad uydurma", prompt)
        self.assertFalse(npc["name_known_to_player"])


class FreeDialogueNameTests(unittest.TestCase):
    def test_a_name_counts_as_spoken_only_as_a_first_person_claim(self):
        import npc_speech_boundary as b
        self.assertTrue(b.claims_own_name("Adım Yara, memnun oldum.", "Yara"))
        self.assertTrue(b.claims_own_name("Bana Yara derler.", "Yara"))
        self.assertTrue(b.claims_own_name("Ben Marek'im.", "Marek"))
        self.assertFalse(b.claims_own_name("Bu sana yarar.", "Yara"))
        self.assertFalse(b.claims_own_name("Yaralı biri geçti buradan.", "Yara"))
        self.assertFalse(b.claims_own_name("Adım Yara değil.", "Yara"))

    def test_a_hidden_name_is_repaired_out_of_a_stage_direction(self):
        import npc_speech_boundary as b
        npc = {"id": "n1", "name": "Marek", "name_known_to_player": False, "visible_trait": "kır saçlı"}
        label = living_world.public_npc_name(npc)
        self.assertEqual(b.hide_unknown_name("Marek omuz silkiyor.", npc), f"{label} omuz silkiyor.")


if __name__ == "__main__":
    unittest.main()
