import copy,json,unittest
from api.tests import test_dialogue_runtime as base
class CommitmentTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=base.DialogueRuntimeTests.asyncTearDown
 setup_free=base.DialogueRuntimeTests.setup_free
 send=base.DialogueRuntimeTests.send
 async def test_unbacked_named_recommendation_rolls_back(self):
  await self.setup_free();self.reply.spoken='Gümüş Kılıç Hanı burada; oraya gidebilirsin.';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_unbacked_generic_recommendation_rolls_back(self):
  await self.setup_free();self.reply.spoken='Yakında bir han var, oraya git.';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_denied_historical_and_hypothetical_names_do_not_create(self):
  await self.setup_free()
  for text in ('Gümüş Kılıç Hanı diye bir yer yok.','Eskiden Gümüş Kılıç Hanı vardı.','Gümüş Kılıç Hanı olsaydı oraya giderdim.'):
   self.reply.spoken=text;before=copy.deepcopy(self.world['locations']);r=await self.send('Han var mı?')
   self.assertEqual(r.status_code,200,r.text);self.assertEqual(before,self.world['locations'])
 async def test_denial_does_not_mask_next_unbacked_recommendation(self):
  await self.setup_free();self.reply.spoken='Eski Han yok; Gümüş Kılıç Hanı burada, oraya git.'
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text)
 async def test_job_promise_without_job_record_rolls_back(self):
  await self.setup_free();self.reply.spoken='Sana verebileceğim bir iş var, paketi götür.';before=copy.deepcopy(self.session.serialize_game_state())
  r=await self.send('İş var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_missing_commitment_fields_is_invalid_packet(self):
  await self.setup_free();self.reply.raw=json.dumps({'spoken_text':'Merhaba.','stage_direction':''});r=await self.send('Selam.');self.assertEqual(r.status_code,503,r.text)
 async def test_discourse_prefix_does_not_become_part_of_existing_place_name(self):
  await self.setup_free();self.world['locations']['real_inn']={'id':'real_inn','name':'Gümüş Kılıç Hanı','scene_kind':'tavern','parent_location_id':self.world['location']}
  for text in ('Evet, Gümüş Kılıç Hanı burada.','Hayır, Gümüş Kılıç Hanı kapalı.'):
   self.reply.spoken=text;r=await self.send('Han var mı?');self.assertEqual(r.status_code,200,r.text);self.assertIn(text,r.json()['narration'])
 async def test_unknown_place_after_comma_is_still_unbound(self):
  await self.setup_free();self.reply.spoken='Evet, Gümüş Kılıç Hanı burada.'
  r=await self.send('Han var mı?');self.assertEqual(r.status_code,503,r.text)
