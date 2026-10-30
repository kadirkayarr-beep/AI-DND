"""Monk 1-5 effects through the existing owners: Martial Arts, Unarmored Movement, Focus, Stunning Strike, Deflect Attacks, Open Hand.

Numbers were read from the page renders (PHB 2024 PDF 100/101/102/106): Martial Arts die d6 at 1-4, d8 at 5; Focus Points 2/3/4/5 at
2-5, regained on a Short or Long Rest; save DC 8 + WIS + PB; Flurry 1 point for two Unarmed Strikes; Uncanny Metabolism Martial Arts
die + Monk level, once per Long Rest; Deflect 1d10 + DEX + level, redirect 1 point and two Martial Arts dice + DEX within 5 or 60 ft;
Unarmored Movement +10; Open Hand Push 15 ft. Dice are deterministic; synthetic NPCs are unit fixtures.
"""
import copy
import unittest
from unittest.mock import patch

import action_economy as economy
import character_progression as cp
import game
import monk_features as features
import weapon_attack as attacks
from combat_lifecycle import CombatRequestError
from api.tests.test_roadmap_c15_monk import created, earn, earned, roundtrip, spec
from api.tests.test_roadmap_c10_extra_attack import attack, follow, start_combat


def fight(level=1, **kwargs):
    session = created(level, **kwargs)
    return session, start_combat(session)


def run(session, *steps):
    return economy.execute(session, {"steps": list(steps)})["action_economy_result"]["steps"]


def code(session, *steps):
    before = copy.deepcopy(session.character)
    with session_failure() as caught:
        run(session, *steps)
    assert session.character == before
    return caught.exception.code


class session_failure:
    exception = None

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        assert kind is not None and issubclass(kind, CombatRequestError), kind
        self.exception = value
        return True


def unarmed(npc, **extra):
    return attack(npc, weapon_id="unarmed", **extra)


def bonus_strike(npc, **extra):
    return {"kind": "martial_arts_strike", "target_id": npc["id"], **extra}


def flurry(npc, **extra):
    return {"kind": "flurry_of_blows", "target_id": npc["id"], **extra}


def flurry_strike(npc, **extra):
    return {"kind": "flurry_strike", "target_id": npc["id"], **extra}


def hit(session, *steps, roll=15, damage=None):
    """Run steps with a fixed attack roll; `damage` fixes each die so damage is literal."""
    with patch("game.roll_attack", return_value=roll):
        if damage is None:
            return run(session, *steps)
        with patch.object(session.rng, "randint", return_value=damage):
            return run(session, *steps)


def focus(session):
    return session.character.get("monk_state", {}).get("focus_spent", 0)


def enemy_turn(session, npc):
    combat = session.world_state["combat"]
    combat["current_actor_id"] = npc["id"]
    combat["current_turn_index"] = combat["initiative_order"].index(npc["id"])


def end_turn(session):
    with patch("game.roll_attack", return_value=1), patch("game.roll_d20", return_value=1):
        run(session, {"kind": "end_turn"})


CLAW = {"weapon_id": "unit_claw", "name": "Claw", "kind": "melee", "category": None, "properties": [], "mastery": None,
        "damage_die": 8, "damage_dice": 1, "fixed_damage": None, "damage_type": "slashing", "magic_attack_bonus": 0,
        "magic_damage_bonus": 0, "attack_bonus": 20, "damage_modifier": 6}


