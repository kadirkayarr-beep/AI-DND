"""gate_boot: tokens in the guarded run root's name reach the test child before any test module loads (game.py split, Plan 2 Task 1)."""
import ast
import os
import unittest
from pathlib import Path

import front_proposal
from api.tests import gate_boot

GATE_BOOT_FILE = Path(__file__).with_name("gate_boot.py")


def _engine_import(node):
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        names = [node.module or ""]
    else:
        return None
    return next((n for n in names if n.split(".")[0] in ("game", "game_parts")), None)


class GateBoot(unittest.TestCase):
    def test_tokens_come_from_the_run_root_name(self):
        self.assertEqual(gate_boot.tokens("/x/20261118T061934-p2g0-fon-n4-0"), {"p2g0", "fon", "n4", "0"})
        self.assertEqual(gate_boot.tokens(""), set())

    def test_no_token_changes_nothing(self):
        env = {}
        self.assertEqual(gate_boot.boot("/x/20261118T061934-p2g0off-0", env), set())
        self.assertEqual(env, {})

    def test_fon_sets_the_flag(self):
        env = {}
        self.assertEqual(gate_boot.boot("/x/20261118T061934-p2g0-fon-0", env), {"fon"})
        self.assertEqual(env, {"AI_DND_FRONT_PROPOSAL": "1"})

    def test_the_fon_token_turns_the_flag_on_inside_the_child(self):      # Review Focus 1
        if "fon" not in gate_boot.tokens(os.environ.get("AI_DND_GUARD_RUN_ROOT", "")):
            self.skipTest("no fon token")       # proof: outcome ok in fon ledgers, skip in off ledgers (Task 8 Step 5 a)
        self.assertTrue(front_proposal.enabled())

    def test_boot_never_imports_the_engine(self):
        tree = ast.parse(GATE_BOOT_FILE.read_text(encoding="utf-8"))
        found = [(node.lineno, name) for node in ast.walk(tree) if (name := _engine_import(node))]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
