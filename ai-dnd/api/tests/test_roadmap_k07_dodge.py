"""PHB2024 PDF365 Dodge: existing behavior, QG-1 characterization.

Removing either can_act/speed guard in attack.prepare or attack.save must fail
this matrix. Restrained's separate save disadvantage must survive Dodge loss.
"""
import unittest
from unittest.mock import patch
import action_economy as ae
import weapon_attack as attack
from api.tests.test_weapon_attack import armed


class DodgeBenefitTests(unittest.TestCase):
    def test_dodge_leaf_is_source_bound_and_matches_every_case(self):
        import rule_oracles
        data = rule_oracles.load_oracles()
        leaves = [leaf for leaf in data['leaves'] if leaf['leaf_id'] == 'K07.dodge_benefits_loss']
        self.assertEqual(len(leaves), 1, 'Dodge needs its own bounded source oracle')
        self.assertEqual(leaves[0]['source_ref']['pdf_page'], 365)
        self.assertEqual(len(leaves[0]['cases']), 7)
        for case in leaves[0]['cases']:
            result = rule_oracles.evaluate_rule_case('K07.dodge_benefits_loss#' + case['id'], data)
            self.assertTrue(result['match'], result)

    def test_benefits_follow_capacity_not_remaining_movement(self):
        cases = [
            ([], 30, True, True, 2, 'SUCCESS'),
            (['incapacitated'], 30, True, False, 1, 'FAILURE'),
            ([], 0, True, False, 1, 'FAILURE'),
            ([], 1, True, True, 2, 'SUCCESS'),
            (['grappled'], 30, True, False, 1, 'FAILURE'),
            (['restrained'], 30, True, False, 2, 'FAILURE'),
            ([], 30, False, False, 2, 'SUCCESS'),
        ]
        for names, speed, sees, source, count, outcome in cases:
            with self.subTest(conditions=names, speed=speed, sees=sees):
                session, enemy = armed()
                enemy.update(conditions=names, speed_ft=speed, dexterity_mod=0,
                             dexterity_save_bonus=0, exhaustion=0)
                resource = ae.ensure(session)[enemy['id']]
                resource['dodging'] = True
                resource['movement_used'] = resource['movement_available']
                session.world_state['attack_environment'] = {'pairs': {
                    'player|' + enemy['id']: {'distance_ft': 5,
                        'attacker_sees_target': True, 'target_sees_attacker': sees}}}
                context = attack.prepare(session, 'player', enemy['id'], 'Longsword')
                self.assertEqual('target_dodging' in context['disadvantage_sources'], source)
                with patch.object(session, 'roll_d20', side_effect=[1, 20]) as roll:
                    result = attack.save(session, enemy['id'], ['dexterity'], 12)
                self.assertEqual(roll.call_count, count)
                self.assertEqual(result['outcome'], outcome)