class MartialArts(unittest.TestCase):
    def test_unarmed_strike_rolls_the_die_with_dexterity_for_attack_and_damage(self):
        session, npc = fight(1)
        session.world_state["equipment"].update(main_hand=None)
        result = hit(session, unarmed(npc), damage=4)[0]["result"]
        self.assertEqual(result["ability_used"], "dexterity")
        self.assertEqual(result["attack_bonus"], 3 + 2)
        self.assertEqual(result["damage_rolls"][0]["die"], 6)
        self.assertEqual(result["raw_damage"], 4 + 3)

    def test_level_five_die_is_d8_and_xp_alone_does_not_raise_it(self):
        session, npc = fight(5)
        session.world_state["equipment"].update(main_hand=None)
        self.assertEqual(hit(session, unarmed(npc), damage=4)[0]["result"]["damage_rolls"][0]["die"], 8)
        pending = created(1)
        earn(pending, 5)
        npc = start_combat(pending)
        pending.world_state["equipment"].update(main_hand=None)
        self.assertEqual(hit(pending, unarmed(npc), damage=4)[0]["result"]["damage_rolls"][0]["die"], 6)

    def test_a_monk_weapon_uses_the_larger_die_and_dexterous_attacks(self):
        session, npc = fight(1)
        session.world_state["inventory"].append("Sickle")
        session.world_state["equipment"].update(main_hand="sickle")
        result = hit(session, attack(npc), damage=4)[0]["result"]
        self.assertEqual((result["weapon_id"], result["ability_used"], result["damage_rolls"][0]["die"]), ("sickle", "dexterity", 6))

    def test_a_weapon_die_above_the_martial_arts_die_stays(self):
        session, npc = fight(1)
        session.world_state["inventory"].append("Greatclub")
        session.world_state["equipment"].update(main_hand="greatclub")
        self.assertEqual(hit(session, attack(npc), damage=4)[0]["result"]["damage_rolls"][0]["die"], 8)

    def test_strength_is_still_allowed_when_it_is_the_better_score(self):
        session, npc = fight(1)
        session.character.update(strength=18, strength_mod=4)
        session.world_state["equipment"].update(main_hand=None)
        self.assertEqual(hit(session, unarmed(npc), damage=4)[0]["result"]["ability_used"], "strength")
        session, npc = fight(1)
        session.world_state["equipment"].update(main_hand=None)
        chosen = hit(session, unarmed(npc, attack_choice={"ability": "strength"}), damage=4)[0]["result"]
        self.assertEqual(chosen["ability_used"], "strength")

    def test_a_non_monk_weapon_in_hand_turns_the_benefits_off(self):
        session, npc = fight(1)
        session.world_state["inventory"].append("Longsword")
        session.world_state["equipment"].update(main_hand="longsword")
        result = hit(session, unarmed(npc), damage=4)[0]["result"]
        self.assertEqual((result["ability_used"], result["damage_rolls"]), ("strength", []))
        self.assertEqual(result["raw_damage"], 1 + 1)

    def test_a_martial_weapon_without_light_is_not_proficient_and_a_light_one_is(self):
        session = created(1)
        self.assertEqual(attacks.proficiencies("player", session.character), ["simple", "scimitar", "shortsword", "hand_crossbow"])

    def test_a_dart_is_not_a_monk_weapon_and_a_javelin_is(self):
        from weapon_catalog import lookup
        self.assertFalse(features.monk_weapon(lookup("Dart")))
        self.assertTrue(features.monk_weapon(lookup("Javelin")))
        self.assertTrue(features.monk_weapon(lookup("Shortsword")))
        self.assertFalse(features.monk_weapon(lookup("Hand Crossbow")))
        self.assertFalse(features.monk_weapon(lookup("Rapier")))

    def test_grapple_and_shove_use_dexterity_for_the_save_dc(self):
        session, npc = fight(1)
        session.world_state["equipment"].update(main_hand=None)
        with patch.object(attacks, "save", wraps=attacks.save) as save:
            hit(session, unarmed(npc, attack_choice={"unarmed_option": "shove"}))
        self.assertEqual(save.call_args.args[3], 8 + 3 + 2)

    def test_a_save_without_the_proof_that_carries_armor_has_no_benefits(self):
        session, npc = fight(1)
        session.world_state.pop("worn_armor_v1")
        session.world_state["equipment"].update(main_hand=None)
        session.world_state["inventory"].append("Chain Mail")
        self.assertFalse(features.martial_arts_ready(session))
        self.assertEqual(hit(session, unarmed(npc), damage=4)[0]["result"]["ability_used"], "strength")

    def test_another_class_is_untouched(self):
        import api.tests.test_roadmap_c14_fighter as fighter
        session = fighter.created(1)
        npc = start_combat(session)
        session.world_state["equipment"].update(main_hand=None)
        result = hit(session, unarmed(npc), damage=4)[0]["result"]
        self.assertEqual((result["ability_used"], result["damage_rolls"]), ("strength", []))


