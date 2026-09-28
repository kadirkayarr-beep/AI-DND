"""Startup resume choices without a live narration service."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=42)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "adventure.json"

    def test_resume_existing_character_without_creation(self):
        self.session.character["name"] = "SavedHero"
        self.session.world_state["location"] = "forest"
        self.session.save_game(self.path)
        self.session.character["name"] = "Temporary"
        self.session.world_state["location"] = "tavern"
        output = []
        with patch.object(game, "initialize_game", side_effect=AssertionError("created new character")):
            self.assertTrue(game.start_terminal_game(
                input_fn=lambda prompt: "2", print_fn=output.append,
                save_path=self.path, session=self.session))
        self.assertEqual(self.session.character["name"], "SavedHero")
        self.assertEqual(self.session.world_state["location"], "forest")
        self.assertTrue(any("yüklendi" in line for line in output))

    def test_missing_save_starts_new_character(self):
        with patch.object(game, "initialize_game", return_value=None) as creator:
            self.assertTrue(game.start_terminal_game(
                input_fn=lambda prompt: "2", print_fn=lambda line: None,
                save_path=self.path, session=self.session))
            creator.assert_called_once()

    def test_unreadable_save_can_be_skipped(self):
        self.path.write_text("{broken", encoding="utf-8")
        before = self.session.serialize_game_state()
        choices = iter(["2", "exit"])
        lines = []
        self.assertFalse(game.start_terminal_game(
            input_fn=lambda prompt: next(choices), print_fn=lines.append,
            save_path=self.path, session=self.session))
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertTrue(any("yüklenemedi" in line for line in lines))


if __name__ == "__main__":
    unittest.main()