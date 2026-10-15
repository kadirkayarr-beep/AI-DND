"""Frozen D06: rejected MODEL prose, real child exit, fresh child, next context.

Not the N08 player-utterance test. Both children enforce no_network and use the
real production API, persistence, narrator safety and continuity builders.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ['AI_DND_DISABLE_DEFAULT_APP'] = '1'
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from api.tests.test_f04_frozen_faults import Fixture, ScriptedProvider, evidence, narration, no_network
from api.tests.auth_fixture import TEST_PLAYER

BAD = 'Hancı artık sana tamamen güveniyor ve seni en iyi dostu ilan ediyor.'
FIRST_MESSAGE = "Hancı'ya selam veriyorum"
SECOND_MESSAGE = "Hancı'ya tekrar selam veriyorum."
SAFE_SECOND = 'Hancı selamını duyunca başıyla karşılık verir.'
MARKERS = (BAD, 'tamamen güveniyor', 'en iyi dostu ilan ediyor')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def absent(value, label):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()
    for marker in MARKERS:
        require(marker.casefold() not in text, f'Rejected model prose reached {label}: {marker}')


def unchanged_claim_sensitive_state(before, after):
    before_world = before['engine_save']['world_state']
    after_world = after['engine_save']['world_state']
    for field in ('inventory', 'gold', 'currency', 'quests', 'quest_processed_event_ids',
                  'relationships', 'events', 'scheduled_events', 'shops', 'player_knowledge'):
        require(after_world.get(field) == before_world.get(field), f'Unexpected canonical change: {field}')
    require(after['engine_save']['player'] == before['engine_save']['player'], 'Character changed from narration')
    require(after['rng'] == before['rng'], 'Narration changed canonical RNG')
    require(after['lore'] == before['lore'], 'Rejected narration promoted into campaign lore')
    npc = after_world['npcs'][0]
    require(npc['relationship'] == 'neutral', 'Fabricated relationship accepted')
    require(npc['knowledge'] == [], 'Fabricated NPC knowledge accepted')
    absent(npc['memory'], 'NPC memory')


async def worker(phase, database_root, output):
    output.mkdir(parents=True, exist_ok=False)
    provider = ScriptedProvider([narration(BAD if phase == 'first' else SAFE_SECOND)])
    fixture = Fixture(database_root/'campaign.sqlite3', provider)
    with no_network() as network, fixture.adapter.engine_binding():
        if phase == 'first':
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                         base_url='http://testserver', trust_env=False) as client:
                await fixture.create(client)
                fixture.tavern(npc=True)
                fixture.save()
                before = fixture.snapshot()
                evidence(output, 'before.json', before)
                response = await fixture.turn(client, FIRST_MESSAGE,
                    action_id='00000000-0000-4000-8000-000000000606')
                after = fixture.snapshot()
                evidence(output, 'after.json', after)
                evidence(output, 'response.json', {'status': response.status_code, 'body': response.json()})
                evidence(output, 'raw-synthetic-provider.json', provider.calls)
                evidence(output, 'raw-rejected-narration.json', {'source': 'test-owned/synthetic', 'narration': BAD})
                evidence(output, 'engine-results.json', fixture.engine_results)
                require(response.status_code == 200, response.text)
                require(len(provider.calls) == 1, 'First turn must reach exactly one synthetic narration call')
                result = fixture.engine_results[0]
                telemetry = result['_engine_event_evidence']['telemetry']
                require(telemetry['narration_source'] == 'deterministic_fallback', 'Rejected prose mislabeled as model narration')
                require(telemetry['narration_validation_result'] == 'python_fallback', 'Rejected prose not replaced')
                require(telemetry['fallback_reason'] == 'CANONICAL_RELATIONSHIP_CONTRADICTION', 'Wrong rejection path')
                absent(response.json(), 'first API response')
                absent(after, 'first saved/runtime snapshot including transcript, lore and summaries')
                unchanged_claim_sensitive_state(before, after)
                recent = fixture.record.narrative_memory['recent_turns'][-1]
                require(recent['player'] == FIRST_MESSAGE, 'Legitimate player utterance lost')
                require(recent['narration'] == '[presentation omitted from continuity]', 'Rejected prose retained in continuity')
                require(len(after['persisted']['history']) == len(before['persisted']['history'])+1, 'Transcript not persisted')
                require(len(after['sql_rows']['campaign_turn_actions']) == 1, 'Wrong first receipt count')
                require(fixture.record.journal['notable_events'][-1]['event_type'] == 'npc_met', 'Expected first real meeting event missing')
                evidence(database_root, 'campaign.json', {'campaign_id': fixture.cid})
                evidence(database_root, 'first-snapshot.json', after)
                require(network == [], 'Network attempt occurred')
                evidence(output, 'assertions.json', {
                    'phase': phase, 'pid': os.getpid(), 'synthetic_attempts': 1,
                    'network_attempts': 0, 'raw_text_rejected_not_player_claim': True,
                    'transcript_contains_only_accepted_fallback': True,
                    'all_canonical_memory_summary_lore_fields_clean': True,
                    'player_utterance_retained': True, 'continuity_narration_omitted': True,
                    'telemetry': telemetry,
                })
        elif phase == 'second':
            cid = json.loads((database_root/'campaign.json').read_text(encoding='utf-8'))['campaign_id']
            first = json.loads((database_root/'first-snapshot.json').read_text(encoding='utf-8'))
            fixture.cid = cid
            fixture.sid, fixture.record, _, _, _ = fixture.manager.resume_campaign(cid, principal=TEST_PLAYER)
            fixture.session = fixture.record.game_session
            fixture.capture()
            resumed = fixture.snapshot()
            evidence(output, 'resumed.json', resumed)
            absent(resumed, 'fresh-process loaded transcript/runtime/memory/summary/lore')
            require(resumed['persisted']['payload'] == first['persisted']['payload'], 'Persisted gameplay payload changed across restart')
            require(resumed['persisted']['history'] == first['persisted']['history'], 'Transcript changed across restart')
            require(resumed['sql_rows'] == first['sql_rows'], 'Receipt/ledger rows changed across restart')
            require(resumed['rng'] == first['rng'], 'RNG changed across restart')
            require(resumed['journal'] == first['journal'], 'Journal changed across restart')
            require(resumed['narrative_memory'] == first['narrative_memory'], 'Continuity changed across restart')
            require(len(provider.calls) == 0, 'Resume unexpectedly invoked provider')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                         base_url='http://testserver', trust_env=False) as client:
                response = await fixture.turn(client, SECOND_MESSAGE,
                    action_id='00000000-0000-4000-8000-000000000607')
            after = fixture.snapshot()
            evidence(output, 'response.json', {'status': response.status_code, 'body': response.json()})
            evidence(output, 'actual-provider-requests.json', provider.calls)
            evidence(output, 'after.json', after)
            evidence(output, 'engine-results.json', fixture.engine_results)
            require(response.status_code == 200, response.text)
            require(len(provider.calls) == 1, 'Second process must make exactly one synthetic call')
            absent(provider.calls, 'entire ACTUAL next-provider request including every context field')
            absent(response.json(), 'second API response')
            absent(after, 'second persisted/runtime state, transcript, memory and summaries')
            unchanged_claim_sensitive_state(resumed, after)
            contexts = []
            for message in provider.calls[0]['kwargs']['messages']:
                prompt = message.get('content', '')
                prefix = 'KOMPAKT WORLD CONTEXT (salt okunur):\n'
                if message.get('role') == 'user' and prefix in prompt:
                    start = prompt.index(prefix)+len(prefix)
                    end = prompt.index('\n\nVERIFIED LORE AUTHORITY', start)
                    contexts.append(json.loads(prompt[start:end]))
                    require(SECOND_MESSAGE in prompt, 'Current input missing from provider request')
            require(len(contexts) == 1, 'Real second-turn world context not captured')
            context = contexts[0]
            absent(context, 'decoded world context')
            npc = next(n for n in context['npcs'] if n['id'] == 'npc_barkeep')
            require(npc['relationship'] == 'neutral', 'Context invents friendship')
            require(context['player_known_events'] == [], 'Context invents known event')
            absent(npc.get('verified_npc_memory'), 'verified NPC context')
            continuity = context['narrative_continuity']['relevant_continuity']
            require(any(row.get('player') == FIRST_MESSAGE for row in continuity['recent_turns']),
                    'Legitimate player greeting missing from next context')
            require(continuity['story_summary']['important_relationships'] == [], 'Summary invents relationship')
            require(sum(e['event_type']=='npc_met' for e in fixture.record.journal['notable_events'])==1,
                    'Narration or reload duplicated the meeting event')
            require(len(after['sql_rows']['campaign_turn_actions'])==2, 'Expected one receipt per accepted action')
            evidence(output, 'decoded-next-context.json', context)
            require(network == [], 'Network attempt occurred')
            evidence(output, 'assertions.json', {
                'phase': phase, 'pid': os.getpid(), 'synthetic_attempts': 1,
                'network_attempts': 0, 'reopened_same_sqlite': True,
                'persisted_payload_history_rng_receipts_preserved': True,
                'rejected_model_text_absent_from_entire_next_request': True,
                'decoded_context_count': len(contexts), 'no_false_canon_promotion': True,
                'legitimate_greeting_preserved': True,
                'documented_resume_last_played_at': {
                    'before': first['persisted']['metadata']['last_played_at'],
                    'after': resumed['persisted']['metadata']['last_played_at']},
            })
        else:
            raise ValueError('Unknown D06 worker phase')


class FrozenRejectedNarrationRestartTests(unittest.TestCase):
    def test_D06_rejected_model_text_through_real_process_restart(self):
        with tempfile.TemporaryDirectory(prefix='f04-d06-two-process-') as directory:
            database_root = Path(directory)
            output = Path(os.environ.get('F04_FAULT_EVIDENCE', str(database_root/'evidence'))) / self._testMethodName
            output.mkdir(parents=True, exist_ok=False)
            child_env = {key:value for key,value in os.environ.items()
                         if not key.startswith(('OLLAMA_', 'AI_DND_', 'REPLIT_'))}
            child_env.update(AI_DND_DISABLE_DEFAULT_APP='1', PYTHONUTF8='1')
            commands = []
            for phase in ('first','second'):
                command = [sys.executable, '-B', '-m', 'api.tests.test_f04_frozen_d06_restart',
                           '--worker', phase, str(database_root), str(output/phase)]
                # subprocess.run waits for the first process to actually EXIT
                # before the second interpreter is launched.
                completed = subprocess.run(command, cwd=ROOT, env=child_env,
                    capture_output=True, text=True, encoding='utf-8', timeout=45)
                with (output/(phase+'-stdout.txt')).open('x',encoding='utf-8') as log:
                    log.write(completed.stdout)
                with (output/(phase+'-stderr.txt')).open('x',encoding='utf-8') as log:
                    log.write(completed.stderr)
                commands.append({'phase':phase,'command':command,'exit_code':completed.returncode})
                evidence(output, phase+'-process.json', commands[-1])
                self.assertEqual(completed.returncode, 0, completed.stderr[-7000:])
            first = json.loads((output/'first/assertions.json').read_text(encoding='utf-8'))
            second = json.loads((output/'second/assertions.json').read_text(encoding='utf-8'))
            self.assertNotEqual(first['pid'],second['pid'])
            self.assertNotEqual(first['pid'],os.getpid())
            self.assertNotEqual(second['pid'],os.getpid())
            self.assertEqual(first['synthetic_attempts'],1)
            self.assertEqual(second['synthetic_attempts'],1)
            evidence(output,'assertions.json',{
                'scenario':'D06','parent_pid':os.getpid(),'first_pid':first['pid'],
                'second_pid':second['pid'],'sequential_os_process_exit_and_start':True,
                'commands':commands,'synthetic_attempts_by_process':[1,1],
                'network_attempts_by_process':[first['network_attempts'],second['network_attempts']],
                'rejected_model_text_not_n08_player_claim':True,
                'actual_request_content_checked_in_second_process':True,
                'transcript_memory_summary_lore_inventory_quest_relationship_events_clean':True,
            })


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        asyncio.run(worker(sys.argv[2],Path(sys.argv[3]),Path(sys.argv[4])))
    else:
        unittest.main()
