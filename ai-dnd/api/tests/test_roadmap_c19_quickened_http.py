"""Selected Quickened Magic Missile HTTP durability and legacy wire contract."""
import copy
import hashlib
import json
import unittest
from uuid import uuid4
from unittest.mock import patch
import httpx
import character_progression as cp
from api.auth import FixedAuthenticator
from api.main import create_app
from api.schemas import EconomyStepInput
from api.serializers import serialize_session_state
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.tests import test_campaign_api as fixtures
from api.tests.auth_fixture import TEST_PLAYER, PLAYER_B
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_level3 import TWO


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class QuickenedHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown
    create_campaign = fixtures.CampaignApiTests.create_campaign

    async def encounter(self, legacy=False):
        a = await self.create_campaign()
        record = self.manager.get(a['session_id']); s = record.game_session
        cp.create_at_level(s, SPEC, 2, {'2': copy.deepcopy(TWO)})
        if legacy:
            s.world_state.pop('sorcery_points_v1', None)
        s.commit_location_change('tavern')
        npc = s.create_npc_from_ai({'name': 'Rakip', 'role': 'Guard', 'location': 'tavern'})
        npc.update(current_hp=100, max_hp=100, armor_class=20, hostile=True, distance_ft=5, attack_damage_type='bludgeoning')
        s.world_state.setdefault('monster_perception', {})[npc['id']] = {'player': {'visible': True}}
        with patch('game.roll_initiative_player', return_value=20), patch('game.roll_initiative', return_value=1):
            s.start_combat(npc)
        s.world_state['attack_environment'] = {'pairs': {'player|' + npc['id']: {
            'distance_ft': 5, 'attacker_sees_target': True, 'target_sees_attacker': True, 'cover': 'none'}}}
        self.manager.save_campaign(a['campaign_id'])
        command = {'message': 'Hamle.', 'action_id': str(uuid4()), 'combat_action': {'steps': [
            {'kind': 'magic', 'ability': 'Magic Missile', 'target_id': npc['id'], 'slot_level': 1}]}}
        return a, record, command

    async def post(self, a, command):
        return await self.http.post(f"/api/game/sessions/{a['session_id']}/turn", json=command)

    def snapshot(self, r):
        return copy.deepcopy((r.game_session._capture_runtime_snapshot(), r.journal, r.narrative_memory,
                              r.turn_action_receipts, self.store.get_campaign(r.campaign_id)))

    async def test_legacy_literal_hash_and_absent_projection_freeze(self):
        a, r, command = await self.encounter(legacy=True)
        target = command['combat_action']['steps'][0]['target_id']
        frozen = {'message': 'Hamle.', 'target_id': None, 'combat_action': {'steps': [
            {'kind': 'magic', 'resource': 'action', 'ability': 'Magic Missile', 'target_id': target, 'slot_level': 1}]}}
        # Literal canonical request oracle does not consult today's Pydantic model.
        self.assertEqual(digest({**frozen, 'combat_action': {'steps': [{**frozen['combat_action']['steps'][0], 'target_id': 'npc:legacy'}]}}), '7f4a2fff45adf1cc33dd22327f9b25b01728c2d7ecf541e40174b64a7eeb68c3')
        state = serialize_session_state(r.game_session)
        stable = {'spellcasting': state['spellcasting'], 'pending': state['character']['progression_effects_pending'],
                  'bonus_rules': state['combat']['action_economy']['actors']['player']['bonus_rules']}
        # C10 shared truthful disclosure intentionally updates LIVE text only.
        # Prior view digest was 5a589c18dcdef6ebddb005bba7aa6a86372ddf8f18ddcb7356f93c0e96559f90;
        # historical stored-response replay is independently fixed by checkpoint12.
        self.assertNotIn('sorcery_points', state['spellcasting'])
        self.assertNotIn('quickened_spell', state['combat']['action_economy']['actors']['player'])
        self.assertIn('Font of Magic: Sorcery Points are not adopted in this legacy state; no load-time grant', stable['pending'])
        self.assertEqual(digest(stable), 'e117453c66dbcaf91753b2c5eb2d8f2548ad06a3f541ac0c7a1ae78c76e64863')
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.manager.get_turn_action(r, command['action_id'])['request_hash'], digest(frozen))
        before = self.snapshot(r)
        command['combat_action']['steps'][0]['metamagic'] = None
        replay = await self.post(a, command)
        self.assertEqual(replay.json(), accepted.json())
        self.assertEqual(self.snapshot(r), before)

    async def test_typed_quickened_reaches_real_cast(self):
        a, r, command = await self.encounter()
        command['combat_action']['steps'][0]['metamagic'] = 'quickened_spell'
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(r.game_session.world_state['sorcery_points_v1']['remaining'], 0)
        self.assertEqual(r.game_session.world_state['spellcasting_v1']['slots']['1'], 2)
        pending = ' '.join(response.json()['state']['character']['progression_effects_pending'])
        self.assertIn('Quickened Magic Missile supported', pending)
        self.assertNotIn('Sorcery Points are not tracked yet', pending)

    async def test_invalid_choice_rejected_before_claim(self):
        a, r, command = await self.encounter(); before = self.snapshot(r)
        for value in (True, False, 0, 1, 'true', 'Quickened Spell', [], {}):
            bad = copy.deepcopy(command); bad['combat_action']['steps'][0]['metamagic'] = value
            response = await self.post(a, bad)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.snapshot(r), before)
        for step in ({'kind': 'attack'}, {'kind': 'magic', 'ability': 'Fire Bolt'}):
            bad = copy.deepcopy(command); bad['combat_action']['steps'] = [{**step, 'metamagic': 'quickened_spell'}]
            self.assertEqual((await self.post(a, bad)).status_code, 422)
        self.assertIsNone(self.manager.unresolved_action(r))


    async def quickened(self):
        a, r, command = await self.encounter()
        command['combat_action']['steps'][0]['metamagic'] = 'quickened_spell'
        return a, r, command

    async def reopen(self, a):
        self.manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        sid, r, *_ = self.manager.resume_campaign(a['campaign_id'])
        adapter = self.app.state.ollama_adapter
        await self.http.aclose()
        self.app = create_app(session_manager=self.manager, ollama_adapter=adapter, authenticator=FixedAuthenticator(TEST_PLAYER))
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://testserver')
        a['session_id'] = sid
        return r

    async def test_exact_replay_conflict_and_fresh_manager_preserve_one_debit(self):
        a, r, command = await self.quickened()
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        state = accepted.json()['state']
        self.assertEqual(state['spellcasting']['sorcery_points'], {'current': 0, 'max': 2})
        actor = state['combat']['action_economy']['actors']['player']
        self.assertTrue(actor['bonus_action_spent']); self.assertFalse(actor['base_action_spent'])
        self.assertFalse(actor['quickened_spell']['available'])
        committed = self.snapshot(r)
        with patch('spell_scope.cast', side_effect=AssertionError('Replay recast')):
            self.assertEqual((await self.post(a, command)).json(), accepted.json())
        self.assertEqual(self.snapshot(r), committed)
        altered = copy.deepcopy(command); altered['combat_action']['steps'][0].pop('metamagic')
        conflict = await self.post(a, altered)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()['detail']['code'], 'action_id_conflict')
        self.assertEqual(self.snapshot(r), committed)
        old_rng = r.game_session.rng.getstate()
        r = await self.reopen(a)
        self.assertEqual(r.game_session.rng.getstate(), old_rng)
        self.assertEqual(r.game_session.world_state['sorcery_points_v1']['remaining'], 0)
        committed = self.snapshot(r)
        expected = accepted.json(); expected['session_id'] = a['session_id']
        with patch('spell_scope.cast', side_effect=AssertionError('Restored replay recast')):
            self.assertEqual((await self.post(a, command)).json(), expected)
        self.assertEqual(self.snapshot(r), committed)

    async def test_later_step_failure_rolls_back_all_mechanics(self):
        a, r, command = await self.quickened(); before = r.game_session._capture_runtime_snapshot()
        command['combat_action']['steps'].append({'kind': 'magic', 'ability': 'Magic Missile', 'target_id': 'nonexistent'})
        response = await self.post(a, command)
        self.assertGreaterEqual(response.status_code, 400, response.text)
        self.assertEqual(r.game_session._capture_runtime_snapshot(), before)

    async def test_precommit_failure_then_retry_and_lost_ack_settle_once(self):
        from api.persistence.campaign_models import CampaignStorageError
        a, r, command = await self.quickened(); before = self.snapshot(r)
        with patch.object(self.manager, 'autosave_turn', side_effect=CampaignStorageError('synthetic precommit')):
            failed = await self.post(a, command)
        self.assertGreaterEqual(failed.status_code, 500, failed.text)
        self.assertEqual(self.snapshot(r), before)
        original = self.manager.autosave_turn
        def commit_then_fail(*args, **kwargs):
            original(*args, **kwargs)
            raise CampaignStorageError('synthetic committed acknowledgement lost')
        with patch.object(self.manager, 'autosave_turn', side_effect=commit_then_fail):
            failed = await self.post(a, command)
        self.assertGreaterEqual(failed.status_code, 500, failed.text)
        status = await self.http.get(f"/api/game/sessions/{a['session_id']}/actions/{command['action_id']}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()['state'], 'applied')
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(r.game_session.world_state['sorcery_points_v1']['remaining'], 0)
        self.assertEqual(r.game_session.world_state['spellcasting_v1']['slots']['1'], 2)

    async def test_foreign_owner_and_stale_revision_never_debit(self):
        a, r, command = await self.quickened(); before = self.snapshot(r)
        self.app.state.authenticator = FixedAuthenticator(PLAYER_B)
        try:
            self.assertEqual((await self.post(a, command)).status_code, 404)
        finally:
            self.app.state.authenticator = FixedAuthenticator(TEST_PLAYER)
        self.assertEqual(self.snapshot(r), before)
        fresh = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        fresh.resume_campaign(a['campaign_id']); fresh.save_campaign(a['campaign_id'])
        before = self.snapshot(r)
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'campaign_stale')
        self.assertEqual(self.snapshot(r), before)


    async def test_sqlite_precommit_failure_restores_exact_runtime_and_saved_payload(self):
        from contextlib import contextmanager
        import sqlite3
        a, r, command = await self.quickened(); before = self.snapshot(r)
        transaction = self.store._transaction; faults = []
        @contextmanager
        def failing_transaction():
            with transaction() as connection:
                yield connection
                receipt = connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',
                    (a['campaign_id'], command['action_id'])).fetchone()
                if receipt is not None:
                    faults.append(True)
                    raise sqlite3.OperationalError('synthetic SQLite precommit after receipt insert')
        with patch.object(self.store, '_transaction', side_effect=failing_transaction):
            response = await self.post(a, command)
        self.assertGreaterEqual(response.status_code, 500, response.text)
        self.assertEqual(faults, [True])
        self.assertEqual(self.snapshot(r), before)
        self.assertEqual((await self.post(a, command)).status_code, 200)
        self.assertEqual(r.game_session.world_state['sorcery_points_v1']['remaining'], 0)

    async def test_same_turn_levelled_lock_both_orders_with_additional_action(self):
        import action_economy
        for quick_first in (False, True):
            a, r, command = await self.encounter()
            action_economy.grant(r.game_session, 'player', 'synthetic-extra-action', ['magic'])
            self.manager.save_campaign(a['campaign_id'])
            first = copy.deepcopy(command)
            if quick_first: first['combat_action']['steps'][0]['metamagic'] = 'quickened_spell'
            accepted = await self.post(a, first)
            self.assertEqual(accepted.status_code, 200, accepted.text)
            r = await self.reopen(a)
            before = r.game_session._capture_runtime_snapshot()
            second = copy.deepcopy(command); second['action_id'] = str(uuid4())
            if not quick_first: second['combat_action']['steps'][0]['metamagic'] = 'quickened_spell'
            rejected = await self.post(a, second)
            self.assertGreaterEqual(rejected.status_code, 400, rejected.text)
            self.assertNotEqual(rejected.json()['detail']['code'], 'action_unavailable')
            self.assertEqual(r.game_session._capture_runtime_snapshot(), before)


