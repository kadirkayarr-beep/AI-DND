"""Rogue 1-5 effects through the existing owners: Sneak Attack, Cunning Action, Steady Aim, Cunning Strike, Uncanny Dodge, Assassin.

Numbers were read from the page renders (PHB 2024 PDF 128-130, 133): Sneak Attack 1/1/2/2/3 d6 once per turn; Cunning Strike die cost
1d6, DC 8 + DEX modifier + Proficiency Bonus, Poison 1 minute, Trip Large or smaller, Withdraw half Speed; Uncanny Dodge halves and
rounds down; Assassin extra damage equals the Rogue level. Critical Hit doubling of Sneak Attack dice: K07 playing_the_game, PDF 26/27.
Order of application: multipliers before Resistance, same source. Dice are deterministic; synthetic NPCs are unit fixtures.
"""
import copy
import unittest
from unittest.mock import patch

import action_economy as economy
import game
import initiative
import rogue_features as features
import weapon_attack as attacks
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload
from combat_lifecycle import CombatRequestError
from api.tests.test_roadmap_c10_extra_attack import start_combat
from api.tests.test_roadmap_c18_rogue import created, earn, earned, roundtrip


def fight(level=1, weapon="Rapier", second_round=True, **kwargs):
    session = created(level, **kwargs)
    npc = start_combat(session)
    arm(session, weapon)
    if second_round:
        session.world_state["combat"]["round"] = 2  # no Surprising Strikes
    return session, npc


def arm(session, weapon):
    session.world_state["inventory"].append(weapon)
    identity = attacks.lookup(weapon)["weapon_id"]
    session.world_state["equipment"] = {"main_hand": identity, "off_hand": None}
    session.world_state["ammunition"] = {"arrow": 5, "bolt": 5}
    return identity


def run(session, *steps):
    return economy.execute(session, {"steps": list(steps)})["action_economy_result"]["steps"]


def hit(session, npc, roll=15, die=3, **step):
    """One attack with fixed dice; the target's own save rolls 1 unless a test patches it."""
    with patch("game.roll_attack", return_value=roll), patch("game.roll_d20", return_value=1), \
            patch.object(session.rng, "randint", return_value=die):
        return run(session, {"kind": "attack", "target_id": npc["id"], **step})[0]["result"]


def advantage(npc):
    npc["conditions"] = ["blinded"]


def sneak_rolls(result):
    return [entry for entry in result["damage_rolls"] if entry["source"] == "sneak_attack"]


def ally(session, npc, distance=5, **fields):
    other = session.create_npc_from_ai({"name": "Unit Ally", "role": "Guard", "location": "tavern"})
    other.update(current_hp=20, max_hp=20, armor_class=10, hostile=False, combat_relationships={"player": "ally"}, **fields)
    session.character.setdefault("combat_relationships", {})[other["id"]] = "ally"
    with patch("game.roll_d20", return_value=1):
        session.join_combat_participants([other["id"]])
    if distance is not None:
        session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})[f"{other['id']}|{npc['id']}"] = {"distance_ft": distance}
    return other


def end_turn(session):
    with patch("game.roll_attack", return_value=1), patch("game.roll_d20", return_value=1):
        return run(session, {"kind": "end_turn"})


def incoming(session, npc, damage=11):
    """One real enemy attack against the player through the shared owner."""
    profile = {"weapon_id": "unit_claw", "name": "Claw", "kind": "melee", "category": None, "properties": [], "mastery": None,
               "damage_die": 0, "damage_dice": 0, "fixed_damage": damage, "damage_type": "slashing", "magic_attack_bonus": 0,
               "magic_damage_bonus": 0, "attack_bonus": 10, "damage_modifier": 0}
    economy.ensure(session)[npc["id"]]["attack_action"] = {"remaining_attacks": 9, "total_attacks": 10, "action_resource_cost": 1}
    with patch("game.roll_d20", return_value=15):
        with economy.executing(session, "monster_capability", npc["id"]):
            return attacks.resolve(session, npc["id"], "player", None, None, origin="continuation", profile=profile)


