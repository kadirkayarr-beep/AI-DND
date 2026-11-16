"""D-213: the Turkish question particle ("mı", "mısın", "muyum", "mıydı") in a spell line's negated/asked-form reader
must not eat a spell name that only starts with "mis"/"mus"/"miy".

`spell_effects._NEGATED` read the particle as ``\\bm[iu](?:s\\w*|y\\w*)?\\b``: any word starting "mis" or "miy" was a
question, so "I cast Misty Step", "I cast Mislead", "Mistik Patlama büyüsü" and "Cehennem Misillemesi" got no
"not in the engine yet" line. The particle is a closed set of endings (the same set as `game._QUESTION_CUE_RE`); the
rule is checked against every PHB 2024 spell name and every Turkish alias, not one spell at a time.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import spell_effects  # noqa: E402
import spell_scope  # noqa: E402
import spells  # noqa: E402
from class_progression.prepared_caster import _source_spells  # noqa: E402


class QuestionParticleTests(unittest.TestCase):
    def test_no_spell_name_reads_as_a_question_or_negation(self):
        names = {spell_effects._fold(name) for name in _source_spells()}
        names |= {alias for alias, _ in spells._UNSUPPORTED_ALIASES}
        names |= {alias for alias, _ in spells._V1_ALIASES}
        names |= {spell_effects._fold(alias) for alias in [*spell_scope.CATALOG, *spell_scope.ALIASES]}
        self.assertGreaterEqual(len(names), 391)
        for name in sorted(names):
            for line in (f"i cast {name}", f"{name} buyusu yapiyorum"):
                self.assertIsNone(spell_effects._NEGATED.search(line), line)

    def test_misty_step_and_mislead_get_the_not_yet_line(self):
        self.assertEqual(spell_effects.named("I cast Misty Step"), ("not_yet", "Misty Step"))
        self.assertEqual(spell_effects.named("I cast Mislead"), ("not_yet", "Mislead"))
        self.assertEqual(spell_effects.named("Misty Step büyüsünü kullanıyorum"), ("not_yet", "Misty Step"))
        self.assertEqual(spell_effects.named("I cast Misty Step, I must get out of here"),
                         ("not_yet", "Misty Step"))

    def test_question_particle_forms_still_stop_a_cast(self):
        for line in ("Misty Step atsam mı", "Misty Step kullanır mısın", "Mislead yapıyor muyum",
                     "Misty Step büyüsü atmış mıydım", "mage hand yapar mısınız", "mage hand yapıyor muyuz",
                     "Mislead büyüsü işe yarar mıydı", "mage hand kullanıyor muyum", "Misty Step mi atıyorum",
                     "mage hand yapabilir miyim", "Misty Step atmış mıymışım"):
            self.assertIsNotNone(spell_effects._NEGATED.search(spell_effects._fold(line)), line)
            self.assertIsNone(spell_effects.named(line), line)


if __name__ == "__main__":
    unittest.main()
