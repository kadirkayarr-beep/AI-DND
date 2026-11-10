"""Selected Rage1–2 literal source oracles; no full Barbarian acceptance.

The 12-second soft bridge is an explicit engine convention, not quoted PHB.
Synthetic surviving NPCs/faults are labeled tests, never native fixture claims.
"""
import copy
import importlib
import importlib.util
import unittest
from unittest.mock import patch
import game
import action_economy
import character_progression as cp
from api.tests.test_roadmap_c06_barbarian import spec
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session


def created(level=2, *, ability_scores=None):
    s=game.create_session(seed=52)
    selection=spec()
    if ability_scores is not None:selection['ability_scores']=copy.deepcopy(ability_scores)
    cp.create_at_level(s,selection,level,{'2':{}} if level==2 else {})
    s.commit_location_change('tavern')
    s.ensure_campaign_clock()
    return s


def combat(level=2, *, ability_scores=None):
    s=created(level,ability_scores=ability_scores)
    npc=s.create_npc_from_ai({'name':'Rage Unit Opponent','role':'Guard','location':'tavern'})
    npc.update(current_hp=100,max_hp=100,armor_class=10,hostile=True,combat_side='enemy',
               distance_ft=5,attack_damage_type='bludgeoning',attack_bonus=0,damage_die=6,damage_dice=1,damage_modifier=0)
    s.world_state.setdefault('monster_perception',{})[npc['id']]={'player':{'visible':True}}
    with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
    return s,npc


