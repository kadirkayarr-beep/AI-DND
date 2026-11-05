"""Desired economic-purpose behavior over the real HTTP/game path; scripted reading only."""
import copy
from dataclasses import replace
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems
from api.tests.journeys.schema import load_scenario

class RoomPurposeRouting(JourneyCase):
    def _body(self, session_id, step):
        body = super()._body(session_id, step)
        if getattr(self, 'typed', False):
            body.update(interaction_mode='say', target_id='barman')
        return body

    async def run_purpose(self, text, purpose, *, coin=50, typed=False, person='barman', extra=None, expect=None):
        self.typed = typed
        source = load_scenario(SCENARIO_DIR / '18_room_phrase_not_job.json')
        front = {'kind':'speak_to','person_id':person,'coin_cp':coin,'economic_intent':purpose, **(extra or {})}
        if purpose == '__missing__':
            front.pop('economic_intent')
        wanted = {'kese':100,'saat':0,'oda':False, **(expect or {})}
        step = replace(source.steps[0], say=text, script={'front':front}, expect=wanted, known_broken=(), broken_because=())
        results = await self.run_scenario(replace(source, steps=(step,)))
        self.assertEqual(describe_problems(results), [])
        return self.manager.get(self.last_session_id).game_session

    async def test_payment_request_uses_room_owner_and_engine_price(self):
        s = await self.run_purpose('Oda için beş gümüş ödüyorum','room',extra={'room_price_cp':1},expect={'kart':{'max_total_cp':50,'kalemler':['Oda (bir gece)']}})
        self.assertEqual(s.world_state['currency']['player'],100)

    async def test_compound_gift_mentions_room_but_stays_gift(self):
        await self.run_purpose('Oda hakkında konuşup barmene 5 bakır bahşiş veriyorum','gift',coin=5,expect={'kart':{'max_total_cp':5,'kalemler':['Hediye']}})

    async def test_typed_room_request_binds_the_explicit_actor(self):
        await self.run_purpose('Bir gecelik yer ayırır mısın','room',coin=0,typed=True,expect={'kart':{'max_total_cp':50,'counterparty_label':'Marek','kalemler':['Oda (bir gece)']}})

    async def test_price_question_opens_no_card(self):
        await self.run_purpose('Gecelik fiyat nedir','room_quote',coin=0,typed=True,expect={'kart':None})

    async def test_mismatched_typed_recipient_cannot_open_a_card(self):
        await self.run_purpose('Oda için beş gümüş ödüyorum','room',typed=True,person='not-listed',expect={'kart':None,'savas':False})

    async def test_typed_economic_read_cannot_turn_into_a_strike(self):
        await self.run_purpose('Bir gecelik yer ayırır mısın','room',typed=True,extra={'kind':'attempt','strike_to':'barman'},expect={'kart':None,'savas':False})

    async def test_tip_amount_comes_from_words_not_model_figure(self):
        await self.run_purpose('Barmene beş bakır veriyorum','tip',coin=500,expect={'kart':{'max_total_cp':5,'kalemler':['Bahşiş']}})


    async def test_economic_purpose_does_not_leak_into_next_typed_turn(self):
        self.typed = True
        source = load_scenario(SCENARIO_DIR / '18_room_phrase_not_job.json')
        first = replace(source.steps[0], say='Bir gecelik yer ayır', script={'front':{'kind':'speak_to','person_id':'barman','economic_intent':'room'}}, expect={'kese':100,'kart':{'max_total_cp':50}}, known_broken=(), broken_because=())
        second = replace(first, say='Selam', script={'front':{'kind':'attempt','economic_intent':'none'}})
        results = await self.run_scenario(replace(source,steps=(first,second)))
        self.assertEqual(describe_problems(results), [])
        offers = self.manager.get(self.last_session_id).game_session.world_state['flags']['economic_offers']
        self.assertEqual(len(offers),1,'a normal next line must not replay the previous purpose')


    async def test_explicit_no_economic_intent_cannot_fall_back_to_room_or_gift(self):
        await self.run_purpose('Oda hakkında konuşup barmene 5 bakır bahşiş veriyorum','none',coin=5,expect={'kart':None})

    async def test_unknown_purpose_cannot_fall_back_to_a_room(self):
        await self.run_purpose('Bir oda ver','unsupported',coin=50,expect={'kart':None})

    async def test_quoted_room_payment_with_no_intent_opens_nothing(self):
        await self.run_purpose('Kervancı "oda tutuyorum, beş bakır veriyorum" dedi','none',coin=50,expect={'kart':None})


    async def counter_tender(self, typed):
        self.typed = typed
        source = load_scenario(SCENARIO_DIR / '02_beer_tip.json')
        first = replace(source.steps[0],known_broken=(),broken_because=())
        second = replace(source.steps[1],script={'front':{'kind':'speak_to','person_id':'barman','economic_intent':'purchase','coin_cp':5}},expect={'kese':100,'kart':None},known_broken=(),broken_because=())
        results = await self.run_scenario(replace(source,steps=(first,second)))
        self.assertEqual(describe_problems(results),[])
        session = self.manager.get(self.last_session_id).game_session
        self.assertEqual(session.world_state['flags']['counter_offer_v1'].get('tender_cp'),5)
        self.assertEqual(session.world_state['flags'].get('economic_offers',{}),{})

    async def test_purchase_read_preserves_existing_counter_tender(self):
        await self.counter_tender(False)

    async def test_typed_purchase_read_preserves_existing_counter_tender(self):
        await self.counter_tender(True)


    async def test_missing_purpose_cannot_guess_a_room_or_gift(self):
        await self.run_purpose('Oda hakkında konuşup barmene 5 bakır bahşiş veriyorum','__missing__',coin=5,expect={'kart':None})

    async def test_null_purpose_cannot_guess_a_room_or_gift(self):
        await self.run_purpose('Oda hakkında konuşup barmene 5 bakır bahşiş veriyorum',None,coin=5,expect={'kart':None})


