"""Evidence runner contracts, isolated from game state and live HTTP."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_regression_evidence.py"
spec = importlib.util.spec_from_file_location("regression_evidence", SCRIPT)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


class EvidenceRunnerTests(unittest.TestCase):
    def run_fixture(self, code, *selectors):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "evidence_fixture.py").write_text(code, encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(directory), str(ROOT)]))
            command = [sys.executable, str(SCRIPT), "--archive-root", str(directory / "archive"),
                       *(selectors or ["evidence_fixture"])]
            process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            archives = list((directory / "archive").glob("*/run.json"))
            self.assertEqual(len(archives), 1, process.stderr)
            data = json.loads(archives[0].read_text())
            log = archives[0].with_name("output.log").read_bytes()
            self.assertEqual(data["exit_status"], process.returncode)
            self.assertEqual(data["command"]["argv"], command)
            self.assertEqual(data["output_log_sha256"], owner.hashlib.sha256(log).hexdigest())
            self.assertLessEqual(data["started_at"], data["ended_at"])
            self.assertEqual(data["run_label"], "NEW RUN")
            self.assertFalse(data["historical_certification"])
            return process, data

    def test_duplicate_function_module_selection_executes_once(self):
        process, data = self.run_fixture(
            "def test_ok():\n    print('FUNCTION EXECUTED')\n",
            "evidence_fixture", "evidence_fixture", "evidence_fixture.test_ok")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.count("FUNCTION EXECUTED"), 1)
        self.assertEqual(data["selected_test_ids"], ["evidence_fixture.test_ok"])
        self.assertEqual(data["executed_test_ids"], data["selected_test_ids"])
        self.assertEqual(data["deduplication"]["duplicates_removed"], 2)
        self.assertEqual(data["deduplication"]["selected_occurrences"], 3)
        self.assertEqual(data["deduplication"]["duplicate_ids"], {"evidence_fixture.test_ok": 3})
        self.assertEqual(data["aggregate"]["per_test_outcomes"], {"pass": 1})
        self.assertFalse(data["source_changed_during_run"])

    def test_failures_errors_skips_expected_and_unexpected_are_distinct(self):
        process, data = self.run_fixture("""
import unittest
class Outcomes(unittest.TestCase):
    def test_pass(self): pass
    def test_failure(self): self.fail('fixture failure')
    def test_error(self): raise RuntimeError('fixture error')
    @unittest.skip('fixture skip')
    def test_skip(self): pass
    @unittest.expectedFailure
    def test_expected(self): self.fail('expected')
    @unittest.expectedFailure
    def test_unexpected(self): pass
""")
        self.assertEqual(process.returncode, 1)
        for key in ("failures", "errors", "skips", "expected_failures", "unexpected_successes"):
            self.assertEqual(data["aggregate"][key], 1)
        self.assertEqual(data["aggregate"]["tests_run"], 6)
        self.assertTrue(all(row["ended_at"] for row in data["per_test"]))

    def test_setup_class_error_does_not_claim_test_methods_executed(self):
        process, data = self.run_fixture("""
import unittest
class Broken(unittest.TestCase):
    @classmethod
    def setUpClass(cls): raise RuntimeError('setup failed')
    def test_never(self): pass
""")
        self.assertEqual(process.returncode, 1)
        self.assertEqual(data["executed_test_ids"], [])
        self.assertEqual(data["unexecuted_test_ids"], ["evidence_fixture.Broken.test_never"])
        self.assertEqual(data["aggregate"]["errors"], 1)
        self.assertEqual(data["suite_events"][0]["outcome"], "error")

    def test_failed_subtests_retain_parent_and_individual_details(self):
        process, data = self.run_fixture("""
import unittest
class Subtests(unittest.TestCase):
    def test_values(self):
        for value in range(2):
            with self.subTest(value=value): self.fail(str(value))
""")
        self.assertEqual(process.returncode, 1)
        self.assertEqual(data["aggregate"]["failures"], 2)
        self.assertEqual(data["aggregate"]["tests_run"], 1)
        self.assertEqual(data["per_test"][0]["outcome"], "failure")
        self.assertEqual(len(data["per_test"][0]["events"]), 2)

    def test_import_error_and_empty_selection_fail_closed(self):
        for code in ("raise RuntimeError('bad import')", "VALUE = 1"):
            with self.subTest(code=code):
                process, data = self.run_fixture(code)
                self.assertEqual(process.returncode, 2)
                self.assertEqual(data["status"], "runner_error")
                self.assertIn("runner_error", data)
                self.assertEqual(data["executed_test_ids"], [])

    def test_interruption_retains_started_test_and_nonzero_status(self):
        process, data = self.run_fixture("def test_interrupt():\n    raise KeyboardInterrupt()\n")
        self.assertEqual(process.returncode, 130)
        self.assertEqual(data["status"], "interrupted")
        self.assertEqual(data["executed_test_ids"], ["evidence_fixture.test_interrupt"])
        self.assertNotEqual(data["per_test"][0]["outcome"], "pass")
        self.assertEqual(data["aggregate"]["tests_run"], 1)

    def test_source_hash_changes_with_untracked_content_and_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "Evidence Test"],
                check=True,
            )
            tracked = repo / "ai-dnd/game.py"
            tracked.parent.mkdir()
            tracked.write_text("tracked fixture", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-qm", "fixture baseline"],
                check=True,
            )
            path = repo / "fingerprint.txt"
            path.write_text("first", encoding="utf-8")
            with unittest.mock.patch.object(owner, "ROOT", repo), unittest.mock.patch.object(
                owner, "DEFAULT_ARCHIVE", repo / "archive"
            ):
                first = owner.source_snapshot(repo / "archive")
                path.write_text("second", encoding="utf-8")
                second = owner.source_snapshot(repo / "archive")
                path.unlink()
                third = owner.source_snapshot(repo / "archive")
            self.assertNotEqual(first["working_tree_sha256"], second["working_tree_sha256"])
            self.assertNotEqual(second["working_tree_sha256"], third["working_tree_sha256"])
            self.assertTrue(first["dirty"])
            self.assertEqual(len(first["revision"]), 40)
            self.assertTrue(any(row["path"] == "ai-dnd/game.py" and row["kind"] == "file"
                                for row in first["files"]))

    def test_discovery_and_repeated_class_selection_are_deduplicated(self):
        tests, accounting = owner.select_tests(
            ["api.tests.test_regression_evidence.EvidenceRunnerTests"],
            [str(ROOT / "api/tests")], "test_regression_evidence.py")
        ids = [test.id() for test in tests]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(accounting["duplicates_removed"], len(ids))


if __name__ == "__main__":
    unittest.main()