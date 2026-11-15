"""D-120: a longer PHB spell name that contains a supported one ("Mass Healing Word") is not the supported spell.

"Mass Healing Word" and "Mass Cure Wounds" (and their Turkish names) are outside the bounded catalog: a typed cast of
them is refused like any other unsupported spell and spends no slot, no Bonus Action and heals nothing.
"""
from __future__ import annotations

import unittest

import spell_scope
import spells
from api.tests.test_dilim4c_spell_resolvers import CombatRequestError, cleric, held, typed


class MassSpellNameTests(unittest.TestCase):
    def test_a_typed_mass_healing_word_is_refused_without_spending(self):
        for line in ("I cast Mass Healing Word on myself",
                     "Toplu Şifa Sözü büyüsünü kendime yapıyorum",
                     "toplu sifa sozu buyusunu kendime yapiyorum"):
            with self.subTest(line=line):
                s, _enemy = cleric()
                s.character["current_hp"] = 10
                before = held(s)
                with self.assertRaises(CombatRequestError) as raised:
                    typed(s, line, dice=2)
                self.assertEqual(raised.exception.code, "unsupported_spell")
                self.assertEqual(held(s), before)

    def test_mass_cure_wounds_is_not_cure_wounds(self):
        for line in ("I cast Mass Cure Wounds on myself", "Toplu Yara İyileştirme büyüsünü kendime yapıyorum",
                     # The natural lower-case spelling: plain i, ş kept (review of D-120).
                     "toplu yara iyileştirme büyüsünü kendime yapıyorum"):
            with self.subTest(line=line):
                with self.assertRaises(CombatRequestError) as raised:
                    spell_scope.natural_command(line, None)
                self.assertEqual(raised.exception.code, "unsupported_spell")

    def test_the_supported_names_still_cast(self):
        self.assertEqual(spell_scope.natural_command("I cast Healing Word on myself", None),
                         {"steps": [{"kind": "magic", "ability": "Healing Word", "target_id": "player"}]})
        self.assertEqual(spell_scope.natural_command("Şifa sözü büyüsünü kendime yapıyorum", None)["steps"][0]["ability"],
                         "Healing Word")
        self.assertEqual(spell_scope.natural_command("I cast Cure Wounds on myself", None)["steps"][0]["ability"],
                         "Cure Wounds")

    def test_the_cast_phrase_classifier_does_not_read_a_mass_spell_as_a_v1_spell(self):
        # spells.py holds Cure Wounds as V1 (Healing Word is only "unsupported" there, so it never resolves from here).
        self.assertNotEqual(spells.classify_cast_phrase("I cast Mass Cure Wounds")["kind"], "v1")
        self.assertNotEqual(spells.classify_cast_phrase("Toplu Yara İyileştirme büyüsü yapıyorum")["kind"], "v1")
        self.assertNotEqual(spells.classify_cast_phrase("I cast Mass Healing Word")["kind"], "v1")
        self.assertEqual(spells.classify_cast_phrase("I cast Cure Wounds"), {"kind": "v1", "spell_id": "Cure Wounds"})


if __name__ == "__main__":
    unittest.main()
