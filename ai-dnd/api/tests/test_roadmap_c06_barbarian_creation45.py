"""Core-only selected Berserker start 4 and 5. Source values: PHB PDF 51 (Barbarian Features table rows 4 and 5), PDF 40/42
(Character Advancement XP 2,700 / 6,500; Starting at Higher Levels: begin with the minimum XP of the starting level) and PDF 41
(Con modifier increase adds 1 HP per level attained); ASI feat text PDF 201/52.

Everything runs through the real create_at_level -> configure_character -> preview/apply steps 2..5 (no stand-in). A start-4/5
creation must equal the earned path (same owners), differing only by creation initialisation (full HP, no award receipts).
Negative cases pin the refusal REASON so they cannot pass for an unrelated rejection.
"""
import copy
import unittest
from unittest.mock import patch

import game
import xp
import hit_dice
import character_progression as cp
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.tests.test_roadmap_c06_barbarian import barbarian, spec
from api.tests.test_roadmap_c06_nondex_asi import PATTERNS
from api.tests.test_roadmap_c06_barbarian_level4 import selected_three, advance as advance_four
from api.tests.test_roadmap_c06_barbarian_level5 import pending_five, apply_five
from api.tests.test_roadmap_c06 import SPEC as SORCERER_SPEC
from api.tests.test_roadmap_c06_creation45 import steps as sorcerer_steps

PICK = {'subclass_id': 'berserker', 'primal_knowledge_skill': 'Survival'}


def asi(increase):
    return {'asi': {'feat': 'Ability Score Improvement', 'increase': copy.deepcopy(increase)}}


def bundle(level, increase=None):
    value = {'2': {}, '3': copy.deepcopy(PICK), '4': asi({'strength': 2} if increase is None else increase)}
    if level == 5:
        value['5'] = {}
    return value


def create(level, session=None, request=None, increase=None):
    session = barbarian() if session is None else session
    try:
        with patch.object(xp, 'apply_xp', side_effect=AssertionError('Creation must not award XP')):
            cp.create_at_level(session, request or spec(), level, bundle(level, increase))
    except ValueError as error:
        raise AssertionError(f'valid core Barbarian{level} creation rejected: {error}') from error
    return session


def create_sorcerer(level):
    session = game.create_session(seed=42)
    cp.create_at_level(session, copy.deepcopy(SORCERER_SPEC), level, sorcerer_steps(level))
    return session


def roundtrip(session, seed=19):
    fresh = game.create_session(seed=seed)
    restore_campaign_session(fresh, serialize_campaign_payload(session))
    return fresh


