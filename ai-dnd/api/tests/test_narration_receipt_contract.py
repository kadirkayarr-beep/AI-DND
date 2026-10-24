"""Production-context receipt probe; no synthetic lore rows or live provider."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch
import game
from api import main
from api.tests import test_campaign_api as api
from api.tests import test_intent_response_consistency as existing
from api.tests.auth_fixture import TEST_PLAYER
from api.persistence.campaign_models import CampaignStorageError

TEXT = 'Ahşap raf üzerinde sıradan boş kavanozlar var.'

class ReceiptContractTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = existing.IntentResponseConsistencyTests.asyncSetUp
    asyncTearDown = existing.IntentResponseConsistencyTests.asyncTearDown
    known_shop = existing.IntentResponseConsistencyTests.known_shop
    turn = existing.IntentResponseConsistencyTests.turn

    def seed(self):
        city, place, door = self.known_shop()
        feature = next(f for f in self.world['features'] if f.get('location') == place['id'])
        feature['description'] = TEXT
        self.world['location'] = place['id']
        hidden = self.session.create_local_feature({'location': place['id'], 'name': 'Gizli bölme',
            'description': 'Gizli kasa burada.', 'kind': 'furnishing'})
        hidden['hidden'] = True
        undiscovered = self.session.create_local_feature({'location':place['id'],'name':'Kapalı niş','description':'Bilinmeyen niş içeriği.','kind':'furnishing'})
        undiscovered['discovered'] = False
        self.world['location'] = city
        return place, door, feature, hidden

    async def enter(self):
        place, door, feature, hidden = self.seed()
        await self.turn("Orin Dükkânı'na gidiyorum.", interaction_mode='do')
        entered = await self.turn('İçeri giriyorum.', interaction_mode='do')
        self.assertEqual(self.world['location'], place['id'])
        self.assertTrue(next(d for d in self.world['doors'] if d['id'] == door['id'])['open'])
        self.assertEqual(self.client.calls, 0)
        return place, door, feature, hidden, entered

    async def observe(self, *, failing_save=False, text=TEXT, claims=None, registry=None, message='Etrafıma bakıyorum.'):
        contexts, requests, receipts = [], [], []
        original = main._lore_context_for_turn
        original_narrate = game._narrate_resolved_turn
        def context(*args, **kwargs):
            if registry is not None:
                kwargs['registry'] = registry
            result = original(*args, **kwargs)
            contexts.append(copy.deepcopy(result))
            return result
        def narrate(*args, **kwargs):
            resolved = args[0]
            receipts.append(copy.deepcopy(vars(resolved)))
            return original_narrate(*args, **kwargs)
        def chat(*args, **kwargs):
            requests.append(copy.deepcopy(kwargs))
            return {'message': {'content': json.dumps({'narration': text, 'world_updates': {}, 'lore_claims': [] if claims is None else claims}, ensure_ascii=False)}}
        body = {'message': message, 'interaction_mode': 'do', 'action_id': str(uuid.uuid4())}
        with patch.object(main, '_lore_context_for_turn', side_effect=context), patch.object(game, '_narrate_resolved_turn', side_effect=narrate), patch.object(self.client, 'chat', side_effect=chat):
            if failing_save:
                with patch.object(self.store, 'save_campaign', side_effect=CampaignStorageError('synthetic failure')):
                    response = await self.http.post(f'/api/game/sessions/{self.session_id}/turn', json=body)
            else:
                response = await self.http.post(f'/api/game/sessions/{self.session_id}/turn', json=body)
        print('RECEIPT_PROBE=' + json.dumps({'contexts': contexts, 'requests': requests, 'receipts': receipts, 'response': response.json()}, ensure_ascii=False, default=str))
        return body, response, contexts, requests, receipts

    async def test_real_registry_visible_shelf_native_receipt_and_model_context(self):
        place, door, feature, hidden, entered = await self.enter()
        before = copy.deepcopy((self.session.character, self.world['inventory'], self.world['location'], self.world['doors']))
        body, response, contexts, requests, receipts = await self.observe()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(receipts), 1)
        self.assertTrue(contexts)
        self.assertEqual(receipts[0]['lore_context'], contexts[-1])
        self.assertIn(TEXT, str(requests[0]['messages']))
        self.assertIn('Ahşap raf', receipts[0]['action_result'].get('direct_response', ''))
        self.assertIn('Ahşap raf', response.json()['narration'])
        self.assertNotIn('Gizli kasa', response.json()['narration'])
        self.assertEqual(before, (self.session.character, self.world['inventory'], self.world['location'], self.world['doors']))

    async def test_real_receipt_save_fresh_resume_same_action_replay(self):
        await self.enter()
        body, response, _, requests, _ = await self.observe()
        self.assertEqual(response.status_code, 200, response.text)
        saved = await self.http.post(f'/api/game/campaigns/{self.campaign_id}/save')
        self.assertEqual(saved.status_code, 200, saved.text)
        history = (await self.http.get(f'/api/game/campaigns/{self.campaign_id}')).json()['history']
        manager = api.SessionManager(campaign_store=self.store)
        app = api.create_app(session_manager=manager, ollama_adapter=api.AuthenticatedOllamaAdapter(self.client), authenticator=api.FixedAuthenticator(TEST_PLAYER))
        async with api.httpx.AsyncClient(transport=api.httpx.ASGITransport(app=app), base_url='http://test') as http:
            resumed = await http.post(f'/api/game/campaigns/{self.campaign_id}/resume')
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()['history'], history)
            sid = resumed.json()['session_id']
            fresh = manager.get(sid).game_session
            before = copy.deepcopy(fresh.serialize_game_state())
            rng = fresh.rng.getstate()
            with patch.object(self.client, 'chat', side_effect=AssertionError('replay must not generate')) as chat:
                replay = await http.post(f'/api/game/sessions/{sid}/turn', json=body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), {**response.json(), 'session_id': sid})
            self.assertEqual(chat.call_count, 0)
            self.assertEqual(fresh.serialize_game_state(), before)
            self.assertEqual(fresh.rng.getstate(), rng)
            self.assertEqual((await http.get(f'/api/game/campaigns/{self.campaign_id}')).json()['history'], history)

    async def test_real_receipt_save_failure_restores_state_and_history(self):
        await self.enter()
        before = copy.deepcopy(self.session.serialize_game_state())
        history = (await self.http.get(f'/api/game/campaigns/{self.campaign_id}')).json()['history']
        _, response, _, _, _ = await self.observe(failing_save=True)
        self.assertEqual(response.status_code, 503, response.text)
        fresh = self.manager.get(self.session_id).game_session
        self.assertEqual(fresh.serialize_game_state(), before)
        self.assertEqual((await self.http.get(f'/api/game/campaigns/{self.campaign_id}')).json()['history'], history)


    async def test_both_prompt_projections_keep_visible_and_exclude_private_features(self):
        await self.enter()
        _, response, _, requests, receipts = await self.observe()
        self.assertEqual(response.status_code, 200, response.text)
        content = requests[0]['messages'][-1]['content']
        for start, end in (
            ('KOMPAKT WORLD CONTEXT (salt okunur):\n', '\n\nVERIFIED LORE AUTHORITY'),
            ('CURRENT LOCAL SCENE STATE (Python-owned, read-only):\n', '\n\nRECENT NARRATION')):
            with self.subTest(projection=start):
                projection = json.loads(content.split(start,1)[1].split(end,1)[0])
                text = json.dumps(projection['features'],ensure_ascii=False)
                self.assertIn(TEXT,text)
                self.assertNotIn('Gizli',text)
                self.assertNotIn('Bilinmeyen niş',text)
        self.assertEqual(receipts[0]['action_result']['status'],'observed')
        self.assertIn('Ahşap raf',response.json()['narration'])
    async def test_typed_selected_lore_citation_conflict_is_diagnostic_not_receipt_authority(self):
        from api.tests import test_lore_authority as fixture
        row = fixture.fact('fact:distance:current','fr:city:neverwinter','route_distance','10 miles',valid_from='1501',valid_until='1501')
        row['notes'] = 'Neverwinter is 10 miles away.'
        registry = fixture.verified_registry(entities=[fixture.entity('fr:city:neverwinter','Neverwinter',entity_type='CITY')],facts=[row])
        await self.enter()
        message = 'Neverwinter route distance hakkında bilgi ver.'
        context = main._lore_context_for_turn(self.manager.get(self.session_id),self.session,message,None,registry=registry)
        self.assertEqual(context['diagnostics']['selected_fact_ids'],[row['fact_id']])
        selected = context['sections']['official_forgotten_realms_lore'][0]
        self.assertEqual(selected['visibility'],'COMMON_KNOWLEDGE')
        self.assertEqual(selected['claim_type'],'OBJECTIVE_CANON_FACT')
        # Boundary diagnostic: this resolved receipt is explicitly synthetic.
        # It is NOT evidence that public API routes this information request here.
        action = {'action':'explore','status':'observed','success':True,'direct_response':'Ahşap raf görünür.'}
        resolved = game.ResolvedTurn(action,action['direct_response'],{'action_result':action},lore_context=context)
        self.session._living_world_prompt_context(player_input=message)
        before = copy.deepcopy(self.session.world_state)
        raw = {'narration':row['notes'],'world_updates':{},'lore_claims':[]}
        with patch('game.ollama.chat',return_value={'message':{'content':json.dumps(raw)}}) as chat:
            result = self.session._narrate_resolved_turn(resolved,message,[],None)
        request = chat.call_args.kwargs
        self.assertEqual(chat.call_count,1)
        self.assertIn(row['notes'],str(request['messages']))
        self.assertIn('ilgili fact_id veya override_id',str(request['messages']))
        self.assertEqual(request['format']['properties']['lore_claims']['maxItems'],0)
        self.assertNotEqual(result['narration'],row['notes'])
        self.assertIn('Ahşap raf',result['narration'])
        self.assertEqual(self.session.world_state,before)
        self.assertTrue(game._narration_has_unsupported_lore_claim(row['notes'],[],context,self.world))
        self.assertFalse(game._narration_has_unsupported_lore_claim(row['notes'],[row['fact_id']],context,self.world))
        print('TYPED_CITATION_DIAGNOSTIC=' + json.dumps({'context':context,'action':action,'request':request,'result':result},ensure_ascii=False,default=str))
    async def test_hidden_scene_description_is_not_sent_to_model(self):
        await self.enter()
        _, response, _, requests, _ = await self.observe()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('Gizli kasa burada.', str(requests))

    async def test_unsupported_ruler_decoration_preserves_observed_receipt(self):
        await self.enter()
        before = copy.deepcopy((self.session.character, self.world['inventory'], self.world['location'], self.world['doors']))
        _, response, _, _, receipts = await self.observe(text='King Zargoth rules Neverwinter.')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(receipts[0]['action_result']['status'], 'observed')
        self.assertTrue(receipts[0]['action_result']['success'])
        self.assertIn('Ahşap raf', response.json()['narration'])
        self.assertNotIn('Zargoth', response.json()['narration'])
        self.assertEqual(before, (self.session.character, self.world['inventory'], self.world['location'], self.world['doors']))

    async def test_explicit_invalid_claim_is_not_recovered_from_scene_text(self):
        await self.enter()
        _, response, _, _, receipts = await self.observe(claims=['fact:unloaded:forged'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json()['narration'], TEXT)
        self.assertIn('Ahşap raf', response.json()['narration'])
        self.assertTrue(receipts[0]['action_result']['success'])

class TypedRegistryContractTests(unittest.TestCase):
    def build(self):
        from api.tests import test_lore_authority as fixture
        from api.lore_authority import CampaignLoreState
        rows = []
        for fid, subject, visibility, kind in (
            ('fact:public', 'city:a', 'COMMON_KNOWLEDGE', 'OBJECTIVE_CANON_FACT'),
            ('fact:foreign', 'city:b', 'COMMON_KNOWLEDGE', 'OBJECTIVE_CANON_FACT'),
            ('fact:secret', 'city:a', 'DM_SECRET', 'SECRET_DM_LEVEL_FACT'),
            ('fact:npc', 'city:a', 'DISCOVERABLE_SECRET', 'OBJECTIVE_CANON_FACT'),
            ('fact:rumor', 'city:a', 'COMMON_KNOWLEDGE', 'CANONICAL_RUMOR')):
            row = fixture.fact(fid, subject, fid.split(':')[-1] + '_distance', '10 miles', visibility=visibility, claim_type=kind)
            row['notes'] = 'The city is 10 miles away.'
            rows.append(row)
        registry = fixture.verified_registry(entities=[fixture.entity('city:a','City A',entity_type='CITY'),fixture.entity('city:b','City B',entity_type='CITY')], facts=rows)
        state = CampaignLoreState.from_mapping({'binding_status':'BOUND','setting_profile':'TEST_SETTING','world_id':'world:test','epoch_id':'epoch:test','region_id':'region:test','current_location_entity_id':'city:a','player_known_fact_ids':[],'npc_known_fact_ids':{'npc:a':['fact:npc']},'campaign_overrides':[],'procedural_entity_refs':[],'lore_discoveries':[]})
        return registry, state, rows

    def test_real_typed_audience_and_subject_filtering_does_not_authorize_same_notes(self):
        registry, state, rows = self.build()
        packet = registry.retrieve_lore_context(current_location_id='city:a', campaign_state=state)
        actual = packet['sections']['official_forgotten_realms_lore']
        ids = {r['fact_id'] for r in actual}
        self.assertIn('fact:public', ids)
        self.assertNotIn('fact:foreign', ids)
        self.assertNotIn('fact:secret', ids)
        self.assertNotIn('fact:npc', ids)
        rumor = next(r for r in actual if r['fact_id']=='fact:rumor')
        self.assertEqual(rumor['claim_type'], 'CANONICAL_RUMOR')
        self.assertTrue(all(r['visibility'] == 'COMMON_KNOWLEDGE' for r in actual))
        self.assertFalse(game._lore_claims_are_supported(['fact:foreign'], packet))
        self.assertFalse(game._lore_claims_are_supported(['fact:public','fact:public'], packet))
        self.assertTrue(game._narration_has_unsupported_lore_claim('The city is 10 miles away.', [], packet, {'locations':{},'npcs':[],'features':[]}))
        npc_packet = registry.retrieve_lore_context(current_location_id='city:a', campaign_state=state, target_npc_id='npc:a')
        self.assertIn('fact:npc', {r['fact_id'] for r in npc_packet['sections']['npc_known_lore']})
        self.assertNotIn('fact:secret', {r['fact_id'] for r in npc_packet['sections']['official_forgotten_realms_lore']})
        print('TYPED_REGISTRY_PROBE=' + json.dumps({'rows':rows,'narrator':packet,'npc':npc_packet},ensure_ascii=False))

    def test_duplicate_id_conflicting_subject_is_rejected_by_registry(self):
        from api.tests import test_lore_authority as fixture
        registry, state, rows = self.build()
        changed = copy.deepcopy(rows[0])
        changed.update(subject_id='city:b', visibility='DM_SECRET')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            fixture.verified_registry(entities=[fixture.entity('city:a','City A',entity_type='CITY'),fixture.entity('city:b','City B',entity_type='CITY')], facts=rows+[changed])

class ExactSkillReceiptTests(unittest.TestCase):
    def test_rejected_lore_keeps_exact_skill_result_and_protected_state(self):
        from api.tests.test_skill_result_pipeline_regression import city_session
        for d20 in (2,20):
            with self.subTest(d20=d20):
                session = city_session()
                session.initialize_species_trait_state()
                before = copy.deepcopy((session.character, session.world_state['inventory'], session.world_state['location']))
                bad = {'world_updates':{},'narration':'King Zargoth rules Neverwinter.','lore_claims':[{'fact_id':'unverified:ruler'}]}
                with patch('game.roll_d20',return_value=d20), patch('game.ollama.chat',return_value={'message':{'content':json.dumps(bad)}}) as chat:
                    result = session.run_player_turn('Köşede gizlenmeye çalışıyorum.',interaction_mode='do')
                action = result['action_result']
                self.assertEqual(action['action'],'skill_check')
                self.assertEqual(action['skill'],'Stealth')
                self.assertEqual(action['status'],'resolved')
                self.assertEqual(action['success'], d20==20)
                print('SKILL_STATE_PROBE=' + json.dumps({'before':before,'after':(session.character,session.world_state['inventory'],session.world_state['location']),'action':action,'telemetry':result['_engine_event_evidence']['telemetry']},ensure_ascii=False))
                self.assertEqual(before, (session.character, session.world_state['inventory'], session.world_state['location']))
                self.assertNotIn('Zargoth',result['narration'])
                self.assertEqual(result['_engine_event_evidence']['telemetry']['fallback_reason'],'UNVERIFIED_LORE_CLAIM')
                self.assertLessEqual(chat.call_count,2)
                print('SKILL_RECEIPT_PROBE=' + json.dumps({'d20':d20,'action':action,'narration':result['narration'],'telemetry':result['_engine_event_evidence']['telemetry']},ensure_ascii=False))





