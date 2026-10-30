"""Typed source-owned creation choice metadata; no grants or UI readiness claim."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml
import character_progression as cp
from api.dnd_2024_rules import get_character_creation_catalog, SPELLS_CATALOG
from api.tests import test_campaign_api as fixtures
from api.tests.test_roadmap_c06_level3 import IDS

ROOT = Path(__file__).resolve().parents[3]


class CreationCatalogTests(unittest.TestCase):
    def options(self):
        helper = getattr(cp, 'sorcerer_starting_creation_options', None)
        self.assertTrue(callable(helper), 'source-owned creation options helper is absent')
        return helper()

    def test_literal_supported_levels_counts_and_source_option_ids(self):
        catalog = get_character_creation_catalog()
        self.assertIn('sorcerer_starting_creation', catalog)
        options = catalog['sorcerer_starting_creation']
        self.assertEqual(options['supported_starting_levels'], [1, 2, 3, 4, 5])
        self.assertEqual(options['level_2']['prepared_spell_count'], 2)
        self.assertEqual(options['level_2']['metamagic_count'], 2)
        self.assertEqual(options['level_3']['prepared_spell_count'], 2)
        ids = [x['id'] for x in SPELLS_CATALOG['Sorcerer']['spells_level_1']]
        self.assertIn('Chaos Bolt', ids, 'legacy membership must not be silently removed')
        self.assertEqual(options['level_2']['prepared_spell_ids'], ids)
        self.assertEqual(options['level_3']['prepared_spell_ids'], ids)
        self.assertEqual(options['level_2']['metamagic_options'], cp.table('Sorcerer')['metamagic_options'])
        self.assertEqual({x['id'] for x in options['level_3']['subclass_options']}, set(IDS))
        self.assertEqual(set(options['effects_pending_by_level']), {'1', '2', '3', '4', '5'})
        for level in (1, 2, 3):
            self.assertEqual(options['effects_pending_by_level'][str(level)], cp.progression_effects_pending('Sorcerer', level))
        self.assertNotIn('slots', options); self.assertNotIn('sorcery_points', options)

    def test_projection_is_detached_without_mutating_warmed_source(self):
        source = cp.table('Sorcerer'); before = copy.deepcopy(source)
        spells_before = copy.deepcopy(SPELLS_CATALOG['Sorcerer'])
        first = self.options(); second = self.options()
        first['level_2']['prepared_spell_ids'].clear()
        first['level_3']['prepared_spell_ids'].append('client edit')
        first['level_2']['metamagic_options'].clear()
        first['level_3']['subclass_options'][0]['name'] = 'client edit'
        first['effects_pending_by_level']['3'].clear()
        self.assertEqual(cp.table('Sorcerer'), before)
        self.assertEqual(SPELLS_CATALOG['Sorcerer'], spells_before)
        self.assertEqual(second, self.options())

    def test_missing_source_or_core_support_fails_closed_and_future_core_does_not_expand_http(self):
        with patch.object(cp, 'MAX_SUPPORTED_LEVEL', 2): self.assertIsNone(self.options())
        with patch.object(cp, 'MAX_SUPPORTED_LEVEL', 20): self.assertEqual(self.options()['supported_starting_levels'], [1, 2, 3, 4, 5])
        with patch.object(cp, 'table', return_value=None): self.assertIsNone(self.options())
        for missing in ('row', 'metamagic', 'subclass'):
            with self.subTest(missing=missing):
                bad = copy.deepcopy(cp.table('Sorcerer'))
                if missing == 'row': del bad['levels']['3']
                if missing == 'metamagic': bad['metamagic_options'] = []
                if missing == 'subclass': bad['subclass_options'] = {}
                with patch.object(cp, 'table', return_value=bad): self.assertIsNone(self.options())


    def test_incompatible_fixed_http_bundle_is_not_advertised(self):
        for mode in ('wrong-step-count', 'wrong-base', 'three-metamagic', 'third-level-metamagic', 'one-distinct-metamagic', 'too-few-spells'):
            with self.subTest(mode=mode):
                source = copy.deepcopy(cp.table('Sorcerer'))
                catalog = copy.deepcopy(SPELLS_CATALOG['Sorcerer'])
                if mode == 'wrong-step-count': source['levels']['2']['prepared_spells'] = 5
                if mode == 'wrong-base':
                    for level, count in zip(('1', '2', '3'), (3, 5, 7)): source['levels'][level]['prepared_spells'] = count
                if mode == 'three-metamagic': source['metamagic_choice_counts']['2'] = 3
                if mode == 'third-level-metamagic': source['metamagic_choice_counts']['3'] = 1
                if mode == 'one-distinct-metamagic': source['metamagic_options'] = ['Quickened Spell', 'Quickened Spell']
                if mode == 'too-few-spells': catalog['spells_level_1'] = catalog['spells_level_1'][:5]
                with patch.object(cp, 'table', return_value=source), patch.dict(SPELLS_CATALOG, {'Sorcerer': catalog}):
                    self.assertIsNone(self.options())


class CreationCatalogApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CampaignApiTests.asyncSetUp
    asyncTearDown = fixtures.CampaignApiTests.asyncTearDown

    async def test_canonical_and_alias_keep_typed_numeric_pending_keys(self):
        for url in ('/api/game/character-creation-catalog', '/api/character-creation-catalog'):
            with self.subTest(url=url):
                response = await self.http.get(url)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn('sorcerer_starting_creation', response.json())
                options = response.json()['sorcerer_starting_creation']
                self.assertEqual(options['supported_starting_levels'], [1, 2, 3, 4, 5])
                self.assertEqual(set(options['effects_pending_by_level']), {'1', '2', '3', '4', '5'})
                self.assertEqual({x['id'] for x in options['level_3']['subclass_options']}, set(IDS))
        with patch.object(cp, 'MAX_SUPPORTED_LEVEL', 2):
            response = await self.http.get('/api/game/character-creation-catalog')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(response.json().get('sorcerer_starting_creation'))

    async def test_runtime_and_published_nested_contract_is_explicit(self):
        runtime = self.app.openapi()['components']['schemas']
        published = yaml.safe_load((ROOT/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']
        for schemas in (runtime, published):
            with self.subTest(runtime=schemas is runtime):
                self.assertIn('sorcerer_starting_creation', schemas['CharacterCreationCatalogResponse']['properties'])
                bundle = schemas['SorcererStartingCreationOptions']
                self.assertEqual(set(bundle['required']), {'supported_starting_levels','level_2','level_3','level_4','level_5','effects_pending_by_level'})
                self.assertIn('$ref', bundle['properties']['level_2'])
                self.assertIn('$ref', bundle['properties']['level_3'])
                pending = schemas['SorcererEffectsPendingByLevel']
                self.assertEqual(set(pending['properties']), {'1', '2', '3', '4', '5'})
                self.assertEqual(set(pending['required']), {'1', '2', '3', '4', '5'})
                for value in pending['properties'].values(): self.assertEqual(value['type'], 'array')
