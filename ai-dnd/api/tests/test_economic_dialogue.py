"""A4: talk, handed coin, NPC gifts, wages and the counter trade all go through the one economic owner.

No real model is called: a turn either runs with the model boundary patched to fail, or the scripted fake model
of the campaign fixtures stands in. Coin handed over in a line only opens a card; an NPC paying from their own
purse and a day's wage are engine payments (no card) recorded once in the ledger; a counter sale moves coin,
goods, stock and the counter's sequence together through `shop_trade.commit` and nothing else.
"""

from __future__ import annotations

import copy
import json
import unittest
import uuid
from unittest.mock import patch

import bold_acts
import economic_actions as ea
import equipment_economy
import game
import shop_trade
import town_knowledge
import world_reactions
import world_threads
from api.core_resolution import resolution_action_scope
from api.tests import test_thread_hiring as hiring
from api.tests.test_economic_action_http import EconomicHttpFixture
from money_owner import CoinDecision

DAY = 86400
HOUR = 3600


class Talk(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.w = self.s.world_state
        self.here = self.w["location"]
        self.w["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "guest", "name": "Oren", "role": "Yolcu", "location": self.here, "current_hp": 10},
        ]
        self.w["currency"] = {"player": 500, "barman": 100, "guest": 100}
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)

    def npc(self, npc_id):
        return next(npc for npc in self.w["npcs"] if npc["id"] == npc_id)

    def offers(self):
        return self.w.get("flags", {}).get("economic_offers", {})

    def prepared(self):
        return [data for data in self.offers().values() if data["status"] == "prepared"]

    def ledger(self):
        return self.w.get("flags", {}).get("economic_ledger", {})

    def money(self):
        """The purses and the names in the pack (a turn may give the pack's things their item ids)."""
        names = [item.get("name") if isinstance(item, dict) else item for item in self.w.get("inventory", [])]
        return copy.deepcopy((self.w["currency"], names))

    def confirm(self, data, action="confirm-1", check=lambda skill, dc: "BAŞARILI"):
        with resolution_action_scope(action, "session"):
            return ea.confirm_offer(ea.EconomicState(world=self.w, character=self.s.character),
                                    offer_id=data["offer_id"], confirmation_digest=data["confirmation_digest"],
                                    operation_id=f"offer:{action}", check=check)

    def settle(self, npc_id, amount, text="paramı ver hadi"):
        return town_knowledge.settle_reply(self.w, self.npc(npc_id), text, {"kind": "give", "amount_cp": amount},
                                           "Al bakalım.", accept_job=lambda thread: None)


class HandedCoin(Talk):
    def hold_out(self, amount, npc_id, kind="gift"):
        """What the reading leaves for coin held out in a line: the money owner's decision and the coin in hand."""
        self.s._coin_decision = CoinDecision(kind, npc_id, amount, 0, None, "model", self.here)
        self.s._coin_paid = (amount, self.npc(npc_id) if npc_id else None, self.here)

    def test_refused_gift_does_not_debit(self):
        self.hold_out(5, "guest")
        before = self.money()
        with patch.object(world_reactions, "refuses", side_effect=lambda world, npc: npc.get("id") == "guest"):
            result = self.s.run_player_turn("/item list")
        self.assertEqual(self.money(), before)
        self.assertEqual(self.prepared(), [])
        self.assertIn(world_reactions.refusal_line(self.npc("guest")), result["narration"])

    def test_tip_is_not_swallowed_by_currency_flag(self):
        # The old end-of-turn payer skipped any line that already showed a coin change; the card does not.
        self.s._economic_turn_key = "turn-tip"
        self.hold_out(5, "guest")
        result = {"narration": "Kese şıngırdıyor.",
                  "action_result": {"action": "narrative", "status": "resolved", "state_changes": ["currency"]}}
        before = self.money()
        game._tell_the_coin(result, session=self.s)
        self.assertEqual(self.money(), before)
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["proposal"]["recipient_id"], card["proposal"]["amount_cp"]),
                         ("gift", "guest", 5))
        self.assertEqual(card["proposal"]["source_action_id"], "turn-tip")

    def test_handed_coin_without_order_opens_gift_card_no_debit(self):
        self.hold_out(5, "guest")
        before = self.money()
        result = self.s.run_player_turn("/item list")
        self.assertEqual(self.money(), before)
        [card] = self.prepared()
        self.assertEqual((card["proposal"]["purpose"], card["lines"][0]["recipient_id"], card["lines"][0]["total_cp"]),
                         ("gift", "guest", 5))
        self.assertNotIn("kesenden çıkıyor", result["narration"])
        self.assertIn("teklif hazır", result["narration"])
        self.assertEqual(self.ledger().get("operations", {}), {})

    def test_unconfirmed_coin_prompt_never_says_taken(self):
        guest = self.npc("guest")
        self.hold_out(5, "guest")
        note = game._experimental_speech_note(self.w, guest, None, "al şunu", session=self.s)
        self.assertNotIn("artık sende", note)
        self.assertIn("henüz sende değil", note)
        self.assertIn("5 bakır", note)
        # Coin held out to nobody the line could name opens no card naming anyone: whoever answers is not told of it.
        self.hold_out(5, None, "unclear")
        note = game._experimental_speech_note(self.w, guest, None, "al şunu", session=self.s)
        self.assertNotIn("bakır uzatıyor", note)
        # Coin held out to someone else is not this person's either.
        self.hold_out(5, "barman")
        note = game._experimental_speech_note(self.w, guest, None, "al şunu", session=self.s)
        self.assertNotIn("bakır uzatıyor", note)
        # A room line takes the coin as its tender (or ignores it with a note): nobody is told it changed hands.
        self.hold_out(100, "barman", "room")
        self.s.run_player_turn("hancıya 1 altın verip oda tutuyorum")
        note = game._experimental_speech_note(self.w, self.npc("barman"), None, "oda", session=self.s)
        self.assertNotIn("artık sende", note)
        # A thing really carried over keeps today's sentence.
        self.s._handed_note = "Mektup"
        note = game._experimental_speech_note(self.w, guest, None, "al şunu", session=self.s)
        self.assertIn("artık sende: Mektup", note)


