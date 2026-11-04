"""What held-out coin means this turn: one pure decision, the model's deal first, structure second, never a gift."""
import copy
import unittest

import bold_acts
from money_owner import CoinDecision, Deal, decide, read_deal

LISTED = {"goods": [{"id": "bira", "name": "bira"}, {"id": "sarap", "name": "şarap"},
                    {"id": "yemek", "name": "tabak yemek"}]}
DEALS = (Deal("goods", "bira", False), Deal("goods", "bira", True), Deal("room", None, False),
         Deal("tip", None, False), Deal("gift", None, False), Deal("paid_before", None, False))


def tavern(purse=100):
    return {"location": "inn",
            "npcs": [{"id": "barman", "name": "Marek", "role": "Barmen", "location": "inn"},
                     {"id": "osman", "name": "Osman", "role": "Kervancı", "location": "inn"}],
            "currency": {"player": purse}, "flags": {"turn_index": 3}, "campaign_time": {"elapsed_seconds": 0}}


class MoneyOwnerDecision(unittest.TestCase):
    def setUp(self):
        self.w = tavern()
        self.barman, self.osman = self.w["npcs"]

    def decide(self, person, amount, deal, arrester=None):
        return decide(self.w, person=person, amount_cp=amount, deal=deal, arrester=arrester)

    def guard(self):
        guard = {"id": "guard", "name": "Bekçi", "role": "Muhafız", "location": "inn"}
        self.w["npcs"].append(guard)
        return guard

    def open_counter_offer(self, key="bira"):
        self.w["flags"]["counter_offer_v1"] = {"npc_id": "barman", "key": key, "seq": 0, "turn": 3}

    def test_coin_to_the_arresting_guard_is_a_bribe_whatever_the_deal(self):
        guard = self.guard()
        d = self.decide(guard, 5, Deal("tip", None, False), arrester=guard)
        self.assertEqual(d.kind, "bribe")
        self.assertEqual((d.npc_id, d.amount_cp, d.tip_cp, d.goods_key, d.place_id), ("guard", 5, 0, None, "inn"))
        for deal in (*DEALS, None):
            self.assertEqual(self.decide(guard, 5, deal, arrester=guard).kind, "bribe", deal)
            unnamed = self.decide(None, 5, deal, arrester=guard)
            self.assertEqual((unnamed.kind, unnamed.npc_id), ("bribe", "guard"), deal)

    def test_coin_for_someone_else_during_an_arrest_is_no_bribe(self):
        guard = self.guard()
        d = self.decide(self.barman, 50, Deal("room", None, False), arrester=guard)
        self.assertEqual((d.kind, d.npc_id, d.amount_cp), ("room", "barman", 50))
        self.assertEqual(self.decide(self.osman, 5, None, arrester=guard).kind, "unclear")

    def test_no_coin_to_the_arresting_guard_is_no_bribe(self):
        guard = self.guard()
        self.assertIsNone(self.decide(guard, 0, None, arrester=guard))
        self.assertEqual(self.decide(guard, 0, Deal("paid_before", None, False), arrester=guard).kind, "paid_before")

    def test_goods_with_keep_change_gets_its_tip_from_python(self):
        d = self.decide(self.barman, 5, Deal("goods", "bira", True))
        self.assertEqual((d.kind, d.goods_key, d.tip_cp, d.source), ("goods", "bira", 1, "model"))
        self.assertEqual((d.npc_id, d.amount_cp, d.place_id), ("barman", 5, "inn"))
        self.assertIsInstance(d, CoinDecision)

    def test_goods_without_keep_change_has_no_tip(self):
        d = self.decide(self.barman, 5, Deal("goods", "bira", False))
        self.assertEqual((d.kind, d.goods_key, d.amount_cp, d.tip_cp, d.source), ("goods", "bira", 5, 0, "model"))
        exact = self.decide(self.barman, 4, Deal("goods", "bira", True))
        self.assertEqual((exact.kind, exact.amount_cp, exact.tip_cp), ("goods", 4, 0))

    def test_goods_at_a_non_vendor_is_unclear_never_structure_never_gift(self):
        d = self.decide(self.osman, 5, Deal("goods", "bira", False))
        self.assertEqual((d.kind, d.source), ("unclear", "model"))
        self.assertEqual((d.npc_id, d.amount_cp, d.tip_cp, d.goods_key), ("osman", 5, 0, None))
        self.assertEqual((self.decide(None, 5, Deal("goods", "bira", False)).kind), "unclear")

    def test_goods_coin_below_the_price_or_beyond_the_purse_is_unclear(self):
        for amount in (3, 101):
            d = self.decide(self.barman, amount, Deal("goods", "bira", True))
            self.assertEqual((d.kind, d.source, d.tip_cp, d.goods_key), ("unclear", "model", 0, None), amount)

    def test_a_goods_deal_without_coin_is_an_offer_not_a_tender(self):
        d = self.decide(self.barman, 0, Deal("goods", "bira", False))
        self.assertEqual((d.kind, d.goods_key, d.amount_cp, d.tip_cp, d.source), ("goods", "bira", 0, 0, "model"))
        kept = self.decide(self.barman, 0, Deal("goods", "bira", True))
        self.assertEqual((kept.kind, kept.amount_cp, kept.tip_cp), ("goods", 0, 0))

    def test_a_room_deal_without_coin_is_a_room_card_without_tender(self):
        d = self.decide(self.barman, 0, Deal("room", None, False))
        self.assertEqual((d.kind, d.amount_cp, d.source), ("room", 0, "model"))
        self.assertEqual((d.npc_id, d.tip_cp, d.goods_key), ("barman", 0, None))

    def test_a_failed_model_deal_never_falls_to_structure(self):
        d = self.decide(self.barman, 50, Deal("goods", None, False))
        self.assertEqual((d.kind, d.source), ("unclear", "model"))
        self.open_counter_offer("bira")
        dear = self.decide(self.barman, 5, Deal("goods", "sarap", False))
        self.assertEqual((dear.kind, dear.source, dear.goods_key), ("unclear", "model", None))

    def test_a_tip_or_gift_deal_without_coin_is_unclear(self):
        for kind in ("tip", "gift"):
            d = self.decide(self.osman, 0, Deal(kind, None, False))
            self.assertEqual((d.kind, d.amount_cp, d.source), ("unclear", 0, "model"), kind)

    def test_room_needs_a_server_no_room_and_coin_between_price_and_purse(self):
        room = Deal("room", None, False)
        d = self.decide(self.barman, 50, room)
        self.assertEqual((d.kind, d.amount_cp, d.tip_cp, d.source), ("room", 50, 0, "model"))
        self.assertEqual(self.decide(self.barman, 100, room).kind, "room")
        for amount in (40, 101):
            self.assertEqual((self.decide(self.barman, amount, room).kind), "unclear", amount)
        self.assertEqual(self.decide(self.osman, 50, room).kind, "unclear")
        self.w["flags"]["inn_room"] = {"place": "inn", "until": 8 * 3600}
        for amount in (50, 0):
            held = self.decide(self.barman, amount, room)
            self.assertEqual((held.kind, held.source), ("unclear", "model"), amount)

    def test_a_room_held_elsewhere_or_run_out_is_no_room_here(self):
        room = Deal("room", None, False)
        self.w["flags"]["inn_room"] = {"place": "harbour", "until": 8 * 3600}
        self.assertEqual(self.decide(self.barman, 50, room).kind, "room")
        self.w["flags"]["inn_room"] = {"place": "inn", "until": 8 * 3600}
        self.w["campaign_time"]["elapsed_seconds"] = 8 * 3600
        self.assertEqual(self.decide(self.barman, 50, room).kind, "room")

    def test_gift_and_tip_need_coin_the_purse_holds(self):
        for kind in ("gift", "tip"):
            d = self.decide(self.osman, 100, Deal(kind, None, False))
            self.assertEqual((d.kind, d.npc_id, d.amount_cp, d.tip_cp, d.source), (kind, "osman", 100, 0, "model"))
            self.assertEqual(self.decide(self.osman, 1, Deal(kind, None, False)).kind, kind)
            self.assertEqual(self.decide(self.osman, 200, Deal(kind, None, False)).kind, "unclear", kind)

    def test_gift_and_tip_need_the_person_here(self):
        self.osman["location"] = "harbour"
        for kind in ("gift", "tip"):
            self.assertEqual(self.decide(self.osman, 5, Deal(kind, None, False)).kind, "unclear", kind)
            self.assertEqual(self.decide(None, 5, Deal(kind, None, False)).kind, "unclear", kind)

    def test_paid_before_opens_nothing_even_without_coin(self):
        d = self.decide(self.barman, 0, Deal("paid_before", None, False))
        self.assertEqual((d.kind, d.amount_cp, d.tip_cp, d.source), ("paid_before", 0, 0, "model"))
        self.assertEqual(self.decide(self.osman, 5, Deal("paid_before", None, False)).kind, "paid_before")
        self.assertEqual(self.decide(None, 500, Deal("paid_before", None, False)).npc_id, None)

    def test_no_deal_coin_for_the_open_counter_offer_is_its_tender(self):
        self.open_counter_offer("bira")
        d = self.decide(self.barman, 5, None)
        self.assertEqual((d.kind, d.goods_key, d.amount_cp, d.tip_cp, d.source),
                         ("goods", "bira", 5, 0, "structural"))
        self.assertEqual(d.npc_id, "barman")

    def test_no_deal_room_sized_coin_to_a_server_is_a_room(self):
        d = self.decide(self.barman, 50, None)
        self.assertEqual((d.kind, d.npc_id, d.amount_cp, d.tip_cp, d.goods_key, d.source),
                         ("room", "barman", 50, 0, None, "structural"))

    def test_no_deal_no_structure_is_unclear(self):
        d = self.decide(self.osman, 5, None)
        self.assertEqual((d.kind, d.npc_id, d.amount_cp, d.source), ("unclear", "osman", 5, "structural"))
        self.assertEqual(self.decide(self.barman, 5, None).kind, "unclear")
        self.assertEqual(self.decide(None, 5, None).kind, "unclear")
        self.open_counter_offer("bira")
        self.assertEqual(self.decide(self.barman, 3, None).kind, "unclear")
        self.assertEqual(self.decide(self.barman, 101, None).kind, "unclear")
        self.w["flags"]["inn_room"] = {"place": "inn", "until": 8 * 3600}
        self.w["flags"].pop("counter_offer_v1")
        self.assertEqual(self.decide(self.barman, 50, None).kind, "unclear")

    def test_a_stale_counter_offer_is_no_tender(self):
        self.open_counter_offer("bira")
        self.w["flags"]["turn_index"] = 6
        self.assertEqual(self.decide(self.barman, 5, None).kind, "unclear")

    def test_in_a_fight_every_deal_is_unclear(self):
        self.w["combat"] = {"active": True}
        self.open_counter_offer("bira")
        for deal in DEALS:
            for amount in (0, 5, 50):
                d = self.decide(self.barman, amount, deal)
                self.assertEqual((d.kind, d.source, d.amount_cp), ("unclear", "model", amount), (deal, amount))
        for amount in (5, 50):
            d = self.decide(self.barman, amount, None)
            self.assertEqual((d.kind, d.source), ("unclear", "structural"), amount)
        self.assertIsNone(self.decide(self.barman, 0, None))

    def test_no_coin_and_no_deal_is_no_decision(self):
        self.open_counter_offer("bira")
        for front in ({}, {"deal": "none"}, {"deal": "loan"}, None):
            self.assertIsNone(self.decide(self.barman, 0, read_deal(front, LISTED)), front)
        self.assertIsNone(self.decide(None, 0, None))
        self.assertIsNone(self.decide(self.barman, -5, None))
        self.assertIsNone(self.decide(self.barman, 0, Deal("none", None, False)))

    def test_a_none_deal_with_coin_is_read_as_no_deal(self):
        d = self.decide(self.barman, 50, Deal("none", None, False))
        self.assertEqual((d.kind, d.source), ("room", "structural"))
        self.assertEqual(self.decide(self.osman, 5, Deal("none", None, False)).source, "structural")

    def test_a_decision_writes_nothing(self):
        self.open_counter_offer("bira")
        guard = self.guard()
        before = copy.deepcopy(self.w)
        for person in (self.barman, self.osman, guard, None):
            for deal in (*DEALS, None):
                for amount in (0, 5, 50):
                    self.decide(person, amount, deal)
                    self.decide(person, amount, deal, arrester=guard)
        self.assertEqual(self.w, before)

    def test_read_deal_drops_unknown_kinds_and_unlisted_goods(self):
        self.assertIsNone(read_deal({"deal": "loan"}, LISTED))
        self.assertIsNone(read_deal({}, LISTED))
        self.assertEqual(read_deal({"deal": "goods", "deal_goods": "rakı"}, LISTED).goods_key, None)
        self.assertIsNone(read_deal({"deal": "none", "deal_goods": "bira"}, LISTED))
        self.assertIsNone(read_deal(None, LISTED))
        self.assertIsNone(read_deal({"deal": ["goods"]}, LISTED))
        self.assertEqual(read_deal({"deal": "goods", "deal_goods": "bira", "keep_change": True}, LISTED),
                         Deal("goods", "bira", True))
        self.assertEqual(read_deal({"deal": "goods", "deal_goods": "none"}, LISTED), Deal("goods", None, False))
        self.assertEqual(read_deal({"deal": "goods", "deal_goods": "bira"}, {}), Deal("goods", None, False))
        self.assertEqual(read_deal({"deal": "goods", "deal_goods": "bira", "keep_change": "true"}, LISTED),
                         Deal("goods", "bira", False))

    def test_read_deal_keeps_goods_and_change_only_on_a_goods_deal(self):
        for kind in ("room", "tip", "gift", "paid_before"):
            self.assertEqual(read_deal({"deal": kind, "deal_goods": "bira", "keep_change": True}, LISTED),
                             Deal(kind, None, False), kind)

    def test_room_price_is_fifty(self):
        self.assertEqual(bold_acts.room_price(self.w, self.barman), 50)
        self.assertEqual(bold_acts.room_price(self.w, None), 50)


if __name__ == "__main__":
    unittest.main()
