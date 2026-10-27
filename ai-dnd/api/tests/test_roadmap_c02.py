"""C02: species and backgrounds match the PHB 2024 oracle; legacy options are kept; a bonus comes from ONE source.

The oracle (`content/rules/phb2024/origins.json`) holds values and page numbers read from the book, never book text. The
resolver (`api/dnd_2024_rules.py`) must agree with it for every manifest entry (10 species + 16 backgrounds). Half-Elf and
Half-Orc are deliberate 2014 options kept beside the 2024 entries; their source is not in the local approved scope, so their
VALUES are not asserted (oracle_status BLOCKED_SOURCE_NOT_LOCAL), only that they stay selectable, saved, and add no second bonus.
Not covered here (owners recorded in HANDOFF): lineage/ancestry choices, trait use, level progression, size/tool choice persistence.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import game
from api.character_creation import configure_character
from api.dnd_2024_rules import BACKGROUND_DEFINITIONS, SPECIES_DEFINITIONS, get_character_creation_catalog
from api.persistence.campaign_validation import restore_campaign_session, serialize_campaign_payload

ROOT = Path(__file__).resolve().parents[3]
ORACLE = json.loads((ROOT / "content" / "rules" / "phb2024" / "origins.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / "content" / "manifest" / "phb2024.json").read_text(encoding="utf-8"))
C02_ROWS = [r for r in MANIFEST["rows"] if r["proposed_owner"] == "C02"]
LEGACY = ("Half-Elf", "Half-Orc")
BASE = {"strength": 8, "dexterity": 15, "constitution": 13, "intelligence": 12, "wisdom": 14, "charisma": 10}


def printed_pages(citation):
    return [int(n) for n in re.findall(r"pp?\.\s*(\d+)", citation)]


def selections(species, background="Criminal"):
    chosen = {
        "name": "Rook", "race": species, "species": species, "character_class": "Rogue", "background": background,
        "alignment": "Neutral Good", "ability_score_method": "standard_array", "ability_scores": dict(BASE),
        "background_ability_bonuses": {"dexterity": 2, "constitution": 1},
        "proficient_skills": ["Sleight of Hand", "Stealth", "Athletics", "Deception", "Insight", "Perception"],
        "expertise_skills": ["Sleight of Hand", "Perception"], "equipment_package": "A", "background_equipment_option": "A",
        "languages": ["Common", "Dwarvish", "Giant"],
    }
    return chosen


def species_extras(species):
    """What the creation rules additionally require for a species with bonus skills or a bonus Origin feat."""
    definition = SPECIES_DEFINITIONS[species]
    extra = {}
    count = definition.get("skill_bonus_count", 0)
    if count:
        bonus = ["Arcana", "History"][:count]
        extra["species_bonus_skills"] = bonus
        extra["proficient_skills"] = [*selections(species)["proficient_skills"], *bonus]
    if definition.get("origin_feat_bonus_count"):
        extra["species_bonus_feat"] = "Tough"
    if definition.get("giant_ancestry_options"):
        extra["giant_ancestry"] = definition["giant_ancestry_options"][0]["id"]
    return extra


class OriginOracleTests(unittest.TestCase):
    def test_manifest_oracle_and_resolver_name_the_same_entries(self):
        manifest_species = {r["name"] for r in C02_ROWS if r["category"] == "species"}
        manifest_backgrounds = {r["name"] for r in C02_ROWS if r["category"] == "background"}
        self.assertEqual((len(manifest_species), len(manifest_backgrounds)), (10, 16))
        self.assertEqual(manifest_species, set(ORACLE["species"]))
        self.assertEqual(manifest_backgrounds, set(ORACLE["backgrounds"]))
        self.assertTrue(manifest_species <= set(SPECIES_DEFINITIONS))
        self.assertTrue(manifest_backgrounds <= set(BACKGROUND_DEFINITIONS))
        self.assertEqual(set(SPECIES_DEFINITIONS) - manifest_species, set(LEGACY), "only the two legacy options are extra")
        self.assertEqual(set(BACKGROUND_DEFINITIONS), manifest_backgrounds)

    def test_background_values_match_the_book(self):
        for name, expected in ORACLE["backgrounds"].items():
            actual = BACKGROUND_DEFINITIONS[name]
            self.assertEqual(set(actual["abilities"]), set(expected["abilities"]), f"{name} abilities")
            self.assertEqual(set(actual["skills"]), set(expected["skills"]), f"{name} skills")
            self.assertEqual(actual["feat"], expected["feat"], f"{name} feat")
            self.assertEqual(actual.get("feat_variant"), expected["feat_variant"], f"{name} feat list")
            self.assertEqual(actual.get("tool_choice"), expected["tool_choice"], f"{name} tool is chosen from a category")
            if expected["tool"]:
                self.assertEqual(actual["tool"], expected["tool"], f"{name} tool")
            else:
                self.assertTrue(actual.get("tool_options") or actual.get("tool_choice"), f"{name} offers a choice")

    def test_species_values_match_the_book(self):
        for name, expected in ORACLE["species"].items():
            actual = SPECIES_DEFINITIONS[name]
            self.assertEqual(actual["size_options"], expected["size"], f"{name} size (a chosen size is a list)")
            self.assertEqual(actual["speed"], expected["speed"], f"{name} speed")
            self.assertEqual(actual["darkvision"], expected["darkvision"], f"{name} darkvision")
            self.assertIn(actual["size"].split(" ")[0], expected["size"], f"{name} default size is an allowed one")

    def test_pages_agree_between_manifest_oracle_and_resolver_citations(self):
        for row in C02_ROWS:
            expected_pdf = ORACLE["species" if row["category"] == "species" else "backgrounds"][row["name"]]["pdf_page"]
            self.assertEqual(row["source"]["pdf_page"], expected_pdf, row["name"])
            self.assertEqual(row["source"]["printed_page"], expected_pdf + 1, row["name"])
            if row["category"] == "species":
                self.assertEqual(printed_pages(SPECIES_DEFINITIONS[row["name"]]["source_citation"])[0],
                                 row["source"]["printed_page"], f"{row['name']} citation page")

    def test_the_catalog_shows_every_entry_with_the_checked_values(self):
        catalog = get_character_creation_catalog()
        self.assertTrue(set(ORACLE["species"]) | set(LEGACY) <= set(catalog["races"]))
        self.assertEqual(set(ORACLE["backgrounds"]), set(catalog["backgrounds"]))


class SingleBonusSourceTests(unittest.TestCase):
    def test_legacy_origin_has_single_bonus_source(self):
        for species in SPECIES_DEFINITIONS:
            session = game.create_session(seed=42)
            definition = SPECIES_DEFINITIONS[species]
            extra = species_extras(species)
            configure_character(session, mode="custom", **{**selections(species), **extra})
            expected = {k: BASE[k] + {"dexterity": 2, "constitution": 1}.get(k, 0) for k in BASE}
            actual = {k: session.character[k] for k in BASE}
            obs = {
                "final_scores": actual,
                "expected_scores": expected,
                "species_ability_bonus_keys": sorted(k for k in definition if ("ability" in k or any(a in k for a in BASE))
                                                 and ("bonus" in k or "increase" in k)),
            }
            assert obs["final_scores"] == obs["expected_scores"], species
            assert obs["species_ability_bonus_keys"] == [], f"{species} must not carry its own ability bonus"

    def test_random_creation_also_has_one_bonus_source(self):
        for seed in range(1, 9):
            session = game.create_session(seed=seed)
            configure_character(session, mode="random")
            character = session.character
            final = {k: character["base_ability_scores"][k] + character["background_ability_bonuses"].get(k, 0) for k in BASE}
            self.assertEqual({k: character[k] for k in BASE}, final, f"seed {seed}: only the background adds to the scores")
            species = SPECIES_DEFINITIONS[character["species"]]
            self.assertEqual([k for k in species if k.endswith("_bonus") and any(a in k for a in BASE)], [])

    def test_a_background_bonus_cannot_be_added_twice_or_beyond_the_rule(self):
        from api.dnd_2024_rules import CharacterCreationError, validate_background_bonuses
        with self.assertRaises(CharacterCreationError):
            validate_background_bonuses("Criminal", {"dexterity": 2, "constitution": 2})  # +2/+2 is not allowed
        with self.assertRaises(CharacterCreationError):
            validate_background_bonuses("Criminal", {"strength": 2, "dexterity": 1})  # strength is not a Criminal ability
        with self.assertRaises(CharacterCreationError):
            validate_background_bonuses("Criminal", {"dexterity": 2, "constitution": 1}, {"dexterity": 19})  # would exceed 20
        validate_background_bonuses("Criminal", {"dexterity": 1, "constitution": 1, "intelligence": 1})

    def test_every_species_including_legacy_is_created_and_saved_and_loaded(self):
        for species in SPECIES_DEFINITIONS:
            session = game.create_session(seed=42)
            extra = species_extras(species)
            configure_character(session, mode="custom", **{**selections(species), **extra})
            self.assertEqual(session.character["species"], species)
            payload = serialize_campaign_payload(session)
            restored = game.create_session(seed=7)
            restore_campaign_session(restored, payload)
            self.assertEqual(restored.character["species"], species, f"{species} survives save and load")
            self.assertEqual({k: restored.character[k] for k in BASE}, {k: session.character[k] for k in BASE})

    def test_every_background_is_created_with_its_checked_feat_and_saved(self):
        for name, expected in ORACLE["backgrounds"].items():
            session = game.create_session(seed=42)
            abilities = expected["abilities"]
            bonuses = {abilities[0]: 2, abilities[1]: 1}
            rogue = ["Acrobatics", "Athletics", "Deception", "Insight", "Intimidation", "Investigation", "Perception",
                     "Persuasion", "Sleight of Hand", "Stealth"]
            class_skills = [skill for skill in rogue if skill not in expected["skills"]][:4]
            chosen = {**selections("Elf", name), "background_ability_bonuses": bonuses,
                      "proficient_skills": [*expected["skills"], *class_skills],
                      "expertise_skills": list(expected["skills"])}
            try:
                configure_character(session, mode="custom", **chosen)
            except Exception as error:  # a background that cannot be created is a real finding
                self.fail(f"{name} could not be created: {error}")
            self.assertEqual(session.character["background"], name)
            self.assertEqual(session.character["origin_feat"], expected["feat"], name)
            restored = game.create_session(seed=7)
            restore_campaign_session(restored, serialize_campaign_payload(session))
            self.assertEqual(restored.character["background"], name)

    def test_origin_choices_are_saved_loaded_cleared_and_validated(self):
        import copy
        session = game.create_session(seed=42)
        configure_character(session, mode="custom", **selections("Elf"))
        payload = serialize_campaign_payload(session)
        saved = payload["engine_save"]["player"]["origin_choices"]
        self.assertEqual(saved["background"], "Criminal")
        self.assertEqual(saved["background_ability_bonuses"], {"dexterity": 2, "constitution": 1})
        self.assertEqual(saved["base_ability_scores"], BASE)
        self.assertTrue({"Common", "Dwarvish", "Giant"} <= set(saved["languages"]), "chosen languages are kept (creation may add more)")
        # a session that already holds ANOTHER character's choices: loading replaces them, nothing leaks
        other = game.create_session(seed=3)
        configure_character(other, mode="custom", **selections("Dwarf", "Charlatan"))
        other.character["equipment_choices"] = ["stale item"]
        restore_campaign_session(other, copy.deepcopy(payload))
        self.assertEqual(other.character["background"], "Criminal")
        self.assertEqual(other.character["base_ability_scores"], BASE)
        self.assertNotIn("stale item", other.character.get("equipment_choices", []))
        # an old save without the block still loads and leaves no origin keys behind
        old = copy.deepcopy(payload)
        del old["engine_save"]["player"]["origin_choices"]
        restored_old = game.create_session(seed=5)
        configure_character(restored_old, mode="custom", **selections("Gnome", "Charlatan"))
        restore_campaign_session(restored_old, old)
        self.assertNotIn("background", restored_old.character)
        self.assertNotIn("base_ability_scores", restored_old.character)
        # a character without creation choices saves exactly as before (no block)
        plain = game.create_session(seed=9)
        self.assertNotIn("origin_choices", serialize_campaign_payload(plain)["engine_save"]["player"])
        # shapes and semantics that must be refused on load
        for label, change in {
            "text too long": {"background": "x" * 61},
            "unknown background": {"background": "Nonexistent"},
            "absurd bonus": {"background_ability_bonuses": {"strength": 30, "dexterity": 1}},
            "negative bonus": {"background_ability_bonuses": {"strength": -1}},
            "+2/+2": {"background_ability_bonuses": {"dexterity": 2, "constitution": 2}},
            "unknown key": {"surprise": 1},
            "unknown ability": {"base_ability_scores": {"luck": 5}},
            "languages not a list": {"languages": "Common"},
        }.items():
            broken = copy.deepcopy(payload)
            broken["engine_save"]["player"]["origin_choices"].update(change)
            with self.assertRaises(Exception, msg=label):
                restore_campaign_session(game.create_session(seed=1), broken)

    def test_legacy_options_stay_and_their_values_are_not_asserted_from_memory(self):
        for name in LEGACY:
            self.assertIn(name, SPECIES_DEFINITIONS, "a working legacy option is never deleted")
            self.assertEqual(SPECIES_DEFINITIONS[name]["rules_version"], "2014 legacy")
            self.assertEqual(ORACLE["legacy"][name]["oracle_status"], "BLOCKED_SOURCE_NOT_LOCAL")
            self.assertNotIn(name, ORACLE["species"])


if __name__ == "__main__":
    unittest.main()
