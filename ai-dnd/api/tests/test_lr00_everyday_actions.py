"""LR00 step 7: ordinary harmless actions get a concrete in-character result.

Phrases come from the 18 Oct live probe (live-lr00-probe-*). Before this fix
they produced HTTP 400 (knock) or the generic "iz göremiyorsun" wall.
"""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import everyday_actions
import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness

WALLS = ("iz göremiyorsun", "Sahnedeki hareketlilik", "desteklenmiyor", "yapamazsın")


class NoModelClient(test_campaign_api.FakeOllamaClient):
    """Everyday actions are resolved by Python; any model call fails the test."""


class EverydayActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", NoModelClient()))
        _, _, self.session, self.turn_url, self.marek = await (
            harness.ExperimentalNpcDialogueTests.campaign_with_npc(self)
        )
        self.marek["name_known_to_player"] = True

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def turn(self, message):
        response = await self.http.post(
            self.turn_url, json={"message": message, "action_id": str(uuid.uuid4())}
        )
        self.assertEqual(response.status_code, 200, response.text)
        text = response.json()["narration"]
        for wall in WALLS:
            self.assertNotIn(wall, text)
        return text

    def door(self):
        return copy.deepcopy(next(
            d for d in self.session.world_state["doors"] if d["id"].startswith("venue-door:")
        ))

    async def test_knocking_on_the_locked_inn_door_gets_no_answer_and_changes_nothing(self):
        before = self.door()
        location = self.session.world_state["location"]
        for message in (
            "kapıyı birkaç kez hafifçe vuruyorum, içerde biri var mı diye",
            "Yumruğumun yan tarafıyla kapıya üç kere tıklatıp bekliyorum",
        ):
            with self.subTest(message=message):
                text = await self.turn(message)
                self.assertIn("kilitli", text)
                self.assertEqual(self.door(), before)
                self.assertEqual(self.session.world_state["location"], location)

    async def test_ringing_the_bell_over_the_door_is_a_bell_not_a_knock(self):
        text = await self.turn("kapının üstündeki küçük çanı çekiştirip çalıyorum")
        self.assertIn("Çanı çalıyorsun", text)

    async def test_reading_a_book_depends_on_actually_carrying_one(self):
        text = await self.turn("Çantamdaki eski kitabı açıp birkaç sayfa okuyorum.")
        self.assertIn("kitap yok", text)
        self.session.world_state.setdefault("inventory", []).append("Yıpranmış kitap")
        text = await self.turn("Çantamdaki kitabı çıkarıp ilk sayfayı yüksek sesle okuyorum")
        self.assertIn("Yıpranmış kitap", text)

    async def test_following_a_visible_person_or_losing_an_unknown_one(self):
        location = self.session.world_state["location"]
        text = await self.turn("Marek'in peşinden gidiyorum ama fark ettirmeden, biraz arkadan")
        self.assertIn("Marek", text)
        self.assertEqual(self.session.world_state["location"], location)
        text = await self.turn("Az önce gördüğüm adamın peşine takılıyorum.")
        self.assertIn("izini kaybediyorsun", text)

    async def test_whistling_and_dancing_get_a_small_reaction(self):
        text = await self.turn("sıkıldım, ıslık çala çala sokakta biraz dans ediyorum")
        self.assertIn("ıslık", text)

    def test_negated_conditional_question_and_trying_forms_are_not_claimed(self):
        for message in (
            "Kapıyı çalmıyorum, sadece bekliyorum.",
            "Eğer kimse yoksa çanı çalarım.",
            "Çanı çalsam ne olur?",
            "Kapıyı açmaya çalışıyorum.",
        ):
            with self.subTest(message=message):
                self.assertIsNone(everyday_actions.classify(message))


if __name__ == "__main__":
    unittest.main()
