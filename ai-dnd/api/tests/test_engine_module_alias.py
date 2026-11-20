"""The 22 character aliases (game.max_hp, game.character_name, ...) on the engine module (game.py split Plan 4, Task 1).

The module keeps its `_GameModule` class and its aliases mirror the default session's character; a plain engine read
through the module runs no Python code (Ruling A: the per-read `__getattribute__` hook costs every `game.X` read a
Python call).
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game  # noqa: E402
from api.tests.town_seed import fixed_town  # noqa: E402


class EngineModuleAliasTests(unittest.TestCase):
    def test_reading_an_engine_name_through_the_module_runs_no_python_code(self):
        with fixed_town(self, 20261301):
            calls = []

            def profiler(frame, event, arg):
                if event == "call":
                    calls.append(frame.f_code.co_qualname)

            sys.setprofile(profiler)
            try:
                for _ in range(100):
                    game.roll_d20
                for _ in range(100):
                    game._session
                for _ in range(100):
                    game.world_state
            finally:
                sys.setprofile(None)
            self.assertEqual(calls, [])
            self.assertNotIn("__getattribute__", type(game).__dict__)
            self.assertNotIn("__setattr__", type(game).__dict__)

    def test_every_character_alias_reads_and_writes_the_default_character(self):
        with fixed_town(self, 20261302):
            character = game._DEFAULT_SESSION.character
            saved = dict(character)
            try:
                self.assertEqual(len(game._CHARACTER_GLOBALS), 22)
                for name, key in game._CHARACTER_GLOBALS.items():
                    self.assertIs(getattr(game, name), character[key], name)
                    sentinel = object()
                    setattr(game, name, sentinel)
                    self.assertIs(character[key], sentinel, name)
                    self.assertIs(getattr(game, name), sentinel, name)
                    self.assertNotIn(name, vars(game), name)
            finally:
                for key in game._CHARACTER_GLOBALS.values():
                    character[key] = saved[key]
            self.assertIs(game._DEFAULT_SESSION.character, character)

    def test_the_aliases_stay_on_the_default_session_inside_another_session(self):
        with fixed_town(self, 20261303):
            default = game._DEFAULT_SESSION.character
            saved_hp = default["current_hp"]
            other = game.create_session(seed=13)
            other.character["name"] = "Baska"
            other_hp = other.character["current_hp"]
            token = game._ACTIVE_SESSION.set(other)
            try:
                self.assertIs(game._session(), other)
                self.assertEqual(game.character_name, default["name"])
                self.assertNotEqual(game.character_name, "Baska")
                game.current_hp = 7
                self.assertEqual(default["current_hp"], 7)
                self.assertEqual(other.character["current_hp"], other_hp)
            finally:
                game._ACTIVE_SESSION.reset(token)
                default["current_hp"] = saved_hp

    def test_the_alias_shapes_tests_use_are_unchanged(self):
        # Pinned from today's behaviour (Plan 4 Task 1 Step 1), not from what would be nicer: patch.object sets the
        # alias through the default character, its __exit__ raises AttributeError (the alias is not in the module
        # __dict__, so the delete fails) and the patched value stays; hasattr is True; dir and vars do not list it.
        with fixed_town(self, 20261304):
            character = game._DEFAULT_SESSION.character
            for name in ("character_name", "current_hp"):
                key = game._CHARACTER_GLOBALS[name]
                original = character[key]
                try:
                    self.assertNotIn(name, vars(game), name)
                    sentinel = object()
                    patcher = mock.patch.object(game, name, sentinel)
                    patcher.__enter__()
                    self.assertIs(getattr(game, name), sentinel, name)
                    self.assertIs(character[key], sentinel, name)
                    raised = None
                    try:
                        patcher.__exit__(None, None, None)
                    except Exception as exc:  # noqa: BLE001 - the pin is the exception class
                        raised = type(exc)
                    self.assertIs(raised, AttributeError, name)
                    self.assertIs(getattr(game, name), sentinel, name)
                    self.assertNotIn(name, vars(game), name)
                    character[key] = original
                    self.assertTrue(hasattr(game, name), name)
                    self.assertNotIn(name, dir(game), name)
                    setattr(game, name, original)
                    self.assertNotIn(name, vars(game), name)
                    self.assertIs(character[key], original, name)
                finally:
                    character[key] = original


if __name__ == "__main__":
    unittest.main()
