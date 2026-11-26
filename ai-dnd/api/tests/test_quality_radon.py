"""G1.8 (D-592): the radon complexity ratchet. A function of rank E or F may get simpler, never more complex; a new one fails."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from quality_gate import ratchet  # noqa: E402
from quality_gate.ratchet import ToolOutputError, compare, count_findings, load_baseline, parse_radon  # noqa: E402


def block(name, cc, classname=None, closures=()):
    row = {"type": "method" if classname else "function", "rank": "F", "complexity": cc, "lineno": 1, "endline": 9,
           "name": name, "col_offset": 0, "closures": list(closures)}
    if classname:
        row["classname"] = classname
    return row


def report(**files):
    return json.dumps({path.replace("__", "/"): blocks for path, blocks in files.items()})


class RadonRatchet(unittest.TestCase):
    def counts(self, text):
        return count_findings(parse_radon(text))

    def test_only_rank_e_and_f_are_findings(self):
        text = report(a=[block("big", 31), block("edge", 30), block("small", 5)])
        self.assertEqual(self.counts(text), {"radon|a|cc|big": 31})

    def test_class_and_closure_names_are_part_of_the_key(self):
        text = report(a=[block("run", 40, classname="Game", closures=[block("inner", 33)])])
        self.assertEqual(self.counts(text), {"radon|a|cc|Game.run": 40, "radon|a|cc|Game.run.inner": 33})

    def test_a_windows_path_is_the_same_key(self):
        win = json.dumps({"game_parts" + chr(92) + "turn.py": [block("f", 35)]})
        self.assertEqual(self.counts(win), {"radon|game_parts/turn.py|cc|f": 35})

    def test_simpler_is_fine_more_complex_and_new_fail(self):
        base = self.counts(report(a=[block("f", 50), block("g", 40)]))
        self.assertEqual(compare(base, self.counts(report(a=[block("f", 44), block("g", 40)]))), [])
        self.assertEqual(compare(base, self.counts(report(a=[block("f", 51), block("g", 40)]))),
                         ["radon|a|cc|f: 51 found, baseline allows 50"])
        self.assertEqual(compare(base, self.counts(report(a=[block("f", 50), block("g", 40), block("h", 31)]))),
                         ["radon|a|cc|h: 31 found, baseline allows 0"])

    def test_a_function_that_drops_below_the_bar_leaves_the_findings(self):
        base = self.counts(report(a=[block("f", 50)]))
        self.assertEqual(compare(base, self.counts(report(a=[block("f", 30)]))), [])

    def test_a_radon_error_or_garbage_is_a_tool_error(self):
        for text in ("", "not json", "[]", json.dumps({"a.py": "SyntaxError"})):
            with self.subTest(text=text), self.assertRaises(ToolOutputError):
                parse_radon(text)

    def test_the_committed_baseline_is_loadable_and_names_the_three_split_functions(self):
        baseline = load_baseline(ratchet.BASELINE_DIR / "radon.json")
        for key in ("radon|game_parts/turn.py|cc|_run_player_turn_internal",
                    "radon|game_parts/turn.py|cc|_dispatch_player_turn",
                    "radon|game_parts/narration_safety.py|cc|_narration_safety_decision"):
            self.assertIn(key, baseline)
        self.assertTrue(all(v >= ratchet.RADON_MIN_CC for v in baseline.values()))


if __name__ == "__main__":
    unittest.main()
