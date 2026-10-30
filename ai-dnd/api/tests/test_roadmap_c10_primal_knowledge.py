"""Selected Primal Knowledge immediate checks; synthetic dice/model transport only.

Creation, earned progression, Rage activation and combat exit use existing owners.
Unit-only altered exhaustion/conditions test boundaries, never native acceptance.
"""
import copy
import inspect
import json
import unittest
from unittest.mock import patch

import game
import xp
import barbarian_rage as rage
import character_progression as progression
from api.core_resolution import resolution_action_scope
from api.tests.test_roadmap_c10_rage import combat
from api.tests.test_roadmap_c10_berserker_progression import apply

SKILLS = ('Acrobatics', 'Intimidation', 'Perception', 'Stealth', 'Survival')
NORMAL = ('dexterity', 'charisma', 'wisdom', 'dexterity', 'wisdom')
SCORES = dict(strength=14, dexterity=8, constitution=13, intelligence=10, wisdom=12, charisma=15)


def selected(test, *, raging=True, outside=True):
    session, npc = combat(ability_scores=SCORES)
    # A synthetic pre-existing Acrobatics proficiency; choice provenance is then
    # recorded by the real earned-level owner, not forged after selection.
    session.character['proficient_skills'].append('Acrobatics')
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 600, 'quest:primal-earned')
    apply(test, session)
    session.ensure_combat_state()
    if raging:
        rage.activate(session)
    if outside:
        session.end_combat('unit_immediate_check')
    return session, npc


def roll(session, skill='Acrobatics', *, feature='primal_knowledge', **kwargs):
    # Before the feature exists, exercise its actual old branch, so RED is the
    # intended wrong-ability assertion rather than a missing-keyword TypeError.
    if 'check_feature' in inspect.signature(game.perform_skill_check).parameters:
        kwargs['check_feature'] = feature
    c = session.character
    return session.perform_skill_check(skill, 15, c['modifiers'], c['proficient_skills'], c['proficiency_bonus'], **kwargs)


WORDS = ('Takla atıyorum', 'Onu korkutmaya çalışıyorum', 'Bir şey fark etmeye çalışıyorum', 'Gizleniyorum', 'Yolumu buluyorum')


def turn(session, text='Takla atıyorum', *, feature='primal_knowledge', evidence=None, **kwargs):
    if 'check_feature' in inspect.signature(game.run_player_turn).parameters:
        kwargs.update(check_feature=feature, check_evidence=evidence)
    kwargs.setdefault('interaction_mode', 'do')
    return session.run_player_turn(text, **kwargs)


def execute(session, text='Takla atıyorum', **kwargs):
    if 'check_feature' in inspect.signature(game.execute_intent).parameters:
        kwargs['check_feature'] = 'primal_knowledge'
    return session.execute_intent({'intent': 'unknown'}, text, **kwargs)