from unittest.mock import patch
import bold_acts
import world_reactions
from api.tests.test_economic_room import Counter

class EconomicPurposeOwnerControls(Counter):
    def test_open_counter_offer_keeps_tender_in_its_existing_owner(self):
        bold_acts._open_offer(self.s, self.npc('barman'), 'bira')
        before = self.money()
        self.s._front_coin = 5
        result = self.s._front_economic_offer({'kind':'economic','id':'barman','purpose':'tip','valid':True}, 'Beş bakır bırakıyorum')
        self.assertEqual(result['action_result']['action'], 'shop_offer')
        self.assertEqual(self.w['flags']['counter_offer_v1']['tender_cp'], 5)
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)

    def test_prepare_refusal_is_not_projected_as_success(self):
        self.s._front_coin = 5
        before = self.money()
        with patch.object(world_reactions, 'refuses', return_value=True):
            result = self.s._front_economic_offer({'kind':'economic','id':'barman','purpose':'gift','valid':True}, 'Beş bakır veriyorum')
        self.assertEqual(result['action_result']['status'], 'refused')
        self.assertEqual(result['action_result']['reason_code'], 'npc_refuses')
        self.assertFalse(result['action_result']['success'])
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)

    def test_non_counter_server_cannot_fall_back_to_the_first_server(self):
        self.w['npcs'].append({'id':'other-server','name':'Rolan','role':'Barmen','location':self.here,'current_hp':10})
        self.s._front_coin = 50
        before = self.money()
        result = self.s._front_economic_offer({'kind':'economic','id':'other-server','purpose':'room','valid':True}, 'Bir gecelik yer ayır')
        # The existing room engine authorizes only the current counter vendor; do not relax it for binding.
        self.assertEqual(result['action_result']['status'], 'clarification')
        self.assertEqual(result['action_result']['reason_code'], 'shop_unavailable')
        self.assertEqual(self.prepared(), [])
        self.assertEqual(self.money(), before)

    def test_gift_uses_second_valid_actor_without_substituting_the_first(self):
        self.w['npcs'].append({'id':'other-person','name':'Rolan','role':'Yolcu','location':self.here,'current_hp':10})
        self.s._front_coin = 5
        before = self.money()
        result = self.s._front_economic_offer({'kind':'economic','id':'other-person','purpose':'gift','valid':True}, 'Beş bakır veriyorum')
        self.assertEqual(result['action_result']['status'], 'prepared')
        [offer] = self.prepared()
        self.assertEqual(offer['proposal']['recipient_id'], 'other-person')
        self.assertEqual(offer['lines'][0]['total_cp'], 5)
        self.assertEqual(self.money(),before)

    def test_combat_quote_and_held_room_cannot_advance_the_turn(self):
        self.w['combat'] = {'active':True}
        self.w['flags']['inn_room'] = {'place':self.here,'until':999999999}
        for purpose in ['room_quote','room']:
            with self.subTest(purpose=purpose):
                before = self.money()
                turn = self.w['flags']['turn_index']
                result = self.s._front_economic_offer({'kind':'economic','id':'barman','purpose':purpose,'valid':True}, 'Oda')
                self.assertEqual(result['action_result']['reason_code'],'combat_active')
                self.assertFalse(result['action_result']['success'])
                self.assertEqual(self.w['flags']['turn_index'],turn)
                self.assertEqual(self.money(),before)

    def test_boolean_coin_cannot_prepare_a_tip_or_hide_clarification(self):
        self.s._front_coin = True
        before = self.money()
        result = self.s._front_economic_offer({'kind':'economic','id':'barman','purpose':'tip','valid':True}, 'Bahşiş')
        self.assertEqual(result['action_result']['status'],'clarification')
        self.assertFalse(result['action_result']['success'])
        self.assertEqual(self.prepared(),[])
        self.assertEqual(self.money(),before)


    def test_room_quote_refusal_preserves_failure_status(self):
        with patch.object(world_reactions,'refuses',return_value=True):
            result = self.s._front_economic_offer({'kind':'economic','id':'barman','purpose':'room_quote','valid':True}, 'Fiyat nedir')
        self.assertEqual(result['action_result']['status'],'refused')
        self.assertFalse(result['action_result']['success'])
        self.assertEqual(result['action_result']['reason_code'],'npc_refuses')

    def test_invalid_recipient_clarification_is_not_success(self):
        result = self.s._front_economic_offer({'kind':'economic','id':'missing','purpose':None,'valid':False}, 'Oda')
        self.assertEqual(result['action_result']['status'],'clarification')
        self.assertFalse(result['action_result']['success'])
        self.assertEqual(result['action_result']['reason_code'],'npc_unknown')


    def test_purchase_cannot_use_a_different_vendor_from_current_counter(self):
        self.w['npcs'].append({'id':'other-server','name':'Rolan','role':'Barmen','location':self.here,'current_hp':10})
        self.s._front_coin = 5
        before = self.money()
        result = self.s._front_economic_offer({'kind':'economic','id':'other-server','purpose':'purchase','valid':True}, 'Bir bira alayım, beş bakır')
        self.assertIsNotNone(result,'an unauthorized counter recipient must not enter unbound legacy routing')
        self.assertEqual(result['action_result']['reason_code'],'shop_unavailable')
        self.assertFalse(result['action_result']['success'])
        self.assertEqual(self.prepared(),[])
        self.assertNotIn('counter_offer_v1',self.w['flags'])
        self.assertEqual(self.money(),before)

    def test_inactive_room_actor_cannot_quote_or_reuse_a_room_right(self):
        self.npc('barman').update(current_hp=0,combat_status='unconscious')
        self.w['flags']['inn_room']={'place':self.here,'until':999999999}
        for purpose in ['room_quote','room']:
            with self.subTest(purpose=purpose):
                before=self.money()
                turn=self.w['flags']['turn_index']
                result=self.s._front_economic_offer({'kind':'economic','id':'barman','purpose':purpose,'valid':True},'Marek oda kaç para')
                self.assertFalse(result['action_result']['success'])
                self.assertEqual(self.w['flags']['turn_index'],turn)
                self.assertEqual(self.prepared(),[])
                self.assertEqual(self.money(),before)

    def test_economic_request_keeps_existing_confession_observation(self):
        import os
        import front_proposal
        from api.tests.journeys.runner import ScriptedClient
        client=ScriptedClient({'front':{'kind':'speak_to','person_id':'barman','economic_intent':'room'}})
        before=copy.deepcopy(self.w['currency'])
        with patch.dict(os.environ,{front_proposal.FLAG:'1'}), patch('game.ollama.chat',side_effect=client.chat):
            self.turn('Bir adamı öldürdüm, bir gecelik yer ayır')
        self.assertIn('front',client.kinds)
        self.assertEqual(client.unexpected,[])
        self.assertTrue(any('barman' in deed.get('told',[]) for deed in self.w['flags'].get('deeds',[])))
        self.assertEqual(self.w['currency'],before)


    def test_disabled_turn_does_not_skip_next_enabled_economic_read(self):
        import os
        import front_proposal
        from api.tests.journeys.runner import ScriptedClient
        with patch.dict(os.environ,{front_proposal.FLAG:'0'}):
            self.turn('bi oda tutayım')
        client=ScriptedClient({'front':{'kind':'speak_to','person_id':'barman','economic_intent':'gift','coin_cp':5}})
        with patch.dict(os.environ,{front_proposal.FLAG:'1'}),patch('game.ollama.chat',side_effect=client.chat):
            self.turn('Barmene beş bakır veriyorum')
        self.assertIn('front',client.kinds)
        [card]=self.prepared()
        self.assertEqual(card['proposal']['purpose'],'gift')
        self.assertEqual(card['proposal']['amount_cp'],5)


