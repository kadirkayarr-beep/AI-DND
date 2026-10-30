"""Selected Font slot→points; source Sorcerer PDF140/printed141.

One slot gains its level in points, no action. No reverse creation or overcap
policy claim. Existing test combat has a deliberately surviving synthetic NPC.
"""
import copy
import unittest
from unittest.mock import patch
import game
import xp
import sorcery_points
import spell_scope
import action_economy
from combat_lifecycle import CombatRequestError
from api.tests.test_roadmap_c19_quickened import created, combat
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session


def spent(level=3, outside=False):
    s, enemy=combat(level)
    spell_scope.cast(s,'Magic Missile',enemy['id'],metamagic='quickened_spell')
    if outside: s.end_combat('font_fixture_finished_combat')
    return s, enemy


def command(level=1):
    return {'steps':[{'kind':'convert_spell_slot','slot_level':level}]}


class FontConversionTests(unittest.TestCase):
    def convert(self,s,level=1):
        try: return action_economy.execute(s,command(level))
        except CombatRequestError as error: self.fail('Source-valid conversion rejected: '+error.code)

    def test_actual_typed_conversion_outside_restores_literal_points_and_spends_one_slot(self):
        s,_=spent(3,True); before=copy.deepcopy(s.world_state['spellcasting_v1']); rng=s.rng.getstate()
        result=self.convert(s,2)
        self.assertEqual(s.world_state['sorcery_points_v1'],{'version':1,'remaining':3})
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':before['slots']['1'],'2':before['slots']['2']-1})
        self.assertEqual(s.world_state['spellcasting_v1']['slot_turn'],before['slot_turn'])
        self.assertEqual(s.rng.getstate(),rng)
        self.assertEqual(result['model_calls'],0)
        self.assertEqual(result['action_economy_result']['steps'][0]['result'],{'slot_level':2,'slot_spent':1,'points_gained':2,'points_remaining':3})

    def test_conversion_after_cast_and_spent_action_bonus_does_not_change_budgets(self):
        s,enemy=spent(3); action_economy.dash(s)
        budget=copy.deepcopy(action_economy.ensure(s)); marker=copy.deepcopy(s.world_state['spellcasting_v1']['slot_turn']);clock=copy.deepcopy(s.world_state.get('campaign_time'))
        self.convert(s,1)
        self.assertEqual(action_economy.ensure(s),budget)
        self.assertEqual(s.world_state['spellcasting_v1']['slot_turn'],marker)
        self.assertEqual(s.world_state.get('campaign_time'),clock)
        action_economy.grant(s,'player','test_extra_action',['magic'])
        with self.assertRaises(CombatRequestError) as e: spell_scope.cast(s,'Magic Missile',enemy['id'])
        self.assertEqual(e.exception.code,'spell_slot_turn_limit')

    def test_conversion_does_not_require_quickened_selected(self):
        s,_=spent(3,True)
        s.character['metamagic']=['Careful Spell','Twinned Spell']
        self.convert(s,1)
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],2)

    def test_option_projection_is_pure_and_authoritative(self):
        self.assertTrue(callable(getattr(sorcery_points,'conversion_options',None)))
        s,_=spent(3,True); before=s._capture_runtime_snapshot()
        self.assertEqual(sorcery_points.conversion_options(s),[
            {'slot_level':1,'points_gained':1,'available':True,'reason':None},
            {'slot_level':2,'points_gained':2,'available':True,'reason':None}])
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_exact_native_command_recognition(self):
        self.assertTrue(callable(getattr(sorcery_points,'native_conversion_request',None)))
        self.assertTrue(sorcery_points.native_conversion_request(command(1)))
        for bad in (None,{}, {'steps':[]}, {'steps':command()['steps']*2}, command(True), command(0),command(4), {'steps':[{'kind':'convert_spell_slot','slot_level':1,'metamagic':'quickened_spell'}]}):
            self.assertFalse(sorcery_points.native_conversion_request(bad),bad)

    def test_full_pool_refusal_preserves_everything(self):
        s,_=combat(3);before=s._capture_runtime_snapshot()
        with self.assertRaises(CombatRequestError) as error: action_economy.execute(s,command(1))
        self.assertEqual(error.exception.code,'sorcery_points_capacity')
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_save_fresh_restore_keeps_both_pools_without_award(self):
        s,_=spent(3,True);self.convert(s,2);original=serialize_campaign_payload(s)
        fresh=game.create_session(seed=77);restore_campaign_session(fresh,original)
        self.assertEqual(serialize_campaign_payload(fresh)['engine_save'],original['engine_save'])
        self.assertEqual(fresh.world_state['sorcery_points_v1']['remaining'],3)
        self.assertEqual(fresh.world_state.get('xp_awarded_event_ids',[]),[])

    def test_literal_slot_three_gain_after_two_real_feature_spends(self):
        s,enemy=spent(5)
        # Existing turn-budget owner starts the next synthetic player turn.
        action_economy.begin_turn(s,'player')
        spell_scope.cast(s,'Magic Missile',enemy['id'],metamagic='quickened_spell')
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],1)
        before=copy.deepcopy(s.world_state['spellcasting_v1'])
        self.convert(s,3)
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],4)
        self.assertEqual(s.world_state['spellcasting_v1']['slots']['3'],before['slots']['3']-1)
        self.assertEqual(s.world_state['spellcasting_v1']['slot_turn'],before['slot_turn'])

    def test_conversion_before_first_cast_does_not_write_cast_lock(self):
        s,enemy=spent(3);action_economy.begin_turn(s,'player')
        marker=copy.deepcopy(s.world_state['spellcasting_v1']['slot_turn'])
        self.convert(s,1)
        self.assertEqual(s.world_state['spellcasting_v1']['slot_turn'],marker)
        spell_scope.cast(s,'Magic Missile',enemy['id'],metamagic='quickened_spell')
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],0)

    def test_strict_negative_modes_preserve_snapshot_and_rng(self):
        for mode in ('missing_pool','null_pool','wrong_class','empty_slot','overcap','wrong_actor','pending_reaction','zero_hp','dead'):
            s,enemy=spent(3)
            if mode=='missing_pool': s.world_state.pop('sorcery_points_v1')
            if mode=='null_pool': s.world_state['sorcery_points_v1']=None
            if mode=='wrong_class': s.character['class']='Barbarian'
            if mode=='empty_slot': s.world_state['spellcasting_v1']['slots']['1']=0
            if mode=='overcap': s.world_state['sorcery_points_v1']['remaining']=3
            if mode=='wrong_actor': s.world_state['combat']['current_actor_id']=enemy['id']
            if mode=='pending_reaction': action_economy.ensure(s)['player']['opportunity']={'id':'synthetic-pending'}
            if mode=='zero_hp': s.character['current_hp']=0
            if mode=='dead': s.world_state['death_state']['dead']=True
            before=s._capture_runtime_snapshot()
            with self.subTest(mode=mode),self.assertRaises((ValueError,CombatRequestError)):
                action_economy.execute(s,command(1))
            self.assertEqual(s._capture_runtime_snapshot(),before,mode)

    def test_bad_fields_and_mixed_commands_reject_before_debit(self):
        for bad in (command(True),command(0),command(4),command('1'),{'steps':command()['steps']*2},
                    {'steps':[{'kind':'dash'},*command()['steps']]},
                    {'steps':[{'kind':'convert_spell_slot','slot_level':1,'resource':'bonus'}]},
                    {'steps':[{'kind':'convert_spell_slot','slot_level':1,'target_id':None}]},
                    {'steps':[{'kind':'convert_spell_slot','slot_level':1,'ability':'Magic Missile'}]}):
            s,_=spent(3,True);before=s._capture_runtime_snapshot()
            with self.subTest(command=bad),self.assertRaises(CombatRequestError): action_economy.execute(s,bad)
            self.assertEqual(s._capture_runtime_snapshot(),before)
        s,_=spent(3,True)
        for bad in (True,0,4,'1',None):
            before=s._capture_runtime_snapshot()
            with self.assertRaises(CombatRequestError): sorcery_points.convert_slot(s,bad)
            self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_incapacitated_is_not_an_invented_action_budget_gate(self):
        s,_=spent(3);s.character['conditions']=['incapacitated']
        before=copy.deepcopy(action_economy.ensure(s))
        self.convert(s,1)
        self.assertEqual(action_economy.ensure(s),before)
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],2)

    def test_raw_xp_ahead_uses_applied_capacity_not_raw_slots(self):
        s,_=spent(3,True)
        s._receive_xp_award(xp.apply_xp,s.character,s.world_state,5600,'quest:font-pending')
        self.assertEqual((s.character['level'],s.character['progression_level']),(5,3))
        self.assertEqual([o['slot_level'] for o in sorcery_points.conversion_options(s)],[1,2])
        before=s._capture_runtime_snapshot()
        with self.assertRaises(CombatRequestError): sorcery_points.convert_slot(s,3)
        self.assertEqual(s._capture_runtime_snapshot(),before)
        self.convert(s,2)
        self.assertEqual(s.world_state['sorcery_points_v1']['remaining'],3)

    def test_late_narration_fault_rolls_back_both_resources(self):
        s,_=spent(3,True);before=s._capture_runtime_snapshot()
        with patch.object(action_economy,'resolved_narration',side_effect=RuntimeError('synthetic postconversion fault')):
            with self.assertRaises(RuntimeError): action_economy.execute(s,command(1))
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_long_rest_restores_original_slots_and_point_maximum(self):
        s,_=spent(3,True);s.commit_location_change('tavern');self.convert(s,1)
        marker=copy.deepcopy(s.world_state['spellcasting_v1']['slot_turn'])
        s.resolve_species_trait_action('long_rest')
        self.assertEqual(s.world_state['sorcery_points_v1'],{'version':1,'remaining':3})
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':4,'2':2})
        self.assertEqual(s.world_state['spellcasting_v1']['slot_turn'],marker)
