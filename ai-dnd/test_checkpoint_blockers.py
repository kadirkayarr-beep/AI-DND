import unittest
from unittest.mock import patch
import game
import living_world

class CheckpointBlockers(unittest.TestCase):
    def fresh(self, role=None):
        s = game.create_session(seed=1729)
        s.world_state['location'] = 'forest'
        n = None
        if role:
            n = s.create_npc_from_ai({'name': 'Liora', 'role': role, 'location': 'forest'})
            n['name_known_to_player'] = False
            n['distance_ft'] = 5
            living_world.ensure_scene_record(s.world_state, 'forest', 0)['materialized'] = True
        return s, n

    def test_merchant_search_preserves_unknown_identity(self):
        for text in ('Bir tüccar arıyorum.', 'tüccar bul'):
            with self.subTest(text=text):
                s, _ = self.fresh()
                with patch('game.ollama.chat', side_effect=AssertionError('No model needed')):
                    r = s.run_player_turn(text)
                n = next(n for n in s.world_state['npcs'] if n['id'] == r['action_result']['target_id'])
                self.assertFalse(n['name_known_to_player'])
                self.assertNotIn(n['name'], r['narration'])
                self.assertIn(living_world.public_npc_name(n), r['narration'])

    def test_rejected_interaction_preserves_unknown_identity_without_retry(self):
        for text in ('Ona sembol hakkında fısıldıyorum.', 'Yolcuya sembol hakkında fısıldıyorum.'):
            with self.subTest(text=text):
                s, n = self.fresh('Yolcu')
                with patch('game.ollama.chat', return_value={'message': {'content': '{}'}}) as model:
                    r = s.run_player_turn(text, target_id=n['id'])
                self.assertEqual(r['action_result']['status'], 'proposal_rejected')
                self.assertEqual(model.call_count, 1)
                self.assertEqual(n['name'], 'Liora')
                self.assertFalse(n['name_known_to_player'])
                self.assertNotIn('Liora', r['narration'])
                self.assertIn(living_world.public_npc_name(n), r['narration'])

    def test_explicit_attack_wins_over_inventory_query(self):
        for text in ('Envanterimi kontrol etmeden barmene saldırıyorum.',
                     'Envanterimde ne var bilmiyorum ama barmene saldırıyorum.'):
            with self.subTest(text=text):
                s, n = self.fresh('Barmen')
                with patch('game.ollama.chat', side_effect=AssertionError('No model needed')), \
                     patch('game.roll_initiative_player', return_value=20), \
                     patch('game.roll_initiative_npc', return_value=1):
                    r = s.run_player_turn(text)
                self.assertEqual(r['action_result']['action'], 'attack')
                self.assertEqual(r['action_result']['target_id'], n['id'])
                self.assertTrue(r['action_result']['combat_started'])

    def test_inventory_questions_keep_inventory_owner(self):
        for text in ('Envanterimde neler var?', 'Envanterimi göster', 'Envanterimi gözden geçir'):
            with self.subTest(text=text):
                s, _ = self.fresh()
                with patch('game.ollama.chat', side_effect=AssertionError('No model needed')):
                    r = s.run_player_turn(text)
                self.assertEqual(r['action_result']['action'], 'inventory')
                self.assertFalse(s.world_state['combat']['active'])
