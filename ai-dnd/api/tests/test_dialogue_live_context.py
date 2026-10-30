"""Regression tests for information missing from the first real free_v1 playthrough.
These verify request plumbing, NOT Qwen output quality.
"""
import copy,json,unittest
import dialogue_runtime,local_dialogue,campaign_time
from api.tests import test_dialogue_runtime as fixture

class LiveContextTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=fixture.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=fixture.DialogueRuntimeTests.asyncTearDown
 setup_free=fixture.DialogueRuntimeTests.setup_free
 send=fixture.DialogueRuntimeTests.send
 async def test_unnamed_player_is_not_the_speaker(self):
  await self.setup_free()
  c=dialogue_runtime.build_context(self.world,self.npc,'Merhaba.')
  self.assertIn('addressee',c)
  self.assertEqual(c['addressee']['actor'],'player')
  self.assertIsNone(c['addressee']['known_name'])
  self.assertEqual(c['speaker']['name'],'Edric')
 async def test_disclosed_name_reaches_same_turn_and_is_remembered(self):
  await self.setup_free();self.reply.spoken='Memnun oldum Kadir.'
  r=await self.send('Benim adım Kadir. Sen nasılsın?');self.assertEqual(r.status_code,200,r.text)
  c=json.loads(self.reply.batches[-1]['messages'][-1]['content'])
  self.assertIn('addressee',c)
  self.assertEqual(c['addressee']['known_name'],'Kadir')
  for _ in range(5):local_dialogue.remember_speech_exchange(self.world,self.npc['id'],'Başka konu.','Peki.')
  self.assertEqual(dialogue_runtime.build_context(self.world,self.npc,'Adımı hatırlıyor musun?')['addressee']['known_name'],'Kadir')
 async def test_disclosed_name_does_not_leak_to_unintroduced_npc(self):
  await self.setup_free();local_dialogue.remember_explicit_player_name(self.npc,'Kadir')
  other={'id':'other','name':'Damaia','location':self.world['location']};self.world['npcs'].append(other)
  c=dialogue_runtime.build_context(self.world,other,'Merhaba');self.assertIn('addressee',c);self.assertIsNone(c['addressee']['known_name'])
 async def test_current_clock_is_projected_without_advancing(self):
  await self.setup_free();campaign_time.initialize(self.world);before=copy.deepcopy(self.world)
  c=dialogue_runtime.build_context(self.world,self.npc,'Sabah mı?')
  self.assertIn('current_time',c)
  self.assertEqual(c['current_time'],campaign_time.public_time(self.world));self.assertEqual(self.world,before)
 async def test_latest_exchange_is_sent_once_not_duplicated(self):
  await self.setup_free();local_dialogue.remember_speech_exchange(self.world,self.npc['id'],'Han?','UNIQUE_OLD_INN_REPLY')
  c=dialogue_runtime.build_context(self.world,self.npc,'Evli misin?')
  self.assertEqual(json.dumps(c).count('UNIQUE_OLD_INN_REPLY'),1)
  self.assertEqual(c['player_message'],'Evli misin?');self.assertEqual(c['history_authority'],'attributed_speech_not_fact')
 async def test_empty_job_pool_has_bounded_reason_not_sleep_claim(self):
  await self.setup_free();c=dialogue_runtime.build_context(self.world,self.npc,'İş var mı?')
  self.assertIn('job_availability',c)
  self.assertEqual(c['job_availability'],{'has_eligible_recipients':False,'reason':'no_eligible_recipient_in_current_context'})
 async def test_current_place_access_in_available_places(self):
  await self.setup_free();city=self.world['location'];pid='test_inn'
  self.world['locations'][pid]={'id':pid,'name':'Rashid Hanı','parent_location_id':city,'scene_kind':'tavern'}
  self.world.setdefault('doors',[]).append({'id':'venue-door:'+pid,'place_id':pid,'locked':True,'open':False})
  c=dialogue_runtime.build_context(self.world,self.npc,'Han açık mı?')
  place=next(p for p in c['available_places'] if p['location_id']==pid);self.assertIn('access',place);self.assertEqual(place['access'],'locked')
 async def test_failed_reply_does_not_persist_name_disclosure(self):
  await self.setup_free();self.reply.raw='not-json';before=copy.deepcopy(self.world)
  r=await self.send('Benim adım Kadir.');self.assertEqual(r.status_code,503,r.text);self.assertEqual(self.world,before)
 async def test_opt_in_trace_records_bound_request_and_raw_reply(self):
  import os,tempfile,uuid
  from pathlib import Path
  from unittest.mock import patch
  await self.setup_free();aid=str(uuid.uuid4())
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'speech.jsonl'
   with patch.dict(os.environ,{'AI_DND_SPEECH_DEBUG':str(path)}):
    r=await self.send('Günün nasıl?',action_id=aid)
   self.assertEqual(r.status_code,200,r.text)
   self.assertTrue(path.exists(),'free_v1 raw/context trace absent')
   records=[json.loads(line) for line in path.read_text().splitlines()]
   rows=[x for x in records if x.get('route')=='free_v1' and x.get('phase')=='provider_response']
   self.assertEqual(len(rows),1);row=rows[0]
   self.assertEqual(row['action_id'],aid);self.assertEqual(row['speaker_id'],self.npc['id'])
   self.assertEqual(row['context']['player_message'],'Günün nasıl?')
   self.assertEqual(json.loads(row['raw_response'])['spoken_text'],self.reply.spoken)
   self.assertEqual(self.reply.calls,1)
 async def test_recipient_pool_does_not_claim_offer_capacity(self):
  from adventure import dialogue_jobs,director
  await self.setup_free();city=self.world['location'];pid='recipient_shop'
  self.world['locations'][pid]={'id':pid,'name':'Alıcı Dükkânı','parent_location_id':city,'scene_kind':'shop'}
  self.world['npcs'].append({'id':'recipient','name':'Cora','location':pid})
  self.world['quests']=[{'quest_id':f'full:{i}','status':'ACTIVE'} for i in range(director.MAX_OPEN)]
  c=dialogue_runtime.build_context(self.world,self.npc,'İş var mı?')
  self.assertTrue(c['job_targets'])
  self.assertEqual(c['job_availability'],{'has_eligible_recipients':True,'reason':'eligible_recipients_available'})
  proposal={'request_key':'capacity','template_id':'DELIVERY','title':'Teslimat','description':'Paket teslimatı','target_npc_id':'recipient','location_id':pid}
  before=copy.deepcopy(self.world)
  with self.assertRaisesRegex(dialogue_runtime.DialogueResponseError,'capacity'):
   dialogue_jobs.prepare(self.session,proposal,self.npc['id'])
  self.assertEqual(self.world,before)
 async def test_hidden_places_doors_and_recipients_are_not_newly_projected(self):
  await self.setup_free();city=self.world['location']
  for pid,flags in (('hidden_place',{'hidden':True}),('undiscovered_place',{'discovered':False}),('public_place',{})):
   self.world['locations'][pid]={'id':pid,'name':pid,'parent_location_id':city,'scene_kind':'shop',**flags}
  for nid,flags in (('hidden_person',{'hidden':True}),('undiscovered_person',{'discovered':False})):
   self.world['npcs'].append({'id':nid,'name':nid,'location':'public_place',**flags})
  self.world.setdefault('doors',[]).extend([
   {'id':'hidden_door','place_id':'public_place','locked':True,'hidden':True},
   {'id':'undiscovered_door','place_id':'public_place','locked':True,'discovered':False}])
  c=dialogue_runtime.build_context(self.world,self.npc,'Neresi açık?')
  self.assertNotIn('hidden_place',[p['location_id'] for p in c['available_places']])
  self.assertNotIn('undiscovered_place',[p['location_id'] for p in c['available_places']])
  self.assertEqual(next(p for p in c['available_places'] if p['location_id']=='public_place')['access'],'unknown')
  self.assertFalse(c['job_targets'])
  self.assertNotIn('hidden_person',json.dumps(c));self.assertNotIn('undiscovered_person',json.dumps(c))
 async def test_four_exchange_order_preserved_once_each(self):
  await self.setup_free()
  for i in range(6):local_dialogue.remember_speech_exchange(self.world,self.npc['id'],f'question_{i}',f'reply_{i}')
  c=dialogue_runtime.build_context(self.world,self.npc,'Yeni soru.')
  self.assertEqual(c['conversation_so_far'],[{'player':f'question_{i}','npc':f'reply_{i}'} for i in (2,3,4)])
  self.assertEqual(c['last_exchange'],{'player':'question_5','npc':'reply_5'})
  for i in (2,3,4,5):self.assertEqual(json.dumps(c).count(f'reply_{i}'),1)
 async def test_invalid_commitment_does_not_persist_name_disclosure(self):
  await self.setup_free()
  self.reply.raw=json.dumps({'spoken_text':'Buyur.','stage_direction':'','place_proposals':[],
   'job_proposals':[{'request_key':'bad','template_id':'DELIVERY','title':'Teslimat','description':'Paket','target_npc_id':'missing','location_id':'missing'}]})
  before=copy.deepcopy(self.world)
  r=await self.send('Benim adım Kadir.');self.assertEqual(r.status_code,503,r.text);self.assertEqual(self.world,before)
 async def test_disabled_trace_does_not_open_output_file(self):
  import os,game
  from unittest.mock import patch
  await self.setup_free()
  with patch.dict(os.environ,{'AI_DND_SPEECH_DEBUG':'off'}),patch.object(game,'open',create=True) as opened:
   r=await self.send('Merhaba.')
  self.assertEqual(r.status_code,200,r.text);opened.assert_not_called();self.assertEqual(self.reply.calls,1)
 async def test_unwritable_trace_does_not_break_turn(self):
  import os,game
  from unittest.mock import patch
  await self.setup_free()
  with patch.dict(os.environ,{'AI_DND_SPEECH_DEBUG':'synthetic-denied-trace.jsonl'}),patch.object(game,'open',create=True,side_effect=PermissionError('synthetic denied trace')) as opened:
   r=await self.send('Merhaba.')
  self.assertEqual(r.status_code,200,r.text);self.assertTrue(opened.called);self.assertEqual(self.reply.calls,1)
