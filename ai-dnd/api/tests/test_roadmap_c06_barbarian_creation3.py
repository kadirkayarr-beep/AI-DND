"""Core-only selected Berserker start3 (Task 1 of the start3 plan). Source values: PHB PDF 50-52 via the accepted earned3 owners.

Everything runs through the real create_at_level -> configure_character -> preview/apply steps 2 and 3 (no stand-in).
Human bonus Tough is NOT excluded: the staged Tough per-level fix makes its HP exact (PHB Tough, PDF 201).
"""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import hit_dice
from api.tests.test_roadmap_c06_barbarian import barbarian, spec
from api.tests.test_roadmap_c06_starting_xp import create as create_sorcerer

PICK = {'subclass_id': 'berserker', 'primal_knowledge_skill': 'Survival'}
CHOICES = {'2': {}, '3': PICK}


def create_three(session=None, request=None, choices=None):
    session = barbarian() if session is None else session
    try:
        cp.create_at_level(session, request or spec(), 3, copy.deepcopy(choices or CHOICES))
    except ValueError as error:
        raise AssertionError(f'valid core Barbarian3 creation rejected: {error}') from error
    return session


class BarbarianStartThreeTests(unittest.TestCase):
    def test_exact_selected_start_three_uses_real_creation_and_progression(self):
        prior = list(barbarian().character['proficient_skills'])
        session = create_three()
        c = session.character
        self.assertEqual((c['level'], c['progression_level'], c['xp'], c['proficiency_bonus']), (3, 3, 900, 2))
        self.assertEqual((c['max_hp'], c['current_hp']), (32, 32))
        self.assertEqual((hit_dice.total(c), hit_dice.die_size(c), hit_dice.spent(c)), (3, 12, 0))
        self.assertEqual(c['subclass_id'], 'berserker')
        self.assertEqual(c['proficient_skills'], [*prior, 'Survival'])
        self.assertEqual(c['primal_knowledge_choice'],
                         {'class_level': 3, 'skill': 'Survival', 'prior_proficient_skills': prior})
        self.assertEqual(c['spell_slots_remaining'], {'1': 0})
        self.assertEqual((c['spells'], c['cantrips']), ([], []))
        self.assertNotIn('spellcasting_v1', session.world_state)
        self.assertNotIn('metamagic', c)
        self.assertEqual(session.world_state.get('xp_awarded_event_ids', []), [])
        self.assertEqual(session.world_state['rage_v1']['remaining'], 3)

    def test_human_bonus_tough_is_not_excluded_and_hit_points_are_exact(self):
        request = spec()
        request.update(species_bonus_feat='Tough', species_bonus_skills=['Persuasion'])
        session = create_three(request=request)
        # d12 + CON 2 + Tough 2 at level 1, then 7 + 2 + Tough 2 on each of levels 2 and 3 = 16 + 11 + 11.
        self.assertEqual((session.character['max_hp'], session.character['current_hp']), (38, 38))

    def test_dwarf_and_background_tough_hit_points_are_exact(self):
        dwarf = spec()
        dwarf.update(species='Dwarf', race='Dwarf', proficient_skills=['Athletics', 'Perception', 'Sleight of Hand', 'Stealth'])
        self.assertEqual(create_three(request=dwarf).character['max_hp'], 35)  # 12+2+1, then 7+2+1 twice
        farmer = copy.deepcopy(dwarf)
        farmer.update(background='Farmer', background_ability_bonuses={'strength': 2, 'constitution': 1},
                      proficient_skills=['Athletics', 'Perception', 'Animal Handling', 'Nature'])
        session = create_three(request=farmer, choices={'2': {}, '3': {**PICK, 'primal_knowledge_skill': 'Intimidation'}})
        # Farmer's origin feat Tough: 17 at level 1, then 12 on each of levels 2 and 3.
        self.assertEqual((session.character['max_hp'], session.character['current_hp']), (41, 41))

    def test_wrong_bundle_never_creates_a_partial_character(self):
        cases = [None, [], '3', {}, {'2': {}}, {'3': PICK}, {'2': None, '3': PICK}, {'2': {'x': 1}, '3': PICK},
                 {'2': {}, '3': None}, {'2': {}, '3': {}}, {'2': {}, '3': {'subclass_id': 'berserker'}},
                 {'2': {}, '3': {**PICK, 'extra': 1}}, {'2': {}, '3': {**PICK, 'subclass_id': 'wild_heart'}},
                 {'2': {}, '3': {**PICK, 'primal_knowledge_skill': True}},
                 {'2': {}, '3': {**PICK, 'primal_knowledge_skill': 'Athletics'}},
                 {'2': {}, '3': {**PICK, 'primal_knowledge_skill': 'Nonsense'}}, {**CHOICES, '4': {}}]
        session = barbarian()
        for value in cases:
            with self.subTest(choices=value):
                before = session._capture_runtime_snapshot()
                with self.assertRaises(ValueError):
                    cp.create_at_level(session, spec(), 3, value)
                self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_catalog_keeps_verified_one_and_two_when_source_row_three_is_wrong(self):
        source = cp.table('Barbarian')
        for broken in ({**source['levels']['3'], 'features': ['Barbarian Subclass']},
                       {**source['levels']['3'], 'rages': 4}, {**source['levels']['3'], 'slots': {'1': 2}}, None):
            levels = {**source['levels'], '3': broken}
            with self.subTest(row=broken), patch.object(cp, 'table', return_value={**source, 'levels': levels}):
                options = cp.barbarian_starting_creation_options()
                self.assertEqual(options['supported_starting_levels'], [1, 2])
                self.assertNotIn('level_3', options)

    def test_refusals_name_the_level_and_a_stray_level_three_never_reaches_start_two(self):
        session = barbarian()
        with self.assertRaisesRegex(ValueError, 'barbarian_level_three_choices_required'):
            cp.create_at_level(session, spec(), 3, {'2': {}})
        with self.assertRaisesRegex(ValueError, 'barbarian_level_two_choices_required'):
            cp.create_at_level(session, spec(), 2, {'2': {}, '3': PICK})

    def test_start_levels_above_five_stay_unsupported_and_four_five_need_their_own_bundles(self):
        # Start 4 and 5 are supported now (test_roadmap_c06_barbarian_creation45); a start-3 bundle never reaches them.
        session = barbarian()
        for level, reason in ((4, 'barbarian_level_four_choices_required'), (5, 'barbarian_level_five_choices_required'),
                              (6, 'progression_level_not_supported')):
            with self.subTest(level=level):
                before = session._capture_runtime_snapshot()
                with self.assertRaisesRegex(ValueError, reason):
                    cp.create_at_level(session, spec(), level, {'2': {}, '3': PICK})
                self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_recreation_from_a_populated_sorcerer_replaces_it_cleanly(self):
        session = create_sorcerer(3)
        create_three(session)
        c = session.character
        self.assertEqual((c['class'], c['level'], c['progression_level']), ('Barbarian', 3, 3))
        self.assertNotIn('spellcasting_v1', session.world_state)
        self.assertNotIn('metamagic', c)
        self.assertEqual(c['subclass_id'], 'berserker')

    def test_late_failure_after_real_step_three_restores_the_populated_session(self):
        session = create_sorcerer(3)
        session.messages.append({'role': 'user', 'content': 'sentinel'})
        before = session._capture_runtime_snapshot()
        containers = (session.character, session.world_state, session.messages)
        real = cp.apply_level_choices
        applied = []

        def fail_after_apply(*args):
            result = real(*args)
            self.assertEqual(result['status'], 'applied')
            applied.append(args[0].character['progression_level'])
            if len(applied) == 2:
                raise RuntimeError('synthetic post-apply failure')
            return result

        with patch.object(cp, 'apply_level_choices', side_effect=fail_after_apply):
            with self.assertRaisesRegex(RuntimeError, 'synthetic post-apply failure'):
                cp.create_at_level(session, spec(), 3, copy.deepcopy(CHOICES))
        self.assertEqual(applied, [2, 3])
        self.assertEqual(session._capture_runtime_snapshot(), before)
        for old, current in zip(containers, (session.character, session.world_state, session.messages)):
            self.assertIs(old, current)

    def test_catalog_declares_start_three_with_source_vocabulary_only(self):
        options = cp.barbarian_starting_creation_options()
        self.assertEqual(options['supported_starting_levels'], [1, 2, 3, 4, 5])
        three = options['level_3']
        self.assertEqual(three['subclass_options'], [{'id': 'berserker', 'name': 'Path of the Berserker'}])
        self.assertEqual(len(three['primal_knowledge_skill_options']), 6)
        self.assertNotIn('unsupported_species_bonus_feats', three)
        options['level_3']['subclass_options'].clear()
        self.assertTrue(cp.barbarian_starting_creation_options()['level_3']['subclass_options'])


if __name__ == '__main__':
    unittest.main()
