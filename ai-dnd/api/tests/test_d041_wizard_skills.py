"""D-041: the Wizard creation skill list is the PHB 2024 list (PDF 164), Nature included.

Values only: Arcana, History, Insight, Investigation, Medicine, Nature, Religion (choose 2).
The three copies of the list (rules catalog, legacy engine table, offline UI fallback) must agree.
"""
import re
import unittest
from pathlib import Path

import game
from api.character_creation import configure_character
from api.dnd_2024_rules import CLASS_DEFINITIONS, get_character_creation_catalog
from api.tests.test_character_creation_2024 import MockSession

REPO = Path(__file__).resolve().parents[3]
FALLBACK = REPO / "artifacts" / "ai-dnd-experience" / "src" / "lib" / "character-catalog-defaults.ts"
PHB_WIZARD = ["Arcana", "History", "Insight", "Investigation", "Medicine", "Nature", "Religion"]


class WizardSkillList(unittest.TestCase):
    def test_rules_catalog_and_engine_table_carry_the_source_list(self):
        self.assertEqual(CLASS_DEFINITIONS["Wizard"]["skill_options"], PHB_WIZARD)
        self.assertEqual(get_character_creation_catalog()["classes"]["Wizard"]["skill_options"], PHB_WIZARD)
        self.assertEqual(game.CLASS_SKILL_OPTIONS["Wizard"], PHB_WIZARD)
        self.assertEqual(CLASS_DEFINITIONS["Wizard"]["skill_count"], 2)

    def test_offline_ui_fallback_carries_the_source_list(self):
        source = FALLBACK.read_text(encoding="utf-8")
        block = source[source.index("    Wizard: {"):]
        match = re.search(r"skill_options: \[([^\]]*)\]", block)
        self.assertIsNotNone(match)
        self.assertEqual(re.findall(r"'([^']+)'", match.group(1)), PHB_WIZARD)

    def test_custom_wizard_may_pick_nature(self):
        session = MockSession()
        configure_character(
            session,
            mode="custom",
            name="Lyra",
            species="Elf",
            character_class="Wizard",
            background="Sage",
            alignment="Neutral Good",
            ability_score_method="standard_array",
            ability_scores={"intelligence": 15, "dexterity": 14, "constitution": 13,
                            "wisdom": 12, "charisma": 10, "strength": 8},
            background_ability_bonuses={"intelligence": 2, "constitution": 1},
            proficient_skills=["Arcana", "History", "Investigation", "Nature"],
            equipment_package="A",
            background_equipment_option="A",
            languages=["Common", "Dwarvish", "Elvish"],
            cantrips=["Fire Bolt", "Mage Hand", "Light"],
            spells=["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Thunderwave", "Sleep"],
        )
        self.assertIn("Nature", session.character["proficient_skills"])


if __name__ == "__main__":
    unittest.main()
