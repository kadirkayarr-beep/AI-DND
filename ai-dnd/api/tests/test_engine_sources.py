"""engine_source_files(): the engine's source files are game.py plus game_parts/*.py (game.py split, T0.3)."""
import tempfile
import unittest
from pathlib import Path

from api.tests.engine_sources import engine_source_files, engine_source_text


class EngineSourceFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "game.py").write_text("G = 1\n", encoding="utf-8")

    def test_without_a_package_only_game_py_is_listed(self):
        self.assertEqual(engine_source_files(self.root), [self.root / "game.py"])

    def test_parts_follow_game_py_in_name_order(self):
        (self.root / "game_parts").mkdir()
        for name in ("b.py", "a.py"):
            (self.root / "game_parts" / name).write_text(name + "\n", encoding="utf-8")
        (self.root / "game_parts" / "notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(engine_source_files(self.root),
                         [self.root / "game.py", self.root / "game_parts" / "a.py", self.root / "game_parts" / "b.py"])

    def test_the_real_list_starts_with_the_engine_file(self):
        self.assertEqual(engine_source_files()[0].name, "game.py")
        self.assertTrue(engine_source_files()[0].is_file())

    def test_the_text_joins_the_files_with_a_newline(self):
        (self.root / "game_parts").mkdir()
        (self.root / "game_parts" / "a.py").write_text("A = 2", encoding="utf-8")
        self.assertEqual(engine_source_text(self.root), "G = 1\n\nA = 2")


if __name__ == "__main__":
    unittest.main()
