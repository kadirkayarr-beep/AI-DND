"""C06 real unpatched Sorcerer3 progression STATE, not subclass-effect/playability acceptance.
Source table PDF139:4cantrips,6ordinaryprepared,slots4/2,PB2; subclass choicePDF140.
"""
import copy
import unittest
from unittest.mock import patch
import game
import character_progression as cp
import spell_scope
import xp
from api.tests.test_roadmap_c06 import created_sorcerer, SPEC
from api.dnd_2024_rules import SPELLS_CATALOG
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError

IDS=['phb2024:subclass:sorcerer:'+x for x in ('aberrant-sorcery','clockwork-sorcery','draconic-sorcery','wild-magic-sorcery')]
TWO={'prepared_spells':['Burning Hands','Chromatic Orb'],'metamagic':['Quickened Spell','Twinned Spell']}


def two():
    s=created_sorcerer()
    assert cp.apply_level_choices(s,cp.preview_level_up(s,2),copy.deepcopy(TWO))['status']=='applied'
    return s


def choices(identity=IDS[0]):
    return {'prepared_spells':['Disguise Self','Detect Magic'],'subclass_id':identity}


def three(identity=IDS[0]):
    s=two();delta=cp.apply_level_choices(s,cp.preview_level_up(s,3),choices(identity))
    assert delta['status']=='applied',delta
    return s


