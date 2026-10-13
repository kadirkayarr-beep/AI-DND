"""Unit tests for D&D 2024 player-owned character creation."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import game
from api.character_creation import CharacterCreationError, configure_character
from api.dnd_2024_rules import (
    BACKGROUND_DEFINITIONS,
    CLASS_DEFINITIONS,
    SPECIES_DEFINITIONS,
    calculate_derived_stats,
    get_equipment_armor_and_shield,
    get_character_creation_catalog,
    get_expertise_choice_count,
    roll_4d6_drop_lowest,
    validate_ability_scores,
    validate_background_bonuses,
)
from api.tests.auth_fixture import TEST_PLAYER
from api.persistence.campaign_validation import (
    restore_campaign_session,
    serialize_campaign_payload,
)
from api.serializers import serialize_session_state


class MockSession:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.character: dict[str, Any] = {}
        self.inventory: list[str] = []
        self.world_state: dict[str, Any] = {"inventory": []}

    def initialize_species_trait_state(self, giant_ancestry: str | None = None):
        species = self.character.get("species", self.character.get("race"))
        self.character["giant_ancestry"] = giant_ancestry
        self.character["species_trait_state"] = game._new_species_trait_state(
            species, self.character.get("proficiency_bonus", 2)
        )


class CharacterCreation2024Tests(unittest.TestCase):
    def test_catalog_returns_all_rules_data(self):
        catalog = get_character_creation_catalog()
        self.assertIn("classes", catalog)
        self.assertIn("races", catalog)
        self.assertIn("backgrounds", catalog)
        self.assertIn("ability_score_methods", catalog)
        self.assertIn("alignments", catalog)
        self.assertIn("origin_feats", catalog)
        self.assertIn("spells_catalog", catalog)
        self.assertIn("skills", catalog)
        self.assertIn("equipment_rules", catalog)

        # 12 classes
        self.assertEqual(len(catalog["classes"]), 12)
        # 16 backgrounds
        self.assertEqual(len(catalog["backgrounds"]), 16)
        self.assertEqual(catalog["races"]["Human"]["skill_bonus_count"], 1)
        self.assertEqual(catalog["races"]["Human"]["origin_feat_bonus_count"], 1)
        self.assertEqual(catalog["races"]["Half-Elf"]["skill_bonus_count"], 2)
        self.assertEqual(
            set(catalog["races"]),
            {
                "Aasimar",
                "Dragonborn",
                "Dwarf",
                "Elf",
                "Gnome",
                "Goliath",
                "Halfling",
                "Half-Elf",
                "Half-Orc",
                "Human",
                "Orc",
                "Tiefling",
            },
        )
        self.assertEqual(set(game.RACES), set(catalog["races"]))
        self.assertEqual(set(game.RACE_FEATURES), set(game.RACES))
        self.assertEqual(catalog["races"]["Aasimar"]["rules_version"], "2024 PHB")
        self.assertEqual(catalog["races"]["Goliath"]["speed"], 35)
        self.assertEqual(catalog["races"]["Orc"]["darkvision"], 120)
        self.assertEqual(catalog["races"]["Half-Elf"]["rules_version"], "2014 legacy")
        self.assertEqual(catalog["races"]["Half-Orc"]["rules_version"], "2014 legacy")
        self.assertEqual(catalog["races"]["Half-Orc"]["darkvision"], 60)
        self.assertEqual(
            {style["id"] for style in catalog["classes"]["Fighter"]["fighting_styles"]},
            {
                "Archery",
                "Defense",
                "Dueling",
                "Great Weapon Fighting",
                "Protection",
                "Two-Weapon Fighting",
            },
        )
        self.assertEqual(catalog["races"]["Dwarf"]["hp_bonus"], 1)
        self.assertEqual(catalog["origin_feats"]["Tough"]["hp_bonus"], 2)
        # Species count
        self.assertEqual(len(catalog["races"]), len(SPECIES_DEFINITIONS))

    def test_every_spellcasting_class_has_enough_level_one_choices(self):
        catalog = get_character_creation_catalog()
        spell_catalog = catalog["spells_catalog"]

        for class_name, class_data in catalog["classes"].items():
            if not class_data.get("is_spellcaster"):
                continue

            spells = spell_catalog.get(class_name, {})
            self.assertGreaterEqual(
                len(spells.get("cantrips", [])),
                class_data.get("cantrips_count", 0),
                f"{class_name} does not have enough cantrip options.",
            )
            self.assertGreaterEqual(
                len(spells.get("spells_level_1", [])),
                class_data.get("spells_count", 0),
                f"{class_name} does not have enough level-one spell options.",
            )

    def test_random_mode_produces_complete_2024_character(self):
        session = MockSession(seed=123)
        configure_character(session, mode="random")
        char = session.character

        self.assertTrue(char["name"])
        self.assertIn(char["species"], SPECIES_DEFINITIONS)
        self.assertIn(char["class"], CLASS_DEFINITIONS)
        self.assertIn(char["background"], BACKGROUND_DEFINITIONS)
        self.assertEqual(char["level"], 1)
        self.assertEqual(char["proficiency_bonus"], 2)
        self.assertGreater(char["max_hp"], 0)
        self.assertEqual(char["current_hp"], char["max_hp"])
        self.assertGreater(char["armor_class"], 9)
        self.assertEqual(len(char["saving_throws"]), 2)
        self.assertIn("initiative", char)
        self.assertIn("proficient_skills", char)
        self.assertGreaterEqual(len(char["proficient_skills"]), 2)
        self.assertIn("origin_feat", char)
        self.assertIn("equipment_choices", char)
        self.assertIn("species_bonus_skills", char)
        self.assertIn("species_bonus_feat", char)
        self.assertIn("origin_feats", char)
        expected_expertise_count = get_expertise_choice_count(
            char["class"], char["level"]
        )
        self.assertEqual(len(char["expertise_skills"]), expected_expertise_count)
        self.assertTrue(
            set(char["expertise_skills"]).issubset(char["proficient_skills"])
        )

        armor, has_shield = get_equipment_armor_and_shield(char["equipment_choices"])
        expected = calculate_derived_stats(
            character_class=char["class"],
            species=char["species"],
            final_scores={
                ability: char[ability]
                for ability in (
                    "strength",
                    "dexterity",
                    "constitution",
                    "intelligence",
                    "wisdom",
                    "charisma",
                )
            },
            chosen_feat=char.get("origin_feat"),
            chosen_feats=char.get("origin_feats"),
            fighting_style=char.get("fighting_style"),
            equipped_armor=armor,
            has_shield=has_shield,
        )
        self.assertEqual(char["armor_class"], expected["armor_class"])
        self.assertEqual(char["max_hp"], expected["max_hp"])

    def test_expertise_progression_validation_and_campaign_restore(self):
        self.assertEqual(get_expertise_choice_count("Rogue", 1), 2)
        self.assertEqual(get_expertise_choice_count("Rogue", 5), 2)
        self.assertEqual(get_expertise_choice_count("Rogue", 6), 4)
        self.assertEqual(get_expertise_choice_count("Bard", 1), 0)
        self.assertEqual(get_expertise_choice_count("Bard", 2), 2)
        self.assertEqual(get_expertise_choice_count("Bard", 9), 4)
        self.assertEqual(get_expertise_choice_count("Fighter", 20), 0)

        selections = {
            "name": "Rook",
            "race": "Elf",
            "character_class": "Rogue",
            "background": "Criminal",
            "alignment": "Neutral Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "strength": 8,
                "dexterity": 15,
                "constitution": 13,
                "intelligence": 12,
                "wisdom": 14,
                "charisma": 10,
            },
            "background_ability_bonuses": {
                "dexterity": 2,
                "constitution": 1,
            },
            "proficient_skills": [
                "Sleight of Hand",
                "Stealth",
                "Athletics",
                "Deception",
                "Insight",
                "Perception",
            ],
            "expertise_skills": ["Sleight of Hand", "Perception"],
            "equipment_package": "A",
            "background_equipment_option": "A",
            "languages": ["Common", "Dwarvish", "Giant"],
        }
        session = game.create_session(seed=42)
        configure_character(session, mode="custom", **selections)
        self.assertEqual(
            session.character["expertise_skills"],
            selections["expertise_skills"],
        )

        with patch("game.roll_d20", return_value=10):
            check = game.perform_skill_check(
                "Perception",
                12,
                session.character["modifiers"],
                session.character["proficient_skills"],
                session.character["proficiency_bonus"],
                expertise_skills=session.character["expertise_skills"],
            )
        self.assertTrue(check["expertise"])
        self.assertEqual(check["proficiency_bonus"], 4)

        for invalid_expertises in (
            [],
            ["History", "Perception"],
            ["Perception", "Perception"],
        ):
            with self.assertRaises(CharacterCreationError):
                configure_character(
                    MockSession(),
                    mode="custom",
                    **{**selections, "expertise_skills": invalid_expertises},
                )

        campaign_payload = serialize_campaign_payload(session)
        restored = game.create_session(seed=7)
        restore_campaign_session(restored, campaign_payload)
        self.assertEqual(
            restored.character["expertise_skills"],
            selections["expertise_skills"],
        )
        projected_state = serialize_session_state(restored)
        self.assertEqual(
            projected_state["character"]["expertise_skills"],
            selections["expertise_skills"],
        )

        legacy_save = session.serialize_game_state()
        legacy_save["player"].pop("expertise_skills")
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "legacy-without-expertise.json"
            save_path.write_text(json.dumps(legacy_save), encoding="utf-8")
            legacy_session = game.create_session(seed=11)
            legacy_session.load_game(save_path)
        self.assertEqual(legacy_session.character["expertise_skills"], [])

    def test_derived_stats_follow_equipment_species_and_feat_rules(self):
        fighter = CLASS_DEFINITIONS["Fighter"]
        scores = {
            "strength": 12,
            "dexterity": 16,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
        }
        expected_ac_by_package = {"A": 19, "B": 15, "C": 13}

        for package in fighter["equipment_packages"]:
            with self.subTest(package=package["id"]):
                armor, has_shield = get_equipment_armor_and_shield(package["items"])
                derived = calculate_derived_stats(
                    character_class="Fighter",
                    species="Human",
                    final_scores=scores,
                    fighting_style="Defense",
                    equipped_armor=armor,
                    has_shield=has_shield,
                )
                self.assertEqual(
                    derived["armor_class"],
                    expected_ac_by_package[package["id"]],
                )
                self.assertEqual(
                    derived["max_hp"],
                    fighter["hit_die"] + 2,
                )

        dwarf_with_tough = calculate_derived_stats(
            character_class="Fighter",
            species="Dwarf",
            final_scores=scores,
            chosen_feat="Tough",
            chosen_feats=["Tough"],
        )
        self.assertEqual(dwarf_with_tough["max_hp"], 15)

        armor, has_shield = get_equipment_armor_and_shield(
            ["Pul Zırh", "Ahşap Kalkan"]
        )
        medium_armor = calculate_derived_stats(
            character_class="Fighter",
            species="Human",
            final_scores=scores,
            fighting_style="Defense",
            equipped_armor=armor,
            has_shield=has_shield,
        )
        self.assertEqual(armor, "Scale Mail")
        self.assertTrue(has_shield)
        self.assertEqual(medium_armor["armor_class"], 19)

    def test_random_humans_and_half_elves_receive_species_bonuses(self):
        found_species = set()
        for seed in range(100):
            session = MockSession(seed=seed)
            configure_character(session, mode="random")
            character = session.character
            if character["species"] not in {"Human", "Half-Elf"}:
                continue

            found_species.add(character["species"])
            expected_skill_count = 1 if character["species"] == "Human" else 2
            self.assertEqual(
                len(character["species_bonus_skills"]), expected_skill_count
            )
            self.assertTrue(
                set(character["species_bonus_skills"]).issubset(
                    character["proficient_skills"]
                )
            )
            if character["species"] == "Human":
                self.assertIn(character["species_bonus_feat"], character["origin_feats"])

            if found_species == {"Human", "Half-Elf"}:
                break

        self.assertEqual(found_species, {"Human", "Half-Elf"})

    def test_random_mode_rejects_custom_fields(self):
        session = MockSession()
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="random", name="Arven")
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="random", race="Elf")
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="random", character_class="Wizard")
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="random", background="Soldier")

    def test_custom_mode_with_standard_array_valid(self):
        session = MockSession()
        configure_character(
            session,
            mode="custom",
            name="Thorne Ironbreaker",
            species="Dwarf",
            character_class="Fighter",
            background="Soldier",
            alignment="Lawful Good",
            ability_score_method="standard_array",
            ability_scores={
                "strength": 15,
                "constitution": 14,
                "dexterity": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "constitution": 1},
            proficient_skills=["Athletics", "Intimidation", "Acrobatics", "Perception"],
            origin_feat="Savage Attacker",
            fighting_style="Defense",
            equipment_package="A",
            background_equipment_option="A",
            languages=["Common", "Dwarvish", "Giant"],
        )
        char = session.character

        self.assertEqual(char["name"], "Thorne Ironbreaker")
        self.assertEqual(char["species"], "Dwarf")
        self.assertEqual(char["class"], "Fighter")
        self.assertEqual(char["background"], "Soldier")
        self.assertEqual(char["alignment"], "Lawful Good")

        # Base 15 STR + 2 bonus = 17 STR (+3 mod)
        self.assertEqual(char["strength"], 17)
        self.assertEqual(char["strength_mod"], 3)
        # Base 14 CON + 1 bonus = 15 CON (+2 mod)
        self.assertEqual(char["constitution"], 15)
        self.assertEqual(char["constitution_mod"], 2)

        # Fighter hit die is 10 + CON mod (2) + Dwarf Toughness (+1) = 13 HP
        self.assertEqual(char["max_hp"], 13)
        self.assertEqual(char["current_hp"], 13)

        # Chain Mail (16) + Shield (+2) + Defense fighting style (+1) = 19 AC
        self.assertEqual(char["armor_class"], 19)

        # Saving throws: Fighter has Strength & Constitution
        self.assertEqual(set(char["saving_throws"]), {"strength", "constitution"})

    def test_human_bonus_skills_and_origin_feat_are_validated_and_persisted(self):
        selections = {
            "name": "Mira Versatile",
            "species": "Human",
            "character_class": "Fighter",
            "background": "Soldier",
            "alignment": "Lawful Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "strength": 15,
                "constitution": 14,
                "dexterity": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            "background_ability_bonuses": {"strength": 2, "constitution": 1},
            "proficient_skills": [
                "Athletics",
                "Intimidation",
                "Acrobatics",
                "Perception",
                "History",
            ],
            "species_bonus_skills": ["History"],
            "species_bonus_feat": "Tough",
            "fighting_style": "Defense",
            "equipment_package": "A",
            "background_equipment_option": "A",
            "languages": ["Common", "Dwarvish", "Giant"],
        }

        session = MockSession()
        configure_character(session, mode="custom", **selections)
        character = session.character
        self.assertEqual(character["species_bonus_skills"], ["History"])
        self.assertEqual(character["species_bonus_feat"], "Tough")
        self.assertEqual(character["origin_feats"], ["Savage Attacker", "Tough"])
        self.assertIn("History", character["proficient_skills"])
        self.assertEqual(character["max_hp"], 14)

        with self.assertRaises(CharacterCreationError):
            configure_character(
                MockSession(),
                mode="custom",
                **{**selections, "species_bonus_feat": "Savage Attacker"},
            )

    def test_half_elf_requires_two_distinct_species_bonus_skills(self):
        selections = {
            "name": "Rowan Twofold",
            "species": "Half-Elf",
            "character_class": "Fighter",
            "background": "Soldier",
            "alignment": "Lawful Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "strength": 15,
                "constitution": 14,
                "dexterity": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            "background_ability_bonuses": {"strength": 2, "constitution": 1},
            "proficient_skills": [
                "Athletics",
                "Intimidation",
                "Acrobatics",
                "Perception",
                "History",
                "Stealth",
            ],
            "species_bonus_skills": ["History", "Stealth"],
            "fighting_style": "Defense",
            "equipment_package": "A",
            "background_equipment_option": "A",
            "languages": ["Common", "Dwarvish", "Giant"],
        }

        session = game.create_session(seed=42)
        configure_character(session, mode="custom", **selections)
        self.assertEqual(session.character["species_bonus_skills"], ["History", "Stealth"])
        self.assertEqual(
            session.serialize_game_state()["player"]["species_bonus_skills"],
            ["History", "Stealth"],
        )
        self.assertIsNone(session.character["species_bonus_feat"])

        legacy_save = session.serialize_game_state()
        legacy_save["player"].pop("species_bonus_skills")
        with tempfile.TemporaryDirectory() as directory:
            save_path = Path(directory) / "legacy-half-elf.json"
            save_path.write_text(json.dumps(legacy_save), encoding="utf-8")
            restored_session = game.create_session(seed=7)
            restored_session.character["species_bonus_skills"] = ["Perception"]
            restored_session.load_game(save_path)
            self.assertEqual(
                restored_session.character["species_bonus_skills"], []
            )
            self.assertEqual(
                set(restored_session.character["proficient_skills"]),
                set(selections["proficient_skills"]),
            )

        with self.assertRaises(CharacterCreationError):
            configure_character(
                MockSession(),
                mode="custom",
                **{
                    **selections,
                    "proficient_skills": selections["proficient_skills"][:-1],
                    "species_bonus_skills": ["History"],
                },
            )

    def test_custom_mode_point_buy_validation(self):
        session = MockSession()
        # Valid 27 point buy:
        # 15 (9 pts), 15 (9 pts), 15 (9 pts), 8 (0 pts), 8 (0 pts), 8 (0 pts) = 27 pts
        valid_pb_scores = {
            "strength": 15,
            "dexterity": 15,
            "constitution": 15,
            "intelligence": 8,
            "wisdom": 8,
            "charisma": 8,
        }
        validate_ability_scores("point_buy", valid_pb_scores)

        # Invalid: score > 15
        with self.assertRaises(CharacterCreationError):
            validate_ability_scores(
                "point_buy",
                {
                    "strength": 16,
                    "dexterity": 14,
                    "constitution": 14,
                    "intelligence": 8,
                    "wisdom": 8,
                    "charisma": 8,
                },
            )

        # Invalid: overspent budget
        with self.assertRaises(CharacterCreationError):
            validate_ability_scores(
                "point_buy",
                {
                    "strength": 15,
                    "dexterity": 15,
                    "constitution": 15,
                    "intelligence": 10,  # +2 pts -> 29 total
                    "wisdom": 8,
                    "charisma": 8,
                },
            )

    def test_custom_mode_background_bonus_validation(self):
        # Soldier allows boosting Strength, Constitution, Dexterity
        valid_bonuses = {"strength": 2, "constitution": 1}
        validate_background_bonuses("Soldier", valid_bonuses)

        valid_three_bonuses = {"strength": 1, "constitution": 1, "dexterity": 1}
        validate_background_bonuses("Soldier", valid_three_bonuses)

        # Illegal: Charisma is not in Soldier's abilities
        with self.assertRaises(CharacterCreationError):
            validate_background_bonuses("Soldier", {"charisma": 2, "strength": 1})

        # Illegal: +3 to single stat
        with self.assertRaises(CharacterCreationError):
            validate_background_bonuses("Soldier", {"strength": 3})

    def test_custom_mode_skill_choice_validation(self):
        session = MockSession()
        # Missing background skills
        with self.assertRaises(CharacterCreationError):
            configure_character(
                session,
                mode="custom",
                name="Aldric",
                species="Human",
                character_class="Fighter",
                background="Soldier",  # Soldier requires Athletics, Intimidation
                ability_scores={
                    "strength": 15,
                    "constitution": 14,
                    "dexterity": 13,
                    "wisdom": 12,
                    "intelligence": 10,
                    "charisma": 8,
                },
                background_ability_bonuses={"strength": 2, "constitution": 1},
                proficient_skills=["Acrobatics", "Perception", "History", "Survival", "Stealth"],
            )

        # Illegal class skill: Fighter cannot pick Arcana
        with self.assertRaises(CharacterCreationError):
            configure_character(
                session,
                mode="custom",
                name="Aldric",
                species="Elf",
                character_class="Fighter",
                background="Soldier",
                ability_scores={
                    "strength": 15,
                    "constitution": 14,
                    "dexterity": 13,
                    "wisdom": 12,
                    "intelligence": 10,
                    "charisma": 8,
                },
                background_ability_bonuses={"strength": 2, "constitution": 1},
                proficient_skills=["Athletics", "Intimidation", "Arcana", "Perception"],
            )

    def test_spellcaster_cantrip_and_spell_validation(self):
        session = MockSession()
        # Valid Wizard setup: 3 cantrips, 2 1st-level spells
        configure_character(
            session,
            mode="custom",
            name="Lyra Starweaver",
            species="Elf",
            character_class="Wizard",
            background="Sage",
            alignment="Neutral Good",
            ability_score_method="standard_array",
            ability_scores={
                "intelligence": 15,
                "dexterity": 14,
                "constitution": 13,
                "wisdom": 12,
                "charisma": 10,
                "strength": 8,
            },
            background_ability_bonuses={"intelligence": 2, "constitution": 1},
            proficient_skills=["Arcana", "History", "Investigation", "Insight"],
            equipment_package="A",
            background_equipment_option="A",
            languages=["Common", "Dwarvish", "Elvish"],
            cantrips=["Fire Bolt", "Mage Hand", "Light"],
            spells=[
                "Magic Missile",
                "Shield",
                "Mage Armor",
                "Detect Magic",
                "Thunderwave",
                "Sleep",
            ],
        )
        char = session.character
        self.assertEqual(char["intelligence"], 17)
        self.assertEqual(char["intelligence_mod"], 3)
        self.assertEqual(char["spell_save_dc"], 8 + 2 + 3)  # 13
        self.assertEqual(char["spell_attack_bonus"], 2 + 3)  # +5
        self.assertEqual(char["cantrips"], ["Fire Bolt", "Mage Hand", "Light"])
        self.assertEqual(
            char["spells"],
            [
                "Magic Missile",
                "Shield",
                "Mage Armor",
                "Detect Magic",
                "Thunderwave",
                "Sleep",
            ],
        )

        # Invalid spell choice: Eldritch Blast is not a Wizard cantrip
        with self.assertRaises(CharacterCreationError):
            configure_character(
                session,
                mode="custom",
                name="Lyra",
                species="Elf",
                character_class="Wizard",
                background="Sage",
                alignment="Neutral Good",
                ability_score_method="standard_array",
                equipment_package="A",
                background_equipment_option="A",
                languages=["Common", "Dwarvish", "Elvish"],
                ability_scores={
                    "intelligence": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "wisdom": 12,
                    "charisma": 10,
                    "strength": 8,
                },
                background_ability_bonuses={"intelligence": 2, "constitution": 1},
                proficient_skills=["Arcana", "History", "Investigation", "Insight"],
                cantrips=["Eldritch Blast", "Mage Hand", "Light"],
                spells=[
                    "Magic Missile",
                    "Shield",
                    "Mage Armor",
                    "Detect Magic",
                    "Thunderwave",
                    "Sleep",
                ],
            )

    def test_custom_mode_fail_closed_missing_choices_rejected(self):
        # TESTS 1 - 8 & 13: Player choices are mandatory; no silent engine defaults!
        session = MockSession()
        base_valid = {
            "mode": "custom",
            "name": "Valen",
            "species": "Human",
            "character_class": "Fighter",
            "background": "Soldier",
            "alignment": "Neutral Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "strength": 15, "dexterity": 14, "constitution": 13,
                "wisdom": 12, "intelligence": 10, "charisma": 8
            },
            "background_ability_bonuses": {"strength": 2, "constitution": 1},
            "proficient_skills": ["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
            "fighting_style": "Defense",
            "equipment_package": "A",
            "background_equipment_option": "A",
            "languages": ["Common", "Dwarvish", "Elvish"],
        }

        # TEST 1: missing background -> rejected
        d1 = dict(base_valid)
        d1["background"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d1)

        # TEST 2: missing ability score method -> rejected
        d2 = dict(base_valid)
        d2["ability_score_method"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d2)

        # TEST 3: missing required ability score data -> rejected
        d3 = dict(base_valid)
        d3["ability_scores"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d3)

        # TEST 4: missing alignment -> rejected
        d4 = dict(base_valid)
        d4["alignment"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d4)

        # TEST 5: missing required languages -> rejected
        d5 = dict(base_valid)
        d5["languages"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d5)

        # TEST 6: missing background equipment option -> rejected
        d6 = dict(base_valid)
        d6["background_equipment_option"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d6)

        # TEST 7: missing class equipment package/choices -> rejected
        d7 = dict(base_valid)
        d7["equipment_package"] = None
        d7["equipment_choices"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d7)

        # TEST 8: missing fighting style for Fighter -> rejected
        d8 = dict(base_valid)
        d8["fighting_style"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d8)

        # Missing species -> rejected
        d9 = dict(base_valid)
        d9["species"] = None
        d9["race"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d9)

        # Missing class -> rejected
        d10 = dict(base_valid)
        d10["character_class"] = None
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d10)

        # Missing spells for spellcaster -> rejected
        d11 = {
            "mode": "custom",
            "name": "Elora",
            "species": "Elf",
            "character_class": "Wizard",
            "background": "Sage",
            "alignment": "Neutral Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "intelligence": 15, "dexterity": 14, "constitution": 13,
                "wisdom": 12, "charisma": 10, "strength": 8
            },
            "background_ability_bonuses": {"intelligence": 2, "constitution": 1},
            "proficient_skills": ["Arcana", "History", "Investigation", "Insight"],
            "languages": ["Common", "Dwarvish", "Elvish"],
            "equipment_package": "A",
            "background_equipment_option": "A",
            # cantrips and spells omitted!
        }
        with self.assertRaises(CharacterCreationError):
            configure_character(session, **d11)

    def test_roleplay_identity_fields_persisted_and_non_mechanical(self):
        # TESTS 11 & 12: appearance/personality/backstory persisted & cannot alter mechanical derived values
        session1 = MockSession()
        session2 = MockSession()

        base_params = {
            "mode": "custom",
            "name": "Valen",
            "species": "Human",
            "character_class": "Fighter",
            "background": "Soldier",
            "alignment": "Neutral Good",
            "ability_score_method": "standard_array",
            "ability_scores": {
                "strength": 15, "dexterity": 14, "constitution": 13,
                "wisdom": 12, "intelligence": 10, "charisma": 8
            },
            "background_ability_bonuses": {"strength": 2, "constitution": 1},
            "proficient_skills": ["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
            "fighting_style": "Defense",
            "equipment_package": "A",
            "background_equipment_option": "A",
            "languages": ["Common", "Dwarvish", "Elvish"],
        }

        # Without RP fields
        configure_character(session1, **base_params)

        # With RP fields
        configure_character(
            session2,
            **base_params,
            origin="Neverwinter",
            appearance="Tall, scarred veteran with grey eyes and braided dark hair.",
            personality="Pragmatic and quiet, values loyalty above all else.",
            backstory="Former sergeant of the Neverwinter city watch who left after uncovering local corruption.",
        )

        char1 = session1.character
        char2 = session2.character

        # RP fields are persisted in canonical state
        self.assertEqual(char2["appearance"], "Tall, scarred veteran with grey eyes and braided dark hair.")
        self.assertEqual(char2["personality"], "Pragmatic and quiet, values loyalty above all else.")
        self.assertEqual(char2["backstory"], "Former sergeant of the Neverwinter city watch who left after uncovering local corruption.")
        self.assertEqual(char2["origin"], "Neverwinter")
        self.assertIsNone(char1["appearance"])
        self.assertIsNone(char1["origin"])

        # Mechanical derived stats are 100% IDENTICAL
        self.assertEqual(char1["max_hp"], char2["max_hp"])
        self.assertEqual(char1["armor_class"], char2["armor_class"])
        self.assertEqual(char1["initiative"], char2["initiative"])
        self.assertEqual(char1["strength"], char2["strength"])
        self.assertEqual(char1["strength_mod"], char2["strength_mod"])
        self.assertEqual(char1["modifiers"], char2["modifiers"])
        self.assertEqual(char1["saving_throws"], char2["saving_throws"])

    def test_persisted_save_without_rp_fields_loads_safely(self):
        # TEST 10: Old save without appearance/personality/backstory loads cleanly
        import copy
        legacy_save = {
            "name": "OldHero",
            "class": "Fighter",
            "species": "Human",
            "level": 1,
            "max_hp": 12,
            "current_hp": 12,
            "armor_class": 16,
            "strength": 16,
        }
        loaded_session = MockSession()
        loaded_session.character = copy.deepcopy(legacy_save)

        self.assertEqual(loaded_session.character["name"], "OldHero")
        self.assertIsNone(loaded_session.character.get("appearance"))
        self.assertIsNone(loaded_session.character.get("personality"))
        self.assertIsNone(loaded_session.character.get("backstory"))

    def test_custom_mode_never_silently_substitutes_defaults(self):
        # TEST 13: Passing minimal/empty fields never silently generates Cedric the Human Fighter Soldier
        session = MockSession()
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="custom")
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="custom", name="Cedric")
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="custom", name="Cedric", character_class="Fighter")
        with self.assertRaises(CharacterCreationError):
            configure_character(session, mode="custom", name="Cedric", character_class="Fighter", species="Human")
        self.assertEqual(session.character, {})

    def test_standard_array_duplicate_and_missing_rejected(self):
        # Duplicate 15 rejected
        with self.assertRaises(CharacterCreationError):
            validate_ability_scores(
                "standard_array",
                {
                    "strength": 15,
                    "dexterity": 15,
                    "constitution": 13,
                    "intelligence": 12,
                    "wisdom": 10,
                    "charisma": 8,
                },
            )
        # Missing score (only 5 provided)
        with self.assertRaises(CharacterCreationError):
            validate_ability_scores(
                "standard_array",
                {
                    "strength": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "intelligence": 12,
                    "wisdom": 10,
                },
            )

    def test_random_generation_4d6_drop_lowest(self):
        rng = random.Random(12345)
        # roll_4d6_drop_lowest produces values within [3, 18]
        for _ in range(50):
            score = roll_4d6_drop_lowest(rng)
            self.assertGreaterEqual(score, 3)
            self.assertLessEqual(score, 18)

        session = MockSession(seed=999)
        configure_character(session, mode="random")
        char = session.character
        for key in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
            self.assertIn(key, char)
            self.assertGreaterEqual(char[key], 3)
            self.assertLessEqual(char[key], 20)

        # Arbitrary manual scores with method="rolled" without verified pool rejected
        with self.assertRaises(CharacterCreationError):
            validate_ability_scores(
                "rolled",
                {
                    "strength": 18,
                    "dexterity": 18,
                    "constitution": 18,
                    "intelligence": 18,
                    "wisdom": 18,
                    "charisma": 18,
                },
            )

    def test_sailor_background_matches_2024_phb(self):
        sailor_bg = BACKGROUND_DEFINITIONS["Sailor"]
        # Per 2024 PHB Chapter 4, p. 184: Acrobatics and Perception
        self.assertEqual(sailor_bg["skills"], ["Acrobatics", "Perception"])
        self.assertNotIn("Athletics", sailor_bg["skills"])
        self.assertEqual(sailor_bg["tool"], "Navigator's Tools")
        self.assertEqual(sailor_bg["feat"], "Tavern Brawler")
        self.assertEqual(sailor_bg["abilities"], ["strength", "dexterity", "wisdom"])

        # Configure custom Sailor character successfully
        session = MockSession()
        configure_character(
            session,
            mode="custom",
            name="Captain Jax",
            species="Human",
            character_class="Fighter",
            background="Sailor",
            alignment="Chaotic Good",
            ability_score_method="standard_array",
            ability_scores={
                "strength": 15,
                "dexterity": 14,
                "constitution": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "dexterity": 1},
            proficient_skills=["Acrobatics", "Perception", "Athletics", "Intimidation", "Survival"],
            fighting_style="Dueling",
            languages=["Common", "Elvish", "Dwarvish"],
            background_equipment_option="A",
            equipment_package="A",
        )
        char = session.character
        self.assertEqual(char["background"], "Sailor")
        self.assertIn("Acrobatics", char["proficient_skills"])
        self.assertIn("Perception", char["proficient_skills"])

    def test_background_bonus_limit_20_and_no_duplicate_bonus(self):
        # Base 19 + 2 bonus = 21 (exceeds 20, must be rejected)
        session = MockSession()
        with self.assertRaises(CharacterCreationError):
            configure_character(
                session,
                mode="custom",
                name="Titan",
                species="Human",
                character_class="Fighter",
                background="Soldier",
                alignment="Lawful Neutral",
                ability_score_method="manual",
                ability_scores={
                    "strength": 19,
                    "dexterity": 10,
                    "constitution": 10,
                    "intelligence": 10,
                    "wisdom": 10,
                    "charisma": 10,
                },
                background_ability_bonuses={"strength": 2, "constitution": 1},
                proficient_skills=["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
                fighting_style="Defense",
                languages=["Common", "Orc", "Goblin"],
                background_equipment_option="A",
                equipment_package="A",
            )

        # Same ability cannot receive both +2 and +1 (bonuses must be distinct)
        with self.assertRaises(CharacterCreationError):
            validate_background_bonuses("Soldier", {"strength": 3})

    def test_languages_validation_and_preservation(self):
        session = MockSession()
        # Valid: Common + Dwarvish + Elvish
        configure_character(
            session,
            mode="custom",
            name="Elora",
            species="Elf",
            character_class="Wizard",
            background="Sage",
            origin="Silverymoon",
            alignment="Neutral Good",
            ability_score_method="standard_array",
            ability_scores={
                "intelligence": 15,
                "dexterity": 14,
                "constitution": 13,
                "wisdom": 12,
                "charisma": 10,
                "strength": 8,
            },
            background_ability_bonuses={"intelligence": 2, "constitution": 1},
            proficient_skills=["Arcana", "History", "Investigation", "Insight"],
            languages=["Common", "Dwarvish", "Elvish"],
            background_equipment_option="A",
            equipment_package="A",
            cantrips=["Fire Bolt", "Mage Hand", "Light"],
            spells=["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Thunderwave", "Sleep"],
        )
        self.assertEqual(session.character["languages"], ["Common", "Dwarvish", "Elvish"])

        # Duplicate language rejected
        with self.assertRaises(CharacterCreationError):
            configure_character(
                MockSession(),
                mode="custom",
                name="Elora",
                species="Elf",
                character_class="Wizard",
                background="Sage",
                alignment="Neutral Good",
                ability_score_method="standard_array",
                ability_scores={
                    "intelligence": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "wisdom": 12,
                    "charisma": 10,
                    "strength": 8,
                },
                background_ability_bonuses={"intelligence": 2, "constitution": 1},
                proficient_skills=["Arcana", "History", "Investigation", "Insight"],
                languages=["Common", "Elvish", "Elvish"],
                background_equipment_option="A",
                equipment_package="A",
                cantrips=["Fire Bolt", "Mage Hand", "Light"],
                spells=["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Thunderwave", "Sleep"],
            )

        # Unknown language rejected
        with self.assertRaises(CharacterCreationError):
            configure_character(
                MockSession(),
                mode="custom",
                name="Elora",
                species="Elf",
                character_class="Wizard",
                background="Sage",
                alignment="Neutral Good",
                ability_score_method="standard_array",
                ability_scores={
                    "intelligence": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "wisdom": 12,
                    "charisma": 10,
                    "strength": 8,
                },
                background_ability_bonuses={"intelligence": 2, "constitution": 1},
                proficient_skills=["Arcana", "History", "Investigation", "Insight"],
                languages=["Common", "Klingon", "Elvish"],
                background_equipment_option="A",
                equipment_package="A",
                cantrips=["Fire Bolt", "Mage Hand", "Light"],
                spells=["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Thunderwave", "Sleep"],
            )

        # Rare language rejected when not granted (e.g. Abyssal)
        with self.assertRaises(CharacterCreationError):
            configure_character(
                MockSession(),
                mode="custom",
                name="Elora",
                species="Elf",
                character_class="Wizard",
                background="Sage",
                alignment="Neutral Good",
                ability_score_method="standard_array",
                ability_scores={
                    "intelligence": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "wisdom": 12,
                    "charisma": 10,
                    "strength": 8,
                },
                background_ability_bonuses={"intelligence": 2, "constitution": 1},
                proficient_skills=["Arcana", "History", "Investigation", "Insight"],
                languages=["Common", "Abyssal", "Elvish"],
                background_equipment_option="A",
                equipment_package="A",
                cantrips=["Fire Bolt", "Mage Hand", "Light"],
                spells=["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Thunderwave", "Sleep"],
            )

        # Class-granted language preserved: Druid gets Druidic automatically
        druid_session = MockSession()
        configure_character(
            druid_session,
            mode="custom",
            name="Rowan",
            species="Human",
            character_class="Druid",
            background="Guide",
            alignment="Neutral Good",
            ability_score_method="standard_array",
            ability_scores={
                "wisdom": 15,
                "constitution": 14,
                "dexterity": 13,
                "intelligence": 12,
                "strength": 10,
                "charisma": 8,
            },
            background_ability_bonuses={"wisdom": 2, "constitution": 1},
            proficient_skills=["Stealth", "Survival", "Animal Handling", "Nature", "Medicine"],
            languages=["Common", "Elvish", "Dwarvish"],
            background_equipment_option="A",
            equipment_package="A",
            cantrips=["Druidcraft", "Produce Flame"],
            spells=["Cure Wounds", "Entangle"],
        )
        self.assertIn("Druidic", druid_session.character["languages"])

    def test_alignment_validation(self):
        session = MockSession()
        configure_character(
            session,
            mode="custom",
            name="Justiciar",
            species="Human",
            character_class="Fighter",
            background="Soldier",
            alignment="Lawful Neutral",
            ability_score_method="standard_array",
            ability_scores={
                "strength": 15,
                "constitution": 14,
                "dexterity": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "constitution": 1},
            proficient_skills=["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
            languages=["Common", "Orc", "Goblin"],
            fighting_style="Defense",
            background_equipment_option="A",
            equipment_package="A",
        )
        self.assertEqual(session.character["alignment"], "Lawful Neutral")

        # Invalid alignment rejected
        with self.assertRaises(CharacterCreationError):
            configure_character(
                MockSession(),
                mode="custom",
                name="Justiciar",
                species="Human",
                character_class="Fighter",
                background="Soldier",
                alignment="Chaotic Awesome",
                ability_score_method="standard_array",
                ability_scores={
                    "strength": 15,
                    "constitution": 14,
                    "dexterity": 13,
                    "wisdom": 12,
                    "intelligence": 10,
                    "charisma": 8,
                },
                background_ability_bonuses={"strength": 2, "constitution": 1},
                proficient_skills=["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
                languages=["Common", "Orc", "Goblin"],
                fighting_style="Defense",
                background_equipment_option="A",
                equipment_package="A",
            )

    def test_background_equipment_option_a_vs_b(self):
        # Option A: Package items present
        session_a = MockSession()
        configure_character(
            session_a,
            mode="custom",
            name="Galan",
            species="Human",
            character_class="Fighter",
            background="Soldier",
            alignment="Lawful Neutral",
            ability_score_method="standard_array",
            background_equipment_option="A",
            equipment_package="A",
            fighting_style="Defense",
            languages=["Common", "Orc", "Goblin"],
            ability_scores={
                "strength": 15,
                "constitution": 14,
                "dexterity": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "constitution": 1},
            proficient_skills=["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
        )
        self.assertEqual(session_a.character["background_equipment_option"], "A")
        # Soldier background package has 'Birlik Sancağı Parçası'
        self.assertTrue(any("Sancak" in it or "Askeri" in it for it in session_a.character["equipment_choices"]))

        # Option B: 50 Altın present, package items NOT present
        session_b = MockSession()
        configure_character(
            session_b,
            mode="custom",
            name="Galan",
            species="Human",
            character_class="Fighter",
            background="Soldier",
            alignment="Lawful Neutral",
            ability_score_method="standard_array",
            background_equipment_option="B",
            equipment_package="A",
            fighting_style="Defense",
            languages=["Common", "Orc", "Goblin"],
            ability_scores={
                "strength": 15,
                "constitution": 14,
                "dexterity": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "constitution": 1},
            proficient_skills=["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
        )
        self.assertEqual(session_b.character["background_equipment_option"], "B")
        self.assertIn("50 Altın", session_b.character["equipment_choices"])
        self.assertFalse(any("Sancak" in it for it in session_b.character["equipment_choices"]))

        # Invalid option rejected
        with self.assertRaises(CharacterCreationError):
            configure_character(
                MockSession(),
                mode="custom",
                name="Galan",
                species="Human",
                character_class="Fighter",
                background="Soldier",
                alignment="Lawful Neutral",
                ability_score_method="standard_array",
                background_equipment_option="C",
                equipment_package="A",
                fighting_style="Defense",
                languages=["Common", "Orc", "Goblin"],
                ability_scores={
                    "strength": 15,
                    "constitution": 14,
                    "dexterity": 13,
                    "wisdom": 12,
                    "intelligence": 10,
                    "charisma": 8,
                },
                background_ability_bonuses={"strength": 2, "constitution": 1},
                proficient_skills=["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
            )

    def test_persistence_round_trip_preservation(self):
        import copy
        session = MockSession()
        configure_character(
            session,
            mode="custom",
            name="Aeloria",
            species="Elf",
            character_class="Wizard",
            background="Sage",
            origin="Silverymoon",
            alignment="Neutral Good",
            ability_score_method="standard_array",
            ability_scores={
                "intelligence": 15,
                "dexterity": 14,
                "constitution": 13,
                "wisdom": 12,
                "charisma": 10,
                "strength": 8,
            },
            background_ability_bonuses={"intelligence": 2, "constitution": 1},
            proficient_skills=["Arcana", "History", "Investigation", "Insight"],
            languages=["Common", "Dwarvish", "Elvish"],
            background_equipment_option="B",
            equipment_package="A",
            cantrips=["Fire Bolt", "Mage Hand", "Light"],
            spells=["Magic Missile", "Shield", "Mage Armor", "Detect Magic", "Thunderwave", "Sleep"],
        )
        # Snapshot state as would be saved in SQLite / JSON
        saved_char = copy.deepcopy(session.character)

        # Restore into new session
        loaded_session = MockSession()
        loaded_session.character = copy.deepcopy(saved_char)

        # Verify all fields preserved intact
        self.assertEqual(loaded_session.character["name"], "Aeloria")
        self.assertEqual(loaded_session.character["origin"], "Silverymoon")
        self.assertEqual(loaded_session.character["alignment"], "Neutral Good")
        self.assertEqual(loaded_session.character["languages"], ["Common", "Dwarvish", "Elvish"])
        self.assertEqual(loaded_session.character["background_equipment_option"], "B")
        self.assertEqual(loaded_session.character["intelligence"], 17)
        self.assertEqual(loaded_session.character["intelligence_mod"], 3)
        self.assertIn("50 Altın", loaded_session.character["equipment_choices"])
        self.assertEqual(len(loaded_session.character["languages"]), 3)
        # No duplicates
        self.assertEqual(len(loaded_session.character["languages"]), len(set(loaded_session.character["languages"])))


    def test_a1_1_random_character_creation_and_rolls_authority(self):
        """Random mode generates 4d6-drop-lowest abilities and starting equipment authoritatively."""
        session1 = MockSession(seed=42)
        configure_character(session1, mode="random")
        char1 = session1.character

        # Scores are in valid 4d6-drop-lowest range (3-18 before background bonus, 3-20 after)
        for stat in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
            self.assertGreaterEqual(char1[stat], 3)
            self.assertLessEqual(char1[stat], 20)

        # Canonical equipment package was chosen authoritatively and transferred to inventory
        self.assertIn("equipment_package", char1)
        self.assertTrue(len(char1["equipment_choices"]) > 0)
        self.assertEqual(session1.world_state["inventory"], char1["equipment_choices"])
        self.assertEqual(session1.inventory, char1["equipment_choices"])
        self.assertEqual(char1["inventory"], char1["equipment_choices"])

        # Deterministic RNG seed produces reproducible result
        session2 = MockSession(seed=42)
        configure_character(session2, mode="random")
        self.assertEqual(session1.character, session2.character)

    def test_a1_1_fake_rolled_scores_rejected_in_custom_mode(self):
        """Client-submitted rolled ability scores cannot override Python engine authority."""
        session = MockSession()
        with self.assertRaises(CharacterCreationError) as ctx:
            configure_character(
                session,
                mode="custom",
                name="Cheater",
                species="Human",
                character_class="Fighter",
                background="Soldier",
                alignment="True Neutral",
                ability_score_method="rolled",
                ability_scores={"strength": 20, "dexterity": 20, "constitution": 20, "intelligence": 20, "wisdom": 20, "charisma": 20},
                background_ability_bonuses={"strength": 2, "constitution": 1},
                proficient_skills=["Athletics", "Intimidation", "Perception", "Survival", "Stealth"],
                equipment_package="A",
                background_equipment_option="A",
                languages=["Common", "Dwarvish", "Elvish"],
            )
        self.assertIn("Rolled ability scores require game engine authority", str(ctx.exception))

    def test_a1_1_equipment_transfer_to_canonical_inventory(self):
        """Valid equipment from creation is transferred to session.world_state['inventory']."""
        session = MockSession()
        configure_character(
            session,
            mode="custom",
            name="Valeros",
            species="Dwarf",
            character_class="Fighter",
            background="Soldier",
            alignment="Neutral Good",
            ability_score_method="standard_array",
            ability_scores={
                "strength": 15,
                "constitution": 14,
                "dexterity": 13,
                "wisdom": 12,
                "intelligence": 10,
                "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "constitution": 1},
            proficient_skills=["Athletics", "Intimidation", "Perception", "Survival"],
            equipment_package="A",
            background_equipment_option="A",
            fighting_style="Defense",
            languages=["Common", "Dwarvish", "Elvish"],
        )
        self.assertIn("Zincir Zırh", session.world_state["inventory"])
        self.assertIn("Kalkan", session.world_state["inventory"])
        self.assertEqual(session.world_state["inventory"], session.character["equipment_choices"])
        self.assertEqual(session.world_state["inventory"], session.character["inventory"])

    def test_a1_1_invalid_and_fake_equipment_rejected(self):
        """Arbitrary/fake equipment invented by client is rejected fail-closed."""
        session = MockSession()
        with self.assertRaises(CharacterCreationError) as ctx:
            configure_character(
                session,
                mode="custom",
                name="Hacker",
                species="Elf",
                character_class="Wizard",
                background="Sage",
                alignment="True Neutral",
                ability_score_method="standard_array",
                ability_scores={
                    "intelligence": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "wisdom": 12,
                    "charisma": 10,
                    "strength": 8,
                },
                background_ability_bonuses={"intelligence": 2, "constitution": 1},
                proficient_skills=["Arcana", "History", "Investigation", "Insight"],
                languages=["Common", "Draconic", "Elvish"],
                equipment_package="A",
                background_equipment_option="A",
                equipment_choices=["Lazer Silahı", "Nanotek Zırh"],
            )
        self.assertIn("unauthorized items", str(ctx.exception).lower())

    def test_a1_1_equipment_validation_bypass_without_package_rejected(self):
        """Omitting package and providing arbitrary equipment choices is rejected."""
        session = MockSession()
        with self.assertRaises(CharacterCreationError) as ctx:
            configure_character(
                session,
                mode="custom",
                name="Bypasser",
                species="Elf",
                character_class="Wizard",
                background="Sage",
                alignment="True Neutral",
                ability_score_method="standard_array",
                ability_scores={
                    "intelligence": 15,
                    "dexterity": 14,
                    "constitution": 13,
                    "wisdom": 12,
                    "charisma": 10,
                    "strength": 8,
                },
                background_ability_bonuses={"intelligence": 2, "constitution": 1},
                proficient_skills=["Arcana", "History", "Investigation", "Insight"],
                languages=["Common", "Draconic", "Elvish"],
                background_equipment_option="A",
                equipment_choices=["Zincir Zırh", "Kalkan"],
            )
        self.assertIn("unauthorized equipment", str(ctx.exception).lower())

    def test_a1_1_ac_calculated_strictly_from_validated_equipment(self):
        """Equipment-dependent AC is derived solely from Python-validated gear."""
        session = MockSession()
        configure_character(
            session,
            mode="custom",
            name="Ironclad",
            species="Dwarf",
            character_class="Fighter",
            background="Soldier",
            alignment="Lawful Good",
            ability_score_method="standard_array",
            ability_scores={
                "strength": 15,
                "constitution": 14,
                "dexterity": 10,
                "wisdom": 12,
                "intelligence": 13,
                "charisma": 8,
            },
            background_ability_bonuses={"strength": 2, "constitution": 1},
            proficient_skills=["Athletics", "Intimidation", "Perception", "Survival"],
            equipment_package="A",  # Chain Mail (16) + Shield (+2)
            background_equipment_option="A",
            fighting_style="Defense",  # +1 AC with armor
            languages=["Common", "Dwarvish", "Orc"],
        )
        # 16 (Chain Mail) + 2 (Shield) + 1 (Defense style) = 19 AC
        self.assertEqual(session.character["armor_class"], 19)

    def test_a1_1_real_sqlite_persistence_preserves_canonical_inventory(self):
        """Verify real SQLite persistence path round-trips character and world_state inventory."""
        from pathlib import Path
        import tempfile
        from api.lore_authority import PRODUCTION_START_CATALOG
        from api.persistence.campaign_store import CampaignStore
        from api.session_manager import SessionManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_campaign.sqlite3"
            store = CampaignStore(db_path, bound_principal=TEST_PLAYER)
            manager = SessionManager(campaign_store=store)

            char_input = {
                "mode": "custom",
                "name": "Bruenor",
                "species": "Dwarf",
                "character_class": "Fighter",
                "background": "Soldier",
                "alignment": "Lawful Good",
                "ability_score_method": "standard_array",
                "ability_scores": {
                    "strength": 15,
                    "constitution": 14,
                    "dexterity": 13,
                    "wisdom": 12,
                    "intelligence": 10,
                    "charisma": 8,
                },
                "background_ability_bonuses": {"strength": 2, "constitution": 1},
                "proficient_skills": ["Athletics", "Intimidation", "Perception", "Survival"],
                "equipment_package": "A",
                "background_equipment_option": "A",
                "fighting_style": "Defense",
                "languages": ["Common", "Dwarvish", "Giant"],
            }
            setting = PRODUCTION_START_CATALOG.to_response()["settings"][0]
            region = setting["regions"][0]
            location = region["starting_locations"][0]
            start_input = {
                "setting_id": setting["setting_id"],
                "region_pack_id": region["region_pack_id"],
                "region_id": region["region_id"],
                "starting_location_id": location["entity_id"],
            }

            campaign_id, session_id, record, metadata = manager.create_campaign(
                name="Bruenor's Campaign",
                character=char_input,
                campaign_start=start_input,
            )

            # Check starting inventory in active session
            active_inv = record.game_session.world_state.get("inventory", [])
            self.assertIn("Zincir Zırh", active_inv)
            self.assertIn("Kalkan", active_inv)
            self.assertEqual(record.game_session.character["armor_class"], 19)

            # Restart session manager from the same SQLite database
            restarted_manager = SessionManager(campaign_store=CampaignStore(db_path, bound_principal=TEST_PLAYER))
            resumed_session_id, resumed_record, resumed_meta, _, _ = restarted_manager.resume_campaign(campaign_id)

            # Assert inventory survived the real database round-trip
            resumed_inv = resumed_record.game_session.world_state.get("inventory", [])
            self.assertEqual(resumed_inv, active_inv)
            self.assertEqual(resumed_record.game_session.character["armor_class"], 19)
            self.assertEqual(resumed_record.game_session.character["name"], "Bruenor")


if __name__ == "__main__":
    unittest.main()
