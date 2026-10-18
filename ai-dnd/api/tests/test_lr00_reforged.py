"""LR00 Reforged acceptance tests (deterministic layer), written red-first.

Sources: two real play sessions (35 + 19 turns), the speech-debug trail and the
One Handoff acceptance candidates OH1-01 (intent/target), OH1-04 (concrete result),
OH1-05/09/10 (creation, persistence, single effect), OH1-08 (narration vs receipt).
Scripted fake client only: no real model call is made. The wording of an assertion
is behavior ("the world answers specifically", "nothing is invented"), never the
exact sentence.
"""

from __future__ import annotations

import json
import os
import unittest
import uuid
from unittest.mock import patch

import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness

ScriptedNpcSpeechClient = harness.ScriptedNpcSpeechClient

GENERIC_REFUSALS = (
    "destekleyen bir iz göremiyorsun",
    "Bunu gerçekten bilmiyorum; ağzıma gelen",
    "Sahnedeki hareketlilik",
    "Kiminle konuşmak istiyorsun",
    "Hamle seni bekliyor",
)


class Lr00Base(unittest.IsolatedAsyncioTestCase):
    """Borrows the experimental harness helpers without re-running its tests."""

    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    campaign_with_npc = harness.ExperimentalNpcDialogueTests.campaign_with_npc
    sensitive_state = staticmethod(harness.ExperimentalNpcDialogueTests.sensitive_state)
    request = staticmethod(harness.ExperimentalNpcDialogueTests.request)

    async def turn(self, turn_url, client, body):
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, body
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def say(self, turn_url, client, npc, message):
        return await self.turn(turn_url, client, self.request(npc, message=message))

    async def do(self, turn_url, client, message, target_id=None):
        body = {
            "message": message,
            "interaction_mode": "do",
            "action_id": str(uuid.uuid4()),
        }
        if target_id is not None:
            body["target_id"] = target_id
        return await self.turn(turn_url, client, body)

    def assert_specific(self, text):
        for phrase in GENERIC_REFUSALS:
            self.assertNotIn(phrase.casefold(), text.casefold(), text)


class P1MentionIsNotAddressTests(Lr00Base):
    async def test_possessive_name_in_an_action_is_not_an_address(self):
        """Report 1, turn 21: "Samira'nın gösterdiği yönde ... bir yer arıyorum" reopened
        a finished conversation with Samira and she answered "bilmiyorum"."""
        _, _, session, _, npc = await self.campaign_with_npc()
        npc["name"] = "Samira"
        npc["role"] = "Muhafız"
        npc["name_known_to_player"] = True
        npc["role_known_to_player"] = True
        for other in list(session.world_state.get("npcs", [])):
            if other.get("id") != npc["id"]:
                session.world_state["npcs"].remove(other)
        session.world_state.setdefault("flags", {})["active_npc_until_turn"] = -1
        for text in (
            "Samira'nın gösterdiği yönde yürüyorum.",
            "Samiranın gösterdiği sokağa gidiyorum.",
            "Muhafızın yanına gidiyorum.",
            "Muhafızın baktığı yere bakıyorum.",
        ):
            with self.subTest(text=text):
                found = game.resolve_npc_reference(text, session=session)
                self.assertNotEqual(found.get("status"), "found", (text, found))
        for text in (
            "Samira'ya selam veriyorum.",
            "Samira, yardım eder misin?",
            "Muhafıza yaklaşıp selam veriyorum.",
            "Samira ile konuşuyorum.",
        ):
            with self.subTest(text=text):
                found = game.resolve_npc_reference(text, session=session)
                self.assertEqual(found.get("status"), "found", (text, found))


class DoClient(ScriptedNpcSpeechClient):
    """Intent calls get a scripted classification; narration calls get `narration`."""

    packet = {
        "intent": "unknown", "action": "unknown",
        "target": {"type": "none", "reference": ""},
        "completion": "unclear", "confidence": 0.9,
    }
    interaction = {"operation": "none"}

    def chat(self, *args, **kwargs):
        import copy

        schema = copy.deepcopy(kwargs.get("format", {}))
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        self.chat_calls += 1
        self.schemas.append(schema)
        messages = copy.deepcopy(kwargs.get("messages", []))
        self.message_batches.append(messages)
        prompt = next(m.get("content", "") for m in reversed(messages) if m.get("role") == "user")
        quote = prompt.split("Current player message: ", 1)[-1].splitlines()[0]
        if "intent" in props:
            packet = dict(self.packet)
            if "interaction" in props:
                packet["interaction"] = {"operation": "none", "quote": quote}
                if self.interaction.get("operation") != "none":
                    packet["interaction"] = dict(self.interaction, quote=quote)
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return {"message": {"content": json.dumps(
            {"narration": self.narration, "world_updates": {}, "lore_claims": []},
            ensure_ascii=False,
        )}}


def explore_client(narration="Çamurda ejderha izleri görüyorsun.", **fields):
    client = DoClient(narration=narration)
    client.packet = {**DoClient.packet, **fields}
    return client


class P2ConcreteResultTests(Lr00Base):
    """OH1-04: an inspection result is tied to the target and usable; absence is
    claimed with measure; a rejected narration never repeats the dice."""

    async def inspect(self, force_roll):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        client = explore_client(
            intent="explore", action="inspect", explore_type="inspect",
            target={"type": "none", "reference": ""},
        )
        # The model narration claims an unregistered finding: Python rejects it.
        body = {
            "message": "Yerdeki izlere dikkatle bakıyorum.",
            "interaction_mode": "do", "action_id": str(uuid.uuid4()),
        }
        with patch.object(session.rng, "randint", return_value=force_roll):
            reply = await self.turn(turn_url, client, body)
        return session, npc, client, reply

    async def test_success_names_what_is_actually_there_and_claims_absence_with_measure(self):
        session, npc, client, reply = await self.inspect(force_roll=19)
        text = reply["narration"]
        self.assertNotRegex(text, r"^İnceleme girişimin başarılı olur\.?$")
        self.assertNotIn("ejderha", text.casefold(), "an invented finding reached the player")
        self.assertIn("Marek", text, "the registered person nearby should be part of the result")
        self.assertRegex(text.casefold(), r"belirgin|kayda değer|seçemiyorsun|çıkmıyor")
        self.assert_specific(text)
        self.assertLessEqual(client.chat_calls, 2)

    async def test_failure_is_a_failure_but_still_shows_what_is_in_plain_sight(self):
        session, npc, client, reply = await self.inspect(force_roll=1)
        text = reply["narration"]
        self.assertNotRegex(text, r"^İnceleme girişimin başarısız olur\.?$")
        self.assertNotIn("ejderha", text.casefold())
        self.assertIn("Marek", text)
        self.assertRegex(text.casefold(), r"gözden kaçır|yeterince|aceleyle|bu kez")
        self.assert_specific(text)

    async def test_a_rejected_narration_does_not_roll_again(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        rolls = []
        original = session.rng.randint

        def counting(*args, **kwargs):
            value = original(*args, **kwargs)
            rolls.append(value)
            return value

        client = explore_client(
            intent="explore", action="inspect", explore_type="inspect",
        )
        body = {
            "message": "Duvardaki çatlaklara bakıyorum.",
            "interaction_mode": "do", "action_id": str(uuid.uuid4()),
        }
        with patch.object(session.rng, "randint", side_effect=counting):
            await self.turn(turn_url, client, body)
        d20_rolls = [value for value in rolls if 1 <= value <= 20]
        self.assertLessEqual(len(d20_rolls), 1, rolls)


if __name__ == "__main__":
    unittest.main()
