"""Selected Quickened Magic Missile, not general Metamagic/Font completion.

Literal PHB2024 Sorcerer PDF139–141/Quickened options: maxima2–5,
Quickened cost2, Bonus Action; Long Rest restores. External source verified.
"""
import copy
import unittest

import action_economy
import character_progression as cp
import game
import spell_scope
from api.tests.test_roadmap_c06_starting_xp import create
from api.tests.test_roadmap_c06_creation45 import steps
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_level3 import choices
from api.tests.test_spell_scope import caster
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignValidationError, CampaignCorruptError
from combat_lifecycle import CombatRequestError
from unittest.mock import patch
import sorcery_points
import xp


def created(level):
    if level < 4:
        return create(level)
    s = game.create_session(seed=42)
    cp.create_at_level(s, copy.deepcopy(SPEC), level, steps(level))
    return s


def combat(level=2):
    source = created(level)
    s, enemy = caster()
    s.character.clear(); s.character.update(copy.deepcopy(source.character))
    s.world_state['spellcasting_v1'] = copy.deepcopy(source.world_state['spellcasting_v1'])
    if 'sorcery_points_v1' in source.world_state:
        s.world_state['sorcery_points_v1'] = copy.deepcopy(source.world_state['sorcery_points_v1'])
    if 'xp_awarded_event_ids' in source.world_state:
        s.world_state['xp_awarded_event_ids'] = copy.deepcopy(source.world_state['xp_awarded_event_ids'])
    s._persisted_engine_format = getattr(source, '_persisted_engine_format', 4)
    return s, enemy