class BonusUnarmedStrike(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(1)
        self.session.world_state["equipment"].update(main_hand=None)

    def test_it_spends_only_the_bonus_action(self):
        result = hit(self.session, bonus_strike(self.npc), damage=4)[0]["result"]
        self.assertEqual(result["attack"]["attack_origin"], "martial_arts")
        resources = economy.ensure(self.session)["player"]
        self.assertTrue(resources["bonus_action_spent"])
        self.assertFalse(resources["base_action_spent"])

    def test_it_works_with_the_attack_action_on_the_same_turn(self):
        hit(self.session, unarmed(self.npc), damage=4)
        hit(self.session, bonus_strike(self.npc), damage=4)
        self.assertTrue(economy.ensure(self.session)["player"]["base_action_spent"])
        self.assertEqual(attacks.sequence_snapshot(self.session, "player")["attacks"], 2)

    def test_one_bonus_action_a_turn(self):
        hit(self.session, bonus_strike(self.npc))
        self.assertEqual(code(self.session, bonus_strike(self.npc)), "bonus_action_spent")

    def test_only_on_your_own_turn_and_while_able(self):
        self.session.character.setdefault("conditions", []).append("stunned")
        self.assertEqual(code(self.session, bonus_strike(self.npc)), "martial_arts_strike_incapacitated")

    def test_a_non_monk_weapon_in_hand_refuses_it(self):
        self.session.world_state["inventory"].append("Longsword")
        self.session.world_state["equipment"].update(main_hand="longsword")
        self.assertEqual(code(self.session, bonus_strike(self.npc)), "martial_arts_conditions_not_met")

    def test_another_class_cannot_use_it(self):
        import api.tests.test_roadmap_c14_fighter as fighter
        session = fighter.created(1)
        npc = start_combat(session)
        self.assertEqual(code(session, bonus_strike(npc)), "martial_arts_not_available")

    def test_range_is_the_attack_owner(self):
        session, npc = fight(1)
        session.world_state["equipment"].update(main_hand=None)
        npc["distance_ft"] = 30
        self.assertEqual(code(session, bonus_strike(npc)), "out_of_range")


class Focus(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(2)
        self.session.world_state["equipment"].update(main_hand=None)

    def test_flurry_spends_one_point_and_the_bonus_action_for_two_strikes(self):
        first = hit(self.session, flurry(self.npc), damage=4)[0]["result"]
        self.assertEqual((focus(self.session), first["strikes_remaining"]), (1, 1))
        self.assertEqual(first["attack"]["attack_origin"], "flurry")
        self.assertTrue(economy.ensure(self.session)["player"]["bonus_action_spent"])
        second = hit(self.session, flurry_strike(self.npc), damage=4)[0]["result"]
        self.assertEqual((focus(self.session), second["strikes_remaining"]), (1, 0))
        self.assertEqual(code(self.session, flurry_strike(self.npc)), "flurry_strike_unavailable")

    def test_flurry_is_a_focus_feature_and_needs_no_martial_arts_conditions(self):
        self.session.world_state["inventory"].append("Longsword")
        self.session.world_state["equipment"].update(main_hand="longsword")
        self.assertFalse(features.martial_arts_ready(self.session))
        self.assertTrue(features.projection(self.session)["flurry_of_blows"]["available"])
        result = hit(self.session, flurry(self.npc), damage=4)[0]["result"]
        self.assertEqual((focus(self.session), result["attack"]["ability_used"]), (1, "strength"))

    def test_the_second_strike_lapses_with_the_turn(self):
        hit(self.session, flurry(self.npc))
        end_turn(self.session)
        self.assertEqual(code(self.session, flurry_strike(self.npc)), "flurry_strike_unavailable")

    def test_the_second_strike_survives_a_save_and_a_load(self):
        hit(self.session, flurry(self.npc))
        fresh, _ = roundtrip(self.session)
        fresh.commit_location_change("tavern")
        self.assertEqual(hit(fresh, flurry_strike(self.npc), damage=4)[0]["result"]["strikes_remaining"], 0)

    def test_no_focus_refuses_and_changes_nothing(self):
        self.session.character["monk_state"] = {"focus_spent": 2, "metabolism_spent": False, "deflect": "reduce"}
        self.assertEqual(code(self.session, flurry(self.npc)), "focus_points_exhausted")
        self.assertFalse(economy.ensure(self.session)["player"]["bonus_action_spent"])

    def test_level_one_has_no_focus(self):
        session, npc = fight(1)
        session.world_state["equipment"].update(main_hand=None)
        self.assertEqual(code(session, flurry(npc)), "focus_not_available")

    def test_a_refused_strike_refunds_the_point(self):
        self.npc["distance_ft"] = 30
        self.assertEqual(code(self.session, flurry(self.npc)), "out_of_range")
        self.assertEqual(focus(self.session), 0)

    def test_patient_defense_free_is_disengage_and_paid_adds_dodge(self):
        resources = economy.ensure(self.session)["player"]
        hit(self.session, {"kind": "patient_defense"})
        self.assertEqual((resources.get("disengaging"), resources.get("dodging"), focus(self.session)), (True, None, 0))
        session, _ = fight(2)
        hit(session, {"kind": "patient_defense", "spend_focus": True})
        resources = economy.ensure(session)["player"]
        self.assertEqual((resources.get("disengaging"), resources.get("dodging"), focus(session)), (True, True, 1))
        self.assertTrue(resources["bonus_action_spent"])

    def test_patient_defense_gives_disadvantage_through_the_dodge_owner(self):
        hit(self.session, {"kind": "patient_defense", "spend_focus": True})
        environment = self.session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})
        environment[f"{self.npc['id']}|player"] = {"distance_ft": 5, "target_sees_attacker": True, "attacker_sees_target": True}
        enemy_turn(self.session, self.npc)
        view = attacks.prepare(self.session, self.npc["id"], "player", profile=CLAW)
        self.assertIn("target_dodging", view["disadvantage_sources"])

    def test_step_of_the_wind_free_is_dash_and_paid_adds_disengage(self):
        speed = economy.speed(self.session, "player")
        result = hit(self.session, {"kind": "step_of_the_wind"})[0]["result"]
        resources = economy.ensure(self.session)["player"]
        self.assertEqual((result["movement_added_ft"], resources["dash_count"], resources.get("disengaging")), (speed, 1, None))
        self.assertEqual(economy.movement_limit(self.session, "player"), 2 * speed)
        self.assertFalse(resources["base_action_spent"])
        session, _ = fight(2)
        hit(session, {"kind": "step_of_the_wind", "spend_focus": True})
        self.assertEqual((economy.ensure(session)["player"].get("disengaging"), focus(session)), (True, 1))

    def test_step_of_the_wind_never_spends_an_orc_adrenaline_rush(self):
        request = spec()
        request.update(species="Orc", race="Orc", proficient_skills=["Acrobatics", "Insight", "Sleight of Hand", "Stealth"])
        session = created(2, request=request)
        start_combat(session)
        uses = session.character["species_trait_state"]["adrenaline_rush_uses_remaining"]
        hit(session, {"kind": "step_of_the_wind"})
        self.assertEqual(session.character["species_trait_state"]["adrenaline_rush_uses_remaining"], uses)

    def test_one_bonus_action_across_the_features(self):
        hit(self.session, {"kind": "patient_defense"})
        for step in ({"kind": "step_of_the_wind"}, flurry(self.npc), bonus_strike(self.npc)):
            self.assertEqual(code(self.session, step), "bonus_action_spent", step)

    def test_short_and_long_rest_regain_all_points_through_the_rest_owner(self):
        for kind in ("short_rest", "long_rest"):
            session = created(2)
            session.character["monk_state"] = {"focus_spent": 2, "metabolism_spent": True, "deflect": "off"}
            cp.rest_recovery(session, kind)
            self.assertEqual(session.character["monk_state"], {"focus_spent": 0, "metabolism_spent": kind == "short_rest", "deflect": "off"})

    def test_a_real_long_rest_runs_the_recovery(self):
        session = created(2)
        session.character["monk_state"] = {"focus_spent": 2, "metabolism_spent": True, "deflect": "reduce"}
        session.character["current_hp"] = 1
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(session.character["monk_state"]["focus_spent"], 0)
        self.assertFalse(session.character["monk_state"]["metabolism_spent"])

    def test_save_dc_is_eight_plus_wisdom_plus_proficiency(self):
        self.assertEqual(features.save_dc(self.session.character), 8 + 2 + 2)

    def test_steps_must_be_exact_and_alone(self):
        for command in ({"steps": [{"kind": "patient_defense", "target_id": "x"}]}, {"steps": [{"kind": "flurry_of_blows"}]},
                        {"steps": [{"kind": "step_of_the_wind", "spend_focus": 1}]},
                        {"steps": [{"kind": "patient_defense"}, {"kind": "end_turn"}]}):
            with self.assertRaises(CombatRequestError) as caught:
                economy.execute(self.session, command)
            self.assertEqual(caught.exception.code, "invalid_monk_command", command)


