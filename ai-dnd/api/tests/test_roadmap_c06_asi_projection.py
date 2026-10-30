"""Preparatory ASI/paid-HP bridge only; actual Sorcerer4 remains blocked.

Literal oracle: PHB C06 PDF41/201, CON14→16 at attained4 adds4 max HP.
The detached projection is not authorization or an applied character level.
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import feat_rules
import xp
from api.tests.test_roadmap_c06_starting_xp import create
from api.tests.test_roadmap_c06 import SPEC


class AsiProjectionTests(unittest.TestCase):
    def project(self, character, target=4, choice=None):
        helper = getattr(cp, '_project_selected_asi_hp', None)
        self.assertTrue(callable(helper), 'preparatory ASI/paid-HP projection is not implemented')
        return helper(character, target, {'increase': {'constitution': 2}} if choice is None else choice)

    def test_real_raw_three_and_xp_first_four_project_same_maximum_without_mutation(self):
        for xp_first, base_gain in ((False, 6), (True, 0)):
            with self.subTest(xp_first=xp_first):
                session = create(3)
                if xp_first:
                    xp.apply_xp(session.character, session.world_state, 1800, 'quest:asi-target-four')
                before = session._capture_runtime_snapshot()
                choice = {'increase': {'constitution': 2}}
                original = copy.deepcopy(choice)
                with patch.object(feat_rules, 'apply_feat_choice', wraps=feat_rules.apply_feat_choice) as feat:
                    result = self.project(session.character, choice=choice)
                self.assertEqual(result['status'], 'projected')
                self.assertEqual((result['unpaid_base_gain'], result['retroactive_max_gain'], result['resulting_maximum']),
                                 (base_gain, 4, 30))
                self.assertEqual(result['feat_delta']['changes'], [{'ability': 'constitution', 'from': 14, 'to': 16}])
                feat.assert_called_once()
                self.assertEqual(feat.call_args.args[0]['level'], 4)
                self.assertEqual(feat.call_args.args[1], 'Ability Score Improvement')
                self.assertEqual(feat.call_args.args[2]['source'], 'class_asi')
                self.assertEqual(session._capture_runtime_snapshot(), before)
                self.assertEqual(choice, original)

    def test_existing_maximum_owner_increases_maximum_without_healing(self):
        session = create(3)
        xp.apply_xp(session.character, session.world_state, 1800, 'quest:maximum-owner')
        session.character['current_hp'] = 10
        session.ensure_death_state()  # Setter may initialize this; not universally side-effect-free.
        result = self.project(session.character)
        before = session._capture_runtime_snapshot()
        with patch.object(session, 'heal_player', side_effect=AssertionError('ASI maximum must not heal')):
            session.set_player_max_hp(result['resulting_maximum'])
        self.assertEqual((session.character['current_hp'], session.character['max_hp']), (10, 30))
        after = session._capture_runtime_snapshot()
        expected = copy.deepcopy(before)
        # Snapshot shape is owned by the session; verify non-character state verbatim.
        self.assertEqual(after.keys(), before.keys())
        for key in before:
            if key != 'character': self.assertEqual(after[key], before[key], key)
        expected['character']['max_hp'] = 30
        self.assertEqual(after, expected)

    def test_rejected_and_unsupported_inputs_preserve_character(self):
        session = create(3)
        for changes, target, choice in (
            ({'class': 'Wizard'}, 4, {'increase': {'constitution': 2}}),
            ({'level': 6}, 4, {'increase': {'constitution': 2}}),
            ({'progression_level': 2}, 4, {'increase': {'constitution': 2}}),
            ({'level': True}, 4, {'increase': {'constitution': 2}}),
            ({}, True, {'increase': {'constitution': 2}}),
            ({'max_hp': True}, 4, {'increase': {'constitution': 2}}),
            ({'constitution': True}, 4, {'increase': {'constitution': 2}}),
            ({'constitution': 19}, 4, {'increase': {'constitution': 2}}),
            ({}, 4, []), ({}, 4, {'increase': {'constitution': True}}),
            ({}, 4, {'increase': {'dexterity': 3}}),  # not a family pattern
            ({}, 4, {'increase': {'constitution': 2}, 'source': 'any'}),
        ):
            with self.subTest(changes=changes, target=target, choice=choice):
                character = {**copy.deepcopy(session.character), **changes}
                before = copy.deepcopy(character)
                result = self.project(character, target, choice)
                self.assertIn(result['status'], ('rejected', 'unsupported'))
                self.assertTrue(result['reason'])
                self.assertEqual(character, before)

    def test_projection_is_not_death_authorization_or_level_four_entitlement(self):
        session = create(3)
        session.character['current_hp'] = 0
        before = session._capture_runtime_snapshot()
        self.assertEqual(self.project(session.character)['status'], 'projected')
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertEqual(cp.preview_level_up(session, 5)['status'], 'blocked')
        self.assertEqual(cp.apply_level_choices(session, self.project(session.character), {})['status'], 'rejected')
        with self.assertRaises(ValueError): cp.create_at_level(session, SPEC, 4, {})
        self.assertEqual(session._capture_runtime_snapshot(), before)
