"""Direct tests for the pure text helpers of text_rules_a, through the game facade."""
import unittest
from types import SimpleNamespace

import game as rules


class OllamaReplyTests(unittest.TestCase):
    def test_content_is_read_from_dicts_and_typed_replies(self):
        self.assertEqual(rules.ollama_response_content({"message": {"content": "Selam"}}), "Selam")
        typed = SimpleNamespace(message=SimpleNamespace(content="Merhaba"))
        self.assertEqual(rules.ollama_response_content(typed), "Merhaba")
        self.assertEqual(rules.ollama_response_content({}), "")

    def test_cut_reply_is_the_length_stop_only(self):
        self.assertTrue(rules.ollama_reply_was_cut({"done_reason": "length"}))
        self.assertFalse(rules.ollama_reply_was_cut({"done_reason": "stop"}))
        self.assertTrue(rules.ollama_reply_was_cut(SimpleNamespace(done_reason="length")))
        self.assertFalse(rules.ollama_reply_was_cut(SimpleNamespace()))


class JsonObjectTests(unittest.TestCase):
    def test_object_inside_fences_and_think_block(self):
        raw = "<think>{\"no\": 1}</think>```json\n{\"intent\": \"talk\"}\n```"
        self.assertEqual(rules._extract_json_object(raw), {"intent": "talk"})

    def test_unclosed_containers_are_closed(self):
        self.assertEqual(rules._extract_json_object('{"a": [1, 2'), {"a": [1, 2]})

    def test_brace_inside_a_string_is_text(self):
        self.assertEqual(rules._extract_json_object('{"say": "a } b"}'), {"say": "a } b"})

    def test_no_object_or_non_text(self):
        self.assertIsNone(rules._extract_json_object("no json here"))
        self.assertIsNone(rules._extract_json_object(None))


class NarrationCleanupTests(unittest.TestCase):
    def test_repeated_sentences_from_last_turn_are_dropped(self):
        earlier = ["Rüzgâr esiyor. Kapı gıcırdıyor."]
        self.assertEqual(rules._drop_repeated_sentences("Rüzgâr esiyor. Bir köpek havlıyor.", earlier),
                         "Bir köpek havlıyor.")

    def test_all_new_or_all_repeated_text_is_kept_whole(self):
        earlier = ["Rüzgâr esiyor."]
        self.assertEqual(rules._drop_repeated_sentences("Bir köpek havlıyor.", earlier), "Bir köpek havlıyor.")
        self.assertEqual(rules._drop_repeated_sentences("Rüzgâr esiyor.", earlier), "Rüzgâr esiyor.")

    def test_pictographs_are_removed(self):
        self.assertEqual(rules._strip_pictographs("Selam 👋🏽 dostum ❤️"), "Selam  dostum ")

    def test_real_world_faith_phrases_get_this_worlds_words(self):
        self.assertEqual(rules._without_real_world_faith("İnşallah yağmur yağmaz."),
                         "Tanrılar izin verirse yağmur yağmaz.")
        self.assertEqual(rules._without_real_world_faith("Yarın gelir, inşallah."),
                         "Yarın gelir, tanrılar izin verirse.")

    def test_interaction_mode_keeps_known_values_only(self):
        for mode in ("say", "do", "ask_dm"):
            self.assertEqual(rules._normalize_interaction_mode(mode), mode)
        self.assertIsNone(rules._normalize_interaction_mode("shout"))

    def test_inside_speech_finds_positions_within_quotes(self):
        text = "Adam “dur” diyor."
        self.assertTrue(rules._inside_speech(text, text.index("dur")))
        self.assertFalse(rules._inside_speech(text, text.index("diyor")))


if __name__ == "__main__":
    unittest.main()
