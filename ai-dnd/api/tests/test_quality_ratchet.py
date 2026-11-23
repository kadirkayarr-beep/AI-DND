"""Quality gate ratchet core: line-free keys, counts, shrink-only baselines."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

BS = chr(92)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from quality_gate import ratchet  # noqa: E402
from quality_gate.ratchet import (  # noqa: E402
    ToolOutputError,
    baseline_growth,
    compare,
    count_findings,
    finding_key,
    parse_ruff,
)


def ruff_report(line: int, path: str = "a/b.py", crlf: bool = False) -> str:
    item = {
        "code": "F401",
        "message": "`os` imported but unused",
        "filename": path,
        "location": {"row": line, "column": 1},
    }
    text = json.dumps([item], indent=2)
    return text.replace("\n", "\r\n") if crlf else text


class RatchetCompareTests(unittest.TestCase):
    def test_line_shift_is_not_new(self):
        base = count_findings(parse_ruff(ruff_report(10)))
        cur = count_findings(parse_ruff(ruff_report(90)))
        self.assertEqual(compare(base, cur), [])

    def test_second_identical_finding_is_new(self):
        k = finding_key("ruff", "a/b.py", "F401", "os")
        msgs = compare({k: 1}, {k: 2})
        self.assertEqual(len(msgs), 1)
        self.assertIn(k, msgs[0])

    def test_new_key_fails_and_fixed_key_passes(self):
        old = finding_key("ruff", "a.py", "F401", "os")
        new = finding_key("ruff", "b.py", "F401", "sys")
        self.assertEqual(len(compare({old: 1}, {old: 1, new: 1})), 1)
        self.assertEqual(compare({old: 1}, {}), [])

    def test_windows_path_and_crlf_same_key(self):
        self.assertEqual(
            finding_key("ruff", "a" + BS + "b.py", "F401", "os"),
            finding_key("ruff", "a/b.py", "F401", "os"),
        )
        self.assertEqual(finding_key("ruff", "./a/b.py", "F401", "os"), "ruff|a/b.py|F401|os")
        self.assertEqual(
            parse_ruff(ruff_report(3, crlf=True)),
            parse_ruff(ruff_report(3, path="a" + BS + "b.py")),
        )

    def test_empty_or_garbage_output_is_an_error(self):
        for bad in ("", "   \n", "Traceback (most recent call last): boom"):
            with self.assertRaises(ToolOutputError):
                parse_ruff(bad)
        self.assertEqual(parse_ruff("[]"), [])


class RatchetAbsolutePathTests(unittest.TestCase):
    def keys(self, path: str, root: str) -> list[str]:
        return parse_ruff(ruff_report(1, path=path), root=root)

    def test_absolute_windows_and_linux_paths_give_same_key(self):
        win = self.keys("C:" + BS + "Work" + BS + "ai-dnd" + BS + "a" + BS + "b.py", "C:/Work/ai-dnd")
        lin = self.keys("/home/runner/w/ai-dnd/a/b.py", "/home/runner/w/ai-dnd")
        self.assertEqual(win, lin)
        self.assertEqual(win, ["ruff|a/b.py|F401|os"])

    def test_windows_root_is_case_insensitive(self):
        self.assertEqual(self.keys("c:/work/AI-DND/a/b.py", "C:/Work/ai-dnd"), ["ruff|a/b.py|F401|os"])

    def test_path_outside_root_stays_absolute(self):
        self.assertEqual(self.keys("/other/x.py", "/home/r/ai-dnd"), ["ruff|/other/x.py|F401|os"])

    def test_non_dict_item_is_tool_error(self):
        with self.assertRaises(ToolOutputError):
            parse_ruff("[1, 2]")


class RatchetCliTests(unittest.TestCase):
    def run_cli(self, mode: str, tool: str, report: Path, base_dir: Path):
        """In-process: the test slot blocks child processes."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ratchet.main([mode, tool, str(report), "--baseline-dir", str(base_dir)])
        return types.SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())

    def test_update_refuses_to_grow(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report = tmp / "r.json"
            base_dir = tmp / "baselines"
            base_dir.mkdir()
            report.write_text(ruff_report(1), encoding="utf-8")
            self.assertEqual(self.run_cli("update", "ruff", report, base_dir).returncode, 0)
            target = base_dir / "ruff.json"
            before = target.read_bytes()
            two = json.loads(ruff_report(1)) * 2
            report.write_text(json.dumps(two), encoding="utf-8")
            res = self.run_cli("update", "ruff", report, base_dir)
            self.assertEqual(res.returncode, 3)
            self.assertIn("baseline may only shrink", res.stdout + res.stderr)
            self.assertEqual(target.read_bytes(), before)

    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report = tmp / "r.json"
            base_dir = tmp / "baselines"
            base_dir.mkdir()
            report.write_text(ruff_report(1), encoding="utf-8")
            self.run_cli("update", "ruff", report, base_dir)
            self.assertEqual(self.run_cli("check", "ruff", report, base_dir).returncode, 0)
            report.write_text(ruff_report(1, path="new.py"), encoding="utf-8")
            self.assertEqual(self.run_cli("check", "ruff", report, base_dir).returncode, 1)
            report.write_text("", encoding="utf-8")
            self.assertEqual(self.run_cli("check", "ruff", report, base_dir).returncode, 2)

    def test_missing_report_file_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.assertEqual(self.run_cli("check", "ruff", tmp / "nope.json", tmp).returncode, 2)

    def test_corrupt_baseline_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "ruff.json").write_text("{not json", encoding="utf-8")
            rep = tmp / "r.json"
            rep.write_text("[]", encoding="utf-8")
            self.assertEqual(self.run_cli("check", "ruff", rep, tmp).returncode, 2)
            self.assertEqual(self.run_cli("update", "ruff", rep, tmp).returncode, 2)

    def test_ruff_key_ignores_line_numbers_in_message(self):
        def key(msg):
            rep = json.dumps([{"filename": "a.py", "code": "F811", "message": msg}])
            return ratchet.parse_ruff(rep, root="/r")
        self.assertEqual(
            key("Redefinition of unused `x` from line 3"),
            key("Redefinition of unused `x` from line 40"),
        )
        self.assertEqual(key("Unquoted thing at line 3"), key("Unquoted thing at line 40"))

    def test_baseline_io_is_sorted_lf_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "b.json"
            ratchet.write_baseline(p, {"b": 1, "a": 2})
            raw = p.read_bytes()
            self.assertNotIn(b"\r", raw)
            self.assertLess(raw.index(b'"a"'), raw.index(b'"b"'))
            self.assertEqual(ratchet.load_baseline(p), {"a": 2, "b": 1})


