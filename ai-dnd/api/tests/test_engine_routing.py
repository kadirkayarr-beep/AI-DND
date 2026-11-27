"""Tests for the N3 routing audit (scripts/engine_split/routing_audit.py): thirteen static rules on ai-dnd/game_parts."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from api.tests.engine_sources import engine_source_files  # noqa: E402
from engine_split import routing_audit  # noqa: E402
from engine_split.routing_audit import audit, character_names, game_imports, part_files  # noqa: E402

LOCKS = Path(__file__).parent / "engine_split_locks"
TARGETS = json.loads((LOCKS / "patch_census.json").read_text(encoding="utf-8"))["targets"]  # name -> kind (R11 reads the kind)
ALLOWED = set(json.loads((LOCKS / "allowed_imports.json").read_text(encoding="utf-8")))
ALLOWLIST = json.loads((LOCKS / "identity_allowlist.json").read_text(encoding="utf-8"))
CHARACTER_NAMES = character_names(ROOT / "game.py")

# The T1 guard is game.py's first statement (Ruling 1); the rest binds the names the fixtures read through game.
GAME_PY = ('if __name__ == "__main__":\n    import game\n    from game_parts import terminal\n'
           '    raise SystemExit(terminal.run(input_fn=input, print_fn=print))\n'
           "import random\nimport sys\nK = 1\ndef roll_d20():\n    return random.randint(1, 20)\ndef _session():\n    return None\n")

BAD = {
 "R1": "import game\nimport requests\n",
 "R2": "import game\nfrom game_parts import dice\n",
 "R2b": "from game import roll_d20\n",
 "R3": "import game\nfrom uuid import uuid4\ndef f():\n    return uuid4()\n",
 "R3b": "import game\ndef f():\n    return roll_d20()\n",          # roll_d20 is a surface target
 "R3c": "import game\ndef f(p):\n    return open(p)\n",
 "R4": "import game\nCAP = game.K\n",
 "R4b": "import game\ndef f(x=game.K):\n    return x\n",
 "R5": "import game\nB = OTHER_PART_CONSTANT + 1\n",
 "R6": "import game\ndef f():\n    return __file__\n",
 "R7": "import game\ndef f():\n    return helper()\n",
 "R7b": "import game\ndef f():\n    return game.current_hp\n",
}
# Further holes each rule must close (same assertion as BAD).
MORE = {
 "R1": "import game\ndef f():\n    return __import__('requests')\n",                      # dynamic import
 "R2": "import game\nfrom . import dice\n",                                                 # relative import
 "R3": "import game\nimport random\n",                                                      # a patched module bound in the part
 "R4": "import game\n@game.K\ndef f():\n    return 1\n",                                    # decorator
 "R4 ": "import game\nG = game\ndef f():\n    return G.K\n",                                # module-level alias of game
 "R6": "import game\nimport sys\ndef f():\n    return sys.modules\n",
 "R6 ": "import game\ndef f():\n    return globals()\n",
 "R7": "import game\ndef f():\n    return game.no_such_name()\n",                           # Ruling 3: misspelt engine name
 "R7 ": "import game\ndef f():\n    global LATE\n    LATE = 1\n",                            # `global` rebinds the part, not game
}
# Fix round 1: escapes the strong review found; each must give exactly its rule and nothing else.
ESCAPES = [
 ("R3", "import game\nfrom uuid import uuid4 as _u4\ndef f():\n    return _u4()\n"),         # I1 aliased patched name
 ("R3 R11", "import game\nimport ollama as _ol\ndef f():\n    return _ol.chat\n"),       # R11 (Task 4): target via a module
 ("R3 R11", "import game\nimport random as _r\ndef f():\n    return _r.random()\n"),
 ("R3", "import game\nfrom os import path\ndef f():\n    return path.sep\n"),                  # patched module, other name
 ("R7", "def f():\n    return game.K\n"),                                                    # I2 no `import game`
 ("R7", "import game\ndef f():\n    import game\n    return game.K\n"),                       # I2 local import shadows
 ("R7", "import game\ndef f(game):\n    return game.K\n"),                                   # I2 parameter shadows
 ("R7", "import game\ngame = None\n"),                                                      # I2 module rebinding
 ("R3", "import game\nclass C:\n    roll_d20 = staticmethod(roll_d20)\n"),                  # I3 LOAD_NAME falls to global
 ("R3", "import game\ndef f(xs):\n    return [u for uuid4 in xs for u in [uuid4]], [uuid4() for _ in xs]\n"),  # I3 PEP 709
 ("R3", "import game\ndef f():\n    from uuid import uuid4\n    return uuid4()\n"),          # I4 function-local import
 ("R3", "import game\ndef f():\n    import ollama\n    return ollama\n"),
 ("R3 R11", "import game\ndef f():\n    import random\n    return random.random()\n"),
 ("R7", "import game\ndef f(s):\n    return eval(s)\n"),                                      # M4
 ("R7", "import game\ndef f(s):\n    exec(s)\n"),
 ("R7", "def f():\n    return __import__('game').K\n"),                                        # I2 game reached dynamically
 ("R6", "import game\ndef f():\n    return sys.modules\nimport sys\n"),                     # sys imported below its use
 ("R6", "import game\ndef f():\n    return game.sys.modules\n"),                             # sys.modules through game
]
# M1: game.py re-exports roll_d20 from part p (the only case a part may define a patched name).
GAME_REEXPORT = (GAME_PY.replace("def roll_d20():\n    return random.randint(1, 20)\n", "from game_parts.p import roll_d20\n")
                 + '_PART_MODULES = ("game_parts.p",)\n')
FINDING = re.compile(r"^R(?:1[0-3]|[1-9]) \S+:\d+: ")


def reexporting(names: str, part_modules: bool = True) -> str:
    """GAME_PY plus `from game_parts.p import <names>`, and _PART_MODULES when a def is among the names."""
    return GAME_PY + f"from game_parts.p import {names}\n" + ('_PART_MODULES = ("game_parts.p",)\n' if part_modules else "")


# Task 4 (D-349): rules R8-R13. Each bad row gives exactly its rule on the full audit: (rule, part, game.py, extra files).
NEW_BAD = [
 ("R8", "import game\ndef f():\n    return 1\n", GAME_PY, None),                                    # f not imported by game.py
 ("R8", "import game\nK = 2\n", reexporting("K", False), None),                                     # K also bound in game.py
 ("R8", "import game\nX = 1\n", reexporting("X", False) + "from game_parts.q import X\n",
  {"game_parts/q.py": "import game\nX = 2\n"}),                                                       # two parts bind X
 ("R9", "import game\ndef f():\n    return g()\ndef g():\n    return 1\n", reexporting("f, g"), None),
 ("R9", "import game\nclass C:\n    pass\ndef f():\n    return C()\n", reexporting("C, f"), None),
 ("R9", "import game\ndef g():\n    return 1\nX = g()\n", reexporting("X, g"), None),                  # at import time
 ("R10", "import game\ndef f():\n    game.K = 2\n", reexporting("f"), None),
 ("R10", "import game\ndef f():\n    del game.K\n", reexporting("f"), None),
 ("R11", "import game\nimport uuid\ndef f():\n    return uuid.uuid4()\n", reexporting("f"), None),
 ("R11", "import game\nimport builtins\ndef f(p):\n    return builtins.open(p)\n", reexporting("f"), None),
 ("R11", "import game\nimport io\ndef f(p):\n    return io.open(p)\n", reexporting("f"), None),
 ("R12", "import game\ndef f():\n    return getattr(game, 'K')\n", reexporting("f"), None),
 ("R12", "import game\ndef f():\n    g = game\n    return g.K\n", reexporting("f"), None),
 ("R12", "import game\ndef f():\n    setattr(game, 'K', 2)\n", reexporting("f"), None),             # game as an argument
 ("R13", None, GAME_PY, {"game_parts/__init__.py": "import game\nimport re\n"}),
 ("R13", None, GAME_PY, {"game_parts/__init__.py": '"""Parts."""\nimport game\n'}),
]
GAME_ALIAS_ROW = {"file": "game_parts/p.py", "function": "f", "name": "game", "reason": "test"}
# One clean fixture per rule: the full audit gives nothing. (rule, part, game.py, extra files, identity allow-list)
NEW_CLEAN = [
 ("R8", None, GAME_PY, {"game_parts/terminal.py": "import game\ndef run(input_fn, print_fn):\n    return game.K\n"}, None),
 ("R9", "import game\nRX = 1\ndef f():\n    return game.g(), RX\ndef g():\n    return 1\n", reexporting("RX, f, g"), None, None),
 ("R10", "import game\ndef f():\n    return game.K\n", reexporting("f"), None, None),
 ("R11", "import game\ndef f():\n    return game._session().rng.randint(1, 20)\n", reexporting("f"), None, None),
 ("R12", "import game\ndef f():\n    g = game\n    return g.K\n", reexporting("f"), None, [GAME_ALIAS_ROW]),
 ("R13", None, GAME_PY, {"game_parts/__init__.py": "import game\n"}, None),
]


class RoutingAuditTests(unittest.TestCase):
    def setUp(self):
        self.fresh()

    def fresh(self):
        """A new empty root: rows that write different files (q.py, terminal.py) must not leak into the next row."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def tree(self, part: str | None = None, game: str = GAME_PY, extra: dict[str, str] | None = None) -> Path:
        files = {"game.py": game, "game_parts/__init__.py": "import game\n", **(extra or {})}
        if part is not None:
            files["game_parts/p.py"] = part
        for rel, text in files.items():
            path = self.tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return self.tmp

    def run_all(self, root: Path, allowlist=None) -> list[str]:
        # a fixture tree has none of the live lock's functions: it runs with no identity rows unless a test gives some
        # (the live lock is read by test_the_real_tree_is_clean); Plan 5 front-1 adds the lock's first row
        return audit(root, TARGETS, ALLOWED, [] if allowlist is None else allowlist, CHARACTER_NAMES)

    def run_audit(self, root: Path, allowlist=None) -> list[str]:
        """The full audit minus R8: the R1-R7 fixtures define names game.py does not re-export (R8 has its own rows)."""
        return [f for f in self.run_all(root, allowlist) if not f.startswith("R8 ")]

    def test_each_rule_fires_on_its_fixture(self):
        for key, src in [*BAD.items(), *MORE.items()]:
            rule = key.strip()[:2]
            with self.subTest(key=key):
                findings = self.run_audit(self.tree(src))
                self.assertIn(rule, {f.split()[0] for f in findings}, findings)
                for f in findings:
                    self.assertRegex(f, FINDING)

    def test_a_clean_part_passes(self):
        src = "import game\nimport re\nRX = re.compile('a')\ndef f(s):\n    random = game._session().rng\n    return RX.match(s), game.roll_d20(), random\n"
        self.assertEqual(self.run_audit(self.tree(src)), [])

    def test_each_escape_gives_exactly_its_rule(self):
        for rule, src in ESCAPES:
            with self.subTest(src=src):
                findings = self.run_audit(self.tree(src))
                self.assertEqual({f.split()[0] for f in findings}, set(rule.split()), findings)

    def test_each_new_rule_fires_alone_on_its_fixture(self):
        for rule, src, game, extra in NEW_BAD:
            with self.subTest(rule=rule, src=src, extra=extra):
                self.fresh()
                findings = self.run_all(self.tree(src, game=game, extra=extra))
                self.assertEqual({f.split()[0] for f in findings}, {rule}, findings)
                for f in findings:
                    self.assertRegex(f, FINDING)

    def test_each_new_rule_passes_its_clean_fixture(self):
        for rule, src, game, extra, allowlist in NEW_CLEAN:
            with self.subTest(rule=rule):
                self.fresh()
                self.assertEqual(self.run_all(self.tree(src, game=game, extra=extra), allowlist), [])

    def test_re_exports_reads_the_top_level_part_imports_of_game_py(self):
        from engine_split.routing_audit import re_exports
        game = reexporting("f, g") + "from game_parts.q import X\n"
        self.assertEqual(re_exports(self.tree(game=game)), {"p": ["f", "g"], "q": ["X"]})
        self.assertEqual(re_exports(self.tree(game=GAME_PY)), {})   # the __main__ guard's terminal import is not one

    def test_a_moved_surface_function_may_be_defined_in_its_part(self):
        src = "import game\ndef roll_d20():\n    return game._session().rng.randint(1, 20)\n"
        self.assertEqual(self.run_audit(self.tree(src, game=GAME_REEXPORT)), [])

    def test_part_modules_and_the_reexport_lines_agree(self):
        moved = "import game\ndef roll_d20():\n    return game._session().rng.randint(1, 20)\nK2 = 1\n"
        plain = GAME_REEXPORT.replace('_PART_MODULES = ("game_parts.p",)\n', "")
        cases = [
            (moved, plain + "_PART_MODULES = ()\n", "game_parts.p"),                         # re-exported def, empty list
            (moved, plain, "game_parts.p"),                                                  # re-exported def, no list at all
            ("import game\n", GAME_PY + '_PART_MODULES = ("game_parts.p",)\n', "game_parts.p"),  # entry with no re-export
            (moved, GAME_REEXPORT + '_PART_MODULES = ("game_parts.p",)\n', "_PART_MODULES"),  # bound twice
            (moved, plain + '_PART_MODULES = tuple(["game_parts.p"])\n', "_PART_MODULES"),    # not a tuple literal
        ]
        for src, game, word in cases:
            with self.subTest(game=game[-60:]):
                findings = self.run_audit(self.tree(src, game=game))
                self.assertEqual([f.split(":")[0] for f in findings], ["R2 game.py"], findings)
                self.assertIn(word, findings[0])
        # a re-exported constant alone (like _SPEECH_SPAN_RE) does not put its part in the list
        constant_only = GAME_PY + "from game_parts.p import K2\n"
        self.assertEqual(self.run_audit(self.tree("import game\nK2 = 1\n", game=constant_only)), [])
        self.assertEqual(self.run_audit(self.tree(moved, game=GAME_REEXPORT)), [])

    def test_the_accepted_blind_spots_are_documented_and_still_unseen(self) -> None:
        """D-349, owner S25 (a): the audit does not see these; the docstring says so."""
        self.assertIn("Known blind spots", routing_audit.__doc__)
        head = "import game\nimport builtins\n"
        for spot, src in (
            ("builtins.eval", head + "def f(s):\n    return builtins.eval(s)\n"),
            ("getattr on a module",
             head + "def f():\n    return getattr(builtins, 'open')\n"),
        ):
            with self.subTest(spot):
                self.assertIn(spot, routing_audit.__doc__)
                self.fresh()
                tree = self.tree(src, game=reexporting("f"))
                self.assertEqual(self.run_all(tree), [])

    def test_a_patched_name_is_defined_only_in_the_part_game_py_reexports_it_from(self):
        bound = "patched name roll_d20 is bound in the part"
        q = {"game_parts/q.py": "import game\ndef roll_d20():\n    return 1\n"}
        cases = [
            ("import game\ndef open(p):\n    return p\n", GAME_REEXPORT, None, "patched name open is bound in the part"),
            ("import game\ndef roll_d20():\n    return 1\n", GAME_PY, None, bound),         # game.py defines it itself
            ("import game\ndef roll_d20():\n    return 1\n",
             GAME_PY.replace("def roll_d20():\n    return random.randint(1, 20)\n", "from game_parts.q import roll_d20\n"), q, bound),
            ("import game\nroll_d20 += 1\n", GAME_REEXPORT, None, bound),
            ("import game\nroll_d20, b = 1, 2\n", GAME_REEXPORT, None, bound),
        ]
        for src, game, extra, message in cases:
            with self.subTest(src=src, game=game[-40:]):
                findings = [f for f in self.run_audit(self.tree(src, game=game, extra=extra)) if f.startswith("R3 game_parts/p.py")]
                self.assertTrue(any(message in f for f in findings), findings)

    def test_a_string_patch_target_on_a_part_is_reported_outside_game_py(self):
        extra = {"api/tests/test_x.py": "from unittest.mock import patch\nimport pkgutil, sys\n"
                 "def test_a():\n    with patch('game_parts.terminal.run'):\n        pass\n"
                 "    pkgutil.resolve_name('game_parts.x')\n    sys.modules['game_parts.x']\n"}
        self.assertEqual([f.split(":")[0] + ":" + f.split(":")[1] for f in self.run_audit(self.tree(extra=extra))],
                         ["R2 api/tests/test_x.py:4", "R2 api/tests/test_x.py:6", "R2 api/tests/test_x.py:7"])

    def test_a_part_module_name_used_as_data_is_not_an_import(self):
        extra = {"api/tests/test_x.py": "import game\ndef test_a(self):\n"
                 "    self.assertEqual(game.f.__module__, 'game_parts.p')\n"
                 "    self.assertEqual(game._PART_MODULES, ('game_parts.p',))\n"
                 "    assert game.f.__module__ == 'game_parts.p'\n"
                 "    surface = {'f': {'kind': 'function', 'module': 'game_parts.x'}}\n"
                 "    surface['f']['module'] = 'game_parts.y'\n"}
        self.assertEqual(self.run_audit(self.tree(extra=extra)), [])

    def test_an_allowlisted_identity_name_passes_and_only_that_one(self):
        src = "import game\ndef f():\n    return __file__\ndef g():\n    return __file__, __name__\n"
        row = {"file": "game_parts/p.py", "function": "f", "name": "__file__", "reason": "test"}
        findings = self.run_audit(self.tree(src), [row])
        self.assertEqual([f.split(":")[0] + ":" + f.split(":")[1] for f in findings],
                         ["R6 game_parts/p.py:5", "R6 game_parts/p.py:5"], findings)
        self.assertEqual(sorted(f.rsplit(" ", 1)[-1] for f in findings), ["__file__", "__name__"])

    def test_an_allowlist_row_that_matches_nothing_is_reported(self):
        row = {"file": "game_parts/p.py", "function": "f", "name": "__file__", "reason": "stale"}
        findings = self.run_audit(self.tree("import game\n"), [row])
        self.assertEqual([f.split()[0] for f in findings], ["R6"], findings)

    def test_a_test_file_importing_game_parts_is_reported(self):
        root = self.tree(extra={"api/tests/test_x.py": "from game_parts import terminal\n"})
        self.assertEqual([f.split(":")[0] for f in self.run_audit(root)], ["R2 api/tests/test_x.py"])

    def test_a_star_reexport_in_game_py_is_reported(self):
        findings = self.run_audit(self.tree(game=GAME_PY + "from game_parts.dice import *\n"))
        self.assertEqual([f.split(":")[0] for f in findings], ["R2 game.py"], findings)

    def test_the_game_py_main_guard_is_the_one_allowed_game_parts_import(self):
        self.assertEqual(self.run_audit(self.tree()), [])
        findings = self.run_audit(self.tree(game=GAME_PY + "def f():\n    import game\n    from game_parts import terminal\n"))
        self.assertEqual([f.split(":")[0] for f in findings], ["R2 game.py", "R2 game.py"], findings)
        findings = self.run_audit(self.tree(game='"""doc"""\n' + GAME_PY))   # the guard is no longer first
        self.assertEqual([f.split(":")[0] for f in findings], ["R2 game.py", "R2 game.py"], findings)

    def test_the_real_tree_is_clean(self):
        self.assertEqual(audit(ROOT, TARGETS, ALLOWED, ALLOWLIST, CHARACTER_NAMES), [])

    def test_the_audit_reads_the_parts_engine_source_files_names(self):
        self.assertEqual(part_files(ROOT), engine_source_files(ROOT)[1:])

    def test_character_names_are_the_keys_of_character_globals(self):
        self.assertEqual(len(CHARACTER_NAMES), 22)
        self.assertLessEqual({"character_name", "character_race", "character_class", "current_hp", "modifiers"}, CHARACTER_NAMES)

    def test_the_allowed_imports_lock_equals_what_the_engine_imports(self):
        from engine_split.routing_audit import engine_imports
        lock = json.loads((LOCKS / "allowed_imports.json").read_text(encoding="utf-8"))
        self.assertEqual(lock, sorted(set(lock)))
        self.assertEqual(lock, engine_imports(ROOT))   # game.py + parts: a move keeps the union, an appended module fails
        self.assertLessEqual(set(game_imports(ROOT / "game.py")), set(lock))
        self.assertEqual([m for m in lock if m.split(".")[0] in sys.stdlib_module_names or m.split(".")[0] in {"game", "game_parts"}], [])


    def test_a_walrus_inside_a_generator_binds_the_enclosing_function(self):
        src = 'import game\n\n\ndef f(text):\n    return min((p for m in ".!?" if (p := text.find(m)) >= 0), default=0)\n'
        self.assertEqual(self.run_audit(self.tree(src)), [])

    def test_a_module_level_walrus_inside_a_generator_binds_the_part(self):
        src = 'import game\n\nFIRST = min((p for m in ".!?" if (p := "a.b".find(m)) >= 0), default=0)\n'
        self.assertEqual(self.run_audit(self.tree(src)), [])

    def test_a_walrus_inside_a_lambda_inside_a_generator_binds_the_lambda_not_the_part(self):
        src = 'import game\n\nL = list((lambda: (y := 1)) for _ in "a")\nZ = y\n'
        self.assertIn("R5 game_parts/p.py:4: y is not bound in this part, its imports or builtins", self.run_audit(self.tree(src)))

    def test_another_modules_attribute_named_like_a_patched_builtin_is_not_r11(self):
        """talk_mode.open is talk_mode's own function, not the builtin open tests patch as game.open (Task 5 rehearsal)."""
        src = "import game\nimport talk_mode\ndef f(w):\n    return talk_mode.open(w, 'n', turn=0)\n"
        self.assertEqual(TARGETS["open"], "absent")
        self.assertEqual(self.run_all(self.tree(src, game=reexporting("f"))), [])

    def test_a_module_that_re_exports_a_builtin_is_r11(self):
        """D-440: a module that binds open from builtins hands out the builtin; a patch on game.open cannot reach it."""
        src = "import game\nimport talk_mode\ndef f(p):\n    return talk_mode.open(p)\n"
        for shim in ("from builtins import open\n", "import builtins\nopen = builtins.open\n"):
            with self.subTest(shim=shim):
                self.fresh()
                findings = self.run_all(self.tree(src, game=reexporting("f"), extra={"talk_mode.py": shim}))
                self.assertEqual([f.split(":")[0] + ":" + f.split(":")[1] for f in findings], ["R11 game_parts/p.py:4"], findings)

    def test_a_modules_own_open_is_still_not_r11(self):
        """Guard (b585dd96): the module's own def open is not the builtin, even with its source in the tree."""
        src = "import game\nimport talk_mode\ndef f(w):\n    return talk_mode.open(w, 'n', turn=0)\n"
        extra = {"talk_mode.py": "import builtins\ndef open(w, n, turn=0):\n    return builtins.len(w)\n"}
        self.assertEqual(self.run_all(self.tree(src, game=reexporting("f"), extra=extra)), [])


class EngineSourcesNeverReflectLocalsTests(unittest.TestCase):
    """T2: locals()/globals()/vars() hide names from block_io and cut_block, so no game_parts file may call them."""

    def test_no_engine_file_calls_locals_globals_or_vars(self):
        import ast

        hits = []
        for path in engine_source_files()[1:]:  # game_parts only; game.py names its own namespace (3 globals() calls)
            tree = ast.parse(Path(path).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"locals", "globals", "vars"}:
                    hits.append(f"{Path(path).name}:{node.lineno}")
        self.assertEqual(hits, [])

    def test_game_py_keeps_exactly_three_globals_calls(self):
        import ast

        tree = ast.parse(Path(engine_source_files()[0]).read_text(encoding="utf-8"))
        names = sorted(n.func.id for n in ast.walk(tree)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"locals", "globals", "vars"})
        self.assertEqual(names, ["globals"] * 3)


if __name__ == "__main__":
    unittest.main()