class SneakAttack(unittest.TestCase):
    def test_advantage_finesse_hit_adds_the_table_die_of_the_weapon_type(self):
        session, npc = fight()
        advantage(npc)
        result = hit(session, npc, die=4)
        self.assertEqual([(e["die"], e["count"], e["rolls"]) for e in sneak_rolls(result)], [(6, 1, [4])])
        self.assertEqual(result["damage_instances"][0]["damage_type"], "piercing")
        self.assertEqual(result["sneak_attack"]["dice"], 1)
        self.assertEqual(result["raw_damage"], 4 + session.character["dexterity_mod"] + 4
                         if result["ability_used"] == "dexterity" else 4 + session.character["strength_mod"] + 4)

    def test_dice_follow_the_applied_level_only(self):
        for level, dice in ((1, 1), (2, 1), (3, 2), (4, 2), (5, 3)):
            with self.subTest(level):
                session, npc = fight(level)
                advantage(npc)
                self.assertEqual(sneak_rolls(hit(session, npc))[0]["count"], dice)
        session = earned(self, 2)
        earn(session, 5)
        npc = start_combat(session)
        arm(session, "Rapier")
        advantage(npc)
        self.assertEqual(sneak_rolls(hit(session, npc))[0]["count"], 1)

    def test_once_per_turn_and_again_on_another_turn(self):
        session, npc = fight()
        advantage(npc)
        session.character["attacks_per_action"] = 2
        self.assertTrue(sneak_rolls(hit(session, npc)))
        with patch("game.roll_attack", return_value=15), patch.object(session.rng, "randint", return_value=3):
            second = run(session, {"kind": "continue_attack", "target_id": npc["id"]})[0]["result"]
        self.assertFalse(sneak_rolls(second))
        combat = session.world_state["combat"]
        combat["current_actor_id"] = npc["id"]
        self.assertFalse(features.sneak_used(session))
        combat["current_actor_id"] = "player"
        self.assertTrue(features.sneak_used(session))
        combat["round"] += 1
        self.assertFalse(features.sneak_used(session))

    def test_a_miss_does_not_use_it(self):
        session, npc = fight()
        advantage(npc)
        self.assertFalse(hit(session, npc, roll=2)["hit"])
        self.assertFalse(features.sneak_used(session))

    def test_needs_advantage_or_an_ally(self):
        session, npc = fight()
        self.assertFalse(sneak_rolls(hit(session, npc)))

    def test_advantage_cancelled_by_disadvantage_does_not_count(self):
        session, npc = fight()
        advantage(npc)
        session.character["conditions"] = ["poisoned"]
        self.assertFalse(sneak_rolls(hit(session, npc)))

    def test_weapon_must_be_finesse_or_ranged(self):
        cases = (("Club", None, False), ("Dagger", None, True), ("Shortbow", None, True), ("Handaxe", "thrown", False), ("Dagger", "thrown", True))
        for weapon, mode, expected in cases:
            with self.subTest(weapon=weapon, mode=mode):
                session, npc = fight(weapon=weapon)
                advantage(npc)
                step = {"attack_choice": {"mode": mode}} if mode else {}
                self.assertEqual(bool(sneak_rolls(hit(session, npc, **step))), expected)

    def test_unarmed_never_qualifies(self):
        session, npc = fight()
        advantage(npc)
        self.assertFalse(sneak_rolls(hit(session, npc, weapon_id="unarmed")))

    def test_an_ally_within_five_feet_replaces_advantage(self):
        session, npc = fight()
        ally(session, npc)
        self.assertTrue(sneak_rolls(hit(session, npc)))

    def test_the_ally_must_be_near_and_able_and_there_is_no_disadvantage(self):
        session, npc = fight()
        ally(session, npc, distance=10)
        self.assertFalse(sneak_rolls(hit(session, npc)))
        session, npc = fight()
        ally(session, npc, distance=None)
        self.assertFalse(sneak_rolls(hit(session, npc)), "an unknown distance is never guessed")
        session, npc = fight()
        ally(session, npc, conditions=["incapacitated"])
        self.assertFalse(sneak_rolls(hit(session, npc)))
        session, npc = fight()
        ally(session, npc)
        session.character["conditions"] = ["poisoned"]
        self.assertFalse(sneak_rolls(hit(session, npc)))

    def test_a_critical_hit_doubles_the_dice(self):
        session, npc = fight(3)
        advantage(npc)
        self.assertEqual(sneak_rolls(hit(session, npc, roll=20))[0]["count"], 4)

    def test_other_classes_and_the_enemy_get_nothing(self):
        from api.tests.test_roadmap_c14_fighter import created as fighter
        session = fighter(1)
        npc = start_combat(session)
        arm(session, "Rapier")
        advantage(npc)
        self.assertFalse(sneak_rolls(hit(session, npc)))


