"""Paladin 1-5 effects through the existing owners: Lay On Hands, Divine Smite, Channel Divinity, Divine Sense, Sacred Weapon, styles, spells.

Numbers were read from the page renders (PHB 2024 PDF 108-110, 112/113, 264): Lay On Hands 5 x Paladin level, 5 points remove Poisoned;
Divine Smite 2d8 Radiant, +1d8 per slot level above 1, +1d8 against a Fiend or an Undead, one cast without a slot per Long Rest; Channel
Divinity two uses, one back on a Short Rest, all on a Long Rest; Divine Sense 10 minutes, 60 feet; Sacred Weapon Charisma modifier
(minimum +1) for 10 minutes. Dice are deterministic; synthetic NPCs are unit fixtures.
"""
import unittest
from unittest.mock import patch

import action_economy as economy
import character_progression as cp
import fighter_features
import paladin_features as features
import spell_scope
import weapon_attack as attacks
from combat_lifecycle import CombatRequestError
from api.tests.test_roadmap_c10_extra_attack import attack, follow, start_combat
from api.tests.test_roadmap_c16_paladin import created, earn, earned, roundtrip, spells, step


def fight(level=2, **two):
    session = created(level, **two)
    session.world_state["equipment"] = {"main_hand": "longsword", "off_hand": None}
    return session, start_combat(session)


def run(session, *steps):
    return economy.execute(session, {"steps": list(steps)})["action_economy_result"]["steps"]


def hit(session, npc, *steps, roll=19):
    with patch("game.roll_attack", return_value=roll):
        return run(session, *(steps or (attack(npc),)))


def smite(**extra):
    return {"kind": "divine_smite", "resource": "bonus", **extra}


def lay(**extra):
    return {"kind": "lay_on_hands", "resource": "bonus", **extra}


SENSE = {"kind": "divine_sense", "resource": "bonus"}


def wound(session, amount=20):
    session.character["max_hp"] = 60
    session.character["current_hp"] = max(1, 60 - amount)


def code_of(test, session, *steps):
    before = session._capture_runtime_snapshot()
    with test.assertRaises(CombatRequestError) as caught:
        run(session, *steps)
    test.assertEqual(session._capture_runtime_snapshot(), before, "a refusal changes nothing")
    return caught.exception.code


def clock(session, seconds):
    session.world_state["campaign_time"]["elapsed_seconds"] += seconds


