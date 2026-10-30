"""Earned selected Berserker4 ordinary ASI; literal PHB numeric oracles.

Synthetic dice, ambiguous AC and injected late faults are unit boundaries, not
native campaign evidence. Human species-bonus Tough is an unresolved XP owner
gap and is not certified by ordinary Human/background Tough cases here.
"""
import copy
import json
import unittest
from unittest.mock import patch

import game
import xp
import hit_dice
import character_progression as cp
import barbarian_rage as rage
import weapon_attack as attacks
from api.tests.test_roadmap_c06_barbarian import spec
from api.tests.test_roadmap_c06_nondex_asi import PATTERNS, ABILITIES
from api.tests.test_roadmap_c10_berserker_progression import PICK as THREE
from api.tests.test_roadmap_c10_rage import combat
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError, CampaignValidationError


def selected_three(test, *, raw=4, species='Human', background='Criminal', odd_con=False, scores=None, bonuses=None):
    request = spec()
    if species == 'Dwarf':
        request.update(species=species, race=species)
        request['proficient_skills'].remove('Persuasion')
    if background == 'Farmer':
        request.update(background=background, background_ability_bonuses={'wisdom': 2, 'constitution': 1},
                       proficient_skills=['Athletics', 'Perception', 'Persuasion', 'Animal Handling', 'Nature'])
    if odd_con:
        request['background_ability_bonuses'] = {'dexterity': 2, 'intelligence': 1}
    if scores:
        request['ability_score_method'] = 'manual'
        request['ability_scores'].update(scores)
    if bonuses is not None:
        request["background_ability_bonuses"] = bonuses
    session = game.create_session(seed=52)
    cp.create_at_level(session, request, 2, {'2': {}})
    session.commit_location_change('tavern')
    session.ensure_campaign_clock()
    session._receive_xp_award(xp.apply_xp, session.character, session.world_state, 600, 'quest:barbarian4-three')
    result = cp.apply_level_choices(session, cp.preview_level_up(session, 3), copy.deepcopy(THREE))
    test.assertEqual(result['status'], 'applied', result)
    if raw > 3:
        session._receive_xp_award(xp.apply_xp, session.character, session.world_state,
                                 1800 if raw == 4 else 5600, 'quest:barbarian4-earned')
    return session


def choose(increase):
    return {'asi': {'feat': 'Ability Score Improvement', 'increase': copy.deepcopy(increase)}}


def advance(test, session, increase=None):
    preview = cp.preview_level_up(session, 4)
    test.assertEqual(preview['status'], 'ready', preview)
    result = cp.apply_level_choices(session, preview, choose({'constitution': 2} if increase is None else increase))
    test.assertEqual(result['status'], 'applied', result)
    return result


