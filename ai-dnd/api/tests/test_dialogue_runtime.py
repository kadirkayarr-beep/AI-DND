"""Free dialogue contract; assertions target engine behavior, not stub internals."""
import copy,importlib.util,json,unittest,uuid
from unittest.mock import patch
from api.tests import test_intent_response_consistency as base_fixture

class FreeReplyClient:
 def __init__(self,spoken='Kapıyı akşam güvenlik için kilitli tutuyoruz.',stage=''):
  self.spoken=spoken;self.stage=stage;self.calls=0;self.batches=[];self.raw=None
 def list(self):return {'models':[{'model':'qwen3:8b'}]}
 def chat(self,**kwargs):
  self.calls+=1;self.batches.append(kwargs)
  return {'message':{'content':self.raw if self.raw is not None else json.dumps({'spoken_text':self.spoken,'stage_direction':self.stage,'place_proposals':[],'job_proposals':[]},ensure_ascii=False)}}

class DialogueRuntimeTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base_fixture.IntentResponseConsistencyTests.asyncSetUp
 asyncTearDown=base_fixture.IntentResponseConsistencyTests.asyncTearDown
 async def setup_free(self):
  self.world['dialogue_runtime_v1']={'mode':'free_v1','version':1}
  self.npc={'id':'npc_free_edric','name':'Edric','role':'bartender','personality':'Kısa konuşan, temkinli ama yardımsever.','location':self.world['location'],'reality_layer':'PROCEDURAL_LOCAL_FICTION','name_known':True,'role_known':True}
  self.world['npcs']=[self.npc]
  self.world['flags'].update(active_npc_id=self.npc['id'],last_npc_id=self.npc['id'],active_npc_until_turn=100)
  self.reply=FreeReplyClient()
 async def send(self,text,mode='say',action_id=None):
  with patch.object(self.app.state.ollama_adapter,'_client',self.reply):
   return await self.http.post(f'/api/game/sessions/{self.session_id}/turn',json={'message':text,'interaction_mode':mode,'action_id':action_id or str(uuid.uuid4())})
 async def test_free_coordinator_exists(self):
  self.assertIsNotNone(importlib.util.find_spec('dialogue_runtime'))
 async def test_door_cause_question_reaches_npc_without_world_action(self):
  await self.setup_free();before=copy.deepcopy((self.world['location'],self.world['inventory'],self.world['doors']))
  r=await self.send('kapı niye kilitliydi?',mode='do')
  self.assertEqual(r.status_code,200,r.text);self.assertIn(self.reply.spoken,r.json()['narration'])
  self.assertEqual(before,(self.world['location'],self.world['inventory'],self.world['doors']))
 async def test_name_answer_is_not_compulsory_occupation_paragraph(self):
  await self.setup_free();self.reply.spoken='Edric. Sana nasıl yardımcı olayım?'
  r=await self.send('ismin nedir',mode='do')
  self.assertEqual(r.status_code,200,r.text);self.assertIn(self.reply.spoken,r.json()['narration'])
  self.assertNotIn('Barmen olarak buradayım',r.json()['narration']);self.assertEqual(self.reply.calls,1)
 async def test_short_relevant_speech_is_not_repaired(self):
  await self.setup_free();self.reply.spoken='Doğrusunu istersen bugün biraz yorgunum.'
  r=await self.send('Günün nasıl geçti?');self.assertEqual(r.status_code,200,r.text)
  self.assertIn(self.reply.spoken,r.json()['narration']);self.assertEqual(self.reply.calls,1)
 async def test_say_mode_cannot_mutate_inventory(self):
  await self.setup_free();self.reply.spoken='Sana on altın verdiğimi söylüyorum.'
  before=copy.deepcopy(self.world['inventory']);r=await self.send('Bana para verdiğini söyle.')
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(before,self.world['inventory'])
 async def test_malformed_reply_is_explicit_technical_error_and_rolls_back(self):
  await self.setup_free();self.reply.raw='not json';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('Nasılsın?');self.assertEqual(r.status_code,503,r.text)
  self.assertEqual(r.json()['detail']['code'],'invalid_dialogue_response')
  self.assertEqual(before,self.session.serialize_game_state());self.assertEqual(self.reply.calls,1)
 async def test_private_other_npc_data_absent_from_prompt(self):
  await self.setup_free();self.world['npcs'].append({'id':'private_other','name':'SecretOther','location':'elsewhere','secret':'NEVER_INCLUDE_MARKER'})
  r=await self.send('Nasılsın?');self.assertEqual(r.status_code,200,r.text)
  prompt=json.dumps(self.reply.batches,ensure_ascii=False)
  self.assertNotIn('NEVER_INCLUDE_MARKER',prompt)
 async def test_same_action_id_replays_without_second_model_call(self):
  await self.setup_free();aid=str(uuid.uuid4());a=await self.send('Nasılsın?',action_id=aid);b=await self.send('Nasılsın?',action_id=aid)
  self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json(),b.json());self.assertEqual(self.reply.calls,1)
 async def test_mode_is_not_enabled_by_player_message(self):
  await self.setup_free();self.world.pop('dialogue_runtime_v1')
  self.assertIsNotNone(importlib.util.find_spec('dialogue_runtime'))
  import dialogue_runtime
  self.assertFalse(dialogue_runtime.is_enabled(self.world))
 async def test_model_supplied_authority_field_is_rejected(self):
  await self.setup_free();self.reply.raw=json.dumps({'spoken_text':'Buyur.','stage_direction':'','place_proposals':[],'job_proposals':[],'world_updates':{'gold':999}})
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('Merhaba.')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_repeated_valid_prose_is_not_replaced(self):
  await self.setup_free();self.reply.spoken='Benim bildiğim de bu.'
  for _ in range(2):
   r=await self.send('Emin misin?');self.assertEqual(r.status_code,200,r.text);self.assertIn(self.reply.spoken,r.json()['narration'])
  self.assertEqual(self.reply.calls,2)
 async def test_new_mode_is_persisted_only_for_new_campaign(self):
  import os
  import dialogue_runtime
  self.assertFalse(dialogue_runtime.is_enabled(self.world))
  with patch.dict(os.environ,{'AI_DND_DIALOGUE_MODE':'free_v1'}):
   r=await self.http.post('/api/game/campaigns',json={})
  self.assertEqual(r.status_code,200,r.text)
  new=self.manager.get(r.json()['session_id']).game_session
  self.assertTrue(dialogue_runtime.is_enabled(new.world_state));self.assertFalse(dialogue_runtime.is_enabled(self.world))
 async def test_save_and_resume_retains_free_dialogue_and_exchange(self):
  await self.setup_free();r=await self.send('Nasılsın?');self.assertEqual(r.status_code,200,r.text)
  saved=await self.http.post(f'/api/game/campaigns/{self.campaign_id}/save');self.assertEqual(saved.status_code,200,saved.text)
  import httpx
  from api.session_manager import SessionManager
  from api.main import create_app
  from api.auth import FixedAuthenticator
  from api.tests.auth_fixture import TEST_PLAYER
  from api.ollama_adapter import AuthenticatedOllamaAdapter
  fresh_manager=SessionManager(campaign_store=self.store)
  fresh_app=create_app(session_manager=fresh_manager,ollama_adapter=AuthenticatedOllamaAdapter(self.reply),authenticator=FixedAuthenticator(TEST_PLAYER))
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fresh_app),base_url='http://test') as fresh_http:
   resumed=await fresh_http.post(f'/api/game/campaigns/{self.campaign_id}/resume')
  self.assertEqual(resumed.status_code,200,resumed.text)
  fresh=fresh_manager.get(resumed.json()['session_id']).game_session
  self.assertIsNot(fresh,self.session)
  import dialogue_runtime
  self.assertTrue(dialogue_runtime.is_enabled(fresh.world_state))
  fresh_npc=next(n for n in fresh.world_state['npcs'] if n['id']==self.npc['id'])
  self.assertEqual(fresh_npc['dialogue_persona'],self.npc['dialogue_persona'])
  self.assertEqual(fresh.world_state['npc_speech_log'][self.npc['id']][-1]['npc'],self.reply.spoken)
 async def test_empty_reply_is_not_a_fake_npc_refusal(self):
  await self.setup_free();self.reply.spoken='';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('Nasılsın?');self.assertEqual(r.status_code,503,r.text)
  self.assertEqual(r.json()['detail']['code'],'invalid_dialogue_response');self.assertEqual(before,self.session.serialize_game_state())
 async def test_provider_timeout_is_technical_unavailable_and_rolls_back(self):
  await self.setup_free();before=copy.deepcopy(self.session.serialize_game_state())
  with patch.object(self.reply,'chat',side_effect=TimeoutError('synthetic provider timeout')):
   r=await self.send('Nasılsın?')
  self.assertEqual(r.status_code,503,r.text)
  self.assertEqual(r.json()['detail']['code'],'ollama_unavailable')
  self.assertEqual(before,self.session.serialize_game_state())
 async def test_question_about_npc_hiding_does_not_roll_player_stealth(self):
  await self.setup_free();self.reply.spoken='Gizlenmiyorum; sadece biraz yalnız kalmak istedim.'
  for text in ('Neden gizleniyorsun?','Neden saklanıyorsun?','Neden etrafa bakıyorsun?','“Gizleniyorum” dedim.'):
   with self.subTest(text=text):
    rng=self.session.rng.getstate();r=await self.send(text,mode='do');self.assertEqual(r.status_code,200,r.text);self.assertIn(self.reply.spoken,r.json()['narration']);self.assertEqual(rng,self.session.rng.getstate())
