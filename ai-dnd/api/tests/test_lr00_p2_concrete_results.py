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

import httpx

import game
from api.tests import test_campaign_api
from api.tests import test_experimental_npc_dialogue as harness
from api.tests.test_lr00_p1_intent import ProbeShapedClient

GENERIC = ("iz göremiyorsun", "kontrol başarılı", "kontrol başarısız",
           "küçük ayrıntıları seçmeni sağlıyor", "girişimin başarı")


class NarrationDownClient(ProbeShapedClient):
    """Intent works; narration fails, so only engine-owned fallbacks can complete."""

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
        _, self.session_id, self.session, self.turn_url, _ = await (
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
        self.assertEqual(receipt["inspection"]["target_id"], before["id"])
        self.assertTrue(receipt["inspection"]["found"])
        self.assertIn("kilitli", text)
        self.assertIn("zorlandığına dair bir iz görmüyorsun", text)
        text, receipt = await self.look(
            "Kilidi bir kez daha inceliyorum.", "investigation", 1)
        self.assertFalse(receipt["inspection"]["found"])
        self.assertIn("bu bakışla", text)
        self.assertEqual(self.door(), before)

    async def test_missing_door_inspection_is_honest_without_blocking_other_investigation(self):
        library = await self.http.post(
            self.turn_url,
            json={
                "message": "Kütüphaneye gidiyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(library.status_code, 200, library.text)
        location_id = self.session.world_state["location"]
        self.assertEqual(
            self.session.world_state["locations"][location_id].get("place_kind"),
            "library",
        )
        self.assertIsNone(game._current_door())

        before = copy.deepcopy(self.session.world_state)
        rng_before = self.session.rng.getstate()
        client = ProbeShapedClient()
        client.intent = {
            "intent": "investigation",
            "action": "investigate",
            "target": {"type": "none", "reference": ""},
        }
        client.narration = (
            "DOOR_HALLUCINATION: Kapının üzerindeki leylak desenleri ve kilit deliği belirgin."
        )
        self.receipts.clear()
        request = {
            "message": "Kapıyı inceliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        with (
            patch.object(self.app.state.ollama_adapter, "_client", client),
            patch.object(
                game,
                "roll_d20",
                side_effect=AssertionError("Missing door must not roll Investigation."),
            ),
        ):
            response = await self.http.post(self.turn_url, json=request)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.calls, 1)  # Intent only; no ungrounded narration call.
        self.assertEqual(len(self.receipts), 1)
        receipt = self.receipts[0]
        self.assertEqual(receipt["action"], "inspect")
        self.assertEqual(receipt["status"], "unresolved")
        self.assertEqual(receipt["target_type"], "door")
        self.assertIsNone(receipt["target_id"])
        self.assertNotIn("dice", receipt)
        narration = response.json()["narration"]
        self.assertIn("belirgin bir kapı göremiyorsun", narration)
        self.assertNotIn("DOOR_HALLUCINATION", narration)
        self.assertNotIn("leylak", narration.casefold())
        self.assertEqual(self.session.world_state["location"], location_id)
        self.assertEqual(self.session.world_state["locations"], before["locations"])
        self.assertEqual(self.session.world_state["doors"], before["doors"])
        self.assertEqual(self.session.world_state["features"], before["features"])
        self.assertEqual(self.session.world_state["npcs"], before["npcs"])
        self.assertEqual(self.session.rng.getstate(), rng_before)

        # An unrelated investigation still uses the normal check/narration path.
        client.calls = 0
        client.narration = "Rafları inceliyorsun; bu bakışta belirgin bir iz seçilmiyor."
        self.receipts.clear()
        with (
            patch.object(self.app.state.ollama_adapter, "_client", client),
            patch.object(game, "roll_d20", return_value=12),
        ):
            other = await self.http.post(
                self.turn_url,
                json={
                    "message": "Rafları araştırıyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(other.status_code, 200, other.text)
        self.assertEqual(self.receipts[-1]["action"], "skill_check")
        self.assertEqual(client.calls, 2)
        self.assertIn("Rafları inceliyorsun", other.json()["narration"])

        campaign_id = self.manager.get(self.session_id).campaign_id
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        for key in ("location", "locations", "doors", "features", "npcs"):
            self.assertEqual(saved_world[key], self.session.world_state[key], key)
        self.assertEqual(committed.history[-2]["narration"], narration)
        self.assertEqual(committed.history[-1]["narration"], other.json()["narration"])

        reopened_store = test_campaign_api.CampaignStore(
            self.store.path, bound_principal=test_campaign_api.TEST_PLAYER
        )
        reopened_manager = test_campaign_api.SessionManager(campaign_store=reopened_store)
        reopened_app = test_campaign_api.create_app(
            session_manager=reopened_manager,
            ollama_adapter=test_campaign_api.AuthenticatedOllamaAdapter(
                test_campaign_api.FakeOllamaClient()
            ),
            authenticator=test_campaign_api.FixedAuthenticator(test_campaign_api.TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as resumed_http:
            resumed = await resumed_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        resumed_session = reopened_manager.get(resumed.json()["session_id"]).game_session
        self.assertEqual(resumed_session.serialize_game_state(), committed.payload["engine_save"])
        self.assertEqual(resumed.json()["history"], committed.history)
        self.assertEqual(resumed.json()["state"]["location"], location_id)

    async def test_canonical_door_inspection_stays_bound_after_save_resume(self):
        before = self.door()
        location_before = self.session.world_state["location"]
        text, receipt = await self.look(
            "kilide yakından bakıyorum, zorlanmış mı yeni mi takılmış",
            "investigation",
            20,
        )
        self.assertEqual(receipt["inspection"]["target_kind"], "door")
        self.assertEqual(receipt["inspection"]["target_id"], before["id"])
        self.assertEqual(receipt["inspection"]["target_name"], before["name"])
        self.assertEqual(text, receipt["inspection"]["text"])
        self.assertEqual(self.session.world_state["location"], location_before)
        self.assertEqual(self.door(), before)

        campaign_id = self.manager.get(self.session_id).campaign_id
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["location"], location_before)
        saved_door = next(item for item in saved_world["doors"] if item["id"] == before["id"])
        self.assertEqual(saved_door, before)
        self.assertEqual(committed.history[-1]["narration"], text)

        reopened_store = test_campaign_api.CampaignStore(
            self.store.path, bound_principal=test_campaign_api.TEST_PLAYER
        )
        reopened_manager = test_campaign_api.SessionManager(campaign_store=reopened_store)
        reopened_app = test_campaign_api.create_app(
            session_manager=reopened_manager,
            ollama_adapter=test_campaign_api.AuthenticatedOllamaAdapter(
                test_campaign_api.FakeOllamaClient()
            ),
            authenticator=test_campaign_api.FixedAuthenticator(test_campaign_api.TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as resumed_http:
            resumed = await resumed_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        resumed_session = reopened_manager.get(resumed.json()["session_id"]).game_session
        resumed_door = next(
            item for item in resumed_session.world_state["doors"]
            if item["id"] == before["id"]
        )
        self.assertEqual(resumed_door, before)
        self.assertEqual(resumed.json()["history"], committed.history)

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
        client = ProbeShapedClient()
        client.narration = (
            "Yakındaki yapılar ve sokaklar görüş alanında; belirgin bir ayrıntı "
            "öne çıkmıyor."
        )
        self.client = client
        self.enterContext(patch.object(self.app.state.ollama_adapter, "_client", client))
        door_guard = game._is_door_inspection_request
        with patch.object(game, "_is_door_inspection_request", wraps=door_guard) as guard_spy:
            text, receipt = await self.look(
                "Etrafa dikkatlice bakıyorum.", "perception", 20
            )
        guard_spy.assert_called_once_with("Etrafa dikkatlice bakıyorum.")
        self.assertFalse(door_guard("Etrafa dikkatlice bakıyorum."))
        self.assertNotIn("inspection", receipt or {})
        self.assertEqual(receipt["action"], "explore")
        self.assertEqual(text, client.narration, str(self.session.last_narration_safety))
        self.assertIn("yakındaki yapılar ve sokaklar", text.casefold())

        campaign_id = self.manager.get(self.session_id).campaign_id
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["location"], self.session.world_state["location"])
        self.assertEqual(committed.history[-1]["narration"], text)


if __name__ == "__main__":
    unittest.main()
