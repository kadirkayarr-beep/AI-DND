"""API boundaries for Spells V1: no client-authored damage, and failed turns roll back slots."""

from __future__ import annotations

import unittest
import uuid

import httpx

from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_validation import serialize_combat_history_entry
from api.serializers import serialize_combat_result, serialize_session_state
from api.session_manager import SessionManager


class FakeOllamaClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("spell API tests must not call a model")


class SpellApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = SessionManager()
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()

    async def test_client_cannot_submit_spell_damage_or_healing(self):
        created = await self.http.post("/api/sessions")
        session_id = created.json()["session_id"]
        response = await self.http.post(
            f"/api/sessions/{session_id}/turn",
            json={"message": "I cast Fire Bolt", "damage": 99, "healing": 20, "spell_slots_remaining": {"1": 9}},
        )
        self.assertEqual(response.status_code, 422)

    async def test_failed_cast_turn_restores_slots_and_hp(self):
        created = await self.http.post("/api/sessions")
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session
        session.character["spell_slots_remaining"] = {"1": 2}
        session.character["cantrips"] = ["Fire Bolt"]
        session.character["spells"] = ["Magic Missile"]
        before = serialize_session_state(session)

        def broken_cast(_message, **_kwargs):
            session.character["spell_slots_remaining"]["1"] = 0
            session.character["current_hp"] = 1
            raise RuntimeError("cast failed after a partial write")

        session.run_player_turn = broken_cast
        response = await self.http.post(
            f"/api/sessions/{session_id}/turn",
            json={"message": "I cast Magic Missile"},
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "engine_error")
        restored = serialize_session_state(session)
        self.assertEqual(restored["character"]["current_hp"], before["character"]["current_hp"])
        self.assertEqual(
            restored["character"]["spell_slots_remaining"],
            before["character"]["spell_slots_remaining"],
        )

    def test_cast_result_projects_spell_fields_and_hides_private_state(self):
        projected = serialize_combat_result(
            {
                "action": "cast",
                "spell": "Fire Bolt",
                "casting_ability": "intelligence",
                "attack_or_save": "spell_attack",
                "damage": 4,
                "healing": None,
                "slot_spent": False,
                "save_roll": None,
                "save_dc": None,
                "secret_prompt": "must not be returned",
            }
        )
        self.assertEqual(projected["spell"], "Fire Bolt")
        self.assertEqual(projected["slot_spent"], False)
        self.assertNotIn("secret_prompt", projected)
        self.assertIsNone(serialize_combat_result({"action": "dialogue", "damage": 9}))

    def test_cast_result_can_be_stored_in_combat_history(self):
        stored = serialize_combat_history_entry(
            {
                "event_id": str(uuid.uuid4()),
                "turn_index": 1,
                "result": {
                    "action": "cast",
                    "spell": "Cure Wounds",
                    "outcome": "healed",
                    "healing": 6,
                    "slot_spent": True,
                },
            }
        )
        self.assertEqual(stored["result"]["action"], "cast")
        self.assertEqual(stored["result"]["healing"], 6)
        self.assertTrue(stored["result"]["slot_spent"])
