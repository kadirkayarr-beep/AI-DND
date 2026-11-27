"""G2.17: CI discovery and lock guards (D-342, D-340, D-341, D-500, D-553, D-346, D-467).

Checks that CI runs what the debt rows say it runs. The engine start probe and the protected persistence tests run in child processes, so CI runs them (workflow text is checked).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess  # nosec B404 - fixed argv list, no shell
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from api.tests.guard_bound import CHILD_PROCESS, guard_bound
from scripts import protected_tests_run
from scripts.quality_gate import size_lock_shrink

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent

CI = (REPO / ".github" / "workflows" / "ai-dnd-ci.yml").read_text(encoding="utf-8")
QUALITY = (REPO / ".github" / "workflows" / "ai-dnd-quality.yml").read_text(encoding="utf-8")
REGRESSION = ROOT / "test_regression.py"
SIZE_LOCK = ROOT / "scripts" / "quality_gate" / "size_lock.json"
SIZE_BUDGET = Path(__file__).parent / "engine_split_locks" / "size_budget.json"


def _job(text: str, name: str) -> str:
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  \S[^\n]*:\n|\Z)", text, re.S | re.M)
    if match is None:
        raise AssertionError(name)
    return match.group(1)


def _case_ids(suite: unittest.TestSuite) -> list[str]:
    ids: list[str] = []
    for test in suite:
        ids += _case_ids(test) if isinstance(test, unittest.TestSuite) else [test.id()]
    return ids


class TestRegressionScript(unittest.TestCase):
    def test_the_script_starts_every_session_with_a_fixed_seed(self):
        self.assertEqual(re.findall(r"create_session\(\s*\)", REGRESSION.read_text(encoding="utf-8")), [])

    def test_the_script_does_not_patch_the_ollama_module_entry(self):
        # D-340: the second ollama copy is gone; patch.dict(sys.modules) also deleted game_parts imported inside it.
        self.assertNotIn("sys.modules", re.sub(r"assert sys\.modules\[\"game\"\][^\n]*", "", REGRESSION.read_text(encoding="utf-8")))


class TestCiWorkflowSteps(unittest.TestCase):
    def test_ci_runs_the_regression_script_and_demands_thirty_passes(self):
        gate = _job(CI, "bounded-gate")
        self.assertIn("python test_regression.py", gate)
        self.assertIn("Results: 30 passed, 0 failed out of 30", gate)

    def test_ci_runs_the_engine_start_probe(self):
        gate = _job(CI, "bounded-gate")
        self.assertIn("python scripts/engine_split/outside_probe.py", gate)

    def test_ci_checks_that_the_engine_size_budget_only_shrinks(self):
        job = _job(QUALITY, "python-gate")
        self.assertIn("scripts.quality_gate.size_lock_shrink api/tests/engine_split_locks/size_budget.json origin/main", job)

    def test_ci_runs_the_protected_persistence_tests_and_fails_on_a_skip(self):
        # D-467: those nine tests are skipped in every slot run; in CI a skip must fail the job.
        gate = _job(CI, "bounded-gate")
        self.assertIn("scripts/protected_tests_run.py", gate)


class TestProtectedTestsRun(unittest.TestCase):
    def test_the_nine_protected_tests_exist_and_are_named_once(self):
        run = protected_tests_run
        self.assertEqual(len(run.PROTECTED), 9)
        self.assertEqual(len(set(run.PROTECTED)), 9)
        for name in run.PROTECTED:
            loaded = unittest.defaultTestLoader.loadTestsFromName(name)
            self.assertEqual(_case_ids(loaded), [name], name)

    @staticmethod
    def result(tests_run, skipped=(), failures=(), errors=()):
        outcome = unittest.TestResult()
        outcome.testsRun = tests_run
        outcome.skipped, outcome.failures, outcome.errors = list(skipped), list(failures), list(errors)
        return outcome

    def test_a_skip_a_failure_or_a_short_count_is_a_problem(self):
        run = protected_tests_run
        self.assertEqual(run.problems(self.result(9), 9), [])
        self.assertEqual(run.problems(self.result(9, skipped=[("t", "guard-bound")]), 9), ["1 skipped"])
        self.assertEqual(run.problems(self.result(8, errors=[("t", "boom")]), 9), ["1 failed", "ran 8, expected 9"])

    @guard_bound(CHILD_PROCESS)
    def test_the_script_loads_its_tests_when_run_the_way_ci_runs_it(self):
        # A script run has scripts/ first on sys.path; it must still find `api` and `game` (review of G2.17).
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        done = subprocess.run([sys.executable, "scripts/protected_tests_run.py", "--load-only"], cwd=ROOT, env=env,  # nosec B603
                              capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class TestSizeBudgetShrinkCheck(unittest.TestCase):
    @staticmethod
    def budget(files=None, long_functions=None, part_max=2500):
        return {"files": files or {}, "part_max": part_max, "slack": 50, "long_function_min": 151,
                "long_functions": long_functions or {}}

    def run_cli(self, new, old):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "size_budget.json"
            f.write_text(json.dumps(new), encoding="utf-8")
            git = types.SimpleNamespace(returncode=0, stdout=json.dumps(old), stderr="")
            with mock.patch.object(size_lock_shrink.subprocess, "run", return_value=git), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return size_lock_shrink.check_size_lock_shrink(f, "origin/main")

    def test_the_real_budget_file_is_readable_as_a_lock(self):
        size_lock_shrink._size_lock(SIZE_BUDGET.read_text(encoding="utf-8"))

    def test_a_raised_budget_or_new_long_function_fails_and_equal_passes(self):
        old = self.budget(files={"game.py": 1148}, long_functions={"game_parts/a.py::f": 200})
        self.assertEqual(self.run_cli(old, old), 0)
        self.assertEqual(self.run_cli(self.budget(files={"game.py": 1149}, long_functions={"game_parts/a.py::f": 200}), old), 1)
        self.assertEqual(self.run_cli(self.budget(files={"game.py": 1148}, long_functions={"game_parts/a.py::f": 201}), old), 1)
        self.assertEqual(self.run_cli(self.budget(files={"game.py": 1148}, long_functions={"game_parts/a.py::f": 200, "game_parts/a.py::g": 160}), old), 1)


class TestLockEntries(unittest.TestCase):
    def test_the_big_economy_files_have_a_size_lock_entry(self):
        # D-500: without an entry a file may grow to part_max (2500) unnoticed.
        lock = json.loads(SIZE_LOCK.read_text(encoding="utf-8"))["files"]
        for name in ("economic_actions.py", "bold_acts.py", "action_economy.py", "equipment_economy.py", "grounded_action.py"):
            size = len((ROOT / name).read_text(encoding="utf-8").splitlines())
            self.assertIn(name, lock)
            self.assertGreaterEqual(lock[name], size, name)


class TestSmokeScriptDigests(unittest.TestCase):
    SCRIPTS = ("live_narration_smoke.py", "live_phase_c_narrative_smoke.py", "acceptance_test.py")

    def test_saves_and_scripts_share_one_digest_function(self):
        import engine_digest
        from api.persistence import campaign_store
        self.assertIs(campaign_store._engine_digest, engine_digest.engine_digest)

    def test_each_script_prints_the_digest_of_the_whole_engine(self):
        # D-346: a digest of game.py alone does not change when code that moved into game_parts changes.
        for name in self.SCRIPTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("engine_digest(", text, name)
            self.assertNotIn("hashlib", text, name)


if __name__ == "__main__":
    unittest.main()
