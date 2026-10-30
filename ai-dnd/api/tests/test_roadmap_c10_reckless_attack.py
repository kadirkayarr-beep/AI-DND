"""PHB2024 PDF51 Reckless Attack: existing owner, explicit first-roll choice."""
import copy
import unittest
from unittest.mock import patch
from pydantic import ValidationError
import action_economy as ae
import weapon_attack as attack
from api.schemas import EconomyStepInput
from api.tests.test_weapon_attack import armed, resolve
from combat_lifecycle import CombatRequestError


class RecklessAttackTests(unittest.TestCase):
    def encounter(self, weapon='Longsword', distance=5):
        s, n = armed(weapon, distance=distance)
        s.character.update({'class': 'Barbarian', 'level': 2, 'progression_level': 2})
        return s, n

    def test_typed_choice_preserves_legacy_omission_and_rejects_coercion(self):
        old = {'kind': 'attack', 'resource': 'action', 'target_id': 'enemy'}
        self.assertEqual(EconomyStepInput(**old).model_dump(exclude_none=True), old)
        self.assertEqual(EconomyStepInput(**old, reckless_attack=True).reckless_attack, True)
        self.assertIs(EconomyStepInput(**old, reckless_attack=False).model_dump(exclude_none=True)['reckless_attack'], False)
        for value in ('true', 1, 0, [], {}):
            with self.assertRaises(ValidationError): EconomyStepInput(**old, reckless_attack=value)
        with self.assertRaises(ValidationError): EconomyStepInput(kind='move', distance_ft=5, reckless_attack=False)

    def test_first_strength_roll_activates_and_count_tracks_roll_not_dice(self):
        s, n = self.encounter()
        result = resolve(s, n, choice={'reckless_attack': True}, rolls=(1, 18))
        self.assertEqual(result['attack_rolls'], [1, 18])
        self.assertIn('reckless_attack', result['advantage_sources'])
        self.assertEqual(attack.sequence_snapshot(s, 'player')['attack_rolls'], 1)
        self.assertTrue(ae.projection(s)['actors']['player']['reckless_attack']['active'])
        self.assertFalse(ae.projection(s)['actors']['player']['reckless_attack']['available'])

    def test_dex_first_can_choose_but_only_strength_benefits(self):
        s, n = self.encounter('Dagger')
        r = resolve(s, n, 'Dagger', {'ability': 'dexterity', 'reckless_attack': True})
        self.assertNotIn('reckless_attack', r['advantage_sources'])
        r = resolve(s, n, 'Dagger', {'ability': 'strength'}, rolls=(1, 18))
        self.assertIn('reckless_attack', r['advantage_sources'])

    def test_decline_or_miss_closes_choice(self):
        for choice in ({}, {'reckless_attack': False}):
            s, n = self.encounter()
            resolve(s, n, choice=choice, rolls=(1,))
            before = s._capture_runtime_snapshot()
            with self.assertRaises(CombatRequestError): resolve(s, n, choice={'reckless_attack': True})
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_grapple_save_does_not_close_first_roll(self):
        s, n = self.encounter()
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        resolve(s, n, 'unarmed', {'unarmed_option': 'shove'})
        self.assertEqual(attack.sequence_snapshot(s, 'player')['attack_rolls'], 0)
        self.assertTrue(ae.projection(s)['actors']['player']['reckless_attack']['available'])
        r = resolve(s, n, 'unarmed', {'reckless_attack': True}, rolls=(1, 18))
        self.assertIn('reckless_attack', r['advantage_sources'])

    def test_ineligible_and_legacy_midturn_cannot_activate(self):
        for changes in ({'level': 1}, {'progression_level': 1}, {'level': True}, {'progression_level': True}, {'progression_level': 3}, {'class': 'Wizard'}):
            s, n = self.encounter(); s.character.update(changes)
            with self.assertRaises(CombatRequestError): resolve(s, n, choice={'reckless_attack': True})
        s, n = self.encounter()
        seq = attack.turn_state(s, 'player'); seq.pop('attack_rolls', None)
        self.assertEqual(ae.projection(s)['actors']['player']['reckless_attack']['reason'], 'legacy_attack_roll_count_unknown')
        with self.assertRaises(CombatRequestError): resolve(s, n, choice={'reckless_attack': True})
        ae.begin_turn(s, 'player')
        self.assertTrue(ae.projection(s)['actors']['player']['reckless_attack']['available'])

    def test_duration_incoming_cancellation_and_next_turn_expiry(self):
        s, n = self.encounter()
        resolve(s, n, choice={'reckless_attack': True}, rolls=(1, 18))
        attack.boundary(s, 'player', 'end')
        c = s.world_state['combat']; c['current_actor_id'] = n['id']
        c['current_turn_index'] = c['initiative_order'].index(n['id'])
        ae.begin_turn(s, n['id']); n['conditions'] = ['poisoned']
        with patch.object(s.rng, 'randint', return_value=1):
            result = attack.resolve(s, n['id'], 'player', 'unarmed')
        self.assertIn('reckless_attack', result['advantage_sources'])
        self.assertEqual(result['attack_rolls'], [1])
        for condition in ('incapacitated', 'unconscious', 'stunned'):
            s.character['conditions'] = [condition]
            self.assertTrue(ae.projection(s)['actors']['player']['reckless_attack']['active'])
        ae.begin_turn(s, 'player')
        self.assertFalse(ae.projection(s)['actors']['player']['reckless_attack']['active'])

    def test_strength_thrown_advantage_and_rng_failure_rollback(self):
        s, n = self.encounter('Javelin', 20)
        r = resolve(s, n, 'Javelin', {'mode': 'thrown', 'reckless_attack': True}, rolls=(1, 18))
        self.assertIn('reckless_attack', r['advantage_sources'])
        s, n = self.encounter(); before = s._capture_runtime_snapshot()
        with patch('game.roll_attack', side_effect=RuntimeError('synthetic')), self.assertRaises(RuntimeError):
            attack.resolve(s, 'player', n['id'], 'Longsword', {'reckless_attack': True})
        self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_saved_count_and_effect_validation_and_restore(self):
        import game
        from api.tests.test_roadmap_c06_barbarian import barbarian, advance
        from api.tests.test_combat_lifecycle import ready
        from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
        s = barbarian(); advance(self, s); s.world_state['location'] = 'tavern'
        s, n = ready(s); n.update(current_hp=100, max_hp=100)
        # ready() appends a legacy weapon placeholder; canonical saves need item IDs.
        s.world_state['inventory'] = [i for i in s.world_state['inventory'] if i != {'name': 'Kılıç'}]
        s.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        resolve(s, n, 'unarmed', {'reckless_attack': True}, rolls=(1, 18))
        saved = s.serialize_game_state()
        game._validate_save_payload(saved)
        restored = game.create_session(seed=99)
        restore_campaign_session(restored, serialize_campaign_payload(s))
        self.assertTrue(attack.reckless_state(restored)['active'])
        self.assertEqual(restored.rng.getstate(), s.rng.getstate())
        self.assertEqual(attack.sequence_snapshot(restored, 'player')['attack_rolls'], 1)
        for key, value in [('source_actor', n['id']), ('target_id', n['id']), ('expires_turn', True), ('expires_boundary', 'end'), ('expires_turn', 999)]:
            malformed = copy.deepcopy(saved); malformed['world_state']['attack_effects'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): game._validate_save_payload(malformed)
        for value in (-1, True, '1'):
            malformed = copy.deepcopy(saved)
            malformed['world_state']['combat']['turn_resources']['player']['weapon_sequence']['attack_rolls'] = value
            with self.subTest(count=value), self.assertRaises(ValueError): game._validate_save_payload(malformed)
        for value in (None, [], 'bad', 1):
            malformed = copy.deepcopy(saved)
            malformed['world_state']['combat']['turn_resources']['player']['weapon_sequence'] = value
            with self.subTest(sequence=value), self.assertRaises(ValueError): game._validate_save_payload(malformed)
        old = copy.deepcopy(saved); old['world_state']['attack_effects'] = []
        del old['world_state']['combat']['turn_resources']['player']['weapon_sequence']['attack_rolls']
        game._validate_save_payload(old)
        payload = serialize_campaign_payload(s); payload['engine_save'] = old
        restore_campaign_session(restored, payload)
        self.assertEqual(attack.reckless_state(restored)['reason'], 'legacy_attack_roll_count_unknown')
        ae.begin_turn(restored, 'player')
        self.assertTrue(attack.reckless_state(restored)['available'])

    def test_typed_owner_steps_and_own_turn_reaction(self):
        from api.tests.test_action_economy import step
        s, n = self.encounter()
        ae.prepare_ready(s, 'player', {'event': 'actor_moves', 'actor_id': 'player'}, {'kind': 'attack', 'target_id': n['id']})
        ae.move(s, 'player', 5)
        self.assertTrue(attack.reckless_state(s)['available'])
        request = EconomyStepInput(kind='react', opportunity_id=ae.ensure(s)['player']['opportunity']['id'], reckless_attack=True)
        with patch('game.roll_attack', side_effect=[1, 18]), patch.object(s.rng, 'randint', return_value=3):
            step(s, request.model_dump(exclude_none=True))
        self.assertTrue(attack.reckless_state(s)['active'])
        self.assertTrue(ae.ensure(s)['player']['reaction_spent'])

    def test_offturn_reaction_cannot_activate_but_active_strength_benefits(self):
        for active in (False, True):
            s, n = self.encounter()
            if active: resolve(s, n, choice={'reckless_attack': True}, rolls=(1, 18))
            ae.prepare_ready(s, 'player', {'event': 'actor_moves', 'actor_id': n['id']}, {'kind': 'attack', 'target_id': n['id']})
            s.advance_combat_turn(); n['speed_ft'] = 30; ae.move(s, n['id'], 5)
            identity = ae.ensure(s)['player']['opportunity']['id']; before = s._capture_runtime_snapshot()
            with self.assertRaises(CombatRequestError):
                ae.react(s, identity, reckless_attack=True)
            self.assertEqual(s._capture_runtime_snapshot(), before)
            with patch('game.roll_attack', side_effect=[1, 18] if active else [1]), patch.object(s.rng, 'randint', return_value=3):
                r = ae.react(s, identity)
            self.assertEqual('reckless_attack' in r['response']['advantage_sources'], active)

    def test_move_reaction_rejects_choice_and_barbarian_firebolt_cannot_bypass(self):
        import spell_scope
        s, n = self.encounter()
        ae.prepare_ready(s, 'player', {'event': 'actor_moves', 'actor_id': 'player'}, {'kind': 'move', 'distance_ft': 5})
        ae.move(s, 'player', 5); before = s._capture_runtime_snapshot()
        with self.assertRaises(CombatRequestError): ae.react(s, ae.ensure(s)['player']['opportunity']['id'], reckless_attack=False)
        self.assertEqual(s._capture_runtime_snapshot(), before)
        for state in (None, {'version': 1, 'class': 'Barbarian', 'cantrips': ['Fire Bolt'], 'prepared': [], 'slots': {}, 'slot_turn': None}):
            s, n = self.encounter()
            s.world_state['spellcasting_v1'] = state; before = s._capture_runtime_snapshot()
            with self.assertRaises((ValueError, CombatRequestError)): spell_scope.cast(s, 'Fire Bolt', n['id'])
            self.assertEqual(s._capture_runtime_snapshot(), before)
            self.assertTrue(attack.reckless_state(s)['available'])

    def test_invalid_and_late_hook_failure_rollback(self):
        for mode in ('range', 'special', 'hook', 'incapacitated'):
            s, n = self.encounter()
            weapon = 'unarmed' if mode == 'special' else 'Longsword'
            choice = {'reckless_attack': True}
            if mode == 'range': n['distance_ft'] = 100
            if mode == 'special': choice['unarmed_option'] = 'shove'
            if mode == 'incapacitated': s.character['conditions'] = ['incapacitated']
            if mode == 'hook': s.register_attack_hook('after_mastery', lambda *_: (_ for _ in ()).throw(RuntimeError('late synthetic')))
            before = s._capture_runtime_snapshot()
            with self.assertRaises((CombatRequestError, RuntimeError)):
                resolve(s, n, weapon, choice, rolls=(1, 18))
            self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_actual_scheduler_expires_even_when_player_cannot_act(self):
        for status in ('incapacitated', 'unconscious', 'stable'):
            s, n = self.encounter()
            resolve(s, n, choice={'reckless_attack': True}, rolls=(1, 18))
            s.advance_combat_turn()
            self.assertTrue(attack.reckless_state(s)['active'])
            if status == 'incapacitated': s.character['conditions'] = ['incapacitated']
            else:
                s.character['current_hp'] = 0
                s.world_state['player_combat_status'] = 'unconscious'
                s.world_state['death_state']['stable'] = status == 'stable'
            s.advance_combat_turn()
            self.assertEqual(s.world_state['combat']['current_actor_id'], 'player')
            self.assertFalse(attack.reckless_state(s)['active'])
            self.assertNotIn('weapon_sequence', ae.ensure(s)['player'])

    def test_outgoing_cancellation_and_preview_do_not_spend(self):
        s, n = self.encounter(); s.character['conditions'] = ['poisoned']
        before = s._capture_runtime_snapshot()
        preview = attack.preview(s, 'player', n['id'], 'Longsword', {'reckless_attack': True})
        self.assertIn('reckless_attack', preview['advantage_sources'])
        self.assertEqual(s._capture_runtime_snapshot(), before)
        r = resolve(s, n, choice={'reckless_attack': True}, rolls=(1,))
        self.assertEqual(r['attack_rolls'], [1])
        self.assertEqual(attack.sequence_snapshot(s, 'player')['attack_rolls'], 1)

    def test_malformed_runtime_effect_and_count_cannot_grant_reckless(self):
        s, n = self.encounter()
        seq = attack.turn_state(s, 'player'); seq['attack_rolls'] = False
        with self.subTest(count='bool'):
            self.assertFalse(attack.reckless_state(s)['available'])
        for changes in ({'expires_turn': True}, {'expires_turn': 999}, {'source_actor': n['id']}, {'target_id': n['id']}):
            s, n = self.encounter()
            resolve(s, n, choice={'reckless_attack': True}, rolls=(1, 18))
            s.world_state['attack_effects'][0].update(changes)
            with self.subTest(changes=changes):
                self.assertFalse(attack.reckless_state(s)['active'])

    def test_rolled_automatic_miss_closes_choice_and_combat_close_clears_effect(self):
        s, n = self.encounter()
        s.world_state['attack_environment'] = {'pairs': {f"player|{n['id']}": {'distance_ft': 5, 'guessed_location_correct': False}}}
        r = resolve(s, n, choice={'reckless_attack': True}, rolls=(18, 20))
        self.assertFalse(r['hit'])
        self.assertEqual(attack.sequence_snapshot(s, 'player')['attack_rolls'], 1)
        self.assertTrue(attack.reckless_state(s)['active'])
        s.apply_npc_damage(n, n['current_hp'])
        s._combat_end_if_decided()
        self.assertFalse(s.world_state['combat']['active'])
        self.assertFalse(attack.reckless_state(s)['active'])
        self.assertEqual(s.world_state['attack_effects'], [])