class LevelThreeTests(unittest.TestCase):
    def test_level_three_has_six_source_list_choices_without_forcing_legacy_chaos_bolt(self):
        names={s['id'] for s in SPELLS_CATALOG['Sorcerer']['spells_level_1']}
        self.assertTrue({'Magic Missile','Shield','Burning Hands','Chromatic Orb','Disguise Self','Detect Magic'}<=names)
        self.assertIn('Chaos Bolt',names,'legacy option must not be silently deleted')

    def test_preview_level_three_is_pure_and_requires_subclass(self):
        s=two();before=s._capture_runtime_snapshot();p=cp.preview_level_up(s,3)
        self.assertEqual(p['status'],'ready');self.assertEqual(s._capture_runtime_snapshot(),before)
        self.assertEqual(p['choices_required'],{'prepared_spells':2,'subclass_id':1})
        self.assertEqual(p['capacity'],{'cantrips':4,'prepared_spells':6,'slots':{'1':4,'2':2},'sorcery_points':3})
        for name in ('Innate Sorcery','Font of Magic','Metamagic','subclass'):
            self.assertIn(name.casefold(),' '.join(p['effects_pending']).casefold())

    def test_apply_preserves_spent_slots_choices_and_opens_second_bucket(self):
        s=two();s.world_state['spellcasting_v1']['slots']['1']=1
        old=copy.deepcopy(s.character);prepared=list(s.world_state['spellcasting_v1']['prepared']);p=cp.preview_level_up(s,3)
        result=cp.apply_level_choices(s,p,choices())
        self.assertEqual(result['status'],'applied');self.assertTrue(result['effects_pending'])
        self.assertEqual((s.character['level'],s.character['progression_level'],s.character['proficiency_bonus']),(3,3,2))
        self.assertEqual(s.character['subclass_id'],IDS[0])
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':2,'2':2})
        self.assertEqual(s.world_state['spellcasting_v1']['prepared'],prepared+['Disguise Self','Detect Magic'])
        self.assertEqual(s.character['metamagic'],old['metamagic'])
        self.assertEqual(s.character['cantrips'],old['cantrips'])
        self.assertEqual(s.character['max_hp']-old['max_hp'],6)
        snapshot=s._capture_runtime_snapshot()
        self.assertEqual(cp.apply_level_choices(s,p,choices())['status'],'rejected')
        self.assertEqual(s._capture_runtime_snapshot(),snapshot)

    def test_missing_invalid_or_replayed_choices_never_mutate(self):
        for bad in ({'prepared_spells':['Disguise Self','Detect Magic']},choices('wrong'),choices(['bad']),
                    {'prepared_spells':['Magic Missile','Detect Magic'],'subclass_id':IDS[0]}):
            with self.subTest(bad=bad):
                s=two();p=cp.preview_level_up(s,3);self.assertEqual(p['status'],'ready')
                before=s._capture_runtime_snapshot();self.assertEqual(cp.apply_level_choices(s,p,bad)['status'],'rejected')
                self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_xp_pending_level_three_keeps_level_two_until_choices_apply(self):
        s=two();xp.apply_xp(s.character,s.world_state,900,'quest:level3')
        hp=s.character['max_hp'];self.assertEqual(s.character['level'],3)
        self.assertEqual(cp.slot_capacity(s.character),{'1':3})
        self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,3),choices())['status'],'applied')
        self.assertEqual(s.character['max_hp'],hp)
        self.assertEqual(cp.slot_capacity(s.character),{'1':4,'2':2})

    def test_partial_xp_jump_to_three_pays_only_one_remaining_hp_gain(self):
        for award,gain in ((300,6),(900,0)):
            with self.subTest(award=award):
                s=created_sorcerer();self.assertEqual(s.character['constitution'],14)
                xp.apply_xp(s.character,s.world_state,award,'quest:partial-level3');hp=s.character['max_hp']
                p=cp.preview_level_up(s,3);self.assertEqual(p['status'],'ready');self.assertEqual(p['hit_points']['gain'],gain)
                all_choices={'prepared_spells':['Burning Hands','Chromatic Orb','Disguise Self','Detect Magic'],
                             'metamagic':TWO['metamagic'],'subclass_id':IDS[0]}
                self.assertEqual(cp.apply_level_choices(s,p,all_choices)['status'],'applied')
                self.assertEqual(s.character['max_hp'],hp+gain)
                self.assertEqual(cp.apply_level_choices(s,p,all_choices)['status'],'rejected')
                self.assertEqual(s.character['max_hp'],hp+gain)

    def test_all_four_subclass_ids_apply_and_roundtrip(self):
        for identity in IDS:
            with self.subTest(identity=identity):
                s=three(identity);payload=serialize_campaign_payload(s);restored=game.create_session(seed=99)
                restore_campaign_session(restored,payload)
                self.assertEqual(restored.character['subclass_id'],identity)
                self.assertEqual(restored.world_state['spellcasting_v1'],s.world_state['spellcasting_v1'])

    def test_real_level_three_roundtrip_and_rest_keep_both_slot_levels(self):
        s=three();s.commit_location_change('tavern')
        s.world_state['spellcasting_v1']['slots']={'1':1,'2':0};s.character['spell_slots_remaining']={'1':1,'2':0}
        restored=game.create_session(seed=99);restore_campaign_session(restored,serialize_campaign_payload(s))
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'],{'1':1,'2':0})
        self.assertEqual(restored.character['spell_slots_remaining'],{'1':1,'2':0})
        restored.resolve_species_trait_action('long_rest')
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'],{'1':4,'2':2})

    def test_missing_invalid_or_unearned_subclass_save_is_rejected(self):
        s=three();payload=serialize_campaign_payload(s)
        for mode in ('missing','wrong-class','without-progression','below-three','boolean-level','duplicate-metamagic'):
            with self.subTest(mode=mode):
                bad=copy.deepcopy(payload);p=bad['engine_save']['player']
                if mode=='missing':p.pop('subclass_id')
                elif mode=='wrong-class':p['subclass_id']='phb2024:subclass:wizard:evoker'
                elif mode=='without-progression':p.pop('progression_level')
                elif mode=='below-three':p['progression_level']=2
                elif mode=='boolean-level':p['progression_level']=True
                else:p['metamagic']=['Quickened Spell','Quickened Spell']
                restored=game.create_session(seed=99);before=restored._capture_runtime_snapshot()
                with self.assertRaises(CampaignCorruptError):restore_campaign_session(restored,bad)
                self.assertEqual(restored._capture_runtime_snapshot(),before)

    def test_old_save_clears_stale_subclass(self):
        payload=serialize_campaign_payload(two());restored=game.create_session(seed=99)
        restored.character['subclass_id']=IDS[1];restore_campaign_session(restored,payload)
        self.assertNotIn('subclass_id',restored.character)

    def test_create_at_three_uses_same_choices_and_rolls_back_invalid_final_choice(self):
        s=game.create_session(seed=99)
        try:cp.create_at_level(s,SPEC,3,{'2':copy.deepcopy(TWO),'3':choices()})
        except ValueError as error:self.fail(f'valid level3 creation rejected: {error}')
        self.assertEqual((s.character['level'],s.character['progression_level'],s.character['subclass_id']),(3,3,IDS[0]))
        s.character['hit_dice']={'spent':2,'window_second':None,'hp':None}
        s.world_state.setdefault('flags',{})['sentinel']='retained';s.messages.append({'role':'user','content':'retained'})
        s.recent_dm_narrations.append('retained');s._xp_level_up={'sentinel':True}
        before=s._capture_runtime_snapshot();containers=[s.character,s.world_state,s.messages,s.recent_dm_narrations]
        original=cp.apply_level_choices
        with patch.object(cp,'apply_level_choices',wraps=original) as apply:
            with self.assertRaises(ValueError):cp.create_at_level(s,SPEC,3,{'2':copy.deepcopy(TWO),'3':choices('bad')})
        self.assertIn(3,[call.args[1].get('to_level') for call in apply.call_args_list])
        self.assertEqual(s._capture_runtime_snapshot(),before)
        for old,new in zip(containers,[s.character,s.world_state,s.messages,s.recent_dm_narrations]):self.assertIs(old,new)
        cp.create_at_level(s,SPEC,1)
        self.assertEqual(s.character['progression_level'],1)
        self.assertNotIn('metamagic',s.character);self.assertNotIn('subclass_id',s.character)
        self.assertNotIn('hit_dice',s.character)

    def test_level_five_requires_prior_choices_no_full_subclass_support(self):
        s=three();self.assertEqual(cp.preview_level_up(s,5)['status'],'blocked')
        self.assertEqual(cp.MAX_SUPPORTED_LEVEL,5)

    def test_existing_level_one_spell_stays_castable_at_real_level_three(self):
        from api.tests.test_spell_scope import caster
        import spell_registry
        s,enemy=caster()
        self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,2),copy.deepcopy(TWO))['status'],'applied')
        self.assertEqual(cp.apply_level_choices(s,cp.preview_level_up(s,3),choices())['status'],'applied')
        with patch.object(s.rng,'randint',return_value=2):
            delta=spell_registry.cast_spell('Magic Missile',{'session':s},1,{'target_id':enemy['id']})
        self.assertEqual(delta['status'],'applied')
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':3,'2':2})
        restored=game.create_session(seed=99);restore_campaign_session(restored,serialize_campaign_payload(s))
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'],{'1':3,'2':2})

    def test_subclass_guard_rejects_injection_into_otherwise_valid_low_level_payloads(self):
        for session in (created_sorcerer(),two()):
            with self.subTest(level=session.character['level']):
                payload=serialize_campaign_payload(session)
                payload['engine_save']['player']['subclass_id']=IDS[0]
                restored=game.create_session(seed=99);before=restored._capture_runtime_snapshot()
                with self.assertRaises(CampaignCorruptError):restore_campaign_session(restored,payload)
                self.assertEqual(restored._capture_runtime_snapshot(),before)
