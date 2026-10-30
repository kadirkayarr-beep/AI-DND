import copy,json,unittest,uuid
from unittest.mock import patch
import npc_statements,grounded_action
from api.tests import test_dialogue_runtime as runtime_fixture
from api.persistence.campaign_models import CampaignStorageError

class DialoguePlaceTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=runtime_fixture.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=runtime_fixture.DialogueRuntimeTests.asyncTearDown
 setup_free=runtime_fixture.DialogueRuntimeTests.setup_free
 send=runtime_fixture.DialogueRuntimeTests.send
 async def setup_place(self):
  await self.setup_free();self.name='Gümüş Kılıç Hanı'
  self.reply.raw=json.dumps({'spoken_text':"Gümüş Kılıç Hanı burada, şehirde. Orada dinlenebilirsin.",'stage_direction':'','job_proposals':[],'place_proposals':[{'request_key':'inn','kind':'tavern','name':self.name,'settlement_id':self.world['location']}]},ensure_ascii=False)
 def matches(self):return [v for v in self.world['locations'].values() if v.get('name')==self.name]
 async def test_factual_place_reply_commits_real_full_name(self):
  await self.setup_place();r=await self.send('Buralarda bir han var mı?');self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(len(self.matches()),1);self.assertIn(self.name,r.json()['narration'])
  place=self.matches()[0];self.assertEqual(place['parent_location_id'],self.world['location']);self.assertEqual(place['exit_location_id'],self.world['location'])
  self.assertTrue(any(d['id']=='venue-door:'+place['id'] for d in self.world['doors']))
 async def test_same_named_place_is_reused_on_new_question(self):
  await self.setup_place()
  for _ in range(2):
   r=await self.send('Buralarda bir han var mı?');self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(len(self.matches()),1)
 async def test_action_replay_creates_once(self):
  await self.setup_place();aid=str(uuid.uuid4());a=await self.send('Buralarda bir han var mı?',action_id=aid);b=await self.send('Buralarda bir han var mı?',action_id=aid)
  self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json(),b.json());self.assertEqual(len(self.matches()),1);self.assertEqual(self.reply.calls,1)
 async def test_failed_autosave_rolls_back_place_and_dialogue(self):
  await self.setup_place();before=copy.deepcopy(self.session.serialize_game_state())
  with patch.object(self.manager,'autosave_turn',side_effect=CampaignStorageError('synthetic write failure')):r=await self.send('Buralarda bir han var mı?')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_cross_settlement_proposal_not_committed(self):
  await self.setup_place();raw=json.loads(self.reply.raw);raw['place_proposals'][0]['settlement_id']='not_here';self.reply.raw=json.dumps(raw)
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('Buralarda bir han var mı?')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_full_name_parser_does_not_drop_quoted_first_word(self):
  names=npc_statements._named_places("O büyük kule 'Gümüş Kılıç' Hanı olarak bilinir.")
  self.assertIn('Gümüş Kılıç Hanı',[x[0] for x in names]);self.assertNotIn('Kılıç Hanı',[x[0] for x in names])
 async def test_recommended_place_can_be_approached_through_http(self):
  await self.setup_place();a=await self.send('Buralarda bir han var mı?');self.assertEqual(a.status_code,200,a.text)
  place=self.matches()[0]
  await self.send('Konuşmayı bitiriyorum.',mode='do')
  r=await self.send('Gümüş Kılıç Hanına gidiyorum',mode='do');self.assertEqual(r.status_code,200,r.text)
  self.assertIn(self.name,r.json()['narration']);self.assertEqual(len(self.matches()),1)
  near=grounded_action.near_door_id(self.world)
  self.assertTrue(near=='venue-door:'+place['id'] or self.world['location']==place['id'],r.text)
 async def test_capacity_error_does_not_show_nonexistent_recommendation(self):
  await self.setup_place();settlement=self.world['location']
  for i in range(4):self.world['locations'][f'existing_{i}']={'id':f'existing_{i}','name':f'Existing{i} Hanı','parent_location_id':settlement,'scene_kind':'tavern','type':'building'}
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('Buralarda bir han var mı?')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state());self.assertFalse(self.matches())
 async def test_proposal_and_spoken_name_disagree_rolls_back(self):
  await self.setup_place();raw=json.loads(self.reply.raw);raw['spoken_text']='Başka Hanı yakında, oraya gidebilirsin.';self.reply.raw=json.dumps(raw,ensure_ascii=False)
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('Buralarda bir han var mı?')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_hidden_same_named_place_is_not_exposed(self):
  await self.setup_place();self.world['locations']['hidden_inn']={'id':'hidden_inn','name':self.name,'parent_location_id':self.world['location'],'hidden':True,'scene_kind':'tavern'}
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('Buralarda bir han var mı?')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
