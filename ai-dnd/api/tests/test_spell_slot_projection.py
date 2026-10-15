"""Synthetic API projection regressions; no live campaigns or models."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game
import spell_scope
from api.serializers import serialize_session_state
from api.tests.test_spell_scope import caster


class SpellSlotProjectionTests(unittest.TestCase):
    def assert_projection(self, session, expected):
        before=copy.deepcopy((session.serialize_game_state(),session.rng.getstate()))
        public=serialize_session_state(session)
        self.assertEqual(public['spellcasting']['slots'], {'1':expected})
        self.assertEqual(public['character']['spell_slots_remaining'], {'1':expected})
        public['character']['spell_slots_remaining']['1']=99
        self.assertEqual(public['spellcasting']['slots'], {'1':expected})
        self.assertEqual(before,(session.serialize_game_state(),session.rng.getstate()))

    def test_native_cast_overrides_stale_character_projection_without_mutating_save(self):
        session, enemy=caster()
        session.character['spell_slots_remaining']={'1':2}
        with patch('game.ollama.chat',side_effect=AssertionError('no model')):
            spell_scope.cast(session,'Magic Missile',enemy['id'])
        self.assertEqual(session.character['spell_slots_remaining'],{'1':2})
        self.assert_projection(session,1)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic.json'
            session.save_game(path)
            restored=game.GameSession()
            restored.load_game(path)
            self.assert_projection(restored,1)
            self.assertEqual(restored.character['spell_slots_remaining'],{'1':2})

    def test_native_zero_remaining_and_capacity_are_not_inferred_from_legacy_field(self):
        for remaining in (0,1,2):
            session,_=caster()
            session.character['spell_slots_remaining']={'1':2}
            session.world_state['spellcasting_v1']['slots']={'1':remaining}
            self.assert_projection(session,remaining)
        session.world_state['spellcasting_v1']['slots']={'1':3}
        with self.assertRaises(ValueError):
            game._validate_save_payload(session.serialize_game_state())

    def test_short_and_long_rest_project_native_owner_without_changing_capacity(self):
        from api.tests.test_campaign_time import scene
        session, enemy=caster(scene())
        session.character['spell_slots_remaining']={'1':2}
        spell_scope.cast(session,'Magic Missile',enemy['id'])
        session.end_combat('synthetic rest setup')
        session.resolve_species_trait_action('short_rest')
        self.assert_projection(session,1)
        session.resolve_species_trait_action('long_rest')
        self.assert_projection(session,2)

    def test_legacy_without_native_owner_retains_saved_remaining_slots(self):
        for version in (3,4,5):
            session=game.create_session(seed=7)
            session._persisted_engine_format=version
            session.character['spell_slots_remaining']={'1':1}
            self.assertNotIn('spellcasting_v1',session.world_state)
            before=copy.deepcopy(session.serialize_game_state())
            public=serialize_session_state(session)
            self.assertIsNone(public['spellcasting'])
            self.assertEqual(public['character']['spell_slots_remaining'],{'1':1})
            self.assertEqual(session.serialize_game_state(),before)
