"""Own-name inflections preserve speech; other identities never gain authority."""
import copy
import unittest
from unittest.mock import patch
import npc_speech_boundary
from api.tests import test_intent_response_consistency as fixture
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient


class SpeakerIdentityInflectionTests(unittest.TestCase):
    def test_exact_and_first_person_inflections_match_bound_name(self):
        for name, claim in [('lysa', 'Lysa'), ('lysa', "Lysa'yım"), ('marek', "Marek'im"), ('omur', 'Ömür’üm'), ('orin', "Orin'im"), ('san', "Şân'ım")]:
            with self.subTest(claim=claim):
                self.assertTrue(npc_speech_boundary.matches_speaker_identity(claim, {name}))

    def test_different_name_prefix_and_other_suffixes_are_not_identity(self):
        for name, claim in [('lysa', "Zorveth'im"), ('lysa', "Lysanna'yım"), ('sel', 'Selim'), ('lysa', "Lysa'nın"), ('lysa', "Lysa'ya"), ('lysa', 'Lysayım')]:
            with self.subTest(claim=claim):
                self.assertFalse(npc_speech_boundary.matches_speaker_identity(claim, {name}))


class SpeakerIdentityHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixture.IntentResponseConsistencyTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await fixture.IntentResponseConsistencyTests.asyncTearDown(self)

    async def turn(self, message, **fields):
        return await fixture.IntentResponseConsistencyTests.turn(self, message, **fields)

    async def prepare_npc(self):
        await self.turn('Çevreme bakıyorum.')
        npc = self.world['npcs'][0]
        npc.update(name='Lysa', name_known_to_player=True)
        return npc

    async def test_real_reply_with_own_inflection_keeps_both_answer_parts(self):
        npc = await self.prepare_npc()
        spoken = "Ben Lysa'yım. Günlerim fırının dumanı, unun kokusu ve müşterilerin gürültüsüyla dolup taşıyor; işi bitirdikten sonra ise biraz nefes almak için dışarı çıkıyorum."
        client = ScriptedNpcSpeechClient(spoken)
        before = copy.deepcopy((self.session.character, self.world['inventory'], self.world['location']))
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH':'1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('Adın neydi, bir de günün nasıl geçiyor?', target_id=npc['id'])
        self.assertIn(spoken, result['narration'])
        self.assertEqual(self.session.last_narration_safety['handling'], 'accepted')
        self.assertEqual(client.chat_calls, 1)
        self.assertEqual(before, (self.session.character, self.world['inventory'], self.world['location']))

    async def test_other_inflected_identity_is_still_rejected(self):
        npc = await self.prepare_npc()
        spoken = "Ben Zorveth'im. Günüm iyi geçiyor."
        client = ScriptedNpcSpeechClient(spoken)
        before = copy.deepcopy((self.session.character, self.world['inventory'], self.world['location']))
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH':'1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('Adın neydi, bir de günün nasıl geçiyor?', target_id=npc['id'])
        self.assertNotIn('Zorveth', result['narration'])
        self.assertTrue(any(d.get('reason_code')=='WRONG_NPC_SPEAKER_ATTRIBUTION' for d in self.session.narration_safety_history))
        self.assertEqual(before, (self.session.character, self.world['inventory'], self.world['location']))

    async def test_valid_identity_does_not_hide_later_wrong_identity(self):
        npc = await self.prepare_npc()
        spoken = "Ben Lysa'yım. Ben Zorveth'im. Günüm iyi geçiyor."
        client = ScriptedNpcSpeechClient(spoken)
        with patch.dict('os.environ', {'AI_DND_NPC_SPEECH':'1'}), patch.object(self.app.state.ollama_adapter, '_client', client):
            result = await self.turn('Adın neydi, bir de günün nasıl geçiyor?', target_id=npc['id'])
        self.assertNotIn('Zorveth', result['narration'])
        self.assertTrue(any(d.get('reason_code')=='WRONG_NPC_SPEAKER_ATTRIBUTION' for d in self.session.narration_safety_history))


class PublicPlaceIdentityBoundaryTests(unittest.TestCase):
    def setUp(self):
        import game
        self.session=game.create_session(seed=7)
        self.world=self.session.world_state
        self.world['locations']['known_inn']={'id':'known_inn','name':'Hlin Hanı','type':'building','scene_kind':'tavern','description':'Sade bir salon.'}
        self.world['location']='known_inn'
        self.npc=self.session.create_npc_from_ai({'name':'Hlin','role':'Barmen','location':'known_inn','appearance':'Tezgâh arkasında duran kişi.'})
        self.npc.update(name_known_to_player=False,role_known_to_player=True)

    def decision(self,text):
        return self.session._narration_safety_decision(text,'Etrafa bakıyorum.',action_result={'action':'explore','status':'observed','success':True})

    def test_public_place_label_is_not_namesake_npc_disclosure(self):
        for text in ("Hlin Hanı'nın salonu sessiz.", 'Hlin Hanının salonu sessiz.', 'HLIN HANI sessiz.'):
            with self.subTest(text=text):
                before=copy.deepcopy(self.world)
                self.assertFalse(self.decision(text)['unsafe'])
                self.assertEqual(before,self.world)
                self.assertFalse(self.npc['name_known_to_player'])

    def test_bare_identity_remains_hidden_even_next_to_public_place_label(self):
        result=self.decision("Hlin Hanı'nın salonu sessiz. Barmen Hlin gülümsüyor.")
        self.assertTrue(result['unsafe']);self.assertEqual(result['reason_code'],'HIDDEN_NPC_IDENTITY_DISCLOSURE')

    def test_unknown_or_hidden_place_does_not_grant_exception(self):
        self.world['locations']['secret']={'id':'secret','name':'Hlin Sığınağı','hidden':True}
        for text in ('Hlin Sarayı sessiz.','Hlin Sığınağı sessiz.'):
            with self.subTest(text=text):self.assertEqual(self.decision(text)['reason_code'],'HIDDEN_NPC_IDENTITY_DISCLOSURE')
        with patch('exploration.known_locations',return_value=set()):
            self.assertEqual(self.decision('Hlin Hanı sessiz.')['reason_code'],'HIDDEN_NPC_IDENTITY_DISCLOSURE')

    def test_single_word_and_equal_full_identity_are_not_masked(self):
        self.world['locations']['known_inn']['name']='Hlin'
        self.assertEqual(self.decision('Hlin sessiz.')['reason_code'],'HIDDEN_NPC_IDENTITY_DISCLOSURE')
        self.world['locations']['known_inn']['name']='Hlin Hanı';self.npc['name']='Hlin Hanı'
        self.assertEqual(self.decision('Hlin Hanı sessiz.')['reason_code'],'HIDDEN_NPC_IDENTITY_DISCLOSURE')

    def test_public_place_exception_does_not_authorize_player_action(self):
        result=self.decision("Hlin Hanı'nın salonunda masaya oturuyorsun.")
        self.assertTrue(result['unsafe']);self.assertEqual(result['reason_code'],'INVENTED_PLAYER_ACTION')
