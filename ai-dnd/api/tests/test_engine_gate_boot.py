"""gate_boot: tokens in the guarded run root's name reach the test child before any test module loads (game.py split, Plan 2 Task 1)."""
import ast
import contextlib
import io
import os
import unittest
from pathlib import Path

import front_proposal
from api.tests import gate_boot

GATE_BOOT_FILE = Path(__file__).with_name("gate_boot.py")
SLOT_GATE = Path(__file__).resolve().parents[2] / "scripts" / "engine_split" / "slot_gate.sh"


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

    # Stage A review finding 7. The guarded child may not start a process (B06), so the label rule lives here and
    # slot_gate.sh runs this module's command line before it stages or syncs anything.
    def label_main(self, label: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gate_boot.main(["--label", label])
        return code, out.getvalue(), err.getvalue()

    def test_a_label_names_the_tokens_boot_will_apply(self):
        for label in ("p2g0", "p2g0-fon-a", "p2g0-n7-n4-fon", "p2g0-n4", "fon"):
            with self.subTest(label=label):
                applied = [t for t in ("fon", "n4", "n7") if t in gate_boot.tokens(f"/x/20261118T000000-{label}-0")]
                self.assertEqual(gate_boot.label_tokens(label), applied)
                self.assertEqual(self.label_main(label), (0, f"TOKENS {' '.join(applied) or 'none'}\n", ""))

    def test_a_token_word_that_is_not_a_dash_token_is_refused(self):
        for label in ("p2g0fon-a", "fon_a", "p2g0-fonx", "x-n4b", "n7-x7n7", "p2g0-fon-xn4"):
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    gate_boot.label_tokens(label)
                code, out, err = self.label_main(label)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err.startswith(f"BAD_LABEL {label}: "), err)

    def test_slot_gate_checks_the_label_before_it_stages_or_syncs(self):
        text = SLOT_GATE.read_text(encoding="utf-8")
        check = text.index('-m api.tests.gate_boot --label "$label"')
        self.assertLess(check, text.index("git add"))
        self.assertLess(check, text.index("slot_sync.sh\""))

    def test_boot_never_imports_the_engine(self):
        tree = ast.parse(GATE_BOOT_FILE.read_text(encoding="utf-8"))
        found = [(node.lineno, name) for node in ast.walk(tree) if (name := _engine_import(node))]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
