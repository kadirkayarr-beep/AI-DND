"""Mage Armor selection metadata only: accepted Sorcerer list PDF142.

No Mage Armor resolver, effects, or level4 entitlement is supplied here.
"""
import copy
import json
from pathlib import Path
import unittest

import game
import character_progression as cp
import spell_registry
import spell_scope
from combat_lifecycle import CombatRequestError
from api.dnd_2024_rules import SPELLS_CATALOG
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.tests.test_roadmap_c06 import SPEC
from api.tests.test_roadmap_c06_level3 import two, choices

PHB_OPTIONS = {'Magic Missile', 'Shield', 'Burning Hands', 'Chromatic Orb',
               'Disguise Self', 'Detect Magic', 'Mage Armor'}
NOTICE = 'Yalnızca seçim kaydıdır; büyünün oyun içi etkisi henüz desteklenmiyor.'
# Added by the later accepted Sorcerer start 4/5 slices; both are level-1 Sorcerer-list spells in the spells oracle (PDF 316 / PDF 275).
LATER_SLICE_OPTIONS = {'Silent Image', 'Fog Cloud'}


def selected_three(test):
    session = two()
    picks = choices()
    picks['prepared_spells'] = ['Disguise Self', 'Mage Armor']
    result = cp.apply_level_choices(session, cp.preview_level_up(session, 3), picks)
    test.assertEqual(result['status'], 'applied', result)
    return session


class MageArmorOptionTests(unittest.TestCase):
    def test_seven_literal_phb_options_and_legacy_option_are_distinct(self):
        entries = SPELLS_CATALOG['Sorcerer']['spells_level_1']
        names = {entry['id'] for entry in entries}
        self.assertEqual(names, PHB_OPTIONS | {'Chaos Bolt'} | LATER_SLICE_OPTIONS)
        self.assertEqual((len(PHB_OPTIONS), len(entries)), (7, 10))
        mage = next(entry for entry in entries if entry['id'] == 'Mage Armor')
        self.assertEqual(mage['desc'], NOTICE)
        root = Path(__file__).resolve().parents[3]
        header = json.loads((root / 'content/rules/phb2024/spells.json').read_text())['spells']['Mage Armor']
        self.assertEqual(header['level'], 1)
        self.assertIn('Sorcerer', header['classes'])
        self.assertEqual(spell_registry.spell_state('Mage Armor'), 'catalog_only')
        self.assertEqual(spell_registry.resolvers(), {'Fire Bolt': 0, 'Magic Missile': 1, 'Cure Wounds': 1, 'Sacred Flame': 0})

    def test_actual_level_three_selection_and_fresh_restore(self):
        session = selected_three(self)
        self.assertEqual((session.character['level'], session.character['progression_level']), (3, 3))
        self.assertEqual(len(session.world_state['spellcasting_v1']['prepared']), 6)
        self.assertIn('Mage Armor', session.character['spells'])
        payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=81)
        restore_campaign_session(restored, payload)
        self.assertEqual(restored.world_state['spellcasting_v1'], session.world_state['spellcasting_v1'])
        self.assertEqual(restored.character['spells'], session.character['spells'])

    def test_registry_and_direct_cast_remain_unsupported_without_resource_changes(self):
        session = selected_three(self)
        session.ensure_death_state()  # Avoid attributing canonical actor initialization to casting.
        before = session._capture_runtime_snapshot()
        slots = copy.deepcopy(session.world_state['spellcasting_v1']['slots'])
        result = spell_registry.cast_spell('Mage Armor', {'session': session}, 1, {'target_id': 'player'})
        self.assertEqual((result['status'], result['reason'], result['result'], result['changes']),
                         ('unsupported', 'spell_resolver_missing', None, []))
        self.assertEqual(session._capture_runtime_snapshot(), before)
        with self.assertRaises(CombatRequestError) as error:
            spell_scope.cast(session, 'Mage Armor', 'player', 1)
        self.assertEqual(error.exception.code, 'unsupported_spell')
        self.assertEqual(session._capture_runtime_snapshot(), before)
        self.assertEqual(session.world_state['spellcasting_v1']['slots'], slots)
        self.assertEqual(session.rng.getstate(), before['rng_state'])

    def test_catalog_projection_adds_option_without_new_level_support(self):
        options = cp.sorcerer_starting_creation_options()
        # Mage Armor itself adds no level support; starts 4 and 5 come from their own accepted Sorcerer slices.
        self.assertEqual(options['supported_starting_levels'], [1, 2, 3, 4, 5])
        self.assertIn('Mage Armor', options['level_2']['prepared_spell_ids'])
        self.assertIn('Mage Armor', options['level_3']['prepared_spell_ids'])
        session = two()
        before = session._capture_runtime_snapshot()
        self.assertEqual(cp.preview_level_up(session, 4)['status'], 'blocked')
        with self.assertRaises(ValueError): cp.create_at_level(session, SPEC, 4, {})
        self.assertEqual(session._capture_runtime_snapshot(), before)