class BarbarianFourTests(unittest.TestCase):
    def test_existing_core_request_result_oracles(self):
        # Recorded before implementation, with all actual target imports guarded.
        from api.tests.test_roadmap_c06_starting_xp import create
        from api.tests.test_roadmap_c06_level4_con import PICK as FOUR
        sorcerer = create(3)
        sp = cp.preview_level_up(sorcerer, 4)
        sd = cp.apply_level_choices(sorcerer, sp, copy.deepcopy(FOUR))
        self.assertEqual(sd['status'], 'applied')
        barbarian = game.create_session(seed=52)
        cp.create_at_level(barbarian, spec(), 2, {'2': {}})
        bp = cp.preview_level_up(barbarian, 3)
        bd = cp.apply_level_choices(barbarian, bp, copy.deepcopy(THREE))
        self.assertEqual(bd['status'], 'applied')
        print('BARBARIAN4_PREEXISTING_CORE_ORACLES:' + json.dumps(
            {'sorcerer4': {'request': FOUR, 'preview': sp, 'result': sd},
             'barbarian3': {'request': THREE, 'preview': bp, 'result': bd}}, sort_keys=True))

    def test_source_four_and_pure_exact_noncasting_preview(self):
        s = selected_three(self)
        before = s._capture_runtime_snapshot()
        p = cp.preview_level_up(s, 4)
        self.assertEqual(p['status'], 'ready', p)
        self.assertEqual(p['choices_required'], {'asi': 1})
        self.assertIsNone(p['capacity'])
        self.assertIsNone(cp.capacity(s.character))
        self.assertEqual(p['features'], ['Ability Score Improvement'])
        self.assertEqual([o['increase'] for o in p['supported_asi_choices']], PATTERNS)
        self.assertEqual(cp.table('Barbarian')['levels'].get('4'),
                         {'proficiency_bonus': 2, 'features': ['Ability Score Improvement'],
                          'rages': 3, 'rage_damage': 2, 'weapon_mastery': 3})
        self.assertIn('Weapon Mastery', ' '.join(p['effects_pending']))
        self.assertIn('CON', ' '.join(p['effects_pending']))
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_all_fifteen_scores_provenance_no_caster_and_repeated_fresh_restore(self):
        for inc in PATTERNS:
            with self.subTest(increase=inc):
                s = selected_three(self)
                old = copy.deepcopy(s.character); world = copy.deepcopy(s.world_state); rng = s.rng.getstate()
                advance(self, s, inc)
                for ability in ABILITIES:
                    self.assertEqual(s.character[ability], old[ability] + inc.get(ability, 0))
                    self.assertEqual(s.character[ability + '_mod'], (s.character[ability] - 10) // 2)
                    self.assertEqual(s.character['modifiers'][ability], s.character[ability + '_mod'])
                    self.assertEqual(s.character['saving_throw_mods'][ability], old['saving_throw_mods'][ability]
                                     + s.character[ability + '_mod'] - old[ability + '_mod'])
                self.assertEqual(s.character['asi_choices'], [{'class_level': 4, **choose(inc)['asi']}])
                self.assertEqual(s.character['primal_knowledge_choice'], old['primal_knowledge_choice'])
                self.assertEqual(s.character['primal_knowledge_choice']['class_level'], 3)
                for key in ('proficient_skills', 'base_ability_scores', 'background_ability_bonuses', 'origin_feat',
                            'origin_feats', 'inventory', 'initiative', 'species_bonus_skills', 'background'):
                    self.assertEqual(s.character.get(key), old.get(key), key)
                for key in ('inventory', 'currency', 'equipment', 'rage_v1', 'worn_armor_v1', 'xp_awarded_event_ids'):
                    self.assertEqual(s.world_state.get(key), world.get(key), key)
                self.assertNotIn('spellcasting_v1', s.world_state)
                self.assertNotIn('sorcery_points_v1', s.world_state)
                self.assertFalse(s.character.get('metamagic'))
                self.assertEqual(s.rng.getstate(), rng)
                for _ in range(2):
                    payload = serialize_campaign_payload(s); fresh = game.create_session(seed=19)
                    restore_campaign_session(fresh, payload)
                    self.assertEqual(serialize_campaign_payload(fresh), payload)
                    s = fresh

    def test_conditional_ac_filter_preserves_noncon_and_parity_neutral_options(self):
        for ac in (0, 13, 14, 16, 17):
            for inc, accepted in (({'constitution': 2}, False), ({'strength': 2}, True),
                                  ({'constitution': 1, 'strength': 1}, True)):
                with self.subTest(ac=ac, inc=inc):
                    s = selected_three(self); self.assertEqual(s.character['armor_class'], 15)
                    s.character['armor_class'] = ac
                    # Possession is not worn-formula evidence.
                    s.world_state['inventory'].extend(['Shield', 'Chain Mail'])
                    p = cp.preview_level_up(s, 4)
                    self.assertEqual(p['status'], 'ready', p)
                    self.assertEqual(choose(inc)['asi'] in p['supported_asi_choices'], accepted)
                    before = s._capture_runtime_snapshot()
                    result = cp.apply_level_choices(s, p, choose(inc))
                    if accepted:
                        self.assertEqual(result['status'], 'applied', result)
                        self.assertEqual(s.character['armor_class'], ac)
                        fresh = game.create_session(seed=19)
                        restore_campaign_session(fresh, serialize_campaign_payload(s))
                        self.assertEqual(fresh.character['armor_class'], ac)
                    else:
                        self.assertEqual(result['reason'], 'asi_choice_not_eligible')
                        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_con_split_order_and_odd_threshold_canonical_ac(self):
        for inc in ({'constitution': 1, 'strength': 1}, {'strength': 1, 'constitution': 1}):
            s = selected_three(self, odd_con=True)
            self.assertEqual((s.character['constitution'], s.character['armor_class'], s.character['max_hp']), (13, 14, 37))
            advance(self, s, inc)
            self.assertEqual((s.character['constitution'], s.character['armor_class'], s.character['current_hp'], s.character['max_hp']),
                             (14, 15, 37, 41))
            payload = serialize_campaign_payload(s); fresh = game.create_session(seed=19)
            restore_campaign_session(fresh, payload)
            self.assertEqual(serialize_campaign_payload(fresh), payload)
            payload['engine_save']['player']['armor_class'] = 14
            before = fresh._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError): restore_campaign_session(fresh, payload)
            self.assertEqual(fresh._capture_runtime_snapshot(), before)
            s = selected_three(self, odd_con=True); s.character['armor_class'] = 15
            p = cp.preview_level_up(s, 4)
            self.assertEqual(p['status'], 'ready', p)
            self.assertNotIn(choose(inc)['asi'], p['supported_asi_choices'])
            before = s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s, p, choose(inc))['status'], 'rejected')
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_invalid_ac_proof_and_caster_state_block_without_adoption(self):
        changes = [lambda s, ac=ac: s.character.update(armor_class=ac) for ac in (True, -1, 15.0, '15', None)]
        changes += [lambda s: s.character.pop('armor_class'), lambda s: s.world_state.pop('rage_v1'),
                    lambda s: s.world_state.pop('worn_armor_v1'),
                    lambda s: s.world_state.update(worn_armor_v1={'version': True, 'armor_id': None}),
                    lambda s: s.world_state.update(spellcasting_v1=None),
                    lambda s: s.world_state.update(sorcery_points_v1={'version': 1, 'remaining': 0}),
                    lambda s: s.character.update(metamagic=['Quickened Spell'])]
        for change in changes:
            s = selected_three(self); change(s); before = s._capture_runtime_snapshot()
            self.assertEqual(cp.preview_level_up(s, 4)['status'], 'blocked')
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_literal_hp_species_background_actual_xp_and_maximum_only(self):
        for species, bg, three, paid, final in (('Human', 'Criminal', 32, 41, 45),
                                               ('Dwarf', 'Criminal', 35, 45, 49),
                                               ('Human', 'Farmer', 38, 49, 53)):
            s = selected_three(self, raw=3, species=species, background=bg)
            self.assertEqual((s.character['current_hp'], s.character['max_hp']), (three, three))
            s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 1800, 'quest:literal-four')
            self.assertEqual((s.character['level'], s.character['current_hp'], s.character['max_hp']), (4, paid, paid))
            with patch.object(s, 'heal_player', side_effect=AssertionError('ASI cannot heal')):
                delta = advance(self, s)
            self.assertEqual((s.character['current_hp'], s.character['max_hp']), (paid, final))
            self.assertIn({'kind': 'hit_points', 'gain': 0}, delta['changes'])
            self.assertIn({'kind': 'maximum_hit_points', 'gain': 4}, delta['changes'])

    def test_raw_five_and_direct_unpaid_base_no_repeat_no_extra_xp(self):
        for raw, old_hp, new_hp, base, retro in ((3, 32, 45, 9, 4), (5, 50, 55, 0, 5)):
            s = selected_three(self, raw=raw)
            self.assertEqual(s.character['max_hp'], old_hp)
            old_xp = s.character['xp']; ids = copy.deepcopy(s.world_state['xp_awarded_event_ids'])
            delta = advance(self, s)
            self.assertEqual((s.character['current_hp'], s.character['max_hp']), (old_hp + base, new_hp))
            self.assertIn({'kind': 'hit_points', 'gain': base}, delta['changes'])
            self.assertIn({'kind': 'maximum_hit_points', 'gain': retro}, delta['changes'])
            self.assertEqual(s.character['xp'], old_xp)
            self.assertEqual(s.world_state['xp_awarded_event_ids'], ids)
            before = s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s, {'status': 'ready', 'to_level': 4}, choose({'constitution': 2}))['reason'], 'already_applied')
            self.assertEqual(s._capture_runtime_snapshot(), before)
        for inc in ({'strength': 2}, {'constitution': 1, 'strength': 1}):
            s = selected_three(self); advance(self, s, inc)
            self.assertEqual((s.character['current_hp'], s.character['max_hp'], s.character['armor_class']), (41, 41, 15))

    def test_hit_dice_actual_spending_window_and_derived_total_only(self):
        for count in (2, 3):
            s = selected_three(self)
            s._apply_player_damage(30, took_damage=True)
            s.resolve_species_trait_action('short_rest')
            with patch.object(s.rng, 'randint', return_value=1):
                for _ in range(count): hit_dice.spend(s, s.heal_player)
            old = copy.deepcopy(s.character['hit_dice']); hp = s.character['current_hp']; rng = s.rng.getstate()
            self.assertEqual((hit_dice.total(s.character), hit_dice.remaining(s.character)), (3, 3-count))
            self.assertTrue(hit_dice.window_open(s))
            advance(self, s)
            self.assertEqual(s.character['hit_dice'], old)
            self.assertEqual((hit_dice.total(s.character), hit_dice.remaining(s.character)), (4, 4-count))
            self.assertEqual(s.character['current_hp'], hp)
            self.assertTrue(hit_dice.window_open(s))
            self.assertEqual(s.rng.getstate(), rng)

    def test_saved_con_changing_ac_and_forged_records_refuse_atomically(self):
        s = selected_three(self); advance(self, s)
        payload = serialize_campaign_payload(s)
        self.assertEqual(payload['engine_save']['player']['armor_class'], 16)
        changes = [lambda p: p.update(armor_class=15), lambda p: p.update(armor_class=17),
                   lambda p: p.update(level=3), lambda p: p.update(level=True), lambda p: p.update(progression_level='4'),
                   lambda p: p.pop('asi_choices'), lambda p: p.pop('primal_knowledge_choice'),
                   lambda p: p.pop('subclass_id'), lambda p: p.update(subclass_id='wild_heart'),
                   lambda p: p['asi_choices'][0].update(increase={'dexterity': 2}),
                   lambda p: p['asi_choices'][0].update(class_level=True),
                   lambda p: p['primal_knowledge_choice'].update(class_level=4),
                   lambda p: p['origin_choices']['base_ability_scores'].update(constitution=12)]
        for change in changes:
            bad = copy.deepcopy(payload); change(bad['engine_save']['player'])
            target = selected_three(self); before = target._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError): restore_campaign_session(target, bad)
            self.assertEqual(target._capture_runtime_snapshot(), before)
        for version in (4, 5, 6):
            s._persisted_engine_format = version
            p = serialize_campaign_payload(s); target = game.create_session(seed=19)
            restore_campaign_session(target, p)
            self.assertEqual(serialize_campaign_payload(target), p)

    def test_strict_increases_and_caps_reject_without_mutation(self):
        for inc in ({}, {'constitution': True}, {'strength': 2.0}, {'wisdom': '2'}, {'dexterity': 2},
                    {'STR': 2}, {'unknown': 2}, {'strength': 1}, {'strength': 2, 'wisdom': 1}, {'strength': 1, 'wisdom': 1, 'charisma': 1}):
            s = selected_three(self); p = cp.preview_level_up(s, 4)
            self.assertEqual(p['status'], 'ready', p)
            before = s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s, p, choose(inc))['status'], 'rejected', inc)
            self.assertEqual(s._capture_runtime_snapshot(), before)
        for choice in ({}, {'asi': []}, {'asi': {'feat': 'Other', 'increase': {'strength': 2}}},
                       {'asi': {'feat': 'Ability Score Improvement', 'increase': {'strength': 2}, 'ignore_caps': True}},
                       {**choose({'strength': 2}), 'cantrips': []}, {**choose({'strength': 2}), 'prepared_spells': []}):
            s = selected_three(self); p = cp.preview_level_up(s, 4)
            self.assertEqual(p['status'], 'ready', p)
            before = s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s, p, choice)['status'], 'rejected')
            self.assertEqual(s._capture_runtime_snapshot(), before)
        for score, allow_two, allow_one in ((18, True, True), (19, False, True), (20, False, False)):
            s = selected_three(self, scores={'constitution': score - 2}, bonuses={'constitution': 2, 'dexterity': 1})
            p = cp.preview_level_up(s, 4)
            self.assertEqual(p['status'], 'ready', p)
            self.assertEqual(choose({'constitution': 2})['asi'] in p['supported_asi_choices'], allow_two)
            self.assertEqual(choose({'constitution': 1, 'wisdom': 1})['asi'] in p['supported_asi_choices'], allow_one)

    def test_zero_hp_death_rng_and_late_failures_restore_exact_format_presence(self):
        from api.tests.test_roadmap_c06_zero_hp_progression import zero_state
        for status in ('unconscious', 'stable', 'dead'):
            s = selected_three(self); before = zero_state(s, status)
            with patch.object(s, 'heal_player', side_effect=AssertionError('ASI cannot revive')): advance(self, s)
            self.assertEqual((s.character['current_hp'], s.character['max_hp']), (0, 45))
            self.assertEqual((s.world_state['death_state'], s.world_state['player_combat_status'], s.rng.getstate()), before)
        for field in ('set_player_max_hp', '_player_state_for_save', '_validate_save_payload', '_sync_combat_participant_records'):
            for present in (False, True):
                s, npc = combat()
                result = cp.apply_level_choices(s, cp.preview_level_up(s, 3), copy.deepcopy(THREE))
                self.assertEqual(result['status'], 'applied')
                if present: s._persisted_engine_format = 4
                else: s.__dict__.pop('_persisted_engine_format', None)
                p = cp.preview_level_up(s, 4); self.assertEqual(p['status'], 'ready', p)
                before = s._capture_runtime_snapshot()
                def fault(*args, **kwargs):
                    s._persisted_engine_format = 1; s.rng.randint(1, 20)
                    raise ValueError('synthetic late ' + field)
                with patch.object(game if field == '_player_state_for_save' else s, field, side_effect=fault):
                    self.assertEqual(cp.apply_level_choices(s, p, choose({'constitution': 2}))['status'], 'rejected', field)
                self.assertEqual(s._capture_runtime_snapshot(), before)
                self.assertEqual('_persisted_engine_format' in s.__dict__, present)
                if present: self.assertEqual(s._persisted_engine_format, 4)

    def test_creation_bundles_are_exact_per_level_and_level_six_is_unsupported(self):
        # Superseded: start 4 and 5 are accepted creation leaves now (test_roadmap_c06_barbarian_creation45). A bundle that does
        # not match its starting level exactly is still refused before any mutation.
        for level, bundle in ((3, {'2': {}, '3': THREE, '4': choose({'strength': 2})}),
                              (4, {'2': {}, '3': THREE}), (4, {'2': {}, '3': THREE, '4': choose({'strength': 2}), '5': {}}),
                              (5, {'2': {}, '3': THREE, '4': choose({'strength': 2})})):
            s = selected_three(self); before = s._capture_runtime_snapshot()
            with self.assertRaises(ValueError): cp.create_at_level(s, spec(), level, bundle)
            self.assertEqual(s._capture_runtime_snapshot(), before)
        for level, bundle in ((4, {'2': {}, '3': THREE, '4': choose({'strength': 2})}),
                              (5, {'2': {}, '3': THREE, '4': choose({'strength': 2}), '5': {}})):
            s = selected_three(self)
            cp.create_at_level(s, spec(), level, bundle)
            self.assertEqual((s.character['level'], s.character['progression_level']), (level, level))
        s = selected_three(self); before = s._capture_runtime_snapshot()
        with self.assertRaisesRegex(ValueError, 'progression_level_not_supported'):
            cp.create_at_level(s, spec(), 6, {'2': {}, '3': THREE, '4': choose({'strength': 2}), '5': {}, '6': {}})
        self.assertEqual(s._capture_runtime_snapshot(), before)
        s = selected_three(self, raw=5); advance(self, s)
        before = s._capture_runtime_snapshot()
        # Earned level 5 is now supported (test_roadmap_c06_barbarian_level5); level 6 stays unsupported.
        self.assertEqual(cp.preview_level_up(s, 5)['status'], 'ready')
        self.assertEqual(cp.preview_level_up(s, 6)['reason'], 'progression_level_not_supported')
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_live_frenzy_rage_preserved_and_actual_primal_at_four(self):
        from api.tests.test_roadmap_c10_frenzy import FrenzyTests
        f = FrenzyTests(); s, npc = f.encounter()
        first = f.strike(s, npc, reckless=True)
        self.assertEqual(first['damage'], 10)
        state = copy.deepcopy(s.world_state['rage_v1']); seq = attacks.sequence_snapshot(s, 'player')
        advance(self, s, {'strength': 2})
        self.assertEqual(s.world_state['rage_v1'], state)
        self.assertEqual(attacks.sequence_snapshot(s, 'player'), seq)
        self.assertEqual(f.strike(s, npc)['damage'], 5)  # STR -1→0, no repeated Frenzy
        s.advance_combat_turn(); s.advance_combat_turn(); rage.extend(s)
        self.assertEqual(f.strike(s, npc, reckless=True)['damage'], 11)
        s.ensure_combat_state()  # Direct strike helper bypasses the outer action owner's record refresh.
        payload = serialize_campaign_payload(s); t = game.create_session(seed=19)
        restore_campaign_session(t, payload); self.assertEqual(serialize_campaign_payload(t), payload)
        s.end_combat('four_primal')
        from api.tests.test_roadmap_c10_primal_knowledge import roll
        with patch('game.roll_d20', side_effect=[5, 16]): result = roll(s, 'Survival')
        self.assertEqual((result['ability'], result['modifier'], result['proficiency_bonus'], result['total']), ('strength', 0, 2, 18))
        self.assertTrue(result['advantage'])

    def test_pool_zero_to_three_and_active_hardcap_retained(self):
        for remaining in range(4):
            s = selected_three(self)
            s.world_state['rage_v1']['remaining'] = remaining  # bounded spent-resource fixture
            before = copy.deepcopy(s.world_state['rage_v1'])
            advance(self, s)
            self.assertEqual(s.world_state['rage_v1'], before)
            self.assertEqual(rage.capacity(s.character), 3)
        s, npc = combat()
        self.assertEqual(cp.apply_level_choices(s, cp.preview_level_up(s, 3), copy.deepcopy(THREE))['status'], 'applied')
        rage.activate(s); s.advance_campaign_time(599, 'combat_round', source='barbarian4:hardcap')
        old = copy.deepcopy(s.world_state['rage_v1'])
        advance(self, s)
        self.assertEqual(s.world_state['rage_v1'], old)
        self.assertTrue(rage.active(s))
        records = s.world_state['combat']['participant_records']
        player = next(r for r in records if r['id'] == 'player')
        self.assertEqual((player['current_hp'], player['max_hp'], player['armor_class']), (41, 45, 16))
        s.advance_campaign_time(1, 'combat_round', source='barbarian4:hardcap-end')
        self.assertFalse(rage.active(s))

    def test_strict_retained_levels_and_no_bare_forged_four(self):
        s = selected_three(self, raw=5); advance(self, s)
        self.assertTrue(cp.berserker_eligible(s.character))
        for raw, applied in ((3, 4), (True, 4), ('4', 4), (4, True), (4, '4'), (4, 5)):
            c = copy.deepcopy(s.character); c.update(level=raw, progression_level=applied)
            self.assertFalse(cp.berserker_eligible(c), (raw, applied))
            with self.assertRaises(ValueError): rage.validate(s.world_state, c, 4)
        for missing in ('asi_choices', 'primal_knowledge_choice', 'subclass_id'):
            c = copy.deepcopy(s.character); c.pop(missing)
            self.assertFalse(cp.berserker_eligible(c), missing)
            with self.assertRaises(ValueError): rage.validate(s.world_state, c, 4)

    def test_save_offsets_and_real_int_cha_wis_checks_update_not_dex_or_npcs(self):
        for ability, skill, expected in (('intelligence', 'Arcana', 1), ('charisma', 'Deception', 3), ('wisdom', 'Insight', 2)):
            s = selected_three(self)
            for a in ABILITIES: s.character['saving_throw_mods'][a] += 7
            old = copy.deepcopy(s.character); npcs = copy.deepcopy(s.world_state['npcs'])
            s.character['passive_perception'] = 999
            advance(self, s, {ability: 2})
            self.assertNotIn('passive_perception', s.character)
            for a in ABILITIES:
                self.assertEqual(s.character['saving_throw_mods'][a], old['saving_throw_mods'][a] + (1 if a == ability else 0))
            self.assertEqual(s.character['dexterity'], old['dexterity'])
            self.assertEqual(s.character.get('initiative'), old.get('initiative'))
            self.assertEqual(s.world_state['npcs'], npcs)
            with patch('game.roll_d20', return_value=10):
                c = s.character
                check = game.perform_skill_check(skill, 10, c['modifiers'], c['proficient_skills'], c['proficiency_bonus'], session=s)
            self.assertEqual((check['modifier'], check['total']), (expected, 10 + expected))


    def test_real_strength_save_keeps_offsets_and_rage_advantage_at_four(self):
        from api.tests.test_roadmap_c10_frenzy import FrenzyTests
        s, npc = FrenzyTests().encounter()
        s.character['saving_throw_mods']['strength'] += 7
        old_npc = copy.deepcopy(npc)
        advance(self, s, {'strength': 2})
        self.assertEqual(npc, old_npc)
        with patch.object(s.rng, 'randint', side_effect=[5, 16]):
            result = attacks.save(s, 'player', ['strength'], 20)
        self.assertEqual(result['raw_rolls'], [5, 16])
        self.assertEqual(result['modifier_breakdown']['ability_modifier'], 0)
        self.assertEqual(result['total_modifier'], 9)  # STR0 + proficient2 + retained extra7
        self.assertEqual(result['total'], 25)

    def test_real_passive_perception_uses_new_wisdom_without_roll_or_cache(self):
        import exploration
        import local_adventure_catalog as catalog
        for apply_asi, expected in ((False, []), (True, ['stone_secret', 'stone_wire'])):
            s = selected_three(self, scores={'wisdom': 14})
            s.character['passive_perception'] = 999  # creation hint must not authorize notice
            if apply_asi:
                advance(self, s, {'wisdom': 2})
            exploration.resolve_command(s, '/explore begin')
            # Unit-only position fixture; this test does not certify a travel path.
            s.world_state['location'] = catalog.ENTRY
            rng = s.rng.getstate()
            with patch('game.roll_d20', side_effect=AssertionError('Passive notice cannot roll')):
                self.assertEqual(len(exploration.notice_passively(s)), len(expected))  # literal DC15, passive14→15
            self.assertEqual(s.world_state[catalog.KEY]['discoveries'], expected)
            self.assertEqual(s.rng.getstate(), rng)


    def test_unpaid_base_changes_hp_but_never_reopens_or_rewrites_hit_die_window(self):
        s = selected_three(self, raw=3)
        s._apply_player_damage(15, took_damage=True)
        s.resolve_species_trait_action('short_rest')
        with patch.object(s.rng, 'randint', return_value=1): hit_dice.spend(s, s.heal_player)
        before = copy.deepcopy(s.character['hit_dice']); hp = s.character['current_hp']
        self.assertTrue(hit_dice.window_open(s))
        advance(self, s)
        self.assertEqual(s.character['hit_dice'], before)
        self.assertEqual(s.character['current_hp'], hp + 9)
        self.assertEqual((hit_dice.total(s.character), hit_dice.remaining(s.character)), (4, 3))
        self.assertFalse(hit_dice.window_open(s))


    def test_bare_four_numeric_claim_is_not_admitted_by_preview_apply_or_save(self):
        for missing in (None, 'primal_knowledge_choice', 'subclass_id'):
            s = selected_three(self)
            preview = cp.preview_level_up(s, 4)
            self.assertEqual(preview['status'], 'ready', preview)
            s.character['progression_level'] = 4  # forged applied claim, no selected ASI
            if missing: s.character.pop(missing)
            before = s._capture_runtime_snapshot()
            self.assertEqual(cp.preview_level_up(s, 4)['status'], 'blocked')
            self.assertEqual(cp.apply_level_choices(s, preview, choose({'strength': 2}))['status'], 'rejected')
            with self.assertRaises(ValueError): cp.validate_saved(s.character, s.world_state)
            with self.assertRaises(CampaignValidationError): serialize_campaign_payload(s)
            self.assertEqual(s._capture_runtime_snapshot(), before)
