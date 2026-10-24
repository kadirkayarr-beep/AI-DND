import copy
import json
import unittest
from unittest.mock import patch
import game
from api.tests.test_stage10a_gameplay_repairs import city_session

TEXT = "Neverwinter is 10 miles away."
FACT = "fact:synthetic:lord"

def context():
    ctx = game._empty_lore_authority_context()
    ctx['sections']['official_forgotten_realms_lore'] = [dict(
        fact_id=FACT,subject_id='fr:city:neverwinter',predicate='distance',
        object_id_or_value='10 miles',notes=TEXT)]
    ctx['sections']['verified_entities'] = [
        dict(entity_id='fr:city:neverwinter',canonical_name='Neverwinter',aliases=[]),
        dict(entity_id='person:dagult',canonical_name='Dagult Neverember',aliases=[])]
    return ctx

def ask(session, *args, **kwargs):
    # Some legacy tests replace the module function with an unbound wrapper.
    # Bind the test session explicitly; do not mutate or repair product globals.
    token=game._ACTIVE_SESSION.set(session)
    try:
        return game.ask_dungeon_master(*args, **kwargs)
    finally:
        game._ACTIVE_SESSION.reset(token)

class NarrationEvidenceTests(unittest.TestCase):
    def test_empty_claims_drop_loaded_fact_at_current_guard(self):
        ctx=context(); s=city_session()
        # Diagnostic: raw text identical, only explicit citation changes.
        self.assertTrue(s._narration_has_unsupported_lore_claim(TEXT,[],ctx,s.world_state))
        self.assertFalse(s._narration_has_unsupported_lore_claim(TEXT,[FACT],ctx,s.world_state))
        s._living_world_prompt_context(player_input="Look around.")
        before=copy.deepcopy(s.world_state)
        action=dict(action='explore',status='observed',success=True,direct_response='The street is quiet.')
        resolved=game.ResolvedTurn(action,'The street is quiet.',dict(action_result=action),lore_context=ctx)
        with patch('game.ollama.chat',return_value={'message':{'content':json.dumps(dict(narration=TEXT,world_updates={},lore_claims=[]))}}) as model:
            result=s._narrate_resolved_turn(resolved,'Look around.',[],None)
        self.assertEqual(result['narration'],TEXT)
        self.assertEqual(model.call_count,1)
        self.assertEqual(s.world_state,before)

    def test_narration_only_prompt_has_no_incompatible_citation_order(self):
        s=city_session(); ctx=context()
        with patch('game.ollama.chat',return_value={'message':{'content':json.dumps(dict(narration=TEXT,world_updates={},lore_claims=[]))}}) as model:
            packet=ask(s,[], 'Look around.', lore_context=ctx,narration_only=True,return_details=True)
        request=model.call_args.kwargs
        self.assertEqual(request['format']['properties']['lore_claims']['maxItems'],0)
        prompt=request['messages'][-1]['content']
        self.assertIn(TEXT,prompt)
        self.assertNotIn('ilgili fact_id veya override_id',prompt)
        self.assertEqual(packet['lore_claims'],[])

    def test_exact_evidence_rejects_private_nonfact_and_foreign_npc_rows(self):
        from api.lore_authority.claim_authorization import exact_narration_evidence_ids as select
        for section in ('npc_known_lore','unknown_or_unloaded','procedural_local_content'):
            ctx=context(); row=ctx['sections']['official_forgotten_realms_lore'].pop()
            ctx['sections'][section]=[row]
            self.assertEqual(select(TEXT,ctx),[])
        for field,value in (('hidden',True),('visibility','secret'),('claim_type','rumor')):
            ctx=context();ctx['sections']['official_forgotten_realms_lore'][0][field]=value
            self.assertEqual(select(TEXT,ctx),[])
        self.assertEqual(select(TEXT+' A secret king rules here.',context()),[])
        self.assertEqual(select(TEXT.replace('10','20'),context()),[])

    def test_bad_claims_and_unloaded_fact_stay_rejected(self):
        s=city_session(); ctx=context()
        for ids in ([FACT,FACT],['unloaded'],[{'fact_id':FACT}]):
            self.assertFalse(s._lore_claims_are_supported(ids,ctx))
        empty=game._empty_lore_authority_context()
        self.assertTrue(s._narration_has_unsupported_lore_claim(TEXT,[],empty,s.world_state))
        self.assertTrue(s._narration_has_unsupported_lore_claim('King Vharion rules Neverwinter.',[],ctx,s.world_state))

    def test_invalid_packet_cannot_gain_authority_from_matching_text(self):
        s=city_session()
        s._living_world_prompt_context(player_input="Look around.")
        before=copy.deepcopy(s.world_state)
        action=dict(action='explore',status='observed',success=True,direct_response='The street is quiet.')
        resolved=game.ResolvedTurn(action,'The street is quiet.',dict(action_result=action),lore_context=context())
        with patch('game.ollama.chat',return_value={'message':{'content':json.dumps(dict(narration=TEXT,world_updates={},lore_claims=['unloaded']))}}) as model:
            result=s._narrate_resolved_turn(resolved,'Look around.',[],None)
        self.assertNotEqual(result['narration'],TEXT)
        self.assertEqual(model.call_count,1)
        self.assertEqual(s.world_state,before)

    def test_non_narration_prompt_keeps_citation_contract(self):
        s=city_session()
        with patch('game.ollama.chat',return_value={'message':{'content':json.dumps(dict(narration=TEXT,world_updates={},lore_claims=[FACT]))}}) as model:
            packet=ask(s,[], 'Look around.',lore_context=context(),return_details=True)
        self.assertIn('ilgili fact_id veya override_id',model.call_args.kwargs['messages'][-1]['content'])
        self.assertEqual(packet['lore_claims'],[FACT])

    def test_freeze_authorization_denial_is_not_bypassed(self):
        s=city_session();s._living_world_prompt_context(player_input='Look around.')
        before=copy.deepcopy(s.world_state)
        action=dict(action='explore',status='observed',success=True,direct_response='The street is quiet.')
        resolved=game.ResolvedTurn(action,'The street is quiet.',dict(action_result=action),lore_context=context())
        def authorization(ids, ctx):
            return ids == []
        with patch('api.lore_authority.claim_authorization.freeze_claims_authorized',side_effect=authorization), patch('game.ollama.chat',return_value={'message':{'content':json.dumps(dict(narration=TEXT,world_updates={},lore_claims=[]))}}):
            result=s._narrate_resolved_turn(resolved,'Look around.',[],None)
        self.assertNotEqual(result['narration'],TEXT)
        self.assertEqual(s.world_state,before)

    def test_npc_bound_turn_does_not_borrow_narrator_evidence(self):
        from api.lore_authority.claim_authorization import exact_narration_evidence_ids
        s=city_session()
        npc=dict(id='npc:synthetic',name='Rana',role='merchant',location=s.world_state['location'],memory=[])
        s.world_state['npcs'].append(npc)
        action=dict(action='dialogue',status='resolved',npc_id=npc['id'])
        resolved=game.ResolvedTurn(action,'No answer.',dict(action_result=action),lore_context=context(),npc_target=npc)
        with patch('api.lore_authority.claim_authorization.exact_narration_evidence_ids',wraps=exact_narration_evidence_ids) as select, patch('game.ollama.chat',return_value={'message':{'content':json.dumps(dict(narration=TEXT,world_updates={},lore_claims=[]))}}) as model:
            result=s._narrate_resolved_turn(resolved,'What do you know?',[],npc['id'])
        select.assert_not_called()
        self.assertNotEqual(result['narration'],TEXT)
        self.assertEqual(model.call_count,1)
