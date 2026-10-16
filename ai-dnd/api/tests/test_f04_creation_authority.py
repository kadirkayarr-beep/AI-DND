"""Synthetic F04 AC002 authority checks; no live inference or campaign data."""
import copy
import json
import unittest
from unittest.mock import patch
import game
import living_world
from api.tests.test_stage10a_gameplay_repairs import city_session as _city_session, DISCLOSURE
from api.tests import test_explicit_shop_creation as shop_tests
from api.persistence.campaign_models import CampaignStorageError
import uuid

def city_session():
    import scheduled_events
    s=_city_session()
    s.world_state.setdefault('scheduled_events', [])
    return s

FIND='Bu bölgede yerel bir tüccar bul.'
CREATE='Bu kampanya için burada yerel bir dükkân ve tüccar oluştur.'

def stable(s):
    w=s.world_state
    scene=w.get('scene_state',{})
    return copy.deepcopy({'npcs':w.get('npcs',[]),'shops':w.get('shops',[]),'inventory':w.get('inventory'),
        'locations':w.get('locations',{}),'doors':w.get('doors',[]),'features':w.get('features',[]),
        'materialized_scenes':{key:value for key,value in scene.get('scenes',{}).items()
                               if isinstance(value,dict) and value.get('materialized')},
        'rng':s.rng.getstate(),'events':scene.get('ambient_event_history',[]),'counts':scene.get('ambient_event_counts',{}),
        'currency':w.get('currency'),'quests':w.get('quests'),'processed_quest_events':w.get('quest_processed_event_ids'),
        'world_events':w.get('events'),'scheduled_events':w.get('scheduled_events')})

