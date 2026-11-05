"""#17: shown money-offer replies and later card confirmation share authorization."""
import copy
import json
from dataclasses import replace
from unittest.mock import patch
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, ScriptedClient, describe_problems
from api.tests.journeys.schema import load_scenario

class SpokenConsentHttp(JourneyCase):
    async def run_consent(self, response="__missing__", *, refuse=False, malformed=False):
        source=load_scenario(SCENARIO_DIR/'17_refused_gift_not_charged.json')
        steps=[replace(s,known_broken=(),broken_because=()) for s in source.steps]
        if refuse:
            steps=steps[:2]
            steps[1]=replace(steps[1],expect={'kese':100,'kart':None,'kisi_kese':{'caravaner':0}})
        elif response=='accept' and not malformed:
            steps[2]=replace(steps[2],expect={'kese':95,'kisi_kese':{'caravaner':5}})
        first_script=copy.deepcopy(steps[0].script)
        first_script['front']['economic_intent']='gift'
        if response=='accept' and not malformed:
            first_script['spoken']='Olur, hediyeni kabul ediyorum.'
        steps[0]=replace(steps[0],script=first_script)
        original=ScriptedClient.chat
        def chat(client,*args,**kwargs):
            result=original(client,*args,**kwargs)
            packet=json.loads(result['message']['content'])
            if 'spoken_text' in packet and response!='__missing__':
                packet['coin_response']=response
                if malformed:
                    packet['speaker_id']='another-person'
                result['message']['content']=json.dumps(packet,ensure_ascii=False)
            return result
        with patch.object(ScriptedClient,'chat',new=chat):
            results=await self.run_scenario(replace(source,steps=tuple(steps)))
        self.assertEqual(describe_problems(results),[])
        return self.manager.get(self.last_session_id).game_session

    async def test_validated_offer_without_semantic_reply_cannot_debit(self):
        s=await self.run_consent()
        [entry]=s.world_state['flags']['economic_ledger']['operations'].values()
        self.assertEqual(entry['net_debit_cp'],0)
        self.assertEqual(entry['reason_code'],'npc_consent_required')

    async def test_explicit_refusal_of_same_offer_prevents_new_tip_card(self):
        await self.run_consent('refuse',refuse=True)

    async def test_structured_acceptance_allows_same_recipient_tip(self):
        await self.run_consent('accept')

    async def test_unknown_response_cannot_authorize_debit(self):
        await self.run_consent('unsupported')

    async def test_model_injected_speaker_cannot_authorize_debit(self):
        await self.run_consent('accept',malformed=True)

from api.tests.test_economic_offer import OfferFixture, proposal
import economic_actions as ea
from api.core_resolution import resolution_action_scope

class RecordedConsent(OfferFixture):
    def response(self, npc='barman', amount=5, status='unknown'):
        next(n for n in self.w['npcs'] if n['id']==npc).setdefault('coin_responses',{})[str(amount)]=status

    def test_unknown_reply_card_cannot_apply_and_warns_may_refuse(self):
        self.response()
        result=self.prepare(proposal(amount_cp=5))
        self.assertEqual(result.status,'prepared')
        self.assertTrue(ea.public_offer(self.state(),result.offer).may_refuse)
        resolved=ea.resolve_offer(self.state(),result.offer,operation_id='test',check=lambda *a:None)
        self.assertEqual((resolved.status,resolved.reason_code,resolved.net_debit_cp),('refused','npc_consent_required',0))

    def test_explicit_refusal_is_same_recipient_and_same_amount_only(self):
        self.response(status='refuse')
        blocked=self.prepare(proposal(amount_cp=5))
        self.assertEqual((blocked.status,blocked.reason_code),('refused','npc_refuses'))
        self.assertEqual(self.prepare(proposal(amount_cp=6)).status,'prepared')
        self.assertEqual(self.prepare(proposal(amount_cp=5,recipient_id='farmer')).status,'prepared')

    def test_other_purpose_does_not_inherit_gift_response(self):
        self.response(amount=50,status='refuse')
        self.assertEqual(self.prepare(proposal(purpose='room',amount_cp=None)).status,'prepared')

    def test_reply_after_card_preparation_invalidates_confirmation(self):
        result=ea.prepare_from_panel(self.state(),proposal(amount_cp=5),campaign_id='campaign-1',actor_id='player',turn_index=3)
        self.response(status='refuse')
        before=copy.deepcopy(self.w['currency'])
        with resolution_action_scope('consent-confirm','session'):
            resolved=ea.confirm_offer(self.state(),offer_id=result.offer.offer_id,confirmation_digest=result.offer.confirmation_digest,operation_id='consent-confirm',check=lambda *a:None)
        self.assertEqual((resolved.status,resolved.reason_code),('refused','stale'))
        self.assertEqual(self.w['currency'],before)

class NoOfferAdmission(JourneyCase):
    async def test_none_read_of_quoted_money_does_not_block_later_panel_tip(self):
        source=load_scenario(SCENARIO_DIR/'17_refused_gift_not_charged.json')
        steps=[replace(s,known_broken=(),broken_because=()) for s in source.steps]
        script=copy.deepcopy(steps[0].script)
        script['front']['economic_intent']='none'
        steps[0]=replace(steps[0],say='Kervanc\u0131 "be\u015f bak\u0131r veriyorum" dedi',script=script)
        steps[2]=replace(steps[2],expect={'kese':95,'kisi_kese':{'caravaner':5}})
        results=await self.run_scenario(replace(source,steps=tuple(steps)))
        self.assertEqual(describe_problems(results),[])

