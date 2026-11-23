"""Tests for the cut tool (scripts/engine_split/cut_block.py) and its check (cut_check.py)."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split import cut_block, cut_check  # noqa: E402

GAME = '''import game_parts
from game_parts.turn import run, LIMIT
_PART_MODULES = ("game_parts.narration", "game_parts.turn")
'''


def _write_tree(root: Path, source: str) -> None:
    (root / "game_parts").mkdir(parents=True, exist_ok=True)
    (root / "game.py").write_text(GAME, encoding="utf-8")
    (root / "game_parts" / "__init__.py").write_text("", encoding="utf-8")
    (root / "game_parts" / "turn.py").write_text(source, encoding="utf-8")
    (root / "census.json").write_text(json.dumps({"targets": {}}), encoding="utf-8")


def _run_cut(root: Path, **kw) -> tuple[int, str]:
    """Run cut_block.main on the tree under root; returns (exit code, stderr)."""
    argv = ["--file", str(root / "game_parts" / "turn.py"), "--function", kw.get("function", "run"),
            "--anchor", kw["anchor"], "--helper", kw.get("helper", "_cut"),
            "--part", str(root / "game_parts" / "turn_cuts.py"), "--census", str(root / "census.json")]
    if "occurrence" in kw:
        argv += ["--occurrence", str(kw["occurrence"])]
    if "sub_anchor" in kw:
        argv += ["--sub-anchor", kw["sub_anchor"]]
    if "report" in kw:
        argv += ["--report", str(kw["report"])]
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = cut_block.main(argv)
    return code, err.getvalue()


def _call(root: Path, expr: str) -> str:
    """Evaluate `expr` against the fixture tree under root and return its repr (or the error line).

    The parts are exec'd in-process (the guarded test runner allows no subprocess): `game` is a stand-in module that
    collects every name the parts define, as game.py's re-exports do.
    """
    fake = types.ModuleType("game")
    saved = sys.modules.get("game")
    sys.modules["game"] = fake
    try:
        spaces = {}
        for path in sorted((root / "game_parts").glob("*.py")):
            ns = {"__name__": f"fixture.{path.stem}"}
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)
            spaces[path.stem] = ns
            fake.__dict__.update({k: v for k, v in ns.items() if not k.startswith("__")})
    finally:
        if saved is None:
            del sys.modules["game"]
        else:
            sys.modules["game"] = saved
    try:
        return repr(eval(expr, {"turn": types.SimpleNamespace(**spaces["turn"])}))
    except Exception as exc:
        return f"ERROR {type(exc).__name__}: {exc}"


class CutToolCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "cut"
        self.base = Path(self._tmp.name) / "base"

    def cut(self, source: str, **kw):
        source = textwrap.dedent(source).lstrip("\n")
        if "LIMIT" not in source:
            source = source.replace("import game\n", "import game\n\nLIMIT = 3\n", 1)
        self.source = source
        _write_tree(self.base, source)
        _write_tree(self.root, source)
        return _run_cut(self.root, **kw)

    def turn(self) -> str:
        return (self.root / "game_parts" / "turn.py").read_text(encoding="utf-8")

    def part(self) -> str:
        return (self.root / "game_parts" / "turn_cuts.py").read_text(encoding="utf-8")

    def same_behaviour(self, *calls: str) -> None:
        for expr in calls:
            self.assertEqual(_call(self.root, expr), _call(self.base, expr), expr)

    def assert_refused(self, source, reason, **kw):
        code, err = self.cut(source, **kw)
        self.assertEqual(code, 2, err)
        self.assertIn(f"REFUSED {reason}", err)
        self.assertFalse((self.root / "game_parts" / "turn_cuts.py").exists())  # a refusal writes nothing
        self.assertEqual(self.turn(), self.source)


class ClassATests(CutToolCase):
    SRC = '''
        import game

        LIMIT = 3


        def run(a, b):
            base = 1
            if a > b:
                big = a - b
                small = b
            else:
                big = 0
                small = a
            return base + big + small
    '''

    def test_class_a_block_becomes_a_call_and_a_helper(self):
        code, err = self.cut(self.SRC, anchor="if a > b:", helper="_split")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.turn(), textwrap.dedent('''
            import game

            LIMIT = 3


            def run(a, b):
                base = 1
                big, small = game._split(a=a, b=b)
                return base + big + small
        ''').lstrip("\n"))
        self.assertEqual(self.part(), textwrap.dedent('''
            import game


            def _split(*, a, b):
                if a > b:
                    big = a - b
                    small = b
                else:
                    big = 0
                    small = a
                return big, small
        ''').lstrip("\n"))
        game = (self.root / "game.py").read_text(encoding="utf-8")
        self.assertIn("from game_parts.turn_cuts import _split\n", game)
        self.assertIn('_PART_MODULES = ("game_parts.narration", "game_parts.turn", "game_parts.turn_cuts")', game)
        self.same_behaviour("turn.run(3, 1)", "turn.run(1, 3)")

    def test_a_turn_py_constant_gets_the_game_prefix(self):  # Review Focus 4
        src = '''
            import game
            import re

            LIMIT = 3


            def run(a):
                tail = 0
                if a > LIMIT:
                    tail = len(re.findall("x", "xx"))
                return tail
        '''
        code, err = self.cut(src, anchor="if a > LIMIT:")
        self.assertEqual(code, 0, err)
        part = self.part()
        self.assertIn("if a > game.LIMIT:", part)  # LIMIT is a turn.py constant the new part does not bind
        self.assertIn("import re\n", part)         # a plain import of the source file is copied
        self.assertIn("def _cut(*, a, tail):", part)  # `tail` is bound before and only conditionally rebound
        self.same_behaviour("turn.run(5)", "turn.run(1)")

    def test_a_conditionally_rebound_output_is_also_an_input(self):  # Review Focus 1
        src = '''
            import game


            def run(c, x):
                npc_target = "old"
                if c:
                    npc_target = x
                return npc_target
        '''
        code, err = self.cut(src, anchor="if c:")
        self.assertEqual(code, 0, err)
        self.assertIn("def _cut(*, c, npc_target, x):", self.part())
        self.same_behaviour("turn.run(True, 'new')", "turn.run(False, 'new')")
        self.assertEqual(_call(self.root, "turn.run(False, 'new')"), "'old'")

    def test_a_conditionally_bound_input_is_refused(self):
        src = '''
            import game


            def run(c, x):
                if c:
                    seen = x
                if c:
                    return seen
                return None
        '''
        self.assert_refused(src, "conditional input seen", anchor="if c:", occurrence=2)

    def test_a_block_rebinding_a_captured_name_is_refused(self):
        src = '''
            import game


            def run(c):
                npc_target = "a"

                def finish():
                    return npc_target

                if c:
                    npc_target = "b"
                    seen = finish()
                return finish()
        '''
        self.assert_refused(src, "hazard npc_target", anchor="if c:")

    def test_more_than_five_outputs_is_refused(self):
        src = '''
            import game


            def run(c):
                if c:
                    a = 1
                    b = 2
                    d = 3
                    e = 4
                    f = 5
                    g = 6
                return a + b + d + e + f + g
        '''
        self.assert_refused(src, "6 outputs", anchor="if c:")

    def test_class_c_is_refused(self):
        src = '''
            import game


            def run(c, x):
                if c:
                    val = 1
                    if x:
                        return 5
                return val
        '''
        self.assert_refused(src, "class C", anchor="if c:")

    def test_break_or_continue_leaving_the_block_is_refused(self):
        src = '''
            import game


            def run(items):
                for i in items:
                    if i:
                        continue
                    print(i)
                return 0
        '''
        self.assert_refused(src, "forbidden construct: break/continue", anchor="if i:", sub_anchor="for i in items:")

    def test_a_sub_anchor_cuts_inside_a_compound_statement(self):
        src = '''
            import game


            def run(items):
                total = 0
                for i in items:
                    if i:
                        total += i
                return total
        '''
        code, err = self.cut(src, anchor="if i:", sub_anchor="for i in items:")
        self.assertEqual(code, 0, err)
        self.assertIn("        total = game._cut(i=i, total=total)\n", self.turn())
        self.same_behaviour("turn.run([0, 1, 2, 3])")

    def test_an_ambiguous_anchor_needs_an_occurrence(self):
        src = '''
            import game


            def run(c):
                x = 0
                if c:
                    x = 1
                if c:
                    x = 2
                return x
        '''
        self.assert_refused(src, "anchor 'if c:' is ambiguous", anchor="if c:")
        code, err = self.cut(src, anchor="if c:", occurrence=2)
        self.assertEqual(code, 0, err)
        self.same_behaviour("turn.run(True)", "turn.run(False)")

    def test_multi_line_strings_are_not_dedented(self):
        src = '''
            import game


            def run(c):
                text = ""
                if c:
                    text = """a
              b"""
                return text
        '''
        code, err = self.cut(src, anchor="if c:")
        self.assertEqual(code, 0, err)
        self.same_behaviour("turn.run(True)", "turn.run(False)")

    def test_a_nested_function_is_cut_with_the_enclosing_names_as_parameters(self):
        src = '''
            import game


            def run(c):
                seed = 4

                def inner(n):
                    acc = 0
                    if n > 1:
                        acc = n + seed
                    return acc

                return inner(c)
        '''
        code, err = self.cut(src, function="run.inner", anchor="if n > 1:")
        self.assertEqual(code, 0, err)
        self.assertIn("def _cut(*, acc, n, seed):", self.part())
        self.same_behaviour("turn.run(5)", "turn.run(0)")


class ClassBTests(CutToolCase):
    def test_class_b_block_returns_through_the_sentinel(self):
        src = '''
            import game


            def run(c):
                out = 0
                if c == 1:
                    return "one"
                out = 5
                return out
        '''
        code, err = self.cut(src, anchor="if c == 1:", helper="_first")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.turn(), textwrap.dedent('''
            import game

            LIMIT = 3


            def run(c):
                out = 0
                _exit = game._first(c=c)
                if _exit is not game._TURN_FALL_THROUGH:
                    return _exit
                out = 5
                return out
        ''').lstrip("\n"))
        self.assertIn("    return game._TURN_FALL_THROUGH\n", self.part())
        common = self.root / "game_parts" / "turn_cuts_common.py"
        self.assertEqual(common.read_text(encoding="utf-8"), "_TURN_FALL_THROUGH = object()\n")
        game = (self.root / "game.py").read_text(encoding="utf-8")
        self.assertIn("from game_parts.turn_cuts_common import _TURN_FALL_THROUGH\n", game)
        self.assertNotIn('"game_parts.turn_cuts_common"', game)  # no function in it: routing_audit R2
        self.same_behaviour("turn.run(0)", "turn.run(1)", "turn.run(2)")

    def test_a_second_class_b_cut_in_one_function_reuses_the_tool_exit_name(self):
        src = '''
            import game


            def run(c, d):
                if c == 1:
                    return "one"
                if d == 2:
                    return "two"
                return "end"
        '''
        code, err = self.cut(src, anchor="if d == 2:", helper="_second")
        self.assertEqual(code, 0, err)
        code, err = _run_cut(self.root, anchor="if c == 1:", helper="_first")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.turn().count("_exit = game._"), 2)
        self.same_behaviour("turn.run(1, 0)", "turn.run(0, 2)", "turn.run(0, 0)")

    def test_a_user_exit_name_blocks_a_class_b_cut(self):
        src = '''
            import game


            def run(c):
                _exit = c
                if c == 1:
                    return "one"
                return _exit
        '''
        self.assert_refused(src, "the function already uses the name _exit", anchor="if c == 1:")

    def test_bare_return_inside_a_b_block_is_not_fall_through(self):  # Review Focus 3
        src = '''
            import game


            def run(c):
                if c:
                    return
                return "end"
        '''
        code, err = self.cut(src, anchor="if c:")
        self.assertEqual(code, 0, err)
        self.same_behaviour("turn.run(True)", "turn.run(False)")
        self.assertEqual(_call(self.root, "turn.run(True)"), "None")


class ForbiddenTests(CutToolCase):
    def test_locals_globals_vars_yield_await_nonlocal_global_are_refused(self):
        cases = {
            "locals()": ("def", "if c:\n        seen = locals()"),
            "globals()": ("def", "if c:\n        seen = globals()"),
            "vars()": ("def", "if c:\n        seen = vars(c)"),
            "yield": ("def", "if c:\n        yield 1"),
            "await": ("async def", "if c:\n        seen = await c"),
            "nonlocal": ("def", "if c:\n        nonlocal seen\n        seen = 1"),
            "global": ("def", "if c:\n        global SEEN\n        SEEN = 1"),
        }
        for label, (kw, block) in cases.items():
            with self.subTest(label):
                src = f"import game\n\n\n{kw} run(c):\n    seen = 0\n    {block}\n    return seen\n"
                self.assert_refused(src, "forbidden construct", anchor="if c:")


    def test_del_of_a_name_in_a_block_is_refused(self):  # fix round 1
        src = "import game\n\n\ndef run(c):\n    seen = 1\n    if c:\n        del seen\n    return c\n"
        self.assert_refused(src, "forbidden construct", anchor="if c:")

    def test_a_def_or_lambda_output_is_refused(self):  # fix round 1: closure would bind the helper's locals
        for label, body in (("def", "def add(n):\n            return n + base"), ("lambda", "add = lambda n: n + base")):
            with self.subTest(label):
                src = (f"import game\n\n\ndef run(c):\n    base = 1\n    if c:\n        {body}\n"
                       "        base = 5\n    else:\n        add = None\n    return add(c) if add else base\n")
                self.assert_refused(src, "closure output", anchor="if c:")

    def test_a_block_calling_a_nonlocal_writer_is_refused(self):  # Task 3 fix round 1
        src = ("import game\n\n\ndef run(c):\n    spent = 0\n\n    def bump():\n        nonlocal spent\n        spent += 1\n\n"
               "    if c:\n        bump()\n        seen = spent\n    else:\n        seen = 0\n    return seen\n")
        self.assert_refused(src, "nonlocal-written input spent", anchor="if c:")

    def test_a_block_in_a_nested_def_calling_an_outer_nonlocal_writer_is_refused(self):  # Task 3 fix round 2
        src = ("import game\n\n\ndef run(c):\n    spent = 0\n\n    def bump():\n        nonlocal spent\n        spent += 1\n\n"
               "    def inner(c):\n        if c:\n            bump()\n            seen = spent\n        else:\n            seen = 0\n"
               "        return seen\n\n    return inner(c)\n")
        self.assert_refused(src, "nonlocal-written input spent", anchor="if c:", function="run.inner")

    def test_a_block_calling_a_nonlocal_writer_without_reading_its_name_is_cut(self):
        src = ("import game\n\n\ndef run(c):\n    spent = 0\n\n    def bump():\n        nonlocal spent\n        spent += 1\n\n"
               "    if c:\n        bump()\n    return spent\n")
        code, err = self.cut(src, anchor="if c:", helper="_go")
        self.assertEqual(code, 0, err)


class CutCheckTests(CutToolCase):
    SRC = '''
        import game


        def run(a, b):
            base = 1
            # keep the bigger one
            if a > b:
                big = a - b  # difference
                small = b
            else:
                big = 0
                small = a
            return base + big + small
    '''

    def cut_with_report(self) -> Path:
        report = Path(self._tmp.name) / "report.json"
        code, err = self.cut(self.SRC, anchor="if a > b:", helper="_split", report=report)
        self.assertEqual(code, 0, err)
        return report

    def check(self, report) -> list[str]:
        return cut_check.check(self.base, self.root, json.loads(report.read_text(encoding="utf-8"))["helpers"])

    def test_cut_check_reports_changed_0_for_a_clean_cut(self):
        report = self.cut_with_report()
        self.assertEqual(self.check(report), [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cut_check.main(["--base-root", str(self.base), "--root", str(self.root), "--report", str(report)])
        self.assertEqual((code, out.getvalue().strip()), (0, "CHANGED 0"))

    def test_cut_check_reports_a_changed_statement(self):
        report = self.cut_with_report()
        path = self.root / "game_parts" / "turn_cuts.py"
        path.write_text(path.read_text(encoding="utf-8").replace("small = b", "small = b + 1"), encoding="utf-8")
        findings = self.check(report)
        self.assertTrue(any("not the cut block" in f for f in findings), findings)

    def test_cut_check_reports_a_lost_comment(self):
        report = self.cut_with_report()
        path = self.root / "game_parts" / "turn_cuts.py"
        path.write_text(path.read_text(encoding="utf-8").replace("  # difference", ""), encoding="utf-8")
        findings = self.check(report)
        self.assertTrue(any("comments" in f for f in findings), findings)

    def test_cut_check_reports_a_changed_call_site(self):
        report = self.cut_with_report()
        path = self.root / "game_parts" / "turn.py"
        path.write_text(path.read_text(encoding="utf-8").replace("base = 1", "base = 2"), encoding="utf-8")
        findings = self.check(report)
        self.assertTrue(any("base function" in f for f in findings), findings)


if __name__ == "__main__":
    unittest.main()
