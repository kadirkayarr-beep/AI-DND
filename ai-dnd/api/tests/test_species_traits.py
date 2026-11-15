from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game


def attack_fixture(session, creature):
    """Explicit geometry/type facts; #06 no longer guesses missing attack facts."""
    creature.update(location=session.world_state["location"], distance_ft=5,
                    attack_damage_type="bludgeoning")
    session.world_state["npcs"].append(creature)


def make_session(species: str, *, ancestry: str | None = None, level: int = 5):
    session = game.GameSession(seed=17)
    session.character.update(
        {
            "name": "Test Adventurer",
            "race": species,
            "species": species,
            "class": "Fighter",
            "strength": 14,
            "dexterity": 12,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
            "strength_mod": 2,
            "dexterity_mod": 1,
            "constitution_mod": 2,
            "intelligence_mod": 0,
            "wisdom_mod": 0,
            "charisma_mod": 0,
            "modifiers": {
                "strength": 2,
                "dexterity": 1,
                "constitution": 2,
                "intelligence": 0,
                "wisdom": 0,
                "charisma": 0,
            },
            "proficient_skills": [],
            "level": level,
            "proficiency_bonus": 2,
            "max_hp": 20,
            "current_hp": 8,
            "armor_class": 12,
        }
    )
    session.initialize_species_trait_state(giant_ancestry=ancestry)
    session.commit_location_change("tavern")
    return session


