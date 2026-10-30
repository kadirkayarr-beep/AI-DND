"""PHB2024 PDF362: active Charmed cannot attack its known charmer.

Only existing canonical charmed_by identity; no inferred source or spell/social
eligibility claim. Shared weapon and Unarmed Strike path, before any effects.
"""
import copy
import unittest
from unittest.mock import patch
import weapon_attack as attack
from combat_lifecycle import CombatRequestError
from api.tests.test_weapon_attack import armed, resolve
from api.tests.test_monster_combat import fixture, activate, claw


class CharmedAttackTests(unittest.TestCase):
    def test_source_oracle_is_registered(self):
        import rule_oracles
        data=rule_oracles.load_oracles();leaf='K07.charmed_attack_charmer'
        rows=[x for x in data['leaves'] if x['leaf_id']==leaf]
        self.assertEqual(len(rows),1,'Charmed attack oracle missing')
        self.assertEqual(rows[0]['source_ref']['pdf_page'],362)
        for case in rows[0]['cases']:
            result=rule_oracles.evaluate_rule_case(leaf+'#'+case['id'],data)
            self.assertTrue(result['match'],result)

    def test_player_weapon_and_unarmed_attacks_refuse_known_charmer_without_effects(self):
        for weapon,choice in [('Longsword',{}),('unarmed',{'unarmed_option':'damage'}),
                              ('unarmed',{'unarmed_option':'grapple'}),('unarmed',{'unarmed_option':'shove'})]:
            with self.subTest(weapon=weapon,choice=choice):
                s,n=armed();s.character.update(conditions=['charmed'],charmed_by=n['id'])
                before=copy.deepcopy((s.world_state,s.character,s.rng.getstate(),s.messages))
                with patch('game.roll_attack',side_effect=AssertionError('prohibited attack rolled')),patch('game.roll_d20',side_effect=AssertionError('prohibited save rolled')):
                    with self.assertRaises(CombatRequestError) as error:
                        attack.resolve(s,'player',n['id'],weapon,choice)
                self.assertEqual(error.exception.code,'charmed_target_forbidden')
                self.assertEqual((s.world_state,s.character,s.rng.getstate(),s.messages),before)

    def test_other_unknown_or_inactive_source_does_not_invent_a_target_ban(self):
        for conditions,source in [(['charmed'],'another-actor'),(['charmed'],None),([],True),({'charmed':False},True)]:
            with self.subTest(conditions=conditions,source=source):
                s,n=armed();s.character['conditions']=conditions
                if source is not None:s.character['charmed_by']=n['id'] if source is True else source
                result=resolve(s,n)
                self.assertEqual(result['attack_rolls'],[10])

    def test_enabled_dictionary_and_npc_direct_owner_cannot_bypass(self):
        s,n=fixture();n.update(conditions={'charmed':True},charmed_by='player');activate(s,n)
        before=copy.deepcopy((s.world_state,s.character,s.rng.getstate(),s.messages))
        with patch('game.roll_d20',side_effect=AssertionError('prohibited NPC attack rolled')):
            with self.assertRaises(CombatRequestError) as error:
                attack.resolve(s,n['id'],'player','claw',profile=claw()['profile'])
        self.assertEqual(error.exception.code,'charmed_target_forbidden')
        self.assertEqual((s.world_state,s.character,s.rng.getstate(),s.messages),before)
