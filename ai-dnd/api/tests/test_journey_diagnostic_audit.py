"""Diagnostic evidence only: expected known breaks never imply product acceptance."""
import json
from dataclasses import replace
from unittest.mock import patch
import game
from api.tests.journeys.runner import SCENARIO_DIR, JourneyCase, describe_problems, summary_line
from api.tests.journeys.schema import load_scenario
from api.tests.test_journeys import MIN_SCENARIOS, loose_causes

class JourneyDiagnosticAudit(JourneyCase):
    async def test_record_current_scenario_failures(self):
        all_results = {}
        records = []
        for path in sorted(SCENARIO_DIR.glob('*.json')):
            scenario = load_scenario(path)
            results = await self.run_scenario(scenario)
            all_results[scenario.id] = results
            for step, result in zip(scenario.steps, results):
                self.assertFalse(step.known_broken and not step.broken_because)
                if result.status == 'known_broken':
                    self.assertEqual(loose_causes(step, result.failures), [])
                records.append({'scenario': scenario.id, 'step': result.index,
                    'status': result.status, 'failures': result.failures, 'items': result.items,
                    'marked': bool(step.known_broken), 'real_chain': step.real_chain,
                    'independent': step.independent, 'seconds': result.seconds})
            self.assertEqual(describe_problems(results), [], scenario.id)
        self.assertGreaterEqual(len(all_results), MIN_SCENARIOS)
        print('JOURNEY_AUDIT_DATA:' + json.dumps({'product_acceptance': False,
            'summary': summary_line(all_results), 'steps': records}, ensure_ascii=False))

    async def test_room_payment_never_works_an_accepted_shift(self):
        source = load_scenario(SCENARIO_DIR / '18_room_phrase_not_job.json')
        step = replace(source.steps[0], expect={'kese': 100, 'saat': 0}, known_broken=(), broken_because=())
        results = await self.run_scenario(replace(source, steps=(step,)))
        self.assertEqual(describe_problems(results), [])

    async def test_explicit_work_still_completes_the_accepted_shift(self):
        source = load_scenario(SCENARIO_DIR / '18_room_phrase_not_job.json')
        step = replace(source.steps[0], say='Sayım işini yapıyorum',
            script={'front': {'kind': 'work'}}, expect={'kese': 126, 'saat': 8}, known_broken=(), broken_because=())
        results = await self.run_scenario(replace(source, steps=(step,)))
        self.assertEqual(describe_problems(results), [])

    async def test_direct_dispatch_payment_never_works_a_shift(self):
        source = load_scenario(SCENARIO_DIR / '18_room_phrase_not_job.json')
        step = replace(source.steps[0], expect={'kese': 100, 'saat': 0}, known_broken=(), broken_because=())
        # Bypass only the optional read-ahead boundary; the real dispatch invokes its normal front reader.
        with patch.object(game.GameSession, 'front_read_ahead', return_value=None, create=True):
            results = await self.run_scenario(replace(source, steps=(step,)))
        self.assertEqual(describe_problems(results), [])

    async def test_real_work_after_payment_still_advances_and_pays(self):
        source = load_scenario(SCENARIO_DIR / '18_room_phrase_not_job.json')
        payment = replace(source.steps[0], expect={'kese': 100, 'saat': 0}, known_broken=(), broken_because=())
        work = replace(payment, say='Sayım işini yapıyorum', script={'front': {'kind': 'work'}}, expect={'kese': 126, 'saat': 8})
        results = await self.run_scenario(replace(source, steps=(payment, work)))
        self.assertEqual(describe_problems(results), [])

    async def test_zero_coin_conversation_does_not_disable_real_work_fallback(self):
        source = load_scenario(SCENARIO_DIR / '18_room_phrase_not_job.json')
        step = replace(source.steps[0], say='Sayım işini yapıyorum', script={'front': {'kind': 'speak_to', 'person_id': 'barman', 'coin_cp': 0}}, expect={'kese': 126, 'saat': 8}, known_broken=(), broken_because=())
        results = await self.run_scenario(replace(source, steps=(step,)))
        self.assertEqual(describe_problems(results), [])
