"""Tests for the layout tool (scripts/engine_split/blank_runs.py): top-level blank runs beyond two (T7.1)."""
from __future__ import annotations

import ast
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split import blank_runs  # noqa: E402


def _lines(text: str) -> list[str]:
    return text.split("\n")


def _cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = blank_runs.main(list(argv))
    return code, out.getvalue()


class BlankRunsFixtureTests(unittest.TestCase):
    def _file(self, data: bytes) -> Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "fixture.py"
        path.write_bytes(data)
        return path

    def test_a_run_of_five_between_two_defs_keeps_two(self):
        old = "def a():\n    pass\n" + "\n" * 5 + "def b():\n    pass\n"
        self.assertEqual(blank_runs.find(_lines(old)), [5, 6, 7])
        path = self._file(old.encode("utf-8"))
        self.assertEqual(_cli("--check", str(path)), (1, f"RUNS {path} 3\n"))
        self.assertEqual(_cli("--apply", str(path)), (0, f"DELETED {path} 3\n"))
        new = path.read_bytes().decode("utf-8")
        self.assertEqual(new, "def a():\n    pass\n\n\ndef b():\n    pass\n")
        self.assertEqual(blank_runs.verify(old, new), [])
        self.assertEqual(_cli("--check", str(path)), (0, f"RUNS {path} 0\n"))

    def test_blank_lines_inside_a_statement_are_kept(self):
        text = ('X = """a\n\n\n\n\nb"""\n\n'
                "def f():\n    x = 1\n\n\n\n\n    return x\n")
        self.assertEqual(blank_runs.find(_lines(text)), [])

    def test_a_comment_block_keeps_its_place(self):
        old = "def a():\n    pass\n\n\n\n# note\ndef b():\n    pass\n"
        self.assertEqual(blank_runs.find(_lines(old)), [5])
        path = self._file(old.encode("utf-8"))
        _cli("--apply", str(path))
        new = path.read_text(encoding="utf-8")
        self.assertEqual(new, "def a():\n    pass\n\n\n# note\ndef b():\n    pass\n")
        self.assertEqual(blank_runs.verify(old, new), [])

    def test_apply_keeps_crlf_and_every_other_byte(self):
        old_lines = ["def a():", "    pass", "", "", "", "", "", "def b():", "    return 'ç'  # é", ""]
        old = "\r\n".join(old_lines).encode("utf-8")
        self.assertEqual(blank_runs.find(old.decode("utf-8").split("\n")), [5, 6, 7])
        path = self._file(old)
        self.assertEqual(_cli("--apply", str(path)), (0, f"DELETED {path} 3\n"))
        kept = [line for number, line in enumerate(old_lines, 1) if number not in (5, 6, 7)]
        self.assertEqual(path.read_bytes(), "\r\n".join(kept).encode("utf-8"))

    def test_verify_refuses_a_changed_line_and_a_lost_comment(self):
        old = "def a():\n    return 1  # one\n\n\n\n\ndef b():\n    pass\n"
        good = "def a():\n    return 1  # one\n\n\ndef b():\n    pass\n"
        self.assertEqual(blank_runs.verify(old, good), [])
        changed = blank_runs.verify(old, good.replace("return 1", "return 2"))
        self.assertTrue(any("ast" in finding for finding in changed), changed)
        lost = blank_runs.verify(old, good.replace("  # one", ""))
        self.assertTrue(any("comment" in finding for finding in lost), lost)

    def test_verify_refuses_a_blank_line_removed_inside_a_def(self):
        old = "def a():\n    x = 1\n\n    return x\n"
        new = "def a():\n    x = 1\n    return x\n"
        self.assertEqual(ast.dump(ast.parse(old)), ast.dump(ast.parse(new)))
        findings = blank_runs.verify(old, new)
        self.assertTrue(findings)
        self.assertTrue(any("3" in finding for finding in findings), findings)

    def test_a_form_feed_inside_a_string_does_not_shift_lines(self):
        text = 'X = "a\x0cb"\n' + "\n" * 5 + "def b():\n    pass\n"
        self.assertEqual(blank_runs.find(_lines(text)), [4, 5, 6])

    def test_verify_refuses_a_line_inside_a_def_even_if_find_returns_it(self):
        old = "def a():\n    x = 1\n\n    return x\n"
        new = "def a():\n    x = 1\n    return x\n"
        with mock.patch.object(blank_runs, "find", return_value=[3]):
            findings = blank_runs.verify(old, new)
        self.assertTrue(any("inside" in finding for finding in findings), findings)


if __name__ == "__main__":
    unittest.main()
