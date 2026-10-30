"""Synthetic external factory preflight: real owners, SQLite and in-process HTTP; no socket/model."""
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
import httpx
from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.c06_level5_external_fixture_runtime import _seed_selected_level_five

class ExternalLevelFiveFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_seed_canonical_target_apply_five_cast_slot_three_and_fresh_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            store=CampaignStore(root/'campaigns.sqlite3',bound_principal=TEST_PLAYER)
            manager=SessionManager(campaign_store=store)
            try:
                seed=_seed_selected_level_five(manager,store,root)
            except Exception as error:
                self.fail(f'External fixture seed must establish canonical target/player turn before socket launch: {type(error).__name__}: {error}')
            sid,record,*_=manager.resume_campaign(seed['campaign_id'])
            s=record.game_session
            self.assertIn(s.world_state['location'],s.world_state['locations'])
            self.assertEqual(s.world_state['combat']['current_actor_id'],'player')
            enemy=next(n for n in s.world_state['npcs'] if n['id']==seed['combat_target_id'])
            self.assertEqual((enemy['current_hp'],enemy['max_hp']),(4,4))
            self.assertEqual((s.character['level'],s.character['progression_level'],s.character['xp']),(5,4,6500))
            app=create_app(session_manager=manager,ollama_adapter=None,authenticator=FixedAuthenticator(TEST_PLAYER))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                url=f'/api/game/sessions/{sid}/level-up';p=(await client.get(url)).json()
                self.assertEqual((p['status'],p['target_level']),('ready',5))
                response=await client.post(url,json={'action_id':str(uuid4()),'campaign_id':seed['campaign_id'],'expected_revision':p['revision'],'target_level':5,'choices':{'prepared_spells':['Fog Cloud','Silent Image']}})
                self.assertEqual(response.status_code,200,response.text)
                state=response.json()['state'];self.assertEqual(state['spellcasting']['slots'],{'1':4,'2':3,'3':2})
                combat=state['combat'];action_id=str(uuid4())
                request={'action_id':action_id,'message':'Magic Missile kullanıyorum.','interaction_mode':'do','target_id':seed['combat_target_id'],'combat_id':combat['combat_id'],'combat_round':combat['round'],'combat_turn_index':combat['current_turn_index'],'combat_action':{'steps':[{'kind':'magic','ability':'Magic Missile','target_id':seed['combat_target_id'],'slot_level':3}]}}
                response=await client.post(f'/api/game/sessions/{sid}/turn',json=request)
                self.assertEqual(response.status_code,200,response.text)
                result=response.json();steps=result['combat_result']['economy_steps'];self.assertEqual(len(steps),1)
                self.assertEqual(len(steps[0]['result']['darts']),5)
                self.assertEqual(result['state']['spellcasting']['slots'],{'1':4,'2':3,'3':1})
                self.assertEqual(app.state.ollama_adapter,None)
                replay=await client.post(f'/api/game/sessions/{sid}/turn',json=request)
                self.assertEqual(replay.json(),result)
                request['action_id']=str(uuid4())
                refused=await client.post(f'/api/game/sessions/{sid}/turn',json=request)
                self.assertNotEqual(refused.status_code,200,'dead target cannot be forced to accept a new cast')
                self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':4,'2':3,'3':1})
            fresh=SessionManager(campaign_store=CampaignStore(store.path,bound_principal=TEST_PLAYER))
            _,reopened,*_=fresh.resume_campaign(seed['campaign_id'])
            self.assertEqual(reopened.game_session.world_state['spellcasting_v1']['slots'],{'1':4,'2':3,'3':1})
            self.assertEqual(reopened.game_session.character['progression_level'],5)
            self.assertEqual(_seed_selected_level_five(fresh,fresh._campaign_store,root),seed,'restart does not re-award or renew target')
