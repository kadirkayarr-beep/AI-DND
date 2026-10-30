"""PHB2024 Invisible PDF369: Initiative advantage, separate from attack visibility.

Actual combat-start owner, deterministic dice. Removing the Invisible source
must fail; multiple disadvantage sources cancel, not outvote, advantage.
"""
import copy
import unittest
from unittest.mock import patch
from api.tests.test_initiative import actors


class InvisibleInitiativeTests(unittest.TestCase):
    def test_source_oracle_covers_invisibility_and_cancellation(self):
        import rule_oracles
        data = rule_oracles.load_oracles()
        rows = [x for x in data['leaves'] if x['leaf_id'] == 'K07.initiative_invisible']
        self.assertEqual(len(rows), 1, 'Invisible Initiative source binding missing')
        self.assertEqual(rows[0]['source_ref']['pdf_page'], 369)
        for case in rows[0]['cases']:
            result = rule_oracles.evaluate_rule_case('K07.initiative_invisible#' + case['id'], data)
            self.assertTrue(result['match'], result)

    def test_invisible_player_gets_advantage_on_combat_start(self):
        session, enemies = actors(player={'conditions': ['invisible']})
        with patch('game.roll_d20', side_effect=[3, 17, 1]) as roll:
            session.start_combat(enemies[0])
        result = session.world_state['combat']['initiative_results']['player']
        self.assertIn('invisible_2024', result['advantage_sources'])
        self.assertEqual(result['raw_rolls'], [3, 17])
        self.assertEqual(result['final_total'], 19)
        self.assertEqual(roll.call_count, 3)

    def test_invisible_npc_sources_cancel_without_counting_votes(self):
        for conditions, surprise, rolls, selected, count in (
            (['invisible'], False, [20, 3, 17], 17, 2),
            (['invisible'], True, [20, 3, 17], 3, 1),
            (['invisible', 'incapacitated'], False, [20, 3, 17], 3, 1),
            (['invisible', 'incapacitated'], True, [20, 3, 17], 3, 1),
        ):
            with self.subTest(conditions=conditions, surprised=surprise):
                session, enemies = actors([{'conditions': conditions,
                    'surprised_at_combat_start': surprise}])
                with patch('game.roll_d20', side_effect=rolls):
                    session.start_combat(enemies[0])
                result = session.world_state['combat']['initiative_results'][enemies[0]['id']]
                self.assertIn('invisible_2024', result['advantage_sources'])
                self.assertEqual(result['selected_roll'], selected)
                self.assertEqual(len(result['raw_rolls']), count)
                if surprise:
                    self.assertIn('surprise_2024', result['disadvantage_sources'])
                if 'incapacitated' in conditions:
                    self.assertIn('incapacitated_2024', result['disadvantage_sources'])

    def test_enabled_conditions_and_feature_advantage_do_not_add_dice(self):
        for conditions, active in (({'invisible': False}, False), ({'INVISIBLE': True}, True),
                                   (('invisible',), True), ({'invisible'}, True)):
            with self.subTest(conditions=conditions):
                session, enemies = actors([{'conditions': conditions,
                    'initiative_rules': {'advantage_sources': ['feature']}}])
                with patch('game.roll_d20', side_effect=[20, 3, 17]) as roll:
                    session.start_combat(enemies[0])
                result = session.world_state['combat']['initiative_results'][enemies[0]['id']]
                self.assertEqual('invisible_2024' in result['advantage_sources'], active)
                self.assertEqual(result['raw_rolls'], [3, 17])
                self.assertEqual(roll.call_count, 3)

    def test_losing_invisibility_does_not_rewrite_completed_initiative(self):
        session, enemies = actors([{'conditions': ['invisible']}])
        with patch('game.roll_d20', side_effect=[20, 3, 17]):
            session.start_combat(enemies[0])
        before = copy.deepcopy(session.world_state['combat']['initiative_results'])
        self.assertEqual(before[enemies[0]['id']]['raw_rolls'], [3, 17])
        enemies[0]['conditions'] = []
        with patch('game.roll_d20', side_effect=AssertionError('must not reroll')):
            session.advance_combat_turn()
        self.assertEqual(session.world_state['combat']['initiative_results'], before)
