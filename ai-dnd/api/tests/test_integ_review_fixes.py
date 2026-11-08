"""Fixes after the independent review of the D0 + D1 merge (S1-S4), each pinned by its own test.

S1 walk-to-bed with a front reading still opens the room card and sleep waits; S2 a spoken coin reply belongs to one
game day and to one kind of card; S3 a stale bound card is hidden from the projection but stays stored (Undo reopens
it); S4 `economic_intent` sits right after the deal fields and a valid room/goods `deal` is used on a typed line.
"""
import copy
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import campaign_time
import economic_actions as ea
import front_proposal
import game
import shop_trade
from api import serializers
from api.tests import test_economic_room as room_tests
from api.tests import test_last_play_blockers as blockers
from api.tests import test_money_routes as routes
from api.tests.journeys.runner import ScriptedClient
from api.tests.test_economic_action_http import EconomicHttpFixture
from api.tests.test_world_keeps_its_word import ReadingClient

DAY = 86400


class WalkToBedWithAReading(unittest.IsolatedAsyncioTestCase):
    """S1: the front reading closes the room words, but the walk to a bed is no word read: its card still opens."""

    asyncSetUp, asyncTearDown = blockers.InnRoomTests.asyncSetUp, blockers.InnRoomTests.asyncTearDown
    post_scene_turn, begin, say = (blockers.InnRoomTests.post_scene_turn, blockers.InnRoomTests.begin,
                                   blockers.InnRoomTests.say)
    add_person, inn, coin = blockers.InnRoomTests.add_person, blockers.InnRoomTests.inn, blockers.InnRoomTests.coin

    def prepared(self):
        return [data for data in self.world["flags"].get("economic_offers", {}).values()
                if data["status"] == "prepared"]

    async def test_walk_then_sleep_with_a_reading_opens_the_room_card_and_waits(self):
        await self.inn(inside=False)
        clock = self.world["campaign_time"]["elapsed_seconds"]
        client = ReadingClient({"kind": "go_to", "place_id": self.place["id"], "inside": True,
                                "economic_intent": "none"})
        with patch.dict(os.environ, {"AI_DND_FRONT_PROPOSAL": "1"}):
            out = await self.say(room_tests.WALK_AND_SLEEP, client)
        self.assertEqual(self.world["location"], self.place["id"], out["narration"])
        cards = self.prepared()
        self.assertEqual(len(cards), 1, out["narration"])
        [card] = cards
        self.assertEqual(card["proposal"]["purpose"], "room")
        self.assertEqual(self.coin(), 2400)
        self.assertIsNone(self.world["flags"].get("inn_room"))
        self.assertEqual(self.session.character["current_hp"], 5, out["narration"])  # no sleep before the room is held
        self.assertLess(self.world["campaign_time"]["elapsed_seconds"], clock + 6 * 3600)


