"""The Wizard and Cleric start options and level choices read back through their typed models (G2.12 schemas).

`test_g212_wizard_cleric_start_http` reads the catalog as plain dicts. Here the same catalog is read the way the
response model types it, so a field that is renamed or dropped in the model fails a test, and each new model is
pinned to refuse a key it does not know."""
from __future__ import annotations

import unittest

from pydantic import BaseModel, ValidationError

from api.schemas import (
    BarbarianLevel2Choices,
    CharacterCreationCatalogResponse,
    ClericLevelChoices,
    ClericStartingCreationOptions,
    ClericStartingLevel3Options,
    ClericStartingLevel4Options,
    WizardLevelChoices,
    WizardStartingCreationOptions,
    WizardStartingLevel3Options,
    WizardStartingLevel4Options,
    WizardStartingSpellbookOptions,
)
from api.tests.test_wizard_cleric_4c3 import CHOICES
from dnd_2024_rules import get_character_creation_catalog

NEW_MODELS: tuple[type[BaseModel], ...] = (
    WizardLevelChoices, ClericLevelChoices, WizardStartingSpellbookOptions, WizardStartingLevel3Options,
    WizardStartingLevel4Options, WizardStartingCreationOptions, ClericStartingLevel3Options,
    ClericStartingLevel4Options, ClericStartingCreationOptions,
)


class TestStartOptionsModels(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = CharacterCreationCatalogResponse.model_validate(get_character_creation_catalog())

    def test_the_wizard_start_options_read_back_level_by_level(self) -> None:
        wizard = self.catalog.wizard_starting_creation
        if wizard is None:
            self.fail("the catalog offers a Wizard start")
        self.assertEqual(wizard.supported_starting_levels, [1, 2, 3, 4, 5])
        for book in (wizard.level_2, wizard.level_5):
            self.assertEqual(book.spellbook_spell_count, 2)
            self.assertGreaterEqual(len(book.spellbook_spell_ids), 2)
        self.assertEqual(wizard.level_3.spellbook_spell_count, 2)
        self.assertEqual([option.id for option in wizard.level_3.subclass_options], ["evoker"])
        self.assertEqual(wizard.level_4.cantrip_count, 1)
        self.assertTrue(wizard.level_4.cantrip_ids)
        self.assertTrue(wizard.level_4.supported_asi_choices)
        self.assertEqual(wizard.level_4.spellbook_spell_count, 2)
        self.assertGreaterEqual(len(wizard.level_3.spellbook_spell_ids), 2)
        self.assertIsInstance(wizard.effects_pending_by_level.level_1, list)

    def test_the_cleric_start_options_read_back_level_by_level(self) -> None:
        cleric = self.catalog.cleric_starting_creation
        if cleric is None:
            self.fail("the catalog offers a Cleric start")
        self.assertEqual(cleric.supported_starting_levels, [1, 2, 3, 4, 5])
        self.assertIsInstance(cleric.level_2, BarbarianLevel2Choices)
        self.assertIsInstance(cleric.level_5, BarbarianLevel2Choices)
        self.assertEqual([option.id for option in cleric.level_3.subclass_options], ["life_domain"])
        self.assertEqual(cleric.level_4.cantrip_count, 1)
        self.assertTrue(cleric.level_4.cantrip_ids)
        self.assertTrue(cleric.level_4.supported_asi_choices)
        self.assertIsInstance(cleric.effects_pending_by_level.level_5, list)

    def test_the_level_choice_bundles_read_back_each_step(self) -> None:
        wizard = WizardLevelChoices.model_validate(CHOICES["Wizard"])
        self.assertEqual(wizard.level_2.spellbook_spells, ["Thunderwave", "Feather Fall"])
        self.assertIsNotNone(wizard.level_3)
        self.assertIsNotNone(wizard.level_4)
        self.assertEqual(wizard.level_5.spellbook_spells, ["Fireball", "Counterspell"])
        cleric = ClericLevelChoices.model_validate(CHOICES["Cleric"])
        self.assertIsNotNone(cleric.level_2)
        self.assertIsNotNone(cleric.level_3)
        self.assertIsNotNone(cleric.level_4)
        self.assertIsNotNone(cleric.level_5)

    def test_every_new_model_refuses_a_key_it_does_not_know(self) -> None:
        for model in NEW_MODELS:
            with self.subTest(model=model.__name__):
                self.assertEqual(model.model_config.get("extra"), "forbid")
        with self.assertRaises(ValidationError):
            WizardStartingSpellbookOptions.model_validate(
                {"spellbook_spell_count": 2, "spellbook_spell_ids": [], "surprise": 1})


if __name__ == "__main__":
    unittest.main()
