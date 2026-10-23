"""Default-mode NPC targeting from the visible scene transcript."""

from __future__ import annotations

import copy
import json
import os
import unittest
import uuid
from unittest.mock import patch

import grounded_action
import living_world
import npc_statements
import local_dialogue
from api.tests import test_campaign_api
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
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


class AttributedPlaceClient(ScriptedNpcSpeechClient):
    def __init__(
        self,
        npc_id: str,
        narration: str,
        *,
        stage_direction: str = "",
    ):
        super().__init__(
            narration=narration,
            stage_direction=stage_direction,
            conversation={
                "addressee_id": npc_id,
                "subject_phrase": "yer",
                "subject_role": "world_entity",
                "meaning": "other",
                "topic_relation": "new",
                "candidate_evidence_ids": [],
            },
        )
        self.npc_id = npc_id
        self.prompts: list[str] = []

    def chat(self, *args, **kwargs):
        messages = kwargs.get("messages", [])
        prompt = next(
            item.get("content", "")
            for item in reversed(messages)
            if item.get("role") == "user"
        )
        self.prompts.append(prompt)
        return super().chat(*args, **kwargs)


class InvalidConversationPlaceClient(AttributedPlaceClient):
    def chat(self, *args, **kwargs):
        response = super().chat(*args, **kwargs)
        packet = json.loads(response["message"]["content"])
        packet["interaction"]["conversation"]["candidate_evidence_ids"] = [
            "unavailable-evidence-id"
        ]
        response["message"]["content"] = json.dumps(packet, ensure_ascii=False)
        return response


class DefaultNpcTargetingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        self.enterContext(
            patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "0"})
        )

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    async def _focused_recommendation_fixture(self, *, unlock=True):
        city_id, _, session, turn_url, tavern_id, _ = (
            await create_city_with_locked_tavern(self)
        )
        if unlock:
            test_campaign_api.unlock_venue_door(session.world_state, tavern_id)
        guard = {
            "id": "npc_recommendation_turn_guard",
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
        targeter = DescriptorTargetClient(guard["id"], scene)
        greeting = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            targeter,
            {
                "message": "Pazar girişindeki mavi pelerinli muhafıza selam veriyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(greeting.status_code, 200, greeting.text)
        self.assertEqual(
            session.world_state["flags"].get("last_npc_id"), guard["id"]
        )
        return city_id, session, turn_url, tavern_id, guard

    async def _recommendation_turn(self, turn_url, client, message):
        with patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "1"}):
            return await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                client,
                {
                    "message": message,
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )

    async def test_recovered_speech_and_stage_replay_as_one_grounded_transcript(self):
        _, session, turn_url, tavern_id, guard = (
            await self._focused_recommendation_fixture()
        )
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        raw_spoken = "Karanlık Han'ı deneyin, orada sakin bir ortam var."
        raw_stage = (
            "Marek, pazar meydanında biraz uzaklaşarak karanlık hanı gösterir."
        )
        recovered_question = (
            "Bu şehirde akşam oturmak için hangi hanı önerirsin?"
        )
        self.assertTrue(
            local_dialogue.is_local_place_recommendation_request(recovered_question)
        )
        self.assertFalse(
            local_dialogue.is_local_place_recommendation_request(
                "Masa başında oturuyorum."
            )
        )
        client = AttributedPlaceClient(
            guard["id"], raw_spoken, stage_direction=raw_stage
        )
        response = await self._recommendation_turn(
            turn_url, client, recovered_question
        )
        self.assertEqual(response.status_code, 200, response.text)
        after = response.json()["narration"]
        expected = (
            f'Marek: “Bildiğim ve şu anda gidebileceğin yerlerden '
            f'{tavern_name} iyi bir seçenek olabilir.”'
        )
        self.assertEqual(after, expected)
        self.assertNotIn("Karanlık Han", after)
        if os.environ.get("AI_DND_CAPTURE_REPLAY_EVIDENCE") == "1":
            before = (
                "Marek (Marek, pazar meydanında biraz uzaklaşarak karanlık hanı "
                "gösterir): “Karanlık Han'ı deneyin, orada sakin bir ortam var.”"
            )
            print("RECOVERED_VISIBLE_BEFORE=" + json.dumps(before, ensure_ascii=False))
            print("RECOVERED_VISIBLE_AFTER=" + json.dumps(after, ensure_ascii=False))

    def test_scene_sitting_classifier_ignores_infinitive_and_nonaffirmative_forms(self):
        self.assertIsNone(
            living_world.classify_scene_action(
                "Bu şehirde akşam oturmak için hangi hanı önerirsin?"
            )
        )
        self.assertEqual(
            living_world.classify_scene_action("Masa başında oturuyorum."),
            "sit",
        )
        self.assertIsNone(
            living_world.classify_scene_action("Masa başında oturmuyorum.")
        )
        self.assertIsNone(
            living_world.classify_scene_action(
                "Masa başında oturursam haber veririm."
            )
        )
        self.assertEqual(
            living_world.classify_scene_action(
                "Muhafıza soruyorum ve sandalyeye oturuyorum."
            ),
            "sit",
        )

    async def test_direct_sitting_action_is_not_consumed_as_npc_dialogue_over_http(self):
        _, _, turn_url, _, guard = await self._focused_recommendation_fixture()
        client = AttributedPlaceClient(guard["id"], "Bir hanı tavsiye ederim.")
        response = await self._recommendation_turn(
            turn_url, client, "Masa başında oturuyorum."
        )
        self.assertEqual(response.status_code, 200, response.text)
        visible = response.json()["narration"]
        self.assertIn("oturabileceğin", visible.casefold())
        self.assertNotIn("Marek:", visible)
        self.assertNotIn("iyi bir seçenek olabilir", visible)

    async def test_recommendation_matches_an_alternate_canonical_option_over_http(self):
        city_id, session, turn_url, _, guard = (
            await self._focused_recommendation_fixture()
        )
        session.world_state["locations"]["place_gumus_fener"] = {
            "id": "place_gumus_fener",
            "name": "Gümüş Fener Hanı",
            "type": "building",
            "scene_kind": "tavern",
            "parent_location_id": city_id,
            "hidden": False,
            "aliases": [],
        }
        client = AttributedPlaceClient(
            guard["id"], "Gümüş Fener Hanı şehirde güzel bir seçenek."
        )
        response = await self._recommendation_turn(
            turn_url, client, "Şehirde gidebileceğim sakin bir yer önerir misin?"
        )
        self.assertEqual(response.status_code, 200, response.text)
        visible = response.json()["narration"]
        self.assertIn("Gümüş Fener Hanı", visible)
        self.assertNotIn("Karanlık Han", visible)

    async def test_specific_tavern_recommendation_ignores_unrelated_canonical_service(self):
        city_id, session, turn_url, tavern_id, guard = (
            await self._focused_recommendation_fixture()
        )
        session.world_state["locations"]["unrelated-workshop"] = {
            "id": "unrelated-workshop",
            "name": "Bakır Atölyesi",
            "type": "building",
            "scene_kind": "building",
            "place_kind": "workshop",
            "parent_location_id": city_id,
            "hidden": False,
            "aliases": ["atölye"],
        }
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        question = "Bu şehirde akşam oturmak için hangi hanı önerirsin?"
        self.assertEqual(
            local_dialogue.local_place_recommendation_kind(question), "tavern"
        )
        self.assertFalse(local_dialogue.is_open_local_place_discovery(question))
        client = AttributedPlaceClient(
            guard["id"],
            "Karanlık Han'ı deneyin, orada sakin bir ortam var.",
            stage_direction="Marek karanlık hana doğru yürür.",
        )
        response = await self._recommendation_turn(turn_url, client, question)
        self.assertEqual(response.status_code, 200, response.text)
        visible = response.json()["narration"]
        self.assertIn(tavern_name, visible)
        self.assertNotIn("Bakır Atölyesi", visible)
        self.assertNotIn("Karanlık Han", visible)
        self.assertNotIn("yürür", visible)

    async def test_recommendation_without_visible_options_stays_a_rumor_over_http(self):
        _, session, turn_url, tavern_id, guard = (
            await self._focused_recommendation_fixture()
        )
        session.world_state["locations"][tavern_id]["hidden"] = True
        client = AttributedPlaceClient(
            guard["id"],
            "Karanlık Han'ı deneyin, orada sakin bir ortam var.",
            stage_direction="Marek karanlık hana doğru yürür.",
        )
        response = await self._recommendation_turn(
            turn_url, client, "Şehirde gidebileceğim sakin bir yer önerir misin?"
        )
        self.assertEqual(response.status_code, 200, response.text)
        visible = response.json()["narration"]
        self.assertIn("söylenti", visible)
        self.assertNotIn("yürür", visible)

    async def test_hidden_place_is_not_named_or_pointed_to_over_http(self):
        city_id, session, turn_url, _, guard = (
            await self._focused_recommendation_fixture()
        )
        session.world_state["locations"]["secret_inn"] = {
            "id": "secret_inn",
            "name": "Gizli Fener Hanı",
            "type": "building",
            "scene_kind": "tavern",
            "parent_location_id": city_id,
            "hidden": True,
            "aliases": [],
        }
        client = AttributedPlaceClient(
            guard["id"],
            "Gizli Fener Hanı'na git.",
            stage_direction="Marek Gizli Fener Hanı'nı gösterir.",
        )
        response = await self._recommendation_turn(
            turn_url, client, "Şehirde gidebileceğim sakin bir yer önerir misin?"
        )
        self.assertEqual(response.status_code, 200, response.text)
        visible = response.json()["narration"]
        self.assertNotIn("Gizli Fener Hanı", visible)
        self.assertNotIn("gösterir", visible)

    async def test_locked_recommendation_does_not_claim_entry_is_possible_over_http(self):
        _, session, turn_url, tavern_id, guard = (
            await self._focused_recommendation_fixture(unlock=False)
        )
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        client = AttributedPlaceClient(
            guard["id"], f"{tavern_name}'na git; içerisi açık."
        )
        response = await self._recommendation_turn(
            turn_url, client, "Şehirde gidebileceğim sakin bir yer önerir misin?"
        )
        self.assertEqual(response.status_code, 200, response.text)
        visible = response.json()["narration"]
        self.assertIn("kilitli", visible)
        self.assertNotIn("iyi bir seçenek olabilir", visible)
        self.assertNotIn("açık", visible)

    async def test_combined_name_and_place_recommendation_is_grounded_over_http(self):
        _, session, turn_url, tavern_id, guard = (
            await self._focused_recommendation_fixture()
        )
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        client = AttributedPlaceClient(guard["id"], "Karanlık Han'ı deneyin.")
        response = await self._recommendation_turn(
            turn_url,
            client,
            "Marek, şehirde gidebileceğim sakin bir yer önerir misin?",
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(tavern_name, response.json()["narration"])
        self.assertNotIn("Karanlık Han", response.json()["narration"])

    async def test_harmless_gesture_survives_place_repair_over_http(self):
        _, session, turn_url, tavern_id, guard = (
            await self._focused_recommendation_fixture()
        )
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        client = AttributedPlaceClient(
            guard["id"],
            "Karanlık Han'ı deneyin.",
            stage_direction="Marek omuz silker.",
        )
        response = await self._recommendation_turn(
            turn_url, client, "Şehirde gidebileceğim sakin bir yer önerir misin?"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["narration"],
            f'Marek (omuz silker): “Bildiğim ve şu anda gidebileceğin '
            f'yerlerden {tavern_name} iyi bir seçenek olabilir.”',
        )

    async def test_unapproved_player_motion_is_removed_but_harmless_gesture_survives(self):
        _, session, turn_url, tavern_id, guard = (
            await self._focused_recommendation_fixture()
        )
        tavern_name = session.world_state["locations"][tavern_id]["name"]
        client = AttributedPlaceClient(
            guard["id"],
            "Karanlık Han'ı deneyin.",
            stage_direction=(
                "Marek gülümser. Oyuncu Dagna Hanı'na girer."
            ),
        )
        response = await self._recommendation_turn(
            turn_url, client, "Şehirde gidebileceğim sakin bir yer önerir misin?"
        )
        self.assertEqual(response.status_code, 200, response.text)
        visible = response.json()["narration"]
        self.assertIn("Marek (gülümser):", visible)
        self.assertNotIn("Oyuncu", visible)
        self.assertNotIn("girer", visible)
        self.assertIn(tavern_name, visible)

    async def test_default_npc_reply_uses_direct_speaker_prompt_over_http(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        npc = {
            "id": "npc_dialogue_prompt_regression",
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
        flags = session.world_state["flags"]
        flags["last_npc_id"] = npc["id"]
        flags["active_npc_id"] = npc["id"]
        flags["active_npc_until_turn"] = flags.get("turn_index", 0) + 5

        client = AttributedPlaceClient(
            npc["id"], "Marek: “Bunu tam bilmiyorum; bugün burası bana da sakin geliyor.”"
        )
        captured = {}
        run_player_turn = session.run_player_turn

        def capture_turn(*args, **kwargs):
            result = run_player_turn(*args, **kwargs)
            captured["telemetry"] = result["_engine_event_evidence"]["telemetry"]
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                client,
                {
                    "message": "Marek, bu yer neden sessiz?",
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["narration"], client.narration)
        self.assertEqual(captured["telemetry"]["narration_source"], "qwen")
        self.assertEqual(
            captured["telemetry"]["narration_validation_result"], "accepted"
        )
        self.assertTrue(any(
            "NPC dialogue mode" in prompt
            and "natural, direct speech" in prompt
            and "Answer the player's actual question" in prompt
            and "Marek" in prompt
            for prompt in client.prompts
        ), client.prompts)

    async def test_local_place_recommendation_reaches_focused_npc_in_default_mode(self):
        city_id, _, session, turn_url, _, _ = await create_city_with_locked_tavern(self)
        guard = {
            "id": "npc_default_recommendation_guard",
            "name": "Marek",
            "role": "guard",
            "role_known_to_player": True,
            "appearance": "Pazar girişinde mavi pelerinli bir muhafız.",
            "location": city_id,
            "status": "active",
            "current_hp": 12,
            "combat_status": "active",
            "memory": [],
        }
        session.world_state["npcs"].append(guard)
        scene = "Pazar girişinde mavi pelerinli muhafız arabaları kontrol ediyor."
        session.messages.append({"role": "assistant", "content": scene})
        greeting = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            DescriptorTargetClient(guard["id"], scene),
            {
                "message": "Pazar girişindeki mavi pelerinli muhafıza selam veriyorum.",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(greeting.status_code, 200, greeting.text)
        self.assertEqual(
            session.world_state["flags"].get("last_npc_id"), guard["id"]
        )

        client = InvalidConversationPlaceClient(
            guard["id"],
            "Marek: “Şehirdeki han kısa bir mola için sakin bir yer.”",
        )
        before_locations = set(session.world_state["locations"])
        captured = {}
        run_player_turn = session.run_player_turn

        def capture_turn(*args, **kwargs):
            result = run_player_turn(*args, **kwargs)
            captured["telemetry"] = result["_engine_event_evidence"]["telemetry"]
            return result

        with patch.object(session, "run_player_turn", new=capture_turn):
            response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                client,
                {
                    "message": "Şehirde gidebileceğim sakin bir yer önerir misin?",
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(client.chat_calls, 0)
        self.assertEqual(captured["telemetry"]["narration_source"], "qwen")
        self.assertEqual(
            captured["telemetry"]["narration_validation_result"], "accepted"
        )
        self.assertEqual(
            session.world_state["flags"].get("last_npc_id"), guard["id"]
        )
        self.assertEqual(set(session.world_state["locations"]), before_locations)

    async def test_entry_door_can_be_inspected_from_its_venue_interior(self):
        city_id, _, session, turn_url, tavern_id, door = (
            await create_city_with_locked_tavern(self)
        )
        unlock_venue_door(session.world_state, tavern_id)
        enter = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            test_campaign_api.FakeOllamaClient(),
            {
                "message": f"{session.world_state['locations'][tavern_id]['name']} içine giriyorum.",
                "interaction_mode": "do",
                "target_id": tavern_id,
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(enter.status_code, 200, enter.text)
        self.assertEqual(enter.json()["state"]["location"], tavern_id)
        self.assertEqual(door["location"], city_id)
        self.assertIsNone(
            session.world_state.get("grounded_actions", {}).get("near_target_id")
        )

        inspect = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            test_campaign_api.FakeOllamaClient(),
            {
                "message": f"{door['name']} kilidini dikkatlice inceliyorum.",
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(inspect.status_code, 200, inspect.text)
        outcome = inspect.json()["turn_outcome"]
        self.assertEqual(outcome.get("action"), "grounded_action", inspect.json())
        self.assertEqual(outcome.get("status"), "completed", inspect.json())
        self.assertEqual(outcome.get("kind"), "door", inspect.json())
        self.assertEqual(outcome.get("target_name"), door["name"], inspect.json())
        self.assertEqual(inspect.json()["state"]["location"], tavern_id)

    async def test_registered_lysa_name_does_not_turn_door_inspection_conditional(self):
        for venue_name in ("Lysa Hanı", "Alysa Hanı"):
            with self.subTest(venue_name=venue_name):
                city_id, _, session, turn_url, tavern_id, door = (
                    await create_city_with_locked_tavern(self)
                )
                session.world_state["locations"][tavern_id]["name"] = venue_name
                door.update({
                    "name": f"{venue_name} Kapısı",
                    "description": f"{venue_name} Kapısı",
                    "open": False,
                    "locked": True,
                    "broken": False,
                })

                response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                    self,
                    turn_url,
                    test_campaign_api.FakeOllamaClient(),
                    {
                        "message": f"{venue_name} Kapısı üzerindeki kilidi dikkatlice inceliyorum.",
                        "interaction_mode": "do",
                        "action_id": str(uuid.uuid4()),
                    },
                )

                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                outcome = payload["turn_outcome"]
                self.assertEqual(outcome.get("action"), "grounded_action", payload)
                self.assertEqual(outcome.get("status"), "completed", payload)
                self.assertEqual(outcome.get("kind"), "door", payload)
                self.assertEqual(outcome.get("target_name"), door["name"], payload)
                self.assertEqual(payload["state"]["location"], city_id)
                self.assertEqual(
                    {key: door.get(key) for key in ("open", "locked", "broken")},
                    {"open": False, "locked": True, "broken": False},
                )
                narration = payload.get("narration", "")
                self.assertIn(door["name"], narration)
                self.assertIn("kilitli", narration.casefold())

                negative = await test_campaign_api.CampaignApiTests.post_scene_turn(
                    self,
                    turn_url,
                    test_campaign_api.FakeOllamaClient(),
                    {
                        "message": f"{venue_name} Kapısını açmıyorum.",
                        "interaction_mode": "do",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(negative.status_code, 200, negative.text)
                self.assertNotEqual(negative.json()["turn_outcome"].get("status"), "completed")
                self.assertEqual(negative.json()["state"]["location"], city_id)
                self.assertEqual(
                    {key: door.get(key) for key in ("open", "locked", "broken")},
                    {"open": False, "locked": True, "broken": False},
                )

                conditional = await test_campaign_api.CampaignApiTests.post_scene_turn(
                    self,
                    turn_url,
                    test_campaign_api.FakeOllamaClient(),
                    {
                        "message": f"Eğer {venue_name} Kapısı açıksa içeri giriyorum.",
                        "interaction_mode": "do",
                        "action_id": str(uuid.uuid4()),
                    },
                )
                self.assertEqual(conditional.status_code, 200, conditional.text)
                self.assertNotEqual(
                    conditional.json()["turn_outcome"].get("status"), "completed"
                )
                self.assertEqual(conditional.json()["state"]["location"], city_id)
                self.assertEqual(
                    {key: door.get(key) for key in ("open", "locked", "broken")},
                    {"open": False, "locked": True, "broken": False},
                )

    async def test_registered_name_keeps_real_condition_and_sibling_target_separate(self):
        city_id, _, session, turn_url, lysa_id, lysa_door = (
            await create_city_with_locked_tavern(self)
        )
        lysa = session.world_state["locations"][lysa_id]
        lysa.update({"name": "Lysa Hanı", "scene_kind": "tavern", "type": "inn"})
        lysa_door.update({
            "name": "Lysa Hanı Kapısı",
            "description": "Lysa Hanı Kapısı",
            "open": False,
            "locked": True,
            "broken": False,
        })

        alysa_id = "test:local:alysa-venue"
        alysa = copy.deepcopy(lysa)
        alysa.update({
            "id": alysa_id,
            "name": "Alysa Hanı",
            "parent_location_id": city_id,
            "exit_location_id": city_id,
        })
        session.world_state["locations"][alysa_id] = alysa
        alysa_door = copy.deepcopy(lysa_door)
        alysa_door.update({
            "id": f"venue-door:{alysa_id}",
            "name": "Alysa Hanı Kapısı",
            "description": "Alysa Hanı Kapısı",
            "location": city_id,
            "open": True,
            "locked": False,
            "broken": False,
        })
        session.world_state["doors"].append(alysa_door)

        alysa_inspection = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            test_campaign_api.FakeOllamaClient(),
            {
                "message": "Alysa Hanı Kapısı üzerindeki kilidi dikkatlice inceliyorum.",
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(alysa_inspection.status_code, 200, alysa_inspection.text)
        alysa_payload = alysa_inspection.json()
        self.assertEqual(alysa_payload["turn_outcome"].get("kind"), "door", alysa_payload)
        self.assertEqual(
            alysa_payload["turn_outcome"].get("target_name"), alysa_door["name"], alysa_payload
        )
        self.assertEqual(alysa_payload["state"]["location"], city_id)
        self.assertTrue(lysa_door["locked"])
        self.assertTrue(alysa_door["open"])
        self.assertFalse(alysa_door["locked"])
        self.assertFalse(alysa_door["broken"])
        self.assertNotIn(lysa_door["name"], alysa_payload["narration"])
        self.assertIn(alysa_door["name"], alysa_payload["narration"])

        grounded_action.note_near(session.world_state, lysa_door["id"])

        conditional = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            test_campaign_api.FakeOllamaClient(),
            {
                "message": "Eğer Lysa Hanı Kapısı açıksa Alysa Hanına giriyorum.",
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(conditional.status_code, 200, conditional.text)
        payload = conditional.json()
        self.assertNotEqual(payload["turn_outcome"].get("status"), "completed", payload)
        self.assertEqual(payload["state"]["location"], city_id, payload)
        self.assertFalse(lysa_door["open"])
        self.assertTrue(lysa_door["locked"])
        self.assertTrue(alysa_door["open"])
        self.assertFalse(alysa_door["locked"])
        self.assertNotIn("Alysa Hanı içine giriyorsun", payload.get("narration", ""))
        self.assertTrue(
            any(term in payload.get("narration", "").casefold() for term in ("koşul", "kilit", "kapalı")),
            payload.get("narration", ""),
        )

    async def test_sibling_door_name_does_not_cross_bind_lysa_and_alysa(self):
        city_id, _, session, turn_url, lysa_id, lysa_door = (
            await create_city_with_locked_tavern(self)
        )
        lysa = session.world_state["locations"][lysa_id]
        lysa.update({"name": "Lysa Hanı", "scene_kind": "tavern", "type": "inn"})
        lysa_door.update({
            "name": "Lysa Hanı Kapısı",
            "description": "Lysa Hanı Kapısı",
            "open": False,
            "locked": True,
            "broken": False,
        })
        alysa_id = "test:local:alysa-venue"
        alysa = copy.deepcopy(lysa)
        alysa.update({
            "id": alysa_id,
            "name": "Alysa Hanı",
            "parent_location_id": city_id,
            "exit_location_id": city_id,
        })
        session.world_state["locations"][alysa_id] = alysa
        alysa_door = copy.deepcopy(lysa_door)
        alysa_door.update({
            "id": f"venue-door:{alysa_id}",
            "name": "Alysa Hanı Kapısı",
            "description": "Alysa Hanı Kapısı",
            "location": city_id,
            "open": True,
            "locked": False,
            "broken": False,
        })
        session.world_state["doors"].append(alysa_door)

        alysa_inspection = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            test_campaign_api.FakeOllamaClient(),
            {
                "message": "Alysa Hanı Kapısı üzerindeki kilidi dikkatlice inceliyorum.",
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(alysa_inspection.status_code, 200, alysa_inspection.text)
        self.assertEqual(
            alysa_inspection.json()["turn_outcome"].get("target_name"),
            alysa_door["name"],
            alysa_inspection.json(),
        )
        before_location = alysa_inspection.json()["state"]["location"]
        before_doors = {
            "Lysa": {key: lysa_door.get(key) for key in ("open", "locked", "broken")},
            "Alysa": {key: alysa_door.get(key) for key in ("open", "locked", "broken")},
        }

        response = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self,
            turn_url,
            test_campaign_api.FakeOllamaClient(),
            {
                "message": "Lysa Hanı Kapısı üzerindeki kilidi dikkatlice inceliyorum.",
                "interaction_mode": "do",
                "action_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["turn_outcome"].get("kind"), "door", payload)
        after_doors = {
            "Lysa": {key: lysa_door.get(key) for key in ("open", "locked", "broken")},
            "Alysa": {key: alysa_door.get(key) for key in ("open", "locked", "broken")},
        }
        state_diff = {}
        if before_location != payload["state"]["location"]:
            state_diff["location"] = {
                "before": before_location,
                "after": payload["state"]["location"],
            }
        for door_name in before_doors:
            if before_doors[door_name] != after_doors[door_name]:
                state_diff[f"door:{door_name}"] = {
                    "before": before_doors[door_name],
                    "after": after_doors[door_name],
                }
        narration = payload.get("narration", "")
        diagnostic = json.dumps({
            "expected_target": lysa_door["name"],
            "actual_target": payload["turn_outcome"].get("target_name"),
            "visible_answer": narration,
            "player_location": {
                "before": before_location,
                "after": payload["state"]["location"],
            },
            "state_diff": state_diff,
        }, ensure_ascii=False, sort_keys=True)
        self.assertEqual(state_diff, {}, diagnostic)
        self.assertEqual(
            payload["turn_outcome"].get("target_name"), lysa_door["name"], diagnostic
        )
        self.assertIn(lysa_door["name"], narration)
        self.assertIn("kilitli", narration.casefold())

    async def test_failed_investigation_http_keeps_result_and_rejects_player_agency_claims(self):
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
        session_id = created.json()["session_id"]
        record = self.manager.get(session_id)
        session = record.game_session
        before_world = copy.deepcopy(session.world_state)
        before_receipt_refs = set(record.lore_authority.procedural_entity_refs)
        campaign_id = record.campaign_id
        turn_url = f"/api/game/sessions/{session_id}/turn"

        class FailedInvestigationClient(test_campaign_api.FakeOllamaClient):
            def __init__(self):
                self.prompts = []

            def chat(self, *args, **kwargs):
                messages = kwargs.get("messages", [])
                prompt = next(
                    item.get("content", "")
                    for item in reversed(messages)
                    if item.get("role") == "user"
                )
                self.prompts.append(prompt)
                properties = kwargs.get("format", {}).get("properties", {})
                if "intent" in properties:
                    packet = {
                        "intent": "investigation",
                        "action": "investigate",
                        "target": {
                            "type": "location",
                            "reference": "Han binasının girişindeki taş işçiliği",
                            "npc_id": "",
                            "evidence_quote": "",
                        },
                        "completion": "intended",
                        "confidence": 1.0,
                        "interaction": {"operation": "none"},
                    }
                else:
                    packet = {
                        "narration": (
                            "Taş işçiliğine dair net bir ayrıntı seçemiyorsun. "
                            "Korkmuş hissedersin. Sonra hana girersin."
                        ),
                        "world_updates": {},
                        "lore_claims": [],
                    }
                return {"message": {"content": json.dumps(packet, ensure_ascii=False)}}

        client = FailedInvestigationClient()
        captured = {}
        run_player_turn = session.run_player_turn

        def capture_turn(*args, **kwargs):
            result = run_player_turn(*args, **kwargs)
            captured["action_result"] = dict(result.get("action_result", {}))
            captured["telemetry"] = result["_engine_event_evidence"]["telemetry"]
            return result

        with patch("game.roll_d20", return_value=1):
            with patch.object(session, "run_player_turn", new=capture_turn):
                response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                    self,
                    turn_url,
                    client,
                    {
                        "message": (
                            "Han binasının girişindeki taş işçiliğini "
                            "sistemli biçimde inceliyorum."
                        ),
                        "interaction_mode": "do",
                        "target_id": city_id,
                        "action_id": str(uuid.uuid4()),
                    },
                )

        self.assertEqual(response.status_code, 200, (response.text, captured))
        action_result = captured["action_result"]
        self.assertEqual(action_result["action"], "skill_check", action_result)
        self.assertEqual(action_result["skill"], "Investigation", action_result)
        self.assertEqual(action_result["dc"], 15, action_result)
        self.assertEqual(action_result["resolution"]["raw_rolls"], [1], action_result)
        self.assertEqual(action_result["resolution"]["selected_roll"], 1, action_result)
        self.assertFalse(action_result["success"], action_result)
        self.assertEqual(action_result["outcome"], "failure", action_result)
        public_check = response.json()["skill_check_result"]
        self.assertEqual(public_check["d20"], 1)
        self.assertEqual(public_check["dc"], 15)
        self.assertEqual(public_check["outcome"], "failure")
        self.assertEqual(response.json()["turn_outcome"]["status"], "resolved")
        self.assertEqual(session.world_state["location"], city_id)
        procedural_entity_refs = test_campaign_api.main_module._procedural_entity_refs
        actual_added_refs = (
            procedural_entity_refs(session.world_state)
            - procedural_entity_refs(before_world)
        )
        committed_added_refs = (
            set(record.lore_authority.procedural_entity_refs)
            - before_receipt_refs
        )
        self.assertTrue(actual_added_refs, "fixture must materialize procedural entities")
        self.assertEqual(committed_added_refs, actual_added_refs)
        persisted = self.store.get_campaign(campaign_id)
        persisted_refs = set(
            persisted.payload["lore_authority"]["procedural_entity_refs"]
        )
        self.assertEqual(persisted_refs - before_receipt_refs, actual_added_refs)
        final_text = response.json()["narration"]
        self.assertNotIn("korkmuş hissedersin", final_text.casefold())
        self.assertNotIn("hana girersin", final_text.casefold())
        telemetry = captured["telemetry"]
        self.assertEqual(telemetry["narration_source"], "deterministic_fallback")
        self.assertEqual(telemetry["fallback_reason"], "INVENTED_PLAYER_ACTION")
        self.assertEqual(
            telemetry["narration_validation_result"], "python_fallback"
        )
        self.assertEqual(
            session.last_narration_safety["reason_code"],
            telemetry["fallback_reason"],
        )
        self.assertEqual(
            session.last_narration_safety["handling"], "python_fallback"
        )

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
        test_campaign_api.unlock_venue_door(session.world_state, tavern_id)
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
                self.assertEqual(place_ref.get("location_id"), tavern_id)
                self.assertEqual(
                    set(session.world_state["locations"]), original_location_ids
                )

        recovered_reply = (
            "Karanlık Han'ı deneyin, orada sakin bir ortam var."
        )
        recovered_stage = (
            "Marek, pazar meydanında biraz uzaklaşarak karanlık hanı gösterir."
        )
        recovered_client = AttributedPlaceClient(
            guard["id"],
            recovered_reply,
            stage_direction=recovered_stage,
        )
        with patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "1"}):
            grounded_response = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self,
                turn_url,
                recovered_client,
                {
                    "message": recommendation_phrasings[0],
                    "interaction_mode": "do",
                    "action_id": str(uuid.uuid4()),
                },
            )
        self.assertEqual(grounded_response.status_code, 200, grounded_response.text)
        self.assertIn(tavern_name, grounded_response.json()["narration"])
        self.assertIn(
            f"{tavern_name} iyi bir seçenek olabilir",
            grounded_response.json()["narration"],
        )
        self.assertNotIn("Karanlık Han", grounded_response.json()["narration"])
        recovered_transcript = grounded_response.json()["narration"]
        self.assertEqual(
            recovered_transcript,
            f'Marek: “Bildiğim ve şu anda gidebileceğin yerlerden '
            f'{tavern_name} iyi bir seçenek olabilir.”',
        )
        recovered_ref = next(
            ref for ref in npc_statements.place_references(
                session.world_state, settlement_id=city_id
            ) if ref.get("name") == tavern_name
        )
        self.assertEqual(recovered_ref.get("location_id"), tavern_id)
        combined_request = (
            "Marek, şehirde gidebileceğim sakin bir yer önerir misin?"
        )
        self.assertTrue(
            local_dialogue.is_local_place_recommendation_request(combined_request)
        )
        combined_reply = test_campaign_api.game._ground_local_place_recommendation_reply(
            recovered_reply,
            guard,
            session.world_state,
            combined_request,
        )
        self.assertIn(tavern_name, combined_reply)
        self.assertNotIn("Karanlık Han", combined_reply)

        locked_world = copy.deepcopy(session.world_state)
        next(
            door for door in locked_world["doors"]
            if door.get("id") == f"venue-door:{tavern_id}"
        )["locked"] = True
        locked_reply = test_campaign_api.game._ground_local_place_recommendation_reply(
            recovered_reply,
            guard,
            locked_world,
            recommendation_phrasings[0],
        )
        self.assertIn(tavern_name, locked_reply)
        self.assertIn("kilitli", locked_reply)
        self.assertNotIn("Karanlık Han", locked_reply)
        self.assertEqual(
            test_campaign_api.game._ground_local_place_recommendation_reply(
                recovered_reply,
                guard,
                locked_world,
                "Neden?",
            ),
            recovered_reply,
        )

        multiple_options_world = copy.deepcopy(session.world_state)
        second_place_id = "test-visible-second-han"
        second_place_name = "Gümüş Fener Hanı"
        multiple_options_world["locations"][second_place_id] = {
            "id": second_place_id,
            "name": second_place_name,
            "type": "building",
            "scene_kind": "tavern",
            "parent_location_id": city_id,
            "aliases": [],
        }
        second_place_reply = (
            f"{second_place_name}'nı severim; orası bana daha uygun geliyor."
        )
        self.assertEqual(
            test_campaign_api.game._ground_local_place_recommendation_reply(
                second_place_reply,
                guard,
                multiple_options_world,
                recommendation_phrasings[0],
            ),
            second_place_reply,
        )

        no_visible_place_world = copy.deepcopy(session.world_state)
        no_visible_place_world["locations"][tavern_id]["hidden"] = True
        no_visible_place_world["locations"]["hidden-place-for-test"] = {
            "id": "hidden-place-for-test",
            "name": "Karanlık Han",
            "type": "building",
            "scene_kind": "tavern",
            "parent_location_id": city_id,
            "hidden": True,
            "aliases": [],
        }
        rumor_reply = test_campaign_api.game._ground_local_place_recommendation_reply(
            recovered_reply,
            guard,
            no_visible_place_world,
            recommendation_phrasings[0],
        )
        self.assertNotIn("Karanlık Han", rumor_reply)
        self.assertIn("söylenti", rumor_reply)
        context_world = copy.deepcopy(no_visible_place_world)
        context_guard = next(
            item for item in context_world["npcs"]
            if item.get("id") == guard["id"]
        )
        context_guard["personal_profile"] = {
            "private_secret": "Mührün altında gizli bir geçit var."
        }
        scoped_context = test_campaign_api.game._experimental_npc_dialogue_context(
            context_world, context_guard
        )
        recommendation_guidance = (
            test_campaign_api.game._local_place_recommendation_guidance(
                recommendation_phrasings[0],
                scoped_context,
                context_world,
            )
        )
        serialized_context = json.dumps(scoped_context, ensure_ascii=False)
        self.assertNotIn("Karanlık Han", recommendation_guidance)
        self.assertNotIn("private_secret", serialized_context)
        self.assertNotIn("Mührün altında", serialized_context)

        self.assertTrue(
            any(
                set(schema.get("properties", {}))
                == {"spoken_text", "stage_direction"}
                and schema.get("required") == ["spoken_text", "stage_direction"]
                for schema in recommendation_client.schemas
            ),
            recommendation_client.schemas,
        )

        refs_before_wrong_addressee = copy.deepcopy(
            npc_statements.place_references(
                session.world_state, settlement_id=city_id
            )
        )
        wrong_addressee_client = AttributedPlaceClient(
            "npc_not_in_this_campaign", quote
        )
        with patch.dict(os.environ, {"AI_DND_NPC_SPEECH": "1"}):
            wrong_addressee_response = (
                await test_campaign_api.CampaignApiTests.post_scene_turn(
                    self,
                    turn_url,
                    wrong_addressee_client,
                    {
                        "message": recommendation_phrasings[0],
                        "interaction_mode": "do",
                        "action_id": str(uuid.uuid4()),
                    },
                )
            )
        self.assertEqual(
            wrong_addressee_response.status_code,
            200,
            wrong_addressee_response.text,
        )
        self.assertFalse(
            any(
                ref.get("said_by") == "npc_not_in_this_campaign"
                for ref in npc_statements.place_references(
                    session.world_state, settlement_id=city_id
                )
            )
        )
        self.assertEqual(
            npc_statements.place_references(
                session.world_state, settlement_id=city_id
            ),
            refs_before_wrong_addressee,
        )
        self.assertEqual(
            session.world_state["flags"].get("last_npc_id"), guard["id"]
        )
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
        # The already active canonical NPC no longer needs a target-parser call.
        # The actual uncertainty answer still takes exactly one speech request.
        self.assertEqual(fallback_client.chat_calls, 1)
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
            self.assertEqual(
                resumed_session.world_state["location"],
                city_id,
            )
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
        city_id, session_id, session, turn_url, tavern_id, protected_door = (
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

        travel_action_id = str(uuid.uuid4())
        travel_body = {
            "message": f"Marek'in söylediği {spoken_place}'ne gidiyorum.",
            "interaction_mode": "do",
            "action_id": travel_action_id,
        }
        engine_receipts = []
        original_dispatch = test_campaign_api.game._dispatch_player_turn

        def capture_dispatch(*args, **kwargs):
            result = original_dispatch(*args, **kwargs)
            engine_receipts.append(
                result.get("action_result") if isinstance(result, dict) else None
            )
            return result

        with patch.object(
            test_campaign_api.game, "_dispatch_player_turn", capture_dispatch
        ):
            travel = await test_campaign_api.CampaignApiTests.post_scene_turn(
                self, turn_url, client, travel_body
            )
        self.assertEqual(travel.status_code, 200, travel.text)
        travel_payload = travel.json()
        travel_outcome = travel_payload["turn_outcome"]
        self.assertEqual(travel_payload["action_id"], travel_action_id)
        self.assertEqual(travel_outcome.get("action"), "grounded_action")
        self.assertEqual(travel_outcome.get("status"), "completed")
        self.assertEqual(travel_outcome.get("target_name"), spoken_place)
        travel_engine_result = engine_receipts[-1]
        self.assertEqual(
            travel_engine_result["steps"][0].get("position"), "at_door"
        )

        materialized_ref = next(
            ref for ref in npc_statements.place_references(
                session.world_state, settlement_id=city_id
            ) if ref.get("name") == spoken_place
        )
        place_id = materialized_ref.get("location_id")
        self.assertIsInstance(place_id, str)
        self.assertEqual(
            travel_engine_result["steps"][0].get("target_id"), place_id
        )
        self.assertNotEqual(place_id, tavern_id)
        self.assertEqual(materialized_ref.get("said_by"), npc["id"])
        self.assertEqual(
            session.world_state["locations"][place_id]["parent_location_id"],
            city_id,
        )
        self.assertEqual(session.world_state["location"], city_id)
        # The player reached the locked venue's street-side entry, not its
        # interior: city is the scene container; the local venue has its own ID.
        self.assertEqual(travel_payload["state"]["location"], city_id)
        self.assertEqual(
            travel_payload["state"]["locations"][city_id]["name"],
            session.world_state["locations"][city_id]["name"],
        )
        entry_door_id = f"venue-door:{place_id}"
        entry_door = next(
            door for door in session.world_state["doors"]
            if door.get("id") == entry_door_id
        )
        self.assertEqual(entry_door.get("location"), city_id)
        self.assertFalse(entry_door.get("open"))
        entry_door_was_locked = bool(entry_door.get("locked"))
        self.assertEqual(
            session.world_state["grounded_actions"]["near_target_id"],
            entry_door_id,
        )
        response_door = next(
            door for door in travel_payload["state"]["doors"]
            if door.get("id") == entry_door_id
        )
        self.assertEqual(response_door.get("location"), city_id)
        self.assertEqual(response_door.get("locked"), entry_door_was_locked)
        self.assertFalse(response_door.get("open"))

        inspect_action_id = str(uuid.uuid4())
        inspect_body = {
            "message": "Kapıyı dikkatlice inceliyorum.",
            "interaction_mode": "do",
            "target_id": entry_door_id,
            "action_id": inspect_action_id,
        }
        inspect = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, inspect_body
        )
        self.assertEqual(inspect.status_code, 200, inspect.text)
        inspect_payload = inspect.json()
        inspect_outcome = inspect_payload["turn_outcome"]
        self.assertEqual(inspect_payload["action_id"], inspect_action_id)
        self.assertEqual(inspect_outcome.get("action"), "grounded_action")
        self.assertEqual(inspect_outcome.get("status"), "completed")
        self.assertEqual(inspect_outcome.get("kind"), "door")
        self.assertEqual(inspect_outcome.get("target_name"), entry_door["name"])
        self.assertEqual(inspect_payload["state"]["location"], city_id)
        self.assertEqual(bool(next(
            door for door in session.world_state["doors"]
            if door.get("id") == entry_door_id
        )["locked"]), entry_door_was_locked)
        self.assertFalse(next(
            door for door in session.world_state["doors"]
            if door.get("id") == entry_door_id
        )["open"])

        self.assertTrue(protected_door["locked"])
        self.assertTrue(next(
            door for door in session.world_state["doors"]
            if door.get("id") == protected_door["id"]
        )["locked"])
        self.assertFalse(next(
            door for door in session.world_state["doors"]
            if door.get("id") == protected_door["id"]
        )["open"])

        second_visit = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, {
                **travel_body,
                "action_id": str(uuid.uuid4()),
            }
        )
        self.assertEqual(second_visit.status_code, 200, second_visit.text)
        self.assertEqual(
            second_visit.json()["turn_outcome"].get("status"), "blocked",
            second_visit.json(),
        )
        self.assertIn(entry_door["name"], second_visit.json()["narration"])
        self.assertEqual(session.world_state["location"], city_id)
        self.assertEqual(
            session.world_state["grounded_actions"]["near_target_id"],
            entry_door_id,
        )
        self.assertEqual(
            len([
                location for location in session.world_state["locations"].values()
                if location.get("name") == spoken_place
            ]),
            1,
        )
        self.assertEqual(bool(entry_door["locked"]), entry_door_was_locked)
        self.assertFalse(entry_door["open"])
        self.assertTrue(protected_door["locked"])
        self.assertFalse(protected_door["open"])

        state_before_travel_replay = json.dumps(
            session.world_state, sort_keys=True, ensure_ascii=False
        )
        calls_before_travel_replay = client.chat_calls
        travel_replay = await test_campaign_api.CampaignApiTests.post_scene_turn(
            self, turn_url, client, travel_body
        )
        self.assertEqual(travel_replay.status_code, 200, travel_replay.text)
        self.assertEqual(travel_replay.json(), travel_payload)
        self.assertEqual(client.chat_calls, calls_before_travel_replay)
        self.assertEqual(
            json.dumps(session.world_state, sort_keys=True, ensure_ascii=False),
            state_before_travel_replay,
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
            self.assertEqual(cold_ref.get("location_id"), place_id)
            self.assertEqual(
                resumed_session.world_state["locations"][place_id]["name"],
                spoken_place,
            )
            self.assertEqual(
                resumed_session.world_state["grounded_actions"]["near_target_id"],
                entry_door_id,
            )
            self.assertEqual(bool(next(
                door for door in resumed_session.world_state["doors"]
                if door.get("id") == entry_door_id
            )["locked"]), entry_door_was_locked)
            self.assertFalse(next(
                door for door in resumed_session.world_state["doors"]
                if door.get("id") == entry_door_id
            )["open"])

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
            cold_travel_replay = await cold_http.post(
                resumed_turn_url, json=travel_body
            )
            cold_inspect_replay = await cold_http.post(
                resumed_turn_url, json=inspect_body
            )
            self.assertEqual(cold_suggestion_replay.status_code, 200)
            self.assertEqual(cold_travel_replay.status_code, 200)
            self.assertEqual(cold_inspect_replay.status_code, 200)
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
            self.assertEqual(
                cold_travel_replay.json()["turn_outcome"],
                travel_payload["turn_outcome"],
            )
            self.assertEqual(
                cold_inspect_replay.json()["turn_outcome"],
                inspect_payload["turn_outcome"],
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
            cold_second_visit = await cold_http.post(
                resumed_turn_url,
                json={**travel_body, "action_id": str(uuid.uuid4())},
            )
            self.assertEqual(cold_second_visit.status_code, 200)
            self.assertEqual(
                cold_second_visit.json()["turn_outcome"].get("status"),
                "blocked",
                cold_second_visit.json(),
            )
            self.assertEqual(
                len([
                    location for location in resumed_session.world_state[
                        "locations"
                    ].values() if location.get("name") == spoken_place
                ]),
                1,
            )
            self.assertEqual(
                resumed_session.world_state["location"],
                city_id,
            )
            self.assertTrue(next(
                door for door in resumed_session.world_state["doors"]
                if door.get("id") == protected_door["id"]
            )["locked"])

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
