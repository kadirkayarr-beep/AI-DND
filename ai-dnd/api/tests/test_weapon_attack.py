"""Weapon & Attack Lock: mechanics, shared callers, boundaries and receipts."""
import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch
from uuid import uuid4

import game
import action_economy as ae
import equipment_economy
import weapon_attack as attack
from api.character_creation import configure_character
from weapon_catalog import WEAPONS, lookup
from combat_lifecycle import CombatRequestError
from api.tests.test_combat_lifecycle import ready, CombatLifecycleApiTests
from api.tests.test_action_economy import step
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager


from api.tests.auth_fixture import TEST_PLAYER
def armed(weapon="Longsword", *, mastery=False, distance=5):
    s, n = ready()
    s.character.update(current_hp=100, max_hp=100, strength=16, dexterity=14,
                       strength_mod=3, dexterity_mod=2, proficiency_bonus=2,
                       weapon_proficiencies=["simple", "martial"], conditions=[])
    w = lookup(weapon)
    s.world_state["inventory"] = [weapon]
    s.world_state["equipment"] = {"main_hand": w["weapon_id"], "off_hand": None}
    s.world_state["ammunition"] = {"arrow": 20, "bolt": 20, "bullet": 20, "needle": 20}
    s.character["weapon_masteries"] = [w["weapon_id"]] if mastery else []
    n.update(distance_ft=distance, armor_class=12, current_hp=100, max_hp=100,
             strength_mod=0, dexterity_mod=0, constitution_mod=0)
    return s, n


def resolve(s, n, weapon="Longsword", choice=None, *, rolls=(10,), origin="action"):
    with patch("game.roll_attack", side_effect=list(rolls)), patch.object(s.rng, "randint", return_value=3):
        return attack.resolve(s, "player", n["id"], weapon, choice, origin=origin)


