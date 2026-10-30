"""Earned selected Berserker 4->5 (Extra Attack, Fast Movement): literal PHB numeric oracles, state and persistence.

Values only (Barbarian features table, PHB 2024 PDF 51): level 5 = PB +3, 3 Rages, Rage Damage +2, Weapon Mastery 3,
features Extra Attack and Fast Movement. Effects are tested in test_roadmap_c10_extra_attack / _fast_movement.
Synthetic faults here are unit boundaries, not native campaign evidence.
"""
import copy
import unittest

import game
import xp
import hit_dice
import character_progression as cp
import barbarian_rage as rage
from api.dnd_2024_rules import proficiency_bonus_for_level
from api.tests.test_roadmap_c06_barbarian_level4 import selected_three, advance as advance_four
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError, CampaignValidationError


def pending_five(test, **kwargs):
    """Applied 4, XP-earned numeric level 5 (class choices of level 5 not applied yet)."""
    session = selected_three(test, raw=3, **kwargs)
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 1800, 'quest:b5-four')
    advance_four(test, session)
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 3800, 'quest:b5-five')
    test.assertEqual((session.character['level'], session.character['progression_level'], session.character['xp']), (5, 4, 6500))
    return session


def apply_five(test, session):
    preview = cp.preview_level_up(session, 5)
    test.assertEqual(preview['status'], 'ready', preview)
    result = cp.apply_level_choices(session, preview, {})
    test.assertEqual(result['status'], 'applied', result)
    return result


def applied_five(test, **kwargs):
    session = pending_five(test, **kwargs)
    apply_five(test, session)
    return session


def roundtrip(session, seed=19):
    payload = serialize_campaign_payload(session)
    fresh = game.create_session(seed=seed)
    restore_campaign_session(fresh, payload)
    return fresh, payload


