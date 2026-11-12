"""Dilim 4C Task 4b: engine resolvers for Ray of Frost, Shocking Grasp, Toll the Dead, Healing Word and Bless, and the
player's Concentration. The engine rolls every die (patched here only to fix them); the model only narrates.

Book wins over the design (4C.4a page-cited leaves): Shocking Grasp blocks only Opportunity Attacks; a successful save
against Toll the Dead takes no damage; Healing Word is V only with a seen target; Bless adds to attack rolls and saving
throws, not ability checks; Concentration ends when the caster is Incapacitated and may be dropped at will (no action).
Engine readings pinned here as ledger Rulings (UNVERIFIED by a page): Bless's minute = 60 seconds of the fight clock;
one Concentration save per damage instance; a negative Healing Word total heals 0 (Cure Wounds' reading).
Fixture: test_spell_scope.caster (fixed session seed 17; no campaign, no town)."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import action_economy
import combat_lifecycle
import spell_concentration
import spell_scope
import weapon_attack
from api.tests.test_spell_scope import caster

CombatRequestError = combat_lifecycle.CombatRequestError


def wizard():
    s, enemy = caster(cls="Wizard")
    state = s.world_state["spellcasting_v1"]
    state["cantrips"] = s.character["cantrips"] = ["Fire Bolt", "Ray of Frost", "Shocking Grasp"]
    enemy["speed_ft"] = 30
    return s, enemy


def cleric(prepared=("Bless", "Healing Word")):
    s, enemy = caster(cls="Cleric")
    state = s.world_state["spellcasting_v1"]
    state["cantrips"] = s.character["cantrips"] = ["Sacred Flame", "Toll the Dead", "Guidance"]
    state["prepared"] = list(prepared)
    s.character.update(max_hp=40, current_hp=40, conditions=[])
    spell_scope.validate(state, s.character)
    return s, enemy


def magic(spell, target, **extra):
    return {"steps": [{"kind": "magic", "ability": spell, "target_id": target, **extra}]}


def turn(s, command, *, d20=10, dice=4, message="Hamle."):
    with patch("game.roll_d20", return_value=d20), patch.object(s.rng, "randint", return_value=dice):
        return s.run_player_turn(message, combat_action=command)


def typed(s, message, target_id=None, *, d20=10, dice=4):
    with patch("game.roll_d20", return_value=d20), patch.object(s.rng, "randint", return_value=dice):
        return s.run_player_turn(message, target_id=target_id)


def held(s):
    return copy.deepcopy((s.world_state, s.character))


def refused(test, s, command, code):
    before = held(s)
    with test.assertRaises(CombatRequestError) as raised:
        turn(s, command)
    test.assertEqual(raised.exception.code, code)
    test.assertEqual(held(s), before)


def next_turn(s, actor="player"):
    for _ in range(12):
        s.advance_combat_turn()
        if s.world_state["combat"]["current_actor_id"] == actor:
            return
    raise AssertionError(actor)


def at_reach(s, enemy, feet=5):
    enemy["distance_ft"] = feet
    s.world_state["attack_environment"]["pairs"][f"player|{enemy['id']}"]["distance_ft"] = feet


class RayOfFrost(unittest.TestCase):
    def test_a_hit_deals_cold_and_slows_until_the_casters_next_turn(self):
        s, enemy = wizard()
        before_speed = action_economy.speed(s, enemy["id"])
        result = turn(s, magic("Ray of Frost", enemy["id"]), d20=19, dice=6)
        fields = result["action_result"]
        self.assertEqual((fields["spell"], fields["damage_type"], fields["damage"], fields["slot_spent"]),
                         ("Ray of Frost", "cold", 6, False))
        self.assertEqual(enemy["current_hp"], 94)
        self.assertEqual(before_speed - action_economy.speed(s, enemy["id"]), 10)
        self.assertIn("10 fit", result["narration"])
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 2})
        next_turn(s, enemy["id"])
        self.assertEqual(s.world_state["combat"]["turn_resources"][enemy["id"]]["movement_available"], 20)
        next_turn(s)
        self.assertEqual(spell_scope.speed_penalty(s, enemy["id"]), 0)

    def test_a_miss_leaves_no_rider(self):
        s, enemy = wizard()
        result = turn(s, magic("Ray of Frost", enemy["id"]), d20=1)
        self.assertEqual(result["action_result"]["damage"], 0)
        self.assertEqual(spell_scope.speed_penalty(s, enemy["id"]), 0)
        self.assertEqual([e for e in s.world_state.get("attack_effects", []) if e["kind"] in spell_scope.RIDERS], [])

    def test_two_rays_never_stack(self):
        s, enemy = wizard()
        turn(s, magic("Ray of Frost", enemy["id"]), d20=19)
        next_turn(s)
        turn(s, magic("Ray of Frost", enemy["id"]), d20=19)
        rays = [e for e in s.world_state["attack_effects"] if e["kind"] == spell_scope.RAY_OF_FROST_EFFECT]
        self.assertEqual(len(rays), 1)
        self.assertEqual(spell_scope.speed_penalty(s, enemy["id"]), 10)

    def test_a_ranged_spell_attack_next_to_a_foe_is_refused_unchanged(self):
        s, enemy = wizard()
        at_reach(s, enemy)
        refused(self, s, magic("Ray of Frost", enemy["id"]), "unsupported_spell_attack_mode")

    def test_beyond_sixty_feet_is_out_of_range(self):
        s, enemy = wizard()
        at_reach(s, enemy, 65)
        refused(self, s, magic("Ray of Frost", enemy["id"]), "spell_out_of_range")

    def test_the_rider_saves_and_a_forged_rider_is_refused(self):
        s, enemy = wizard()
        turn(s, magic("Ray of Frost", enemy["id"]), d20=19)
        saved = s.serialize_game_state()
        s._validate_save_payload(copy.deepcopy(saved))
        forged = copy.deepcopy(saved)
        next(e for e in forged["world_state"]["attack_effects"]
             if e["kind"] == spell_scope.RAY_OF_FROST_EFFECT)["source_actor"] = enemy["id"]
        with self.assertRaises(ValueError):
            s._validate_save_payload(forged)


class ShockingGrasp(unittest.TestCase):
    def test_a_hit_blocks_only_opportunity_attacks_until_the_targets_next_turn(self):
        s, enemy = wizard()
        at_reach(s, enemy)  # a melee spell attack: a foe at 5 ft is no "close hostile" problem
        result = turn(s, magic("Shocking Grasp", enemy["id"]), d20=19, dice=5)
        self.assertEqual((result["action_result"]["damage_type"], result["action_result"]["damage"]), ("lightning", 5))
        self.assertTrue(spell_scope.opportunity_attacks_blocked(s, enemy["id"]))
        self.assertTrue(action_economy.can_act(s, enemy["id"]))  # its other Reactions stay
        self.assertIn("Fırsat Saldırısı", result["narration"])
        saved = s.serialize_game_state()
        s._validate_save_payload(copy.deepcopy(saved))
        next_turn(s, enemy["id"])
        self.assertFalse(spell_scope.opportunity_attacks_blocked(s, enemy["id"]))

    def test_out_of_touch_is_refused_unchanged(self):
        s, enemy = wizard()
        refused(self, s, magic("Shocking Grasp", enemy["id"]), "spell_out_of_range")

    def test_the_creation_text_tells_the_book_rider(self):
        from api.dnd_2024_rules import SPELLS_CATALOG
        for cls in ("Wizard", "Sorcerer"):
            entry = next(s for s in SPELLS_CATALOG[cls]["cantrips"] if s["id"] == "Shocking Grasp")
            self.assertIn("Fırsat Saldırısı yapamaz", entry["desc"])
            self.assertNotIn("tepki", entry["desc"])


class TollTheDead(unittest.TestCase):
    def test_a_successful_wisdom_save_takes_no_damage(self):
        s, enemy = cleric()
        result = turn(s, magic("Toll the Dead", enemy["id"]), d20=19)
        fields = result["action_result"]
        self.assertEqual((fields["attack_or_save"], fields["save_dc"], fields["damage"]), ("save", 13, 0))
        self.assertEqual(enemy["current_hp"], 100)
        self.assertEqual(result["action_result"]["economy_steps"][0]["result"]["resolution"]["ability"], "wisdom")

    def test_a_wounded_target_takes_the_d12(self):
        s, enemy = cleric()
        enemy["current_hp"] = 99
        result = typed(s, "Ölüm çanı büyüsünü atıyorum", enemy["id"], d20=2, dice=11)
        step = result["action_result"]["economy_steps"][0]["result"]
        self.assertEqual((step["damage_die"], step["damage"], step["damage_type"]), (12, 11, "necrotic"))
        self.assertEqual(enemy["current_hp"], 88)

    def test_an_unsourced_wisdom_save_is_refused_unchanged(self):
        s, enemy = cleric()
        enemy["monster_stat_block"]["ability_modifiers"]["wisdom"] = 2
        refused(self, s, magic("Toll the Dead", enemy["id"]), "spell_save_modifier_unknown")

    def test_toll_the_dead_is_harmful_and_the_buffs_are_not(self):
        self.assertEqual({name for name in ("Ray of Frost", "Shocking Grasp", "Toll the Dead", "Healing Word", "Bless")
                          if spell_scope.harmful(name)}, {"Ray of Frost", "Shocking Grasp", "Toll the Dead"})


class HealingWord(unittest.TestCase):
    def test_a_bonus_action_heal_with_the_action_still_free(self):
        s, enemy = cleric()
        s.character["current_hp"] = 10
        healed = turn(s, magic("Healing Word", "player"), dice=3)
        fields = healed["action_result"]
        self.assertEqual((fields["spell"], fields["healing"], fields["heal_source"], fields["slot_spent"]),
                         ("Healing Word", 9, "spell", True))  # 2d4 (3+3) + Wisdom 3
        resources = action_economy.ensure(s)["player"]
        self.assertEqual((resources["bonus_action_spent"], resources["base_action_spent"]), (True, False))
        cantrip = turn(s, magic("Toll the Dead", enemy["id"]), d20=2, dice=4)
        self.assertEqual(cantrip["action_result"]["damage"], 4)
        self.assertTrue(action_economy.ensure(s)["player"]["base_action_spent"])

    def test_a_second_leveled_spell_on_the_turn_is_refused_unchanged(self):
        s, enemy = cleric()
        s.character["current_hp"] = 10
        turn(s, magic("Healing Word", "player"))
        refused(self, s, magic("Bless", "player"), "spell_slot_turn_limit")

    def test_a_second_bonus_action_is_refused_unchanged(self):
        s, enemy = cleric()
        s.character["current_hp"] = 10
        action_economy.ensure(s)["player"]["bonus_action_spent"] = True
        refused(self, s, magic("Healing Word", "player"), "bonus_action_spent")

    def test_verbal_only_needs_no_free_hand(self):
        s, enemy = cleric()
        s.character["current_hp"] = 10
        s.world_state["equipment"] = {"main_hand": "mace", "off_hand": "shield"}
        self.assertEqual(turn(s, magic("Healing Word", "player"))["action_result"]["spell"], "Healing Word")
        next_turn(s)
        refused(self, s, magic("Bless", "player"), "spell_components_unavailable")

    def test_a_typed_bonus_action_heal(self):
        s, enemy = cleric()
        s.character["current_hp"] = 10
        result = typed(s, "Bonus eylemle şifa sözü büyüsünü kendime yapıyorum", dice=2)
        self.assertEqual(result["action_result"]["spell"], "Healing Word")
        self.assertEqual(s.character["current_hp"], 17)

    def test_only_the_player_has_a_healing_owner(self):
        s, enemy = cleric()
        refused(self, s, magic("Healing Word", enemy["id"]), "unsupported_spell_mode")

    def test_a_higher_slot_adds_two_d4(self):
        s, enemy = cleric()
        s.character.update(level=3, progression_level=3, current_hp=5)
        import character_progression
        s.world_state["spellcasting_v1"]["slots"] = character_progression.slot_capacity(s.character)
        result = turn(s, magic("Healing Word", "player", slot_level=2), dice=1)
        self.assertEqual(result["action_result"]["healing"], 7)  # 4d4 (all 1) + 3
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["2"], 1)

    def test_a_negative_total_heals_nothing_ruling_unverified(self):
        s, enemy = cleric()
        s.character.update(wisdom=6, current_hp=10)  # modifier -2; 2d4 of 1 and 1 = 0
        result = turn(s, magic("Healing Word", "player"), dice=1)
        self.assertEqual(result["action_result"]["healing"], 0)
        self.assertEqual(s.character["current_hp"], 10)


class Bless(unittest.TestCase):
    def blessed(self):
        s, enemy = cleric()
        result = turn(s, magic("Bless", "player"))
        return s, enemy, result

    def test_bless_starts_concentration_and_spends_the_action_and_a_slot(self):
        s, enemy, result = self.blessed()
        held_spell = spell_concentration.current(s.world_state)
        self.assertEqual((held_spell["spell_id"], held_spell["targets"], held_spell["slot_level"]), ("Bless", ["player"], 1))
        self.assertEqual(held_spell["combat_id"], s.world_state["combat"]["combat_id"])
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"], {"1": 1})
        self.assertTrue(action_economy.ensure(s)["player"]["base_action_spent"])
        self.assertIn("1d4", result["narration"])

    def test_a_blessed_save_adds_the_d4_and_an_ability_check_does_not(self):
        s, enemy, _ = self.blessed()
        with patch("game.roll_d20", return_value=10), patch.object(s.rng, "randint", return_value=4):
            save = weapon_attack.save(s, "player", ["wisdom"], 10)
        self.assertEqual(save["bless_roll"], 4)
        unblessed, _ = cleric()
        with patch("game.roll_d20", return_value=10):
            plain = weapon_attack.save(unblessed, "player", ["wisdom"], 10)
        self.assertEqual(save["total"], plain["total"] + 4)

    def test_bless_at_a_foe_and_a_higher_slot_are_refused_unchanged(self):
        s, enemy = cleric()
        refused(self, s, magic("Bless", enemy["id"]), "unsupported_spell_mode")
        refused(self, s, magic("Bless", "player", slot_level=2), "unsupported_spell_mode")

    def test_a_second_bless_ends_the_first(self):
        s, enemy, _ = self.blessed()
        first = copy.deepcopy(spell_concentration.current(s.world_state))
        next_turn(s)
        again = turn(s, magic("Bless", "player"))
        self.assertNotEqual(spell_concentration.current(s.world_state), first)
        self.assertIn("konsantrasyonun biter", again["narration"])

    def test_dropping_concentration_is_free_and_typed(self):
        s, enemy, _ = self.blessed()
        next_turn(s)
        resources = copy.deepcopy(action_economy.ensure(s)["player"])
        dropped = typed(s, "Konsantrasyonu bırakıyorum")
        self.assertIsNone(spell_concentration.current(s.world_state))
        self.assertEqual(action_economy.ensure(s)["player"], resources)
        self.assertIn("Eylem harcanmaz", dropped["narration"])
        before = held(s)
        with self.assertRaises(CombatRequestError) as raised:
            typed(s, "Konsantrasyonu bırakıyorum")
        self.assertEqual(raised.exception.code, "concentration_not_held")
        self.assertEqual(held(s), before)

    def test_the_fight_ending_ends_it(self):
        s, enemy, _ = self.blessed()
        s.end_combat("test")
        self.assertIsNone(spell_concentration.current(s.world_state))

    def test_incapacitated_ends_it_at_the_next_turn_start_and_the_d4_stops_at_once(self):
        s, enemy, _ = self.blessed()
        s.character["conditions"] = ["stunned"]
        self.assertFalse(spell_concentration.blessed(s, "player"))
        next_turn(s, enemy["id"])
        self.assertIsNone(spell_concentration.current(s.world_state))

    def test_the_minute_is_ten_rounds_ruling_unverified(self):
        s, enemy, _ = self.blessed()
        for _ in range(9):
            next_turn(s)
        self.assertEqual(s.world_state["combat"]["round"], 10)
        self.assertIsNotNone(spell_concentration.holds(s))
        next_turn(s)
        self.assertIsNone(spell_concentration.current(s.world_state))  # round 11: the minute is over

    def test_damage_asks_a_constitution_save_once_per_instance(self):
        s, enemy, _ = self.blessed()
        with patch("game.roll_d20", return_value=2), patch.object(s.rng, "randint", return_value=1):
            first = s._apply_attack_damage_to_player(5, False, True)
        self.assertEqual({k: first["concentration_check"][k] for k in ("dc", "kept")}, {"dc": 10, "kept": False})
        self.assertIsNone(spell_concentration.current(s.world_state))
        with patch("game.roll_d20", return_value=2):
            second = s._apply_attack_damage_to_player(5, False, True)
        self.assertNotIn("concentration_check", second)

    def test_a_kept_save_is_told_and_zero_hit_points_end_it(self):
        s, enemy, _ = self.blessed()
        with patch("game.roll_d20", return_value=18), patch.object(s.rng, "randint", return_value=1):
            kept = s._apply_attack_damage_to_player(24, False, True)
        self.assertEqual({k: kept["concentration_check"][k] for k in ("dc", "kept")}, {"dc": 12, "kept": True})
        text = s._enemy_exchange_text([{"outcome": "hit", "damage": 24, "actor_id": enemy["id"],
                                        "concentration_check": kept["concentration_check"]}])
        self.assertIn("Konsantrasyonunu korursun", text)
        down = s._apply_attack_damage_to_player(20, False, True)  # 16 HP left: 0 HP, not massive damage
        self.assertEqual(down["target_status"], "unconscious")
        self.assertEqual({k: down["concentration_check"][k] for k in ("kept", "reason")}, {"kept": False, "reason": "incapacitated"})
        self.assertIsNone(spell_concentration.current(s.world_state))

    def test_concentration_saves_and_a_forged_record_is_refused_and_a_stale_one_loads(self):
        s, enemy, _ = self.blessed()
        saved = s.serialize_game_state()
        s._validate_save_payload(copy.deepcopy(saved))
        forged = copy.deepcopy(saved)
        forged["world_state"]["spell_concentration_v1"]["targets"] = [enemy["id"]]
        with self.assertRaises(ValueError):
            s._validate_save_payload(forged)
        stale = copy.deepcopy(saved)
        stale["world_state"]["spell_concentration_v1"]["combat_id"] = "an-old-fight"
        s._validate_save_payload(stale)  # a finished fight's record never holds; it must not lock the campaign

    def test_bless_and_healing_word_at_a_surrendered_fight_are_never_asked(self):
        s, enemy = cleric()
        command = magic("Bless", "player")
        with patch("action_economy._surrendered", return_value=True):
            self.assertIsNone(combat_lifecycle.surrendered_strike_question(s, "Hamle.", None, command))


if __name__ == "__main__":
    unittest.main()
