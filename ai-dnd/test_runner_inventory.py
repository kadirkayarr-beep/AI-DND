"""Offline checks for release versus historical runner selection."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_tests


class RunnerInventoryTests(unittest.TestCase):
    def test_release_keeps_existing_gates_except_retired_prototypes(self):
        # Explicit policy inventory: do not silently drop another gate.
        expected = {
            "test_definition_preflight_checks.py", "test_runner_inventory.py",
            "test_ai_pipeline_port.py", "test_ai_pipeline_semantics.py",
            "test_startup.py", "test_sessions.py", "test_playable_living_world.py",
            "test_persistence.py", "test_combat.py", "test_combat_v2_authoritative.py",
            "test_regression.py", "test_migration.py", "test_migration_harden.py",
            "test_door_enter.py", "test_query.py", "test_self_query.py",
            "test_actual_logic.py", "test_npc_query.py",
        }
        self.assertEqual(set(run_tests.TESTS), expected)
        self.assertEqual(len(run_tests.TESTS), len(expected))
        self.assertEqual(run_tests.PROTOTYPE_TESTS, (
            "test_combat_v2.py", "test_combat_v2_fixed.py",
        ))
        self.assertTrue(set(run_tests.TESTS).isdisjoint(run_tests.PROTOTYPE_TESTS))
        for name in (*run_tests.TESTS, *run_tests.PROTOTYPE_TESTS):
            self.assertTrue((run_tests.ROOT / name).is_file(), name)

    def test_default_and_explicit_release_execute_only_release_gates(self):
        for argv in ((), ("--suite", "release")):
            with self.subTest(argv=argv), \
                 patch.object(run_tests, "check_test_definitions", return_value=[]) as preflight, \
                 patch.object(run_tests.subprocess, "run") as execute, \
                 redirect_stdout(StringIO()):
                execute.return_value.returncode = 0
                self.assertEqual(run_tests.main(argv), 0)
                self.assertEqual(list(preflight.call_args.args[0]),
                                 [run_tests.ROOT / name for name in run_tests.TESTS])
                self.assertEqual([call.args[0] for call in execute.call_args_list], [
                    [run_tests.sys.executable, str(run_tests.ROOT / name)]
                    for name in run_tests.TESTS
                ])
                self.assertTrue(all(call.kwargs["cwd"] == run_tests.ROOT
                                    for call in execute.call_args_list))

    def test_prototypes_are_opt_in_and_failures_are_not_release_results(self):
        for failed in (False, True):
            output = StringIO()
            with self.subTest(failed=failed), \
                 patch.object(run_tests, "check_test_definitions", return_value=[]) as preflight, \
                 patch.object(run_tests.subprocess, "run") as execute, \
                 redirect_stdout(output):
                execute.side_effect = [
                    subprocess.CompletedProcess([], int(failed)),
                    subprocess.CompletedProcess([], 0),
                ]
                self.assertEqual(run_tests.main(("--suite", "prototype")), int(failed))
                self.assertEqual(list(preflight.call_args.args[0]),
                                 [run_tests.ROOT / name for name in run_tests.PROTOTYPE_TESTS])
                self.assertEqual([call.args[0] for call in execute.call_args_list], [
                    [run_tests.sys.executable, str(run_tests.ROOT / name)]
                    for name in run_tests.PROTOTYPE_TESTS
                ])
            self.assertIn("NOT RELEASE GATES", output.getvalue())
            self.assertNotIn("DETERMINISTIC GATES PASSED", output.getvalue())
            if failed:
                self.assertIn("FAILED: test_combat_v2.py", output.getvalue())

    def test_authoritative_failure_blocks_release_but_remaining_gates_run(self):
        output = StringIO()
        with patch.object(run_tests, "check_test_definitions", return_value=[]), \
             patch.object(run_tests.subprocess, "run") as execute, redirect_stdout(output):
            execute.side_effect = [
                subprocess.CompletedProcess([], int(name == "test_combat_v2_authoritative.py"))
                for name in run_tests.TESTS
            ]
            self.assertEqual(run_tests.main(), 1)
            self.assertEqual(execute.call_count, len(run_tests.TESTS))
        self.assertIn("RELEASE DETERMINISTIC GATES FAILED: test_combat_v2_authoritative.py",
                      output.getvalue())
        self.assertNotIn("GATES PASSED", output.getvalue())

    def test_listing_is_source_only_and_not_a_pass_claim(self):
        for suite, selected in (("release", run_tests.TESTS),
                                ("prototype", run_tests.PROTOTYPE_TESTS)):
            output = StringIO()
            with self.subTest(suite=suite), \
                 patch.object(run_tests, "check_test_definitions") as preflight, \
                 patch.object(run_tests.subprocess, "run") as execute, redirect_stdout(output):
                self.assertEqual(run_tests.main(("--suite", suite, "--list")), 0)
                preflight.assert_not_called()
                execute.assert_not_called()
            self.assertEqual([line for line in output.getvalue().splitlines()
                              if line.endswith(".py") and not line.startswith("Excluded")],
                             list(selected))
            self.assertNotIn("PASSED", output.getvalue())

    def test_unknown_suite_is_rejected_before_execution(self):
        with patch.object(run_tests.subprocess, "run") as execute, \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            run_tests.main(("--suite", "all"))
        self.assertEqual(error.exception.code, 2)
        execute.assert_not_called()

    def test_missing_selected_source_fails_before_execution(self):
        for suite in ("release", "prototype"):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory() as directory, \
                 patch.object(run_tests, "ROOT", Path(directory)), \
                 patch.object(run_tests.subprocess, "run") as execute, \
                 redirect_stderr(StringIO()) as stderr, redirect_stdout(StringIO()):
                self.assertEqual(run_tests.main(("--suite", suite)), 1)
                execute.assert_not_called()
                self.assertIn("PREFLIGHT FAILED", stderr.getvalue())

    def test_invalid_unselected_prototype_cannot_block_release_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in run_tests.TESTS:
                (root / name).write_text("class Checks:\n    def test_ok(self): pass\n",
                                         encoding="utf-8")
            for name in run_tests.PROTOTYPE_TESTS:
                (root / name).write_text("class Invalid:\n", encoding="utf-8")
            with patch.object(run_tests, "ROOT", root), \
                 patch.object(run_tests.subprocess, "run") as execute, \
                 redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                execute.return_value.returncode = 0
                self.assertEqual(run_tests.main(), 0)
                self.assertEqual(execute.call_count, len(run_tests.TESTS))
                execute.reset_mock()
                self.assertEqual(run_tests.main(("--suite", "prototype")), 1)
                execute.assert_not_called()
                self.assertIn("PREFLIGHT FAILED", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