class BaselineShrinkTests(unittest.TestCase):
    def test_growth_is_listed(self):
        out = baseline_growth({"a": 1, "b": 2}, {"a": 2, "b": 2, "c": 1})
        self.assertEqual(len(out), 2)
        self.assertIn("a", out[0])
        self.assertIn("c", out[1])

    def test_shrink_and_equal_pass(self):
        self.assertEqual(baseline_growth({"a": 2, "b": 1}, {"a": 1, "b": 1}), [])
        self.assertEqual(baseline_growth({"a": 2}, {}), [])

    def test_first_introduction_passes(self):
        self.assertEqual(baseline_growth({}, {}), [])


class CheckShrinkCliTests(unittest.TestCase):
    def run_cli(self, new_counts, git_result):
        """git is mocked: the test slot blocks child processes."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ruff.json"
            f.write_text(json.dumps(new_counts), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(ratchet.subprocess, "run", return_value=git_result) as run, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = ratchet.main(["check-shrink", str(f), "origin/main"])
            return code, out.getvalue() + err.getvalue(), run

    @staticmethod
    def git(code, out="", err=""):
        return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)

    def test_growth_exits_1(self):
        code, text, run = self.run_cli({"a": 2}, self.git(0, '{"a": 1}'))
        self.assertEqual(code, 1)
        self.assertIn("a", text)
        self.assertIn("origin/main:", " ".join(run.call_args[0][0]))

    def test_shrink_exits_0(self):
        self.assertEqual(self.run_cli({"a": 1}, self.git(0, '{"a": 2}'))[0], 0)

    def test_file_absent_at_base_is_first_introduction(self):
        err = "fatal: path 'x/ruff.json' exists on disk, but not in 'origin/main'"
        self.assertEqual(self.run_cli({"a": 5}, self.git(128, "", err))[0], 0)
        err2 = "fatal: path 'x/ruff.json' does not exist in 'origin/main'"
        self.assertEqual(self.run_cli({"a": 5}, self.git(128, "", err2))[0], 0)

    def test_other_git_error_exits_2(self):
        err = "fatal: invalid object name 'origin/main'."
        self.assertEqual(self.run_cli({"a": 1}, self.git(128, "", err))[0], 2)

    def test_garbage_base_content_exits_2(self):
        self.assertEqual(self.run_cli({"a": 1}, self.git(0, "{not json"))[0], 2)

    def test_non_object_base_content_exits_2(self):
        for body in ("[1, 2]", "null", '{"a": null}', '{"a": [1]}'):
            self.assertEqual(self.run_cli({"a": 1}, self.git(0, body))[0], 2, body)

    def test_non_int_or_negative_base_counts_exit_2(self):
        for body in ('{"a": 1.9}', '{"a": true}', '{"a": "3"}', '{"a": -1}'):
            self.assertEqual(self.run_cli({"a": 1}, self.git(0, body))[0], 2, body)

    def test_git_missing_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "r.json"
            f.write_text("{}", encoding="utf-8")
            with mock.patch.object(ratchet.subprocess, "run", side_effect=OSError("no git")), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ratchet.main(["check-shrink", str(f), "origin/main"]), 2)


if __name__ == "__main__":
    unittest.main()
