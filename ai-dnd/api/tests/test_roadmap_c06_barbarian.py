"""Bounded Barbarian 1→2 state; PHB PDF50/51 and C06 PDF40/41 values only."""
import copy
import unittest

import game
import xp
import hit_dice
import character_progression as cp
from api.character_creation import configure_character
from api.persistence.campaign_validation import serialize_campaign_payload, restore_campaign_session
from api.persistence.campaign_models import CampaignCorruptError
from api.schemas import CharacterCreateInput
from api.tests.test_roadmap_c06 import SPEC


def spec():
    result = copy.deepcopy(SPEC)
    result.update(character_class='Barbarian', cantrips=[], spells=[],
                  proficient_skills=['Athletics', 'Perception', 'Persuasion', 'Sleight of Hand', 'Stealth'])
    return result


def barbarian():
    session = game.create_session(seed=52)
    configure_character(session, mode='custom', **spec())
    return session


def advance(test, session):
    result = cp.apply_level_choices(session, cp.preview_level_up(session, 2), {})
    test.assertEqual(result['status'], 'applied', result)
    return result


class BarbarianProgressionTests(unittest.TestCase):
    def test_source_row_and_pure_noncasting_preview(self):
        session = barbarian()
        before = session._capture_runtime_snapshot()
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(preview['status'], 'ready')
        self.assertEqual(preview['choices_required'], {})
        self.assertIsNone(preview['capacity'])
        self.assertIsNone(cp.capacity(session.character))
        self.assertEqual(preview['features'], ['Danger Sense', 'Reckless Attack'])
        self.assertEqual(session._capture_runtime_snapshot(), before)
        row = cp.table('Barbarian')['levels']['2']
        self.assertEqual((row['proficiency_bonus'], row['rages'], row['rage_damage'], row['weapon_mastery']), (2, 2, 2, 2))
        # Applied1 cannot skip its earlier level2 choices to reach selected3.
        self.assertEqual(cp.preview_level_up(session, 3)['status'], 'blocked')
        self.assertEqual(cp.preview_level_up(session, 4)['status'], 'blocked')

    def test_apply_preserves_noncasting_world_and_existing_choices(self):
        session = barbarian()
        before = copy.deepcopy(session.world_state)
        kept = {k: copy.deepcopy(session.character[k]) for k in ('inventory', 'proficient_skills', 'armor_class', 'spell_slots_remaining')}
        hp = session.character['max_hp']
        delta = advance(self, session)
        self.assertEqual(session.world_state, before)
        self.assertEqual({k: session.character[k] for k in kept}, kept)
        self.assertEqual(session.character['spell_slots_remaining'], {'1': 0})
        self.assertNotIn('spellcasting_v1', session.world_state)
        self.assertNotIn('metamagic', session.character)
        self.assertNotIn('subclass_id', session.character)
        self.assertEqual(session.character['max_hp'], hp + 9)
        self.assertEqual((session.character['level'], session.character['progression_level'], session.character['proficiency_bonus']), (2, 2, 2))
        # Reckless now has an accepted effect leaf; retain the truly pending scopes.
        self.assertIn('Rage', ' '.join(cp.progression_disclosure('Barbarian', 2)['supported']))
        for effect in ('Weapon Mastery', 'Danger Sense'):
            self.assertIn(effect, ' '.join(delta['effects_pending']))

    def test_xp_first_pays_hp_once_and_unlocks_only_applied_hit_die(self):
        session = barbarian()
        session.character['hit_dice'] = {'spent': 1, 'window_second': None, 'hp': None}
        xp.apply_xp(session.character, session.world_state, 300, 'quest:barbarian-two')
        hp = session.character['max_hp']
        self.assertEqual((hit_dice.total(session.character), hit_dice.remaining(session.character)), (1, 0))
        advance(self, session)
        self.assertEqual(session.character['max_hp'], hp)
        self.assertEqual((hit_dice.die_size(session.character), hit_dice.total(session.character), hit_dice.remaining(session.character)), (12, 2, 1))
        self.assertEqual(session.character['hit_dice']['spent'], 1)

    def test_rejected_choices_preserve_snapshot_and_rng(self):
        session = barbarian()
        preview = cp.preview_level_up(session, 2)
        self.assertEqual(preview['status'], 'ready')
        for choices in (None, [], {'prepared_spells': []}, {'metamagic': []}, {'subclass_id': 'bad'}, {'unknown': 1}):
            with self.subTest(choices=choices):
                before = session._capture_runtime_snapshot()
                self.assertEqual(cp.apply_level_choices(session, preview, choices)['status'], 'rejected')
                self.assertEqual(session._capture_runtime_snapshot(), before)
        changed = copy.deepcopy(preview); changed['hit_points']['gain'] += 1
        before = session._capture_runtime_snapshot()
        self.assertEqual(cp.apply_level_choices(session, changed, {})['status'], 'rejected')
        self.assertEqual(session._capture_runtime_snapshot(), before)
        advance(self, session)
        before = session._capture_runtime_snapshot()
        self.assertEqual(cp.apply_level_choices(session, preview, {})['status'], 'rejected')
        self.assertEqual(session._capture_runtime_snapshot(), before)

    def test_even_none_spellstate_is_rejected_without_mutation(self):
        session = barbarian()
        session.world_state['spellcasting_v1'] = None
        before = session._capture_runtime_snapshot()
        self.assertEqual(cp.apply_level_choices(session, cp.preview_level_up(session, 2), {})['status'], 'rejected')
        self.assertEqual(session._capture_runtime_snapshot(), before)
        with self.assertRaises(ValueError):
            cp.validate_saved({**session.character, 'progression_level': 1}, session.world_state)
        with self.assertRaises(ValueError):
            cp.validate_saved(session.character, session.world_state)

    def test_roundtrip_xp_ahead_level_three_applied_two_and_spent_die(self):
        session = barbarian()
        advance(self, session)
        session.character['hit_dice'] = {'spent': 1, 'window_second': None, 'hp': None}
        xp.apply_xp(session.character, session.world_state, 900, 'quest:pending-three')
        payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=53)
        restore_campaign_session(restored, payload)
        self.assertEqual((restored.character['level'], restored.character['progression_level']), (3, 2))
        self.assertEqual(hit_dice.remaining(restored.character), 1)
        self.assertNotIn('spellcasting_v1', restored.world_state)
        self.assertEqual(restored.character['spell_slots_remaining'], {'1': 0})
        # Selected earned3 is now ready; unsupported4 remains a real boundary.
        self.assertEqual(cp.preview_level_up(restored, 3)['status'], 'ready')
        self.assertEqual(cp.preview_level_up(restored, 4)['status'], 'blocked')
        bad = copy.deepcopy(payload)
        bad['engine_save']['player']['progression_level'] = 3
        with self.assertRaises(CampaignCorruptError):
            restore_campaign_session(barbarian(), bad)

    def test_saved_injections_reject_before_target_mutation(self):
        session = barbarian(); advance(self, session)
        payload = serialize_campaign_payload(session)
        changes = [('progression_level', 3), ('progression_level', True), ('subclass_id', 'bad'),
                   ('metamagic', None), ('metamagic', {}), ('metamagic', ''), ('metamagic', ['Quickened Spell']),
                   ('hit_dice', {'spent': 3, 'window_second': None, 'hp': None})]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                bad = copy.deepcopy(payload); bad['engine_save']['player'][key] = value
                target = barbarian(); before = target._capture_runtime_snapshot()
                with self.assertRaises(CampaignCorruptError): restore_campaign_session(target, bad)
                self.assertEqual(target._capture_runtime_snapshot(), before)
        for value in (None, {}):
            bad = copy.deepcopy(payload); bad['engine_save']['world_state']['spellcasting_v1'] = value
            with self.assertRaises(CampaignCorruptError): restore_campaign_session(barbarian(), bad)

    def test_empty_metamagic_list_is_legacy_compatible(self):
        session = barbarian(); advance(self, session)
        cp.validate_saved({**session.character, 'metamagic': []}, session.world_state)

    def test_unsupported_start_three_core_and_http_schema_stay_blocked(self):
        session = barbarian(); before = session._capture_runtime_snapshot()
        # Core creation2 gets its own positive proof; actual unsupported3 remains rejected.
        with self.assertRaises(ValueError): cp.create_at_level(session, spec(), 3, {'2': {}, '3': {}})
        self.assertEqual(session._capture_runtime_snapshot(), before)
        # Public2 now has positive HTTP proof; keep schema rejection at unsupported3.
        request = spec(); request.update(mode='custom', starting_level=3, level_choices={'2': {}, '3': {}})
        with self.assertRaises(ValueError): CharacterCreateInput.model_validate(request)
        self.assertEqual(cp.sorcerer_starting_creation_options()['supported_starting_levels'], [1, 2, 3, 4, 5])
