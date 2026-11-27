"""D-552: every long function locked in size_budget.json has a shrink row in the quality document."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIZE_BUDGET = HERE / "engine_split_locks" / "size_budget.json"
QUALITY_DOC = HERE.parents[2] / "docs" / "agents" / "kalite-taramasi-20261124.md"


class EveryLongFunctionHasAShrinkRow(unittest.TestCase):
    def test_every_long_function_has_shrink_row(self):
        """D-552: each `long_functions` entry of size_budget.json has a row in the quality document with a plan."""
        if not QUALITY_DOC.is_file():
            self.skipTest("docs/ is not part of the test tree; CI checks it")
        text = QUALITY_DOC.read_text(encoding="utf-8")
        _, _, section = text.partition("## Küçültme planı (D-552)")
        self.assertTrue(section, "the quality document has no D-552 shrink section")
        rows = {cells[0].strip("` "): cells for cells in
                (line.strip().strip("|").split("|") for line in section.splitlines() if line.startswith("| `"))}
        lock = json.loads(SIZE_BUDGET.read_text(encoding="utf-8"))["long_functions"]
        for key in lock:
            with self.subTest(function=key):
                self.assertIn(key, rows, f"{key} has no shrink row")
                self.assertGreaterEqual(len(rows[key]), 3)
                self.assertTrue(rows[key][-1].strip(), f"{key} has an empty plan")
        for key in rows:
            self.assertIn(key, lock, f"{key} has a row but is no longer a locked long function")


__all__ = ["EveryLongFunctionHasAShrinkRow"]

if __name__ == "__main__":
    unittest.main()
