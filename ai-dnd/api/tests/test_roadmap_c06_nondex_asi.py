"""Selected ordinary ASI family, PHB PDF201 literal pattern oracles. DEX armor rules: test_roadmap_c06_dex_asi."""
import copy
import unittest
from unittest.mock import patch
import game
import character_progression as cp
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_starting_xp import create
from api.tests.test_roadmap_c06_creation45 import steps
from api.tests.test_roadmap_c06_level4_con import PICK
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session

PATTERNS = [
 {'strength':2}, {'dexterity':2}, {'constitution':2}, {'intelligence':2}, {'wisdom':2}, {'charisma':2},
 {'strength':1,'dexterity':1}, {'strength':1,'constitution':1}, {'strength':1,'intelligence':1}, {'strength':1,'wisdom':1}, {'strength':1,'charisma':1},
 {'dexterity':1,'constitution':1}, {'dexterity':1,'intelligence':1}, {'dexterity':1,'wisdom':1}, {'dexterity':1,'charisma':1},
 {'constitution':1,'intelligence':1}, {'constitution':1,'wisdom':1}, {'constitution':1,'charisma':1},
 {'intelligence':1,'wisdom':1}, {'intelligence':1,'charisma':1}, {'wisdom':1,'charisma':1},
]
ABILITIES = ('strength','dexterity','constitution','intelligence','wisdom','charisma')

def pick(increase):
    result = copy.deepcopy(PICK); result['asi']['increase'] = copy.deepcopy(increase)
    return result

def origin_session(*, odd_con=False, ability=None, score=None):
    spec = copy.deepcopy(SPEC)
    if odd_con: spec['background_ability_bonuses'] = {'dexterity':2,'intelligence':1}
    if ability:
        spec['ability_score_method'] = 'manual'; spec['ability_scores'][ability] = score
    s = game.create_session(seed=42)
    cp.create_at_level(s, spec, 3, {k:v for k,v in steps(4).items() if k in ('2','3')})
    return s

