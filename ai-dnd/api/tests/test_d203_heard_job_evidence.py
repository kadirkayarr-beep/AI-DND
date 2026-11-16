"""D-203 (Kadir kararı 2026-11-15): evidence gathered before a job is accepted is kept, and counts on acceptance.

A heard (DISCOVERED) bounty whose target falls before the player takes the job keeps that step: the save holds it,
a resumed campaign still has it, accepting the job counts it, and the next turn closes and pays the job once.
Undoing that paying turn puts the purse back and leaves the stored step and the accepted job as they were.
"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

import adventure.transitions as adventure_transitions
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaign_fixtures
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_campaign_api import create_city_with_locked_tavern
from api.tests.test_species_action_quest_evidence import _stage_radiant_bounty
from api.tests.town_seed import fixed_town

QUEST_ID = "adv.d105-bounty"


def _bounty(world):
    return next(q for q in world["quests"] if q.get("quest_id") == QUEST_ID)


def _states(quest):
    return {item["objective_id"]: item["graph_state"] for item in quest["objectives"]}


class HeardJobEvidenceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def heard_bounty_whose_target_falls(self):
        campaign, record, session, purse, xp_before = await self.heard_bounty()
        with patch.object(session.rng, "randint", return_value=1):
            struck = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/species-actions",
                                          json={"action": "healing_hands", "action_id": str(uuid.uuid4())})
        self.assertEqual(struck.status_code, 200, struck.text)
        return campaign, record, session, purse, xp_before

    async def heard_bounty(self):
        with fixed_town(self, 11900):
            _city, session_id, _session, _turn_url, _tavern, _door = await create_city_with_locked_tavern(self)
        record = self.manager.get(session_id)
        campaign = {"session_id": session_id, "campaign_id": record.campaign_id}
        session = record.game_session
        _stage_radiant_bounty(session, target_hp=1)
        quest = _bounty(session.world_state)
        heard = adventure_transitions.transition(
            {**quest, "status": "AVAILABLE", "accepted_turn": None}, "DISCOVERED", quest["updated_turn"],
        )
        quest.clear()
        quest.update(heard)  # heard, never accepted; notice and mark were done earlier, only the target is left
        self.assertEqual(_states(quest), {"notice": "COMPLETE", "mark": "COMPLETE", "resolve": "ACTIVE"})
        purse = session.world_state.get("currency", {}).get("player", 0)
        xp_before = session.character.get("xp", 0)
        return campaign, record, session, purse, xp_before

    def resumed_world(self, campaign):
        resumed = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _session_id, record, *_rest = resumed.resume_campaign(campaign["campaign_id"])
        return record.game_session.world_state

    async def turn(self, campaign, action_id):
        return await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn",
                                    json={"message": "Etrafa bakıyorum.", "action_id": action_id})

    async def test_target_felled_before_acceptance_is_kept_saved_and_counted_on_acceptance(self):
        campaign, record, session, purse, xp_before = await self.heard_bounty_whose_target_falls()
        quest = _bounty(session.world_state)
        self.assertEqual((quest["status"], quest["outcome"]), ("DISCOVERED", None), "a heard job never closes itself")
        self.assertEqual(_states(quest)["resolve"], "COMPLETE", "the fallen target is kept on the heard job")
        self.assertIsNone(quest.get("reward_application_id"))
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0), purse, "nothing is paid for a job not taken")
        stored = _bounty(self.resumed_world(campaign))
        self.assertEqual((stored["status"], _states(stored)["resolve"]), ("DISCOVERED", "COMPLETE"),
                         "the kept step survives save and resume")

        accepted = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/quests/{QUEST_ID}/accept")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        quest = _bounty(session.world_state)
        self.assertEqual(quest["status"], "ACTIVE")
        self.assertEqual(set(_states(quest).values()), {"COMPLETE"}, "acceptance counts the kept steps")
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0), purse)

        paying = str(uuid.uuid4())
        closed = await self.turn(campaign, paying)
        self.assertEqual(closed.status_code, 200, closed.text)
        quest = _bounty(session.world_state)
        self.assertEqual((quest["status"], quest["outcome"]), ("COMPLETED", "success"))
        gold = quest["reward_plan"]["success"]["gold"] * 100
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0) - purse, gold)
        self.assertEqual(session.character["xp"] - xp_before, quest["reward_plan"]["success"]["xp"] + 10)
        self.assertEqual(quest["reward_application_id"], f"quest:{QUEST_ID}:success")
        completed = [item for item in closed.json()["quest_outcomes"]
                     if item.get("quest_id") == QUEST_ID and item.get("transition") == "completed"]
        self.assertEqual(len(completed), 1, "the paying turn tells the narrator and the canon that the job is done")

        undone = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": paying})
        self.assertEqual(undone.status_code, 200, undone.text)
        session = self.manager.get(campaign["session_id"]).game_session
        quest = _bounty(session.world_state)
        self.assertEqual((quest["status"], quest.get("reward_application_id")), ("ACTIVE", None))
        self.assertEqual(set(_states(quest).values()), {"COMPLETE"}, "undo keeps the kept steps of the accepted job")
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0), purse, "undo takes the reward back")
        stored = _bounty(self.resumed_world(campaign))
        self.assertEqual((stored["status"], set(_states(stored).values())), ("ACTIVE", {"COMPLETE"}))

        again = await self.turn(campaign, str(uuid.uuid4()))
        self.assertEqual(again.status_code, 200, again.text)
        quest = _bounty(session.world_state)
        self.assertEqual((quest["status"], quest["outcome"]), ("COMPLETED", "success"))
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0) - purse, gold, "paid exactly once")

    async def test_undoing_the_attack_that_felled_the_target_reopens_the_kept_step(self):
        campaign, _record, session, purse, _xp = await self.heard_bounty()
        blow = str(uuid.uuid4())  # an ordinary attack turn (a species action stays outside Undo, D-188)
        with patch("game.roll_d20", return_value=20):
            struck = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json={
                "message": "Haydut'a saldırıyorum.", "target_id": "npc.d105-target", "action_id": blow})
        self.assertEqual(struck.status_code, 200, struck.text)
        quest = _bounty(session.world_state)
        self.assertEqual((quest["status"], _states(quest)["resolve"]), ("DISCOVERED", "COMPLETE"), struck.text)
        undone = await self.http.post(f"/api/game/sessions/{campaign['session_id']}/undo",
                                      json={"action_id": str(uuid.uuid4()), "target_action_id": blow})
        self.assertEqual(undone.status_code, 200, undone.text)
        session = self.manager.get(campaign["session_id"]).game_session
        quest = _bounty(session.world_state)
        self.assertEqual((quest["status"], _states(quest)["resolve"]), ("DISCOVERED", "ACTIVE"),
                         "undo takes the kept step back off the heard job")
        self.assertEqual(session.world_state.get("currency", {}).get("player", 0), purse)
        stored = _bounty(self.resumed_world(campaign))
        self.assertEqual((stored["status"], _states(stored)["resolve"]), ("DISCOVERED", "ACTIVE"),
                         "the save holds the undone step as open")


if __name__ == "__main__":
    unittest.main()
