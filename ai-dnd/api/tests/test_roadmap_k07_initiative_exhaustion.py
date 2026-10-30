"""PHB2024 PDF365 exhaustion penalty applies to Initiative, a Dexterity check."""
import copy
import unittest
from unittest.mock import patch
from api.tests.test_initiative import actors, newcomer
import game
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session


class InitiativeExhaustionTests(unittest.TestCase):
    def test_source_bound_oracle_exists_and_matches(self):
        import rule_oracles
        data=rule_oracles.load_oracles()
        leaves=[x for x in data['leaves'] if x['leaf_id']=='K07.initiative_exhaustion_penalty']
        self.assertEqual(len(leaves),1,'Exhaustion Initiative oracle missing')
        self.assertEqual(leaves[0]['source_ref']['pdf_page'],365)
        for case in leaves[0]['cases']:
            result=rule_oracles.evaluate_rule_case('K07.initiative_exhaustion_penalty#'+case['id'],data)
            self.assertTrue(result['match'],result)

    def test_late_join_and_reload_preserve_audited_penalty(self):
        s,ns=actors()
        with patch('game.roll_d20',side_effect=[20,1]):
            s.start_combat(ns[0])
        entrant=newcomer(s,'exhausted-late-join',exhaustion=2)
        with patch('game.roll_d20',return_value=10):
            s.join_combat_participants([entrant['id']])
        result=s.world_state['combat']['initiative_results'][entrant['id']]
        self.assertEqual(result['final_total'],6)
        self.assertEqual(result['additional_modifiers'],[{'source':'exhaustion_2024','value':-4}])
        payload=serialize_campaign_payload(s)
        restored=game.create_session(seed=99)
        restore_campaign_session(restored,payload)
        self.assertEqual(restored.world_state['combat']['initiative_results'][entrant['id']],result)

    def test_player_penalty_uses_each_level_and_keeps_raw_dice(self):
        for level, total in ((0,12),(1,10),(2,8),(5,2)):
            with self.subTest(level=level):
                s, ns = actors(player={'exhaustion': level})
                with patch('game.roll_d20', side_effect=[10,1]):
                    s.start_combat(ns[0])
                r = s.world_state['combat']['initiative_results']['player']
                self.assertEqual(r['raw_rolls'], [10])
                self.assertEqual(r['final_total'], total)
                expected = [] if level == 0 else [{'source':'exhaustion_2024','value':-2*level}]
                self.assertEqual(r['additional_modifiers'], expected)

    def test_npc_and_invisible_surprise_use_same_penalty_owner(self):
        for surprise, rolls, total in ((False,[20,3,17],13),(True,[20,10],6)):
            with self.subTest(surprise=surprise):
                s, ns = actors([{'exhaustion':2,'conditions':['invisible'],
                                 'surprised_at_combat_start':surprise}])
                with patch('game.roll_d20', side_effect=rolls):
                    s.start_combat(ns[0])
                r=s.world_state['combat']['initiative_results'][ns[0]['id']]
                self.assertEqual(r['final_total'], total)
                self.assertEqual(r['additional_modifiers'], [{'source':'exhaustion_2024','value':-4}])

    def test_feature_modifiers_remain_additive_not_replaced(self):
        s,ns=actors(player={'exhaustion':2,'initiative_rules':{'modifiers':[{'source':'feature','value':3}]}})
        with patch('game.roll_d20',side_effect=[10,1]):
            s.start_combat(ns[0])
        r=s.world_state['combat']['initiative_results']['player']
        self.assertEqual(r['final_total'],11)
        self.assertEqual(r['additional_modifiers'],[{'source':'feature','value':3},{'source':'exhaustion_2024','value':-4}])

    def test_invalid_exhaustion_or_duplicate_canonical_source_refuses_before_rng(self):
        cases=[{'exhaustion':v}for v in (True,-1,7,'2',None)]
        cases.append({'exhaustion':2,'initiative_rules':{'modifiers':[{'source':'exhaustion_2024','value':-4}]}})
        for config in cases:
            with self.subTest(config=config):
                s,ns=actors([config]);before=copy.deepcopy((s.world_state,s.character,s.rng.getstate()))
                with patch('game.roll_d20',side_effect=AssertionError('invalid input rolled')) as roll:
                    with self.assertRaises(ValueError):
                        s.start_combat(ns[0])
                roll.assert_not_called()
                self.assertEqual((s.world_state,s.character,s.rng.getstate()),before)

    def test_changing_exhaustion_does_not_recalculate_historical_roll(self):
        s,ns=actors([{'exhaustion':2}])
        with patch('game.roll_d20',side_effect=[20,10]):
            s.start_combat(ns[0])
        before=copy.deepcopy(s.world_state['combat']['initiative_results'])
        self.assertEqual(before[ns[0]['id']]['final_total'],6)
        ns[0]['exhaustion']=0
        with patch('game.roll_d20',side_effect=AssertionError('historical reroll')):
            s.advance_combat_turn()
        self.assertEqual(s.world_state['combat']['initiative_results'],before)
