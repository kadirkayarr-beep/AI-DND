"""4A.2 death-rules audit: source-backed oracle cases and the table-rule label.

Expected values are written by hand from the cited rule (PHB 2024: Dropping to 0 Hit Points / Death Saving Throws on pdf page 28,
the Unconscious condition on pdf page 376), never taken from engine output. No HTTP case: every case drives a GameSession directly.
"""
from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

import game
import rule_oracles
from api.tests.test_death_system import make_session, start_test_combat

ORACLES = rule_oracles.load_oracles()
LAST_CORE_CASE = 20
LAST_UNCONSCIOUS_CASE = 3


def shortbow_enemy(session, distance):
    enemy = {
        "id": "audit-archer", "name": "Audit Archer", "location": session.world_state["location"],
        "combat_status": "active", "current_hp": 10, "max_hp": 10, "armor_class": 10,
        "attack_bonus": 0, "damage_die": 8, "damage_dice": 1, "damage_modifier": 0,
        "distance_ft": distance, "weapon_id": "shortbow", "inventory": ["Shortbow"],
        "equipment": {"main_hand": "shortbow", "off_hand": None}, "dexterity": 14, "dexterity_mod": 2,
        "proficiency_bonus": 2, "weapon_proficiencies": ["simple"], "weapon_masteries": [],
        "ammunition": {"arrow": 20},
    }
    session.world_state["npcs"].append(enemy)
    return enemy


def downed(max_hp=20):
    session = make_session()
    session.ensure_death_state()["mode"] = "PERMADEATH"
    session.character.update(max_hp=max_hp, current_hp=0)
    session.world_state["player_combat_status"] = "unconscious"
    return session


class DeathTableHouseRules(unittest.TestCase):
    def test_new_oracle_cases_match_source(self):
        for number in range(15, LAST_CORE_CASE + 1):
            with self.subTest(case=number):
                result = rule_oracles.evaluate_rule_case(f"K07.death_saves_and_stable.core#{number:02d}", ORACLES)
                self.assertTrue(result["match"], result)
                self.assertEqual(result["source_ref"]["pdf_page"], 28)

    def test_unconscious_condition_oracle_cases_match_source(self):
        for number in range(1, LAST_UNCONSCIOUS_CASE + 1):
            with self.subTest(case=number):
                result = rule_oracles.evaluate_rule_case(
                    f"K07.death_saves_and_stable.unconscious_condition#{number:02d}", ORACLES)
                self.assertTrue(result["match"], result)
                self.assertEqual(result["source_ref"]["pdf_page"], 376)

    def test_massive_damage_threshold_from_positive_hp(self):
        # Damage left over after reaching 0 HP: 11 < 12 lives, 12 == 12 dies; from full HP 24 - 12 = 12 dies, 23 lives.
        for max_hp, hp, damage, dead in ((12, 6, 17, False), (12, 6, 18, True), (12, 12, 24, True), (12, 12, 23, False)):
            with self.subTest(max_hp=max_hp, hp=hp, damage=damage):
                session = make_session()
                session.ensure_death_state()["mode"] = "PERMADEATH"
                session.character.update(max_hp=max_hp, current_hp=hp)
                session._apply_player_damage(damage, took_damage=True)
                self.assertEqual(session.ensure_death_state()["dead"], dead)
                self.assertEqual(session.world_state["player_combat_status"], "dead" if dead else "unconscious")
                self.assertEqual(session.character["current_hp"], 0)
                if not dead:
                    self.assertEqual(session.ensure_death_state()["failures"], 0)

    def test_ranged_hit_beyond_five_feet_is_no_automatic_crit(self):
        for distance, failures in ((30, 1), (10, 1), (5, 2)):
            with self.subTest(distance=distance):
                session = downed()
                enemy = shortbow_enemy(session, distance)
                with patch("game.roll_d20", side_effect=[10, 14]), patch("game.roll_damage", return_value=2):
                    result = session.resolve_enemy_attack(enemy)
                self.assertEqual(result["critical"], failures == 2)
                self.assertEqual(session.ensure_death_state()["failures"], failures)

    def test_stable_creature_stays_down_before_its_hours(self):
        session = downed()
        session.commit_location_change("tavern")  # resolves the first scene so campaign time can pass
        with patch.object(session.rng, "randint", return_value=3):
            session.stabilize_player()
        session.advance_campaign_time(2 * 3600, "wait")
        self.assertEqual(session.character["current_hp"], 0)
        self.assertTrue(session.ensure_death_state()["stable"])
        self.assertEqual(session.world_state["player_combat_status"], "unconscious")
        session.advance_campaign_time(3600, "wait")
        self.assertEqual(session.character["current_hp"], 1)

    def test_last_call_is_the_table_rule_only_a_natural_20_and_says_so(self):
        self.assertIn("masa kuralı (SRD'de yok): Kadir kararı 2", inspect.getsource(game._last_call))
        answered = []
        for roll in range(1, 21):
            session = downed()
            death = session.ensure_death_state()
            death.update(dead=True, failures=3)
            session.world_state["player_combat_status"] = "dead"
            with patch("game.roll_d20", return_value=roll):
                session.player_cannot_act_turn()
            answered.append(roll if not session.ensure_death_state()["dead"] else None)
        self.assertEqual([roll for roll in answered if roll], [20])  # 1 face in 20 = 5%

    def test_ironman_has_no_last_call_and_normal_rolls_back(self):
        ironman = make_session()
        death = ironman.ensure_death_state()
        death["mode"] = "IRONMAN"
        start_test_combat(ironman)
        ironman._apply_player_damage(20, took_damage=True)
        death.update(failures=2)
        with patch("game.roll_d20", return_value=2):
            ironman._resolve_player_death_turn()
        self.assertTrue(death["dead"])
        self.assertTrue(death["terminal"])
        with patch("game.roll_d20", side_effect=AssertionError("Ironman has no last call")):
            ironman.player_cannot_act_turn()
        self.assertTrue(death["dead"])

        normal = make_session()
        normal.ensure_death_state()["mode"] = "NORMAL"
        game._capture_combat_death_checkpoint(session=normal)
        result = game._apply_player_damage(40, critical=False, took_damage=True, session=normal)
        self.assertTrue(result["death_resolution"]["rolled_back"])
        self.assertEqual(normal.character["current_hp"], 20)
        self.assertFalse(normal.ensure_death_state()["dead"])


if __name__ == "__main__":
    unittest.main()
