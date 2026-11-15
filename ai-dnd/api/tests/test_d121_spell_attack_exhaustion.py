"""D-121: a spell attack roll is a D20 Test, so Exhaustion lowers it by 2 per level (SRD 5.2.1 p.181).

Fire Bolt, Ray of Frost and Shocking Grasp used the bare spell attack modifier; a weapon attack already took the
penalty (weapon_attack.prepare). Exhaustion 2 turns a d20 of 10 (+5) from 15 into 11: a miss against AC 14.
"""
import unittest
from unittest.mock import patch

from api.tests.test_spell_scope import caster
import spell_scope


class SpellAttackExhaustionTests(unittest.TestCase):
    def _cast(self, spell, exhaustion, d20):
        s, e = caster(cls="Wizard")  # INT 16 (+3), proficiency +2: spell attack +5
        s.character["cantrips"] = [spell]
        s.world_state["spellcasting_v1"]["cantrips"] = [spell]
        s.character["exhaustion"] = exhaustion
        e["armor_class"] = 14
        if spell == "Shocking Grasp":
            e["distance_ft"] = 5
            s.world_state["attack_environment"]["pairs"]["player|" + e["id"]]["distance_ft"] = 5
        with patch("game.roll_d20", return_value=d20), patch.object(s.rng, "randint", return_value=4):
            return spell_scope.cast(s, spell, e["id"]), e

    def test_exhaustion_two_lowers_each_spell_attack_by_four(self):
        for spell in ("Fire Bolt", "Ray of Frost", "Shocking Grasp"):
            with self.subTest(spell=spell):
                result, enemy = self._cast(spell, 2, 10)
                self.assertEqual(result["resolution"]["total_modifier"], 1)
                self.assertEqual(result["resolution"]["total"], 11)
                self.assertEqual(result["resolution"]["outcome"], "MISS")
                self.assertEqual(result["damage"], 0)
                self.assertEqual(enemy["current_hp"], 100)

    def test_no_exhaustion_keeps_the_hit(self):
        result, enemy = self._cast("Fire Bolt", 0, 10)
        self.assertEqual(result["resolution"]["total"], 15)
        self.assertEqual(result["resolution"]["outcome"], "HIT")
        self.assertEqual(enemy["current_hp"], 96)

    def test_natural_twenty_still_crits_under_exhaustion(self):
        result, _ = self._cast("Fire Bolt", 5, 20)
        self.assertEqual(result["resolution"]["total_modifier"], -5)
        self.assertEqual(result["resolution"]["outcome"], "CRITICAL_HIT")


if __name__ == "__main__":
    unittest.main()
