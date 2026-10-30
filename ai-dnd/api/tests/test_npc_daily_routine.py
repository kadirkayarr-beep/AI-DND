import copy,unittest
from unittest.mock import patch
import campaign_time,scheduled_events,local_places
class RoutineTests(unittest.TestCase):
 def setup_world(self):
  w={'location':'square','locations':{'square':{'id':'square','name':'Kent','type':'city'},'work':{'id':'work','name':'Arşiv','parent_location_id':'square'},'rest':{'id':'rest','name':'Dinlenme yeri','parent_location_id':'square'}},'npcs':[{'id':'n','name':'Marek','location':'work','place_role_of':'work'}],'flags':{'turn_index':0},'quests':[]}
  campaign_time.initialize(w)
  stops=[{'start_second':0,'end_second':8*3600,'location_id':'rest','activity':'Dinleniyor.'},{'start_second':8*3600,'end_second':17*3600,'location_id':'work','activity':'Çalışıyor.'},{'start_second':17*3600,'end_second':86400,'location_id':'rest','activity':'Dinleniyor.'}]
  return w,stops
 def register(self):
  self.assertTrue(hasattr(scheduled_events,'register_npc_routine'));w,s=self.setup_world();scheduled_events.register_npc_routine(w,'n',s);return w
 def test_offscreen_shift_moves_same_npc(self):
  w=self.register();campaign_time.advance(w,9*3600,'wait','e1');self.assertEqual(w['npcs'][0]['location'],'rest');self.assertEqual(len(w['npcs']),1)
 def test_long_jump_and_midnight_use_game_clock(self):
  w=self.register();campaign_time.advance(w,3*86400+15*3600,'wait','e1');self.assertEqual(w['npcs'][0]['location'],'rest');campaign_time.advance(w,9*3600,'wait','e2');self.assertEqual(w['npcs'][0]['location'],'work')
 def test_registration_rejects_overlap_and_unknown_place_atomically(self):
  self.assertTrue(hasattr(scheduled_events,'register_npc_routine'));w,s=self.setup_world();before=copy.deepcopy(w);s[1]['start_second']=0
  with self.assertRaises(ValueError):scheduled_events.register_npc_routine(w,'n',s)
  self.assertEqual(w,before);w,s=self.setup_world();s[1]['location_id']='missing'
  with self.assertRaises(ValueError):scheduled_events.register_npc_routine(w,'n',s)
 def test_conversation_and_combat_prevent_mid_scene_teleport(self):
  w=self.register();w['location']='work';w['flags'].update(active_npc_id='n',active_npc_until_turn=6)
  campaign_time.advance(w,9*3600,'wait','e1');self.assertEqual(w['npcs'][0]['location'],'work');w['flags'].pop('active_npc_id');w['combat']={'active':True}
  campaign_time.advance(w,0,'wait','e2');self.assertEqual(w['npcs'][0]['location'],'work');w['combat']['active']=False
  campaign_time.advance(w,0,'wait','e3');self.assertEqual(w['npcs'][0]['location'],'rest')
 def test_open_job_giver_keeps_identity_and_resumes_after_close(self):
  w=self.register();w['quests']=[{'status':'ACTIVE','giver_npc_id':'n','bindings':{'source_npc_id':'n','target_npc_id':'n'}}]
  campaign_time.advance(w,9*3600,'wait','e1');self.assertEqual(w['npcs'][0]['location'],'work');w['quests'][0]['status']='COMPLETED'
  campaign_time.advance(w,0,'wait','e2');self.assertEqual(w['npcs'][0]['location'],'rest')
 def test_wall_clock_read_and_roundtrip_do_not_advance(self):
  w=self.register();before=copy.deepcopy(w)
  with patch('time.time',return_value=999999999999):
   for _ in range(5):campaign_time.public_time(w)
  self.assertEqual(w,before);import json;restored=json.loads(json.dumps(w));self.assertEqual(campaign_time.public_time(restored),campaign_time.public_time(w))
 def test_repeated_processing_does_not_clone_or_repeat_notice(self):
  w=self.register();w['location']='work';a=campaign_time.advance(w,9*3600,'wait','e1');b=campaign_time.advance(w,0,'wait','e2');self.assertEqual(len(w['npcs']),1);self.assertFalse(b['player_known_events'])
 def test_away_resident_is_not_replaced_on_furnishing(self):
  w,s=self.setup_world();w['locations']['work'].update(place_kind='archive');w['npcs'][0]['location']='rest'
  def forbidden(_):self.fail('Duplicate resident created')
  npc,_=local_places.furnish(w,w['locations']['work'],create_npc=forbidden,create_feature=lambda p:dict(p,id='feature'))
  self.assertIsNone(npc);self.assertEqual(len(w['npcs']),1)

 def test_unconscious_or_hidden_event_does_not_reveal_movement(self):
  w=self.register();w['location']='work';w['player_combat_status']='unconscious'
  result=campaign_time.advance(w,9*3600,'wait','e1');self.assertEqual(w['npcs'][0]['location'],'rest');self.assertFalse(result['player_known_events'])
  w=self.register();w['location']='work';w['scheduled_events']=[{'status':'OCCURRED','player_observed':False,'visibility':'hidden','effects':[{'kind':'npc_location','npc_id':'n','location_id':'work'}]}]
  self.assertFalse(scheduled_events.process_npc_routines(w,9*3600))

 def test_scripted_relocation_takes_precedence_over_daily_routine(self):
  w=self.register();scheduled_events.register_event(w,event_id='move',window_start=1,window_end=60,location_id='work',effects=[{'kind':'npc_location','npc_id':'n','location_id':'rest'}])
  campaign_time.advance(w,60,'wait','e1');self.assertEqual(w['scheduled_events'][0]['status'],'OCCURRED');self.assertEqual(w['npcs'][0]['location'],'rest')
  campaign_time.advance(w,60,'wait','e2');self.assertEqual(w['npcs'][0]['location'],'rest')

 def test_undiscovered_npc_does_not_emit_named_notice(self):
  w=self.register();w['location']='work';w['npcs'][0]['discovered']=False
  result=campaign_time.advance(w,9*3600,'wait','e1');self.assertFalse(result['player_known_events'])

