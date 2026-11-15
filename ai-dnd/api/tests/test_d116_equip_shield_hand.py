"""D-116 on the item command (`/item equip`), D-178 and the new shield-wearer's default hand.

A creation shield has no hand entry, yet while it is in use its share is in the Armor Class and it holds a hand: a
weapon taken into the second hand puts it down, as a two-handed weapon does (`equipment_economy._apply` "equip", then
`gear.settle_shield`). A new world's default "longsword" hand names a weapon a Cleric or Druid never owned; it holds
nothing, as the attack path already reads it (`weapon_attack._names_no_owned_weapon`), so the class's own weapon can
be taken in hand out of combat too.
"""
import unittest

import character_progression
import equipment_economy
import game
import gear
from api.character_creation import configure_character
from api.tests.test_wizard_cleric_4c3 import SPECS


def created_cleric(seed=42):
    session = game.create_session(seed=seed)
    configure_character(session, mode="custom", **SPECS["Cleric"])
    return session


def item_id(session, weapon_id):
    return next(item["item_id"] for item in session.world_state["inventory"] if item.get("weapon_id") == weapon_id)


def run(session, text):
    return equipment_economy.execute(session, text)["action_result"]


class NewClericOwnWeapon(unittest.TestCase):
    def test_new_cleric_takes_the_owned_mace_in_hand(self):
        s = created_cleric()
        self.assertEqual(s.world_state["equipment"], {"main_hand": "longsword", "off_hand": None})
        self.assertTrue(run(s, "/item list")["success"])
        self.assertEqual(s.world_state["equipment"], {"main_hand": None, "off_hand": None})
        result = run(s, f"/item equip {item_id(s, 'mace')} main_hand")
        self.assertTrue(result["success"], result)
        self.assertEqual(s.world_state["equipment"], {"main_hand": item_id(s, "mace"), "off_hand": None})

    def test_new_cleric_draws_the_owned_mace_past_the_default_hand(self):
        s = created_cleric()
        equipment_economy.materialize(s.world_state)
        s.world_state["equipment"]["main_hand"] = "longsword"  # the default hand, as an older save may still hold it
        result = gear.draw(s.world_state, item_id(s, "mace"), character=s.character)
        self.assertEqual(result.status, "drawn")
        self.assertEqual(s.world_state["equipment"], {"main_hand": item_id(s, "mace"), "off_hand": None})
        self.assertNotIn("shield_down", s.world_state)

    def test_an_ambiguous_hand_and_an_npc_stat_hand_keep_their_value(self):
        s = created_cleric()
        s.world_state["npcs"] = [{"id": "guard", "name": "Nöbetçi", "location": s.world_state["location"],
                                  "current_hp": 10, "inventory": [],
                                  "equipment": {"main_hand": "longsword", "off_hand": None}}]
        s.world_state["inventory"] += ["Longsword", "Kılıç"]  # two owned longswords: the alias stays unresolved
        equipment_economy.materialize(s.world_state)
        self.assertEqual(s.world_state["equipment"]["main_hand"], "longsword")
        self.assertEqual(s.world_state["npcs"][0]["equipment"]["main_hand"], "longsword")


class SecondWeaponPutsTheShieldDown(unittest.TestCase):
    def setUp(self):
        self.s = created_cleric()
        self.s.world_state["inventory"].append("Dagger")
        self.assertTrue(run(self.s, "/item list")["success"])
        self.assertTrue(run(self.s, f"/item equip {item_id(self.s, 'mace')} main_hand")["success"])
        self.share = character_progression.shield_share(self.s.character)
        self.assertGreater(self.share, 0)

    def shield_id(self):
        return next(item["item_id"] for item in self.s.world_state["inventory"] if item["name"] == "Kalkan")

    def test_off_hand_dagger_beside_a_mace_puts_the_shield_down_and_lowers_ac(self):
        before = self.s.character["armor_class"]
        result = run(self.s, f"/item equip {item_id(self.s, 'dagger')} off_hand")
        self.assertTrue(result["success"], result)
        self.assertEqual(self.s.world_state["equipment"],
                         {"main_hand": item_id(self.s, "mace"), "off_hand": item_id(self.s, "dagger")})
        self.assertEqual(self.s.world_state["shield_down"], {"item_id": self.shield_id(), "ac_bonus": self.share})
        self.assertEqual(self.s.character["armor_class"], before - self.share)
        # The dagger goes back to the bag: the shield can be donned again, and the full total returns.
        self.assertTrue(run(self.s, "/item unequip off_hand")["success"])
        self.assertEqual(gear.don_shield(self.s.world_state, self.s.character).status, "donned")
        self.assertEqual(self.s.character["armor_class"], before)

    def test_one_weapon_beside_the_shield_keeps_it_up(self):
        before = self.s.character["armor_class"]
        self.assertTrue(run(self.s, "/item unequip main_hand")["success"])
        self.assertTrue(run(self.s, f"/item equip {item_id(self.s, 'dagger')} off_hand")["success"])
        self.assertNotIn("shield_down", self.s.world_state)
        self.assertEqual(self.s.character["armor_class"], before)


if __name__ == "__main__":
    unittest.main()
