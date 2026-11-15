"""D-145: a rest taken from the species panel that ends in death keeps the death, like the same rest taken in words.

A Long Rest crossing midnight with too few supplies can raise exhaustion to 6 and kill the character. The state
projection did not know an exhaustion death's cause and the engine's death branch answered with a shape the panel's
response contract refuses, so the panel route rolled the death, the elapsed time and the eaten rations back with a
409; a rest said in words was rolled back too (500 journal_error).
"""
from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx

import timed_gameplay
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_time import scene
from api.tests.test_model_failure_never_locks import ScriptedModel
from api.tests.town_seed import fixed_town


def _stage_fatal_night(session):
    """One hour before midnight, one day of food and no water, exhaustion 5: midnight's supply check is fatal."""
    session.ensure_campaign_clock()
    world = session.world_state
    world["campaign_time"]["start_second"] = 0
    world["campaign_time"]["elapsed_seconds"] = 23 * 3600
    world["supplies_policy"] = {"enabled": True}
    world["inventory"] = ["Rations (1 day)"]
    session.character["exhaustion"] = 5


class SpeciesPanelRestDeath(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = CampaignStore(Path(self.temporary_directory.name) / "campaigns.sqlite3",
                                   bound_principal=TEST_PLAYER)
        self.manager = SessionManager(session_factory=scene, campaign_store=self.store)  # a registered scene starts the clock
        adapter = AuthenticatedOllamaAdapter(ScriptedModel())
        self.enterContext(adapter.engine_binding())
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver")

    async def asyncTearDown(self):
        await self.http.aclose()

    async def campaign(self):
        with fixed_town(self, 14501):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        self.campaign_record = created.json()
        session_id = self.campaign_record["session_id"]
        return session_id, self.manager.get(session_id).game_session

    async def test_panel_long_rest_that_kills_commits_the_death(self):
        session_id, session = await self.campaign()
        _stage_fatal_night(session)
        with patch.object(session.rng, "randint", return_value=20):
            response = await self.http.post(f"/api/game/sessions/{session_id}/species-actions",
                                            json={"action": "long_rest", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertEqual(result["action"], "long_rest")
        self.assertFalse(result["effects"]["rest_completed"])
        time_result = result["effects"]["time_result"]
        self.assertTrue(time_result["condition_death"])
        self.assertEqual(time_result["elapsed_seconds"], 3600)  # the rest stops at midnight, not eight hours later
        # The death, the hour and the eaten ration stay; nothing was rolled back.
        live = self.manager.get(session_id).game_session
        self.assertEqual(live.character["exhaustion"], 6)
        self.assertEqual(live.character["current_hp"], 0)
        self.assertTrue(live.world_state["death_state"]["dead"])
        self.assertEqual(live.world_state["campaign_time"]["elapsed_seconds"], 24 * 3600)
        self.assertNotIn("Rations (1 day)", live.world_state["inventory"])
        self.assertNotIn("last_long_rest_completed_at", live.world_state)  # an unfinished rest is not a Long Rest
        stored = self.store.get_campaign(self.campaign_record["campaign_id"])
        self.assertEqual(stored.history[-1]["narration"], result["message"])

    async def test_words_and_panel_read_one_result_contract(self):
        _session_id, session = await self.campaign()
        _stage_fatal_night(session)
        with patch.object(session.rng, "randint", return_value=20):
            rest = session.resolve_species_trait_action("long_rest")
        self.assertEqual(set(rest), {"action", "message", "effects"})
        self.assertFalse(rest["effects"]["rest_completed"])
        self.assertTrue(rest["effects"]["time_result"]["condition_death"])

    async def test_rest_said_in_words_still_ends_in_the_same_death(self):
        _session_id, session = await self.campaign()
        _stage_fatal_night(session)
        with patch.object(session.rng, "randint", return_value=20):
            said = timed_gameplay._take_rest(session, "long_rest", 8 * 3600)
        self.assertEqual(said["time_result"]["elapsed_seconds"], 3600)
        self.assertTrue(said["time_result"]["condition_death"])
        self.assertTrue(session.world_state["death_state"]["dead"])

    async def test_rest_said_in_a_turn_commits_the_death(self):
        # The state projection refused an exhaustion death's cause, so the play turn rolled it back as well.
        session_id, session = await self.campaign()
        _stage_fatal_night(session)
        with patch.object(session.rng, "randint", return_value=20):
            response = await self.http.post(f"/api/game/sessions/{session_id}/turn",
                                            json={"message": "8 saat uyuyorum.", "action_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        death = response.json()["state"]["death_state"]
        self.assertEqual(death["status"], "dead")
        self.assertEqual(death["last_resolution"]["cause"], "dehydration")
        live = self.manager.get(session_id).game_session
        self.assertTrue(live.world_state["death_state"]["dead"])
        self.assertEqual(live.world_state["campaign_time"]["elapsed_seconds"], 24 * 3600)


if __name__ == "__main__":
    unittest.main()
