"""PDF369 Invisible attack exception. True means resolved ability to SEE,
not merely detected/located, ordinary line of sight, or an unverified sense.
No special-sense implementation is certified by these explicit fixture facts.
"""
import unittest
from api.tests.test_weapon_attack import armed, resolve


class InvisibleSightTests(unittest.TestCase):
    def test_sight_exception_is_source_bound(self):
        import rule_oracles
        data=rule_oracles.load_oracles();leaf='K07.invisible_attack_explicit_sight_exception'
        rows=[x for x in data['leaves'] if x['leaf_id']==leaf]
        self.assertEqual(len(rows),1,'Invisible sight exception oracle missing')
        self.assertEqual(rows[0]['source_ref']['pdf_page'],369)
        for case in rows[0]['cases']:
            result=rule_oracles.evaluate_rule_case(leaf+'#'+case['id'],data)
            self.assertTrue(result['match'],result)

    def test_explicit_directed_sight_suppresses_only_corresponding_invisible_source(self):
        cases=[
            (['invisible'],[],{'target_sees_attacker':True},False,False,[3]),
            ([],['invisible'],{'attacker_sees_target':True},False,False,[3]),
            (['invisible'],[],{'target_sees_attacker':False},True,False,[3,17]),
            ([],['invisible'],{'attacker_sees_target':False},False,True,[3,17]),
            (['invisible'],[],{},True,False,[3,17]),
            ([],['invisible'],{},False,True,[3,17]),
            (['invisible'],['invisible'],{'target_sees_attacker':True,'attacker_sees_target':False},False,True,[3,17]),
            (['invisible'],['invisible'],{'target_sees_attacker':False,'attacker_sees_target':True},True,False,[3,17]),
        ]
        for player,target,sight,adv,dis,raw in cases:
            with self.subTest(player=player,target=target,sight=sight):
                s,n=armed();s.character['conditions']=player;n['conditions']=target
                s.world_state['attack_environment']={'pairs':{'player|'+n['id']:{'distance_ft':5,**sight}}}
                result=resolve(s,n,rolls=(3,17))
                self.assertEqual('invisible_attacker' in result['advantage_sources'],adv)
                self.assertEqual('invisible_target' in result['disadvantage_sources'],dis)
                self.assertEqual(result['attack_rolls'],raw)

    def test_reverse_pair_sight_does_not_change_directed_invisible_effect(self):
        s,n=armed();s.character['conditions']=['invisible']
        s.world_state['attack_environment']={'pairs':{n['id']+'|player':{'distance_ft':5,'target_sees_attacker':True,'attacker_sees_target':True}}}
        result=resolve(s,n,rolls=(3,17))
        self.assertIn('invisible_attacker',result['advantage_sources'])
        self.assertEqual(result['attack_rolls'],[3,17])

    def test_explicit_sight_does_not_remove_independent_poisoned_disadvantage(self):
        s,n=armed();s.character['conditions']=['invisible','poisoned']
        s.world_state['attack_environment']={'pairs':{'player|'+n['id']:{'distance_ft':5,'target_sees_attacker':True}}}
        result=resolve(s,n,rolls=(3,17))
        self.assertNotIn('invisible_attacker',result['advantage_sources'])
        self.assertIn('poisoned',result['disadvantage_sources'])
        self.assertEqual(result['attack_rolls'],[3,17])
        self.assertEqual(result['attack_roll'],3)