class CunningAction(unittest.TestCase):
    def code(self, session, *steps):
        with self.assertRaises(CombatRequestError) as caught:
            run(session, *steps)
        return caught.exception.code

    def step(self, option):
        return {"kind": "cunning_action", "resource": "bonus", "cunning_option": option}

    def test_refused_at_level_one(self):
        session, _ = fight(1)
        self.assertEqual(self.code(session, self.step("dash")), "cunning_action_not_available")

    def test_dash_adds_speed_and_spends_only_the_bonus_action(self):
        session, _ = fight(2)
        speed = economy.speed(session, "player")
        result = run(session, self.step("dash"))[0]["result"]
        resources = economy.ensure(session)["player"]
        self.assertEqual(result["movement_added_ft"], speed)
        self.assertEqual(economy.movement_limit(session, "player"), speed * 2)
        self.assertTrue(resources["bonus_action_spent"])
        self.assertFalse(resources["base_action_spent"])

    def test_dash_never_spends_an_orc_adrenaline_use(self):
        session, _ = fight(2)
        session.character["species"] = "Orc"
        session.character["species_trait_state"] = {**(session.character.get("species_trait_state") or {}), "adrenaline_rush_uses_remaining": 2}
        run(session, self.step("dash"))
        self.assertEqual(session.character["species_trait_state"]["adrenaline_rush_uses_remaining"], 2)

    def test_disengage_is_recorded_for_the_turn(self):
        session, _ = fight(2)
        run(session, self.step("disengage"))
        self.assertTrue(economy.ensure(session)["player"]["disengaging"])

    def test_one_bonus_action(self):
        session, _ = fight(2)
        run(session, self.step("dash"))
        self.assertEqual(self.code(session, self.step("disengage")), "bonus_action_spent")

    def test_hide_is_not_offered(self):
        session, _ = fight(2)
        self.assertEqual(self.code(session, self.step("hide")), "invalid_rogue_command")

    def test_exact_step_only(self):
        session, npc = fight(2)
        self.assertEqual(self.code(session, self.step("dash"), {"kind": "attack", "target_id": npc["id"]}), "invalid_rogue_command")
        self.assertEqual(self.code(session, {"kind": "cunning_action", "cunning_option": "dash"}), "invalid_rogue_command")

    def test_own_turn_only(self):
        session, npc = fight(2)
        combat = session.world_state["combat"]
        combat["current_actor_id"], combat["current_turn_index"] = npc["id"], combat["initiative_order"].index(npc["id"])
        self.assertEqual(self.code(session, self.step("dash")), "cunning_action_current_combat_turn_required")


STEADY = {"kind": "steady_aim", "resource": "bonus"}


class SteadyAim(unittest.TestCase):
    def code(self, session, *steps):
        with self.assertRaises(CombatRequestError) as caught:
            run(session, *steps)
        return caught.exception.code

    def test_refused_below_level_three(self):
        session, _ = fight(2)
        self.assertEqual(self.code(session, STEADY), "steady_aim_not_available")

    def test_refused_after_moving(self):
        session, _ = fight(3)
        run(session, {"kind": "move", "distance_ft": 5})
        self.assertEqual(self.code(session, STEADY), "steady_aim_moved")

    def test_advantage_on_the_next_attack_roll_only_and_it_enables_sneak_attack(self):
        session, npc = fight(3)
        session.character["attacks_per_action"] = 2
        run(session, STEADY)
        self.assertTrue(economy.ensure(session)["player"]["bonus_action_spent"])
        first = hit(session, npc)
        self.assertIn("steady_aim", first["advantage_sources"])
        self.assertTrue(sneak_rolls(first))
        with patch("game.roll_attack", return_value=15), patch.object(session.rng, "randint", return_value=3):
            second = run(session, {"kind": "continue_attack", "target_id": npc["id"]})[0]["result"]
        self.assertNotIn("steady_aim", second["advantage_sources"])

    def test_a_miss_also_uses_it(self):
        session, npc = fight(3)
        session.character["attacks_per_action"] = 2
        run(session, STEADY)
        hit(session, npc, roll=2)
        self.assertFalse(economy.ensure(session)["player"]["steady_aim"]["advantage"])

    def test_speed_is_zero_until_the_turn_ends_then_back(self):
        session, npc = fight(3)
        speed = economy.speed(session, "player")
        run(session, STEADY)
        self.assertEqual(economy.speed(session, "player"), 0)
        self.assertEqual(self.code(session, {"kind": "move", "distance_ft": 5}), "movement_unavailable")
        self.assertEqual(run(session, {"kind": "dash"})[0]["movement_added_ft"], 0)
        end_turn(session)
        self.assertNotIn("steady_aim", economy.ensure(session)["player"])
        self.assertEqual(economy.speed(session, "player"), speed)

    def test_unused_advantage_does_not_survive_the_turn(self):
        session, npc = fight(3)
        run(session, STEADY)
        end_turn(session)
        self.assertNotIn("steady_aim", hit(session, npc)["advantage_sources"])

    def test_it_ends_at_the_end_of_the_turn_not_at_the_start_of_the_next(self):
        session, npc = fight(3)
        speed = economy.speed(session, "player")
        run(session, STEADY)
        attacks.boundary(session, "player", "end")
        self.assertEqual(economy.speed(session, "player"), speed)


