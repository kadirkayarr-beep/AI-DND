"""The narrator speaks to one player in present tense, in every prompt that writes narration."""

from __future__ import annotations

import unittest
import uuid

import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_free_attempts import NarratingClient


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
        self.assertLess(len(game.NARRATOR_VOICE.split()), 40)
        self.assertNotIn("hissediyorsun", game.NARRATOR_VOICE)

    async def test_the_main_narration_prompt_carries_the_voice(self):
        _, _, self.session, self.turn_url, _ = await self.campaign_with_npc(experimental=False)
        client = NarratingClient()
        await self.play(client, "Masanın üstüne çıkıp yüksek sesle bir şarkı söylüyorum.")
        systems = self.narrator_systems(client)
        self.assertTrue(systems)
        self.assertTrue(all(game.NARRATOR_VOICE in text for text in systems))

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
