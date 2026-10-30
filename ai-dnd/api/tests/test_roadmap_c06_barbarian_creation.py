"""Core-only Barbarian2 creation, PHB PDF40–42/50–51 numeric facts.

Late rollback is explicit synthetic fault injection, not a rule capability.
"""
import copy
import unittest
from unittest.mock import patch

import game
import xp
import hit_dice
import character_progression as cp
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.tests import test_campaign_api as campaigns
from api.tests.test_roadmap_c06_barbarian import barbarian, spec
from api.tests.test_roadmap_c06_starting_xp import create as create_sorcerer


def create_two(session=None):
    session = barbarian() if session is None else session
    try:
        cp.create_at_level(session, spec(), 2, {'2': {}})
    except ValueError as error:
        raise AssertionError(f'valid core Barbarian2 creation rejected: {error}') from error
    return session


class BarbarianCreationTests(unittest.TestCase):
    def assert_two(self, session):
        c = session.character
        self.assertEqual((c['level'], c['progression_level'], c['xp'], c['proficiency_bonus']), (2, 2, 300, 2))
        self.assertEqual(c['constitution'], 14)
        self.assertEqual((c['max_hp'], c['current_hp']), (23, 23))
        self.assertEqual((hit_dice.total(c), hit_dice.die_size(c), hit_dice.spent(c)), (2, 12, 0))
        self.assertEqual(c['spell_slots_remaining'], {'1': 0})
        self.assertEqual((c['spells'], c['cantrips']), ([], []))
        self.assertNotIn('spellcasting_v1', session.world_state)
        self.assertNotIn('metamagic', c)
        self.assertNotIn('subclass_id', c)

    def test_actual_creation_one_two_and_fresh_restore(self):
        one = barbarian()
        cp.create_at_level(one, spec())
        self.assertEqual((one.character['level'], one.character['xp'], one.character['max_hp']), (1, 0, 14))
        session = create_two()
        self.assert_two(session)
        self.assertEqual(session.world_state.get('xp_awarded_event_ids', []), [])
        for field in ('inventory', 'proficient_skills', 'armor_class'):
            self.assertEqual(session.character[field], one.character[field])
        payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=91)
        restore_campaign_session(restored, payload)
        self.assert_two(restored)
        # Reckless now has its own accepted effect leaf; no longer claim it pending.
        self.assertIn('Rage', ' '.join(cp.progression_disclosure('Barbarian', 2)['supported']))
        for name in ('Weapon Mastery', 'Danger Sense'):
            self.assertIn(name, ' '.join(cp.progression_effects_pending('Barbarian', 2)))

    def test_exact_choices_and_unsupported_levels_reject_before_configuration(self):
        session = barbarian()
        cases = [None, [], '2', {}, {2: {}}, {'02': {}}, {'2': None}, {'2': []},
                 {'2': {'prepared_spells': []}}, {'2': {'metamagic': []}},
                 {'2': {}, '1': {}}, {'2': {}, '3': {}}]
        for value in cases:
            with self.subTest(choices=value):
                before = session._capture_runtime_snapshot()
                with patch('api.character_creation.configure_character') as configure:
                    with self.assertRaises(ValueError): cp.create_at_level(session, spec(), 2, value)
                    configure.assert_not_called()
                self.assertEqual(session._capture_runtime_snapshot(), before)
        for level in (0, 3, 4, 20, 21, True):
            with self.subTest(level=level):
                before = session._capture_runtime_snapshot()
                with patch('api.character_creation.configure_character') as configure:
                    with self.assertRaises(ValueError): cp.create_at_level(session, spec(), level, {'2': {}})
                    configure.assert_not_called()
                self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_former_sorcerer_cleanup_preserves_existing_reward_history(self):
        session = create_sorcerer(3)
        xp.apply_xp(session.character, session.world_state, 1, 'quest:prior-history')
        session.character['hit_dice'] = {'spent': 2, 'window_second': None, 'hp': None}
        events = copy.deepcopy(session.world_state['xp_awarded_event_ids'])
        create_two(session)
        self.assert_two(session)
        self.assertEqual(session.world_state['xp_awarded_event_ids'], events)

    def test_synthetic_failure_after_real_apply_restores_complete_populated_session(self):
        session = create_sorcerer(3)
        xp.apply_xp(session.character, session.world_state, 1, 'quest:rollback-prior')
        session.character['hit_dice'] = {'spent': 2, 'window_second': None, 'hp': None}
        session.messages.append({'role': 'user', 'content': 'sentinel'})
        session.recent_dm_narrations.append('sentinel')
        before = session._capture_runtime_snapshot()
        containers = (session.character, session.world_state, session.messages, session.recent_dm_narrations)
        real = cp.apply_level_choices
        applied = []
        def fail_after_apply(*args):
            result = real(*args)
            self.assertEqual(result['status'], 'applied')
            applied.append(args[0].character['progression_level'])
            raise RuntimeError('synthetic post-apply failure')
        with patch.object(cp, 'apply_level_choices', side_effect=fail_after_apply):
            with self.assertRaisesRegex(RuntimeError, 'synthetic post-apply failure'):
                create_two(session)
        self.assertEqual(applied, [2])
        self.assertEqual(session._capture_runtime_snapshot(), before)
        for old, current in zip(containers, (session.character, session.world_state, session.messages, session.recent_dm_narrations)):
            self.assertIs(old, current)

    def test_xp_boundary_keeps_applied_level_and_hit_dice_bounded(self):
        session = create_two()
        for amount, identity, expected in ((599, 'quest:below-three', (899, 2, 23)),
                                           (1, 'quest:reach-three', (900, 3, 32))):
            xp.apply_xp(session.character, session.world_state, amount, identity)
            c = session.character
            self.assertEqual((c['xp'], c['level'], c['max_hp']), expected)
            self.assertEqual((c['progression_level'], hit_dice.total(c)), (2, 2))
            before = session._capture_runtime_snapshot()
            self.assertIsNone(xp.apply_xp(c, session.world_state, amount, identity))
            self.assertEqual(session._capture_runtime_snapshot(), before)
        # Selected earned3 is now ready; unsupported4 remains a real boundary.
        self.assertEqual(cp.preview_level_up(session, 3)['status'], 'ready')
        self.assertEqual(cp.preview_level_up(session, 4)['status'], 'blocked')


class BarbarianCreationHttpBoundaryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown

    async def test_http_unsupported_start_three_stays_rejected_before_store(self):
        request = spec(); request['class'] = request.pop('character_class')
        # Public2 is now supported; retain a real unsupported higher-level boundary.
        request.update(mode='custom', starting_level=3, level_choices={'2': {}, '3': {}})
        with patch.object(self.store, 'create_campaign', wraps=self.store.create_campaign) as store:
            response = await self.http.post('/api/game/campaigns', json={'character': request})
            self.assertEqual(response.status_code, 422, response.text)
            store.assert_not_called()
