"""Coin leaving the player's hand never runs a shift or draws a wage (design §11 D4, decision 57; item 110).

Real app, real adapter, real engine; only the Ollama client is scripted. The rule sits in one place, at the entry of
`_carry_out_thread_turn`: while this turn's money decision holds coin, the job gate's `work` and `pay` are not
applied and the line is said to the person. A line without coin still works the shift as before.
"""

from __future__ import annotations

import unittest

import money_owner
import world_threads
from api.tests import test_front_proposal as front_tests
from money_owner import CoinDecision

HOUR = 3600


class CoinNeverWorks(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = front_tests.FrontTable.asyncSetUp
    asyncTearDown = front_tests.FrontTable.asyncTearDown
    campaign_with_npc = front_tests.FrontTable.campaign_with_npc
    open_job = front_tests.FrontTable.open_job
    begin = front_tests.FrontTable.begin
    line = front_tests.FrontTable.line
    status = front_tests.FrontTable.status
    offer = front_tests.FrontTable.offer

    async def hired(self):
        """The barman's 26 cp counting job, offered and taken on the screen; 100 cp in the purse."""
        await self.begin(kind="hiring")
        self.thread["terms"].update(pay=26, work_days=1)
        self.offer()
        self.client.front = {"kind": "offer_answer", "offer_id": self.thread["thread_id"], "answer": "accept"}
        await self.line("olur", "Güzel.")
        self.assertEqual(self.status(), "accepted")
        self.world.setdefault("currency", {})["player"] = 100
        self.clock0 = self.elapsed()

    def elapsed(self):
        return self.world["campaign_time"]["elapsed_seconds"]

    def purse(self):
        return self.world.get("currency", {}).get("player", 0)

    def job(self):
        return world_threads.by_id(self.world, self.thread["thread_id"])

    def decision(self):
        decision = getattr(self.session, "_coin_decision", None)
        self.assertIsInstance(decision, CoinDecision)
        return decision

    async def test_a_room_coin_line_runs_no_shift_and_pays_no_wage(self):
        await self.hired()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 50}
        out = await self.line("Oda için beş gümüş ödüyorum")
        self.assertEqual(self.elapsed(), self.clock0)
        self.assertEqual(self.purse(), 100)
        self.assertEqual(self.job()["status"], "accepted")
        self.assertEqual(self.job().get("days_worked", 0), 0)
        self.assertNotEqual(out["turn_outcome"]["action"], "work")
        self.assertEqual((self.decision().amount_cp, self.decision().npc_id), (50, self.npc["id"]))

    async def test_a_work_reading_with_coin_runs_no_shift(self):
        await self.hired()
        self.client.front = {"kind": "work", "coin_cp": 50}
        out = await self.line("Oda için beş gümüş ödüyorum")
        self.assertEqual(self.elapsed(), self.clock0)
        self.assertEqual(self.purse(), 100)
        self.assertEqual(self.job()["status"], "accepted")
        self.assertEqual(self.job().get("days_worked", 0), 0)
        self.assertNotEqual(out["turn_outcome"]["action"], "work")
        self.assertEqual(self.decision().amount_cp, 50)

    async def test_coin_held_out_to_a_payer_whose_wage_is_due_draws_no_pay(self):
        await self.hired()
        self.session.advance_campaign_time(2 * HOUR, "wait")  # past the first hour: the day's wage is due
        due, why = world_threads.wage_due(self.world, self.job())
        self.assertEqual((due, why), (26, None))
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "coin_cp": 5}
        out = await self.line("5 bakır atıyorum", "Hmm.")
        self.assertEqual(self.purse(), 100)
        self.assertNotIn(world_threads.paid_line(26, True), out["narration"])
        self.assertNotIn(world_threads.paid_line(26, False), out["narration"])
        self.assertIsNone(self.job().get("last_paid_day_index"))
        self.assertEqual(self.job()["status"], "accepted")
        self.assertIsNone((getattr(self.session, "_thread_turn", None) or {}).get("paid_line"))
        self.assertEqual(self.decision().amount_cp, 5)

    async def test_a_work_line_without_coin_still_runs_the_shift(self):
        await self.hired()
        self.client.front = {"kind": "work"}
        await self.line("Tamam, işi yapıyorum")
        self.assertEqual(self.elapsed() - self.clock0, 8 * HOUR)
        self.assertEqual(self.purse(), 126)
        self.assertIsNone(getattr(self.session, "_coin_decision", None))

    async def test_a_deal_with_no_coin_still_writes_the_decision_and_blocks_nothing(self):
        # D29: opening an offer is not holding out coin; the decision is written, with no tender
        await self.hired()
        self.client.front = {"kind": "speak_to", "person_id": self.npc["id"], "deal": "room"}
        await self.line("Bu gece için bir oda var mı?", "Bakalım.")
        decision = self.decision()
        self.assertEqual((decision.amount_cp, decision.source, decision.npc_id), (0, "model", self.npc["id"]))
        self.assertEqual(self.purse(), 100)


class MoneyOwnerReadsTheTurn(unittest.TestCase):
    """`current` and `blocks_money_moves` read only this turn's decision on the session."""

    def test_no_decision_blocks_nothing(self):
        class Session:
            pass
        session = Session()
        self.assertIsNone(money_owner.current(session))
        self.assertFalse(money_owner.blocks_money_moves(session))
        session._coin_decision = "not a decision"
        self.assertIsNone(money_owner.current(session))
        self.assertFalse(money_owner.blocks_money_moves(session))

    def test_only_coin_held_out_blocks(self):
        class Session:
            pass
        session = Session()
        offer = CoinDecision("room", "barman", 0, 0, None, "model", "here")
        session._coin_decision = offer
        self.assertIs(money_owner.current(session), offer)
        self.assertFalse(money_owner.blocks_money_moves(session))
        for kind in ("room", "goods", "gift", "tip", "unclear", "bribe", "paid_before"):
            session._coin_decision = CoinDecision(kind, "barman", 5, 0, None, "structural", "here")
            self.assertTrue(money_owner.blocks_money_moves(session), kind)
