"""Synthetic regression cases: presentation only, not live acceptance evidence."""
import copy
import unittest
from unittest.mock import patch

import action_economy as ae
import spell_scope
from combat_lifecycle import CombatRequestError
from api.tests.test_combat_lifecycle import ready
from api.tests.test_bounded_encounter import NativeBase
from api.tests import test_living_world_v2_foundation as opening_fixtures
from api.opening_narrative import initialize_campaign_opening


class ResolvedNarrationTests(unittest.TestCase):
    def test_read_only_ordered_results_do_not_invent_dash_motion_or_target_identity(self):
        session, npc = ready()
        steps = [{"kind": "dash", "movement_added_ft": 30},
                 {"kind": "move", "distance_ft": 10}, {"kind": "ready"},
                 {"kind": "attack", "result": {"outcome": "miss"}},
                 {"kind": "attack", "result": {"outcome": "hit", "target_id": npc["id"], "damage": 3}},
                 {"kind": "magic", "result": {"spell_id": "Fire Bolt", "hit": True,
                    "target_id": "private-target-id", "damage": 4}}]
        before = copy.deepcopy((session.serialize_game_state(), session.rng.getstate(), session.messages, steps))
        with patch('game.ollama.chat', side_effect=AssertionError('no model')):
            text = ae.resolved_narration(session, steps)
        expected = ['Bu tur 30 feet daha hareket edebilirsin.', '10 feet ilerlersin.',
                    'Belirlediğin an için hazır bekliyorsun.', 'Saldırın hedefi ıskalar.',
                    '3 hasar.', 'Fire Bolt hedefe 4 hasar verir.']
        self.assertEqual([text.index(part) for part in expected], sorted(text.index(part) for part in expected))
        self.assertNotIn('private-target-id', text)
        self.assertNotIn('Python', text)
        self.assertEqual(before, (session.serialize_game_state(), session.rng.getstate(), session.messages, steps))
        self.assertEqual(ae.resolved_narration(session, [{"kind":"dash", "movement_added_ft":0}]),
                         'Bu hamle sana ek hareket sağlamaz.')

    def test_dash_executes_once_without_moving_rng_or_model_and_failed_compound_rolls_back(self):
        session, _ = ready()
        before_rng = session.rng.getstate()
        before_position = copy.deepcopy(session.world_state.get('scene_state'))
        with patch('game.ollama.chat', side_effect=AssertionError('no model')):
            result = ae.execute(session, {'steps':[{'kind':'dash'}]})
        self.assertEqual(result['model_calls'], 0)
        self.assertIn('daha hareket edebilirsin', result['narration'])
        self.assertEqual(session.rng.getstate(), before_rng)
        self.assertEqual(session.world_state.get('scene_state'), before_position)
        self.assertEqual(ae.ensure(session)['player']['dash_count'], 1)
        before = copy.deepcopy((session.serialize_game_state(), session.rng.getstate(), session.messages))
        with self.assertRaises(CombatRequestError):
            ae.execute(session, {'steps':[{'kind':'move','distance_ft':5},{'kind':'dash'}]})
        self.assertEqual(before, (session.serialize_game_state(), session.rng.getstate(), session.messages))

    def test_presentation_enabled_and_disabled_have_identical_mechanics_and_rng(self):
        session, _ = ready()
        control = copy.deepcopy(session)
        command = {'steps':[{'kind':'dash'}, {'kind':'move','distance_ft':5}]}
        with patch('game.ollama.chat', side_effect=AssertionError('no model')):
            result = ae.execute(session, command, action_id='synthetic-comparison')
            with patch.object(ae, 'resolved_narration', return_value='control presentation'):
                baseline = ae.execute(control, command, action_id='synthetic-comparison')
        self.assertNotEqual(result.pop('narration'), baseline.pop('narration'))
        self.assertEqual(result, baseline)
        self.assertEqual(session.serialize_game_state(), control.serialize_game_state())
        self.assertEqual(session.rng.getstate(), control.rng.getstate())
        self.assertEqual(result['model_calls'], 0)

    def test_executed_attacks_narrate_their_actual_outcomes(self):
        for roll, expected in [(1, 'ıskalar'), (20, 'kritik bir darbe')]:
            session, npc = ready()
            with patch('game.roll_d20', return_value=roll), patch('game.roll_damage', return_value=3), \
                 patch('game.ollama.chat', side_effect=AssertionError('no model')):
                result=ae.execute(session, {'steps':[{'kind':'attack','target_id':npc['id']}]})
            resolved=result['action_result']['economy_steps'][0]['result']
            self.assertEqual(result['narration'],session._combat_narration(resolved))
            self.assertIn(expected,result['narration'])
            self.assertEqual(result['model_calls'],0)

    def test_spell_amounts_and_names_survive_without_internal_ids(self):
        for result, expected in [
            ({'spell_id':'Cure Wounds','healing':0}, 'Cure Wounds ile 0 canın yenilenir.'),
            ({'spell_id':'Cure Wounds','healing':7}, 'Cure Wounds ile 7 canın yenilenir.'),
            ({'spell_id':'Sacred Flame','hit':False}, 'Sacred Flame hedefe hasar vermez.'),
            ({'spell_id':'Magic Missile','hit':True,'target_id':'secret-id','damage':9},
             'Magic Missile hedefe 9 hasar verir.')]:
            before=copy.deepcopy(result)
            self.assertEqual(spell_scope.narration(result), expected)
            self.assertEqual(result,before)

    def test_opening_omits_unknown_weather_and_unverified_social_knowledge(self):
        session=opening_fixtures.LivingWorldV2FoundationTests().make_session()
        session.world_metadata['weather']='unknown'
        before=copy.deepcopy(session.character)
        text=initialize_campaign_opening(session, 'synthetic-immersion')['text']
        self.assertIn('Kökenin Neverwinter.', text)
        self.assertNotIn('doğrulanmış', text)
        self.assertNotIn('kimin bildiği', text)
        self.assertNotIn('Havanın', text)
        self.assertEqual(session.character,before)


class CourtyardNarrationTests(NativeBase):
    def test_entry_keeps_distance_without_command_and_replays_original_receipt(self):
        import bounded_encounter as owner
        body, result=self.call(owner.ENTER)
        self.assertIn('60 feet', result['narration'])
        public = result['state']
        encounter = public['bounded_encounter']
        self.assertEqual(encounter['scenario_id'], owner.SCENARIO_ID)
        self.assertEqual(encounter['location_id'], public['location'])
        self.assertEqual(encounter['visible_opponent']['distance_ft'], 60)
        npc = next(n for n in public['npcs'] if n['id'] == encounter['visible_opponent']['npc_id'])
        self.assertEqual(npc['combat_status'], 'active')
        self.assertGreater(npc['current_hp'], 0)
        self.assertIn(npc['name'], result['narration'])
        self.assertNotIn('başlat', result['narration'])
        self.assertFalse(self.session.world_state['combat']['active'])
        before=self.canonical()
        replay=self.client.post(f'/api/sessions/{self.sid}/turn',json=body)
        self.assertEqual(replay.status_code,200)
        self.assertEqual(replay.json(),result)
        self.assertEqual(self.canonical(),before)
