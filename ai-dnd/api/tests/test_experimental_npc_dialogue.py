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
from api.persistence.campaign_models import CampaignStorageError
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import (
    CampaignApiTests,
    create_city_with_locked_tavern,
)


class ScriptedNpcSpeechClient:
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


class ExperimentalNpcDialogueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await CampaignApiTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await CampaignApiTests.asyncTearDown(self)

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
            "memory": [],
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
            # Test-only opt-in; no request field or persisted setting exposes this.
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
    def request(npc, *, message="Selam, bugün nasılsın?", action_id=None):
        return {
            "message": message,
            "interaction_mode": "say",
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
            response = await CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(client.chat_calls, 2)
        self.assertEqual(record_calls, [])
        self.assertTrue(response.json()["narration"].startswith("Marek"))
        self.assertNotIn("Dün sana on altın vadetmiştim.", response.json()["narration"])
        self.assertEqual(self.sensitive_state(session), before)
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
        self.assertNotIn("Dün sana on altın vadetmiştim.", response.json()["narration"])

        replay = await CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), response.json())
        self.assertLessEqual(client.chat_calls, 2)

    async def test_opt_in_invalid_proposal_does_not_trigger_repair_or_mutation(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        client = ScriptedNpcSpeechClient(conversation={
            "addressee_id": "npc_private_sera",
            "subject_phrase": "Marek",
            "subject_role": "addressee",
            "meaning": "personal_purpose",
            "topic_relation": "new",
            "candidate_evidence_ids": [
                f"npc-profile:{npc['id']}:v1:reason_for_being_here",
            ],
        })
        response = await CampaignApiTests.post_scene_turn(
            self, turn_url, client, self.request(npc)
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(client.chat_calls, 2)
        self.assertEqual(self.sensitive_state(session), before)
        self.assertNotIn("on altın", response.json()["narration"].casefold())

    async def test_opt_in_model_operation_is_not_accepted(self):
        _, _, session, turn_url, npc = await self.campaign_with_npc()
        before = self.sensitive_state(session)
        client = ScriptedNpcSpeechClient(operation="promise")
        response = await CampaignApiTests.post_scene_turn(
            self, turn_url, client,
            self.request(npc, message="Sana yardım edeceğim."),
        )
        self.assertEqual(response.status_code, 200, response.text)
        first_call_count = client.chat_calls
        self.assertLessEqual(first_call_count, 2)
        self.assertEqual(self.sensitive_state(session), before)

    async def test_default_say_path_still_requires_conversation_contract(self):
        _, _, _, turn_url, npc = await self.campaign_with_npc(experimental=False)
        client = ScriptedNpcSpeechClient(narration="Merhaba.")
        response = await CampaignApiTests.post_scene_turn(
            self, turn_url, client, self.request(npc)
        )
        self.assertEqual(response.status_code, 200, response.text)
        required = client.schemas[0]["properties"]["interaction"]["required"]
        self.assertIn("conversation", required)

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
            failed = await CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(failed.status_code, 503, failed.text)
        first_call_count = client.chat_calls
        self.assertLessEqual(first_call_count, 2)
        self.assertEqual(session.serialize_game_state(), before_state)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertIsNone(self.store.get_turn_action(campaign_id, action_id, principal=TEST_PLAYER))

        # Failed-save rollback replaces the in-memory session. Re-enable the
        # non-persisted test-only switch on that fresh session before retrying.
        self.manager.get(session_id).game_session._experimental_npc_dialogue_enabled = True
        retry = await CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(client.chat_calls, first_call_count * 2)
        replay = await CampaignApiTests.post_scene_turn(self, turn_url, client, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(client.chat_calls, first_call_count * 2)
        interaction_schema = client.schemas[0]["properties"]["interaction"]
        self.assertNotIn("conversation", interaction_schema.get("required", []))
