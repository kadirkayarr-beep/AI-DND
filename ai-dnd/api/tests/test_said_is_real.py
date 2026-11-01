"""What the screen says happened happened: items, hand-overs, work and blows are Python's to commit.

Real app, real engine; only the Ollama client is scripted. Lines are typed the way the owner types them.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from api.tests import test_front_proposal as front_tests
from api.tests import test_thread_gate as gate_tests
from api.tests import test_experimental_npc_dialogue as speech


class Table(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = speech.ExperimentalNpcDialogueTests.asyncSetUp
    asyncTearDown = speech.ExperimentalNpcDialogueTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc
    open_job = gate_tests.ThreadTable.open_job
    line = gate_tests.ThreadTable.line
    status = gate_tests.ThreadTable.status
    offer = gate_tests.ThreadTable.offer
    begin = front_tests.FrontTable.begin
    routes = front_tests.FrontTable.routes


class ClassifiedClient(front_tests.FrontClient):
    """A classifier that heard something else than the line says, as a small model does."""

    intent = None
    narrator_extra = {}

    def chat(self, *args, **kwargs):
        properties = (kwargs.get("format") or {}).get("properties") or {}
        if "narration" in properties and "intent" not in properties:
            self.chat_calls += 1
            self.schemas.append(kwargs.get("format"))
            self.message_batches.append(kwargs.get("messages", []))
            packet = {"narration": self.narration, "world_updates": {}, "lore_claims": []}
            return {"message": {"content": json.dumps({**packet, **self.narrator_extra}, ensure_ascii=False)}}
        reply = super().chat(*args, **kwargs)
        if self.intent and "intent" in properties:
            packet = json.loads(reply["message"]["content"])
            packet.update(intent=self.intent, action=self.intent)
            reply = {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        return reply


class BlowsThatRan(Table):
    async def fight(self):
        await self.begin()
        self.client = ClassifiedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.npc.update(armor_class=8, max_hp=40, current_hp=40)
        self.session.character.update(max_hp=300, current_hp=300)
        await self.line("marek'in suratina vuruyorum")
        self.assertTrue(self.world["combat"]["active"])

    async def test_a_blow_with_a_do_not_kill_beside_it_is_still_a_blow(self):
        await self.fight()
        reply = await self.line("bir daha kabzayla vuruyorum, bayilt onu, oldurme")
        self.assertEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_blow_said_with_i_am_not_killing_him_is_still_a_blow(self):
        await self.fight()
        reply = await self.line("vuruyorum yine ama oldurmuyorum")
        self.assertEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_line_that_refuses_every_blow_stays_no_blow(self):
        await self.fight()
        reply = await self.line("vurmuyorum, saldirmiyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")

    async def test_a_fall_nothing_caused_leaves_the_line(self):
        await self.fight()
        self.client.intent = "attack"
        self.client.narration = ("Taş avluda rüzgâr esiyor. Marek geriye doğru sendeliyor, "
                                 "gözlerinde şaşkınlıkla yere yığılıyor.")
        reply = await self.line("kilici kaldirip tehditkar bir hamle yapiyorum")
        self.assertNotEqual(reply["turn_outcome"]["action"], "attack")
        self.assertNotIn("yığılıyor", reply["narration"])

    async def test_a_refused_blow_is_not_told_as_a_hit(self):
        await self.fight()
        self.client.intent = "attack"
        self.client.narration = "Marek bir darbe alır ve yere yığılıyor."
        reply = await self.line("onu oldurmuyorum")
        self.assertNotIn("darbe", reply["narration"])
        self.assertNotIn("yığılıyor", reply["narration"])
