"""Barbarian Extra Attack (level 5): the existing Attack-action allowance owner, not a second budget.

PHB 2024 Barbarian features table: Extra Attack at level 5 = two attacks instead of one whenever you take the Attack action on your
turn. Only the APPLIED level-5 selected Berserker gets it; XP-earned numeric level 5 alone does not. Dice are deterministic
(natural 1 misses); synthetic NPCs are labeled unit fixtures, not native campaign evidence.
"""
import copy
import unittest
from unittest.mock import patch

import action_economy as economy
import weapon_attack as attacks
from combat_lifecycle import CombatRequestError
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
import game
from api.tests.test_roadmap_c06_barbarian_level5 import applied_five, pending_five
from api.tests.test_roadmap_c06_barbarian_level4 import selected_three, advance as advance_four


def start_combat(session, *, distance=5):
    npc = session.create_npc_from_ai({'name': 'Extra Attack Unit Opponent', 'role': 'Guard', 'location': 'tavern'})
    npc.update(current_hp=500, max_hp=500, armor_class=10, hostile=True, combat_side='enemy', distance_ft=distance,
               attack_damage_type='bludgeoning', attack_bonus=0, damage_die=6, damage_dice=1, damage_modifier=0)
    session.world_state.setdefault('monster_perception', {})[npc['id']] = {'player': {'visible': True}}
    with patch('game.roll_initiative_player', return_value=20), patch('game.roll_initiative', return_value=1):
        session.start_combat(npc)
    return npc


def attack(npc, **extra):
    return {'kind': 'attack', 'target_id': npc['id'], **extra}


def follow(npc, **extra):
    return {'kind': 'continue_attack', 'target_id': npc['id'], **extra}


