"""LR00-P1: intent, addressee and target rules over the real HTTP turn path.

Model packets below copy the shape qwen3:8b actually produced in the 18 Oct
live probe (live-lr00-probe-*): a sensible top-level intent plus an optional,
often unresolvable `interaction.conversation` block. The phrases come from the
unseen-phrase probe; once used here they are regression cases, not unseen.
"""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness

ROBOTIC_WALL = "bu düşünceyi destekleyen bir iz göremiyorsun"


class ProbeShapedClient:
    """Answers intent calls like the live model did; narration calls get a neutral line."""

    def __init__(self):
        self.message = ""
        self.intent = {"intent": "narrative", "action": "narrative",
                       "target": {"type": "none", "reference": ""}}
        self.operation = "none"
        self.narration = "Bir an durup çevrene kulak veriyorsun."
        self.calls = 0

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls += 1
        schema = kwargs.get("format", {}) or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "intent" not in properties:
            return {"message": {"content": json.dumps({
                "narration": self.narration, "world_updates": {}, "lore_claims": [],
            }, ensure_ascii=False)}}
        packet = {
            **copy.deepcopy(self.intent),
            "completion": "intended",
            "confidence": 1.0,
            "interaction": {
                "operation": self.operation,
                "quote": self.message,
                "thread_id": None, "evidence_id": None, "requested_item": None,
                "steps": [], "candidates": [],
                # The live model fills this even with nobody addressed.
                "conversation": {
                    "addressee_id": "npc_unknown", "subject_phrase": "",
                    "subject_role": "unknown", "meaning": "other",
                    "topic_relation": "new", "candidate_evidence_ids": [],
                },
            },
        }
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class Lr00P1IntentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.client = ProbeShapedClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.receipts = []
        original = game._dispatch_player_turn

        def recording(*args, **kwargs):
            outcome = original(*args, **kwargs)
            self.receipts.append(outcome.get("action_result") if isinstance(outcome, dict) else None)
            return outcome

        self.enterContext(patch.object(game, "_dispatch_player_turn", recording))
        _, _, self.session, self.turn_url, self.marek = await (
            harness.ExperimentalNpcDialogueTests.campaign_with_npc(self)
        )
        self.sera = next(n for n in self.session.world_state["npcs"] if n["id"] == "npc_private_sera")
        self.sera["name_known_to_player"] = True
        self.marek["name_known_to_player"] = True

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def turn(self, message, *, mode=None, target=None):
        self.client.message = message
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
        if target:
            body["target_id"] = target
        self.receipts.clear()
        response = await self.http.post(self.turn_url, json=body)
        return response, (self.receipts[-1] if self.receipts else None)

    def door(self):
        return copy.deepcopy(next(
            d for d in self.session.world_state["doors"] if d["id"].startswith("venue-door:")
        ))

    async def test_knock_and_attack_lookalike_words_are_not_attacks(self):
        for message in (
            "kapıyı birkaç kez hafifçe vuruyorum, içerde biri var mı diye",
            "Hanın kapısına iki kez hafifçe vurup içeriden ses gelip gelmediğini dinliyorum.",
            "bu sokağı biraz keşfetmek istiyorum, acelem yok",
            "Kesinlikle kavga istemiyorum Sera, sadece içerdekini merak ediyorum",
            "halatın yıpranmış ucunu bıçakla kesip düzeltiyorum",
            "Marek'e kitapta vurguladığı satırı soruyorum",
        ):
            with self.subTest(message=message):
                self.assertFalse(self.session._has_explicit_attack_verb(message))
                response, _ = await self.turn(message)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(self.session.world_state.get("combat", {}).get("active"))

    def test_real_attacks_still_count(self):
        for message in (
            "Marek'e yumrukla vuruyorum",
            "Sera'ya kılıcımla saldırıyorum",
            "muhafızı bıçaklıyorum",
            "ona vuruyorum",
            "kapının önündeki adama vuruyorum",
        ):
            with self.subTest(message=message):
                self.assertTrue(self.session._has_explicit_attack_verb(message))

    async def test_explicit_vocative_or_dative_question_picks_the_addressee(self):
        for message, expected in (
            ("Sera, Marek'in dediğine sen de inanıyor musun?", "npc_private_sera"),
            ("marek sen sus biraz, sera'ya soruyorum: han neden kapalı", "npc_private_sera"),
            ("Marek'e dönüp Sera'nın az önce söylediğini tekrarlamasını istiyorum", "npc_experimental_marek"),
        ):
            with self.subTest(message=message):
                resolution = game.resolve_npc_reference(message, session=self.session)
                self.assertEqual(resolution.get("status"), "found", resolution)
                self.assertEqual(resolution["npc"]["id"], expected)

    async def test_object_inspection_question_does_not_ask_which_person(self):
        response, receipt = await self.turn(
            "duvarda kapının hemen yanındaki o çiziklere bakıyorum, ne bunlar?"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("birden fazla kişi", response.json()["narration"])

    async def test_short_followup_stays_with_the_active_speaker(self):
        await self.turn("Merhaba Marek, biraz konuşabilir miyiz?", mode="say", target=self.marek["id"])
        for message in ("e sonra", "ne zamandan beri"):
            with self.subTest(message=message):
                resolution = game.resolve_npc_reference(message, session=self.session)
                self.assertEqual(resolution.get("status"), "found", resolution)
                self.assertEqual(resolution["npc"]["id"], self.marek["id"])

    async def test_unaddressed_physical_action_is_not_vetoed_by_optional_conversation(self):
        cases = (
            ("Pencerenin sürgüsünü parmaklarımla yokluyorum.", "perception", "none"),
            ("Biraz şehrin sokaklarında amaçsızca dolaşıyorum.", "explore", "none"),
            ("Çantamdaki eski kitabı açıp birkaç sayfa okuyorum.", "interact", "information"),
            ("Az önce gördüğüm adamın peşine takılıyorum.", "investigation", "promise"),
        )
        for message, intent, operation in cases:
            with self.subTest(message=message):
                self.client.intent = {"intent": intent, "action": intent,
                                      "target": {"type": "none", "reference": ""}}
                self.client.operation = operation
                response, receipt = await self.turn(message)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn(ROBOTIC_WALL, response.json()["narration"])
                self.assertNotEqual((receipt or {}).get("status"), "proposal_rejected", receipt)

    async def test_named_topic_change_in_default_mode_reaches_npc_speech(self):
        """The UI default mode is 'do'; naming the NPC must not hit a stricter path."""
        speech = harness.ScriptedNpcSpeechClient(
            narration="Kâtiplik yapıyorum; eski kayıtları ayıklıyorum.",
            # Live shape: plausible but unverifiable classifier guess.
            conversation={
                "addressee_id": "npc_experimental_marek", "subject_phrase": "arşiv",
                "subject_role": "addressee", "meaning": "occupation",
                "topic_relation": "topic_change", "candidate_evidence_ids": [],
            },
        )
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", speech))
        response, receipt = await self.turn(
            "neyse bunu boşver marek, sen arşivde ne iş yapıyosun tam olarak"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((receipt or {}).get("npc_id"), self.marek["id"], receipt)
        self.assertIn("Kâtiplik yapıyorum", response.json()["narration"])

    def test_object_verb_with_a_person_named_later_is_not_an_attack(self):
        self.assertFalse(self.session._has_explicit_attack_verb(
            "halatın yıpranmış ucunu bıçakla kesip düzeltiyorum, sonra Marek'e "
            "kitapta vurguladığı satırı sorucam"
        ))

    def test_greeting_plus_question_is_not_answered_with_a_bare_hello(self):
        npc = {"id": "npc_x", "name": "Melis"}
        self.assertIsNone(game._direct_npc_smalltalk_response(
            "Arşivciye selam verip burada bir sorun olup olmadığını soruyorum.", npc,
            session=self.session,
        ))
        self.assertIsNone(game._direct_npc_smalltalk_response(
            "Merhaba Melis, bu sabah kimse uğradı mı?", npc, session=self.session,
        ))
        self.assertEqual(
            game._direct_npc_smalltalk_response("Merhaba Melis!", npc, session=self.session),
            "Melis, “Merhaba,” diye karşılık verir.",
        )

    def test_colloquial_future_in_past_promise_is_a_historical_claim(self):
        for message in (
            "Hani geçen sefer bu kitabı getirirsem 50 altın vericektin marek? işte getirdim",
            "dün bana arşivin anahtarını verecektin, ne oldu?",
        ):
            with self.subTest(message=message):
                self.assertTrue(game.is_npc_historical_claim(message, session=self.session))

    async def test_reassurance_to_a_named_npc_is_not_a_negotiation(self):
        self.client.intent = {"intent": "dialogue", "action": "dialogue",
                              "target": {"type": "none", "reference": ""}}
        for message, operation in (
            ("Kapıyı kırmayacağım, merak etme Sera. sadece kilide bakıcam", "conditional"),
            ("Kesinlikle kavga istemiyorum Sera, sadece içerdekini merak ediyorum", "promise"),
        ):
            with self.subTest(message=message):
                self.client.operation = operation
                before = self.door()
                response, receipt = await self.turn(message)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotEqual((receipt or {}).get("status"), "pending", receipt)
                self.assertNotIn("Önce ne istediğimizi", response.json()["narration"])
                self.assertEqual(self.door(), before)

    async def test_short_followup_in_default_mode_gets_npc_speech(self):
        speech = harness.ScriptedNpcSpeechClient(narration="Sonra kayıtların yarısı kayboldu.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", speech))
        speech.narration = "Arşivde gece yarısına kadar çalıştım."
        await self.turn("Merhaba Marek, biraz konuşabilir miyiz?", mode="say", target=self.marek["id"])
        speech.narration = "Sonra kayıtların yarısı kayboldu."
        response, receipt = await self.turn("e sonra")
        self.assertEqual((receipt or {}).get("npc_id"), self.marek["id"], receipt)
        self.assertIn("kayıtların yarısı", response.json()["narration"])

    async def test_walking_up_to_a_named_npc_is_an_approach_not_a_question(self):
        response, receipt = await self.turn("Marek'in yanına yürüyorum.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((receipt or {}).get("action"), "approach", receipt)
        self.assertEqual(receipt.get("target_id"), self.marek["id"])

    async def test_approach_plus_question_keeps_the_question(self):
        speech = harness.ScriptedNpcSpeechClient(narration="Arşiv, meydanın arkasındaki taş binada.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", speech))
        response, receipt = await self.turn("Marek'e yaklaşıp arşivi soruyorum.")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((receipt or {}).get("npc_id"), self.marek["id"], receipt)
        self.assertIn("taş binada", response.json()["narration"])

    async def test_compound_knock_does_the_first_step_and_keeps_the_rest(self):
        # Contract changed by the owner on 18 Oct 2026 (after the P6 rejection):
        # compound actions run in order in the same turn instead of waiting as a
        # plan. What this test protects is unchanged: no step is silently dropped
        # (OH1-03). Every step is reported, in order, with what really happened.
        response, receipt = await self.turn(
            "kapıyı çalıyorum, cevap gelmezse pencereden içeri bakıyorum sonra marek'e dönüp soruyorum"
        )
        self.assertEqual(response.status_code, 200, response.text)
        text = response.json()["narration"]
        self.assertIn("kilitli", text)
        steps = (receipt or {}).get("steps") or []
        self.assertGreaterEqual(len(steps), 3, receipt)
        self.assertEqual(steps[0].get("verb"), "knock", steps)
        self.assertEqual(steps[0].get("status"), "completed", steps)
        self.assertTrue(all(step.get("status") for step in steps), steps)
        # The question to Marek is not narrated as asked in this turn.
        self.assertNotEqual(steps[-1].get("status"), "completed", steps)

    async def test_a_statement_said_to_a_named_npc_gets_their_own_answer(self):
        speech = harness.ScriptedNpcSpeechClient(narration="Duydum ama sorun yok, sesin pek yüksek değildi.")
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", speech))
        response, receipt = await self.turn("marek'e bağırmadım ki ben, yüksek sesle düşündüm sadece")
        self.assertEqual((receipt or {}).get("npc_id"), self.marek["id"], receipt)
        self.assertIn("sesin pek yüksek", response.json()["narration"])

    async def test_reassurance_plus_lock_look_is_a_look_not_an_npc_wall(self):
        before = self.door()
        self.client.intent = {"intent": "investigation", "action": "investigation",
                              "target": {"type": "none", "reference": ""}}
        response, receipt = await self.turn("Kapıyı kırmayacağım, merak etme Sera. sadece kilide bakıcam")
        text = response.json()["narration"]
        self.assertNotIn("Emin değilim", text)
        self.assertNotIn("bir şey bilmiyorum", text)
        self.assertEqual((receipt or {}).get("inspection", {}).get("target_kind"), "door", receipt)
        self.assertEqual(self.door(), before)

    async def test_a_successful_look_never_opens_or_breaks_the_door(self):
        """Found by the 18 Oct full run: any successful check whose text merely
        contained "kapıyı aç"/"kapıyı kır" opened or broke the door."""
        self.session.rng.randint = lambda _a, _b: 20
        before = self.door()
        self.client.intent = {"intent": "investigation", "action": "investigation",
                              "target": {"type": "none", "reference": ""}}
        for message in (
            "Kapıyı açmaya kalkmıyorum; sadece kilidin nasıl bir şey olduğuna bakıyorum.",
            "Kapıyı kırmayacağım, merak etme Sera. sadece kilide bakıcam",
            "Kapıyı zorlamıyorum, kilit zorlanmış mı diye inceliyorum.",
        ):
            with self.subTest(message=message):
                response, _ = await self.turn(message)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(self.door(), before)

    def test_affirmative_door_verbs_are_still_attempts(self):
        for text, expected in (
            ("kapiyi kiriyorum", True), ("kapiyi kirmaya calisiyorum", True),
            ("kapiyi kirmayacagim", False), ("kapiyi zorlamiyorum", False),
            ("kilit zorlanmis mi", False), ("kapiyi zorla aciyorum", True),
        ):
            with self.subTest(text=text):
                found = (game._affirmative_door_verb(text, r"kapiyi\s+", ("kir",))
                         or game._affirmative_door_verb(text, "", ("zorla",)))
                self.assertEqual(found, expected)

    async def test_walk_up_and_greet_is_a_greeting(self):
        response, receipt = await self.turn("Marek'in yanına gidip başımla selam veriyorum.")
        text = response.json()["narration"]
        self.assertNotIn("bir şey bilmiyorum", text)
        self.assertEqual((receipt or {}).get("npc_id"), self.marek["id"], receipt)

    async def test_negated_and_conditional_entry_never_moves_through_a_locked_door(self):
        location = self.session.world_state["location"]
        before = self.door()
        for message in (
            "Kapıyı açmaya kalkmıyorum; sadece kilidin nasıl bir şey olduğuna bakıyorum.",
            "Eğer kapı açıksa içeri süzülürüm, değilse beklerim.",
            "Kapıyı kırmayacağım, merak etme Sera. sadece kilide bakıcam",
        ):
            with self.subTest(message=message):
                response, _ = await self.turn(message)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(self.session.world_state["location"], location)
                self.assertEqual(self.door(), before)


if __name__ == "__main__":
    unittest.main()
