"""Selected earned Berserker3, extra skill and resource state; no creation3."""
import copy
import unittest
from unittest.mock import patch
import game
import xp
import character_progression as cp
import barbarian_rage as rage
from api.tests.test_roadmap_c10_rage import created,combat
from api.tests.test_roadmap_c06_barbarian import spec
from api.persistence.campaign_validation import serialize_campaign_payload,restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError
PICK={'subclass_id':'berserker','primal_knowledge_skill':'Survival'}

def earned(raw=3):
    s=created(2)
    s._receive_xp_award(xp.apply_xp,s.character,s.world_state,600 if raw==3 else 6200,'quest:berserker-earned')
    return s

def apply(test,s,pick=None):
    preview=cp.preview_level_up(s,3)
    test.assertEqual(preview['status'],'ready',preview)
    result=cp.apply_level_choices(s,preview,copy.deepcopy(PICK if pick is None else pick))
    test.assertEqual(result['status'],'applied',result)
    return result

class BerserkerProgressionTests(unittest.TestCase):
    def test_actual_earned_three_skill_provenance_pool_hp_and_restore(self):
        s=earned();before=copy.deepcopy(s.character);world=copy.deepcopy(s.world_state);rng=s.rng.getstate()
        apply(self,s)
        self.assertEqual(s.character['progression_level'],3)
        self.assertEqual(s.character['subclass_id'],'berserker')
        self.assertEqual(s.character['primal_knowledge_choice'],{'class_level':3,'skill':'Survival','prior_proficient_skills':before['proficient_skills']})
        self.assertEqual(s.character['proficient_skills'],before['proficient_skills']+['Survival'])
        self.assertEqual(s.world_state['rage_v1']['remaining'],3)
        self.assertEqual((s.character['current_hp'],s.character['max_hp'],s.character['xp']),(32,32,900))
        self.assertEqual(s.rng.getstate(),rng)
        self.assertEqual((s.world_state['inventory'],s.world_state['currency']),(world['inventory'],world['currency']))
        p=serialize_campaign_payload(s);t=created();restore_campaign_session(t,p)
        self.assertEqual(serialize_campaign_payload(t),p)

    def test_spent_active_pool_delta_preserves_duration_and_paid_raw_five(self):
        s,n=combat();rage.activate(s)
        s._receive_xp_award(xp.apply_xp,s.character,s.world_state,6200,'quest:berserker-ahead')
        before=copy.deepcopy(s.world_state['rage_v1']['active']);hp=s.character['max_hp']
        apply(self,s)
        self.assertEqual(s.world_state['rage_v1']['remaining'],2)
        self.assertEqual(s.world_state['rage_v1']['active'],before)
        self.assertEqual(s.character['max_hp'],hp)
        self.assertEqual(rage.projection(s)['max_uses'],3)

    def test_direct_core_choices_do_not_award_xp_or_repeat_hp(self):
        s=created();apply(self,s)
        self.assertEqual((s.character['level'],s.character['xp'],s.character['max_hp']),(3,300,32))
        before=s._capture_runtime_snapshot()
        self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,3),PICK)['status'],'rejected')
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_invalid_owned_skill_and_foreign_subclass_refuse_without_mutation(self):
        for pick in ({'subclass_id':'berserker','primal_knowledge_skill':'Athletics'},
                     {'subclass_id':'wild_heart','primal_knowledge_skill':'Survival'},
                     {'subclass_id':'berserker','primal_knowledge_skill':True},
                     {**PICK,'spells':[]}):
            s=earned();before=s._capture_runtime_snapshot()
            self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,3),pick)['status'],'rejected')
            self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_creation_four_without_its_asi_is_refused_before_mutation(self):
        # Start 3-5 are accepted creation leaves (test_roadmap_c06_barbarian_creation3 / _creation45); a start-4 bundle without its ASI is refused.
        s=created();before=s._capture_runtime_snapshot()
        with self.assertRaisesRegex(ValueError,'barbarian_level_four_choices_required'):cp.create_at_level(s,spec(),4,{'2':{},'3':PICK,'4':{}})
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_corrupt_skill_baseline_save_refuses_without_append(self):
        s=earned();apply(self,s);p=serialize_campaign_payload(s)
        p['engine_save']['player']['primal_knowledge_choice']['prior_proficient_skills'].append('Survival')
        t=created();before=t._capture_runtime_snapshot()
        with self.assertRaises(CampaignCorruptError):restore_campaign_session(t,p)
        self.assertEqual(t._capture_runtime_snapshot(),before)

    def test_pool_delta_short_and_long_rest_cap_three_without_reactivation(self):
        s,n=combat();rage.activate(s);s.end_combat('pool_fixture');s.advance_campaign_time(12,'wait',source='berserker:expiry')
        # Present spent state comes from actual activation, not a fixture refill.
        apply(self,s)
        self.assertEqual(s.world_state['rage_v1']['remaining'],2)
        rage.restore(s,'short_rest');self.assertEqual(s.world_state['rage_v1']['remaining'],3)
        rage.restore(s,'short_rest');self.assertEqual(s.world_state['rage_v1']['remaining'],3)
        rage.restore(s,'long_rest');self.assertIsNone(s.world_state['rage_v1']['active'])

    def test_absent_legacy_capability_refuses_without_adoption(self):
        s=earned();s.world_state.pop('rage_v1');s.world_state.pop('worn_armor_v1')
        before=s._capture_runtime_snapshot()
        self.assertEqual(cp.preview_level_up(s,3)['reason'],'selected_subclass_rage_capability_required')
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_late_fault_restores_format_state_rng_and_origin(self):
        s=earned();before=s._capture_runtime_snapshot();old=s.__dict__.get('_persisted_engine_format')
        def fault():
            s._persisted_engine_format=1;s.rng.randint(1,20)
            raise RuntimeError('synthetic final save refusal')
        with patch.object(s,'_player_state_for_save',side_effect=fault):
            result=cp.apply_level_choices(s,cp.preview_level_up(s,3),PICK)
        self.assertEqual(result['status'],'rejected')
        self.assertEqual(s._capture_runtime_snapshot(),before)
        self.assertEqual(s.__dict__.get('_persisted_engine_format'),old)

    def test_new_perception_skill_clears_player_cache_preserves_other_origins(self):
        request=spec();request['proficient_skills']=[('Nature' if x=='Perception' else x) for x in request['proficient_skills']]
        s=game.create_session(seed=52);cp.create_at_level(s,request,2,{'2':{}})
        before=copy.deepcopy(s.character);s.character['passive_perception']=99
        apply(self,s,{'subclass_id':'berserker','primal_knowledge_skill':'Perception'})
        self.assertNotIn('passive_perception',s.character)
        for key in ('base_ability_scores','background_ability_bonuses','species_bonus_skills','expertise_skills','saving_throw_mods','armor_class'):
            self.assertEqual(s.character.get(key),before.get(key))

    def test_zero_hp_choice_does_not_heal_or_resurrect(self):
        s,n=combat();s._apply_player_damage(s.character['current_hp'],took_damage=True)
        self.assertEqual(s.character['current_hp'],0)
        before=copy.deepcopy(s.world_state['death_state']);apply(self,s)
        self.assertEqual(s.character['current_hp'],0)
        self.assertEqual(s.world_state['death_state'],before)

    def test_shared_disclosure_does_not_claim_all_supported_effects_missing(self):
        for name,level,bad in (('Barbarian',3,'activation, resources, renewal and effects remain pending'),
                               ('Sorcerer',2,'Sorcery Points are not tracked yet')):
            self.assertNotIn(bad,' '.join(cp.progression_effects_pending(name,level)))
        self.assertIn('Strength substitution',' '.join(cp.progression_effects_pending('Barbarian',3)))

    def test_actual_added_skill_check_uses_proficiency_and_no_strength_substitution(self):
        s=earned();apply(self,s)
        c=s.character
        with patch('game.roll_d20',return_value=10):
            result=game.perform_skill_check('Survival',10,c['modifiers'],c['proficient_skills'],c['proficiency_bonus'],session=s)
        self.assertEqual((result['ability'],result['modifier'],result['proficiency_bonus']),('wisdom',1,2))
        self.assertEqual(result['total'],13)

    def test_stale_choice_cleared_on_legacy_restore_and_recreation(self):
        old=serialize_campaign_payload(created())
        s=earned();apply(self,s);restore_campaign_session(s,old)
        self.assertNotIn('primal_knowledge_choice',s.character)
        self.assertNotIn('subclass_id',s.character)
        s=earned();apply(self,s);cp.create_at_level(s,spec(),2,{'2':{}})
        self.assertNotIn('primal_knowledge_choice',s.character)
        self.assertNotIn('subclass_id',s.character)

    def test_invalid_choice_records_and_legacy_formats_reject_saved_claim(self):
        for mutation in ('boollevel','duplicateprior','missingmembership','badsubclass','v3'):
            s=earned();apply(self,s);p=serialize_campaign_payload(s);player=p['engine_save']['player']
            if mutation=='boollevel':player['primal_knowledge_choice']['class_level']=True
            if mutation=='duplicateprior':player['primal_knowledge_choice']['prior_proficient_skills']*=2
            if mutation=='missingmembership':player['proficient_skills'].remove('Survival')
            if mutation=='badsubclass':player['subclass_id']='zealot'
            if mutation=='v3':p['engine_save']['version']=3
            with self.assertRaises(CampaignCorruptError):restore_campaign_session(created(),p)

    def test_direct_transition_during_combat_has_exact_fresh_restore(self):
        s,n=combat();apply(self,s)
        p=serialize_campaign_payload(s);t=created();restore_campaign_session(t,p)
        self.assertEqual(serialize_campaign_payload(t),p)

    def test_bare_numeric_three_cannot_claim_new_rage_capacity(self):
        s=earned();s.character['progression_level']=3  # malformed feature claim, no selected provenance
        before=s._capture_runtime_snapshot()
        with self.assertRaises(ValueError):rage.validate(s.world_state,s.character,4)
        self.assertEqual(s._capture_runtime_snapshot(),before)
