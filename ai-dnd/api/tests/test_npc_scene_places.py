"""Public nearby places are bounded scene data, not keyword-triggered knowledge."""
import copy,json,unittest
from unittest.mock import patch
import living_world
class Projection(unittest.TestCase):
 def world(self):return {'location':'city','locations':{'city':{'name':'Şehir','type':'city'},'inn':{'name':'Alaca Hanı','parent_location_id':'city','scene_kind':'tavern','secret':'PRIVATE_SENTINEL'}},'npcs':[],'features':[],'doors':[]}
 def test_read_only_public_projection(self):
  w=self.world();before=copy.deepcopy(w);f=living_world.visible_scene_facts(w);self.assertEqual(w,before)
  self.assertEqual(f['nearby_places'],[{'id':'inn','name':'Alaca Hanı','kind':'tavern','access':'available'}]);self.assertNotIn('PRIVATE_SENTINEL',json.dumps(f))
 def test_hidden_distant_undiscovered_excluded(self):
  w=self.world()
  for name,extras in [('hidden',{'hidden':True}),('unseen',{'discovered':False}),('away',{'parent_location_id':'elsewhere'})]:w['locations'][name]={**w['locations']['inn'],'name':name,**extras}
  self.assertEqual([x['id']for x in living_world.visible_scene_facts(w)['nearby_places']],['inn'])
 def test_player_knowledge_is_respected(self):
  with patch('exploration.known_locations',return_value={'city'}):self.assertEqual(living_world.visible_scene_facts(self.world())['nearby_places'],[])
 def test_locked_not_visitable(self):
  w=self.world();w['doors']=[{'place_id':'inn','locked':True}];self.assertEqual(living_world.visible_scene_facts(w)['nearby_places'][0]['access'],'locked')
 def test_no_registered_local_place_is_not_a_fabricated_target(self):
  w=self.world();del w['locations']['inn']['parent_location_id'];self.assertEqual(living_world.visible_scene_facts(w)['nearby_places'],[])
 def test_bounded_stable_and_only_public_fields(self):
  w=self.world()
  for i in range(30):w['locations'][f'place{i:02}']={'name':'N'*120,'parent_location_id':'city','scene_kind':'tavern','private_notes':'secret'}
  a=living_world.visible_scene_facts(w)['nearby_places'];self.assertEqual(len(a),6);self.assertTrue(all(len(x['name'])<=80 for x in a));w['locations']=dict(reversed(list(w['locations'].items())));self.assertEqual(a,living_world.visible_scene_facts(w)['nearby_places'])

from api.tests import test_intent_response_consistency as fixture
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient

class NpcScenePlaceHttpTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):await fixture.IntentResponseConsistencyTests.asyncSetUp(self)
 async def asyncTearDown(self):await fixture.IntentResponseConsistencyTests.asyncTearDown(self)
 async def turn(self,message,**kw):return await fixture.IntentResponseConsistencyTests.turn(self,message,**kw)
 async def test_known_place_context_does_not_require_recommendation_keyword(self):
  await self.turn('Çevreme bakıyorum.')
  npc=self.world['npcs'][0];npc.update(name='Quenna',name_known_to_player=True)
  self.world['locations']['public_inn']={'id':'public_inn','name':'Alaca Hanı','type':'building','scene_kind':'tavern','parent_location_id':self.world['location'],'hidden':False}
  self.world['locations']['secret_inn']={'id':'secret_inn','name':'GizliMenekşe','type':'building','scene_kind':'tavern','parent_location_id':self.world['location'],'hidden':True}
  for message in ['Buralarda han varmı?','En yakın han nerede?','Gece nerede kalabilirim?','Bir han önerir misin?']:
   with self.subTest(message=message):
    client=ScriptedNpcSpeechClient('Bir hana bakabiliriz.')
    before=copy.deepcopy((self.world['location'],self.world['locations'],self.world['inventory']))
    with patch.dict('os.environ',{'AI_DND_NPC_SPEECH':'1'}),patch.object(self.app.state.ollama_adapter,'_client',client):
     await self.turn(message,target_id=npc['id'],interaction_mode='say')
    prompts='\n'.join(x.get('content','')for batch in client.message_batches for x in batch)
    self.assertEqual(client.chat_calls,1);self.assertIn('Alaca Hanı',prompts);self.assertNotIn('GizliMenekşe',prompts)
    self.assertEqual(before,(self.world['location'],self.world['locations'],self.world['inventory']))

if __name__ == '__main__':unittest.main()
