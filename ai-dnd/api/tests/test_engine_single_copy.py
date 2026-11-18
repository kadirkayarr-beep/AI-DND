"""The terminal entry must run on the engine that is already imported, not on a second copy (game.py split, T1.1)."""
import ast
import io
import os
import runpy
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game  # noqa: E402
from api.tests.town_seed import fixed_town  # noqa: E402


def _start_answers():
    """A new character ("2"), after the resume prompt when a default save happens to exist."""
    return ["1"] if game.DEFAULT_SAVE_PATH.is_file() else []


class TerminalEntry(unittest.TestCase):
    def _run_main(self, answers, workdir=None):
        """Run game.py as `python game.py` would, in this process; return (exit code, stdout).

        The default session is snapshotted first and restored in `finally`, so the run cannot leak a hero.
        """
        answers = iter(answers)
        out = io.StringIO()
        cwd = os.getcwd()
        snapshot = game._session()._capture_runtime_snapshot()
        try:
            if workdir is not None:
                os.chdir(workdir)
            with fixed_town(self, 20261118), patch("builtins.input", lambda prompt="": next(answers)), \
                    patch("sys.stdout", out):
                with self.assertRaises(SystemExit) as stop:
                    runpy.run_path(str(ROOT / "game.py"), run_name="__main__")
        finally:
            os.chdir(cwd)
            game._session()._restore_runtime_snapshot(snapshot)
        return stop.exception.code, out.getvalue()

    def test_a_terminal_run_uses_the_engine_that_is_already_imported(self):
        answers = _start_answers() + ["2", "/skill stealth 15", "çık"]
        iterator = iter(answers)
        out = io.StringIO()
        snapshot = game._session()._capture_runtime_snapshot()
        try:
            game._session().character["name"] = "NotYetAHero"
            with fixed_town(self, 20261118), patch("builtins.input", lambda prompt="": next(iterator)), \
                    patch("sys.stdout", out):
                with self.assertRaises(SystemExit) as stop:
                    runpy.run_path(str(ROOT / "game.py"), run_name="__main__")
            hero = game._session().character["name"]
        finally:
            game._session()._restore_runtime_snapshot(snapshot)
        self.assertEqual(stop.exception.code, 0)
        self.assertIn("🎲 SKILL CHECK", out.getvalue())
        self.assertIn("Skill: Stealth", out.getvalue())
        self.assertNotEqual(hero, "NotYetAHero")   # red before T1.1: the second copy got the hero

    def test_the_main_guard_is_first_and_always_exits(self):
        def is_main_guard(node):      # `if __name__ == "__main__":` (Eq only; the `!=` block further down is not one)
            t = getattr(node, "test", None)
            return (isinstance(node, ast.If) and isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                    and t.left.id == "__name__" and isinstance(t.ops[0], ast.Eq)
                    and getattr(t.comparators[0], "value", None) == "__main__")
        body = ast.parse((ROOT / "game.py").read_text(encoding="utf-8")).body
        self.assertTrue(is_main_guard(body[0]))
        self.assertIsInstance(body[0].body[-1], ast.Raise)
        self.assertEqual(sum(is_main_guard(n) for n in body), 1)

    def test_the_default_save_path_stays_under_ai_dnd_saves(self):          # green before T1.1; pinned
        self.assertEqual(game.DEFAULT_SAVE_PATH, ROOT / "saves" / "adventure.json")

    def test_terminal_save_and_load_use_the_given_path(self):               # Review Focus 2
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "slot.json"
            code, text = self._run_main(_start_answers() + ["2", f"/save {target}", f"/load {target}", "çık"])
            self.assertTrue(target.is_file())
        self.assertEqual(code, 0)
        self.assertIn("Oyun kaydedildi:", text)
        self.assertIn("Oyun yüklendi:", text)
        self.assertFalse((ROOT / "game_parts" / "saves").exists())

    def test_the_terminal_starts_from_another_working_directory(self):      # Review Focus 1
        with tempfile.TemporaryDirectory() as tmp:
            started = time.perf_counter()
            code, text = self._run_main(_start_answers() + ["2", "zar at", "exit"], workdir=tmp)
            elapsed = time.perf_counter() - started
        self.assertEqual(code, 0)
        self.assertIn("D20 sonucu:", text)
        print(f"TERMINAL_CHILD_SECONDS={elapsed:.2f}")

    def test_closed_stdin_ends_the_terminal_promptly(self):                 # Review Focus 3
        def closed(prompt=""):
            raise EOFError
        snapshot = game._session()._capture_runtime_snapshot()
        try:
            started = time.perf_counter()
            with fixed_town(self, 20261118), patch("builtins.input", closed), patch("sys.stdout", io.StringIO()):
                with self.assertRaises(EOFError):
                    runpy.run_path(str(ROOT / "game.py"), run_name="__main__")
            self.assertLess(time.perf_counter() - started, 60)
        finally:
            game._session()._restore_runtime_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
