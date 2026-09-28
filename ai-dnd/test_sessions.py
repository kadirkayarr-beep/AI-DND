"""Offline contracts for independent adventures and the legacy default adapter."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random
import json
import tempfile
import threading
import subprocess
import sys
import unittest
from unittest.mock import patch

import game


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.a = game.create_session(seed=17)
        self.b = game.create_session(seed=17)
        self.default_before = game.serialize_game_state()

    def tearDown(self):
        self.assertEqual(game.serialize_game_state(), self.default_before)

    def npc(self, session):
        session.world_state["location"] = "tavern"
        npc = {
            "id": "npc_001", "name": "Gromm", "role": "Barmen",
            "location": "tavern", "personality": "", "appearance": "",
            "relationship": "neutral", "knowledge": [], "memory": [],
            "backstory": "", "max_hp": 100, "current_hp": 100,
            "armor_class": 10, "combat_status": "active",
        }
        session.world_state["npcs"].append(npc)
        return npc

    def test_inventory_memory_and_narration_are_independent(self):
        npc_a, npc_b = self.npc(self.a), self.npc(self.b)
        before_b = self.b.serialize_game_state()
        game.update_inventory_from_player("Kılıcı yere bırak", session=self.a)
        self.assertNotIn("Kılıç", self.a.world_state["inventory"])
        game.record_npc_interaction(npc_a, "Burada çalışıyorum.", "Merhaba",
                                    npc_a, session=self.a)
        self.assertTrue(npc_a["memory"])
        self.assertEqual(npc_b["memory"], [])
        game.finalize_narration("Rüzgar esiyor.", "Bekle", None,
                                {"action": "wait"}, session=self.a)
        self.assertTrue(self.a.recent_dm_narrations)
        self.a.messages.append({"role": "user", "content": "A only"})
        self.assertEqual(len(self.b.messages), 1)
        self.assertEqual(self.b.serialize_game_state(), before_b)

    def test_combat_and_hp_are_independent(self):
        self.npc(self.a)
        self.npc(self.b)
        before_b = self.b.serialize_game_state()
        hp_before = self.a.character["current_hp"]
        with patch.object(game, "roll_d20", return_value=20):
            result = game.execute_intent(
                {"intent": "attack"}, "Gromm'a saldır", session=self.a)
        self.assertGreater(result["damage"], 0)
        self.assertLess(self.a.character["current_hp"], hp_before)
        self.assertLess(self.a.world_state["npcs"][0]["current_hp"], 100)
        self.assertNotEqual(self.a.world_state["combat"],
                            self.b.world_state["combat"])
        self.assertEqual(self.b.serialize_game_state(), before_b)

    def test_rng_streams_are_independent_and_not_module_random(self):
        control = random.Random(17)
        module_state = random.getstate()
        for _ in range(30):
            game.roll_d20(session=self.a)
            game.roll_stat(session=self.a)
        self.assertEqual([self.b.roll_d20() for _ in range(10)],
                         [control.randint(1, 20) for _ in range(10)])
        self.assertEqual(random.getstate(), module_state)

    def test_turn_uses_owned_messages_and_context(self):
        before_b = self.b.serialize_game_state()
        with patch.object(game, "parse_player_intent",
                          return_value={"intent": "unknown"}), \
             patch.object(game, "ask_dungeon_master", return_value={
                 "narration": "Rüzgar esiyor.", "world_updates": {},
                 "valid_response": True}) as narrator:
            self.a.run_player_turn("Bekle")
        self.assertIs(narrator.call_args.args[0], self.a.messages)
        self.assertEqual(self.a.world_state["flags"]["turn_index"], 1)
        self.assertTrue(self.a.recent_dm_narrations)
        self.assertEqual(self.b.serialize_game_state(), before_b)

    def test_save_load_preserves_ownership_and_references(self):
        self.npc(self.a)
        self.a.character["current_hp"] = 3
        self.a.recent_dm_narrations.append("Önceki anlatı")
        expected = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        world = self.a.world_state
        history = self.a.recent_dm_narrations
        character = self.a.character
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            self.a.save_game(path)
            self.a.character["current_hp"] = 0
            self.a.world_state["inventory"].clear()
            self.a.recent_dm_narrations.clear()
            self.assertEqual(self.a.load_game(path), expected)
        self.assertIs(world, self.a.world_state)
        self.assertIs(history, self.a.recent_dm_narrations)
        self.assertIs(character, self.a.character)
        self.assertEqual(expected["version"], 1)
        self.assertEqual(self.b.serialize_game_state(), before_b)

    def test_nested_session_and_exception_restore_context(self):
        enemy = self.npc(self.a)
        def nested_roll():
            self.b.character["current_hp"] = 7
            game.known_character_answer("HP", session=self.b)
            raise RuntimeError("dice failed")
        with patch.object(game, "roll_d20", side_effect=nested_roll):
            with self.assertRaisesRegex(RuntimeError, "dice failed"):
                game.resolve_enemy_attack(enemy, session=self.a)
        self.assertEqual(self.b.character["current_hp"], 7)
        self.assertEqual(self.a.character["current_hp"],
                         self.a.character["max_hp"])
        self.assertEqual(game.serialize_game_state(), self.default_before)

    def test_overlapping_calls_do_not_swap_global_state(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.a.character["armor_class"] = 100
        self.b.character["armor_class"] = 0
        self.a.character["current_hp"] = 11
        self.b.character["current_hp"] = 12
        barrier = threading.Barrier(2)
        def simultaneous_roll():
            barrier.wait(timeout=5)
            return 15
        with patch.object(game, "roll_d20", side_effect=simultaneous_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(game.resolve_enemy_attack, npc,
                                       session=session)
                           for npc, session in zip(enemies, (self.a, self.b))]
                results = [future.result(timeout=10) for future in futures]
        self.assertFalse(results[0]["success"])
        self.assertTrue(results[1]["success"])
        self.assertEqual(self.a.character["current_hp"], 11)
        self.assertLess(self.b.character["current_hp"], 12)


class CompatibilityTests(unittest.TestCase):
    def test_module_aliases_remain_live_without_scalar_mirrors(self):
        before = game.serialize_game_state()
        world = game.world_state
        try:
            game.current_hp = 3
            game.character_name = "AliasHero"
            self.assertEqual(game.serialize_game_state()["player"]["current_hp"], 3)
            self.assertEqual(game.character_name, "AliasHero")
            game._DEFAULT_SESSION.character["current_hp"] = 4
            self.assertEqual(game.current_hp, 4)
            self.assertNotIn("current_hp", vars(game))
            game.initialize_game(creation_choice="2", print_fn=lambda *a: None)
            self.assertEqual(game.current_hp, game.max_hp)
            self.assertIs(game.world_state, world)
        finally:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "default.json"
                path.write_text(json.dumps(before), encoding="utf-8")
                game.load_game(path)

    def test_exec_namespace_scalars_are_not_a_state_input(self):
        namespace = {"__name__": "isolated_engine", "__file__": game.__file__}
        exec(compile(Path(game.__file__).read_text(), game.__file__, "exec"),
             namespace)
        before = namespace["serialize_game_state"]()
        namespace["current_hp"] = 0
        namespace["character_name"] = "Unowned character"
        session = namespace["create_session"](seed=17)
        session.character["current_hp"] = 2
        self.assertEqual(session.serialize_game_state()["player"]["current_hp"], 2)
        self.assertEqual(namespace["serialize_game_state"](), before)
        self.assertEqual(namespace["serialize_game_state"](session=session),
                         session.serialize_game_state())

    def test_terminal_initialization_dice_and_exit(self):
        result = subprocess.run(
            [sys.executable, game.__file__], input="2\nzar at\nexit\n",
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D20 sonucu:", result.stdout)
        self.assertIn("Oyun kapatılıyor...", result.stdout)


if __name__ == "__main__":
    unittest.main()