class WeaponTests(unittest.TestCase):
    def assert_invalid_unchanged(self, s, n, weapon, choice=None, origin="action"):
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate(), s.messages))
        with patch("game.roll_attack", side_effect=AssertionError("invalid request rolled")), self.assertRaises(CombatRequestError):
            attack.resolve(s, "player", n["id"], weapon, choice, origin=origin)
        self.assertEqual((s.world_state, s.character, s.rng.getstate(), s.messages), before)

    def test_melee_ranged_thrown_shared_path(self):
        for weapon, distance, choice in (("Longsword", 5, {}), ("Shortbow", 30, {}),
                                        ("Javelin", 20, {"mode": "thrown"})):
            s, n = armed(weapon, distance=distance)
            result = resolve(s, n, weapon, choice)
            self.assertTrue(result["hit"])
            self.assertEqual(n["current_hp"], 100 - result["damage"])
            self.assertEqual(result["damage_type"], lookup(weapon)["damage_type"])

    def test_unseen_sources_and_cancellation(self):
        s, n = armed()
        s.world_state["attack_environment"] = {"pairs": {
            f"player|{n['id']}": {"distance_ft": 5, "attacker_sees_target": False, "target_sees_attacker": False}}}
        result = resolve(s, n)
        self.assertEqual(result["attack_rolls"], [10])
        self.assertIn("unseen_target", result["disadvantage_sources"])
        self.assertIn("unseen_attacker", result["advantage_sources"])

    def test_guessed_wrong_location_misses_even_natural_20_no_damage_rng(self):
        s, n = armed()
        s.world_state["attack_environment"] = {"pairs": {
            f"player|{n['id']}": {"distance_ft": 5, "guessed_location_correct": False}}}
        with patch("game.roll_attack", return_value=20), patch("game.roll_damage", side_effect=AssertionError("damage")):
            r = attack.resolve(s, "player", n["id"], "Longsword")
        self.assertFalse(r["hit"])
        self.assertFalse(r["critical"])
        self.assertEqual(r["damage"], 0)

    def assert_directional_location_guesses(self, *, forward_correct, attack_roll,
                                           reverse_correct=None):
        s, n = armed()
        pairs = {
            f"{n['id']}|player": {
                "distance_ft": 5,
                "guessed_location_correct": (
                    not forward_correct if reverse_correct is None else reverse_correct)},
        }
        if forward_correct is not None:
            pairs[f"player|{n['id']}"] = {
                "distance_ft": 5, "guessed_location_correct": forward_correct}
        else:
            # The reverse pair is the only geometry source, not an NPC fallback.
            del n["distance_ft"]
        s.world_state["attack_environment"] = {"pairs": pairs}
        if forward_correct is None:
            self.assertNotIn(f"player|{n['id']}", pairs)
            self.assertEqual(attack.pair(s, "player", n["id"]), {"distance_ft": 5})
        # Initialize the existing observer/encounter owners before measuring
        # attack mutations, so lazy NPC normalization is not part of the diff.
        import monster_combat
        import monster_perception
        memory = monster_combat.state(s, n["id"])
        monster_perception.snapshot(s, n["id"], memory)
        s.initialize_species_trait_state()
        s.ensure_combat_state()
        expected_save = s.serialize_game_state()
        expected_world = copy.deepcopy(s.world_state)
        unchanged = copy.deepcopy((s.character, s.messages, s.rng.getstate()))
        default_before = copy.deepcopy((
            game._DEFAULT_SESSION.world_state, game._DEFAULT_SESSION.character,
            game._DEFAULT_SESSION.messages, game._DEFAULT_SESSION.rng.getstate()))
        # Exercise the real attack/damage owners, not fixed roll-function mocks.
        hit = forward_correct is not False and (
            attack_roll == 20 or attack_roll + 5 >= 12)
        critical = hit and attack_roll == 20
        damage_values = [4, 6] if critical else [4] if hit else []
        dice = [(20, attack_roll)] + [(8, value) for value in damage_values]
        remaining = iter(dice)

        def owned_randint(low, high):
            self.assertIs(game._session(), s)
            expected = next(remaining, None)
            self.assertIsNotNone(expected, "Unexpected attack or damage die")
            sides, value = expected
            self.assertEqual((low, high), (1, sides))
            return value

        with patch.object(s.rng, "randint", side_effect=owned_randint) as rolls, \
             patch.object(game._DEFAULT_SESSION.rng, "randint",
                          side_effect=AssertionError("Attack used default-session dice")):
            result = attack.resolve(s, "player", n["id"], "Longsword")
            self.assertIsNone(next(remaining, None), "Unused owned dice")
            self.assertEqual(rolls.call_args_list,
                             [call(1, sides) for sides, _ in dice])

        damage = sum(damage_values) + 3 if hit else 0
        self.assertEqual(result["actor_id"], "player")
        self.assertEqual(result["target_id"], n["id"])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["success"], hit)
        self.assertEqual(result["hit"], hit)
        self.assertEqual(result["outcome"],
                         "critical_hit" if critical else "hit" if hit else "miss")
        self.assertEqual(result["critical"], critical)
        self.assertEqual(result["natural_20"], attack_roll == 20)
        self.assertEqual(result["attack_rolls"], [attack_roll])
        self.assertEqual(result["attack_roll"], attack_roll)
        self.assertEqual(result["attack_bonus"], 5)
        self.assertEqual(result["attack_total"], attack_roll + 5)
        self.assertEqual(result["target_ac_base"], 12)
        self.assertEqual(result["target_ac"], 12)
        self.assertEqual(result["advantage_sources"], [])
        self.assertEqual(result["disadvantage_sources"], [])
        self.assertEqual(result["damage_rolls"], [
            {"source": "weapon", "die": 8, "count": len(damage_values),
             "rolls": damage_values}
        ] if hit else [])
        self.assertEqual(result["damage_instances"], [{
            "damage_type": "slashing", "raw_damage": damage,
            "pre_resistance_damage": damage, "flat_reduction": 0,
            "resistance_applied": False, "vulnerability_applied": False,
            "immunity_applied": False, "final_damage": damage,
        }] if hit else [])
        self.assertEqual(result["raw_damage"], damage)
        self.assertEqual(result["damage"], damage)
        self.assertEqual(result["hp_damage"], damage)
        self.assertEqual(result["target_hp_before"], 100)
        self.assertEqual(result["target_hp_after"], 100 - damage)
        self.assertEqual(n["current_hp"], 100 - damage)
        self.assertEqual(s.character["current_hp"], 100)
        self.assertEqual(result["target_status"], "active")
        self.assertEqual(result["resulting_conditions"], [])
        self.assertEqual(result["species_effects"], [])
        self.assertEqual(result["additional_effects"], [])
        self.assertEqual(result["resolution"]["raw_rolls"], [attack_roll])
        self.assertEqual(result["resolution"]["actor_id"], "player")
        self.assertEqual(result["resolution"]["target_id"], n["id"])
        self.assertEqual(result["attack_id"], result["resolution"]["resolution_id"])
        self.assertEqual(result["action_id"], result["resolution"]["action_id"])
        self.assertTrue(result["action_id"])
        self.assertEqual(s.world_state["attack_results"], [result])
        self.assertIsNot(s.world_state["attack_results"][0], result)

        # Only HP, the owned sequence/result, and the perceived attack change.
        expected_target = next(npc for npc in expected_world["npcs"]
                               if npc["id"] == n["id"])
        expected_target["current_hp"] = 100 - damage
        expected_world["combat"]["turn_resources"]["player"]["weapon_sequence"] = {
            "attacks": 1, "light_weapon_ids": [], "light_used": False,
            "cleave_used": False, "loading_origins": [],
            "active_action_key": "action:0", "action_index": 1,
        }
        expected_world["monster_combat"]["actors"][n["id"]]["observations"] = {
            "player": {"threat": 2 if hit else 0, "beliefs": {},
                       "attacked_id": n["id"]},
        }
        expected_world["attack_results"] = [copy.deepcopy(result)]
        expected_save["world_state"] = copy.deepcopy(expected_world)
        self.assertEqual(s.world_state, expected_world)
        self.assertEqual(s.serialize_game_state(), expected_save)
        self.assertEqual((s.character, s.messages, s.rng.getstate()), unchanged)
        self.assertEqual((
            game._DEFAULT_SESSION.world_state, game._DEFAULT_SESSION.character,
            game._DEFAULT_SESSION.messages, game._DEFAULT_SESSION.rng.getstate()),
            default_before)

    def test_false_reverse_location_guess_cannot_override_valid_forward_hit(self):
        self.assert_directional_location_guesses(
            forward_correct=True, attack_roll=15)

    def test_true_reverse_location_guess_cannot_rescue_forward_natural_20_miss(self):
        self.assert_directional_location_guesses(
            forward_correct=False, attack_roll=20)

    def test_false_reverse_only_location_guess_preserves_normal_hit(self):
        self.assert_directional_location_guesses(
            forward_correct=None, reverse_correct=False, attack_roll=15)

    def test_true_reverse_only_location_guess_preserves_normal_hit(self):
        self.assert_directional_location_guesses(
            forward_correct=None, reverse_correct=True, attack_roll=15)

    def test_false_reverse_only_location_guess_preserves_ordinary_miss(self):
        self.assert_directional_location_guesses(
            forward_correct=None, reverse_correct=False, attack_roll=2)

    def test_true_reverse_only_location_guess_cannot_rescue_ordinary_miss(self):
        self.assert_directional_location_guesses(
            forward_correct=None, reverse_correct=True, attack_roll=2)

    def test_false_reverse_only_location_guess_preserves_natural_20_critical(self):
        self.assert_directional_location_guesses(
            forward_correct=None, reverse_correct=False, attack_roll=20)

    def test_true_reverse_only_location_guess_preserves_natural_20_critical(self):
        self.assert_directional_location_guesses(
            forward_correct=None, reverse_correct=True, attack_roll=20)

    def test_hidden_reveals_only_after_legal_attack(self):
        s, n = armed()
        s.character["hidden"] = True
        resolve(s, n, rolls=(1,))
        self.assertFalse(s.character["hidden"])
        s.character["hidden"] = True
        n["distance_ft"] = 500
        self.assert_invalid_unchanged(s, n, "Longsword")
        self.assertTrue(s.character["hidden"])

    def test_proficiency_once_and_sourced_magic_modifiers(self):
        s, n = armed()
        s.world_state["inventory"] = [{"weapon_id": "longsword", "magic_attack_bonus": 2, "magic_damage_bonus": 1}]
        s.character["attack_rules"] = {"attack_modifiers": [{"source": "feat", "value": -1}],
                                      "damage_modifiers": [{"source": "style", "value": 2}]}
        r = resolve(s, n)
        self.assertEqual(r["attack_bonus"], 6)
        self.assertEqual(r["damage"], 9)

    def test_additional_typed_damage_critical(self):
        s, n = armed()
        s.character["attack_rules"] = {"additional_damage": [
            {"source": "owned_feature", "damage_die": 6, "damage_dice": 2,
             "damage_type": "fire", "modifier": 1, "critical_doublable": True}]}
        n["resistances"] = ["fire"]
        r = resolve(s, n, rolls=(20,))
        self.assertEqual([d["count"] for d in r["damage_rolls"]], [2, 4])
        self.assertEqual(r["raw_damage"], 22)
        self.assertEqual(r["damage"], 15)

    def test_existing_species_bonus_dice_critical_and_fixed_bonus_not_doubled(self):
        from api.tests.test_species_traits import make_session
        for species, ancestry, expected, dice in (("Goliath", "fire", 6, 2), ("Aasimar", None, 2, 0)):
            s, n = ready(make_session(species, ancestry=ancestry, level=3))
            n["armor_class"] = 10
            if ancestry:
                s.resolve_species_trait_action("arm_giant_ancestry")
            else:
                s.resolve_species_trait_action("celestial_revelation", form="heavenly_wings")
            r = resolve(s, n, rolls=(20,))
            effect = next(e for e in r["species_effects"] if e.get("damage"))
            self.assertEqual(effect["damage"], expected)
            self.assertEqual(len(effect.get("raw_rolls", [])), dice)

    def test_critical_rolls_all_dice_not_fixed_modifiers(self):
        s, n = armed("Greatsword")
        s.world_state["inventory"] = [{"name": "Greatsword", "magic_damage_bonus": 2}]
        r = resolve(s, n, "Greatsword", rolls=(20,))
        self.assertEqual(r["damage_rolls"][0]["count"], 4)
        self.assertEqual(r["damage"], 17)

    def test_damage_zero_is_still_hit(self):
        s, n = armed()
        s.character["strength_mod"] = -9
        r = resolve(s, n, rolls=(20,))
        self.assertTrue(r["hit"])
        self.assertEqual(r["damage"], 0)
        self.assertEqual(n["current_hp"], 100)

    def test_blowgun_fixed_damage_has_no_ability_modifier(self):
        s, n = armed("Blowgun", distance=20)
        r = resolve(s, n, "Blowgun", rolls=(20,))
        self.assertEqual(r["damage"], 1)
        self.assertEqual(r["damage_rolls"], [])

    def test_cover_most_protective_not_stacked(self):
        s, n = armed()
        s.world_state["attack_environment"] = {"pairs": {
            f"player|{n['id']}": {"distance_ft": 5, "cover": ["half", "three_quarters", "half"]}}}
        r = resolve(s, n)
        self.assertEqual(r["target_ac_base"], 12)
        self.assertEqual(r["target_ac"], 17)
        self.assertEqual(r["cover_state"], "three_quarters")

    def test_underwater_long_range_automatic_miss(self):
        s, n = armed("Shortbow", distance=100)
        s.world_state["attack_environment"] = {"underwater": True}
        r = resolve(s, n, "Shortbow", rolls=(20, 20))
        self.assertFalse(r["hit"])
        self.assertEqual(r["damage_rolls"], [])

    def test_ranged_close_enemy_not_necessarily_target(self):
        s, n = armed("Shortbow", distance=30)
        other = s.create_npc_from_ai({"name": "Yakın rakip", "role": "Guard", "location": "tavern"})
        other.update(current_hp=100, max_hp=100, armor_class=10, distance_ft=5, initiative_modifier=0)
        with patch("game.roll_d20", return_value=1):
            s.join_combat_participants([other["id"]])
        r = resolve(s, n, "Shortbow", rolls=(15, 8))
        self.assertIn("ranged_in_close_combat", r["disadvantage_sources"])
        other["conditions"] = ["incapacitated"]
        r = resolve(s, n, "Shortbow")
        self.assertNotIn("ranged_in_close_combat", r["disadvantage_sources"])

    def test_thrown_consumes_weapon_not_ammunition(self):
        s, n = armed("Dagger", distance=10)
        r = resolve(s, n, "Dagger", {"mode": "thrown"}, rolls=(1,))
        self.assertIsNone(r["ammunition_consumed"])
        self.assertEqual(s.world_state["inventory"], [])
        self.assertIsNone(s.world_state["equipment"]["main_hand"])
        self.assertEqual(len(s.world_state["spent_thrown_weapons"]), 1)

    def test_loading_extra_attack_cannot_bypass(self):
        s, n = armed("Light Crossbow", distance=30)
        s.character["attacks_per_action"] = 2
        with patch("game.roll_attack", return_value=1):
            step(s, {"kind": "attack", "target_id": n["id"]})
        self.assert_invalid_unchanged(s, n, "Light Crossbow", origin="continuation")
        self.assertEqual(s.world_state["ammunition"]["bolt"], 19)

    def test_loading_separate_action_grant_is_separate_origin(self):
        s, n = armed("Light Crossbow", distance=30)
        ae.grant(s, "player", "feature", ["attack"])
        with patch("game.roll_attack", return_value=1):
            step(s, {"kind": "attack", "target_id": n["id"]})
        # New Action is not an Extra Attack continuation.
        with patch("game.roll_attack", return_value=1):
            result = step(s, {"kind": "attack", "target_id": n["id"]})
        self.assertEqual(s.world_state["ammunition"]["bolt"], 18)
        self.assertEqual(result["model_calls"], 0)

    def light_setup(self, *, nick=False):
        s, n = armed("Shortsword")
        s.world_state["inventory"].append("Dagger")
        s.world_state["equipment"]["off_hand"] = "dagger"
        if nick:
            s.character["weapon_masteries"] = ["dagger"]
        with patch("game.roll_attack", return_value=10), patch.object(s.rng, "randint", return_value=3):
            step(s, {"kind": "attack", "target_id": n["id"]})
        return s, n

    def test_light_bonus_once_different_weapon_and_no_positive_modifier(self):
        s, n = self.light_setup()
        with patch("game.roll_attack", return_value=10), patch.object(s.rng, "randint", return_value=3):
            r = ae.attack_step(s, n["id"], weapon_id="dagger", origin="light")
        self.assertEqual(r["result"]["damage"], 3)
        self.assertTrue(ae.ensure(s)["player"]["bonus_action_spent"])
        self.assert_invalid_unchanged(s, n, "Dagger", origin="light")

    def test_light_rejects_same_weapon(self):
        s, n = self.light_setup()
        self.assert_invalid_unchanged(s, n, "Shortsword", origin="light")

    def test_two_different_daggers_are_light_eligible(self):
        s, n = armed("Dagger", mastery=True)
        s.world_state["inventory"] = [{"weapon_id": "dagger", "item_id": "first"},
                                      {"weapon_id": "dagger", "item_id": "second"}]
        s.world_state["equipment"] = {"main_hand": "first", "off_hand": "second"}
        resolve(s, n, "Dagger", {"weapon_instance_id": "first"})
        r = resolve(s, n, "Dagger", origin="nick")
        self.assertEqual(r["weapon_instance_id"], "second")
        self.assertEqual(r["damage"], 3)

    def test_finesse_choice_applies_same_ability_to_attack_damage(self):
        for ability, modifier in (("strength", 3), ("dexterity", 2)):
            s, n = armed("Rapier")
            r = resolve(s, n, "Rapier", {"ability": ability})
            self.assertEqual(r["attack_bonus"], modifier + 2)
            self.assertEqual(r["damage"], modifier + 3)

    def test_non_proficiency_does_not_add_pb(self):
        s, n = armed()
        s.character["weapon_proficiencies"] = []
        r = resolve(s, n)
        self.assertEqual(r["attack_bonus"], 3)
        self.assertFalse(r["proficient"])

    def test_heavy_uses_score_and_correct_melee_ranged_threshold(self):
        for weapon, score, field in (("Greatsword", 12, "strength"), ("Longbow", 12, "dexterity")):
            s, n = armed(weapon, distance=20 if weapon == "Longbow" else 5)
            s.character[field] = score
            r = resolve(s, n, weapon, rolls=(10, 15))
            self.assertIn("heavy", r["disadvantage_sources"])
            s.character[field] = 13
            r = resolve(s, n, weapon)
            self.assertNotIn("heavy", r["disadvantage_sources"])

    def test_versatile_choice_changes_die_only_melee_with_both_hands(self):
        s, n = armed("Spear")
        r = resolve(s, n, "Spear", {"grip": 2})
        self.assertEqual(r["damage_rolls"][0]["die"], 8)
        n["distance_ft"] = 20
        r = resolve(s, n, "Spear", {"grip": 2, "mode": "thrown"})
        self.assertEqual(r["damage_rolls"][0]["die"], 6)

    def test_reach_boundary_does_not_grant_all_melee_ten_feet(self):
        s, n = armed("Whip", distance=10)
        self.assertTrue(resolve(s, n, "Whip")["hit"])
        n["distance_ft"] = 10.1
        self.assert_invalid_unchanged(s, n, "Whip")
        s, n = armed(distance=5.1)
        self.assert_invalid_unchanged(s, n, "Longsword")

    def test_long_range_disadvantage_and_boundary_ammo_on_miss(self):
        s, n = armed("Shortbow", distance=320)
        r = resolve(s, n, "Shortbow", rolls=(20, 1))
        self.assertIn("long_range", r["disadvantage_sources"])
        self.assertFalse(r["hit"])
        self.assertEqual(s.world_state["ammunition"]["arrow"], 19)
        n["distance_ft"] = 320.1
        self.assert_invalid_unchanged(s, n, "Shortbow")

    def test_repeated_sources_roll_two_not_three_and_both_cancel(self):
        s, n = armed()
        s.character["attack_rules"] = {"advantage_sources": ["a", "a", "b"]}
        r = resolve(s, n, rolls=(10, 15))
        self.assertEqual(r["attack_rolls"], [10, 15])
        s.character["attack_rules"]["disadvantage_sources"] = ["c", "d"]
        r = resolve(s, n)
        self.assertEqual(r["attack_rolls"], [10])

    def test_natural_one_and_twenty_override_ac_totals(self):
        s, n = armed()
        s.character["attack_rules"] = {"attack_modifiers": [{"source": "owned", "value": 999}]}
        self.assertFalse(resolve(s, n, rolls=(1,))["hit"])
        n["armor_class"] = 10000
        self.assertTrue(resolve(s, n, rolls=(20,))["critical"])

    def test_paralyzed_unconscious_crit_only_within_five_feet(self):
        for distance, critical in ((5, True), (10, False)):
            s, n = armed("Whip", distance=distance)
            n["conditions"] = ["paralyzed"]
            self.assertEqual(resolve(s, n, "Whip", rolls=(10, 15))["critical"], critical)

    def test_mastery_can_be_declined(self):
        s, n = armed("Warhammer", mastery=True)
        r = resolve(s, n, "Warhammer", {"mastery": "none"})
        self.assertIsNone(r["mastery"])
        self.assertEqual(n["distance_ft"], 5)

    def test_owned_weapon_draw_commits_only_after_valid_attack(self):
        s, n = armed()
        s.world_state["inventory"].append("Dagger")
        r = resolve(s, n, "Dagger", {"draw": True})
        self.assertEqual(s.world_state["equipment"]["off_hand"], "dagger")
        self.assertTrue(r["hit"])

    def test_npc_equipped_weapon_uses_same_typed_damage_pipeline(self):
        s, n = armed()
        n.update(weapon_id="longsword", inventory=["Longsword"],
                 equipment={"main_hand": "longsword", "off_hand": None},
                 strength_mod=3, strength=16, proficiency_bonus=2,
                 weapon_proficiencies=["martial"], weapon_masteries=["longsword"])
        s.character["resistances"] = ["slashing"]
        s.advance_combat_turn()
        with patch("game.roll_d20", return_value=10), patch.object(s.rng, "randint", return_value=3):
            r = s.resolve_enemy_attack(n)
        self.assertEqual(r["damage"], 3)
        self.assertEqual(r["attack_bonus"], 5)
        self.assertEqual(r["mastery"], "sap")
        self.assertEqual(r["damage_instances"][0]["final_damage"], 3)

    def test_light_negative_modifier_is_retained(self):
        s, n = self.light_setup()
        s.character["strength_mod"] = -2
        r = resolve(s, n, "Dagger", origin="light", rolls=(20,))
        self.assertEqual(r["damage"], 4)

    def test_nick_not_bonus_and_not_third_attack(self):
        s, n = self.light_setup(nick=True)
        with patch("game.roll_attack", return_value=10), patch.object(s.rng, "randint", return_value=3):
            r = ae.attack_step(s, n["id"], weapon_id="dagger", origin="nick")
        self.assertEqual(r["result"]["damage"], 3)
        self.assertFalse(ae.ensure(s)["player"]["bonus_action_spent"])
        self.assert_invalid_unchanged(s, n, "Dagger", origin="nick")
        self.assert_invalid_unchanged(s, n, "Dagger", origin="light")

    def test_nick_requires_mastery_and_prior_light(self):
        s, n = armed("Dagger", mastery=True)
        self.assert_invalid_unchanged(s, n, "Dagger", origin="nick")
        s, n = self.light_setup(nick=False)
        self.assert_invalid_unchanged(s, n, "Dagger", origin="nick")

    def test_graze_no_weapon_die_or_bonuses_or_damage_increase(self):
        s, n = armed("Greatsword", mastery=True)
        n["vulnerabilities"] = ["slashing"]
        with patch("game.roll_attack", return_value=1), patch("game.roll_damage", side_effect=AssertionError("graze die")):
            r = attack.resolve(s, "player", n["id"], "Greatsword")
        self.assertFalse(r["hit"])
        self.assertEqual(r["damage"], 3)
        self.assertEqual(r["damage_rolls"], [])

    def test_graze_resistance_and_immunity(self):
        s, n = armed("Greatsword", mastery=True)
        n["resistances"] = ["slashing"]
        r = resolve(s, n, "Greatsword", rolls=(1,))
        self.assertEqual(r["damage"], 1)
        n["immunities"] = ["slashing"]
        self.assertEqual(resolve(s, n, "Greatsword", rolls=(1,))["damage"], 0)

    def test_mastery_requires_eligibility(self):
        s, n = armed()
        r = resolve(s, n)
        self.assertIsNone(r["mastery"])
        self.assert_invalid_unchanged(s, n, "Longsword", {"mastery": "sap"})

    def test_authoritative_mastery_override_and_feature_hooks(self):
        s, n = armed("Longsword", mastery=True)
        observed = []
        s.register_attack_hook("attack_rules", lambda *_: {"source": "feature", "mastery_overrides": ["slow"]})
        s.register_attack_hook("after_attack", lambda _, r: observed.append(("attack", r["hit"])))
        s.register_attack_hook("after_damage", lambda _, r: observed.append(("damage", r["damage"])))
        s.register_attack_hook("after_mastery", lambda _, r: observed.append(("mastery", r["mastery"])))
        r = resolve(s, n, choice={"mastery": "slow"})
        self.assertEqual(r["mastery"], "slow")
        self.assertEqual([v[0] for v in observed], ["attack", "damage", "mastery"])
        self.assertEqual(attack.slow_penalty(s, n["id"]), 10)

    def test_sap_consumed_by_next_attack_not_save(self):
        s, n = armed(mastery=True)
        resolve(s, n)
        with patch("game.roll_d20", return_value=15):
            attack.save(s, n["id"], ("constitution",), 12)
        self.assertEqual(len(s.world_state["attack_effects"]), 1)
        s.advance_combat_turn()
        with patch("game.roll_d20", side_effect=[10, 5]):
            r = s.resolve_enemy_attack(n)
        self.assertIn("sap", r["disadvantage_sources"])
        self.assertEqual(s.world_state["attack_effects"], [])

    def test_sap_slow_expire_at_source_next_start(self):
        for weapon in ("Longsword", "Whip"):
            s, n = armed(weapon, mastery=True)
            resolve(s, n, weapon)
            s.advance_combat_turn()
            self.assertTrue(s.world_state["attack_effects"])
            s.advance_combat_turn()
            self.assertEqual(s.world_state["attack_effects"], [])

    def test_slow_not_stacked_and_zero_damage_does_not_trigger(self):
        s, n = armed("Whip", mastery=True)
        resolve(s, n, "Whip")
        resolve(s, n, "Whip")
        n["speed_ft"] = 30
        self.assertEqual(ae.speed(s, n["id"]), 20)
        n["immunities"] = ["slashing"]
        s.world_state["attack_effects"] = []
        resolve(s, n, "Whip")
        self.assertEqual(attack.slow_penalty(s, n["id"]), 0)

    def test_vex_same_target_next_attack_consumed_and_regranted(self):
        s, n = armed("Rapier", mastery=True)
        resolve(s, n, "Rapier")
        r = resolve(s, n, "Rapier", rolls=(3, 18))
        self.assertIn("vex", r["advantage_sources"])
        self.assertTrue(r["hit"])
        r = resolve(s, n, "Rapier", rolls=(1, 1))
        self.assertFalse(r["hit"])
        self.assertEqual(s.world_state["attack_effects"], [])

    def test_vex_expires_at_end_of_next_source_turn(self):
        s, n = armed("Rapier", mastery=True)
        resolve(s, n, "Rapier")
        s.advance_combat_turn()
        s.advance_combat_turn()
        self.assertTrue(s.world_state["attack_effects"])
        s.advance_combat_turn()
        self.assertEqual(s.world_state["attack_effects"], [])

    def test_topple_dc_constitution_and_success_failure(self):
        for die, prone in ((1, True), (20, False)):
            s, n = armed("Battleaxe", mastery=True)
            with patch("game.roll_attack", return_value=10), patch("game.roll_d20", return_value=die), patch.object(s.rng, "randint", return_value=3):
                r = attack.resolve(s, "player", n["id"], "Battleaxe")
            saving = r["mastery_effect"]["save"]
            self.assertEqual(saving["dc"], 13)
            self.assertEqual(saving["ability"], "constitution")
            self.assertEqual(bool(n.get("prone")), prone)

    def test_push_authoritative_corridor_only_and_size(self):
        for size, corridor, applied in (("medium", 10, True), ("huge", 10, False), ("large", 5, False)):
            s, n = armed("Warhammer", mastery=True)
            n["size"] = size
            s.world_state["attack_environment"] = {"pairs": {
                f"player|{n['id']}": {"distance_ft": 5, "push_clear_ft": corridor}}}
            r = resolve(s, n, "Warhammer", rolls=(20,))
            self.assertEqual(r["mastery_effect"]["applied"], applied)
            self.assertEqual(n["distance_ft"], 15 if applied else 5)
            if applied:
                self.assertEqual(r["mastery_effect"]["distance_ft"], 10)

    def test_push_uses_only_forward_corridor_and_invalidates_target_geometry(self):
        cases = (
            ("blocked", {"distance_ft": 5, "push_clear_ft": 0}, 20, False),
            ("too_short", {"distance_ft": 5, "push_clear_ft": 5}, 20, False),
            ("missing_corridor", {"distance_ft": 5}, 20, False),
            ("reverse_only", None, 20, False),
            ("clear_exactly", {"distance_ft": 5, "push_clear_ft": 10}, 0, True),
            ("clear_longer", {"distance_ft": 5, "push_clear_ft": 20}, 5, True),
        )
        for name, forward, reverse_clear, applied in cases:
            with self.subTest(case=name):
                s, n = armed("Warhammer", mastery=True)
                other = s.create_npc_from_ai({
                    "name": "Bystander", "role": "Guard", "location": "tavern"})
                other["distance_ft"] = 30
                forward_key = f"player|{n['id']}"
                pairs = {
                    f"{n['id']}|player": {
                        "distance_ft": 5, "push_clear_ft": reverse_clear},
                    f"{n['id']}|{other['id']}": {"distance_ft": 25},
                    f"{other['id']}|{n['id']}": {"distance_ft": 25},
                    f"player|{other['id']}": {"distance_ft": 30},
                    f"{other['id']}|player": {"distance_ft": 30},
                }
                if forward is not None:
                    pairs[forward_key] = copy.deepcopy(forward)
                else:
                    # Force distance to come from the reverse pair, but never
                    # borrow its directional corridor to authorize this push.
                    del n["distance_ft"]
                s.world_state["attack_environment"] = {"pairs": pairs}
                if forward is None:
                    self.assertEqual(attack.pair(s, "player", n["id"]),
                                     {"distance_ft": 5})
                geometry_before = copy.deepcopy(s.world_state["attack_environment"])
                target_distance_before = {
                    k: n[k] for k in ("distance_ft",) if k in n}
                # No fixture supplies coordinates or a destination.
                position_keys = ("position", "position_ft", "coordinates", "x", "y", "z")
                positions_before = copy.deepcopy([
                    {k: data[k] for k in position_keys if k in data}
                    for data in (s.character, n, other)])

                r = resolve(s, n, "Warhammer", rolls=(20,))
                self.assertTrue(r["hit"])
                expected_effect = (
                    {"kind": "push", "applied": True, "distance_ft": 10,
                     "resulting_distance_ft": 15} if applied else
                    {"kind": "push", "applied": False,
                     "reason": "position_unresolved_or_blocked"})
                self.assertEqual(r["mastery_effect"], expected_effect)
                self.assertEqual(r["resulting_position"], expected_effect)
                if applied:
                    expected_pairs = {
                        key: value for key, value in geometry_before["pairs"].items()
                        if n["id"] not in key.split("|")}
                    expected_pairs[forward_key] = {
                        **forward, "distance_ft": 15,
                        "push_clear_ft": forward["push_clear_ft"] - 10}
                    self.assertEqual(s.world_state["attack_environment"],
                                     {"pairs": expected_pairs})
                    self.assertEqual(n["distance_ft"], 15)
                    # Symmetric distance may be reused; the new forward
                    # corridor must not become a reverse push permission.
                    self.assertEqual(attack.pair(s, n["id"], "player"),
                                     {"distance_ft": 15})
                    if name == "clear_longer":
                        live_pairs = s.world_state["attack_environment"]["pairs"]
                        self.assertGreaterEqual(live_pairs[forward_key]["push_clear_ft"], 10)
                        reverse_before = copy.deepcopy((
                            s.world_state, s.character, s.messages, s.rng.getstate()))
                        unrelated_before = copy.deepcopy({
                            key: value for key, value in live_pairs.items()
                            if n["id"] not in key.split("|")})
                        mirrors_before = (n["distance_ft"], other["distance_ft"])
                        self.assertEqual(attack.push(s, n["id"], "player", 10), {
                            "kind": "push", "applied": False,
                            "reason": "position_unresolved_or_blocked"})
                        self.assertEqual((
                            s.world_state, s.character, s.messages, s.rng.getstate()),
                            reverse_before)
                        self.assertEqual({
                            key: value for key, value in
                            s.world_state["attack_environment"]["pairs"].items()
                            if n["id"] not in key.split("|")}, unrelated_before)
                        self.assertEqual((n["distance_ft"], other["distance_ft"]),
                                         mirrors_before)
                else:
                    self.assertEqual(s.world_state["attack_environment"], geometry_before)
                    self.assertEqual({k: n[k] for k in ("distance_ft",) if k in n},
                                     target_distance_before)
                self.assertEqual(other["distance_ft"], 30)
                self.assertEqual([
                    {k: data[k] for k in position_keys if k in data}
                    for data in (s.character, n, other)], positions_before)

    def test_npc_push_player_uses_forward_corridor_and_actor_distance_mirror(self):
        cases = (
            ("blocked", {"distance_ft": 5, "push_clear_ft": 0}, 20, False),
            ("too_short", {"distance_ft": 5, "push_clear_ft": 5}, 20, False),
            ("missing_corridor", {"distance_ft": 5}, 20, False),
            ("reverse_only", None, 20, False),
            ("clear_exactly", {"distance_ft": 5, "push_clear_ft": 10}, 0, True),
            ("clear_longer", {"distance_ft": 5, "push_clear_ft": 20}, 5, True),
        )
        for name, forward, reverse_clear, applied in cases:
            with self.subTest(case=name):
                s, n = armed("Warhammer", mastery=True)
                other = s.create_npc_from_ai({
                    "name": "Bystander", "role": "Guard", "location": "tavern"})
                other["distance_ft"] = 30
                forward_key = f"{n['id']}|player"
                pairs = {
                    f"player|{n['id']}": {
                        "distance_ft": 5, "push_clear_ft": reverse_clear},
                    f"player|{other['id']}": {
                        "distance_ft": 30, "push_clear_ft": 20},
                    f"{other['id']}|player": {
                        "distance_ft": 30, "push_clear_ft": 0},
                    f"{n['id']}|{other['id']}": {
                        "distance_ft": 25, "push_clear_ft": 10},
                    f"{other['id']}|{n['id']}": {
                        "distance_ft": 25, "push_clear_ft": 0},
                }
                if forward is not None:
                    pairs[forward_key] = copy.deepcopy(forward)
                else:
                    # Only symmetric distance may come from the reverse pair.
                    del n["distance_ft"]
                    self.assertNotIn(forward_key, pairs)
                s.world_state["attack_environment"] = {"pairs": pairs}
                if forward is None:
                    self.assertEqual(attack.pair(s, n["id"], "player"),
                                     {"distance_ft": 5})
                expected_world = copy.deepcopy(s.world_state)
                unchanged = copy.deepcopy((s.character, s.messages, s.rng.getstate()))
                actor_distance_before = {
                    k: n[k] for k in ("distance_ft",) if k in n}
                # No destination coordinates are supplied or justified.
                position_keys = ("position", "position_ft", "coordinates", "x", "y", "z")
                positions_before = copy.deepcopy([
                    {k: data[k] for k in position_keys if k in data}
                    for data in (s.character, n, other)])

                result = attack.push(s, n["id"], "player", 10)

                expected_effect = (
                    {"kind": "push", "applied": True, "distance_ft": 10,
                     "resulting_distance_ft": 15} if applied else
                    {"kind": "push", "applied": False,
                     "reason": "position_unresolved_or_blocked"})
                self.assertEqual(result, expected_effect)
                if applied:
                    expected_pairs = {
                        key: value for key, value in
                        expected_world["attack_environment"]["pairs"].items()
                        if "player" not in key.split("|")}
                    expected_pairs[forward_key] = {
                        **forward, "distance_ft": 15,
                        "push_clear_ft": forward["push_clear_ft"] - 10}
                    expected_world["attack_environment"]["pairs"] = expected_pairs
                    expected_actor = next(
                        npc for npc in expected_world["npcs"] if npc["id"] == n["id"])
                    expected_actor["distance_ft"] = 15
                    self.assertEqual(n["distance_ft"], 15)
                    self.assertEqual(attack.pair(s, "player", n["id"]),
                                     {"distance_ft": 15})
                    if name == "clear_longer":
                        live_pairs = s.world_state["attack_environment"]["pairs"]
                        self.assertGreaterEqual(live_pairs[forward_key]["push_clear_ft"], 10)
                        reverse_before = copy.deepcopy((
                            s.world_state, s.character, s.messages, s.rng.getstate()))
                        unrelated_before = copy.deepcopy({
                            key: value for key, value in live_pairs.items()
                            if "player" not in key.split("|")})
                        mirrors_before = (n["distance_ft"], other["distance_ft"])
                        self.assertEqual(attack.push(s, "player", n["id"], 10), {
                            "kind": "push", "applied": False,
                            "reason": "position_unresolved_or_blocked"})
                        self.assertEqual((
                            s.world_state, s.character, s.messages, s.rng.getstate()),
                            reverse_before)
                        self.assertEqual({
                            key: value for key, value in
                            s.world_state["attack_environment"]["pairs"].items()
                            if "player" not in key.split("|")}, unrelated_before)
                        self.assertEqual((n["distance_ft"], other["distance_ft"]),
                                         mirrors_before)
                else:
                    self.assertEqual({k: n[k] for k in ("distance_ft",) if k in n},
                                     actor_distance_before)
                # Includes exact pair invalidation, unrelated NPC-to-NPC
                # geometry, and every other canonical world field.
                self.assertEqual(s.world_state, expected_world)
                self.assertEqual((s.character, s.messages, s.rng.getstate()), unchanged)
                self.assertEqual(other["distance_ft"], 30)
                self.assertEqual([
                    {k: data[k] for k in position_keys if k in data}
                    for data in (s.character, n, other)], positions_before)

    def test_npc_push_npc_uses_forward_corridor_and_preserves_player_mirrors(self):
        cases = (
            ("blocked", {"distance_ft": 5, "push_clear_ft": 0}, 20, False),
            ("too_short", {"distance_ft": 5, "push_clear_ft": 5}, 20, False),
            ("missing_corridor", {"distance_ft": 5}, 20, False),
            ("reverse_only", None, 20, False),
            ("clear_exactly", {"distance_ft": 5, "push_clear_ft": 10}, 0, True),
            ("clear_longer", {"distance_ft": 5, "push_clear_ft": 20}, 5, True),
        )
        for name, forward, reverse_clear, applied in cases:
            with self.subTest(case=name):
                s, actor = armed("Warhammer", mastery=True)
                actor["distance_ft"] = 40
                target = s.create_npc_from_ai({
                    "name": "Push target", "role": "Guard", "location": "tavern"})
                target.update(size="medium", distance_ft=35)
                other = s.create_npc_from_ai({
                    "name": "Bystander", "role": "Guard", "location": "tavern"})
                other["distance_ft"] = 30
                forward_key = f"{actor['id']}|{target['id']}"
                pairs = {
                    f"{target['id']}|{actor['id']}": {
                        "distance_ft": 5, "push_clear_ft": reverse_clear},
                    f"player|{target['id']}": {
                        "distance_ft": 35, "push_clear_ft": 20},
                    f"{target['id']}|player": {
                        "distance_ft": 35, "push_clear_ft": 0},
                    f"{target['id']}|{other['id']}": {
                        "distance_ft": 25, "push_clear_ft": 10},
                    f"{other['id']}|{target['id']}": {
                        "distance_ft": 25, "push_clear_ft": 0},
                    f"player|{actor['id']}": {
                        "distance_ft": 40, "push_clear_ft": 20},
                    f"{actor['id']}|player": {
                        "distance_ft": 40, "push_clear_ft": 0},
                    f"player|{other['id']}": {"distance_ft": 30},
                    f"{other['id']}|player": {"distance_ft": 30},
                    f"{actor['id']}|{other['id']}": {"distance_ft": 15},
                    f"{other['id']}|{actor['id']}": {"distance_ft": 15},
                }
                if forward is not None:
                    pairs[forward_key] = copy.deepcopy(forward)
                s.world_state["attack_environment"] = {"pairs": pairs}
                if forward is None:
                    self.assertNotIn(forward_key, pairs)
                    # Symmetric NPC distance is valid, but the reverse corridor
                    # and either NPC's player-distance mirror cannot authorize a push.
                    self.assertEqual(attack.pair(s, actor["id"], target["id"]),
                                     {"distance_ft": 5})
                expected_world = copy.deepcopy(s.world_state)
                unchanged = copy.deepcopy((s.character, s.messages, s.rng.getstate()))
                mirrors_before = [npc["distance_ft"] for npc in (actor, target, other)]
                position_keys = ("position", "position_ft", "coordinates", "x", "y", "z")
                positions_before = copy.deepcopy([
                    {k: data[k] for k in position_keys if k in data}
                    for data in (s.character, actor, target, other)])

                result = attack.push(s, actor["id"], target["id"], 10)

                expected_effect = (
                    {"kind": "push", "applied": True, "distance_ft": 10,
                     "resulting_distance_ft": 15} if applied else
                    {"kind": "push", "applied": False,
                     "reason": "position_unresolved_or_blocked"})
                self.assertEqual(result, expected_effect)
                if applied:
                    expected_pairs = expected_world["attack_environment"]["pairs"]
                    for key in (
                        forward_key, f"{target['id']}|{actor['id']}",
                        f"player|{target['id']}", f"{target['id']}|player",
                        f"{target['id']}|{other['id']}", f"{other['id']}|{target['id']}",
                    ):
                        del expected_pairs[key]
                    expected_pairs[forward_key] = {
                        **forward, "distance_ft": 15,
                        "push_clear_ft": forward["push_clear_ft"] - 10}
                    self.assertEqual(attack.pair(s, target["id"], actor["id"]),
                                     {"distance_ft": 15})
                # Only target-containing pairs change. Unrelated pairs, NPC
                # player-distance mirrors, and all other world fields survive.
                self.assertEqual(s.world_state, expected_world)
                self.assertEqual((s.character, s.messages, s.rng.getstate()), unchanged)
                self.assertEqual([npc["distance_ft"] for npc in (actor, target, other)],
                                 mirrors_before)
                # The corridor proves separation, not destination coordinates.
                self.assertEqual([
                    {k: data[k] for k in position_keys if k in data}
                    for data in (s.character, actor, target, other)], positions_before)

    def test_sequential_npc_pushes_consume_corridor_without_partial_movement(self):
        for corridor in (20, 25):
            with self.subTest(initial_corridor_ft=corridor):
                s, actor = armed("Warhammer", mastery=True)
                actor["distance_ft"] = 40
                target = s.create_npc_from_ai({
                    "name": "Push target", "role": "Guard", "location": "tavern"})
                target.update(size="medium", distance_ft=35)
                other = s.create_npc_from_ai({
                    "name": "Bystander", "role": "Guard", "location": "tavern"})
                other["distance_ft"] = 30
                forward_key = f"{actor['id']}|{target['id']}"
                s.world_state["attack_environment"] = {"pairs": {
                    forward_key: {"distance_ft": 5, "push_clear_ft": corridor},
                    f"{target['id']}|{actor['id']}": {
                        "distance_ft": 5, "push_clear_ft": 50},
                    f"player|{target['id']}": {"distance_ft": 35},
                    f"{target['id']}|player": {"distance_ft": 35},
                    f"{target['id']}|{other['id']}": {"distance_ft": 25},
                    f"{other['id']}|{target['id']}": {"distance_ft": 25},
                    f"player|{actor['id']}": {"distance_ft": 40},
                    f"{actor['id']}|player": {"distance_ft": 40},
                    f"player|{other['id']}": {"distance_ft": 30},
                    f"{other['id']}|player": {"distance_ft": 30},
                    f"{actor['id']}|{other['id']}": {"distance_ft": 15},
                    f"{other['id']}|{actor['id']}": {"distance_ft": 15},
                }}
                expected_world = copy.deepcopy(s.world_state)
                unchanged = copy.deepcopy((s.character, s.messages, s.rng.getstate()))
                mirrors_before = [npc["distance_ft"] for npc in (actor, target, other)]
                position_keys = ("position", "position_ft", "coordinates", "x", "y", "z")
                positions_before = copy.deepcopy([
                    {k: data[k] for k in position_keys if k in data}
                    for data in (s.character, actor, target, other)])

                for push_number in (1, 2, 3):
                    with self.subTest(push_number=push_number):
                        before = copy.deepcopy((
                            s.world_state, s.character, s.messages, s.rng.getstate()))
                        result = attack.push(s, actor["id"], target["id"], 10)
                        if push_number <= 2:
                            separation = 5 + 10 * push_number
                            self.assertEqual(result, {
                                "kind": "push", "applied": True, "distance_ft": 10,
                                "resulting_distance_ft": separation})
                            expected_pairs = expected_world["attack_environment"]["pairs"]
                            for key in list(expected_pairs):
                                if target["id"] in key.split("|"):
                                    del expected_pairs[key]
                            expected_pairs[forward_key] = {
                                "distance_ft": separation,
                                "push_clear_ft": corridor - 10 * push_number}
                            self.assertEqual(
                                attack.pair(s, target["id"], actor["id"]),
                                {"distance_ft": separation})
                            if push_number == 1:
                                # Enough forward corridor remains for another
                                # push, but it cannot authorize the reverse one.
                                live_pairs = s.world_state["attack_environment"]["pairs"]
                                self.assertGreaterEqual(
                                    live_pairs[forward_key]["push_clear_ft"], 10)
                                self.assertNotIn(
                                    f"{target['id']}|{actor['id']}", live_pairs)
                                reverse_before = copy.deepcopy((
                                    s.world_state, s.character, s.messages,
                                    s.rng.getstate()))
                                unrelated_before = copy.deepcopy({
                                    key: value for key, value in live_pairs.items()
                                    if target["id"] not in key.split("|")})
                                reverse_result = attack.push(
                                    s, target["id"], actor["id"], 10)
                                self.assertEqual(reverse_result, {
                                    "kind": "push", "applied": False,
                                    "reason": "position_unresolved_or_blocked"})
                                self.assertEqual((
                                    s.world_state, s.character, s.messages,
                                    s.rng.getstate()), reverse_before)
                                self.assertEqual({
                                    key: value for key, value in
                                    s.world_state["attack_environment"]["pairs"].items()
                                    if target["id"] not in key.split("|")},
                                    unrelated_before)
                                self.assertEqual(
                                    [npc["distance_ft"] for npc in (actor, target, other)],
                                    mirrors_before)
                        else:
                            # Zero or five feet left cannot fund another ten-foot
                            # push, even partly. Rejection must be a pure no-op.
                            self.assertEqual(result, {
                                "kind": "push", "applied": False,
                                "reason": "position_unresolved_or_blocked"})
                            self.assertEqual((
                                s.world_state, s.character, s.messages, s.rng.getstate()),
                                before)
                        self.assertEqual(s.world_state, expected_world)
                        self.assertEqual(
                            (s.character, s.messages, s.rng.getstate()), unchanged)
                        self.assertEqual(
                            [npc["distance_ft"] for npc in (actor, target, other)],
                            mirrors_before)
                        self.assertEqual([
                            {k: data[k] for k in position_keys if k in data}
                            for data in (s.character, actor, target, other)],
                            positions_before)

    def test_push_unresolved_does_not_invent_position(self):
        s, n = armed("Warhammer", mastery=True)
        r = resolve(s, n, "Warhammer")
        self.assertFalse(r["mastery_effect"]["applied"])
        self.assertEqual(n["distance_ft"], 5)

    def test_cleave_second_roll_once_and_damage_modifier_excluded(self):
        s, n = armed("Greataxe", mastery=True)
        other = s.create_npc_from_ai({"name": "Second", "role": "Guard", "location": "tavern"})
        other.update(current_hp=100, max_hp=100, armor_class=10, distance_ft=5, initiative_modifier=0)
        with patch("game.roll_d20", return_value=1):
            s.join_combat_participants([other["id"]])
        s.world_state["attack_environment"] = {"pairs": {f"{n['id']}|{other['id']}": {"distance_ft": 5}}}
        r = resolve(s, n, "Greataxe", {"cleave_target_id": other["id"]}, rolls=(10, 10))
        self.assertEqual(r["cleave_attack"]["damage"], 3)
        self.assertNotEqual(r["resolution_id"], r["cleave_attack"]["resolution_id"])
        self.assert_invalid_unchanged(s, n, "Greataxe", {"cleave_target_id": other["id"]})

    def test_cleave_invalid_second_target_rejects_before_first_roll(self):
        s, n = armed("Greataxe", mastery=True)
        self.assert_invalid_unchanged(s, n, "Greataxe", {"cleave_target_id": "foreign"})

    def test_unarmed_damage_not_weapon_and_critical_no_fake_die(self):
        s, n = armed()
        r = resolve(s, n, "unarmed", rolls=(20,))
        self.assertEqual(r["damage"], 4)
        self.assertEqual(r["damage_type"], "bludgeoning")
        self.assertEqual(r["damage_rolls"], [])
        self.assertIsNone(r["mastery"])

    def test_unarmed_grapple_shove_save_and_conditions(self):
        for option, condition in (("grapple", "grappled"), ("shove", "prone")):
            s, n = armed()
            with patch("game.roll_d20", return_value=1), patch("game.roll_attack", side_effect=AssertionError("not attack roll")):
                r = attack.resolve(s, "player", n["id"], "unarmed", {"unarmed_option": option})
            self.assertEqual(r["resolution"]["dc"], 13)
            self.assertIn(condition, n["conditions"])
            self.assertEqual(r["damage"], 0)

    def test_unarmed_save_choice_and_success(self):
        s, n = armed()
        n["dexterity_mod"] = 5
        with patch("game.roll_d20", return_value=10):
            r = attack.resolve(s, "player", n["id"], "unarmed", {"unarmed_option": "grapple"})
        self.assertFalse(r["hit"])
        self.assertEqual(r["resolution"]["ability"], "dexterity")
        self.assertNotIn("grappled", n.get("conditions", []))

    def test_unarmed_size_and_free_hand(self):
        s, n = armed()
        n["size"] = "huge"
        self.assert_invalid_unchanged(s, n, "unarmed", {"unarmed_option": "grapple"})
        self.assert_invalid_unchanged(s, n, "unarmed", {"unarmed_option": "shove"})
        n["size"] = "medium"
        s.world_state["equipment"]["off_hand"] = "shield"
        self.assert_invalid_unchanged(s, n, "unarmed", {"unarmed_option": "grapple"})

    def test_grapple_occupies_one_hand_and_records_escape_dc(self):
        s, n = armed()
        with patch("game.roll_d20", return_value=1):
            attack.resolve(s, "player", n["id"], "unarmed", {"unarmed_option": "grapple"})
        self.assertEqual(n["grapple_escape_dc"], 13)
        self.assertEqual(s.world_state["equipment"]["off_hand"], f"grapple:{n['id']}")
        self.assert_invalid_unchanged(s, n, "unarmed", {"unarmed_option": "grapple"})

    def test_nonfinite_distance_is_not_authoritative(self):
        for distance in (float("nan"), float("inf")):
            s, n = armed()
            n["distance_ft"] = distance
            # NaN is unequal to itself; compare explicit state identities/RNG.
            before = s.rng.getstate()
            with self.assertRaises(CombatRequestError):
                attack.resolve(s, "player", n["id"], "Longsword")
            self.assertEqual(s.rng.getstate(), before)

    def assert_invalid_reverse_distance_unchanged(self, reverse_pair):
        s, n = armed("Shortbow")
        del n["distance_ft"]
        pairs = {f"{n['id']}|player": reverse_pair}
        s.world_state["attack_environment"] = {"pairs": pairs}
        self.assertNotIn(f"player|{n['id']}", pairs)
        self.assertNotIn("distance_ft", n)
        self.assert_unknown_distance_unchanged(s, n)

    def assert_invalid_forward_distance_unchanged(self, forward_pair):
        s, n = armed("Shortbow")
        del n["distance_ft"]
        pairs = {
            f"player|{n['id']}": forward_pair,
            f"{n['id']}|player": {"distance_ft": 30},
        }
        s.world_state["attack_environment"] = {"pairs": pairs}
        self.assertIn(f"player|{n['id']}", pairs)
        self.assertEqual(pairs[f"player|{n['id']}"], forward_pair)
        self.assertEqual(pairs[f"{n['id']}|player"]["distance_ft"], 30)
        self.assertNotIn("distance_ft", n)
        self.assert_unknown_distance_unchanged(s, n)

    def assert_unknown_distance_unchanged(self, s, n, *, npc_origin=False):
        self.assertNotIn("attack_results", s.world_state)

        def snapshot(session):
            # Include the complete save, unsanitized character, messages and RNG.
            # JSON preserves nonfinite fixture values without NaN equality issues.
            return json.dumps((
                session.serialize_game_state(), session.world_state, session.character,
                session.messages, session.rng.getstate(),
            ), sort_keys=True)

        before = snapshot(s)
        npc_before = json.dumps(n, sort_keys=True)
        default_before = snapshot(game._DEFAULT_SESSION)
        with patch("game.roll_attack",
                   side_effect=AssertionError("Rejected attack rolled")) as attack_roll, \
             patch("game.roll_damage",
                   side_effect=AssertionError("Rejected attack rolled damage")) as damage_roll, \
             patch.object(s.rng, "randint",
                          side_effect=AssertionError("Rejected attack consumed dice")) as dice, \
             patch.object(game._DEFAULT_SESSION.rng, "randint",
                          side_effect=AssertionError("Rejected attack used default dice")) as default_dice:
            with self.assertRaises(CombatRequestError) as raised:
                if npc_origin:
                    s.resolve_enemy_attack(n)
                else:
                    attack.resolve(s, "player", n["id"], "Shortbow")
            self.assertEqual(raised.exception.code, "distance_unknown")
            attack_roll.assert_not_called()
            damage_roll.assert_not_called()
            dice.assert_not_called()
            default_dice.assert_not_called()

        self.assertNotIn("attack_results", s.world_state)
        self.assertEqual(snapshot(s), before)
        self.assertEqual(json.dumps(n, sort_keys=True), npc_before)
        self.assertEqual(snapshot(game._DEFAULT_SESSION), default_before)

    def test_npc_invalid_authored_pair_distance_not_replaced_by_valid_fallback(self):
        invalid_distances = (
            None, False, True, -1, float("nan"), float("inf"), float("-inf"),
            "30", "30.0", [], [30], {}, {"distance_ft": 30},
        )
        for direction in ("forward_only", "forward_with_valid_reverse", "reverse_only"):
            for distance in invalid_distances:
                with self.subTest(direction=direction, distance=distance):
                    s, n = armed("Shortbow", distance=30)
                    n.update(weapon_id="shortbow", inventory=["Shortbow"],
                             equipment={"main_hand": "shortbow", "off_hand": None},
                             dexterity=14, dexterity_mod=2, proficiency_bonus=2,
                             weapon_proficiencies=["simple"], weapon_masteries=[],
                             ammunition={"arrow": 20})
                    s.character["armor_class"] = 12
                    forward_key = f"{n['id']}|player"
                    reverse_key = f"player|{n['id']}"
                    invalid_key = reverse_key if direction == "reverse_only" else forward_key
                    pairs = {invalid_key: {
                        "distance_ft": distance, "cover": "half",
                        "attacker_sees_target": False, "target_sees_attacker": True,
                    }}
                    if direction == "forward_with_valid_reverse":
                        pairs[reverse_key] = {"distance_ft": 30}
                    else:
                        self.assertNotIn(
                            forward_key if direction == "reverse_only" else reverse_key, pairs)
                    s.world_state["attack_environment"] = {"pairs": pairs}
                    self.assertIn("distance_ft", pairs[invalid_key])
                    self.assertEqual(n["distance_ft"], 30)
                    s.advance_combat_turn()
                    self.assertEqual(s.world_state["combat"]["current_actor_id"], n["id"])
                    # Use the real enemy entry point and equipped weapon resolver.
                    # A supplied invalid value must never become NPC/reverse fallback.
                    self.assert_unknown_distance_unchanged(s, n, npc_origin=True)

    def assert_invalid_canonical_npc_distance_unchanged(self, distance, *, missing=False):
        for geometry in ("no_environment", "empty_pairs", "forward_only", "reverse_only"):
            for attack_source in ("equipped_weapon", "stat_block"):
                with self.subTest(geometry=geometry, attack_source=attack_source):
                    s, n = armed("Shortbow", distance=distance)
                    if missing:
                        del n["distance_ft"]
                    if attack_source == "equipped_weapon":
                        n.update(weapon_id="shortbow", inventory=["Shortbow"],
                                 equipment={"main_hand": "shortbow", "off_hand": None},
                                 dexterity=14, dexterity_mod=2, proficiency_bonus=2,
                                 weapon_proficiencies=["simple"], weapon_masteries=[],
                                 ammunition={"arrow": 20})
                    else:
                        self.assertNotIn("weapon_id", n)
                    s.character["armor_class"] = 12
                    s.world_state.pop("attack_environment", None)
                    pairs = {}
                    if geometry in ("forward_only", "reverse_only"):
                        key = (f"{n['id']}|player" if geometry == "forward_only"
                               else f"player|{n['id']}")
                        pairs[key] = {"cover": "half", "attacker_sees_target": False,
                                      "target_sees_attacker": True}
                    if geometry != "no_environment":
                        s.world_state["attack_environment"] = {"pairs": pairs}
                    # No authored distance can mask the canonical NPC fallback.
                    for authored_pair in pairs.values():
                        self.assertNotIn("distance_ft", authored_pair)
                    if missing:
                        self.assertNotIn("distance_ft", n)
                    else:
                        self.assertIn("distance_ft", n)
                    s.advance_combat_turn()
                    self.assertEqual(s.world_state["combat"]["current_actor_id"], n["id"])
                    self.assert_unknown_distance_unchanged(s, n, npc_origin=True)

    def test_npc_invalid_canonical_distance_rejected_without_authored_distance(self):
        invalid_distances = (
            None, False, True, -1, float("nan"), float("inf"), float("-inf"),
            "30", "30.0", [], [30], {}, {"distance_ft": 30},
        )
        for distance in invalid_distances:
            with self.subTest(distance=distance):
                self.assert_invalid_canonical_npc_distance_unchanged(distance)

    def test_npc_absent_canonical_distance_rejected_without_authored_distance(self):
        self.assert_invalid_canonical_npc_distance_unchanged(None, missing=True)

    def assert_npc_authored_distance_overrides_broken_canonical(self, distance, *, missing=False):
        for reverse_only in (False, True):
            for attack_source in ("equipped_weapon", "stat_block"):
                with self.subTest(reverse_only=reverse_only, attack_source=attack_source):
                    s, n = armed("Shortbow", distance=distance)
                    if missing:
                        del n["distance_ft"]
                    if attack_source == "equipped_weapon":
                        n.update(weapon_id="shortbow", inventory=["Shortbow"],
                                 equipment={"main_hand": "shortbow", "off_hand": None},
                                 dexterity=14, dexterity_mod=2, proficiency_bonus=2,
                                 weapon_proficiencies=["simple"], weapon_masteries=[],
                                 ammunition={"arrow": 20})
                    else:
                        self.assertNotIn("weapon_id", n)
                        n.update(attack_bonus=4, damage_die=6, damage_dice=1,
                                 damage_modifier=2, attack_damage_type="piercing",
                                 ammunition={"arrow": 20})
                    s.character["armor_class"] = 12
                    # Stat-block attacks are melee; the bow uses normal range.
                    authored_pair = {
                        "distance_ft": 30 if attack_source == "equipped_weapon" else 5,
                        "cover": "half", "attacker_sees_target": False,
                        "target_sees_attacker": True,
                    }
                    forward_key, reverse_key = f"{n['id']}|player", f"player|{n['id']}"
                    key = reverse_key if reverse_only else forward_key
                    pairs = {key: authored_pair}
                    s.world_state["attack_environment"] = {"pairs": pairs}
                    geometry_before = copy.deepcopy(s.world_state["attack_environment"])
                    canonical_before = json.dumps(
                        {"distance_ft": n["distance_ft"]} if "distance_ft" in n else {},
                        sort_keys=True)
                    player_ammunition_before = copy.deepcopy(s.world_state["ammunition"])
                    self.assertNotIn(forward_key if reverse_only else reverse_key, pairs)
                    self.assertEqual(
                        attack.pair(s, n["id"], "player"),
                        {"distance_ft": authored_pair["distance_ft"]} if reverse_only
                        else authored_pair)
                    s.advance_combat_turn()
                    self.assertEqual(s.world_state["combat"]["current_actor_id"], n["id"])
                    self.assertNotIn("attack_results", s.world_state)

                    def snapshot(session):
                        # JSON compares NaN-bearing state without NaN equality pitfalls.
                        return json.dumps((
                            session.serialize_game_state(), session.world_state,
                            session.character, session.messages, session.rng.getstate(),
                        ), sort_keys=True)

                    default_before = snapshot(game._DEFAULT_SESSION)
                    attack_rolls = [10] if reverse_only else [10, 12]
                    remaining = iter([(20, value) for value in attack_rolls] + [(6, 4)])

                    def owned_randint(low, high):
                        self.assertIs(game._session(), s)
                        expected = next(remaining, None)
                        self.assertIsNotNone(expected, "Unexpected attack or damage die")
                        sides, value = expected
                        self.assertEqual((low, high), (1, sides))
                        return value

                    # Keep both real roll owners; script only the explicit session's RNG.
                    with patch.object(s.rng, "randint", side_effect=owned_randint) as dice, \
                         patch.object(game._DEFAULT_SESSION.rng, "randint",
                                      side_effect=AssertionError("Enemy used default dice")) as default_dice:
                        result = s.resolve_enemy_attack(n)
                        self.assertEqual(dice.call_args_list,
                                         [call(1, 20)] * len(attack_rolls) + [call(1, 6)])
                        self.assertIsNone(next(remaining, None), "Expected dice were not consumed")
                        default_dice.assert_not_called()

                    self.assertEqual(result["actor_id"], n["id"])
                    self.assertEqual(result["target_id"], "player")
                    self.assertEqual(result["weapon_id"],
                                     "shortbow" if attack_source == "equipped_weapon"
                                     else "stat_block_attack")
                    self.assertEqual(result["status"], "resolved")
                    self.assertTrue(result["success"])
                    self.assertTrue(result["hit"])
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["outcome"], "hit")
                    self.assertEqual(result["attack_rolls"], attack_rolls)
                    self.assertEqual(result["attack_bonus"], 4)
                    self.assertEqual(result["attack_total"], 14)
                    self.assertEqual(result["target_ac_base"], 12)
                    self.assertEqual(result["target_ac"], 12 if reverse_only else 14)
                    self.assertEqual(result["cover_state"], "none" if reverse_only else "half")
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"],
                                     [] if reverse_only else ["unseen_target"])
                    self.assertEqual(result["damage_rolls"], [
                        {"source": "weapon", "die": 6, "count": 1, "rolls": [4]}])
                    self.assertEqual(result["damage_type"], "piercing")
                    self.assertEqual(result["damage"], 6)
                    self.assertEqual(result["hp_damage"], 6)
                    self.assertEqual(result["target_hp_before"], 100)
                    self.assertEqual(result["target_hp_after"], 94)
                    self.assertEqual(s.character["current_hp"], 94)
                    self.assertEqual(n["current_hp"], 100)
                    bow = attack_source == "equipped_weapon"
                    self.assertEqual(result["ammunition_consumed"],
                                     {"type": "arrow", "quantity": 1} if bow else None)
                    self.assertEqual(n["ammunition"], {"arrow": 19 if bow else 20})
                    self.assertEqual(s.world_state["ammunition"], player_ammunition_before)
                    self.assertEqual(s.world_state["attack_results"], [result])
                    self.assertIsNot(s.world_state["attack_results"][0], result)
                    self.assertEqual(s.world_state["attack_environment"], geometry_before)
                    self.assertEqual(json.dumps(
                        {"distance_ft": n["distance_ft"]} if "distance_ft" in n else {},
                        sort_keys=True), canonical_before)
                    self.assertEqual(snapshot(game._DEFAULT_SESSION), default_before)

    def test_npc_valid_authored_distance_overrides_invalid_canonical_distance(self):
        invalid_distances = (
            None, False, True, -1, float("nan"), float("inf"), float("-inf"),
            "30", "30.0", [], [30], {}, {"distance_ft": 30},
        )
        for distance in invalid_distances:
            with self.subTest(distance=distance):
                self.assert_npc_authored_distance_overrides_broken_canonical(distance)

    def test_npc_valid_authored_distance_overrides_absent_canonical_distance(self):
        self.assert_npc_authored_distance_overrides_broken_canonical(None, missing=True)

    def test_forward_pair_missing_distance_uses_valid_npc_distance(self):
        s, n = armed("Shortbow", distance=30)
        # Unlike supplied-invalid-distance cases, an absent key permits fallback.
        forward_pair = {"cover": "half"}
        pairs = {f"player|{n['id']}": forward_pair}
        s.world_state["attack_environment"] = {"pairs": pairs}
        self.assertIn(f"player|{n['id']}", pairs)
        self.assertNotIn("distance_ft", forward_pair)
        self.assertNotIn(f"{n['id']}|player", pairs)
        self.assertEqual(n["distance_ft"], 30)
        self.assertEqual(attack.pair(s, "player", n["id"]),
                         {"cover": "half", "distance_ft": 30})
        self.assertEqual(forward_pair, {"cover": "half"})

        # Use the real roll owners with exactly one attack die and one damage die.
        with patch.object(s.rng, "randint", side_effect=[10, 4]) as dice, \
             patch.object(game._DEFAULT_SESSION.rng, "randint",
                          side_effect=AssertionError("Attack used default-session dice")):
            result = attack.resolve(s, "player", n["id"], "Shortbow")
            self.assertEqual(dice.call_args_list, [call(1, 20), call(1, 6)])

        self.assertEqual(result["actor_id"], "player")
        self.assertEqual(result["target_id"], n["id"])
        self.assertEqual(result["status"], "resolved")
        self.assertTrue(result["success"])
        self.assertTrue(result["hit"])
        self.assertFalse(result["critical"])
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["attack_rolls"], [10])
        self.assertEqual(result["attack_bonus"], 4)
        self.assertEqual(result["attack_total"], 14)
        self.assertEqual(result["target_ac_base"], 12)
        self.assertEqual(result["target_ac"], 14)
        self.assertEqual(result["advantage_sources"], [])
        self.assertEqual(result["disadvantage_sources"], [])
        self.assertEqual(result["damage_rolls"], [
            {"source": "weapon", "die": 6, "count": 1, "rolls": [4]}])
        self.assertEqual(result["damage_type"], "piercing")
        self.assertEqual(result["damage"], 6)
        self.assertEqual(result["hp_damage"], 6)
        self.assertEqual(result["target_hp_before"], 100)
        self.assertEqual(result["target_hp_after"], 94)
        self.assertEqual(n["current_hp"], 94)
        self.assertEqual(s.character["current_hp"], 100)
        self.assertEqual(s.world_state["ammunition"]["arrow"], 19)
        self.assertEqual(s.world_state["attack_results"], [result])
        self.assertIsNot(s.world_state["attack_results"][0], result)
        self.assertEqual(pairs, {f"player|{n['id']}": {"cover": "half"}})
        self.assertEqual(n["distance_ft"], 30)

    def test_reverse_pair_missing_distance_uses_valid_npc_distance(self):
        s, n = armed("Shortbow", distance=30)
        # A reverse-only pair with no distance key still permits NPC fallback.
        reverse_pair = {"cover": "half"}
        pairs = {f"{n['id']}|player": reverse_pair}
        s.world_state["attack_environment"] = {"pairs": pairs}
        geometry_before = copy.deepcopy(s.world_state["attack_environment"])
        ammunition_before = copy.deepcopy(s.world_state["ammunition"])
        self.assertNotIn(f"player|{n['id']}", pairs)
        self.assertNotIn("distance_ft", reverse_pair)
        self.assertEqual(n["distance_ft"], 30)
        self.assertNotIn("attack_results", s.world_state)
        self.assertEqual(attack.pair(s, "player", n["id"]),
                         {"distance_ft": 30})
        self.assertEqual(s.world_state["attack_environment"], geometry_before)

        # Keep the real attack/damage owners; only script this session's dice.
        with patch.object(s.rng, "randint", side_effect=[10, 4]) as dice, \
             patch.object(game._DEFAULT_SESSION.rng, "randint",
                          side_effect=AssertionError("Attack used default-session dice")) as default_dice:
            result = attack.resolve(s, "player", n["id"], "Shortbow")
            self.assertEqual(dice.call_args_list, [call(1, 20), call(1, 6)])
            default_dice.assert_not_called()

        self.assertEqual(result["actor_id"], "player")
        self.assertEqual(result["target_id"], n["id"])
        self.assertEqual(result["status"], "resolved")
        self.assertTrue(result["success"])
        self.assertTrue(result["hit"])
        self.assertFalse(result["critical"])
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["attack_rolls"], [10])
        self.assertEqual(result["attack_bonus"], 4)
        self.assertEqual(result["attack_total"], 14)
        self.assertEqual(result["target_ac_base"], 12)
        # Reverse-only cover does not apply to the player-to-NPC attack.
        self.assertEqual(result["target_ac"], 12)
        self.assertEqual(result["advantage_sources"], [])
        self.assertEqual(result["disadvantage_sources"], [])
        self.assertEqual(result["damage_rolls"], [
            {"source": "weapon", "die": 6, "count": 1, "rolls": [4]}])
        self.assertEqual(result["damage_type"], "piercing")
        self.assertEqual(result["damage"], 6)
        self.assertEqual(result["hp_damage"], 6)
        self.assertEqual(result["target_hp_before"], 100)
        self.assertEqual(result["target_hp_after"], 94)
        self.assertEqual(n["current_hp"], 94)
        self.assertEqual(s.character["current_hp"], 100)
        ammunition_before["arrow"] -= 1
        self.assertEqual(s.world_state["ammunition"], ammunition_before)
        self.assertEqual(s.world_state["attack_results"], [result])
        self.assertIsNot(s.world_state["attack_results"][0], result)
        self.assertEqual(s.world_state["attack_environment"], geometry_before)
        self.assertEqual(n["distance_ft"], 30)

    def test_npc_attack_missing_pair_distance_uses_canonical_npc_distance(self):
        for reverse_only in (True, False):
            with self.subTest(reverse_only=reverse_only):
                s, n = armed("Shortbow", distance=30)
                n.update(weapon_id="shortbow", inventory=["Shortbow"],
                         equipment={"main_hand": "shortbow", "off_hand": None},
                         dexterity=14, dexterity_mod=2, proficiency_bonus=2,
                         weapon_proficiencies=["simple"], weapon_masteries=[],
                         ammunition={"arrow": 20})
                s.character["armor_class"] = 12
                # These facts describe only the authored direction. Reversing
                # the attack must not transfer its cover or unseen target.
                authored_pair = {"cover": "half", "attacker_sees_target": False,
                                 "target_sees_attacker": True}
                key = f"player|{n['id']}" if reverse_only else f"{n['id']}|player"
                pairs = {key: authored_pair}
                s.world_state["attack_environment"] = {"pairs": pairs}
                geometry_before = copy.deepcopy(s.world_state["attack_environment"])
                player_ammunition_before = copy.deepcopy(s.world_state["ammunition"])
                self.assertNotIn("distance_ft", authored_pair)
                self.assertEqual(n["distance_ft"], 30)
                if reverse_only:
                    self.assertNotIn(f"{n['id']}|player", pairs)
                self.assertEqual(
                    attack.pair(s, n["id"], "player"),
                    {"distance_ft": 30} if reverse_only
                    else {**authored_pair, "distance_ft": 30})
                s.advance_combat_turn()
                self.assertEqual(s.world_state["combat"]["current_actor_id"], n["id"])
                default_before = copy.deepcopy((
                    game._DEFAULT_SESSION.world_state, game._DEFAULT_SESSION.character,
                    game._DEFAULT_SESSION.messages, game._DEFAULT_SESSION.rng.getstate()))
                attack_rolls = [10] if reverse_only else [10, 12]
                remaining = iter([(20, value) for value in attack_rolls] + [(6, 4)])

                def owned_randint(low, high):
                    self.assertIs(game._session(), s)
                    expected = next(remaining, None)
                    self.assertIsNotNone(expected, "Unexpected attack or damage die")
                    sides, value = expected
                    self.assertEqual((low, high), (1, sides))
                    return value

                # Do not mock roll_attack/roll_damage: both must use this session.
                with patch.object(s.rng, "randint", side_effect=owned_randint) as dice, \
                     patch.object(game._DEFAULT_SESSION.rng, "randint",
                                  side_effect=AssertionError("Enemy used default dice")) as default_dice:
                    result = s.resolve_enemy_attack(n)
                    self.assertEqual(dice.call_args_list,
                                     [call(1, 20)] * len(attack_rolls) + [call(1, 6)])
                    self.assertIsNone(next(remaining, None), "Expected dice were not consumed")
                    default_dice.assert_not_called()

                self.assertEqual(result["actor_id"], n["id"])
                self.assertEqual(result["target_id"], "player")
                self.assertEqual(result["status"], "resolved")
                self.assertTrue(result["success"])
                self.assertTrue(result["hit"])
                self.assertFalse(result["critical"])
                self.assertEqual(result["outcome"], "hit")
                self.assertEqual(result["attack_rolls"], attack_rolls)
                self.assertEqual(result["attack_bonus"], 4)
                self.assertEqual(result["attack_total"], 14)
                self.assertEqual(result["target_ac_base"], 12)
                self.assertEqual(result["target_ac"], 12 if reverse_only else 14)
                self.assertEqual(result["cover_state"], "none" if reverse_only else "half")
                self.assertEqual(result["advantage_sources"], [])
                self.assertEqual(result["disadvantage_sources"],
                                 [] if reverse_only else ["unseen_target"])
                self.assertEqual(result["damage_rolls"], [
                    {"source": "weapon", "die": 6, "count": 1, "rolls": [4]}])
                self.assertEqual(result["damage_type"], "piercing")
                self.assertEqual(result["damage"], 6)
                self.assertEqual(result["hp_damage"], 6)
                self.assertEqual(result["target_hp_before"], 100)
                self.assertEqual(result["target_hp_after"], 94)
                self.assertEqual(s.character["current_hp"], 94)
                self.assertEqual(n["current_hp"], 100)
                self.assertEqual(n["ammunition"], {"arrow": 19})
                self.assertEqual(s.world_state["ammunition"], player_ammunition_before)
                self.assertEqual(s.world_state["attack_results"], [result])
                self.assertIsNot(s.world_state["attack_results"][0], result)
                self.assertEqual(s.world_state["attack_environment"], geometry_before)
                self.assertEqual(n["distance_ft"], 30)
                self.assertEqual((
                    game._DEFAULT_SESSION.world_state, game._DEFAULT_SESSION.character,
                    game._DEFAULT_SESSION.messages, game._DEFAULT_SESSION.rng.getstate()),
                    default_before)

    def assert_invalid_forward_distance_not_replaced_by_npc(self, distance):
        s, n = armed("Shortbow", distance=30)
        pairs = {f"player|{n['id']}": {"distance_ft": distance}}
        s.world_state["attack_environment"] = {"pairs": pairs}
        self.assertIn("distance_ft", pairs[f"player|{n['id']}"])
        self.assertNotIn(f"{n['id']}|player", pairs)
        self.assertEqual(n["distance_ft"], 30)
        self.assert_unknown_distance_unchanged(s, n)

    def test_forward_pair_negative_distance_not_replaced_by_valid_npc(self):
        self.assert_invalid_forward_distance_not_replaced_by_npc(-1)

    def test_forward_pair_boolean_distance_not_replaced_by_valid_npc(self):
        for distance in (False, True):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_not_replaced_by_npc(distance)

    def test_forward_pair_nonfinite_distance_not_replaced_by_valid_npc(self):
        for distance in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_not_replaced_by_npc(distance)

    def test_forward_pair_none_distance_not_replaced_by_valid_npc(self):
        self.assert_invalid_forward_distance_not_replaced_by_npc(None)

    def test_forward_pair_numeric_string_distance_not_replaced_by_valid_npc(self):
        for distance in ("30", "30.0"):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_not_replaced_by_npc(distance)

    def test_forward_pair_list_distance_not_replaced_by_valid_npc(self):
        for distance in ([], [30]):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_not_replaced_by_npc(distance)

    def test_forward_pair_dict_distance_not_replaced_by_valid_npc(self):
        for distance in ({}, {"distance_ft": 30}):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_not_replaced_by_npc(distance)

    def assert_invalid_reverse_distance_not_replaced_by_npc(self, distance):
        s, n = armed("Shortbow", distance=30)
        pairs = {f"{n['id']}|player": {"distance_ft": distance}}
        s.world_state["attack_environment"] = {"pairs": pairs}
        self.assertIn("distance_ft", pairs[f"{n['id']}|player"])
        self.assertNotIn(f"player|{n['id']}", pairs)
        self.assertEqual(n["distance_ft"], 30)
        self.assert_unknown_distance_unchanged(s, n)

    def test_reverse_pair_negative_distance_not_replaced_by_valid_npc(self):
        self.assert_invalid_reverse_distance_not_replaced_by_npc(-1)

    def test_reverse_pair_boolean_distance_not_replaced_by_valid_npc(self):
        for distance in (False, True):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_not_replaced_by_npc(distance)

    def test_reverse_pair_nonfinite_distance_not_replaced_by_valid_npc(self):
        for distance in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_not_replaced_by_npc(distance)

    def test_reverse_pair_none_distance_not_replaced_by_valid_npc(self):
        self.assert_invalid_reverse_distance_not_replaced_by_npc(None)

    def test_reverse_pair_numeric_string_distance_not_replaced_by_valid_npc(self):
        for distance in ("30", "30.0"):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_not_replaced_by_npc(distance)

    def test_reverse_pair_list_distance_not_replaced_by_valid_npc(self):
        for distance in ([], [30]):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_not_replaced_by_npc(distance)

    def test_reverse_pair_dict_distance_not_replaced_by_valid_npc(self):
        for distance in ({}, {"distance_ft": 30}):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_not_replaced_by_npc(distance)

    def test_reverse_pair_negative_distance_rejected_unchanged(self):
        self.assert_invalid_reverse_distance_unchanged({"distance_ft": -1})

    def test_reverse_pair_boolean_distance_rejected_unchanged(self):
        for distance in (False, True):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_unchanged({"distance_ft": distance})

    def test_reverse_pair_nonfinite_distance_rejected_unchanged(self):
        for distance in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_unchanged({"distance_ft": distance})

    def test_reverse_pair_missing_distance_rejected_unchanged(self):
        self.assert_invalid_reverse_distance_unchanged({})

    def test_reverse_pair_none_distance_rejected_unchanged(self):
        self.assert_invalid_reverse_distance_unchanged({"distance_ft": None})

    def test_reverse_pair_numeric_string_distance_rejected_unchanged(self):
        for distance in ("30", "30.0"):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_unchanged({"distance_ft": distance})

    def test_reverse_pair_list_distance_rejected_unchanged(self):
        for distance in ([], [30]):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_unchanged({"distance_ft": distance})

    def test_reverse_pair_dict_distance_rejected_unchanged(self):
        for distance in ({}, {"distance_ft": 30}):
            with self.subTest(distance=distance):
                self.assert_invalid_reverse_distance_unchanged({"distance_ft": distance})

    def test_forward_pair_negative_distance_not_replaced_by_valid_reverse(self):
        self.assert_invalid_forward_distance_unchanged({"distance_ft": -1})

    def test_forward_pair_boolean_distance_not_replaced_by_valid_reverse(self):
        for distance in (False, True):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_unchanged({"distance_ft": distance})

    def test_forward_pair_nonfinite_distance_not_replaced_by_valid_reverse(self):
        for distance in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_unchanged({"distance_ft": distance})

    def test_forward_pair_missing_distance_not_replaced_by_valid_reverse(self):
        self.assert_invalid_forward_distance_unchanged({})

    def test_forward_pair_none_distance_not_replaced_by_valid_reverse(self):
        self.assert_invalid_forward_distance_unchanged({"distance_ft": None})

    def test_forward_pair_numeric_string_distance_not_replaced_by_valid_reverse(self):
        for distance in ("30", "30.0"):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_unchanged({"distance_ft": distance})

    def test_forward_pair_list_distance_not_replaced_by_valid_reverse(self):
        for distance in ([], [30]):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_unchanged({"distance_ft": distance})

    def test_forward_pair_dict_distance_not_replaced_by_valid_reverse(self):
        for distance in ({}, {"distance_ft": 30}):
            with self.subTest(distance=distance):
                self.assert_invalid_forward_distance_unchanged({"distance_ft": distance})

    def assert_valid_forward_pair_ignores_broken_reverse(self, *, npc_origin):
        malformed_pairs = [
            {}, *({"distance_ft": value} for value in (
                -1, False, True, float("nan"), float("inf"), float("-inf"),
                None, "30", "30.0", [], [30], {}, {"distance_ft": 30},
            )),
        ]

        def snapshot(session):
            # JSON also permits a stable comparison of malformed NaN fixtures.
            return json.dumps((
                session.serialize_game_state(), session.world_state,
                session.character, session.messages, session.rng.getstate(),
            ), sort_keys=True)

        for reverse_distance in malformed_pairs:
            for obscured_forward in (False, True):
                with self.subTest(reverse=reverse_distance,
                                  obscured_forward=obscured_forward):
                    s, n = armed("Shortbow")
                    # No canonical distance may hide an incorrect pair lookup.
                    del n["distance_ft"]
                    s.character["armor_class"] = 12
                    if npc_origin:
                        n.update(weapon_id="shortbow", inventory=["Shortbow"],
                                 equipment={"main_hand": "shortbow", "off_hand": None},
                                 dexterity=14, dexterity_mod=2, proficiency_bonus=2,
                                 weapon_proficiencies=["simple"], weapon_masteries=[],
                                 ammunition={"arrow": 20})
                        s.advance_combat_turn()
                    actor, target = ((n["id"], "player") if npc_origin
                                     else ("player", n["id"]))
                    forward = {
                        "distance_ft": 30,
                        "cover": "half" if obscured_forward else "none",
                        "attacker_sees_target": not obscured_forward,
                        "target_sees_attacker": True,
                    }
                    reverse = {
                        **reverse_distance,
                        "cover": "none" if obscured_forward else "total",
                        "attacker_sees_target": obscured_forward,
                        "target_sees_attacker": False,
                        "guessed_location_correct": False,
                    }
                    s.world_state["attack_environment"] = {"pairs": {
                        f"{actor}|{target}": forward,
                        f"{target}|{actor}": reverse,
                    }}
                    geometry_before = json.dumps(s.world_state["attack_environment"],
                                                 sort_keys=True)
                    ammunition_before = copy.deepcopy(s.world_state["ammunition"])
                    default_before = snapshot(game._DEFAULT_SESSION)
                    rng_before = s.rng.getstate()
                    self.assertEqual(attack.pair(s, actor, target), forward)
                    self.assertNotIn("distance_ft", n)

                    attack_rolls = [10, 12] if obscured_forward else [10]
                    remaining = iter([*attack_rolls, 4])

                    def owned_randint(low, high):
                        self.assertIs(game._session(), s)
                        value = next(remaining)
                        self.assertLessEqual(low, value)
                        self.assertLessEqual(value, high)
                        return value

                    # Do not replace roll_attack/roll_damage: they must route
                    # through the explicit session, never the default campaign.
                    with patch.object(s.rng, "randint", side_effect=owned_randint) as dice, \
                         patch.object(game._DEFAULT_SESSION.rng, "randint",
                                      side_effect=AssertionError("Attack used default dice")) as default_dice:
                        result = (s.resolve_enemy_attack(n) if npc_origin else
                                  attack.resolve(s, actor, target, "Shortbow"))
                        self.assertEqual(dice.call_args_list,
                                         [call(1, 20)] * len(attack_rolls) + [call(1, 6)])
                        self.assertIsNone(next(remaining, None), "Expected dice were not consumed")
                        default_dice.assert_not_called()

                    self.assertEqual(result["actor_id"], actor)
                    self.assertEqual(result["target_id"], target)
                    self.assertEqual(result["status"], "resolved")
                    self.assertTrue(result["success"])
                    self.assertTrue(result["hit"])
                    self.assertFalse(result["critical"])
                    self.assertEqual(result["outcome"], "hit")
                    self.assertEqual(result["attack_rolls"], attack_rolls)
                    self.assertEqual(result["attack_bonus"], 4)
                    self.assertEqual(result["attack_total"], 14)
                    self.assertEqual(result["target_ac_base"], 12)
                    self.assertEqual(result["target_ac"], 14 if obscured_forward else 12)
                    self.assertEqual(result["cover_state"], forward["cover"])
                    self.assertEqual(result["advantage_sources"], [])
                    self.assertEqual(result["disadvantage_sources"],
                                     ["unseen_target"] if obscured_forward else [])
                    self.assertEqual(result["damage_rolls"], [
                        {"source": "weapon", "die": 6, "count": 1, "rolls": [4]}])
                    self.assertEqual(result["damage_type"], "piercing")
                    self.assertEqual(result["damage"], 6)
                    self.assertEqual(result["hp_damage"], 6)
                    self.assertEqual(result["target_hp_before"], 100)
                    self.assertEqual(result["target_hp_after"], 94)
                    self.assertEqual(s.character["current_hp"], 94 if npc_origin else 100)
                    self.assertEqual(n["current_hp"], 100 if npc_origin else 94)
                    self.assertEqual(result["ammunition_consumed"],
                                     {"type": "arrow", "quantity": 1})
                    if npc_origin:
                        self.assertEqual(n["ammunition"], {"arrow": 19})
                    else:
                        ammunition_before["arrow"] -= 1
                    self.assertEqual(s.world_state["ammunition"], ammunition_before)
                    self.assertEqual(s.world_state["attack_results"], [result])
                    self.assertIsNot(s.world_state["attack_results"][0], result)
                    self.assertEqual(json.dumps(s.world_state["attack_environment"],
                                                sort_keys=True), geometry_before)
                    self.assertNotIn("distance_ft", n)
                    # The scripted RNG does not advance its underlying state.
                    self.assertEqual(s.rng.getstate(), rng_before)
                    self.assertEqual(snapshot(game._DEFAULT_SESSION), default_before)

    def test_player_valid_forward_pair_ignores_malformed_reverse_distance(self):
        self.assert_valid_forward_pair_ignores_broken_reverse(npc_origin=False)

    def test_npc_valid_forward_pair_ignores_malformed_reverse_distance(self):
        self.assert_valid_forward_pair_ignores_broken_reverse(npc_origin=True)

    def test_lance_has_2024_two_handed_property_not_2014_mounted_exception(self):
        s, n = armed("Lance")
        s.character["mounted"] = True
        s.world_state["equipment"]["off_hand"] = "shield"
        self.assert_invalid_unchanged(s, n, "Lance", {"grip": 1})

    def test_class_override_no_hardcoded_class_and_no_weapon_properties(self):
        s, n = armed()
        s.character["attack_rules"] = {"ability": "dexterity", "damage_die": 6, "damage_dice": 1}
        r = resolve(s, n, "unarmed")
        self.assertEqual(r["ability_used"], "dexterity")
        self.assertEqual(r["damage"], 5)
        self.assertIsNone(r["mastery"])

    def test_authoritative_rng_exact_consumption(self):
        for rolls, damage_dice in ((1, 1), (2, 1), (1, 0)):
            s, n = armed()
            s.rng.seed(1234)
            oracle = random.Random(1234)
            if rolls == 2:
                s.character["attack_rules"] = {"advantage_sources": ["owned"]}
            if damage_dice == 0:
                n["armor_class"] = 99
            selected = max(oracle.randint(1, 20) for _ in range(rolls))
            if selected == 20:
                damage_dice = 2
            for _ in range(damage_dice):
                oracle.randint(1, 8)
            r = attack.resolve(s, "player", n["id"], "Longsword")
            self.assertEqual(s.rng.getstate(), oracle.getstate())
            self.assertEqual(r["attack_roll"], selected)

    def test_preview_no_rng_ammo_resources_hp_or_receipt(self):
        s, n = armed("Shortbow", distance=20)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        attack.preview(s, "player", n["id"], "Shortbow")
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_feature_failure_rolls_back_dice_hp_inventory_and_effects(self):
        s, n = armed("Shortbow", distance=20, mastery=True)
        s.register_attack_hook("after_mastery", lambda *_: (_ for _ in ()).throw(ValueError("forced")))
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with self.assertRaises(ValueError):
            attack.resolve(s, "player", n["id"], "Shortbow")
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_save_load_keeps_result_effects_ammo_and_rng_without_reroll(self):
        s, n = armed("Shortbow", distance=20, mastery=True)
        resolve(s, n, "Shortbow")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            s.save_game(path)
            other, _ = ready()
            with patch("game.roll_d20", side_effect=AssertionError("reload roll")):
                other.load_game(path)
        self.assertEqual(other.world_state["attack_results"], s.world_state["attack_results"])
        self.assertEqual(other.world_state["attack_effects"], s.world_state["attack_effects"])
        self.assertEqual(other.world_state["ammunition"], s.world_state["ammunition"])
        self.assertEqual(other.rng.getstate(), s.rng.getstate())

    def test_sessions_and_feature_hooks_are_isolated(self):
        left, n = armed()
        right, _ = armed()
        before = copy.deepcopy((right.world_state, right.character, right.rng.getstate()))
        left.register_attack_hook("after_damage", lambda *_: None)
        resolve(left, n)
        self.assertEqual((right.world_state, right.character, right.rng.getstate()), before)
        self.assertFalse(hasattr(right, "_attack_hooks"))

    def test_qwen_cannot_supply_equipment_attack_effects_or_weapon_stats(self):
        s, n = armed()
        before = copy.deepcopy((s.world_state, s.character))
        candidate = {"equipment": {"main_hand": "greatsword"}, "ammunition": {"arrow": 999},
                     "attack_effects": [{"kind": "vex"}], "attack_results": [{"damage": 999}],
                     "update_npcs": [{"id": n["id"], "distance_ft": 0, "weapon_id": "greatsword",
                                      "resistances": [], "armor_class": 1, "current_hp": 0}]}
        s.merge_world_updates(s.validate_world_updates(candidate))
        self.assertEqual((s.world_state, s.character), before)

    def test_starting_held_sword_survives_materialize_for_named_and_pronoun_attacks(self):
        """Regression: item_* migration must not break an already-held starting sword."""
        s, n = ready()
        self.assertEqual(s.world_state["equipment"]["main_hand"], "longsword")
        equipment_economy.materialize(s.world_state)
        sword = next(i for i in s.world_state["inventory"] if i["name"] == "Kılıç")
        self.assertEqual(s.world_state["equipment"]["main_hand"], sword["item_id"])
        for text in ("Ona kılıcımla saldırıyorum.", "Ona saldırıyorum."):
            with self.subTest(text=text):
                identity, choice = attack.natural_choice(s, text)
                self.assertEqual(identity, "longsword")
                self.assertNotIn("draw", choice)
                result = resolve(s, n, identity, choice, rolls=(12,))
                self.assertEqual(result["weapon_id"], "longsword")
                self.assertEqual(s.world_state["equipment"]["main_hand"], sword["item_id"])

    def test_unheld_inventory_sword_still_rejects_named_attack_without_draw(self):
        s, n = ready()
        s.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        equipment_economy.materialize(s.world_state)
        self.assertIsNone(s.world_state["equipment"]["main_hand"])
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with self.assertRaises(CombatRequestError) as raised:
            attack.resolve(s, "player", n["id"], "longsword", {})
        self.assertEqual(raised.exception.code, "weapon_not_held")
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

    def test_new_fighter_package_c_greatsword_identity_and_draw(self):
        s = game.GameSession(seed=20261012)
        configure_character(
            s,
            mode="custom",
            name="LR00 package C",
            species="Dwarf",
            character_class="Fighter",
            background="Soldier",
            alignment="Neutral Good",
            ability_score_method="standard_array",
            ability_scores={
                "strength": 15, "constitution": 14, "dexterity": 13,
                "wisdom": 12, "intelligence": 10, "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "constitution": 1},
            proficient_skills=["Athletics", "Intimidation", "Perception", "Survival"],
            equipment_package="C",
            background_equipment_option="A",
            fighting_style="Defense",
            languages=["Common", "Dwarvish", "Elvish"],
        )

        self.assertIn("Büyük Kılıç (Greatsword)", s.character["equipment_choices"])
        equipment_economy.materialize(s.world_state)
        greatsword = next(
            item for item in s.world_state["inventory"]
            if item.get("weapon_id") == "greatsword"
        )
        self.assertEqual(lookup(greatsword["weapon_id"])["name"], "Greatsword")
        self.assertIsNone(s.world_state["equipment"]["main_hand"])
        self.assertIsNone(s.world_state["equipment"]["off_hand"])

        s.world_state["location"] = "tavern"
        npc = s.create_npc_from_ai({
            "name": "Package C probe target", "role": "Guard", "location": "tavern",
        })
        npc.update(
            current_hp=40, max_hp=40, armor_class=20, hostile=True, distance_ft=5,
        )
        s.world_state.setdefault("monster_perception", {})[npc["id"]] = {
            "player": {"visible": True},
        }
        with patch("game.roll_initiative_player", return_value=20), patch(
            "game.roll_initiative", return_value=1
        ):
            s.start_combat(npc)

        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with self.assertRaises(CombatRequestError) as raised:
            attack.prepare(s, "player", npc["id"], "greatsword")
        self.assertEqual(raised.exception.code, "weapon_not_held")
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)

        prepared = attack.prepare(
            s, "player", npc["id"], "greatsword", {"draw": True},
        )
        self.assertEqual(prepared["weapon"]["weapon_id"], "greatsword")
        self.assertEqual(prepared["weapon"]["instance_id"], greatsword["item_id"])
        self.assertEqual(
            prepared["weapon"]["equipment_after"]["main_hand"],
            greatsword["item_id"],
        )
        self.assertEqual(
            (s.world_state, s.character, s.rng.getstate()), before,
            "prepare is a preview; the selected draw is committed only by resolution",
        )

    def test_natural_language_choices_no_stats_from_prose(self):
        s, n = armed("Dagger")
        identity, choice = attack.natural_choice(s, "Rakip'e hançerle dexterity kullanarak saldırıyorum.")
        self.assertEqual(identity, "dagger")
        self.assertEqual(choice, {"ability": "dexterity"})
        with patch("game.parse_player_intent", return_value={"intent": "attack"}) as intent, patch("game.roll_attack", return_value=1), patch("game.resolve_enemy_attack", return_value={"action": "enemy_attack", "damage": 0}):
            r = s.run_player_turn("Rakip'e hançerle saldırıyorum.", target_id=n["id"], action_id=str(uuid4()))
        self.assertEqual(r["action_result"]["weapon_id"], "dagger")
        self.assertLessEqual(intent.call_count, 1)