class CreationAuthorityTests(unittest.TestCase):
    def test_exact_find_empty_city_is_read_only_model0(self):
        s=city_session();before=stable(s)
        with patch('game.ollama.chat',side_effect=AssertionError('provider forbidden')) as model:
            result=s.run_player_turn(FIND)
        self.assertEqual(model.call_count,0)
        self.assertEqual(stable(s),before)
        self.assertEqual(result['action_result']['status'],'unavailable')

    def test_passive_planning_does_not_materialize_scene(self):
        adversarial = (
            "Etrafımda neler var diye bakarken kim olduğunu merak edip "
            "çevreyi gözlemliyorum."
        )
        self.assertIsNone(living_world.affirmative_scene_intent(adversarial))
        quoted_report = 'Önceki anlatıda "etrafımda neler var gözlemliyorum" yazıyordu.'
        denied_report = "Etrafımda neler var gözlemliyorum demedim."
        for message in (quoted_report, denied_report):
            with self.subTest(message=message):
                self.assertIsNone(living_world.affirmative_scene_intent(message))
        cases=[('Burada kim var?',None),('Etrafımda neler var?',None),('Tüccar var mı?',None),
            (adversarial,None),
            (quoted_report,None),(denied_report,None),
            ('Daha önce etrafımda neler olduğunu gözlemlemiştim.',None),
            ('Muhafız nerede?',None),('Yolcu hakkında ne biliyorum?',None),
            ('Muhafıza yaklaşmıyorum.',None),('Etrafıma bakmıyorum.',None),
            ('Etrafıma bakma.',None),('Bir tüccar aramıyorum.',None),
            ('Burada tüccar oluşturma.',None),('Muhafız', 'say'),('Etrafıma bakıyorum.','ask_dm')]
        for message,mode in cases:
            with self.subTest(message=message,mode=mode):
                s=city_session();before=stable(s)
                s.plan_living_world_turn(message,interaction_mode=mode)
                self.assertEqual(stable(s),before)

    def test_explicit_observation_still_materializes_real_scene(self):
        s=city_session()
        observation = "Şehirde dolanırken etrafımda neler var gözlemliyorum."
        intent = living_world.affirmative_scene_intent(observation)
        self.assertIsNotNone(intent)
        self.assertEqual(intent[0], "look")
        with patch('game.ollama.chat',side_effect=AssertionError('no inference')) as model:
            s.run_player_turn(observation)
        self.assertEqual(model.call_count,0)
        self.assertGreaterEqual(len(s.world_state['npcs']),2)
        self.assertTrue(s.world_state['scene_state']['scenes']['fr:city:neverwinter']['materialized'])
        self.assertTrue(s.world_state['scene_state']['ambient_event_history'])
        self.assertEqual(s.world_state['shops'],[])

    def test_mixed_question_or_negative_keeps_separate_explicit_observation(self):
        for message in ['Etrafıma bakıyorum. Burada kim var?',
                        'Yolcuya yaklaşmıyorum. Etrafıma bakıyorum.']:
            with self.subTest(message=message):
                session=city_session()
                session.plan_living_world_turn(message)
                self.assertGreaterEqual(len(session.world_state['npcs']),2)
                self.assertEqual(session.world_state['shops'],[])

    def test_find_then_explicit_create_then_disclosure_targets_created_owner(self):
        s=city_session()
        with patch('game.ollama.chat',side_effect=AssertionError('find needs no model')):
            s.run_player_turn(FIND)
        packet={'narration':'Burada küçük bir yerel dükkân var; başında bir dükkâncı duruyor.','world_updates':{},'lore_claims':[]}
        with patch('game.ollama.chat',return_value={'message':{'content':json.dumps(packet)}}):
            created=s.run_player_turn(CREATE)
        self.assertEqual(created['action_result']['status'],'created')
        self.assertEqual(len(s.world_state['shops']),1)
        shop=s.world_state['shops'][0]
        npc=next(n for n in s.world_state['npcs'] if n['id']==shop['shopkeeper_id'])
        self.assertEqual(npc['shop_id'],shop['id'])
        before_shop=copy.deepcopy(s.world_state['shops'])
        with patch('game.ollama.chat',side_effect=AssertionError('disclosure needs no model')) as model:
            disclosure=s.run_player_turn(DISCLOSURE,target_id=npc['id'],interaction_mode='say')
        self.assertEqual(model.call_count,0)
        self.assertEqual(s.world_state['shops'],before_shop)
        self.assertIn('Arven',json.dumps(npc,ensure_ascii=False))
        self.assertNotEqual(disclosure['action_result'].get('status'),'invalid_target')

    def test_existing_merchant_search_reuses_without_events_rng_or_new_ids(self):
        import shop_creation
        s=city_session();shop_creation.resolve_explicit_request(s);before=stable(s)
        with patch('game.ollama.chat',side_effect=AssertionError('no inference')) as model:
            r=s.run_player_turn(FIND)
        self.assertEqual(model.call_count,0);self.assertEqual(stable(s),before)
        self.assertEqual(r['action_result']['status'],'found')

    def test_passive_reference_does_not_promote_but_explicit_approach_does(self):
        for message in ['Yolcu','Yolcu kim?','Yolcu hakkında ne biliyorum?','Yolcuya yaklaşmıyorum.','Yolcuya saldırmıyorum.','Yolcuya seslenmiyorum.']:
            with self.subTest(message=message):
                s=city_session()
                ref=living_world.create_scene_referent(s.world_state,s.world_state['location'],0,description='Sentetik yolcu.',aliases=['yolcu'])
                s.plan_living_world_turn(message)
                self.assertEqual(s.world_state['npcs'],[])
                self.assertIsNone(ref['promoted_npc_id'])
        s=city_session()
        ref=living_world.create_scene_referent(s.world_state,s.world_state['location'],0,description='Sentetik yolcu.',aliases=['yolcu'])
        result=s.plan_living_world_turn('Yolcuya yaklaşıyorum. Adı ne?')
        self.assertIsNotNone(ref['promoted_npc_id'])
        self.assertEqual(result['direct_result']['status'],'completed')

    def test_declined_address_cannot_borrow_observation_or_wait_authority(self):
        for action in ['Bekliyorum.', 'Etrafıma bakıyorum.']:
            for clauses in [('Yolcuya seslenmiyorum.', action),
                            (action, 'Yolcuya seslenmiyorum.')]:
                with self.subTest(clauses=clauses):
                    session=city_session()
                    ref=living_world.create_scene_referent(
                        session.world_state,session.world_state['location'],0,
                        description='Sentetik yolcu.',aliases=['yolcu'])
                    result=session.plan_living_world_turn(' '.join(clauses))
                    self.assertIsNone(ref['promoted_npc_id'])
                    self.assertEqual(len(session.world_state['npcs']),2)
                    self.assertTrue(session.world_state['scene_state']['scenes'][session.world_state['location']]['materialized'])
                    self.assertEqual(session.world_state['shops'],[])
                    self.assertIsNotNone(result['direct_result'])

    def test_approach_binds_only_its_own_clause_target(self):
        for passive,active,expected in [
            ('Yolcu kim?', 'Muhafıza yaklaşıyorum.', 'guard'),
            ('Muhafız kim?', 'Yolcuya yaklaşıyorum.', 'traveler'),
            ('Yolcuya seslenmiyorum.', 'Muhafıza yaklaşıyorum.', 'guard'),
            ('Muhafıza seslenmiyorum.', 'Yolcuya yaklaşıyorum.', 'traveler'),
        ]:
            for clauses in [(passive,active),(active,passive)]:
                with self.subTest(clauses=clauses):
                    session=city_session()
                    ref=living_world.create_scene_referent(
                        session.world_state,session.world_state['location'],0,
                        description='Sentetik yolcu.',aliases=['yolcu'])
                    result=session.plan_living_world_turn(' '.join(clauses))
                    guard=next(n for n in session.world_state['npcs'] if n.get('role')=='Muhafız')
                    if expected=='traveler':
                        self.assertIsNotNone(ref['promoted_npc_id'])
                        target_id=ref['promoted_npc_id']
                        self.assertNotEqual(target_id,guard['id'])
                    else:
                        self.assertIsNone(ref['promoted_npc_id'])
                        target_id=guard['id']
                    self.assertEqual(result['direct_result']['action'],'approach')
                    self.assertEqual(result['direct_result']['target_id'],target_id)
                    self.assertEqual(session.world_state['shops'],[])


