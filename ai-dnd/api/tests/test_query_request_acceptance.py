"""Job5: same model query label, original Turkish input authority."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch
import game
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_npc_transcript_replay_baseline import QwenShapedModel

RAW = dict(intent='query', action='query', query_type='location', target=dict(type='none', reference=''), completion='unclear', confidence=1.0)

class QueryRequestAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def test_fixed_query_label_information_and_statement_gate(self):
        _, _, session, _, _ = await self.campaign_with_npc(experimental=False)
        for message, expected in (
            ('Neredeyim', True), ('Han nerede', True),
            ('Bana bulunduğum yeri söyle', True),
            ('Lütfen bulunduğum yeri söyleyin', True),
            ('Tamam, o zaman gideyim.', False),
            ('Muhafız duruyor.', False), ('Mutlu hissediyorum.', False),
            ('Mirasımı düşünüyorum.', False),
            ('Bulunduğum yeri söyleme.', False),
            ('Han açıksa oraya giderim.', False), ('Hana gitmiyorum.', False),
        ):
            with self.subTest(message=message):
                before = copy.deepcopy(session.world_state)
                normalized = session.normalize_intent(copy.deepcopy(RAW), message)
                result = session.validate_intent(normalized, message)
                print('QUERY_GATE', json.dumps(dict(input=message, raw=RAW, normalized=normalized, result=result),ensure_ascii=False))
                self.assertEqual(result.get('query_type') == 'location', expected)
                self.assertEqual(session.world_state, before)

    async def test_public_location_information_without_question_mark(self):
        for mode in ('do','ask_dm'):
            for message in ('Neredeyim', 'Bana bulunduğum yeri söyle'):
                with self.subTest(mode=mode, message=message):
                    _, _, session, url, npc = await self.campaign_with_npc(experimental=False)
                    model = QwenShapedModel('Sokak sessiz.',fault='clean',intent='query',query_type='location')
                    before = copy.deepcopy((session.character, session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))
                    response = await api.CampaignApiTests.post_scene_turn(self,url,model,dict(message=message,interaction_mode=mode,action_id=str(uuid.uuid4())))
                    print('QUERY_API',json.dumps(dict(input=message,mode=mode,http=response.status_code,body=response.json(),calls=model.calls),ensure_ascii=False,default=str))
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertIn('Neverwinter',response.json()['narration'])
                    self.assertEqual(before,(session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))

    async def test_same_location_label_cannot_turn_npc_departure_into_location_answer(self):
        for mode in (None,'do','say'):
            with self.subTest(mode=mode):
                _, _, session, url, npc = await self.campaign_with_npc(experimental=False)
                intro = speech.ScriptedNpcSpeechClient('Unused')
                await api.CampaignApiTests.post_scene_turn(self,url,intro,dict(message='Adın ne?',target_id=npc['id']))
                model = QwenShapedModel('İyi yolculuklar.',fault='clean',intent='query',query_type='location')
                fields = {} if mode is None else dict(interaction_mode=mode)
                before=copy.deepcopy((session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))
                response=await api.CampaignApiTests.post_scene_turn(self,url,model,dict(message='Tamam, o zaman gideyim.',action_id=str(uuid.uuid4()),**fields))
                self.assertEqual(response.status_code,200,response.text)
                self.assertNotIn('Bulunduğun yer',response.json()['narration'])
                self.assertEqual(before,(session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))

    async def test_registered_venue_question_without_punctuation(self):
        for mode in ('do','ask_dm'):
            with self.subTest(mode=mode):
                city, _, session, url, npc = await self.campaign_with_npc(experimental=False)
                venue = next(v for v in session.world_state['locations'].values() if v.get('scene_kind') == 'tavern')
                message = venue['name'] + ' nerede'
                model = QwenShapedModel('Sokak sessiz.', fault='clean', intent='query',query_type='location')
                before=copy.deepcopy((session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))
                response=await api.CampaignApiTests.post_scene_turn(self,url,model,dict(message=message,interaction_mode=mode,action_id=str(uuid.uuid4())))
                print('VENUE_QUERY',json.dumps(dict(input=message,mode=mode,http=response.status_code,body=response.json(),calls=model.calls),ensure_ascii=False,default=str))
                self.assertEqual(response.status_code,200,response.text)
                self.assertIn(venue['name'],response.json()['narration'])
                self.assertNotEqual(response.json()['narration'],'Bulunduğun yer: Neverwinter.')
                self.assertEqual(before,(session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))

    async def test_conditional_and_negative_travel_do_not_move_from_query_label(self):
        for message in ('Han açıksa oraya giderim.', 'Hana gitmiyorum.'):
            with self.subTest(message=message):
                _,_,session,url,_=await self.campaign_with_npc(experimental=False)
                model=QwenShapedModel('Sokak sessiz.',fault='clean',intent='query',query_type='location')
                before=copy.deepcopy((session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))
                response=await api.CampaignApiTests.post_scene_turn(self,url,model,dict(message=message,interaction_mode='do',action_id=str(uuid.uuid4())))
                self.assertEqual(response.status_code,200,response.text)
                self.assertNotIn('Bulunduğun yer',response.json()['narration'])
                self.assertEqual(before,(session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))

    async def test_location_information_say_keeps_attributed_npc_speech(self):
        _,_,session,url,npc=await self.campaign_with_npc(experimental=False)
        client=speech.ScriptedNpcSpeechClient('Neverwinter şehrindesin.')
        response=await api.CampaignApiTests.post_scene_turn(self,url,client,dict(message='Bana bulunduğum yeri söyle',interaction_mode='say',target_id=npc['id'],action_id=str(uuid.uuid4())))
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['narration'].startswith(npc['name']))
        self.assertIn(client.narration,response.json()['narration'])
        self.assertEqual(client.chat_calls,1)
        self.assertEqual(client.schemas[0]['required'],['spoken_text','stage_direction'])

    async def test_new_native_venue_query_does_not_disclose_hidden_place(self):
        _,_,session,url,_=await self.campaign_with_npc(experimental=False)
        venue=next(v for v in session.world_state['locations'].values() if v.get('scene_kind')=='tavern')
        venue['hidden']=True
        venue['description']='HIDDEN_VENUE_DETAIL'
        before=copy.deepcopy((session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))
        model=QwenShapedModel('Sokak sessiz.',fault='clean',intent='query',query_type='location')
        response=await api.CampaignApiTests.post_scene_turn(self,url,model,dict(message=venue['name']+' nerede',interaction_mode='ask_dm',action_id=str(uuid.uuid4())))
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(venue['name'],response.json()['narration'])
        self.assertNotEqual(response.json()['turn_outcome']['status'],'answered_from_campaign_state')
        self.assertTrue(session.world_state['locations'][venue['id']]['hidden'])
        self.assertEqual(before,(session.character,session.world_state['inventory'],session.world_state['location'],session.world_state['doors'],session.rng.getstate()))