class NonDexAsiTests(unittest.TestCase):
    def apply(self, s, increase):
        p = cp.preview_level_up(s,4)
        self.assertEqual(p['status'],'ready',p)
        result = cp.apply_level_choices(s,p,pick(increase))
        self.assertEqual(result['status'],'applied',result)

    def test_literal_fifteen_choices_actual_apply_and_repeat_restore(self):
        for increase in PATTERNS:
            with self.subTest(increase=increase):
                s=create(3); before=copy.deepcopy(s.character)
                self.apply(s,increase)
                for a in ABILITIES:
                    self.assertEqual(s.character[a],before[a]+increase.get(a,0))
                    self.assertEqual(s.character[a+'_mod'],(s.character[a]-10)//2)
                    self.assertEqual(s.character['modifiers'][a],s.character[a+'_mod'])
                    self.assertEqual(s.character['saving_throw_mods'][a],before['saving_throw_mods'][a]+s.character[a+'_mod']-before[a+'_mod'])
                self.assertEqual(s.character['asi_choices'],[{'class_level':4,**pick(increase)['asi']}])
                self.assertEqual(s.character['base_ability_scores'],before['base_ability_scores'])
                for _ in range(2):
                    payload=serialize_campaign_payload(s); fresh=game.create_session(seed=99)
                    restore_campaign_session(fresh,payload)
                    self.assertEqual(fresh.character['asi_choices'],s.character['asi_choices'])
                    self.assertEqual(fresh.character['saving_throw_mods'],s.character['saving_throw_mods'])
                    self.assertEqual((fresh.character['current_hp'],fresh.character['max_hp']),(s.character['current_hp'],s.character['max_hp']))
                    s=fresh

    def test_preview_and_catalog_have_family_not_only_con(self):
        s=create(3)
        options=cp.preview_level_up(s,4)['supported_asi_choices']
        self.assertEqual([x['increase'] for x in options],PATTERNS)
        self.assertEqual([x['increase'] for x in cp.sorcerer_starting_creation_options()['level_4']['supported_asi_choices']],PATTERNS)

    def test_affected_offsets_preserved_and_cache_clear_on_apply_and_restore(self):
        s=create(3)
        for a in ABILITIES: s.character['saving_throw_mods'][a]+=7
        before=copy.deepcopy(s.character['saving_throw_mods'])
        preserved={k:s.character[k] for k in ('armor_class','initiative','dexterity')}
        self.apply(s,{'constitution':1,'charisma':1})
        self.assertEqual(s.character['saving_throw_mods'],{**before,'charisma':before['charisma']+1})
        for k in ('spell_save_dc','spell_attack_bonus','passive_perception'): self.assertNotIn(k,s.character)
        for k,v in preserved.items(): self.assertEqual(s.character[k],v)
        target=create(3)
        for k in ('spell_save_dc','spell_attack_bonus','passive_perception'): target.character[k]=999
        restore_campaign_session(target,serialize_campaign_payload(s))
        for k in ('spell_save_dc','spell_attack_bonus','passive_perception'): self.assertNotIn(k,target.character)
        self.assertEqual(target.character['saving_throw_mods'],s.character['saving_throw_mods'])

    def test_con_thresholds_raw_five_spent_resources_and_no_healing(self):
        for odd,increase,maximum in ((False,{'charisma':2},32),(False,{'constitution':1,'charisma':1},32),(True,{'charisma':1,'constitution':1},32)):
            s=origin_session(odd_con=odd)
            s._receive_xp_award(lambda: __import__('xp').apply_xp(s.character,s.world_state,5600,'quest:nondex-five'))
            s.character['current_hp']=7
            s.character['hit_dice']={'spent':2,'window_second':None,'hp':None}
            s.world_state['sorcery_points_v1']['remaining']=1
            s.world_state['spellcasting_v1']['slots']={'1':2,'2':1}
            s.character['spell_slots_remaining']={'1':2,'2':1}
            rng=s.rng.getstate(); ids=copy.deepcopy(s.world_state['xp_awarded_event_ids'])
            with patch.object(s,'heal_player',side_effect=AssertionError('No ASI healing')): self.apply(s,increase)
            self.assertEqual((s.character['level'],s.character['progression_level'],s.character['current_hp'],s.character['max_hp']),(5,4,7,maximum))
            self.assertEqual(s.character['hit_dice']['spent'],2)
            self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],2)
            self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':2,'2':2})
            self.assertEqual(s.world_state['xp_awarded_event_ids'],ids);self.assertEqual(s.rng.getstate(),rng)

    def test_full_creation_four_five_no_awards_and_noncon_hp(self):
        for level,hp in ((4,26),(5,32)):
            s=game.create_session(seed=42); bundle=steps(level);bundle['4']=pick({'charisma':2})
            try: cp.create_at_level(s,copy.deepcopy(SPEC),level,bundle)
            except ValueError as e: self.fail(str(e))
            self.assertEqual((s.character['current_hp'],s.character['max_hp']),(hp,hp))
            self.assertEqual(s.character['xp'],2700 if level==4 else 6500)
            self.assertEqual(s.world_state.get('xp_awarded_event_ids',[]),[])
            self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],level)

    def test_strict_patterns_and_cap_filter_without_mutation(self):
        for increase in ({},{'constitution':True},{'charisma':2.0},{'wisdom':'2'},{'dexterity':3},{'dexterity':1},{'charisma':1},{'charisma':2,'wisdom':1},{'charisma':1,'wisdom':1,'strength':1},{'unknown':2}):
            s=create(3);p=cp.preview_level_up(s,4);before=s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s,p,pick(increase))['status'],'rejected',increase)
            self.assertEqual(s._capture_runtime_snapshot(),before)
        s=origin_session(ability='constitution',score=18)
        self.assertEqual(cp.preview_level_up(s,4)['status'],'ready')
        self.assertNotIn(pick({'constitution':2})['asi'],cp.preview_level_up(s,4)['supported_asi_choices'])
        before=s._capture_runtime_snapshot()
        self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,4),pick({'constitution':2}))['status'],'rejected')
        self.assertEqual(s._capture_runtime_snapshot(),before)
        self.apply(s,{'constitution':1,'wisdom':1});self.assertEqual(s.character['constitution'],20)

    def test_zero_hp_and_synthetic_late_failure_rollback(self):
        from api.tests.test_roadmap_c06_zero_hp_progression import zero_state
        for status in ('unconscious','stable','dead'):
            s=origin_session(odd_con=True);before=zero_state(s,status)
            self.apply(s,{'charisma':1,'constitution':1})
            self.assertEqual((s.character['current_hp'],s.character['max_hp']),(0,26))
            self.assertEqual((s.world_state['death_state'],s.world_state['player_combat_status'],s.rng.getstate()),before)
        s=create(3); p=cp.preview_level_up(s,4);before=s._capture_runtime_snapshot()
        with patch.object(s,'_player_state_for_save',side_effect=ValueError('synthetic late failure')):
            self.assertEqual(cp.apply_level_choices(s,p,pick({'wisdom':2}))['status'],'rejected')
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_actual_cha_spell_and_strength_intelligence_wisdom_check_consumers(self):
        import spell_scope
        from api.tests.test_roadmap_c19_quickened import combat
        s,enemy=combat(3)
        self.apply(s,{'charisma':2})  # canonical CHA15→17, modifier2→3
        before=copy.deepcopy(s.world_state['spellcasting_v1']['slots'])
        with patch('game.roll_d20',return_value=12),patch.object(s.rng,'randint',return_value=3):
            result=spell_scope.cast(s,'Fire Bolt',enemy['id'])
        self.assertEqual(result['spell_attack_modifier'],5)
        self.assertEqual(result['spell_save_dc'],13)
        self.assertEqual(result['resolution']['total_modifier'],5)
        self.assertEqual(result['damage'],3)
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],before)
        for ability,skill,modifier,bonus in (('strength','Athletics',0,0),('intelligence','Arcana',1,3),('wisdom','Insight',2,4)):
            s=create(3);self.apply(s,{ability:2})
            with patch('game.roll_d20',return_value=10):
                check=game.perform_skill_check(skill,12,s.character['modifiers'],s.character['proficient_skills'],s.character['proficiency_bonus'],session=s)
            self.assertEqual(check['ability'],ability)
            self.assertEqual(check['modifier'],modifier)
            self.assertEqual(check['total_bonus'],bonus)
            self.assertEqual(check['total'],10+bonus)

    def test_cap_twenty_and_eighteen_boundary_and_forged_record(self):
        s=origin_session(ability='charisma',score=18);self.apply(s,{'charisma':2})
        self.assertEqual(s.character['charisma'],20)
        spec=copy.deepcopy(SPEC);spec['ability_score_method']='manual';spec['ability_scores']['constitution']=18
        spec['background_ability_bonuses']={'constitution':2,'dexterity':1}
        s=game.create_session(seed=42);cp.create_at_level(s,spec,3,{k:v for k,v in steps(4).items() if k in ('2','3')})
        options=cp.preview_level_up(s,4)['supported_asi_choices']
        self.assertTrue(options);self.assertFalse(any('constitution' in x['increase'] for x in options))
        self.apply(s,{'wisdom':2})
        from api.persistence.campaign_models import CampaignCorruptError
        for version in (4,5,6):
            s._persisted_engine_format=version;s.world_state.setdefault('xp_awarded_event_ids',[])
            payload=serialize_campaign_payload(s)
            fresh=create(1);restore_campaign_session(fresh,payload)
            self.assertEqual(fresh.character['wisdom'],14)
            bad=copy.deepcopy(payload);bad['engine_save']['player']['asi_choices'][0]['increase']={'dexterity':2}
            before=fresh._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError):restore_campaign_session(fresh,bad)
            self.assertEqual(fresh._capture_runtime_snapshot(),before)
