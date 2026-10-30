"""Selected Rage consumers: real canonical creation/activation, deterministic dice only.

No fabricated Rage state or armor proof. STR-save disadvantage has no current
producer; supported DEX cancellation is covered without inventing one.
"""
import copy
import unittest
from unittest.mock import patch

import action_economy as economy
import weapon_attack as attacks
import spell_scope
from combat_lifecycle import CombatRequestError


class RageCombatTests(unittest.TestCase):
    def encounter(self, *, strong=False):
        from api.tests.test_roadmap_c10_rage import combat
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec("barbarian_rage"), "Rage activation owner missing")
        import barbarian_rage
        scores = {"strength": 15, "dexterity": 14, "constitution": 13, "intelligence": 10, "wisdom": 12, "charisma": 8} if strong else None
        session, enemy = combat(ability_scores=scores)
        barbarian_rage.activate(session)
        return session, enemy

    def strike(self, session, enemy, weapon='Greataxe', choice=None, roll=15):
        with patch('game.roll_attack', return_value=roll), patch.object(session.rng, 'randint', return_value=3):
            return attacks.resolve(session, 'player', enemy['id'], weapon, choice)

    def test_strength_greataxe_flat_bonus_once_on_hit_and_critical(self):
        for roll, expected in ((15, 4), (20, 7)):
            with self.subTest(roll=roll):
                s, n = self.encounter()
                n['armor_class'] = 10
                result = self.strike(s, n, roll=roll)
                self.assertEqual(result['damage'], expected)  # d12=3, STR−1, Rage+2
                self.assertEqual(result['critical'], roll == 20)

    def test_unarmed_strength_damage_and_nondamaging_shove(self):
        s, n = self.encounter(); n['armor_class'] = 10
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        result = self.strike(s, n, 'unarmed')
        self.assertEqual(result['damage'], 2)  # 1−1+2
        s, n = self.encounter()
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        result = self.strike(s, n, 'unarmed', {'unarmed_option': 'shove'})
        self.assertEqual(result['damage'], 0)

    def test_dexterity_weapon_never_gets_rage_damage(self):
        s, n = self.encounter(); n['armor_class'] = 10
        s.world_state['inventory'].append('Dagger')
        s.world_state['equipment'] = {'main_hand': 'dagger', 'off_hand': None}
        result = self.strike(s, n, 'Dagger', {'ability': 'dexterity'})
        self.assertEqual(result['damage'], 6)  # d4=3, canonical DEX+3

    def test_bps_resistance_rounds_down_and_does_not_rewrite_resistances(self):
        s, n = self.encounter()
        s.character['resistances'] = ['fire', 'slashing']
        before = copy.deepcopy(s.character['resistances'])
        for kind, expected in (('bludgeoning', 2), ('piercing', 2), ('slashing', 2), ('fire', 2), ('cold', 5)):
            self.assertEqual(attacks.mitigate(s, 'player', kind, 5)['final_damage'], expected)
        self.assertEqual(s.character['resistances'], before)
        self.assertEqual(attacks.mitigate(s, n['id'], 'slashing', 5)['final_damage'], 5)

    def test_resistance_existing_immunity_and_vulnerability_order(self):
        s, _ = self.encounter()
        s.character['vulnerabilities'] = ['slashing']
        self.assertEqual(attacks.mitigate(s, 'player', 'slashing', 5)['final_damage'], 4)
        s.character['immunities'] = ['slashing']
        self.assertEqual(attacks.mitigate(s, 'player', 'slashing', 5)['final_damage'], 0)

    def test_strength_save_advantage_other_abilities_unchanged(self):
        for ability, expected in (('strength', [1, 20]), ('constitution', [1])):
            s, _ = self.encounter()
            with patch.object(s.rng, 'randint', side_effect=[1, 20]):
                result = attacks.save(s, 'player', [ability], 12)
            self.assertEqual(result['raw_rolls'], expected)
        s, _ = self.encounter(); s.character['conditions'] = ['restrained']
        with patch.object(s.rng, 'randint', side_effect=[1, 20]):
            result = attacks.save(s, 'player', ['dexterity'], 12)
        self.assertEqual(result['raw_rolls'], [1])  # Danger Sense + restrained cancel

    def test_incapacitated_save_ends_rage_permanently(self):
        s, _ = self.encounter()
        s.character['conditions'] = ['stunned']
        before_rng = s.rng.getstate()
        result = attacks.save(s, 'player', ['strength'], 12)
        self.assertTrue(result['automatic_failure'])
        self.assertEqual(s.rng.getstate(), before_rng)
        s.character['conditions'] = []
        self.assertEqual(attacks.mitigate(s, 'player', 'slashing', 5)['final_damage'], 5)
        self.assertIsNone(s.world_state['rage_v1']['active'])

    def test_all_supported_spell_requests_block_before_cost_or_rng(self):
        # A canonical Barbarian does not currently have a lawful spellcasting
        # grant. Test the Rage prohibition at request admission, not fake spells.
        for spell in spell_scope.CATALOG:
            s, n = self.encounter(); before = s._capture_runtime_snapshot()
            with self.assertRaises(CombatRequestError) as error:
                spell_scope.cast(s, spell, n['id'])
            self.assertEqual(error.exception.code, 'rage_spellcasting_forbidden')
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_preview_never_extends_or_mutates(self):
        s, n = self.encounter(); self.next_player_turn(s)
        before = s._capture_runtime_snapshot()
        attacks.preview(s, 'player', n['id'], 'Greataxe')
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_late_attack_failure_restores_rage_state_damage_budget_and_rng(self):
        s, n = self.encounter(); n['armor_class'] = 10
        before = s._capture_runtime_snapshot()
        with patch.object(s, 'apply_npc_damage', side_effect=RuntimeError('synthetic late fault')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic late fault'):
                self.strike(s, n)
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def next_player_turn(self, session):
        session.advance_combat_turn()
        session.advance_combat_turn()
        self.assertEqual(session.world_state['combat']['current_actor_id'], 'player')
        self.assertEqual(session.world_state['rage_v1']['active']['remaining_seconds'], 6)

    def test_enemy_miss_and_forced_save_extend_next_turn(self):
        for weapon, choice in (('Greataxe', None), ('unarmed', {'unarmed_option': 'shove'})):
            s, n = self.encounter(); self.next_player_turn(s)
            result = self.strike(s, n, weapon, choice, roll=1)
            self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'], 12)
            if weapon == 'Greataxe':
                self.assertFalse(result['hit'])

    def test_qualifying_lethal_roll_extends_before_combat_cleanup(self):
        s, n = self.encounter(); self.next_player_turn(s)
        n['current_hp'] = 1  # synthetic lethal-boundary fixture, not native proof
        with patch('game.roll_attack', return_value=15), patch.object(s.rng, 'randint', return_value=3):
            economy.execute(s, {'steps': [{'kind': 'attack', 'target_id': n['id'], 'weapon_id': 'Greataxe'}]})
        self.assertFalse(s.world_state['combat']['active'])
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'], 12)

    def test_ally_or_companion_rolls_do_not_extend(self):
        for companion in (False, True):
            s, n = self.encounter(); self.next_player_turn(s)
            if companion:
                s.world_state['companions'] = [{'npc_id': n['id']}]
            else:
                n['combat_side'] = 'party'
            self.strike(s, n, roll=1)
            self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'], 6)

    def test_real_incoming_weapon_uses_resistance_before_hp(self):
        s, n = self.encounter()
        n.update(strength_mod=4, proficiency_bonus=2, equipment={'main_hand': None, 'off_hand': None})
        s.advance_combat_turn()
        hp = s.character['current_hp']
        with patch.object(s.rng, 'randint', return_value=15):
            result = attacks.resolve(s, n['id'], 'player', 'unarmed')
        self.assertEqual(result['raw_damage'], 5)
        self.assertEqual(result['damage'], 2)
        self.assertEqual(s.character['current_hp'], hp - 2)
        self.assertTrue(result['damage_instances'][0]['resistance_applied'])

    def test_rage_and_reckless_preserve_attack_advantage_and_flat_damage(self):
        s, n = self.encounter(strong=True)
        with patch('game.roll_attack', side_effect=[1, 15]), patch.object(s.rng, 'randint', return_value=3):
            result = attacks.resolve(s, 'player', n['id'], 'Greataxe', {'reckless_attack': True})
        self.assertEqual(result['attack_rolls'], [1, 15])
        self.assertIn('reckless_attack', result['advantage_sources'])
        self.assertEqual(result['damage'], 7)  # d12=3, STR+2, Rage+2

    def test_late_fault_rolls_back_extension_before_lethal_damage(self):
        s, n = self.encounter(); self.next_player_turn(s)
        n['current_hp'] = 1
        before = s._capture_runtime_snapshot()
        with patch.object(s, 'apply_npc_damage', side_effect=RuntimeError('synthetic late fault')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic late fault'):
                self.strike(s, n)
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_positive_base_unarmed_adds_bonus_once(self):
        s, n = self.encounter(strong=True)
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        self.assertEqual(self.strike(s, n, 'unarmed')['damage'], 5)