class PrimalKnowledgeCoreTests(unittest.TestCase):
    def test_explicit_opt_in_changes_each_five_to_strength_and_keeps_default(self):
        for skill, normal in zip(SKILLS, NORMAL):
            with self.subTest(skill=skill):
                session, _ = selected(self)
                before = copy.deepcopy(session.world_state['rage_v1'])
                with patch('game.roll_d20', side_effect=[5, 16]):
                    result = roll(session, skill)
                self.assertEqual(result['ability'], 'strength')
                self.assertEqual(result['modifier'], 2)
                self.assertEqual(result['dice_rolls'], [5, 16])
                self.assertTrue(result['advantage'])
                self.assertEqual(session.world_state['rage_v1'], before)
                with patch('game.roll_d20', return_value=7):
                    ordinary = roll(session, skill, feature=None)
                self.assertEqual(ordinary['ability'], normal)
                self.assertEqual(ordinary['dice_rolls'], [7])
                self.assertNotIn('check_feature', ordinary)

    def test_acrobatics_literal_proficiency_expertise_exhaustion_and_cancellation(self):
        session, _ = selected(self)
        for expertise, exhaustion, disadvantage, expected in (
            (False, 0, False, 20), (True, 0, False, 22),
            (True, 2, False, 18), (False, 1, True, 7),
        ):
            with self.subTest(expertise=expertise, exhaustion=exhaustion, disadvantage=disadvantage):
                session.character['exhaustion'] = exhaustion
                with patch('game.roll_d20', side_effect=[5, 16]):
                    result = roll(session, expertise_skills=['Acrobatics'] if expertise else [], disadvantage=disadvantage)
                self.assertEqual(result['ability'], 'strength')
                self.assertEqual(result['total'], expected)
                self.assertEqual(result['proficiency_bonus'], 4 if expertise else 2)
                self.assertEqual(result['dice_rolls'], [5] if disadvantage else [5, 16])
                self.assertEqual(result['resolution']['modifier_breakdown']['circumstantial_modifier'], -2 * exhaustion)

    def test_nonproficient_intimidation_still_uses_strength_without_proficiency(self):
        session, _ = selected(self)
        with patch('game.roll_d20', side_effect=[5, 16]):
            result = roll(session, 'Intimidation')
        self.assertEqual((result['ability'], result['proficiency_bonus'], result['total']), ('strength', 0, 18))

    def test_invalid_entitlement_rage_feature_and_foreign_skill_are_atomic(self):
        changes = (
            lambda s: s.character.update({'class': 'Fighter'}),
            lambda s: s.character.update(progression_level=2),
            lambda s: s.character.update(level=True),
            lambda s: s.character.pop('primal_knowledge_choice'),
            lambda s: s.character['primal_knowledge_choice'].update(skill='Perception'),
            lambda s: s.world_state['rage_v1'].update(active=None),
            lambda s: s.world_state['campaign_time'].update(elapsed_seconds=12),
            lambda s: s.character.update(conditions=['incapacitated']),
        )
        for change in changes:
            session, _ = selected(self)
            change(session)
            before = session._capture_runtime_snapshot()
            with self.subTest(change=change), self.assertRaises(ValueError):
                roll(session)
            self.assertEqual(session._capture_runtime_snapshot(), before)
        for feature, skill in ((True, 'Acrobatics'), ('other', 'Acrobatics'), ('primal_knowledge', 'Athletics')):
            session, _ = selected(self)
            before = session._capture_runtime_snapshot()
            with self.subTest(feature=feature, skill=skill), self.assertRaises(ValueError):
                roll(session, skill, feature=feature)
            self.assertEqual(session._capture_runtime_snapshot(), before)


    def test_actual_execute_intent_each_skill_carries_raw_dice_and_strength(self):
        for skill, text in zip(SKILLS, WORDS):
            with self.subTest(skill=skill):
                session, _ = selected(self)
                with patch('game.roll_d20', side_effect=[5, 16]):
                    result = execute(session, text)
                self.assertEqual((result['skill'], result['ability']), (skill, 'strength'))
                self.assertEqual(result.get('dice_rolls'), [5, 16])
                self.assertEqual(result['resolution']['raw_rolls'], [5, 16])

    def test_whole_ordinary_pipeline_keeps_model_route_and_feature_is_not_sticky(self):
        session, _ = selected(self)
        evidence = []
        packets = []
        def narrator(*args, **kwargs):
            packets.append(json.dumps(kwargs, ensure_ascii=False))
            return {'message': {'content': '{"world_updates": {}, "narration": "Hamlen çözülür.", "lore_claims": []}'}}
        before_rage = copy.deepcopy(session.world_state['rage_v1'])
        with patch('game.ollama.chat', side_effect=narrator), patch('game.roll_d20', side_effect=[5, 16]):
            result = turn(session, evidence=evidence, action_id='unit-primal-action', session_id='unit-session')
        self.assertEqual(result['action_result'].get('ability'), 'strength')
        self.assertEqual(result['action_result'].get('dice_rolls'), [5, 16])
        self.assertEqual(len(evidence), 1)
        self.assertGreaterEqual(len(packets), 1)  # Existing model-backed path, not a new bypass.
        self.assertEqual(session.world_state['rage_v1'], before_rage)
        for packet in packets:
            self.assertNotIn('check_evidence', packet)
            self.assertNotIn('rage_activation', packet)
        json.dumps(result)
        json.dumps(session.messages)
        json.dumps(session.serialize_game_state())
        with patch('game.ollama.chat', side_effect=narrator), patch('game.roll_d20', return_value=7):
            ordinary = turn(session, feature=None, action_id='unit-ordinary-action')
        self.assertEqual(ordinary['action_result']['ability'], 'dexterity')
        self.assertNotIn('check_feature', ordinary['action_result'])

    def test_mixed_timed_noncheck_and_combat_refuse_before_any_route_effect(self):
        texts = ('Selam', 'Tırmanıyorum', 'Takla atıyorum ve 10 dakika bekliyorum',
                 'Takla atıyorum. Sonra kılıcı bırakıyorum', 'Takla atıyorum bekliyorum',
                 '10 dakika etrafı araştırıyorum', '1 saat etrafı gözlemliyorum',
                 '/travel track trail:unit', '/travel reacquire', 'devam',
                 '"Takla atıyorum" diyor', 'Takla atmıyorum', 'Takla atıyorum?',
                 'Takla atıyorum ama saldırıyorum', 'Sessizce ilerliyorum')
        for text in texts:
            session, _ = selected(self)
            before = session._capture_runtime_snapshot()
            with self.subTest(text=text), patch('game._dispatch_player_turn', side_effect=AssertionError('mutating dispatcher reached')):
                with self.assertRaises(ValueError):
                    turn(session, text)
            self.assertEqual(session._capture_runtime_snapshot(), before)
        for kwargs in ({'interaction_mode': 'say'}, {'interaction_mode': 'ask_dm'},
                       {'combat_action': {'steps': [{'kind': 'end_turn'}]}}, {'feature': True}):
            session, _ = selected(self)
            before = session._capture_runtime_snapshot()
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                turn(session, **kwargs)
            self.assertEqual(session._capture_runtime_snapshot(), before)
        session, _ = selected(self, outside=False)
        before = session._capture_runtime_snapshot()
        with self.assertRaises(ValueError):
            turn(session)
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_pending_timed_task_tracking_and_event_routes_do_not_advance(self):
        for confined in (True, False):
            session, _ = selected(self)
            session.world_state['tracking'] = dict(trail_id='unit-trail', location_id='tavern', status='LOST', confined=confined, dc=15, spent_seconds=0, attempts=0)
            before = session._capture_runtime_snapshot()
            with self.assertRaises(ValueError):
                turn(session, '/travel reacquire')
            self.assertEqual(session._capture_runtime_snapshot(), before)
        session, _ = selected(self)
        session.world_state['active_task'] = dict(location_id='tavern', target_id='tavern', kind='search', required_seconds=360, spent_seconds=0, dc=15)
        before = session._capture_runtime_snapshot()
        with self.assertRaises(ValueError):
            turn(session, 'Takla atıyorum')
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_evidence_is_out_of_band_bound_to_completed_roll_not_current_rage(self):
        session, _ = selected(self)
        evidence = []
        kwargs = {'check_evidence': evidence} if 'check_evidence' in inspect.signature(game.perform_skill_check).parameters else {}
        with resolution_action_scope('primal-bound', 'session-bound'), patch('game.roll_d20', side_effect=[5, 16]):
            result = roll(session, **kwargs)
        self.assertEqual(len(evidence), 1)
        rage.end(session)
        check = getattr(rage, 'primal_knowledge_annotation', None)
        self.assertTrue(callable(check), 'live serializer needs the trusted evidence validator')
        action = dict(result, action='skill_check', action_id='primal-bound', resolution_id='primal-bound:skill_check:1')
        self.assertEqual(check(evidence[0], action), {'check_feature': 'primal_knowledge', 'original_ability': 'dexterity'})
        for field, value in (('ability', 'dexterity'), ('modifier', 99), ('skill', 'Stealth'), ('action_id', 'other')):
            changed = dict(action, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                check(evidence[0], changed)
        forged = dict(action, check_feature='primal_knowledge', original_ability='dexterity')
        with self.assertRaises(ValueError):
            check(forged, action)
        json.dumps(result)

    def test_execute_late_failure_restores_rng_world_and_evidence(self):
        session, _ = selected(self)
        before = session._capture_runtime_snapshot()
        evidence = []
        kwargs = {'check_evidence': evidence} if 'check_evidence' in inspect.signature(game.execute_intent).parameters else {}
        def fail(*args):
            session.world_state['flags']['synthetic_late_write'] = True
            raise RuntimeError('synthetic late check failure')
        with patch('game.apply_check_outcome_to_world_state', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'synthetic late check failure'):
                execute(session, **kwargs)
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertEqual(evidence, [])

    def test_projection_is_pure_selected_only_and_reports_active_rage(self):
        project = getattr(rage, 'primal_knowledge_projection', None)
        self.assertTrue(callable(project), 'authoritative projection missing')
        session, _ = selected(self)
        before = session._capture_runtime_snapshot()
        self.assertEqual(project(session), {'available': True, 'reason': None, 'skills': list(SKILLS)})
        self.assertEqual(session._capture_runtime_snapshot(), before)
        rage.end(session)
        self.assertFalse(project(session)['available'])
        session.character['progression_level'] = 2
        self.assertIsNone(project(session))


    def test_direct_roll_fault_rolls_back_rng_and_rejects_bad_evidence_sink_before_dice(self):
        session, _ = selected(self)
        before = session._capture_runtime_snapshot()
        original = game.roll_d20
        calls = []
        def fault():
            calls.append(True)
            value = original(session=session)
            if len(calls) == 2:
                raise RuntimeError('synthetic second die failure')
            return value
        with patch('game.roll_d20', side_effect=fault):
            with self.assertRaisesRegex(RuntimeError, 'synthetic second die failure'):
                roll(session)
        self.assertEqual(session._capture_runtime_snapshot(), before)
        with patch('game.roll_d20', side_effect=AssertionError('dice before sink validation')):
            with self.assertRaises(ValueError):
                roll(session, check_evidence={})
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_model_conflicting_travel_intent_cannot_reach_mutating_owner(self):
        session, _ = selected(self)
        before = session._capture_runtime_snapshot()
        with patch('timed_gameplay.start_travel', side_effect=AssertionError('wrong owner reached')):
            with self.assertRaises(ValueError):
                session.execute_intent({'intent': 'travel', 'target': {'reference': 'forest'}}, 'Takla atıyorum', check_feature='primal_knowledge')
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_rage_revalidated_at_roll_and_whole_turn_late_failure_does_not_publish(self):
        for failure in ('expired_before_roll', 'late_observation'):
            session, _ = selected(self)
            before = session._capture_runtime_snapshot()
            evidence = []
            original = game.perform_skill_check
            def expired(*args, **kwargs):
                rage.end(session)
                return original(*args, **kwargs)
            reply = {'message': {'content': '{"world_updates": {}, "narration": "Hamlen çözülür.", "lore_claims": []}'}}
            guard = (patch('game.perform_skill_check', side_effect=expired) if failure == 'expired_before_roll'
                     else patch('dialogue_runtime.observe_turn', side_effect=RuntimeError('synthetic late observation')))
            with self.subTest(failure=failure), patch('game.ollama.chat', return_value=reply), guard:
                with self.assertRaises((ValueError, RuntimeError)):
                    turn(session, evidence=evidence)
            self.assertEqual(session._capture_runtime_snapshot(), before)
            self.assertEqual(evidence, [])

    def test_ordinary_literal_result_and_player_npc_derived_values_unchanged(self):
        session, npc = selected(self)
        character = copy.deepcopy(session.character)
        npc_before = copy.deepcopy(npc)
        with resolution_action_scope('ordinary-fixture', 'fixture-session'), patch('game.roll_d20', return_value=7):
            ordinary = roll(session, feature=None)
        self.assertEqual({key: ordinary[key] for key in ('skill', 'ability', 'dice', 'dice_rolls', 'advantage', 'disadvantage', 'modifier', 'proficient', 'expertise', 'proficiency_bonus', 'total_bonus', 'total', 'dc', 'result')},
                         dict(skill='Acrobatics', ability='dexterity', dice=7, dice_rolls=[7], advantage=False, disadvantage=False, modifier=0, proficient=True, expertise=False, proficiency_bonus=2, total_bonus=2, total=9, dc=15, result='BAŞARISIZ'))
        with patch('game.roll_d20', side_effect=[5, 16]):
            roll(session, 'Perception')
        self.assertEqual(session.character, character)
        self.assertEqual(npc, npc_before)

    def test_pace_cancellation_uses_effective_strength_without_changing_owner(self):
        session, _ = selected(self)
        # Unit-only journey context tests arithmetic; public opt-in rejects travel.
        session.world_state['journey'] = {'status': 'TRAVELLING', 'pace': 'fast'}
        with patch('game.roll_d20', side_effect=[5, 16]):
            result = roll(session, 'Perception')
        self.assertTrue(result['advantage'])
        self.assertTrue(result['disadvantage'])
        self.assertEqual((result['dice_rolls'], result['total']), ([5], 9))

    def test_pure_admission_each_skill_and_pending_contexts(self):
        session, _ = selected(self)
        for skill, text in zip(SKILLS, WORDS):
            before = session._capture_runtime_snapshot()
            self.assertEqual(session.primal_knowledge_check_admission(text), {'action_type': 'check', 'skill': skill, 'difficulty': 'medium'})
            self.assertEqual(session._capture_runtime_snapshot(), before)
        session.world_state['scheduled_events'] = [{'decision_status': 'PENDING'}]
        before = session._capture_runtime_snapshot()
        with self.assertRaises(ValueError):
            session.primal_knowledge_check_admission('Takla atıyorum')
        self.assertEqual(session._capture_runtime_snapshot(), before)


    def test_each_skill_reaches_existing_whole_turn_check_route(self):
        for skill, text in zip(SKILLS, WORDS):
            with self.subTest(skill=skill):
                session, npc = selected(self)
                evidence = []
                reply = {'message': {'content': '{"world_updates": {}, "narration": "Hamlen çözülür.", "lore_claims": []}'}}
                kwargs = {}
                with patch('game.ollama.chat', return_value=reply), patch('game.roll_d20', side_effect=[5, 16]):
                    result = turn(session, text, evidence=evidence, action_id='five:' + skill, **kwargs)
                self.assertEqual((result['action_result'].get('skill'), result['action_result'].get('ability')), (skill, 'strength'))
                self.assertEqual(len(evidence), 1)


    def test_explicit_target_is_rejected_before_dispatch_ordinary_target_is_not_changed(self):
        session, npc = selected(self)
        before = session._capture_runtime_snapshot()
        with patch('game._dispatch_player_turn', side_effect=AssertionError('target route entered')):
            with self.assertRaises(ValueError):
                turn(session, 'Onu korkutmaya çalışıyorum', target_id=npc['id'])
        self.assertEqual(session._capture_runtime_snapshot(), before)
        reply = {'message': {'content': '{"world_updates": {}, "narration": "Hamlen çözülür.", "lore_claims": []}'}}
        with patch('game.ollama.chat', return_value=reply):
            ordinary = turn(session, 'Onu korkutmaya çalışıyorum', feature=None, target_id=npc['id'])
        self.assertNotEqual(ordinary['action_result'].get('action'), 'skill_check')
        self.assertNotIn('check_feature', ordinary['action_result'])

    def test_admitted_wording_preserves_actual_ordinary_immediate_owner(self):
        texts = ('Takla atacağım', 'Dengede yürüyorum', 'Dengede kalıyorum',
                 'İp üzerinde yürüyorum', 'Akrobatik hareket yapıyorum',
                 'Gözdağı vermeye çalışıyorum', 'Tehdit ediyorum',
                 'Ses dinliyorum', 'Etrafı gözlemliyorum',
                 'Tehlikeyi fark etmeye çalışıyorum', 'Bir şey duymaya çalışıyorum',
                 'Saklanıyorum', 'Yönümü buluyorum',
                 'Yiyecek arıyorum', 'Barınak kurmaya çalışıyorum')
        reply = {'message': {'content': '{"world_updates": {}, "narration": "Hamlen çözülür.", "lore_claims": []}'}}
        for text in texts:
            session, _ = selected(self)
            with self.subTest(text=text):
                selected_check = session.primal_knowledge_check_admission(text)
                with patch('game.ollama.chat', return_value=reply), patch('game.roll_d20', return_value=10):
                    ordinary = turn(session, text, feature=None)
                self.assertEqual(ordinary['action_result'].get('action'), 'skill_check', ordinary['action_result'])
                self.assertEqual(ordinary['action_result'].get('skill'), selected_check['skill'])


if __name__ == '__main__':
    unittest.main()
