"""Player condition/source save ownership: no inferred historical conditions."""
import copy
import unittest
from unittest.mock import patch
import game
import weapon_attack as attack
from combat_lifecycle import CombatRequestError
from api.tests.test_weapon_attack import armed, resolve
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError


class ConditionPersistenceTests(unittest.TestCase):
    def test_charm_roundtrip_still_refuses_actual_attack(self):
        for conditions in (['charmed'], {'charmed':True}):
            with self.subTest(conditions=conditions):
                s,n=armed();s.character.update(conditions=conditions,charmed_by=n['id'])
                payload=serialize_campaign_payload(s)
                restored=game.create_session(seed=99)
                restore_campaign_session(restored,payload)
                self.assertEqual(restored.character.get('conditions'),conditions)
                self.assertEqual(restored.character.get('charmed_by'),n['id'])
                before=copy.deepcopy((restored.world_state,restored.character,restored.rng.getstate()))
                with patch('game.roll_attack',side_effect=AssertionError('saved charm lost')):
                    with self.assertRaises(CombatRequestError) as error:
                        attack.resolve(restored,'player',n['id'],'Longsword')
                self.assertEqual(error.exception.code,'charmed_target_forbidden')
                self.assertEqual((restored.world_state,restored.character,restored.rng.getstate()),before)

    def test_absent_legacy_fields_clear_stale_runtime_charm(self):
        s,n=armed();s.character.pop('conditions',None);s.character.pop('charmed_by',None)
        payload=serialize_campaign_payload(s)
        restored=game.create_session(seed=99)
        restored.character.update(conditions=['charmed'],charmed_by='stale-other-campaign')
        restore_campaign_session(restored,payload)
        self.assertNotIn('conditions',restored.character)
        self.assertNotIn('charmed_by',restored.character)

    def test_disabled_dictionary_and_snapshot_do_not_alias(self):
        s,n=armed();s.character.update(conditions={'charmed':False},charmed_by=n['id'])
        payload=serialize_campaign_payload(s)
        self.assertEqual(payload['engine_save']['player'].get('conditions'),{'charmed':False})
        restored=game.create_session(seed=99)
        restored.character.update(conditions=['charmed'],charmed_by='stale')
        restore_campaign_session(restored,payload)
        self.assertEqual(restored.character.get('conditions'),{'charmed':False})
        self.assertEqual(restored.character.get('charmed_by'),n['id'])
        enemy=next(x for x in restored.world_state['npcs'] if x['id']==n['id'])
        result=resolve(restored,enemy)
        self.assertEqual(result['attack_rolls'],[10])
        payload['engine_save']['player']['conditions']['charmed']=True
        self.assertFalse(restored.character['conditions']['charmed'])
        self.assertFalse(s.character['conditions']['charmed'])

    def test_invalid_new_fields_fail_before_load_mutation(self):
        for field,value in [('conditions','charmed'),('conditions',[1]),('conditions',['']),
                            ('conditions',{'charmed':1}),('charmed_by',True),('charmed_by',[]),('charmed_by',' ')]:
            with self.subTest(field=field,value=value):
                s,n=armed();payload=serialize_campaign_payload(s)
                payload['engine_save']['player'][field]=value
                restored=game.create_session(seed=99);before=copy.deepcopy((restored.world_state,restored.character))
                with self.assertRaises(CampaignCorruptError):restore_campaign_session(restored,payload)
                self.assertEqual((restored.world_state,restored.character),before)

    def test_condition_sources_and_legacy_effect_fields_are_not_borrowed_across_load(self):
        fields={'frightened_by':'fear-source','grappled_by':'grappler','grapple_escape_dc':13,
                'prone':True,'frightened_until_player_turn':5,'speed_penalty_ft':10,
                'speed_penalty_turns_remaining':1}
        s,n=armed();s.character.update(fields)
        s.character['conditions']=['frightened','grappled']
        payload=serialize_campaign_payload(s)
        restored=game.create_session(seed=99)
        restore_campaign_session(restored,payload)
        for key,value in fields.items():self.assertEqual(restored.character.get(key),value,key)
        for key in [*fields,'conditions','charmed_by']:
            payload['engine_save']['player'].pop(key,None)
        restore_campaign_session(restored,payload)
        for key in [*fields,'conditions','charmed_by']:self.assertNotIn(key,restored.character)

    def test_invalid_condition_metadata_is_rejected_before_mutation(self):
        cases=[('frightened_by',3),('grappled_by',{}),('grapple_escape_dc',True),
               ('grapple_escape_dc',-1),('prone',1),('frightened_until_player_turn',-1),
               ('speed_penalty_ft','10'),('speed_penalty_turns_remaining',True)]
        for field,value in cases:
            with self.subTest(field=field,value=value):
                s,n=armed();payload=serialize_campaign_payload(s)
                payload['engine_save']['player'][field]=value
                restored=game.create_session(seed=99);before=copy.deepcopy((restored.world_state,restored.character))
                with self.assertRaises(CampaignCorruptError):restore_campaign_session(restored,payload)
                self.assertEqual((restored.world_state,restored.character),before)

    def test_unsupported_concentration_is_not_borrowed_or_claimed_supported(self):
        s,n=armed();payload=serialize_campaign_payload(s)
        restored=game.create_session(seed=99);restored.character['concentration']={'old-campaign':True}
        restore_campaign_session(restored,payload)
        self.assertNotIn('concentration',restored.character)
        payload['engine_save']['player']['concentration']={'unvalidated':True}
        before=copy.deepcopy((restored.world_state,restored.character))
        with self.assertRaises(CampaignCorruptError):restore_campaign_session(restored,payload)
        self.assertEqual((restored.world_state,restored.character),before)
