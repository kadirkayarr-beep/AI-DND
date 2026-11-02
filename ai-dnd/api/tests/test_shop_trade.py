"""One counter trade: price, purse, goods and stock change together or not at all; no model call."""
import copy
import unittest
from unittest.mock import patch

import bold_acts
import equipment_economy
import game
import shop_trade


class CounterTrade(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session()
        self.w = self.s.world_state
        self.w["npcs"] = [{"id": "barman", "name": "Marek", "role": "Barmen", "location": self.w["location"],
                           "current_hp": 10}]
        self.w["currency"] = {"player": 500}

    def buy(self, key="bira", count=1, seq=0, total=4):
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            result = self.s.run_player_turn(f"/item shop_buy barman {key} {count} {seq} {total}")
        self.assertEqual(result["model_calls"], 0)
        return result

    def unchanged(self, reason, **kwargs):
        before = copy.deepcopy(self.w)
        result = self.buy(**kwargs)
        self.assertFalse(result["action_result"]["success"], result["narration"])
        self.assertEqual(result["action_result"]["reason"], reason)
        self.assertEqual(self.w, before)
        return result

    def goods(self, name):
        return [item for item in self.w["inventory"] if isinstance(item, dict) and item.get("name") == name]

    def test_the_price_list_is_the_one_the_speaker_is_told(self):
        listed = {line["key"]: line["unit_cp"] for line in shop_trade.goods(self.w, self.w["npcs"][0])}
        self.assertEqual(listed, {key: price for key, _, price in shop_trade.PRICES})
        told = bold_acts.price_note(self.w["npcs"][0], "bira ne kadar")
        for key, label, price in shop_trade.PRICES:
            self.assertIn(f"{label} {price} bakır", told)

    def test_a_quote_reads_and_writes_nothing(self):
        before = copy.deepcopy(self.w)
        quote = shop_trade.quote(self.w, "barman", "bira", 2)
        self.assertEqual((quote["unit_cp"], quote["total_cp"], quote["purse_cp"], quote["seq"], quote["can_pay"]),
                         (4, 8, 500, 0, True))
        self.assertEqual(self.w, before)

    def test_coin_and_goods_change_together(self):
        result = self.buy(count=2, total=8)
        self.assertTrue(result["action_result"]["success"], result["narration"])
        self.assertEqual(self.w["currency"], {"player": 492, "barman": 8})
        beers = self.goods("Bira")
        self.assertEqual(len(beers), 2)
        self.assertEqual(len({beer["item_id"] for beer in beers}), 2)
        self.assertEqual(self.w["npcs"][0]["wares_v1"]["bira"]["stock"], shop_trade.DEFAULT_STOCK - 2)
        self.assertEqual(self.w["shop_trades_v1"]["seq"], 1)
        self.assertEqual(self.w["shop_trades_v1"]["ledger"][-1]["total_cp"], 8)
        self.assertIn("8 bakır", result["narration"])
        self.assertIn("2 bira", result["narration"])

    def test_the_whole_price_is_paid_with_no_change_made(self):
        self.w["currency"]["player"] = 30
        self.assertTrue(self.buy(key="yemek", total=30)["action_result"]["success"])
        self.assertEqual(self.w["currency"], {"player": 0, "barman": 30})
        self.assertEqual(len(self.goods("Tabak yemek")), 1)

    def test_gold_written_in_the_pack_pays(self):
        self.w["currency"] = {}
        self.w["inventory"].append("1 Altın")
        self.assertTrue(self.buy()["action_result"]["success"])
        self.assertEqual(self.w["currency"], {"player": 96, "barman": 4})

    def test_not_enough_coin_changes_nothing(self):
        self.w["currency"]["player"] = 3
        self.assertFalse(shop_trade.quote(self.w, "barman", "bira", 1)["can_pay"])
        self.unchanged("insufficient_funds")

    def test_a_stale_offer_changes_nothing(self):
        self.assertTrue(self.buy()["action_result"]["success"])
        self.unchanged("offer_stale")

    def test_a_changed_price_changes_nothing_and_gives_the_fresh_quote(self):
        self.w["npcs"][0]["price_cut_cp_v1"] = {"bira": 1}
        result = self.unchanged("price_changed", total=4)
        self.assertEqual(result["action_result"]["offer"]["total_cp"], 3)
        self.assertTrue(self.buy(total=3)["action_result"]["success"])
        self.assertEqual(self.w["currency"]["player"], 497)

    def test_bad_count_and_short_stock_change_nothing(self):
        self.unchanged("invalid_count", count=0, total=0)
        self.w["npcs"][0]["wares_v1"] = {"bira": {"stock": 1}}
        self.unchanged("out_of_stock", count=2, total=8)

    def test_an_absent_or_unknown_vendor_changes_nothing(self):
        self.w["npcs"][0]["location"] = "elsewhere"
        self.unchanged("npc_unavailable")
        self.w["npcs"][0]["location"] = self.w["location"]
        self.w["npcs"][0]["role"] = "Muhafız"
        self.unchanged("not_a_vendor")
        self.w["npcs"][0]["role"] = "Barmen"
        self.unchanged("goods_unknown", key="kilic")

    def test_a_failed_grant_after_payment_leaves_purse_and_stock(self):
        before = copy.deepcopy(self.w)
        with patch.object(equipment_economy, "grant_named_item", side_effect=equipment_economy.EquipmentError("boom")):
            result = self.buy()
        self.assertFalse(result["action_result"]["success"])
        self.assertEqual(self.w, before)

    def test_the_trade_ledger_stays_small(self):
        self.w["currency"]["player"] = 10_000
        self.w["npcs"][0]["wares_v1"] = {"bira": {"stock": 100}}
        for seq in range(shop_trade.LEDGER_CAP + 5):
            self.assertTrue(self.buy(seq=seq)["action_result"]["success"])
        self.assertEqual(len(self.w["shop_trades_v1"]["ledger"]), shop_trade.LEDGER_CAP)

    def test_a_vendor_is_one_who_serves(self):
        self.assertTrue(shop_trade.is_vendor(self.w, self.w["npcs"][0]))
        self.assertFalse(shop_trade.is_vendor(self.w, {"id": "x", "role": "Muhafız"}))
        self.assertTrue(shop_trade.is_priced("bira"))
        self.assertFalse(shop_trade.is_priced("kılıç"))


class WordsOpenTheCounter(CounterTrade):
    def turn(self, line, **kwargs):
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            return self.s.run_player_turn(line, **kwargs)

    def offered(self, result, key, total):
        outcome = result["action_result"]
        self.assertEqual((outcome["action"], outcome["status"]), ("shop_offer", "offer_open"), result["narration"])
        self.assertEqual(outcome["state_changes"], [])
        self.assertEqual((outcome["offer"]["key"], outcome["offer"]["total_cp"], outcome["offer"]["seq"]), (key, total, 0))
        self.assertEqual(result["model_calls"], 0)

    def test_asking_for_a_beer_opens_the_offer_and_moves_nothing(self):
        for mode in (None, "do", "say"):
            with self.subTest(mode=mode):
                self.setUp()
                before = copy.deepcopy(self.w)
                result = self.turn("bi bira alayım usta", interaction_mode=mode,
                                   **({"target_id": "barman"} if mode == "say" else {}))
                self.offered(result, "bira", 4)
                self.assertEqual(self.w["currency"], before["currency"])
                self.assertEqual(self.w["inventory"], before["inventory"])
                self.assertNotIn(shop_trade.KEY, self.w)

    def test_the_plate_the_speaker_names_opens_the_plate(self):
        self.offered(self.turn("ver bi tabak o zaman"), "yemek", 30)

    def test_a_good_named_with_its_softened_ending_opens_its_offer(self):
        for line, key, total in (("şarabı ver usta", "sarap", 20), ("yemeği getir", "yemek", 30),
                                 ("bi tabağı ver", "yemek", 30)):
            with self.subTest(line=line):
                self.setUp()
                self.offered(self.turn(line, interaction_mode="say", target_id="barman"), key, total)
        self.assertIsNone(shop_trade.priced_in("biraz bekle"))

    def test_a_market_shop_does_not_swallow_the_counter(self):
        self.w["shops"] = [{"id": "shop", "location": self.w["location"], "shopkeeper_id": "barman"}]
        self.offered(self.turn("bi bira satın alayım"), "bira", 4)

    def test_a_room_is_still_rented_with_its_own_price(self):
        result = self.turn("bi oda tutayım usta")
        self.assertEqual(result["action_result"]["action"], "lodging", result["narration"])
        self.assertEqual(self.w["currency"]["player"], 500 - bold_acts._ROOM_PRICE)


class WhatIsShownIsNotFree(CounterTrade):
    def shown(self):
        self.s.messages.append({"role": "assistant", "content": "Tezgâhın üstünde köpüklü bir bira duruyor, yanında bir anahtar."})

    def test_a_beer_on_the_counter_is_not_taken_for_nothing(self):
        import pocket
        self.shown()
        before = copy.deepcopy(self.w)
        self.assertIsNone(pocket.take_named(self.s, "tezgahtaki birayı alıyorum", "bira"))
        self.assertIsNone(pocket.take_named(self.s, "birayı kapıp alıyorum", ""))
        self.assertEqual(self.w["inventory"], before["inventory"])
        self.assertEqual(self.w["currency"], before["currency"])

    def test_a_plain_thing_on_the_counter_is_still_taken(self):
        import pocket
        self.shown()
        taken = pocket.take_named(self.s, "anahtarı alıyorum", "anahtar")
        self.assertIsNotNone(taken)
        self.assertIn("Anahtar", [item if isinstance(item, str) else item.get("name") for item in self.w["inventory"]])


class TypedLane(CounterTrade):
    def test_a_typed_line_never_reaches_the_word_matcher(self):
        before = copy.deepcopy(self.w)
        for line in ("/item ver bira barman", "/item bira getir 1 0 4", "/oda tutuyorum"):
            with self.subTest(line=line):
                self.assertIsNone(bold_acts.resolve(self.s, line))
                self.assertIsNone(bold_acts.resolve(self.s, line, ""))
                self.assertEqual(self.w, before)

    def test_a_typed_buy_takes_the_typed_lane_with_no_reading(self):
        with patch.object(bold_acts, "resolve", wraps=bold_acts.resolve) as heard:
            result = self.buy(count=2, total=8)
        self.assertTrue(result["action_result"]["success"], result["narration"])
        self.assertTrue(all(call.args[1].startswith("/") for call in heard.call_args_list))
        self.assertEqual(self.w["currency"]["player"], 492)


if __name__ == "__main__":
    unittest.main()
