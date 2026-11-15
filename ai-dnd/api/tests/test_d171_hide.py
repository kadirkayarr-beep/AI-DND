"""D-094 rest, D-171, D-176: a hide needs cover or the dark (dice guide 4.4/H01); hiding one's own thing on oneself is
Sleight of Hand. The turn route is pinned by journeys 55, 55b and 55c."""

from __future__ import annotations

import unittest

import game


def folded(line):
    return " ".join(game.re.findall(r"\w+", game._normalize_turkish_typos(line)))


class TheWordsOfAHide(unittest.TestCase):
    def test_named_cover_counts(self):
        for line in ("fıçının arkasına saklanıyorum", "gölgelere gizleniyorum", "kalabalığa karışıp gizleniyorum",
                     "masanın altına saklanıyorum", "çalıların arasına gizleniyorum", "köşeye sinip saklanıyorum",
                     "perdenin ardına saklanıyorum"):
            with self.subTest(line=line):
                self.assertTrue(game._COVER.search(folded(line)))

    def test_a_plain_hide_names_no_cover(self):
        for line in ("saklanıyorum", "gizleniyorum", "sessizce gizlenmeye çalışıyorum", "kendimi gizliyorum"):
            with self.subTest(line=line):
                self.assertFalse(game._COVER.search(folded(line)))

    def test_ones_own_thing_hidden_is_no_hide(self):
        for line in ("hançerimi kolumun içine gizliyorum", "kesemi pelerinimin altına saklıyorum",
                     "yüzüğümü cebime saklıyorum", "kılıcımı saklıyorum"):
            with self.subTest(line=line):
                self.assertTrue(game._OWN_THING_HIDDEN.search(folded(line)))
        for line in ("kendimi gizliyorum", "saklanıyorum", "fıçının arkasına saklanıyorum"):
            with self.subTest(line=line):
                self.assertFalse(game._OWN_THING_HIDDEN.search(folded(line)))


if __name__ == "__main__":
    unittest.main()
