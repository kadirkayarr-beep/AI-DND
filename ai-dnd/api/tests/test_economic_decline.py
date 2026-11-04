"""Dilim 1, Task 3: the economic owner keeps a spoken decline per part, and ledger operations carry label and payee.

A decline is written per NPC and per part (`tip`, `gift`, `room`, `goods:<key>` or `*` for an unclear one) in
`flags.money_declined`. While it holds, no card of that part opens for that NPC and the open ones are cancelled.
It ends only by an explicit take of that part (`clear_decline`) or by a new game day; turns do not end it. At most
32 NPCs are kept: earlier days go first and today's record never goes silently. New ledger operations carry a
short `label` and the `payee_id`, which `recent_payments` reads. No real model is called.
"""

from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import patch

import campaign_time
import economic_actions as ea
import game
from api.core_resolution import resolution_action_scope

DAY = 86400


class DeclineFixture(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session(seed=7)
        self.world = self.s.world_state
        self.here = self.world["location"]
        self.world["npcs"] = [
            {"id": "barman", "name": "Marek", "role": "Barmen", "location": self.here, "current_hp": 10},
            {"id": "osman", "name": "Osman", "role": "Yolcu", "location": self.here, "current_hp": 10},
        ]
        self.world["currency"] = {"player": 500, "barman": 100, "osman": 100}
        self.world.setdefault("flags", {})["turn_index"] = 3
        campaign_time.initialize(self.world)
        chat = patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call"))
        chat.start()
        self.addCleanup(chat.stop)
        self.actions = 0

    def state(self) -> ea.EconomicState:
        return ea.EconomicState(world=self.world, character=self.s.character)

    @staticmethod
    def proposal(purpose: str, npc_id: str, amount: int | None = None, *, tip_cp: int = 0,
                 dependency: str = "base_required") -> ea.EconomicProposal:
        return ea.EconomicProposal(purpose=purpose, recipient_id=npc_id, source_id=None, item_id=None, count=1,
                                   amount_cp=amount, tip_cp=tip_cp, tender_cp=None, dependency=dependency,
                                   source_action_id=f"action-{purpose}-{npc_id}", text_span=None)

    def prepare(self, purpose: str, npc_id: str, amount: int | None = None, **extra) -> str:
        """A card stored as it is, next to any other open one (an old save may hold more than one)."""
        offer_id = ea.new_offer_id()
        result = ea.prepare_offer(self.state(), self.proposal(purpose, npc_id, amount, **extra), offer_id=offer_id,
                                  campaign_id="c", actor_id="player", turn_index=self.world["flags"]["turn_index"])
        self.assertEqual(result.status, "prepared", result.public_message)
        self.world["flags"].setdefault("economic_offers", {})[offer_id] = dataclasses.asdict(result.offer)
        return offer_id

    def panel(self, purpose: str, npc_id: str, amount: int | None = None, **extra) -> ea.PrepareResult:
        return ea.prepare_from_panel(self.state(), self.proposal(purpose, npc_id, amount, **extra), campaign_id="c",
                                     actor_id="player", turn_index=self.world["flags"]["turn_index"])

    def status(self, offer_id: str) -> str:
        return self.world["flags"]["economic_offers"][offer_id]["status"]

    def prepared(self) -> list[dict]:
        return [data for data in ea.offer_records(self.world).values() if data["status"] == "prepared"]

    def confirm(self, offer_id: str) -> ea.EconomicResolution:
        data = self.world["flags"]["economic_offers"][offer_id]
        self.actions += 1
        action = f"confirm-{self.actions}"
        with resolution_action_scope(action, "session"):
            return ea.confirm_offer(self.state(), offer_id=offer_id,
                                    confirmation_digest=data["confirmation_digest"],
                                    operation_id=f"offer:{action}", check=lambda skill, dc: "BAŞARILI")

    def ledger_ops(self) -> list[dict]:
        return list(self.world["flags"].get("economic_ledger", {}).get("operations", {}).values())

    def advance_turns(self, count: int) -> None:
        self.world["flags"]["turn_index"] += count

    def next_day(self) -> None:
        self.world["campaign_time"]["elapsed_seconds"] += DAY


class ADeclineIsKeptPerPart(DeclineFixture):
    def test_a_decline_cancels_open_cards_of_that_part_to_that_person_only(self):
        gift_osman, tip_marek = self.prepare("gift", "osman", 5), self.prepare("tip", "barman", 3)
        tip_osman = self.prepare("tip", "osman", 2)
        write = ea.record_decline(self.world, "osman", "gift", 5, day=0, turn=3)
        self.assertEqual((write.status, write.cancelled), ("written", 1))
        self.assertEqual(self.status(gift_osman), "cancelled")
        self.assertEqual(self.status(tip_marek), "prepared")
        self.assertEqual(self.status(tip_osman), "prepared")
        self.assertEqual(self.world["flags"]["money_declined"],
                         {"osman": {"gift": {"amount_cp": 5, "day": 0, "turn": 3}}})

    def test_while_declined_no_card_of_that_part_opens(self):
        ea.record_decline(self.world, "osman", "tip", 5, day=0, turn=3)
        result = self.panel("tip", "osman", 5)
        self.assertEqual((result.status, result.reason_code), ("refused", "npc_declined"))
        self.assertIsNone(result.offer)
        self.assertEqual(result.public_message, "Osman az önce parayı geri çevirdi.")
        self.assertEqual(self.prepared(), [])
        gift = self.panel("gift", "osman", 5)
        self.assertEqual(gift.status, "prepared", gift.public_message)  # a tip decline is not a gift decline

    def test_a_tip_decline_never_stops_a_room_card(self):
        ea.record_decline(self.world, "barman", "tip", 2, day=0, turn=3)
        room = self.panel("room", "barman")
        self.assertEqual(room.status, "prepared", room.public_message)
        [card] = self.prepared()
        self.assertEqual(card["proposal"]["purpose"], "room")

    def test_a_room_decline_cancels_and_blocks_the_room_card(self):
        room = self.prepare("room", "barman")
        write = ea.record_decline(self.world, "barman", "room", 50, day=0, turn=3)
        self.assertEqual((write.status, write.cancelled), ("written", 1))
        self.assertEqual(self.status(room), "cancelled")
        again = self.panel("room", "barman")
        self.assertEqual((again.status, again.reason_code, again.public_message),
                         ("refused", "npc_declined", "Marek az önce parayı geri çevirdi."))
        self.assertEqual(self.prepared(), [])

    def assert_room_paid_without_the_tip(self, offer_id: str) -> None:
        purse, barman = self.world["currency"]["player"], self.world["currency"]["barman"]
        resolution = self.confirm(offer_id)
        self.assertEqual((resolution.status, resolution.net_debit_cp), ("applied", 50))
        self.assertEqual([(refusal.line_id, refusal.reason_code) for refusal in resolution.refusals],
                         [("tip:1", "npc_declined")])
        self.assertIn("Bahşiş geçmedi; kesende kaldı.", resolution.public_summary)
        self.assertEqual((self.world["currency"]["player"], self.world["currency"]["barman"]),
                         (purse - 50, barman))  # the declined tip never reaches the barman

    def test_a_tip_decline_lets_a_room_card_with_a_tip_open_and_drops_only_the_tip(self):
        ea.record_decline(self.world, "barman", "tip", 2, day=0, turn=3)
        room = self.panel("room", "barman", tip_cp=1)
        self.assertEqual(room.status, "prepared", room.public_message)
        self.assertEqual([line.kind for line in room.offer.lines], ["room", "tip"])
        self.assertEqual({(d.line_id, d.status, d.reason_code) for d in room.offer.acceptance.line_decisions},
                         {("room:0", "accepted", "engine_accepts"), ("tip:1", "refused", "npc_declined")})
        self.assert_room_paid_without_the_tip(room.offer.offer_id)

    def test_a_tip_decline_keeps_an_open_room_card_and_its_confirm_pays_no_tip(self):
        room = self.prepare("room", "barman", tip_cp=1)
        write = ea.record_decline(self.world, "barman", "tip", 1, day=0, turn=3)
        self.assertEqual((write.status, write.cancelled), ("written", 0))
        self.assertEqual(self.status(room), "prepared")
        self.assert_room_paid_without_the_tip(room)

    def test_a_room_or_unclear_decline_still_closes_a_room_card_with_a_tip(self):
        for part in ("room", "*"):
            self.world["flags"].pop("money_declined", None)
            room = self.prepare("room", "barman", tip_cp=1)
            write = ea.record_decline(self.world, "barman", part, 50, day=0, turn=3)
            self.assertEqual((write.status, write.cancelled, self.status(room)), ("written", 1, "cancelled"), part)

    def test_a_tip_decline_stops_a_room_and_tip_card_that_goes_only_as_a_whole(self):
        whole = self.prepare("room", "barman", tip_cp=1, dependency="all_or_none")
        write = ea.record_decline(self.world, "barman", "tip", 1, day=0, turn=3)
        self.assertEqual((write.cancelled, self.status(whole)), (1, "cancelled"))
        again = self.panel("room", "barman", tip_cp=1, dependency="all_or_none")
        self.assertEqual((again.status, again.reason_code, again.public_message),
                         ("refused", "npc_declined", "Marek az önce parayı geri çevirdi."))
        self.assertEqual(self.panel("room", "barman").status, "prepared")  # the room alone still opens

    def test_an_unclear_decline_blocks_every_part_until_that_part_is_taken(self):
        gift, tip, room = self.prepare("gift", "osman", 5), self.prepare("tip", "osman", 2), \
            self.prepare("room", "barman")
        write = ea.record_decline(self.world, "osman", "*", 5, day=0, turn=3)
        self.assertEqual((write.status, write.cancelled), ("written", 2))
        self.assertEqual((self.status(gift), self.status(tip), self.status(room)),
                         ("cancelled", "cancelled", "prepared"))
        for part in ("tip", "gift", "room", "goods:bira"):
            self.assertTrue(ea.declined(self.world, "osman", part, day=0), part)
        ea.clear_decline(self.world, "osman", "tip")
        self.assertFalse(ea.declined(self.world, "osman", "tip", day=0))
        self.assertTrue(ea.declined(self.world, "osman", "gift", day=0))
        self.assertTrue(ea.declined(self.world, "osman", "goods:bira", day=0))
        self.assertEqual(self.world["flags"]["money_declined"]["osman"]["*"]["taken"], ["tip"])
        self.assertEqual(self.panel("tip", "osman", 2).status, "prepared")
        refused = self.panel("gift", "osman", 5)
        self.assertEqual((refused.status, refused.reason_code), ("refused", "npc_declined"))
        self.assertFalse(ea.declined(self.world, "barman", "gift", day=0))

    def test_clearing_a_named_part_lifts_only_that_part(self):
        ea.record_decline(self.world, "osman", "gift", 5, day=0, turn=3)
        ea.record_decline(self.world, "osman", "tip", 2, day=0, turn=3)
        ea.clear_decline(self.world, "osman", "gift")
        self.assertFalse(ea.declined(self.world, "osman", "gift", day=0))
        self.assertTrue(ea.declined(self.world, "osman", "tip", day=0))
        ea.clear_decline(self.world, "osman", "tip")
        self.assertEqual(self.world["flags"]["money_declined"], {})

    def test_a_decline_holds_after_three_turns_and_ends_with_the_day(self):
        ea.record_decline(self.world, "osman", "gift", 5, day=0, turn=3)
        self.advance_turns(3)
        self.assertTrue(ea.declined(self.world, "osman", "gift", day=0))
        self.assertEqual(self.panel("gift", "osman", 5).reason_code, "npc_declined")
        self.assertFalse(ea.declined(self.world, "osman", "gift", day=1))

    def test_cards_cancelled_by_a_decline_do_not_return_with_the_day(self):
        gift = self.prepare("gift", "osman", 5)
        ea.record_decline(self.world, "osman", "gift", 5, day=ea.game_day(self.world), turn=3)
        self.next_day()
        self.assertEqual(ea.game_day(self.world), 1)
        self.assertEqual(self.status(gift), "cancelled")
        fresh = self.panel("gift", "osman", 5)
        self.assertEqual(fresh.status, "prepared", fresh.public_message)
        self.assertEqual(self.status(gift), "cancelled")
        self.assertEqual([data["offer_id"] for data in self.prepared()], [fresh.offer.offer_id])

    def test_the_game_day_is_the_clock_in_whole_days(self):
        self.world["campaign_time"]["elapsed_seconds"] = 2 * DAY + 5
        self.assertEqual(ea.game_day(self.world), 2)
        self.assertEqual(ea.game_day({}), 0)

    def test_a_guard_holding_the_player_still_takes_the_bribe_path(self):
        self.world["npcs"].append({"id": "guard", "name": "Çavuş Hale", "role": "Muhafız", "location": self.here,
                                   "current_hp": 10})
        self.world["flags"].setdefault("deeds", []).append(
            {"kind": "theft", "at": 120, "location": self.here, "text": "Tezgâhtan kese çalındı",
             "described": ["guard"], "witnesses": [], "told": [], "heard": [], "seen_near": [],
             "hold": {"guard": "guard", "place": self.here, "turn": 2, "arrest": True}})
        ea.record_decline(self.world, "guard", "gift", 5, day=0, turn=3)
        result = ea.prepare_offer(self.state(), self.proposal("gift", "guard", 150), offer_id="bribe",
                                  campaign_id="c", actor_id="player", turn_index=3)
        self.assertEqual(result.status, "prepared", result.public_message)
        self.assertIsNotNone(result.offer.acceptance.check)


class TheDeclineCap(DeclineFixture):
    def test_the_cap_drops_earlier_days_first_and_never_todays_silently(self):
        for index in range(31):
            ea.record_decline(self.world, f"npc-{index:02d}", "gift", 1, day=0, turn=index)
        ea.record_decline(self.world, "today", "tip", 1, day=1, turn=40)
        write = ea.record_decline(self.world, "newcomer", "gift", 1, day=1, turn=41)
        self.assertEqual(write.status, "written")
        records = self.world["flags"]["money_declined"]
        self.assertEqual(len(records), ea.DECLINE_CAP)
        self.assertNotIn("npc-00", records)  # the oldest of an earlier day went
        self.assertIn("today", records)
        self.assertIn("npc-01", records)
        self.assertTrue(ea.declined(self.world, "newcomer", "gift", day=1))

        self.world["flags"]["money_declined"] = {}
        for index in range(ea.DECLINE_CAP):
            ea.record_decline(self.world, f"npc-{index:02d}", "gift", 1, day=1, turn=index)
        gift = self.prepare("gift", "osman", 5)
        with self.assertLogs("economic_actions", "WARNING") as logged:
            full = ea.record_decline(self.world, "osman", "gift", 5, day=1, turn=50)
        self.assertEqual(full.status, "decline_cap_full")
        self.assertIn("decline_cap_full", "\n".join(logged.output))
        self.assertEqual(len(self.world["flags"]["money_declined"]), ea.DECLINE_CAP)
        self.assertNotIn("osman", self.world["flags"]["money_declined"])
        self.assertTrue(ea.declined(self.world, "npc-00", "gift", day=1))
        # A full record still never lets an open card of the declined part charge later.
        self.assertEqual((full.cancelled, self.status(gift)), (1, "cancelled"))

    def test_an_unwritten_tip_decline_closes_a_room_card_carrying_the_tip(self):
        for index in range(ea.DECLINE_CAP):
            ea.record_decline(self.world, f"npc-{index:02d}", "gift", 1, day=0, turn=index)
        room = self.prepare("room", "barman", tip_cp=1)
        with self.assertLogs("economic_actions", "WARNING"):
            full = ea.record_decline(self.world, "barman", "tip", 1, day=0, turn=50)
        # Nothing is on record to refuse the tip at confirmation, so the card carrying it does not stay open.
        self.assertEqual((full.status, full.cancelled, self.status(room)), ("decline_cap_full", 1, "cancelled"))

    def test_an_overfull_record_never_grows_past_what_ended_rows_free(self):
        rows = {f"npc-{index:02d}": {"gift": {"amount_cp": 1, "day": 1, "turn": index}} for index in range(33)}
        rows["npc-00"]["gift"]["day"] = 0
        self.world["flags"]["money_declined"] = rows
        with self.assertLogs("economic_actions", "WARNING"):
            write = ea.record_decline(self.world, "osman", "gift", 5, day=1, turn=60)
        self.assertEqual(write.status, "decline_cap_full")
        self.assertEqual(len(self.world["flags"]["money_declined"]), 33)  # nothing dropped for a write that failed

    def test_a_known_npc_writes_another_part_even_when_the_cap_is_full(self):
        for index in range(ea.DECLINE_CAP):
            ea.record_decline(self.world, f"npc-{index:02d}", "gift", 1, day=0, turn=index)
        write = ea.record_decline(self.world, "npc-00", "tip", 1, day=0, turn=60)
        self.assertEqual(write.status, "written")
        self.assertTrue(ea.declined(self.world, "npc-00", "tip", day=0))


class TheLedgerCarriesLabelAndPayee(DeclineFixture):
    def test_new_ledger_operations_carry_label_and_payee(self):
        self.confirm(self.prepare("room", "barman"))
        [op] = self.ledger_ops()
        self.assertEqual((op["label"], op["payee_id"]), ("Oda (bir gece)", "barman"))

    def test_a_refused_confirm_also_carries_label_and_payee(self):
        gift = self.prepare("gift", "osman", 5)
        self.world["currency"]["player"] = 0
        resolution = self.confirm(gift)
        self.assertEqual((resolution.status, resolution.reason_code), ("refused", "no_money"))
        [op] = self.ledger_ops()
        self.assertEqual((op["label"], op["payee_id"], op["net_debit_cp"]), ("Hediye", "osman", 0))

    def test_recent_payments_lists_money_paid_newest_first(self):
        for purpose, npc_id, amount in (("gift", "osman", 5), ("tip", "barman", 3), ("room", "barman", None),
                                        ("gift", "osman", 7)):
            self.assertEqual(self.confirm(self.prepare(purpose, npc_id, amount)).status, "applied")
            self.advance_turns(1)
        refused = self.prepare("gift", "osman", 9)
        purse = self.world["currency"]["player"]
        self.world["currency"]["player"] = 0
        self.assertEqual(self.confirm(refused).status, "refused")
        self.world["currency"]["player"] = purse
        self.assertEqual(ea.npc_gift(self.state(), npc_id="osman", amount_cp=4).status, "applied")
        self.assertEqual(ea.recent_payments(self.world), [
            {"label": "Hediye", "amount_cp": 7, "payee_id": "osman", "turn_index": 6},
            {"label": "Oda (bir gece)", "amount_cp": 50, "payee_id": "barman", "turn_index": 5},
            {"label": "Bahşiş", "amount_cp": 3, "payee_id": "barman", "turn_index": 4},
        ])
        self.assertEqual(ea.recent_payments(self.world, payee_id="osman"), [
            {"label": "Hediye", "amount_cp": 7, "payee_id": "osman", "turn_index": 6},
            {"label": "Hediye", "amount_cp": 5, "payee_id": "osman", "turn_index": 3},
        ])
        self.assertEqual(ea.recent_payments(self.world, limit=1, payee_id="barman"), [
            {"label": "Oda (bir gece)", "amount_cp": 50, "payee_id": "barman", "turn_index": 5},
        ])
        self.assertEqual(ea.recent_payments({}), [])

    def test_an_old_operation_without_label_is_listed_without_one(self):
        self.world["flags"]["economic_ledger"] = {"operations": {
            "old": {"offer_id": "x", "purpose": "gift", "net_debit_cp": 6, "turn_index": 1}}}
        self.assertEqual(ea.recent_payments(self.world),
                         [{"label": None, "amount_cp": 6, "payee_id": None, "turn_index": 1}])
        self.assertEqual(ea.recent_payments(self.world, payee_id="osman"), [])


class BadRowsAreRepairedAndNamed(DeclineFixture):
    def test_bad_decline_rows_are_repaired_and_named(self):
        good = {"amount_cp": 5, "day": 0, "turn": 3}
        self.world["flags"]["money_declined"] = {
            "x": "bad", "osman": {"gift": dict(good), "nope": dict(good), "tip": {"amount_cp": -1, "day": 0,
                                                                                 "turn": 1}},
            "barman": {"*": {**good, "taken": ["tip", 7]}}, "": {"gift": dict(good)}}
        with self.assertLogs("economic_actions", "WARNING"):
            dropped = ea.repair_declines(self.world)
        self.assertEqual(sorted(dropped), sorted(["money_declined.x", "money_declined.osman.nope",
                                                  "money_declined.osman.tip", "money_declined.barman.*.taken",
                                                  "money_declined."]))
        self.assertEqual(self.world["flags"]["money_declined"],
                         {"osman": {"gift": good}, "barman": {"*": {**good, "taken": []}}})
        self.assertTrue(ea.declined(self.world, "barman", "tip", day=0))  # a bad taken list blocks more, not less
        self.assertEqual(ea.repair_declines(self.world), [])

        self.world["flags"]["money_declined"] = "not a table"
        with self.assertLogs("economic_actions", "WARNING"):
            self.assertEqual(ea.repair_declines(self.world), ["money_declined"])
        self.assertEqual(self.world["flags"]["money_declined"], {})

    def test_forty_rows_go_down_to_thirty_two_earlier_days_first(self):
        rows = {f"old-{index:02d}": {"gift": {"amount_cp": 1, "day": 0, "turn": index}} for index in range(10)}
        rows.update({f"new-{index:02d}": {"gift": {"amount_cp": 1, "day": 1, "turn": 100 + index}}
                     for index in range(30)})
        self.world["flags"]["money_declined"] = rows
        self.world["campaign_time"]["elapsed_seconds"] = DAY + 10
        with self.assertLogs("economic_actions", "WARNING"):
            dropped = ea.repair_declines(self.world)
        self.assertEqual(dropped, [f"money_declined.old-{index:02d}" for index in range(8)])
        kept = self.world["flags"]["money_declined"]
        self.assertEqual(len(kept), ea.DECLINE_CAP)
        self.assertTrue(all(f"new-{index:02d}" in kept for index in range(30)))

        self.world["flags"]["money_declined"] = {
            f"new-{index:02d}": {"gift": {"amount_cp": 1, "day": 1, "turn": 100 + index}} for index in range(40)}
        with self.assertLogs("economic_actions", "WARNING"):
            dropped = ea.repair_declines(self.world)
        self.assertEqual(dropped, [f"money_declined.new-{index:02d}" for index in range(8)])

    def test_bad_ledger_labels_are_dropped_and_named_and_the_operation_stays(self):
        self.world["flags"]["economic_ledger"] = {"operations": {
            "a": {"offer_id": "x", "purpose": "gift", "net_debit_cp": 6, "turn_index": 1, "label": 12,
                  "payee_id": "osman"},
            "b": {"offer_id": "y", "purpose": "tip", "net_debit_cp": 2, "turn_index": 2, "label": "B" * 41,
                  "payee_id": ["osman"]},
            "c": {"offer_id": "z", "purpose": "tip", "net_debit_cp": 2, "turn_index": 2, "label": "Bahşiş",
                  "payee_id": "barman"}}}
        with self.assertLogs("economic_actions", "WARNING"):
            dropped = ea.repair_ledger_labels(self.world)
        self.assertEqual(dropped, ["economic_ledger.operations.a.label", "economic_ledger.operations.b.label",
                                   "economic_ledger.operations.b.payee_id"])
        operations = self.world["flags"]["economic_ledger"]["operations"]
        self.assertEqual(set(operations), {"a", "b", "c"})
        self.assertEqual(operations["a"], {"offer_id": "x", "purpose": "gift", "net_debit_cp": 6, "turn_index": 1,
                                           "payee_id": "osman"})
        self.assertEqual(operations["c"]["label"], "Bahşiş")
        self.assertEqual(ea.repair_ledger_labels(self.world), [])
        self.assertEqual(ea.repair_ledger_labels({}), [])


if __name__ == "__main__":
    unittest.main()
