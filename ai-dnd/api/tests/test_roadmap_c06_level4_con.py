"""Actual selected CON+2 progression; PHB PDF139/41/201 literal oracles.

This is partial engine support, not a PHB restriction on other ASI choices.
"""
import copy
import unittest
from unittest.mock import patch
import game
import xp
import character_progression as cp
from api.tests.test_roadmap_c06_starting_xp import create
from api.tests.test_roadmap_c06 import SPEC
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session

PICK = {'prepared_spells': ['Mage Armor'], 'cantrips': ['Shocking Grasp'],
        'asi': {'feat': 'Ability Score Improvement', 'increase': {'constitution': 2}}}
RECORD = [{'class_level': 4, **PICK['asi']}]


class LevelFourConTests(unittest.TestCase):
    def advance(self, s):
        preview = cp.preview_level_up(s, 4)
        self.assertEqual(preview['status'], 'ready', preview)
        result = cp.apply_level_choices(s, preview, copy.deepcopy(PICK))
        self.assertEqual(result['status'], 'applied', result)
        return result

    def test_actual_direct_and_xp_first_spent_resources_and_no_replay(self):
        for first in (False, True):
            s = create(3)
            if first: xp.apply_xp(s.character, s.world_state, 1800, 'quest:four')
            s.character['current_hp'] = 10
            s.world_state['spellcasting_v1']['slots'] = {'1': 2, '2': 1}
            s.character['spell_slots_remaining'] = {'1': 2, '2': 1}
            before = copy.deepcopy(s.character)
            self.advance(s)
            self.assertEqual((s.character['level'], s.character['progression_level'], s.character['constitution']), (4, 4, 16))
            self.assertEqual((s.character['current_hp'], s.character['max_hp']), (10 if first else 16, 30))
            self.assertEqual(s.character['xp'], 2700 if first else 900)
            self.assertEqual(s.character['asi_choices'], RECORD)
            self.assertEqual(s.character['constitution_mod'], 3)
            self.assertEqual(s.character['modifiers']['constitution'], 3)
            self.assertEqual(s.character['final_ability_scores']['constitution'], 16)
            self.assertEqual(s.character['saving_throw_mods']['constitution'], 5)
            self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 2, '2': 2})
            self.assertEqual((len(s.character['cantrips']), len(s.character['spells'])), (5, 7))
            for field in ('base_ability_scores', 'background_ability_bonuses', 'metamagic', 'subclass_id'):
                self.assertEqual(s.character[field], before[field])
            snapshot = s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 4), PICK)['status'], 'rejected')
            self.assertEqual(s._capture_runtime_snapshot(), snapshot)

    def test_versions_four_five_repeated_fresh_restore_without_reapplying(self):
        for version in (4, 5):
            for first in (False, True):
                s = create(3); s._persisted_engine_format = version
                # v5 already requires a receipt list, even with no awards.
                s.world_state.setdefault('xp_awarded_event_ids', [])
                if first: xp.apply_xp(s.character, s.world_state, 1800, 'quest:version-four')
                self.advance(s)
                for _ in range(2):
                    payload = serialize_campaign_payload(s)
                    restored = game.create_session(seed=98)
                    restore_campaign_session(restored, payload)
                    for field in ('asi_choices', 'constitution', 'constitution_mod', 'modifiers', 'saving_throw_mods', 'final_ability_scores', 'max_hp', 'current_hp', 'xp'):
                        self.assertEqual(restored.character[field], s.character[field], field)
                    self.assertEqual(restored._persisted_engine_format, version)
                    s = restored

    def test_unaffected_and_affected_save_offsets_preserved(self):
        s = create(3)
        for ability in s.character['saving_throw_mods']:
            if ability != 'constitution': s.character['saving_throw_mods'][ability] += 7
        old = copy.deepcopy(s.character['saving_throw_mods'])
        self.advance(s)
        self.assertEqual(s.character['saving_throw_mods'], {**old, 'constitution': 5})
        # Generalized ordinary ASI preserves authoritative save extras instead
        # of imposing the former selected-CON-only canonical-total restriction.
        s = create(3); s.character['saving_throw_mods']['constitution'] += 1
        self.advance(s)
        self.assertEqual(s.character['saving_throw_mods']['constitution'], 6)

    def test_strict_previous_markers_caches_and_mirrors_block_without_mutation(self):
        edits = [('progression_level', None), ('progression_level', True), ('progression_level', 4),
                 ('constitution_mod', 99), ('final_ability_scores', {}), ('base_ability_scores', {}),
                 ('metamagic', []), ('subclass_id', 'wrong'), ('spells', []), ('cantrips', [])]
        for key, value in edits:
            s = create(3); s.character[key] = value; before = s._capture_runtime_snapshot()
            self.assertEqual(cp.preview_level_up(s, 4)['status'], 'blocked', key)
            self.assertEqual(s._capture_runtime_snapshot(), before)
        for version in (1, 2, 3):
            s = create(3); s._persisted_engine_format = version
            self.assertEqual(cp.preview_level_up(s, 4)['status'], 'blocked')

    def test_choices_are_exact_and_creation_four_remains_blocked(self):
        for edit in ({'cantrips': ['Fire Bolt']}, {'asi': {'feat': 'Alert', 'increase': {'constitution': 2}}},
                     {'asi': {'feat': 'Ability Score Improvement', 'increase': {'dexterity': 3}}},
                     {'asi': {'feat': 'Ability Score Improvement', 'increase': {'constitution': True}}},
                     {'asi': {'feat': 'Ability Score Improvement', 'increase': {'constitution': 2}, 'ignore_caps': True}}):
            s = create(3); p = cp.preview_level_up(s, 4)
            self.assertEqual(p['status'], 'ready')
            before = s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s, p, {**PICK, **edit})['status'], 'rejected')
            self.assertEqual(s._capture_runtime_snapshot(), before)
        s = create(3); before = s._capture_runtime_snapshot()
        with self.assertRaises(ValueError): cp.create_at_level(s, SPEC, 4, {'2': {}, '3': {}, '4': PICK})
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(cp.preview_level_up(s, 5)['status'], 'blocked')

    def test_synthetic_late_setter_fault_restores_snapshot_and_format_presence(self):
        for present in (False, True):
            s = create(3)
            if present: s._persisted_engine_format = 5
            else: s.__dict__.pop('_persisted_engine_format', None)
            p = cp.preview_level_up(s, 4); self.assertEqual(p['status'], 'ready')
            before = s._capture_runtime_snapshot(); containers = [s.character, s.world_state, s.messages]
            def fail(maximum):
                s._persisted_engine_format = 1
                s.rng.random(); s.messages.append({'synthetic': True})
                raise ValueError('synthetic late maximum fault')
            with patch.object(s, 'set_player_max_hp', side_effect=fail):
                self.assertEqual(cp.apply_level_choices(s, p, PICK)['status'], 'rejected')
            self.assertEqual(s._capture_runtime_snapshot(), before)
            self.assertEqual(hasattr(s, '_persisted_engine_format'), present)
            if present: self.assertEqual(s._persisted_engine_format, 5)
            for old, now in zip(containers, [s.character, s.world_state, s.messages]): self.assertIs(old, now)

    def test_zero_stable_dead_preserve_status_rng_and_do_not_heal(self):
        from api.tests.test_roadmap_c06_zero_hp_progression import zero_state
        for state in ('unconscious', 'stable', 'dead'):
            for first in (False, True):
                s = create(3)
                if first: xp.apply_xp(s.character, s.world_state, 1800, 'quest:zero-four')
                before = zero_state(s, state)
                with patch.object(s, 'heal_player', side_effect=AssertionError('ASI cannot heal')):
                    self.advance(s)
                self.assertEqual((s.character['current_hp'], s.character['max_hp']), (0, 30))
                self.assertEqual((s.world_state['death_state'], s.world_state['player_combat_status'], s.rng.getstate()), before)
                restored = game.create_session(seed=98)
                restore_campaign_session(restored, serialize_campaign_payload(s))
                self.assertEqual((restored.character['current_hp'], restored.character['max_hp']), (0, 30))

    def test_forged_or_missing_ledger_and_old_versions_reject_before_load(self):
        from api.persistence.campaign_models import CampaignCorruptError
        s = create(3); self.advance(s)
        payload = serialize_campaign_payload(s)
        variants = [None, [], {}, [None], [*RECORD, *RECORD],
                    [{'class_level': True, **PICK['asi']}],
                    [{'class_level': 4, 'feat': 'Ability Score Improvement', 'increase': {'constitution': 1, 'charisma': 1}}]]
        for record in variants:
            bad = copy.deepcopy(payload); bad['engine_save']['player']['asi_choices'] = record
            target = game.create_session(seed=19); before = target._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError): restore_campaign_session(target, bad)
            self.assertEqual(target._capture_runtime_snapshot(), before)
        for mode in ('missing', 'score', 'origin', 'saving', 'version1', 'version2', 'version3'):
            bad = copy.deepcopy(payload); player = bad['engine_save']['player']
            if mode == 'missing': player.pop('asi_choices')
            elif mode == 'score': player['constitution'] = 18
            elif mode == 'origin': player['origin_choices'].pop('base_ability_scores')
            elif mode == 'saving': player['saving_throw_mods']['constitution'] = True  # integer extras are now preserved; malformed totals still reject
            else: bad['engine_save']['version'] = int(mode[-1])
            target = game.create_session(seed=19); before = target._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError): restore_campaign_session(target, bad)
            self.assertEqual(target._capture_runtime_snapshot(), before)

    def test_restored_three_can_advance_and_retains_spent_hit_dice(self):
        s = create(3)
        s.character['hit_dice'] = {'spent': 2, 'window_second': None, 'hp': None}
        restored = game.create_session(seed=67)
        restore_campaign_session(restored, serialize_campaign_payload(s))
        before = copy.deepcopy(restored.character['hit_dice'])
        self.advance(restored)
        self.assertEqual(restored.character['hit_dice'], before)
        self.assertEqual(cp.capacity(restored.character)['slots'], {'1': 4, '2': 3})

    def test_actual_four_catalog_only_spell_rejects_without_debit(self):
        import spell_registry
        import spell_scope
        from combat_lifecycle import CombatRequestError
        s = create(3); self.advance(s)
        before = s._capture_runtime_snapshot()
        result = spell_registry.cast_spell('Mage Armor', {'session': s}, 1, {'target_id': 'player'})
        self.assertEqual((result['status'], result['reason']), ('unsupported', 'spell_resolver_missing'))
        with self.assertRaises(CombatRequestError): spell_scope.cast(s, 'Mage Armor', 'player', 1)
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_alive_combat_incapacitation_is_not_a_new_advancement_gate_or_action(self):
        from api.tests.test_death_system import start_test_combat
        s = create(3); start_test_combat(s)
        s.character['conditions'] = ['incapacitated']
        before = copy.deepcopy(s.world_state['combat'])
        self.advance(s)
        self.assertEqual(s.world_state['combat'], before)
        self.assertEqual(s.character['conditions'], ['incapacitated'])

    def test_actual_four_long_rest_restores_capacities_without_asi_replay(self):
        s = create(3); s.commit_location_change('tavern')
        self.advance(s)
        s.world_state['spellcasting_v1']['slots'] = {'1': 1, '2': 0}
        s.character['spell_slots_remaining'] = {'1': 1, '2': 0}
        restored = game.create_session(seed=32)
        restore_campaign_session(restored, serialize_campaign_payload(s))
        restored.resolve_species_trait_action('long_rest')
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'], {'1': 4, '2': 3})
        self.assertEqual((restored.character['constitution'], restored.character['max_hp']), (16, 30))

    def test_present_boolean_cache_and_saved_spell_mirror_forgery_reject(self):
        from api.persistence.campaign_models import CampaignCorruptError
        s = create(3)
        # Equality is insufficient: bool must not masquerade as an integer modifier.
        ability = next(a for a, v in s.character['modifiers'].items() if v in (0, 1))
        s.character['modifiers'][ability] = bool(s.character['modifiers'][ability])
        self.assertEqual(cp.preview_level_up(s, 4)['status'], 'blocked')
        s = create(3); self.advance(s)
        payload = serialize_campaign_payload(s)
        for field, value in (('cantrips', []), ('spells', []), ('spell_slots_remaining', {'1': 0, '2': 4})):
            bad = copy.deepcopy(payload); bad['engine_save']['player'][field] = value
            target = game.create_session(seed=75); before = target._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError): restore_campaign_session(target, bad)
            self.assertEqual(target._capture_runtime_snapshot(), before)

    def test_synthetic_postcommit_validation_failure_and_stale_preview_roll_back(self):
        s = create(3); preview = cp.preview_level_up(s, 4); before = s._capture_runtime_snapshot()
        original = cp.validate_saved
        def fail(player, world, **kwargs):
            if player.get('progression_level') == 4:
                raise ValueError('synthetic late validation fault')
            return original(player, world, **kwargs)
        with patch.object(cp, 'validate_saved', side_effect=fail):
            self.assertEqual(cp.apply_level_choices(s, preview, PICK)['status'], 'rejected')
        self.assertEqual(s._capture_runtime_snapshot(), before)
        stale = copy.deepcopy(preview); stale['capacity']['slots']['2'] = 99
        self.assertEqual(cp.apply_level_choices(s, stale, PICK)['status'], 'rejected')
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_actual_four_slot_two_cast_and_real_save_preserve_spent_world_authority(self):
        from api.tests.test_death_system import start_test_combat
        import bounded_encounter
        import spell_registry
        s = create(3); self.advance(s); start_test_combat(s)
        enemy = s.world_state['npcs'][-1]
        enemy.update(current_hp=100, max_hp=100, distance_ft=30,
                     monster_stat_block=copy.deepcopy(bounded_encounter.COMMONER))
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        s.world_state['attack_environment'] = {'pairs': {'player|' + enemy['id']: {
            'distance_ft': 30, 'attacker_sees_target': True, 'target_sees_attacker': True, 'cover': 'none'}}}
        with patch.object(s.rng, 'randint', return_value=2):
            result = spell_registry.cast_spell('Magic Missile', {'session': s}, 2, {'target_id': enemy['id']})
        self.assertEqual(result['status'], 'applied', result)
        self.assertEqual(result['result']['darts'], [3, 3, 3, 3])
        self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 4, '2': 2})
        restored = game.create_session(seed=24)
        restore_campaign_session(restored, serialize_campaign_payload(s))
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'], {'1': 4, '2': 2})
        self.assertEqual(restored.character['spell_slots_remaining'], {'1': 4, '2': 3})
        self.assertEqual(restored.character['max_hp'], 30)

    def test_preview_is_pure_and_advertises_only_selected_asi_scope(self):
        s = create(3); before = s._capture_runtime_snapshot()
        preview = cp.preview_level_up(s, 4)
        self.assertEqual(preview['choices_required'], {'prepared_spells': 1, 'cantrips': 1, 'asi': 1})
        from api.tests.test_roadmap_c06_nondex_asi import PATTERNS
        self.assertEqual(preview.get('supported_asi_choices'), [{'feat': 'Ability Score Improvement', 'increase': inc} for inc in PATTERNS])
        self.assertEqual(preview['capacity'], {'cantrips': 5, 'prepared_spells': 7, 'slots': {'1': 4, '2': 3}, 'sorcery_points': 4})
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_prior_spent_world_with_lagging_counter_can_advance_without_refill(self):
        s = create(3)
        s.world_state['spellcasting_v1']['slots'] = {'1': 1, '2': 0}
        # Existing cast/rest contract permits this older, bounded cache.
        self.assertEqual(s.character['spell_slots_remaining'], {'1': 4, '2': 2})
        self.advance(s)
        self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 1, '2': 1})
        self.assertEqual(s.character['spell_slots_remaining'], {'1': 1, '2': 1})
