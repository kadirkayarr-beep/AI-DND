import os
"""Offline contracts for independent adventures and the legacy default adapter."""
import ast
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

    def test_overlapping_invalid_cover_does_not_disrupt_valid_attack(self):
        # Exercise both validation branches: unknown values and invalid shapes.
        # Swap owners so rejection is not tied to one campaign's identity.
        for invalid_cover in ("unknown", ["half", "unknown"], {"half": True}, None):
            for valid_index in (0, 1):
                with self.subTest(invalid_cover=invalid_cover, valid_index=valid_index):
                    sessions = [game.create_session(seed=17),
                                game.create_session(seed=17)]
                    enemies = [self.npc(session) for session in sessions]
                    self.assertEqual(enemies[0]["id"], enemies[1]["id"])
                    valid, invalid = sessions[valid_index], sessions[1 - valid_index]
                    valid_enemy = enemies[valid_index]
                    invalid_enemy = enemies[1 - valid_index]
                    for session, enemy in zip(sessions, enemies):
                        session.character.update(armor_class=10, current_hp=19)
                        enemy.update(attack_bonus=0, damage_die=6,
                                     damage_dice=1, damage_modifier=2)
                        pairs = session.world_state["attack_environment"]["pairs"]
                        pairs[f"{enemy['id']}|player"]["cover"] = (
                            ["none", "half"] if session is valid
                            else copy.deepcopy(invalid_cover)
                        )
                        # A legal reverse entry cannot repair invalid forward cover.
                        pairs[f"player|{enemy['id']}"]["cover"] = "none"
                        self.assertEqual(
                            pairs[f"{enemy['id']}|player"]["distance_ft"], 5
                        )
                    before_valid = valid.serialize_game_state()
                    before_invalid = invalid.serialize_game_state()
                    rng_valid, rng_invalid = valid.rng.getstate(), invalid.rng.getstate()
                    rng_default = game._DEFAULT_SESSION.rng.getstate()
                    valid_waiting = threading.Event()
                    rejection_finished = threading.Event()
                    roll_d20 = valid.roll_d20

                    def overlapping_roll():
                        self.assertIs(game._session(), valid)
                        valid_waiting.set()
                        self.assertTrue(rejection_finished.wait(timeout=5))
                        self.assertIs(game._session(), valid)
                        return roll_d20()

                    def reject_invalid_cover():
                        try:
                            self.assertTrue(valid_waiting.wait(timeout=5))
                            with self.assertRaises(
                                game.combat_lifecycle.CombatRequestError
                            ) as error:
                                game.resolve_enemy_attack(invalid_enemy, session=invalid)
                            self.assertEqual(error.exception.code, "invalid_attack_state")
                            # Neither campaign commits anything while the valid
                            # attack is paused, including an attack result.
                            self.assertEqual(valid.serialize_game_state(), before_valid)
                            self.assertEqual(invalid.serialize_game_state(), before_invalid)
                            self.assertEqual(valid.rng.getstate(), rng_valid)
                            self.assertEqual(invalid.rng.getstate(), rng_invalid)
                            self.assertEqual(game._DEFAULT_SESSION.serialize_game_state(),
                                             self.default_before)
                            self.assertEqual(game._DEFAULT_SESSION.rng.getstate(),
                                             rng_default)
                        finally:
                            rejection_finished.set()

                    with self.rolls(valid, (20, 12), (6, 4)), \
                         self.rolls(invalid), self.rolls(game._DEFAULT_SESSION), \
                         patch.object(valid, "roll_d20", side_effect=overlapping_roll):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            legal = pool.submit(game.resolve_enemy_attack, valid_enemy,
                                                session=valid)
                            rejected = pool.submit(reject_invalid_cover)
                            rejected.result(timeout=10)
                            result = legal.result(timeout=10)

                    # Independent arithmetic: half cover gives AC 10 + 2;
                    # 12 + 0 hits exactly, and d6=4 + 2 deals 6 (19 -> 13).
                    self.assertTrue(result["success"])
                    self.assertEqual(result["outcome"], "hit")
                    self.assertEqual(result["actor_id"], valid_enemy["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["cover_state"], "half")
                    self.assertEqual(result["target_ac_base"], 10)
                    self.assertEqual(result["target_ac"], 12)
                    self.assertEqual(result["attack_rolls"], [12])
                    self.assertEqual(result["attack_total"], 12)
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"], [])
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["damage"], 6)
                    self.assertEqual(result["target_hp_before"], 19)
                    self.assertEqual(result["target_hp_after"], 13)
                    self.assertEqual(result["target_status"], "active")
                    expected_valid = copy.deepcopy(before_valid)
                    expected_valid["player"]["current_hp"] = 13
                    expected_valid["world_state"].setdefault("attack_results", []).append(
                        copy.deepcopy(result)
                    )
                    self.assertEqual(valid.serialize_game_state(), expected_valid)
                    self.assertEqual(invalid.serialize_game_state(), before_invalid)
                    self.assertEqual(valid.rng.getstate(), rng_valid)
                    self.assertEqual(invalid.rng.getstate(), rng_invalid)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

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

    def test_overlapping_attacks_use_reverse_distance_but_not_reverse_visibility(self):
        cases = (
            (False, True, [], ["unseen_target"], [(20, 15), (20, 3)], False),
            (True, False, ["unseen_attacker"], [], [(20, 3), (20, 15)], True),
            (False, False, ["unseen_attacker"], ["unseen_target"], [(20, 15)], True),
        )
        for sees_target, seen_by_target, advantages, disadvantages, dice_b, hit_b in cases:
            with self.subTest(attacker_sees_target=sees_target,
                              target_sees_attacker=seen_by_target):
                self.a = game.create_session(seed=17)
                self.b = game.create_session(seed=17)
                enemies = [self.npc(self.a), self.npc(self.b)]
                self.assertEqual(enemies[0]["id"], enemies[1]["id"])
                for session, enemy in zip((self.a, self.b), enemies):
                    session.character.update(armor_class=10, current_hp=19)
                    enemy.update(attack_bonus=0, damage_die=6,
                                 damage_dice=1, damage_modifier=2)
                    self.assertNotIn("distance_ft", enemy)
                direct = f"{enemies[0]['id']}|player"
                reverse = f"player|{enemies[0]['id']}"
                pairs_a = self.a.world_state["attack_environment"]["pairs"]
                del pairs_a[direct]
                # A has only reverse geometry. Its directional perception
                # flags must not be used for the NPC's attack on the player.
                pairs_a[reverse].update(
                    attacker_sees_target=sees_target,
                    target_sees_attacker=seen_by_target,
                )
                self.b.world_state["attack_environment"]["pairs"][direct].update(
                    attacker_sees_target=sees_target,
                    target_sees_attacker=seen_by_target,
                )
                self.assertNotIn(direct, pairs_a)
                self.assertEqual(pairs_a[reverse]["distance_ft"], 5)
                before_a = self.a.serialize_game_state()
                before_b = self.b.serialize_game_state()
                rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                fallback_waiting = threading.Event()
                directional_finished = threading.Event()
                roll_d20 = self.a.roll_d20

                def overlapping_roll():
                    self.assertIs(game._session(), self.a)
                    fallback_waiting.set()
                    self.assertTrue(directional_finished.wait(timeout=5))
                    self.assertIs(game._session(), self.a)
                    return roll_d20()

                def directional_attack():
                    try:
                        self.assertTrue(fallback_waiting.wait(timeout=5))
                        result = game.resolve_enemy_attack(enemies[1], session=self.b)
                        self.assertEqual(self.a.serialize_game_state(), before_a)
                        self.assertEqual(self.a.rng.getstate(), rng_a)
                        self.assertEqual(game._DEFAULT_SESSION.serialize_game_state(),
                                         self.default_before)
                        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(),
                                         rng_default)
                        return result
                    finally:
                        directional_finished.set()

                expected_b = dice_b + ([(6, 2)] if hit_b else [])
                with self.rolls(self.a, (20, 15), (6, 4)), \
                     self.rolls(self.b, *expected_b), \
                     self.rolls(game._DEFAULT_SESSION), \
                     patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        fallback = pool.submit(game.resolve_enemy_attack, enemies[0],
                                               session=self.a)
                        directional = pool.submit(directional_attack)
                        result_b = directional.result(timeout=10)
                        result_a = fallback.result(timeout=10)

                for result in (result_a, result_b):
                    self.assertEqual(result["actor_id"], enemies[0]["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["target_ac"], 10)
                    self.assertEqual(result["target_hp_before"], 19)
                    self.assertEqual(result["target_status"], "active")
                    self.assertFalse(result["critical"])
                self.assertTrue(result_a["success"])
                self.assertEqual(result_a["outcome"], "hit")
                self.assertEqual(result_a["attack_rolls"], [15])
                self.assertEqual(result_a["attack_roll"], 15)
                self.assertEqual(result_a["advantage_sources"], [])
                self.assertEqual(result_a["disadvantage_sources"], [])
                self.assertFalse(result_a["disadvantage"])
                self.assertFalse(result_a["resolution"]["advantage"])
                self.assertFalse(result_a["resolution"]["advantage_cancelled"])
                self.assertEqual(result_a["damage"], 6)
                self.assertEqual(result_a["damage_rolls"], [
                    {"source": "weapon", "die": 6, "count": 1, "rolls": [4]},
                ])
                self.assertEqual(result_a["target_hp_after"], 13)
                self.assertEqual(result_b["success"], hit_b)
                self.assertEqual(result_b["outcome"], "hit" if hit_b else "miss")
                self.assertEqual(result_b["attack_rolls"], [v for _, v in dice_b])
                self.assertEqual(result_b["attack_roll"], 15 if hit_b else 3)
                self.assertEqual(result_b["advantage_sources"], advantages)
                self.assertEqual(result_b["disadvantage_sources"], disadvantages)
                self.assertEqual(result_b["disadvantage"],
                                 bool(disadvantages) and not advantages)
                self.assertEqual(result_b["resolution"]["advantage"], bool(advantages))
                self.assertEqual(result_b["resolution"]["advantage_cancelled"],
                                 bool(advantages and disadvantages))
                self.assertEqual(result_b["damage"], 4 if hit_b else 0)
                self.assertEqual(result_b["damage_rolls"], [
                    {"source": "weapon", "die": 6, "count": 1, "rolls": [2]},
                ] if hit_b else [])
                self.assertEqual(result_b["target_hp_after"], 15 if hit_b else 19)
                # Preserve every field, including reverse visibility; only
                # owning HP and the owning attack receipt may change.
                before_a["player"]["current_hp"] = 13
                before_b["player"]["current_hp"] = 15 if hit_b else 19
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

    def test_overlapping_hits_keep_damage_protection_in_their_own_sessions(self):
        # Odd raw damage (5 + 2 = 7) distinguishes unprotected damage, resistance
        # rounding down to 3, and immunity to 0. Swap owners so neither campaign
        # can hide leakage by always being the protected/default defender.
        protections = {
            "none": ([], [], 7, 12),
            "resistant": (["slashing"], [], 3, 16),
            "immune": ([], ["slashing"], 0, 19),
        }
        cases = [
            ("none", "resistant"), ("resistant", "none"),
            ("none", "immune"), ("immune", "none"),
            ("resistant", "immune"), ("immune", "resistant"),
        ]
        for protection_a, protection_b in cases:
            with self.subTest(protection_a=protection_a, protection_b=protection_b):
                sessions = (game.create_session(seed=17),
                            game.create_session(seed=17))
                enemies = [self.npc(session) for session in sessions]
                self.assertEqual(enemies[0]["id"], enemies[1]["id"])
                for session, enemy, protection in zip(
                    sessions, enemies, (protection_a, protection_b)
                ):
                    resistances, immunities, _, _ = protections[protection]
                    session.character.update(
                        armor_class=10, current_hp=19,
                        resistances=list(resistances), immunities=list(immunities),
                        vulnerabilities=[],
                    )
                    enemy.update(attack_bonus=0, damage_die=6,
                                 damage_dice=1, damage_modifier=2)
                self.assertEqual(sessions[0].world_state["attack_environment"],
                                 sessions[1].world_state["attack_environment"])
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                attack_barrier = threading.Barrier(2)
                damage_barrier = threading.Barrier(2)
                # Rendezvous again on damage, immediately before mitigation.
                # No dice or mitigation/HP owners are bypassed.
                with self.rolls(sessions[0], (20, 15), (6, 5),
                                barrier=attack_barrier,
                                damage_barrier=damage_barrier), \
                     self.rolls(sessions[1], (20, 15), (6, 5),
                                barrier=attack_barrier,
                                damage_barrier=damage_barrier), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [
                            pool.submit(game.resolve_enemy_attack, enemy,
                                        session=session)
                            for session, enemy in zip(sessions, enemies)
                        ]
                        results = [future.result(timeout=10) for future in futures]
                for session, enemy, protection, result, expected, rng in zip(
                    sessions, enemies, (protection_a, protection_b),
                    results, before, rng_before
                ):
                    resistances, immunities, damage, hp_after = protections[protection]
                    self.assertEqual(result["actor_id"], enemy["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["attack_rolls"], [15])
                    self.assertEqual(result["attack_total"], 15)
                    self.assertEqual(result["target_ac"], 10)
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"], [])
                    self.assertFalse(result["critical"])
                    self.assertTrue(result["hit"])
                    self.assertTrue(result["success"])
                    self.assertEqual(result["outcome"], "hit")
                    self.assertEqual(result["damage_type"], "slashing")
                    self.assertEqual(result["raw_damage"], 7)
                    self.assertEqual(result["damage_rolls"], [
                        {"source": "weapon", "die": 6, "count": 1, "rolls": [5]},
                    ])
                    self.assertEqual(result["damage_instances"], [{
                        "damage_type": "slashing", "raw_damage": 7,
                        "pre_resistance_damage": 7, "flat_reduction": 0,
                        "resistance_applied": bool(resistances),
                        "immunity_applied": bool(immunities),
                        "vulnerability_applied": False, "final_damage": damage,
                    }])
                    self.assertEqual(result["damage"], damage)
                    self.assertEqual(result["hp_damage"], damage)
                    self.assertEqual(result["target_hp_before"], 19)
                    self.assertEqual(result["target_hp_after"], hp_after)
                    self.assertEqual(result["target_status"], "active")
                    self.assertEqual(session.character["current_hp"], hp_after)
                    # Include the legitimate owned result record, but no other
                    # state changes beyond independently calculated player HP.
                    expected["player"]["current_hp"] = hp_after
                    expected["world_state"].setdefault("attack_results", []).append(
                        copy.deepcopy(result)
                    )
                    self.assertEqual(session.serialize_game_state(), expected)
                    self.assertEqual(session.rng.getstate(), rng)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)

    def test_overlapping_attack_cannot_borrow_another_sessions_guessed_location(self):
        enemies = [self.npc(self.a), self.npc(self.b)]
        self.assertEqual(enemies[0]["id"], enemies[1]["id"])
        for session, enemy, correct in zip(
                (self.a, self.b), enemies, (True, False)):
            session.character.update(armor_class=10, current_hp=19)
            enemy.update(attack_bonus=0, damage_die=6,
                         damage_dice=1, damage_modifier=2)
            session.world_state["attack_environment"]["pairs"][
                f"{enemy['id']}|player"
            ]["guessed_location_correct"] = correct
        # Both campaigns have the same known distance and visible target.
        # Only B guesses the wrong location; its natural 20 must still miss.
        before_a = self.a.serialize_game_state()
        before_b = self.b.serialize_game_state()
        rng_a, rng_b = self.a.rng.getstate(), self.b.rng.getstate()
        rng_default = game._DEFAULT_SESSION.rng.getstate()
        valid_attack_waiting = threading.Event()
        wrong_location_attack_finished = threading.Event()
        roll_d20 = self.a.roll_d20

        def overlapping_roll():
            self.assertIs(game._session(), self.a)
            valid_attack_waiting.set()
            self.assertTrue(wrong_location_attack_finished.wait(timeout=5))
            self.assertIs(game._session(), self.a)
            return roll_d20()

        def wrong_location_attack():
            try:
                self.assertTrue(valid_attack_waiting.wait(timeout=5))
                result = game.resolve_enemy_attack(enemies[1], session=self.b)
                # B commits its miss while A is still inside its attack.
                self.assertEqual(self.a.serialize_game_state(), before_a)
                self.assertEqual(self.a.rng.getstate(), rng_a)
                return result
            finally:
                wrong_location_attack_finished.set()

        with self.rolls(self.a, (20, 15), (6, 4)), \
             self.rolls(self.b, (20, 20)), \
             self.rolls(game._DEFAULT_SESSION), \
             patch.object(self.a, "roll_d20", side_effect=overlapping_roll):
            with ThreadPoolExecutor(max_workers=2) as pool:
                valid = pool.submit(game.resolve_enemy_attack, enemies[0],
                                    session=self.a)
                wrong_location = pool.submit(wrong_location_attack)
                result_b = wrong_location.result(timeout=10)
                result_a = valid.result(timeout=10)

        for result in (result_a, result_b):
            self.assertEqual(result["actor_id"], enemies[0]["id"])
            self.assertEqual(result["target_id"], "player")
            self.assertEqual(result["target_ac"], 10)
            self.assertEqual(result["target_hp_before"], 19)
            self.assertEqual(result["target_status"], "active")
            self.assertEqual(result["advantage_sources"], [])
            self.assertEqual(result["disadvantage_sources"], [])
            self.assertFalse(result["critical"])
        self.assertTrue(result_a["success"])
        self.assertTrue(result_a["hit"])
        self.assertEqual(result_a["outcome"], "hit")
        self.assertEqual(result_a["attack_rolls"], [15])
        self.assertEqual(result_a["attack_roll"], 15)
        self.assertEqual(result_a["damage_rolls"], [
            {"source": "weapon", "die": 6, "count": 1, "rolls": [4]}
        ])
        self.assertEqual(result_a["damage"], 6)
        self.assertEqual(result_a["target_hp_after"], 13)
        self.assertFalse(result_b["success"])
        self.assertFalse(result_b["hit"])
        self.assertEqual(result_b["outcome"], "miss")
        self.assertEqual(result_b["attack_rolls"], [20])
        self.assertEqual(result_b["attack_roll"], 20)
        self.assertTrue(result_b["natural_20"])
        self.assertEqual(result_b["damage_rolls"], [])
        self.assertEqual(result_b["damage"], 0)
        self.assertEqual(result_b["target_hp_after"], 19)
        # Both legal attacks record their own result, but only A loses HP.
        # Whole snapshots also preserve the distinct location guesses.
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

    def test_overlapping_short_rests_recharge_only_their_own_orc(self):
        for first_index in (0, 1):
            with self.subTest(first_index=first_index):
                sessions = [game.create_session(seed=17),
                            game.create_session(seed=29)]
                fixtures = [(2, 0, 7), (3, 2, 11)]
                for session, (maximum, uses, reserve) in zip(sessions, fixtures):
                    session.world_state["location"] = "tavern"
                    session.character.update(
                        species="Orc", race="Orc",
                        level=1 if maximum == 2 else 5,
                        proficiency_bonus=maximum, current_hp=13, max_hp=19,
                    )
                    game.initialize_species_trait_state(session=session)
                    session.character["species_trait_state"].update(
                        adrenaline_rush_uses_remaining=uses,
                        temporary_hit_points=reserve,
                        movement_budget_ft=60,
                        movement_effect="adrenaline_rush",
                    )
                    game.ensure_campaign_clock(session=session)
                    game.ensure_death_state(session=session)
                    game.ensure_combat_state(session=session)
                before = [session.serialize_game_state() for session in sessions]
                expected = copy.deepcopy(before)
                for snapshot, (maximum, _, _) in zip(expected, fixtures):
                    state = snapshot["player"]["species_trait_state"]
                    state.update(
                        adrenaline_rush_uses_remaining=maximum,
                        movement_budget_ft=0, movement_effect=None,
                    )
                    # Compute only the legitimate clock delta, not recharge,
                    # through the time owner on a detached expected world.
                    world = snapshot["world_state"]
                    game.campaign_time.advance(
                        world, 3600, "short_rest",
                        f"turn:{world.get('flags', {}).get('turn_index', 0)}",
                    )
                rng_before = [session.rng.getstate() for session in sessions]
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                rng_module = random.getstate()
                default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                messages_before = [copy.deepcopy(session.messages)
                                   for session in sessions]
                first, waiting = sessions[first_index], sessions[1 - first_index]
                waiting_entered = threading.Event()
                release_waiting = threading.Event()
                time_owner = game.advance_campaign_time

                def overlapping_time(*args, **kwargs):
                    owner = game._session()
                    self.assertTrue(any(owner is session for session in sessions))
                    if owner is waiting:
                        waiting_entered.set()
                        self.assertTrue(release_waiting.wait(timeout=5))
                    else:
                        self.assertTrue(waiting_entered.wait(timeout=5))
                    self.assertIs(game._session(), owner)
                    result = time_owner(*args, **kwargs)
                    self.assertIs(game._session(), owner)
                    return result

                def assert_preserved():
                    for session, rng, messages in zip(
                        sessions, rng_before, messages_before
                    ):
                        self.assertEqual(session.rng.getstate(), rng)
                        self.assertEqual(session.messages, messages)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                    self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                    self.assertEqual(random.getstate(), rng_module)

                with patch.object(game, "advance_campaign_time",
                                  side_effect=overlapping_time), \
                     self.rolls(first), self.rolls(waiting), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        waiting_future = pool.submit(
                            game.resolve_species_trait_action,
                            "short_rest", session=waiting,
                        )
                        first_future = pool.submit(
                            game.resolve_species_trait_action,
                            "short_rest", session=first,
                        )
                        try:
                            first_result = first_future.result(timeout=10)
                            self.assertEqual(
                                first.serialize_game_state(), expected[first_index]
                            )
                            self.assertEqual(
                                waiting.serialize_game_state(), before[1 - first_index]
                            )
                            assert_preserved()
                        finally:
                            release_waiting.set()
                        waiting_result = waiting_future.result(timeout=10)

                for index, result in (
                    (first_index, first_result),
                    (1 - first_index, waiting_result),
                ):
                    maximum, uses, reserve = fixtures[index]
                    self.assertEqual(result["action"], "short_rest")
                    self.assertEqual(
                        result["effects"]["adrenaline_rush_uses_refreshed"],
                        maximum - uses,
                    )
                    self.assertEqual(result["effects"]["time_result"]["elapsed_seconds"],
                                     3600)
                    self.assertFalse(result["effects"]["time_result"]["interrupted"])
                    self.assertEqual(
                        sessions[index].character["species_trait_state"][
                            "temporary_hit_points"
                        ], reserve,
                    )
                    self.assertEqual(sessions[index].serialize_game_state(),
                                     expected[index])
                assert_preserved()

    def test_overlapping_interrupted_rest_cannot_recharge_another_campaign(self):
        import scheduled_events

        for interrupted_index in (0, 1):
            for first_index in (0, 1):
                with self.subTest(interrupted_index=interrupted_index,
                                  first_index=first_index):
                    sessions = [game.create_session(seed=17),
                                game.create_session(seed=29)]
                    fixtures = [(2, 0, 7), (3, 1, 11)]
                    for session, (maximum, uses, reserve) in zip(sessions, fixtures):
                        session.world_state["location"] = "tavern"
                        session.character.update(
                            species="Orc", race="Orc",
                            level=1 if maximum == 2 else 5,
                            proficiency_bonus=maximum, current_hp=13, max_hp=19,
                        )
                        game.initialize_species_trait_state(session=session)
                        session.character["species_trait_state"].update(
                            adrenaline_rush_uses_remaining=uses,
                            temporary_hit_points=reserve,
                            movement_budget_ft=60,
                            movement_effect="adrenaline_rush",
                        )
                        game.ensure_campaign_clock(session=session)
                        game.ensure_death_state(session=session)
                        game.ensure_combat_state(session=session)
                    interrupted = sessions[interrupted_index]
                    encounter = scheduled_events.register_event(
                        interrupted.world_state, event_id="rest-stop",
                        window_start=1200, window_end=1800,
                        location_id="tavern", behavior="INTERRUPTIVE",
                        requires_decision=True, summary="A visitor needs a decision.",
                        effects=[{"kind": "flag", "key": "scheduled:rest_encounter",
                                  "value": True}],
                    )
                    before = [session.serialize_game_state() for session in sessions]
                    characters_before = [copy.deepcopy(session.character)
                                         for session in sessions]
                    expected = copy.deepcopy(before)
                    for index, snapshot in enumerate(expected):
                        # Resolve legitimate clock/encounter changes on detached
                        # worlds. Never obtain expected recharge from the action.
                        world = snapshot["world_state"]
                        game.campaign_time.advance(
                            world, 3600, "short_rest",
                            f"turn:{world.get('flags', {}).get('turn_index', 0)}",
                        )
                        if index != interrupted_index:
                            snapshot["player"]["species_trait_state"].update(
                                adrenaline_rush_uses_remaining=fixtures[index][0],
                                movement_budget_ft=0, movement_effect=None,
                            )
                    rng_before = [session.rng.getstate() for session in sessions]
                    rng_default = game._DEFAULT_SESSION.rng.getstate()
                    rng_module = random.getstate()
                    messages_before = [copy.deepcopy(session.messages)
                                       for session in sessions]
                    default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                    first, waiting = sessions[first_index], sessions[1 - first_index]
                    waiting_entered = threading.Event()
                    release_waiting = threading.Event()
                    time_owner = game.advance_campaign_time

                    def overlapping_time(*args, **kwargs):
                        owner = game._session()
                        self.assertTrue(any(owner is session for session in sessions))
                        if owner is waiting:
                            waiting_entered.set()
                            self.assertTrue(release_waiting.wait(timeout=5))
                        else:
                            self.assertTrue(waiting_entered.wait(timeout=5))
                        self.assertIs(game._session(), owner)
                        result = time_owner(*args, **kwargs)
                        self.assertIs(game._session(), owner)
                        return result

                    def assert_preserved():
                        for session, rng, messages in zip(
                            sessions, rng_before, messages_before
                        ):
                            self.assertEqual(session.rng.getstate(), rng)
                            self.assertEqual(session.messages, messages)
                        self.assertEqual(game.serialize_game_state(), self.default_before)
                        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                        self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                        self.assertEqual(random.getstate(), rng_module)

                    results = {}
                    with patch.object(game, "advance_campaign_time",
                                      side_effect=overlapping_time), \
                         self.rolls(first), self.rolls(waiting), \
                         self.rolls(game._DEFAULT_SESSION):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            waiting_future = pool.submit(
                                game.resolve_species_trait_action,
                                "short_rest", session=waiting,
                            )
                            first_future = pool.submit(
                                game.resolve_species_trait_action,
                                "short_rest", session=first,
                            )
                            try:
                                results[first_index] = first_future.result(timeout=10)
                                self.assertEqual(first.serialize_game_state(),
                                                 expected[first_index])
                                self.assertEqual(waiting.serialize_game_state(),
                                                 before[1 - first_index])
                                assert_preserved()
                            finally:
                                release_waiting.set()
                            results[1 - first_index] = waiting_future.result(timeout=10)

                    for index, session in enumerate(sessions):
                        result = results[index]
                        self.assertEqual(result["action"], "short_rest")
                        effects = result["effects"]
                        time_result = effects["time_result"]
                        stopped = index == interrupted_index
                        self.assertEqual(time_result["interrupted"], stopped)
                        self.assertEqual(time_result["requested_seconds"], 3600)
                        self.assertEqual(time_result["elapsed_seconds"],
                                         1200 if stopped else 3600)
                        self.assertEqual(time_result["remaining_seconds"],
                                         2400 if stopped else 0)
                        state = session.character["species_trait_state"]
                        maximum, uses, reserve = fixtures[index]
                        self.assertEqual(state["temporary_hit_points"], reserve)
                        if stopped:
                            self.assertFalse(effects["rest_completed"])
                            self.assertNotIn("adrenaline_rush_uses_refreshed", effects)
                            self.assertEqual(state["adrenaline_rush_uses_remaining"], uses)
                            self.assertEqual(session.character, characters_before[index])
                        else:
                            self.assertEqual(effects["adrenaline_rush_uses_refreshed"],
                                             maximum - uses)
                            self.assertEqual(state["adrenaline_rush_uses_remaining"],
                                             maximum)
                            self.assertEqual(time_result["player_known_events"], [])
                            self.assertNotIn("scheduled:rest_encounter",
                                             session.world_state["flags"])
                        self.assertEqual(session.serialize_game_state(), expected[index])
                    self.assertEqual(encounter["status"], "OCCURRED")
                    self.assertEqual(encounter["decision_status"], "PENDING")
                    self.assertEqual(encounter["encounter_status"], "OBSERVED")
                    self.assertTrue(encounter["player_observed"])
                    self.assertEqual(encounter["canonical_result"]["resolved_at"], 1200)
                    self.assertTrue(
                        interrupted.world_state["flags"]["scheduled:rest_encounter"]
                    )
                    assert_preserved()

    def test_overlapping_interrupted_long_rest_keeps_healing_and_spells_session_owned(self):
        import spell_scope
        from api.tests.test_campaign_time import scene
        from api.tests.test_campaign_time_edges import event, flag

        for interrupted_index in (0, 1):
            for first_index in (0, 1):
                with self.subTest(interrupted_index=interrupted_index,
                                  first_index=first_index):
                    sessions = [scene(), scene()]
                    fixtures = [("Wizard", 7, 19, 0, 17),
                                ("Cleric", 13, 27, 1, 29)]
                    for session, (cls, hp, maximum, slots, seed) in zip(
                        sessions, fixtures
                    ):
                        session.rng.seed(seed)
                        session.character.update(
                            species="Human", race="Human", level=1,
                            proficiency_bonus=2, current_hp=hp, max_hp=maximum,
                            **{"class": cls},
                        )
                        game.initialize_species_trait_state(session=session)
                        spell_scope.initialize(session)
                        session.world_state["spellcasting_v1"]["slots"]["1"] = slots
                        # A rest must not erase the existing slot-turn receipt.
                        session.world_state["spellcasting_v1"]["slot_turn"] = [
                            f"combat-{cls}", 1, 1,
                        ]
                        game.ensure_death_state(session=session)
                        game.ensure_combat_state(session=session)
                    interrupted = sessions[interrupted_index]
                    encounter = event(
                        interrupted, "long-rest-stop", 1200, 1800,
                        behavior="INTERRUPTIVE", requires_decision=True,
                        summary="A visitor needs a decision.",
                        effects=[flag("long_rest_encounter")],
                    )
                    before = [session.serialize_game_state() for session in sessions]
                    characters_before = [copy.deepcopy(session.character)
                                         for session in sessions]
                    expected = copy.deepcopy(before)
                    for index, snapshot in enumerate(expected):
                        world = snapshot["world_state"]
                        # Compute only clock/event changes on detached worlds;
                        # healing and slots have explicit, independent expectations.
                        game.campaign_time.advance(
                            world, 8 * 3600, "long_rest",
                            f"turn:{world.get('flags', {}).get('turn_index', 0)}",
                        )
                        if index != interrupted_index:
                            snapshot["player"]["current_hp"] = fixtures[index][2]
                            world["spellcasting_v1"]["slots"] = copy.deepcopy(
                                spell_scope.CLASS_DEFINITIONS[fixtures[index][0]][
                                    "spell_slots"
                                ]
                            )
                    rng_before = [session.rng.getstate() for session in sessions]
                    messages_before = [copy.deepcopy(session.messages)
                                       for session in sessions]
                    default_rng = game._DEFAULT_SESSION.rng.getstate()
                    default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                    module_rng = random.getstate()
                    self.assertIsNot(sessions[0].rng, sessions[1].rng)
                    self.assertNotEqual(rng_before[0], rng_before[1])
                    first, waiting = sessions[first_index], sessions[1 - first_index]
                    waiting_entered = threading.Event()
                    release_waiting = threading.Event()
                    time_owner = game.advance_campaign_time

                    def overlapping_time(*args, **kwargs):
                        owner = game._session()
                        self.assertTrue(any(owner is session for session in sessions))
                        if owner is waiting:
                            waiting_entered.set()
                            self.assertTrue(release_waiting.wait(timeout=5))
                        else:
                            self.assertTrue(waiting_entered.wait(timeout=5))
                        self.assertIs(game._session(), owner)
                        result = time_owner(*args, **kwargs)
                        self.assertIs(game._session(), owner)
                        return result

                    def assert_preserved():
                        for session, rng, messages in zip(
                            sessions, rng_before, messages_before
                        ):
                            self.assertEqual(session.rng.getstate(), rng)
                            self.assertEqual(session.messages, messages)
                        self.assertEqual(game.serialize_game_state(), self.default_before)
                        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), default_rng)
                        self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                        self.assertEqual(random.getstate(), module_rng)

                    results = {}
                    with patch.object(game, "advance_campaign_time",
                                      side_effect=overlapping_time), \
                         self.rolls(first), self.rolls(waiting), \
                         self.rolls(game._DEFAULT_SESSION):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            waiting_future = pool.submit(
                                game.resolve_species_trait_action,
                                "long_rest", session=waiting,
                            )
                            first_future = pool.submit(
                                game.resolve_species_trait_action,
                                "long_rest", session=first,
                            )
                            try:
                                results[first_index] = first_future.result(timeout=10)
                                self.assertEqual(first.serialize_game_state(),
                                                 expected[first_index])
                                self.assertEqual(waiting.serialize_game_state(),
                                                 before[1 - first_index])
                                assert_preserved()
                            finally:
                                release_waiting.set()
                            results[1 - first_index] = waiting_future.result(timeout=10)

                    for index, session in enumerate(sessions):
                        result = results[index]
                        stopped = index == interrupted_index
                        self.assertEqual(result["action"], "long_rest")
                        effects = result["effects"]
                        time_result = effects["time_result"]
                        self.assertEqual(time_result["interrupted"], stopped)
                        self.assertEqual(time_result["requested_seconds"], 28800)
                        self.assertEqual(time_result["elapsed_seconds"],
                                         1200 if stopped else 28800)
                        self.assertEqual(time_result["remaining_seconds"],
                                         27600 if stopped else 0)
                        self.assertEqual(
                            session.character["current_hp"],
                            fixtures[index][1] if stopped else fixtures[index][2],
                        )
                        if stopped:
                            self.assertFalse(effects["rest_completed"])
                            self.assertNotIn("current_hp", effects)
                            self.assertNotIn("refreshed", effects)
                            self.assertEqual(session.character, characters_before[index])
                            self.assertEqual(
                                session.world_state["spellcasting_v1"],
                                before[index]["world_state"]["spellcasting_v1"],
                            )
                        else:
                            self.assertEqual(effects["current_hp"], fixtures[index][2])
                            self.assertEqual(
                                session.world_state["spellcasting_v1"]["slots"],
                                spell_scope.CLASS_DEFINITIONS[fixtures[index][0]][
                                    "spell_slots"
                                ],
                            )
                            self.assertEqual(time_result["player_known_events"], [])
                            self.assertNotIn("scheduled:long_rest_encounter",
                                             session.world_state["flags"])
                        self.assertEqual(session.serialize_game_state(), expected[index])
                    self.assertEqual(encounter["status"], "OCCURRED")
                    self.assertEqual(encounter["decision_status"], "PENDING")
                    self.assertEqual(encounter["encounter_status"], "OBSERVED")
                    self.assertTrue(encounter["player_observed"])
                    self.assertEqual(encounter["canonical_result"]["resolved_at"], 1200)
                    self.assertTrue(
                        interrupted.world_state["flags"]["scheduled:long_rest_encounter"]
                    )
                    assert_preserved()

    def test_overlapping_adrenaline_rush_grants_and_absorption_stay_session_owned(self):
        # Different proficiency bonuses and uses expose a borrowed character
        # or trait state. Reverse the fixtures to avoid depending on call order.
        for reserves in ((0, 1), (2, 3)):
            for reverse in (False, True):
                with self.subTest(reserves=reserves, reverse=reverse):
                    sessions = (game.create_session(seed=17),
                                game.create_session(seed=17))
                    fixtures = [(2, 1, reserves[0], 1, 1, 19),
                                (3, 2, reserves[1], 4, 0, 18)]
                    if reverse:
                        fixtures.reverse()
                    enemies = [self.npc(session) for session in sessions]
                    for session, enemy, fixture in zip(sessions, enemies, fixtures):
                        proficiency, uses, reserve, _, _, _ = fixture
                        session.character.update(
                            species="Orc", race="Orc",
                            level=1 if proficiency == 2 else 5,
                            proficiency_bonus=proficiency, speed_ft=30,
                            armor_class=10, current_hp=19, max_hp=19,
                            resistances=[], immunities=[], vulnerabilities=[],
                        )
                        game.initialize_species_trait_state(session=session)
                        session.character["species_trait_state"].update(
                            temporary_hit_points=reserve,
                            adrenaline_rush_uses_remaining=uses,
                        )
                        enemy.update(attack_bonus=0, damage_die=6,
                                     damage_dice=1, damage_modifier=0)
                    before = [session.serialize_game_state() for session in sessions]
                    rng_before = [session.rng.getstate() for session in sessions]
                    rng_default = game._DEFAULT_SESSION.rng.getstate()
                    rng_module = random.getstate()
                    default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                    grant_barrier = threading.Barrier(2)
                    bonus_action_owner = game._species_bonus_action

                    def overlapping_bonus_action():
                        # Pause after the real ability owner has bound its
                        # character/state and before it decrements uses/grants HP.
                        owner = game._session()
                        self.assertTrue(any(owner is session for session in sessions))
                        grant_barrier.wait(timeout=5)
                        self.assertIs(game._session(), owner)
                        result = bonus_action_owner()
                        grant_barrier.wait(timeout=5)
                        self.assertIs(game._session(), owner)
                        return result

                    with patch.object(game, "_species_bonus_action",
                                      side_effect=overlapping_bonus_action), \
                         self.rolls(sessions[0]), self.rolls(sessions[1]), \
                         self.rolls(game._DEFAULT_SESSION):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [
                                pool.submit(game.resolve_species_trait_action,
                                            "adrenaline_rush", session=session)
                                for session in sessions
                            ]
                            grants = [future.result(timeout=10) for future in futures]
                    for session, fixture, grant, expected, rng in zip(
                        sessions, fixtures, grants, before, rng_before
                    ):
                        proficiency, uses, _, _, _, _ = fixture
                        self.assertEqual(grant["action"], "adrenaline_rush")
                        self.assertEqual(grant["effects"], {
                            "temporary_hit_points": proficiency,
                            "dash_distance_ft": 60,
                        })
                        state = expected["player"]["species_trait_state"]
                        state.update(
                            temporary_hit_points=proficiency,
                            adrenaline_rush_uses_remaining=uses - 1,
                            movement_budget_ft=60,
                            movement_effect={"kind": "dash", "distance_ft": 60},
                        )
                        self.assertEqual(session.serialize_game_state(), expected)
                        self.assertEqual(session.rng.getstate(), rng)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                    self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                    self.assertEqual(random.getstate(), rng_module)

                    attack_barrier = threading.Barrier(2)
                    damage_barrier = threading.Barrier(2)
                    with self.rolls(sessions[0], (20, 15), (6, fixtures[0][3]),
                                    barrier=attack_barrier,
                                    damage_barrier=damage_barrier), \
                         self.rolls(sessions[1], (20, 15), (6, fixtures[1][3]),
                                    barrier=attack_barrier,
                                    damage_barrier=damage_barrier), \
                         self.rolls(game._DEFAULT_SESSION):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [
                                pool.submit(game.resolve_enemy_attack, enemy,
                                            session=session)
                                for session, enemy in zip(sessions, enemies)
                            ]
                            attacks = [future.result(timeout=10) for future in futures]
                    for session, fixture, attack, expected, rng in zip(
                        sessions, fixtures, attacks, before, rng_before
                    ):
                        proficiency, uses, _, damage, remaining, hp_after = fixture
                        self.assertTrue(attack["hit"])
                        self.assertEqual(attack["damage"], damage)
                        self.assertEqual(attack["temporary_hp_before"], proficiency)
                        self.assertEqual(attack["temporary_hp_absorbed"],
                                         1 if proficiency == 2 else 3)
                        self.assertEqual(attack["temporary_hp_after"], remaining)
                        self.assertEqual(attack["hp_damage"], 19 - hp_after)
                        self.assertEqual(attack["target_hp_after"], hp_after)
                        self.assertEqual(
                            session.character["species_trait_state"][
                                "adrenaline_rush_uses_remaining"
                            ], uses - 1,
                        )
                        expected["player"]["current_hp"] = hp_after
                        expected["player"]["species_trait_state"][
                            "temporary_hit_points"
                        ] = remaining
                        expected["world_state"].setdefault("attack_results", []).append(
                            copy.deepcopy(attack)
                        )
                        self.assertEqual(session.serialize_game_state(), expected)
                        self.assertEqual(session.rng.getstate(), rng)
                    self.assertIs(game._session(), game._DEFAULT_SESSION)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                    self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                    self.assertEqual(random.getstate(), rng_module)

    def test_overlapping_exhausted_adrenaline_rush_cannot_borrow_another_sessions_uses(self):
        for eligible_index in (0, 1):
            with self.subTest(eligible_index=eligible_index):
                sessions = (game.create_session(seed=17),
                            game.create_session(seed=29))
                eligible = sessions[eligible_index]
                exhausted = sessions[1 - eligible_index]
                for session in sessions:
                    can_activate = session is eligible
                    session.character.update(
                        species="Orc", race="Orc",
                        level=5 if can_activate else 1,
                        proficiency_bonus=3 if can_activate else 2,
                        current_hp=18 if can_activate else 11, max_hp=19,
                    )
                    game.initialize_species_trait_state(session=session)
                    session.character["species_trait_state"].update(
                        adrenaline_rush_uses_remaining=2 if can_activate else 0,
                        temporary_hit_points=0 if can_activate else 1,
                        movement_budget_ft=20 if can_activate else 10,
                        movement_effect={
                            "kind": "dash",
                            "distance_ft": 20 if can_activate else 10,
                        },
                    )
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                messages_before = [copy.deepcopy(session.messages) for session in sessions]
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                rng_module = random.getstate()
                default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                eligible_waiting = threading.Event()
                rejection_finished = threading.Event()
                bonus_action_owner = game._species_bonus_action

                def overlapping_bonus_action():
                    # The real handler has bound its character/trait state and
                    # passed its use check, but has not consumed a use or granted
                    # HP/movement. An exhausted handler must never reach here.
                    self.assertIs(game._session(), eligible)
                    eligible_waiting.set()
                    self.assertTrue(rejection_finished.wait(timeout=5))
                    self.assertIs(game._session(), eligible)
                    return bonus_action_owner()

                def reject_exhausted():
                    try:
                        self.assertTrue(eligible_waiting.wait(timeout=5))
                        with self.assertRaisesRegex(
                            ValueError, "^Adrenalin Patlaması için kullanım kalmadı\\.$"
                        ):
                            game.resolve_species_trait_action(
                                "adrenaline_rush", session=exhausted
                            )
                        # Rejection must leave both complete snapshots untouched,
                        # including the eligible campaign's still-pending grant.
                        for session, snapshot, rng, messages in zip(
                            sessions, before, rng_before, messages_before
                        ):
                            self.assertEqual(session.serialize_game_state(), snapshot)
                            self.assertEqual(session.rng.getstate(), rng)
                            self.assertEqual(session.messages, messages)
                        self.assertIs(game._session(), game._DEFAULT_SESSION)
                        self.assertEqual(game.serialize_game_state(), self.default_before)
                        self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                        self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                        self.assertEqual(random.getstate(), rng_module)
                    finally:
                        rejection_finished.set()

                with patch.object(game, "_species_bonus_action",
                                  side_effect=overlapping_bonus_action) as bonus_action, \
                     self.rolls(eligible), self.rolls(exhausted), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        # Reverse submission order as well as campaign roles;
                        # events guarantee overlap without timing-based sleeps.
                        jobs = (
                            lambda: game.resolve_species_trait_action(
                                "adrenaline_rush", session=eligible
                            ),
                            reject_exhausted,
                        )
                        if eligible_index:
                            rejected = pool.submit(jobs[1])
                            granted = pool.submit(jobs[0])
                        else:
                            granted = pool.submit(jobs[0])
                            rejected = pool.submit(jobs[1])
                        rejected.result(timeout=10)
                        grant = granted.result(timeout=10)
                    bonus_action.assert_called_once_with()

                self.assertEqual(grant["action"], "adrenaline_rush")
                self.assertEqual(grant["effects"], {
                    "temporary_hit_points": 3,
                    "dash_distance_ft": 60,
                })
                expected = copy.deepcopy(before)
                expected[eligible_index]["player"]["species_trait_state"].update(
                    adrenaline_rush_uses_remaining=1,
                    temporary_hit_points=3,
                    movement_budget_ft=60,
                    movement_effect={"kind": "dash", "distance_ft": 60},
                )
                for session, snapshot, rng, messages in zip(
                    sessions, expected, rng_before, messages_before
                ):
                    self.assertEqual(session.serialize_game_state(), snapshot)
                    self.assertEqual(session.rng.getstate(), rng)
                    self.assertEqual(session.messages, messages)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                self.assertEqual(random.getstate(), rng_module)

    def test_overlapping_adrenaline_rush_keeps_spent_bonus_actions_session_owned(self):
        for eligible_index in (0, 1):
            with self.subTest(eligible_index=eligible_index):
                sessions = (game.create_session(seed=17),
                            game.create_session(seed=29))
                eligible = sessions[eligible_index]
                spent = sessions[1 - eligible_index]
                for index, session in enumerate(sessions):
                    session.character.update(
                        species="Orc", race="Orc", level=1 if index == 0 else 5,
                        proficiency_bonus=2 + index, current_hp=11 + index * 7,
                        max_hp=19,
                    )
                    game.initialize_species_trait_state(session=session)
                    enemy = self.npc(session)
                    with patch.object(game, "roll_initiative_player", return_value=20), \
                         patch.object(game, "roll_initiative", return_value=1):
                        session.start_combat(enemy)
                    combat = session.world_state["combat"]
                    self.assertTrue(combat["active"])
                    self.assertEqual(combat["current_actor_id"], "player")
                    session.character["species_trait_state"].update(
                        adrenaline_rush_uses_remaining=1 + index,
                        temporary_hit_points=index,
                        movement_budget_ft=10 + index * 10,
                        movement_effect={"kind": "dash", "distance_ft": 10 + index * 10},
                    )
                    resources = game.action_economy.ensure(session)["player"]
                    resources.update(
                        bonus_action_spent=session is spent,
                        base_action_spent=bool(index),
                        reaction_spent=not bool(index),
                        movement_used=5 + index * 5,
                    )
                    # Keep the legacy round marker unset: rejection must come
                    # from this campaign's action-economy ledger, not that marker.
                    self.assertIsNone(
                        session.character["species_trait_state"]["bonus_action_used_round"]
                    )
                    self.assertGreater(
                        session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
                        0,
                    )
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                messages_before = [copy.deepcopy(session.messages) for session in sessions]
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                rng_module = random.getstate()
                default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                eligible_waiting = threading.Event()
                rejection_finished = threading.Event()
                bonus_action_owner = game._species_bonus_action

                def overlapping_bonus_action():
                    owner = game._session()
                    if owner is eligible:
                        # Both real handlers pass the positive-use gate while
                        # this activation is pending; only one may spend a bonus.
                        eligible_waiting.set()
                        self.assertTrue(rejection_finished.wait(timeout=5))
                    else:
                        self.assertIs(owner, spent)
                        self.assertTrue(eligible_waiting.is_set())
                    self.assertIs(game._session(), owner)
                    return bonus_action_owner()

                def assert_isolated(expected):
                    for session, snapshot, rng, messages in zip(
                        sessions, expected, rng_before, messages_before
                    ):
                        self.assertEqual(session.serialize_game_state(), snapshot)
                        self.assertEqual(session.rng.getstate(), rng)
                        self.assertEqual(session.messages, messages)
                    self.assertIs(game._session(), game._DEFAULT_SESSION)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                    self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                    self.assertEqual(random.getstate(), rng_module)

                def reject_spent():
                    try:
                        self.assertTrue(eligible_waiting.wait(timeout=5))
                        with self.assertRaisesRegex(
                            ValueError, "^Bu tur bonus eylemini zaten kullandın\\.$"
                        ):
                            game.resolve_species_trait_action(
                                "adrenaline_rush", session=spent
                            )
                        # The rejected campaign and the paused eligible campaign
                        # must both remain completely unchanged at this boundary.
                        assert_isolated(before)
                    finally:
                        rejection_finished.set()

                with patch.object(game, "_species_bonus_action",
                                  side_effect=overlapping_bonus_action) as bonus_action, \
                     self.rolls(eligible), self.rolls(spent), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        jobs = (
                            lambda: game.resolve_species_trait_action(
                                "adrenaline_rush", session=eligible
                            ),
                            reject_spent,
                        )
                        if eligible_index:
                            rejected = pool.submit(jobs[1])
                            granted = pool.submit(jobs[0])
                        else:
                            granted = pool.submit(jobs[0])
                            rejected = pool.submit(jobs[1])
                        rejected.result(timeout=10)
                        grant = granted.result(timeout=10)
                    self.assertEqual(bonus_action.call_count, 2)
                self.assertEqual(grant["action"], "adrenaline_rush")
                self.assertEqual(grant["effects"], {
                    "temporary_hit_points": 2 + eligible_index,
                    "dash_distance_ft": 60,
                })
                expected = copy.deepcopy(before)
                expected[eligible_index]["player"]["species_trait_state"].update(
                    adrenaline_rush_uses_remaining=eligible_index,
                    temporary_hit_points=2 + eligible_index,
                    movement_budget_ft=60,
                    movement_effect={"kind": "dash", "distance_ft": 60},
                    bonus_action_used_round=before[eligible_index]["world_state"]["combat"]["round"],
                )
                expected[eligible_index]["world_state"]["combat"]["turn_resources"]["player"].update(
                    bonus_action_spent=True, dash_count=1, movement_available=60,
                )
                assert_isolated(expected)

    def test_overlapping_orc_and_aasimar_bonus_actions_keep_transformations_session_owned(self):
        for eligible_index in (0, 1):
            with self.subTest(eligible_species=("Orc", "Aasimar")[eligible_index]):
                sessions = (game.create_session(seed=17),
                            game.create_session(seed=29))
                eligible = sessions[eligible_index]
                spent = sessions[1 - eligible_index]
                requests = (
                    {"action": "adrenaline_rush"},
                    {"action": "celestial_revelation", "form": "heavenly_wings"},
                )
                use_keys = ("adrenaline_rush_uses_remaining",
                            "celestial_revelation_uses_remaining")
                for index, (session, species) in enumerate(zip(sessions, ("Orc", "Aasimar"))):
                    session.character.update(
                        species=species, race=species, level=5,
                        proficiency_bonus=3, current_hp=11 + index * 7,
                        max_hp=19,
                    )
                    game.initialize_species_trait_state(session=session)
                    session.character["speed_ft"] = 30 + index * 5
                    enemy = self.npc(session)
                    with patch.object(game, "roll_initiative_player", return_value=20), \
                         patch.object(game, "roll_initiative", return_value=1):
                        session.start_combat(enemy)
                    combat = session.world_state["combat"]
                    self.assertTrue(combat["active"])
                    self.assertEqual(combat["current_actor_id"], "player")
                    state = session.character["species_trait_state"]
                    state.update(
                        temporary_hit_points=index,
                        movement_budget_ft=10 + index * 10,
                        movement_effect={"kind": "dash", "distance_ft": 10 + index * 10},
                    )
                    state[use_keys[index]] = 1
                    resources = game.action_economy.ensure(session)["player"]
                    resources.update(
                        bonus_action_spent=session is spent,
                        base_action_spent=bool(index),
                        reaction_spent=not bool(index),
                        movement_used=5 + index * 5,
                    )
                    # Both branches have uses; only the ledger may reject one.
                    self.assertGreater(state[use_keys[index]], 0)
                    self.assertIsNone(state["bonus_action_used_round"])
                    self.assertIsNone(state["active_celestial_form"])
                    session.messages.append({
                        "role": "user", "content": f"{species} campaign history",
                    })
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                messages_before = [copy.deepcopy(session.messages) for session in sessions]
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                rng_module = random.getstate()
                default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                eligible_waiting = threading.Event()
                rejection_finished = threading.Event()
                bonus_action_owner = game._species_bonus_action

                def overlapping_bonus_action():
                    owner = game._session()
                    if owner is eligible:
                        eligible_waiting.set()
                        self.assertTrue(rejection_finished.wait(timeout=5))
                    else:
                        self.assertIs(owner, spent)
                        self.assertTrue(eligible_waiting.is_set())
                    self.assertIs(game._session(), owner)
                    return bonus_action_owner()

                def assert_isolated(expected):
                    for session, snapshot, rng, messages in zip(
                        sessions, expected, rng_before, messages_before
                    ):
                        self.assertEqual(session.serialize_game_state(), snapshot)
                        self.assertEqual(session.messages, messages)
                        self.assertEqual(session.rng.getstate(), rng)
                    self.assertIs(game._session(), game._DEFAULT_SESSION)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                    self.assertEqual(random.getstate(), rng_module)

                def reject_spent():
                    try:
                        self.assertTrue(eligible_waiting.wait(timeout=5))
                        with self.assertRaisesRegex(
                            ValueError, "^Bu tur bonus eylemini zaten kullandın\\.$"
                        ):
                            game.resolve_species_trait_action(
                                **requests[1 - eligible_index], session=spent
                            )
                        # The eligible handler is still paused at the real owner.
                        assert_isolated(before)
                    finally:
                        rejection_finished.set()

                with patch.object(game, "_species_bonus_action",
                                  side_effect=overlapping_bonus_action) as bonus_action, \
                     self.rolls(eligible), self.rolls(spent), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        jobs = (
                            lambda: game.resolve_species_trait_action(
                                **requests[eligible_index], session=eligible
                            ),
                            reject_spent,
                        )
                        # Reverse submission order along with species eligibility.
                        if eligible_index:
                            rejected = pool.submit(jobs[1])
                            granted = pool.submit(jobs[0])
                        else:
                            granted = pool.submit(jobs[0])
                            rejected = pool.submit(jobs[1])
                        rejected.result(timeout=10)
                        grant = granted.result(timeout=10)
                    self.assertEqual(bonus_action.call_count, 2)
                self.assertEqual(grant["action"], requests[eligible_index]["action"])
                expected = copy.deepcopy(before)
                state = expected[eligible_index]["player"]["species_trait_state"]
                state[use_keys[eligible_index]] = 0
                state["bonus_action_used_round"] = (
                    before[eligible_index]["world_state"]["combat"]["round"]
                )
                resources = expected[eligible_index]["world_state"]["combat"]["turn_resources"]["player"]
                resources["bonus_action_spent"] = True
                if eligible_index == 0:
                    self.assertEqual(grant["effects"], {
                        "temporary_hit_points": 3, "dash_distance_ft": 60,
                    })
                    state.update(
                        temporary_hit_points=3, movement_budget_ft=60,
                        movement_effect={"kind": "dash", "distance_ft": 60},
                    )
                    resources.update(dash_count=1, movement_available=60)
                else:
                    self.assertEqual(grant["effects"], {
                        "form": "heavenly_wings", "duration_turns": 10,
                    })
                    state.update(
                        active_celestial_form="heavenly_wings",
                        celestial_revelation_turns_remaining=10,
                        movement_effect={"kind": "flight", "speed_ft": 35},
                    )
                assert_isolated(expected)

    def test_overlapping_hits_keep_temporary_hp_in_their_own_sessions(self):
        # Legal Orc reserves (proficiency bonus 2) exercise full absorption,
        # a surviving reserve, and spillover into regular HP. Explicit expected
        # values do not reuse the production damage owner as an oracle.
        expectations = {
            # (temporary HP before, damage): (absorbed, reserve after, HP after)
            (0, 1): (0, 0, 18),
            (1, 1): (1, 0, 19),
            (2, 1): (1, 1, 19),
            (0, 3): (0, 0, 16),
            (1, 3): (1, 0, 17),
            (2, 3): (2, 0, 18),
        }
        for damage in (1, 3):
            for reserves in ((0, 1), (1, 0), (0, 2), (2, 0), (1, 2), (2, 1)):
                with self.subTest(damage=damage, reserves=reserves):
                    sessions = (game.create_session(seed=17),
                                game.create_session(seed=17))
                    enemies = [self.npc(session) for session in sessions]
                    for session, enemy, reserve in zip(sessions, enemies, reserves):
                        session.character.update(
                            species="Orc", race="Orc", proficiency_bonus=2,
                            armor_class=10, current_hp=19, max_hp=19,
                            resistances=[], immunities=[], vulnerabilities=[],
                        )
                        game.initialize_species_trait_state(session=session)
                        session.character["species_trait_state"][
                            "temporary_hit_points"
                        ] = reserve
                        enemy.update(attack_bonus=0, damage_die=6,
                                     damage_dice=1, damage_modifier=0)
                    self.assertEqual(enemies[0], enemies[1])
                    self.assertEqual(sessions[0].world_state["attack_environment"],
                                     sessions[1].world_state["attack_environment"])
                    before = [session.serialize_game_state() for session in sessions]
                    rng_before = [session.rng.getstate() for session in sessions]
                    rng_default = game._DEFAULT_SESSION.rng.getstate()
                    rng_module = random.getstate()
                    attack_barrier = threading.Barrier(2)
                    damage_barrier = threading.Barrier(2)
                    # Both contexts are live at attack and damage rolls. Keep
                    # the real temporary-HP/regular-HP owners in the call path.
                    with self.rolls(sessions[0], (20, 15), (6, damage),
                                    barrier=attack_barrier,
                                    damage_barrier=damage_barrier), \
                         self.rolls(sessions[1], (20, 15), (6, damage),
                                    barrier=attack_barrier,
                                    damage_barrier=damage_barrier), \
                         self.rolls(game._DEFAULT_SESSION):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [
                                pool.submit(game.resolve_enemy_attack, enemy,
                                            session=session)
                                for session, enemy in zip(sessions, enemies)
                            ]
                            results = [future.result(timeout=10) for future in futures]
                    for session, enemy, reserve, result, expected, rng in zip(
                        sessions, enemies, reserves, results, before, rng_before
                    ):
                        absorbed, remaining, hp_after = expectations[(reserve, damage)]
                        self.assertEqual(result["actor_id"], enemy["id"])
                        self.assertEqual(result["target_id"], "player")
                        self.assertEqual(result["attack_rolls"], [15])
                        self.assertEqual(result["attack_roll"], 15)
                        self.assertEqual(result["attack_total"], 15)
                        self.assertEqual(result["target_ac"], 10)
                        self.assertEqual(result["advantage_sources"], [])
                        self.assertEqual(result["disadvantage_sources"], [])
                        self.assertFalse(result["critical"])
                        self.assertTrue(result["hit"])
                        self.assertTrue(result["success"])
                        self.assertEqual(result["outcome"], "hit")
                        self.assertEqual(result["damage_type"], "slashing")
                        self.assertEqual(result["damage_rolls"], [
                            {"source": "weapon", "die": 6, "count": 1,
                             "rolls": [damage]},
                        ])
                        self.assertEqual(result["raw_damage"], damage)
                        self.assertEqual(result["damage"], damage)
                        self.assertEqual(result["temporary_hp_before"], reserve)
                        self.assertEqual(result["temporary_hp_absorbed"], absorbed)
                        self.assertEqual(result["temporary_hp_after"], remaining)
                        self.assertEqual(result["hp_damage"], 19 - hp_after)
                        self.assertEqual(result["target_hp_before"], 19)
                        self.assertEqual(result["target_hp_after"], hp_after)
                        self.assertEqual(result["target_status"], "active")
                        self.assertEqual(result["species_effects"], [])
                        self.assertIsNone(result["death_resolution"])
                        self.assertEqual(session.character["current_hp"], hp_after)
                        self.assertEqual(
                            session.character["species_trait_state"][
                                "temporary_hit_points"
                            ], remaining,
                        )
                        # Only the owning HP/reserve and its attack receipt may
                        # change; preserve the rest of the complete snapshot.
                        expected["player"]["current_hp"] = hp_after
                        expected["player"]["species_trait_state"][
                            "temporary_hit_points"
                        ] = remaining
                        expected["world_state"].setdefault("attack_results", []).append(
                            copy.deepcopy(result)
                        )
                        self.assertEqual(session.serialize_game_state(), expected)
                        self.assertEqual(session.rng.getstate(), rng)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                    self.assertEqual(random.getstate(), rng_module)

    def test_overlapping_knockouts_keep_relentless_endurance_in_owning_session(self):
        for available_index in (0, 1):
            with self.subTest(available_index=available_index):
                sessions = (game.create_session(seed=17),
                            game.create_session(seed=17))
                enemies = [self.npc(session) for session in sessions]
                for index, (session, enemy) in enumerate(zip(sessions, enemies)):
                    session.character.update(
                        species="Orc", race="Orc", proficiency_bonus=2,
                        armor_class=10, current_hp=3, max_hp=19,
                        resistances=[], immunities=[], vulnerabilities=[],
                    )
                    session.initialize_species_trait_state()
                    session.character["species_trait_state"][
                        "relentless_endurance_available"
                    ] = index == available_index
                    session.ensure_campaign_clock()
                    enemy.update(attack_bonus=0, damage_die=6,
                                 damage_dice=1, damage_modifier=1)
                self.assertEqual(enemies[0], enemies[1])
                self.assertEqual(sessions[0].world_state["attack_environment"],
                                 sessions[1].world_state["attack_environment"])
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                messages_before = [copy.deepcopy(session.messages)
                                   for session in sessions]
                default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                rng_module = random.getstate()
                attack_barrier = threading.Barrier(2)
                damage_barrier = threading.Barrier(2)
                # Six damage knocks both players out but cannot kill outright
                # (3 + 19 HP). Only the available owner may instead stay at 1 HP.
                # Fix only the episode identifier, not the damage/survival owner,
                # so the complete expected death-state snapshot is deterministic.
                episode_id = "00000000-0000-0000-0000-000000000090"
                with self.rolls(sessions[0], (20, 15), (6, 5),
                                barrier=attack_barrier,
                                damage_barrier=damage_barrier), \
                     self.rolls(sessions[1], (20, 15), (6, 5),
                                barrier=attack_barrier,
                                damage_barrier=damage_barrier), \
                     self.rolls(game._DEFAULT_SESSION), \
                     patch.object(game, "uuid4", return_value=episode_id):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [
                            pool.submit(game.resolve_enemy_attack, enemy,
                                        session=session)
                            for session, enemy in zip(sessions, enemies)
                        ]
                        results = [future.result(timeout=10) for future in futures]
                for index, (session, enemy, result, expected, rng, messages) in enumerate(
                    zip(sessions, enemies, results, before, rng_before, messages_before)
                ):
                    available = index == available_index
                    hp_after = 1 if available else 0
                    status = "active" if available else "unconscious"
                    self.assertEqual(result["actor_id"], enemy["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["attack_rolls"], [15])
                    self.assertEqual(result["attack_total"], 15)
                    self.assertEqual(result["target_ac"], 10)
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"], [])
                    self.assertFalse(result["critical"])
                    self.assertTrue(result["hit"])
                    self.assertTrue(result["success"])
                    self.assertEqual(result["outcome"], "hit")
                    self.assertEqual(result["damage_type"], "slashing")
                    self.assertEqual(result["damage_rolls"], [
                        {"source": "weapon", "die": 6, "count": 1, "rolls": [5]},
                    ])
                    self.assertEqual(result["raw_damage"], 6)
                    self.assertEqual(result["damage"], 6)
                    self.assertEqual(result["hp_damage"], 6)
                    self.assertEqual(result["temporary_hp_before"], 0)
                    self.assertEqual(result["temporary_hp_absorbed"], 0)
                    self.assertEqual(result["temporary_hp_after"], 0)
                    self.assertEqual(result["target_hp_before"], 3)
                    self.assertEqual(result["target_hp_after"], hp_after)
                    self.assertEqual(result["target_status"], status)
                    self.assertEqual(result["species_effects"],
                                     [{"trait": "relentless_endurance", "current_hp": 1}]
                                     if available else [])
                    self.assertIsNone(result["death_resolution"])
                    self.assertEqual(session.character["current_hp"], hp_after)
                    self.assertEqual(session.world_state["player_combat_status"], status)
                    self.assertFalse(session.character["species_trait_state"][
                        "relentless_endurance_available"
                    ])
                    expected["player"]["current_hp"] = hp_after
                    expected["player"]["species_trait_state"][
                        "relentless_endurance_available"
                    ] = False
                    expected["world_state"]["player_combat_status"] = status
                    if not available:
                        expected["world_state"]["death_state"].update(
                            prone=True,
                            noncombat_episode_id=episode_id,
                            noncombat_next_save_at=(
                                expected["world_state"]["campaign_time"][
                                    "elapsed_seconds"
                                ] + 6
                            ),
                        )
                    self.assertEqual(session.world_state["death_state"],
                                     expected["world_state"]["death_state"])
                    expected["world_state"].setdefault("attack_results", []).append(
                        copy.deepcopy(result)
                    )
                    # No borrowed resource, death bookkeeping, NPC/environment
                    # mutation, combat transition, or unrelated species effect.
                    self.assertEqual(session.serialize_game_state(), expected)
                    self.assertEqual(session.messages, messages)
                    self.assertEqual(session.rng.getstate(), rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                self.assertEqual(random.getstate(), rng_module)

    def test_overlapping_fatal_hit_cannot_use_another_orcs_relentless_endurance(self):
        for fatal_index in (0, 1):
            with self.subTest(fatal_index=fatal_index):
                sessions = (game.create_session(seed=17),
                            game.create_session(seed=17))
                enemies = [self.npc(session) for session in sessions]
                for session, enemy in zip(sessions, enemies):
                    session.character.update(
                        species="Orc", race="Orc", proficiency_bonus=2,
                        armor_class=10, current_hp=3, max_hp=19,
                        resistances=[], immunities=[], vulnerabilities=[],
                    )
                    session.initialize_species_trait_state()
                    self.assertTrue(session.character["species_trait_state"][
                        "relentless_endurance_available"
                    ])
                    session.ensure_campaign_clock()
                    enemy.update(attack_bonus=0, damage_die=12,
                                 damage_dice=1, damage_modifier=10)
                self.assertEqual(enemies[0], enemies[1])
                self.assertEqual(sessions[0].world_state["attack_environment"],
                                 sessions[1].world_state["attack_environment"])
                before = [session.serialize_game_state() for session in sessions]
                rng_before = [session.rng.getstate() for session in sessions]
                messages_before = [copy.deepcopy(session.messages)
                                   for session in sessions]
                default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                rng_module = random.getstate()
                attack_barrier = threading.Barrier(2)
                damage_barrier = threading.Barrier(2)
                # 22 damage equals current + max HP: instant death. 21 is
                # one below that boundary and must instead trigger Endurance.
                # Keep identical NPCs/geometry and swap the fatal owner.
                damage_rolls = [12 if index == fatal_index else 11
                                for index in range(2)]
                with self.rolls(sessions[0], (20, 15), (12, damage_rolls[0]),
                                barrier=attack_barrier,
                                damage_barrier=damage_barrier), \
                     self.rolls(sessions[1], (20, 15), (12, damage_rolls[1]),
                                barrier=attack_barrier,
                                damage_barrier=damage_barrier), \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [
                            pool.submit(game.resolve_enemy_attack, enemy,
                                        session=session)
                            for session, enemy in zip(sessions, enemies)
                        ]
                        results = [future.result(timeout=10) for future in futures]
                for index, (session, enemy, result, expected, rng, messages) in enumerate(
                    zip(sessions, enemies, results, before, rng_before, messages_before)
                ):
                    fatal = index == fatal_index
                    damage = 22 if fatal else 21
                    hp_after = 0 if fatal else 1
                    status = "dead" if fatal else "active"
                    resolution = {
                        "mode": "NORMAL", "outcome": "dead",
                        "cause": "massive_damage", "rolled_back": False,
                        "terminal": False,
                    } if fatal else None
                    self.assertEqual(result["actor_id"], enemy["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["attack_rolls"], [15])
                    self.assertEqual(result["attack_total"], 15)
                    self.assertEqual(result["target_ac"], 10)
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"], [])
                    self.assertFalse(result["critical"])
                    self.assertTrue(result["hit"])
                    self.assertTrue(result["success"])
                    self.assertEqual(result["outcome"], "hit")
                    self.assertEqual(result["damage_type"], "slashing")
                    self.assertEqual(result["damage_rolls"], [
                        {"source": "weapon", "die": 12, "count": 1,
                         "rolls": [damage_rolls[index]]},
                    ])
                    self.assertEqual(result["raw_damage"], damage)
                    self.assertEqual(result["damage"], damage)
                    self.assertEqual(result["hp_damage"], damage)
                    self.assertEqual(result["temporary_hp_before"], 0)
                    self.assertEqual(result["temporary_hp_absorbed"], 0)
                    self.assertEqual(result["temporary_hp_after"], 0)
                    self.assertEqual(result["target_hp_before"], 3)
                    self.assertEqual(result["target_hp_after"], hp_after)
                    self.assertEqual(result["target_status"], status)
                    self.assertEqual(result["species_effects"], [] if fatal else [
                        {"trait": "relentless_endurance", "current_hp": 1},
                    ])
                    self.assertEqual(result["death_resolution"], resolution)
                    self.assertEqual(session.character["current_hp"], hp_after)
                    self.assertEqual(session.world_state["player_combat_status"], status)
                    # Fatal damage must leave its unused resource available;
                    # only the survivable campaign spends its own resource.
                    self.assertEqual(session.character["species_trait_state"][
                        "relentless_endurance_available"
                    ], fatal)
                    expected["player"]["current_hp"] = hp_after
                    expected["player"]["species_trait_state"][
                        "relentless_endurance_available"
                    ] = fatal
                    expected["world_state"]["player_combat_status"] = status
                    if fatal:
                        expected["world_state"]["death_state"].update(
                            dead=True, failures=3, last_resolution=resolution,
                        )
                    self.assertEqual(session.world_state["death_state"],
                                     expected["world_state"]["death_state"])
                    expected["world_state"].setdefault("attack_results", []).append(
                        copy.deepcopy(result)
                    )
                    self.assertEqual(session.serialize_game_state(), expected)
                    self.assertEqual(session.messages, messages)
                    self.assertEqual(session.rng.getstate(), rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                self.assertEqual(random.getstate(), rng_module)

    def test_overlapping_fatal_rollback_cannot_restore_another_orcs_endurance(self):
        for rollback_index in (0, 1):
            with self.subTest(rollback_index=rollback_index):
                sessions = (game.create_session(seed=17),
                            game.create_session(seed=29))
                enemies = [self.npc(session) for session in sessions]
                for index, (session, enemy) in enumerate(zip(sessions, enemies)):
                    session.character.update(
                        species="Orc", race="Orc", proficiency_bonus=2,
                        armor_class=10, current_hp=19, max_hp=19,
                        resistances=[], immunities=[], vulnerabilities=[],
                    )
                    session.initialize_species_trait_state()
                    session.ensure_campaign_clock()
                    session.world_state["campaign_id"] = f"rollback-campaign-{index}"
                    session.world_state["inventory"].append(f"keepsake-{index}")
                    session.world_state["attack_results"] = [
                        {"marker": f"precombat-{index}"}
                    ]
                    session.recent_dm_narrations.append(f"precombat-{index}")
                    session.messages.append(
                        {"role": "user", "content": f"campaign-{index}"}
                    )
                    enemy.update(attack_bonus=0, damage_die=12,
                                 damage_dice=1, damage_modifier=10)
                rollback = sessions[rollback_index]
                survivor = sessions[1 - rollback_index]
                checkpoint_snapshot = rollback.serialize_game_state()
                checkpoint_rng = rollback.rng.getstate()
                # Use the real checkpoint owner, as in test_death_system.py.
                game._capture_combat_death_checkpoint(session=rollback)
                self.assertEqual(rollback.world_state["death_state"]["mode"],
                                 "NORMAL")
                self.assertEqual(
                    rollback.world_state["death_state"]["combat_checkpoint"][
                        "campaign_id"
                    ], rollback.world_state["campaign_id"],
                )
                for session in sessions:
                    session.character["current_hp"] = 3
                rollback.character["species_trait_state"][
                    "relentless_endurance_available"
                ] = False
                rollback.world_state["inventory"].append("combat-only loot")
                rollback.world_state["attack_results"].append(
                    {"marker": "combat-only attack"}
                )
                rollback.recent_dm_narrations.append("combat-only narration")
                # Advance both streams after the checkpoint. Rollback must not
                # rewind even its own RNG, much less the other campaign's.
                for session in sessions:
                    session.rng.random()
                before = [session.serialize_game_state() for session in sessions]
                messages = [copy.deepcopy(session.messages) for session in sessions]
                references = [(session.world_state, session.character,
                               session.recent_dm_narrations)
                              for session in sessions]
                expected_rng = []
                for session in sessions:
                    reference_rng = random.Random()
                    reference_rng.setstate(session.rng.getstate())
                    reference_rng.randint(1, 20)
                    reference_rng.randint(1, 12)
                    expected_rng.append(reference_rng.getstate())
                rng_default = game._DEFAULT_SESSION.rng.getstate()
                default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                rng_module = random.getstate()
                attack_barrier = threading.Barrier(2)
                damage_barrier = threading.Barrier(2)
                survivor_finished = threading.Event()
                survivor_results = []
                original_restore = game._restore_combat_death_checkpoint

                def assert_survivor_unchanged():
                    expected = copy.deepcopy(before[1 - rollback_index])
                    expected["player"]["current_hp"] = 1
                    expected["player"]["species_trait_state"][
                        "relentless_endurance_available"
                    ] = False
                    expected["world_state"]["attack_results"].append(
                        copy.deepcopy(survivor_results[0])
                    )
                    self.assertEqual(survivor.serialize_game_state(), expected)
                    self.assertEqual(survivor.rng.getstate(),
                                     expected_rng[1 - rollback_index])
                    self.assertEqual(survivor.messages, messages[1 - rollback_index])

                def overlapping_restore(cause):
                    self.assertIs(game._session(), rollback)
                    self.assertTrue(survivor_finished.wait(timeout=5),
                                    "Survivable hit did not finish before rollback")
                    assert_survivor_unchanged()
                    resolution = original_restore(cause)
                    self.assertIs(game._session(), rollback)
                    assert_survivor_unchanged()
                    return resolution

                def scripted_roll(session, damage_roll):
                    original_randint = session.rng.randint
                    remaining = iter(((20, 15), (12, damage_roll)))

                    def randint(low, high):
                        sides, value = next(remaining)
                        self.assertEqual((low, high), (1, sides))
                        self.assertIs(game._session(), session)
                        original_randint(low, high)
                        barrier = attack_barrier if sides == 20 else damage_barrier
                        barrier.wait(timeout=5)
                        self.assertIs(game._session(), session)
                        return value

                    return randint, remaining

                rolls = [scripted_roll(session, 12 if index == rollback_index else 11)
                         for index, session in enumerate(sessions)]

                def attack(index):
                    session = sessions[index]
                    result = game.resolve_enemy_attack(enemies[index], session=session)
                    if session is survivor:
                        survivor_results.append(result)
                        survivor_finished.set()
                    return result

                with patch.object(sessions[0].rng, "randint", side_effect=rolls[0][0]), \
                     patch.object(sessions[1].rng, "randint", side_effect=rolls[1][0]), \
                     patch("game._restore_combat_death_checkpoint",
                           side_effect=overlapping_restore) as restore, \
                     self.rolls(game._DEFAULT_SESSION):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(attack, index) for index in range(2)]
                        results = [future.result(timeout=10) for future in futures]
                    restore.assert_called_once_with("massive_damage")
                for _, remaining in rolls:
                    self.assertIsNone(next(remaining, None), "Unused scripted dice")
                resolution = {
                    "mode": "NORMAL", "outcome": "rolled_back",
                    "cause": "massive_damage", "rolled_back": True, "terminal": False,
                }
                for index, result in enumerate(results):
                    fatal = index == rollback_index
                    self.assertTrue(result["hit"])
                    self.assertTrue(result["success"])
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["attack_rolls"], [15])
                    self.assertEqual(result["damage"], 22 if fatal else 21)
                    self.assertEqual(result["target_hp_before"], 3)
                    self.assertEqual(result["target_hp_after"], 19 if fatal else 1)
                    self.assertEqual(result["target_status"], "active")
                    self.assertEqual(result["death_resolution"],
                                     resolution if fatal else None)
                    self.assertEqual(result["species_effects"], [] if fatal else [
                        {"trait": "relentless_endurance", "current_hp": 1},
                    ])
                expected = copy.deepcopy(checkpoint_snapshot)
                expected["world_state"]["death_state"]["last_resolution"] = resolution
                expected["world_state"]["attack_results"].append(
                    copy.deepcopy(results[rollback_index])
                )
                self.assertEqual(rollback.serialize_game_state(), expected)
                self.assertIsNone(rollback.world_state["death_state"]["combat_checkpoint"])
                self.assertTrue(rollback.character["species_trait_state"][
                    "relentless_endurance_available"
                ])
                self.assertNotEqual(rollback.rng.getstate(), checkpoint_rng)
                assert_survivor_unchanged()
                for index, session in enumerate(sessions):
                    self.assertEqual(session.rng.getstate(), expected_rng[index])
                    self.assertEqual(session.messages, messages[index])
                    world, character, narrations = references[index]
                    self.assertIs(session.world_state, world)
                    self.assertIs(session.character, character)
                    self.assertIs(session.recent_dm_narrations, narrations)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                self.assertEqual(random.getstate(), rng_module)

    def test_overlapping_fatal_hits_keep_temporary_hp_protection_session_owned(self):
        for protected_reserve in (1, 2):
            for fatal_index in (0, 1):
                with self.subTest(protected_reserve=protected_reserve,
                                  fatal_index=fatal_index):
                    sessions = (game.create_session(seed=17),
                                game.create_session(seed=29))
                    self.assertIsNot(sessions[0].rng, sessions[1].rng)
                    enemies = [self.npc(session) for session in sessions]
                    reserves = [0 if index == fatal_index else protected_reserve
                                for index in range(2)]
                    for session, enemy, reserve in zip(sessions, enemies, reserves):
                        session.character.update(
                            species="Orc", race="Orc", proficiency_bonus=2,
                            armor_class=10, current_hp=3, max_hp=19,
                            resistances=[], immunities=[], vulnerabilities=[],
                        )
                        session.initialize_species_trait_state()
                        session.character["species_trait_state"][
                            "temporary_hit_points"
                        ] = reserve
                        self.assertTrue(session.character["species_trait_state"][
                            "relentless_endurance_available"
                        ])
                        session.ensure_campaign_clock()
                        enemy.update(attack_bonus=0, damage_die=12,
                                     damage_dice=1, damage_modifier=10)
                    self.assertEqual(enemies[0], enemies[1])
                    self.assertEqual(sessions[0].world_state["attack_environment"],
                                     sessions[1].world_state["attack_environment"])
                    before = [session.serialize_game_state() for session in sessions]
                    rng_before = [session.rng.getstate() for session in sessions]
                    self.assertNotEqual(rng_before[0], rng_before[1])
                    messages_before = [copy.deepcopy(session.messages)
                                       for session in sessions]
                    default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
                    rng_default = game._DEFAULT_SESSION.rng.getstate()
                    rng_module = random.getstate()
                    attack_barrier = threading.Barrier(2)
                    damage_barrier = threading.Barrier(2)
                    # Identical d12=12 + 10 damage equals 3 + 19 HP. Only
                    # the owning reserve lowers HP damage below instant death:
                    # 0 -> 22 (fatal), 1 -> 21 or 2 -> 20 (Endurance).
                    # Synchronize both dice stages without replacing HP/death
                    # owners, and swap which campaign has the protection.
                    with self.rolls(sessions[0], (20, 15), (12, 12),
                                    barrier=attack_barrier,
                                    damage_barrier=damage_barrier), \
                         self.rolls(sessions[1], (20, 15), (12, 12),
                                    barrier=attack_barrier,
                                    damage_barrier=damage_barrier), \
                         self.rolls(game._DEFAULT_SESSION):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [
                                pool.submit(game.resolve_enemy_attack, enemy,
                                            session=session)
                                for session, enemy in zip(sessions, enemies)
                            ]
                            results = [future.result(timeout=10) for future in futures]
                    for index, (session, enemy, reserve, result, expected, rng,
                                messages) in enumerate(zip(
                                    sessions, enemies, reserves, results, before,
                                    rng_before, messages_before,
                                )):
                        fatal = index == fatal_index
                        hp_after = 0 if fatal else 1
                        status = "dead" if fatal else "active"
                        resolution = {
                            "mode": "NORMAL", "outcome": "dead",
                            "cause": "massive_damage", "rolled_back": False,
                            "terminal": False,
                        } if fatal else None
                        self.assertEqual(result["actor_id"], enemy["id"])
                        self.assertEqual(result["target_id"], "player")
                        self.assertEqual(result["attack_rolls"], [15])
                        self.assertEqual(result["attack_roll"], 15)
                        self.assertEqual(result["attack_total"], 15)
                        self.assertEqual(result["target_ac"], 10)
                        self.assertEqual(result["advantage_sources"], [])
                        self.assertEqual(result["disadvantage_sources"], [])
                        self.assertFalse(result["critical"])
                        self.assertTrue(result["hit"])
                        self.assertTrue(result["success"])
                        self.assertEqual(result["outcome"], "hit")
                        self.assertEqual(result["damage_type"], "slashing")
                        self.assertEqual(result["damage_rolls"], [
                            {"source": "weapon", "die": 12, "count": 1,
                             "rolls": [12]},
                        ])
                        self.assertEqual(result["raw_damage"], 22)
                        self.assertEqual(result["damage"], 22)
                        self.assertEqual(result["hp_damage"], 22 - reserve)
                        self.assertEqual(result["temporary_hp_before"], reserve)
                        self.assertEqual(result["temporary_hp_absorbed"], reserve)
                        self.assertEqual(result["temporary_hp_after"], 0)
                        self.assertEqual(result["target_hp_before"], 3)
                        self.assertEqual(result["target_hp_after"], hp_after)
                        self.assertEqual(result["target_status"], status)
                        self.assertEqual(result["species_effects"], [] if fatal else [
                            {"trait": "relentless_endurance", "current_hp": 1},
                        ])
                        self.assertEqual(result["death_resolution"], resolution)
                        expected["player"]["current_hp"] = hp_after
                        expected["player"]["species_trait_state"].update(
                            temporary_hit_points=0,
                            relentless_endurance_available=fatal,
                        )
                        expected["world_state"]["player_combat_status"] = status
                        if fatal:
                            expected["world_state"]["death_state"].update(
                                dead=True, failures=3, last_resolution=resolution,
                            )
                        self.assertEqual(session.world_state["death_state"],
                                         expected["world_state"]["death_state"])
                        expected["world_state"].setdefault("attack_results", []).append(
                            copy.deepcopy(result)
                        )
                        # Full equality also protects all other species uses,
                        # NPCs, geometry, clock, combat and death bookkeeping.
                        self.assertEqual(session.serialize_game_state(), expected)
                        self.assertEqual(session.messages, messages)
                        self.assertEqual(session.rng.getstate(), rng)
                    self.assertIs(game._session(), game._DEFAULT_SESSION)
                    self.assertEqual(game.serialize_game_state(), self.default_before)
                    self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                    self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                    self.assertEqual(random.getstate(), rng_module)
                }
                for index, result in enumerate(results):
                    fatal = index == rollback_index
                    self.assertTrue(result["hit"])
                    self.assertTrue(result["success"])
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["attack_rolls"], [15])
                    self.assertEqual(result["damage"], 22 if fatal else 21)
                    self.assertEqual(result["target_hp_before"], 3)
                    self.assertEqual(result["target_hp_after"], 19 if fatal else 1)
                    self.assertEqual(result["target_status"], "active")
                    self.assertEqual(result["death_resolution"],
                                     resolution if fatal else None)
                    self.assertEqual(result["species_effects"], [] if fatal else [
                        {"trait": "relentless_endurance", "current_hp": 1},
                    ])
                expected = copy.deepcopy(checkpoint_snapshot)
                expected["world_state"]["death_state"]["last_resolution"] = resolution
                expected["world_state"]["attack_results"].append(
                    copy.deepcopy(results[rollback_index])
                )
                self.assertEqual(rollback.serialize_game_state(), expected)
                self.assertIsNone(rollback.world_state["death_state"]["combat_checkpoint"])
                self.assertTrue(rollback.character["species_trait_state"][
                    "relentless_endurance_available"
                ])
                self.assertNotEqual(rollback.rng.getstate(), checkpoint_rng)
                assert_survivor_unchanged()
                for index, session in enumerate(sessions):
                    self.assertEqual(session.rng.getstate(), expected_rng[index])
                    self.assertEqual(session.messages, messages[index])
                    world, character, narrations = references[index]
                    self.assertIs(session.world_state, world)
                    self.assertIs(session.character, character)
                    self.assertIs(session.recent_dm_narrations, narrations)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(game.serialize_game_state(), self.default_before)
                self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
                self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), rng_default)
                self.assertEqual(random.getstate(), rng_module)


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

class DiscoveryTests(unittest.TestCase):
    def test_session_regressions_are_discoverable_without_shadowed_methods(self):
        """Check source definitions as well as the methods visible to unittest."""
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        loader = unittest.TestLoader()
        expected_session_tests = {
            "test_overlapping_invalid_cover_does_not_disrupt_valid_attack",
            "test_inventory_memory_and_narration_are_independent",
            "test_combat_and_hp_are_independent",
            "test_rng_streams_are_independent_and_not_module_random",
            "test_turn_uses_owned_messages_and_context",
            "test_unverified_lore_claim_preserves_unrelated_local_proposals",
            "test_unregistered_lore_question_returns_explicit_unverified_without_model_answer",
            "test_save_load_preserves_ownership_and_references",
            "test_invalid_load_preserves_all_sessions_and_held_references",
            "test_invalid_default_load_preserves_all_sessions_and_held_references",
            "test_save_load_conscious_player_clears_unconscious_status",
            "test_save_load_unconscious_player_keeps_other_sessions_conscious",
            "test_nested_session_and_exception_restore_context",
            "test_overlapping_calls_do_not_swap_global_state",
            "test_overlapping_attack_cannot_borrow_another_sessions_distance",
            "test_overlapping_attack_cannot_borrow_another_sessions_visibility",
            "test_overlapping_attacks_keep_directional_cover_in_their_own_sessions",
            "test_overlapping_attack_cannot_borrow_another_sessions_total_cover",
            "test_overlapping_hits_keep_damage_dice_in_their_own_sessions",
            "test_overlapping_knockout_does_not_incapacitate_other_sessions",
            "test_overlapping_attacks_use_reverse_distance_but_not_reverse_visibility",
            "test_overlapping_attack_cannot_borrow_another_sessions_hidden_attacker",
            "test_overlapping_hits_keep_damage_protection_in_their_own_sessions",
            "test_overlapping_attack_cannot_borrow_another_sessions_guessed_location",
        }
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [
                child.name for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            with self.subTest(test_class=node.name):
                # Runtime inspection alone cannot see overwritten definitions.
                self.assertEqual(
                    len(methods), len(set(methods)),
                    f"{node.name} contains duplicate method definitions",
                )
                defined_tests = {name for name in methods if name.startswith("test_")}
                test_class = getattr(sys.modules[__name__], node.name)
                discovered_tests = {
                    case.id().rsplit(".", 1)[-1]
                    for case in loader.loadTestsFromTestCase(test_class)
                }
                self.assertEqual(discovered_tests, defined_tests)
                if node.name == "SessionTests":
                    self.assertLessEqual(expected_session_tests, discovered_tests)


if __name__ == "__main__":
    unittest.main()
