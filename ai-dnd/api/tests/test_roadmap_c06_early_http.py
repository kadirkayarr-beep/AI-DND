"""Public early earned transitions; real engine/HTTP/SQLite, synthetic XP events."""
import copy
import hashlib
import json
import unittest
from uuid import uuid4
from pydantic import ValidationError
from api.schemas import LevelUpApplyRequest
from api.tests import test_campaign_api as campaigns
from api.tests import test_roadmap_c06_level4_http as previous
from api.tests.test_roadmap_c06_creation_http import character_request
from api.tests.test_roadmap_c06_barbarian import spec
from api.tests.test_roadmap_c06_level3 import TWO, choices as THREE
from api.tests.test_roadmap_c06_level4_con import PICK
from api.tests.test_roadmap_c06_level5 import award, FIVE


class EarlyHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown
    url = previous.LevelFourHttpTests.url
    reopen = previous.LevelFourHttpTests.reopen

    async def start(self, class_name='Sorcerer', amount=300):
        data = character_request(1)
        if class_name == 'Barbarian':
            data = spec(); data['class'] = data.pop('character_class'); data.update(mode='custom', starting_level=1)
        response = await self.http.post('/api/game/campaigns', json={'character': data})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json(); s = self.manager.get(body['session_id']).game_session
        award(s, amount, 'quest:early-earned')
        self.manager.save_campaign(body['campaign_id'])
        return body, s

    async def preview(self, body, target):
        response = await self.http.get(self.url(body))
        self.assertEqual(response.status_code, 200, response.text)
        p = response.json(); self.assertEqual(p['status'], 'ready', p)
        self.assertEqual(p['target_level'], target)
        return p

    def request(self, body, p, choice):
        return dict(action_id=str(uuid4()), campaign_id=body['campaign_id'], expected_revision=p['revision'], target_level=p['target_level'], choices=copy.deepcopy(choice))

    async def test_real_sorcerer_two_three_preserve_spent_pool_and_fresh_restore(self):
        body, s = await self.start(); s.world_state['spellcasting_v1']['slots']['1'] = 1
        self.manager.save_campaign(body['campaign_id'])
        p = await self.preview(body, 2)
        self.assertEqual(p['choices_required'], {'prepared_spells': 2, 'metamagic': 2})
        self.assertIn('Quickened Spell', p['metamagic_options'])
        request = self.request(body, p, TWO)
        response = await self.http.post(self.url(body), json=request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 2})
        self.assertEqual((s.character['max_hp'], s.character['xp']), (14, 300))
        self.assertEqual((await self.http.post(self.url(body), json=request)).json(), response.json())
        award(s, 600, 'quest:early-three'); self.manager.save_campaign(body['campaign_id'])
        p = await self.preview(body, 3)
        self.assertIn(THREE()['subclass_id'], [x['id'] for x in p['subclass_options']])
        response = await self.http.post(self.url(body), json=self.request(body, p, THREE()))
        self.assertEqual(response.status_code, 200, response.text)
        restored, manager = await self.reopen(body); t = manager.get(restored['session_id']).game_session
        self.assertEqual((t.character['progression_level'], t.character['xp'], t.character['max_hp']), (3, 900, 20))
        self.assertEqual(t.world_state['spellcasting_v1']['slots'], {'1': 3, '2': 2})
        self.assertEqual(t.character['metamagic'], TWO['metamagic'])

    async def test_barbarian_empty_choices_no_caster_state_and_ceiling(self):
        body, s = await self.start('Barbarian')
        s.character['hit_dice'] = {'spent': 1, 'window_second': None, 'hp': None}
        self.manager.save_campaign(body['campaign_id'])
        p = await self.preview(body, 2)
        self.assertEqual(p['choices_required'], {}); self.assertIsNone(p['capacity'])
        self.assertTrue(any('Reckless Attack' in value for value in p['effects_supported']))
        self.assertFalse(any('Reckless Attack' in value for value in p['effects_pending']))
        self.assertTrue(any('other save routes' in value for value in p['effects_pending']))
        response = await self.http.post(self.url(body), json=self.request(body, p, {}))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('spellcasting_v1', s.world_state)
        self.assertEqual(s.character['hit_dice']['spent'], 1)
        self.assertEqual((s.character['progression_level'], s.character['max_hp'], s.character['xp']), (2, 23, 300))
        response = await self.http.get(self.url(body)); self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'blocked')

    async def test_raw_five_queue_applies_each_step_without_xp_or_base_hp_again(self):
        body, s = await self.start(amount=6500)
        self.assertEqual((s.character['level'], s.character['max_hp']), (5, 32))
        history = copy.deepcopy(s.world_state['xp_awarded_event_ids'])
        for target, choice, maximum in [(2, TWO, 32), (3, THREE(), 32), (4, PICK, 37), (5, FIVE, 37)]:
            p = await self.preview(body, target)
            response = await self.http.post(self.url(body), json=self.request(body, p, choice))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual((s.character['progression_level'], s.character['max_hp'], s.character['xp']), (target, maximum, 6500))
            self.assertEqual(s.world_state['xp_awarded_event_ids'], history)
        response = await self.http.get(self.url(body)); self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'blocked'); self.assertLessEqual(response.json()['target_level'], 5)

    async def test_malformed_present_marker_blocks_without_defaulting_or_mutation(self):
        body, s = await self.start()
        for value in (True, 0, '1', None):
            s.character['progression_level'] = value
            before = s._capture_runtime_snapshot()
            response = await self.http.get(self.url(body))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['status'], 'blocked')
            self.assertEqual(s._capture_runtime_snapshot(), before)

    async def test_absent_legacy_marker_uses_admitted_level_one_choices(self):
        body, s = await self.start()
        s.character.pop('progression_level', None)
        # The production save boundary, not a fabricated migration, admits this state.
        self.manager.save_campaign(body['campaign_id'])
        p = await self.preview(body, 2)
        response = await self.http.post(self.url(body), json=self.request(body, p, TWO))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(s.character['progression_level'], 2)

    async def test_invalid_previous_spell_state_blocks_before_choice_reads(self):
        body, s = await self.start()
        s.world_state.pop('spellcasting_v1')
        before = s._capture_runtime_snapshot()
        response = await self.http.get(self.url(body))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'blocked')
        self.assertNotEqual(response.json()['reason'], 'level_not_earned')
        self.assertEqual(s._capture_runtime_snapshot(), before)

    async def test_applied_five_ceiling_stays_bounded_blocked_response(self):
        data = character_request(3)
        data['starting_level'] = 5
        data['level_choices'].update({'4': copy.deepcopy(PICK), '5': copy.deepcopy(FIVE)})
        response = await self.http.post('/api/game/campaigns', json={'character': data})
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.http.get(self.url(response.json()))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'blocked')
        self.assertEqual(response.json()['target_level'], 5)

    async def test_preflight_requires_exact_prior_spell_counts_mirrors_and_valid_noncasters(self):
        for change in ('short_cantrips', 'short_prepared', 'mirror', 'slot_mirror'):
            body, session = await self.start()
            state = session.world_state['spellcasting_v1']
            if change == 'short_cantrips':
                state['cantrips'].pop(); session.character['cantrips'] = list(state['cantrips'])
            elif change == 'short_prepared':
                state['prepared'].pop(); session.character['spells'] = list(state['prepared'])
            elif change == 'mirror': session.character['spells'] = []
            else: session.character['spell_slots_remaining'] = {'1': 999}
            before = session._capture_runtime_snapshot()
            response = await self.http.get(self.url(body))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['reason'], 'previous_progression_state_invalid')
            self.assertEqual(session._capture_runtime_snapshot(), before)
        body, session = await self.start('Barbarian')
        session.world_state['spellcasting_v1'] = None
        before = session._capture_runtime_snapshot()
        response = await self.http.get(self.url(body))
        self.assertEqual(response.json()['status'], 'blocked')
        self.assertEqual(session._capture_runtime_snapshot(), before)

    async def test_invalid_early_choices_and_wrong_class_shape_reject_without_mutation(self):
        for cls, bad in [('Sorcerer', {}), ('Sorcerer', {**TWO, 'metamagic':['Quickened Spell']*2}),
                         ('Sorcerer', {**TWO, 'prepared_spells':['Shield','Burning Hands']}), ('Barbarian', TWO)]:
            body, session = await self.start(cls); p = await self.preview(body, 2)
            before = session._capture_runtime_snapshot()
            response = await self.http.post(self.url(body), json=self.request(body, p, bad))
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(session._capture_runtime_snapshot(), before)

    async def test_early_precommit_then_commit_unacknowledged_preserves_durable_recovery(self):
        from unittest.mock import patch
        from api.persistence.campaign_models import CampaignStorageError
        body, session = await self.start(); request = self.request(body, await self.preview(body, 2), TWO)
        record = self.manager.get(body['session_id'])
        before = session._capture_runtime_snapshot(); saved = copy.deepcopy(self.store.get_campaign(body['campaign_id']).payload)
        with patch.object(self.manager, 'save_campaign_locked', side_effect=CampaignStorageError('synthetic before commit')):
            response = await self.http.post(self.url(body), json=request)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).payload, saved)
        original = self.manager.save_campaign_locked
        def commit_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise CampaignStorageError('synthetic lost acknowledgement')
        record.undo_checkpoint = {'old': True}
        with patch.object(self.manager, 'save_campaign_locked', side_effect=commit_then_fail):
            response = await self.http.post(self.url(body), json=request)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertIsNone(record.undo_checkpoint)
        status = await self.http.get(f"/api/game/sessions/{body['session_id']}/actions/{request['action_id']}")
        self.assertEqual(status.json()['state'], 'applied'); self.assertIsNone(status.json()['response'])
        before = session._capture_runtime_snapshot()
        repeated = await self.http.post(self.url(body), json=request)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(session._capture_runtime_snapshot(), before)
        restored, manager = await self.reopen(body)
        self.assertEqual(manager.get(restored['session_id']).game_session.character['progression_level'], 2)

    async def test_real_factory_openapi_matches_published_new_contract(self):
        import yaml
        from pathlib import Path
        runtime = self.app.openapi()['components']['schemas']
        published = yaml.safe_load((Path(__file__).resolve().parents[3]/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']
        def normalize(value):
            if isinstance(value, dict): return {k:normalize(v) for k,v in value.items() if k not in ('title','description')}
            if isinstance(value, list): return [normalize(v) for v in value]
            return value
        for name in ('LevelUpApplyRequest','LevelUpPreviewResponse','BarbarianLevel2Choices','SorcererLevel2Choices','SorcererLevel3Choices','LevelUpChoices','LevelUpFiveChoices'):
            self.assertEqual(normalize(runtime[name]), normalize(published[name]), name)

    async def test_actual_sql_update_then_fault_rolls_back_early_choice_and_receipt(self):
        import sqlite3
        from contextlib import contextmanager
        from unittest.mock import patch
        body, session = await self.start()
        request = self.request(body, await self.preview(body, 2), TWO)
        before = session._capture_runtime_snapshot()
        saved = copy.deepcopy(self.store.get_campaign(body['campaign_id']).payload)
        real_transaction = self.store._transaction
        reached = []
        @contextmanager
        def fail_after_actual_update():
            with real_transaction() as connection:
                yield connection
                raw = connection.execute('SELECT payload_json FROM campaigns WHERE campaign_id=?', (body['campaign_id'],)).fetchone()[0]
                player = json.loads(raw)['engine_save']['player']
                if player.get('progression_level') == 2:
                    reached.append(player['metamagic'])
                    raise sqlite3.OperationalError('synthetic after actual early-level UPDATE')
        with patch.object(self.store, '_transaction', side_effect=fail_after_actual_update):
            response = await self.http.post(self.url(body), json=request)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertTrue(reached)
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertEqual(self.store.get_campaign(body['campaign_id']).payload, saved)
        with self.store._connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM campaign_turn_actions WHERE campaign_id=?',(body['campaign_id'],)).fetchone()[0], 0)
        self.assertEqual((await self.http.get(self.url(body))).status_code, 200)

    async def test_threshold_and_stale_step_never_grant_unearned_or_skip_choices(self):
        body, session = await self.start(amount=299)
        response = await self.http.get(self.url(body))
        self.assertEqual(response.json()['reason'], 'level_not_earned')
        award(session, 1, 'quest:threshold-three-hundred'); self.manager.save_campaign(body['campaign_id'])
        p = await self.preview(body, 2)
        before = session._capture_runtime_snapshot()
        wrong = self.request(body, p, THREE()); wrong['target_level'] = 3
        response = await self.http.post(self.url(body), json=wrong)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(session._capture_runtime_snapshot(), before)
        stale = self.request(body, p, TWO); stale['expected_revision'] -= 1
        self.assertEqual((await self.http.post(self.url(body), json=stale)).status_code, 409)
        self.assertEqual(session._capture_runtime_snapshot(), before)


class EarlyShapeTests(unittest.TestCase):
    def body(self, target, choice):
        return dict(action_id='22222222-2222-4222-8222-222222222222', campaign_id='11111111-1111-4111-8111-111111111111', expected_revision=7, target_level=target, choices=choice)

    def test_prechange_four_five_hash_literal_oracles(self):
        for target, choice, expected in [(4, PICK, '0556daebb0afd76901922df2334c81c4e300462dc860ffe54321a224146c3350'), (5, FIVE, '2e7b591cabe3af4f4ac93a193b5ce33ca93caac60b8fb0d426ae380670bb037c')]:
            value = LevelUpApplyRequest.model_validate(self.body(target, choice))
            raw = json.dumps({'command': 'level_up', **value.model_dump(mode='json', exclude={'action_id'})}, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
            self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(), expected)

    def test_exact_early_shapes_accept_and_empty_extra_null_reject(self):
        for target, choice in [(2, {}), (2, TWO), (3, THREE()), (5, {})]:
            try: value = LevelUpApplyRequest.model_validate(self.body(target, choice))
            except ValidationError as error: self.fail(f'valid early shape rejected: {error}')
            self.assertEqual(value.model_dump(mode='json')['choices'], choice)
        for target, choice in [(2, None), (2, {'unknown': 1}), (2, {'prepared_spells': []}), (3, {}), (3, TWO), (4, {}), (5, {'unknown': 1}), (5, TWO)]:
            with self.assertRaises(ValidationError): LevelUpApplyRequest.model_validate(self.body(target, choice))
