"""Selected earned5: literal PHB advancement/Sorcerer rows, no full class claim."""
import copy
import unittest
from unittest.mock import patch
import game
import xp
import character_progression as cp
from api.tests.test_roadmap_c06_starting_xp import create
from api.tests.test_roadmap_c06_level4_con import PICK, RECORD
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session

FIVE = {'prepared_spells': ['Fog Cloud', 'Silent Image']}


def award(s, amount, identity):
    return s._receive_xp_award(xp.apply_xp, s.character, s.world_state, amount, identity)


def four():
    s = create(3)
    award(s, 1800, 'quest:four')
    result = cp.apply_level_choices(s, cp.preview_level_up(s, 4), copy.deepcopy(PICK))
    assert result['status'] == 'applied', result
    return s


class LevelFiveTests(unittest.TestCase):
    def test_real_threshold_and_pending_resources_roundtrip(self):
        s = four(); s.character['current_hp'] = 26
        slots = copy.deepcopy(s.world_state['spellcasting_v1'])
        self.assertEqual(award(s, 3799, 'quest:below')['new_level'], 4)
        result = award(s, 1, 'quest:five')
        self.assertEqual(result['new_level'], 5)
        self.assertEqual(result['hit_points_gained'], 7)
        self.assertEqual((s.character['xp'], s.character['progression_level'], s.character['proficiency_bonus']), (6500, 4, 3))
        self.assertEqual((s.character['current_hp'], s.character['max_hp']), (33, 37))
        self.assertEqual(s.world_state['spellcasting_v1'], slots)
        self.assertEqual(s._persisted_engine_format, 6)
        restored = game.create_session(seed=77)
        restore_campaign_session(restored, serialize_campaign_payload(s))
        self.assertEqual(restored.character['asi_choices'], RECORD)
        self.assertEqual(restored._persisted_engine_format, 6)
        before = restored._capture_runtime_snapshot()
        self.assertIsNone(award(restored, 1, 'quest:five'))
        self.assertEqual(restored._capture_runtime_snapshot(), before)

    def test_real_five_choices_preserve_spent_resources(self):
        s = four(); award(s, 3800, 'quest:five')
        s.world_state['spellcasting_v1']['slots'] = {'1': 2, '2': 1}
        before = copy.deepcopy(s.character)
        p = cp.preview_level_up(s, 5)
        self.assertEqual(p['status'], 'ready', p)
        self.assertEqual(p['choices_required'], {'prepared_spells': 2})
        self.assertEqual(p['capacity'], {'cantrips': 5, 'prepared_spells': 9, 'slots': {'1': 4, '2': 3, '3': 2}, 'sorcery_points': 5})
        self.assertEqual(cp.apply_level_choices(s, p, FIVE)['status'], 'applied')
        self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 2, '2': 1, '3': 2})
        for k in ('max_hp', 'current_hp', 'asi_choices', 'cantrips', 'metamagic', 'subclass_id', 'base_ability_scores'):
            self.assertEqual(s.character[k], before[k], k)
        self.assertEqual(s.character['spells'], before['spells'] + FIVE['prepared_spells'])
        for _ in range(2):
            fresh = game.create_session(seed=99); restore_campaign_session(fresh, serialize_campaign_payload(s)); s = fresh
        self.assertEqual((s.character['level'], s.character['progression_level'], s.character['max_hp']), (5, 5, 37))

    def test_xp_ahead_raw_five_can_apply_four_without_double_base_hp(self):
        s = create(3); award(s, 5600, 'quest:jump-five')
        self.assertEqual(s.character['level'], 5)
        self.assertEqual(s.character['max_hp'], 32)
        p = cp.preview_level_up(s, 4); self.assertEqual(p['status'], 'ready', p)
        r = cp.apply_level_choices(s, p, PICK); self.assertEqual(r['status'], 'applied', r)
        self.assertEqual((s.character['level'], s.character['progression_level'], s.character['max_hp'], s.character['current_hp']), (5, 4, 37, 32))
        self.assertEqual(s.character['asi_choices'], RECORD)
        self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 5), FIVE)['status'], 'applied')

    def test_pb_delta_preserves_offsets_and_refreshes_present_caches(self):
        s = four()
        s.character['saving_throw_mods']['charisma'] += 7
        s.character['saving_throw_mods']['dexterity'] += 9
        old = copy.deepcopy(s.character['saving_throw_mods'])
        award(s, 3800, 'quest:pb-five')
        self.assertEqual(s.character['proficiency_bonus'], 3)
        for ability, total in old.items():
            self.assertEqual(s.character['saving_throw_mods'][ability], total + (ability in ('constitution', 'charisma')))

    def test_historical_overflow_is_readable_without_load_awards(self):
        for version in (4, 5):
            s = four(); s._persisted_engine_format = version
            # Historically valid cap4 overflow fixture, not a newly earned5 fixture.
            s.character['xp'] = 10000
            p = serialize_campaign_payload(s)
            fresh = game.create_session(seed=99); restore_campaign_session(fresh, p)
            self.assertEqual((fresh.character['level'], fresh.character['max_hp'], fresh._persisted_engine_format), (4, 30, version))
            self.assertEqual(serialize_campaign_payload(fresh)['engine_save'], p['engine_save'])
            r = award(fresh, 1, 'quest:legitimate-next-award')
            self.assertEqual((r['xp_gained'], r['new_level'], r['hit_points_gained']), (1, 5, 7))
            self.assertEqual(fresh.character['xp'], 10001)
            self.assertEqual(fresh._persisted_engine_format, 6)

    def test_session_award_boundary_rejects_legacy_and_rolls_back_failed_v6_admission(self):
        s = four()
        self.assertTrue(callable(getattr(s, '_receive_xp_award', None)), 'Session must wrap pre-award mutation')
        # 4B carry-over (was: legacy 1..3 refused): the crossing now moves the campaign to format6 in place, admitted
        # by the real save validator; a refused admission still restores everything, the legacy format included.
        for version in (1, 2, 3):
            s = four(); s._persisted_engine_format = version
            r = s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 3800, 'quest:legacy-five')
            self.assertEqual((r['previous_level'], r['new_level'], s.character['level'], s._persisted_engine_format), (4, 5, 5, 6))
            game._validate_save_payload(s.serialize_game_state())
            s = four(); s._persisted_engine_format = version
            before = s._capture_runtime_snapshot()
            with patch('game._validate_save_payload', side_effect=ValueError('synthetic admission failure')):
                with self.assertRaises(ValueError):
                    s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 3800, 'quest:legacy-five')
            self.assertEqual(s._capture_runtime_snapshot(), before)
            self.assertEqual(s._persisted_engine_format, version)
        s = four(); before = s._capture_runtime_snapshot()
        # Synthetic late validation fault, not an actual failed SQL commit.
        with patch('game._validate_save_payload', side_effect=ValueError('synthetic admission failure')):
            with self.assertRaises(ValueError):
                s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 3800, 'quest:fault-five')
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(s._persisted_engine_format, 4)

    def test_real_slot_three_cast_uses_five_darts_and_only_selected_pool(self):
        import spell_registry
        from api.tests.test_spell_scope import caster
        s, enemy = caster(); source = four()
        s.character.clear(); s.character.update(copy.deepcopy(source.character))
        s.world_state['spellcasting_v1'] = copy.deepcopy(source.world_state['spellcasting_v1'])
        award(s, 3800, 'quest:five-cast')
        self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 5), FIVE)['status'], 'applied')
        s.world_state['spellcasting_v1']['slots']['1'] = 0
        with patch.object(s.rng, 'randint', return_value=2):
            result = spell_registry.cast_spell('Magic Missile', {'session': s}, 3, {'target_id': enemy['id']})
        self.assertEqual(result['status'], 'applied', result)
        self.assertEqual(result['slot_level'], 3)
        self.assertEqual(result['result']['darts'], [3, 3, 3, 3, 3])
        self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1': 0, '2': 3, '3': 1})

    def test_policy_discriminator_preserves_historic_equality_and_choices_ahead(self):
        s = four(); player = copy.deepcopy(s.character); player['xp'] = 10000
        xp.validate_saved_advancement(player, s.world_state, policy=5)
        with self.assertRaises(ValueError): xp.validate_saved_advancement(player, s.world_state, policy=6)
        player.pop('progression_level')
        xp.validate_saved_advancement(player, s.world_state, policy=5)
        with self.assertRaises(ValueError): xp.validate_saved_advancement(player, s.world_state, policy=6)
        player.update(level=3, proficiency_bonus=2)
        with self.assertRaises(ValueError): xp.validate_saved_advancement(player, s.world_state, policy=5)
        player.update(level=4, progression_level=4, xp=900)
        for policy in (5, 6): xp.validate_saved_advancement(player, s.world_state, policy=policy)
        for policy in (None, True, 4, 7):
            with self.assertRaises(ValueError): xp.validate_saved_advancement(player, s.world_state, policy=policy)

    def test_no_promotion_from_duplicate_zero_preview_or_save_and_exact_absence_rollback(self):
        s = four(); s.character['xp'] = 10000
        for amount, identity in [(0, 'quest:none'), (1, 'quest:four')]:
            before = s._capture_runtime_snapshot()
            self.assertIsNone(award(s, amount, identity))
            self.assertEqual(s._capture_runtime_snapshot(), before)
            self.assertEqual(s._persisted_engine_format, 4)
        cp.preview_level_up(s, 5); serialize_campaign_payload(s)
        self.assertEqual(s._persisted_engine_format, 4)
        s.__dict__.pop('_persisted_engine_format'); before = s._capture_runtime_snapshot()
        with patch('game._validate_save_payload', side_effect=ValueError('synthetic admission failure')):
            with self.assertRaises(ValueError): award(s, 1, 'quest:format-absent-fault')
        self.assertNotIn('_persisted_engine_format', s.__dict__)
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_invalid_v6_spell_admission_rolls_back_actual_award(self):
        s = four(); s.world_state.pop('spellcasting_v1')
        before = s._capture_runtime_snapshot()
        with self.assertRaises(ValueError): award(s, 3800, 'quest:invalid-spell-state')
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(s._persisted_engine_format, 4)

    def test_refused_five_choices_preserve_full_state_and_rng(self):
        for choices in ({}, {'prepared_spells': ['Fog Cloud']}, {'prepared_spells': ['Fog Cloud', 'Fog Cloud']},
                        {'prepared_spells': ['Magic Missile', 'Silent Image']}, {**FIVE, 'asi': PICK['asi']},
                        {**FIVE, 'cantrips': []}, {'prepared_spells': ['Fog Cloud', 'not-a-spell']}):
            s = four(); award(s, 3800, 'quest:five')
            p = cp.preview_level_up(s, 5); before = s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s, p, choices)['status'], 'rejected')
            self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(cp.preview_level_up(s, 6)['status'], 'blocked')

    def test_selection_only_spells_never_debit_resources(self):
        import spell_registry
        s = four(); award(s, 3800, 'quest:five'); cp.apply_level_choices(s, cp.preview_level_up(s, 5), FIVE)
        for name in FIVE['prepared_spells']:
            before = s._capture_runtime_snapshot()
            r = spell_registry.cast_spell(name, {'session': s}, 1, {})
            self.assertEqual((r['status'], r['reason']), ('unsupported', 'spell_resolver_missing'))
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_present_pb_caches_are_invalidated_without_touching_resources(self):
        s = four()
        for key in ('initiative', 'spell_save_dc', 'spell_attack_bonus'): s.character[key] = 99
        state = copy.deepcopy(s.world_state['spellcasting_v1'])
        award(s, 3800, 'quest:five-caches')
        for key in ('initiative', 'spell_save_dc', 'spell_attack_bonus'): self.assertNotIn(key, s.character)
        self.assertEqual(s.world_state['spellcasting_v1'], state)

    def test_magic_public_availability_tracks_action_slot_not_target_success(self):
        import action_economy as ae
        from api.tests.test_spell_scope import caster
        s, enemy = caster()
        def magic():
            return next(v for v in ae.projection(s)['actors']['player']['legal_actions'] if v['kind'] == 'magic')
        self.assertTrue(magic()['legal'], magic())
        # An invalid target remains the spell owner's concern, not slot eligibility.
        enemy['current_hp'] = 0
        self.assertTrue(magic()['legal'])
        ae.ensure(s)['player']['base_action_spent'] = True
        self.assertFalse(magic()['legal'])
        ae.grant(s, 'player', 'synthetic-extra-attack-only', ['attack'])
        self.assertFalse(magic()['legal'])
        ae.grant(s, 'player', 'synthetic-extra-magic', ['magic'])
        self.assertTrue(magic()['legal'])

    def test_numeric_five_award_announcement_is_admitted(self):
        from api.schemas import LevelUpResult
        try:
            result = LevelUpResult.model_validate({'previous_level': 4, 'new_level': 5, 'xp_gained': 1, 'hit_points_gained': 7})
        except ValueError as error:
            self.fail('Real XP5 announcement rejected: ' + str(error))
        self.assertEqual(result.new_level, 5)

    def test_zero_hp_and_spent_hit_dice_survive_numeric_and_applied_five(self):
        import hit_dice
        from api.tests.test_roadmap_c06_zero_hp_progression import zero_state
        for status in ('unconscious', 'stable', 'dead'):
            s = four(); s.character['hit_dice'] = {'spent': 2, 'window_second': None, 'hp': None}
            old = zero_state(s, status)
            award(s, 3800, 'quest:zero-five')
            self.assertEqual(hit_dice.total(s.character), 4)
            self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 5), FIVE)['status'], 'applied')
            self.assertEqual((hit_dice.total(s.character), hit_dice.remaining(s.character)), (5, 3))
            self.assertEqual((s.character['current_hp'], s.character['max_hp']), (0, 37))
            self.assertEqual((s.world_state['death_state'], s.world_state['player_combat_status'], s.rng.getstate()), old)
            fresh = game.create_session(seed=99); restore_campaign_session(fresh, serialize_campaign_payload(s))
            self.assertEqual((fresh.character['current_hp'], fresh.character['max_hp'], fresh.character['hit_dice']['spent']), (0, 37, 2))

    def test_slot_three_empty_unsupported_and_rest_save_contract(self):
        import spell_scope
        from combat_lifecycle import CombatRequestError
        from api.tests.test_spell_scope import caster
        def ready():
            s, enemy = caster(); source = four()
            s.character.clear(); s.character.update(copy.deepcopy(source.character))
            s.world_state['spellcasting_v1'] = copy.deepcopy(source.world_state['spellcasting_v1'])
            award(s, 3800, 'quest:five-slot'); cp.apply_level_choices(s, cp.preview_level_up(s, 5), FIVE)
            return s, enemy
        for mode in ('empty', 'unsupported', 'other-upcast'):
            s, enemy = ready()
            if mode == 'empty': s.world_state['spellcasting_v1']['slots']['3'] = 0
            before = s._capture_runtime_snapshot()
            with self.assertRaises(CombatRequestError):
                spell_scope.cast(s, 'Fire Bolt' if mode == 'other-upcast' else 'Magic Missile', enemy['id'], 4 if mode == 'unsupported' else 3)
            self.assertEqual(s._capture_runtime_snapshot(), before)
        s, enemy = ready(); spell_scope.cast(s, 'Magic Missile', enemy['id'], 3)
        s.commit_location_change('tavern')
        fresh = game.create_session(seed=88); restore_campaign_session(fresh, serialize_campaign_payload(s))
        self.assertEqual(fresh.world_state['spellcasting_v1']['slots'], {'1': 4, '2': 3, '3': 1})
        marker = copy.deepcopy(fresh.world_state['spellcasting_v1']['slot_turn'])
        fresh.end_combat('explicit_rest'); fresh.resolve_species_trait_action('long_rest')
        self.assertEqual(fresh.world_state['spellcasting_v1']['slots'], {'1': 4, '2': 3, '3': 2})
        self.assertEqual(fresh.world_state['spellcasting_v1']['slot_turn'], marker)