class NpcGifts(Talk):
    def test_npc_purse_gift_applies_once_after_commit(self):
        settled = self.settle("guest", 5)
        self.assertEqual(settled["moved"], 5)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guest"]), (505, 95))
        [(operation_id, entry)] = self.ledger()["operations"].items()
        self.assertEqual((entry["purpose"], entry["net_debit_cp"]), ("npc_gift", 5))
        self.assertTrue(operation_id.startswith("unscoped:economic:npc_gift:"), operation_id)
        self.assertIn("5", settled["note"])
        self.assertEqual(self.prepared(), [])

    def test_npc_spoken_give_beyond_purse_moves_nothing(self):
        before = self.money()
        settled = self.settle("guest", 500)
        self.assertEqual(settled["moved"], 0)
        self.assertIsNone(settled["note"])
        self.assertEqual(self.money(), before)
        self.assertEqual(self.ledger().get("operations", {}), {})
        resolution = ea.npc_gift(ea.EconomicState(world=self.w, character=None), npc_id="guest", amount_cp=500)
        self.assertEqual((resolution.status, resolution.reason_code, resolution.asset_deltas),
                         ("refused", "npc_purse_short", []))

    def test_spoken_give_without_payer_purse_creates_no_coin(self):
        del self.w["currency"]["guest"]
        before = self.money()
        settled = self.settle("guest", 5)
        self.assertEqual(settled["moved"], 0)
        self.assertEqual(self.money(), before)
        self.assertNotIn("guest", self.w["currency"])

    def test_failed_npc_gift_write_leaves_the_operation_counter(self):
        before = copy.deepcopy(self.w)
        with patch("economic_actions.validate_economic_resolution",
                   side_effect=ea.EconomicReceiptError("receipt_mismatch")):
            with self.assertRaises(ea.EconomicReceiptError):
                ea.npc_gift(ea.EconomicState(world=self.w, character=None), npc_id="guest", amount_cp=5)
        self.assertEqual(self.w, before)
        self.assertNotIn("operation_seq", self.ledger())
        self.settle("guest", 5)
        self.assertEqual(list(self.ledger()["operations"]), ["unscoped:economic:npc_gift:1"])

    def test_npc_gift_without_scope_pays_once(self):
        self.settle("guest", 5)
        self.assertEqual(self.w["currency"]["player"], 505)
        self.assertEqual(list(self.ledger()["operations"]), [f"unscoped:economic:npc_gift:1"])

    def test_two_npc_gifts_same_turn_get_distinct_operations(self):
        turn = self.w["flags"].get("turn_index", 0)
        self.settle("guest", 5)
        self.settle("guest", 5)
        self.assertEqual(self.w["flags"].get("turn_index", 0), turn)
        self.assertEqual((self.w["currency"]["player"], self.w["currency"]["guest"]), (510, 90))
        self.assertEqual(sorted(self.ledger()["operations"]),
                         ["unscoped:economic:npc_gift:1", "unscoped:economic:npc_gift:2"])

    def test_scoped_two_part_line_gifts_get_distinct_operations(self):
        # Two scopes opened with the same action id, as game.py opens it many times in one turn.
        for _ in range(2):
            with resolution_action_scope("a-two", "session"):
                self.settle("guest", 5)
        self.assertEqual(sorted(self.ledger()["operations"]), ["a-two:economic:npc_gift:1", "a-two:economic:npc_gift:2"])
        self.assertEqual(self.w["currency"]["player"], 510)
        # The same within one line said in two parts: the rest of the line runs a second dispatch under one id.
        gifts = iter([5, 5])
        real = town_knowledge.settle_reply

        def paying_dispatch(*args, **kwargs):
            with resolution_action_scope("a-line", "session"):
                real(self.w, self.npc("guest"), "paramı ver hadi", {"kind": "give", "amount_cp": next(gifts)},
                     "Al.", accept_job=lambda thread: None)
            return {"messages": self.s.messages, "narration": "Al.", "model_calls": 0,
                    "action_result": {"action": "dialogue", "status": "resolved", "npc_id": "guest",
                                      "state_changes": []}}

        self.s._front_rest = "paramı da ver"
        self.s._front_read = {"id": "guest"}
        first = paying_dispatch()
        first["action_result"]["action"] = "narrative"
        turn = self.w["flags"].get("turn_index", 0)
        with patch("game._dispatch_player_turn", side_effect=paying_dispatch), \
                patch("api.ollama_adapter.model_calls_left", return_value=True):
            game._the_rest_of_the_line(first, self.s.messages, "a-line", "session", self.here, session=self.s)
        self.assertEqual(self.w["flags"].get("turn_index", 0), turn)
        self.assertEqual(sorted(op for op in self.ledger()["operations"] if op.startswith("a-line")),
                         ["a-line:economic:npc_gift:3", "a-line:economic:npc_gift:4"])
        self.assertEqual(self.w["currency"]["player"], 520)


