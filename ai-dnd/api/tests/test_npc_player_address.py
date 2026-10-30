"""Known player names are usable as NPC address, not as narrator agency."""
import copy
import unittest
from unittest.mock import patch
from api.tests import test_intent_response_consistency as fixture
from api.tests.test_experimental_npc_dialogue import ScriptedNpcSpeechClient


class NpcPlayerAddressTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixture.IntentResponseConsistencyTests.asyncSetUp(self)
        await self.turn('Çevreme bakıyorum.')
        self.npc=self.world['npcs'][0];self.npc.update(name='Lysa',name_known_to_player=True)
        self.session.character['name']='Riven'
        self.enterContext(patch.dict('os.environ',{'AI_DND_NPC_SPEECH':'1'}))

    async def asyncTearDown(self):await fixture.IntentResponseConsistencyTests.asyncTearDown(self)
    async def turn(self,message,**fields):return await fixture.IntentResponseConsistencyTests.turn(self,message,**fields)
    def protected(self):return copy.deepcopy((self.session.character,self.world['inventory'],self.world['location'],self.world['doors']))
    async def spoken(self,message,speech,stage=''):
        client=ScriptedNpcSpeechClient(speech,stage_direction=stage)
        with patch.object(self.app.state.ollama_adapter,'_client',client):
            out=await self.turn(message,target_id=self.npc['id'],interaction_mode='say')
        self.assertEqual(client.chat_calls,1)
        return out
    async def introduce(self):
        before=self.client.calls
        out=await self.turn('Benim adım Riven.',target_id=self.npc['id'],interaction_mode='say')
        self.assertIn('Riven',out['narration']);self.assertEqual(self.client.calls,before)

    async def test_plain_introduction_remains_deterministic(self):
        await self.introduce()
        self.assertTrue(any('Riven' in m.get('text','') for m in self.npc['memory']))

    async def test_introduction_does_not_consume_day_question(self):
        speech='Memnun oldum Riven. Bugün günüm iyi geçiyor.';before=self.protected()
        out=await self.spoken('Benim adım Riven. Senin günün nasıl geçiyor?',speech)
        self.assertIn(speech,out['narration']);self.assertEqual(before,self.protected())
        self.assertTrue(any(m.get('speaker')=='player' and 'Riven' in m.get('text','') for m in self.npc['memory']))

    async def test_previously_disclosed_name_is_usable_by_same_npc(self):
        await self.introduce();speech='Bugün iyiyim, Riven.'
        out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?',speech)
        self.assertIn(speech,out['narration'])

    async def test_disclosed_name_survives_save_resume(self):
        await self.introduce()
        response=await self.http.post(f'/api/game/campaigns/{self.campaign_id}/save');self.assertEqual(response.status_code,200,response.text)
        response=await self.http.post(f'/api/game/campaigns/{self.campaign_id}/resume');self.assertEqual(response.status_code,200,response.text)
        self.session_id=response.json()['session_id'];self.session=self.manager.get(self.session_id).game_session;self.world=self.session.world_state
        self.npc=next(n for n in self.world['npcs'] if n['id']==self.npc['id'])
        speech='Bugün iyiyim, Riven.';out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?',speech)
        self.assertIn(speech,out['narration'])

    async def test_unknown_name_cannot_be_guessed_from_character_state(self):
        out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?','Bugün iyiyim, Riven.')
        self.assertNotIn('Riven',out['narration'])
        self.assertTrue(any(d.get('reason_code')=='PLAYER_NAME_IN_NARRATION' for d in self.session.narration_safety_history))

    async def test_other_npc_memory_does_not_authorize_address(self):
        other=self.session.create_npc_from_ai({'name':'Darin','role':'Yolcu','location':self.world['location'],'appearance':'Yol kenarında duran bir yolcu.'})
        self.session.record_npc_interaction(other,'Memnun oldum.','Benim adım Riven.',other)
        out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?','Bugün iyiyim, Riven.')
        self.assertNotIn('Riven',out['narration'])
        self.assertTrue(any(d.get('reason_code')=='NPC_MEMORY_DISCLOSURE_LEAK' for d in self.session.narration_safety_history))

    async def test_fresh_identity_and_day_are_both_answerable_after_introduction(self):
        self.npc['name_known_to_player']=False
        speech='Memnun oldum Riven. Ben Lysa. Günüm iyi geçiyor.'
        out=await self.spoken('Benim adım Riven. Senin adın ne? Günün nasıl geçiyor?',speech)
        self.assertIn(speech,out['narration']);self.assertTrue(self.npc['name_known_to_player'])

    async def test_name_address_does_not_authorize_player_movement(self):
        await self.introduce();before=self.protected()
        out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?','Riven, masaya oturuyorsun.')
        self.assertNotIn('masaya oturuyorsun',out['narration']);self.assertEqual(before,self.protected())

    async def test_known_name_in_stage_does_not_gain_speech_exemption(self):
        await self.introduce();before=self.protected()
        out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?','Bugün iyiyim, Riven.','Riven masaya oturuyor.')
        self.assertIn('Bugün iyiyim, Riven.',out['narration']);self.assertNotIn('masaya oturuyor',out['narration']);self.assertEqual(before,self.protected())

    async def test_requested_identity_still_respects_do_not_disclose(self):
        self.npc['name_known_to_player']=False
        speech='Memnun oldum Riven. Günüm iyi geçiyor.'
        out=await self.spoken('Benim adım Riven. Adını söyleme, günün nasıl geçiyor?',speech)
        self.assertIn(speech,out['narration']);self.assertNotIn('Lysa',out['narration']);self.assertFalse(self.npc['name_known_to_player'])


    async def test_disclosed_name_confirmation_keeps_full_captured_reply(self):
        self.npc['name_known_to_player']=False
        speech='Merhaba, ben Lysa. Şu sıralar fırında işlerimi bitirip biraz nefes alıyorum. Sen Riven mi? İsimlerini duyduğuma memnun oldum.'
        before=self.protected()
        out=await self.spoken('Benim adım Riven. Senin adın ne? Günün nasıl geçiyor?',speech)
        self.assertIn(speech,out['narration']);self.assertEqual(before,self.protected())

    async def test_undisclosed_name_confirmation_still_rejects_private_name(self):
        out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?','Sen Riven mi? Bugün iyiyim.')
        self.assertNotIn('Riven',out['narration'])

    async def test_confirmation_does_not_hide_prior_third_person_player_action(self):
        await self.introduce();before=self.protected()
        out=await self.spoken('Nasıl hissediyorsun, günün nasıl geçiyor?','Riven kapıya gidiyor. Sen Riven mi?')
        self.assertNotIn('kapıya gidiyor',out['narration']);self.assertEqual(before,self.protected())


class NameDisclosureMemoryTests(unittest.TestCase):
    def test_only_bounded_identity_is_stored_without_invented_npc_reply(self):
        import local_dialogue
        npc={'id':'npc-test','memory':[]}
        local_dialogue.remember_explicit_player_name(npc,'X'*101)
        local_dialogue.remember_explicit_player_name(npc,'Riven. Sana altın vermiştim')
        self.assertEqual(npc['memory'],[])
        local_dialogue.remember_explicit_player_name(npc,'Riven')
        local_dialogue.remember_explicit_player_name(npc,'Riven')
        self.assertEqual(npc['memory'],[{'speaker':'player','text':'Benim adım Riven.'}])

    def test_memory_stays_bounded(self):
        import local_dialogue
        npc={'id':'npc-test','memory':[]}
        for i in range(26):local_dialogue.remember_explicit_player_name(npc,'Name'+chr(65+i))
        self.assertEqual(len(npc['memory']),16)
        self.assertTrue(all(m['speaker']=='player' for m in npc['memory']))
