"""Direct tests for the pure Turkish text rules of text_rules_b, through the game facade."""
import unittest

import game as rules


class GenitiveTests(unittest.TestCase):
    def test_consonant_ending_takes_the_vowel_harmony_suffix(self):
        self.assertEqual(rules._turkish_genitive_form("Marek"), "Marek'in")
        self.assertEqual(rules._turkish_genitive_form("Doruk"), "Doruk'un")
        self.assertEqual(rules._turkish_genitive_form("Aslan"), "Aslan'ın")
        self.assertEqual(rules._turkish_genitive_form("Gül"), "Gül'ün")

    def test_vowel_ending_takes_a_buffer_n(self):
        self.assertEqual(rules._turkish_genitive_form("Ayla"), "Ayla'nın")
        self.assertEqual(rules._turkish_genitive_form("Bruno"), "Bruno'nun")
        self.assertEqual(rules._turkish_genitive_form("Elif"), "Elif'in")

    def test_empty_or_vowelless_names(self):
        self.assertEqual(rules._turkish_genitive_form(None), "")
        self.assertEqual(rules._turkish_genitive_form("  "), "")
        self.assertEqual(rules._turkish_genitive_form("Krr"), "Krr")


class NarratorVoiceTests(unittest.TestCase):
    def test_plural_you_becomes_singular_outside_quotes(self):
        self.assertEqual(rules._singular_narrator("Size bakıyor."), "Sana bakıyor.")
        self.assertEqual(rules._singular_narrator("Adam sizi süzüyor."), "Adam seni süzüyor.")

    def test_quoted_speech_keeps_its_own_words(self):
        line = "Kadın size dönüyor: “Sizi bekliyordum.”"
        self.assertEqual(rules._singular_narrator(line), "Kadın sana dönüyor: “Sizi bekliyordum.”")

    def test_non_text_passes_through(self):
        self.assertIsNone(rules._singular_narrator(None))


class SentenceAndQuoteTests(unittest.TestCase):
    def test_split_keeps_a_quoted_utterance_whole(self):
        parts = rules._split_sentences_keep_speech("Adam döner. “Dur! Bekle.” Sonra gider.")
        self.assertEqual(parts[0], "Adam döner.")
        self.assertIn("“Dur! Bekle.”", " ".join(parts[1:]))
        self.assertEqual(parts[-1].split()[-1], "gider.")

    def test_dangling_closing_quote_drops_the_fragment_before_it(self):
        self.assertEqual(rules._trim_dangling_quote("alırız.” Fırın kokusu yayılıyor."), "Fırın kokusu yayılıyor.")

    def test_balanced_or_quote_free_text_is_untouched(self):
        for text in ("Fırın kokusu yayılıyor.", "Adam “Merhaba.” diyor."):
            self.assertEqual(rules._trim_dangling_quote(text), text)


class SmallRuleTests(unittest.TestCase):
    def test_skill_result_category_defaults_to_failure(self):
        self.assertEqual(rules._skill_result_category("BAŞARILI"), "success")
        self.assertEqual(rules._skill_result_category("BAŞARISIZ"), "failure")
        self.assertEqual(rules._skill_result_category("anything"), "failure")

    def test_word_root_keeps_short_words_and_trims_long_ones(self):
        self.assertEqual(rules._word_root("kapı"), "kapı")
        self.assertEqual(rules._word_root("takımı"), "takım")
        self.assertEqual(rules._word_root("emanetini"), "emaneti")

    def test_asks_what_is_going_on_needs_both_place_and_question(self):
        self.assertTrue(rules._asks_what_is_going_on("Bugün burada neler oluyor?"))
        self.assertFalse(rules._asks_what_is_going_on("Neler oluyor?"))
        self.assertFalse(rules._asks_what_is_going_on("Bugün buradayım."))


if __name__ == "__main__":
    unittest.main()
