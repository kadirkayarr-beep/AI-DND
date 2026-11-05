"""Task11: HTTP projection of a held tip; reads cannot move money."""
import copy
import unittest
from api.tests import test_campaign_api as fixtures
from api.tests.test_counter_tip import tavern, open_offer

class HeldTipHttp(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def ready(self):
        campaign = await self.create_campaign()
        record = self.manager.get(campaign['session_id'])
        tavern(record.game_session)
        open_offer(record.game_session)
        self.manager.save_campaign(campaign['campaign_id'])
        return campaign, record

    async def read(self, campaign):
        response = await self.http.get(f"/api/game/sessions/{campaign['session_id']}/shop")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_counter_reports_the_held_tip_only_while_it_is_valid(self):
        campaign, record = await self.ready()
        before = copy.deepcopy(record.game_session.world_state)
        first = await self.read(campaign)
        self.assertEqual(first['held'], {'npc_id':'barman', 'key':'bira', 'count':1, 'tip_cp':1, 'total_cp':5})
        self.assertEqual(await self.read(campaign), first)
        self.assertEqual(record.game_session.world_state, before)
        record.game_session.world_state['currency']['player'] = 4
        self.assertNotIn('held', await self.read(campaign))

    async def test_missing_stale_and_wrong_vendor_tip_are_absent_not_null(self):
        campaign, record = await self.ready()
        world = record.game_session.world_state
        original = copy.deepcopy(world['flags']['counter_offer_v1'])
        for field, value in [('seq', -1), ('npc_id', 'other'), ('tip_cp', True), ('tender_cp', 4)]:
            with self.subTest(field=field):
                world['flags']['counter_offer_v1'] = {**original, field:value}
                self.assertNotIn('held', await self.read(campaign))
        world['flags'].pop('counter_offer_v1')
        self.assertNotIn('held', await self.read(campaign))