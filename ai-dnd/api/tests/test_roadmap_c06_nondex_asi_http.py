"""Actual fifteen-pattern non-DEX ASI HTTP contract; no general feats/armor claim."""
import copy
import hashlib
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import httpx
from api.auth import FixedAuthenticator
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests import test_roadmap_c06_level4_http as previous
from api.tests.test_roadmap_c06_creation45_http import request as creation_request
from api.schemas import LevelUpAsiChoice

PATTERNS = [
    {'strength':2}, {'constitution':2}, {'intelligence':2}, {'wisdom':2}, {'charisma':2},
    {'strength':1,'constitution':1}, {'strength':1,'intelligence':1}, {'strength':1,'wisdom':1}, {'strength':1,'charisma':1},
    {'constitution':1,'intelligence':1}, {'constitution':1,'wisdom':1}, {'constitution':1,'charisma':1},
    {'intelligence':1,'wisdom':1}, {'intelligence':1,'charisma':1}, {'wisdom':1,'charisma':1},
]
FIXTURE = Path(__file__).parent/'fixtures/c06_checkpoint13_con_asi_receipt.json'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

class NonDexAsiHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = previous.LevelFourHttpTests.asyncSetUp
    asyncTearDown = previous.LevelFourHttpTests.asyncTearDown
    earned = previous.LevelFourHttpTests.earned
    ready = previous.LevelFourHttpTests.ready
    url = previous.LevelFourHttpTests.url
    request = previous.LevelFourHttpTests.request
    reopen = previous.LevelFourHttpTests.reopen

    async def test_actual_earned_charisma_and_split_choice_reach_core(self):
        for increase in ({'charisma':2}, {'constitution':1,'charisma':1}):
            body, record = await self.earned()
            preview = await self.ready(body)
            request = self.request(body, preview); request['choices']['asi']['increase'] = increase
            before = copy.deepcopy(record.game_session.character)
            response = await self.http.post(self.url(body), json=request)
            self.assertEqual(response.status_code,200,response.text)
            for ability, amount in increase.items():
                self.assertEqual(record.game_session.character[ability], before[ability]+amount)
            self.assertEqual(record.game_session.character['armor_class'], before['armor_class'])
            self.assertEqual(record.game_session.character['current_hp'], before['current_hp'])

    async def test_actual_creation_four_and_five_accept_new_patterns(self):
        for level in (4,5):
            for increase in ({'charisma':2}, {'constitution':1,'charisma':1}):
                request = creation_request(level); request['level_choices']['4']['asi']['increase'] = increase
                response = await self.http.post('/api/game/campaigns', json={'character':request})
                self.assertEqual(response.status_code,200,response.text)
                body=response.json(); s=self.manager.get(body['session_id']).game_session
                self.assertEqual(s.character['charisma'],15+increase['charisma'])
                self.assertEqual(s.character['constitution'],14+increase.get('constitution',0))
                self.assertEqual(s.character['current_hp'],s.character['max_hp'])
                self.assertEqual(s.character['xp'],2700 if level==4 else 6500)
                resumed, manager = await self.reopen(body)
                self.assertEqual(manager.get(resumed['session_id']).game_session.serialize_game_state(),s.serialize_game_state())

    async def test_old_actual_con_receipt_replays_without_schema_hash_drift(self):
        fixture=json.loads(FIXTURE.read_text())
        path=Path(self.temporary_directory.name)/'old-con.sqlite3'
        with sqlite3.connect(path) as connection:
            connection.executescript(fixture['sqlite_dump'])
            connection.execute(f"PRAGMA user_version={fixture['sqlite_user_version']}")
        store=CampaignStore(path,bound_principal=TEST_PLAYER); manager=SessionManager(campaign_store=store)
        sid,r,*_=manager.resume_campaign(fixture['campaign']['campaign_id'])
        self.assertEqual(r.game_session.serialize_game_state(),fixture['runtime'])
        literal={'command':'level_up', **{k:v for k,v in fixture['request'].items() if k!='action_id'}}
        self.assertEqual(digest(literal),fixture['request_hash'])
        app=create_app(session_manager=manager,authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            with patch('character_progression.apply_level_choices',side_effect=AssertionError('receipt reapplied ASI')):
                response=await client.post(f'/api/game/sessions/{sid}/level-up',json=fixture['request'])
        self.assertEqual(response.status_code,200,response.text)
        expected=copy.deepcopy(fixture['response']);expected['session_id']=sid
        self.assertEqual(response.json(),expected)
        self.assertEqual(r.game_session.serialize_game_state(),fixture['runtime'])
        self.assertEqual(manager.get_turn_action(r,fixture['request']['action_id'])['request_hash'],fixture['request_hash'])

    async def test_invalid_shapes_reject_before_claim_without_partial_asi(self):
        body,r=await self.earned(); request=self.request(body,await self.ready(body))
        before=r.game_session._capture_runtime_snapshot()
        invalid=[{}, {'dexterity':2}, {'CHA':2}, {'charisma':'2'}, {'charisma':True,'wisdom':1},
                 {'charisma':None}, {'charisma':1}, {'charisma':1.5,'wisdom':0.5},
                 {'charisma':2,'wisdom':1}, {'strength':1,'wisdom':1,'charisma':1},
                 {'charisma':2,'dexterity':None}, {'constitution':2,'charisma':0}]
        for increase in invalid:
            bad=copy.deepcopy(request);bad['choices']['asi']['increase']=increase
            response=await self.http.post(self.url(body),json=bad)
            self.assertEqual(response.status_code,422,response.text)
            self.assertEqual(r.game_session._capture_runtime_snapshot(),before)
        self.assertIsNone(self.manager.unresolved_action(r))

    async def test_authoritative_preview_filters_real_created_cap_and_rejects_stale_choice(self):
        import xp
        from api.tests.test_roadmap_c06_creation_http import character_request
        for con_bonus,increase in ((1,{'constitution':2}),(2,{'constitution':1,'charisma':1})):
            data=character_request(3);data['ability_score_method']='manual';data['ability_scores']['constitution']=18
            data['background_ability_bonuses']={'constitution':con_bonus,'dexterity':3-con_bonus}
            response=await self.http.post('/api/game/campaigns',json={'character':data})
            self.assertEqual(response.status_code,200,response.text)
            body=response.json();r=self.manager.get(body['session_id'])
            self.assertEqual(r.game_session.character['constitution'],18+con_bonus)
            xp.apply_xp(r.game_session.character,r.game_session.world_state,1800,'quest:cap-http')
            self.manager.save_campaign(body['campaign_id'])
            preview=await self.ready(body)
            self.assertNotIn({'feat':'Ability Score Improvement','increase':increase},preview['supported_asi_choices'])
            request=self.request(body,preview);request['choices']['asi']['increase']=increase
            before=r.game_session._capture_runtime_snapshot()
            response=await self.http.post(self.url(body),json=request)
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(r.game_session._capture_runtime_snapshot(),before)

    async def test_actual_fire_bolt_uses_improved_charisma_modifier(self):
        body,r=await self.earned();request=self.request(body,await self.ready(body))
        request['choices']['asi']['increase']={'charisma':2}
        response=await self.http.post(self.url(body),json=request)
        self.assertEqual(response.status_code,200,response.text)
        session=r.game_session
        self.assertEqual((session.character['charisma'],session.character['proficiency_bonus']),(17,2))
        session.commit_location_change('tavern')
        npc=session.create_npc_from_ai({'name':'Synthetic opponent','role':'Guard','location':'tavern'})
        npc.update(current_hp=100,max_hp=100,armor_class=10,hostile=True,distance_ft=30)
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):
            session.start_combat(npc)
        session.world_state['attack_environment']={'pairs':{'player|'+npc['id']:{'distance_ft':30,
            'attacker_sees_target':True,'target_sees_attacker':True,'cover':'none'}}}
        self.manager.save_campaign(body['campaign_id'])
        command={'message':'Fire Bolt','action_id':str(uuid4()),'combat_action':{'steps':[{
            'kind':'magic','ability':'Fire Bolt','target_id':npc['id']}]}}
        with patch('game.roll_d20',return_value=12):
            cast=await self.http.post(f"/api/game/sessions/{body['session_id']}/turn",json=command)
        self.assertEqual(cast.status_code,200,cast.text)
        result=cast.json()['combat_result']['economy_steps'][0]['result']
        self.assertEqual(result['spell_attack_modifier'],5)
        self.assertEqual(result['spell_save_dc'],13)
        self.assertTrue(result['hit'])

    async def test_exact_retry_conflict_and_fresh_manager_keep_single_split_asi(self):
        body,r=await self.earned();request=self.request(body,await self.ready(body))
        request['choices']['asi']['increase']={'constitution':1,'charisma':1}
        accepted=await self.http.post(self.url(body),json=request)
        self.assertEqual(accepted.status_code,200,accepted.text)
        before=r.game_session._capture_runtime_snapshot();revision=self.store.get_campaign(body['campaign_id']).metadata['revision']
        self.assertEqual((await self.http.post(self.url(body),json=request)).json(),accepted.json())
        conflict=copy.deepcopy(request);conflict['choices']['asi']['increase']={'charisma':2}
        response=await self.http.post(self.url(body),json=conflict)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail']['code'],'action_id_conflict')
        self.assertEqual(r.game_session._capture_runtime_snapshot(),before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).metadata['revision'],revision)
        reopened,manager=await self.reopen(body)
        restored=manager.get(reopened['session_id']).game_session
        self.assertEqual(restored.serialize_game_state(),r.game_session.serialize_game_state())
        self.assertEqual(len(restored.character['asi_choices']),1)

    async def test_sqlite_precommit_rollback_retry_and_committed_lost_ack(self):
        from contextlib import contextmanager
        from api.persistence.campaign_models import CampaignStorageError
        body,r=await self.earned();request=self.request(body,await self.ready(body))
        request['choices']['asi']['increase']={'charisma':2}
        before=r.game_session._capture_runtime_snapshot();saved=copy.deepcopy(self.store.get_campaign(body['campaign_id']).payload)
        transaction=self.store._transaction;faults=[]
        @contextmanager
        def fail_after_receipt():
            with transaction() as connection:
                yield connection
                row=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',
                    (body['campaign_id'],request['action_id'])).fetchone()
                if row is not None:
                    faults.append(True);raise sqlite3.OperationalError('synthetic ASI precommit')
        with patch.object(self.store,'_transaction',side_effect=fail_after_receipt):
            response=await self.http.post(self.url(body),json=request)
        self.assertGreaterEqual(response.status_code,500,response.text)
        self.assertEqual(faults,[True]);self.assertEqual(r.game_session._capture_runtime_snapshot(),before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).payload,saved)
        save=self.manager.save_campaign_locked
        def commit_then_fail(*args,**kwargs):
            save(*args,**kwargs);raise CampaignStorageError('synthetic lost ASI acknowledgement')
        with patch.object(self.manager,'save_campaign_locked',side_effect=commit_then_fail):
            response=await self.http.post(self.url(body),json=request)
        self.assertGreaterEqual(response.status_code,500,response.text)
        status=await self.http.get(f"/api/game/sessions/{body['session_id']}/actions/{request['action_id']}")
        self.assertEqual(status.json()['state'],'applied')
        retry=await self.http.post(self.url(body),json=request)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual(r.game_session.character['charisma'],17)
        self.assertEqual(len(r.game_session.character['asi_choices']),1)


    async def test_live_options_expand_without_mutating_old_recorded_preview(self):
        fixture=json.loads(FIXTURE.read_text())
        self.assertEqual(fixture['preview']['supported_asi_choices'],[{'feat':'Ability Score Improvement','increase':{'constitution':2}}])
        body,r=await self.earned();before=r.game_session._capture_runtime_snapshot()
        preview=await self.ready(body)
        self.assertEqual(preview['supported_asi_choices'],[{'feat':'Ability Score Improvement','increase':p} for p in PATTERNS])
        self.assertEqual(r.game_session._capture_runtime_snapshot(),before)

    async def test_stale_and_foreign_owner_reject_without_applying_new_choice(self):
        from api.tests.auth_fixture import PLAYER_B
        body,r=await self.earned();request=self.request(body,await self.ready(body))
        request['choices']['asi']['increase']={'intelligence':1,'wisdom':1}
        before=r.game_session._capture_runtime_snapshot()
        self.app.state.authenticator=FixedAuthenticator(PLAYER_B)
        try:
            response=await self.http.post(self.url(body),json=request)
            self.assertEqual(response.status_code,404,response.text)
        finally:
            self.app.state.authenticator=FixedAuthenticator(TEST_PLAYER)
        self.assertEqual(r.game_session._capture_runtime_snapshot(),before)
        self.manager.save_campaign(body['campaign_id'])
        response=await self.http.post(self.url(body),json=request)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail']['code'],'level_up_preview_stale')
        self.assertEqual(r.game_session._capture_runtime_snapshot(),before)


    async def test_actual_spent_slots_and_points_stay_spent_through_earned_split(self):
        import xp
        body,r=await self.earned(0);session=r.game_session
        session.commit_location_change('tavern')
        npc=session.create_npc_from_ai({'name':'Synthetic opponent','role':'Guard','location':'tavern'})
        npc.update(current_hp=100,max_hp=100,armor_class=10,hostile=True,distance_ft=30)
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):
            session.start_combat(npc)
        session.world_state['attack_environment']={'pairs':{'player|'+npc['id']:{'distance_ft':30,
            'attacker_sees_target':True,'target_sees_attacker':True,'cover':'none'}}}
        self.manager.save_campaign(body['campaign_id'])
        cast={'message':'Quickened','action_id':str(uuid4()),'combat_action':{'steps':[{
            'kind':'magic','ability':'Magic Missile','target_id':npc['id'],'slot_level':1,'metamagic':'quickened_spell'}]}}
        response=await self.http.post(f"/api/game/sessions/{body['session_id']}/turn",json=cast)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(session.world_state['sorcery_points_v1']['remaining'],1)
        self.assertEqual(session.world_state['spellcasting_v1']['slots'],{'1':3,'2':2})
        session.end_combat('synthetic_advancement_boundary')
        xp.apply_xp(session.character,session.world_state,1800,'quest:spent-asi-http')
        self.manager.save_campaign(body['campaign_id'])
        old_rng=session.rng.getstate(); old_hp=session.character['current_hp']
        request=self.request(body,await self.ready(body));request['choices']['asi']['increase']={'constitution':1,'charisma':1}
        response=await self.http.post(self.url(body),json=request)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(session.world_state['sorcery_points_v1']['remaining'],2)
        self.assertEqual(session.world_state['spellcasting_v1']['slots'],{'1':3,'2':3})
        self.assertEqual(session.rng.getstate(),old_rng)
        self.assertEqual(session.character['current_hp'],old_hp)


class NonDexAsiSchemaTests(unittest.TestCase):
    def test_all_fifteen_exact_patterns_retain_wire_shape(self):
        for increase in PATTERNS:
            choice={'feat':'Ability Score Improvement','increase':increase}
            with self.subTest(increase=increase):
                self.assertEqual(LevelUpAsiChoice(**choice).model_dump(mode='json'),choice)

    def test_actual_factory_and_published_union_have_exact_fifteen_strict_shapes(self):
        import yaml
        actual=create_app().openapi()['components']['schemas']
        published=yaml.safe_load((Path(__file__).resolve().parents[3]/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']
        for components in (actual,published):
            variants=components['LevelUpAsiChoice']['properties']['increase']['anyOf']
            shapes=[]
            for variant in variants:
                model=components[variant['$ref'].rsplit('/',1)[1]]
                self.assertFalse(model['additionalProperties'])
                self.assertEqual(set(model['required']),set(model['properties']))
                shape={}
                for ability,field in model['properties'].items():
                    self.assertEqual(field['type'],'integer')
                    self.assertEqual(field['minimum'],field['maximum'])
                    shape[ability]=field['minimum']
                shapes.append(shape)
            self.assertEqual(shapes,PATTERNS)
