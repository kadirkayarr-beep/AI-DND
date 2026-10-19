"""Isolated HTTP acceptance for naturally introduced local NPCs."""

from __future__ import annotations

import json
import copy
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

import httpx

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

from api.auth import FixedAuthenticator
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.main import create_app


class LocalPersonModel:
    def __init__(self):
        self.force_proposal = True

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        properties = kwargs.get("format", {}).get("properties", {})
        schema = kwargs.get("format", {})
        npc_ids = schema.get("properties", {}).get("target", {}).get(
            "properties", {}
        ).get("npc_id", {}).get("enum", [])
        npc_id = next((item for item in npc_ids if item), None)
        if "narration" in properties:
            packet = {
                "intent": "dialogue",
                "action": "dialogue",
                "target": {
                    "type": "npc",
                    "reference": "kıyı balıkçısı",
                    "npc_id": npc_id,
                    "evidence_quote": "Yosun lekeli pelerinli balıkçıya",
                },
                "completion": "unclear",
                "confidence": 1.0,
                "narration": "Balıkçı selamını sıcak bir baş hareketiyle karşılıyor.",
                "interaction": {
                    "operation": "none",
                    "quote": "Yosun lekeli pelerinli balıkçıya selam veriyorum.",
                    "conversation": None,
                },
            }
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        if npc_id is not None and not self.force_proposal:
            return {"message": {"content": json.dumps({
                "intent": "dialogue",
                "action": "dialogue",
                "target": {
                    "type": "npc",
                    "reference": "kıyı balıkçısı",
                    "npc_id": npc_id,
                    "evidence_quote": "Yosun lekeli pelerinli balıkçıya",
                },
                "completion": "unclear",
                "confidence": 1.0,
            }, ensure_ascii=False)}}
        if "local_person_proposal" not in properties:
            raise AssertionError("Unexpected model phase in local-person test.")
        return {
            "message": {
                "content": json.dumps({
                    "intent": "dialogue",
                    "action": "dialogue",
                    "target": {"type": "none", "reference": ""},
                    "completion": "unclear",
                    "confidence": 1.0,
                    "local_person_proposal": {
                        "name": "Neris",
                        "role": "kıyı balıkçısı",
                        "appearance": "Yosun lekeli pelerinli, gümüş sakallı biri",
                        "reason": "Liman söylentilerini biliyor olabilir.",
                    },
                }, ensure_ascii=False),
            }
        }


class LocalPersonPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        store = CampaignStore(
            Path(self.tempdir.name) / "campaigns.sqlite3",
            bound_principal=TEST_PLAYER,
        )
        self.manager = SessionManager(campaign_store=store)
        self.model = LocalPersonModel()
        adapter = AuthenticatedOllamaAdapter(self.model)
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://isolated-test",
        )

    async def _create_campaign(self):
        response = await self.http.post(
            "/api/game/campaigns",
            json={"campaign_start": {
                "setting_id": "forgotten_realms",
                "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                "region_id": "fr:region:the_north",
                "starting_location_id": "fr:city:neverwinter",
            }},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def asyncTearDown(self):
        await self.http.aclose()
        self.tempdir.cleanup()

    async def test_new_local_person_becomes_campaign_content_through_http(self):
        campaign = await self._create_campaign()
        turn = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json={
                "message": "Liman söylentileri için sahilde bir balıkçıyla konuşmak istiyorum.",
                "interaction_mode": "say",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(turn.status_code, 200, turn.text)

        session = self.manager.get(campaign["session_id"]).game_session
        accepted = [
            npc for npc in session.world_state["npcs"]
            if npc.get("role") == "kıyı balıkçısı"
            and npc.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        ]
        self.assertEqual(
            len(accepted),
            1,
            "a scene-consistent local person suggestion must become campaign content",
        )
        self.assertEqual(accepted[0]["name"], "Neris")
        self.assertEqual(accepted[0]["knowledge"], [])
        self.assertEqual(accepted[0]["backstory"], "")
        first_npc_id = accepted[0]["id"]

        replay = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json={
                "message": "Liman söylentileri için sahilde bir balıkçıyla konuşmak istiyorum.",
                "interaction_mode": "say",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(
            [
                npc for npc in session.world_state["npcs"]
                if npc.get("origin_request_key")
            ][0]["id"],
            first_npc_id,
        )
        self.assertEqual(len(accepted), 1)

        saved = await self.http.post(
            f"/api/game/campaigns/{campaign['campaign_id']}/save"
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        resumed = await self.http.post(
            f"/api/game/campaigns/{campaign['campaign_id']}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        resumed_session_id = resumed.json()["session_id"]
        resumed_session = self.manager.get(resumed_session_id).game_session
        restored_npc = next(
            npc for npc in resumed_session.world_state["npcs"]
            if npc.get("id") == first_npc_id
        )
        self.assertEqual(restored_npc["origin_request_key"], accepted[0]["origin_request_key"])

        repeated_after_resume = await self.http.post(
            f"/api/game/sessions/{resumed_session_id}/turn",
            json={
                "message": "Liman söylentileri için sahilde bir balıkçıyla konuşmak istiyorum.",
                "interaction_mode": "say",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(repeated_after_resume.status_code, 200, repeated_after_resume.text)
        same_key_npcs = [
            npc for npc in resumed_session.world_state["npcs"]
            if npc.get("origin_request_key") == restored_npc["origin_request_key"]
        ]
        self.assertEqual(len(same_key_npcs), 1)
        self.assertEqual(same_key_npcs[0]["id"], first_npc_id)

        self.model.force_proposal = False
        conversation = await self.http.post(
            f"/api/game/sessions/{resumed_session_id}/turn",
            json={
                "message": "Yosun lekeli pelerinli balıkçıya selam veriyorum.",
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(conversation.status_code, 200, conversation.text)
        self.assertIn("selamını", conversation.json()["narration"])
        self.assertEqual(
            resumed_session.world_state["flags"].get("last_npc_id"), first_npc_id
        )

        second_campaign = await self._create_campaign()
        other_id = second_campaign["session_id"]
        other_session = self.manager.get(other_id).game_session
        self.assertNotIn(
            first_npc_id,
            [npc.get("id") for npc in other_session.world_state["npcs"]],
        )
        second_turn = await self.http.post(
            f"/api/game/sessions/{other_id}/turn",
            json={
                "message": "Liman söylentileri için sahilde bir balıkçıyla konuşmak istiyorum.",
                "interaction_mode": "say",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(second_turn.status_code, 200, second_turn.text)
        second_npc = next(
            npc for npc in other_session.world_state["npcs"]
            if npc.get("origin_request_key")
        )
        self.assertNotEqual(
            second_npc["origin_request_key"],
            restored_npc["origin_request_key"],
        )
        self.assertEqual(
            [npc["id"] for npc in resumed_session.world_state["npcs"] if npc.get("role") == "kıyı balıkçısı"],
            [first_npc_id],
        )

    async def test_past_promise_and_reward_claim_cannot_create_a_person_or_reward(self):
        campaign = await self._create_campaign()
        session = self.manager.get(campaign["session_id"]).game_session
        character_before = copy.deepcopy(session.character)
        events_before = copy.deepcopy(session.world_state.get("events", []))

        response = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json={
                "message": "Geçen sefer Neris bana 100 altın vereceğine söz verdi.",
                "interaction_mode": "say",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(session.character, character_before)
        self.assertEqual(session.world_state.get("events", []), events_before)
        self.assertFalse(any(
            npc.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
            for npc in session.world_state["npcs"]
        ))

    async def test_existing_canonical_name_with_different_role_blocks_proposal(self):
        campaign = await self._create_campaign()
        session = self.manager.get(campaign["session_id"]).game_session
        session.world_state["npcs"].append({
            "id": "npc_existing_neris",
            "name": "Neris",
            "role": "liman muhafızı",
            "location": session.world_state["location"],
            "reality_layer": "CANON",
            "knowledge": [],
            "backstory": "",
        })

        response = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json={
                "message": "Liman söylentileri için sahilde bir balıkçıyla konuşmak istiyorum.",
                "interaction_mode": "say",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        same_name = [
            npc for npc in session.world_state["npcs"]
            if npc.get("name") == "Neris"
        ]
        self.assertEqual(len(same_name), 1)
        self.assertEqual(same_name[0]["id"], "npc_existing_neris")
        self.assertEqual(same_name[0]["role"], "liman muhafızı")
