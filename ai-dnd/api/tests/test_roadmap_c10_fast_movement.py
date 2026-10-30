"""Barbarian Fast Movement (level 5): +10 ft Speed while not wearing Heavy armor, through the existing Speed owner.

The engine has no general worn-armor owner: the only retained armor fact is the Barbarian `worn_armor_v1` proof (`armor_id` None =
verified unarmored). The bonus therefore needs that proof; a Heavy suit named by `armor_id` (PHB armor table categories already
in `ARMOR_CLASS_RULES`) or an unverifiable/unknown armor state gives no bonus. Only the APPLIED level-5 selected Berserker has it.
"""
import unittest

import action_economy as economy
import character_progression as cp
from combat_lifecycle import CombatRequestError
from api.tests.test_roadmap_c06_barbarian_level5 import applied_five, pending_five, roundtrip
from api.tests.test_roadmap_c06_barbarian_level4 import selected_three, advance as advance_four
from api.tests.test_roadmap_c10_extra_attack import start_combat


class FastMovementTests(unittest.TestCase):
    def test_applied_level_five_gains_ten_feet_in_and_out_of_combat(self):
        for species, base in (('Human', 30), ('Dwarf', 30)):
            s = applied_five(self, species=species)
            self.assertEqual(s.character['speed_ft'], base)
            self.assertEqual(economy.speed(s, 'player'), base + 10, 'out of combat')  # Speed owner, no stored copy
            start_combat(s)
            self.assertEqual(economy.speed(s, 'player'), base + 10, 'in combat')
            self.assertEqual(s.character['speed_ft'], base)  # the stored base is never rewritten

    def test_no_bonus_before_the_level_is_applied(self):
        s = pending_five(self)
        self.assertEqual(economy.speed(s, 'player'), 30)
        ahead = selected_three(self, raw=5)
        self.assertEqual(economy.speed(ahead, 'player'), 30)
        four = selected_three(self, raw=4); advance_four(self, four)
        self.assertEqual(economy.speed(four, 'player'), 30)

    def test_heavy_armor_removes_the_bonus_and_other_armor_states_follow_the_armor_table(self):
        s = applied_five(self)
        start_combat(s)
        expected = {None: 40, 'Leather Armor': 40, 'Studded Leather Armor': 40, 'Hide Armor': 40, 'Breastplate': 40,
                    'Chain Mail': 30, 'Ring Mail': 30, 'Splint Armor': 30, 'Plate Armor': 30, 'Zincir Zırh': 30,
                    'Unknown Armor': 30, 42: 30, '': 30}
        for armor_id, speed in expected.items():
            s.world_state['worn_armor_v1'] = {'version': 1, 'armor_id': armor_id}
            self.assertEqual(economy.speed(s, 'player'), speed, armor_id)
        s.world_state.pop('worn_armor_v1')  # armor state unverifiable: no bonus
        self.assertEqual(economy.speed(s, 'player'), 30)

    def test_shield_or_inventory_possession_is_not_worn_heavy_armor(self):
        s = applied_five(self)
        s.world_state['inventory'].extend(['Plate Armor', 'Shield'])
        self.assertEqual(economy.speed(s, 'player'), 40)

    def test_bonus_stacks_with_penalties_and_zero_speed_conditions_still_win(self):
        s = applied_five(self); start_combat(s)
        s.character['speed_penalty_ft'] = 10
        self.assertEqual(economy.speed(s, 'player'), 30)
        s.character['speed_penalty_ft'] = 0
        s.character['conditions'] = ['grappled']
        self.assertEqual(economy.speed(s, 'player'), 0)
        s.character['conditions'] = ['restrained']
        self.assertEqual(economy.speed(s, 'player'), 0)
        s.character['conditions'] = []
        self.assertEqual(economy.speed(s, 'player'), 40)

    def test_combat_movement_and_dash_budget_use_the_boosted_speed(self):
        s = applied_five(self); n = start_combat(s)
        economy.execute(s, {'steps': [{'kind': 'move', 'distance_ft': 40}]})
        self.assertEqual(economy.movement_limit(s, 'player'), 40)
        with self.assertRaises(CombatRequestError):
            economy.execute(s, {'steps': [{'kind': 'move', 'distance_ft': 5}]})
        economy.begin_turn(s, 'player')
        self.assertEqual(economy.ensure(s)['player']['movement_available'], 40)
        economy.execute(s, {'steps': [{'kind': 'dash'}, {'kind': 'move', 'distance_ft': 80}]})
        self.assertEqual(economy.ensure(s)['player']['movement_used'], 80)
        self.assertEqual(economy.projection(s)['actors']['player']['speed_ft'], 40)

    def test_survives_fresh_restore_and_pending_state_stays_unboosted(self):
        s = applied_five(self)
        fresh, _ = roundtrip(s)
        self.assertEqual(economy.speed(fresh, 'player'), 40)
        pending, _ = roundtrip(pending_five(self))
        self.assertEqual(economy.speed(pending, 'player'), 30)

    def test_disclosure_names_the_armor_scope(self):
        supported = ' '.join(cp.progression_disclosure('Barbarian', 5)['supported'])
        pending = ' '.join(cp.progression_effects_pending('Barbarian', 5))
        self.assertIn('Fast Movement', supported)
        self.assertIn('armor', supported.lower())
        self.assertIn('Fast Movement', pending)  # general worn-armor tracking is still pending


if __name__ == '__main__':
    unittest.main()
