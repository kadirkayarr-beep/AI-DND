"""HTTP-level tests for persistent campaign lifecycle and autosave behavior."""

from __future__ import annotations

import asyncio
import copy
from contextlib import closing
from functools import wraps
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

import httpx

import adventure.templates as adventure_templates
import adventure.transitions as adventure_transitions

AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
import campaign_time
import living_world
import timed_gameplay
import local_dialogue
import quest_catalog
import api.main as main_module
from api.auth import FixedAuthenticator
from api.campaign_journal import create_initial_campaign_journal
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.dnd_2024_rules import SPECIES_DEFINITIONS
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignStaleError,
    CampaignStorageError,
)
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER


def unlock_venue_door(world_state, tavern_id):
    """Open a door this test already discovered. Not a player turn."""
    door_id = f"venue-door:{tavern_id}"
    matches = [
        door for door in world_state.get("doors", [])
        if isinstance(door, dict) and door.get("id") == door_id
    ]
    if len(matches) != 1:
        raise AssertionError(door_id)
    matches[0]["locked"] = False
    matches[0]["open"] = True


async def create_city_with_locked_tavern(test_case):
    city_id = "fr:city:neverwinter"
    created = await test_case.http.post(
        "/api/game/campaigns",
        json={"campaign_start": {
            "setting_id": "forgotten_realms",
            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
            "region_id": "fr:region:the_north",
            "starting_location_id": city_id,
        }},
    )
    test_case.assertEqual(created.status_code, 200, created.text)
    session_id = created.json()["session_id"]
    session = test_case.manager.get(session_id).game_session
    turn_url = f"/api/game/sessions/{session_id}/turn"
    discovered = await test_case.http.post(
        turn_url,
        json={"message": "Yakınlarda bir taverna arıyorum.", "action_id": str(uuid.uuid4())},
    )
    test_case.assertEqual(discovered.status_code, 200, discovered.text)
    taverns = [
        identity for identity, location in session.world_state["locations"].items()
        if isinstance(location, dict) and location.get("scene_kind") == "tavern"
        and location.get("parent_location_id") == city_id
    ]
    test_case.assertEqual(len(taverns), 1)
    tavern_id = taverns[0]
    door = next(
        item for item in session.world_state["doors"]
        if item.get("id") == f"venue-door:{tavern_id}"
    )
    test_case.assertTrue(door["locked"])
    test_case.assertFalse(door["open"])
    return city_id, session_id, session, turn_url, tavern_id, door


class FakeOllamaClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("Campaign API tests must not call a real model.")


class ControlledVenueOllamaClient(FakeOllamaClient):
    """Synthetic intent and narration responses scoped to venue HTTP tests."""

    def __init__(self, intent, target_reference=""):
        self.intent = intent
        self.target_reference = target_reference

    def chat(self, *args, **kwargs):
        schema = kwargs.get("format", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "intent" in properties:
            packet = {
                "intent": self.intent,
                "action": "travel" if self.intent == "travel" else "narrative",
                "target": {
                    "type": "location" if self.intent == "travel" else "none",
                    "reference": self.target_reference,
                },
                "completion": "completed",
                "confidence": 1.0,
            }
        else:
            packet = {
                "narration": (
                    "Yolculuk tamamlandı."
                    if self.intent == "travel"
                    else "Kapı açıldı; bulunduğun yer değişmedi."
                ),
                "world_updates": {},
                "lore_claims": [],
            }
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class CapturingConversationContextClient(ControlledVenueOllamaClient):
    def __init__(self):
        super().__init__(intent="narrative")
        self.message_batches = []
        self.generated_narrations = []
        self.intent_schemas = []
        self.conversation_replies = []
        self.chat_calls = 0

    def chat(self, *args, **kwargs):
        self.chat_calls += 1
        messages = copy.deepcopy(kwargs.get("messages", []))
        schema = kwargs.get("format", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if "intent" in properties:
            self.intent_schemas.append(copy.deepcopy(schema))
            self.message_batches.append(messages)
            response = super().chat(*args, **kwargs)
            packet = json.loads(response["message"]["content"])
            prompt = next(
                item.get("content", "")
                for item in reversed(messages)
                if item.get("role") == "user"
            )
            quote = prompt.split("Current player message: ", 1)[-1].splitlines()[0]
            marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
            context_text = prompt.split(marker, 1)[1]
            context, _ = json.JSONDecoder().raw_decode(context_text)
            addressee = context.get("addressee") or {}
            focus = context.get("conversation_focus") or {}
            name = addressee.get("name", "")
            candidates = context.get("conversation_candidates", [])
            candidate_by_field = {
                item.get("field"): item.get("evidence_id")
                for item in candidates if isinstance(item, dict)
            }
            if "şu an ne yapıyorsun" in quote.casefold():
                meaning, field = "current_activity", "current_activity"
                subject, role = name, "addressee"
            elif "neden buraya geldin" in quote.casefold():
                meaning, field = "personal_purpose", "reason_for_being_here"
                subject, role = name, "addressee"
            elif "arıyorsun" in quote.casefold():
                meaning, field = "personal_purpose", "reason_for_being_here"
                subject, role = name, "addressee"
            elif "neden bunu yap" in quote.casefold() and focus:
                field = focus.get("predicate")
                meaning = (
                    "current_activity"
                    if field == "current_activity"
                    else "cause"
                )
                subject, role = name, "addressee"
            elif quote.casefold().rstrip().endswith(("neden?", "niye?")) and focus:
                field = focus.get("predicate")
                if field == "reason_for_being_here":
                    meaning, subject, role = "personal_purpose", name, "addressee"
                else:
                    meaning, subject, role = "cause", "", "unknown"
            elif "neden kilitli" in quote.casefold() and focus:
                field = focus.get("predicate")
                meaning, subject, role = "cause", "", "unknown"
            else:
                meaning, field = "cause", None
                subject = next(
                    (word for word in ("Sera", "kervan", "ejderha", "kapı", "Neverwinter")
                     if word.casefold() in quote.casefold()),
                    "",
                )
                role = "other_actor" if subject in {"Sera", "kervan", "ejderha"} else "world_entity"
            proposal = {
                "addressee_id": addressee.get("npc_id"),
                "subject_phrase": subject,
                "subject_role": role,
                "meaning": meaning,
                "topic_relation": (
                    "followup"
                    if focus and field == focus.get("predicate")
                    else "topic_change" if focus else "new"
                ),
                "candidate_evidence_ids": (
                    [candidate_by_field[field]]
                    if field and candidate_by_field.get(field) else []
                ),
            }
            reply = self.conversation_replies.pop(0) if self.conversation_replies else {}
            proposal = reply.get("conversation", proposal)
            if reply.get("include_interaction", True):
                if isinstance(reply.get("interaction"), dict):
                    packet["interaction"] = copy.deepcopy(reply["interaction"])
                else:
                    packet["interaction"] = {
                        "operation": reply.get("operation", "none"),
                        "quote": reply.get("quote", quote),
                        "conversation": proposal,
                    }
                    if not reply.get("include_conversation", True):
                        packet["interaction"].pop("conversation", None)
            else:
                packet.pop("interaction", None)
            packet["narration"] = reply.get(
                "narration", "Bu konuda doğrulanmış bir bilgi yok."
            )
            if not reply.get("include_narration", True):
                packet.pop("narration", None)
            return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}
        self.message_batches.append(messages)
        marker = "CURRENT LOCAL SCENE STATE (Python-owned, read-only):\n"
        scene = None
        for item in messages:
            content = item.get("content", "")
            if marker in content:
                raw = content.split(marker, 1)[1].split(
                    "\n\nRECENT NARRATION", 1
                )[0]
                scene = json.loads(raw)
                break
        accepted = (scene or {}).get("accepted_npc_profile") or {}
        cause = next(
            (
                item.get("value")
                for item in accepted.get("evidence", [])
                if item.get("field") == "reason_for_being_here"
                and isinstance(item.get("value"), str)
                and item.get("value").strip()
            ),
            None,
        )
        narration = (
            f'Marek, “{cause}” diye açıklar.'
            if cause
            else "Bu konuda elimde doğrulanmış bir neden yok; kesin konuşamam."
        )
        self.generated_narrations.append(narration)
        packet = {"narration": narration, "world_updates": {}, "lore_claims": []}
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class ControlledSceneDetailOllamaClient(FakeOllamaClient):
    """Synthetic provider proposing one new local detail beneath a building."""

    def __init__(self, location_id, parent_id, proposals=None, narration=None):
        self.location_id = location_id
        self.parent_id = parent_id
        self.proposals = proposals
        self.narration = narration or "Girişte taş bir kartal kabartması göze çarpıyor."
        self.calls = 0
        self.last_intent_schema_has_proposals = False
        self.last_intent_proposals = None

    def chat(self, *args, **kwargs):
        self.calls += 1
        properties = kwargs.get("format", {}).get("properties", {})
        if "intent" in properties:
            self.last_intent_schema_has_proposals = (
                "scene_detail_proposals" in properties
            )
            packet = {
                "intent": "explore",
                "action": "narrative",
                "target": {"type": "location", "reference": ""},
                "explore_type": "inspect",
                "completion": "completed",
                "confidence": 1.0,
            }
            packet["scene_detail_proposals"] = copy.deepcopy(
                self.proposals if self.proposals is not None else [{
                    "proposal_key": "f1",
                    "location": self.location_id,
                    "parent_id": self.parent_id,
                    "name": "Taş Kartal Kabartması",
                    "description": "Giriş kemerinin üstünde taşa işlenmiş küçük bir kartal.",
                    "kind": "detail",
                    "aliases": ["taş kartal", "kartal kabartması"],
                }]
            )
            self.last_intent_proposals = copy.deepcopy(
                packet["scene_detail_proposals"]
            )
        else:
            packet = {
                "narration": self.narration,
                "world_updates": {},
                "lore_claims": [],
            }
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class RecordedStoneworkOllamaClient(FakeOllamaClient):
    """Replays the captured Qwen investigation response for the stonework case."""

    def __init__(self):
        self.calls = 0
        self.intent_schema_has_scene_proposals = False
        self.intent_response = None
        self.intent_messages = None
        self.intent_schema = None

    def chat(self, *args, **kwargs):
        self.calls += 1
        properties = kwargs.get("format", {}).get("properties", {})
        if "intent" in properties:
            self.intent_schema_has_scene_proposals = (
                "scene_detail_proposals" in properties
            )
            self.intent_messages = copy.deepcopy(kwargs.get("messages"))
            self.intent_schema = copy.deepcopy(kwargs.get("format"))
            packet = {
                "intent": "investigation",
                "action": "investigate",
                "target": {
                    "type": "location",
                    "reference": "Han binasının girişindeki taş işçiliği",
                },
                "completion": "intended",
                "confidence": 1.0,
                "interaction": {"operation": "none"},
                "scene_detail_proposals": [{
                    "proposal_key": "stone_carving_details",
                    "location": "location_001",
                    "parent_id": "location_001",
                    "name": "Gizli taş işçiliği detayı",
                    "description": (
                        "Gizli bir taş işçiliği detayı, muhtemelen bir gizli "
                        "geçit veya bir tarihî bilgiye işaret edebilir."
                    ),
                    "kind": "local",
                    "aliases": [
                        "gizli taş işçiliği detayı",
                        "gizli geçit",
                        "tarihî bilgi",
                    ],
                }],
            }
            self.intent_response = copy.deepcopy(packet)
        else:
            packet = {
                "narration": "Taş işçiliğini dikkatle inceliyorsun.",
                "world_updates": {},
                "lore_claims": [],
            }
        return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}


class CampaignApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(
            Path(self.temporary_directory.name) / "campaigns.sqlite3",
            bound_principal=TEST_PLAYER,
        )
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.enterContext(adapter.engine_binding())
        app_options = {"authenticator": FixedAuthenticator(TEST_PLAYER)}
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=adapter,
            **app_options,
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()
        self.temporary_directory.cleanup()

    async def create_campaign(self):
        response = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def post_scene_turn(self, url, model, body):
        with (
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("External network is disabled in this API test."),
            ),
            patch.object(self.app.state.ollama_adapter, "_client", model),
        ):
            return await self.http.post(url, json=body)

    async def test_unpunctuated_locked_followup_reaches_same_npc_door_context(self):
        city_id, session_id, session, turn_url, tavern_id, door = (
            await create_city_with_locked_tavern(self)
        )
        marek = {
            "id": "npc_marek",
            "name": "Marek",
            "role": "keeper",
            "location": city_id,
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        private_other_npc_fact = "SERA_PRIVATE_SECRET_NOT_FOR_MAREK_82c1"
        session.world_state["npcs"].append({
            "id": "npc_sera",
            "name": "Sera",
            "role": "guard",
            "location": city_id,
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [private_other_npc_fact],
            "memory": [{
                "speaker": "npc",
                "text": private_other_npc_fact,
            }],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        })
        client = CapturingConversationContextClient()
        trace = {
            "api_turns": [],
            "owner_answer": [],
            "focus_write": [],
            "http_response": None,
        }

        original_direct = game._direct_npc_smalltalk_response
        original_focus_writer = game._remember_owner_locked_tavern_focus
        original_run_player_turn = session.run_player_turn

        @wraps(original_run_player_turn)
        def traced_run_player_turn(player_input, *args, **kwargs):
            trace["api_turns"].append({
                "player_input": player_input,
                "target_id": kwargs.get("target_id"),
                "interaction_mode": kwargs.get("interaction_mode"),
                "scene_plan": copy.deepcopy(kwargs.get("scene_plan")),
                "session_matches_manager": (
                    self.manager.get(session_id).game_session is session
                ),
            })
            return original_run_player_turn(player_input, *args, **kwargs)

        def traced_direct(player_input, npc_target):
            result = original_direct(player_input, npc_target)
            trace["owner_answer"].append({
                "player_input": player_input,
                "npc_id": (
                    npc_target.get("id") if isinstance(npc_target, dict) else None
                ),
                "active_session_matches_manager": game._session() is session,
                "response": result,
            })
            return result

        def traced_focus_writer(player_input, npc_target, action_id):
            focus_state = session.world_state.get("interaction_adventure_v1", {})
            before = copy.deepcopy(focus_state.get("conversation_focus"))
            result = original_focus_writer(player_input, npc_target, action_id)
            focus_state = session.world_state.get("interaction_adventure_v1", {})
            trace["focus_write"].append({
                "called": True,
                "player_input": player_input,
                "npc_id": (
                    npc_target.get("id") if isinstance(npc_target, dict) else None
                ),
                "action_id": action_id,
                "active_session_matches_manager": game._session() is session,
                "before": before,
                "after": copy.deepcopy(focus_state.get("conversation_focus")),
            })
            return result

        async def say(message, action_id=None):
            return await self.post_scene_turn(
                turn_url,
                client,
                {
                    "message": message,
                    "action_id": action_id or str(uuid.uuid4()),
                },
            )

        greeting = await say("Merhaba Marek.")
        self.assertEqual(greeting.status_code, 200, greeting.text)
        with (
            patch.object(
                session, "run_player_turn", traced_run_player_turn, create=True
            ),
            patch.object(game, "_direct_npc_smalltalk_response", side_effect=traced_direct),
            patch.object(game, "_remember_owner_locked_tavern_focus", side_effect=traced_focus_writer),
        ):
            tavern_action_id = str(uuid.uuid4())
            world_before_failed_save = copy.deepcopy(session.world_state)
            rng_before_failed_save = session.rng.getstate()
            with patch.object(
                self.manager,
                "autosave_turn",
                side_effect=CampaignStorageError("synthetic save failure"),
            ):
                failed_save = await say(
                    "Buralarda han var mı Marek?", tavern_action_id
                )
            self.assertGreaterEqual(failed_save.status_code, 500, failed_save.text)
            self.assertEqual(session.world_state, world_before_failed_save)
            self.assertEqual(session.rng.getstate(), rng_before_failed_save)
            tavern_answer = await say(
                "Buralarda han var mı Marek?", tavern_action_id
            )
        self.assertEqual(tavern_answer.status_code, 200, tavern_answer.text)
        tavern_payload = tavern_answer.json()
        trace["http_response"] = {
            "narration": tavern_payload.get("narration"),
            "action_result": tavern_payload.get("action_result"),
        }
        self.assertTrue(
            trace["api_turns"]
            and trace["api_turns"][-1]["player_input"] == "Buralarda han var mı Marek?",
            json.dumps(trace, ensure_ascii=False),
        )
        self.assertIn("kilitli", tavern_payload["narration"].casefold())
        stored_focus = session.world_state.get(
            "interaction_adventure_v1", {}
        ).get("conversation_focus")
        self.assertIsInstance(stored_focus, dict, json.dumps(trace, ensure_ascii=False))
        self.assertEqual(stored_focus.get("speaker_id"), marek["id"])
        self.assertEqual(stored_focus.get("scene_id"), city_id)
        self.assertEqual(stored_focus.get("subject_id"), door["id"])
        self.assertEqual(stored_focus.get("predicate"), "locked")
        self.assertIs(stored_focus.get("value"), True)
        self.assertEqual(stored_focus.get("epistemic"), "owner_verified")
        campaign_id = self.manager.get(session_id).campaign_id
        focus_before_failed_save = copy.deepcopy(stored_focus)
        memory_before_failed_save = copy.deepcopy(marek["memory"])
        failed_focus_action_id = str(uuid.uuid4())
        with patch.object(
            self.manager,
            "autosave_turn",
            side_effect=CampaignStorageError("synthetic focus save failure"),
        ):
            failed_focus_save = await say(
                "Buralarda han var mı Marek?", failed_focus_action_id
            )
        self.assertGreaterEqual(
            failed_focus_save.status_code, 500, failed_focus_save.text
        )
        self.assertEqual(
            session.world_state["interaction_adventure_v1"]["conversation_focus"],
            focus_before_failed_save,
        )
        current_marek = next(
            npc for npc in session.world_state["npcs"]
            if npc.get("id") == marek["id"]
        )
        self.assertEqual(current_marek["memory"], memory_before_failed_save)
        calls_before_replay = len(client.message_batches)
        replay = await say("Buralarda han var mı Marek?", tavern_action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), tavern_answer.json())
        self.assertEqual(len(client.message_batches), calls_before_replay)

        old_http = self.http
        resumed_manager = SessionManager(campaign_store=self.store)
        resumed_adapter = AuthenticatedOllamaAdapter(client)
        self.app = create_app(
            session_manager=resumed_manager,
            ollama_adapter=resumed_adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        await old_http.aclose()
        resumed = await self.http.post(
            f"/api/game/campaigns/{campaign_id}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        session_id = resumed.json()["session_id"]
        session = resumed_manager.get(session_id).game_session
        turn_url = f"/api/game/sessions/{session_id}/turn"
        resumed_focus = session.world_state.get(
            "interaction_adventure_v1", {}
        ).get("conversation_focus")
        self.assertEqual(resumed_focus, stored_focus)
        trace["focus_before_followup"] = {
            "raw": copy.deepcopy(stored_focus),
            "validated": game.interaction_adventure.current_conversation_focus(
                session.world_state, marek
            ),
            "turn_index": session.world_state.get("flags", {}).get("turn_index"),
            "active_npc_id": session.world_state.get("flags", {}).get("active_npc_id"),
            "active_npc_until_turn": session.world_state.get("flags", {}).get(
                "active_npc_until_turn"
            ),
        }

        before_followup = {
            "location": copy.deepcopy(session.world_state.get("location")),
            "doors": copy.deepcopy(session.world_state.get("doors")),
            "rng": session.rng.getstate(),
            "campaign_time": copy.deepcopy(session.world_state.get("campaign_time")),
            "inventory": copy.deepcopy(session.world_state.get("inventory")),
            "quests": copy.deepcopy(session.world_state.get("quests")),
        }
        resolved_targets = []
        original_resolver = game.resolve_npc_reference

        def trace_resolver(text, *args, **kwargs):
            resolution = original_resolver(text, *args, **kwargs)
            if text == "neden kilitli":
                resolved_targets.append(copy.deepcopy(resolution))
            return resolution

        with patch.object(game, "resolve_npc_reference", side_effect=trace_resolver):
            followup = await say("neden kilitli")
        self.assertEqual(followup.status_code, 200, followup.text)
        self.assertTrue(resolved_targets)
        self.assertEqual(resolved_targets[-1]["npc"]["id"], marek["id"])
        self.assertTrue(client.message_batches, "The intent parser was not reached.")
        context_text = json.dumps(client.message_batches, ensure_ascii=False)
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        message = next(
            item["content"]
            for batch in reversed(client.message_batches)
            for item in reversed(batch)
            if marker in item.get("content", "")
        )
        scene_context = json.loads(
            message.split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
        )
        def latest_scene_context():
            latest = next(
                item["content"]
                for batch in reversed(client.message_batches)
                for item in reversed(batch)
                if marker in item.get("content", "")
            )
            return json.loads(
                latest.split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
            )

        focus_in_model_context = scene_context["conversation_focus"]
        self.assertEqual(scene_context["addressee"]["npc_id"], marek["id"])
        self.assertEqual(focus_in_model_context["speaker_id"], marek["id"])
        self.assertEqual(focus_in_model_context["scene_id"], city_id)
        self.assertEqual(focus_in_model_context["subject_id"], door["id"])
        self.assertEqual(focus_in_model_context["evidence_id"], door["id"])
        self.assertEqual(focus_in_model_context["predicate"], "locked")
        self.assertNotIn("value", focus_in_model_context)
        self.assertEqual(focus_in_model_context["epistemic"], "owner_verified")
        self.assertNotIn("reason_for_lock", context_text)
        self.assertNotIn(private_other_npc_fact, context_text)
        other_venue_world = copy.deepcopy(session.world_state)
        other_venue = copy.deepcopy(
            other_venue_world["locations"][tavern_id]
        )
        other_venue["name"] = "Demirci Hanı"
        other_venue_world["locations"]["focus-outside-location"] = other_venue
        self.assertFalse(
            game.interaction_adventure.is_focus_followup(
                other_venue_world,
                "Marek, Demirci Hanı kapısı neden kilitli?",
            )
        )

        after_followup = {
            "location": session.world_state.get("location"),
            "doors": session.world_state.get("doors"),
            "rng": session.rng.getstate(),
            "campaign_time": session.world_state.get("campaign_time"),
            "inventory": session.world_state.get("inventory"),
            "quests": session.world_state.get("quests"),
        }
        self.assertEqual(after_followup, before_followup)

        for epistemic in ("player_claim", "rumor", "belief"):
            untrusted = copy.deepcopy(session.world_state)
            untrusted["interaction_adventure_v1"]["conversation_focus"] = (
                copy.deepcopy(stored_focus)
            )
            untrusted["interaction_adventure_v1"]["conversation_focus"][
                "epistemic"
            ] = epistemic
            self.assertIsNone(
                game.interaction_adventure.current_conversation_focus(
                    untrusted, marek
                ),
                epistemic,
            )
        stale = copy.deepcopy(session.world_state)
        stale["flags"]["turn_index"] = stored_focus["turn"] + 7
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(stale, marek)
        )
        changed_speaker = copy.deepcopy(session.world_state)
        changed_speaker["flags"]["active_npc_id"] = "npc_sera"
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(
                changed_speaker, marek
            )
        )
        wrong_npc = copy.deepcopy(marek)
        wrong_npc["id"] = "npc_sera"
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(
                session.world_state, wrong_npc
            )
        )

        short_followup = await say("Niye?")
        self.assertEqual(short_followup.status_code, 200, short_followup.text)
        short_scene = latest_scene_context()
        self.assertEqual(
            short_scene["conversation_focus"]["subject_id"], door["id"]
        )
        self.assertEqual(short_scene["addressee"]["npc_id"], marek["id"])

        other_topic = await say("Marek, bugün hava nasıl?")
        self.assertEqual(other_topic.status_code, 200, other_topic.text)
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(
                session.world_state, marek
            )
        )
        self.assertIsNone(
            session.world_state["interaction_adventure_v1"]["conversation_focus"]
        )

        other_speaker = await say("Sera, bugün hava nasıl?")
        self.assertEqual(other_speaker.status_code, 200, other_speaker.text)
        self.assertEqual(
            session.world_state["flags"]["active_npc_id"], "npc_sera"
        )
        self.assertIsNone(
            session.world_state["interaction_adventure_v1"]["conversation_focus"]
        )

        duplicate_marek = copy.deepcopy(marek)
        duplicate_marek["id"] = "npc_marek_duplicate"
        session.world_state["npcs"].append(duplicate_marek)
        calls_before_ambiguous_address = len(client.message_batches)
        ambiguous_address = await say("Marek, neden kilitli?")
        self.assertEqual(ambiguous_address.status_code, 200, ambiguous_address.text)
        self.assertEqual(
            len(client.message_batches), calls_before_ambiguous_address
        )

    async def test_personal_profile_why_followup_reaches_same_npc_context(self):
        city_id, session_id, session, turn_url, _, _ = (
            await create_city_with_locked_tavern(self)
        )
        profile = {
            "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
            "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
            "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
            "mood": "İyiyim.",
            "recent_activity": "Sabah pazardan yeşil iplik aldım.",
            "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
            "reason_for_being_here": "Arşivciye verdiğim sözü tutup kayıp yük kayıtlarını bulmaya çalışıyorum.",
            "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
            "immediate_goal": "Bugün tasnifi bitirmek.",
        }
        marek = {
            "id": "npc_marek_profile",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": profile,
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        private_fact = "OTHER_NPC_PRIVATE_PROFILE_SENTINEL"
        session.world_state.setdefault("npcs", []).extend([
            marek,
            {
                "id": "npc_sera_profile",
                "name": "Sera",
                "role": "guard",
                "location": city_id,
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                "personal_profile": {"private_detail": private_fact},
                "personality": "",
                "appearance": "",
                "relationship": "neutral",
                "knowledge": [private_fact],
                "memory": [],
                "combat_status": "active",
                "current_hp": 12,
                "status": "active",
            },
        ])
        client = CapturingConversationContextClient()

        async def say(message):
            return await self.post_scene_turn(
                turn_url, client, {
                    "message": message,
                    "interaction_mode": "say",
                    "target_id": marek["id"],
                    "action_id": str(uuid.uuid4()),
                }
            )

        first_model = await say("Marek, neden kayıp yük kayıtlarını arıyorsun?")
        self.assertEqual(first_model.status_code, 200, first_model.text)
        first_context = json.dumps(client.message_batches, ensure_ascii=False)
        self.assertIn(profile["reason_for_being_here"], first_context)
        self.assertIn(
            f"npc-profile:{marek['id']}:v1:reason_for_being_here",
            first_context,
        )

        first = await say("Marek, şu an ne yapıyorsun?")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn(profile["current_activity"], first.json()["narration"])
        stored_focus = session.world_state["interaction_adventure_v1"].get(
            "conversation_focus"
        )
        self.assertIsInstance(stored_focus, dict)
        campaign_id = self.manager.get(session_id).campaign_id
        resumed_manager = SessionManager(campaign_store=self.store)
        self.app = create_app(
            session_manager=resumed_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(client),
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        resumed = await self.http.post(
            f"/api/game/campaigns/{campaign_id}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        resumed_session_id = resumed.json()["session_id"]
        resumed_session = resumed_manager.get(resumed_session_id).game_session
        turn_url = f"/api/game/sessions/{resumed_session_id}/turn"
        self.assertEqual(
            resumed_session.world_state["interaction_adventure_v1"][
                "conversation_focus"
            ],
            stored_focus,
        )
        followup = await say("Marek, neden?")
        self.assertEqual(followup.status_code, 200, followup.text)
        self.assertNotIn(profile["reason_for_being_here"], followup.json()["narration"])
        messages = client.message_batches[-1]
        context_text = json.dumps(messages, ensure_ascii=False)
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        payload = next(
            item["content"].split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
            for item in messages
            if marker in item.get("content", "")
        )
        scene = json.loads(payload)
        focus = scene["conversation_focus"]
        self.assertEqual(scene["addressee"]["npc_id"], marek["id"])
        self.assertEqual(focus["speaker_id"], marek["id"])
        self.assertEqual(
            focus["subject_id"], f"npc-profile:{marek['id']}:current_activity"
        )
        self.assertEqual(focus["predicate"], "current_activity")
        self.assertNotIn("value", focus)
        self.assertEqual(focus["epistemic"], "witnessed")
        self.assertNotIn("accepted_npc_profile", scene)
        self.assertNotIn(private_fact, context_text)
        action_followup = await say("Neden bunu yapıyorsun?")
        self.assertEqual(action_followup.status_code, 200, action_followup.text)
        self.assertNotIn(
            profile["reason_for_being_here"], action_followup.json()["narration"]
        )
        self.assertEqual(
            session.world_state["interaction_adventure_v1"]["conversation_focus"][
                "subject_id"
            ],
            f"npc-profile:{marek['id']}:current_activity",
        )
        rumor = "Kasaba söylentisine göre, kayıp yük kayıtlarını bir tüccar saklıyor."
        current_marek = next(
            npc for npc in resumed_session.world_state["npcs"]
            if npc.get("id") == marek["id"]
        )
        current_marek["personal_profile"]["reason_for_being_here"] = rumor
        attributed = await say("Marek, neden kayıp yük kayıtlarını arıyorsun?")
        self.assertEqual(attributed.status_code, 200, attributed.text)
        self.assertIn("söylentisine göre", attributed.json()["narration"].casefold())
        self.assertIn(rumor, attributed.json()["narration"])
        current_marek["personal_profile"]["reason_for_being_here"] = ""
        sera = next(
            npc for npc in resumed_session.world_state["npcs"]
            if npc.get("id") == "npc_sera_profile"
        )
        other_npc_only_cause = "SERA_ONLY_CAUSE_SENTINEL_03f7"
        sera["personal_profile"]["reason_for_being_here"] = other_npc_only_cause
        sera["knowledge"].append(other_npc_only_cause)
        unknown = await say("Marek, neden kayıp yük kayıtlarını arıyorsun?")
        self.assertEqual(unknown.status_code, 200, unknown.text)
        # In-character "I do not know" (wording varies by NPC and input).
        self.assertTrue(
            any(marker in unknown.json()["narration"]
                for marker in ("bilmiyorum", "emin değilim")),
            unknown.json()["narration"],
        )
        unknown_context = json.dumps(client.message_batches[-1], ensure_ascii=False)
        self.assertNotIn(other_npc_only_cause, unknown_context)
        self.assertNotIn(other_npc_only_cause, unknown.json()["narration"])

    async def test_changed_door_invalidates_focus_and_legacy_focus_defaults(self):
        city_id, session_id, session, turn_url, tavern_id, door = (
            await create_city_with_locked_tavern(self)
        )
        marek = {
            "id": "npc_marek_door_lifecycle",
            "name": "Marek",
            "role": "keeper",
            "location": city_id,
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        first = await self.post_scene_turn(turn_url, client, {
            "message": "Buralarda han var mı Marek?",
            "action_id": str(uuid.uuid4()),
        })
        self.assertEqual(first.status_code, 200, first.text)
        focus = copy.deepcopy(
            session.world_state["interaction_adventure_v1"]["conversation_focus"]
        )
        self.assertEqual(focus["subject_id"], door["id"])

        door["locked"] = False
        opened = await self.post_scene_turn(turn_url, client, {
            "message": "Kapıyı açıyorum.",
            "action_id": str(uuid.uuid4()),
        })
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertTrue(door["open"])
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(
                session.world_state, marek
            )
        )
        changed_state = await self.post_scene_turn(turn_url, client, {
            "message": "Marek, kapı artık neden kilitli değil?",
            "action_id": str(uuid.uuid4()),
        })
        self.assertEqual(changed_state.status_code, 200, changed_state.text)
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        changed_messages = client.message_batches[-1]
        changed_payload = next(
            item["content"].split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
            for item in changed_messages
            if marker in item.get("content", "")
        )
        self.assertIsNone(json.loads(changed_payload)["conversation_focus"])
        legacy_world = copy.deepcopy(session.world_state)
        legacy_world["interaction_adventure_v1"].pop("conversation_focus", None)
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(
                legacy_world, marek
            )
        )
        profile_world = copy.deepcopy(session.world_state)
        profile_owner = {
            **marek,
            "id": "npc_malformed_focus_owner",
            "location": city_id,
            "personal_profile": {
                "reason_for_being_here": "Kayıp defteri bulmak.",
            },
        }
        profile_world["npcs"].append(profile_owner)
        profile_world["flags"]["active_npc_id"] = profile_owner["id"]
        profile_world["flags"]["active_npc_until_turn"] = (
            profile_world["flags"]["turn_index"] + 6
        )
        game.interaction_adventure.remember_conversation_focus(
            profile_world,
            speaker_id=profile_owner["id"],
            scene_id=city_id,
            subject_id=f"npc-profile:{profile_owner['id']}:reason_for_being_here",
            predicate="reason_for_being_here",
            value="Kayıp defteri bulmak.",
            turn=profile_world["flags"]["turn_index"],
            action_id="profile-focus-test",
            evidence_id=f"npc-profile:{profile_owner['id']}:v1:reason_for_being_here",
            epistemic="witnessed",
        )
        self.assertIsNotNone(
            game.interaction_adventure.current_conversation_focus(
                profile_world, profile_owner
            )
        )
        malformed_world = copy.deepcopy(profile_world)
        malformed_world["interaction_adventure_v1"]["conversation_focus"][
            "subject_id"
        ] = "npc-profile:malformed"
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(
                malformed_world, profile_owner
            )
        )
        for status, location in (("dead", city_id), ("active", "somewhere-else")):
            stale_world = copy.deepcopy(profile_world)
            stale_owner = next(
                npc for npc in stale_world["npcs"]
                if npc["id"] == profile_owner["id"]
            )
            stale_owner["status"] = status
            stale_owner["location"] = location
            self.assertIsNone(
                game.interaction_adventure.current_conversation_focus(
                    stale_world, stale_owner
                ),
                f"Stale profile focus must be ignored for {status=} {location=}.",
            )
        campaign_id = self.manager.get(session_id).campaign_id
        session.world_state["interaction_adventure_v1"].pop(
            "conversation_focus", None
        )
        self.manager.save_campaign(campaign_id)
        resumed_manager = SessionManager(campaign_store=self.store)
        self.app = create_app(
            session_manager=resumed_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(client),
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        resumed = await self.http.post(
            f"/api/game/campaigns/{campaign_id}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        resumed_session = resumed_manager.get(
            resumed.json()["session_id"]
        ).game_session
        self.assertNotIn(
            "conversation_focus",
            resumed_session.world_state["interaction_adventure_v1"],
        )
        self.assertIsNone(
            game.interaction_adventure.current_conversation_focus(
                resumed_session.world_state, marek
            )
        )

    async def test_focus_does_not_resurrect_after_topic_or_speaker_change(self):
        city_id, _, session, turn_url, _, door = await create_city_with_locked_tavern(self)
        marek = {
            "id": "npc_marek_focus_lifecycle",
            "name": "Marek",
            "role": "keeper",
            "location": city_id,
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        sera = {
            **marek,
            "id": "npc_sera_focus_lifecycle",
            "name": "Sera",
            "role": "guard",
        }
        session.world_state.setdefault("npcs", []).extend([marek, sera])
        client = CapturingConversationContextClient()

        async def say(message):
            return await self.post_scene_turn(
                turn_url, client, {"message": message, "action_id": str(uuid.uuid4())}
            )

        async def focus_for(message):
            response = await say(message)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(client.message_batches, "Expected the real narrative request.")
            marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
            content = next(
                item["content"]
                for item in client.message_batches[-1]
                if marker in item.get("content", "")
            )
            return json.loads(
                content.split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
            )["conversation_focus"]

        first = await say("Buralarda han var mı Marek?")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(
            session.world_state["interaction_adventure_v1"]["conversation_focus"][
                "subject_id"
            ],
            door["id"],
        )
        await say("Marek, bugün hava nasıl?")
        reactivated_after_topic = await focus_for("Niye?")
        self.assertIsNone(
            reactivated_after_topic,
            "A completed off-topic turn must retire the previous door focus.",
        )
        await say("Sera, bugün hava nasıl?")
        reactivated_after_speaker = await focus_for("Marek, neden?")
        self.assertIsNone(
            reactivated_after_speaker,
            "Switching away from and back to Marek must not revive retired focus.",
        )

    async def test_named_non_tavern_building_does_not_inherit_tavern_focus_over_http(self):
        city_id, _, session, turn_url, _, door = await create_city_with_locked_tavern(self)
        marek = {
            "id": "npc_marek_named_building",
            "name": "Marek",
            "role": "keeper",
            "location": city_id,
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        session.world_state["locations"]["fr:building:neverwinter_prison"] = {
            "id": "fr:building:neverwinter_prison",
            "name": "Hapishane",
            "type": "building",
            "scene_kind": "building",
            "parent_location_id": city_id,
        }
        client = CapturingConversationContextClient()
        first = await self.post_scene_turn(turn_url, client, {
            "message": "Buralarda han var mı Marek?",
            "action_id": str(uuid.uuid4()),
        })
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(
            session.world_state["interaction_adventure_v1"]["conversation_focus"][
                "subject_id"
            ],
            door["id"],
        )
        response = await self.post_scene_turn(turn_url, client, {
            "message": "Hapishane kapısı neden kilitli?",
            "action_id": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(client.message_batches, "Expected the real narrative request.")
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        content = next(
            item["content"]
            for item in client.message_batches[-1]
            if marker in item.get("content", "")
        )
        scene = json.loads(
            content.split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
        )
        self.assertIsNone(scene["conversation_focus"])
        self.assertNotEqual(
            (scene["conversation_focus"] or {}).get("subject_id"), door["id"]
        )

    async def test_profile_why_does_not_bypass_unverified_lore_safety(self):
        city_id, session_id, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        marek = {
            "id": "npc_marek_lore_safety",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": "Arşivde kayıp yük kayıtlarını bulmaya geldim.",
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        purpose = marek["personal_profile"]["reason_for_being_here"]
        greeting = await self.post_scene_turn(turn_url, client, {
            "message": "Marek, şu an ne yapıyorsun?",
            "interaction_mode": "say",
            "action_id": str(uuid.uuid4()),
            "target_id": marek["id"],
        })
        self.assertEqual(greeting.status_code, 200, greeting.text)
        self.assertIsInstance(
            session.world_state["interaction_adventure_v1"]["conversation_focus"],
            dict,
        )
        batches_before_lore_question = len(client.message_batches)
        response = await self.post_scene_turn(turn_url, client, {
            "message": "Marek, Neverwinter neden gizlice bir ejderha tarafından yönetiliyor?",
            "interaction_mode": "say",
            "action_id": str(uuid.uuid4()),
            "target_id": marek["id"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(
            purpose, response.json()["narration"],
            "Unrelated NPC purpose must not answer an unsupported lore question.",
        )
        self.assertTrue(
            any(term in response.json()["narration"].casefold() for term in (
                "doğrulanmış", "belirsiz", "kesin konuşamam",
            )),
            response.json()["narration"],
        )
        self.assertEqual(
            len(client.message_batches), batches_before_lore_question,
            "Unsupported lore remains on the deterministic safety path.",
        )

    async def test_activity_why_does_not_inherit_unrelated_profile_purpose(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        activity = "Sabah yeşil iplik aldım."
        purpose = "Arşivde kayıp yük kayıtlarını bulmaya geldim."
        marek = {
            "id": "npc_marek_unrelated_profile_reason",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": activity,
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan kurdele aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": purpose,
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()

        async def say(message):
            return await self.post_scene_turn(
                turn_url, client, {
                    "message": message,
                    "interaction_mode": "say",
                    "target_id": marek["id"],
                    "action_id": str(uuid.uuid4()),
                }
            )

        first = await say("Marek, şu an ne yapıyorsun?")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn(activity, first.json()["narration"])
        followup = await say("Marek, neden?")
        self.assertEqual(followup.status_code, 200, followup.text)
        marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        messages = client.message_batches[-1]
        scene_text = next(
            item["content"].split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
            for item in messages
            if marker in item.get("content", "")
        )
        scene = json.loads(scene_text)
        self.assertEqual(
            scene["conversation_focus"]["subject_id"],
            f"npc-profile:{marek['id']}:current_activity",
        )
        self.assertIn(purpose, json.dumps(scene, ensure_ascii=False))
        self.assertNotIn(
            purpose, followup.json()["narration"],
            "A profile purpose is not evidence for an unrelated activity's cause.",
        )
        self.assertTrue(
            any(term in followup.json()["narration"].casefold()
                for term in (
                    "bilmiyorum", "emin değilim", "kesin konuşamam",
                    "belirsiz", "doğrulamam yok", "bilgi yok",
                )),
            followup.json()["narration"],
        )

    async def test_free_http_profile_purpose_is_owned_by_personal_topic(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        purpose = "Arşivde kayıp yük kayıtlarını bulmaya geldim."
        activity = "Sabah yeşil iplik aldım."
        marek = {
            "id": "npc_marek_free_profile_scope",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": activity,
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan kurdele aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": purpose,
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()

        async def post(message):
            return await self.post_scene_turn(
                turn_url,
                client,
                {"message": message, "action_id": str(uuid.uuid4())},
            )

        def last_scene():
            messages = client.message_batches[-1]
            marker = "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
            content = next(
                item["content"]
                for item in messages
                if marker in item.get("content", "")
            )
            raw = content.split(marker, 1)[1].split("\nNPC dialogue mode", 1)[0]
            return json.loads(raw), json.dumps(messages, ensure_ascii=False)

        direct = await post("Marek, neden buraya geldin?")
        self.assertEqual(direct.status_code, 200, direct.text)
        self.assertIn(purpose, direct.json()["narration"])
        self.assertEqual(
            len(client.intent_schemas),
            1,
            "A free personal question must use exactly one existing intent call.",
        )
        self.assertIn(
            "conversation",
            client.intent_schemas[-1]["properties"]["interaction"]["properties"],
        )
        self.assertEqual(
            session.world_state["interaction_adventure_v1"][
                "conversation_focus"
            ]["predicate"],
            "reason_for_being_here",
        )

        continued = await post("Marek, neden?")
        self.assertEqual(continued.status_code, 200, continued.text)
        self.assertTrue(
            client.message_batches,
            "Expected a real first conversation-model input after the owned answer.",
        )
        continued_scene, continued_context = last_scene()
        self.assertIn(
            f"npc-profile:{marek['id']}:v1:reason_for_being_here",
            [item["evidence_id"] for item in continued_scene["conversation_candidates"]],
        )
        self.assertIn(purpose, continued_context)
        self.assertIn(purpose, continued.json()["narration"])

        door = await post("Marek, burada kapı neden kilitli?")
        self.assertEqual(door.status_code, 200, door.text)
        self.assertNotIn(purpose, door.json()["narration"])
        _, door_context = last_scene()
        self.assertIn(purpose, door_context)

        batches_before_lore = len(client.message_batches)
        lore = await post(
            "Marek, burada Neverwinter neden gizlice bir ejderha tarafından yönetiliyor?"
        )
        self.assertEqual(lore.status_code, 200, lore.text)
        self.assertNotIn(purpose, lore.json()["narration"])
        self.assertTrue(
            any(
                marker in lore.json()["narration"].casefold()
                for marker in ("doğrulanmış", "belirsiz", "kesin konuşamam")
            ),
            lore.json()["narration"],
        )
        self.assertEqual(len(client.message_batches), batches_before_lore)

        other_actor = await post(
            "Marek, kayıp yük kayıtlarını Sera neden yaktı?"
        )
        self.assertEqual(other_actor.status_code, 200, other_actor.text)
        self.assertNotIn(purpose, other_actor.json()["narration"])

        activity_answer = await post("Marek, şu an ne yapıyorsun?")
        self.assertEqual(activity_answer.status_code, 200, activity_answer.text)
        self.assertIn(activity, activity_answer.json()["narration"])
        activity_why = await post("Marek, neden?")
        self.assertEqual(activity_why.status_code, 200, activity_why.text)
        self.assertNotIn(purpose, activity_why.json()["narration"])
        activity_scene, _ = last_scene()
        self.assertEqual(
            activity_scene["conversation_focus"]["predicate"], "current_activity"
        )
        self.assertIn(purpose, json.dumps(activity_scene, ensure_ascii=False))

        for actor_question in (
            "Marek, kervan neden buraya geldi?",
            "Marek, ejderha neden buraya geldi?",
        ):
            with self.subTest(actor_question=actor_question):
                owner_question = await post("Marek, neden buraya geldin?")
                self.assertEqual(owner_question.status_code, 200, owner_question.text)
                self.assertIn(purpose, owner_question.json()["narration"])

                actor_answer = await post(actor_question)
                self.assertEqual(actor_answer.status_code, 200, actor_answer.text)
                self.assertNotIn(purpose, actor_answer.json()["narration"])
                _, actor_context = last_scene()
                self.assertIn(purpose, actor_context)

    async def test_model_owned_personal_purpose_phrasings_do_not_need_lexical_gate(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        purpose = "Arşivde kayıp yük kayıtlarını bulmaya geldim."
        marek = {
            "id": "npc_marek_model_owned_purpose",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": purpose,
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        evidence_id = f"npc-profile:{marek['id']}:v1:reason_for_being_here"
        client.conversation_replies = [
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": "personal_purpose",
                    "topic_relation": "new",
                    "candidate_evidence_ids": [evidence_id],
                }
            },
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": "personal_purpose",
                    "topic_relation": "new",
                    "candidate_evidence_ids": [evidence_id],
                }
            },
        ]

        for message in (
            "Marek, seni bu şehre getiren şey neydi?",
            "Marek, buraya gelişinin sebebi ne?",
        ):
            response = await self.post_scene_turn(
                turn_url,
                client,
                {
                    "message": message,
                    "target_id": marek["id"],
                    "interaction_mode": "say",
                    "action_id": str(uuid.uuid4()),
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn(purpose, response.json()["narration"])
        self.assertEqual(len(client.intent_schemas), 2)
        self.assertEqual(client.conversation_replies, [])

    async def test_free_npc_profile_statement_uses_shared_resolution_without_forced_target(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        purpose = "Arşivde kayıp yük kayıtlarını bulmaya geldim."
        marek = {
            "id": "npc_marek_free_message",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": purpose,
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        client.conversation_replies = [{
            "conversation": {
                "addressee_id": marek["id"],
                "subject_phrase": "Marek",
                "subject_role": "addressee",
                "meaning": "personal_purpose",
                "topic_relation": "new",
                "candidate_evidence_ids": [
                    f"npc-profile:{marek['id']}:v1:reason_for_being_here"
                ],
            }
        }]

        response = await self.post_scene_turn(
            turn_url,
            client,
            {
                "message": "Marek, seni bu şehre getiren şeyi anlat",
                "action_id": str(uuid.uuid4()),
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(purpose, response.json()["narration"])
        focus = session.world_state["interaction_adventure_v1"]["conversation_focus"]
        self.assertEqual(focus["speaker_id"], marek["id"])
        self.assertEqual(focus["predicate"], "reason_for_being_here")

        accepted_focus = copy.deepcopy(focus)
        invalid_replies = [
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "kervan",
                    "subject_role": "other_actor",
                    "meaning": "cause",
                    "topic_relation": "topic_change",
                    "candidate_evidence_ids": [
                        f"npc-profile:{marek['id']}:v1:reason_for_being_here"
                    ],
                },
                "include_narration": True,
                "narration": f"Marek, “{purpose}” diye yanıt verir.",
            },
            {
                "include_conversation": False,
                "include_narration": False,
            },
        ]
        for index, reply in enumerate(invalid_replies):
            with self.subTest(invalid_proposal=index):
                client.conversation_replies = [reply]
                calls_before = client.chat_calls
                rejected = await self.post_scene_turn(
                    turn_url,
                    client,
                    {
                        "message": "Marek, kervanla ilgili ne biliyorsun",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(rejected.status_code, 200, rejected.text)
                self.assertEqual(client.chat_calls, calls_before + 1)
                self.assertNotIn(purpose, rejected.json()["narration"])
                self.assertEqual(
                    session.world_state["interaction_adventure_v1"][
                        "conversation_focus"
                    ],
                    accepted_focus,
                )

        client.conversation_replies = [{
            "conversation": {
                "addressee_id": marek["id"],
                "subject_phrase": "Marek",
                "subject_role": "addressee",
                "meaning": "other",
                "topic_relation": "topic_change",
                "candidate_evidence_ids": [],
            }
        }]
        weather = await self.post_scene_turn(
            turn_url,
            client,
            {
                "message": "Marek, bugün hava nasıl",
                "target_id": marek["id"],
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(weather.status_code, 200, weather.text)
        self.assertNotIn(purpose, weather.json()["narration"])
        self.assertIsNone(
            session.world_state["interaction_adventure_v1"]["conversation_focus"]
        )
        context_marker = (
            "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
        )
        intent_prompt = next(
            item["content"]
            for item in reversed(client.message_batches[-1])
            if context_marker in item.get("content", "")
        )
        current_context, _ = json.JSONDecoder().raw_decode(
            intent_prompt.split(context_marker, 1)[1]
        )
        self.assertIn(
            purpose,
            json.dumps(
                current_context.get("conversation_candidates", []),
                ensure_ascii=False,
            ),
        )

    async def test_short_followup_uses_previous_focus_with_ui_selected_addressee(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        purpose = "Arşivde kayıp yük kayıtlarını bulmaya geldim."
        marek = {
            "id": "npc_marek_ui_addressee",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": purpose,
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        evidence_id = f"npc-profile:{marek['id']}:v1:reason_for_being_here"
        client.conversation_replies = [
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": "personal_purpose",
                    "topic_relation": "new",
                    "candidate_evidence_ids": [evidence_id],
                }
            },
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "",
                    "subject_role": "addressee",
                    "meaning": "personal_purpose",
                    "topic_relation": "followup",
                    "candidate_evidence_ids": [evidence_id],
                }
            },
        ]

        async def ask(message):
            return await self.post_scene_turn(
                turn_url,
                client,
                {
                    "message": message,
                    "target_id": marek["id"],
                    "interaction_mode": "say",
                    "action_id": str(uuid.uuid4()),
                },
            )

        first = await ask("Marek, neden buraya geldin?")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn(purpose, first.json()["narration"])
        followup = await ask("Peki neden?")
        self.assertEqual(followup.status_code, 200, followup.text)
        self.assertIn(purpose, followup.json()["narration"])

    async def test_conversation_proposal_rejection_and_valid_unknown_are_distinct(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        purpose = "Arşivde kayıp yük kayıtlarını bulmaya geldim."
        marek = {
            "id": "npc_marek_terminal_resolution",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": purpose,
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        evidence_id = f"npc-profile:{marek['id']}:v1:reason_for_being_here"

        async def ask(message):
            return await self.post_scene_turn(
                turn_url,
                client,
                {
                    "message": message,
                    "target_id": marek["id"],
                    "interaction_mode": "say",
                    "action_id": str(uuid.uuid4()),
                },
            )

        accepted = await ask("Marek, neden buraya geldin?")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertIn(purpose, accepted.json()["narration"])
        focus_before = copy.deepcopy(
            session.world_state["interaction_adventure_v1"]["conversation_focus"]
        )

        invalid_proposals = [
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "kervan",
                    "subject_role": "other_actor",
                    "meaning": "cause",
                    "topic_relation": "topic_change",
                    "candidate_evidence_ids": [evidence_id],
                },
                "include_narration": True,
            },
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": "current_activity",
                    "topic_relation": "followup",
                    "candidate_evidence_ids": [
                        f"npc-profile:{marek['id']}:v1:current_activity"
                    ],
                },
                "include_narration": True,
            },
            {"include_conversation": False, "include_narration": False},
        ]
        for message, override in zip(
            (
                "Marek, kervan neden geldi?",
                "Marek, şu an ne yapıyorsun?",
                "Marek, bana bunu açıkla.",
            ),
            invalid_proposals,
        ):
            with self.subTest(message=message):
                client.conversation_replies = [override]
                calls_before = client.chat_calls
                response = await ask(message)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(client.chat_calls, calls_before + 1)
                self.assertNotIn(purpose, response.json()["narration"])
                self.assertEqual(
                    session.world_state["interaction_adventure_v1"][
                        "conversation_focus"
                    ],
                    focus_before,
                )

        client.conversation_replies = [{
            "conversation": {
                "addressee_id": marek["id"],
                "subject_phrase": "",
                "subject_role": "unknown",
                "meaning": "unknown",
                "topic_relation": "topic_change",
                "candidate_evidence_ids": [],
            }
        }]
        calls_before = client.chat_calls
        unknown = await ask("Peki ya kervan?")
        self.assertEqual(unknown.status_code, 200, unknown.text)
        self.assertEqual(client.chat_calls, calls_before + 1)
        self.assertNotIn(purpose, unknown.json()["narration"])
        self.assertIsNone(
            session.world_state["interaction_adventure_v1"]["conversation_focus"]
        )

    async def test_npc_occupation_and_origin_share_validated_profile_resolution(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        marek = {
            "id": "npc_marek_occupation_origin",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": "Kayıp yük kayıtlarını bulmaya geldim.",
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        proposals = (
            ("occupation", "occupation", "mesleğin nedir?"),
            ("origin", "origin", "nereli olduğunu anlatır mısın?"),
        )
        client.conversation_replies = [
            {
                "conversation": {
                    "addressee_id": marek["id"],
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": meaning,
                    "topic_relation": "new",
                    "candidate_evidence_ids": [
                        f"npc-profile:{marek['id']}:v1:{field}"
                    ],
                }
            }
            for meaning, field, _ in proposals
        ]
        for meaning, field, message in proposals:
            calls_before = client.chat_calls
            response = await self.post_scene_turn(
                turn_url,
                client,
                {
                    "message": f"Marek, {message}",
                    "target_id": marek["id"],
                    "interaction_mode": "say",
                    "action_id": str(uuid.uuid4()),
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(client.chat_calls, calls_before + 1)
            self.assertIn(marek["personal_profile"][field], response.json()["narration"])
            self.assertEqual(
                session.world_state["interaction_adventure_v1"][
                    "conversation_focus"
                ]["predicate"],
                field,
            )

    async def test_conversation_contract_is_required_at_model_adapter_boundary(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        marek = {
            "id": "npc_marek_adapter_contract",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Kâtip.",
                "current_activity": "Kayıtları düzenliyorum.",
                "mood": "İyiyim.",
                "recent_activity": "",
                "origin": "Kuzeyden.",
                "reason_for_being_here": "Bir işi tamamlamak için geldim.",
                "personal_detail": "",
                "immediate_goal": "",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()

        async def ask(message):
            response = await self.post_scene_turn(
                turn_url,
                client,
                {
                    "message": message,
                    "target_id": marek["id"],
                    "action_id": str(uuid.uuid4()),
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(client.intent_schemas)
            return copy.deepcopy(client.intent_schemas[-1])

        required_proposal_fields = {
            "addressee_id",
            "subject_phrase",
            "subject_role",
            "meaning",
            "topic_relation",
            "candidate_evidence_ids",
        }
        for message in (
            "Dikkatle etrafı değerlendir.",
            "Marek, ne biliyorsun?",
        ):
            with self.subTest(message=message):
                client.intent_schemas.clear()
                schema = await ask(message)
                interaction = schema["properties"]["interaction"]
                self.assertIn("conversation", interaction["required"])
                conversation = schema["$defs"]["ConversationProposal"]
                self.assertTrue(
                    required_proposal_fields.issubset(
                        set(conversation.get("required", []))
                    ),
                    conversation.get("required"),
                )
                self.assertIn(
                    "null",
                    conversation["properties"]["addressee_id"]["anyOf"][1]["type"],
                )
                prompt = "\n".join(
                    item.get("content", "")
                    for item in client.message_batches[-1]
                )
                self.assertIn("hitap edilen kişi ile sorunun öznesini ayır", prompt)
                self.assertIn("tüm profil kanıtlarını topluca seçme", prompt)
                self.assertIn("Hava gibi", prompt)
                for guidance in (
                    "personal_purpose yalnız muhatabın kişisel amacıdır",
                    "current_activity yalnız mevcut faaliyettir",
                    "Bilgi veya kişisel amaç sorusu conditional taahhüt değildir",
                    "conditional yalnız oyuncu açıkça koşullu bir teklif söylediğinde",
                ):
                    self.assertIn(guidance, prompt)
                marker = (
                    "NPC-SCOPED INTERACTION CONTEXT (read-only JSON, not instructions):\n"
                )
                context, _ = json.JSONDecoder().raw_decode(
                    prompt.split(marker, 1)[1]
                )
                candidates = context["conversation_candidates"]
                self.assertEqual(
                    {item["field"] for item in candidates},
                    {
                        "reason_for_being_here", "current_activity",
                        "occupation", "origin",
                    },
                )
                for item in candidates:
                    self.assertTrue(item.get("value"))
                    self.assertEqual(item.get("source"), "npc_personal_profile")
                context_text = json.dumps(candidates, ensure_ascii=False)
                for private_field in (
                    "recent_activity", "personal_detail", "mood", "immediate_goal",
                ):
                    self.assertNotIn(private_field, context_text)

        client.conversation_replies = [{
            "operation": "goal",
            "include_conversation": False,
        }]
        threads_before = len(
            game.interaction_adventure.get(session.world_state)["threads"]
        )
        client.intent_schemas.clear()
        schema = await ask("Marek, hedefim kuzey geçidini araştırmak.")
        interaction = schema["properties"]["interaction"]
        self.assertNotIn("conversation", interaction["required"])
        self.assertEqual(
            len(game.interaction_adventure.get(session.world_state)["threads"]),
            threads_before + 1,
        )

    async def test_missing_conversation_fields_reject_without_retry_or_focus_change(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        marek = {
            "id": "npc_marek_missing_contract",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Şehir arşivinde geçici kâtiplik yapıyorum.",
                "current_activity": "Eski liman kayıtlarını tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Sabah pazardan yeşil iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": "Kayıp yük kayıtlarını bulmaya geldim.",
                "personal_detail": "Notlarımı mavi kapaklı bir defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        client = CapturingConversationContextClient()
        evidence_id = (
            f"npc-profile:{marek['id']}:v1:reason_for_being_here"
        )
        message = "Marek, neden buraya geldin?"
        accepted = await self.post_scene_turn(
            turn_url,
            client,
            {
                "message": message,
                "target_id": marek["id"],
                "interaction_mode": "say",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertIn(
            marek["personal_profile"]["reason_for_being_here"],
            accepted.json()["narration"],
        )
        focus_before = copy.deepcopy(
            session.world_state["interaction_adventure_v1"]["conversation_focus"]
        )
        self.assertEqual(focus_before["evidence_id"], evidence_id)
        valid_conversation = {
            "addressee_id": marek["id"],
            "subject_phrase": "Marek",
            "subject_role": "addressee",
            "meaning": "personal_purpose",
            "topic_relation": "new",
            "candidate_evidence_ids": [evidence_id],
        }
        envelope = {
            "operation": "none",
            "quote": message,
            "conversation": valid_conversation,
        }
        for missing in (
            "addressee_id", "subject_phrase", "subject_role", "meaning",
            "topic_relation", "candidate_evidence_ids",
        ):
            with self.subTest(missing=missing):
                incomplete = copy.deepcopy(envelope)
                incomplete["conversation"].pop(missing)
                self.assertIsNone(
                    game.interaction_adventure.resolve_conversation(
                        session.world_state, message, incomplete, marek
                    )
                )

        profile_evidence_ids = [
            f"npc-profile:{marek['id']}:v1:{field}"
            for field in (
                "reason_for_being_here", "current_activity", "occupation",
                "recent_activity", "origin", "personal_detail", "mood",
            )
        ]
        overbroad = copy.deepcopy(envelope)
        overbroad["conversation"]["candidate_evidence_ids"] = (
            profile_evidence_ids
        )
        self.assertIsNone(
            game.interaction_adventure.resolve_conversation(
                session.world_state, message, overbroad, marek
            )
        )
        malformed_replies = [
            (
                message,
                {
                    "addressee_id": marek["id"],
                    "candidate_evidence_ids": profile_evidence_ids,
                },
            ),
            (
                message,
                {
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": "personal_purpose",
                    "topic_relation": "followup",
                    "candidate_evidence_ids": [evidence_id],
                },
            ),
            (
                "Marek, ne iş yapıyorsun?",
                {
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": "occupation",
                    "topic_relation": "new",
                    "candidate_evidence_ids": [
                        f"npc-profile:{marek['id']}:v1:occupation"
                    ],
                },
            ),
            (
                "Marek, nerelisin?",
                {
                    "subject_phrase": "Marek",
                    "subject_role": "addressee",
                    "meaning": "origin",
                    "topic_relation": "new",
                    "candidate_evidence_ids": [
                        f"npc-profile:{marek['id']}:v1:origin"
                    ],
                },
            ),
        ]
        for index, (raw_message, incomplete) in enumerate(malformed_replies):
            with self.subTest(raw_shape=index):
                client.conversation_replies = [{"conversation": incomplete}]
                calls_before = client.chat_calls
                response = await self.post_scene_turn(
                    turn_url,
                    client,
                    {
                        "message": raw_message,
                        "target_id": marek["id"],
                        "interaction_mode": "say",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(client.chat_calls, calls_before + 1)
                self.assertNotIn(
                    marek["personal_profile"]["reason_for_being_here"],
                    response.json()["narration"],
                )
                self.assertEqual(
                    session.world_state["interaction_adventure_v1"][
                        "conversation_focus"
                    ],
                    focus_before,
                )

    async def test_invalid_conditional_conversation_rejects_before_interaction_effects(self):
        requests = (
            (
                "general",
                "Marek, seni bu şehre getiren şeyi anlat",
                True,
            ),
            (
                "conditional_hint",
                "Yalnızca kapı açılmış olursa sana yardım ederim.",
                True,
            ),
            (
                "required_conversation_missing",
                "Marek, seni bu şehre getiren şeyi anlat",
                False,
            ),
        )
        for path, message, include_conversation in requests:
            with self.subTest(path=path):
                city_id, session_id, session, turn_url, _, _ = (
                    await create_city_with_locked_tavern(self)
                )
                npc_id = "npc_marek_live_pr13"
                evidence_id = (
                    f"npc-profile:{npc_id}:v1:reason_for_being_here"
                )
                profile = {
                    "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                    "occupation": "Şehir arşivinde kâtiplik yapıyorum.",
                    "current_activity": "Eski kayıtları tasnif ediyorum.",
                    "mood": "İyiyim.",
                    "recent_activity": "Sabah pazardan iplik aldım.",
                    "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                    "reason_for_being_here": "Kayıp kayıtları bulmaya geldim.",
                    "personal_detail": "Notlarımı mavi defterde tutarım.",
                    "immediate_goal": "Bugün tasnifi bitirmek.",
                }
                marek = {
                    "id": npc_id,
                    "name": "Marek",
                    "role": "resident",
                    "location": city_id,
                    "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                    "personal_profile": profile,
                    "personality": "",
                    "appearance": "",
                    "relationship": "neutral",
                    "knowledge": [],
                    "memory": [],
                    "combat_status": "active",
                    "current_hp": 12,
                    "status": "active",
                }
                session.world_state.setdefault("npcs", []).append(marek)
                profile_evidence_ids = [
                    f"npc-profile:{npc_id}:v1:{field}"
                    for field in (
                        "reason_for_being_here", "current_activity", "occupation",
                        "recent_activity", "origin", "personal_detail", "mood",
                    )
                ]
                client = CapturingConversationContextClient()
                interaction = {
                    "operation": "conditional",
                    "quote": message,
                    "thread_id": None,
                    "evidence_id": None,
                    "requested_item": None,
                    "steps": [],
                    "candidates": [{
                        "kind": "inquiry",
                        "impact": "local",
                        "npc_id": npc_id,
                        "location_id": city_id,
                        "routes": [{"kind": "talk", "target": npc_id}],
                        "evidence_id": evidence_id,
                    }],
                    "conversation": {
                        "addressee_id": npc_id,
                        "subject_phrase": message,
                        "subject_role": "unknown",
                        "meaning": "unknown",
                        "topic_relation": "unclear",
                        "candidate_evidence_ids": profile_evidence_ids,
                    },
                }
                if not include_conversation:
                    interaction.pop("conversation")
                client.conversation_replies = [{"interaction": interaction}]
                action_id = str(uuid.uuid4())
                body = {
                    "message": message,
                    "target_id": npc_id,
                    "interaction_mode": "say",
                    "action_id": action_id,
                }
                def snapshot():
                    return {
                        "interaction": copy.deepcopy(
                            game.interaction_adventure.get(session.world_state)
                        ),
                        "npc": copy.deepcopy(marek),
                    }

                before = snapshot()
                calls_before = client.chat_calls
                first = await self.post_scene_turn(turn_url, client, body)
                calls_after_first = client.chat_calls
                after_first = snapshot()
                replay = await self.post_scene_turn(turn_url, client, body)
                calls_after_replay = client.chat_calls
                after_replay = snapshot()

                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(replay.status_code, 200, replay.text)
                with self.subTest(path=path, check="one model call then replay"):
                    self.assertEqual(calls_after_first, calls_before + 1)
                    self.assertEqual(calls_after_replay, calls_after_first)
                    self.assertEqual(replay.json(), first.json())
                with self.subTest(path=path, check="no interaction or memory effects"):
                    self.assertEqual(after_first, before)
                    self.assertEqual(after_replay, before)

    async def test_npc_conversation_save_failure_rolls_back_and_receipt_replay_skips_model(self):
        city_id, session_id, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        marek = {
            "id": "npc_marek_atomic_conversation",
            "name": "Marek",
            "role": "resident",
            "location": city_id,
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            "personal_profile": {
                "schema_version": local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,
                "occupation": "Arşiv kâtibiyim.",
                "current_activity": "Eski kayıtları tasnif ediyorum.",
                "mood": "İyiyim.",
                "recent_activity": "Pazardan iplik aldım.",
                "origin": "Kuzeydeki küçük bir yerleşimden geldim.",
                "reason_for_being_here": "Kayıp yük kayıtlarını bulmaya geldim.",
                "personal_detail": "Notlarımı mavi defterde tutarım.",
                "immediate_goal": "Bugün tasnifi bitirmek.",
            },
            "personality": "",
            "appearance": "",
            "relationship": "neutral",
            "knowledge": [],
            "memory": [],
            "combat_status": "active",
            "current_hp": 12,
            "status": "active",
        }
        session.world_state.setdefault("npcs", []).append(marek)
        record = self.manager.get(session_id)
        campaign_id = record.campaign_id
        client = CapturingConversationContextClient()
        purpose_evidence = f"npc-profile:{marek['id']}:v1:reason_for_being_here"
        proposal = {
            "addressee_id": marek["id"],
            "subject_phrase": "Marek",
            "subject_role": "addressee",
            "meaning": "personal_purpose",
            "topic_relation": "new",
            "candidate_evidence_ids": [purpose_evidence],
        }
        client.conversation_replies = [
            {"conversation": copy.deepcopy(proposal)},
            {"conversation": copy.deepcopy(proposal)},
        ]
        action_id = str(uuid.uuid4())
        body = {
            "message": "Marek, neden buraya geldin?",
            "target_id": marek["id"],
            "interaction_mode": "say",
            "action_id": action_id,
        }
        before_state = copy.deepcopy(session.serialize_game_state())
        before_rng = session.rng.getstate()
        before_memory = copy.deepcopy(record.narrative_memory)
        original_save = self.store.save_campaign
        save_calls = 0

        def fail_once(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                raise CampaignStorageError("synthetic save failure")
            return original_save(*args, **kwargs)

        with patch.object(self.store, "save_campaign", side_effect=fail_once):
            failed = await self.post_scene_turn(turn_url, client, body)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(session.serialize_game_state(), before_state)
        self.assertEqual(session.rng.getstate(), before_rng)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertIsNone(
            self.store.get_turn_action(
                campaign_id, action_id, principal=TEST_PLAYER
            )
        )

        retry = await self.post_scene_turn(turn_url, client, body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(client.chat_calls, 2)
        self.assertIn("Kayıp yük kayıtlarını bulmaya geldim.", retry.json()["narration"])
        replay = await self.post_scene_turn(turn_url, client, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(client.chat_calls, 2)

    async def test_death_mode_selection_persists_and_legacy_requests_default_to_normal(self):
        legacy = await self.create_campaign()
        self.assertEqual(legacy["state"]["death_state"]["mode"], "NORMAL")

        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                response = await self.http.post(
                    "/api/game/campaigns",
                    json={"death_mode": mode},
                )
                self.assertEqual(response.status_code, 200, response.text)
                created = response.json()
                self.assertEqual(created["state"]["death_state"]["mode"], mode)

                resumed_manager = SessionManager(
                    campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
                )
                resumed_id, _, _, _, _ = resumed_manager.resume_campaign(
                    created["campaign_id"]
                )
                self.assertEqual(
                    resumed_manager.get(resumed_id)
                    .game_session.world_state["death_state"]["mode"],
                    mode,
                )

    async def test_normal_death_rollback_does_not_rewrite_campaign_metadata(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session

        def rolled_back_turn(_message, **_kwargs):
            return {
                "narration": "Normal modda çatışma öncesi duruma dönüldü.",
                "action_result": {
                    "action": "death_save",
                    "status": "resolved",
                    "success": True,
                    "death_resolution": {
                        "mode": "NORMAL",
                        "outcome": "rolled_back",
                        "cause": "failed_death_saves",
                        "rolled_back": True,
                        "terminal": False,
                    },
                },
            }

        session.run_player_turn = rolled_back_turn
        with (
            patch.object(
                main_module,
                "set_session_world_metadata",
                side_effect=AssertionError("metadata must come from the checkpoint"),
            ),
            patch.object(
                main_module,
                "update_narrative_memory",
                side_effect=AssertionError("rollback turns do not add memories"),
            ),
            patch.object(
                main_module,
                "update_campaign_journal",
                side_effect=AssertionError("rollback turns do not add journal entries"),
            ),
        ):
            response = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "Bekle."},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["combat_result"]["death_resolution"]["outcome"],
            "rolled_back",
        )

    async def test_death_checkpoint_is_json_safe_and_external_restore_is_atomic(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        game._capture_combat_death_checkpoint(session=session)
        self.assertIsNotNone(
            session.world_state["death_state"]["combat_checkpoint"]
        )

        self.manager.save_campaign(created["campaign_id"])
        stored = self.store.get_campaign(created["campaign_id"])
        encoded = json.dumps(
            stored.payload,
            ensure_ascii=False,
            allow_nan=False,
        )
        self.assertTrue(encoded)

        resumed_manager = SessionManager(
            campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        )
        resumed_id, resumed_record, _, _, _ = resumed_manager.resume_campaign(
            created["campaign_id"]
        )
        resumed_session = resumed_record.game_session
        checkpoint = copy.deepcopy(
            resumed_session.world_state["death_state"]["combat_checkpoint"]
        )
        campaign_state = checkpoint["campaign_state"]

        resumed_record.journal = {"marker": "must remain untouched"}
        before_narrative = copy.deepcopy(resumed_record.narrative_memory)
        before_lore = resumed_record.lore_authority.to_dict()
        invalid_checkpoint = copy.deepcopy(checkpoint)
        invalid_checkpoint["campaign_state"]["narrative_memory"] = []
        resumed_session.world_state["death_state"][
            "combat_checkpoint"
        ] = invalid_checkpoint

        with self.assertRaises(CampaignStorageError):
            game._restore_combat_death_checkpoint(
                "massive_damage",
                session=resumed_session,
            )

        self.assertEqual(
            resumed_record.journal,
            {"marker": "must remain untouched"},
        )
        self.assertEqual(resumed_record.narrative_memory, before_narrative)
        self.assertEqual(resumed_record.lore_authority.to_dict(), before_lore)

        resumed_session.world_state["death_state"][
            "combat_checkpoint"
        ] = checkpoint
        result = game._restore_combat_death_checkpoint(
            "massive_damage",
            session=resumed_session,
        )
        self.assertTrue(result["rolled_back"])
        self.assertEqual(resumed_record.journal, campaign_state["journal"])
        self.assertEqual(
            resumed_record.narrative_memory,
            campaign_state["narrative_memory"],
        )
        self.assertEqual(
            resumed_record.lore_authority.to_dict(),
            campaign_state["lore_authority"],
        )
        self.assertEqual(
            resumed_session.world_metadata,
            campaign_state["world_metadata"],
        )

    async def test_turn_action_replays_after_resume_and_rejects_reused_payload(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        calls = []

        def deterministic_turn(_message, **_kwargs):
            calls.append(True)
            return {
                "narration": "Kapıdan hafif bir ses geliyor.",
                "action_result": {
                    "action": "world_interaction",
                    "status": "resolved",
                    "success": True,
                    "state_changes": [],
                },
            }

        session.run_player_turn = deterministic_turn
        action_id = str(uuid.uuid4())
        body = {
            "message": "Kapının arkasından ses dinliyorum.",
            "action_id": action_id,
        }
        first = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json=body,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["action_id"], action_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.store.get_campaign(created["campaign_id"]).history), 1)

        same_session_retry = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json=body,
        )
        self.assertEqual(same_session_retry.status_code, 200, same_session_retry.text)
        self.assertEqual(same_session_retry.json(), first.json())
        self.assertEqual(len(calls), 1)

        reloaded_manager = SessionManager(
            campaign_store=CampaignStore(
                self.store.path,
                bound_principal=TEST_PLAYER,
            )
        )
        resumed_id, _, _, _, _ = reloaded_manager.resume_campaign(
            created["campaign_id"]
        )
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=None,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        ) as reloaded_http:
            after_resume = await reloaded_http.post(
                f"/api/game/sessions/{resumed_id}/turn",
                json=body,
            )
            self.assertEqual(after_resume.status_code, 200, after_resume.text)
            self.assertEqual(after_resume.json()["action_id"], action_id)
            self.assertEqual(after_resume.json()["narration"], first.json()["narration"])
            self.assertEqual(
                after_resume.json()["state"],
                first.json()["state"],
            )

            conflicting = await reloaded_http.post(
                f"/api/game/sessions/{resumed_id}/turn",
                json={**body, "message": "Kapıyı açıyorum."},
            )
            self.assertEqual(conflicting.status_code, 409)
            self.assertEqual(
                conflicting.json()["detail"]["code"],
                "action_id_conflict",
            )
        self.assertEqual(len(self.store.get_campaign(created["campaign_id"]).history), 1)
        self.assertEqual(len(calls), 1)

    def install_test_ambient_event(self, session, event_type="BLUE"):
        world = session.world_state
        if world.get("location") == "Henüz belirlenmedi":
            world["location"] = "tavern"
        location_id = world["location"]
        turn_index = world.get("flags", {}).get("turn_index", 0)
        scene = living_world.ensure_scene_record(
            world,
            location_id,
            turn_index,
        )
        scene["materialized"] = False
        scene["referents"] = []
        scene.pop("ambient_event", None)
        event = {
            "event_id": "city_test_traveler",
            "variation_id": "v1",
            "repeat_group": "test-traveler",
            "event_type": event_type,
            "text": "Bir yolcu kısa süreliğine yakındaki bir kişiye sesleniyor.",
            "aliases": ["yolcu", "gezgin"],
        }
        with patch.object(
            living_world,
            "select_ambient_event",
            return_value=event,
        ):
            scene = living_world.materialize_scene(
                world,
                location_id,
                turn_index,
                create_npc=session.create_npc_from_ai,
                create_feature=session.create_local_feature,
            )
        return scene["ambient_event"]["instance_id"]

    async def test_game_session_bound_turn_uses_engine_signature_fallback(self):
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "Session-bound engine signature regression",
                # This is the release-gate start where city-look is deterministic
                # and must not invoke the fake model adapter.
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": "fr:city:neverwinter",
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        session = self.manager.get(created["session_id"]).game_session
        self.assertIsInstance(session, game.GameSession)

        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Etrafıma bakıyorum."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        turn = response.json()
        self.assertTrue(turn["narration"].strip())
        self.assertIsInstance(turn.get("state"), dict)
        self.assertTrue(turn["state"])

    async def test_city_observation_and_discovery_receipts_survive_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "City observation and discovery receipt regression",
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        session = self.manager.get(created["session_id"]).game_session
        messages = [
            "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "Yakınlarda oturup bir şeyler içebileceğim bir yer var mı?",
            "Buralarda bir tücaar var mı?",
            "Bu kampanya için burada yerel bir dükkân ve tüccar oluştur.",
            "Buralarda bir tücaar var mı?",
        ]
        requests = [
            {"message": message, "action_id": str(uuid.uuid4())}
            for message in messages
        ]
        turns = []
        engine_results = []

        def merchant_state_snapshot(game_session):
            world = game_session.world_state
            scene_state = world.get("scene_state", {})
            return copy.deepcopy({
                "npcs": world.get("npcs", []),
                "shops": world.get("shops", []),
                "locations": world.get("locations", {}),
                "doors": world.get("doors", []),
                "features": world.get("features", []),
                "inventory": world.get("inventory"),
                "currency": world.get("currency"),
                "quests": world.get("quests"),
                "quest_offers": world.get("quest_offers"),
                "item_rewards": world.get("item_rewards"),
                "quest_processed_event_ids": world.get("quest_processed_event_ids"),
                "world_events": world.get("events"),
                "scheduled_events": world.get("scheduled_events"),
                "scene_state": scene_state,
                "rng": game_session.rng.getstate(),
            })

        async def execute_and_replay(
            http,
            session_id,
            game_session,
            body,
            index,
            *,
            expected_action,
            expected_status,
            expected_success=True,
            assert_read_only=False,
        ):
            # Observe the real engine boundary: TurnResponse deliberately exposes
            # narration/state rather than the living-world action_result.
            real_turn = game_session.run_player_turn
            state_before = (
                merchant_state_snapshot(game_session) if assert_read_only else None
            )

            @wraps(real_turn)
            def capture_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                engine_results.append(copy.deepcopy(result["action_result"]))
                return result

            url = f"/api/game/sessions/{session_id}/turn"
            with patch.object(game_session, "run_player_turn", new=capture_turn):
                first = await http.post(url, json=body)
                self.assertEqual(first.status_code, 200, first.text)
                turn = first.json()
                self.assertEqual(turn["action_id"], body["action_id"])
                self.assertTrue(turn["narration"].strip())
                self.assertEqual(turn["state"]["location"], city_id)
                result = engine_results[-1]
                self.assertEqual(result["action"], expected_action)
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["success"], expected_success)
                self.assertTrue(result["direct_response"].strip())
                if assert_read_only:
                    self.assertEqual(result["state_changes"], [])
                    self.assertEqual(
                        merchant_state_snapshot(game_session), state_before
                    )
                before_replay = copy.deepcopy(game_session.serialize_game_state())
                replay = await http.post(url, json=body)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), turn)
                self.assertEqual(game_session.serialize_game_state(), before_replay)
                self.assertEqual(len(engine_results), index + 1)
                self.assertEqual(
                    len(self.store.get_campaign(created["campaign_id"]).history),
                    index + 1,
                )
            turns.append(turn)

        await execute_and_replay(
            self.http,
            created["session_id"],
            session,
            requests[0],
            0,
            expected_action="explore",
            expected_status="observed",
        )
        scene = copy.deepcopy(session.world_state["scene_state"]["scenes"][city_id])
        self.assertEqual(scene["kind"], "city")
        self.assertTrue(scene["materialized"])
        self.assertIn("Neverwinter", turns[0]["narration"])

        # Reopen before discovery as well as after it: no original in-memory
        # scene or manager may be needed to continue this sequence.
        reloaded_manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], turns[0]["state"])
            session_id = resumed.json()["session_id"]
            loaded = reloaded_manager.get(session_id).game_session
            await execute_and_replay(
                http, session_id, loaded, requests[1], 1,
                expected_action="local_search", expected_status="found",
            )
            self.assertEqual(loaded.world_state.get("shops", []), [])
            self.assertFalse(any(
                npc.get("location") == city_id
                and game._is_shopkeeper_role(npc.get("role"))
                for npc in loaded.world_state.get("npcs", [])
                if isinstance(npc, dict)
            ))
            await execute_and_replay(
                http, session_id, loaded, requests[2], 2,
                expected_action="local_search",
                expected_status="unavailable",
                expected_success=False,
                assert_read_only=True,
            )
            await execute_and_replay(
                http, session_id, loaded, requests[3], 3,
                expected_action="shop_setup", expected_status="created",
            )
            created_shop = engine_results[3]["shop_id"]
            created_shopkeeper = engine_results[3]["shopkeeper_id"]
            self.assertEqual(len(loaded.world_state["shops"]), 1)
            self.assertEqual(loaded.world_state["shops"][0]["id"], created_shop)
            self.assertEqual(
                loaded.world_state["shops"][0]["shopkeeper_id"], created_shopkeeper
            )
            await execute_and_replay(
                http, session_id, loaded, requests[4], 4,
                expected_action="local_search", expected_status="found",
            )

        world = loaded.world_state
        tavern_id = engine_results[1]["target_id"]
        tavern = world["locations"][tavern_id]
        self.assertEqual(tavern["scene_kind"], "tavern")
        self.assertEqual(tavern["parent_location_id"], city_id)
        self.assertEqual(tavern["exit_location_id"], city_id)
        self.assertEqual(len(world["shops"]), 1)
        shop = world["shops"][0]
        self.assertEqual(shop["id"], engine_results[4]["shop_id"])
        self.assertEqual(shop["location"], city_id)
        self.assertEqual(shop["shopkeeper_id"], engine_results[4]["target_id"])
        shopkeeper = next(npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"])
        self.assertEqual(shopkeeper["location"], city_id)
        self.assertEqual(world["location"], city_id)
        self.assertEqual(world["scene_state"]["scenes"][city_id], scene)
        saved_state = copy.deepcopy(loaded.serialize_game_state())

        restarted_manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        restarted_app = create_app(
            session_manager=restarted_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], turns[-1]["state"])
            session_id = resumed.json()["session_id"]
            reopened = restarted_manager.get(session_id).game_session
            self.assertEqual(reopened.serialize_game_state(), saved_state)
            with patch.object(
                reopened, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not execute a turn"),
            ):
                for body, original in zip(requests, turns):
                    replay = await http.post(
                        f"/api/game/sessions/{session_id}/turn", json=body
                    )
                    self.assertEqual(replay.status_code, 200, replay.text)
                    # Resume rebinds only session_id; the saved result,
                    # narration, action ID and historical state stay identical.
                    self.assertEqual(
                        replay.json(), {**original, "session_id": session_id}
                    )
                    self.assertEqual(reopened.serialize_game_state(), saved_state)
            self.assertEqual(
                len(self.store.get_campaign(created["campaign_id"]).history),
                len(requests),
            )

    async def test_failed_tavern_discovery_is_rolled_back_and_retry_commits_once(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        url = f"/api/game/sessions/{created['session_id']}/turn"
        materialization_body = {
            "message": "Etrafıma bakıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        materialized = await self.http.post(url, json=materialization_body)
        self.assertEqual(materialized.status_code, 200, materialized.text)
        self.assertEqual(materialized.json()["state"]["location"], city_id)
        self.assertTrue(
            session.world_state["scene_state"]["scenes"][city_id]["materialized"]
        )
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        observation_results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_observation(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            observation_results.append(copy.deepcopy(result["action_result"]))
            return result

        # Preserve a committed turn, not merely the campaign's empty baseline.
        with patch.object(session, "run_player_turn", new=capture_observation):
            observed = await self.http.post(url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(observed.json()["action_id"], observation_body["action_id"])
        self.assertEqual(len(observation_results), 1)
        self.assertEqual(observation_results[0]["action"], "explore")
        self.assertEqual(observation_results[0]["status"], "observed")
        self.assertTrue(observation_results[0]["success"])
        self.assertEqual(observation_results[0]["state_changes"], [])
        self.assertNotEqual(observed.json()["state"], created["state"])
        self.assertTrue(record.journal["notable_events"])
        self.assertIn(
            city_id,
            [entry["location_id"] for entry in record.journal["discovered_locations"]],
        )
        observation_receipt = copy.deepcopy(
            self.manager.get_turn_action(record, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        before_save = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        before_memory = copy.deepcopy(record.narrative_memory)
        before_receipts = copy.deepcopy(record.turn_action_receipts)
        before_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(before_save["world_state"]["location"], city_id)
        self.assertFalse(any(
            location.get("scene_kind") == "tavern"
            for location in session.world_state["locations"].values()
        ))
        self.assertTrue(
            before_save["world_state"]["scene_state"]["scenes"][city_id]["materialized"]
        )
        self.assertEqual(len(before_campaign.history), 2)
        self.assertEqual(
            before_campaign.history[0]["player_message"],
            materialization_body["message"],
        )
        self.assertEqual(
            before_campaign.history[1]["player_message"], observation_body["message"]
        )
        self.assertEqual(before_campaign.payload["engine_save"], before_save)
        self.assertEqual(before_campaign.payload["journal"], before_journal)
        results = []
        attempted_saves = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            attempted_saves.append(copy.deepcopy(session.serialize_game_state()))
            return result

        # Observe a genuine offline discovery, failing only its persistence.
        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(
                self.store,
                "save_campaign",
                side_effect=CampaignStorageError("database unavailable"),
            ) as failed_save,
        ):
            failed = await self.http.post(url, json=body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertNotIn("database unavailable", failed.text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "local_search")
        self.assertEqual(results[0]["status"], "found")
        self.assertTrue(results[0]["success"])
        uncommitted_id = results[0]["target_id"]
        self.assertNotIn(uncommitted_id, before_save["world_state"]["locations"])
        self.assertEqual(
            attempted_saves[0]["world_state"]["locations"][uncommitted_id][
                "scene_kind"
            ],
            "tavern",
        )
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertNotIn(uncommitted_id, session.world_state["locations"])
        self.assertEqual(record.journal, before_journal)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertEqual(record.turn_action_receipts, before_receipts)
        self.assertEqual(
            self.manager.get_turn_action(record, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertNotIn(body["action_id"], record.turn_action_receipts)
        self.assertIsNone(self.manager.get_turn_action(record, body["action_id"]))
        failed_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(failed_campaign, before_campaign)
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(self.store.get_turn_action(campaign_id, body["action_id"]))

        # A new manager must retain the observation without any unsaved venue,
        # scene changes, journal entries, history, or failed discovery receipt.
        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"], observed.json()["state"])
        self.assertEqual(resumed.json()["history"], before_campaign.history)
        reopened_record = reopened_manager.get(resumed.json()["session_id"])
        self.assertEqual(
            reopened_record.game_session.serialize_game_state(), before_save
        )
        self.assertEqual(reopened_record.journal, before_journal)
        self.assertEqual(reopened_record.narrative_memory, before_memory)
        self.assertEqual(reopened_record.turn_action_receipts, before_receipts)
        self.assertEqual(
            reopened_manager.get_turn_action(
                reopened_record, observation_body["action_id"]
            ),
            observation_receipt,
        )
        self.assertNotIn(
            uncommitted_id, reopened_record.game_session.world_state["locations"]
        )
        self.assertNotIn(body["action_id"], reopened_record.turn_action_receipts)
        self.assertIsNone(
            reopened_manager.get_turn_action(reopened_record, body["action_id"])
        )
        reopened_campaign = reopened_store.get_campaign(campaign_id)
        # Resume may refresh metadata timestamps, but not saved gameplay.
        self.assertEqual(reopened_campaign.payload, before_campaign.payload)
        self.assertEqual(reopened_campaign.history, before_campaign.history)
        self.assertEqual(reopened_campaign.combat_history, before_campaign.combat_history)
        self.assertEqual(
            reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(
            reopened_store.get_turn_action(campaign_id, body["action_id"])
        )

        # Recover storage and retry the identical action on the live session.
        with patch.object(session, "run_player_turn", new=capture_turn):
            retry = await self.http.post(url, json=body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["action_id"], body["action_id"])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        tavern_id = results[-1]["target_id"]
        taverns = [
            location
            for location in session.world_state["locations"].values()
            if location.get("scene_kind") == "tavern"
        ]
        self.assertEqual(len(taverns), 1)
        self.assertEqual(taverns[0], session.world_state["locations"][tavern_id])
        self.assertEqual(taverns[0]["parent_location_id"], city_id)
        self.assertEqual(taverns[0]["exit_location_id"], city_id)
        self.assertEqual(retry.json()["state"]["location"], city_id)
        committed_save = copy.deepcopy(session.serialize_game_state())
        committed_journal = copy.deepcopy(record.journal)
        committed_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
        self.assertEqual(committed_campaign.payload["journal"], committed_journal)
        self.assertEqual(len(committed_campaign.history), 3)
        self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
        self.assertEqual(
            self.manager.get_turn_action(record, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertEqual(
            self.manager.get_turn_action(record, body["action_id"])["response"],
            retry.json(),
        )
        self.assertEqual(
            self.store.get_turn_action(campaign_id, body["action_id"])["response"],
            retry.json(),
        )
        with patch.object(
            session,
            "run_player_turn",
            side_effect=AssertionError("Discovery replay must not execute a turn"),
        ):
            replay = await self.http.post(url, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(session.serialize_game_state(), committed_save)
        self.assertEqual(record.journal, committed_journal)
        self.assertEqual(self.store.get_campaign(campaign_id), committed_campaign)

    async def test_failed_tavern_discovery_retries_once_from_a_fresh_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        turn_url = f"/api/game/sessions/{created['session_id']}/turn"
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            observed = await self.http.post(turn_url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(results[0]["action"], "explore")
        self.assertEqual(results[0]["status"], "observed")
        self.assertTrue(results[0]["success"])
        observation_receipt = copy.deepcopy(
            self.store.get_turn_action(campaign_id, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        before_save = copy.deepcopy(session.serialize_game_state())
        before_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(len(before_campaign.history), 1)
        self.assertEqual(
            before_campaign.history[0]["player_message"], observation_body["message"]
        )
        self.assertEqual(before_save["world_state"]["location"], city_id)
        self.assertFalse(any(
            location.get("scene_kind") == "tavern"
            for location in before_save["world_state"]["locations"].values()
        ))
        discovery_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(
                self.store, "save_campaign",
                side_effect=CampaignStorageError("database unavailable"),
            ) as failed_save,
        ):
            failed = await self.http.post(turn_url, json=discovery_body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        uncommitted_id = results[-1]["target_id"]
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)
        self.assertIsNone(
            self.store.get_turn_action(campaign_id, discovery_body["action_id"])
        )

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], observed.json()["state"])
            self.assertEqual(resumed.json()["history"], before_campaign.history)
            resumed_record = reopened_manager.get(resumed.json()["session_id"])
            resumed_session = resumed_record.game_session
            self.assertIsNot(resumed_session, session)
            self.assertEqual(resumed_session.serialize_game_state(), before_save)
            self.assertEqual(resumed_record.journal, before_campaign.payload["journal"])
            self.assertNotIn(uncommitted_id, resumed_session.world_state["locations"])
            self.assertIsNone(
                reopened_manager.get_turn_action(
                    resumed_record, discovery_body["action_id"]
                )
            )
            self.assertEqual(
                reopened_manager.get_turn_action(
                    resumed_record, observation_body["action_id"]
                ),
                observation_receipt,
            )
            resumed_url = f"/api/game/sessions/{resumed.json()['session_id']}/turn"
            resumed_real_turn = resumed_session.run_player_turn
            retry_results = []

            @wraps(resumed_real_turn)
            def capture_retry(*args, **kwargs):
                result = resumed_real_turn(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            with (
                patch.object(
                    session, "run_player_turn",
                    side_effect=AssertionError("Retry must use the resumed session"),
                ) as original_turn,
                patch.object(
                    resumed_session, "run_player_turn", new=capture_retry,
                ),
                patch.object(
                    reopened_store, "save_campaign", wraps=reopened_store.save_campaign
                ) as retry_save,
            ):
                retry = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            original_turn.assert_not_called()
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "local_search")
            self.assertEqual(retry_results[0]["status"], "found")
            self.assertTrue(retry_results[0]["success"])
            retry_save.assert_called_once()
            self.assertEqual(retry.json()["action_id"], discovery_body["action_id"])
            taverns = [
                location
                for location in resumed_session.world_state["locations"].values()
                if location.get("scene_kind") == "tavern"
            ]
            self.assertEqual(len(taverns), 1)
            self.assertEqual(
                taverns[0],
                resumed_session.world_state["locations"][retry_results[0]["target_id"]],
            )
            self.assertEqual(taverns[0]["parent_location_id"], city_id)
            self.assertEqual(taverns[0]["exit_location_id"], city_id)
            self.assertEqual(retry.json()["state"]["location"], city_id)
            committed_save = copy.deepcopy(resumed_session.serialize_game_state())
            committed_campaign = reopened_store.get_campaign(campaign_id)
            self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
            self.assertEqual(
                committed_campaign.payload["journal"], resumed_record.journal
            )
            self.assertEqual(
                len(committed_campaign.history), len(before_campaign.history) + 1
            )
            self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
            self.assertEqual(
                committed_campaign.history[-1]["player_message"],
                discovery_body["message"],
            )
            for manager, receipt_record in (
                (self.manager, record), (reopened_manager, resumed_record)
            ):
                self.assertEqual(
                    manager.get_turn_action(
                        receipt_record, observation_body["action_id"]
                    ),
                    observation_receipt,
                )
            self.assertEqual(
                reopened_store.get_turn_action(
                    campaign_id, observation_body["action_id"]
                ),
                observation_receipt,
            )
            discovery_receipt = copy.deepcopy(
                reopened_manager.get_turn_action(
                    resumed_record, discovery_body["action_id"]
                )
            )
            self.assertEqual(discovery_receipt["response"], retry.json())
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )
            with (
                patch.object(
                    resumed_session, "run_player_turn",
                    side_effect=AssertionError("Replay must not execute another turn"),
                ) as replay_turn,
                patch.object(
                    reopened_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save again"),
                ) as replay_save,
            ):
                replay = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(resumed_session.serialize_game_state(), committed_save)
            self.assertEqual(
                resumed_record.journal, committed_campaign.payload["journal"]
            )
            self.assertEqual(reopened_store.get_campaign(campaign_id), committed_campaign)
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
                observation_receipt,
            )
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )

    async def test_reopened_declined_tavern_search_preserves_entities_and_history(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        discovery_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        real_discovery = original_session.run_player_turn
        discovery_results = []

        @wraps(real_discovery)
        def capture_discovery(*args, **kwargs):
            result = real_discovery(*args, **kwargs)
            discovery_results.append(copy.deepcopy(result["action_result"]))
            return result

        with patch.object(original_session, "run_player_turn", new=capture_discovery):
            discovered = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json=discovery_body,
            )
        self.assertEqual(discovered.status_code, 200, discovered.text)
        self.assertEqual(len(discovery_results), 1)
        self.assertEqual(discovery_results[0]["action"], "local_search")
        self.assertEqual(discovery_results[0]["status"], "found")
        self.assertTrue(discovery_results[0]["success"])
        tavern_id = discovery_results[0]["target_id"]
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["locations"][tavern_id]["scene_kind"], "tavern")
        self.assertEqual(
            saved_world["locations"][tavern_id]["parent_location_id"], city_id
        )

        non_search_narration = "Şehrin sokaklarından gelen sesler sürüyor."

        class DeclinedTavernOllamaClient(FakeOllamaClient):
            def chat(self, *args, **kwargs):
                # Script only the model boundary, never the real turn or save.
                if "intent" in kwargs["format"]["properties"]:
                    packet = {
                        "intent": "narrative",
                        "action": "decline_search",
                        "target": {"type": "none", "reference": ""},
                        "completion": "completed",
                        "confidence": 1.0,
                    }
                else:
                    packet = {
                        "narration": non_search_narration,
                        "world_updates": {},
                        "lore_claims": [],
                    }
                return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(DeclinedTavernOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        declined_body = {
            # The supported negative suffix used by the living-world regression
            # also bypasses game.py's is_tavern_search gate.
            "message": "Bir taverna aramıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        self.assertNotEqual(declined_body["action_id"], discovery_body["action_id"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            session = reopened_manager.get(session_id).game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, declined_body["action_id"])
            )
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_declined_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_declined_turn):
                declined = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=declined_body
                )
            self.assertEqual(declined.status_code, 200, declined.text)
            self.assertEqual(declined.json()["action_id"], declined_body["action_id"])
            self.assertEqual(len(results), 1)
            action = results[0]["action_result"]
            self.assertEqual(action["action"], "narrative")
            self.assertEqual(action["status"], "resolved")
            self.assertTrue(action["success"])
            self.assertEqual(action["state_changes"], [])
            self.assertNotIn("target_id", action)
            self.assertEqual(results[0]["narration"], non_search_narration)
            self.assertEqual(declined.json()["narration"], non_search_narration)
            self.assertNotEqual(declined.json()["narration"], discovered.json()["narration"])

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], session.serialize_game_state())
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(set(world["locations"]), set(saved_world["locations"]))
            self.assertEqual(
                {npc["id"] for npc in world["npcs"]},
                {npc["id"] for npc in saved_world["npcs"]},
            )
            self.assertEqual(world["locations"][tavern_id], saved_world["locations"][tavern_id])
            self.assertEqual(
                world["flags"]["turn_index"], saved_world["flags"]["turn_index"] + 1
            )
            self.assertEqual(len(persisted.history), len(committed.history) + 1)
            self.assertEqual(persisted.history[:-1], committed.history)
            self.assertEqual(persisted.history[-1]["player_message"], declined_body["message"])
            self.assertEqual(persisted.history[-1]["narration"], non_search_narration)

        # Reload the new non-search turn, without issuing any receipt replay.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            reloaded = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        final_session = final_manager.get(reloaded.json()["session_id"]).game_session
        self.assertIsNot(final_session, session)
        self.assertEqual(final_session.serialize_game_state(), persisted.payload["engine_save"])
        self.assertEqual(reloaded.json()["state"], declined.json()["state"])
        self.assertEqual(reloaded.json()["history"], persisted.history)
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)

    async def test_reopened_tavern_distance_question_preserves_entities_and_history(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        turn_url = f"/api/game/sessions/{created['session_id']}/turn"
        discovery_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        real_discovery = original_session.run_player_turn
        discovery_results = []

        @wraps(real_discovery)
        def capture_discovery(*args, **kwargs):
            result = real_discovery(*args, **kwargs)
            discovery_results.append(copy.deepcopy(result["action_result"]))
            return result

        with patch.object(original_session, "run_player_turn", new=capture_discovery):
            discovered = await self.http.post(turn_url, json=discovery_body)
        self.assertEqual(discovered.status_code, 200, discovered.text)
        self.assertEqual(len(discovery_results), 1)
        self.assertEqual(discovery_results[0]["action"], "local_search")
        self.assertEqual(discovery_results[0]["status"], "found")
        self.assertTrue(discovery_results[0]["success"])
        tavern_id = discovery_results[0]["target_id"]
        unlock_venue_door(original_session.world_state, tavern_id)
        entered = await self.http.post(
            turn_url,
            json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(entered.status_code, 200, entered.text)
        self.assertEqual(entered.json()["state"]["location"], tavern_id)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["locations"][tavern_id]["scene_kind"], "tavern")
        self.assertEqual(saved_world["locations"][tavern_id]["parent_location_id"], city_id)

        # Use the supported route-distance wording, not a declined search.
        question_body = {
            "message": "Taverna ile Kale arasındaki yol mesafesi kaç kilometre?",
            "action_id": str(uuid.uuid4()),
        }
        self.assertNotEqual(question_body["action_id"], discovery_body["action_id"])
        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            # This question is deterministic; unexpected model calls fail offline.
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            session = reopened_manager.get(session_id).game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, question_body["action_id"])
            )
            before = copy.deepcopy(session.world_state)
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_question_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_question_turn):
                question = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=question_body
                )
            self.assertEqual(question.status_code, 200, question.text)
            self.assertEqual(question.json()["action_id"], question_body["action_id"])
            self.assertEqual(len(results), 1)  # A fresh turn, not a receipt replay.
            action = results[0]["action_result"]
            self.assertFalse(action.get("action") == "local_search" and action.get("success"))
            self.assertEqual(action["status"], "unverified")
            narration = results[0]["narration"]
            self.assertIn("ölçüm kaydı yok", narration)
            self.assertEqual(question.json()["narration"], narration)
            self.assertNotEqual(narration, discovered.json()["narration"])

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], session.serialize_game_state())
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], tavern_id)
            self.assertEqual(set(world["locations"]), set(saved_world["locations"]))
            self.assertEqual(
                {npc["id"] for npc in world["npcs"]},
                {npc["id"] for npc in saved_world["npcs"]},
            )
            # Keep discovered entities unchanged. HTTP turn metadata can refresh
            # scene environment fields independently of the lore-query owner.
            for key in (
                "location", "locations", "npcs", "shops", "features", "doors",
                "containers", "quests", "quest_offers", "inventory",
            ):
                self.assertEqual(session.world_state.get(key), before.get(key), key)
                self.assertEqual(world.get(key), saved_world.get(key), key)
            self.assertEqual(len(persisted.history), len(committed.history) + 1)
            self.assertEqual(persisted.history[:-1], committed.history)
            self.assertEqual(persisted.history[-1]["player_message"], question_body["message"])
            self.assertEqual(persisted.history[-1]["narration"], narration)
            question_receipt = reopened_store.get_turn_action(
                campaign_id, question_body["action_id"]
            )
            self.assertEqual(question_receipt["response"], question.json())

        # Reload the accepted question without reissuing its action ID.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            reloaded = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        final_session = final_manager.get(reloaded.json()["session_id"]).game_session
        self.assertIsNot(final_session, session)
        self.assertEqual(final_session.serialize_game_state(), persisted.payload["engine_save"])
        self.assertEqual(reloaded.json()["state"], question.json()["state"])
        self.assertEqual(reloaded.json()["history"], persisted.history)
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
        self.assertEqual(
            final_store.get_turn_action(campaign_id, question_body["action_id"]),
            question_receipt,
        )

    async def test_locked_venue_blocks_timed_travel_by_location_id(self):
        city_id = "fr:city:neverwinter"
        created = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session
        turn_url = f"/api/game/sessions/{session_id}/turn"
        discovered = await self.http.post(
            turn_url,
            json={
                "message": "Yakınlarda bir taverna arıyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(discovered.status_code, 200, discovered.text)
        venues = [
            (identity, location)
            for identity, location in session.world_state["locations"].items()
            if isinstance(location, dict)
            and location.get("scene_kind") == "tavern"
            and location.get("parent_location_id") == city_id
        ]
        self.assertEqual(len(venues), 1)
        venue_id, venue = venues[0]
        door_id = f"venue-door:{venue_id}"
        door = next(item for item in session.world_state["doors"] if item.get("id") == door_id)
        self.assertTrue(door["locked"])
        self.assertFalse(door["open"])
        elapsed_before = session.world_state["campaign_time"]["elapsed_seconds"]

        action_results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            action_results.append(copy.deepcopy(result["action_result"]))
            return result

        travel_body = {
            "message": f"{venue_id} konumuna gidiyorum.",
            "action_id": str(uuid.uuid4()),
        }
        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch("timed_gameplay.travel_dice", return_value=(None, {})),
        ):
            response = await self.http.post(
                turn_url,
                json=travel_body,
            )
            repeated = await self.http.post(turn_url, json=travel_body)
            named = await self.http.post(
                turn_url,
                json={
                    "message": f"{venue['name']} konumuna gidiyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json(), response.json())
        self.assertEqual(named.status_code, 200, named.text)
        self.assertEqual(action_results[-1]["action"], "travel")
        self.assertEqual(action_results[-1]["status"], "blocked")
        self.assertFalse(action_results[-1]["success"])
        self.assertEqual(action_results[-2]["status"], "blocked")
        self.assertEqual(session.world_state["location"], city_id)
        self.assertEqual(
            session.world_state["campaign_time"]["elapsed_seconds"],
            elapsed_before,
        )
        self.assertEqual(response.json()["state"]["location"], city_id)

        before_journey = {
            "origin": city_id,
            "destination": venue_id,
            "stages": [300],
            "stage_index": 0,
            "stage_spent_seconds": 150,
            "stage_checked": True,
            "status": "INTERRUPTED",
            "encounter": None,
            "recent_patterns": [],
        }
        session.world_state["journey"] = copy.deepcopy(before_journey)
        journey_snapshot = copy.deepcopy(session.world_state["journey"])
        elapsed_before_continue = session.world_state["campaign_time"]["elapsed_seconds"]
        first_continue = timed_gameplay.continue_travel(session)
        after_first_continue = copy.deepcopy(session.world_state)
        second_continue = timed_gameplay.continue_travel(session)
        self.assertEqual(first_continue["status"], "blocked")
        self.assertEqual(second_continue["status"], "blocked")
        self.assertEqual(session.world_state["journey"], journey_snapshot)
        self.assertEqual(session.world_state["location"], city_id)
        self.assertEqual(
            session.world_state["campaign_time"]["elapsed_seconds"],
            elapsed_before_continue,
        )
        self.assertEqual(after_first_continue, session.world_state)

    async def test_venue_door_opening_direct_entry_and_exit(self):
        city_id, session_id, session, turn_url, venue_id, door = (
            await create_city_with_locked_tavern(self)
        )
        results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            blocked = await self.http.post(
                turn_url,
                json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(blocked.status_code, 200, blocked.text)
            self.assertEqual(results[-1]["status"], "blocked")
            self.assertEqual(blocked.json()["state"]["location"], city_id)

            # The test opens a known door without introducing a lock-picking rule.
            door["locked"] = False
            with patch.object(
                self.app.state.ollama_adapter,
                "_client",
                ControlledVenueOllamaClient(intent="narrative"),
            ):
                opened = await self.http.post(
                    turn_url,
                    json={"message": "Kapıyı açıyorum.", "action_id": str(uuid.uuid4())},
                )
            self.assertEqual(opened.status_code, 200, opened.text)
            self.assertTrue(door["open"])
            self.assertEqual(opened.json()["state"]["location"], city_id)

            entered = await self.http.post(
                turn_url,
                json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(entered.status_code, 200, entered.text)
            self.assertEqual(results[-1]["status"], "completed")
            self.assertEqual(entered.json()["state"]["location"], venue_id)

            exited = await self.http.post(
                turn_url,
                json={
                    "message": "Tavernadan dışarı çıkıyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
            self.assertEqual(exited.status_code, 200, exited.text)
            self.assertEqual(exited.json()["state"]["location"], city_id)

    async def test_exact_dynamic_venue_door_break_uses_authoritative_handler(self):
        city_id, session_id, session, turn_url, venue_id, door = (
            await create_city_with_locked_tavern(self)
        )
        venue = session.world_state["locations"][venue_id]
        venue["name"] = "Kael Hanı"
        door.update({
            "name": "Kael Hanı Kapısı",
            "description": "Kael Hanı sokağa açılan kapısı",
            "open": False,
            "locked": True,
            "broken": False,
        })
        results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        body = {
            "message": "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum.",
            "action_id": str(uuid.uuid4()),
        }
        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await self.http.post(turn_url, json=body)
            replay = await self.http.post(turn_url, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["action"], "skill_check")
        self.assertEqual(result["skill"], "Athletics")
        self.assertEqual(result["dc"], 15)
        self.assertEqual(result["success"], result["outcome"] == "success")
        self.assertEqual(session.world_state["location"], city_id)
        self.assertEqual(door["id"], f"venue-door:{venue_id}")
        managed = self.manager.get(session_id)
        self.assertEqual(
            self.manager.get_turn_action(managed, body["action_id"])["response"],
            response.json(),
        )
        reopened = SessionManager(
            campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        )
        resumed_id, resumed_record, *_ = reopened.resume_campaign(
            managed.campaign_id, principal=TEST_PLAYER
        )
        self.assertIsNotNone(resumed_id)
        resumed_door = next(
            item for item in resumed_record.game_session.world_state["doors"]
            if item.get("id") == f"venue-door:{venue_id}"
        )
        self.assertEqual(resumed_door["broken"], door["broken"])
        self.assertEqual(resumed_door["open"], door["open"])
        self.assertEqual(resumed_door["locked"], door["locked"])

    async def test_targetless_entry_reuses_failed_door_target_through_http(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            city_id, session_id, session, turn_url, venue_id, door = (
                await create_city_with_locked_tavern(self)
            )
            session.world_state["locations"][venue_id]["name"] = "Kael Hanı"
            door.update({
                "name": "Kael Hanı Kapısı",
                "description": "Kael Hanı sokağa açılan kapısı",
                "open": False,
                "locked": True,
                "broken": False,
            })
            engine_results = []
            entry_plans = []
            real_turn = session.run_player_turn
            real_plan = session.plan_living_world_turn

            @wraps(real_turn)
            def capture_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                engine_results.append(copy.deepcopy(result["action_result"]))
                return result

            @wraps(real_plan)
            def capture_plan(*args, **kwargs):
                result = real_plan(*args, **kwargs)
                message = args[0] if args else kwargs.get("player_input")
                if message == "İçeri giriyorum.":
                    entry_plans.append(copy.deepcopy(result))
                return result

            before_enter = None
            with (
                patch("game.roll_d20", return_value=8) as roll,
                patch.object(
                    self.app.state.ollama_adapter,
                    "_client",
                    ControlledVenueOllamaClient(intent="narrative"),
                ),
                patch.object(session, "run_player_turn", new=capture_turn),
                patch.object(session, "plan_living_world_turn", new=capture_plan),
            ):
                break_body = {
                    "message": "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum.",
                    "action_id": str(uuid.uuid4()),
                }
                failed_break = await self.http.post(
                    turn_url,
                    json=break_body,
                )
                self.assertEqual(failed_break.status_code, 200, failed_break.text)
                self.assertEqual(engine_results[-1]["action"], "skill_check")
                self.assertEqual(engine_results[-1]["skill"], "Athletics")
                self.assertEqual(engine_results[-1]["dc"], 15)
                self.assertFalse(engine_results[-1]["success"])
                roll.assert_called_once()
                self.assertIsInstance(
                    session.world_state.get("scene_state", {}).get(
                        "entry_target_reference"
                    ),
                    dict,
                    "The failed, engine-resolved door action should bind a target.",
                )
                saved_reference = copy.deepcopy(
                    session.world_state["scene_state"]["entry_target_reference"]
                )
                self.assertEqual(saved_reference["location_id"], venue_id)
                self.assertEqual(saved_reference["source_kind"], "door_skill_check")
                self.assertEqual(saved_reference["source_location_id"], city_id)
                self.assertTrue(saved_reference["source_action_id"])
                self.assertEqual(
                    saved_reference["expires_after_turn_index"],
                    saved_reference["source_turn_index"] + 1,
                )
                replay = await self.http.post(turn_url, json=break_body)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), failed_break.json())
                self.assertEqual(len(engine_results), 1)
                self.assertEqual(
                    session.world_state["scene_state"]["entry_target_reference"],
                    saved_reference,
                )
                campaign_id = self.manager.get(
                    session_id
                ).campaign_id
                reopened = SessionManager(
                    campaign_store=CampaignStore(
                        self.store.path, bound_principal=TEST_PLAYER
                    )
                )
                resumed_id, resumed_record, *_ = reopened.resume_campaign(
                    campaign_id, principal=TEST_PLAYER
                )
                self.assertIsNotNone(resumed_id)
                self.assertEqual(
                    resumed_record.game_session.world_state["scene_state"][
                        "entry_target_reference"
                    ],
                    saved_reference,
                )

                before_enter = {
                    "location": session.world_state["location"],
                    "door": copy.deepcopy(door),
                    "rng": session.rng.getstate(),
                    "clock": copy.deepcopy(session.world_state.get("campaign_time")),
                    "inventory": copy.deepcopy(session.world_state.get("inventory")),
                    "entity_ids": {
                        key: tuple(sorted(
                            str(item.get("id"))
                            for item in session.world_state.get(key, [])
                            if isinstance(item, dict) and item.get("id") is not None
                        ))
                        for key in ("npcs", "features", "shops", "doors")
                    },
                    "locations": tuple(sorted(session.world_state.get("locations", {}))),
                }
                entered = await self.http.post(
                    turn_url,
                    json={
                        "message": "İçeri giriyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )

            self.assertEqual(entered.status_code, 200, entered.text)
            self.assertEqual(len(entry_plans), 1)
            direct = entry_plans[0].get("direct_result")
            self.assertIsInstance(direct, dict)
            self.assertEqual(direct.get("action"), "enter")
            self.assertEqual(direct.get("status"), "blocked")
            self.assertIs(direct.get("success"), False)
            self.assertEqual(direct.get("target_id"), venue_id)
            self.assertEqual(session.world_state["location"], city_id)
            self.assertEqual(session.world_state["location"], before_enter["location"])
            self.assertEqual(door, before_enter["door"])
            self.assertEqual(session.rng.getstate(), before_enter["rng"])
            self.assertEqual(
                session.world_state.get("campaign_time"), before_enter["clock"]
            )
            self.assertEqual(
                session.world_state.get("inventory"), before_enter["inventory"]
            )
            self.assertEqual(
                {
                    key: tuple(sorted(
                        str(item.get("id"))
                        for item in session.world_state.get(key, [])
                        if isinstance(item, dict) and item.get("id") is not None
                    ))
                    for key in ("npcs", "features", "shops", "doors")
                },
                before_enter["entity_ids"],
            )
            self.assertEqual(
                tuple(sorted(session.world_state.get("locations", {}))),
                before_enter["locations"],
            )
            narration = entered.json().get("narration", "").casefold()
            self.assertTrue(
                ("kael hanı" in narration or "kael hanı kapısı" in narration)
                and ("kilit" in narration or "kapalı" in narration),
                narration,
            )

    async def test_negative_and_conditional_entry_cannot_reuse_target_over_http(self):
        for message in ("İçeri girmiyorum.", "Eğer kapı açıksa içeri giriyorum."):
            with self.subTest(message=message), patch(
                "socket.socket.connect",
                side_effect=AssertionError("External network is disabled in this API test."),
            ):
                city_id, _, session, turn_url, venue_id, door = (
                    await create_city_with_locked_tavern(self)
                )
                venue = session.world_state["locations"][venue_id]
                venue.update({"name": "Kuzey Atölyesi", "scene_kind": "workshop"})
                door.update({
                    "name": "Kuzey Atölyesi Kapısı",
                    "open": False,
                    "locked": True,
                    "broken": False,
                })
                with (
                    patch("game.roll_d20", return_value=8),
                    patch.object(
                        self.app.state.ollama_adapter,
                        "_client",
                        ControlledVenueOllamaClient(intent="narrative"),
                    ),
                ):
                    failed = await self.http.post(
                        turn_url,
                        json={
                            "message": "Kuzey Atölyesi Kapısını omzumla zorlayarak kırmayı deniyorum.",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                    self.assertEqual(failed.status_code, 200, failed.text)
                    self.assertEqual(
                        session.world_state["scene_state"]["entry_target_reference"][
                            "location_id"
                        ],
                        venue_id,
                    )
                    door.update({"open": True, "locked": False})
                    response = await self.http.post(
                        turn_url,
                        json={"message": message, "action_id": str(uuid.uuid4())},
                    )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    session.world_state["location"],
                    city_id,
                    f"{message!r} must not authorize movement.",
                )

    async def test_door_provenance_comes_from_exact_resolved_door_owner(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            city_id, _, session, turn_url, first_id, first_door = (
                await create_city_with_locked_tavern(self)
            )
            first = session.world_state["locations"][first_id]
            first.update({"name": "Kael Hanı", "scene_kind": "workshop"})
            first_door.update({"name": "Kael Hanı Kapısı", "open": False, "locked": True})
            second_id = "test:local:two-door-workshop"
            second = copy.deepcopy(first)
            second.update({
                "id": second_id,
                "name": "Demirci Atölyesi",
                "parent_location_id": city_id,
                "scene_kind": "workshop",
            })
            second_door = copy.deepcopy(first_door)
            second_door.update({
                "id": f"venue-door:{second_id}",
                "name": "Demirci Atölyesi Kapısı",
                "location": city_id,
            })
            session.world_state["locations"][second_id] = second
            session.world_state["doors"].append(second_door)
            with (
                patch("game.roll_d20", return_value=8),
                patch.object(
                    self.app.state.ollama_adapter,
                    "_client",
                    ControlledVenueOllamaClient(intent="narrative"),
                ),
            ):
                response = await self.http.post(
                    turn_url,
                    json={
                        "message": "Demirci Atölyesi Kapısını omzumla zorlayarak kırmayı deniyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            reference = session.world_state["scene_state"]["entry_target_reference"]
            self.assertEqual(reference["location_id"], second_id)
            self.assertEqual(reference["door_id"], f"venue-door:{second_id}")

    async def test_non_door_athletics_near_named_venue_does_not_record_door(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            _, _, session, turn_url, venue_id, _ = (
                await create_city_with_locked_tavern(self)
            )
            session.world_state["locations"][venue_id]["name"] = "Workshop"
            with (
                patch("game.roll_d20", return_value=8),
                patch.object(
                    self.app.state.ollama_adapter,
                    "_client",
                    ControlledVenueOllamaClient(intent="narrative"),
                ),
            ):
                response = await self.http.post(
                    turn_url,
                    json={
                        "message": "Workshop yanında duvara tırmanıyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(
                session.world_state["scene_state"]["entry_target_reference"]
            )

    async def test_targetless_open_workshop_entry_works_over_resumed_http_session(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            city_id, session_id, session, turn_url, venue_id, door = (
                await create_city_with_locked_tavern(self)
            )
            session.world_state["locations"][venue_id].update({
                "name": "Kuzey Atölyesi",
                "scene_kind": "workshop",
            })
            door.update({
                "name": "Kuzey Atölyesi Kapısı",
                "open": False,
                "locked": True,
                "broken": False,
            })
            with patch("game.roll_d20", return_value=8):
                failed = await self.http.post(
                    turn_url,
                    json={
                        "message": "Kuzey Atölyesi Kapısını omzumla zorlayarak kırmayı deniyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
            self.assertEqual(failed.status_code, 200, failed.text)
            self.assertEqual(
                session.world_state["scene_state"]["entry_target_reference"][
                    "location_id"
                ],
                venue_id,
            )
            campaign_id = self.manager.get(session_id).campaign_id
            reopened = SessionManager(
                campaign_store=CampaignStore(
                    self.store.path, bound_principal=TEST_PLAYER
                )
            )
            reopened_app = create_app(
                session_manager=reopened,
                ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
                authenticator=FixedAuthenticator(TEST_PLAYER),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=reopened_app),
                base_url="http://testserver",
            ) as resumed_http:
                resumed = await resumed_http.post(
                    f"/api/game/campaigns/{campaign_id}/resume"
                )
                self.assertEqual(resumed.status_code, 200, resumed.text)
                resumed_session_id = resumed.json()["session_id"]
                resumed_session = reopened.get(resumed_session_id).game_session
                self.assertEqual(
                    resumed_session.world_state["scene_state"][
                        "entry_target_reference"
                    ]["location_id"],
                    venue_id,
                )
                resumed_door = next(
                    item for item in resumed_session.world_state["doors"]
                    if item.get("id") == f"venue-door:{venue_id}"
                )
                resumed_door.update({"open": True, "locked": False})
                with patch.object(
                    reopened_app.state.ollama_adapter,
                    "_client",
                    ControlledVenueOllamaClient(intent="narrative"),
                ):
                    entered = await resumed_http.post(
                        f"/api/game/sessions/{resumed_session_id}/turn",
                        json={
                            "message": "İçeri giriyorum.",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                self.assertEqual(entered.status_code, 200, entered.text)
                self.assertEqual(entered.json()["state"]["location"], venue_id)

    async def test_entry_reference_expires_when_target_or_source_scene_changes(self):
        cases = ("moved_target", "expired", "scene_changed", "old_save")
        for case in cases:
            with self.subTest(case=case), patch(
                "socket.socket.connect",
                side_effect=AssertionError("External network is disabled in this API test."),
            ):
                city_id, _, session, turn_url, venue_id, door = (
                    await create_city_with_locked_tavern(self)
                )
                with patch("game.roll_d20", return_value=8):
                    failed = await self.http.post(
                        turn_url,
                        json={
                            "message": "Yakındaki hanın kapısını omzumla zorlayarak kırmayı deniyorum.",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                self.assertEqual(failed.status_code, 200, failed.text)
                self.assertIsInstance(
                    session.world_state["scene_state"]["entry_target_reference"],
                    dict,
                )
                expected_location = city_id
                if case == "moved_target":
                    session.world_state["locations"][venue_id][
                        "parent_location_id"
                    ] = "fr:region:the_north"
                elif case == "expired":
                    session.world_state["flags"]["turn_index"] += 1
                elif case == "scene_changed":
                    session.world_state["location"] = "fr:region:the_north"
                    expected_location = "fr:region:the_north"
                else:
                    del session.world_state["scene_state"]["entry_target_reference"]
                plans = []
                real_plan = session.plan_living_world_turn

                @wraps(real_plan)
                def capture_plan(*args, **kwargs):
                    result = real_plan(*args, **kwargs)
                    if (args[0] if args else kwargs.get("player_input")) == "İçeri giriyorum.":
                        plans.append(copy.deepcopy(result))
                    return result

                with (
                    patch.object(session, "plan_living_world_turn", new=capture_plan),
                    patch.object(
                        self.app.state.ollama_adapter,
                        "_client",
                        ControlledVenueOllamaClient(intent="narrative"),
                    ),
                ):
                    response = await self.http.post(
                        turn_url,
                        json={
                            "message": "İçeri giriyorum.",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(session.world_state["location"], expected_location)
                self.assertEqual(len(plans), 1)
                self.assertIsNone(plans[0].get("direct_result"))

    async def test_explicit_sibling_target_overrides_recent_entry_reference(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            city_id, _, session, turn_url, venue_id, door = (
                await create_city_with_locked_tavern(self)
            )
            session.world_state["locations"][venue_id]["name"] = "Kael Hanı"
            door.update({
                "name": "Kael Hanı Kapısı",
                "open": False,
                "locked": True,
                "broken": False,
            })
            sibling_id = "test:local:demirci-atolyesi"
            sibling = copy.deepcopy(session.world_state["locations"][venue_id])
            sibling.update({
                "id": sibling_id,
                "name": "Demirci Atölyesi",
                "scene_kind": "workshop",
                "parent_location_id": city_id,
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            })
            sibling_door = copy.deepcopy(door)
            sibling_door.update({
                "id": f"venue-door:{sibling_id}",
                "name": "Demirci Atölyesi Kapısı",
                "open": True,
                "locked": False,
            })
            session.world_state["locations"][sibling_id] = sibling
            session.world_state["doors"].append(sibling_door)
            with (
                patch("game.roll_d20", return_value=8),
                patch.object(
                    self.app.state.ollama_adapter,
                    "_client",
                    ControlledVenueOllamaClient(intent="narrative"),
                ),
            ):
                failed = await self.http.post(
                    turn_url,
                    json={
                        "message": "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(failed.status_code, 200, failed.text)
                self.assertEqual(
                    session.world_state["scene_state"]["entry_target_reference"][
                        "location_id"
                    ],
                    venue_id,
                )
                entered = await self.http.post(
                    turn_url,
                    json={
                        "message": "İçeri giriyorum.",
                        "target_id": sibling_id,
                        "action_id": str(uuid.uuid4()),
                    },
                )
            self.assertEqual(entered.status_code, 200, entered.text)
            self.assertEqual(entered.json()["state"]["location"], sibling_id)
            self.assertEqual(
                session.world_state["location"],
                sibling_id,
                "The explicit non-tavern target must override the saved tavern reference.",
            )

    async def test_say_and_ask_dm_cannot_consume_local_entry_reference(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            for mode in ("say", "ask_dm"):
                city_id, _, session, turn_url, venue_id, door = (
                    await create_city_with_locked_tavern(self)
                )
                session.world_state["locations"][venue_id]["name"] = "Kael Hanı"
                door.update({
                    "name": "Kael Hanı Kapısı",
                    "open": False,
                    "locked": True,
                    "broken": False,
                })
                entry_plans = []
                real_plan = session.plan_living_world_turn

                @wraps(real_plan)
                def capture_plan(*args, **kwargs):
                    result = real_plan(*args, **kwargs)
                    message = args[0] if args else kwargs.get("player_input")
                    if message == "İçeri giriyorum.":
                        entry_plans.append(copy.deepcopy(result))
                    return result

                with (
                    patch("game.roll_d20", return_value=8) as roll,
                    patch.object(
                        self.app.state.ollama_adapter,
                        "_client",
                        ControlledVenueOllamaClient(intent="narrative"),
                    ),
                    patch.object(
                        session, "plan_living_world_turn", new=capture_plan
                    ),
                ):
                    failed = await self.http.post(
                        turn_url,
                        json={
                            "message": "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum.",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                    self.assertEqual(failed.status_code, 200, failed.text)
                    self.assertEqual(
                        session.world_state["scene_state"]["entry_target_reference"][
                            "location_id"
                        ],
                        venue_id,
                    )
                    spoken = await self.http.post(
                        turn_url,
                        json={
                            "message": "İçeri giriyorum.",
                            "interaction_mode": mode,
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                    self.assertEqual(spoken.status_code, 200, spoken.text)
                    self.assertEqual(session.world_state["location"], city_id)
                    self.assertIsNone(
                        session.world_state["scene_state"]["entry_target_reference"]
                    )
                    entered = await self.http.post(
                        turn_url,
                        json={
                            "message": "İçeri giriyorum.",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                    self.assertEqual(entered.status_code, 200, entered.text)
                    self.assertEqual(session.world_state["location"], city_id)
                    self.assertIsNone(entry_plans[-1].get("direct_result"))
                    roll.assert_called_once()

    async def test_entry_reference_rolls_back_when_blocked_entry_save_fails(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            city_id, session_id, session, turn_url, venue_id, door = (
                await create_city_with_locked_tavern(self)
            )
            session.world_state["locations"][venue_id]["name"] = "Kael Hanı"
            door.update({
                "name": "Kael Hanı Kapısı",
                "open": False,
                "locked": True,
                "broken": False,
            })
            with patch("game.roll_d20", return_value=8):
                failed_break = await self.http.post(
                    turn_url,
                    json={
                        "message": "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
            self.assertEqual(failed_break.status_code, 200, failed_break.text)
            before_entry = session.serialize_game_state()
            reference_before = copy.deepcopy(
                session.world_state["scene_state"]["entry_target_reference"]
            )
            campaign_id = self.manager.get(session_id).campaign_id
            failed_entry_body = {
                "message": "İçeri giriyorum.",
                "action_id": str(uuid.uuid4()),
            }
            with (
                patch.object(
                    self.store,
                    "save_campaign",
                    side_effect=CampaignStorageError("database unavailable"),
                ) as failed_save,
                patch.object(
                    self.app.state.ollama_adapter,
                    "_client",
                    ControlledVenueOllamaClient(intent="narrative"),
                ),
            ):
                failed_entry = await self.http.post(
                    turn_url, json=failed_entry_body
                )
            failed_save.assert_called_once()
            self.assertEqual(failed_entry.status_code, 503, failed_entry.text)
            self.assertEqual(session.serialize_game_state(), before_entry)
            self.assertEqual(
                session.world_state["scene_state"]["entry_target_reference"],
                reference_before,
            )
            self.assertIsNone(
                self.manager.get_turn_action(
                    self.manager.get(session_id), failed_entry_body["action_id"]
                )
            )

            entry_plans = []
            real_plan = session.plan_living_world_turn

            @wraps(real_plan)
            def capture_plan(*args, **kwargs):
                result = real_plan(*args, **kwargs)
                if (args[0] if args else kwargs.get("player_input")) == "İçeri giriyorum.":
                    entry_plans.append(copy.deepcopy(result))
                return result

            with patch.object(session, "plan_living_world_turn", new=capture_plan):
                retry = await self.http.post(
                    turn_url,
                    json={
                        "message": "İçeri giriyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(retry.json()["state"]["location"], city_id)
            self.assertEqual(len(entry_plans), 1)
            direct = entry_plans[0].get("direct_result")
            self.assertIsInstance(direct, dict)
            self.assertEqual(direct.get("status"), "blocked")
            self.assertEqual(direct.get("target_id"), venue_id)
            self.assertEqual(
                session.world_state["scene_state"]["entry_target_reference"],
                None,
            )

    async def test_dynamic_venue_break_preserves_authoritative_success_and_failure(self):
        city_id, _, session, turn_url, venue_id, door = await create_city_with_locked_tavern(self)
        session.world_state["locations"][venue_id]["name"] = "Kael Hanı"
        door["name"] = "Kael Hanı Kapısı"
        initial_ids = {
            "locations": set(session.world_state["locations"]),
            "npcs": {npc["id"] for npc in session.world_state["npcs"]},
            "shops": {shop["id"] for shop in session.world_state["shops"]},
        }
        outcomes = [
            {"skill": "Athletics", "dc": 15, "success": False, "outcome": "failure", "action": "skill_check"},
            {"skill": "Athletics", "dc": 15, "success": True, "outcome": "success", "action": "skill_check"},
        ]
        with patch("game.roll_d20", side_effect=[1, 20]):
            failed = await self.http.post(
                turn_url,
                json={"message": "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum.", "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(failed.status_code, 200, failed.text)
            self.assertFalse(door["broken"])
            self.assertTrue(door["locked"])
            succeeded = await self.http.post(
                turn_url,
                json={"message": "Kael Hanı Kapısını omzumla zorlayarak kırmayı deniyorum.", "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(succeeded.status_code, 200, succeeded.text)
        self.assertTrue(door["broken"])
        self.assertTrue(door["open"])
        self.assertFalse(door["locked"])
        self.assertEqual(set(session.world_state["locations"]), initial_ids["locations"])
        self.assertEqual({npc["id"] for npc in session.world_state["npcs"]}, initial_ids["npcs"])
        self.assertEqual({shop["id"] for shop in session.world_state["shops"]}, initial_ids["shops"])

    async def test_exact_dynamic_venue_unlock_with_tools_uses_existing_skill_check(self):
        _, _, session, turn_url, venue_id, door = await create_city_with_locked_tavern(self)
        session.world_state["locations"][venue_id]["name"] = "Kael Hanı"
        door["name"] = "Kael Hanı Kapısı"
        session.world_state["inventory"].append("Thieves' Tools")
        with patch("game.roll_d20", return_value=20):
            response = await self.http.post(
                turn_url,
                json={
                    "message": "Kael Hanı Kapısı kilitli. İçeri girebilmek için kilidini açmayı deniyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(door["locked"])
        self.assertFalse(door["open"])

    async def test_exact_dynamic_venue_door_unlock_without_tools_is_no_cost_400(self):
        _, _, session, turn_url, venue_id, door = await create_city_with_locked_tavern(self)
        session.world_state["locations"][venue_id]["name"] = "Kael Hanı"
        door.update({
            "name": "Kael Hanı Kapısı",
            "description": "Kael Hanı sokağa açılan kapısı",
            "open": False,
            "locked": True,
            "broken": False,
        })
        before_world = copy.deepcopy(session.world_state)
        response = await self.http.post(
            turn_url,
            json={
                "message": "Kael Hanı Kapısı kilitli. İçeri girebilmek için "
                           "kilidini açmayı deniyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"]["code"], "thieves_tools_required")
        self.assertEqual(session.world_state, before_world)

    async def test_natural_venue_door_intent_rejects_noncurrent_and_unbound_api_inputs(self):
        messages = (
            "I am not breaking Old Inn Door.",
            "I don't break Old Inn Door.",
            "Yesterday I tried breaking Old Inn Door.",
            'I tell the guard, "I break Old Inn Door".',
            "I examine Old Inn Door and break a stick.",
            "I eat breakfast beside Old Inn Door.",
            "I am not breaking Old Inn Doorway.",
            "Eski Han Kapısını kırmıyorum.",
            "Dün Eski Han Kapısını kırmayı denedim.",
            "Muhafıza, 'Eski Han Kapısını kırıyorum' diyorum.",
            "Eski Han Kapısını inceliyorum ve bir dalı kırıyorum.",
            "Kael Hanı Kapısını kırmayı deniyorum demiyorum.",
            "Kael Hanı Kapısını incelerken bir dalı kırıyorum.",
            "I don’t break Old Inn Door.",
            "I won't break Old Inn Door.",
            "I used to break Old Inn Door.",
            "Kael Hanı Kapısını kırıyorum demedim.",
            "I won’t unlock Old Inn Door.",
            "I used to unlock Old Inn Door.",
            "Kael Hanı Kapısını kilidini açmayı deniyorum demedim.",
            "I break a branch beside Old Inn Door.",
            "People say I break Old Inn Door.",
            "Şöyle demiyorum: Kael Hanı Kapısını kırıyorum.",
            "Diyelim ki Kael Hanı Kapısını kırıyorum.",
            "Şöyle demiyorum: Kael Hanı Kapısını kilidini açmayı deniyorum.",
            "Diyelim ki Kael Hanı Kapısını kilidini açmayı deniyorum.",
        )

        def entity_ids(world, key):
            collection = world.get(key)
            if isinstance(collection, dict):
                return set(collection)
            if isinstance(collection, list):
                return {
                    item["id"] for item in collection
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                }
            return set()

        async def observe_api_turn(message, door_name):
            _, _, session, turn_url, venue_id, door = await create_city_with_locked_tavern(self)
            door.update({
                "name": door_name,
                "description": door_name,
                "open": False,
                "locked": True,
                "broken": False,
            })
            session.rng.seed(1776)
            before_world = copy.deepcopy(session.world_state)
            before_door = copy.deepcopy(door)
            before_character = copy.deepcopy(session.character)
            before_inventory = copy.deepcopy(session.world_state["inventory"])
            before_combat = copy.deepcopy(session.world_state["combat"])
            before_rng = session.rng.getstate()
            before_clock = campaign_time.public_time(before_world)
            before_turn_index = before_world["flags"]["turn_index"]
            before_entities = {
                key: entity_ids(before_world, key)
                for key in ("locations", "npcs", "shops", "doors")
            }
            results = []
            real_turn = session.run_player_turn

            @wraps(real_turn)
            def capture_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result.get("action_result")))
                return result

            with (
                patch.object(session, "run_player_turn", new=capture_turn),
                patch.object(
                    self.app.state.ollama_adapter,
                    "_client",
                    ControlledVenueOllamaClient(intent="narrative"),
                ),
            ):
                response = await self.http.post(
                    turn_url,
                    json={"message": message, "action_id": str(uuid.uuid4())},
                )

            after_entities = {
                key: entity_ids(session.world_state, key)
                for key in before_entities
            }
            return {
                "status": response.status_code,
                "action": (
                    results[0].get("action")
                    if len(results) == 1 and isinstance(results[0], dict)
                    else None
                ),
                "turn_delta": (
                    session.world_state["flags"]["turn_index"] - before_turn_index
                ),
                "door_state": {
                    key: door.get(key) for key in ("open", "locked", "broken")
                },
                "initial_door_state": {
                    key: before_door.get(key) for key in ("open", "locked", "broken")
                },
                "rng_changed": session.rng.getstate() != before_rng,
                "character_changed": session.character != before_character,
                "inventory_changed": (
                    session.world_state["inventory"] != before_inventory
                ),
                "combat_changed": session.world_state["combat"] != before_combat,
                "clock_changed": (
                    campaign_time.public_time(session.world_state) != before_clock
                ),
                "new_entities": {
                    key: len(after_entities[key] - before_entities[key])
                    for key in before_entities
                },
            }

        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            for message in messages:
                with self.subTest(message=message):
                    door_name = (
                        "Eski Han Kapısı"
                        if message.startswith(("Eski Han", "Dün", "Muhafıza"))
                        else "Kael Hanı Kapısı"
                        if "Kael Hanı" in message
                        else "Old Inn Door"
                    )
                    baseline_message = (
                        "I examine the street."
                        if "examine" in message.casefold() or "incel" in message.casefold()
                        else "I take a breath."
                    )
                    baseline = await observe_api_turn(baseline_message, door_name)
                    actual = await observe_api_turn(message, door_name)
                    self.assertEqual(baseline["status"], 200)
                    self.assertEqual(actual["status"], 200)
                    self.assertEqual(baseline["turn_delta"], 1)
                    self.assertEqual(actual["turn_delta"], 1)
                    self.assertNotIn(baseline["action"], {"skill_check", "door_interaction"})
                    self.assertNotIn(actual["action"], {"skill_check", "door_interaction"})
                    self.assertEqual(actual["door_state"], actual["initial_door_state"])
                    self.assertFalse(actual["rng_changed"])
                    self.assertFalse(actual["character_changed"])
                    self.assertFalse(actual["inventory_changed"])
                    self.assertFalse(actual["combat_changed"])
                    self.assertFalse(actual["clock_changed"])
                    self.assertEqual(actual["new_entities"]["locations"], 0)
                    self.assertEqual(actual["new_entities"]["shops"], 0)
                    self.assertEqual(actual["new_entities"]["doors"], 0)
                    self.assertLessEqual(
                        actual["new_entities"]["npcs"],
                        baseline["new_entities"]["npcs"],
                        "The input must not materialize more NPCs than the ordinary-turn control.",
                    )

    async def test_public_turn_accepts_and_persists_parent_linked_scene_detail(self):
        city_id, session_id, session, turn_url, tavern_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        model = ControlledSceneDetailOllamaClient(city_id, tavern_id)
        action_id = str(uuid.uuid4())
        request_body = {
            "message": "hanın olduğu binayı araştırıyorum taş kartal kabartmasını inceliyorum",
            "action_id": action_id,
        }

        with (
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("External network is disabled in this API test."),
            ),
            patch.object(self.app.state.ollama_adapter, "_client", model),
        ):
            response = await self.http.post(
                turn_url,
                json=request_body,
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(model.calls, 0, "The synthetic proposal must pass through the model adapter.")
        self.assertLessEqual(model.calls, 2, "One logical turn must keep the existing model-call budget.")
        feature = next(
            (
                row for row in session.world_state.get("features", [])
                if row.get("name") == "Taş Kartal Kabartması"
            ),
            None,
        )
        self.assertIsNotNone(
            feature,
            "The validated local feature should be committed to world state; "
            f"schema={model.last_intent_schema_has_proposals}, "
            f"proposal={model.last_intent_proposals!r}",
        )
        self.assertEqual(feature.get("parent_id"), tavern_id)
        history_after_acceptance = len(
            self.store.get_campaign(self.manager.get(session_id).campaign_id).history
        )
        duplicate = await self.http.post(turn_url, json=request_body)
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(duplicate.json(), response.json())
        self.assertEqual(model.calls, 2)
        self.assertEqual(
            len(self.store.get_campaign(self.manager.get(session_id).campaign_id).history),
            history_after_acceptance,
        )

        campaign_id = self.manager.get(session_id).campaign_id
        resumed_manager = SessionManager(
            campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        )
        resumed_id, _, _, _, _ = resumed_manager.resume_campaign(campaign_id)
        resumed_session = resumed_manager.get(resumed_id).game_session
        resumed_app = create_app(
            session_manager=resumed_manager,
            ollama_adapter=self.app.state.ollama_adapter,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        persisted_feature = next(
            (
                row for row in resumed_session.world_state.get("features", [])
                if row.get("id") == feature["id"]
            ),
            None,
        )
        self.assertEqual(persisted_feature, feature)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=resumed_app),
            base_url="http://testserver",
        ) as resumed_http:
            replay_after_resume = await resumed_http.post(
                f"/api/game/sessions/{resumed_id}/turn",
                json=request_body,
            )
        self.assertEqual(replay_after_resume.status_code, 200, replay_after_resume.text)
        self.assertEqual(replay_after_resume.json()["action_id"], action_id)
        self.assertEqual(replay_after_resume.json()["narration"], response.json()["narration"])
        self.assertEqual(replay_after_resume.json()["state"], response.json()["state"])
        self.assertEqual(model.calls, 2)

        calls_before_targeted_inspection = model.calls
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=resumed_app),
            base_url="http://testserver",
        ) as resumed_http:
            with (
                patch(
                    "socket.socket.connect",
                    side_effect=AssertionError("External network is disabled in this API test."),
                ),
                patch.object(self.app.state.ollama_adapter, "_client", model),
            ):
                targeted = await resumed_http.post(
                    f"/api/game/sessions/{resumed_id}/turn",
                    json={
                        "message": "Hanın bulunduğu binadaki taş kartal kabartmasını inceliyorum.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
        self.assertEqual(targeted.status_code, 200, targeted.text)
        self.assertIn("Taş Kartal Kabartması", targeted.json()["narration"])
        self.assertEqual(
            model.calls,
            calls_before_targeted_inspection,
            "A saved detail should resolve through the existing deterministic inspection path.",
        )

    async def test_parent_detail_with_different_wording_targets_existing_sit_mechanic(self):
        city_id, _, session, turn_url, tavern_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        proposal = {
            "proposal_key": "f1",
            "location": city_id,
            "parent_id": tavern_id,
            "name": "Taş Bank",
            "description": "Giriş duvarının yanında alçak, sağlam bir taş bank.",
            "kind": "seat",
            "aliases": ["taş bank", "bank"],
        }
        model = ControlledSceneDetailOllamaClient(
            city_id, tavern_id, proposals=[proposal],
            narration="Giriş duvarının yanında taş bir bank göze çarpıyor.",
        )
        created = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "Hanın bulunduğu binanın girişindeki taş bankı dikkatle inceliyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(model.calls, 2)
        feature = next(
            item for item in session.world_state["features"]
            if item.get("name") == "Taş Bank"
        )
        self.assertEqual(feature.get("parent_id"), tavern_id)
        calls_before_sit = model.calls
        seated = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "Taş bankta oturuyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(seated.status_code, 200, seated.text)
        position = session.world_state["scene_state"]["player_position"]
        self.assertEqual(position["kind"], "seated")
        self.assertEqual(position["target_id"], feature["id"])
        self.assertEqual(model.calls, calls_before_sit)

    async def test_parent_detail_stays_bound_to_explicit_venue_with_sibling_venue(self):
        city_id, _, session, turn_url, venue_a_id, door_a = (
            await create_city_with_locked_tavern(self)
        )
        session.rng.seed(9)
        venue_a = session.world_state["locations"][venue_a_id]
        venue_a.update(name="Gümüş Han", aliases=["Gümüş Han"])
        venue_b_id = f"{venue_a_id}:bakir-han"
        venue_b = copy.deepcopy(venue_a)
        venue_b.update(
            id=venue_b_id,
            name="Bakır Han",
            aliases=["Bakır Han"],
        )
        session.world_state["locations"][venue_b_id] = venue_b
        door_b = copy.deepcopy(door_a)
        door_b.update(
            id=f"venue-door:{venue_b_id}",
            name="Bakır Han Kapısı",
            aliases=["Bakır Han kapısı"],
        )
        session.world_state["doors"].append(door_b)
        parents = [
            session.world_state["locations"][identity]
            for identity in (venue_a_id, venue_b_id)
        ]
        self.assertTrue(all(
            parent.get("parent_location_id") == city_id
            and parent.get("scene_kind") == "tavern"
            and parent.get("hidden") is not True
            for parent in parents
        ))

        proposal_name = "Taş Kartal Kabartması"
        proposal = {
            "proposal_key": "f1",
            "location": city_id,
            "parent_id": venue_b_id,
            "name": proposal_name,
            "description": "Giriş kemerinin üstünde taşa işlenmiş küçük bir kartal.",
            "kind": "detail",
            "aliases": ["taş kartal", "kartal kabartması"],
        }
        model = ControlledSceneDetailOllamaClient(
            city_id,
            venue_a_id,
            proposals=[proposal],
            narration=f"{proposal_name}, Bakır Han'ın kuzey duvarında.",
        )
        player_request = (
            "Gümüş Han'ın olduğu binayı araştırıyorum "
            "taş kartal kabartmasını inceliyorum"
        )
        before_entities = {
            collection: copy.deepcopy(session.world_state[collection])
            for collection in ("locations", "features", "doors", "shops")
        }
        rejected = await self.post_scene_turn(
            turn_url,
            model,
            {"message": player_request, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertNotIn(proposal_name, rejected.json()["narration"])
        for collection, before in before_entities.items():
            self.assertEqual(session.world_state[collection], before, collection)
        self.assertFalse(any(
            feature.get("name") == proposal_name
            and feature.get("parent_id") == venue_b_id
            for feature in session.world_state["features"]
        ))
        self.assertEqual(
            model.last_intent_proposals[0].get("parent_id"),
            venue_b_id,
        )
        self.assertLessEqual(model.calls, 2)

        proposal["parent_id"] = venue_a_id
        model.narration = f"{proposal_name}, Gümüş Han'ın kuzey duvarında."
        calls_before_accept = model.calls
        accepted = await self.post_scene_turn(
            turn_url,
            model,
            {"message": player_request, "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        accepted_feature = next((
            feature for feature in session.world_state["features"]
            if feature.get("name") == proposal_name
        ), None)
        self.assertIsNotNone(
            accepted_feature,
            f"proposal={model.last_intent_proposals!r}; "
            f"schema={model.last_intent_schema_has_proposals}; "
            f"features={session.world_state['features']!r}; "
            f"narration={accepted.json()['narration']!r}",
        )
        self.assertEqual(accepted_feature.get("parent_id"), venue_a_id)
        self.assertNotIn("Bakır Han", accepted.json()["narration"])
        self.assertFalse(any(
            feature.get("name") == proposal_name
            and feature.get("parent_id") == venue_b_id
            for feature in session.world_state["features"]
        ))
        self.assertLessEqual(model.calls - calls_before_accept, 2)

    async def test_scene_authority_finite_api_cases(self):
        city_id, _, session, turn_url, venue_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        session.rng.seed(9)
        venue = session.world_state["locations"][venue_id]
        venue.update(name="Gümüş Han", aliases=["Gümüş Han"])
        model = ControlledSceneDetailOllamaClient(city_id, venue_id)
        cases = (
            ("I am not inspecting the inn building.", None),
            ("If the inn building is empty, I will inspect it.", None),
            ("The guard inspects the inn building.", None),
            ("I inspect the sword while standing near the inn building.", None),
            ("Han binasını araştırıyorum demiyorum.", None),
            ("I inspect the inn building.", "say"),
            ("I inspect the inn building.", "ask_dm"),
            ("Are there windows in the inn building?", "say"),
            ("Are there windows in the inn building?", "ask_dm"),
        )
        initial_elapsed = session.world_state["campaign_time"]["elapsed_seconds"]
        for index, (message, mode) in enumerate(cases):
            with self.subTest(message=message, mode=mode):
                name = f"Authority probe detail {index}"
                model.proposals = [{
                    "proposal_key": "f1",
                    "location": city_id,
                    "parent_id": venue_id,
                    "name": name,
                    "description": f"Untrusted proposal {index}.",
                    "kind": "detail",
                    "aliases": [],
                }]
                model.narration = f"{name} is here."
                before_features = copy.deepcopy(session.world_state["features"])
                calls_before = model.calls
                body = {"message": message, "action_id": str(uuid.uuid4())}
                if mode is not None:
                    body["interaction_mode"] = mode
                response = await self.post_scene_turn(turn_url, model, body)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(session.world_state["features"], before_features)
                self.assertNotIn(name, response.json()["narration"])
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"],
                    initial_elapsed,
                )
                self.assertLessEqual(model.calls - calls_before, 2)

        before_observation = copy.deepcopy(session.world_state["features"])
        observation = await self.post_scene_turn(
            turn_url,
            model,
            {"message": "I look around freely.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(observation.status_code, 200, observation.text)
        self.assertEqual(session.world_state["features"], before_observation)

        model.proposals = [{
            "proposal_key": "f1",
            "location": city_id,
            "parent_id": venue_id,
            "name": "Confirmed ordinary detail",
            "description": "A small, visible stone carving.",
            "kind": "detail",
            "aliases": [],
        }]
        model.narration = "A small, visible stone carving is above the entrance."
        accepted = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "Gümüş Han'ın olduğu binayı araştırıyorum taş kartal kabartmasını inceliyorum",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        created = next(
            (item for item in session.world_state["features"]
             if item.get("name") == "Confirmed ordinary detail"),
            None,
        )
        self.assertIsNotNone(created)
        self.assertEqual(created.get("parent_id"), venue_id)

        question_proposal = {
            "proposal_key": "f1",
            "location": city_id,
            "parent_id": venue_id,
            "name": "Arched upper windows",
            "description": "Two narrow arched windows above the entrance.",
            "kind": "detail",
            "aliases": [],
        }
        model.proposals = [question_proposal]
        model.narration = "There are two narrow arched windows above the entrance."
        question_calls_before = model.calls
        exploratory_question = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "Are there windows in the inn building?",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(
            exploratory_question.status_code, 200, exploratory_question.text
        )
        self.assertLessEqual(model.calls - question_calls_before, 2)
        self.assertEqual(
            model.last_intent_proposals[0]["parent_id"], venue_id
        )
        proposed_window = next(
            (
                item for item in session.world_state["features"]
                if item.get("name") == "Arched upper windows"
            ),
            None,
        )
        self.assertIsNotNone(
            proposed_window,
            f"schema={model.last_intent_schema_has_proposals}; "
            f"intent_proposals={model.last_intent_proposals!r}; "
            f"response={exploratory_question.json()!r}; "
            f"features={session.world_state['features']!r}",
        )
        self.assertEqual(proposed_window.get("location"), city_id)
        self.assertEqual(proposed_window.get("parent_id"), venue_id)

    async def test_scene_target_resolution_uses_affirmed_context_and_parent(self):
        city_id, _, session, turn_url, first_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        first = session.world_state["locations"][first_id]
        first.update(name="First Inn", aliases=["First Inn"])
        second_id = f"{first_id}:second-inn"
        second = copy.deepcopy(first)
        second.update(id=second_id, name="Second Inn", aliases=["Second Inn"])
        session.world_state["locations"][second_id] = second
        model = ControlledSceneDetailOllamaClient(city_id, second_id)
        model.proposals = [{
            "proposal_key": "f1",
            "location": city_id,
            "parent_id": second_id,
            "name": "Second Inn detail",
            "description": "A newly proposed visible detail.",
            "kind": "detail",
            "aliases": [],
        }]
        response = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "I inspect Second Inn building.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(model.last_intent_proposals[0]["parent_id"], second_id)
        stored = next(
            (item for item in session.world_state["features"]
             if item.get("name") == "Second Inn detail"),
            None,
        )
        self.assertIsNotNone(stored)
        self.assertEqual(stored.get("parent_id"), second_id)

        session.world_state["features"].extend([
            {
                "id": "feature-first-sign",
                "location": city_id,
                "parent_id": first_id,
                "name": "Tabela",
                "description": "FIRST_PARENT_SIGN_PRIVATE_DETAIL",
                "kind": "detail",
                "aliases": ["Tabela"],
            },
            {
                "id": "feature-second-hidden-sign",
                "location": city_id,
                "parent_id": second_id,
                "name": "Gizli Tabela",
                "description": "HIDDEN_SIGN_PRIVATE_DETAIL",
                "kind": "detail",
                "aliases": ["Tabela"],
                "hidden": True,
            },
        ])
        quoted = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": 'I inspect Second Inn building; "Tabela" is only a word.',
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(quoted.status_code, 200, quoted.text)
        self.assertNotIn("FIRST_PARENT_SIGN_PRIVATE_DETAIL", quoted.json()["narration"])
        self.assertNotIn("HIDDEN_SIGN_PRIVATE_DETAIL", quoted.json()["narration"])

        session.world_state["location"] = second_id
        model.proposals = []
        second_detail_before = copy.deepcopy(stored)
        first_parent_features_before = copy.deepcopy([
            feature for feature in session.world_state["features"]
            if feature.get("parent_id") == first_id
        ])
        inside = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "I inspect Second Inn building and the Second Inn detail.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(inside.status_code, 200, inside.text)
        self.assertEqual(inside.json()["state"]["location"], second_id)
        self.assertIn(stored["name"], inside.json()["narration"])
        self.assertNotIn("First Inn", inside.json()["narration"])
        self.assertEqual(
            next(
                feature for feature in session.world_state["features"]
                if feature.get("id") == stored["id"]
            ),
            second_detail_before,
        )
        self.assertEqual(
            [
                feature for feature in session.world_state["features"]
                if feature.get("parent_id") == first_id
            ],
            first_parent_features_before,
        )

        session.world_state["location"] = city_id
        hidden = next(
            feature for feature in session.world_state["features"]
            if feature.get("id") == "feature-second-hidden-sign"
        )
        before_hidden = copy.deepcopy(hidden)
        model.proposals = [{
            "proposal_key": "f1",
            "location": city_id,
            "parent_id": second_id,
            "name": hidden["name"],
            "description": "GUESSED_REPLACEMENT_MUST_NOT_OVERWRITE",
            "kind": "detail",
            "aliases": ["Tabela"],
        }]
        model.narration = "A guessed detail is visible."
        hidden_guess = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "I inspect Second Inn building.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(hidden_guess.status_code, 200, hidden_guess.text)
        self.assertEqual(hidden, before_hidden)
        self.assertNotIn("HIDDEN_SIGN_PRIVATE_DETAIL", hidden_guess.json()["narration"])
        self.assertNotIn("GUESSED_REPLACEMENT_MUST_NOT_OVERWRITE", hidden_guess.json()["narration"])

    async def test_parent_detail_rejects_canonical_conflict_and_invalid_parents(self):
        city_id, _, session, turn_url, tavern_id, door = (
            await create_city_with_locked_tavern(self)
        )
        model = ControlledSceneDetailOllamaClient(city_id, tavern_id)
        cases = [
            {
                "name": "Yanlış Parent Ayrıntısı",
                "parent_id": "unknown-parent",
                "description": "Sıradan bir taş ayrıntısı.",
            },
            {
                "name": "Gizli Parent Ayrıntısı",
                "parent_id": tavern_id,
                "description": "Sıradan bir taş ayrıntısı.",
                "hide_parent": True,
            },
            {
                "name": door["name"],
                "parent_id": tavern_id,
                "description": f"{door['name']} artık açık ve kilitsiz.",
            },
        ]
        for index, case in enumerate(cases):
            with self.subTest(case=case["name"]):
                if case.get("hide_parent"):
                    session.world_state["locations"][tavern_id]["hidden"] = True
                model.proposals = [{
                    "proposal_key": "f1",
                    "location": city_id,
                    "parent_id": case["parent_id"],
                    "name": case["name"],
                    "description": case["description"],
                    "kind": "detail",
                    "aliases": [],
                }]
                model.narration = f"{case['name']} burada bulunuyor."
                calls_before = model.calls
                engine_results = []
                original_turn = session.run_player_turn

                @wraps(original_turn)
                def capture_turn(*args, **kwargs):
                    result = original_turn(*args, **kwargs)
                    engine_results.append(copy.deepcopy(result["action_result"]))
                    return result

                with patch.object(session, "run_player_turn", new=capture_turn):
                    response = await self.post_scene_turn(
                        turn_url,
                        model,
                        {
                            "message": "hanın olduğu binayı araştırıyorum taş kartal kabartmasını inceliyorum",
                            "action_id": str(uuid.uuid4()),
                        },
                    )
                if case.get("hide_parent"):
                    session.world_state["locations"][tavern_id].pop("hidden", None)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertLessEqual(model.calls - calls_before, 2)
                self.assertTrue(
                    engine_results[-1].get("scene_detail_proposal_submitted"),
                    f"engine={engine_results[-1]!r}; proposal={model.last_intent_proposals!r}",
                )
                self.assertEqual(
                    engine_results[-1].get("verified_world_updates", {}).get(
                        "create_features"
                    ),
                    [],
                )
                self.assertNotIn(case["name"], response.json()["narration"])
                self.assertFalse(any(
                    item.get("name") == case["name"]
                    for item in session.world_state["features"]
                ))
        self.assertTrue(door["locked"])
        self.assertFalse(door["open"])

    async def test_question_denial_and_false_history_cannot_authorize_scene_details(self):
        city_id, _, session, turn_url, tavern_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        model = ControlledSceneDetailOllamaClient(
            city_id,
            tavern_id,
            proposals=[{
                "proposal_key": "f1",
                "location": city_id,
                "parent_id": tavern_id,
                "name": "Yetkisiz Kabartma",
                "description": "Bir taş kartal kabartması.",
                "kind": "detail",
                "aliases": ["yetkisiz kabartma"],
            }],
            narration="Yetkisiz Kabartma burada bulunuyor.",
        )
        messages = (
            "Hanın bulunduğu binada taş kartal kabartması var mı?",
            "Hanın bulunduğu binadaki taş kabartmayı incelemiyorum.",
            "Daha önce hanın duvarında taş kartal kabartması gördüğümü söylüyorum.",
        )
        for message in messages:
            with self.subTest(message=message):
                before_calls = model.calls
                response = await self.post_scene_turn(
                    turn_url,
                    model,
                    {"message": message, "action_id": str(uuid.uuid4())},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn("Yetkisiz Kabartma", response.json()["narration"])
                self.assertFalse(any(
                    item.get("name") == "Yetkisiz Kabartma"
                    for item in session.world_state["features"]
                ))
                self.assertLessEqual(model.calls - before_calls, 2)

    async def test_parent_detail_save_failure_rolls_back_state_rng_and_receipt(self):
        city_id, session_id, session, turn_url, tavern_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        model = ControlledSceneDetailOllamaClient(city_id, tavern_id)
        campaign_id = self.manager.get(session_id).campaign_id
        record = self.manager.get(session_id)
        before_state = copy.deepcopy(session.serialize_game_state())
        before_rng = session.rng.getstate()
        before_saved = self.store.get_campaign(campaign_id)
        before_history_count = len(before_saved.history)
        action_id = str(uuid.uuid4())
        body = {
            "message": "hanın olduğu binayı araştırıyorum taş kartal kabartmasını inceliyorum",
            "action_id": action_id,
        }
        original_save = self.store.save_campaign
        save_calls = 0

        def fail_once(*args, **kwargs):
            nonlocal save_calls
            save_calls += 1
            if save_calls == 1:
                raise CampaignStorageError("synthetic save failure")
            return original_save(*args, **kwargs)

        with patch.object(self.store, "save_campaign", side_effect=fail_once):
            failed = await self.post_scene_turn(turn_url, model, body)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(session.serialize_game_state(), before_state)
        self.assertEqual(session.rng.getstate(), before_rng)
        self.assertIsNone(
            self.store.get_turn_action(
                campaign_id,
                action_id,
                principal=TEST_PLAYER,
            )
        )
        self.assertEqual(
            len(self.store.get_campaign(campaign_id).history),
            before_history_count,
        )
        self.assertFalse(any(
            item.get("name") == "Taş Kartal Kabartması"
            for item in session.world_state["features"]
        ))
        self.assertEqual(model.calls, 2)

        retry = await self.post_scene_turn(turn_url, model, body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(model.calls, 4)
        saved = self.store.get_campaign(campaign_id)
        self.assertEqual(len(saved.history), before_history_count + 1)
        self.assertEqual(saved.history[-1]["player_message"], body["message"])
        self.assertIsNotNone(
            self.store.get_turn_action(
                campaign_id,
                action_id,
                principal=TEST_PLAYER,
            )
        )
        receipt_replay = await self.post_scene_turn(turn_url, model, body)
        self.assertEqual(receipt_replay.status_code, 200, receipt_replay.text)
        self.assertEqual(receipt_replay.json(), retry.json())
        self.assertEqual(model.calls, 4)
        self.assertEqual(len(self.store.get_campaign(campaign_id).history), before_history_count + 1)

    async def test_natural_venue_door_knock_binds_the_named_door(self):
        positives = (
            ("kael hanı kapısına elimle tıklıyorum", "Kael Hanı Kapısı"),
            ("Kael Hanı Kapısına tıklatıyorum.", "Kael Hanı Kapısı"),
            ("Kael Hanı Kapısını çalıyorum.", "Kael Hanı Kapısı"),
            ("I knock on Old Inn Door.", "Old Inn Door"),
        )
        negatives = (
            ("Kael Hanı Kapısına tıklıyorum demiyorum.", "Kael Hanı Kapısı"),
            ("Şöyle demiyorum: Kael Hanı Kapısına tıklıyorum.", "Kael Hanı Kapısı"),
            ("Muhafıza, 'Kael Hanı Kapısına tıklıyorum' diyorum.", "Kael Hanı Kapısı"),
            ("Eski Han Kapısına tıklıyorum.", "Kael Hanı Kapısı"),
            ("I am not knocking on Old Inn Door.", "Old Inn Door"),
            ('I tell the guard, "I knock on Old Inn Door".', "Old Inn Door"),
            ("I knock on the window.", "Old Inn Door"),
        )

        async def post_knock(message, door_name):
            _, _, session, turn_url, _, door = await create_city_with_locked_tavern(self)
            door.update({
                "name": door_name,
                "description": door_name,
                "open": False,
                "locked": True,
                "broken": False,
            })
            before_door = {
                key: door.get(key) for key in ("open", "locked", "broken")
            }
            before_location = session.world_state["location"]
            before_rng = session.rng.getstate()
            results = []
            real_turn = session.run_player_turn

            @wraps(real_turn)
            def capture_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                action_result = result.get("action_result")
                results.append(copy.deepcopy(action_result) if isinstance(action_result, dict) else None)
                return result

            with (
                patch.object(session, "run_player_turn", new=capture_turn),
                patch(
                    "socket.socket.connect",
                    side_effect=AssertionError("External network is disabled in this API test."),
                ),
            ):
                response = await self.http.post(
                    turn_url,
                    json={"message": message, "action_id": str(uuid.uuid4())},
                )
            return {
                "status": response.status_code,
                "narration": response.json().get("narration") if response.status_code == 200 else "",
                "skill": response.json().get("skill_check_result") if response.status_code == 200 else None,
                "action": results[0].get("action") if len(results) == 1 and isinstance(results[0], dict) else None,
                "door": {key: door.get(key) for key in ("open", "locked", "broken")},
                "before_door": before_door,
                "location": session.world_state["location"],
                "before_location": before_location,
                "rng_changed": session.rng.getstate() != before_rng,
            }

        for message, door_name in positives:
            with self.subTest(message=message):
                observed = await post_knock(message, door_name)
                self.assertEqual(observed["status"], 200)
                self.assertEqual(observed["action"], "door_knock")
                self.assertIn(door_name, observed["narration"])
                self.assertIn("kilitli", observed["narration"])
                self.assertIsNone(observed["skill"])
                self.assertEqual(observed["door"], observed["before_door"])
                self.assertEqual(observed["location"], observed["before_location"])
                self.assertFalse(observed["rng_changed"])

        for message, door_name in negatives:
            with self.subTest(message=message):
                _, _, session, turn_url, _, door = await create_city_with_locked_tavern(self)
                door.update({
                    "name": door_name,
                    "description": door_name,
                    "open": False,
                    "locked": True,
                    "broken": False,
                })
                before_door = {
                    key: door.get(key) for key in ("open", "locked", "broken")
                }
                results = []
                real_turn = session.run_player_turn

                @wraps(real_turn)
                def capture_turn(*args, **kwargs):
                    result = real_turn(*args, **kwargs)
                    action_result = result.get("action_result")
                    results.append(copy.deepcopy(action_result) if isinstance(action_result, dict) else None)
                    return result

                with (
                    patch.object(session, "run_player_turn", new=capture_turn),
                    patch.object(
                        self.app.state.ollama_adapter,
                        "_client",
                        ControlledVenueOllamaClient(intent="narrative"),
                    ),
                    patch(
                        "socket.socket.connect",
                        side_effect=AssertionError("External network is disabled in this API test."),
                    ),
                ):
                    response = await self.http.post(
                        turn_url,
                        json={"message": message, "action_id": str(uuid.uuid4())},
                    )
                action = results[0].get("action") if len(results) == 1 and isinstance(results[0], dict) else None
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotEqual(action, "door_knock")
                self.assertEqual(
                    {key: door.get(key) for key in ("open", "locked", "broken")},
                    before_door,
                )

    async def test_natural_venue_door_api_binds_operation_to_named_door(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            _, _, session, turn_url, venue_id, door = await create_city_with_locked_tavern(self)
        door.update({
            "name": "Old Inn Door",
            "description": "Old Inn Door",
            "open": False,
            "locked": True,
            "broken": False,
        })
        chest_message = "I break Old Inn Door after unlocking my chest."
        with (
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("External network is disabled in this API test."),
            ),
            patch("game.roll_d20", return_value=20),
            patch.object(
                self.app.state.ollama_adapter,
                "_client",
                ControlledVenueOllamaClient(intent="narrative"),
            ),
        ):
            chest_response = await self.http.post(
                turn_url,
                json={"message": chest_message, "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(chest_response.status_code, 200, chest_response.text)
        self.assertTrue(door["broken"])
        self.assertTrue(door["open"])
        self.assertFalse(door["locked"])

    async def test_natural_venue_door_api_matches_door_ids_by_boundaries(self):
        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        ):
            _, _, session, turn_url, _, door = await create_city_with_locked_tavern(self)
        short_door = copy.deepcopy(door)
        short_door.update({
            "id": "venue-door:location_001",
            "name": "Short Door",
            "open": False,
            "locked": True,
            "broken": False,
        })
        long_door = copy.deepcopy(short_door)
        long_door.update({
            "id": "venue-door:location_0010",
            "name": "Long Door",
        })
        session.world_state["doors"] = [short_door, long_door]
        with (
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("External network is disabled in this API test."),
            ),
            patch("game.roll_d20", return_value=20),
            patch.object(
                self.app.state.ollama_adapter,
                "_client",
                ControlledVenueOllamaClient(intent="narrative"),
            ),
        ):
            identity_response = await self.http.post(
                turn_url,
                json={
                    "message": "I break venue-door:location_0010.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(identity_response.status_code, 200, identity_response.text)
        self.assertFalse(short_door["broken"])
        self.assertTrue(long_door["broken"])
        self.assertTrue(long_door["open"])
        self.assertFalse(long_door["locked"])

    async def test_natural_venue_door_api_accepts_plain_english_break_and_unlock(self):
        network_block = patch(
            "socket.socket.connect",
            side_effect=AssertionError("External network is disabled in this API test."),
        )
        with network_block:
            _, _, break_session, break_url, _, break_door = await create_city_with_locked_tavern(self)
        break_door.update({
            "name": "Old Inn Door",
            "description": "Old Inn Door",
            "open": False,
            "locked": True,
            "broken": False,
        })
        break_attempts = []
        real_break = break_session.run_player_turn

        @wraps(real_break)
        def capture_break(*args, **kwargs):
            result = real_break(*args, **kwargs)
            break_attempts.append(copy.deepcopy(result.get("action_result")))
            return result

        with (
            network_block,
            patch("game.roll_d20", return_value=20),
            patch.object(break_session, "run_player_turn", new=capture_break),
            patch.object(
                self.app.state.ollama_adapter,
                "_client",
                ControlledVenueOllamaClient(intent="narrative"),
            ),
        ):
            broken = await self.http.post(
                break_url,
                json={"message": "I break Old Inn Door.", "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(broken.status_code, 200, broken.text)
        self.assertEqual(len(break_attempts), 1)
        self.assertEqual(break_attempts[0]["action"], "skill_check")
        self.assertEqual(break_attempts[0]["skill"], "Athletics")
        self.assertTrue(break_door["broken"])
        self.assertTrue(break_door["open"])
        self.assertFalse(break_door["locked"])

        with network_block:
            _, _, unlock_session, unlock_url, _, unlock_door = await create_city_with_locked_tavern(self)
        unlock_door.update({
            "name": "Old Inn Door",
            "description": "Old Inn Door",
            "open": False,
            "locked": True,
            "broken": False,
        })
        before_world = copy.deepcopy(unlock_session.world_state)
        before_rng = unlock_session.rng.getstate()
        unlock_attempts = []
        real_unlock = unlock_session.run_player_turn

        @wraps(real_unlock)
        def capture_unlock(*args, **kwargs):
            result = real_unlock(*args, **kwargs)
            unlock_attempts.append(copy.deepcopy(result.get("action_result")))
            return result

        with (
            network_block,
            patch.object(unlock_session, "run_player_turn", new=capture_unlock),
            patch.object(
                self.app.state.ollama_adapter,
                "_client",
                ControlledVenueOllamaClient(intent="narrative"),
            ),
        ):
            locked = await self.http.post(
                unlock_url,
                json={"message": "I unlock Old Inn Door.", "action_id": str(uuid.uuid4())},
            )
        self.assertEqual(locked.status_code, 400, locked.text)
        self.assertEqual(locked.json()["detail"]["code"], "thieves_tools_required")
        self.assertEqual(unlock_attempts, [])
        self.assertEqual(unlock_session.world_state, before_world)
        self.assertEqual(unlock_session.rng.getstate(), before_rng)

    async def test_venue_gate_targets_legacy_routes_and_campaigns_independently(self):
        city_id, first_id, first, first_url, first_venue_id, first_door = (
            await create_city_with_locked_tavern(self)
        )
        other_city_id, second_id, second, second_url, second_campaign_venue_id, second_campaign_door = (
            await create_city_with_locked_tavern(self)
        )
        self.assertEqual(city_id, other_city_id)

        second_venue = copy.deepcopy(first.world_state["locations"][first_venue_id])
        second_venue_id = "venue:second-test-tavern"
        second_venue.update({
            "id": second_venue_id,
            "name": "İkinci Han",
            "aliases": ["ikinci han", "second inn"],
            "parent_location_id": city_id,
            "exit_location_id": city_id,
        })
        first.world_state["locations"][second_venue_id] = second_venue
        second_venue_door = {
            **copy.deepcopy(first_door),
            "id": f"venue-door:{second_venue_id}",
            "name": "İkinci Han Kapısı",
            "location": city_id,
            "open": False,
            "locked": True,
        }
        first.world_state["doors"].append(second_venue_door)
        first_door["open"] = True
        first_door["locked"] = False

        with patch("timed_gameplay.travel_dice", return_value=(None, {})):
            first_entry = await self.http.post(
                first_url,
                json={
                    "message": f"{first_venue_id} konumuna gidiyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(first_entry.status_code, 200, first_entry.text)
        self.assertEqual(first_entry.json()["state"]["location"], first_venue_id)
        self.assertTrue(second_venue_door["locked"])

        exit_response = await self.http.post(
            first_url,
            json={
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(exit_response.status_code, 200, exit_response.text)
        self.assertEqual(exit_response.json()["state"]["location"], city_id)

        legacy_id = "venue:legacy-test-tavern"
        first.world_state["locations"][first_venue_id]["aliases"] = [
            alias
            for alias in first.world_state["locations"][first_venue_id].get("aliases", [])
            if alias.casefold() != "tavern"
        ]
        legacy = copy.deepcopy(second_venue)
        legacy.update({
            "id": legacy_id,
            "name": "Eski Han",
            "aliases": [*legacy.get("aliases", []), legacy_id],
        })
        first.world_state["locations"][legacy_id] = legacy
        first.world_state["locations"][city_id]["travel_routes"] = {
            "side-forest": [300],
            legacy_id: [300],
        }
        first.world_state["locations"]["side-forest"] = {
            "id": "side-forest",
            "name": "Yan Orman",
            "aliases": ["side-forest"],
            "region_id": "fr:region:the_north",
        }
        with (
            patch.object(
                self.app.state.ollama_adapter,
                "_client",
                ControlledVenueOllamaClient(
                    intent="travel",
                    target_reference=legacy_id,
                ),
            ),
            patch("timed_gameplay.travel_dice", return_value=(None, {})),
        ):
            legacy_entry = await self.http.post(
                first_url,
                json={
                    "message": f"{legacy_id} konumuna gidiyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(legacy_entry.status_code, 200, legacy_entry.text)
        self.assertEqual(legacy_entry.json()["state"]["location"], legacy_id)

        # A legacy child with no matching venue-door record remains traversable.
        first.world_state["location"] = city_id
        first.world_state["locations"][city_id]["travel_routes"] = {
            "side-forest": [300],
        }
        with (
            patch.object(
                self.app.state.ollama_adapter,
                "_client",
                ControlledVenueOllamaClient(
                    intent="travel",
                    target_reference="side-forest",
                ),
            ),
            patch("timed_gameplay.travel_dice", return_value=(None, {})),
        ):
            unrelated = await self.http.post(
                first_url,
                json={
                    "message": "side-forest konumuna gidiyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(unrelated.status_code, 200, unrelated.text)
        self.assertEqual(unrelated.json()["state"]["location"], "side-forest")

        before_second = second.world_state["campaign_time"]["elapsed_seconds"]
        blocked_second = await self.http.post(
            second_url,
            json={
                "message": f"{second_campaign_venue_id} konumuna gidiyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(blocked_second.status_code, 200, blocked_second.text)
        self.assertEqual(blocked_second.json()["state"]["location"], city_id)
        self.assertEqual(second.world_state["location"], city_id)
        self.assertEqual(
            second.world_state["campaign_time"]["elapsed_seconds"],
            before_second,
        )

    async def test_locked_sibling_venue_blocks_http_and_direct_entry_paths(self):
        cases = (
            ("location ID", "venue-id"),
            ("venue name", "venue-name"),
            ("direct engine entry", "direct-entry"),
            ("HTTP continuation", "continuation"),
        )
        for label, path in cases:
            with self.subTest(path=label):
                city_id, session_id, session, turn_url, source_id, source_door = (
                    await create_city_with_locked_tavern(self)
                )
                source_door["locked"] = False
                source_door["open"] = True
                entered = await self.http.post(
                    turn_url,
                    json={
                        "message": "Enter the tavern.",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(entered.status_code, 200, entered.text)
                self.assertEqual(entered.json()["state"]["location"], source_id)

                target_id = "sibling_venue_02"
                target_name = (
                    "Taverna Kardeş"
                    if path == "direct-entry"
                    else "Kilitli İkinci Mekân"
                )
                if path == "direct-entry":
                    source_location = session.world_state["locations"][source_id]
                    source_location["aliases"] = [
                        alias for alias in source_location.get("aliases", [])
                        if str(alias).casefold() not in {"tavern", "taverna"}
                    ]
                target = copy.deepcopy(session.world_state["locations"][source_id])
                target.update({
                    "id": target_id,
                    "name": target_name,
                    "aliases": (
                        [target_id, "taverna", "taverna kardeş"]
                        if path == "direct-entry"
                        else [target_id, "kilitli ikinci mekân"]
                    ),
                    "parent_location_id": city_id,
                    "exit_location_id": city_id,
                })
                session.world_state["locations"][target_id] = target
                target_door = {
                    **copy.deepcopy(source_door),
                    "id": f"venue-door:{target_id}",
                    "name": "Kilitli Kardeş Han Kapısı",
                    "location": city_id,
                    "open": False,
                    "locked": True,
                }
                session.world_state["doors"].append(target_door)
                self.assertEqual(target["parent_location_id"], city_id)
                self.assertEqual(
                    session.world_state["locations"][source_id]["parent_location_id"],
                    city_id,
                )
                self.assertTrue(source_door["open"])
                self.assertTrue(target_door["locked"])
                self.assertIs(
                    game._venue_entry_door(
                        session.world_state,
                        source_id,
                        target_id,
                    ),
                    target_door,
                )
                self.assertIsNone(
                    game._venue_entry_door(
                        session.world_state,
                        source_id,
                        source_id,
                    )
                )
                messages = {
                    "venue-id": f"{target_id} konumuna gidiyorum.",
                    "venue-name": f"{target_name} konumuna gidiyorum.",
                    "direct-entry": "Taverna'ya gidiyorum.",
                    "continuation": "Yolculuğa devam ediyorum.",
                }
                continuation_before_world = None
                continuation_before_rng = None
                continuation_after_world = None
                continuation_after_rng = None
                http_after_world = None
                http_after_rng = None
                if path == "continuation":
                    session.world_state["journey"] = {
                        "origin": source_id,
                        "destination": target_id,
                        "stages": [300],
                        "stage_index": 0,
                        "stage_spent_seconds": 150,
                        "stage_checked": True,
                        "status": "INTERRUPTED",
                        "encounter": None,
                        "recent_patterns": [],
                    }
                results = []
                real_turn = session.run_player_turn

                @wraps(real_turn)
                def capture_turn(*args, **kwargs):
                    quest = None
                    if path == "direct-entry":
                        npc_ids = [
                            npc.get("id")
                            for npc in session.world_state.get("npcs", [])
                            if isinstance(npc, dict)
                            and isinstance(npc.get("id"), str)
                        ]
                        self.assertTrue(npc_ids)
                        quest = adventure_templates.instantiate(
                            "BOUNTY",
                            quest_id="adv.sibling-venue-test",
                            turn=1,
                            opportunity_key="opportunity:sibling-venue-test",
                            creation_evidence="event:sibling-venue-test",
                            bindings=adventure_templates.prepared_bindings(
                                source_npc_id=npc_ids[0],
                                target_npc_id=npc_ids[-1],
                                location_ids=[city_id],
                            ),
                            rumor="Synthetic route fixture for the HTTP regression.",
                        )
                        quest = adventure_transitions.transition(
                            quest, "DISCOVERED", 1
                        )
                        quest = adventure_transitions.transition(
                            quest, "ACTIVE", 2
                        )
                        session.world_state["quests"].append(quest)
                    try:
                        result = real_turn(*args, **kwargs)
                    finally:
                        if quest is not None:
                            session.world_state["quests"].remove(quest)
                    results.append(copy.deepcopy(result["action_result"]))
                    return result

                def capture_continue(target_session):
                    nonlocal continuation_before_world, continuation_before_rng
                    nonlocal continuation_after_world, continuation_after_rng
                    if path == "continuation" and continuation_before_world is None:
                        continuation_before_world = copy.deepcopy(
                            target_session.world_state
                        )
                        continuation_before_rng = copy.deepcopy(
                            target_session.rng.getstate()
                        )
                    result = real_continue(target_session)
                    if path == "continuation":
                        continuation_after_world = copy.deepcopy(
                            target_session.world_state
                        )
                        continuation_after_rng = copy.deepcopy(
                            target_session.rng.getstate()
                        )
                    return result

                real_continue = timed_gameplay.continue_travel
                body = {
                    "message": messages[path],
                    "action_id": str(uuid.uuid4()),
                }
                with (
                    patch.object(session, "run_player_turn", new=capture_turn),
                    patch.object(
                        timed_gameplay,
                        "continue_travel",
                        new=capture_continue,
                    ),
                    patch("timed_gameplay.travel_dice", return_value=(None, {})),
                    patch.object(
                        self.app.state.ollama_adapter,
                        "_client",
                        ControlledVenueOllamaClient(
                            intent="travel",
                            target_reference=target_id,
                        ),
                    ),
                ):
                    response = await self.http.post(turn_url, json=body)

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    results[-1]["status"],
                    "blocked",
                    f"path={path} result={results[-1]!r}",
                )
                self.assertEqual(
                    response.json()["state"]["location"],
                    source_id,
                )
                if path == "continuation":
                    self.assertEqual(
                        continuation_after_world,
                        continuation_before_world,
                        msg="blocked continuation mutated canonical world state",
                    )
                    self.assertEqual(
                        continuation_after_rng,
                        continuation_before_rng,
                    )
                    for key in ("location", "journey", "campaign_time"):
                        self.assertEqual(
                            session.world_state.get(key),
                            continuation_before_world.get(key),
                            msg=f"blocked HTTP continuation changed {key}",
                        )
                    http_after_world = copy.deepcopy(session.world_state)
                    http_after_rng = copy.deepcopy(session.rng.getstate())
                    first_result_count = len(results)
                    replay = await self.http.post(turn_url, json=body)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    self.assertEqual(replay.json(), response.json())
                    self.assertEqual(len(results), first_result_count)
                    self.assertEqual(
                        session.world_state,
                        http_after_world,
                    )
                    self.assertEqual(
                        session.rng.getstate(),
                        http_after_rng,
                    )
                    campaign_id = self.manager.get(session_id).campaign_id
                    resumed_manager = SessionManager(
                        campaign_store=CampaignStore(
                            self.store.path,
                            bound_principal=TEST_PLAYER,
                        )
                    )
                    _, resumed, _, _, _ = resumed_manager.resume_campaign(
                        campaign_id
                    )
                    self.assertEqual(
                        resumed.game_session.world_state,
                        http_after_world,
                    )
                    self.assertEqual(
                        resumed.game_session.rng.getstate(),
                        http_after_rng,
                    )

    async def test_discovered_tavern_visit_city_return_and_revisit_survive_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        session = self.manager.get(created["session_id"]).game_session
        url = f"/api/game/sessions/{created['session_id']}/turn"
        results = []

        # Keep the real engine and HTTP save path; capture only the internal
        # action result, which the public TurnResponse does not expose.
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        search_body = {
            "message": "Yakınlarda bir taverna arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        enter_body = {
            "message": "Enter the tavern.",
            "action_id": str(uuid.uuid4()),
        }
        with patch.object(session, "run_player_turn", new=capture_turn):
            search = await self.http.post(url, json=search_body)
            self.assertEqual(search.status_code, 200, search.text)
            self.assertEqual(results[-1]["action"], "local_search")
            self.assertEqual(results[-1]["status"], "found")
            tavern_id = results[-1]["target_id"]
            unlock_venue_door(session.world_state, tavern_id)
            self.assertEqual(search.json()["state"]["location"], city_id)
            city_visits = session.world_state["scene_state"]["scenes"][city_id][
                "visit_revision"
            ]

            enter = await self.http.post(url, json=enter_body)
            self.assertEqual(enter.status_code, 200, enter.text)
            self.assertEqual(results[-1]["action"], "enter")
            self.assertEqual(results[-1]["status"], "completed")
            self.assertEqual(results[-1]["target_id"], tavern_id)
            self.assertEqual(enter.json()["state"]["location"], tavern_id)

        entered_world = session.world_state
        tavern = entered_world["locations"][tavern_id]
        self.assertEqual(tavern["scene_kind"], "tavern")
        self.assertEqual(tavern["parent_location_id"], city_id)
        self.assertEqual(tavern["exit_location_id"], city_id)
        self.assertEqual(
            sum(
                location.get("scene_kind") == "tavern"
                and location.get("parent_location_id") == city_id
                for location in entered_world["locations"].values()
            ),
            1,
        )
        tavern_visits = entered_world["scene_state"]["scenes"][tavern_id][
            "visit_revision"
        ]
        self.assertGreater(tavern_visits, 0)
        self.assertEqual(
            entered_world["scene_state"]["player_position"]["location_id"],
            tavern_id,
        )
        entered_save = copy.deepcopy(session.serialize_game_state())
        self.assertEqual(
            self.store.get_campaign(campaign_id).payload["engine_save"],
            entered_save,
        )

        # A new manager/store must restore the venue and its visit, not
        # reconstruct a second local tavern when the player exits.
        reloaded_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reloaded_manager = SessionManager(campaign_store=reloaded_store)
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], enter.json()["state"])
            session_id = resumed.json()["session_id"]
            loaded = reloaded_manager.get(session_id).game_session
            self.assertEqual(loaded.serialize_game_state(), entered_save)
            resumed_world = loaded.world_state
            city_visits_after_entry = resumed_world["scene_state"]["scenes"][city_id][
                "visit_revision"
            ]
            self.assertEqual(city_visits_after_entry, city_visits + 1)
            self.assertEqual(resumed_world["locations"][tavern_id], tavern)
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                tavern_id,
            )
            locations_before_exit = copy.deepcopy(resumed_world["locations"])
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            real_exit = loaded.run_player_turn
            exit_results = []

            @wraps(real_exit)
            def capture_exit(*args, **kwargs):
                result = real_exit(*args, **kwargs)
                exit_results.append(copy.deepcopy(result["action_result"]))
                return result

            turn_url = f"/api/game/sessions/{session_id}/turn"
            with patch.object(loaded, "run_player_turn", new=capture_exit):
                exit_response = await http.post(turn_url, json=exit_body)
            self.assertEqual(exit_response.status_code, 200, exit_response.text)
            self.assertEqual(exit_results[0]["action"], "exit")
            self.assertEqual(exit_results[0]["status"], "completed")
            self.assertEqual(exit_results[0]["target_id"], city_id)
            self.assertEqual(exit_response.json()["state"]["location"], city_id)
            self.assertEqual(resumed_world["locations"], locations_before_exit)
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                city_id,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits_after_entry + 1,
            )
            exited_save = copy.deepcopy(loaded.serialize_game_state())
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                exited_save,
            )

            # All three receipts must replay historical responses, even though
            # the current location is now different from the search/enter turns.
            with patch.object(
                loaded, "run_player_turn",
                side_effect=AssertionError("Receipt replay must not execute a turn"),
            ):
                for body, original in (
                    (search_body, search),
                    (enter_body, enter),
                    (exit_body, exit_response),
                ):
                    replay = await http.post(turn_url, json=body)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    self.assertEqual(
                        replay.json(), {**original.json(), "session_id": session_id}
                    )
                    self.assertEqual(loaded.serialize_game_state(), exited_save)
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                exited_save,
            )
            self.assertEqual(len(reloaded_store.get_campaign(campaign_id).history), 3)

            # A fresh action is a second visit, not a replay of the first entry.
            revisit_body = {
                "message": "Enter the tavern.",
                "action_id": str(uuid.uuid4()),
            }
            self.assertNotIn(
                revisit_body["action_id"],
                {body["action_id"] for body in (search_body, enter_body, exit_body)},
            )
            revisit_results = []
            real_revisit = loaded.run_player_turn

            @wraps(real_revisit)
            def capture_revisit(*args, **kwargs):
                result = real_revisit(*args, **kwargs)
                revisit_results.append(copy.deepcopy(result["action_result"]))
                return result

            # The real second entry completes in the engine, but a failed
            # autosave must leave both the live session and disk at the exit.
            exited_record = reloaded_manager.get(session_id)
            exited_journal = copy.deepcopy(exited_record.journal)
            exited_memory = copy.deepcopy(exited_record.narrative_memory)
            exited_receipts = copy.deepcopy(exited_record.turn_action_receipts)
            exited_campaign = reloaded_store.get_campaign(campaign_id)
            with (
                patch.object(loaded, "run_player_turn", new=capture_revisit),
                patch.object(
                    reloaded_store,
                    "save_campaign",
                    side_effect=CampaignStorageError("database unavailable"),
                ) as failed_save,
            ):
                failed_revisit = await http.post(turn_url, json=revisit_body)
            failed_save.assert_called_once()
            self.assertEqual(failed_revisit.status_code, 503, failed_revisit.text)
            self.assertEqual(
                failed_revisit.json()["detail"]["code"],
                "campaign_storage_unavailable",
            )
            self.assertNotIn("database unavailable", failed_revisit.text)
            self.assertEqual(len(revisit_results), 1)
            self.assertEqual(revisit_results[0]["action"], "enter")
            self.assertEqual(revisit_results[0]["status"], "completed")
            self.assertEqual(revisit_results[0]["target_id"], tavern_id)
            self.assertEqual(loaded.serialize_game_state(), exited_save)
            self.assertEqual(resumed_world["location"], city_id)
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                city_id,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits_after_entry + 1,
            )
            self.assertEqual(exited_record.journal, exited_journal)
            self.assertEqual(exited_record.narrative_memory, exited_memory)
            self.assertEqual(exited_record.turn_action_receipts, exited_receipts)
            self.assertNotIn(revisit_body["action_id"], exited_record.turn_action_receipts)
            failed_campaign = reloaded_store.get_campaign(campaign_id)
            self.assertEqual(failed_campaign.payload, exited_campaign.payload)
            self.assertEqual(failed_campaign.metadata, exited_campaign.metadata)
            self.assertEqual(failed_campaign.history, exited_campaign.history)
            self.assertEqual(len(failed_campaign.history), 3)
            self.assertIsNone(
                reloaded_store.get_turn_action(campaign_id, revisit_body["action_id"])
            )

            # Independently reopening after the failure must see the city exit,
            # with no uncommitted second visit, history entry, or action receipt.
            failed_resume_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
            failed_resume_manager = SessionManager(campaign_store=failed_resume_store)
            failed_resume_app = create_app(
                session_manager=failed_resume_manager,
                ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=failed_resume_app),
                base_url="http://testserver",
            ) as failed_resume_http:
                failed_resume = await failed_resume_http.post(
                    f"/api/game/campaigns/{campaign_id}/resume"
                )
            self.assertEqual(failed_resume.status_code, 200, failed_resume.text)
            self.assertEqual(failed_resume.json()["state"], exit_response.json()["state"])
            failed_resume_record = failed_resume_manager.get(
                failed_resume.json()["session_id"]
            )
            self.assertEqual(
                failed_resume_record.game_session.serialize_game_state(), exited_save
            )
            self.assertEqual(
                failed_resume_store.get_campaign(campaign_id).history,
                exited_campaign.history,
            )
            self.assertIsNone(
                failed_resume_store.get_turn_action(
                    campaign_id, revisit_body["action_id"]
                )
            )

            # Retry the same uncommitted action after storage recovers.
            with patch.object(loaded, "run_player_turn", new=capture_revisit):
                revisit = await http.post(turn_url, json=revisit_body)
            self.assertEqual(revisit.status_code, 200, revisit.text)
            self.assertEqual(len(revisit_results), 2)
            self.assertEqual(revisit_results[-1]["action"], "enter")
            self.assertEqual(revisit_results[-1]["status"], "completed")
            self.assertEqual(revisit_results[-1]["target_id"], tavern_id)
            self.assertEqual(revisit.json()["state"]["location"], tavern_id)
            self.assertEqual(resumed_world["locations"], locations_before_exit)
            self.assertEqual(resumed_world["locations"][tavern_id], tavern)
            self.assertEqual(
                resumed_world["locations"][tavern_id]["parent_location_id"], city_id
            )
            self.assertEqual(
                resumed_world["locations"][tavern_id]["exit_location_id"], city_id
            )
            self.assertEqual(
                resumed_world["scene_state"]["player_position"]["location_id"],
                tavern_id,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits + 1,
            )
            self.assertEqual(
                resumed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits_after_entry + 1,
            )
            revisited_save = copy.deepcopy(loaded.serialize_game_state())
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                revisited_save,
            )
            self.assertEqual(len(reloaded_store.get_campaign(campaign_id).history), 4)
            self.assertEqual(
                reloaded_store.get_turn_action(
                    campaign_id, revisit_body["action_id"]
                )["response"],
                revisit.json(),
            )

            with patch.object(
                loaded, "run_player_turn",
                side_effect=AssertionError("Revisit replay must not execute a turn"),
            ):
                replay = await http.post(turn_url, json=revisit_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), revisit.json())
            self.assertEqual(loaded.serialize_game_state(), revisited_save)
            self.assertEqual(
                reloaded_store.get_campaign(campaign_id).payload["engine_save"],
                revisited_save,
            )
            self.assertEqual(len(reloaded_store.get_campaign(campaign_id).history), 4)

        # Another fresh manager must restore the second visit from disk.
        revisited_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        revisited_manager = SessionManager(campaign_store=revisited_store)
        revisited_app = create_app(
            session_manager=revisited_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=revisited_app),
            base_url="http://testserver",
        ) as http:
            restored = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()["state"], revisit.json()["state"])
            restored_session = revisited_manager.get(
                restored.json()["session_id"]
            ).game_session
            self.assertEqual(restored_session.serialize_game_state(), revisited_save)
            restored_world = restored_session.world_state
            self.assertEqual(restored_world["location"], tavern_id)
            self.assertEqual(restored_world["locations"], locations_before_exit)
            self.assertEqual(restored_world["locations"][tavern_id], tavern)
            self.assertEqual(
                restored_world["scene_state"]["player_position"]["location_id"],
                tavern_id,
            )
            self.assertEqual(
                restored_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits + 1,
            )
            self.assertEqual(
                revisited_store.get_campaign(campaign_id).payload["engine_save"],
                revisited_save,
            )
            self.assertEqual(len(revisited_store.get_campaign(campaign_id).history), 4)

    async def test_stale_resume_keeps_corrected_disclosure_private_to_original_npc(self):
        from api.narrative_memory import build_narrative_context

        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        active_record = self.manager.get(created["session_id"])
        active_session = active_record.game_session
        location_id = active_session.world_state["location"]
        active_session.world_state["npcs"] = [
            {
                "id": "npc_private_mira",
                "name": "Mira",
                "role": "innkeeper",
                "location": location_id,
                "memory": [],
            },
            {
                "id": "npc_private_aldren",
                "name": "Aldren",
                "role": "patron",
                "location": location_id,
                "memory": [],
            },
        ]
        self.manager.save_campaign(campaign_id)
        active_url = f"/api/game/sessions/{created['session_id']}/turn"
        old_body = {
            "message": "Benim adım Arven.",
            "target_id": "npc_private_mira",
            "action_id": str(uuid.uuid4()),
        }
        old_turn = await self.http.post(active_url, json=old_body)
        self.assertEqual(old_turn.status_code, 200, old_turn.text)
        self.assertIn("Arven", old_turn.json()["narration"])
        old_saved = self.store.get_campaign(campaign_id)

        def receipt_rows():
            with closing(sqlite3.connect(self.store.path)) as connection:
                return connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id",
                    (campaign_id,),
                ).fetchall()

        stale_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        stale_manager = SessionManager(campaign_store=stale_store)
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=stale_app),
            base_url="http://testserver",
        ) as stale_http:
            resume_url = f"/api/game/campaigns/{campaign_id}/resume"
            first_resume = await stale_http.post(resume_url)
            self.assertEqual(first_resume.status_code, 200, first_resume.text)
            stale_id = first_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(stale_session, active_session)
            stale_memory = copy.deepcopy(stale_record.narrative_memory)
            self.assertEqual(stale_memory, old_saved.payload["narrative_memory"])

            corrected_body = {
                "message": "Benim adım Rowan.",
                "target_id": "npc_private_mira",
                "action_id": str(uuid.uuid4()),
            }
            corrected_turn = await self.http.post(active_url, json=corrected_body)
            self.assertEqual(corrected_turn.status_code, 200, corrected_turn.text)
            self.assertIn("Rowan", corrected_turn.json()["narration"])
            latest = self.store.get_campaign(campaign_id)
            self.assertEqual(latest.history[:-1], old_saved.history)
            self.assertNotEqual(latest.payload["narrative_memory"], stale_memory)
            self.assertEqual(stale_record.narrative_memory, stale_memory)
            prior_receipts = receipt_rows()
            self.assertEqual(len(prior_receipts), 2)

            # Refresh the older manager, rather than opening a third manager.
            refreshed = await stale_http.post(resume_url)
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertIs(stale_record.game_session, stale_session)
            self.assertEqual(refreshed.json()["history"], latest.history)
            self.assertEqual(
                stale_session.serialize_game_state(), latest.payload["engine_save"]
            )
            self.assertEqual(
                stale_record.narrative_memory, latest.payload["narrative_memory"]
            )
            after_resume = stale_store.get_campaign(campaign_id)
            self.assertEqual(after_resume.payload, latest.payload)
            self.assertEqual(after_resume.history, latest.history)
            self.assertEqual(after_resume.metadata["revision"], latest.metadata["revision"])
            self.assertEqual(receipt_rows(), prior_receipts)

            npc_a, npc_b = stale_session.world_state["npcs"]
            a_memory = copy.deepcopy(npc_a["memory"])
            self.assertEqual(npc_b["memory"], [])
            self.assertEqual(
                [entry["text"] for entry in a_memory if entry["speaker"] == "player"],
                [old_body["message"], corrected_body["message"]],
            )
            recall_body = {
                "message": "Bana adımla hitap et",
                "target_id": "npc_private_aldren",
                "action_id": str(uuid.uuid4()),
            }
            packet, _ = build_narrative_context(
                stale_record.narrative_memory,
                game.build_world_context(npc_target=npc_b, session=stale_session),
                recall_body["message"],
                {"npc_id": npc_b["id"]},
            )
            recent_players = [
                turn["player"]
                for turn in packet["relevant_continuity"]["recent_turns"]
            ]
            self.assertNotIn(old_body["message"], recent_players)
            self.assertNotIn(corrected_body["message"], recent_players)

            real_turn = stale_session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_recall(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result["action_result"]))
                return result

            with patch.object(stale_session, "run_player_turn", new=capture_recall):
                recall = await stale_http.post(
                    f"/api/game/sessions/{stale_id}/turn", json=recall_body
                )
            self.assertEqual(recall.status_code, 200, recall.text)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["npc_id"], npc_b["id"])
            self.assertEqual(results[0]["status"], "answered_from_npc_memory")
            self.assertIn("Aldren", recall.json()["narration"])
            for private_name in ("Arven", "Rowan", "Mira"):
                self.assertNotIn(private_name, recall.json()["narration"])
            self.assertEqual(npc_a["memory"], a_memory)
            self.assertFalse(any(
                "Arven" in entry["text"] or "Rowan" in entry["text"]
                for entry in npc_b["memory"]
            ))

            after_recall = stale_store.get_campaign(campaign_id)
            self.assertEqual(after_recall.history[:-1], latest.history)
            self.assertEqual(after_recall.history[-1]["player_message"], recall_body["message"])
            self.assertEqual(after_recall.history[-1]["narration"], recall.json()["narration"])
            self.assertEqual(after_recall.metadata["revision"], latest.metadata["revision"] + 1)
            final_receipts = receipt_rows()
            self.assertEqual(len(final_receipts), len(prior_receipts) + 1)
            for receipt in prior_receipts:
                self.assertIn(receipt, final_receipts)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, recall_body["action_id"])["response"],
                recall.json(),
            )
            self.assertEqual(
                after_recall.payload["narrative_memory"], stale_record.narrative_memory
            )

    async def test_stale_resume_refreshes_journal_and_conversation_memory(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        active_id = created["session_id"]
        active_record = self.manager.get(active_id)
        active_session = active_record.game_session
        location_id = active_session.world_state["location"]
        active_session.world_state["npcs"] = [
            {
                "id": "npc_resume_mira",
                "name": "Mira",
                "role": "innkeeper",
                "location": location_id,
                "memory": [],
            },
            {
                "id": "npc_resume_aldren",
                "name": "Aldren",
                "role": "patron",
                "location": location_id,
                "memory": [],
            },
        ]
        self.manager.save_campaign(campaign_id)
        active_url = f"/api/game/sessions/{active_id}/turn"
        old_body = {
            "message": "Benim adım Arven.",
            "target_id": "npc_resume_mira",
            "action_id": str(uuid.uuid4()),
        }
        old_turn = await self.http.post(active_url, json=old_body)
        self.assertEqual(old_turn.status_code, 200, old_turn.text)
        self.assertIn("Arven", old_turn.json()["narration"])
        old_saved = self.store.get_campaign(campaign_id)
        old_receipt = self.store.get_turn_action(campaign_id, old_body["action_id"])

        stale_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        stale_manager = SessionManager(campaign_store=stale_store)
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=stale_app),
            base_url="http://testserver",
        ) as stale_http:
            resume_url = f"/api/game/campaigns/{campaign_id}/resume"
            first_resume = await stale_http.post(resume_url)
            self.assertEqual(first_resume.status_code, 200, first_resume.text)
            stale_id = first_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(stale_session, active_session)
            stale_engine = copy.deepcopy(stale_session.serialize_game_state())
            stale_journal = copy.deepcopy(stale_record.journal)
            stale_memory = copy.deepcopy(stale_record.narrative_memory)
            stale_version = stale_session._campaign_persistence_version
            self.assertEqual(stale_journal, old_saved.payload["journal"])
            self.assertEqual(stale_memory, old_saved.payload["narrative_memory"])
            self.assertEqual(first_resume.json()["history"], old_saved.history)
            self.assertEqual(
                {npc["npc_id"] for npc in stale_journal["known_npcs"]},
                {"npc_resume_mira"},
            )

            new_body = {
                "message": "Benim adım Rowan.",
                "target_id": "npc_resume_mira",
                "action_id": str(uuid.uuid4()),
            }
            meet_body = {
                "message": "Adın ne?",
                "target_id": "npc_resume_aldren",
                "action_id": str(uuid.uuid4()),
            }
            new_turn = await self.http.post(active_url, json=new_body)
            meet_turn = await self.http.post(active_url, json=meet_body)
            for response in (new_turn, meet_turn):
                self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("Rowan", new_turn.json()["narration"])
            self.assertIn("Aldren", meet_turn.json()["narration"])
            latest = self.store.get_campaign(campaign_id)
            self.assertNotEqual(latest.payload["journal"], stale_journal)
            self.assertNotEqual(latest.payload["narrative_memory"], stale_memory)
            self.assertEqual(latest.history[:len(old_saved.history)], old_saved.history)
            self.assertEqual(len(latest.history), len(old_saved.history) + 2)
            receipts = {
                body["action_id"]: self.store.get_turn_action(
                    campaign_id, body["action_id"]
                )
                for body in (old_body, new_body, meet_body)
            }
            self.assertEqual(receipts[old_body["action_id"]], old_receipt)
            # Another manager's accepted turns must not silently update this cache.
            self.assertEqual(stale_session.serialize_game_state(), stale_engine)
            self.assertEqual(stale_record.journal, stale_journal)
            self.assertEqual(stale_record.narrative_memory, stale_memory)
            self.assertEqual(stale_session._campaign_persistence_version, stale_version)

            resumed = await stale_http.post(resume_url)
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertIs(stale_record.game_session, stale_session)
            self.assertEqual(
                stale_session.serialize_game_state(), latest.payload["engine_save"]
            )
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, latest.metadata["revision"]),
            )
            self.assertEqual(stale_record.journal, latest.payload["journal"])
            self.assertEqual(
                stale_record.narrative_memory, latest.payload["narrative_memory"]
            )
            self.assertEqual(resumed.json()["state"]["journal"], stale_record.journal)
            self.assertEqual(resumed.json()["history"], latest.history)
            self.assertEqual(
                {npc["npc_id"] for npc in stale_record.journal["known_npcs"]},
                {"npc_resume_mira", "npc_resume_aldren"},
            )
            refreshed = stale_store.get_campaign(campaign_id)
            self.assertEqual(refreshed.payload, latest.payload)
            self.assertEqual(refreshed.history, latest.history)
            stale_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Saved turns must replay without execution"),
                ),
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save another turn"),
                ),
            ):
                for body, response in (
                    (old_body, old_turn), (new_body, new_turn), (meet_body, meet_turn)
                ):
                    replay = await stale_http.post(stale_url, json=body)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    expected = response.json()
                    expected["session_id"] = stale_id
                    self.assertEqual(replay.json(), expected)
            self.assertEqual(stale_store.get_campaign(campaign_id), refreshed)
            self.assertEqual(stale_record.journal, latest.payload["journal"])
            self.assertEqual(
                stale_record.narrative_memory, latest.payload["narrative_memory"]
            )

            recall_body = {
                "message": "Bana adımla hitap et",
                "target_id": "npc_resume_mira",
                "action_id": str(uuid.uuid4()),
            }
            recall = await stale_http.post(stale_url, json=recall_body)
            self.assertEqual(recall.status_code, 200, recall.text)
            self.assertIn("Mira", recall.json()["narration"])
            self.assertIn("Rowan", recall.json()["narration"])
            self.assertNotIn("Arven", recall.json()["narration"])
            after_recall = stale_store.get_campaign(campaign_id)
            self.assertEqual(after_recall.history[:-1], latest.history)
            self.assertEqual(
                after_recall.history[-1]["player_message"], recall_body["message"]
            )
            self.assertEqual(after_recall.payload["journal"], stale_record.journal)
            self.assertEqual(
                after_recall.payload["narrative_memory"], stale_record.narrative_memory
            )
            for action_id, receipt in receipts.items():
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, action_id), receipt
                )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, recall_body["action_id"])[
                    "response"
                ],
                recall.json(),
            )

    async def test_reopened_city_ruler_question_does_not_answer_with_npc_identity(self):
        # A default campaign has no loaded ruler evidence. Seed only the local
        # scene, as in the living-world regression; do not script query routing.
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        world = original_session.world_state
        local_npcs = [
            {
                "id": "npc_v11_world_subject",
                "name": "Melis",
                "role": "Kent sakini",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
            {
                "id": "npc_v11_world_subject_other",
                "name": "Darian",
                "role": "Yolcu",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
        ]
        world["npcs"].extend(local_npcs)
        world["flags"]["active_npc_id"] = local_npcs[0]["id"]
        world["flags"]["active_npc_until_turn"] = world["flags"]["turn_index"] + 6
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(saved_world["npcs"], world["npcs"])
        requests = [
            {
                "message": "Bu şehrin hükümdarı kim?",
                "target_id": local_npcs[0]["id"],
                "action_id": str(uuid.uuid4()),
            },
            {
                "message": "Bu şehrin hükümdarı kim?",
                "action_id": str(uuid.uuid4()),
            },
        ]
        self.assertNotEqual(requests[0]["action_id"], requests[1]["action_id"])
        receipts = {}
        narrations = []

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            # The real engine answers this deterministically. Any model call
            # fails offline rather than supplying a scripted identity answer.
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_question_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_question_turn):
                for index, body in enumerate(requests):
                    with self.subTest(target_id=body.get("target_id")):
                        self.assertEqual(
                            session.world_state["flags"]["active_npc_id"],
                            local_npcs[0]["id"],
                        )
                        self.assertGreaterEqual(
                            session.world_state["flags"]["active_npc_until_turn"],
                            session.world_state["flags"]["turn_index"],
                        )
                        self.assertIsNone(
                            reopened_store.get_turn_action(campaign_id, body["action_id"])
                        )
                        before = reopened_store.get_campaign(campaign_id)
                        response = await http.post(
                            f"/api/game/sessions/{session_id}/turn", json=body
                        )
                        self.assertEqual(response.status_code, 200, response.text)
                        turn = response.json()
                        self.assertEqual(turn["action_id"], body["action_id"])
                        self.assertEqual(len(results), index + 1)  # Not receipt replay.
                        action = results[-1]["action_result"]
                        self.assertEqual(action["action"], "dialogue")
                        self.assertEqual(action["status"], "unverified")
                        self.assertFalse(action["success"])
                        self.assertEqual(action["state_changes"], [])
                        self.assertNotIn("npc_id", action)
                        narration = results[-1]["narration"]
                        self.assertIn("güvenilir bir doğrulamam yok", narration)
                        for npc in local_npcs:
                            self.assertNotIn(npc["name"], narration)
                        self.assertEqual(turn["narration"], narration)
                        narrations.append(narration)

                        persisted = reopened_store.get_campaign(campaign_id)
                        self.assertEqual(
                            persisted.payload["engine_save"], session.serialize_game_state()
                        )
                        self.assertEqual(persisted.payload["journal"], record.journal)
                        persisted_world = persisted.payload["engine_save"]["world_state"]
                        for key in (
                            "location", "locations", "npcs", "shops", "features",
                            "doors", "containers", "quests", "quest_offers", "inventory",
                        ):
                            self.assertEqual(persisted_world.get(key), saved_world.get(key), key)
                        self.assertEqual(
                            persisted_world["flags"]["turn_index"],
                            saved_world["flags"]["turn_index"] + index + 1,
                        )
                        self.assertEqual(persisted.history[:-1], before.history)
                        self.assertEqual(len(persisted.history), len(before.history) + 1)
                        self.assertEqual(
                            persisted.history[-1]["player_message"], body["message"]
                        )
                        self.assertEqual(persisted.history[-1]["narration"], narration)
                        receipt = reopened_store.get_turn_action(campaign_id, body["action_id"])
                        self.assertEqual(receipt["response"], turn)
                        receipts[body["action_id"]] = copy.deepcopy(receipt)

        # Reopen again without sending either action: both accepted questions,
        # their narration and the unchanged local identities must be durable.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        _, final_record, _, final_history, _ = final_manager.resume_campaign(campaign_id)
        self.assertIsNot(final_record.game_session, session)
        self.assertEqual(
            final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
        )
        self.assertEqual(final_record.journal, persisted.payload["journal"])
        self.assertEqual(final_history, persisted.history)
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
        self.assertEqual(
            [entry["player_message"] for entry in final_history[-2:]],
            [body["message"] for body in requests],
        )
        self.assertEqual([entry["narration"] for entry in final_history[-2:]], narrations)
        for action_id, receipt in receipts.items():
            self.assertEqual(final_store.get_turn_action(campaign_id, action_id), receipt)
            self.assertEqual(final_manager.get_turn_action(final_record, action_id), receipt)

    async def test_dead_lore_question_cannot_change_saved_campaign(self):
        question = "Bu şehrin hükümdarı kim?"
        city_id = "fr:city:neverwinter"
        npc_id = "npc_dead_ruler_local"
        for target_id in (None, npc_id):
            with self.subTest(target_id=target_id):
                created_response = await self.http.post(
                    "/api/game/campaigns",
                    json={
                        "death_mode": "PERMADEATH",
                        "campaign_start": {
                            "setting_id": "forgotten_realms",
                            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                            "region_id": "fr:region:the_north",
                            "starting_location_id": city_id,
                        },
                    },
                )
                self.assertEqual(created_response.status_code, 200, created_response.text)
                created = created_response.json()
                campaign_id = created["campaign_id"]
                record = self.manager.get(created["session_id"])
                session = record.game_session
                session.world_state["npcs"].append({
                    "id": npc_id,
                    "name": "Elara",
                    "role": "Guide",
                    "location": city_id,
                    "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                    "memory": [],
                    "knowledge": [],
                })
                # Seed terminal state directly: death execution and reopening
                # have separate coverage; this test owns rejected lore turns.
                session.character.update(current_hp=0, max_hp=10)
                session.world_state["player_combat_status"] = "dead"
                session.world_state["death_state"]["dead"] = True
                self.assertFalse(session.ensure_combat_state()["active"])
                saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
                self.assertEqual(saved.status_code, 200, saved.text)
                before_campaign = copy.deepcopy(self.store.get_campaign(campaign_id))
                before_save = copy.deepcopy(session.serialize_game_state())
                before_messages = copy.deepcopy(session.messages)
                before_rng = session.rng.getstate()
                before_metadata = copy.deepcopy(session.world_metadata)
                before_journal = copy.deepcopy(record.journal)
                before_memory = copy.deepcopy(record.narrative_memory)
                before_lore = copy.deepcopy(record.lore_authority.to_dict())
                before_context = copy.deepcopy(session.lore_authority_context)
                before_receipts = copy.deepcopy(record.turn_action_receipts)
                self.assertEqual(before_campaign.payload["engine_save"], before_save)
                self.assertEqual(before_campaign.payload["lore_authority"], before_lore)
                self.assertEqual(before_lore["binding_status"], "BOUND")
                action_id = str(uuid.uuid4())
                body = {"message": question, "action_id": action_id}
                if target_id is not None:
                    body["target_id"] = target_id
                rejections = []
                supported_answers = []
                real_turn = session.run_player_turn

                @wraps(real_turn)
                def capture_rejected_turn(*args, **kwargs):
                    supported_answers.append(game._supported_lore_question_response(
                        question, session.lore_authority_context, session.world_state
                    ))
                    try:
                        return real_turn(*args, **kwargs)
                    except ValueError as error:
                        rejections.append(str(error))
                        raise

                with (
                    patch.object(session, "run_player_turn", new=capture_rejected_turn),
                    patch.object(
                        game, "parse_player_intent",
                        side_effect=AssertionError("Dead lore turns must not parse intent"),
                    ) as intent_model,
                    patch.object(
                        game, "ask_dungeon_master",
                        side_effect=AssertionError("Dead lore turns must not narrate"),
                    ) as narration_model,
                ):
                    response = await self.http.post(
                        f"/api/game/sessions/{created['session_id']}/turn", json=body
                    )

                self.assertEqual(response.status_code, 500, response.text)
                self.assertEqual(response.json()["detail"], {
                    "code": "engine_error",
                    "message": "The game turn could not be completed.",
                })
                self.assertEqual(rejections, ["Ölü karakter eylem gerçekleştiremez."])
                self.assertEqual(
                    supported_answers,
                    ["Neverwinter kentinin güncel Lordu Dagult Neverember."],
                )
                intent_model.assert_not_called()
                narration_model.assert_not_called()
                self.assertEqual(session.serialize_game_state(), before_save)
                self.assertEqual(session.messages, before_messages)
                self.assertEqual(session.rng.getstate(), before_rng)
                self.assertEqual(session.world_metadata, before_metadata)
                self.assertEqual(record.journal, before_journal)
                self.assertEqual(record.narrative_memory, before_memory)
                self.assertEqual(record.lore_authority.to_dict(), before_lore)
                self.assertEqual(session.lore_authority_context, before_context)
                self.assertEqual(record.turn_action_receipts, before_receipts)
                self.assertNotIn(action_id, record.turn_action_receipts)
                self.assertIsNone(self.manager.get_turn_action(record, action_id))
                self.assertIsNone(self.store.get_turn_action(campaign_id, action_id))
                self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)

    async def test_partial_death_markers_block_saved_city_ruler_question(self):
        question = "Bu şehrin hükümdarı kim?"
        city_id = "fr:city:neverwinter"
        npc_id = "npc_partial_dead_ruler_local"
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for death_marker in ("player_combat_status", "death_state"):
                for target_id in (None, npc_id):
                    with self.subTest(
                        mode=mode, death_marker=death_marker, target_id=target_id
                    ):
                        created_response = await self.http.post(
                            "/api/game/campaigns",
                            json={
                                "death_mode": mode,
                                "campaign_start": {
                                    "setting_id": "forgotten_realms",
                                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                                    "region_id": "fr:region:the_north",
                                    "starting_location_id": city_id,
                                },
                            },
                        )
                        self.assertEqual(
                            created_response.status_code, 200, created_response.text
                        )
                        created = created_response.json()
                        campaign_id = created["campaign_id"]
                        record = self.manager.get(created["session_id"])
                        session = record.game_session
                        session.world_state["npcs"].append({
                            "id": npc_id,
                            "name": "Elara",
                            "role": "Guide",
                            "location": city_id,
                            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                            "memory": [],
                            "knowledge": [],
                        })
                        session.character.update(current_hp=10, max_hp=10)
                        # Prepare combat before introducing conflicting markers;
                        # ensure_combat_state also validates death state.
                        self.assertFalse(session.ensure_combat_state()["active"])
                        session.world_state["player_combat_status"] = (
                            "dead" if death_marker == "player_combat_status" else "active"
                        )
                        session.world_state["death_state"]["dead"] = (
                            death_marker == "death_state"
                        )
                        session.world_state["death_state"]["terminal"] = False
                        saved = await self.http.post(
                            f"/api/game/campaigns/{campaign_id}/save"
                        )
                        self.assertEqual(saved.status_code, 200, saved.text)
                        before_campaign = copy.deepcopy(self.store.get_campaign(campaign_id))
                        before_save = copy.deepcopy(session.serialize_game_state())
                        before_messages = copy.deepcopy(session.messages)
                        before_rng = session.rng.getstate()
                        before_metadata = copy.deepcopy(session.world_metadata)
                        before_journal = copy.deepcopy(record.journal)
                        before_memory = copy.deepcopy(record.narrative_memory)
                        before_lore = copy.deepcopy(record.lore_authority.to_dict())
                        before_context = copy.deepcopy(session.lore_authority_context)
                        before_receipts = copy.deepcopy(record.turn_action_receipts)
                        self.assertEqual(before_campaign.payload["engine_save"], before_save)
                        self.assertEqual(before_campaign.payload["lore_authority"], before_lore)
                        self.assertEqual(before_lore["binding_status"], "BOUND")
                        self.assertEqual(before_save["player"]["current_hp"], 10)
                        saved_world = before_save["world_state"]
                        self.assertEqual(saved_world["death_state"]["mode"], mode)
                        self.assertFalse(saved_world["death_state"]["terminal"])
                        self.assertNotEqual(
                            saved_world["player_combat_status"] == "dead",
                            saved_world["death_state"]["dead"],
                        )
                        action_id = str(uuid.uuid4())
                        body = {"message": question, "action_id": action_id}
                        if target_id is not None:
                            body["target_id"] = target_id
                        rejections = []
                        # This positive-HP inconsistency is rejected by the
                        # real planning death gate, before turn dispatch. Prove
                        # that it is otherwise a supported lore question.
                        lore_context = main_module._lore_context_for_turn(
                            record, session, question, target_id
                        )
                        self.assertEqual(
                            game._supported_lore_question_response(
                                question, lore_context, session.world_state
                            ),
                            "Neverwinter kentinin güncel Lordu Dagult Neverember.",
                        )
                        before_runtime = session._capture_runtime_snapshot()
                        world_reference = session.world_state
                        character_reference = session.character
                        messages_reference = session.messages
                        narrations_reference = session.recent_dm_narrations
                        # External saves must still reject this inconsistent
                        # state. Only an internal capture may restore it.
                        invalid_path = Path(self.temporary_directory.name) / "invalid-death.json"
                        invalid_path.write_text(json.dumps(before_save), encoding="utf-8")
                        with self.assertRaises(ValueError):
                            session.load_game(invalid_path)
                        self.assertEqual(session._capture_runtime_snapshot(), before_runtime)
                        real_plan = session.plan_living_world_turn

                        @wraps(real_plan)
                        def capture_rejected_plan(*args, **kwargs):
                            # Speculative setup can change state before the
                            # real positive-HP death gate rejects planning.
                            session.world_state["flags"]["speculative_setup"] = True
                            session.world_state["npcs"][0]["memory"].append("uncommitted")
                            session.character["current_hp"] = 9
                            session.character["uncommitted_detail"] = {"nested": [1]}
                            session.messages.append({"role": "user", "content": "uncommitted"})
                            session.recent_dm_narrations.append("uncommitted")
                            session.rng.random()
                            session.world_metadata = {}
                            record.journal.clear()
                            record.narrative_memory.clear()
                            record.lore_authority = type(record.lore_authority).legacy_unbound()
                            session.lore_authority_context = {"uncommitted": True}
                            self.assertNotEqual(session._capture_runtime_snapshot(), before_runtime)
                            try:
                                return real_plan(*args, **kwargs)
                            except ValueError as error:
                                rejections.append(str(error))
                                raise

                        with (
                            patch.object(
                                session, "plan_living_world_turn", new=capture_rejected_plan
                            ),
                            patch.object(
                                session, "run_player_turn",
                                side_effect=AssertionError(
                                    "Invalid death state must block turn dispatch"
                                ),
                            ) as turn_dispatch,
                            patch.object(
                                game, "parse_player_intent",
                                side_effect=AssertionError(
                                    "Partial death markers must block intent parsing"
                                ),
                            ) as intent_model,
                            patch.object(
                                game, "ask_dungeon_master",
                                side_effect=AssertionError(
                                    "Partial death markers must block narration"
                                ),
                            ) as narration_model,
                            patch.object(main_module._logger, "critical") as rollback_failed,
                        ):
                            response = await self.http.post(
                                f"/api/game/sessions/{created['session_id']}/turn", json=body
                            )

                        self.assertEqual(response.status_code, 500, response.text)
                        self.assertEqual(response.json()["detail"], {
                            "code": "engine_error",
                            "message": "The game turn could not be completed.",
                        })
                        # Positive HP rejects during real death-state validation,
                        # before the zero-HP dead-action gate or any lore answer.
                        self.assertEqual(
                            rejections, ["Dead player state cannot have positive hit points."]
                        )
                        turn_dispatch.assert_not_called()
                        intent_model.assert_not_called()
                        narration_model.assert_not_called()
                        rollback_failed.assert_not_called()
                        self.assertEqual(session._capture_runtime_snapshot(), before_runtime)
                        self.assertIs(session.world_state, world_reference)
                        self.assertIs(session.character, character_reference)
                        self.assertIs(session.messages, messages_reference)
                        self.assertIs(session.recent_dm_narrations, narrations_reference)
                        self.assertEqual(session.serialize_game_state(), before_save)
                        self.assertEqual(session.messages, before_messages)
                        self.assertEqual(session.rng.getstate(), before_rng)
                        self.assertEqual(session.world_metadata, before_metadata)
                        self.assertEqual(record.journal, before_journal)
                        self.assertEqual(record.narrative_memory, before_memory)
                        self.assertEqual(record.lore_authority.to_dict(), before_lore)
                        self.assertEqual(session.lore_authority_context, before_context)
                        self.assertEqual(record.turn_action_receipts, before_receipts)
                        self.assertNotIn(action_id, record.turn_action_receipts)
                        self.assertIsNone(self.manager.get_turn_action(record, action_id))
                        self.assertIsNone(self.store.get_turn_action(campaign_id, action_id))
                        self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)

    async def test_stable_unconscious_lore_question_preserves_saved_pending_recovery(self):
        question = "Bu şehrin hükümdarı kim?"
        city_id = "fr:city:neverwinter"
        npc_id = "npc_stable_ruler_local"
        for target_id in (None, npc_id):
            with self.subTest(target_id=target_id):
                created_response = await self.http.post(
                    "/api/game/campaigns",
                    json={
                        "death_mode": "PERMADEATH",
                        "campaign_start": {
                            "setting_id": "forgotten_realms",
                            "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                            "region_id": "fr:region:the_north",
                            "starting_location_id": city_id,
                        },
                    },
                )
                self.assertEqual(created_response.status_code, 200, created_response.text)
                created = created_response.json()
                campaign_id = created["campaign_id"]
                record = self.manager.get(created["session_id"])
                session = record.game_session
                session.world_state["npcs"].append({
                    "id": npc_id,
                    "name": "Melis",
                    "role": "Kent sakini",
                    "location": city_id,
                    "reality_layer": "PROCEDURAL_LOCAL_FICTION",
                    "memory": [],
                    "knowledge": [],
                })
                session.character.update(current_hp=20, max_hp=20)
                # Match the Death owner's stable scheduling fixture: schedule
                # through real damage/stabilization, then save partway to waking.
                campaign_time.initialize(session.world_state)
                session.advance_campaign_time(137, "wait")
                session._apply_player_damage(20, took_damage=True)
                with patch.object(session.rng, "randint", return_value=2) as die:
                    session.stabilize_player()
                die.assert_called_once_with(1, 4)
                session.advance_campaign_time(600, "wait")

                recovery = {"hours": 2, "at": 137 + 7200}
                self.assertEqual(session.character["current_hp"], 0)
                self.assertEqual(session.world_state["player_combat_status"], "unconscious")
                self.assertTrue(session.ensure_death_state()["stable"])
                self.assertFalse(session.ensure_death_state()["dead"])
                self.assertEqual(session.ensure_death_state()["recovery"], recovery)
                self.assertFalse(session.ensure_combat_state()["active"])
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"], 737
                )
                saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
                self.assertEqual(saved.status_code, 200, saved.text)
                before_campaign = copy.deepcopy(self.store.get_campaign(campaign_id))
                before_save = copy.deepcopy(session.serialize_game_state())
                before_messages = copy.deepcopy(session.messages)
                before_rng = session.rng.getstate()
                before_metadata = copy.deepcopy(session.world_metadata)
                before_journal = copy.deepcopy(record.journal)
                before_memory = copy.deepcopy(record.narrative_memory)
                before_lore = copy.deepcopy(record.lore_authority.to_dict())
                before_context = copy.deepcopy(session.lore_authority_context)
                before_receipts = copy.deepcopy(record.turn_action_receipts)
                before_clock = copy.deepcopy(session.world_state["campaign_time"])
                self.assertEqual(before_campaign.payload["engine_save"], before_save)
                self.assertEqual(before_campaign.payload["lore_authority"], before_lore)
                self.assertEqual(before_lore["binding_status"], "BOUND")
                action_id = str(uuid.uuid4())
                body = {"message": question, "action_id": action_id}
                if target_id is not None:
                    body["target_id"] = target_id
                rejections = []
                supported_answers = []
                real_turn = session.run_player_turn

                @wraps(real_turn)
                def capture_rejected_turn(*args, **kwargs):
                    supported_answers.append(game._supported_lore_question_response(
                        question, session.lore_authority_context, session.world_state
                    ))
                    try:
                        return real_turn(*args, **kwargs)
                    except ValueError as error:
                        rejections.append(str(error))
                        raise

                with (
                    patch.object(session, "run_player_turn", new=capture_rejected_turn),
                    patch.object(
                        game, "parse_player_intent",
                        side_effect=AssertionError("Rejected lore must not parse intent"),
                    ) as intent_model,
                    patch.object(
                        game, "ask_dungeon_master",
                        side_effect=AssertionError("Rejected lore must not narrate"),
                    ) as narration_model,
                ):
                    response = await self.http.post(
                        f"/api/game/sessions/{created['session_id']}/turn", json=body
                    )

                self.assertEqual(response.status_code, 500, response.text)
                self.assertEqual(response.json()["detail"], {
                    "code": "engine_error",
                    "message": "The game turn could not be completed.",
                })
                self.assertEqual(rejections, ["Bilinçsiz karakter eylem gerçekleştiremez."])
                self.assertEqual(
                    supported_answers,
                    ["Neverwinter kentinin güncel Lordu Dagult Neverember."],
                )
                intent_model.assert_not_called()
                narration_model.assert_not_called()
                self.assertEqual(session.serialize_game_state(), before_save)
                self.assertEqual(session.messages, before_messages)
                self.assertEqual(session.rng.getstate(), before_rng)
                self.assertEqual(session.world_metadata, before_metadata)
                self.assertEqual(record.journal, before_journal)
                self.assertEqual(record.narrative_memory, before_memory)
                self.assertEqual(record.lore_authority.to_dict(), before_lore)
                self.assertEqual(session.lore_authority_context, before_context)
                self.assertEqual(session.world_state["death_state"]["recovery"], recovery)
                self.assertEqual(session.world_state["campaign_time"], before_clock)
                self.assertEqual(record.turn_action_receipts, before_receipts)
                self.assertNotIn(action_id, record.turn_action_receipts)
                self.assertIsNone(self.manager.get_turn_action(record, action_id))
                self.assertIsNone(self.store.get_turn_action(campaign_id, action_id))
                self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)

    async def test_reopened_verified_city_ruler_answer_preserves_lore_and_history(self):
        # Reuse the installed, reviewed pack from the lore-engine regression;
        # no test-authored ruler claim or production canon change is needed.
        city_id = "fr:city:neverwinter"
        ruler_fact_id = "fr:fact:dagult_neverember_current_lord"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        original_record = self.manager.get(created["session_id"])
        original_session = original_record.game_session
        world = original_session.world_state
        local_npcs = [
            {
                "id": "npc_verified_ruler_local",
                "name": "Melis",
                "role": "Kent sakini",
                "location": city_id,
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
            {
                "id": "npc_verified_ruler_other",
                "name": "Darian",
                "role": "Yolcu",
                "location": city_id,
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
        ]
        world["npcs"].extend(local_npcs)
        world["flags"]["active_npc_id"] = local_npcs[0]["id"]
        world["flags"]["active_npc_until_turn"] = world["flags"]["turn_index"] + 6
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        saved_lore = committed.payload["lore_authority"]
        self.assertEqual(saved_world["location"], city_id)
        self.assertEqual(saved_world["npcs"], world["npcs"])
        self.assertEqual(saved_lore, original_record.lore_authority.to_dict())
        self.assertEqual(saved_lore["binding_status"], "BOUND")
        self.assertEqual(saved_lore["current_location_entity_id"], city_id)
        self.assertNotIn("lore_authority", committed.payload["engine_save"])
        requests = [
            {
                "message": "Bu şehrin hükümdarı kim?",
                "target_id": local_npcs[0]["id"],
                "action_id": str(uuid.uuid4()),
            },
            {
                "message": "Bu şehrin hükümdarı kim?",
                "action_id": str(uuid.uuid4()),
            },
        ]
        self.assertNotEqual(requests[0]["action_id"], requests[1]["action_id"])
        receipts = {}
        narrations = []
        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            # Unexpected model calls fail offline rather than inventing lore.
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(record.lore_authority.to_dict(), saved_lore)
            self.assertEqual(resumed.json()["history"], committed.history)
            real_turn = session.run_player_turn
            results = []
            contexts = []

            @wraps(real_turn)
            def capture_question_turn(*args, **kwargs):
                contexts.append(copy.deepcopy(session.lore_authority_context))
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_question_turn):
                for index, body in enumerate(requests):
                    with self.subTest(target_id=body.get("target_id")):
                        self.assertEqual(
                            session.world_state["flags"]["active_npc_id"],
                            local_npcs[0]["id"],
                        )
                        self.assertGreaterEqual(
                            session.world_state["flags"]["active_npc_until_turn"],
                            session.world_state["flags"]["turn_index"],
                        )
                        self.assertIsNone(
                            reopened_store.get_turn_action(campaign_id, body["action_id"])
                        )
                        before = reopened_store.get_campaign(campaign_id)
                        response = await http.post(
                            f"/api/game/sessions/{session_id}/turn", json=body
                        )
                        self.assertEqual(response.status_code, 200, response.text)
                        turn = response.json()
                        self.assertEqual(turn["action_id"], body["action_id"])
                        self.assertEqual(len(results), index + 1)  # Not receipt replay.
                        self.assertIn(
                            ruler_fact_id, contexts[-1]["diagnostics"]["selected_fact_ids"]
                        )
                        action = results[-1]["action_result"]
                        self.assertEqual(action["action"], "dialogue")
                        self.assertEqual(action["status"], "answered_from_loaded_lore")
                        self.assertTrue(action["success"])
                        self.assertEqual(action["state_changes"], [])
                        self.assertNotIn("npc_id", action)
                        self.assertEqual(
                            results[-1]["_engine_event_evidence"]["telemetry"]["total_model_calls"],
                            0,
                        )
                        narration = results[-1]["narration"]
                        self.assertEqual(
                            narration, "Neverwinter kentinin güncel Lordu Dagult Neverember."
                        )
                        self.assertNotIn("güvenilir bir doğrulamam yok", narration)
                        for npc in local_npcs:
                            self.assertNotIn(npc["name"], narration)
                        self.assertEqual(turn["narration"], narration)
                        narrations.append(narration)

                        persisted = reopened_store.get_campaign(campaign_id)
                        self.assertEqual(
                            persisted.payload["engine_save"], session.serialize_game_state()
                        )
                        self.assertEqual(persisted.payload["journal"], record.journal)
                        self.assertEqual(
                            persisted.payload["lore_authority"], record.lore_authority.to_dict()
                        )
                        for key in (
                            "binding_status", "setting_profile", "world_id", "epoch_id",
                            "region_id", "current_location_entity_id",
                        ):
                            self.assertEqual(persisted.payload["lore_authority"][key], saved_lore[key])
                        persisted_world = persisted.payload["engine_save"]["world_state"]
                        for key in (
                            "location", "locations", "npcs", "shops", "features",
                            "doors", "containers", "quests", "quest_offers", "inventory",
                        ):
                            self.assertEqual(persisted_world.get(key), saved_world.get(key), key)
                        self.assertEqual(
                            persisted_world["flags"]["turn_index"],
                            saved_world["flags"]["turn_index"] + index + 1,
                        )
                        self.assertEqual(persisted.history[:-1], before.history)
                        self.assertEqual(len(persisted.history), len(before.history) + 1)
                        self.assertEqual(persisted.history[-1]["player_message"], body["message"])
                        self.assertEqual(persisted.history[-1]["narration"], narration)
                        receipt = reopened_store.get_turn_action(campaign_id, body["action_id"])
                        self.assertEqual(receipt["response"], turn)
                        receipts[body["action_id"]] = copy.deepcopy(receipt)

        # A second fresh HTTP resume must restore both accepted answers and
        # their lore binding without issuing either action again.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            reloaded = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        final_record = final_manager.get(reloaded.json()["session_id"])
        self.assertIsNot(final_record.game_session, session)
        self.assertEqual(
            final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
        )
        self.assertEqual(final_record.lore_authority.to_dict(), persisted.payload["lore_authority"])
        self.assertEqual(final_record.journal, persisted.payload["journal"])
        self.assertEqual(reloaded.json()["history"], persisted.history)
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
        self.assertEqual(
            [entry["player_message"] for entry in reloaded.json()["history"][-2:]],
            [body["message"] for body in requests],
        )
        self.assertEqual(
            [entry["narration"] for entry in reloaded.json()["history"][-2:]], narrations
        )
        for action_id, receipt in receipts.items():
            self.assertEqual(final_store.get_turn_action(campaign_id, action_id), receipt)
            self.assertEqual(final_manager.get_turn_action(final_record, action_id), receipt)

    async def test_selected_npc_identity_query_is_deterministic(self):
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "Selected NPC identity target regression",
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": "fr:city:neverwinter",
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        session = self.manager.get(created["session_id"]).game_session

        look_response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Etrafıma bakıyorum."},
        )
        self.assertEqual(look_response.status_code, 200, look_response.text)
        npc = session.world_state["npcs"][0]

        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Adın ne?", "target_id": npc["id"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        turn = response.json()
        self.assertIn(npc["name"], turn["narration"])
        self.assertIn(npc["role"], turn["narration"])

    async def test_create_list_detail_resume_and_safe_metadata(self):
        created = await self.create_campaign()
        self.assertTrue(created["campaign_id"])
        self.assertTrue(created["session_id"])
        self.assertEqual(created["history"], [])
        self.assertEqual(
            set(created["state"]["journal"]),
            {
                "schema_version",
                "discovered_locations",
                "known_npcs",
                "notable_events",
                "quests",
            },
        )
        self.assertEqual(created["state"]["journal"]["quests"], [])

        campaign_id = created["campaign_id"]
        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["campaign_id"], campaign_id)
        self.assertNotIn("engine_hash", listed.text)
        self.assertNotIn("payload_json", listed.text)
        self.assertNotIn("world_state", listed.text)

        detail = await self.http.get(f"/api/game/campaigns/{campaign_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["state"], created["state"])
        self.assertEqual(detail.json()["campaign"]["name"], created["name"])

        resumed = await self.http.post(
            f"/api/game/campaigns/{campaign_id}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["campaign_id"], campaign_id)
        self.assertEqual(resumed.json()["state"], created["state"])

    async def test_character_options_and_custom_creation_are_engine_canonical(self):
        options = await self.http.get("/api/game/character-options")
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.json(), {"races": game.RACES, "classes": game.CLASSES})

        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "character": {
                    "mode": "custom",
                    "name": "  Arven  ",
                    "race": "Elf",
                    "class": "Wizard",
                    "background": "Sage",
                    "alignment": "Neutral Good",
                    "ability_score_method": "standard_array",
                    "ability_scores": {
                        "intelligence": 15,
                        "dexterity": 14,
                        "constitution": 13,
                        "wisdom": 12,
                        "charisma": 10,
                        "strength": 8,
                    },
                    "background_ability_bonuses": {
                        "intelligence": 2,
                        "constitution": 1,
                    },
                    "proficient_skills": [
                        "Arcana",
                        "History",
                        "Investigation",
                        "Insight",
                    ],
                    "languages": ["Common", "Dwarvish", "Elvish"],
                    "background_equipment_option": "A",
                    "equipment_package": "A",
                    "cantrips": ["Fire Bolt", "Mage Hand", "Light"],
                    "spells": [
                        "Magic Missile",
                        "Shield",
                        "Mage Armor",
                        "Detect Magic",
                        "Thunderwave",
                        "Sleep",
                    ],
                }
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        character = created["state"]["character"]
        self.assertEqual(
            (character["name"], character["race"], character["class"]),
            ("Arven", "Elf", "Wizard"),
        )

        session = self.manager.get(created["session_id"]).game_session
        engine_character = session.character
        self.assertEqual(engine_character["level"], 1)
        self.assertEqual(engine_character["proficiency_bonus"], 2)
        self.assertEqual(engine_character["current_hp"], engine_character["max_hp"])
        self.assertEqual(
            engine_character["max_hp"],
            session.calculate_hp(
                "Wizard", session.get_modifier(engine_character["constitution"])
            ),
        )
        self.assertEqual(
            engine_character["armor_class"],
            session.calculate_ac(
                "Wizard",
                session.get_modifier(engine_character["dexterity"]),
                session.get_modifier(engine_character["constitution"]),
                session.get_modifier(engine_character["wisdom"]),
            ),
        )
        self.assertTrue(
            all(
                3 <= engine_character[ability] <= 18
                for ability in (
                    "strength",
                    "dexterity",
                    "constitution",
                    "intelligence",
                    "wisdom",
                    "charisma",
                )
            )
        )
        self.assertEqual(len(engine_character["proficient_skills"]), 4)
        self.assertTrue(
            set(engine_character["proficient_skills"])
            <= set(game.CLASS_SKILL_OPTIONS["Wizard"])
        )
        for ability in (
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "wisdom",
            "charisma",
        ):
            self.assertEqual(character[ability], engine_character[ability])

        restarted_manager = SessionManager(campaign_store=self.store)
        restarted_app = create_app(
            session_manager=restarted_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted_app),
            base_url="http://testserver",
        ) as restarted_http:
            resumed = await restarted_http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"], created["state"])

    async def test_random_creation_and_invalid_character_choices(self):
        random_response = await self.http.post(
            "/api/game/campaigns",
            json={"character": {"mode": "random"}},
        )
        self.assertEqual(random_response.status_code, 200, random_response.text)
        random_character = random_response.json()["state"]["character"]
        self.assertIn(random_character["name"], game.RANDOM_NAMES)
        self.assertIn(random_character["race"], game.RACES)
        self.assertIn(random_character["class"], game.CLASSES)
        valid_skills = game.CLASS_SKILL_OPTIONS[random_character["class"]]
        expected_class_skill_count = 4 if random_character["class"] == "Rogue" else 2
        species_bonus_skills = set(random_character["species_bonus_skills"])
        expected_species_skill_count = SPECIES_DEFINITIONS[
            random_character["race"]
        ].get("skill_bonus_count", 0)
        expected_skill_count = (
            expected_class_skill_count + expected_species_skill_count
        )
        self.assertEqual(len(random_character["proficient_skills"]), expected_skill_count)
        self.assertEqual(len(species_bonus_skills), expected_species_skill_count)
        self.assertTrue(
            species_bonus_skills <= set(random_character["proficient_skills"])
        )
        self.assertTrue(
            set(random_character["proficient_skills"])
            <= set(valid_skills) | species_bonus_skills
        )

        invalid_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Not a supported race",
                    "class": "Wizard",
                }
            },
        )
        self.assertEqual(invalid_response.status_code, 422)
        self.assertEqual(
            invalid_response.json()["detail"]["code"],
            "invalid_character",
        )

        forged_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Elf",
                    "class": "Wizard",
                    "max_hp": 999,
                }
            },
        )
        self.assertEqual(forged_response.status_code, 422)

        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(len(listed.json()), 1)

    async def test_character_creation_rejects_empty_malformed_and_authoritative_fields(self):
        invalid_requests = [
            {
                "character": {
                    "mode": "custom",
                    "name": "   ",
                    "race": "Human",
                    "class": "Fighter",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "A" * 41,
                    "race": "Human",
                    "class": "Fighter",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": 27,
                    "race": "Human",
                    "class": "Fighter",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Human",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Human",
                    "class": "Unsupported Class",
                }
            },
            {
                "character": {
                    "mode": "random",
                    "name": "Client-selected",
                }
            },
            {
                "character": {
                    "mode": "custom",
                    "name": "Arven",
                    "race": "Human",
                    "class": "Fighter",
                    "current_hp": 1,
                    "max_hp": 999,
                    "armor_class": 99,
                    "inventory": ["Forged item"],
                    "combat": {"active": True},
                    "level": 20,
                    "proficiency_bonus": 99,
                    "strength": 30,
                }
            },
        ]
        for body in invalid_requests:
            with self.subTest(body=body):
                response = await self.http.post("/api/game/campaigns", json=body)
                self.assertEqual(response.status_code, 422, response.text)

        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(listed.json(), [])

    async def test_campaign_creation_ids_and_sessions_are_isolated(self):
        async def create(name, race, character_class):
            if character_class == "Wizard":
                char_payload = {
                    "mode": "custom",
                    "name": name,
                    "race": race,
                    "class": character_class,
                    "background": "Sage",
                    "alignment": "Neutral Good",
                    "ability_score_method": "standard_array",
                    "ability_scores": {
                        "intelligence": 15,
                        "dexterity": 14,
                        "constitution": 13,
                        "wisdom": 12,
                        "charisma": 10,
                        "strength": 8,
                    },
                    "background_ability_bonuses": {
                        "intelligence": 2,
                        "constitution": 1,
                    },
                    "proficient_skills": [
                        "Arcana",
                        "History",
                        "Investigation",
                        "Insight",
                    ],
                    "languages": ["Common", "Dwarvish", "Elvish"],
                    "background_equipment_option": "A",
                    "equipment_package": "A",
                    "cantrips": ["Fire Bolt", "Mage Hand", "Light"],
                    "spells": [
                        "Magic Missile",
                        "Shield",
                        "Mage Armor",
                        "Detect Magic",
                        "Thunderwave",
                        "Sleep",
                    ],
                }
            else:
                char_payload = {
                    "mode": "custom",
                    "name": name,
                    "race": race,
                    "class": character_class,
                    "background": "Acolyte",
                    "alignment": "Lawful Good",
                    "ability_score_method": "standard_array",
                    "ability_scores": {
                        "wisdom": 15,
                        "constitution": 14,
                        "strength": 13,
                        "dexterity": 12,
                        "intelligence": 10,
                        "charisma": 8,
                    },
                    "background_ability_bonuses": {
                        "wisdom": 2,
                        "intelligence": 1,
                    },
                    "proficient_skills": [
                        "Insight",
                        "Religion",
                        "History",
                        "Medicine",
                    ],
                    "languages": ["Common", "Dwarvish", "Elvish"],
                    "background_equipment_option": "A",
                    "equipment_package": "A",
                    "cantrips": ["Light", "Sacred Flame", "Thaumaturgy"],
                    "spells": ["Bless", "Cure Wounds"],
                }
            response = await self.http.post(
                "/api/game/campaigns",
                json={"character": char_payload},
            )
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        first = await create("Arven", "Elf", "Wizard")
        second = await create("Mira", "Dwarf", "Cleric")
        self.assertNotEqual(first["campaign_id"], second["campaign_id"])
        self.assertNotEqual(first["session_id"], second["session_id"])

        first_session = self.manager.get(first["session_id"]).game_session
        second_session = self.manager.get(second["session_id"]).game_session
        second_before = copy.deepcopy(second_session.serialize_game_state())
        first_session.character["name"] = "Changed only in the first session"
        first_session.world_state["inventory"].append("Isolation check")
        self.assertEqual(second_session.serialize_game_state(), second_before)

        for response in (first, second):
            self.assertNotIn("OLLAMA_PROXY_TOKEN", str(response))
            self.assertNotIn("SESSION_SECRET", str(response))
            self.assertNotIn("Authorization", str(response))

    async def test_blank_target_id_is_rejected(self):
        created = await self.create_campaign()
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Bandit'e saldırıyorum.", "target_id": "   "},
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_attack_turn_returns_only_safe_structured_combat_result(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        target = {
            "id": "npc_bandit",
            "name": "Bandit",
            "role": "bandit",
            "location": session.world_state["location"],
            "max_hp": 14,
            "current_hp": 7,
            "armor_class": 12,
            # Serializer fixture only: satisfy authoritative range validation.
            # This injected distance is not native production encounter evidence.
            "distance_ft": 5,
            "combat_status": "active",
            "memory": [],
        }
        session.world_state["npcs"].append(target)
        with patch.object(session.rng, "randint", side_effect=[20, 1]):
            session.start_combat(target)
        received_target_ids = []

        def attack_turn(_message, *, target_id=None):
            received_target_ids.append(target_id)
            return {
                "narration": "The blade catches the bandit.",
                "action_result": {
                    "action": "attack",
                    "status": "resolved",
                    "success": True,
                    "outcome": "critical_hit",
                    "actor": "player",
                    "target": "npc_bandit",
                    "target_id": "npc_bandit",
                    "target_name": "Bandit",
                    "weapon": "Longsword",
                    "attack_roll": 20,
                    "attack_bonus": 4,
                    "attack_total": 24,
                    "target_ac": 12,
                    "critical": True,
                    "damage": 7,
                    "target_hp_before": 14,
                    "target_hp_after": 7,
                    "target_status": "active",
                    "combat_started": True,
                    "combat_ended": False,
                    "enemy_action": {
                        "action": "enemy_attack",
                        "status": "resolved",
                        "success": True,
                        "outcome": "hit",
                        "actor": "npc_bandit",
                        "target": "player",
                        "target_id": "player",
                        "target_name": "Arven",
                        "weapon": "Dagger",
                        "attack_roll": 12,
                        "attack_bonus": 2,
                        "attack_total": 14,
                        "target_ac": 13,
                        "critical": False,
                        "damage": 2,
                        "target_hp_before": 11,
                        "target_hp_after": 9,
                        "target_status": "active",
                        "direct_response": "must not leave the engine",
                    },
                    "enemy_actions": [
                        {
                            "action": "enemy_attack",
                            "actor": "npc_bandit",
                            "actor_name": "Bandit",
                            "outcome": "hit",
                            "attack_roll": 12,
                            "damage": 2,
                            "private_state": "must not leave the engine",
                        },
                        {
                            "action": "enemy_attack",
                            "actor": "npc_archer",
                            "actor_name": "Archer",
                            "outcome": "miss",
                            "attack_roll": 4,
                            "damage": 0,
                            "private_state": "must not leave the engine",
                        },
                    ],
                    "direct_response": "must not leave the engine",
                    "state_changes": {"private": "must not leave the engine"},
                },
            }

        session.run_player_turn = attack_turn
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Bandit'e saldırıyorum.", "target_id": "npc_bandit"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(received_target_ids, ["npc_bandit"])
        result = response.json()["combat_result"]
        self.assertEqual(result["outcome"], "critical_hit")
        self.assertEqual(result["attack_roll"], 20)
        self.assertEqual(result["damage"], 7)
        self.assertEqual(result["enemy_action"]["attack_total"], 14)
        self.assertEqual(result["enemy_action"]["damage"], 2)
        self.assertNotIn("direct_response", result)
        self.assertNotIn("state_changes", result)
        self.assertNotIn("direct_response", result["enemy_action"])
        self.assertEqual(
            [(enemy["actor"], enemy["actor_name"], enemy["outcome"])
             for enemy in result["enemy_actions"]],
            [
                ("npc_bandit", "Bandit", "hit"),
                ("npc_archer", "Archer", "miss"),
            ],
        )
        self.assertNotIn("private_state", result["enemy_actions"][0])
        history_entry = response.json()["combat_history_entry"]
        self.assertEqual(history_entry["result"], result)
        self.assertRegex(
            history_entry["event_id"],
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        )
        self.assertEqual(history_entry["turn_index"], response.json()["state"]["turn_index"])
        self.assertNotIn("direct_response", history_entry["result"])
        self.assertNotIn("state_changes", history_entry["result"])

        detail = await self.http.get(
            f"/api/game/campaigns/{created['campaign_id']}"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["combat_history"], [history_entry])
        resumed = await self.http.post(
            f"/api/game/campaigns/{created['campaign_id']}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["combat_history"], [history_entry])

    async def test_engine_failure_does_not_append_campaign_combat_history(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        saved_before = self.store.get_campaign(created["campaign_id"]).payload

        def fail_after_mutation(_message):
            record.game_session.character["current_hp"] = 0
            record.game_session.world_state["inventory"].clear()
            raise RuntimeError("private engine failure")

        record.game_session.run_player_turn = fail_after_mutation
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "I attack."},
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).payload,
            saved_before,
        )
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).combat_history,
            [],
        )
        self.assertEqual(record.combat_history, [])

    async def test_skill_check_turn_returns_only_allowlisted_canonical_result(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.character["modifiers"]["wisdom"] = 2
        session.character["modifiers"]["strength"] = 3
        session.character["proficient_skills"] = ["Perception"]
        session.character["proficiency_bonus"] = 2

        def perception_turn(_message):
            return {
                "narration": "Bir ses duyuyorsun.",
                "action_result": {
                    "action": "skill_check",
                    "skill": "Perception",
                    "ability": "wisdom",
                    "dice": 14,
                    "modifier": 2,
                    "proficiency_bonus": 2,
                    "total": 18,
                    "dc": 15,
                    "outcome": "success",
                    "success": True,
                    "status": "resolved",
                    "target_type": "door",
                    "direct_response": "must not leave the engine",
                    "state_changes": ["private"],
                    "model_result": {"d20": 20, "outcome": "critical_success"},
                },
            }

        session.run_player_turn = perception_turn
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Kapının arkasından ses dinliyorum."},
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["skill_check_result"]
        self.assertEqual(
            result,
            {
                "skill": "Perception",
                "ability": "wisdom",
                "d20": 14,
                "proficient": True,
                "ability_modifier": 2,
                "proficiency_modifier": 2,
                "total_modifier": 4,
                "total": 18,
                "difficulty": "medium",
                "dc": 15,
                "outcome": "success",
            },
        )
        self.assertNotIn("direct_response", result)
        self.assertNotIn("state_changes", result)
        self.assertNotIn("model_result", result)
        self.assertIsNone(response.json()["combat_result"])

        def athletics_turn(_message):
            return {
                "narration": "Tırmanışın başarılı olur.",
                "action_result": {
                    "action": "skill_check",
                    "skill": "Athletics",
                    "ability": "strength",
                    "dice": 13,
                    "modifier": 3,
                    "proficiency_bonus": 0,
                    "total": 16,
                    "dc": 15,
                    "outcome": "success",
                    "success": True,
                    "status": "resolved",
                    "state_changes": ["private"],
                },
            }

        session.run_player_turn = athletics_turn
        nonproficient_response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Tırmanıyorum."},
        )
        self.assertEqual(
            nonproficient_response.status_code,
            200,
            nonproficient_response.text,
        )
        nonproficient = nonproficient_response.json()["skill_check_result"]
        self.assertEqual(nonproficient["skill"], "Athletics")
        self.assertEqual(nonproficient["ability"], "strength")
        self.assertFalse(nonproficient["proficient"])
        self.assertEqual(nonproficient["proficiency_modifier"], 0)
        self.assertEqual(nonproficient["total_modifier"], 3)
        self.assertEqual(nonproficient["total"], 16)

    async def test_four_new_skill_results_serialize_for_the_existing_client_contract(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.character["modifiers"].update({
            "charisma": 1,
            "dexterity": 1,
            "wisdom": 1,
        })
        session.character["proficiency_bonus"] = 2

        cases = (
            ("Persuasion", "charisma", True),
            ("Deception", "charisma", False),
            ("Acrobatics", "dexterity", True),
            ("Survival", "wisdom", False),
        )
        for skill, ability, proficient in cases:
            with self.subTest(skill=skill):
                session.character["proficient_skills"] = [skill] if proficient else []
                proficiency_modifier = 2 if proficient else 0
                total = 12 + 1 + proficiency_modifier
                outcome = "success" if total >= 15 else "failure"

                def skill_turn(_message):
                    return {
                        "narration": "A canonical skill result.",
                        "action_result": {
                            "action": "skill_check",
                            "skill": skill,
                            "ability": ability,
                            "dice": 12,
                            "modifier": 1,
                            "proficiency_bonus": proficiency_modifier,
                            "total": total,
                            "dc": 15,
                            "outcome": outcome,
                            "success": outcome == "success",
                            "status": "resolved",
                        },
                    }

                session.run_player_turn = skill_turn
                response = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/turn",
                    json={"message": f"I attempt {skill}."},
                )
                self.assertEqual(response.status_code, 200, response.text)
                projected = response.json()["skill_check_result"]
                self.assertEqual(projected["skill"], skill)
                self.assertEqual(projected["ability"], ability)
                self.assertEqual(projected["proficient"], proficient)
                self.assertEqual(projected["proficiency_modifier"], proficiency_modifier)
                self.assertEqual(projected["total"], total)
                self.assertEqual(projected["outcome"], outcome)

    async def test_invalid_skill_check_projection_rolls_back_turn(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        before = copy.deepcopy(session.serialize_game_state())
        before_rng = session.rng.getstate()

        def invalid_skill_turn(_message):
            session.character["current_hp"] -= 1
            session.rng.randint(1, 20)
            return {
                "narration": "This result must not be committed.",
                "action_result": {
                    "action": "skill_check",
                    "skill": "Perception",
                    "ability": "charisma",
                    "dice": 14,
                    "modifier": 2,
                    "proficiency_bonus": 0,
                    "total": 16,
                    "dc": 15,
                    "outcome": "success",
                },
            }

        session.run_player_turn = invalid_skill_turn
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Kapının arkasından ses dinliyorum."},
        )

        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["detail"]["code"], "engine_error")
        self.assertEqual(session.serialize_game_state(), before)
        self.assertEqual(session.rng.getstate(), before_rng)

    async def test_turn_request_rejects_client_skill_mechanics(self):
        created = await self.create_campaign()
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={
                "message": "Kapının arkasından ses dinliyorum.",
                "skill": "Perception",
                "d20": 20,
                "dc": 1,
                "outcome": "critical_success",
                "skill_check_result": {"skill": "Perception", "d20": 20},
            },
        )

        self.assertEqual(response.status_code, 422, response.text)

    async def test_successful_turn_is_autosaved_with_history(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session

        def complete_turn(_message):
            session.character["current_hp"] -= 1
            session.world_state["location"] = "tavern"
            session.world_state["inventory"].append("Lantern")
            npc = {
                "id": "npc_api",
                "name": "Mira",
                "role": "innkeeper",
                "location": "tavern",
                "memory": [
                    {"speaker": "player", "text": "My name is Arven."},
                    {"speaker": "npc", "text": "Welcome, Arven."},
                ],
            }
            session.world_state["npcs"].append(npc)
            return {
                "narration": "Mira welcomes Arven.",
                "action_result": {
                    "action": "dialogue",
                    "npc_id": "npc_api",
                    "status": "resolved",
                },
            }

        session.run_player_turn = complete_turn
        turn = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Mira'ya adım Arven diyorum."},
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertIsNone(turn.json()["combat_result"])
        self.assertIsNone(turn.json()["skill_check_result"])
        self.assertIn("Lantern", turn.json()["state"]["inventory"])
        self.assertEqual(turn.json()["state"]["location"], "tavern")

        detail = await self.http.get(
            f"/api/game/campaigns/{created['campaign_id']}"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["state"], turn.json()["state"])
        self.assertEqual(len(detail.json()["history"]), 1)
        self.assertEqual(
            detail.json()["history"][0]["player_message"],
            "Mira'ya adım Arven diyorum.",
        )
        self.assertEqual(
            detail.json()["state"]["npcs"][0]["name"],
            "Mira",
        )
        journal = turn.json()["state"]["journal"]
        self.assertEqual(
            [item["location_id"] for item in journal["discovered_locations"]],
            ["tavern"],
        )
        self.assertEqual(journal["known_npcs"][0]["npc_id"], "npc_api")
        self.assertEqual(journal["quests"], [])
        self.assertEqual(
            [item["event_type"] for item in journal["notable_events"]],
            ["location_discovered", "npc_met", "item_gained"],
        )
        stored = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(stored.payload["journal"], journal)

    async def test_failed_autosave_rolls_back_turn_and_keeps_last_good_save(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        record = self.manager.get(created["session_id"])
        from api.narrative_memory import (
            empty_narrative_memory,
            update_narrative_memory,
        )

        record.narrative_memory = update_narrative_memory(
            empty_narrative_memory(),
            player_message="I promise Mira I will ask about the caravan.",
            narration="The hearth glows softly in the old inn.",
            action_result={
                "action": "dialogue",
                "status": "success",
                "npc_id": "npc-mira",
            },
            world_state_before={},
            world_state_after={
                "location": "loc-inn",
                "npcs": [
                    {
                        "id": "npc-mira",
                        "name": "Mira",
                        "role": "merchant",
                        "location": "loc-inn",
                    }
                ],
            },
        )
        self.manager.save_campaign(created["campaign_id"])
        before = copy.deepcopy(session.serialize_game_state())
        journal_before = copy.deepcopy(record.journal)
        memory_before = copy.deepcopy(record.narrative_memory)
        saved_before = self.store.get_campaign(created["campaign_id"]).payload

        def mutate_then_succeed(_message):
            session.character["current_hp"] -= 2
            session.world_state["inventory"].append("Uncommitted")
            return {
                "narration": "This turn will not be committed.",
                "action_result": {
                    "action": "attack",
                    "status": "resolved",
                    "success": True,
                    "attack_roll": 14,
                },
            }

        session.run_player_turn = mutate_then_succeed
        with patch.object(
            self.store,
            "save_campaign",
            side_effect=CampaignStorageError("database unavailable"),
        ):
            response = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "This write will fail."},
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("database unavailable", response.text)
        self.assertEqual(session.serialize_game_state(), before)
        self.assertEqual(
            record.journal,
            journal_before,
        )
        self.assertEqual(record.narrative_memory, memory_before)
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).payload,
            saved_before,
        )
        self.assertEqual(
            self.store.get_campaign(created["campaign_id"]).combat_history,
            [],
        )
        self.assertEqual(
            self.manager.get(created["session_id"]).combat_history,
            [],
        )

    async def test_create_rejects_client_supplied_canonical_state(self):
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "name": "Forged",
                "current_hp": 0,
                "inventory": ["forged"],
                "location": "forest",
            },
        )
        self.assertEqual(response.status_code, 422)
        listed = await self.http.get("/api/game/campaigns")
        self.assertEqual(listed.json(), [])

    async def test_explicit_save_uses_active_server_session_and_unknown_campaign_is_404(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.world_state["location"] = "tavern"

        saved = await self.http.post(
            f"/api/game/campaigns/{created['campaign_id']}/save"
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["location"], "tavern")

        missing = "00000000-0000-4000-8000-000000000000"
        unavailable = await self.http.post(
            f"/api/game/campaigns/{missing}/resume"
        )
        self.assertEqual(unavailable.status_code, 404)
        self.assertEqual(
            unavailable.json()["detail"]["code"],
            "campaign_not_found",
        )

    async def test_journal_survives_explicit_save_and_a_new_session_manager(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.world_state["location"] = "tavern"
        session.plan_living_world_turn("Etrafıma bakıyorum.")

        def visit_tavern(_message):
            session.world_state["location"] = "tavern"
            return {
                "narration": "The room comes into view.",
                "action_result": {"action": "travel", "status": "completed", "success": True},
            }

        session.run_player_turn = visit_tavern
        turn = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Taverna'ya giriyorum."},
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        saved = await self.http.post(
            f"/api/game/campaigns/{created['campaign_id']}/save"
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        restarted_manager = SessionManager(campaign_store=self.store)
        _, _, _, _, resumed_state = restarted_manager.resume_campaign(
            created["campaign_id"]
        )
        self.assertEqual(
            resumed_state["journal"],
            turn.json()["state"]["journal"],
        )
        self.assertEqual(resumed_state["scene"]["id"], "scene:tavern")
        self.assertTrue(
            resumed_state["scene"]["visit_revision"] >= 1
        )

    async def test_store_save_without_journal_argument_preserves_existing_journal(self):
        created = await self.create_campaign()
        record = self.manager.get(created["session_id"])
        session = record.game_session
        session.world_state["location"] = "tavern"
        record.journal = create_initial_campaign_journal(
            session.world_state,
            session.world_metadata,
        )
        self.store.save_campaign(
            created["campaign_id"],
            session,
            journal=record.journal,
        )

        self.store.save_campaign(created["campaign_id"], session)
        stored = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(stored.payload["journal"], record.journal)

    async def test_legacy_save_without_narrative_memory_migrates_to_empty_memory(self):
        from api.narrative_memory import empty_narrative_memory

        created = await self.create_campaign()
        connection = sqlite3.connect(self.store.path)
        try:
            row = connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (created["campaign_id"],),
            ).fetchone()
            payload = json.loads(row[0])
            payload.pop("narrative_memory")
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                (json.dumps(payload), created["campaign_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        restarted_manager = SessionManager(campaign_store=self.store)
        _, record, _, _, _ = restarted_manager.resume_campaign(
            created["campaign_id"]
        )
        self.assertEqual(record.narrative_memory, empty_narrative_memory())
        migrated = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(
            migrated.payload["narrative_memory"],
            empty_narrative_memory(),
        )

    async def test_legacy_save_without_journal_migrates_to_empty_ledger(self):
        created = await self.create_campaign()
        connection = sqlite3.connect(self.store.path)
        try:
            row = connection.execute(
                "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                (created["campaign_id"],),
            ).fetchone()
            payload = json.loads(row[0])
            payload.pop("journal")
            connection.execute(
                "UPDATE campaigns SET payload_json = ? WHERE campaign_id = ?",
                (json.dumps(payload), created["campaign_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        restarted_manager = SessionManager(campaign_store=self.store)
        _, record, _, _, state = restarted_manager.resume_campaign(
            created["campaign_id"]
        )
        self.assertEqual(record.journal["quests"], [])
        self.assertEqual(state["journal"], record.journal)
        migrated = self.store.get_campaign(created["campaign_id"])
        self.assertEqual(migrated.payload["journal"]["discovered_locations"], [])
        self.assertEqual(migrated.payload["journal"]["quests"], [])

    async def test_turn_request_cannot_inject_journal_sections(self):
        created = await self.create_campaign()
        forged_fields = {
            "discovered_locations": [{"location_id": "forged"}],
            "known_npcs": [{"npc_id": "forged"}],
            "notable_events": [{"summary": "forged"}],
            "quests": [{"title": "Forged quest"}],
        }
        for field, value in forged_fields.items():
            response = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "continue", field: value},
            )
            self.assertEqual(response.status_code, 422, response.text)
        state = await self.http.get(
            f"/api/game/sessions/{created['session_id']}/state"
        )
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()["journal"]["quests"], [])
        self.assertEqual(
            state.json()["journal"]["discovered_locations"],
            [],
        )

    async def test_narration_cannot_create_or_complete_quests(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        session.run_player_turn = lambda _message: {
            "narration": "Görev tamamlandı; ödülün sana verildi."
        }
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Ne oldu?"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        journal = response.json()["state"]["journal"]
        self.assertEqual(journal["quests"], [])
        self.assertEqual(journal["notable_events"], [])

    async def test_ambient_event_outcome_is_authoritative_idempotent_and_persistent(self):
        created = await self.create_campaign()
        session_id = created["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        event_instance_id = self.install_test_ambient_event(session)
        action_id = "00000000-0000-4000-8000-000000000051"
        event_url = (
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{event_instance_id}/actions"
        )
        npc_count = len(session.world_state["npcs"])

        applied = await self.http.post(
            event_url,
            json={"action_id": action_id, "action": "interact"},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        applied_body = applied.json()
        result = applied_body["result"]
        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(result["event_instance_id"], event_instance_id)
        self.assertEqual(len(session.world_state["npcs"]), npc_count + 1)
        self.assertIn(
            result["transition_id"],
            {item["id"] for item in applied_body["state"]["npcs"]},
        )
        self.assertTrue(result["canonical_event_id"])
        ambient_records = [
            item for item in record.journal["notable_events"]
            if item.get("event_type") == "ambient_event_outcome"
        ]
        self.assertEqual(len(ambient_records), 1)
        self.assertEqual(
            ambient_records[0]["event_id"],
            result["canonical_event_id"],
        )
        self.assertEqual(
            ambient_records[0]["event_result"]["event_instance_id"],
            event_instance_id,
        )

        state_after_apply = copy.deepcopy(session.serialize_game_state())
        journal_after_apply = copy.deepcopy(record.journal)
        replay = await self.http.post(
            event_url,
            json={"action_id": action_id, "action": "interact"},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["result"]["status"], "ALREADY_APPLIED")
        self.assertEqual(
            replay.json()["result"]["canonical_event_id"],
            result["canonical_event_id"],
        )
        self.assertEqual(session.serialize_game_state(), state_after_apply)
        self.assertEqual(record.journal, journal_after_apply)
        different_action_replay = await self.http.post(
            event_url,
            json={
                "action_id": "00000000-0000-4000-8000-000000000052",
                "action": "interact",
            },
        )
        self.assertEqual(
            different_action_replay.json()["result"]["status"],
            "ALREADY_APPLIED",
        )
        self.assertEqual(session.serialize_game_state(), state_after_apply)
        self.assertEqual(record.journal, journal_after_apply)

        reloaded_manager = SessionManager(campaign_store=self.store)
        reloaded_app = create_app(
            session_manager=reloaded_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        reloaded_http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reloaded_app),
            base_url="http://testserver",
        )
        try:
            resumed = await reloaded_http.post(
                f"/api/game/campaigns/{created['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            loaded_session_id = resumed.json()["session_id"]
            loaded_record = reloaded_manager.get(loaded_session_id)
            loaded_scene = resumed.json()["state"]["scene"]
            self.assertEqual(
                loaded_scene["ambient_event"]["instance_id"],
                event_instance_id,
            )
            loaded_replay = await reloaded_http.post(
                f"/api/game/sessions/{loaded_session_id}/ambient-events/"
                f"{event_instance_id}/actions",
                json={"action_id": action_id, "action": "interact"},
            )
            self.assertEqual(loaded_replay.status_code, 200, loaded_replay.text)
            self.assertEqual(
                loaded_replay.json()["result"]["status"],
                "ALREADY_APPLIED",
            )
            self.assertEqual(
                loaded_replay.json()["result"]["canonical_event_id"],
                result["canonical_event_id"],
            )
            self.assertEqual(
                len([
                    item for item in loaded_record.journal["notable_events"]
                    if item.get("event_type") == "ambient_event_outcome"
                ]),
                1,
            )
        finally:
            await reloaded_http.aclose()

    async def test_ambient_event_rejections_no_effect_and_campaign_isolation(self):
        created = await self.create_campaign()
        session_id = created["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        green_instance_id = self.install_test_ambient_event(session, "GREEN")
        before_world = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        green_result = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{green_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000053",
                "action": "interact",
            },
        )
        self.assertEqual(green_result.status_code, 200, green_result.text)
        self.assertEqual(green_result.json()["result"]["status"], "REJECTED")
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)

        blue_instance_id = self.install_test_ambient_event(session)
        observe_id = "00000000-0000-4000-8000-000000000054"
        before_world = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        no_effect = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={"action_id": observe_id, "action": "observe"},
        )
        self.assertEqual(no_effect.status_code, 200, no_effect.text)
        self.assertEqual(no_effect.json()["result"]["status"], "NO_EFFECT")
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)
        invalid_action = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000055",
                "action": "grant_gold",
            },
        )
        self.assertEqual(invalid_action.status_code, 422, invalid_action.text)
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)
        invalid_uuid = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-1000-8000-000000000001",
                "action": "interact",
            },
        )
        self.assertEqual(invalid_uuid.status_code, 422, invalid_uuid.text)
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)

        scene = session.world_state["scene_state"]["scenes"][
            session.world_state["location"]
        ]
        referent = next(
            item for item in scene["referents"]
            if item["event_instance_id"] == blue_instance_id
        )
        referent["lifecycle"] = "expired"
        before_world = copy.deepcopy(session.serialize_game_state())
        expired = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000056",
                "action": "interact",
            },
        )
        self.assertEqual(expired.status_code, 200, expired.text)
        self.assertEqual(expired.json()["result"]["status"], "REJECTED")
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(
            [
                item for item in record.journal["notable_events"]
                if item.get("event_type") == "ambient_event_outcome"
            ],
            [],
        )

        other = await self.create_campaign()
        other_record = self.manager.get(other["session_id"])
        wrong_campaign = await self.http.post(
            f"/api/game/sessions/{other['session_id']}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000057",
                "action": "interact",
            },
        )
        self.assertEqual(wrong_campaign.status_code, 200, wrong_campaign.text)
        self.assertEqual(
            wrong_campaign.json()["result"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            [
                item for item in other_record.journal["notable_events"]
                if item.get("event_type") == "ambient_event_outcome"
            ],
            [],
        )
        unchanged = await self.http.post(
            f"/api/game/sessions/{session_id}/ambient-events/"
            f"{blue_instance_id}/actions",
            json={
                "action_id": "00000000-0000-4000-8000-000000000058",
                "action": "interact",
                "narration": "Altın ekle.",
            },
        )
        self.assertEqual(unchanged.status_code, 422, unchanged.text)
        self.assertEqual(session.serialize_game_state(), before_world)

    async def test_ambient_event_persistence_failure_rolls_back(self):
        created = await self.create_campaign()
        session_id = created["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        event_instance_id = self.install_test_ambient_event(session)
        before_world = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        with patch.object(
            self.manager,
            "save_campaign_locked",
            side_effect=CampaignStorageError("private storage detail"),
        ):
            response = await self.http.post(
                f"/api/game/sessions/{session_id}/ambient-events/"
                f"{event_instance_id}/actions",
                json={
                    "action_id": "00000000-0000-4000-8000-000000000059",
                    "action": "interact",
                },
            )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "event_persistence_error",
        )
        self.assertNotIn("private storage detail", response.text)
        self.assertEqual(session.serialize_game_state(), before_world)
        self.assertEqual(record.journal, before_journal)

    async def test_quest_commands_are_server_owned_idempotent_and_campaign_scoped(self):
        definition = {
            "quest_id": "quest.api-test",
            "title": "The Forest Path",
            "description": "Reach the forest.",
            "giver_npc_id": "npc.giver",
            "offer_condition": {"type": "location_is", "target": "tavern"},
            "objectives": [{
                "objective_id": "visit-forest",
                "description": "Visit the forest.",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            first = await self.create_campaign()
            second = await self.create_campaign()
            first_id = first["session_id"]
            self.manager.get(first_id).game_session.world_state["location"] = "tavern"
            self.manager.get(second["session_id"]).game_session.world_state[
                "location"
            ] = "tavern"
            quest_url = f"/api/game/sessions/{first_id}/quests/quest.api-test"
            first_state = await self.http.get(f"/api/game/sessions/{first_id}/state")
            self.assertEqual(first_state.status_code, 200, first_state.text)

            self.assertEqual(
                [item["quest_id"] for item in first_state.json()["quest_offers"]],
                ["quest.api-test"],
            )
            self.assertEqual(first_state.json()["quests"], [])
            self.assertEqual(first_state.json()["journal"]["quests"], [])

            unavailable = await self.http.post(
                f"/api/game/sessions/{first_id}/quests/unknown/accept"
            )
            self.assertEqual(unavailable.status_code, 404)

            accepted = await self.http.post(
                f"{quest_url}/accept",
                json={
                    "status": "completed",
                    "quest_id": "forged",
                    "objectives": [{"objective_id": "forged"}],
                },
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            accepted_body = accepted.json()
            self.assertEqual(accepted_body["quest"]["quest_id"], "quest.api-test")
            self.assertEqual(accepted_body["quest"]["status"], "accepted")
            self.assertEqual(
                accepted_body["quest"]["objectives"][0]["objective_id"],
                "visit-forest",
            )
            self.assertEqual(accepted_body["outcome"]["transition"], "accepted")
            self.assertEqual(accepted_body["state"]["quests"][0]["status"], "accepted")
            self.assertEqual(accepted_body["state"]["quest_offers"], [])

            repeated_accept = await self.http.post(f"{quest_url}/accept")
            self.assertEqual(repeated_accept.status_code, 200, repeated_accept.text)
            self.assertIsNone(repeated_accept.json()["outcome"])

            second_state = await self.http.get(
                f"/api/game/sessions/{second['session_id']}/state"
            )
            self.assertEqual(second_state.status_code, 200, second_state.text)
            self.assertEqual(second_state.json()["quests"], [])
            self.assertEqual(
                [item["quest_id"] for item in second_state.json()["quest_offers"]],
                ["quest.api-test"],
            )

            cancelled = await self.http.post(
                f"{quest_url}/cancel",
                json={"status": "completed", "progress": 999},
            )
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["quest"]["status"], "cancelled")
            self.assertEqual(
                cancelled.json()["quest"]["objectives"][0]["status"], "cancelled"
            )
            self.assertEqual(cancelled.json()["outcome"]["transition"], "cancelled")

            repeated_cancel = await self.http.post(f"{quest_url}/cancel")
            self.assertEqual(repeated_cancel.status_code, 200, repeated_cancel.text)
            self.assertIsNone(repeated_cancel.json()["outcome"])

            resumed = await self.http.post(
                f"/api/game/campaigns/{first['campaign_id']}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"]["quests"][0]["status"], "cancelled")
            self.assertEqual(resumed.json()["state"]["quest_offers"], [])

    async def test_quest_offer_conditions_and_autosave_failure_roll_back(self):
        definition = {
            "quest_id": "quest.rollback-test",
            "title": "Forest Path",
            "description": "Reach the forest.",
            "offer_condition": {"type": "location_is", "target": "forest"},
            "objectives": [{
                "objective_id": "visit-forest",
                "description": "Visit the forest.",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            created = await self.create_campaign()
            session = self.manager.get(created["session_id"]).game_session
            self.assertEqual(created["state"]["quest_offers"], [])

            not_offerable = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/quests/"
                "quest.rollback-test/accept"
            )
            self.assertEqual(not_offerable.status_code, 404)

            session.world_state["location"] = "forest"
            state = await self.http.get(
                f"/api/game/sessions/{created['session_id']}/state"
            )
            self.assertEqual(
                [item["quest_id"] for item in state.json()["quest_offers"]],
                ["quest.rollback-test"],
            )
            before = copy.deepcopy(session.serialize_game_state())
            world_ref = session.world_state
            rng_state = session.rng.getstate()
            saved_before = self.store.get_campaign(created["campaign_id"]).payload
            with patch.object(
                self.store,
                "save_campaign",
                side_effect=CampaignStorageError("database unavailable"),
            ):
                failed = await self.http.post(
                    f"/api/game/sessions/{created['session_id']}/quests/"
                    "quest.rollback-test/accept"
                )

            self.assertEqual(failed.status_code, 503)
            self.assertNotIn("database unavailable", failed.text)
            self.assertIs(session.world_state, world_ref)
            self.assertEqual(session.serialize_game_state(), before)
            self.assertEqual(session.rng.getstate(), rng_state)
            self.assertEqual(
                self.store.get_campaign(created["campaign_id"]).payload,
                saved_before,
            )

    async def test_active_quest_is_not_completed_by_narration(self):
        definition = {
            "quest_id": "quest.narration-test",
            "title": "Forest Path",
            "description": "Reach the forest.",
            "offer_condition": {"type": "location_is", "target": "tavern"},
            "objectives": [{
                "objective_id": "visit-forest",
                "description": "Visit the forest.",
                "type": "visit_location",
                "target": "forest",
            }],
        }
        with patch.object(quest_catalog, "CATALOG", (definition,)):
            created = await self.create_campaign()
            session = self.manager.get(created["session_id"]).game_session
            session.world_state["location"] = "tavern"
            accepted = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/quests/"
                "quest.narration-test/accept"
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)

            session.run_player_turn = lambda _message: {
                "action_result": {},
                "narration": "The quest is accepted and the objective is complete.",
            }
            turn = await self.http.post(
                f"/api/game/sessions/{created['session_id']}/turn",
                json={"message": "What happened?"},
            )
            self.assertEqual(turn.status_code, 200, turn.text)
            self.assertEqual(turn.json()["quest_outcomes"], [])
            self.assertEqual(turn.json()["state"]["quests"][0]["status"], "accepted")
            self.assertEqual(
                turn.json()["state"]["quests"][0]["objectives"][0]["progress"], 0
            )

    async def test_journal_state_is_isolated_between_campaigns(self):
        first = await self.create_campaign()
        second = await self.create_campaign()
        session = self.manager.get(first["session_id"]).game_session

        def enter_forest(_message):
            session.world_state["location"] = "forest"
            return {
                "narration": "Ormana ilerliyorsun.",
                "action_result": {"action": "travel", "status": "completed", "success": True},
            }

        session.run_player_turn = enter_forest
        changed = await self.http.post(
            f"/api/game/sessions/{first['session_id']}/turn",
            json={"message": "Ormana gidiyorum."},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(
            changed.json()["state"]["journal"]["discovered_locations"][0]["location_id"],
            "forest",
        )

        untouched = await self.http.get(
            f"/api/game/sessions/{second['session_id']}/state"
        )
        self.assertEqual(untouched.status_code, 200, untouched.text)
        self.assertEqual(
            untouched.json()["journal"]["discovered_locations"],
            [],
        )

    async def test_failed_tavern_exit_after_resume_rolls_back_and_retries_once(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        initial_url = f"/api/game/sessions/{created['session_id']}/turn"
        searched = await self.http.post(
            initial_url,
            json={"message": "Yakınlarda bir taverna arıyorum.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(searched.status_code, 200, searched.text)
        setup_world = self.manager.get(created["session_id"]).game_session.world_state
        tavern_ids = [
            location_id for location_id, location in setup_world["locations"].items()
            if isinstance(location, dict) and location.get("scene_kind") == "tavern"
        ]
        self.assertEqual(len(tavern_ids), 1)
        unlock_venue_door(setup_world, tavern_ids[0])
        entered = await self.http.post(
            initial_url,
            json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        # Resume the real, persisted venue before injecting an exit save failure.
        store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        manager = SessionManager(campaign_store=store)
        app = create_app(
            session_manager=manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], entered.json()["state"])
            session_id = resumed.json()["session_id"]
            record = manager.get(session_id)
            session = record.game_session
            world = session.world_state
            self.assertEqual(world["location"], tavern_id)
            self.assertEqual(world["locations"][tavern_id]["scene_kind"], "tavern")
            self.assertEqual(world["locations"][tavern_id]["exit_location_id"], city_id)
            before_save = copy.deepcopy(session.serialize_game_state())
            before_campaign = store.get_campaign(campaign_id)
            self.assertEqual(before_campaign.payload["engine_save"], before_save)
            self.assertEqual(len(before_campaign.history), 2)
            before_position = copy.deepcopy(world["scene_state"]["player_position"])
            self.assertEqual(before_position["location_id"], tavern_id)
            city_visits = world["scene_state"]["scenes"][city_id]["visit_revision"]
            tavern_visits = world["scene_state"]["scenes"][tavern_id]["visit_revision"]
            before_journal = copy.deepcopy(record.journal)
            before_memory = copy.deepcopy(record.narrative_memory)
            before_receipts = copy.deepcopy(record.turn_action_receipts)
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            turn_url = f"/api/game/sessions/{session_id}/turn"
            real_turn = session.run_player_turn
            exit_results = []
            exit_worlds = []

            @wraps(real_turn)
            def capture_exit(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                exit_results.append(copy.deepcopy(result["action_result"]))
                exit_worlds.append(copy.deepcopy(session.world_state))
                return result

            with (
                patch.object(session, "run_player_turn", new=capture_exit),
                patch.object(
                    store, "save_campaign",
                    side_effect=CampaignStorageError("database unavailable"),
                ) as failed_save,
            ):
                failed = await http.post(turn_url, json=exit_body)
            failed_save.assert_called_once()
            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertEqual(
                failed.json()["detail"]["code"], "campaign_storage_unavailable"
            )
            self.assertNotIn("database unavailable", failed.text)
            self.assertEqual(len(exit_results), 1)
            self.assertEqual(exit_results[0]["action"], "exit")
            self.assertEqual(exit_results[0]["status"], "completed")
            self.assertEqual(exit_results[0]["target_id"], city_id)
            # Prove the engine actually exited before the save was rejected.
            self.assertEqual(exit_worlds[0]["location"], city_id)
            self.assertEqual(
                exit_worlds[0]["scene_state"]["player_position"]["location_id"],
                city_id,
            )
            self.assertEqual(
                exit_worlds[0]["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            self.assertEqual(session.serialize_game_state(), before_save)
            self.assertEqual(world["location"], tavern_id)
            self.assertEqual(world["scene_state"]["player_position"], before_position)
            self.assertEqual(
                world["scene_state"]["scenes"][city_id]["visit_revision"], city_visits
            )
            self.assertEqual(record.journal, before_journal)
            self.assertEqual(record.narrative_memory, before_memory)
            self.assertEqual(record.turn_action_receipts, before_receipts)
            self.assertNotIn(exit_body["action_id"], record.turn_action_receipts)
            failed_campaign = store.get_campaign(campaign_id)
            self.assertEqual(failed_campaign.payload, before_campaign.payload)
            self.assertEqual(failed_campaign.metadata, before_campaign.metadata)
            self.assertEqual(failed_campaign.history, before_campaign.history)
            self.assertEqual(failed_campaign.combat_history, before_campaign.combat_history)
            self.assertIsNone(store.get_turn_action(campaign_id, exit_body["action_id"]))

            # A separate manager must still restore the tavern, not the failed exit.
            fresh_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
            fresh_manager = SessionManager(campaign_store=fresh_store)
            fresh_app = create_app(
                session_manager=fresh_manager,
                ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=fresh_app),
                base_url="http://testserver",
            ) as fresh_http:
                restored = await fresh_http.post(
                    f"/api/game/campaigns/{campaign_id}/resume"
                )
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()["state"], entered.json()["state"])
            self.assertEqual(restored.json()["history"], resumed.json()["history"])
            fresh_record = fresh_manager.get(restored.json()["session_id"])
            self.assertEqual(fresh_record.game_session.serialize_game_state(), before_save)
            self.assertEqual(fresh_record.turn_action_receipts, before_receipts)
            self.assertIsNone(
                fresh_store.get_turn_action(campaign_id, exit_body["action_id"])
            )

            # Reuse the failed action ID once storage is healthy.
            with patch.object(session, "run_player_turn", new=capture_exit):
                retry = await http.post(turn_url, json=exit_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(len(exit_results), 2)
            self.assertEqual(exit_results[-1]["action"], "exit")
            self.assertEqual(exit_results[-1]["status"], "completed")
            self.assertEqual(exit_results[-1]["target_id"], city_id)
            self.assertEqual(retry.json()["state"]["location"], city_id)
            self.assertEqual(world["location"], city_id)
            self.assertEqual(
                world["scene_state"]["player_position"]["location_id"], city_id
            )
            self.assertEqual(
                world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            self.assertEqual(
                world["scene_state"]["scenes"][tavern_id]["visit_revision"], tavern_visits
            )
            committed_save = copy.deepcopy(session.serialize_game_state())
            committed = store.get_campaign(campaign_id)
            self.assertEqual(committed.payload["engine_save"], committed_save)
            self.assertEqual(len(committed.history), len(before_campaign.history) + 1)
            self.assertEqual(committed.history[:-1], before_campaign.history)
            # Campaign receipts are store-owned, unlike transient session receipts.
            self.assertEqual(
                manager.get_turn_action(record, exit_body["action_id"])["response"],
                retry.json(),
            )

            with patch.object(
                session, "run_player_turn",
                side_effect=AssertionError("Exit replay must not execute another turn"),
            ):
                replay = await http.post(turn_url, json=exit_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            self.assertEqual(session.serialize_game_state(), committed_save)
            replayed = store.get_campaign(campaign_id)
            self.assertEqual(replayed.payload, committed.payload)
            self.assertEqual(replayed.metadata, committed.metadata)
            self.assertEqual(replayed.history, committed.history)

    async def test_stale_resumed_tavern_cannot_overwrite_saved_exit_but_can_replay(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        initial_url = f"/api/game/sessions/{created['session_id']}/turn"
        searched = await self.http.post(
            initial_url,
            json={"message": "Yakınlarda bir taverna arıyorum.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(searched.status_code, 200, searched.text)
        setup_world = self.manager.get(created["session_id"]).game_session.world_state
        tavern_ids = [
            location_id for location_id, location in setup_world["locations"].items()
            if isinstance(location, dict) and location.get("scene_kind") == "tavern"
        ]
        self.assertEqual(len(tavern_ids), 1)
        unlock_venue_door(setup_world, tavern_ids[0])
        entered = await self.http.post(
            initial_url,
            json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        active_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        stale_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            # Both independent managers open the same saved tavern before the exit.
            active_resume = await active_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            stale_resume = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"], entered.json()["state"])
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            active_session = active_manager.get(active_id).game_session
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_session, stale_session)
            self.assertIsNot(active_session.world_state, stale_session.world_state)
            before = active_store.get_campaign(campaign_id)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            stale_world = stale_session.world_state
            stale_position = copy.deepcopy(stale_world["scene_state"]["player_position"])
            city_visits = stale_world["scene_state"]["scenes"][city_id]["visit_revision"]
            tavern_visits = stale_world["scene_state"]["scenes"][tavern_id]["visit_revision"]
            self.assertEqual(stale_world["location"], tavern_id)
            self.assertEqual(stale_position["location_id"], tavern_id)
            self.assertEqual(stale_save, before.payload["engine_save"])

            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            accepted = await active_http.post(
                f"/api/game/sessions/{active_id}/turn", json=exit_body
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["state"]["location"], city_id)
            committed = active_store.get_campaign(campaign_id)
            committed_world = committed.payload["engine_save"]["world_state"]
            self.assertEqual(committed_world["location"], city_id)
            self.assertEqual(
                committed_world["scene_state"]["player_position"]["location_id"], city_id
            )
            self.assertEqual(
                committed_world["scene_state"]["scenes"][city_id]["visit_revision"],
                city_visits + 1,
            )
            self.assertEqual(
                committed_world["scene_state"]["scenes"][tavern_id]["visit_revision"],
                tavern_visits,
            )
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(len(committed.history), len(before.history) + 1)
            self.assertEqual(committed.history[-1]["player_message"], exit_body["message"])
            exit_receipt = active_store.get_turn_action(campaign_id, exit_body["action_id"])
            self.assertEqual(exit_receipt["response"], accepted.json())
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_before = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(len(receipts_before), 3)

            # Do not resume again: this manager must keep its old tavern context.
            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            stale_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            stale_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Stale requests must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Stale requests must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(stale_url, json=stale_body)
                self.assertEqual(rejected.status_code, 409, rejected.text)
                self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
                rejected_campaign = stale_store.get_campaign(campaign_id)
                self.assertEqual(rejected_campaign.payload, committed.payload)
                self.assertEqual(rejected_campaign.metadata, committed.metadata)
                self.assertEqual(rejected_campaign.history, committed.history)
                self.assertEqual(rejected_campaign.combat_history, committed.combat_history)
                self.assertIsNone(stale_store.get_turn_action(campaign_id, stale_body["action_id"]))
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, exit_body["action_id"]),
                    exit_receipt,
                )

                replay = await stale_http.post(stale_url, json=exit_body)
                self.assertEqual(replay.status_code, 200, replay.text)
                expected_replay = copy.deepcopy(accepted.json())
                expected_replay["session_id"] = stale_id
                self.assertEqual(replay.json(), expected_replay)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()

            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            self.assertEqual(stale_world["scene_state"]["player_position"], stale_position)
            replayed_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(replayed_campaign.payload, committed.payload)
            self.assertEqual(replayed_campaign.metadata, committed.metadata)
            self.assertEqual(replayed_campaign.history, committed.history)
            self.assertEqual(replayed_campaign.combat_history, committed.combat_history)
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_after = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(receipts_after, receipts_before)

    async def test_stale_tavern_resume_refreshes_city_and_rejected_action_commits_once(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        turn_url = f"/api/game/sessions/{created['session_id']}/turn"
        searched = await self.http.post(
            turn_url,
            json={"message": "Yakınlarda bir taverna arıyorum.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(searched.status_code, 200, searched.text)
        setup_world = self.manager.get(created["session_id"]).game_session.world_state
        tavern_ids = [
            location_id for location_id, location in setup_world["locations"].items()
            if isinstance(location, dict) and location.get("scene_kind") == "tavern"
        ]
        self.assertEqual(len(tavern_ids), 1)
        unlock_venue_door(setup_world, tavern_ids[0])
        entered = await self.http.post(
            turn_url,
            json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        def receipt_rows():
            with closing(sqlite3.connect(self.store.path)) as connection:
                return connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()

        active_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        stale_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            resume_url = f"/api/game/campaigns/{campaign_id}/resume"
            active_resume = await active_http.post(resume_url)
            stale_resume = await stale_http.post(resume_url)
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"], entered.json()["state"])
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_manager.get(active_id).game_session, stale_session)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            before = active_store.get_campaign(campaign_id)
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, before.metadata["revision"]),
            )
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            accepted = await active_http.post(
                f"/api/game/sessions/{active_id}/turn", json=exit_body
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["state"]["location"], city_id)
            committed = active_store.get_campaign(campaign_id)
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(len(committed.history), len(before.history) + 1)
            prior_receipts = receipt_rows()
            self.assertEqual(len(prior_receipts), 3)
            exit_receipt = active_store.get_turn_action(campaign_id, exit_body["action_id"])
            self.assertEqual(exit_receipt["response"], accepted.json())

            # This is a new request, not replay of the already accepted exit.
            retry_body = {
                "message": "Enter the tavern.",
                "action_id": str(uuid.uuid4()),
            }
            turn_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Stale requests must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Stale requests must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(turn_url, json=retry_body)
            self.assertEqual(rejected.status_code, 409, rejected.text)
            self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
            blocked_turn.assert_not_called()
            blocked_save.assert_not_called()
            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            rejected_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(rejected_campaign, committed)
            self.assertIsNone(stale_store.get_turn_action(campaign_id, retry_body["action_id"]))
            self.assertEqual(receipt_rows(), prior_receipts)

            # Explicit resume through the SAME manager must refresh its cached session.
            refreshed = await stale_http.post(resume_url)
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertEqual(refreshed.json()["state"], accepted.json()["state"])
            self.assertEqual(refreshed.json()["history"], committed.history)
            self.assertEqual(
                stale_session.serialize_game_state(), committed.payload["engine_save"]
            )
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, committed.metadata["revision"]),
            )
            refreshed_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(
                refreshed_campaign.metadata["revision"], committed.metadata["revision"]
            )
            self.assertEqual(refreshed_campaign.history, committed.history)
            self.assertEqual(refreshed_campaign.payload, committed.payload)
            self.assertEqual(receipt_rows(), prior_receipts)
            self.assertIsNone(stale_store.get_turn_action(campaign_id, retry_body["action_id"]))

            # Keep the rejected ID: it should execute from the refreshed city exactly once.
            world = stale_session.world_state
            self.assertEqual(world["scene_state"]["player_position"]["location_id"], city_id)
            city_visits = world["scene_state"]["scenes"][city_id]["visit_revision"]
            tavern_visits = world["scene_state"]["scenes"][tavern_id]["visit_revision"]
            real_turn = stale_session.run_player_turn
            retry_results = []

            @wraps(real_turn)
            def capture_retry(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            with patch.object(stale_session, "run_player_turn", new=capture_retry):
                retry = await stale_http.post(turn_url, json=retry_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "enter")
            self.assertEqual(retry_results[0]["status"], "completed")
            self.assertEqual(retry_results[0]["target_id"], tavern_id)
            self.assertEqual(retry.json()["state"]["location"], tavern_id)
            self.assertEqual(world["scene_state"]["player_position"]["location_id"], tavern_id)
            self.assertEqual(
                world["scene_state"]["scenes"][tavern_id]["visit_revision"], tavern_visits + 1
            )
            self.assertEqual(
                world["scene_state"]["scenes"][city_id]["visit_revision"], city_visits
            )
            retried = stale_store.get_campaign(campaign_id)
            self.assertEqual(retried.metadata["revision"], committed.metadata["revision"] + 1)
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, retried.metadata["revision"]),
            )
            self.assertEqual(retried.history[:-1], committed.history)
            self.assertEqual(len(retried.history), len(committed.history) + 1)
            self.assertEqual(retried.history[-1]["player_message"], retry_body["message"])
            retried_save = copy.deepcopy(stale_session.serialize_game_state())
            self.assertEqual(retried.payload["engine_save"], retried_save)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, retry_body["action_id"])["response"],
                retry.json(),
            )
            committed_receipts = receipt_rows()
            self.assertEqual(len(committed_receipts), len(prior_receipts) + 1)
            self.assertTrue(all(row in committed_receipts for row in prior_receipts))
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, exit_body["action_id"]), exit_receipt
            )

            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Replay must not run another turn"),
                ) as replay_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save again"),
                ) as replay_save,
            ):
                replay = await stale_http.post(turn_url, json=retry_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(stale_session.serialize_game_state(), retried_save)
            self.assertEqual(stale_store.get_campaign(campaign_id), retried)
            self.assertEqual(receipt_rows(), committed_receipts)

    async def test_stale_city_cannot_overwrite_merchant_discovery_but_can_replay(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        campaign_id = created_response.json()["campaign_id"]
        active_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        stale_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            # Load both independent sessions before any merchant is discovered.
            active_resume = await active_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            stale_resume = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"]["location"], city_id)
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            active_session = active_manager.get(active_id).game_session
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_session, stale_session)
            self.assertIsNot(active_session.world_state, stale_session.world_state)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            stale_journal = copy.deepcopy(stale_record.journal)
            before = active_store.get_campaign(campaign_id)
            self.assertEqual(stale_save, before.payload["engine_save"])
            self.assertEqual(stale_save["world_state"]["shops"], [])

            body = {
                "message": "Bir tüccar arıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            results = []
            real_turn = active_session.run_player_turn

            @wraps(real_turn)
            def capture_search(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result["action_result"]))
                return result

            # Observe the real deterministic engine, not a scripted discovery.
            with patch.object(active_session, "run_player_turn", new=capture_search):
                accepted = await active_http.post(
                    f"/api/game/sessions/{active_id}/turn", json=body
                )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["action_id"], body["action_id"])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["action"], "local_search")
            self.assertEqual(results[0]["status"], "found")
            self.assertTrue(results[0]["success"])
            committed = active_store.get_campaign(campaign_id)
            world = committed.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(len(world["shops"]), 1)
            shop = world["shops"][0]
            self.assertEqual(shop["id"], results[0]["shop_id"])
            self.assertEqual(shop["shopkeeper_id"], results[0]["target_id"])
            self.assertEqual(shop["location"], city_id)
            shopkeepers = [
                npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]
            ]
            self.assertEqual(len(shopkeepers), 1)
            self.assertEqual(shopkeepers[0]["shop_id"], shop["id"])
            self.assertEqual(shopkeepers[0]["location"], city_id)
            self.assertEqual(
                [npc["id"] for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            self.assertEqual(committed.payload["engine_save"], active_session.serialize_game_state())
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(len(committed.history), len(before.history) + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(committed.history[-1]["player_message"], body["message"])
            receipt = copy.deepcopy(active_store.get_turn_action(campaign_id, body["action_id"]))
            self.assertEqual(receipt["response"], accepted.json())
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_before = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(len(receipts_before), 1)

            # No second resume: this session still has the merchant-free city.
            self.assertEqual(stale_session.serialize_game_state(), stale_save)
            stale_body = {
                "message": "Yakınlarda bir satıcı bulunuyor mu?",
                "action_id": str(uuid.uuid4()),
            }
            self.assertNotEqual(stale_body["message"], body["message"])
            self.assertNotEqual(stale_body["action_id"], body["action_id"])
            stale_url = f"/api/game/sessions/{stale_id}/turn"

            def assert_discovery_preserved():
                persisted = stale_store.get_campaign(campaign_id)
                self.assertEqual(persisted, committed)
                saved_world = persisted.payload["engine_save"]["world_state"]
                self.assertEqual(saved_world["shops"], [shop])
                self.assertEqual(
                    [npc for npc in saved_world["npcs"] if npc.get("shop_id") == shop["id"]],
                    shopkeepers,
                )
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
                )
                self.assertIsNone(
                    stale_store.get_turn_action(campaign_id, stale_body["action_id"])
                )
                self.assertEqual(stale_session.serialize_game_state(), stale_save)
                self.assertEqual(stale_record.journal, stale_journal)
                with closing(sqlite3.connect(self.store.path)) as connection:
                    receipts_after = connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                        "ORDER BY action_id", (campaign_id,),
                    ).fetchall()
                self.assertEqual(receipts_after, receipts_before)

            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Stale discovery and replay must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Stale discovery and replay must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(stale_url, json=stale_body)
                self.assertEqual(rejected.status_code, 409, rejected.text)
                self.assertEqual(rejected.json()["detail"]["code"], "campaign_stale")
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()
                assert_discovery_preserved()

                replay = await stale_http.post(stale_url, json=body)
                self.assertEqual(replay.status_code, 200, replay.text)
                expected_replay = copy.deepcopy(accepted.json())
                expected_replay["session_id"] = stale_id
                self.assertEqual(replay.json(), expected_replay)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()
                assert_discovery_preserved()

            # Refresh the cached stale session over HTTP, keeping its rejected ID.
            refreshed = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], stale_id)
            self.assertIs(stale_manager.get(stale_id), stale_record)
            self.assertIs(stale_record.game_session, stale_session)
            self.assertEqual(refreshed.json()["state"], accepted.json()["state"])
            self.assertEqual(refreshed.json()["history"], committed.history)
            self.assertEqual(
                stale_session.serialize_game_state(), committed.payload["engine_save"]
            )
            self.assertEqual(stale_record.journal, committed.payload["journal"])
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, committed.metadata["revision"]),
            )
            refreshed_campaign = stale_store.get_campaign(campaign_id)
            # Resume may refresh metadata timestamps, but not gameplay or receipts.
            self.assertEqual(refreshed_campaign.payload, committed.payload)
            self.assertEqual(refreshed_campaign.history, committed.history)
            self.assertEqual(
                refreshed_campaign.metadata["revision"], committed.metadata["revision"]
            )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
            )
            self.assertIsNone(
                stale_store.get_turn_action(campaign_id, stale_body["action_id"])
            )
            with closing(sqlite3.connect(self.store.path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                        "ORDER BY action_id", (campaign_id,),
                    ).fetchall(),
                    receipts_before,
                )

            real_retry = stale_session.run_player_turn
            retry_results = []

            @wraps(real_retry)
            def capture_retry(*args, **kwargs):
                result = real_retry(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            # Recovery has loaded an already committed merchant. A storage
            # failure here must restore that state, not the old merchant-free
            # snapshot, and must leave the rejected action ID available to retry.
            recovered_save = copy.deepcopy(stale_session.serialize_game_state())
            recovered_journal = copy.deepcopy(stale_record.journal)
            recovered_memory = copy.deepcopy(stale_record.narrative_memory)
            recovered_receipts = copy.deepcopy(stale_record.turn_action_receipts)
            recovered_version = stale_session._campaign_persistence_version
            failed_results = []
            attempted_saves = []

            @wraps(real_retry)
            def capture_failed_recovery(*args, **kwargs):
                result = real_retry(*args, **kwargs)
                failed_results.append(copy.deepcopy(result["action_result"]))
                return result

            def fail_recovered_save(*args, **kwargs):
                attempted_saves.append(copy.deepcopy(stale_session.serialize_game_state()))
                raise CampaignStorageError("recovered search database unavailable")

            with (
                patch.object(
                    stale_session, "run_player_turn", new=capture_failed_recovery
                ),
                patch.object(
                    stale_store, "save_campaign", side_effect=fail_recovered_save
                ) as failed_save,
            ):
                failed = await stale_http.post(stale_url, json=stale_body)
            failed_save.assert_called_once()
            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertEqual(
                failed.json()["detail"]["code"], "campaign_storage_unavailable"
            )
            self.assertNotIn("recovered search database unavailable", failed.text)
            self.assertEqual(len(failed_results), 1)
            self.assertEqual(failed_results[0]["action"], "local_search")
            self.assertEqual(failed_results[0]["status"], "found")
            self.assertTrue(failed_results[0]["success"])
            self.assertEqual(failed_results[0]["shop_id"], shop["id"])
            self.assertEqual(failed_results[0]["target_id"], shop["shopkeeper_id"])
            self.assertEqual(len(attempted_saves), 1)
            attempted_world = attempted_saves[0]["world_state"]
            self.assertEqual(attempted_world["shops"], [shop])
            self.assertEqual(
                [npc for npc in attempted_world["npcs"] if npc.get("shop_id") == shop["id"]],
                shopkeepers,
            )
            for collection in ("shops", "npcs"):
                self.assertEqual(
                    [item["id"] for item in attempted_world[collection]],
                    [item["id"] for item in world[collection]],
                )

            self.assertEqual(stale_session.serialize_game_state(), recovered_save)
            self.assertEqual(stale_record.journal, recovered_journal)
            self.assertEqual(stale_record.narrative_memory, recovered_memory)
            self.assertEqual(stale_record.turn_action_receipts, recovered_receipts)
            self.assertEqual(stale_session._campaign_persistence_version, recovered_version)
            # Compare with the post-resume record: its timestamps may have
            # legitimately changed when the stale session was refreshed.
            self.assertEqual(stale_store.get_campaign(campaign_id), refreshed_campaign)
            self.assertEqual(active_store.get_campaign(campaign_id), refreshed_campaign)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
            )
            self.assertEqual(
                stale_manager.get_turn_action(stale_record, body["action_id"]), receipt
            )
            self.assertIsNone(
                stale_store.get_turn_action(campaign_id, stale_body["action_id"])
            )
            self.assertIsNone(
                stale_manager.get_turn_action(stale_record, stale_body["action_id"])
            )
            with closing(sqlite3.connect(self.store.path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                        "ORDER BY action_id", (campaign_id,),
                    ).fetchall(),
                    receipts_before,
                )

            with (
                patch.object(stale_session, "run_player_turn", new=capture_retry),
                patch.object(
                    stale_store, "save_campaign", wraps=stale_store.save_campaign
                ) as retry_save,
            ):
                retried_response = await stale_http.post(stale_url, json=stale_body)
            self.assertEqual(retried_response.status_code, 200, retried_response.text)
            self.assertEqual(retried_response.json()["action_id"], stale_body["action_id"])
            retry_save.assert_called_once()
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "local_search")
            self.assertEqual(retry_results[0]["status"], "found")
            self.assertTrue(retry_results[0]["success"])
            self.assertEqual(retry_results[0]["shop_id"], shop["id"])
            self.assertEqual(retry_results[0]["target_id"], shop["shopkeeper_id"])
            retried = stale_store.get_campaign(campaign_id)
            retried_save = copy.deepcopy(stale_session.serialize_game_state())
            self.assertEqual(retried.payload["engine_save"], retried_save)
            self.assertEqual(retried.payload["journal"], stale_record.journal)
            retry_world = retried_save["world_state"]
            self.assertEqual(retry_world["location"], city_id)
            self.assertEqual(retry_world["shops"], [shop])
            self.assertEqual(
                [npc for npc in retry_world["npcs"] if npc["id"] == shop["shopkeeper_id"]],
                shopkeepers,
            )
            self.assertEqual(
                [npc["id"] for npc in retry_world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            for collection in ("shops", "npcs"):
                self.assertEqual(
                    [item["id"] for item in retry_world[collection]],
                    [item["id"] for item in world[collection]],
                )
            self.assertEqual(retried.metadata["revision"], committed.metadata["revision"] + 1)
            self.assertEqual(
                stale_session._campaign_persistence_version,
                (campaign_id, retried.metadata["revision"]),
            )
            self.assertEqual(len(retried.history), len(committed.history) + 1)
            self.assertEqual(retried.history[:-1], committed.history)
            self.assertEqual(retried.history[-1]["player_message"], stale_body["message"])
            recovered_receipt = stale_store.get_turn_action(
                campaign_id, stale_body["action_id"]
            )
            self.assertEqual(recovered_receipt["response"], retried_response.json())
            self.assertEqual(
                stale_manager.get_turn_action(stale_record, stale_body["action_id"]),
                recovered_receipt,
            )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
            )
            with closing(sqlite3.connect(self.store.path)) as connection:
                receipts_after = connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()
            self.assertEqual(len(receipts_after), len(receipts_before) + 1)
            self.assertTrue(all(row in receipts_after for row in receipts_before))

            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Recovered replay must not run another turn"),
                ) as replay_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Recovered replay must not save again"),
                ) as replay_save,
            ):
                replay = await stale_http.post(stale_url, json=stale_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retried_response.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(stale_session.serialize_game_state(), retried_save)
            self.assertEqual(stale_record.journal, retried.payload["journal"])
            self.assertEqual(stale_store.get_campaign(campaign_id), retried)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, body["action_id"]), receipt
            )
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, stale_body["action_id"]),
                recovered_receipt,
            )
            with closing(sqlite3.connect(self.store.path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                        "ORDER BY action_id", (campaign_id,),
                    ).fetchall(),
                    receipts_after,
                )

    async def test_first_merchant_search_same_id_race_rolls_back_and_replays_winner(self):
        await self._assert_first_merchant_search_save_race(shared_action=True)

    async def test_first_merchant_search_same_id_changed_payload_race_rejects_loser(self):
        await self._assert_first_merchant_search_save_race(
            shared_action=True, changed_payload=True,
        )

    async def test_first_merchant_search_distinct_id_race_rolls_back_and_retries_once(self):
        await self._assert_first_merchant_search_save_race(shared_action=False)

    async def test_first_merchant_search_race_retry_save_failure_restores_winner_and_retries_once(self):
        await self._assert_first_merchant_search_save_race(
            shared_action=False, fail_resumed_retry=True,
        )

    async def test_first_merchant_save_race_post_rollback_receipt_storage_error_is_safe(self):
        for changed_payload in (False, True):
            with self.subTest(changed_payload=changed_payload):
                await self._assert_first_merchant_search_save_race(
                    shared_action=True, changed_payload=changed_payload,
                    post_save_receipt_error=CampaignStorageError,
                )

    async def test_first_merchant_save_race_post_rollback_receipt_corrupt_error_is_safe(self):
        for changed_payload in (False, True):
            with self.subTest(changed_payload=changed_payload):
                await self._assert_first_merchant_search_save_race(
                    shared_action=True, changed_payload=changed_payload,
                    post_save_receipt_error=CampaignCorruptError,
                )

    async def test_first_merchant_distinct_id_save_race_post_rollback_receipt_storage_error_is_safe(self):
        await self._assert_first_merchant_search_save_race(
            shared_action=False, post_save_receipt_error=CampaignStorageError,
        )

    async def test_first_merchant_distinct_id_save_race_post_rollback_receipt_corrupt_error_is_safe(self):
        await self._assert_first_merchant_search_save_race(
            shared_action=False, post_save_receipt_error=CampaignCorruptError,
        )

    async def test_first_merchant_save_race_timeout_drains_worker_before_teardown(self):
        worker_entered = threading.Event()
        release_worker = threading.Event()
        worker_finished = threading.Event()
        real_save = CampaignStore.save_campaign
        real_wait_for = asyncio.wait_for
        real_exit = httpx.AsyncClient.__aexit__
        turn_saves = []
        request_tasks = []
        exited_clients = []
        timed_out = False

        def delayed_save(store, *args, **kwargs):
            if kwargs.get("turn_action_receipt") is not None:
                turn_saves.append(store)
                # The instance-level pause runs before this class-level spy.
                # Identify the loser by its save patch, not thread arrival order.
                if callable(getattr(store.save_campaign, "side_effect", None)):
                    worker_entered.set()
                    if not release_worker.wait(timeout=5):
                        raise AssertionError("Timeout injection did not release the worker.")
                    try:
                        self.assertIs(CampaignStore.save_campaign, delayed_save)
                        self.assertTrue(callable(getattr(store.save_campaign, "side_effect", None)))
                        self.assertTrue(self.store.path.exists())
                        return real_save(store, *args, **kwargs)
                    finally:
                        worker_finished.set()
            return real_save(store, *args, **kwargs)

        async def injected_wait_for(awaitable, timeout):
            nonlocal timed_out
            if timeout == 30:
                if len(request_tasks) == 2:
                    self.assertTrue(await asyncio.to_thread(worker_entered.wait, 5))
                    self.assertFalse(worker_finished.is_set())
                    # Emulate wait_for's timeout cancellation. Only the shield
                    # may be cancelled; the ASGI task and its save must survive.
                    awaitable.cancel()
                    timed_out = True
                    asyncio.get_running_loop().call_soon(release_worker.set)
                    raise TimeoutError("injected merchant request timeout")
            return await real_wait_for(awaitable, timeout)

        real_request_wait = self._wait_for_merchant_race_request

        async def observed_request_wait(task):
            request_tasks.append(task)
            return await real_request_wait(task)

        async def checked_exit(client, *args):
            if timed_out:
                self.assertFalse(client.is_closed)
                self.assertTrue(worker_finished.is_set())
                self.assertTrue(all(task.done() and not task.cancelled() for task in request_tasks))
                exited_clients.append(client)
            return await real_exit(client, *args)

        try:
            with (
                patch.object(CampaignStore, "save_campaign", new=delayed_save),
                patch.object(asyncio, "wait_for", new=injected_wait_for),
                patch.object(self, "_wait_for_merchant_race_request", new=observed_request_wait),
                patch.object(httpx.AsyncClient, "__aexit__", new=checked_exit),
            ):
                with self.assertRaisesRegex(TimeoutError, "injected merchant request timeout"):
                    await self._assert_first_merchant_search_save_race(shared_action=False)
                self.assertTrue(timed_out)
                self.assertTrue(worker_finished.is_set())
                self.assertEqual(len(turn_saves), 2)
                self.assertEqual(len(request_tasks), 2)
                self.assertEqual(len(exited_clients), 2)
                self.assertTrue(all(task.done() and not task.cancelled() for task in request_tasks))
                # Read the real SQLite fixture after cleanup, while patches are
                # still installed: the worker must not outlive this scope.
                with closing(sqlite3.connect(self.store.path)) as connection:
                    self.assertEqual(connection.execute(
                        "SELECT COUNT(*) FROM campaign_turn_actions",
                    ).fetchone()[0], 1)
        finally:
            release_worker.set()

    async def _wait_for_merchant_race_request(self, task):
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=30)
        except BaseException:
            # ASGI cancellation cannot stop a synchronous database worker.
            # Keep the client, patches and SQLite fixture alive until it exits.
            # The cleanup budget exceeds the fixture's 30-second event waits.
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=35)
            except TimeoutError as error:
                raise AssertionError("Merchant race request did not drain during cleanup.") from error
            except Exception:
                # Retrieve the worker error without replacing the original
                # timeout/assertion/cancellation that triggered cleanup.
                pass
            raise

    async def _assert_first_merchant_search_save_race(
        self, *, shared_action, fail_resumed_retry=False, changed_payload=False,
        post_save_receipt_error=None,
    ):
        if changed_payload:
            self.assertTrue(shared_action)
        city_id = "fr:city:neverwinter"
        created = await self.http.post(
            "/api/game/campaigns",
            json={"campaign_start": {
                "setting_id": "forgotten_realms",
                "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                "region_id": "fr:region:the_north",
                "starting_location_id": city_id,
            }},
        )
        self.assertEqual(created.status_code, 200, created.text)
        campaign_id = created.json()["campaign_id"]
        resume_url = f"/api/game/campaigns/{campaign_id}/resume"
        winner_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        loser_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        winner_manager = SessionManager(campaign_store=winner_store)
        loser_manager = SessionManager(campaign_store=loser_store)
        winner_app = create_app(
            session_manager=winner_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        loser_app = create_app(
            session_manager=loser_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))

        def receipt_rows():
            with closing(sqlite3.connect(self.store.path)) as connection:
                return connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()

        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=winner_app),
                base_url="http://testserver",
            ) as winner_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=loser_app),
                base_url="http://testserver",
            ) as loser_http,
        ):
            winner_resume = await winner_http.post(resume_url)
            loser_resume = await loser_http.post(resume_url)
            for response in (winner_resume, loser_resume):
                self.assertEqual(response.status_code, 200, response.text)
            winner_id = winner_resume.json()["session_id"]
            loser_id = loser_resume.json()["session_id"]
            winner_record = winner_manager.get(winner_id)
            loser_record = loser_manager.get(loser_id)
            winner_session = winner_record.game_session
            loser_session = loser_record.game_session
            self.assertIsNot(winner_store, loser_store)
            self.assertIsNot(winner_manager, loser_manager)
            self.assertNotEqual(winner_id, loser_id)
            self.assertIsNot(winner_session, loser_session)
            self.assertIsNot(winner_session.world_state, loser_session.world_state)

            def loser_runtime_state():
                return {
                    "messages": copy.deepcopy(loser_session.messages),
                    "rng": loser_session.rng.getstate(),
                    "metadata": copy.deepcopy(loser_session.world_metadata),
                    "lore": copy.deepcopy(loser_record.lore_authority),
                }

            before_runtime = loser_runtime_state()
            before_campaign = loser_store.get_campaign(campaign_id)
            before_engine = copy.deepcopy(loser_session.serialize_game_state())
            before_journal = copy.deepcopy(loser_record.journal)
            before_memory = copy.deepcopy(loser_record.narrative_memory)
            before_receipts = copy.deepcopy(loser_record.turn_action_receipts)
            before_version = loser_session._campaign_persistence_version
            before_rows = receipt_rows()
            self.assertEqual(before_engine["world_state"]["shops"], [])
            self.assertFalse(any(
                npc.get("shop_id") for npc in before_engine["world_state"]["npcs"]
            ))
            self.assertEqual(winner_session.serialize_game_state(), before_engine)
            self.assertEqual(before_campaign.payload["engine_save"], before_engine)
            self.assertEqual(before_version, (campaign_id, before_campaign.metadata["revision"]))
            self.assertEqual(winner_session._campaign_persistence_version, before_version)
            body = {"message": "Bir tüccar arıyorum.", "action_id": str(uuid.uuid4())}
            winner_body = copy.deepcopy(body)
            if changed_payload:
                winner_body["message"] = "Yakınlarda bir satıcı bulunuyor mu?"
                self.assertNotEqual(winner_body["message"], body["message"])
                self.assertEqual(winner_body["action_id"], body["action_id"])
            if not shared_action:
                winner_body["action_id"] = str(uuid.uuid4())
                self.assertNotEqual(winner_body["action_id"], body["action_id"])
            self.assertIsNone(loser_store.get_turn_action(campaign_id, body["action_id"]))
            self.assertIsNone(winner_store.get_turn_action(campaign_id, winner_body["action_id"]))
            winner_url = f"/api/game/sessions/{winner_id}/turn"
            loser_url = f"/api/game/sessions/{loser_id}/turn"
            results = {"winner": [], "loser": []}

            def observe_turn(session, key):
                real_turn = session.run_player_turn

                @wraps(real_turn)
                def observed(*args, **kwargs):
                    result = real_turn(*args, **kwargs)
                    results[key].append(copy.deepcopy(result["action_result"]))
                    return result

                return observed

            save_reached = threading.Event()
            release_save = threading.Event()
            stale_save_rejected = threading.Event()
            attempts = []
            real_save = loser_store.save_campaign
            real_receipt_read = loser_manager.get_turn_action
            receipt_reads = []
            private_receipt_detail = "private post-save receipt failure"

            @wraps(real_receipt_read)
            def observe_receipt_read(*args, **kwargs):
                after_stale_save = stale_save_rejected.is_set()
                receipt_reads.append({
                    "after_stale_save": after_stale_save,
                    "engine": copy.deepcopy(loser_session.serialize_game_state()),
                    "runtime": loser_runtime_state(),
                    "journal": copy.deepcopy(loser_record.journal),
                    "memory": copy.deepcopy(loser_record.narrative_memory),
                    "receipts": copy.deepcopy(loser_record.turn_action_receipts),
                    "version": loser_session._campaign_persistence_version,
                    "args": args,
                })
                if after_stale_save and post_save_receipt_error is not None:
                    raise post_save_receipt_error(private_receipt_detail)
                return real_receipt_read(*args, **kwargs)

            @wraps(real_save)
            def pause_loser_save(*args, **kwargs):
                attempts.append({
                    "engine": copy.deepcopy(loser_session.serialize_game_state()),
                    "journal": copy.deepcopy(kwargs["journal"]),
                    "memory": copy.deepcopy(kwargs["narrative_memory"]),
                    "receipt": copy.deepcopy(kwargs["turn_action_receipt"]),
                    "version": loser_session._campaign_persistence_version,
                })
                save_reached.set()
                if not release_save.wait(timeout=30):
                    raise AssertionError("The competing first discovery did not release the save.")
                try:
                    return real_save(*args, **kwargs)
                except CampaignStaleError:
                    stale_save_rejected.set()
                    raise

            # Both requests enter against the merchant-free revision. Pause only
            # after the loser's real engine has materialized its first shop.
            with (
                patch.object(
                    loser_session, "run_player_turn", new=observe_turn(loser_session, "loser"),
                ),
                patch.object(
                    winner_session, "run_player_turn", new=observe_turn(winner_session, "winner"),
                ),
                patch.object(loser_store, "save_campaign", side_effect=pause_loser_save) as raced_save,
                patch.object(loser_manager, "get_turn_action", new=observe_receipt_read),
            ):
                pending = asyncio.create_task(loser_http.post(loser_url, json=body))
                try:
                    self.assertTrue(
                        await asyncio.to_thread(save_reached.wait, 30),
                        "First discovery never reached persistence.",
                    )
                    winner = await self._wait_for_merchant_race_request(
                        asyncio.create_task(winner_http.post(winner_url, json=winner_body)),
                    )
                    self.assertEqual(winner.status_code, 200, winner.text)
                    committed = winner_store.get_campaign(campaign_id)
                    committed_rows = receipt_rows()
                    if shared_action and not changed_payload:
                        # Replay through the winner after its commit, while the
                        # competing first discovery is still blocked in save.
                        committed_receipt = winner_store.get_turn_action(
                            campaign_id, winner_body["action_id"],
                        )
                        self.assertEqual(committed_receipt["response"], winner.json())
                        self.assertFalse(release_save.is_set())
                        self.assertFalse(pending.done())
                        self.assertEqual(len(results["winner"]), 1)
                        self.assertEqual(len(results["loser"]), 1)
                        raced_save.assert_called_once()
                        with (
                            patch.object(winner_session, "run_player_turn", side_effect=AssertionError(
                                "Winning-session replay must not execute another turn.",
                            )) as blocked_turn,
                            patch.object(winner_store, "save_campaign", side_effect=AssertionError(
                                "Winning-session replay must not save again.",
                            )) as blocked_save,
                        ):
                            winner_replay = await self._wait_for_merchant_race_request(
                                asyncio.create_task(winner_http.post(winner_url, json=winner_body)),
                            )
                        self.assertEqual(winner_replay.status_code, 200, winner_replay.text)
                        self.assertEqual(winner_replay.json(), winner.json())
                        blocked_turn.assert_not_called()
                        blocked_save.assert_not_called()
                        self.assertFalse(release_save.is_set())
                        self.assertFalse(pending.done())
                        raced_save.assert_called_once()
                        self.assertEqual(len(attempts), 1)
                        self.assertEqual(len(results["winner"]), 1)
                        self.assertEqual(len(results["loser"]), 1)
                        for store in (winner_store, loser_store):
                            after_replay = store.get_campaign(campaign_id)
                            self.assertEqual(after_replay, committed)
                            self.assertEqual(after_replay.history, committed.history)
                            self.assertEqual(
                                after_replay.metadata["revision"], committed.metadata["revision"],
                            )
                            self.assertEqual(
                                store.get_turn_action(campaign_id, winner_body["action_id"]),
                                committed_receipt,
                            )
                        self.assertEqual(receipt_rows(), committed_rows)
                finally:
                    release_save.set()
                    loser = await self._wait_for_merchant_race_request(pending)

            raced_save.assert_called_once()
            if post_save_receipt_error is not None:
                status, code, message = (
                    (503, "campaign_storage_unavailable",
                     "Macera kaydı şu anda güvenli biçimde saklanamıyor.")
                    if post_save_receipt_error is CampaignStorageError
                    else (409, "campaign_unavailable",
                          "Bu macera kaydı güvenli biçimde yüklenemedi.")
                )
                self.assertEqual(loser.status_code, status, loser.text)
                self.assertEqual(loser.json(), {"detail": {"code": code, "message": message}})
                self.assertNotIn(private_receipt_detail, loser.text)
                self.assertTrue(stale_save_rejected.is_set())
                self.assertEqual(
                    [read["after_stale_save"] for read in receipt_reads], [False, True],
                )
                # The second lookup must see a fully restored loser, not just
                # eventually get restored after the receipt read has failed.
                for read in receipt_reads:
                    self.assertIs(read["args"][0], loser_record)
                    self.assertEqual(read["args"][1:], (body["action_id"],))
                    self.assertEqual(read["engine"], before_engine)
                    self.assertEqual(read["runtime"], before_runtime)
                    self.assertEqual(read["journal"], before_journal)
                    self.assertEqual(read["memory"], before_memory)
                    self.assertEqual(read["receipts"], before_receipts)
                    self.assertEqual(read["version"], before_version)
            else:
                self.assertEqual(loser.status_code, 409, loser.text)
                self.assertEqual(
                    loser.json()["detail"]["code"],
                    "action_id_conflict" if changed_payload else "campaign_stale",
                )
            self.assertEqual(len(attempts), 1)
            attempted = attempts[0]
            attempted_world = attempted["engine"]["world_state"]
            saved_world = committed.payload["engine_save"]["world_state"]
            before_npc_ids = {npc["id"] for npc in before_engine["world_state"]["npcs"]}
            for key, world in (("loser", attempted_world), ("winner", saved_world)):
                self.assertEqual(len(results[key]), 1)
                result = results[key][0]
                self.assertEqual(result["action"], "local_search")
                self.assertEqual(result["status"], "found")
                self.assertTrue(result["success"])
                self.assertEqual(world["location"], city_id)
                self.assertEqual(len(world["shops"]), 1)
                shop = world["shops"][0]
                shopkeepers = [npc for npc in world["npcs"] if npc.get("shop_id") == shop["id"]]
                self.assertEqual(len(shopkeepers), 1)
                self.assertEqual(shopkeepers[0]["id"], shop["shopkeeper_id"])
                self.assertNotIn(shop["shopkeeper_id"], before_npc_ids)
                self.assertEqual(result["shop_id"], shop["id"])
                self.assertEqual(result["target_id"], shop["shopkeeper_id"])
                self.assertEqual(
                    world["flags"]["turn_index"],
                    before_engine["world_state"]["flags"]["turn_index"] + 1,
                )
            self.assertNotEqual(attempted["engine"], before_engine)
            self.assertNotEqual(attempted["journal"], before_journal)
            self.assertEqual(attempted["version"], before_version)
            self.assertEqual(attempted["receipt"]["action_id"], body["action_id"])
            self.assertEqual(attempted["receipt"]["response"]["session_id"], loser_id)
            # Full equality includes every newly materialized NPC, not just the
            # shopkeeper: city discovery may also introduce unrelated bystanders.
            self.assertEqual(loser_session.serialize_game_state(), before_engine)
            self.assertEqual(loser_record.journal, before_journal)
            self.assertEqual(loser_record.narrative_memory, before_memory)
            self.assertEqual(loser_record.turn_action_receipts, before_receipts)
            self.assertEqual(loser_session._campaign_persistence_version, before_version)
            self.assertEqual(loser_runtime_state(), before_runtime)
            self.assertEqual(committed.metadata["revision"], before_version[1] + 1)
            self.assertEqual(committed.history[:-1], before_campaign.history)
            self.assertEqual(len(committed.history), len(before_campaign.history) + 1)
            self.assertEqual(committed.history[-1]["player_message"], winner_body["message"])
            self.assertEqual(committed.history[-1]["narration"], winner.json()["narration"])
            self.assertEqual(committed.payload["engine_save"], winner_session.serialize_game_state())
            self.assertEqual(committed.payload["journal"], winner_record.journal)
            self.assertEqual(committed.payload["narrative_memory"], winner_record.narrative_memory)
            self.assertEqual(loser_store.get_campaign(campaign_id), committed)
            self.assertEqual(winner_store.get_campaign(campaign_id), committed)
            self.assertEqual(receipt_rows(), committed_rows)
            self.assertEqual(len(committed_rows), len(before_rows) + 1)
            self.assertTrue(all(row in committed_rows for row in before_rows))
            receipt = winner_store.get_turn_action(campaign_id, winner_body["action_id"])
            self.assertEqual(receipt["response"], winner.json())
            if changed_payload:
                self.assertNotEqual(receipt["request_hash"], attempted["receipt"]["request_hash"])
            else:
                self.assertEqual(receipt["request_hash"], attempted["receipt"]["request_hash"])
            self.assertEqual(receipt["response"]["session_id"], winner_id)
            self.assertEqual(
                loser_store.get_turn_action(campaign_id, winner_body["action_id"]), receipt,
            )
            if shared_action:
                self.assertEqual(loser_store.get_turn_action(campaign_id, body["action_id"]), receipt)
                # Replay must work while the loser still holds its rolled-back,
                # merchant-free revision, without recovering the winning state.
                replay_messages = copy.deepcopy(loser_session.messages)
                replay_rng = loser_session.rng.getstate()
                with (
                    patch.object(loser_session, "run_player_turn", side_effect=AssertionError(
                        "Pre-resume replay must not execute another turn.",
                    )) as blocked_turn,
                    patch.object(loser_store, "save_campaign", side_effect=AssertionError(
                        "Pre-resume replay must not save again.",
                    )) as blocked_save,
                    patch.object(loser_manager, "resume_campaign", side_effect=AssertionError(
                        "Pre-resume replay must not resume the campaign.",
                    )) as blocked_resume,
                    patch.object(main_module, "_restore_session", side_effect=AssertionError(
                        "Pre-resume replay must not restore the engine.",
                    )) as blocked_restore,
                    patch("api.session_manager.restore_stored_campaign", side_effect=AssertionError(
                        "Pre-resume replay must not recover the saved winner.",
                    )) as blocked_recovery,
                ):
                    stale_replay = await asyncio.wait_for(
                        loser_http.post(loser_url, json=winner_body), timeout=30,
                    )
                self.assertEqual(stale_replay.status_code, 200, stale_replay.text)
                expected = copy.deepcopy(winner.json())
                expected["session_id"] = loser_id
                self.assertEqual(stale_replay.json(), expected)
                for blocked in (
                    blocked_turn, blocked_save, blocked_resume, blocked_restore, blocked_recovery,
                ):
                    blocked.assert_not_called()
                self.assertIs(loser_manager.get(loser_id), loser_record)
                self.assertIs(loser_record.game_session, loser_session)
                self.assertEqual(loser_session.serialize_game_state(), before_engine)
                self.assertEqual(loser_session.messages, replay_messages)
                self.assertEqual(loser_session.rng.getstate(), replay_rng)
                self.assertEqual(loser_record.journal, before_journal)
                self.assertEqual(loser_record.narrative_memory, before_memory)
                self.assertEqual(loser_record.turn_action_receipts, before_receipts)
                self.assertEqual(loser_session._campaign_persistence_version, before_version)
                self.assertEqual(loser_store.get_campaign(campaign_id), committed)
                self.assertEqual(winner_store.get_campaign(campaign_id), committed)
                self.assertEqual(receipt_rows(), committed_rows)
                self.assertEqual(loser_store.get_turn_action(campaign_id, body["action_id"]), receipt)
                self.assertEqual(winner_store.get_turn_action(campaign_id, body["action_id"]), receipt)
                self.assertEqual(len(results["winner"]), 1)
                self.assertEqual(len(results["loser"]), 1)
            else:
                self.assertIsNone(loser_store.get_turn_action(campaign_id, body["action_id"]))
                self.assertIsNone(winner_store.get_turn_action(campaign_id, body["action_id"]))
                self.assertIsNone(loser_manager.get_turn_action(loser_record, body["action_id"]))
                if post_save_receipt_error is not None:
                    # Distinct-ID lookup failures end with only the winner
                    # committed. Normal stale/resume/retry has separate coverage.
                    return

            retry_runtime = before_runtime

            def assert_changed_retries_unchanged(stored, engine, journal, memory, receipts, version):
                self.assertIs(loser_manager.get(loser_id), loser_record)
                self.assertIs(loser_record.game_session, loser_session)
                self.assertEqual(loser_session.serialize_game_state(), engine)
                self.assertEqual(loser_record.journal, journal)
                self.assertEqual(loser_record.narrative_memory, memory)
                self.assertEqual(loser_record.turn_action_receipts, receipts)
                self.assertEqual(loser_session._campaign_persistence_version, version)
                self.assertEqual(loser_runtime_state(), retry_runtime)
                self.assertEqual(loser_store.get_campaign(campaign_id), stored)
                self.assertEqual(winner_store.get_campaign(campaign_id), stored)
                self.assertEqual(stored.payload, committed.payload)
                self.assertEqual(stored.history, committed.history)
                self.assertEqual(stored.metadata["revision"], committed.metadata["revision"])
                self.assertEqual(receipt_rows(), committed_rows)
                self.assertEqual(loser_store.get_turn_action(campaign_id, body["action_id"]), receipt)
                self.assertEqual(loser_manager.get_turn_action(loser_record, body["action_id"]), receipt)
                self.assertEqual(len(results["loser"]), 1)
                self.assertEqual(len(results["winner"]), 1)

            if changed_payload:
                # The persistence race rejects the conflicting action ID.
                # Changed-ID retries must reject the payload before recovery,
                # even though this rolled-back session still has no merchant.
                self.assertLess(before_version[1], committed.metadata["revision"])
                with (
                    patch.object(loser_session, "run_player_turn", side_effect=AssertionError(
                        "Pre-resume receipt retries must not execute another first discovery.",
                    )) as blocked_turn,
                    patch.object(loser_store, "save_campaign", side_effect=AssertionError(
                        "Pre-resume receipt retries must not save.",
                    )) as blocked_save,
                    patch.object(loser_manager, "resume_campaign", side_effect=AssertionError(
                        "Pre-resume receipt retries must not recover the session.",
                    )) as blocked_resume,
                    patch("api.session_manager.restore_stored_campaign", side_effect=AssertionError(
                        "Pre-resume receipt retries must not restore saved state.",
                    )) as blocked_restore,
                ):
                    conflict = await asyncio.wait_for(
                        loser_http.post(loser_url, json=body), timeout=30,
                    )
                    self.assertEqual(conflict.status_code, 409, conflict.text)
                    self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
                    for blocked in (blocked_turn, blocked_save, blocked_resume, blocked_restore):
                        blocked.assert_not_called()
                    assert_changed_retries_unchanged(
                        committed, before_engine, before_journal, before_memory,
                        before_receipts, before_version,
                    )
                    replay = await asyncio.wait_for(
                        loser_http.post(loser_url, json=winner_body), timeout=30,
                    )
                    self.assertEqual(replay.status_code, 200, replay.text)
                    expected = copy.deepcopy(winner.json())
                    expected["session_id"] = loser_id
                    self.assertEqual(replay.json(), expected)
                    for blocked in (blocked_turn, blocked_save, blocked_resume, blocked_restore):
                        blocked.assert_not_called()
                    assert_changed_retries_unchanged(
                        committed, before_engine, before_journal, before_memory,
                        before_receipts, before_version,
                    )

            refreshed = await loser_http.post(resume_url)
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], loser_id)
            self.assertEqual(refreshed.json()["history"], committed.history)
            self.assertIs(loser_manager.get(loser_id), loser_record)
            self.assertIs(loser_record.game_session, loser_session)
            self.assertEqual(loser_session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(loser_record.journal, committed.payload["journal"])
            self.assertEqual(loser_record.narrative_memory, committed.payload["narrative_memory"])
            self.assertEqual(
                loser_session._campaign_persistence_version,
                (campaign_id, committed.metadata["revision"]),
            )
            resumed_campaign = loser_store.get_campaign(campaign_id)
            self.assertEqual(resumed_campaign.payload, committed.payload)
            self.assertEqual(resumed_campaign.history, committed.history)
            self.assertEqual(resumed_campaign.metadata["revision"], committed.metadata["revision"])
            self.assertEqual(receipt_rows(), committed_rows)
            retry_runtime = loser_runtime_state()

            if not shared_action:
                # The rejected first search created real local identities, but
                # none survived rollback. Resume must reuse the winner's saved
                # discovery when committing the loser's still-free action ID.
                self.assertIsNone(loser_store.get_turn_action(campaign_id, body["action_id"]))
                self.assertIsNone(loser_manager.get_turn_action(loser_record, body["action_id"]))
                shop = copy.deepcopy(saved_world["shops"][0])
                shopkeepers = [
                    npc for npc in saved_world["npcs"] if npc.get("shop_id") == shop["id"]
                ]

                def assert_saved_discovery(stored):
                    world = stored.payload["engine_save"]["world_state"]
                    self.assertEqual(world["location"], city_id)
                    self.assertEqual(world["shops"], [shop])
                    self.assertEqual(
                        [npc for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                        shopkeepers,
                    )
                    for collection in ("shops", "npcs"):
                        self.assertEqual(
                            [item["id"] for item in world[collection]],
                            [item["id"] for item in saved_world[collection]],
                        )
                    self.assertEqual(
                        loser_store.get_turn_action(campaign_id, winner_body["action_id"]),
                        receipt,
                    )

                if fail_resumed_retry:
                    recovered_engine = copy.deepcopy(loser_session.serialize_game_state())
                    recovered_journal = copy.deepcopy(loser_record.journal)
                    recovered_memory = copy.deepcopy(loser_record.narrative_memory)
                    recovered_receipts = copy.deepcopy(loser_record.turn_action_receipts)
                    recovered_version = loser_session._campaign_persistence_version
                    failed_attempts = []

                    @wraps(real_save)
                    def observe_failed_save(*args, **kwargs):
                        failed_attempts.append({
                            "engine": copy.deepcopy(loser_session.serialize_game_state()),
                            "journal": copy.deepcopy(kwargs["journal"]),
                            "memory": copy.deepcopy(kwargs["narrative_memory"]),
                            "receipt": copy.deepcopy(kwargs["turn_action_receipt"]),
                            "version": loser_session._campaign_persistence_version,
                        })
                        return real_save(*args, **kwargs)

                    # Fail inside the real save transaction at receipt insertion,
                    # after campaign and history writes, not before the turn runs.
                    with closing(sqlite3.connect(self.store.path)) as connection:
                        connection.execute(
                            "CREATE TRIGGER fail_recovered_merchant_receipt "
                            "BEFORE INSERT ON campaign_turn_actions "
                            f"WHEN NEW.action_id = '{body['action_id']}' "
                            "BEGIN SELECT RAISE(ABORT, 'injected merchant save failure'); END"
                        )
                        connection.commit()
                    try:
                        with (
                            patch.object(
                                loser_session, "run_player_turn",
                                new=observe_turn(loser_session, "loser"),
                            ),
                            patch.object(
                                loser_store, "save_campaign", new=observe_failed_save,
                            ),
                        ):
                            failed = await asyncio.wait_for(
                                loser_http.post(loser_url, json=body), timeout=30,
                            )
                    finally:
                        with closing(sqlite3.connect(self.store.path)) as connection:
                            connection.execute("DROP TRIGGER fail_recovered_merchant_receipt")
                            connection.commit()
                    self.assertEqual(failed.status_code, 503, failed.text)
                    self.assertEqual(
                        failed.json()["detail"]["code"], "campaign_storage_unavailable",
                    )
                    self.assertNotIn("injected merchant save failure", failed.text)
                    self.assertEqual(len(failed_attempts), 1)
                    self.assertEqual(len(results["loser"]), 2)
                    self.assertEqual(len(results["winner"]), 1)
                    failed_result = results["loser"][-1]
                    self.assertEqual(failed_result["action"], "local_search")
                    self.assertEqual(failed_result["status"], "found")
                    self.assertTrue(failed_result["success"])
                    self.assertEqual(failed_result["shop_id"], shop["id"])
                    self.assertEqual(failed_result["target_id"], shop["shopkeeper_id"])
                    failed_attempt = failed_attempts[0]
                    failed_world = failed_attempt["engine"]["world_state"]
                    self.assertEqual(
                        failed_world["flags"]["turn_index"],
                        saved_world["flags"]["turn_index"] + 1,
                    )
                    self.assertNotEqual(failed_attempt["engine"], recovered_engine)
                    self.assertEqual(failed_world["shops"], [shop])
                    self.assertEqual(
                        [npc for npc in failed_world["npcs"] if npc.get("shop_id") == shop["id"]],
                        shopkeepers,
                    )
                    for collection in ("shops", "npcs"):
                        self.assertEqual(
                            [item["id"] for item in failed_world[collection]],
                            [item["id"] for item in saved_world[collection]],
                        )
                    self.assertEqual(failed_attempt["version"], recovered_version)
                    self.assertEqual(failed_attempt["receipt"]["action_id"], body["action_id"])
                    self.assertEqual(
                        failed_attempt["receipt"]["request_hash"], attempted["receipt"]["request_hash"],
                    )
                    self.assertEqual(
                        failed_attempt["receipt"]["response"]["session_id"], loser_id,
                    )
                    # Roll back to the recovered winner, never to the original
                    # merchant-free snapshot or the failed retry's staged state.
                    self.assertEqual(loser_session.serialize_game_state(), recovered_engine)
                    self.assertEqual(loser_record.journal, recovered_journal)
                    self.assertEqual(loser_record.narrative_memory, recovered_memory)
                    self.assertEqual(loser_record.turn_action_receipts, recovered_receipts)
                    self.assertEqual(loser_session._campaign_persistence_version, recovered_version)
                    self.assertEqual(loser_store.get_campaign(campaign_id), resumed_campaign)
                    self.assertEqual(winner_store.get_campaign(campaign_id), resumed_campaign)
                    self.assertEqual(receipt_rows(), committed_rows)
                    self.assertIsNone(loser_store.get_turn_action(campaign_id, body["action_id"]))
                    self.assertIsNone(loser_manager.get_turn_action(loser_record, body["action_id"]))
                    self.assertEqual(
                        loser_manager.get_turn_action(loser_record, winner_body["action_id"]), receipt,
                    )
                    assert_saved_discovery(resumed_campaign)

                previous_loser_turns = len(results["loser"])
                with (
                    patch.object(
                        loser_session, "run_player_turn",
                        new=observe_turn(loser_session, "loser"),
                    ),
                    patch.object(loser_store, "save_campaign", wraps=real_save) as retry_save,
                ):
                    retried = await asyncio.wait_for(
                        loser_http.post(loser_url, json=body), timeout=30,
                    )
                self.assertEqual(retried.status_code, 200, retried.text)
                self.assertEqual(retried.json()["action_id"], body["action_id"])
                self.assertEqual(retried.json()["session_id"], loser_id)
                retry_save.assert_called_once()
                self.assertEqual(len(results["loser"]), previous_loser_turns + 1)
                self.assertEqual(len(results["winner"]), 1)
                retry_result = results["loser"][-1]
                self.assertEqual(retry_result["action"], "local_search")
                self.assertEqual(retry_result["status"], "found")
                self.assertTrue(retry_result["success"])
                self.assertEqual(retry_result["shop_id"], shop["id"])
                self.assertEqual(retry_result["target_id"], shop["shopkeeper_id"])
                retried_campaign = loser_store.get_campaign(campaign_id)
                retried_rows = receipt_rows()
                self.assertEqual(
                    retried_campaign.metadata["revision"], committed.metadata["revision"] + 1,
                )
                self.assertEqual(len(retried_campaign.history), len(committed.history) + 1)
                self.assertEqual(retried_campaign.history[:-1], committed.history)
                self.assertEqual(retried_campaign.history[-1]["player_message"], body["message"])
                self.assertEqual(
                    retried_campaign.history[-1]["narration"], retried.json()["narration"],
                )
                self.assertEqual(
                    retried_campaign.payload["engine_save"], loser_session.serialize_game_state(),
                )
                self.assertEqual(retried_campaign.payload["journal"], loser_record.journal)
                self.assertEqual(
                    retried_campaign.payload["narrative_memory"], loser_record.narrative_memory,
                )
                self.assertEqual(
                    loser_session._campaign_persistence_version,
                    (campaign_id, retried_campaign.metadata["revision"]),
                )
                self.assertEqual(
                    retried_campaign.payload["engine_save"]["world_state"]["flags"]["turn_index"],
                    saved_world["flags"]["turn_index"] + 1,
                )
                self.assertEqual(len(retried_rows), len(committed_rows) + 1)
                self.assertTrue(all(row in retried_rows for row in committed_rows))
                retry_receipt = loser_store.get_turn_action(campaign_id, body["action_id"])
                self.assertEqual(retry_receipt["response"], retried.json())
                self.assertEqual(retry_receipt["request_hash"], attempted["receipt"]["request_hash"])
                self.assertEqual(
                    loser_manager.get_turn_action(loser_record, body["action_id"]), retry_receipt,
                )
                assert_saved_discovery(retried_campaign)
                replay_engine = copy.deepcopy(loser_session.serialize_game_state())
                replay_journal = copy.deepcopy(loser_record.journal)
                replay_memory = copy.deepcopy(loser_record.narrative_memory)
                replay_receipts = copy.deepcopy(loser_record.turn_action_receipts)
                replay_version = loser_session._campaign_persistence_version
                with (
                    patch.object(loser_session, "run_player_turn", side_effect=AssertionError(
                        "The accepted distinct-ID retry must not execute another turn.",
                    )) as blocked_turn,
                    patch.object(loser_store, "save_campaign", side_effect=AssertionError(
                        "The accepted distinct-ID retry must not save again.",
                    )) as blocked_save,
                ):
                    replay = await asyncio.wait_for(
                        loser_http.post(loser_url, json=body), timeout=30,
                    )
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), retried.json())
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()
                self.assertEqual(loser_session.serialize_game_state(), replay_engine)
                self.assertEqual(loser_record.journal, replay_journal)
                self.assertEqual(loser_record.narrative_memory, replay_memory)
                self.assertEqual(loser_record.turn_action_receipts, replay_receipts)
                self.assertEqual(loser_session._campaign_persistence_version, replay_version)
                self.assertEqual(loser_store.get_campaign(campaign_id), retried_campaign)
                self.assertEqual(winner_store.get_campaign(campaign_id), retried_campaign)
                self.assertEqual(receipt_rows(), retried_rows)
                self.assertEqual(
                    loser_store.get_turn_action(campaign_id, body["action_id"]), retry_receipt,
                )
                assert_saved_discovery(retried_campaign)
                return

            replay_receipts = copy.deepcopy(loser_record.turn_action_receipts)
            with (
                patch.object(loser_session, "run_player_turn", side_effect=AssertionError(
                    "The shared first-discovery receipt must not execute another turn.",
                )) as blocked_turn,
                patch.object(loser_store, "save_campaign", side_effect=AssertionError(
                    "The shared first-discovery receipt must not save again.",
                )) as blocked_save,
            ):
                if changed_payload:
                    conflict = await asyncio.wait_for(
                        loser_http.post(loser_url, json=body), timeout=30,
                    )
                    self.assertEqual(conflict.status_code, 409, conflict.text)
                    self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
                    blocked_turn.assert_not_called()
                    blocked_save.assert_not_called()
                    assert_changed_retries_unchanged(
                        resumed_campaign, committed.payload["engine_save"],
                        committed.payload["journal"], committed.payload["narrative_memory"],
                        replay_receipts, (campaign_id, committed.metadata["revision"]),
                    )
                replay = await asyncio.wait_for(
                    loser_http.post(loser_url, json=winner_body), timeout=30,
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            expected = copy.deepcopy(winner.json())
            expected["session_id"] = loser_id
            self.assertEqual(replay.json(), expected)
            blocked_turn.assert_not_called()
            blocked_save.assert_not_called()
            self.assertEqual(loser_session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(loser_record.journal, committed.payload["journal"])
            self.assertEqual(loser_record.narrative_memory, committed.payload["narrative_memory"])
            self.assertEqual(loser_record.turn_action_receipts, replay_receipts)
            self.assertEqual(
                loser_session._campaign_persistence_version,
                (campaign_id, committed.metadata["revision"]),
            )
            self.assertEqual(resumed_campaign.payload, committed.payload)
            self.assertEqual(resumed_campaign.history, committed.history)
            self.assertEqual(resumed_campaign.metadata["revision"], committed.metadata["revision"])
            self.assertEqual(loser_store.get_campaign(campaign_id), resumed_campaign)
            self.assertEqual(winner_store.get_campaign(campaign_id), resumed_campaign)
            self.assertEqual(receipt_rows(), committed_rows)
            self.assertEqual(loser_store.get_turn_action(campaign_id, body["action_id"]), receipt)
            self.assertEqual(len(results["winner"]), 1)
            self.assertEqual(len(results["loser"]), 1)
            if changed_payload:
                assert_changed_retries_unchanged(
                    resumed_campaign, committed.payload["engine_save"],
                    committed.payload["journal"], committed.payload["narrative_memory"],
                    replay_receipts, (campaign_id, committed.metadata["revision"]),
                )

    async def test_recovered_merchant_search_save_race_rolls_back_and_retries_once(self):
        await self._assert_recovered_merchant_search_save_race(shared_action=False)

    async def test_recovered_merchant_search_same_id_race_rolls_back_and_replays_winner(self):
        await self._assert_recovered_merchant_search_save_race(shared_action=True)

    async def test_recovered_merchant_search_same_id_changed_payload_race_rejects_loser(self):
        await self._assert_recovered_merchant_search_save_race(
            shared_action=True, changed_payload=True,
        )

    async def test_recovered_merchant_search_paused_winner_receipt_storage_error_is_safe(self):
        for shared_action, changed_payload in ((False, False), (True, False), (True, True)):
            with self.subTest(shared_action=shared_action, changed_payload=changed_payload):
                await self._assert_recovered_merchant_search_save_race(
                    shared_action=shared_action, changed_payload=changed_payload,
                    paused_receipt_error=CampaignStorageError,
                )

    async def test_recovered_merchant_search_paused_winner_receipt_corrupt_error_is_safe(self):
        for shared_action, changed_payload in ((False, False), (True, False), (True, True)):
            with self.subTest(shared_action=shared_action, changed_payload=changed_payload):
                await self._assert_recovered_merchant_search_save_race(
                    shared_action=shared_action, changed_payload=changed_payload,
                    paused_receipt_error=CampaignCorruptError,
                )

    async def test_recovered_merchant_save_race_winner_timeout_drains_workers_before_teardown(self):
        await self._assert_recovered_merchant_timeout_cleanup(timeout_winner=True)

    async def test_recovered_merchant_save_race_loser_timeout_drains_workers_before_teardown(self):
        await self._assert_recovered_merchant_timeout_cleanup(timeout_winner=False)

    async def _assert_recovered_merchant_timeout_cleanup(self, *, timeout_winner):
        worker_entered = threading.Event()
        release_worker = threading.Event()
        worker_finished = threading.Event()
        real_save = CampaignStore.save_campaign
        real_wait_for = asyncio.wait_for
        real_exit = httpx.AsyncClient.__aexit__
        real_request_wait = self._wait_for_merchant_race_request
        turn_saves = []
        request_tasks = []
        exited_clients = []
        worker_checks = []
        timed_out = False

        def delayed_save(store, *args, **kwargs):
            if kwargs.get("turn_action_receipt") is not None:
                turn_saves.append(store)
                is_recovered = callable(getattr(store.save_campaign, "side_effect", None))
                # Ignore the initial discovery. Delay either the competing
                # winner or the recovered save after its instance barrier opens.
                if (timeout_winner and len(turn_saves) == 2) or (
                    not timeout_winner and is_recovered
                ):
                    worker_entered.set()
                    if not release_worker.wait(timeout=5):
                        raise AssertionError("Recovered timeout injection did not release the worker.")
                    try:
                        worker_checks.append((
                            CampaignStore.save_campaign is delayed_save,
                            callable(getattr(store.save_campaign, "side_effect", None)),
                            self.store.path.exists(),
                        ))
                        return real_save(store, *args, **kwargs)
                    finally:
                        worker_finished.set()
            return real_save(store, *args, **kwargs)

        async def observed_request_wait(task):
            request_tasks.append(task)
            return await real_request_wait(task)

        async def injected_wait_for(awaitable, timeout):
            nonlocal timed_out
            # Without a shared action, the helper waits for the winner, its
            # changed-payload conflict, then the recovered losing request.
            target_wait = 1 if timeout_winner else 3
            if timeout == 30 and len(request_tasks) == target_wait and not timed_out:
                self.assertTrue(await asyncio.to_thread(worker_entered.wait, 5))
                self.assertFalse(worker_finished.is_set())
                self.assertTrue(all(not client.is_closed for client in turn_clients))
                # Cancel the timeout wrapper, never the underlying ASGI task.
                awaitable.cancel()
                timed_out = True
                asyncio.get_running_loop().call_soon(release_worker.set)
                raise TimeoutError("injected recovered merchant request timeout")
            return await real_wait_for(awaitable, timeout)

        turn_clients = []
        real_enter = httpx.AsyncClient.__aenter__

        async def observed_enter(client):
            turn_clients.append(client)
            return await real_enter(client)

        async def checked_exit(client, *args):
            self.assertTrue(timed_out)
            self.assertFalse(client.is_closed)
            self.assertTrue(worker_finished.is_set())
            self.assertTrue(all(task.done() and not task.cancelled() for task in request_tasks))
            self.assertEqual(len(turn_saves), 3)
            exited_clients.append(client)
            return await real_exit(client, *args)

        try:
            with (
                patch.object(CampaignStore, "save_campaign", new=delayed_save),
                patch.object(asyncio, "wait_for", new=injected_wait_for),
                patch.object(self, "_wait_for_merchant_race_request", new=observed_request_wait),
                patch.object(httpx.AsyncClient, "__aenter__", new=observed_enter),
                patch.object(httpx.AsyncClient, "__aexit__", new=checked_exit),
            ):
                with self.assertRaisesRegex(TimeoutError, "injected recovered merchant request timeout"):
                    await self._assert_recovered_merchant_search_save_race(shared_action=False)
                self.assertTrue(timed_out)
                self.assertTrue(worker_finished.is_set())
                self.assertEqual(worker_checks, [(True, not timeout_winner, True)])
                self.assertEqual(len(request_tasks), 2 if timeout_winner else 3)
                self.assertEqual(len(exited_clients), 2)
                self.assertTrue(all(task.done() and not task.cancelled() for task in request_tasks))
                # Both real accepted turns remain readable before the patches
                # and temporary SQLite fixture can be torn down.
                with closing(sqlite3.connect(self.store.path)) as connection:
                    self.assertEqual(connection.execute(
                        "SELECT COUNT(*) FROM campaign_turn_actions",
                    ).fetchone()[0], 2)
        finally:
            release_worker.set()

    async def _assert_recovered_merchant_search_save_race(
        self, *, shared_action, changed_payload=False, paused_receipt_error=None,
    ):
        city_id = "fr:city:neverwinter"
        created = await self.http.post(
            "/api/game/campaigns",
            json={"campaign_start": {
                "setting_id": "forgotten_realms",
                "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                "region_id": "fr:region:the_north",
                "starting_location_id": city_id,
            }},
        )
        self.assertEqual(created.status_code, 200, created.text)
        campaign_id = created.json()["campaign_id"]
        resume_url = f"/api/game/campaigns/{campaign_id}/resume"
        active_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        recovered_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        active_manager = SessionManager(campaign_store=active_store)
        recovered_manager = SessionManager(campaign_store=recovered_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        recovered_app = create_app(
            session_manager=recovered_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))

        def receipt_rows():
            with closing(sqlite3.connect(self.store.path)) as connection:
                return connection.execute(
                    "SELECT * FROM campaign_turn_actions WHERE campaign_id = ? "
                    "ORDER BY action_id", (campaign_id,),
                ).fetchall()

        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=recovered_app),
                base_url="http://testserver",
            ) as recovered_http,
        ):
            active_resume = await active_http.post(resume_url)
            stale_resume = await recovered_http.post(resume_url)
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
            active_id = active_resume.json()["session_id"]
            recovered_id = stale_resume.json()["session_id"]
            active_session = active_manager.get(active_id).game_session
            record = recovered_manager.get(recovered_id)
            session = record.game_session
            self.assertIsNot(active_store, recovered_store)
            self.assertIsNot(active_manager, recovered_manager)
            self.assertNotEqual(active_id, recovered_id)
            self.assertIsNot(active_session, session)
            self.assertIsNot(active_session.world_state, session.world_state)
            self.assertEqual(session.world_state["shops"], [])
            active_url = f"/api/game/sessions/{active_id}/turn"
            recovered_url = f"/api/game/sessions/{recovered_id}/turn"
            discovery_body = {
                "message": "Bir tüccar arıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            discovered = await active_http.post(active_url, json=discovery_body)
            self.assertEqual(discovered.status_code, 200, discovered.text)
            discovery = active_store.get_campaign(campaign_id)
            discovery_receipt = copy.deepcopy(active_store.get_turn_action(
                campaign_id, discovery_body["action_id"]
            ))
            self.assertEqual(discovery_receipt["response"], discovered.json())
            saved_world = discovery.payload["engine_save"]["world_state"]
            self.assertEqual(len(saved_world["shops"]), 1)
            shop = copy.deepcopy(saved_world["shops"][0])
            shopkeepers = [
                npc for npc in saved_world["npcs"] if npc.get("shop_id") == shop["id"]
            ]
            self.assertEqual(len(shopkeepers), 1)
            self.assertEqual(shopkeepers[0]["id"], shop["shopkeeper_id"])

            def assert_identities_and_discovery(stored):
                world = stored.payload["engine_save"]["world_state"]
                self.assertEqual(world["location"], city_id)
                self.assertEqual(world["shops"], [shop])
                self.assertEqual(
                    [npc for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                    shopkeepers,
                )
                for collection in ("shops", "npcs"):
                    self.assertEqual(
                        [item["id"] for item in world[collection]],
                        [item["id"] for item in saved_world[collection]],
                    )
                self.assertEqual(
                    recovered_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                    discovery_receipt,
                )

            rejected_body = {
                "message": "Yakınlarda bir satıcı bulunuyor mu?",
                "action_id": str(uuid.uuid4()),
            }
            # First become stale, then explicitly recover the SAME cached session.
            stale = await recovered_http.post(recovered_url, json=rejected_body)
            self.assertEqual(stale.status_code, 409, stale.text)
            self.assertEqual(stale.json()["detail"]["code"], "campaign_stale")
            resumed = await recovered_http.post(resume_url)
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["session_id"], recovered_id)
            self.assertIs(recovered_manager.get(recovered_id), record)
            self.assertIs(record.game_session, session)
            self.assertEqual(session.serialize_game_state(), discovery.payload["engine_save"])
            self.assertEqual(record.journal, discovery.payload["journal"])
            before_race = recovered_store.get_campaign(campaign_id)
            before_save = copy.deepcopy(session.serialize_game_state())
            before_journal = copy.deepcopy(record.journal)
            before_memory = copy.deepcopy(record.narrative_memory)
            before_receipts = copy.deepcopy(record.turn_action_receipts)
            before_version = session._campaign_persistence_version
            before_rows = receipt_rows()
            self.assertEqual(before_version, (campaign_id, before_race.metadata["revision"]))
            self.assertEqual(active_session._campaign_persistence_version, before_version)
            self.assertIsNone(recovered_store.get_turn_action(
                campaign_id, rejected_body["action_id"]
            ))

            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def observe_search(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result["action_result"]))
                return result

            save_reached = threading.Event()
            release_save = threading.Event()
            attempts = []
            real_save = recovered_store.save_campaign

            @wraps(real_save)
            def pause_recovered_save(*args, **kwargs):
                attempts.append({
                    "engine": copy.deepcopy(session.serialize_game_state()),
                    "journal": copy.deepcopy(kwargs["journal"]),
                    "memory": copy.deepcopy(kwargs["narrative_memory"]),
                    "receipt": copy.deepcopy(kwargs["turn_action_receipt"]),
                    "version": session._campaign_persistence_version,
                })
                save_reached.set()
                if not release_save.wait(timeout=30):
                    raise AssertionError("The competing HTTP turn did not release the save.")
                return real_save(*args, **kwargs)

            competing_body = {
                "message": "Bir tüccar arıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            if shared_action:
                competing_body["action_id"] = rejected_body["action_id"]
                if changed_payload:
                    self.assertNotEqual(competing_body["message"], rejected_body["message"])
                else:
                    competing_body = copy.deepcopy(rejected_body)
                    self.assertEqual(competing_body, rejected_body)
            active_results = []
            real_active_turn = active_session.run_player_turn

            @wraps(real_active_turn)
            def observe_competing_search(*args, **kwargs):
                result = real_active_turn(*args, **kwargs)
                active_results.append(copy.deepcopy(result["action_result"]))
                return result

            # The barrier is after entry validation AND the real recovered turn,
            # but before the store's transactional revision check. No sleeps or
            # injected storage exceptions substitute for the competing commit.
            with (
                patch.object(session, "run_player_turn", new=observe_search),
                patch.object(active_session, "run_player_turn", new=observe_competing_search),
                patch.object(
                    recovered_store, "save_campaign", side_effect=pause_recovered_save
                ) as raced_save,
            ):
                pending = asyncio.create_task(
                    recovered_http.post(recovered_url, json=rejected_body)
                )
                try:
                    self.assertTrue(
                        await asyncio.to_thread(save_reached.wait, 30),
                        "Recovered request never reached persistence.",
                    )
                    competing = await self._wait_for_merchant_race_request(
                        asyncio.create_task(active_http.post(active_url, json=competing_body)),
                    )
                    self.assertEqual(competing.status_code, 200, competing.text)
                    newer = active_store.get_campaign(campaign_id)
                    newer_rows = receipt_rows()
                    # Changed reuse must be rejected through the winning session
                    # before the losing save is released, in every race variant.
                    committed_receipt = active_store.get_turn_action(
                        campaign_id, competing_body["action_id"],
                    )
                    self.assertEqual(committed_receipt["response"], competing.json())
                    changed_retry_body = {
                        **competing_body,
                        "message": "Çevreme bakıyorum.",
                    }
                    self.assertNotEqual(changed_retry_body["message"], competing_body["message"])
                    self.assertFalse(release_save.is_set())
                    self.assertFalse(pending.done())
                    with (
                        patch.object(active_session, "run_player_turn", side_effect=AssertionError(
                            "Winning-session changed retry must not execute another search.",
                        )) as conflict_turn,
                        patch.object(active_store, "save_campaign", side_effect=AssertionError(
                            "Winning-session changed retry must not save again.",
                        )) as conflict_save,
                    ):
                        winner_conflict = await self._wait_for_merchant_race_request(
                            asyncio.create_task(active_http.post(active_url, json=changed_retry_body)),
                        )
                    self.assertEqual(winner_conflict.status_code, 409, winner_conflict.text)
                    self.assertEqual(
                        winner_conflict.json()["detail"]["code"], "action_id_conflict",
                    )
                    conflict_turn.assert_not_called()
                    conflict_save.assert_not_called()
                    self.assertFalse(release_save.is_set())
                    self.assertFalse(pending.done())
                    raced_save.assert_called_once()
                    self.assertEqual(len(attempts), 1)
                    self.assertEqual(len(active_results), 1)
                    self.assertEqual(len(results), 1)
                    for store in (active_store, recovered_store):
                        after_conflict = store.get_campaign(campaign_id)
                        self.assertEqual(after_conflict, newer)
                        self.assertEqual(after_conflict.payload, newer.payload)
                        self.assertEqual(after_conflict.history, newer.history)
                        self.assertEqual(
                            after_conflict.metadata["revision"], newer.metadata["revision"],
                        )
                        self.assertEqual(
                            store.get_turn_action(campaign_id, competing_body["action_id"]),
                            committed_receipt,
                        )
                    self.assertEqual(receipt_rows(), newer_rows)
                    if shared_action and not changed_payload:
                        # Replay the committed winner while the recovered
                        # request is still paused before its revision check.
                        self.assertFalse(release_save.is_set())
                        self.assertFalse(pending.done())
                        self.assertEqual(len(active_results), 1)
                        self.assertEqual(len(results), 1)
                        raced_save.assert_called_once()
                        with (
                            patch.object(active_session, "run_player_turn", side_effect=AssertionError(
                                "Winning-session replay must not execute another search.",
                            )) as blocked_turn,
                            patch.object(active_store, "save_campaign", side_effect=AssertionError(
                                "Winning-session replay must not save again.",
                            )) as blocked_save,
                        ):
                            winner_replay = await self._wait_for_merchant_race_request(
                                asyncio.create_task(active_http.post(active_url, json=competing_body)),
                            )
                        self.assertEqual(winner_replay.status_code, 200, winner_replay.text)
                        self.assertEqual(winner_replay.json(), competing.json())
                        blocked_turn.assert_not_called()
                        blocked_save.assert_not_called()
                        self.assertFalse(release_save.is_set())
                        self.assertFalse(pending.done())
                        raced_save.assert_called_once()
                        self.assertEqual(len(attempts), 1)
                        self.assertEqual(len(active_results), 1)
                        self.assertEqual(len(results), 1)
                        for store in (active_store, recovered_store):
                            after_replay = store.get_campaign(campaign_id)
                            self.assertEqual(after_replay, newer)
                            self.assertEqual(after_replay.history, newer.history)
                            self.assertEqual(
                                after_replay.metadata["revision"], newer.metadata["revision"],
                            )
                            self.assertEqual(
                                store.get_turn_action(campaign_id, competing_body["action_id"]),
                                committed_receipt,
                            )
                        self.assertEqual(receipt_rows(), newer_rows)
                    if paused_receipt_error is not None:
                        # Fail only the winner's durable receipt read. The losing
                        # save must remain paused, and its later rollback lookup
                        # must use the restored, independent store.
                        winner_record = active_manager.get(active_id)
                        winner_engine = copy.deepcopy(active_session.serialize_game_state())
                        winner_journal = copy.deepcopy(winner_record.journal)
                        winner_memory = copy.deepcopy(winner_record.narrative_memory)
                        winner_receipts = copy.deepcopy(winner_record.turn_action_receipts)
                        winner_version = active_session._campaign_persistence_version
                        real_lookup = active_store.get_turn_action
                        private_detail = "private paused winner receipt lookup failure"
                        self.assertFalse(release_save.is_set())
                        self.assertFalse(pending.done())
                        with (
                            patch.object(
                                active_store, "get_turn_action",
                                side_effect=paused_receipt_error(private_detail),
                            ) as failed_lookup,
                            patch.object(active_session, "run_player_turn", side_effect=AssertionError(
                                "Unreadable winner receipt must not execute another search.",
                            )) as blocked_turn,
                            patch.object(active_store, "save_campaign", side_effect=AssertionError(
                                "Unreadable winner receipt must not save again.",
                            )) as blocked_save,
                        ):
                            failed_retry = await self._wait_for_merchant_race_request(
                                asyncio.create_task(active_http.post(active_url, json=competing_body)),
                            )
                            failed_lookup.assert_called_once_with(
                                campaign_id, competing_body["action_id"], principal=TEST_PLAYER,
                            )
                            blocked_turn.assert_not_called()
                            blocked_save.assert_not_called()
                        status, code, message = (
                            (503, "campaign_storage_unavailable",
                             "Macera kaydı şu anda güvenli biçimde saklanamıyor.")
                            if paused_receipt_error is CampaignStorageError
                            else (409, "campaign_unavailable",
                                  "Bu macera kaydı güvenli biçimde yüklenemedi.")
                        )
                        self.assertEqual(failed_retry.status_code, status, failed_retry.text)
                        self.assertEqual(
                            failed_retry.json(), {"detail": {"code": code, "message": message}},
                        )
                        self.assertNotIn(private_detail, failed_retry.text)
                        self.assertEqual(active_store.get_turn_action, real_lookup)
                        self.assertFalse(release_save.is_set())
                        self.assertFalse(pending.done())
                        raced_save.assert_called_once()
                        self.assertEqual(len(attempts), 1)
                        self.assertEqual(len(active_results), 1)
                        self.assertEqual(len(results), 1)
                        self.assertEqual(active_session.serialize_game_state(), winner_engine)
                        self.assertEqual(winner_record.journal, winner_journal)
                        self.assertEqual(winner_record.narrative_memory, winner_memory)
                        self.assertEqual(winner_record.turn_action_receipts, winner_receipts)
                        self.assertEqual(active_session._campaign_persistence_version, winner_version)
                        for store in (active_store, recovered_store):
                            after_failure = store.get_campaign(campaign_id)
                            self.assertEqual(after_failure, newer)
                            self.assertEqual(after_failure.payload, newer.payload)
                            self.assertEqual(after_failure.history, newer.history)
                            self.assertEqual(
                                after_failure.metadata["revision"], newer.metadata["revision"],
                            )
                            self.assertEqual(
                                store.get_turn_action(campaign_id, competing_body["action_id"]),
                                committed_receipt,
                            )
                        self.assertEqual(receipt_rows(), newer_rows)
                finally:
                    release_save.set()
                    rejected = await self._wait_for_merchant_race_request(pending)
            raced_save.assert_called_once()
            self.assertEqual(rejected.status_code, 409, rejected.text)
            self.assertEqual(
                rejected.json()["detail"]["code"],
                "action_id_conflict" if changed_payload else "campaign_stale",
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(len(active_results), 1)
            self.assertEqual(active_results[0]["action"], "local_search")
            self.assertEqual(active_results[0]["status"], "found")
            self.assertTrue(active_results[0]["success"])
            self.assertEqual(active_results[0]["shop_id"], shop["id"])
            self.assertEqual(active_results[0]["target_id"], shop["shopkeeper_id"])
            self.assertEqual(results[0]["action"], "local_search")
            self.assertEqual(results[0]["status"], "found")
            self.assertTrue(results[0]["success"])
            self.assertEqual(results[0]["shop_id"], shop["id"])
            self.assertEqual(results[0]["target_id"], shop["shopkeeper_id"])
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["version"], before_version)
            self.assertEqual(
                attempts[0]["engine"]["world_state"]["flags"]["turn_index"],
                before_save["world_state"]["flags"]["turn_index"] + 1,
            )
            self.assertNotEqual(attempts[0]["journal"], before_journal)
            self.assertEqual(attempts[0]["receipt"]["action_id"], rejected_body["action_id"])
            self.assertEqual(attempts[0]["engine"]["world_state"]["shops"], [shop])
            self.assertEqual(session.serialize_game_state(), before_save)
            self.assertEqual(record.journal, before_journal)
            self.assertEqual(record.narrative_memory, before_memory)
            self.assertEqual(record.turn_action_receipts, before_receipts)
            self.assertEqual(session._campaign_persistence_version, before_version)
            self.assertEqual(newer.metadata["revision"], before_version[1] + 1)
            self.assertEqual(len(newer.history), len(before_race.history) + 1)
            self.assertEqual(newer.history[:-1], before_race.history)
            self.assertEqual(newer.history[-1]["player_message"], competing_body["message"])
            self.assertEqual(newer.payload["engine_save"], active_session.serialize_game_state())
            self.assertEqual(
                newer.payload["engine_save"]["world_state"]["flags"]["turn_index"],
                before_save["world_state"]["flags"]["turn_index"] + 1,
            )
            self.assertEqual(active_store.get_campaign(campaign_id), newer)
            self.assertEqual(recovered_store.get_campaign(campaign_id), newer)
            self.assertEqual(receipt_rows(), newer_rows)
            self.assertEqual(len(newer_rows), len(before_rows) + 1)
            self.assertTrue(all(row in newer_rows for row in before_rows))
            competing_receipt = active_store.get_turn_action(
                campaign_id, competing_body["action_id"]
            )
            self.assertEqual(competing_receipt["response"], competing.json())
            if shared_action:
                if changed_payload:
                    self.assertNotEqual(
                        attempts[0]["receipt"]["request_hash"],
                        competing_receipt["request_hash"],
                    )
                else:
                    self.assertEqual(
                        attempts[0]["receipt"]["request_hash"], competing_receipt["request_hash"],
                    )
                self.assertEqual(
                    attempts[0]["receipt"]["response"]["session_id"], recovered_id,
                )
                self.assertEqual(competing_receipt["response"]["session_id"], active_id)
                self.assertEqual(
                    recovered_store.get_turn_action(campaign_id, rejected_body["action_id"]),
                    competing_receipt,
                )
                self.assertEqual(
                    recovered_manager.get_turn_action(record, rejected_body["action_id"]),
                    competing_receipt,
                )
            else:
                self.assertIsNone(recovered_store.get_turn_action(
                    campaign_id, rejected_body["action_id"]
                ))
                self.assertIsNone(recovered_manager.get_turn_action(record, rejected_body["action_id"]))
            assert_identities_and_discovery(newer)

            if shared_action:
                # Rollback left this session one revision behind. Receipt
                # validation must still precede stale-session recovery, both
                # for a changed losing payload and an exact replay of the winner.
                def assert_stale_retry_unchanged():
                    self.assertIs(recovered_manager.get(recovered_id), record)
                    self.assertIs(record.game_session, session)
                    self.assertEqual(session.serialize_game_state(), before_save)
                    self.assertEqual(record.journal, before_journal)
                    self.assertEqual(record.narrative_memory, before_memory)
                    self.assertEqual(record.turn_action_receipts, before_receipts)
                    self.assertEqual(session._campaign_persistence_version, before_version)
                    self.assertEqual(recovered_store.get_campaign(campaign_id), newer)
                    self.assertEqual(active_store.get_campaign(campaign_id), newer)
                    self.assertEqual(receipt_rows(), newer_rows)
                    self.assertEqual(
                        recovered_store.get_turn_action(campaign_id, competing_body["action_id"]),
                        competing_receipt,
                    )
                    self.assertEqual(
                        recovered_manager.get_turn_action(record, rejected_body["action_id"]),
                        competing_receipt,
                    )
                    assert_identities_and_discovery(newer)

                self.assertLess(before_version[1], newer.metadata["revision"])
                with (
                    patch.object(session, "run_player_turn", side_effect=AssertionError(
                        "Pre-resume receipt retries must not execute another search."
                    )) as blocked_turn,
                    patch.object(recovered_store, "save_campaign", side_effect=AssertionError(
                        "Pre-resume receipt retries must not save."
                    )) as blocked_save,
                    patch.object(recovered_manager, "resume_campaign", side_effect=AssertionError(
                        "Pre-resume receipt retries must not recover the session."
                    )) as blocked_resume,
                    patch("api.session_manager.restore_stored_campaign", side_effect=AssertionError(
                        "Pre-resume receipt retries must not restore saved state."
                    )) as blocked_restore,
                ):
                    if changed_payload:
                        conflict = await self._wait_for_merchant_race_request(
                            asyncio.create_task(recovered_http.post(recovered_url, json=rejected_body)),
                        )
                        self.assertEqual(conflict.status_code, 409, conflict.text)
                        self.assertEqual(conflict.json()["detail"]["code"], "action_id_conflict")
                        blocked_turn.assert_not_called()
                        blocked_save.assert_not_called()
                        blocked_resume.assert_not_called()
                        blocked_restore.assert_not_called()
                        assert_stale_retry_unchanged()

                    replay = await self._wait_for_merchant_race_request(
                        asyncio.create_task(recovered_http.post(recovered_url, json=competing_body)),
                    )
                    self.assertEqual(replay.status_code, 200, replay.text)
                    expected = copy.deepcopy(competing.json())
                    expected["session_id"] = recovered_id
                    self.assertEqual(replay.json(), expected)
                    blocked_turn.assert_not_called()
                    blocked_save.assert_not_called()
                    blocked_resume.assert_not_called()
                    blocked_restore.assert_not_called()
                    assert_stale_retry_unchanged()
                self.assertEqual(len(results), 1)
                self.assertEqual(len(active_results), 1)

            refreshed = await recovered_http.post(resume_url)
            self.assertEqual(refreshed.status_code, 200, refreshed.text)
            self.assertEqual(refreshed.json()["session_id"], recovered_id)
            self.assertEqual(refreshed.json()["history"], newer.history)
            self.assertEqual(session.serialize_game_state(), newer.payload["engine_save"])
            self.assertEqual(record.journal, newer.payload["journal"])
            self.assertEqual(record.narrative_memory, newer.payload["narrative_memory"])
            self.assertEqual(session._campaign_persistence_version, (campaign_id, newer.metadata["revision"]))
            self.assertEqual(receipt_rows(), newer_rows)

            if shared_action:
                # The winner already owns the shared ID. Recovery must replay its
                # response, not commit the loser's previously rolled-back turn.
                resumed_campaign = recovered_store.get_campaign(campaign_id)
                replay_save = copy.deepcopy(session.serialize_game_state())
                replay_journal = copy.deepcopy(record.journal)
                replay_memory = copy.deepcopy(record.narrative_memory)
                replay_receipts = copy.deepcopy(record.turn_action_receipts)
                replay_version = session._campaign_persistence_version

                def assert_shared_receipt_unchanged():
                    self.assertEqual(session.serialize_game_state(), replay_save)
                    self.assertEqual(record.journal, replay_journal)
                    self.assertEqual(record.narrative_memory, replay_memory)
                    self.assertEqual(record.turn_action_receipts, replay_receipts)
                    self.assertEqual(session._campaign_persistence_version, replay_version)
                    self.assertEqual(recovered_store.get_campaign(campaign_id), resumed_campaign)
                    self.assertEqual(active_store.get_campaign(campaign_id), resumed_campaign)
                    self.assertEqual(receipt_rows(), newer_rows)
                    self.assertEqual(
                        recovered_store.get_turn_action(campaign_id, rejected_body["action_id"]),
                        competing_receipt,
                    )
                    self.assertEqual(
                        recovered_manager.get_turn_action(record, rejected_body["action_id"]),
                        competing_receipt,
                    )
                    assert_identities_and_discovery(resumed_campaign)

                with (
                    patch.object(session, "run_player_turn", side_effect=AssertionError(
                        "The winning shared receipt must not execute another search."
                    )) as blocked_turn,
                    patch.object(recovered_store, "save_campaign", side_effect=AssertionError(
                        "The winning shared receipt must not save again."
                    )) as blocked_save,
                ):
                    if changed_payload:
                        conflict = await self._wait_for_merchant_race_request(
                            asyncio.create_task(recovered_http.post(recovered_url, json=rejected_body)),
                        )
                        self.assertEqual(conflict.status_code, 409, conflict.text)
                        self.assertEqual(
                            conflict.json()["detail"]["code"], "action_id_conflict",
                        )
                        blocked_turn.assert_not_called()
                        blocked_save.assert_not_called()
                        assert_shared_receipt_unchanged()
                    replay = await self._wait_for_merchant_race_request(
                        asyncio.create_task(recovered_http.post(recovered_url, json=competing_body)),
                    )
                self.assertEqual(replay.status_code, 200, replay.text)
                expected = copy.deepcopy(competing.json())
                expected["session_id"] = recovered_id
                self.assertEqual(replay.json(), expected)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()
                self.assertEqual(len(results), 1)
                self.assertEqual(len(active_results), 1)
                assert_shared_receipt_unchanged()
                self.assertEqual(resumed_campaign.payload, newer.payload)
                self.assertEqual(resumed_campaign.history, newer.history)
                self.assertEqual(resumed_campaign.metadata["revision"], newer.metadata["revision"])
                return

            # The failed ID is still free: one real retry commits, then replay
            # returns that accepted receipt without executing or saving again.
            with (
                patch.object(session, "run_player_turn", new=observe_search),
                patch.object(recovered_store, "save_campaign", wraps=real_save) as retry_save,
            ):
                retried = await recovered_http.post(recovered_url, json=rejected_body)
            self.assertEqual(retried.status_code, 200, retried.text)
            retry_save.assert_called_once()
            self.assertEqual(len(results), 2)
            self.assertEqual(results[1]["action"], "local_search")
            self.assertEqual(results[1]["status"], "found")
            self.assertTrue(results[1]["success"])
            self.assertEqual(results[1]["shop_id"], shop["id"])
            self.assertEqual(results[1]["target_id"], shop["shopkeeper_id"])
            committed = recovered_store.get_campaign(campaign_id)
            committed_rows = receipt_rows()
            self.assertEqual(committed.metadata["revision"], newer.metadata["revision"] + 1)
            self.assertEqual(len(committed.history), len(newer.history) + 1)
            self.assertEqual(committed.history[:-1], newer.history)
            self.assertEqual(committed.history[-1]["player_message"], rejected_body["message"])
            self.assertEqual(committed.payload["engine_save"], session.serialize_game_state())
            self.assertEqual(committed.payload["journal"], record.journal)
            self.assertEqual(committed.payload["narrative_memory"], record.narrative_memory)
            self.assertEqual(len(committed_rows), len(newer_rows) + 1)
            self.assertTrue(all(row in committed_rows for row in newer_rows))
            retry_receipt = recovered_store.get_turn_action(campaign_id, rejected_body["action_id"])
            self.assertEqual(retry_receipt["response"], retried.json())
            assert_identities_and_discovery(committed)

            replay_save = copy.deepcopy(session.serialize_game_state())
            replay_journal = copy.deepcopy(record.journal)
            replay_memory = copy.deepcopy(record.narrative_memory)
            replay_receipts = copy.deepcopy(record.turn_action_receipts)
            with (
                patch.object(session, "run_player_turn", side_effect=AssertionError(
                    "Receipt replay must not execute another merchant search."
                )) as blocked_turn,
                patch.object(recovered_store, "save_campaign", side_effect=AssertionError(
                    "Receipt replay must not save."
                )) as blocked_save,
            ):
                replay = await recovered_http.post(recovered_url, json=rejected_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retried.json())
            blocked_turn.assert_not_called()
            blocked_save.assert_not_called()
            self.assertEqual(session.serialize_game_state(), replay_save)
            self.assertEqual(record.journal, replay_journal)
            self.assertEqual(record.narrative_memory, replay_memory)
            self.assertEqual(record.turn_action_receipts, replay_receipts)
            self.assertEqual(recovered_store.get_campaign(campaign_id), committed)
            self.assertEqual(active_store.get_campaign(campaign_id), committed)
            self.assertEqual(receipt_rows(), committed_rows)
            self.assertEqual(recovered_store.get_turn_action(
                campaign_id, rejected_body["action_id"]
            ), retry_receipt)
            self.assertEqual(recovered_store.get_turn_action(
                campaign_id, competing_body["action_id"]
            ), competing_receipt)
            assert_identities_and_discovery(committed)

    async def test_reopened_merchant_search_with_equivalent_wording_reuses_saved_identities(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        requests = [
            {"message": message, "action_id": str(uuid.uuid4())}
            for message in (
                "Buralarda bir tücaar var mı?",
                "Bir tüccar arıyorum.",
                "Yakınlarda bir satıcı bulunuyor mu?",
            )
        ]
        self.assertEqual(len({body["message"] for body in requests}), 3)
        self.assertEqual(len({body["action_id"] for body in requests}), 3)
        results = []
        receipts = {}

        async def search(http, manager, store, session_id, body):
            record = manager.get(session_id)
            session = record.game_session
            before = store.get_campaign(campaign_id)
            self.assertIsNone(store.get_turn_action(campaign_id, body["action_id"]))
            real_turn = session.run_player_turn
            captured = []

            @wraps(real_turn)
            def capture_search(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                captured.append(copy.deepcopy(result["action_result"]))
                return result

            # Observe the real offline engine; no scripted discovery or replay.
            with patch.object(session, "run_player_turn", new=capture_search):
                searched = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=body
                )
            self.assertEqual(searched.status_code, 200, searched.text)
            self.assertEqual(searched.json()["action_id"], body["action_id"])
            self.assertEqual(len(captured), 1)
            result = captured[0]
            self.assertEqual(result["action"], "local_search")
            self.assertEqual(result["status"], "found")
            self.assertTrue(result["success"])
            results.append(result)

            persisted = store.get_campaign(campaign_id)
            self.assertEqual(
                persisted.payload["engine_save"], session.serialize_game_state()
            )
            self.assertEqual(persisted.payload["journal"], record.journal)
            self.assertEqual(len(persisted.history), len(before.history) + 1)
            self.assertEqual(persisted.history[:-1], before.history)
            self.assertEqual(
                persisted.history[-1]["player_message"], body["message"]
            )
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(len(world["shops"]), 1)
            shop = world["shops"][0]
            self.assertEqual(shop["id"], results[0]["shop_id"])
            self.assertEqual(shop["shopkeeper_id"], results[0]["target_id"])
            self.assertEqual(shop["location"], city_id)
            self.assertEqual(result["shop_id"], shop["id"])
            self.assertEqual(result["target_id"], shop["shopkeeper_id"])
            self.assertEqual(
                [npc["id"] for npc in world["npcs"]
                 if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            shopkeepers = [
                npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]
            ]
            self.assertEqual(len(shopkeepers), 1)
            self.assertEqual(shopkeepers[0]["location"], city_id)
            if len(results) > 1:
                previous_world = before.payload["engine_save"]["world_state"]
                for collection in ("shops", "npcs"):
                    self.assertEqual(
                        [item["id"] for item in world[collection]],
                        [item["id"] for item in previous_world[collection]],
                    )

            for action_id, receipt in receipts.items():
                self.assertEqual(store.get_turn_action(campaign_id, action_id), receipt)
                self.assertEqual(manager.get_turn_action(record, action_id), receipt)
            receipt = store.get_turn_action(campaign_id, body["action_id"])
            self.assertIsNotNone(receipt)
            self.assertEqual(receipt["response"], searched.json())
            self.assertEqual(manager.get_turn_action(record, body["action_id"]), receipt)
            receipts[body["action_id"]] = copy.deepcopy(receipt)
            self.assertEqual(
                len({item["request_hash"] for item in receipts.values()}),
                len(receipts),
            )
            return persisted

        committed = await search(
            self.http, self.manager, self.store, created["session_id"], requests[0]
        )
        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            loaded_record = reopened_manager.get(session_id)
            self.assertEqual(
                loaded_record.game_session.serialize_game_state(),
                committed.payload["engine_save"],
            )
            self.assertEqual(resumed.json()["history"], committed.history)
            for body in requests[1:]:
                with self.subTest(message=body["message"]):
                    committed = await search(
                        http, reopened_manager, reopened_store, session_id, body
                    )

        # A second reopen verifies the paraphrases are durable independent turns.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_id, _, _, _, _ = final_manager.resume_campaign(campaign_id)
        final_record = final_manager.get(final_id)
        self.assertEqual(
            final_record.game_session.serialize_game_state(),
            committed.payload["engine_save"],
        )
        self.assertEqual(final_record.journal, committed.payload["journal"])
        final_campaign = final_store.get_campaign(campaign_id)
        self.assertEqual(final_campaign.history, committed.history)
        self.assertEqual(
            [entry["player_message"] for entry in final_campaign.history],
            [body["message"] for body in requests],
        )
        for action_id, receipt in receipts.items():
            self.assertEqual(final_store.get_turn_action(campaign_id, action_id), receipt)
            self.assertEqual(final_manager.get_turn_action(final_record, action_id), receipt)

    async def test_reopened_declined_merchant_search_does_not_rediscover_or_duplicate(self):
        city_id = "fr:city:neverwinter"
        # Ambient scene selection is seeded by campaign UUID, not session RNG.
        # A random BLUE referent can match "tüccar" and legitimately promote a
        # separate traveler. This fixture tests merchant rediscovery, not that
        # independent promotion. Keep the real scene/engine owners and a known
        # non-overlapping ambient seed; campaign/session/action UUIDs stay real.
        original_context = living_world.set_ambient_context

        def fixture_context(world, metadata, character, campaign_id):
            return original_context(
                world, metadata, character,
                "10000000-0000-4000-8000-000000000001",
            )

        self.enterContext(patch.object(living_world, "set_ambient_context",
                                      new=fixture_context))
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        # Materialize the city's authored scene before taking the merchant
        # identity baseline. A first visit can legitimately create a BLUE-event
        # referent NPC; that is not merchant rediscovery by the declined input.
        observed = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Etrafıma bakıyorum.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(
            self.store.get_campaign(campaign_id).payload["engine_save"]["world_state"]["shops"],
            [],
        )
        discovery_body = {
            "message": "Bir tüccar arıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        discovered = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json=discovery_body,
        )
        self.assertEqual(discovered.status_code, 200, discovered.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        self.assertEqual(len(saved_world["shops"]), 1)
        shop = saved_world["shops"][0]
        self.assertEqual(shop["location"], city_id)
        self.assertEqual(saved_world["flags"]["active_npc_id"], shop["shopkeeper_id"])
        discovery_receipt = self.store.get_turn_action(
            campaign_id, discovery_body["action_id"]
        )
        self.assertEqual(discovery_receipt["response"], discovered.json())

        class DeclinedSearchOllamaClient(FakeOllamaClient):
            def chat(self, *args, **kwargs):
                # Only the model boundary is scripted; Python still plans,
                # resolves and persists the actual resumed turn.
                if "intent" in kwargs["format"]["properties"]:
                    packet = {
                        "intent": "narrative",
                        "action": "decline_search",
                        "target": {"type": "none", "reference": ""},
                        "completion": "completed",
                        "confidence": 1.0,
                    }
                else:
                    packet = {
                        "narration": "Sokaktaki sesler sürüyor; tezgâh yerinde duruyor.",
                        "world_updates": {},
                        "lore_claims": [],
                    }
                return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(DeclinedSearchOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        declined_body = {
            "message": "Bir tüccar aramıyorum.",
            "action_id": str(uuid.uuid4()),
        }
        self.assertNotEqual(declined_body["action_id"], discovery_body["action_id"])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertEqual(
                session.world_state["flags"]["active_npc_id"], shop["shopkeeper_id"]
            )
            self.assertGreaterEqual(
                session.world_state["flags"]["active_npc_until_turn"],
                session.world_state["flags"]["turn_index"],
            )
            before = reopened_store.get_campaign(campaign_id)
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, declined_body["action_id"])
            )
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_declined_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            # Preserve dispatch's signature and observe a real new offline turn,
            # with the saved merchant still active, rather than receipt replay.
            with patch.object(session, "run_player_turn", new=capture_declined_turn):
                declined = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=declined_body
                )
            self.assertEqual(declined.status_code, 200, declined.text)
            self.assertEqual(declined.json()["action_id"], declined_body["action_id"])
            self.assertEqual(len(results), 1)
            action = results[0]["action_result"]
            self.assertEqual(action["action"], "narrative")
            self.assertEqual(action["status"], "resolved")
            self.assertTrue(action["success"])
            self.assertEqual(action["state_changes"], [])
            self.assertNotIn("shop_id", action)
            self.assertNotEqual(declined.json()["narration"], discovered.json()["narration"])
            self.assertEqual(declined.json()["narration"], results[0]["narration"])

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(
                persisted.payload["engine_save"], session.serialize_game_state()
            )
            self.assertEqual(persisted.payload["journal"], record.journal)
            world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual(world["location"], city_id)
            self.assertEqual(
                world["flags"]["turn_index"],
                saved_world["flags"]["turn_index"] + 1,
            )
            for collection in ("shops", "npcs"):
                self.assertEqual(
                    [item["id"] for item in world[collection]],
                    [item["id"] for item in saved_world[collection]],
                )
            self.assertEqual(world["shops"], saved_world["shops"])
            self.assertEqual(
                [npc["id"] for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            self.assertEqual(len(persisted.history), len(before.history) + 1)
            self.assertEqual(persisted.history[:-1], before.history)
            self.assertEqual(
                persisted.history[-1]["player_message"], declined_body["message"]
            )
            self.assertEqual(
                persisted.history[-1]["narration"], results[0]["narration"]
            )
            declined_receipt = reopened_store.get_turn_action(
                campaign_id, declined_body["action_id"]
            )
            self.assertEqual(declined_receipt["response"], declined.json())
            self.assertEqual(
                reopened_manager.get_turn_action(record, declined_body["action_id"]),
                declined_receipt,
            )
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )

        # Another fresh load checks the non-search history and result persisted;
        # no replay or additional action is sent here.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_id, final_record, _, _, _ = final_manager.resume_campaign(campaign_id)
        self.assertEqual(
            final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
        )
        self.assertEqual(final_record.journal, persisted.payload["journal"])
        self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
        self.assertEqual(
            final_store.get_turn_action(campaign_id, declined_body["action_id"]),
            declined_receipt,
        )
        self.assertEqual(
            final_manager.get_turn_action(final_manager.get(final_id), declined_body["action_id"]),
            declined_receipt,
        )

    async def test_failed_merchant_discovery_is_rolled_back_and_retry_commits_once(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        url = f"/api/game/sessions/{created['session_id']}/turn"
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        observation_results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_observation(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            observation_results.append(copy.deepcopy(result["action_result"]))
            return result

        # Commit real city progress before testing a later failed discovery.
        with patch.object(session, "run_player_turn", new=capture_observation):
            observed = await self.http.post(url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(len(observation_results), 1)
        self.assertEqual(observation_results[0]["action"], "explore")
        self.assertEqual(observation_results[0]["status"], "observed")
        self.assertTrue(observation_results[0]["success"])
        self.assertNotEqual(observed.json()["state"], created["state"])
        self.assertTrue(record.journal["notable_events"])
        self.assertIn(
            city_id,
            [entry["location_id"] for entry in record.journal["discovered_locations"]],
        )
        observation_receipt = copy.deepcopy(
            self.manager.get_turn_action(record, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        body = {
            "message": "Buralarda bir tücaar var mı?",
            "action_id": str(uuid.uuid4()),
        }
        before_save = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        before_memory = copy.deepcopy(record.narrative_memory)
        before_receipts = copy.deepcopy(record.turn_action_receipts)
        before_campaign = self.store.get_campaign(campaign_id)
        before_world = before_save["world_state"]
        self.assertEqual(before_world["location"], city_id)
        self.assertEqual(before_world["shops"], [])
        self.assertTrue(before_world["scene_state"]["scenes"][city_id]["materialized"])
        self.assertEqual(len(before_campaign.history), 1)
        self.assertEqual(before_campaign.payload["engine_save"], before_save)
        self.assertEqual(before_campaign.payload["journal"], before_journal)
        results = []
        attempted_saves = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        def fail_save(*args, **kwargs):
            # Fail at the actual persistence boundary, after the real engine
            # has created both related records, not before discovery executes.
            attempted_saves.append(copy.deepcopy(session.serialize_game_state()))
            raise CampaignStorageError("database unavailable")

        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(self.store, "save_campaign", side_effect=fail_save) as failed_save,
        ):
            failed = await self.http.post(url, json=body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertNotIn("database unavailable", failed.text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "local_search")
        self.assertEqual(results[0]["status"], "found")
        self.assertTrue(results[0]["success"])
        uncommitted_shop_id = results[0]["shop_id"]
        uncommitted_npc_id = results[0]["target_id"]
        attempted_world = attempted_saves[0]["world_state"]
        self.assertEqual(len(attempted_world["shops"]), 1)
        attempted_shop = attempted_world["shops"][0]
        self.assertEqual(attempted_shop["id"], uncommitted_shop_id)
        self.assertEqual(attempted_shop["shopkeeper_id"], uncommitted_npc_id)
        self.assertEqual(attempted_shop["location"], city_id)
        new_shopkeepers = [
            npc for npc in attempted_world["npcs"]
            if npc.get("shop_id") == uncommitted_shop_id
        ]
        self.assertEqual(len(new_shopkeepers), 1)
        self.assertEqual(new_shopkeepers[0]["id"], uncommitted_npc_id)
        self.assertEqual(new_shopkeepers[0]["location"], city_id)

        # Rollback covers the entire engine and the API-owned side effects.
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertEqual(session.world_state["shops"], before_world["shops"])
        self.assertEqual(session.world_state["npcs"], before_world["npcs"])
        self.assertEqual(record.journal, before_journal)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertEqual(record.turn_action_receipts, before_receipts)
        self.assertEqual(
            self.manager.get_turn_action(record, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(self.manager.get_turn_action(record, body["action_id"]))
        self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(self.store.get_turn_action(campaign_id, body["action_id"]))

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["state"], observed.json()["state"])
        self.assertEqual(resumed.json()["history"], before_campaign.history)
        reopened_record = reopened_manager.get(resumed.json()["session_id"])
        self.assertEqual(
            reopened_record.game_session.serialize_game_state(), before_save
        )
        self.assertEqual(reopened_record.journal, before_journal)
        self.assertEqual(reopened_record.narrative_memory, before_memory)
        self.assertEqual(reopened_record.turn_action_receipts, before_receipts)
        self.assertEqual(
            reopened_manager.get_turn_action(
                reopened_record, observation_body["action_id"]
            ),
            observation_receipt,
        )
        reopened_campaign = reopened_store.get_campaign(campaign_id)
        # Resume can refresh metadata timestamps without changing saved progress.
        self.assertEqual(reopened_campaign.payload, before_campaign.payload)
        self.assertEqual(reopened_campaign.history, before_campaign.history)
        self.assertEqual(reopened_campaign.combat_history, before_campaign.combat_history)
        reopened_world = reopened_record.game_session.world_state
        self.assertNotIn(
            uncommitted_shop_id, [shop["id"] for shop in reopened_world["shops"]]
        )
        self.assertNotIn(
            uncommitted_npc_id, [npc["id"] for npc in reopened_world["npcs"]]
        )
        self.assertEqual(
            reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertIsNone(
            reopened_store.get_turn_action(campaign_id, body["action_id"])
        )

        # Recovery re-executes the identical action once, then receipts replay it.
        with patch.object(session, "run_player_turn", new=capture_turn):
            retry = await self.http.post(url, json=body)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["action_id"], body["action_id"])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        world = session.world_state
        self.assertEqual(len(world["shops"]), 1)
        shop = world["shops"][0]
        self.assertEqual(shop["id"], results[-1]["shop_id"])
        self.assertEqual(shop["shopkeeper_id"], results[-1]["target_id"])
        self.assertEqual(shop["location"], city_id)
        shopkeepers = [npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]]
        self.assertEqual(len(shopkeepers), 1)
        self.assertEqual(shopkeepers[0]["location"], city_id)
        self.assertEqual(
            len([npc for npc in world["npcs"] if npc.get("shop_id") == shop["id"]]),
            1,
        )
        self.assertEqual(retry.json()["state"]["location"], city_id)
        committed_save = copy.deepcopy(session.serialize_game_state())
        committed_journal = copy.deepcopy(record.journal)
        committed_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
        self.assertEqual(committed_campaign.payload["journal"], committed_journal)
        self.assertEqual(len(committed_campaign.history), len(before_campaign.history) + 1)
        self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
        self.assertEqual(
            self.store.get_turn_action(campaign_id, observation_body["action_id"]),
            observation_receipt,
        )
        self.assertEqual(
            self.manager.get_turn_action(record, body["action_id"])["response"],
            retry.json(),
        )
        self.assertEqual(
            self.store.get_turn_action(campaign_id, body["action_id"])["response"],
            retry.json(),
        )
        with patch.object(
            session, "run_player_turn",
            side_effect=AssertionError("Discovery replay must not execute a turn"),
        ):
            replay = await self.http.post(url, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), retry.json())
        self.assertEqual(session.serialize_game_state(), committed_save)
        self.assertEqual(record.journal, committed_journal)
        self.assertEqual(self.store.get_campaign(campaign_id), committed_campaign)

        # A second fresh manager proves the recovered discovery and receipt
        # actually persisted, and replay after reopening cannot create duplicates.
        restarted_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        restarted_manager = SessionManager(campaign_store=restarted_store)
        restarted_app = create_app(
            session_manager=restarted_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            loaded_record = restarted_manager.get(session_id)
            loaded = loaded_record.game_session
            self.assertEqual(loaded.serialize_game_state(), committed_save)
            self.assertEqual(loaded_record.journal, committed_journal)
            with patch.object(
                loaded, "run_player_turn",
                side_effect=AssertionError("Saved receipt must not rediscover a merchant"),
            ):
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=body
                )
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), {**retry.json(), "session_id": session_id})
            self.assertEqual(loaded.serialize_game_state(), committed_save)
            self.assertEqual(loaded_record.journal, committed_journal)
            persisted = restarted_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], committed_save)
            self.assertEqual(persisted.payload["journal"], committed_journal)
            self.assertEqual(persisted.history, committed_campaign.history)
            self.assertEqual(len(loaded.world_state["shops"]), 1)
            self.assertEqual(
                len([
                    npc for npc in loaded.world_state["npcs"]
                    if npc.get("shop_id") == shop["id"]
                ]),
                1,
            )

            # A new request is not a receipt replay: the real offline search
            # must find the saved merchant without materializing another one.
            new_body = {**body, "action_id": str(uuid.uuid4())}
            self.assertNotEqual(new_body["action_id"], body["action_id"])
            previous_receipt = copy.deepcopy(
                restarted_store.get_turn_action(campaign_id, body["action_id"])
            )
            previous_world = persisted.payload["engine_save"]["world_state"]
            previous_shop_ids = [item["id"] for item in previous_world["shops"]]
            previous_npc_ids = [item["id"] for item in previous_world["npcs"]]
            new_results = []
            loaded_real_turn = loaded.run_player_turn

            @wraps(loaded_real_turn)
            def capture_new_search(*args, **kwargs):
                result = loaded_real_turn(*args, **kwargs)
                new_results.append(copy.deepcopy(result["action_result"]))
                return result

            with patch.object(loaded, "run_player_turn", new=capture_new_search):
                searched = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=new_body
                )
            self.assertEqual(searched.status_code, 200, searched.text)
            self.assertEqual(searched.json()["action_id"], new_body["action_id"])
            self.assertEqual(len(new_results), 1)
            self.assertEqual(new_results[0]["action"], "local_search")
            self.assertEqual(new_results[0]["status"], "found")
            self.assertTrue(new_results[0]["success"])
            self.assertEqual(new_results[0]["shop_id"], shop["id"])
            self.assertEqual(new_results[0]["target_id"], shop["shopkeeper_id"])

            searched_campaign = restarted_store.get_campaign(campaign_id)
            searched_world = searched_campaign.payload["engine_save"]["world_state"]
            self.assertEqual(
                searched_campaign.payload["engine_save"], loaded.serialize_game_state()
            )
            self.assertEqual(
                [item["id"] for item in searched_world["shops"]], previous_shop_ids
            )
            self.assertEqual(
                [item["id"] for item in searched_world["npcs"]], previous_npc_ids
            )
            self.assertEqual(len(searched_world["shops"]), 1)
            self.assertEqual(searched_world["shops"][0]["shopkeeper_id"], shop["shopkeeper_id"])
            self.assertEqual(
                [npc["id"] for npc in searched_world["npcs"]
                 if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            self.assertEqual(len(searched_campaign.history), len(persisted.history) + 1)
            self.assertEqual(searched_campaign.history[:-1], persisted.history)
            self.assertEqual(
                searched_campaign.history[-1]["player_message"], new_body["message"]
            )
            self.assertEqual(
                restarted_store.get_turn_action(campaign_id, body["action_id"]),
                previous_receipt,
            )
            self.assertEqual(
                restarted_store.get_turn_action(campaign_id, new_body["action_id"])["response"],
                searched.json(),
            )
            self.assertEqual(
                restarted_manager.get_turn_action(loaded_record, new_body["action_id"])["response"],
                searched.json(),
            )

    async def test_failed_merchant_discovery_retries_once_from_a_fresh_resume(self):
        city_id = "fr:city:neverwinter"
        response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = response.json()
        campaign_id = created["campaign_id"]
        record = self.manager.get(created["session_id"])
        session = record.game_session
        turn_url = f"/api/game/sessions/{created['session_id']}/turn"
        observation_body = {
            "message": "Şehirde dolanırken etrafımda neler var gözlemliyorum.",
            "action_id": str(uuid.uuid4()),
        }
        results = []
        real_turn = session.run_player_turn

        @wraps(real_turn)
        def capture_turn(*args, **kwargs):
            result = real_turn(*args, **kwargs)
            results.append(copy.deepcopy(result["action_result"]))
            return result

        # Establish real committed city progress, rather than injecting state.
        with patch.object(session, "run_player_turn", new=capture_turn):
            observed = await self.http.post(turn_url, json=observation_body)
        self.assertEqual(observed.status_code, 200, observed.text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "explore")
        self.assertEqual(results[0]["status"], "observed")
        self.assertTrue(results[0]["success"])
        observation_receipt = copy.deepcopy(
            self.store.get_turn_action(campaign_id, observation_body["action_id"])
        )
        self.assertEqual(observation_receipt["response"], observed.json())
        before_save = copy.deepcopy(session.serialize_game_state())
        before_journal = copy.deepcopy(record.journal)
        before_memory = copy.deepcopy(record.narrative_memory)
        before_receipts = copy.deepcopy(record.turn_action_receipts)
        before_campaign = self.store.get_campaign(campaign_id)
        self.assertEqual(before_save["world_state"]["location"], city_id)
        self.assertEqual(before_save["world_state"]["shops"], [])
        self.assertTrue(
            before_save["world_state"]["scene_state"]["scenes"][city_id]["materialized"]
        )
        self.assertEqual(len(before_campaign.history), 1)
        self.assertEqual(
            before_campaign.history[0]["player_message"], observation_body["message"]
        )
        discovery_body = {
            "message": "Buralarda bir tücaar var mı?",
            "action_id": str(uuid.uuid4()),
        }
        attempted_saves = []

        def fail_save(*args, **kwargs):
            # Fail after discovery really creates the shop and linked keeper.
            attempted_saves.append(copy.deepcopy(session.serialize_game_state()))
            raise CampaignStorageError("database unavailable")

        with (
            patch.object(session, "run_player_turn", new=capture_turn),
            patch.object(self.store, "save_campaign", side_effect=fail_save) as failed_save,
        ):
            failed = await self.http.post(turn_url, json=discovery_body)
        failed_save.assert_called_once()
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(
            failed.json()["detail"]["code"], "campaign_storage_unavailable"
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[-1]["action"], "local_search")
        self.assertEqual(results[-1]["status"], "found")
        self.assertTrue(results[-1]["success"])
        attempted_world = attempted_saves[0]["world_state"]
        self.assertEqual(len(attempted_world["shops"]), 1)
        attempted_shop = attempted_world["shops"][0]
        self.assertEqual(attempted_shop["id"], results[-1]["shop_id"])
        self.assertEqual(attempted_shop["shopkeeper_id"], results[-1]["target_id"])
        self.assertEqual(
            [npc["id"] for npc in attempted_world["npcs"]
             if npc.get("shop_id") == attempted_shop["id"]],
            [attempted_shop["shopkeeper_id"]],
        )
        self.assertEqual(session.serialize_game_state(), before_save)
        self.assertEqual(record.journal, before_journal)
        self.assertEqual(record.narrative_memory, before_memory)
        self.assertEqual(record.turn_action_receipts, before_receipts)
        self.assertEqual(self.store.get_campaign(campaign_id), before_campaign)
        self.assertIsNone(
            self.store.get_turn_action(campaign_id, discovery_body["action_id"])
        )

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()["state"], observed.json()["state"])
            self.assertEqual(resumed.json()["history"], before_campaign.history)
            resumed_record = reopened_manager.get(resumed.json()["session_id"])
            resumed_session = resumed_record.game_session
            self.assertIsNot(resumed_session, session)
            self.assertEqual(resumed_session.serialize_game_state(), before_save)
            self.assertEqual(resumed_record.journal, before_journal)
            self.assertEqual(resumed_record.narrative_memory, before_memory)
            self.assertEqual(resumed_record.turn_action_receipts, before_receipts)
            reopened_campaign = reopened_store.get_campaign(campaign_id)
            self.assertEqual(reopened_campaign.payload, before_campaign.payload)
            self.assertEqual(reopened_campaign.history, before_campaign.history)
            self.assertIsNone(
                reopened_manager.get_turn_action(
                    resumed_record, discovery_body["action_id"]
                )
            )
            self.assertIsNone(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"])
            )
            self.assertEqual(
                reopened_manager.get_turn_action(
                    resumed_record, observation_body["action_id"]
                ),
                observation_receipt,
            )
            resumed_url = f"/api/game/sessions/{resumed.json()['session_id']}/turn"
            resumed_real_turn = resumed_session.run_player_turn
            retry_results = []

            @wraps(resumed_real_turn)
            def capture_retry(*args, **kwargs):
                result = resumed_real_turn(*args, **kwargs)
                retry_results.append(copy.deepcopy(result["action_result"]))
                return result

            with (
                patch.object(
                    session, "run_player_turn",
                    side_effect=AssertionError("Retry must use the resumed session"),
                ) as original_turn,
                patch.object(resumed_session, "run_player_turn", new=capture_retry),
                patch.object(
                    reopened_store, "save_campaign", wraps=reopened_store.save_campaign
                ) as retry_save,
            ):
                retry = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(retry.status_code, 200, retry.text)
            original_turn.assert_not_called()
            retry_save.assert_called_once()
            self.assertEqual(len(retry_results), 1)
            self.assertEqual(retry_results[0]["action"], "local_search")
            self.assertEqual(retry_results[0]["status"], "found")
            self.assertTrue(retry_results[0]["success"])
            self.assertEqual(retry.json()["action_id"], discovery_body["action_id"])
            self.assertEqual(retry.json()["state"]["location"], city_id)
            committed_save = copy.deepcopy(resumed_session.serialize_game_state())
            world = committed_save["world_state"]
            self.assertEqual(len(world["shops"]), 1)
            shop = world["shops"][0]
            self.assertEqual(shop["id"], retry_results[0]["shop_id"])
            self.assertEqual(shop["shopkeeper_id"], retry_results[0]["target_id"])
            self.assertEqual(shop["location"], city_id)
            self.assertEqual(
                [npc["id"] for npc in world["npcs"] if npc.get("shop_id") == shop["id"]],
                [shop["shopkeeper_id"]],
            )
            shopkeepers = [npc for npc in world["npcs"] if npc["id"] == shop["shopkeeper_id"]]
            self.assertEqual(len(shopkeepers), 1)
            self.assertEqual(shopkeepers[0]["location"], city_id)
            committed_campaign = reopened_store.get_campaign(campaign_id)
            self.assertEqual(committed_campaign.payload["engine_save"], committed_save)
            self.assertEqual(committed_campaign.payload["journal"], resumed_record.journal)
            self.assertEqual(len(committed_campaign.history), len(before_campaign.history) + 1)
            self.assertEqual(committed_campaign.history[:-1], before_campaign.history)
            self.assertEqual(
                committed_campaign.history[-1]["player_message"], discovery_body["message"]
            )
            self.assertEqual(
                committed_campaign.history[-1]["narration"], retry.json()["narration"]
            )
            for manager, receipt_record in (
                (self.manager, record), (reopened_manager, resumed_record)
            ):
                self.assertEqual(
                    manager.get_turn_action(receipt_record, observation_body["action_id"]),
                    observation_receipt,
                )
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, observation_body["action_id"]),
                observation_receipt,
            )
            discovery_receipt = copy.deepcopy(
                reopened_manager.get_turn_action(resumed_record, discovery_body["action_id"])
            )
            self.assertEqual(discovery_receipt["response"], retry.json())
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, discovery_body["action_id"]),
                discovery_receipt,
            )
            with (
                patch.object(
                    resumed_session, "run_player_turn",
                    side_effect=AssertionError("Replay must not execute another turn"),
                ) as replay_turn,
                patch.object(
                    reopened_store, "save_campaign",
                    side_effect=AssertionError("Replay must not save again"),
                ) as replay_save,
            ):
                replay = await http.post(resumed_url, json=discovery_body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), retry.json())
            replay_turn.assert_not_called()
            replay_save.assert_not_called()
            self.assertEqual(resumed_session.serialize_game_state(), committed_save)
            self.assertEqual(resumed_record.journal, committed_campaign.payload["journal"])
            self.assertEqual(reopened_store.get_campaign(campaign_id), committed_campaign)
            for action_id, receipt in (
                (observation_body["action_id"], observation_receipt),
                (discovery_body["action_id"], discovery_receipt),
            ):
                self.assertEqual(reopened_store.get_turn_action(campaign_id, action_id), receipt)
                self.assertEqual(reopened_manager.get_turn_action(resumed_record, action_id), receipt)

    async def test_altered_exit_retry_conflicts_before_stale_campaign_check(self):
        city_id = "fr:city:neverwinter"
        created_response = await self.http.post(
            "/api/game/campaigns",
            json={
                "campaign_start": {
                    "setting_id": "forgotten_realms",
                    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
                    "region_id": "fr:region:the_north",
                    "starting_location_id": city_id,
                },
            },
        )
        self.assertEqual(created_response.status_code, 200, created_response.text)
        created = created_response.json()
        campaign_id = created["campaign_id"]
        initial_url = f"/api/game/sessions/{created['session_id']}/turn"
        searched = await self.http.post(
            initial_url,
            json={"message": "Yakınlarda bir taverna arıyorum.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(searched.status_code, 200, searched.text)
        setup_world = self.manager.get(created["session_id"]).game_session.world_state
        tavern_ids = [
            location_id for location_id, location in setup_world["locations"].items()
            if isinstance(location, dict) and location.get("scene_kind") == "tavern"
        ]
        self.assertEqual(len(tavern_ids), 1)
        unlock_venue_door(setup_world, tavern_ids[0])
        entered = await self.http.post(
            initial_url,
            json={"message": "Enter the tavern.", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(entered.status_code, 200, entered.text)
        tavern_id = entered.json()["state"]["location"]
        self.assertNotEqual(tavern_id, city_id)

        active_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        stale_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        active_manager = SessionManager(campaign_store=active_store)
        stale_manager = SessionManager(campaign_store=stale_store)
        active_app = create_app(
            session_manager=active_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        stale_app = create_app(
            session_manager=stale_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=active_app),
                base_url="http://testserver",
            ) as active_http,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stale_app),
                base_url="http://testserver",
            ) as stale_http,
        ):
            active_resume = await active_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            stale_resume = await stale_http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            for response in (active_resume, stale_resume):
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"], entered.json()["state"])
            active_id = active_resume.json()["session_id"]
            stale_id = stale_resume.json()["session_id"]
            stale_record = stale_manager.get(stale_id)
            stale_session = stale_record.game_session
            self.assertIsNot(active_manager.get(active_id).game_session, stale_session)
            stale_save = copy.deepcopy(stale_session.serialize_game_state())
            before = active_store.get_campaign(campaign_id)
            self.assertEqual(stale_save["world_state"]["location"], tavern_id)
            self.assertEqual(stale_save, before.payload["engine_save"])

            # Execute a real exit, while the other manager keeps its tavern state.
            exit_body = {
                "message": "Tavernadan dışarı çıkıyorum.",
                "action_id": str(uuid.uuid4()),
            }
            accepted = await active_http.post(
                f"/api/game/sessions/{active_id}/turn", json=exit_body
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["state"]["location"], city_id)
            committed = active_store.get_campaign(campaign_id)
            self.assertEqual(committed.payload["engine_save"]["world_state"]["location"], city_id)
            self.assertEqual(committed.metadata["revision"], before.metadata["revision"] + 1)
            self.assertEqual(committed.history[:-1], before.history)
            self.assertEqual(committed.history[-1]["player_message"], exit_body["message"])
            exit_receipt = copy.deepcopy(
                active_store.get_turn_action(campaign_id, exit_body["action_id"])
            )
            self.assertEqual(exit_receipt["response"], accepted.json())
            self.assertEqual(stale_session.serialize_game_state(), stale_save)

            altered_body = {**exit_body, "message": "Tavernada bekliyorum."}
            stale_url = f"/api/game/sessions/{stale_id}/turn"
            with (
                patch.object(
                    stale_session, "run_player_turn",
                    side_effect=AssertionError("Conflicting retries must not run the engine"),
                ) as blocked_turn,
                patch.object(
                    stale_store, "save_campaign",
                    side_effect=AssertionError("Conflicting retries must not save"),
                ) as blocked_save,
            ):
                rejected = await stale_http.post(stale_url, json=altered_body)
                self.assertEqual(rejected.status_code, 409, rejected.text)
                self.assertEqual(rejected.json()["detail"]["code"], "action_id_conflict")
                rejected_campaign = stale_store.get_campaign(campaign_id)
                self.assertEqual(rejected_campaign.payload, committed.payload)
                self.assertEqual(rejected_campaign.metadata, committed.metadata)
                self.assertEqual(rejected_campaign.history, committed.history)
                self.assertEqual(rejected_campaign.combat_history, committed.combat_history)
                self.assertEqual(
                    stale_store.get_turn_action(campaign_id, exit_body["action_id"]),
                    exit_receipt,
                )
                self.assertEqual(stale_session.serialize_game_state(), stale_save)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()

                # The conflict must not poison the accepted action's valid replay.
                replay = await stale_http.post(stale_url, json=exit_body)
                self.assertEqual(replay.status_code, 200, replay.text)
                expected_replay = copy.deepcopy(accepted.json())
                expected_replay["session_id"] = stale_id
                self.assertEqual(replay.json(), expected_replay)
                blocked_turn.assert_not_called()
                blocked_save.assert_not_called()

            replayed_campaign = stale_store.get_campaign(campaign_id)
            self.assertEqual(replayed_campaign.payload, committed.payload)
            self.assertEqual(replayed_campaign.metadata, committed.metadata)
            self.assertEqual(replayed_campaign.history, committed.history)
            self.assertEqual(replayed_campaign.combat_history, committed.combat_history)
            self.assertEqual(
                stale_store.get_turn_action(campaign_id, exit_body["action_id"]),
                exit_receipt,
            )
            self.assertEqual(stale_session.serialize_game_state(), stale_save)

    async def test_reopened_name_fallback_uses_only_player_claim_bound_to_same_npc(self):
        from api.narrative_memory import build_narrative_context

        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        original_record = self.manager.get(created["session_id"])
        original_session = original_record.game_session
        location_id = original_session.world_state["location"]
        npc_a = {
            "id": "npc_continuity_name_mira",
            "name": "Mira",
            "role": "Yolcu",
            "location": location_id,
            "memory": [],
        }
        npc_b = {
            "id": "npc_continuity_name_aldren",
            "name": "Aldren",
            "role": "Muhafız",
            "location": location_id,
            "memory": [],
        }
        original_session.world_state["npcs"] = [npc_a, npc_b]
        self.manager.save_campaign(campaign_id)

        disclosure = {
            "message": "Benim adım Arven.",
            "target_id": npc_a["id"],
            "action_id": str(uuid.uuid4()),
        }
        response = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn", json=disclosure
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Arven", response.json()["narration"])
        player_claims = (
            original_record.narrative_memory["npc_interactions"][npc_a["id"]]
        )
        self.assertTrue(any(
            entry.get("source") == "player_utterance"
            and entry.get("authority") == "narrative_continuity"
            and "Benim adım Arven." in entry.get("text", "")
            for entry in player_claims
        ))

        # Build a saved fixture where only the NPC's direct duplicate is
        # absent. The player-origin claim remains bound to Mira's stable ID.
        npc_a["memory"] = []
        memory = original_record.narrative_memory
        memory["recent_turns"][-1]["narration"] = "Mira: Adın Galen."
        self.manager.save_campaign(campaign_id)
        saved = self.store.get_campaign(campaign_id)
        saved_world = saved.payload["engine_save"]["world_state"]
        saved_npcs = {npc["id"]: npc for npc in saved_world["npcs"]}
        self.assertEqual(saved_npcs[npc_a["id"]]["memory"], [])
        saved_claims = saved.payload["narrative_memory"]["npc_interactions"]
        self.assertTrue(any(
            entry.get("source") == "player_utterance"
            and entry.get("authority") == "narrative_continuity"
            and "Benim adım Arven." in entry.get("text", "")
            for entry in saved_claims[npc_a["id"]]
        ))

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.world_state["npcs"][0]["memory"], [])

            ask_a = {
                "message": "Bana adımla hitap et",
                "target_id": npc_a["id"],
                "action_id": str(uuid.uuid4()),
            }
            ask_b = {
                **ask_a,
                "target_id": npc_b["id"],
                "action_id": str(uuid.uuid4()),
            }
            packet_a, _ = build_narrative_context(
                record.narrative_memory,
                game.build_world_context(
                    npc_target=session.world_state["npcs"][0], session=session
                ),
                ask_a["message"],
                {"npc_id": npc_a["id"]},
            )
            packet_b, _ = build_narrative_context(
                record.narrative_memory,
                game.build_world_context(
                    npc_target=session.world_state["npcs"][1], session=session
                ),
                ask_b["message"],
                {"npc_id": npc_b["id"]},
            )
            self.assertNotIn(
                "Galen", json.dumps(packet_a, ensure_ascii=False)
            )
            self.assertNotIn(
                "Benim adım Arven.",
                json.dumps(
                    packet_b["relevant_continuity"], ensure_ascii=False
                ),
            )
            self.assertEqual(
                record.narrative_memory["recent_turns"][-1]["narration"],
                "Mira: Adın Galen.",
            )

            for body, expected_name in ((ask_a, "Arven"), (ask_b, None)):
                with self.subTest(target_id=body["target_id"]):
                    before = reopened_store.get_campaign(campaign_id)
                    turn = await http.post(
                        f"/api/game/sessions/{session_id}/turn", json=body
                    )
                    self.assertEqual(turn.status_code, 200, turn.text)
                    narration = turn.json()["narration"]
                    if expected_name:
                        self.assertIn(expected_name, narration)
                        self.assertNotIn("Galen", narration)
                    else:
                        self.assertNotIn("Arven", narration)
                        self.assertNotIn("Galen", narration)
                    after = reopened_store.get_campaign(campaign_id)
                    self.assertEqual(after.history[:-1], before.history)
                    self.assertEqual(
                        after.history[-1]["player_message"], body["message"]
                    )
                    receipt = reopened_store.get_turn_action(
                        campaign_id, body["action_id"]
                    )
                    self.assertEqual(receipt["response"], turn.json())

    async def test_reopened_personal_reply_conflicts_when_target_changes(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        location_id = original_session.world_state["location"]
        npc_a = {
            "id": "npc_personal_receipt_mira",
            "name": "Mira",
            "role": "Yolcu",
            "location": location_id,
            "memory": [],
        }
        npc_b = {
            "id": "npc_personal_receipt_aldren",
            "name": "Aldren",
            "role": "Muhafız",
            "location": location_id,
            "memory": [],
        }
        original_session.world_state["npcs"] = [npc_a, npc_b]
        self.manager.save_campaign(campaign_id)
        disclosure = {
            "message": "Benim adım Arven.",
            "target_id": npc_a["id"],
            "action_id": str(uuid.uuid4()),
        }
        disclosed = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn", json=disclosure
        )
        self.assertEqual(disclosed.status_code, 200, disclosed.text)
        self.assertIn("Arven", disclosed.json()["narration"])

        body = {
            "message": "Bana adımla hitap et",
            "target_id": npc_a["id"],
            "action_id": str(uuid.uuid4()),
        }
        original_answer = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn", json=body
        )
        self.assertEqual(original_answer.status_code, 200, original_answer.text)
        self.assertIn("Arven", original_answer.json()["narration"])
        original_receipt = self.store.get_turn_action(
            campaign_id, body["action_id"]
        )
        self.assertEqual(original_receipt["response"], original_answer.json())

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(
                f"/api/game/campaigns/{campaign_id}/resume"
            )
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertIsNot(session, original_session)
            committed = reopened_store.get_campaign(campaign_id)
            self.assertEqual(
                session.serialize_game_state(), committed.payload["engine_save"]
            )
            self.assertEqual(resumed.json()["history"], committed.history)
            before_replay = reopened_store.get_campaign(campaign_id)
            runtime_before = copy.deepcopy((
                session.serialize_game_state(),
                session.rng.getstate(),
                session.messages,
                record.journal,
                record.narrative_memory,
                record.turn_action_receipts,
            ))

            changed = {**body, "target_id": npc_b["id"]}
            with patch.object(
                session, "run_player_turn",
                side_effect=AssertionError("saved personal reply reran"),
            ), patch.object(
                reopened_store, "save_campaign",
                side_effect=AssertionError("saved personal reply autosaved"),
            ):
                replay = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=body
                )
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(
                    replay.json(),
                    dict(original_receipt["response"], session_id=session_id),
                )
                self.assertEqual(runtime_before, (
                    session.serialize_game_state(),
                    session.rng.getstate(),
                    session.messages,
                    record.journal,
                    record.narrative_memory,
                    record.turn_action_receipts,
                ))
                self.assertEqual(
                    reopened_store.get_campaign(campaign_id), before_replay
                )
                conflict = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=changed
                )
            self.assertEqual(conflict.status_code, 409, conflict.text)
            self.assertEqual(
                conflict.json()["detail"]["code"], "action_id_conflict"
            )
            self.assertEqual(
                reopened_store.get_campaign(campaign_id), before_replay
            )
            self.assertEqual(runtime_before, (
                session.serialize_game_state(),
                session.rng.getstate(),
                session.messages,
                record.journal,
                record.narrative_memory,
                record.turn_action_receipts,
            ))
            self.assertEqual(
                reopened_store.get_turn_action(campaign_id, body["action_id"]),
                original_receipt,
            )

    async def test_reopened_personal_questions_stay_bound_to_saved_npcs(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        world = original_session.world_state
        local_npcs = [
            {
                "id": "npc_saved_personal_traveler",
                "name": "Derya",
                "role": "Yolcu",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
            {
                "id": "npc_saved_personal_guard",
                "name": "Duru",
                "role": "Muhafız",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
        ]
        for npc in local_npcs:
            local_dialogue.ensure_personal_profile(npc)
        world["npcs"].extend(local_npcs)
        world["flags"]["active_npc_id"] = local_npcs[0]["id"]
        world["flags"]["active_npc_until_turn"] = world["flags"]["turn_index"] + 6
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        saved_npcs = copy.deepcopy(saved_world["npcs"])
        saved_ids = [npc["id"] for npc in saved_npcs]
        self.assertEqual(len(saved_ids), len(set(saved_ids)))
        expected_npcs = {npc["id"]: npc for npc in saved_npcs}
        self.assertNotEqual(
            expected_npcs[local_npcs[0]["id"]]["personal_profile"],
            expected_npcs[local_npcs[1]["id"]]["personal_profile"],
        )

        # Use the supported profile questions from test_playable_living_world.
        # Expected prose comes from the saved profile, not a mocked responder.
        questions = (
            ("Adın ne?", None),
            ("Mesleğin nedir?", "occupation"),
            ("Şu an ne yapıyorsun?", "current_activity"),
            ("Bugün ne yaptın?", "recent_activity"),
            ("Keyfin nasıl?", "mood"),
            ("Nereden geliyorsun?", "origin"),
            ("Peki sen, kendinden biraz bahset.", "personal_detail"),
        )
        requests = []
        for selected, npc in ((False, local_npcs[0]), (True, local_npcs[1])):
            for question, profile_field in questions:
                body = {"message": question, "action_id": str(uuid.uuid4())}
                if selected:
                    body["target_id"] = npc["id"]
                requests.append((body, npc["id"], profile_field))
        self.assertEqual(
            len({body["action_id"] for body, _, _ in requests}), len(requests)
        )
        receipts = {}
        narrations = []
        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            record = reopened_manager.get(session_id)
            session = record.game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertEqual(
                session.world_state["flags"]["active_npc_id"], local_npcs[0]["id"]
            )
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_personal_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_personal_turn):
                for index, (body, npc_id, profile_field) in enumerate(requests):
                    with self.subTest(target_id=body.get("target_id"), question=body["message"]):
                        if "target_id" not in body:
                            self.assertEqual(
                                session.world_state["flags"]["active_npc_id"], npc_id
                            )
                            self.assertGreaterEqual(
                                session.world_state["flags"]["active_npc_until_turn"],
                                session.world_state["flags"]["turn_index"],
                            )
                        self.assertIsNone(
                            reopened_store.get_turn_action(campaign_id, body["action_id"])
                        )
                        before = reopened_store.get_campaign(campaign_id)
                        response = await http.post(
                            f"/api/game/sessions/{session_id}/turn", json=body
                        )
                        self.assertEqual(response.status_code, 200, response.text)
                        turn = response.json()
                        self.assertEqual(turn["action_id"], body["action_id"])
                        self.assertEqual(len(results), index + 1)  # A fresh real turn.
                        action = results[-1]["action_result"]
                        self.assertTrue(action["success"])
                        self.assertEqual(action["npc_id"], npc_id)
                        self.assertEqual(action["state_changes"], [])
                        npc = expected_npcs[npc_id]
                        narration = turn["narration"]
                        self.assertEqual(narration, results[-1]["narration"])
                        self.assertIn(npc["name"], narration)
                        for other in local_npcs:
                            if other["id"] != npc_id:
                                self.assertNotIn(other["name"], narration)
                        if profile_field is None:
                            self.assertEqual(action["action"], "query")
                            self.assertEqual(action["status"], "answered_from_campaign_state")
                            self.assertEqual(action["query_type"], "npc_identity")
                            self.assertIn(npc["role"], narration)
                        else:
                            self.assertEqual(action["action"], "dialogue")
                            self.assertEqual(action["status"], "answered_personal_question")
                            self.assertEqual(
                                action["reality_category"], local_dialogue.PROCEDURAL_PERSONAL_FACT
                            )
                            self.assertEqual(
                                narration,
                                f'{npc["name"]}, “{npc["personal_profile"][profile_field]}” diye yanıt verir.',
                            )
                        narrations.append(narration)

                        persisted = reopened_store.get_campaign(campaign_id)
                        self.assertEqual(
                            persisted.payload["engine_save"], session.serialize_game_state()
                        )
                        persisted_world = persisted.payload["engine_save"]["world_state"]
                        # Dialogue may append NPC memory, but must never rename,
                        # replace, duplicate or regenerate the saved people.
                        self.assertEqual(
                            [item["id"] for item in persisted_world["npcs"]], saved_ids
                        )
                        for current in persisted_world["npcs"]:
                            expected = expected_npcs[current["id"]]
                            for key in ("id", "name", "role", "location", "reality_layer", "personal_profile"):
                                self.assertEqual(current.get(key), expected.get(key), key)
                        self.assertEqual(persisted_world["flags"]["active_npc_id"], npc_id)
                        self.assertEqual(
                            persisted_world["flags"]["turn_index"],
                            saved_world["flags"]["turn_index"] + index + 1,
                        )
                        self.assertEqual(persisted.history[:-1], before.history)
                        self.assertEqual(len(persisted.history), len(before.history) + 1)
                        self.assertEqual(persisted.history[-1]["player_message"], body["message"])
                        self.assertEqual(persisted.history[-1]["narration"], narration)
                        receipt = reopened_store.get_turn_action(campaign_id, body["action_id"])
                        self.assertEqual(receipt["response"], turn)
                        receipts[body["action_id"]] = copy.deepcopy(receipt)

        # A second fresh reload must retain all accepted answers and identities,
        # without using the previous SessionManager's objects or receipt cache.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            final_record = final_manager.get(resumed.json()["session_id"])
            self.assertIsNot(final_record.game_session, session)
            self.assertEqual(
                final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
            )
            self.assertEqual(final_record.journal, persisted.payload["journal"])
            final_history = resumed.json()["history"]
            self.assertEqual(final_history, persisted.history)
            self.assertEqual(final_store.get_campaign(campaign_id).history, final_history)
            self.assertEqual(
                [entry["player_message"] for entry in final_history[-len(requests):]],
                [body["message"] for body, _, _ in requests],
            )
            self.assertEqual(
                [entry["narration"] for entry in final_history[-len(requests):]], narrations
            )
            for action_id, receipt in receipts.items():
                self.assertEqual(final_store.get_turn_action(campaign_id, action_id), receipt)
                self.assertEqual(final_manager.get_turn_action(final_record, action_id), receipt)

    async def test_reopened_expired_conversation_honors_selected_personal_target(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        world = original_session.world_state
        local_npcs = [
            {
                "id": "npc_expired_selected_traveler",
                "name": "Derya",
                "role": "Yolcu",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
            {
                "id": "npc_expired_selected_guard",
                "name": "Duru",
                "role": "Muhafız",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
        ]
        for npc in local_npcs:
            local_dialogue.ensure_personal_profile(npc)
        world["npcs"].extend(local_npcs)
        flags = world["flags"]
        flags["active_npc_id"] = flags["last_npc_id"] = local_npcs[0]["id"]
        flags["active_npc_until_turn"] = flags["turn_index"] - 1
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        saved_npcs = copy.deepcopy(saved_world["npcs"])
        saved_ids = [npc["id"] for npc in saved_npcs]
        self.assertEqual(len(saved_ids), len(set(saved_ids)))
        expected_npcs = {npc["id"]: npc for npc in saved_npcs}
        expired_npc = expected_npcs[local_npcs[0]["id"]]
        selected_npc = expected_npcs[local_npcs[1]["id"]]
        self.assertLess(
            saved_world["flags"]["active_npc_until_turn"],
            saved_world["flags"]["turn_index"],
        )
        self.assertNotEqual(
            expired_npc["personal_profile"]["occupation"],
            selected_npc["personal_profile"]["occupation"],
        )
        body = {
            "message": "Mesleğin nedir?",
            "target_id": selected_npc["id"],
            "action_id": str(uuid.uuid4()),
        }
        self.assertEqual(local_dialogue.personal_question_kind(body["message"]), "occupation")
        expected_narration = (
            f'{selected_npc["name"]}, '
            f'“{selected_npc["personal_profile"]["occupation"]}” diye yanıt verir.'
        )

        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            session = reopened_manager.get(session_id).game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertIsNone(reopened_store.get_turn_action(campaign_id, body["action_id"]))

            # Observe the real engine: neither its target resolution nor its
            # profile answer is replaced by a canned result.
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with patch.object(session, "run_player_turn", new=capture_turn):
                response = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=body
                )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(results), 1)
            action = results[0]["action_result"]
            self.assertEqual(action["action"], "dialogue")
            self.assertEqual(action["status"], "answered_personal_question")
            self.assertTrue(action["success"])
            self.assertEqual(action["npc_id"], selected_npc["id"])
            self.assertEqual(action["state_changes"], [])
            self.assertEqual(action["reality_category"], local_dialogue.PROCEDURAL_PERSONAL_FACT)
            turn = response.json()
            self.assertEqual(turn["action_id"], body["action_id"])
            self.assertEqual(turn["narration"], results[0]["narration"])
            self.assertEqual(turn["narration"], expected_narration)
            self.assertNotIn(expired_npc["name"], turn["narration"])
            self.assertNotIn(
                expired_npc["personal_profile"]["occupation"], turn["narration"]
            )

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], session.serialize_game_state())
            persisted_world = persisted.payload["engine_save"]["world_state"]
            self.assertEqual([npc["id"] for npc in persisted_world["npcs"]], saved_ids)
            for npc in persisted_world["npcs"]:
                expected = expected_npcs[npc["id"]]
                for key in ("id", "name", "role", "location", "reality_layer", "personal_profile"):
                    self.assertEqual(npc.get(key), expected.get(key), key)
            persisted_flags = persisted_world["flags"]
            self.assertEqual(persisted_flags["active_npc_id"], selected_npc["id"])
            self.assertEqual(persisted_flags["last_npc_id"], selected_npc["id"])
            self.assertEqual(
                persisted_flags["turn_index"], saved_world["flags"]["turn_index"] + 1
            )
            self.assertEqual(
                persisted_flags["active_npc_until_turn"], persisted_flags["turn_index"] + 6
            )
            self.assertEqual(persisted.history[:-1], committed.history)
            self.assertEqual(len(persisted.history), len(committed.history) + 1)
            self.assertEqual(persisted.history[-1]["player_message"], body["message"])
            self.assertEqual(persisted.history[-1]["narration"], expected_narration)
            receipt = copy.deepcopy(reopened_store.get_turn_action(campaign_id, body["action_id"]))
            self.assertEqual(receipt["response"], turn)

        # Fresh persistence and session objects must retain the selected
        # conversation, both saved profiles, the answer, and the action receipt.
        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            final_record = final_manager.get(resumed.json()["session_id"])
            self.assertIsNot(final_record.game_session, session)
            self.assertEqual(
                final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
            )
            self.assertEqual(final_record.journal, persisted.payload["journal"])
            self.assertEqual(resumed.json()["history"], persisted.history)
            self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
            self.assertEqual(final_store.get_turn_action(campaign_id, body["action_id"]), receipt)
            self.assertEqual(final_manager.get_turn_action(final_record, body["action_id"]), receipt)

    async def test_reopened_expired_conversation_clarifies_personal_question(self):
        created = await self.create_campaign()
        campaign_id = created["campaign_id"]
        original_session = self.manager.get(created["session_id"]).game_session
        world = original_session.world_state
        local_npcs = [
            {
                "id": "npc_expired_personal_traveler",
                "name": "Derya",
                "role": "Yolcu",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
            {
                "id": "npc_expired_personal_guard",
                "name": "Duru",
                "role": "Muhafız",
                "location": world["location"],
                "reality_layer": "PROCEDURAL_LOCAL_FICTION",
            },
        ]
        for npc in local_npcs:
            local_dialogue.ensure_personal_profile(npc)
        world["npcs"].extend(local_npcs)
        flags = world["flags"]
        flags["active_npc_id"] = flags["last_npc_id"] = local_npcs[0]["id"]
        flags["active_npc_until_turn"] = flags["turn_index"] - 1
        saved = await self.http.post(f"/api/game/campaigns/{campaign_id}/save")
        self.assertEqual(saved.status_code, 200, saved.text)
        committed = self.store.get_campaign(campaign_id)
        saved_world = committed.payload["engine_save"]["world_state"]
        saved_npcs = copy.deepcopy(saved_world["npcs"])
        saved_ids = [npc["id"] for npc in saved_npcs]
        self.assertEqual(len(saved_ids), len(set(saved_ids)))
        self.assertLess(
            saved_world["flags"]["active_npc_until_turn"],
            saved_world["flags"]["turn_index"],
        )
        body = {"message": "Mesleğin nedir?", "action_id": str(uuid.uuid4())}
        self.assertEqual(local_dialogue.personal_question_kind(body["message"]), "occupation")
        reopened_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        reopened_manager = SessionManager(campaign_store=reopened_store)
        reopened_app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=reopened_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            session_id = resumed.json()["session_id"]
            session = reopened_manager.get(session_id).game_session
            self.assertIsNot(session, original_session)
            self.assertEqual(session.serialize_game_state(), committed.payload["engine_save"])
            self.assertEqual(resumed.json()["history"], committed.history)
            self.assertIsNone(reopened_store.get_turn_action(campaign_id, body["action_id"]))

            # As with expired scene references, no selected target means the
            # saved referent cannot authorize an answer. Observe (do not replace)
            # the real resolver and turn through the HTTP endpoint.
            real_turn = session.run_player_turn
            results = []

            @wraps(real_turn)
            def capture_turn(*args, **kwargs):
                result = real_turn(*args, **kwargs)
                results.append(copy.deepcopy(result))
                return result

            with (
                patch.object(session, "run_player_turn", new=capture_turn),
                patch.object(game, "resolve_npc_reference", wraps=game.resolve_npc_reference) as resolver,
            ):
                response = await http.post(
                    f"/api/game/sessions/{session_id}/turn", json=body
                )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(results), 1)
            resolver.assert_called_with(body["message"])
            action = results[0]["action_result"]
            self.assertEqual(action["action"], "dialogue")
            self.assertEqual(action["status"], "clarification")
            self.assertFalse(action["success"])
            self.assertEqual(action["state_changes"], [])
            self.assertIsNone(action.get("npc_id"))
            turn = response.json()
            self.assertEqual(turn["action_id"], body["action_id"])
            self.assertEqual(turn["narration"], results[0]["narration"])
            expected_narration = game.npc_ambiguity_response(
                {"npcs": saved_npcs}
            )
            self.assertEqual(turn["narration"], expected_narration)
            for npc in local_npcs:
                self.assertIn(npc["name"], turn["narration"])
                self.assertNotEqual(
                    turn["narration"],
                    f'{npc["name"]}, “{npc["personal_profile"]["occupation"]}” diye yanıt verir.',
                )

            persisted = reopened_store.get_campaign(campaign_id)
            self.assertEqual(persisted.payload["engine_save"], session.serialize_game_state())
            persisted_world = persisted.payload["engine_save"]["world_state"]
            # Clarification must not choose a person, append NPC dialogue memory,
            # regenerate profiles, or refresh the expired conversation.
            self.assertEqual(persisted_world["npcs"], saved_npcs)
            for key in ("active_npc_id", "last_npc_id", "active_npc_until_turn"):
                self.assertEqual(persisted_world["flags"][key], saved_world["flags"][key])
            self.assertEqual(
                persisted_world["flags"]["turn_index"],
                saved_world["flags"]["turn_index"] + 1,
            )
            self.assertEqual(persisted.history[:-1], committed.history)
            self.assertEqual(len(persisted.history), len(committed.history) + 1)
            self.assertEqual(persisted.history[-1]["player_message"], body["message"])
            self.assertEqual(persisted.history[-1]["narration"], expected_narration)
            receipt = copy.deepcopy(reopened_store.get_turn_action(campaign_id, body["action_id"]))
            self.assertEqual(receipt["response"], turn)

        final_store = CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        final_manager = SessionManager(campaign_store=final_store)
        final_app = create_app(
            session_manager=final_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=final_app),
            base_url="http://testserver",
        ) as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            final_record = final_manager.get(resumed.json()["session_id"])
            self.assertIsNot(final_record.game_session, session)
            self.assertEqual(
                final_record.game_session.serialize_game_state(), persisted.payload["engine_save"]
            )
            self.assertEqual(final_record.journal, persisted.payload["journal"])
            self.assertEqual(resumed.json()["history"], persisted.history)
            self.assertEqual(final_store.get_campaign(campaign_id).history, persisted.history)
            self.assertEqual(final_store.get_turn_action(campaign_id, body["action_id"]), receipt)
            self.assertEqual(final_manager.get_turn_action(final_record, body["action_id"]), receipt)

    async def run_review_scene_turn(
        self, message, proposals, *, narration="A visible stone detail.",
        mode=None, prepare=None,
    ):
        city_id, _, session, turn_url, venue_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        if prepare:
            prepare(session, city_id, venue_id)
        if callable(proposals):
            proposals = proposals(session, city_id, venue_id)
        model = ControlledSceneDetailOllamaClient(
            city_id, venue_id, proposals=proposals, narration=narration,
        )
        body = {"message": message, "action_id": str(uuid.uuid4())}
        if mode:
            body["interaction_mode"] = mode
        elapsed_before = session.world_state["campaign_time"]["elapsed_seconds"]
        rng_before = session.rng.getstate()
        outcomes = []
        run_turn = session.run_player_turn
        @wraps(run_turn)
        def capture_turn(*args, **kwargs):
            result = run_turn(*args, **kwargs)
            outcomes.append(copy.deepcopy(result.get("action_result", {})))
            return result
        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await self.post_scene_turn(turn_url, model, body)
        return (
            response, session, model, city_id, venue_id, outcomes,
            elapsed_before, rng_before,
        )

    async def test_recorded_stonework_investigation_does_not_route_as_travel_over_http(self):
        city_id, session_id, session, turn_url, venue_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        model = RecordedStoneworkOllamaClient()
        outcomes = []
        original_turn = session.run_player_turn

        @wraps(original_turn)
        def capture_turn(*args, **kwargs):
            result = original_turn(*args, **kwargs)
            outcomes.append(copy.deepcopy(result.get("action_result", {})))
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await self.post_scene_turn(
                turn_url,
                model,
                {
                    "message": "Han binasının girişindeki taş işçiliğini inceliyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(model.intent_schema_has_scene_proposals)
        self.assertEqual(model.intent_response["intent"], "investigation")
        self.assertEqual(len(outcomes), 1)
        action_result = outcomes[0]
        self.assertNotEqual(
            action_result.get("action"),
            "travel",
            f"Investigating the entrance must not route as travel: {action_result!r}",
        )
        self.assertEqual(session.world_state["location"], city_id)
        self.assertIsNone(session.world_state["flags"].get("pending_destination"))
        self.assertTrue(action_result.get("scene_detail_proposal_submitted"))
        self.assertEqual(
            action_result.get("verified_world_updates", {}).get("create_features"),
            [],
        )
        self.assertFalse(any(
            item.get("name") == "Gizli taş işçiliği detayı"
            for item in session.world_state["features"]
        ))
        record = self.manager.get(session_id)
        persisted = self.store.get_campaign(record.campaign_id)
        self.assertEqual(
            persisted.payload["engine_save"]["world_state"]["location"],
            city_id,
        )
        self.assertFalse(any(
            item.get("name") == "Gizli taş işçiliği detayı"
            for item in persisted.payload["engine_save"]["world_state"]["features"]
        ))
        public_response = json.dumps(response.json(), ensure_ascii=False)
        for internal_value in (
            "Gizli taş işçiliği detayı",
            "gizli geçit",
            "tarihî bilgi",
        ):
            self.assertNotIn(internal_value, public_response)

    async def test_public_api_capture_binds_scene_detail_location_and_parent_contract(self):
        city_id, _, _, turn_url, venue_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        model = RecordedStoneworkOllamaClient()
        response = await self.post_scene_turn(
            turn_url,
            model,
            {
                "message": "Han binasının girişindeki taş işçiliğini inceliyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(model.intent_schema_has_scene_proposals)
        prompt = next(
            message["content"] for message in model.intent_messages
            if message.get("role") == "user"
        )
        properties = model.intent_schema["properties"]["scene_detail_proposals"]["items"]["properties"]
        observed = {
            "prompt_has_exact_current_scene_id": (
                f"Current scene ID: {city_id}" in prompt
            ),
            "prompt_has_exact_parent_structure_id": (
                f"Parent structure ID: {venue_id}" in prompt
            ),
            "prompt_has_kind_allowlist_and_scope": (
                "kind yalnızca detail veya seat olabilir" in prompt
                and "seat yalnızca sıradan, görünür bir oturma yüzeyini adlandırır"
                in prompt
                and "yeni etkileşim veya mekanik açmaz" in prompt
            ),
            "location_enum": properties["location"].get("enum"),
            "parent_id_enum": properties["parent_id"].get("enum"),
            "kind_enum": properties["kind"].get("enum"),
        }
        expected = {
            "prompt_has_exact_current_scene_id": True,
            "prompt_has_exact_parent_structure_id": True,
            "prompt_has_kind_allowlist_and_scope": True,
            "location_enum": [city_id],
            "parent_id_enum": [venue_id],
            "kind_enum": ["detail", "seat"],
        }
        self.assertEqual(observed, expected)

    async def test_ordinary_stonework_proposal_for_city_and_inn_is_accepted_and_persisted(self):
        city_id, session_id, session, turn_url, venue_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        name = "Düzenli keski izleri"
        model = ControlledSceneDetailOllamaClient(
            city_id,
            venue_id,
            proposals=[{
                "proposal_key": "ordinary_stonework",
                "location": city_id,
                "parent_id": venue_id,
                "name": name,
                "description": "Giriş taşında düzenli keski izleri görünüyor.",
                "kind": "detail",
                "aliases": ["keski izleri"],
            }],
        )
        outcomes = []
        original_turn = session.run_player_turn

        @wraps(original_turn)
        def capture_turn(*args, **kwargs):
            result = original_turn(*args, **kwargs)
            outcomes.append(copy.deepcopy(result.get("action_result", {})))
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await self.post_scene_turn(
                turn_url,
                model,
                {
                    "message": "Han binasının girişindeki taş işçiliğini inceliyorum.",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(model.last_intent_schema_has_proposals)
        self.assertEqual(session.world_state["location"], city_id)
        feature = next(
            item for item in session.world_state["features"]
            if item.get("name") == name
        )
        self.assertEqual(feature.get("parent_id"), venue_id)
        self.assertTrue(outcomes[0].get("scene_detail_proposal_submitted"))
        record = self.manager.get(session_id)
        persisted = self.store.get_campaign(record.campaign_id)
        saved_features = persisted.payload["engine_save"]["world_state"]["features"]
        self.assertTrue(any(
            item.get("name") == name and item.get("parent_id") == venue_id
            for item in saved_features
        ))

    async def test_review_denied_and_other_actor_intents_do_not_accept_details(self):
        for index, message in enumerate((
            "Han binasını inceliyorum demiyorum.",
            "Muhafız han binasını inceliyor.",
        )):
            with self.subTest(message=message):
                name = f"Denied detail {index}"
                proposal = [{
                    "proposal_key": "f1", "location": "fr:city:neverwinter",
                    "parent_id": "location_001", "name": name,
                    "description": "A newly proposed detail.", "kind": "detail",
                }]
                response, session, _, _, _, outcomes, *_ = await self.run_review_scene_turn(
                    message, proposal, narration=f"{name} is visible."
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(any(
                    row.get("name") == name for row in session.world_state["features"]
                ))
                self.assertNotIn(name, response.json()["narration"])
                self.assertNotIn(
                    outcomes[0].get("action"),
                    {"inspect", "investigation", "skill_check"},
                )

    async def test_review_explicit_unknown_parent_does_not_bind_single_candidate(self):
        name = "Wrong-parent detail"
        response, session, _, _, first_id, *_ = await self.run_review_scene_turn(
            "I inspect Second Inn building.",
            [{
                "proposal_key": "f1", "location": "fr:city:neverwinter",
                "parent_id": "location_001", "name": name,
                "description": "A visible detail.", "kind": "detail",
            }],
            narration=f"{name} is in Second Inn.",
            prepare=lambda session, city, venue: session.world_state["locations"][venue].update(
                name="First Inn", aliases=["First Inn"]
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(any(
            row.get("name") == name for row in session.world_state["features"]
        ))
        self.assertNotIn(name, response.json()["narration"])

    async def test_review_acceptance_enforces_one_detail_limit_and_rejects_unsupported_mechanics(self):
        proposals = [{
            "proposal_key": f"f{i}", "location": "fr:city:neverwinter",
            "parent_id": "location_001", "name": f"Detail {i}",
            "description": "A small visible carving.", "kind": "detail",
        } for i in range(4)]
        response, session, *_ = await self.run_review_scene_turn(
            "I inspect the inn building.", proposals,
            narration="Four new details are present.",
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(sum(
            row.get("name", "").startswith("Detail ")
            for row in session.world_state["features"]
        ), 1)

        for name, description in (
            ("Open Entrance", "The entrance is open and leads inside."),
            ("Secret Passage", "A secret passage leads into the locked inn."),
        ):
            with self.subTest(name=name):
                response, session, *_ = await self.run_review_scene_turn(
                    f"I inspect the {name.lower()}.",
                    [{
                        "proposal_key": "f1", "location": "fr:city:neverwinter",
                        "parent_id": "location_001", "name": name,
                        "description": description, "kind": "detail",
                    }],
                    narration=description,
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(any(
                    row.get("name") == name for row in session.world_state["features"]
                ))

    async def test_review_legacy_unparented_hidden_name_collision_is_rejected(self):
        hidden_name = "Gizli sürgü"
        def prepare(session, city, venue):
            session.world_state["features"].append({
                "id": "legacy-hidden-feature", "location": city,
                "name": hidden_name, "description": "PRIVATE_HIDDEN_DESCRIPTION",
                "kind": "detail", "aliases": [hidden_name], "hidden": True,
            })
        response, session, *_ = await self.run_review_scene_turn(
            "Hanın bulunduğu binayı inceliyorum.",
            [{
                "proposal_key": "f1", "location": "fr:city:neverwinter",
                "parent_id": "location_001", "name": hidden_name,
                "description": "A harmless new detail.", "kind": "detail",
            }],
            narration="A new sliding bolt is visible.", prepare=prepare,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(sum(
            row.get("name") == hidden_name for row in session.world_state["features"]
        ), 1)
        self.assertNotIn("PRIVATE_HIDDEN_DESCRIPTION", response.json()["narration"])

    async def test_review_quote_scope_and_sibling_parent_identity_are_consistent(self):
        name = "Second-only detail"
        def prepare(session, city, first_id):
            session.world_state["locations"][first_id].update(
                name="First Inn", aliases=["First Inn"]
            )
            second_id = f"{first_id}:second-inn"
            second = copy.deepcopy(session.world_state["locations"][first_id])
            second.update(id=second_id, name="Second Inn", aliases=["Second Inn"])
            session.world_state["locations"][second_id] = second
            session._review_second_id = second_id
            session.world_state["features"].append({
                "id": "first-table-sign", "location": city, "parent_id": first_id,
                "name": name, "description": "FIRST_PARENT_PRIVATE_DETAIL",
                "kind": "detail", "aliases": [name, "Tabela"],
            })
            session.world_state["features"].append({
                "id": "second-hidden-sign", "location": city, "parent_id": second_id,
                "name": "Gizli Tabela", "description": "SECOND_HIDDEN_PRIVATE_DETAIL",
                "kind": "detail", "aliases": ["Tabela"], "hidden": True,
            })
        def proposals(session, city, first_id):
            return [{
                "proposal_key": "f1", "location": city,
                "parent_id": session._review_second_id, "name": name,
                "description": "A visible note on the second building.",
                "kind": "detail", "aliases": [],
            }]
        response, session, model, city, first_id, *_ = await self.run_review_scene_turn(
            'I inspect Second Inn building; "First Inn" is only a name.',
            proposals, narration="The second building has a painted mark.",
            prepare=prepare,
        )
        second_id = session._review_second_id
        self.assertEqual(response.status_code, 200, response.text)
        stored = [
            row for row in session.world_state["features"]
            if row.get("name") == name
        ]
        self.assertEqual(len(stored), 2)
        self.assertEqual(
            {row.get("parent_id") for row in stored}, {first_id, second_id}
        )
        self.assertNotIn("FIRST_PARENT_PRIVATE_DETAIL", response.json()["narration"])
        self.assertNotIn("SECOND_HIDDEN_PRIVATE_DETAIL", response.json()["narration"])

        response, session, model, city, first_id, *_ = await self.run_review_scene_turn(
            'I inspect Second Inn building with "Tabela" written in my notebook.',
            proposals,
            narration="A new detail is visible.",
            prepare=prepare,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(any(
            row.get("name") == name and row.get("parent_id") == second_id
            for row in session.world_state["features"]
        ))
        self.assertNotIn("FIRST_PARENT_PRIVATE_DETAIL", response.json()["narration"])
        self.assertNotIn("SECOND_HIDDEN_PRIVATE_DETAIL", response.json()["narration"])

    async def test_review_say_and_ask_dm_do_not_inspect_visible_detail(self):
        for mode in ("say", "ask_dm"):
            with self.subTest(mode=mode):
                sentinel = "PRIVATE_VISIBLE_DETAIL"
                def prepare(session, city, venue):
                    session.world_state["features"].append({
                        "id": "visible-detail", "location": city,
                        "parent_id": venue, "name": "Taş Kartal Kabartması",
                        "description": sentinel, "kind": "detail",
                        "aliases": ["taş kartal"],
                    })
                response, session, model, city, venue, outcomes, elapsed_before, rng_before = await self.run_review_scene_turn(
                    "I inspect the Taş Kartal Kabartması.",
                    [], mode=mode, prepare=prepare,
                    narration=f"The detail reads {sentinel}.",
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn(sentinel, response.json()["narration"])
                self.assertNotIn(outcomes[0].get("status"), {"observed", "not_visible"})
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"],
                    elapsed_before,
                )
                self.assertEqual(session.rng.getstate(), rng_before)
                self.assertEqual(
                    session.world_state["features"][0]["description"], sentinel
                )

    async def test_review_canonical_door_truth_is_normalized_and_independent(self):
        for message, unlocked, expected_count in (
            ("First Inn Door açık.", False, 0),
            ("First Inn Door open.", False, 0),
            ("First Inn Door kapalı.", True, 1),
        ):
            with self.subTest(message=message, unlocked=unlocked):
                name = f"Door claim {expected_count}"
                def prepare(session, city, venue):
                    session.world_state["locations"][venue].update(
                        name="First Inn", aliases=["First Inn"]
                    )
                    door = next(
                        row for row in session.world_state["doors"]
                        if row.get("id") == f"venue-door:{venue}"
                    )
                    door.update(name="First Inn Door", aliases=["First Inn Door"],
                                open=False, locked=not unlocked)
                response, session, *_ = await self.run_review_scene_turn(
                    "I inspect First Inn building.",
                    [{
                        "proposal_key": "f1", "location": "fr:city:neverwinter",
                        "parent_id": "location_001", "name": f"First Inn Door {name}",
                        "description": message, "kind": "detail",
                    }],
                    narration=message, prepare=prepare,
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(sum(
                    row.get("name") == f"First Inn Door {name}"
                    for row in session.world_state["features"]
                ), expected_count)

    async def test_review_seat_kind_cannot_claim_secret_passage_but_real_seating_is_supported(self):
        for name, description, expected_count in (
            (
                "Hidden Passage Seat",
                "A secret passage leads into the locked inn.",
                0,
            ),
            (
                "Window Bench",
                "A sturdy bench sits beneath the window.",
                1,
            ),
        ):
            with self.subTest(name=name):
                response, session, *_ = await self.run_review_scene_turn(
                    "I inspect the inn building.",
                    [{
                        "proposal_key": "seat-1",
                        "location": "fr:city:neverwinter",
                        "parent_id": "location_001",
                        "name": name,
                        "description": description,
                        "kind": "seat",
                        "aliases": [name.lower()],
                    }],
                    narration=description,
                )
                self.assertEqual(response.status_code, 200, response.text)
                matching = [
                    row for row in session.world_state["features"]
                    if row.get("name") == name
                ]
                self.assertEqual(len(matching), expected_count)
                if expected_count:
                    self.assertEqual(matching[0].get("kind"), "seat")
                else:
                    self.assertNotIn(name, response.json()["narration"])

if __name__ == "__main__":
    unittest.main()
