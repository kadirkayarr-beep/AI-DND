"""D-189: the live lore copy (session.campaign_lore_state) is never older than the record's lore when a command reads it.

A committed play turn moves only the record's lore, and a resume reloads it; a copy left from an earlier Undo,
rolled-back turn or hear() is then older. A play turn staged from that copy, or a quest command that writes the copy
back over the record, would drop lore that is already saved.
"""

from __future__ import annotations

import unittest
import uuid

from api.lore_authority.campaign_state import EngineActionEvidence, apply_faction_standing
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as campaign_fixtures
from api.tests.auth_fixture import TEST_PLAYER
from api.tests.test_phase7_package import bound_state
from api.tests.test_species_action_quest_evidence import _stage_radiant_bounty, _standings
from api.tests.town_seed import fixed_town


class StaleLoreCopyTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign_fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = campaign_fixtures.CampaignApiTests.asyncTearDown

    async def campaign_with_stale_copy(self):
        with fixed_town(self, 18901):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        record = self.manager.get(campaign["session_id"])
        session = record.game_session
        stale = bound_state()
        # The record already holds a later, saved turn's standing; the live copy is still the older lore.
        record.lore_authority = apply_faction_standing(
            stale, faction_id="faction:guild", standing=2, known_to_player=True, local_presence=True,
            evidence=EngineActionEvidence("turn:9", 9, "python_engine"), source_action_id="turn:9", turn_index=9,
        )
        session.campaign_lore_state = stale
        return campaign, record, session

    def resumed_lore(self, campaign):
        resumed = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _session_id, record, *_rest = resumed.resume_campaign(campaign["campaign_id"])
        return record.lore_authority

    async def test_a_play_turn_does_not_stage_from_a_stale_lore_copy(self):
        campaign, record, session = await self.campaign_with_stale_copy()
        # A model-free engine turn: the lore staging under test is the API's, not the engine's.
        session.run_player_turn = lambda message: {
            "action_result": {"action": "wait", "status": "resolved"},
            "narration": f"Handled: {message}",
        }
        response = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json={"message": "Bekle", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(_standings(record.lore_authority, "faction:guild"), [(2, "turn:9")])
        self.assertEqual(_standings(self.resumed_lore(campaign), "faction:guild"), [(2, "turn:9")])
        # The copy left behind is the record's lore, so the next command cannot read an older one.
        self.assertIs(session.campaign_lore_state, record.lore_authority)

    async def test_a_quest_command_after_a_lore_turn_keeps_that_turns_lore(self):
        # The real chain: a committed turn writes its quest evidence onto the record's lore only, so the copy the turn
        # started from is older afterwards; the next quest command must not save that older copy over it.
        with fixed_town(self, 18902):
            created = await self.http.post("/api/game/campaigns", json={"death_mode": "NORMAL"})
        self.assertEqual(created.status_code, 200, created.text)
        campaign = created.json()
        record = self.manager.get(campaign["session_id"])
        session = record.game_session
        record.lore_authority = bound_state()
        _stage_radiant_bounty(session, target_hp=30)

        def lore_turn(message):
            turn = session.world_state.setdefault("flags", {}).get("turn_index", 0) + 1
            session.world_state["flags"]["turn_index"] = turn
            outcome = {"event_id": "event:d189", "quest_id": "q.d189", "transition": "objective_progress",
                       "objective_id": None, "source_event_id": "event:d189", "turn_index": turn}
            return {
                "action_result": {"action": "wait", "status": "resolved", "quest_outcomes": [outcome]},
                "narration": f"Handled: {message}",
                "_engine_event_evidence": {"authority": "python_engine", "action_id": f"turn:{turn}",
                                           "turn_index": turn, "quest_outcomes": [outcome],
                                           "procedural_entity_ids": []},
            }

        session.run_player_turn = lore_turn
        response = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/turn",
            json={"message": "Bekle", "action_id": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 200, response.text)
        turn_overrides = [o.override_id for o in record.lore_authority.campaign_overrides]
        self.assertEqual(len(turn_overrides), 1, "the turn's quest evidence is on the record's lore")
        cancelled = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/quests/adv.d105-bounty/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual([o.override_id for o in record.lore_authority.campaign_overrides], turn_overrides)
        self.assertEqual([o.override_id for o in self.resumed_lore(campaign).campaign_overrides], turn_overrides)

    async def test_a_quest_command_does_not_write_a_stale_lore_copy_over_the_record(self):
        campaign, record, session = await self.campaign_with_stale_copy()
        _stage_radiant_bounty(session, target_hp=30)
        cancelled = await self.http.post(
            f"/api/game/sessions/{campaign['session_id']}/quests/adv.d105-bounty/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(_standings(record.lore_authority, "faction:guild"), [(2, "turn:9")])
        self.assertEqual(_standings(self.resumed_lore(campaign), "faction:guild"), [(2, "turn:9")])
        self.assertIs(session.campaign_lore_state, record.lore_authority)


if __name__ == "__main__":
    unittest.main()
