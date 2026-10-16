"""Frozen D02-D05: real resolver outcomes plus injected narrator failures."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from uuid import uuid4

os.environ['AI_DND_DISABLE_DEFAULT_APP'] = '1'
import httpx
import game
from api.tests.test_f04_frozen_faults import (
    Fixture, ScriptedProvider, evidence, narration, no_network, plain,
)


class FrozenNarratorFaultTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='f04-narrator-fault-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.output = Path(os.environ.get('F04_FAULT_EVIDENCE', str(self.folder/'evidence'))) / self._testMethodName
        self.output.mkdir(parents=True, exist_ok=True)

    async def test_D02_resolved_mechanics_survive_narrator_exception(self):
        intent = {'intent': 'door', 'action': 'open', 'target': {'type': 'feature', 'reference': 'door'},
                  'completion': 'intended', 'confidence': 1.0}
        provider = ScriptedProvider([intent, TimeoutError('D02 synthetic narration failure')])
        fixture = Fixture(self.folder/'campaign.sqlite3', provider)
        with no_network() as network, fixture.adapter.engine_binding():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                         base_url='http://testserver', trust_env=False) as client:
                await fixture.create(client)
                fixture.tavern(locked_door=True)
                fixture.session.rng.seed(5)
                fixture.save()
                before = fixture.snapshot()
                evidence(self.output, 'before.json', before)
                during = []
                def at_provider(index, kwargs):
                    during.append(fixture.snapshot())
                provider.before_call = at_provider
                action_id = str(uuid4())
                response = await fixture.turn(client, 'Kapıyı zorlayarak açmaya çalışıyorum.', action_id)
                after = fixture.snapshot()
                evidence(self.output, 'after.json', after)
                evidence(self.output, 'provider-entry.json', during)
                evidence(self.output, 'engine-results.json', fixture.engine_results)
                evidence(self.output, 'response.json', {'status': response.status_code, 'body': response.json(),
                         'failures': fixture.adapter.failure_scopes, 'calls': provider.calls})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(provider.calls), 2)
                self.assertEqual(len(fixture.engine_results), 1)
                result = fixture.engine_results[0]
                action = result['action_result']
                self.assertEqual(action['action'], 'skill_check')
                self.assertTrue(action['success'])
                self.assertFalse(during[0]['engine_save']['world_state']['doors'][0]['open'])
                self.assertTrue(during[1]['engine_save']['world_state']['doors'][0]['open'])
                self.assertTrue(after['engine_save']['world_state']['doors'][0]['open'])
                self.assertEqual(after['engine_save']['world_state'], during[1]['engine_save']['world_state'])
                self.assertEqual(after['engine_save']['player'], during[1]['engine_save']['player'])
                self.assertEqual(after['rng'], during[1]['rng'])
                self.assertEqual(len(after['sql_rows']['campaign_turn_actions']), 1)
                self.assertEqual(len(after['persisted']['history']), len(before['persisted']['history']) + 1)
                telemetry = result['_engine_event_evidence']['telemetry']
                self.assertEqual(telemetry['narration_source'], 'deterministic_fallback')
                self.assertEqual(telemetry['narration_validation_result'], 'python_fallback')
                self.assertEqual(telemetry['fallback_reason'], 'MODEL_UNAVAILABLE')
                self.assertEqual(fixture.adapter.failure_scopes[-1], [
                    {'error_type': 'TimeoutError', 'phase': 'resolved_narration'}])
                self.assertEqual(response.json()['narration'], result['narration'])
                # Receipt replay must not resolve, roll, narrate or commit twice.
                replay = await fixture.turn(client, 'Kapıyı zorlayarak açmaya çalışıyorum.', action_id)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(replay.json(), response.json())
                self.assertEqual(len(provider.calls), 2)
                self.assertEqual(fixture.snapshot(), after)
                self.assertEqual(network, [])
                evidence(self.output, 'assertions.json', {
                    'scenario': 'D02', 'provider_after_mechanical_resolution': True,
                    'mechanics_and_rng_retained': True, 'receipt_count': 1,
                    'same_uuid_replay_equal': True, 'telemetry': telemetry,
                    'synthetic_attempts': 2, 'intent_attempts': 1, 'narration_attempts': 1, 'extra_narration_attempts': 0, 'network_attempts': 0,
                })


    async def test_D03_conflicting_hp_and_critical_narration(self):
        bad = 'Kritik vuruş gerçekleşmedi. Rakibin hiç hasar almadı ve canın 999 HP oldu.'
        provider = ScriptedProvider([narration(bad)])
        fixture = Fixture(self.folder/'campaign.sqlite3', provider)
        with no_network() as network, fixture.adapter.engine_binding():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                         base_url='http://testserver', trust_env=False) as client:
                await fixture.create(client)
                fixture.tavern()
                npc = {'id': 'npc_enemy', 'name': 'Haydut', 'role': 'Guard',
                       'location': 'tavern', 'relationship': 'hostile', 'hostile': True,
                       'memory': [], 'knowledge': [], 'current_hp': 100, 'max_hp': 100,
                       'armor_class': 10, 'combat_status': 'active', 'distance_ft': 5,
                       'dexterity_mod': -5, 'attack_bonus': 0, 'damage_die': 4,
                       'damage_dice': 1, 'damage_modifier': 0}
                fixture.session.world_state['npcs'] = [npc]
                fixture.session.rng.seed(5)
                game._living_world_prompt_context(session=fixture.session)
                fixture.session.start_combat(npc)
                self.assertEqual(fixture.session.world_state['combat']['current_actor_id'], 'player')
                fixture.session.rng.seed(5)  # actual RNG yields natural 20, not a mocked resolution
                fixture.save()
                before = fixture.snapshot()
                combat = fixture.session.world_state['combat']
                message = 'Kılıçla saldırıyorum.'
                response = await fixture.turn(client, message, target_id=npc['id'],
                    interaction_mode='do', combat_id=combat['combat_id'],
                    combat_round=combat['round'], combat_turn_index=combat['current_turn_index'])
                evidence(self.output, 'native-response.json', {'status': response.status_code, 'body': response.json()})
                evidence(self.output, 'native-engine.json', fixture.engine_results)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(provider.calls), 0, 'Native combat must not add a model call')
                native = fixture.engine_results[-1]
                action = native['action_result']
                self.assertEqual(action['outcome'], 'critical_hit')
                self.assertGreater(action['damage'], 0)
                self.assertEqual(npc['current_hp'], 100 - action['damage'])
                committed = fixture.snapshot()
                # Native combat renders deterministically. Inject the frozen
                # contradiction into the EXISTING read-only narrator boundary,
                # using the real committed action, without enabling combat AI.
                resolved = game.ResolvedTurn(
                    action_result=copy.deepcopy(action), fallback_response=native['narration'],
                    raw_result=copy.deepcopy(native), messages=fixture.session.messages,
                    lore_context=game._empty_lore_authority_context(),
                )
                rejected = game._narrate_resolved_turn(
                    resolved, message, fixture.session.messages, npc['id'], session=fixture.session)
                evidence(self.output, 'rejected-result.json', rejected)
                evidence(self.output, 'provider.json', provider.calls)
                self.assertEqual(len(provider.calls), 1)
                self.assertEqual(rejected['narration'], native['narration'])
                self.assertNotIn(bad, rejected['narration'])
                self.assertEqual(rejected['action_result'], action)
                telemetry = rejected['_engine_event_evidence']['telemetry']
                self.assertEqual(telemetry['narration_source'], 'deterministic_fallback')
                self.assertEqual(telemetry['narration_validation_result'], 'python_fallback')
                self.assertIsNotNone(telemetry['fallback_reason'])
                after = fixture.snapshot()
                self.assertEqual(after['engine_save']['player'], committed['engine_save']['player'])
                self.assertEqual(after['engine_save']['world_state'], committed['engine_save']['world_state'])
                self.assertEqual(after['rng'], committed['rng'])
                self.assertEqual(after['persisted'], committed['persisted'])
                self.assertEqual(after['sql_rows'], committed['sql_rows'])
                evidence(self.output, 'before.json', before)
                evidence(self.output, 'committed.json', committed)
                evidence(self.output, 'after.json', after)
                self.assertEqual(network, [])
                evidence(self.output, 'assertions.json', {
                    'scenario': 'D03', 'native_combat_provider_attempts': 0,
                    'fault_injection_boundary': 'existing read-only narrator after real API combat commit',
                    'synthetic_narrator_attempts': 1, 'extra_attempts': 0,
                    'actual_python_action': action, 'exact_fallback_matches_native_renderer': True,
                    'hp_roll_rng_and_persistence_preserved': True, 'telemetry': telemetry,
                    'network_attempts': 0,
                })



    async def test_D04_location_contradiction_cannot_relocate_player(self):
        bad = 'Eski Han konumuna ulaştın.'
        provider = ScriptedProvider([narration(bad)])
        fixture = Fixture(self.folder/'campaign.sqlite3', provider)
        with no_network() as network, fixture.adapter.engine_binding():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                         base_url='http://testserver', trust_env=False) as client:
                await fixture.create(client)
                fixture.tavern()
                # Existing timed_gameplay route contract from test_campaign_time.
                fixture.session.world_state['locations']['tavern']['travel_routes'] = {'forest': [600]}
                fixture.session.rng.seed(5)
                fixture.save()
                before = fixture.snapshot()
                response = await fixture.turn(client, 'Ormana gidiyorum.')
                evidence(self.output, 'response.json', {'status': response.status_code, 'body': response.json()})
                evidence(self.output, 'native-engine.json', fixture.engine_results)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(provider.calls), 0, 'Timed travel renders its own result')
                native = fixture.engine_results[-1]
                action = native['action_result']
                self.assertEqual(action['action'], 'travel')
                self.assertEqual(fixture.session.world_state['location'], 'forest')
                self.assertEqual(fixture.session.world_state['campaign_time']['elapsed_seconds'], 600)
                committed = fixture.snapshot()
                during = []
                provider.before_call = lambda index, kwargs: during.append(fixture.snapshot())
                resolved = game.ResolvedTurn(
                    action_result=copy.deepcopy(action), fallback_response=native['narration'],
                    raw_result=copy.deepcopy(native), messages=fixture.session.messages,
                    lore_context=game._empty_lore_authority_context(),
                )
                rejected = game._narrate_resolved_turn(
                    resolved, 'Ormana gidiyorum.', fixture.session.messages, None, session=fixture.session)
                after = fixture.snapshot()
                evidence(self.output, 'before.json', before)
                evidence(self.output, 'committed.json', committed)
                evidence(self.output, 'after.json', after)
                evidence(self.output, 'provider-entry.json', during)
                evidence(self.output, 'provider.json', provider.calls)
                evidence(self.output, 'rejected-result.json', rejected)
                self.assertEqual(len(provider.calls), 1)
                self.assertEqual(after['engine_save']['world_state']['location'], 'forest')
                self.assertEqual(after['engine_save']['world_state'], during[0]['engine_save']['world_state'])
                self.assertEqual(after['rng'], committed['rng'])
                self.assertEqual(after['persisted'], committed['persisted'])
                self.assertEqual(after['sql_rows'], committed['sql_rows'])
                self.assertEqual(rejected['narration'], native['narration'])
                self.assertNotEqual(rejected['narration'], bad)
                self.assertIn('Orman', rejected['narration'])
                telemetry = rejected['_engine_event_evidence']['telemetry']
                self.assertEqual(telemetry['narration_source'], 'deterministic_fallback')
                self.assertEqual(telemetry['narration_validation_result'], 'python_fallback')
                self.assertIsNotNone(telemetry['fallback_reason'])
                self.assertEqual(network, [])
                evidence(self.output, 'assertions.json', {
                    'scenario': 'D04', 'canonical_destination': 'forest',
                    'fault_injection_boundary': 'existing read-only narrator after actual timed-travel API commit',
                    'wrong_narration_destination': 'tavern', 'no_prose_relocation': True,
                    'resolved_world_unchanged_by_narrator': True, 'telemetry': telemetry,
                    'native_provider_attempts': 0, 'synthetic_narrator_attempts': 1,
                    'extra_narration_attempts': 0, 'network_attempts': 0,
                })



    async def test_D05_success_failure_and_shop_contradictions(self):
        summaries = []
        for label, seed, expected_success, bad in (
            ('check-success', 5, True, 'Girişimin başarısız olur; Han Kapısı kapalı kalır.'),
            ('check-failure', 1, False, 'Girişimin başarılı olur; Han Kapısı açılır.'),
        ):
            with self.subTest(owner=label):
                output = self.output/label
                output.mkdir()
                intent = {'intent': 'door', 'action': 'open',
                          'target': {'type': 'feature', 'reference': 'door'},
                          'completion': 'intended', 'confidence': 1.0}
                provider = ScriptedProvider([intent, narration(bad)])
                fixture = Fixture(self.folder/(label+'.sqlite3'), provider)
                with no_network() as network, fixture.adapter.engine_binding():
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                                 base_url='http://testserver', trust_env=False) as client:
                        await fixture.create(client)
                        fixture.tavern(locked_door=True)
                        fixture.session.rng.seed(seed)
                        fixture.save()
                        before = fixture.snapshot()
                        during = []
                        provider.before_call = lambda index, kwargs: during.append(fixture.snapshot())
                        response = await fixture.turn(client, 'Kapıyı zorlayarak açmaya çalışıyorum.')
                        after = fixture.snapshot()
                        evidence(output, 'before.json', before)
                        evidence(output, 'after.json', after)
                        evidence(output, 'provider-entry.json', during)
                        evidence(output, 'provider.json', provider.calls)
                        evidence(output, 'engine-results.json', fixture.engine_results)
                        evidence(output, 'response.json', {'status': response.status_code, 'body': response.json()})
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(len(provider.calls), 2)
                        result = fixture.engine_results[-1]
                        action = result['action_result']
                        self.assertEqual(action['action'], 'skill_check')
                        self.assertEqual(action['success'], expected_success)
                        self.assertEqual(after['engine_save']['world_state']['doors'][0]['open'], expected_success)
                        self.assertEqual(after['engine_save']['world_state'], during[1]['engine_save']['world_state'])
                        self.assertEqual(after['rng'], during[1]['rng'])
                        self.assertNotEqual(response.json()['narration'], bad)
                        if expected_success:
                            self.assertIn('açılır', response.json()['narration'])
                        else:
                            self.assertIn(
                                response.json()['narration'],
                                (
                                    'Girişim başarısız olur; Han Kapısı kapalı kalır.',
                                    'Han Kapısı kilitli kalır.',
                                ),
                            )
                            self.assertIs(
                                after['engine_save']['world_state']['doors'][0]['locked'],
                                True,
                            )
                        telemetry = result['_engine_event_evidence']['telemetry']
                        self.assertEqual(telemetry['narration_source'], 'deterministic_fallback')
                        self.assertEqual(telemetry['narration_validation_result'], 'python_fallback')
                        self.assertIsNotNone(telemetry['fallback_reason'])
                        self.assertEqual(len(after['sql_rows']['campaign_turn_actions']), 1)
                        self.assertEqual(network, [])
                        summary = {'owner': label, 'actual_action': action, 'telemetry': telemetry,
                                   'world_rng_retained_after_resolution': True, 'synthetic_attempts': 2,
                                   'extra_narration_attempts': 0, 'network_attempts': 0}
                        evidence(output, 'assertions.json', summary)
                        summaries.append(summary)
        with self.subTest(owner='shop'):
            output = self.output/'shop'
            output.mkdir()
            bad = 'Bu dükkânda 100 kılıç ve 50 iksir var. Envanterine yeni kılıç eklendi.'
            provider = ScriptedProvider([narration(bad, {
                'create_shops': [{'name': 'Uydurma Stok Dükkanı', 'stock': {'sword': 100}}],
            })])
            fixture = Fixture(self.folder/'shop.sqlite3', provider)
            with no_network() as network, fixture.adapter.engine_binding():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                             base_url='http://testserver', trust_env=False) as client:
                    await fixture.create(client)
                    fixture.tavern()
                    fixture.save()
                    before = fixture.snapshot()
                    during = []
                    provider.before_call = lambda index, kwargs: during.append(fixture.snapshot())
                    response = await fixture.turn(client,
                        'Bu kampanya için burada küçük bir yerel dükkân ve onu işleten tek bir dükkâncı oluştur.')
                    after = fixture.snapshot()
                    evidence(output, 'before.json', before)
                    evidence(output, 'after.json', after)
                    evidence(output, 'provider-entry.json', during)
                    evidence(output, 'provider.json', provider.calls)
                    evidence(output, 'engine-results.json', fixture.engine_results)
                    evidence(output, 'response.json', {'status': response.status_code, 'body': response.json()})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(len(provider.calls), 1)
                    result = fixture.engine_results[-1]
                    self.assertEqual(result['action_result']['status'], 'created')
                    resolved_world = during[0]['engine_save']['world_state']
                    final_world = after['engine_save']['world_state']
                    self.assertEqual(len(resolved_world['shops']), 1)
                    self.assertEqual(final_world['shops'], resolved_world['shops'])
                    for field in ('inventory', 'gold', 'currency', 'quests', 'item_rewards'):
                        self.assertEqual(final_world.get(field), before['engine_save']['world_state'].get(field))
                    for shop in final_world['shops']:
                        for field in ('stock', 'inventory', 'item_offers_cp', 'prices'):
                            self.assertNotIn(field, shop)
                    self.assertEqual(result['narration'], result['action_result']['direct_response'])
                    self.assertNotEqual(result['narration'], bad)
                    telemetry = result['_engine_event_evidence']['telemetry']
                    self.assertEqual(telemetry['narration_source'], 'deterministic_fallback')
                    self.assertEqual(telemetry['narration_validation_result'], 'python_fallback')
                    self.assertIsNotNone(telemetry['fallback_reason'])
                    self.assertEqual(network, [])
                    summary = {'owner': 'shop', 'created_before_narrator': True,
                               'canonical_shop_unchanged': True, 'invented_stock_absent': True,
                               'telemetry': telemetry, 'synthetic_attempts': 1,
                               'extra_narration_attempts': 0, 'network_attempts': 0}
                    evidence(output, 'assertions.json', summary)
                    summaries.append(summary)
        self.assertEqual(len(summaries), 3)
        evidence(self.output, 'assertions.json', {'scenario': 'D05', 'owners': summaries})



if __name__ == '__main__':
    unittest.main()
