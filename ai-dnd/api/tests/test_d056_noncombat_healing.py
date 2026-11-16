"""D-056: Cure Wounds and Healing Word work outside a fight (Kadir 2026-11-15).

Rule (PHB 2024): Cure Wounds 2d8 + modifier, Healing Word 2d4 + modifier (+2d4 per slot level above 1); both spend a
slot. Outside a fight there is no turn: no action or Bonus Action is spent and the one-slot-per-turn limit does not
apply. In a fight the behavior is unchanged (test_dilim4c_spell_resolvers). The only creature healed outside a fight
is the player (the same target owner as in a fight). The first slot spell cast outside a fight closes a Long Rest
preparation window (D-038).
Fixtures: test_dilim4c_spell_resolvers.cleric (fixed session seed; no campaign, no town)."""
from __future__ import annotations

import unittest

import spell_preparation
import spell_scope
from combat_lifecycle import CombatRequestError
from api.tests.test_dilim4c_spell_resolvers import cleric, held, magic, turn, typed


def calm_cleric(prepared=("Bless", "Cure Wounds", "Healing Word"), hp=10):
    s, enemy = cleric(prepared=prepared)
    s.end_combat("test_setup")
    s.character["current_hp"] = hp
    return s, enemy


class NonCombatHealing(unittest.TestCase):
    def test_cure_wounds_heals_and_spends_one_slot_with_no_fight(self):
        s, _ = calm_cleric()
        slots = s.world_state["spellcasting_v1"]["slots"]["1"]
        result = turn(s, magic("Cure Wounds", "player"), dice=4)
        self.assertFalse(s.world_state["combat"]["active"])
        self.assertEqual(s.character["current_hp"], 10 + 4 + 4 + 3)  # 2d8 (4+4) + Wisdom 3
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], slots - 1)
        action = result["action_result"]
        self.assertEqual((action["spell"], action["healing"], action["heal_source"], action["slot_spent"]),
                         ("Cure Wounds", 11, "spell", True))

    def test_healing_word_heals_with_no_fight_and_spends_no_action(self):
        s, _ = calm_cleric()
        turn(s, magic("Healing Word", "player"), dice=3)
        self.assertEqual(s.character["current_hp"], 10 + 3 + 3 + 3)  # 2d4 (3+3) + Wisdom 3
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 1)
        economy = s.world_state.get("action_economy", {}).get("player", {})
        self.assertFalse(economy.get("bonus_action_spent"))
        self.assertFalse(economy.get("base_action_spent"))

    def test_two_slot_spells_in_a_row_are_fine_with_no_turn(self):
        s, _ = calm_cleric(hp=5)
        turn(s, magic("Cure Wounds", "player"), dice=1)
        turn(s, magic("Healing Word", "player"), dice=1)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 0)
        self.assertEqual(s.character["current_hp"], 5 + (1 + 1 + 3) + (1 + 1 + 3))

    def test_a_typed_line_casts_it_with_no_target_named(self):
        s, _ = calm_cleric()
        result = typed(s, "Cure Wounds büyüsünü kendime yapıyorum", dice=4)
        self.assertEqual(result["action_result"]["spell"], "Cure Wounds")
        self.assertEqual(s.character["current_hp"], 21)

    def test_no_slot_left_refuses_and_changes_nothing(self):
        s, _ = calm_cleric()
        s.world_state["spellcasting_v1"]["slots"]["1"] = 0
        before = held(s)
        with self.assertRaises(CombatRequestError) as raised:
            turn(s, magic("Cure Wounds", "player"))
        self.assertEqual(raised.exception.code, "spell_slot_unavailable")
        self.assertEqual(held(s), before)

    def test_another_creature_is_no_target_outside_a_fight(self):
        s, enemy = calm_cleric()
        before = held(s)
        with self.assertRaises(CombatRequestError):
            turn(s, magic("Cure Wounds", enemy["id"]))
        self.assertEqual(held(s), before)

    def test_a_damage_spell_outside_a_fight_is_still_refused(self):
        s, enemy = calm_cleric()
        before = held(s)
        with self.assertRaises(CombatRequestError) as raised:
            turn(s, magic("Sacred Flame", enemy["id"]))
        self.assertEqual(raised.exception.code, "unsupported_spell_mode")
        self.assertEqual(held(s), before)

    def test_a_player_at_zero_hit_points_cannot_cast(self):
        s, _ = calm_cleric(hp=0)
        result = turn(s, magic("Cure Wounds", "player"))  # a dying body rolls its death save instead of casting
        self.assertEqual(result["action_result"]["action"], "death_save")
        self.assertEqual(s.character["current_hp"], 0)
        self.assertEqual(s.world_state["spellcasting_v1"]["slots"]["1"], 2)

    def test_the_first_cast_closes_a_long_rest_preparation_window(self):
        s, _ = calm_cleric(prepared=("Cure Wounds",))
        s.world_state["spellcasting_v1"]["prepare_window"] = {
            "opened_second": spell_scope.clock_second(s.world_state), "reason": "long_rest"}
        self.assertTrue(spell_preparation.window_open(s))
        turn(s, magic("Cure Wounds", "player"))
        self.assertFalse(spell_preparation.window_open(s))


if __name__ == "__main__":
    unittest.main()
