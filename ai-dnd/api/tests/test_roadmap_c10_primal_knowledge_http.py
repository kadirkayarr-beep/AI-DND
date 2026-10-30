"""Real factory ASGI HTTP boundaries; synthetic store/model/dice, not live acceptance."""
import copy
import hashlib
import inspect
import json
import sqlite3
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import game
import barbarian_rage
from api.schemas import TurnRequest, SkillCheckResult
from api.serializers import serialize_skill_check_result, SkillCheckResultSerializationError
from api.core_resolution import resolution_action_scope
from api.tests import test_roadmap_c10_berserker_http as prior
from api.tests.test_roadmap_c10_primal_knowledge import selected, roll
from api.tests.test_campaign_api import ControlledVenueOllamaClient

FIXTURE = Path(__file__).parent / 'fixtures' / 'c10_pre_primal_http_receipt.json'
HASH = 'fae5bab8973fb30dee0bfbbbc872da54ea13b3b65a32498ffe47d488b3d32cf0'

class PrimalKnowledgeHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = prior.BerserkerHttpTests.asyncSetUp
    asyncTearDown = prior.BerserkerHttpTests.asyncTearDown
    earned = prior.BerserkerHttpTests.earned
    preview = prior.BerserkerHttpTests.preview
    url = prior.BerserkerHttpTests.url
    command = prior.BerserkerHttpTests.command
    reopen = prior.BerserkerHttpTests.reopen
    snapshot = prior.BerserkerHttpTests.snapshot

    async def ready(self):
        a,r=await self.earned()
        response=await self.http.post(self.url(a),json=self.command(a,prior.PICK,await self.preview(a)))
        self.assertEqual(response.status_code,200,response.text)
        s=r.game_session;s.commit_location_change('tavern')
        npc=s.create_npc_from_ai({'name':'Rakip','role':'Guard','location':'tavern'})
        npc.update(current_hp=100,max_hp=100,armor_class=20,hostile=True,distance_ft=5)
        s.world_state.setdefault('monster_perception',{})[npc['id']]={'player':{'visible':True}}
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
        self.manager.save_campaign(a['campaign_id'])
        response=await self.post(a,{'message':'Rage','action_id':str(uuid4()),'combat_action':{'steps':[{'kind':'activate_rage','resource':'bonus'}]}})
        self.assertEqual(response.status_code,200,response.text)
        s.end_combat('synthetic_immediate_check_fixture');self.manager.save_campaign(a['campaign_id'])
        return a,r,{'message':'Takla atıyorum','interaction_mode':'do','action_id':str(uuid4()),'check_feature':'primal_knowledge'}

    async def post(self,a,command):
        # Exercise the real adapter phases, not a substituted engine turn.
        narrator=ControlledVenueOllamaClient('narrative')
        with patch('api.tests.test_campaign_api.FakeOllamaClient.chat',side_effect=narrator.chat):
            return await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",json=command)

    async def test_actual_prechange_receipt_bytes_and_omitted_null_hash_survive_restart(self):
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        fixture=json.loads(FIXTURE.read_text());path=Path(self.temporary_directory.name)/'prechange.sqlite3'
        with sqlite3.connect(path) as connection:
            connection.executescript(fixture['sqlite_dump'])
            connection.execute(f"PRAGMA user_version={fixture['sqlite_user_version']}")
        self.store=CampaignStore(path,bound_principal=TEST_PLAYER)
        a=copy.deepcopy(fixture['campaign']);r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),fixture['runtime'])
        expected=copy.deepcopy(fixture['response']);expected['session_id']=a['session_id']
        before=self.snapshot(r)
        with patch('game.perform_skill_check',side_effect=AssertionError('old receipt rerolled')):
            for command in (fixture['command'],{**fixture['command'],'check_feature':None}):
                response=await self.post(a,command);self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json(),expected)
        self.assertEqual(self.snapshot(r),before)
        receipt=self.manager.get_turn_action(r,fixture['command']['action_id']);self.assertEqual(receipt['request_hash'],HASH)
        with sqlite3.connect(path) as connection:
            raw=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',(a['campaign_id'],fixture['command']['action_id'])).fetchone()[0]
        self.assertEqual(raw,fixture['response_json'])
        self.assertNotIn('check_feature',expected['skill_check_result'])
        self.assertNotIn('original_ability',expected['skill_check_result'])
        self.assertNotIn('primal_knowledge_check',expected['state']['character'])

    async def test_explicit_request_reaches_actual_strength_check_and_projection(self):
        a,r,command=await self.ready()
        with patch('game.roll_d20',side_effect=[5,16]):response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()['skill_check_result']
        self.assertEqual((result['check_feature'],result['original_ability'],result['ability']),('primal_knowledge','dexterity','strength'))
        self.assertEqual(result['d20_rolls'],[5,16])
        self.assertEqual(result['action_id'],command['action_id'])
        self.assertEqual(response.json()['state']['character']['primal_knowledge_check']['skills'],['Acrobatics','Intimidation','Perception','Stealth','Survival'])
        self.assertNotIn('_PrimalKnowledge',response.text)

    async def test_schema_retains_only_explicit_option_and_refuses_mixed_client_authority(self):
        value={'message':'Takla atıyorum','interaction_mode':'do','check_feature':'primal_knowledge'}
        try:parsed=TurnRequest.model_validate(value)
        except ValueError as error:self.fail(f'Explicit feature rejected: {error}')
        self.assertEqual(parsed.model_dump(exclude_none=True),value)
        for extra in ({'interaction_mode':'say'},{'interaction_mode':None},{'combat_action':{'steps':[{'kind':'dash'}]}},
                      {'combat_id':'x','combat_round':1,'combat_turn_index':0},{'check_feature':True},{'check_feature':'other'},
                      {'ability':'strength'},{'skill':'Acrobatics'},{'dc':1},{'modifier':10},{'check_evidence':[]}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):TurnRequest.model_validate({**value,**extra})

    async def test_actual_http503_has_no_permanent_refusal_and_exact_same_id_retries(self):
        a,r,command=await self.ready();before=self.snapshot(r)
        with patch('api.tests.test_campaign_api.FakeOllamaClient.chat',return_value={'message':{'content':'not usable JSON'}}):
            failed=await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",json=command)
        self.assertEqual(failed.status_code,503,failed.text)
        self.assertEqual(failed.json()['detail']['code'],'intent_json_invalid')
        self.assertEqual(self.snapshot(r),before)
        self.assertIsNone(self.manager.get_refused_action(r,command['action_id']))
        self.assertIsNone(self.manager.get_turn_action(r,command['action_id']))
        self.assertEqual(self.manager.unresolved_action(r)['action_id'],command['action_id'])
        response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['skill_check_result']['check_feature'],'primal_knowledge')
        self.assertIsNone(self.manager.unresolved_action(r))

    async def test_actual_sqlite_precommit_fault_restores_full_runtime_and_retry_rolls_once(self):
        a,r,command=await self.ready();before=self.snapshot(r)
        transaction=self.store._transaction;reached=[]
        @contextmanager
        def fault():
            with transaction() as connection:
                yield connection
                row=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',(a['campaign_id'],command['action_id'])).fetchone()
                if row:
                    reached.append(True)
                    raise sqlite3.OperationalError('synthetic primal precommit after actual receipt insert')
        with patch.object(self.store,'_transaction',side_effect=fault):failed=await self.post(a,command)
        self.assertGreaterEqual(failed.status_code,500,failed.text)
        self.assertEqual(reached,[True]);self.assertEqual(self.snapshot(r),before)
        self.assertIsNone(self.manager.get_turn_action(r,command['action_id']))
        accepted=await self.post(a,command);self.assertEqual(accepted.status_code,200,accepted.text)
        before=self.snapshot(r)
        with patch('game.perform_skill_check',side_effect=AssertionError('retry rerolled')):
            self.assertEqual((await self.post(a,command)).json(),accepted.json())
        self.assertEqual(self.snapshot(r),before)

    async def test_lost_ack_status_fresh_manager_replay_and_feature_hash_conflict(self):
        from api.persistence.campaign_models import CampaignStorageError
        a,r,command=await self.ready();original=self.manager.autosave_turn
        def lost(*args,**kwargs):
            original(*args,**kwargs)
            raise CampaignStorageError('synthetic primal committed acknowledgement lost')
        with patch.object(self.manager,'autosave_turn',side_effect=lost):failed=await self.post(a,command)
        self.assertGreaterEqual(failed.status_code,500,failed.text)
        status=await self.http.get(f"/api/game/sessions/{a['session_id']}/actions/{command['action_id']}")
        self.assertEqual(status.status_code,200,status.text);self.assertEqual(status.json()['state'],'applied')
        with patch('game.perform_skill_check',side_effect=AssertionError('lost acknowledgement rerolled')):
            response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        canonical={'message':'Takla atıyorum','target_id':None,'interaction_mode':'do','check_feature':'primal_knowledge'}
        expected_hash=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(self.manager.get_turn_action(r,command['action_id'])['request_hash'],expected_hash)
        for value in (None,'omit'):
            changed={**command,'check_feature':value}
            if value=='omit':changed.pop('check_feature')
            conflict=await self.post(a,changed);self.assertEqual(conflict.status_code,409,conflict.text)
            self.assertEqual(conflict.json()['detail']['code'],'action_id_conflict')
        r=await self.reopen(a);expected=response.json();expected['session_id']=a['session_id'];before=self.snapshot(r)
        with patch('game.perform_skill_check',side_effect=AssertionError('fresh replay rerolled')):
            self.assertEqual((await self.post(a,command)).json(),expected)
        self.assertEqual(self.snapshot(r),before)

    async def test_completed_annotation_survives_expiry_before_response_and_saved_history(self):
        a,r,command=await self.ready();original=serialize_skill_check_result
        def expire(result,session,**kwargs):
            session.world_state['campaign_time']['elapsed_seconds']+=13
            barbarian_rage.settle(session)
            return original(result,session,**kwargs)
        with patch('api.main.serialize_skill_check_result',side_effect=expire):response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        body=response.json();self.assertFalse(body['state']['character']['rage']['active'])
        self.assertFalse(body['state']['character']['primal_knowledge_check']['available'])
        self.assertEqual(body['skill_check_result']['check_feature'],'primal_knowledge')
        r=await self.reopen(a);expected=body;expected['session_id']=a['session_id']
        with patch('game.perform_skill_check',side_effect=AssertionError('expired receipt rerolled')):
            self.assertEqual((await self.post(a,command)).json(),expected)
        history=await self.http.get(f"/api/game/campaigns/{a['campaign_id']}")
        self.assertEqual(history.status_code,200,history.text)
        matches=[entry['skill_check_result'] for entry in history.json()['history'] if entry.get('skill_check_result')]
        self.assertIn(body['skill_check_result'],matches)

    async def test_foreign_owner_campaign_isolation_and_stale_intent_never_roll(self):
        from api.auth import FixedAuthenticator
        from api.tests.auth_fixture import TEST_PLAYER,PLAYER_B
        from api.session_manager import SessionManager
        from api.persistence.campaign_store import CampaignStore
        a,r,command=await self.ready();before=self.snapshot(r)
        self.app.state.authenticator=FixedAuthenticator(PLAYER_B)
        try:
            self.assertEqual((await self.post(a,command)).status_code,404)
        finally:self.app.state.authenticator=FixedAuthenticator(TEST_PLAYER)
        self.assertEqual(self.snapshot(r),before)
        other,other_r,other_command=await self.ready();other_command['action_id']=command['action_id']
        accepted=await self.post(other,other_command);self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertIsNone(self.manager.get_turn_action(r,command['action_id']))
        fresh=SessionManager(campaign_store=CampaignStore(self.store.path,bound_principal=TEST_PLAYER))
        fresh.resume_campaign(a['campaign_id']);fresh.save_campaign(a['campaign_id']);before=self.snapshot(r)
        with patch('game.perform_skill_check',side_effect=AssertionError('stale intent rolled')):
            failed=await self.post(a,command)
        self.assertEqual(failed.status_code,409,failed.text);self.assertEqual(failed.json()['detail']['code'],'campaign_stale')
        self.assertEqual(self.snapshot(r),before)

    async def test_unsupported_preflight_precedes_scene_model_clock_and_rng(self):
        a,r,command=await self.ready();s=r.game_session
        for message,extra in [('İzleri on dakika takip ediyorum',{}),('Bir saat bekliyorum',{}),('Takla atıyorum ve ormana gidiyorum',{}),
                              ('Merhaba',{}),('Takla atıyorum',{'target_id':'npc_001'})]:
            before=self.snapshot(r);bad={**command,**extra,'message':message,'action_id':str(uuid4())}
            with self.subTest(message=message),patch.object(s,'plan_living_world_turn',side_effect=AssertionError('preflight reached mutating scene planner')),patch('api.tests.test_campaign_api.FakeOllamaClient.chat',side_effect=AssertionError('preflight reached model')):
                refused=await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",json=bad)
            self.assertEqual(refused.status_code,400,refused.text)
            self.assertEqual(refused.json()['detail']['code'],'primal_knowledge_immediate_check_only')
            self.assertEqual(self.snapshot(r),before)

    async def test_ordinary_and_explicit_null_remain_dexterity_and_kwargs_compatible(self):
        for value in ('omit',None):
            a,r,command=await self.ready();command['check_feature']=value
            if value=='omit':command.pop('check_feature')
            real=game.run_player_turn;seen=[]
            def observe(*args,**kwargs):
                seen.append(kwargs.copy());return real(*args,**kwargs)
            observe.__signature__=inspect.signature(real)
            with patch('game.run_player_turn',side_effect=observe),patch('game.roll_d20',return_value=11):response=await self.post(a,command)
            self.assertEqual(response.status_code,200,response.text)
            result=response.json()['skill_check_result'];self.assertEqual(result['ability'],'dexterity')
            self.assertNotIn('check_feature',result);self.assertNotIn('original_ability',result)
            self.assertTrue(seen);self.assertNotIn('check_feature',seen[-1]);self.assertNotIn('check_evidence',seen[-1])
            self.assertEqual(self.manager.get_turn_action(r,command['action_id'])['request_hash'],HASH)

    async def test_quoted_question_preflight_variants_preserve_actual_check_with_interlocutor(self):
        for text in ('Gizleniyorum?', '"Gizleniyorum"', 'Bir şey fark etmeye çalışıyorum?',
                     '"Bir şey fark etmeye çalışıyorum"', 'Onu korkutmaya çalışıyorum?', '"Onu korkutmaya çalışıyorum"'):
            a,r,command=await self.ready();s=r.game_session
            npc=next(n for n in s.world_state['npcs'] if n.get('location')=='tavern')
            s.world_state['flags'].update(active_npc_id=npc['id'],active_npc_until_turn=100)
            self.manager.save_campaign(a['campaign_id']);before=self.snapshot(r)
            try:admission=s.primal_knowledge_check_admission(text,interaction_mode='do')
            except ValueError:admission=None
            self.assertEqual(self.snapshot(r),before)
            response=await self.post(a,{**command,'message':text})
            with self.subTest(text=text):
                if admission is None:
                    self.assertEqual(response.status_code,400,response.text);self.assertEqual(self.snapshot(r),before)
                else:
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['skill_check_result']['skill'],admission['skill'])
                    self.assertEqual(response.json()['skill_check_result']['check_feature'],'primal_knowledge')

    async def test_actual_factory_openapi_preserves_option_and_annotated_result_fields(self):
        schema=self.app.openapi()['components']['schemas']
        self.assertIn('primal_knowledge',schema['TurnRequest']['properties']['check_feature']['anyOf'][0]['enum'])
        self.assertIn('primal_knowledge',schema['SkillCheckResult']['properties']['check_feature']['anyOf'][0]['enum'])
        self.assertIn('original_ability',schema['SkillCheckResult']['properties'])
        self.assertNotIn('check_evidence',json.dumps(schema))

