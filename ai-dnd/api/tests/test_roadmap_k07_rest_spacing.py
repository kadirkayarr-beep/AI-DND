"""PHB2024 PDF369: wait16h after completing Long Rest before STARTING next.

The requested8h does not count toward eligibility; first legacy rest is allowed
because absent historical information cannot be invented. Resume is separate.
"""
import copy
import unittest
import game
from api.tests.test_campaign_time import scene
from api.tests.test_campaign_time_edges import event
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError

MARKER = 'last_long_rest_completed_at'


class RestSpacingTests(unittest.TestCase):
    def test_spacing_oracle_has_normal_boundary_and_interaction_cases(self):
        import rule_oracles
        data = rule_oracles.load_oracles()
        leaves = [x for x in data['leaves'] if x['leaf_id'] == 'K07.long_rest_start_spacing']
        self.assertEqual(len(leaves), 1, 'Long Rest spacing source oracle missing')
        self.assertEqual(leaves[0]['source_ref']['pdf_page'], 369)
        self.assertEqual({x['kind'] for x in leaves[0]['cases']}, {'normal', 'boundary', 'interaction'})
        for case in leaves[0]['cases']:
            result = rule_oracles.evaluate_rule_case('K07.long_rest_start_spacing#' + case['id'], data)
            self.assertTrue(result['match'], result)

    def test_first_rest_stamps_actual_completion_and_blocks_immediate_repeat(self):
        session = scene()
        session.resolve_species_trait_action('long_rest')
        self.assertEqual(session.world_state.get(MARKER), 28800)
        before = copy.deepcopy((session.world_state, session.character, session.rng.getstate()))
        with self.assertRaisesRegex(ValueError, '16'):
            session.resolve_species_trait_action('long_rest', elapsed_seconds=86400)
        self.assertEqual((session.world_state, session.character, session.rng.getstate()), before)

    def test_start_boundary_is_57600_since_completion_not_since_start(self):
        for elapsed, allowed in ((57599, False), (57600, True)):
            with self.subTest(elapsed=elapsed):
                session = scene()
                session.resolve_species_trait_action('long_rest')
                session.advance_campaign_time(elapsed, 'wait')
                before = copy.deepcopy((session.world_state, session.character, session.rng.getstate()))
                if allowed:
                    session.resolve_species_trait_action('long_rest')
                    self.assertEqual(session.world_state.get(MARKER), 115200)
                else:
                    with self.assertRaisesRegex(ValueError, '16'):
                        session.resolve_species_trait_action('long_rest')
                    self.assertEqual((session.world_state, session.character, session.rng.getstate()), before)

    def test_short_rest_does_not_reset_completed_long_rest_timestamp(self):
        session = scene()
        session.resolve_species_trait_action('long_rest')
        session.resolve_species_trait_action('short_rest')
        self.assertEqual(session.world_state.get(MARKER), 28800)
        self.assertEqual(session.world_state['campaign_time']['elapsed_seconds'], 32400)

    def test_interrupted_rest_never_stamps_completion(self):
        for prior in (False, True):
            with self.subTest(prior=prior):
                session = scene()
                if prior:
                    session.resolve_species_trait_action('long_rest')
                    session.advance_campaign_time(57600, 'wait')
                now = session.world_state['campaign_time']['elapsed_seconds']
                event(session, 'interrupt-rest', now+3700, now+5400,
                      behavior='FORCED', summary='Leave the building.')
                result = session.resolve_species_trait_action('long_rest')
                self.assertFalse(result['effects']['rest_completed'])
                self.assertTrue(result['effects']['short_rest_hit_dice'])
                if prior:
                    self.assertEqual(session.world_state.get(MARKER), 28800)
                else:
                    self.assertNotIn(MARKER, session.world_state)

    def test_reload_preserves_spacing_and_old_save_missing_marker(self):
        session = scene()
        session.resolve_species_trait_action('long_rest')
        payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=99)
        restore_campaign_session(restored, payload)
        self.assertEqual(restored.world_state.get(MARKER), 28800)
        with self.assertRaisesRegex(ValueError, '16'):
            restored.resolve_species_trait_action('long_rest')
        payload['engine_save']['world_state'].pop(MARKER, None)
        legacy = game.create_session(seed=99)
        restore_campaign_session(legacy, payload)
        self.assertNotIn(MARKER, legacy.world_state)
        legacy.resolve_species_trait_action('long_rest')
        self.assertEqual(legacy.world_state.get(MARKER), 57600)

    def test_invalid_marker_is_rejected_on_load_without_mutation(self):
        for bad in (True, -1, 0.5, '0', None, 1):
            with self.subTest(bad=bad):
                payload = serialize_campaign_payload(scene())
                payload['engine_save']['world_state'][MARKER] = bad
                restored = game.create_session(seed=99)
                before = copy.deepcopy((restored.world_state, restored.character))
                with self.assertRaises(CampaignCorruptError):
                    restore_campaign_session(restored, payload)
                self.assertEqual((restored.world_state, restored.character), before)