from api.tests.test_economic_bribe import Arrest, bribe_cards
import economic_actions as ea
import game

class EconomicPurposeBribeOwner(Arrest):
    def drive_owner(self, purpose):
        self.held(since=world_reactions.ARREST_PATIENCE + 3)
        before = copy.deepcopy(self.w['currency'])
        self.s._front_coin = 100
        result = self.s._front_economic_offer({'kind':'economic','id':'guard','purpose':purpose,'valid':True}, 'Bir altın uzatıyorum')
        self.assertIsNone(result,'the arrester retains its owner instead of generic gift preparation')
        self.assertEqual(self.offers(),{})
        token = game._ACTIVE_SESSION.set(self.s)
        try:
            world_reactions._settle_the_law(self.s,{'action_result':{}})
            self.assertFalse(self.fighting(),'only the first bribe pauses escalation')
            self.assertTrue(self.deed()['hold']['bribe_card_opened'])
            self.assertEqual(len(bribe_cards(self.w)),1)
            self.s._front_coin = 100
            self.assertIsNone(self.s._front_economic_offer({'kind':'economic','id':'guard','purpose':purpose,'valid':True}, 'Bir altın uzatıyorum'))
            with patch.object(ea,'prepare_from_turn',side_effect=AssertionError('no second card before arrest escalation')):
                world_reactions._settle_the_law(self.s,{'action_result':{}})
            self.assertTrue(self.fighting())
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(self.w['currency'],before)

    def test_guard_gift_keeps_first_and_repeat_bribe_ownership(self):
        self.drive_owner('gift')

    def test_guard_tip_keeps_first_and_repeat_bribe_ownership(self):
        self.drive_owner('tip')