class QuickenedSchemaTests(unittest.TestCase):
    def test_enum_retained_and_null_absent_dump_is_unchanged(self):
        ordinary = {'kind': 'magic', 'ability': 'Magic Missile'}
        self.assertEqual(EconomyStepInput(**ordinary).model_dump(exclude_none=True), {**ordinary, 'resource': 'action'})
        self.assertEqual(EconomyStepInput(**ordinary, metamagic=None).model_dump(exclude_none=True), {**ordinary, 'resource': 'action'})
        self.assertEqual(EconomyStepInput(**ordinary, metamagic='quickened_spell').model_dump(exclude_none=True)['metamagic'], 'quickened_spell')

    def test_factory_and_published_schema_agree_on_optional_enum(self):
        from pathlib import Path
        import yaml
        actual = create_app().openapi()['components']['schemas']['EconomyStepInput']
        published = yaml.safe_load((Path(__file__).resolve().parents[3] / 'lib/api-spec/openapi.yaml').read_text())['components']['schemas']['EconomyStepInput']
        self.assertNotIn('metamagic', actual['required'])
        self.assertNotIn('metamagic', published['required'])
        for component in (actual, published):
            branches = component['properties']['metamagic']['anyOf']
            self.assertIn({'type': 'null'}, branches)
            value = next(branch for branch in branches if branch.get('type') == 'string')
            self.assertEqual(value.get('enum', [value.get('const')]), ['quickened_spell'])
