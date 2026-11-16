import unittest

import equipment_economy


def _world(**extra):
    return {
        "inventory": [
            {"item_id": "item_s1", "name": "Kalkan"},
            {"item_id": "item_m1", "name": "Gürz (Mace)"},
            {"item_id": "item_c1", "name": "Kutsal Sembol"},
        ],
        "equipment": {"main_hand": None, "off_hand": None},
        **extra,
    }


class PublicInventoryShieldTests(unittest.TestCase):
    def test_creation_shield_without_hand_entry_is_marked_equipped(self):
        labels = equipment_economy.public_inventory(_world())
        self.assertEqual(labels[0], "Kalkan [item_s1] (kuşanılmış)")
        self.assertEqual(labels[1], "Gürz (Mace) [item_m1]")
        self.assertEqual(labels[2], "Kutsal Sembol [item_c1]")

    def test_put_down_shield_is_not_marked(self):
        labels = equipment_economy.public_inventory(_world(shield_down=True))
        self.assertEqual(labels[0], "Kalkan [item_s1]")

    def test_hand_held_item_still_marked(self):
        world = _world()
        world["equipment"]["main_hand"] = "item_m1"
        labels = equipment_economy.public_inventory(world)
        self.assertEqual(labels[1], "Gürz (Mace) [item_m1] (kuşanılmış)")
        self.assertEqual(labels[0], "Kalkan [item_s1] (kuşanılmış)")

    def test_shield_without_identity_does_not_crash(self):
        world = _world()
        world["inventory"] = [{"name": "Kalkan"}]
        self.assertEqual(equipment_economy.public_inventory(world), ["Kalkan [kimlik doğrulanmamış]"])


if __name__ == "__main__":
    unittest.main()
