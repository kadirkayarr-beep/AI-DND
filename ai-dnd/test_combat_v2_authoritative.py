"""Authoritative Combat V3 scheduler contract; no Ollama service is required."""
import copy
import contextlib
import io
import json
import game
from combat_lifecycle import CombatRequestError
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = __import__('pathlib').Path(game.__file__)
INITIAL_WORLD = copy.deepcopy(game.create_session().world_state)


class CombatV2(unittest.TestCase):
    def setUp(self):
        self.session = game.create_session()
        self.session.character.update(current_hp=30, max_hp=30, armor_class=12,
                                      strength=14, dexterity=14,
                                      strength_mod=2, dexterity_mod=2, proficiency_bonus=2,
                                      weapon_proficiencies=['longsword'],
                                      weapon_masteries=[], conditions=[])
        self.w = self.session.world_state
        self.w.update(location='tavern', npcs=[], player_combat_status='active')
        self.w['inventory'] = ['Macera çantası', 'Kılıç']
        self.w['equipment'] = {'main_hand': 'longsword', 'off_hand': None}
        self.npc = {'id': 'npc_test', 'name': 'Sentinel', 'role': 'guard',
                    'location': 'tavern', 'max_hp': 100, 'current_hp': 100,
                    'armor_class': 10, 'combat_status': 'active',
                    'attack_bonus': 2, 'damage_die': 6, 'damage_dice': 2,
                    'damage_modifier': 3, 'memory': [],
                    # Authored fixture distance, never an engine fallback.
                    'distance_ft': 5, 'attack_damage_type': 'slashing'}
        self.w['npcs'].append(self.npc)
        # Distance alone does not prove the enemy can perceive its target.
        self.w['monster_perception'] = {
            self.npc['id']: {'player': {'visible': True}},
        }

    @contextlib.contextmanager
    def rolls(self, *expected, session=None):
        """Strict, ordered (die size, value) pairs on the owning session."""
        session = self.session if session is None else session
        remaining = iter(expected)

        def randint(low, high):
            roll = next(remaining, None)
            self.assertIsNotNone(roll, f"Unexpected d{high} roll")
            sides, value = roll
            self.assertEqual((low, high), (1, sides), "Wrong scripted die")
            self.assertTrue(low <= value <= high, "Scripted value outside die range")
            return value

        with patch.object(session.rng, 'randint', side_effect=randint) as dice:
            yield dice
            self.assertIsNone(next(remaining, None), "Unused scripted dice")

    def attack(self, target=None):
        return self.session.execute_intent({'intent': 'attack'},
                                           "Sentinel'a kılıcımla saldırıyorum", target or self.npc)

    def start(self, player=15, npc=5):
        with self.rolls((20, player), (20, npc)):
            return self.session.start_combat(self.npc)

    def assert_snapshot(self, result):
        expected = copy.deepcopy(self.w['combat'])
        expected.update(player_current_hp=self.session.character['current_hp'],
                        player_max_hp=self.session.character['max_hp'],
                        player_combat_status=self.w['player_combat_status'])
        self.assertEqual(result['combat'], expected)

    def test_A_combat_starts(self):
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 1)):
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
        self.session.end_combat()
        self.start(10, 12)
        self.assertEqual(self.w['combat']['initiative_order'][0], 'player')

    def test_C_npc_initiative_higher_owns_the_first_turn(self):
        self.start(2, 18)
        self.assertEqual(self.w['combat']['initiative_order'], [self.npc['id'], 'player'])
        before = self.session.serialize_game_state()
        rng_before = self.session.rng.getstate()
        with self.rolls():
            result = self.attack()
        self.assertEqual(result['outcome'], 'out_of_turn')
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertEqual(self.session.rng.getstate(), rng_before)

        with self.rolls((20, 1)):
            enemy_actions = game._resolve_enemy_turns_until_player(session=self.session)
        self.assertEqual(enemy_actions[0]['outcome'], 'miss')
        self.assertEqual(self.w['combat']['current_actor_id'], 'player')
        with self.rolls((20, 1), (20, 1)):
            result = self.attack()
        self.assertEqual(result['outcome'], 'miss')
        self.assertEqual(result['enemy_actions'][0]['outcome'], 'miss')
        self.assertEqual(self.w['combat']['round'], 2)
        self.assertEqual(self.w['combat']['current_actor_id'], 'player')

    def test_D_enemy_normal_hit(self):
        with self.rolls((20, 15), (6, 4), (6, 5)):
            result = self.session.resolve_enemy_attack(self.npc)
        self.assertEqual(result['damage'], 12)
        self.assertEqual((result['target_hp_before'], result['target_hp_after']), (30, 18))
        self.assertEqual(self.session.character['current_hp'], 18)
        self.npc['damage_modifier'] = -20
        with self.rolls((20, 15), (6, 1), (6, 1)):
            result = self.session.resolve_enemy_attack(self.npc)
        # Negative modifiers cannot heal the target; PHB damage floors at zero.
        self.assertEqual(result['damage'], 0)
        self.assertEqual((result['target_hp_before'], result['target_hp_after']), (18, 18))
        self.assertEqual(self.session.character['current_hp'], 18)

    def test_E_enemy_miss(self):
        with self.rolls((20, 2)):
            result = self.session.resolve_enemy_attack(self.npc)
        self.assertEqual((result['outcome'], result['damage']), ('miss', 0))
        self.assertEqual(self.session.character['current_hp'], 30)

    def test_F_enemy_nat1(self):
        self.npc['attack_bonus'] = 100
        with self.rolls((20, 1)):
            result = self.session.resolve_enemy_attack(self.npc)
        self.assertEqual((result['outcome'], result['damage'], result['critical']), ('miss', 0, False))

    def test_G_enemy_nat20(self):
        self.session.character['armor_class'] = 100
        with self.rolls((20, 20), (6, 2), (6, 3), (6, 4), (6, 5)):
            result = self.session.resolve_enemy_attack(self.npc)
        self.assertEqual((result['outcome'], result['critical'], result['damage']), ('critical_hit', True, 17))
        self.assertEqual((result['target_hp_before'], result['target_hp_after']), (30, 13))

    def test_H_player_lethal_damage_kills_npc(self):
        self.npc['current_hp'] = 1
        with self.rolls((20, 15), (20, 5), (20, 15), (8, 4)):
            result = self.attack()
        self.assertEqual(self.npc['combat_status'], 'dead')
        self.assertEqual(self.npc['current_hp'], 0)
        self.assertEqual(result['target_status'], 'dead')
        self.assertNotIn('enemy_action', result)
        self.assertEqual(result['end_reason'], 'target_defeated')
        self.assertFalse(result['combat']['active'])
        self.assertEqual(result['combat']['round'], 0)
        self.assert_snapshot(result)

    def test_I_enemy_knocks_out_player(self):
        self.session.character['current_hp'] = 2
        with self.rolls(
            (20, 15), (20, 5), (20, 1), (20, 15), (6, 4), (6, 5),
            (20, 10), (20, 1), (20, 1),
            (20, 10), (20, 1), (20, 1),
            # Stabilization schedules recovery with an owned 1d4-hour roll.
            (20, 10), (4, 2), (20, 1), (20, 1),
        ):
            result = self.attack()
        self.assertEqual(self.session.character['current_hp'], 0)
        self.assertEqual(self.w['player_combat_status'], 'unconscious')
        self.assertEqual(result['enemy_action']['target_hp_before'], 2)
        self.assertTrue(self.w['death_state']['stable'])
        self.assertEqual(self.w['death_state']['recovery']['hours'], 2)
        self.assertTrue(result['combat']['active'])
        death_saves = [
            action for action in result['enemy_actions']
            if action.get('action') == 'death_save'
        ]
        self.assertEqual(len(death_saves), 3)
        self.assertEqual(
            [action['outcome'] for action in death_saves],
            ['success', 'success', 'stable'],
        )
        self.assert_snapshot(result)
        self.session.end_combat()
        self.session.end_combat()
        self.assertEqual(self.w['player_combat_status'], 'unconscious')

    def test_J_round_once_per_exchange(self):
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 1)):
            self.attack()
        self.assertEqual(self.w['combat']['round'], 2)
        with self.rolls((20, 1), (20, 1)):
            self.attack()
        self.assertEqual(self.w['combat']['round'], 3)
        self.assertEqual(self.w['combat']['current_turn_index'], 0)

    def test_K_missing_state(self):
        del self.w['combat']
        del self.w['player_combat_status']
        self.session.ensure_combat_state()
        self.assertEqual(self.w['combat'], INITIAL_WORLD['combat'])
        self.assertEqual(self.w['player_combat_status'], 'active')

    def test_L_empty_partial_invalid_state(self):
        for malformed in ({}, None, {'active': False, 'current_turn_index': -100}):
            self.w['combat'] = malformed
            self.w['player_combat_status'] = 'unconscious'
            self.session.ensure_combat_state()
            self.assertEqual(self.w['combat'], INITIAL_WORLD['combat'])
            self.assertEqual(self.w['player_combat_status'], 'unconscious')
        self.w['player_combat_status'] = 'active'
        self.start()
        for index in (-1, 100, None, 'bad'):
            self.w['combat']['current_turn_index'] = index
            with self.assertRaises(ValueError):
                self.session.advance_combat_turn()
            self.w['combat']['current_turn_index'] = 0

    def test_M_active_empty_order(self):
        self.w['combat'] = {'active': True, 'initiative_order': [], 'current_turn_index': 99}
        with self.assertRaises(ValueError):
            self.session.advance_combat_turn()
        self.assertTrue(self.w['combat']['active'])

    def test_N_wrong_location(self):
        self.npc['location'] = 'forest'
        with self.rolls():
            result = self.attack()
        self.assertEqual(result['outcome'], 'no_target')
        self.assertEqual(self.npc['current_hp'], 100)

    def test_O_forged_stats(self):
        forged = dict(self.npc, armor_class=0, current_hp=1)
        self.npc['armor_class'] = 100
        with self.rolls((20, 15), (20, 5), (20, 15), (20, 1)):
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
        player_before = {key: self.session.character[key] for key in ('current_hp', 'max_hp', 'armor_class',
                                                'strength_mod', 'dexterity_mod')}
        self.assertNotIn('tavern', self.w['ground_items_by_location'])
        with self.rolls():
            result = self.attack(other)
        self.assertFalse(result['success'])
        self.assertEqual(result['outcome'], 'target_mismatch')
        self.assertEqual(self.w, before)
        self.assertNotIn('tavern', self.w['ground_items_by_location'])
        self.assertEqual({key: self.session.character[key] for key in player_before}, player_before)

    def test_Q_location_change(self):
        self.start()
        self.session.commit_location_change('tavern')
        self.assertTrue(self.w['combat']['active'])
        before = copy.deepcopy((self.w, self.session.character, self.session.rng.getstate()))
        with self.rolls(), self.assertRaises(CombatRequestError) as rejected:
            self.session.execute_intent({'intent': 'travel', 'target': {'reference': 'forest'},
                                         'completion': 'completed'}, 'ormana gidiyorum')
        self.assertEqual(rejected.exception.code, 'combat_travel')
        self.assertEqual(rejected.exception.status_code, 400)
        self.assertEqual(self.w['location'], 'tavern')
        self.assertTrue(self.w['combat']['active'])
        self.assertEqual((self.w, self.session.character, self.session.rng.getstate()), before)

    def test_R_incapacitated(self):
        for hp, status in [(0, 'active'), (10, 'unconscious')]:
            self.session.character['current_hp'] = hp
            self.w['player_combat_status'] = status
            with self.rolls():
                result = self.attack()
            self.assertEqual(result['outcome'], 'player_unconscious')
            self.assertEqual(self.session.character['current_hp'], hp)
            self.assertEqual(self.npc['current_hp'], 100)

    def test_S_qwen_npc_mechanics(self):
        before = copy.deepcopy(self.npc)
        fields = ['max_hp', 'current_hp', 'armor_class', 'combat_status',
            'attack_bonus', 'damage_die', 'damage_dice', 'damage_modifier',
            'distance_ft', 'attack_damage_type']
        updates = {'update_npcs': [dict(id=self.npc['id'], **dict.fromkeys(fields, 999))]}
        self.session.merge_world_updates(self.session.validate_world_updates(updates))
        self.assertEqual(self.npc, before)

    def test_T_qwen_global_mechanics(self):
        before = copy.deepcopy(self.w)
        player = [self.session.character[k] for k in ('current_hp', 'max_hp', 'armor_class')]
        fields = ['combat', 'round', 'initiative_order', 'current_turn_index', 'participants',
                  'schema_version', 'status', 'current_actor_id', 'turn_owner',
                  'participant_records', 'actions_used', 'end_reason', 'target_id',
                  'player_combat_status', 'current_hp', 'max_hp', 'armor_class']
        self.session.merge_world_updates(self.session.validate_world_updates(dict.fromkeys(fields, 999)))
        self.assertEqual(self.w, before)
        self.assertEqual([self.session.character[k] for k in ('current_hp', 'max_hp', 'armor_class')], player)

    def test_U_final_snapshot(self):
        with self.rolls((20, 15), (20, 5), (20, 1), (20, 15), (6, 2), (6, 3)):
            result = self.attack()
        self.assert_snapshot(result)
        self.assertIn('player.current_hp', result['state_changes'])
        frozen = copy.deepcopy(result['combat'])
        self.w['combat']['initiative_order'].reverse()
        self.assertEqual(result['combat'], frozen)

    def test_V_no_combat_dialogue_memory(self):
        with patch.object(game, 'parse_player_intent', return_value={'intent': 'attack'}), \
             patch.object(game, 'ask_dungeon_master', return_value={
                 'narration': 'Darbe hedefe isabet eder.', 'world_updates': {}}), \
             self.rolls((20, 15), (20, 5), (20, 1), (20, 1)):
            result = self.session.run_player_turn("Sentinel'a kılıcımla saldırıyorum", [])
        self.assertEqual(self.npc['memory'], [])
        self.assertIn('ıskalar', result['narration'])

    def test_W_single_end_combat_definition(self):
        import ast
        tree = ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
        self.assertEqual(sum(isinstance(n, ast.FunctionDef) and n.name == 'end_combat'
                             for n in ast.walk(tree)), 1)

    def test_W_npc_death_narration(self):
        self.npc['current_hp'] = 1
        with self.rolls((20, 15), (20, 5), (20, 20), (8, 3), (8, 4)):
            result = self.attack()
        narration = game.finalize_narration(
            'Hedef dimdik ayakta kalır.',
            'saldırıyorum',
            self.npc,
            result,
            session=self.session,
        )
        self.assertEqual(result['target_status'], 'dead')
        self.assertEqual(self.npc['combat_status'], 'dead')
        self.assertIn('kritik', narration)
        self.assertEqual(self.npc['memory'], [])
        # Preserve the outcome-narration contract under Policy A, even if
        # production omits the death sentence. Never turn this into an xfail.
        self.assertIn('ölür', narration)

    def test_W_player_unconscious_narration(self):
        result = {'action': 'attack', 'outcome': 'hit', 'target_name': 'Sentinel', 'damage': 4,
                  'target_status': 'active', 'enemy_action': {'outcome': 'critical_hit', 'damage': 9},
                  'combat': {'player_combat_status': 'unconscious'}}
        narration = game.finalize_narration(
            'Rakibin ıskalar; sapasağlamsın.',
            'saldırıyorum',
            self.npc,
            result,
            session=self.session,
        )
        self.assertIn('9 hasar', narration)
        self.assertIn('Bilincini kaybedersin', narration)

    def test_W_npc_lethal_hit_narration(self):
        self.npc['current_hp'] = 1
        with self.rolls((20, 15), (20, 5), (20, 15), (8, 3)):
            result = self.attack()
        narration = game.finalize_narration(
            'Hedef dimdik ayakta kalır.', 'saldırıyorum', self.npc,
            result, session=self.session,
        )
        self.assertEqual(result['outcome'], 'hit')
        self.assertEqual(result['damage'], 5)
        self.assertEqual(result['target_status'], 'dead')
        self.assertEqual(self.npc['combat_status'], 'dead')
        self.assertIn('5 hasar', narration)
        self.assertIn('Sentinel ölür.', narration)
        self.assertNotIn('kritik', narration)
        self.assertNotIn('bilincini kaybeder', narration)

    def test_W_npc_nonlethal_hit_narration(self):
        with self.rolls((20, 15), (20, 5), (20, 15), (8, 3), (20, 1)):
            result = self.attack()
        narration = game.finalize_narration(
            'Hedef ölür.', 'saldırıyorum', self.npc,
            result, session=self.session,
        )
        self.assertEqual(result['target_status'], 'active')
        self.assertEqual(self.npc['combat_status'], 'active')
        self.assertEqual(self.npc['current_hp'], 95)
        self.assertIn('5 hasar', narration)
        self.assertNotIn('ölür', narration)
        self.assertNotIn('bilincini kaybeder', narration)

    def test_W_historical_unconscious_npc_narration(self):
        self.npc.update(current_hp=0, combat_status='unconscious')
        result = {'action': 'attack', 'outcome': 'hit', 'target_name': 'Sentinel',
                  'damage': 4, 'target_status': 'unconscious', 'target_hp': 0}
        world_before = copy.deepcopy(self.w)
        character_before = copy.deepcopy(self.session.character)
        rng_before = self.session.rng.getstate()
        narration = game.finalize_narration(
            'Hedef ölür.', 'saldırıyorum', self.npc,
            result, session=self.session,
        )
        self.assertIn('4 hasar', narration)
        self.assertIn('Sentinel bilincini kaybeder.', narration)
        self.assertNotIn('ölür', narration)
        self.assertEqual(self.w, world_before)
        self.assertEqual(self.session.character, character_before)
        self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_W_critical_damage_narration(self):
        with self.rolls((20, 15), (20, 5), (20, 20), (8, 3), (8, 4), (20, 1)):
            result = self.attack()
        narration = game.finalize_narration(
            'Hedef ölür.', 'saldırıyorum', self.npc,
            result, session=self.session,
        )
        self.assertEqual((result['outcome'], result['critical'], result['damage']),
                         ('critical_hit', True, 9))
        self.assertEqual(self.npc['current_hp'], 91)
        self.assertEqual(result['target_status'], 'active')
        self.assertIn('kritik bir darbe alır: 9 hasar.', narration)
        self.assertNotIn('ölür', narration)

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
                self.assertIsNone(self.session.update_inventory_from_player("Gromm'a kılıcımla saldırıyorum"))
                self.assertEqual(self.w, before)
        self.w['ground_items'] = []
        self.w['ground_items_by_location'] = {}
        self.session.update_inventory_from_player('kılıcı yerden al')
        self.assertNotIn('tavern', self.w['ground_items_by_location'])
        self.session.update_inventory_from_player('kılıcı bırak')
        self.assertEqual(self.w['ground_items_by_location']['tavern'], ['Kılıç'])
        self.assertNotIn('Kılıç', self.w['inventory'])
        self.session.update_inventory_from_player('kılıcı yerden al')
        self.assertEqual(self.w['ground_items_by_location']['tavern'], [])
        self.assertEqual(self.w['inventory'].count('Kılıç'), 1)

    def test_Y_interleaved_adventures_own_all_combat_dice(self):
        other = game.create_session()
        other.character.update(copy.deepcopy(self.session.character))
        other.world_state.update(copy.deepcopy(self.w))
        other_npc = other.world_state['npcs'][0]
        self.assertIsNot(self.session.rng, other.rng)
        default_before = game.serialize_game_state()

        # Keep both scripts installed throughout A/B/A/B exchanges. Different
        # initiative, attack and damage values expose accidental cross-routing.
        with self.rolls(
            (20, 16), (20, 3),
            (20, 14), (8, 4), (20, 12), (6, 2), (6, 3),
            (20, 1), (20, 1),
        ) as dice_a, self.rolls(
            (20, 18), (20, 2),
            (20, 20), (8, 7), (8, 8), (20, 15), (6, 5), (6, 6),
            (20, 1), (20, 1), session=other,
        ) as dice_b:
            before_b = other.serialize_game_state()
            init_a = self.session.start_combat(self.npc)
            self.assertEqual((init_a['player_initiative'], init_a['npc_initiative']),
                             (18, 3))
            self.assertEqual(init_a['initiative_order'], ['player', self.npc['id']])
            self.assertEqual((dice_a.call_count, dice_b.call_count), (2, 0))
            self.assertEqual(other.serialize_game_state(), before_b)

            before_a = self.session.serialize_game_state()
            init_b = other.start_combat(other_npc)
            self.assertEqual((init_b['player_initiative'], init_b['npc_initiative']),
                             (20, 2))
            self.assertEqual(init_b['initiative_order'], ['player', other_npc['id']])
            self.assertEqual((dice_a.call_count, dice_b.call_count), (2, 2))
            self.assertEqual(self.session.serialize_game_state(), before_a)

            for session, npc, idle, own_dice, idle_dice, attack_roll, damage, enemy_roll, enemy_damage, total in (
                (self.session, self.npc, other, dice_a, dice_b, 14, 6, 12, 8, 7),
                (other, other_npc, self.session, dice_b, dice_a, 20, 17, 15, 14, 8),
                (self.session, self.npc, other, dice_a, dice_b, 1, 0, 1, 0, 9),
                (other, other_npc, self.session, dice_b, dice_a, 1, 0, 1, 0, 10),
            ):
                with self.subTest(session='A' if session is self.session else 'B',
                                  attack_roll=attack_roll):
                    idle_before = idle.serialize_game_state()
                    idle_calls = idle_dice.call_count
                    npc_hp, player_hp = npc['current_hp'], session.character['current_hp']
                    round_before = session.world_state['combat']['round']
                    result = session.execute_intent(
                        {'intent': 'attack'}, "Sentinel'a kılıcımla saldırıyorum", npc)
                    self.assertEqual((result['attack_roll'], result['damage']),
                                     (attack_roll, damage))
                    enemy = result['enemy_action']
                    self.assertEqual((enemy['attack_roll'], enemy['damage']),
                                     (enemy_roll, enemy_damage))
                    self.assertEqual(npc['current_hp'], npc_hp - damage)
                    self.assertEqual(session.character['current_hp'], player_hp - enemy_damage)
                    self.assertEqual(result['combat']['round'], round_before + 1)
                    self.assertEqual(own_dice.call_count, total)
                    self.assertEqual(idle_dice.call_count, idle_calls)
                    self.assertEqual(idle.serialize_game_state(), idle_before)
                    self.assertEqual(game.serialize_game_state(), default_before)

        self.assertEqual((self.npc['current_hp'], self.session.character['current_hp']), (94, 22))
        self.assertEqual((other_npc['current_hp'], other.character['current_hp']), (83, 16))

    def test_V3_multiple_enemies_and_stable_initiative_ties(self):
        self.session.character['dexterity_mod'] = 0
        self.npc['hostile'] = True
        archer = {
            'id': 'npc_alpha', 'name': 'Archer', 'role': 'enemy',
            'location': 'tavern', 'max_hp': 50, 'current_hp': 50,
            'armor_class': 10, 'combat_status': 'active', 'hostile': True,
            'attack_bonus': 0, 'damage_die': 6, 'damage_dice': 1,
            'damage_modifier': 0, 'memory': [], 'distance_ft': 5,
            'attack_damage_type': 'piercing',
        }
        self.w['npcs'].append(archer)
        self.w['monster_perception'][archer['id']] = {'player': {'visible': True}}

        with self.rolls(
            (20, 10), (20, 10), (20, 10),
            (20, 15), (8, 3),
            (20, 1), (20, 1),
        ):
            result = self.session.execute_intent(
                {'intent': 'attack'},
                "Sentinel'a kılıcımla saldırıyorum",
                self.npc,
                target_id=archer['id'],
            )

        combat = result['combat']
        self.assertEqual(combat['initiative_order'], ['player', 'npc_alpha', 'npc_test'])
        self.assertEqual([action['actor'] for action in result['enemy_actions']],
                         ['npc_alpha', 'npc_test'])
        self.assertEqual(result['target_id'], archer['id'])
        self.assertEqual(archer['current_hp'], 45)
        self.assertEqual(combat['round'], 2)
        self.assertEqual(combat['current_actor_id'], 'player')
        self.assertEqual(combat['actions_used'], [])
        self.assertTrue(all(record['primary_action_available']
                            for record in combat['participant_records']))

    def test_V3_rejects_forged_and_nonparticipant_targets_without_rolls(self):
        other = dict(self.npc, id='npc_other', name='Other')
        self.w['npcs'].append(other)
        self.start()
        before = self.session.serialize_game_state()
        rng_before = self.session.rng.getstate()

        with self.rolls():
            nonparticipant = self.session.execute_intent(
                {'intent': 'attack'}, "Sentinel'a kılıcımla saldırıyorum",
                self.npc, target_id='npc_other',
            )
        self.assertEqual(nonparticipant['outcome'], 'target_mismatch')
        self.assertEqual(self.session.serialize_game_state(), before)

        with self.rolls():
            forged = self.session.execute_intent(
                {'intent': 'attack'}, "Sentinel'a kılıcımla saldırıyorum",
                self.npc, target_id='npc_forged',
            )
        self.assertIn(forged['outcome'], ('no_target', 'invalid_target'))
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_V3_unsupported_combat_actions_do_not_change_the_turn(self):
        self.start()
        before = self.session.serialize_game_state()
        result = self.session.execute_intent(
            {'intent': 'explore'}, 'Çatışma sırasında etrafı araştırıyorum'
        )
        self.assertEqual(result['outcome'], 'unsupported_combat_action')
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertEqual(self.w['combat']['current_actor_id'], 'player')

    def test_V3_legacy_turn_boundary_migrates_without_losing_cursor(self):
        self.w['combat'] = {
            'active': True,
            'round': 4,
            'initiative_order': [self.npc['id'], 'player'],
            'current_turn_index': 1,
            'participants': [self.npc['id'], 'player'],
            'target_id': self.npc['id'],
        }
        combat = self.session.ensure_combat_state()
        self.assertEqual(combat['schema_version'], 3)
        self.assertEqual(combat['round'], 4)
        self.assertEqual(combat['initiative_order'], [self.npc['id'], 'player'])
        self.assertEqual(combat['current_turn_index'], 1)
        self.assertEqual(combat['current_actor_id'], 'player')
        self.assertTrue(combat['active'])

    def test_V3_legacy_active_state_without_boundary_fails_visibly(self):
        self.w['combat'] = {
            'active': True,
            'round': 4,
            'initiative_order': [self.npc['id'], 'player'],
            'participants': [self.npc['id'], 'player'],
            'target_id': self.npc['id'],
        }
        with self.assertRaisesRegex(ValueError, 'turn boundary'):
            self.session.ensure_combat_state()
        self.assertTrue(self.w['combat']['active'])

    def test_V3_legacy_versions_resume_and_persist_migration_owned_identity(self):
        original = self.session.serialize_game_state()
        for version in (1, 2):
            for schema_version in (None, version):
                for index in (0, 1):
                    with self.subTest(version=version, schema=schema_version, index=index):
                        legacy = copy.deepcopy(original)
                        legacy['version'] = version
                        order = [self.npc['id'], 'player']
                        participants = ['player', self.npc['id']]
                        legacy['world_state']['combat'] = {
                            'active': True,
                            'round': 4,
                            'initiative_order': order,
                            'current_turn_index': index,
                            'participants': participants,
                            'target_id': self.npc['id'],
                        }
                        if schema_version is not None:
                            legacy['world_state']['combat']['schema_version'] = schema_version
                        migrated = game.create_session(seed=73)
                        world_ref = migrated.world_state
                        character_ref = migrated.character
                        rng_before = migrated.rng.getstate()
                        with tempfile.TemporaryDirectory() as directory:
                            path = Path(directory) / 'legacy.json'
                            path.write_text(json.dumps(legacy), encoding='utf-8')
                            migrated.load_game(path)
                            combat = migrated.ensure_combat_state()
                            self.assertIsInstance(combat['combat_id'], str)
                            self.assertTrue(combat['combat_id'])
                            self.assertEqual(combat['schema_version'], 3)
                            self.assertEqual(combat['round'], 4)
                            self.assertEqual(combat['initiative_order'], order)
                            self.assertEqual(combat['participants'], participants)
                            self.assertEqual(combat['target_id'], self.npc['id'])
                            self.assertEqual(combat['current_turn_index'], index)
                            self.assertEqual(combat['current_actor_id'], order[index])
                            self.assertTrue(combat['active'])
                            self.assertIs(migrated.ensure_combat_state(), combat)
                            expected = migrated.serialize_game_state()
                            migrated.save_game(path)
                            reopened = game.create_session(seed=99)
                            reopen_rng = reopened.rng.getstate()
                            reopened.load_game(path)
                            self.assertEqual(reopened.serialize_game_state(), expected)
                            self.assertEqual(reopened.rng.getstate(), reopen_rng)
                            combat_id = combat['combat_id']
                            reopened.advance_combat_turn()
                            next_combat = reopened.ensure_combat_state()
                            self.assertEqual(next_combat['combat_id'], combat_id)
                            self.assertEqual(next_combat['current_turn_index'], 1 - index)
                            self.assertEqual(next_combat['current_actor_id'], order[1 - index])
                            self.assertEqual(next_combat['round'], 4 + index)
                            self.assertEqual(reopened.rng.getstate(), reopen_rng)
                        self.assertIs(migrated.world_state, world_ref)
                        self.assertIs(migrated.character, character_ref)
                        self.assertEqual(migrated.rng.getstate(), rng_before)

    def test_V3_native_active_identity_is_not_repaired_by_migration(self):
        self.start()
        expected = self.session.serialize_game_state()
        for missing in (True, False):
            with self.subTest(missing=missing):
                forged = copy.deepcopy(expected)
                combat = forged['world_state']['combat']
                if missing:
                    del combat['combat_id']
                else:
                    combat['combat_id'] = None
                rng_before = self.session.rng.getstate()
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'missing-identity.json'
                    path.write_text(json.dumps(forged), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'kimliği eksik'):
                        self.session.load_game(path)
                self.assertEqual(self.session.serialize_game_state(), expected)
                self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_V3_invalid_legacy_boundaries_roll_back_load_references_and_rng(self):
        original = self.session.serialize_game_state()
        legacy_combat = {
            'active': True,
            'round': 4,
            'initiative_order': [self.npc['id'], 'player'],
            'current_turn_index': 1,
            'participants': [self.npc['id'], 'player'],
            'target_id': self.npc['id'],
        }
        changes = (
            ('current_turn_index', None),
            ('current_turn_index', -1),
            ('current_turn_index', 2),
            ('current_turn_index', True),
            ('round', 0),
            ('round', True),
            ('initiative_order', ['player', 'player']),
            ('participants', ['player', 'npc_missing']),
            ('target_id', 'npc_missing'),
        )
        character_ref = self.session.character
        world_ref = self.session.world_state
        narration_ref = self.session.recent_dm_narrations
        rng_before = self.session.rng.getstate()
        for version in (1, 2):
            for field, value in changes:
                with self.subTest(version=version, field=field, value=value):
                    legacy = copy.deepcopy(original)
                    legacy['version'] = version
                    legacy['player']['name'] = 'Must Roll Back'
                    legacy['recent_dm_narrations'] = ['Must Roll Back']
                    legacy['world_state']['combat'] = copy.deepcopy(legacy_combat)
                    legacy['world_state']['combat']['schema_version'] = version
                    legacy['world_state']['combat'][field] = value
                    with tempfile.TemporaryDirectory() as directory:
                        path = Path(directory) / 'bad-boundary.json'
                        path.write_text(json.dumps(legacy), encoding='utf-8')
                        with self.assertRaisesRegex(ValueError, 'turn boundary'):
                            self.session.load_game(path)
                    self.assertIs(self.session.character, character_ref)
                    self.assertIs(self.session.world_state, world_ref)
                    self.assertIs(self.session.recent_dm_narrations, narration_ref)
                    self.assertEqual(self.session.serialize_game_state(), original)
                    self.assertEqual(self.session.rng.getstate(), rng_before)

    def test_V3_midround_engine_save_resumes_exact_scheduler_state(self):
        self.start()
        self.session._mark_combat_action_used('player')
        self.session.advance_combat_turn()
        expected = self.session.serialize_game_state()
        self.assertEqual(expected['world_state']['combat']['current_actor_id'], self.npc['id'])
        self.assertEqual(expected['world_state']['combat']['actions_used'], ['player'])
        self.assertFalse(
            expected['world_state']['combat']['participant_records'][0]['primary_action_available']
        )

        resumed = game.create_session(seed=999)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'combat-save.json'
            self.session.save_game(path)
            resumed.load_game(path)
        self.assertEqual(resumed.serialize_game_state(), expected)

    def test_V3_failed_legacy_load_restores_state_and_references(self):
        before = self.session.serialize_game_state()
        character_ref = self.session.character
        world_ref = self.session.world_state
        rng_before = self.session.rng.getstate()
        legacy = copy.deepcopy(before)
        legacy['version'] = 2
        legacy['player']['name'] = 'Forged Name'
        legacy['world_state']['combat'] = {
            'active': True,
            'round': 2,
            'initiative_order': ['player', 'npc_missing'],
            'current_turn_index': 0,
            'participants': ['player', 'npc_missing'],
            'target_id': 'npc_missing',
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad-legacy-save.json'
            path.write_text(json.dumps(legacy), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'target'):
                self.session.load_game(path)

        self.assertIs(self.session.character, character_ref)
        self.assertIs(self.session.world_state, world_ref)
        self.assertEqual(self.session.serialize_game_state(), before)
        self.assertEqual(self.session.rng.getstate(), rng_before)


if __name__ == '__main__':
    # A real contract failure must not conceal later retained assertions.
    unittest.main(verbosity=2)
