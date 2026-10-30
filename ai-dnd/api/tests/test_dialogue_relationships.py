import copy,json,unittest,uuid
import relationships
from api.tests import test_dialogue_runtime as base
class RelationshipTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=base.DialogueRuntimeTests.asyncTearDown
 setup_free=base.DialogueRuntimeTests.setup_free
 send=base.DialogueRuntimeTests.send
 async def test_threat_is_experienced_once_and_person_scoped(self):
  await self.setup_free();aid=str(uuid.uuid4());a=await self.send('Seni öldüreceğim.',action_id=aid);b=await self.send('Seni öldüreceğim.',action_id=aid)
  self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json(),b.json());self.assertEqual(relationships.score(self.world,self.npc['id']),-1);self.assertEqual(relationships.score(self.world,'other'),0)
 async def test_claim_of_past_help_does_not_invent_relationship_event(self):
  await self.setup_free();before=relationships.read(self.world);r=await self.send('Dün sana yardım etmiştim, bana borçlusun.');self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(relationships.score(self.world,self.npc['id']),0)
 async def test_negated_threat_does_not_penalize(self):
  await self.setup_free();r=await self.send('Seni öldürmeyeceğim.');self.assertEqual(r.status_code,200,r.text);self.assertEqual(relationships.score(self.world,self.npc['id']),0)
 async def test_actual_threat_creates_bounded_motive_not_phantom_place(self):
  await self.setup_free();await self.send('Seni öldüreceğim.');self.assertEqual(self.npc.get('dialogue_deception',{}).get('remaining_uses'),1)
  await self.send('Planın ne?');context=json.loads(self.reply.batches[-1]['messages'][-1]['content']);self.assertIsNotNone(context['deception']);self.assertEqual(self.npc['dialogue_deception']['remaining_uses'],0)
 async def test_relationship_survives_cold_resume(self):
  await self.setup_free();await self.send('Seni öldüreceğim.');saved=await self.http.post(f'/api/game/campaigns/{self.campaign_id}/save');self.assertEqual(saved.status_code,200,saved.text)
  import httpx
  from api.session_manager import SessionManager
  from api.main import create_app
  from api.auth import FixedAuthenticator
  from api.tests.auth_fixture import TEST_PLAYER
  from api.ollama_adapter import AuthenticatedOllamaAdapter
  fresh_manager=SessionManager(campaign_store=self.store)
  fresh_app=create_app(session_manager=fresh_manager,ollama_adapter=AuthenticatedOllamaAdapter(self.reply),authenticator=FixedAuthenticator(TEST_PLAYER))
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fresh_app),base_url='http://test') as http:
   resumed=await http.post(f'/api/game/campaigns/{self.campaign_id}/resume')
  self.assertEqual(resumed.status_code,200,resumed.text)
  restored=fresh_manager.get(resumed.json()['session_id']).game_session
  self.assertIsNot(restored,self.session);self.assertEqual(relationships.score(restored.world_state,self.npc['id']),-1)
 async def test_failed_autosave_rolls_back_relationship(self):
  await self.setup_free();before=copy.deepcopy(self.session.serialize_game_state())
  from unittest.mock import patch
  from api.persistence.campaign_models import CampaignStorageError
  with patch.object(self.manager,'autosave_turn',side_effect=CampaignStorageError('synthetic')):r=await self.send('Seni öldüreceğim.')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_actual_gift_and_disagreement_are_distinct(self):
  await self.setup_free();import dialogue_runtime
  item={'item_id':'gift:test','name':'Ekmek','quantity':1};self.world['inventory'].append(item);before=copy.deepcopy(self.world)
  self.world['inventory'].remove(item);self.npc['inventory']=[item]
  dialogue_runtime.observe_turn(self.session,before,self.session.character['current_hp'],{'action_result':{'action':'item_transfer'},'model_calls':0},'Ekmeği veriyorum','gift1')
  self.assertEqual(relationships.score(self.world,self.npc['id']),1)
  await self.send('Bu konuda sana katılmıyorum.');self.assertEqual(relationships.score(self.world,self.npc['id']),1)
  self.assertTrue(any(e.startswith('disagreed:') for e in relationships.read(self.world)[self.npc['id']]['events']))
