"""The owner's first browser play (31 Oct 2026) pinned as regressions.

Every test replays the owner's own sentence, or the exact line the game showed.
The model is mocked, so these prove the deterministic path alone.
"""

from __future__ import annotations

import unittest

import npc_statements


class SpokenPlaceNames(unittest.TestCase):
    def names(self, line):
        return [item[0] for item in npc_statements._named_places(line)]

    def test_a_yes_before_the_name_is_not_part_of_the_name(self):
        self.assertEqual(self.names("Bir şey yok, sadece yolculuk. Evet, Veyra Hanı var."), ["Veyra Hanı"])

    def test_a_yes_without_a_comma_is_not_part_of_the_name(self):
        self.assertEqual(self.names("Evet Veyra Hanı var."), ["Veyra Hanı"])

    def test_two_places_in_a_list_stay_two_places(self):
        self.assertEqual(self.names("Kızıl Kule, Veyra Hanı ikisi de yakın."), ["Kızıl Kule", "Veyra Hanı"])

    def test_a_real_two_word_name_keeps_both_words(self):
        self.assertEqual(self.names("Tamam, Gümüş Kılıç Hanı burada."), ["Gümüş Kılıç Hanı"])
