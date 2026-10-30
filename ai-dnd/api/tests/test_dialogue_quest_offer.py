import copy,json,unittest,uuid
from unittest.mock import patch
import local_places
from api.tests import test_dialogue_runtime as base
from api.persistence.campaign_models import CampaignStorageError
class DialogueJobTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=base.DialogueRuntimeTests.asyncSetUp
 asyncTearDown=base.DialogueRuntimeTests.asyncTearDown
 setup_free=base.DialogueRuntimeTests.setup_free
 send=base.DialogueRuntimeTests.send
 async def setup_job(self,template='DELIVERY'):
  await self.setup_free();self.destination=local_places.create_local_place(self.world,self.world['location'],'archive',name='Kent Arşivi')
  self.receiver={'id':'npc_lia','name':'Lia','role':'Arşivci','location':self.destination['id'],'reality_layer':'PROCEDURAL_LOCAL_FICTION','name_known_to_player':True,'role_known_to_player':True}
  self.world['npcs'].append(self.receiver)
  self.proposal={'request_key':'delivery','template_id':template,'title':'Arşive teslimat','description':'Kent Arşivindeki Lia için bir paket var.','target_npc_id':self.receiver['id'],'location_id':self.destination['id']}
  self.reply.raw=json.dumps({'spoken_text':'Arşive teslimat işim var. İlgilenir misin?','stage_direction':'','place_proposals':[],'job_proposals':[self.proposal]},ensure_ascii=False)
 async def offer(self):
  r=await self.send('Burada iş bulabilir miyim?');self.assertEqual(r.status_code,200,r.text)
  qs=[q for q in self.world['quests'] if q.get('creation_evidence','').startswith('dialogue-job:')]
  self.assertEqual(len(qs),1);return qs[0]
 async def test_offer_is_real_but_not_accepted(self):
  await self.setup_job();q=await self.offer();self.assertEqual(q['status'],'DISCOVERED');self.assertIsNone(q['accepted_turn']);self.assertEqual(q['giver_npc_id'],self.npc['id'])
 async def test_duplicate_offer_reuses_quest(self):
  await self.setup_job();a=await self.offer();b=await self.offer();self.assertEqual(a['quest_id'],b['quest_id'])
 async def test_model_cannot_choose_reward_amount(self):
  await self.setup_job();raw=json.loads(self.reply.raw);raw['job_proposals'][0]['gold']=999999;self.reply.raw=json.dumps(raw)
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('İş var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_missing_recipient_rejected_before_commitment(self):
  await self.setup_job();raw=json.loads(self.reply.raw);raw['job_proposals'][0]['target_npc_id']='not-a-person';self.reply.raw=json.dumps(raw)
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('İş var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_offer_autosave_failure_rolls_back(self):
  await self.setup_job();before=copy.deepcopy(self.session.serialize_game_state())
  with patch.object(self.manager,'autosave_turn',side_effect=CampaignStorageError('synthetic')):r=await self.send('İş var mı?')
  self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_delivery_completes_through_real_http_actions_once(self):
  await self.setup_job();q=await self.offer();qid=q['quest_id'];self.reply.raw=None
  accept=await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{qid}/accept');self.assertEqual(accept.status_code,200,accept.text)
  gold=self.world.get('currency',{}).get('player',0)
  take=await self.send('Paketi alıyorum',mode='do');self.assertEqual(take.status_code,200,take.text)
  self.assertTrue(any(isinstance(i,dict) and i.get('item_id')=='parcel:'+qid for i in self.world['inventory']))
  travel=await self.send('Kent Arşivine gidiyorum',mode='do');self.assertEqual(travel.status_code,200,travel.text)
  self.assertEqual(self.world['location'],self.destination['id'])
  aid=str(uuid.uuid4());hand=await self.send('Paketi Lia adlı arşivciye teslim ediyorum',mode='do',action_id=aid);self.assertEqual(hand.status_code,200,hand.text)
  self.assertEqual(q['status'],'COMPLETED');self.assertIsNotNone(q['reward_application_id'])
  import relationships
  self.assertEqual(relationships.score(self.world,self.npc['id']),1)
  self.assertEqual(self.world['currency']['player'],gold+q['reward_plan']['success']['gold'])
  after=copy.deepcopy(self.session.serialize_game_state());again=await self.send('Paketi Lia adlı arşivciye teslim ediyorum',mode='do',action_id=aid)
  self.assertEqual(hand.json(),again.json());self.assertEqual(after,self.session.serialize_game_state())
 async def test_declining_offer_does_not_accept_it(self):
  await self.setup_job();q=await self.offer();self.reply.raw=None
  r=await self.send('Bu işi kabul etmiyorum.');self.assertEqual(r.status_code,200,r.text);self.assertEqual(q['status'],'DISCOVERED')
 async def test_blocked_destination_rejected(self):
  await self.setup_job();self.world['blocked_travel_routes']={self.world['location']:{self.destination['id']:True}}
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('İş var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_cancel_and_repeat_accept_do_not_give_parcel(self):
  await self.setup_job();q=await self.offer();url=f'/api/game/sessions/{self.session_id}/quests/{q["quest_id"]}'
  a=await self.http.post(url+'/accept');self.assertEqual(a.status_code,200,a.text)
  again=await self.http.post(url+'/accept');self.assertEqual(again.status_code,200,again.text)
  cancel=await self.http.post(url+'/cancel');self.assertEqual(cancel.status_code,200,cancel.text)
  self.assertFalse(any(isinstance(i,dict) and i.get('item_id')=='parcel:'+q['quest_id'] for i in self.world['inventory']))
 async def test_urban_investigation_real_chain(self):
  await self.setup_job('URBAN_INVESTIGATION');q=await self.offer();qid=q['quest_id'];self.reply.raw=None
  accept=await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{qid}/accept');self.assertEqual(accept.status_code,200,accept.text)
  heard=await self.send('Bu soruşturma hakkında ne biliyorsun?');self.assertEqual(heard.status_code,200,heard.text)
  self.assertEqual(q['objectives'][0]['graph_state'],'COMPLETE')
  moved=await self.send('Kent Arşivine gidiyorum',mode='do');self.assertEqual(moved.status_code,200,moved.text)
  import game
  with patch.object(game,'roll_d20',return_value=20):
   clue=await self.send('Görev için buradaki izleri araştırıyorum',mode='do')
  self.assertEqual(clue.status_code,200,clue.text);self.assertEqual(q['status'],'COMPLETED');self.assertIsNotNone(q['reward_application_id'])
 async def test_question_or_quoted_parcel_action_does_not_transfer(self):
  await self.setup_job();q=await self.offer();await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{q["quest_id"]}/accept');self.reply.raw=None
  for text in ('Paketi alıyorum?','“Paketi alıyorum”','Paketi almıyorum','Paketi aldığımı söyledim'):
   with self.subTest(text=text):
    before=copy.deepcopy(self.world['inventory']);r=await self.send(text,mode='do');self.assertEqual(r.status_code,200,r.text);self.assertEqual(before,self.world['inventory'])
 async def test_unnamed_delivery_uses_present_bound_recipient(self):
  await self.setup_job();q=await self.offer();await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{q["quest_id"]}/accept');self.reply.raw=None
  await self.send('Paketi alıyorum',mode='do');await self.send('Kent Arşivine gidiyorum',mode='do')
  r=await self.send('Paketi teslim ediyorum',mode='do');self.assertEqual(r.status_code,200,r.text);self.assertEqual(q['status'],'COMPLETED')
 async def test_incapacitated_player_cannot_investigate(self):
  await self.setup_job('URBAN_INVESTIGATION');q=await self.offer();await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{q["quest_id"]}/accept');self.reply.raw=None
  await self.send('Bu soruşturma hakkında ne biliyorsun?');await self.send('Kent Arşivine gidiyorum',mode='do')
  self.session.character['current_hp']=0
  before=copy.deepcopy(q)
  await self.send('Görev için buradaki izleri araştırıyorum',mode='do')
  self.assertEqual(before,q);self.assertIsNone(q['reward_application_id'])
 async def test_unobserved_remote_routine_target_not_in_context(self):
  await self.setup_job();self.world['scheduled_events']=[{'status':'OCCURRED','player_observed':False,'visibility':'hidden','effects':[{'kind':'npc_location','npc_id':'npc_lia','location_id':self.destination['id']}]}]
  import dialogue_runtime
  context=dialogue_runtime.build_context(self.world,self.npc,'İş var mı?')
  self.assertNotIn('npc_lia',json.dumps(context));self.assertNotIn('Lia',json.dumps(context))
 async def test_conflicting_reward_promise_rolls_back(self):
  await self.setup_job();raw=json.loads(self.reply.raw);raw['spoken_text']='Arşive teslimat işim var, sana 100 altın vereceğim.';self.reply.raw=json.dumps(raw,ensure_ascii=False)
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('İş var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_offer_card_uses_canonical_objectives_and_reward(self):
  await self.setup_job();r=await self.send('İş var mı?');self.assertEqual(r.status_code,200,r.text)
  self.assertIn('25 altın',r.json()['narration']);self.assertIn('Kent Arşivi',r.json()['narration']);self.assertIn('Lia',r.json()['narration'])
 async def test_model_flavor_cannot_add_objectives_or_rewards(self):
  await self.setup_job();raw=json.loads(self.reply.raw);raw['job_proposals'][0].update(title='Ejderhayı öldür, 999 altın kazan',description='Ejderhayı öldürünce 999 altın');raw['spoken_text']='Bir çift ele ihtiyacım var.';self.reply.raw=json.dumps(raw,ensure_ascii=False)
  r=await self.send('İş var mı?');self.assertEqual(r.status_code,200,r.text)
  self.assertNotIn('999',r.json()['narration']);self.assertNotIn('Ejderha',r.json()['narration'])
  q=next(q for q in self.world['quests'] if q.get('creation_evidence','').startswith('dialogue-job:'));self.assertNotIn('999',q['description']);self.assertNotIn('999',q['title'])
 async def test_existing_offer_followup_does_not_require_new_proposal(self):
  await self.setup_job();await self.offer();self.reply.raw=None;self.reply.spoken='Evet, bir iş var.'
  r=await self.send('Yani bir işin var mı?');self.assertEqual(r.status_code,200,r.text)
 async def test_active_job_card_does_not_ask_to_accept_again(self):
  await self.setup_job();q=await self.offer();await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{q["quest_id"]}/accept')
  r=await self.send('İşi tekrar anlat.');self.assertEqual(r.status_code,200,r.text);self.assertNotIn('kabul edebilirsin',r.json()['narration']);self.assertIn('Devam eden iş',r.json()['narration'])
 async def test_same_location_delivery_is_rejected_before_offer(self):
  await self.setup_job();self.receiver['location']=self.world['location'];raw=json.loads(self.reply.raw);raw['job_proposals'][0]['location_id']=self.world['location'];self.reply.raw=json.dumps(raw,ensure_ascii=False)
  before=copy.deepcopy(self.session.serialize_game_state());r=await self.send('İş var mı?');self.assertEqual(r.status_code,503,r.text);self.assertEqual(before,self.session.serialize_game_state())
 async def test_inside_venue_can_offer_real_city_recipient_in_context(self):
  await self.setup_job();city=self.world['location'];self.world['location']=self.destination['id'];self.npc['location']=self.destination['id'];self.receiver['location']=city
  import dialogue_runtime
  targets=dialogue_runtime.build_context(self.world,self.npc,'İş var mı?')['job_targets']
  self.assertIn({'npc_id':self.receiver['id'],'name':self.receiver['name'],'location_id':city},targets)
 async def test_delivery_before_road_objective_keeps_parcel(self):
  await self.setup_job();q=await self.offer();await self.http.post(f'/api/game/sessions/{self.session_id}/quests/{q["quest_id"]}/accept');self.reply.raw=None
  await self.send('Paketi alıyorum',mode='do');self.receiver['location']=self.world['location']
  before=copy.deepcopy(self.world['inventory']);r=await self.send('Paketi Lia adlı kişiye teslim ediyorum',mode='do')
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(before,self.world['inventory']);self.assertEqual(q['status'],'ACTIVE')
