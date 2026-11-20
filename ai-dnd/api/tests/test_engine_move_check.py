"""Tests for the move equivalence check (scripts/engine_split/move_check.py)."""
from __future__ import annotations

import ast
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_split.move_block import move  # noqa: E402
from engine_split.move_check import check_move, comment_counts  # noqa: E402

BASE = "K = 1\n\n# why roll exists (D-123)\ndef roll():\n    return helper() + K  # keep\n\ndef helper():\n    return 2\n"
GOOD_GAME = "K = 1\n\nfrom game_parts.dice import roll\n\ndef helper():\n    return 2\n"
GOOD_PART = "import game\n\n# why roll exists (D-123)\ndef roll():\n    return game.helper() + game.K  # keep\n"
MOVED = {"roll": "dice.py"}
DICE = ('import random\n\ndef roll_d20():\n    """One d20."""\n    return random.randint(1, 20)\n\n'
        'def roll_d6():\n    return random.randint(1, 6)\n')
NO_LOCK = {"functions": {}}


class MoveCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name) / "base"
        self.new = Path(self._tmp.name) / "new"

    def build(self, base=BASE, game=GOOD_GAME, part=GOOD_PART, newline=None):
        for root, files in ((self.base, {"game.py": base}), (self.new, {"game.py": game, "game_parts/dice.py": part})):
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode("utf-8") if newline is None or root is self.base
                                 else text.replace("\n", newline).encode("utf-8"))

    def check(self, tier="normal", sensitive=NO_LOCK, manual=()):
        return check_move(self.base, self.new, MOVED, sensitive, tier, list(manual))

    def test_a_clean_move_is_equivalent(self):
        self.build()
        result = self.check()
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["comments_base"], result["comments_now"])

    def test_a_changed_operator_is_reported(self):
        self.build(part=GOOD_PART.replace("+", "-"))
        self.assertTrue(self.check()["changed"])

    def test_a_deleted_comment_is_reported(self):
        self.build(part=GOOD_PART.replace("  # keep", ""))
        result = self.check()
        self.assertTrue(result["changed"])
        self.assertEqual(result["comments_now"], result["comments_base"] - 1)

    def test_a_dropped_leading_comment_is_reported(self):
        self.build(part=GOOD_PART.replace("# why roll exists (D-123)\n", ""))
        self.assertTrue(self.check()["changed"])

    def test_ast_unparse_output_is_reported(self):
        body = ast.unparse(ast.parse("def roll():\n    return game.helper() + game.K"))
        self.build(part="import game\n\n" + body + "\n")
        self.assertTrue(self.check()["changed"])

    def test_an_extra_edit_in_game_py_is_reported(self):
        self.build(game=GOOD_GAME.replace("return 2", "return 3"))
        self.assertTrue(self.check()["changed"])

    def test_a_deleted_unmoved_line_in_game_py_is_reported(self):
        self.build(game=GOOD_GAME.replace("def helper():\n    return 2\n", ""))
        self.assertTrue(self.check()["changed"])

    def test_a_sensitive_name_needs_the_strong_tier(self):
        self.build()
        lock = {"functions": {"roll": ["money"]}}
        self.assertTrue(self.check(tier="normal", sensitive=lock)["changed"])
        self.assertEqual(self.check(tier="strong", sensitive=lock)["changed"], [])

    def test_crlf_and_lf_give_the_same_verdict(self):
        self.build(base=BASE.replace("\n", "\r\n"), game=GOOD_GAME.replace("\n", "\r\n"), part=GOOD_PART.replace("\n", "\r\n"))
        self.assertEqual(self.check()["changed"], [])

    def test_an_lf_base_against_a_crlf_working_copy_is_equivalent(self):  # F15: git archive gives LF
        self.build(newline="\r\n")
        self.assertEqual(self.check()["changed"], [])

    def test_a_statement_after_the_import_on_one_line_is_reported(self):  # review 1
        self.build(game=GOOD_GAME.replace("import roll", "import roll; K = 2"))
        self.assertTrue(self.check()["changed"])

    def test_an_import_of_a_name_that_was_not_moved_is_reported(self):  # review 1
        self.build(game=GOOD_GAME.replace("import roll", "import roll, helper"))
        self.assertTrue(self.check()["changed"])

    def test_extra_statements_on_a_part_import_line_are_reported(self):  # review 2
        self.build(part=GOOD_PART.replace("import game\n", "import game; import os; os.x = 1\n"))
        self.assertTrue(self.check()["changed"])

    def test_a_parenthesised_part_import_is_allowed(self):  # review 2
        header = "import game\nfrom os import (\n    path,\n    sep,\n)\n"
        self.build(part=GOOD_PART.replace("import game\n", header))
        self.assertEqual(self.check()["changed"], [])

    def test_a_copy_that_leaves_the_block_in_game_py_is_reported(self):  # review 3 (no comments, so the count cannot catch it)
        base = BASE.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        part = GOOD_PART.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        self.build(base=base, game=base.replace("def helper", "from game_parts.dice import roll\n\ndef helper"), part=part)
        self.assertTrue(self.check()["changed"])

    def test_a_body_only_deletion_in_game_py_is_reported(self):  # review 3 (no comments)
        base = BASE.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        part = GOOD_PART.replace("# why roll exists (D-123)\n", "").replace("  # keep", "")
        game = "K = 1\n\nfrom game_parts.dice import roll\n\ndef roll():\n\ndef helper():\n    return 2\n"
        self.build(base=base, game=game, part=part)
        self.assertTrue(self.check()["changed"])

    def test_a_manual_line_in_game_py_is_exempt_and_echoed(self):
        self.build(game=GOOD_GAME.replace("K = 1", "K = 2"))
        self.assertTrue(self.check()["changed"])
        manual = ["game.py:base:1:test", "game.py:new:1:test"]  # T2.4 prep: one edited line, seen from both sides
        result = self.check(manual=manual)
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["manual"], manual)

    def test_a_game_py_manual_line_exempts_only_its_own_side(self):  # T2.4 prep
        self.build(game=GOOD_GAME.replace("K = 1", "K = 2"))  # base line 1 deleted, new line 1 inserted
        base_only = self.check(manual=["game.py:base:1:test"])["changed"]
        self.assertEqual(len(base_only), 1)
        self.assertIn("game.py:1:", base_only[0])
        new_only = self.check(manual=["game.py:new:1:test"])["changed"]
        self.assertEqual(len(new_only), 1)
        self.assertIn("base line 1 deleted", new_only[0])

    def test_a_game_py_manual_line_without_a_side_is_refused(self):  # T2.4 prep
        self.build(game=GOOD_GAME.replace("K = 1", "K = 2"))
        for item in ("game.py:1:test", "game.py:both:1:test", "game.py:base:x:test"):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.check(manual=[item])

    def test_a_hand_written_part_line_is_reported_unless_manual(self):  # F16
        part = GOOD_PART.replace("import game\n", "import game\nEXTRA = 1\n")
        self.build(part=part)
        self.assertTrue(self.check()["changed"])
        # T2.4 prep: a part is named by its path under the ai-dnd root
        self.assertEqual(self.check(manual=["game_parts/dice.py:2:header constant"])["changed"], [])

    def test_a_manual_line_naming_a_file_outside_the_check_is_refused(self):  # T2.4 prep
        self.build(part=GOOD_PART.replace("import game\n", "import game\nEXTRA = 1\n"))
        for item in ("dice.py:2:bare name", "game_parts/other.py:2:not moved here", "other.py:1:x"):
            with self.subTest(item=item):
                with self.assertRaises(ValueError) as caught:
                    self.check(manual=[item])
                self.assertIn(item.rsplit(":", 2)[0], str(caught.exception))

    def test_the_command_line_fails_on_a_manual_line_outside_the_check(self):  # T2.4 prep
        import contextlib
        import io
        from engine_split.move_check import main
        self.build()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = main(["--base-root", str(self.base), "--root", str(self.new), "--moved", "roll=dice.py",
                         "--manual", "other.py:1:x"])
        self.assertNotEqual(code, 0)
        self.assertIn("other.py", err.getvalue())

    def test_a_part_header_of_import_lines_is_allowed(self):  # F16
        self.build(part=GOOD_PART.replace("import game\n", "import re\nimport game\nfrom pathlib import Path\n"))
        self.assertEqual(self.check()["changed"], [])

    def test_a_missing_part_or_block_is_reported(self):
        self.build()
        self.assertTrue(check_move(self.base, self.new, {"nope": "dice.py"}, NO_LOCK, "normal")["changed"])
        self.assertTrue(check_move(self.base, self.new, {"roll": "gone.py"}, NO_LOCK, "normal")["changed"])

    def test_comment_counts_cover_game_py_and_every_part(self):
        self.build(base="# a\n# b\nX = 1\n", game="# a\nX = 1\n", part="# b\n")
        self.assertEqual(comment_counts(self.base, self.new), (2, 2))

    def test_round_trip_move_output_is_equivalent(self):  # Task 6 Step 4: move() then check_move()
        self.build(game=BASE, part="import game\n")
        move(self.new / "game.py", self.new / "game_parts" / "dice.py", ["roll"], set())
        self.assertEqual(self.check()["changed"], [])

    def test_round_trip_of_a_multi_name_move_is_equivalent(self):  # deferred by the Task 5 review
        self.build(game=BASE, part="import game\n")
        move(self.new / "game.py", self.new / "game_parts" / "dice.py", ["roll", "helper"], set())
        moved = {"roll": "dice.py", "helper": "dice.py"}
        self.assertEqual(check_move(self.base, self.new, moved, NO_LOCK, "normal")["changed"], [])

    def test_round_trip_of_a_decorated_function_is_equivalent(self):  # deferred by the Task 5 review
        base = "import functools\n\n# cache it\n@functools.lru_cache(maxsize=None)\ndef roll():\n    return K\n\nK = 1\n"
        self.build(base=base, game=base, part="import game\n")
        move(self.new / "game.py", self.new / "game_parts" / "dice.py", ["roll"], set())
        self.assertEqual(self.check()["changed"], [])

    def second_move(self, edit=None, source=DICE):
        """Base = game.py after moving roll_d20 into dice.py; new = base plus a second move of roll_d6 into it."""
        self.base.mkdir()
        (self.base / "game.py").write_text(source, encoding="utf-8")
        (self.base / "game_parts").mkdir()
        (self.base / "game_parts" / "dice.py").write_text("import random\n", encoding="utf-8")
        move(self.base / "game.py", self.base / "game_parts" / "dice.py", ["roll_d20"], set())
        shutil.copytree(self.base, self.new)
        move(self.new / "game.py", self.new / "game_parts" / "dice.py", ["roll_d6"], set())
        part = self.new / "game_parts" / "dice.py"
        if edit:
            part.write_text(edit(part.read_text(encoding="utf-8")), encoding="utf-8")
        return check_move(self.base, self.new, {"roll_d6": "dice.py"}, NO_LOCK, "normal")["changed"]

    def test_a_second_move_into_the_same_part_is_equivalent(self):
        self.assertEqual(self.second_move(), [])

    def test_a_deleted_line_in_an_earlier_moved_block_is_reported(self):  # gate TM0 review
        self.assertTrue(self.second_move(lambda t: t.replace("    return random.randint(1, 20)\n", "", 1)))

    def test_swapped_lines_in_an_earlier_moved_block_are_reported(self):  # gate TM0 review
        swap = lambda t: t.replace('    """One d20."""\n    return random.randint(1, 20)\n',
                                   '    return random.randint(1, 20)\n    """One d20."""\n', 1)
        self.assertTrue(self.second_move(swap))

    def test_a_tail_delete_in_an_earlier_block_is_reported_when_the_new_block_has_the_same_line(self):  # T2.4 prep
        twin = DICE.replace("random.randint(1, 6)", "random.randint(1, 20)")
        self.assertTrue(self.second_move(lambda t: t.replace("    return random.randint(1, 20)\n", "", 1), twin))

    def test_a_held_block_before_a_moved_block_with_the_same_last_line_is_no_change(self):  # D-376
        base = 'K = 1\n\nHELD = {\n    "a": 1,\n}\nMOVED = {\n    "a": 1,\n    "b": 2,\n}\n\ndef helper():\n    return 2\n'
        game = 'K = 1\n\nfrom game_parts.dice import MOVED\nHELD = {\n    "a": 1,\n}\n\ndef helper():\n    return 2\n'
        part = 'import game\n\nMOVED = {\n    "a": 1,\n    "b": 2,\n}\n'
        self.build(base=base, game=game, part=part)
        self.assertEqual(check_move(self.base, self.new, {"MOVED": "dice.py"}, NO_LOCK, "normal")["changed"], [])

    def test_an_old_batch_checked_against_an_older_root_says_wrong_root(self):  # D-376: base has a and b; batch moved a; b moved later
        base = "K = 1\n_PART_MODULES = ()\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n"
        self.build(base=base, game="K = 1\n_PART_MODULES = ('game_parts.dice',)\n\nfrom game_parts.dice import a, b\n",
                   part="import game\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n")
        code, out, _ = self.main("--moved", "a=dice.py")
        self.assertEqual(code, 2)
        self.assertEqual(out, "WRONG ROOT? 2 base lines belong to 1 names moved by later batches; "
                              "use the parent of this batch's move commit\n")

    def test_a_deleted_line_outside_a_later_moved_name_is_not_wrong_root(self):  # D-376: the warning needs every line covered
        base = "K = 1\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n"
        self.build(base=base, game="from game_parts.dice import a, b\n",
                   part="import game\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n")
        code, out, _ = self.main("--moved", "a=dice.py")
        self.assertEqual(code, 1)
        self.assertNotIn("WRONG ROOT", out)

    def other_part(self, base_text="X = 1\n", new_text="X = 2\n"):
        for root, text in ((self.base, base_text), (self.new, new_text)):
            (root / "game_parts").mkdir(parents=True, exist_ok=True)
            (root / "game_parts" / "other.py").write_text(text, encoding="utf-8")

    def test_a_hand_edit_in_another_part_is_a_finding(self):  # D-360 (1)
        self.build()
        self.other_part()
        self.assertEqual(self.check()["changed"], ["CHANGED other part other.py differs from base"])
        self.other_part(new_text="X = 1\n")
        self.assertEqual(self.check()["changed"], [])
        self.other_part(new_text="X = 2\n")
        self.assertEqual(self.check(manual=["game_parts/other.py:1:owner edit"])["changed"], [])

    def test_a_stale_exemption_in_a_failing_import_group_is_reported(self):  # D-360 (2)
        self.build(game=GOOD_GAME.replace("import roll\n", "import roll\nSTRAY = 1\n"))
        changed = self.check(manual=["game.py:new:3:valid import"])["changed"]
        self.assertEqual(len(changed), 2, changed)
        self.assertIn("STRAY", changed[0])
        self.assertEqual(changed[1], "manual entry exempts nothing: game.py:new:3:valid import")

    def main(self, *argv: str) -> tuple[int, str, str]:
        import contextlib
        import io
        from engine_split.move_check import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(["--base-root", str(self.base), "--root", str(self.new), *argv])
            except SystemExit as exc:  # argparse: an unknown option exits instead of returning
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_a_manual_entry_that_exempts_nothing_is_a_finding(self):  # D-350
        self.build()
        # an unchanged base line, the moved-name import line, and a part header import line (F16 accepts it already)
        stale = ["game.py:base:1:unchanged", "game.py:new:3:moved import", "game_parts/dice.py:1:import header"]
        self.assertEqual(self.check(manual=stale)["changed"], [f"manual entry exempts nothing: {e}" for e in stale])
        self.build(game=GOOD_GAME.replace("K = 1", "K = 2"))
        used = ["game.py:base:1:edited", "game.py:new:1:edited"]
        self.assertEqual(self.check(manual=used + ["game.py:base:6:stale"])["changed"],
                         ["manual entry exempts nothing: game.py:base:6:stale"])

    def test_an_undecodable_file_is_named(self):  # D-350
        for target, argv in ((self.base / "game.py", ("--moved", "roll=dice.py")),
                             (self.new / "game_parts" / "dice.py", ("--moved", "roll=dice.py")),
                             (self.new / "game_parts" / "dice.py", ("--comments-only",))):
            with self.subTest(target=target.name, argv=argv):
                self.build()
                target.write_bytes(b"x = '\xff\xfe'\n")
                code, _, err = self.main(*argv)
                self.assertEqual(code, 2)
                self.assertEqual(err, f"ERROR cannot decode {target}\n")

    def test_a_manual_entry_without_a_reason_is_refused(self):  # D-350
        self.build(game=GOOD_GAME.replace("K = 1", "K = 2"))
        for item in ("game.py:base:1", "game.py:base:1:", "game.py:base:1:  "):
            with self.subTest(item=item):
                code, _, err = self.main("--moved", "roll=dice.py", "--manual", item, "--manual", "game.py:new:1:edited")
                self.assertEqual(code, 2)
                self.assertIn("reason", err)

    def test_a_part_that_does_not_parse_is_a_finding_not_a_traceback(self):  # D-350
        self.build(part=GOOD_PART.replace("def roll():", "def roll(:"))
        try:
            changed = self.check()["changed"]
        except SyntaxError as exc:
            self.fail(f"traceback instead of a finding: {exc!r}")
        self.assertTrue(any("dice.py does not parse" in line for line in changed), changed)

    def test_moved_file_equals_the_long_moved_form(self):  # D-348
        self.build(game=BASE, part="import game\n")
        move(self.new / "game.py", self.new / "game_parts" / "dice.py", ["roll", "helper"], set())
        names = Path(self._tmp.name) / "names.txt"
        names.write_text("roll\nhelper\n", encoding="utf-8")
        long_form = self.main("--moved", "roll=dice.py,helper=dice.py")
        self.assertEqual(long_form, (0, "CHANGED 0 names=2\n", ""))
        self.assertEqual(self.main("--moved-file", str(names), "--part", "dice.py"), long_form)
        (self.new / "game_parts" / "dice.py").write_text("import game\n", encoding="utf-8")  # both forms see a broken move
        broken = self.main("--moved", "roll=dice.py,helper=dice.py")
        self.assertEqual(broken[0], 1)
        self.assertEqual(self.main("--moved-file", str(names), "--part", "dice.py"), broken)

    def test_an_empty_moved_set_is_refused(self):  # stage A review finding 4
        self.build()
        names = Path(self._tmp.name) / "names.txt"
        names.write_text("\n", encoding="utf-8")
        for argv in ((), ("--moved", ""), ("--moved-file", str(names), "--part", "dice.py")):
            with self.subTest(argv=argv):
                code, out, err = self.main(*argv)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("no moved names", err)
        self.assertEqual(self.main("--comments-only"), (0, "COMMENTS base=2 now=2\n", ""))

    def test_a_part_that_is_not_a_bare_file_name_is_refused(self):  # stage A review finding 5
        self.build()
        names = Path(self._tmp.name) / "names.txt"
        names.write_text("roll\n", encoding="utf-8")
        for part in (str(self.new / "game_parts" / "dice.py"), "game_parts/dice.py", "../dice.py", "dice", "di-ce.py"):
            for argv in (("--moved-file", str(names), "--part", part), ("--moved", f"roll={part}")):
                with self.subTest(argv=argv):
                    code, out, err = self.main(*argv)
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn("bare", err)
        self.assertEqual(self.main("--moved-file", str(names), "--part", "dice.py"), (0, "CHANGED 0 names=1\n", ""))


if __name__ == "__main__":
    unittest.main()
