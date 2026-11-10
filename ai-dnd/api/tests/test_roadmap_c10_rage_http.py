"""Selected canonical unarmored Barbarian Rage HTTP and durable receipt boundary."""
import copy
import unittest
from uuid import uuid4
from unittest.mock import patch
from api.auth import FixedAuthenticator
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.tests.auth_fixture import TEST_PLAYER, PLAYER_B
from api.tests import test_roadmap_c19_quickened_http as prior
from api.tests.test_roadmap_c06_barbarian_creation_http import request

class RageHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = prior.QuickenedHttpTests.asyncSetUp
    asyncTearDown = prior.QuickenedHttpTests.asyncTearDown
    post = prior.QuickenedHttpTests.post
    snapshot = prior.QuickenedHttpTests.snapshot
    reopen = prior.QuickenedHttpTests.reopen

    async def encounter(self, level=2):
        response = await self.http.post('/api/game/campaigns', json={'character': request(level)})
        self.assertEqual(response.status_code, 200, response.text)
        a = response.json(); r = self.manager.get(a['session_id']); s = r.game_session
        s.commit_location_change('tavern')
        npc = s.create_npc_from_ai({'name': 'Rakip', 'role': 'Guard', 'location': 'tavern'})
        npc.update(current_hp=100, max_hp=100, armor_class=20, hostile=True, distance_ft=5)
        s.world_state.setdefault('monster_perception', {})[npc['id']] = {'player': {'visible': True}}
        with patch('game.roll_initiative_player', return_value=20), patch('game.roll_initiative', return_value=1):
            s.start_combat(npc)
        self.manager.save_campaign(a['campaign_id'])
        command = {'message': 'Rage', 'action_id': str(uuid4()), 'combat_action': {'steps': [{'kind': 'activate_rage', 'resource': 'bonus'}]}}
        return a, r, command

    async def test_actual_canonical_creation_projects_pool_without_mutating_preview(self):
        for level in (1,2):
            response = await self.http.post('/api/game/campaigns', json={'character': request(level)})
            self.assertEqual(response.status_code, 200, response.text)
            a = response.json(); r = self.manager.get(a['session_id'])
            rage = a['state']['character'].get('rage')
            self.assertIsNotNone(rage)
            self.assertEqual((rage['uses_remaining'], rage['max_uses'], rage['active'], rage['remaining_seconds']), (2,2,False,None))
            self.assertFalse(rage['activate']['available'])
            before = self.snapshot(r)
            for _ in range(2):
                current = await self.http.get(f"/api/game/sessions/{a['session_id']}/state")
                self.assertEqual(current.json()['character']['rage'], rage)
            self.assertEqual(self.snapshot(r), before)

    async def test_typed_activation_costs_one_bonus_use_and_no_focus(self):
        a, r, command = await self.encounter()
        old = copy.deepcopy(r.game_session.world_state.get('flags'))
        response = await self.post(a, command)
        self.assertEqual(response.status_code, 200, response.text)
        rage = response.json()['state']['character']['rage']
        self.assertEqual((rage['uses_remaining'],rage['active'],rage['remaining_seconds']), (1,True,12))
        actor = response.json()['state']['combat']['action_economy']['actors']['player']
        self.assertTrue(actor['bonus_action_spent']); self.assertFalse(actor['base_action_spent'])
        flags=copy.deepcopy(r.game_session.world_state.get('flags'))
        self.assertEqual(flags.pop('turn_index'),old.pop('turn_index')+1)
        self.assertEqual(flags,old)
        self.assertEqual(response.json()['narration'], 'Bonus eylem ile Öfke başlatırsın; kalan kullanım: 1.')
        before=self.snapshot(r)
        with patch('barbarian_rage.activate',side_effect=AssertionError('replay activation')), patch('action_economy.resolved_narration',side_effect=AssertionError('receipt narration regenerated')):
            replay=await self.post(a,command)
        self.assertEqual(replay.json(),response.json())
        self.assertEqual(self.snapshot(r),before)

    async def test_invalid_shape_rejects_before_claim(self):
        a, r, command = await self.encounter(); before = self.snapshot(r)
        for kind in ('activate_rage','extend_rage'):
            for step in ({'kind':kind}, {'kind':kind,'resource':'action'},
                         *({'kind':kind,'resource':'bonus',field:value} for field,value in
                           [('target_id',None),('target_id','npc_001'),('ability',None),('slot_level',None),
                            ('metamagic',None),('reckless_attack',False),('form','rage')])):
                bad = copy.deepcopy(command); bad['combat_action']['steps'] = [step]
                response = await self.post(a,bad)
                self.assertEqual(response.status_code,422,response.text)
                self.assertEqual(self.snapshot(r),before)
            bad = copy.deepcopy(command); bad['combat_action']['steps'].append({'kind':'dash'})
            self.assertEqual((await self.post(a,bad)).status_code,422)
        self.assertIsNone(self.manager.unresolved_action(r))

    async def test_precommit_failure_then_retry_and_lost_ack_settle_once(self):
        from api.persistence.campaign_models import CampaignStorageError
        a, r, command = await self.encounter(); before = self.snapshot(r)
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
        self.assertEqual(r.game_session.world_state['rage_v1']['remaining'], 1)

    async def test_foreign_owner_and_stale_revision_never_debit(self):
        a, r, command = await self.encounter(); before = self.snapshot(r)
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
        a, r, command = await self.encounter(); before = self.snapshot(r)
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
        self.assertEqual(r.game_session.world_state['rage_v1']['remaining'], 1)


    async def test_exact_replay_conflict_fresh_resume_active_and_no_refill(self):
        a, r, command = await self.encounter()
        accepted = await self.post(a,command)
        self.assertEqual(accepted.status_code,200,accepted.text)
        before = self.snapshot(r)
        with patch('barbarian_rage.activate',side_effect=AssertionError('replay activated')):
            self.assertEqual((await self.post(a,command)).json(),accepted.json())
        self.assertEqual(self.snapshot(r),before)
        changed=copy.deepcopy(command); changed['combat_action']['steps'][0]['kind']='extend_rage'
        conflict=await self.post(a,changed)
        self.assertEqual(conflict.status_code,409,conflict.text)
        self.assertEqual(conflict.json()['detail']['code'],'action_id_conflict')
        runtime=copy.deepcopy(r.game_session.serialize_game_state())
        r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),runtime)
        expected=accepted.json(); expected['session_id']=a['session_id']
        with patch('barbarian_rage.activate',side_effect=AssertionError('fresh replay activated')):
            self.assertEqual((await self.post(a,command)).json(),expected)
        live=await self.http.get(f"/api/game/sessions/{a['session_id']}/state")
        self.assertEqual(live.json()['character']['rage'],accepted.json()['state']['character']['rage'])

    async def test_legacy_absence_stays_absent_and_refuses_activation(self):
        a,r,command=await self.encounter()
        r.game_session.world_state.pop('rage_v1',None)
        r.game_session.world_state.pop('worn_armor_v1',None)
        self.manager.save_campaign(a['campaign_id'])
        canonical=copy.deepcopy(r.game_session.serialize_game_state())
        r=await self.reopen(a)
        self.assertEqual(r.game_session.serialize_game_state(),canonical)
        live=await self.http.get(f"/api/game/sessions/{a['session_id']}/state")
        self.assertNotIn('rage',live.json()['character'])
        self.assertIn('legacy state is not automatically adopted', ' '.join(live.json()['character']['progression_effects_pending']))
        before=r.game_session._capture_runtime_snapshot()
        refused=await self.post(a,command)
        self.assertGreaterEqual(refused.status_code,400,refused.text)
        self.assertEqual(r.game_session._capture_runtime_snapshot(),before)
        self.assertNotIn('rage_v1',r.game_session.world_state)

    async def test_manual_extension_on_next_player_turn_uses_bonus_not_another_use(self):
        a,r,command=await self.encounter()
        accepted=await self.post(a,command)
        self.assertEqual(accepted.status_code,200,accepted.text)
        s=r.game_session
        s.advance_combat_turn()
        s.advance_combat_turn()
        self.manager.save_campaign(a['campaign_id'])
        live=await self.http.get(f"/api/game/sessions/{a['session_id']}/state")
        self.assertEqual(live.json()['character']['rage']['remaining_seconds'],6)
        self.assertTrue(live.json()['character']['rage']['extend']['available'])
        command['action_id']=str(uuid4()); command['combat_action']['steps'][0]['kind']='extend_rage'
        response=await self.post(a,command)
        self.assertEqual(response.status_code,200,response.text)
        rage=response.json()['state']['character']['rage']
        self.assertEqual((rage['remaining_seconds'],rage['uses_remaining']),(12,1))
        self.assertFalse(rage['extend']['available'])
        self.assertEqual(response.json()['narration'], 'Bonus eylem ile Öfke süreni uzatırsın; ek kullanım harcanmaz.')
        before=self.snapshot(r)
        with patch('barbarian_rage.extend',side_effect=AssertionError('replay extension')), patch('action_economy.resolved_narration',side_effect=AssertionError('receipt narration regenerated')):
            replay=await self.post(a,command)
        self.assertEqual(replay.json(),response.json())
        self.assertEqual(self.snapshot(r),before)
        command['action_id']=str(uuid4()); before=s._capture_runtime_snapshot()
        refused=await self.post(a,command)
        self.assertGreaterEqual(refused.status_code,400,refused.text)
        self.assertEqual(s._capture_runtime_snapshot(),before)

    async def test_outside_activation_never_gets_conversion_model_bypass(self):
        a,r,command=await self.encounter()
        r.game_session.end_combat('synthetic_outside_admission')
        self.manager.save_campaign(a['campaign_id'])
        before=r.game_session._capture_runtime_snapshot()
        self.app.state.ollama_adapter=None
        refused=await self.post(a,command)
        self.assertGreaterEqual(refused.status_code,400,refused.text)
        self.assertEqual(r.game_session._capture_runtime_snapshot(),before)

    async def test_completed_short_rest_recovers_one_use_with_sql_rollback_and_exact_replay(self):
        from contextlib import contextmanager
        import sqlite3
        a,r,command=await self.encounter(); session=r.game_session
        self.assertEqual((await self.post(a,command)).status_code,200)
        npc=next(n for n in session.world_state['npcs'] if n['id'] in session.world_state['combat']['participants'])
        session.end_combat('synthetic_rest_boundary')
        session.advance_campaign_time(12,'synthetic_rage_expiry')
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):
            session.start_combat(npc)
        self.manager.save_campaign(a['campaign_id'])
        command['action_id']=str(uuid4())
        self.assertEqual((await self.post(a,command)).status_code,200)
        self.assertEqual(session.world_state['rage_v1']['remaining'],0)
        session.end_combat('synthetic_rest_boundary')
        self.manager.save_campaign(a['campaign_id'])
        command={'action':'short_rest','action_id':str(uuid4())}
        url=f"/api/game/sessions/{a['session_id']}/species-actions"
        before=self.snapshot(r); transaction=self.store._transaction; reached=[]
        @contextmanager
        def fail_after_receipt_insert():
            with transaction() as connection:
                yield connection
                receipt=connection.execute('SELECT response_json FROM campaign_turn_actions WHERE campaign_id=? AND action_id=?',
                    (a['campaign_id'],command['action_id'])).fetchone()
                if receipt is not None:
                    reached.append(True)
                    self.assertEqual(session.world_state['rage_v1']['remaining'],1)
                    raise sqlite3.OperationalError('synthetic completed rest receipt precommit')
        with patch.object(self.store,'_transaction',side_effect=fail_after_receipt_insert):
            failed=await self.http.post(url,json=command)
        self.assertGreaterEqual(failed.status_code,500,failed.text)
        self.assertEqual(reached,[True]); self.assertEqual(self.snapshot(r),before)
        accepted=await self.http.post(url,json=command)
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(session.world_state['rage_v1']['remaining'],1)
        self.assertEqual(accepted.json()['state']['character']['rage']['uses_remaining'],1)
        self.assertFalse(accepted.json()['state']['character']['rage']['active'])
        r=await self.reopen(a); expected=accepted.json(); expected['session_id']=a['session_id']
        url=f"/api/game/sessions/{a['session_id']}/species-actions"
        with patch.object(r.game_session,'resolve_species_trait_action',side_effect=AssertionError('rest replayed')):
            self.assertEqual((await self.http.post(url,json=command)).json(),expected)
        self.assertEqual(r.game_session.world_state['rage_v1']['remaining'],1)


