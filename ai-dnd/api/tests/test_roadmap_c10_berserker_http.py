"""Selected earned Berserker3 strict API choices and durable application."""
import copy
import unittest
from uuid import uuid4
from unittest.mock import patch
import xp
from api.tests import test_roadmap_c10_rage_http as helpers
from api.tests.test_roadmap_c06_barbarian_creation_http import request as creation_request

PICK={'subclass_id':'berserker','primal_knowledge_skill':'Survival'}
class BerserkerHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=helpers.RageHttpTests.asyncSetUp
    asyncTearDown=helpers.RageHttpTests.asyncTearDown
    reopen=helpers.RageHttpTests.reopen
    snapshot=helpers.RageHttpTests.snapshot

    async def earned(self,level=2,award=600):
        response=await self.http.post('/api/game/campaigns',json={'character':creation_request(level)})
        self.assertEqual(response.status_code,200,response.text)
        a=response.json();r=self.manager.get(a['session_id'])
        xp.apply_xp(r.game_session.character,r.game_session.world_state,award,'quest:synthetic-earned-berserker')
        self.manager.save_campaign(a['campaign_id'])
        return a,r
    def url(self,a):return f"/api/game/sessions/{a['session_id']}/level-up"
    async def preview(self,a):
        response=await self.http.get(self.url(a));self.assertEqual(response.status_code,200,response.text)
        return response.json()
    def command(self,a,pick,preview):
        return {'action_id':str(uuid4()),'campaign_id':a['campaign_id'],'expected_revision':preview['revision'],'target_level':preview['target_level'],'choices':copy.deepcopy(pick)}

    async def test_actual_earned_preview_and_choice_persist_skill_provenance(self):
        a,r=await self.earned();s=r.game_session;before=copy.deepcopy(s.character)
        preview=await self.preview(a)
        self.assertEqual((preview['status'],preview['target_level']),('ready',3))
        self.assertEqual(preview['choices_required'],{'subclass_id':1,'primal_knowledge_skill':1})
        self.assertEqual(preview['subclass_options'],[{'id':'berserker','name':'Path of the Berserker'}])
        self.assertEqual(preview['primal_knowledge_skill_options'],['Animal Handling','Intimidation','Nature','Survival'])
        command=self.command(a,PICK,preview)
        response=await self.http.post(self.url(a),json=command)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(s.character['subclass_id'],'berserker')
        self.assertEqual(s.character['proficient_skills'],before['proficient_skills']+['Survival'])
        self.assertEqual(s.character['primal_knowledge_choice'],{'class_level':3,'skill':'Survival','prior_proficient_skills':before['proficient_skills']})
        self.assertEqual(s.character.get('origin_choices'),before.get('origin_choices'))
        self.assertEqual(response.json()['state']['character']['rage']['max_uses'],3)
        runtime=copy.deepcopy(s.serialize_game_state());r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),runtime)
        expected=response.json();expected['session_id']=a['session_id']
        with patch('character_progression.apply_level_choices',side_effect=AssertionError('reapplied skill')):
            self.assertEqual((await self.http.post(self.url(a),json=command)).json(),expected)

    async def test_new_choice_shape_retained_not_stripped(self):
        from api.schemas import LevelUpApplyRequest
        command={'action_id':str(uuid4()),'campaign_id':str(uuid4()),'expected_revision':0,'target_level':3,'choices':PICK}
        try: parsed=LevelUpApplyRequest.model_validate(command)
        except ValueError as error:self.fail(f'Berserker earned choice rejected: {error}')
        self.assertEqual(parsed.model_dump(mode='json'),command)

    async def test_public_creation_three_without_the_level_three_bundle_is_refused(self):
        # Selected start 3 is public since the Barbarian start-3 slice; the bundle for level 3 stays mandatory.
        data=creation_request();data['starting_level']=3;data['level_choices'].pop('3',None)
        response=await self.http.post('/api/game/campaigns',json={'character':data})
        self.assertEqual(response.status_code,422,response.text)

    async def test_strict_invalid_choice_and_wrong_class_shape_never_mutate(self):
        a,r=await self.earned();p=await self.preview(a);before=r.game_session._capture_runtime_snapshot()
        for pick in ({}, {'subclass_id':'Berserker','primal_knowledge_skill':'Survival'},
                     {'subclass_id':'berserker'}, {**PICK,'primal_knowledge_skill':None},
                     {**PICK,'primal_knowledge_skill':True},{**PICK,'primal_knowledge_skill':['Survival']},
                     {**PICK,'primal_knowledge_skill':'survival'},{**PICK,'prepared_spells':[]},{**PICK,'extra':None}):
            response=await self.http.post(self.url(a),json=self.command(a,pick,p))
            self.assertEqual(response.status_code,422,response.text)
            self.assertEqual(r.game_session._capture_runtime_snapshot(),before)
        for pick in ({**PICK,'primal_knowledge_skill':'Athletics'},
                     {'subclass_id':'phb2024:subclass:sorcerer:aberrant-sorcery','prepared_spells':['Disguise Self','Detect Magic']}):
            response=await self.http.post(self.url(a),json=self.command(a,pick,p))
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(r.game_session._capture_runtime_snapshot(),before)

    async def test_xp_ahead_queue_two_then_three_omits_skill_options_on_two(self):
        a,r=await self.earned(level=1,award=6500)
        preview=await self.preview(a)
        self.assertEqual((preview['status'],preview['target_level']),('ready',2))
        self.assertNotIn('primal_knowledge_skill_options',preview)
        hp=r.game_session.character['max_hp']
        response=await self.http.post(self.url(a),json=self.command(a,{},preview))
        self.assertEqual(response.status_code,200,response.text)
        preview=await self.preview(a);self.assertEqual(preview['target_level'],3)
        response=await self.http.post(self.url(a),json=self.command(a,PICK,preview))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(r.game_session.character['level'],5)
        self.assertEqual(r.game_session.character['progression_level'],3)
        self.assertEqual(r.game_session.character['max_hp'],hp)

    async def test_legacy_absent_rage_is_explicitly_blocked_not_adopted(self):
        a,r=await self.earned();s=r.game_session
        s.world_state.pop('rage_v1');s.world_state.pop('worn_armor_v1')
        self.manager.save_campaign(a['campaign_id']);before=s.serialize_game_state()
        p=await self.preview(a)
        self.assertEqual(p['status'],'blocked',p)
        self.assertEqual(p['reason'],'selected_subclass_rage_capability_required')
        response=await self.http.post(self.url(a),json=self.command(a,PICK,p))
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(s.serialize_game_state(),before)
        self.assertNotIn('rage_v1',s.world_state)

    async def test_sqlite_receipt_insert_fault_rolls_back_then_retry_applies_once(self):
        from contextlib import contextmanager
        import sqlite3
        a,r=await self.earned();command=self.command(a,PICK,await self.preview(a));before=self.snapshot(r)
        transaction=self.store._transaction;reached=[]
        @contextmanager
        def fail_after_receipt():
            with transaction() as connection:
                yield connection
                row=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',
                    (a['campaign_id'],command['action_id'])).fetchone()
                if row:
                    reached.append(True)
                    raise sqlite3.OperationalError('synthetic Berserker receipt precommit')
        with patch.object(self.store,'_transaction',side_effect=fail_after_receipt):response=await self.http.post(self.url(a),json=command)
        self.assertGreaterEqual(response.status_code,500,response.text)
        self.assertEqual(reached,[True]);self.assertEqual(self.snapshot(r),before)
        response=await self.http.post(self.url(a),json=command)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(r.game_session.character['proficient_skills'].count('Survival'),1)
        self.assertEqual(r.game_session.world_state['rage_v1']['remaining'],3)
        self.assertEqual((await self.http.post(self.url(a),json=command)).json(),response.json())

    async def test_stale_revision_foreign_owner_and_conflicting_retry_do_not_reapply(self):
        from api.auth import FixedAuthenticator
        from api.tests.auth_fixture import TEST_PLAYER,PLAYER_B
        a,r=await self.earned();p=await self.preview(a);command=self.command(a,PICK,p)
        self.app.state.authenticator=FixedAuthenticator(PLAYER_B)
        try:self.assertEqual((await self.http.post(self.url(a),json=command)).status_code,404)
        finally:self.app.state.authenticator=FixedAuthenticator(TEST_PLAYER)
        bad=copy.deepcopy(command);bad['expected_revision']-=1
        self.assertEqual((await self.http.post(self.url(a),json=bad)).status_code,409)
        command['action_id']=str(uuid4())
        accepted=await self.http.post(self.url(a),json=command);self.assertEqual(accepted.status_code,200,accepted.text)
        bad=copy.deepcopy(command);bad['choices']['primal_knowledge_skill']='Nature'
        response=await self.http.post(self.url(a),json=bad)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail']['code'],'action_id_conflict')
        self.assertNotIn('Nature',r.game_session.character['proficient_skills'])

    async def test_actual_earned_rage_reckless_frenzy_receipt_and_fresh_replay_no_reroll(self):
        a,r=await self.earned();command=self.command(a,PICK,await self.preview(a))
        response=await self.http.post(self.url(a),json=command);self.assertEqual(response.status_code,200,response.text)
        s=r.game_session;s.commit_location_change('tavern')
        npc=s.create_npc_from_ai({'name':'Rakip','role':'Guard','location':'tavern'})
        npc.update(current_hp=100,max_hp=100,armor_class=10,hostile=True,distance_ft=5)
        s.world_state.setdefault('monster_perception',{})[npc['id']]={'player':{'visible':True}}
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
        s.world_state['attack_environment']={'pairs':{'player|'+npc['id']:{'distance_ft':5,'attacker_sees_target':True,'target_sees_attacker':True,'cover':'none'}}}
        self.manager.save_campaign(a['campaign_id'])
        url=f"/api/game/sessions/{a['session_id']}/turn"
        activate={'message':'Rage','action_id':str(uuid4()),'combat_action':{'steps':[{'kind':'activate_rage','resource':'bonus'}]}}
        response=await self.http.post(url,json=activate);self.assertEqual(response.status_code,200,response.text)
        attack={'message':'Hamle.','action_id':str(uuid4()),'combat_action':{'steps':[{'kind':'attack','target_id':npc['id'],'reckless_attack':True}]}}
        with patch.object(s,'roll_attack',return_value=10):response=await self.http.post(url,json=attack)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()['combat_result']['economy_steps'][0]['result']
        self.assertTrue(result['hit']);self.assertFalse(result['critical'])
        frenzy=[part for part in result['damage_rolls'] if part['source']=='frenzy']
        self.assertEqual(len(frenzy),1);self.assertEqual((frenzy[0]['die'],frenzy[0]['count']),(6,2))
        self.assertEqual(s.world_state['rage_v1']['remaining'],2)
        sequence=s.world_state['combat']['turn_resources']['player']['weapon_sequence']
        self.assertTrue(sequence['frenzy_eligible']);self.assertTrue(sequence['frenzy_used'])
        runtime=copy.deepcopy(s.serialize_game_state());r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),runtime)
        before=self.snapshot(r);expected=response.json();expected['session_id']=a['session_id']
        with patch.object(r.game_session,'roll_attack',side_effect=AssertionError('Frenzy receipt rerolled')),patch('weapon_attack.resolve',side_effect=AssertionError('Frenzy receipt resolved')):
            replay=await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",json=attack)
        self.assertEqual(replay.json(),expected);self.assertEqual(self.snapshot(r),before)

    async def test_commit_ack_loss_adopts_once_clears_undo_and_status_recovers(self):
        from api.persistence.campaign_models import CampaignStorageError
        a,r=await self.earned();command=self.command(a,PICK,await self.preview(a))
        r.undo_checkpoint={'synthetic_old_turn':True}
        original=self.manager.save_campaign_locked
        def commit_then_fail(*args,**kwargs):
            original(*args,**kwargs)
            raise CampaignStorageError('synthetic Berserker committed acknowledgement lost')
        with patch.object(self.manager,'save_campaign_locked',side_effect=commit_then_fail):response=await self.http.post(self.url(a),json=command)
        self.assertGreaterEqual(response.status_code,500,response.text)
        self.assertIsNone(r.undo_checkpoint)
        self.assertEqual(r.game_session.character['subclass_id'],'berserker')
        self.assertEqual(r.game_session.character['proficient_skills'].count('Survival'),1)
        status=await self.http.get(f"/api/game/sessions/{a['session_id']}/actions/{command['action_id']}")
        self.assertEqual(status.json()['state'],'applied');self.assertIsNone(status.json()['response'])
        accepted=await self.http.post(self.url(a),json=command)
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(r.game_session.world_state['rage_v1']['remaining'],3)

    async def test_apply_adds_capacity_delta_to_spent_pool_without_refill(self):
        from api.tests import test_roadmap_c10_rage_http as rage
        # Actual source activation spends one use before the earned transition.
        a,r,activate=await rage.RageHttpTests.encounter(self)
        response=await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",json=activate)
        self.assertEqual(response.status_code,200,response.text)
        s=r.game_session;s.end_combat('synthetic_earned_boundary')
        xp.apply_xp(s.character,s.world_state,600,'quest:synthetic-spent-earned-three')
        self.manager.save_campaign(a['campaign_id'])
        resources=copy.deepcopy((s.world_state['rage_v1']['active'],s.world_state['inventory'],s.world_state['currency'],s.world_state['campaign_time'],s.rng.getstate()))
        response=await self.http.post(self.url(a),json=self.command(a,PICK,await self.preview(a)))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(s.world_state['rage_v1']['remaining'],2)
        self.assertEqual((s.world_state['rage_v1']['active'],s.world_state['inventory'],s.world_state['currency'],s.world_state['campaign_time'],s.rng.getstate()),resources)