class UnarmoredMovement(unittest.TestCase):
    def test_the_bonus_reaches_the_speed_owner_at_the_applied_level_only(self):
        session = created(1)
        base = economy.speed(session, "player")
        earn(session, 2)
        self.assertEqual(economy.speed(session, "player"), base)
        cp.apply_level_choices(session, cp.preview_level_up(session, 2), {})
        self.assertEqual(economy.speed(session, "player"), base + 10)

    def test_the_bonus_needs_the_unarmored_fact(self):
        session = created(2)
        base = economy.speed(session, "player")
        session.world_state.pop("worn_armor_v1")
        session.world_state["inventory"].append("Shield")
        self.assertEqual(economy.speed(session, "player"), base - 10)


class UncannyMetabolism(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(3)
        self.session.character.update(max_hp=40, current_hp=10)
        self.session.character["monk_state"] = {"focus_spent": 3, "metabolism_spent": False, "deflect": "reduce"}

    def test_it_regains_all_focus_and_heals_die_plus_applied_level(self):
        with patch.object(self.session.rng, "randint", return_value=5) as rolled:
            result = run(self.session, {"kind": "uncanny_metabolism"})[0]["result"]
        rolled.assert_called_once_with(1, 6)
        self.assertEqual((result["roll"], result["healing"], focus(self.session)), (5, 8, 0))
        self.assertEqual(self.session.character["current_hp"], 18)
        self.assertEqual(economy.ensure(self.session)["player"]["bonus_action_spent"], False)

    def test_once_until_a_long_rest(self):
        run(self.session, {"kind": "uncanny_metabolism"})
        self.assertEqual(code(self.session, {"kind": "uncanny_metabolism"}), "uncanny_metabolism_used")
        cp.rest_recovery(self.session, "short_rest")
        self.assertEqual(code(self.session, {"kind": "uncanny_metabolism"}), "uncanny_metabolism_used")
        cp.rest_recovery(self.session, "long_rest")
        run(self.session, {"kind": "uncanny_metabolism"})

    def test_the_window_closes_after_the_first_round(self):
        self.session.world_state["combat"]["round"] = 2
        self.assertEqual(code(self.session, {"kind": "uncanny_metabolism"}), "uncanny_metabolism_initiative_only")

    def test_level_one_has_none(self):
        session, _ = fight(1)
        self.assertEqual(code(session, {"kind": "uncanny_metabolism"}), "uncanny_metabolism_not_available")


class EnemyAttack(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(3)
        self.session.character.update(max_hp=60, current_hp=60)
        self.npc.update(damage_die=8, damage_dice=1, damage_modifier=6, attack_bonus=20)

    def enemy(self, *, session=None, npc=None, damage=8, reaction=4, save=1):
        session, npc = session or self.session, npc or self.npc
        with patch("game.roll_d20", side_effect=[15, save, save]), \
                patch.object(session.rng, "randint", side_effect=lambda low, high: reaction if high == 10 else damage):
            enemy_turn(session, npc)
            return attacks.resolve(session, npc["id"], "player", profile=self.profile())

    def profile(self):
        return dict(CLAW)

    def set_mode(self, mode, session=None):
        session = session or self.session
        run(session, {"kind": "set_deflect_attacks", "deflect_mode": mode})

    def test_deflect_reduces_by_die_plus_dexterity_plus_level_and_spends_the_reaction(self):
        result = self.enemy(damage=8, reaction=4)
        deflect = next(e for e in result["additional_effects"] if e["kind"] == "deflect_attacks")
        self.assertEqual((deflect["roll"], deflect["reduction"]), (4, 4 + 3 + 3))
        self.assertEqual(result["damage"], 14 - 10)
        self.assertEqual(self.session.character["current_hp"], 56)
        self.assertTrue(economy.ensure(self.session)["player"]["reaction_spent"])

    def test_it_needs_a_reaction_and_stays_out_of_a_readied_one(self):
        economy.ensure(self.session)["player"]["reaction_spent"] = True
        self.assertEqual(self.enemy()["damage"], 14)
        session, npc = fight(3)
        session.character.update(max_hp=60, current_hp=60)
        economy.ensure(session)["player"]["ready"] = {"trigger": {"event": "actor_attacks", "actor_id": npc["id"]},
                                                      "response": {"kind": "move", "distance_ft": 5}, "spell_metadata": None}
        self.assertEqual(self.enemy(session=session, npc=npc)["damage"], 14)

    def test_the_off_setting_declines_it(self):
        self.set_mode("off")
        self.assertEqual(self.enemy()["damage"], 14)
        self.assertFalse(economy.ensure(self.session)["player"]["reaction_spent"])

    def test_other_damage_types_are_not_deflected(self):
        profile = self.profile()
        profile["damage_type"] = "fire"
        with patch.object(self, "profile", return_value=profile):
            self.assertEqual(self.enemy()["damage"], 14)

    def test_a_miss_is_not_deflected(self):
        with patch("game.roll_d20", return_value=1):
            enemy_turn(self.session, self.npc)
            result = attacks.resolve(self.session, self.npc["id"], "player", profile={**self.profile(), "attack_bonus": -50})
        self.assertFalse(result["hit"])
        self.assertFalse(economy.ensure(self.session)["player"]["reaction_spent"])

    def test_level_two_has_no_deflect(self):
        session, npc = fight(2)
        session.character.update(max_hp=60, current_hp=60)
        self.assertEqual(self.enemy(session=session, npc=npc)["damage"], 14)

    def test_incapacitated_cannot_deflect(self):
        self.session.character.setdefault("conditions", []).append("stunned")
        self.assertEqual(self.enemy()["damage"], 14)

    def test_redirect_needs_zero_damage_spends_a_point_and_rolls_two_dice_plus_dexterity(self):
        self.set_mode("redirect")
        hp = self.npc["current_hp"]
        result = self.enemy(damage=5, reaction=9)
        self.assertEqual(result["damage"], 0)
        effect = next(e for e in result["additional_effects"] if e["kind"] == "deflect_redirect")
        self.assertEqual((effect["save"]["outcome"], effect["damage"], effect["damage_type"], focus(self.session)),
                         ("FAILURE", 5 + 5 + 3, "slashing", 1))
        self.assertEqual(effect["save"]["dc"], 8 + 2 + 2)
        self.assertEqual(self.npc["current_hp"], hp - 13)

    def test_redirect_does_not_happen_above_zero_or_on_the_reduce_setting(self):
        self.set_mode("redirect")
        self.assertFalse([e for e in self.enemy(damage=8, reaction=1)["additional_effects"] if e["kind"] == "deflect_redirect"])
        self.assertEqual(focus(self.session), 0)
        session, npc = fight(3)
        session.character.update(max_hp=60, current_hp=60)
        self.assertFalse([e for e in self.enemy(session=session, npc=npc, damage=5, reaction=9)["additional_effects"] if e["kind"] == "deflect_redirect"])

    def test_a_successful_save_takes_no_damage_and_the_point_is_spent(self):
        self.set_mode("redirect")
        hp = self.npc["current_hp"]
        result = self.enemy(damage=5, reaction=9, save=20)
        effect = next(e for e in result["additional_effects"] if e["kind"] == "deflect_redirect")
        self.assertEqual((effect["save"]["outcome"], effect["damage"], focus(self.session)), ("SUCCESS", 0, 1))
        self.assertEqual(self.npc["current_hp"], hp)

    def test_a_melee_attacker_beyond_five_feet_is_not_a_redirect_target(self):
        self.set_mode("redirect")
        self.npc["distance_ft"] = 5
        pairs = self.session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})
        profile = {**self.profile(), "properties": ["reach"]}
        pairs[f"{self.npc['id']}|player"] = {"distance_ft": 10}
        with patch.object(self, "profile", return_value=profile):
            result = self.enemy(damage=5, reaction=9)
        self.assertFalse([e for e in result["additional_effects"] if e["kind"] == "deflect_redirect"])

    def test_a_redirect_with_no_focus_left_stays_a_reduction(self):
        self.set_mode("redirect")
        self.session.character["monk_state"]["focus_spent"] = 3
        result = self.enemy(damage=5, reaction=9)
        self.assertEqual(result["damage"], 0)
        self.assertFalse([e for e in result["additional_effects"] if e["kind"] == "deflect_redirect"])

    def test_a_lethal_redirect_ends_the_combat_through_the_owner(self):
        self.set_mode("redirect")
        self.npc["current_hp"] = 3
        self.session.character["monk_state"] = {"focus_spent": 0, "metabolism_spent": False, "deflect": "redirect"}
        with patch("game.roll_d20", side_effect=[15, 1, 1]), \
                patch.object(self.session.rng, "randint", side_effect=lambda low, high: 9 if high == 10 else 5):
            enemy_turn(self.session, self.npc)
            attacks.resolve(self.session, self.npc["id"], "player", profile=self.profile())
            self.session._combat_end_if_decided()
        self.assertFalse(self.session.world_state["combat"]["active"])
        self.assertEqual(self.session.world_state["attack_effects"] if "attack_effects" in self.session.world_state else [], [])

    def test_the_setting_is_validated_and_kept(self):
        self.set_mode("redirect")
        self.assertEqual(roundtrip(self.session)[0].character["monk_state"]["deflect"], "redirect")
        self.assertEqual(code(self.session, {"kind": "set_deflect_attacks", "deflect_mode": "always"}), "invalid_monk_command")
        session, _ = fight(2)
        self.assertEqual(code(session, {"kind": "set_deflect_attacks", "deflect_mode": "off"}), "deflect_attacks_not_available")