class RageSchemaTests(unittest.TestCase):
    def test_explicit_bonus_retained_and_old_command_dump_unchanged(self):
        from api.schemas import EconomyStepInput
        for kind in ('activate_rage','extend_rage'):
            step={'kind':kind,'resource':'bonus'}
            self.assertEqual(EconomyStepInput(**step).model_dump(exclude_none=True),step)
        self.assertEqual(EconomyStepInput(kind='dash').model_dump(exclude_none=True),{'kind':'dash','resource':'action'})
        frozen={'message':'Hamle.','target_id':None,'combat_action':{'steps':[{'kind':'magic','resource':'action','ability':'Magic Missile','target_id':'npc:legacy','slot_level':1}]}}
        self.assertEqual(prior.digest(frozen),'7f4a2fff45adf1cc33dd22327f9b25b01728c2d7ecf541e40174b64a7eeb68c3')

    def test_factory_published_command_enum_and_optional_projection(self):
        from api.main import create_app
        from pathlib import Path
        import yaml
        actual=create_app().openapi()['components']['schemas']['EconomyStepInput']
        published=yaml.safe_load((Path(__file__).resolve().parents[3]/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']
        self.assertEqual(actual['properties']['kind']['enum'],published['EconomyStepInput']['properties']['kind']['enum'])
        self.assertIn('rage',published['GameCharacter']['properties'])
        self.assertNotIn('rage',published['GameCharacter'].get('required',[]))
