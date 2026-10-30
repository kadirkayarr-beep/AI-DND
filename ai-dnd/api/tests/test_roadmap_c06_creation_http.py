"""C06 explicit custom creation adapter, real HTTP/store; no full class-effects claim."""
import copy
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
import yaml
import game
import bounded_encounter
import character_progression as cp
from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
from api.tests import test_campaign_api as campaigns
from api.tests import test_death_system as encounter
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_level3 import TWO, choices, IDS
from api.main import create_app
from api.schemas import CharacterCreateInput
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.dnd_2024_rules import CharacterCreationError
from api.serializers import serialize_session_state

ROOT = Path(__file__).resolve().parents[3]


def character_request(level=3, identity=IDS[0]):
    data = copy.deepcopy(SPEC)
    data['class'] = data.pop('character_class')
    data.update(mode='custom', starting_level=level)
    if level > 1:
        data['level_choices'] = {'2': copy.deepcopy(TWO)}
    if level > 2:
        data['level_choices']['3'] = choices(identity)
    return data


class CreationHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown

    def rows(self):
        # A fresh connection, never an uncommitted connection view.
        with self.store._connect() as connection:
            return [tuple(row) for row in connection.execute('SELECT * FROM campaigns ORDER BY campaign_id')]

    async def post_character(self, data, path='/api/game/campaigns'):
        return await self.http.post(path, json={'character': data})

    def assert_three(self, body, identity):
        c = body['state']['character']
        self.assertEqual((c['level'], c.get('progression_level'), c['proficiency_bonus']), (3, 3, 2))
        self.assertEqual((c['max_hp'], c['current_hp']), (20, 20))
        self.assertEqual(c.get('subclass_id'), identity)
        self.assertEqual(c.get('metamagic'), TWO['metamagic'])
        self.assertEqual(c['cantrips'], SPEC['cantrips'])
        self.assertEqual(c['spells'], SPEC['spells'] + TWO['prepared_spells'] + choices()['prepared_spells'])
        self.assertEqual(c['spell_slots_remaining'], {'1': 4, '2': 2})
        for name in ('Innate Sorcery', 'Font of Magic', 'Metamagic', 'subclass'):
            self.assertIn(name.casefold(), ' '.join(c.get('progression_effects_pending', [])).casefold())

    async def test_custom_three_creates_and_fresh_http_resume_preserves_all_four_choices(self):
        for identity in IDS:
            with self.subTest(identity=identity):
                response = await self.post_character(character_request(identity=identity))
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json(); self.assert_three(body, identity)
                record = self.manager.get(body['session_id'])
                saved = self.store.get_campaign(body['campaign_id'])
                engine = saved.payload['engine_save']
                self.assertEqual(engine['player']['subclass_id'], identity)
                self.assertEqual(engine['world_state']['spellcasting_v1'], record.game_session.world_state['spellcasting_v1'])
                manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
                app = create_app(session_manager=manager, authenticator=FixedAuthenticator(TEST_PLAYER))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    resumed = await client.post(f"/api/game/campaigns/{body['campaign_id']}/resume")
                self.assertEqual(resumed.status_code, 200, resumed.text)
                self.assert_three(resumed.json(), identity)
                restored = manager.get(resumed.json()['session_id']).game_session
                self.assertEqual(restored.world_state['spellcasting_v1'], record.game_session.world_state['spellcasting_v1'])
                self.assertEqual(restored.world_state['equipment'], record.game_session.world_state['equipment'])

    async def test_a_random_fighter_discloses_its_scope(self):
        with patch('game.CLASSES', ('Fighter',)):
            response = await self.post_character({'mode': 'random'}, '/api/campaigns')
        self.assertEqual(response.status_code, 200, response.text)
        c = response.json()['state']['character']
        self.assertEqual(c['class'], 'Fighter')
        self.assertIn('Second Wind', ' '.join(c['progression_effects_pending']))

    async def test_a_random_slice_class_discloses_its_scope(self):
        for name in ('Monk', 'Paladin', 'Rogue'):
            with self.subTest(name=name), patch('game.CLASSES', (name,)):
                response = await self.post_character({'mode': 'random'}, '/api/campaigns')
                self.assertEqual(response.status_code, 200, response.text)
                c = response.json()['state']['character']
                self.assertEqual(c['class'], name)
                self.assertTrue(c['progression_effects_pending'])

    async def test_default_random_and_explicit_levels_keep_legacy_shape(self):
        default = await self.http.post('/api/game/campaigns', json={})
        self.assertEqual(default.status_code, 200, default.text)
        self.assertEqual(default.json()['state']['character']['level'], 1)
        for mode in ('omitted-level', 'explicit-one', 'empty-choices', 'level-two', 'random', 'random-one'):
            with self.subTest(mode=mode):
                data = character_request(1)
                if mode == 'omitted-level': data.pop('starting_level')
                if mode == 'empty-choices': data['level_choices'] = {}
                if mode == 'level-two': data = character_request(2)
                if mode == 'random': data = {'mode': 'random'}
                if mode == 'random-one': data = {'mode': 'random', 'starting_level': 1}
                response = await self.post_character(data, '/api/campaigns')
                self.assertEqual(response.status_code, 200, response.text)
                c = response.json()['state']['character']
                self.assertEqual(c['level'], 2 if mode == 'level-two' else 1)
                if mode == 'level-two':
                    self.assertEqual(c['spell_slots_remaining'], {'1': 3})
                    self.assertNotIn('subclass_id', c)
                else:
                    self.assertNotIn('progression_level', c)
                    if c['class'] == 'Barbarian':
                        # Canonical creation now proves unarmored Rage admission;
                        # this is not adoption of an ambiguous legacy save.
                        session = self.manager.get(response.json()['session_id']).game_session
                        self.assertEqual(session.world_state['worn_armor_v1'], {'version': 1, 'armor_id': None})
                        self.assertEqual(session.world_state['rage_v1'], {'version': 1, 'remaining': 2, 'active': None})
                        self.assertEqual((c['rage']['uses_remaining'], c['rage']['max_uses'], c['rage']['active'], c['rage']['remaining_seconds']), (2, 2, False, None))
                        self.assertFalse(c['rage']['activate']['available'])
                        self.assertIn('known-unarmored Barbarian 1–2', ' '.join(c['progression_effects_pending']))
                    else:
                        self.assertNotIn('rage', c)
                        if c['class'] == 'Fighter':  # the random class can be a Fighter, whose scope is always disclosed
                            self.assertIn('Second Wind', ' '.join(c['progression_effects_pending']))
                        elif c['class'] == 'Paladin':  # the same for a random Paladin
                            self.assertIn('catalog-only', ' '.join(c['progression_effects_pending']))
                        elif c['class'] in ('Monk', 'Rogue'):  # both disclose their scope from level 1 as well
                            self.assertTrue(c['progression_effects_pending'])
                        else:
                            self.assertNotIn('progression_effects_pending', c)

    async def test_malformed_requests_and_direct_manager_never_publish(self):
        cases = []
        for value in (True, 3.0, '3', 0, 4, None):
            data = character_request(); data['starting_level'] = value; cases.append(data)
        for mode in ('missing-two', 'missing-three', 'future', 'zero-padded', 'internal-alias', 'null-step', 'extra-step-field', 'bad-count', 'other-class', 'random-high', 'random-choices'):
            data = character_request()
            if mode == 'missing-two': del data['level_choices']['2']
            if mode == 'missing-three': del data['level_choices']['3']
            if mode == 'future': data['level_choices']['4'] = {}
            if mode == 'zero-padded': data['level_choices']['02'] = data['level_choices'].pop('2')
            if mode == 'internal-alias': data['level_choices']['level_2'] = data['level_choices'].pop('2')
            if mode == 'null-step': data['level_choices']['2'] = None
            if mode == 'extra-step-field': data['level_choices']['3']['metamagic'] = ['Quickened Spell']
            if mode == 'bad-count': data['level_choices']['2']['prepared_spells'] = ['Burning Hands']
            if mode == 'other-class': data['class'] = 'Wizard'
            if mode == 'random-high': data = {'mode': 'random', 'starting_level': 3}
            if mode == 'random-choices': data = {'mode': 'random', 'level_choices': {}}
            cases.append(data)
        before = self.rows(); registry = dict(self.manager._sessions)
        for index, data in enumerate(cases):
            with self.subTest(case=index), patch.object(self.store, 'create_campaign', wraps=self.store.create_campaign) as store:
                response = await self.post_character(data)
                self.assertEqual(response.status_code, 422, response.text)
                store.assert_not_called()
                self.assertEqual(self.rows(), before); self.assertEqual(self.manager._sessions, registry)
        direct_bad = character_request(); direct_bad['starting_level'] = True
        alias_bad = character_request(); alias_bad['level_choices']['level_2'] = alias_bad['level_choices'].pop('2')
        null_bad = character_request(); null_bad['level_choices']['2'] = None
        for bad in (direct_bad, alias_bad, null_bad):
            with self.assertRaises(CharacterCreationError): self.manager.create_campaign(character=bad)
        self.assertEqual(self.rows(), before); self.assertEqual(self.manager._sessions, registry)

    async def test_semantic_late_failure_restores_runtime_before_store_or_registry(self):
        existing = await self.http.post('/api/game/campaigns', json={})
        self.assertEqual(existing.status_code, 200, existing.text)
        sentinel = self.manager.get(existing.json()['session_id']).game_session
        sentinel_before = sentinel._capture_runtime_snapshot()
        rows_before = self.rows(); sessions_before = dict(self.manager._sessions)
        campaigns_before = dict(self.manager._campaign_sessions)
        session = game.create_session(seed=42)
        before = session._capture_runtime_snapshot(); character_ref = session.character; world_ref = session.world_state
        data = character_request(); data['level_choices']['3']['subclass_id'] = 'phb2024:subclass:wizard:evoker'
        applied = []; real = cp.apply_level_choices
        def observe(*args, **kwargs):
            result = real(*args, **kwargs); applied.append((args[1]['to_level'], result['status'])); return result
        with patch.object(self.manager, '_session_factory', return_value=session), patch.object(cp, 'apply_level_choices', side_effect=observe), patch.object(self.store, 'create_campaign', wraps=self.store.create_campaign) as store:
            response = await self.post_character(data)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIsInstance(response.json()['detail'], dict, response.text)
        self.assertEqual(response.json()['detail']['code'], 'invalid_character')
        self.assertIn((2, 'applied'), applied)
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertIs(session.character, character_ref); self.assertIs(session.world_state, world_ref)
        store.assert_not_called(); self.assertEqual(self.rows(), rows_before)
        self.assertEqual(self.manager._sessions, sessions_before); self.assertEqual(self.manager._campaign_sessions, campaigns_before)
        self.assertEqual(sentinel._capture_runtime_snapshot(), sentinel_before)

    async def test_real_insert_then_precommit_failure_rolls_back_and_does_not_register(self):
        existing = await self.http.post('/api/game/campaigns', json={})
        self.assertEqual(existing.status_code, 200, existing.text)
        sentinel = self.manager.get(existing.json()['session_id']).game_session
        sentinel_before = sentinel._capture_runtime_snapshot()
        rows_before = self.rows(); sessions_before = dict(self.manager._sessions)
        campaigns_before = dict(self.manager._campaign_sessions)
        real_transaction = self.store._transaction; faults = []
        @contextmanager
        def failing_transaction():
            with real_transaction() as connection:
                yield connection
                count = connection.execute('SELECT COUNT(*) FROM campaigns').fetchone()[0]
                self.assertEqual(count, len(rows_before) + 1, 'fault must occur after real INSERT')
                faults.append(count)
                raise sqlite3.OperationalError('controlled precommit failure')
        with patch.object(self.store, '_transaction', side_effect=failing_transaction):
            response = await self.post_character(character_request())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(faults, [len(rows_before) + 1]); self.assertEqual(self.rows(), rows_before)
        self.assertEqual(self.manager._sessions, sessions_before); self.assertEqual(self.manager._campaign_sessions, campaigns_before)
        self.assertEqual(sentinel._capture_runtime_snapshot(), sentinel_before)

    async def test_http_created_three_casts_slot_two_and_replays_without_reconfiguration(self):
        created = await self.post_character(character_request())
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json(); session = self.manager.get(body['session_id']).game_session
        before_character = copy.deepcopy(session.character)
        encounter.start_test_combat(session)
        enemy = session.world_state['npcs'][-1]
        enemy.update(current_hp=100, max_hp=100, distance_ft=30, monster_stat_block=copy.deepcopy(bounded_encounter.COMMONER))
        session.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        session.world_state['attack_environment'] = {'pairs': {'player|' + enemy['id']: {'distance_ft': 30, 'attacker_sees_target': True, 'target_sees_attacker': True, 'cover': 'none'}}}
        session.ensure_combat_state()
        self.assertEqual(session.character, before_character, 'encounter must not rebuild the caster')
        self.manager.save_campaign(body['campaign_id']); self.app.state.ollama_adapter = None
        combat = session.world_state['combat']
        command = {'message': 'Magic Missile', 'action_id': str(uuid4()), 'combat_id': combat['combat_id'], 'combat_round': combat['round'], 'combat_turn_index': combat['current_turn_index'], 'combat_action': {'steps': [{'kind': 'magic', 'ability': 'Magic Missile', 'target_id': enemy['id'], 'slot_level': 2}]}}
        url = f"/api/game/sessions/{body['session_id']}/turn"
        with patch.object(session.rng, 'randint', return_value=2): first = await self.http.post(url, json=command)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['combat_result']['economy_steps'][0]['result']['darts'], [3, 3, 3, 3])
        self.assertEqual(session.world_state['spellcasting_v1']['slots'], {'1': 4, '2': 1})
        snapshot = session._capture_runtime_snapshot()
        with patch.object(session, 'run_player_turn', side_effect=AssertionError('replay reran engine')): replay = await self.http.post(url, json=command)
        self.assertEqual(replay.json(), first.json()); self.assertEqual(session._capture_runtime_snapshot(), snapshot)
        manager = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        app = create_app(session_manager=manager, authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            resumed = await client.post(f"/api/game/campaigns/{body['campaign_id']}/resume")
            self.assertEqual(resumed.status_code, 200, resumed.text)
            sid = resumed.json()['session_id']; restored = manager.get(sid).game_session
            self.assertEqual(restored.world_state['spellcasting_v1']['slots'], {'1': 4, '2': 1})
            restored_before = restored._capture_runtime_snapshot()
            with patch.object(restored, 'run_player_turn', side_effect=AssertionError('reopened replay reran engine')):
                reopened_replay = await client.post(f'/api/game/sessions/{sid}/turn', json=command)
            self.assertEqual(reopened_replay.status_code, 200, reopened_replay.text)
            self.assertEqual(reopened_replay.json()['combat_result'], first.json()['combat_result'])
            self.assertEqual(restored._capture_runtime_snapshot(), restored_before)

    async def test_runtime_request_and_published_projection_contract(self):
        request_schema = self.app.openapi()['components']['schemas']['CharacterCreateInput']
        self.assertIn('starting_level', request_schema['properties'])
        level = request_schema['properties']['starting_level']
        self.assertEqual((level['type'], level['minimum'], level['maximum'], level['default']), ('integer', 1, 5, 1))
        published = yaml.safe_load((ROOT/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']
        self.assertIn('level_choices', published['CharacterCreateInput']['properties'])
        runtime_choices = self.app.openapi()['components']['schemas']['SorcererLevelChoices']
        for schema in (runtime_choices, published['SorcererLevelChoices']):
            self.assertEqual(set(schema['properties']), {'2', '3', '4', '5'})
            self.assertIs(schema['additionalProperties'], False)
            self.assertEqual(schema.get('required', []), [])
            for step in ('2', '3', '4', '5'):
                self.assertIn('$ref', schema['properties'][step])
                self.assertNotIn('anyOf', schema['properties'][step])
        for field in ('progression_level', 'metamagic', 'subclass_id', 'progression_effects_pending'):
            self.assertIn(field, published['GameCharacter']['properties'])
        from api.tests.test_roadmap_c06_level3 import three
        s = three(); s.character['level'] = 4  # unapplied XP level must not claim new feature effects
        before = s._capture_runtime_snapshot(); projected = serialize_session_state(s)
        self.assertEqual(projected['character'].get('progression_level'), 3)
        self.assertEqual(s._capture_runtime_snapshot(), before)
        projected['character']['metamagic'].append('client mutation')
        self.assertEqual(s._capture_runtime_snapshot(), before)

    async def test_pending_status_uses_applied_level_and_is_detached(self):
        from api.tests.test_roadmap_c06_level3 import two
        s = two(); s.character['level'] = 3
        before = s._capture_runtime_snapshot(); projection = serialize_session_state(s)
        c = projection['character']
        self.assertEqual(c.get('progression_level'), 2)
        pending = c.get('progression_effects_pending', [])
        self.assertTrue(pending)
        self.assertNotIn('subclass', ' '.join(pending).casefold())
        self.assertIn('Font of Magic', ' '.join(pending))
        self.assertEqual(s._capture_runtime_snapshot(), before)
        pending.append('client mutation')
        self.assertEqual(s._capture_runtime_snapshot(), before)