# Individually named tests give exact results for catalog, condition and boundary
# cases rather than one opaque test that hides hundreds of subcases.
def catalog_test(name):
    def test(self):
        w = lookup(name)
        s, n = armed(name, distance=20 if w["kind"] == "ranged" else 5)
        r = resolve(s, n, name)
        self.assertEqual(r["weapon_id"], w["weapon_id"])
        self.assertEqual(r["damage_type"], w["damage_type"])
        self.assertEqual(w["source"], "PHB 2024 p.215")
        self.assertIn(w["mastery"], attack.MASTERY)
    return test


for name in WEAPONS:
    if name != "Kılıç":
        setattr(WeaponTests, "test_catalog_" + lookup(name)["weapon_id"], catalog_test(name))


def damage_test(kind, mode):
    def test(self):
        s, n = armed()
        n[mode] = [kind, kind]
        s.character["attack_rules"] = {"additional_damage": [
            {"source": "typed_feature", "damage_type": kind, "damage_dice": 0, "modifier": 7}]}
        r = resolve(s, n)
        instance = next(i for i in r["damage_instances"] if i["damage_type"] == kind)
        raw = 13 if kind == "slashing" else 7
        expected = raw // 2 if mode == "resistances" else raw * 2 if mode == "vulnerabilities" else 0
        self.assertEqual(instance["final_damage"], expected)
    return test