class SearchTransactionTests(shop_tests.ShopTransactionTests):
    async def test_empty_find_receipt_resume_and_no_downstream_quest(self):
        import scheduled_events
        session=self.record.game_session
        session.world_state.setdefault('scheduled_events', [])
        before=stable(session)
        extra=copy.deepcopy((self.record.journal,self.record.narrative_memory,self.record.lore_authority))
        body={'message':FIND,'action_id':str(uuid.uuid4())}
        response=await self.http.post(self.url,json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.model.chat.call_count,0)
        self.assertEqual(stable(session),before)
        self.assertEqual(self.record.journal,extra[0])
        self.assertEqual(self.record.lore_authority,extra[2])
        self.assertEqual(len(self.record.narrative_memory['recent_turns']),len(extra[1]['recent_turns'])+1)
        self.assertEqual(self.record.narrative_memory['recent_turns'][-1]['player'],FIND)
        persisted=self.store.get_campaign(self.created['campaign_id'])
        self.assertEqual(persisted.payload['engine_save']['world_state']['quests'],before['quests'])
        replay=await self.http.post(self.url,json=body)
        self.assertEqual(replay.json(),response.json());self.assertEqual(self.model.chat.call_count,0)
        self.assertEqual(self.store.get_campaign(self.created['campaign_id']).payload,persisted.payload)
        from api.session_manager import SessionManager
        reopened=SessionManager(campaign_store=self.store)
        sid,record,*_=reopened.resume_campaign(self.created['campaign_id'])
        self.assertEqual(stable(record.game_session),before)
        self.assertEqual(reopened.get_turn_action(record,body['action_id'])['response'],response.json())

    async def test_search_save_failure_restores_rng_event_history_and_no_receipt(self):
        session=self.record.game_session
        before=copy.deepcopy((session.serialize_game_state(),session.rng.getstate(),self.record.journal,self.record.narrative_memory,self.record.lore_authority))
        saved=self.store.get_campaign(self.created['campaign_id'])
        body={'message':FIND,'action_id':str(uuid.uuid4())}
        with patch.object(self.store,'save_campaign',side_effect=CampaignStorageError('synthetic failure')):
            response=await self.http.post(self.url,json=body)
        self.assertEqual(response.status_code,503)
        self.assertEqual((session.serialize_game_state(),session.rng.getstate(),self.record.journal,self.record.narrative_memory,self.record.lore_authority),before)
        self.assertEqual(self.store.get_campaign(self.created['campaign_id']).payload,saved.payload)
        self.assertIsNone(self.store.get_turn_action(self.created['campaign_id'],body['action_id']))
        self.assertEqual(self.model.chat.call_count,0)
        retry=await self.http.post(self.url,json=body)
        self.assertEqual(retry.status_code,200);self.assertEqual(session.world_state['shops'],[])
        self.assertEqual(session.world_state['quests'],[]);self.assertEqual(self.model.chat.call_count,0)

    async def test_exact_N04_N05_N06_chain_over_real_api(self):
        r=await self.http.post(self.url,json={'message':FIND,'action_id':str(uuid.uuid4())})
        self.assertEqual(r.status_code,200);self.assertEqual(self.model.chat.call_count,0)
        r=await self.http.post(self.url,json={'message':CREATE,'action_id':str(uuid.uuid4())})
        self.assertEqual(r.status_code,200)
        w=self.record.game_session.world_state
        self.assertEqual(len(w['shops']),1)
        shop=w['shops'][0];npc=next(n for n in w['npcs'] if n['id']==shop['shopkeeper_id'])
        self.assertEqual(npc['shop_id'],shop['id'])
        calls=self.model.chat.call_count
        r=await self.http.post(self.url,json={'message':DISCLOSURE,'interaction_mode':'say','target_id':npc['id'],'action_id':str(uuid.uuid4())})
        self.assertEqual(r.status_code,200);self.assertEqual(self.model.chat.call_count,calls)
        self.assertIn('Arven',json.dumps(npc,ensure_ascii=False))
        self.assertFalse(any(q.get('creation_evidence')=='found:'+npc['id'] for q in w['quests']))

if __name__=='__main__': unittest.main(verbosity=2)
