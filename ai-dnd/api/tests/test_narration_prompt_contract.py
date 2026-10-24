"""Narrow narration-only instructions; information-answer citations unchanged."""
import copy
import json
import unittest
from unittest.mock import patch
import game
import living_world
from api.tests import test_lore_authority as fixture
from api.tests.test_narration_evidence_acceptance import ask
from api.tests.test_stage10a_gameplay_repairs import city_session

class PromptRoleContractTests(unittest.TestCase):
    def setup_context(self):
        s = city_session()
        row = fixture.fact('fact:route:distance','fr:city:neverwinter','route_distance','10 miles',valid_from='1501',valid_until='1501')
        row['notes']='Neverwinter is 10 miles away.'
        registry=fixture.verified_registry(entities=[fixture.entity('fr:city:neverwinter','Neverwinter',entity_type='CITY')],facts=[row])
        context=registry.retrieve_lore_context(current_location_id='fr:city:neverwinter',player_message='route distance',campaign_year=1501)
        self.assertEqual(context['diagnostics']['selected_fact_ids'],[row['fact_id']])
        s._living_world_prompt_context(player_input='Look around.')
        return s,context,row

    def request(self,s,context,raw,only):
        with patch('game.ollama.chat',return_value={'message':{'content':json.dumps(raw)}}) as chat:
            result=ask(s,[],'Look around.',lore_context=context,narration_only=only,return_details=True,
                       action_result={'action':'explore','status':'observed','success':True,'direct_response':'Ahşap raf görünür.'})
        self.assertEqual(chat.call_count,1)
        return result,chat.call_args.kwargs

    def test_narration_only_instruction_matches_empty_claim_schema_and_receipt_role(self):
        s,context,row=self.setup_context()
        before=copy.deepcopy(s.world_state)
        result,request=self.request(s,context,{'narration':'Ahşap raf görünür.','world_updates':{},'lore_claims':[]},True)
        prompt=request['messages'][-1]['content']
        self.assertNotIn('ilgili fact_id veya override_id',prompt)
        self.assertIn('lore_claims boş kalır',prompt)
        self.assertIn('PYTHON ACTION RESULT',prompt)
        self.assertIn('yeni setting/campaign canon iddiası ekleme',prompt)
        self.assertIn(row['notes'],prompt)  # No context deletion to evade contradiction.
        self.assertEqual(request['format']['properties']['lore_claims']['maxItems'],0)
        self.assertTrue(result['valid_response'])
        self.assertEqual(result['narration'],'Ahşap raf görünür.')
        self.assertEqual(result['lore_claims'],[])
        self.assertEqual(s.world_state,before)

    def test_information_answer_keeps_loaded_citation_and_schema(self):
        s,context,row=self.setup_context()
        result,request=self.request(s,context,{'narration':row['notes'],'world_updates':{},'lore_claims':[row['fact_id']]},False)
        self.assertIn('ilgili fact_id veya override_id',request['messages'][-1]['content'])
        self.assertNotEqual(request['format']['properties']['lore_claims'].get('maxItems'),0)
        self.assertTrue(result['valid_response'])
        self.assertEqual(result['lore_claims'],[row['fact_id']])
        self.assertEqual(result['narration'],row['notes'])
        self.assertFalse(s._narration_has_unsupported_lore_claim(row['notes'],result['lore_claims'],context,s.world_state))

    def test_information_answer_invalid_or_duplicate_citation_stays_rejected(self):
        s,context,row=self.setup_context()
        before=copy.deepcopy(s.world_state)
        for claims in (['fact:unknown'],[row['fact_id'],row['fact_id']],[{'fact_id':row['fact_id']}]):
            with self.subTest(claims=claims):
                result,request=self.request(s,context,{'narration':row['notes'],'world_updates':{},'lore_claims':claims},False)
                self.assertIn('ilgili fact_id veya override_id',request['messages'][-1]['content'])
                self.assertFalse(result['valid_response'])
                self.assertEqual(result['fallback_reason_code'],'UNVERIFIED_LORE_CLAIM')
                self.assertIsNone(result['narration'])
        self.assertEqual(s.world_state,before)

    def test_visible_feature_policy_matches_native_hidden_discovered_combinations(self):
        for hidden in (None,False,True):
            for discovered in (None,False,True):
                with self.subTest(hidden=hidden,discovered=discovered):
                    f={'id':'f','name':'Raf','location':'room','description':'Boş raf.'}
                    if hidden is not None: f['hidden']=hidden
                    if discovered is not None: f['discovered']=discovered
                    world={'location':'room','locations':{'room':{'id':'room','name':'Oda'}},'features':[f]}
                    before=copy.deepcopy(world)
                    expected=not bool(hidden) and discovered is not False
                    self.assertEqual(bool(living_world.visible_features(world)),expected)
                    self.assertEqual(bool(living_world.visible_scene_facts(world)['features']),expected)
                    self.assertEqual(world,before)
