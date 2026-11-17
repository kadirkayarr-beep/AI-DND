"""Tests for the move equivalence check (scripts/engine_split/move_check.py)."""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.move_block import move  # noqa: E402
from engine_split.move_check import check_move, comment_counts  # noqa: E402

BASE = "K = 1\n\n# why roll exists (D-123)\ndef roll():\n    return helper() + K  # keep\n\ndef helper():\n    return 2\n"
GOOD_GAME = "K = 1\n\nfrom game_parts.dice import roll\n\ndef helper():\n    return 2\n"
GOOD_PART = "import game\n\n# why roll exists (D-123)\ndef roll():\n    return game.helper() + game.K  # keep\n"
MOVED = {"roll": "dice.py"}
NO_LOCK = {"functions": {}}


class MoveCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name) / "base"
        self.new = Path(self._tmp.name) / "new"

    def build(self, base=BASE, game=GOOD_GAME, part=GOOD_PART, newline=None):
        for root, files in ((self.base, {"game.py": base}), (self.new, {"game.py": game, "game_parts/dice.py": part})):
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode("utf-8") if newline is None or root is self.base
                                 else text.replace("\n", newline).encode("utf-8"))

    def check(self, tier="normal", sensitive=NO_LOCK, manual=()):
        return check_move(self.base, self.new, MOVED, sensitive, tier, list(manual))

    def test_a_clean_move_is_equivalent(self):
        self.build()
        result = self.check()
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["comments_base"], result["comments_now"])

    def test_a_changed_operator_is_reported(self):
        self.build(part=GOOD_PART.replace("+", "-"))
        self.assertTrue(self.check()["changed"])

    def test_a_deleted_comment_is_reported(self):
        self.build(part=GOOD_PART.replace("  # keep", ""))
        result = self.check()
        self.assertTrue(result["changed"])
        self.assertEqual(result["comments_now"], result["comments_base"] - 1)

    def test_a_dropped_leading_comment_is_reported(self):
        self.build(part=GOOD_PART.replace("# why roll exists (D-123)\n", ""))
        self.assertTrue(self.check()["changed"])

    def test_ast_unparse_output_is_reported(self):
        body = ast.unparse(ast.parse("def roll():\n    return game.helper() + game.K"))
        self.build(part="import game\n\n" + body + "\n")
        self.assertTrue(self.check()["changed"])

    def test_an_extra_edit_in_game_py_is_reported(self):
        self.build(game=GOOD_GAME.replace("return 2", "return 3"))
        self.assertTrue(self.check()["changed"])

    def test_a_deleted_unmoved_line_in_game_py_is_reported(self):
        self.build(game=GOOD_GAME.replace("def helper():\n    return 2\n", ""))
        self.assertTrue(self.check()["changed"])

    def test_a_sensitive_name_needs_the_strong_tier(self):
        self.build()
        lock = {"functions": {"roll": ["money"]}}
        self.assertTrue(self.check(tier="normal", sensitive=lock)["changed"])
        self.assertEqual(self.check(tier="strong", sensitive=lock)["changed"], [])

    def test_crlf_and_lf_give_the_same_verdict(self):
        self.build(base=BASE.replace("\n", "\r\n"), game=GOOD_GAME.replace("\n", "\r\n"), part=GOOD_PART.replace("\n", "\r\n"))
        self.assertEqual(self.check()["changed"], [])

    def test_an_lf_base_against_a_crlf_working_copy_is_equivalent(self):  # F15: git archive gives LF
        self.build(newline="\r\n")
        self.assertEqual(self.check()["changed"], [])

    def test_a_statement_after_the_import_on_one_line_is_reported(self):  # review 1
        self.build(game=GOOD_GAME.replace("import roll", "import roll; K = 2"))
        self.assertTrue(self.check()["changed"])

    def test_an_import_of_a_name_that_was_not_moved_is_reported(self):  # review 1
        self.build(game=GOOD_GAME.replace("import roll", "import roll, helper"))
        self.assertTrue(self.check()["changed"])

    def test_extra_statements_on_a_part_import_line_are_reported(self):  # review 2
        self.build(part=GOOD_PART.replace("import game\n", "import game; import os; os.x = 1\n"))
        self.assertTrue(self.check()["changed"])

    def test_a_parenthesised_part_import_is_allowed(self):  # review 2
        header = "import game\nfrom os import (\n    path,\n    sep,\n)\n"
        self.build(part=GOOD_PART.replace("import game\n", header))
        self.assertEqual(self.check()["changed"], [])

    def test_a_copy_that_leaves_the_block_in_game_py_is_reported(self):  # review 3 (no comments, so the count cannot catch it)
        base = BASE.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        part = GOOD_PART.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        self.build(base=base, game=base.replace("def helper", "from game_parts.dice import roll\n\ndef helper"), part=part)
        self.assertTrue(self.check()["changed"])

    def test_a_body_only_deletion_in_game_py_is_reported(self):  # review 3 (no comments)
        base = BASE.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        part = GOOD_PART.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        game = "K = 1\n\nfrom game_parts.dice import roll\n\ndef roll():\n\ndef helper():\n    return 2\n"
        self.build(base=base, game=game, part=part)
        self.assertTrue(self.check()["changed"])

    def test_a_manual_line_in_game_py_is_exempt_and_echoed(self):
        self.build(game=GOOD_GAME.replace("K = 1", "K = 2"))
        self.assertTrue(self.check()["changed"])
        result = self.check(manual=["game.py:1:test"])
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["manual"], ["game.py:1:test"])

    def test_a_hand_written_part_line_is_reported_unless_manual(self):  # F16
        part = GOOD_PART.replace("import game\n", "import game\nEXTRA = 1\n")
        self.build(part=part)
        self.assertTrue(self.check()["changed"])
        self.assertEqual(self.check(manual=["dice.py:2:header constant"])["changed"], [])

    def test_a_part_header_of_import_lines_is_allowed(self):  # F16
        self.build(part=GOOD_PART.replace("import game\n", "import re\nimport game\nfrom pathlib import Path\n"))
        self.assertEqual(self.check()["changed"], [])

    def test_a_missing_part_or_block_is_reported(self):
        self.build()
        self.assertTrue(check_move(self.base, self.new, {"nope": "dice.py"}, NO_LOCK, "normal")["changed"])
        self.assertTrue(check_move(self.base, self.new, {"roll": "gone.py"}, NO_LOCK, "normal")["changed"])

    def test_comment_counts_cover_game_py_and_every_part(self):
        self.build(base="# a\n# b\nX = 1\n", game="# a\nX = 1\n", part="# b\n")
        self.assertEqual(comment_counts(self.base, self.new), (2, 2))

    def test_round_trip_move_output_is_equivalent(self):  # Task 6 Step 4: move() then check_move()
        self.build(game=BASE, part="import game\n")
        move(self.new / "game.py", self.new / "game_parts" / "dice.py", ["roll"], set())
        self.assertEqual(self.check()["changed"], [])


if __name__ == "__main__":
    unittest.main()
