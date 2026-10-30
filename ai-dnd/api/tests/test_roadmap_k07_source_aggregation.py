"""PHB2024 PDF11: eligible sources do not stack or vote. QG-1 characterization."""
import unittest
from unittest.mock import patch
from api.tests.test_weapon_attack import armed, resolve
from api.tests.test_initiative import actors

MATRIX=[([],[],[3],3),(['a','b','c'],[],[3,17],17),([],['x','y','z'],[3,17],3),
        (['a','b','c'],['x'],[3],3),(['a'],['x','y','z'],[3],3),
        (['a','b'],['x','y'],[3],3),(['a','a','b'],[],[3,17],17),([],['x','x','y'],[3,17],3)]


class AggregationTests(unittest.TestCase):
    def test_eligible_source_matrix_through_weapon_and_initiative(self):
        for adv,dis,raw,selected in MATRIX:
            for owner in ('weapon','initiative'):
                with self.subTest(owner=owner,adv=adv,dis=dis):
                    rules={'advantage_sources':adv,'disadvantage_sources':dis}
                    if owner=='weapon':
                        s,n=armed();s.character['attack_rules']=rules
                        r=resolve(s,n,rolls=(3,17))
                        self.assertEqual((r['attack_rolls'],r['attack_roll']),(raw,selected))
                    else:
                        s,ns=actors(player={'initiative_rules':rules})
                        with patch('game.roll_d20',side_effect=[3,17,1]):
                            s.start_combat(ns[0])
                        r=s.world_state['combat']['initiative_results']['player']
                        self.assertEqual((r['raw_rolls'],r['selected_roll']),(raw,selected))
                    self.assertEqual(r['advantage_sources'],sorted(set(adv)))
                    self.assertEqual(r['disadvantage_sources'],sorted(set(dis)))

    def test_state_and_hook_sources_use_the_same_aggregation(self):
        for owner in ('weapon','initiative'):
            with self.subTest(owner=owner):
                if owner=='weapon':
                    s,n=armed();s.character['attack_rules']={'advantage_sources':['state','duplicate']}
                    s.register_attack_hook('attack_rules',lambda *_:{'source':'fixture','advantage_sources':['hook','duplicate'],'disadvantage_sources':['opposing']})
                    r=resolve(s,n,rolls=(3,17));raw=r['attack_rolls']
                else:
                    s,ns=actors(player={'initiative_rules':{'advantage_sources':['state','duplicate']}})
                    s.register_initiative_hook('ON_INITIATIVE_ROLL',lambda _,c:{'advantage_sources':['hook','duplicate'],'disadvantage_sources':['opposing']} if c['actor_id']=='player' else None)
                    with patch('game.roll_d20',side_effect=[3,1]):s.start_combat(ns[0])
                    r=s.world_state['combat']['initiative_results']['player'];raw=r['raw_rolls']
                self.assertEqual(raw,[3])
                self.assertEqual(r['advantage_sources'],['duplicate','hook','state'])
                self.assertEqual(r['disadvantage_sources'],['opposing'])

    def test_source_oracle_is_registered(self):
        import rule_oracles
        data=rule_oracles.load_oracles();leaf_id='K07.advantage_disadvantage_source_aggregation.weapon_and_initiative'
        leaves=[x for x in data['leaves'] if x['leaf_id']==leaf_id]
        self.assertEqual(len(leaves),1,'eligible-source aggregation oracle missing')
        for case in leaves[0]['cases']:
            result=rule_oracles.evaluate_rule_case(leaf_id+'#'+case['id'],data)
            self.assertTrue(result['match'],result)
