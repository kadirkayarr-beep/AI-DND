"""Fighter 1-5 effects through the existing owners: Second Wind, Action Surge, Tactical Shift, Extra Attack, styles, Champion.

Numbers were read from the page renders (PHB 2024 PDF 90/91/95, Fighting Style feats PDF 208/209): Second Wind heals 1d10 + Fighter
level as a Bonus Action, 2/2/2/3/3 uses, one back on a Short Rest and all on a Long Rest; Action Surge one additional action, not
Magic, one use back on a Short or Long Rest; Tactical Shift half Speed; Archery +2 attack with Ranged weapons; Dueling +2 damage;
Great Weapon Fighting 1 or 2 count as 3; Improved Critical 19-20. Dice are deterministic; synthetic NPCs are unit fixtures.
"""
import copy
import unittest
from unittest.mock import patch

import action_economy as economy
import character_progression as cp
import fighter_features as features
import game
import initiative
import weapon_attack as attacks
from api.core_resolution import resolution_action_scope
from combat_lifecycle import CombatRequestError
from api.tests.test_roadmap_c14_fighter import created, earn, earned, roundtrip
from api.tests.test_roadmap_c10_extra_attack import attack, follow, start_combat


def fight(level=1, **kwargs):
    session = created(level, **kwargs)
    return session, start_combat(session)


def wound(session, amount=20):
    session.character["max_hp"] = 60
    session.character["current_hp"] = max(1, 60 - amount)


def run(session, *steps):
    return economy.execute(session, {"steps": list(steps)})["action_economy_result"]["steps"]


def second_wind(**extra):
    return {"kind": "second_wind", "resource": "bonus", **extra}


SURGE = {"kind": "action_surge"}
DUELING = {"source": "fighting_style_dueling", "value": 2}


def end_turn(session):
    with patch("game.roll_attack", return_value=1), patch("game.roll_d20", return_value=1):
        run(session, {"kind": "end_turn"})


