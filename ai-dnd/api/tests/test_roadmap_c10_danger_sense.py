"""Barbarian PDF51/printed52 Danger Sense, bounded to weapon_attack.save.

Source barbarian.md SHA256 7c9beb785364945923f78a9b0fd9830786c3b33d4838ea545847b3ad1d9c41f2:
DEX-save Advantage unless Incapacitated (no 2014 sight/hearing restriction).
Mutations caught: raw-XP eligibility, wrong class/ability, extra dice, lost
cancellation, implied-condition RNG, restore losing eligibility, late rollback.
"""
import copy
import random
import unittest
from unittest.mock import patch

import game
import action_economy as ae
import weapon_attack as attack
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.tests.test_roadmap_c06_barbarian import barbarian, advance
from api.tests.test_combat_lifecycle import ready


class DangerSenseTests(unittest.TestCase):
    def session(self):
        session = barbarian()
        advance(self, session)
        return session

    def controlled_save(self, session, ability='dexterity', values=(1, 20), target='player'):
        # Replace only RNG draws, not the saving throw, game binding or resolver.
        with patch.object(session.rng, 'randint', side_effect=values) as dice:
            result = attack.save(session, target, [ability], 12)
        self.assertTrue(all(call.args == (1, 20) for call in dice.call_args_list))
        return result, dice.call_count

    def encounter(self):
        session = self.session()
        session.world_state['location'] = 'tavern'
        session, enemy = ready(session)
        enemy.update(strength_mod=3, proficiency_bonus=2,
                     equipment={'main_hand': None, 'off_hand': None})
        combat = session.world_state['combat']
        combat['current_actor_id'] = enemy['id']
        combat['current_turn_index'] = combat['initiative_order'].index(enemy['id'])
        ae.begin_turn(session, enemy['id'])
        return session, enemy

    def grapple(self, session, enemy, chosen='dexterity'):
        choice = {'unarmed_option': 'grapple'}
        if chosen is not None:
            choice['target_save_ability'] = chosen
        return attack.resolve(session, enemy['id'], 'player', 'unarmed', choice)

    def test_applied_two_real_npc_grapple_fails_against_dex_advantage(self):
        session, enemy = self.encounter()
        with patch.object(session.rng, 'randint', side_effect=[1, 20]) as dice:
            result = self.grapple(session, enemy)
        self.assertEqual(result['resolution']['raw_rolls'], [1, 20])
        self.assertEqual(result['resolution']['ability'], 'dexterity')
        self.assertEqual(result['resolution']['dc'], 13)
        self.assertEqual(result['resolution']['total'], 23)
        self.assertFalse(result['hit'])
        self.assertEqual(result['damage'], 0)
        self.assertNotIn('grappled', session.character.get('conditions', []))
        self.assertEqual(enemy['equipment'], {'main_hand': None, 'off_hand': None})
        self.assertEqual(dice.call_count, 2)

    def test_only_applied_barbarian_two_dex_gets_advantage(self):
        cases = [({}, 'dexterity', 2, 'SUCCESS'),
                 ({'level': 3}, 'dexterity', 2, 'SUCCESS'),
                 ({'progression_level': 1}, 'dexterity', 1, 'FAILURE'),
                 ({'progression_level': 3}, 'dexterity', 1, 'FAILURE'),
                 ({'progression_level': True}, 'dexterity', 1, 'FAILURE'),
                 ({'progression_level': '2'}, 'dexterity', 1, 'FAILURE'),
                 ({'level': True}, 'dexterity', 1, 'FAILURE'),
                 ({'level': '2'}, 'dexterity', 1, 'FAILURE'),
                 ({'level': 0}, 'dexterity', 1, 'FAILURE'),
                 ({'level': 1}, 'dexterity', 1, 'FAILURE'),
                 ({'class': 'Sorcerer'}, 'dexterity', 1, 'FAILURE'),
                 ({}, 'strength', 1, 'FAILURE'), ({}, 'constitution', 1, 'FAILURE')]
        for changes, ability, count, outcome in cases:
            with self.subTest(changes=changes, ability=ability):
                session = self.session()
                # Isolate the passive eligibility guard: deliberately malformed
                # class/level inputs must not retain newly created Rage proof.
                session.world_state.pop('rage_v1', None)
                session.world_state.pop('worn_armor_v1', None)
                session.character.update(changes)
                result, used = self.controlled_save(session, ability)
                self.assertEqual((used, result['outcome']), (count, outcome))
        session = self.session(); del session.character['progression_level']
        self.assertEqual(self.controlled_save(session)[1], 1)
        self.assertEqual(self.controlled_save(barbarian())[1], 1)

    def test_npc_class_fields_do_not_grant_player_class_feature(self):
        session, enemy = self.encounter()
        enemy.update({'class': 'Barbarian', 'level': 2, 'progression_level': 2,
                      'dexterity_mod': 0, 'dexterity_save_bonus': 0})
        result, used = self.controlled_save(session, target=enemy['id'])
        self.assertEqual((used, result['outcome']), (1, 'FAILURE'))

    def test_conditions_and_boolean_source_cancellation(self):
        cases = [([], False, 2, 'SUCCESS'), (['incapacitated'], False, 1, 'FAILURE'),
                 ({'Incapacitated': True}, False, 1, 'FAILURE'),
                 ({'incapacitated': False}, False, 2, 'SUCCESS'),
                 (['blinded', 'deafened'], False, 2, 'SUCCESS'),
                 (['grappled'], False, 2, 'SUCCESS'),
                 ([], True, 2, 'SUCCESS'),
                 (['restrained'], False, 1, 'FAILURE'),
                 (['restrained'], True, 1, 'FAILURE')]
        for conditions, dodge, count, outcome in cases:
            with self.subTest(conditions=conditions, dodge=dodge):
                session, _ = self.encounter()
                session.character['conditions'] = conditions
                ae.ensure(session)['player']['dodging'] = dodge
                result, used = self.controlled_save(session)
                self.assertEqual((used, result['outcome']), (count, outcome))

    def test_implied_incapacitation_auto_fails_without_rng(self):
        for name in ('unconscious', 'paralyzed', 'stunned', 'petrified'):
            with self.subTest(condition=name):
                session = self.session(); session.character['conditions'] = [name]
                before = session.rng.getstate()
                result, used = self.controlled_save(session, values=())
                self.assertEqual(result['outcome'], 'FAILURE')
                self.assertTrue(result['automatic_failure'])
                self.assertEqual(used, 0)
                self.assertEqual(session.rng.getstate(), before)
        session = self.session(); session.world_state['player_combat_status'] = 'unconscious'
        self.assertTrue(self.controlled_save(session, values=())[0]['automatic_failure'])

    def test_fresh_restore_preserves_eligibility_and_real_rng_continuation(self):
        session = self.session(); session.rng.seed(1)
        payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=999)
        restore_campaign_session(restored, payload)
        result = attack.save(restored, 'player', ['dexterity'], 12)
        self.assertEqual(result['raw_rolls'], [5, 19])
        self.assertEqual(result['outcome'], 'SUCCESS')
        self.assertEqual(restored.roll_d20(), 3)
        self.assertEqual((restored.character['class'], restored.character['progression_level']), ('Barbarian', 2))

    def test_actual_caller_default_choice_and_rng_advancement(self):
        session, enemy = self.encounter()
        session.rng.seed(1)
        result = self.grapple(session, enemy, chosen=None)
        self.assertEqual(result['resolution']['ability'], 'dexterity')
        self.assertEqual(result['resolution']['raw_rolls'], [5, 19])
        self.assertFalse(result['hit'])
        self.assertEqual(session.roll_d20(), 3)

    def test_late_real_grapple_failure_restores_world_character_messages_rng(self):
        session, enemy = self.encounter()
        # Seed2 begins 2,3: even the advantaged DEX save fails DC13, so grapple
        # mutates condition and hands before the existing turn-state write fails.
        session.rng.seed(2)
        before = copy.deepcopy((session.world_state, session.character, session.messages, session.rng.getstate()))
        real = attack.turn_state
        def late_failure(s, actor):
            if 'grappled' in s.character.get('conditions', []):
                self.assertEqual(s.rng.getstate(), expected_rng)
                self.assertEqual(attack.actor_data(s, actor)['equipment']['main_hand'], 'grapple:player')
                raise RuntimeError('late synthetic turn-state failure')
            return real(s, actor)
        expected = random.Random(2); expected.randint(1, 20); expected.randint(1, 20)
        expected_rng = expected.getstate()
        with patch.object(attack, 'turn_state', side_effect=late_failure), self.assertRaisesRegex(RuntimeError, 'late synthetic'):
            self.grapple(session, enemy)
        self.assertEqual((session.world_state, session.character, session.messages, session.rng.getstate()), before)
