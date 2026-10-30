"""Preparatory persistence boundary; detached future claims are not level admission."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import character_progression as cp
import feat_rules
import game
from api.character_creation import configure_character
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_starting_xp import create

RECORD = {'class_level': 4, 'feat': 'Ability Score Improvement', 'increase': {'constitution': 2}}


class AsiPersistenceBoundaryTests(unittest.TestCase):
    def test_nonempty_presence_without_progression_markers_is_rejected(self):
        player = {'class': 'Sorcerer', 'level': 1, 'asi_choices': [copy.deepcopy(RECORD)]}
        before = copy.deepcopy(player)
        with self.assertRaises(ValueError):
            cp.validate_saved(player, {})
        self.assertEqual(player, before)

    def test_writer_rejects_malformed_and_nonempty_instead_of_dropping(self):
        for value in (None, {}, (), '', False, [RECORD], [RECORD, RECORD], [None]):
            with self.subTest(value=value):
                session = create(3)
                session.character['asi_choices'] = copy.deepcopy(value)
                before = session._capture_runtime_snapshot()
                with self.assertRaises(ValueError): session.serialize_game_state()
                self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_absent_and_exact_empty_real_save_load_clear_only_owned_state(self):
        for empty in (False, True):
            session = create(3)
            if empty: session.character['asi_choices'] = []
            payload = session.serialize_game_state()
            self.assertNotIn('asi_choices', payload['player'])
            if empty: payload['player']['asi_choices'] = []
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'save.json'
                path.write_text(json.dumps(payload), encoding='utf-8')
                session.character['asi_choices'] = [copy.deepcopy(RECORD)]
                session.character['feats'] = ['unrelated-test-state']
                session.load_game(path)
                self.assertNotIn('asi_choices', session.character)
                self.assertEqual(session.character['feats'], ['unrelated-test-state'])
                self.assertEqual(session.character['constitution'], 14)
                self.assertEqual(session.character['max_hp'], 20)
                self.assertEqual(session.character['current_hp'], 20)
                session.save_game(path)
                session.load_game(path)
                self.assertNotIn('asi_choices', session.character)

    def test_bad_load_rejects_before_any_mutation(self):
        session = create(3)
        payload = session.serialize_game_state()
        for value in (None, {}, [RECORD], [None]):
            bad = copy.deepcopy(payload)
            bad['player']['asi_choices'] = copy.deepcopy(value)
            before = session._capture_runtime_snapshot()
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'save.json'
                path.write_text(json.dumps(bad), encoding='utf-8')
                with self.assertRaises(ValueError): session.load_game(path)
            self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_direct_and_progression_creation_clear_owned_stale_field(self):
        session = create(3)
        for direct in (False, True):
            session.character['asi_choices'] = [copy.deepcopy(RECORD)]
            session.character['feats'] = ['unrelated-test-state']
            if direct: configure_character(session, mode='custom', **copy.deepcopy(SPEC))
            else: cp.create_at_level(session, copy.deepcopy(SPEC), 1)
            self.assertNotIn('asi_choices', session.character)
            self.assertEqual(session.character['feats'], ['unrelated-test-state'])

    def test_applied_five_and_creation_four_remain_blocked(self):
        session = create(3)
        before = session._capture_runtime_snapshot()
        self.assertEqual(cp.preview_level_up(session, 5)['status'], 'blocked')
        with self.assertRaises(ValueError): cp.create_at_level(session, SPEC, 4, {})
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertEqual(cp.MAX_SUPPORTED_LEVEL, 5)  # Selected5 requires applied4 and earned raw5; skip remains blocked.


class DetachedFutureAsiConsistencyTests(unittest.TestCase):
    def context(self, increase=None):
        increase = {'constitution': 2} if increase is None else increase
        base = copy.deepcopy(SPEC['ability_scores'])
        bonuses = copy.deepcopy(SPEC['background_ability_bonuses'])
        scores = {k: base[k] + bonuses.get(k, 0) + increase.get(k, 0) for k in feat_rules.ABILITIES}
        return dict(scores=scores, base_scores=base, background_bonuses=bonuses,
                    ability_score_method='standard_array', background='Criminal',
                    class_name='Sorcerer', level=4, applied_level=4,
                    asi_choices=[{**copy.deepcopy(RECORD), 'increase': increase}])

    def check(self, context):
        before = copy.deepcopy(context)
        result = cp._check_detached_asi_consistency(**context)
        self.assertEqual(context, before)
        self.assertEqual(set(result), {'consistent', 'reason'})
        return result

    def test_detached_plus_two_and_split_delegate_without_mutation(self):
        for increase in ({'constitution': 2}, {'constitution': 1, 'charisma': 1}):
            context = self.context(increase)
            with patch.object(feat_rules, 'apply_feat_choice', wraps=feat_rules.apply_feat_choice) as apply:
                self.assertTrue(self.check(context)['consistent'])
            apply.assert_called_once()
            self.assertEqual(apply.call_args.args[2]['source'], 'class_asi')

    def test_detached_rejects_missing_invalid_baseline_types_and_double_delta(self):
        variants = []
        for field, value in (('class_name', 'Wizard'), ('level', True), ('applied_level', 3),
                             ('ability_score_method', 'rolled'), ('background', 'unknown'),
                             ('base_scores', {}), ('background_bonuses', {'constitution': 3}),
                             ('asi_choices', []), ('asi_choices', [RECORD, RECORD])):
            context = self.context(); context[field] = value; variants.append(context)
        for field, key, value in (('base_scores', 'strength', True), ('scores', 'constitution', 18),
                                  ('scores', 'wisdom', 13), ('scores', 'strength', False),
                                  ('base_scores', 'strength', 9), ('background_bonuses', 'wisdom', -1)):
            context = self.context(); context[field][key] = value; variants.append(context)
        for record in ({**RECORD, 'class_level': True}, {**RECORD, 'source': 'any'},
                       {**RECORD, 'feat': 'Tough'}, {**RECORD, 'increase': {'constitution': True}},
                       {**RECORD, 'increase': {'constitution': 3}}):
            context = self.context(); context['asi_choices'] = [record]; variants.append(context)
        for context in variants:
            with self.subTest(context=context):
                result = self.check(context)
                self.assertFalse(result['consistent']); self.assertTrue(result['reason'])

    def test_detached_cap_and_creation_constraints_are_not_bypassed(self):
        context = self.context()
        context['ability_score_method'] = 'manual'
        context['base_scores']['constitution'] = 18
        context['scores']['constitution'] = 21
        self.assertFalse(self.check(context)['consistent'])
        context = self.context()
        context['background_bonuses'] = {'wisdom': 2, 'constitution': 1}
        context['scores'] = {k: context['base_scores'][k] + context['background_bonuses'].get(k, 0)
                            + (2 if k == 'constitution' else 0) for k in feat_rules.ABILITIES}
        self.assertFalse(self.check(context)['consistent'])
