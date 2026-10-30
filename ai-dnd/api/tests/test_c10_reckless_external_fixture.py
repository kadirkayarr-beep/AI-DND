"""Natural synthetic external fixture through canonical owners; no weapon/target/RNG overrides."""
import copy
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
import httpx
import weapon_attack
from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.c10_reckless_external_fixture_runtime import _seed_reckless_attack

class ExternalRecklessFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_natural_starting_greataxe_seed_typed_reckless_attack_replay_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=CampaignStore(root/'campaigns.sqlite3',bound_principal=TEST_PLAYER);manager=SessionManager(campaign_store=store)
            try:seed=_seed_reckless_attack(manager,store,root)
            except Exception as error:self.fail(f'Natural fixture must be ready before socket launch: {type(error).__name__}: {error}')
            sid,record,*_=manager.resume_campaign(seed['campaign_id']);session=record.game_session
            self.assertEqual(session.world_state['equipment']['main_hand'],seed['weapon_item_id'])
            self.assertEqual(seed['weapon_id'],'greataxe')
            self.assertEqual(weapon_attack.pair(session,'player',seed['combat_target_id'])['distance_ft'],5)
            self.assertEqual(weapon_attack.reckless_state(session),{'available':True,'active':False,'reason':None})
            target=next(n for n in session.world_state['npcs'] if n['id']==seed['combat_target_id'])
            self.assertEqual((target['max_hp'],target['current_hp'],target['armor_class']),(4,4,10))
            combat=session.world_state['combat'];request={'message':'Saldırı Action kullanıyorum.','interaction_mode':'do','target_id':target['id'],'action_id':str(uuid4()),'combat_id':combat['combat_id'],'combat_round':combat['round'],'combat_turn_index':combat['current_turn_index'],'combat_action':{'steps':[{'kind':'attack','target_id':target['id'],'reckless_attack':True}]}}
            app=create_app(session_manager=manager,ollama_adapter=None,authenticator=FixedAuthenticator(TEST_PLAYER))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                response=await client.post(f'/api/game/sessions/{sid}/turn',json=request);self.assertEqual(response.status_code,200,response.text)
                body=response.json();result=body['combat_result']['economy_steps'][0]['result']
                self.assertEqual(result['weapon_id'],'greataxe');self.assertEqual(result['advantage_sources'],['reckless_attack']);self.assertEqual(len(result['attack_rolls']),2)
                after=copy.deepcopy(session._capture_runtime_snapshot())
                replay=await client.post(f'/api/game/sessions/{sid}/turn',json=request);self.assertEqual(replay.json(),body);self.assertEqual(session._capture_runtime_snapshot(),after)
                self.assertIsNone(app.state.ollama_adapter)
                # Natural outcome may end combat; do not pad NPC HP or reroll to force a window.
                if not session.world_state['combat']['active']:
                    self.assertFalse(any(e.get('kind')=='reckless_attack' for e in session.world_state.get('attack_effects',[])))
                else:self.assertTrue(weapon_attack.reckless_state(session)['active'])
            fresh=SessionManager(campaign_store=CampaignStore(store.path,bound_principal=TEST_PLAYER));_,restored,*_=fresh.resume_campaign(seed['campaign_id'])
            self.assertEqual(restored.game_session.world_state['combat']['active'],session.world_state['combat']['active'])
            self.assertEqual(restored.game_session.world_state.get('attack_effects'),session.world_state.get('attack_effects'))
            self.assertEqual(restored.game_session.rng.getstate(),session.rng.getstate())
            self.assertEqual(_seed_reckless_attack(fresh,fresh._campaign_store,root),seed)
