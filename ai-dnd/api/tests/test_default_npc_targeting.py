"""Default-mode NPC targeting from the visible scene transcript."""

from __future__ import annotations

import json
import os
import unittest
import uuid
from unittest.mock import patch

import npc_statements
from api.tests import test_campaign_api
from api.tests.test_campaign_api import create_city_with_locked_tavern


class DescriptorTargetClient(test_campaign_api.FakeOllamaClient):
    def __init__(self, npc_id: str, visible_cue: str):
        self.npc_id = npc_id
        self.visible_cue = visible_cue
        self.prompts: list[str] = []

    def chat(self, *args, **kwargs):
        messages = kwargs.get("messages", [])
        prompt = next(
            item.get("content", "")
            for item in reversed(messages)
            if item.get("role") == "user"
        )
        self.prompts.append(prompt)
        target_schema = kwargs.get("format", {}).get("properties", {}).get("target", {})
        allowed = target_schema.get("properties", {}).get("npc_id", {}).get("enum", [])
        selected = self.npc_id if self.visible_cue in prompt and self.npc_id in allowed else ""
        quote = "arabaları kontrol eden kişiye" if selected else ""
        return {"message": {"content": json.dumps({
            "intent": "dialogue",
            "action": "dialogue",
            "target": {
                "type": "none",
                "reference": "",
                "npc_id": selected,
                "evidence_quote": quote,
            },
            "completion": "unclear",
            "confidence": 1.0,
        }, ensure_ascii=False)}}


class AttributedPlaceClient(test_campaign_api.FakeOllamaClient):
    def __init__(self, npc_id: str, narration: str):
        self.npc_id = npc_id
        self.narration = narration
        self.chat_calls = 0

    def chat(self, *args, **kwargs):
        self.chat_calls += 1
        messages = kwargs.get("messages", [])
        prompt = next(
            item.get("content", "")
            for item in reversed(messages)
            if item.get("role") == "user"
        )
        player_text = prompt.rsplit("Current player message: ", 1)[-1].splitlines()[0]
        return {"message": {"content": json.dumps({
            "intent": "dialogue",
            "action": "dialogue",
            "target": {"type": "none", "reference": ""},
            "completion": "unclear",
            "confidence": 1.0,
            "narration": self.narration,
            "world_updates": {},
            "lore_claims": [],
            "interaction": {
                "operation": "none",
                "quote": player_text,
                "conversation": {
                    "addressee_id": self.npc_id,
                    "subject_phrase": "yer",
                    "subject_role": "world_entity",
                    "meaning": "other",
                    "topic_relation": "new",
                    "candidate_evidence_ids": [],
                },
            },
        }, ensure_ascii=False)}}


class DefaultNpcTargetingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.enterContext(
            patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "0"})
        )

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def test_default_greeting_binds_visible_scene_description_to_one_npc(self):
        _, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        city_id = session.world_state["location"]
        guard = {
            "id": "npc_scene_guard",
            "name": "HiddenGuardName",
            "name_known_to_player": False,
            "role": "guard",
            "role_known_to_player": True,
            "appearance": "Aşınmış pazar üniforması giyiyor.",
            "location": city_id,
            "status": "active",
            "current_hp": 12,
            "combat_status": "active",
            "memory": [],
        }
        other = {
            **guard,
            "id": "npc_scene_civilian",
            "name": "HiddenCivilianName",
            "role": "resident",
            "appearance": "Yol kenarında bekliyor.",
        }
        session.world_state["npcs"].extend([guard, other])
        scene_line = (
            "Bir muhafız pazar girişinde arabaları sırayla kontrol eder."
        )
        session.messages.append({"role": "assistant", "content": scene_line})
        client = DescriptorTargetClient(
            guard["id"], "Bir muhafız pazar girişinde arabaları sırayla kontrol eder."
        )
        message = "Pazar girişinde arabaları kontrol eden kişiye selam veriyorum."
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            client,
            {"message": message, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(client.prompts)
        self.assertIn(scene_line, client.prompts[0])
        self.assertEqual(
            session.world_state.get("flags", {}).get("last_npc_id"),
            guard["id"],
            response.json(),
        )

    async def test_default_npc_place_statement_keeps_attribution_after_resume_and_respects_locked_target(self):
        city_id, session_id, session, turn_url, tavern_id, door = (
            await create_city_with_locked_tavern(self)
        )
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        npc = {
            "id": "npc_default_local",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {},
            "knowledge": [],
            "status": "active",
            "combat_status": "active",
            "current_hp": 12,
            "memory": [],
        }
        session.world_state["npcs"].append(npc)
        quote = f"{tavern_name} şehir merkezinde, uğrayabileceğin sakin bir yerdir."
        client = AttributedPlaceClient(npc["id"], quote)
        body = {
            "message": "Merhaba; bana şehirde gidilecek bir yer öner.",
            "interaction_mode": "do",
            "target_id": npc["id"],
            "action_id": str(uuid.uuid4()),
        }
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, body
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(client.chat_calls, 2)
        refs = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        place_ref = next(
            (ref for ref in refs if ref.get("name") == tavern_name), None
        )
        self.assertIsNotNone(
            place_ref, {"turn": response.json(), "refs": refs}
        )
        self.assertEqual(place_ref.get("said_by"), npc["id"])
        self.assertIn(quote, place_ref.get("quotes", []))

        campaign_id = self.manager.get(session_id).campaign_id
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        resumed_manager = test_campaign_api.SessionManager(campaign_store=self.store)
        resumed_app = test_campaign_api.create_app(
            session_manager=resumed_manager,
            ollama_adapter=test_campaign_api.AuthenticatedOllamaAdapter(client),
            authenticator=test_campaign_api.FixedAuthenticator(
                test_campaign_api.TEST_PLAYER
            ),
        )
        async with test_campaign_api.httpx.AsyncClient(
            transport=test_campaign_api.httpx.ASGITransport(app=resumed_app),
            base_url="http://test",
        ) as resumed_http:
            resumed = await resumed_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            resumed_session = resumed_manager.get(
                resumed.json()["session_id"]
            ).game_session
            resumed_ref = next(
                ref for ref in npc_statements.place_references(
                    resumed_session.world_state, settlement_id=city_id
                ) if ref.get("name") == tavern_name
            )
            self.assertEqual(resumed_ref.get("said_by"), npc["id"])
            travel = await resumed_http.post(
                f"/api/game/sessions/{resumed.json()['session_id']}/turn",
                json={
                    "message": f"Marek'in söylediği {tavern_name}'e gidiyorum.",
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )
            self.assertEqual(travel.status_code, 200, travel.text)
            self.assertEqual(travel.json()["turn_outcome"]["status"], "blocked")
            self.assertEqual(resumed_session.world_state["location"], city_id)
            self.assertTrue(next(
                item for item in resumed_session.world_state["doors"]
                if item.get("id") == door["id"]
            )["locked"])
            inspect = await resumed_http.post(
                f"/api/game/sessions/{resumed.json()['session_id']}/turn",
                json={
                    "message": "Kapıyı dikkatlice inceliyorum.",
                    "interaction_mode": "do",
                    "target_id": door["id"],
                    "action_id": str(uuid.uuid4()),
                },
            )
            self.assertEqual(inspect.status_code, 200, inspect.text)
            inspect_outcome = inspect.json()["turn_outcome"]
            self.assertEqual(
                inspect_outcome.get("action"), "grounded_action", inspect.json()
            )
            self.assertEqual(
                inspect_outcome.get("status"), "completed", inspect.json()
            )
            self.assertEqual(inspect_outcome.get("kind"), "door", inspect.json())
            self.assertTrue(next(
                item for item in resumed_session.world_state["doors"]
                if item.get("id") == door["id"]
            )["locked"])
            self.assertLessEqual(client.chat_calls, 3)
