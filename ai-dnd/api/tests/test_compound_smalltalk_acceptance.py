"""Job3: existing compound route and paired follow-up acceptance."""
import copy
import unittest
from unittest.mock import patch

import game
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech


class CompoundSmalltalkAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def post(self, url, client, body):
        response = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def establish(self):
        _, _, session, url, npc = await self.campaign_with_npc()
        client = speech.ScriptedNpcSpeechClient("Unused.")
        response = await self.post(url, client, {"message": "Adın ne?", "target_id": npc["id"]})
        self.assertEqual(client.chat_calls, 0)
        self.assertIn(npc["name"], response["narration"])
        return session, url, npc

    async def test_compound_name_day_survives_omitted_do_say(self):
        for mode in (None, "do", "say"):
            with self.subTest(mode=mode):
                session, url, npc = await self.establish()
                reply = "Adım Marek. Günüm sakin geçiyor."
                client = speech.ScriptedNpcSpeechClient(reply)
                body = {"message": "Adın neydi, bir de günün nasıl geçiyor?"}
                if mode is not None:
                    body["interaction_mode"] = mode
                result = await self.post(url, client, body)
                self.assertIn(reply, result["narration"])
                self.assertEqual(client.chat_calls, 1)
                self.assertIn("spoken_text", client.schemas[0]["properties"])
                self.assertEqual(session.world_state["flags"]["active_npc_id"], npc["id"])

    async def test_preference_then_why_uses_same_pair_without_profile_promotion(self):
        for mode in (None, "do", "say"):
            with self.subTest(mode=mode):
                session, url, npc = await self.establish()
                profile = copy.deepcopy(npc["personal_profile"])
                character = copy.deepcopy(session.character)
                inventory = copy.deepcopy(session.world_state["inventory"])
                question = "İnsanlarla sohbet etmeyi mi seversin, tek başına kalmayı mı?"
                reply = "İnsanlarla sohbet etmeyi tercih ederim."
                client = speech.ScriptedNpcSpeechClient(reply)
                body = {"message": question}
                if mode is not None:
                    body["interaction_mode"] = mode
                first = await self.post(url, client, body)
                self.assertIn(reply, first["narration"])
                self.assertEqual(client.chat_calls, 1)
                pair = copy.deepcopy(session.world_state["npc_speech_log"][npc["id"]][-1])
                contexts = []
                original = game._experimental_npc_dialogue_context
                def capture(*args, **kwargs):
                    result = original(*args, **kwargs)
                    contexts.append(copy.deepcopy(result))
                    return result
                follow = speech.ScriptedNpcSpeechClient("Çünkü sohbet etmek hoşuma gidiyor.")
                with patch.object(game, "_experimental_npc_dialogue_context", side_effect=capture):
                    second = await self.post(url, follow, {**body, "message": "Peki neden?"})
                self.assertIn(follow.narration, second["narration"])
                self.assertEqual(follow.chat_calls, 1)
                self.assertEqual(contexts[-1]["last_exchange"], {"player": question, "npc_reply": pair["npc"]})
                self.assertEqual(profile, npc["personal_profile"])
                self.assertEqual(character, session.character)
                self.assertEqual(inventory, session.world_state["inventory"])

