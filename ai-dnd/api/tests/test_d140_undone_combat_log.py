"""D-140 / ORTA-02: an undone attack is marked undone in the combat log, like its story row.

Undo puts the world back (the foe's hit points come back) but the combat log row of that attack is kept as evidence.
Without a mark the log still shows the blow as applied. The mark is read-time only (decision 31): it comes from the
undo receipt, which names the undone turn's receipt, which carries that turn's own combat event id. Nothing is saved.
"""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from api.tests import test_campaign_api as campaign_fixtures
from api.tests import test_death_system as death_fixtures
from api.tests.town_seed import fixed_town
import campaign_time


class UndoneAttackInCombatLog(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def attack(self, campaign, d20):
        request = {"message": "Düşmana saldırıyorum.", "target_id": "death-save-enemy", "action_id": str(uuid.uuid4())}
        with patch("game.roll_d20", return_value=d20):
            turn = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json=request)
        self.assertEqual(turn.status_code, 200, turn.text)
        entry = turn.json()["combat_history_entry"]
        self.assertIsNotNone(entry, turn.text)
        self.assertEqual(entry["result"]["action"], "attack", turn.text)
        return request["action_id"], entry

    async def test_the_undone_fight_ending_attack_is_marked_undone_and_the_earlier_one_is_not(self):
        with fixed_town(self, 14001):
            created = await self.http.post("/api/game/campaigns", json={})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        session = self.manager.get(campaign["session_id"]).game_session
        campaign_time.initialize(session.world_state)
        death_fixtures.start_test_combat(session)
        enemy = next(npc for npc in session.world_state["npcs"] if npc["id"] == "death-save-enemy")

        _missed_turn, missed = await self.attack(campaign, 2)
        self.assertTrue(session.world_state["combat"]["active"])
        enemy["current_hp"] = 1  # the next blow ends the fight: the case the screen offers to undo
        ending_turn, ending = await self.attack(campaign, 20)
        self.assertTrue(ending["result"]["combat_ended"], ending)

        undo = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/undo",
            json={"action_id": str(uuid.uuid4()), "target_action_id": ending_turn},
        )
        self.assertEqual(undo.status_code, 200, undo.text)
        enemy = next(npc for npc in session.world_state["npcs"] if npc["id"] == "death-save-enemy")
        self.assertEqual(enemy["current_hp"], 1, "the undo gave the foe its hit points back")
        self.assertTrue(session.world_state["combat"]["active"], "the undo put the fight back")

        detail = await self.http.get(f"/api/game/campaigns/{campaign['campaign_id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        log = {entry["event_id"]: entry for entry in detail.json()["combat_history"]}
        self.assertIs(log[ending["event_id"]].get("undone"), True, "the undone blow is marked in the combat log")
        self.assertNotIn("undone", log[missed["event_id"]], "a turn that stands carries no mark")
        self.assertEqual(log[ending["event_id"]]["result"], ending["result"], "the evidence row itself is unchanged")

        resumed = await self.http.post(f"/api/game/campaigns/{campaign['campaign_id']}/resume")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        log = {entry["event_id"]: entry for entry in resumed.json()["combat_history"]}
        self.assertIs(log[ending["event_id"]].get("undone"), True)
        self.assertNotIn("undone", log[missed["event_id"]])

        stored = self.store.get_campaign(campaign["campaign_id"])
        self.assertEqual(len(stored.combat_history), 2)


if __name__ == "__main__":
    unittest.main()