class PrimalKnowledgeSerializerTests(unittest.TestCase):
    def completed(self):
        session,_=selected(self);evidence=[]
        with resolution_action_scope('5df78dbd-3908-4a4d-bd91-1888fe1ccc0c'),patch('game.roll_d20',side_effect=[5,16]):
            result=session.execute_intent({'intent':'unknown'},'Takla atıyorum',check_feature='primal_knowledge',check_evidence=evidence)
        return session,result,evidence

    def project(self,result,session,evidence):
        kwargs={'check_evidence':evidence} if 'check_evidence' in inspect.signature(serialize_skill_check_result).parameters else {}
        return serialize_skill_check_result(result,session,**kwargs)

    def test_proven_completed_roll_survives_rage_expiry_without_current_authorization(self):
        session,result,evidence=self.completed();session.world_state['campaign_time']['elapsed_seconds']=30
        try:value=self.project(result,session,evidence)
        except ValueError as error:self.fail(f'Actual completed feature result rejected: {error}')
        self.assertEqual((value['check_feature'],value['original_ability'],value['ability']),('primal_knowledge','dexterity','strength'))
        self.assertFalse(barbarian_rage.active(session))

    def test_dictionary_forgery_and_completed_resolution_mismatch_refuse(self):
        session,result,evidence=self.completed()
        for fake in (None,[],[{}],[{'check_feature':'primal_knowledge'}],evidence*2):
            with self.subTest(fake=repr(fake)),self.assertRaises(ValueError):self.project(result,session,fake)
        for field,value in [('total',99),('modifier',True),('proficiency_bonus',0),('dice',True),('dice_rolls',[16]),('expertise',True),('resolution_id','other')]:
            bad=copy.deepcopy(result);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.project(bad,session,evidence)

    def test_proven_feature_cannot_forge_outcome_or_hide_proof_on_noncheck(self):
        session,result,evidence=self.completed()
        bad=copy.deepcopy(result);bad['outcome']='failure'
        for value in (bad,{'action':'narrative'}):
            with self.subTest(value=value.get('action')),self.assertRaises(ValueError):self.project(value,session,evidence)

    def test_historical_annotation_consistency_is_validated_without_live_session(self):
        plain={'skill':'Acrobatics','ability':'strength','original_ability':'dexterity','check_feature':'primal_knowledge','d20':16,'d20_rolls':[5,16],'advantage':True,'proficient':True,'ability_modifier':2,'proficiency_modifier':2,'total_modifier':4,'total':20,'difficulty':'medium','dc':15,'outcome':'success','action_id':'5df78dbd-3908-4a4d-bd91-1888fe1ccc0c','resolution_id':'5df78dbd-3908-4a4d-bd91-1888fe1ccc0c:skill_check:1'}
        try:valid=SkillCheckResult.model_validate(plain,strict=True)
        except ValueError as error:self.fail(f'Valid historical annotation rejected: {error}')
        self.assertEqual(valid.model_dump(exclude_none=True),plain)
        for extra in ({'skill':'Athletics'},{'ability':'dexterity'},{'original_ability':'wisdom'},{'check_feature':None},{'action_id':None},{'resolution_id':None}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):SkillCheckResult.model_validate({**plain,**extra},strict=True)
