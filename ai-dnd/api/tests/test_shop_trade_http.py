"""HTTP/SQLite proof for the counter trade: replay, conflict, resume, rollback and a stale offer; no model call."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

from api.tests import test_campaign_api as fixtures


class ShopTradeHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    def prepare(self, campaign, line="/item shop_buy barman bira 2 0 8"):
        record = self.manager.get(campaign["session_id"])
        world = record.game_session.world_state
        world["npcs"] = [{"id": "barman", "name": "Marek", "role": "Barmen", "location": world["location"],
                          "current_hp": 10}]
        world["currency"] = {"player": 500}
        self.manager.save_campaign(campaign["campaign_id"])
        return record, {"message": line, "action_id": str(uuid4())}

    async def post(self, campaign, command):
        return await self.http.post(f'/api/game/sessions/{campaign["session_id"]}/turn', json=command)

    def snapshot(self, record):
        return copy.deepcopy((
            record.game_session.serialize_game_state(),
            record.game_session.rng.getstate(),
            record.journal, record.narrative_memory, record.lore_authority.to_dict(),
            record.turn_action_receipts,
            self.store.get_campaign(record.campaign_id),
        ))

    @staticmethod
    def trade_state(record):
        world = record.game_session.world_state
        return copy.deepcopy((world["currency"], world["inventory"], world.get("shop_trades_v1"),
                              [npc.get("wares_v1") for npc in world["npcs"]]))

    def beers(self, record):
        return [item for item in record.game_session.world_state["inventory"]
                if isinstance(item, dict) and item.get("name") == "Bira"]

    async def test_buy_replay_conflict_resume_and_stale_offer(self):
        campaign = await self.create_campaign()
        record, command = self.prepare(campaign)
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            accepted = await self.post(campaign, command)
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertIn("8 bakır", accepted.json()["narration"])
            self.assertEqual(record.game_session.world_state["currency"], {"player": 492, "barman": 8})
            self.assertEqual(len(self.beers(record)), 2)
            committed = self.snapshot(record)
            replay = await self.post(campaign, command)
            self.assertEqual(replay.json(), accepted.json())
            self.assertEqual(self.snapshot(record), committed)
            conflict = await self.post(campaign, {**command, "message": "/item shop_buy barman bira 1 0 4"})
            self.assertEqual(conflict.status_code, 409, conflict.text)
            self.assertEqual(self.snapshot(record), committed)
            sid, restored, *_ = self.manager.resume_campaign(campaign["campaign_id"])
            campaign["session_id"] = sid
            self.assertEqual(self.trade_state(restored), self.trade_state(record))
            after_resume = self.snapshot(restored)
            replay = await self.post(campaign, command)
            self.assertEqual(replay.json(), accepted.json())
            self.assertEqual(self.snapshot(restored), after_resume)
            # The same confirm under a new action id is an old offer: refused, and nothing moves.
            trades = self.trade_state(restored)
            stale = await self.post(campaign, {**command, "action_id": str(uuid4())})
            self.assertEqual(stale.status_code, 200, stale.text)
            self.assertIn("offer_stale", stale.json()["narration"])
            self.assertEqual(self.trade_state(restored), trades)
            self.assertEqual(restored.game_session.world_state["currency"], {"player": 492, "barman": 8})

    async def test_failed_autosave_restores_purse_goods_stock_and_offer(self):
        campaign = await self.create_campaign()
        record, command = self.prepare(campaign, "/item shop_buy barman yemek 1 0 30")
        before = self.snapshot(record)
        with patch.object(self.manager, "autosave_turn", side_effect=RuntimeError("fixture save failure")):
            failed = await self.post(campaign, command)
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(self.snapshot(record), before)
        self.assertIsNone(self.manager.get_turn_action(record, command["action_id"]))
        retry = await self.post(campaign, command)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(record.game_session.world_state["currency"], {"player": 470, "barman": 30})
        plates = [item for item in record.game_session.world_state["inventory"]
                  if isinstance(item, dict) and item.get("name") == "Tabak yemek"]
        self.assertEqual(len(plates), 1)

    async def test_a_refused_trade_changes_nothing_over_http(self):
        campaign = await self.create_campaign()
        record, command = self.prepare(campaign, "/item shop_buy barman bira 1 0 5")
        trades = self.trade_state(record)
        refused = await self.post(campaign, command)
        self.assertEqual(refused.status_code, 200, refused.text)
        self.assertIn("price_changed", refused.json()["narration"])
        self.assertEqual(self.trade_state(record), trades)


if __name__ == "__main__":
    unittest.main()
