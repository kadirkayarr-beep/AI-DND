"""D-249 F4/E9: the person a line is said to gets it; a shop line is never printed twice."""

from __future__ import annotations

import os
import unittest
import uuid
from unittest.mock import patch

import game
import local_dialogue
from api import ollama_adapter
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.town_seed import fixed_town

TOWN_SEED = 4101
SPOKEN = "Çizelgeyi sabah ben yazdım, başka bir şey bilmem."


def guard(npc_id, name):
    return {"id": npc_id, "name": name, "public_name": name, "role": "Nöbetçi çavuş",
            "reality_layer": "PROCEDURAL_LOCAL_FICTION", "relationship": "neutral", "knowledge": [],
            "combat_status": "active", "current_hp": 12, "status": "active", "memory": []}


class UnitVocative(unittest.TestCase):
    def test_a_role_word_vocative_is_not_an_unknown_name(self):
        npc = guard("npc_g1", "Hadrik")
        self.assertIsNone(local_dialogue.unresolved_named_address("Çavuş, bu gece nöbette kim var?", [npc]))
        self.assertEqual(local_dialogue.unresolved_named_address("Garrick, bu gece nöbette kim var?", [npc]),
                         "Garrick")


class AddressedLines(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def start(self, *guards):
        self.enterContext(patch.dict(os.environ))
        os.environ.pop("AI_DND_NPC_SPEECH", None)
        with fixed_town(self, TOWN_SEED):
            city_id, self.session_id, self.session, self.turn_url, marek = await self.campaign_with_npc(
                experimental=False)
        world = self.session.world_state
        self.marek = next(n for n in world["npcs"] if n["id"] == marek["id"])
        for npc in guards:
            npc["location"] = city_id
            world["npcs"].append(npc)
        self.client = speech.ScriptedNpcSpeechClient(SPOKEN)
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        return world

    async def say(self, message, **body):
        response = await self.http.post(self.turn_url, json={
            "message": message, "action_id": str(uuid.uuid4()), **body})
        self.assertEqual(response.status_code, 200, response.text)
        self.body = response.json()
        return self.body["narration"]

    async def test_a_quoted_satici_to_the_cavus_is_no_shop_question(self):
        await self.start(guard("npc_g1", "Hadrik"))
        text = await self.say(
            "Nöbetçi çavuşa soruyorum: Satıcı, çizelgeden bir isim silindi dedi. Ne geldi başına?")
        self.assertNotIn("dükkân", text.casefold())
        self.assertGreaterEqual(self.client.chat_calls, 1)
        self.assertLessEqual(self.client.chat_calls, 2)

    async def test_a_role_word_vocative_reaches_the_role(self):
        await self.start(guard("npc_g1", "Hadrik"))
        text = await self.say("Çavuş, çizelgeyi neden bozdular?")
        self.assertNotIn("adıyla tanıdığın biri görünmüyor", text)
        self.assertNotEqual((self.body.get("action_result") or {}).get("status"), "invalid_target")
        self.assertIn(SPOKEN, text)

    async def test_two_present_roles_share_the_word(self):
        await self.start(guard("npc_g1", "Hadrik"), guard("npc_g2", "Bolen"))
        text = await self.say("Çavuş, çizelgeyi neden bozdular?")
        self.assertNotIn("adıyla tanıdığın biri görünmüyor", text)
        self.assertNotEqual((self.body.get("action_result") or {}).get("status"), "invalid_target")
        self.assertIn(SPOKEN, text)

    async def test_name_and_question_answers_the_question(self):
        await self.start()
        self.assertFalse(game._npc_speech_enabled())
        text = await self.say("Adım Borin. Pomşuna Karakolu'nda kimler var?",
                              interaction_mode="say", target_id=self.marek["id"])
        self.assertGreaterEqual(self.client.chat_calls, 1)
        self.assertLessEqual(self.client.chat_calls, 2)
        self.assertTrue(any(m.get("text") == "Benim adım Borin." for m in self.marek["memory"]), self.marek["memory"])
        for reply in local_dialogue.INTRODUCTION_REPLIES:
            self.assertNotIn(reply.format(name="Borin"), text)


class TheRestIsNotPrintedTwice(unittest.TestCase):
    def run_rest(self, first_action, first_text, rest_text):
        npc = {"id": "npc_g1", "name": "Hadrik", "location": "here"}
        session = game.GameSession(1)
        session.world_state.update(location="here", combat={"active": False})
        session._front_rest = "Satıcı var mı?"
        session._front_read = {"kind": "speak_to", "id": "npc_g1"}
        result = {"narration": first_text, "action_result": {"action": first_action, "status": "ok"}}
        said = {"narration": rest_text}
        with patch.object(game, "_session", return_value=session), \
                patch.object(game, "_conversation_npcs", return_value=[npc]), \
                patch.object(game, "_active_interlocutor", return_value=npc), \
                patch.object(game, "_dispatch_player_turn", return_value=said), \
                patch.object(game, "_is_stock", return_value=False), \
                patch.object(ollama_adapter, "model_calls_left", return_value=True):
            return game._the_rest_of_the_line(result, [], "a", "s", "here")

    def test_a_shop_answer_is_never_printed_twice(self):
        line = "Burada Demirci adlı dükkânlar var."
        out = self.run_rest("shop_inquiry", line, line)
        self.assertEqual(out["narration"].count(line), 1, out["narration"])

    def test_an_equal_rest_answer_is_not_appended(self):
        line = "Hadrik başını sallar."
        out = self.run_rest("dialogue_none", line, line)
        self.assertEqual(out["narration"].count(line), 1, out["narration"])

    def test_a_different_rest_answer_is_still_appended(self):
        out = self.run_rest("dialogue_none", "Birinci.", "İkinci.")
        self.assertEqual(out["narration"], "Birinci. İkinci.")


if __name__ == "__main__":
    unittest.main()
