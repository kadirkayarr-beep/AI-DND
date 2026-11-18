"""Tests for the N3 routing audit (scripts/engine_split/routing_audit.py): seven static rules on ai-dnd/game_parts."""
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
from engine_split.routing_audit import audit, character_names, game_imports, part_files  # noqa: E402

LOCKS = Path(__file__).parent / "engine_split_locks"
TARGETS = set(json.loads((LOCKS / "patch_census.json").read_text(encoding="utf-8"))["targets"])
ALLOWED = set(json.loads((LOCKS / "allowed_imports.json").read_text(encoding="utf-8")))
ALLOWLIST = json.loads((LOCKS / "identity_allowlist.json").read_text(encoding="utf-8"))
CHARACTER_NAMES = character_names(ROOT / "game.py")

# The T1 guard is game.py's first statement (Ruling 1); the rest binds the names the fixtures read through game.
GAME_PY = ('if __name__ == "__main__":\n    import game\n    from game_parts import terminal\n'
           '    raise SystemExit(terminal.run(input_fn=input, print_fn=print))\n'
           "import random\nK = 1\ndef roll_d20():\n    return random.randint(1, 20)\ndef _session():\n    return None\n")

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
FINDING = re.compile(r"^R[1-7] \S+:\d+: ")


class RoutingAuditTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def tree(self, part: str | None = None, game: str = GAME_PY, extra: dict[str, str] | None = None) -> Path:
        files = {"game.py": game, "game_parts/__init__.py": "import game\n", **(extra or {})}
        if part is not None:
            files["game_parts/p.py"] = part
        for rel, text in files.items():
            path = self.tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return self.tmp

    def run_audit(self, root: Path, allowlist=None) -> list[str]:
        return audit(root, TARGETS, ALLOWED, ALLOWLIST if allowlist is None else allowlist, CHARACTER_NAMES)

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

    def test_a_moved_surface_function_may_be_defined_in_its_part(self):
        src = "import game\ndef roll_d20():\n    return game._session().rng.randint(1, 20)\n"
        game = GAME_PY.replace("def roll_d20():\n    return random.randint(1, 20)\n", "from game_parts.p import roll_d20\n")
        self.assertEqual(self.run_audit(self.tree(src, game=game)), [])

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

    def test_the_allowed_imports_lock_covers_every_project_module_game_py_imports(self):
        lock = json.loads((LOCKS / "allowed_imports.json").read_text(encoding="utf-8"))
        self.assertEqual(lock, sorted(set(lock)))
        self.assertLessEqual(set(game_imports(ROOT / "game.py")), set(lock))
        self.assertEqual([m for m in lock if m.split(".")[0] in sys.stdlib_module_names or m.split(".")[0] in {"game", "game_parts"}], [])


if __name__ == "__main__":
    unittest.main()