class RageTests(unittest.TestCase):
    def owner(self):
        self.assertIsNotNone(importlib.util.find_spec('barbarian_rage'),'selected Rage owner is not implemented')
        return importlib.import_module('barbarian_rage')

    def test_actual_creation_proof_pool_and_absent_legacy_roundtrip(self):
        for level in (1,2):
            s=created(level)
            self.assertEqual(s.world_state.get('worn_armor_v1'),{'version':1,'armor_id':None})
            self.assertEqual(s.world_state.get('rage_v1'),{'version':1,'remaining':2,'active':None})
            fresh=game.create_session(seed=99);restore_campaign_session(fresh,serialize_campaign_payload(s))
            self.assertEqual(fresh.world_state['rage_v1'],s.world_state['rage_v1'])
            s.world_state.pop('rage_v1');s.world_state.pop('worn_armor_v1')
            restore_campaign_session(fresh,serialize_campaign_payload(s))
            self.assertNotIn('rage_v1',fresh.world_state);self.assertNotIn('worn_armor_v1',fresh.world_state)

    def test_activation_consumes_only_bonus_and_one_use_exact_once(self):
        r=self.owner();s,npc=combat();before=s.rng.getstate()
        result=action_economy.execute(s,{'steps':[{'kind':'activate_rage','resource':'bonus'}]})
        self.assertTrue(r.active(s),result)
        self.assertEqual(s.world_state['rage_v1']['remaining'],1)
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],12)
        resources=action_economy.ensure(s)['player']
        self.assertTrue(resources['bonus_action_spent']);self.assertFalse(resources['base_action_spent'])
        self.assertEqual(s.rng.getstate(),before)
        snapshot=s._capture_runtime_snapshot()
        with self.assertRaises(ValueError):r.activate(s)
        self.assertEqual(s._capture_runtime_snapshot(),snapshot)

    def test_two_own_end_boundaries_and_duplicate_identity(self):
        r=self.owner();s,npc=combat();r.activate(s)
        c=s.world_state['combat'];turn=c['turn_resources']['player']['attack_turn_counter'];identity=c['combat_id']
        r.end_player_turn(s,identity,turn)
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],6)
        snapshot=s._capture_runtime_snapshot();r.end_player_turn(s,identity,turn)
        self.assertEqual(s._capture_runtime_snapshot(),snapshot)
        r.end_player_turn(s,identity,turn+1)
        self.assertIsNone(s.world_state['rage_v1']['active'])

    def test_exit_fractional_time_and_reentry_do_not_inflate_budget(self):
        r=self.owner();s,npc=combat();r.activate(s)
        s.end_combat('fixture_transition')
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],12)
        s.advance_campaign_time(11,'fixture_wait',source='rage:wait11')
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],1)
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
        s.end_combat('fixture_transition_again')
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],1)
        s.advance_campaign_time(1,'fixture_wait',source='rage:wait1')
        self.assertFalse(r.active(s));self.assertIsNone(s.world_state['rage_v1']['active'])

    def test_hard_cap_checked_before_extension_and_projection_is_pure(self):
        r=self.owner();s,npc=combat();r.activate(s)
        s.advance_campaign_time(599,'combat_round',source='rage:cap599')
        self.assertTrue(r.active(s))
        before=s._capture_runtime_snapshot();self.assertTrue(r.projection(s)['active'])
        self.assertEqual(s._capture_runtime_snapshot(),before)
        s.advance_campaign_time(1,'combat_round',source='rage:cap600')
        self.assertFalse(r.active(s));self.assertIsNone(s.world_state['rage_v1']['active'])
        before=s._capture_runtime_snapshot()
        with self.assertRaises(ValueError):r.extend(s)
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_completed_rests_recover_one_then_all_and_progression_preserves_spent(self):
        r=self.owner();s,npc=combat(1);r.activate(s);s.end_combat('fixture_rest')
        s.advance_campaign_time(12,'fixture_wait',source='rage:expire')
        self.assertEqual(s.world_state['rage_v1']['remaining'],1)
        self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,2),{})['status'],'applied')
        self.assertEqual(s.world_state['rage_v1']['remaining'],1)
        s.resolve_species_trait_action('short_rest')
        self.assertEqual(s.world_state['rage_v1']['remaining'],2)
        with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
        r.activate(s);s.end_combat('fixture_rest2');s.resolve_species_trait_action('long_rest')
        self.assertEqual(s.world_state['rage_v1'],{'version':1,'remaining':2,'active':None})

    def test_invalid_commands_and_ambiguous_proof_leave_snapshot_unchanged(self):
        r=self.owner()
        for command in ({'steps':[{'kind':'activate_rage'}]}, {'steps':[{'kind':'activate_rage','resource':'bonus','target_id':None}]},
                        {'steps':[{'kind':'activate_rage','resource':'bonus'},{'kind':'end_turn'}]}):
            s,npc=combat();before=s._capture_runtime_snapshot()
            with self.assertRaises(ValueError):action_economy.execute(s,command)
            self.assertEqual(s._capture_runtime_snapshot(),before)
        for proof in (None,{'version':True,'armor_id':None},{'version':1,'armor_id':'heavy'}):
            s,npc=combat();s.world_state['worn_armor_v1']=proof;before=s._capture_runtime_snapshot()
            with self.assertRaises(ValueError):r.activate(s)
            self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_active_save_roundtrip_and_late_synthetic_fault(self):
        r=self.owner();s,npc=combat();r.activate(s);s.end_combat('fixture_save')
        s.advance_campaign_time(5,'fixture_wait',source='rage:save5')
        payload=serialize_campaign_payload(s);fresh=game.create_session(seed=12)
        restore_campaign_session(fresh,payload)
        self.assertEqual(fresh.world_state['rage_v1'],s.world_state['rage_v1'])
        self.assertEqual(fresh.rng.getstate(),s.rng.getstate())
        s,npc=combat();before=s._capture_runtime_snapshot()
        with patch('action_economy.resolved_narration',side_effect=ValueError('synthetic late fault')):
            with self.assertRaises(ValueError):action_economy.execute(s,{'steps':[{'kind':'activate_rage','resource':'bonus'}]})
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_malformed_numeric_or_ahead_applied_levels_never_grant_benefits(self):
        r=self.owner()
        for raw,applied in ((True,1),('2',1),(1,2),(2,3),(0,1),(21,2)):
            s,npc=combat();r.activate(s)
            s.character['level']=raw;s.character['progression_level']=applied
            before=s._capture_runtime_snapshot()
            with self.assertRaises(ValueError,msg=(raw,applied)):r.active(s)
            self.assertEqual(s._capture_runtime_snapshot(),before)
        s,npc=combat();r.activate(s)
        import xp
        s._receive_xp_award(xp.apply_xp,s.character,s.world_state,6200,'quest:rage-raw-five')
        self.assertEqual((s.character['level'],s.character['progression_level']),(5,2))
        self.assertTrue(r.active(s));self.assertEqual(r.projection(s)['max_uses'],2)

    def test_zero_pool_short_rest_recovers_one_not_all_and_interruption_none(self):
        r=self.owner();s,npc=combat()
        for _ in range(2):
            r.activate(s);s.end_combat('drain_for_rest')
            s.advance_campaign_time(12,'fixture_wait',source=f"rage:drain:{_}")
            if _==0:
                with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
        self.assertEqual(s.world_state['rage_v1']['remaining'],0)
        for kind in ('short_rest','long_rest'):
            before=copy.deepcopy(s.world_state['rage_v1'])
            # Synthetic interrupted-rest return pins the actual completion branch;
            # it is not an observed native scheduled event.
            with patch.object(game,'advance_campaign_time',return_value={'interrupted':True,'elapsed_seconds':1}):
                result=s.resolve_species_trait_action(kind)
            self.assertFalse(result['effects']['rest_completed']);self.assertEqual(s.world_state['rage_v1'],before)
        s.resolve_species_trait_action('short_rest');self.assertEqual(s.world_state['rage_v1']['remaining'],1)
        s.resolve_species_trait_action('long_rest');self.assertEqual(s.world_state['rage_v1']['remaining'],2)

    def test_actual_turn_owner_extension_and_combat_clock_not_double_debited(self):
        r=self.owner();s,npc=combat();r.activate(s)
        original=s.world_state['rage_v1']['active']['started_at']
        s.advance_combat_turn()  # actual player END, then enemy begins
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],6)
        s.advance_combat_turn()  # enemy END -> new round6s -> player begins
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],6)
        self.assertEqual(s.world_state['campaign_time']['elapsed_seconds'],original+6)
        r.extend(s)
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],12)
        self.assertEqual(s.world_state['rage_v1']['active']['started_at'],original)
        self.assertEqual(s.world_state['rage_v1']['remaining'],1)
        s.advance_combat_turn();s.end_combat('next_turn_exit')
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'],6)

    def test_skill_advantage_terminal_incapacitation_and_actual_zero_hp(self):
        r=self.owner();s,npc=combat();r.activate(s)
        c=s.character
        with patch('game.roll_d20',side_effect=[4,17]):
            check=game.perform_skill_check('Athletics',10,c['modifiers'],c['proficient_skills'],c['proficiency_bonus'],session=s)
        self.assertTrue(check['advantage']);self.assertEqual(check['dice'],17)
        with patch('game.roll_d20',return_value=10):
            check=game.perform_skill_check('Athletics',10,c['modifiers'],c['proficient_skills'],c['proficiency_bonus'],disadvantage=True,session=s)
        self.assertEqual(check['dice_rolls'],[10])
        c['conditions']=['incapacitated']  # condition fixture, settled at actual mechanical boundary
        with patch('game.roll_d20',return_value=10):
            game.perform_skill_check('Athletics',10,c['modifiers'],c['proficient_skills'],c['proficiency_bonus'],session=s)
        self.assertIsNone(s.world_state['rage_v1']['active'])
        c['conditions']=[];self.assertFalse(r.active(s))
        s,npc=combat();r.activate(s);s._apply_player_damage(23,took_damage=True)
        self.assertEqual(s.character['current_hp'],0);self.assertIsNone(s.world_state['rage_v1']['active'])

    def test_clock_dispatch_without_species_state_and_malformed_save_rejects(self):
        r=self.owner();s,npc=combat();r.activate(s);s.end_combat('clock_route')
        s.character.pop('species_trait_state')  # explicit clock-dispatch branch fixture
        import timed_gameplay
        timed_gameplay._advance(s,12,'fixture_clock')
        self.assertIsNone(s.world_state['rage_v1']['active'])
        from api.persistence.campaign_models import CampaignCorruptError
        s,npc=combat();r.activate(s);payload=serialize_campaign_payload(s)
        for mutate in (
            lambda w:w['rage_v1'].update(remaining=True),
            lambda w:w['rage_v1'].update(extra=1),
            lambda w:w['rage_v1']['active'].update(remaining_seconds=0),
            lambda w:w['rage_v1']['active'].update(started_at=True),
            lambda w:w['rage_v1']['active'].update(settled_at=99999),
            lambda w:w['rage_v1']['active'].update(last_end={'combat_id':'x','turn':True}),
            lambda w:w.pop('worn_armor_v1'),
        ):
            bad=copy.deepcopy(payload);mutate(bad['engine_save']['world_state'])
            target=created();before=target._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError):restore_campaign_session(target,bad)
            self.assertEqual(target._capture_runtime_snapshot(),before)

    def test_outside_soft_expired_saved_active_record_is_rejected_not_normalized(self):
        from api.persistence.campaign_models import CampaignCorruptError
        r=self.owner();s,npc=combat();r.activate(s);s.end_combat('saved_soft_deadline')
        payload=serialize_campaign_payload(s)
        payload['engine_save']['world_state']['campaign_time']['elapsed_seconds']+=12
        target=created();before=target._capture_runtime_snapshot()
        with self.assertRaises(CampaignCorruptError):restore_campaign_session(target,payload)
        self.assertEqual(target._capture_runtime_snapshot(),before)

    def test_actual_interrupted_long_rest_hour_boundary_recovers_one_only(self):
        from api.tests.test_campaign_time_edges import event
        r=self.owner()
        for seconds,expected in ((3599,0),(3600,1)):
            s,npc=combat()
            for i in range(2):
                r.activate(s);s.end_combat('drain_interrupted')
                s.advance_campaign_time(12,'fixture_wait',source=f'rage:interrupted-drain:{i}')
                if i==0:
                    with patch('game.roll_initiative_player',return_value=20),patch('game.roll_initiative',return_value=1):s.start_combat(npc)
            now=s.world_state['campaign_time']['elapsed_seconds']
            event(s,'rage-interrupt-rest',now+seconds,now+seconds+600,behavior='FORCED',summary='Leave the building.')
            result=s.resolve_species_trait_action('long_rest')
            self.assertFalse(result['effects']['rest_completed'])
            self.assertEqual(result['effects']['time_result']['elapsed_seconds'],seconds)
            self.assertEqual(s.world_state['rage_v1']['remaining'],expected)
            self.assertNotIn('last_long_rest_completed_at',s.world_state)

    def test_rage_narration_reads_completed_result_only(self):
        # No live session is available: summaries must not resolve or consult mechanics.
        for kind,expected in (
            ('activate_rage','Bonus eylem ile Öfke başlatırsın; kalan kullanım: 1.'),
            ('extend_rage','Bonus eylem ile Öfke süreni uzatırsın; ek kullanım harcanmaz.'),
        ):
            result={'active':True,'uses_remaining':1,'remaining_seconds':12}
            before=copy.deepcopy(result)
            self.assertEqual(action_economy.resolved_narration(None,[{'kind':kind,'result':result}]),expected)
            self.assertEqual(result,before)

    def test_rage_narration_does_not_claim_unresolved_or_malformed_success(self):
        for kind in ('activate_rage','extend_rage'):
            for result in (None,{}, {'active':False,'uses_remaining':1},
                           {'active':True,'uses_remaining':True},
                           {'active':True,'uses_remaining':-1},
                           {'active':True,'uses_remaining':3}):
                self.assertEqual(action_economy.resolved_narration(None,[{'kind':kind,'result':result}]),
                                 'Hamlenin sonucunu şu an gösteremiyorum.')