class SecondWind(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(2)
        wound(self.session)

    def code(self, *steps):
        with self.assertRaises(CombatRequestError) as caught:
            run(self.session, *steps)
        return caught.exception.code

    def test_heals_one_d10_plus_applied_level_and_spends_the_bonus_action_and_a_use(self):
        with patch.object(self.session.rng, "randint", return_value=7) as rolled:
            result = run(self.session, second_wind())[0]["result"]
        rolled.assert_called_once_with(1, 10)
        self.assertEqual((result["roll"], result["healing"], result["uses_remaining"]), (7, 9, 1))
        self.assertEqual(self.session.character["current_hp"], 49)
        self.assertTrue(economy.ensure(self.session)["player"]["bonus_action_spent"])
        self.assertFalse(economy.ensure(self.session)["player"]["base_action_spent"])

    def test_xp_level_above_the_applied_level_does_not_raise_the_healing(self):
        session = earned(self, 2)
        earn(session, 4)
        start_combat(session)
        wound(session)
        with patch.object(session.rng, "randint", return_value=7):
            self.assertEqual(run(session, second_wind())[0]["result"]["healing"], 9)

    def test_healing_is_capped_at_the_maximum(self):
        wound(self.session, 3)
        with patch.object(self.session.rng, "randint", return_value=10):
            self.assertEqual(run(self.session, second_wind())[0]["result"]["healing"], 3)
        self.assertEqual(self.session.character["current_hp"], 60)

    def test_one_bonus_action_a_turn(self):
        run(self.session, second_wind())
        self.assertEqual(self.code(second_wind()), "bonus_action_spent")

    def test_uses_run_out(self):
        self.session.character["fighter_uses"] = {"second_wind_spent": 2, "action_surge_spent": 0}
        self.assertEqual(self.code(second_wind()), "second_wind_uses_exhausted")

    def test_not_on_another_actors_turn_and_not_at_zero_hit_points(self):
        combat = self.session.world_state["combat"]
        combat["current_actor_id"] = self.npc["id"]
        self.assertEqual(features._second_wind_reason(self.session), "second_wind_current_combat_turn_required")
        combat["current_actor_id"] = "player"
        self.session.character["current_hp"] = 0
        self.assertEqual(features._second_wind_reason(self.session), "second_wind_incapacitated")

    def test_only_a_fighter_has_it(self):
        from api.tests.test_roadmap_c10_rage import combat
        session, _ = combat(2)
        with self.assertRaises(CombatRequestError):
            run(session, second_wind())
        self.assertIsNone(features.projection(session))

    def test_command_is_one_exact_step(self):
        for command in ({"steps": [second_wind(), {"kind": "end_turn"}]}, {"steps": [{"kind": "second_wind", "resource": "action"}]},
                        {"steps": [second_wind(target_id=self.npc["id"])]}, {"steps": [{"kind": "action_surge", "resource": "bonus"}]}):
            self.assertFalse(features.native_command(command), command)
            before = self.session._capture_runtime_snapshot()
            with self.assertRaises(CombatRequestError):
                economy.execute(self.session, command)
            self.assertEqual(self.session._capture_runtime_snapshot(), before)

    def test_failure_inside_activation_rolls_everything_back(self):
        before = self.session._capture_runtime_snapshot()
        with patch.object(features, "_heal", side_effect=ValueError("synthetic")), self.assertRaises(ValueError):
            run(self.session, second_wind())
        self.assertEqual(self.session._capture_runtime_snapshot(), before)

    def test_narration_reports_the_resolved_result(self):
        with patch.object(self.session.rng, "randint", return_value=4):
            text = economy.execute(self.session, {"steps": [second_wind()]})["narration"]
        self.assertIn("Second Wind", text)
        self.assertIn("6", text)

    def test_outside_combat_it_is_the_same_pool_and_costs_no_economy(self):
        session = created(2)
        wound(session)
        with patch.object(session.rng, "randint", return_value=5):
            result = session.resolve_species_trait_action("second_wind")
        self.assertEqual((result["effects"]["healing"], result["effects"]["uses_remaining"]), (7, 1))
        self.assertEqual(session.character["fighter_uses"]["second_wind_spent"], 1)

    def test_outside_combat_action_refuses_active_combat_and_exhausted_pool(self):
        with self.assertRaises(ValueError):
            self.session.resolve_species_trait_action("second_wind")
        session = created(2)
        session.character["fighter_uses"] = {"second_wind_spent": 2, "action_surge_spent": 0}
        with self.assertRaises(ValueError):
            session.resolve_species_trait_action("second_wind")


class Rest(unittest.TestCase):
    def spent(self, session, wind=2, surge=1):
        session.character["fighter_uses"] = {"second_wind_spent": wind, "action_surge_spent": surge}

    def test_short_rest_returns_one_second_wind_and_action_surge(self):
        session = created(2)
        self.spent(session)
        session.resolve_species_trait_action("short_rest")
        self.assertEqual(session.character["fighter_uses"], {"second_wind_spent": 1, "action_surge_spent": 0})

    def test_long_rest_returns_all(self):
        session = created(4)
        self.spent(session, 3)
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(session.character["fighter_uses"], {"second_wind_spent": 0, "action_surge_spent": 0})

    def test_interrupted_long_rest_gives_the_short_rest_part_only_after_an_hour(self):
        for elapsed, wind, surge in ((3600, 1, 0), (1800, 2, 1)):
            session = created(2)
            self.spent(session)
            with patch("game.advance_campaign_time", return_value={"interrupted": True, "elapsed_seconds": elapsed}):
                session.resolve_species_trait_action("long_rest")
            self.assertEqual(session.character["fighter_uses"], {"second_wind_spent": wind, "action_surge_spent": surge}, elapsed)

    def test_rest_with_forged_uses_changes_nothing(self):
        session = created(2)
        session.character["fighter_uses"] = {"second_wind_spent": 9, "action_surge_spent": 0}
        clock = copy.deepcopy(session.world_state["campaign_time"])
        with self.assertRaises(ValueError):
            session.resolve_species_trait_action("short_rest")
        self.assertEqual(session.world_state["campaign_time"], clock)


class ActionSurge(unittest.TestCase):
    def test_it_needs_level_two(self):
        session, _ = fight(1)
        with self.assertRaises(CombatRequestError) as caught:
            run(session, SURGE)
        self.assertEqual(caught.exception.code, "action_surge_not_available")
        self.assertIsNone(features.projection(session)["action_surge"])

    def test_gives_one_more_action_and_spends_the_use(self):
        session, npc = fight(2)
        with patch("game.roll_attack", return_value=1):
            run(session, attack(npc))
            with self.assertRaises(CombatRequestError):
                run(session, attack(npc))
            run(session, SURGE)
            run(session, attack(npc))
            with self.assertRaises(CombatRequestError):
                run(session, attack(npc))
        self.assertEqual(session.character["fighter_uses"]["action_surge_spent"], 1)
        self.assertEqual(attacks.sequence_snapshot(session, "player")["attacks"], 2)

    def test_it_can_be_declared_first_and_the_base_action_still_comes_first(self):
        session, npc = fight(2)
        run(session, SURGE)
        r = economy.ensure(session)["player"]
        self.assertEqual(r["additional_actions"][0]["remaining"], 1)
        with patch("game.roll_attack", return_value=1):
            run(session, attack(npc))
        self.assertEqual(economy.ensure(session)["player"]["additional_actions"][0]["remaining"], 1)

    def test_the_extra_action_is_not_the_magic_action(self):
        session, npc = fight(2)
        run(session, SURGE)
        grant = economy.ensure(session)["player"]["additional_actions"][0]
        self.assertNotIn("magic", grant["allowed_action_types"])
        self.assertIn("attack", grant["allowed_action_types"])
        self.assertIn("dash", grant["allowed_action_types"])
        with patch("game.roll_attack", return_value=1):
            run(session, attack(npc))
        with self.assertRaises(CombatRequestError):
            economy.action_slot(session, "player", "magic")
        economy.action_slot(session, "player", "dash")

    def test_one_use_before_a_rest_and_it_does_not_cost_the_bonus_action(self):
        session, _ = fight(2)
        run(session, SURGE)
        self.assertFalse(economy.ensure(session)["player"]["bonus_action_spent"])
        with self.assertRaises(CombatRequestError) as caught:
            run(session, SURGE)
        self.assertEqual(caught.exception.code, "action_surge_uses_exhausted")

    def test_the_grant_expires_with_the_turn(self):
        session, _ = fight(2)
        run(session, SURGE)
        end_turn(session)
        self.assertEqual(economy.ensure(session)["player"]["additional_actions"], [])

    def test_surged_attack_action_has_the_extra_attack_at_five(self):
        session, npc = fight(5)
        with patch("game.roll_attack", return_value=1):
            run(session, attack(npc), follow(npc))
            run(session, SURGE)
            run(session, attack(npc), follow(npc))
            with self.assertRaises(CombatRequestError):
                run(session, follow(npc))
        self.assertEqual(attacks.sequence_snapshot(session, "player")["attacks"], 4)

    def test_saved_grant_and_use_round_trip(self):
        session, _ = fight(2)
        run(session, SURGE)
        fresh, _ = roundtrip(session)
        self.assertEqual(fresh.character["fighter_uses"]["action_surge_spent"], 1)
        self.assertEqual(economy.ensure(fresh)["player"]["additional_actions"], economy.ensure(session)["player"]["additional_actions"])

    def test_not_outside_the_own_combat_turn(self):
        session = created(2)
        self.assertEqual(features.projection(session)["action_surge"]["activate"]["reason"], "action_surge_current_combat_turn_required")


class TacticalShift(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(5)
        wound(self.session)
        self.speed = economy.speed(self.session, "player")

    def test_moves_up_to_half_speed_outside_the_ordinary_budget(self):
        half = self.speed // 2
        run(self.session, second_wind(distance_ft=half))
        r = economy.ensure(self.session)["player"]
        self.assertEqual(economy.movement_limit(self.session, "player") - r["movement_used"], self.speed)

    def test_more_than_half_is_refused_and_nothing_is_spent(self):
        before = self.session._capture_runtime_snapshot()
        with self.assertRaises(CombatRequestError) as caught:
            run(self.session, second_wind(distance_ft=self.speed // 2 + 5))
        self.assertEqual(caught.exception.code, "tactical_shift_out_of_range")
        self.assertEqual(self.session._capture_runtime_snapshot(), before)

    def test_no_allowance_remains_when_no_distance_was_asked(self):
        run(self.session, second_wind())
        self.assertEqual(economy.movement_limit(self.session, "player"), self.speed)

    def test_before_level_five_a_distance_is_refused(self):
        session, _ = fight(4)
        wound(session)
        with self.assertRaises(CombatRequestError) as caught:
            run(session, second_wind(distance_ft=5))
        self.assertEqual(caught.exception.code, "tactical_shift_not_available")


class TacticalMind(unittest.TestCase):
    """PDF 90: on a failed ability check, spend a Second Wind use to add 1d10; a check that still fails spends nothing."""

    def check(self, session, dc, d10=6, d20=5, skill="Acrobatics"):
        character = session.character
        evidence = []
        with patch("game.roll_d20", return_value=d20), patch.object(session.rng, "randint", return_value=d10) as rolled:
            result = session.perform_skill_check(skill, dc, character["modifiers"], character["proficient_skills"],
                                                 character["proficiency_bonus"], check_feature="tactical_mind", check_evidence=evidence)
        return result, evidence, rolled

    def plain_total(self, session, skill="Acrobatics"):
        character = session.character
        with patch("game.roll_d20", return_value=5):
            return session.perform_skill_check(skill, 10, character["modifiers"], character["proficient_skills"], character["proficiency_bonus"])["total"]

    def spent(self, session):
        return (session.character.get("fighter_uses") or {}).get("second_wind_spent", 0)

    def test_a_failed_check_that_the_d10_turns_into_a_success_spends_a_use(self):
        session = created(2)
        base = self.plain_total(session)
        result, evidence, rolled = self.check(session, base + 4, d10=6)
        rolled.assert_called_once_with(1, 10)
        self.assertEqual((result["total"], result["tactical_mind_roll"], result["resolution"]["outcome"]), (base + 6, 6, "SUCCESS"))
        self.assertEqual(result["result"], "BAŞARILI")
        self.assertEqual(self.spent(session), 1)
        self.assertEqual(len(evidence), 1)

    def test_a_check_that_still_fails_spends_nothing(self):
        session = created(2)
        base = self.plain_total(session)
        result, _, _ = self.check(session, base + 7, d10=6)
        self.assertEqual((result["total"], result["tactical_mind_roll"], result["resolution"]["outcome"]), (base + 6, 6, "FAILURE"))
        self.assertEqual(self.spent(session), 0)

    def test_a_check_that_succeeds_rolls_and_spends_nothing(self):
        session = created(2)
        result, _, rolled = self.check(session, self.plain_total(session))
        rolled.assert_not_called()
        self.assertIsNone(result["tactical_mind_roll"])
        self.assertEqual(self.spent(session), 0)

    def test_the_d10_replaces_the_healing(self):
        session = created(2)
        wound(session)
        hp = session.character["current_hp"]
        self.check(session, self.plain_total(session) + 4)
        self.assertEqual(session.character["current_hp"], hp)

    def test_it_shares_the_second_wind_pool(self):
        session = created(2)
        base = self.plain_total(session)
        self.check(session, base + 1)
        self.check(session, base + 1)
        self.assertEqual(features.projection(session)["second_wind"]["uses_remaining"], 0)
        self.assertEqual(features.projection(session)["tactical_mind"]["reason"], "tactical_mind_uses_exhausted")
        with self.assertRaises(CombatRequestError) as caught:
            self.check(session, base + 1)
        self.assertEqual(caught.exception.code, "tactical_mind_uses_exhausted")

    def test_it_needs_level_two_and_no_active_combat(self):
        with self.assertRaises(CombatRequestError) as caught:
            self.check(created(1), 30)
        self.assertEqual(caught.exception.code, "tactical_mind_not_available")
        self.assertIsNone(features.projection(created(1))["tactical_mind"])
        session, _ = fight(2)
        with self.assertRaises(CombatRequestError) as caught:
            self.check(session, 30)
        self.assertEqual(caught.exception.code, "tactical_mind_immediate_check_only")

    def test_a_failure_after_the_roll_restores_everything(self):
        session = created(2)
        base = self.plain_total(session)
        before = session._capture_runtime_snapshot()
        with patch.object(features, "record_tactical_mind", side_effect=ValueError("synthetic")), self.assertRaises(ValueError):
            self.check(session, base + 1)
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_annotation_refuses_a_result_that_does_not_match_the_evidence(self):
        session = created(2)
        dc = self.plain_total(session) + 4
        with resolution_action_scope("5df78dbd-3908-4a4d-bd91-1888fe1ccc0c"):
            result, evidence, _ = self.check(session, dc)
        action = {"action": "skill_check", "skill": result["skill"], "action_id": result["resolution"]["action_id"],
                  "resolution_id": result["resolution"]["resolution_id"], "resolution": result["resolution"], "tactical_mind_roll": 6}
        self.assertEqual(features.tactical_mind_annotation(evidence[0], action), {"check_feature": "tactical_mind", "tactical_mind_roll": 6})
        with self.assertRaises(ValueError):
            features.tactical_mind_annotation(evidence[0], {**action, "tactical_mind_roll": 7})
        with self.assertRaises(ValueError):
            features.tactical_mind_annotation(object(), action)


class ExtraAttack(unittest.TestCase):
    def test_applied_level_five_fighter_has_exactly_two_attacks(self):
        session, npc = fight(5)
        with patch("game.roll_attack", return_value=1):
            run(session, attack(npc), follow(npc))
            with self.assertRaises(CombatRequestError):
                run(session, follow(npc))

    def test_level_four_and_numeric_five_have_one(self):
        session = earned(self, 4)
        earn(session, 5)
        npc = start_combat(session)
        self.assertEqual(economy.attacks_per_action(session, "player"), 1)
        with patch("game.roll_attack", return_value=1):
            run(session, attack(npc))
            with self.assertRaises(CombatRequestError):
                run(session, follow(npc))

    def test_it_is_one_shared_owner(self):
        from class_progression.base import ClassProgression, EXTRA_ATTACK_ATTACKS
        from class_progression import barbarian, fighter
        self.assertEqual(EXTRA_ATTACK_ATTACKS, 2)
        self.assertIs(barbarian.EXTRA_ATTACK_ATTACKS, EXTRA_ATTACK_ATTACKS)
        for handler in (barbarian.HANDLER, fighter.HANDLER):
            self.assertIs(type(handler).attacks_per_attack_action, ClassProgression.attacks_per_attack_action)
            self.assertEqual(handler.extra_attack_level, 5)

    def test_a_subclass_mismatch_never_opens_it(self):
        session = created(5)
        session.character["subclass_id"] = "berserker"
        self.assertEqual(cp.attacks_per_attack_action(session.character), 1)


def weapon_session(style, level=1, weapon="longsword", off_hand=None, items=()):
    session, npc = fight(level, style=style)
    session.world_state["inventory"][:] = [weapon, *items]
    session.world_state["equipment"] = {"main_hand": weapon, "off_hand": off_hand}
    session.world_state["ammunition"] = {"arrow": 20, "arrows": 20}
    return session, npc


def swing(session, npc, roll=12, damage=None, **extra):
    with patch("game.roll_attack", return_value=roll):
        if damage is None:
            return run(session, attack(npc, **extra))[0]["result"]
        with patch.object(session, "roll_damage", side_effect=damage):
            return run(session, attack(npc, **extra))[0]["result"]


def fixed_rolls(values):
    def roll(die, count, modifier, rolls=None):
        rolls.extend(values[:count])
        return sum(values[:count]) + modifier
    return roll


class WeaponProficiency(unittest.TestCase):
    """PDF 90: a Fighter is proficient with Simple and Martial weapons."""

    def test_a_new_fighter_adds_proficiency_to_a_martial_and_a_simple_weapon(self):
        for weapon in ("greatsword", "dagger", "longbow"):
            session, npc = weapon_session("Defense", weapon=weapon)
            self.assertTrue(swing(session, npc)["proficiency_applied"], weapon)

    def test_every_start_keeps_the_grant_through_a_save(self):
        for level in (1, 3, 5):
            self.assertEqual(roundtrip(created(level))[0].character["weapon_proficiencies"], ["simple", "martial"])

    def test_a_fighter_save_without_the_key_reads_the_class_grant_and_keeps_its_record(self):
        """Repair at read time: a save from before the creation grant is neither refused nor rewritten."""
        session = created(2)
        del session.character["weapon_proficiencies"]
        fresh, payload = roundtrip(session)
        self.assertNotIn("weapon_proficiencies", payload["engine_save"]["player"])
        npc = start_combat(fresh)
        fresh.world_state["inventory"][:] = ["greatsword"]
        fresh.world_state["equipment"] = {"main_hand": "greatsword", "off_hand": None}
        self.assertTrue(swing(fresh, npc)["proficiency_applied"])
        self.assertNotIn("weapon_proficiencies", fresh.character)
        self.assertNotIn("weapon_proficiencies", fresh.serialize_game_state()["player"])

    def test_the_read_time_grant_does_not_depend_on_the_save_format(self):
        session, npc = weapon_session("Defense", weapon="dagger")
        del session.character["weapon_proficiencies"]
        session._persisted_engine_format = 3
        self.assertTrue(swing(session, npc)["proficiency_applied"])

    def test_a_stored_list_is_kept_exactly_even_an_empty_one(self):
        for stored, wanted in ((["longsword"], False), ([], False), (["greatsword"], True)):
            session, npc = weapon_session("Defense", weapon="greatsword")
            session.character["weapon_proficiencies"] = stored
            self.assertEqual(swing(session, npc)["proficiency_applied"], wanted, stored)
            self.assertEqual(session.character["weapon_proficiencies"], stored)

    def test_only_a_player_whose_class_declares_a_grant_reads_one(self):
        self.assertEqual(attacks.proficiencies("player", {"class": "Fighter"}), ["simple", "martial"])
        self.assertEqual(attacks.proficiencies("npc", {"class": "Fighter"}), [])
        for name in ("Barbarian", "Sorcerer", "Wizard", None):
            self.assertEqual(attacks.proficiencies("player", {"class": name}), ["longsword"], name)
        from class_progression import barbarian
        with patch.object(barbarian.HANDLER, "class_weapon_proficiencies", ("simple",)):
            self.assertEqual(attacks.proficiencies("player", {"class": "Barbarian"}), ["simple"])

    def test_the_disclosure_states_the_read_time_grant(self):
        pending = " ".join(cp.progression_disclosure("Fighter", 1)["pending"])
        self.assertIn("worked out at each attack", pending)
        self.assertNotIn("not inferred on load", pending)


class Styles(unittest.TestCase):
    def test_catalog_offers_only_styles_with_an_effect(self):
        from api.dnd_2024_rules import CLASS_DEFINITIONS
        offered = {style["id"] for style in CLASS_DEFINITIONS["Fighter"]["fighting_styles"]}
        self.assertEqual(offered, {"Archery", "Defense", "Dueling", "Great Weapon Fighting", "Two-Weapon Fighting"})
        self.assertEqual(offered, features.APPLIED_STYLES)

    def test_defense_raises_armor_class_only_in_armor(self):
        armored = created(style="Defense").character["armor_class"]
        other = created(style="Archery").character["armor_class"]
        self.assertEqual(armored, other + 1)

    def test_archery_adds_two_to_ranged_attacks_only(self):
        session, npc = weapon_session("Archery", weapon="longbow")
        result = swing(session, npc, roll=5)
        self.assertIn({"source": "fighting_style_archery", "value": 2}, result["attack_bonuses"])
        session, npc = weapon_session("Archery")
        self.assertFalse(swing(session, npc)["attack_bonuses"])
        session, npc = weapon_session("Defense", weapon="longbow")
        self.assertFalse(swing(session, npc)["attack_bonuses"])

    def test_dueling_adds_two_damage_with_one_melee_weapon_and_nothing_else_held(self):
        session, npc = weapon_session("Dueling")
        self.assertIn({"source": "fighting_style_dueling", "value": 2}, swing(session, npc)["damage_modifiers"])
        session, npc = weapon_session("Dueling", weapon="longbow")
        self.assertFalse(swing(session, npc)["damage_modifiers"])
        session, npc = weapon_session("Dueling", weapon="shortsword", off_hand="dagger", items=("dagger",))
        self.assertFalse(swing(session, npc)["damage_modifiers"])
        session, npc = weapon_session("Dueling")
        self.assertFalse(swing(session, npc, attack_choice={"grip": 2})["damage_modifiers"], "a two-handed grip is not one hand")

    def test_dueling_counts_other_weapons_not_filled_hands(self):
        """PDF 208 names no other weapons: a Shield or a grappled creature in the other hand does not cost the bonus."""
        session, npc = weapon_session("Dueling", off_hand="Shield", items=("Shield",))
        self.assertIn(DUELING, swing(session, npc)["damage_modifiers"])
        session, npc = weapon_session("Dueling")
        session.world_state["equipment"]["off_hand"] = f"grapple:{npc['id']}"
        self.assertIn(DUELING, swing(session, npc)["damage_modifiers"])

    def test_dueling_still_refuses_a_second_weapon_however_the_hand_names_it(self):
        session, npc = weapon_session("Dueling", weapon="dagger", off_hand="dagger", items=("dagger",))
        self.assertFalse(swing(session, npc)["damage_modifiers"], "two weapons of one type")
        session, npc = weapon_session("Dueling", off_hand="owned-dagger", items=({"item_id": "owned-dagger", "name": "Hançer", "weapon_id": "dagger"},))
        self.assertFalse(swing(session, npc)["damage_modifiers"], "an owned instance id is still a weapon")

    def test_a_thrown_melee_weapon_keeps_dueling_and_a_thrown_ranged_weapon_is_archery(self):
        """PDF 208 sets Dueling on a Melee weapon and Archery on Ranged weapons; PDF 213 Thrown leaves a Melee weapon a Melee weapon."""
        thrown = {"attack_choice": {"mode": "thrown"}}
        session, npc = weapon_session("Dueling", weapon="dagger")
        self.assertIn(DUELING, swing(session, npc, **thrown)["damage_modifiers"])
        session, npc = weapon_session("Dueling", weapon="dagger", off_hand="handaxe", items=("handaxe",))
        self.assertFalse(swing(session, npc, **thrown)["damage_modifiers"])
        session, npc = weapon_session("Dueling", weapon="dart")
        self.assertFalse(swing(session, npc, **thrown)["damage_modifiers"], "a Dart is a Ranged weapon")
        session, npc = weapon_session("Archery", weapon="dagger")
        self.assertFalse(swing(session, npc, **thrown)["attack_bonuses"], "a thrown Dagger is still a Melee weapon")
        session, npc = weapon_session("Archery", weapon="dart")
        self.assertIn({"source": "fighting_style_archery", "value": 2}, swing(session, npc, **thrown)["attack_bonuses"])

    def test_great_weapon_fighting_counts_one_and_two_as_three_in_two_hands(self):
        session, npc = weapon_session("Great Weapon Fighting", weapon="greatsword")
        result = swing(session, npc, damage=fixed_rolls([1, 6]))
        plain, other = weapon_session("Defense", weapon="greatsword")
        base = swing(plain, other, damage=fixed_rolls([1, 6]))
        self.assertEqual(result["damage"], base["damage"] + 2)
        self.assertEqual(result["damage_rolls"][0]["rolls"], [3, 6])
        self.assertEqual(result["damage_rolls"][0]["natural_rolls"], [1, 6])

    def test_great_weapon_fighting_needs_a_two_handed_grip(self):
        session, npc = weapon_session("Great Weapon Fighting")
        one = swing(session, npc, damage=fixed_rolls([2]), attack_choice={"grip": 1})
        self.assertEqual(one["damage_rolls"][0]["rolls"], [2])
        session, npc = weapon_session("Great Weapon Fighting")
        two = swing(session, npc, damage=fixed_rolls([2]), attack_choice={"grip": 2})
        self.assertEqual(two["damage_rolls"][0]["rolls"], [3])
        session, npc = weapon_session("Great Weapon Fighting", weapon="longbow")
        self.assertEqual(swing(session, npc, damage=fixed_rolls([2]))["damage_rolls"][0]["rolls"], [2])

    def test_two_weapon_fighting_adds_the_modifier_to_the_light_attack(self):
        def strike(style):
            session, npc = weapon_session(style, weapon="shortsword", off_hand="dagger", items=("dagger",))
            session.character["dexterity_mod"] = 3
            session.character["strength_mod"] = 3
            with patch("game.roll_attack", return_value=12), patch.object(session, "roll_damage", side_effect=fixed_rolls([1])):
                run(session, attack(npc))
                return run(session, attack(npc, weapon_id="dagger", attack_origin="light", resource="bonus"))[0]["result"]["damage"]
        self.assertEqual(strike("Two-Weapon Fighting"), strike("Defense") + 3)

    def test_styles_do_not_reach_another_class(self):
        session, _ = weapon_session("Archery", weapon="longbow")
        session.character["class"] = "Barbarian"
        self.assertIsNone(features.style(session.character))


class Champion(unittest.TestCase):
    def test_nineteen_that_hits_is_a_critical_hit_from_level_three(self):
        for level, wanted in ((2, False), (3, True), (5, True)):
            session, npc = weapon_session("Defense", level=level)
            self.assertEqual(swing(session, npc, roll=19)["critical"], wanted, level)

    def test_nineteen_that_misses_stays_a_miss(self):
        session, npc = weapon_session("Defense", level=3)
        npc["armor_class"] = 40
        result = swing(session, npc, roll=19)
        self.assertEqual((result["hit"], result["critical"]), (False, False))

    def test_natural_twenty_still_hits_any_armor_class(self):
        session, npc = weapon_session("Defense", level=3)
        npc["armor_class"] = 40
        self.assertTrue(swing(session, npc, roll=20)["critical"])

    def test_numeric_level_three_without_the_applied_subclass_has_no_critical(self):
        session = earned(self, 2)
        earn(session, 3)
        self.assertEqual(features.critical_threshold(session.character), 20)

    def test_initiative_has_advantage(self):
        session = created(3)
        self.assertIn("remarkable_athlete", initiative.settings(session, "player")["advantage_sources"])
        self.assertNotIn("remarkable_athlete", initiative.settings(created(2), "player")["advantage_sources"])

    def test_strength_athletics_has_advantage_only(self):
        session = created(3)
        self.assertTrue(features.remarkable_athlete_check(session.character, "Athletics", "strength"))
        self.assertFalse(features.remarkable_athlete_check(session.character, "Acrobatics", "dexterity"))
        self.assertFalse(features.remarkable_athlete_check(created(2).character, "Athletics", "strength"))
        args = ("Athletics", 15, session.character["modifiers"], session.character["proficient_skills"], session.character["proficiency_bonus"])
        self.assertTrue(session.perform_skill_check(*args)["advantage"])

    def test_critical_move_stays_pending_and_disclosed(self):
        self.assertIn("Remarkable Athlete: the half-Speed move after a Critical Hit", " ".join(cp.progression_effects_pending("Fighter", 3)))

    def test_level_two_discloses_the_tactical_mind_scope(self):
        supported = " ".join(cp.progression_disclosure("Fighter", 2)["supported"])
        self.assertIn("Tactical Mind", supported)
        self.assertIn("shares the Second Wind uses", supported)
        self.assertNotIn("Tactical Mind", " ".join(cp.progression_disclosure("Fighter", 1)["supported"]))


if __name__ == "__main__":
    unittest.main()
