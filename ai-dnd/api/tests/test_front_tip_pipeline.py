"""J077: fake wire replies through the real classifier, money owner and HTTP.

These tests characterize transport/ownership, not a model's Turkish comprehension.
Only the provider is scripted; no turn decision or held offer is injected.
"""
import copy
import json
import uuid
from unittest.mock import patch

import game
import money_owner
from api.tests import test_money_routes as routes
from api.tests.journeys.runner import call_kind


LINE = "Bir bira almak istiyorum. Beş bakır uzatıyorum; üstü kalsın."
MISSING = object()


class WireClient(routes.RouteClient):
    def __init__(self):
        super().__init__()
        self.wire = []
        self.requests = []

    def chat(self, *args, **kwargs):
        reply = super().chat(*args, **kwargs)
        if call_kind(kwargs.get('format')) == 'front':
            self.wire.append(copy.deepcopy(json.loads(reply['message']['content'])['front']))
            self.requests.append(copy.deepcopy(kwargs))
        return reply


class TipPipeline(routes.Routes):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.client = WireClient()
        self.enterContext(patch.object(self.app.state.ollama_adapter, '_client', self.client))
        self.parsed = []
        self.reads = []
        self.decisions = []
        parse = game.parse_player_intent
        read = money_owner.read_deal
        decide = money_owner.decide

        def trace_parse(*args, **kwargs):
            result = parse(*args, **kwargs)
            if kwargs.get('front_list') is not None:
                self.parsed.append(copy.deepcopy(result.get('front')))
            return result

        def trace_read(front, listed):
            result = read(front, listed)
            self.reads.append((copy.deepcopy(front), result))
            return result

        def trace_decide(*args, **kwargs):
            result = decide(*args, **kwargs)
            self.decisions.append(result)
            return result

        self.enterContext(patch.object(game, 'parse_player_intent', trace_parse))
        self.enterContext(patch.object(money_owner, 'read_deal', trace_read))
        self.enterContext(patch.object(money_owner, 'decide', trace_decide))

    async def offer(self, keep_change, *, to=None, goods='bira', line=LINE):
        self.client.front = {'kind': 'speak_to', 'person_id': 'barman', 'deal': 'goods',
                             'deal_goods': goods, 'coin_cp': 5}
        if keep_change is not MISSING:
            self.client.front['keep_change'] = keep_change
        before = copy.deepcopy(self.world['currency'])
        reply = await self.line(line, to=to)
        # Wire -> actual JSON extraction -> owner input: no silent false coercion.
        self.assertEqual(len(self.client.wire), 1)
        self.assertEqual(self.parsed, self.client.wire)
        self.assertEqual([row[0] for row in self.reads], self.client.wire)
        self.assertEqual(self.world['currency'], before)
        self.assertEqual(len(self.decisions), 1)
        self.assertEqual(self.client.kinds.count('front'), 1)
        self.assertLessEqual(len(self.client.kinds), 2)
        self.assertNotIn('intent', self.client.kinds)
        return reply

    async def held(self):
        response = await self.http.get(f'/api/game/sessions/{self.session_id}/shop')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json().get('held')

    async def test_true_survives_wire_parser_owner_and_projection(self):
        await self.offer(True)
        self.assertIs(self.reads[0][1].keep_change, True)
        self.assertEqual(self.decisions[0].tip_cp, 1)
        self.assertEqual(self.world['flags']['counter_offer_v1']['tip_cp'], 1)
        self.assertEqual(await self.held(), {'npc_id':'barman','key':'bira','count':1,'tip_cp':1,'total_cp':5})

    async def test_say_mode_keeps_the_same_true_for_the_chosen_vendor(self):
        await self.offer(True, to='barman')
        self.assertEqual(self.decisions[0].tip_cp, 1)
        self.assertEqual((await self.held())['total_cp'], 5)

    async def test_false_reproduces_the_observed_missing_tip_without_money_moving(self):
        await self.offer(False)
        self.assertIs(self.reads[0][1].keep_change, False)
        self.assertEqual(self.decisions[0].tip_cp, 0)
        self.assertNotIn('tip_cp', self.world['flags']['counter_offer_v1'])
        self.assertIsNone(await self.held())

    async def test_missing_boolean_cannot_invent_a_tip_from_the_players_words(self):
        await self.offer(MISSING)
        self.assertIs(self.reads[0][1].keep_change, False)
        self.assertEqual(self.decisions[0].tip_cp, 0)
        self.assertIsNone(await self.held())

    async def test_string_true_does_not_become_explicit_boolean_consent(self):
        await self.offer('true')
        self.assertIs(self.reads[0][1].keep_change, False)
        self.assertEqual(self.decisions[0].tip_cp, 0)
        self.assertIsNone(await self.held())

    async def test_true_with_unlisted_goods_does_not_fall_back_to_a_tip(self):
        await self.offer(True, goods='invented_drink')
        self.assertEqual(self.decisions[0].kind, 'unclear')
        self.assertEqual(self.decisions[0].tip_cp, 0)
        self.assertIsNone(await self.held())

    async def test_false_on_a_plain_overpayment_cannot_turn_into_a_tip(self):
        await self.offer(False, line='Bir bira için beş bakır uzatıyorum, para üstünü ver.')
        self.assertEqual(self.decisions[0].tip_cp, 0)
        self.assertIsNone(await self.held())

    async def test_true_offer_confirmation_replay_and_resume_pay_once(self):
        await self.offer(True)
        self.assertEqual((await self.held())['total_cp'], 5)
        url=f'/api/game/sessions/{self.session_id}/turn'
        body={'message':'/item shop_buy barman bira 1 0 5','action_id':str(uuid.uuid4())}
        with patch.object(game.ollama, 'chat', side_effect=AssertionError('No provider on confirm/replay')):
            first=await self.http.post(url,json=body)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(self.world['currency']['player'],95)
            self.assertEqual(self.world['currency']['barman'],5)
            again=await self.http.post(url,json=body)
            self.assertEqual(again.content,first.content)
            self.assertEqual(self.world['currency']['player'],95)
            campaign_id=self.manager.get(self.session_id).campaign_id
            sid,record,*_=self.manager.resume_campaign(campaign_id)
            self.assertEqual(record.game_session.world_state['currency'],{'player':95,'barman':5,'osman':0})
            resumed=await self.http.post(f'/api/game/sessions/{sid}/turn',json=body)
            self.assertEqual(resumed.content,first.content)
            self.assertEqual(record.game_session.world_state['currency']['player'],95)

    async def test_request_explains_combined_goods_and_tip_before_the_long_route_rules(self):
        """A request-contract regression, not proof of scripted model comprehension."""
        await self.offer(True)
        request=self.client.requests[0]
        prompt=next(row['content'] for row in request['messages'] if row['role']=='user')
        routing=prompt.index('kind: speak_to')
        early=prompt[:routing]
        self.assertIn('keep_change=true',early)
        self.assertIn('deal=goods',early)
        self.assertIn('deal=tip',early)
        self.assertIn('keep_change=false',early)
        for safety in ('olumsuz','alıntı','koşul','belirsiz','Python'):
            self.assertIn(safety,early)
