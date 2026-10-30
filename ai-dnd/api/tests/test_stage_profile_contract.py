"""Scoped stage authority and native-public personal-detail contracts."""
import copy,json,unittest,uuid
from unittest.mock import patch
import game,local_dialogue
import test_narrative_rebalance as nr
from api.tests import test_route_focus_regressions as route

KING='Neverwinter is ruled by King Vharion.'
class Client:
 def __init__(self,spoken,stage=''):self.spoken=spoken;self.stage=stage;self.calls=[]
 def list(self):return {'models':[{'model':'qwen3:8b'}]}
 def chat(self,*a,**k):
  self.calls.append(copy.deepcopy(k))
  return {'message':{'content':json.dumps({'spoken_text':self.spoken,'stage_direction':self.stage},ensure_ascii=False)}}

class StageContractTests(unittest.TestCase):
 setUp=nr.TestNarrativeRebalance.setUp
 tearDown=nr.TestNarrativeRebalance.tearDown
 def turn(self,spoken,stage):
  client=Client(spoken,stage);before=copy.deepcopy(self.session.world_state['npcs']);inventory=copy.deepcopy(self.session.world_state['inventory']);rng=self.session.rng.getstate()
  with patch('game.ollama.chat',side_effect=client.chat):r=self.session.run_player_turn('Hancı, buralarda neler dönüyor?')
  self.assertEqual(self.session.world_state['npcs'],before);self.assertEqual(self.session.world_state['inventory'],inventory);self.assertEqual(self.session.rng.getstate(),rng);self.assertEqual(len(client.calls),1)
  return r
 def test_spoken_rumor_retained_stage_removed_and_history_single(self):
  r=self.turn(KING,KING);self.assertIn('“'+KING+'”',r['narration']);self.assertNotIn('('+KING.rstrip('.')+')',r['narration'])
  self.assertEqual(self.session.last_narration_safety['reason_code'],'UNVERIFIED_LORE_CLAIM');self.assertEqual(self.session.last_narration_safety['handling'],'repaired')
  self.assertEqual(len(self.session.narration_safety_history),1);self.assertEqual(self.session.world_state['npc_speech_log']['npc_barkeep'],[{'player':'Hancı, buralarda neler dönüyor?','npc':KING}])
 def test_spoken_only_rumor_remains_attributed(self):
  r=self.turn(KING,'');self.assertIn(KING,r['narration']);self.assertEqual(self.session.last_narration_safety['handling'],'accepted')
 def test_visible_gesture_and_current_scene_retained(self):
  r=self.turn('Burada seni dinliyorum.','Hancı tezgaha yaslanıp kısık sesle konuşur.');self.assertIn('tezgaha yaslanıp',r['narration']);self.assertEqual(self.session.last_narration_safety['handling'],'accepted')
 def test_relationship_claim_still_rejected(self):
  text='Hancı artık sana tamamen güveniyor ve seni en iyi dostu ilan ediyor.';r=self.turn(text,text);self.assertNotIn('en iyi dostu',r['narration']);self.assertEqual(self.session.last_narration_safety['reason_code'],'CANONICAL_RELATIONSHIP_CONTRADICTION')
 def test_player_action_and_transfer_still_rejected(self):
  r=self.turn('Kapıyı açıp içeri giriyorsun.','Hancı sana hanın anahtarını veriyor.');self.assertNotIn('Kapıyı açıp içeri giriyorsun',r['narration']);self.assertNotIn('anahtarını veriyor',r['narration'])
 def test_private_stage_not_repaired_into_acceptance(self):
  self.session.world_state['npcs'][0]['personal_profile']={'private_secret':'Mahzenin altında mor mühür saklıdır.'}
  r=self.turn('Burada seni dinliyorum.','Mahzenin altında mor mühür saklıdır.');self.assertNotIn('mor mühür',r['narration']);self.assertEqual(self.session.last_narration_safety['reason_code'],'NPC_PRIVATE_PROFILE_DISCLOSURE')

class PublicDetailHttpTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=route.RouteFocusRegressionTests.asyncSetUp
 asyncTearDown=route.RouteFocusRegressionTests.asyncTearDown
 prepare=route.RouteFocusRegressionTests.prepare
 replay_cold=route.RouteFocusRegressionTests.replay_cold
 async def setup_person(self):
  await self.prepare();self.npc.clear();self.npc.update(id='npc_saved_personal_traveler',name='Derya',role='Yolcu',location=self.session.world_state['location'],reality_layer='PROCEDURAL_LOCAL_FICTION',name_known_to_player=True)
  local_dialogue.ensure_personal_profile(self.npc);self.session.world_state['flags']['active_npc_id']=self.npc['id']
 async def send(self,text,answer,target=None):
  self.client=Client(answer);body={'message':text,'action_id':str(uuid.uuid4())}
  if target:body['target_id']=target
  before=copy.deepcopy(self.session.world_state['npcs']);rng=self.session.rng.getstate();inventory=copy.deepcopy(self.session.world_state['inventory'])
  with patch.object(self.app.state.ollama_adapter,'_client',self.client), self.app.state.ollama_adapter.engine_binding():
   r=await self.http.post(self.url,json=body)
  self.assertEqual(len(self.client.calls),1, 'Each turn must use its own configured fake provider')
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.session.rng.getstate(),rng);self.assertEqual(self.session.world_state['inventory'],inventory)
  for n,old in zip(self.session.world_state['npcs'],before):
   for key in ('id','name','personal_profile','location'):self.assertEqual(n.get(key),old.get(key))
  return r,body
 async def test_native_public_detail_prompt_response_cold_replay(self):
  await self.setup_person();detail=self.npc['personal_profile']['personal_detail'];self.assertEqual(detail,'Yol boyunca çantamın kayışı yine gevşedi.')
  native=local_dialogue.personal_answer(self.npc,'Peki sen, kendinden biraz bahset.');self.assertIn(detail,native[0])
  r,b=await self.send('Peki sen, kendinden biraz bahset.',detail)
  self.assertIn(detail,json.dumps(self.client.calls,ensure_ascii=False));self.assertIn(detail,r.json()['narration']);self.assertEqual(len(self.client.calls),1);await self.replay_cold(b,r)
 async def test_other_npc_detail_private_and_hidden_stay_rejected(self):
  for mode in ('other','private','hidden'):
   with self.subTest(mode=mode):
    await self.setup_person();other=copy.deepcopy(self.npc);other.update(id='npc_saved_personal_guard',name='Duru',role='Muhafız');other.pop('personal_profile');local_dialogue.ensure_personal_profile(other);other['hidden']=mode=='hidden';self.session.world_state['npcs'].append(other)
    secret='Mahzenin altında mor mühür saklıdır.'
    if mode=='private':self.npc['personal_profile']['private_secret']=secret
    answer=secret if mode=='private' else other['personal_profile']['personal_detail']
    r,b=await self.send('Peki sen, kendinden biraz bahset.',answer,self.npc['id']);self.assertNotIn(answer,json.dumps(self.client.calls,ensure_ascii=False));self.assertNotIn(answer,r.json()['narration']);self.assertEqual(self.session.last_narration_safety['reason_code'],'NPC_PRIVATE_PROFILE_DISCLOSURE');await self.replay_cold(b,r)
 async def test_npc_switch_and_topic_change_keep_public_detail_bound(self):
  await self.setup_person();other=copy.deepcopy(self.npc);other.update(id='npc_saved_personal_guard',name='Duru',role='Muhafız');other.pop('personal_profile');local_dialogue.ensure_personal_profile(other);self.session.world_state['npcs'].append(other)
  first=self.npc['personal_profile']['personal_detail'];r,b=await self.send('Peki sen, kendinden biraz bahset.',first,self.npc['id']);self.assertIn(first,r.json()['narration'])
  detail=other['personal_profile']['personal_detail'];self.assertEqual(detail,'Nöbet değişimleri genelde günün aynı saatlerinde olur.')
  r,b=await self.send('Peki sen, kendinden biraz bahset.',detail,other['id']);self.assertIn(detail,r.json()['narration']);self.assertNotIn(first,json.dumps(self.client.calls,ensure_ascii=False));await self.replay_cold(b,r)
  r,b=await self.send('Bugün hava nasıl?','Bence hava güzel.',other['id']);self.assertIn('Bence hava güzel.',r.json()['narration']);await self.replay_cold(b,r)
