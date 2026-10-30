"""Selected MM slot2 dependency: actual Sorcerer3, existing cast/HTTP/receipt owners.
Official2024BasicRules source in decisions/C05-magic-missile-slot2-plan.md.
Single target only; deterministic rawdie2 produces four darts of3, total12.
"""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
import yaml
import game
import action_economy as ae
import character_progression as cp
import spell_registry
import spell_scope
from api.tests import test_spell_scope as fixtures
from api.tests.test_roadmap_c06_level3 import TWO, choices
from api.schemas import EconomyStepInput
from api.main import create_app
from api.auth import FixedAuthenticator
from api.tests.auth_fixture import TEST_PLAYER
from api.session_manager import SessionManager
from api.persistence.campaign_store import CampaignStore
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from combat_lifecycle import CombatRequestError

ROOT=Path(__file__).resolve().parents[3]


def caster3(session=None):
    s,e=fixtures.caster(session)
    assert cp.apply_level_choices(s,cp.preview_level_up(s,2),copy.deepcopy(TWO))['status']=='applied'
    assert cp.apply_level_choices(s,cp.preview_level_up(s,3),choices())['status']=='applied'
    return s,e


class SlotTwoTests(unittest.TestCase):
    def test_real_level_three_slot_two_spends_only_second_bucket_and_emits_four_darts(self):
        for first in (0,4):
            with self.subTest(first=first):
                s,e=caster3();s.world_state['spellcasting_v1']['slots']['1']=first
                with patch.object(s.rng,'randint',return_value=2):
                    result=spell_registry.cast_spell('Magic Missile',{'session':s},2,{'target_id':e['id']})
                self.assertEqual(result['status'],'applied',result)
                self.assertEqual(result['slot_level'],2);self.assertEqual(result['result']['slot_level'],2)
                self.assertEqual(result['result']['darts'],[3,3,3,3]);self.assertEqual(result['result']['damage'],12)
                self.assertEqual([x for x in result['changes'] if x['kind']=='spell_slot'],[{'kind':'spell_slot','level':2,'spent':1}])
                self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':first,'2':1})
                self.assertEqual(e['current_hp'],88)

    def test_default_slot_one_remains_three_darts(self):
        s,e=caster3()
        with patch.object(s.rng,'randint',return_value=2):r=spell_scope.cast(s,'Magic Missile',e['id'])
        self.assertEqual(r['darts'],[3,3,3]);self.assertEqual(r['slot_level'],1)
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':3,'2':2})

    def test_empty_unearned_or_unsupported_slot_refuses_before_rng_and_resources(self):
        for mode in ('empty-two','default-empty-one','unearned-two','unsupported-four'):
            with self.subTest(mode=mode):
                s,e=fixtures.caster() if mode=='unearned-two' else caster3()
                slot=2
                if mode=='empty-two':s.world_state['spellcasting_v1']['slots']['2']=0
                if mode=='default-empty-one':s.world_state['spellcasting_v1']['slots']['1']=0;slot=None
                if mode=='unsupported-four':slot=4  # Slot3 supported only with earned capacity; slot4 remains unsupported.
                before=s._capture_runtime_snapshot()
                with patch.object(s.rng,'randint',side_effect=AssertionError('rejected cast rolled')):
                    with self.assertRaises(CombatRequestError) as error:spell_scope.cast(s,'Magic Missile',e['id'],slot)
                expected='unsupported_spell_mode' if mode=='unsupported-four' else 'spell_slot_unavailable'
                self.assertEqual(error.exception.code,expected)
                self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_additional_action_does_not_allow_second_spell_slot_same_turn(self):
        s,e=caster3()
        try:spell_scope.cast(s,'Magic Missile',e['id'],2)
        except ValueError as error:self.fail(f'first slot2 cast rejected: {error}')
        ae.grant(s,'player','test_additional_magic',['magic'])
        before=s._capture_runtime_snapshot()
        with self.assertRaises(CombatRequestError) as error:spell_scope.cast(s,'Magic Missile',e['id'],1)
        self.assertEqual(error.exception.code,'spell_slot_turn_limit')
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_save_load_and_long_rest_preserve_selected_bucket(self):
        s,e=caster3()
        try:spell_scope.cast(s,'Magic Missile',e['id'],2)
        except ValueError as error:self.fail(f'slot2 cast rejected: {error}')
        s.commit_location_change('tavern')
        restored=game.create_session(seed=99);restore_campaign_session(restored,serialize_campaign_payload(s))
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'],{'1':4,'2':1})
        marker=copy.deepcopy(restored.world_state['spellcasting_v1']['slot_turn'])
        restored.end_combat('explicit_rest');restored.resolve_species_trait_action('long_rest')
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'],{'1':4,'2':2})
        self.assertEqual(restored.world_state['spellcasting_v1']['slot_turn'],marker)

    def test_direct_owner_rejects_malformed_or_other_spell_upcast(self):
        for spell, slot in [('Magic Missile', True), ('Magic Missile', '2'),
                            ('Magic Missile', 2.0), ('Magic Missile', 0),
                            ('Fire Bolt', 2)]:
            with self.subTest(spell=spell, slot=slot):
                s, e = caster3()
                before = s._capture_runtime_snapshot()
                with patch.object(s.rng, 'randint', side_effect=AssertionError('refusal rolled')):
                    with self.assertRaises(CombatRequestError) as error:
                        spell_scope.cast(s, spell, e['id'], slot)
                self.assertEqual(error.exception.code, 'unsupported_spell_mode')
                self.assertEqual(s._capture_runtime_snapshot(), before)

    def test_native_nonmagic_slot_choice_refuses(self):
        s,e=caster3();before=s._capture_runtime_snapshot()
        with self.assertRaises(CombatRequestError):ae.execute(s,{'steps':[{'kind':'dash','slot_level':2}]})
        self.assertEqual(s._capture_runtime_snapshot(),before)

    def test_schema_strictness_and_legacy_absent_field_fingerprint_shape(self):
        base={'kind':'magic','ability':'Magic Missile','target_id':'npc'}
        try:valid=EconomyStepInput.model_validate({**base,'slot_level':2})
        except ValueError as error:self.fail(f'valid slot selection rejected: {error}')
        self.assertEqual(valid.model_dump(exclude_none=True)['slot_level'],2)
        for value in (True,0,10,'2',2.0):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):EconomyStepInput.model_validate({**base,'slot_level':value})
        with self.assertRaises(ValueError):EconomyStepInput.model_validate({'kind':'dash','slot_level':2})
        self.assertEqual(EconomyStepInput.model_validate(base).model_dump(exclude_none=True),
                         EconomyStepInput.model_validate({**base,'slot_level':None}).model_dump(exclude_none=True))
        self.assertNotIn('slot_level',EconomyStepInput.model_validate(base).model_dump(exclude_none=True))

    def test_runtime_and_published_slot_field_contract_agree(self):
        runtime=EconomyStepInput.model_json_schema();self.assertIn('slot_level',runtime['properties'])
        self.assertNotIn('slot_level',runtime.get('required',[]))
        prop=runtime['properties']['slot_level'];branches={x['type']:x for x in prop['anyOf']}
        self.assertIn('null',branches);self.assertEqual((branches['integer']['minimum'],branches['integer']['maximum']),(1,9))
        published=yaml.safe_load((ROOT/'lib/api-spec/openapi.yaml').read_text())['components']['schemas']['EconomyStepInput']
        self.assertIn('slot_level',published['properties']);p=published['properties']['slot_level']
        self.assertEqual(set(p['type']),{'integer','null'});self.assertEqual((p['minimum'],p['maximum']),(1,9))
        self.assertNotIn('slot_level',published.get('required',[]))


class SlotTwoApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.SpellApiTests.asyncSetUp
    asyncTearDown=fixtures.SpellApiTests.asyncTearDown
    create_campaign=fixtures.SpellApiTests.create_campaign

    async def setup_slot2(self):
        created=await self.create_campaign();record=self.manager.get(created['session_id']);s,e=caster3(record.game_session)
        self.manager.save_campaign(created['campaign_id']);self.app.state.ollama_adapter=None
        combat=s.world_state['combat']
        request={'message':'Canonical spell only.','action_id':str(uuid4()),'combat_id':combat['combat_id'],
                 'combat_round':combat['round'],'combat_turn_index':combat['current_turn_index'],
                 'combat_action':{'steps':[{'kind':'magic','ability':'Magic Missile','target_id':e['id'],'slot_level':2}]}}
        return created,record,e,request,f"/api/game/sessions/{created['session_id']}/turn"

    async def test_http_explicit_slot_two_receipt_replays_after_reopen_without_reroll(self):
        created,record,e,request,url=await self.setup_slot2();s=record.game_session
        other=await self.create_campaign();other_session=self.manager.get(other['session_id']).game_session
        untouched=other_session._capture_runtime_snapshot()
        with patch.object(s.rng,'randint',return_value=2):first=await self.http.post(url,json=request)
        self.assertEqual(first.status_code,200,first.text)
        result=first.json()['combat_result']['economy_steps'][0]['result']
        self.assertEqual((result['slot_level'],result['darts'],result['damage']),(2,[3,3,3,3],12))
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':4,'2':1})
        self.assertEqual(other_session._capture_runtime_snapshot(),untouched)
        changed=copy.deepcopy(request);changed['combat_action']['steps'][0]['slot_level']=1
        conflict=await self.http.post(url,json=changed)
        self.assertEqual(conflict.status_code,409,conflict.text);self.assertEqual(conflict.json()['detail']['code'],'action_id_conflict')
        manager=SessionManager(campaign_store=CampaignStore(self.store.path,bound_principal=TEST_PLAYER))
        sid,resumed,*_=manager.resume_campaign(created['campaign_id']);restored=resumed.game_session
        self.assertEqual(restored.world_state['spellcasting_v1']['slots'],{'1':4,'2':1})
        before=restored._capture_runtime_snapshot()
        app=create_app(session_manager=manager,authenticator=FixedAuthenticator(TEST_PLAYER))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            with patch.object(restored,'run_player_turn',side_effect=AssertionError('replay reran engine')):
                replay=await client.post(f'/api/game/sessions/{sid}/turn',json=request)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['combat_result'],first.json()['combat_result'])
        self.assertEqual(restored._capture_runtime_snapshot(),before)

    async def test_slot_two_save_failure_rolls_back_and_retry_spends_once(self):
        created,record,e,request,url=await self.setup_slot2();s=record.game_session
        before=s._capture_runtime_snapshot();stored=self.store.get_campaign(created['campaign_id'])
        def fail_after_cast(*args, **kwargs):
            self.assertEqual(s.world_state['spellcasting_v1']['slots'], {'1':4,'2':1})
            self.assertLess(e['current_hp'], 100)
            raise CampaignStorageError('controlled post-cast slot2 save failure')
        with patch.object(self.store,'save_campaign',side_effect=fail_after_cast) as save:
            failed=await self.http.post(url,json=request)
        save.assert_called_once()
        self.assertEqual(failed.status_code,503,failed.text)
        self.assertEqual(s._capture_runtime_snapshot(),before)
        self.assertEqual(self.store.get_campaign(created['campaign_id']),stored)
        self.assertIsNone(self.store.get_turn_action(created['campaign_id'],request['action_id']))
        with patch.object(s.rng,'randint',return_value=2):retry=await self.http.post(url,json=request)
        self.assertEqual(retry.status_code,200,retry.text)
        self.assertEqual(s.world_state['spellcasting_v1']['slots'],{'1':4,'2':1})
        committed=s._capture_runtime_snapshot()
        with patch.object(s,'run_player_turn',side_effect=AssertionError('replay reran engine')):
            replay=await self.http.post(url,json=request)
        self.assertEqual(replay.json(),retry.json());self.assertEqual(s._capture_runtime_snapshot(),committed)
