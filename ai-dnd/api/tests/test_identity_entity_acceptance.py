"""Job7 exact attribution and visible entity acceptance; no live provider."""
import copy
import json
import unittest
from unittest.mock import patch
import game
import living_world
from api.tests import test_job6_compound_trace as trace
from api.tests import test_campaign_api as api
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient
from api.tests.auth_fixture import TEST_PLAYER

class IdentityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=2108)
        self.world = self.session.world_state
        self.public = {'id':'public','name':'Lysa','name_known_to_player':True,'role':'Kent sakini','role_known_to_player':True,'location':self.world['location']}
        self.hidden = {'id':'hidden','name':'Lysa','name_known_to_player':False,'role':'Gölge casusu','role_known_to_player':False,'location':'secret_room','personal_profile':{'secret':'Kırmızı mühür yedinci kuyuda','private_lodging':'Kuzey mahzeninde'}}
        self.world['npcs'] = [self.public,self.hidden]
    def decision(self, spoken, stage='', *, speaker=None, action_npc=None, source='experimental_attributed_speech'):
        payload={'source':source,'speaker_id':speaker or 'public','spoken_text':spoken,'stage_direction':stage}
        action={'action':'dialogue','status':'experimental_attributed_speech','npc_id':action_npc or 'public'}
        text=' '.join(p for p in (stage,spoken) if p)
        before=copy.deepcopy(self.session.serialize_game_state())
        result=self.session._narration_safety_decision(text,'Adın neydi, günün nasıl?',self.public,action,attributed_speech=payload)
        self.assertEqual(before,self.session.serialize_game_state())
        print('IDENTITY_DECISION='+json.dumps({'raw':payload,'decision':result},ensure_ascii=False))
        return result
    def test_bound_public_self_identity_with_hidden_namesake(self):
        for text in ('Adım Lysa. Günüm sakin geçiyor.','Ben Lysa. Günüm iyi.','Ben Lysa\'yım. Günüm iyi.'):
            with self.subTest(text=text): self.assertFalse(self.decision(text)['unsafe'])
    def test_namesake_exception_does_not_disclose_other_identity_or_facts(self):
        for text in ('Adım Lysa. Diğer Lysa gizli odada.', 'Adım Lysa. Gölge casusu burada.', 'Adım Lysa. Kırmızı mühür yedinci kuyuda.', 'Adım Lysa. Kuzey mahzeninde.'):
            with self.subTest(text=text): self.assertTrue(self.decision(text)['unsafe'])
    def test_stage_and_wrong_provenance_do_not_receive_exception(self):
        for kwargs in ({'stage':'Lysa gizli odada durur.'},{'speaker':'hidden'},{'action_npc':'hidden'},{'source':'model'}):
            with self.subTest(kwargs=kwargs): self.assertTrue(self.decision('Adım Lysa. Günüm sakin.',**kwargs)['unsafe'])
    def test_non_namesake_hidden_name_and_wrong_speaker_remain_rejected(self):
        self.hidden['name']='Quarion'
        for text in ('Adım Quarion. Günüm sakin.','Adım Lysa. Quarion burada.','Adım Lysa. Ben Quarion.'):
            with self.subTest(text=text): self.assertTrue(self.decision(text)['unsafe'])
    def test_unknown_selected_name_does_not_get_public_namesake_exception(self):
        self.public['name_known_to_player']=False
        self.assertTrue(self.decision('Adım Lysa. Günüm sakin.')['unsafe'])
    def test_conditional_defense_cannot_invent_a_broom_or_a_counter(self):
        hlin = {"id": "hlin", "name": "Hlin", "name_known_to_player": True,
                "role": "barmen", "location": self.world["location"]}
        self.world["npcs"] = [hlin]
        shown = (
            "Hlin'in yanındaki küçük han tezgahına doğru yürüyorsun. "
            "Hlin, elindeki süpürgeyi yere vurarak tozları savuruyor. "
            "Kendinizi savunmanız gerekirse, kılıcınızdaki alevi kullanın."
        )
        decision = self.session._narration_safety_decision(
            shown,
            "O bana saldırırsa kendimi savunacağım.",
            hlin,
            {"action": "narrative", "status": "resolved"},
        )
        self.assertTrue(decision["unsafe"], decision)
        self.assertIn(decision["reason_code"], {
            "INVENTED_PLAYER_ACTION", "UNREGISTERED_PERSISTENT_OBJECT",
            "INVENTED_ITEM",
        })

    def test_reported_non_attack_cannot_be_narrated_as_a_fight(self):
        hlin = {"id": "hlin", "name": "Hlin", "name_known_to_player": True,
                "role": "barmen", "location": self.world["location"]}
        self.world["npcs"] = [hlin]
        shown = (
            "Hlin, sözlerini kesip omuz silker ve tezgâhının kenarına yaslanır; "
            "elleri cebinde kayarak hafifçe titrer: 'Saldırırsan kendimi savunacağım mı? "
            "Hah! İyi ki durdun. Yoksa şimdi bu sokakta kan izi bırakmış birisi olurdum.'"
        )
        decision = self.session._narration_safety_decision(
            shown,
            "O bana saldırırsa kendimi savunacağım.",
            hlin,
            {"action": "narrative", "status": "resolved"},
        )
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(decision["reason_code"], "REPORTED_NON_ATTACK")

    def test_reported_non_attack_can_stay_a_calm_line(self):
        hlin = {"id": "hlin", "name": "Hlin", "name_known_to_player": True,
                "role": "barmen", "location": self.world["location"]}
        self.world["npcs"] = [hlin]
        decision = self.session._narration_safety_decision(
            "Hlin başını sallar ve sözü sana bırakır.",
            "O bana saldırırsa kendimi savunacağım.",
            hlin,
            {"action": "narrative", "status": "resolved"},
        )
        self.assertFalse(decision["unsafe"], decision)

    def test_narrative_held_broom_is_rejected_without_a_player_verb(self):
        hlin = {"id": "hlin", "name": "Hlin", "name_known_to_player": True,
                "role": "barmen", "location": self.world["location"]}
        self.world["npcs"] = [hlin]
        decision = self.session._narration_safety_decision(
            "Hlin elindeki süpürgenin sapına dokundu.",
            "Eğlenmiş görünerek bir şaka yapıyorum.",
            hlin,
            {"action": "narrative", "status": "resolved"},
        )
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(decision["reason_code"], "UNREGISTERED_PERSISTENT_OBJECT")
        kettle = self.session._narration_safety_decision(
            "Tezgahındaki çaydanlıkta kaynayan suyun cızırtısı sürer.",
            "Eğlenmiş görünerek bir şaka yapıyorum.",
            hlin,
            {"action": "narrative", "status": "resolved"},
        )
        self.assertTrue(kettle["unsafe"], kettle)
        self.assertEqual(kettle["reason_code"], "UNREGISTERED_PERSISTENT_OBJECT")

    def test_failed_investigation_cannot_report_a_find(self):
        decision = self.session._narration_safety_decision(
            "Tezgahın altında paslı vida başları fark edebiliyorsunuz.",
            "Tezgâhın altını sistemli inceliyorum.",
            None,
            {"action": "skill_check", "status": "resolved",
             "skill": "Investigation", "outcome": "failure"},
        )
        self.assertTrue(decision["unsafe"], decision)
        self.assertEqual(decision["reason_code"], "SKILL_RESULT_CONTRADICTION")
        live = self.session._narration_safety_decision(
            "Tezgâhın altında tozlu bir ahşap yüzey fark edersin.",
            "Tezgâhın altını sistemli inceliyorum.",
            None,
            {"action": "skill_check", "status": "resolved",
             "skill": "Investigation", "outcome": "failure"},
        )
        self.assertTrue(live["unsafe"], live)
        self.assertEqual(live["reason_code"], "SKILL_RESULT_CONTRADICTION")

    def test_social_act_rejected_for_lore_is_not_the_rumor_shrug(self):
        token = game._ACTIVE_SESSION.set(self.session)
        try:
            line = game._rejected_lore_narration("Eğlenmiş görünerek bir şaka yapıyorum.", None)
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertNotIn("hiçbir söz sağlam", line)
        self.assertIn("belirgin bir değişiklik olmuyor", line)

    def test_named_table_beats_the_shorter_masa_alias(self):
        loc = self.world["location"]
        self.world["features"] = [
            {"id": "wood", "name": "Ahşap masa", "location": loc, "kind": "table",
             "aliases": ["masa", "ahşap masa", "bardak", "kil bardak"],
             "description": "Kenarında sıradan bir kil bardak duran sağlam bir masa."},
            {"id": "empty", "name": "Boş masa", "location": loc, "kind": "table",
             "description": "Kimsenin oturmadığı sade bir masa."},
        ]
        token = game._ACTIVE_SESSION.set(self.session)
        try:
            seated = game.resolve_scene_seating("Boş masaya oturuyorum.")
            looked = game._inspection_findings("Masada gizli bir çekmece arıyorum.", "success")
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(seated["status"], "completed", seated)
        self.assertEqual(seated["target_id"], "empty")
        self.assertNotIn("bardak", looked["text"].casefold())
        self.assertIn("seçemiyorsun", looked["text"])

    def test_successful_search_of_an_absent_counter_is_a_miss(self):
        findings = self.session._inspection_findings(
            "Tezgâhın altını sistemli inceliyorum.", "success"
        )
        self.assertIsNotNone(findings)
        self.assertFalse(findings["found"])
        self.assertIn("seçilmiyor", findings["text"])
        self.assertNotIn("yük arabası", findings["text"])
        self.assertNotIn("İncelemen başarılı", findings["text"])

    def test_broom_stage_is_not_shown(self):
        self.assertEqual(
            game._shown_stage_direction("elindeki süpürgeyi yere vurur", self.world),
            "",
        )

    def test_whole_visible_feature_and_unknown_person_are_distinct(self):
        self.world['npcs']=[]
        self.world['features']=[{'id':'path','name':'Gizli Yol','location':self.world['location'],'description':'Dar bir patika.'}]
        action={'action':'explore','status':'observed'}
        for text,unsafe in (('Gizli Yol durur.',False),('Elara durur.',True),('Yol durur.',True)):
            with self.subTest(text=text):
                result=self.session._narration_safety_decision(text,'Etrafa bakıyorum.',None,action)
                print('ENTITY_DECISION='+json.dumps({'text':text,'decision':result},ensure_ascii=False))
                self.assertEqual(result['unsafe'],unsafe)
        self.world['features'][0]['hidden']=True
        self.assertTrue(self.session._narration_safety_decision('Gizli Yol durur.','Etrafa bakıyorum.',None,action)['unsafe'])

    def test_short_and_concatenated_labels_do_not_mask_name_prefixes(self):
        import npc_speech_boundary as boundary
        self.world['npcs']=[]
        self.world['features']=[{'id':'short','name':'Ora','location':self.world['location']},
                                {'id':'path','name':'Gizli Yol','location':self.world['location']}]
        for text in ('Oran durur.', 'GizliYol durur.', 'Gizli Yolcu durur.', 'Elias Gizli Yol durur.'):
            with self.subTest(text=text):
                self.assertEqual(boundary.mask_visible_entity_labels(text,self.world),text)
        self.assertNotEqual(boundary.mask_visible_entity_labels('Ora durur.',self.world),'Ora durur.')
        self.assertTrue(self.session._narration_safety_decision('Oran durur.','Etrafa bakıyorum.',None,{'action':'explore','status':'observed'})['unsafe'])

    def test_same_label_npc_place_and_feature_does_not_hide_identity(self):
        import npc_speech_boundary as boundary
        self.world['features']=[{'id':'name','name':'Lysa','location':self.world['location']}]
        self.world['locations'][self.world['location']]={'id':self.world['location'],'name':'Lysa'}
        self.assertEqual(boundary.mask_visible_entity_labels('Lysa durur.',self.world),'Lysa durur.')
        self.assertTrue(self.decision('Diğer Lysa gizli odada.')['unsafe'])
        self.assertTrue(self.decision('Adım Lysa. Gölge casusu burada.')['unsafe'])

    def test_bound_self_name_does_not_mask_longer_or_quoted_identity(self):
        for text in ('Adım Lysandra. Günüm iyi.', 'Birisi "Ben Lysa." dedi.', 'Adım Lysa. Ben Quarion.'):
            with self.subTest(text=text): self.assertTrue(self.decision(text)['unsafe'])