class StunningStrike(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(5)
        self.session.world_state["equipment"].update(main_hand=None)
        self.npc["constitution_mod"] = 0

    def strike(self, save=1, **extra):
        with patch("game.roll_d20", return_value=save):
            return hit(self.session, unarmed(self.npc, stunning_strike=True, **extra), damage=2)[0]["result"]

    def effect(self, result):
        return next(e for e in result["additional_effects"] if e["kind"] == "stunning_strike")

    def test_a_failed_save_stuns_and_spends_one_point(self):
        effect = self.effect(self.strike(save=1))
        self.assertEqual((effect["save"]["outcome"], effect["save"]["dc"], effect["outcome"], focus(self.session)),
                         ("FAILURE", 8 + 2 + 3, "stunned", 1))
        self.assertIn("stunned", self.npc["conditions"])

    def test_the_stun_stops_the_turn_and_ends_at_the_start_of_your_next_turn(self):
        self.strike(save=1)
        self.assertFalse(economy.can_act(self.session, self.npc["id"]))
        hp = self.session.character["current_hp"]
        end_turn(self.session)
        self.assertEqual(self.session.character["current_hp"], hp, "a stunned creature does not act")
        self.assertEqual(self.session.world_state["combat"]["current_actor_id"], "player")
        self.assertNotIn("stunned", self.npc.get("conditions", []))
        self.assertFalse([e for e in self.session.world_state["attack_effects"] if e["kind"].startswith("stunning")])

    def test_a_stun_the_target_already_had_outlives_the_strike(self):
        self.npc.setdefault("conditions", []).append("stunned")
        self.strike(save=1)
        end_turn(self.session)
        self.assertIn("stunned", self.npc["conditions"])

    def test_the_stun_ends_with_the_combat(self):
        self.strike(save=1)
        self.session.end_combat("target_defeated")
        self.assertNotIn("stunned", self.npc.get("conditions", []))

    def test_stunned_gives_attackers_advantage_and_fails_strength_and_dexterity_saves(self):
        self.strike(save=1)
        view = attacks.preview(self.session, "player", self.npc["id"], "unarmed", {}, origin="continuation")
        self.assertIn("target_stunned", view["advantage_sources"])
        self.assertTrue(attacks.save(self.session, self.npc["id"], ("dexterity",), 5)["automatic_failure"])

    def test_a_successful_save_halves_speed_and_opens_the_next_attack(self):
        self.npc["speed_ft"] = 30
        effect = self.effect(self.strike(save=20))
        self.assertEqual((effect["outcome"], focus(self.session)), ("resisted", 1))
        self.assertEqual(economy.speed(self.session, self.npc["id"]), 15)
        view = attacks.preview(self.session, "player", self.npc["id"], "unarmed", {}, origin="continuation")
        self.assertIn("stunning_strike_opening", view["advantage_sources"])
        hit(self.session, {"kind": "continue_attack", "target_id": self.npc["id"], "weapon_id": "unarmed"}, damage=2)
        view = attacks.preview(self.session, "player", self.npc["id"], "unarmed", {}, origin="martial_arts")
        self.assertNotIn("stunning_strike_opening", view["advantage_sources"], "only the next attack roll")
        self.assertEqual(economy.speed(self.session, self.npc["id"]), 15, "the Speed effect stays")
        end_turn(self.session)
        self.assertEqual(economy.speed(self.session, self.npc["id"]), 30)

    def test_once_per_turn_on_the_same_turn_and_again_on_the_next(self):
        self.strike(save=20)
        self.assertEqual(code(self.session, {"kind": "continue_attack", "target_id": self.npc["id"], "weapon_id": "unarmed", "stunning_strike": True}),
                         "stunning_strike_used_this_turn")
        end_turn(self.session)
        self.strike(save=20)
        self.assertEqual(focus(self.session), 2)

    def test_a_miss_spends_nothing(self):
        with patch("game.roll_d20", return_value=1):
            result = hit(self.session, unarmed(self.npc, stunning_strike=True), roll=1)[0]["result"]
        self.assertFalse(result["hit"])
        self.assertEqual(focus(self.session), 0)
        self.assertFalse(economy.ensure(self.session)["player"]["weapon_sequence"].get("stunning_strike_turn"))

    def test_it_needs_level_five_focus_and_a_monk_weapon(self):
        session, npc = fight(4)
        session.world_state["equipment"].update(main_hand=None)
        self.assertEqual(code(session, unarmed(npc, stunning_strike=True)), "stunning_strike_not_available")
        self.session.character["monk_state"] = {"focus_spent": 5, "metabolism_spent": False, "deflect": "reduce"}
        self.assertEqual(code(self.session, unarmed(self.npc, stunning_strike=True)), "focus_points_exhausted")
        session, npc = fight(5)
        session.world_state["inventory"].append("Shortbow")
        session.world_state["equipment"].update(main_hand="shortbow")
        session.world_state["ammunition"] = {"arrow": 5}
        self.assertEqual(code(session, attack(npc, stunning_strike=True)), "stunning_strike_weapon_required")

    def test_a_grapple_or_shove_is_not_a_hit(self):
        self.assertEqual(code(self.session, unarmed(self.npc, stunning_strike=True, attack_choice={"unarmed_option": "shove"})),
                         "stunning_strike_weapon_required")

    def test_a_defeated_target_makes_no_save_and_costs_nothing(self):
        self.npc["current_hp"] = 1
        self.strike(save=1)
        self.assertEqual(focus(self.session), 0)

    def test_the_timed_effects_survive_a_load_and_a_forged_one_is_refused(self):
        self.strike(save=1)
        fresh, payload = roundtrip(self.session)
        self.assertEqual([e["kind"] for e in fresh.world_state["attack_effects"]], ["stunning_strike_stun"])
        for change in (lambda e: e.update(expires_turn=99), lambda e: e.update(source_actor="other"), lambda e: e.update(extra=1),
                       lambda e: e.update(expires_boundary="end")):
            forged = copy.deepcopy(self.session.world_state)
            change(forged["attack_effects"][0])
            with self.assertRaises(ValueError):
                features.validate_saved_effects(forged, self.session.character)

    def test_a_timed_effect_is_refused_on_another_class(self):
        self.strike(save=1)
        import api.tests.test_roadmap_c14_fighter as fighter
        with self.assertRaises(ValueError):
            features.validate_saved_effects(self.session.world_state, fighter.created(1).character)


class OpenHand(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(3)
        self.session.world_state["equipment"].update(main_hand=None)

    def strike(self, technique, save=1):
        with patch("game.roll_d20", return_value=save):
            return hit(self.session, flurry(self.npc, open_hand_technique=technique), damage=2)[0]["result"]["attack"]

    def effect(self, result):
        return next(e for e in result["additional_effects"] if e["kind"] == "open_hand_technique")

    def test_topple_on_a_failed_dexterity_save(self):
        effect = self.effect(self.strike("topple"))
        self.assertEqual((effect["technique"], effect["save"]["ability"], effect["save"]["dc"], effect["applied"]),
                         ("topple", "dexterity", 8 + 2 + 2, True))
        self.assertIn("prone", attacks.conditions(self.session, self.npc["id"], self.npc))

    def test_topple_resisted(self):
        self.assertFalse(self.effect(self.strike("topple", save=20))["applied"])
        self.assertNotIn("prone", attacks.conditions(self.session, self.npc["id"], self.npc))

    def test_push_moves_fifteen_feet_on_a_failed_strength_save(self):
        pairs = self.session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})
        pairs[f"player|{self.npc['id']}"] = {"distance_ft": 5, "push_clear_ft": 30}
        effect = self.effect(self.strike("push"))
        self.assertEqual((effect["save"]["ability"], effect["push"]["applied"], effect["push"]["distance_ft"]), ("strength", True, 15))
        self.assertEqual(self.npc["distance_ft"], 20)

    def test_push_without_a_known_clear_line_reports_it_and_moves_nothing(self):
        effect = self.effect(self.strike("push"))
        self.assertEqual((effect["applied"], effect["push"]["reason"]), (False, "position_unresolved_or_blocked"))

    def test_only_a_flurry_attack_carries_it(self):
        self.assertEqual(code(self.session, unarmed(self.npc, open_hand_technique="topple")), "open_hand_technique_flurry_only")
        self.assertEqual(code(self.session, bonus_strike(self.npc, open_hand_technique="topple")), "open_hand_technique_flurry_only")

    def test_level_two_does_not_have_it(self):
        session, npc = fight(2)
        session.world_state["equipment"].update(main_hand=None)
        self.assertEqual(code(session, flurry(npc, open_hand_technique="topple")), "open_hand_technique_not_available")

    def test_addle_is_not_offered_while_the_engine_has_no_opportunity_attacks_against_the_player(self):
        self.assertEqual(code(self.session, flurry(self.npc, open_hand_technique="addle")), "invalid_monk_command")


