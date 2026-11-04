"""Keep the change in one line (plan Task 9, panel "yes" path): the beer and its tip are one confirm, one receipt.

Design §3b and §11 D1, D8: Python writes the tip on the counter's offer (the coin held out over the price, from the
money owner's decision; the model never gives a figure), and the confirmed total decides. Goods plus that tip pays
both on one receipt; the goods' price alone buys the goods with no tip and says so; a tip that no longer fits moves
nothing (`tip_unavailable`); any other total is a changed price. The engine never charges more than the confirmed
total. Replay over HTTP is byte for byte the first answer and pays once; one undo takes back the purse, the vendor's
purse, the beer and the tipped offer together. No model call.
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

import bold_acts
import economic_actions
import game
import money_owner
import shop_trade
from api.tests import test_campaign_api as fixtures

LINE = "bir bira, 5 bakır, üstü kalsın"
TIP_SAID = "Bira 4 bakır + bahşiş 1 bakır = 5 bakır; onaylarsan 5 bakır geçer."
NO_TIP_SAID = "Bahşiş geçmedi; kesende kaldı."


def tavern(session, purse=100):
    world = session.world_state
    world["npcs"] = [{"id": "barman", "name": "Marek", "role": "Barmen", "location": world["location"],
                      "current_hp": 10}]
    world["currency"] = {"player": purse, "barman": 0}
    return world


def open_offer(session, *, amount=5, keep_change=True, goods="bira"):
    """The turn as the reading leaves it: the money owner's decision on the coin held out, then the counter opens.

    The decision is `money_owner.decide`'s own (the reading's deal is goods, these goods, keep the change); the
    counter reads it through `bold_acts.resolve`. The turn's fields are cleared afterwards, as the next turn does.
    """
    world = session.world_state
    barman = world["npcs"][0]
    session._coin_decision = money_owner.decide(world, person=barman, amount_cp=amount,
                                                deal=money_owner.Deal("goods", goods, keep_change), arrester=None)
    session._coin_paid = (amount, barman, world["location"])
    try:
        return bold_acts.resolve(session, LINE)
    finally:
        money_owner.forget_turn(session)
        session._coin_paid = None


def purse(world):
    return world["currency"]["player"]


def bag(world):
    return [item.get("name") if isinstance(item, dict) else item for item in world.get("inventory", [])]


def snapshot(world):
    return copy.deepcopy(world)


def operations(world):
    return list(((world.get("flags") or {}).get("economic_ledger") or {}).get("operations", {}).values())


class KeepTheChange(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session()
        self.w = tavern(self.s)
        self.reply = open_offer(self.s)

    def last_op(self):
        return operations(self.w)[-1]

    def offer(self):
        return self.w["flags"]["counter_offer_v1"]

    def refused(self, reason, total, count=1):
        before = snapshot(self.w)
        with self.assertRaises(shop_trade.TradeRefused) as raised:
            shop_trade.commit(self.w, "barman", "bira", count, 0, total)
        self.assertEqual(raised.exception.args[0], reason, total)
        self.assertEqual(snapshot(self.w), before, total)
        return raised.exception

    def test_counter_tip_is_the_coin_over_the_price_written_by_python(self):
        self.assertEqual(self.reply["action_result"]["action"], "shop_offer", self.reply["narration"])
        self.assertEqual({key: self.offer().get(key) for key in ("npc_id", "key", "seq", "tender_cp", "tip_cp")},
                         {"npc_id": "barman", "key": "bira", "seq": 0, "tender_cp": 5, "tip_cp": 1})
        self.assertTrue(self.reply["narration"].endswith(f" {TIP_SAID}"), self.reply["narration"])
        self.assertEqual(self.reply["action_result"]["direct_response"], self.reply["narration"])
        # Opening the offer moves nothing and opens no card: only the counter's confirm pays.
        self.assertEqual((purse(self.w), self.w["currency"]["barman"], bag(self.w).count("Bira")), (100, 0, 0))
        self.assertEqual([data for data in self.w["flags"].get("economic_offers", {}).values()
                          if data.get("status") == "prepared"], [])
        # The figure is Python's: coin held out minus the price, whatever coin it was.
        self.setUp()
        self.reply = open_offer(self.s, amount=10)
        self.assertEqual((self.offer()["tender_cp"], self.offer()["tip_cp"]), (10, 6))
        self.assertIn("Bira 4 bakır + bahşiş 6 bakır = 10 bakır; onaylarsan 10 bakır geçer.", self.reply["narration"])
        # No keep-the-change, no tip: the coin is the offer's tender and the change is the player's.
        self.setUp()
        self.reply = open_offer(self.s, keep_change=False)
        self.assertEqual(self.offer()["tender_cp"], 5)
        self.assertNotIn("tip_cp", self.offer())
        self.assertNotIn("bahşiş", self.reply["narration"])

    def test_a_tip_is_written_only_for_the_person_and_goods_it_was_decided_for(self):
        world = tavern(self.s)
        barman = world["npcs"][0]
        # The decision kept the change on a plate (31 for 30); the offer opening now is the beer's.
        self.s._coin_decision = money_owner.decide(world, person=barman, amount_cp=31,
                                                   deal=money_owner.Deal("goods", "yemek", True), arrester=None)
        self.assertEqual(self.s._coin_decision.tip_cp, 1)
        reply = bold_acts._with_tender(self.s, barman, "bira", 31)
        self.assertEqual(self.offer()["tender_cp"], 31)
        self.assertNotIn("tip_cp", self.offer())
        self.assertNotIn("bahşiş", reply["narration"])
        # Nor for someone else who serves.
        other = {**barman, "id": "osman_barman", "name": "Osman"}
        world["npcs"].append(other)
        self.s._coin_decision = money_owner.decide(world, person=barman, amount_cp=5,
                                                   deal=money_owner.Deal("goods", "bira", True), arrester=None)
        bold_acts._with_tender(self.s, other, "bira", 5)
        self.assertEqual(self.offer()["npc_id"], "osman_barman")
        self.assertNotIn("tip_cp", self.offer())

    def test_confirming_goods_plus_tip_pays_both_on_one_receipt(self):
        line = shop_trade.commit(self.w, "barman", "bira", 1, 0, 5)
        self.assertEqual((purse(self.w), self.w["currency"]["barman"], bag(self.w).count("Bira")), (95, 5, 1))
        self.assertNotIn("para üstü", line)
        self.assertEqual(line, "Marek önüne 1 bira bırakıyor; 4 bakır ve 1 bakır bahşiş kesenden tezgâha geçiyor.")
        self.assertEqual(self.last_op()["net_debit_cp"], 5)
        self.assertEqual(len(operations(self.w)), 1)  # one receipt for the goods and the tip
        self.assertEqual((self.last_op()["purpose"], self.last_op()["payee_id"]), ("purchase", "barman"))
        self.assertEqual(self.w["shop_trades_v1"]["seq"], 1)

    def test_old_panel_total_buys_without_tip_and_says_so(self):
        line = shop_trade.commit(self.w, "barman", "bira", 1, 0, 4)
        self.assertEqual(purse(self.w), 96)
        self.assertEqual((self.w["currency"]["barman"], bag(self.w).count("Bira")), (4, 1))
        self.assertTrue(line.endswith(NO_TIP_SAID), line)
        self.assertNotIn("para üstü", line)  # the coin held out for goods and tip is not this sale's tender
        self.assertEqual(self.last_op()["net_debit_cp"], 4)

    def test_tip_that_no_longer_fits_moves_nothing(self):
        self.w["currency"]["player"] = 4
        refusal = self.refused("tip_unavailable", 5)
        self.assertEqual(refusal.quote["total_cp"], 4)
        # The goods alone still fit and are sold, with the tip left in the purse.
        self.assertTrue(shop_trade.commit(self.w, "barman", "bira", 1, 0, 4).endswith(NO_TIP_SAID))
        self.assertEqual((purse(self.w), self.w["currency"]["barman"]), (0, 4))

    def test_a_tip_declined_today_is_not_paid_by_the_counter(self):
        economic_actions.record_decline(self.w, "barman", "tip", 1, day=economic_actions.game_day(self.w), turn=0)
        self.refused("tip_unavailable", 5)
        self.assertTrue(shop_trade.commit(self.w, "barman", "bira", 1, 0, 4).endswith(NO_TIP_SAID))
        self.assertEqual((purse(self.w), self.w["currency"]["barman"]), (96, 4))

    def test_any_other_total_is_price_changed(self):
        for total in (6, 3, 0, 9):
            with self.subTest(total=total):
                self.assertEqual(self.refused("price_changed", total).quote["total_cp"], 4)

    def test_a_tip_rides_on_one_of_the_goods_only(self):
        self.refused("tip_unavailable", 9, count=2)
        line = shop_trade.commit(self.w, "barman", "bira", 2, 0, 8)
        self.assertTrue(line.endswith(NO_TIP_SAID), line)
        self.assertEqual((purse(self.w), bag(self.w).count("Bira")), (92, 2))

    def test_engine_never_charges_more_than_the_confirmed_total(self):
        def tipped(s):
            open_offer(s)

        def tipped_short_purse(s):
            open_offer(s)
            s.world_state["currency"]["player"] = 4

        def tip_declined(s):
            open_offer(s)
            economic_actions.record_decline(s.world_state, "barman", "tip", 1,
                                            day=economic_actions.game_day(s.world_state), turn=0)

        def plain_tender(s):
            open_offer(s, keep_change=False)

        def gold_kept(s):
            open_offer(s, amount=100)

        sold: dict[str, list[int]] = {}
        refused: dict[str, int] = {}
        for setup in (tipped, tipped_short_purse, tip_declined, plain_tender, gold_kept):
            session = game.create_session()
            tavern(session)
            setup(session)
            tavern_as_set = snapshot(session.world_state)
            for count in (1, 2):
                for confirmed in [*range(0, 12), 100, 104]:
                    with self.subTest(setup=setup.__name__, count=count, confirmed=confirmed):
                        world = snapshot(tavern_as_set)  # a fresh tavern each time
                        before = snapshot(world)
                        try:
                            shop_trade.commit(world, "barman", "bira", count, 0, confirmed)
                        except shop_trade.TradeRefused:
                            self.assertEqual(snapshot(world), before)
                            refused[setup.__name__] = refused.get(setup.__name__, 0) + 1
                            continue
                        spent = before["currency"]["player"] - world["currency"]["player"]
                        self.assertLessEqual(spent, confirmed)
                        self.assertEqual(spent, confirmed)
                        self.assertEqual(world["currency"]["barman"], spent)
                        self.assertEqual(operations(world)[-1]["net_debit_cp"], spent)
                        sold.setdefault(setup.__name__, []).append(confirmed)
        # What each tavern sold at: the goods alone always, goods plus tip only where the tip still fits.
        self.assertEqual(sold, {"tipped": [4, 5, 8], "tipped_short_purse": [4], "tip_declined": [4, 8],
                                "plain_tender": [4, 8], "gold_kept": [4, 100, 8]})
        self.assertTrue(all(refused.get(name) for name in sold))

    def test_counter_purchase_tip_line_is_accepted_and_paid_to_the_vendor(self):
        offer = economic_actions.counter_purchase_offer(self.w, npc_id="barman", key="bira", count=1, unit_cp=4,
                                                        tender_cp=5, tip_cp=1)
        self.assertEqual(offer.lines[1], economic_actions.OfferLine(
            line_id="tip:1", kind="tip", source_id=None, item_id=None, recipient_id="barman", count=1, unit_cp=1,
            total_cp=1, optional=True))
        self.assertIn(economic_actions.LineDecision(line_id="tip:1", status="accepted", reason_code="engine_accepts"),
                      offer.acceptance.line_decisions)
        state = economic_actions.EconomicState(world=self.w, character=None)
        resolution = economic_actions.resolve_offer(
            state, offer, operation_id=economic_actions.operation_id_for(self.w, "purchase"))
        self.assertEqual((resolution.status, resolution.refusals, resolution.net_debit_cp, resolution.change_cp),
                         ("applied", [], 5, 0))
        applied = economic_actions.apply_resolution(state, resolution, confirmed_offer=offer)
        self.assertEqual(applied.status, "applied")
        self.assertEqual((purse(self.w), self.w["currency"]["barman"]), (95, 5))
        # With no tip the counter's offer is its one goods line, as before.
        plain = economic_actions.counter_purchase_offer(self.w, npc_id="barman", key="bira", count=1, unit_cp=4,
                                                        tender_cp=None)
        self.assertEqual([line.line_id for line in plain.lines], ["goods:0"])
        self.assertEqual([decision.line_id for decision in plain.acceptance.line_decisions], ["goods:0"])

    def test_dropping_the_tip_keeps_the_goods_at_their_price(self):
        self.assertTrue(bold_acts.drop_counter_tip(self.w, "barman"))
        self.assertNotIn("tip_cp", self.offer())
        self.assertEqual(self.offer()["tender_cp"], 4)  # the coin the offer takes is the price, no tip on top
        self.assertFalse(bold_acts.drop_counter_tip(self.w, "barman"))  # nothing left to drop
        self.offer()["tip_after_cp"] = 1  # the panel-"no" path's waiting tip goes the same way
        self.assertTrue(bold_acts.drop_counter_tip(self.w, "barman"))
        self.assertNotIn("tip_after_cp", self.offer())
        self.offer()["tip_cp"] = 1
        self.assertFalse(bold_acts.drop_counter_tip(self.w, "osman"))  # another person's word drops nothing
        self.assertEqual(self.offer()["tip_cp"], 1)
        del self.offer()["tip_cp"]
        before = snapshot(self.w)
        self.refused("price_changed", 5)
        self.assertEqual(snapshot(self.w), before)
        line = shop_trade.commit(self.w, "barman", "bira", 1, 0, 4)
        self.assertNotIn(NO_TIP_SAID, line)
        self.assertNotIn("para üstü", line)
        self.assertEqual((purse(self.w), self.w["currency"]["barman"]), (96, 4))

    def test_a_malformed_counter_tip_is_dropped_on_repair(self):
        self.assertEqual(bold_acts.repair_counter_tip(self.w), [])
        self.assertEqual(self.offer()["tip_cp"], 1)
        for bad in (0, -1, True, "1", 1.0, None, [1]):
            with self.subTest(bad=bad):
                self.offer()["tip_cp"] = bad
                self.offer()["tip_after_cp"] = bad
                with self.assertLogs("bold_acts", level="WARNING"):
                    dropped = bold_acts.repair_counter_tip(self.w)
                self.assertEqual(dropped, ["counter_offer_v1.tip_cp", "counter_offer_v1.tip_after_cp"])
                self.assertNotIn("tip_cp", self.offer())
                self.assertNotIn("tip_after_cp", self.offer())
                self.assertEqual(self.offer()["tender_cp"], 5)  # the rest of the offer stays
        self.w["flags"].pop("counter_offer_v1")
        self.assertEqual(bold_acts.repair_counter_tip(self.w), [])
        self.assertEqual(bold_acts.repair_counter_tip({}), [])


class KeepTheChangeOverHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def tipped_campaign(self):
        campaign = await self.create_campaign()
        record = self.manager.get(campaign["session_id"])
        tavern(record.game_session)
        open_offer(record.game_session)
        self.manager.save_campaign(campaign["campaign_id"])
        return campaign, record

    async def post(self, campaign, body):
        return await self.http.post(f'/api/game/sessions/{campaign["session_id"]}/turn', json=body)

    async def undo(self, campaign, target):
        return await self.http.post(f'/api/game/sessions/{campaign["session_id"]}/undo',
                                    json={"action_id": str(uuid4()), "target_action_id": target})

    def snapshot(self, record):
        return copy.deepcopy((
            record.game_session.serialize_game_state(),
            record.game_session.rng.getstate(),
            record.journal, record.narrative_memory, record.lore_authority.to_dict(),
            record.turn_action_receipts,
            self.store.get_campaign(record.campaign_id),
        ))

    async def test_tipped_buy_replay_is_byte_identical_and_pays_once(self):
        campaign, record = await self.tipped_campaign()
        command = {"message": "/item shop_buy barman bira 1 0 5", "action_id": str(uuid4())}
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            first = await self.post(campaign, command)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertIn("1 bakır bahşiş", first.json()["narration"])
            world = record.game_session.world_state
            self.assertEqual(world["currency"], {"player": 95, "barman": 5})
            self.assertEqual(bag(world).count("Bira"), 1)
            committed = self.snapshot(record)
            again = await self.post(campaign, command)
            self.assertEqual(again.status_code, 200, again.text)
            self.assertEqual(again.content, first.content)
            self.assertEqual(self.snapshot(record), committed)
            self.assertEqual(len(operations(world)), 1)
            sid, restored, *_ = self.manager.resume_campaign(campaign["campaign_id"])
            campaign["session_id"] = sid
            resumed = self.snapshot(restored)
            after_resume = await self.post(campaign, command)
            self.assertEqual(after_resume.content, first.content)
            self.assertEqual(self.snapshot(restored), resumed)
            self.assertEqual(restored.game_session.world_state["currency"], {"player": 95, "barman": 5})

    async def test_undo_restores_purse_vendor_goods_and_the_offer(self):
        campaign, record = await self.tipped_campaign()
        offer = copy.deepcopy(record.game_session.world_state["flags"]["counter_offer_v1"])
        self.assertEqual((offer["tip_cp"], offer["tender_cp"]), (1, 5))
        bought_id = str(uuid4())
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            bought = await self.post(campaign, {"message": "/item shop_buy barman bira 1 0 5", "action_id": bought_id})
            self.assertEqual(bought.status_code, 200, bought.text)
            self.assertEqual(record.game_session.world_state["currency"], {"player": 95, "barman": 5})
            undone = await self.undo(campaign, bought_id)
            self.assertEqual(undone.status_code, 200, undone.text)
            self.assertEqual(undone.json()["undone_action_id"], bought_id)
            world = record.game_session.world_state
            self.assertEqual(world["currency"], {"player": 100, "barman": 0})
            self.assertNotIn("Bira", bag(world))
            self.assertEqual(world["flags"]["counter_offer_v1"], offer)
            self.assertEqual(shop_trade.seq(world), 0)
            self.assertEqual(operations(world), [])
            # One step only (D37): a second undo is refused and changes nothing.
            settled = self.snapshot(record)
            again = await self.undo(campaign, bought_id)
            self.assertEqual(again.status_code, 409, again.text)
            self.assertEqual(again.json()["detail"]["code"], "undo_unavailable")
            self.assertEqual(self.snapshot(record), settled)
            # The offer came back with its tip: confirming it again pays once.
            rebought = await self.post(campaign, {"message": "/item shop_buy barman bira 1 0 5",
                                                  "action_id": str(uuid4())})
            self.assertEqual(rebought.status_code, 200, rebought.text)
            self.assertEqual(world["currency"], {"player": 95, "barman": 5})
            self.assertEqual(bag(world).count("Bira"), 1)
            self.assertEqual([op["net_debit_cp"] for op in operations(world)], [5])


if __name__ == "__main__":
    unittest.main()
