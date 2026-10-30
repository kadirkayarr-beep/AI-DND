"""Same creation endpoint and persisted campaign owner, selected starts4/5."""
import copy
import unittest
import httpx
from api.tests import test_campaign_api as campaigns
from api.tests.test_roadmap_c06_creation_http import character_request
from api.tests.test_roadmap_c06_creation45 import steps
from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
from api.main import create_app
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.dnd_2024_rules import get_character_creation_catalog


def request(level):
    value = character_request(level)
    value['level_choices'] = steps(level)
    return value


class CreationFourFiveHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown

    async def test_real_http_creation_stored_and_fresh_resumed(self):
        for level,hp,xp,version in ((4,30,2700,4),(5,37,6500,6)):
            response = await self.http.post('/api/game/campaigns', json={'character':request(level)})
            self.assertEqual(response.status_code,200,response.text)
            body=response.json(); saved=self.store.get_campaign(body['campaign_id']).payload['engine_save']
            self.assertEqual((saved['version'],saved['player']['xp'],saved['player']['current_hp'],saved['player']['max_hp']),(version,xp,hp,hp))
            self.assertEqual(saved['world_state'].get('xp_awarded_event_ids',[]),[])
            manager=SessionManager(campaign_store=CampaignStore(self.store.path,bound_principal=TEST_PLAYER))
            app=create_app(session_manager=manager,authenticator=FixedAuthenticator(TEST_PLAYER))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                resumed=await client.post(f"/api/game/campaigns/{body['campaign_id']}/resume")
            self.assertEqual(resumed.status_code,200,resumed.text)
            s=manager.get(resumed.json()['session_id']).game_session
            self.assertEqual((s.character['level'],s.character['progression_level'],s.character['current_hp'],s.character['max_hp']),(level,level,hp,hp))

    async def test_catalog_exposes_fixed_selected_step_four_five_shapes(self):
        meta=get_character_creation_catalog()['sorcerer_starting_creation']
        self.assertEqual(meta['supported_starting_levels'],[1,2,3,4,5])
        self.assertEqual(meta['level_4']['prepared_spell_count'],1)
        self.assertEqual(meta['level_4']['cantrip_count'],1)
        from api.tests.test_roadmap_c06_nondex_asi_http import PATTERNS
        self.assertEqual(meta['level_4']['supported_asi_choices'],[{'feat':'Ability Score Improvement','increase':p} for p in PATTERNS])
        self.assertIn('Shocking Grasp',meta['level_4']['cantrip_ids'])
        self.assertEqual(meta['level_5']['prepared_spell_count'],2)
        self.assertIn('Fog Cloud',meta['level_5']['prepared_spell_ids'])
        self.assertIn('Silent Image',meta['level_5']['prepared_spell_ids'])
        self.assertEqual(set(meta['effects_pending_by_level']),{'1','2','3','4','5'})

    async def test_actual_factory_and_published_creation_schema_fields_match(self):
        import yaml
        from pathlib import Path
        runtime=self.app.openapi()['components']['schemas']
        published=yaml.safe_load((Path(__file__).resolve().parents[3]/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']
        def normalized(value):
            if isinstance(value,dict):return {k:normalized(v) for k,v in value.items() if k not in ('title','description')}
            if isinstance(value,list):return [normalized(v) for v in value]
            return value
        for name in runtime:
            if name=='CharacterCreateInput' or name.startswith('Sorcerer'):
                self.assertIn(name,published)
                if name=='CharacterCreateInput':
                    for field in ('starting_level','level_choices'):
                        self.assertEqual(normalized(runtime[name]['properties'][field]),normalized(published[name]['properties'][field]),field)
                else:
                    self.assertEqual(normalized(runtime[name]),normalized(published[name]),name)

    async def test_new_start_invalid_shape_origin_and_choices_never_publish(self):
        from api.tests import test_roadmap_c06_creation_http as prior
        rows=lambda:prior.CreationHttpTests.rows(self)
        cases=[]
        for level in (4,5):
            for mode in ('missing-step','null-step','extra-step','unsupported-asi','duplicate-spell','other-class','bad-origin','wrong-level-type'):
                value=request(level)
                if mode=='missing-step':value['level_choices'].pop('4')
                if mode=='null-step':value['level_choices']['4']=None
                if mode=='extra-step':value['level_choices']['6']={}
                if mode=='unsupported-asi':value['level_choices']['4']['asi']['increase']={'dexterity':2}
                if mode=='duplicate-spell':value['level_choices']['4']['prepared_spells']=['Magic Missile']
                if mode=='other-class':value['class']='Barbarian'
                if mode=='bad-origin':value['ability_scores']['constitution']=99
                if mode=='wrong-level-type':value['starting_level']=float(level)
                cases.append(value)
        before_rows=rows();before_sessions=dict(self.manager._sessions)
        for value in cases:
            response=await self.http.post('/api/game/campaigns',json={'character':value})
            self.assertEqual(response.status_code,422,response.text)
            self.assertEqual(rows(),before_rows)
            self.assertEqual(self.manager._sessions,before_sessions)

    async def test_real_insert_then_failure_never_publishes_new_start_four_or_five(self):
        import sqlite3,json
        from contextlib import contextmanager
        from unittest.mock import patch
        from api.tests import test_roadmap_c06_creation_http as prior
        rows=lambda:prior.CreationHttpTests.rows(self)
        real_transaction=self.store._transaction
        for level,hp in ((4,30),(5,37)):
            before_rows=rows();before_sessions=dict(self.manager._sessions); before_campaigns=dict(self.manager._campaign_sessions)
            inserted=[]
            @contextmanager
            def fail_after_real_insert():
                with real_transaction() as connection:
                    yield connection
                    payloads=connection.execute('SELECT payload_json FROM campaigns').fetchall()
                    self.assertEqual(len(payloads),len(before_rows)+1)
                    payload=json.loads(payloads[-1][0]);player=payload['engine_save']['player']
                    self.assertEqual((player['level'],player['current_hp'],player['max_hp']),(level,hp,hp))
                    inserted.append(level)
                    raise sqlite3.OperationalError('synthetic fault after real creation INSERT')
            with patch.object(self.store,'_transaction',side_effect=fail_after_real_insert):
                response=await self.http.post('/api/game/campaigns',json={'character':request(level)})
            self.assertEqual(response.status_code,503,response.text)
            self.assertEqual(inserted,[level]);self.assertEqual(rows(),before_rows)
            self.assertEqual(self.manager._sessions,before_sessions)
            self.assertEqual(self.manager._campaign_sessions,before_campaigns)
