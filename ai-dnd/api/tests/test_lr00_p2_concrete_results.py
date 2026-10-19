"""LR00-P2: a look or search is bound to its target and says what it found.

OH1-04: success/failure x found/not-found; the receipt (action_result) names
the target and the narration agrees with it. When the narration model fails
or is rejected, the fallback carries the same concrete finding instead of
"iz göremiyorsun" or "kontrol başarılı olur".
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
from api.tests.test_lr00_p1_intent import ProbeShapedClient

GENERIC = ("iz göremiyorsun", "kontrol başarılı", "kontrol başarısız",
           "küçük ayrıntıları seçmeni sağlıyor", "girişimin başarı")


class NarrationDownClient(ProbeShapedClient):
    """Intent answers like the live model; the narration call fails -> fallback."""

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format", {}) or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "intent" not in properties:
            raise RuntimeError("narration model unavailable in this test")
        return super().chat(*args, **kwargs)


class ConcreteResultTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.client = NarrationDownClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", self.client))
        self.receipts = []
        original = game._dispatch_player_turn

        def recording(*args, **kwargs):
            outcome = original(*args, **kwargs)
            self.receipts.append(outcome.get("action_result") if isinstance(outcome, dict) else None)
            return outcome

        self.enterContext(patch.object(game, "_dispatch_player_turn", recording))
        _, _, self.session, self.turn_url, _ = await (
            harness.ExperimentalNpcDialogueTests.campaign_with_npc(self)
        )

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    def force(self, roll):
        self.session.rng.randint = lambda _a, _b: roll

    async def look(self, message, intent, roll):
        self.force(roll)
        self.client.message = message
        self.client.intent = {"intent": intent, "action": intent,
                              "target": {"type": "none", "reference": ""}}
        self.client.operation = "none"
        self.receipts.clear()
        response = await self.http.post(
            self.turn_url, json={"message": message, "action_id": str(uuid.uuid4())}
        )
        self.assertEqual(response.status_code, 200, response.text)
        text = response.json()["narration"]
        for generic in GENERIC:
            self.assertNotIn(generic, text)
        return text, self.receipts[-1]

    def door(self):
        return copy.deepcopy(next(
            d for d in self.session.world_state["doors"] if d["id"].startswith("venue-door:")
        ))

    async def test_lock_inspection_success_and_failure_are_bound_to_the_door(self):
        before = self.door()
        text, receipt = await self.look(
            "kilide yakından bakıyorum, zorlanmış mı yeni mi takılmış", "investigation", 20)
        self.assertEqual(receipt["inspection"]["target_kind"], "door")
        self.assertTrue(receipt["inspection"]["found"])
        self.assertIn("kilitli", text)
        self.assertIn("zorlandığına dair bir iz görmüyorsun", text)
        text, receipt = await self.look(
            "Kilidi bir kez daha inceliyorum.", "investigation", 1)
        self.assertFalse(receipt["inspection"]["found"])
        self.assertIn("bu bakışla", text)
        self.assertEqual(self.door(), before)

    async def test_window_becomes_a_saved_detail_and_reports_a_limited_view(self):
        text, receipt = await self.look(
            "Hanın sokağa bakan penceresinden içeriyi görmeye çalışıyorum.", "perception", 20)
        self.assertEqual(receipt["inspection"]["target_kind"], "feature")
        self.assertIn("Kepenklerin aralığından", text)
        windows = [f for f in self.session.world_state.get("features", [])
                   if "penceresi" in str(f.get("name", ""))]
        self.assertEqual(len(windows), 1)
        await self.look("Pencerenin kepenklerini inceliyorum.", "investigation", 1)
        windows_again = [f for f in self.session.world_state.get("features", [])
                         if "penceresi" in str(f.get("name", ""))]
        self.assertEqual([w["id"] for w in windows_again], [w["id"] for w in windows])

    async def test_tracks_are_reported_as_a_limited_finding_not_a_wall(self):
        text, receipt = await self.look(
            "Yerdeki çamurlu ayak izlerini dikkatle inceliyorum.", "investigation", 20)
        self.assertEqual(receipt["inspection"]["target_kind"], "tracks")
        self.assertIn("izini ayırmak", text)

    async def test_narrator_cannot_contradict_a_finding(self):
        """Live: the narrator put a figure behind closed shutters. The finding wins."""
        inventive = ProbeShapedClient()
        inventive.narration = "Kepenklerin arasında bir figür beliriyor; karanlıkta hareketsiz duruyor."
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", inventive))
        self.client = inventive
        text, receipt = await self.look(
            "Hanın sokağa bakan penceresinden içeriyi görmeye çalışıyorum.", "perception", 20)
        self.assertNotIn("figür", text)
        self.assertEqual(text, receipt["inspection"]["text"])

    def test_quoted_and_hidden_details_are_not_the_target(self):
        world = self.session.world_state
        here = world["location"]
        world.setdefault("features", []).extend([
            {"id": "f-secret", "location": here, "name": "Gizli işaret", "aliases": ["işaret"],
             "description": "PRIVATE_MARK", "kind": "detail", "hidden": True},
        ])
        self.assertIsNone(game._inspection_findings(
            'Duvara bakıyorum; "işaret" sadece bir kelime.', "success", session=self.session))
        self.assertIsNone(game._inspection_findings("İşarete bakıyorum.", "success", session=self.session))

    async def test_untargeted_look_describes_the_scene_on_success(self):
        text, receipt = await self.look("Etrafa dikkatlice bakıyorum.", "perception", 20)
        self.assertNotIn("inspection", receipt or {})
        self.assertTrue(text.strip())


if __name__ == "__main__":
    unittest.main()
