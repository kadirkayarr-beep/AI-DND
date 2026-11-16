"""D-227: "Işık (Light) büyüsü yapıyorum" is a cast of Light (the spell named with its other-language name in brackets).

Before the fix `spell_effects._LIGHT` allowed only "ışık/light" right before "büyü/spell/cantrip", so the bracketed form
read as no cast and the line fell to the model's skill-roll intent. Everyday uses of the words stay no cast."""
import unittest

import spell_effects


class LightWithBracketedName(unittest.TestCase):
    def test_bracketed_names_read_as_light(self):
        for line in ("Işık (Light) büyüsü yapıyorum", "Light (Işık) büyüsü yapıyorum", "Işık (Light) büyüsünü yapıyorum",
                     "Işık (Light) cantrip yapıyorum", "Light (Işık) spell yapıyorum", "Işık ( Light ) büyüsü yapıyorum",
                     "Işık büyüsü yapıyorum", "Light büyüsü yapıyorum"):
            with self.subTest(line=line):
                self.assertEqual(spell_effects.named(line), ("narrative", "Light"))

    def test_other_narrative_spells_with_brackets_still_read(self):
        for line, spell in (("Mage Hand (Büyücü Eli) büyüsü yapıyorum", "Mage Hand"),
                            ("Büyücü Eli (Mage Hand) büyüsü yapıyorum", "Mage Hand"),
                            ("Küçük Yanılsama (Minor Illusion) büyüsü yapıyorum", "Minor Illusion")):
            with self.subTest(line=line):
                self.assertEqual(spell_effects.named(line), ("narrative", spell))

    def test_questions_negations_and_everyday_words_are_no_cast(self):
        for line in ("Işık (Light) büyüsü yapsam mı", "Işık (Light) büyüsü yapmak istemiyorum", "Işık (Light) nedir?",
                     "Işık (Light) büyüsü yapıyorum ve cebime altın koyuyorum", "Işık (Light) ile etrafa bakıyorum",
                     "Odaya bir ışık (light) giriyor"):
            with self.subTest(line=line):
                self.assertIsNone(spell_effects.named(line))


if __name__ == "__main__":
    unittest.main()
