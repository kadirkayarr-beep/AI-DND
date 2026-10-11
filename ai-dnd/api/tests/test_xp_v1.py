"""The client cannot submit experience, level, or hit points."""

from __future__ import annotations

import unittest

import httpx

from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.session_manager import SessionManager


class FakeOllamaClient:
    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        raise AssertionError("XP API tests must not call a model")


class ExperienceApiTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_client_cannot_send_xp_level_or_hit_points(self):
        created = await self.http.post("/api/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["session_id"]
        for field, value in (("xp", 300), ("level", 4), ("current_hp", 99)):
            with self.subTest(field=field):
                response = await self.http.post(
                    f"/api/sessions/{session_id}/turn",
                    json={"message": "Bekle", field: value},
                )
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(str(value), response.text)

    async def test_turn_exposes_only_a_server_level_up(self):
        created = await self.http.post("/api/sessions")
        session_id = created.json()["session_id"]
        session = self.manager.get(session_id).game_session

        def no_award(message):
            return {
                "action_result": {"action": "attack", "status": "resolved"},
                "narration": "The blade misses.",
            }

        session.run_player_turn = no_award
        missed = await self.http.post(
            f"/api/sessions/{session_id}/turn",
            json={"message": "Saldır"},
        )
        self.assertEqual(missed.status_code, 200, missed.text)
        self.assertIsNone(missed.json()["level_up"])

        def awarded(message):
            session.character["xp"] = 300
            session.character["level"] = 2
            return {
                "action_result": {
                    "action": "attack",
                    "status": "resolved",
                    "level_up": {
                        "previous_level": 1,
                        "new_level": 2,
                        "xp_gained": 300,
                        "hit_points_gained": 8,
                    },
                },
                "narration": "The fight is over.",
            }

        session.run_player_turn = awarded
        gained = await self.http.post(
            f"/api/sessions/{session_id}/turn",
            json={"message": "Saldır"},
        )
        self.assertEqual(gained.status_code, 200, gained.text)
        self.assertEqual(
            gained.json()["level_up"],
            {
                "previous_level": 1,
                "new_level": 2,
                "xp_gained": 300,
                "hit_points_gained": 8,
            },
        )
        self.assertEqual(gained.json()["state"]["character"]["xp"], 300)


if __name__ == "__main__":
    unittest.main()
