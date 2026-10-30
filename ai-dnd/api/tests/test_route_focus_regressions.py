"""Task-only schema-aware HTTP diagnostics; no product assertions replaced."""
import copy,json,uuid,unittest,sys
from pathlib import Path
from unittest.mock import patch
from api.tests import test_campaign_api as api
from api.tests.test_local_person_persistence import LocalPersonModel
import local_dialogue


class SchemaClient:
 def __init__(self,npc):
  self.npc=npc; self.mode='talk'; self.calls=[]; self.message=''; self.old=api.CapturingConversationContextClient();self.local=LocalPersonModel()
 def list(self):return {'models':[{'model':'qwen3:8b'}]}
 def chat(self,*a,**k):
  props=k.get('format',{}).get('properties',{})
  if 'spoken_text' in props:
   text='Seninle konuşmak güzel.' if self.mode!='weather' else 'Bence bugün hava güzel.'
   reply={'message':{'content':json.dumps({'spoken_text':text,'stage_direction':''},ensure_ascii=False)}}
  elif self.mode=='search':reply=self.local.chat(*a,**k)
  else:
   meaning='personal_purpose' if self.mode=='purpose' else 'other'
   self.old.conversation_replies=[{'conversation':{'addressee_id':self.npc['id'],'subject_phrase':'' if self.message=='Peki neden?' else 'Marek','subject_role':'addressee','meaning':meaning,'topic_relation':('followup' if self.message=='Peki neden?' else 'new') if self.mode=='purpose' else 'topic_change','candidate_evidence_ids':[f"npc-profile:{self.npc['id']}:v1:reason_for_being_here"] if self.mode=='purpose' else []},'narration':'Bence bugün hava güzel.' if self.mode=='weather' else 'Seninle konuşmak güzel.'}]
   reply=self.old.chat(*a,**k)
  self.calls.append({'properties':sorted(props),'request_message':self.message,'response':json.loads(reply['message']['content'])})
  return reply

class RouteFocusRegressionTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=api.CampaignApiTests.asyncSetUp
 asyncTearDown=api.CampaignApiTests.asyncTearDown
 async def prepare(self):
  city,sid,s,url,venue,door=await api.create_city_with_locked_tavern(self)
  npc={'id':'npc_diag_marek','name':'Marek','role':'resident','location':city,'reality_layer':'PROCEDURAL_LOCAL_FICTION','personal_profile':{'schema_version':local_dialogue.PERSONAL_PROFILE_SCHEMA_VERSION,'occupation':'Arşivde kâtiplik yapıyorum.','current_activity':'Eski kayıtları tasnif ediyorum.','origin':'Kuzeydeki küçük bir yerleşimden geldim.','reason_for_being_here':'Kayıp kayıtları bulmaya geldim.'},'knowledge':[],'memory':[],'status':'active','combat_status':'active','current_hp':12,'relationship':'neutral','appearance':'','personality':''}
  s.world_state.setdefault('npcs',[]).append(npc);s._experimental_npc_dialogue_enabled=False
  self.session=s;self.url=url;self.npc=npc;self.client=SchemaClient(npc);self.rows=[]
 def snap(self):
  w=self.session.world_state
  return copy.deepcopy({'location':w.get('location'),'inventory':w.get('inventory'),'character':self.session.character,'scene_state':w.get('scene_state'),'conversation_focus':w.get('interaction_adventure_v1',{}).get('conversation_focus'),'npcs':[{'id':n.get('id'),'name':n.get('name'),'role':n.get('role')} for n in w.get('npcs',[])],'rng':repr(self.session.rng.getstate())})
 async def send(self,text,mode='do',kind='talk',target=None):
  self.client.mode=kind;self.client.message=text;before=self.snap();n=len(self.client.calls)
  body={'message':text,'action_id':str(uuid.uuid4()),'interaction_mode':mode}
  if mode is None:body.pop('interaction_mode')
  if target:body['target_id']=target
  with patch.object(self.app.state.ollama_adapter,'_client',self.client):r=await self.http.post(self.url,json=body)
  self.rows.append({'request':body,'http':r.status_code,'response':r.json(),'before':before,'after':self.snap(),'chat_calls':len(self.client.calls)-n,'calls':self.client.calls[n:],'safety':copy.deepcopy(self.session.last_narration_safety)})
  print('HTTP_ROUTE_RECEIPT',json.dumps(self.rows[-1],ensure_ascii=False,default=str))
  return r,body

 async def ok(self,*a,**k):
  r,b=await self.send(*a,**k);self.assertEqual(r.status_code,200,r.text);return r,b
 def unchanged(self,row):
  self.assertEqual(row['before']['location'],row['after']['location']);self.assertEqual(row['before']['inventory'],row['after']['inventory']);self.assertEqual(row['before']['rng'],row['after']['rng'])
 async def replay_cold(self,body,original):
  from api.tests.auth_fixture import TEST_PLAYER
  from api.session_manager import SessionManager
  from api.main import create_app
  from api.auth import FixedAuthenticator
  from api.ollama_adapter import AuthenticatedOllamaAdapter
  import httpx,game
  sid=self.url.split('/')[-2];cid=self.manager.get(sid).campaign_id
  before=copy.deepcopy(self.session.serialize_game_state());calls=len(self.client.calls)
  save=await self.http.post(f'/api/game/campaigns/{cid}/save');self.assertEqual(save.status_code,200,save.text)
  manager=SessionManager(campaign_store=self.store);app=create_app(session_manager=manager,ollama_adapter=AuthenticatedOllamaAdapter(self.client),authenticator=FixedAuthenticator(TEST_PLAYER))
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as http:
   resumed=await http.post(f'/api/game/campaigns/{cid}/resume');self.assertEqual(resumed.status_code,200,resumed.text)
   fresh=manager.get(resumed.json()['session_id']).game_session
   self.assertEqual(fresh.world_state['npcs'],self.session.world_state['npcs'])
   self.assertEqual(fresh.world_state.get('interaction_adventure_v1'),self.session.world_state.get('interaction_adventure_v1'))
   frozen=copy.deepcopy(fresh.serialize_game_state());rng=fresh.rng.getstate()
   with patch.object(game,'run_player_turn',side_effect=AssertionError('Replay cannot execute')):
    replay=await http.post(f"/api/game/sessions/{resumed.json()['session_id']}/turn",json=body)
   self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json(),{**original.json(),'session_id':resumed.json()['session_id']})
   self.assertEqual(fresh.serialize_game_state(),frozen);self.assertEqual(fresh.rng.getstate(),rng)
  self.assertEqual(len(self.client.calls),calls);self.assertEqual(self.session.serialize_game_state(),before)
 async def test_search_active_npc_reuse_cold_replay(self):
  await self.prepare();await self.ok('Marek ile konuşmak istiyorum.',target=self.npc['id'])
  text='Sahnede olmayan bir balıkçıyı bulup liman söylentilerini sormak istiyorum.'
  r,b=await self.ok(text,mode='say',kind='search');self.assertEqual(r.json()['turn_outcome']['status'],'created_local_person');self.assertEqual(len(self.session.world_state['npcs']),2);self.assertEqual(self.rows[-1]['chat_calls'],1);self.unchanged(self.rows[-1])
  r,b=await self.ok(text,mode='say',kind='search');self.assertEqual(r.json()['turn_outcome']['status'],'reused_local_person');self.assertEqual(len(self.session.world_state['npcs']),2);self.assertEqual(self.rows[-1]['chat_calls'],1)
  await self.replay_cold(b,r)
 async def test_empty_search_save_failure_retry_one_person(self):
  from api.persistence.campaign_models import CampaignStorageError
  await self.prepare();self.session.world_state['npcs']=[]
  text='Sahilde bir balıkçı bulup liman söylentilerini onunla konuşmak istiyorum.'
  before=copy.deepcopy(self.session.serialize_game_state())
  with patch.object(self.store,'save_campaign',side_effect=CampaignStorageError('synthetic failure')):r,b=await self.send(text,mode='say',kind='search')
  self.assertEqual(r.status_code,503);self.assertEqual(self.session.serialize_game_state(),before)
  with patch.object(self.app.state.ollama_adapter,'_client',self.client):r=await self.http.post(self.url,json=b)
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(self.session.world_state['npcs']),1)
  r,b=await self.ok(text,mode='say',kind='search');self.assertEqual(r.json()['turn_outcome']['status'],'reused_local_person');self.assertEqual(len(self.session.world_state['npcs']),1);await self.replay_cold(b,r)
 async def test_rejected_search_proposal_preserves_people_and_replay(self):
  await self.prepare();self.npc.update(name='Neris',reality_layer='CANON');await self.ok('Neris ile konuşmak istiyorum.',target=self.npc['id'])
  before=copy.deepcopy(self.session.world_state['npcs']);r,b=await self.ok('Sahilde bir balıkçı bulup liman söylentilerini onunla konuşmak istiyorum.',mode='say',kind='search')
  self.assertEqual(r.json()['turn_outcome']['status'],'proposal_rejected');self.assertEqual(self.session.world_state['npcs'],before);calls=len(self.client.calls)
  with patch.object(self.app.state.ollama_adapter,'_client',self.client):rr=await self.http.post(self.url,json=b)
  self.assertEqual(rr.json(),r.json());self.assertEqual(len(self.client.calls),calls)
 async def test_ordinary_preference_stays_single_structured_call(self):
  await self.prepare();await self.ok('Marek ile konuşmak istiyorum.',target=self.npc['id'])
  r,b=await self.ok('İnsanlarla sohbet etmeyi mi seversin, tek başına kalmayı mı?',mode='say')
  self.assertEqual(self.rows[-1]['chat_calls'],1);self.assertIn('spoken_text',self.client.calls[-1]['properties']);self.assertIn('Seninle konuşmak güzel.',r.json()['narration'])
 async def purpose(self):
  await self.prepare();r,b=await self.ok('Marek, seni bu şehre getiren şeyi anlat',kind='purpose',target=self.npc['id']);self.assertIn('Kayıp kayıtları',r.json()['narration']);self.assertIsNotNone(self.snap()['conversation_focus'])
 async def test_topic_change_clears_focus_cold_replay(self):
  await self.purpose();r,b=await self.ok('Marek, bugün hava nasıl',kind='weather',target=self.npc['id']);self.assertIn('Bence bugün hava güzel.',r.json()['narration']);self.assertEqual(self.rows[-1]['chat_calls'],1);self.assertIsNone(self.snap()['conversation_focus']);self.unchanged(self.rows[-1]);await self.replay_cold(b,r)
  r,b=await self.ok('Peki neden?',kind='weather');self.assertIn('Bence bugün hava güzel.',r.json()['narration']);self.assertIsNone(self.snap()['conversation_focus'])
 async def test_factual_followup_preserves_focus(self):
  await self.purpose();old=copy.deepcopy(self.snap()['conversation_focus']);r,b=await self.ok('Peki neden?',kind='purpose');self.assertIn('Kayıp kayıtları',r.json()['narration']);self.assertEqual(self.snap()['conversation_focus']['predicate'],old['predicate'])
 async def test_end_clears_focus_reopen(self):
  await self.purpose();r,b=await self.ok('Konuşmayı bitiriyorum.');self.assertFalse(r.json()['state']['conversation']['active']);self.assertEqual(self.rows[-1]['chat_calls'],0);self.assertIsNone(self.snap()['conversation_focus']);await self.replay_cold(b,r)
  r,b=await self.ok('Marek ile konuşmak istiyorum.',target=self.npc['id']);self.assertTrue(r.json()['state']['conversation']['active']);self.assertIsNone(self.snap()['conversation_focus'])
 async def test_rejected_wrong_speaker_and_save_failure_preserve_focus(self):
  from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
  from api.persistence.campaign_models import CampaignStorageError
  await self.purpose();before=copy.deepcopy(self.session.serialize_game_state());focus=copy.deepcopy(self.snap()['conversation_focus'])
  bad=ScriptedNpcSpeechClient('Benim adım Sera.')
  with patch.object(self.app.state.ollama_adapter,'_client',bad):r=await self.http.post(self.url,json={'message':'Bugün keyfin nasıl?','target_id':self.npc['id'],'interaction_mode':'say','action_id':str(uuid.uuid4())})
  self.assertEqual(r.status_code,200);self.assertNotIn('Benim adım Sera.',r.json()['narration']);self.assertEqual(self.snap()['conversation_focus'],focus)
  before=copy.deepcopy(self.session.serialize_game_state())
  with patch.object(self.store,'save_campaign',side_effect=CampaignStorageError('synthetic failure')):r,b=await self.send('Marek, bugün hava nasıl',kind='weather',target=self.npc['id'])
  self.assertEqual(r.status_code,503);self.assertEqual(self.session.serialize_game_state(),before)
 async def test_other_npc_accepted_topic_clears_old_focus(self):
  await self.purpose();other=copy.deepcopy(self.npc);other.update(id='npc_diag_other',name='Lysa');self.session.world_state['npcs'].append(other)
  r,b=await self.ok('Lysa, bugün hava nasıl',kind='weather',target=other['id']);self.assertIn('Lysa',r.json()['narration']);self.assertEqual(r.json()['state']['conversation']['interlocutor']['id'],other['id']);self.assertIsNone(self.snap()['conversation_focus'])

 async def test_search_mode_matrix(self):
  for mode in (None,'do','say'):
   with self.subTest(mode=mode):
    await self.prepare();await self.ok('Marek ile konuşmak istiyorum.',target=self.npc['id'])
    r,b=await self.ok('Sahnede olmayan bir balıkçıyı bulup liman söylentilerini sormak istiyorum.',mode=mode,kind='search')
    self.assertEqual(r.json()['turn_outcome']['status'],'created_local_person');self.assertEqual(len(self.session.world_state['npcs']),2);self.assertEqual(self.rows[-1]['chat_calls'],1);self.unchanged(self.rows[-1])