class BarbarianStartFourFiveTests(unittest.TestCase):
    def test_start_four_exact_state_from_real_owners(self):
        prior = list(barbarian().character['proficient_skills'])
        s = create(4)
        c = s.character
        self.assertEqual((c['level'], c['progression_level'], c['xp'], c['proficiency_bonus']), (4, 4, 2700, 2))
        # Level 1 d12+CON 2 = 14, then 7+2 on each of levels 2, 3 and 4 (Strength ASI changes no HP).
        self.assertEqual((c['max_hp'], c['current_hp']), (41, 41))
        self.assertEqual(c['strength'], 10)
        self.assertEqual(c['asi_choices'], [{'class_level': 4, 'feat': 'Ability Score Improvement', 'increase': {'strength': 2}}])
        self.assertEqual(c['subclass_id'], 'berserker')
        self.assertEqual(c['proficient_skills'], [*prior, 'Survival'])
        self.assertEqual((hit_dice.total(c), hit_dice.die_size(c), hit_dice.spent(c)), (4, 12, 0))
        self.assertEqual(s.world_state['rage_v1']['remaining'], 3)
        self.assertNotIn('spellcasting_v1', s.world_state)
        self.assertNotIn('metamagic', c)
        self.assertEqual((c['spells'], c['cantrips']), ([], []))
        self.assertEqual(s.world_state.get('xp_awarded_event_ids', []), [])
        self.assertIsNone(s._xp_level_up)
        self.assertEqual(s._persisted_engine_format, 4)
        self.assertEqual(cp.attacks_per_attack_action(c), 1)  # level-5 features do not exist yet
        self.assertEqual(cp.fast_movement_bonus_ft(c, s.world_state), 0)

    def test_start_five_exact_state_with_level_five_features(self):
        s = create(5)
        c = s.character
        self.assertEqual((c['level'], c['progression_level'], c['xp'], c['proficiency_bonus']), (5, 5, 6500, 3))
        self.assertEqual((c['max_hp'], c['current_hp']), (50, 50))
        self.assertEqual((hit_dice.total(c), hit_dice.die_size(c), hit_dice.spent(c)), (5, 12, 0))
        self.assertEqual(s.world_state['rage_v1']['remaining'], 3)  # table: 3 Rages at level 5, no refill invented
        self.assertEqual(s._persisted_engine_format, 6)
        self.assertIsNone(s._xp_level_up)
        self.assertEqual(s.world_state.get('xp_awarded_event_ids', []), [])
        self.assertEqual(c['saving_throw_mods']['strength'], 3)  # STR 10 mod 0 + Barbarian save proficiency +PB 3
        self.assertTrue(cp.barbarian_level_five_applied(c))
        self.assertEqual(cp.attacks_per_attack_action(c), 2)
        self.assertEqual(cp.fast_movement_bonus_ft(c, s.world_state), 10)
        import action_economy as economy
        self.assertEqual(economy.speed(s, 'player'), 40)

    def test_creation_equals_the_earned_path_except_initialisation(self):
        created = create(5, increase={'constitution': 2})
        earned = pending_five(self)
        apply_five(self, earned)
        for key in ('current_hp',):
            earned.character[key] = earned.character['max_hp']
        self.assertEqual({k: v for k, v in created.character.items() if k not in ('inventory',)},
                         {k: v for k, v in earned.character.items() if k not in ('inventory',)})
        self.assertEqual(created.world_state['rage_v1'], earned.world_state['rage_v1'])
        self.assertEqual(created.world_state.get('worn_armor_v1'), earned.world_state.get('worn_armor_v1'))

    def test_all_fifteen_asi_patterns_hit_points_and_scores_at_start_four_and_five(self):
        for level in (4, 5):
            for increase in PATTERNS:
                with self.subTest(level=level, increase=increase):
                    base = barbarian().character
                    c = create(level, increase=increase).character
                    delta = ((base['constitution'] + increase.get('constitution', 0) - 10) // 2
                             - (base['constitution'] - 10) // 2)
                    expected = 32 + 9 + 4 * delta  # level 4: base gain with the old modifier + 1 per level attained
                    if level == 5:
                        expected += 7 + 2 + delta
                    self.assertEqual((c['max_hp'], c['current_hp']), (expected, expected))
                    for ability, amount in increase.items():
                        self.assertEqual(c[ability], base[ability] + amount)
                    self.assertEqual(c['asi_choices'][0]['increase'], increase)

    def test_constitution_asi_raises_modifier_hp_retroactively_and_armor_class(self):
        four = create(4, increase={'constitution': 2}).character
        self.assertEqual((four['constitution'], four['max_hp'], four['armor_class']), (16, 45, 16))
        five = create(5, increase={'constitution': 2}).character
        self.assertEqual((five['max_hp'], five['current_hp'], five['armor_class']), (55, 55, 16))

    def test_tough_origin_and_species_hit_points_are_exact(self):
        human = spec()
        human.update(species_bonus_feat='Tough', species_bonus_skills=['Persuasion'])
        # d12+2+Tough 2 = 16 at level 1, then 7+2+2 = 11 per level.
        self.assertEqual(create(4, request=human).character['max_hp'], 16 + 33)
        self.assertEqual(create(5, request=human).character['max_hp'], 16 + 44)
        dwarf = spec()
        dwarf.update(species='Dwarf', race='Dwarf', proficient_skills=['Athletics', 'Perception', 'Sleight of Hand', 'Stealth'])
        self.assertEqual(create(4, request=dwarf).character['max_hp'], 15 + 30)  # 12+2+1, then 7+2+1 per level
        self.assertEqual(create(5, request=dwarf).character['max_hp'], 15 + 40)
        farmer = copy.deepcopy(dwarf)
        farmer.update(background='Farmer', background_ability_bonuses={'strength': 2, 'constitution': 1},
                      proficient_skills=['Athletics', 'Perception', 'Animal Handling', 'Nature'])
        picks = bundle(5)
        picks['3']['primal_knowledge_skill'] = 'Intimidation'
        s = barbarian()
        cp.create_at_level(s, farmer, 5, picks)  # Dwarf + Farmer Tough: 12 per level, 17 at level 1
        self.assertEqual((s.character['max_hp'], s.character['current_hp']), (17 + 48, 17 + 48))

    def test_saved_and_restored_repeatedly(self):
        for level, version in ((4, 4), (5, 6)):
            with self.subTest(level=level):
                s = create(level)
                for _ in range(2):
                    payload = serialize_campaign_payload(s)
                    s = roundtrip(s)
                    self.assertEqual(serialize_campaign_payload(s), payload)
                self.assertEqual((s.character['level'], s.character['progression_level'], s._persisted_engine_format),
                                 (level, level, version))
                self.assertEqual(s.character['current_hp'], s.character['max_hp'])

    def test_wrong_bundle_never_creates_a_partial_character_and_names_its_reason(self):
        ok4, ok5 = bundle(4), bundle(5)
        cases = [
            (4, None, 'barbarian_level_four_choices_required'), (4, [], 'barbarian_level_four_choices_required'),
            (4, {}, 'barbarian_level_four_choices_required'),
            (4, {k: v for k, v in ok4.items() if k != '4'}, 'barbarian_level_four_choices_required'),
            (4, {k: v for k, v in ok4.items() if k != '2'}, 'barbarian_level_four_choices_required'),
            (4, {**ok4, '5': {}}, 'barbarian_level_four_choices_required'),
            (4, {**ok4, '4': None}, 'barbarian_level_four_choices_required'),
            (4, {**ok4, '4': {}}, 'barbarian_level_four_choices_required'),
            (4, {**ok4, '4': {**asi({'strength': 2}), 'extra': 1}}, 'barbarian_level_four_choices_required'),
            (4, {**ok4, '4': {'asi': None}}, 'selected_asi_not_supported'),
            (4, {**ok4, '4': {'asi': {'feat': 'Ability Score Improvement'}}}, 'selected_asi_not_supported'),
            (4, {**ok4, '4': {'asi': {'feat': 'Tough', 'increase': {'strength': 2}}}}, 'selected_asi_not_supported'),
            (4, {**ok4, '4': asi({'dexterity': 2})}, 'selected_asi_not_supported'),
            (4, {**ok4, '4': asi({'strength': 3})}, 'selected_asi_not_supported'),
            (4, {**ok4, '4': asi({'strength': 1, 'wisdom': 1, 'charisma': 1})}, 'selected_asi_not_supported'),
            (4, {**ok4, '4': asi({})}, 'selected_asi_not_supported'),
            (4, {**ok4, '4': asi({'strength': True})}, 'selected_asi_not_supported'),
            (4, {**ok4, '3': {**PICK, 'primal_knowledge_skill': 'Athletics'}}, 'primal_knowledge_skill_invalid'),
            (4, {**ok4, '2': {'x': 1}}, 'barbarian_level_four_choices_required'),
            (5, ok4, 'barbarian_level_five_choices_required'),
            (5, {k: v for k, v in ok5.items() if k != '5'}, 'barbarian_level_five_choices_required'),
            (5, {**ok5, '5': None}, 'barbarian_level_five_choices_required'),
            (5, {**ok5, '5': {'prepared_spells': []}}, 'barbarian_level_five_choices_required'),
            (5, {**ok5, '6': {}}, 'barbarian_level_five_choices_required'),
            (5, {**ok5, '4': {}}, 'barbarian_level_five_choices_required'),
            (5, {**ok5, '4': asi({'dexterity': 2})}, 'selected_asi_not_supported'),
            (6, ok5, 'progression_level_not_supported'), (True, ok4, 'invalid_target_level'),
        ]
        session = barbarian()
        for level, value, reason in cases:
            with self.subTest(level=level, reason=reason, choices=value):
                before = session._capture_runtime_snapshot()
                with self.assertRaisesRegex(ValueError, reason):
                    cp.create_at_level(session, spec(), level, copy.deepcopy(value))
                self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_only_the_two_supported_classes_and_levels_reach_the_new_steps(self):
        for class_name in ('Wizard', 'Fighter'):
            session = barbarian()
            before = session._capture_runtime_snapshot()
            request = spec(); request['character_class'] = class_name
            with self.assertRaisesRegex(ValueError, 'starting_level_class_not_supported'):
                cp.create_at_level(session, request, 4, bundle(4))
            self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_late_failure_after_each_real_step_restores_the_populated_session(self):
        for level, fail_on in ((4, 3), (5, 3), (5, 4)):
            with self.subTest(level=level, fail_on=fail_on):
                session = create_sorcerer(5)
                session.messages.append({'role': 'user', 'content': 'sentinel'})
                before = session._capture_runtime_snapshot()
                containers = (session.character, session.world_state, session.messages)
                real = cp.apply_level_choices
                applied = []

                def fail_after_apply(*args):
                    result = real(*args)
                    self.assertEqual(result['status'], 'applied')
                    applied.append(args[0].character['progression_level'])
                    if len(applied) == fail_on:
                        raise RuntimeError('synthetic post-apply failure')
                    return result

                with patch.object(cp, 'apply_level_choices', side_effect=fail_after_apply):
                    with self.assertRaisesRegex(RuntimeError, 'synthetic post-apply failure'):
                        cp.create_at_level(session, spec(), level, bundle(level))
                self.assertEqual(applied, list(range(2, 2 + fail_on)))
                self.assertEqual(session._capture_runtime_snapshot(), before)
                for old, current in zip(containers, (session.character, session.world_state, session.messages)):
                    self.assertIs(old, current)

    def test_final_admission_failure_rolls_back_format_absence_and_old_history(self):
        for level, version, hp in ((4, 4, 41), (5, 6, 50)):
            for present in (False, True):
                with self.subTest(level=level, present=present):
                    s = create_sorcerer(4)
                    if present:
                        s._persisted_engine_format = 5  # Barbarian creation itself requires a format in 4-6
                    else:
                        s.__dict__.pop('_persisted_engine_format')
                    before = s._capture_runtime_snapshot()

                    real = s._validate_save_payload
                    reached = []

                    def fail(payload):
                        if payload['player'].get('xp') != {4: 2700, 5: 6500}[level]:
                            return real(payload)  # the real step owners admit their own intermediate states
                        self.assertEqual((payload['version'], payload['player']['current_hp'], payload['player']['class']),
                                         (version, hp, 'Barbarian'))
                        reached.append(True)
                        raise ValueError('synthetic final creation admission')

                    with patch.object(s, '_validate_save_payload', side_effect=fail):
                        with self.assertRaises(ValueError):
                            cp.create_at_level(s, spec(), level, bundle(level))
                    self.assertTrue(reached)
                    self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_recreation_replaces_other_class_and_lower_barbarian_state_but_keeps_award_history(self):
        for old in (create_sorcerer(5), create(5, increase={'constitution': 2})):
            for level, version in ((4, 4), (5, 6), (3, None)):
                with self.subTest(old=old.character['class'], level=level):
                    s = old
                    if 'quest:before-recreate' not in s.world_state.setdefault('xp_awarded_event_ids', []):
                        s.world_state['xp_awarded_event_ids'].append('quest:before-recreate')
                    s.character['hit_dice'] = {'spent': 2, 'window_second': None, 'hp': None}
                    if level == 3:
                        cp.create_at_level(s, spec(), 3, {'2': {}, '3': copy.deepcopy(PICK)})
                        self.assertNotIn('asi_choices', s.character)
                        self.assertEqual(s.world_state['rage_v1']['remaining'], 3)
                    else:
                        cp.create_at_level(s, spec(), level, bundle(level))
                        self.assertEqual(s._persisted_engine_format, version)
                        self.assertEqual(s.character['asi_choices'][0]['increase'], {'strength': 2})
                    self.assertEqual(s.character['class'], 'Barbarian')
                    self.assertNotIn('spellcasting_v1', s.world_state)
                    self.assertNotIn('metamagic', s.character)
                    self.assertNotIn('hit_dice', s.character)
                    self.assertIn('quest:before-recreate', s.world_state['xp_awarded_event_ids'])
                    if level >= 4:
                        self.assertIsNone(s._xp_level_up)

    def test_shared_numeric_owner_real_award_after_creation_does_not_duplicate_hp(self):
        s = create(5)
        before = copy.deepcopy(s.character)
        receipt = s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 1, 'quest:after-barbarian-start')
        self.assertEqual((receipt['previous_level'], receipt['new_level'], receipt['hit_points_gained']), (5, 5, 0))
        self.assertEqual((s.character['current_hp'], s.character['max_hp'], s.character['xp']), (50, 50, 6501))
        self.assertEqual(s.character['saving_throw_mods'], before['saving_throw_mods'])
        self.assertEqual(s.world_state['xp_awarded_event_ids'], ['quest:after-barbarian-start'])

    def test_created_start_four_earns_level_five_without_a_second_asi(self):
        s = create(4)
        receipt = s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 3800, 'quest:start-four-to-five')
        self.assertEqual((receipt['previous_level'], receipt['new_level']), (4, 5))
        self.assertEqual((s.character['level'], s.character['progression_level']), (5, 4))
        hp_before = s.character['max_hp']
        apply_five(self, s)
        c = s.character
        self.assertEqual((c['level'], c['progression_level'], c['proficiency_bonus']), (5, 5, 3))
        self.assertEqual(len(c['asi_choices']), 1)  # the single level-4 pick, not a second one
        self.assertEqual(c['max_hp'], hp_before)  # the class step repays no HP
        fresh = roundtrip(s)
        self.assertEqual((fresh.character['progression_level'], fresh.character['max_hp']), (5, hp_before))

    def test_created_start_five_cannot_advance_past_the_supported_ceiling(self):
        s = create(5)
        s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 7500, 'quest:start-five-to-six')
        # Enough XP for level 6, but the numeric level stays at the engine's supported ceiling.
        self.assertEqual((s.character['level'], s.character['progression_level'], s.character['xp']), (5, 5, 14000))
        before = s._capture_runtime_snapshot()
        preview = cp.preview_level_up(s, 6)
        self.assertEqual((preview['status'], preview.get('reason')), ('blocked', 'progression_level_not_supported'))
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_catalog_declares_four_and_five_with_source_vocabulary_only(self):
        options = cp.barbarian_starting_creation_options()
        self.assertEqual(options['supported_starting_levels'], [1, 2, 3, 4, 5])
        four, five = options['level_4'], options['level_5']
        self.assertEqual(four['supported_asi_choices'], [{'feat': 'Ability Score Improvement', 'increase': p} for p in PATTERNS])
        self.assertEqual(set(four), {'supported_asi_choices', 'effects_supported', 'effects_pending'})
        self.assertEqual(set(five), {'effects_supported', 'effects_pending'})
        self.assertIn('Extra Attack', ' '.join(five['effects_supported']))
        self.assertIn('Fast Movement', ' '.join(five['effects_supported']))
        for block in (four, five):
            self.assertIn('Higher-start equipment', ' '.join(block['effects_pending']))
        self.assertIn('Weapon Mastery', ' '.join(four['effects_pending']))
        options['level_4']['supported_asi_choices'].clear()
        self.assertTrue(cp.barbarian_starting_creation_options()['level_4']['supported_asi_choices'])  # detached copy

    def test_catalog_fails_closed_per_row_keeping_the_verified_prefix(self):
        source = cp.table('Barbarian')
        good3, good4, good5 = (source['levels'][n] for n in ('3', '4', '5'))
        broken_fours = [None, {**good4, 'features': ['Ability Score Improvement', 'Extra']}, {**good4, 'proficiency_bonus': 3},
                        {**good4, 'rages': 4}, {**good4, 'rage_damage': 3}, {**good4, 'weapon_mastery': 2},
                        {**good4, 'slots': {'1': 4}}, {**good4, 'proficiency_bonus': True}]
        for broken in broken_fours:
            levels = {**source['levels'], '4': broken}
            with self.subTest(row=4, broken=broken), patch.object(cp, 'table', return_value={**source, 'levels': levels}):
                options = cp.barbarian_starting_creation_options()
                self.assertEqual(options['supported_starting_levels'], [1, 2, 3])
                self.assertNotIn('level_4', options)
                self.assertNotIn('level_5', options)
        broken_fives = [None, {**good5, 'features': ['Extra Attack']}, {**good5, 'proficiency_bonus': 2},
                        {**good5, 'rages': 4}, {**good5, 'rage_damage': 3}, {**good5, 'weapon_mastery': 4},
                        {**good5, 'prepared_spells': 1}, {**good5, 'proficiency_bonus': True}]
        for broken in broken_fives:
            levels = {**source['levels'], '5': broken}
            with self.subTest(row=5, broken=broken), patch.object(cp, 'table', return_value={**source, 'levels': levels}):
                options = cp.barbarian_starting_creation_options()
                self.assertEqual(options['supported_starting_levels'], [1, 2, 3, 4])
                self.assertIn('level_4', options)
                self.assertNotIn('level_5', options)
        # A broken row 3 never lets a later row through (no gap in the advertised range).
        levels = {**source['levels'], '3': {**good3, 'rages': 4}}
        with patch.object(cp, 'table', return_value={**source, 'levels': levels}):
            options = cp.barbarian_starting_creation_options()
            self.assertEqual(options['supported_starting_levels'], [1, 2])
            self.assertNotIn('level_4', options)

    def test_catalog_hides_start_four_when_no_asi_family_is_available(self):
        with patch.object(cp, 'supported_asi_choices', return_value=[]):
            options = cp.barbarian_starting_creation_options()
        self.assertEqual(options['supported_starting_levels'], [1, 2, 3])
        self.assertNotIn('level_4', options)

    def test_earned_levels_four_and_five_are_unchanged_by_creation_support(self):
        s = selected_three(self, raw=4)
        advance_four(self, s)
        self.assertEqual((s.character['level'], s.character['progression_level']), (4, 4))


if __name__ == '__main__':
    unittest.main()
