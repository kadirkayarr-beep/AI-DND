"""Dilim 3 Task 27: the money path says why, and a purchase reading that the money owner decided is a room goes to
the room card. Nobody's purse moves here: every answer is a card, an offer or a reasoned no. No model call."""
from __future__ import annotations

import copy

import bold_acts
import item_use
import shop_trade
from api.tests.test_economic_room import Counter

PURCHASE = {"kind": "economic", "id": "barman", "purpose": "purchase", "valid": True}


class MoneyPathRepair(Counter):
    def purchase(self, line, *, person="barman", coin=0, deal=None, deal_goods=None, keep_change=False):
        self.s._front_coin = coin
        self.s._front_economic_front = {"kind": "speak_to", "person_id": person, "deal": deal or "none",
                                        "deal_goods": deal_goods or "none", "keep_change": keep_change}
        return self.s._front_economic_offer({**PURCHASE, "id": person, "keep_change": keep_change}, line)

    def refused(self, result, line, reason):
        self.assertEqual(result["narration"], line)
        self.assertEqual(result["action_result"]["reason_code"], reason)
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(self.prepared(), [])
        self.assertNotIn("counter_offer_v1", self.w["flags"])

    # fix round 1, (1): the reason is the engine's own fact, in order
    def test_p1_coin_below_the_beer_price_says_what_beer_costs(self):
        before = self.money()
        result = self.purchase("Marek'e 2 bakır verip bir bira alıyorum", coin=2, deal="goods", deal_goods="bira")
        self.refused(result, "Bira 4 bakır; uzattığın 2 bakır bunu karşılamıyor.", "coin_below_price")
        self.assertEqual(self.money(), before)

    def test_p2_coin_below_the_room_price_says_what_the_room_costs(self):
        before = self.money()
        result = self.purchase("30 bakıra bu gecelik odayı tutuyorum", coin=30, deal="room")
        self.refused(result, "Gecelik oda 50 bakır; uzattığın 30 bakır bunu karşılamıyor.", "coin_below_price")
        self.assertEqual(self.money(), before)

    def test_p3_a_room_already_held_here_is_said_so(self):
        self.w["flags"]["inn_room"] = {"place": self.here, "until": 999999999}
        before = self.money()
        result = self.purchase("Beş gümüşe bu gecelik odayı tutuyorum", coin=50, deal="room")
        self.refused(result, "Burada tuttuğun oda zaten duruyor.", "room_already_held")
        self.assertEqual(self.money(), before)

    # fix round 1, (6): keep-change is prepared only for an offer that opened
    def test_keep_change_with_goods_this_counter_does_not_sell_prepares_nothing(self):
        before = self.money()
        result = self.purchase("Bir peynir alayım, üstü kalsın", coin=20, keep_change=True)
        self.assertEqual(result["action_result"]["reason_code"], "not_sold_here")
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)

    # fix round 1, (4): a purchase line's reply never pays the player from the person's purse
    def test_a_reply_to_a_purchase_line_does_not_pay_the_player(self):
        guest = self.npc("guest")
        guest.update(name="Vobarin", role="Demirci")
        line = "60 altına bir kılıç almak istiyorum"
        self.purchase(line, person="guest", coin=6000)
        before = self.money()
        raw = {"kind": "give", "item": "kılıç", "amount_cp": 60}
        settled = self.s._settle_spoken_commitment(self.w, guest, line, raw, "Altmış bakır.")
        self.assertEqual(settled["moved"], 0)
        self.assertEqual(self.money(), before)

    def test_a_reply_that_pays_on_another_line_still_pays(self):
        guest = self.npc("guest")
        raw = {"kind": "give", "item": "", "amount_cp": 5}
        settled = self.s._settle_spoken_commitment(self.w, guest, "paramı ver hadi", raw, "Al, beş bakır.")
        self.assertEqual(settled["moved"], 5)

    # (a) the money owner's room decision under a purchase reading opens the room card, and only after its checks
    def test_purchase_reading_with_a_room_deal_opens_the_room_card(self):
        before = self.money()
        result = self.purchase("Beş gümüşü Marek'e verip bu gecelik odayı tutuyorum", coin=50, deal="room")
        self.assertEqual(result["action_result"]["action"], "lodging", result["narration"])
        self.assertEqual(result["action_result"]["status"], "offered")
        [offer] = self.prepared()
        self.assertEqual(offer["proposal"]["purpose"], "room")
        self.assertEqual(offer["proposal"]["tender_cp"], 50)
        self.assertEqual(self.money(), before)

    def test_purchase_reading_with_a_room_deal_the_purse_cannot_pay_opens_nothing_and_says_why(self):
        self.w["currency"]["player"] = 30
        before = self.money()
        result = self.purchase("Beş gümüşü Marek'e verip bu gecelik odayı tutuyorum", coin=50, deal="room")
        self.assertEqual(result["narration"], "Kesendeki para bunu karşılamıyor.")
        self.assertEqual(result["action_result"]["reason_code"], "purse_below_base")
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)

    # (b) an unclear decision says its reason, not "Bu şu an burada yok"
    def test_coin_beyond_the_purse_is_told_as_a_short_purse(self):
        before = self.money()
        result = self.purchase("Marek'e 100 altın veriyorum", coin=10000, deal="gift")
        self.assertEqual(result["narration"], "Kesendeki para bunu karşılamıyor.")
        self.assertEqual(result["action_result"]["reason_code"], "purse_below_base")
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)

    def test_goods_not_on_the_counter_are_told_with_what_is_sold(self):
        before = self.money()
        result = self.purchase("Bir kılıç almak istiyorum")
        self.assertEqual(result["narration"], "Burada bu satılık değil; bu tezgâhta bira, şarap, tabak yemek var.")
        self.assertEqual(result["action_result"]["reason_code"], "no_stock_or_service")
        self.assertFalse(result["action_result"]["success"])
        self.assertNotIn("counter_offer_v1", self.w["flags"])
        self.assertEqual(self.money(), before)

    # (c) said to someone here who sells nothing: the line is theirs to answer, no card refusal
    def test_purchase_said_to_someone_who_sells_nothing_goes_to_their_words(self):
        self.npc("guest").update(name="Vobarin", role="Demirci")
        before = self.money()
        result = self.purchase("60 altına bir kılıç almak istiyorum", person="guest", coin=6000)
        self.assertIsNone(result)
        self.assertEqual(self.prepared(), [])
        self.assertNotIn("counter_offer_v1", self.w["flags"])
        self.assertEqual(self.money(), before)


