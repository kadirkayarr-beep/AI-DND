"""Bounded earned Barbarian 5 via actual ASGI HTTP and synthetic SQLite campaigns (empty choice object, no new schema)."""
import copy
import unittest
from uuid import uuid4
from unittest.mock import patch

import xp
from api.tests import test_roadmap_c06_barbarian_level4_http as four
from api.tests import test_roadmap_c06_level4_http as sorcerer


class BarbarianFiveHttpTests(unittest.IsolatedAsyncioTestCase):
    # Harness reuse only (same ASGI app / synthetic SQLite store as the Barbarian-4 module).
    asyncSetUp = four.BarbarianFourHttpTests.asyncSetUp
    asyncTearDown = four.BarbarianFourHttpTests.asyncTearDown
    reopen = four.BarbarianFourHttpTests.reopen
    snapshot = four.BarbarianFourHttpTests.snapshot
    url = four.BarbarianFourHttpTests.url
    preview = four.BarbarianFourHttpTests.preview
    command = four.BarbarianFourHttpTests.command
    pick = four.BarbarianFourHttpTests.pick
    ready = four.BarbarianFourHttpTests.ready

    async def earned_pending_five(self):
        a, r = await four.BarbarianFourHttpTests.earned(self)
        response = await self.http.post(self.url(a), json=self.command(a, self.pick(), await self.ready(a)))
        self.assertEqual(response.status_code, 200, response.text)
        s = r.game_session
        s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 3800, 'quest:synthetic-earned-five-http')
        self.manager.save_campaign(a['campaign_id'])
        return a, r

    async def ready_five(self, a):
        p = await self.preview(a)
        self.assertEqual((p['status'], p['target_level']), ('ready', 5), p)
        return p

    def five(self, a, p, choices=None):
        return self.command(a, {} if choices is None else choices, p)

    async def test_request_shape_empty_object_only_for_barbarian_five(self):
        from api.schemas import LevelUpApplyRequest
        command = {'action_id': str(uuid4()), 'campaign_id': str(uuid4()), 'expected_revision': 0, 'target_level': 5, 'choices': {}}
        parsed = LevelUpApplyRequest.model_validate(command)
        self.assertEqual(parsed.model_dump(mode='json'), command)
        for choices in ({'asi': {'feat': 'Ability Score Improvement', 'increase': {'strength': 2}}}, {'extra': None}, None, []):
            with self.assertRaises(ValueError):
                LevelUpApplyRequest.model_validate({**command, 'choices': choices})
        # The same empty object is still not a level-4 body, and the level-4 body is not a level-5 body.
        with self.assertRaises(ValueError):
            LevelUpApplyRequest.model_validate({**command, 'target_level': 4})

    async def test_actual_public_preview_empty_choices_effects_and_no_mutation(self):
        a, r = await self.earned_pending_five(); before = self.snapshot(r)
        p = await self.ready_five(a)
        self.assertEqual((p['class_name'], p['from_level']), ('Barbarian', 4))
        self.assertEqual(p['choices_required'], {})
        self.assertIsNone(p['capacity'])
        self.assertEqual((p['supported_asi_choices'], p['prepared_spell_ids'], p['cantrip_ids']), ([], [], []))
        supported = ' '.join(p['effects_supported'])
        self.assertIn('Extra Attack', supported)
        self.assertIn('Fast Movement', supported)
        self.assertIn('Weapon Mastery', ' '.join(p['effects_pending']))
        self.assertEqual(self.snapshot(r), before)

    async def test_unearned_five_and_applied_ceiling(self):
        a, r = await four.BarbarianFourHttpTests.earned(self)
        response = await self.http.post(self.url(a), json=self.command(a, self.pick(), await self.ready(a)))
        self.assertEqual(response.status_code, 200, response.text)
        p = await self.preview(a)
        self.assertEqual((p['status'], p['reason'], p['target_level']), ('blocked', 'level_not_earned', 5))
        before = self.snapshot(r)
        response = await self.http.post(self.url(a), json=self.five(a, p))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.snapshot(r), before)

    async def test_earned_five_apply_persist_replay_and_conflict(self):
        a, r = await self.earned_pending_five(); s = r.game_session
        s.world_state['rage_v1']['remaining'] = 1
        s.character['hit_dice'] = {'spent': 2, 'window_second': None, 'hp': None}
        before = copy.deepcopy((s.character['max_hp'], s.character['current_hp'], s.character['hit_dice'], s.world_state['rage_v1'],
                                s.world_state['inventory'], s.world_state.get('campaign_time'), s.rng.getstate()))
        self.manager.save_campaign(a['campaign_id'])
        p = await self.ready_five(a); command = self.five(a, p)
        response = await self.http.post(self.url(a), json=command)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['result']['changes'], [{'kind': 'level', 'from': 4, 'to': 5}])
        c = body['state']['character']
        self.assertEqual((c['level'], c['proficiency_bonus'], c['rage']['max_uses']), (5, 3, 3))
        self.assertEqual(s.character['progression_level'], 5)
        self.assertEqual(copy.deepcopy((s.character['max_hp'], s.character['current_hp'], s.character['hit_dice'], s.world_state['rage_v1'],
                                        s.world_state['inventory'], s.world_state.get('campaign_time'), s.rng.getstate())), before)
        text = ' '.join(c['progression_effects_pending'])
        self.assertIn('Extra Attack', text); self.assertIn('Fast Movement', text)
        runtime = copy.deepcopy(s.serialize_game_state()); r = await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(), runtime)
        expected = body; expected['session_id'] = a['session_id']; snapshot = self.snapshot(r)
        with patch('character_progression.apply_level_choices', side_effect=AssertionError('level 5 replayed')):
            self.assertEqual((await self.http.post(self.url(a), json=command)).json(), expected)
        self.assertEqual(self.snapshot(r), snapshot)
        changed = copy.deepcopy(command); changed['choices'] = {'prepared_spells': ['Fog Cloud', 'Silent Image']}
        conflict = await self.http.post(self.url(a), json=changed)
        self.assertEqual(conflict.status_code, 409); self.assertEqual(conflict.json()['detail']['code'], 'action_id_conflict')
        p = await self.preview(a)
        self.assertEqual((p['status'], p['reason'], p['target_level']), ('blocked', 'target_not_above_applied_level', 5))

    async def test_class_mismatch_and_bad_bodies_never_mutate(self):
        a, r = await self.earned_pending_five(); p = await self.ready_five(a); before = self.snapshot(r)
        mismatch = self.command(a, {'prepared_spells': ['Fog Cloud', 'Silent Image']}, p)
        response = await self.http.post(self.url(a), json=mismatch)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'level_up_choice_class_mismatch')
        for choices in ({'asi': {'feat': 'Ability Score Improvement', 'increase': {'strength': 2}}}, {'extra': None}, None, [], {'subclass_id': 'berserker'}):
            response = await self.http.post(self.url(a), json=self.command(a, choices, p))
            self.assertEqual(response.status_code, 422, response.text)
        stale = self.five(a, {**p, 'revision': p['revision'] - 1})
        self.assertEqual((await self.http.post(self.url(a), json=stale)).status_code, 409)
        self.assertEqual(self.snapshot(r), before)

    async def test_sorcerer_cannot_use_the_empty_barbarian_body_for_five(self):
        a, r = await sorcerer.LevelFourHttpTests.earned(self)
        s = r.game_session
        response = await self.http.post(self.url(a), json=sorcerer.LevelFourHttpTests.request(self, a, await self.preview(a)))
        self.assertEqual(response.status_code, 200, response.text)
        s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 3800, 'quest:synthetic-sorcerer-five-mismatch')
        self.manager.save_campaign(a['campaign_id'])
        p = await self.preview(a); before = self.snapshot(r)
        self.assertEqual((p['status'], p['target_level'], p['class_name']), ('ready', 5, 'Sorcerer'))
        response = await self.http.post(self.url(a), json=self.command(a, {}, p))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'level_up_choice_class_mismatch')
        self.assertEqual(self.snapshot(r), before)

    async def test_missing_source_refuses_without_adoption(self):
        for source in ('rage_v1', 'worn_armor_v1', 'primal_knowledge_choice', 'asi_choices'):
            a, r = await self.earned_pending_five(); s = r.game_session
            (s.character if source in ('primal_knowledge_choice', 'asi_choices') else s.world_state).pop(source)
            before = s._capture_runtime_snapshot()
            p = await self.preview(a)
            self.assertEqual(p['status'], 'blocked', (source, p))
            command = self.five(a, {**p, 'target_level': 5})
            response = await self.http.post(self.url(a), json=command)
            self.assertEqual(response.status_code, 409, (source, response.text))
            self.assertEqual(s._capture_runtime_snapshot(), before)

    async def test_precommit_failure_restores_everything_then_exact_retry_applies(self):
        from api.persistence.campaign_models import CampaignStorageError
        a, r = await self.earned_pending_five(); s = r.game_session
        p = await self.ready_five(a); command = self.five(a, p); before = self.snapshot(r)
        with patch.object(self.manager, 'save_campaign_locked', side_effect=CampaignStorageError('synthetic Barbarian5 precommit')):
            response = await self.http.post(self.url(a), json=command)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertEqual(self.snapshot(r), before)
        self.assertEqual(s.character['progression_level'], 4)
        response = await self.http.post(self.url(a), json=command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(s.character['progression_level'], 5)


if __name__ == '__main__':
    unittest.main()