class LayOnHands(unittest.TestCase):
    def test_the_pool_is_five_times_the_applied_level(self):
        for level in range(1, 6):
            self.assertEqual(features.projection(created(level))["lay_on_hands"]["pool_maximum"], 5 * level)

    def test_xp_alone_does_not_grow_the_pool(self):
        session = created()
        earn(session, 2)
        self.assertEqual(features.projection(session)["lay_on_hands"]["pool_maximum"], 5)

    def test_a_bonus_action_restores_up_to_the_pool(self):
        session, _ = fight(2)
        wound(session)
        before = session.character["current_hp"]
        result = run(session, lay(healing_amount=7))[0]["result"]
        self.assertEqual((result["healing"], result["pool_remaining"]), (7, 3))
        self.assertEqual(session.character["current_hp"], before + 7)
        self.assertTrue(economy.ensure(session)["player"]["bonus_action_spent"])
        self.assertEqual(code_of(self, session, lay(healing_amount=1)), "bonus_action_spent")

    def test_only_restored_points_leave_the_pool(self):
        session, _ = fight(2)
        wound(session, 3)
        result = run(session, lay(healing_amount=8))[0]["result"]
        self.assertEqual((result["healing"], result["pool_spent"], result["pool_remaining"]), (3, 3, 7))

    def test_the_pool_limits_a_touch(self):
        session, _ = fight(1)
        wound(session)
        self.assertEqual(code_of(self, session, lay(healing_amount=6)), "lay_on_hands_pool_exceeded")

    def test_full_hit_points_and_an_empty_touch_are_refused(self):
        session, _ = fight(1)
        self.assertEqual(code_of(self, session, lay(healing_amount=1)), "lay_on_hands_no_wounds")
        with self.assertRaises(CombatRequestError) as caught:
            economy.execute(session, {"steps": [lay()]})
        self.assertEqual(caught.exception.code, "invalid_paladin_command")

    def test_five_points_remove_poisoned_and_restore_nothing(self):
        session, _ = fight(1)
        wound(session)
        session.character["conditions"] = ["poisoned"]
        before = session.character["current_hp"]
        result = run(session, lay(remove_poisoned=True))[0]["result"]
        self.assertEqual((result["healing"], result["pool_spent"], result["pool_remaining"]), (0, 5, 0))
        self.assertEqual(session.character["current_hp"], before)
        self.assertNotIn("poisoned", session.character["conditions"])

    def test_remove_poisoned_needs_the_condition_and_the_points(self):
        session, _ = fight(1)
        self.assertEqual(code_of(self, session, lay(remove_poisoned=True)), "lay_on_hands_not_poisoned")
        session.character["conditions"] = ["poisoned"]
        session.character["paladin_uses"] = {**features.fresh_uses(), "lay_on_hands_spent": 1}
        self.assertEqual(code_of(self, session, lay(remove_poisoned=True)), "lay_on_hands_pool_exceeded")

    def test_outside_combat_there_is_no_turn_budget_and_the_pool_is_the_same(self):
        session = created(2)
        wound(session)
        result = features.lay_on_hands_outside_combat(session, 4, False)
        self.assertEqual(result["pool_remaining"], 6)
        session, _ = fight(2)
        with self.assertRaises(ValueError):
            features.lay_on_hands_outside_combat(session, 1, False)

    def test_out_of_turn_or_incapacitated_is_refused(self):
        session, _ = fight(2)
        wound(session)
        session.world_state["combat"]["current_actor_id"] = "someone"
        self.assertEqual(features._touch_reason(session), "lay_on_hands_current_combat_turn_required")
        session, _ = fight(2)
        wound(session)
        session.character["conditions"] = ["stunned"]
        self.assertEqual(code_of(self, session, lay(healing_amount=1)), "lay_on_hands_incapacitated")

    def test_a_long_rest_refills_and_a_short_rest_does_not(self):
        session = created(2)
        wound(session)
        features.lay_on_hands_outside_combat(session, 4, False)
        session.resolve_species_trait_action("short_rest")
        self.assertEqual(session.character["paladin_uses"]["lay_on_hands_spent"], 4)
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(session.character["paladin_uses"]["lay_on_hands_spent"], 0)


