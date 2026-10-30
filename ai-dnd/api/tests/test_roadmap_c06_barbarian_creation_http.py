"""Existing public custom creation, accepted Barbarian2 core; no new class effects."""
import copy
import unittest
from pydantic import ValidationError
from api.schemas import CharacterCreateInput
from api.tests import test_campaign_api as campaigns
from api.tests import test_roadmap_c06_level4_http as prior
from api.tests.test_roadmap_c06_barbarian import spec


def request(level=2):
    value = spec(); value['class'] = value.pop('character_class')
    value.update(mode='custom', starting_level=level)
    if level == 2: value['level_choices'] = {'2': {}}
    if level == 3: value['level_choices'] = {'2': {}, '3': {'subclass_id': 'berserker', 'primal_knowledge_skill': 'Survival'}}
    return value


class BarbarianCreationHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown
    reopen = prior.LevelFourHttpTests.reopen

    async def test_actual_custom_two_full_hp_noncasting_store_and_fresh_restore(self):
        response = await self.http.post('/api/game/campaigns', json={'character': request()})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json(); session = self.manager.get(body['session_id']).game_session
        player = session.character
        self.assertEqual((player['level'], player['progression_level'], player['xp'], player['max_hp'], player['current_hp']), (2, 2, 300, 23, 23))
        self.assertEqual(player['spell_slots_remaining'], {'1': 0})
        self.assertEqual((player['spells'], player['cantrips']), ([], []))
        self.assertNotIn('spellcasting_v1', session.world_state)
        self.assertEqual(session.world_state.get('xp_awarded_event_ids', []), [])
        saved = self.store.get_campaign(body['campaign_id']).payload['engine_save']
        self.assertEqual(saved['version'], 4)
        # Creation retains package labels until the existing equipment owner materializes instances.
        self.assertIn('Büyük Balta (Greataxe)', session.world_state['inventory'])
        self.assertEqual(session.world_state['equipment'], {'main_hand': 'greataxe', 'off_hand': None})
        import hit_dice
        self.assertEqual((hit_dice.total(player), hit_dice.remaining(player), hit_dice.die_size(player)), (2, 2, 12))
        self.assertIn('known-unarmored Barbarian 1–2', ' '.join(body['state']['character']['progression_effects_pending']))
        self.assertEqual(body['state']['character']['rage']['uses_remaining'], 2)
        reopened, manager = await self.reopen(body)
        restored = manager.get(reopened['session_id']).game_session
        self.assertEqual((restored.character['current_hp'], restored.character['xp']), (23, 300))
        self.assertNotIn('spellcasting_v1', restored.world_state)

    async def test_source_catalogue_has_independent_noncasting_capability_and_scope(self):
        response = await self.http.get('/api/game/character-creation-catalog')
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertIn('barbarian_starting_creation', value)
        option = value['barbarian_starting_creation']
        self.assertEqual(option['supported_starting_levels'], [1, 2, 3, 4, 5])  # start 4/5: test_roadmap_c06_barbarian_creation45_http
        self.assertEqual(option['level_3']['subclass_options'], [{'id': 'berserker', 'name': 'Path of the Berserker'}])
        self.assertEqual(len(option['level_3']['primal_knowledge_skill_options']), 6)
        self.assertNotIn('unsupported_species_bonus_feats', option['level_3'])
        self.assertEqual(option['level_2']['choices'], {})
        self.assertTrue(any('Reckless Attack' in x for x in option['level_2']['effects_supported']))
        self.assertTrue(any('Danger Sense' in x for x in option['level_2']['effects_supported']))
        self.assertTrue(any('Rage' in x for x in option['level_2']['effects_supported']))
        self.assertFalse(any('activation, resources, renewal and effects remain pending' in x for x in option['level_2']['effects_pending']))
        self.assertNotIn('prepared_spell_ids', option['level_2'])
        self.assertEqual(value['sorcerer_starting_creation']['supported_starting_levels'], [1, 2, 3, 4, 5])

    async def test_actual_custom_three_berserker_public_creation_store_and_fresh_restore(self):
        response = await self.http.post('/api/game/campaigns', json={'character': request(3)})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json(); session = self.manager.get(body['session_id']).game_session
        player = session.character
        self.assertEqual((player['level'], player['progression_level'], player['xp'], player['max_hp'], player['current_hp']), (3, 3, 900, 32, 32))
        self.assertEqual((player['subclass_id'], player['primal_knowledge_choice']['skill']), ('berserker', 'Survival'))
        self.assertIn('Survival', player['proficient_skills'])
        self.assertEqual(session.world_state['rage_v1']['remaining'], 3)
        self.assertNotIn('spellcasting_v1', session.world_state)
        self.assertEqual(session.world_state.get('xp_awarded_event_ids', []), [])
        reopened, manager = await self.reopen(body)
        restored = manager.get(reopened['session_id']).game_session
        self.assertEqual((restored.character['current_hp'], restored.character['xp'], restored.character['subclass_id']), (32, 900, 'berserker'))
        self.assertEqual(restored.character['primal_knowledge_choice'], player['primal_knowledge_choice'])

    async def test_invalid_start_three_bundles_never_publish(self):
        pick = {'subclass_id': 'berserker', 'primal_knowledge_skill': 'Survival'}
        for edit in [lambda x: x.update(level_choices={'2': {}}), lambda x: x.update(level_choices={'2': {}, '3': None}),
                     lambda x: x.update(level_choices={'2': {}, '3': {}}), lambda x: x.update(level_choices={'3': pick}),
                     lambda x: x.update(level_choices={'2': {}, '3': {**pick, 'extra': 1}}),
                     lambda x: x.update(level_choices={'2': {}, '3': {**pick, 'subclass_id': 'wild_heart'}}),
                     lambda x: x.update(level_choices={'2': {}, '3': {**pick, 'primal_knowledge_skill': 'Arcana'}}),
                     lambda x: x.update(level_choices={'2': {}, '3': pick, '4': {}}), lambda x: x.update(starting_level=2),
                     lambda x: x.update(starting_level=4), lambda x: x.update({'class': 'Sorcerer'}),
                     lambda x: x.update(level_choices={'2': {}, '3': {**pick, 'primal_knowledge_skill': 'Athletics'}})]:
            value = request(3); edit(value)
            response = await self.http.post('/api/game/campaigns', json={'character': value})
            self.assertIn(response.status_code, (422, 400), response.text)
        with self.store._connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM campaigns').fetchone()[0], 0)

    async def test_invalid_nonempty_null_missing_extra_or_other_class_never_publish(self):
        for edit in [lambda x:x.pop('level_choices'), lambda x:x.update(level_choices=None),
                     lambda x:x.update(level_choices={'2':None}), lambda x:x.update(level_choices={'2':{'forged':True}}),
                     lambda x:x.update(level_choices={'2':{},'3':{}}),lambda x:x.update(starting_level=3),
                     lambda x:x.update(mode='random'), lambda x:x.update({'class':'Wizard'}),lambda x:x.update({'class':'Sorcerer'})]:
            value=request();edit(value)
            response=await self.http.post('/api/game/campaigns',json={'character':value})
            self.assertEqual(response.status_code,422,response.text)
        with self.store._connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM campaigns').fetchone()[0],0)

    async def test_catalogue_fails_closed_on_missing_or_inconsistent_source_and_is_detached(self):
        import character_progression as cp
        from unittest.mock import patch
        value = cp.barbarian_starting_creation_options()
        self.assertIsNotNone(value)
        value['level_2']['choices']['forged'] = True
        self.assertEqual(cp.barbarian_starting_creation_options()['level_2']['choices'], {})
        source = copy.deepcopy(cp.table('Barbarian'))
        for broken in (None, {}, {**source, 'levels': {'1': source['levels']['1']}}):
            with patch.object(cp, 'table', return_value=broken):
                self.assertIsNone(cp.barbarian_starting_creation_options())
        with patch.object(cp, 'barbarian_starting_creation_options', return_value=None):
            response = await self.http.get('/api/game/character-creation-catalog')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['barbarian_starting_creation'])
        self.assertEqual(response.json()['sorcerer_starting_creation']['supported_starting_levels'], [1,2,3,4,5])

    async def test_actual_insert_then_fault_publishes_no_barbarian_two(self):
        import sqlite3,json
        from contextlib import contextmanager
        from unittest.mock import patch
        original = self.store._transaction; reached=[]
        before_sessions = dict(self.manager._sessions)
        @contextmanager
        def fail_after_insert():
            with original() as connection:
                yield connection
                rows = connection.execute('SELECT payload_json FROM campaigns').fetchall()
                if rows:
                    player = json.loads(rows[-1][0])['engine_save']['player']
                    self.assertEqual((player['class'],player['level'],player['xp'],player['current_hp']), ('Barbarian',2,300,23))
                    reached.append(True)
                    raise sqlite3.OperationalError('synthetic after real Barbarian INSERT')
        with patch.object(self.store,'_transaction',side_effect=fail_after_insert):
            response=await self.http.post('/api/game/campaigns',json={'character':request()})
        self.assertEqual(response.status_code,503,response.text)
        self.assertTrue(reached)
        self.assertEqual(self.manager._sessions,before_sessions)
        with self.store._connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM campaigns').fetchone()[0],0)

    async def test_actual_factory_schema_matches_published_new_fields(self):
        import yaml
        from pathlib import Path
        runtime=self.app.openapi()['components']['schemas']
        published=yaml.safe_load((Path(__file__).resolve().parents[3]/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']
        def norm(v):
            if isinstance(v,dict):return {k:norm(x) for k,x in v.items() if k not in ('title','description')}
            if isinstance(v,list):return [norm(x) for x in v]
            return v
        for name in ('BarbarianLevel2Choices','BarbarianLevel3Choices','BarbarianLevelChoices','BarbarianStartingLevel2Options','BarbarianStartingSubclassOption','BarbarianStartingLevel3Options','BarbarianStartingLevel4Options','BarbarianStartingLevel5Options','BarbarianLevel4Choices','BarbarianStartingCreationOptions','CharacterCreationCatalogResponse'):
            self.assertEqual(norm(runtime[name]),norm(published[name]),name)
        self.assertEqual(norm(runtime['CharacterCreateInput']['properties']['level_choices']),norm(published['CharacterCreateInput']['properties']['level_choices']))

    async def test_canonical_and_legacy_creation_routes_retain_identical_no_caster_projection(self):
        from unittest.mock import patch
        import xp
        for route in ('/api/game/campaigns','/api/campaigns'):
            with patch.object(xp,'apply_xp',side_effect=AssertionError('creation must not award XP')):
                response=await self.http.post(route,json={'character':request()})
            self.assertEqual(response.status_code,200,response.text)
            c=response.json()['state']['character']
            self.assertEqual((c['level'],c['current_hp'],c['xp']),(2,23,300))
            self.assertIn('known-unarmored Barbarian 1–2', ' '.join(c['progression_effects_pending']))
            self.assertEqual(c['rage']['uses_remaining'],2)


class BarbarianCreationShapeTests(unittest.TestCase):
    def test_exact_numeric_empty_step_is_accepted_without_stripping(self):
        try: value = CharacterCreateInput.model_validate(request())
        except ValidationError as error: self.fail(f'accepted core bundle rejected publicly: {error}')
        self.assertEqual(value.level_choices.model_dump(by_alias=True), {'2': {}})