class ExtraAttack(unittest.TestCase):
    def test_level_five_comes_from_the_shared_owner(self):
        session, npc = fight(5)
        session.world_state["equipment"].update(main_hand=None)
        steps = hit(session, unarmed(npc), {"kind": "continue_attack", "target_id": npc["id"], "weapon_id": "unarmed"}, damage=2)
        self.assertEqual([step["action_resource_cost"] for step in steps], [1, 0])
        self.assertEqual(attacks.sequence_snapshot(session, "player")["attacks"], 2)


class RealTurn(unittest.TestCase):
    """Through the scheduler and the monster owner, not a direct attack call."""
    def turn(self, session, npc, *, damage=5, reaction=9, save=1):
        npc.update(attack_bonus=20, damage_die=8, damage_dice=1, damage_modifier=6, attack_damage_type="slashing")
        with patch("game.roll_d20", side_effect=[15, save, save, save]), patch("game.roll_attack", return_value=15), \
                patch.object(session.rng, "randint", side_effect=lambda low, high: reaction if high == 10 else damage):
            return run(session, {"kind": "end_turn"})[0]["enemy_actions"]

    def test_an_enemy_turn_reaches_deflect_attacks(self):
        session, npc = fight(3)
        session.character.update(max_hp=60, current_hp=60)
        attacks_made = [a for a in self.turn(session, npc) if a.get("action") == "enemy_attack"]
        self.assertTrue(attacks_made)
        self.assertEqual(attacks_made[0]["additional_effects"][0]["kind"], "deflect_attacks")
        self.assertEqual(session.character["current_hp"], 60)
        self.assertFalse(economy.ensure(session)["player"]["reaction_spent"], "the Reaction comes back on the player's turn")

    def test_a_lethal_redirect_on_an_enemy_turn_ends_the_combat(self):
        session, npc = fight(3)
        session.character.update(max_hp=60, current_hp=60)
        run(session, {"kind": "set_deflect_attacks", "deflect_mode": "redirect"})
        npc["current_hp"] = 3
        self.turn(session, npc)
        self.assertFalse(session.world_state["combat"]["active"])

    def test_the_default_attack_of_an_empty_handed_monk_is_an_unarmed_strike(self):
        session, npc = fight(1)
        self.assertEqual(session.world_state["equipment"]["main_hand"], None)
        self.assertEqual(hit(session, attack(npc), damage=4)[0]["result"]["weapon_id"], "unarmed")
        self.assertIn("unarmed", attacks.natural_choice(session, "saldiriyorum"))


