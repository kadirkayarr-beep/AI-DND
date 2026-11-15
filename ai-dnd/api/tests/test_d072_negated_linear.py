"""D-072: the negated/wished/asked-form reader of a spell line runs in linear time.

`_NEGATED` had two alternatives starting with a bare ``\\w+`` (``\\w+(?:sam|sem|saydim|seydim)\\b`` and
``\\w+m[ae]li\\b``); the engine tried them from every letter of a long word, so one 4000-character word took about
a third of a second and the cost grew with the square of the length. A word boundary before them keeps the same
answers and tries each word once.
"""
from __future__ import annotations

import random
import re
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import spell_effects  # noqa: E402

# The pattern as it stood before D-072 (no word boundary before the two ``\w+`` alternatives); answers must not change.
# D-213 narrowed the question-particle alternative to a closed set of endings; the reference carries that same
# alternative, so this test still checks only what D-072 changed.
_OLD_NEGATED = re.compile(
    r"\b(?:not|don't|dont|never|degil|should|would|could|shall|if|maybe|acaba|keske|eger|belki)\b"
    r"|\bm[iu](?:y?d[iu](?:m|n|k|n[iu]z|lar|ler)?|y?m[iu]s(?:[iu]m|s[iu]n(?:[iu]z)?|[iu]z|lar|ler)?|y[iu]m"
    r"|s[iu]n(?:[iu]z)?|y[iu]z|d[iu]r)?\b"
    r"|istem(?:iyor|em|ez|edi|eyece)|\w+(?:sam|sem|saydim|seydim)\b|\w+m[ae]li\b"
    r"|\b(?:kullan|yap|at|dene)m(?:a\b|iyor|am\b|ayacag|adi)")


class NegatedReaderLinearTests(unittest.TestCase):
    def test_one_long_word_is_read_in_linear_time(self):
        # Quadratic reading took seconds here (about 8 s for 20000 letters); linear reading takes milliseconds.
        for word in ("m" * 20000, "a" * 20000, "kullan" * 3400):
            started = time.perf_counter()
            spell_effects._NEGATED.search(word)
            self.assertLess(time.perf_counter() - started, 0.5, word[:8])

    def test_a_long_spell_line_is_still_read_quickly(self):
        spell_effects.named("mage hand yapiyorum")  # the one-time spell-name table is built here, not timed
        started = time.perf_counter()
        self.assertIsNone(spell_effects.named("m" * 4000))
        self.assertLess(time.perf_counter() - started, 0.5)

    def test_answers_are_the_same_as_before(self):
        lines = ["yapsam mi", "atsam", "kullanmali miyim", "keske", "isik buyusu yapsaydim", "gelseydim",
                 "isaret etmeli", "magic missile atiyorum", "mage hand kullaniyorum", "sam", "mali", "emeli",
                 "x-yapsam", "_sam", "9sam", "yap_sam", "minor illusion yapiyorum", "light cast ediyorum"]
        rng = random.Random(72)
        alphabet = "asmeliydk _-9'?"
        lines += ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30))) for _ in range(5000)]
        for line in lines:
            self.assertEqual(bool(spell_effects._NEGATED.search(line)), bool(_OLD_NEGATED.search(line)), line)

    def test_wished_and_weighed_forms_still_stop_a_cast(self):
        for line in ("mage hand yapsam", "isik buyusu atmali", "mage hand kullansaydim"):
            self.assertIsNone(spell_effects.named(line), line)


if __name__ == "__main__":
    unittest.main()
