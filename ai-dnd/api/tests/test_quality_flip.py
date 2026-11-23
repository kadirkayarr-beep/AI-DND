"""Quality gate Task 9: size_lock.json shrink check (ratchet CLI) and the flip to blocking (workflow policy)."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from quality_gate import size_lock_shrink  # noqa: E402
from api.tests.test_quality_policy import WORKFLOW, _job_steps, _job_text  # noqa: E402


class SizeLockShrinkTests(unittest.TestCase):
    """size_lock.json: no budget may rise, no long function may appear or grow, limits may not loosen."""

    @staticmethod
    def git(code, out="", err=""):
        return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)

    @staticmethod
    def lock(files=None, long_functions=None, ts_files=None, part_max=2500, slack=50, long_function_min=151):
        return {"part_max": part_max, "slack": slack, "long_function_min": long_function_min,
                "files": files or {}, "long_functions": long_functions or {}, "ts_files": ts_files or {}}

    def run_cli(self, new, git_result):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "size_lock.json"
            f.write_text(json.dumps(new), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(size_lock_shrink.subprocess, "run", return_value=git_result), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = size_lock_shrink.main([str(f), "origin/main"])
            return code, out.getvalue() + err.getvalue()

    def base(self, **kw):
        return self.git(0, json.dumps(self.lock(**kw)))

    def test_raised_budget_exits_1(self):
        code, text = self.run_cli(self.lock(files={"a.py": 101}), self.base(files={"a.py": 100}))
        self.assertEqual(code, 1)
        self.assertIn("a.py", text)
        self.assertEqual(self.run_cli(self.lock(ts_files={"artifacts/x/src/a.ts": 11}), self.base(ts_files={"artifacts/x/src/a.ts": 10}))[0], 1)

    def test_lowered_removed_and_equal_exit_0(self):
        old = self.base(files={"a.py": 100, "b.py": 5}, ts_files={"t.ts": 9}, long_functions={"a.py::f": 200})
        new = self.lock(files={"a.py": 90}, ts_files={"t.ts": 9}, long_functions={"a.py::f": 180})
        self.assertEqual(self.run_cli(new, old)[0], 0)

    def test_new_file_entry_above_part_max_exits_1(self):
        self.assertEqual(self.run_cli(self.lock(files={"n.py": 2501}), self.base())[0], 1)
        self.assertEqual(self.run_cli(self.lock(ts_files={"artifacts/x/src/n.ts": 2501}), self.base())[0], 1)

    def test_new_small_file_entry_exits_0(self):
        self.assertEqual(self.run_cli(self.lock(files={"n.py": 40}), self.base())[0], 0)

    def test_new_or_grown_long_function_exits_1(self):
        self.assertEqual(self.run_cli(self.lock(long_functions={"a.py::g": 160}), self.base())[0], 1)
        old = self.base(long_functions={"a.py::f": 200})
        self.assertEqual(self.run_cli(self.lock(long_functions={"a.py::f": 201}), old)[0], 1)

    def test_loosened_limits_exit_1(self):
        for kw in ({"part_max": 2501}, {"slack": 51}, {"long_function_min": 150}):
            self.assertEqual(self.run_cli(self.lock(**kw), self.base())[0], 1, kw)

    def test_absent_at_base_is_first_introduction(self):
        err = "fatal: path 'x' exists on disk, but not in 'origin/main'"
        self.assertEqual(self.run_cli(self.lock(files={"a.py": 5}), self.git(128, "", err))[0], 0)

    def test_git_failure_or_bad_json_exits_2(self):
        self.assertEqual(self.run_cli(self.lock(), self.git(128, "", "fatal: bad ref"))[0], 2)
        self.assertEqual(self.run_cli(self.lock(), self.git(0, "{nope"))[0], 2)
        self.assertEqual(self.run_cli(self.lock(), self.git(0, "[1]"))[0], 2)
        self.assertEqual(self.run_cli({"files": {}}, self.base())[0], 2)  # new lock missing keys
        self.assertEqual(self.run_cli(self.lock(files={"a.py": "x"}), self.base())[0], 2)


class QualityFlipToBlockingTest(unittest.TestCase):
    """Task 9: the gate blocks; only fallow and skylos may still be report-only; the measure job is gone."""

    def test_measure_job_is_gone(self):
        self.assertEqual(_job_text("measure"), "")
        self.assertNotIn("measure:", WORKFLOW.read_text(encoding="utf-8"))

    def test_only_fallow_and_skylos_continue_on_error(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for job in ("python-gate", "secrets-gate", "ui-gate"):
            for step in _job_steps(_job_text(job)):
                if "continue-on-error" in step:
                    self.assertTrue("fallow@" in step or "skylos " in step, step)
        self.assertNotIn("continue-on-error", _job_text("python-gate"))
        self.assertNotIn("continue-on-error", _job_text("secrets-gate"))
        self.assertEqual(text.count("continue-on-error"), 2)

    def test_three_gate_jobs_exist(self):
        for job in ("python-gate", "secrets-gate", "ui-gate"):
            self.assertTrue(_job_text(job), job)

    def test_size_lock_shrink_step_in_python_gate(self):
        steps = [s for s in _job_steps(_job_text("python-gate")) if "size_lock_shrink" in s]
        self.assertEqual(len(steps), 1)
        self.assertIn("scripts/quality_gate/size_lock.json origin/main", steps[0])
        self.assertIn("git fetch --no-tags origin main", steps[0])
        self.assertNotIn("continue-on-error", steps[0])


if __name__ == "__main__":
    unittest.main()
