"""Numeric level HP is not recovery: canonical zero-HP regression boundaries.

Choice application below is a core boundary, not a claim of a live choice HTTP
route. Dynamic settlement exercises a production reward caller, not a forced
combat victory. Positive-current compatibility and the existing XP cap remain.
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import game
import xp
import adventure.evidence as evidence
import adventure.play as play
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_starting_xp import create
from api.tests.test_roadmap_c06_level3 import TWO, choices
from api.tests.test_roadmap_c06_barbarian import barbarian
from api.tests.test_adventure_session import _session, _active_missing, _finish_to_cell
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session


def zero_state(session, state):
    session.ensure_campaign_clock()
    session.ensure_death_state()['mode'] = 'PERMADEATH'
    session._apply_player_damage(session.character['current_hp'], took_damage=True)
    if state == 'stable':
        session.stabilize_player()
    elif state == 'dead':
        session._apply_player_damage(session.character['max_hp'], took_damage=True)
    session.ensure_death_state()
    return (copy.deepcopy(session.world_state['death_state']),
            session.world_state['player_combat_status'], session.rng.getstate())


class ZeroHpProgressionTests(unittest.TestCase):
    def assert_zero_preserved(self, session, before):
        self.assertEqual(session.character['current_hp'], 0)
        self.assertEqual(session.world_state['death_state'], before[0])
        self.assertEqual(session.world_state['player_combat_status'], before[1])
        self.assertEqual(session.rng.getstate(), before[2])
        self.assertEqual(session.ensure_death_state(), before[0])

    def test_xp_numeric_gain_preserves_canonical_zero_states(self):
        for level, amount in ((1, 300), (3, 1800)):
            for state in ('unconscious', 'stable', 'dead'):
                with self.subTest(level=level, state=state):
                    session = create(level)
                    before = zero_state(session, state)
                    maximum = session.character['max_hp']
                    with patch.object(session, 'heal_player', side_effect=AssertionError('XP is not healing')):
                        result = xp.apply_xp(session.character, session.world_state, amount, 'quest:zero-level')
                    self.assertEqual(result['new_level'], level + 1)
                    self.assertEqual(result['hit_points_gained'], 6)
                    self.assertEqual(session.character['max_hp'], maximum + 6)
                    self.assert_zero_preserved(session, before)
                    snapshot = session._capture_runtime_snapshot()
                    self.assertIsNone(xp.apply_xp(session.character, session.world_state, amount, 'quest:zero-level'))
                    self.assertEqual(session._capture_runtime_snapshot(), snapshot)

    def test_unpaid_core_choices_preserve_canonical_zero_states(self):
        for kind in ('sorcerer2', 'sorcerer3', 'barbarian2'):
            for state in ('unconscious', 'stable', 'dead'):
                with self.subTest(kind=kind, state=state):
                    session = barbarian() if kind == 'barbarian2' else create(2 if kind == 'sorcerer3' else 1)
                    target = 3 if kind == 'sorcerer3' else 2
                    picks = {} if kind == 'barbarian2' else choices() if target == 3 else copy.deepcopy(TWO)
                    before = zero_state(session, state)
                    preview = cp.preview_level_up(session, target)
                    self.assertEqual(preview['status'], 'ready')
                    self.assertFalse(preview['hit_points']['already_applied'])
                    maximum = session.character['max_hp']
                    with patch.object(session, 'heal_player', side_effect=AssertionError('Choices are not healing')):
                        result = cp.apply_level_choices(session, preview, picks)
                    self.assertEqual(result['status'], 'applied', result)
                    self.assertEqual(session.character['max_hp'], maximum + preview['hit_points']['gain'])
                    self.assert_zero_preserved(session, before)

    def test_pending_dynamic_reward_settlement_preserves_zero(self):
        for state in ('unconscious', 'stable', 'dead'):
            with self.subTest(state=state):
                session = _session()
                cp.create_at_level(session, copy.deepcopy(SPEC), 1, {})
                quest = _active_missing(session)
                _finish_to_cell(session, quest)
                evidence.fail_objective(quest, 'threat')
                xp.apply_xp(session.character, session.world_state, 260, 'quest:near-boundary')
                previous = copy.deepcopy(session.world_state)
                session.world_state['flags']['turn_index'] += 1
                # Actual evidence owner completes the quest; defer settlement,
                # rather than faking a completed row or unconscious self-action.
                evidence.apply_dynamic_evidence(session.world_state, previous, {
                    'action': 'skill_check', 'success': True, 'skill': 'persuasion',
                    'target': 'npc.missing', 'action_id': 'check:rescue-zero-regression',
                })
                self.assertEqual(quest['status'], 'COMPLETED')
                self.assertEqual(quest['outcome'], 'partial_success')
                self.assertIsNone(quest['reward_application_id'])
                before = zero_state(session, state)
                play.settle_session(session)
                self.assertEqual((session.character['xp'], session.character['level']), (300, 2))
                self.assertEqual(quest['reward_application_id'], 'quest:adv.session-missing:partial_success')
                self.assert_zero_preserved(session, before)
                snapshot = session._capture_runtime_snapshot()
                play.settle_session(session)
                self.assertEqual(session._capture_runtime_snapshot(), snapshot)

    def test_positive_current_compatibility_paid_choices_and_cap(self):
        session = create(1)
        session._apply_player_damage(3, took_damage=True)
        self.assertEqual(session.character['current_hp'], 5)
        xp.apply_xp(session.character, session.world_state, 300, 'quest:positive')
        self.assertEqual((session.character['current_hp'], session.character['max_hp']), (11, 14))
        before = zero_state(session, 'stable')
        preview = cp.preview_level_up(session, 2)
        self.assertTrue(preview['hit_points']['already_applied'])
        self.assertEqual(cp.apply_level_choices(session, preview, copy.deepcopy(TWO))['status'], 'applied')
        self.assert_zero_preserved(session, before)
        xp.apply_xp(session.character, session.world_state, 10000, 'quest:cap')
        self.assertEqual(session.character['level'], 5)  # Numeric cap expanded; zero/death state remains unchanged.
        self.assert_zero_preserved(session, before)

    def test_real_healing_remains_recovery_owner(self):
        for state in ('unconscious', 'stable', 'dead'):
            with self.subTest(state=state):
                session = create(1)
                before = zero_state(session, state)
                if state == 'dead':
                    with self.assertRaises(ValueError):
                        session.heal_player(1)
                    self.assert_zero_preserved(session, before)
                else:
                    self.assertEqual(session.heal_player(1), 1)
                    self.assertEqual(session.world_state['player_combat_status'], 'active')
                    death = session.ensure_death_state()
                    self.assertFalse(death['stable'])
                    self.assertIsNone(death['recovery'])
                    self.assertEqual((death['successes'], death['failures']), (0, 0))

    def test_advanced_zero_states_roundtrip_then_real_healing(self):
        """Postimplementation interaction check, not additional pre-fix RED evidence."""
        for route in ('xp2', 'xp4', 'sorcerer2', 'sorcerer3', 'barbarian2'):
            for state in ('unconscious', 'stable', 'dead'):
                with self.subTest(route=route, state=state):
                    level = 3 if route == 'xp4' else 2 if route == 'sorcerer3' else 1
                    session = barbarian() if route == 'barbarian2' else create(level)
                    before = zero_state(session, state)
                    maximum = session.character['max_hp']
                    if route.startswith('xp'):
                        result = xp.apply_xp(session.character, session.world_state,
                                             1800 if level == 3 else 300, 'quest:roundtrip-zero')
                        gain = result['hit_points_gained']
                    else:
                        preview = cp.preview_level_up(session, level + 1)
                        picks = {} if route == 'barbarian2' else choices() if level == 2 else copy.deepcopy(TWO)
                        self.assertEqual(cp.apply_level_choices(session, preview, picks)['status'], 'applied')
                        gain = preview['hit_points']['gain']
                    self.assertEqual(gain, 9 if route == 'barbarian2' else 6)
                    self.assert_zero_preserved(session, before)
                    payload = serialize_campaign_payload(session)
                    self.assert_zero_preserved(session, before)
                    restored = game.create_session(seed=987)
                    restore_campaign_session(restored, copy.deepcopy(payload))
                    self.assert_zero_preserved(restored, before)
                    self.assertEqual(restored.character['max_hp'], maximum + gain)
                    for field in ('level', 'progression_level', 'xp'):
                        self.assertEqual(restored.character.get(field), session.character.get(field))
                    self.assertEqual(restored.world_state.get('xp_awarded_event_ids'),
                                     session.world_state.get('xp_awarded_event_ids'))
                    if state == 'dead':
                        snapshot = restored._capture_runtime_snapshot()
                        with self.assertRaises(ValueError):
                            restored.heal_player(1)
                        self.assertEqual(restored._capture_runtime_snapshot(), snapshot)
                    else:
                        self.assertEqual(restored.heal_player(1), 1)
                        self.assertEqual(restored.character['current_hp'], 1)
                        self.assertEqual(restored.world_state['player_combat_status'], 'active')
                        death = restored.ensure_death_state()
                        self.assertFalse(death['stable'])
                        for field in ('recovery', 'noncombat_next_save_at', 'noncombat_episode_id'):
                            self.assertIsNone(death[field])
                        self.assertEqual((death['successes'], death['failures']), (0, 0))
                    self.assertEqual(restored.character['max_hp'], maximum + gain)
                    self.assertEqual(restored.rng.getstate(), before[2])
