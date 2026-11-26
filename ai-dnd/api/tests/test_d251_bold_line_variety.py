"""D-251: a caught or empty-handed theft does not read the same three lines over and over.

Real play showed "Ne yaptığını sanıyorsun sen?" four times in one evening: the tables were three lines each,
drawn with no memory. They are wider now, and the line just said is not drawn again next time.
"""
import random
import types
import unittest

import bold_acts


def session(seed):
    return types.SimpleNamespace(rng=random.Random(seed), world_state={"flags": {}})


class BoldLineVariety(unittest.TestCase):
    def test_the_tables_are_wide_and_hold_no_twin(self):
        for table in (bold_acts._CAUGHT, bold_acts._NOTHING_THERE):
            self.assertGreaterEqual(len(table), 6)
            self.assertEqual(len(set(table)), len(table))

    def test_a_caught_thief_never_hears_the_same_line_twice_in_a_row(self):
        npc = {"id": "npc_1", "name": "Kavşim"}
        for seed in range(30):
            with self.subTest(seed=seed):
                s = session(seed)
                lines = [bold_acts._pick_line(s, npc) for _ in range(6)]
                for first, second in zip(lines, lines[1:]):
                    self.assertNotEqual(first, second)

    def test_an_empty_hand_never_reads_the_same_line_twice_in_a_row(self):
        for seed in range(30):
            with self.subTest(seed=seed):
                s = session(seed)
                lines = [bold_acts._empty_line(s) for _ in range(6)]
                for first, second in zip(lines, lines[1:]):
                    self.assertNotEqual(first, second)

    def test_an_old_save_without_the_memory_still_draws(self):
        s = session(1)
        s.world_state["flags"]["bold_lines_said"] = "bozuk"
        self.assertIn(bold_acts._empty_line(s), bold_acts._NOTHING_THERE)


class NamedEmptyHandsVaryToo(unittest.TestCase):
    """Merge of D-251 with D-229/D-230: a named thing, armour and an empty purse never read the same line twice in a row."""

    def test_no_line_twice_in_a_row(self):
        for thing in ("Mızrak", "Deri Zırh"):
            for seed in range(30):
                with self.subTest(thing=thing, seed=seed):
                    s = session(seed)
                    lines = [bold_acts._empty_line(s, thing) for _ in range(6)]
                    for first, second in zip(lines, lines[1:]):
                        self.assertNotEqual(first, second)
        for seed in range(30):
            with self.subTest(purse=seed):
                s = session(seed)
                lines = [bold_acts.fresh_line(s, "purse_empty", bold_acts._PURSE_EMPTY) for _ in range(6)]
                for first, second in zip(lines, lines[1:]):
                    self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
