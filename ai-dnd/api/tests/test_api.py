"""Deterministic HTTP contracts for the FastAPI adapter.

These tests replace the remote model client and are not live-model validation.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.serializers import serialize_session_state
from api.session_manager import SessionManager


class FakeOllamaClient:
    def __init__(self, models=("qwen3:8b",), list_error=None, chat_error=None):
        self.models = list(models)
        self.list_error = list_error
        self.chat_error = chat_error
        self.list_calls = 0

    def list(self):
        self.list_calls += 1
        if self.list_error:
            raise RuntimeError(self.list_error)
        return {"models": [{"model": name} for name in self.models]}

    def chat(self, *args, **kwargs):
        if self.chat_error:
            raise RuntimeError(self.chat_error)
        raise AssertionError("API unit tests must not call a real model.")


class ApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = SessionManager()
        self.fake_client = FakeOllamaClient()
        self.adapter = AuthenticatedOllamaAdapter(self.fake_client)
        self.app = create_app(
            session_manager=self.manager,
            ollama_adapter=self.adapter,
        )
        self.http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.http.aclose()

    async def create_session(self):
        response = await self.http.post("/api/sessions")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_health_endpoint(self):
        response = await self.http.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "engine": "AI-DND", "model": "qwen3:8b"},
        )

    async def test_browser_proxy_routes_reach_the_same_python_api(self):
        health = await self.http.get("/api/game/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["engine"], "AI-DND")

        created = await self.http.post("/api/game/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session
        session.run_player_turn = lambda message: {
            "action_result": {"action": "wait", "status": "resolved"},
            "narration": f"Handled: {message}",
        }

        state = await self.http.get(
            f"/api/game/sessions/{session_id}/state"
        )
        self.assertEqual(state.status_code, 200)
        turn = await self.http.post(
            f"/api/game/sessions/{session_id}/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertEqual(turn.json()["narration"], "Handled: Bekle")
        self.assertEqual(turn.json()["state"], state.json())

    async def test_species_action_returns_authoritative_result_and_state(self):
        created = await self.create_session()
        session_id = created["session_id"]
        session = self.manager.get(session_id).game_session
        session.character.update(
            {
                "species": "Aasimar",
                "race": "Aasimar",
                "level": 3,
                "proficiency_bonus": 2,
                "current_hp": 1,
                "max_hp": 20,
                "charisma_mod": 1,
            }
        )
        session.initialize_species_trait_state()

        with patch.object(session.rng, "randint", return_value=1):
            response = await self.http.post(
                f"/api/game/sessions/{session_id}/species-actions",
                json={"action": "healing_hands"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["result"]["action"], "healing_hands")
        self.assertEqual(payload["result"]["effects"]["current_hp"], 3)
        self.assertEqual(payload["state"]["character"]["current_hp"], 3)
        self.assertEqual(
            payload["state"]["character"]["species_trait_state"][
                "healing_hands_uses_remaining"
            ],
            0,
        )

    async def test_new_sessions_have_unique_opaque_uuid4_ids(self):
        first = await self.create_session()
        second = await self.create_session()
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(len(first["session_id"]), 36)
        self.assertEqual(len(second["session_id"]), 36)
        self.assertEqual(__import__("uuid").UUID(first["session_id"]).version, 4)
        self.assertEqual(__import__("uuid").UUID(second["session_id"]).version, 4)

    async def test_session_state_is_isolated(self):
        first = await self.create_session()
        second = await self.create_session()
        first_session = self.manager.get(first["session_id"]).game_session
        first_session.character["current_hp"] = 2
        first_session.world_state["inventory"].append("Only in first session")
        first_session.world_state["location"] = "forest"

        first_state = (await self.http.get(
            f"/api/sessions/{first['session_id']}/state"
        )).json()
        second_state = (await self.http.get(
            f"/api/sessions/{second['session_id']}/state"
        )).json()
        self.assertEqual(first_state["character"]["current_hp"], 2)
        self.assertEqual(first_state["location"], "forest")
        self.assertIn("Only in first session", first_state["inventory"])
        self.assertNotIn("Only in first session", second_state["inventory"])
        self.assertNotEqual(
            first_state["character"]["current_hp"],
            second_state["character"]["current_hp"],
        )

    async def test_state_endpoint_is_a_canonical_public_projection(self):
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        response = await self.http.get(
            f"/api/sessions/{created['session_id']}/state"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), serialize_session_state(session))
        self.assertNotIn("world_state", response.json())
        self.assertNotIn("messages", response.json())
        self.assertNotIn("recent_dm_narrations", response.json())

    async def test_blank_player_message_is_rejected(self):
        created = await self.create_session()
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": " \t  "},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("input", response.text)

    async def test_turn_delegates_to_existing_game_session_pipeline(self):
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        received = []

        def existing_pipeline(message):
            received.append(message)
            session.world_state["location"] = "forest"
            return {
                "action_result": {"action": "explore", "status": "resolved"},
                "narration": "Python tarafından doğrulanan anlatı.",
            }

        session.run_player_turn = existing_pipeline
        player_message = "  Ormana bakıyorum  "
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": player_message},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(received, [player_message])
        self.assertEqual(response.json()["narration"], "Python tarafından doğrulanan anlatı.")
        self.assertEqual(response.json()["state"]["location"], "forest")
        self.assertEqual(self.fake_client.list_calls, 1)

    async def test_client_cannot_submit_authoritative_state(self):
        created = await self.create_session()
        session_id = created["session_id"]
        session = self.manager.get(session_id).game_session
        before = serialize_session_state(session)
        forbidden_values = {
            "hp": 0,
            "inventory": ["forged item"],
            "location": "forest",
            "combat": {"active": True, "round": 999},
        }
        for field, value in forbidden_values.items():
            with self.subTest(field=field):
                response = await self.http.post(
                    f"/api/sessions/{session_id}/turn",
                    json={"message": "Bekle", field: value},
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(serialize_session_state(session), before)

    async def test_unknown_session_returns_404(self):
        state_response = await self.http.get(
            "/api/sessions/not-a-real-session/state"
        )
        turn_response = await self.http.post(
            "/api/sessions/not-a-real-session/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(state_response.status_code, 404)
        self.assertEqual(turn_response.status_code, 404)
        self.assertEqual(self.fake_client.list_calls, 0)

    async def test_missing_required_model_returns_safe_503(self):
        self.fake_client.models = []
        created = await self.create_session()
        before = serialize_session_state(
            self.manager.get(created["session_id"]).game_session
        )
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "model_unavailable")
        self.assertEqual(
            serialize_session_state(
                self.manager.get(created["session_id"]).game_session
            ),
            before,
        )

    async def test_ollama_preflight_failure_returns_safe_503(self):
        self.fake_client.list_error = "private-token-sentinel"
        created = await self.create_session()
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "ollama_unavailable")
        self.assertNotIn("private-token-sentinel", response.text)

    async def test_engine_exception_becomes_safe_error_and_rolls_back(self):
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        before = serialize_session_state(session)

        def broken_engine(_message):
            session.character["current_hp"] = 0
            session.world_state["inventory"].clear()
            raise RuntimeError("private-engine-detail")

        session.run_player_turn = broken_engine
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "engine_error")
        self.assertNotIn("private-engine-detail", response.text)
        self.assertEqual(serialize_session_state(session), before)

    async def test_model_call_error_returns_safe_503_and_rolls_back(self):
        self.fake_client.chat_error = "private-token-sentinel"
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        before = serialize_session_state(session)

        def engine_that_uses_the_bound_client(_message):
            try:
                game.ollama.chat(model="qwen3:8b")
            except RuntimeError:
                pass
            return {"action_result": {}, "narration": "Fallback text"}

        session.run_player_turn = engine_that_uses_the_bound_client
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "ollama_unavailable")
        self.assertNotIn("private-token-sentinel", response.text)
        self.assertEqual(serialize_session_state(session), before)

    async def test_turn_is_rolled_back_if_model_call_limit_is_exceeded(self):
        self.fake_client.chat = lambda *args, **kwargs: {"ok": True}
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        before = serialize_session_state(session)

        def excessive_model_turn(_message):
            for _ in range(3):
                game.ollama.chat(model="qwen3:8b")
            session.character["current_hp"] = 0
            return {"action_result": {}, "narration": "Too many calls"}

        session.run_player_turn = excessive_model_turn
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "engine_error")
        self.assertEqual(serialize_session_state(session), before)

    async def test_secret_values_are_redacted_from_responses(self):
        host = "https://host-secret-sentinel.invalid"
        token = "token-secret-sentinel"
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        session.run_player_turn = lambda _message: {
            "action_result": {},
            "narration": f"Do not return {token} or {host}.",
        }

        with patch.dict(
            os.environ,
            {"OLLAMA_HOST": host, "OLLAMA_PROXY_TOKEN": token},
        ):
            response = await self.http.post(
                f"/api/sessions/{created['session_id']}/turn",
                json={"message": "Bekle"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(token, response.text)
        self.assertNotIn(host, response.text)
        self.assertIn("[redacted]", response.json()["narration"])

    async def test_validation_error_does_not_echo_extra_secret(self):
        created = await self.create_session()
        sentinel = "token-submitted-as-extra-field"
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Bekle", "OLLAMA_PROXY_TOKEN": sentinel},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(sentinel, response.text)

    async def test_real_engine_evidence_with_telemetry_succeeds_without_500(self):
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        session.world_state["flags"]["turn_index"] = 0

        def engine_with_telemetry(message):
            session.world_state["flags"]["turn_index"] = 1
            session.world_state["location"] = "tavern"
            return {
                "action_result": {"action": "explore", "status": "observed"},
                "narration": "Taverna hareketli ve kalabalık.",
                "_engine_event_evidence": {
                    "authority": "python_engine",
                    "action_id": "turn:1",
                    "turn_index": 1,
                    "quest_outcomes": [],
                    "procedural_entity_ids": [],
                    "telemetry": {
                        "intent_model_calls": 0,
                        "narration_model_calls": 1,
                        "total_model_calls": 1,
                        "intent_source": "deterministic",
                        "narration_source": "qwen",
                        "fallback_reason": None,
                        "narration_validation_result": "accepted",
                        "resolved_action_type": "explore",
                    },
                },
            }

        session.run_player_turn = engine_with_telemetry
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Etrafıma bakıyorum"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["narration"], "Taverna hareketli ve kalabalık.")
        self.assertEqual(response.json()["state"]["location"], "tavern")
        self.assertNotIn("_engine_event_evidence", response.json())

    async def test_model_call_limit_enforced_by_captured_calls_ignoring_telemetry_claim(self):
        self.fake_client.chat = lambda *args, **kwargs: {"ok": True}
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        session.world_state["flags"]["turn_index"] = 0
        before = serialize_session_state(session)

        def forged_telemetry_turn(_message):
            for _ in range(3):
                game.ollama.chat(model="qwen3:8b")
            session.world_state["flags"]["turn_index"] = 1
            return {
                "action_result": {"action": "explore", "status": "observed"},
                "narration": "Narration text",
                "_engine_event_evidence": {
                    "authority": "python_engine",
                    "action_id": "turn:1",
                    "turn_index": 1,
                    "quest_outcomes": [],
                    "procedural_entity_ids": [],
                    "telemetry": {
                        "intent_model_calls": 0,
                        "narration_model_calls": 1,
                        "total_model_calls": 1,
                    },
                },
            }

        session.run_player_turn = forged_telemetry_turn
        response = await self.http.post(
            f"/api/sessions/{created['session_id']}/turn",
            json={"message": "Bekle"},
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "engine_error")
        self.assertEqual(serialize_session_state(session), before)

    async def test_turns_in_one_session_are_serialized(self):
        created = await self.create_session()
        session = self.manager.get(created["session_id"]).game_session
        counter_lock = threading.Lock()
        active = 0
        maximum_active = 0

        def slow_turn(message):
            nonlocal active, maximum_active
            with counter_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.06)
            with counter_lock:
                active -= 1
            return {"action_result": {}, "narration": f"Handled: {message}"}

        session.run_player_turn = slow_turn
        path = f"/api/sessions/{created['session_id']}/turn"
        responses = await asyncio.gather(
            self.http.post(path, json={"message": "Birinci"}),
            self.http.post(path, json={"message": "İkinci"}),
        )
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(maximum_active, 1)

    async def test_different_sessions_can_process_turns_independently(self):
        first = await self.create_session()
        second = await self.create_session()
        sessions = [
            self.manager.get(first["session_id"]).game_session,
            self.manager.get(second["session_id"]).game_session,
        ]
        barrier = threading.Barrier(2)
        errors = []

        def rendezvous_turn(message):
            try:
                barrier.wait(timeout=3)
            except threading.BrokenBarrierError:
                errors.append("sessions did not overlap")
            return {"action_result": {}, "narration": message}

        for session in sessions:
            session.run_player_turn = rendezvous_turn
        responses = await asyncio.gather(
            self.http.post(
                f"/api/sessions/{first['session_id']}/turn",
                json={"message": "A"},
            ),
            self.http.post(
                f"/api/sessions/{second['session_id']}/turn",
                json={"message": "B"},
            ),
        )
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()