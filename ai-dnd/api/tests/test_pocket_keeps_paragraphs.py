"""The pocket repairs drop only the false sentence; the paragraph break between the sentences that stay is kept.

Before: both repairs rejoined the kept sentences with one space, so a multi-paragraph narration came out as one block
on every turn that moved no coin (found by test_ai_pipeline_port's multi-paragraph texture test).
"""
import unittest

import pocket

TEXT = "Kapı gıcırdar. Yağmur yağar.\n\nAnahtarı cebine koydun. Sokak sessizdir.\n\nUzakta bir köpek havlar."


class KeepTheBreak(unittest.TestCase):
    def test_without_the_taking_keeps_the_break_when_nothing_in_it_is_false(self):
        self.assertEqual(pocket.without_the_taking(TEXT, ("kilic",)), TEXT)

    def test_without_the_taking_drops_only_the_false_sentence_and_keeps_the_later_break(self):
        self.assertEqual(
            pocket.without_the_taking(TEXT, ("anahtar",)),
            "Kapı gıcırdar. Yağmur yağar.\n\nSokak sessizdir.\n\nUzakta bir köpek havlar.",
        )

    def test_without_false_purse_keeps_the_break_when_nothing_in_it_is_false(self):
        self.assertEqual(pocket.without_false_purse(TEXT, {"inventory": []}), TEXT)

    def test_without_false_purse_drops_only_the_false_sentence_and_keeps_the_break(self):
        text = "Kapı gıcırdar.\n\nKesende 900 bakır var. Sokak sessizdir."
        self.assertEqual(pocket.without_false_purse(text, {"inventory": []}), "Kapı gıcırdar.\n\nSokak sessizdir.")


if __name__ == "__main__":
    unittest.main()
