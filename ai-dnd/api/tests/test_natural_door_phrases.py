import copy,unittest
from unittest.mock import patch
import game,grounded_action
from api.tests import test_door_tool_acceptance as fixture
class NaturalDoorTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=fixture.DoorToolAcceptance.asyncSetUp
 asyncTearDown=fixture.DoorToolAcceptance.asyncTearDown
 scene=fixture.DoorToolAcceptance.scene
 post=fixture.DoorToolAcceptance.post
 door=fixture.DoorToolAcceptance.door
 protected=fixture.DoorToolAcceptance.protected
 async def test_short_open_targets_locked_door(self):
  await self.scene(active=False);before=self.protected();out,r,_=await self.post('Han kapısını açıyorum')
  self.assertEqual(r['target_id'],self.door_id);self.assertFalse(self.door()['open']);self.assertTrue(self.door()['locked']);self.assertEqual(before,self.protected());self.assertIn('kilitli',out['narration'])
 async def test_tool_phrases_require_real_tools(self):
  await self.scene(active=False)
  for text in ('Kapıyı maymuncukla açıyorum','Orryn Hanı Kapısını maymuncukla açıyorum'):
   with self.subTest(text=text):
    before=self.protected();out,r,_=await self.post(text);self.assertEqual(r['reason'],'tools_required');self.assertEqual(r['target_id'],self.door_id);self.assertEqual(before,self.protected())
 async def test_tool_phrase_uses_unlock_not_plain_open(self):
  await self.scene(active=False,tools=True,seed=5)
  out,r,_=await self.post('Kapıyı maymuncukla açıyorum')
  self.assertEqual(r['target_id'],self.door_id);self.assertEqual(r['skill'],'Sleight of Hand');self.assertIn('success',r)
 async def test_negative_and_reported_do_not_change_door(self):
  await self.scene(active=False)
  for text in ('Kapıyı açmıyorum','Kapıyı açmak istemiyorum','Dün kapıyı maymuncukla açmayı denedim','Kapıyı açabilir miyim?'):
   with self.subTest(text=text):
    before=self.protected()
    with self.app.state.ollama_adapter.engine_binding():
     p=grounded_action.plan(self.session,text)
     self.assertFalse(any(grounded_action._direct_door_step(s) for s in p['steps']))
    self.assertEqual(before,self.protected())
 async def test_other_object_is_not_nearest_door(self):
  await self.scene(active=False)
  with self.app.state.ollama_adapter.engine_binding():
   p=grounded_action.plan(self.session,'Kitabı maymuncukla açıyorum')
  self.assertTrue(p['steps'][0].get('foreign_object'));self.assertFalse(grounded_action._direct_door_step(p['steps'][0]))
 async def test_locked_open_then_enter_stops_before_entry(self):
  await self.scene(active=False);location=self.world['location'];out,r,_=await self.post('Kapıyı açıp içeri giriyorum')
  self.assertEqual(self.world['location'],location);self.assertTrue(self.door()['locked']);self.assertFalse(self.door()['open'])
 async def test_reason_question_not_caught_by_legacy_absence_rule(self):
  await self.scene(active=False)
  with patch.object(game,'_current_door',return_value=None):
   self.assertIsNone(self.session.resolve_python_world_action('kapı niye kilitliydi?'))
