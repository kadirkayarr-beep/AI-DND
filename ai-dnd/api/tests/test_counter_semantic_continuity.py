"""Admitted purchase requests reach the native counter, never an automatic sale."""
import copy
from dataclasses import replace
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems
from api.tests.journeys.schema import load_scenario

class CounterSemanticContinuity(JourneyCase):
    def _body(self,session_id,step):
        body=super()._body(session_id,step)
        if getattr(self,'typed',False) and step.say is not None:
            body.update(interaction_mode='say',target_id='barman')
        return body

    async def test_polite_question_preserves_original_beer_journey_expectations(self):
        source=load_scenario(SCENARIO_DIR/'01_beer_chat.json')
        setup={**copy.deepcopy(source.setup),'front_proposal':True}
        steps=tuple(replace(s,script={'front':{'kind':'speak_to','person_id':'barman','economic_intent':'purchase'}} if s.say else s.script,known_broken=(),broken_because=()) for s in source.steps)
        results=await self.run_scenario(replace(source,setup=setup,steps=steps))
        self.assertEqual(describe_problems(results),[])

    async def run_request(self,text,*,typed=False,purpose='purchase',person='barman'):
        self.typed=typed
        source=load_scenario(SCENARIO_DIR/'01_beer_chat.json')
        setup={**copy.deepcopy(source.setup),'front_proposal':True}
        expected={'kese':100,'envanter':{},'kart':None,'kisi_kese':{'barman':0}}
        step=replace(source.steps[0],say=text,script={'front':{'kind':'speak_to','person_id':person,'economic_intent':purpose}},expect=expected,known_broken=(),broken_because=())
        results=await self.run_scenario(replace(source,setup=setup,steps=(step,)))
        self.assertEqual(describe_problems(results),[])
        return self.manager.get(self.last_session_id).game_session

    async def test_typed_polite_request_opens_engine_priced_offer_without_payment(self):
        s=await self.run_request('Bir bira alabilir miyim?',typed=True)
        offer=s.world_state['flags'].get('counter_offer_v1')
        self.assertIsNotNone(offer)
        self.assertEqual((offer['npc_id'],offer['key']),('barman','bira'))

    async def test_no_purchase_read_does_not_gain_the_new_question_admission(self):
        s=await self.run_request('Bir bira alabilir miyim?',purpose='none')
        self.assertFalse(s.world_state['flags'].get('counter_offer_v1'))

    async def test_unknown_catalog_product_opens_no_offer(self):
        s=await self.run_request('Bir yastik alabilir miyim?',typed=True)
        self.assertFalse(s.world_state['flags'].get('counter_offer_v1'))

    async def test_new_named_product_replaces_old_order_before_native_commit(self):
        source=load_scenario(SCENARIO_DIR/'02_beer_tip.json')
        first=replace(source.steps[0],script={'front':{'kind':'speak_to','person_id':'barman','economic_intent':'purchase'}},known_broken=(),broken_because=())
        second=replace(source.steps[1],say='Yemek icin 40 bakir koyuyorum',script={'front':{'kind':'speak_to','person_id':'barman','economic_intent':'purchase','coin_cp':40}},expect={'tezgah':{'npc_id':'barman','key':'yemek','unit_cp':30},'kese':100,'envanter':{},'kisi_kese':{'barman':0}},known_broken=(),broken_because=())
        last=replace(source.steps[1],say=None,command='/item shop_buy barman yemek 1 0 30',script={},expect={'kese':70,'envanter':{'Tabak yemek':1},'kisi_kese':{'barman':30}},known_broken=(),broken_because=())
        results=await self.run_scenario(replace(source,steps=(first,second,last)))
        self.assertEqual(describe_problems(results),[])
        s=self.manager.get(self.last_session_id).game_session
        self.assertEqual(s.world_state['flags']['counter_offer_v1']['tender_cp'],40)

    async def test_rejected_new_product_does_not_tender_the_previous_order(self):
        source=load_scenario(SCENARIO_DIR/'02_beer_tip.json')
        first=replace(source.steps[0],script={'front':{'kind':'speak_to','person_id':'barman','economic_intent':'purchase'}},known_broken=(),broken_because=())
        second=replace(source.steps[1],say='Yemek almaya gidiyorum, 40 bakir koyuyorum',script={'front':{'kind':'speak_to','person_id':'barman','economic_intent':'purchase','coin_cp':40}},expect={'kese':100,'envanter':{},'kisi_kese':{'barman':0}},known_broken=(),broken_because=())
        results=await self.run_scenario(replace(source,steps=(first,second)))
        self.assertEqual(describe_problems(results),[])
        s=self.manager.get(self.last_session_id).game_session
        opened=s.world_state['flags']['counter_offer_v1']
        self.assertEqual(opened['key'],'bira')
        self.assertNotIn('tender_cp',opened)
