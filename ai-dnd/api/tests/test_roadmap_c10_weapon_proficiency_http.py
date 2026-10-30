"""Canonical source-owned Barbarian weapon training through actual HTTP/save owners."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4
from api.tests import test_roadmap_c10_rage_http as rage_fixtures
from api.tests.test_roadmap_c06_barbarian_creation_http import request

class WeaponProficiencyHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = rage_fixtures.RageHttpTests.asyncSetUp
    asyncTearDown = rage_fixtures.RageHttpTests.asyncTearDown
    post = rage_fixtures.RageHttpTests.post
    snapshot = rage_fixtures.RageHttpTests.snapshot
    reopen = rage_fixtures.RageHttpTests.reopen

    async def encounter(self,level=2):
        data=request(level)
        data['ability_scores']['strength']=14
        data['ability_scores']['dexterity']=8
        response=await self.http.post('/api/game/campaigns',json={'character':data})
        self.assertEqual(response.status_code,200,response.text)
        a=response.json();r=self.manager.get(a['session_id']);s=r.game_session
        s.commit_location_change('tavern')
        npc=s.create_npc_from_ai({'name':'Rakip','role':'Guard','location':'tavern'})
        npc.update(current_hp=100,max_hp=100,armor_class=10,hostile=True,distance_ft=5)
        s.world_state.setdefault('monster_perception',{})[npc['id']]={'player':{'visible':True}}
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
        s.world_state['attack_environment']={'pairs':{'player|'+npc['id']:{'distance_ft':5,'attacker_sees_target':True,'target_sees_attacker':True,'cover':'none'}}}
        self.manager.save_campaign(a['campaign_id'])
        return a,r,{'message':'Hamle.','action_id':str(uuid4()),'combat_action':{'steps':[{'kind':'attack','target_id':npc['id']}]}}

    async def test_canonical_one_two_grant_survives_save_and_fresh_restore(self):
        for level in (1,2):
            a,r,command=await self.encounter(level)
            self.assertEqual(r.game_session.character.get('weapon_proficiencies'),['simple','martial'])
            saved=self.store.get_campaign(a['campaign_id']).payload['engine_save']
            self.assertEqual(saved['player']['weapon_proficiencies'],['simple','martial'])
            before=copy.deepcopy(r.game_session.serialize_game_state())
            r=await self.reopen(a)
            self.assertEqual(r.game_session.serialize_game_state(),before)

    async def test_actual_greataxe_after_resume_adds_pb_to_hit_not_damage(self):
        a,r,command=await self.encounter();r=await self.reopen(a)
        with patch.object(r.game_session,'roll_attack',return_value=10):response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        attack=response.json()['combat_result']['economy_steps'][0]['result']
        self.assertEqual((attack['weapon_id'],attack['ability_modifier'],attack['proficiency_bonus'],attack['attack_bonus']),('greataxe',2,2,4))
        self.assertTrue(attack['proficient']);self.assertTrue(attack['proficiency_applied']);self.assertTrue(attack['hit'])
        dice=sum(sum(part['rolls']) for part in attack['damage_rolls'])
        self.assertEqual(attack['raw_damage'],dice+2)
        before=self.snapshot(r)
        with patch.object(r.game_session,'roll_attack',side_effect=AssertionError('receipt rerolled')):
            self.assertEqual((await self.post(a,command)).json(),response.json())
        self.assertEqual(self.snapshot(r),before)

    async def test_rage_reckless_keep_training_on_attack_not_damage(self):
        a,r,command=await self.encounter()
        activate={'message':'Rage','action_id':str(uuid4()),'combat_action':{'steps':[{'kind':'activate_rage','resource':'bonus'}]}}
        response=await self.post(a,activate);self.assertEqual(response.status_code,200,response.text)
        command['combat_action']['steps'][0]['reckless_attack']=True
        with patch.object(r.game_session,'roll_attack',return_value=10):response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        attack=response.json()['combat_result']['economy_steps'][0]['result']
        self.assertEqual(attack['attack_bonus'],4);self.assertTrue(attack['proficient'])
        self.assertIn('reckless_attack',attack['advantage_sources']);self.assertEqual(len(attack['attack_rolls']),2)
        self.assertEqual(attack['raw_damage'],sum(sum(part['rolls']) for part in attack['damage_rolls'])+2+2)
        self.assertEqual(r.game_session.world_state['rage_v1']['remaining'],1)

    async def test_no_request_controlled_grant_or_ambiguous_legacy_adoption(self):
        data=request();data['weapon_proficiencies']=['simple','martial']
        response=await self.http.post('/api/game/campaigns',json={'character':data})
        self.assertEqual(response.status_code,422,response.text)
        a,r,command=await self.encounter()
        r.game_session.character.pop('weapon_proficiencies',None)
        self.manager.save_campaign(a['campaign_id'])
        before=copy.deepcopy(r.game_session.serialize_game_state());r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),before)
        self.assertNotIn('weapon_proficiencies',r.game_session.character)
        bad=copy.deepcopy(command);bad['combat_action']['steps'][0]['weapon_proficiencies']=['martial']
        self.assertEqual((await self.post(a,bad)).status_code,422)
        with patch.object(r.game_session,'roll_attack',return_value=10):response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        attack=response.json()['combat_result']['economy_steps'][0]['result']
        self.assertFalse(attack['proficient']);self.assertEqual(attack['attack_bonus'],2)
        self.assertNotIn('weapon_proficiencies',r.game_session.character)

    async def test_real_sqlite_attack_rollback_retry_and_fresh_replay_preserve_training(self):
        from contextlib import contextmanager
        import sqlite3
        a,r,command=await self.encounter();before=self.snapshot(r)
        transaction=self.store._transaction;reached=[]
        @contextmanager
        def failing_transaction():
            with transaction() as connection:
                yield connection
                receipt=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',
                    (a['campaign_id'],command['action_id'])).fetchone()
                if receipt is not None:
                    reached.append(True)
                    raise sqlite3.OperationalError('synthetic trained attack receipt precommit')
        with patch.object(self.store,'_transaction',side_effect=failing_transaction):failed=await self.post(a,command)
        self.assertGreaterEqual(failed.status_code,500,failed.text)
        self.assertEqual(reached,[True]);self.assertEqual(self.snapshot(r),before)
        accepted=await self.post(a,command);self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json()['combat_result']['economy_steps'][0]['result']['attack_bonus'],4)
        r=await self.reopen(a);expected=accepted.json();expected['session_id']=a['session_id']
        before=self.snapshot(r)
        with patch.object(r.game_session,'roll_attack',side_effect=AssertionError('restored receipt rerolled')):
            self.assertEqual((await self.post(a,command)).json(),expected)
        self.assertEqual(self.snapshot(r),before)
        self.assertEqual(r.game_session.character['weapon_proficiencies'],['simple','martial'])
