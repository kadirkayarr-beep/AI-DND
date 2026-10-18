"""NPC P2 (conversation continuity) tests, written red-first.

The CONTINUITY tests failed on checkpoint 55ac8f7 (17 Oct live sample gaps) and
pass with the P2 fix. The GUARD tests passed before and must keep passing.
Scripted fake clients only: no real model call is made.
"""

from __future__ import annotations

import json
import unittest
import uuid

from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness

ScriptedNpcSpeechClient = harness.ScriptedNpcSpeechClient

FIRST_REPLY = "Kâtibim, kayıp mühür kayıtlarını aramak için buradayım."
FOLLOWUP = "Neden?"


class NpcP2ContinuityTests(unittest.IsolatedAsyncioTestCase):
    """Borrows the experimental harness helpers without re-running its tests."""

    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    campaign_with_npc = harness.ExperimentalNpcDialogueTests.campaign_with_npc
    sensitive_state = staticmethod(harness.ExperimentalNpcDialogueTests.sensitive_state)
    request = staticmethod(harness.ExperimentalNpcDialogueTests.request)

    @staticmethod
    def user_prompt(client, index):
        return next(
            item["content"]
            for item in reversed(client.message_batches[index])
            if item.get("role") == "user"
        )

    async def say(self, turn_url, client, npc, message):
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, self.request(npc, message=message)
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    # ---- CONTINUITY -----------------------------------------------------------

    async def test_continuity_followup_prompt_carries_previous_displayed_npc_reply(self):
        """T2/T5: 'Neden?' must reach the model with the NPC line the player saw."""
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        first = await self.say(turn_url, client, npc, "Kendini tanıtır mısın?")
        shown = first["narration"]
        self.assertTrue(shown.startswith("Marek"), shown)

        client.narration = "Çünkü arşiv bana emanet."
        await self.say(turn_url, client, npc, FOLLOWUP)

        self.assertEqual(client.chat_calls, 2)
        followup_prompt = self.user_prompt(client, 1)
        self.assertIn(
            FIRST_REPLY.rstrip("."), followup_prompt,
            "previous displayed NPC reply is absent from the follow-up prompt",
        )
        self.assertIn('"last_exchange":{"player":"Kendini tanıtır mısın?"', followup_prompt)

    async def test_continuity_exchange_pairs_are_labelled_and_last_one_is_marked(self):
        """Carried history is (player -> NPC) pairs, labelled speech-not-fact,
        and last_exchange names the pair a short follow-up refers to."""
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        await self.say(turn_url, client, npc, "Burada ne yapıyorsun?")
        client.narration = "Çünkü öyle gerekiyor."
        await self.say(turn_url, client, npc, "Yağmurda ne içersin?")
        client.narration = "Kahve, çünkü sıcak tutuyor."
        await self.say(turn_url, client, npc, "Neden onu?")

        prompt = self.user_prompt(client, 2)
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        context, _ = json.JSONDecoder().raw_decode(prompt.split(marker, 1)[1])
        self.assertEqual(context["conversation_status"], "attributed_speech_not_fact")
        self.assertEqual(len(context["conversation_so_far"]), 2)
        self.assertEqual(
            context["last_exchange"],
            {"player": "Yağmurda ne içersin?", "npc_reply": "Çünkü öyle gerekiyor."},
        )
        for fact_key in ("shareable_profile_facts", "perspective"):
            self.assertNotIn(
                "Çünkü öyle gerekiyor",
                json.dumps(context.get(fact_key, []), ensure_ascii=False),
                f"previous NPC speech must not be filed under {fact_key}",
            )

    async def test_continuity_conversation_survives_save_and_resume(self):
        """Exchanges live in the campaign state, not in process memory."""
        _, session_id, session, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        await self.say(turn_url, client, npc, "Kendini tanıtır mısın?")
        saved = session.serialize_game_state()["world_state"]
        log = saved["npc_speech_log"][npc["id"]]
        self.assertEqual(log[-1]["player"], "Kendini tanıtır mısın?")
        self.assertIn(FIRST_REPLY.rstrip("."), log[-1]["npc"])

    async def test_continuity_first_person_switch_can_come_from_environment(self):
        import os
        from unittest.mock import patch

        _, _, session, turn_url, npc = await self.campaign_with_npc(experimental=False)
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        with patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "1"}):
            await self.say(turn_url, client, npc, "Kendini tanıtır mısın?")
        self.assertEqual(set(client.schemas[0]["properties"]), {"narration"})

    # ---- IN-CHARACTER CLAIM HANDLING (no stock "no record" line) ---------------

    CLAIM = (
        "Dün bana yardım edersen yirmi altın vereceğini söylemiştin. "
        "Şimdi sözünü tutup altınları verir misin?"
    )
    ROBOTIC = ("belleğimde", "kayıt yok", "doğrulanmış", "kayıt")

    async def test_continuity_false_promise_gets_in_character_reply_from_model(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        client = ScriptedNpcSpeechClient(
            narration="Yirmi altın mı? Hayır dostum, ben öyle bir söz vermedim; "
                      "beni başkasıyla karıştırıyorsun."
        )
        reply = await self.say(turn_url, client, npc, self.CLAIM)
        self.assertEqual(client.chat_calls, 1)
        self.assertIn("başkasıyla karıştırıyorsun", reply["narration"])
        for phrase in self.ROBOTIC:
            self.assertNotIn(phrase, reply["narration"].casefold())
        self.assertEqual(self.sensitive_state(session), before)
        prompt = self.user_prompt(client, 0)
        self.assertIn('"player_claims_unrecorded_past_event":true', prompt)

    async def test_continuity_false_promise_acceptance_is_replaced_in_character(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        client = ScriptedNpcSpeechClient(narration="Tabii, söylemiştim. Al yirmi altın.")
        reply = await self.say(turn_url, client, npc, self.CLAIM)
        self.assertNotIn("Al yirmi altın", reply["narration"])
        self.assertTrue(reply["narration"].startswith("Marek"), reply["narration"])
        for phrase in self.ROBOTIC:
            self.assertNotIn(phrase, reply["narration"].casefold())
        self.assertEqual(self.sensitive_state(session), before)

    async def test_continuity_personal_opinion_request_reaches_the_model(self):
        """T3: a harmless personal-opinion question was blocked before any model call."""
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration="Bence nehir kıyısında yürümek iyi gelir.")
        reply = await self.say(
            turn_url, client, npc,
            "Sence bir yolcu bu şehirde boş bir öğleden sonrayı nasıl geçirebilir? "
            "Kendi fikrini söyle.",
        )
        self.assertEqual(client.chat_calls, 1, "request never reached the model")
        self.assertNotIn("güvenilir bir doğrulamam yok", reply["narration"])

    # ---- GUARD (pass today; the fix must not break them) ----------------

    async def test_guard_previous_reply_does_not_become_world_state(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        before = self.sensitive_state(session)
        await self.say(turn_url, client, npc, "Kendini tanıtır mısın?")
        client.narration = "Çünkü arşiv bana emanet."
        await self.say(turn_url, client, npc, FOLLOWUP)
        after = self.sensitive_state(session)
        for key in ("inventory", "items", "quests", "gold"):
            self.assertEqual(after[key], before[key], key)

    async def test_guard_private_and_other_npc_text_never_reaches_prompt(self):
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        await self.say(turn_url, client, npc, "Kendini tanıtır mısın?")
        client.narration = "Çünkü arşiv bana emanet."
        await self.say(turn_url, client, npc, FOLLOWUP)
        for index in range(client.chat_calls):
            prompt = self.user_prompt(client, index)
            for secret in (
                "PRIVATE_NPC_REPLY_SECRET_19ac",
                "PRIVATE_PROFILE_SECRET_71ef",
                "OTHER_NPC_MEMORY_SECRET_06ad",
                "OTHER_NPC_PERSPECTIVE_SECRET_7d21",
                "PRIVATE_PERSPECTIVE_SECRET_1a7b",
            ):
                self.assertNotIn(secret, prompt)

    async def test_guard_model_budget_stays_at_one_call_per_turn(self):
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        await self.say(turn_url, client, npc, "Kendini tanıtır mısın?")
        await self.say(turn_url, client, npc, FOLLOWUP)
        self.assertLessEqual(client.chat_calls, 2)

    async def test_speech_call_uses_lean_schema_and_non_greedy_sampling(self):
        """18 Oct live sample: the classifier schema and temperature 0.0 made the
        model put speech in interaction.quote and repeat filler in narration."""
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        captured = {}
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        original_chat = client.chat

        def recording_chat(*args, **kwargs):
            captured["options"] = kwargs.get("options")
            return original_chat(*args, **kwargs)

        client.chat = recording_chat
        await self.say(turn_url, client, npc, "Merhaba!")
        schema = client.schemas[0]
        self.assertEqual(set(schema["properties"]), {"narration"})
        self.assertNotIn("intent", schema["properties"])
        self.assertNotIn("interaction", schema["properties"])
        options = captured["options"]
        self.assertGreater(options["temperature"], 0.0)
        self.assertGreater(options.get("repeat_penalty", 1.0), 1.0)

    async def test_guard_exact_repeat_of_previous_speech_still_falls_back(self):
        """Repetition protection stays: the same line twice is not shown again."""
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        first = await self.say(turn_url, client, npc, "Kendini tanıtır mısın?")
        second = await self.say(turn_url, client, npc, FOLLOWUP)
        self.assertIn(FIRST_REPLY.rstrip("."), first["narration"])
        self.assertNotIn(FIRST_REPLY.rstrip("."), second["narration"])

    async def test_guard_fake_client_output_conforms_to_the_requested_schema(self):
        """The fixture itself must be schema-compliant (the 1fbec296 trap)."""
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration=FIRST_REPLY)
        await self.say(turn_url, client, npc, "Merhaba!")
        schema = client.schemas[0]
        self.assertIn("narration", schema.get("properties", {}))
        self.assertIn("narration", schema.get("required", []))


if __name__ == "__main__":
    unittest.main()
