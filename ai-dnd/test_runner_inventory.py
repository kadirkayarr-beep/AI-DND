"""Offline checks for release versus historical runner selection."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import ast
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import run_tests


class RunnerInventoryTests(unittest.TestCase):
    @staticmethod
    def completed_gate(command, *, cwd, timeout, returncode=0):
        """Simulate the child's receipt as well as its process exit status."""
        if len(command) == 5 and returncode == 0:
            Path(command[4]).write_text(command[3], encoding="utf-8")
        return subprocess.CompletedProcess(command, returncode)

    def test_release_keeps_existing_gates_except_retired_prototypes(self):
        # Explicit policy inventory: do not silently drop another gate.
        expected = {
            "test_definition_preflight_checks.py", "test_runner_inventory.py",
            "test_ai_pipeline_port.py", "test_ai_pipeline_semantics.py",
            "test_startup.py", "test_sessions.py", "test_playable_living_world.py",
            "test_persistence.py", "test_combat.py", "test_combat_v2_authoritative.py",
            "api/tests/test_death_bounded.py", "api/tests/test_initiative.py",
            "test_regression.py", "test_migration.py", "test_migration_harden.py",
            "test_door_enter.py", "test_query.py", "test_self_query.py",
            "test_actual_logic.py", "test_npc_query.py",
            "test_narrative_rebalance.py", "test_narrative_safety_calibration.py",
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
                execute.side_effect = self.completed_gate
                self.assertEqual(run_tests.main(argv), 0)
                self.assertEqual(list(preflight.call_args.args[0]),
                                 [run_tests.ROOT / name for name in run_tests.TESTS])
                self.assertEqual([
                    call.args[0][:-1] if name.startswith("api/tests/") else call.args[0]
                    for name, call in zip(run_tests.TESTS, execute.call_args_list)
                ], [
                    ([run_tests.sys.executable, "-c",
                      "import sys; from run_tests import run_unittest_gate; "
                      "sys.exit(run_unittest_gate(sys.argv[1], sys.argv[2]))",
                      name.removesuffix(".py").replace("/", ".")]
                     if name.startswith("api/tests/") else
                     [run_tests.sys.executable, str(run_tests.ROOT / name)])
                    for name in run_tests.TESTS
                ])
                self.assertTrue(all(call.kwargs["cwd"] == run_tests.ROOT
                                    for call in execute.call_args_list))
                self.assertTrue(all(call.kwargs["timeout"] == run_tests.DEFAULT_GATE_TIMEOUT
                                    for call in execute.call_args_list))
                receipts = [Path(call.args[0][4]) for call in execute.call_args_list
                            if len(call.args[0]) == 5]
                self.assertEqual(len(receipts), 2)
                self.assertEqual(len(set(receipts)), 2)
                self.assertTrue(all(not path.parent.exists() for path in receipts))

    def test_api_completion_evidence_must_be_valid_and_cannot_override_failure(self):
        first, second = ("api/tests/test_initiative.py",
                         "api/tests/test_death_bounded.py")
        gates = (first, second, "release_later.py")
        for argv in ((), ("--suite", "release")):
            for evidence in (None, b"", b"wrong.module", b"\xff", b"valid_but_failed"):
                with self.subTest(argv=argv, evidence=evidence), \
                     patch.object(run_tests, "TESTS", gates), \
                     patch.object(run_tests, "check_test_definitions", return_value=[]), \
                     patch.object(run_tests.subprocess, "run") as execute, \
                     redirect_stdout(StringIO()) as output, \
                     redirect_stderr(StringIO()) as stderr:
                    receipts = []

                    def finish(command, **kwargs):
                        if len(command) != 5:
                            return self.completed_gate(command, **kwargs)
                        receipts.append(Path(command[4]))
                        self.assertFalse(receipts[-1].exists())
                        if command[3] != first[:-3].replace("/", "."):
                            return self.completed_gate(command, **kwargs)
                        if evidence == b"valid_but_failed":
                            self.completed_gate(command, **kwargs)
                            return subprocess.CompletedProcess(command, 1)
                        if evidence is not None:
                            receipts[-1].write_bytes(evidence)
                        return subprocess.CompletedProcess(command, 0)

                    execute.side_effect = finish
                    self.assertEqual(run_tests.main(argv), 1)
                    self.assertEqual(execute.call_count, len(gates))
                    self.assertEqual(output.getvalue().splitlines()[-1],
                                     f"RELEASE DETERMINISTIC GATES FAILED: {first}")
                    self.assertNotIn("PASSED", output.getvalue())
                    if evidence != b"valid_but_failed":
                        self.assertIn("no valid successful completion evidence",
                                      stderr.getvalue())
                    self.assertEqual(len(set(receipts)), 2)
                    self.assertTrue(all(not path.parent.exists() for path in receipts))

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
            results = iter([
                subprocess.CompletedProcess([], int(name == "test_combat_v2_authoritative.py"))
                for name in run_tests.TESTS
            ])
            execute.side_effect = lambda command, **kwargs: self.completed_gate(
                command, **kwargs, returncode=next(results).returncode)
            self.assertEqual(run_tests.main(), 1)
            self.assertEqual(execute.call_count, len(run_tests.TESTS))
        self.assertIn("RELEASE DETERMINISTIC GATES FAILED: test_combat_v2_authoritative.py",
                      output.getvalue())
        self.assertNotIn("GATES PASSED", output.getvalue())

    def test_each_narrative_failure_blocks_default_and_explicit_release(self):
        for argv in ((), ("--suite", "release")):
            for failed_gate in ("test_narrative_rebalance.py",
                                "test_narrative_safety_calibration.py"):
                output = StringIO()
                with self.subTest(argv=argv, failed_gate=failed_gate), \
                     patch.object(run_tests, "check_test_definitions", return_value=[]), \
                     patch.object(run_tests.subprocess, "run") as execute, \
                     redirect_stdout(output):
                    results = iter([
                        subprocess.CompletedProcess([], int(name == failed_gate))
                        for name in run_tests.TESTS
                    ])
                    execute.side_effect = lambda command, **kwargs: self.completed_gate(
                        command, **kwargs, returncode=next(results).returncode)
                    self.assertEqual(run_tests.main(argv), 1)
                    self.assertEqual(execute.call_count, len(run_tests.TESTS))
                self.assertIn(f"RELEASE DETERMINISTIC GATES FAILED: {failed_gate}",
                              output.getvalue())
                self.assertNotIn("GATES PASSED", output.getvalue())

    def test_each_scheduler_failure_blocks_default_and_explicit_release(self):
        for argv in ((), ("--suite", "release")):
            for failed_gate in ("api/tests/test_death_bounded.py",
                                "api/tests/test_initiative.py"):
                output = StringIO()
                with self.subTest(argv=argv, failed_gate=failed_gate), \
                     patch.object(run_tests, "check_test_definitions", return_value=[]), \
                     patch.object(run_tests.subprocess, "run") as execute, \
                     redirect_stdout(output):
                    results = iter([
                        subprocess.CompletedProcess([], int(name == failed_gate))
                        for name in run_tests.TESTS
                    ])
                    execute.side_effect = lambda command, **kwargs: self.completed_gate(
                        command, **kwargs, returncode=next(results).returncode)
                    self.assertEqual(run_tests.main(argv), 1)
                    self.assertEqual(execute.call_count, len(run_tests.TESTS))
                self.assertIn(f"RELEASE DETERMINISTIC GATES FAILED: {failed_gate}",
                              output.getvalue())
                self.assertNotIn("GATES PASSED", output.getvalue())

    def test_release_sources_pass_real_definition_preflight(self):
        self.assertEqual(run_tests.check_test_definitions(
            run_tests.ROOT / name for name in run_tests.TESTS
        ), [])

    def test_narrative_and_scheduler_definition_loss_blocks_release_before_any_gate_runs(self):
        for failed_gate in ("test_narrative_rebalance.py",
                            "test_narrative_safety_calibration.py",
                            "api/tests/test_death_bounded.py",
                            "api/tests/test_initiative.py"):
            with self.subTest(failed_gate=failed_gate), \
                 tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in run_tests.TESTS:
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_text(
                        "class Checks:\n    def test_ok(self): pass\n",
                        encoding="utf-8",
                    )
                (root / failed_gate).write_text(
                    "class Checks:\n"
                    "    def test_boundary(self): pass\n"
                    "    def test_boundary(self): pass\n",
                    encoding="utf-8",
                )
                with patch.object(run_tests, "ROOT", root), \
                     patch.object(run_tests.subprocess, "run") as execute, \
                     redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(run_tests.main(), 1)
                    execute.assert_not_called()
                self.assertIn(failed_gate, stderr.getvalue().replace("\\", "/"))
                self.assertIn("duplicate method Checks.test_boundary", stderr.getvalue())

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

    def test_timeout_must_be_positive_and_finite_before_preflight(self):
        for value in ("0", "-1", "nan", "inf", "-inf", "not-a-number"):
            with self.subTest(value=value), \
                 patch.object(run_tests, "check_test_definitions") as preflight, \
                 patch.object(run_tests.subprocess, "run") as execute, \
                 redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                run_tests.main((f"--gate-timeout={value}",))
            self.assertEqual(error.exception.code, 2)
            preflight.assert_not_called()
            execute.assert_not_called()

    def test_timeout_cannot_be_overridden_by_a_completion_receipt(self):
        gates = ("api/tests/test_initiative.py", "release_later.py")
        receipts = []
        with patch.object(run_tests, "TESTS", gates), \
             patch.object(run_tests, "check_test_definitions", return_value=[]), \
             patch.object(run_tests.subprocess, "run") as execute, \
             redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as stderr:
            def finish(command, **kwargs):
                if len(command) == 5:
                    receipts.append(Path(command[4]))
                    self.completed_gate(command, **kwargs)
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                return self.completed_gate(command, **kwargs)

            execute.side_effect = finish
            self.assertEqual(run_tests.main(("--gate-timeout", "0.5")), 1)
            self.assertEqual(execute.call_count, 2)
            self.assertTrue(all(call.kwargs["timeout"] == 0.5
                                for call in execute.call_args_list))
        self.assertIn(f"GATE TIMED OUT: {gates[0]} exceeded 0.5 seconds", stderr.getvalue())
        self.assertEqual(output.getvalue().splitlines()[-1],
                         f"RELEASE DETERMINISTIC GATES FAILED: {gates[0]}")
        self.assertTrue(all(not path.parent.exists() for path in receipts))

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
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text("class Checks:\n    def test_ok(self): pass\n",
                                         encoding="utf-8")
            for name in run_tests.PROTOTYPE_TESTS:
                (root / name).write_text("class Invalid:\n", encoding="utf-8")
            with patch.object(run_tests, "ROOT", root), \
                 patch.object(run_tests.subprocess, "run") as execute, \
                 redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                execute.side_effect = self.completed_gate
                self.assertEqual(run_tests.main(), 0)
                self.assertEqual(execute.call_count, len(run_tests.TESTS))
                execute.reset_mock()
                self.assertEqual(run_tests.main(("--suite", "prototype")), 1)
                execute.assert_not_called()
                self.assertIn("PREFLIGHT FAILED", stderr.getvalue())


class RunnerProcessTests(unittest.TestCase):
    """Exercise real preflight and child processes using only offline toy gates."""

    SUITES = {
        "TESTS": ("release_first.py", "release_later.py"),
        "PROTOTYPE_TESTS": ("prototype_first.py", "prototype_later.py"),
    }
    SELECTIONS = (
        ((), "TESTS"),
        (("--suite", "release"), "TESTS"),
        (("--suite", "prototype"), "PROTOTYPE_TESTS"),
    )

    def copy_runner(self, root):
        for name in ("run_tests.py", "test_definition_preflight.py"):
            shutil.copyfile(run_tests.ROOT / name, root / name)
        runner = root / "run_tests.py"
        source = runner.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        # Change only the copied inventories, leaving the runner's CLI, preflight,
        # subprocess execution and exit handling intact. Never copy real gates.
        inventories = {
            node.targets[0].id: node
            for node in ast.parse(source).body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in self.SUITES
        }
        self.assertEqual(set(inventories), set(self.SUITES))
        for name, node in sorted(inventories.items(),
                                 key=lambda item: item[1].lineno, reverse=True):
            lines[node.lineno - 1:node.end_lineno] = [
                f"{name} = {self.SUITES[name]!r}\n"
            ]
        runner.write_text("".join(lines), encoding="utf-8")

    def write_gate(self, root, name, body, exit_code=0):
        # Write the sentinel before any definitions: even merely importing a
        # rejected gate would leave evidence. The shared log proves child order.
        (root / name).write_text(
            "from pathlib import Path\n"
            f"Path({name + '.sentinel'!r}).write_text('started', encoding='utf-8')\n"
            + textwrap.dedent(body).lstrip("\n")
            + f"\nwith Path('order.txt').open('a', encoding='utf-8') as log:\n"
            f"    log.write({name + chr(10)!r})\n"
            + f"\nraise SystemExit({exit_code!r})\n",
            encoding="utf-8",
        )

    def launch_runner(self, root, argv, cwd=None):
        return subprocess.run(
            [sys.executable, str(root / "run_tests.py"), *argv],
            cwd=root if cwd is None else cwd,
            capture_output=True, text=True, timeout=20,
        )

    def test_real_api_import_and_loading_timeouts_preserve_failure_order_and_continue(self):
        api_gates = ("api/tests/test_initiative.py",
                     "api/tests/test_death_bounded.py")
        failed_script, later = "release_failed.py", "release_later.py"
        suites = {
            "TESTS": (*api_gates, failed_script, later),
            "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
        }
        hangs = {
            "import": "time.sleep(60)\n",
            "load_tests": (
                "def load_tests(loader, tests, pattern):\n"
                "    Path(__file__ + '.hook').write_text('started')\n"
                "    time.sleep(60)\n"
                "    return tests\n"
            ),
        }
        for argv, kinds in (((), ("import", "load_tests")),
                            (("--suite", "release"), ("load_tests", "import"))):
            with self.subTest(argv=argv, kinds=kinds), \
                 tempfile.TemporaryDirectory() as directory, \
                 patch.object(self, "SUITES", suites):
                root = Path(directory)
                self.copy_runner(root)
                package = root / "api" / "tests"
                package.mkdir(parents=True)
                (package.parent / "__init__.py").touch()
                (package / "__init__.py").touch()
                for name, kind in zip(api_gates, kinds):
                    (root / name).write_text(
                        "import time\nimport unittest\nfrom pathlib import Path\n"
                        f"Path({name + '.sentinel'!r}).write_text('imported')\n"
                        "with Path('order.txt').open('a') as log:\n"
                        f"    log.write({name + chr(10)!r})\n"
                        "class BoundaryTests(unittest.TestCase):\n"
                        "    def test_boundary(self):\n"
                        f"        Path({name + '.assertion'!r}).write_text('ran')\n"
                        + hangs[kind], encoding="utf-8",
                    )
                self.write_gate(root, failed_script, "def test_ok(): pass\n", exit_code=7)
                self.write_gate(root, later, "def test_ok(): pass\n")
                self.assertEqual(run_tests.check_test_definitions(
                    root / name for name in suites["TESTS"]), [])
                self.assertFalse((root / "order.txt").exists())
                for name in api_gates:
                    self.assertFalse((root / (name + ".sentinel")).exists())
                    self.assertFalse((root / (name + ".hook")).exists())

                result = self.launch_runner(root, (*argv, "--gate-timeout", "1"))
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertEqual(
                    result.stdout.splitlines()[-1],
                    "RELEASE DETERMINISTIC GATES FAILED: "
                    + ", ".join((*api_gates, failed_script)),
                )
                self.assertEqual((root / "order.txt").read_text().splitlines(),
                                 list(suites["TESTS"]))
                for name, kind in zip(api_gates, kinds):
                    self.assertIn(f"GATE TIMED OUT: {name} exceeded 1 seconds",
                                  result.stderr)
                    self.assertEqual((root / (name + ".sentinel")).read_text(), "imported")
                    self.assertEqual((root / (name + ".hook")).exists(), kind == "load_tests")
                    self.assertFalse((root / (name + ".assertion")).exists())
                self.assertEqual(result.stderr.count("GATE TIMED OUT:"), 2)
                self.assertEqual((root / (later + ".sentinel")).read_text(), "started")
                self.assertNotIn("PREFLIGHT FAILED", output)
                self.assertNotIn("PASSED", output)

    def test_real_script_timeout_keeps_later_gate_running_in_each_selection(self):
        for argv, inventory in self.SELECTIONS:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_runner(root)
                first, later = self.SUITES[inventory]
                self.write_gate(root, first, """
                    import time
                    def test_ok(): pass
                    with Path('order.txt').open('a') as log:
                        log.write(Path(__file__).name + '\\n')
                    time.sleep(60)
                    Path('hang.finished').write_text('finished')
                """)
                self.write_gate(root, later, "def test_ok(): pass\n")
                self.assertEqual(run_tests.check_test_definitions(
                    root / name for name in self.SUITES[inventory]), [])
                self.assertFalse((root / "order.txt").exists())
                self.assertFalse((root / (first + ".sentinel")).exists())

                result = self.launch_runner(root, (*argv, "--gate-timeout", "1"))
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertEqual(result.stderr.strip(),
                                 f"GATE TIMED OUT: {first} exceeded 1 seconds")
                self.assertEqual((root / "order.txt").read_text().splitlines(), [first, later])
                self.assertFalse((root / "hang.finished").exists())
                for name in (first, later):
                    self.assertEqual((root / (name + ".sentinel")).read_text(), "started")
                label = ("RELEASE DETERMINISTIC GATES" if inventory == "TESTS"
                         else "HISTORICAL PROTOTYPE CHECKS (NOT RELEASE GATES)")
                self.assertEqual(result.stdout.splitlines()[-1], f"{label} FAILED: {first}")
                for name in self.SUITES[
                        "PROTOTYPE_TESTS" if inventory == "TESTS" else "TESTS"]:
                    self.assertFalse((root / (name + ".sentinel")).exists())
                self.assertNotIn("PREFLIGHT FAILED", output)
                self.assertNotIn("PASSED", output)

    def test_real_unknown_suite_is_rejected_before_any_gate_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_runner(root)
            for gates in self.SUITES.values():
                for name in gates:
                    self.write_gate(root, name, "def test_ok(): pass\n")

            result = self.launch_runner(root, ("--suite", "all"))
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 2, output)
            self.assertIn("argument --suite: invalid choice: 'all'", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse((root / "order.txt").exists())
            for gates in self.SUITES.values():
                for name in gates:
                    self.assertFalse((root / (name + ".sentinel")).exists(), name)
            self.assertNotIn("PASSED", output)

    def test_real_listing_skips_invalid_definitions_and_never_starts_gates(self):
        for argv, inventory in self.SELECTIONS:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_runner(root)
                for gates in self.SUITES.values():
                    for name in gates:
                        # Parseable but rejected by preflight, with a sentinel
                        # that would fire even if listing merely imported a gate.
                        self.write_gate(root, name, """
                            def test_result(): pass
                            def test_result(): pass
                        """)

                result = self.launch_runner(root, (*argv, "--list"))
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertEqual(result.stderr, "")
                selected = self.SUITES[inventory]
                if inventory == "TESTS":
                    heading = [
                        f"RELEASE DETERMINISTIC GATES: {len(selected)} selected",
                        "Excluded historical prototypes: "
                        + ", ".join(self.SUITES["PROTOTYPE_TESTS"]),
                    ]
                else:
                    heading = [
                        "HISTORICAL PROTOTYPE CHECKS (NOT RELEASE GATES): "
                        f"{len(selected)} selected",
                    ]
                self.assertEqual(result.stdout.splitlines(), heading + list(selected))
                self.assertFalse((root / "order.txt").exists())
                for gates in self.SUITES.values():
                    for name in gates:
                        self.assertFalse((root / (name + ".sentinel")).exists(), name)
                self.assertNotIn("PREFLIGHT", output)
                self.assertNotIn("PASSED", output)
                self.assertNotIn("FAILED", output)

    def test_real_gates_use_launcher_interpreter_and_copied_runner_directory(self):
        for argv, inventory in self.SELECTIONS:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "runner"
                root.mkdir()
                self.copy_runner(root)
                selected = self.SUITES[inventory]
                for name in selected:
                    self.write_gate(root, name, """
                        import json
                        import sys

                        def test_ok(): pass

                        Path(__file__).with_suffix('.environment.json').write_text(
                            json.dumps({
                                'executable': sys.executable,
                                'cwd': str(Path.cwd()),
                            }),
                            encoding='utf-8',
                        )
                    """)

                # Launch outside the copied runner directory so inheriting the
                # launcher's cwd cannot accidentally satisfy the child contract.
                result = self.launch_runner(root, argv, cwd=Path(directory))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                for name in selected:
                    with self.subTest(gate=name):
                        recorded = json.loads(
                            (root / name).with_suffix(".environment.json")
                            .read_text(encoding="utf-8")
                        )
                        self.assertEqual(recorded["executable"], sys.executable)
                        self.assertEqual(Path(recorded["cwd"]), root.resolve())
                self.assertEqual((root / "order.txt").read_text(encoding="utf-8")
                                 .splitlines(), list(selected))

    def test_missing_later_selected_source_blocks_every_gate_in_real_process(self):
        for argv, inventory in self.SELECTIONS:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_runner(root)
                first, later = self.SUITES[inventory]
                for gates in self.SUITES.values():
                    for name in gates:
                        if name != later:
                            self.write_gate(root, name, "def test_ok(): pass\n")
                self.assertTrue((root / first).is_file())
                self.assertFalse((root / later).exists())

                result = self.launch_runner(root, argv)
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("TEST DEFINITION PREFLIGHT FAILED:", result.stderr)
                self.assertTrue(any(
                    line.startswith(f"{root / later}:")
                    and "cannot inspect test definitions" in line
                    and "No such file or directory" in line
                    for line in result.stderr.splitlines()
                ), result.stderr)
                self.assertFalse((root / "order.txt").exists())
                for gates in self.SUITES.values():
                    for name in gates:
                        self.assertFalse((root / (name + ".sentinel")).exists(), name)
                self.assertNotIn("PASSED", output)

    def test_later_alias_replacement_blocks_every_gate_in_real_process(self):
        for argv, inventory in self.SELECTIONS:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_runner(root)
                first, later = self.SUITES[inventory]
                self.write_gate(root, first, "def test_ok(): pass\n")
                self.write_gate(root, later, """
                    class Checks:
                        def test_result(self): pass
                    Alias = Checks
                    Alias.test_result = None
                """)
                result = self.launch_runner(root, argv)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("TEST DEFINITION PREFLIGHT FAILED:", result.stderr)
                self.assertIn(str(root / later), result.stderr)
                self.assertIn("overwrites method Alias.test_result", result.stderr)
                self.assertFalse((root / "order.txt").exists())
                for name in (first, later):
                    self.assertFalse((root / (name + ".sentinel")).exists(), name)
                self.assertNotIn("PASSED", result.stdout)

    def test_multiple_invalid_sources_are_all_reported_before_any_gate_starts(self):
        first_cases = (
            ("duplicate definition", """
                def test_result(): pass
                def test_result(): pass
            """, "duplicate module function test_result"),
            ("syntax error", "def test_result(: pass\n",
             "cannot inspect test definitions"),
        )
        for argv, inventory in self.SELECTIONS:
            for case, body, diagnostic in first_cases:
                with self.subTest(argv=argv, case=case), \
                     tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_runner(root)
                    first, later = self.SUITES[inventory]
                    self.write_gate(root, first, body)
                    self.write_gate(root, later, """
                        class Checks:
                            def test_result(self): pass
                        Alias = Checks
                        Alias.test_result = None
                    """)

                    result = self.launch_runner(root, argv)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertIn("TEST DEFINITION PREFLIGHT FAILED:", result.stderr)
                    for name, expected in (
                        (first, diagnostic),
                        (later, "overwrites method Alias.test_result"),
                    ):
                        self.assertTrue(any(
                            line.startswith(f"{root / name}:") and expected in line
                            for line in result.stderr.splitlines()
                        ), result.stderr)
                    self.assertFalse((root / "order.txt").exists())
                    for name in (first, later):
                        self.assertFalse((root / (name + ".sentinel")).exists(), name)
                    self.assertNotIn("PASSED", output)

    def test_failed_real_gate_keeps_later_gate_running_and_reports_failure(self):
        for argv, inventory in self.SELECTIONS:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_runner(root)
                first, later = self.SUITES[inventory]
                self.write_gate(root, first, "def test_ok(): pass\n", exit_code=7)
                self.write_gate(root, later, "def test_ok(): pass\n")

                result = self.launch_runner(root, argv)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual((root / "order.txt").read_text(encoding="utf-8")
                                 .splitlines(), [first, later])
                for name in (first, later):
                    self.assertEqual((root / (name + ".sentinel"))
                                     .read_text(encoding="utf-8"), "started")
                label = ("RELEASE DETERMINISTIC GATES" if inventory == "TESTS"
                         else "HISTORICAL PROTOTYPE CHECKS (NOT RELEASE GATES)")
                self.assertEqual(result.stdout.splitlines()[-1],
                                 f"{label} FAILED: {first}")
                self.assertNotIn("PREFLIGHT FAILED", result.stdout + result.stderr)
                self.assertNotIn("PASSED", result.stdout + result.stderr)

    def test_nested_unittest_gate_really_runs_and_failure_blocks_release(self):
        # API suites have no script entrypoint: importing or executing their
        # source directly would silently skip the actual assertions.
        suites = {
            "TESTS": ("api/tests/test_scheduler.py", "release_later.py"),
            "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
        }
        for argv in ((), ("--suite", "release")):
            for fail in (False, True):
                with self.subTest(argv=argv, fail=fail), \
                     tempfile.TemporaryDirectory() as directory, \
                     patch.object(self, "SUITES", suites):
                    root = Path(directory) / "runner"
                    root.mkdir()
                    self.copy_runner(root)
                    package = root / "api" / "tests"
                    package.mkdir(parents=True)
                    (package.parent / "__init__.py").touch()
                    (package / "__init__.py").touch()
                    (package / "test_scheduler.py").write_text(
                        "import unittest\nfrom pathlib import Path\n"
                        "class SchedulerTests(unittest.TestCase):\n"
                        "    def test_boundary(self):\n"
                        "        with Path('order.txt').open('a') as log:\n"
                        "            log.write('api/tests/test_scheduler.py\\n')\n"
                        f"        self.assertFalse({fail!r}, 'scheduler boundary')\n",
                        encoding="utf-8",
                    )
                    self.write_gate(root, "release_later.py", "def test_ok(): pass\n")
                    result = self.launch_runner(root, argv, cwd=Path(directory))
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, int(fail), output)
                    self.assertIn("Ran 1 test", result.stderr)
                    self.assertEqual((root / "order.txt").read_text().splitlines(),
                                     list(suites["TESTS"]))
                    if fail:
                        self.assertIn("scheduler boundary", result.stderr)
                        self.assertIn("FAILED: api/tests/test_scheduler.py", result.stdout)
                        self.assertNotIn("GATES PASSED", output)
                    else:
                        self.assertIn("ALL 2 DETERMINISTIC GATES PASSED", result.stdout)

    def test_api_zero_exit_before_tests_blocks_release_and_keeps_later_gate_running(self):
        # Keep both failure paths in non-alphabetical inventory order.
        api_gates = ("api/tests/test_initiative.py",
                     "api/tests/test_death_bounded.py")
        later = "release_later.py"
        suites = {
            "TESTS": (*api_gates, later),
            "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
        }
        exits = {
            "import": "raise SystemExit(0)\n",
            "load_tests": (
                "def load_tests(loader, tests, pattern):\n"
                "    Path(__file__ + '.hook').write_text('started')\n"
                "    raise SystemExit(0)\n"
            ),
        }
        for argv in ((), ("--suite", "release")):
            for kinds in (("import", "load_tests"), ("load_tests", "import")):
                with self.subTest(argv=argv, kinds=kinds), \
                     tempfile.TemporaryDirectory() as directory, \
                     patch.object(self, "SUITES", suites):
                    root = Path(directory) / "runner"
                    root.mkdir()
                    self.copy_runner(root)
                    package = root / "api" / "tests"
                    package.mkdir(parents=True)
                    (package.parent / "__init__.py").touch()
                    (package / "__init__.py").touch()
                    for name, kind in zip(api_gates, kinds):
                        (root / name).write_text(
                            "import unittest\nfrom pathlib import Path\n"
                            f"Path({name + '.sentinel'!r}).write_text('imported')\n"
                            "with Path('order.txt').open('a') as log:\n"
                            f"    log.write({name + chr(10)!r})\n"
                            "class BoundaryTests(unittest.TestCase):\n"
                            "    def test_boundary(self):\n"
                            f"        Path({name + '.assertion'!r}).write_text('ran')\n"
                            + exits[kind], encoding="utf-8",
                        )
                    self.write_gate(root, later, "def test_ok(): pass\n")

                    # Source-only preflight must not execute imports or hooks.
                    self.assertEqual(run_tests.check_test_definitions(
                        root / gate for gate in suites["TESTS"]), [])
                    self.assertFalse((root / "order.txt").exists())
                    for name in api_gates:
                        self.assertFalse((root / (name + ".sentinel")).exists())
                        self.assertFalse((root / (name + ".hook")).exists())

                    result = self.launch_runner(root, argv, cwd=Path(directory))
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, output)
                    self.assertEqual(
                        result.stdout.splitlines()[-1],
                        f"RELEASE DETERMINISTIC GATES FAILED: {', '.join(api_gates)}",
                    )
                    self.assertEqual(
                        (root / "order.txt").read_text().splitlines(),
                        list(suites["TESTS"]),
                    )
                    for name, kind in zip(api_gates, kinds):
                        self.assertEqual(
                            (root / (name + ".sentinel")).read_text(), "imported",
                        )
                        self.assertFalse((root / (name + ".assertion")).exists())
                        self.assertEqual(
                            (root / (name + ".hook")).exists(), kind == "load_tests",
                        )
                        self.assertIn(
                            f"UNITTEST GATE FAILED: {name[:-3].replace('/', '.')} "
                            "exited before completing tests (SystemExit: 0)",
                            result.stderr,
                        )
                    self.assertEqual(
                        (root / (later + ".sentinel")).read_text(), "started",
                    )
                    self.assertNotIn("PREFLIGHT FAILED", output)
                    self.assertNotIn("PASSED", output)
                    self.assertNotIn("Ran 1 test", output)

    def test_api_abrupt_zero_exit_blocks_release_and_keeps_later_gate_running(self):
        api_gates = ("api/tests/test_initiative.py",
                     "api/tests/test_death_bounded.py")
        later = "release_later.py"
        suites = {
            "TESTS": (*api_gates, later),
            "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
        }
        exits = {
            "import": "os._exit(0)\n",
            "load_tests": (
                "def load_tests(loader, tests, pattern):\n"
                "    Path(__file__ + '.hook').write_text('started')\n"
                "    os._exit(0)\n"
            ),
        }
        for argv in ((), ("--suite", "release")):
            for kinds in (("import", "load_tests"), ("load_tests", "import")):
                with self.subTest(argv=argv, kinds=kinds), \
                     tempfile.TemporaryDirectory() as directory, \
                     patch.object(self, "SUITES", suites):
                    root = Path(directory) / "runner"
                    root.mkdir()
                    self.copy_runner(root)
                    package = root / "api" / "tests"
                    package.mkdir(parents=True)
                    (package.parent / "__init__.py").touch()
                    (package / "__init__.py").touch()
                    for name, kind in zip(api_gates, kinds):
                        (root / name).write_text(
                            "import os\nimport unittest\nfrom pathlib import Path\n"
                            f"Path({name + '.sentinel'!r}).write_text('imported')\n"
                            "with Path('order.txt').open('a') as log:\n"
                            f"    log.write({name + chr(10)!r})\n"
                            "class BoundaryTests(unittest.TestCase):\n"
                            "    def test_boundary(self):\n"
                            f"        Path({name + '.assertion'!r}).write_text('ran')\n"
                            + exits[kind], encoding="utf-8",
                        )
                    self.write_gate(root, later, "def test_ok(): pass\n")
                    self.assertEqual(run_tests.check_test_definitions(
                        root / gate for gate in suites["TESTS"]), [])
                    self.assertFalse((root / "order.txt").exists())
                    for name in api_gates:
                        self.assertFalse((root / (name + ".sentinel")).exists())
                        self.assertFalse((root / (name + ".hook")).exists())

                    result = self.launch_runner(root, argv, cwd=Path(directory))
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, output)
                    self.assertEqual(result.stdout.splitlines()[-1],
                                     "RELEASE DETERMINISTIC GATES FAILED: "
                                     + ", ".join(api_gates))
                    self.assertEqual((root / "order.txt").read_text().splitlines(),
                                     list(suites["TESTS"]))
                    for name, kind in zip(api_gates, kinds):
                        self.assertEqual((root / (name + ".sentinel")).read_text(),
                                         "imported")
                        self.assertFalse((root / (name + ".assertion")).exists())
                        self.assertEqual((root / (name + ".hook")).exists(),
                                         kind == "load_tests")
                        self.assertIn(
                            f"UNITTEST GATE FAILED: {name[:-3].replace('/', '.')} "
                            "has no valid successful completion evidence",
                            result.stderr,
                        )
                    self.assertEqual((root / (later + ".sentinel")).read_text(),
                                     "started")
                    self.assertNotIn("PREFLIGHT FAILED", output)
                    self.assertNotIn("PASSED", output)
                    self.assertNotIn("Ran 1 test", output)

    def test_empty_api_unittest_gate_cannot_pass_release(self):
        empty_sources = {
            # Source definitions alone do not make a unittest-discoverable test.
            "plain_function": "def test_boundary(): pass\n",
            # Even a real TestCase can be hidden by a module's loading hook.
            "load_tests": (
                "class SchedulerTests(unittest.TestCase):\n"
                "    def test_boundary(self):\n"
                "        Path('assertion.sentinel').write_text('ran')\n"
                "def load_tests(loader, tests, pattern):\n"
                "    return unittest.TestSuite()\n"
            ),
        }
        for name in ("api/tests/test_death_bounded.py",
                     "api/tests/test_initiative.py"):
            suites = {
                "TESTS": (name, "release_later.py"),
                "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
            }
            for argv in ((), ("--suite", "release")):
                for kind, source in empty_sources.items():
                    with self.subTest(name=name, argv=argv, kind=kind), \
                         tempfile.TemporaryDirectory() as directory, \
                         patch.object(self, "SUITES", suites):
                        root = Path(directory) / "runner"
                        root.mkdir()
                        self.copy_runner(root)
                        package = root / "api" / "tests"
                        package.mkdir(parents=True)
                        (package.parent / "__init__.py").touch()
                        (package / "__init__.py").touch()
                        (root / name).write_text(
                            "import unittest\nfrom pathlib import Path\n"
                            "with Path('order.txt').open('a') as log:\n"
                            f"    log.write({name + chr(10)!r})\n"
                            + source, encoding="utf-8",
                        )
                        self.write_gate(root, "release_later.py", "def test_ok(): pass\n")
                        # Preflight must remain source-only: it accepts intact
                        # definitions without importing the gate or its hook.
                        self.assertEqual(run_tests.check_test_definitions(
                            root / gate for gate in suites["TESTS"]), [])
                        self.assertFalse((root / "order.txt").exists())
                        result = self.launch_runner(root, argv, cwd=Path(directory))
                        output = result.stdout + result.stderr
                        self.assertEqual(result.returncode, 1, output)
                        self.assertIn("Ran 0 tests", result.stderr)
                        self.assertIn(
                            f"UNITTEST GATE FAILED: {name[:-3].replace('/', '.')} "
                            "ran no tests", result.stderr,
                        )
                        self.assertIn(f"FAILED: {name}", result.stdout)
                        self.assertNotIn("PASSED", output)
                        self.assertNotIn("PREFLIGHT FAILED", output)
                        self.assertEqual((root / "order.txt").read_text().splitlines(),
                                         list(suites["TESTS"]))
                        self.assertFalse((root / "assertion.sentinel").exists())
                        self.assertEqual((root / "release_later.py.sentinel").read_text(),
                                         "started")

    def test_empty_api_suite_and_assertion_failure_keep_later_script_running(self):
        # Reverse alphabetical order makes a sorted failure summary incorrect.
        api_gates = ("api/tests/test_initiative.py",
                     "api/tests/test_death_bounded.py")
        later = "release_later.py"
        suites = {
            "TESTS": (*api_gates, later),
            "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
        }
        for argv in ((), ("--suite", "release")):
            with self.subTest(argv=argv), \
                 tempfile.TemporaryDirectory() as directory, \
                 patch.object(self, "SUITES", suites):
                root = Path(directory) / "runner"
                root.mkdir()
                self.copy_runner(root)
                package = root / "api" / "tests"
                package.mkdir(parents=True)
                (package.parent / "__init__.py").touch()
                (package / "__init__.py").touch()
                first, second = api_gates
                (root / first).write_text(
                    "import unittest\nfrom pathlib import Path\n"
                    f"Path({first + '.sentinel'!r}).write_text('imported')\n"
                    "class HiddenTests(unittest.TestCase):\n"
                    "    def test_boundary(self):\n"
                    "        Path('hidden_assertion.sentinel').write_text('ran')\n"
                    "def load_tests(loader, tests, pattern):\n"
                    "    Path('loading_hook.sentinel').write_text('ran')\n"
                    "    with Path('order.txt').open('a') as log:\n"
                    f"        log.write({first + chr(10)!r})\n"
                    "    return unittest.TestSuite()\n",
                    encoding="utf-8",
                )
                (root / second).write_text(
                    "import unittest\nfrom pathlib import Path\n"
                    f"Path({second + '.sentinel'!r}).write_text('imported')\n"
                    "class BoundaryTests(unittest.TestCase):\n"
                    "    def test_boundary(self):\n"
                    "        with Path('order.txt').open('a') as log:\n"
                    f"            log.write({second + chr(10)!r})\n"
                    "        self.fail('mixed empty-suite assertion executed')\n",
                    encoding="utf-8",
                )
                self.write_gate(root, later, "def test_ok(): pass\n")

                # Source-only preflight accepts intact definitions without
                # importing gates or invoking load_tests or assertions.
                self.assertEqual(run_tests.check_test_definitions(
                    root / gate for gate in suites["TESTS"]), [])
                self.assertFalse((root / "order.txt").exists())
                for name in suites["TESTS"]:
                    self.assertFalse((root / (name + ".sentinel")).exists())
                self.assertFalse((root / "loading_hook.sentinel").exists())
                self.assertFalse((root / "hidden_assertion.sentinel").exists())

                result = self.launch_runner(root, argv, cwd=Path(directory))
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertIn("Ran 0 tests", result.stderr)
                self.assertIn(
                    f"UNITTEST GATE FAILED: {first[:-3].replace('/', '.')} "
                    "ran no tests", result.stderr,
                )
                self.assertIn("Ran 1 test", result.stderr)
                self.assertIn(
                    "AssertionError: mixed empty-suite assertion executed",
                    result.stderr,
                )
                self.assertEqual(
                    (root / "order.txt").read_text(encoding="utf-8").splitlines(),
                    list(suites["TESTS"]),
                )
                self.assertEqual(
                    (root / "loading_hook.sentinel").read_text(encoding="utf-8"),
                    "ran",
                )
                self.assertFalse((root / "hidden_assertion.sentinel").exists())
                for name in api_gates:
                    self.assertEqual(
                        (root / (name + ".sentinel")).read_text(encoding="utf-8"),
                        "imported",
                    )
                self.assertEqual(
                    (root / (later + ".sentinel")).read_text(encoding="utf-8"),
                    "started",
                )
                self.assertEqual(
                    result.stdout.splitlines()[-1],
                    f"RELEASE DETERMINISTIC GATES FAILED: {', '.join(api_gates)}",
                )
                self.assertNotIn("PREFLIGHT FAILED", output)
                self.assertNotIn("PASSED", output)

    def test_api_loader_errors_block_release_but_not_prototype_selection(self):
        failures = {
            "import": (
                "raise RuntimeError('scheduler import failure')\n",
                "scheduler import failure",
            ),
            "load_tests": (
                "def load_tests(loader, tests, pattern):\n"
                "    with Path('order.txt').open('a') as log:\n"
                "        log.write('load_tests\\n')\n"
                "    raise RuntimeError('scheduler loading hook failure')\n",
                "scheduler loading hook failure",
            ),
        }
        for name in ("api/tests/test_death_bounded.py",
                     "api/tests/test_initiative.py"):
            suites = {
                "TESTS": (name, "release_later.py"),
                "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
            }
            for argv, inventory in self.SELECTIONS:
                for kind, (source, diagnostic) in failures.items():
                    with self.subTest(name=name, argv=argv, kind=kind), \
                         tempfile.TemporaryDirectory() as directory, \
                         patch.object(self, "SUITES", suites):
                        root = Path(directory) / "runner"
                        root.mkdir()
                        self.copy_runner(root)
                        package = root / "api" / "tests"
                        package.mkdir(parents=True)
                        (package.parent / "__init__.py").touch()
                        (package / "__init__.py").touch()
                        (root / name).write_text(
                            "import unittest\nfrom pathlib import Path\n"
                            "with Path('order.txt').open('a') as log:\n"
                            f"    log.write({name + chr(10)!r})\n"
                            "class SchedulerTests(unittest.TestCase):\n"
                            "    def test_boundary(self):\n"
                            "        Path('assertion.sentinel').write_text('ran')\n"
                            + source, encoding="utf-8",
                        )
                        for gate in ("release_later.py", *suites["PROTOTYPE_TESTS"]):
                            self.write_gate(root, gate, "def test_ok(): pass\n")

                        # Intact source definitions pass without executing the
                        # import-time error or the unittest loading hook.
                        self.assertEqual(run_tests.check_test_definitions(
                            root / gate for gate in suites["TESTS"]), [])
                        self.assertFalse((root / "order.txt").exists())
                        result = self.launch_runner(root, argv, cwd=Path(directory))
                        output = result.stdout + result.stderr
                        self.assertNotIn("PREFLIGHT FAILED", output)
                        self.assertFalse((root / "assertion.sentinel").exists())
                        if inventory == "TESTS":
                            self.assertEqual(result.returncode, 1, output)
                            self.assertIn(f"RuntimeError: {diagnostic}", result.stderr)
                            self.assertEqual(
                                result.stdout.splitlines()[-1],
                                f"RELEASE DETERMINISTIC GATES FAILED: {name}",
                            )
                            self.assertNotIn("PASSED", output)
                            expected_order = [name]
                            if kind == "load_tests":
                                expected_order.append("load_tests")
                            expected_order.append("release_later.py")
                            self.assertEqual(
                                (root / "release_later.py.sentinel").read_text(),
                                "started",
                            )
                            for gate in suites["PROTOTYPE_TESTS"]:
                                self.assertFalse((root / (gate + ".sentinel")).exists())
                        else:
                            self.assertEqual(result.returncode, 0, output)
                            self.assertEqual(result.stderr, "")
                            self.assertIn(
                                "ALL 2 HISTORICAL PROTOTYPE CHECKS PASSED "
                                "(NOT RELEASE GATES)", result.stdout,
                            )
                            self.assertNotIn("DETERMINISTIC GATES PASSED", output)
                            self.assertFalse((root / "release_later.py.sentinel").exists())
                            expected_order = list(suites["PROTOTYPE_TESTS"])
                        self.assertEqual(
                            (root / "order.txt").read_text().splitlines(),
                            expected_order,
                        )

    def test_multiple_failed_real_gates_are_reported_in_inventory_order(self):
        # Non-alphabetical order catches summaries that sort instead of retaining
        # the selected inventory's execution order.
        suites = {name: tuple(reversed(gates)) for name, gates in self.SUITES.items()}
        with patch.object(self, "SUITES", suites):
            for argv, inventory in self.SELECTIONS:
                with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.copy_runner(root)
                    selected = self.SUITES[inventory]
                    for name, exit_code in zip(selected, (7, 9)):
                        self.write_gate(root, name, "def test_ok(): pass\n",
                                        exit_code=exit_code)

                    result = self.launch_runner(root, argv)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual((root / "order.txt").read_text(encoding="utf-8")
                                     .splitlines(), list(selected))
                    for name in selected:
                        self.assertEqual((root / (name + ".sentinel"))
                                         .read_text(encoding="utf-8"), "started")
                    label = ("RELEASE DETERMINISTIC GATES" if inventory == "TESTS"
                             else "HISTORICAL PROTOTYPE CHECKS (NOT RELEASE GATES)")
                    self.assertEqual(result.stdout.splitlines()[-1],
                                     f"{label} FAILED: {', '.join(selected)}")
                    self.assertNotIn("PREFLIGHT FAILED", result.stdout + result.stderr)
                    self.assertNotIn("PASSED", result.stdout + result.stderr)

    def test_multiple_failed_api_gates_are_reported_before_later_script_success(self):
        # Reverse alphabetical order so sorting the failures cannot pass.
        api_gates = ("api/tests/test_initiative.py",
                     "api/tests/test_death_bounded.py")
        later = "release_later.py"
        suites = {
            "TESTS": (*api_gates, later),
            "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
        }
        for argv in ((), ("--suite", "release")):
            with self.subTest(argv=argv), \
                 tempfile.TemporaryDirectory() as directory, \
                 patch.object(self, "SUITES", suites):
                root = Path(directory) / "runner"
                root.mkdir()
                self.copy_runner(root)
                package = root / "api" / "tests"
                package.mkdir(parents=True)
                (package.parent / "__init__.py").touch()
                (package / "__init__.py").touch()
                for name in api_gates:
                    # No script entrypoint: only unittest execution reaches the
                    # failing assertion and records this gate in the order log.
                    (root / name).write_text(
                        "import unittest\nfrom pathlib import Path\n"
                        f"Path({name + '.sentinel'!r}).write_text('imported')\n"
                        "class BoundaryTests(unittest.TestCase):\n"
                        "    def test_boundary(self):\n"
                        "        with Path('order.txt').open('a') as log:\n"
                        f"            log.write({name + chr(10)!r})\n"
                        f"        self.fail({name + ' assertion executed'!r})\n",
                        encoding="utf-8",
                    )
                self.write_gate(root, later, "def test_ok(): pass\n")

                # Inspecting valid sources must not import any fixture.
                self.assertEqual(run_tests.check_test_definitions(
                    root / gate for gate in suites["TESTS"]), [])
                self.assertFalse((root / "order.txt").exists())
                for name in suites["TESTS"]:
                    self.assertFalse((root / (name + ".sentinel")).exists())

                result = self.launch_runner(root, argv, cwd=Path(directory))
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertEqual(
                    (root / "order.txt").read_text(encoding="utf-8").splitlines(),
                    list(suites["TESTS"]),
                )
                self.assertEqual(result.stderr.count("Ran 1 test"), 2, output)
                for name in api_gates:
                    self.assertIn(name + " assertion executed", result.stderr)
                    self.assertEqual(
                        (root / (name + ".sentinel")).read_text(encoding="utf-8"),
                        "imported",
                    )
                self.assertEqual(
                    (root / (later + ".sentinel")).read_text(encoding="utf-8"),
                    "started",
                )
                self.assertEqual(
                    result.stdout.splitlines()[-1],
                    f"RELEASE DETERMINISTIC GATES FAILED: {', '.join(api_gates)}",
                )
                self.assertNotIn("PREFLIGHT FAILED", output)
                self.assertNotIn("PASSED", output)

    def test_api_loader_error_and_assertion_failure_keep_later_script_running(self):
        # Deliberately reverse alphabetical order to catch sorted summaries.
        api_gates = ("api/tests/test_initiative.py",
                     "api/tests/test_death_bounded.py")
        later = "release_later.py"
        suites = {
            "TESTS": (*api_gates, later),
            "PROTOTYPE_TESTS": self.SUITES["PROTOTYPE_TESTS"],
        }
        loader_errors = {
            "import": (
                "raise RuntimeError('mixed API import failure')\n",
                "mixed API import failure",
            ),
            "load_tests": (
                "def load_tests(loader, tests, pattern):\n"
                "    Path('loading_hook.sentinel').write_text('ran')\n"
                "    raise RuntimeError('mixed API loading hook failure')\n",
                "mixed API loading hook failure",
            ),
        }
        for argv in ((), ("--suite", "release")):
            for kind, (source, diagnostic) in loader_errors.items():
                with self.subTest(argv=argv, kind=kind), \
                     tempfile.TemporaryDirectory() as directory, \
                     patch.object(self, "SUITES", suites):
                    root = Path(directory) / "runner"
                    root.mkdir()
                    self.copy_runner(root)
                    package = root / "api" / "tests"
                    package.mkdir(parents=True)
                    (package.parent / "__init__.py").touch()
                    (package / "__init__.py").touch()
                    first, second = api_gates
                    (root / first).write_text(
                        "import unittest\nfrom pathlib import Path\n"
                        f"Path({first + '.sentinel'!r}).write_text('imported')\n"
                        "with Path('order.txt').open('a') as log:\n"
                        f"    log.write({first + chr(10)!r})\n"
                        "class LoadingTests(unittest.TestCase):\n"
                        "    def test_boundary(self):\n"
                        "        Path('loader_assertion.sentinel').write_text('ran')\n"
                        + source, encoding="utf-8",
                    )
                    (root / second).write_text(
                        "import unittest\nfrom pathlib import Path\n"
                        f"Path({second + '.sentinel'!r}).write_text('imported')\n"
                        "class BoundaryTests(unittest.TestCase):\n"
                        "    def test_boundary(self):\n"
                        "        with Path('order.txt').open('a') as log:\n"
                        f"            log.write({second + chr(10)!r})\n"
                        "        self.fail('mixed API assertion executed')\n",
                        encoding="utf-8",
                    )
                    self.write_gate(root, later, "def test_ok(): pass\n")

                    # Source inspection must not execute imports, hooks or tests.
                    self.assertEqual(run_tests.check_test_definitions(
                        root / gate for gate in suites["TESTS"]), [])
                    self.assertFalse((root / "order.txt").exists())
                    for name in suites["TESTS"]:
                        self.assertFalse((root / (name + ".sentinel")).exists())
                    self.assertFalse((root / "loading_hook.sentinel").exists())
                    self.assertFalse((root / "loader_assertion.sentinel").exists())

                    result = self.launch_runner(root, argv, cwd=Path(directory))
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, output)
                    self.assertIn(f"RuntimeError: {diagnostic}", result.stderr)
                    self.assertIn(
                        "AssertionError: mixed API assertion executed", result.stderr,
                    )
                    self.assertFalse((root / "loader_assertion.sentinel").exists())
                    self.assertEqual((root / "loading_hook.sentinel").exists(),
                                     kind == "load_tests")
                    self.assertEqual(
                        (root / "order.txt").read_text(encoding="utf-8").splitlines(),
                        list(suites["TESTS"]),
                    )
                    for name in api_gates:
                        self.assertEqual(
                            (root / (name + ".sentinel")).read_text(encoding="utf-8"),
                            "imported",
                        )
                    self.assertEqual(
                        (root / (later + ".sentinel")).read_text(encoding="utf-8"),
                        "started",
                    )
                    self.assertEqual(
                        result.stdout.splitlines()[-1],
                        f"RELEASE DETERMINISTIC GATES FAILED: {', '.join(api_gates)}",
                    )
                    self.assertNotIn("PREFLIGHT FAILED", output)
                    self.assertNotIn("PASSED", output)

    def test_valid_aliases_and_decorators_run_real_gates_in_order(self):
        for argv, inventory in self.SELECTIONS:
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_runner(root)
                first, later = self.SUITES[inventory]
                self.write_gate(root, first, """
                    def decorator(function):
                        return function
                    def test_result(): pass
                    alias = test_result
                    test_result = decorator(test_result)
                    assert alias is test_result
                """)
                self.write_gate(root, later, """
                    def wrapper(function):
                        return function
                    class Checks:
                        def test_result(self): pass
                        alias = test_result
                        test_result = staticmethod(test_result)
                    Checks.test_result = wrapper(Checks.test_result)
                    Alias = Checks
                    Alias.test_result = wrapper(Alias.test_result)
                    assert Alias is Checks
                    assert Checks.alias is Alias.test_result
                """)
                # Unselected sources are deliberately absent. A runner that
                # preflights or executes the wrong suite cannot pass this case.
                result = self.launch_runner(root, argv)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual((root / "order.txt").read_text(encoding="utf-8")
                                 .splitlines(), [first, later])
                for name in (first, later):
                    self.assertEqual((root / (name + ".sentinel"))
                                     .read_text(encoding="utf-8"), "started")
                summary = ("ALL 2 DETERMINISTIC GATES PASSED" if inventory == "TESTS"
                           else "ALL 2 HISTORICAL PROTOTYPE CHECKS PASSED "
                           "(NOT RELEASE GATES)")
                self.assertIn(summary, result.stdout)


if __name__ == "__main__":
    unittest.main()