class ExtraAttackTests(unittest.TestCase):
    def five(self, build=applied_five):
        session = build(self)
        return session, start_combat(session)

    def run_steps(self, session, *steps, roll=1):
        with patch('game.roll_attack', return_value=roll) as rolled:
            result = economy.execute(session, {'steps': list(steps)})
        return result['action_economy_result']['steps'], rolled

    def test_applied_level_five_attack_action_has_exactly_two_attacks(self):
        s, n = self.five()
        steps, rolled = self.run_steps(s, attack(n), follow(n))
        self.assertEqual([step['action_resource_cost'] for step in steps], [1, 0])
        sequence = attacks.sequence_snapshot(s, 'player')
        self.assertEqual((sequence['attacks'], sequence['attack_rolls']), (2, 2))  # two separate attacks, two attack rolls
        r = economy.ensure(s)['player']
        self.assertEqual((r['attack_action']['remaining_attacks'], r['attack_action']['total_attacks']), (0, 2))
        self.assertTrue(r['base_action_spent'])
        self.assertFalse(r['bonus_action_spent'])
        before = s._capture_runtime_snapshot()
        with patch('game.roll_attack', return_value=1), self.assertRaises(CombatRequestError) as caught:
            economy.execute(s, {'steps': [follow(n)]})
        self.assertEqual(caught.exception.code, 'no_attack_continuation')
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_second_attack_may_follow_movement_and_keeps_one_action(self):
        s, n = self.five()
        steps, _ = self.run_steps(s, attack(n), {'kind': 'move', 'distance_ft': 5}, follow(n))
        self.assertEqual([step['kind'] for step in steps], ['attack', 'move', 'attack'])
        self.assertEqual(economy.ensure(s)['player']['attack_action']['remaining_attacks'], 0)

    def test_second_attack_cannot_be_started_as_a_new_attack_action(self):
        s, n = self.five()
        self.run_steps(s, attack(n), follow(n))
        with patch('game.roll_attack', return_value=1), self.assertRaises(CombatRequestError):
            economy.execute(s, {'steps': [attack(n)]})  # the single Action is spent; no second Attack action

    def test_no_second_attack_for_xp_earned_numeric_five_without_applied_choices(self):
        for build in (pending_five, lambda test: selected_three(test, raw=5)):
            s, n = self.five(build)
            self.assertEqual(s.character['level'], 5)
            self.run_steps(s, attack(n))
            self.assertEqual(economy.ensure(s)['player']['attack_action']['total_attacks'], 1)
            with patch('game.roll_attack', return_value=1), self.assertRaises(CombatRequestError):
                economy.execute(s, {'steps': [follow(n)]})

    def test_applied_level_four_has_one_attack(self):
        s = selected_three(self, raw=4)
        advance_four(self, s)
        n = start_combat(s)
        self.run_steps(s, attack(n))
        self.assertEqual(economy.ensure(s)['player']['attack_action']['total_attacks'], 1)

    def test_forged_state_gets_no_extra_attack(self):
        for change in ({'subclass_id': 'other'}, {'progression_level': 4}, {'progression_level': True}):
            s, n = self.five()
            s.character.update(change)
            self.assertEqual(economy.attacks_per_action(s, 'player'), 1, change)

    def test_engine_hook_still_wins_when_larger_and_is_not_lowered_by_the_feature(self):
        s, n = self.five()
        s.character['attacks_per_action'] = 3  # existing engine-only hook; never lowered by Extra Attack
        self.run_steps(s, attack(n))
        self.assertEqual(economy.ensure(s)['player']['attack_action']['total_attacks'], 3)

    def test_malformed_engine_hook_is_not_repaired_by_the_feature(self):
        for bad in (0, -1, True):
            s, n = self.five()
            s.character['attacks_per_action'] = bad
            before = s._capture_runtime_snapshot()
            with patch('game.roll_attack', return_value=1), self.assertRaises(CombatRequestError) as caught:
                economy.execute(s, {'steps': [attack(n)]})
            self.assertEqual(caught.exception.code, 'invalid_attack_allowance', bad)
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_attack_budget_resets_next_turn_and_survives_mid_action_save(self):
        s, n = self.five()
        self.run_steps(s, attack(n))
        payload = serialize_campaign_payload(s)
        fresh = game.create_session(seed=7)
        restore_campaign_session(fresh, payload)
        self.assertEqual(economy.ensure(fresh)['player']['attack_action']['remaining_attacks'], 1)
        steps, _ = self.run_steps(fresh, follow(n))
        self.assertEqual(steps[0]['action_resource_cost'], 0)
        economy.begin_round(fresh)
        economy.begin_turn(fresh, 'player')
        self.assertIsNone(economy.ensure(fresh)['player']['attack_action'])
        steps, _ = self.run_steps(fresh, attack(n), follow(n))
        self.assertEqual([step['action_resource_cost'] for step in steps], [1, 0])

    def test_rage_reckless_and_frenzy_across_both_attacks(self):
        import barbarian_rage
        s, n = self.five()
        barbarian_rage.activate(s)
        self.assertEqual(barbarian_rage.damage_bonus(s, 'strength'), 2)  # features table: Rage Damage +2 at level 5
        n['armor_class'] = 10
        with patch('game.roll_attack', return_value=15), patch.object(s.rng, 'randint', return_value=3):
            result = economy.execute(s, {'steps': [attack(n, reckless_attack=True), follow(n)]})
        steps = result['action_economy_result']['steps']
        for step in steps:
            self.assertIn('reckless_attack', step['result']['advantage_sources'])  # the window covers the second attack
            self.assertTrue(step['result']['hit'])
        frenzy = [[row for row in step['result']['damage_rolls'] if row['source'] == 'frenzy'] for step in steps]
        self.assertEqual([len(rows) for rows in frenzy], [1, 0])  # Frenzy is once per turn, not once per attack
        self.assertEqual(steps[1]['result']['damage'], 3 - 1 + 2)  # d12=3, STR -1 (fixture), Rage +2, no Frenzy
        self.assertEqual(steps[0]['result']['damage'], 3 - 1 + 2 + 6)

    def test_bonus_light_and_reaction_attacks_are_not_extra_attack(self):
        s, n = self.five()
        self.run_steps(s, attack(n))
        r = economy.ensure(s)['player']
        # Extra Attack is part of the Attack action only: nothing else gained an allowance.
        self.assertEqual(r['additional_actions'], [])
        self.assertEqual(r['bonus_grants'], [])
        self.assertFalse(r['reaction_spent'])

    def test_projection_exposes_remaining_attack_without_new_fields_authority(self):
        s, n = self.five()
        self.run_steps(s, attack(n))
        actor = economy.projection(s)['actors']['player']
        self.assertEqual(actor['attack_action']['remaining_attacks'], 1)
        self.assertEqual(actor['attack_action']['total_attacks'], 2)


if __name__ == '__main__':
    unittest.main()
