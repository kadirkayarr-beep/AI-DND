"""D-071: "cast" in an everyday English phrase ("cast a glance", "cast aside") is no casting word.

Before the fix, "I cast a glance at the guard and command him to leave" read as a cast of Command and the turn answered
"Command büyüsü henüz motorda yok". The spell gate in game.py routes a turn by `spell_effects.named` alone, so the
reading is checked here; a real cast of the same spell keeps its "not yet" line."""
import unittest

import spell_effects


class CastIdiomIsNoCast(unittest.TestCase):
    def test_everyday_cast_phrases_name_no_spell(self):
        for line in ("I cast a glance at the guard and command him to leave",
                     "I cast a look at the door and command it to open",
                     "Casting a quick glance around, I command the dog to sit",
                     "I cast my eyes over the hall and command silence",
                     "I cast aside my cloak and command the room",
                     "I cast off the rope and command the crew to row",
                     "I cast the net and command the boy to pull"):
            with self.subTest(line=line):
                self.assertIsNone(spell_effects.named(line))

    def test_real_casts_still_read(self):
        for line, expected in (("I cast Command on the guard", ("not_yet", "Command")),
                               ("I cast a glance at the guard and cast Command on him", ("not_yet", "Command")),
                               ("I cast a spell: Command", ("not_yet", "Command")),
                               ("Muhafıza Command büyüsü yapıyorum", ("not_yet", "Command")),
                               ("I cast Mage Hand to open the door", ("narrative", "Mage Hand")),
                               ("I cast light on the torch", ("narrative", "Light"))):
            with self.subTest(line=line):
                self.assertEqual(spell_effects.named(line), expected)

    def test_idiom_never_eats_a_spell_name(self):
        # 391 scaling: "cast Arcane Eye" and "cast Stone Shape" end in idiom words; every PHB name reads as before.
        import re
        from unittest import mock
        names = sorted(spell_effects._manifest_names())
        lines = [prefix + name for name in names for prefix in ("I cast ", "I cast the ", "I cast an ", "I cast a quick ")]
        with mock.patch.object(spell_effects, "_CAST_IDIOM", re.compile(r"(?!x)x")):
            before = [spell_effects.named(line) for line in lines]
        self.assertEqual([spell_effects.named(line) for line in lines], before)
        self.assertEqual(spell_effects.named("I cast Arcane Eye"), ("not_yet", "Arcane Eye"))
        self.assertEqual(spell_effects.named("I cast Stone Shape"), ("not_yet", "Stone Shape"))


if __name__ == "__main__":
    unittest.main()
