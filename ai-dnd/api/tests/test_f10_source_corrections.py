"""Synthetic PHB 2024 pp.101/184/219 regressions; no live/model acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import game
from api.character_creation import configure_character
from api.dnd_2024_rules import BACKGROUND_DEFINITIONS, calculate_derived_stats
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload


SCORES = dict(strength=15, dexterity=13, constitution=14, intelligence=10, wisdom=12, charisma=8)
PACKAGES = {
    'Sailor': (["Dagger", "Navigator's Tools", "Rope", "Traveler's Clothes", "20 GP"], 20,
               {'strength': 2, 'wisdom': 1}, ['Acrobatics', 'Perception']),
    'Scribe': (["Calligrapher's Supplies", "Fine Clothes", "Lamp", "Oil (3 flasks)",
                "Parchment (12 sheets)", "23 GP"], 23,
               {'intelligence': 2, 'wisdom': 1}, ['Investigation', 'Perception']),
}


class SourceCorrectionsTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch('game.ollama.chat', side_effect=AssertionError('no model calls')).start()

    def create(self, background, option):
        _, _, bonuses, skills = PACKAGES[background]
        session = game.create_session(seed=101)
        configure_character(session, mode='custom', name='Synthetic Source Test',
            species='Dwarf', character_class='Fighter', background=background,
            alignment='Neutral Good', ability_score_method='standard_array',
            ability_scores=SCORES, background_ability_bonuses=bonuses,
            proficient_skills=['Athletics', 'Intimidation', *skills],
            fighting_style='Defense', equipment_package='A',
            background_equipment_option=option, languages=['Common', 'Orc', 'Goblin'])
        return session

    def test_new_sailor_and_scribe_exact_source_package_and_wallet(self):
        for background, (items, gp, _, _) in PACKAGES.items():
            with self.subTest(background=background):
                self.assertEqual(BACKGROUND_DEFINITIONS[background]['equipment'], items)
                session = self.create(background, 'A')
                self.assertEqual(session.world_state['currency']['player'], gp * 100)
                self.assertIn(f'{gp} GP', session.character['equipment_choices'])
                self.assertNotIn(f'{gp} GP', session.world_state['inventory'])
                for item in items[:-1]:
                    self.assertIn(item, session.world_state['inventory'])
                restored = game.create_session(seed=99)
                restore_campaign_session(restored, serialize_campaign_payload(session))
                self.assertEqual(restored.world_state['inventory'], session.world_state['inventory'])
                self.assertEqual(restored.world_state['currency'], session.world_state['currency'])

    def test_option_b_remains_50_gp_without_option_a_items(self):
        for background, (items, _, _, _) in PACKAGES.items():
            with self.subTest(background=background):
                session = self.create(background, 'B')
                self.assertEqual(session.world_state['currency']['player'], 5000)
                self.assertIn('50 Altın', session.character['equipment_choices'])
                self.assertNotIn('50 Altın', session.world_state['inventory'])
                self.assertNotIn(items[1], session.world_state['inventory'])

    def test_legacy_saves_keep_old_possessions_coins_wallet_and_ac(self):
        for background, old_items in [('Sailor', ['Denizci Pusulası', '15 Altın']),
                                      ('Scribe', ['Kayıt Defteri', '20 Altın'])]:
            for balance in [None, 731]:
                with self.subTest(background=background, balance=balance):
                    session = game.create_session(seed=101)
                    session.character.update(background=background, armor_class=17)
                    session.world_state['inventory'] = old_items.copy()
                    if balance is not None:
                        session.world_state['currency'] = {'player': balance}
                    else:
                        session.world_state.pop('currency', None)
                    expected_currency = copy.deepcopy(session.world_state.get('currency', {}))
                    with tempfile.TemporaryDirectory() as folder:
                        path = Path(folder)/'synthetic-legacy.json'
                        path.write_text(json.dumps(session.serialize_game_state()), encoding='utf-8')
                        restored = game.create_session()
                        self.assertTrue(restored.load_game(path))
                    self.assertEqual(restored.world_state['inventory'], old_items)
                    self.assertEqual(restored.world_state.get('currency', {}), expected_currency)
                    self.assertEqual(restored.character['armor_class'], 17)

    def test_unarmored_defense_and_shield_training_are_distinct(self):
        scores = dict(SCORES, dexterity=16, wisdom=18, constitution=14)
        # PHB 101: Monk loses Wisdom while wielding a shield. PHB 219:
        # this level-one Monk has no shield training, hence no +2 either.
        cases = [('Monk', False, None, 17), ('Monk', True, None, 13),
                 ('Monk', True, 'Leather Armor', 14),
                 ('Barbarian', False, None, 15), ('Barbarian', True, None, 17),
                 ('Fighter', True, 'Chain Mail', 18), ('Wizard', True, None, 13)]
        for cls, shield, armor, expected in cases:
            with self.subTest(cls=cls, shield=shield, armor=armor):
                result = calculate_derived_stats(cls, 'Human', scores,
                    has_shield=shield, equipped_armor=armor)
                self.assertEqual(result['armor_class'], expected)

    def test_monk_cannot_use_unarmored_defense_even_with_explicit_training(self):
        from api.dnd_2024_rules import CLASS_DEFINITIONS
        # Test-only prerequisite probe, not a new production grant or multiclass owner.
        with patch.dict(CLASS_DEFINITIONS['Monk'], armor_proficiencies=['Shields']):
            stats = calculate_derived_stats('Monk', 'Human', dict(SCORES, dexterity=16, wisdom=18), has_shield=True)
        self.assertEqual(stats['armor_class'], 15)


if __name__ == '__main__':
    unittest.main()
