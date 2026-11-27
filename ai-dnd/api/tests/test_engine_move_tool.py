"""Tests for the in-place move tool (scripts/engine_split/move_block.py)."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import symtable
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.move_block import MoveRefused, move, prefix_names  # noqa: E402
from engine_split.move_block import main as move_block_main  # noqa: E402


class PrefixNamesTests(unittest.TestCase):
    def test_only_free_engine_names_get_the_prefix(self):
        block = "def roll(messages):\n    random = _session().rng\n    return random.randint(1, K) + len(messages) + obj.helper\n"
        out, ins = prefix_names(block, {"_session", "K", "helper", "messages", "random"}, keep_bare=set())
        self.assertEqual(out, "def roll(messages):\n    random = game._session().rng\n"
                              "    return random.randint(1, game.K) + len(messages) + obj.helper\n")
        self.assertEqual([name for _, _, name in ins], ["_session", "K"])

    def test_same_part_constants_stay_bare_but_surface_names_never_do(self):
        out, _ = prefix_names("def f():\n    return RX.match(CLASSES)\n", {"RX", "CLASSES"}, keep_bare={"RX"})
        self.assertEqual(out, "def f():\n    return RX.match(game.CLASSES)\n")

    def test_comments_strings_and_line_endings_are_untouched(self):  # Review Focus 4
        block = "# K is the cap\r\ndef f():\r\n    return 'K' + str(K)  # K\r\n"
        out, _ = prefix_names(block, {"K"}, keep_bare=set())
        self.assertEqual(out, "# K is the cap\r\ndef f():\r\n    return 'K' + str(game.K)  # K\r\n")

    def test_columns_count_characters_not_utf8_bytes(self):
        out, ins = prefix_names("def f():\n    return 'çş' + str(K)\n", {"K"}, keep_bare=set())
        self.assertEqual(out, "def f():\n    return 'çş' + str(game.K)\n")
        self.assertEqual(ins, [(2, 22, "K")])

    def test_nested_scopes_follow_symtable(self):
        block = ("def f(items):\n    K = 1\n    inner = lambda: K\n"
                 "    return [K + x for x in items] + [X for X in items] + [g(y) for y in items]\n")
        out, ins = prefix_names(block, {"K", "X", "g"}, keep_bare=set())
        self.assertEqual([n for _, _, n in ins], ["g"])
        self.assertIn("[game.g(y) for y in items]", out)

    def test_inlined_comprehension_and_genexpr_on_one_line(self):  # real case: _physical_line in game.py
        block = "def f(p):\n    return [s for s in p if not any(s.get(k) for k in K)]\n"
        out, ins = prefix_names(block, {"K"}, keep_bare=set())
        self.assertEqual(out, "def f(p):\n    return [s for s in p if not any(s.get(k) for k in game.K)]\n")

    def test_self_recursion_gets_the_prefix(self):
        out, _ = prefix_names("def f(n):\n    return f(n - 1)\n", {"f"}, keep_bare=set())
        self.assertEqual(out, "def f(n):\n    return game.f(n - 1)\n")

    def test_refusals(self):
        cases = {
            "bare open": "def f():\n    return open('x')\n",
            "default": "def f(x=K):\n    return x\n",
            "kw default": "def f(*, x=K):\n    return x\n",
            "decorator": "@K\ndef f():\n    return 1\n",
            "__file__": "def f():\n    return __file__\n",
            "__name__": "def f():\n    return __name__\n",
            "globals": "def f():\n    return globals()\n",
            "locals": "def f():\n    return locals()\n",
            "vars": "def f(o):\n    return vars(o)\n",
            "sys.modules": "def f():\n    return sys.modules\n",
            "global statement": "def f():\n    global K\n    K = 1\n",
        }
        for label, block in cases.items():
            with self.subTest(label):
                with self.assertRaises(MoveRefused):
                    prefix_names(block, {"K"}, keep_bare=set())

    def test_prefix_outside_a_def_body_is_refused(self):  # F6
        for label, block in {
            "module assignment": "B = re.compile(A)\n",
            "class body": "class C:\n    x = A\n",
            "module comprehension": "L = [A for _ in range(3)]\n",
            "annotation": "def f(x: A):\n    return x\n",
        }.items():
            with self.subTest(label):
                with self.assertRaises(MoveRefused):
                    prefix_names(block, {"A"}, keep_bare=set())

    def test_bare_constants_outside_a_def_body_are_fine(self):
        out, ins = prefix_names("B = re.compile(A)\n", {"A"}, keep_bare={"A"})
        self.assertEqual((out, ins), ("B = re.compile(A)\n", []))

    def test_class_body_inside_a_def_is_in_a_def_body(self):
        out, _ = prefix_names("def f():\n    class C:\n        x = K\n    return C\n", {"K"}, keep_bare=set())
        self.assertIn("x = game.K", out)


class MoveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.game = self.tmp / "game.py"
        self.part = self.tmp / "p.py"

    def test_move_leaves_one_import_line_at_the_old_position(self):
        self.game.write_bytes(b"A = 1\n\n# c\ndef f():\n    return A\n\ndef g():\n    return f()\n")
        result = move(self.game, self.part, ["f"], set())
        self.assertEqual(self.game.read_bytes(),
                         b"A = 1\n\nfrom game_parts.p import f\n\ndef g():\n    return f()\n")
        self.assertEqual(self.part.read_bytes(), b"# c\ndef f():\n    return game.A\n")
        self.assertEqual(result["blocks"][0]["game_span"], (3, 5))
        self.assertEqual(result["insertions"], [(3, 11, "A")])

    def test_two_blocks_one_import_line_at_the_first_position(self):
        self.game.write_bytes(b"def a():\n    return 1\n\nX = 2\n\ndef b():\n    return a() + X\n")
        move(self.game, self.part, ["a", "b"], set())
        self.assertEqual(self.game.read_bytes(), b"from game_parts.p import a, b\n\nX = 2\n\n")
        self.assertEqual(self.part.read_bytes(),
                         b"def a():\n    return 1\n\n\ndef b():\n"
                         b"    return game.a() + game.X\n")  # D-475 (d): E302

    def test_two_blank_lines_only_next_to_a_def_or_class(self) -> None:
        """D-475 (d): moved blocks get two blank lines when a def is beside."""
        self.game.write_bytes(b"A = 1\nB = 2\n\ndef f():\n    return 1\n\nC = 3\n")
        move(self.game, self.part, ["A", "B", "f", "C"], set())
        self.assertEqual(
            self.part.read_bytes(),
            b"A = 1\n\nB = 2\n\n\ndef f():\n    return 1\n\n\nC = 3\n")
        self.game.write_bytes(b"A = 1\n\nB = 2\n")
        self.part.unlink()
        move(self.game, self.part, ["A", "B"], set())
        self.assertEqual(self.part.read_bytes(), b"A = 1\n\nB = 2\n")

    def test_constant_moving_with_its_function_stays_bare_unless_a_surface_target(self):
        src = b"RX = 1\n\ndef f():\n    return RX\n"
        self.game.write_bytes(src)
        move(self.game, self.part, ["RX", "f"], set())
        self.assertIn(b"return RX\n", self.part.read_bytes())
        self.game.write_bytes(src)
        self.part.unlink()
        move(self.game, self.part, ["RX", "f"], {"RX"})
        self.assertIn(b"return game.RX\n", self.part.read_bytes())

    def test_crlf_game_py_keeps_its_line_endings(self):
        self.game.write_bytes(b"def f():\r\n    return K\r\n\r\nK = 1\r\n")
        move(self.game, self.part, ["f"], set())
        self.assertEqual(self.game.read_bytes(), b"from game_parts.p import f\r\n\r\nK = 1\r\n")
        self.assertEqual(self.part.read_bytes(), b"def f():\r\n    return game.K\r\n")

    def test_a_refusal_writes_nothing(self):
        src = b"def ok():\n    return 1\n\ndef bad():\n    return open('x')\n"
        self.game.write_bytes(src)
        with self.assertRaises(MoveRefused):
            move(self.game, self.part, ["ok", "bad"], set())
        self.assertEqual(self.game.read_bytes(), src)
        self.assertFalse(self.part.exists())

    def test_a_name_moved_earlier_is_still_an_engine_name(self):  # F7 amended
        self.game.write_bytes(b"def f():\n    return 1\n\ndef h():\n    return f()\n")
        move(self.game, self.tmp / "p1.py", ["f"], set())
        move(self.game, self.tmp / "p2.py", ["h"], set())
        self.assertEqual((self.tmp / "p2.py").read_bytes(), b"def h():\n    return game.f()\n")

    def test_third_party_imports_stay_bare(self):
        self.game.write_bytes(b"import re\nfrom os import path\n\ndef h():\n    return re.x + path.y\n")
        move(self.game, self.part, ["h"], set())
        self.assertEqual(self.part.read_bytes(), b"def h():\n    return re.x + path.y\n")

    def test_a_name_bound_twice_is_refused(self):
        self.game.write_bytes(b"K = 1\nK = 2\n")
        with self.assertRaises(MoveRefused):
            move(self.game, self.part, ["K"], set())

    def test_a_never_moved_name_is_refused(self):  # spec section 5: create_session stays in game.py
        src = b"def create_session(seed=None):\n    return seed\n"
        self.game.write_bytes(src)
        with self.assertRaises(MoveRefused):
            move(self.game, self.part, ["create_session"], set())
        self.assertEqual(self.game.read_bytes(), src)
        self.assertFalse(self.part.exists())

    def test_a_never_moved_name_bound_by_the_same_statement_is_refused(self):  # T2.4 prep
        src = b"X, RULE_ORDER = 1, 2\n"
        self.game.write_bytes(src)
        with self.assertRaises(MoveRefused):
            move(self.game, self.part, ["X"], set())
        self.assertEqual(self.game.read_bytes(), src)
        self.assertFalse(self.part.exists())

    def test_the_part_list_and_the_narration_list_never_move(self):  # T2.4 prep
        for name in ("_PART_MODULES", "recent_dm_narrations"):
            with self.subTest(name):
                src = f"{name} = ()\n".encode()
                self.game.write_bytes(src)
                with self.assertRaises(MoveRefused):
                    move(self.game, self.part, [name], set())
                self.assertEqual(self.game.read_bytes(), src)
                self.assertFalse(self.part.exists())

    def test_unknown_and_import_names_are_refused(self):
        self.game.write_bytes(b"import re\n\ndef f():\n    return re\n")
        for name in ("nope", "re"):
            with self.subTest(name):
                with self.assertRaises(MoveRefused):
                    move(self.game, self.part, [name], set())


class IdentityAllowlistTests(unittest.TestCase):  # Plan 5 Task 1, spec section 7, Ruling J
    LOCALS = b'def f():\n    x = 1\n    return locals().get("x")\n'
    MODULES = b'def f():\n    return sys.modules["game"]\n'

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.game = self.tmp / "game.py"
        (self.tmp / "game_parts").mkdir()
        self.part = self.tmp / "game_parts" / "p.py"
        self.part.write_bytes(b"import sys\nimport game\n")

    def r6_keys(self) -> set[tuple[str, str]]:
        """(function, name) of every identity use R6 (routing_audit) reports in the part: the row key it would need."""
        from engine_split import routing_audit
        text = self.part.read_text(encoding="utf-8")
        walker = routing_audit._Walker(ast.parse(text), symtable.symtable(text, str(self.part), "exec"))
        uses = [u for u in walker.reads if u.name in routing_audit.IDENTITY_NAMES] + walker.identity
        return {(u.function, u.name) for u in uses}

    def assert_refused_and_untouched(self, game_src: bytes, rows: set[tuple[str, str, str]], names=("f",)):
        self.part.write_bytes(b"import sys\nimport game\n")  # each subtest starts from the same part
        self.game.write_bytes(game_src)
        with self.assertRaises(MoveRefused):
            move(self.game, self.part, list(names), set(), identity_allow=frozenset(rows))
        self.assertEqual(self.game.read_bytes(), game_src)
        self.assertEqual(self.part.read_bytes(), b"import sys\nimport game\n")

    def test_move_block_moves_an_allowlisted_locals_call(self):
        self.game.write_bytes(b"import sys\n\n" + self.LOCALS)
        move(self.game, self.part, ["f"], set(), identity_allow=frozenset({("game_parts/p.py", "f", "locals")}))
        self.assertEqual(self.part.read_bytes(), b"import sys\nimport game\n\n" + self.LOCALS)
        self.assertEqual(self.r6_keys(), {("f", "locals")})  # the row names the use exactly as R6 reports it

    def test_move_block_moves_an_allowlisted_sys_modules_read(self):
        self.game.write_bytes(b"import sys\n\n" + self.MODULES)
        move(self.game, self.part, ["f"], set(), identity_allow=frozenset({("game_parts/p.py", "f", "sys.modules")}))
        self.assertEqual(self.part.read_bytes(), b"import sys\nimport game\n\n" + self.MODULES)
        self.assertEqual(self.r6_keys(), {("f", "sys.modules")})

    def test_move_block_still_refuses_an_unlisted_locals_call(self):  # guard
        for label, rows in {"no row": set(), "a row for another name": {("game_parts/p.py", "f", "sys.modules")}}.items():
            with self.subTest(label):
                self.assert_refused_and_untouched(b"import sys\n\n" + self.LOCALS, rows)

    def test_move_block_refuses_a_listed_identity_use_outside_a_def(self):  # outside a def it reads the part's globals
        for label, (block, name, row) in {
                "module level locals": (b"X = locals()\n", "X", ("game_parts/p.py", "<module>", "locals")),
                "class body locals": (b"class C:\n    Y = locals()\n", "C", ("game_parts/p.py", "C", "locals")),
                "module level sys.modules": (b"M = sys.modules\n", "M", ("game_parts/p.py", "<module>", "sys.modules")),
        }.items():
            with self.subTest(label):
                self.assert_refused_and_untouched(b"import sys\n\n" + block, {row}, names=(name,))

    def test_move_block_refuses_a_row_for_another_part_or_function(self):  # guard
        for label, row in {"another part": ("game_parts/q.py", "f", "sys.modules"),
                           "another function": ("game_parts/p.py", "g", "sys.modules"),
                           "game.py itself": ("game.py", "f", "sys.modules")}.items():
            with self.subTest(label):
                self.assert_refused_and_untouched(b"import sys\n\n" + self.MODULES, {row})

    def test_move_block_still_refuses_dunder_name_even_with_a_row(self):  # guard
        for name, block in {"__name__": b"def f():\n    return __name__\n", "__file__": b"def f():\n    return __file__\n",
                            "globals": b"def f():\n    return globals()\n", "vars": b"def f(o):\n    return vars(o)\n"}.items():
            with self.subTest(name):
                self.assert_refused_and_untouched(b"import sys\n\n" + block, {("game_parts/p.py", "f", name)})

    def test_the_cli_reads_the_identity_allowlist(self):
        rows = self.tmp / "identity_allowlist.json"
        rows.write_text(json.dumps([{"file": "game_parts/p.py", "function": "f", "name": "locals",
                                     "reason": "spec section 7"}]), encoding="utf-8")
        census = self.tmp / "patch_census.json"
        census.write_text(json.dumps({"targets": {}, "not_called_tests": []}), encoding="utf-8")
        self.game.write_bytes(b"import sys\n\n" + self.LOCALS)
        from engine_split.move_block import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(["--game", str(self.game), "--part", str(self.part), "--names", "f", "--census", str(census),
                             "--identity-allowlist", str(rows)])
            except SystemExit as exc:  # argparse: an unknown option exits instead of returning
                code = exc.code
        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertEqual(self.part.read_bytes(), b"import sys\nimport game\n\n" + self.LOCALS)

    def test_the_cli_refuses_a_malformed_allowlist(self) -> None:
        """D-475 (a): a bad allowlist ends in REFUSED and exit 2, no traceback."""
        good = {"file": "game_parts/p.py", "function": "f", "name": "locals",
                "reason": "spec section 7"}
        census = self.tmp / "patch_census.json"
        census.write_text(json.dumps({"targets": {}, "not_called_tests": []}),
                          encoding="utf-8")
        src = b"import sys\n\n" + self.LOCALS
        no_reason = {k: v for k, v in good.items() if k != "reason"}
        bad = {"not a list": json.dumps(good),
               "a row that is not an object": json.dumps(["x"]),
               "a missing key": json.dumps([no_reason]),
               "an extra key": json.dumps([dict(good, extra="x")]),
               "an empty string": json.dumps([dict(good, file=" ")]),
               "a value that is not a string": json.dumps([dict(good, name=3)]),
               "not JSON": "[{"}
        for label, text in bad.items():
            with self.subTest(label):
                rows = self.tmp / "identity_allowlist.json"
                rows.write_text(text, encoding="utf-8")
                self.game.write_bytes(src)
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = move_block_main(
                        ["--game", str(self.game), "--part", str(self.part),
                         "--names", "f", "--census", str(census),
                         "--identity-allowlist", str(rows)])
                self.assertEqual((code, out.getvalue()), (2, ""))
                self.assertTrue(
                    err.getvalue().startswith("REFUSED identity allowlist"),
                    err.getvalue())
                self.assertEqual(self.game.read_bytes(), src)

    def test_an_identity_use_behind_another_name_is_refused(self) -> None:
        """D-475 (b): sys.modules or locals under another name is refused."""
        for label, src in {
            "import as": b"import sys as _sys\n\ndef f():\n    return _sys.modules\n",
            "from import": b"from sys import modules\n\ndef f():\n    return modules\n",
            "from import as": (b"from sys import modules as mods\n\n"
                               b"def f():\n    return mods\n"),
            "through game": b"def f():\n    return game.sys.modules\n",
            "a bare locals": b"def f():\n    g = locals\n    return g()\n",
            "a bare vars": b"def f(o):\n    g = vars\n    return g(o)\n",
        }.items():
            with self.subTest(label):
                self.assert_refused_and_untouched(src, set())

    def test_a_local_named_like_an_identity_function_is_not_refused(self) -> None:
        """D-475 (b) guard: a parameter or local named `vars` is not an identity use."""
        body = b"def f(vars):\n    locals = vars\n    return locals\n"
        self.game.write_bytes(body)
        move(self.game, self.part, ["f"], set())
        self.assertEqual(self.part.read_bytes(), b"import sys\nimport game\n\n" + body)


class MoveCliTests(unittest.TestCase):  # D-348: the command line of move_block.py
    GAME = b"import functools\n\nK = 1\n\ndef a():\n    return K\n\ndef b():\n    return a() + Z\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.census = self.tmp / "patch_census.json"
        self.census.write_text(json.dumps({"targets": {"Z": "data", "Q": "absent"}, "not_called_tests": []}),
                               encoding="utf-8")

    def files(self, folder: str, game: bytes = GAME, part: bytes | None = None) -> tuple[Path, Path]:
        root = self.tmp / folder
        root.mkdir()
        (root / "game.py").write_bytes(game)
        if part is not None:
            (root / "p.py").write_bytes(part)
        return root / "game.py", root / "p.py"

    def cli(self, game: Path, part: Path, *names_args: str, report: Path | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = ["--game", str(game), "--part", str(part), *names_args, "--census", str(self.census)]
        if report:
            argv += ["--report", str(report)]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = move_block_main(argv)
            except SystemExit as exc:  # argparse: an unknown option exits instead of returning
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_the_cli_gives_the_same_files_as_move(self):
        game, part = self.files("direct", part=b"import game\n")
        expected = move(game, part, ["a", "b"], {"Z"})
        names_file = self.tmp / "names.txt"
        names_file.write_text("a\nb\n", encoding="utf-8")
        for label, names_args in (("names", ("--names", "a,b")), ("names-file", ("--names-file", str(names_file)))):
            with self.subTest(label):
                cli_game, cli_part = self.files(label, part=b"import game\n")
                report = self.tmp / f"{label}.json"
                code, out, err = self.cli(cli_game, cli_part, *names_args, report=report)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual((cli_game.read_bytes(), cli_part.read_bytes()), (game.read_bytes(), part.read_bytes()))
                self.assertEqual(out, f"MOVED names=2 import_line={expected['import_line']} "
                                      f"insertions={len(expected['insertions'])}\n")
                self.assertEqual(json.loads(report.read_text(encoding="utf-8")), json.loads(json.dumps(expected)))

    def test_a_refusal_exits_2_and_changes_no_byte(self):
        src = self.GAME + b"\ndef create_session(seed=None):\n    return seed\n"
        game, part = self.files("refused", game=src, part=b"import game\n")
        code, out, err = self.cli(game, part, "--names", "a,create_session")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("REFUSED "), err)
        self.assertIn("create_session", err)
        self.assertEqual(out, "")
        self.assertEqual((game.read_bytes(), part.read_bytes()), (src, b"import game\n"))

    def test_an_absent_census_target_is_not_prefixed(self):
        game, part = self.files("absent", game=b"def f():\n    return Q + Z\n")
        code, _, err = self.cli(game, part, "--names", "f")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(part.read_bytes(), b"def f():\n    return Q + game.Z\n")

    def test_the_cli_keeps_utf8_bytes_and_line_endings(self):  # Review Focus 2
        block = '# ğüşıöç “x” —\ndef f():\n    return "ğüşıöç “x” —"\n'.encode("utf-8")
        game, part = self.files("utf8", game=block + b"\nK = 1\n")
        code, _, err = self.cli(game, part, "--names", "f")
        self.assertEqual((code, err), (0, ""))
        moved = part.read_bytes()
        self.assertFalse(moved.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", moved)
        self.assertEqual(moved, block)
        self.assertEqual(game.read_bytes(), b"from game_parts.p import f\n\nK = 1\n")

    def test_a_multi_name_block_and_a_decorated_function_round_trip(self):  # Plan 1 Task 5 deferred minor
        from engine_split.move_check import check_move
        base = ("import functools\n\nX, Y = 1, 2\n\n# cache it\n@functools.lru_cache(maxsize=None)\n"
                "def roll():\n    return X + K\n\nK = 1\n").encode("utf-8")
        (self.tmp / "base").mkdir()
        (self.tmp / "base" / "game.py").write_bytes(base)
        (self.tmp / "new" / "game_parts").mkdir(parents=True)
        (self.tmp / "new" / "game.py").write_bytes(base)
        part = self.tmp / "new" / "game_parts" / "dice.py"
        part.write_bytes(b"import functools\nimport game\n")
        code, out, err = self.cli(self.tmp / "new" / "game.py", part, "--names", "X,roll")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("MOVED names=3 ", out)  # Y rides along: the statement binds both names
        self.assertIn(b"from game_parts.dice import X, Y, roll\n", (self.tmp / "new" / "game.py").read_bytes())
        moved = {"X": "dice.py", "Y": "dice.py", "roll": "dice.py"}
        result = check_move(self.tmp / "base", self.tmp / "new", moved, {"functions": {}}, "normal")
        self.assertEqual(result["changed"], [])


if __name__ == "__main__":
    unittest.main()
