"""Mechanical regressions; mocked/offline execution is not live model acceptance."""
import copy
import unittest
from unittest.mock import patch

import campaign_time
import game
import grounded_action as grounded
import interaction_adventure
import timed_gameplay
import test_open_shop_search as open_shop_fixture


class CompanionWaitTests(unittest.TestCase):
    setUp = open_shop_fixture.OpenShopSearchTests.setUp

    def inn_scene(self, *, locked=True):
        self.world['locations']['inn'] = {
            'id': 'inn', 'name': 'Rashid Hanı', 'type': 'building',
            'parent_location_id': 'city', 'scene_kind': 'tavern',
        }
        self.world['doors'] = [{
            'id': 'venue-door:inn', 'name': 'Rashid Hanı Kapısı',
            'location': 'city', 'open': not locked, 'locked': locked, 'broken': False,
        }]
        self.world['npcs'] = [{
            'id': 'damaia', 'name': 'Damaia', 'name_known_to_player': True,
            'location': 'city', 'role': 'resident', 'current_hp': 10,
        }]
        self.text = 'Damaia ile hana doğru gidiyorum ve içeri giriyorum'

    def test_companion_is_not_destination_and_locked_entry_is_blocked(self):
        self.inn_scene()
        before = copy.deepcopy((self.world['doors'], self.world['npcs']))
        p = grounded.plan(self.session, self.text)
        self.assertEqual(p['steps'][0]['target']['id'], 'inn')
        result = self.session.run_player_turn(self.text)
        self.assertEqual(result['action_result']['action'], 'grounded_action')
        self.assertEqual([s['status'] for s in result['action_result']['steps']], ['completed', 'blocked'])
        self.assertEqual(self.world['location'], 'city')
        self.assertEqual((self.world['doors'], self.world['npcs']), before)
        self.assertIn('İçeri giremiyorsun', result['narration'])
        self.assertNotIn(interaction_adventure.KEY, self.world)
        self.assertEqual(result.get('model_calls', result.get('_engine_event_evidence', {}).get('telemetry', {}).get('total_model_calls')), 0)

    def test_open_entry_does_not_automatically_move_companion(self):
        self.inn_scene(locked=False)
        result = self.session.run_player_turn(self.text)
        self.assertEqual(self.world['location'], 'inn')
        self.assertEqual(self.world['npcs'][0]['location'], 'city')
        self.assertNotIn('companions', result['action_result'])
        self.assertEqual(result.get('model_calls', result.get('_engine_event_evidence', {}).get('telemetry', {}).get('total_model_calls')), 0)

    def test_ordinary_approach_to_person_retains_npc_binding(self):
        self.inn_scene()
        p = grounded.plan(self.session, "Damaia'ya doğru gidiyorum")
        self.assertEqual(p['steps'][0]['target']['id'], 'damaia')
        self.assertIsNone(grounded.resolve_turn(self.session, "Damaia'ya doğru gidiyorum", allow_model=False))

    def test_recorded_only_plan_is_final_without_model_narration(self):
        self.inn_scene()
        text = 'Damaia ile konuşuyorum ve sonra şarkı söylüyorum'
        self.assertIsNotNone(interaction_adventure.compound_plan(text))
        result = self.session.run_player_turn(text)
        self.assertEqual(result['action_result']['operation'], 'plan')
        self.assertEqual(result['action_result']['status'], 'recorded')
        self.assertEqual(self.world[interaction_adventure.KEY]['plan']['cursor'], 0)
        self.assertEqual(self.world[interaction_adventure.KEY]['plan']['status'], 'awaiting_confirmation')
        self.assertEqual(result['narration'], result['action_result']['direct_response'])
        self.assertIn('Bunu denemek için', result['narration'])
        self.assertEqual(self.world['location'], 'city')
        self.assertEqual(result.get('model_calls', result.get('_engine_event_evidence', {}).get('telemetry', {}).get('total_model_calls')), 0)

    def test_unknown_opening_wait_asks_duration_without_advancing(self):
        self.inn_scene(); campaign_time.initialize(self.world)
        before = copy.deepcopy((self.world['campaign_time'], self.world['doors']))
        result = timed_gameplay.resolve_input(self.session, 'han açılana kadar bekle')
        self.assertIsNotNone(result)
        self.assertEqual(result['status'], 'clarification')
        self.assertFalse(result['success'])
        self.assertIn('açılacağı', result['direct_response'])
        self.assertIn('dakika', result['direct_response'])
        self.assertEqual((self.world['campaign_time'], self.world['doors']), before)

    def test_full_turn_unknown_opening_wait_is_truthful_and_zero_call(self):
        self.inn_scene(); campaign_time.initialize(self.world)
        before = copy.deepcopy((self.world['campaign_time'], self.world['doors']))
        result = self.session.run_player_turn('han açılana kadar bekle')
        self.assertEqual(result['action_result']['status'], 'clarification')
        self.assertIn('açılacağı', result['narration'])
        self.assertEqual((self.world['campaign_time'], self.world['doors']), before)
        self.assertEqual(result.get('model_calls', result.get('_engine_event_evidence', {}).get('telemetry', {}).get('total_model_calls')), 0)

    def test_explicit_duration_still_advances_without_opening_door(self):
        self.inn_scene(); campaign_time.initialize(self.world)
        before = self.world['campaign_time']['elapsed_seconds']
        result = timed_gameplay.resolve_input(self.session, '5 dakika bekliyorum')
        self.assertEqual(self.world['campaign_time']['elapsed_seconds'], before + 300)
        self.assertTrue(self.world['doors'][0]['locked'])
        self.assertTrue(result['success'])

    def test_explicit_wait_gate_rejects_non_action_semantics(self):
        for text in ('Neden 2 saat bekle', 'Damaia dedi ki 2 saat bekle',
                     'Eğer kapı açıksa 2 saat bekle', '2 saat bekleme',
                     '2 saat bekle demiyorum', '2 saat bekle?', '"2 saat bekle"'):
            with self.subTest(text=text):
                self.assertFalse(timed_gameplay.explicit_wait_request(text))

    def test_wait_gate_does_not_absorb_other_sentences_or_clauses(self):
        for text in ('Yolcuya seslenmiyorum. Bekliyorum.',
                     'Yolcuya seslenmedim. Bekle.',
                     'Yolcuya seslenmiyorum; bekle',
                     'Yolcuya seslenmiyorum, bekle',
                     'Yolcuya seslenmiyorum ve bekle'):
            with self.subTest(text=text):
                self.assertFalse(timed_gameplay.explicit_wait_request(text))
        self.assertTrue(timed_gameplay.explicit_wait_request('Bekliyorum.'))
        self.assertTrue(timed_gameplay.explicit_wait_request('0.5 saat bekle'))
        self.assertTrue(timed_gameplay.explicit_wait_request('0,5 saat bekle'))

    def test_question_or_report_does_not_become_opening_wait(self):
        self.inn_scene(); campaign_time.initialize(self.world)
        for text in ('Han açılana kadar bekliyorum?', '"Han açılana kadar bekle" dedi.'):
            before = copy.deepcopy(self.world['campaign_time'])
            result = timed_gameplay.resolve_input(self.session, text)
            self.assertIsNone(result)
            self.assertEqual(self.world['campaign_time'], before)

