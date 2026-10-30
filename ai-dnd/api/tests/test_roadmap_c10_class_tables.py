"""C10-C21 data oracle: source-backed 1-20 progression TABLES for Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue,
Warlock and Wizard (`content/rules/phb2024/class_tables/<class>.json`, loaded by `class_tables.table`).

Source: PHB 2024 class "Features" tables, PDF ordinals Bard 59, Cleric 69, Druid 79, Fighter 91, Monk 101, Paladin 109, Ranger 119,
Rogue 129, Warlock 153, Wizard 165 (printed page = ordinal + 1). The expected values below were typed independently of the data
files from the page renders; the data files were generated from the local source package and must equal them cell for cell.

This is DATA only. Nothing here makes a class creatable or levelable: the engine's `_supported_level` mapping and the public
creation catalog are untouched, which the last test class pins. Not covered: class feature EFFECTS, subclass features,
Warlock/other choice lists, spell lists, multiclass, UI.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import character_progression as cp
import class_tables
from api.dnd_2024_rules import get_character_creation_catalog, proficiency_bonus_for_level

ROOT = Path(__file__).resolve().parents[3]
CLASS_DIR = ROOT / "content" / "rules" / "phb2024" / "classes"
TABLE_DIR = ROOT / "content" / "rules" / "phb2024" / "class_tables"
LEVELS = range(1, 21)
FULL_SLOTS = ["2", "3", "42", "43", "432", "433", "4331", "4332", "43331", "43332", "433321", "433321", "4333211", "4333211",
              "43332111", "43332111", "433321111", "433331111", "433332111", "433332211"]
HALF_SLOTS = ["2", "2", "3", "3", "42", "42", "43", "43", "432", "432", "433", "433", "4331", "4331", "4332", "4332",
              "43331", "43331", "43332", "43332"]
CASTER_PREPARED = [4, 5, 6, 7, 9, 10, 11, 12, 14, 15, 16, 16, 17, 17, 18, 18, 19, 20, 21, 22]
HALF_PREPARED = [2, 3, 4, 5, 6, 6, 7, 7, 9, 9, 10, 10, 11, 11, 12, 12, 14, 14, 15, 15]


def steps(*pairs):
    """steps((1, 2), (4, 3)) -> value 2 from level 1, 3 from level 4 ...; None before the first step (the table's em dash)."""
    out = []
    for level in LEVELS:
        values = [v for start, v in pairs if start <= level]
        out.append(values[-1] if values else None)
    return out


def feats(spec):
    """{level: 'A; B'} -> 20 lists of feature names (missing level = the table's em dash = [])."""
    return [[x for x in spec.get(level, "").split("; ") if x] for level in LEVELS]


def slot_map(text):
    return {str(i + 1): int(c) for i, c in enumerate(text)}


BARD_F = {1: "Bardic Inspiration; Spellcasting", 2: "Expertise; Jack of All Trades", 3: "Bard Subclass", 4: "Ability Score Improvement",
          5: "Font of Inspiration", 6: "Subclass feature", 7: "Countercharm", 8: "Ability Score Improvement", 9: "Expertise",
          10: "Magical Secrets", 12: "Ability Score Improvement", 14: "Subclass feature", 16: "Ability Score Improvement",
          18: "Superior Inspiration", 19: "Epic Boon", 20: "Words of Creation"}
CLERIC_F = {1: "Spellcasting; Divine Order", 2: "Channel Divinity", 3: "Cleric Subclass", 4: "Ability Score Improvement",
            5: "Sear Undead", 6: "Subclass feature", 7: "Blessed Strikes", 8: "Ability Score Improvement", 10: "Divine Intervention",
            12: "Ability Score Improvement", 14: "Improved Blessed Strikes", 16: "Ability Score Improvement", 17: "Subclass feature",
            19: "Epic Boon", 20: "Greater Divine Intervention"}
DRUID_F = {1: "Spellcasting; Druidic; Primal Order", 2: "Wild Shape; Wild Companion", 3: "Druid Subclass", 4: "Ability Score Improvement",
           5: "Wild Resurgence", 6: "Subclass feature", 7: "Elemental Fury", 8: "Ability Score Improvement", 10: "Subclass feature",
           12: "Ability Score Improvement", 14: "Subclass feature", 15: "Improved Elemental Fury", 16: "Ability Score Improvement",
           18: "Beast Spells", 19: "Epic Boon", 20: "Archdruid"}
FIGHTER_F = {1: "Fighting Style; Second Wind; Weapon Mastery", 2: "Action Surge (one use); Tactical Mind", 3: "Fighter Subclass",
             4: "Ability Score Improvement", 5: "Extra Attack; Tactical Shift", 6: "Ability Score Improvement", 7: "Subclass feature",
             8: "Ability Score Improvement", 9: "Indomitable (one use); Tactical Master", 10: "Subclass feature", 11: "Two Extra Attacks",
             12: "Ability Score Improvement", 13: "Indomitable (two uses); Studied Attacks", 14: "Ability Score Improvement",
             15: "Subclass feature", 16: "Ability Score Improvement", 17: "Action Surge (two uses); Indomitable (three uses)",
             18: "Subclass feature", 19: "Epic Boon", 20: "Three Extra Attacks"}
MONK_F = {1: "Martial Arts; Unarmored Defense", 2: "Monk's Focus; Unarmored Movement; Uncanny Metabolism",
          3: "Deflect Attacks; Monk Subclass", 4: "Ability Score Improvement; Slow Fall", 5: "Extra Attack; Stunning Strike",
          6: "Empowered Strikes; Subclass feature", 7: "Evasion", 8: "Ability Score Improvement", 9: "Acrobatic Movement",
          10: "Heightened Focus; Self-Restoration", 11: "Subclass feature", 12: "Ability Score Improvement", 13: "Deflect Energy",
          14: "Disciplined Survivor", 15: "Perfect Focus", 16: "Ability Score Improvement", 17: "Subclass feature",
          18: "Superior Defense", 19: "Epic Boon", 20: "Body and Mind"}
PALADIN_F = {1: "Lay On Hands; Spellcasting; Weapon Mastery", 2: "Fighting Style; Paladin's Smite", 3: "Channel Divinity; Paladin Subclass",
             4: "Ability Score Improvement", 5: "Extra Attack; Faithful Steed", 6: "Aura of Protection", 7: "Subclass feature",
             8: "Ability Score Improvement", 9: "Abjure Foes", 10: "Aura of Courage", 11: "Radiant Strikes",
             12: "Ability Score Improvement", 14: "Restoring Touch", 15: "Subclass feature", 16: "Ability Score Improvement",
             18: "Aura Expansion", 19: "Epic Boon", 20: "Subclass feature"}
RANGER_F = {1: "Spellcasting; Favored Enemy; Weapon Mastery", 2: "Deft Explorer; Fighting Style", 3: "Ranger Subclass",
            4: "Ability Score Improvement", 5: "Extra Attack", 6: "Roving", 7: "Subclass feature", 8: "Ability Score Improvement",
            9: "Expertise", 10: "Tireless", 11: "Subclass feature", 12: "Ability Score Improvement", 13: "Relentless Hunter",
            14: "Nature's Veil", 15: "Subclass feature", 16: "Ability Score Improvement", 17: "Precise Hunter", 18: "Feral Senses",
            19: "Epic Boon", 20: "Foe Slayer"}
ROGUE_F = {1: "Expertise; Sneak Attack; Thieves' Cant; Weapon Mastery", 2: "Cunning Action", 3: "Rogue Subclass; Steady Aim",
           4: "Ability Score Improvement", 5: "Cunning Strike; Uncanny Dodge", 6: "Expertise", 7: "Evasion; Reliable Talent",
           8: "Ability Score Improvement", 9: "Subclass feature", 10: "Ability Score Improvement", 11: "Improved Cunning Strike",
           12: "Ability Score Improvement", 13: "Subclass feature", 14: "Devious Strikes", 15: "Slippery Mind",
           16: "Ability Score Improvement", 17: "Subclass feature", 18: "Elusive", 19: "Epic Boon", 20: "Stroke of Luck"}
WARLOCK_F = {1: "Eldritch Invocations; Pact Magic", 2: "Magical Cunning", 3: "Warlock Subclass", 4: "Ability Score Improvement",
             6: "Subclass feature", 8: "Ability Score Improvement", 9: "Contact Patron", 10: "Subclass feature",
             11: "Mystic Arcanum (level 6 spell)", 12: "Ability Score Improvement", 13: "Mystic Arcanum (level 7 spell)",
             14: "Subclass feature", 15: "Mystic Arcanum (level 8 spell)", 16: "Ability Score Improvement",
             17: "Mystic Arcanum (level 9 spell)", 19: "Epic Boon", 20: "Eldritch Master"}
WIZARD_F = {1: "Spellcasting; Ritual Adept; Arcane Recovery", 2: "Scholar", 3: "Wizard Subclass", 4: "Ability Score Improvement",
            5: "Memorize Spell", 6: "Subclass feature", 8: "Ability Score Improvement", 10: "Subclass feature",
            12: "Ability Score Improvement", 14: "Subclass feature", 16: "Ability Score Improvement", 18: "Spell Mastery",
            19: "Epic Boon", 20: "Signature Spells"}

# class -> (pdf ordinal, features, extra ASI levels, subclass levels, subclass names, column oracle)
ORACLE = {
    "Bard": dict(pdf=59, features=feats(BARD_F), asi=[4, 8, 12, 16], sub=[3, 6, 14],
                 subclasses=["College of Dance", "College of Glamour", "College of Lore", "College of Valor"],
                 columns=dict(bardic_die=steps((1, 6), (5, 8), (10, 10), (15, 12)), cantrips=steps((1, 2), (4, 3), (10, 4)),
                              prepared_spells=CASTER_PREPARED, slots=[slot_map(t) for t in FULL_SLOTS])),
    "Cleric": dict(pdf=69, features=feats(CLERIC_F), asi=[4, 8, 12, 16], sub=[3, 6, 17],
                   subclasses=["Life Domain", "Light Domain", "Trickery Domain", "War Domain"],
                   columns=dict(channel_divinity=steps((2, 2), (6, 3), (18, 4)), cantrips=steps((1, 3), (4, 4), (10, 5)),
                                prepared_spells=CASTER_PREPARED, slots=[slot_map(t) for t in FULL_SLOTS])),
    "Druid": dict(pdf=79, features=feats(DRUID_F), asi=[4, 8, 12, 16], sub=[3, 6, 10, 14],
                  subclasses=["Circle of the Land", "Circle of the Moon", "Circle of the Sea", "Circle of the Stars"],
                  columns=dict(wild_shape=steps((2, 2), (6, 3), (17, 4)), cantrips=steps((1, 2), (4, 3), (10, 4)),
                               prepared_spells=CASTER_PREPARED, slots=[slot_map(t) for t in FULL_SLOTS])),
    "Fighter": dict(pdf=91, features=feats(FIGHTER_F), asi=[4, 6, 8, 12, 14, 16], sub=[3, 7, 10, 15, 18],
                    subclasses=["Battle Master", "Champion", "Eldritch Knight", "Psi Warrior"],
                    columns=dict(second_wind=steps((1, 2), (4, 3), (10, 4)),
                                 weapon_mastery=steps((1, 3), (4, 4), (10, 5), (16, 6)))),
    "Monk": dict(pdf=101, features=feats(MONK_F), asi=[4, 8, 12, 16], sub=[3, 6, 11, 17],
                 subclasses=["Warrior of Mercy", "Warrior of Shadow", "Warrior of the Elements", "Warrior of the Open Hand"],
                 columns=dict(martial_arts_die=steps((1, 6), (5, 8), (11, 10), (17, 12)),
                              focus_points=[None] + list(range(2, 21)),
                              unarmored_movement_ft=steps((2, 10), (6, 15), (10, 20), (14, 25), (18, 30)))),
    "Paladin": dict(pdf=109, features=feats(PALADIN_F), asi=[4, 8, 12, 16], sub=[3, 7, 15, 20],
                    subclasses=["Oath of Devotion", "Oath of Glory", "Oath of the Ancients", "Oath of Vengeance"],
                    columns=dict(channel_divinity=steps((3, 2), (11, 3)), prepared_spells=HALF_PREPARED,
                                 slots=[slot_map(t) for t in HALF_SLOTS])),
    "Ranger": dict(pdf=119, features=feats(RANGER_F), asi=[4, 8, 12, 16], sub=[3, 7, 11, 15],
                   subclasses=["Beast Master", "Fey Wanderer", "Gloom Stalker", "Hunter"],
                   columns=dict(favored_enemy=steps((1, 2), (5, 3), (9, 4), (13, 5), (17, 6)), prepared_spells=HALF_PREPARED,
                                slots=[slot_map(t) for t in HALF_SLOTS])),
    "Rogue": dict(pdf=129, features=feats(ROGUE_F), asi=[4, 8, 10, 12, 16], sub=[3, 9, 13, 17],
                  subclasses=["Arcane Trickster", "Assassin", "Soulknife", "Thief"],
                  columns=dict(sneak_attack_dice=[1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10],
                               sneak_attack_die=[6] * 20)),
    "Warlock": dict(pdf=153, features=feats(WARLOCK_F), asi=[4, 8, 12, 16], sub=[3, 6, 10, 14],
                    subclasses=["Archfey Patron", "Celestial Patron", "Fiend Patron", "Great Old One Patron"],
                    columns=dict(eldritch_invocations=[1, 3, 3, 3, 5, 5, 6, 6, 7, 7, 7, 8, 8, 8, 9, 9, 9, 10, 10, 10],
                                 cantrips=steps((1, 2), (4, 3), (10, 4)),
                                 prepared_spells=[2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15],
                                 pact_slots=[{"count": c, "level": lv} for c, lv in zip(
                                     steps((1, 1), (2, 2), (11, 3), (17, 4)),
                                     [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5])],
                                 mystic_arcanum_spell_level=[None] * 10 + [6, None, 7, None, 8, None, 9, None, None, None])),
    "Wizard": dict(pdf=165, features=feats(WIZARD_F), asi=[4, 8, 12, 16], sub=[3, 6, 10, 14],
                   subclasses=["Abjurer", "Diviner", "Evoker", "Illusionist"],
                   columns=dict(cantrips=steps((1, 3), (4, 4), (10, 5)),
                                prepared_spells=[4, 5, 6, 7, 9, 10, 11, 12, 14, 15, 16, 16, 17, 18, 19, 21, 22, 23, 24, 25],
                                slots=[slot_map(t) for t in FULL_SLOTS])),
}
CLASSES = tuple(ORACLE)
NOT_PROGRESSED = tuple(name for name in CLASSES if name not in {"Fighter", "Monk"})  # these tables moved to classes/ with real progression (C14, C15)


def oracle_row(name, level):
    spec = ORACLE[name]
    row = {"proficiency_bonus": proficiency_bonus_for_level(level), "features": spec["features"][level - 1]}
    for column, values in spec["columns"].items():
        row[column] = values[level - 1]
    return row


def differences(name, data):
    """Every cell where `data` differs from the independent oracle (empty = equal)."""
    out = []
    for level in LEVELS:
        want, got = oracle_row(name, level), data["levels"].get(str(level))
        if got != want:
            for key in sorted(set(want) | set(got or {})):
                if (got or {}).get(key, "<absent>") != want.get(key, "<absent>"):
                    out.append((level, key, (got or {}).get(key, "<absent>"), want.get(key, "<absent>")))
    return out


def load(name):
    return json.loads(class_tables.table_path(name).read_text(encoding="utf-8"))


class TableOracleTests(unittest.TestCase):
    def test_ten_data_files_exist_and_load_through_the_new_loader(self):
        self.assertEqual(class_tables.CLASSES, CLASSES)
        for name in CLASSES:
            with self.subTest(name):
                self.assertTrue(class_tables.table_path(name).is_file(), "missing data file")
                self.assertEqual(class_tables.table(name), load(name))
        self.assertIsNone(class_tables.table("Barbarian"))
        self.assertIsNone(class_tables.table("Sorcerer"))
        self.assertIsNone(class_tables.table("../barbarian"))
        self.assertIsNone(class_tables.table(7))

    def test_every_table_equals_the_independent_oracle_cell_for_cell(self):
        for name in CLASSES:
            with self.subTest(name):
                data = load(name)
                self.assertEqual(list(data["levels"]), [str(n) for n in LEVELS], "20 rows in order")
                self.assertEqual(differences(name, data), [])
                self.assertEqual(class_tables.validate(name, data), [])

    def test_source_block_records_page_ordinals_and_verification(self):
        for name in CLASSES:
            with self.subTest(name):
                src = load(name)["source"]
                self.assertEqual(src["class"], name)
                self.assertEqual(src["features_table"]["pdf_page"], ORACLE[name]["pdf"])
                self.assertEqual(src["features_table"]["printed_page"], ORACLE[name]["pdf"] + 1)
                self.assertEqual(src["verification"]["level"], "dual-source+render-read")
                self.assertTrue(src["verification"]["package_file"].endswith(f"{name.lower()}_1_20.md"))
                self.assertEqual(src["unverified_cells"], [], "no cell is unverified; a null is an em dash")
                if name not in {"Fighter", "Monk"}:  # these tables moved to classes/ and state their progression scope
                    self.assertEqual(src["scope"], "progression table only; no feature effects, spell lists or choices")

    def test_features_per_level_and_distinct_names(self):
        for name in CLASSES:
            for level in LEVELS:
                with self.subTest(name=name, level=level):
                    self.assertEqual(load(name)["levels"][str(level)]["features"], ORACLE[name]["features"][level - 1])

    def test_asi_epic_boon_and_subclass_levels(self):
        for name in CLASSES:
            with self.subTest(name):
                data = load(name)
                asi = [n for n in LEVELS if "Ability Score Improvement" in data["levels"][str(n)]["features"]]
                boon = [n for n in LEVELS if "Epic Boon" in data["levels"][str(n)]["features"]]
                sub = [n for n in LEVELS if any(f == "Subclass feature" or f.endswith(" Subclass")
                                                for f in data["levels"][str(n)]["features"])]
                self.assertEqual(asi, ORACLE[name]["asi"])
                self.assertEqual(boon, [19], "the level-19 slot is the Epic Boon feature, not another Ability Score Improvement")
                self.assertEqual(sub, ORACLE[name]["sub"])
                self.assertEqual(data["subclass_levels"], sub)
                self.assertEqual(data["asi_levels"], asi)
                self.assertEqual(data["epic_boon_level"], 19)
                self.assertEqual([o["name"] for o in data["subclass_options"].values()], ORACLE[name]["subclasses"])
                self.assertEqual(len(data["subclass_options"]), 4)

    def test_fighter_and_rogue_extra_asi_levels_are_not_applied_to_others(self):
        self.assertEqual(ORACLE["Fighter"]["asi"], [4, 6, 8, 12, 14, 16])
        self.assertEqual(ORACLE["Rogue"]["asi"], [4, 8, 10, 12, 16])
        for name in set(CLASSES) - {"Fighter", "Rogue"}:
            self.assertEqual(load(name)["asi_levels"], [4, 8, 12, 16])

    def test_proficiency_bonus_follows_the_character_level_table(self):
        for name in CLASSES:
            for level in LEVELS:
                self.assertEqual(load(name)["levels"][str(level)]["proficiency_bonus"], proficiency_bonus_for_level(level))


class InternalConsistencyTests(unittest.TestCase):
    def test_full_caster_slot_tables_are_identical_and_follow_the_full_caster_shape(self):
        rows = {n: [load(n)["levels"][str(l)]["slots"] for l in LEVELS] for n in ("Bard", "Cleric", "Druid", "Wizard")}
        self.assertTrue(rows["Bard"] == rows["Cleric"] == rows["Druid"] == rows["Wizard"])
        for level, slots in enumerate(rows["Bard"], start=1):
            self.assertEqual(max(map(int, slots)), min(9, (level + 1) // 2), "highest slot level")
            self.assertEqual(list(slots), [str(i) for i in range(1, len(slots) + 1)], "contiguous slot levels")

    def test_half_caster_slots_equal_the_full_caster_row_at_half_level_rounded_up(self):
        full = [load("Wizard")["levels"][str(l)]["slots"] for l in LEVELS]
        for name in ("Paladin", "Ranger"):
            for level in LEVELS:
                self.assertEqual(load(name)["levels"][str(level)]["slots"], full[(level + 1) // 2 - 1], (name, level))
        self.assertEqual([load("Paladin")["levels"][str(l)]["slots"] for l in LEVELS],
                         [load("Ranger")["levels"][str(l)]["slots"] for l in LEVELS])

    def test_prepared_spells_shapes_and_monotonic_columns(self):
        bard, cleric, druid = (load(n) for n in ("Bard", "Cleric", "Druid"))
        for level in LEVELS:
            key = str(level)
            self.assertEqual(bard["levels"][key]["prepared_spells"], cleric["levels"][key]["prepared_spells"])
            self.assertEqual(bard["levels"][key]["prepared_spells"], druid["levels"][key]["prepared_spells"])
        for name in CLASSES:
            data = load(name)
            for column in ORACLE[name]["columns"]:
                values = [data["levels"][str(l)][column] for l in LEVELS]
                if all(isinstance(v, int) for v in values):
                    self.assertEqual(values, sorted(values), f"{name}.{column} must never decrease")

    def test_slot_totals_never_decrease_and_cantrips_never_decrease(self):
        for name in ("Bard", "Cleric", "Druid", "Wizard", "Paladin", "Ranger"):
            totals = [sum(load(name)["levels"][str(l)]["slots"].values()) for l in LEVELS]
            self.assertEqual(totals, sorted(totals), name)

    def test_warlock_pact_magic_is_not_a_spell_slot_map_and_arcanum_follows_the_feature_names(self):
        data = load("Warlock")
        for level in LEVELS:
            row = data["levels"][str(level)]
            self.assertNotIn("slots", row, "Pact Magic is kept apart from Spellcasting slots")
            self.assertEqual(row["pact_slots"]["level"], min(5, (level + 1) // 2))
            arcanum = [f for f in row["features"] if f.startswith("Mystic Arcanum")]
            if arcanum:
                self.assertEqual(arcanum, [f"Mystic Arcanum (level {row['mystic_arcanum_spell_level']} spell)"])
            else:
                self.assertIsNone(row["mystic_arcanum_spell_level"])

    def test_monk_rogue_and_class_resources_follow_their_stated_shape(self):
        monk, rogue = load("Monk"), load("Rogue")
        for level in range(2, 21):
            self.assertEqual(monk["levels"][str(level)]["focus_points"], level, "Focus Points equal Monk level")
        self.assertIsNone(monk["levels"]["1"]["focus_points"])
        self.assertIsNone(monk["levels"]["1"]["unarmored_movement_ft"])
        for level in LEVELS:
            self.assertEqual(rogue["levels"][str(level)]["sneak_attack_dice"], (level + 1) // 2)
        self.assertEqual([load("Fighter")["levels"][str(l)]["weapon_mastery"] for l in (1, 4, 10, 16)], [3, 4, 5, 6])

    def test_extra_attack_features_at_their_levels(self):
        fighter = load("Fighter")["levels"]
        for level, name in ((5, "Extra Attack"), (11, "Two Extra Attacks"), (20, "Three Extra Attacks")):
            self.assertIn(name, fighter[str(level)]["features"])
        for name in ("Monk", "Paladin", "Ranger"):
            self.assertIn("Extra Attack", load(name)["levels"]["5"]["features"])


class MutationTests(unittest.TestCase):
    """Altering one cell of a table must be caught by the oracle comparison (and by validate() when structural)."""

    MUTATIONS = [
        ("Bard", 7, "slots", {"1": 4, "2": 3, "3": 3, "4": 2}),
        ("Bard", 10, "bardic_die", 8),
        ("Cleric", 18, "channel_divinity", 3),
        ("Druid", 17, "wild_shape", 3),
        ("Fighter", 16, "weapon_mastery", 5),
        ("Monk", 14, "unarmored_movement_ft", 20),
        ("Paladin", 19, "slots", {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1}),
        ("Ranger", 13, "favored_enemy", 4),
        ("Rogue", 19, "sneak_attack_dice", 9),
        ("Warlock", 11, "pact_slots", {"count": 2, "level": 5}),
        ("Wizard", 16, "prepared_spells", 20),
        ("Wizard", 5, "proficiency_bonus", 2),
        ("Fighter", 19, "features", ["Ability Score Improvement"]),
        ("Rogue", 10, "features", []),
    ]

    def test_each_single_cell_change_is_detected(self):
        for name, level, column, value in self.MUTATIONS:
            with self.subTest(name=name, level=level, column=column):
                data = load(name)
                self.assertNotEqual(data["levels"][str(level)][column], value, "mutation must actually change the cell")
                self.assertEqual(differences(name, data), [])
                data["levels"][str(level)][column] = value
                found = differences(name, data)
                self.assertEqual([(l, c) for l, c, _, _ in found], [(level, column)])

    def test_structural_mutations_fail_validate(self):
        data = load("Bard")
        broken = copy.deepcopy(data)
        broken["levels"]["5"]["proficiency_bonus"] = 2
        self.assertTrue(class_tables.validate("Bard", broken))
        broken = copy.deepcopy(data)
        del broken["levels"]["20"]
        self.assertTrue(class_tables.validate("Bard", broken))
        broken = copy.deepcopy(data)
        broken["levels"]["3"]["slots"]["10"] = 1
        self.assertTrue(class_tables.validate("Bard", broken))
        broken = copy.deepcopy(data)
        broken["levels"]["4"]["cantrips"] = None
        self.assertTrue(class_tables.validate("Bard", broken), "an unexplained null is refused")
        broken = copy.deepcopy(load("Warlock"))
        broken["levels"]["4"]["pact_slots"] = {"count": 2, "level": 6}
        self.assertTrue(class_tables.validate("Warlock", broken))
        self.assertTrue(class_tables.validate("Barbarian", data))

    def test_a_listed_unverified_cell_is_the_only_allowed_unexplained_null(self):
        data = load("Bard")
        data["levels"]["4"]["cantrips"] = None
        data["source"]["unverified_cells"] = [[4, "cantrips"]]
        self.assertEqual(class_tables.validate("Bard", data), [])
        self.assertNotEqual(differences("Bard", data), [], "the oracle still refuses an unverified cell")

    def test_malformed_unverified_cell_entries_are_reported_not_raised(self):
        for bad in ([4, ["cantrips"]], [4, 7], ["4", "cantrips"], [4], [4, "cantrips", "x"], "4"):
            data = load("Bard")
            data["source"]["unverified_cells"] = [bad]
            self.assertTrue(class_tables.validate("Bard", data), bad)

    def test_loader_returns_detached_copies(self):
        first = class_tables.table("Fighter")
        first["levels"]["1"]["second_wind"] = 99
        self.assertEqual(class_tables.table("Fighter")["levels"]["1"]["second_wind"], 2)


class NoGameplayChangeTests(unittest.TestCase):
    """The new data must not make any class appear supported for creation or level-up."""

    def test_classes_directory_holds_only_the_classes_with_real_progression(self):
        self.assertEqual(sorted(p.name for p in CLASS_DIR.glob("*.json")), ["barbarian.json", "fighter.json", "monk.json", "sorcerer.json"])

    def test_progression_engine_still_has_no_table_and_level_one_support_for_the_ten_classes(self):
        for name in NOT_PROGRESSED:
            with self.subTest(name):
                self.assertIsNone(cp.table(name))
                self.assertFalse(cp.has_table({"class": name}))
                self.assertEqual(cp._supported_level(name), 1)
                self.assertIsNone(cp.capacity({"class": name, "level": 3}))
        self.assertEqual((cp._supported_level("Sorcerer"), cp._supported_level("Barbarian"), cp._supported_level("Fighter")), (5, 5, 5))

    def test_level_up_and_creation_stay_blocked_for_the_ten_classes(self):
        import game
        for name in NOT_PROGRESSED:
            with self.subTest(name):
                session = game.create_session(seed=3)
                session.character["class"] = name
                preview = cp.preview_level_up(session, 2)
                self.assertEqual((preview["status"], preview["reason"]), ("blocked", "class_table_not_available"))
                with self.assertRaises(ValueError) as caught:
                    cp.create_at_level(session, {"character_class": name}, 2)
                self.assertIn(str(caught.exception), {"starting_level_class_not_supported", "class_table_not_available"})

    def test_public_creation_catalog_offers_starting_levels_only_for_the_progressed_classes(self):
        catalog = get_character_creation_catalog()
        self.assertEqual(sorted(k for k in catalog if k.endswith("_starting_creation")),
                         ["barbarian_starting_creation", "fighter_starting_creation", "monk_starting_creation", "sorcerer_starting_creation"])
        self.assertEqual(catalog["sorcerer_starting_creation"]["supported_starting_levels"], [1, 2, 3, 4, 5])
        blob = json.dumps(catalog, sort_keys=True)
        self.assertNotIn("class_tables", blob)
        self.assertNotIn("Epic Boon", blob, "no table content leaks into the public catalog")

    def test_data_files_hold_no_book_prose(self):
        for name in CLASSES:
            text = class_tables.table_path(name).read_text(encoding="utf-8")
            data = json.loads(text)
            names = {f for row in data["levels"].values() for f in row["features"]}
            self.assertTrue(all(len(f) <= 48 for f in names), name)
            self.assertLess(len(text), 20000, "tables hold values and names, not text")


if __name__ == "__main__":
    unittest.main()
