"""C06 starting XP: literal PHB 2024 PDF40/42 source oracles.

Byte-verified external C06 release_v1 advancement.md requires minimum XP at
creation: levels 1/2/3 start at 0/300/900. No source text is copied here.
"""
import copy
import unittest
from unittest.mock import patch

import httpx
import game
import character_progression as cp
import xp
from api.auth import FixedAuthenticator
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests import test_campaign_api as campaigns
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_level3 import TWO, choices
from api.tests.test_roadmap_c06_creation_http import character_request


def create(level):
    session = game.create_session(seed=42)
    steps = {}
    if level >= 2:
        steps['2'] = copy.deepcopy(TWO)
    if level >= 3:
        steps['3'] = choices()
    cp.create_at_level(session, copy.deepcopy(SPEC), level, steps)
    return session


class StartingXpTests(unittest.TestCase):
    def test_real_creation_initializes_minimum_xp_without_award_receipts(self):
        for level, expected_xp, expected_hp in ((1, 0, 8), (2, 300, 14), (3, 900, 20)):
            with self.subTest(level=level):
                session = create(level)
                self.assertEqual(session.character['xp'], expected_xp)
                self.assertEqual(session.character['level'], level)
                self.assertEqual(session.character['progression_level'], level)
                self.assertEqual(session.character['max_hp'], expected_hp)
                self.assertEqual(session.world_state.get('xp_awarded_event_ids', []), [])

    def test_earned_xp_after_start_crosses_next_boundary_once_without_extra_hp(self):
        for level, amount, expected_xp in ((2, 600, 900), (3, 1800, 2700)):
            with self.subTest(level=level):
                session = create(level)
                hp = session.character['max_hp']
                result = xp.apply_xp(session.character, session.world_state, amount, 'quest:starting-xp')
                self.assertEqual(session.character['level'], level + 1)
                self.assertEqual(session.character['xp'], expected_xp)
                self.assertEqual(result['hit_points_gained'], 6)
                self.assertEqual(session.character['max_hp'], hp + 6)
                self.assertEqual(session.character['progression_level'], level)
                after = session._capture_runtime_snapshot()
                self.assertIsNone(xp.apply_xp(session.character, session.world_state, amount, 'quest:starting-xp'))
                self.assertEqual(session._capture_runtime_snapshot(), after)

    def test_late_invalid_creation_restores_preexisting_xp_and_snapshot(self):
        session = create(1)
        xp.apply_xp(session.character, session.world_state, 123, 'quest:prior')
        before = session._capture_runtime_snapshot()
        character = session.character
        with patch.object(cp, 'apply_level_choices', wraps=cp.apply_level_choices) as apply:
            with self.assertRaises(ValueError):
                cp.create_at_level(session, copy.deepcopy(SPEC), 3,
                                   {'2': copy.deepcopy(TWO), '3': choices('invalid')})
        self.assertEqual([call.args[1]['to_level'] for call in apply.call_args_list], [2, 3])
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertIs(session.character, character)
        self.assertEqual(session.character['xp'], 123)

    def test_level_two_boundary_and_pending_choices_never_double_pay_hp(self):
        session = create(2)
        hp = session.character['max_hp']
        xp.apply_xp(session.character, session.world_state, 599, 'quest:below-three')
        self.assertEqual((session.character['xp'], session.character['level'], session.character['max_hp']),
                         (899, 2, hp))
        xp.apply_xp(session.character, session.world_state, 1, 'quest:reach-three')
        self.assertEqual((session.character['xp'], session.character['level'], session.character['max_hp']),
                         (900, 3, hp + 6))
        delta = cp.apply_level_choices(session, cp.preview_level_up(session, 3), choices())
        self.assertEqual(delta['status'], 'applied')
        self.assertEqual((session.character['xp'], session.character['progression_level'], session.character['max_hp']),
                         (900, 3, hp + 6))

    def test_level_three_below_next_threshold_does_not_pay_hp(self):
        session = create(3)
        hp = session.character['max_hp']
        xp.apply_xp(session.character, session.world_state, 1799, 'quest:below-four')
        self.assertEqual((session.character['xp'], session.character['level'], session.character['max_hp']),
                         (2699, 3, hp))

    def test_unsupported_creation_levels_preserve_existing_xp_and_snapshot(self):
        session = create(2)
        before = session._capture_runtime_snapshot()
        for level in (0, 4, 5, 20, 21, True):
            with self.subTest(level=level):
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, copy.deepcopy(SPEC), level, {})
                self.assertEqual(session._capture_runtime_snapshot(), before)


class StartingXpHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown

    async def test_http_create_store_and_fresh_resume_preserve_starting_xp(self):
        for level, expected_xp in ((1, 0), (2, 300), (3, 900)):
            with self.subTest(level=level):
                response = await self.http.post('/api/game/campaigns', json={'character': character_request(level)})
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                saved = self.store.get_campaign(body['campaign_id'])
                manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
                app = create_app(session_manager=manager, authenticator=FixedAuthenticator(TEST_PLAYER))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    resumed = await client.post(f"/api/game/campaigns/{body['campaign_id']}/resume")
                self.assertEqual(resumed.status_code, 200, resumed.text)
                self.assertEqual((body['state']['character']['xp'], saved.payload['engine_save']['player']['xp'],
                                  resumed.json()['state']['character']['xp']), (expected_xp,) * 3)
