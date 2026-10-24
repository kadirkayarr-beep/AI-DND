import copy,json,uuid,unittest
from unittest.mock import patch
import game,interaction_adventure,exploration
from api.tests.test_route_focus_regressions import RouteFocusRegressionTests
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient

class PublicDoorFocusTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=RouteFocusRegressionTests.asyncSetUp
 asyncTearDown=RouteFocusRegressionTests.asyncTearDown
 prepare=RouteFocusRegressionTests.prepare
 snap=RouteFocusRegressionTests.snap
 replay_cold=RouteFocusRegressionTests.replay_cold
 async def setup_focus(self):
  await self.prepare()
  from api.tests.test_campaign_api import CapturingConversationContextClient
  self.client=CapturingConversationContextClient()
  with patch.object(self.app.state.ollama_adapter,'_client',self.client):
   greeting=await self.http.post(self.url,json={'message':'Marek ile konuşmak istiyorum.','action_id':str(uuid.uuid4())})
  self.assertEqual(greeting.status_code,200,greeting.text)
  body={'message':'Buralarda han var mı Marek?','action_id':str(uuid.uuid4())}
  with patch.object(self.app.state.ollama_adapter,'_client',self.client):r=await self.http.post(self.url,json=body)
  self.assertEqual(r.status_code,200,r.text)
  self.focus=copy.deepcopy(interaction_adventure.current_conversation_focus(self.session.world_state,self.npc))
  self.assertIsNotNone(self.focus);self.assertEqual(self.focus['predicate'],'locked')
 def context(self,world=None,npc=None):
  token=game._ACTIVE_SESSION.set(self.session)
  try:return game._experimental_npc_dialogue_context(world or self.session.world_state,npc or self.npc)
  finally:game._ACTIVE_SESSION.reset(token)
 async def test_public_projection_no_raw_value(self):
  await self.setup_focus();before=copy.deepcopy(self.session.serialize_game_state())
  focus=self.context().get('conversation_focus');self.assertIsInstance(focus,dict)
  self.assertEqual(focus['subject_id'],self.focus['subject_id']);self.assertEqual(focus['speaker_id'],self.npc['id']);self.assertNotIn('value',focus)
  self.assertEqual(self.session.serialize_game_state(),before)
 async def test_invalid_or_private_focus_not_projected(self):
  await self.setup_focus();base=copy.deepcopy(self.session.world_state);did=self.focus['subject_id'];lid=did.partition(':')[2]
  for case in ('unlocked','removed','other_scene','door_hidden','door_undiscovered','place_hidden','place_undiscovered','scene_hidden','speaker_hidden','speaker_undiscovered','other_npc','expired','bad_evidence','unknown_destination'):
   with self.subTest(case=case):
    w=copy.deepcopy(base);n=next(n for n in w['npcs'] if n['id']==self.npc['id']);d=next(d for d in w['doors'] if d['id']==did)
    if case=='unlocked':d['locked']=False
    elif case=='removed':w['doors'].remove(d)
    elif case=='other_scene':d['location']='different-scene'
    elif case=='door_hidden':d['hidden']=True
    elif case=='door_undiscovered':d['discovered']=False
    elif case=='place_hidden':w['locations'][lid]['hidden']=True
    elif case=='place_undiscovered':w['locations'][lid]['discovered']=False
    elif case=='scene_hidden':w['locations'][w['location']]['hidden']=True
    elif case=='speaker_hidden':n['hidden']=True
    elif case=='speaker_undiscovered':n['discovered']=False
    elif case=='other_npc':n={**n,'id':'another-npc'}
    elif case=='expired':w['flags']['active_npc_until_turn']=-1
    elif case=='bad_evidence':w[interaction_adventure.KEY]['conversation_focus']['evidence_id']='unrelated'
    elif case=='unknown_destination':w['locations'].pop(lid)
    before=copy.deepcopy(w);self.assertIsNone(self.context(w,n).get('conversation_focus'));self.assertEqual(w,before)
  with patch.object(exploration,'known_locations',return_value={base['location']}):self.assertIsNone(self.context(base).get('conversation_focus'))
 async def test_http_followup_topic_end_rollback_cold_replay(self):
  from api.persistence.campaign_models import CampaignStorageError
  await self.setup_focus();contexts=[];original=game._experimental_npc_dialogue_context
  def capture(*a,**k):
   result=original(*a,**k);contexts.append(copy.deepcopy(result));return result
  self.client=ScriptedNpcSpeechClient('Bunun nedenini bilmiyorum.')
  body={'message':'Niye?','interaction_mode':'say','action_id':str(uuid.uuid4())}
  before=copy.deepcopy(self.session.serialize_game_state());protected=self.snap()
  with patch.object(game,'_experimental_npc_dialogue_context',side_effect=capture),patch.object(self.app.state.ollama_adapter,'_client',self.client),patch.object(self.manager,'autosave_turn',side_effect=CampaignStorageError('synthetic failure')):r=await self.http.post(self.url,json=body)
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(self.session.serialize_game_state(),before)
  with patch.object(game,'_experimental_npc_dialogue_context',side_effect=capture),patch.object(self.app.state.ollama_adapter,'_client',self.client):r=await self.http.post(self.url,json=body)
  self.assertEqual(r.status_code,200,r.text);self.assertIn('Bunun nedenini bilmiyorum.',r.json()['narration']);self.assertEqual(self.client.chat_calls,2)
  self.assertEqual(contexts[-1]['conversation_focus']['subject_id'],self.focus['subject_id']);self.assertNotIn('value',contexts[-1]['conversation_focus'])
  prompt='\n'.join(m['content'] for m in self.client.message_batches[-1])
  self.assertIn('"conversation_focus"',prompt);self.assertIn(self.focus['subject_id'],prompt)
  self.assertEqual(interaction_adventure.current_conversation_focus(self.session.world_state,self.npc),self.focus)
  for key in ('location','inventory','rng'):self.assertEqual(self.snap()[key],protected[key])
  self.client.calls=[None]*self.client.chat_calls;await self.replay_cold(body,r);self.assertEqual(self.client.chat_calls,2)
 async def test_accepted_topic_and_end_retire_door_focus(self):
  await self.setup_focus()
  body={'message':'Marek, bugün hava nasıl','interaction_mode':'say','action_id':str(uuid.uuid4())}
  weather=ScriptedNpcSpeechClient('Bence bugün hava güzel.')
  with patch.object(self.app.state.ollama_adapter,'_client',weather):r=await self.http.post(self.url,json={**body,'message':'Marek, bugün hava nasıl','action_id':str(uuid.uuid4())})
  self.assertIn('Bence bugün hava güzel.',r.json()['narration']);self.assertEqual(weather.chat_calls,1)
  self.assertEqual(r.status_code,200);self.assertIsNone(interaction_adventure.current_conversation_focus(self.session.world_state,self.npc))
  with patch.object(self.app.state.ollama_adapter,'_client',weather):r=await self.http.post(self.url,json={**body,'message':'Konuşmayı bitiriyorum.','interaction_mode':'do','action_id':str(uuid.uuid4())})
  self.assertEqual(r.status_code,200);self.assertFalse(r.json()['state']['conversation']['active']);self.assertEqual(weather.chat_calls,1)
 async def test_end_directly_from_door_focus(self):
  await self.setup_focus();client=ScriptedNpcSpeechClient('unused')
  with patch.object(self.app.state.ollama_adapter,'_client',client):r=await self.http.post(self.url,json={'message':'Konuşmayı bitiriyorum.','action_id':str(uuid.uuid4())})
  self.assertEqual(r.status_code,200);self.assertFalse(r.json()['state']['conversation']['active']);self.assertIsNone(self.context().get('conversation_focus'));self.assertEqual(client.chat_calls,0)
