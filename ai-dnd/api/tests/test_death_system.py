from __future__ import annotations

from pathlib import Path
import copy
import json
import random
import sys
import tempfile
import unittest
from unittest.mock import patch


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
import campaign_time
from api.serializers import serialize_session_state


def make_session(seed=17):
    session = game.GameSession(seed=seed)
    session.character.update({
        "name": "Test Adventurer",
        "race": "Human",
        "species": "Human",
        "class": "Fighter",
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
        "dexterity_mod": 0,
        "proficient_skills": [],
        "level": 1,
        "proficiency_bonus": 2,
        "max_hp": 20,
        "current_hp": 20,
        "armor_class": 1,
    })
    return session


def start_test_combat(session):
    enemy = {
        "id": "death-save-enemy",
        "name": "Death Save Enemy",
        "location": session.world_state["location"],
        "combat_status": "active",
        "current_hp": 10,
        "max_hp": 10,
        "armor_class": 10,
        "attack_bonus": 0,
        "damage_die": 8,
        "damage_dice": 1,
        "damage_modifier": 0,
    }
    enemy.update(distance_ft=5, attack_damage_type="bludgeoning")
    session.world_state["npcs"].append(enemy)
    with patch("game.roll_d20", side_effect=[20, 10]):
        session.start_combat(enemy)
    combat = session.world_state["combat"]
    player_index = combat["initiative_order"].index("player")
    combat["current_turn_index"] = player_index
    combat["current_actor_id"] = "player"


