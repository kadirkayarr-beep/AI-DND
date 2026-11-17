"""Tests for the in-place move tool (scripts/engine_split/move_block.py)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.move_block import MoveRefused, move, prefix_names  # noqa: E402


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
                         b"def a():\n    return 1\n\ndef b():\n    return game.a() + game.X\n")

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

    def test_unknown_and_import_names_are_refused(self):
        self.game.write_bytes(b"import re\n\ndef f():\n    return re\n")
        for name in ("nope", "re"):
            with self.subTest(name):
                with self.assertRaises(MoveRefused):
                    move(self.game, self.part, [name], set())


if __name__ == "__main__":
    unittest.main()
