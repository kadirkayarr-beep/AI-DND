"""Offline persistence contract, including failure safety."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        game.initialize_game(creation_choice="2", print_fn=lambda *args: None)
        game.world_state.clear()
        game.world_state.update(copy.deepcopy(game.INITIAL_WORLD_STATE))
        game.recent_dm_narrations[:] = ["Türkçe anlatı"]
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "adventure.json"

    def test_round_trip_preserves_references(self):
        expected = game.serialize_game_state()
        world = game.world_state
        game.save_game(self.path)
        game.current_hp = 0
        game.world_state["inventory"].clear()
        game.recent_dm_narrations.clear()
        self.assertEqual(game.load_game(self.path), expected)
        self.assertIs(world, game.world_state)

    def test_invalid_payload_does_not_mutate_session(self):
        original = game.serialize_game_state()
        changes = [
            ("version", 999), ("recent_dm_narrations", None),
            ("player", {**original["player"], "strength": "bad"}),
            ("player", {**original["player"], "current_hp": -1}),
            ("world_state", {**original["world_state"], "flags": []}),
            ("world_state", {**original["world_state"], "npcs": ["bad"]}),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                payload = copy.deepcopy(original)
                payload[key] = value
                self.path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    game.load_game(self.path)
                self.assertEqual(game.serialize_game_state(), original)

    def test_malformed_or_missing_file(self):
        original = game.serialize_game_state()
        with self.assertRaises(FileNotFoundError):
            game.load_game(self.path)
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            game.load_game(self.path)
        self.assertEqual(game.serialize_game_state(), original)

    def test_failed_replace_preserves_existing_save(self):
        game.save_game(self.path)
        original = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                game.save_game(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()