class BarbarianFiveTests(unittest.TestCase):
    def test_source_row_five_and_pb_leaf(self):
        row = cp.table('Barbarian')['levels'].get('5')
        self.assertEqual(row, {'proficiency_bonus': 3, 'features': ['Extra Attack', 'Fast Movement'],
                               'rages': 3, 'rage_damage': 2, 'weapon_mastery': 3})
        self.assertEqual(row['proficiency_bonus'], proficiency_bonus_for_level(5))
        self.assertNotIn('6', cp.table('Barbarian')['levels'])  # Subclass level-6 features stay out of scope.

    def test_xp_crossing_gives_pb_and_save_totals_but_no_level_five_features(self):
        s = selected_three(self, raw=3)
        s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 1800, 'quest:b5-four')
        advance_four(self, s)
        before = copy.deepcopy(s.character)
        gain = xp.hit_point_gain(before)
        s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 3800, 'quest:b5-five')
        c = s.character
        self.assertEqual((c['level'], c['progression_level'], c['proficiency_bonus']), (5, 4, 3))
        self.assertEqual(c['max_hp'], before['max_hp'] + gain)
        self.assertEqual(c['saving_throw_mods']['strength'], before['saving_throw_mods']['strength'] + 1)
        self.assertEqual(c['saving_throw_mods']['constitution'], before['saving_throw_mods']['constitution'] + 1)
        self.assertEqual(c['saving_throw_mods']['dexterity'], before['saving_throw_mods']['dexterity'])
        self.assertEqual(s._persisted_engine_format, 6)
        # Applied level (not XP level) still gates features, Hit Dice and Rage capacity.
        self.assertEqual(hit_dice.total(c), 4)
        self.assertEqual(rage.capacity(c), 3)

    def test_preview_is_pure_and_literal(self):
        s = pending_five(self)
        before = s._capture_runtime_snapshot()
        p = cp.preview_level_up(s, 5)
        self.assertEqual(p['status'], 'ready', p)
        self.assertEqual((p['class_name'], p['from_level'], p['to_level']), ('Barbarian', 4, 5))
        self.assertEqual(p['features'], ['Extra Attack', 'Fast Movement'])
        self.assertEqual(p['choices_required'], {})
        self.assertIsNone(p['capacity'])
        self.assertEqual(p['hit_points'], {'gain': 0, 'already_applied': True})
        self.assertNotIn('supported_asi_choices', p)
        text = ' '.join(p['effects_supported'])
        self.assertIn('Extra Attack', text)
        self.assertIn('Fast Movement', text)
        self.assertIn('Weapon Mastery', ' '.join(p['effects_pending']))
        self.assertFalse([item for item in p['effects_pending'] if item.startswith(('Extra Attack', 'Fast Movement: +10'))])
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_preview_blocks_without_earned_numeric_five_or_applied_four(self):
        s = selected_three(self, raw=3)
        s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 1800, 'quest:b5-four')
        advance_four(self, s)
        self.assertEqual(cp.preview_level_up(s, 5)['reason'], 'previous_level_four_choices_and_numeric_five_required')
        ahead = selected_three(self, raw=5)  # XP-ahead numeric 5, level-4 choices not applied
        self.assertEqual((ahead.character['level'], ahead.character['progression_level']), (5, 3))
        self.assertEqual(cp.preview_level_up(ahead, 5)['reason'], 'previous_level_four_choices_and_numeric_five_required')
        self.assertEqual(cp.preview_level_up(ahead, 6)['status'], 'blocked')

    def test_preview_blocks_without_retained_rage_capability_or_with_caster_state(self):
        changes = [lambda s: s.world_state.pop('rage_v1'), lambda s: s.world_state.pop('worn_armor_v1'),
                   lambda s: s.world_state.update(spellcasting_v1=None),
                   lambda s: s.world_state.update(sorcery_points_v1={'version': 1, 'remaining': 0}),
                   lambda s: s.character.update(metamagic=['Quickened Spell']),
                   lambda s: s.character.pop('subclass_id'),
                   lambda s: s.character.pop('asi_choices'),
                   lambda s: s.character.pop('primal_knowledge_choice')]
        for change in changes:
            s = pending_five(self); change(s); before = s._capture_runtime_snapshot()
            preview = cp.preview_level_up(s, 5)
            self.assertEqual(preview['status'], 'blocked', preview)
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_apply_sets_level_features_without_hp_rage_or_slot_changes(self):
        s = pending_five(self)
        s.world_state['rage_v1']['remaining'] = 1  # spent uses are not refilled by a level
        old_character, old_world = copy.deepcopy(s.character), copy.deepcopy(s.world_state)
        result = apply_five(self, s)
        c = s.character
        self.assertEqual(result['changes'], [{'kind': 'level', 'from': 4, 'to': 5}])
        self.assertIn('Weapon Mastery', ' '.join(result['effects_pending']))
        self.assertEqual((c['level'], c['progression_level'], c['proficiency_bonus']), (5, 5, 3))
        for key in set(old_character) - {'progression_level'}:
            self.assertEqual(c[key], old_character[key], key)
        self.assertEqual(s.world_state, old_world)
        self.assertEqual(s.world_state['rage_v1']['remaining'], 1)
        self.assertEqual(rage.capacity(c), 3)
        self.assertEqual(hit_dice.total(c), 5)
        self.assertEqual(hit_dice.spent(c), 0)
        self.assertNotIn('spellcasting_v1', s.world_state)
        self.assertNotIn('sorcery_points_v1', s.world_state)
        self.assertFalse(c.get('metamagic'))
        self.assertEqual(c['primal_knowledge_choice']['class_level'], 3)
        self.assertEqual(c['asi_choices'][0]['class_level'], 4)

    def test_apply_is_exactly_once_and_rejects_any_choice(self):
        s = pending_five(self)
        for choices in ({'asi': {'feat': 'Ability Score Improvement', 'increase': {'strength': 2}}}, {'prepared_spells': ['Fog Cloud']},
                        {'subclass_id': 'berserker'}, None, [], 'x'):
            before = s._capture_runtime_snapshot()
            preview = cp.preview_level_up(s, 5)
            self.assertEqual(cp.apply_level_choices(s, preview, choices)['status'], 'rejected', choices)
            self.assertEqual(s._capture_runtime_snapshot(), before)
        preview = cp.preview_level_up(s, 5)
        self.assertEqual(cp.apply_level_choices(s, preview, {})['status'], 'applied')
        before = s._capture_runtime_snapshot()
        again = cp.apply_level_choices(s, preview, {})
        self.assertEqual((again['status'], again['reason']), ('rejected', 'already_applied'))
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(cp.preview_level_up(s, 5)['reason'], 'target_not_above_applied_level')
        self.assertEqual(cp.preview_level_up(s, 6)['reason'], 'progression_level_not_supported')

    def test_late_fault_rolls_back_atomically(self):
        s = pending_five(self); before = s._capture_runtime_snapshot()
        preview = cp.preview_level_up(s, 5)
        from unittest.mock import patch
        with patch('game._validate_save_payload', side_effect=ValueError('synthetic admission failure')):
            result = cp.apply_level_choices(s, preview, {})
        self.assertEqual((result['status'], result['reason']), ('rejected', 'resulting_state_invalid'))
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 5), {})['status'], 'applied')

    def test_pending_and_applied_five_survive_repeated_fresh_restore(self):
        for build in (pending_five, applied_five):
            s = build(self)
            for _ in range(2):
                fresh, payload = roundtrip(s)
                self.assertEqual(serialize_campaign_payload(fresh), payload)
                self.assertEqual(fresh.character['progression_level'], s.character['progression_level'])
                self.assertEqual(fresh._persisted_engine_format, 6)
                s = fresh
        self.assertEqual(s.character['progression_level'], 5)
        self.assertEqual(rage.capacity(s.character), 3)

    def test_restore_rejects_forged_level_five_state_without_changing_session(self):
        forged = {
            'applied5_without_rage': lambda p: p['engine_save']['world_state'].pop('rage_v1'),
            'applied5_without_proof': lambda p: p['engine_save']['world_state'].pop('worn_armor_v1'),
            'applied5_without_subclass': lambda p: p['engine_save']['player'].pop('subclass_id'),
            'applied5_without_asi': lambda p: p['engine_save']['player'].pop('asi_choices'),
            'applied5_without_primal': lambda p: p['engine_save']['player'].pop('primal_knowledge_choice'),
            'applied5_with_pb2': lambda p: p['engine_save']['player'].update(proficiency_bonus=2),
            'applied5_with_caster_state': lambda p: p['engine_save']['world_state'].update(sorcery_points_v1={'version': 1, 'remaining': 0}),
            'rage_over_capacity': lambda p: p['engine_save']['world_state']['rage_v1'].update(remaining=4),
        }
        for name, change in forged.items():
            s = applied_five(self); payload = serialize_campaign_payload(s)
            self.assertIn('rage_v1', payload['engine_save']['world_state'], name)
            change(payload)
            fresh = game.create_session(seed=19); before = fresh._capture_runtime_snapshot()
            with self.assertRaises((CampaignCorruptError, CampaignValidationError), msg=name):
                restore_campaign_session(fresh, payload)
            self.assertEqual(fresh._capture_runtime_snapshot(), before, name)

    def test_restore_rejects_applied_five_below_numeric_five_and_applied_six(self):
        s = applied_five(self); payload = serialize_campaign_payload(s)
        payload['engine_save']['player'].update(level=6, progression_level=6)
        fresh = game.create_session(seed=19)
        with self.assertRaises((CampaignCorruptError, CampaignValidationError)):
            restore_campaign_session(fresh, payload)
        s = pending_five(self); payload = serialize_campaign_payload(s)
        payload['engine_save']['player'].update(progression_level=5, level=4, xp=2700)
        with self.assertRaises((CampaignCorruptError, CampaignValidationError)):
            restore_campaign_session(game.create_session(seed=19), payload)

    def test_species_background_hp_is_not_paid_twice(self):
        for species, background in (('Human', 'Criminal'), ('Dwarf', 'Criminal'), ('Human', 'Farmer')):
            s = pending_five(self, species=species, background=background)
            maximum, current = s.character['max_hp'], s.character['current_hp']
            apply_five(self, s)
            self.assertEqual((s.character['max_hp'], s.character['current_hp']), (maximum, current), (species, background))

    def test_xp_ahead_numeric_five_can_apply_four_then_five_without_double_hp(self):
        s = selected_three(self, raw=5)
        maximum = s.character['max_hp']
        advance_four(self, s)
        self.assertEqual(s.character['max_hp'], maximum + 5)  # ASI maximum-only: +1 CON modifier x numeric level 5; base Hit Points were paid by XP
        maximum = s.character['max_hp']
        apply_five(self, s)
        self.assertEqual((s.character['level'], s.character['progression_level'], s.character['max_hp']), (5, 5, maximum))

    def test_disclosure_is_honest_for_level_five(self):
        supported = ' '.join(cp.progression_disclosure('Barbarian', 5)['supported'])
        pending = ' '.join(cp.progression_effects_pending('Barbarian', 5))
        self.assertIn('Extra Attack', supported)
        self.assertIn('Fast Movement', supported)
        self.assertIn('1–5', supported)  # Rage scope text follows the applied level
        self.assertIn('Weapon Mastery', pending)
        self.assertIn('higher-level features remain unsupported', pending)
        for level in (3, 4):
            self.assertNotIn('Extra Attack', ' '.join(cp.progression_disclosure('Barbarian', level)['supported']))
        # Superseded: the detached creation catalog publishes Barbarian start 1-5 now (test_roadmap_c06_barbarian_creation45).
        self.assertEqual(cp.barbarian_starting_creation_options()['supported_starting_levels'], [1, 2, 3, 4, 5])


if __name__ == '__main__':
    unittest.main()
