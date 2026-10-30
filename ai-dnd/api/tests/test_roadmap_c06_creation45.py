"""Selected higher starts: actual creation, no XP award and no class-complete claim."""
import copy
import unittest
from unittest.mock import patch
import game
import xp
import character_progression as cp
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_level3 import TWO, choices
from api.tests.test_roadmap_c06_level4_con import PICK, RECORD
from api.tests.test_roadmap_c06_level5 import FIVE, four
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session


def steps(level):
    result = {'2': copy.deepcopy(TWO), '3': choices(), '4': copy.deepcopy(PICK)}
    if level == 5: result['5'] = copy.deepcopy(FIVE)
    return result


class CreationFourFiveTests(unittest.TestCase):
    def create(self, level):
        s = game.create_session(seed=42)
        try:
            with patch.object(xp, 'apply_xp', side_effect=AssertionError('Creation must not award XP')):
                cp.create_at_level(s, copy.deepcopy(SPEC), level, steps(level))
        except ValueError as error:
            self.fail('Valid selected creation blocked: ' + str(error))
        return s

    def test_real_creation_full_final_hp_threshold_xp_unspent_pools_no_awards(self):
        for level, hp, xp_value, version, slots, prepared in ((4, 30, 2700, 4, {'1':4,'2':3}, 7), (5, 37, 6500, 6, {'1':4,'2':3,'3':2}, 9)):
            with self.subTest(level=level):
                s = self.create(level)
                self.assertEqual((s.character['level'], s.character['progression_level'], s.character['xp']), (level, level, xp_value))
                self.assertEqual((s.character['current_hp'], s.character['max_hp']), (hp, hp))
                self.assertEqual(s.world_state['spellcasting_v1']['slots'], slots)
                self.assertEqual((len(s.character['cantrips']), len(s.character['spells'])), (5, prepared))
                self.assertEqual(s.character['asi_choices'], RECORD)
                self.assertEqual(s.character['constitution'], 16)
                self.assertEqual(s.character['proficiency_bonus'], 2 if level == 4 else 3)
                self.assertEqual(s.character['saving_throw_mods']['constitution'], 5 if level == 4 else 6)
                self.assertEqual(s.world_state.get('xp_awarded_event_ids', []), [])
                self.assertIsNone(s._xp_level_up)
                self.assertEqual(s._persisted_engine_format, version)
                self.assertNotIn('hit_dice', s.character)
                for _ in range(2):
                    fresh = game.create_session(seed=99); restore_campaign_session(fresh, serialize_campaign_payload(s)); s = fresh
                self.assertEqual((s.character['current_hp'], s.character['max_hp'], s._persisted_engine_format), (hp, hp, version))

    def test_existing_advancement_still_does_not_heal_asi(self):
        s = four()
        self.assertEqual((s.character['current_hp'], s.character['max_hp']), (26, 30))
        fresh = self.create(4)
        self.assertEqual((fresh.character['current_hp'], fresh.character['max_hp']), (30, 30))

    def test_late_step_five_refusal_rolls_back_exact_old_runtime_and_format(self):
        s = four(); s._persisted_engine_format = 5
        s.character['current_hp'] = 1
        before = s._capture_runtime_snapshot(); containers = (s.character, s.world_state, s.messages)
        invalid = steps(5); invalid['5'] = {'prepared_spells':['Fog Cloud', 'not-a-spell']}
        with patch.object(cp, 'apply_level_choices', wraps=cp.apply_level_choices) as apply:
            with self.assertRaises(ValueError): cp.create_at_level(s, copy.deepcopy(SPEC), 5, invalid)
        self.assertEqual([c.args[1]['to_level'] for c in apply.call_args_list], [2,3,4,5])
        self.assertEqual(s._capture_runtime_snapshot(), before)
        for previous,current in zip(containers,(s.character,s.world_state,s.messages)): self.assertIs(previous,current)

    def test_recreation_initializes_format_but_preserves_existing_award_history(self):
        for old_version in (1,2,3,4,5,6):
            for level,version in ((4,4),(5,6)):
                s = four(); s._persisted_engine_format = old_version
                s.character['hit_dice']={'spent':2,'window_second':None,'hp':None}
                old_ids=copy.deepcopy(s.world_state['xp_awarded_event_ids'])
                cp.create_at_level(s,copy.deepcopy(SPEC),level,steps(level))
                self.assertEqual(s._persisted_engine_format,version)
                self.assertEqual(s.world_state['xp_awarded_event_ids'],old_ids)
                self.assertEqual(s.character['asi_choices'],RECORD)
                self.assertNotIn('hit_dice',s.character)
                self.assertIsNone(s._xp_level_up, 'New character must not announce old character XP awards')

    def test_final_admission_failure_rolls_back_format_absence_and_old_history(self):
        for present in (False,True):
            s = four()
            if present: s._persisted_engine_format=2
            else: s.__dict__.pop('_persisted_engine_format')
            before=s._capture_runtime_snapshot()
            # Synthetic final admission error after XP and full-HP finalization.
            def fail(payload):
                self.assertEqual((payload['version'],payload['player']['xp'],payload['player']['current_hp']),(6,6500,37))
                raise ValueError('synthetic final creation admission')
            with patch.object(s,'_validate_save_payload',side_effect=fail):
                with self.assertRaises(ValueError):cp.create_at_level(s,copy.deepcopy(SPEC),5,steps(5))
            self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_expanded_catalog_fails_closed_for_incompatible_cantrip_or_metamagic_rows(self):
        for mode in ('four-cantrips','five-cantrips','four-metamagic','five-metamagic','no-cantrip-options'):
            table=copy.deepcopy(cp.table('Sorcerer'))
            from api.dnd_2024_rules import SPELLS_CATALOG
            catalog=copy.deepcopy(SPELLS_CATALOG['Sorcerer'])
            if mode=='four-cantrips':table['levels']['4']['cantrips']=6
            if mode=='five-cantrips':table['levels']['5']['cantrips']=6
            if mode=='four-metamagic':table['metamagic_choice_counts']['4']=1
            if mode=='five-metamagic':table['metamagic_choice_counts']['5']=1
            if mode=='no-cantrip-options':catalog['cantrips']=[]
            with patch.object(cp,'table',return_value=table),patch.dict(SPELLS_CATALOG,{'Sorcerer':catalog}):
                self.assertIsNone(cp.sorcerer_starting_creation_options(),mode)

    def test_new_start_shape_bounds_and_other_classes_reject_without_mutation(self):
        for level, bundle, class_name in ((6,steps(5),'Sorcerer'), (True,steps(4),'Sorcerer'),
                                         (4,[], 'Sorcerer'), (4,None,'Sorcerer'),
                                         (4,{**steps(4),'5':{}},'Sorcerer'),
                                         (5,steps(4),'Sorcerer'), (4,{**steps(4),'4':None},'Sorcerer'),
                                         (4,steps(4),'Barbarian'), (5,steps(5),'Wizard')):
            s=four(); before=s._capture_runtime_snapshot(); spec=copy.deepcopy(SPEC);spec['character_class']=class_name
            with self.assertRaises(ValueError):cp.create_at_level(s,spec,level,bundle)
            self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_shared_numeric_owner_initialization_then_real_award_does_not_duplicate_hp(self):
        s=self.create(5); before=copy.deepcopy(s.character)
        receipt=s._receive_xp_award(xp.apply_xp,s.character,s.world_state,1,'quest:after-new-start')
        self.assertEqual((receipt['previous_level'],receipt['new_level'],receipt['xp_gained'],receipt['hit_points_gained']),(5,5,1,0))
        self.assertEqual((s.character['current_hp'],s.character['max_hp'],s.character['xp']),(37,37,6501))
        self.assertEqual(s.character['saving_throw_mods'],before['saving_throw_mods'])
        self.assertEqual(s.world_state['xp_awarded_event_ids'],['quest:after-new-start'])
