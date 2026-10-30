"""Bounded earned Barbarian4 via actual ASGI HTTP and synthetic SQLite campaigns."""
import copy
import hashlib
import json
import unittest
from uuid import uuid4
from unittest.mock import patch
import xp
from api.tests import test_roadmap_c10_berserker_http as three
from api.tests import test_roadmap_c06_level4_http as sorcerer


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class BarbarianFourHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=three.BerserkerHttpTests.asyncSetUp
    asyncTearDown=three.BerserkerHttpTests.asyncTearDown
    reopen=three.BerserkerHttpTests.reopen
    snapshot=three.BerserkerHttpTests.snapshot
    url=three.BerserkerHttpTests.url
    preview=three.BerserkerHttpTests.preview
    command=three.BerserkerHttpTests.command

    async def test_pre_api_existing_request_receipt_oracles(self):
        from api.schemas import LevelUpApplyRequest,LevelUpCommandResult
        oracles={}
        for name in ('sorcerer4','barbarian3'):
            if name=='sorcerer4':
                a,r=await sorcerer.LevelFourHttpTests.earned(self)
                p=await self.preview(a); command=sorcerer.LevelFourHttpTests.request(self,a,p)
            else:
                a,r=await three.BerserkerHttpTests.earned(self)
                p=await self.preview(a);command=self.command(a,three.PICK,p)
            response=await self.http.post(self.url(a),json=command)
            self.assertEqual(response.status_code,200,response.text)
            receipt=self.manager.get_turn_action(r,command['action_id'])
            self.assertEqual(receipt['request_hash'],digest({'command':'level_up',**{k:v for k,v in command.items() if k!='action_id'}}))
            self.assertEqual(LevelUpApplyRequest.model_validate(command).model_dump(mode='json'),command)
            self.assertEqual(LevelUpCommandResult.model_validate(receipt['response']).model_dump(mode='json'),response.json())
            before=self.snapshot(r)
            with patch('character_progression.apply_level_choices',side_effect=AssertionError('old receipt reapplied')):
                replay=await self.http.post(self.url(a),json=command)
            self.assertEqual(replay.json(),response.json());self.assertEqual(self.snapshot(r),before)
            oracles[name]={'request':command,'receipt':receipt,'preview':p,'campaign':a,'runtime':r.game_session.serialize_game_state()}
        import sqlite3
        with sqlite3.connect(self.store.path) as connection:
            fixture={'oracles':oracles,'sqlite_dump':'\n'.join(connection.iterdump()),'sqlite_user_version':connection.execute('PRAGMA user_version').fetchone()[0]}
        print('BARBARIAN4_CURRENT_API_ORACLES:'+json.dumps({name:{'request':value['request'],'request_hash':value['receipt']['request_hash']} for name,value in oracles.items()},sort_keys=True))

    async def earned(self,raw=4):
        a,r=await three.BerserkerHttpTests.earned(self)
        response=await self.http.post(self.url(a),json=self.command(a,three.PICK,await self.preview(a)))
        self.assertEqual(response.status_code,200,response.text)
        if raw>3:
            s=r.game_session
            s._receive_xp_award(xp.apply_xp,s.character,s.world_state,1800 if raw==4 else 5600,'quest:synthetic-earned-four-http')
            self.manager.save_campaign(a['campaign_id'])
        return a,r

    def pick(self,increase=None):
        return {'asi':{'feat':'Ability Score Improvement','increase':copy.deepcopy(increase or {'constitution':2})}}

    async def ready(self,a):
        p=await self.preview(a)
        self.assertEqual((p['status'],p['target_level']),('ready',4),p)
        return p

    async def test_exact_new_shape_and_all_fifteen_strict_patterns(self):
        from api.schemas import LevelUpApplyRequest
        from api.tests.test_roadmap_c06_nondex_asi import PATTERNS
        for inc in PATTERNS:
            command={'action_id':str(uuid4()),'campaign_id':str(uuid4()),'expected_revision':0,'target_level':4,'choices':self.pick(inc)}
            try:parsed=LevelUpApplyRequest.model_validate(command)
            except ValueError as error:self.fail(f'exact Barbarian4 ASI refused: {error}')
            self.assertEqual(type(parsed.choices).__name__,'BarbarianLevel4Choices')
            self.assertEqual(parsed.model_dump(mode='json'),command)

    async def test_actual_public_preview_asi_only_filtered_and_no_mutation(self):
        a,r=await self.earned();before=self.snapshot(r);p=await self.ready(a)
        self.assertEqual(p['class_name'],'Barbarian');self.assertEqual(p['choices_required'],{'asi':1})
        self.assertIsNone(p['capacity']);self.assertEqual(len(p['supported_asi_choices']),21)
        self.assertEqual(p['prepared_spell_ids'],[]);self.assertEqual(p['cantrip_ids'],[])
        self.assertIn('Weapon Mastery',' '.join(p['effects_pending']))
        self.assertEqual(self.snapshot(r),before)
        r.game_session.character['armor_class']+=2
        p=await self.ready(a)
        self.assertNotIn(self.pick()['asi'],p['supported_asi_choices'])
        self.assertIn(self.pick({'strength':2})['asi'],p['supported_asi_choices'])

    async def test_earned_con_literal_ac_hp_spent_resources_restart_and_exact_replay(self):
        import hit_dice
        a,r=await self.earned();s=r.game_session
        self.assertEqual((s.character['max_hp'],s.character['current_hp'],s.character['armor_class']),(41,41,15))
        # A retained spent/window record is an authored persistence prerequisite, not a new spending grant.
        s.character['hit_dice']={'spent':2,'window_second':0,'hp':32}
        s.commit_location_change('tavern');npc=s.create_npc_from_ai({'name':'Rakip','role':'Guard','location':'tavern'})
        npc.update(current_hp=100,max_hp=100,armor_class=20,hostile=True,distance_ft=5)
        s.world_state.setdefault('monster_perception',{})[npc['id']]={'player':{'visible':True}}
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
        self.manager.save_campaign(a['campaign_id'])
        activate={'message':'Rage','action_id':str(uuid4()),'combat_action':{'steps':[{'kind':'activate_rage','resource':'bonus'}]}}
        response=await self.http.post(f"/api/game/sessions/{a['session_id']}/turn",json=activate)
        self.assertEqual(response.status_code,200,response.text)
        resources=copy.deepcopy((s.world_state['rage_v1'],s.character['hit_dice'],s.world_state['inventory'],s.world_state['campaign_time'],s.rng.getstate()))
        p=await self.ready(a);command=self.command(a,self.pick(),p)
        response=await self.http.post(self.url(a),json=command);self.assertEqual(response.status_code,200,response.text)
        c=response.json()['state']['character']
        self.assertEqual((c['level'],c['progression_level'],c['xp'],c['max_hp'],c['current_hp'],c['armor_class']),(4,4,2700,45,41,16))
        self.assertEqual((hit_dice.total(s.character),hit_dice.remaining(s.character)),(4,2))
        self.assertEqual((s.world_state['rage_v1'],s.character['hit_dice'],s.world_state['inventory'],s.world_state['campaign_time'],s.rng.getstate()),resources)
        self.assertNotIn('spellcasting_v1',s.world_state);self.assertEqual(s.character['spells'],[])
        runtime=copy.deepcopy(s.serialize_game_state());r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),runtime)
        expected=response.json();expected['session_id']=a['session_id'];before=self.snapshot(r)
        with patch('character_progression.apply_level_choices',side_effect=AssertionError('ASI replayed')):
            self.assertEqual((await self.http.post(self.url(a),json=command)).json(),expected)
        self.assertEqual(self.snapshot(r),before)
        changed=copy.deepcopy(command);changed['choices']=self.pick({'strength':2})
        conflict=await self.http.post(self.url(a),json=changed)
        self.assertEqual(conflict.status_code,409);self.assertEqual(conflict.json()['detail']['code'],'action_id_conflict')

    async def test_unearned_creation_ceiling_and_raw_five_queue(self):
        from api.tests.test_roadmap_c06_barbarian_creation_http import request
        a,r=await self.earned(raw=3);p=await self.preview(a)
        self.assertEqual((p['status'],p['reason'],p['target_level']),('blocked','level_not_earned',4))
        before=self.snapshot(r);response=await self.http.post(self.url(a),json=self.command(a,self.pick(),p))
        self.assertEqual(response.status_code,409);self.assertEqual(self.snapshot(r),before)
        for level in (3,4):
            data=request(2);data['starting_level']=level
            self.assertEqual((await self.http.post('/api/game/campaigns',json={'character':data})).status_code,422)
        a,r=await self.earned(raw=5);p=await self.ready(a);old=r.game_session.character['max_hp']
        bad=self.command(a,self.pick(),p);bad['target_level']=5
        self.assertEqual((await self.http.post(self.url(a),json=bad)).status_code,422)
        response=await self.http.post(self.url(a),json=self.command(a,self.pick(),p));self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((r.game_session.character['level'],r.game_session.character['progression_level'],r.game_session.character['max_hp']),(5,4,old+5))
        p=await self.preview(a);self.assertEqual((p['status'],p['reason'],p['target_level']),('ready',None,5))  # earned level 5 is supported (test_roadmap_c06_barbarian_level5_http)

    async def test_invalid_extra_null_alias_numeric_fields_reject_without_intent(self):
        a,r=await self.earned();p=await self.ready(a);before=self.snapshot(r)
        for choices in ({},None,{**self.pick(),'cantrips':[]},{**self.pick(),'prepared_spells':[]},{**self.pick(),'extra':None},
                        {'asi':None},self.pick({'dexterity':3}),self.pick({'constitution':True}),self.pick({'constitution':'2'}),self.pick({'constitution':2.0}),
                        self.pick({'CON':2}),self.pick({'constitution':1}),self.pick({'strength':1,'constitution':2})):
            response=await self.http.post(self.url(a),json=self.command(a,choices,p))
            self.assertEqual(response.status_code,422,response.text);self.assertEqual(self.snapshot(r),before)
            self.assertIsNone(self.manager.unresolved_action(r))

    async def test_actual_class_mismatch_cap_and_stale_con_eligibility_refuse(self):
        from api.tests.test_roadmap_c06_level4_con import PICK as caster
        a,r=await self.earned();p=await self.ready(a)
        response=await self.http.post(self.url(a),json=self.command(a,caster,p))
        self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail']['code'],'level_up_choice_class_mismatch')
        a2,r2=await sorcerer.LevelFourHttpTests.earned(self);p2=await self.preview(a2);before=self.snapshot(r2)
        response=await self.http.post(self.url(a2),json=self.command(a2,self.pick(),p2))
        self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail']['code'],'level_up_choice_class_mismatch');self.assertEqual(self.snapshot(r2),before)
        # Same-revision AC source drift: recompute admission, not500 and not stale-option acceptance.
        r.game_session.character['armor_class']+=2;before=self.snapshot(r)
        response=await self.http.post(self.url(a),json=self.command(a,self.pick(),p))
        self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail']['code'],'asi_choice_not_eligible');self.assertEqual(self.snapshot(r),before)

    async def test_missing_source_and_prior_record_refuse_without_adoption(self):
        for source in ('rage_v1','worn_armor_v1','primal_knowledge_choice'):
            a,r=await self.earned();p=await self.ready(a);s=r.game_session
            (s.character if source=='primal_knowledge_choice' else s.world_state).pop(source)
            before=s._capture_runtime_snapshot();response=await self.http.post(self.url(a),json=self.command(a,self.pick(),p))
            self.assertEqual(response.status_code,409,response.text);self.assertEqual(s._capture_runtime_snapshot(),before)

    async def test_sqlite_precommit_restores_rng_format_ac_and_saved_payload_then_exact_retry(self):
        from contextlib import contextmanager
        import sqlite3
        a,r=await self.earned();command=self.command(a,self.pick(),await self.ready(a));s=r.game_session
        before=self.snapshot(r);format_state=copy.deepcopy(('_persisted_engine_format' in s.__dict__,s.__dict__.get('_persisted_engine_format')))
        transaction=self.store._transaction;reached=[]
        @contextmanager
        def fail_after_receipt():
            with transaction() as connection:
                yield connection
                row=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',(a['campaign_id'],command['action_id'])).fetchone()
                if row:reached.append(True);raise sqlite3.OperationalError('synthetic Barbarian4 SQLite precommit')
        with patch.object(self.store,'_transaction',side_effect=fail_after_receipt):response=await self.http.post(self.url(a),json=command)
        self.assertGreaterEqual(response.status_code,500,response.text);self.assertEqual(reached,[True]);self.assertEqual(self.snapshot(r),before)
        self.assertEqual(('_persisted_engine_format' in s.__dict__,s.__dict__.get('_persisted_engine_format')),format_state)
        response=await self.http.post(self.url(a),json=command);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((s.character['max_hp'],s.character['current_hp'],s.character['armor_class']),(45,41,16))
        self.assertEqual((await self.http.post(self.url(a),json=command)).json(),response.json())

    async def test_committed_lost_ack_status_recovery_exact_retry_and_duplicate_one_revision(self):
        import asyncio
        from api.persistence.campaign_models import CampaignStorageError
        a,r=await self.earned();p=await self.ready(a);command=self.command(a,self.pick(),p);original=self.manager.save_campaign_locked
        r.undo_checkpoint={'synthetic_old_turn':True}
        def commit_then_fail(*args,**kwargs):
            original(*args,**kwargs);raise CampaignStorageError('synthetic Barbarian4 committed acknowledgement lost')
        with patch.object(self.manager,'save_campaign_locked',side_effect=commit_then_fail):response=await self.http.post(self.url(a),json=command)
        self.assertGreaterEqual(response.status_code,500,response.text);self.assertIsNone(r.undo_checkpoint)
        status=await self.http.get(f"/api/game/sessions/{a['session_id']}/actions/{command['action_id']}")
        self.assertEqual(status.json()['state'],'applied');self.assertIsNone(status.json()['response'])
        responses=await asyncio.gather(*(self.http.post(self.url(a),json=command) for _ in range(2)))
        self.assertEqual([r.status_code for r in responses],[200,200]);self.assertEqual(responses[0].json(),responses[1].json())
        self.assertEqual(self.store.get_campaign(a['campaign_id']).metadata['revision'],p['revision']+1)
        self.assertEqual((r.game_session.character['max_hp'],r.game_session.character['armor_class']),(45,16))

    async def test_owner_campaign_revision_and_stale_session_refuse_no_effects(self):
        from api.auth import FixedAuthenticator
        from api.tests.auth_fixture import TEST_PLAYER,PLAYER_B
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        a,r=await self.earned();p=await self.ready(a);command=self.command(a,self.pick(),p);before=self.snapshot(r)
        self.app.state.authenticator=FixedAuthenticator(PLAYER_B)
        try:self.assertEqual((await self.http.post(self.url(a),json=command)).status_code,404)
        finally:self.app.state.authenticator=FixedAuthenticator(TEST_PLAYER)
        self.assertEqual(self.snapshot(r),before)
        for key,value,code in [('campaign_id',str(uuid4()),'level_up_campaign_mismatch'),('expected_revision',p['revision']-1,'level_up_preview_stale')]:
            bad=copy.deepcopy(command);bad.update(action_id=str(uuid4()));bad[key]=value
            response=await self.http.post(self.url(a),json=bad);self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail']['code'],code)
            self.assertEqual(r.game_session._capture_runtime_snapshot(),before[0])
        fresh=SessionManager(campaign_store=CampaignStore(self.store.path,bound_principal=TEST_PLAYER));fresh.resume_campaign(a['campaign_id']);fresh.save_campaign(a['campaign_id'])
        response=await self.http.post(self.url(a),json=command);self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail']['code'],'campaign_stale')

    async def test_actual_pre_api_sqlite_oracle_receipts_and_request_hashes_survive_fresh_resume(self):
        import sqlite3
        from pathlib import Path
        from api.persistence.campaign_store import CampaignStore
        from api.tests.auth_fixture import TEST_PLAYER
        from api.schemas import LevelUpApplyRequest
        fixture=json.loads((Path(__file__).parent/'fixtures/c06_pre_barbarian4_http_receipts.json').read_text())
        path=Path(self.temporary_directory.name)/'before-barbarian4.sqlite3'
        with sqlite3.connect(path) as connection:
            connection.executescript(fixture['sqlite_dump']);connection.execute(f"PRAGMA user_version={fixture['sqlite_user_version']}")
        self.store=CampaignStore(path,bound_principal=TEST_PLAYER)
        for name,oracle in fixture['oracles'].items():
            a=copy.deepcopy(oracle['campaign']);r=await self.reopen(a);runtime=r.game_session.serialize_game_state();runtime['player'].pop('armor_origin',None);self.assertEqual(runtime,oracle['runtime'])  # the one additive read-time repair
            command=oracle['request'];self.assertEqual(LevelUpApplyRequest.model_validate(command).model_dump(mode='json'),command)
            frozen_hash={'sorcerer4':'f67acd162f1ca010d2578f835cd1b53356dddf5b61592803daad7fba56670211',
                         'barbarian3':'9fc2c61bea962fd4e6f2f2e6e5c34c74f0f1790947cd3091362ce23297c7f5dc'}[name]
            self.assertEqual(oracle['receipt']['request_hash'],frozen_hash)
            self.assertEqual(digest({'command':'level_up',**{key:value for key,value in command.items() if key!='action_id'}}),frozen_hash)
            expected=copy.deepcopy(oracle['receipt']['response']);expected['session_id']=a['session_id'];before=self.snapshot(r)
            with sqlite3.connect(path) as connection:old_raw=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',(a['campaign_id'],command['action_id'])).fetchone()[0]
            with patch('character_progression.apply_level_choices',side_effect=AssertionError('pre API receipt reapplied')):
                response=await self.http.post(self.url(a),json=command)
            self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json(),expected);self.assertEqual(self.snapshot(r),before)
            self.assertEqual(self.manager.get_turn_action(r,command['action_id'])['request_hash'],oracle['receipt']['request_hash'])
            with sqlite3.connect(path) as connection:self.assertEqual(connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',(a['campaign_id'],command['action_id'])).fetchone()[0],old_raw)

    async def test_openapi_actual_factory_new_component_and_existing_union_parity(self):
        import yaml
        from pathlib import Path
        actual=self.app.openapi();published=yaml.safe_load((Path(__file__).resolve().parents[3]/'lib/api-spec/openapi.yaml').read_text())
        print('BARBARIAN4_API_COMPONENTS:'+json.dumps({name:actual['components']['schemas'][name] for name in ('BarbarianLevel4Choices','LevelUpApplyRequest','LevelUpAsiChoice','LevelUpChoices')},sort_keys=True))
        self.assertIn('BarbarianLevel4Choices',actual['components']['schemas'])
        for name in ('BarbarianLevel4Choices','LevelUpApplyRequest','LevelUpChoices','LevelUpAsiChoice'):
            runtime=copy.deepcopy(actual['components']['schemas'][name])
            if name=='LevelUpAsiChoice':
                # Exact pre-edit annotation mismatch, not a constraint relaxation:
                # published increase lacks only Pydantic's display title='Increase'.
                self.assertEqual(runtime['properties']['increase'].pop('title'),'Increase')
                self.assertNotIn('title',published['components']['schemas'][name]['properties']['increase'])
            self.assertEqual(runtime,published['components']['schemas'][name],name)
        new=actual['components']['schemas']['BarbarianLevel4Choices'];self.assertEqual(set(new['properties']),{'asi'});self.assertFalse(new['additionalProperties'])

    async def test_actual_cap_twenty_filters_and_refuses_without_mutation(self):
        from api.tests.test_roadmap_c06_barbarian_creation_http import request
        data=request(2);data.update(ability_score_method='manual',background_ability_bonuses={'constitution':2,'dexterity':1})
        data['ability_scores']['constitution']=18
        response=await self.http.post('/api/game/campaigns',json={'character':data});self.assertEqual(response.status_code,200,response.text)
        a=response.json();r=self.manager.get(a['session_id']);s=r.game_session
        s._receive_xp_award(xp.apply_xp,s.character,s.world_state,600,'quest:synthetic-cap-three');self.manager.save_campaign(a['campaign_id'])
        response=await self.http.post(self.url(a),json=self.command(a,three.PICK,await self.preview(a)));self.assertEqual(response.status_code,200,response.text)
        s._receive_xp_award(xp.apply_xp,s.character,s.world_state,1800,'quest:synthetic-cap-four');self.manager.save_campaign(a['campaign_id'])
        p=await self.ready(a);self.assertEqual(s.character['constitution'],20)
        self.assertTrue(all('constitution' not in choice['increase'] for choice in p['supported_asi_choices']))
        before=self.snapshot(r);response=await self.http.post(self.url(a),json=self.command(a,self.pick(),p))
        self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail']['code'],'asi_choice_not_eligible');self.assertEqual(self.snapshot(r),before)

    async def test_all_fifteen_actual_http_asi_applications_keep_exact_noncaster_body(self):
        from api.tests.test_roadmap_c06_nondex_asi import PATTERNS
        for inc in PATTERNS:
            with self.subTest(increase=inc):
                a,r=await self.earned();command=self.command(a,self.pick(inc),await self.ready(a));before=copy.deepcopy(r.game_session.world_state)
                response=await self.http.post(self.url(a),json=command);self.assertEqual(response.status_code,200,response.text)
                s=r.game_session;self.assertEqual(s.character['asi_choices'],[{'class_level':4,**self.pick(inc)['asi']}])
                self.assertEqual((s.character['max_hp'],s.character['current_hp'],s.character['armor_class']),(45,41,16) if inc=={'constitution':2} else (41,41,16) if inc=={'dexterity':2} else (41,41,15))
                self.assertEqual((s.character['xp'],s.character['level'],s.character['progression_level']),(2700,4,4))
                self.assertEqual(s.world_state,before);self.assertNotIn('spellcasting_v1',s.world_state)
