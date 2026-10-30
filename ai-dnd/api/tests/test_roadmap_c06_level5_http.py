"""Actual existing HTTP owner, selected5 and XP-ahead prior4 choices."""
import copy
import unittest
from uuid import uuid4
from api.tests import test_roadmap_c06_level4_http as previous
from api.tests.test_roadmap_c06_level5 import award, FIVE

class LevelFiveHttpTests(previous.LevelFourHttpTests):
    async def test_actual_four_to_five_preview_apply_replay_and_fresh_resume(self):
        body, record = await self.earned()
        response = await self.http.post(self.url(body), json=self.request(body, await self.ready(body)))
        self.assertEqual(response.status_code, 200, response.text)
        award(record.game_session, 3800, 'quest:http-five')
        self.manager.save_campaign(body['campaign_id'])
        response = await self.http.get(self.url(body)); p = response.json()
        self.assertEqual(p['status'], 'ready', p)
        self.assertEqual(p['target_level'], 5)
        self.assertEqual(p['choices_required'], {'prepared_spells': 2})
        self.assertEqual(p['cantrip_ids'], []); self.assertEqual(p['supported_asi_choices'], [])
        request = {'action_id': str(uuid4()), 'campaign_id': body['campaign_id'], 'expected_revision': p['revision'], 'target_level': 5, 'choices': copy.deepcopy(FIVE)}
        response = await self.http.post(self.url(body), json=request)
        self.assertEqual(response.status_code, 200, response.text)
        revision = self.store.get_campaign(body['campaign_id']).metadata['revision']
        repeated = await self.http.post(self.url(body), json=request)
        self.assertEqual(repeated.json(), response.json())
        self.assertEqual(self.store.get_campaign(body['campaign_id']).metadata['revision'], revision)
        reopened, manager = await self.reopen(body)
        s = manager.get(reopened['session_id']).game_session
        self.assertEqual((s.character['progression_level'], s.character['max_hp'], len(s.character['spells'])), (5, 37, 9))
        self.assertEqual(s._persisted_engine_format, 6)

    async def test_public_raw_five_still_requires_prior_four_choices(self):
        body, record = await self.earned(0)
        award(record.game_session, 5600, 'quest:jump-five-http')
        self.manager.save_campaign(body['campaign_id'])
        p = await self.ready(body)
        response = await self.http.post(self.url(body), json=self.request(body, p))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(record.game_session.character['level'], 5)
        response = await self.http.get(self.url(body))
        self.assertEqual(response.json()['target_level'], 5)

    async def test_outer_turn_save_failure_restores_pre_award_format_and_remains_usable(self):
        from unittest.mock import patch
        from api.persistence.campaign_models import CampaignStorageError
        body, record = await self.earned()
        self.assertEqual((await self.http.post(self.url(body), json=self.request(body, await self.ready(body)))).status_code, 200)
        s = record.game_session
        award(s, 3799, 'quest:below-five'); self.manager.save_campaign(body['campaign_id'])
        before = s._capture_runtime_snapshot()
        old_saved = copy.deepcopy(self.store.get_campaign(body['campaign_id']).payload)
        reached = []
        def synthetic_turn(message, **kwargs):
            summary = award(s, 1, 'quest:outer-five')
            reached.append((s.character['level'], s._persisted_engine_format))
            return {'action_result': {'action': 'wait', 'status': 'resolved', 'level_up': summary}, 'narration': 'Synthetic XP boundary.'}
        with patch.object(s, 'run_player_turn', side_effect=synthetic_turn), patch.object(self.manager, 'autosave_turn', side_effect=CampaignStorageError('synthetic precommit after XP')):
            response = await self.http.post(f"/api/game/sessions/{body['session_id']}/turn", json={'message':'Bekle','action_id':str(uuid4())})
        self.assertEqual(reached, [(5, 6)])
        self.assertEqual(s._persisted_engine_format, 4)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).payload, old_saved)
        state = await self.http.get(f"/api/game/sessions/{body['session_id']}/state")
        self.assertEqual(state.status_code, 200, state.text)

    async def five_request(self):
        body, record = await self.earned()
        self.assertEqual((await self.http.post(self.url(body), json=self.request(body, await self.ready(body)))).status_code, 200)
        award(record.game_session, 3800, 'quest:five-http-boundary'); self.manager.save_campaign(body['campaign_id'])
        p = (await self.http.get(self.url(body))).json()
        return body, record, {'action_id': str(uuid4()), 'campaign_id': body['campaign_id'], 'expected_revision': p['revision'], 'target_level': 5, 'choices': copy.deepcopy(FIVE)}

    async def test_selected_five_precommit_and_lost_ack_use_existing_receipt_boundary(self):
        from unittest.mock import patch
        from api.persistence.campaign_models import CampaignStorageError
        body, record, request = await self.five_request()
        before = record.game_session._capture_runtime_snapshot()
        saved = copy.deepcopy(self.store.get_campaign(body['campaign_id']).payload)
        with patch.object(self.manager, 'save_campaign_locked', side_effect=CampaignStorageError('synthetic precommit selected5')):
            response = await self.http.post(self.url(body), json=request)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).payload, saved)
        # Precommit server failure retains pending intent: retry exact original identity/body.
        original = self.manager.save_campaign_locked
        def commit_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise CampaignStorageError('synthetic postcommit selected5')
        record.undo_checkpoint = {'old': True}
        with patch.object(self.manager, 'save_campaign_locked', side_effect=commit_then_fail):
            response = await self.http.post(self.url(body), json=request)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertIsNone(record.undo_checkpoint)
        status = await self.http.get(f"/api/game/sessions/{body['session_id']}/actions/{request['action_id']}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()['state'], 'applied'); self.assertIsNone(status.json()['response'])
        self.assertEqual((await self.http.post(self.url(body), json=request)).status_code, 200)
        self.assertEqual(record.game_session.character['progression_level'], 5)

    async def test_selected_five_shape_target_and_revision_reject_without_partial_state(self):
        body, record, request = await self.five_request()
        for change in ({'choices': {**FIVE, 'cantrips': []}}, {'choices': {'prepared_spells': ['Fog Cloud']}},
                       {'choices': copy.deepcopy(previous.PICK)}, {'target_level': 4}, {'target_level': True}):
            bad = {**copy.deepcopy(request), **change, 'action_id': str(uuid4())}
            before = record.game_session._capture_runtime_snapshot()
            response = await self.http.post(self.url(body), json=bad)
            # One prepared spell is the exact Paladin 5 shape, so it parses and the route refuses the class instead.
            one_spell = change == {'choices': {'prepared_spells': ['Fog Cloud']}}
            self.assertEqual(response.status_code, 409 if one_spell else 422, response.text)
            if one_spell:
                self.assertEqual(response.json()['detail']['code'], 'level_up_choice_class_mismatch')
            self.assertEqual(record.game_session._capture_runtime_snapshot(), before)
        stale = {**request, 'expected_revision': request['expected_revision'] - 1}
        response = await self.http.post(self.url(body), json=stale)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(record.game_session.character['progression_level'], 4)
