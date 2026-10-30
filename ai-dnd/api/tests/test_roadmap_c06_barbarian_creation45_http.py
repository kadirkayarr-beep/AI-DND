"""Public selected-Berserker creation at starting levels 4 and 5 through the real ASGI app and synthetic SQLite campaigns.

Source values: PHB PDF 51 (Barbarian Features rows 4/5), PDF 40/42 (XP 2,700 / 6,500, minimum XP at the starting level).
Refusals are pinned by status AND by absence of any published campaign/session.
"""
import copy
import unittest
import httpx
from pydantic import ValidationError
from api.schemas import CharacterCreateInput
from api.tests import test_campaign_api as campaigns
from api.tests import test_roadmap_c06_level4_http as prior
from api.tests.test_roadmap_c06_barbarian import spec
from api.tests.test_roadmap_c06_barbarian_creation45 import PICK, asi, bundle
from api.dnd_2024_rules import get_character_creation_catalog

ASI = asi({'strength': 2})['asi']


def request(level, increase=None):
    value = spec()
    value['class'] = value.pop('character_class')
    value.update(mode='custom', starting_level=level, level_choices=bundle(level, increase))
    return value


class BarbarianCreationFourFiveHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaigns.CampaignApiTests.asyncSetUp
    asyncTearDown = campaigns.CampaignApiTests.asyncTearDown
    reopen = prior.LevelFourHttpTests.reopen

    def rows(self):
        with self.store._connect() as connection:
            return [tuple(row) for row in connection.execute('SELECT * FROM campaigns ORDER BY campaign_id')]

    async def test_actual_creation_stored_and_fresh_resumed_for_four_and_five(self):
        for level, hp, xp_value, version, pb in ((4, 41, 2700, 4, 2), (5, 50, 6500, 6, 3)):
            with self.subTest(level=level):
                response = await self.http.post('/api/game/campaigns', json={'character': request(level)})
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                saved = self.store.get_campaign(body['campaign_id']).payload['engine_save']
                self.assertEqual((saved['version'], saved['player']['xp'], saved['player']['current_hp'], saved['player']['max_hp']),
                                 (version, xp_value, hp, hp))
                self.assertEqual(saved['world_state'].get('xp_awarded_event_ids', []), [])
                public = body['state']['character']
                self.assertEqual((public['level'], public['proficiency_bonus'], public['rage']['uses_remaining']), (level, pb, 3))
                self.assertEqual(self.manager.get(body['session_id']).game_session.character['asi_choices'][0]['increase'], {'strength': 2})
                reopened, manager = await self.reopen(body)
                restored = manager.get(reopened['session_id']).game_session
                self.assertEqual((restored.character['level'], restored.character['progression_level'], restored.character['current_hp'],
                                  restored.character['max_hp'], restored.character['xp'], restored._persisted_engine_format),
                                 (level, level, hp, hp, xp_value, version))
                self.assertEqual(restored.character['subclass_id'], 'berserker')
                self.assertEqual(restored.world_state['rage_v1']['remaining'], 3)

    async def test_no_xp_award_or_level_up_offer_appears_after_creation(self):
        for level, reason in ((4, 'level_not_earned'), (5, 'target_not_above_applied_level')):
            body = (await self.http.post('/api/game/campaigns', json={'character': request(level)})).json()
            preview = await self.http.get(f"/api/game/sessions/{body['session_id']}/level-up")
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual((preview.json()['status'], preview.json()['reason']), ('blocked', reason), preview.text)

    async def test_both_creation_routes_accept_the_same_exact_bundle(self):
        for route in ('/api/game/campaigns', '/api/campaigns'):
            response = await self.http.post(route, json={'character': request(5)})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['state']['character']['level'], 5)

    async def test_catalog_exposes_fixed_start_four_five_shapes_with_source_vocabulary(self):
        from api.tests.test_roadmap_c06_nondex_asi_http import PATTERNS
        response = await self.http.get('/api/game/character-creation-catalog')
        self.assertEqual(response.status_code, 200, response.text)
        option = response.json()['barbarian_starting_creation']
        self.assertEqual(option['supported_starting_levels'], [1, 2, 3, 4, 5])
        self.assertEqual(option['level_4']['supported_asi_choices'], [{'feat': 'Ability Score Improvement', 'increase': p} for p in PATTERNS])
        self.assertIn('Extra Attack', ' '.join(option['level_5']['effects_supported']))
        self.assertIn('Weapon Mastery', ' '.join(option['level_4']['effects_pending']))
        for block in (option['level_4'], option['level_5']):
            self.assertIn('Higher-start equipment', ' '.join(block['effects_pending']))
        self.assertEqual(option['level_3']['subclass_options'], [{'id': 'berserker', 'name': 'Path of the Berserker'}])
        self.assertEqual(get_character_creation_catalog()['barbarian_starting_creation']['supported_starting_levels'], [1, 2, 3, 4, 5])
        self.assertEqual(response.json()['sorcerer_starting_creation']['supported_starting_levels'], [1, 2, 3, 4, 5])

    async def test_catalog_keeps_the_verified_prefix_when_a_source_row_is_wrong(self):
        import character_progression as cp
        from unittest.mock import patch
        source = cp.table('Barbarian')
        for row, expected in (('5', [1, 2, 3, 4]), ('4', [1, 2, 3])):
            levels = {**source['levels'], row: {**source['levels'][row], 'rages': 9}}
            with patch.object(cp, 'table', return_value={**source, 'levels': levels}):
                response = await self.http.get('/api/game/character-creation-catalog')
            self.assertEqual(response.json()['barbarian_starting_creation']['supported_starting_levels'], expected)

    async def test_actual_factory_and_published_schema_agree_for_the_new_fields(self):
        import yaml
        from pathlib import Path
        runtime = self.app.openapi()['components']['schemas']
        published = yaml.safe_load((Path(__file__).resolve().parents[3] / 'lib/api-spec/openapi.yaml').read_text())['components']['schemas']

        def norm(v):
            if isinstance(v, dict):
                return {k: norm(x) for k, x in v.items() if k not in ('title', 'description')}
            if isinstance(v, list):
                return [norm(x) for x in v]
            return v

        for name in ('BarbarianLevelChoices', 'BarbarianLevel4Choices', 'BarbarianLevel2Choices', 'BarbarianStartingLevel4Options',
                     'BarbarianStartingLevel5Options', 'BarbarianStartingCreationOptions'):
            self.assertEqual(norm(runtime[name]), norm(published[name]), name)
        self.assertEqual(set(published['BarbarianLevelChoices']['properties']), {'2', '3', '4', '5'})
        self.assertEqual(published['BarbarianLevelChoices']['required'], ['2'])

    async def test_invalid_bundles_origin_and_class_mix_never_publish(self):
        cases = []
        for level in (4, 5):
            def mutate(edit, level=level):
                value = request(level)
                edit(value)
                cases.append((level, value))
            mutate(lambda v: v['level_choices'].pop('4'))
            mutate(lambda v: v['level_choices'].pop('2'))
            mutate(lambda v: v['level_choices'].update({'4': None}))
            mutate(lambda v: v['level_choices'].update({'4': {}}))
            mutate(lambda v: v['level_choices']['4'].update({'extra': 1}))
            mutate(lambda v: v['level_choices'].update({'4': {'asi': {'feat': 'Ability Score Improvement', 'increase': {'dexterity': 2}}}}))
            mutate(lambda v: v['level_choices'].update({'4': {'asi': {'feat': 'Tough', 'increase': {'strength': 2}}}}))
            mutate(lambda v: v['level_choices'].update({'4': {'asi': {'feat': 'Ability Score Improvement', 'increase': {'strength': 3}}}}))
            mutate(lambda v: v['level_choices'].update({'4': {'asi': {'feat': 'Ability Score Improvement', 'increase': {'strength': True}}}}))
            mutate(lambda v: v['level_choices'].update({'4': {'asi': None}}))
            mutate(lambda v: v['level_choices'].update({'3': {**PICK, 'primal_knowledge_skill': 'Arcana'}}))
            mutate(lambda v: v['level_choices'].update({'3': {**PICK, 'primal_knowledge_skill': 'Athletics'}}))  # already owned
            mutate(lambda v: v['level_choices'].update({'3': {**PICK, 'subclass_id': 'wild_heart'}}))
            mutate(lambda v: v['level_choices'].update({'7': {}}))
            mutate(lambda v: v.update({'class': 'Wizard'}))
            mutate(lambda v: v.update({'class': 'Sorcerer'}))
            mutate(lambda v: v.update(mode='random'))
            mutate(lambda v: v.update(starting_level=float(level)))
            mutate(lambda v: v.update(starting_level=True))
            mutate(lambda v: v['ability_scores'].update(constitution=99))
        for edit in (lambda v: v['level_choices'].pop('5'), lambda v: v['level_choices'].update({'5': None}),
                     lambda v: v['level_choices'].update({'5': {'prepared_spells': []}}),
                     lambda v: v['level_choices'].update({'5': {'asi': ASI}})):
            value = request(5); edit(value); cases.append((5, value))
        value = request(4); value['level_choices']['5'] = {}; cases.append((4, value))  # level 5 body below a level-4 start
        value = request(5); value['starting_level'] = 4; cases.append((5, value))
        value = request(4); value['starting_level'] = 6; cases.append((6, value))
        before_rows, before_sessions = self.rows(), dict(self.manager._sessions)
        for level, value in cases:
            response = await self.http.post('/api/game/campaigns', json={'character': value})
            self.assertIn(response.status_code, (400, 422), (level, response.text))
            self.assertEqual(self.rows(), before_rows)
            self.assertEqual(self.manager._sessions, before_sessions)

    async def test_ineligible_constitution_asi_is_refused_by_the_real_owner_without_publishing(self):
        # A Shield-like AC extra that the canonical unarmored total cannot explain is not representable at creation; the owner
        # check is exercised here by a CON ASI request on a character whose AC is not the canonical formula.
        import character_progression as cp
        from unittest.mock import patch
        real = cp._barbarian_asi_options
        with patch.object(cp, '_barbarian_asi_options', side_effect=lambda session: [
                o for o in real(session) if o['increase'] != {'constitution': 2}]):
            response = await self.http.post('/api/game/campaigns', json={'character': request(4, {'constitution': 2})})
        self.assertIn(response.status_code, (400, 422), response.text)
        self.assertIn('asi_choice_not_eligible', response.text)
        self.assertEqual(self.rows(), [])

    async def test_actual_insert_then_fault_publishes_no_barbarian_four_or_five(self):
        import json
        import sqlite3
        from contextlib import contextmanager
        from unittest.mock import patch
        original = self.store._transaction
        for level, hp in ((4, 41), (5, 50)):
            before_rows, before_sessions = self.rows(), dict(self.manager._sessions)
            reached = []

            @contextmanager
            def fail_after_insert():
                with original() as connection:
                    yield connection
                    payloads = connection.execute('SELECT payload_json FROM campaigns').fetchall()
                    player = json.loads(payloads[-1][0])['engine_save']['player']
                    self.assertEqual((player['class'], player['level'], player['current_hp'], player['max_hp']), ('Barbarian', level, hp, hp))
                    reached.append(level)
                    raise sqlite3.OperationalError('synthetic after real Barbarian INSERT')

            with patch.object(self.store, '_transaction', side_effect=fail_after_insert):
                response = await self.http.post('/api/game/campaigns', json={'character': request(level)})
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(reached, [level])
            self.assertEqual(self.rows(), before_rows)
            self.assertEqual(self.manager._sessions, before_sessions)


class BarbarianCreationFourFiveShapeTests(unittest.TestCase):
    def test_exact_numeric_steps_round_trip_without_stripping(self):
        for level in (4, 5):
            try:
                value = CharacterCreateInput.model_validate(request(level))
            except ValidationError as error:
                self.fail(f'accepted bundle rejected publicly: {error}')
            self.assertEqual(value.level_choices.model_dump(by_alias=True, exclude_none=True), bundle(level))

    def test_a_sorcerer_bundle_is_not_a_barbarian_bundle(self):
        from api.tests.test_roadmap_c06_creation45 import steps
        value = request(4)
        value['level_choices'] = steps(4)
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate(value)
        sorcerer = copy.deepcopy(request(4))
        sorcerer['class'] = 'Sorcerer'
        with self.assertRaises(ValidationError):
            CharacterCreateInput.model_validate(sorcerer)


if __name__ == '__main__':
    unittest.main()
