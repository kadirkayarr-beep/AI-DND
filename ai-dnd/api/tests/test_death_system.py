from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


AI_DND_DIR = Path(__file__).resolve().parents[2]
if str(AI_DND_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DND_DIR))

import game
from api.serializers import serialize_session_state


def make_session():
    session = game.GameSession(seed=17)
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