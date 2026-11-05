"""Review regression: a held tip shares the counter offer lifetime."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4
from api.tests import test_shop_counter_http as held
from api.tests import test_counter_tip as tip

class OfferTipExpiry(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = held.HeldTipHttp.asyncSetUp
    asyncTearDown = held.HeldTipHttp.asyncTearDown
    create_campaign = held.HeldTipHttp.create_campaign
    ready = held.HeldTipHttp.ready
    read = held.HeldTipHttp.read
    post = tip.KeepTheChangeOverHttp.post

    async def test_same_sequence_tip_is_absent_after_offer_turn_expiry(self):
        campaign, record = await self.ready()
        world = record.game_session.world_state
        opened = copy.deepcopy(world['flags']['counter_offer_v1'])
        world['flags']['turn_index'] = opened['turn'] + 2
        self.assertEqual((await self.read(campaign))['held']['total_cp'], 5)
        world['flags']['turn_index'] = opened['turn'] + 3
        before = copy.deepcopy(world)
        self.assertNotIn('held', await self.read(campaign))
        self.assertEqual(world, before)
        self.assertEqual(world['flags']['counter_offer_v1'], opened)

    async def test_expired_tip_total_cannot_debit_then_base_price_buys_without_tip(self):
        campaign, record = await self.ready()
        world = record.game_session.world_state
        world['flags']['turn_index'] = world['flags']['counter_offer_v1']['turn'] + 3
        with patch('game.ollama.chat', side_effect=AssertionError('Unexpected model call')):
            await self.post(campaign, {'message':'/item shop_buy barman bira 1 0 5','action_id':str(uuid4())})
            self.assertEqual(world['currency'], {'player':100,'barman':0})
            self.assertEqual(tip.bag(world).count('Bira'), 0)
            response = await self.post(campaign, {'message':'/item shop_buy barman bira 1 0 4','action_id':str(uuid4())})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(world['currency'], {'player':96,'barman':4})
            self.assertEqual(tip.bag(world).count('Bira'), 1)