class CounterTradeOwner(Talk):
    def buy(self, key="bira", count=1, seq=0, total=4):
        return shop_trade.commit(self.w, "barman", key, count, seq, total)

    def snapshot(self):
        flags = self.w.get("flags", {})
        return json.dumps({"currency": self.w["currency"], "inventory": self.w.get("inventory"),
                           "wares": self.npc("barman").get("wares_v1"), "trades": self.w.get(shop_trade.KEY),
                           "ledger": flags.get("economic_ledger"), "served": flags.get("served_turn")},
                          ensure_ascii=False, sort_keys=True, default=str)

    def test_shop_commit_label_only_purse_is_atomic(self):
        self.w["currency"]["player"] = 0
        self.w["inventory"] = ["1 Altın"]
        self.w["flags"]["turn_index"] = 4
        before = self.snapshot()
        with patch.object(equipment_economy, "grant_named_item", side_effect=equipment_economy.EquipmentError("boom")):
            with self.assertRaises(equipment_economy.EquipmentError):
                self.buy()
        self.assertEqual(self.snapshot(), before)
        self.buy()
        self.assertEqual(self.w["currency"]["player"], 96)
        self.assertNotIn("1 Altın", self.w["inventory"])
        self.assertEqual([item["name"] for item in self.w["inventory"] if isinstance(item, dict)].count("Bira"), 1)
        self.assertEqual(self.npc("barman")["wares_v1"]["bira"]["stock"], shop_trade.DEFAULT_STOCK - 1)
        self.assertEqual(self.w[shop_trade.KEY]["seq"], 1)
        self.assertEqual(self.w["flags"]["served_turn"], 4)
        purchases = [entry for entry in self.ledger()["operations"].values() if entry["purpose"] == "purchase"]
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases[0]["net_debit_cp"], 4)

    def test_shop_commit_records_purchase_operation(self):
        self.buy()
        self.assertEqual(list(self.ledger()["operations"]), ["unscoped:economic:purchase:1"])
        self.assertEqual(self.ledger()["operations"]["unscoped:economic:purchase:1"]["purpose"], "purchase")
        self.assertEqual(self.offers(), {})
        with resolution_action_scope("buy-2", "session"):
            self.buy(seq=1)
        self.assertIn("buy-2:economic:purchase:2", self.ledger()["operations"])

    def test_shop_commit_validates_goods_and_stock_receipt(self):
        real_grant = equipment_economy.grant_named_item

        def twice(world, name):
            real_grant(world, name)
            return real_grant(world, name)

        before = self.snapshot()
        with patch.object(equipment_economy, "grant_named_item", side_effect=twice):
            with self.assertRaises(ea.EconomicReceiptError):
                self.buy()
        self.assertEqual(self.snapshot(), before)
        real_goods = shop_trade.goods

        def stock_never_falls(world, npc):
            npc.pop("wares_v1", None)  # the counter forgets the sale it just wrote
            return real_goods(world, npc)

        with patch.object(shop_trade, "goods", side_effect=stock_never_falls):
            with self.assertRaises((ea.EconomicReceiptError, equipment_economy.EquipmentError)):
                self.buy()
        self.assertEqual(self.snapshot(), before)


