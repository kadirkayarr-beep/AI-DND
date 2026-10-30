"""Synthetic-only tests for the fail-closed Linux guarded gate entry point."""
import hashlib
import json
import os
from pathlib import Path
import py_compile
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "acceptance"))
import guarded_runner
import source_identity
from api.tests.guard_bound import CHILD_PROCESS, guard_bound


class GuardedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="b06-guard-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_root = self.root / "run"
        self.run_root.mkdir()

    def run_gate(self, selector, timeout_s=10):
        return guarded_runner.run_unittest_gate(
            [selector], timeout_s=timeout_s, run_root=self.run_root)

    @guard_bound(CHILD_PROCESS)
    def test_internal_asyncio_pair_does_not_enable_network_or_unix_services(self):
        result = self.run_gate(
            "api.tests.fixtures.b06_guard_target.AsyncioTarget."
            "test_internal_event_loop_works_but_service_connections_are_blocked")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["testMethodsRun"], 1)

    @guard_bound(CHILD_PROCESS)
    def test_fresh_temporary_database_does_not_enable_other_database_access(self):
        result = self.run_gate(
            "api.tests.fixtures.b06_guard_target.GuardedTarget."
            "test_fresh_temporary_database_is_allowed_but_other_database_is_denied")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["testMethodsRun"], 1)

    @guard_bound(CHILD_PROCESS)
    def test_read_only_sqlite_uri_cannot_bypass_database_boundaries(self):
        result = self.run_gate(
            "api.tests.fixtures.b06_guard_target.GuardedTarget."
            "test_read_only_sqlite_uri_is_limited_to_owned_synthetic_database")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["testMethodsRun"], 1)

    def run_gate_with_environment(self, selector, additions):
        clean_env = guarded_runner._clean_env

        def injected_env(run_root):
            env = clean_env(run_root)
            env.update(additions)
            return env

        with mock.patch.object(guarded_runner, "_clean_env", side_effect=injected_env):
            return self.run_gate(selector)

    def run_gate_with_summary(self, summary_text):
        proof = json.dumps({
            "guard_id": guarded_runner.GUARD_ID,
            "sha256": guarded_runner.EXPECTED_GUARD_SHA256,
            "denied_path_blocked": True,
        }, sort_keys=True)
        proof_digest = hashlib.sha256(
            f"B06_GUARD_PROOF:{proof}\n".encode()).hexdigest()
        calls = 0

        def synthetic_gate(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"status": "PASS", "rawDigest": proof_digest}
            if summary_text is not None:
                (self.run_root / "unittest-summary.json").write_text(
                    summary_text, encoding="utf-8")
            return {"status": "PASS", "exitCode": 0}

        # Under the guard the temp dir is not below /tmp; the base check is not the subject here.
        with mock.patch.object(guarded_runner, "SCRATCH_BASE", self.root.parent.resolve()),                 mock.patch.object(guarded_runner.platform_runner, "run_gate",
                                  side_effect=synthetic_gate):
            result = self.run_gate("api.tests.fixtures.b06_guard_target.GuardedTarget")
        self.assertEqual(calls, 2, result)
        return result

    @guard_bound(CHILD_PROCESS)
    def test_guard_proof_and_exact_clean_environment_precede_target(self):
        os.environ["AI_DND_SECRET_PROBE"] = "synthetic-only"
        self.addCleanup(os.environ.pop, "AI_DND_SECRET_PROBE", None)
        result = self.run_gate(
            "api.tests.fixtures.b06_guard_target.GuardedTarget."
            "test_guard_blocks_synthetic_private_path_and_network")
        self.assertEqual(result["guard"]["status"], "PASS")
        self.assertEqual(result["target"]["status"], "PASS")
        self.assertEqual(result["testMethodsRun"], 1)
        self.assertTrue((self.run_root / "target.started").is_file())

    @guard_bound(CHILD_PROCESS)
    def test_python_user_site_pth_does_not_run_before_guard(self):
        userbase = self.root / "synthetic-userbase"
        site_packages = (userbase / "lib" /
                         f"python{sys.version_info.major}.{sys.version_info.minor}" /
                         "site-packages")
        site_packages.mkdir(parents=True)
        shadow = self.root / "synthetic-sitecustomize"
        shadow.mkdir()
        marker = self.run_root / "startup-pth-ran"
        (site_packages / "startup.pth").write_text(
            f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')\n",
            encoding="utf-8")
        (shadow / "sitecustomize.py").write_text(
            f"import site\nsite.addsitedir({str(site_packages)!r})\n",
            encoding="utf-8")
        result = self.run_gate_with_environment(
            "api.tests.fixtures.b06_guard_target.GuardedTarget."
            "test_guard_blocks_synthetic_private_path_and_network",
            {"PYTHONUSERBASE": str(userbase), "PYTHONPATH": str(shadow)})
        self.assertFalse(marker.exists(), "user-site .pth ran before guard activation")
        self.assertEqual(result["target"]["status"], "PASS")

    @guard_bound(CHILD_PROCESS)
    def test_pythonpath_sitecustomize_shadow_does_not_run(self):
        shadow = self.root / "synthetic-shadow"
        shadow.mkdir()
        marker = self.run_root / "shadow-module-ran"
        (shadow / "sitecustomize.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
            encoding="utf-8")
        result = self.run_gate_with_environment(
            "api.tests.fixtures.b06_guard_target.GuardedTarget."
            "test_guard_blocks_synthetic_private_path_and_network",
            {"PYTHONPATH": str(shadow)})
        self.assertFalse(marker.exists(), "environment-supplied sitecustomize ran")
        self.assertEqual(result["target"]["status"], "PASS")

    @guard_bound(CHILD_PROCESS)
    def test_stale_guard_bytecode_cannot_replace_verified_source(self):
        shadow = self.root / "synthetic-bytecode-shadow"
        shadow.mkdir()
        source = shadow / "sitecustomize.py"
        guard_bytes = guarded_runner.GUARD_FILE.read_bytes()
        source.write_bytes(guard_bytes)
        marker = self.run_root / "stale-bytecode-ran"
        forged = (
            "import os, sys\n"
            f"GUARD_ID = {guarded_runner.GUARD_ID!r}\n"
            f"open({str(marker)!r}, 'w').write('ran')\n"
            "denied = os.environ['AI_DND_GUARD_DENIED_PATH']\n"
            "def _audit(event, args):\n"
            "    if event == 'open' and args and os.fsdecode(args[0]) == denied:\n"
            "        raise PermissionError('synthetic deny')\n"
            "    if event in {'socket.__new__', 'socket.connect', 'socket.bind', "
            "'socket.getaddrinfo', 'subprocess.Popen'}:\n"
            "        raise PermissionError('synthetic deny')\n"
            "sys.addaudithook(_audit)\n"
        ).encode("utf-8")
        self.assertLessEqual(len(forged), len(guard_bytes))
        forged += b"#" + b" " * (len(guard_bytes) - len(forged) - 1)
        source.write_bytes(forged)
        fixed_mtime = 1_700_000_000
        os.utime(source, (fixed_mtime, fixed_mtime))
        py_compile.compile(str(source), doraise=True)
        source.write_bytes(guard_bytes)
        os.utime(source, (fixed_mtime, fixed_mtime))

        with mock.patch.object(guarded_runner, "GUARD_FILE", source):
            result = self.run_gate_with_environment(
                "api.tests.fixtures.b06_guard_target.GuardedTarget."
                "test_guard_blocks_synthetic_private_path_and_network",
                {"PYTHONPATH": str(shadow)})
        self.assertFalse(marker.exists(), "cached forged guard bytecode ran")
        self.assertEqual(result["target"]["status"], "PASS")
        self.assertTrue((self.run_root / "target.started").is_file())

    @guard_bound(CHILD_PROCESS)
    def test_runner_owned_campaign_database_passes_but_other_database_is_blocked(self):
        result = self.run_gate(
            "api.tests.fixtures.b06_guard_target.GuardedTarget."
            "test_only_runner_owned_synthetic_campaign_database_is_allowed")
        self.assertEqual(result["guard"]["status"], "PASS")
        self.assertEqual(result["target"]["status"], "PASS")
        self.assertEqual(result["testMethodsRun"], 1)
        self.assertTrue((self.run_root / "db" / "campaigns.sqlite3").is_file())
        self.assertFalse((self.run_root / "db" / "personal.sqlite3").exists())

    @guard_bound(CHILD_PROCESS)
    def test_nested_temporary_directory_cleanup_with_dir_fd_is_allowed(self):
        result = self.run_gate(
            "api.tests.fixtures.b06_guard_target.DirFdTarget."
            "test_nested_temporary_directory_is_created_and_cleaned")
        self.assertEqual(result["guard"]["status"], "PASS")
        self.assertEqual(result["target"]["status"], "PASS")
        self.assertEqual(result["testMethodsRun"], 1)
        self.assertEqual(list((self.run_root / "nested-cleanup").iterdir()), [])

    @guard_bound(CHILD_PROCESS)
    def test_dir_fd_cannot_delete_file_outside_run_root(self):
        outside = self.root / "outside-sentinel.txt"
        outside.write_text("preserve", encoding="utf-8")
        clean_env = guarded_runner._clean_env

        def env_with_external_read_root(run_root):
            env = clean_env(run_root)
            roots = json.loads(env["AI_DND_GUARD_ALLOWED_ROOTS"])
            roots.append(str(self.root))
            env["AI_DND_GUARD_ALLOWED_ROOTS"] = json.dumps(roots)
            env["AI_DND_GUARD_OUTSIDE_SENTINEL"] = str(outside)
            return env

        with mock.patch.object(guarded_runner, "_clean_env",
                               side_effect=env_with_external_read_root):
            result = self.run_gate(
                "api.tests.fixtures.b06_guard_target.DirFdTarget."
                "test_dir_fd_delete_outside_run_root_is_denied")
        self.assertEqual(result["guard"]["status"], "PASS")
        self.assertEqual(result["target"]["status"], "PASS")
        self.assertEqual(result["testMethodsRun"], 1)
        self.assertEqual(outside.read_text(encoding="utf-8"), "preserve")

    @guard_bound(CHILD_PROCESS)
    def test_import_time_exit_zero_without_summary_does_not_pass(self):
        result = self.run_gate("api.tests.fixtures.b06_import_exit_zero")
        self.assertEqual(result["target"]["exitCode"], 0)
        self.assertIsNone(result["testMethodsRun"])
        self.assertEqual(result["status"], "FAIL")

    @guard_bound(CHILD_PROCESS)
    def test_zero_tests_do_not_pass(self):
        result = self.run_gate(
            "api.tests.fixtures.b06_guard_target.EmptyTarget")
        self.assertEqual(result["target"]["exitCode"], 0)
        self.assertEqual(result["testMethodsRun"], 0)
        self.assertEqual(result["status"], "FAIL")

    def test_missing_summary_does_not_pass_and_keeps_process_exit_code(self):
        result = self.run_gate_with_summary(None)
        self.assertEqual(result["target"]["exitCode"], 0)
        self.assertIsNone(result["testMethodsRun"])
        self.assertEqual(result["status"], "FAIL")

    def test_malformed_summary_does_not_pass_and_keeps_process_exit_code(self):
        result = self.run_gate_with_summary("{not-json")
        self.assertEqual(result["target"]["exitCode"], 0)
        self.assertIsNone(result["testMethodsRun"])
        self.assertEqual(result["status"], "FAIL")

    def test_missing_guard_blocks_before_target_starts(self):
        with mock.patch.object(guarded_runner, "GUARD_FILE", self.root / "missing-sitecustomize.py"):
            with mock.patch.object(guarded_runner.platform_runner, "run_gate") as run_gate:
                result = self.run_gate(
                    "api.tests.fixtures.b06_guard_target.GuardedTarget."
                    "test_guard_blocks_synthetic_private_path_and_network")
        run_gate.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["target"])
        self.assertFalse((self.run_root / "target.started").exists())

    def test_wrong_guard_blocks_before_target_starts(self):
        bad_dir = self.root / "bad-guard"
        bad_dir.mkdir()
        bad_guard = bad_dir / "sitecustomize.py"
        bad_guard.write_text("GUARD_ID = 'wrong'\n", encoding="utf-8")
        with mock.patch.object(guarded_runner, "GUARD_FILE", bad_guard):
            with mock.patch.object(guarded_runner.platform_runner, "run_gate") as run_gate:
                result = self.run_gate(
                    "api.tests.fixtures.b06_guard_target.GuardedTarget."
                    "test_guard_blocks_synthetic_private_path_and_network")
        run_gate.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["target"])
        self.assertFalse((self.run_root / "target.started").exists())

    @guard_bound(CHILD_PROCESS)
    def test_target_child_rechecks_guard_before_importing_tests(self):
        guard_dir = self.root / "replaceable-guard"
        guard_dir.mkdir()
        guard = guard_dir / "sitecustomize.py"
        guard.write_bytes(guarded_runner.GUARD_FILE.read_bytes())
        real_run = guarded_runner.platform_runner.run_gate
        calls = 0

        def tamper_after_preflight(*args, **kwargs):
            nonlocal calls
            result = real_run(*args, **kwargs)
            calls += 1
            if calls == 1:
                guard.write_text(guard.read_text(encoding="utf-8") + "\n# synthetic tamper\n",
                                 encoding="utf-8")
            return result

        with mock.patch.object(guarded_runner, "GUARD_FILE", guard):
            with mock.patch.object(guarded_runner.platform_runner, "run_gate",
                                   side_effect=tamper_after_preflight):
                result = self.run_gate(
                    "api.tests.fixtures.b06_guard_target.GuardedTarget."
                    "test_guard_blocks_synthetic_private_path_and_network")
        self.assertEqual(calls, 2, result)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["guard"]["status"], "PASS")
        self.assertEqual(result["target"]["status"], "FAIL")
        self.assertEqual(result["target"]["exitCode"], 97)
        self.assertFalse((self.run_root / "target.started").exists())

    def test_run_root_outside_scratch_is_rejected_without_writes(self):
        # /var/tmp can resolve to /tmp; use owned sibling paths instead of
        # assuming two platform-specific temporary directories are distinct.
        outside = self.root / "outside-scratch"
        with mock.patch.object(guarded_runner, "SCRATCH_BASE", self.root / "scratch"):
            result = guarded_runner.run_unittest_gate(
                ["api.tests.fixtures.b06_guard_target.GuardedTarget"], timeout_s=5,
                run_root=outside)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["guard"])
        self.assertFalse(outside.exists())

    @guard_bound(CHILD_PROCESS)
    def test_target_failure_exit_code_is_forwarded(self):
        result = self.run_gate("api.tests.fixtures.b06_guard_target.FailingTarget")
        self.assertEqual(result["guard"]["status"], "PASS")
        self.assertEqual((result["target"]["status"], result["target"]["exitCode"]), ("FAIL", 1))
        self.assertEqual(result["testMethodsRun"], 1)
        self.assertEqual(result["status"], "FAIL")

    @guard_bound(CHILD_PROCESS)
    def test_target_timeout_is_forwarded_and_owned_process_is_closed(self):
        result = self.run_gate("api.tests.fixtures.b06_guard_target.SlowTarget.test_timeout_fixture",
                               timeout_s=1)
        self.assertEqual(result["guard"]["status"], "PASS")
        self.assertEqual((result["target"]["status"], result["target"]["exitCode"]), ("FAIL", None))

    def test_source_identity_git_environment_drops_caller_secrets(self):
        # The checkout's .git entry is not the subject (and is not readable under the guard).
        stub_git_dir = REPO.resolve() / "stub-git-dir"
        with mock.patch.object(source_identity, "_git_context",
                               return_value=(REPO.resolve(), stub_git_dir)),                 mock.patch.dict(os.environ, {"B06_SECRET_SENTINEL": "synthetic-only"}):
            with mock.patch.object(source_identity.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = str(REPO.resolve()).encode()
                with mock.patch.object(source_identity.subprocess, "check_output",
                                       return_value=b"ok") as call:
                    source_identity.git(
                        REPO, "status",
                        env={"PATH": "/tmp/b06-untrusted-bin:/usr/bin",
                             "B06_SECRET_SENTINEL": "synthetic-only"})
        child_env = call.call_args.kwargs["env"]
        self.assertNotIn("B06_SECRET_SENTINEL", child_env)
        self.assertNotIn("/tmp/b06-untrusted-bin", child_env["PATH"])
        self.assertEqual(child_env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(child_env["GIT_CONFIG_GLOBAL"], os.devnull)

    @guard_bound(CHILD_PROCESS)
    def test_source_identity_uses_isolated_candidate_root_and_head(self):
        marker = (REPO / ".git").read_text(encoding="utf-8").strip()
        self.assertTrue(marker.startswith("gitdir: "))
        admin = Path(marker.removeprefix("gitdir: ").strip())
        if not admin.is_absolute():
            admin = (REPO / admin).resolve()
        expected_head = (admin / "HEAD").read_text(encoding="utf-8").strip()
        self.assertEqual(source_identity.git_root(REPO), REPO.resolve())
        self.assertEqual(source_identity.ref_sha(REPO, "HEAD"), expected_head)

    def test_source_identity_git_context_overrides_caller_git_routing(self):
        # A stub context stands in for the checkout's .git entry, which the guard denies.
        admin = REPO.resolve() / "stub-git-dir"
        with mock.patch.object(source_identity, "_git_context",
                               return_value=(REPO.resolve(), admin)),                 mock.patch.object(source_identity.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = str(REPO.resolve()).encode()
            with mock.patch.object(source_identity.subprocess, "check_output",
                                   return_value=b"ok") as call:
                source_identity.git(
                    REPO, "status",
                    env={"PATH": "/usr/bin", "GIT_DIR": "/tmp/wrong-git-dir",
                         "GIT_WORK_TREE": "/tmp/wrong-worktree",
                         "GIT_CONFIG_GLOBAL": "/tmp/private-gitconfig",
                         "GITHUB_TOKEN": "synthetic-secret"})
        child_env = call.call_args.kwargs["env"]
        self.assertEqual(Path(child_env["GIT_DIR"]), admin)
        self.assertEqual(Path(child_env["GIT_WORK_TREE"]), REPO.resolve())
        self.assertEqual(child_env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertNotIn("GITHUB_TOKEN", child_env)

    def test_source_identity_keeps_only_trusted_windows_git_paths(self):
        with mock.patch.dict(os.environ, {
                "ProgramFiles": r"D:\Apps",
                "ProgramFiles(x86)": r"D:\Apps32",
                "ProgramW6432": r"D:\Apps",
        }):
            child_env = source_identity._git_environment(
                {
                    "PATH": (
                        r"D:\Apps\Git\cmd;"
                        r"C:\Users\synthetic\AppData\Local\Programs\Git\cmd;"
                        r"C:\Windows\System32"
                    ),
                    "HOME": r"C:\Users\synthetic",
                    "GIT_CONFIG_GLOBAL": r"C:\Users\synthetic\.gitconfig",
                    "GIT_ASKPASS": "synthetic-secret-helper",
                    "GITHUB_TOKEN": "synthetic-secret-token",
                },
                platform_name="nt",
            )
        self.assertEqual(child_env["PATH"], r"D:\Apps\Git\cmd")
        self.assertEqual(child_env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(child_env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertNotIn("GIT_ASKPASS", child_env)
        self.assertNotIn("GITHUB_TOKEN", child_env)


if __name__ == "__main__":
    unittest.main()
