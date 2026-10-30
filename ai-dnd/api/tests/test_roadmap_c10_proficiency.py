"""Source core-traits proficiency lifecycle; no equipment or mastery grant."""
import copy
import unittest
from unittest.mock import patch
import game
import weapon_attack
from api.persistence.campaign_models import CampaignCorruptError
from api.tests.test_roadmap_c10_rage import created, combat
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session

class ProficiencyTests(unittest.TestCase):
    def test_canonical_creation_levels_and_fresh_restore(self):
        for level in (1,2):
            s=created(level)
            self.assertEqual(s.character.get('weapon_proficiencies'),['simple','martial'])
            payload=serialize_campaign_payload(s); t=created()
            restore_campaign_session(t,payload)
            self.assertEqual(t.character['weapon_proficiencies'],['simple','martial'])
            self.assertEqual(serialize_campaign_payload(t),payload)

    def test_actual_greataxe_attack_adds_pb_not_damage_after_restore(self):
        scores={'strength':14,'dexterity':15,'constitution':13,'intelligence':10,'wisdom':12,'charisma':8}
        s,n=combat(ability_scores=scores)
        payload=serialize_campaign_payload(s); t=created();restore_campaign_session(t,payload)
        with patch('game.roll_attack',return_value=15),patch.object(t.rng,'randint',return_value=3):
            result=weapon_attack.resolve(t,'player',n['id'],'greataxe')
        self.assertTrue(result['proficient'])
        self.assertEqual(result['attack_bonus'],4)
        self.assertEqual(result['damage'],5)

    def test_explicit_canonical_ids_and_categories_survive(self):
        s=created();s.character['weapon_proficiencies']=['simple','greataxe','longsword']
        p=serialize_campaign_payload(s);t=created();restore_campaign_session(t,p)
        self.assertEqual(t.character.get('weapon_proficiencies'),['simple','greataxe','longsword'])

    def test_legacy_absence_clears_reused_session_without_grant(self):
        s=created();s.character.pop('weapon_proficiencies',None)
        p=serialize_campaign_payload(s);t=created();t.character['weapon_proficiencies']=['martial']
        restore_campaign_session(t,p)
        self.assertNotIn('weapon_proficiencies',t.character)
        self.assertEqual(serialize_campaign_payload(t),p)

    def test_malformed_present_saved_field_refuses_atomically(self):
        for bad in (None,True,'martial',['Martial'],['Great Axe'],['martial','martial'],[True],['unknown']):
            s=created();p=serialize_campaign_payload(s)
            p['engine_save']['player']['weapon_proficiencies']=bad
            t=created();before=t._capture_runtime_snapshot()
            with self.assertRaises(CampaignCorruptError):restore_campaign_session(t,p)
            self.assertEqual(t._capture_runtime_snapshot(),before)

    def test_legacy_format_may_not_silently_drop_present_capability(self):
        s=created();s.world_state.pop('rage_v1');s.world_state.pop('worn_armor_v1')
        s.character['weapon_proficiencies']=['simple','martial'];s._persisted_engine_format=3
        with self.assertRaises(ValueError):s.serialize_game_state()

    def test_grant_eligibility_is_separate_and_strict(self):
        from api.character_creation import _barbarian_weapon_proficiencies as grant
        for raw,applied in ((1,1),(2,2),(5,2)):
            self.assertEqual(grant(raw,applied),['simple','martial'])
        for raw,applied in ((True,1),('2',2),(1,2),(3,3),(2,True),(21,2)):
            with self.assertRaises(ValueError):grant(raw,applied)

    def test_recreation_as_sorcerer_clears_previous_entitlement(self):
        import character_progression as cp
        from api.tests.test_roadmap_c06 import SPEC
        s=created();cp.create_at_level(s,copy.deepcopy(SPEC),1,{})
        self.assertNotIn('weapon_proficiencies',s.character)

    def test_explicit_empty_nonproficient_control_and_absent_fallback_unchanged(self):
        for field in ([],None):
            s,n=combat();s.character['weapon_proficiencies']=field
            if field is None:s.character.pop('weapon_proficiencies')
            with patch('game.roll_attack',return_value=15),patch.object(s.rng,'randint',return_value=3):
                result=weapon_attack.resolve(s,'player',n['id'],'greataxe')
            self.assertFalse(result['proficient'])
            self.assertEqual(result['attack_bonus'],-1)

    def test_canonical_capability_present_survives_formats_four_through_six(self):
        for version in (4,5,6):
            s=created();s._persisted_engine_format=version
            s.world_state.setdefault('xp_awarded_event_ids',[])
            p=serialize_campaign_payload(s);t=created();restore_campaign_session(t,p)
            self.assertEqual(t.character['weapon_proficiencies'],['simple','martial'])
            self.assertEqual(t._persisted_engine_format,version)