class DeathSystemTests(unittest.TestCase):
    def test_normal_mode_restores_precombat_state_after_massive_damage(self):
        session = make_session()
        rng_state = session.rng.getstate()
        game._capture_combat_death_checkpoint(session=session)

        result = game._apply_player_damage(
            40, critical=False, took_damage=True, session=session
        )

        self.assertTrue(result["death_resolution"]["rolled_back"])
        self.assertEqual(result["death_resolution"]["cause"], "massive_damage")
        self.assertEqual(session.character["current_hp"], 20)
        self.assertEqual(session.world_state["player_combat_status"], "active")
        self.assertIsNone(session.world_state["death_state"]["combat_checkpoint"])
        self.assertEqual(session.rng.getstate(), rng_state)

    def test_unconscious_melee_attack_has_advantage_and_automatically_criticals(self):
        session = make_session()
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"
        enemy = {
            "id": "test-enemy",
            "name": "Test Enemy",
            "location": session.world_state["location"],
            "combat_status": "active",
            "current_hp": 10,
            "max_hp": 10,
            "armor_class": 10,
            "attack_bonus": 0,
            "damage_die": 8,
            "damage_dice": 1,
            "damage_modifier": 0,
        }
        enemy.update(distance_ft=5, attack_damage_type="bludgeoning")
        session.world_state["npcs"].append(enemy)

        with (
            patch("game.roll_d20", side_effect=[10, 14]),
            patch("game.roll_damage", return_value=2),
        ):
            result = session.resolve_enemy_attack(enemy)

        self.assertEqual(result["attack_rolls"], [10, 14])
        self.assertTrue(result["critical"])
        self.assertEqual(session.world_state["death_state"]["failures"], 2)
        self.assertEqual(result["target_status"], "unconscious")

    def test_stable_unconscious_player_does_not_spin_the_combat_scheduler(self):
        session = make_session()
        start_test_combat(session)
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"
        session.world_state["death_state"]["stable"] = True
        combat = session.world_state["combat"]
        enemy_id = next(
            participant_id
            for participant_id in combat["initiative_order"]
            if participant_id != "player"
        )
        combat["current_turn_index"] = combat["initiative_order"].index(enemy_id)
        combat["current_actor_id"] = enemy_id
        game.ensure_combat_state(session=session)

        with patch(
            "game.resolve_enemy_attack",
            return_value={"action": "enemy_attack", "outcome": "miss"},
        ):
            result = game._resolve_enemy_turns_until_player(session=session)

        self.assertEqual(len(result), 1)
        self.assertTrue(session.world_state["death_state"]["stable"])
        self.assertEqual(
            session.world_state["combat"]["current_actor_id"],
            "player",
        )

    def test_death_save_turns_are_idempotent_and_normal_death_rolls_back(self):
        session = make_session()
        start_test_combat(session)
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"

        with patch("game.roll_d20", side_effect=[1, 1]) as die:
            first = game._resolve_player_death_turn(session=session)
            duplicate = game._resolve_player_death_turn(session=session)
            session.world_state["combat"]["round"] = 2
            player_index = session.world_state["combat"]["initiative_order"].index(
                "player"
            )
            session.world_state["combat"]["current_turn_index"] = player_index
            session.world_state["combat"]["current_actor_id"] = "player"
            fatal = game._resolve_player_death_turn(session=session)

        self.assertEqual(first["outcome"], "natural_1")
        self.assertEqual(duplicate, first)
        self.assertEqual(die.call_count, 2)
        self.assertEqual(fatal["outcome"], "rolled_back")
        self.assertTrue(fatal["death_resolution"]["rolled_back"])
        self.assertEqual(session.character["current_hp"], 20)
        self.assertFalse(session.world_state["death_state"]["dead"])
        self.assertFalse(session.world_state["combat"]["active"])

        public_state = serialize_session_state(session)
        self.assertEqual(public_state["death_state"]["mode"], "NORMAL")
        self.assertEqual(public_state["death_state"]["status"], "active")
        self.assertTrue(
            public_state["death_state"]["last_death_save"]["death_resolution"][
                "rolled_back"
            ]
        )

    def test_permadeath_and_ironman_finalize_death_without_normal_rollback(self):
        for mode, terminal in (
            ("PERMADEATH", False),
            ("IRONMAN", True),
        ):
            with self.subTest(mode=mode):
                session = make_session()
                death = session.world_state["death_state"]
                death["mode"] = mode
                death["failures"] = 2
                session.character["current_hp"] = 0
                session.world_state["player_combat_status"] = "unconscious"

                result = game._apply_player_damage(
                    1, took_damage=True, session=session
                )

                self.assertEqual(result["death_resolution"]["outcome"], "dead")
                self.assertEqual(result["death_resolution"]["cause"], "failed_death_saves")
                self.assertTrue(death["dead"])
                self.assertEqual(death["terminal"], terminal)
                self.assertEqual(session.world_state["player_combat_status"], "dead")

    def test_permadeath_committed_attack_survives_reopening(self):
        self._assert_committed_death_round_trip("PERMADEATH", terminal=False)

    def test_ironman_committed_attack_survives_reopening(self):
        self._assert_committed_death_round_trip("IRONMAN", terminal=True)

    def test_permadeath_fatal_death_save_survives_reopening(self):
        self._assert_fatal_death_save_round_trip("PERMADEATH", terminal=False)

    def test_ironman_fatal_death_save_survives_reopening(self):
        self._assert_fatal_death_save_round_trip("IRONMAN", terminal=True)

    def test_nonfatal_death_save_replays_after_reopening_until_next_player_turn(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, successes, failures in (
                (10, "success", 1, 0),
                (4, "failure", 0, 1),
                (1, "natural_1", 0, 2),
            ):
                with self.subTest(mode=mode, outcome=outcome):
                    self._assert_nonfatal_death_save_round_trip(
                        mode, roll, outcome, successes, failures
                    )

    def test_stable_recovery_deadline_survives_reopening_and_heals_once(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_stable_recovery_round_trip(mode)

    def test_zero_healing_preserves_stable_recovery_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_stable_recovery_round_trip(mode, zero_healing=True)

    def test_rejected_healing_preserves_stable_recovery_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for amount in (-1, 1.0, 1.5, "1", None, True, False):
                with self.subTest(mode=mode, amount=amount):
                    self._assert_stable_recovery_round_trip(
                        mode, rejected_healing=(amount,)
                    )

    def test_rejected_max_hp_preserves_stable_recovery_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for maximum in (-1, 1.0, 1.5, "1", None, True, False):
                with self.subTest(mode=mode, maximum=maximum):
                    self._assert_stable_recovery_round_trip(
                        mode, rejected_maximum=(maximum,)
                    )

    def test_positive_max_hp_change_preserves_stable_recovery_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            # Lowering to one also checks recovery at the new HP ceiling.
            for maximum in (1, 35):
                with self.subTest(mode=mode, maximum=maximum):
                    self._assert_stable_recovery_round_trip(
                        mode, positive_maximum=maximum
                    )

    def _assert_stable_recovery_round_trip(
        self, mode, *, zero_healing=False, rejected_healing=(), rejected_maximum=(),
        positive_maximum=None
    ):
        session = make_session()
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        campaign_time.initialize(session.world_state)
        campaign_time.initialize(peer.world_state)
        session.ensure_death_state()["mode"] = mode
        # A nonzero starting time and progress before saving distinguish the
        # absolute deadline from a fresh duration incorrectly scheduled on load.
        session.advance_campaign_time(137, "wait")
        session._apply_player_damage(20, took_damage=True)
        with patch.object(session.rng, "randint", return_value=2) as die:
            session.stabilize_player()
        die.assert_called_once_with(1, 4)
        recovery = copy.deepcopy(session.ensure_death_state()["recovery"])
        self.assertEqual(recovery, {"hours": 2, "at": 137 + 7200})
        session.advance_campaign_time(600, "wait")
        if positive_maximum is not None:
            expected = copy.deepcopy(session.serialize_game_state())
            self.assertEqual(session.character["max_hp"], 20)
            expected["player"]["max_hp"] = positive_maximum
            death_state = copy.deepcopy(session.ensure_death_state())
            clock = copy.deepcopy(session.world_state["campaign_time"])
            session_rng = session.rng.getstate()
            module_rng = random.getstate()
            with (
                patch.object(
                    session.rng, "randint",
                    side_effect=AssertionError("Positive HP maximum rerolled recovery"),
                ),
                patch("game.roll_d20", side_effect=AssertionError("Positive HP maximum rolled dice")),
            ):
                self.assertIsNone(session.set_player_max_hp(positive_maximum))
            self.assertEqual(session.serialize_game_state(), expected)
            self.assertEqual(session.character["max_hp"], positive_maximum)
            self.assertEqual(session.character["current_hp"], 0)
            self.assertEqual(session.world_state["player_combat_status"], "unconscious")
            self.assertEqual(session.ensure_death_state(), death_state)
            self.assertTrue(session.ensure_death_state()["stable"])
            self.assertEqual(session.ensure_death_state()["recovery"], recovery)
            self.assertEqual(session.world_state["campaign_time"], clock)
            self.assertEqual(session.rng.getstate(), session_rng)
            self.assertEqual(random.getstate(), module_rng)
            progress = session.advance_campaign_time(91, "wait")
            self.assertEqual(progress["death_results"], [])
            self.assertEqual(session.ensure_death_state()["recovery"], recovery)
        if rejected_maximum:
            before_maximum = session.serialize_game_state()
            maximum_hp = session.character["max_hp"]
            death_state = copy.deepcopy(session.ensure_death_state())
            clock = copy.deepcopy(session.world_state["campaign_time"])
            session_rng = session.rng.getstate()
            module_rng = random.getstate()
            with (
                patch.object(
                    session.rng, "randint",
                    side_effect=AssertionError("Rejected HP maximum rerolled recovery"),
                ),
                patch("game.roll_d20", side_effect=AssertionError("Rejected HP maximum rolled dice")),
            ):
                for maximum in rejected_maximum:
                    with self.assertRaisesRegex(ValueError, "^HP maximum is invalid\\.$"):
                        session.set_player_max_hp(maximum)
            self.assertEqual(session.serialize_game_state(), before_maximum)
            self.assertEqual(session.character["current_hp"], 0)
            self.assertEqual(session.character["max_hp"], maximum_hp)
            self.assertEqual(session.ensure_death_state(), death_state)
            self.assertTrue(session.ensure_death_state()["stable"])
            self.assertEqual(session.ensure_death_state()["recovery"], recovery)
            self.assertEqual(session.world_state["campaign_time"], clock)
            self.assertEqual(session.rng.getstate(), session_rng)
            self.assertEqual(random.getstate(), module_rng)
            # Additional progress before saving must not restart the deadline.
            progress = session.advance_campaign_time(91, "wait")
            self.assertEqual(progress["death_results"], [])
            self.assertEqual(session.ensure_death_state()["recovery"], recovery)
        if zero_healing or rejected_healing:
            before_healing = session.serialize_game_state()
            healing_rng = session.rng.getstate()
            module_healing_rng = random.getstate()
            healing_clock = copy.deepcopy(session.world_state["campaign_time"])
            with (
                patch.object(
                    session.rng, "randint",
                    side_effect=AssertionError("Non-healing input rerolled recovery"),
                ),
                patch("game.roll_d20", side_effect=AssertionError("Non-healing input rolled dice")),
            ):
                if zero_healing:
                    self.assertEqual(session.heal_player(0), 0)
                for amount in rejected_healing:
                    with self.assertRaisesRegex(ValueError, "^Healing amount is invalid\\.$"):
                        session.heal_player(amount)
            self.assertEqual(session.serialize_game_state(), before_healing)
            self.assertEqual(session.rng.getstate(), healing_rng)
            self.assertEqual(random.getstate(), module_healing_rng)
            self.assertEqual(session.world_state["campaign_time"], healing_clock)
            self.assertEqual(session.character["current_hp"], 0)
            self.assertEqual(session.world_state["player_combat_status"], "unconscious")
            self.assertTrue(session.ensure_death_state()["stable"])
            self.assertEqual(session.ensure_death_state()["recovery"], recovery)
            # Saving later must retain the original deadline, not restart the
            # two-hour duration from the healing input or reopening.
            progress = session.advance_campaign_time(91, "wait")
            self.assertEqual(progress["death_results"], [])
            self.assertEqual(session.ensure_death_state()["recovery"], recovery)
        session.messages.append({"role": "user", "content": "Source history"})
        peer.messages.append({"role": "user", "content": "Unrelated history"})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stable.json"
            peer_path = Path(directory) / "unrelated.json"
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            saved_bytes = path.read_bytes()
            peer_bytes = peer_path.read_bytes()
            committed = session.serialize_game_state()
            self.assertEqual(json.loads(saved_bytes), committed)
            owners = (session, peer, game._DEFAULT_SESSION)
            snapshots = [owner.serialize_game_state() for owner in owners]
            rng_states = [owner.rng.getstate() for owner in owners]
            histories = [copy.deepcopy(owner.messages) for owner in owners]
            module_rng = random.getstate()
            load_rng = reopened.rng.getstate()
            reopened.messages.append({"role": "user", "content": "Reopen history"})
            load_history = copy.deepcopy(reopened.messages)

            def assert_preserved():
                for owner, snapshot, rng_state, history in zip(
                    owners, snapshots, rng_states, histories
                ):
                    self.assertEqual(owner.serialize_game_state(), snapshot)
                    self.assertEqual(owner.rng.getstate(), rng_state)
                    self.assertEqual(owner.messages, history)
                self.assertEqual(random.getstate(), module_rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(reopened.rng.getstate(), load_rng)
                self.assertEqual(reopened.messages, load_history)
                self.assertEqual(path.read_bytes(), saved_bytes)
                self.assertEqual(peer_path.read_bytes(), peer_bytes)
                self.assertEqual(set(Path(directory).iterdir()), {path, peer_path})

            with (
                patch.object(
                    reopened.rng, "randint",
                    side_effect=AssertionError("Load or recovery rolled dice"),
                ),
                patch(
                    "game.roll_d20",
                    side_effect=AssertionError("Stable recovery rolled a death save"),
                ),
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                self.assertEqual(reopened.load_game(path), committed)
                self.assertEqual(reopened.serialize_game_state(), committed)
                self.assertEqual(reopened.ensure_death_state()["recovery"], recovery)
                self.assertIsNot(reopened.world_state, session.world_state)
                self.assertIsNot(reopened.character, session.character)
                self.assertIsNot(
                    reopened.ensure_death_state()["recovery"],
                    session.ensure_death_state()["recovery"],
                )
                heal.assert_not_called()
                assert_preserved()

                now = reopened.world_state["campaign_time"]["elapsed_seconds"]
                before = reopened.advance_campaign_time(recovery["at"] - now - 1, "wait")
                self.assertEqual(before["death_results"], [])
                self.assertEqual(
                    reopened.world_state["campaign_time"]["elapsed_seconds"],
                    recovery["at"] - 1,
                )
                self.assertEqual(reopened.character["current_hp"], 0)
                self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                self.assertTrue(reopened.ensure_death_state()["stable"])
                self.assertEqual(reopened.ensure_death_state()["recovery"], recovery)
                heal.assert_not_called()
                assert_preserved()

                due = reopened.advance_campaign_time(1, "wait")
                self.assertEqual(
                    reopened.world_state["campaign_time"]["elapsed_seconds"], recovery["at"]
                )
                self.assertEqual(
                    due["death_results"], [{"action": "stable_recovery", "current_hp": 1}]
                )
                self.assertEqual(reopened.character["current_hp"], 1)
                self.assertEqual(reopened.character["max_hp"], committed["player"]["max_hp"])
                self.assertLessEqual(reopened.character["current_hp"], reopened.character["max_hp"])
                self.assertEqual(reopened.world_state["player_combat_status"], "active")
                self.assertFalse(reopened.ensure_death_state()["stable"])
                self.assertFalse(reopened.ensure_death_state()["dead"])
                self.assertFalse(reopened.ensure_death_state()["terminal"])
                self.assertEqual(reopened.ensure_death_state()["mode"], mode)
                self.assertIsNone(reopened.ensure_death_state()["recovery"])
                heal.assert_called_once_with(1)
                assert_preserved()

                later = reopened.advance_campaign_time(7200, "wait")
                self.assertEqual(later["death_results"], [])
                self.assertEqual(reopened.character["current_hp"], 1)
                self.assertEqual(reopened.character["max_hp"], committed["player"]["max_hp"])
                self.assertIsNone(reopened.ensure_death_state()["recovery"])
                heal.assert_called_once_with(1)
                assert_preserved()

    def test_healing_cancelled_stable_recovery_stays_cancelled_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_cancelled_recovery_round_trip(mode, healed=True)

    def test_damage_cancelled_stable_recovery_stays_cancelled_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_cancelled_recovery_round_trip(mode, healed=False)

    def _assert_cancelled_recovery_round_trip(self, mode, *, healed):
        session = make_session()
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        campaign_time.initialize(session.world_state)
        campaign_time.initialize(peer.world_state)
        session.ensure_death_state()["mode"] = mode
        session.advance_campaign_time(137, "wait")
        session._apply_player_damage(20, took_damage=True)
        with patch.object(session.rng, "randint", return_value=2) as die:
            session.stabilize_player()
        die.assert_called_once_with(1, 4)
        cancelled_recovery = copy.deepcopy(session.ensure_death_state()["recovery"])
        self.assertEqual(cancelled_recovery, {"hours": 2, "at": 137 + 7200})
        session.advance_campaign_time(600, "wait")
        cancelled_at = session.world_state["campaign_time"]["elapsed_seconds"]
        if healed:
            self.assertEqual(session.heal_player(3), 3)
        else:
            damage = session._apply_player_damage(1, took_damage=True)
            self.assertIsNone(damage["death_resolution"])
        death = session.ensure_death_state()
        self.assertIsNone(death["recovery"])
        self.assertFalse(death["stable"])
        self.assertFalse(death["dead"])
        self.assertFalse(death["terminal"])
        self.assertEqual(death["successes"], 0)
        self.assertEqual(death["failures"], 0 if healed else 1)
        self.assertEqual(
            death["noncombat_next_save_at"], None if healed else cancelled_at + 6
        )
        self.assertEqual(session.character["current_hp"], 3 if healed else 0)
        self.assertEqual(
            session.world_state["player_combat_status"],
            "active" if healed else "unconscious",
        )
        session.messages.append({"role": "user", "content": "Source history"})
        peer.messages.append({"role": "user", "content": "Unrelated history"})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cancelled-recovery.json"
            peer_path = Path(directory) / "unrelated.json"
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            saved_bytes = path.read_bytes()
            peer_bytes = peer_path.read_bytes()
            saved_files = {path: saved_bytes, peer_path: peer_bytes}
            committed = session.serialize_game_state()
            self.assertEqual(json.loads(saved_bytes), committed)
            owners = (session, peer, game._DEFAULT_SESSION)
            snapshots = [owner.serialize_game_state() for owner in owners]
            rng_states = [owner.rng.getstate() for owner in owners]
            histories = [copy.deepcopy(owner.messages) for owner in owners]
            module_rng = random.getstate()
            load_rng = reopened.rng.getstate()
            reopened.messages.append({"role": "user", "content": "Reopen history"})
            load_history = copy.deepcopy(reopened.messages)

            def assert_preserved():
                for owner, snapshot, rng_state, history in zip(
                    owners, snapshots, rng_states, histories
                ):
                    self.assertEqual(owner.serialize_game_state(), snapshot)
                    self.assertEqual(owner.rng.getstate(), rng_state)
                    self.assertEqual(owner.messages, history)
                self.assertEqual(random.getstate(), module_rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(reopened.rng.getstate(), load_rng)
                self.assertEqual(reopened.messages, load_history)
                for saved_path, content in saved_files.items():
                    self.assertEqual(saved_path.read_bytes(), content)
                self.assertEqual(set(Path(directory).iterdir()), set(saved_files))

            with (
                patch.object(
                    reopened.rng, "randint",
                    side_effect=AssertionError("Loading cancelled recovery rolled dice"),
                ),
                patch("game.roll_d20", side_effect=AssertionError("Load rolled a death save")),
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                self.assertEqual(reopened.load_game(path), committed)
                self.assertEqual(reopened.serialize_game_state(), committed)
                self.assertEqual(reopened.ensure_death_state(), death)
                self.assertIsNot(reopened.world_state, session.world_state)
                self.assertIsNot(reopened.character, session.character)
                self.assertIsNot(reopened.ensure_death_state(), death)
                heal.assert_not_called()
                assert_preserved()

            # Damage legitimately restarts noncombat death saves. Three successes
            # stabilize again, with a NEW four-hour recovery later than the old
            # deadline. Neither that stabilization nor real healing may resurrect
            # the cancelled two-hour episode.
            with (
                patch("game.roll_d20", side_effect=[10, 10, 10]) as death_die,
                patch.object(reopened.rng, "randint", return_value=4) as recovery_die,
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                now = reopened.world_state["campaign_time"]["elapsed_seconds"]
                before = reopened.advance_campaign_time(
                    cancelled_recovery["at"] - now - 1, "wait"
                )
                self.assertEqual(
                    reopened.world_state["campaign_time"]["elapsed_seconds"],
                    cancelled_recovery["at"] - 1,
                )
                if healed:
                    self.assertEqual(before["death_results"], [])
                    death_die.assert_not_called()
                    recovery_die.assert_not_called()
                    expected_death = copy.deepcopy(death)
                else:
                    self.assertEqual(
                        [result["action"] for result in before["death_results"]],
                        ["death_save"] * 3,
                    )
                    self.assertEqual(
                        [result["death_save"]["outcome"] for result in before["death_results"]],
                        ["success", "success", "stable"],
                    )
                    self.assertEqual(death_die.call_count, 3)
                    recovery_die.assert_called_once_with(1, 4)
                    expected_death = copy.deepcopy(reopened.ensure_death_state())
                    self.assertTrue(expected_death["stable"])
                    self.assertEqual(
                        (expected_death["successes"], expected_death["failures"]), (0, 0)
                    )
                    self.assertEqual(
                        expected_death["recovery"],
                        {"hours": 4, "at": cancelled_at + 18 + 14400},
                    )
                    self.assertIsNone(expected_death["noncombat_next_save_at"])
                self.assertFalse(expected_death["dead"])
                self.assertFalse(expected_death["terminal"])
                self.assertEqual(expected_death["mode"], mode)
                heal.assert_not_called()
                assert_preserved()

                if not healed:
                    replacement_path, replacement_bytes = (
                        self._assert_replacement_recovery_second_reopening(
                            mode, reopened, owners, path, peer_path, cancelled_recovery
                        )
                    )
                    saved_files[replacement_path] = replacement_bytes
                    assert_preserved()
                    return

                for duration, expected_time in (
                    (1, cancelled_recovery["at"]),
                    (7200, cancelled_recovery["at"] + 7200),
                ):
                    result = reopened.advance_campaign_time(duration, "wait")
                    self.assertEqual(result["death_results"], [])
                    self.assertEqual(
                        reopened.world_state["campaign_time"]["elapsed_seconds"], expected_time
                    )
                    self.assertEqual(reopened.character["current_hp"], 3 if healed else 0)
                    self.assertEqual(
                        reopened.world_state["player_combat_status"],
                        "active" if healed else "unconscious",
                    )
                    self.assertEqual(reopened.ensure_death_state(), expected_death)
                    self.assertEqual(death_die.call_count, 0 if healed else 3)
                    self.assertEqual(recovery_die.call_count, 0 if healed else 1)
                    heal.assert_not_called()
                    assert_preserved()

    def _assert_replacement_recovery_second_reopening(
        self, mode, source, owners, cancelled_path, peer_path, cancelled_recovery
    ):
        # Persist after stabilization and time already spent on the replacement
        # episode: loading must retain its absolute deadline, not restart four hours.
        replacement = copy.deepcopy(source.ensure_death_state()["recovery"])
        expected_death = copy.deepcopy(source.ensure_death_state())
        self.assertLess(cancelled_recovery["at"], replacement["at"])
        replacement_path = cancelled_path.with_name("replacement-recovery.json")
        self.assertEqual(source.save_game(replacement_path), replacement_path)
        committed = source.serialize_game_state()
        paths = (cancelled_path, peer_path, replacement_path)
        saved_bytes = {path: path.read_bytes() for path in paths}
        self.assertEqual(json.loads(saved_bytes[replacement_path]), committed)
        protected = (*owners, source)
        snapshots = [owner.serialize_game_state() for owner in protected]
        rng_states = [owner.rng.getstate() for owner in protected]
        histories = [copy.deepcopy(owner.messages) for owner in protected]
        module_rng = random.getstate()
        second = make_session(seed=101)
        second.messages.append({"role": "user", "content": "Second reopen history"})
        second_rng = second.rng.getstate()
        second_history = copy.deepcopy(second.messages)

        def assert_preserved():
            for owner, snapshot, rng_state, history in zip(
                protected, snapshots, rng_states, histories
            ):
                self.assertEqual(owner.serialize_game_state(), snapshot)
                self.assertEqual(owner.rng.getstate(), rng_state)
                self.assertEqual(owner.messages, history)
            self.assertEqual(random.getstate(), module_rng)
            self.assertIs(game._session(), game._DEFAULT_SESSION)
            self.assertEqual(second.rng.getstate(), second_rng)
            self.assertEqual(second.messages, second_history)
            for path, content in saved_bytes.items():
                self.assertEqual(path.read_bytes(), content)
            self.assertEqual(set(cancelled_path.parent.iterdir()), set(paths))

        with (
            patch.object(
                second.rng, "randint",
                side_effect=AssertionError("Replacement load or recovery rolled dice"),
            ),
            patch(
                "game.roll_d20",
                side_effect=AssertionError("Replacement recovery rolled a death save"),
            ),
            patch("game.heal_player", wraps=game.heal_player) as heal,
        ):
            self.assertEqual(second.load_game(replacement_path), committed)
            self.assertEqual(second.serialize_game_state(), committed)
            self.assertEqual(second.ensure_death_state(), expected_death)
            for owner in protected:
                self.assertIsNot(second.world_state, owner.world_state)
                self.assertIsNot(second.character, owner.character)
                self.assertIsNot(
                    second.ensure_death_state(), owner.ensure_death_state()
                )
            self.assertIsNot(
                second.ensure_death_state()["recovery"],
                source.ensure_death_state()["recovery"],
            )
            heal.assert_not_called()
            assert_preserved()

            # The saved episode is one second before the cancelled deadline.
            # Crossing that deadline must not revive the player or alter the
            # replacement episode; neither may the second load reschedule it.
            self.assertEqual(
                second.world_state["campaign_time"]["elapsed_seconds"],
                cancelled_recovery["at"] - 1,
            )
            for deadline in (cancelled_recovery["at"], replacement["at"] - 1):
                now = second.world_state["campaign_time"]["elapsed_seconds"]
                result = second.advance_campaign_time(deadline - now, "wait")
                self.assertEqual(result["death_results"], [])
                self.assertEqual(
                    second.world_state["campaign_time"]["elapsed_seconds"], deadline
                )
                self.assertEqual(second.character["current_hp"], 0)
                self.assertEqual(second.world_state["player_combat_status"], "unconscious")
                self.assertEqual(second.ensure_death_state(), expected_death)
                heal.assert_not_called()
                assert_preserved()

            due = second.advance_campaign_time(1, "wait")
            self.assertEqual(
                second.world_state["campaign_time"]["elapsed_seconds"], replacement["at"]
            )
            self.assertEqual(
                due["death_results"], [{"action": "stable_recovery", "current_hp": 1}]
            )
            self.assertEqual(second.character["current_hp"], 1)
            self.assertEqual(second.world_state["player_combat_status"], "active")
            death = second.ensure_death_state()
            self.assertFalse(death["stable"])
            self.assertFalse(death["dead"])
            self.assertFalse(death["terminal"])
            self.assertEqual(death["mode"], mode)
            self.assertIsNone(death["recovery"])
            self.assertIsNone(death["noncombat_next_save_at"])
            heal.assert_called_once_with(1)
            assert_preserved()

            later = second.advance_campaign_time(14400, "wait")
            self.assertEqual(later["death_results"], [])
            self.assertEqual(second.character["current_hp"], 1)
            self.assertEqual(second.world_state["player_combat_status"], "active")
            self.assertIsNone(second.ensure_death_state()["recovery"])
            heal.assert_called_once_with(1)
            assert_preserved()

        return replacement_path, saved_bytes[replacement_path]

    def _assert_nonfatal_death_save_round_trip(
        self, mode, roll, outcome, successes, failures
    ):
        session = make_session()
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        session.world_state["death_state"]["mode"] = mode
        start_test_combat(session)
        session.ensure_campaign_clock()
        peer.ensure_campaign_clock()
        peer.character["name"] = "Unrelated Adventurer"
        peer.messages.append({"role": "user", "content": "Unrelated message"})
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"
        combat = session.world_state["combat"]
        combat_id, round_number = combat["combat_id"], combat["round"]
        turn_key = f"{combat_id}:{round_number}"
        unrelated = (peer, game._DEFAULT_SESSION)
        snapshots = [owner.serialize_game_state() for owner in unrelated]
        rng_states = [owner.rng.getstate() for owner in unrelated]
        messages = [copy.deepcopy(owner.messages) for owner in unrelated]
        module_rng = random.getstate()

        def assert_isolation():
            for owner, snapshot, rng_state, history in zip(
                unrelated, snapshots, rng_states, messages
            ):
                self.assertEqual(owner.serialize_game_state(), snapshot)
                self.assertEqual(owner.rng.getstate(), rng_state)
                self.assertEqual(owner.messages, history)
            self.assertEqual(random.getstate(), module_rng)
            self.assertIs(game._session(), game._DEFAULT_SESSION)

        def assert_nonfatal(owner, expected_successes, expected_failures):
            death = owner.world_state["death_state"]
            self.assertEqual(death["mode"], mode)
            self.assertEqual(death["successes"], expected_successes)
            self.assertEqual(death["failures"], expected_failures)
            self.assertFalse(death["stable"])
            self.assertFalse(death["dead"])
            self.assertFalse(death["terminal"])
            self.assertEqual(owner.character["current_hp"], 0)
            self.assertEqual(owner.world_state["player_combat_status"], "unconscious")
            self.assertTrue(owner.world_state["combat"]["active"])
            self.assertEqual(owner.world_state["combat"]["combat_id"], combat_id)
            self.assertEqual(owner.world_state["combat"]["current_actor_id"], "player")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nonfatal.json"
            peer_path = Path(directory) / "unrelated.json"
            self.assertEqual(peer.save_game(peer_path), peer_path)
            peer_bytes = peer_path.read_bytes()
            with patch("game.roll_d20", return_value=roll) as die:
                first = game._resolve_player_death_turn(session=session)
            die.assert_called_once_with()
            self.assertEqual(first["roll"], roll)
            self.assertEqual(first["outcome"], outcome)
            self.assertEqual(first["successes"], successes)
            self.assertEqual(first["failures"], failures)
            self.assertFalse(first["dead"])
            self.assertFalse(first["stable"])
            assert_nonfatal(session, successes, failures)
            self.assertEqual(
                session.world_state["death_state"]["last_death_save_turn_key"],
                turn_key,
            )
            committed = session.serialize_game_state()
            self.assertEqual(session.save_game(path), path)
            committed_bytes = path.read_bytes()
            self.assertEqual(json.loads(committed_bytes), committed)
            source_rng = session.rng.getstate()
            source_messages = copy.deepcopy(session.messages)
            reopened.messages.append({"role": "user", "content": "Reopen save"})
            rng_at_load = reopened.rng.getstate()
            messages_at_load = copy.deepcopy(reopened.messages)
            held = (reopened.world_state, reopened.character,
                    reopened.recent_dm_narrations, reopened.messages, reopened.rng)

            with (
                patch("game.roll_d20", side_effect=AssertionError("Replay rolled dice")),
                patch.object(reopened.rng, "randint",
                             side_effect=AssertionError("Load or replay rolled dice")),
            ):
                self.assertEqual(reopened.load_game(path), committed)
                assert_nonfatal(reopened, successes, failures)
                self.assertEqual(
                    reopened.world_state["death_state"]["last_death_save_turn_key"],
                    turn_key,
                )
                duplicate = game._resolve_player_death_turn(session=reopened)
                self.assertEqual(duplicate, first)
                self.assertIsNot(
                    duplicate,
                    reopened.world_state["death_state"]["last_death_save_result"],
                )
                self.assertEqual(reopened.serialize_game_state(), committed)
                self.assertEqual(reopened.rng.getstate(), rng_at_load)
                # Advance through the enemy slot without resolving an attack.
                advanced, actor_id, _ = reopened.advance_combat_turn()
                self.assertTrue(advanced)
                self.assertNotEqual(actor_id, "player")
                advanced, actor_id, round_changed = reopened.advance_combat_turn()
                self.assertTrue(advanced)
                self.assertEqual(actor_id, "player")
                self.assertTrue(round_changed)
            self.assertEqual(reopened.world_state["combat"]["round"], round_number + 1)
            assert_nonfatal(reopened, successes, failures)
            self.assertEqual(reopened.rng.getstate(), rng_at_load)
            for actual, reference in zip(
                (reopened.world_state, reopened.character,
                 reopened.recent_dm_narrations, reopened.messages, reopened.rng), held
            ):
                self.assertIs(actual, reference)
            self.assertIsNot(reopened.world_state, session.world_state)
            self.assertIsNot(reopened.character, session.character)
            self.assertIsNot(
                reopened.world_state["death_state"]["last_death_save_result"],
                session.world_state["death_state"]["last_death_save_result"],
            )
            reference_rng = random.Random()
            reference_rng.setstate(rng_at_load)
            next_roll = reference_rng.randint(1, 20)
            # This seed supplies a nonfatal success for every initial case.
            self.assertTrue(10 <= next_roll < 20)
            with patch.object(
                reopened.rng, "randint", wraps=reopened.rng.randint
            ) as die:
                second = game._resolve_player_death_turn(session=reopened)
                after_second = reopened.serialize_game_state()
                second_duplicate = game._resolve_player_death_turn(session=reopened)
            die.assert_called_once_with(1, 20)
            self.assertEqual(second["roll"], next_roll)
            self.assertEqual(second["outcome"], "success")
            self.assertEqual(second_duplicate, second)
            self.assertEqual(reopened.serialize_game_state(), after_second)
            self.assertEqual(reopened.rng.getstate(), reference_rng.getstate())
            assert_nonfatal(reopened, successes + 1, failures)
            self.assertEqual(
                reopened.world_state["death_state"]["last_death_save_turn_key"],
                f"{combat_id}:{round_number + 1}",
            )
            self.assertEqual(
                reopened.world_state["death_state"]["last_death_save_result"], second
            )
            self.assertEqual(reopened.messages, messages_at_load)
            self.assertEqual(session.serialize_game_state(), committed)
            self.assertEqual(session.rng.getstate(), source_rng)
            self.assertEqual(session.messages, source_messages)
            self.assertEqual(path.read_bytes(), committed_bytes)
            self.assertEqual(peer_path.read_bytes(), peer_bytes)
            self.assertEqual(set(Path(directory).iterdir()), {path, peer_path})
            assert_isolation()

    def test_natural_twenty_revival_survives_reopening_without_another_death_save(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_natural_twenty_revival_round_trip(mode)

    def _assert_natural_twenty_revival_round_trip(self, mode):
        session = make_session()
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        session.world_state["death_state"]["mode"] = mode
        start_test_combat(session)
        session.ensure_campaign_clock()
        peer.ensure_campaign_clock()
        peer.character["name"] = "Unrelated Adventurer"
        peer.recent_dm_narrations.append("Unrelated campaign history")
        peer.messages.append({"role": "user", "content": "Unrelated message"})
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"
        # Nonzero counters prove revival resets them rather than retaining defaults.
        session.world_state["death_state"].update(successes=2, failures=2)
        combat = session.world_state["combat"]
        turn_key = f"{combat['combat_id']}:{combat['round']}"
        unrelated = (peer, game._DEFAULT_SESSION)
        snapshots = [owner.serialize_game_state() for owner in unrelated]
        rng_states = [owner.rng.getstate() for owner in unrelated]
        messages = [copy.deepcopy(owner.messages) for owner in unrelated]
        module_rng = random.getstate()

        def assert_isolation():
            for owner, snapshot, rng_state, history in zip(
                unrelated, snapshots, rng_states, messages
            ):
                self.assertEqual(owner.serialize_game_state(), snapshot)
                self.assertEqual(owner.rng.getstate(), rng_state)
                self.assertEqual(owner.messages, history)
            self.assertEqual(random.getstate(), module_rng)
            self.assertIs(game._session(), game._DEFAULT_SESSION)

        def assert_revived(owner):
            self.assertEqual(owner.character["current_hp"], 1)
            self.assertEqual(owner.world_state["player_combat_status"], "active")
            death = owner.world_state["death_state"]
            self.assertEqual(death["mode"], mode)
            self.assertTrue(death["prone"])
            self.assertEqual((death["successes"], death["failures"]), (0, 0))
            self.assertFalse(death["stable"])
            self.assertFalse(death["dead"])
            self.assertFalse(death["terminal"])
            self.assertEqual(death["last_death_save_turn_key"], turn_key)
            self.assertEqual(death["last_death_save_result"], result)
            current_combat = owner.world_state["combat"]
            self.assertTrue(current_combat["active"])
            self.assertEqual(current_combat["combat_id"], combat["combat_id"])
            self.assertEqual(current_combat["round"], combat["round"])
            self.assertEqual(current_combat["current_actor_id"], "player")
            public_death = serialize_session_state(owner)["death_state"]
            self.assertEqual(public_death["status"], "active")
            self.assertTrue(public_death["prone"])
            self.assertEqual(
                public_death["last_death_save"],
                {key: value for key, value in result.items() if value is not None},
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "revived.json"
            peer_path = Path(directory) / "unrelated.json"
            self.assertEqual(peer.save_game(peer_path), peer_path)
            peer_bytes = peer_path.read_bytes()
            with patch("game.roll_d20", return_value=20) as die:
                result = game._resolve_player_death_turn(session=session)
            die.assert_called_once_with()
            self.assertEqual(result["roll"], 20)
            self.assertEqual(result["outcome"], "revived")
            self.assertEqual((result["successes"], result["failures"]), (0, 0))
            self.assertTrue(result["prone"])
            self.assertFalse(result["stable"])
            self.assertFalse(result["dead"])
            self.assertNotIn("death_resolution", result)
            assert_revived(session)
            assert_isolation()
            committed = session.serialize_game_state()
            self.assertEqual(session.save_game(path), path)
            committed_bytes = path.read_bytes()
            self.assertEqual(json.loads(committed_bytes), committed)
            source_rng = session.rng.getstate()
            source_messages = copy.deepcopy(session.messages)

            reopened.character["name"] = "Unsaved replacement"
            reopened.recent_dm_narrations.append("Unsaved replacement history")
            reopened.messages.append({"role": "user", "content": "Reopen save"})
            reopened.rng.random()
            rng_at_load = reopened.rng.getstate()
            messages_at_load = copy.deepcopy(reopened.messages)
            held = (reopened.world_state, reopened.character,
                    reopened.recent_dm_narrations, reopened.messages, reopened.rng)
            self.assertNotEqual(reopened.serialize_game_state(), committed)
            with (
                patch("game.roll_d20",
                      side_effect=AssertionError("Revived player rolled a death save")),
                patch.object(reopened.rng, "randint",
                             side_effect=AssertionError("Load or retry rolled dice")),
                patch.object(session.rng, "randint",
                             side_effect=AssertionError("Source rolled dice")),
                patch.object(peer.rng, "randint",
                             side_effect=AssertionError("Peer rolled dice")),
                patch.object(game._DEFAULT_SESSION.rng, "randint",
                             side_effect=AssertionError("Default session rolled dice")),
            ):
                self.assertEqual(reopened.load_game(path), committed)
                assert_revived(reopened)
                # Unlike an unconscious replay, consciousness takes precedence
                # over the stored result for this same scheduled turn.
                self.assertIsNone(game._resolve_player_death_turn(session=reopened))
                self.assertIsNone(game._resolve_player_death_turn(session=reopened))
                assert_revived(reopened)
            self.assertEqual(reopened.serialize_game_state(), committed)
            self.assertEqual(reopened.rng.getstate(), rng_at_load)
            self.assertEqual(reopened.messages, messages_at_load)
            for actual, reference in zip(
                (reopened.world_state, reopened.character,
                 reopened.recent_dm_narrations, reopened.messages, reopened.rng), held
            ):
                self.assertIs(actual, reference)
            self.assertIsNot(reopened.world_state, session.world_state)
            self.assertIsNot(reopened.character, session.character)
            self.assertIsNot(reopened.rng, session.rng)
            self.assertIsNot(reopened.rng, peer.rng)
            self.assertIsNot(
                reopened.world_state["death_state"]["last_death_save_result"],
                session.world_state["death_state"]["last_death_save_result"],
            )
            self.assertEqual(session.serialize_game_state(), committed)
            self.assertEqual(session.rng.getstate(), source_rng)
            self.assertEqual(session.messages, source_messages)
            assert_isolation()
            self.assertEqual(path.read_bytes(), committed_bytes)
            self.assertEqual(peer_path.read_bytes(), peer_bytes)
            self.assertEqual(set(Path(directory).iterdir()), {path, peer_path})

    def _assert_fatal_death_save_round_trip(self, mode, *, terminal):
        session = make_session()
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        session.world_state["death_state"]["mode"] = mode
        start_test_combat(session)
        session.ensure_campaign_clock()
        peer.ensure_campaign_clock()
        peer.character["name"] = "Unrelated Adventurer"
        peer.recent_dm_narrations.append("Unrelated campaign history")
        peer.messages.append({"role": "user", "content": "Unrelated message"})
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"
        session.world_state["death_state"]["failures"] = 2
        combat = session.world_state["combat"]
        turn_key = f"{combat['combat_id']}:{combat['round']}"
        expected_resolution = {
            "mode": mode, "outcome": "dead", "cause": "failed_death_saves",
            "rolled_back": False, "terminal": terminal,
        }
        default_before = game.serialize_game_state()
        default_rng = game._DEFAULT_SESSION.rng.getstate()
        default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
        module_rng = random.getstate()
        peer_before = peer.serialize_game_state()
        peer_rng = peer.rng.getstate()
        peer_messages = copy.deepcopy(peer.messages)

        def assert_isolation():
            self.assertEqual(peer.serialize_game_state(), peer_before)
            self.assertEqual(peer.rng.getstate(), peer_rng)
            self.assertEqual(peer.messages, peer_messages)
            self.assertEqual(game.serialize_game_state(), default_before)
            self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), default_rng)
            self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
            self.assertEqual(random.getstate(), module_rng)
            self.assertIs(game._session(), game._DEFAULT_SESSION)

        def assert_death_state(owner):
            self.assertEqual(owner.character["current_hp"], 0)
            self.assertEqual(owner.world_state["player_combat_status"], "dead")
            death = owner.world_state["death_state"]
            self.assertEqual(death["mode"], mode)
            self.assertTrue(death["dead"])
            self.assertFalse(death["stable"])
            self.assertEqual(death["failures"], 3)
            self.assertEqual(death["terminal"], terminal)
            self.assertEqual(death["last_resolution"], expected_resolution)
            self.assertEqual(death["last_death_save_turn_key"], turn_key)
            self.assertEqual(death["last_death_save_result"], result)
            self.assertFalse(owner.world_state["combat"]["active"])
            self.assertEqual(owner.world_state["combat"]["end_reason"], "player_dead")
            public_death = serialize_session_state(owner)["death_state"]
            self.assertEqual(public_death["status"], "dead")
            self.assertEqual(public_death["terminal"], terminal)
            self.assertEqual(public_death["last_resolution"], expected_resolution)
            # Public projections omit optional None-valued receipt identifiers.
            self.assertEqual(
                public_death["last_death_save"],
                {key: value for key, value in result.items() if value is not None},
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{mode.lower()}.json"
            peer_path = Path(directory) / "unrelated.json"
            predeath = session.serialize_game_state()
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            predeath_bytes = path.read_bytes()
            peer_bytes = peer_path.read_bytes()
            # Only the scheduled death save can finalize this death, not damage.
            with (
                patch("game.roll_d20", return_value=4) as die,
                patch("game.resolve_enemy_attack",
                      side_effect=AssertionError("Death save ran an enemy attack")),
                patch("game._apply_player_damage",
                      side_effect=AssertionError("Death save applied damage")),
            ):
                result = game._resolve_player_death_turn(session=session)
            die.assert_called_once_with()
            self.assertEqual(result["roll"], 4)
            self.assertEqual(result["outcome"], "dead")
            self.assertEqual(result["successes"], 0)
            self.assertEqual(result["failures"], 3)
            self.assertTrue(result["dead"])
            self.assertFalse(result["stable"])
            self.assertEqual(result["death_resolution"], expected_resolution)
            assert_death_state(session)
            assert_isolation()
            # Finalization must neither delete nor overwrite either existing save.
            self.assertEqual(path.read_bytes(), predeath_bytes)
            self.assertEqual(json.loads(predeath_bytes), predeath)
            self.assertEqual(peer_path.read_bytes(), peer_bytes)
            committed = session.serialize_game_state()
            source_rng = session.rng.getstate()
            source_messages = copy.deepcopy(session.messages)
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), committed)
            committed_bytes = path.read_bytes()

            reopened.character["name"] = "Unsaved replacement"
            reopened.recent_dm_narrations.append("Unsaved replacement history")
            reopened.messages.append({"role": "user", "content": "Reopen save"})
            reopened.rng.random()
            rng_at_load = reopened.rng.getstate()
            messages_at_load = copy.deepcopy(reopened.messages)
            held = (reopened.world_state, reopened.character,
                    reopened.recent_dm_narrations, reopened.messages, reopened.rng)
            self.assertNotEqual(reopened.serialize_game_state(), committed)
            with (
                patch("game.roll_d20", side_effect=AssertionError("Reopen rolled dice")),
                patch.object(reopened.rng, "randint",
                             side_effect=AssertionError("Load rolled dice")),
                patch.object(session.rng, "randint",
                             side_effect=AssertionError("Source rolled dice")),
                patch.object(peer.rng, "randint",
                             side_effect=AssertionError("Peer rolled dice")),
                patch.object(game._DEFAULT_SESSION.rng, "randint",
                             side_effect=AssertionError("Default session rolled dice")),
            ):
                self.assertEqual(reopened.load_game(path), committed)
                assert_death_state(reopened)
                # A reopened terminal/dead turn must not roll or finalize again.
                self.assertIsNone(game._resolve_player_death_turn(session=reopened))
            self.assertEqual(reopened.serialize_game_state(), committed)
            self.assertEqual(reopened.rng.getstate(), rng_at_load)
            self.assertEqual(reopened.messages, messages_at_load)
            for actual, reference in zip(
                (reopened.world_state, reopened.character,
                 reopened.recent_dm_narrations, reopened.messages, reopened.rng), held
            ):
                self.assertIs(actual, reference)
            self.assertIsNot(reopened.world_state, session.world_state)
            self.assertIsNot(reopened.character, session.character)
            self.assertIsNot(reopened.rng, session.rng)
            self.assertIsNot(reopened.rng, peer.rng)
            self.assertIsNot(
                reopened.world_state["death_state"]["last_death_save_result"],
                session.world_state["death_state"]["last_death_save_result"],
            )
            self.assertEqual(session.serialize_game_state(), committed)
            self.assertEqual(session.rng.getstate(), source_rng)
            self.assertEqual(session.messages, source_messages)
            assert_isolation()
            self.assertEqual(path.read_bytes(), committed_bytes)
            self.assertEqual(peer_path.read_bytes(), peer_bytes)
            self.assertEqual(set(Path(directory).iterdir()), {path, peer_path})
            reference_rng = random.Random()
            reference_rng.setstate(rng_at_load)
            self.assertEqual(reopened.roll_d20(), reference_rng.randint(1, 20))
            self.assertEqual(reopened.rng.getstate(), reference_rng.getstate())
            self.assertEqual(session.rng.getstate(), source_rng)
            assert_isolation()

    def _assert_committed_death_round_trip(self, mode, *, terminal):
        session = make_session()
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        session.world_state["death_state"]["mode"] = mode
        start_test_combat(session)
        session.ensure_campaign_clock()
        peer.ensure_campaign_clock()
        peer.character["name"] = "Unrelated Adventurer"
        peer.recent_dm_narrations.append("Unrelated campaign history")
        peer.messages.append({"role": "user", "content": "Unrelated message"})
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"
        session.world_state["death_state"]["failures"] = 2
        enemy = session.world_state["npcs"][-1]
        game._begin_combat_actor_turn(enemy["id"], session=session)
        expected_resolution = {
            "mode": mode, "outcome": "dead", "cause": "failed_death_saves",
            "rolled_back": False, "terminal": terminal,
        }
        default_before = game.serialize_game_state()
        default_rng = game._DEFAULT_SESSION.rng.getstate()
        default_messages = copy.deepcopy(game._DEFAULT_SESSION.messages)
        module_rng = random.getstate()
        peer_before = peer.serialize_game_state()
        peer_rng = peer.rng.getstate()
        peer_messages = copy.deepcopy(peer.messages)
        source_rng = session.rng.getstate()

        def assert_isolation():
            self.assertEqual(peer.serialize_game_state(), peer_before)
            self.assertEqual(peer.rng.getstate(), peer_rng)
            self.assertEqual(peer.messages, peer_messages)
            self.assertEqual(game.serialize_game_state(), default_before)
            self.assertEqual(game._DEFAULT_SESSION.rng.getstate(), default_rng)
            self.assertEqual(game._DEFAULT_SESSION.messages, default_messages)
            self.assertEqual(random.getstate(), module_rng)
            self.assertIs(game._session(), game._DEFAULT_SESSION)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{mode.lower()}.json"
            peer_path = Path(directory) / "unrelated.json"
            # Both campaigns already have saves when the fatal attack commits.
            predeath = session.serialize_game_state()
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            with (
                patch("game.roll_d20", side_effect=[10, 14]) as attack_dice,
                patch("game.roll_damage", return_value=2) as damage_die,
            ):
                result = session.resolve_enemy_attack(enemy)
            self.assertEqual(attack_dice.call_count, 2)
            damage_die.assert_called_once()
            self.assertEqual(result["attack_rolls"], [10, 14])
            self.assertTrue(result["critical"])
            self.assertEqual(result["target_hp_after"], 0)
            self.assertEqual(result["target_status"], "dead")
            self.assertEqual(result["death_resolution"], expected_resolution)
            self.assertEqual(session.world_state["attack_results"], [result])
            self.assertTrue(session.world_state["death_state"]["dead"])
            self.assertEqual(session.world_state["death_state"]["terminal"], terminal)
            self.assertEqual(
                session.world_state["death_state"]["last_resolution"],
                expected_resolution,
            )
            self.assertFalse(session.world_state["combat"]["active"])
            self.assertEqual(session.world_state["combat"]["end_reason"], "player_dead")
            self.assertEqual(session.rng.getstate(), source_rng)
            assert_isolation()
            # Neither mode deletes an existing save, even on terminal death.
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), predeath)
            self.assertEqual(json.loads(peer_path.read_text(encoding="utf-8")), peer_before)
            committed = session.serialize_game_state()
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), committed)

            # Reopen into a genuinely fresh owner with different state and RNG.
            reopened.character["name"] = "Unsaved replacement"
            reopened.recent_dm_narrations.append("Unsaved replacement history")
            reopened.messages.append({"role": "user", "content": "Reopen save"})
            reopened.rng.random()
            rng_at_load = reopened.rng.getstate()
            messages_at_load = copy.deepcopy(reopened.messages)
            held = (reopened.world_state, reopened.character,
                    reopened.recent_dm_narrations, reopened.messages, reopened.rng)
            self.assertNotEqual(reopened.serialize_game_state(), committed)
            with (
                patch.object(reopened.rng, "randint", side_effect=AssertionError("Load rolled dice")),
                patch.object(peer.rng, "randint", side_effect=AssertionError("Peer rolled dice")),
                patch.object(game._DEFAULT_SESSION.rng, "randint",
                             side_effect=AssertionError("Default session rolled dice")),
            ):
                self.assertEqual(reopened.load_game(path), committed)
            self.assertEqual(reopened.serialize_game_state(), committed)
            self.assertEqual(reopened.character["current_hp"], 0)
            self.assertEqual(reopened.world_state["player_combat_status"], "dead")
            death = reopened.world_state["death_state"]
            self.assertTrue(death["dead"])
            self.assertEqual(death["mode"], mode)
            self.assertEqual(death["terminal"], terminal)
            self.assertEqual(death["last_resolution"], expected_resolution)
            self.assertEqual(reopened.world_state["attack_results"], [result])
            self.assertEqual(reopened.rng.getstate(), rng_at_load)
            self.assertEqual(reopened.messages, messages_at_load)
            for actual, reference in zip(
                (reopened.world_state, reopened.character,
                 reopened.recent_dm_narrations, reopened.messages, reopened.rng), held
            ):
                self.assertIs(actual, reference)
            self.assertIsNot(reopened.world_state, session.world_state)
            self.assertIsNot(reopened.character, session.character)
            self.assertIsNot(reopened.rng, session.rng)
            self.assertIsNot(reopened.rng, peer.rng)
            self.assertIsNot(reopened.world_state["attack_results"],
                             session.world_state["attack_results"])
            self.assertEqual(session.serialize_game_state(), committed)
            self.assertEqual(session.rng.getstate(), source_rng)
            assert_isolation()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), committed)
            self.assertEqual(json.loads(peer_path.read_text(encoding="utf-8")), peer_before)
            self.assertEqual(set(Path(directory).iterdir()), {path, peer_path})
            reference_rng = random.Random()
            reference_rng.setstate(rng_at_load)
            self.assertEqual(reopened.roll_d20(), reference_rng.randint(1, 20))
            self.assertEqual(reopened.rng.getstate(), reference_rng.getstate())
            self.assertEqual(session.rng.getstate(), source_rng)
            assert_isolation()

    def test_massive_damage_takes_precedence_over_third_damage_failure(self):
        session = make_session()
        death = session.world_state["death_state"]
        death["mode"] = "PERMADEATH"
        death["failures"] = 2
        session.character["current_hp"] = 0
        session.world_state["player_combat_status"] = "unconscious"

        result = game._apply_player_damage(
            20, critical=True, took_damage=True, session=session
        )

        self.assertEqual(result["death_resolution"]["cause"], "massive_damage")
        self.assertEqual(death["failures"], 3)
        self.assertTrue(death["dead"])


if __name__ == "__main__":
    unittest.main()