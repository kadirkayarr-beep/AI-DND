"""HTTP/SQLite contract acceptance, using trusted fixtures, not live NPC producers."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import equipment_economy
from api.tests import test_campaign_api as fixtures


class EquipmentHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    def prepare(self, campaign):
        record = self.manager.get(campaign["session_id"])
        session = record.game_session
        world = session.world_state
        world["npcs"] = [{
            "id": "vendor", "name": "Mira", "location": world["location"],
            "current_hp": 10, "inventory": ["Hançer"],
        }]
        equipment_economy.materialize(world)
        item = world["npcs"][0]["inventory"][0]
        world["npcs"][0]["item_consents"] = {
            item["item_id"]: {"operation": "receive", "recipient": "player"}}
        self.manager.save_campaign(campaign["campaign_id"])
        return record, {
            "message": f'/item receive {item["item_id"]} vendor',
            "action_id": str(uuid4()),
        }

    async def post(self, campaign, command):
        return await self.http.post(
            f'/api/game/sessions/{campaign["session_id"]}/turn', json=command)

    def snapshot(self, record):
        return copy.deepcopy((
            record.game_session.serialize_game_state(),
            record.game_session.rng.getstate(),
            record.journal, record.narrative_memory, record.lore_authority.to_dict(),
            record.turn_action_receipts,
            self.store.get_campaign(record.campaign_id),
        ))

    async def test_transfer_replay_conflict_and_restart(self):
        campaign = await self.create_campaign()
        record, command = self.prepare(campaign)
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected Qwen call")):
            accepted = await self.post(campaign, command)
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertIn("atomik olarak tamamlandı", accepted.json()["narration"])
            self.assertEqual(record.game_session.world_state["npcs"][0]["inventory"], [])
            committed = self.snapshot(record)
            replay = await self.post(campaign, command)
            self.assertEqual(replay.json(), accepted.json())
            self.assertEqual(self.snapshot(record), committed)
            conflict = await self.post(campaign, {
                **command, "message": "/item list"})
            self.assertEqual(conflict.status_code, 409, conflict.text)
            self.assertEqual(self.snapshot(record), committed)
            # Existing resume owner reads the same persisted engine/receipt.
            sid, restored, *_ = self.manager.resume_campaign(campaign["campaign_id"])
            campaign["session_id"] = sid
            after_resume = self.snapshot(restored)
            replay = await self.post(campaign, command)
            self.assertEqual(replay.json(), accepted.json())
            self.assertEqual(self.snapshot(restored), after_resume)

    async def test_failed_autosave_restores_inventory_consent_equipment_and_rng(self):
        campaign = await self.create_campaign()
        record, command = self.prepare(campaign)
        item = record.game_session.world_state["npcs"][0]["inventory"][0]["item_id"]
        record.game_session.world_state["npcs"][0]["equipment"] = {
            "main_hand": item, "off_hand": None}
        self.manager.save_campaign(campaign["campaign_id"])
        before = self.snapshot(record)
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("fixture save failure")):
            failed = await self.post(campaign, command)
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(self.snapshot(record), before)
        self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        retry = await self.post(campaign, command)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertIn("atomik olarak tamamlandı", retry.json()["narration"])

    async def test_item_ids_cannot_transfer_another_sessions_possessions(self):
        first, second = await self.create_campaign(), await self.create_campaign()
        _, command = self.prepare(first)
        record_b = self.manager.get(second["session_id"])
        before = copy.deepcopy(record_b.game_session.world_state["inventory"])
        denied = await self.post(second, command)
        self.assertEqual(denied.status_code, 200, denied.text)
        self.assertIn("reddedildi", denied.json()["narration"])
        self.assertEqual(record_b.game_session.world_state["inventory"], before)


if __name__ == "__main__":
    unittest.main()
