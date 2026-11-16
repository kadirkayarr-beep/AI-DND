"""D-215: `spells.classify_cast_phrase` reads "cast" in an everyday phrase the way `spell_effects.named` does (D-071).

"I cast a glance at the guard and command him to leave" is no cast: the idiom is no casting verb, so "command" there is
an order, not the Command spell. A real cast in the same line, a spell name an idiom word sits in ("Arcane Eye") and
the Turkish casting verb still classify as before. One shared rule, not a per-spell patch.
"""
from __future__ import annotations

import unittest

import spells


class ClassifyCastIdiomTests(unittest.TestCase):
    def test_an_english_idiom_is_no_casting_verb(self):
        for line in (
            "I cast a glance at the guard and command him to leave",
            "I cast my eyes over the room and see a shadow",
            "I cast the net into the water",
            "I cast aside my cloak and command the guard to kneel",
            "I cast doubt on his story",
        ):
            with self.subTest(line=line):
                self.assertIsNone(spells.classify_cast_phrase(line))

    def test_a_real_cast_next_to_an_idiom_still_classifies(self):
        self.assertEqual(spells.classify_cast_phrase("I cast aside my cloak and cast Command on the guard"),
                         {"kind": "unsupported", "spell_id": "Command"})
        self.assertEqual(spells.classify_cast_phrase("I cast a glance at him, then cast Fire Bolt"),
                         {"kind": "v1", "spell_id": "Fire Bolt"})

    def test_plain_english_and_turkish_casts_are_unchanged(self):
        self.assertEqual(spells.classify_cast_phrase("I cast Command"), {"kind": "unsupported", "spell_id": "Command"})
        self.assertEqual(spells.classify_cast_phrase("I cast Fire Bolt at the guard"),
                         {"kind": "v1", "spell_id": "Fire Bolt"})
        self.assertEqual(spells.classify_cast_phrase("Emir büyüsü yapıyorum"),
                         {"kind": "unsupported", "spell_id": "Command"})
        self.assertEqual(spells.classify_cast_phrase("Muhafıza bir bakış atıp Ateş Oku büyüsü yapıyorum"),
                         {"kind": "v1", "spell_id": "Fire Bolt"})
        # A spell name holding an idiom word ("eye") is a cast, not an idiom.
        self.assertEqual(spells.classify_cast_phrase("I cast Arcane Eye"), {"kind": "unknown", "spell_id": ""})

    def test_turkish_line_without_a_casting_verb_is_none(self):
        self.assertIsNone(spells.classify_cast_phrase("Muhafıza bir bakış atıp ona gitmesini emrediyorum"))


if __name__ == "__main__":
    unittest.main()