from api.tests import test_dialogue_runtime as dialogue_fixture


class FreeDialogueWaitApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = dialogue_fixture.DialogueRuntimeTests.asyncSetUp
    asyncTearDown = dialogue_fixture.DialogueRuntimeTests.asyncTearDown
    setup_free = dialogue_fixture.DialogueRuntimeTests.setup_free
    send = dialogue_fixture.DialogueRuntimeTests.send

    async def test_do_wait_durations_bypass_active_npc_and_replay_once(self):
        import uuid
        await self.setup_free(); campaign_time.initialize(self.world)
        for text, seconds in [('30 dakika bekle', 1800), ('2 saat bekle', 7200),
                              ('sabaha kadar bekle', None)]:
            with self.subTest(text=text):
                before = self.world['campaign_time']['elapsed_seconds']
                expected = seconds if seconds is not None else campaign_time.until_morning(self.world)
                action = str(uuid.uuid4())
                first = await self.send(text, mode='do', action_id=action)
                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(self.world['campaign_time']['elapsed_seconds'], before + expected)
                self.assertEqual(self.reply.calls, 0)
                replay = await self.send(text, mode='do', action_id=action)
                self.assertEqual(replay.json(), first.json())
                self.assertEqual(self.world['campaign_time']['elapsed_seconds'], before + expected)

    async def test_bare_wait_asks_duration_instead_of_talking_to_npc(self):
        await self.setup_free(); campaign_time.initialize(self.world)
        for text in ('bekle', 'bekliyorum', 'han açılana kadar bekle'):
            before = copy.deepcopy(self.world['campaign_time'])
            r = await self.send(text, mode='do')
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn('dakika', r.json()['narration'])
            self.assertEqual(self.world['campaign_time'], before)
            self.assertEqual(self.reply.calls, 0)

    async def test_report_and_unpunctuated_question_remain_npc_dialogue(self):
        await self.setup_free(); campaign_time.initialize(self.world)
        for text in ('Damaia dedi ki 2 saat bekle', 'Neden 2 saat bekle'):
            with self.subTest(text=text):
                before = self.world['campaign_time']['elapsed_seconds']
                calls = self.reply.calls
                r = await self.send(text, mode='do')
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(self.reply.calls, calls + 1)
                self.assertEqual(self.world['campaign_time']['elapsed_seconds'], before + 60)

    async def test_say_wait_remains_speech_not_elapsed_wait(self):
        await self.setup_free(); campaign_time.initialize(self.world)
        before = self.world['campaign_time']['elapsed_seconds']
        r = await self.send('2 saat bekle', mode='say')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.reply.calls, 1)
        self.assertEqual(self.world['campaign_time']['elapsed_seconds'], before + 60)

    async def test_wait_failed_save_rolls_back_and_retry_then_resume_retains_time(self):
        import uuid
        from api.persistence.campaign_models import CampaignStorageError
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager
        from api.tests.auth_fixture import TEST_PLAYER
        await self.setup_free(); campaign_time.initialize(self.world)
        action = str(uuid.uuid4()); before = copy.deepcopy(self.world)
        with patch.object(self.store, 'save_campaign', side_effect=CampaignStorageError('synthetic failure')):
            failed = await self.send('30 dakika bekle', mode='do', action_id=action)
        self.assertGreaterEqual(failed.status_code, 400)
        self.assertEqual(self.world, before)
        self.assertIsNone(self.manager.get_turn_action(self.manager.get(self.session_id), action))
        good = await self.send('30 dakika bekle', mode='do', action_id=action)
        self.assertEqual(good.status_code, 200, good.text)
        self.assertEqual(self.world['campaign_time']['elapsed_seconds'], before['campaign_time']['elapsed_seconds'] + 1800)
        restarted = SessionManager(campaign_store=CampaignStore(self.store.path, bound_principal=TEST_PLAYER))
        _, record, _, _, _ = restarted.resume_campaign(self.campaign_id)
        self.assertEqual(record.game_session.world_state['campaign_time'], self.world['campaign_time'])
        self.assertIsNotNone(restarted.get_turn_action(record, action))
        self.assertEqual(self.reply.calls, 0)


if __name__ == '__main__':
    unittest.main()
