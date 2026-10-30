"""Earned selected4 HTTP adapter: actual engine/SQLite, synthetic campaign XP.

No claim that a human played to2700. Direct core choices ahead of XP remain legal.
"""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
import xp
from api.auth import FixedAuthenticator
from api.main import create_app
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests import test_campaign_api as campaigns
from api.tests.test_roadmap_c06_creation_http import character_request
from api.tests.test_roadmap_c06_level4_con import PICK


class LevelFourHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown

    async def earned(self, award=1800):
        response = await self.http.post('/api/game/campaigns', json={'character': character_request(3)})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json(); record = self.manager.get(body['session_id'])
        if award: xp.apply_xp(record.game_session.character, record.game_session.world_state, award, 'quest:synthetic-earned-four')
        self.manager.save_campaign(body['campaign_id'])
        return body, record

    def url(self, body):
        return f"/api/game/sessions/{body['session_id']}/level-up"

    async def ready(self, body):
        response = await self.http.get(self.url(body))
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual(preview['status'], 'ready', preview)
        self.assertEqual(preview['target_level'], 4)
        return preview

    def request(self, body, preview):
        return {'action_id': str(uuid4()), 'campaign_id': body['campaign_id'],
                'expected_revision': preview['revision'], 'target_level': 4, 'choices': copy.deepcopy(PICK)}

    async def reopen(self, body):
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        app = create_app(session_manager=manager, authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post(f"/api/game/campaigns/{body['campaign_id']}/resume")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), manager

    async def test_earned_preview_apply_and_fresh_resume_are_real_and_atomic(self):
        body, record = await self.earned()
        s = record.game_session; s.character['current_hp'] = 10
        s.world_state['spellcasting_v1']['slots'] = {'1': 2, '2': 1}
        self.manager.save_campaign(body['campaign_id'])
        before = s._capture_runtime_snapshot()
        preview = await self.ready(body)
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(preview['choices_required'], {'prepared_spells': 1, 'cantrips': 1, 'asi': 1})
        self.assertIn('Mage Armor', preview['prepared_spell_ids'])
        self.assertIn('Shocking Grasp', preview['cantrip_ids'])
        request = self.request(body, preview)
        response = await self.http.post(self.url(body), json=request)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json(); self.assertEqual(result['action_id'], request['action_id'])
        self.assertEqual(result['result']['status'], 'applied')
        c = result['state']['character']
        self.assertEqual((c['level'], c['progression_level'], c['xp'], c['max_hp'], c['current_hp']), (4, 4, 2700, 30, 10))
        self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 2, '2': 2})
        saved = self.store.get_campaign(body['campaign_id']).payload['engine_save']
        self.assertEqual(saved['player']['constitution'], 16)
        self.assertEqual(saved['player']['asi_choices'], [{'class_level': 4, **PICK['asi']}])
        reopened, manager = await self.reopen(body)
        restored = manager.get(reopened['session_id']).game_session
        self.assertEqual((restored.character['max_hp'], restored.character['current_hp'], restored.character['constitution']), (30, 10, 16))
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'], {'1': 2, '2': 2})

    async def test_public_unearned_is_blocked_without_changing_core_compatibility(self):
        import character_progression as cp
        for award in (0, 1799):
            body, record = await self.earned(award)
            before = record.game_session._capture_runtime_snapshot()
            response = await self.http.get(self.url(body))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['status'], 'blocked')
            self.assertEqual(response.json()['reason'], 'level_not_earned')
            self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
            self.assertEqual(cp.preview_level_up(record.game_session, 4)['status'], 'ready')

    async def test_matching_replay_and_conflicting_action_id_never_repeat_asi(self):
        body, record = await self.earned(); request = self.request(body, await self.ready(body))
        first = await self.http.post(self.url(body), json=request)
        self.assertEqual(first.status_code, 200, first.text)
        before = record.game_session._capture_runtime_snapshot()
        revision = self.store.get_campaign(body['campaign_id']).metadata['revision']
        again = await self.http.post(self.url(body), json=request)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json(), first.json())
        changed = copy.deepcopy(request); changed['choices']['cantrips'] = ['Prestidigitation']
        conflict = await self.http.post(self.url(body), json=changed)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).metadata['revision'], revision)
        status = await self.http.get(f"/api/game/sessions/{body['session_id']}/actions/{request['action_id']}")
        self.assertEqual(status.json()['state'], 'applied')

    async def test_stale_preview_and_invalid_choices_have_no_partial_effect(self):
        body, record = await self.earned(); preview = await self.ready(body)
        request = self.request(body, preview)
        self.manager.save_campaign(body['campaign_id'])
        before = record.game_session._capture_runtime_snapshot()
        response = await self.http.post(self.url(body), json=request)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'level_up_preview_stale')
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        request = self.request(body, await self.ready(body))
        request['choices']['asi']['increase'] = {'dexterity': 2}
        bad = await self.http.post(self.url(body), json=request)
        self.assertIn(bad.status_code, (409, 422), bad.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)

    async def test_synthetic_precommit_failure_rolls_back_runtime_and_saved_state(self):
        body, record = await self.earned(); request = self.request(body, await self.ready(body))
        before = record.game_session._capture_runtime_snapshot()
        saved = copy.deepcopy(self.store.get_campaign(body['campaign_id']).payload)
        with patch.object(self.manager, 'save_campaign_locked', side_effect=CampaignStorageError('synthetic precommit failure')):
            response = await self.http.post(self.url(body), json=request)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).payload, saved)
        self.assertIsNone(self.manager.get_turn_action(record, request['action_id']))

    async def test_abandoned_id_and_other_campaign_identity_cannot_apply(self):
        body, record = await self.earned(); request = self.request(body, await self.ready(body))
        abandoned = await self.http.post(f"/api/game/sessions/{body['session_id']}/actions/{request['action_id']}/abandon")
        self.assertEqual(abandoned.status_code, 200, abandoned.text)
        before = record.game_session._capture_runtime_snapshot()
        denied = await self.http.post(self.url(body), json=request)
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        request = self.request(body, await self.ready(body)); request['campaign_id'] = str(uuid4())
        denied = await self.http.post(self.url(body), json=request)
        self.assertEqual(denied.status_code, 409, denied.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)

    async def test_synthetic_committed_ack_loss_retains_state_clears_undo_and_recovers(self):
        body, record = await self.earned(); request = self.request(body, await self.ready(body))
        record.undo_checkpoint = {'synthetic_old_turn': True}
        original = self.manager.save_campaign_locked
        def commit_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise CampaignStorageError('synthetic lost acknowledgement after commit')
        with patch.object(self.manager, 'save_campaign_locked', side_effect=commit_then_fail):
            response = await self.http.post(self.url(body), json=request)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertIsNone(record.undo_checkpoint)
        self.assertEqual(record.game_session.character['constitution'], 16)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).payload['engine_save']['player']['max_hp'], 30)
        status = await self.http.get(f"/api/game/sessions/{body['session_id']}/actions/{request['action_id']}")
        self.assertEqual(status.json()['state'], 'applied')
        self.assertIsNone(status.json()['response'], 'non-turn recovery must not invent a TurnResponse')
        canonical = await self.http.get(f"/api/game/campaigns/{body['campaign_id']}")
        self.assertEqual(canonical.status_code, 200, canonical.text)
        self.assertEqual(canonical.json()['state']['character']['max_hp'], 30)
        retry = await self.http.post(self.url(body), json=request)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()['state']['character']['max_hp'], 30)

    async def test_other_open_action_blocks_level_up_and_retry_keeps_its_identity(self):
        body, record = await self.earned(); request = self.request(body, await self.ready(body))
        other_id = str(uuid4())
        self.manager.claim_action_intent(record, other_id, 'a' * 64)
        before = record.game_session._capture_runtime_snapshot()
        response = await self.http.post(self.url(body), json=request)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'unresolved_action')
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        self.assertEqual(self.manager.unresolved_action(record)['action_id'], other_id)

    async def test_duplicate_concurrent_requests_commit_one_revision_only(self):
        import asyncio
        body, record = await self.earned(); preview = await self.ready(body)
        request = self.request(body, preview)
        responses = await asyncio.gather(*(self.http.post(self.url(body), json=request) for _ in range(2)))
        self.assertEqual([r.status_code for r in responses], [200, 200], [r.text for r in responses])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(self.store.get_campaign(body['campaign_id']).metadata['revision'], preview['revision'] + 1)
        self.assertEqual(record.game_session.character['max_hp'], 30)

    async def test_other_owner_and_stale_session_cannot_mutate(self):
        from api.tests.auth_fixture import PLAYER_B
        body, record = await self.earned(); request = self.request(body, await self.ready(body))
        before = record.game_session._capture_runtime_snapshot()
        app = create_app(session_manager=self.manager, authenticator=FixedAuthenticator(PLAYER_B))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            for response in (await client.get(self.url(body)), await client.post(self.url(body), json=request)):
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        reopened, manager = await self.reopen(body)
        manager.save_campaign(body['campaign_id'])
        stale = await self.http.post(self.url(body), json=request)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()['detail']['code'], 'campaign_stale')
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)

    async def test_strict_payload_rejects_client_numeric_grants_without_intent(self):
        body, record = await self.earned(); base = self.request(body, await self.ready(body))
        for mutate in ('target', 'revision', 'increase', 'extra'):
            request = copy.deepcopy(base)
            if mutate == 'target': request['target_level'] = True
            elif mutate == 'revision': request['expected_revision'] = True
            elif mutate == 'increase': request['choices']['asi']['increase']['constitution'] = 2.0
            else: request['max_hp'] = 999
            before = record.game_session._capture_runtime_snapshot()
            response = await self.http.post(self.url(body), json=request)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
            self.assertIsNone(self.manager.unresolved_action(record))

    async def test_level_up_contract_is_published_with_frozen_operation_ids(self):
        import json
        from pathlib import Path
        import yaml
        actual = self.app.openapi()
        path = '/api/game/sessions/{session_id}/level-up'
        names = [n for n in actual['components']['schemas'] if n.startswith('LevelUp') and n != 'LevelUpResult']
        published = yaml.safe_load((Path(__file__).resolve().parents[3] / 'lib/api-spec/openapi.yaml').read_text())
        if '/game/sessions/{session_id}/level-up' not in published['paths']:
            print('C06_LEVELUP_OPENAPI:' + json.dumps({'path': actual['paths'][path], 'schemas': {n: actual['components']['schemas'][n] for n in names}}))
        self.assertIn('/game/sessions/{session_id}/level-up', published['paths'])
        for method, identity in (('get', 'getGameSessionLevelUp'), ('post', 'applyGameSessionLevelUp')):
            self.assertEqual(actual['paths'][path][method]['operationId'], identity)
            self.assertEqual(published['paths']['/game/sessions/{session_id}/level-up'][method]['operationId'], identity)
        def normalized(value):
            if isinstance(value, dict):
                return {k: normalized(v) for k, v in value.items() if k != 'title'}
            if isinstance(value, list): return [normalized(v) for v in value]
            return value
        for name in names:
            self.assertEqual(normalized(published['components']['schemas'][name]),
                             normalized(actual['components']['schemas'][name]), name)
        documented = published['paths']['/game/sessions/{session_id}/level-up']
        for method in ('get', 'post'):
            self.assertEqual(documented[method]['responses']['200']['content'],
                             actual['paths'][path][method]['responses']['200']['content'])
        self.assertEqual(documented['post']['requestBody'], actual['paths'][path]['post']['requestBody'])