class Projection(unittest.TestCase):
    def test_level_five_block(self):
        session, npc = fight(5)
        view = features.projection(session)
        self.assertEqual((view["martial_arts_die"], view["save_dc"], view["movement_bonus_ft"]), (8, 13, 10))
        self.assertEqual((view["focus"]["points_remaining"], view["focus"]["max_points"]), (5, 5))
        for name in ("martial_arts_strike", "flurry_of_blows", "patient_defense", "step_of_the_wind", "uncanny_metabolism"):
            self.assertEqual(view[name], {"available": True, "reason": None}, name)
        self.assertEqual(view["stunning_strike"], {"available": True, "reason": None})
        self.assertEqual(view["deflect_mode"], "reduce")
        self.assertEqual(view["open_hand_techniques"], ["push", "topple"])
        self.assertEqual(view["flurry_strikes_remaining"], 0)

    def test_level_one_block_hides_the_later_features(self):
        session, _ = fight(1)
        view = features.projection(session)
        self.assertIsNone(view["focus"])
        for name in ("flurry_of_blows", "patient_defense", "step_of_the_wind", "uncanny_metabolism", "stunning_strike", "deflect_mode"):
            self.assertIsNone(view[name], name)
        self.assertEqual(view["open_hand_techniques"], [])

    def test_a_refusal_reason_is_public_and_the_projection_is_pure(self):
        session, _ = fight(2)
        session.world_state["combat"]["current_actor_id"] = "nobody"
        before = copy.deepcopy(session.world_state)
        view = features.projection(session)
        self.assertEqual(view["flurry_of_blows"], {"available": False, "reason": "flurry_of_blows_current_combat_turn_required"})
        self.assertEqual(session.world_state, before)

    def test_invalid_state_hides_the_block_and_other_classes_have_none(self):
        session = created(2)
        session.character["monk_state"] = {"focus_spent": 9, "metabolism_spent": False, "deflect": "reduce"}
        self.assertIsNone(features.projection(session))
        import api.tests.test_roadmap_c14_fighter as fighter
        self.assertIsNone(features.projection(fighter.created(1)))

    def test_disclosure_names_what_is_supported_and_what_is_not(self):
        text = " ".join(cp.progression_disclosure("Monk", 5)["pending"])
        for word in ("Slow Fall", "DEX", "Addle", "jump", "Disengage"):
            self.assertIn(word, text, word)
        supported = " ".join(cp.progression_disclosure("Monk", 5)["supported"])
        for word in ("Martial Arts", "Unarmored Defense", "Focus Points", "Stunning Strike", "Deflect Attacks", "Extra Attack", "Open Hand"):
            self.assertIn(word, supported, word)
        self.assertNotIn("Stunning Strike", " ".join(cp.progression_disclosure("Monk", 4)["supported"]))


if __name__ == "__main__":
    unittest.main()