class TwoBuyersOneBeer(EconomicHttpFixture):
    async def test_two_shop_buys_last_stock_one_winner(self):
        self.world["npcs"][0]["wares_v1"] = {"bira": {"stock": 1}}
        self.save()
        first = await self.post({"message": "/item shop_buy barman bira 1 0 4", "action_id": str(uuid.uuid4())})
        second = await self.post({"message": "/item shop_buy barman bira 1 0 4", "action_id": str(uuid.uuid4())})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(first.json()["turn_outcome"]["status"] == "resolved", first.text)
        self.assertEqual(second.json()["turn_outcome"]["reason"], "offer_stale")
        self.assertEqual(self.world["npcs"][0]["wares_v1"]["bira"]["stock"], 0)
        self.assertEqual((self.purse(), self.world["currency"]["barman"]), (96, 4))
        purchases = [entry for entry in self.world["flags"]["economic_ledger"]["operations"].values()
                     if entry["purpose"] == "purchase"]
        self.assertEqual(len(purchases), 1)


class Wages(unittest.IsolatedAsyncioTestCase):
    asyncSetUp, asyncTearDown = hiring.HiringTable.asyncSetUp, hiring.HiringTable.asyncTearDown
    campaign_with_npc, job, line = hiring.HiringTable.campaign_with_npc, hiring.HiringTable.job, hiring.HiringTable.line
    t, wallet, now = hiring.HiringTable.t, hiring.HiringTable.wallet, hiring.HiringTable.now

    def entitlements(self):
        return self.world.get("flags", {}).get("economic_ledger", {}).get("entitlements", {})

    async def test_job_pay_once_via_entitlement(self):
        await self.job(pay=40, days=3)
        money = self.wallet()
        await self.line("başlayalım")
        self.assertEqual(self.wallet() - money, 40)
        day = self.t()["last_paid_day_index"]
        self.assertEqual(self.entitlements(), {f"wage:{self.tid}:{day}": f"entitlement:wage:{self.tid}:{day}"})
        await self.line("başlayalım")  # the same day: nothing more is due
        self.assertEqual(self.wallet() - money, 40)
        self.assertEqual(len(self.entitlements()), 1)
        self.assertNotIn(f"thread-pool:{self.tid}:{day}", self.world["currency"])

    async def test_wage_without_action_id_pays_once(self):
        await self.job(pay=40, days=3)
        money, worked = self.wallet(), self.t()["days_worked"]
        token = game._ACTIVE_SESSION.set(self.session)  # the engine's clock is this session's, outside any request
        try:
            with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
                world_threads.work_turn(self.session, self.tid, "başlayalım")
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(self.wallet() - money, 40)
        self.assertEqual(self.t()["days_worked"], worked + 1)
        self.assertEqual(self.t()["paid_cp"], 40)
        day = self.t()["last_paid_day_index"]
        world_threads._credit_day(self.world, self.t(), day)  # the same day's tick comes again
        self.assertEqual(self.wallet() - money, 40)
        self.assertEqual(self.t()["paid_cp"], 40)

    async def test_last_day_remainder_paid_after_reorder(self):
        await self.job(pay=10, days=3, basis="total")
        paid = []
        for _ in range(3):
            money = self.wallet()
            await self.line("başlayalım")
            paid.append(self.wallet() - money)
            if self.t()["status"] == "accepted":
                self.world["campaign_time"]["elapsed_seconds"] += DAY - 8 * HOUR
        self.assertEqual(paid, [3, 3, 4])
        self.assertEqual(self.t()["paid_cp"], 10)
        self.assertEqual(self.t()["status"], "done")

    async def test_replayed_wage_event_does_not_count_day_twice(self):
        await self.job(pay=10, days=2, basis="total")
        thread, day = self.t(), world_threads._today(self.world)
        first = ea.settle_entitlement(ea.EconomicState(world=self.world, character=None), event_id=f"wage:{self.tid}:{day}",
                                      payer_id=f"thread-pool:{self.tid}:{day}", recipient_id="player", amount_cp=5)
        self.assertFalse(first.replayed)
        money, worked, paid = self.wallet(), thread.get("days_worked", 0), thread.get("paid_cp", 0)
        self.assertEqual(world_threads._credit_day(self.world, thread, day), (0, False))
        self.assertEqual((self.wallet(), thread.get("days_worked", 0), thread.get("paid_cp", 0)), (money, worked, paid))
        self.assertEqual(thread["status"], "accepted")

    def test_day_wage_reads_the_day_it_is_asked_for(self):
        thread = {"terms": {"pay": 10, "work_days": 3, "pay_basis": "total"}, "days_worked": 0}
        self.assertEqual([world_threads._day_wage(thread, worked=day) for day in (1, 2, 3)], [3, 3, 4])
        self.assertEqual(world_threads._day_wage({**thread, "days_worked": 3}), 4)


if __name__ == "__main__":
    unittest.main()
