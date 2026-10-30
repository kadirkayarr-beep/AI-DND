"""Job4 flag-off active-focus and real exit API acceptance."""
import copy
import json
import os
import uuid
from unittest.mock import patch
from api.tests import test_campaign_api as api
from api.tests import test_experimental_npc_dialogue as speech
import game
import unittest

class DefaultFocusAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = api.CampaignApiTests.asyncSetUp
    asyncTearDown = api.CampaignApiTests.asyncTearDown
    campaign_with_npc = speech.ExperimentalNpcDialogueTests.campaign_with_npc

    async def post(self, url, client, message, **fields):
        body = dict(message=message, action_id=str(uuid.uuid4()), **fields)
        response = await api.CampaignApiTests.post_scene_turn(self, url, client, body)
        print('FOCUS_TURN', json.dumps(dict(body=body, status=response.status_code, response=response.json(), chats=client.chat_calls, schemas=client.schemas), ensure_ascii=False, default=str))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_flag_off_active_focus_preference_followup_all_modes(self):
        for flag in (None, '0'):
            for mode in (None, 'do', 'say'):
                with self.subTest(flag=flag, mode=mode), patch.dict(os.environ):
                    os.environ.pop('AI_DND_NPC_SPEECH', None)
                    if flag is not None: os.environ['AI_DND_NPC_SPEECH'] = flag
                    _, _, session, url, npc = await self.campaign_with_npc(experimental=False)
                    self.assertFalse(getattr(session, '_experimental_npc_dialogue_enabled', False))
                    intro = speech.ScriptedNpcSpeechClient('Unused')
                    await self.post(url, intro, 'Adın ne?', target_id=npc['id'])
                    self.assertEqual(intro.chat_calls, 0)
                    self.assertEqual(session.world_state['flags']['active_npc_id'], npc['id'])
                    before = copy.deepcopy((session.character, session.world_state['inventory'], npc['personal_profile'], session.world_state['location'], session.world_state['doors'], session.rng.getstate()))
                    fields = {} if mode is None else dict(interaction_mode=mode)
                    question = 'İnsanlarla sohbet etmeyi mi seversin, tek başına kalmayı mı?'
                    reply = 'İnsanlarla sohbet etmeyi tercih ederim.'
                    client = speech.ScriptedNpcSpeechClient(reply)
                    first = await self.post(url, client, question, **fields)
                    self.assertIn(reply, first['narration'])
                    self.assertEqual(client.chat_calls, 1)
                    self.assertEqual(client.schemas[0]['required'], ['spoken_text', 'stage_direction'])
                    self.assertTrue(first['narration'].startswith(npc['name']))
                    pairs = session.world_state['npc_speech_log'][npc['id']]
                    self.assertEqual(sum(p['player'] == question for p in pairs), 1)
                    contexts = []
                    original = game._experimental_npc_dialogue_context
                    def capture(*args, **kwargs):
                        result = original(*args, **kwargs)
                        contexts.append(copy.deepcopy(result))
                        return result
                    follow = speech.ScriptedNpcSpeechClient('Çünkü sohbet etmek hoşuma gidiyor.')
                    with patch.object(game, '_experimental_npc_dialogue_context', side_effect=capture):
                        second = await self.post(url, follow, 'Peki neden?', **fields)
                    self.assertIn(follow.narration, second['narration'])
                    self.assertTrue(second['narration'].startswith(npc['name']))
                    self.assertEqual(follow.chat_calls, 1)
                    self.assertEqual(follow.schemas[0]['required'], ['spoken_text', 'stage_direction'])
                    self.assertEqual(contexts[-1]['last_exchange'], dict(player=question, npc_reply=reply))
                    self.assertEqual(sum(p['player'] == 'Peki neden?' for p in session.world_state['npc_speech_log'][npc['id']]), 1)
                    self.assertEqual(before, (session.character, session.world_state['inventory'], npc['personal_profile'], session.world_state['location'], session.world_state['doors'], session.rng.getstate()))
                    self.assertEqual(session.world_state['flags']['active_npc_id'], npc['id'])

    async def test_flag_off_real_end_then_inventory_travel_and_door(self):
        for flag in (None, '0'):
            for end_mode in (None, 'do'):
                with self.subTest(flag=flag, end_mode=end_mode), patch.dict(os.environ):
                    os.environ.pop('AI_DND_NPC_SPEECH', None)
                    if flag is not None: os.environ['AI_DND_NPC_SPEECH'] = flag
                    city, _, session, url, npc = await self.campaign_with_npc(experimental=False)
                    # Canonical fixture changes before measured turns only.
                    door = session.world_state['doors'][0]
                    door['locked'] = False
                    door['open'] = False
                    door_id = door['id']
                    venue_id = door_id.removeprefix('venue-door:')
                    venue = session.world_state['locations'][venue_id]['name']
                    if 'Kılıç' not in session.world_state['inventory']: session.world_state['inventory'].append('Kılıç')
                    client = speech.ScriptedNpcSpeechClient('UNEXPECTED_MODEL')
                    await self.post(url, client, 'Adın ne?', target_id=npc['id'])
                    pairs = copy.deepcopy(session.world_state.get('npc_speech_log'))
                    fields = {} if end_mode is None else dict(interaction_mode=end_mode)
                    ended = await self.post(url, client, 'Konuşmayı bitiriyorum.', **fields)
                    self.assertEqual(ended['turn_outcome']['status'], 'conversation_ended')
                    self.assertFalse(session.world_state['flags'].get('active_npc_id'))
                    self.assertEqual(session.world_state.get('npc_speech_log'), pairs)
                    dropped = await self.post(url, client, 'Kılıcımı yere bırakıyorum.', interaction_mode='do')
                    self.assertEqual(dropped['turn_outcome']['action'], 'inventory')
                    self.assertNotIn('Kılıç', session.world_state['inventory'])
                    self.assertIn('Kılıç', session.world_state['ground_items_by_location'][city])
                    await self.post(url, client, venue + "'na gidiyorum.", interaction_mode='do')
                    entered = await self.post(url, client, 'İçeri giriyorum.', interaction_mode='do')
                    self.assertEqual(session.world_state['location'], venue_id)
                    canonical_door = next(d for d in session.world_state['doors'] if d['id'] == door_id)
                    self.assertTrue(canonical_door['open'])
                    self.assertEqual(client.chat_calls, 0)
                    self.assertFalse(session.world_state['flags'].get('active_npc_id'))


