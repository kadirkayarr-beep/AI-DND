"""D-112 / YÜK-09: an Ironman death is final, so the one-step undo must not bring the hero back.

The fatal death-save turn sets the usual undo point like every other completed turn. The undo route and the action
status hint must both see the live terminal death and refuse, and the death must stay in the game and in the save.
"""

from __future__ import annotations

import random
import unittest
import uuid
from unittest.mock import patch

from api.tests import test_campaign_api as campaign_fixtures
from api.tests import test_death_system as death_fixtures
from api.tests.town_seed import fixed_town
import campaign_time


class IronmanFinalDeathUndo(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def die(self, mode):
        """Play the third failed death save through the real turn route; return the campaign and that turn's id."""
        with fixed_town(self, 11201):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": mode})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        s = self.manager.get(campaign["session_id"]).game_session
        campaign_time.initialize(s.world_state)
        death_fixtures.start_test_combat(s)
        s._apply_player_damage(s.character["current_hp"], took_damage=True)
        s.ensure_death_state()["failures"] = 2
        self.app.state.ollama_adapter = None
        request = {"message": "Ölüm kurtarmasını bekliyorum.", "action_id": str(uuid.uuid4())}
        rng = random.Random(1)
        with patch("game.roll_d20", side_effect=lambda: rng.randint(2, 9)), patch(
            "game._resolve_enemy_turns_until_player",
            side_effect=AssertionError("Fatal save must stop the enemy scheduler"),
        ):
            turn = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json=request)
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertEqual(turn.json()["combat_result"]["outcome"], "dead")
        return campaign, s, request["action_id"]

    async def test_ironman_final_death_cannot_be_undone(self):
        campaign, s, death_turn = await self.die("IRONMAN")
        self.assertTrue(s.ensure_death_state()["terminal"])
        status = await self.http.get(f"/api/game/sessions/{campaign['session_id']}/actions/{death_turn}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertIs(status.json().get("undo_available"), False, "a final death offers no undo")

        undo = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/undo",
            json={"action_id": str(uuid.uuid4()), "target_action_id": death_turn},
        )
        self.assertEqual(undo.status_code, 409, undo.text)
        self.assertEqual(undo.json()["detail"]["code"], "undo_final_death", undo.text)

        death = s.ensure_death_state()
        self.assertTrue(death["dead"])
        self.assertTrue(death["terminal"])
        self.assertEqual(s.character["current_hp"], 0)
        self.assertEqual(s.world_state["player_combat_status"], "dead")
        stored = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertTrue(stored["death_state"]["terminal"], "the saved campaign keeps the final death")

    async def test_permadeath_death_cannot_be_undone(self):
        # D-178 (Kadir): "PERMADEATH'te ölüm kesin; ölüm turu Geri Al ile geri alınamaz."
        campaign, s, death_turn = await self.die("PERMADEATH")
        death = s.ensure_death_state()
        self.assertTrue(death["dead"])
        status = await self.http.get(f"/api/game/sessions/{campaign['session_id']}/actions/{death_turn}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertIs(status.json().get("undo_available"), False, "a real death offers no undo")

        undo = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/undo",
            json={"action_id": str(uuid.uuid4()), "target_action_id": death_turn},
        )
        self.assertEqual(undo.status_code, 409, undo.text)
        self.assertEqual(undo.json()["detail"]["code"], "undo_final_death", undo.text)
        self.assertNotIn("Ironman", undo.json()["detail"]["message"], "the refusal names the campaign's own mode")

        death = s.ensure_death_state()
        self.assertTrue(death["dead"])
        self.assertEqual(s.character["current_hp"], 0)
        self.assertEqual(s.world_state["player_combat_status"], "dead")
        stored = self.store.get_campaign(campaign["campaign_id"]).payload["engine_save"]["world_state"]
        self.assertTrue(stored["death_state"]["dead"], "the saved campaign keeps the death")


if __name__ == "__main__":
    unittest.main()
