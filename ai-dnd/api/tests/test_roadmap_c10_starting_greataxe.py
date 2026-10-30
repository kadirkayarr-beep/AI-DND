"""Existing Barbarian package label resolves through the one weapon catalog."""
import copy
import unittest
from unittest.mock import patch

import character_progression as cp
import equipment_economy
import game
import weapon_attack
from weapon_catalog import lookup
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.tests.test_roadmap_c06_barbarian import spec
from api.character_creation import configure_character
from api.tests.test_roadmap_c06 import SPEC
from combat_lifecycle import CombatRequestError


LABEL = 'Büyük Balta (Greataxe)'


class StartingGreataxeTests(unittest.TestCase):
    def create(self, level=2):
        session = game.create_session(seed=52)
        request = spec()
        self.assertEqual(request['equipment_package'], 'A')
        cp.create_at_level(session, request, level, {'2': {}} if level == 2 else None)
        return session

    def target(self, session):
        session.commit_location_change('tavern')
        npc = session.create_npc_from_ai({'name': 'Catalog target', 'role': 'Guard', 'location': 'tavern'})
        npc.update(current_hp=100, max_hp=100, armor_class=1, distance_ft=5)
        return npc

    def assert_plain_attack(self, session):
        npc = self.target(session)
        with patch.object(session.rng, 'randint', return_value=10):
            result = weapon_attack.resolve(session, 'player', npc['id'], 'greataxe')
        self.assertTrue(result['hit'])
        self.assertGreater(result['damage'], 0)
        self.assertEqual(npc['current_hp'], 100 - result['damage'])

    def test_creation_one_and_two_select_package_weapon_and_plain_attack(self):
        for level in (1, 2):
            with self.subTest(level=level):
                session = self.create(level)
                self.assertEqual(session.world_state['equipment'], {'main_hand': 'greataxe', 'off_hand': None})
                before = copy.deepcopy(session.world_state['inventory'])
                self.assert_plain_attack(session)
                self.assertEqual(session.world_state['inventory'], before)

    def test_new_creation_reuses_hands_and_clears_prior_offhand(self):
        session = game.create_session(seed=52)
        hands = session.world_state['equipment']
        hands['off_hand'] = 'dagger'
        configure_character(session, mode='custom', **spec())
        self.assertIs(session.world_state['equipment'], hands)
        self.assertEqual(hands, {'main_hand': 'greataxe', 'off_hand': None})

    def test_cash_only_barbarian_b_clears_hands_and_other_class_keeps_behavior(self):
        for request in (dict(spec(), equipment_package='B'), copy.deepcopy(SPEC)):
            with self.subTest(character_class=request['character_class'], package=request['equipment_package']):
                session = game.create_session(seed=52)
                before = copy.deepcopy(session.world_state['equipment'])
                configure_character(session, mode='custom', **request)
                if request['character_class'] == 'Barbarian':
                    # Source-correct B is cash only: it must not inherit a sword.
                    self.assertEqual(session.world_state['equipment'], {'main_hand': None, 'off_hand': None})
                else:
                    self.assertEqual(session.world_state['equipment'], before)

    def test_failed_level_two_creation_restores_previous_inventory_hands_and_history(self):
        session = game.create_session(seed=52)
        before = session._capture_runtime_snapshot()
        character, world = session.character, session.world_state
        real = cp.apply_level_choices
        def fail_after_apply(*args):
            real(*args)
            self.assertEqual(session.world_state['equipment'], {'main_hand': 'greataxe', 'off_hand': None})
            raise RuntimeError('synthetic post-apply failure')
        with patch.object(cp, 'apply_level_choices', side_effect=fail_after_apply):
            with self.assertRaisesRegex(RuntimeError, 'synthetic post-apply failure'):
                cp.create_at_level(session, spec(), 2, {'2': {}})
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertIs(session.character, character)
        self.assertIs(session.world_state, world)

    def test_actual_package_materializes_canonical_greataxe_without_item_churn(self):
        session = self.create()
        before = copy.deepcopy(session.world_state['inventory'])
        history = copy.deepcopy(session.world_state.get('xp_awarded_event_ids', []))
        equipment_economy.materialize(session.world_state)
        items = session.world_state['inventory']
        axe = next(item for item in items if item['name'] == LABEL)
        self.assertEqual(axe, {'item_id': 'item_000001', 'name': LABEL, 'weapon_id': 'greataxe'})
        self.assertEqual(session.world_state['equipment'], {'main_hand': axe['item_id'], 'off_hand': None})
        self.assertEqual(len(items), len(before))
        self.assertEqual(session.world_state.get('xp_awarded_event_ids', []), history)
        stable = copy.deepcopy(items)
        equipment_economy.materialize(session.world_state)
        self.assertEqual(session.world_state['inventory'], stable)
        self.assertIs(lookup(LABEL), lookup('greataxe'))

    def test_fresh_restore_keeps_package_identity_and_can_attack_with_owned_axe(self):
        session = self.create()
        equipment_economy.materialize(session.world_state)
        original = copy.deepcopy(session.world_state['inventory'])
        restored = game.create_session(seed=91)
        restore_campaign_session(restored, serialize_campaign_payload(session))
        self.assertEqual(restored.world_state['inventory'], original)
        axe = next(item for item in original if item['name'] == LABEL)
        self.assertEqual(axe.get('weapon_id'), 'greataxe')
        self.assertEqual(restored.world_state['equipment'], {'main_hand': axe['item_id'], 'off_hand': None})
        self.assert_plain_attack(restored)
        self.assertEqual(restored.world_state['inventory'], original)
        self.assertEqual(restored.world_state['equipment']['main_hand'], axe['item_id'])

    def test_runtime_occupied_offhand_still_rejects_two_handed_attack(self):
        session = self.create()
        session.world_state['inventory'].append('Dagger')
        equipment_economy.materialize(session.world_state)
        dagger = next(i for i in session.world_state['inventory'] if i.get('weapon_id') == 'dagger')
        session.world_state['equipment']['off_hand'] = dagger['item_id']
        npc = self.target(session)
        before = session._capture_runtime_snapshot()
        with self.assertRaisesRegex(CombatRequestError, 'Two-handed attack needs both hands'):
            weapon_attack.resolve(session, 'player', npc['id'], 'greataxe')
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_restore_historical_hand_selection_is_not_new_creation(self):
        session = self.create()
        session.world_state['equipment'] = {'main_hand': None, 'off_hand': None}
        payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=91)
        restore_campaign_session(restored, payload)
        self.assertEqual(restored.world_state['equipment'], {'main_hand': None, 'off_hand': None})

    def test_unrelated_decorated_label_is_not_inferred_as_weapon(self):
        session = self.create()
        label = 'Unknown ceremonial object (Greataxe)'
        self.assertIsNone(lookup(label))
        session.world_state['inventory'].append(label)
        equipment_economy.materialize(session.world_state)
        item = next(item for item in session.world_state['inventory'] if item['name'] == label)
        self.assertNotIn('weapon_id', item)
