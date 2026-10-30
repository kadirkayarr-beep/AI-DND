"""Bounded slot→Sorcery Points HTTP and checkpoint12 stored receipt contract."""
import copy
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from api.persistence.campaign_store import CampaignStore
from api.tests.auth_fixture import TEST_PLAYER
from api.tests import test_roadmap_c19_quickened_http as quickened_fixtures

FIXTURE = Path(__file__).parent / 'fixtures' / 'c19_checkpoint12_adopted_receipt.json'

class FontHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = quickened_fixtures.QuickenedHttpTests.asyncSetUp
    asyncTearDown = quickened_fixtures.QuickenedHttpTests.asyncTearDown
    create_campaign = quickened_fixtures.QuickenedHttpTests.create_campaign
    encounter = quickened_fixtures.QuickenedHttpTests.encounter
    post = quickened_fixtures.QuickenedHttpTests.post
    quickened = quickened_fixtures.QuickenedHttpTests.quickened
    reopen = quickened_fixtures.QuickenedHttpTests.reopen
    snapshot = quickened_fixtures.QuickenedHttpTests.snapshot

    async def frozen_campaign(self):
        fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        path = Path(self.temporary_directory.name) / f'checkpoint12-{uuid4()}.sqlite3'
        with sqlite3.connect(path) as connection:
            connection.executescript(fixture['sqlite_dump'])
            # SQL iterdump omits the database header version; restore the captured value, no migration.
            connection.execute(f"PRAGMA user_version={fixture['sqlite_user_version']}")
        self.store = CampaignStore(path, bound_principal=TEST_PLAYER)
        a = copy.deepcopy(fixture['campaign'])
        r = await self.reopen(a)
        return fixture, a, r

    async def test_checkpoint12_stored_receipt_and_canonical_state_survive_new_code(self):
        fixture, a, r = await self.frozen_campaign()
        self.assertEqual(r.game_session.serialize_game_state(), fixture['runtime'])
        old = self.manager.get_turn_action(r, fixture['command']['action_id'])
        self.assertEqual(old['request_hash'], fixture['request_hash'])
        expected = copy.deepcopy(fixture['response']); expected['session_id'] = a['session_id']
        before = self.snapshot(r)
        with patch('spell_scope.cast', side_effect=AssertionError('old receipt must not recast')):
            replay = await self.post(a, fixture['command'])
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), expected)
        self.assertEqual(self.snapshot(r), before)
        self.assertIn('Font of Magic: Sorcery Points tracked; slot conversion and creation remain unsupported',
                      replay.json()['state']['character']['progression_effects_pending'])

    async def test_live_projection_intentionally_announces_new_supported_conversion(self):
        fixture, a, r = await self.frozen_campaign()
        response = await self.http.get(f"/api/game/sessions/{a['session_id']}/state")
        self.assertEqual(response.status_code, 200, response.text)
        pending = ' '.join(response.json()['character']['progression_effects_pending'])
        self.assertIn('slot-to-point conversion supported', pending)
        self.assertEqual(r.game_session.serialize_game_state(), fixture['runtime'])

    async def conversion(self, outside=False):
        fixture, a, r = await self.frozen_campaign()
        if outside:
            r.game_session.end_combat('synthetic_conversion_fixture')
            self.manager.save_campaign(a['campaign_id'])
        command = {'message': 'Büyü yuvasını puana dönüştür.', 'action_id': str(uuid4()),
                   'combat_action': {'steps': [{'kind': 'convert_spell_slot', 'slot_level': 1}]}}
        return a, r, command

    async def test_actual_typed_conversion_debits_slot_not_action_or_clock(self):
        a, r, command = await self.conversion()
        s = r.game_session
        before = copy.deepcopy((s.world_state['combat'], s.world_state['combat']['turn_resources'],
                                s.world_state['spellcasting_v1']['slot_turn'], s.rng.getstate(),
                                s.world_state.get('campaign_time')))
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'], 1)
        self.assertEqual(s.world_state['spellcasting_v1']['slots']['1'], 1)
        self.assertEqual((s.world_state['combat'], s.world_state['combat']['turn_resources'],
                          s.world_state['spellcasting_v1']['slot_turn'], s.rng.getstate(),
                          s.world_state.get('campaign_time')), before)
        options = response.json()['state']['spellcasting']['convert_spell_slot']['options']
        self.assertEqual(options, [{'slot_level': 1, 'points_gained': 1, 'available': True, 'reason': None}])

    async def test_outside_model_unavailable_converts_with_zero_model_calls(self):
        a, r, command = await self.conversion(outside=True)
        s = r.game_session
        before = copy.deepcopy((s.world_state['combat'], s.world_state['spellcasting_v1']['slot_turn'],
                                s.rng.getstate(), s.world_state.get('campaign_time')))
        self.app.state.ollama_adapter = None
        with patch('api.tests.test_campaign_api.FakeOllamaClient.chat', side_effect=AssertionError('conversion called model')) as chat:
            response = await self.post(a, command)
        chat.assert_not_called()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'], 1)
        self.assertEqual(s.world_state['spellcasting_v1']['slots']['1'], 1)
        self.assertEqual((s.world_state['combat'], s.world_state['spellcasting_v1']['slot_turn'],
                          s.rng.getstate(), s.world_state.get('campaign_time')), before)

    async def test_conversion_strict_fields_reject_before_claim(self):
        a, r, command = await self.conversion(); before = self.snapshot(r)
        for value in (None, True, False, 0, 4, '1', 1.5):
            bad = copy.deepcopy(command); bad['combat_action']['steps'][0]['slot_level'] = value
            self.assertEqual((await self.post(a, bad)).status_code, 422, repr(value))
            self.assertEqual(self.snapshot(r), before)
        for field, value in [('ability','Magic Missile'), ('target_id','player'), ('metamagic','quickened_spell'),
                             ('resource','bonus'), ('distance_ft',5), ('reckless_attack',False)]:
            bad = copy.deepcopy(command); bad['combat_action']['steps'][0][field] = value
            self.assertEqual((await self.post(a, bad)).status_code, 422, field)
            self.assertEqual(self.snapshot(r), before)
        self.assertIsNone(self.manager.unresolved_action(r))

    async def test_exact_replay_conflict_and_fresh_resume_do_not_convert_twice(self):
        a, r, command = await self.conversion(outside=True)
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        before = self.snapshot(r)
        with patch('sorcery_points.convert_slot', side_effect=AssertionError('replay converted again')):
            replay = await self.post(a, command)
        self.assertEqual(replay.json(), accepted.json())
        self.assertEqual(self.snapshot(r), before)
        changed = copy.deepcopy(command); changed['combat_action']['steps'][0]['slot_level'] = 2
        refused = await self.post(a, changed)
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(refused.json()['detail']['code'], 'action_id_conflict')
        self.assertEqual(self.snapshot(r), before)
        r = await self.reopen(a)
        self.assertEqual(r.game_session.world_state['sorcery_points_v1']['remaining'], 1)
        self.assertEqual(r.game_session.world_state['spellcasting_v1']['slots']['1'], 1)
        expected = accepted.json(); expected['session_id'] = a['session_id']
        before = self.snapshot(r)
        with patch('sorcery_points.convert_slot', side_effect=AssertionError('restored replay converted again')):
            replay = await self.post(a, command)
        self.assertEqual(replay.json(), expected)
        self.assertEqual(self.snapshot(r), before)

    async def test_spent_action_and_bonus_do_not_prevent_conversion(self):
        a, r, command = await self.conversion()
        dash = {'message': 'Dash', 'action_id': str(uuid4()), 'combat_action': {'steps': [{'kind': 'dash'}]}}
        response = await self.post(a, dash)
        self.assertEqual(response.status_code, 200, response.text)
        resources = r.game_session.world_state['combat']['turn_resources']['player']
        self.assertTrue(resources['base_action_spent']); self.assertTrue(resources['bonus_action_spent'])
        before = copy.deepcopy(resources)
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(resources, before)
        self.assertEqual(r.game_session.world_state['sorcery_points_v1']['remaining'], 1)

    async def test_mixed_steps_and_unrelated_prose_never_gain_no_model_bypass(self):
        a, r, command = await self.conversion(outside=True)
        self.app.state.ollama_adapter = None
        before = self.snapshot(r)
        for other in ({'kind': 'dash'}, {'kind':'convert_spell_slot','slot_level':1},
                      {'kind':'magic','ability':'Magic Missile','target_id':'player'}):
            bad = copy.deepcopy(command); bad['combat_action']['steps'].append(other)
            response = await self.post(a, bad)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.snapshot(r), before)
        for body in ({'message':'Büyü yuvasını puana dönüştür.'},
                     {'message':'Konuş.', 'combat_action': {'steps':[{'kind':'dash'}]}}):
            a, r, _ = await self.conversion(outside=True)
            self.app.state.ollama_adapter = None
            before = self.snapshot(r)
            response = await self.post(a, {**body, 'action_id':str(uuid4())})
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(self.snapshot(r), before)

    async def test_sqlite_precommit_then_lost_ack_settles_one_conversion(self):
        from contextlib import contextmanager
        from api.persistence.campaign_models import CampaignStorageError
        a, r, command = await self.conversion(outside=True); before = self.snapshot(r)
        store = self.manager._require_campaign_store()
        transaction = store._transaction; faults = []
        @contextmanager
        def fail_after_receipt_insert():
            with transaction() as connection:
                yield connection
                row = connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',
                    (a['campaign_id'], command['action_id'])).fetchone()
                if row is not None:
                    faults.append(True)
                    raise sqlite3.OperationalError('synthetic conversion precommit')
        with patch.object(store, '_transaction', side_effect=fail_after_receipt_insert):
            failed = await self.post(a, command)
        self.assertGreaterEqual(failed.status_code, 500, failed.text)
        self.assertEqual(faults, [True]); self.assertEqual(self.snapshot(r), before)
        autosave = self.manager.autosave_turn
        def commit_then_fail(*args, **kwargs):
            autosave(*args, **kwargs)
            raise CampaignStorageError('synthetic conversion acknowledgement lost')
        with patch.object(self.manager, 'autosave_turn', side_effect=commit_then_fail):
            failed = await self.post(a, command)
        self.assertGreaterEqual(failed.status_code, 500, failed.text)
        status = await self.http.get(f"/api/game/sessions/{a['session_id']}/actions/{command['action_id']}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()['state'], 'applied')
        accepted = await self.post(a, command)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(r.game_session.world_state['sorcery_points_v1']['remaining'], 1)
        self.assertEqual(r.game_session.world_state['spellcasting_v1']['slots']['1'], 1)

    async def test_foreign_owner_and_stale_revision_cannot_convert(self):
        from api.auth import FixedAuthenticator
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import PLAYER_B
        a, r, command = await self.conversion(outside=True); before = self.snapshot(r)
        self.app.state.authenticator = FixedAuthenticator(PLAYER_B)
        try:
            response = await self.post(a, command)
            self.assertEqual(response.status_code, 404, response.text)
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


    async def test_conversion_preserves_before_and_after_spell_cast_lock(self):
        for new_turn in (False, True):
            a, r, command = await self.conversion()
            s = r.game_session
            target = next(n for n in s.world_state['npcs'] if n['id'] in s.world_state['combat']['participants'])
            if new_turn:
                s.end_combat('synthetic_next_encounter')
                with patch('game.roll_initiative_player', return_value=20), patch('game.roll_initiative', return_value=1):
                    s.start_combat(target)
                self.manager.save_campaign(a['campaign_id'])
            marker = copy.deepcopy(s.world_state['spellcasting_v1']['slot_turn'])
            converted = await self.post(a, command)
            self.assertEqual(converted.status_code, 200, converted.text)
            self.assertEqual(s.world_state['spellcasting_v1']['slot_turn'], marker)
            cast = {'message':'Cast', 'action_id':str(uuid4()), 'combat_action': {'steps': [{
                'kind':'magic', 'ability':'Magic Missile', 'target_id':target['id'], 'slot_level':1}]}}
            before = s._capture_runtime_snapshot()
            response = await self.post(a, cast)
            if new_turn:
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(s.world_state['spellcasting_v1']['slots']['1'], 0)
            else:
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()['detail']['code'], 'spell_slot_turn_limit')
                self.assertEqual(s._capture_runtime_snapshot(), before)


    async def test_full_and_unadopted_pool_refuse_without_debit_or_adoption(self):
        for legacy in (False, True):
            a, r, command = await self.encounter(legacy=legacy)
            s = r.game_session; s.end_combat('synthetic_full_pool')
            self.manager.save_campaign(a['campaign_id'])
            command['combat_action'] = {'steps':[{'kind':'convert_spell_slot','slot_level':1}]}
            before = s._capture_runtime_snapshot()
            response = await self.post(a, command)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(s._capture_runtime_snapshot(), before)
            state = (await self.http.get(f"/api/game/sessions/{a['session_id']}/state")).json()
            if legacy:
                self.assertNotIn('sorcery_points_v1', s.world_state)
                self.assertNotIn('convert_spell_slot', state['spellcasting'])
            else:
                self.assertEqual(s.world_state['sorcery_points_v1']['remaining'], 2)
                self.assertFalse(state['spellcasting']['convert_spell_slot']['options'][0]['available'])


    async def test_native_natural_kill_conversion_does_not_open_conversation(self):
        import bounded_encounter
        from api.lore_authority import PRODUCTION_START_CATALOG
        from api.tests.test_roadmap_c06_creation_http import character_request
        from api.serializers import serialize_session_state
        setting = PRODUCTION_START_CATALOG.to_response()['settings'][0]
        region = setting['regions'][0]
        start = {'setting_id': setting['setting_id'], 'region_pack_id':region['region_pack_id'],
                 'region_id':region['region_id'], 'starting_location_id':region['starting_locations'][0]['entity_id']}
        for stale_target in (False, True):
            campaign_id, session_id, r, _ = self.manager.create_campaign(
                character=character_request(2), campaign_start=start)
            a = {'campaign_id':campaign_id, 'session_id':session_id}; session = r.game_session
            bounded_encounter.resolve_command(session, bounded_encounter.ENTER)
            bounded_encounter.resolve_command(session, bounded_encounter.START)
            target = bounded_encounter.binding(session)['npc_id']
            self.manager.save_campaign(campaign_id)
            quick = {'message':'Quickened Magic Missile', 'action_id':str(uuid4()), 'combat_action': {'steps': [{
                'kind':'magic','ability':'Magic Missile','target_id':target,'slot_level':1,'metamagic':'quickened_spell'}]}}
            response = await self.post(a, quick)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(session.world_state['combat']['active'])
            self.assertEqual(session.world_state['combat']['end_reason'], 'target_defeated')
            before_state = serialize_session_state(session)
            self.assertFalse(before_state['conversation']['active'])
            before_flags = {k:copy.deepcopy(v) for k,v in session.world_state['flags'].items() if k != 'turn_index'}
            before_npcs = copy.deepcopy(session.world_state['npcs'])
            before_scene = copy.deepcopy(before_state['scene'])
            command = {'message':'Büyü yuvasını Sorcery Points puanına dönüştürüyorum.',
                'action_id':str(uuid4()), 'combat_action':{'steps':[{'kind':'convert_spell_slot','slot_level':1}]}}
            if stale_target: command['target_id'] = target
            response = await self.post(a, command)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['state']['conversation'], before_state['conversation'])
            self.assertEqual({k:v for k,v in session.world_state['flags'].items() if k != 'turn_index'}, before_flags)
            self.assertEqual(session.world_state['npcs'], before_npcs)
            self.assertEqual(response.json()['state']['scene'], before_scene)
            self.assertEqual(session.world_state['sorcery_points_v1']['remaining'], 1)
            self.assertEqual(session.world_state['spellcasting_v1']['slots']['1'], 1)


    async def test_conversion_preserves_existing_focus_despite_label_and_stale_target(self):
        from api.serializers import serialize_session_state
        a, r, command = await self.conversion(outside=True)
        session = r.game_session
        focus = session.resolve_npc_reference('Bir barmen')
        self.assertEqual(focus['status'], 'found')
        self.manager.save_campaign(a['campaign_id'])
        before = serialize_session_state(session)
        self.assertTrue(before['conversation']['active'])
        before_world = copy.deepcopy(session.world_state)
        command['message'] = 'Muhafıza yaklaşıyorum.'
        command['target_id'] = next(n['id'] for n in session.world_state['npcs'] if n['id'] != focus['npc']['id'])
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['state']['conversation'], before['conversation'])
        self.assertEqual(response.json()['state']['scene'], before['scene'])
        # Typed conversion may only advance its logical turn and change its two resources.
        after_world = copy.deepcopy(session.world_state)
        for world in (before_world, after_world):
            world['flags'].pop('turn_index', None)
            world['spellcasting_v1'].pop('slots', None)
            world.pop('sorcery_points_v1', None)
        self.assertEqual(after_world, before_world)


