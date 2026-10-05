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
                execute.return_value.returncode = 0
                self.assertEqual(run_tests.main(argv), 0)
                self.assertEqual(list(preflight.call_args.args[0]),
                                 [run_tests.ROOT / name for name in run_tests.TESTS])
                self.assertEqual([call.args[0] for call in execute.call_args_list], [
                    ([run_tests.sys.executable, "-m", "unittest",
                      name.removesuffix(".py").replace("/", ".")]
                     if name.startswith("api/tests/") else
                     [run_tests.sys.executable, str(run_tests.ROOT / name)])
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

    def test_each_narrative_failure_blocks_default_and_explicit_release(self):
        for argv in ((), ("--suite", "release")):
            for failed_gate in ("test_narrative_rebalance.py",
                                "test_narrative_safety_calibration.py"):
                output = StringIO()
                with self.subTest(argv=argv, failed_gate=failed_gate), \
                     patch.object(run_tests, "check_test_definitions", return_value=[]), \
                     patch.object(run_tests.subprocess, "run") as execute, \
                     redirect_stdout(output):
                    execute.side_effect = [
                        subprocess.CompletedProcess([], int(name == failed_gate))
                        for name in run_tests.TESTS
                    ]
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
                    execute.side_effect = [
                        subprocess.CompletedProcess([], int(name == failed_gate))
                        for name in run_tests.TESTS
                    ]
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
                self.assertIn(failed_gate, stderr.getvalue())
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
                execute.return_value.returncode = 0
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
