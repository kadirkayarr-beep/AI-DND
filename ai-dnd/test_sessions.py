"""Offline contracts for independent adventures and the legacy default adapter."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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

    @contextmanager
    def rolls(self, session, *expected, barrier=None, damage_barrier=None):
        """Require every scripted die to be consumed by its owning adventure."""
        remaining = iter(expected)

        def randint(low, high):
            roll = next(remaining, None)
            self.assertIsNotNone(roll, f"Unexpected d{high} roll")
            sides, value = roll
            self.assertEqual((low, high), (1, sides))
            self.assertTrue(low <= value <= high)
            self.assertIs(game._session(), session)
            if barrier is not None and sides == 20:
                barrier.wait(timeout=5)
            if damage_barrier is not None and sides != 20:
                damage_barrier.wait(timeout=5)
            self.assertIs(game._session(), session)
            return value

        with patch.object(session.rng, "randint", side_effect=randint):
            yield
            self.assertIsNone(next(remaining, None), "Unused scripted dice")

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
        rng_b = self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        hp_before = self.a.character["current_hp"]
        with self.rolls(self.a, (20, 20), (20, 20), (20, 20),
                        (8, 4), (8, 5), (20, 20), (6, 2), (6, 3)), \
             self.rolls(self.b), self.rolls(game._DEFAULT_SESSION):
            result = game.execute_intent(
                {"intent": "attack"}, "Gromm'a saldır", session=self.a)
        self.assertGreater(result["damage"], 0)
        self.assertLess(self.a.character["current_hp"], hp_before)
        self.assertLess(self.a.world_state["npcs"][0]["current_hp"], 100)
        self.assertNotEqual(self.a.world_state["combat"],
                            self.b.world_state["combat"])
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

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
        rng_b = self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()

        def nested_roll(low, high):
            self.assertEqual((low, high), (1, 20))
            self.assertIs(game._session(), self.a)
            self.b.character["current_hp"] = 7
            game.known_character_answer("HP", session=self.b)
            self.assertIs(game._session(), self.a)
            raise RuntimeError("dice failed")

        with patch.object(self.a.rng, "randint", side_effect=nested_roll) as dice, \
             self.rolls(self.b), self.rolls(game._DEFAULT_SESSION):
            # Exercise both a default caller and a different active adventure.
            for caller in (game._DEFAULT_SESSION, self.b):
                with self.subTest(caller=caller):
                    token = game._ACTIVE_SESSION.set(caller)
                    try:
                        with self.assertRaisesRegex(RuntimeError, "dice failed"):
                            game.resolve_enemy_attack(enemy, session=self.a)
                        self.assertIs(game._session(), caller)
                        self.assertEqual(game.serialize_game_state(),
                                         caller.serialize_game_state())
                    finally:
                        game._ACTIVE_SESSION.reset(token)
            self.assertEqual(dice.call_args_list, [unittest.mock.call(1, 20)] * 2)
        self.assertIs(game._session(), game._DEFAULT_SESSION)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
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
        enemies[1].update(damage_die=6, damage_dice=1, damage_modifier=1)
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        barrier = threading.Barrier(2)
        with self.rolls(self.a, (20, 7), barrier=barrier), \
             self.rolls(self.b, (20, 15), (6, 4), barrier=barrier), \
             self.rolls(game._DEFAULT_SESSION):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(game.resolve_enemy_attack, npc,
                                       session=session)
                           for npc, session in zip(enemies, (self.a, self.b))]
                results = [future.result(timeout=10) for future in futures]
        self.assertFalse(results[0]["success"])
        self.assertTrue(results[1]["success"])
        self.assertEqual([result["attack_roll"] for result in results], [7, 15])
        self.assertEqual([result["damage"] for result in results], [0, 5])
        self.assertEqual([result["target_ac"] for result in results], [100, 0])
        self.assertEqual([result["target_hp_before"] for result in results],
                         [11, 12])
        self.assertEqual(self.a.character["current_hp"], 11)
        self.assertEqual(self.b.character["current_hp"], 7)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)


    def test_overlapping_hits_keep_damage_dice_in_their_own_sessions(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.a.character.update(armor_class=10, current_hp=19)
        self.b.character.update(armor_class=12, current_hp=23)
        enemies[0].update(attack_bonus=0, damage_die=6,
                          damage_dice=1, damage_modifier=2)
        enemies[1].update(attack_bonus=0, damage_die=8,
                          damage_dice=2, damage_modifier=1)
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        attack_barrier = threading.Barrier(2)
        damage_barrier = threading.Barrier(2)
        # Both attacks roll two damage dice: A doubles its die on a critical,
        # while B has two base dice. Rendezvous on each damage die as well as
        # the attack, so ownership is checked after the attack-roll boundary.
        with self.rolls(self.a, (20, 20), (6, 3), (6, 5),
                        barrier=attack_barrier, damage_barrier=damage_barrier), \
             self.rolls(self.b, (20, 15), (8, 7), (8, 4),
                        barrier=attack_barrier, damage_barrier=damage_barrier), \
             self.rolls(game._DEFAULT_SESSION):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(game.resolve_enemy_attack, npc,
                                       session=session)
                           for npc, session in zip(enemies, (self.a, self.b))]
                results = [future.result(timeout=10) for future in futures]
        self.assertEqual([result["success"] for result in results], [True, True])
        self.assertEqual([result["critical"] for result in results], [True, False])
        self.assertEqual([result["outcome"] for result in results],
                         ["critical_hit", "hit"])
        self.assertEqual([result["attack_roll"] for result in results], [20, 15])
        self.assertEqual([result["target_ac"] for result in results], [10, 12])
        self.assertEqual([result["damage"] for result in results], [10, 12])
        self.assertEqual([result["target_hp_before"] for result in results],
                         [19, 23])
        self.assertEqual([result["target_hp_after"] for result in results], [9, 11])
        self.assertEqual(self.a.character["current_hp"], 9)
        self.assertEqual(self.b.character["current_hp"], 11)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)


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