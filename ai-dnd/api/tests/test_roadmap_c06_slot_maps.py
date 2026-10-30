"""C06 slot-map encoding PREPARATION only, not production level3 support.

Future capacity is patched only in explicitly named storage tests. Every
injection/production gate test is unpatched. Literal map {1:4,2:2} is Sorcerer
Features PDF139. Eligibility remains in the real progression/save owners.
"""
import copy
import unittest
from unittest.mock import patch
import game
import spells
import character_progression as cp
from api.tests.test_roadmap_c06 import created_sorcerer, level_two_choices, SPEC
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError, CampaignValidationError


def level_two():
    s=created_sorcerer()
    assert cp.apply_level_choices(s,cp.preview_level_up(s,2),level_two_choices(s))['status']=='applied'
    return s


def spell_fields(slots):
    return {'cantrips':[],'spells':[],'spell_slots_remaining':slots}


class SlotMapTests(unittest.TestCase):
    def test_slot_map_syntax_accepts_canonical_multiple_levels(self):
        for slots in ({'1':0},{'1':4,'2':2},{'1':1,'2':0},{'9':1}):
            with self.subTest(slots=slots):
                try:spells.validate_saved_spell_fields(spell_fields(slots))
                except ValueError as error:self.fail(f'canonical encoding rejected: {error}')

    def test_slot_map_syntax_rejects_noncanonical_keys_and_counts(self):
        for slots in ({},{'0':1},{'10':1},{'01':1},{1:1},{'1':True},{'1':-1},
                      {'1':21},{'1':1.0},{'1':'1'},{'1':1,'2':None}):
            with self.subTest(slots=slots):
                with self.assertRaises(ValueError):spells.validate_saved_spell_fields(spell_fields(slots))

    def test_expanded_player_slots_rejected_with_low_level_world(self):
        s=level_two();payload=serialize_campaign_payload(s)
        payload['engine_save']['player']['spell_slots_remaining']={'1':3,'2':1}
        restored=game.create_session(seed=99);before=copy.deepcopy((restored.character,restored.world_state))
        with self.assertRaises(CampaignCorruptError):restore_campaign_session(restored,payload)
        self.assertEqual((restored.character,restored.world_state),before)

    def test_expanded_player_slots_rejected_without_world_state(self):
        s=created_sorcerer();payload=serialize_campaign_payload(s)
        payload['engine_save']['world_state'].pop('spellcasting_v1')
        payload['engine_save']['player']['spell_slots_remaining']={'1':2,'2':1}
        restored=game.create_session(seed=99);before=copy.deepcopy((restored.character,restored.world_state))
        with self.assertRaises(CampaignCorruptError):restore_campaign_session(restored,payload)
        self.assertEqual((restored.character,restored.world_state),before)

    def test_storage_roundtrip_with_explicit_future_capacity_fixture_only(self):
        s=level_two();cap=cp.capacity(s.character);cap['slots']={'1':4,'2':2}
        s.world_state['spellcasting_v1']['slots']={'1':2,'2':1}
        s.character['spell_slots_remaining']={'1':1,'2':0}  # existing mirror may lag world
        with patch.object(cp,'capacity',return_value=cap):
            try:
                payload=serialize_campaign_payload(s)
                restored=game.create_session(seed=99)
                restore_campaign_session(restored,payload)
            except (ValueError,CampaignCorruptError,CampaignValidationError) as error:self.fail(f'storage fixture rejected: {error}')
        self.assertEqual(restored.character['spell_slots_remaining'],{'1':1,'2':0})
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'],{'1':2,'2':1})
        payload['engine_save']['player']['spell_slots_remaining']['2']=2
        self.assertEqual(restored.character['spell_slots_remaining']['2'],0)
        self.assertEqual(s.character['spell_slots_remaining']['2'],0)

    def test_expanded_map_requires_exact_capacity_and_bounded_counts(self):
        s=level_two();cap=cp.capacity(s.character);cap['slots']={'1':4,'2':2}
        s.world_state['spellcasting_v1']['slots']={'1':4,'2':2}
        s.character['spell_slots_remaining']={'1':4,'2':2}
        with patch.object(cp,'capacity',return_value=cap):
            try:payload=serialize_campaign_payload(s)
            except (ValueError,CampaignValidationError) as error:self.fail(f'fixture encoding rejected: {error}')
            for slots in ({'2':1},{'1':4,'2':2,'3':1},{'1':5,'2':2},{'1':4,'2':3}):
                with self.subTest(slots=slots):
                    changed=copy.deepcopy(payload);changed['engine_save']['player']['spell_slots_remaining']=slots
                    with self.assertRaises(CampaignCorruptError):restore_campaign_session(game.create_session(seed=99),changed)

    def test_encoding_does_not_authorize_unsupported_or_unearned_levels(self):
        s=level_two()
        self.assertEqual(cp.preview_level_up(s,4)['status'],'blocked')
        before=copy.deepcopy((s.character,s.world_state))
        with self.assertRaises(ValueError):cp.create_at_level(s,SPEC,3,{})
        self.assertEqual((s.character,s.world_state),before)
        payload=serialize_campaign_payload(s)
        payload['engine_save']['player'].update(level=3,progression_level=3)
        with self.assertRaises(CampaignCorruptError):restore_campaign_session(game.create_session(seed=99),payload)
