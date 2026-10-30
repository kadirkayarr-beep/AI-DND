import copy,unittest
import dialogue_runtime
class InitiativeTests(unittest.TestCase):
 def setup(self):
  n={'id':'n','name':'Marek','location':'here'};w={'location':'here','npcs':[n],'flags':{'turn_index':2}}
  event={'id':'injury:1','kind':'visible_injury','visible':True,'location_id':'here','turn_index':1};n['dialogue_observation']=event
  return w,n,event
 def test_visible_witnessed_injury_can_prompt_once(self):
  self.assertTrue(hasattr(dialogue_runtime,'initiative_context'));w,n,e=self.setup();self.assertIsNotNone(dialogue_runtime.initiative_context(w,n,e));n['dialogue_initiative_handled']=e['id'];self.assertIsNone(dialogue_runtime.initiative_context(w,n,e))
 def test_hidden_condition_or_remote_npc_not_eligible(self):
  self.assertTrue(hasattr(dialogue_runtime,'initiative_context'));w,n,e=self.setup();e['visible']=False;self.assertIsNone(dialogue_runtime.initiative_context(w,n,e));e['visible']=True;n['location']='elsewhere';self.assertIsNone(dialogue_runtime.initiative_context(w,n,e))
 def test_unrecorded_event_cannot_claim_observation(self):
  self.assertTrue(hasattr(dialogue_runtime,'initiative_context'));w,n,e=self.setup();n.pop('dialogue_observation');self.assertIsNone(dialogue_runtime.initiative_context(w,n,e))
 def test_context_is_pure(self):
  self.assertTrue(hasattr(dialogue_runtime,'initiative_context'));w,n,e=self.setup();before=copy.deepcopy(w);dialogue_runtime.initiative_context(w,n,e);self.assertEqual(before,w)

from api.tests import test_dialogue_runtime as base
from unittest.mock import patch
import json,uuid
class InitiativeHttpTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=base.DialogueRuntimeTests.asyncTearDown
 setup_free=base.DialogueRuntimeTests.setup_free
 send=base.DialogueRuntimeTests.send
 async def test_exploration_can_include_one_contextual_initiative_and_replay(self):
  await self.setup_free();self.npc['dialogue_observation']={'id':'injury:test','kind':'visible_injury','visible':True,'location_id':self.world['location'],'turn_index':0}
  self.reply.spoken='Kolun yaralanmış, iyi misin?';aid=str(uuid.uuid4())
  r=await self.send('Çevreyi gözlemliyorum.',mode='do',action_id=aid);self.assertEqual(r.status_code,200,r.text)
  self.assertIn(self.reply.spoken,r.json()['narration']);self.assertEqual(self.npc.get('dialogue_initiative_handled'),'injury:test');self.assertLessEqual(self.reply.calls,2)
  calls=self.reply.calls;again=await self.send('Çevreyi gözlemliyorum.',mode='do',action_id=aid);self.assertEqual(r.json(),again.json());self.assertEqual(self.reply.calls,calls)
  self.reply.calls=0;r2=await self.send('Çevreyi gözlemliyorum.',mode='do');self.assertEqual(r2.status_code,200,r2.text);self.assertNotIn(self.reply.spoken,r2.json()['narration'])
 async def test_failed_optional_initiative_does_not_invent_a_reply(self):
  await self.setup_free();self.npc['dialogue_observation']={'id':'injury:test','kind':'visible_injury','visible':True,'location_id':self.world['location'],'turn_index':0}
  self.reply.raw='not json';r=await self.send('Çevreyi gözlemliyorum.',mode='do');self.assertEqual(r.status_code,200,r.text);self.assertNotIn('not json',r.json()['narration']);self.assertNotIn('dialogue_initiative_handled',self.npc)
 async def test_combat_wound_is_observed_only_by_present_visible_npc(self):
  await self.setup_free();before=copy.deepcopy(self.world);hp=self.session.character['current_hp'];self.session.character['current_hp']=max(0,hp-1)
  self.world['npcs'].append({'id':'remote','name':'Remote','location':'far'})
  result={'action_result':{'action':'attack'},'model_calls':0}
  dialogue_runtime.observe_turn(self.session,before,hp,result,'Saldırıyorum','e1')
  self.assertEqual(self.npc.get('dialogue_observation',{}).get('id'),'injury:e1');self.assertNotIn('dialogue_observation',self.world['npcs'][-1])
 async def test_optional_timeout_keeps_resolved_exploration(self):
  await self.setup_free();self.npc['dialogue_observation']={'id':'injury:test','kind':'visible_injury','visible':True,'location_id':self.world['location'],'turn_index':0}
  with patch.object(self.reply,'chat',side_effect=TimeoutError('synthetic timeout')):
   r=await self.send('Çevreyi gözlemliyorum.',mode='do')
  self.assertEqual(r.status_code,200,r.text);self.assertNotIn('dialogue_initiative_handled',self.npc)
 async def test_optional_initiative_does_not_expose_deception_motive(self):
  await self.setup_free();await self.send('Seni öldüreceğim.');self.npc['dialogue_observation']={'id':'injury:test','kind':'visible_injury','visible':True,'location_id':self.world['location'],'turn_index':0}
  self.reply.calls=0;self.reply.batches=[]
  r=await self.send('Çevreyi gözlemliyorum.',mode='do');self.assertEqual(r.status_code,200,r.text)
  context=json.loads(self.reply.batches[-1]['messages'][-1]['content']);self.assertIsNone(context['deception']);self.assertEqual(self.npc['dialogue_deception']['remaining_uses'],1)
