"""C10 existing HTTP/SQLite boundary: explicit choice, old hashes, real replay.

Breaks caught: schema coercion/default drift; lost typed choice forwarding;
re-executing receipts; changed-body UUID reuse; ownership/stale mutation.
All characters use the real creation owner, never patched final levels.
"""
import copy
import hashlib
import json
import unittest
import httpx
from unittest.mock import patch
from uuid import uuid4

import action_economy as ae
import equipment_economy
import weapon_attack
from api.auth import FixedAuthenticator
from api.main import create_app
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests import test_campaign_api as fixtures
from api.tests.auth_fixture import TEST_PLAYER, PLAYER_B
from api.tests.test_roadmap_c06_barbarian_creation import create_two


class RecklessHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def encounter(self):
        campaign = await self.create_campaign()
        record = self.manager.get(campaign['session_id'])
        s = create_two(record.game_session)
        s.commit_location_change('tavern')
        npc = s.create_npc_from_ai({'name': 'Rakip', 'role': 'Guard', 'location': 'tavern'})
        npc.update(current_hp=100, max_hp=100, armor_class=20, hostile=True,
                   distance_ft=5, attack_damage_type='bludgeoning')
        s.world_state.setdefault('monster_perception', {})[npc['id']] = {'player': {'visible': True}}
        # Tactical weapon fixture, not a class grant or final-level override.
        s.world_state['inventory'].append('Longsword')
        equipment_economy.materialize(s.world_state)
        axe = next(i for i in s.world_state['inventory'] if i.get('weapon_id') == 'longsword')
        s.world_state['equipment'] = {'main_hand': axe['item_id'], 'off_hand': None}
        with patch('game.roll_initiative_player', return_value=20), patch('game.roll_initiative', return_value=1):
            s.start_combat(npc)
        self.manager.save_campaign(campaign['campaign_id'])
        command = {'message': 'Hamle.', 'action_id': str(uuid4()),
                   'combat_action': {'steps': [{'kind': 'attack', 'target_id': npc['id']}]}}
        self.assertEqual((s.character['level'], s.character['progression_level']), (2, 2))
        return campaign, record, command

    async def post(self, campaign, command):
        return await self.http.post(f"/api/game/sessions/{campaign['session_id']}/turn", json=command)

    def snapshot(self, record):
        return copy.deepcopy((record.game_session._capture_runtime_snapshot(),
                              record.journal, record.narrative_memory,
                              record.turn_action_receipts,
                              self.store.get_campaign(record.campaign_id)))

    @staticmethod
    def legacy_hash(command):
        # Frozen pre-C10 representation, explicitly includes the old resource
        # default. Do NOT serialize today's schema to construct this oracle.
        payload = {'message': 'Hamle.', 'target_id': None, 'combat_action': {
            'steps': [{'kind': 'attack', 'resource': 'action',
                       'target_id': command['combat_action']['steps'][0]['target_id']}]}}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                        separators=(',', ':')).encode('utf-8')).hexdigest()

    async def test_typed_true_reaches_real_barbarian_and_exact_replay_has_no_side_effects(self):
        a, record, command = await self.encounter()
        command['combat_action']['steps'][0]['reckless_attack'] = True
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        s = record.game_session
        result = accepted.json()['combat_result']['economy_steps'][0]['result']
        self.assertEqual(result['advantage_sources'], ['reckless_attack'])
        self.assertEqual(len(result['attack_rolls']), 2)
        self.assertTrue(weapon_attack.reckless_state(s)['active'])
        self.assertEqual(weapon_attack.sequence_snapshot(s, 'player')['attack_rolls'], 1)
        effects = [e for e in s.world_state['attack_effects'] if e['kind'] == 'reckless_attack']
        self.assertEqual(len(effects), 1)
        committed = self.snapshot(record)
        # An exact replay must not even enter dice resolution.
        with patch('game.roll_attack', side_effect=AssertionError('Replay rerolled')):
            replay = await self.post(a, command)
        self.assertEqual(replay.json(), accepted.json())
        self.assertEqual(self.snapshot(record), committed)
        altered = copy.deepcopy(command)
        altered['combat_action']['steps'][0]['reckless_attack'] = False
        conflict = await self.post(a, altered)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()['detail']['code'], 'action_id_conflict')
        self.assertEqual(self.snapshot(record), committed)

    async def test_accepted_absent_hash_is_prechange_and_null_replays_but_false_conflicts(self):
        a, record, command = await self.encounter()
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        receipt = self.manager.get_turn_action(record, command['action_id'])
        self.assertEqual(receipt['request_hash'], self.legacy_hash(command))
        self.assertFalse(weapon_attack.reckless_state(record.game_session)['active'])
        self.assertFalse(weapon_attack.reckless_state(record.game_session)['available'])
        committed = self.snapshot(record)
        command['combat_action']['steps'][0]['reckless_attack'] = None
        self.assertEqual((await self.post(a, command)).json(), accepted.json())
        command['combat_action']['steps'][0]['reckless_attack'] = False
        rejected = await self.post(a, command)
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()['detail']['code'], 'action_id_conflict')
        self.assertEqual(self.snapshot(record), committed)

    async def test_prechange_refused_hash_replays_absent_and_null_without_execution(self):
        a, record, command = await self.encounter()
        old_hash = self.legacy_hash(command)
        detail = {'code': 'synthetic_old_refusal', 'message': 'Old request refused.', 'not_applied': True}
        self.assertTrue(self.manager.record_refused_action(record, command['action_id'], old_hash, 409, detail))
        before = self.snapshot(record)
        for step in ({}, {'reckless_attack': None}):
            command['combat_action']['steps'][0].update(step)
            response = await self.post(a, command)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json(), {'detail': detail})
            self.assertEqual(self.manager.get_refused_action(record, command['action_id'])['request_hash'], old_hash)
            self.assertEqual(self.snapshot(record), before)
        command['combat_action']['steps'][0]['reckless_attack'] = False
        self.assertEqual((await self.post(a, command)).json()['detail']['code'], 'action_id_conflict')
        self.assertEqual(self.snapshot(record), before)

    async def test_prechange_pending_hash_accepts_null_then_closes_once(self):
        a, record, command = await self.encounter()
        old_hash = self.legacy_hash(command)
        self.assertEqual(self.manager.claim_action_intent(record, command['action_id'], old_hash)['outcome'], 'claimed')
        self.assertEqual(self.manager.claim_action_intent(record, command['action_id'], old_hash)['outcome'], 'existing')
        before = self.snapshot(record)
        altered = copy.deepcopy(command)
        altered['combat_action']['steps'][0]['reckless_attack'] = False
        response = await self.post(a, altered)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'action_id_conflict')
        self.assertEqual(self.snapshot(record), before)
        command['combat_action']['steps'][0]['reckless_attack'] = None
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.manager.get_turn_action(record, command['action_id'])['request_hash'], old_hash)
        self.assertIsNone(self.manager.unresolved_action(record))
        committed = self.snapshot(record)
        del command['combat_action']['steps'][0]['reckless_attack']
        self.assertEqual((await self.post(a, command)).json(), accepted.json())
        self.assertEqual(self.snapshot(record), committed)

    async def test_strict_invalid_flags_and_unrelated_steps_reject_before_claim(self):
        a, record, command = await self.encounter()
        before = self.snapshot(record)
        for value in ('true', 'false', 0, 1, 0.0, 1.0, [], {}):
            bad = copy.deepcopy(command)
            bad['combat_action']['steps'][0]['reckless_attack'] = value
            with self.subTest(value=value):
                response = await self.post(a, bad)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIsNone(self.manager.unresolved_action(record))
                self.assertEqual(self.snapshot(record), before)
        for kind in ('move', 'ready', 'end_turn'):
            bad = copy.deepcopy(command)
            bad['combat_action']['steps'] = [{'kind': kind, 'reckless_attack': False}]
            response = await self.post(a, bad)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.snapshot(record), before)

    async def test_foreign_owner_and_stale_revision_reject_before_attack_or_claim(self):
        a, record, command = await self.encounter()
        command['combat_action']['steps'][0]['reckless_attack'] = True
        before = self.snapshot(record)
        self.app.state.authenticator = FixedAuthenticator(PLAYER_B)
        try:
            response = await self.post(a, command)
            self.assertEqual(response.status_code, 404, response.text)
        finally:
            self.app.state.authenticator = FixedAuthenticator(TEST_PLAYER)
        self.assertEqual(self.snapshot(record), before)
        self.assertIsNone(self.manager.unresolved_action(record))
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, newer, *_ = fresh.resume_campaign(a['campaign_id'])
        fresh.save_campaign(a['campaign_id'])
        before = self.snapshot(record)
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'campaign_stale')
        self.assertEqual(self.snapshot(record), before)
        self.assertIsNone(self.manager.unresolved_action(record))

    async def test_other_campaign_target_and_stale_combat_context_reject_without_mechanics(self):
        a, record, command = await self.encounter()
        b, other, _ = await self.encounter()
        command['combat_action']['steps'][0]['reckless_attack'] = True
        before_a, before_b = self.snapshot(record), self.snapshot(other)
        combat = record.game_session.world_state['combat']
        command.update(combat_id=combat['combat_id'], combat_round=combat['round'],
                       combat_turn_index=combat['current_turn_index'])
        response = await self.post(b, command)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(other.game_session._capture_runtime_snapshot(), before_b[0])
        self.assertEqual(self.snapshot(record), before_a)
        combat = record.game_session.world_state['combat']
        command.update(combat_id=combat['combat_id'], combat_round=combat['round'] + 1,
                       combat_turn_index=combat['current_turn_index'])
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(record.game_session._capture_runtime_snapshot(), before_a[0])
        self.assertFalse(weapon_attack.reckless_state(record.game_session)['active'])


    async def test_explicit_false_persists_distinct_hash_and_closes_choice(self):
        a, record, command = await self.encounter()
        command['combat_action']['steps'][0]['reckless_attack'] = False
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['combat_result']['economy_steps'][0]['result']
        self.assertNotIn('reckless_attack', result['advantage_sources'])
        self.assertEqual(len(result['attack_rolls']), 1)
        receipt = self.manager.get_turn_action(record, command['action_id'])
        self.assertNotEqual(receipt['request_hash'], self.legacy_hash(command))
        self.assertFalse(weapon_attack.reckless_state(record.game_session)['active'])
        self.assertFalse(weapon_attack.reckless_state(record.game_session)['available'])
        committed = self.snapshot(record)
        command['combat_action']['steps'][0]['reckless_attack'] = True
        self.assertEqual((await self.post(a, command)).json()['detail']['code'], 'action_id_conflict')
        self.assertEqual(self.snapshot(record), committed)

    async def test_http_ready_then_own_turn_first_roll_reaction_accepts_choice(self):
        a, record, command = await self.encounter()
        target = command['combat_action']['steps'][0]['target_id']
        command['combat_action']['steps'] = [
            {'kind': 'ready', 'trigger': {'event': 'actor_moves', 'actor_id': 'player'},
             'response': {'kind': 'attack', 'target_id': target}},
            {'kind': 'move', 'distance_ft': 5}]
        ready = await self.post(a, command)
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertTrue(weapon_attack.reckless_state(record.game_session)['available'])
        opportunity = ae.ensure(record.game_session)['player']['opportunity']['id']
        command = {'message': 'Reaksiyon.', 'action_id': str(uuid4()), 'combat_action': {'steps': [
            {'kind': 'react', 'opportunity_id': opportunity, 'reckless_attack': True}]}}
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['combat_result']['economy_steps'][0]['response']
        self.assertIn('reckless_attack', result['advantage_sources'])
        self.assertEqual(len(result['attack_rolls']), 2)
        self.assertTrue(ae.ensure(record.game_session)['player']['reaction_spent'])
        self.assertTrue(weapon_attack.reckless_state(record.game_session)['active'])
        committed = self.snapshot(record)
        self.assertEqual((await self.post(a, command)).json(), response.json())
        self.assertEqual(self.snapshot(record), committed)

    async def test_http_readied_movement_rejects_flag_without_consuming_opportunity(self):
        a, record, command = await self.encounter()
        s = record.game_session
        ae.prepare_ready(s, 'player', {'event': 'actor_moves', 'actor_id': 'player'},
                         {'kind': 'move', 'distance_ft': 5})
        ae.move(s, 'player', 5)
        self.manager.save_campaign(a['campaign_id'])
        before = s._capture_runtime_snapshot()
        command['combat_action']['steps'] = [{'kind': 'react',
            'opportunity_id': ae.ensure(s)['player']['opportunity']['id'], 'reckless_attack': False}]
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()['detail']['code'], 'invalid_attack_choice')
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertFalse(ae.ensure(s)['player']['reaction_spent'])
        self.assertTrue(weapon_attack.reckless_state(s)['available'])

    async def test_fresh_manager_replays_stored_reckless_without_reroll_or_duplicate_effect(self):
        a, record, command = await self.encounter()
        command['combat_action']['steps'][0]['reckless_attack'] = True
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        old_rng = record.game_session.rng.getstate()
        self.manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        sid, restored, *_ = self.manager.resume_campaign(a['campaign_id'])
        self.assertEqual(restored.game_session.rng.getstate(), old_rng)
        self.assertTrue(weapon_attack.reckless_state(restored.game_session)['active'])
        adapter = self.app.state.ollama_adapter
        await self.http.aclose()
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter,
                              authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver')
        a['session_id'] = sid
        committed = self.snapshot(restored)
        with patch('game.roll_attack', side_effect=AssertionError('Restored replay rerolled')):
            replay = await self.post(a, command)
        self.assertEqual(replay.status_code, 200, replay.text)
        expected = accepted.json()
        expected['session_id'] = sid  # existing replay owner intentionally rebinds envelope
        self.assertEqual(replay.json(), expected)
        self.assertEqual(self.snapshot(restored), committed)
        self.assertEqual(weapon_attack.sequence_snapshot(restored.game_session, 'player')['attack_rolls'], 1)
        self.assertEqual(len([e for e in restored.game_session.world_state['attack_effects']
                              if e['kind'] == 'reckless_attack']), 1)

    async def test_http_save_failure_rolls_back_reckless_rng_count_then_retry_commits_once(self):
        a, record, command = await self.encounter()
        command['combat_action']['steps'][0]['reckless_attack'] = True
        before = self.snapshot(record)
        with patch.object(self.manager, 'autosave_turn', side_effect=RuntimeError('synthetic save failure')):
            failed = await self.post(a, command)
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(self.snapshot(record), before)
        self.assertTrue(weapon_attack.reckless_state(record.game_session)['available'])
        self.assertFalse(weapon_attack.reckless_state(record.game_session)['active'])
        self.assertIsNone(self.manager.get_turn_action(record, command['action_id']))
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(weapon_attack.sequence_snapshot(record.game_session, 'player')['attack_rolls'], 1)
        self.assertTrue(weapon_attack.reckless_state(record.game_session)['active'])
        committed = self.snapshot(record)
        self.assertEqual((await self.post(a, command)).json(), accepted.json())
        self.assertEqual(self.snapshot(record), committed)

if __name__ == '__main__':
    unittest.main()
