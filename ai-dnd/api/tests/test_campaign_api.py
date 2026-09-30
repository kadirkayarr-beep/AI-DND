"""HTTP-level tests for persistent campaign lifecycle and autosave behavior."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
import quest_catalog
from api.campaign_journal import create_initial_campaign_journal
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


class FakeOllamaClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("Campaign API tests must not call a real model.")


class CampaignApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = CampaignStore(
            Path(self.temporary_directory.name) / "campaigns.sqlite3"
        )
        self.manager = SessionManager(campaign_store=self.store)
        adapter = AuthenticatedOllamaAdapter(FakeOllamaClient())
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=adapter,
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
        self.assertEqual(len(engine_character["proficient_skills"]), 2)
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
        )
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
        expected_skill_count = 4 if random_character["class"] == "Rogue" else 2
        self.assertEqual(len(random_character["proficient_skills"]), expected_skill_count)
        self.assertTrue(set(random_character["proficient_skills"]) <= set(valid_skills))

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
            response = await self.http.post(
                "/api/game/campaigns",
                json={
                    "character": {
                        "mode": "custom",
                        "name": name,
                        "race": race,
                        "class": character_class,
                    }
                },
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


if __name__ == "__main__":
    unittest.main()