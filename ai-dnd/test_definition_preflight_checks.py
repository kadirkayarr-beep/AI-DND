"""Offline fixtures for the deterministic runner's source preflight."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import run_tests
from test_definition_preflight import check_test_definitions


class DefinitionPreflightTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def write_fixture(self, name, source):
        path = self.root / name
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
        return path

    def test_duplicate_test_reports_file_class_method_and_both_lines(self):
        path = self.write_fixture("duplicate.py", """
            class RegressionTests:
                def test_result(self): pass
                def test_result(self): pass
        """)
        self.assertEqual(check_test_definitions([path]), [
            f"{path}:3: duplicate method RegressionTests.test_result "
            "(first defined at line 2, redefined at line 3); "
            "rename or remove the duplicate definition"
        ])

    def test_helpers_and_async_methods_are_not_exempt(self):
        path = self.write_fixture("helpers.py", """
            class RegressionTests:
                def setUp(self): pass
                def setUp(self): pass
                def _helper(self): pass
                async def _helper(self): pass
                async def test_async(self): pass
                async def test_async(self): pass
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 3)
        for method, first, second in [("setUp", 2, 3), ("_helper", 4, 5),
                                      ("test_async", 6, 7)]:
            self.assertTrue(any(
                f"RegressionTests.{method}" in error
                and f"line {first}" in error and f"line {second}" in error
                for error in errors
            ), errors)

    def test_unique_methods_overrides_and_separate_scopes_pass_without_import(self):
        path = self.write_fixture("unique.py", """
            raise AssertionError("the scanner must not execute this module")
            class Base:
                def test_result(self): pass
                def helper(self):
                    def helper(): pass
            class Child(Base):
                def test_result(self): pass
                async def test_other(self): pass
                class Nested:
                    def test_result(self): pass
            class Unrelated:
                def test_result(self): pass
        """)
        self.assertEqual(check_test_definitions([path]), [])

    def test_nested_classes_and_conditional_class_methods_are_checked(self):
        path = self.write_fixture("nested.py", """
            class Outer:
                class Nested:
                    def helper(self): pass
                    def helper(self): pass
                def test_result(self): pass
                if True:
                    def test_result(self): pass
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("Outer.test_result" in error for error in errors))
        self.assertTrue(any("Nested.helper" in error for error in errors))

    def test_all_files_and_redefinitions_are_reported(self):
        paths = [
            self.write_fixture(name, """
                class Checks:
                    def helper(self): pass
                    def helper(self): pass
                    def helper(self): pass
            """) for name in ("first.py", "second.py")
        ]
        errors = check_test_definitions(paths)
        self.assertEqual(len(errors), 4)
        for path in paths:
            self.assertEqual(sum(str(path) in error for error in errors), 2)
        self.assertTrue(all("first defined at line 2" in error for error in errors))

    def test_missing_unreadable_and_invalid_source_fail_closed(self):
        invalid = self.write_fixture("invalid.py", "class Broken:\n")
        unreadable = self.root / "unreadable.py"
        unreadable.write_bytes(b"\xff")
        missing = self.root / "missing.py"
        errors = check_test_definitions([invalid, unreadable, missing])
        self.assertEqual(len(errors), 3)
        for path, error in zip([invalid, unreadable, missing], errors):
            self.assertIn(str(path), error)
            self.assertIn("cannot inspect test definitions", error)

    def test_runner_checks_later_files_before_starting_any_gate(self):
        self.write_fixture("first.py", "class Good:\n    def test_ok(self): pass\n")
        bad = self.write_fixture("second.py", """
            class Bad:
                def test_hidden(self): pass
                def test_hidden(self): pass
        """)
        stderr = StringIO()
        with patch.object(run_tests, "ROOT", self.root), \
             patch.object(run_tests, "TESTS", ("first.py", "second.py")), \
             patch.object(run_tests.subprocess, "run") as execute, \
             redirect_stderr(stderr), redirect_stdout(StringIO()):
            self.assertEqual(run_tests.main(), 1)
        execute.assert_not_called()
        self.assertIn("PREFLIGHT FAILED", stderr.getvalue())
        self.assertIn(f"{bad}:3", stderr.getvalue())
        self.assertIn("Bad.test_hidden", stderr.getvalue())

    def test_runner_executes_unique_gates_in_order_and_preserves_failures(self):
        names = ("first.py", "second.py")
        for name in names:
            self.write_fixture(name, "class Good:\n    def test_ok(self): pass\n")
        for failed in (False, True):
            with self.subTest(failed=failed), \
                 patch.object(run_tests, "ROOT", self.root), \
                 patch.object(run_tests, "TESTS", names), \
                 patch.object(run_tests.subprocess, "run") as execute, \
                 redirect_stdout(StringIO()):
                execute.return_value.returncode = int(failed)
                self.assertEqual(run_tests.main(), int(failed))
                self.assertEqual(execute.call_count, 2)
                self.assertEqual(
                    [call.args[0] for call in execute.call_args_list],
                    [[run_tests.sys.executable, str(self.root / name)] for name in names],
                )
                self.assertTrue(all(
                    call.kwargs["cwd"] == self.root for call in execute.call_args_list
                ))


if __name__ == "__main__":
    unittest.main()