from api.tests import test_dialogue_runtime as base
import uuid,json,httpx
class RoutineHttpTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=base.DialogueRuntimeTests.asyncTearDown
 setup_free=base.DialogueRuntimeTests.setup_free
 send=base.DialogueRuntimeTests.send
 async def test_conversation_time_is_fixed_replayable_and_not_wall_clock(self):
  await self.setup_free();start=self.world['campaign_time']['elapsed_seconds'];aid=str(uuid.uuid4())
  with patch('time.time',return_value=999999999):r=await self.send('Nasılsın?',action_id=aid)
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.world['campaign_time']['elapsed_seconds'],start+60)
  again=await self.send('Nasılsın?',action_id=aid);self.assertEqual(r.json(),again.json());self.assertEqual(self.world['campaign_time']['elapsed_seconds'],start+60)
  self.assertIn('daily_routine',self.npc)
 async def test_cold_resume_retains_schedule_and_does_not_catch_up(self):
  await self.setup_free();await self.send('Nasılsın?');await self.http.post(f'/api/game/campaigns/{self.campaign_id}/save')
  from api.session_manager import SessionManager
  from api.main import create_app
  from api.auth import FixedAuthenticator
  from api.tests.auth_fixture import TEST_PLAYER
  from api.ollama_adapter import AuthenticatedOllamaAdapter
  fresh=SessionManager(campaign_store=self.store);app=create_app(session_manager=fresh,ollama_adapter=AuthenticatedOllamaAdapter(self.reply),authenticator=FixedAuthenticator(TEST_PLAYER))
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as http:
   r=await http.post(f'/api/game/campaigns/{self.campaign_id}/resume')
  self.assertEqual(r.status_code,200,r.text);restored=fresh.get(r.json()['session_id']).game_session.world_state
  self.assertEqual(restored['campaign_time'],self.world['campaign_time']);n=next(n for n in restored['npcs'] if n['id']==self.npc['id']);self.assertEqual(n['daily_routine'],self.npc['daily_routine'])
