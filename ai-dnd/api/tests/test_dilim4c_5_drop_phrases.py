"""Dilim 4C.5 (4C.4b re-review): a line that refuses, regrets or denies dropping Concentration never drops it (keeping it
is the safe side: the player can rephrase); a positive drop followed by an unrelated negated clause still drops.
No campaign, no town: the parser is pure; the turn check uses test_spell_scope.caster (fixed session seed 17)."""
from __future__ import annotations

import copy
import unittest

import spell_concentration
import spell_scope
from api.tests.test_dilim4c_4b_fix1 import NEGATED, POSITIVE, blessed
from api.tests.test_dilim4c_spell_resolvers import typed

REFUSED = ("Konsantrasyonumu bırakmak istemiyorum", "Konsantrasyonu bırakmaya niyetim yok",
           "Konsantrasyonu bırakmaktan vazgeçtim", "I refuse to drop concentration", "Konsantrasyonu bırakmadım",
           "konsantrasyonu kesmedim", "I didn't drop my concentration",
           "Konsantrasyonu bırakıyorum ama vazgeçtim",  # a retraction after "ama" keeps it
           "Konsantrasyonu bırakmak ve saldırmak istemiyorum",  # a Turkish negation scopes back over "ve"
           "I won't attack and drop concentration")  # an English negation scopes forward over "and"
DROPS_DESPITE_LATER_CLAUSE = ("I drop concentration and do not attack", "I end my concentration and then wait, not moving",
                              "Konsantrasyonu bırakıyorum ve saldırmıyorum", "Konsantrasyonumu bıraktım ve beklemiyorum")


class RefusedDropKeepsConcentration(unittest.TestCase):
    def test_a_refused_or_denied_drop_is_no_command(self):
        for line in REFUSED:
            with self.subTest(line):
                self.assertIsNone(spell_scope.natural_command(line, None))
                self.assertFalse(spell_scope.explicit_request(line))

    def test_a_refused_turn_keeps_bless(self):
        for line in REFUSED:
            with self.subTest(line):
                s, _ = blessed()
                record = copy.deepcopy(spell_concentration.current(s.world_state))
                try:
                    typed(s, line)
                except Exception:  # whatever else the line means, it is not a drop
                    pass
                self.assertEqual(spell_concentration.current(s.world_state), record)

    def test_a_later_negated_clause_does_not_cancel_the_drop(self):
        for line in DROPS_DESPITE_LATER_CLAUSE:
            with self.subTest(line):
                self.assertEqual(spell_scope.natural_command(line, None), {"steps": [{"kind": "end_concentration"}]})
                self.assertTrue(spell_scope.explicit_request(line))

    def test_the_4b_lines_are_unchanged(self):
        for line in NEGATED:
            with self.subTest(line):
                self.assertIsNone(spell_scope.natural_command(line, None))
        for line in POSITIVE:
            with self.subTest(line):
                self.assertEqual(spell_scope.natural_command(line, None), {"steps": [{"kind": "end_concentration"}]})


if __name__ == "__main__":
    unittest.main()
