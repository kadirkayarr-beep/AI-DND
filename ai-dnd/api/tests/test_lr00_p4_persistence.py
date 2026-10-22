"""LR00-P4: new LR00 content is applied once, replayed exactly, rolled back on a
failed save, and survives a fresh manager (OH1-09/10).

Covers the owners added in this round (local place, everyday action with a
compound plan, venue window detail). Older owners keep their existing
replay/restart/isolation tests (test_campaign_api, test_http_two_player_isolation,
test_lr00_process_restart).
"""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest.mock import patch

import httpx

import local_places
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient, create_city_with_locked_tavern


class Lr00PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        _, self.session_id, _, self.turn_url, _, _ = await create_city_with_locked_tavern(self)
        self.record = self.manager.get(self.session_id)

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    def world(self):
        return self.manager.get(self.session_id).game_session.world_state

    def places(self):
        return [r for r in self.world()["locations"].values() if isinstance(r, dict) and r.get("place_kind")]

    async def post(self, message, action_id):
        return await self.http.post(self.turn_url, json={"message": message, "action_id": action_id})

    async def test_same_request_replays_exactly_and_creates_the_place_once(self):
        action_id = str(uuid.uuid4())
        first = await self.post("Tapınağa gidiyorum.", action_id)
        self.assertEqual(first.status_code, 200, first.text)
        state = copy.deepcopy(self.world())
        replay = await self.post("Tapınağa gidiyorum.", action_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self.world(), state)
        self.assertEqual(len(self.places()), 1)

    async def test_same_action_id_with_a_different_payload_is_refused(self):
        action_id = str(uuid.uuid4())
        first = await self.post("Tapınağa gidiyorum.", action_id)
        self.assertEqual(first.status_code, 200, first.text)
        conflict = await self.post("Demirciye gidiyorum.", action_id)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual([p["place_kind"] for p in self.places()], ["temple"])

    async def test_failed_save_rolls_back_the_new_place_and_a_retry_creates_it_once(self):
        action_id = str(uuid.uuid4())
        before = copy.deepcopy(self.world())
        original_save = self.store.save_campaign
        calls = 0

        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise CampaignStorageError("synthetic save failure")
            return original_save(*args, **kwargs)

        with patch.object(self.store, "save_campaign", side_effect=fail_once):
            failed = await self.post("Arşive gidiyorum.", action_id)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(self.world(), before)
        retry = await self.post("Arşive gidiyorum.", action_id)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(len(self.places()), 1)
        replay = await self.post("Arşive gidiyorum.", action_id)
        self.assertEqual(replay.json(), retry.json())

    async def test_plan_window_and_place_survive_a_fresh_manager(self):
        campaign_id = self.record.campaign_id
        knock = await self.post(
            "kapıyı çalıyorum, cevap gelmezse pencereden içeri bakıyorum sonra marek'e dönüp soruyorum",
            str(uuid.uuid4()),
        )
        self.assertEqual(knock.status_code, 200, knock.text)
        plan = copy.deepcopy(self.world()["interaction_adventure_v1"]["plan"])
        went = await self.post("Ahıra gidiyorum.", str(uuid.uuid4()))
        self.assertEqual(went.status_code, 200, went.text)
        place = self.places()[0]
        person = local_places.resident_of(self.world(), place["id"])
        reopened_manager = SessionManager(
            campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER)
        )
        app = create_app(
            session_manager=reopened_manager,
            ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://testserver") as http:
            resumed = await http.post(f"/api/game/campaigns/{campaign_id}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        world = reopened_manager.get(resumed.json()["session_id"]).game_session.world_state
        self.assertEqual(world["interaction_adventure_v1"]["plan"], plan)
        self.assertEqual(world["locations"][place["id"]], place)
        self.assertEqual(local_places.resident_of(world, place["id"])["id"], person["id"])

    def test_old_save_without_pilot_fields_reads_cleanly(self):
        world = {"locations": {"fr:city:neverwinter": {"id": "fr:city:neverwinter", "type": "city"},
                               "location_001": {"id": "location_001", "name": "Eski Han",
                                                "parent_location_id": "fr:city:neverwinter"}},
                 "npcs": [{"id": "npc_1", "location": "location_001"}], "features": []}
        self.assertIsNone(local_places.find_local_place(world, "fr:city:neverwinter", "archive"))
        self.assertIsNone(local_places.resident_of(world, "location_001"))
        self.assertEqual(local_places.settlement_of(world, "location_001"), "fr:city:neverwinter")


if __name__ == "__main__":
    unittest.main()
