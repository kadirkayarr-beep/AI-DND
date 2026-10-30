"""Job5 review: quotation, morphology and unique subject authority."""
import copy
import unittest
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech
from api.tests.test_query_request_acceptance import RAW

class QueryReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def test_quoted_reported_negative_conditional_information_commands(self):
        _,_,s,_,_=await self.campaign_with_npc(experimental=False)
        for message in ('“Bulunduğum yeri söyle” dedim.', 'Muhafıza "Bulunduğum yeri söyle" dedi.',
                        'Ona bulunduğum yeri söyle dedim.', 'Bulunduğum yeri söyleme.',
                        'Bulunduğum yeri söylersem giderim.', 'İstersen bulunduğum yeri söyle.'):
            with self.subTest(message=message):
                result=s.validate_intent(s.normalize_intent(copy.deepcopy(RAW),message),message)
                self.assertNotEqual(result.get('query_type'),'location')
        for message in ('Bana bulunduğum yeri söyle','Lütfen bulunduğum yeri söyleyin'):
            with self.subTest(positive=message):
                result=s.validate_intent(s.normalize_intent(copy.deepcopy(RAW),message),message)
                self.assertEqual(result.get('query_type'),'location')

    async def test_interrogative_particle_morphology_not_ordinary_words(self):
        _,_,s,_,_=await self.campaign_with_npc(experimental=False)
        for particle in ('misin','mıyım','mıdır','mıydı','mıymış','misiniz','mıyız','mıydınız','mıymışsınız','mıydım','mıymışım','mıydılar'):
            with self.subTest(particle=particle):
                text='Burada '+particle
                result=s.validate_intent(s.normalize_intent(copy.deepcopy(RAW),text),text)
                self.assertEqual(result.get('query_type'),'location')
        for text in ('Muhafız duruyor.','Mutlu hissediyorum.','Mirasımı düşünüyorum.'):
            with self.subTest(negative=text):
                result=s.validate_intent(s.normalize_intent(copy.deepcopy(RAW),text),text)
                self.assertNotEqual(result.get('query_type'),'location')

    async def test_location_answer_requires_one_public_subject(self):
        city,_,s,_,npc=await self.campaign_with_npc(experimental=False)
        venue=next(v for v in s.world_state['locations'].values() if v.get('scene_kind')=='tavern')
        other=copy.deepcopy(venue); other.update(id='review_second_place',name='İkinci Han',aliases=[])
        s.world_state['locations'][other['id']]=other
        before=copy.deepcopy(s.world_state)
        for text in (venue['name']+' ve İkinci Han nerede','Kayıtsız Kule nerede',npc['name']+' nerede'):
            with self.subTest(text=text):
                self.assertIsNone(s._handle_query(text,'location',npc))
        self.assertEqual(s.world_state,before)
        venue['hidden']=True
        before=copy.deepcopy(s.world_state)
        self.assertIsNone(s._handle_query(venue['name']+' nerede','location',npc))
        self.assertEqual(s.world_state,before)

    async def test_player_text_wins_conflicting_model_location_target(self):
        city,_,s,_,_=await self.campaign_with_npc(experimental=False)
        venue=next(v for v in s.world_state['locations'].values() if v.get('scene_kind')=='tavern')
        raw=copy.deepcopy(RAW); raw['target']=dict(type='location',reference='Kayıtsız Kule')
        text=venue['name']+' nerede'
        before=copy.deepcopy(s.world_state)
        result=s.execute_intent(s.validate_intent(s.normalize_intent(raw,text),text),text)
        self.assertIn(venue['name'],result['direct_response'])
        self.assertNotIn('Kayıtsız Kule',result['direct_response'])
        self.assertEqual(s.world_state,before)
