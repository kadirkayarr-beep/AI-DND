"""An NPC may ask about player intent; questions do not commit player state."""
import copy
import unittest
from unittest.mock import patch
import npc_speech_boundary
from api.tests import test_intent_response_consistency as fixture
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient


class QuestionMaskTests(unittest.TestCase):
    def test_only_question_in_speech_is_masked_without_offset_changes(self):
        stage='Oyuncu korkuyor. '
        speech='Artık bana güveniyorsun. Kimi demek istiyorsun?'
        masked=npc_speech_boundary.mask_spoken_questions(stage+speech,len(stage))
        self.assertEqual(len(masked),len(stage+speech))
        self.assertTrue(masked.startswith(stage+'Artık bana güveniyorsun.'))
        self.assertNotIn('istiyorsun',masked)
        self.assertEqual(npc_speech_boundary.mask_spoken_questions(stage+speech,None),stage+speech)

    def test_semicolon_does_not_hide_an_assertion_before_question(self):
        text='Masaya oturuyorsun; ne istiyorsun?'
        masked=npc_speech_boundary.mask_spoken_questions(text,0)
        self.assertIn('Masaya oturuyorsun;',masked)


class NpcQuestionHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):await fixture.IntentResponseConsistencyTests.asyncSetUp(self)
    async def asyncTearDown(self):await fixture.IntentResponseConsistencyTests.asyncTearDown(self)
    async def turn(self,message,**fields):return await fixture.IntentResponseConsistencyTests.turn(self,message,**fields)
    async def npc(self):
        await self.turn('Çevreme bakıyorum.')
        npc=self.world['npcs'][0];npc.update(name='Lysa',name_known_to_player=True);return npc

    async def test_captured_clarifying_question_is_not_invented_mental_state(self):
        npc=await self.npc()
        speech="Brom'u... Ne kadar tanıdığını bilmiyorum. Fırın çevresindeki işçilerden birisi olabilir mi? Yoksa çoktan şehir dışına giden o eski komşumuz mu demek istiyorsun?"
        client=ScriptedNpcSpeechClient(speech)
        before=copy.deepcopy((self.session.character,self.world['inventory'],self.world['location'],self.world['doors']))
        ids=[n['id'] for n in self.world['npcs']]
        with patch.dict('os.environ',{'AI_DND_NPC_SPEECH':'1'}),patch.object(self.app.state.ollama_adapter,'_client',client):
            out=await self.turn('Brom diye birini tanıyor musun?',target_id=npc['id'])
        self.assertIn(speech,out['narration'])
        self.assertEqual(self.session.last_narration_safety['handling'],'accepted')
        self.assertEqual(ids,[n['id'] for n in self.world['npcs']])
        self.assertEqual(before,(self.session.character,self.world['inventory'],self.world['location'],self.world['doors']))
        self.assertEqual(client.chat_calls,1)

    async def test_question_mark_does_not_bypass_transfer_or_identity_validation(self):
        npc=await self.npc();inventory=copy.deepcopy(self.world['inventory'])
        for speech in ('Altını sana verdim?', "Ben Zorveth'im?"):
            client=ScriptedNpcSpeechClient(speech)
            with self.subTest(speech=speech),patch.dict('os.environ',{'AI_DND_NPC_SPEECH':'1'}),patch.object(self.app.state.ollama_adapter,'_client',client):
                out=await self.turn('Günün nasıl geçiyor, bir de kendini tanıtır mısın?',target_id=npc['id'])
            self.assertNotIn(speech,out['narration']);self.assertEqual(inventory,self.world['inventory'])

    async def test_assertion_before_question_remains_rejected(self):
        npc=await self.npc();client=ScriptedNpcSpeechClient('Artık bana güveniyorsun. Kiminle konuşmak istiyorsun?')
        with patch.dict('os.environ',{'AI_DND_NPC_SPEECH':'1'}),patch.object(self.app.state.ollama_adapter,'_client',client):
            out=await self.turn('Lysa, ne söylemek istersin?',target_id=npc['id'])
        self.assertNotIn('Artık bana güveniyorsun',out['narration'])
        self.assertTrue(any(x.get('reason_code') in {'INVENTED_PLAYER_ACTION','INVENTED_PLAYER_MENTAL_STATE'} for x in self.session.narration_safety_history))

    async def test_unattributed_narration_has_no_question_exemption(self):
        npc=await self.npc()
        decision=self.session._narration_safety_decision('Ne demek istiyorsun?', 'Etrafa bakıyorum.', npc_target=npc,action_result={'action':'dialogue','status':'resolved'})
        self.assertTrue(decision['unsafe'])
        self.assertEqual(decision['reason_code'],'INVENTED_PLAYER_MENTAL_STATE')