class MenuByPlaceKind(Counter):
    def setUp(self):
        super().setUp()
        self.w.setdefault("locations", {}).setdefault(self.here, {"id": self.here})["place_kind"] = "market"
        self.npc("barman").update(name="Özpil", role="Seyyar satıcı")

    def test_a_market_counter_sells_its_own_menu(self):
        listed = [line["key"] for line in shop_trade.goods(self.w, self.npc("barman"))]
        self.assertEqual(listed, ["elma", "ekmek", "peynir"])

    def test_an_inn_counter_keeps_the_drink_and_food_menu(self):
        self.w["locations"][self.here].pop("place_kind")
        listed = [line["key"] for line in shop_trade.goods(self.w, self.npc("barman"))]
        self.assertEqual(listed, ["bira", "sarap", "yemek"])

    def test_a_tavern_and_a_kind_with_no_row_sell_the_tavern_list(self):
        for kind in ("tavern", "smithy"):
            with self.subTest(kind=kind):
                self.w["locations"][self.here]["place_kind"] = kind
                self.assertEqual([line["key"] for line in shop_trade.goods(self.w, self.npc("barman"))],
                                 [key for key, _, _ in shop_trade.MENUS["tavern"]])

    def test_a_counter_sells_only_its_own_list(self):
        seller = self.npc("barman")
        self.assertTrue(shop_trade.sells(self.w, seller, "bir elma"))
        self.assertFalse(shop_trade.sells(self.w, seller, "bir bira"))
        self.w["locations"][self.here].pop("place_kind")
        self.assertFalse(shop_trade.sells(self.w, seller, "bir elma"))
        self.assertTrue(shop_trade.sells(self.w, seller, "bir bira"))
        self.assertFalse(shop_trade.sells(self.w, self.npc("guest"), "bir bira"))

    def test_a_market_purchase_rides_the_counter_and_the_eat_path(self):
        unit = shop_trade.quote(self.w, "barman", "ekmek", 1)["unit_cp"]
        line = shop_trade.commit(self.w, "barman", "ekmek", 1, 0, unit)
        self.assertIn("ekmek", line)
        self.assertEqual(self.w["currency"]["player"], 500 - unit)
        [bread] = [item for item in self.w["inventory"] if isinstance(item, dict) and item.get("name") == "Ekmek"]
        self.assertEqual(item_use.consume(self.w, bread["item_id"]).note, "Ekmek yendi")

    def test_beer_asked_at_the_market_is_a_reasoned_no(self):
        before = self.money()
        result = bold_acts.shop_offer(self.s, "Bir bira istiyorum", self.npc("barman"), requested=True)
        self.assertEqual(result["narration"], "Burada satılık bira yok; bu tezgâhta elma, ekmek, peynir var.")
        self.assertEqual(result["action_result"]["reason_code"], "not_sold_here")
        self.assertNotIn("counter_offer_v1", self.w["flags"])
        self.assertEqual(self.money(), before)

    def test_market_goods_asked_at_the_inn_are_a_reasoned_no(self):
        self.w["locations"][self.here].pop("place_kind")
        self.npc("barman").update(name="Marek", role="Barmen")
        before = copy.deepcopy(self.money())
        result = bold_acts.shop_offer(self.s, "Bir peynir istiyorum", self.npc("barman"), requested=True)
        self.assertEqual(result["narration"], "Burada satılık peynir yok; bu tezgâhta bira, şarap, tabak yemek var.")
        self.assertNotIn("counter_offer_v1", self.w["flags"])
        self.assertEqual(self.money(), before)


