import copy,json,unittest
import local_dialogue,dialogue_runtime
from api.tests import test_dialogue_runtime as runtime_fixture

class PersonaUnitTests(unittest.TestCase):
 def npc(self):return {'id':'edric','name':'Edric','role':'bartender','personality':'Temkinli, az konuşur ama yardımsever.'}
 def require(self):self.assertTrue(hasattr(local_dialogue,'ensure_dialogue_persona'),'persona projection not implemented')
 def test_personality_is_preserved_in_stable_persona(self):
  self.require();n=self.npc();p=local_dialogue.ensure_dialogue_persona(n)
  self.assertEqual(p['temperament'],n['personality']);self.assertEqual(p['version'],1);self.assertIn('voice',p)
 def test_persona_is_stable_when_current_mood_changes(self):
  self.require();n=self.npc();a=copy.deepcopy(local_dialogue.ensure_dialogue_persona(n));n['personal_profile']={'mood':'Endişeliyim.'}
  self.assertEqual(local_dialogue.ensure_dialogue_persona(n),a)
 def test_same_role_does_not_force_identical_voice(self):
  self.require();a=local_dialogue.ensure_dialogue_persona(self.npc());n=self.npc();n.update(id='another',personality='Şakacı ve konuşkan.')
  b=local_dialogue.ensure_dialogue_persona(n);self.assertNotEqual(a['temperament'],b['temperament'])
 def test_read_only_context_does_not_create_persona(self):
  self.require();n=self.npc();world={'npcs':[n]};before=copy.deepcopy(world)
  local_dialogue.persona_context(world,n);self.assertEqual(world,before)

class PersonaHttpTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=runtime_fixture.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=runtime_fixture.DialogueRuntimeTests.asyncTearDown
 setup_free=runtime_fixture.DialogueRuntimeTests.setup_free
 send=runtime_fixture.DialogueRuntimeTests.send
 # Explicit loader selects these methods only; inherited contract tests are run separately.
 async def test_personality_reaches_speech_context(self):
  await self.setup_free();r=await self.send('Burada iş bulabilir miyim?');self.assertEqual(r.status_code,200,r.text)
  context=json.loads(self.reply.batches[-1]['messages'][-1]['content'])
  self.assertIn('persona',context);self.assertEqual(context['persona']['stable']['temperament'],self.npc['personality'])
 async def test_irrelevant_counter_scratch_not_in_job_context(self):
  await self.setup_free();self.npc['personal_profile']={'personal_detail':'Tezgâhın köşesindeki küçük çizik yıllardır orada.','occupation':'Barmenlik yapıyorum.'}
  r=await self.send('Burada nerede iş bulabilirim?');self.assertEqual(r.status_code,200,r.text)
  context=json.loads(self.reply.batches[-1]['messages'][-1]['content'])
  self.assertNotIn('küçük çizik',json.dumps(context,ensure_ascii=False))
 async def test_followup_receives_last_place_exchange_not_identity_template(self):
  await self.setup_free();self.world['locations']['test_inn']={'id':'test_inn','name':'Orryn Hanı','parent_location_id':self.world['location'],'scene_kind':'tavern'};self.reply.spoken='Orryn Hanı yakında.'
  a=await self.send('Bir han var mı?');self.assertEqual(a.status_code,200,a.text)
  self.reply.spoken='Orryn Hanı.';b=await self.send('İsmi nedir?',mode='do');self.assertEqual(b.status_code,200,b.text)
  self.assertIn('Orryn Hanı',b.json()['narration'])
  context=json.loads(self.reply.batches[-1]['messages'][-1]['content'])
  self.assertEqual(context['last_exchange']['npc'],'Orryn Hanı yakında.')
 async def test_persona_context_read_is_pure(self):
  await self.setup_free();before=copy.deepcopy(self.world);dialogue_runtime.build_context(self.world,self.npc,'Nasılsın?');self.assertEqual(self.world,before)