for damage_type in sorted(attack.DAMAGE_TYPES):
    for mode in ("resistances", "vulnerabilities", "immunities"):
        setattr(WeaponTests, f"test_damage_{damage_type}_{mode}", damage_test(damage_type, mode))


def condition_test(who, condition, distance, expected):
    def test(self):
        s, n = armed("Whip", distance=distance)
        data = s.character if who == "actor" else n
        data["conditions"] = [condition]
        r = resolve(s, n, "Whip", rolls=(10, 15))
        self.assertIn(expected, r["advantage_sources"] + r["disadvantage_sources"])
        self.assertEqual(len(r["attack_rolls"]), 2)
    return test


for who, name, distance, source in [
    ("actor", "blinded", 5, "blinded"), ("actor", "poisoned", 5, "poisoned"),
    ("actor", "prone", 5, "prone"), ("actor", "restrained", 5, "restrained"),
    ("actor", "invisible", 5, "invisible_attacker"),
    ("target", "blinded", 5, "target_blinded"), ("target", "restrained", 5, "target_restrained"),
    ("target", "stunned", 5, "target_stunned"), ("target", "unconscious", 5, "target_unconscious"),
    ("target", "prone", 5, "target_prone"), ("target", "prone", 10, "target_prone"),
    ("target", "invisible", 5, "invisible_target"),
]:
    setattr(WeaponTests, f"test_condition_{who}_{name}_{distance}", condition_test(who, name, distance, source))


