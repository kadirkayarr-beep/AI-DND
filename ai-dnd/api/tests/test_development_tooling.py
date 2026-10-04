"""Offline tooling contracts in disposable repos; no game/model/server calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import development_checks as owner
from development_archive import Archive


class DevelopmentToolingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.config = owner.load_config(owner.DEFAULT_CONFIG)
        for name in self.config["required_paths"]:
            path = self.repo / name
            if path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n")
            else:
                path.mkdir(parents=True, exist_ok=True)
                (path / ".keep").write_text("fixture\n")
        package = self.repo / self.config["frontend_package"]
        package.write_text(json.dumps({"scripts": {
            "typecheck": "fixture", "test": "fixture", "build": "fixture"}}))
        self.archive_root = self.repo / "ai-dnd/docs/evidence/development-runs"
        self.config_path = self.repo / "checks.json"
        self.config_path.write_text(json.dumps(self.config))
        (self.repo / ".gitignore").write_text("__pycache__/\n*.py[cod]\n")
        # These commits are fixture-only; never commit the real checkout.
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.name=Tooling Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "offline fixture")
        self.head = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.repo, stderr=subprocess.PIPE,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}).decode()

    @contextlib.contextmanager
    def fixture_owner(self):
        with patch.object(owner, "REPO", self.repo), \
                patch.object(owner.evidence, "ROOT", self.repo / "ai-dnd"), \
                patch.object(owner.evidence, "DEFAULT_ARCHIVE",
                             self.repo / "ai-dnd/docs/evidence/suite-runs"):
            yield

    def invoke(self, kind="project_health_check", *args):
        with self.fixture_owner(), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            code = owner.main(kind, [
                "--config", str(self.config_path),
                "--archive-root", str(self.archive_root), *args])
        records = sorted(self.archive_root.glob("*/run.json"))
        return code, [json.loads(path.read_text()) for path in records]

    def test_clean_repo_health_success_head_and_not_run(self):
        code, records = self.invoke()
        record = records[-1]
        self.assertEqual(code, 0, record)
        self.assertEqual(record["result"], "HEALTHY")
        self.assertEqual(record["repository_state"]["revision"], self.head)
        self.assertEqual(record["source_start"]["revision"], self.head)
        self.assertEqual(record["exit_status"], 0)
        self.assertFalse(record["historical_certification"])
        self.assertTrue(any(row["status"] == "NOT RUN" for row in record["checks"]))
        self.assertFalse(record["source_changed_during_run"])

    def test_dirty_repo_staged_unstaged_untracked_detection(self):
        (self.repo / "checks.json").write_text(json.dumps(self.config) + " ")
        self.git("add", "checks.json")
        (self.repo / "checks.json").write_text(json.dumps(self.config) + "\n")
        (self.repo / "uploaded.txt").write_text("untracked")
        state = owner.repository_state(self.repo)
        self.assertEqual(len(state["staged"]), 1)
        self.assertEqual(len(state["unstaged"]), 1)
        self.assertEqual(len(state["untracked"]), 1)
        code, records = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(records[-1]["result"], "UNHEALTHY")

    def test_detached_head_is_blocking(self):
        # No checkout/reset/history rewrite in the real project; fixture ref only.
        self.git("update-ref", "--no-deref", "HEAD", self.head)
        self.assertTrue(owner.repository_state(self.repo)["detached"])
        code, _ = self.invoke()
        self.assertEqual(code, 1)

    def test_ci_exact_sha_detachment_is_explicit_and_mismatch_blocks(self):
        self.git("update-ref", "--no-deref", "HEAD", self.head)
        state = owner.repository_state(self.repo)
        rows = owner.structural_checks(self.config, state, self.repo,
                                       ci={"GITHUB_SHA": self.head, "GITHUB_RUN_ID": "fixture"})
        self.assertEqual(owner.exit_code(rows), 0)
        rows = owner.structural_checks(self.config, state, self.repo,
                                       ci={"GITHUB_SHA": "0" * 40, "GITHUB_RUN_ID": "fixture"})
        self.assertEqual(owner.exit_code(rows), 1)

    def test_missing_required_infrastructure_is_failure(self):
        (self.repo / "ai-dnd/docs/regression-evidence.md").unlink()
        state = owner.repository_state(self.repo)
        rows = owner.structural_checks(self.config, state, self.repo)
        row = next(row for row in rows if row["name"] == "Project structure")
        self.assertEqual(row["status"], "FAIL")
        self.assertIn("ai-dnd/docs/regression-evidence.md", row["detail"]["missing"])

    def test_failed_required_command_and_timeout(self):
        with (self.repo / "command.log").open("w") as log:
            row = owner.run_command("failure", [sys.executable, "-c", "raise SystemExit(7)"],
                                    self.repo, 10, log)
            timeout = owner.run_command("timeout", [sys.executable, "-c",
                                        "import time;time.sleep(5)"], self.repo, 1, log)
        self.assertEqual(row["exit_status"], 7)
        self.assertEqual(row["status"], "FAIL")
        self.assertEqual(owner.exit_code([row]), 1)
        self.assertEqual(timeout["status"], "FAIL")
        self.assertTrue(timeout["timed_out"])

    def test_required_not_run_unverified_never_pass(self):
        for status in ("NOT RUN", "UNVERIFIED", "FAIL"):
            self.assertEqual(owner.exit_code([owner.check("required", status, "fixture")]), 1)
        self.assertEqual(owner.exit_code([owner.check("optional", "NOT RUN", "fixture", False)]), 0)
        with self.assertRaises(ValueError):
            owner.check("bad", "SKIP", "fixture")

    def test_static_final_gate_never_claims_go(self):
        code, records = self.invoke("final_gate", "--static-only")
        self.assertEqual(code, 1)
        self.assertEqual(records[-1]["result"], "NO-GO")
        self.assertTrue(any(row["required"] and row["status"] == "NOT RUN"
                            for row in records[-1]["checks"]))

    def test_unique_identity_historical_records_unchanged_and_stable_fingerprint(self):
        code, records = self.invoke()
        first = next(self.archive_root.glob("*/run.json"))
        content = first.read_bytes()
        code2, records2 = self.invoke()
        self.assertEqual((code, code2), (0, 1))  # Generated untracked evidence is still Git-dirty.
        self.assertEqual(len(records2), len(records) + 1)
        self.assertEqual(first.read_bytes(), content)
        self.assertTrue(all(not record["source_changed_during_run"] for record in records2))
        self.assertEqual(records2[0]["source_start"]["working_tree_sha256"],
                         records2[1]["source_start"]["working_tree_sha256"])

    def test_malformed_missing_configuration_fails_and_is_retained(self):
        for content in ("not-json", "{}", '{"schema_version": 2}'):
            with self.subTest(content=content):
                self.config_path.write_text(content)
                code, records = self.invoke()
                self.assertEqual(code, 2)
                self.assertTrue(any(row["name"] == "Configuration/tooling error"
                                    for record in records for row in record["checks"]))
        self.config_path.unlink()
        code, _ = self.invoke()
        self.assertEqual(code, 2)

    def test_config_rejects_missing_commands_invalid_types_and_paths(self):
        invalid = [
            {"command_timeout_seconds": 0},
            {"required_paths": ["../outside"]},
            {"frontend_commands": []},
            {"regression_selectors": []},
            {"frontend_commands": [{"name": "frontend_test", "argv": "pnpm test"}]},
            {"extra": "unsupported"},
        ]
        for change in invalid:
            with self.subTest(change=change):
                self.config_path.write_text(json.dumps({**self.config, **change}))
                with self.assertRaises(ValueError):
                    owner.load_config(self.config_path)

    def test_production_scope_is_not_semantic_authority_proof(self):
        (self.repo / "ai-dnd/game.py").write_text("changed")
        rows = owner.structural_checks(self.config, owner.repository_state(self.repo), self.repo)
        scope = next(row for row in rows if row["name"] == "Infrastructure scope")
        self.assertEqual(scope["status"], "FAIL")
        self.assertIn("ai-dnd/game.py", scope["detail"]["protected_changes"])
        self.assertFalse(owner.protected_path("ai-dnd/api/tests/test_example.py"))
        self.assertTrue(owner.protected_path("artifacts/ai-dnd-experience/src/App.tsx"))

    def test_archives_must_not_exclude_verifier_sources(self):
        with self.fixture_owner():
            for path in (self.repo, self.repo / "ai-dnd/scripts",
                         self.repo / "ai-dnd/docs/evidence/suite-runs/old"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    Archive(path, "fixture", [sys.executable])

    def test_zero_exit_without_retained_regression_evidence_is_not_pass(self):
        with (self.repo / "command.log").open("w") as log:
            row = owner.check("Python regression", "PASS", "exit 0 alone")
            with self.assertRaises(ValueError):
                owner.validate_suite(row, log, 0, self.archive_root)

    def test_retained_skips_and_source_changes_cannot_certify_regression(self):
        directory = self.archive_root / "fixture-suite"
        directory.mkdir(parents=True)
        path = directory / "run.json"
        path.with_name("output.log").write_bytes(b"fixture output\n")
        aggregate = {"tests_run": 1, "per_test_outcomes": {"pass": 1}, "failures": 0,
                     "errors": 0, "skips": 0, "expected_failures": 0, "unexpected_successes": 0}
        record = {
            "evidence_kind": "suite_run", "status": "completed", "exit_status": 0,
            "selected_test_ids": ["fixture.test_ok"], "executed_test_ids": ["fixture.test_ok"],
            "unexecuted_test_ids": [], "source_changed_during_run": False, "aggregate": aggregate,
            "output_log_sha256": owner.evidence.hashlib.sha256(b"fixture output\n").hexdigest()
        }
        cases = [
            {"aggregate": {**aggregate, "skips": 1}},
            {"source_changed_during_run": True},
            {"executed_test_ids": []},
            {"output_log_sha256": "invalid"},
        ]
        for change in cases:
            with self.subTest(change=change):
                path.write_text(json.dumps({**record, **change}))
                with (self.repo / "command.log").open("w") as log:
                    log.write(f"NEW suite evidence: {path}\n")
                    row = owner.check("Python regression", "PASS", "fixture")
                    owner.validate_suite(row, log, 0, self.archive_root)
                self.assertEqual(row["status"], "FAIL")

    def test_full_clean_final_gate_reuses_real_runner_and_has_go(self):
        # Real existing evidence runner, but only one disposable offline function.
        runner = self.repo / "ai-dnd/scripts/run_regression_evidence.py"
        runner.write_bytes((ROOT / "scripts/run_regression_evidence.py").read_bytes())
        (self.repo / "ai-dnd/test_fixture.py").write_text("def test_ok(): pass\n")
        self.config["regression_selectors"] = ["test_fixture"]
        for command in self.config["frontend_commands"]:
            command["argv"] = [sys.executable, "-c", "print('offline command fixture')"]
        self.config_path.write_text(json.dumps(self.config))
        self.git("add", ".")
        self.git("-c", "user.name=Tooling Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "fixture runner")
        code, records = self.invoke("final_gate")
        final = next(record for record in records if record["evidence_kind"] == "final_gate")
        self.assertEqual(code, 0, final)
        self.assertEqual(final["result"], "GO")
        self.assertTrue(all(row["status"] == "PASS" for row in final["checks"] if row["required"]))
        self.assertEqual(len([record for record in records if record["evidence_kind"] == "suite_run"]), 1)


if __name__ == "__main__":
    unittest.main()