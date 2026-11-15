"""D-198: Paladin package B's "5 Cirit" is the catalog Javelin, so the Paladin can attack with it."""
import unittest
from unittest.mock import patch

import weapon_attack
from weapon_catalog import lookup
from api.tests.test_roadmap_c16_paladin import created, spec


class PaladinJavelinTests(unittest.TestCase):
    def paladin_b(self):
        return created(request=dict(spec(), equipment_package="B"))

    def test_cirit_labels_are_the_catalog_javelin(self):
        for label in ("5 Cirit", "Cirit", "cirit"):
            with self.subTest(label=label):
                self.assertEqual((lookup(label) or {}).get("weapon_id"), "javelin")

    def test_package_b_paladin_owns_and_names_the_javelins(self):
        session = self.paladin_b()
        self.assertIn("5 Cirit", [item.get("name") if isinstance(item, dict) else item
                                  for item in session.world_state["inventory"]])
        self.assertIn("javelin", weapon_attack._owned_weapon_ids(session))
        self.assertIn("javelin", weapon_attack.weapons_named(session, "ciritimle saldırıyorum"))

    def test_package_b_paladin_attacks_with_a_javelin(self):
        session = self.paladin_b()
        npc = session.create_npc_from_ai({"name": "Cirit hedefi", "role": "Guard", "location": "tavern"})
        npc.update(current_hp=100, max_hp=100, armor_class=1, distance_ft=5)
        with patch.object(session.rng, "randint", return_value=10):
            result = weapon_attack.resolve(session, "player", npc["id"], "javelin", {"draw": True})
        self.assertTrue(result["hit"], result)
        self.assertGreater(result["damage"], 0)
        self.assertEqual(npc["current_hp"], 100 - result["damage"])


if __name__ == "__main__":
    unittest.main()
