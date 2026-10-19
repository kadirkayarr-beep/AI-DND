"""Regression cases taken from the 18 Oct final live probe (live-lr00-probe-final*).

Each case is a sentence the real model run got wrong after the first round of
fixes. Once used here they are regression phrases, no longer unseen.
"""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import game
import interaction_adventure
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness
from api.tests.test_lr00_p1_intent import ProbeShapedClient


class LiveRegressionUnitTests(unittest.TestCase):
    def test_accepting_an_unmade_promise_is_not_a_refusal(self):
        for accepting in (
            "Hayır, unutmadım.",
            "Kılıç mı? Ama ben unutmadım.",
            "Üzgünüm, seninle söz verdiklerim var, ama bu kitapla ilgili bir şey hatırlamıyorum.",
        ):
            with self.subTest(text=accepting):
                self.assertFalse(game._npc_speech_rejects_claim(accepting))
        for refusing in (
            "Hayır, öyle bir sözüm yok. Kimden duyduysan iyi düşün, yanılıyorsun.",
            "Kılıç mı? Ne demek istediğini anlamadım. Bu konuda hiçbir şey söylemedim.",
        ):
            with self.subTest(text=refusing):
                self.assertTrue(game._npc_speech_rejects_claim(refusing))

    def test_negation_plus_sadece_is_one_act_not_a_plan(self):
        self.assertIsNone(interaction_adventure.compound_plan(
            "Kapıyı açmaya kalkmıyorum; sadece kilidin nasıl bir şey olduğuna bakıyorum."
        ))


class LiveRegressionHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.client = ProbeShapedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        _, _, self.session, self.turn_url, self.marek = await (
            harness.ExperimentalNpcDialogueTests.campaign_with_npc(self)
        )
        self.sera = next(n for n in self.session.world_state["npcs"] if n["id"] == "npc_private_sera")
        self.sera["name_known_to_player"] = True
        self.marek["name_known_to_player"] = True

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    def door(self):
        return copy.deepcopy(next(
            d for d in self.session.world_state["doors"] if d["id"].startswith("venue-door:")
        ))

    async def turn(self, message, *, mode=None, target=None):
        self.client.message = message
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
        if target:
            body["target_id"] = target
        response = await self.http.post(self.turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["narration"]

    async def test_conditional_entry_through_a_locked_door_waits(self):
        before, location = self.door(), self.session.world_state["location"]
        text = await self.turn("Eğer kapı açıksa içeri süzülürüm, değilse beklerim.")
        self.assertIn("bekliyorsun", text)
        self.assertEqual(self.door(), before)
        self.assertEqual(self.session.world_state["location"], location)

    async def test_false_promise_in_default_mode_is_refused_even_if_the_model_agrees(self):
        agreeing = harness.ScriptedNpcSpeechClient(narration="Hayır, unutmadım.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", agreeing))
        text = await self.turn("Marek, dün bana arşivin anahtarını vereceğine söz vermiştin unuttun mu")
        self.assertNotIn("unutmadım", text)
        self.assertTrue(game._npc_speech_is_claim_refusal(text, self.marek, session=self.session), text)

    def test_mid_sentence_vocative_names_the_addressee(self):
        resolution = game.resolve_npc_reference(
            "Kesinlikle kavga istemiyorum Sera, sadece içerdekini merak ediyorum",
            session=self.session,
        )
        self.assertEqual(resolution.get("status"), "found", resolution)
        self.assertEqual(resolution["npc"]["id"], "npc_private_sera")


if __name__ == "__main__":
    unittest.main()
