"""Source Barbarian starting packages, new creation only; opaque pack contents."""
import copy
import unittest
from unittest.mock import patch
import game
import character_progression as cp
import equipment_economy as eq
from api.dnd_2024_rules import CLASS_DEFINITIONS, BACKGROUND_DEFINITIONS
from api.tests.test_roadmap_c06_barbarian import spec
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session

A=['Büyük Balta (Greataxe)','4 Handaxes',"Explorer's Pack",'15 GP']
B=['75 GP']

def create(package='A',background_option='B',level=2,session=None):
    s=session or game.create_session(seed=52)
    request=dict(spec(),equipment_package=package,background_equipment_option=background_option)
    cp.create_at_level(s,request,level,{'2':{}} if level==2 else {})
    return s

class StartingEquipmentTests(unittest.TestCase):
    def test_literal_source_catalogue(self):
        packages=CLASS_DEFINITIONS['Barbarian']['equipment_packages']
        self.assertEqual([p['items'] for p in packages],[A,B])

    def test_actual_a_and_b_levels_cash_counts_hands(self):
        for level in (1,2):
            a=create(level=level);b=create('B',level=level)
            self.assertEqual(a.world_state['inventory'].count('Handaxe'),4)
            self.assertIn("Explorer's Pack",a.world_state['inventory'])
            self.assertNotIn('4 Cirit',a.world_state['inventory'])
            self.assertEqual(a.world_state['currency']['player'],6500)
            self.assertEqual(b.world_state['inventory'],[])
            self.assertEqual(b.world_state['currency']['player'],12500)
            self.assertEqual(b.world_state['equipment'],{'main_hand':None,'off_hand':None})

    def test_materialization_unique_ids_idempotent_and_fresh_restore(self):
        s=create();eq.materialize(s.world_state)
        axes=[i for i in s.world_state['inventory'] if i.get('weapon_id')=='handaxe']
        self.assertEqual(len(axes),4)
        self.assertEqual(len({i['item_id'] for i in axes}),4)
        before=copy.deepcopy(s.world_state);eq.materialize(s.world_state)
        self.assertEqual(s.world_state,before)
        p=serialize_campaign_payload(s);t=game.create_session(seed=9);restore_campaign_session(t,p)
        self.assertEqual(serialize_campaign_payload(t),p)

    def test_unknown_background_cash_joins_the_purse_at_creation(self):
        for package,amount in (('A',3100),('B',9100)):
            s=create(package,'A')
            self.assertNotIn('16 Altın',s.world_state['inventory'])
            self.assertEqual(s.world_state.get('currency',{}).get('player'),amount)

    def test_background_extra_handaxe_not_deduped_after_expansion(self):
        # Synthetic boundary: one additional legal background item, not source claim.
        bg=copy.deepcopy(BACKGROUND_DEFINITIONS['Criminal']);bg['equipment'].append('Handaxe')
        with patch.dict(BACKGROUND_DEFINITIONS,{'Criminal':bg}):s=create('A','A')
        eq.materialize(s.world_state)
        self.assertEqual(sum(i.get('weapon_id')=='handaxe' for i in s.world_state['inventory']),5)

    def test_recreation_b_clears_stale_hands_and_replaces_only_player_wallet(self):
        s=create();s.world_state['currency']={'player':99999,'npc_other':321}
        hands=s.world_state['equipment'];hands['off_hand']='dagger'
        create('B',session=s)
        self.assertIs(s.world_state['equipment'],hands)
        self.assertEqual(hands,{'main_hand':None,'off_hand':None})
        self.assertEqual(s.world_state['currency'],{'player':12500,'npc_other':321})

    def test_certified_background_cash_and_identical_labels_each_count_once(self):
        # Synthetic collision oracle: selected background has certified15 GP,
        # plus an unrelated retained identical legacy cash label.
        bg=copy.deepcopy(BACKGROUND_DEFINITIONS['Criminal'])
        bg['equipment']=['15 GP','15 GP','Handaxe'];bg['starting_gp']=15
        with patch.dict(BACKGROUND_DEFINITIONS,{'Criminal':bg}):s=create('A','A')
        # Class 15 + certified 15 + the other written 15 (joins the purse at creation).
        self.assertEqual(s.world_state['currency']['player'],4500)
        self.assertEqual(s.world_state['inventory'].count('15 GP'),0)
        self.assertEqual(s.world_state['inventory'].count('Handaxe'),5)

    def test_historical_inventory_wallet_and_advance_do_not_regrant(self):
        s=create(level=1)
        s.world_state['inventory']=[{'item_id':'old_javelin','name':'4 Cirit'},'15 Altın']
        s.world_state['equipment']={'main_hand':None,'off_hand':None}
        s.world_state['currency']={'player':123}
        p=serialize_campaign_payload(s);t=game.create_session(seed=13);restore_campaign_session(t,p)
        self.assertEqual(serialize_campaign_payload(t),p)
        before=copy.deepcopy((t.world_state['inventory'],t.world_state['currency'],t.world_state['equipment']))
        result=cp.apply_level_choices(t,cp.preview_level_up(t,2),{})
        self.assertEqual(result['status'],'applied')
        self.assertEqual((t.world_state['inventory'],t.world_state['currency'],t.world_state['equipment']),before)

    def test_drop_one_materialized_handaxe_preserves_other_three(self):
        s=create();s.commit_location_change('tavern');eq.materialize(s.world_state)
        axes=[i for i in s.world_state['inventory'] if i.get('weapon_id')=='handaxe']
        self.assertEqual(len(axes),4)
        result=eq.execute(s,'/item drop '+axes[0]['item_id'])
        self.assertEqual(sum(i.get('weapon_id')=='handaxe' for i in s.world_state['inventory']),3)
        self.assertTrue(all(i in s.world_state['inventory'] for i in axes[1:]))

    def test_late_creation_fault_restores_all_prior_state(self):
        s=create();before=s._capture_runtime_snapshot();real=cp.apply_level_choices
        def fail_after(*args):
            real(*args)
            raise RuntimeError('synthetic after new package grant')
        with patch.object(cp,'apply_level_choices',side_effect=fail_after):
            with self.assertRaisesRegex(RuntimeError,'synthetic after'):create('B',session=s)
        self.assertEqual(s._capture_runtime_snapshot(),before)