class ConsentPersistence(OfferFixture):
    response=RecordedConsent.response
    def test_consuming_refusal_cannot_be_retried_after_turn_advance(self):
        self.response()
        before=copy.deepcopy(self.w['currency'])
        for index in range(2):
            card=ea.prepare_from_panel(self.state(),proposal(amount_cp=5),campaign_id='campaign-1',actor_id='player',turn_index=3+index)
            with resolution_action_scope(f'consent-{index}','session'):
                result=ea.confirm_offer(self.state(),offer_id=card.offer.offer_id,confirmation_digest=card.offer.confirmation_digest,operation_id=f'consent-{index}',check=lambda *a:None)
            self.assertEqual((result.status,result.reason_code,result.net_debit_cp),('refused','npc_consent_required',0))
            self.w['flags']['turn_index']+=1
        self.assertEqual(self.w['currency'],before)

    def test_saved_reply_survives_reload(self):
        self.response()
        self.w=json.loads(json.dumps(self.w))
        result=self.prepare(proposal(amount_cp=5))
        resolved=ea.resolve_offer(self.state(),result.offer,operation_id='reload',check=lambda *a:None)
        self.assertEqual((resolved.status,resolved.reason_code),('refused','npc_consent_required'))

    def test_new_bound_acceptance_clears_only_same_amount_conversation_gate(self):
        self.response()
        self.response(amount=6,status='refuse')
        npc=next(n for n in self.w['npcs'] if n['id']=='barman')
        ea.record_coin_response(self.w,npc,5,'accept',source_action_id='new-proposal')
        card=self.prepare(proposal(amount_cp=5))
        self.assertEqual(card.status,'prepared')
        resolved=ea.resolve_offer(self.state(),card.offer,operation_id='accepted',check=lambda *a:None)
        self.assertEqual((resolved.status,resolved.net_debit_cp),('applied',5))
        self.assertEqual(self.prepare(proposal(amount_cp=6)).reason_code,'npc_refuses')

class EarlyReplyCompletion(OfferFixture):
    def test_deterministic_reply_cannot_silently_drop_pending_gift(self):
        self.s._spoken_coin_proposal=ea.turn_proposal('gift','barman',amount_cp=5)
        self.s._front_economic_none=True
        self.s._tell_the_coin({'narration':'Marek yanıt verir.','action_result':{'action':'dialogue'}})
        cards=[v for v in ea.offer_records(self.w).values() if v['status']=='prepared']
        self.assertEqual(len(cards),1,'the pending offer must reach the economic owner')
        [data]=cards
        offer=ea.offer_from_record(data)
        result=ea.resolve_offer(self.state(),offer,operation_id='early',check=lambda *a:None)
        self.assertEqual((result.status,result.reason_code),('refused','npc_consent_required'))
        self.assertIsNone(self.s._spoken_coin_proposal)

class FailedSpeechRollback(JourneyCase):
    async def test_failed_preparation_rolls_back_reply_record_and_pending_proposal(self):
        source=load_scenario(SCENARIO_DIR/'17_refused_gift_not_charged.json')
        script=copy.deepcopy(source.steps[0].script)
        script['front']['economic_intent']='gift'
        first=replace(source.steps[0],script=script,known_broken=(),broken_because=())
        with patch('economic_actions.prepare_from_turn',side_effect=RuntimeError('synthetic preparation failure')):
            results=await self.run_scenario(replace(source,steps=(first,)))
        self.assertTrue(any('HTTP 500' in f for f in results[0].failures),results)
        session=self.manager.get(self.last_session_id).game_session
        self.assertEqual(session.world_state['currency']['player'],100)
        self.assertFalse(any(n.get('coin_responses') for n in session.world_state['npcs']))
        self.assertFalse(ea.offer_records(session.world_state))
        self.assertIsNone(getattr(session,'_spoken_coin_proposal',None))
        self.assertIsNone(getattr(session,'_spoken_coin_result',None))

import game
class PendingCoinPrompt(OfferFixture):
    def test_bound_pending_offer_tells_only_recipient_coin_is_not_transferred(self):
        npc=next(n for n in self.w['npcs'] if n['id']=='barman')
        self.s._front_coin=5
        self.assertTrue(self.s._defer_spoken_coin_offer({'kind':'economic','valid':True,'purpose':'gift','id':'barman'}))
        before=copy.deepcopy(self.w['currency'])
        note=game._experimental_speech_note(self.w,npc,None,'gift',session=self.s)
        self.assertIn('5 bak\u0131r',note)
        self.assertIn('hen\u00fcz sende de\u011fil',note)
        self.assertNotIn('art\u0131k sende',note)
        other=next(n for n in self.w['npcs'] if n['id']=='farmer')
        other_note=game._experimental_speech_note(self.w,other,None,'gift',session=self.s)
        self.assertNotIn('5 bak\u0131r',other_note)
        self.assertEqual(self.w['currency'],before)
        self.assertIsNone(getattr(self.s,'_coin_paid',None))
