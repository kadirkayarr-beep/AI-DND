"""Held weapon identity selects the sword; it does not roll the attack."""

import unittest

import game
import held_weapon


class HeldWeaponTests(unittest.TestCase):
    def test_package_longsword_and_turkish_alias_are_the_sword(self):
        world = {"inventory": ["Longsword"]}
        self.assertEqual(held_weapon.attack_weapon_name(world), "Kılıç")
        world["inventory"] = ["Uzun Kılıç"]
        self.assertEqual(held_weapon.attack_weapon_name(world), "Kılıç")

    def test_held_item_wins_over_another_sword(self):
        session = game.create_session(seed=1)
        world = session.world_state
        world["inventory"] = [
            {"item_id": "sword-a", "weapon_id": "longsword", "name": "Longsword"},
            {"item_id": "sword-b", "weapon_id": "longsword", "name": "Longsword"},
            "Hançer",
        ]
        vague = held_weapon.resolve_turn(session, "/equip longsword")
        self.assertFalse(vague["success"])
        chosen = held_weapon.resolve_turn(session, "/equip sword-b")
        self.assertEqual(chosen["main_hand"], "sword-b")
        self.assertEqual(held_weapon.attack_weapon_name(world), "Kılıç")
        world["equipment"]["main_hand"] = "Hançer"
        self.assertIsNone(held_weapon.attack_weapon_name(world))
        held_weapon.resolve_turn(session, "/equip clear")
        self.assertIsNone(world["equipment"]["main_hand"])
        self.assertIsNone(held_weapon.attack_weapon_name(world))

    def test_attack_uses_the_held_longsword(self):
        session = game.create_session(seed=2)
        world = session.world_state
        world.update(location="tavern", npcs=[], inventory=["Longsword"], player_combat_status="active")
        world["npcs"].append({
            "id": "npc_001", "name": "Gromm", "role": "Barmen", "location": "tavern",
            "memory": [], "max_hp": 20, "current_hp": 20, "armor_class": 10,
            "combat_status": "active", "attack_bonus": 0, "damage_die": 4,
            "damage_dice": 1, "damage_modifier": 0, "distance_ft": 5,
        })
        session.character.update(current_hp=20, max_hp=20, strength_mod=2, dexterity_mod=1, proficiency_bonus=2)
        session.rng.randint = lambda low, high: 15 if high == 20 else 4
        result = session.execute_intent(
            {"intent": "attack", "target": {"type": "npc", "reference": "Gromm"}},
            "Gromm'a saldırıyorum",
        )
        self.assertNotEqual(result.get("outcome"), "no_weapon")
        self.assertEqual(result.get("weapon"), "Kılıç")

    def test_dropping_the_equipped_sword_clears_the_hand(self):
        session = game.create_session(seed=5)
        world = session.world_state
        world["inventory"] = [
            {"item_id": "sword-a", "weapon_id": "longsword", "name": "Longsword"},
            {"item_id": "sword-b", "weapon_id": "longsword", "name": "Longsword"},
        ]
        held_weapon.resolve_turn(session, "/equip sword-b")
        reply = session.update_inventory_from_player("kılıcı yere bırakıyorum")
        self.assertIn("yere taşındı", reply)
        self.assertIsNone(world["equipment"]["main_hand"])
        self.assertIsNone(held_weapon.attack_weapon_name(world))
        self.assertTrue(any(item.get("item_id") == "sword-a" for item in world["inventory"] if isinstance(item, dict)))
        self.assertIn("Kılıç", world["ground_items_by_location"][world["location"]])


if __name__ == "__main__":
    unittest.main()
