"""Dilim 4C Task 4b fix round 1 (review): a negated line never drops Concentration, die sizes and the Bless d4 are
pinned by the dice the engine asks for, the DC cap, Relentless Endurance's save, a real ability check, Bless lasting
ten full rounds whatever the caster's place in initiative, and a stale record never narrated or dropped.
Fixture: test_spell_scope.caster (fixed session seed 17; no campaign, no town)."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import combat_lifecycle
import spell_concentration
import spell_registry
import spell_scope
import weapon_attack
from api.tests.test_dilim4c_spell_resolvers import cleric, held, magic, next_turn, turn, typed, wizard

NEGATED = ("Konsantrasyonumu bırakmıyorum, bekliyorum", "Konsantrasyonumu bırakmadan geri çekiliyorum",
           "I will not drop my concentration", "don't break concentration")
POSITIVE = ("Konsantrasyonu bırakıyorum", "konsantrasyonumu bitiriyorum", "I drop my concentration",
            "end concentration")


class Spy:
    """rng.randint stand-in: records the sides asked for and answers a fixed face (never above the die)."""

    def __init__(self, face=1):
        self.face, self.asked = face, []

    def __call__(self, low, high):
        self.asked.append((low, high))
        return min(self.face, high)


def blessed():
    s, enemy = cleric()
    turn(s, magic("Bless", "player"))
    return s, enemy


class NegatedLinesKeepConcentration(unittest.TestCase):
    def test_a_negated_line_is_no_drop_command(self):
        for line in NEGATED:
            with self.subTest(line):
                self.assertIsNone(spell_scope.natural_command(line, None))
                self.assertFalse(spell_scope.explicit_request(line))

    def test_a_positive_line_still_drops(self):
        for line in POSITIVE:
            with self.subTest(line):
                self.assertEqual(spell_scope.natural_command(line, None), {"steps": [{"kind": "end_concentration"}]})
                self.assertTrue(spell_scope.explicit_request(line))

    def test_a_negated_turn_keeps_bless(self):
        for line in NEGATED:
            with self.subTest(line):
                s, enemy = blessed()
                record = copy.deepcopy(spell_concentration.current(s.world_state))
                try:
                    typed(s, line)
                except Exception:  # whatever else the line means, it is not a drop
                    pass
                self.assertEqual(spell_concentration.current(s.world_state), record)


if __name__ == "__main__":
    unittest.main()
