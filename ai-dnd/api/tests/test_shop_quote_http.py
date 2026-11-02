"""The counter quote route reads the offer and writes nothing; a trade turn says why it was refused."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import yaml

from api.tests import test_campaign_api as fixtures

SPEC = yaml.safe_load((Path(__file__).resolve().parents[3] / "lib/api-spec/openapi.yaml").read_text(encoding="utf-8"))


class ShopQuoteHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    def prepare(self, campaign, purse=1234, role="Barmen"):
        record = self.manager.get(campaign["session_id"])
        world = record.game_session.world_state
        world["npcs"] = [{"id": "barman", "name": "Marek", "role": role, "location": world["location"],
                          "current_hp": 10}]
        world["currency"] = {"player": purse}
        self.manager.save_campaign(campaign["campaign_id"])
        return record

    async def quote(self, campaign):
        return await self.http.get(f'/api/game/sessions/{campaign["session_id"]}/shop')

    async def turn(self, campaign, line, mode="do"):
        return await self.http.post(f'/api/game/sessions/{campaign["session_id"]}/turn',
                                    json={"message": line, "action_id": str(uuid4()), "interaction_mode": mode})

    def snapshot(self, record):
        return copy.deepcopy((record.game_session.serialize_game_state(), record.game_session.world_state,
                              record.turn_action_receipts, self.store.get_campaign(record.campaign_id)))

    async def test_quote_shows_vendor_lines_purse_and_offer_number_and_writes_nothing(self):
        campaign = await self.create_campaign()
        record = self.prepare(campaign)
        before = self.snapshot(record)
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            first = await self.quote(campaign)
            second = await self.quote(campaign)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.snapshot(record), before)
        body = first.json()
        self.assertEqual(body["session_id"], campaign["session_id"])
        self.assertEqual(body["campaign_id"], campaign["campaign_id"])
        self.assertEqual(body["status"], "ready")
        self.assertIsNone(body["reason"])
        import living_world
        # The name the player already knows, never a name they were not told.
        self.assertEqual(body["vendor"], {"npc_id": "barman",
                                          "name": living_world.public_npc_name(record.game_session.world_state["npcs"][0])})
        self.assertEqual(body["purse"], {"total_cp": 1234, "gp": 12, "sp": 3, "cp": 4})
        self.assertEqual(body["seq"], 0)
        self.assertEqual([(line["key"], line["unit_cp"], line["stock"], line["discount_cp"]) for line in body["lines"]],
                         [("bira", 4, 12, 0), ("sarap", 20, 12, 0), ("yemek", 30, 12, 0)])
        self.assertEqual(body["lines"][0]["label"], "bira")

    async def test_a_trade_moves_the_quote_and_resume_reads_the_same(self):
        campaign = await self.create_campaign()
        self.prepare(campaign)
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            bought = await self.turn(campaign, "/item shop_buy barman bira 2 0 8")
            self.assertEqual(bought.status_code, 200, bought.text)
            after = (await self.quote(campaign)).json()
        self.assertEqual(after["seq"], 1)
        self.assertEqual(after["lines"][0]["stock"], 10)
        self.assertEqual(after["purse"]["total_cp"], 1226)
        sid, *_ = self.manager.resume_campaign(campaign["campaign_id"])
        campaign["session_id"] = sid
        reopened = (await self.quote(campaign)).json()
        self.assertEqual({**reopened, "session_id": None, "revision": None}, {**after, "session_id": None, "revision": None})

    async def test_no_vendor_here_is_unavailable_with_no_lines(self):
        campaign = await self.create_campaign()
        self.prepare(campaign, role="Muhafız")
        body = (await self.quote(campaign)).json()
        self.assertEqual((body["status"], body["reason"], body["vendor"], body["lines"]), ("unavailable", "no_vendor", None, []))
        self.assertEqual(body["purse"]["total_cp"], 1234)

    async def test_unknown_session_is_404(self):
        response = await self.http.get(f"/api/game/sessions/{uuid4()}/shop")
        self.assertEqual(response.status_code, 404, response.text)

    async def test_a_refused_trade_names_its_reason_in_the_turn_outcome(self):
        campaign = await self.create_campaign()
        self.prepare(campaign)
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            stale = await self.turn(campaign, "/item shop_buy barman bira 1 0 5")
        outcome = stale.json()["turn_outcome"]
        self.assertEqual((outcome["action"], outcome["status"], outcome["reason"]),
                         ("equipment_transaction", "rejected", "price_changed"))

    def test_the_published_route_and_schema_match_the_app(self):
        runtime = self.app.openapi()
        operation = SPEC["paths"]["/game/sessions/{session_id}/shop"]["get"]
        self.assertEqual(operation["operationId"], "getGameSessionShop")
        self.assertEqual(set(operation["responses"]), {"200", "401", "404", "409", "422"})
        self.assertNotIn("/sessions/{session_id}/shop", SPEC["paths"])
        for name in ("ShopCounterResponse", "ShopCounterVendor", "ShopCounterLine", "ShopCounterPurse"):
            with self.subTest(schema=name):
                published, actual = SPEC["components"]["schemas"][name], runtime["components"]["schemas"][name]
                self.assertEqual(set(published["properties"]), set(actual["properties"]))
                self.assertEqual(set(published.get("required", [])), set(actual.get("required", [])))
        self.assertIn("reason", SPEC["components"]["schemas"]["TurnOutcome"]["properties"])


if __name__ == "__main__":
    unittest.main()