class MenuWordsAreNotNames(MenuByPlaceKind):
    """fix round 1, (2): a menu word counts only as a whole word with a case ending, never inside a name."""

    def test_names_and_longer_words_are_no_goods(self):
        for line in ("Rimerun Elmasaz ile konuştum", "Elmaçember'den bir şey almak istiyorum", "bir elmas yüzük",
                     "Vadi Tadı Peynir Evi'ne gidiyorum", "biraz bekle", "ekmekçi nerede"):
            with self.subTest(line=line):
                self.assertIsNone(shop_trade.priced_in(line))

    def test_the_goods_with_their_endings_still_read(self):
        for line, key in (("elmayı alayım", "elma"), ("Peynir istiyorum", "peynir"), ("bir ekmek", "ekmek"),
                          ("şarabı ver", "sarap"), ("yemeği getir", "yemek"), ("Bira alayım", "bira"),
                          ("biradan bir tane", "bira")):
            with self.subTest(line=line):
                self.assertEqual(shop_trade.priced_in(line)[0], key)

    def test_p5_a_surname_at_the_market_opens_no_apple_offer(self):
        before = self.money()
        self.s._front_coin = 0
        self.s._front_economic_front = {"kind": "speak_to", "person_id": "barman", "deal": "none"}
        result = self.s._front_economic_offer(PURCHASE, "Elmasaz'dan bir şey almak istiyorum")
        self.assertNotIn("counter_offer_v1", self.w["flags"])
        self.assertEqual(result["action_result"]["reason_code"], "no_stock_or_service")
        self.assertEqual(self.money(), before)

    def test_p6_a_surname_said_to_the_barman_is_no_order(self):
        self.w["locations"][self.here].pop("place_kind")
        self.npc("barman").update(name="Marek", role="Barmen")
        before = self.money()
        self.assertIsNone(bold_acts.shop_offer(self.s, "Elmaçember'e bir içki almak istiyorum", self.npc("barman"),
                                               requested=True))
        self.assertNotIn("counter_offer_v1", self.w["flags"])
        self.assertEqual(self.money(), before)


class SellsAtItsCallSites(MenuByPlaceKind):
    """fix round 1, (6): the three places that read a sale read it against the seller's own list."""

    def test_an_apple_on_the_ground_at_the_inn_is_picked_up(self):
        import pocket
        self.w["locations"][self.here].pop("place_kind")
        self.npc("barman").update(role="Barmen")
        self.w.setdefault("ground_items_by_location", {})[self.here] = [{"item_id": "item_elma", "name": "Elma"}]
        self.assertEqual(pocket._pick_up(self.s, "elma"), "Elma")

    def test_an_apple_at_the_market_is_bought_not_picked_up(self):
        import pocket
        self.w.setdefault("ground_items_by_location", {})[self.here] = [{"item_id": "item_elma", "name": "Elma"}]
        self.assertIsNone(pocket._pick_up(self.s, "elma"))

    def test_a_claimed_handover_is_a_sale_only_for_the_sellers_own_list(self):
        import pocket
        seller = self.npc("barman")
        self.assertTrue(pocket._a_sale(self.w, seller, {}, "elma", "elma"))
        self.assertFalse(pocket._a_sale(self.w, seller, {}, "bira", "bira"))

    def test_a_reply_naming_the_sellers_own_goods_pays_nothing(self):
        import town_knowledge
        seller = self.npc("barman")
        before = self.money()
        settled = town_knowledge.settle_reply(self.w, seller, "elmanın parasını ver", {"kind": "give", "amount_cp": 1},
                                              "Al.", accept_job=lambda thread: None)
        self.assertEqual(settled["moved"], 0)
        self.assertEqual(self.money(), before)


class OldOpenOfferOffTheMenu(MenuByPlaceKind):
    """fix round 1, (5): a saved open beer offer at a market stall is no price to haggle and raises nothing."""

    def test_an_old_beer_offer_at_the_market_is_not_haggled(self):
        import economic_actions
        import money_owner
        self.w["flags"]["counter_offer_v1"] = {"npc_id": "barman", "key": "bira", "seq": 0, "turn": 3}
        self.assertEqual([row for row in money_owner.price_negotiation_offers(self.w) if row["kind"] == "goods"], [])
        day = economic_actions.game_day(self.w)
        before = self.money()
        said = money_owner.haggle(self.s, self.npc("barman"), {"skill": "Persuasion", "result": "BAŞARILI"},
                                  negotiation={"offer_id": f"counter:barman:bira:0:3:{day}", "npc_id": "barman",
                                               "evidence_quote": "indirim"}, player_input="indirim yap")
        self.assertIsNone(said)
        self.assertEqual(self.money(), before)


if __name__ == "__main__":
    import unittest
    unittest.main()
