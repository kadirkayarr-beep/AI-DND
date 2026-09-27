"""Authoritative V2 exchange contract. No Ollama service or random rolls required."""
import copy
import contextlib
import io
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


SOURCE = pathlib.Path(__file__).with_name('game.py')
fake_ollama = types.ModuleType('ollama')
def no_model(**kwargs):
    raise AssertionError('Unexpected model call in deterministic suite')
fake_ollama.chat = no_model
G = {'__name__': 'game_under_test', '__file__': str(SOURCE)}
with patch.dict(sys.modules, {'ollama': fake_ollama}), \
        patch('builtins.input', return_value='2'), \
        contextlib.redirect_stdout(io.StringIO()):
    exec(compile(SOURCE.read_text(encoding='utf-8-sig'), str(SOURCE), 'exec'), G)
INITIAL_WORLD = copy.deepcopy(G['world_state'])
ORIGINAL_PARSE = G['parse_player_intent']
ORIGINAL_DM = G['ask_dungeon_master']


class CombatV2(unittest.TestCase):
    def setUp(self):
        G['world_state'].clear()
        G['world_state'].update(copy.deepcopy(INITIAL_WORLD))
        G.update(current_hp=30, max_hp=30, armor_class=12,
                 strength_mod=2, dexterity_mod=2, proficiency_bonus=2)
        G['recent_dm_narrations'].clear()
        G['parse_player_intent'] = ORIGINAL_PARSE
        G['ask_dungeon_master'] = ORIGINAL_DM
        self.w = G['world_state']
        self.w.update(location='tavern', npcs=[], player_combat_status='active')
        self.npc = {'id': 'npc_test', 'name': 'Sentinel', 'role': 'guard',
                    'location': 'tavern', 'max_hp': 100, 'current_hp': 100,
                    'armor_class': 10, 'combat_status': 'active',
                    'attack_bonus': 2, 'damage_die': 6, 'damage_dice': 2,
                    'damage_modifier': 3, 'memory': []}
        self.w['npcs'].append(self.npc)

    @contextlib.contextmanager
    def rolls(self, d20, damage=()):
        attack_values, damage_values = iter(d20), iter(damage)
        def damage_roll(low, high):
            value = next(damage_values)
            self.assertLessEqual(low, value)
            self.assertLessEqual(value, high)
            return value
        original_roll = G['roll_d20']
        G['roll_d20'] = lambda: next(attack_values)
        try:
            with patch.object(G['random'], 'randint', side_effect=damage_roll):
                yield
                sentinel = object()
                self.assertIs(next(attack_values, sentinel), sentinel, 'Unused d20 values')
                self.assertIs(next(damage_values, sentinel), sentinel, 'Unused damage values')
        finally:
            G['roll_d20'] = original_roll

    def attack(self, target=None):
        return G['execute_intent']({'intent': 'attack'},
                                   "Sentinel'a kılıcımla saldırıyorum", target or self.npc)

    def start(self, player=15, npc=5):
        with self.rolls([player, npc]):
            return G['start_combat'](self.npc)

    def assert_snapshot(self, result):
        expected = copy.deepcopy(self.w['combat'])
        expected.update(player_current_hp=G['current_hp'], player_max_hp=G['max_hp'],
                        player_combat_status=self.w['player_combat_status'])
        self.assertEqual(result['combat'], expected)

    def test_A_combat_starts(self):
        with self.rolls([15, 5, 1, 1]):
            result = self.attack()
        self.assertTrue(result['combat_started'])
        self.assertTrue(self.w['combat']['active'])
        self.assertEqual(result['outcome'], 'miss')
        self.assertEqual(result['enemy_action']['outcome'], 'miss')
        self.assertEqual(self.w['combat']['target_id'], self.npc['id'])

    def test_B_player_initiative_higher_and_tie(self):
        self.start(15, 5)
        self.assertEqual(self.w['combat']['round'], 1)
        self.assertEqual(self.w['combat']['initiative_order'], ['player', self.npc['id']])
        G['end_combat']()
        self.start(10, 12)
        self.assertEqual(self.w['combat']['initiative_order'][0], 'player')

    def test_C_npc_initiative_higher_still_one_exchange(self):
        with self.rolls([2, 18, 1, 1]):
            result = self.attack()
        self.assertEqual(self.w['combat']['initiative_order'], [self.npc['id'], 'player'])
        self.assertEqual(result['enemy_action']['outcome'], 'miss')
        self.assertEqual(self.w['combat']['round'], 2)
        self.assertEqual(self.w['combat']['current_turn_index'], 1)

    def test_D_enemy_normal_hit(self):
        with self.rolls([15], [4, 5]):
            result = G['resolve_enemy_attack'](self.npc)
        self.assertEqual(result['damage'], 12)
        self.assertEqual((result['target_hp_before'], result['target_hp_after']), (30, 18))
        self.assertEqual(G['current_hp'], 18)
        self.npc['damage_modifier'] = -20
        with self.rolls([15], [1, 1]):
            result = G['resolve_enemy_attack'](self.npc)
        self.assertEqual(result['damage'], 1)

    def test_E_enemy_miss(self):
        with self.rolls([2]):
            result = G['resolve_enemy_attack'](self.npc)
        self.assertEqual((result['outcome'], result['damage']), ('miss', 0))
        self.assertEqual(G['current_hp'], 30)

    def test_F_enemy_nat1(self):
        self.npc['attack_bonus'] = 100
        with self.rolls([1]):
            result = G['resolve_enemy_attack'](self.npc)
        self.assertEqual((result['outcome'], result['damage'], result['critical']), ('miss', 0, False))

    def test_G_enemy_nat20(self):
        G['armor_class'] = 100
        with self.rolls([20], [2, 3, 4, 5]):
            result = G['resolve_enemy_attack'](self.npc)
        self.assertEqual((result['outcome'], result['critical'], result['damage']), ('critical_hit', True, 17))
        self.assertEqual((result['target_hp_before'], result['target_hp_after']), (30, 13))

    def test_H_player_knocks_out_npc(self):
        self.npc['current_hp'] = 1
        with self.rolls([15, 5, 15], [4]):
            result = self.attack()
        self.assertEqual(self.npc['combat_status'], 'unconscious')
        self.assertNotIn('enemy_action', result)
        self.assertEqual(result['end_reason'], 'target_defeated')
        self.assertFalse(result['combat']['active'])
        self.assertEqual(result['combat']['round'], 0)
        self.assert_snapshot(result)

    def test_I_enemy_knocks_out_player(self):
        G['current_hp'] = 2
        with self.rolls([15, 5, 1, 15], [4, 5]):
            result = self.attack()
        self.assertEqual(G['current_hp'], 0)
        self.assertEqual(self.w['player_combat_status'], 'unconscious')
        self.assertEqual(result['enemy_action']['target_hp_before'], 2)
        self.assertEqual(result['end_reason'], 'player_defeated')
        self.assert_snapshot(result)
        G['end_combat']()
        G['end_combat']()
        self.assertEqual(self.w['player_combat_status'], 'unconscious')

    def test_J_round_once_per_exchange(self):
        with self.rolls([15, 5, 1, 1]):
            self.attack()
        self.assertEqual(self.w['combat']['round'], 2)
        with self.rolls([1, 1]):
            self.attack()
        self.assertEqual(self.w['combat']['round'], 3)
        self.assertEqual(self.w['combat']['current_turn_index'], 0)

    def test_K_missing_state(self):
        del self.w['combat']
        del self.w['player_combat_status']
        G['ensure_combat_state']()
        self.assertEqual(self.w['combat'], INITIAL_WORLD['combat'])
        self.assertEqual(self.w['player_combat_status'], 'active')

    def test_L_empty_partial_invalid_state(self):
        for malformed in ({}, None, {'active': False, 'current_turn_index': -100}):
            self.w['combat'] = malformed
            self.w['player_combat_status'] = 'unconscious'
            G['ensure_combat_state']()
            self.assertEqual(self.w['combat'], INITIAL_WORLD['combat'])
            self.assertEqual(self.w['player_combat_status'], 'unconscious')
        self.start()
        for index in (-1, 100, None, 'bad'):
            self.w['combat']['current_turn_index'] = index
            G['advance_combat_turn']()
            self.assertIn(self.w['combat']['current_turn_index'], (0, 1))

    def test_M_active_empty_order(self):
        self.w['combat'] = {'active': True, 'initiative_order': [], 'current_turn_index': 99}
        G['advance_combat_turn']()
        self.assertFalse(self.w['combat']['active'])
        self.assertEqual(G['advance_combat_turn'](), (False, None, False))

    def test_N_wrong_location(self):
        self.npc['location'] = 'forest'
        with self.rolls([]):
            result = self.attack()
        self.assertEqual(result['outcome'], 'no_target')
        self.assertEqual(self.npc['current_hp'], 100)

    def test_O_forged_stats(self):
        forged = dict(self.npc, armor_class=0, current_hp=1)
        self.npc['armor_class'] = 100
        with self.rolls([15, 5, 15, 1]):
            result = self.attack(forged)
        self.assertEqual(result['outcome'], 'miss')
        self.assertEqual(result['target_ac'], 100)
        self.assertEqual(forged['current_hp'], 1)
        self.assertEqual(self.npc['current_hp'], 100)

    def test_P_no_target_switch(self):
        self.start()
        other = dict(self.npc, id='npc_other', name='Other')
        self.w['npcs'].append(other)
        before = copy.deepcopy(self.w)
        player_before = {key: G[key] for key in ('current_hp', 'max_hp', 'armor_class',
                                                'strength_mod', 'dexterity_mod')}
        self.assertNotIn('tavern', self.w['ground_items_by_location'])
        with self.rolls([]):
            result = self.attack(other)
        self.assertFalse(result['success'])
        self.assertEqual(result['outcome'], 'target_mismatch')
        self.assertEqual(self.w, before)
        self.assertNotIn('tavern', self.w['ground_items_by_location'])
        self.assertEqual({key: G[key] for key in player_before}, player_before)

    def test_Q_location_change(self):
        self.start()
        G['commit_location_change']('tavern')
        self.assertTrue(self.w['combat']['active'])
        result = G['execute_intent']({'intent': 'travel', 'target': {'reference': 'forest'},
                                      'completion': 'completed'}, 'ormana gidiyorum')
        self.assertEqual(self.w['location'], 'forest')
        self.assertFalse(self.w['combat']['active'])
        self.assertEqual(result['end_reason'], 'location_changed')

    def test_R_incapacitated(self):
        for hp, status in [(0, 'active'), (10, 'unconscious')]:
            G['current_hp'] = hp
            self.w['player_combat_status'] = status
            with self.rolls([]):
                result = self.attack()
            self.assertEqual(result['outcome'], 'player_unconscious')
            self.assertEqual(G['current_hp'], hp)
            self.assertEqual(self.npc['current_hp'], 100)

    def test_S_qwen_npc_mechanics(self):
        before = copy.deepcopy(self.npc)
        fields = ['max_hp', 'current_hp', 'armor_class', 'combat_status',
                  'attack_bonus', 'damage_die', 'damage_dice', 'damage_modifier']
        updates = {'update_npcs': [dict(id=self.npc['id'], **dict.fromkeys(fields, 999))]}
        G['merge_world_updates'](G['validate_world_updates'](updates))
        self.assertEqual(self.npc, before)

    def test_T_qwen_global_mechanics(self):
        before = copy.deepcopy(self.w)
        player = [G[k] for k in ('current_hp', 'max_hp', 'armor_class')]
        fields = ['combat', 'round', 'initiative_order', 'current_turn_index', 'participants',
                  'target_id', 'player_combat_status', 'current_hp', 'max_hp', 'armor_class']
        G['merge_world_updates'](G['validate_world_updates'](dict.fromkeys(fields, 999)))
        self.assertEqual(self.w, before)
        self.assertEqual([G[k] for k in ('current_hp', 'max_hp', 'armor_class')], player)

    def test_U_final_snapshot(self):
        with self.rolls([2, 18, 1, 15], [2, 3]):
            result = self.attack()
        self.assert_snapshot(result)
        self.assertIn('player.current_hp', result['state_changes'])
        frozen = copy.deepcopy(result['combat'])
        self.w['combat']['initiative_order'].reverse()
        self.assertEqual(result['combat'], frozen)

    def test_V_no_combat_dialogue_memory(self):
        G['parse_player_intent'] = lambda _: {'intent': 'attack'}
        G['ask_dungeon_master'] = lambda *a, **kw: {'narration': 'Darbe hedefe isabet eder.', 'world_updates': {}}
        with self.rolls([15, 5, 1, 1]):
            result = G['run_player_turn']("Sentinel'a kılıcımla saldırıyorum", [])
        self.assertEqual(self.npc['memory'], [])
        self.assertIn('ıskalar', result['narration'])

    def test_W_combat_narration_and_duplicate_guard(self):
        import ast
        tree = ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
        self.assertEqual(sum(isinstance(n, ast.FunctionDef) and n.name == 'end_combat'
                             for n in ast.walk(tree)), 1)
        self.npc['current_hp'] = 1
        with self.rolls([15, 5, 20], [3, 4]):
            result = self.attack()
        narration = G['finalize_narration']('Hedef dimdik ayakta kalır.', 'saldırıyorum', self.npc, result)
        self.assertIn('kritik', narration)
        self.assertIn('bilincini kaybeder', narration)
        self.assertEqual(self.npc['memory'], [])
        result = {'action': 'attack', 'outcome': 'hit', 'target_name': 'Sentinel', 'damage': 4,
                  'target_status': 'active', 'enemy_action': {'outcome': 'critical_hit', 'damage': 9},
                  'combat': {'player_combat_status': 'unconscious'}}
        narration = G['finalize_narration']('Rakibin ıskalar; sapasağlamsın.', 'saldırıyorum', self.npc, result)
        self.assertIn('9 hasar', narration)
        self.assertIn('Bilincini kaybedersin', narration)

    def test_X_inventory_parser_no_op(self):
        # No transfer means no normalization or creation, even for legacy data.
        for legacy, mapping in [([], {}), (['Kalkan'], {}), ([], None)]:
            with self.subTest(legacy=legacy, mapping=mapping):
                self.w['ground_items'] = list(legacy)
                if mapping is None:
                    self.w.pop('ground_items_by_location', None)
                else:
                    self.w['ground_items_by_location'] = copy.deepcopy(mapping)
                before = copy.deepcopy(self.w)
                self.assertIsNone(G['update_inventory_from_player']("Gromm'a kılıcımla saldırıyorum"))
                self.assertEqual(self.w, before)
        self.w['ground_items'] = []
        self.w['ground_items_by_location'] = {}
        G['update_inventory_from_player']('kılıcı yerden al')
        self.assertNotIn('tavern', self.w['ground_items_by_location'])
        G['update_inventory_from_player']('kılıcı bırak')
        self.assertEqual(self.w['ground_items_by_location']['tavern'], ['Kılıç'])
        self.assertNotIn('Kılıç', self.w['inventory'])
        G['update_inventory_from_player']('kılıcı yerden al')
        self.assertEqual(self.w['ground_items_by_location']['tavern'], [])
        self.assertEqual(self.w['inventory'].count('Kılıç'), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2, failfast=True)
