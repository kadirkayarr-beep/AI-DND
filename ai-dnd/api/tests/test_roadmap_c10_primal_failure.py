"""Targeted review regression: preserve existing retryable intent failure semantics."""
import unittest
from unittest.mock import patch

import game
from api.tests.test_roadmap_c10_primal_knowledge import selected, turn


class PrimalKnowledgeInfrastructureTests(unittest.TestCase):
    def test_malformed_classifier_reply_keeps_the_check_retryable_and_no_evidence(self):
        # Only the explicit check stays a failure now: an ordinary turn was moved to a
        # story reply at the owner's request, and a story cannot stand in for this check.
        session, _ = selected(self)
        before = session._capture_runtime_snapshot()
        malformed = {'message': {'content': 'not usable JSON'}}
        evidence = []
        try:
            with patch('game.ollama.chat', return_value=malformed):
                opted = turn(session, evidence=evidence, action_id='retry-same-action')
        except ValueError as exc:
            self.fail('Existing transient intent failure was reclassified as unsupported feature: ' + str(exc))
        self.assertEqual(opted['action_result']['status'], 'infrastructure_failure')
        self.assertEqual(opted['action_result']['infrastructure_code'], 'intent_json_invalid')
        self.assertEqual(evidence, [])
        self.assertEqual(session._capture_runtime_snapshot(), before)
        # Same one-shot command can be retried after a usable classifier reply.
        usable = {'message': {'content': '{"world_updates": {}, "narration": "Hamlen çözülür.", "lore_claims": []}'}}
        with patch('game.ollama.chat', return_value=usable):
            retried = turn(session, evidence=evidence, action_id='retry-same-action')
        self.assertEqual(retried['action_result']['ability'], 'strength')
        self.assertEqual(len(evidence), 1)

    def test_authoritative_intent_failure_restores_prior_route_mutation_and_rng(self):
        session, _ = selected(self)
        before = session._capture_runtime_snapshot()
        evidence = []
        def fail(*args, **kwargs):
            session.world_state['flags']['synthetic_before_failure'] = True
            session.rng.randint(1, 20)
            raise game.IntentInfrastructureError('intent_timeout')
        try:
            with patch('game.parse_player_intent', side_effect=fail):
                result = turn(session, evidence=evidence, action_id='timeout-action')
        except ValueError as exc:
            self.fail('Authoritative timeout changed into non-retryable refusal: ' + str(exc))
        self.assertEqual(result['action_result'], {
            'action': 'unknown', 'status': 'infrastructure_failure', 'success': False,
            'state_changes': [], 'infrastructure_code': 'intent_timeout',
            'direct_response': 'Bu hamle tamamlanamadı; dünya durumu değişmedi.',
        })
        self.assertEqual(result['narration'], result['action_result']['direct_response'])
        self.assertEqual(evidence, [])
        self.assertEqual(session._capture_runtime_snapshot(), before)
