"""D-224 (Kadir playtest 2026-11-15): "Muhafızın kesesi var mı diye inceliyorum." was read deed=steal and 7 copper
moved. A line that only looks (incele, bak, kontrol et, süz, gözden geçir) and names no taking is no theft, whatever
the reading says. Narrow on purpose: D-177's wider guard waits for a real-model measurement, and every real theft
(RealTheftsStillCount, journey 51b) must stay a theft.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import bold_acts
import game
from api.tests.test_d094_model_check import RealTheftsStillCount


def session():
    return SimpleNamespace(_normalize_turkish_typos=game._normalize_turkish_typos, _front_check="",
                           _front_kind="bag")


LOOKS = (
    "Muhafızın kesesi var mı diye inceliyorum.",
    "Muhafızın kesesine bakıyorum",
    "Adamın kesesini kontrol ediyorum",
    "Kadının kesesini dikkatle süzüyorum",
    "Muhafızın cebini gözden geçiriyorum",
    "Kesesine şöyle bir göz atıyorum",
)

TAKES = (
    "kesesini almaya çalışıyorum",  # journey 51b
    "Kesesine bakıp çalıyorum",
    "Kesesini inceleyip aşırıyorum",
    "Kimse bakmazken kesesini alıyorum",
    "Muhafız başka yere bakarken kesesini kapıyorum",
    "Kesesini kontrol edip cebime indiriyorum",
    "Kesesini yokluyorum",
    "Parmaklarımı keseye daldırıyorum",
)


class AnInspectionIsNoTheft(unittest.TestCase):
    def test_a_line_that_only_looks_is_no_steal_whatever_the_reading_says(self):
        for line in LOOKS:
            with self.subTest(line=line):
                self.assertFalse(bold_acts._steals(session(), line, "steal"))

    def test_a_line_that_looks_and_takes_stays_a_steal(self):
        for line in TAKES:
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(session(), line, "steal"))

    def test_the_real_theft_guard_lines_keep_their_steal_reading(self):
        # every guard line the reading's steal took before D-224 still takes it
        before = [line for line in RealTheftsStillCount.LINES if ":" not in line]
        for line in before:
            with self.subTest(line=line):
                self.assertTrue(bold_acts._steals(session(), line, "steal"))


if __name__ == "__main__":
    unittest.main()