def strike(option, **extra):
    return {"cunning_strike": option, **extra}


class CunningStrike(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(5)
        advantage(self.npc)

    def code(self, **step):
        with self.assertRaises(CombatRequestError) as caught:
            hit(self.session, self.npc, **step)
        return caught.exception.code

    def test_refused_below_level_five_and_with_an_unknown_option(self):
        session, npc = fight(4)
        advantage(npc)
        with self.assertRaises(CombatRequestError) as caught:
            hit(session, npc, **strike("trip"))
        self.assertEqual(caught.exception.code, "cunning_strike_not_available")
        self.assertEqual(self.code(**strike("daze")), "invalid_cunning_strike")

    def test_a_step_that_is_not_an_attack_cannot_carry_a_choice_it_would_drop(self):
        before = copy.deepcopy(self.session.world_state["combat"])
        for step in ({"kind": "react", "opportunity_id": "none", "cunning_strike": "trip"},
                     {"kind": "move", "distance_ft": 5, "cunning_strike": "trip"},
                     {"kind": "dash", "cunning_strike_move_ft": 5}):
            with self.subTest(step), self.assertRaises(CombatRequestError) as caught:
                run(self.session, step)
            self.assertEqual(caught.exception.code, "invalid_attack_choice")
        self.assertEqual(self.session.world_state["combat"], before)

    def test_the_turn_text_names_the_die_and_the_outcome(self):
        with patch("game.roll_attack", return_value=15), patch("game.roll_d20", return_value=1),                 patch.object(self.session.rng, "randint", return_value=3):
            narration = economy.execute(self.session, {"steps": [
                {"kind": "attack", "target_id": self.npc["id"], "cunning_strike": "trip"}]})["narration"]
        self.assertIn("Sneak Attack: 2d6", narration)
        self.assertIn("Cunning Strike (Trip)", narration)
        self.assertIn("Prone", narration)

    def test_a_refused_choice_costs_nothing(self):
        before = copy.deepcopy(self.session.world_state["combat"]["turn_resources"]["player"])
        self.code(**strike("daze"))
        self.assertEqual(self.session.world_state["combat"]["turn_resources"]["player"], before)

    def test_the_cost_is_one_die_before_rolling_and_the_dc_is_eight_dex_pb(self):
        self.npc["size"] = "medium"
        result = hit(self.session, self.npc, **strike("trip"))
        self.assertEqual(sneak_rolls(result)[0]["count"], 2)
        effect = result["cunning_strike"]
        character = self.session.character
        self.assertEqual(effect["dc"], 8 + character["dexterity_mod"] + character["proficiency_bonus"])
        self.assertEqual(effect["cost"], 1)
        self.assertEqual(effect["save"]["ability"], "dexterity")
        self.assertIn("prone", self.npc["conditions"])

    def test_no_sneak_attack_means_no_cost_and_no_effect(self):
        self.npc["conditions"] = []
        result = hit(self.session, self.npc, **strike("trip"))
        self.assertNotIn("cunning_strike", result)
        self.assertNotIn("prone", self.npc["conditions"])

    def test_a_critical_hit_doubles_what_remains(self):
        self.assertEqual(sneak_rolls(hit(self.session, self.npc, roll=20, **strike("trip")))[0]["count"], 4)

    def test_it_needs_the_sneak_attack_still_unused(self):
        self.session.character["attacks_per_action"] = 2
        hit(self.session, self.npc)
        with self.assertRaises(CombatRequestError) as caught:
            run(self.session, {"kind": "continue_attack", "target_id": self.npc["id"], **strike("trip")})
        self.assertEqual(caught.exception.code, "sneak_attack_already_used")

    def test_trip_size_limit(self):
        self.npc["size"] = "huge"
        self.assertEqual(self.code(**strike("trip")), "cunning_strike_target_too_large")
        npc = next(n for n in self.session.world_state["npcs"] if n["id"] == self.npc["id"])  # the refusal restored the state
        npc["size"] = "large"
        hit(self.session, npc, **strike("trip"))
        self.assertIn("prone", npc["conditions"])

    def test_trip_save_success_leaves_the_target_standing(self):
        with patch("game.roll_attack", return_value=15), patch("game.roll_d20", return_value=20), \
                patch.object(self.session.rng, "randint", return_value=3):
            result = run(self.session, {"kind": "attack", "target_id": self.npc["id"], **strike("trip")})[0]["result"]
        self.assertFalse(result["cunning_strike"]["applied"])
        self.assertNotIn("prone", self.npc["conditions"])

    def test_poison_needs_the_kit(self):
        self.session.world_state["inventory"].remove("Poisoner's Kit")
        self.assertEqual(self.code(**strike("poison")), "cunning_strike_kit_required")

    def test_poison_applies_and_repeats_at_the_end_of_the_target_turn(self):
        result = hit(self.session, self.npc, **strike("poison"))
        self.assertEqual(result["cunning_strike"]["save"]["ability"], "constitution")
        self.assertIn("poisoned", self.npc["conditions"])
        with patch("game.roll_d20", return_value=1):
            attacks.boundary(self.session, self.npc["id"], "end")
        self.assertIn("poisoned", self.npc["conditions"])
        with patch("game.roll_d20", return_value=20):
            attacks.boundary(self.session, self.npc["id"], "end")
        self.assertNotIn("poisoned", self.npc["conditions"])
        self.assertFalse([e for e in self.session.world_state["attack_effects"] if e["kind"] == "cunning_poison"])

    def test_poison_ends_after_one_minute(self):
        hit(self.session, self.npc, **strike("poison"))
        record = next(e for e in self.session.world_state["attack_effects"] if e["kind"] == "cunning_poison")
        turn = self.session.world_state["combat"]["turn_resources"]["player"]["attack_turn_counter"]
        self.assertEqual(record["expires_turn"], turn + 10)
        self.session.world_state["combat"]["turn_resources"]["player"]["attack_turn_counter"] = turn + 9
        attacks.boundary(self.session, "player", "end")
        self.assertIn("poisoned", self.npc["conditions"])
        self.session.world_state["combat"]["turn_resources"]["player"]["attack_turn_counter"] = turn + 10
        attacks.boundary(self.session, "player", "end")
        self.assertNotIn("poisoned", self.npc["conditions"])

    def test_poison_ends_with_the_combat(self):
        hit(self.session, self.npc, **strike("poison"))
        self.session.end_combat("test_end")
        self.assertNotIn("poisoned", self.npc["conditions"])

    def test_an_already_poisoned_target_keeps_its_own_condition(self):
        self.npc["conditions"] = ["blinded", "poisoned"]
        result = hit(self.session, self.npc, **strike("poison"))
        self.assertFalse(result["cunning_strike"]["applied"])
        self.assertEqual(result["cunning_strike"]["reason"], "already_poisoned")
        self.assertFalse([e for e in self.session.world_state.get("attack_effects", []) if e["kind"] == "cunning_poison"])

    def test_a_condition_immune_target_makes_no_save(self):
        self.npc["condition_immunities"] = ["Poisoned"]
        result = hit(self.session, self.npc, **strike("poison"))
        self.assertEqual(result["cunning_strike"]["reason"], "condition_immunity")
        self.assertNotIn("save", result["cunning_strike"])

    def test_a_target_that_dropped_makes_no_save_and_the_die_stays_spent(self):
        self.npc["current_hp"] = 1
        result = hit(self.session, self.npc, **strike("trip"))
        self.assertEqual(sneak_rolls(result)[0]["count"], 2)
        self.assertEqual(result["cunning_strike"]["reason"], "target_defeated")

    def test_withdraw_moves_up_to_half_speed_on_the_movement_ledger(self):
        speed = economy.speed(self.session, "player")
        result = hit(self.session, self.npc, **strike("withdraw", cunning_strike_move_ft=speed // 2))
        self.assertEqual(result["cunning_strike"]["moved_ft"], speed // 2)
        resources = economy.ensure(self.session)["player"]
        self.assertEqual(resources["movement_used"], speed // 2)
        self.assertEqual(resources["ready_movement_grant"], speed // 2)
        self.assertEqual(economy.movement_limit(self.session, "player") - resources["movement_used"], speed)

    def test_withdraw_refuses_a_bad_distance(self):
        speed = economy.speed(self.session, "player")
        self.assertEqual(self.code(**strike("withdraw", cunning_strike_move_ft=speed // 2 + 5)), "cunning_strike_out_of_range")
        self.assertEqual(self.code(**strike("withdraw")), "invalid_cunning_strike")
        self.assertEqual(self.code(**strike("trip", cunning_strike_move_ft=5)), "invalid_cunning_strike")

    def test_withdraw_after_steady_aim_has_no_speed_to_use(self):
        run(self.session, STEADY)
        self.assertEqual(self.code(**strike("withdraw", cunning_strike_move_ft=5)), "cunning_strike_out_of_range")

    def test_withdraw_works_on_the_turn_the_target_drops(self):
        self.npc["current_hp"] = 1
        result = hit(self.session, self.npc, **strike("withdraw", cunning_strike_move_ft=10))
        self.assertEqual(result["cunning_strike"]["moved_ft"], 10)

    def test_the_kept_choice_never_reaches_the_public_preview_as_a_cost(self):
        before = copy.deepcopy(self.session.world_state)
        attacks.preview(self.session, "player", self.npc["id"], "rapier", strike("trip"))
        self.assertEqual(self.session.world_state, before)


class UncannyDodge(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(5)
        self.session.character["current_hp"] = self.session.character["max_hp"] = 60
        combat = self.session.world_state["combat"]
        combat["current_actor_id"], combat["current_turn_index"] = self.npc["id"], combat["initiative_order"].index(self.npc["id"])

    def test_halves_rounding_down_and_spends_the_reaction(self):
        result = incoming(self.session, self.npc, 11)
        self.assertEqual(result["damage"], 5)
        self.assertEqual(self.session.character["current_hp"], 55)
        self.assertTrue(economy.ensure(self.session)["player"]["reaction_spent"])
        self.assertEqual([e for e in result["additional_effects"] if e["kind"] == "uncanny_dodge"],
                         [{"kind": "uncanny_dodge", "damage_before": 11, "damage_after": 5}])

    def test_it_comes_before_resistance(self):
        self.session.character["resistances"] = ["slashing"]
        self.assertEqual(incoming(self.session, self.npc, 11)["damage"], 2)

    def test_only_one_hit_per_reaction(self):
        incoming(self.session, self.npc, 10)
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 10)

    def test_not_below_level_five_nor_on_xp_alone(self):
        session, npc = fight(4)
        session.character["current_hp"] = session.character["max_hp"] = 60
        self.assertEqual(incoming(session, npc, 10)["damage"], 10)
        session = earned(self, 4)
        earn(session, 5)
        npc = start_combat(session)
        session.character["current_hp"] = session.character["max_hp"] = 60
        self.assertEqual(incoming(session, npc, 10)["damage"], 10)

    def test_an_unseen_attacker_is_not_dodged(self):
        pairs = self.session.world_state.setdefault("attack_environment", {}).setdefault("pairs", {})
        pairs[f"{self.npc['id']}|player"] = {"distance_ft": 5, "target_sees_attacker": False}
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 10)
        self.assertFalse(economy.ensure(self.session)["player"]["reaction_spent"])

    def test_a_blinded_rogue_does_not_dodge(self):
        self.session.character["conditions"] = ["blinded"]
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 10)

    def test_an_incapacitated_rogue_does_not_dodge(self):
        self.session.character["conditions"] = ["incapacitated"]
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 10)

    def test_a_spent_reaction_does_not_dodge(self):
        economy.ensure(self.session)["player"]["reaction_spent"] = True
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 10)

    def test_a_reaction_held_by_ready_is_kept(self):
        economy.ensure(self.session)["player"]["ready"] = {"trigger": {"event": "actor_moves", "actor_id": self.npc["id"]},
                                                           "response": {"kind": "move", "distance_ft": 5}, "spell_metadata": None}
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 10)
        self.assertFalse(economy.ensure(self.session)["player"]["reaction_spent"])

    def test_the_player_can_turn_it_off_and_on(self):
        combat = self.session.world_state["combat"]
        combat["current_actor_id"], combat["current_turn_index"] = "player", combat["initiative_order"].index("player")
        run(self.session, {"kind": "uncanny_dodge", "uncanny_dodge_enabled": False})
        self.assertIs(self.session.character[features.UNCANNY_OFF], True)
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 10)
        run(self.session, {"kind": "uncanny_dodge", "uncanny_dodge_enabled": True})
        self.assertNotIn(features.UNCANNY_OFF, self.session.character)
        self.assertEqual(incoming(self.session, self.npc, 10)["damage"], 5)

    def test_the_toggle_is_refused_before_level_five(self):
        session, _ = fight(4)
        with self.assertRaises(CombatRequestError) as caught:
            run(session, {"kind": "uncanny_dodge", "uncanny_dodge_enabled": False})
        self.assertEqual(caught.exception.code, "uncanny_dodge_not_available")


class Assassin(unittest.TestCase):
    def test_initiative_advantage_needs_the_applied_subclass(self):
        session = created(3)
        self.assertIn("assassinate", initiative.settings(session, "player", notify_features=False)["advantage_sources"])
        session = created(2)
        self.assertNotIn("assassinate", initiative.settings(session, "player", notify_features=False)["advantage_sources"])

    def test_first_round_advantage_and_level_damage_against_a_creature_yet_to_act(self):
        session, npc = fight(3, second_round=False)
        result = hit(session, npc, die=2)
        self.assertIn("surprising_strikes", result["advantage_sources"])
        self.assertEqual(result["sneak_attack"]["surprising_strikes"], 3)
        with_level = result["raw_damage"]
        session, npc = fight(3)
        advantage(npc)
        self.assertEqual(hit(session, npc, die=2)["raw_damage"], with_level - 3)

    def test_the_extra_damage_is_not_doubled_on_a_critical_hit(self):
        session, npc = fight(3, second_round=False)
        self.assertEqual(hit(session, npc, roll=20, die=1)["sneak_attack"]["surprising_strikes"], 3)

    def test_no_advantage_after_the_first_round_or_once_the_target_acted(self):
        session, npc = fight(3)
        self.assertNotIn("surprising_strikes", hit(session, npc)["advantage_sources"])
        session, npc = fight(3, second_round=False)
        self.assertTrue(features.surprising_target(session, npc["id"]))
        with patch.dict(session.world_state["combat"], {"current_turn_index": 1}):
            self.assertFalse(features.surprising_target(session, npc["id"]), "the target's own turn has begun")

    def test_the_extra_damage_reaches_any_target_hit_in_the_first_round(self):
        session, npc = fight(3, second_round=False)
        advantage(npc)
        with patch.object(features, "surprising_target", return_value=False):  # this target already took its turn
            result = hit(session, npc, die=2)
        self.assertNotIn("surprising_strikes", result["advantage_sources"])
        self.assertEqual(result["sneak_attack"]["surprising_strikes"], 3)

    def test_the_extra_damage_stops_after_the_first_round(self):
        session, npc = fight(3)
        advantage(npc)
        self.assertEqual(hit(session, npc)["sneak_attack"]["surprising_strikes"], 0)

    def test_no_surprising_strikes_before_level_three(self):
        session, npc = fight(2, second_round=False)
        self.assertNotIn("surprising_strikes", hit(session, npc)["advantage_sources"])


class SavedTurnState(unittest.TestCase):
    def forged(self, session, change):
        payload = serialize_campaign_payload(session)
        change(payload["engine_save"]["world_state"])
        fresh = game.create_session(seed=19)
        with self.assertRaises(Exception):
            restore_campaign_session(fresh, payload)

    def resources(self, world):
        return world["combat"]["turn_resources"]["player"]

    def test_mid_turn_state_round_trips(self):
        session, npc = fight(5)
        run(session, STEADY)
        advantage(npc)
        hit(session, npc, **strike("poison"))
        fresh, _ = roundtrip(session)
        self.assertEqual(economy.speed(fresh, "player"), 0)
        self.assertTrue(features.sneak_used(fresh))
        self.assertTrue([e for e in fresh.world_state["attack_effects"] if e["kind"] == "cunning_poison"])

    def test_forged_turn_records_fail_closed(self):
        session, npc = fight(5)
        run(session, STEADY)
        advantage(npc)
        hit(session, npc, **strike("poison"))
        identity = npc["id"]

        def bad_poison(world, **change):
            next(e for e in world["attack_effects"] if e["kind"] == "cunning_poison").update(change)
        cases = {
            "steady aim shape": lambda w: self.resources(w).update(steady_aim={"advantage": "yes"}),
            "steady aim after moving": lambda w: self.resources(w).update(movement_used=5, movement_available=30),
            "sneak marker": lambda w: self.resources(w).update(sneak_attack_turn=["x", "player"]),
            "poison dc": lambda w: bad_poison(w, dc="15"),
            "poison source": lambda w: bad_poison(w, source_actor=identity),
            "poison target": lambda w: bad_poison(w, target_id=7),
            "poison extra key": lambda w: bad_poison(w, surprise=1),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.forged(session, change)

    def test_a_lower_level_rogue_cannot_keep_a_steady_aim_record(self):
        session, _ = fight(2)
        self.forged(session, lambda w: self.resources(w).update(steady_aim={"advantage": True}))

    def test_a_forged_record_on_another_class_has_no_effect_on_attacks(self):
        from api.tests.test_roadmap_c14_fighter import created as fighter
        session = fighter(1)
        npc = start_combat(session)
        arm(session, "Rapier")
        economy.ensure(session)["player"]["steady_aim"] = {"advantage": True}
        self.assertNotIn("steady_aim", hit(session, npc)["advantage_sources"])


class Projection(unittest.TestCase):
    def test_level_one_shows_sneak_attack_only(self):
        session, _ = fight(1)
        block = features.projection(session)
        self.assertEqual(block["sneak_attack"], {"dice": 1, "die": 6, "used_this_turn": False})
        self.assertIsNone(block["cunning_action"])
        self.assertIsNone(block["steady_aim"])
        self.assertIsNone(block["cunning_strike"])
        self.assertIsNone(block["uncanny_dodge"])

    def test_level_five_lists_the_options_with_cost_and_dc(self):
        session, _ = fight(5)
        block = features.projection(session)
        self.assertEqual(block["subclass"], "assassin")
        self.assertEqual({row["id"]: row["cost"] for row in block["cunning_strike"]["options"]}, {"poison": 1, "trip": 1, "withdraw": 1})
        self.assertEqual(block["cunning_strike"]["withdraw_max_ft"], economy.speed(session, "player") // 2)
        self.assertEqual(block["uncanny_dodge"], {"enabled": True, "reaction_available": True})
        self.assertEqual(block["cunning_action"]["dash"], {"available": True, "reason": None})

    def test_a_missing_kit_marks_only_poison_unavailable(self):
        session, _ = fight(5)
        session.world_state["inventory"].remove("Poisoner's Kit")
        options = {row["id"]: row for row in features.projection(session)["cunning_strike"]["options"]}
        self.assertEqual(options["poison"]["reason"], "cunning_strike_kit_required")
        self.assertTrue(options["trip"]["available"])

    def test_invalid_state_hides_the_block(self):
        session, _ = fight(3)
        del session.character["subclass_id"]
        self.assertIsNone(features.projection(session))

    def test_another_class_has_no_block(self):
        from api.tests.test_roadmap_c14_fighter import created as fighter
        self.assertIsNone(features.projection(fighter(1)))

    def test_outside_combat_the_block_reads_unavailable_without_changing_anything(self):
        session = created(5)
        before = copy.deepcopy(session.world_state)
        block = features.projection(session)
        self.assertFalse(block["steady_aim"]["available"])
        self.assertEqual(session.world_state, before)


if __name__ == "__main__":
    unittest.main()
