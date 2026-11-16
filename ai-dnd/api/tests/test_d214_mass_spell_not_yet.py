"""D-214: a longer PHB spell name holding a resolver's name ("Mass Healing Word") gets its own "not yet" line.

`spell_effects.named` read the inner "Healing Word" / "Cure Wounds" as a resolver's spell and left the line to the
resolver (None), so the player got no "not in the engine yet" line. The D-120 shield (`spells.without_names`) now runs
on this path too: the inner name is blanked before the resolver check, for every longer name, not one spell.
"""
from __future__ import annotations

import unittest

import spell_effects


class MassSpellNotYetTests(unittest.TestCase):
    def test_an_english_mass_spell_gets_its_own_not_yet_line(self):
        for line, spell in (("I cast Mass Cure Wounds", "Mass Cure Wounds"),
                            ("I cast Mass Healing Word", "Mass Healing Word"),
                            ("I cast Mass Cure Wounds on the wounded", "Mass Cure Wounds"),
                            ("casting Mass Healing Word now", "Mass Healing Word")):
            with self.subTest(line=line):
                self.assertEqual(spell_effects.named(line), ("not_yet", spell))

    def test_a_turkish_mass_spell_is_never_named_as_the_inner_spell(self):
        # A Turkish name of a spell without a resolver gets no layer-3 line today ("Ateş Topu" neither); it must at
        # least never be read as the inner resolver spell.
        for line in ("Toplu Şifa Sözü büyüsünü yapıyorum", "toplu yara iyileştirme büyüsünü yapıyorum"):
            with self.subTest(line=line):
                self.assertNotIn(spell_effects.named(line), {("not_yet", "Healing Word"), ("not_yet", "Cure Wounds")})

    def test_the_resolver_spells_still_go_to_the_resolver(self):
        for line in ("I cast Cure Wounds", "I cast Healing Word", "Şifa Sözü büyüsünü kendime yapıyorum",
                     "Healing Word ve Mass Cure Wounds"):
            with self.subTest(line=line):
                self.assertIsNone(spell_effects.named(line))


if __name__ == "__main__":
    unittest.main()
