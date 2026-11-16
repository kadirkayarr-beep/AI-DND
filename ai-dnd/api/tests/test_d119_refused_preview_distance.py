"""D-119: a refused attack preview leaves no opening distance behind, so the last turn can still be undone."""

from __future__ import annotations

import copy
import unittest
import uuid
from unittest import mock

import combat_lifecycle
from api.ollama_adapter import AuthenticatedOllamaAdapter, OllamaUnavailableError
from api.tests import test_campaign_api
from api.tests.test_campaign_api import create_city_with_locked_tavern
from api.tests.town_seed import fixed_town


class RefusedPreviewDistanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await test_campaign_api.CampaignApiTests.asyncSetUp(self)
        with fixed_town(self, 11900):
            _, self.session_id, _, self.turn_url, _, _ = await create_city_with_locked_tavern(self)
        self.undo_url = f"/api/game/sessions/{self.session_id}/undo"
        session = self.manager.get(self.session_id).game_session
        # A person in the scene with no recorded distance, and a bow with no arrows: the preview refuses the shot.
        self.npc = {
            "id": "npc_d119", "name": "Haydut", "role": "bandit",
            "location": session.world_state["location"],
            "personality": "", "appearance": "", "relationship": "hostile",
            "knowledge": [], "memory": [], "combat_status": "active", "current_hp": 12, "status": "active",
        }
        session.ensure_npc_combat_stats(self.npc)
        self.npc.pop("distance_ft", None)
        session.world_state["npcs"].append(self.npc)
        session.world_state["inventory"] = [item for item in session.world_state["inventory"]
                                            if "ok" not in str(item).lower()] + ["Uzun Yay", "Hançer"]
        session.world_state["ammunition"] = {}
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}

    async def asyncTearDown(self):
        await test_campaign_api.CampaignApiTests.asyncTearDown(self)

    def session(self):
        return self.manager.get(self.session_id).game_session

    async def test_validate_request_refusal_leaves_the_person_untouched(self):
        before = copy.deepcopy(self.npc)
        with self.assertRaises(combat_lifecycle.CombatRequestError) as refused:
            combat_lifecycle.validate_request(self.session(), "Haydut'a uzun yayımla saldırıyorum", self.npc["id"])
        self.assertEqual(refused.exception.code, "no_ammunition")
        self.assertNotIn("distance_ft", self.npc)
        self.assertEqual(self.npc, before)

    async def test_a_refused_shot_does_not_make_the_last_turn_stale(self):
        turn_id = str(uuid.uuid4())
        played = await self.http.post(self.turn_url, json={"message": "Etrafa bakıyorum.", "action_id": turn_id})
        self.assertEqual(played.status_code, 200, played.text)
        self.assertNotIn("distance_ft", self.npc)
        refused = await self.http.post(self.turn_url, json={
            "message": "Haydut'a uzun yayımla saldırıyorum", "action_id": str(uuid.uuid4()),
            "target_id": self.npc["id"],
        })
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "no_ammunition")
        self.assertNotIn("distance_ft", self.npc)
        undone = await self.http.post(self.undo_url, json={
            "action_id": str(uuid.uuid4()), "target_action_id": turn_id,
        })
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(undone.json()["undone_action_id"], turn_id)

    async def _played_then_refused_dagger(self, patcher):
        turn_id = str(uuid.uuid4())
        played = await self.http.post(self.turn_url, json={"message": "Etrafa bakıyorum.", "action_id": turn_id})
        self.assertEqual(played.status_code, 200, played.text)
        self.assertNotIn("distance_ft", self.npc)
        with patcher:
            refused = await self.http.post(self.turn_url, json={
                "message": "Haydut'a hançerle saldırıyorum", "action_id": str(uuid.uuid4()),
                "target_id": self.npc["id"],
            })
        npc = next(item for item in self.session().world_state["npcs"] if item["id"] == self.npc["id"])
        return turn_id, refused, npc

    async def test_a_model_refusal_after_a_passed_preview_leaves_no_opening_step(self):
        # D-119 review: the preview passes (a dagger within a step), then the model is down before the turn's snapshot.
        turn_id, refused, npc = await self._played_then_refused_dagger(mock.patch.object(
            AuthenticatedOllamaAdapter, "ensure_required_model", side_effect=OllamaUnavailableError(),
        ))
        self.assertEqual(refused.status_code, 503, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "ollama_unavailable")
        self.assertNotIn("distance_ft", npc)
        undone = await self.http.post(self.undo_url, json={
            "action_id": str(uuid.uuid4()), "target_action_id": turn_id,
        })
        self.assertEqual(undone.status_code, 200, undone.text)

    async def test_a_check_feature_refusal_after_a_passed_preview_leaves_no_opening_step(self):
        # D-190: the preview passes, then the check-feature admission refuses the turn before its snapshot.
        turn_id = str(uuid.uuid4())
        played = await self.http.post(self.turn_url, json={"message": "Etrafa bakıyorum.", "action_id": turn_id})
        self.assertEqual(played.status_code, 200, played.text)
        self.assertNotIn("distance_ft", self.npc)
        refused = await self.http.post(self.turn_url, json={
            "message": "Haydut'a hançerle saldırıyorum", "action_id": str(uuid.uuid4()),
            "target_id": self.npc["id"], "interaction_mode": "do", "check_feature": "primal_knowledge",
        })
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "primal_knowledge_immediate_check_only")
        npc = next(item for item in self.session().world_state["npcs"] if item["id"] == self.npc["id"])
        self.assertNotIn("distance_ft", npc)
        undone = await self.http.post(self.undo_url, json={
            "action_id": str(uuid.uuid4()), "target_action_id": turn_id,
        })
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(undone.json()["undone_action_id"], turn_id)

    async def test_a_turn_rolled_back_after_its_snapshot_leaves_no_opening_step(self):
        # D-119 review: the turn's own snapshot is the state before the opening step, so a rollback removes it too.
        turn_id, refused, npc = await self._played_then_refused_dagger(mock.patch.object(
            self.session(), "run_player_turn", create=True, side_effect=RuntimeError("engine down"),
        ))
        self.assertEqual(refused.status_code, 500, refused.text)
        self.assertEqual(refused.json()["detail"]["code"], "engine_error")
        self.assertNotIn("distance_ft", npc)
        undone = await self.http.post(self.undo_url, json={
            "action_id": str(uuid.uuid4()), "target_action_id": turn_id,
        })
        self.assertEqual(undone.status_code, 200, undone.text)

    async def test_an_unexpected_error_after_a_passed_preview_leaves_no_opening_step(self):
        # D-256: the preview passes, then something unexpected (not a refusal) breaks before the turn's snapshot.
        turn_id = str(uuid.uuid4())
        played = await self.http.post(self.turn_url, json={"message": "Etrafa bakıyorum.", "action_id": turn_id})
        self.assertEqual(played.status_code, 200, played.text)
        with mock.patch.object(
            AuthenticatedOllamaAdapter, "ensure_required_model", side_effect=RuntimeError("unexpected"),
        ):
            try:  # the test client re-raises an unhandled app error; a real server answers 500
                refused = await self.http.post(self.turn_url, json={
                    "message": "Haydut'a hançerle saldırıyorum", "action_id": str(uuid.uuid4()),
                    "target_id": self.npc["id"],
                })
                self.assertGreaterEqual(refused.status_code, 500, refused.text)
            except RuntimeError:
                pass
        npc = next(item for item in self.session().world_state["npcs"] if item["id"] == self.npc["id"])
        self.assertNotIn("distance_ft", npc)


if __name__ == "__main__":
    unittest.main()
