"""LR00-P7: one explicit undo of the last completed turn (OH1-13, first slice).

Restores world, character, RNG, journal and the model's narrative memory to
the pre-turn capture; keeps the undone turn as history evidence; refuses a
second undo, a stale undo and an undo after restart (no trusted pre-turn state).
Not covered yet: reusing the recorded dice for an equivalent re-attempt is the
contract's proposed default and still needs the owner's policy decision; the
restored RNG already makes an identical deterministic re-attempt roll the same.
"""

from __future__ import annotations

import copy
import unittest
import uuid

import httpx

from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import FakeOllamaClient, create_city_with_locked_tavern


class UndoLastTurnTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        _, self.session_id, _, self.turn_url, _, _ = await create_city_with_locked_tavern(self)
        self.undo_url = f"/api/game/sessions/{self.session_id}/undo"

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    def record(self):
        return self.manager.get(self.session_id)

    def session(self):
        return self.record().game_session

    async def turn(self, message):
        action_id = str(uuid.uuid4())
        response = await self.http.post(self.turn_url, json={"message": message, "action_id": action_id})
        self.assertEqual(response.status_code, 200, response.text)
        return action_id, response.json()

    async def undo(self, target, action_id=None):
        return await self.http.post(self.undo_url, json={
            "action_id": action_id or str(uuid.uuid4()), "target_action_id": target,
        })

    async def test_undo_restores_the_pre_turn_world_and_keeps_the_turn_as_evidence(self):
        before = copy.deepcopy(self.session().serialize_game_state())
        rng_before = self.session().rng.getstate()
        memory_before = copy.deepcopy(self.record().narrative_memory)
        history_before = len(self.store.get_campaign(self.record().campaign_id).history)
        turn_id, played = await self.turn("Tapınağa gidiyorum.")
        self.assertTrue(played["turn_outcome"]["place_created"])
        undone = await self.undo(turn_id)
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(undone.json()["undone_action_id"], turn_id)
        self.assertEqual(self.session().serialize_game_state(), before)
        self.assertEqual(self.session().rng.getstate(), rng_before)
        self.assertEqual(self.record().narrative_memory, memory_before)
        history = self.store.get_campaign(self.record().campaign_id).history
        # The undone turn stays as evidence, followed by the undo marker.
        self.assertEqual(len(history), history_before + 2)
        self.assertEqual(history[-1]["player_message"], "↶ Son turu geri al")
        saved = self.store.get_campaign(self.record().campaign_id)
        self.assertNotIn("place_kind", str(saved.payload))

    async def test_only_one_step_and_only_the_named_last_turn(self):
        first_id, _ = await self.turn("Tapınağa gidiyorum.")
        second_id, _ = await self.turn("Buradan çıkıp sokağa dönüyorum.")
        wrong = await self.undo(first_id)
        self.assertEqual(wrong.status_code, 409, wrong.text)
        self.assertEqual(wrong.json()["detail"]["code"], "undo_unavailable")
        ok = await self.undo(second_id)
        self.assertEqual(ok.status_code, 200, ok.text)
        again = await self.undo(second_id)
        self.assertEqual(again.status_code, 409, again.text)

    async def test_undo_replays_and_the_abandoned_turn_never_reapplies(self):
        turn_id, played = await self.turn("Tapınağa gidiyorum.")
        undo_id = str(uuid.uuid4())
        first = await self.undo(turn_id, undo_id)
        self.assertEqual(first.status_code, 200, first.text)
        state = copy.deepcopy(self.session().serialize_game_state())
        replay = await self.undo(turn_id, undo_id)
        self.assertEqual(replay.json(), first.json())
        old = await self.http.post(self.turn_url, json={"message": "Tapınağa gidiyorum.", "action_id": turn_id})
        self.assertEqual(old.status_code, 200, old.text)
        self.assertEqual(old.json()["narration"], played["narration"])
        self.assertEqual(self.session().serialize_game_state(), state)

    async def test_a_change_after_the_turn_makes_undo_stale(self):
        turn_id, _ = await self.turn("Tapınağa gidiyorum.")
        self.session().world_state.setdefault("flags", {})["unrelated_change"] = True
        stale = await self.undo(turn_id)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"]["code"], "undo_stale")

    async def test_no_undo_after_restart(self):
        turn_id, _ = await self.turn("Tapınağa gidiyorum.")
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        app = create_app(session_manager=manager,
                         ollama_adapter=AuthenticatedOllamaAdapter(FakeOllamaClient()),
                         authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            resumed = await http.post(f"/api/game/campaigns/{self.record().campaign_id}/resume")
            session_id = resumed.json()["session_id"]
            refused = await http.post(f"/api/game/sessions/{session_id}/undo", json={
                "action_id": str(uuid.uuid4()), "target_action_id": turn_id,
            })
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "undo_unavailable")


if __name__ == "__main__":
    unittest.main()
