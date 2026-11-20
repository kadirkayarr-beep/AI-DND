"""Tests for the game.py split inventory tool (scripts/engine_split/inventory.py)."""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split import inventory  # noqa: E402
from engine_split.inventory import (  # noqa: E402
    call_graph,
    closed_helpers,
    constant_clusters,
    top_level_index,
    verify_claims,
)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, src: str, name: str = "game.py") -> Path:
        path = self.tmp / name
        path.write_text(src, encoding="utf-8")
        return path

    def test_index_block_starts_at_the_comment_directly_above(self):
        src = "# banner\n\n# why f exists\n@dec\ndef f():\n    return 1\n"
        f = next(d for d in top_level_index(self.write(src)) if d["name"] == "f")
        self.assertEqual((f["start"], f["def_line"], f["end"]), (3, 4, 6))

    def test_index_lines_count_def_to_end_without_comment_or_decorator(self):
        src = "# why\n@dec\ndef f():\n    a = 1\n    return a\n"
        f = next(d for d in top_level_index(self.write(src)) if d["name"] == "f")
        self.assertEqual(f["lines"], 3)

    def test_index_kinds_cover_every_top_level_statement(self):
        src = (
            "import os\nfrom re import compile as c\nK, L = 1, 2\nM: int = 3\n"
            "def f():\n    pass\nclass C:\n    pass\nif K:\n    pass\nprint(K)\n"
        )
        got = [(d["name"], d["kind"]) for d in top_level_index(self.write(src))]
        self.assertEqual(
            got,
            [("os", "import"), ("c", "import"), ("K", "assign"), ("L", "assign"),
             ("M", "assign"), ("f", "function"), ("C", "class"),
             ("<If@9>", "other"), ("<Expr@11>", "other")],
        )

    def test_call_graph_ignores_locals_and_attributes(self):
        src = "def a():\n    return 1\ndef b():\n    a = 2\n    return a\ndef c(x):\n    return a() + x.a\n"
        self.assertEqual(call_graph(self.write(src)), {"a": [], "b": [], "c": ["a"]})

    def test_call_graph_sees_names_read_in_nested_scopes(self):
        src = "K = 1\ndef a():\n    return 1\ndef b():\n    def inner():\n        return a() + K\n    return [K for _ in inner()]\n"
        self.assertEqual(call_graph(self.write(src))["b"], ["K", "a"])

    def test_constant_clusters_join_dependent_constants(self):
        src = "import re\nA = 'x'\nB = re.compile(A)\nC = 3\n"
        self.assertEqual(constant_clusters(self.write(src)), [["A", "B"], ["C"]])

    def test_closed_helpers_reference_no_engine_function(self):
        src = "K = 1\ndef a():\n    return K\ndef b():\n    return a()\n"
        self.assertEqual(closed_helpers(self.write(src)), ["a"])

    def test_a_caller_of_a_re_exported_function_is_not_closed(self):
        # D-347 helper: a name game.py binds with `from game_parts.<x> import` is a moved function, not an import;
        # a re-exported constant keeps its own kind when the part file says so
        (self.tmp / "game_parts").mkdir()
        (self.tmp / "game_parts" / "p.py").write_text("K = 1\ndef f():\n    return K\n", encoding="utf-8")
        src = ("from game_parts.p import f, K\nimport os\n"
               "def g():\n    return f()\ndef h():\n    return K + os.sep.count('/')\n")
        self.assertEqual(closed_helpers(self.write(src)), ["h"])
        self.assertEqual(closed_helpers(self.write("from game_parts.q import f\ndef g():\n    return f()\n")), [])

    def test_touching_tests_finds_attribute_and_string_uses(self):
        files = {
            "api/tests/test_attr.py": "import game\ngame.X()\n",
            "api/tests/test_string.py": "from unittest.mock import patch\np = patch('game.Y', 1)\n",
            "api/tests/test_object.py": "import game\nfrom unittest import mock\nmock.patch.object(game, 'X')\n",
            "api/tests/test_alias.py": "def t():\n    import game as engine\n    return engine.Y\n",
            "api/tests/test_from.py": "from game import X\n",
            "api/tests/test_other.py": "import game\ngame.XY()\np = 'game.XY'\nq = 'xgame.X'\n",
            "api/tests/helper.py": "import game\ngame.X()\n",
            "test_root.py": "import game\nprint(game.Y)\n",
            "tools/test_elsewhere.py": "import game\ngame.X()\n",
        }
        for rel, src in files.items():
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / rel).write_text(src, encoding="utf-8")
        self.assertEqual(inventory.touching_tests(self.tmp, {"X", "Y"}),
                         ["api.tests.test_alias", "api.tests.test_attr", "api.tests.test_from",
                          "api.tests.test_object", "api.tests.test_string", "test_root"])

    def test_touching_tests_follows_imports_of_touching_helpers(self):
        files = {
            "api/tests/helper.py": "import game\ngame.X()\n",
            "api/tests/test_uses_helper.py": "from api.tests import helper\n",
            "api/tests/sub/__init__.py": "",
            "api/tests/sub/deep.py": "import game\nprint(game.Y)\n",
            "api/tests/mid.py": "from api.tests.sub.deep import f\n",
            "api/tests/test_transitive.py": "import api.tests.mid\n",
            "api/tests/test_from_module.py": "from api.tests.sub import deep\n",
            "api/tests/clean.py": "import game\ngame.Z()\n",
            "api/tests/test_clean.py": "from api.tests import clean\n",
            "test_root_helper.py": "def t():\n    from api.tests.helper import x\n",
            # name level: only names that reach a touching read carry it (town_seed imports one runner helper)
            "api/tests/two.py": "import game\ndef a():\n    return game.X\ndef b():\n    return 1\n",
            "api/tests/test_a.py": "from api.tests.two import a\n",
            "api/tests/test_b.py": "from api.tests.two import b\n",
            "api/tests/seed.py": "from api.tests.two import b, a as aa\ndef fixed():\n    return b()\n"
                                 "def bad():\n    return aa()\n",
            "api/tests/test_seed.py": "from api.tests.seed import fixed\n",
            "api/tests/test_seed_bad.py": "from api.tests.seed import bad\n",
            "api/tests/test_sub.py": "from api.tests.two import a as aa\nclass T:\n    def m(self):\n        return aa()\n",
            # a module imported whole counts by the attributes read on it; a bare use counts the whole module
            "api/tests/test_mod_b.py": "from api.tests import two\ndef t():\n    return two.b()\n",
            "api/tests/test_mod_a.py": "from api.tests import two as t2\ndef t():\n    return t2.a()\n",
            "api/tests/test_mod_bare.py": "from api.tests import two\nprint(two)\n",
        }
        for rel, src in files.items():
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / rel).write_text(src, encoding="utf-8")
        self.assertEqual(inventory.touching_tests(self.tmp, {"X", "Y"}),
                         ["api.tests.test_a", "api.tests.test_from_module", "api.tests.test_mod_a",
                          "api.tests.test_mod_bare", "api.tests.test_seed_bad",
                          "api.tests.test_sub", "api.tests.test_transitive", "api.tests.test_uses_helper",
                          "test_root_helper"])

    def test_bound_names_is_public(self):  # D-364: the surface test reaches it, so it has a public name
        self.assertEqual(inventory.bound_names(ast.parse("def f():\n    pass\n").body[0]), ("function", ["f"]))
        self.assertEqual(inventory.bound_names(ast.parse("A, B = 1, 2\n").body[0]), ("assign", ["A", "B"]))
        self.assertFalse(hasattr(inventory, "_bound"))

    def test_touching_tests_follows_one_import_step(self):  # D-366
        files = {
            "api/tests/a.py": "import game\nTABLE = game.X\n",
            "api/tests/test_b.py": "from api.tests import a\n",
            # b imports a at import time and defines a name that does not read game; importing b runs a
            "api/tests/b.py": "import api.tests.a\ndef f():\n    return 1\n",
            "api/tests/test_c.py": "from api.tests.b import f\n",
            "api/tests/quiet.py": "import game\ndef g():\n    return game.X\n",
            "api/tests/b2.py": "import api.tests.quiet\ndef h():\n    return 1\n",
            "api/tests/test_d.py": "from api.tests.b2 import h\n",
        }
        for rel, src in files.items():
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / rel).write_text(src, encoding="utf-8")
        # quiet reads game only inside a function: importing it (and b2) touches nothing
        self.assertEqual(inventory.touching_tests(self.tmp, {"X"}), ["api.tests.test_b", "api.tests.test_c"])

    def _touching(self, files, names):
        for rel, src in files.items():
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / rel).write_text(src, encoding="utf-8")
        return inventory.touching_tests(self.tmp, names)

    def test_touching_tests_sees_a_session_attribute_read(self):  # D-446: GameSession binds every engine function
        files = {
            "api/tests/test_name.py": "def t(session):\n    return session.X()\n",
            "api/tests/test_attr.py": "class T:\n    def m(self):\n        return self.session.Y\n",
            "api/tests/test_case.py": "def t(ActiveSession):\n    return ActiveSession.X\n",
            "api/tests/test_call.py": "import game\ndef t():\n    return game._session().Y\n",
            "api/tests/helper_s.py": "def h(other_session):\n    return other_session.X\n",
            "api/tests/test_helper.py": "from api.tests.helper_s import h\n",
            "api/tests/test_other_name.py": "def t(session):\n    return session.Z\n",
            "api/tests/test_no_session.py": "def t(world):\n    return world.X\n",
        }
        self.assertEqual(self._touching(files, {"X", "Y"}),
                         ["api.tests.test_attr", "api.tests.test_call", "api.tests.test_case",
                          "api.tests.test_helper", "api.tests.test_name"])

    def test_touching_tests_sees_a_getattr_on_a_session(self):  # D-446
        files = {
            "api/tests/test_getattr.py": "def t(session):\n    return getattr(session, 'X')\n",
            "api/tests/test_getattr_default.py": "def t(self):\n    return getattr(self.session, \"Y\", None)\n",
            "api/tests/test_patch.py": "from unittest import mock\ndef t(session):\n"
                                       "    return mock.patch.object(session, 'X')\n",
            "api/tests/test_other_name.py": "def t(session):\n    return getattr(session, 'Z')\n",
            "api/tests/test_no_session.py": "def t(world):\n    return getattr(world, 'X')\n",
        }
        self.assertEqual(self._touching(files, {"X", "Y"}),
                         ["api.tests.test_getattr", "api.tests.test_getattr_default", "api.tests.test_patch"])

    def test_touching_tests_sees_a_created_session_under_another_name(self):  # D-446
        files = {
            "api/tests/test_created.py": "import game\ndef t():\n    s = game.create_session(seed=1)\n    return s.X\n",
            "api/tests/test_class.py": "from game import GameSession\ndef t():\n    eng = GameSession()\n"
                                       "    return getattr(eng, 'Y')\n",
            "api/tests/test_self.py": "import game\nclass T:\n    def setUp(self):\n        self.a = game.create_session()\n"
                                      "    def t(self):\n        return self.a.X\n",
            "api/tests/test_made.py": "def t(make):\n    s = make()\n    return s.X\n",
            "api/tests/test_created_other.py": "import game\ndef t():\n    s = game.create_session()\n    return s.Z\n",
        }
        self.assertEqual(self._touching(files, {"X", "Y"}),
                         ["api.tests.test_class", "api.tests.test_created", "api.tests.test_self"])

    def test_verify_claims_marks_a_changed_named_set_false_and_a_changed_count_shifted(self):
        game = (
            "from uuid import uuid4\n"
            "def _apply_player_damage():\n    return uuid4()\n"
            "def extra():\n    return uuid4()\n"
        )
        self.write(game)
        (self.tmp / "api" / "tests").mkdir(parents=True)
        (self.tmp / "api" / "tests" / "test_coin_writers.py").write_text(
            'WRITERS = frozenset({"game.py:pay", "x.py:y"})\n', encoding="utf-8")
        rows = {r["claim"]: r for r in verify_claims(self.tmp)}
        uuid_row = next(r for k, r in rows.items() if "uuid4" in k)
        self.assertEqual(uuid_row["status"], "false")
        top = next(r for k, r in rows.items() if k.startswith("top-level functions"))
        self.assertEqual((top["spec_value"], top["measured"], top["status"]), (521, 2, "shifted"))
        coin = next(r for k, r in rows.items() if "WRITERS" in k)
        self.assertEqual(coin["status"], "false")

    def test_verify_claims_on_the_real_engine_returns_valid_rows(self):
        rows = verify_claims(ROOT)
        self.assertGreaterEqual(len(rows), 15)
        for r in rows:
            self.assertEqual(set(r), {"claim", "spec_value", "measured", "status"})
            self.assertIn(r["status"], {"same", "shifted", "false"})


if __name__ == "__main__":
    unittest.main()