def invalid_test(kind):
    def test(self):
        s, n = armed("Shortbow", distance=20)
        choice, origin, weapon = {}, "action", "Shortbow"
        if kind == "missing_distance":
            del n["distance_ft"]
        elif kind == "long_range":
            n["distance_ft"] = 321
        elif kind == "missing_weapon":
            s.world_state["inventory"] = []
        elif kind == "not_held":
            s.world_state["equipment"]["main_hand"] = None
        elif kind == "hands":
            s.world_state["equipment"]["off_hand"] = "shield"
        elif kind == "equipment_unknown":
            del s.world_state["equipment"]
        elif kind == "ammo":
            s.world_state["ammunition"] = {"bolt": 100}
        elif kind == "total_cover":
            s.world_state["attack_environment"] = {"pairs": {
                f"player|{n['id']}": {"distance_ft": 20, "cover": "total"}}}
        elif kind == "out_of_turn":
            s.advance_combat_turn()
        elif kind == "ungranted_reaction":
            origin = "reaction"
        elif kind == "ungranted_continuation":
            origin = "continuation"
        elif kind == "incapacitated":
            s.character["conditions"] = ["incapacitated"]
        elif kind == "forged_numbers":
            choice = {"attack_bonus": 999}
        elif kind == "invalid_mastery":
            choice = {"mastery": "push"}
        elif kind == "wrong_ability":
            choice = {"ability": "strength"}
        elif kind == "invalid_mode":
            choice = {"mode": "melee"}
        elif kind == "duplicate_sources":
            s.character["attack_rules"] = {"attack_modifiers": [{"source": "feat", "value": 1}] * 2}
        elif kind == "double_proficiency":
            s.character["attack_rules"] = {"attack_modifiers": [{"source": "proficiency", "value": 2}]}
        elif kind == "invalid_type":
            s.character["attack_rules"] = {"additional_damage": [{"source": "feat", "damage_type": "invented", "modifier": 1}]}
        elif kind == "unknown_weapon":
            weapon = "invented"
        self.assert_invalid_unchanged(s, n, weapon, choice, origin)
    return test


