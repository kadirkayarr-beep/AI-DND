"""D-199: a counted starting line ("10 Dart", "5 Hançer") is that many weapons; its value and sale count them all."""
import unittest
from unittest.mock import patch

import equipment_economy as economy
import game
from api.tests.town_seed import fixed_town


class CountedBundleSaleTests(unittest.TestCase):
    def setUp(self):
        with fixed_town(self, 19901):
            self.s = game.create_session(seed=1)
        self.w = self.s.world_state
        self.w["npcs"] = [{"id": "vendor", "name": "Mira", "location": self.w["location"], "current_hp": 10,
                           "inventory": []}]
        self.w["shops"] = [{"id": "shop", "location": self.w["location"], "shopkeeper_id": "vendor",
                            "buys_equipment": True}]
        self.w["currency"] = {"player": 5000, "vendor": 5000}

    def run_item(self, text):
        with patch("game.ollama.chat", side_effect=AssertionError("Unexpected model call")):
            result = self.s.run_player_turn(text)
        self.assertEqual(result["model_calls"], 0)
        return result["action_result"]

    def test_counted_line_is_priced_per_weapon(self):
        for name, weapon_id, cp in (("10 Dart", "dart", 50), ("5 Cirit", "javelin", 250),
                                    ("5 Hançer", "dagger", 1000), ("2 Kısa Kılıç", "shortsword", 2000),
                                    ("2 Pala (Scimitar)", "scimitar", 5000), ("Hançer", "dagger", 200),
                                    ("1 Hançer", "dagger", 200)):
            with self.subTest(name=name):
                self.assertEqual(economy.price({"name": name, "weapon_id": weapon_id}), cp)

    def test_count_of_another_weapon_is_not_trusted(self):
        # The count vouches only for the weapon its own words name.
        self.assertEqual(economy.price({"name": "10 Dart", "weapon_id": "dagger"}), 200)

    def sell(self, name):
        self.w["inventory"].append(name)
        self.assertTrue(self.run_item("/item list")["success"])
        record = next(i for i in self.w["inventory"] if i["name"] == name)
        total = sum(self.w["currency"].values())
        self.assertTrue(self.run_item(f"/item sell {record['item_id']} shop")["success"])
        self.assertEqual(sum(self.w["currency"].values()), total)
        self.assertFalse(any(i["item_id"] == record["item_id"] for i in self.w["inventory"]))
        self.assertTrue(any(i["item_id"] == record["item_id"] for i in self.w["npcs"][0]["inventory"]))

    def test_selling_five_daggers_pays_half_of_five(self):
        self.sell("5 Hançer")
        self.assertEqual(self.w["currency"], {"player": 5500, "vendor": 4500})

    def test_selling_ten_darts_pays_half_of_ten(self):
        self.sell("10 Dart")
        self.assertEqual(self.w["currency"], {"player": 5025, "vendor": 4975})


if __name__ == "__main__":
    unittest.main()