class NamesakeApiTests(trace.CompoundCollisionTrace):
    # Inherits unchanged original three-mode compound oracle and exact collision fixture.
    async def test_namesake_pair_resume_replay_and_conflict(self):
        await self.turn('Çevreme bakıyorum.')
        npc=self.world['npcs'][0]; npc.update(name='Lysa',name_known_to_player=False)
        await self.turn('İsmin nedir?',target_id=npc['id'])
        self.assertEqual(self.world['npcs'][1]['name'],'Lysa')
        self.assertFalse(self.world['npcs'][1]['name_known_to_player'])
        before=copy.deepcopy((self.session.character,self.world['inventory'],self.world['location'],self.world['doors'],self.world['npcs'][1]))
        client=ScriptedNpcSpeechClient('Adım Lysa. Günüm sakin geçiyor.')
        import uuid
        body={'message':'Adın neydi, bir de günün nasıl geçiyor?','action_id':str(uuid.uuid4())}
        with patch.object(self.app.state.ollama_adapter,'_client',client):
            response=await self.http.post(f'/api/game/sessions/{self.session_id}/turn',json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn(client.narration,response.json()['narration'])
        self.assertEqual(response.json()['narration'],f'Lysa: “{client.narration}”')
        self.assertEqual(client.chat_calls,1)
        self.assertEqual(before,(self.session.character,self.world['inventory'],self.world['location'],self.world['doors'],self.world['npcs'][1]))
        self.assertEqual(self.world['flags']['active_npc_id'],npc['id'])
        pairs=copy.deepcopy(self.world['npc_speech_log'])
        self.assertEqual(len(pairs[npc['id']]),2)
        self.assertEqual(pairs[npc['id']][-1],{'player':body['message'],'npc':client.narration[:400]})
        self.assertNotIn(self.world['npcs'][1]['id'],pairs)
        self.assertEqual((await self.http.post(f'/api/game/campaigns/{self.campaign_id}/save')).status_code,200)
        manager=api.SessionManager(campaign_store=self.store)
        app=api.create_app(session_manager=manager,ollama_adapter=api.AuthenticatedOllamaAdapter(client),authenticator=api.FixedAuthenticator(TEST_PLAYER))
        async with api.httpx.AsyncClient(transport=api.httpx.ASGITransport(app=app),base_url='http://test') as http:
            resumed=await http.post(f'/api/game/campaigns/{self.campaign_id}/resume')
            self.assertEqual(resumed.status_code,200,resumed.text)
            sid=resumed.json()['session_id']; fresh=manager.get(sid).game_session
            state=copy.deepcopy(fresh.serialize_game_state()); rng=fresh.rng.getstate()
            self.assertEqual(fresh.world_state['npc_speech_log'],pairs)
            history=resumed.json()['history']
            self.assertEqual(history[-1]['narration'],response.json()['narration'])
            with patch.object(game,'run_player_turn',side_effect=AssertionError('Replay executed engine')) as engine:
                replay=await http.post(f'/api/game/sessions/{sid}/turn',json=body)
                self.assertEqual(replay.status_code,200,replay.text)
                self.assertEqual(replay.json(),{**response.json(),'session_id':sid})
                conflict=await http.post(f'/api/game/sessions/{sid}/turn',json={**body,'message':'Başka soru.'})
                self.assertEqual(conflict.status_code,409)
                engine.assert_not_called()
            self.assertEqual(fresh.serialize_game_state(),state)
            self.assertEqual(fresh.rng.getstate(),rng)
            self.assertEqual(client.chat_calls,1)
