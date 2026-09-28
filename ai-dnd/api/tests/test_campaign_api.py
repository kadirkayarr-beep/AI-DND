"""HTTP-level tests for persistent campaign lifecycle and autosave behavior."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
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

    async def test_create_list_detail_resume_and_safe_metadata(self):
        created = await self.create_campaign()
        self.assertTrue(created["campaign_id"])
        self.assertTrue(created["session_id"])
        self.assertEqual(created["history"], [])

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
            return {"narration": "Mira welcomes Arven."}

        session.run_player_turn = complete_turn
        turn = await self.http.post(
            f"/api/game/sessions/{created['session_id']}/turn",
            json={"message": "Mira'ya adım Arven diyorum."},
        )
        self.assertEqual(turn.status_code, 200, turn.text)
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

    async def test_failed_autosave_rolls_back_turn_and_keeps_last_good_save(self):
        created = await self.create_campaign()
        session = self.manager.get(created["session_id"]).game_session
        before = copy.deepcopy(session.serialize_game_state())
        saved_before = self.store.get_campaign(created["campaign_id"]).payload

        def mutate_then_succeed(_message):
            session.character["current_hp"] -= 2
            session.world_state["inventory"].append("Uncommitted")
            return {"narration": "This turn will not be committed."}

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
            self.store.get_campaign(created["campaign_id"]).payload,
            saved_before,
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


if __name__ == "__main__":
    unittest.main()