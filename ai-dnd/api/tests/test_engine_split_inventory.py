"""Tests for the game.py split inventory tool (scripts/engine_split/inventory.py)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.inventory import (  # noqa: E402
    call_graph,
    closed_helpers,
    constant_clusters,
    top_level_index,
    verify_claims,
)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, src: str, name: str = "game.py") -> Path:
        path = self.tmp / name
        path.write_text(src, encoding="utf-8")
        return path

    def test_index_block_starts_at_the_comment_directly_above(self):
        src = "# banner\n\n# why f exists\n@dec\ndef f():\n    return 1\n"
        f = next(d for d in top_level_index(self.write(src)) if d["name"] == "f")
        self.assertEqual((f["start"], f["def_line"], f["end"]), (3, 4, 6))

    def test_index_lines_count_def_to_end_without_comment_or_decorator(self):
        src = "# why\n@dec\ndef f():\n    a = 1\n    return a\n"
        f = next(d for d in top_level_index(self.write(src)) if d["name"] == "f")
        self.assertEqual(f["lines"], 3)

    def test_index_kinds_cover_every_top_level_statement(self):
        src = (
            "import os\nfrom re import compile as c\nK, L = 1, 2\nM: int = 3\n"
            "def f():\n    pass\nclass C:\n    pass\nif K:\n    pass\nprint(K)\n"
        )
        got = [(d["name"], d["kind"]) for d in top_level_index(self.write(src))]
        self.assertEqual(
            got,
            [("os", "import"), ("c", "import"), ("K", "assign"), ("L", "assign"),
             ("M", "assign"), ("f", "function"), ("C", "class"),
             ("<If@9>", "other"), ("<Expr@11>", "other")],
        )

    def test_call_graph_ignores_locals_and_attributes(self):
        src = "def a():\n    return 1\ndef b():\n    a = 2\n    return a\ndef c(x):\n    return a() + x.a\n"
        self.assertEqual(call_graph(self.write(src)), {"a": [], "b": [], "c": ["a"]})

    def test_call_graph_sees_names_read_in_nested_scopes(self):
        src = "K = 1\ndef a():\n    return 1\ndef b():\n    def inner():\n        return a() + K\n    return [K for _ in inner()]\n"
        self.assertEqual(call_graph(self.write(src))["b"], ["K", "a"])

    def test_constant_clusters_join_dependent_constants(self):
        src = "import re\nA = 'x'\nB = re.compile(A)\nC = 3\n"
        self.assertEqual(constant_clusters(self.write(src)), [["A", "B"], ["C"]])

    def test_closed_helpers_reference_no_engine_function(self):
        src = "K = 1\ndef a():\n    return K\ndef b():\n    return a()\n"
        self.assertEqual(closed_helpers(self.write(src)), ["a"])

    def test_verify_claims_marks_a_changed_named_set_false_and_a_changed_count_shifted(self):
        game = (
            "from uuid import uuid4\n"
            "def _apply_player_damage():\n    return uuid4()\n"
            "def extra():\n    return uuid4()\n"
        )
        self.write(game)
        (self.tmp / "api" / "tests").mkdir(parents=True)
        (self.tmp / "api" / "tests" / "test_coin_writers.py").write_text(
            'WRITERS = frozenset({"game.py:pay", "x.py:y"})\n', encoding="utf-8")
        rows = {r["claim"]: r for r in verify_claims(self.tmp)}
        uuid_row = next(r for k, r in rows.items() if "uuid4" in k)
        self.assertEqual(uuid_row["status"], "false")
        top = next(r for k, r in rows.items() if k.startswith("top-level functions"))
        self.assertEqual((top["spec_value"], top["measured"], top["status"]), (521, 2, "shifted"))
        coin = next(r for k, r in rows.items() if "WRITERS" in k)
        self.assertEqual(coin["status"], "false")

    def test_verify_claims_on_the_real_engine_returns_valid_rows(self):
        rows = verify_claims(ROOT)
        self.assertGreaterEqual(len(rows), 15)
        for r in rows:
            self.assertEqual(set(r), {"claim", "spec_value", "measured", "status"})
            self.assertIn(r["status"], {"same", "shifted", "false"})


if __name__ == "__main__":
    unittest.main()