class FontSchemaTests(unittest.TestCase):
    def test_strict_single_step_contract_and_existing_hash_shape(self):
        from api.schemas import CombatActionInput, EconomyStepInput
        from pydantic import ValidationError
        for level in (1, 2, 3):
            value = CombatActionInput(steps=[{'kind':'convert_spell_slot','slot_level':level}])
            self.assertEqual(value.model_dump(exclude_none=True), {'steps':[{
                'kind':'convert_spell_slot','resource':'action','slot_level':level}]})
        ordinary = {'kind':'magic','ability':'Magic Missile','slot_level':1}
        self.assertEqual(EconomyStepInput(**ordinary).model_dump(exclude_none=True), {**ordinary,'resource':'action'})
        for extra in ({'ability':None}, {'target_id':None}, {'metamagic':None}, {'trigger':None}, {'resource':'bonus'}):
            with self.assertRaises(ValidationError):
                EconomyStepInput(kind='convert_spell_slot', slot_level=1, **extra)
        with self.assertRaises(ValidationError):
            CombatActionInput(steps=[{'kind':'convert_spell_slot','slot_level':1},{'kind':'dash'}])

    def test_actual_factory_and_spec_both_publish_new_kind(self):
        from api.main import create_app
        import yaml
        actual = create_app().openapi()['components']['schemas']['EconomyStepInput']
        published = yaml.safe_load((Path(__file__).resolve().parents[3] / 'lib/api-spec/openapi.yaml').read_text())['components']['schemas']['EconomyStepInput']
        self.assertEqual(actual['properties']['kind']['enum'], published['properties']['kind']['enum'])
        self.assertIn('convert_spell_slot', actual['properties']['kind']['enum'])
