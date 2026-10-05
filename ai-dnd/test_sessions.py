import os
"""Offline contracts for independent adventures and the legacy default adapter."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import copy
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
            "attack_damage_type": "slashing",
        }
        session.world_state["npcs"].append(npc)
        # Explicit fixture geometry lets both player and enemy attacks reach
        # the isolation assertions without bypassing unknown-distance rejection.
        pairs = session.world_state.setdefault(
            "attack_environment", {}
        ).setdefault("pairs", {})
        for actor, target in (("player", npc["id"]), (npc["id"], "player")):
            pairs[f"{actor}|{target}"] = {
                "distance_ft": 5,
                "attacker_sees_target": True,
                "target_sees_attacker": True,
            }
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

    def test_unverified_lore_claim_preserves_unrelated_local_proposals(self):
        self.a.world_state["location"] = "tavern"
        self.a.world_state["locations"]["tavern"] = {"name": "Taverna"}
        before_npcs = copy.deepcopy(self.a.world_state["npcs"])
        before_locations = copy.deepcopy(self.a.world_state["locations"])
        before_features = copy.deepcopy(self.a.world_state["features"])
        before_events = copy.deepcopy(self.a.world_state["events"])
        with patch.object(
            game, "parse_player_intent", return_value={"intent": "unknown"}
        ), patch.object(game, "should_generate_npcs", return_value=True), patch.object(
            game,
            "ask_dungeon_master",
            return_value={
                "narration": "King Vharion rules Neverwinter.",
                "world_updates": {
                    "create_npcs": [{
                        "name": "Elara",
                        "role": "merchant",
                        "location": "tavern",
                    }],
                    "events": ["Lamba alevi titrer."],
                },
                "lore_claims": [],
                "valid_response": True,
            },
        ):
            result = self.a.run_player_turn("Rüzgar esiyor.")

        self.assertIn("güvenilir bir doğrulamam yok", result["narration"])
        self.assertNotIn("UNVERIFIED", result["narration"])
        self.assertNotIn("King Vharion", result["narration"])
        self.assertEqual(len(self.a.world_state["npcs"]), len(before_npcs) + 1)
        elara = self.a.world_state["npcs"][-1]
        self.assertEqual(elara["name"], "Elara")
        self.assertEqual(elara["location"], "tavern")
        self.assertEqual(elara["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertEqual(self.a.world_state["locations"], before_locations)
        self.assertEqual(self.a.world_state["features"], before_features)
        self.assertEqual(len(self.a.world_state["events"]), len(before_events) + 1)
        self.assertEqual(
            self.a.world_state["events"][-1]["reality_layer"],
            "NARRATIVE_TEXTURE",
        )

    def test_unregistered_lore_question_returns_explicit_unverified_without_model_answer(self):
        before = copy.deepcopy(self.a.world_state)
        with patch.object(
            game,
            "parse_player_intent",
            side_effect=AssertionError("Unsupported lore questions must be caught before intent parsing."),
        ), patch.object(
            game,
            "ask_dungeon_master",
            side_effect=AssertionError("Unsupported lore question must fail closed."),
        ):
            result = self.a.run_player_turn("Does King Vharion rule Neverwinter?")

        self.assertIn("güvenilir bir doğrulamam yok", result["narration"])
        self.assertNotIn("UNVERIFIED", result["narration"])
        after = copy.deepcopy(self.a.world_state)
        before["flags"]["turn_index"] = after["flags"]["turn_index"]
        self.assertEqual(after, before)

    def test_save_load_preserves_ownership_and_references(self):
        self.npc(self.a)
        self.a.character["current_hp"] = 3
        self.a.recent_dm_narrations.append("Önceki anlatı")
        self.a.messages.append({"role": "user", "content": "Target before save"})
        self.a.roll_d20()
        self.b.world_state["inventory"].append("Other item")
        self.b.character["current_hp"] = 7
        self.b.recent_dm_narrations.append("Other narration")
        self.b.messages.append({"role": "user", "content": "Other adventure"})
        self.b.roll_stat()
        expected = self.a.serialize_game_state()
        sessions = (self.a, self.b, game._DEFAULT_SESSION)
        snapshots = [session.serialize_game_state() for session in sessions]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            self.a.save_game(path)
            self.a.character["current_hp"] = 0
            self.a.world_state["inventory"].clear()
            self.a.recent_dm_narrations.clear()
            self.a.messages.append({"role": "user", "content": "Target after save"})
            self.a.roll_stat()
            held = [
                (session.world_state, session.character, session.recent_dm_narrations,
                 session.messages, session.rng)
                for session in sessions
            ]
            message_histories = [copy.deepcopy(session.messages) for session in sessions]
            rng_states = [session.rng.getstate() for session in sessions]
            self.assertEqual(self.a.load_game(path), expected)
        self.assertEqual(expected["version"], 3)
        for session, references, history, rng_state, snapshot in zip(
                sessions, held, message_histories, rng_states, snapshots):
            with self.subTest(session=session):
                self.assertIs(session.world_state, references[0])
                self.assertIs(session.character, references[1])
                self.assertIs(session.recent_dm_narrations, references[2])
                self.assertIs(session.messages, references[3])
                self.assertIs(session.rng, references[4])
                self.assertEqual(session.messages, history)
                self.assertEqual(session.rng.getstate(), rng_state)
                self.assertEqual(session.serialize_game_state(), snapshot)

    def test_invalid_load_preserves_all_sessions_and_held_references(self):
        for session, name, hp in ((self.a, "Target", 3),
                                  (self.b, "Other", 7)):
            self.npc(session)
            session.character.update(name=name, current_hp=hp)
            session.world_state["inventory"].append(f"{name} item")
            session.recent_dm_narrations.append(f"{name} narration")
            session.messages.append({"role": "user", "content": name})
        self.a.roll_d20()
        self.b.roll_stat()

        sessions = (self.a, self.b, game._DEFAULT_SESSION)
        snapshots = [session.serialize_game_state() for session in sessions]
        rng_states = [session.rng.getstate() for session in sessions]
        messages = [copy.deepcopy(session.messages) for session in sessions]
        held = [
            (session.world_state, session.character, session.recent_dm_narrations)
            for session in sessions
        ]
        held_contents = copy.deepcopy(held)

        # Different valid player/world values expose a partial restore before
        # the invalid narration is rejected at the end of payload validation.
        payload = copy.deepcopy(snapshots[1])
        payload["recent_dm_narrations"] = ["Replacement narration", None]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Anlatı geçmişi geçersiz"):
                self.a.load_game(path)

        self.assertIs(game._session(), game._DEFAULT_SESSION)
        for session, references, contents, snapshot, rng_state, message_history in zip(
                sessions, held, held_contents, snapshots, rng_states, messages):
            with self.subTest(session=session):
                self.assertIs(session.world_state, references[0])
                self.assertIs(session.character, references[1])
                self.assertIs(session.recent_dm_narrations, references[2])
                self.assertEqual(references, contents)
                self.assertEqual(session.serialize_game_state(), snapshot)
                self.assertEqual(session.rng.getstate(), rng_state)
                self.assertEqual(session.messages, message_history)

    def test_invalid_default_load_preserves_all_sessions_and_held_references(self):
        default = game._DEFAULT_SESSION
        original_world = copy.deepcopy(default.world_state)
        original_character = copy.deepcopy(default.character)
        original_narrations = copy.deepcopy(default.recent_dm_narrations)
        original_messages = copy.deepcopy(default.messages)
        original_rng = default.rng.getstate()

        def restore_default():
            default.world_state.clear()
            default.world_state.update(original_world)
            default.character.clear()
            default.character.update(original_character)
            default.recent_dm_narrations[:] = original_narrations
            default.messages[:] = original_messages
            default.rng.setstate(original_rng)

        try:
            for session, name, hp in ((self.a, "First", 3),
                                      (self.b, "Second", 7),
                                      (default, "Default", 11)):
                self.npc(session)
                session.character.update(name=name, current_hp=hp)
                session.world_state["inventory"].append(f"{name} item")
                session.recent_dm_narrations.append(f"{name} narration")
                session.messages.append({"role": "user", "content": name})
                session.roll_d20()

            sessions = (self.a, self.b, default)
            held = [
                (
                    session.world_state,
                    session.character,
                    session.recent_dm_narrations,
                    session.messages,
                    session.rng,
                )
                for session in sessions
            ]
            held_contents = [
                tuple(copy.deepcopy(reference) for reference in references[:4])
                for references in held
            ]
            snapshots = [session.serialize_game_state() for session in sessions]
            rng_states = [session.rng.getstate() for session in sessions]
            messages = [copy.deepcopy(session.messages) for session in sessions]

            with tempfile.TemporaryDirectory() as directory:
                cases = (
                    ("missing", FileNotFoundError),
                    ("malformed", json.JSONDecodeError),
                    ("unsupported-version", ValueError),
                    ("invalid-payload", ValueError),
                )
                for failure, error in cases:
                    with self.subTest(failure=failure):
                        path = Path(directory) / f"{failure}.json"
                        if failure == "malformed":
                            path.write_text("{broken", encoding="utf-8")
                        elif failure == "unsupported-version":
                            payload = copy.deepcopy(snapshots[1])
                            payload["version"] = 999
                            path.write_text(json.dumps(payload), encoding="utf-8")
                        elif failure == "invalid-payload":
                            # Valid world/player data exposes a partial restore
                            # before validation rejects the narration history.
                            payload = copy.deepcopy(snapshots[1])
                            payload["recent_dm_narrations"] = [
                                "Replacement narration", None
                            ]
                            path.write_text(json.dumps(payload), encoding="utf-8")

                        with self.assertRaises(error):
                            game.load_game(path)

                        self.assertIs(game._session(), default)
                        for (session, references, contents, snapshot, rng_state,
                             message_history) in zip(
                                sessions, held, held_contents, snapshots,
                                rng_states, messages):
                            with self.subTest(session=session):
                                self.assertIs(session.world_state, references[0])
                                self.assertIs(session.character, references[1])
                                self.assertIs(
                                    session.recent_dm_narrations, references[2]
                                )
                                self.assertIs(session.messages, references[3])
                                self.assertIs(session.rng, references[4])
                                self.assertEqual(references[:4], contents)
                                self.assertEqual(
                                    session.serialize_game_state(), snapshot
                                )
                                self.assertEqual(session.rng.getstate(), rng_state)
                                self.assertEqual(session.messages, message_history)
        finally:
            restore_default()

    def test_save_load_conscious_player_clears_unconscious_status(self):
        self.a.character["current_hp"] = 3
        self.a.world_state["player_combat_status"] = "active"
        self.a.recent_dm_narrations.append("Ayaktasın.")
        expected = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_b = self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        world = self.a.world_state
        character = self.a.character
        history = self.a.recent_dm_narrations
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conscious.json"
            self.a.save_game(path)
            character["current_hp"] = 0
            world["player_combat_status"] = "unconscious"
            world["inventory"].clear()
            history.clear()
            self.assertEqual(self.a.load_game(path), expected)
        self.assertIs(world, self.a.world_state)
        self.assertIs(character, self.a.character)
        self.assertIs(history, self.a.recent_dm_narrations)
        self.assertEqual(character["current_hp"], 3)
        self.assertGreater(character["current_hp"], 0)
        self.assertEqual(world["player_combat_status"], "active")
        self.assertEqual(history, expected["recent_dm_narrations"])
        self.assertEqual(self.a.serialize_game_state(), expected)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_save_load_unconscious_player_keeps_other_sessions_conscious(self):
        self.a.character["current_hp"] = 0
        self.a.world_state["player_combat_status"] = "unconscious"
        self.a.recent_dm_narrations.append("Yere yığıldın.")
        self.assertGreater(self.b.character["current_hp"], 0)
        self.assertEqual(self.b.world_state["player_combat_status"], "active")
        expected = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_b = self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        world = self.a.world_state
        character = self.a.character
        history = self.a.recent_dm_narrations
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unconscious.json"
            self.a.save_game(path)
            character["current_hp"] = character["max_hp"]
            world["player_combat_status"] = "active"
            world["inventory"].clear()
            history.clear()
            self.assertEqual(self.a.load_game(path), expected)
        self.assertIs(world, self.a.world_state)
        self.assertIs(character, self.a.character)
        self.assertIs(history, self.a.recent_dm_narrations)
        self.assertEqual(character["current_hp"], 0)
        self.assertEqual(world["player_combat_status"], "unconscious")
        self.assertEqual(history, expected["recent_dm_narrations"])
        self.assertEqual(self.a.serialize_game_state(), expected)
        self.assertGreater(self.b.character["current_hp"], 0)
        self.assertEqual(self.b.world_state["player_combat_status"], "active")
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

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

    def test_overlapping_attack_cannot_borrow_another_sessions_distance(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.assertEqual(enemies[0]["id"], enemies[1]["id"])
        for session, enemy in zip((self.a, self.b), enemies):
            session.character.update(armor_class=10, current_hp=19)
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=2)
        # Remove both directional entries so neither reverse-pair geometry nor
        # an NPC distance can supply the missing prerequisite in campaign B.
        del self.b.world_state["attack_environment"]
        self.assertNotIn("distance_ft", enemies[1])
        before_a = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        valid_attack_waiting = threading.Event()
        rejected_attack_finished = threading.Event()
        roll_d20 = self.a.roll_d20

        def overlapping_roll():
            self.assertIs(game._session(), self.a)
            valid_attack_waiting.set()
            self.assertTrue(rejected_attack_finished.wait(timeout=5))
            self.assertIs(game._session(), self.a)
            return roll_d20()

        def reject_without_distance():
            try:
                self.assertTrue(valid_attack_waiting.wait(timeout=5))
                with self.assertRaises(game.combat_lifecycle.CombatRequestError) as error:
                    game.resolve_enemy_attack(enemies[1], session=self.b)
                self.assertEqual(error.exception.code, "distance_unknown")
                self.assertEqual(self.b.serialize_game_state(), before_b)
                self.assertEqual(self.b.rng.getstate(), rng_b)
            finally:
                rejected_attack_finished.set()

        with self.rolls(self.a, (20, 15), (6, 4)), \
             self.rolls(self.b), self.rolls(game._DEFAULT_SESSION), \
             patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                valid = pool.submit(game.resolve_enemy_attack, enemies[0],
                                    session=self.a)
                rejected = pool.submit(reject_without_distance)
                rejected.result(timeout=10)
                result = valid.result(timeout=10)

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["actor_id"], enemies[0]["id"])
        self.assertEqual(result["target_id"], "player")
        self.assertEqual(result["attack_rolls"], [15])
        self.assertEqual(result["target_ac"], 10)
        self.assertEqual(result["damage"], 6)
        self.assertEqual(result["target_hp_before"], 19)
        self.assertEqual(result["target_hp_after"], 13)
        self.assertEqual(result["target_status"], "active")
        # Compare the whole owning state, including its complete result record,
        # rather than just HP; B and the legacy default must remain untouched.
        before_a["player"]["current_hp"] = 13
        before_a["world_state"].setdefault("attack_results", []).append(
            copy.deepcopy(result)
        )
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attack_cannot_borrow_another_sessions_visibility(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.assertEqual(enemies[0]["id"], enemies[1]["id"])
        for session, enemy in zip((self.a, self.b), enemies):
            session.character.update(armor_class=10, current_hp=19)
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=2)
        # Both campaigns know the same distance. Only B's enemy cannot see
        # the player; its reverse directional entry remains fully visible.
        self.b.world_state["attack_environment"]["pairs"][
            f"{enemies[1]['id']}|player"
        ]["attacker_sees_target"] = False
        before_a = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        visible_attack_waiting = threading.Event()
        unseen_attack_finished = threading.Event()
        roll_d20 = self.a.roll_d20

        def overlapping_roll():
            self.assertIs(game._session(), self.a)
            visible_attack_waiting.set()
            self.assertTrue(unseen_attack_finished.wait(timeout=5))
            self.assertIs(game._session(), self.a)
            return roll_d20()

        def attack_without_visibility():
            try:
                self.assertTrue(visible_attack_waiting.wait(timeout=5))
                result = game.resolve_enemy_attack(enemies[1], session=self.b)
                # A is still inside its attack; B must not mutate its state.
                self.assertEqual(self.a.serialize_game_state(), before_a)
                self.assertEqual(self.a.rng.getstate(), rng_a)
                return result
            finally:
                unseen_attack_finished.set()

        with self.rolls(self.a, (20, 15), (6, 4)), \
             self.rolls(self.b, (20, 15), (20, 3)), \
             self.rolls(game._DEFAULT_SESSION), \
             patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                visible = pool.submit(game.resolve_enemy_attack, enemies[0],
                                      session=self.a)
                unseen = pool.submit(attack_without_visibility)
                result_b = unseen.result(timeout=10)
                result_a = visible.result(timeout=10)

        for result in (result_a, result_b):
            self.assertEqual(result["actor_id"], enemies[0]["id"])
            self.assertEqual(result["target_id"], "player")
            self.assertEqual(result["target_ac"], 10)
            self.assertEqual(result["target_hp_before"], 19)
            self.assertEqual(result["target_status"], "active")
            self.assertFalse(result["critical"])
            self.assertEqual(result["advantage_sources"], [])
        self.assertTrue(result_a["success"])
        self.assertEqual(result_a["outcome"], "hit")
        self.assertEqual(result_a["attack_rolls"], [15])
        self.assertEqual(result_a["attack_roll"], 15)
        self.assertEqual(result_a["disadvantage_sources"], [])
        self.assertFalse(result_a["disadvantage"])
        self.assertEqual(result_a["damage"], 6)
        self.assertEqual(result_a["target_hp_after"], 13)
        self.assertFalse(result_b["success"])
        self.assertEqual(result_b["outcome"], "miss")
        self.assertEqual(result_b["attack_rolls"], [15, 3])
        self.assertEqual(result_b["attack_roll"], 3)
        self.assertEqual(result_b["disadvantage_sources"], ["unseen_target"])
        self.assertTrue(result_b["disadvantage"])
        self.assertEqual(result_b["damage"], 0)
        self.assertEqual(result_b["damage_rolls"], [])
        self.assertEqual(result_b["target_hp_after"], 19)
        # A hit changes HP; a legal miss still records its owning result.
        # Everything else, including both directional visibility facts, stays.
        before_a["player"]["current_hp"] = 13
        for before, result in ((before_a, result_a), (before_b, result_b)):
            before["world_state"].setdefault("attack_results", []).append(
                copy.deepcopy(result)
            )
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attacks_keep_directional_cover_in_their_own_sessions(self):
        # The same noncritical roll hits the lower AC and misses the higher AC.
        # Swap the cover owners as well, so either campaign can expose leakage.
        cases = [
            ("none", "half", 11, 10, 12),
            ("half", "none", 11, 12, 10),
            ("half", ["none", "half", "three_quarters"], 14, 12, 15),
            (["three_quarters", "half", "none"], "half", 14, 15, 12),
        ]
        for cover_a, cover_b, roll, ac_a, ac_b in cases:
            with self.subTest(cover_a=cover_a, cover_b=cover_b):
                self.a = game.create_session(seed=17)
                self.b = game.create_session(seed=17)
                sessions = (self.a, self.b)
                enemies = [self.npc(session) for session in sessions]
                self.assertEqual(enemies[0]["id"], enemies[1]["id"])
                for session, enemy, cover in zip(
                    sessions, enemies, (cover_a, cover_b)
                ):
                    session.character.update(armor_class=10, current_hp=19)
                    enemy.update(attack_bonus=0, damage_die=6,
                                 damage_dice=1, damage_modifier=2)
                    pairs = session.world_state["attack_environment"]["pairs"]
                    pairs[f"{enemy['id']}|player"]["cover"] = cover
                    # Reverse geometry must not grant cover to this defender.
                    pairs[f"player|{enemy['id']}"]["cover"] = "total"
                    self.assertEqual(pairs[f"{enemy['id']}|player"]["distance_ft"], 5)
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                barrier = threading.Barrier(2)
                dice_a = ((20, roll),) + (((6, 4),) if roll >= ac_a else ())
                dice_b = ((20, roll),) + (((6, 4),) if roll >= ac_b else ())
                with self.rolls(self.a, *dice_a, barrier=barrier), \
                     self.rolls(self.b, *dice_b, barrier=barrier), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [
                            pool.submit(game.resolve_enemy_attack, enemy,
                                        session=session)
                            for session, enemy in zip(sessions, enemies)
                        ]
                        results = [future.result(timeout=10) for future in futures]

                for session, enemy, result, expected, rng, ac in zip(
                    sessions, enemies, results, before, rng_before, (ac_a, ac_b)
                ):
                    hit = roll >= ac
                    self.assertEqual(result["actor_id"], enemy["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["target_ac_base"], 10)
                    self.assertEqual(result["target_ac"], ac)
                    self.assertEqual(result["cover_state"],
                                     {10: "none", 12: "half", 15: "three_quarters"}[ac])
                    self.assertEqual(result["attack_rolls"], [roll])
                    self.assertEqual(result["attack_roll"], roll)
                    self.assertEqual(result["attack_total"], roll)
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"], [])
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["success"], hit)
                    self.assertEqual(result["outcome"], "hit" if hit else "miss")
                    self.assertEqual(result["damage"], 6 if hit else 0)
                    if not hit:
                        self.assertEqual(result["damage_rolls"], [])
                    self.assertEqual(result["target_hp_before"], 19)
                    self.assertEqual(result["target_hp_after"], 13 if hit else 19)
                    self.assertEqual(result["target_status"], "active")
                    expected["player"]["current_hp"] = 13 if hit else 19
                    expected["world_state"].setdefault("attack_results", []).append(
                        copy.deepcopy(result)
                    )
                    self.assertEqual(session.serialize_game_state(), expected)
                    self.assertEqual(session.rng.getstate(), rng)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attack_cannot_borrow_another_sessions_total_cover(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.assertEqual(enemies[0]["id"], enemies[1]["id"])
        for session, enemy, cover, reverse_cover in (
            (self.a, enemies[0], "none", "total"),
            (self.b, enemies[1], ["half", "total"], "none"),
        ):
            session.character.update(armor_class=10, current_hp=19)
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=2)
            pairs = session.world_state["attack_environment"]["pairs"]
            pairs[f"{enemy['id']}|player"]["cover"] = cover
            pairs[f"player|{enemy['id']}"]["cover"] = reverse_cover
            self.assertEqual(pairs[f"{enemy['id']}|player"]["distance_ft"], 5)
        before_a = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        legal_attack_waiting = threading.Event()
        blocked_attack_finished = threading.Event()
        roll_d20 = self.a.roll_d20

        def overlapping_roll():
            self.assertIs(game._session(), self.a)
            legal_attack_waiting.set()
            self.assertTrue(blocked_attack_finished.wait(timeout=5))
            self.assertIs(game._session(), self.a)
            return roll_d20()

        def reject_total_cover():
            try:
                self.assertTrue(legal_attack_waiting.wait(timeout=5))
                with self.assertRaises(game.combat_lifecycle.CombatRequestError) as error:
                    game.resolve_enemy_attack(enemies[1], session=self.b)
                self.assertEqual(error.exception.code, "total_cover")
                # Rejection consumes no dice and commits no result or state;
                # A is still paused inside its own otherwise legal attack.
                self.assertEqual(self.a.serialize_game_state(), before_a)
                self.assertEqual(self.b.serialize_game_state(), before_b)
                self.assertEqual(self.a.rng.getstate(), rng_a)
                self.assertEqual(self.b.rng.getstate(), rng_b)
            finally:
                blocked_attack_finished.set()

        with self.rolls(self.a, (20, 15), (6, 4)), \
             self.rolls(self.b), self.rolls(game._DEFAULT_SESSION), \
             patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                legal = pool.submit(game.resolve_enemy_attack, enemies[0],
                                    session=self.a)
                blocked = pool.submit(reject_total_cover)
                blocked.result(timeout=10)
                result = legal.result(timeout=10)

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["actor_id"], enemies[0]["id"])
        self.assertEqual(result["target_id"], "player")
        self.assertEqual(result["cover_state"], "none")
        self.assertEqual(result["target_ac_base"], 10)
        self.assertEqual(result["target_ac"], 10)
        self.assertEqual(result["attack_rolls"], [15])
        self.assertEqual(result["attack_total"], 15)
        self.assertEqual(result["advantage_sources"], [])
        self.assertEqual(result["disadvantage_sources"], [])
        self.assertFalse(result["critical"])
        self.assertEqual(result["damage"], 6)
        self.assertEqual(result["target_hp_before"], 19)
        self.assertEqual(result["target_hp_after"], 13)
        self.assertEqual(result["target_status"], "active")
        before_a["player"]["current_hp"] = 13
        before_a["world_state"].setdefault("attack_results", []).append(
            copy.deepcopy(result)
        )
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
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

    def test_overlapping_knockout_does_not_incapacitate_other_sessions(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.a.character.update(armor_class=10, current_hp=3)
        self.b.character.update(armor_class=12, current_hp=18)
        for enemy in enemies:
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=1)
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        attack_barrier = threading.Barrier(2)
        damage_barrier = threading.Barrier(2)
        with self.rolls(self.a, (20, 15), (6, 5),
                        barrier=attack_barrier, damage_barrier=damage_barrier), \
             self.rolls(self.b, (20, 16), (6, 2),
                        barrier=attack_barrier, damage_barrier=damage_barrier), \
             self.rolls(game._DEFAULT_SESSION):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(game.resolve_enemy_attack, npc,
                                       session=session)
                           for npc, session in zip(enemies, (self.a, self.b))]
                results = [future.result(timeout=10) for future in futures]
            self.assertEqual([result["success"] for result in results],
                             [True, True])
            self.assertEqual([result["damage"] for result in results], [6, 3])
            self.assertEqual([result["target_hp_before"] for result in results],
                             [3, 18])
            self.assertEqual([result["target_hp_after"] for result in results],
                             [0, 15])
            self.assertEqual([result["target_status"] for result in results],
                             ["unconscious", "active"])
            self.assertEqual(self.a.character["current_hp"], 0)
            self.assertEqual(self.b.character["current_hp"], 15)
            self.assertEqual(self.a.world_state["player_combat_status"],
                             "unconscious")
            self.assertEqual(self.b.world_state["player_combat_status"], "active")
            before_a = self.a.serialize_game_state()
            before_b = self.b.serialize_game_state()
            rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
            # An attack against an unconscious player has advantage. Script a
            # miss to confirm it consumes only session A's dice and state.
            with self.rolls(self.a, (20, 1), (20, 2)), \
                 self.rolls(self.b), \
                 self.rolls(game._DEFAULT_SESSION):
                follow_up = game.resolve_enemy_attack(enemies[0], session=self.a)
            self.assertFalse(follow_up["success"])
            self.assertEqual(follow_up["outcome"], "miss")
            self.assertEqual(follow_up["attack_rolls"], [1, 2])
            self.assertEqual(follow_up["damage"], 0)
            # A resolved miss records its result in the owning campaign. The
            # expected fixture includes exactly that record, not other changes.
            before_a["world_state"]["attack_results"].append(
                copy.deepcopy(follow_up)
            )
            self.assertEqual(self.a.serialize_game_state(), before_a)
            self.assertEqual(self.b.serialize_game_state(), before_b)
            self.assertEqual(self.a.rng.getstate(), rng_a)
            self.assertEqual(self.b.rng.getstate(), rng_b)
            self.assertEqual(game.serialize_game_state(), self.default_before)
        # B must still accept attacks after A's knockout has fully committed.
        with self.rolls(self.a), \
             self.rolls(self.b, (20, 17), (6, 4)), \
             self.rolls(game._DEFAULT_SESSION):
            conscious_attack = game.resolve_enemy_attack(enemies[1],
                                                         session=self.b)
        self.assertTrue(conscious_attack["success"])
        self.assertEqual(conscious_attack["outcome"], "hit")
        self.assertEqual(conscious_attack["attack_roll"], 17)
        self.assertEqual(conscious_attack["damage"], 5)
        self.assertEqual(conscious_attack["target_hp_before"], 15)
        self.assertEqual(conscious_attack["target_hp_after"], 10)
        self.assertEqual(conscious_attack["target_status"], "active")
        self.assertEqual(self.b.character["current_hp"], 10)
        self.assertEqual(self.b.world_state["player_combat_status"], "active")
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attack_cannot_borrow_another_sessions_hidden_attacker(self):
        for attacker_sees_target in (True, False):
            with self.subTest(attacker_sees_target=attacker_sees_target):
                self.a = game.create_session(seed=17)
                self.b = game.create_session(seed=17)
                enemies = [self.npc(self.a), self.npc(self.b)]
                self.assertEqual(enemies[0]["id"], enemies[1]["id"])
                for session, enemy, target_sees_attacker in zip(
                        (self.a, self.b), enemies, (True, False)):
                    session.character.update(armor_class=10, current_hp=19)
                    enemy.update(attack_bonus=0, damage_die=6,
                                 damage_dice=1, damage_modifier=2)
                    # The same known distance and attacker perception in both
                    # campaigns leave only B's attacker hidden from its target.
                    # Reverse-pair visibility remains unchanged and visible.
                    session.world_state["attack_environment"]["pairs"][
                        f"{enemy['id']}|player"
                    ].update(attacker_sees_target=attacker_sees_target,
                             target_sees_attacker=target_sees_attacker)
                before_a = self.a.serialize_game_state()
                before_b = self.b.serialize_game_state()
                rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                visible_attack_waiting = threading.Event()
                hidden_attack_finished = threading.Event()
                roll_d20 = self.a.roll_d20

                def overlapping_roll():
                    self.assertIs(game._session(), self.a)
                    visible_attack_waiting.set()
                    self.assertTrue(hidden_attack_finished.wait(timeout=5))
                    self.assertIs(game._session(), self.a)
                    return roll_d20()

                def hidden_attack():
                    try:
                        self.assertTrue(visible_attack_waiting.wait(timeout=5))
                        result = game.resolve_enemy_attack(enemies[1], session=self.b)
                        # B completes while A is suspended inside its attack.
                        self.assertEqual(self.a.serialize_game_state(), before_a)
                        self.assertEqual(self.a.rng.getstate(), rng_a)
                        return result
                    finally:
                        hidden_attack_finished.set()

                # Seeing the target gives B advantage (take 15, not 3).
                # Not seeing it cancels B's advantage to exactly one d20,
                # whereas A retains unseen-target disadvantage (take 3).
                rolls_a = ((20, 3),) if attacker_sees_target else ((20, 15), (20, 3))
                rolls_b = (((20, 3), (20, 15), (6, 4)) if attacker_sees_target
                           else ((20, 15), (6, 4)))
                with self.rolls(self.a, *rolls_a), \
                     self.rolls(self.b, *rolls_b), \
                     self.rolls(game._DEFAULT_SESSION), \
                     patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        visible = pool.submit(game.resolve_enemy_attack, enemies[0],
                                              session=self.a)
                        hidden = pool.submit(hidden_attack)
                        result_b = hidden.result(timeout=10)
                        result_a = visible.result(timeout=10)

                disadvantage_sources = [] if attacker_sees_target else ["unseen_target"]
                for result, advantages in ((result_a, []), (result_b, ["unseen_attacker"])):
                    self.assertEqual(result["actor_id"], enemies[0]["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["target_ac"], 10)
                    self.assertEqual(result["target_hp_before"], 19)
                    self.assertEqual(result["target_status"], "active")
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["advantage_sources"], advantages)
                    self.assertEqual(result["disadvantage_sources"], disadvantage_sources)
                self.assertFalse(result_a["success"])
                self.assertEqual(result_a["outcome"], "miss")
                self.assertEqual(result_a["attack_rolls"], [value for _, value in rolls_a])
                self.assertEqual(result_a["attack_roll"], 3)
                self.assertEqual(result_a["disadvantage"], not attacker_sees_target)
                self.assertFalse(result_a["resolution"]["advantage"])
                self.assertFalse(result_a["resolution"]["advantage_cancelled"])
                self.assertEqual(result_a["damage"], 0)
                self.assertEqual(result_a["damage_rolls"], [])
                self.assertEqual(result_a["target_hp_after"], 19)
                self.assertTrue(result_b["success"])
                self.assertEqual(result_b["outcome"], "hit")
                self.assertEqual(result_b["attack_rolls"],
                                 [3, 15] if attacker_sees_target else [15])
                self.assertEqual(result_b["attack_roll"], 15)
                self.assertFalse(result_b["disadvantage"])
                self.assertTrue(result_b["resolution"]["advantage"])
                self.assertEqual(result_b["resolution"]["advantage_cancelled"],
                                 not attacker_sees_target)
                self.assertEqual(result_b["damage"], 6)
                self.assertEqual(result_b["target_hp_after"], 13)
                # Only B loses HP; both legal attacks record their own results.
                # Full snapshots retain all directional environment facts.
                before_b["player"]["current_hp"] = 13
                for before, result in ((before_a, result_a), (before_b, result_b)):
                    before["world_state"].setdefault("attack_results", []).append(
                        copy.deepcopy(result)
                    )
                self.assertEqual(self.a.serialize_game_state(), before_a)
                self.assertEqual(self.b.serialize_game_state(), before_b)
                self.assertEqual(self.a.rng.getstate(), rng_a)
                self.assertEqual(self.b.rng.getstate(), rng_b)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
            }
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

    def test_unverified_lore_claim_preserves_unrelated_local_proposals(self):
        self.a.world_state["location"] = "tavern"
        self.a.world_state["locations"]["tavern"] = {"name": "Taverna"}
        before_npcs = copy.deepcopy(self.a.world_state["npcs"])
        before_locations = copy.deepcopy(self.a.world_state["locations"])
        before_features = copy.deepcopy(self.a.world_state["features"])
        before_events = copy.deepcopy(self.a.world_state["events"])
        with patch.object(
            game, "parse_player_intent", return_value={"intent": "unknown"}
        ), patch.object(game, "should_generate_npcs", return_value=True), patch.object(
            game,
            "ask_dungeon_master",
            return_value={
                "narration": "King Vharion rules Neverwinter.",
                "world_updates": {
                    "create_npcs": [{
                        "name": "Elara",
                        "role": "merchant",
                        "location": "tavern",
                    }],
                    "events": ["Lamba alevi titrer."],
                },
                "lore_claims": [],
                "valid_response": True,
            },
        ):
            result = self.a.run_player_turn("Rüzgar esiyor.")

        self.assertIn("güvenilir bir doğrulamam yok", result["narration"])
        self.assertNotIn("UNVERIFIED", result["narration"])
        self.assertNotIn("King Vharion", result["narration"])
        self.assertEqual(len(self.a.world_state["npcs"]), len(before_npcs) + 1)
        elara = self.a.world_state["npcs"][-1]
        self.assertEqual(elara["name"], "Elara")
        self.assertEqual(elara["location"], "tavern")
        self.assertEqual(elara["reality_layer"], "PROCEDURAL_LOCAL_FICTION")
        self.assertEqual(self.a.world_state["locations"], before_locations)
        self.assertEqual(self.a.world_state["features"], before_features)
        self.assertEqual(len(self.a.world_state["events"]), len(before_events) + 1)
        self.assertEqual(
            self.a.world_state["events"][-1]["reality_layer"],
            "NARRATIVE_TEXTURE",
        )

    def test_unregistered_lore_question_returns_explicit_unverified_without_model_answer(self):
        before = copy.deepcopy(self.a.world_state)
        with patch.object(
            game,
            "parse_player_intent",
            side_effect=AssertionError("Unsupported lore questions must be caught before intent parsing."),
        ), patch.object(
            game,
            "ask_dungeon_master",
            side_effect=AssertionError("Unsupported lore question must fail closed."),
        ):
            result = self.a.run_player_turn("Does King Vharion rule Neverwinter?")

        self.assertIn("güvenilir bir doğrulamam yok", result["narration"])
        self.assertNotIn("UNVERIFIED", result["narration"])
        after = copy.deepcopy(self.a.world_state)
        before["flags"]["turn_index"] = after["flags"]["turn_index"]
        self.assertEqual(after, before)

    def test_save_load_preserves_ownership_and_references(self):
        self.npc(self.a)
        self.a.character["current_hp"] = 3
        self.a.recent_dm_narrations.append("Önceki anlatı")
        self.a.messages.append({"role": "user", "content": "Target before save"})
        self.a.roll_d20()
        self.b.world_state["inventory"].append("Other item")
        self.b.character["current_hp"] = 7
        self.b.recent_dm_narrations.append("Other narration")
        self.b.messages.append({"role": "user", "content": "Other adventure"})
        self.b.roll_stat()
        expected = self.a.serialize_game_state()
        sessions = (self.a, self.b, game._DEFAULT_SESSION)
        snapshots = [session.serialize_game_state() for session in sessions]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            self.a.save_game(path)
            self.a.character["current_hp"] = 0
            self.a.world_state["inventory"].clear()
            self.a.recent_dm_narrations.clear()
            self.a.messages.append({"role": "user", "content": "Target after save"})
            self.a.roll_stat()
            held = [
                (session.world_state, session.character, session.recent_dm_narrations,
                 session.messages, session.rng)
                for session in sessions
            ]
            message_histories = [copy.deepcopy(session.messages) for session in sessions]
            rng_states = [session.rng.getstate() for session in sessions]
            self.assertEqual(self.a.load_game(path), expected)
        self.assertEqual(expected["version"], 3)
        for session, references, history, rng_state, snapshot in zip(
                sessions, held, message_histories, rng_states, snapshots):
            with self.subTest(session=session):
                self.assertIs(session.world_state, references[0])
                self.assertIs(session.character, references[1])
                self.assertIs(session.recent_dm_narrations, references[2])
                self.assertIs(session.messages, references[3])
                self.assertIs(session.rng, references[4])
                self.assertEqual(session.messages, history)
                self.assertEqual(session.rng.getstate(), rng_state)
                self.assertEqual(session.serialize_game_state(), snapshot)

    def test_invalid_load_preserves_all_sessions_and_held_references(self):
        for session, name, hp in ((self.a, "Target", 3),
                                  (self.b, "Other", 7)):
            self.npc(session)
            session.character.update(name=name, current_hp=hp)
            session.world_state["inventory"].append(f"{name} item")
            session.recent_dm_narrations.append(f"{name} narration")
            session.messages.append({"role": "user", "content": name})
        self.a.roll_d20()
        self.b.roll_stat()

        sessions = (self.a, self.b, game._DEFAULT_SESSION)
        snapshots = [session.serialize_game_state() for session in sessions]
        rng_states = [session.rng.getstate() for session in sessions]
        messages = [copy.deepcopy(session.messages) for session in sessions]
        held = [
            (session.world_state, session.character, session.recent_dm_narrations)
            for session in sessions
        ]
        held_contents = copy.deepcopy(held)

        # Different valid player/world values expose a partial restore before
        # the invalid narration is rejected at the end of payload validation.
        payload = copy.deepcopy(snapshots[1])
        payload["recent_dm_narrations"] = ["Replacement narration", None]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Anlatı geçmişi geçersiz"):
                self.a.load_game(path)

        self.assertIs(game._session(), game._DEFAULT_SESSION)
        for session, references, contents, snapshot, rng_state, message_history in zip(
                sessions, held, held_contents, snapshots, rng_states, messages):
            with self.subTest(session=session):
                self.assertIs(session.world_state, references[0])
                self.assertIs(session.character, references[1])
                self.assertIs(session.recent_dm_narrations, references[2])
                self.assertEqual(references, contents)
                self.assertEqual(session.serialize_game_state(), snapshot)
                self.assertEqual(session.rng.getstate(), rng_state)
                self.assertEqual(session.messages, message_history)

    def test_invalid_default_load_preserves_all_sessions_and_held_references(self):
        default = game._DEFAULT_SESSION
        original_world = copy.deepcopy(default.world_state)
        original_character = copy.deepcopy(default.character)
        original_narrations = copy.deepcopy(default.recent_dm_narrations)
        original_messages = copy.deepcopy(default.messages)
        original_rng = default.rng.getstate()

        def restore_default():
            default.world_state.clear()
            default.world_state.update(original_world)
            default.character.clear()
            default.character.update(original_character)
            default.recent_dm_narrations[:] = original_narrations
            default.messages[:] = original_messages
            default.rng.setstate(original_rng)

        try:
            for session, name, hp in ((self.a, "First", 3),
                                      (self.b, "Second", 7),
                                      (default, "Default", 11)):
                self.npc(session)
                session.character.update(name=name, current_hp=hp)
                session.world_state["inventory"].append(f"{name} item")
                session.recent_dm_narrations.append(f"{name} narration")
                session.messages.append({"role": "user", "content": name})
                session.roll_d20()

            sessions = (self.a, self.b, default)
            held = [
                (
                    session.world_state,
                    session.character,
                    session.recent_dm_narrations,
                    session.messages,
                    session.rng,
                )
                for session in sessions
            ]
            held_contents = [
                tuple(copy.deepcopy(reference) for reference in references[:4])
                for references in held
            ]
            snapshots = [session.serialize_game_state() for session in sessions]
            rng_states = [session.rng.getstate() for session in sessions]
            messages = [copy.deepcopy(session.messages) for session in sessions]

            with tempfile.TemporaryDirectory() as directory:
                cases = (
                    ("missing", FileNotFoundError),
                    ("malformed", json.JSONDecodeError),
                    ("unsupported-version", ValueError),
                    ("invalid-payload", ValueError),
                )
                for failure, error in cases:
                    with self.subTest(failure=failure):
                        path = Path(directory) / f"{failure}.json"
                        if failure == "malformed":
                            path.write_text("{broken", encoding="utf-8")
                        elif failure == "unsupported-version":
                            payload = copy.deepcopy(snapshots[1])
                            payload["version"] = 999
                            path.write_text(json.dumps(payload), encoding="utf-8")
                        elif failure == "invalid-payload":
                            # Valid world/player data exposes a partial restore
                            # before validation rejects the narration history.
                            payload = copy.deepcopy(snapshots[1])
                            payload["recent_dm_narrations"] = [
                                "Replacement narration", None
                            ]
                            path.write_text(json.dumps(payload), encoding="utf-8")

                        with self.assertRaises(error):
                            game.load_game(path)

                        self.assertIs(game._session(), default)
                        for (session, references, contents, snapshot, rng_state,
                             message_history) in zip(
                                sessions, held, held_contents, snapshots,
                                rng_states, messages):
                            with self.subTest(session=session):
                                self.assertIs(session.world_state, references[0])
                                self.assertIs(session.character, references[1])
                                self.assertIs(
                                    session.recent_dm_narrations, references[2]
                                )
                                self.assertIs(session.messages, references[3])
                                self.assertIs(session.rng, references[4])
                                self.assertEqual(references[:4], contents)
                                self.assertEqual(
                                    session.serialize_game_state(), snapshot
                                )
                                self.assertEqual(session.rng.getstate(), rng_state)
                                self.assertEqual(session.messages, message_history)
        finally:
            restore_default()

    def test_save_load_conscious_player_clears_unconscious_status(self):
        self.a.character["current_hp"] = 3
        self.a.world_state["player_combat_status"] = "active"
        self.a.recent_dm_narrations.append("Ayaktasın.")
        expected = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_b = self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        world = self.a.world_state
        character = self.a.character
        history = self.a.recent_dm_narrations
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conscious.json"
            self.a.save_game(path)
            character["current_hp"] = 0
            world["player_combat_status"] = "unconscious"
            world["inventory"].clear()
            history.clear()
            self.assertEqual(self.a.load_game(path), expected)
        self.assertIs(world, self.a.world_state)
        self.assertIs(character, self.a.character)
        self.assertIs(history, self.a.recent_dm_narrations)
        self.assertEqual(character["current_hp"], 3)
        self.assertGreater(character["current_hp"], 0)
        self.assertEqual(world["player_combat_status"], "active")
        self.assertEqual(history, expected["recent_dm_narrations"])
        self.assertEqual(self.a.serialize_game_state(), expected)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_save_load_unconscious_player_keeps_other_sessions_conscious(self):
        self.a.character["current_hp"] = 0
        self.a.world_state["player_combat_status"] = "unconscious"
        self.a.recent_dm_narrations.append("Yere yığıldın.")
        self.assertGreater(self.b.character["current_hp"], 0)
        self.assertEqual(self.b.world_state["player_combat_status"], "active")
        expected = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_b = self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        world = self.a.world_state
        character = self.a.character
        history = self.a.recent_dm_narrations
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unconscious.json"
            self.a.save_game(path)
            character["current_hp"] = character["max_hp"]
            world["player_combat_status"] = "active"
            world["inventory"].clear()
            history.clear()
            self.assertEqual(self.a.load_game(path), expected)
        self.assertIs(world, self.a.world_state)
        self.assertIs(character, self.a.character)
        self.assertIs(history, self.a.recent_dm_narrations)
        self.assertEqual(character["current_hp"], 0)
        self.assertEqual(world["player_combat_status"], "unconscious")
        self.assertEqual(history, expected["recent_dm_narrations"])
        self.assertEqual(self.a.serialize_game_state(), expected)
        self.assertGreater(self.b.character["current_hp"], 0)
        self.assertEqual(self.b.world_state["player_combat_status"], "active")
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

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


    def test_overlapping_attack_cannot_borrow_another_sessions_distance(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.assertEqual(enemies[0]["id"], enemies[1]["id"])
        for session, enemy in zip((self.a, self.b), enemies):
            session.character.update(armor_class=10, current_hp=19)
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=2)
        # Remove both directional entries so neither reverse-pair geometry nor
        # an NPC distance can supply the missing prerequisite in campaign B.
        del self.b.world_state["attack_environment"]
        self.assertNotIn("distance_ft", enemies[1])
        before_a = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        valid_attack_waiting = threading.Event()
        rejected_attack_finished = threading.Event()
        roll_d20 = self.a.roll_d20

        def overlapping_roll():
            self.assertIs(game._session(), self.a)
            valid_attack_waiting.set()
            self.assertTrue(rejected_attack_finished.wait(timeout=5))
            self.assertIs(game._session(), self.a)
            return roll_d20()

        def reject_without_distance():
            try:
                self.assertTrue(valid_attack_waiting.wait(timeout=5))
                with self.assertRaises(game.combat_lifecycle.CombatRequestError) as error:
                    game.resolve_enemy_attack(enemies[1], session=self.b)
                self.assertEqual(error.exception.code, "distance_unknown")
                self.assertEqual(self.b.serialize_game_state(), before_b)
                self.assertEqual(self.b.rng.getstate(), rng_b)
            finally:
                rejected_attack_finished.set()

        with self.rolls(self.a, (20, 15), (6, 4)), \
             self.rolls(self.b), self.rolls(game._DEFAULT_SESSION), \
             patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                valid = pool.submit(game.resolve_enemy_attack, enemies[0],
                                    session=self.a)
                rejected = pool.submit(reject_without_distance)
                rejected.result(timeout=10)
                result = valid.result(timeout=10)

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["actor_id"], enemies[0]["id"])
        self.assertEqual(result["target_id"], "player")
        self.assertEqual(result["attack_rolls"], [15])
        self.assertEqual(result["target_ac"], 10)
        self.assertEqual(result["damage"], 6)
        self.assertEqual(result["target_hp_before"], 19)
        self.assertEqual(result["target_hp_after"], 13)
        self.assertEqual(result["target_status"], "active")
        # Compare the whole owning state, including its complete result record,
        # rather than just HP; B and the legacy default must remain untouched.
        before_a["player"]["current_hp"] = 13
        before_a["world_state"].setdefault("attack_results", []).append(
            copy.deepcopy(result)
        )
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attack_cannot_borrow_another_sessions_visibility(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.assertEqual(enemies[0]["id"], enemies[1]["id"])
        for session, enemy in zip((self.a, self.b), enemies):
            session.character.update(armor_class=10, current_hp=19)
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=2)
        # Both campaigns know the same distance. Only B's enemy cannot see
        # the player; its reverse directional entry remains fully visible.
        self.b.world_state["attack_environment"]["pairs"][
            f"{enemies[1]['id']}|player"
        ]["attacker_sees_target"] = False
        before_a = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        visible_attack_waiting = threading.Event()
        unseen_attack_finished = threading.Event()
        roll_d20 = self.a.roll_d20

        def overlapping_roll():
            self.assertIs(game._session(), self.a)
            visible_attack_waiting.set()
            self.assertTrue(unseen_attack_finished.wait(timeout=5))
            self.assertIs(game._session(), self.a)
            return roll_d20()

        def attack_without_visibility():
            try:
                self.assertTrue(visible_attack_waiting.wait(timeout=5))
                result = game.resolve_enemy_attack(enemies[1], session=self.b)
                # A is still inside its attack; B must not mutate its state.
                self.assertEqual(self.a.serialize_game_state(), before_a)
                self.assertEqual(self.a.rng.getstate(), rng_a)
                return result
            finally:
                unseen_attack_finished.set()

        with self.rolls(self.a, (20, 15), (6, 4)), \
             self.rolls(self.b, (20, 15), (20, 3)), \
             self.rolls(game._DEFAULT_SESSION), \
             patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                visible = pool.submit(game.resolve_enemy_attack, enemies[0],
                                      session=self.a)
                unseen = pool.submit(attack_without_visibility)
                result_b = unseen.result(timeout=10)
                result_a = visible.result(timeout=10)

        for result in (result_a, result_b):
            self.assertEqual(result["actor_id"], enemies[0]["id"])
            self.assertEqual(result["target_id"], "player")
            self.assertEqual(result["target_ac"], 10)
            self.assertEqual(result["target_hp_before"], 19)
            self.assertEqual(result["target_status"], "active")
            self.assertFalse(result["critical"])
            self.assertEqual(result["advantage_sources"], [])
        self.assertTrue(result_a["success"])
        self.assertEqual(result_a["outcome"], "hit")
        self.assertEqual(result_a["attack_rolls"], [15])
        self.assertEqual(result_a["attack_roll"], 15)
        self.assertEqual(result_a["disadvantage_sources"], [])
        self.assertFalse(result_a["disadvantage"])
        self.assertEqual(result_a["damage"], 6)
        self.assertEqual(result_a["target_hp_after"], 13)
        self.assertFalse(result_b["success"])
        self.assertEqual(result_b["outcome"], "miss")
        self.assertEqual(result_b["attack_rolls"], [15, 3])
        self.assertEqual(result_b["attack_roll"], 3)
        self.assertEqual(result_b["disadvantage_sources"], ["unseen_target"])
        self.assertTrue(result_b["disadvantage"])
        self.assertEqual(result_b["damage"], 0)
        self.assertEqual(result_b["damage_rolls"], [])
        self.assertEqual(result_b["target_hp_after"], 19)
        # A hit changes HP; a legal miss still records its owning result.
        # Everything else, including both directional visibility facts, stays.
        before_a["player"]["current_hp"] = 13
        for before, result in ((before_a, result_a), (before_b, result_b)):
            before["world_state"].setdefault("attack_results", []).append(
                copy.deepcopy(result)
            )
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attacks_keep_directional_cover_in_their_own_sessions(self):
        # The same noncritical roll hits the lower AC and misses the higher AC.
        # Swap the cover owners as well, so either campaign can expose leakage.
        cases = [
            ("none", "half", 11, 10, 12),
            ("half", "none", 11, 12, 10),
            ("half", ["none", "half", "three_quarters"], 14, 12, 15),
            (["three_quarters", "half", "none"], "half", 14, 15, 12),
        ]
        for cover_a, cover_b, roll, ac_a, ac_b in cases:
            with self.subTest(cover_a=cover_a, cover_b=cover_b):
                self.a = game.create_session(seed=17)
                self.b = game.create_session(seed=17)
                sessions = (self.a, self.b)
                enemies = [self.npc(session) for session in sessions]
                self.assertEqual(enemies[0]["id"], enemies[1]["id"])
                for session, enemy, cover in zip(
                    sessions, enemies, (cover_a, cover_b)
                ):
                    session.character.update(armor_class=10, current_hp=19)
                    enemy.update(attack_bonus=0, damage_die=6,
                                 damage_dice=1, damage_modifier=2)
                    pairs = session.world_state["attack_environment"]["pairs"]
                    pairs[f"{enemy['id']}|player"]["cover"] = cover
                    # Reverse geometry must not grant cover to this defender.
                    pairs[f"player|{enemy['id']}"]["cover"] = "total"
                    self.assertEqual(pairs[f"{enemy['id']}|player"]["distance_ft"], 5)
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                barrier = threading.Barrier(2)
                dice_a = ((20, roll),) + (((6, 4),) if roll >= ac_a else ())
                dice_b = ((20, roll),) + (((6, 4),) if roll >= ac_b else ())
                with self.rolls(self.a, *dice_a, barrier=barrier), \
                     self.rolls(self.b, *dice_b, barrier=barrier), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [
                            pool.submit(game.resolve_enemy_attack, enemy,
                                        session=session)
                            for session, enemy in zip(sessions, enemies)
                        ]
                        results = [future.result(timeout=10) for future in futures]

                for session, enemy, result, expected, rng, ac in zip(
                    sessions, enemies, results, before, rng_before, (ac_a, ac_b)
                ):
                    hit = roll >= ac
                    self.assertEqual(result["actor_id"], enemy["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["target_ac_base"], 10)
                    self.assertEqual(result["target_ac"], ac)
                    self.assertEqual(result["cover_state"],
                                     {10: "none", 12: "half", 15: "three_quarters"}[ac])
                    self.assertEqual(result["attack_rolls"], [roll])
                    self.assertEqual(result["attack_roll"], roll)
                    self.assertEqual(result["attack_total"], roll)
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"], [])
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["success"], hit)
                    self.assertEqual(result["outcome"], "hit" if hit else "miss")
                    self.assertEqual(result["damage"], 6 if hit else 0)
                    if not hit:
                        self.assertEqual(result["damage_rolls"], [])
                    self.assertEqual(result["target_hp_before"], 19)
                    self.assertEqual(result["target_hp_after"], 13 if hit else 19)
                    self.assertEqual(result["target_status"], "active")
                    expected["player"]["current_hp"] = 13 if hit else 19
                    expected["world_state"].setdefault("attack_results", []).append(
                        copy.deepcopy(result)
                    )
                    self.assertEqual(session.serialize_game_state(), expected)
                    self.assertEqual(session.rng.getstate(), rng)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attack_cannot_borrow_another_sessions_total_cover(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.assertEqual(enemies[0]["id"], enemies[1]["id"])
        for session, enemy, cover, reverse_cover in (
            (self.a, enemies[0], "none", "total"),
            (self.b, enemies[1], ["half", "total"], "none"),
        ):
            session.character.update(armor_class=10, current_hp=19)
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=2)
            pairs = session.world_state["attack_environment"]["pairs"]
            pairs[f"{enemy['id']}|player"]["cover"] = cover
            pairs[f"player|{enemy['id']}"]["cover"] = reverse_cover
            self.assertEqual(pairs[f"{enemy['id']}|player"]["distance_ft"], 5)
        before_a = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        legal_attack_waiting = threading.Event()
        blocked_attack_finished = threading.Event()
        roll_d20 = self.a.roll_d20

        def overlapping_roll():
            self.assertIs(game._session(), self.a)
            legal_attack_waiting.set()
            self.assertTrue(blocked_attack_finished.wait(timeout=5))
            self.assertIs(game._session(), self.a)
            return roll_d20()

        def reject_total_cover():
            try:
                self.assertTrue(legal_attack_waiting.wait(timeout=5))
                with self.assertRaises(game.combat_lifecycle.CombatRequestError) as error:
                    game.resolve_enemy_attack(enemies[1], session=self.b)
                self.assertEqual(error.exception.code, "total_cover")
                # Rejection consumes no dice and commits no result or state;
                # A is still paused inside its own otherwise legal attack.
                self.assertEqual(self.a.serialize_game_state(), before_a)
                self.assertEqual(self.b.serialize_game_state(), before_b)
                self.assertEqual(self.a.rng.getstate(), rng_a)
                self.assertEqual(self.b.rng.getstate(), rng_b)
            finally:
                blocked_attack_finished.set()

        with self.rolls(self.a, (20, 15), (6, 4)), \
             self.rolls(self.b), self.rolls(game._DEFAULT_SESSION), \
             patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                legal = pool.submit(game.resolve_enemy_attack, enemies[0],
                                    session=self.a)
                blocked = pool.submit(reject_total_cover)
                blocked.result(timeout=10)
                result = legal.result(timeout=10)

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["actor_id"], enemies[0]["id"])
        self.assertEqual(result["target_id"], "player")
        self.assertEqual(result["cover_state"], "none")
        self.assertEqual(result["target_ac_base"], 10)
        self.assertEqual(result["target_ac"], 10)
        self.assertEqual(result["attack_rolls"], [15])
        self.assertEqual(result["attack_total"], 15)
        self.assertEqual(result["advantage_sources"], [])
        self.assertEqual(result["disadvantage_sources"], [])
        self.assertFalse(result["critical"])
        self.assertEqual(result["damage"], 6)
        self.assertEqual(result["target_hp_before"], 19)
        self.assertEqual(result["target_hp_after"], 13)
        self.assertEqual(result["target_status"], "active")
        before_a["player"]["current_hp"] = 13
        before_a["world_state"].setdefault("attack_results", []).append(
            copy.deepcopy(result)
        )
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.b.serialize_game_state(), before_b)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(self.b.rng.getstate(), rng_b)
        self.assertEqual(game.serialize_game_state(), self.default_before)
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


    def test_overlapping_knockout_does_not_incapacitate_other_sessions(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.a.character.update(armor_class=10, current_hp=3)
        self.b.character.update(armor_class=12, current_hp=18)
        for enemy in enemies:
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=1)
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        attack_barrier = threading.Barrier(2)
        damage_barrier = threading.Barrier(2)
        with self.rolls(self.a, (20, 15), (6, 5),
                        barrier=attack_barrier, damage_barrier=damage_barrier), \
             self.rolls(self.b, (20, 16), (6, 2),
                        barrier=attack_barrier, damage_barrier=damage_barrier), \
             self.rolls(game._DEFAULT_SESSION):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(game.resolve_enemy_attack, npc,
                                       session=session)
                           for npc, session in zip(enemies, (self.a, self.b))]
                results = [future.result(timeout=10) for future in futures]
            self.assertEqual([result["success"] for result in results],
                             [True, True])
            self.assertEqual([result["damage"] for result in results], [6, 3])
            self.assertEqual([result["target_hp_before"] for result in results],
                             [3, 18])
            self.assertEqual([result["target_hp_after"] for result in results],
                             [0, 15])
            self.assertEqual([result["target_status"] for result in results],
                             ["unconscious", "active"])
            self.assertEqual(self.a.character["current_hp"], 0)
            self.assertEqual(self.b.character["current_hp"], 15)
            self.assertEqual(self.a.world_state["player_combat_status"],
                             "unconscious")
            self.assertEqual(self.b.world_state["player_combat_status"], "active")
            before_a = self.a.serialize_game_state()
            before_b = self.b.serialize_game_state()
            rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
            # An attack against an unconscious player has advantage. Script a
            # miss to confirm it consumes only session A's dice and state.
            with self.rolls(self.a, (20, 1), (20, 2)), \
                 self.rolls(self.b), \
                 self.rolls(game._DEFAULT_SESSION):
                follow_up = game.resolve_enemy_attack(enemies[0], session=self.a)
            self.assertFalse(follow_up["success"])
            self.assertEqual(follow_up["outcome"], "miss")
            self.assertEqual(follow_up["attack_rolls"], [1, 2])
            self.assertEqual(follow_up["damage"], 0)
            # A resolved miss records its result in the owning campaign. The
            # expected fixture includes exactly that record, not other changes.
            before_a["world_state"]["attack_results"].append(
                copy.deepcopy(follow_up)
            )
            self.assertEqual(self.a.serialize_game_state(), before_a)
            self.assertEqual(self.b.serialize_game_state(), before_b)
            self.assertEqual(self.a.rng.getstate(), rng_a)
            self.assertEqual(self.b.rng.getstate(), rng_b)
            self.assertEqual(game.serialize_game_state(), self.default_before)
        # B must still accept attacks after A's knockout has fully committed.
        with self.rolls(self.a), \
             self.rolls(self.b, (20, 17), (6, 4)), \
             self.rolls(game._DEFAULT_SESSION):
            conscious_attack = game.resolve_enemy_attack(enemies[1],
                                                         session=self.b)
        self.assertTrue(conscious_attack["success"])
        self.assertEqual(conscious_attack["outcome"], "hit")
        self.assertEqual(conscious_attack["attack_roll"], 17)
        self.assertEqual(conscious_attack["damage"], 5)
        self.assertEqual(conscious_attack["target_hp_before"], 15)
        self.assertEqual(conscious_attack["target_hp_after"], 10)
        self.assertEqual(conscious_attack["target_status"], "active")
        self.assertEqual(self.b.character["current_hp"], 10)
        self.assertEqual(self.b.world_state["player_combat_status"], "active")
        self.assertEqual(self.a.serialize_game_state(), before_a)
        self.assertEqual(self.a.rng.getstate(), rng_a)
        self.assertEqual(game.serialize_game_state(), self.default_before)
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

    def test_default_save_preserves_explicit_sessions_and_held_references(self):
        explicit_sessions = (
            game.create_session(seed=137),
            game.create_session(seed=251),
        )
        for index, session in enumerate(explicit_sessions, start=1):
            session.character["name"] = f"ExplicitAdventure{index}"
            session.character["current_hp"] = index * 3
            session.world_state["location"] = f"explicit_location_{index}"
            session.world_state["inventory"].append(f"Adventure {index} item")
            session.recent_dm_narrations.append(
                f"Adventure {index} narration"
            )

        held_references = [
            (session.world_state, session.character, session.recent_dm_narrations)
            for session in explicit_sessions
        ]
        snapshots = [
            session.serialize_game_state() for session in explicit_sessions
        ]
        default_snapshot = game.serialize_game_state()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "default-save.json"
            self.assertEqual(game.save_game(path), path)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                default_snapshot,
            )

        for session, references, snapshot in zip(
                explicit_sessions, held_references, snapshots):
            with self.subTest(session=session):
                self.assertIs(session.world_state, references[0])
                self.assertIs(session.character, references[1])
                self.assertIs(session.recent_dm_narrations, references[2])
                self.assertEqual(session.serialize_game_state(), snapshot)

    def test_successful_default_load_preserves_other_adventures_and_held_references(self):
        default = game._DEFAULT_SESSION
        explicit_sessions = (
            game.create_session(seed=137),
            game.create_session(seed=251),
        )
        sessions = (default, *explicit_sessions)
        original_default_state = copy.deepcopy(game.serialize_game_state())
        original_default_messages = copy.deepcopy(default.messages)
        original_default_rng_state = default.rng.getstate()

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            load_path = directory / "loaded-adventure.json"
            restore_path = directory / "restore-default.json"
            restore_path.write_text(
                json.dumps(original_default_state), encoding="utf-8"
            )
            try:
                loaded_adventure = game.create_session(seed=389)
                loaded_adventure.character["name"] = "LoadedHero"
                loaded_adventure.world_state["location"] = "forest"
                loaded_adventure.world_state["inventory"].append("Loaded keepsake")
                loaded_adventure.recent_dm_narrations[:] = [
                    "Narration from saved adventure"
                ]
                expected_loaded_state = loaded_adventure.serialize_game_state()
                loaded_adventure.save_game(load_path)

                game.character_name = "DefaultBeforeLoad"
                game.world_state["inventory"].append("Default-only item")
                default.recent_dm_narrations[:] = ["Default-only narration"]
                default.messages.append(
                    {"role": "user", "content": "Default-only message"}
                )
                default.roll_d20()
                for index, session in enumerate(explicit_sessions, start=1):
                    session.character["name"] = f"ExplicitAdventure{index}"
                    session.world_state["inventory"].append(f"Adventure {index} item")
                    session.recent_dm_narrations.append(
                        f"Adventure {index} narration"
                    )
                    session.messages.append(
                        {"role": "user", "content": f"Adventure {index} message"}
                    )
                    session.roll_stat()

                held_references = [
                    (
                        session.world_state,
                        session.character,
                        session.recent_dm_narrations,
                        session.messages,
                        session.rng,
                    )
                    for session in sessions
                ]
                snapshots = [session.serialize_game_state() for session in sessions]
                message_histories = [
                    copy.deepcopy(session.messages) for session in sessions
                ]
                rng_states = [session.rng.getstate() for session in sessions]

                loaded = game.load_game(load_path)

                self.assertEqual(loaded, expected_loaded_state)
                self.assertEqual(game.serialize_game_state(), expected_loaded_state)
                self.assertEqual(
                    default.recent_dm_narrations,
                    ["Narration from saved adventure"],
                )
                self.assertIs(game.world_state, held_references[0][0])
                for index, (session, references, history, rng_state) in enumerate(
                    zip(sessions, held_references, message_histories, rng_states)
                ):
                    with self.subTest(session=index):
                        self.assertIs(session.world_state, references[0])
                        self.assertIs(session.character, references[1])
                        self.assertIs(session.recent_dm_narrations, references[2])
                        self.assertIs(session.messages, references[3])
                        self.assertIs(session.rng, references[4])
                        self.assertEqual(session.messages, history)
                        self.assertEqual(session.rng.getstate(), rng_state)
                        if session is not default:
                            self.assertEqual(
                                session.serialize_game_state(), snapshots[index]
                            )
            finally:
                game.load_game(restore_path)
                default.messages[:] = original_default_messages
                default.rng.setstate(original_default_rng_state)

    def test_exec_namespace_scalars_are_not_a_state_input(self):
        namespace = {"__name__": "isolated_engine", "__file__": game.__file__}
        exec(compile(Path(game.__file__).read_text(encoding="utf-8"), game.__file__, "exec"),
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
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, game.__file__], input="2\nzar at\nexit\n",
            text=True, capture_output=True, timeout=15, encoding="utf-8", env=env
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D20 sonucu:", result.stdout)
        self.assertIn("Oyun kapatılıyor...", result.stdout)


if __name__ == "__main__":
    unittest.main()
