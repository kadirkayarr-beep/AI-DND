"""Integrated synthetic acceptance; this is not real Qwen quality evidence."""
import copy,json,unittest,uuid
from unittest.mock import patch
from api.tests import test_dialogue_runtime as base
class FreePlaythroughTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=base.DialogueRuntimeTests.asyncTearDown
 setup_free=base.DialogueRuntimeTests.setup_free
 send=base.DialogueRuntimeTests.send
 async def step(self,text,mode='do'):
  response=await self.send(text,mode=mode);self.assertEqual(response.status_code,200,response.text);return response.json()
 async def test_kildrak_full_inn_door_edric_and_real_job(self):
  await self.setup_free();self.npc['name']='Kildrak';city=self.world['location'];kildrak=self.npc
  self.reply.spoken='Ben Kildrak.';await self.step('Selam, ismin nedir?',mode='say')
  self.reply.raw=json.dumps({'spoken_text':'Gümüş Kılıç Hanı burada, orada dinlenebilirsin.','stage_direction':'','place_proposals':[{'request_key':'inn','kind':'tavern','name':'Gümüş Kılıç Hanı','settlement_id':city}],'job_proposals':[]},ensure_ascii=False)
  await self.step('Buralarda bildiğin bir han var mı?',mode='say')
  inn=next(p for p in self.world['locations'].values() if p.get('name')=='Gümüş Kılıç Hanı')
  self.reply.raw=None;self.reply.spoken='Gümüş Kılıç Hanı.';follow=await self.step('İsmi nedir?',mode='say');self.assertIn('Gümüş Kılıç Hanı',follow['narration'])
  await self.step('Konuşmayı bitiriyorum.')
  await self.step('Gümüş Kılıç Hanına gidiyorum')
  door=next(d for d in self.world['doors'] if d['id']=='venue-door:'+inn['id']);door.update(locked=True,open=False)
  opened=await self.step('Han kapısını açıyorum');self.assertTrue(door['locked']);self.assertNotIn('Hangisini kastediyorsun',opened['narration'])
  blocked=await self.step('Kapıyı maymuncukla açıyorum');self.assertTrue(door['locked']);self.assertIn('maymuncuk',blocked['narration'].lower())
  self.world['inventory'].append({'item_id':'playthrough_tools','name':"Thieves' Tools"});self.session.rng.seed(5)
  unlocked=await self.step('Kapıyı maymuncukla açıyorum');self.assertFalse(door['locked'],unlocked)
  await self.step('İçeri giriyorum');self.assertEqual(self.world['location'],inn['id'])
  bartender=next(n for n in self.world['npcs'] if n.get('location')==inn['id'] and 'barmen' in str(n.get('role','')).lower());bartender['name']='Edric'
  self.reply.spoken='Edric. Sana nasıl yardımcı olayım?';await self.step('Bir barmen ile konuşmak istiyorum.',mode='say')
  self.reply.spoken='Gece kilitli tutuyoruz; içerideydim.';before=copy.deepcopy(self.world['doors']);cause=await self.step('Kapı niye kilitliydi?',mode='say');self.assertIn(self.reply.spoken,cause['narration']);self.assertEqual(before,self.world['doors'])
  self.reply.raw=json.dumps({'spoken_text':'Bir teslimat işi var, ilgilenir misin?','stage_direction':'','place_proposals':[],'job_proposals':[{'request_key':'parcel','template_id':'DELIVERY','title':'Kildrak için paket','description':'Kildrak için paket','target_npc_id':kildrak['id'],'location_id':city}]},ensure_ascii=False)
  await self.step('Burada nerede iş bulabilirim?',mode='say')
  q=next(q for q in self.world['quests'] if q.get('creation_evidence','').startswith('dialogue-job:'));accept=await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{q["quest_id"]}/accept');self.assertEqual(accept.status_code,200,accept.text)
  self.reply.raw=None;await self.step('Paketi alıyorum');await self.step('Konuşmayı bitiriyorum.')
  await self.step("Neverwinter'a gidiyorum");self.assertEqual(self.world['location'],city)
  await self.step('Paketi Kildrak adlı kişiye teslim ediyorum');self.assertEqual(q['status'],'COMPLETED');self.assertIsNotNone(q['reward_application_id'])
  saved=await self.http.post(f'/api/game/campaigns/{self.campaign_id}/save');self.assertEqual(saved.status_code,200,saved.text)
  self.assertEqual(len([p for p in self.world['locations'].values() if p.get('name')=='Gümüş Kılıç Hanı']),1)
