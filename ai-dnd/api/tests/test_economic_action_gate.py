"""S1a early gate: the economic_action field is in the contract, but until A3/A4 open it a request carrying it is
refused with 409 economic_actions_disabled; no free-text turn runs, nothing moves and no receipt is written."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

from api.tests import test_campaign_api as fixtures


ROOM_PROPOSAL = {"purpose": "room", "recipient_id": "barman", "amount_cp": None}
ECONOMIC_ACTIONS = {
    "prepare": {"kind": "prepare", "proposal": ROOM_PROPOSAL},
    "confirm": {"kind": "confirm", "offer_id": "a" * 32, "confirmation_digest": "b" * 64},
    "cancel": {"kind": "cancel", "offer_id": "a" * 32},
}


class EconomicActionGateTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    def prepare(self, campaign):
        record = self.manager.get(campaign["session_id"])
        world = record.game_session.world_state
        world["npcs"] = [{"id": "barman", "name": "Marek", "role": "Barmen", "location": world["location"],
                          "current_hp": 10}]
        world["currency"] = {"player": 500}
        self.manager.save_campaign(campaign["campaign_id"])
        return record

    async def post(self, campaign, command):
        return await self.http.post(f'/api/game/sessions/{campaign["session_id"]}/turn', json=command)

    def snapshot(self, record):
        session = record.game_session
        world = session.world_state
        return copy.deepcopy((
            world["currency"], world.get("flags"), world["inventory"],
            getattr(session, "messages", None),
            session.serialize_game_state(),
            session.rng.getstate(),
            record.journal, record.narrative_memory,
            record.turn_action_receipts,
            getattr(record, "undo_checkpoint", None),
            self.store.get_campaign(record.campaign_id),
        ))

    async def test_economic_actions_disabled_changes_nothing(self):
        campaign = await self.create_campaign()
        record = self.prepare(campaign)
        before = self.snapshot(record)
        free_turn = AssertionError("The free-text turn must not run for an economic action")
        for kind, economic_action in ECONOMIC_ACTIONS.items():
            with self.subTest(kind=kind):
                command = {"message": "oda tutuyorum", "action_id": str(uuid4()),
                           "economic_action": economic_action}
                with patch("game.run_player_turn", side_effect=free_turn) as run_turn, \
                        patch.object(record.game_session, "run_player_turn", side_effect=free_turn) as bound_turn, \
                        patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
                    refused = await self.post(campaign, command)
                self.assertEqual(refused.status_code, 409, refused.text)
                self.assertEqual(refused.json()["detail"]["code"], "economic_actions_disabled")
                run_turn.assert_not_called()
                bound_turn.assert_not_called()
                self.assertEqual(self.snapshot(record), before)
                self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
                # No intent was claimed (no turn action stored above), so re-sending the same command is refused
                # the same way rather than replayed, and still changes nothing.
                replay = await self.post(campaign, command)
                self.assertEqual(replay.status_code, 409, replay.text)
                self.assertEqual(replay.json()["detail"]["code"], "economic_actions_disabled")
                self.assertEqual(self.snapshot(record), before)

    async def test_client_cannot_send_source_action_id(self):
        campaign = await self.create_campaign()
        record = self.prepare(campaign)
        before = self.snapshot(record)
        command = {"message": "Teklif hazırla", "action_id": str(uuid4()),
                   "economic_action": {"kind": "prepare",
                                       "proposal": {**ROOM_PROPOSAL, "source_action_id": str(uuid4())}}}
        refused = await self.post(campaign, command)
        self.assertEqual(refused.status_code, 422, refused.text)
        self.assertEqual(self.snapshot(record), before)


if __name__ == "__main__":
    unittest.main()
