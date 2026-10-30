"""Selected Berserker3 Frenzy through canonical earned progression and attacks.

Synthetic surviving NPC/deterministic dice permit unit boundaries, not native proof.
Bare weapon resolves model synthetic extra attacks, never a granted class Extra Attack.
"""
import copy
import unittest
from unittest.mock import patch
import game
import xp
import action_economy as economy
import weapon_attack as attacks
import barbarian_rage as rage
from api.tests.test_roadmap_c10_rage import combat
from api.tests.test_roadmap_c10_berserker_progression import apply
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError


class FrenzyTests(unittest.TestCase):
    def encounter(self, raging=True):
        s, n = combat()
        s._receive_xp_award(xp.apply_xp, s.character, s.world_state, 600, 'quest:frenzy-earned')
        apply(self, s)
        s.ensure_combat_state()  # Refresh derived participant HP after earned advancement.
        if raging: rage.activate(s)
        return s, n

    def strike(self, s, n, *, roll=15, reckless=False, weapon='Greataxe', choice=None):
        choice = dict(choice or {})
        if reckless: choice['reckless_attack'] = True
        with patch('game.roll_attack', return_value=roll), patch.object(s.rng, 'randint', return_value=3):
            return attacks.resolve(s, 'player', n['id'], weapon, choice)

    def frenzy(self, result):
        return [row for row in result['damage_rolls'] if row['source'] == 'frenzy']

    def test_first_hit_extra_two_d6_flat_rage_once_and_second_hit_none(self):
        s, n = self.encounter()
        r = self.strike(s, n, reckless=True)
        self.assertEqual(r['damage'], 10)  # weapon3−STR1+Rage2+Frenzy6
        self.assertEqual(self.frenzy(r), [{'source': 'frenzy', 'die': 6, 'count': 2, 'rolls': [3, 3]}])
        self.assertEqual(self.strike(s, n)['damage'], 4)
        self.assertTrue(attacks.sequence_snapshot(s, 'player')['frenzy_used'])

    def test_critical_doubles_frenzy_dice_not_flat_bonus(self):
        s, n = self.encounter()
        r = self.strike(s, n, reckless=True, roll=20)
        self.assertEqual(r['damage'], 19)  # weapon6−1+2+Frenzy12
        self.assertEqual(self.frenzy(r)[0]['count'], 4)

    def test_first_miss_does_not_consume_later_hit(self):
        s, n = self.encounter()
        self.assertEqual(self.strike(s, n, reckless=True, roll=1)['damage'], 0)
        self.assertNotIn('frenzy_used', attacks.sequence_snapshot(s, 'player'))
        self.assertEqual(self.strike(s, n)['damage'], 10)

    def test_dex_declaration_qualifies_but_only_later_strength_hit_consumes(self):
        s, n = self.encounter()
        s.world_state['inventory'].append('Dagger')
        s.world_state['equipment'] = {'main_hand': 'dagger', 'off_hand': None}
        r = self.strike(s, n, reckless=True, weapon='Dagger', choice={'ability': 'dexterity'})
        self.assertEqual(r['damage'], 6)
        self.assertNotIn('frenzy_used', attacks.sequence_snapshot(s, 'player'))
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        r = self.strike(s, n, weapon='unarmed')
        self.assertEqual(r['damage'], 8)
        self.assertEqual(r['damage_type'], 'bludgeoning')

    def test_reckless_before_rage_never_retroactively_qualifies(self):
        s, n = self.encounter(raging=False)
        self.strike(s, n, reckless=True, roll=1)
        rage.activate(s)
        self.assertEqual(self.strike(s, n)['damage'], 4)
        self.assertNotIn('frenzy_eligible', attacks.sequence_snapshot(s, 'player'))

    def test_no_reckless_no_frenzy(self):
        s, n = self.encounter()
        self.assertEqual(self.strike(s, n)['damage'], 4)
        self.assertNotIn('frenzy_eligible', attacks.sequence_snapshot(s, 'player'))

    def test_immunity_still_consumes_and_resistance_groups_same_type(self):
        for field, damage in (('immunities', 0), ('resistances', 5)):
            with self.subTest(field=field):
                s, n = self.encounter(); n[field] = ['slashing']
                r = self.strike(s, n, reckless=True)
                self.assertEqual(r['raw_damage'], 10)
                self.assertEqual(r['damage'], damage)
                self.assertTrue(attacks.sequence_snapshot(s, 'player')['frenzy_used'])
                self.assertEqual(self.frenzy(self.strike(s, n)), [])

    def test_offturn_hit_does_not_consume_and_next_actual_turn_resets(self):
        s, n = self.encounter(); self.strike(s, n, reckless=True, roll=1)
        s.advance_combat_turn()
        # Existing reaction capability context, synthetic unit-only opportunity.
        with economy.executing(s, 'reaction', 'player'):
            with patch('game.roll_attack', return_value=15), patch.object(s.rng, 'randint', return_value=3):
                r = attacks.resolve(s, 'player', n['id'], 'Greataxe', origin='reaction')
        self.assertEqual(r['damage'], 4)
        self.assertNotIn('frenzy_used', attacks.sequence_snapshot(s, 'player'))
        s.advance_combat_turn()
        self.assertNotIn('frenzy_eligible', attacks.sequence_snapshot(s, 'player'))
        self.assertEqual(self.strike(s, n, reckless=True)['damage'], 10)

    def test_save_restore_before_and_after_consumption_preserves_flags(self):
        s, n = self.encounter(); self.strike(s, n, reckless=True, roll=1)
        self.assertTrue(attacks.sequence_snapshot(s, 'player').get('frenzy_eligible'))
        for used in (False, True):
            if used:
                with patch('game.roll_attack', return_value=15), patch.object(s.rng, 'randint', return_value=3):
                    economy.execute(s, {'steps': [{'kind': 'attack', 'target_id': n['id'], 'weapon_id': 'Greataxe'}]})
            payload = serialize_campaign_payload(s)
            restored = game.create_session(seed=13); restore_campaign_session(restored, payload)
            self.assertEqual(serialize_campaign_payload(restored), payload)
            self.assertEqual(restored.rng.getstate(), s.rng.getstate())
            self.assertEqual(attacks.sequence_snapshot(restored, 'player').get('frenzy_used', False), used)

    def test_late_failure_restores_eligibility_consumption_hp_and_rng(self):
        s, n = self.encounter(); before = s._capture_runtime_snapshot()
        with patch.object(s, 'apply_npc_damage', side_effect=RuntimeError('synthetic late fault')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic late fault'):
                self.strike(s, n, reckless=True)
        self.assertEqual(s._capture_runtime_snapshot(), before)
        self.assertEqual(self.strike(s, n, reckless=True)['damage'], 10)

    def test_lethal_hit_actual_action_cleanup_keeps_completed_damage_trace(self):
        s, n = self.encounter(); n['current_hp'] = 1
        with patch('game.roll_attack', return_value=15), patch.object(s.rng, 'randint', return_value=3):
            result = economy.execute(s, {'steps': [{'kind': 'attack', 'target_id': n['id'], 'weapon_id': 'Greataxe', 'reckless_attack': True}]})
        self.assertFalse(s.world_state['combat']['active'])
        trace = s.world_state['attack_results'][-1]
        self.assertEqual(trace['damage'], 10)
        self.assertEqual(self.frenzy(trace)[0]['count'], 2)

    def test_malformed_sequence_flags_refused_on_fresh_restore(self):
        s, n = self.encounter(); self.strike(s, n, reckless=True, roll=1)
        original = serialize_campaign_payload(s)
        cases = ({'frenzy_eligible': False}, {'frenzy_eligible': 1}, {'frenzy_eligible': None},
                 {'frenzy_used': True}, {'frenzy_eligible': True, 'frenzy_used': False},
                 {'frenzy_eligible': True, 'attack_rolls': 0})
        for changes in cases:
            with self.subTest(changes=changes):
                payload = copy.deepcopy(original)
                sequence = payload['engine_save']['world_state']['combat']['turn_resources']['player']['weapon_sequence']
                sequence.pop('frenzy_eligible', None); sequence.pop('frenzy_used', None)
                sequence.update(changes)
                t = game.create_session(seed=9); before = t._capture_runtime_snapshot()
                with self.assertRaises(CampaignCorruptError): restore_campaign_session(t, payload)
                self.assertEqual(t._capture_runtime_snapshot(), before)

    def test_graze_miss_does_not_consume_and_later_hit_does(self):
        s, n = self.encounter()
        # Existing engine-only mastery fixture, not a class mastery grant claim.
        s.world_state['inventory'].append('Greatsword')
        s.world_state['equipment'] = {'main_hand': 'greatsword', 'off_hand': None}
        s.character['weapon_masteries'] = ['greatsword']
        r = self.strike(s, n, reckless=True, roll=1, weapon='Greatsword')
        self.assertFalse(r['hit'])
        self.assertEqual(self.frenzy(r), [])
        self.assertNotIn('frenzy_used', attacks.sequence_snapshot(s, 'player'))
        self.assertEqual(self.strike(s, n, weapon='Greatsword')['damage'], 13)

    def test_strength_thrown_matches_weapon_damage_type(self):
        s, n = self.encounter()
        s.world_state['inventory'].append('Javelin')
        s.world_state['equipment'] = {'main_hand': 'javelin', 'off_hand': None}
        r = self.strike(s, n, reckless=True, weapon='Javelin', choice={'mode': 'thrown'})
        self.assertEqual(r['damage'], 10)
        self.assertEqual(r['damage_type'], 'piercing')
        self.assertEqual(len(r['damage_instances']), 1)

    def test_nondamaging_shove_does_not_consume_after_eligible_miss(self):
        s, n = self.encounter(); self.strike(s, n, reckless=True, roll=1)
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        r = self.strike(s, n, weapon='unarmed', choice={'unarmed_option': 'shove'})
        self.assertEqual(r['damage'], 0)
        self.assertNotIn('frenzy_used', attacks.sequence_snapshot(s, 'player'))
        self.assertEqual(self.strike(s, n, weapon='unarmed')['damage'], 8)

    def test_rage_ending_suppresses_frenzy_without_consuming(self):
        s, n = self.encounter(); self.strike(s, n, reckless=True, roll=1)
        rage.end(s)
        self.assertEqual(self.strike(s, n)['damage'], 2)
        self.assertNotIn('frenzy_used', attacks.sequence_snapshot(s, 'player'))
        # Historical declaration is valid after Rage ends, no active-Rage save requirement.
        payload = serialize_campaign_payload(s)
        restore_campaign_session(game.create_session(seed=8), payload)

    def test_flags_require_selected_owner_and_reckless_provenance(self):
        s, n = self.encounter(); self.strike(s, n, reckless=True, roll=1)
        original = serialize_campaign_payload(s)
        payload = copy.deepcopy(original)
        payload['engine_save']['world_state']['attack_effects'] = []
        with self.assertRaises(CampaignCorruptError):
            restore_campaign_session(game.create_session(seed=8), payload)
        s, n = combat(); rage.activate(s); self.strike(s, n, reckless=True, roll=1)
        self.assertNotIn('frenzy_eligible', attacks.sequence_snapshot(s, 'player'))
        payload = serialize_campaign_payload(s)
        payload['engine_save']['world_state']['combat']['turn_resources']['player']['weapon_sequence']['frenzy_eligible'] = True
        with self.assertRaises(CampaignCorruptError):
            restore_campaign_session(game.create_session(seed=8), payload)

    def test_first_ally_target_hit_consumes_frenzy_but_does_not_extend_rage(self):
        s, n = self.encounter()
        s.advance_combat_turn(); s.advance_combat_turn()
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'], 6)
        # Existing target owner permits participant attacks; no new targeting authority.
        n['combat_side'] = 'party'
        self.assertEqual(self.strike(s, n, reckless=True)['damage'], 10)
        self.assertTrue(attacks.sequence_snapshot(s, 'player')['frenzy_used'])
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'], 6)
        n['combat_side'] = 'enemy'
        self.assertEqual(self.strike(s, n)['damage'], 4)
        self.assertEqual(s.world_state['rage_v1']['active']['remaining_seconds'], 12)

    def test_saved_flags_require_retained_adopted_rage_pool_and_proof(self):
        s, n = self.encounter(); self.strike(s, n, reckless=True, roll=1)
        original = serialize_campaign_payload(s)
        for absent in (('rage_v1',), ('worn_armor_v1',), ('rage_v1', 'worn_armor_v1')):
            with self.subTest(absent=absent):
                payload = copy.deepcopy(original)
                for field in absent: payload['engine_save']['world_state'].pop(field)
                with self.assertRaises(CampaignCorruptError):
                    restore_campaign_session(game.create_session(seed=19), payload)
