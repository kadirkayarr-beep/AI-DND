"""The bound-session wrapper filter reads an explicit list of part modules (game.py split, T2.1)."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game  # noqa: E402
from api.tests.engine_sources import engine_source_files  # noqa: E402


class WrapperFilter(unittest.TestCase):
    def test_the_wrapper_filter_reads_an_explicit_part_list(self):
        self.assertEqual(game._PART_MODULES, ())  # Task 18 changes this expected value
        tree = ast.parse(engine_source_files()[0].read_text(encoding="utf-8"))
        assign = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_ENGINE_FUNCTIONS")
        self.assertIn("_PART_MODULES", {n.id for n in ast.walk(assign) if isinstance(n, ast.Name)})


if __name__ == "__main__":
    unittest.main()