class DivineSmite(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(3)

    def damage(self, session, npc, **extra):
        with patch("game.roll_damage", return_value=6) as dice:
            result = run(session, smite(**extra))[0]["result"]
        return result, dice

    def test_a_melee_hit_opens_it_and_a_slot_pays_two_d_eight_radiant(self):
        hit(self.session, self.npc)
        before = self.npc["current_hp"]
        result, dice = self.damage(self.session, self.npc, slot_level=1)
        self.assertEqual(dice.call_args.args, (8, 2, 0))
        self.assertEqual((result["dice"], result["free_cast"], result["damage"]), (2, False, 6))
        self.assertEqual(self.npc["current_hp"], before - 6)
        self.assertEqual(spells(self.session)["slots"]["1"], 2)
        self.assertTrue(economy.ensure(self.session)["player"]["bonus_action_spent"])

    def test_the_free_cast_spends_no_slot_and_returns_on_a_long_rest(self):
        hit(self.session, self.npc)
        result, _ = self.damage(self.session, self.npc)
        self.assertTrue(result["free_cast"])
        self.assertEqual(spells(self.session)["slots"]["1"], 3)
        self.assertEqual(self.session.character["paladin_uses"]["free_smite_spent"], 1)
        features.rest_recovery(self.session, "short_rest")
        self.assertEqual(self.session.character["paladin_uses"]["free_smite_spent"], 1)
        features.rest_recovery(self.session, "long_rest")
        self.assertEqual(self.session.character["paladin_uses"]["free_smite_spent"], 0)

    def test_a_spent_free_cast_is_refused(self):
        self.session.character["paladin_uses"] = {**features.fresh_uses(), "free_smite_spent": 1}
        hit(self.session, self.npc)
        self.assertEqual(code_of(self, self.session, smite()), "divine_smite_free_cast_spent")

    def test_a_higher_slot_adds_a_die_and_a_fiend_or_undead_adds_another(self):
        session, npc = fight(5)
        hit(session, npc)
        npc["monster_stat_block"] = {"creature_type": "Undead"}
        result, dice = self.damage(session, npc, slot_level=2)
        self.assertEqual(dice.call_args.args, (8, 4, 0))
        self.assertEqual(result["dice"], 4)
        self.assertEqual(spells(session)["slots"], {"1": 4, "2": 1})

    def test_an_unknown_creature_type_adds_nothing(self):
        hit(self.session, self.npc)
        self.npc["monster_stat_block"] = {"creature_type": "humanoid"}
        _, dice = self.damage(self.session, self.npc, slot_level=1)
        self.assertEqual(dice.call_args.args, (8, 2, 0))

    def test_a_miss_or_no_attack_opens_nothing(self):
        self.assertEqual(code_of(self, self.session, smite()), "divine_smite_requires_a_melee_hit")
        hit(self.session, self.npc, roll=1)
        self.assertEqual(code_of(self, self.session, smite()), "divine_smite_requires_a_melee_hit")

    def test_a_ranged_weapon_opens_nothing(self):
        features.observe_attack(self.session, weapon={"kind": "ranged"}, target=self.npc["id"], landed=True)
        self.assertEqual(code_of(self, self.session, smite()), "divine_smite_requires_a_melee_hit")

    def test_any_other_step_closes_the_window(self):
        hit(self.session, self.npc)
        run(self.session, {"kind": "move", "distance_ft": 5})
        self.assertEqual(code_of(self, self.session, smite()), "divine_smite_requires_a_melee_hit")

    def test_one_slot_a_turn_is_shared_with_the_spell_owner(self):
        hit(self.session, self.npc)
        combat = self.session.world_state["combat"]
        spells(self.session)["slot_turn"] = [combat["combat_id"], combat["round"], economy.ensure(self.session)["player"]["attack_turn_counter"]]
        self.assertEqual(code_of(self, self.session, smite(slot_level=1)), "spell_slot_turn_limit")
        self.assertEqual(self.damage(self.session, self.npc)[0]["free_cast"], True, "the free cast spends no slot")

    def test_a_missing_slot_is_refused(self):
        hit(self.session, self.npc)
        self.assertEqual(code_of(self, self.session, smite(slot_level=2)), "spell_slot_unavailable")

    def test_silence_is_refused(self):
        hit(self.session, self.npc)
        self.session.character["conditions"] = ["silenced"]
        self.assertEqual(code_of(self, self.session, smite()), "spell_components_unavailable")

    def test_the_bonus_action_is_required(self):
        hit(self.session, self.npc)
        economy.ensure(self.session)["player"]["bonus_action_spent"] = True
        self.assertEqual(code_of(self, self.session, smite()), "bonus_action_spent")

    def test_level_one_needs_it_prepared_and_has_no_free_cast(self):
        session, npc = fight(1)
        hit(session, npc)
        self.assertEqual(code_of(self, session, smite(slot_level=1)), "divine_smite_not_available")
        spells(session)["prepared"][-1] = "Divine Smite"
        session.character["spells"] = list(spells(session)["prepared"])
        self.assertEqual(code_of(self, session, smite()), "divine_smite_free_cast_spent")
        self.assertEqual(run(session, smite(slot_level=1))[0]["result"]["dice"], 2)

    def test_a_defeated_target_is_gone(self):
        hit(self.session, self.npc)
        self.npc["current_hp"] = 0
        self.assertEqual(code_of(self, self.session, smite()), "divine_smite_target_gone")

    def test_it_closes_the_combat_when_it_finishes_the_last_enemy(self):
        hit(self.session, self.npc)
        self.npc["current_hp"] = 3
        self.damage(self.session, self.npc)
        self.assertEqual(self.npc["current_hp"], 0)
        self.assertFalse(self.session.world_state["combat"]["active"])

    def test_resistance_uses_the_radiant_owner(self):
        hit(self.session, self.npc)
        with patch("weapon_attack.mitigate", return_value={"final_damage": 3}) as owner:
            self.damage(self.session, self.npc)
        self.assertEqual(owner.call_args.args[2], "radiant")

    def test_a_smite_command_rides_alone(self):
        for steps in ([smite(), smite()], [attack(self.npc), smite()]):
            with self.assertRaises(CombatRequestError) as caught:
                economy.execute(self.session, {"steps": steps})
            self.assertEqual(caught.exception.code, "invalid_paladin_command")

    def test_the_window_survives_a_round_trip(self):
        hit(self.session, self.npc)
        fresh, _ = roundtrip(self.session)
        self.assertEqual(features.projection(fresh)["divine_smite"]["target_id"], self.npc["id"])


class ChannelDivinity(unittest.TestCase):
    def test_two_uses_from_level_three_and_none_before(self):
        self.assertIsNone(features.projection(created(2))["channel_divinity"])
        self.assertEqual(features.projection(created(3))["channel_divinity"], {"uses_remaining": 2, "max_uses": 2})

    def test_a_short_rest_returns_one_and_a_long_rest_all(self):
        session = created(3)
        session.character["paladin_uses"] = {**features.fresh_uses(), "channel_divinity_spent": 2}
        session.resolve_species_trait_action("short_rest")
        self.assertEqual(session.character["paladin_uses"]["channel_divinity_spent"], 1)
        session.character["paladin_uses"]["channel_divinity_spent"] = 2
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(session.character["paladin_uses"]["channel_divinity_spent"], 0)

    def test_forged_uses_refuse_the_rest(self):
        session = created(3)
        session.character["paladin_uses"] = {**features.fresh_uses(), "channel_divinity_spent": 9}
        with self.assertRaises(ValueError):
            session.resolve_species_trait_action("short_rest")


class DivineSense(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(3)

    def test_a_bonus_action_spends_one_use_for_ten_minutes(self):
        result = run(self.session, SENSE)[0]["result"]
        self.assertEqual((result["remaining_seconds"], result["uses_remaining"]), (600, 1))
        self.assertTrue(economy.ensure(self.session)["player"]["bonus_action_spent"])
        self.assertTrue(features.divine_sense_active(self.session))
        clock(self.session, 599)
        self.assertTrue(features.divine_sense_active(self.session))
        clock(self.session, 1)
        self.assertFalse(features.divine_sense_active(self.session))

    def test_it_reports_only_the_sourced_types_within_sixty_feet(self):
        run(self.session, SENSE)
        self.npc["monster_stat_block"] = {"creature_type": "Fiend"}
        self.assertEqual(features.projection(self.session)["divine_sense"]["detected"],
                         [{"target_id": self.npc["id"], "creature_type": "fiend", "distance_ft": 5}])
        self.npc["monster_stat_block"] = {"creature_type": "humanoid"}
        self.assertEqual(features.detected(self.session), [])
        self.npc["monster_stat_block"] = {"creature_type": "undead"}
        with patch("weapon_attack.pair", return_value={"distance_ft": 61}):
            self.assertEqual(features.detected(self.session), [])
        with patch("weapon_attack.pair", return_value={"distance_ft": 60}):
            self.assertEqual(len(features.detected(self.session)), 1)

    def test_incapacitated_ends_it_for_good(self):
        run(self.session, SENSE)
        self.session.character["conditions"] = ["stunned"]
        self.assertFalse(features.divine_sense_active(self.session))
        features.settle(self.session)
        self.session.character["conditions"] = []
        self.assertFalse(features.divine_sense_active(self.session))

    def test_uses_and_level_are_required(self):
        self.session.character["paladin_uses"] = {**features.fresh_uses(), "channel_divinity_spent": 2}
        self.assertEqual(code_of(self, self.session, SENSE), "channel_divinity_uses_exhausted")
        session, _ = fight(2)
        self.assertEqual(code_of(self, session, SENSE), "divine_sense_not_available")

    def test_outside_combat_it_starts_without_a_turn(self):
        session = created(3)
        self.assertEqual(features.divine_sense_outside_combat(session)["uses_remaining"], 1)
        self.assertTrue(features.divine_sense_active(session))


class SacredWeapon(unittest.TestCase):
    def setUp(self):
        self.session, self.npc = fight(3)
        self.session.character.update(charisma=16, charisma_mod=3)

    def bonus(self, **choice):
        economy.ensure(self.session)["player"]["attack_action"] = {"remaining_attacks": 1, "total_attacks": 2, "action_resource_cost": 1}
        return attacks.prepare(self.session, "player", self.npc["id"], "longsword", choice, origin="continuation")["attack_bonus"]

    def test_the_first_attack_spends_a_use_and_adds_charisma_for_ten_minutes(self):
        plain = self.bonus()
        with patch("game.roll_attack", return_value=19):
            step = run(self.session, attack(self.npc, sacred_weapon=True))[0]
        self.assertEqual(step["result"]["attack_bonus"], plain + 3)
        self.assertEqual(self.session.character["paladin_uses"]["channel_divinity_spent"], 1)
        self.assertEqual(self.session.character["paladin_uses"]["sacred_weapon"]["weapon_id"], "longsword")
        self.assertEqual(self.bonus(), plain + 3, "it stays on the weapon")
        clock(self.session, 600)
        self.assertEqual(self.bonus(), plain)

    def test_the_minimum_bonus_is_one(self):
        self.session.character.update(charisma=8, charisma_mod=-1)
        plain = self.bonus()
        self.assertEqual(self.bonus(sacred_weapon=True), plain + 1)

    def test_preparing_alone_spends_nothing(self):
        self.bonus(sacred_weapon=True)
        self.assertNotIn("paladin_uses", self.session.character)

    def test_radiant_is_a_choice_on_a_hit_with_the_imbued_weapon(self):
        with patch("game.roll_attack", return_value=19):
            first = run(self.session, attack(self.npc, sacred_weapon=True))[0]["result"]
        self.assertEqual(first["damage_type"], "slashing")
        session, npc = fight(5)
        with patch("game.roll_attack", return_value=19):
            steps = run(session, attack(npc, sacred_weapon=True, radiant_damage=True), follow(npc))
        self.assertEqual(steps[0]["result"]["damage_type"], "radiant")
        self.assertEqual(steps[1]["result"]["damage_type"], "slashing")

    def test_radiant_without_the_effect_is_refused(self):
        self.assertEqual(code_of(self, self.session, attack(self.npc, radiant_damage=True)), "sacred_weapon_not_active")

    def test_another_weapon_gains_nothing(self):
        self.session.character["paladin_uses"] = {**features.fresh_uses(), "sacred_weapon": {
            "until": self.session.world_state["campaign_time"]["elapsed_seconds"] + 600, "weapon_id": "dagger"}}
        self.assertEqual(attacks.prepare(self.session, "player", self.npc["id"], "longsword", {})["attack_modifiers"], [])

    def test_a_use_is_required_and_the_oath_too(self):
        self.session.character["paladin_uses"] = {**features.fresh_uses(), "channel_divinity_spent": 2}
        self.assertEqual(code_of(self, self.session, attack(self.npc, sacred_weapon=True)), "channel_divinity_uses_exhausted")
        session, npc = fight(2)
        self.assertEqual(code_of(self, session, attack(npc, sacred_weapon=True)), "sacred_weapon_not_available")

    def test_using_it_again_replaces_the_effect(self):
        with patch("game.roll_attack", return_value=19):
            run(self.session, attack(self.npc, sacred_weapon=True))
        clock(self.session, 100)
        self.session.character["paladin_uses"]["sacred_weapon"]["until"] -= 0
        features.begin_sacred_weapon(self.session, {"instance_id": "dagger"})
        self.assertEqual(self.session.character["paladin_uses"]["sacred_weapon"]["weapon_id"], "dagger")

    def test_other_classes_cannot_ask_for_it(self):
        from api.tests.test_roadmap_c14_fighter import created as fighter
        session = fighter()
        session.world_state["equipment"] = {"main_hand": "longsword", "off_hand": None}
        npc = start_combat(session)
        self.assertEqual(code_of(self, session, attack(npc, sacred_weapon=True)), "sacred_weapon_not_available")

    def test_the_effect_round_trips(self):
        with patch("game.roll_attack", return_value=19):
            run(self.session, attack(self.npc, sacred_weapon=True))
        fresh, _ = roundtrip(self.session)
        self.assertTrue(features.projection(fresh)["sacred_weapon"]["active"])


class SharedOwners(unittest.TestCase):
    def test_extra_attack_comes_from_the_shared_owner(self):
        session, npc = fight(5)
        steps = hit(session, npc, attack(npc), follow(npc))
        self.assertEqual([step["action_resource_cost"] for step in steps], [1, 0])
        with self.assertRaises(CombatRequestError):
            hit(session, npc, follow(npc))

    def test_xp_level_five_alone_has_one_attack(self):
        session = earned(self, 4)
        earn(session, 5)
        session.world_state["equipment"] = {"main_hand": "longsword", "off_hand": None}
        npc = start_combat(session)
        with self.assertRaises(CombatRequestError):
            hit(session, npc, attack(npc), follow(npc))

    def test_a_held_style_reaches_the_attack_owner_from_level_two_only(self):
        session, npc = fight(2, fighting_style="Dueling")
        context = attacks.prepare(session, "player", npc["id"], "longsword", {})
        self.assertEqual(context["damage_modifiers"], [{"source": "fighting_style_dueling", "value": 2}])
        self.assertEqual(fighter_features.style(session.character), "Dueling")
        blessed, other = fight(2, fighting_style="Blessed Warrior", cantrips=["Guidance", "Sacred Flame"])
        self.assertEqual(attacks.prepare(blessed, "player", other["id"], "longsword", {})["damage_modifiers"], [])

    def test_sacred_flame_is_cast_with_charisma_from_the_blessed_warrior_route(self):
        session, npc = fight(2, fighting_style="Blessed Warrior", cantrips=["Guidance", "Sacred Flame"])
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        session.character.update(charisma=16, charisma_mod=3)
        npc["dexterity_save_bonus"] = 0
        seen = {"distance_ft": 5, "attacker_sees_target": True, "target_sees_attacker": True}
        with patch("game.roll_d20", return_value=1), patch("game.roll_damage", return_value=4), patch("weapon_attack.pair", return_value=seen):
            result = spell_scope.cast(session, "Sacred Flame", npc["id"])
        self.assertEqual(result["spell_save_dc"], 8 + 3 + 2)
        self.assertEqual(result["damage"], 4)
        with self.assertRaises(CombatRequestError) as caught, patch("weapon_attack.pair", return_value=seen):
            spell_scope.cast(session, "Guidance", npc["id"])
        self.assertEqual(caught.exception.code, "unsupported_spell")

    def test_cure_wounds_uses_a_table_slot_at_a_higher_level(self):
        session, npc = fight(3)
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        wound(session)
        result = spell_scope.cast(session, "Cure Wounds", "player")
        self.assertGreater(result["healing"], 0)
        self.assertEqual(spells(session)["slots"]["1"], 2)

    def test_a_catalog_only_spell_prepares_but_never_casts(self):
        session, npc = fight(2)
        session.world_state["equipment"] = {"main_hand": None, "off_hand": None}
        before = session._capture_runtime_snapshot()
        with self.assertRaises(CombatRequestError) as caught:
            spell_scope.cast(session, "Bless", "player")
        self.assertEqual(caught.exception.code, "unsupported_spell")
        self.assertEqual(session._capture_runtime_snapshot(), before)
        rows = {row["id"]: row["castable"] for row in features.projection(session)["prepared_spells"]}
        self.assertEqual(rows, {"Cure Wounds": True, "Command": False, "Bless": False})

    def test_a_long_rest_restores_table_slots_and_a_short_rest_does_not(self):
        session = created(5)
        spells(session)["slots"] = {"1": 0, "2": 0}
        session.resolve_species_trait_action("short_rest")
        self.assertEqual(spells(session)["slots"], {"1": 0, "2": 0})
        session.resolve_species_trait_action("long_rest")
        self.assertEqual(spells(session)["slots"], {"1": 4, "2": 2})

    def test_always_prepared_follows_the_level_and_the_oath(self):
        self.assertEqual(features.projection(created(1))["always_prepared"], [])
        self.assertEqual(features.projection(created(2))["always_prepared"], ["Divine Smite"])
        self.assertEqual(sorted(features.projection(created(5))["always_prepared"]),
                         sorted(["Divine Smite", "Find Steed", "Protection from Evil and Good", "Shield of Faith", "Aid", "Zone of Truth"]))

    def test_disclosure_names_what_is_not_done(self):
        text = " ".join(cp.progression_effects_pending("Paladin", 5))
        for word in ("Weapon Mastery", "catalog-only", "Find Steed", "Critical Hit", "replacing a spell"):
            self.assertIn(word, text)

    def test_invalid_state_hides_the_controls(self):
        session = created(3)
        session.character["paladin_uses"] = {"broken": True}
        self.assertIsNone(features.projection(session))

    def test_other_classes_have_no_block(self):
        from api.tests.test_roadmap_c14_fighter import created as fighter
        self.assertIsNone(features.projection(fighter()))


if __name__ == "__main__":
    unittest.main()
