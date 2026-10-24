"""Job8 bound speech repair and repeat controls; synthetic only."""
import copy
import unittest
import game
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech
from unittest.mock import patch


class RepairRepetitionTests(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session(seed=2108)
        self.npc = {'id': 'speaker', 'name': 'Lysa', 'name_known_to_player': True,
                    'location': self.session.world_state['location'], 'role': 'Kent sakini'}
        self.session.world_state['npcs'] = [self.npc]
        self.action = {'action': 'dialogue', 'status': 'experimental_attributed_speech', 'npc_id': 'speaker'}

    def finish(self, spoken, stage='', question='Günün nasıl, sohbeti sever misin?'):
        payload = {'source': 'experimental_attributed_speech', 'speaker_id': 'speaker',
                   'spoken_text': spoken, 'stage_direction': stage}
        before = copy.deepcopy((self.session.character, self.session.world_state, self.session.rng.getstate()))
        token = game._ACTIVE_SESSION.set(self.session)
        try:
            text = game.finalize_narration(' '.join(p for p in (stage, spoken) if p),
                question, self.npc, self.action, attributed_speech=payload)
        finally:
            game._ACTIVE_SESSION.reset(token)
        self.assertEqual(before, (self.session.character, self.session.world_state, self.session.rng.getstate()))
        return text, payload, copy.deepcopy(self.session.last_narration_safety)

    def test_valid_bound_answer_survives_legitimate_new_turn_repeat(self):
        spoken = 'Günüm sakin geçiyor. İnsanlarla sohbet etmeyi seviyorum.'
        first, _, _ = self.finish(spoken)
        second, _, decision = self.finish(spoken, question='Bir daha söyler misin?')
        self.assertEqual(first, spoken)
        self.assertEqual(second, spoken)
        self.assertEqual(decision['handling'], 'accepted')

    def test_long_answer_keeps_valid_clause_after_invalid_stage(self):
        spoken = 'Günüm sakin geçiyor. İnsanlarla sohbet etmeyi seviyorum, çünkü farklı düşünceler duymak hoşuma gidiyor.'
        self.finish(spoken)
        text, payload, decision = self.finish(spoken, 'Elara durur.')
        self.assertEqual(text, spoken)
        self.assertEqual(payload['stage_direction'], '')
        self.assertEqual(decision['handling'], 'repaired')
        self.assertEqual(decision['reason_code'], 'UNREGISTERED_NAMED_ENTITY')

    def test_rejected_private_speech_stays_rejected_when_fallback_repeats(self):
        self.session.world_state['npcs'].append({'id':'hidden', 'name':'Quarion',
            'hidden':True, 'name_known_to_player':False, 'location':'secret'})
        raw = 'Quarion burada.'
        first, _, first_reason = self.finish(raw)
        second, _, second_reason = self.finish(raw)
        self.assertNotIn('Quarion', first)
        self.assertNotIn('Quarion', second)
        self.assertEqual(second_reason['reason_code'], first_reason['reason_code'])
        self.assertEqual(second_reason['handling'], 'python_fallback')

    def test_repair_rechecks_unsafe_remaining_speech(self):
        self.session.world_state['npcs'].append({'id':'hidden', 'name':'Quarion',
            'hidden':True, 'name_known_to_player':False, 'location':'secret'})
        text, _, decision = self.finish('Quarion burada.', 'Elara durur.')
        self.assertNotIn('Quarion', text)
        self.assertNotIn('Elara', text)
        self.assertEqual(decision['handling'], 'python_fallback')


class RepeatedAnswerApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def test_two_new_turns_keep_answers_and_replay_does_not_consume(self):
        _, sid, session, url, npc = await self.campaign_with_npc()
        protected = copy.deepcopy((session.character, session.world_state['inventory'],
            session.world_state['location'], session.world_state['doors'], session.rng.getstate()))
        answer = 'İnsanlarla sohbet etmeyi seviyorum, çünkü farklı düşünceler duymak hoşuma gidiyor.'
        client = speech.ScriptedNpcSpeechClient(narration=answer, stage_direction='Elara durur.')
        for message in ('İnsanlarla sohbet etmeyi mi seversin, tek başına kalmayı mı?', 'Peki neden?'):
            body = speech.ExperimentalNpcDialogueTests.request(npc, message=message)
            response = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn(answer, response.json()['narration'])
            self.assertNotIn('Elara', response.json()['narration'])
        self.assertEqual(client.chat_calls, 2)
        pairs = session.world_state['npc_speech_log'][npc['id']]
        self.assertEqual(len(pairs), 2)
        self.assertEqual([p['npc'] for p in pairs], [answer, answer])
        self.assertEqual(protected, (session.character, session.world_state['inventory'],
            session.world_state['location'], session.world_state['doors'], session.rng.getstate()))
        before = copy.deepcopy(session.serialize_game_state())
        with patch.object(game, 'run_player_turn', side_effect=AssertionError('replayed engine')):
            replay = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(client.chat_calls, 2)
        self.assertEqual(before, session.serialize_game_state())
