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

    def test_duplicate_module_tests_report_file_name_and_both_lines(self):
        path = self.write_fixture("standalone.py", """
            raise AssertionError("the scanner must not execute this module")
            def test_result(): pass
            def test_result(): pass
            def test_result(): pass
        """)
        self.assertEqual(check_test_definitions([path]), [
            f"{path}:{line}: duplicate module function test_result "
            f"(first defined at line 2, redefined at line {line}); "
            "rename or remove the duplicate definition"
            for line in (3, 4)
        ])

    def test_module_helpers_and_sync_async_collisions_are_not_exempt(self):
        path = self.write_fixture("module_helpers.py", """
            def _helper(): pass
            async def _helper(): pass
            async def test_async(): pass
            def test_async(): pass
            async def other_helper(): pass
            async def other_helper(): pass
        """)
        self.assertEqual(check_test_definitions([path]), [
            f"{path}:{second}: duplicate module function {name} "
            f"(first defined at line {first}, redefined at line {second}); "
            "rename or remove the duplicate definition"
            for name, first, second in [
                ("_helper", 1, 2), ("test_async", 3, 4), ("other_helper", 5, 6)
            ]
        ])

    def test_module_control_flow_does_not_create_separate_namespaces(self):
        path = self.write_fixture("module_blocks.py", """
            if condition:
                def test_branch(): pass
            else:
                def test_branch(): pass
            def helper(): pass
            for item in items:
                async def helper(): pass
            try:
                def test_guarded(): pass
            except Exception:
                def test_guarded(): pass
            with context:
                def helper(): pass
        """)
        self.assertEqual(check_test_definitions([path]), [
            f"{path}:{second}: duplicate module function {name} "
            f"(first defined at line {first}, redefined at line {second}); "
            "rename or remove the duplicate definition"
            for name, first, second in [
                ("test_branch", 2, 4), ("helper", 5, 7),
                ("test_guarded", 9, 11), ("helper", 5, 13)
            ]
        ])

    def test_module_class_local_and_file_namespaces_remain_separate(self):
        source = """
            raise AssertionError("the scanner must not execute this module")
            def helper():
                def helper(): pass
                def helper(): pass
                class Local:
                    def helper(self): pass
            async def test_result():
                async def helper(): pass
            class Outer:
                def helper(self):
                    def test_result(): pass
                class Nested:
                    def helper(self): pass
            class Unrelated:
                def helper(self): pass
        """
        paths = [self.write_fixture(name, source)
                 for name in ("first_module.py", "second_module.py")]
        self.assertEqual(check_test_definitions(paths), [])

    def test_classes_inside_functions_still_have_method_protection(self):
        path = self.write_fixture("local_class.py", """
            def helper():
                class Local:
                    def test_result(self): pass
                    def test_result(self): pass
        """)
        self.assertEqual(check_test_definitions([path]), [
            f"{path}:4: duplicate method Local.test_result "
            "(first defined at line 3, redefined at line 4); "
            "rename or remove the duplicate definition"
        ])

    def test_assignments_report_original_and_replacement_lines_in_each_namespace(self):
        replacements = [
            "helper = None",
            "helper: object = replacement",
            "helper += replacement",
            "helper, other = replacements",
            "other, *helper = replacements",
            "helper = other = replacement",
            "(helper := replacement)",
            "helper = unrelated(original=helper)",
            "helper = factory(helper=helper)",
            "helper = helper()",
            "helper = helper(helper)",
            "helper = wrapper(helper())",
            "class helper: pass",
        ]
        for namespace in ("module", "class"):
            for replacement in replacements:
                with self.subTest(namespace=namespace, replacement=replacement):
                    source = "async def helper(): pass\n" + replacement + "\n"
                    if namespace == "class":
                        source = "class Checks:\n" + textwrap.indent(source, "    ")
                    path = self.write_fixture("rebound.py", source)
                    errors = check_test_definitions([path])
                    first, second = (1, 2) if namespace == "module" else (2, 3)
                    kind = "module function helper" if namespace == "module" \
                        else "method Checks.helper"
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn(f"{path}:{second}:", errors[0])
                    self.assertIn(f"overwrites {kind}", errors[0])
                    self.assertIn(
                        f"first defined at line {first}, rebound at line {second}",
                        errors[0],
                    )

    def test_import_bindings_cannot_replace_functions_or_methods(self):
        imports = [
            "import helper",
            "import helper.submodule",
            "import unrelated as helper",
            "from unrelated import helper",
            "from unrelated import other as helper",
            "from .unrelated import other as helper",
        ]
        for namespace in ("module", "class"):
            for binding in imports:
                with self.subTest(namespace=namespace, binding=binding):
                    source = "def helper(): pass\n" + binding + "\n"
                    if namespace == "class":
                        source = "class Checks:\n" + textwrap.indent(source, "    ")
                    path = self.write_fixture("import_binding.py", source)
                    errors = check_test_definitions([path])
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("import binding overwrites", errors[0])
                    self.assertIn("helper", errors[0])

    def test_wildcard_import_reports_each_previously_defined_function(self):
        path = self.write_fixture("wildcard.py", """
            from earlier import *
            def test_result(): pass
            async def helper(): pass
            from later import *
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 2, errors)
        for error, name, first in zip(
            errors, ("test_result", "helper"), (2, 3)
        ):
            self.assertIn(f"{path}:4: import binding overwrites module function {name}", error)
            self.assertIn(f"first defined at line {first}, rebound at line 4", error)

    def test_control_flow_bindings_share_the_enclosing_namespace(self):
        replacements = [
            "if False:\n    helper = None",
            "for helper in values:\n    pass",
            "with context as helper:\n    pass",
            "try:\n    pass\nexcept Exception as helper:\n    pass",
            "match value:\n    case helper:\n        pass",
            "match value:\n    case [*helper]:\n        pass",
            'match value:\n    case {"key": value, **helper}:\n        pass',
            "del helper",
        ]
        for namespace in ("module", "class"):
            for replacement in replacements:
                with self.subTest(namespace=namespace, replacement=replacement):
                    source = "def helper(): pass\n" + replacement + "\n"
                    if namespace == "class":
                        source = "class Checks:\n" + textwrap.indent(source, "    ")
                    path = self.write_fixture("blocks.py", source)
                    errors = check_test_definitions([path])
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("overwrites", errors[0])
                    self.assertIn("helper", errors[0])

    def test_identity_decorator_assignments_and_new_name_aliases_remain_valid(self):
        path = self.write_fixture("valid_assignments.py", """
            raise AssertionError("must not execute decorators or imports")
            helper = None
            from earlier import helper
            @decorate
            def helper(): pass
            alias = helper
            alias = None
            helper = helper
            helper: object
            helper: object = decorator(helper)
            helper = outer(inner(helper), option=True)
            helper = factory(option=True)(helper)
            other = third = helper
            from other_module import helper as imported_alias
            import helper.submodule as another_alias
            class Checks:
                @decorate
                def helper(self): pass
                alias = helper
                helper = staticmethod(helper)
                helper = classmethod(helper)
                helper = decorator(helper, option=True)
                helper: object = helper
                helper: object
        """)
        self.assertEqual(check_test_definitions([path]), [])

    def test_same_name_bindings_in_other_scopes_do_not_replace_a_function(self):
        source = """
            def helper():
                helper = None
                import unrelated as helper
                def local(): pass
                local = None
            def other():
                global helper
                helper = None
            class Checks:
                helper = None
                def method(self):
                    method = None
                class Nested:
                    method = None
            values = [helper for helper in items]
            values = {helper for helper in items}
            values = {helper: helper for helper in items}
            values = (helper for helper in items)
            value = lambda helper: helper
            obj.helper = None
            mapping["helper"] = None
        """
        paths = [self.write_fixture(name, source) for name in ("one.py", "two.py")]
        self.assertEqual(check_test_definitions(paths), [])

    def test_allowed_wrapping_does_not_reset_first_definition_protection(self):
        path = self.write_fixture("wrapped.py", """
            def helper(): pass
            helper = decorator(helper)
            helper = None
            from other import helper
            def helper(): pass
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 3, errors)
        self.assertTrue(all("first defined at line 1" in error for error in errors))
        self.assertIn("assignment overwrites", errors[0])
        self.assertIn("import binding overwrites", errors[1])
        self.assertIn("duplicate module function", errors[2])

    def test_comprehension_walrus_assignments_are_not_local_iteration_bindings(self):
        expressions = [
            "[(helper := None) for item in items]",
            "{(helper := None) for item in items}",
            "{item: (helper := None) for item in items}",
            "((helper := None) for item in items)",
            "[item for item in items if (helper := None)]",
            "[[(helper := None) for inner in items] for outer in items]",
        ]
        for expression in expressions:
            with self.subTest(expression=expression):
                path = self.write_fixture(
                    "walrus.py", "def helper(): pass\nvalues = " + expression + "\n"
                )
                errors = check_test_definitions([path])
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(
                    f"{path}:2: assignment overwrites module function helper", errors[0]
                )
                self.assertIn("first defined at line 1, rebound at line 2", errors[0])

    def test_runner_rejects_rebinding_in_later_gate_before_any_execution(self):
        replacements = [
            "test_hidden = None",
            "from unrelated import replacement as test_hidden",
            "class Bad:\n    def test_hidden(self): pass\n    test_hidden = None",
            "class Bad:\n    def test_hidden(self): pass\n    import other as test_hidden",
            "class Bad:\n    def test_hidden(self): pass\nBad.test_hidden = None",
            "class Bad:\n    def test_hidden(self): pass\ndel Bad.test_hidden",
            "class Bad:\n    def test_hidden(self): pass\n"
            "if False:\n    Bad.test_hidden = replacement",
        ]
        self.write_fixture("first.py", "def test_ok(): pass\n")
        for replacement in replacements:
            with self.subTest(replacement=replacement):
                bad = self.write_fixture(
                    "later.py",
                    "raise AssertionError('must never import a gate')\n"
                    "def test_hidden(): pass\n" + replacement + "\n",
                )
                stderr = StringIO()
                with patch.object(run_tests, "ROOT", self.root), \
                     patch.object(run_tests, "TESTS", ("first.py", "later.py")), \
                     patch.object(run_tests.subprocess, "run") as execute, \
                     redirect_stderr(stderr), redirect_stdout(StringIO()):
                    self.assertEqual(run_tests.main(), 1)
                execute.assert_not_called()
                self.assertIn("PREFLIGHT FAILED", stderr.getvalue())
                self.assertIn(str(bad), stderr.getvalue())
                self.assertIn("overwrites", stderr.getvalue())
                self.assertIn("test_hidden", stderr.getvalue())
                self.assertIn("first defined at line", stderr.getvalue())
                self.assertIn("rebound at line", stderr.getvalue())

    def test_post_class_writes_report_method_and_original_and_replacement_lines(self):
        replacements = [
            "Checks.helper = None",
            "Checks.helper: object = replacement",
            "Checks.helper += replacement",
            "Checks.helper, other = replacements",
            "other, *Checks.helper = replacements",
            "Checks.helper = other = replacement",
            "del Checks.helper",
            "Checks.helper = unrelated(original=Checks.helper)",
            "Checks.helper = factory(helper=Checks.helper)",
            "Checks.helper = Checks.helper()",
            "Checks.helper = Checks.helper(Checks.helper)",
            "Checks.helper = wrapper(Checks.helper())",
            "Checks.helper = wrapper(Checks.helper, Checks.helper)",
            "Checks.helper = Checks.helper.wrapper(Checks.helper)",
            "for Checks.helper in items:\n    pass",
            "with context as Checks.helper:\n    pass",
            "if False:\n    Checks.helper = None",
        ]
        for replacement in replacements:
            with self.subTest(replacement=replacement):
                path = self.write_fixture(
                    "post_class.py",
                    "class Checks:\n    async def helper(self): pass\n"
                    + replacement + "\n",
                )
                errors = check_test_definitions([path])
                second = 4 if replacement.startswith("if False") else 3
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(f"{path}:{second}: attribute ", errors[0])
                self.assertIn("overwrites method Checks.helper", errors[0])
                self.assertIn(
                    f"first defined at line 2, rebound at line {second}", errors[0]
                )

    def test_post_class_identity_wrapping_and_new_attributes_remain_valid(self):
        path = self.write_fixture("post_class_allowed.py", """
            raise AssertionError("source inspection must never execute this")
            class Checks:
                def helper(self): pass
            Checks = Checks
            Checks.helper = Checks.helper
            Checks.helper: object
            Checks.helper: object = staticmethod(Checks.helper)
            Checks.helper = outer(inner(Checks.helper), option=True)
            Checks.helper = factory(option=True)(Checks.helper)
            Checks.alias = Checks.helper
            Checks.alias = None
            Checks.new_method = replacement
            Checks.metadata = None
        """)
        self.assertEqual(check_test_definitions([path]), [])

    def test_wrapping_does_not_reset_post_class_method_protection(self):
        path = self.write_fixture("post_class_wrapped.py", """
            class Checks:
                def test_result(self): pass
            Checks.test_result = wrapper(Checks.test_result)
            Checks.test_result = None
            del Checks.test_result
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 2, errors)
        for error, second in zip(errors, (4, 5)):
            self.assertIn(
                f"first defined at line 2, rebound at line {second}", error
            )

    def test_post_class_resolution_does_not_follow_rebound_names(self):
        rebindings = [
            "Checks = object()",
            "Checks: object = unrelated",
            "Checks += replacement",
            "Checks, other = values",
            "Checks = other = Checks",
            "(Checks := unrelated)",
            "import unrelated as Checks",
            "from unrelated import Checks",
            "from unrelated import *",
            "del Checks",
            "def Checks(): pass",
            "class Checks: pass",
            "for Checks in items:\n    pass",
            "with context as Checks:\n    pass",
            "try:\n    pass\nexcept Exception as Checks:\n    pass",
            "match value:\n    case Checks:\n        pass",
            "Checks = decorator(Checks)",
        ]
        for rebinding in rebindings:
            with self.subTest(rebinding=rebinding):
                path = self.write_fixture(
                    "rebound_class.py",
                    "class Checks:\n    def test_result(self): pass\n"
                    + rebinding + "\nChecks.test_result = None\n",
                )
                self.assertEqual(check_test_definitions([path]), [])

    def test_unresolved_objects_and_runtime_patch_fixtures_remain_out_of_scope(self):
        path = self.write_fixture("patch_fixtures.py", """
            Checks.test_result = None
            class Checks:
                def test_result(self): pass
                def test_patch(self):
                    with patch.object(Checks, "test_result", None):
                        pass
                    Checks.test_result = None
            alias = unknown
            alias.test_result = None
            obj = Checks()
            obj.test_result = None
            imported.test_result = None
            class Child(Checks): pass
            Child.test_result = None
            class Outer:
                class Nested:
                    def test_result(self): pass
                Checks.test_result = None
            Outer.Nested.test_result = None
            def fixture():
                class Local:
                    def test_result(self): pass
                Local.test_result = None
            with patch.object(Checks, "test_result", None):
                pass
            setattr(Checks, "test_result", None)
            delattr(Checks, "test_result")
            mapping["test_result"] = None
        """)
        self.assertEqual(check_test_definitions([path]), [])

    def test_simple_class_aliases_report_the_written_name_and_both_lines(self):
        aliases = [
            "Alias = Checks",
            "Alias: object = Checks",
            "First = Checks\nAlias = First",
            "if False:\n    Alias = Checks",
        ]
        writes = [
            "Alias.test_result = None",
            "Alias.test_result: object = replacement",
            "Alias.test_result += replacement",
            "Alias.test_result, other = values",
            "Alias.test_result = other = replacement",
            "del Alias.test_result",
            "for Alias.test_result in values:\n    pass",
            "with context as Alias.test_result:\n    pass",
        ]
        for alias in aliases:
            for write in writes:
                with self.subTest(alias=alias, write=write):
                    line = 3 + len(alias.splitlines())
                    path = self.write_fixture(
                        "class_alias.py",
                        "class Checks:\n    async def test_result(self): pass\n"
                        + alias + "\n" + write + "\n",
                    )
                    self.assertEqual(check_test_definitions([path]), [
                        f"{path}:{line}: attribute "
                        f"{'deletion' if write.startswith('del ') else 'assignment'} "
                        "overwrites method Alias.test_result "
                        f"(first defined at line 2, rebound at line {line}); "
                        "use a distinct name or explicit decorator assignment"
                    ])

    def test_alias_rebinding_invalidates_only_the_rebound_name(self):
        rebindings = [
            "Alias = object()",
            "Alias: object = unrelated",
            "Alias += replacement",
            "Alias, other = values",
            "other, *Alias = values",
            "Alias = other = Checks",
            "(Alias := Checks)",
            "import unrelated as Alias",
            "from unrelated import Alias",
            "del Alias",
            "def Alias(): pass",
            "class Alias: pass",
            "for Alias in items:\n    pass",
            "with context as Alias:\n    pass",
            "try:\n    pass\nexcept Exception as Alias:\n    pass",
            "match value:\n    case Alias:\n        pass",
            "match value:\n    case [*Alias]:\n        pass",
            'match value:\n    case {"key": value, **Alias}:\n        pass',
            "[(Alias := unrelated) for item in items]",
            "Alias = decorator(Alias)",
        ]
        for rebinding in rebindings:
            with self.subTest(rebinding=rebinding):
                path = self.write_fixture(
                    "rebound_alias.py",
                    "class Checks:\n    def test_result(self): pass\n"
                    "Alias = Checks\nRetained = Alias\n"
                    + rebinding + "\nAlias.test_result = None\n"
                    "Retained.test_result = None\nChecks.test_result = None\n",
                )
                errors = check_test_definitions([path])
                self.assertEqual(len(errors), 2, errors)
                self.assertIn("overwrites method Retained.test_result", errors[0])
                self.assertIn("overwrites method Checks.test_result", errors[1])

    def test_aliases_keep_original_class_identity_after_source_rebinding(self):
        path = self.write_fixture("retained_alias.py", """
            class Checks:
                def test_result(self): pass
            Alias = Checks
            class Checks:
                def other(self): pass
            Checks.test_result = None
            Alias.test_result = None
            Alias = Checks
            Alias.test_result = None
            Alias.other = None
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 2, errors)
        for error, method, first, second in zip(
            errors, ("test_result", "other"), (2, 5), (7, 10)
        ):
            self.assertIn(f"overwrites method Alias.{method}", error)
            self.assertIn(
                f"first defined at line {first}, rebound at line {second}", error
            )

    def test_alias_wildcard_import_invalidates_all_class_resolutions(self):
        path = self.write_fixture("alias_wildcard.py", """
            class Checks:
                def test_result(self): pass
            Alias = Checks
            Retained = Alias
            from unrelated import *
            Checks.test_result = None
            Alias.test_result = None
            Retained.test_result = None
        """)
        self.assertEqual(check_test_definitions([path]), [])

    def test_alias_identity_wrapping_and_runtime_patches_remain_valid(self):
        path = self.write_fixture("alias_allowed.py", """
            raise AssertionError("must not execute source or decorators")
            class Checks:
                def test_result(self): pass
            Alias = Checks
            Alias = Alias
            Alias: object
            Alias.test_result = Alias.test_result
            Alias.test_result: object = staticmethod(Alias.test_result)
            Alias.test_result = outer(inner(Alias.test_result), option=True)
            Alias.metadata = None
            values = [Alias for Alias in items]
            def fixture():
                Alias.test_result = None
                with patch.object(Alias, "test_result", None):
                    pass
            class Fixture:
                Alias.test_result = None
            with patch.object(Alias, "test_result", None):
                pass
            setattr(Alias, "test_result", None)
            delattr(Alias, "test_result")
        """)
        self.assertEqual(check_test_definitions([path]), [])

    def test_alias_allowances_do_not_reset_method_protection(self):
        path = self.write_fixture("alias_wrapped.py", """
            class Checks:
                def test_result(self): pass
            Alias = Checks
            Alias = Alias
            Alias: object
            values = [Alias for Alias in items]
            Alias.test_result = wrapper(Alias.test_result)
            Alias.test_result = None
            del Checks
            Copied = Alias
            Copied.test_result = None
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 2, errors)
        for error, name, second in zip(errors, ("Alias", "Copied"), (8, 11)):
            self.assertIn(f"overwrites method {name}.test_result", error)
            self.assertIn(
                f"first defined at line 2, rebound at line {second}", error
            )

    def test_unresolved_alias_expressions_do_not_create_class_resolutions(self):
        bindings = [
            "Alias = Checks()",
            "Alias = decorator(Checks)",
            "Alias = other = Checks",
            "Alias, = (Checks,)",
            "(Alias := Checks)",
            "Alias = container.Checks",
            'Alias = mapping["Checks"]',
            "Alias = Checks if condition else unknown",
            "import unrelated as Alias",
            "from unrelated import Checks as Alias",
            "Alias = unknown",
            "Alias = Checks\nAlias = unknown\nCopied = Alias",
        ]
        for binding in bindings:
            with self.subTest(binding=binding):
                path = self.write_fixture(
                    "unresolved_alias.py",
                    "class Checks:\n    def test_result(self): pass\n"
                    + binding + "\nAlias.test_result = None\n"
                    "Copied.test_result = None\n",
                )
                self.assertEqual(check_test_definitions([path]), [])

    def test_runner_rejects_alias_replacement_before_any_gate_executes(self):
        self.write_fixture("first.py", "def test_ok(): pass\n")
        bad = self.write_fixture("later_alias.py", """
            raise AssertionError("must never import a configured gate")
            class Checks:
                def test_result(self): pass
            Alias = Checks
            Alias.test_result = None
        """)
        stderr = StringIO()
        with patch.object(run_tests, "ROOT", self.root), \
             patch.object(run_tests, "TESTS", ("first.py", "later_alias.py")), \
             patch.object(run_tests.subprocess, "run") as execute, \
             redirect_stderr(stderr), redirect_stdout(StringIO()):
            self.assertEqual(run_tests.main(), 1)
        execute.assert_not_called()
        self.assertIn("PREFLIGHT FAILED", stderr.getvalue())
        self.assertIn(f"{bad}:5: attribute assignment", stderr.getvalue())
        self.assertIn("overwrites method Alias.test_result", stderr.getvalue())
        self.assertIn("first defined at line 3, rebound at line 5", stderr.getvalue())

    def test_conditional_classes_are_resolved_without_importing_or_running(self):
        path = self.write_fixture("conditional_class.py", """
            if False:
                class Checks:
                    def setUp(self): pass
                    async def test_result(self): pass
            if False:
                Checks.setUp = None
                Checks.test_result = None
        """)
        errors = check_test_definitions([path])
        self.assertEqual(len(errors), 2, errors)
        for error, name, first, second in zip(
            errors, ("setUp", "test_result"), (3, 4), (6, 7)
        ):
            self.assertIn(f"overwrites method Checks.{name}", error)
            self.assertIn(
                f"first defined at line {first}, rebound at line {second}", error
            )

    def test_runner_executes_gates_with_valid_aliases_and_decorator_assignments(self):
        names = ("wrapped.py", "alias.py")
        self.write_fixture(names[0], """
            def test_result(): pass
            test_result = decorator(test_result)
        """)
        self.write_fixture(names[1], """
            class Checks:
                def test_result(self): pass
                alias = test_result
                test_result = staticmethod(test_result)
            Checks.test_result = wrapper(Checks.test_result)
            Alias = Checks
            Alias.test_result = wrapper(Alias.test_result)
            Alias = unrelated
            Alias.test_result = None
            with patch.object(Checks, "test_result", None):
                pass
            obj.test_result = None
        """)
        with patch.object(run_tests, "ROOT", self.root), \
             patch.object(run_tests, "TESTS", names), \
             patch.object(run_tests.subprocess, "run") as execute, \
             redirect_stdout(StringIO()):
            execute.return_value.returncode = 0
            self.assertEqual(run_tests.main(), 0)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in execute.call_args_list],
            [[run_tests.sys.executable, str(self.root / name)] for name in names],
        )

    def test_runner_rejects_standalone_regression_before_any_gate_executes(self):
        self.write_fixture("first.py", "def test_ok(): pass\n")
        bad = self.write_fixture("test_regression.py", """
            def test_hidden(): pass
            async def test_hidden(): pass
        """)
        stderr = StringIO()
        with patch.object(run_tests, "ROOT", self.root), \
             patch.object(run_tests, "TESTS", ("first.py", "test_regression.py")), \
             patch.object(run_tests.subprocess, "run") as execute, \
             redirect_stderr(stderr), redirect_stdout(StringIO()):
            self.assertEqual(run_tests.main(), 1)
        execute.assert_not_called()
        self.assertIn("PREFLIGHT FAILED", stderr.getvalue())
        self.assertIn(f"{bad}:2: duplicate module function test_hidden", stderr.getvalue())
        self.assertIn("first defined at line 1, redefined at line 2", stderr.getvalue())

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
