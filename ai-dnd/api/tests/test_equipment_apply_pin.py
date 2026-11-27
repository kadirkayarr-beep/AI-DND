"""D-501 characterization (debt-zero G2.9): what `equipment_economy._apply` does for each operation, pinned before it
is split into one function per operation. Coin, item, receipt (the one atomic text) and Undo (a refused command leaves
the live world as it was). Every number here is what the code did before the split."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import game
import equipment_economy as economy

ATOMIC = "Eşya işlemi Python tarafından atomik olarak tamamlandı."
# one wrong argument list per operation: the arity of every branch is part of the contract
WRONG_ARITY = {
    "market": ["x"], "request": ["a"], "work": [], "talk": ["a"], "loot": ["a"], "list": ["x"], "place": ["a"],
    "mark": ["a"], "drop": [], "take": [], "equip": ["a"], "unequip": [], "give": ["a"], "receive": ["a"],
    "buy": ["a"], "sell": [], "reward": [], "explode": [],
}


class EquipmentApplyPin(unittest.TestCase):
    def setUp(self):
        self.s = game.create_session()
        self.w = self.s.world_state
        self.w["npcs"] = [{"id": "vendor", "name": "Mira", "location": self.w["location"], "current_hp": 10,
                           "inventory": ["Hançer"]}]
        self.w["shops"] = [{"id": "shop", "location": self.w["location"], "shopkeeper_id": "vendor"}]
        self.w["currency"] = {"player": 5000, "vendor": 5000}
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            self.assertTrue(self.s.run_player_turn("/item list")["action_result"]["success"])
        self.sword = next(i for i in self.w["inventory"] if i["name"] == "Kılıç")["item_id"]
        self.dagger = self.w["npcs"][0]["inventory"][0]["item_id"]
        self.w["shops"][0].update(item_offers_cp={self.dagger: 200}, buys_equipment=True)

    def apply(self, operation, *args):
        return economy._apply(self.w, operation, list(args))

    def refused(self, reason, operation, *args):
        before = copy.deepcopy(self.w)
        with self.assertRaises(economy.EquipmentError) as caught:
            economy._apply(copy.deepcopy(self.w), operation, list(args))
        self.assertEqual(str(caught.exception), reason)
        self.assertEqual(self.w, before)  # the live world is never the one a refused command wrote to

    def test_every_operation_keeps_its_own_arity(self):
        for operation, args in WRONG_ARITY.items():
            with self.subTest(operation=operation):
                self.refused("invalid_item_command", operation, *args)

    def test_list_reads_the_purse_and_the_counter_and_changes_nothing(self):
        before = copy.deepcopy(self.w)
        text = self.apply("list")
        self.assertIn("Bakiye: 5000 CP", text)
        self.assertIn(f"/item buy {self.dagger} shop", text)
        self.assertEqual(self.w, before)

    def test_buy_pays_the_vendor_moves_the_item_and_spends_the_offer(self):
        self.assertEqual(self.apply("buy", self.dagger, "shop"), ATOMIC)
        self.assertEqual(self.w["currency"], {"player": 4800, "vendor": 5200})
        self.assertIn(self.dagger, [i["item_id"] for i in self.w["inventory"]])
        self.assertEqual(self.w["npcs"][0]["inventory"], [])
        self.assertNotIn(self.dagger, self.w["shops"][0]["item_offers_cp"])
        self.refused("item_not_owned", "buy", self.dagger, "shop")

    def test_buy_without_funds_or_offer_refuses_and_keeps_the_world(self):
        self.w["currency"]["player"] = 199
        self.refused("insufficient_funds", "buy", self.dagger, "shop")
        self.w["currency"]["player"] = 5000
        self.w["shops"][0]["item_offers_cp"] = {}
        self.refused("stock_or_price_unavailable", "buy", self.dagger, "shop")

    def test_sell_pays_half_and_needs_a_merchant_who_buys(self):
        self.apply("buy", self.dagger, "shop")
        self.assertEqual(self.apply("sell", self.dagger, "shop"), ATOMIC)
        self.assertEqual(self.w["currency"], {"player": 4900, "vendor": 5100})
        self.assertEqual(self.w["npcs"][0]["inventory"][0]["item_id"], self.dagger)
        self.w["shops"][0]["buys_equipment"] = False
        self.refused("merchant_acceptance_required", "sell", self.sword, "shop")

    def test_drop_and_take_move_the_item_between_the_pack_and_the_ground(self):
        self.assertEqual(self.apply("drop", self.sword), ATOMIC)
        ground = self.w["ground_items_by_location"][self.w["location"]]
        self.assertEqual([i["item_id"] for i in ground], [self.sword])
        self.assertNotIn(self.sword, [i["item_id"] for i in self.w["inventory"]])
        self.assertEqual(self.apply("take", self.sword), ATOMIC)
        self.assertIn(self.sword, [i["item_id"] for i in self.w["inventory"]])
        self.refused("item_not_owned", "take", self.sword)

    def test_equip_and_unequip_fill_and_empty_the_hand(self):
        self.apply("unequip", "main_hand")
        self.assertIsNone(self.w["equipment"]["main_hand"])
        self.assertEqual(self.apply("equip", self.sword, "main_hand"), ATOMIC)
        self.assertEqual(self.w["equipment"]["main_hand"], self.sword)
        self.refused("hand_occupied", "equip", self.sword, "main_hand")
        self.refused("equipment_unknown", "unequip", "head")

    def test_give_and_receive_need_the_persons_consent(self):
        self.refused("npc_consent_required", "give", self.sword, "vendor")
        self.refused("npc_consent_required", "receive", self.dagger, "vendor")
        self.refused("item_not_owned", "receive", "longsword", "vendor")

    def test_reward_pays_once_and_moves_the_items(self):
        self.w["quests"] = [{"quest_id": "fixture", "status": "completed"}]
        self.w["item_rewards"] = {"fixture": {"source_npc_id": "vendor", "item_ids": [self.dagger],
                                              "currency_cp": 300}}
        self.assertEqual(self.apply("reward", "fixture"), ATOMIC)
        self.assertEqual(self.w["currency"], {"player": 5300, "vendor": 4700})
        self.assertEqual(self.w["npcs"][0]["inventory"], [])
        self.assertEqual(self.w["claimed_item_rewards"], ["fixture"])
        self.refused("reward_already_claimed", "reward", "fixture")
        self.refused("quest_not_completed", "reward", "unknown")

    def test_surface_commands_need_a_visible_surface(self):
        self.refused("surface_not_available", "place", self.sword, "no_such_surface")
        self.refused("surface_not_available", "mark", "no_such_surface", "note")


if __name__ == "__main__":
    unittest.main()
