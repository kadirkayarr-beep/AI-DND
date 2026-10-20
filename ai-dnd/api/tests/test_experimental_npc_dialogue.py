"""Isolated, opt-in NPC speech experiment. Not production-readiness coverage."""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import game
import interaction_adventure
import local_dialogue
import npc_statements
from api.persistence.campaign_models import CampaignStorageError
from api.tests import test_campaign_api
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import create_city_with_locked_tavern


class ScriptedNpcSpeechClient:
    """Schema-compliant positive NPC speech client for the opt-in experiment."""

    def __init__(
        self,
        narration: str = "Dün sana on altın vadetmiştim.",
        *,
        operation: str = "none",
        conversation: dict | None = None,
    ):
        self.narration = narration
        self.operation = operation
        self.conversation = conversation
        self.chat_calls = 0
        self.schemas = []
        self.message_batches = []

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.chat_calls += 1
        schema = copy.deepcopy(kwargs.get("format", {}))
        messages = copy.deepcopy(kwargs.get("messages", []))
        self.schemas.append(schema)
        self.message_batches.append(messages)
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "intent" not in properties:
            return {
                "message": {
                    "content": json.dumps({
                        "narration": self.narration,
                        "world_updates": {},
                        "lore_claims": [],
                    }, ensure_ascii=False)
                }
            }
        prompt = next(
            item.get("content", "")
            for item in reversed(messages)
            if item.get("role") == "user"
        )
        quote = prompt.split("Current player message: ", 1)[-1].splitlines()[0]
        packet = {
            "intent": "dialogue",
            "action": "dialogue",
            "target": {"type": "none", "reference": ""},
            "completion": "unclear",
            "confidence": 1.0,
            "narration": self.narration,
            "world_updates": {},
            "lore_claims": [],
            "interaction": {"operation": self.operation, "quote": quote},
        }
        if self.conversation is not None:
            packet["interaction"]["conversation"] = copy.deepcopy(self.conversation)
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class MalformedNpcSpeechClient:
    """Intentionally non-compliant negative client for testing fallback paths."""

    def __init__(
        self,
        *,
        omit_narration: bool = False,
        empty_narration: bool = False,
        invalid_narration_type: bool = False,
        operation: str = "none",
        conversation: dict | None = None,
        raw_content: str | None = None,
    ):
        self.omit_narration = omit_narration
        self.empty_narration = empty_narration
        self.invalid_narration_type = invalid_narration_type
        self.operation = operation
        self.conversation = conversation
        self.raw_content = raw_content
        self.chat_calls = 0
        self.schemas = []
        self.message_batches = []

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.chat_calls += 1
        schema = copy.deepcopy(kwargs.get("format", {}))
        messages = copy.deepcopy(kwargs.get("messages", []))
        self.schemas.append(schema)
        self.message_batches.append(messages)
        if self.raw_content is not None:
            return {"message": {"content": self.raw_content}}

        prompt = next(
            item.get("content", "")
            for item in reversed(messages)
            if item.get("role") == "user"
        )
        quote = prompt.split("Current player message: ", 1)[-1].splitlines()[0]
        packet = {
            "intent": "dialogue",
            "action": "dialogue",
            "target": {"type": "none", "reference": ""},
            "completion": "unclear",
            "confidence": 1.0,
            "world_updates": {},
            "lore_claims": [],
            "interaction": {"operation": self.operation, "quote": quote},
        }
        if not self.omit_narration:
            if self.invalid_narration_type:
                packet["narration"] = 12345
            elif self.empty_narration:
                packet["narration"] = "   "
            else:
                packet["narration"] = "Fallback text."
        if self.conversation is not None:
            packet["interaction"]["conversation"] = copy.deepcopy(self.conversation)
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class ExperimentalNpcDialogueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def campaign_with_npc(self, *, experimental=True):
        city_id, session_id, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        npc = {
            "id": "npc_experimental_marek",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Arşivde kâtiplik yapıyorum.",
                "current_activity": "Eski kayıtları tasnif ediyorum.",
                "recent_activity": "Saklı bir mührü buldum.",
                "mood": "Saklı konuyu biliyorum.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": "Kayıp kayıtları bulmaya geldim.",
                "personal_detail": "PRIVATE_PROFILE_SECRET_71ef.",
                "immediate_goal": "On altın alacağım.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
            "memory": [
                {"speaker": "player", "text": "Dün arşivdeki kayıtları sordum."},
                {"speaker": "npc", "text": "PRIVATE_NPC_REPLY_SECRET_19ac."},
                {"speaker": "player", "text": "PRIVATE_PROFILE_SECRET_71ef."},
            ],
        }
        session.world_state.setdefault("npcs", []).append(npc)
        session.world_state["npcs"].append({
            "id": "npc_private_sera",
            "name": "Sera",
            "role": "guard",
            "location": city_id,
            "personal_profile": {"personal_detail": "OTHER_NPC_SECRET_251d"},
            "memory": [{"speaker": "npc", "text": "OTHER_NPC_MEMORY_SECRET_06ad"}],
            "status": "active",
        })
        interaction_state = interaction_adventure.get(session.world_state)
        interaction_state["perspectives"][npc["id"]] = [
            {
                "entry_id": "marek-rumor-1",
                "kind": "rumor",
                "text": "Eski arşivde gece ışık görülmüş.",
                "source_id": "rumor-source-1",
                "secret": False,
            },
            {
                "entry_id": "marek-secret-1",
                "kind": "lie",
                "text": "PRIVATE_PERSPECTIVE_SECRET_1a7b.",
                "source_id": "private-source-1",
                "secret": True,
            },
        ]
        interaction_state["perspectives"]["npc_private_sera"] = [{
            "entry_id": "sera-rumor-1",
            "kind": "rumor",
            "text": "OTHER_NPC_PERSPECTIVE_SECRET_7d21.",
            "source_id": "other-source-1",
            "secret": False,
        }]
        interaction_adventure.validate(
            interaction_state,
            {**session.world_state, interaction_adventure.KEY: interaction_state},
        )
        session.world_state[interaction_adventure.KEY] = interaction_state
        if experimental:
            session._experimental_npc_dialogue_enabled = True
        return city_id, session_id, session, turn_url, npc

    @staticmethod
    def sensitive_state(session):
        world = session.world_state
        return {
            "npcs": copy.deepcopy(world.get("npcs", [])),
            "interaction_adventure": interaction_adventure.get(world),
            "inventory": copy.deepcopy(world.get("inventory")),
            "items": copy.deepcopy(world.get("items")),
            "quests": copy.deepcopy(world.get("quests")),
            "gold": copy.deepcopy(world.get("gold")),
        }

    @staticmethod
    def request(npc, *, message="Selam, bugün nasılsın?", action_id=None, interaction_mode="say"):
        return {
            "message": message,
            "interaction_mode": interaction_mode,
            "target_id": npc["id"],
            "action_id": action_id or str(uuid.uuid4()),
        }

    async def test_opt_in_free_speech_is_attributed_noncanonical_and_replayable(self):
        _, session_id, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        client = ScriptedNpcSpeechClient()
        body = self.request(npc)
        record_calls = []
        with patch.object(
            game, "record_npc_interaction",
            side_effect=lambda *args, **kwargs: record_calls.append((args, kwargs)),
        ):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(record_calls, [])
        self.assertTrue(response.json()["narration"].startswith("Marek"))
        self.assertNotIn("Dün sana on altın vadetmiştim.", response.json()["narration"])
        self.assertEqual(self.sensitive_state(session), before)

        # Verify schema: narration is required, conversation is optional
        schema = client.schemas[0]
        self.assertIn("narration", schema.get("required", []))
        self.assertIn("narration", schema.get("properties", {}))
        interaction_schema = schema.get("properties", {}).get("interaction", {})
        self.assertNotIn("conversation", interaction_schema.get("required", []))

        continuity_entries = self.manager.get(
            session_id
        ).narrative_memory["npc_interactions"].get(npc["id"], [])
        self.assertTrue(all(item.get("source") == "player_utterance" for item in continuity_entries))
        self.assertTrue(all(
            "Dün sana on altın vadetmiştim." not in item.get("text", "")
            for item in continuity_entries
        ))

        prompt = next(
            item["content"]
            for item in reversed(client.message_batches[0])
            if item.get("role") == "user"
        )
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        context_text = prompt.split(marker, 1)[1]
        context, _ = json.JSONDecoder().raw_decode(context_text)
        self.assertEqual(context["npc_id"], npc["id"])
        self.assertEqual(len(context["shareable_profile_facts"]), 4)
        self.assertEqual(
            context["perspective"],
            [{
                "kind": "rumor",
                "text": "Eski arşivde gece ışık görülmüş.",
                "source_id": "rumor-source-1",
            }],
        )
        self.assertEqual(
            context["recent_player_utterances"],
            ["Dün arşivdeki kayıtları sordum."],
        )
        self.assertNotIn("actors", context)
        self.assertNotIn("commitments", context)
        for secret in (
            "PRIVATE_PROFILE_SECRET_71ef",
            "PRIVATE_NPC_REPLY_SECRET_19ac",
            "OTHER_NPC_SECRET_251d",
            "OTHER_NPC_MEMORY_SECRET_06ad",
            "PRIVATE_PERSPECTIVE_SECRET_1a7b",
            "OTHER_NPC_PERSPECTIVE_SECRET_7d21",
        ):
            self.assertNotIn(secret, prompt)

        # Zero additional model calls on replay
        calls_before_replay = client.chat_calls
        replay = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(client.chat_calls, calls_before_replay)

    async def test_opt_in_invalid_proposal_does_not_trigger_repair_or_mutation(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        # The lean speech schema has no conversation field; only a model that
        # ignores the schema can still send one. That defensive path is tested.
        client = MalformedNpcSpeechClient(conversation={
            "addressee_id": "npc_private_sera",
            "subject_phrase": "Marek",
            "subject_role": "addressee",
            "meaning": "personal_purpose",
            "topic_relation": "new",
            "candidate_evidence_ids": [
                f"npc-profile:{npc['id']}:v1:reason_for_being_here",
            ],
        })
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, self.request(npc)
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(self.sensitive_state(session), before)
        self.assertNotIn("on altın", response.json()["narration"].casefold())

    async def test_opt_in_model_operation_is_not_accepted(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        # Schema-ignoring model: the lean schema itself has no operation field.
        client = MalformedNpcSpeechClient(operation="promise")
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client,
            self.request(npc, message="Sana yardım edeceğim."),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(self.sensitive_state(session), before)

    async def test_opt_in_all_three_exit_paths_preserve_conversation_focus_and_objectives(self):
        """All 3 exit paths must preserve focus and must NOT advance talk objectives or commitments:
        1. Valid attributed speech (even with optional topic_change proposal)
        2. Unaccepted experimental action (operation != 'none')
        3. Missing, empty, or invalid narration fallback (via negative client)
        """
        exit_path_scenarios = [
            (
                "Exit Path 1: Valid attributed speech with optional topic_change",
                MalformedNpcSpeechClient(
                    conversation={
                        "addressee_id": "npc_experimental_marek",
                        "subject_phrase": "Marek",
                        "subject_role": "addressee",
                        "meaning": "other",
                        "topic_relation": "topic_change",
                        "candidate_evidence_ids": [],
                    },
                ),
            ),
            (
                "Exit Path 2: Unaccepted experimental action",
                MalformedNpcSpeechClient(operation="promise"),
            ),
            (
                "Exit Path 3a: Omitted narration fallback",
                MalformedNpcSpeechClient(omit_narration=True),
            ),
            (
                "Exit Path 3b: Empty whitespace narration fallback",
                MalformedNpcSpeechClient(empty_narration=True),
            ),
            (
                "Exit Path 3c: Invalid narration type fallback",
                MalformedNpcSpeechClient(invalid_narration_type=True),
            ),
        ]

        for label, client in exit_path_scenarios:
            with self.subTest(scenario=label):
                # Fresh isolated campaign per scenario
                city_id, _, session, turn_url, npc = await self.campaign_with_npc()

                # 1. Seed active conversation focus using canonical profile evidence
                turn_index = session.world_state.setdefault("flags", {}).get("turn_index", 0)
                session.world_state["flags"]["active_npc_id"] = npc["id"]
                session.world_state["flags"]["active_npc_until_turn"] = turn_index + 6
                interaction_adventure.remember_conversation_focus(
                    session.world_state,
                    speaker_id=npc["id"],
                    scene_id=city_id,
                    subject_id=f"npc-profile:{npc['id']}:reason_for_being_here",
                    predicate="reason_for_being_here",
                    value=npc["personal_profile"]["reason_for_being_here"],
                    turn=turn_index,
                    action_id=f"focus-action-{uuid.uuid4().hex[:6]}",
                    evidence_id=f"npc-profile:{npc['id']}:v1:reason_for_being_here",
                    epistemic="witnessed",
                )
                focus_before = copy.deepcopy(
                    interaction_adventure.current_conversation_focus(session.world_state)
                )
                self.assertIsNotNone(focus_before, f"Failed to seed focus for {label}")

                # 2. Seed active thread with talk objective targeting the NPC, and an open commitment
                adv_state = interaction_adventure.get(session.world_state)
                thread_id = f"thread-talk-{uuid.uuid4().hex[:6]}"
                obj_id = f"obj-talk-{uuid.uuid4().hex[:6]}"
                commit_id = f"commit-promise-{uuid.uuid4().hex[:6]}"

                seeded_thread = interaction_adventure.Thread(
                    thread_id=thread_id,
                    origin="player",
                    title="Marek ile konuş",
                    status="active",
                    location_id=city_id,
                    objectives=[interaction_adventure.Objective(
                        objective_id=obj_id,
                        description="Marek ile konuş",
                        optional=False,
                        status="active",
                        routes=[{"kind": "talk", "target": npc["id"]}],
                    )],
                    created_turn=1,
                    updated_turn=1,
                ).model_dump()

                seeded_commitment = interaction_adventure.Commitment(
                    commitment_id=commit_id,
                    npc_id=npc["id"],
                    quote="Marek ile konusacagim",
                    thread_id=thread_id,
                    kind="promise",
                    status="open",
                    created_turn=1,
                    updated_turn=1,
                ).model_dump()

                adv_state["threads"] = [seeded_thread]
                adv_state["commitments"] = [seeded_commitment]
                interaction_adventure.validate(
                    adv_state,
                    {**session.world_state, interaction_adventure.KEY: adv_state},
                )
                session.world_state[interaction_adventure.KEY] = adv_state

                # 3. Post scene turn
                body = self.request(npc, message="Marek ile konuşuyorum.")
                response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                    self, turn_url, client, body
                )
                self.assertEqual(response.status_code, 200, f"{label}: {response.text}")
                # Exactly 1 model intent call, zero extra fallback calls
                self.assertEqual(client.chat_calls, 1, f"{label}: extra model calls observed")

                # 4. Assert conversation focus is PRESERVED
                focus_after = interaction_adventure.current_conversation_focus(session.world_state)
                self.assertIsNotNone(focus_after, f"{label}: focus was cleared")
                self.assertEqual(focus_after, focus_before, f"{label}: full conversation focus altered")

                # 5. Assert talk objective is STILL ACTIVE (NOT completed)
                adv_state_after = session.world_state[interaction_adventure.KEY]
                matching_thread = next(
                    t for t in adv_state_after["threads"] if t["thread_id"] == thread_id
                )
                self.assertEqual(matching_thread["status"], "active", f"{label}: thread status changed")
                self.assertEqual(matching_thread["objectives"][0]["status"], "active", f"{label}: objective completed")

                # 6. Assert commitment is STILL OPEN (NOT fulfilled)
                matching_commit = next(
                    c for c in adv_state_after["commitments"] if c["commitment_id"] == commit_id
                )
                self.assertEqual(matching_commit["status"], "open", f"{label}: commitment fulfilled")

    async def test_default_say_path_still_requires_conversation_contract_and_non_say_preserves_behavior(self):
        # 1. Flag-off: say path with non-smalltalk query requires conversation in schema
        _, _, _, turn_url, npc = await self.campaign_with_npc(experimental=False)
        client = ScriptedNpcSpeechClient(narration="Kayıtlarda eski bilgiler var.")
        body = self.request(npc, message="Bana kütüphanedeki eski kayıtları anlat.")
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, body
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.chat_calls, 1)
        required = client.schemas[0]["properties"]["interaction"]["required"]
        self.assertIn("conversation", required)

        # 2. Flag-off: deterministic smalltalk answered immediately with 0 model calls
        client_smalltalk = ScriptedNpcSpeechClient()
        body_smalltalk = self.request(npc, message="Selam, bugün nasılsın?")
        response_st = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client_smalltalk, body_smalltalk
        )
        self.assertEqual(response_st.status_code, 200, response_st.text)
        self.assertEqual(client_smalltalk.chat_calls, 0)

        # 3. Experimental opt-in: non-say interaction preserves deterministic smalltalk with 0 model calls
        _, _, session_exp, turn_url_exp, npc_exp = await self.campaign_with_npc(experimental=True)
        client_act = ScriptedNpcSpeechClient()
        body_act = self.request(npc_exp, message="Selam, bugün nasılsın?", interaction_mode="do")
        response_act = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url_exp, client_act, body_act
        )
        self.assertEqual(response_act.status_code, 200, response_act.text)
        self.assertEqual(client_act.chat_calls, 0)

    async def test_api_npc_reply_records_unknown_place_and_survives_save_resume(self):
        city_id, session_id, session, turn_url, npc = await self.campaign_with_npc()
        spoken_place = "Mavi Fener Camhanesi"
        quote = f"{spoken_place} doğu kapısının yanında, şehirde bilinen bir yerdir."
        client = ScriptedNpcSpeechClient(narration=quote)
        action_id = str(uuid.uuid4())
        body = self.request(
            npc,
            message="Bana şehirde gidilecek başka bir yer öner.",
            action_id=action_id,
        )

        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, body
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(client.chat_calls, 1)
        refs = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        place_ref = next(
            (ref for ref in refs if ref.get("name") == spoken_place), None
        )
        self.assertIsNotNone(place_ref, refs)
        self.assertEqual(place_ref.get("said_by"), npc["id"])
        self.assertIn(quote, place_ref.get("quotes", []))
        self.assertFalse(any(
            location.get("name") == spoken_place
            for location in session.world_state.get("locations", {}).values()
        ))

        travel_body = {
            "message": f"Marek'in söylediği {spoken_place}'ne gidiyorum",
            "interaction_mode": "do",
            "action_id": str(uuid.uuid4()),
        }
        travel = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, travel_body
        )
        self.assertEqual(travel.status_code, 200, travel.text)
        travel_payload = travel.json()
        travel_result = travel_payload.get("turn_outcome", {})
        self.assertEqual(travel_result.get("status"), "completed", travel_payload)
        resolved_ref = next(
            ref for ref in npc_statements.place_references(
                session.world_state, settlement_id=city_id
            ) if ref.get("name") == spoken_place
        )
        visited = session.world_state["locations"].get(resolved_ref.get("location_id"))
        self.assertEqual(visited.get("name"), spoken_place, visited)
        self.assertEqual(visited.get("provenance", {}).get("said_by"), npc["id"])
        locations_after_visit = copy.deepcopy(session.world_state["locations"])

        travel_replay = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, travel_body
        )
        self.assertEqual(travel_replay.status_code, 200, travel_replay.text)
        self.assertEqual(travel_replay.json(), travel.json())
        self.assertEqual(session.world_state["locations"], locations_after_visit)
        self.assertEqual(client.chat_calls, 1)

        replay = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, body
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(client.chat_calls, 1)

        campaign_id = self.manager.get(session_id).campaign_id
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        resumed_manager = test_campaign_api.SessionManager(campaign_store=self.store)
        resumed_app = test_campaign_api.create_app(
            session_manager=resumed_manager,
            ollama_adapter=test_campaign_api.AuthenticatedOllamaAdapter(client),
            authenticator=test_campaign_api.FixedAuthenticator(TEST_PLAYER),
        )
        async with test_campaign_api.httpx.AsyncClient(
            transport=test_campaign_api.httpx.ASGITransport(app=resumed_app),
            base_url="http://test",
        ) as resumed_http:
            resumed = await resumed_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        resumed_session = resumed_manager.get(resumed.json()["session_id"]).game_session
        resumed_refs = npc_statements.place_references(
            resumed_session.world_state, settlement_id=city_id
        )
        resumed_place_ref = next((ref for ref in resumed_refs if
            ref.get("name") == spoken_place and ref.get("said_by") == npc["id"]
            and quote in ref.get("quotes", [])), None)
        self.assertIsNotNone(resumed_place_ref, resumed_refs)
        resumed_location_id = resumed_place_ref.get("location_id")
        self.assertEqual(
            resumed_session.world_state["locations"][resumed_location_id].get("name"),
            spoken_place,
        )
        resumed_session_id = resumed.json()["session_id"]
        async with test_campaign_api.httpx.AsyncClient(
            transport=test_campaign_api.httpx.ASGITransport(app=resumed_app),
            base_url="http://test",
        ) as resumed_turn_http:
            for _ in range(2):
                repeat_after_resume = await resumed_turn_http.post(
                    f"/api/game/sessions/{resumed_session_id}/turn",
                    json={
                        "message": f"Marek'in söylediği {spoken_place}'ne gidiyorum",
                        "interaction_mode": "do",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(
                    repeat_after_resume.status_code, 200, repeat_after_resume.text
                )
                current_refs = npc_statements.place_references(
                    resumed_session.world_state, settlement_id=city_id
                )
                current_ref = next(
                    ref for ref in current_refs if ref.get("name") == spoken_place
                )
                self.assertEqual(
                    current_ref.get("location_id"), resumed_location_id, current_refs
                )
                self.assertEqual(
                    sum(
                        location.get("name") == spoken_place
                        for location in resumed_session.world_state["locations"].values()
                    ),
                    1,
                    resumed_session.world_state["locations"],
                )

        second_city_id, _, second_session, _, _, _ = (
            await create_city_with_locked_tavern(self)
        )
        second_refs = npc_statements.place_references(
            second_session.world_state, settlement_id=second_city_id
        )
        self.assertFalse(any(
            ref.get("name") == spoken_place for ref in second_refs
        ), second_refs)

    async def test_default_player_path_does_not_claim_experimental_npc_place_speech(self):
        city_id, _, session, turn_url, npc = await self.campaign_with_npc(experimental=False)
        self.assertFalse(
            getattr(session, "_experimental_npc_dialogue_enabled", False)
        )
        quote = "Mavi Fener Camhanesi doğu kapısının yanındadır."
        client = ScriptedNpcSpeechClient(narration=quote)
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            client,
            self.request(
                npc,
                message="Bana şehirde başka bir yer öner.",
                action_id=str(uuid.uuid4()),
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        refs = npc_statements.place_references(
            session.world_state, settlement_id=city_id
        )
        ref = next(
            (
                item for item in refs
                if item.get("name") == "Mavi Fener Camhanesi"
                and item.get("said_by") == npc["id"]
            ),
            None,
        )
        self.assertIsNotNone(ref, refs)
        self.assertEqual(ref.get("status"), "rumor")
        self.assertIsNone(ref.get("location_id"))
        self.assertFalse(any(
            location.get("name") == "Mavi Fener Camhanesi"
            for location in session.world_state["locations"].values()
        ))

    async def test_opt_in_save_failure_rolls_back_and_retry_receipt_replays(self):
        _, session_id, session, turn_url, npc = await self.campaign_with_npc()
        record = self.manager.get(session_id)
        campaign_id = record.campaign_id
        before_state = copy.deepcopy(session.serialize_game_state())
        before_memory = copy.deepcopy(record.narrative_memory)
        action_id = str(uuid.uuid4())
        body = self.request(npc, action_id=action_id)
        client = ScriptedNpcSpeechClient()
        original_save = self.store.save_campaign
        save_calls = 0

        def fail_once(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                raise CampaignStorageError("synthetic save failure")
            return original_save(*args, **kwargs)

        with patch.object(self.store, "save_campaign", side_effect=fail_once):
            failed = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(failed.status_code, 503, failed.text)
        first_call_count = client.chat_calls
        self.assertEqual(first_call_count, 1)
        self.assertEqual(session.serialize_game_state(), before_state)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertIsNone(self.store.get_turn_action(campaign_id, action_id, principal=TEST_PLAYER))

        # Failed-save rollback replaces the in-memory session. Re-enable the
        # non-persisted test-only switch on that fresh session before retrying.
        self.manager.get(session_id).game_session._experimental_npc_dialogue_enabled = True
        retry = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(client.chat_calls, first_call_count * 2)

        # Replay makes EXACTLY zero additional model calls
        replay = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(client.chat_calls, first_call_count * 2)
        # Lean speech schema: narration only, no operation/conversation envelope.
        self.assertEqual(set(client.schemas[0]["properties"]), {"narration"})

    async def test_experimental_answer_field_success_path_isolates_objective_and_commitment(self):
        city_id, session_id, session, turn_url, npc = await self.campaign_with_npc(experimental=True)
        marek_id = npc["id"]
        purpose_evidence = f"npc-profile:{marek_id}:v1:reason_for_being_here"

        # 1. Seed active focus on reason_for_being_here
        turn_index = session.world_state.setdefault("flags", {}).get("turn_index", 0)
        session.world_state["flags"]["active_npc_id"] = npc["id"]
        session.world_state["flags"]["active_npc_until_turn"] = turn_index + 6
        interaction_adventure.remember_conversation_focus(
            session.world_state,
            speaker_id=npc["id"],
            scene_id=city_id,
            subject_id=f"npc-profile:{npc['id']}:reason_for_being_here",
            predicate="reason_for_being_here",
            value=npc["personal_profile"]["reason_for_being_here"],
            turn=turn_index,
            action_id=f"focus-action-{uuid.uuid4().hex[:6]}",
            evidence_id=purpose_evidence,
            epistemic="witnessed",
        )
        focus_before = copy.deepcopy(
            interaction_adventure.current_conversation_focus(session.world_state)
        )
        self.assertIsNotNone(focus_before, "Failed to seed focus")

        # 2. Seed active thread with talk objective targeting Marek, and an open commitment
        adv_state = interaction_adventure.get(session.world_state)
        thread_id = f"thread-talk-{uuid.uuid4().hex[:6]}"
        obj_id = f"obj-talk-{uuid.uuid4().hex[:6]}"
        commit_id = f"commit-promise-{uuid.uuid4().hex[:6]}"

        seeded_thread = interaction_adventure.Thread(
            thread_id=thread_id,
            origin="player",
            title="Marek ile konuş",
            status="active",
            location_id=city_id,
            objectives=[interaction_adventure.Objective(
                objective_id=obj_id,
                description="Marek ile konuş",
                optional=False,
                status="active",
                routes=[{"kind": "talk", "target": npc["id"]}],
            )],
            created_turn=1,
            updated_turn=1,
        ).model_dump()

        seeded_commitment = interaction_adventure.Commitment(
            commitment_id=commit_id,
            npc_id=npc["id"],
            quote="Marek ile konusacagim",
            thread_id=thread_id,
            kind="promise",
            status="open",
            created_turn=1,
            updated_turn=1,
        ).model_dump()

        adv_state["threads"] = [seeded_thread]
        adv_state["commitments"] = [seeded_commitment]
        interaction_adventure.validate(
            adv_state,
            {**session.world_state, interaction_adventure.KEY: adv_state},
        )
        session.world_state[interaction_adventure.KEY] = adv_state

        # 3. Model returns a valid conversation proposal that resolves to answer_field (reason_for_being_here)
        message = "Marek, neden buraya geldin?"
        proposal = {
            "addressee_id": marek_id,
            "subject_phrase": "Marek",
            "subject_role": "addressee",
            "meaning": "personal_purpose",
            "topic_relation": "new",
            "candidate_evidence_ids": [purpose_evidence],
        }
        # Schema-ignoring model that still classifies: the canonical answer
        # path must stay isolated from objectives and commitments.
        client = MalformedNpcSpeechClient(
            operation="none",
            conversation=proposal,
        )
        body = self.request(npc, message=message, interaction_mode="say")

        # 4. Execute turn
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, body
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(
            npc["personal_profile"]["reason_for_being_here"],
            response.json()["narration"],
        )

        # 5. Assert full conversation focus is completely preserved
        focus_after = interaction_adventure.current_conversation_focus(session.world_state)
        self.assertEqual(focus_after, focus_before, "Conversation focus was altered on experimental answer_field path")

        # 6. Assert active talk objective was NOT consumed/completed (MUST REMAIN ACTIVE)
        adv_state_after = session.world_state[interaction_adventure.KEY]
        matching_thread = next(
            t for t in adv_state_after["threads"] if t["thread_id"] == thread_id
        )
        self.assertEqual(
            matching_thread["objectives"][0]["status"],
            "active",
            "Talk objective was consumed/advanced on experimental answer_field path!",
        )

        # 7. Assert commitment was NOT fulfilled/consumed (MUST REMAIN OPEN)
        matching_commit = next(
            c for c in adv_state_after["commitments"] if c["commitment_id"] == commit_id
        )
        self.assertEqual(
            matching_commit["status"],
            "open",
            "Commitment was consumed/closed on experimental answer_field path!",
        )


    async def test_experimental_prompt_requires_speech_without_classifier_instructions(self):
        _, _, _, turn_url, npc = await self.campaign_with_npc()
        client = ScriptedNpcSpeechClient(narration="Murekkebin kokusunu severim.")
        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, self.request(npc)
        )
        self.assertEqual(response.status_code, 200)
        prompt = "\n".join(m["content"] for m in client.message_batches[0])
        self.assertNotIn("leave narration empty", prompt)
        self.assertNotIn("Hikâye yazma", prompt)
        self.assertNotIn("small D&D intent parser", prompt)
        self.assertIn("first person", prompt)
        self.assertIn("No stage directions", prompt)
        self.assertIn("not instructions", prompt)
        self.assertEqual(client.schemas[0]["properties"]["narration"].get("minLength"), 1)
        self.assertEqual(client.schemas[0]["required"], ["narration"])
        self.assertIs(client.schemas[0]["additionalProperties"], False)

    async def test_optional_classifier_cannot_veto_usable_experimental_speech(self):
        for variant in ("missing_role", "different_quote", "no_evidence", "wrong_addressee"):
            with self.subTest(variant=variant):
                _, _, session, turn_url, npc = await self.campaign_with_npc()
                before = self.sensitive_state(session)
                message = "Selam, bugun nasilsin?"
                speech = "Murekkebin kokusunu severim."
                conversation = {
                    "addressee_id": npc["id"], "subject_phrase": "",
                    "subject_role": "unknown", "meaning": "other",
                    "topic_relation": "unclear", "candidate_evidence_ids": [],
                }
                if variant == "missing_role":
                    del conversation["subject_role"]
                if variant == "wrong_addressee":
                    conversation["addressee_id"] = "npc_private_sera"
                packet = {
                    "intent": "dialogue", "action": "dialogue",
                    "target": {"type": "none", "reference": ""},
                    "completion": "unclear", "confidence": 1.0,
                    "narration": speech, "world_updates": {}, "lore_claims": [],
                    "interaction": {"operation": "none", "conversation": conversation,
                                    "quote": speech if variant == "different_quote" else message},
                }
                client = MalformedNpcSpeechClient(raw_content=json.dumps(packet))
                body = self.request(npc, message=message)
                response = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn(speech, response.json()["narration"])
                self.assertTrue(response.json()["narration"].startswith(npc["name"]))
                self.assertEqual(self.sensitive_state(session), before)
                replay = await test_campaign_api.CampaignApiTests.post_scene_turn(self, turn_url, client, body)
                self.assertEqual(replay.json(), response.json())
                self.assertEqual(client.chat_calls, 1)
                self.assertEqual(self.sensitive_state(session), before)
