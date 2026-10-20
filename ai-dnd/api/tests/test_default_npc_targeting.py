"""Default-mode NPC targeting from the visible scene transcript."""

from __future__ import annotations

import json
import os
import unittest
import uuid
from unittest.mock import patch

import npc_statements
import local_dialogue
from api.tests import test_campaign_api
from api.tests.test_campaign_api import (
    create_city_with_locked_tavern,
    unlock_venue_door,
)


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
        self.prompts: list[str] = []

    def chat(self, *args, **kwargs):
        self.chat_calls += 1
        messages = kwargs.get("messages", [])
        prompt = next(
            item.get("content", "")
            for item in reversed(messages)
            if item.get("role") == "user"
        )
        self.prompts.append(prompt)
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

    async def test_local_place_recommendations_reach_focused_npc_without_weakening_claim_vetoes(self):
        city_id, _, session, turn_url, tavern_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        guard = {
            "id": "npc_recommendation_guard",
            "name": "Marek",
            "role": "guard",
            "role_known_to_player": True,
            "appearance": "Mavi pelerinli bir muhafız.",
            "location": city_id,
            "status": "active",
            "current_hp": 12,
            "combat_status": "active",
            "memory": [],
        }
        session.world_state["npcs"].append(guard)
        scene = "Pazar girişinde mavi pelerinli muhafız arabaları kontrol ediyor."
        session.messages.append({"role": "assistant", "content": scene})
        selected = DescriptorTargetClient(guard["id"], scene)
        greeting = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            selected,
            {
                "message": "Pazar girişindeki mavi pelerinli muhafıza selam veriyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(greeting.status_code, 200, greeting.text)
        self.assertEqual(
            session.world_state["flags"].get("last_npc_id"), guard["id"]
        )

        original_location_ids = set(session.world_state["locations"])
        quote = f"{tavern_name} şehir merkezinde, uğrayabileceğin sakin bir yerdir."
        recommendation_client = AttributedPlaceClient(guard["id"], quote)
        recommendation_phrasings = (
            "Şehirde gidebileceğim sakin bir yer önerir misin?",
            "Buralarda gezmeye değer bir yer tavsiye eder misin?",
            "Yakınlarda uğramamı önereceğin bir mekân var mı?",
        )
        for message in recommendation_phrasings:
            with self.subTest(message=message):
                self.assertTrue(
                    local_dialogue.is_local_place_recommendation_request(message)
                )
                if message == recommendation_phrasings[0]:
                    self.assertTrue(local_dialogue.is_world_subject_question(message))
                before_calls = recommendation_client.chat_calls
                with patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "1"}):
                    response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                        self,
                        turn_url,
                        recommendation_client,
                        {
                            "message": message,
                            "interaction_mode": "do",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertGreater(recommendation_client.chat_calls, before_calls)
                self.assertTrue(
                    any(
                        "LOCAL PLACE RECOMMENDATION" in prompt
                        and tavern_name in prompt
                        for prompt in recommendation_client.prompts
                    )
                )
                self.assertEqual(
                    session.world_state["flags"].get("last_npc_id"), guard["id"]
                )
                refs = npc_statements.place_references(
                    session.world_state, settlement_id=city_id
                )
                place_ref = next(
                    (ref for ref in refs if ref.get("name") == tavern_name), None
                )
                self.assertIsNotNone(place_ref)
                self.assertEqual(place_ref.get("said_by"), guard["id"])
                self.assertIn(quote, place_ref.get("quotes", []))
                self.assertEqual(
                    set(session.world_state["locations"]), original_location_ids
                )

        fallback_client = AttributedPlaceClient(
            guard["id"], "Bu konuda söyleyecek bir şey bilmiyorum."
        )
        refs_before_uncertain_reply = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        tavern_ref_before_uncertain_reply = next(
            ref for ref in refs_before_uncertain_reply
            if ref.get("name") == tavern_name
        )
        quotes_before_uncertain_reply = list(
            tavern_ref_before_uncertain_reply.get("quotes", [])
        )
        with patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "1"}):
            fallback_response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                fallback_client,
                {
                    "message": recommendation_phrasings[0],
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(fallback_response.status_code, 200, fallback_response.text)
        self.assertTrue(
            any(
                "LOCAL PLACE RECOMMENDATION" in prompt
                and tavern_name in prompt
                for prompt in fallback_client.prompts
            )
        )
        self.assertEqual(fallback_client.chat_calls, 2)
        self.assertIn(
            "Bu konuda söyleyecek bir şey bilmiyorum.",
            fallback_response.json()["narration"],
        )
        self.assertNotIn(tavern_name, fallback_response.json()["narration"])
        refs_after_uncertain_reply = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        tavern_ref_after_uncertain_reply = next(
            ref for ref in refs_after_uncertain_reply
            if ref.get("name") == tavern_name
        )
        self.assertEqual(
            tavern_ref_after_uncertain_reply.get("quotes"),
            quotes_before_uncertain_reply,
        )
        self.assertEqual(set(session.world_state["locations"]), original_location_ids)

        unlock_venue_door(session.world_state, tavern_id)
        travel = await self.http.post(
            turn_url,
            json={
                "message": f"Marek'in söylediği {tavern_name}'e gidiyorum.",
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(travel.status_code, 200, travel.text)
        if travel.json()["turn_outcome"]["status"] == "interrupted":
            travel = await self.http.post(
                turn_url,
                json={
                    "message": "Devam ediyorum.",
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )
            self.assertEqual(travel.status_code, 200, travel.text)
        self.assertEqual(
            session.world_state["location"],
            tavern_id,
            travel.json(),
        )

        hidden_question = "Neverwinter'daki gizli bir yerin adını biliyor musun?"
        history_claims = (
            "Daha önce bana Mavi Fener Camhanesi'ni bulacağına söz vermiştin.",
            "Daha önce bana Mavi Fener Camhanesi'ni önermediğini söylemiştin.",
        )
        before_veto_calls = recommendation_client.chat_calls
        for message in (hidden_question, *history_claims):
            with self.subTest(veto_message=message):
                response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                    self,
                    turn_url,
                    recommendation_client,
                    {
                        "message": message,
                        "interaction_mode": "do",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    response.json()["turn_outcome"]["status"], "unverified"
                )
                self.assertEqual(
                    recommendation_client.chat_calls, before_veto_calls
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
        scene_line = "Bir muhafız pazar girişinde arabaları sırayla kontrol eder."
        session.messages.append({"role": "assistant", "content": scene_line})
        selection = DescriptorTargetClient(npc["id"], scene_line)
        with patch.dict(os.environ):
            os.environ.pop("AI_DND_NPC_SPEECH", None)
            greeting = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                selection,
                {
                    "message": "Pazar girişinde arabaları kontrol eden kişiye selam veriyorum.",
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(greeting.status_code, 200, greeting.text)
        self.assertEqual(
            session.world_state["flags"].get("last_npc_id"), npc["id"]
        )
        self.assertFalse(
            getattr(session, "_experimental_npc_dialogue_enabled", False)
        )

        quote = f"{tavern_name} şehir merkezindedir; uğramaya değer."
        client = AttributedPlaceClient(npc["id"], quote)
        body = {
            "message": "Şehirde gidebileceğim sakin bir yer önerir misin?",
            "interaction_mode": "do",
            "action_id": str(uuid.uuid4()),
        }
        with patch.dict(os.environ):
            os.environ.pop("AI_DND_NPC_SPEECH", None)
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, turn_url, client, body
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.chat_calls, 2)
        self.assertIn(quote, response.json()["narration"])
        self.assertTrue(any(
            "LOCAL PLACE RECOMMENDATION" in prompt
            and tavern_name in prompt
            for prompt in client.prompts
        ))
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

        proposed_place = "Mavi Fener Camhanesi"
        proposed_quote = (
            f"{proposed_place} doğu kapısının yanında; bence uğramaya değer."
        )
        proposed_client = AttributedPlaceClient(npc["id"], proposed_quote)
        with patch.dict(os.environ):
            os.environ.pop("AI_DND_NPC_SPEECH", None)
            proposed = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                proposed_client,
                {
                    "message": "Yakınlarda başka bir yer önerir misin?",
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(proposed.status_code, 200, proposed.text)
        self.assertGreaterEqual(proposed_client.chat_calls, 1)
        self.assertLessEqual(proposed_client.chat_calls, 2)
        self.assertIn(proposed_quote, proposed.json()["narration"])
        proposed_ref = next(
            ref for ref in npc_statements.place_references(
                session.world_state, settlement_id=city_id
            ) if ref.get("name") == proposed_place
        )
        self.assertEqual(proposed_ref.get("said_by"), npc["id"])
        self.assertIsNone(proposed_ref.get("location_id"))
        self.assertFalse(any(
            location.get("name") == proposed_place
            for location in session.world_state["locations"].values()
        ))

        unsure_client = AttributedPlaceClient(
            npc["id"], "Bu konuda emin değilim."
        )
        refs_before_unsure = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        with patch.dict(os.environ):
            os.environ.pop("AI_DND_NPC_SPEECH", None)
            unsure = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                unsure_client,
                {
                    "message": "Bana bir yer tavsiye edebilir misin?",
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(unsure.status_code, 200, unsure.text)
        self.assertGreaterEqual(unsure_client.chat_calls, 1)
        self.assertLessEqual(unsure_client.chat_calls, 2)
        self.assertIn("Bu konuda emin değilim.", unsure.json()["narration"])
        refs_after_unsure = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        self.assertEqual(
            [ref.get("name") for ref in refs_after_unsure],
            [ref.get("name") for ref in refs_before_unsure],
        )

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
            self.assertIn(
                npc["id"],
                {item.get("id") for item in resumed_session.world_state["npcs"]},
            )
            resumed_ref = next(
                ref for ref in npc_statements.place_references(
                    resumed_session.world_state, settlement_id=city_id
                ) if ref.get("name") == tavern_name
            )
            self.assertEqual(resumed_ref.get("said_by"), npc["id"])
            resumed_proposal = next(
                ref for ref in npc_statements.place_references(
                    resumed_session.world_state, settlement_id=city_id
                ) if ref.get("name") == proposed_place
            )
            self.assertEqual(resumed_proposal.get("said_by"), npc["id"])
            self.assertIsNone(resumed_proposal.get("location_id"))
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

    async def test_default_new_place_is_campaign_scoped_replayable_and_cold_loadable(self):
        city_id, session_id, session, turn_url, _, _ = (
            await create_city_with_locked_tavern(self)
        )
        npc = {
            "id": "npc_default_new_place",
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

        other_creation = await test_campaign_api.CampaignApiTests.create_campaign(self)
        self.assertNotEqual(other_creation["session_id"], session_id)
        other_session = self.manager.get(
            other_creation["session_id"]
        ).game_session
        other_campaign_id = self.manager.get(
            other_creation["session_id"]
        ).campaign_id
        campaign_id = self.manager.get(session_id).campaign_id
        self.assertNotEqual(campaign_id, other_campaign_id)

        spoken_place = "Mavi Fener Camhanesi"
        quote = (
            f"{spoken_place} doğu kapısının yanında; bence uğramaya değer."
        )
        client = AttributedPlaceClient(npc["id"], quote)
        suggestion_action_id = str(uuid.uuid4())
        suggestion_body = {
            "message": "Yakınlarda başka bir yer önerir misin?",
            "interaction_mode": "do",
            "target_id": npc["id"],
            "action_id": suggestion_action_id,
        }
        with patch.dict(os.environ):
            os.environ.pop("AI_DND_NPC_SPEECH", None)
            suggestion = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, turn_url, client, suggestion_body
            )
        self.assertEqual(suggestion.status_code, 200, suggestion.text)
        suggestion_payload = suggestion.json()
        suggestion_outcome = suggestion_payload["turn_outcome"]
        self.assertEqual(suggestion_payload["action_id"], suggestion_action_id)
        self.assertEqual(suggestion_outcome.get("action"), "dialogue")
        self.assertEqual(suggestion_outcome.get("status"), "resolved")
        # Dialogue receipts intentionally omit target IDs and names; the
        # request target and the recorded said_by reference are authoritative.
        self.assertIsNone(suggestion_outcome.get("target_name"))
        self.assertEqual(suggestion_payload["state"]["location"], city_id)
        self.assertIn(quote, suggestion_payload["narration"])
        refs = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        rumor = next(
            ref for ref in refs if ref.get("name") == spoken_place
        )
        self.assertEqual(rumor.get("said_by"), npc["id"])
        self.assertIn(quote, rumor.get("quotes", []))
        self.assertIsNone(rumor.get("location_id"))
        self.assertFalse(any(
            item.get("name") == spoken_place
            for item in session.world_state["locations"].values()
        ))

        calls_after_suggestion = client.chat_calls
        suggestion_state = json.dumps(
            session.world_state, sort_keys=True, ensure_ascii=False
        )
        suggestion_replay = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, suggestion_body
        )
        self.assertEqual(suggestion_replay.status_code, 200, suggestion_replay.text)
        self.assertEqual(suggestion_replay.json(), suggestion_payload)
        self.assertEqual(client.chat_calls, calls_after_suggestion)
        self.assertEqual(
            json.dumps(session.world_state, sort_keys=True, ensure_ascii=False),
            suggestion_state,
        )

        self.assertFalse(any(
            npc_item.get("id") == npc["id"]
            for npc_item in other_session.world_state.get("npcs", [])
        ))
        self.assertFalse(any(
            location.get("name") == spoken_place
            for location in other_session.world_state.get("locations", {}).values()
        ))
        self.assertFalse(any(
            ref.get("name") == spoken_place
            for ref in npc_statements.place_references(
                other_session.world_state,
                settlement_id=other_session.world_state.get("location"),
            )
        ))

        self.assertEqual(
            (await self.http.post(
                f"/api/game/campaigns/{campaign_id}/save"
            )).status_code,
            200,
        )
        self.assertEqual(
            (await self.http.post(
                f"/api/game/campaigns/{other_campaign_id}/save"
            )).status_code,
            200,
        )
        cold_manager = test_campaign_api.SessionManager(campaign_store=self.store)
        cold_app = test_campaign_api.create_app(
            session_manager=cold_manager,
            ollama_adapter=test_campaign_api.AuthenticatedOllamaAdapter(client),
            authenticator=test_campaign_api.FixedAuthenticator(
                test_campaign_api.TEST_PLAYER
            ),
        )
        async with test_campaign_api.httpx.AsyncClient(
            transport=test_campaign_api.httpx.ASGITransport(app=cold_app),
            base_url="http://cold-load",
        ) as cold_http:
            resumed = await cold_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            resumed_session_id = resumed.json()["session_id"]
            self.assertNotEqual(resumed_session_id, session_id)
            resumed_session = cold_manager.get(
                resumed_session_id
            ).game_session
            self.assertEqual(resumed_session.world_state["location"], city_id)
            self.assertIn(
                npc["id"],
                {item.get("id") for item in resumed_session.world_state["npcs"]},
            )
            cold_ref = next(
                ref for ref in npc_statements.place_references(
                    resumed_session.world_state, settlement_id=city_id
                ) if ref.get("name") == spoken_place
            )
            self.assertEqual(cold_ref.get("said_by"), npc["id"])
            self.assertIn(quote, cold_ref.get("quotes", []))
            self.assertIsNone(cold_ref.get("location_id"))
            self.assertFalse(any(
                location.get("name") == spoken_place
                for location in resumed_session.world_state["locations"].values()
            ))

            resumed_turn_url = (
                f"/api/game/sessions/{resumed_session_id}/turn"
            )
            calls_before_cold_replays = client.chat_calls
            cold_state_before_replay = json.dumps(
                resumed_session.world_state,
                sort_keys=True,
                ensure_ascii=False,
            )
            cold_suggestion_replay = await cold_http.post(
                resumed_turn_url, json=suggestion_body
            )
            self.assertEqual(cold_suggestion_replay.status_code, 200)
            self.assertEqual(
                cold_suggestion_replay.json()["action_id"],
                suggestion_action_id,
            )
            self.assertEqual(
                cold_suggestion_replay.json()["turn_outcome"],
                suggestion_payload["turn_outcome"],
            )
            self.assertEqual(
                cold_suggestion_replay.json()["narration"],
                suggestion_payload["narration"],
            )
            self.assertEqual(client.chat_calls, calls_before_cold_replays)
            self.assertEqual(
                json.dumps(
                    resumed_session.world_state,
                    sort_keys=True,
                    ensure_ascii=False,
                ),
                cold_state_before_replay,
            )

            other_resumed = await cold_http.post(
                f"/api/game/campaigns/{other_campaign_id}/resume"
            )
            self.assertEqual(other_resumed.status_code, 200, other_resumed.text)
            other_loaded = cold_manager.get(
                other_resumed.json()["session_id"]
            ).game_session
            self.assertFalse(any(
                item.get("id") == npc["id"]
                for item in other_loaded.world_state.get("npcs", [])
            ))
            self.assertFalse(any(
                location.get("name") == spoken_place
                for location in other_loaded.world_state["locations"].values()
            ))