class Keep(EconomicHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.enterContext(patch.dict(os.environ, {'AI_DND_FRONT_PROPOSAL': '1'}))
        self.world['inventory'] = []
        self.save()

    async def utter(self, text, coin=0, keep=False, **extra):
        client = ScriptedClient({'front': {'kind': 'speak_to', 'person_id': 'barman', 'economic_intent': 'purchase',
                                           'coin_cp': coin, 'keep_change': keep, **extra}})
        with patch.object(self.app.state.ollama_adapter, '_client', client):
            response = await self.post({'message': text, 'action_id': str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def keep_card(self):
        await self.utter('bir bira alayim')
        payload = await self.utter('5 bakir koyuyorum, ustu kalsin', 5, True)
        card = payload['state']['economic_offer']
        self.assertIsNotNone(card)
        return card

    def assets(self):
        return copy.deepcopy((self.world['currency'], self.world['inventory'],
                              [n.get('wares_v1') for n in self.world['npcs']], shop_trade.seq(self.world)))

    def shown(self):
        return serializers._economic_projection(self.world)['economic_offer']

    def say_coin(self, amount, answer, purpose):
        """The person's spoken answer to coin held out to them, written the way a turn writes it."""
        session = self.record.game_session
        npc = next(n for n in self.world['npcs'] if n['id'] == 'barman')
        token = game._ACTIVE_SESSION.set(session)
        try:
            session._spoken_coin_proposal = ea.turn_proposal(purpose, 'barman', amount_cp=amount)
            game._record_spoken_coin_response(npc, answer)
        finally:
            game._ACTIVE_SESSION.reset(token)


class AStaleCardIsHiddenNotChanged(Keep):
    """S3."""

    async def test_direct_goods_purchase_hides_the_bound_card_but_keeps_it_stored_for_undo(self):
        card = await self.keep_card()
        self.assertEqual(self.shown()['offer_id'], card['offer_id'])
        before = self.assets()
        action = str(uuid4())
        response = await self.post({'message': '/item shop_buy barman bira 1 0 4', 'action_id': action})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.offers()[card['offer_id']]['status'], 'prepared')  # stored state untouched
        self.assertIsNone(self.shown())  # but no longer offered to the player
        self.assertIsNone(response.json()['state']['economic_offer'])
        undone = await self.undo(action)
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(self.assets(), before)
        self.assertEqual(self.shown()['offer_id'], card['offer_id'])  # Undo reopens the very same card
        self.assertEqual(undone.json()['state']['economic_offer']['offer_id'], card['offer_id'])


class ASpokenReplyBelongsToOneDayAndOneKind(Keep):
    """S2."""

    async def test_an_unanswered_standalone_tip_does_not_drop_a_later_keep_change_tip(self):
        self.say_coin(1, None, 'tip')  # the barman said nothing about the 1 copper held out as a tip
        card = await self.keep_card()
        result, _ = await self.confirm(card)
        resolution = result['economic_resolution']
        self.assertEqual((resolution['status'], resolution['net_debit_cp']), ('applied', 5))
        self.assertEqual((self.purse(), self.world['currency']['barman']), (95, 5))

    async def test_a_recorded_refusal_ends_with_the_game_day(self):
        self.say_coin(5, 'refuse', 'tip')
        same_day = await self.prepare(purpose='tip', recipient_id='barman', amount_cp=5)
        self.assertIsNone(same_day['state']['economic_offer'])  # refused today
        campaign_time.initialize(self.world)
        self.world['campaign_time']['elapsed_seconds'] += DAY
        self.save()
        next_day = await self.prepare(purpose='tip', recipient_id='barman', amount_cp=5)
        self.assertIsNotNone(next_day['state']['economic_offer'])

    async def test_an_old_amount_only_record_still_refuses_and_keeps_its_card_readable(self):
        # A record an earlier build wrote (amount key, no day) is still honoured: nothing older is silently opened.
        self.world['npcs'][0]['coin_responses'] = {'1': {'status': 'refuse', 'source_action_id': 'old'}}
        self.save()
        card = await self.keep_card()
        self.assertTrue(card['may_refuse'])
        result, _ = await self.confirm(card)
        self.assertEqual(result['economic_resolution']['net_debit_cp'], 4)


class TheDealSitsNextToKind(unittest.TestCase):
    """S4: the schema and the guide."""

    LISTED = {"people": [{"id": "npc_a", "name": "A"}], "places": [], "things": [], "offers": [], "bag": [],
              "parcels": [], "jobs": [], "wants": [], "goods": [{"id": "bira", "name": "bira"}],
              "speaking_with": "npc_a"}

    def test_economic_intent_follows_the_deal_fields_right_after_kind(self):
        schema = front_proposal.schema(self.LISTED)
        self.assertEqual(list(schema["properties"])[:5],
                         ["kind", "deal", "deal_goods", "keep_change", "economic_intent"])
        self.assertEqual(len(schema["required"]), len(set(schema["required"])))
        self.assertTrue(set(schema["required"]) <= set(schema["properties"]))
        self.assertIn("economic_intent", schema["required"])

    def test_the_guide_names_economic_intent_beside_the_deal(self):
        text = front_proposal.guidance(self.LISTED)
        self.assertLess(text.index("deal:"), text.index("economic_intent:"))
        self.assertLess(text.index("economic_intent:"), text.index("want:"))


class ATypedLineKeepsAValidDeal(routes.Routes):
    """S4: said to whoever serves, a room or goods `deal` opens its offer even when `economic_intent` says none."""

    async def test_a_typed_room_deal_with_no_economic_intent_opens_the_room_card(self):
        self.client.front = {"kind": "speak_to", "person_id": "barman", "economic_intent": "none", "deal": "room"}
        await self.line("Bu gece burada kalayım", to="barman")
        self.assertIsNotNone(self.card())
        self.assertEqual({key: self.card()[key] for key in routes.ROOM_CARD}, routes.ROOM_CARD)
        self.assertEqual(self.purse(), 100)

    async def test_a_typed_goods_deal_with_no_economic_intent_opens_the_counter_and_moves_no_coin(self):
        self.client.front = {"kind": "speak_to", "person_id": "barman", "economic_intent": "none", "deal": "goods",
                             "deal_goods": "bira"}
        await self.line("Bir bira alabilir miyim", to="barman")
        self.assertIsNotNone(self.counter())
        self.assertEqual(self.counter()["key"], "bira")
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.purse(), 100)

    async def test_a_typed_gift_deal_is_not_used_here(self):
        self.client.front = {"kind": "speak_to", "person_id": "barman", "economic_intent": "none", "deal": "gift"}
        await self.line("Selam usta", to="barman")
        self.assertEqual(self.cards(), [])
        self.assertIsNone(self.counter())
