"""The player-visible game name is Unwritten; internal ids keep their old spelling."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import game
from api import auth, schemas

REPO_ROOT = Path(__file__).resolve().parents[3]
# Distinct AI_DND_ names in ai-dnd/**/*.py (tests and docs excluded) plus tools/**, counted in Task 3.
# Task 1's ledger value (58) is a row count of a wider scan (READMEs included); this pins the test's own scope.
PROTECTED_ENV_NAME_COUNT = 36


class SaveFileNameTests(unittest.TestCase):
    def test_foreign_save_file_error_names_unwritten(self):
        with self.assertRaises(ValueError) as caught:
            game._validate_save_payload({"format": "other-game", "version": 1})
        self.assertEqual(str(caught.exception), "Bu dosya bir Unwritten kayıt dosyası değil.")

    def test_own_format_id_is_unchanged(self):
        # the save format id is an internal id, not a player-visible name
        with self.assertRaises(ValueError) as caught:
            game._validate_save_payload({"format": "ai-dnd-save", "version": 999})
        self.assertNotIn("Unwritten kayıt dosyası değil", str(caught.exception))


class TerminalBannerTests(unittest.TestCase):
    def test_terminal_banner_says_unwritten(self):
        import inspect

        source = inspect.getsource(game)
        self.assertIn('print_fn("       UNWRITTEN")', source)
        self.assertNotIn('print_fn("       AI DUNGEON MASTER")', source)


class ProtectedIdsTests(unittest.TestCase):
    """Internal ids keep their ai-dnd spelling; a missing file fails (never skips)."""

    def _read(self, relative):
        path = REPO_ROOT / relative
        self.assertTrue(path.is_file(), f"{relative} must exist under {REPO_ROOT}")
        return path.read_text(encoding="utf-8")

    def test_save_format_id_is_ai_dnd_save(self):
        self.assertIn('"format": "ai-dnd-save"', self._read("ai-dnd/game.py"))

    def test_request_marker_and_health_engine(self):
        self.assertEqual(auth.REQUEST_MARKER, "X-AI-DND-Request")
        self.assertEqual(schemas.HealthResponse.model_fields["engine"].default, "AI-DND")

    def test_guard_ids(self):
        for relative in ("tools/acceptance/guarded_runner.py", "tools/acceptance/linux_guard/sitecustomize.py"):
            self.assertIn('GUARD_ID = "ai-dnd-b06-linux-guard-v1"', self._read(relative))

    def test_local_data_folder_name(self):
        for relative in ("ai-dnd/api/model_chain.py", "ai-dnd/front_proposal.py"):
            self.assertIn('/ "AI-DND"', self._read(relative))

    def test_env_variable_name_set_is_unchanged(self):
        names = set()
        for path in list((REPO_ROOT / "ai-dnd").rglob("*.py")) + [p for p in (REPO_ROOT / "tools").rglob("*") if p.is_file()]:
            relative = path.relative_to(REPO_ROOT).as_posix()
            if "/tests/" in relative or relative.startswith("ai-dnd/docs/") or "__pycache__" in relative:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            names.update(re.findall(r"AI_DND_[A-Z0-9_]+", text))
        self.assertEqual(len(names), PROTECTED_ENV_NAME_COUNT, sorted(names))


if __name__ == "__main__":
    unittest.main()