for name in ("missing_distance", "long_range", "missing_weapon", "not_held", "hands", "equipment_unknown",
             "ammo", "total_cover", "out_of_turn", "ungranted_reaction", "ungranted_continuation",
             "incapacitated", "forged_numbers", "invalid_mastery", "wrong_ability", "invalid_mode",
             "duplicate_sources", "double_proficiency", "invalid_type", "unknown_weapon"):
    setattr(WeaponTests, "test_invalid_" + name, invalid_test(name))


class WeaponPushPersistenceTests(unittest.TestCase):
    def test_reverse_push_stays_blocked_after_campaign_reopen(self):
        # Keep disk-backed coverage separate from the in-memory push cases.
        for corridor in (20, 30):
            with self.subTest(corridor=corridor), tempfile.TemporaryDirectory() as directory:
                s, n = armed("Warhammer", mastery=True)
                other = s.create_npc_from_ai({
                    "name": "Bystander", "role": "Guard", "location": "tavern"})
                other["distance_ft"] = 30
                forward_key = f"player|{n['id']}"
                reverse_key = f"{n['id']}|player"
                unrelated = {
                    f"player|{other['id']}": {"distance_ft": 30},
                    f"{other['id']}|player": {"distance_ft": 30},
                }
                s.world_state["attack_environment"] = {"pairs": {
                    **copy.deepcopy(unrelated),
                    forward_key: {"distance_ft": 5, "push_clear_ft": corridor},
                    reverse_key: {"distance_ft": 5, "push_clear_ft": 20},
                    f"{n['id']}|{other['id']}": {"distance_ft": 25},
                    f"{other['id']}|{n['id']}": {"distance_ft": 25},
                }}
                s.initialize_species_trait_state()
                store = CampaignStore(Path(directory) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
                campaign_id = str(uuid4())
                s.world_state["campaign_id"] = campaign_id
                store.create_campaign(campaign_id, "Push persistence", s)

                result = resolve(s, n, "Warhammer", rolls=(20,))
                self.assertTrue(result["hit"])
                self.assertEqual(result["mastery_effect"], {
                    "kind": "push", "applied": True, "distance_ft": 10,
                    "resulting_distance_ft": 15})
                expected_geometry = {"pairs": {
                    **unrelated,
                    forward_key: {
                        "distance_ft": 15, "push_clear_ft": corridor - 10},
                }}
                self.assertEqual(s.world_state["attack_environment"], expected_geometry)
                store.save_campaign(campaign_id, s)
                self.assertEqual(
                    store.get_campaign(campaign_id).payload["engine_save"]["world_state"]["attack_environment"],
                    expected_geometry)
                saved_rng = s.rng.getstate()

                # New store, manager, and session: no retained live geometry.
                reopened_store = CampaignStore(store.path, bound_principal=TEST_PLAYER)
                manager = SessionManager(campaign_store=reopened_store)
                _, record, _, _, _ = manager.resume_campaign(campaign_id)
                restored = record.game_session
                self.assertIsNot(restored, s)
                self.assertEqual(restored.rng.getstate(), saved_rng)
                self.assertEqual(restored.world_state["attack_results"], s.world_state["attack_results"])
                self.assertEqual(restored.world_state["attack_environment"], expected_geometry)
                self.assertNotIn(reverse_key, restored.world_state["attack_environment"]["pairs"])
                # Remaining forward clearance is sufficient, but is not
                # permission to push in the opposite direction.
                self.assertGreaterEqual(
                    restored.world_state["attack_environment"]["pairs"][forward_key]["push_clear_ft"], 10)
                self.assertEqual(attack.pair(restored, n["id"], "player"),
                                 {"distance_ft": 15})
                mirrors = {
                    npc["id"]: npc["distance_ft"]
                    for npc in restored.world_state["npcs"]
                    if npc["id"] in (n["id"], other["id"])
                }
                self.assertEqual(mirrors, {n["id"]: 15, other["id"]: 30})
                before = copy.deepcopy((
                    restored.world_state, restored.character, restored.messages,
                    restored.rng.getstate(), restored.serialize_game_state()))
                persisted_before = copy.deepcopy(reopened_store.get_campaign(campaign_id))
                with patch.object(restored.rng, "randint", side_effect=AssertionError("blocked push rolled")):
                    rejected = attack.push(restored, n["id"], "player", 10)
                self.assertEqual(rejected, {
                    "kind": "push", "applied": False,
                    "reason": "position_unresolved_or_blocked"})
                self.assertEqual((
                    restored.world_state, restored.character, restored.messages,
                    restored.rng.getstate(), restored.serialize_game_state()), before)
                self.assertEqual(reopened_store.get_campaign(campaign_id), persisted_before)


    def assert_npc_push_persists_without_reverse_permission(
            self, s, actor_id, target_id, corridor, unrelated, stale_keys, mirrors):
        forward_key = f"{actor_id}|{target_id}"
        reverse_key = f"{target_id}|{actor_id}"
        expected_geometry = {"pairs": {
            **copy.deepcopy(unrelated),
            forward_key: {"distance_ft": 15, "push_clear_ft": corridor - 10},
        }}
        with tempfile.TemporaryDirectory() as directory:
            s.initialize_species_trait_state()
            store = CampaignStore(Path(directory) / "campaigns.sqlite3", bound_principal=TEST_PLAYER)
            campaign_id = str(uuid4())
            s.world_state["campaign_id"] = campaign_id
            store.create_campaign(campaign_id, "NPC push persistence", s)
            rng_before = s.rng.getstate()
            self.assertEqual(attack.push(s, actor_id, target_id, 10), {
                "kind": "push", "applied": True, "distance_ft": 10,
                "resulting_distance_ft": 15})
            self.assertEqual(s.rng.getstate(), rng_before)
            self.assertEqual(s.world_state["attack_environment"], expected_geometry)
            store.save_campaign(campaign_id, s)
            saved_world = store.get_campaign(campaign_id).payload["engine_save"]["world_state"]
            self.assertEqual(saved_world["attack_environment"], expected_geometry)
            self.assertEqual({
                npc["id"]: npc["distance_ft"] for npc in saved_world["npcs"]
                if npc["id"] in mirrors}, mirrors)

            # Use entirely new persistence/session owners, not the live fixture.
            reopened_store = CampaignStore(store.path, bound_principal=TEST_PLAYER)
            manager = SessionManager(campaign_store=reopened_store)
            _, record, _, _, _ = manager.resume_campaign(campaign_id)
            restored = record.game_session
            self.assertIsNot(restored, s)
            self.assertEqual(restored.rng.getstate(), rng_before)
            self.assertEqual(restored.world_state["attack_environment"], expected_geometry)
            live_pairs = restored.world_state["attack_environment"]["pairs"]
            for key in (reverse_key, *stale_keys):
                self.assertNotIn(key, live_pairs)
            self.assertEqual({key: live_pairs[key] for key in unrelated}, unrelated)
            self.assertEqual({
                npc["id"]: npc["distance_ft"] for npc in restored.world_state["npcs"]
                if npc["id"] in mirrors}, mirrors)
            self.assertGreaterEqual(live_pairs[forward_key]["push_clear_ft"], 10)
            self.assertEqual(attack.pair(restored, target_id, actor_id),
                             {"distance_ft": 15})

            # Preserve every session/adapter/store attribute by value, while
            # checking runtime owner identity separately: deepcopy creates new
            # SqliteAttemptStore/CampaignStore handles with identity equality.
            attempt_store = restored.emergence_store
            self.assertIs(attempt_store._store, reopened_store)

            def snapshot():
                self.assertIs(restored.emergence_store, attempt_store)
                self.assertIs(attempt_store._store, reopened_store)
                attributes = dict(vars(restored))
                attributes["rng"] = restored.rng.getstate()
                attributes["emergence_store"] = {
                    key: dict(vars(value)) if key == "_store" else value
                    for key, value in vars(attempt_store).items()}
                return copy.deepcopy(attributes)

            def attempt_records():
                # Read through the same store owner; capture every persisted
                # attempt column, including statuses and proposal contents.
                connection = reopened_store._connect()
                try:
                    return [dict(row) for row in connection.execute(
                        "SELECT * FROM campaign_emergence_attempts "
                        "WHERE campaign_id = ? ORDER BY trigger_id",
                        (campaign_id,)).fetchall()]
                finally:
                    connection.close()

            restored.serialize_game_state()
            before = snapshot()
            attempts_before = attempt_records()
            persisted_before = copy.deepcopy(reopened_store.get_campaign(campaign_id))
            with patch.object(restored.rng, "randint",
                              side_effect=AssertionError("blocked push rolled")):
                rejected = attack.push(restored, target_id, actor_id, 10)
            self.assertEqual(rejected, {
                "kind": "push", "applied": False,
                "reason": "position_unresolved_or_blocked"})
            self.assertEqual(snapshot(), before)
            self.assertEqual(attempt_records(), attempts_before)
            self.assertEqual(reopened_store.get_campaign(campaign_id), persisted_before)

    def test_npc_push_player_corridor_stays_invalidated_after_campaign_reopen(self):
        for corridor in (20, 30):
            with self.subTest(corridor=corridor):
                s, actor = armed("Warhammer", mastery=True)
                other = s.create_npc_from_ai({
                    "name": "Bystander", "role": "Guard", "location": "tavern"})
                other["distance_ft"] = 30
                unrelated = {
                    f"{actor['id']}|{other['id']}": {
                        "distance_ft": 25, "push_clear_ft": 10},
                    f"{other['id']}|{actor['id']}": {
                        "distance_ft": 25, "push_clear_ft": 0},
                }
                stale = {
                    f"player|{other['id']}": {"distance_ft": 30, "push_clear_ft": 20},
                    f"{other['id']}|player": {"distance_ft": 30, "push_clear_ft": 0},
                }
                s.world_state["attack_environment"] = {"pairs": {
                    **copy.deepcopy(unrelated), **stale,
                    f"{actor['id']}|player": {
                        "distance_ft": 5, "push_clear_ft": corridor},
                    f"player|{actor['id']}": {"distance_ft": 5, "push_clear_ft": 20},
                }}
                self.assert_npc_push_persists_without_reverse_permission(
                    s, actor["id"], "player", corridor, unrelated, stale,
                    {actor["id"]: 15, other["id"]: 30})

    def test_npc_push_npc_corridor_stays_invalidated_after_campaign_reopen(self):
        for corridor in (20, 30):
            with self.subTest(corridor=corridor):
                s, actor = armed("Warhammer", mastery=True)
                actor["distance_ft"] = 40
                target = s.create_npc_from_ai({
                    "name": "Push target", "role": "Guard", "location": "tavern"})
                target.update(size="medium", distance_ft=35)
                other = s.create_npc_from_ai({
                    "name": "Bystander", "role": "Guard", "location": "tavern"})
                other["distance_ft"] = 30
                unrelated = {
                    f"player|{actor['id']}": {"distance_ft": 40, "push_clear_ft": 20},
                    f"{actor['id']}|player": {"distance_ft": 40, "push_clear_ft": 0},
                    f"player|{other['id']}": {"distance_ft": 30},
                    f"{other['id']}|player": {"distance_ft": 30},
                    f"{actor['id']}|{other['id']}": {"distance_ft": 15},
                    f"{other['id']}|{actor['id']}": {"distance_ft": 15},
                }
                stale = {
                    f"player|{target['id']}": {"distance_ft": 35, "push_clear_ft": 20},
                    f"{target['id']}|player": {"distance_ft": 35, "push_clear_ft": 0},
                    f"{target['id']}|{other['id']}": {
                        "distance_ft": 25, "push_clear_ft": 10},
                    f"{other['id']}|{target['id']}": {
                        "distance_ft": 25, "push_clear_ft": 0},
                }
                s.world_state["attack_environment"] = {"pairs": {
                    **copy.deepcopy(unrelated), **stale,
                    f"{actor['id']}|{target['id']}": {
                        "distance_ft": 5, "push_clear_ft": corridor},
                    f"{target['id']}|{actor['id']}": {
                        "distance_ft": 5, "push_clear_ft": 20},
                }}
                self.assert_npc_push_persists_without_reverse_permission(
                    s, actor["id"], target["id"], corridor, unrelated, stale,
                    {actor["id"]: 40, target["id"]: 35, other["id"]: 30})


class WeaponApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = CombatLifecycleApiTests.asyncSetUp
    asyncTearDown = CombatLifecycleApiTests.asyncTearDown
    setup_combat = CombatLifecycleApiTests.setup_combat
    request = CombatLifecycleApiTests.request
    post = CombatLifecycleApiTests.post

    def bow_command(self):
        s, n = self.setup_combat()
        s.world_state["inventory"].append("Shortbow")
        s.world_state["equipment"] = {"main_hand": "shortbow", "off_hand": None}
        s.world_state["ammunition"] = {"arrow": 5}
        s.character["weapon_masteries"] = ["shortbow"]
        n["distance_ft"] = 20
        # Match the normal save-loader's neutral character defaults before
        # snapshotting; this test must measure attack rollback, not migration.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            s.save_game(path)
            s.load_game(path)
        n = next(npc for npc in s.world_state["npcs"] if npc["id"] == n["id"])
        command = self.request(s, n, combat_action={"steps": [{"kind": "attack", "target_id": n["id"]}]})
        return s, n, command

    async def test_receipt_replay_preserves_ammo_damage_effects_rng_after_resume(self):
        s, n, command = self.bow_command()
        with patch("game.roll_attack", return_value=20):
            first = await self.post(command)
        self.assertEqual(first.status_code, 200, first.text)
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with patch("game.roll_attack", side_effect=AssertionError("replay roll")):
            duplicate = await self.post(command)
        self.assertEqual(first.json(), duplicate.json())
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)
        self.assertEqual(s.world_state["ammunition"]["arrow"], 4)
        restarted = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, restored, _, _, _ = restarted.resume_campaign(self.created["campaign_id"])
        self.assertEqual(restored.game_session.world_state["attack_results"], s.world_state["attack_results"])
        receipt = restarted.get_turn_action(restored, command["action_id"])
        self.assertEqual(receipt["response"], first.json())
        self.assertEqual(len(self.app.state.ollama_adapter._client.calls), 0)

    async def test_autosave_failure_restores_every_attack_mutation(self):
        s, n, command = self.bow_command()
        before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
        with patch("game.roll_attack", return_value=20), patch.object(self.store, "save_campaign", side_effect=CampaignStorageError("forced")):
            result = await self.post(command)
        self.assertEqual(result.status_code, 503)
        self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)
        self.assertIsNone(self.manager.get_turn_action(self.manager.get(self.sid), command["action_id"]))

    async def test_frontend_stats_forbidden_and_rejected_attack_no_model(self):
        s, n, command = self.bow_command()
        for field in ("damage", "attack_roll", "armor_class", "mastery_result", "ammunition"):
            before = copy.deepcopy((s.world_state, s.character, s.rng.getstate()))
            response = await self.post({**command, field: 999})
            self.assertEqual(response.status_code, 422)
            self.assertEqual((s.world_state, s.character, s.rng.getstate()), before)
        s.world_state["ammunition"]["arrow"] = 0
        response = await self.post(command)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.app.state.ollama_adapter._client.calls), 0)