class SpeciesTraitTests(unittest.TestCase):
    def test_saved_species_temporary_hit_points_cannot_exceed_proficiency_bonus(self):
        state = game._new_species_trait_state("Orc", 2)
        state["temporary_hit_points"] = 2
        game._validate_species_trait_state(state, "Orc", 2)
        state["temporary_hit_points"] = 3
        with self.assertRaises(ValueError):
            game._validate_species_trait_state(state, "Orc", 2)

    def test_healing_hands_rolls_and_consumes_long_rest_use(self):
        session = make_session("Aasimar", level=3)
        result = session.resolve_species_trait_action("healing_hands")

        self.assertEqual(result["action"], "healing_hands")
        self.assertEqual(len(result["effects"]["dice"]), 2)
        self.assertGreater(session.character["current_hp"], 8)
        self.assertEqual(
            session.character["species_trait_state"]["healing_hands_uses_remaining"],
            0,
        )

    def test_celestial_revelation_adds_server_sourced_attack_damage(self):
        session = make_session("Aasimar", level=3)
        session.resolve_species_trait_action(
            "celestial_revelation", form="heavenly_wings"
        )
        target = {
            "id": "celestial-target",
            "name": "Celestial Target",
            "current_hp": 20,
            "max_hp": 20,
            "armor_class": 10,
            "combat_status": "active",
        }
        attack_fixture(session, target)

        with (
            patch("game.roll_attack", return_value=15),
            patch("game.roll_damage", return_value=4),
        ):
            result = session.resolve_attack(
                "attack", "Kılıç", game.WEAPONS["Kılıç"], target
            )

        self.assertEqual(result["damage"], 6)
        self.assertEqual(
            result["species_effects"][0],
            {
                "trait": "celestial_revelation",
                "damage": 2,
                "damage_type": "radiant",
            },
        )
        self.assertEqual(
            session.character["species_trait_state"][
                "celestial_revelation_uses_remaining"
            ],
            0,
        )

    def test_necrotic_shroud_frightens_until_the_end_of_the_next_player_turn(self):
        session = make_session("Aasimar", level=3)
        enemy = {
            "id": "shrouded-enemy",
            "name": "Shrouded Enemy",
            "location": session.world_state["location"],
            "combat_status": "active",
            "current_hp": 10,
            "max_hp": 10,
            "armor_class": 10,
            "attack_bonus": 0,
            "damage_die": 8,
            "damage_dice": 1,
            "damage_modifier": 0,
            "charisma_save_bonus": 0,
        }
        attack_fixture(session, enemy)

        with patch("game.roll_d20", return_value=1):
            result = session.resolve_species_trait_action(
                "celestial_revelation", form="necrotic_shroud"
            )
        self.assertTrue(result["effects"]["saves"][0]["frightened"])
        self.assertEqual(enemy["frightened_until_player_turn"], 2)

        with (
            patch("game.roll_d20", side_effect=[13, 18]),
            patch("game.roll_damage", return_value=1),
        ):
            enemy_attack = session.resolve_enemy_attack(enemy)
        self.assertTrue(enemy_attack["disadvantage"])
        self.assertEqual(enemy_attack["attack_rolls"], [13, 18])

    def test_goliath_ancestry_adds_server_rolled_fire_damage_once(self):
        session = make_session("Goliath", ancestry="fire")
        session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
        target = {
            "id": "practice-target",
            "name": "Practice Target",
            "current_hp": 20,
            "max_hp": 20,
            "armor_class": 10,
            "combat_status": "active",
        }
        attack_fixture(session, target)

        with (
            patch("game.roll_attack", return_value=15),
            patch("game.roll_damage", return_value=4),
            patch.object(session.rng, "randint", return_value=6),
        ):
            result = session.resolve_attack(
                "attack", "Kılıç", game.WEAPONS["Kılıç"], target
            )

        self.assertEqual(result["damage"], 10)
        self.assertEqual(result["species_effects"][0]["damage_type"], "fire")
        self.assertEqual(
            session.character["species_trait_state"]["giant_ancestry_uses_remaining"],
            1,
        )
        self.assertFalse(
            session.character["species_trait_state"]["giant_ancestry_armed"]
        )

    def _hill_tumble_hit(self, size):
        session = make_session("Goliath", ancestry="hill")
        session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
        target = {
            "id": "tumble-target",
            "name": "Tumble Target",
            "current_hp": 40,
            "max_hp": 40,
            "armor_class": 10,
            "combat_status": "active",
            "size": size,
            "strength_save_bonus": 9,
        }
        attack_fixture(session, target)
        # A natural 20 would pass any Strength save; Hill's Tumble (PHB 2024) has none.
        with (
            patch("game.roll_attack", return_value=15),
            patch("game.roll_damage", return_value=4),
            patch("game.roll_d20", return_value=20) as d20,
        ):
            result = session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
        return session, target, result, d20

    def test_goliath_hill_tumble_knocks_a_large_or_smaller_target_prone_without_a_save(self):
        # D-201: PHB 2024 Hill's Tumble gives Prone on a hit to a Large or smaller creature; no saving throw.
        for size in ("medium", "large"):
            session, target, result, d20 = self._hill_tumble_hit(size)
            self.assertTrue(target.get("prone"), size)
            d20.assert_not_called()
            self.assertEqual(
                result["species_effects"], [{"trait": "hill_giant_ancestry", "knocked_prone": True}]
            )
            state = session.character["species_trait_state"]
            self.assertEqual(state["giant_ancestry_uses_remaining"], 1)
            self.assertFalse(state["giant_ancestry_armed"])

    def test_goliath_hill_tumble_cannot_topple_a_huge_target_and_keeps_its_use(self):
        # D-201: a Huge or larger creature is outside Hill's Tumble; the trait does not trigger, so no use is spent.
        session, target, result, d20 = self._hill_tumble_hit("huge")
        self.assertFalse(target.get("prone"))
        d20.assert_not_called()
        self.assertEqual(result["species_effects"], [])
        state = session.character["species_trait_state"]
        self.assertEqual(state["giant_ancestry_uses_remaining"], 2)
        self.assertTrue(state["giant_ancestry_armed"])

    def test_goliath_hill_tumble_needs_a_known_size_and_keeps_its_use(self):
        # D-201: an unrecognised size cannot be shown to be Large or smaller, so Hill's Tumble fails closed.
        session, target, result, d20 = self._hill_tumble_hit("colossal")
        self.assertFalse(target.get("prone"))
        d20.assert_not_called()
        self.assertEqual(result["species_effects"], [])
        state = session.character["species_trait_state"]
        self.assertEqual(state["giant_ancestry_uses_remaining"], 2)
        self.assertTrue(state["giant_ancestry_armed"])

    def test_goliath_ancestry_needs_the_hit_to_deal_damage(self):
        # D-197: PHB 2024 Giant Ancestry triggers on "hit ... and deal damage"; an immune target takes 0, nothing triggers.
        for ancestry in ("fire", "frost", "hill"):
            session = make_session("Goliath", ancestry=ancestry)
            session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
            target = {
                "id": "immune-target",
                "name": "Immune Target",
                "current_hp": 40,
                "max_hp": 40,
                "armor_class": 10,
                "combat_status": "active",
                "immunities": ["slashing"],
            }
            attack_fixture(session, target)
            with (
                patch("game.roll_attack", return_value=15),
                patch("game.roll_damage", return_value=4),
                patch.object(session.rng, "randint", return_value=6),
            ):
                result = session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
            self.assertTrue(result["hit"], ancestry)
            self.assertEqual(result["damage"], 0, ancestry)
            self.assertEqual(result["species_effects"], [], ancestry)
            self.assertFalse(target.get("prone"), ancestry)
            self.assertEqual(target["current_hp"], 40, ancestry)
            state = session.character["species_trait_state"]
            self.assertEqual(state["giant_ancestry_uses_remaining"], 2, ancestry)
            self.assertTrue(state["giant_ancestry_armed"], ancestry)

    def test_aasimar_celestial_revelation_needs_the_hit_to_deal_damage(self):
        # D-197: PHB 2024 Celestial Revelation extra damage needs "when you deal damage"; an immune target takes 0.
        session = make_session("Aasimar")
        state = session._species_trait_state()
        state["active_celestial_form"] = "heavenly_wings"
        target = {
            "id": "immune-target",
            "name": "Immune Target",
            "current_hp": 40,
            "max_hp": 40,
            "armor_class": 10,
            "combat_status": "active",
            "immunities": ["slashing"],
        }
        attack_fixture(session, target)
        with (
            patch("game.roll_attack", return_value=15),
            patch("game.roll_damage", return_value=4),
        ):
            result = session.resolve_attack("attack", "Kılıç", game.WEAPONS["Kılıç"], target)
        self.assertTrue(result["hit"])
        self.assertEqual(result["damage"], 0)
        self.assertEqual(result["species_effects"], [])
        self.assertEqual(target["current_hp"], 40)
        self.assertNotEqual(state.get("celestial_damage_used_turn"), game._species_player_turn_id())

    def test_orc_adrenaline_rush_and_short_rest_recharge(self):
        session = make_session("Orc")
        result = session.resolve_species_trait_action("adrenaline_rush")

        self.assertEqual(result["effects"]["dash_distance_ft"], 60)
        self.assertEqual(result["effects"]["temporary_hit_points"], 2)
        self.assertEqual(
            session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
            1,
        )

        session.resolve_species_trait_action("short_rest")
        self.assertEqual(
            session.character["species_trait_state"]["adrenaline_rush_uses_remaining"],
            2,
        )

    def test_orc_temporary_hit_points_absorb_damage_before_hit_points(self):
        session = make_session("Orc")
        session.resolve_species_trait_action("adrenaline_rush")
        enemy = {
            "id": "orc-attacker",
            "name": "Attacker",
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
        attack_fixture(session, enemy)

        with (
            patch("game.roll_d20", return_value=15),
            patch("game.roll_damage", return_value=3),
        ):
            result = session.resolve_enemy_attack(enemy)

        self.assertEqual(result["damage"], 3)
        self.assertEqual(result["temporary_hp_absorbed"], 2)
        self.assertEqual(result["hp_damage"], 1)
        self.assertEqual(session.character["current_hp"], 7)

    def test_goliath_stone_ancestry_reduces_incoming_damage_with_server_roll(self):
        session = make_session("Goliath", ancestry="stone")
        session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
        enemy = {
            "id": "stone-attacker",
            "name": "Attacker",
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
        attack_fixture(session, enemy)

        with (
            patch("game.roll_d20", return_value=15),
            patch("game.roll_damage", return_value=10),
            patch.object(session.rng, "randint", return_value=6),
        ):
            result = session.resolve_enemy_attack(enemy)

        self.assertEqual(result["damage"], 2)
        self.assertEqual(session.character["current_hp"], 6)
        self.assertEqual(result["species_effects"][0]["damage_reduced"], 8)
        self.assertEqual(
            session.character["species_trait_state"]["giant_ancestry_uses_remaining"],
            1,
        )

    def test_goliath_stone_endurance_answers_trap_damage_but_storm_needs_a_creature(self):
        # D-202: PHB 2024 Stone's Endurance answers any damage ("When you take damage"); a trap is not a
        # creature, so Storm's Thunder stays unspent.
        import exploration

        trap = {"damage": 5, "damage_type": "piercing"}
        session = make_session("Goliath", ancestry="stone")
        session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
        with patch.object(session.rng, "randint", return_value=6):
            result = exploration._damage(session, trap)
        self.assertEqual(result["damage"], 0)
        self.assertEqual(session.character["current_hp"], 8)
        self.assertEqual(
            result["species_effects"],
            [{"trait": "stone_giant_ancestry", "damage_reduced": 8, "damage_remaining": 0}],
        )
        state = session.character["species_trait_state"]
        self.assertEqual(state["giant_ancestry_uses_remaining"], 1)
        self.assertFalse(state["giant_ancestry_armed"])

        session = make_session("Goliath", ancestry="storm")
        session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
        result = exploration._damage(session, trap)
        self.assertEqual(result["damage"], 5)
        self.assertEqual(session.character["current_hp"], 3)
        self.assertEqual(result["species_effects"], [])
        state = session.character["species_trait_state"]
        self.assertEqual(state["giant_ancestry_uses_remaining"], 2)
        self.assertTrue(state["giant_ancestry_armed"])

    def test_goliath_large_form_reports_strength_advantage_and_speed(self):
        session = make_session("Goliath", ancestry="cloud")

        result = session.resolve_species_trait_action("large_form")

        self.assertEqual(result["effects"]["size"], "Large")
        self.assertEqual(result["effects"]["speed_ft"], 45)
        self.assertTrue(result["effects"]["strength_checks_advantage"])
        self.assertEqual(
            session.character["species_trait_state"]["large_form_turns_remaining"],
            100,
        )

    def test_relentless_endurance_prevents_dropping_to_zero_once(self):
        session = make_session("Orc")
        session.character["current_hp"] = 1
        enemy = {
            "id": "enemy-1",
            "name": "Enemy",
            "location": session.world_state["location"],
            "combat_status": "active",
            "current_hp": 10,
            "max_hp": 10,
            "armor_class": 10,
            "attack_bonus": 20,
            "damage_die": 8,
            "damage_dice": 1,
            "damage_modifier": 10,
        }
        attack_fixture(session, enemy)

        with (
            patch("game.roll_d20", return_value=20),
            patch("game.roll_damage", return_value=10),
        ):
            result = session.resolve_enemy_attack(enemy)

        self.assertEqual(result["target_hp_after"], 1)
        self.assertEqual(
            session.character["species_trait_state"]["relentless_endurance_available"],
            False,
        )
        self.assertIn(
            "relentless_endurance",
            [effect["trait"] for effect in result["species_effects"]],
        )

    def test_relentless_endurance_does_not_prevent_instant_death(self):
        session = make_session("Orc")
        session.character["current_hp"] = 1
        enemy = {
            "id": "overwhelming-enemy",
            "name": "Overwhelming Enemy",
            "location": session.world_state["location"],
            "combat_status": "active",
            "current_hp": 10,
            "max_hp": 10,
            "armor_class": 10,
            "attack_bonus": 20,
            "damage_die": 8,
            "damage_dice": 1,
            "damage_modifier": 10,
        }
        attack_fixture(session, enemy)

        with (
            patch("game.roll_d20", return_value=20),
            patch("game.roll_damage", return_value=21),
        ):
            result = session.resolve_enemy_attack(enemy)

        self.assertEqual(result["target_hp_after"], 0)
        self.assertTrue(
            session.character["species_trait_state"]["relentless_endurance_available"]
        )
        self.assertNotIn(
            "relentless_endurance",
            [effect["trait"] for effect in result["species_effects"]],
        )

    def test_long_rest_and_save_resume_preserve_species_resources(self):
        session = make_session("Goliath", ancestry="storm")
        session.resolve_species_trait_action("arm_giant_ancestry", armed=True)
        state = session.character["species_trait_state"]
        state["giant_ancestry_uses_remaining"] = 1
        session.character["current_hp"] = 3

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "campaign.json"
            session.save_game(path)

            restored = game.GameSession(seed=18)
            restored.load_game(path)
            restored_state = restored.character["species_trait_state"]
            self.assertEqual(restored.character["giant_ancestry"], "storm")
            self.assertEqual(restored_state["giant_ancestry_uses_remaining"], 1)
            self.assertTrue(restored_state["giant_ancestry_armed"])

            restored.resolve_species_trait_action("long_rest")
            self.assertEqual(restored.character["current_hp"], 20)
            self.assertEqual(
                restored.character["species_trait_state"]["giant_ancestry_uses_remaining"],
                2,
            )
            self.assertFalse(
                restored.character["species_trait_state"]["giant_ancestry_armed"]
            )

    def test_legacy_save_without_trait_fields_initializes_compatible_state(self):
        session = make_session("Half-Orc", level=1)
        payload = session.serialize_game_state()
        for field in (
            "species",
            "giant_ancestry",
            "species_trait_state",
            "speed_ft",
        ):
            payload["player"].pop(field, None)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-save.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            restored = game.GameSession(seed=19)
            restored.load_game(path)

        self.assertEqual(restored.character["species"], "Half-Orc")
        self.assertTrue(
            restored.character["species_trait_state"]["relentless_endurance_available"]
        )


if __name__ == "__main__":
    unittest.main()