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
        self.session = game.create_session()
        self.session.recent_dm_narrations[:] = ["Türkçe anlatı"]
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "adventure.json"

    def test_round_trip_preserves_references(self):
        expected = self.session.serialize_game_state()
        world = self.session.world_state
        self.session.save_game(self.path)
        self.session.character["current_hp"] = 0
        self.session.world_state["inventory"].clear()
        self.session.recent_dm_narrations.clear()
        self.assertEqual(self.session.load_game(self.path), expected)
        self.assertIs(world, self.session.world_state)

    def test_invalid_payload_does_not_mutate_session(self):
        original = self.session.serialize_game_state()
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
                    self.session.load_game(self.path)
                self.assertEqual(self.session.serialize_game_state(), original)

    def test_unreadable_files_preserve_all_sessions_and_held_references(self):
        other = game.create_session(seed=37)
        for session, name in ((self.session, "Target"), (other, "Other")):
            session.character["name"] = name
            session.world_state["inventory"].append(f"{name} item")
            session.recent_dm_narrations.append(f"{name} narration")
            session.messages.append({"role": "user", "content": name})
        self.session.roll_d20()
        other.roll_stat()

        sessions = (self.session, other, game._DEFAULT_SESSION)
        held = [
            (session.world_state, session.character, session.recent_dm_narrations)
            for session in sessions
        ]
        held_contents = copy.deepcopy(held)
        snapshots = [session.serialize_game_state() for session in sessions]
        rng_states = [session.rng.getstate() for session in sessions]
        messages = [copy.deepcopy(session.messages) for session in sessions]

        for failure, error in (("missing", FileNotFoundError),
                               ("malformed", ValueError)):
            with self.subTest(failure=failure):
                if failure == "malformed":
                    self.path.write_text("{broken", encoding="utf-8")
                with self.assertRaises(error):
                    self.session.load_game(self.path)
                for session, references, contents, snapshot, rng_state, history in zip(
                        sessions, held, held_contents, snapshots, rng_states, messages):
                    with self.subTest(failure=failure, session=session):
                        self.assertIs(session.world_state, references[0])
                        self.assertIs(session.character, references[1])
                        self.assertIs(session.recent_dm_narrations, references[2])
                        self.assertEqual(references, contents)
                        self.assertEqual(session.serialize_game_state(), snapshot)
                        self.assertEqual(session.rng.getstate(), rng_state)
                        self.assertEqual(session.messages, history)

    def test_failed_replace_preserves_existing_save(self):
        self.session.save_game(self.path)
        original = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.session.save_game(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()