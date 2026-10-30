"""Instrumental phrases must not become the direct target of a door action."""
import copy,json,unittest
from pathlib import Path
import grounded_action
from unittest.mock import patch
from api.tests.test_campaign_api import ControlledVenueOllamaClient
from api.tests import test_intent_response_consistency as fixture
class InstrumentObjectTests(unittest.TestCase):
 def classify(self,words):
  return grounded_action._foreign_object(words.split(),len(words.split())-1,{},[])
 def test_instrument_does_not_replace_lock_object(self):
  for text in ['kilidi maymuncukla aciyorum','kilidi tel ile aciyorum','kilidi igneyle aciyorum']:
   with self.subTest(text=text):self.assertIsNone(self.classify(text))
 def test_instrument_does_not_hide_unowned_object(self):
  for text,expected in [('kitabi maymuncukla aciyorum','kitabi'),('dali hancerle kiriyorum','dali'),('zili telle caliyorum','zili'),('kitabi tel ile aciyorum','kitabi')]:
   with self.subTest(text=text):self.assertEqual(self.classify(text),expected)
 def test_instrument_without_object_is_not_permission_for_nearest_door(self):
  self.assertEqual(self.classify('maymuncukla aciyorum'),'maymuncukla')
class InstrumentHttpTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  await fixture.IntentResponseConsistencyTests.asyncSetUp(self)
  await self.turn('Çevreme bakıyorum.')
  self.place=grounded_action._create_venue(grounded_action._Run(self.session,'fixture'),self.world['location'],name='Orryn Hanı',kind='tavern',noun='han',provenance={'kind':'synthetic_verification_setup'})
  self.door_id='venue-door:'+self.place['id'];next(d for d in self.world['doors']if d['id']==self.door_id).update(locked=True,open=False,broken=False)
 def protected(self):return copy.deepcopy((self.world['doors'],self.world['inventory'],self.session.rng.getstate(),self.world['location'],self.session.character))
 async def asyncTearDown(self):await fixture.IntentResponseConsistencyTests.asyncTearDown(self)
 async def turn(self,m,**kw):return await fixture.IntentResponseConsistencyTests.turn(self,m,**kw)
 async def test_three_owner_phrasings_reach_existing_tool_check_without_model(self):
  for text in ['Kilidi maymuncukla açmayı deniyorum','Han kapısı kilidi maymuncukla açmayı deniyorum','Orryn Hanı Kapısının kilidini maymuncukla açmayı deniyorum']:
   with self.subTest(text=text):
    before=self.protected();calls=self.client.calls;out=await self.turn(text,interaction_mode='do')
    self.assertIn('Elinde maymuncuk',out['narration']);self.assertEqual(before,self.protected());self.assertEqual(calls,self.client.calls)
 async def test_real_tools_use_mechanical_check_without_model(self):
  self.world['inventory'].append({'item_id':'item_test_tools','name':"Thieves' Tools"})
  before=self.session.rng.getstate();calls=self.client.calls
  out=await self.turn('Orryn Hanı Kapısının kilidini maymuncukla açmayı deniyorum',interaction_mode='do')
  self.assertNotEqual(before,self.session.rng.getstate());self.assertEqual(calls,self.client.calls);self.assertNotIn('Hangisini kastediyorsun',out['narration'])
 async def test_negated_attempt_does_not_roll_or_open(self):
  self.world['inventory'].append({'item_id':'item_test_tools','name':"Thieves' Tools"});before=self.protected()
  with patch.object(self.app.state.ollama_adapter,'_client',ControlledVenueOllamaClient(intent='narrative')):
   out=await self.turn('Orryn Hanı Kapısının kilidini maymuncukla açmayı denemiyorum',interaction_mode='do')
  self.assertEqual(before,self.protected());self.assertFalse(next(d for d in self.world['doors']if d['id']==self.door_id)['open'])
if __name__ == '__main__':
 unittest.main()