class QuickenedTests(unittest.TestCase):
    def test_real_creation_initializes_literal_applied_point_maxima(self):
        self.assertNotIn('sorcery_points_v1', created(1).world_state)
        for level in (2, 3, 4, 5):
            with self.subTest(level=level):
                s = created(level)
                self.assertEqual(s.world_state.get('sorcery_points_v1'), {'version': 1, 'remaining': level})
                self.assertEqual(s.world_state.get('xp_awarded_event_ids', []), [])

    def test_real_selected_cast_spends_bonus_points_and_slot_not_action(self):
        s, enemy = combat()
        self.assertEqual(s.world_state.get('sorcery_points_v1'), {'version': 1, 'remaining': 2})
        result = spell_scope.cast(s, 'Magic Missile', enemy['id'], metamagic='quickened_spell')
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'], 0)
        self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 2})
        budget = action_economy.ensure(s)['player']
        self.assertTrue(budget['bonus_action_spent'])
        self.assertFalse(budget['base_action_spent'])
        self.assertEqual(budget['bonus_grants'], [])
        self.assertGreater(result['damage'], 0)
        action_economy.dash(s)
        self.assertTrue(budget['base_action_spent'])

    def test_present_advancement_preserves_spent_points_and_legacy_absence(self):
        s = created(2)
        self.assertIn('sorcery_points_v1', s.world_state)
        s.world_state['sorcery_points_v1']['remaining'] = 0
        self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 3), choices())['status'], 'applied')
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'], 1)
        legacy = created(2); legacy.world_state.pop('sorcery_points_v1', None)
        self.assertEqual(cp.apply_level_choices(legacy, cp.preview_level_up(legacy, 3), choices())['status'], 'applied')
        self.assertNotIn('sorcery_points_v1', legacy.world_state)

    def test_completed_long_rest_adopts_legacy_pool_but_short_rest_does_not(self):
        s, _ = combat(3); s.commit_location_change('tavern'); s.end_combat('rest_fixture'); s.world_state.pop('sorcery_points_v1', None)
        s.resolve_species_trait_action('short_rest')
        self.assertNotIn('sorcery_points_v1', s.world_state)
        s.resolve_species_trait_action('long_rest')
        self.assertEqual(s.world_state.get('sorcery_points_v1'), {'version': 1, 'remaining': 3})

    def test_saved_malformed_pool_rejected_without_loading_mutation(self):
        s = created(2)
        s.world_state['sorcery_points_v1'] = {'version': 1, 'remaining': True}
        with self.assertRaises(CampaignValidationError):
            serialize_campaign_payload(s)

    def test_both_spell_orders_reject_with_real_additional_action_available(self):
        for quick_first in (False, True):
            s, enemy = combat(5)
            action_economy.grant(s, 'player', 'test_extra_action', ['magic'])
            spell_scope.cast(s, 'Magic Missile', enemy['id'], metamagic='quickened_spell' if quick_first else None)
            before = s._capture_runtime_snapshot()
            with self.assertRaises(CombatRequestError) as caught:
                spell_scope.cast(s, 'Magic Missile', enemy['id'], metamagic=None if quick_first else 'quickened_spell')
            self.assertEqual(caught.exception.code, 'spell_slot_turn_limit')
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_cantrip_after_quickened_and_existing_action_spent_before_quickened(self):
        s, enemy = combat(3)
        spell_scope.cast(s, 'Magic Missile', enemy['id'], metamagic='quickened_spell')
        spell_scope.cast(s, 'Fire Bolt', enemy['id'])
        self.assertTrue(action_economy.ensure(s)['player']['base_action_spent'])
        s, enemy = combat(3)
        action_economy.dash(s)
        self.assertTrue(sorcery_points.quickened_availability(s)['available'])
        spell_scope.cast(s, 'Magic Missile', enemy['id'], metamagic='quickened_spell')
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'], 1)

    def test_upcast_darts_and_full_roundtrip_without_delta_reapplication(self):
        for level, slot, darts in ((2,1,3),(3,2,4),(5,3,5)):
            s, enemy = combat(level)
            result = spell_scope.cast(s, 'Magic Missile', enemy['id'], slot, metamagic='quickened_spell')
            self.assertEqual(len(result['darts']), darts)
            s._validate_save_payload(s.serialize_game_state())
            original = serialize_campaign_payload(s)
            fresh = game.create_session(seed=99); restore_campaign_session(fresh, original)
            self.assertEqual(serialize_campaign_payload(fresh)['engine_save'], original['engine_save'])
            self.assertEqual(fresh.world_state['sorcery_points_v1']['remaining'], level-2)
            self.assertTrue(action_economy.ensure(fresh)['player']['bonus_action_spent'])
            self.assertEqual(action_economy.ensure(fresh)['player']['bonus_grants'], [])

    def test_rejections_preserve_complete_snapshot_rng_and_no_grant_leak(self):
        for mode in ('absent','empty','unselected','bonus_spent','target','components','dead','slot','other_spell','unknown_mode','boolean_mode'):
            s, enemy = combat(3); spell = 'Magic Missile'; target = enemy['id']; option = 'quickened_spell'
            if mode=='absent': s.world_state.pop('sorcery_points_v1')
            if mode=='empty': s.world_state['sorcery_points_v1']['remaining']=1
            if mode=='unselected': s.character['metamagic']=['Careful Spell','Twinned Spell']
            if mode=='bonus_spent': action_economy.ensure(s)['player']['bonus_action_spent']=True
            if mode=='target': target='unknown'
            if mode=='components': s.world_state['equipment']={'main_hand':'spear','off_hand':'dagger'}
            if mode=='dead': s.character['current_hp']=0
            if mode=='slot': s.world_state['spellcasting_v1']['slots']['1']=0
            if mode=='other_spell': spell='Fire Bolt'
            if mode=='unknown_mode': option='twinned_spell'
            if mode=='boolean_mode': option=True
            before=s._capture_runtime_snapshot()
            with self.subTest(mode=mode), self.assertRaises((ValueError, CombatRequestError)):
                spell_scope.cast(s, spell, target, metamagic=option)
            self.assertEqual(s._capture_runtime_snapshot(),before,mode)

    def test_failed_damage_and_outer_step_rollback_restore_all_resources(self):
        s, enemy=combat(3); before=s._capture_runtime_snapshot()
        with patch.object(s,'apply_npc_damage',side_effect=RuntimeError('synthetic late damage fault')):
            with self.assertRaises(RuntimeError): spell_scope.cast(s,'Magic Missile',enemy['id'],metamagic='quickened_spell')
        self.assertEqual(s._capture_runtime_snapshot(),before)
        with self.assertRaises(CombatRequestError):
            action_economy.execute(s, {'steps':[{'kind':'magic','ability':'Magic Missile','target_id':enemy['id'],'metamagic':'quickened_spell'}, {'kind':'move','distance_ft':99999}]})
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_existing_bonus_grant_is_not_consumed_by_feature(self):
        s, enemy=combat(3)
        action_economy.grant(s,'player','test_other_bonus',['magic'],resource='bonus')
        before=copy.deepcopy(action_economy.ensure(s)['player']['bonus_grants'])
        spell_scope.cast(s,'Magic Missile',enemy['id'],metamagic='quickened_spell')
        self.assertEqual(action_economy.ensure(s)['player']['bonus_grants'],before)

    def test_raw_xp_ahead_preserves_applied_pool_and_recreation_clears(self):
        s=created(3); s.world_state['sorcery_points_v1']['remaining']=1
        s._receive_xp_award(xp.apply_xp,s.character,s.world_state,5600,'quest:quickened-test')
        self.assertEqual((s.character['level'],s.character['progression_level']),(5,3))
        self.assertEqual(sorcery_points.projection(s),{'current':1,'max':3})
        cp.create_at_level(s,copy.deepcopy(SPEC),1,{})
        self.assertNotIn('sorcery_points_v1',s.world_state)

    def test_strict_saved_record_and_legacy_versions(self):
        for bad in (None,{}, {'version':True,'remaining':2},{'version':1,'remaining':True},{'version':1,'remaining':-1},{'version':1,'remaining':3},{'version':1,'remaining':2,'max':2}):
            s=created(2); s.world_state['sorcery_points_v1']=bad
            with self.subTest(bad=bad), self.assertRaises(CampaignValidationError): serialize_campaign_payload(s)
        for version in (1,2,3):
            s=created(2); s._persisted_engine_format=version
            with self.assertRaises(CampaignValidationError): serialize_campaign_payload(s)
            s.world_state.pop('sorcery_points_v1')
            before=copy.deepcopy(s.world_state)
            sorcery_points.restore(s)
            self.assertEqual(s.world_state,before)

    def test_absent_legacy_read_preview_and_failed_cast_never_adopt(self):
        s, enemy=combat(3); s.world_state.pop('sorcery_points_v1'); s.commit_location_change('tavern')
        p=serialize_campaign_payload(s)
        fresh=game.create_session(seed=99); restore_campaign_session(fresh,p)
        before=fresh._capture_runtime_snapshot()
        self.assertIsNone(sorcery_points.projection(fresh))
        self.assertIsNone(sorcery_points.quickened_availability(fresh))
        cp.preview_level_up(fresh,4)
        with self.assertRaises(CombatRequestError): spell_scope.cast(fresh,'Magic Missile',enemy['id'],metamagic='quickened_spell')
        self.assertEqual(fresh._capture_runtime_snapshot(),before)

    def test_slot_restore_preserves_same_turn_lock(self):
        s, enemy=combat(3)
        spell_scope.cast(s,'Magic Missile',enemy['id'])
        marker=copy.deepcopy(s.world_state['spellcasting_v1']['slot_turn'])
        spell_scope.restore_slots(s)
        self.assertEqual(s.world_state['spellcasting_v1']['slot_turn'],marker)
        with self.assertRaises(CombatRequestError) as error: spell_scope.cast(s,'Magic Missile',enemy['id'],metamagic='quickened_spell')
        self.assertEqual(error.exception.code,'spell_slot_turn_limit')

    def test_malformed_pool_rest_rejects_before_time_healing_or_slots_change(self):
        s, _=combat(3); s.commit_location_change('tavern'); s.end_combat('rest_fixture')
        s.world_state['sorcery_points_v1']['remaining']=-1
        s.character['current_hp']=1
        before=s._capture_runtime_snapshot()
        with self.assertRaises(ValueError): s.resolve_species_trait_action('long_rest')
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_malformed_selected_option_cannot_authorize_direct_cast(self):
        s, enemy=combat(3); s.character['metamagic']='Quickened Spell'
        before=s._capture_runtime_snapshot()
        with self.assertRaises((ValueError, CombatRequestError)):
            spell_scope.cast(s,'Magic Missile',enemy['id'],metamagic='quickened_spell')
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_interrupted_long_rest_does_not_adopt_or_refill(self):
        for absent in (False,True):
            s, _=combat(3); s.commit_location_change('tavern'); s.end_combat('rest_fixture')
            if absent: s.world_state.pop('sorcery_points_v1')
            else: s.world_state['sorcery_points_v1']['remaining']=0
            before=copy.deepcopy(s.world_state.get('sorcery_points_v1'))
            with patch.object(game,'advance_campaign_time',return_value={'interrupted':True,'elapsed_seconds':1}):
                result=s.resolve_species_trait_action('long_rest')
            self.assertFalse(result['effects']['rest_completed'])
            self.assertEqual(s.world_state.get('sorcery_points_v1'),before)

    def test_present_spent_pool_preserved_through_actual_four_five_queue(self):
        from api.tests.test_roadmap_c06_level4_con import PICK
        from api.tests.test_roadmap_c06_level5 import FIVE
        for absent in (False, True):
            s=created(3)
            if absent: s.world_state.pop('sorcery_points_v1')
            else: s.world_state['sorcery_points_v1']['remaining']=1
            s._receive_xp_award(xp.apply_xp,s.character,s.world_state,5600,'quest:queue-quickened')
            for target,picks,remaining in ((4,PICK,2),(5,FIVE,3)):
                self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,target),picks)['status'],'applied')
                if absent: self.assertNotIn('sorcery_points_v1',s.world_state)
                else: self.assertEqual(s.world_state['sorcery_points_v1'],{'version':1,'remaining':remaining})
                fresh=game.create_session(seed=99); restore_campaign_session(fresh,serialize_campaign_payload(s));s=fresh