from api.tests.test_economic_action_http import EconomicHttpFixture

class EconomicPurposeBribeHttp(EconomicHttpFixture):
    async def drive_http_owner(self,purpose):
        import os
        import uuid
        import front_proposal
        from api.tests.journeys.runner import ScriptedClient
        self.world['flags']['turn_index']=10
        self.hold_by_guard()
        self.save()
        client=ScriptedClient({'front':{'kind':'speak_to','person_id':'guard','economic_intent':purpose,'coin_cp':100}})
        before=copy.deepcopy(self.world['currency'])
        with patch.dict(os.environ,{front_proposal.FLAG:'1'}),patch.object(self.app.state.ollama_adapter,'_client',client):
            first=await self.post({'message':'Muhafıza bir altın uzatıyorum','action_id':str(uuid.uuid4())})
            self.assertEqual(first.status_code,200,first.text)
            self.assertFalse(self.world.get('combat',{}).get('active'))
            self.assertTrue(self.world['flags']['deeds'][-1]['hold']['bribe_card_opened'])
            self.assertEqual(len(bribe_cards(self.world)),1)
            self.assertEqual(self.world['currency'],before)
            second=await self.post({'message':'Muhafıza yine bir altın uzatıyorum','action_id':str(uuid.uuid4())})
            self.assertEqual(second.status_code,200,second.text)
            self.assertTrue(self.world.get('combat',{}).get('active'),second.text)
            self.assertEqual(self.world['currency'],before)
            self.assertEqual(len(bribe_cards(self.world)),1)
            self.assertEqual(next(iter(self.offers().values()))['status'],'cancelled')
        self.assertEqual(client.unexpected,[])

    async def test_gift_read_uses_the_real_http_law_owner(self):
        await self.drive_http_owner('gift')

    async def test_tip_read_uses_the_real_http_law_owner(self):
        await self.drive_http_owner('tip')
