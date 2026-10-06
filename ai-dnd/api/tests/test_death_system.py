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
import scheduled_events
from api.serializers import serialize_session_state
from api.tests.test_campaign_time import scene
from api.tests.test_campaign_time_edges import event


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

    def test_completed_natural_recovery_stays_completed_after_two_reopenings(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_completed_recovery_round_trip(mode)

    def test_stable_recovery_finishes_oversized_wait_without_more_timers(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                session = make_session()
                campaign_time.initialize(session.world_state)
                session.ensure_death_state()["mode"] = mode
                session.advance_campaign_time(137, "wait")
                session._apply_player_damage(20, took_damage=True)
                with patch.object(session.rng, "randint", return_value=2) as die:
                    session.stabilize_player()
                die.assert_called_once_with(1, 4)
                death = session.ensure_death_state()
                deadline = death["recovery"]["at"]
                started_at = session.world_state["campaign_time"]["elapsed_seconds"]
                self.assertEqual(death["recovery"], {"hours": 2, "at": 137 + 7200})
                self.assertTrue(death["stable"])
                self.assertIsNone(death["noncombat_next_save_at"])
                self.assertEqual(session.character["current_hp"], 0)
                self.assertEqual(session.world_state["player_combat_status"], "unconscious")
                self.assertFalse(session.world_state["combat"]["active"])
                # Continue within one call beyond waking, many six-second save
                # boundaries, and the maximum four-hour recovery window.
                duration = deadline - started_at + 14401
                rng_state = session.rng.getstate()
                original_heal = game.heal_player

                def heal_at_recovery_deadline(amount):
                    self.assertEqual(
                        session.world_state["campaign_time"]["elapsed_seconds"], deadline
                    )
                    return original_heal(amount)

                with (
                    patch.object(session.rng, "randint",
                                 side_effect=AssertionError("Recovery consumed dice")) as die,
                    patch("game.roll_d20",
                          side_effect=AssertionError("Recovery rolled a death save")) as roll,
                    patch("game._resolve_player_death_turn",
                          side_effect=AssertionError("Recovery scheduled a death save")) as resolve,
                    patch("game.stabilize_player",
                          side_effect=AssertionError("Recovery scheduled another deadline")) as stabilize,
                    patch("game.heal_player", side_effect=heal_at_recovery_deadline) as heal,
                ):
                    progress = session.advance_campaign_time(duration, "wait")

                heal.assert_called_once_with(1)
                die.assert_not_called()
                roll.assert_not_called()
                resolve.assert_not_called()
                stabilize.assert_not_called()
                self.assertEqual(session.rng.getstate(), rng_state)
                self.assertEqual(progress["requested_seconds"], duration)
                self.assertEqual(progress["elapsed_seconds"], duration)
                self.assertEqual(progress["remaining_seconds"], 0)
                self.assertFalse(progress["interrupted"])
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"], started_at + duration
                )
                self.assertEqual(
                    progress["death_results"], [{"action": "stable_recovery", "current_hp": 1}]
                )
                self.assertEqual(session.character["current_hp"], 1)
                self.assertEqual(session.world_state["player_combat_status"], "active")
                self.assertFalse(session.world_state["combat"]["active"])
                after = session.ensure_death_state()
                self.assertEqual(after["mode"], mode)
                self.assertEqual((after["successes"], after["failures"]), (0, 0))
                self.assertFalse(after["stable"])
                self.assertFalse(after["dead"])
                self.assertFalse(after["terminal"])
                self.assertIsNone(after["recovery"])
                self.assertIsNone(after["noncombat_next_save_at"])
                self.assertIsNone(after["noncombat_episode_id"])

    def test_stable_recovery_hands_oversized_wait_to_conscious_event_interruption(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                session = scene()
                session.character.update(max_hp=20, current_hp=20)
                session.ensure_death_state()["mode"] = mode
                session.advance_campaign_time(137, "wait")
                session._apply_player_damage(20, took_damage=True)
                with patch.object(session.rng, "randint", return_value=2):
                    session.stabilize_player()
                started_at = session.world_state["campaign_time"]["elapsed_seconds"]
                deadline = session.ensure_death_state()["recovery"]["at"]
                self.assertEqual(deadline, started_at + 7200)
                before = campaign_time.public_time(session.world_state)
                encounter_at = deadline + 600
                duration = deadline - started_at + 14401
                observation = {"kind": "look", "location_id": "tavern"}
                unseen = event(
                    session, "while-unconscious", started_at + 60, started_at + 120,
                    summary="A traveller passes while the adventurer sleeps.",
                    aftermath_visible=False,
                )
                # This window stays open past recovery but closes before the stop.
                # It must not be observed at the unconscious segment's endpoint.
                sleeping_window = event(
                    session, "at-recovery", deadline - 60, deadline + 60,
                    summary="A visitor leaves just after the adventurer wakes.",
                    aftermath_visible=False,
                )
                visible = event(
                    session, "after-waking", deadline + 120, encounter_at + 120,
                    summary="A traveller is visible after waking.",
                    aftermath_visible=False,
                )
                decision = event(
                    session, "waking-decision", encounter_at, encounter_at + 120,
                    behavior="INTERRUPTIVE", requires_decision=True,
                    summary="A traveller wants a decision.",
                )
                rng_state = session.rng.getstate()
                original_heal = game.heal_player

                def heal_at_deadline(amount):
                    self.assertEqual(
                        session.world_state["campaign_time"]["elapsed_seconds"], deadline
                    )
                    self.assertEqual(session.character["current_hp"], 0)
                    self.assertEqual(session.world_state["player_combat_status"], "unconscious")
                    self.assertEqual(scheduled_events.public_events(session.world_state), [])
                    self.assertEqual(unseen["encounter_status"], "MISSED")
                    self.assertFalse(sleeping_window["player_observed"])
                    self.assertEqual(decision["status"], "PENDING")
                    self.assertEqual(decision["decision_status"], "NONE")
                    return original_heal(amount)

                with (
                    patch.object(session.rng, "randint",
                                 side_effect=AssertionError("Recovery rerolled dice")),
                    patch("game._resolve_player_death_turn",
                          side_effect=AssertionError("Stable recovery rolled a death save")),
                    patch("game.stabilize_player",
                          side_effect=AssertionError("Recovery scheduled another deadline")),
                    patch("game.heal_player", side_effect=heal_at_deadline) as heal,
                    patch("campaign_time.advance", wraps=campaign_time.advance) as advance,
                ):
                    progress = session.advance_campaign_time(
                        duration, "explicit_wait", observation=observation
                    )
                    self.assertEqual(advance.call_count, 2)
                    unconscious, conscious = advance.call_args_list
                    self.assertEqual(unconscious.args[1], deadline - started_at)
                    self.assertIsNone(unconscious.kwargs["observation"])
                    self.assertEqual(conscious.args[1], duration - (deadline - started_at))
                    self.assertEqual(conscious.kwargs["observation"], observation)
                    heal.assert_called_once_with(1)
                    self.assertEqual(progress["requested_seconds"], duration)
                    self.assertEqual(progress["elapsed_seconds"], encounter_at - started_at)
                    self.assertEqual(
                        progress["remaining_seconds"], duration - (encounter_at - started_at)
                    )
                    self.assertTrue(progress["interrupted"])
                    self.assertEqual(progress["before"], before)
                    self.assertEqual(progress["after"], campaign_time.public_time(session.world_state))
                    self.assertEqual(
                        session.world_state["campaign_time"]["elapsed_seconds"], encounter_at
                    )
                    self.assertEqual(
                        progress["death_results"], [{"action": "stable_recovery", "current_hp": 1}]
                    )
                    self.assertEqual(
                        progress["player_known_events"],
                        [scheduled_events.public_event(item, encounter_at)
                         for item in (decision, visible)],
                    )
                    for item in (unseen, sleeping_window):
                        self.assertFalse(item["player_observed"])
                        self.assertEqual(item["encounter_status"], "MISSED")
                        self.assertEqual(item["decision_status"], "NONE")
                        self.assertEqual(item["player_known_summary"], "")
                    for item in (visible, decision):
                        self.assertTrue(item["player_observed"])
                        self.assertEqual(item["status"], "OCCURRED")
                        self.assertEqual(item["player_known_summary"], item["summary"])
                    self.assertEqual(decision["decision_status"], "PENDING")
                    self.assertEqual(visible["decision_status"], "NONE")
                    self.assertEqual(session.character["current_hp"], 1)
                    self.assertEqual(session.world_state["player_combat_status"], "active")
                    death = session.ensure_death_state()
                    self.assertEqual(death["mode"], mode)
                    self.assertFalse(death["stable"])
                    self.assertFalse(death["dead"])
                    self.assertFalse(death["terminal"])
                    self.assertIsNone(death["recovery"])
                    self.assertIsNone(death["noncombat_next_save_at"])
                    # A retry while the decision is pending neither advances time
                    # nor heals again, even though it requests the full remainder.
                    retry = session.advance_campaign_time(
                        progress["remaining_seconds"], "explicit_wait", observation=observation
                    )
                    self.assertTrue(retry["interrupted"])
                    self.assertEqual(retry["elapsed_seconds"], 0)
                    self.assertEqual(retry["remaining_seconds"], progress["remaining_seconds"])
                    self.assertEqual(retry["death_results"], [])
                    heal.assert_called_once_with(1)
                self.assertEqual(session.rng.getstate(), rng_state)

    def _assert_completed_recovery_round_trip(self, mode):
        session = make_session()
        peer = make_session(seed=29)
        campaign_time.initialize(session.world_state)
        campaign_time.initialize(peer.world_state)
        session.ensure_death_state()["mode"] = mode
        session.advance_campaign_time(137, "wait")
        session._apply_player_damage(20, took_damage=True)
        with patch.object(session.rng, "randint", return_value=2) as die:
            session.stabilize_player()
        die.assert_called_once_with(1, 4)
        recovery = copy.deepcopy(session.ensure_death_state()["recovery"])
        self.assertEqual(recovery, {"hours": 2, "at": 137 + 7200})
        completion_rng = session.rng.getstate()
        with (
            patch.object(
                session.rng, "randint",
                side_effect=AssertionError("Natural recovery rolled dice"),
            ),
            patch("game.roll_d20", side_effect=AssertionError("Recovery rolled a death save")),
            patch("game.heal_player", wraps=game.heal_player) as heal,
        ):
            due = session.advance_campaign_time(7200, "wait")
            self.assertEqual(
                due["death_results"], [{"action": "stable_recovery", "current_hp": 1}]
            )
            heal.assert_called_once_with(1)
        self.assertEqual(session.rng.getstate(), completion_rng)
        completed_death = copy.deepcopy(session.ensure_death_state())

        def assert_completed(owner):
            self.assertEqual(owner.character["current_hp"], 1)
            self.assertEqual(owner.character["max_hp"], 20)
            self.assertEqual(owner.world_state["player_combat_status"], "active")
            self.assertEqual(owner.ensure_death_state(), completed_death)
            death = owner.ensure_death_state()
            self.assertEqual(death["mode"], mode)
            self.assertFalse(death["stable"])
            self.assertFalse(death["dead"])
            self.assertFalse(death["terminal"])
            self.assertEqual((death["successes"], death["failures"]), (0, 0))
            self.assertIsNone(death["recovery"])
            self.assertIsNone(death["noncombat_next_save_at"])

        assert_completed(session)
        self.assertEqual(
            session.world_state["campaign_time"]["elapsed_seconds"], recovery["at"]
        )
        session.messages.append({"role": "user", "content": "Source history"})
        peer.messages.append({"role": "user", "content": "Unrelated history"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "completed-recovery.json"
            peer_path = Path(directory) / "unrelated.json"
            # The first save is deliberately AFTER natural recovery, not before
            # its deadline or after explicit healing cancelled the timer.
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            saved_files = {path: path.read_bytes(), peer_path: peer_path.read_bytes()}
            protected = [session, peer, game._DEFAULT_SESSION]
            source = session
            for index, seed in enumerate((83, 101), start=1):
                committed = source.serialize_game_state()
                self.assertEqual(json.loads(saved_files[path]), committed)
                snapshots = [owner.serialize_game_state() for owner in protected]
                rng_states = [owner.rng.getstate() for owner in protected]
                histories = [copy.deepcopy(owner.messages) for owner in protected]
                module_rng = random.getstate()
                reopened = make_session(seed=seed)
                reopened.messages.append({"role": "user", "content": f"Reopen {index}"})
                load_rng = reopened.rng.getstate()
                load_history = copy.deepcopy(reopened.messages)

                def assert_preserved():
                    for owner, snapshot, rng_state, history in zip(
                        protected, snapshots, rng_states, histories
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
                        side_effect=AssertionError("Completed recovery rerolled dice"),
                    ),
                    patch(
                        "game.roll_d20",
                        side_effect=AssertionError("Completed recovery rolled a death save"),
                    ),
                    patch("game.heal_player", wraps=game.heal_player) as heal,
                ):
                    self.assertEqual(reopened.load_game(path), committed)
                    self.assertEqual(reopened.serialize_game_state(), committed)
                    for owner in protected:
                        self.assertIsNot(reopened.world_state, owner.world_state)
                        self.assertIsNot(reopened.character, owner.character)
                        self.assertIsNot(reopened.rng, owner.rng)
                        self.assertIsNot(
                            reopened.ensure_death_state(), owner.ensure_death_state()
                        )
                    assert_completed(reopened)
                    heal.assert_not_called()
                    assert_preserved()
                    now = reopened.world_state["campaign_time"]["elapsed_seconds"]
                    for duration in (1, 7200, 14400):
                        later = reopened.advance_campaign_time(duration, "wait")
                        now += duration
                        self.assertEqual(later["death_results"], [])
                        self.assertEqual(
                            reopened.world_state["campaign_time"]["elapsed_seconds"], now
                        )
                        assert_completed(reopened)
                        heal.assert_not_called()
                        assert_preserved()
                    if index == 1:
                        path = Path(directory) / "completed-recovery-second.json"
                        self.assertEqual(reopened.save_game(path), path)
                        saved_files[path] = path.read_bytes()
                        assert_completed(reopened)
                        heal.assert_not_called()
                        assert_preserved()
                protected.append(reopened)
                source = reopened

    def test_new_injury_after_reopened_natural_recovery_gets_fresh_timers(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_new_injury_after_completed_recovery(mode)

    def test_pending_new_injury_death_saves_keep_absolute_deadlines_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_new_injury_after_completed_recovery(mode, pending_reopen=True)

    def _assert_new_injury_after_completed_recovery(self, mode, *, pending_reopen=False):
        session = make_session()
        peer = make_session(seed=29)
        campaign_time.initialize(session.world_state)
        campaign_time.initialize(peer.world_state)
        session.ensure_death_state()["mode"] = mode
        session.advance_campaign_time(137, "wait")
        session._apply_player_damage(20, took_damage=True)
        prior_episode = session.ensure_death_state()["noncombat_episode_id"]
        # Complete the first episode naturally, including its death-save receipt.
        with (
            patch("game.roll_d20", side_effect=[10, 10, 10]) as death_die,
            patch.object(session.rng, "randint", return_value=2) as recovery_die,
        ):
            first_saves = session.advance_campaign_time(18, "wait")
        self.assertEqual(
            [entry["death_save"]["outcome"] for entry in first_saves["death_results"]],
            ["success", "success", "stable"],
        )
        self.assertEqual(death_die.call_count, 3)
        recovery_die.assert_called_once_with(1, 4)
        prior_key = session.ensure_death_state()["last_death_save_turn_key"]
        prior_recovery = copy.deepcopy(session.ensure_death_state()["recovery"])
        self.assertEqual(prior_recovery, {"hours": 2, "at": 137 + 18 + 7200})
        with (
            patch.object(session.rng, "randint", side_effect=AssertionError("Recovery rolled dice")),
            patch("game.roll_d20", side_effect=AssertionError("Recovery rolled a death save")),
            patch("game.heal_player", wraps=game.heal_player) as heal,
        ):
            completed = session.advance_campaign_time(7200, "wait")
        self.assertEqual(
            completed["death_results"], [{"action": "stable_recovery", "current_hp": 1}]
        )
        heal.assert_called_once_with(1)
        self.assertEqual(session.character["current_hp"], 1)
        self.assertIsNone(session.ensure_death_state()["recovery"])
        self.assertIsNone(session.ensure_death_state()["noncombat_next_save_at"])
        self.assertIsNone(session.ensure_death_state()["noncombat_episode_id"])

        with tempfile.TemporaryDirectory() as directory:
            completed_path = Path(directory) / "naturally-completed.json"
            peer_path = Path(directory) / "unrelated.json"
            self.assertEqual(session.save_game(completed_path), completed_path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            saved_files = {
                completed_path: completed_path.read_bytes(),
                peer_path: peer_path.read_bytes(),
            }
            protected = [session, peer, game._DEFAULT_SESSION]
            snapshots = [owner.serialize_game_state() for owner in protected]
            rng_states = [owner.rng.getstate() for owner in protected]
            histories = [copy.deepcopy(owner.messages) for owner in protected]
            module_rng = random.getstate()

            def assert_preserved():
                for owner, snapshot, rng_state, history in zip(
                    protected, snapshots, rng_states, histories
                ):
                    self.assertEqual(owner.serialize_game_state(), snapshot)
                    self.assertEqual(owner.rng.getstate(), rng_state)
                    self.assertEqual(owner.messages, history)
                self.assertEqual(random.getstate(), module_rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                for path, content in saved_files.items():
                    self.assertEqual(path.read_bytes(), content)
                self.assertEqual(set(Path(directory).iterdir()), set(saved_files))

            reopened = make_session(seed=11)
            reopened.messages.append({"role": "user", "content": "New injury owner"})
            reopen_history = copy.deepcopy(reopened.messages)
            reopen_rng = reopened.rng.getstate()
            with (
                patch.object(reopened.rng, "randint", side_effect=AssertionError("Load rolled dice")),
                patch("game.roll_d20", side_effect=AssertionError("Load rolled a death save")),
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                self.assertEqual(reopened.load_game(completed_path), snapshots[0])
                self.assertEqual(reopened.serialize_game_state(), snapshots[0])
                self.assertEqual(reopened.rng.getstate(), reopen_rng)
                self.assertEqual(reopened.advance_campaign_time(91, "wait")["death_results"], [])
                heal.assert_not_called()
                injury_at = reopened.world_state["campaign_time"]["elapsed_seconds"]
                self.assertEqual(injury_at, prior_recovery["at"] + 91)
                damage = reopened._apply_player_damage(1, took_damage=True)
                self.assertIsNone(damage["death_resolution"])
                self.assertEqual((damage["hp_before"], damage["hp_after"]), (1, 0))
                death = reopened.ensure_death_state()
                self.assertFalse(death["stable"])
                self.assertFalse(death["dead"])
                self.assertFalse(death["terminal"])
                self.assertEqual(death["mode"], mode)
                self.assertEqual((death["successes"], death["failures"]), (0, 0))
                self.assertIsNone(death["recovery"])
                self.assertEqual(death["noncombat_next_save_at"], injury_at + 6)
                episode = death["noncombat_episode_id"]
                self.assertIsInstance(episode, str)
                self.assertTrue(episode)
                self.assertNotEqual(episode, prior_episode)
                self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                self.assertEqual(reopened.advance_campaign_time(5, "wait")["death_results"], [])
                self.assertEqual(death["noncombat_next_save_at"], injury_at + 6)
                self.assertEqual((death["successes"], death["failures"]), (0, 0))
                self.assertEqual(reopened.rng.getstate(), reopen_rng)
                heal.assert_not_called()
                assert_preserved()

            if pending_reopen:
                self._assert_pending_new_injury_reopenings(
                    reopened, mode, injury_at, episode, prior_key,
                    protected, snapshots, rng_states, histories, saved_files,
                    assert_preserved,
                )
                return

            # Use the new owner's actual RNG, not the completed campaign's stream.
            reference = random.Random()
            reference.setstate(reopen_rng)
            expected_rolls = [reference.randint(1, 20) for _ in range(3)]
            self.assertTrue(all(10 <= roll < 20 for roll in expected_rolls))
            hours = reference.randint(1, 4)
            self.assertNotEqual(hours, prior_recovery["hours"])
            with (
                patch.object(reopened.rng, "randint", wraps=reopened.rng.randint) as die,
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                for index, duration in enumerate((1, 6, 6), start=1):
                    result = reopened.advance_campaign_time(duration, "wait")
                    self.assertEqual(len(result["death_results"]), 1)
                    entry = result["death_results"][0]
                    self.assertEqual(entry["action"], "death_save")
                    self.assertEqual(entry["death_save"]["roll"], expected_rolls[index - 1])
                    self.assertEqual(
                        entry["death_save"]["outcome"], "stable" if index == 3 else "success"
                    )
                    death = reopened.ensure_death_state()
                    self.assertEqual(
                        death["last_death_save_turn_key"],
                        f"noncombat:{episode}:{injury_at + index * 6}",
                    )
                    self.assertNotEqual(death["last_death_save_turn_key"], prior_key)
                    self.assertEqual(
                        (death["successes"], death["failures"]),
                        (0 if index == 3 else index, 0),
                    )
                    self.assertEqual(
                        death["noncombat_next_save_at"],
                        None if index == 3 else injury_at + (index + 1) * 6,
                    )
                self.assertEqual([call.args for call in die.call_args_list],
                                 [(1, 20)] * 3 + [(1, 4)])
                heal.assert_not_called()
            replacement = {"hours": hours, "at": injury_at + 18 + hours * 3600}
            self.assertEqual(death["recovery"], replacement)
            self.assertGreater(replacement["at"], prior_recovery["at"])
            self.assertTrue(death["stable"])
            self.assertEqual(reopened.rng.getstate(), reference.getstate())
            self.assertEqual(reopened.messages, reopen_history)
            assert_preserved()

            # Save partway through the second episode; load must not restart its duration.
            self.assertEqual(reopened.advance_campaign_time(600, "wait")["death_results"], [])
            replacement_path = Path(directory) / "new-injury-recovery.json"
            self.assertEqual(reopened.save_game(replacement_path), replacement_path)
            committed = reopened.serialize_game_state()
            saved_files[replacement_path] = replacement_path.read_bytes()
            self.assertEqual(json.loads(saved_files[replacement_path]), committed)
            protected.append(reopened)
            snapshots.append(committed)
            rng_states.append(reopened.rng.getstate())
            histories.append(copy.deepcopy(reopened.messages))
            second = make_session(seed=101)
            second.messages.append({"role": "user", "content": "Second episode owner"})
            second_rng = second.rng.getstate()
            second_history = copy.deepcopy(second.messages)
            with (
                patch.object(second.rng, "randint", side_effect=AssertionError("Second recovery rolled dice")),
                patch("game.roll_d20", side_effect=AssertionError("Second recovery rolled a death save")),
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                self.assertEqual(second.load_game(replacement_path), committed)
                self.assertEqual(second.serialize_game_state(), committed)
                for owner in protected:
                    self.assertIsNot(second.world_state, owner.world_state)
                    self.assertIsNot(second.character, owner.character)
                    self.assertIsNot(second.rng, owner.rng)
                    self.assertIsNot(second.ensure_death_state(), owner.ensure_death_state())
                self.assertIsNot(second.ensure_death_state()["recovery"], death["recovery"])
                self.assertEqual(second.ensure_death_state(), death)
                self.assertEqual(second.character["current_hp"], 0)
                self.assertEqual(second.world_state["player_combat_status"], "unconscious")
                now = second.world_state["campaign_time"]["elapsed_seconds"]
                self.assertEqual(now, injury_at + 18 + 600)
                self.assertEqual(
                    second.advance_campaign_time(replacement["at"] - now - 1, "wait")["death_results"], []
                )
                self.assertEqual(second.ensure_death_state(), death)
                self.assertEqual(second.character["current_hp"], 0)
                self.assertEqual(second.world_state["campaign_time"]["elapsed_seconds"], replacement["at"] - 1)
                heal.assert_not_called()
                assert_preserved()
                due = second.advance_campaign_time(1, "wait")
                self.assertEqual(
                    due["death_results"], [{"action": "stable_recovery", "current_hp": 1}]
                )
                self.assertEqual(second.world_state["campaign_time"]["elapsed_seconds"], replacement["at"])
                completed_death = copy.deepcopy(second.ensure_death_state())
                self.assertEqual(completed_death["mode"], mode)
                self.assertFalse(completed_death["stable"])
                self.assertFalse(completed_death["dead"])
                self.assertFalse(completed_death["terminal"])
                self.assertEqual((completed_death["successes"], completed_death["failures"]), (0, 0))
                self.assertIsNone(completed_death["recovery"])
                self.assertIsNone(completed_death["noncombat_next_save_at"])
                self.assertIsNone(completed_death["noncombat_episode_id"])
                for duration in (1, hours * 3600, 14400):
                    self.assertEqual(second.advance_campaign_time(duration, "wait")["death_results"], [])
                    self.assertEqual(second.character["current_hp"], 1)
                    self.assertEqual(second.character["max_hp"], 20)
                    self.assertEqual(second.world_state["player_combat_status"], "active")
                    self.assertEqual(second.ensure_death_state(), completed_death)
                    heal.assert_called_once_with(1)
                    self.assertEqual(second.rng.getstate(), second_rng)
                    self.assertEqual(second.messages, second_history)
                    assert_preserved()

    def _assert_pending_new_injury_reopenings(
        self, source, mode, injury_at, episode, prior_key,
        protected, snapshots, rng_states, histories, saved_files, assert_preserved,
    ):
        # Reopen at injury+5 (no saves yet), then injury+8 (one success).
        # Both loads must preserve an absolute deadline, not start a fresh six seconds.
        for index, seed in enumerate((17, 11)):
            with self.subTest(successes_before_load=index):
                death = copy.deepcopy(source.ensure_death_state())
                deadline = injury_at + (index + 1) * 6
                self.assertEqual(death["noncombat_next_save_at"], deadline)
                self.assertEqual(death["noncombat_episode_id"], episode)
                self.assertEqual((death["successes"], death["failures"]), (index, 0))
                self.assertFalse(death["stable"])
                self.assertIsNone(death["recovery"])
                self.assertEqual(
                    source.world_state["campaign_time"]["elapsed_seconds"],
                    injury_at + (5 if index == 0 else 8),
                )
                path = next(iter(saved_files)).with_name(f"pending-injury-{index}.json")
                self.assertEqual(source.save_game(path), path)
                committed = source.serialize_game_state()
                saved_files[path] = path.read_bytes()
                self.assertEqual(json.loads(saved_files[path]), committed)
                protected.append(source)
                snapshots.append(committed)
                rng_states.append(source.rng.getstate())
                histories.append(copy.deepcopy(source.messages))
                assert_preserved()

                reopened = make_session(seed=seed)
                reopened.character["name"] = "Unsaved pending owner"
                reopened.messages.append({"role": "user", "content": "Pending save owner"})
                load_history = copy.deepcopy(reopened.messages)
                load_rng = reopened.rng.getstate()
                held = (
                    reopened.world_state, reopened.character, reopened.messages,
                    reopened.recent_dm_narrations, reopened.rng,
                )
                with (
                    patch.object(
                        reopened.rng, "randint",
                        side_effect=AssertionError("Pending load or early tick rolled dice"),
                    ) as die,
                    patch("game.heal_player", side_effect=AssertionError("Pending injury healed")),
                ):
                    self.assertEqual(reopened.load_game(path), committed)
                    self.assertEqual(reopened.serialize_game_state(), committed)
                    for actual, original in zip(
                        (reopened.world_state, reopened.character, reopened.messages,
                         reopened.recent_dm_narrations, reopened.rng), held
                    ):
                        self.assertIs(actual, original)
                    for owner in protected:
                        self.assertIsNot(reopened.world_state, owner.world_state)
                        self.assertIsNot(reopened.character, owner.character)
                        self.assertIsNot(reopened.rng, owner.rng)
                        self.assertIsNot(reopened.ensure_death_state(), owner.ensure_death_state())
                    if index:
                        self.assertIsNot(
                            reopened.ensure_death_state()["last_death_save_result"],
                            source.ensure_death_state()["last_death_save_result"],
                        )
                    now = reopened.world_state["campaign_time"]["elapsed_seconds"]
                    for duration in (0, deadline - now - 1, 0):
                        self.assertEqual(
                            reopened.advance_campaign_time(duration, "wait")["death_results"], []
                        )
                        self.assertEqual(reopened.ensure_death_state(), death)
                        self.assertEqual(reopened.character["current_hp"], 0)
                        self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                        self.assertFalse(reopened.world_state["combat"]["active"])
                        self.assertEqual(reopened.rng.getstate(), load_rng)
                        self.assertEqual(reopened.messages, load_history)
                        die.assert_not_called()
                        assert_preserved()
                    self.assertEqual(
                        reopened.world_state["campaign_time"]["elapsed_seconds"], deadline - 1
                    )

                reference = random.Random()
                reference.setstate(load_rng)
                expected_roll = reference.randint(1, 20)
                self.assertTrue(10 <= expected_roll < 20)
                source_reference = random.Random()
                source_reference.setstate(source.rng.getstate())
                self.assertNotEqual(expected_roll, source_reference.randint(1, 20))
                with (
                    patch.object(reopened.rng, "randint", wraps=reopened.rng.randint) as die,
                    patch("game.heal_player", side_effect=AssertionError("Pending injury healed")),
                ):
                    result = reopened.advance_campaign_time(1, "wait")
                    self.assertEqual(len(result["death_results"]), 1)
                    entry = result["death_results"][0]
                    self.assertEqual(entry["action"], "death_save")
                    self.assertEqual(entry["death_save"]["roll"], expected_roll)
                    self.assertEqual(entry["death_save"]["outcome"], "success")
                    die.assert_called_once_with(1, 20)
                    self.assertEqual(reopened.rng.getstate(), reference.getstate())
                    after = copy.deepcopy(reopened.ensure_death_state())
                    self.assertEqual(after["mode"], mode)
                    self.assertEqual((after["successes"], after["failures"]), (index + 1, 0))
                    self.assertFalse(after["stable"])
                    self.assertFalse(after["dead"])
                    self.assertFalse(after["terminal"])
                    self.assertIsNone(after["recovery"])
                    self.assertEqual(after["noncombat_episode_id"], episode)
                    self.assertEqual(after["noncombat_next_save_at"], deadline + 6)
                    self.assertEqual(
                        after["last_death_save_turn_key"], f"noncombat:{episode}:{deadline}"
                    )
                    self.assertNotEqual(after["last_death_save_turn_key"], prior_key)
                    self.assertNotEqual(
                        after["last_death_save_turn_key"], death["last_death_save_turn_key"]
                    )
                    self.assertEqual(after["last_death_save_result"], entry["death_save"])
                    self.assertEqual(
                        reopened.world_state["campaign_time"]["elapsed_seconds"], deadline
                    )
                    # Repeated ticks at and just after the boundary cannot replay
                    # the already committed save or consume another d20.
                    for duration in (0, 1, 0, 1):
                        self.assertEqual(
                            reopened.advance_campaign_time(duration, "wait")["death_results"], []
                        )
                        self.assertEqual(reopened.ensure_death_state(), after)
                        self.assertEqual(reopened.character["current_hp"], 0)
                        self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                        self.assertEqual(reopened.rng.getstate(), reference.getstate())
                        self.assertEqual(reopened.messages, load_history)
                        die.assert_called_once_with(1, 20)
                        assert_preserved()
                source = reopened

    def test_pending_failed_noncombat_death_saves_survive_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                with self.subTest(mode=mode, outcome=outcome):
                    self._assert_pending_failed_noncombat_reopening(
                        mode, roll, outcome, failures
                    )

    def test_zero_healing_preserves_pending_noncombat_saves_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                with self.subTest(mode=mode, outcome=outcome):
                    self._assert_pending_failed_noncombat_reopening(
                        mode, roll, outcome, failures, healing_amounts=(0,)
                    )

    def test_rejected_healing_preserves_pending_noncombat_saves_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                for amount in (-1, 1.0, 1.5, "1", None, True, False):
                    with self.subTest(mode=mode, outcome=outcome, amount=amount):
                        self._assert_pending_failed_noncombat_reopening(
                            mode, roll, outcome, failures, healing_amounts=(amount,)
                        )

    def test_rejected_max_hp_preserves_pending_noncombat_saves_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                for maximum in (-1, 1.0, 1.5, "1", None, True, False):
                    with self.subTest(mode=mode, outcome=outcome, maximum=maximum):
                        self._assert_pending_failed_noncombat_reopening(
                            mode, roll, outcome, failures, rejected_maximum=(maximum,)
                        )

    def test_positive_max_hp_change_preserves_pending_noncombat_saves_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                for maximum in (1, 35):
                    with self.subTest(mode=mode, outcome=outcome, maximum=maximum):
                        self._assert_pending_failed_noncombat_reopening(
                            mode, roll, outcome, failures, positive_maximum=maximum
                        )

    def _assert_pending_failed_noncombat_reopening(
        self, mode, roll, outcome, failures, *, healing_amounts=(),
        rejected_maximum=(), positive_maximum=None
    ):
        source = make_session()
        peer = make_session(seed=29)
        campaign_time.initialize(source.world_state)
        campaign_time.initialize(peer.world_state)
        source.ensure_death_state()["mode"] = mode
        source.advance_campaign_time(137, "wait")

        with tempfile.TemporaryDirectory() as directory:
            prior_path = Path(directory) / "before-injury.json"
            peer_path = Path(directory) / "unrelated.json"
            pending_path = Path(directory) / "pending-failure.json"
            self.assertEqual(source.save_game(prior_path), prior_path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            saved_files = {
                prior_path: prior_path.read_bytes(),
                peer_path: peer_path.read_bytes(),
            }
            source._apply_player_damage(20, took_damage=True)
            episode = source.ensure_death_state()["noncombat_episode_id"]
            self.assertIsInstance(episode, str)
            self.assertTrue(episode)
            first_deadline = 137 + 6
            with (
                patch("game.roll_d20", return_value=roll) as die,
                patch("game.heal_player", side_effect=AssertionError("Failed save healed")),
            ):
                first = source.advance_campaign_time(6, "wait")
            die.assert_called_once_with()
            self.assertEqual(len(first["death_results"]), 1)
            receipt = first["death_results"][0]["death_save"]
            self.assertEqual(first["death_results"][0]["action"], "death_save")
            self.assertEqual(receipt["roll"], roll)
            self.assertEqual(receipt["outcome"], outcome)
            # Persist partway through the interval, not at its starting boundary.
            with patch.object(
                source.rng, "randint", side_effect=AssertionError("Early source tick rolled")
            ):
                self.assertEqual(source.advance_campaign_time(2, "wait")["death_results"], [])
            death = copy.deepcopy(source.ensure_death_state())
            deadline = first_deadline + 6
            self.assertEqual((death["successes"], death["failures"]), (0, failures))
            self.assertEqual(death["noncombat_episode_id"], episode)
            self.assertEqual(death["noncombat_next_save_at"], deadline)
            self.assertEqual(death["last_death_save_turn_key"],
                             f"noncombat:{episode}:{first_deadline}")
            self.assertEqual(death["last_death_save_result"], receipt)
            self.assertFalse(death["stable"])
            self.assertFalse(death["dead"])
            self.assertFalse(death["terminal"])
            self.assertIsNone(death["recovery"])
            self.assertEqual(source.save_game(pending_path), pending_path)
            committed = source.serialize_game_state()
            saved_files[pending_path] = pending_path.read_bytes()
            self.assertEqual(json.loads(saved_files[pending_path]), committed)
            protected = (source, peer, game._DEFAULT_SESSION)
            snapshots = [owner.serialize_game_state() for owner in protected]
            rng_states = [owner.rng.getstate() for owner in protected]
            histories = [copy.deepcopy(owner.messages) for owner in protected]
            module_rng = random.getstate()

            def assert_preserved():
                for owner, snapshot, rng_state, history in zip(
                    protected, snapshots, rng_states, histories
                ):
                    self.assertEqual(owner.serialize_game_state(), snapshot)
                    self.assertEqual(owner.rng.getstate(), rng_state)
                    self.assertEqual(owner.messages, history)
                self.assertEqual(random.getstate(), module_rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                for path, content in saved_files.items():
                    self.assertEqual(path.read_bytes(), content)
                self.assertEqual(set(Path(directory).iterdir()), set(saved_files))

            def assert_ineffective_healing(owner):
                before = copy.deepcopy(owner.serialize_game_state())
                owner_rng = owner.rng.getstate()
                owner_history = copy.deepcopy(owner.messages)
                with (
                    patch.object(
                        owner.rng, "randint",
                        side_effect=AssertionError("Ineffective healing consumed RNG"),
                    ) as die,
                    patch("game.roll_d20",
                          side_effect=AssertionError("Ineffective healing rolled a save")),
                    patch("game.heal_player", wraps=game.heal_player) as heal,
                ):
                    for amount in healing_amounts:
                        if type(amount) is int and amount == 0:
                            self.assertEqual(owner.heal_player(amount), 0)
                        else:
                            with self.assertRaisesRegex(
                                ValueError, "^Healing amount is invalid\\.$"
                            ):
                                owner.heal_player(amount)
                        heal.assert_called_once_with(amount, session=owner)
                        die.assert_not_called()
                        self.assertEqual(owner.serialize_game_state(), before)
                        self.assertEqual(owner.ensure_death_state(), death)
                        self.assertEqual(owner.character["current_hp"], 0)
                        self.assertEqual(owner.world_state["player_combat_status"],
                                         "unconscious")
                        self.assertFalse(owner.world_state["combat"]["active"])
                        self.assertEqual(owner.rng.getstate(), owner_rng)
                        self.assertEqual(owner.messages, owner_history)
                        assert_preserved()

            def assert_maximum_preserves_pending(owner):
                before = copy.deepcopy(owner.serialize_game_state())
                expected = copy.deepcopy(before)
                owner_rng = owner.rng.getstate()
                owner_history = copy.deepcopy(owner.messages)
                with (
                    patch.object(
                        owner.rng, "randint",
                        side_effect=AssertionError("HP maximum consumed RNG"),
                    ) as die,
                    patch("game.roll_d20",
                          side_effect=AssertionError("HP maximum rolled a death save")),
                    patch("game.heal_player",
                          side_effect=AssertionError("HP maximum healed")),
                ):
                    for maximum in rejected_maximum:
                        with self.assertRaisesRegex(ValueError, "^HP maximum is invalid\\.$"):
                            owner.set_player_max_hp(maximum)
                        self.assertEqual(owner.serialize_game_state(), before)
                        assert_preserved()
                    if positive_maximum is not None:
                        expected["player"]["max_hp"] = positive_maximum
                        self.assertIsNone(owner.set_player_max_hp(positive_maximum))
                        self.assertEqual(owner.serialize_game_state(), expected)
                        # Only this owner's maximum may change. Keep comparing
                        # its full state against that explicitly checked delta.
                        if owner is source:
                            snapshots[0] = expected
                    die.assert_not_called()
                self.assertEqual(owner.serialize_game_state(), expected)
                self.assertEqual(owner.ensure_death_state(), death)
                self.assertEqual(owner.character["current_hp"], 0)
                self.assertEqual(owner.world_state["player_combat_status"], "unconscious")
                self.assertFalse(owner.world_state["combat"]["active"])
                self.assertEqual(owner.rng.getstate(), owner_rng)
                self.assertEqual(owner.messages, owner_history)
                assert_preserved()

            # Maximum changes must leave both the persisted source and its
            # reopened copy unconscious, with the same pending episode.
            if rejected_maximum or positive_maximum is not None:
                assert_maximum_preserves_pending(source)
                maximum_path = Path(directory) / "after-maximum-change.json"
                with (
                    patch.object(source.rng, "randint",
                                 side_effect=AssertionError("HP maximum save consumed RNG")),
                    patch("game.roll_d20",
                          side_effect=AssertionError("HP maximum save rolled")),
                ):
                    self.assertEqual(source.save_game(maximum_path), maximum_path)
                committed = source.serialize_game_state()
                saved_files[maximum_path] = maximum_path.read_bytes()
                expected_saved = json.loads(saved_files[pending_path])
                if positive_maximum is not None:
                    expected_saved["player"]["max_hp"] = positive_maximum
                else:
                    self.assertEqual(saved_files[maximum_path], saved_files[pending_path])
                self.assertEqual(json.loads(saved_files[maximum_path]), expected_saved)
                self.assertEqual(committed, expected_saved)
                assert_preserved()
                pending_path = maximum_path

            # The persisted source and its reopened copy must both reject
            # ineffective healing without cancelling or restarting this episode.
            assert_ineffective_healing(source)
            if healing_amounts:
                after_healing_path = Path(directory) / "after-ineffective-healing.json"
                self.assertEqual(source.save_game(after_healing_path), after_healing_path)
                saved_files[after_healing_path] = after_healing_path.read_bytes()
                self.assertEqual(saved_files[after_healing_path], saved_files[pending_path])
                assert_preserved()
                pending_path = after_healing_path
            reopened = make_session(seed=11)
            reopened.messages.append({"role": "user", "content": "Reopen pending failure"})
            load_rng = reopened.rng.getstate()
            load_history = copy.deepcopy(reopened.messages)
            with (
                patch.object(
                    reopened.rng, "randint",
                    side_effect=AssertionError("Pending load or early tick rolled"),
                ) as die,
                patch("game.roll_d20", side_effect=AssertionError("Early death save rolled")),
                patch("game.heal_player", side_effect=AssertionError("Pending failure healed")),
            ):
                self.assertEqual(reopened.load_game(pending_path), committed)
                self.assertEqual(reopened.serialize_game_state(), committed)
                for owner in protected:
                    self.assertIsNot(reopened.world_state, owner.world_state)
                    self.assertIsNot(reopened.character, owner.character)
                    self.assertIsNot(reopened.rng, owner.rng)
                    self.assertIsNot(reopened.ensure_death_state(), owner.ensure_death_state())
                self.assertIsNot(
                    reopened.ensure_death_state()["last_death_save_result"],
                    source.ensure_death_state()["last_death_save_result"],
                )
                self.assertEqual(
                    reopened.world_state["campaign_time"]["elapsed_seconds"], first_deadline + 2
                )
                for duration in (0, 1, 2, 0):
                    self.assertEqual(reopened.advance_campaign_time(duration, "wait")["death_results"], [])
                    self.assertEqual(reopened.ensure_death_state(), death)
                    self.assertEqual(reopened.character["current_hp"], 0)
                    self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                    self.assertFalse(reopened.world_state["combat"]["active"])
                    self.assertEqual(reopened.rng.getstate(), load_rng)
                    self.assertEqual(reopened.messages, load_history)
                    die.assert_not_called()
                    assert_preserved()
                self.assertEqual(
                    reopened.world_state["campaign_time"]["elapsed_seconds"], deadline - 1
                )

            assert_ineffective_healing(reopened)
            if rejected_maximum or positive_maximum is not None:
                assert_maximum_preserves_pending(reopened)
            reference = random.Random()
            reference.setstate(load_rng)
            expected_roll = reference.randint(1, 20)
            self.assertTrue(10 <= expected_roll < 20)
            source_reference = random.Random()
            source_reference.setstate(source.rng.getstate())
            self.assertNotEqual(expected_roll, source_reference.randint(1, 20))
            with (
                patch.object(reopened.rng, "randint", wraps=reopened.rng.randint) as die,
                patch("game.heal_player", side_effect=AssertionError("Pending failure healed")),
            ):
                due = reopened.advance_campaign_time(1, "wait")
                self.assertEqual(len(due["death_results"]), 1)
                entry = due["death_results"][0]
                self.assertEqual(entry["action"], "death_save")
                self.assertEqual(entry["death_save"]["roll"], expected_roll)
                self.assertEqual(entry["death_save"]["outcome"], "success")
                after = copy.deepcopy(reopened.ensure_death_state())
                self.assertEqual(after["mode"], mode)
                self.assertEqual((after["successes"], after["failures"]), (1, failures))
                self.assertEqual(after["noncombat_episode_id"], episode)
                self.assertEqual(after["noncombat_next_save_at"], deadline + 6)
                self.assertEqual(after["last_death_save_turn_key"],
                                 f"noncombat:{episode}:{deadline}")
                self.assertNotEqual(after["last_death_save_turn_key"],
                                    death["last_death_save_turn_key"])
                self.assertEqual(after["last_death_save_result"], entry["death_save"])
                self.assertFalse(after["stable"])
                self.assertFalse(after["dead"])
                self.assertFalse(after["terminal"])
                self.assertIsNone(after["recovery"])
                self.assertEqual(reopened.world_state["campaign_time"]["elapsed_seconds"], deadline)
                for duration in (0, 1, 0):
                    self.assertEqual(reopened.advance_campaign_time(duration, "wait")["death_results"], [])
                    self.assertEqual(reopened.ensure_death_state(), after)
                    self.assertEqual(reopened.character["current_hp"], 0)
                    self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                    self.assertEqual(reopened.rng.getstate(), reference.getstate())
                    self.assertEqual(reopened.messages, load_history)
                    die.assert_called_once_with(1, 20)
                    assert_preserved()

    def test_healing_cancelled_pending_noncombat_saves_stay_cancelled_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                with self.subTest(mode=mode, outcome=outcome):
                    self._assert_healed_pending_noncombat_round_trip(
                        mode, roll, outcome, failures
                    )

    def test_new_injury_after_reopening_healed_noncombat_save_starts_fresh_episode(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                with self.subTest(mode=mode, outcome=outcome):
                    self._assert_healed_pending_noncombat_round_trip(
                        mode, roll, outcome, failures, new_injury=True
                    )

    def test_reopened_reinjury_long_wait_matches_incremental_death_save_deadlines(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            for roll, outcome, failures in ((4, "failure", 1), (1, "natural_1", 2)):
                with self.subTest(mode=mode, outcome=outcome):
                    self._assert_healed_pending_noncombat_round_trip(
                        mode, roll, outcome, failures, new_injury=True, long_wait=True
                    )

    def _assert_healed_pending_noncombat_round_trip(
        self, mode, roll, outcome, failures, *, new_injury=False, long_wait=False
    ):
        session = make_session()
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        campaign_time.initialize(session.world_state)
        campaign_time.initialize(peer.world_state)
        session.ensure_death_state()["mode"] = mode
        session.advance_campaign_time(137, "wait")
        session._apply_player_damage(20, took_damage=True)
        episode = session.ensure_death_state()["noncombat_episode_id"]
        self.assertIsInstance(episode, str)
        self.assertTrue(episode)
        # Establish both counters through actual saves, without stabilizing.
        with patch("game.roll_d20", side_effect=[12, roll]) as die:
            first = session.advance_campaign_time(6, "wait")
            failed = session.advance_campaign_time(6, "wait")
        self.assertEqual(die.call_count, 2)
        self.assertEqual(first["death_results"][0]["death_save"]["outcome"], "success")
        self.assertEqual(len(failed["death_results"]), 1)
        receipt = failed["death_results"][0]["death_save"]
        self.assertEqual(receipt["roll"], roll)
        self.assertEqual(receipt["outcome"], outcome)
        pending = copy.deepcopy(session.ensure_death_state())
        old_deadline = pending["noncombat_next_save_at"]
        self.assertEqual(old_deadline, 155)
        self.assertEqual(pending["noncombat_episode_id"], episode)
        self.assertEqual((pending["successes"], pending["failures"]), (1, failures))
        self.assertFalse(pending["stable"])
        self.assertFalse(pending["dead"])
        self.assertFalse(pending["terminal"])
        self.assertIsNone(pending["recovery"])
        self.assertEqual(session.character["current_hp"], 0)
        self.assertEqual(session.world_state["player_combat_status"], "unconscious")
        self.assertFalse(session.world_state["combat"]["active"])
        session.messages.append({"role": "user", "content": "Source history"})
        peer.messages.append({"role": "user", "content": "Unrelated history"})
        reopened.messages.append({"role": "user", "content": "Reopen history"})

        with tempfile.TemporaryDirectory() as directory:
            pending_path = Path(directory) / "pending-saves.json"
            path = Path(directory) / "healed-pending-saves.json"
            peer_path = Path(directory) / "unrelated.json"
            self.assertEqual(session.save_game(pending_path), pending_path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            saved_files = {
                pending_path: pending_path.read_bytes(),
                peer_path: peer_path.read_bytes(),
            }
            self.assertEqual(json.loads(saved_files[pending_path]),
                             session.serialize_game_state())
            protected = (peer, game._DEFAULT_SESSION)
            snapshots = [owner.serialize_game_state() for owner in protected]
            rng_states = [owner.rng.getstate() for owner in protected]
            histories = [copy.deepcopy(owner.messages) for owner in protected]
            module_rng = random.getstate()
            healing_rng = session.rng.getstate()
            source_history = copy.deepcopy(session.messages)
            # Heal partway through the pending interval, not at a save boundary.
            with (
                patch("game.roll_d20", side_effect=AssertionError("Healing rolled a save")),
                patch.object(session.rng, "randint",
                             side_effect=AssertionError("Healing consumed RNG")) as die,
            ):
                self.assertEqual(session.advance_campaign_time(2, "wait")["death_results"], [])
                self.assertEqual(session.ensure_death_state(), pending)
                healing_clock = copy.deepcopy(session.world_state["campaign_time"])
                self.assertEqual(session.heal_player(3), 3)
                die.assert_not_called()
            self.assertEqual(session.rng.getstate(), healing_rng)
            self.assertEqual(session.messages, source_history)
            self.assertEqual(session.world_state["campaign_time"], healing_clock)
            healed = copy.deepcopy(session.ensure_death_state())
            expected = copy.deepcopy(pending)
            expected.update(successes=0, failures=0, stable=False, recovery=None,
                            noncombat_episode_id=None, noncombat_next_save_at=None)
            self.assertEqual(healed, expected)
            self.assertEqual(healed["last_death_save_result"], receipt)
            self.assertEqual(healed["last_death_save_turn_key"],
                             f"noncombat:{episode}:{old_deadline - 6}")

            def assert_healed(owner):
                self.assertEqual(owner.character["current_hp"], 3)
                self.assertEqual(owner.character["max_hp"], 20)
                self.assertEqual(owner.world_state["player_combat_status"], "active")
                self.assertFalse(owner.world_state["combat"]["active"])
                self.assertEqual(owner.ensure_death_state(), expected)

            assert_healed(session)
            self.assertEqual(session.save_game(path), path)
            committed = session.serialize_game_state()
            saved_files[path] = path.read_bytes()
            self.assertEqual(json.loads(saved_files[path]), committed)
            protected = (session,) + protected
            snapshots.insert(0, committed)
            rng_states.insert(0, healing_rng)
            histories.insert(0, source_history)
            load_rng = reopened.rng.getstate()
            load_history = copy.deepcopy(reopened.messages)

            def assert_preserved(*, reopened_rng=None):
                if reopened_rng is None:
                    reopened_rng = load_rng
                for owner, snapshot, rng_state, history in zip(
                    protected, snapshots, rng_states, histories
                ):
                    self.assertEqual(owner.serialize_game_state(), snapshot)
                    self.assertEqual(owner.rng.getstate(), rng_state)
                    self.assertEqual(owner.messages, history)
                self.assertEqual(random.getstate(), module_rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                self.assertEqual(reopened.rng.getstate(), reopened_rng)
                self.assertEqual(reopened.messages, load_history)
                for saved_path, content in saved_files.items():
                    self.assertEqual(saved_path.read_bytes(), content)
                self.assertEqual(set(Path(directory).iterdir()), set(saved_files))

            with (
                patch("game.roll_d20", side_effect=AssertionError("Healed player rolled a save")),
                patch.object(reopened.rng, "randint",
                             side_effect=AssertionError("Healed player consumed RNG")) as die,
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                self.assertEqual(reopened.load_game(path), committed)
                self.assertEqual(reopened.serialize_game_state(), committed)
                for owner in protected:
                    self.assertIsNot(reopened.world_state, owner.world_state)
                    self.assertIsNot(reopened.character, owner.character)
                    self.assertIsNot(reopened.rng, owner.rng)
                    self.assertIsNot(reopened.ensure_death_state(), owner.ensure_death_state())
                assert_healed(reopened)
                assert_preserved()
                now = healing_clock["elapsed_seconds"]
                targets = (
                    (now, old_deadline - 3) if new_injury else
                    (now, old_deadline - 1, old_deadline, old_deadline,
                     old_deadline + 1, old_deadline + 6,
                     old_deadline + 12, old_deadline + 14401)
                )
                for target in targets:
                    later = reopened.advance_campaign_time(target - now, "wait")
                    self.assertEqual(later["death_results"], [])
                    self.assertEqual(later["elapsed_seconds"], target - now)
                    self.assertEqual(
                        reopened.world_state["campaign_time"]["elapsed_seconds"], target
                    )
                    now = target
                    assert_healed(reopened)
                    assert_preserved()
                    die.assert_not_called()
                    heal.assert_not_called()

            if new_injury:
                def reopen_new_episode(filename, expected_death):
                    nonlocal reopened, protected, load_rng, load_history
                    previous = reopened
                    saved_path = Path(directory) / filename
                    self.assertEqual(previous.save_game(saved_path), saved_path)
                    snapshot = previous.serialize_game_state()
                    saved_files[saved_path] = saved_path.read_bytes()
                    self.assertEqual(json.loads(saved_files[saved_path]), snapshot)
                    previous_rng = previous.rng.getstate()
                    previous_history = copy.deepcopy(previous.messages)
                    resumed = make_session(seed=83)
                    resumed.messages.append({"role": "user", "content": filename})
                    resumed_rng = resumed.rng.getstate()
                    resumed_history = copy.deepcopy(resumed.messages)
                    with (
                        patch("game.roll_d20",
                              side_effect=AssertionError("Reopening new episode rolled")),
                        patch.object(resumed.rng, "randint",
                                     side_effect=AssertionError("Reopening consumed RNG")),
                        patch("game.heal_player",
                              side_effect=AssertionError("Reopening healed new injury")),
                    ):
                        self.assertEqual(resumed.load_game(saved_path), snapshot)
                        self.assertEqual(resumed.serialize_game_state(), snapshot)
                        self.assertEqual(resumed.ensure_death_state(), expected_death)
                        self.assertEqual(resumed.world_state["campaign_time"],
                                         previous.world_state["campaign_time"])
                        self.assertEqual(resumed.rng.getstate(), resumed_rng)
                        self.assertEqual(resumed.messages, resumed_history)
                    protected += (previous,)
                    snapshots.append(snapshot)
                    rng_states.append(previous_rng)
                    histories.append(previous_history)
                    reopened = resumed
                    load_rng = resumed_rng
                    load_history = resumed_history
                    for owner in protected:
                        self.assertIsNot(reopened.world_state, owner.world_state)
                        self.assertIsNot(reopened.character, owner.character)
                        self.assertIsNot(reopened.rng, owner.rng)
                        self.assertIsNot(reopened.ensure_death_state(), owner.ensure_death_state())
                    assert_preserved()

                # The old pending deadline is still ahead when legitimate damage
                # drops the reopened, healed character back to zero HP.
                with (
                    patch("game.roll_d20", side_effect=AssertionError("New injury rolled")),
                    patch.object(reopened.rng, "randint",
                                 side_effect=AssertionError("New injury consumed RNG")) as die,
                    patch("game.heal_player", side_effect=AssertionError("New injury healed")),
                ):
                    damage = reopened._apply_player_damage(3, took_damage=True)
                    self.assertEqual(damage["hp_before"], 3)
                    self.assertEqual(damage["hp_after"], 0)
                    self.assertEqual(damage["status"], "unconscious")
                    self.assertIsNone(damage["death_resolution"])
                    injured = copy.deepcopy(reopened.ensure_death_state())
                    new_episode = injured["noncombat_episode_id"]
                    new_deadline = now + 6
                    self.assertIsInstance(new_episode, str)
                    self.assertTrue(new_episode)
                    self.assertNotEqual(new_episode, episode)
                    self.assertNotEqual(new_deadline, old_deadline)
                    injury_expected = copy.deepcopy(expected)
                    injury_expected.update(prone=True, noncombat_episode_id=new_episode,
                                           noncombat_next_save_at=new_deadline)
                    self.assertEqual(injured, injury_expected)
                    self.assertEqual((injured["successes"], injured["failures"]), (0, 0))
                    self.assertEqual(injured["last_death_save_result"], receipt)
                    self.assertEqual(injured["last_death_save_turn_key"],
                                     healed["last_death_save_turn_key"])
                    die.assert_not_called()
                # Persist the new pending episode while the healed episode's
                # failed receipt is still retained. Loading must not rebase its
                # absolute deadline or make the old deadline actionable.
                reopen_new_episode("new-injury-pending.json", injured)
                if long_wait:
                    self._assert_reopened_reinjury_catch_up(
                        reopened, Path(directory) / "new-injury-pending.json",
                        injured, receipt, old_deadline, assert_preserved,
                    )
                    return
                with (
                    patch("game.roll_d20", side_effect=AssertionError("Early new save rolled")),
                    patch.object(reopened.rng, "randint",
                                 side_effect=AssertionError("Early new save consumed RNG")) as die,
                    patch("game.heal_player", side_effect=AssertionError("Early new save healed")),
                ):
                    for target in (now, old_deadline - 1, old_deadline, old_deadline,
                                   old_deadline + 1, new_deadline - 1):
                        early = reopened.advance_campaign_time(target - now, "wait")
                        self.assertEqual(early["death_results"], [])
                        self.assertEqual(early["elapsed_seconds"], target - now)
                        self.assertEqual(
                            reopened.world_state["campaign_time"]["elapsed_seconds"], target
                        )
                        now = target
                        self.assertEqual(reopened.ensure_death_state(), injured)
                        self.assertEqual(reopened.character["current_hp"], 0)
                        self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                        self.assertFalse(reopened.world_state["combat"]["active"])
                        assert_preserved()
                    die.assert_not_called()

                reference = random.Random()
                reference.setstate(load_rng)
                expected_roll = reference.randint(1, 20)
                self.assertTrue(10 <= expected_roll < 20)
                with (
                    patch.object(reopened.rng, "randint", wraps=reopened.rng.randint) as die,
                    patch("game.heal_player", side_effect=AssertionError("New save healed")),
                ):
                    due = reopened.advance_campaign_time(1, "wait")
                    self.assertEqual(len(due["death_results"]), 1)
                    entry = due["death_results"][0]
                    self.assertEqual(entry["action"], "death_save")
                    new_receipt = entry["death_save"]
                    self.assertEqual(new_receipt["roll"], expected_roll)
                    self.assertEqual(new_receipt["outcome"], "success")
                    self.assertNotEqual(new_receipt, receipt)
                    after = copy.deepcopy(injured)
                    after.update(successes=1, noncombat_next_save_at=new_deadline + 6,
                                 last_death_save_turn_key=f"noncombat:{new_episode}:{new_deadline}",
                                 last_death_save_result=new_receipt)
                    self.assertEqual(reopened.ensure_death_state(), after)
                    self.assertNotEqual(after["last_death_save_turn_key"],
                                        healed["last_death_save_turn_key"])
                    self.assertEqual(
                        reopened.world_state["campaign_time"]["elapsed_seconds"], new_deadline
                    )
                    for duration in (0, 0):
                        self.assertEqual(
                            reopened.advance_campaign_time(duration, "wait")["death_results"], []
                        )
                        self.assertEqual(reopened.ensure_death_state(), after)
                        self.assertEqual(reopened.character["current_hp"], 0)
                        self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                        self.assertFalse(reopened.world_state["combat"]["active"])
                        die.assert_called_once_with(1, 20)
                        assert_preserved(reopened_rng=reference.getstate())

                # Reopen at the first new receipt boundary as well: the receipt
                # and next absolute deadline must survive without a second roll.
                reopen_new_episode("new-injury-first-receipt.json", after)
                with (
                    patch("game.roll_d20", side_effect=AssertionError("Saved receipt rerolled")),
                    patch.object(reopened.rng, "randint",
                                 side_effect=AssertionError("Saved receipt consumed RNG")) as die,
                    patch("game.heal_player", side_effect=AssertionError("Saved receipt healed")),
                ):
                    now = new_deadline
                    for duration in (0, 0, 1, 0):
                        repeated = reopened.advance_campaign_time(duration, "wait")
                        self.assertEqual(repeated["death_results"], [])
                        self.assertEqual(repeated["elapsed_seconds"], duration)
                        now += duration
                        self.assertEqual(
                            reopened.world_state["campaign_time"]["elapsed_seconds"], now
                        )
                        self.assertEqual(reopened.ensure_death_state(), after)
                        self.assertEqual(reopened.character["current_hp"], 0)
                        self.assertEqual(reopened.world_state["player_combat_status"], "unconscious")
                        self.assertFalse(reopened.world_state["combat"]["active"])
                        die.assert_not_called()
                        assert_preserved()

    def _assert_reopened_reinjury_catch_up(
        self, reopened, pending_path, injured, old_receipt, old_deadline, assert_preserved
    ):
        incremental = make_session(seed=83)
        incremental.messages.append({"role": "user", "content": "Incremental wait"})
        incremental_rng = incremental.rng.getstate()
        incremental_history = copy.deepcopy(incremental.messages)
        with (
            patch("game.roll_d20", side_effect=AssertionError("Comparison load rolled")),
            patch.object(incremental.rng, "randint",
                         side_effect=AssertionError("Comparison load consumed RNG")),
            patch("game.heal_player", side_effect=AssertionError("Comparison load healed")),
        ):
            self.assertEqual(incremental.load_game(pending_path),
                             reopened.serialize_game_state())
        self.assertEqual(incremental.rng.getstate(), incremental_rng)
        self.assertEqual(incremental.messages, incremental_history)
        self.assertIsNot(incremental.world_state, reopened.world_state)
        self.assertIsNot(incremental.character, reopened.character)
        self.assertIsNot(incremental.rng, reopened.rng)
        self.assertIsNot(incremental.ensure_death_state(), reopened.ensure_death_state())
        assert_preserved()

        start = reopened.world_state["campaign_time"]["elapsed_seconds"]
        deadline = injured["noncombat_next_save_at"]
        episode = injured["noncombat_episode_id"]
        self.assertLess(start, old_deadline)
        self.assertLess(old_deadline, deadline)
        # The new owner's seeded stream gives two successes and two failures:
        # no revival, stabilization, death, or Normal-mode rollback can mask
        # incorrect catch-up scheduling.
        reference = random.Random()
        reference.setstate(reopened.rng.getstate())
        rolls = [reference.randint(1, 20) for _ in range(4)]
        self.assertEqual(rolls, [16, 15, 3, 5])
        finish = deadline + 23  # Four deadlines; stop one second before the fifth.
        expected_receipts = []
        running_rng = random.Random()
        running_rng.setstate(incremental_rng)
        with (
            patch.object(incremental.rng, "randint", wraps=incremental.rng.randint) as die,
            patch("game.heal_player", side_effect=AssertionError("Incremental wait healed")),
        ):
            now = start
            for target in (old_deadline - 1, old_deadline, old_deadline, deadline - 1,
                           deadline, deadline, deadline + 6, deadline + 12,
                           deadline + 18, finish, finish):
                result = incremental.advance_campaign_time(target - now, "wait")
                self.assertEqual(result["elapsed_seconds"], target - now)
                self.assertEqual(result["remaining_seconds"], 0)
                self.assertFalse(result["interrupted"])
                now = target
                self.assertEqual(incremental.world_state["campaign_time"]["elapsed_seconds"],
                                 target)
                count = max(0, min(4, (target - deadline) // 6 + 1))
                new_count = count - len(expected_receipts)
                self.assertEqual(len(result["death_results"]), new_count)
                if new_count:
                    entry = result["death_results"][0]
                    self.assertEqual(entry["action"], "death_save")
                    save = entry["death_save"]
                    self.assertEqual(save["roll"], running_rng.randint(1, 20))
                    self.assertEqual(save["outcome"], "success" if count <= 2 else "failure")
                    self.assertNotEqual(save, old_receipt)
                    expected_receipts.append(copy.deepcopy(entry))
                expected = copy.deepcopy(injured)
                expected.update(successes=min(count, 2), failures=max(0, count - 2),
                                noncombat_next_save_at=deadline + count * 6)
                if count:
                    expected.update(
                        last_death_save_turn_key=f"noncombat:{episode}:{deadline + (count - 1) * 6}",
                        last_death_save_result=expected_receipts[-1]["death_save"],
                    )
                self.assertEqual(incremental.ensure_death_state(), expected)
                self.assertEqual(incremental.character["current_hp"], 0)
                self.assertEqual(incremental.world_state["player_combat_status"], "unconscious")
                self.assertFalse(incremental.world_state["combat"]["active"])
                self.assertEqual(die.call_count, count)
                self.assertEqual(incremental.rng.getstate(), running_rng.getstate())
                self.assertEqual(incremental.messages, incremental_history)
                # The comparison run must not advance the long-wait owner.
                self.assertEqual(reopened.ensure_death_state(), injured)
                self.assertEqual(reopened.world_state["campaign_time"]["elapsed_seconds"], start)
                assert_preserved()
            self.assertEqual([call.args for call in die.call_args_list], [(1, 20)] * 4)

        comparison = incremental.serialize_game_state()
        with (
            patch.object(reopened.rng, "randint", wraps=reopened.rng.randint) as die,
            patch("game.heal_player", side_effect=AssertionError("Long wait healed")),
        ):
            result = reopened.advance_campaign_time(finish - start, "wait")
            self.assertEqual(result["elapsed_seconds"], finish - start)
            self.assertEqual(result["requested_seconds"], finish - start)
            self.assertEqual(result["remaining_seconds"], 0)
            self.assertFalse(result["interrupted"])
            self.assertEqual(result["death_results"], expected_receipts)
            self.assertEqual(reopened.serialize_game_state(), comparison)
            self.assertEqual(reopened.rng.getstate(), reference.getstate())
            self.assertEqual(reopened.ensure_death_state()["noncombat_next_save_at"],
                             deadline + 24)
            for _ in range(2):
                self.assertEqual(reopened.advance_campaign_time(0, "wait")["death_results"], [])
                self.assertEqual(reopened.serialize_game_state(), comparison)
                self.assertEqual(incremental.serialize_game_state(), comparison)
                self.assertEqual(incremental.rng.getstate(), reference.getstate())
                self.assertEqual(incremental.messages, incremental_history)
                assert_preserved(reopened_rng=reference.getstate())
            self.assertEqual([call.args for call in die.call_args_list], [(1, 20)] * 4)

    def test_repeated_stabilization_preserves_saved_recovery_after_reopening(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_stable_recovery_round_trip(mode, repeat_stabilization=True)

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
        positive_maximum=None, repeat_stabilization=False
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

                if repeat_stabilization:
                    death_at_load = copy.deepcopy(reopened.ensure_death_state())
                    clock_at_load = copy.deepcopy(reopened.world_state["campaign_time"])
                    self.assertEqual(reopened.character["current_hp"], 0)
                    self.assertTrue(death_at_load["stable"])
                    self.assertIsNot(reopened.rng, session.rng)
                    # Repeated stabilization must keep the absolute deadline
                    # created before saving, not start a new duration on reopen.
                    for _ in range(2):
                        self.assertEqual(
                            reopened.stabilize_player(),
                            {"action": "stabilize", "success": True, "status": "resolved"},
                        )
                        self.assertEqual(reopened.serialize_game_state(), committed)
                        self.assertEqual(reopened.ensure_death_state(), death_at_load)
                        self.assertEqual(reopened.ensure_death_state()["recovery"], recovery)
                        self.assertEqual(reopened.world_state["campaign_time"], clock_at_load)
                        self.assertEqual(reopened.character["current_hp"], 0)
                        self.assertEqual(
                            reopened.world_state["player_combat_status"], "unconscious"
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

    def test_noncombat_natural_twenty_revival_clears_saved_absolute_deadline(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                self._assert_noncombat_natural_twenty_revival_round_trip(mode)

    def test_noncombat_natural_twenty_finishes_oversized_wait_without_more_saves(self):
        for mode in ("NORMAL", "PERMADEATH", "IRONMAN"):
            with self.subTest(mode=mode):
                session = make_session(seed=5)
                campaign_time.initialize(session.world_state)
                session.ensure_death_state()["mode"] = mode
                session.advance_campaign_time(137, "wait")
                session._apply_player_damage(20, took_damage=True)
                death = session.ensure_death_state()
                deadline = death["noncombat_next_save_at"]
                episode = death["noncombat_episode_id"]
                self.assertEqual(deadline, 143)
                self.assertIsInstance(episode, str)
                self.assertTrue(episode)
                self.assertFalse(session.world_state["combat"]["active"])
                self.assertEqual(session.character["current_hp"], 0)
                death.update(successes=2, failures=2)
                started_at = session.world_state["campaign_time"]["elapsed_seconds"]
                # One call crosses the first save, many later six-second save
                # boundaries, and even the maximum four-hour recovery window.
                duration = deadline - started_at + 14401
                reference_rng = random.Random()
                reference_rng.setstate(session.rng.getstate())
                self.assertEqual(reference_rng.randint(1, 20), 20)
                original_resolve = game._resolve_player_death_turn
                receipts = []

                def resolve_at_first_deadline(**kwargs):
                    self.assertEqual(
                        session.world_state["campaign_time"]["elapsed_seconds"], deadline
                    )
                    result = original_resolve(**kwargs)
                    receipts.append(copy.deepcopy(result))
                    return result

                turn_key = f"noncombat:{episode}:{deadline}"
                with (
                    patch("game._resolve_player_death_turn",
                          side_effect=resolve_at_first_deadline) as resolve,
                    patch("game.roll_d20", wraps=game.roll_d20) as roll,
                    patch.object(session.rng, "randint", wraps=session.rng.randint) as die,
                    patch("game.heal_player", wraps=game.heal_player) as heal,
                    patch("game.stabilize_player",
                          side_effect=AssertionError("Revival scheduled recovery")),
                ):
                    progress = session.advance_campaign_time(duration, "wait")

                resolve.assert_called_once_with(noncombat_key=turn_key)
                roll.assert_called_once_with()
                die.assert_called_once_with(1, 20)
                heal.assert_called_once_with(1)
                self.assertEqual(session.rng.getstate(), reference_rng.getstate())
                self.assertEqual(progress["requested_seconds"], duration)
                self.assertEqual(progress["elapsed_seconds"], duration)
                self.assertEqual(progress["remaining_seconds"], 0)
                self.assertFalse(progress["interrupted"])
                self.assertEqual(
                    session.world_state["campaign_time"]["elapsed_seconds"], deadline + 14401
                )
                self.assertEqual(progress["death_results"], [
                    {"action": "death_save", "death_save": receipts[0]},
                ])
                self.assertEqual(receipts[0]["roll"], 20)
                self.assertEqual(receipts[0]["outcome"], "revived")
                self.assertNotIn("death_resolution", receipts[0])
                self.assertEqual(session.character["current_hp"], 1)
                self.assertEqual(session.world_state["player_combat_status"], "active")
                self.assertFalse(session.world_state["combat"]["active"])
                after = session.ensure_death_state()
                self.assertEqual(after["mode"], mode)
                self.assertEqual((after["successes"], after["failures"]), (0, 0))
                self.assertTrue(after["prone"])
                self.assertFalse(after["stable"])
                self.assertFalse(after["dead"])
                self.assertFalse(after["terminal"])
                self.assertIsNone(after["noncombat_next_save_at"])
                self.assertIsNone(after["noncombat_episode_id"])
                self.assertIsNone(after["recovery"])
                self.assertEqual(after["last_death_save_turn_key"], turn_key)
                self.assertEqual(after["last_death_save_result"], receipts[0])

    def _assert_noncombat_natural_twenty_revival_round_trip(self, mode):
        session = make_session(seed=5)
        peer = make_session(seed=29)
        reopened = make_session(seed=83)
        campaign_time.initialize(session.world_state)
        campaign_time.initialize(peer.world_state)
        session.ensure_death_state()["mode"] = mode
        session.advance_campaign_time(137, "wait")
        session._apply_player_damage(20, took_damage=True)
        death = session.ensure_death_state()
        deadline = death["noncombat_next_save_at"]
        episode = death["noncombat_episode_id"]
        self.assertEqual(deadline, 143)
        self.assertIsInstance(episode, str)
        self.assertTrue(episode)
        self.assertFalse(session.world_state["combat"]["active"])
        self.assertEqual(session.character["current_hp"], 0)
        self.assertEqual(session.world_state["player_combat_status"], "unconscious")
        death.update(successes=2, failures=2)
        pending_rng = session.rng.getstate()
        with patch("game.roll_d20", side_effect=AssertionError("Early death save")):
            self.assertEqual(session.advance_campaign_time(5, "wait")["death_results"], [])
        self.assertEqual(death["noncombat_next_save_at"], deadline)
        self.assertEqual(death["noncombat_episode_id"], episode)
        self.assertEqual(session.rng.getstate(), pending_rng)

        # Use the real session RNG: seed 5's first d20 is a natural twenty.
        reference_rng = random.Random()
        reference_rng.setstate(pending_rng)
        self.assertEqual(reference_rng.randint(1, 20), 20)
        with (
            patch.object(session.rng, "randint", wraps=session.rng.randint) as die,
            patch("game.heal_player", wraps=game.heal_player) as heal,
        ):
            due = session.advance_campaign_time(1, "wait")
        die.assert_called_once_with(1, 20)
        heal.assert_called_once_with(1)
        self.assertEqual(session.rng.getstate(), reference_rng.getstate())
        self.assertEqual(len(due["death_results"]), 1)
        result = due["death_results"][0]["death_save"]
        self.assertEqual(due["death_results"], [
            {"action": "death_save", "death_save": result},
        ])
        self.assertEqual(result["roll"], 20)
        self.assertEqual(result["outcome"], "revived")
        self.assertEqual((result["successes"], result["failures"]), (0, 0))
        self.assertTrue(result["prone"])
        self.assertFalse(result["stable"])
        self.assertFalse(result["dead"])
        self.assertNotIn("death_resolution", result)
        turn_key = f"noncombat:{episode}:{deadline}"
        revived_death = copy.deepcopy(session.ensure_death_state())

        def assert_revived(owner):
            self.assertEqual(owner.character["current_hp"], 1)
            self.assertEqual(owner.character["max_hp"], 20)
            self.assertEqual(owner.world_state["player_combat_status"], "active")
            self.assertFalse(owner.world_state["combat"]["active"])
            self.assertEqual(owner.ensure_death_state(), revived_death)
            current = owner.ensure_death_state()
            self.assertEqual(current["mode"], mode)
            self.assertEqual((current["successes"], current["failures"]), (0, 0))
            self.assertTrue(current["prone"])
            self.assertFalse(current["stable"])
            self.assertFalse(current["dead"])
            self.assertFalse(current["terminal"])
            self.assertIsNone(current["noncombat_next_save_at"])
            self.assertIsNone(current["noncombat_episode_id"])
            self.assertIsNone(current["recovery"])
            self.assertEqual(current["last_death_save_turn_key"], turn_key)
            self.assertEqual(current["last_death_save_result"], result)
            public = serialize_session_state(owner)["death_state"]
            self.assertEqual(public["status"], "active")
            self.assertEqual(public["last_death_save"], {
                key: value for key, value in result.items() if value is not None
            })

        assert_revived(session)
        self.assertEqual(session.world_state["campaign_time"]["elapsed_seconds"], deadline)
        peer.messages.append({"role": "user", "content": "Unrelated history"})
        reopened.messages.append({"role": "user", "content": "Fresh owner history"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noncombat-revived.json"
            peer_path = Path(directory) / "unrelated.json"
            # Save at the revival boundary, before advancing any further.
            self.assertEqual(session.save_game(path), path)
            self.assertEqual(peer.save_game(peer_path), peer_path)
            saved_files = {path: path.read_bytes(), peer_path: peer_path.read_bytes()}
            committed = session.serialize_game_state()
            self.assertEqual(json.loads(saved_files[path]), committed)
            protected = (session, peer, game._DEFAULT_SESSION)
            snapshots = [owner.serialize_game_state() for owner in protected]
            rng_states = [owner.rng.getstate() for owner in protected]
            histories = [copy.deepcopy(owner.messages) for owner in protected]
            module_rng = random.getstate()
            load_rng = reopened.rng.getstate()
            load_history = copy.deepcopy(reopened.messages)

            def assert_preserved():
                for owner, snapshot, rng_state, history in zip(
                    protected, snapshots, rng_states, histories
                ):
                    self.assertEqual(owner.serialize_game_state(), snapshot)
                    self.assertEqual(owner.rng.getstate(), rng_state)
                    self.assertEqual(owner.messages, history)
                self.assertEqual(reopened.rng.getstate(), load_rng)
                self.assertEqual(reopened.messages, load_history)
                self.assertEqual(random.getstate(), module_rng)
                self.assertIs(game._session(), game._DEFAULT_SESSION)
                for saved_path, content in saved_files.items():
                    self.assertEqual(saved_path.read_bytes(), content)
                self.assertEqual(set(Path(directory).iterdir()), set(saved_files))

            with (
                patch("game.roll_d20", side_effect=AssertionError("Revival rerolled a save")),
                patch.object(reopened.rng, "randint",
                             side_effect=AssertionError("Revival consumed RNG")),
                patch("game.heal_player", wraps=game.heal_player) as heal,
            ):
                self.assertEqual(reopened.load_game(path), committed)
                self.assertEqual(reopened.serialize_game_state(), committed)
                for owner in protected:
                    self.assertIsNot(reopened.world_state, owner.world_state)
                    self.assertIsNot(reopened.character, owner.character)
                    self.assertIsNot(reopened.rng, owner.rng)
                    self.assertIsNot(reopened.ensure_death_state(), owner.ensure_death_state())
                assert_revived(reopened)
                assert_preserved()
                heal.assert_not_called()
                # Revisit the consumed absolute deadline, cross the would-be
                # next save, then cross the entire 1d4-hour recovery window.
                now = deadline
                for target in (deadline, deadline + 5, deadline + 6,
                               deadline + 12, deadline + 3600, deadline + 14400,
                               deadline + 14401):
                    later = reopened.advance_campaign_time(target - now, "wait")
                    self.assertEqual(later["death_results"], [])
                    self.assertEqual(later["elapsed_seconds"], target - now)
                    self.assertEqual(
                        reopened.world_state["campaign_time"]["elapsed_seconds"], target
                    )
                    now = target
                    assert_revived(reopened)
                    assert_preserved()
                    heal.assert_not_called()
                later_path = Path(directory) / "noncombat-revived-later.json"
                self.assertEqual(reopened.save_game(later_path), later_path)
                saved_files[later_path] = later_path.read_bytes()
                self.assertEqual(json.loads(saved_files[later_path]),
                                 reopened.serialize_game_state())
                assert_revived(reopened)
                assert_preserved()
                heal.assert_not_called()

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
