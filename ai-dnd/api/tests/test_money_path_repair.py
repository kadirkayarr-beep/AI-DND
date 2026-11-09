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
    def purchase(self, line, *, person="barman", coin=0, deal=None):
        self.s._front_coin = coin
        self.s._front_economic_front = {"kind": "speak_to", "person_id": person, "deal": deal or "none"}
        return self.s._front_economic_offer({**PURCHASE, "id": person}, line)

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


if __name__ == "__main__":
    import unittest
    unittest.main()
