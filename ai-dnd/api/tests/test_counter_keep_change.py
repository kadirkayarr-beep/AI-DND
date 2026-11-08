"""02: engine-priced base+tip is shown and bound before the native owner can settle it."""
import copy
import os
from unittest.mock import patch
from uuid import uuid4
import economic_actions
import shop_trade
from api.tests.journeys.runner import ScriptedClient
from api.tests.test_economic_action_http import EconomicHttpFixture

class KeepChangeHttp(EconomicHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.enterContext(patch.dict(os.environ,{'AI_DND_FRONT_PROPOSAL':'1'}))
        self.world['inventory']=[]
        self.save()

    async def utter(self,text,coin=0,keep=False,**extra):
        client=ScriptedClient({'front':{'kind':'speak_to','person_id':'barman','economic_intent':'purchase','coin_cp':coin,'keep_change':keep,**extra}})
        with patch.object(self.app.state.ollama_adapter,'_client',client):
            response=await self.post({'message':text,'action_id':str(uuid4())})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    async def offer_keep(self,keep=True):
        await self.utter('bir bira alayim')
        return await self.utter('5 bakir koyuyorum, ustu kalsin',5,keep)

    async def keep_card(self):
        payload=await self.offer_keep()
        card=payload['state']['economic_offer']
        self.assertIsNotNone(card,'current keep-change needs a bound explicit confirmation card')
        return card

    def assets(self):
        return copy.deepcopy((self.world['currency'],self.world['inventory'],[n.get('wares_v1') for n in self.world['npcs']],shop_trade.seq(self.world)))

    def snapshot(self):
        return copy.deepcopy((self.record.game_session.serialize_game_state(),self.record.game_session.rng.getstate(),self.checkpoint(),self.record.turn_action_receipts,self.store.get_campaign(self.record.campaign_id)))

    def beers(self):
        return [x for x in self.world['inventory'] if isinstance(x,dict) and x.get('name')=='Bira']

    async def test_preview_binds_goods4_tip1_total5_without_moving_assets(self):
        before=self.assets()
        card=await self.keep_card()
        self.assertEqual(self.assets(),before)
        self.assertEqual((card['max_total_cp'],card['tender_cp']),(5,5))
        self.assertEqual([(x['line_id'],x['count'],x['unit_cp'],x['total_cp']) for x in card['lines']],[('goods:0',1,4,4),('tip:1',1,1,1)])

    async def test_confirm_moves_all_once_and_replay_cannot_pay_again(self):
        card=await self.keep_card()
        with patch('game.ollama.chat',side_effect=AssertionError('no model at confirmation')):
            first,body=await self.confirm(card)
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers()),shop_trade.seq(self.world)),(95,5,1,1))
        self.assertEqual(first['economic_resolution']['net_debit_cp'],5)
        self.assertEqual(first['narration'],first['economic_resolution']['public_summary'])
        self.assertIn('5 bak\u0131r',first['narration'])
        self.assertEqual(self.world['npcs'][0]['wares_v1']['bira']['stock'],11)
        accepted_assets=self.assets()
        before=self.snapshot()
        replay=await self.post(body)
        self.assertEqual(replay.json(),first)
        self.assertEqual(self.snapshot(),before)
        second,_=await self.confirm(card)
        self.assertEqual(second['economic_resolution']['reason_code'],'offer_not_prepared')
        self.assertEqual(self.assets(),accepted_assets)
        self.assertEqual((self.purse(),len(self.beers())),(95,1))

    async def test_same_total_after_price_drop_requires_new_confirmation(self):
        card=await self.keep_card()
        self.world['npcs'][0]['price_cut_cp_v1']={'bira':1}
        self.world['npcs'][0]['price_cut_day_v1']=economic_actions.game_day(self.world)  # a cut holds only on its game day
        self.save()
        before=self.assets()
        result,_=await self.confirm(card)
        self.assertEqual((result['economic_resolution']['status'],result['economic_resolution']['reason_code']),('refused','stale'))
        self.assertEqual(self.assets(),before)

    async def test_changed_native_order_cannot_reuse_the_card(self):
        card=await self.keep_card()
        self.world['flags']['counter_offer_v1']['key']='yemek'
        self.save()
        before=self.assets()
        result,_=await self.confirm(card)
        self.assertEqual(result['economic_resolution']['reason_code'],'stale')
        self.assertEqual(self.assets(),before)

    async def test_equal_total_redistribution_tampering_is_not_the_shown_offer(self):
        card=await self.keep_card()
        stored=self.offers()[card['offer_id']]
        stored['proposal']['tip_cp']=2
        stored['lines'][0].update(unit_cp=3,total_cp=3)
        stored['lines'][1].update(unit_cp=2,total_cp=2)
        before=self.assets()
        result,_=await self.confirm(card)
        self.assertEqual(result['economic_resolution']['reason_code'],'digest_mismatch')
        self.assertEqual(self.assets(),before)

    async def test_recipient_product_and_count_cannot_be_changed_under_old_digest(self):
        for field,value in [('recipient_id','farmer'),('item_id','yemek'),('count',2)]:
            with self.subTest(field=field):
                card=await self.keep_card()
                self.offers()[card['offer_id']]['proposal'][field]=value
                before=self.assets()
                result,_=await self.confirm(card)
                self.assertEqual(result['economic_resolution']['reason_code'],'digest_mismatch')
                self.assertEqual(self.assets(),before)

    async def test_insufficient_full_tender_does_not_silently_drop_the_tip(self):
        card=await self.keep_card()
        self.world['currency']['player']=4
        self.save()
        before=self.assets()
        result,_=await self.confirm(card)
        self.assertEqual((result['economic_resolution']['status'],result['economic_resolution']['net_debit_cp']),('refused',0))
        self.assertEqual(self.assets(),before)

    async def test_tender_above_initial_purse_opens_no_card(self):
        self.world['currency']['player']=4
        self.save()
        before=self.assets()
        payload=await self.offer_keep()
        self.assertIsNone(payload['state']['economic_offer'])
        self.assertEqual(self.assets(),before)

    async def test_refused_tip_is_not_implied_by_accepting_the_goods(self):
        self.world['npcs'][0]['coin_responses']={'1':{'status':'refuse','source_action_id':'prior-tip'}}
        self.save()
        card=await self.keep_card()
        self.assertTrue(card['may_refuse'])
        result,_=await self.confirm(card)
        resolution=result['economic_resolution']
        self.assertEqual((resolution['status'],resolution['net_debit_cp'],resolution['change_cp']),('applied',4,1))
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(96,4,1))
        self.assertEqual(resolution['refusals'][0]['line_id'],'tip:1')
        self.assertEqual(result['narration'],resolution['public_summary'])
        self.assertIn('4 bak\u0131r',result['narration'])

    async def buy_native(self,command='/item shop_buy barman bira 1 0 4'):
        body={'message':command,'action_id':str(uuid4())}
        response=await self.post(body)
        self.assertEqual(response.status_code,200,response.text)
        return response.json(),body

    async def test_open_total5_card_does_not_block_a_goods_only_native_purchase(self):
        # Owner decision 2026-11-08 (replaces "an open total-5 card blocks the direct 4"): with "keep the change" the
        # player may confirm the combined 5 or the goods alone, and the open card never blocks the goods-only 4.
        card=await self.keep_card()
        before=self.assets()
        first,body=await self.buy_native()
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(96,4,1))
        self.assertEqual((self.world['npcs'][0]['wares_v1']['bira']['stock'],shop_trade.seq(self.world)),(11,1))
        sold=self.assets()
        self.assertNotEqual(sold,before)
        replay=await self.post(body)  # the same action again is the same answer, never a second sale
        self.assertEqual(replay.json(),first)
        self.assertEqual(self.assets(),sold)
        # The still-open card is not paid on top of the goods: its binding (offer number) no longer holds.
        refused,_=await self.confirm(card)
        self.assertNotEqual(refused['economic_resolution']['status'],'applied')
        self.assertEqual(refused['economic_resolution']['net_debit_cp'],0)
        self.assertEqual(self.assets(),sold)
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(96,4,1))

    async def test_goods_only_purchase_beside_an_open_card_undoes_and_resumes(self):
        card=await self.keep_card()
        before=self.assets()
        _,body=await self.buy_native()
        sold=self.assets()
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(96,4,1))
        cid=self.record.campaign_id
        sid,restored,*_=self.manager.resume_campaign(cid)  # a reload keeps exactly the one sale
        self.campaign['session_id']=sid
        self.turn_url=f'/api/game/sessions/{sid}/turn'
        self.undo_url=f'/api/game/sessions/{sid}/undo'
        self.assertEqual(self.assets(),sold)
        replay=await self.post(body)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(self.assets(),sold)
        undone=await self.undo(body['action_id'])
        self.assertEqual(undone.status_code,200,undone.text)
        self.assertEqual(self.assets(),before)  # purse, pack, stock and offer number all come back
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(100,0,0))
        again,_=await self.confirm(card)  # the restored world holds the card again, and it pays its 5 once
        self.assertEqual(again['economic_resolution']['net_debit_cp'],5)
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(95,5,1))

    async def test_open_total5_card_does_not_block_a_two_beer_native_purchase(self):
        await self.keep_card()
        await self.buy_native('/item shop_buy barman bira 2 0 8')
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(92,8,2))
        self.assertEqual((self.world['npcs'][0]['wares_v1']['bira']['stock'],shop_trade.seq(self.world)),(10,1))

    async def test_native_purchase_after_the_total5_card_was_confirmed_is_not_a_second_sale(self):
        card=await self.keep_card()
        await self.confirm(card)
        paid=self.assets()
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(95,5,1))
        await self.buy_native()
        self.assertEqual(self.assets(),paid)

    async def test_cancel_allows_an_explicit_base_only_native_purchase(self):
        card=await self.keep_card()
        await self.cancel(card['offer_id'])
        response=await self.post({'message':'/item shop_buy barman bira 1 0 4','action_id':str(uuid4())})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((self.purse(),self.world['currency']['barman'],len(self.beers())),(96,4,1))

    async def test_save_failure_rolls_back_all_and_retry_pays_once(self):
        card=await self.keep_card()
        body={'message':'Teklifi onayla','action_id':str(uuid4()),'economic_action':{'kind':'confirm','offer_id':card['offer_id'],'confirmation_digest':card['confirmation_digest']}}
        before=self.snapshot()
        with patch.object(self.manager,'autosave_turn',side_effect=RuntimeError('synthetic save failure')):
            failed=await self.post(body)
        self.assertEqual(failed.status_code,500,failed.text)
        self.assertEqual(self.snapshot(),before)
        retry=await self.post(body)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual((self.purse(),len(self.beers())),(95,1))

    async def test_undo_restores_assets_stock_sequence_and_card_without_replay_debit(self):
        card=await self.keep_card()
        before=self.assets()
        accepted,body=await self.confirm(card)
        undone=await self.undo(body['action_id'])
        self.assertEqual(undone.status_code,200,undone.text)
        self.assertEqual(self.assets(),before)
        self.assertEqual(self.offers()[card['offer_id']]['status'],'prepared')
        replay=await self.post(body)
        self.assertEqual(replay.json(),accepted)
        self.assertEqual(self.assets(),before)
        second,_=await self.confirm(card)
        self.assertEqual(second['economic_resolution']['net_debit_cp'],5)
        self.assertEqual((self.purse(),len(self.beers())),(95,1))

    async def test_resume_retains_bound_card_and_replay_history(self):
        card=await self.keep_card()
        cid=self.record.campaign_id
        sid,restored,*_=self.manager.resume_campaign(cid)
        self.campaign['session_id']=sid
        self.turn_url=f'/api/game/sessions/{sid}/turn'
        self.undo_url=f'/api/game/sessions/{sid}/undo'
        self.assertEqual(self.offers()[card['offer_id']]['confirmation_digest'],card['confirmation_digest'])
        result,body=await self.confirm(card)
        self.assertEqual((self.purse(),len(self.beers())),(95,1))
        sid,restored,*_=self.manager.resume_campaign(cid)
        self.campaign['session_id']=sid
        self.turn_url=f'/api/game/sessions/{sid}/turn'
        self.undo_url=f'/api/game/sessions/{sid}/undo'
        replay=await self.post(body)
        self.assertEqual(replay.json(),result)

    async def test_new_native_order_cancels_only_the_stale_bound_card(self):
        card=await self.keep_card()
        before=self.assets()
        payload=await self.utter('bir yemek alayim')
        self.assertIsNone(payload['state']['economic_offer'])
        self.assertEqual(self.offers()[card['offer_id']]['status'],'cancelled')
        self.assertEqual(self.world['flags']['counter_offer_v1']['key'],'yemek')
        self.assertEqual(self.assets(),before)
        refused,_=await self.confirm(card)
        self.assertEqual(refused['economic_resolution']['reason_code'],'offer_not_prepared')
        self.assertEqual(self.assets(),before)

    async def test_same_final_native_binding_keeps_the_card_open(self):
        import bold_acts
        card=await self.keep_card()
        before=self.assets()
        # Rebuild inside the original quote turn; a later turn is a different binding.
        self.world['flags']['turn_index']=self.offers()[card['offer_id']]['counter_binding']['quote_turn']
        bold_acts._with_tender(self.record.game_session,self.world['npcs'][0],'bira',5)
        self.assertEqual(self.offers()[card['offer_id']]['status'],'prepared')
        import economic_actions
        self.assertTrue(shop_trade.binding_matches(self.world,economic_actions.offer_from_record(self.offers()[card['offer_id']])))
        self.assertEqual(self.assets(),before)

    async def test_unrelated_gift_card_is_not_cancelled_by_a_native_quote(self):
        card=await self.card(purpose='gift',recipient_id='farmer',amount_cp=2)
        await self.utter('bir bira alayim')
        self.assertEqual(self.offers()[card['offer_id']]['status'],'prepared')

    async def test_removing_or_mutating_counter_binding_invalidates_digest(self):
        for remove in (True,False):
            with self.subTest(remove=remove):
                card=await self.keep_card()
                data=self.offers()[card['offer_id']]
                if remove:data.pop('counter_binding')
                else:data['counter_binding']['count']=2
                before=self.assets()
                result,_=await self.confirm(card)
                self.assertEqual(result['economic_resolution']['reason_code'],'digest_mismatch')
                self.assertEqual(self.assets(),before)

    async def test_counter_sequence_change_stales_card(self):
        card=await self.keep_card()
        self.world.setdefault(shop_trade.KEY,{})['seq']=1
        self.save()
        before=self.assets()
        result,_=await self.confirm(card)
        self.assertEqual(result['economic_resolution']['reason_code'],'stale')
        self.assertEqual(self.assets(),before)

    async def test_stock_location_and_recipient_liveness_change_stales_card(self):
        for change in ('stock','location','hp'):
            with self.subTest(change=change):
                card=await self.keep_card()
                original=copy.deepcopy(self.world)
                if change=='stock':self.world['npcs'][0]['wares_v1']={'bira':{'stock':0}}
                elif change=='location':self.world['location']='elsewhere'
                else:self.world['npcs'][0]['current_hp']=0
                before=self.assets()
                result,_=await self.confirm(card)
                self.assertEqual(result['economic_resolution']['reason_code'],'stale')
                self.assertEqual(self.assets(),before)
                self.world.clear();self.world.update(original)
                self.save()

    async def test_tip_refusal_after_preview_requires_new_confirmation(self):
        card=await self.keep_card()
        self.world['npcs'][0]['coin_responses']={'1':{'status':'refuse','source_action_id':'late-tip'}}
        self.save()
        before=self.assets()
        result,_=await self.confirm(card)
        self.assertEqual(result['economic_resolution']['reason_code'],'stale')
        self.assertEqual(self.assets(),before)

    async def test_model_coin_number_does_not_price_the_tip(self):
        await self.utter('bir bira alayim')
        payload=await self.utter('5 bakir koyuyorum, ustu kalsin',500,True)
        card=payload['state']['economic_offer']
        self.assertIsNotNone(card)
        self.assertEqual(card['max_total_cp'],5)
        self.assertEqual(card['lines'][1]['total_cp'],1)
        self.assertEqual(self.purse(),100)

    async def test_malformed_keep_change_cannot_authorize_card(self):
        for flag in (1,'true',None):
            with self.subTest(flag=flag):
                payload=await self.offer_keep(flag)
                self.assertIsNone(payload['state']['economic_offer'])
                self.assertEqual((self.purse(),len(self.beers())),(100,0))

    async def test_native_grant_failure_after_candidate_debit_rolls_back_all(self):
        card=await self.keep_card()
        body={'message':'Teklifi onayla','action_id':str(uuid4()),'economic_action':{'kind':'confirm','offer_id':card['offer_id'],'confirmation_digest':card['confirmation_digest']}}
        before=self.snapshot()
        with patch('equipment_economy.grant_named_item',side_effect=RuntimeError('synthetic grant failure')):
            failed=await self.post(body)
        self.assertEqual(failed.status_code,500,failed.text)
        self.assertEqual(self.snapshot(),before)
        repeated=await self.post(body)
        self.assertEqual(repeated.status_code,500,repeated.text)
        self.assertEqual(repeated.json(),failed.json())
        self.assertEqual(self.snapshot(),before)
        retry=await self.post({**body,'action_id':str(uuid4())})
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual((self.purse(),len(self.beers())),(95,1))

    async def test_partial_tip_refusal_undo_preserves_the_refusal(self):
        self.world['npcs'][0]['coin_responses']={'1':{'status':'refuse','source_action_id':'prior-tip'}}
        self.save()
        card=await self.keep_card()
        before=self.assets()
        first,body=await self.confirm(card)
        self.assertEqual(first['economic_resolution']['net_debit_cp'],4)
        undone=await self.undo(body['action_id'])
        self.assertEqual(undone.status_code,200,undone.text)
        self.assertEqual(self.assets(),before)
        second,_=await self.confirm(card)
        self.assertEqual(second['economic_resolution']['net_debit_cp'],4)
        self.assertEqual((self.purse(),len(self.beers())),(96,1))

    async def test_keep_change_without_a_live_native_order_cannot_create_a_sale(self):
        before=self.assets()
        payload=await self.utter('5 bakir koyuyorum, ustu kalsin',5,True)
        self.assertIsNone(payload['state']['economic_offer'])
        self.assertEqual(self.assets(),before)

    async def test_late_hold_by_serving_recipient_cannot_be_bought_through_old_card(self):
        with patch('world_reactions.refuses',return_value=False):
            card=await self.keep_card()
            self.world['flags'].setdefault('deeds',[]).append({
                'kind':'theft','at':120,'location':self.here,'text':'synthetic hold',
                'described':['barman'],'witnesses':[],'told':[],'heard':[],'seen_near':[],
                'challenged':['barman'],'hold':{'guard':'barman','place':self.here,'turn':self.world['flags']['turn_index'],'arrest':True}})
            self.save()
            before=self.assets()
            turn=self.world['flags']['turn_index']
            hold=copy.deepcopy(self.world['flags']['deeds'][-1]['hold'])
            result,_=await self.confirm(card)
        self.assertEqual((result['economic_resolution']['status'],result['economic_resolution']['net_debit_cp']),('refused',0))
        self.assertEqual(result['economic_resolution']['reason_code'],'stale')
        self.assertEqual(self.world['flags']['turn_index'],turn)
        self.assertEqual(self.assets(),before)
        self.assertEqual(self.world['flags']['deeds'][-1]['hold'],hold)
