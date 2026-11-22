"""Size latch: game.py and game_parts/*.py stay within a line budget; long functions cannot appear or grow.

Raising any number in engine_split_locks/size_budget.json needs an approval-list row and Kadir (spec decision 10).
Lowering a number needs no approval.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.inventory import top_level_index  # noqa: E402
from api.tests.engine_sources import engine_source_files  # noqa: E402

LOCK_PATH = Path(__file__).parent / "engine_split_locks" / "size_budget.json"
LOCK = json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def budget_findings(actual: dict[str, int], lock: dict) -> list[str]:
    """A file over its budget; a budget more than `slack` above the real size; a part with no entry over `part_max`."""
    out = []
    for name, size in sorted(actual.items()):
        if name in lock["files"]:
            budget = lock["files"][name]
            if size > budget:
                out.append(f"{name}: {size} lines, over its budget {budget}")
            elif budget - size > lock["slack"]:
                out.append(f"{name}: budget {budget} is more than {lock['slack']} above the real size {size}; lower it")
        elif size > lock["part_max"]:
            out.append(f"{name}: {size} lines, over the part limit {lock['part_max']} and has no budget entry")
    return out


def long_function_findings(actual: dict[str, int], lock: dict) -> list[str]:
    """A function of `long_function_min` lines or more that is not listed, or longer than its entry."""
    out = []
    for name, lines in sorted(actual.items()):
        if lines < lock["long_function_min"]:
            continue
        if name not in lock["long_functions"]:
            out.append(f"{name}: {lines} lines and not in long_functions")
        elif lines > lock["long_functions"][name]:
            out.append(f"{name}: grew to {lines} lines, lock has {lock['long_functions'][name]}")
    return out


def real_sizes() -> dict[str, int]:
    return {p.relative_to(ROOT).as_posix(): len(p.read_text(encoding="utf-8").splitlines())
            for p in engine_source_files(ROOT)}


def real_function_lengths() -> dict[str, int]:
    """`<file>::<name>` -> lines (D-351: keyed by file too, so a same-named function in another file is its own entry)."""
    out: dict[str, int] = {}
    for p in engine_source_files(ROOT):
        for row in top_level_index(p):
            if row["kind"] == "function":
                key = f"{p.relative_to(ROOT).as_posix()}::{row['name']}"
                out[key] = max(out.get(key, 0), row["lines"])
    return out


class SizeBudgetTests(unittest.TestCase):
    def test_the_engine_fits_its_budget(self):
        self.assertEqual(budget_findings(real_sizes(), LOCK), [])
        self.assertEqual(long_function_findings(real_function_lengths(), LOCK), [])

    def test_one_line_over_is_red(self):
        self.assertNotEqual(budget_findings({"game.py": LOCK["files"]["game.py"] + 1}, LOCK), [])

    def test_a_budget_cannot_hoard_room(self):
        self.assertNotEqual(budget_findings({"game.py": LOCK["files"]["game.py"] - 51}, LOCK), [])
        self.assertEqual(budget_findings({"game.py": LOCK["files"]["game.py"] - 50}, LOCK), [])

    def test_a_part_may_not_pass_2500_lines(self):
        self.assertNotEqual(budget_findings({"game.py": LOCK["files"]["game.py"], "game_parts/x.py": 2501}, LOCK), [])
        self.assertEqual(budget_findings({"game.py": LOCK["files"]["game.py"], "game_parts/x.py": 2500}, LOCK), [])

    def test_long_functions_cannot_grow_or_appear(self):
        self.assertNotEqual(long_function_findings({"game.py::brand_new": 151}, LOCK), [])
        key = "game_parts/turn.py::_run_player_turn_internal"
        grown = {key: LOCK["long_functions"][key] + 1}
        self.assertNotEqual(long_function_findings(grown, LOCK), [])
        self.assertEqual(long_function_findings({"game.py::brand_new": 150}, LOCK), [])

    def test_long_functions_are_keyed_by_file_and_name(self):
        # D-351: a bare name (`run`) would let a same-named function in another file share its budget
        files = set(real_sizes())
        for key in LOCK["long_functions"]:
            file, sep, name = key.partition("::")
            self.assertTrue(sep and file in files and name.isidentifier(), key)
        lengths = real_function_lengths()
        self.assertTrue(lengths and all("::" in key for key in lengths))
        self.assertEqual(lengths["game_parts/terminal.py::run"], LOCK["long_functions"]["game_parts/terminal.py::run"])

    def test_the_lock_matches_the_spec_values(self):
        self.assertEqual((LOCK["part_max"], LOCK["slack"], LOCK["long_function_min"]), (2500, 50, 151))


if __name__ == "__main__":
    unittest.main()
