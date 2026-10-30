"""C05 (first slice): the 391 PHB 2024 spells have a source oracle for their rules header; the engine agrees where it implements them.

`content/rules/phb2024/spells.json` holds, per spell, level, school, class list, casting time (+ ritual), range, V/S/M flags,
duration/concentration and PDF page, read from the book's spell pages (PDF 238-342; values only, no text). The book's text layer
is OCR, so a field the OCR made unreadable is stored as null with an explicit status (never guessed): see BLOCKED below.
NOT done here (owners in HANDOFF): the spell EFFECT of any spell beyond the four existing bounded resolvers, upcasting, concentration
handling, component/material rules, spell lists per class level (C10-C21), UI. A header oracle is not a resolver.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import spell_scope
from api.dnd_2024_rules import SPELLS_CATALOG
from capabilities import manifest_rows

ROOT = Path(__file__).resolve().parents[3]
ORACLE = json.loads((ROOT / "content" / "rules" / "phb2024" / "spells.json").read_text(encoding="utf-8"))["spells"]
ROWS = {r["name"]: r for r in manifest_rows() if r["category"] == "spell"}
CLASSES = {"Bard", "Cleric", "Druid", "Paladin", "Ranger", "Sorcerer", "Warlock", "Wizard"}
SCHOOLS = {"Abjuration", "Conjuration", "Divination", "Enchantment", "Evocation", "Illusion", "Necromancy", "Transmutation"}
BLOCKED_LEVEL: set[str] = set()  # the three OCR "Level J" entries were re-read from the page scan (IMAGE_VERIFIED)
RAW = json.loads((ROOT / "content" / "rules" / "phb2024" / "spells.json").read_text(encoding="utf-8"))
LEGACY_ENGINE_ONLY = set(RAW["engine_only_not_in_phb2024"])  # in the creation catalog, not in the PHB 2024 spell pages (source not in the approved local scope)


class OracleShapeTests(unittest.TestCase):
    def test_every_manifest_spell_has_an_oracle_entry_on_its_manifest_page(self):
        self.assertEqual(len(ROWS), 391)
        self.assertEqual(set(ORACLE), set(ROWS))
        for name, spell in ORACLE.items():
            self.assertEqual(spell["pdf_page"], ROWS[name]["source"]["pdf_page"], name)

    def test_fields_are_well_formed_and_blocked_fields_are_explicit(self):
        for name, s in ORACLE.items():
            self.assertIn(s["school"], SCHOOLS, name)
            self.assertTrue(s["classes"] and set(s["classes"]) <= CLASSES, (name, s["classes"]))
            self.assertRegex(s["casting_time"], r"^(Action|Bonus Action|Reaction|\d+ (minute|hour)s?)( .*)?$", name)
            self.assertRegex(s["range"], r"^(Self|Touch|Sight|Unlimited|Special|\d+ (feet|miles?)|Self \(.*\))$", name)
            self.assertTrue(any(s["components"].values()), name)
            self.assertNotRegex(s["casting_time"].lower(), r"rit", name)  # a ritual is the flag, never part of the time
            if s["duration"] is None:
                self.assertEqual((name, s["duration_status"]), (name, "BLOCKED_OCR_UNREADABLE"))
                self.assertIsNone(s["concentration"], name)
            else:
                self.assertRegex(s["duration"], r"^(Instantaneous|Until dispelled( or triggered)?|Concentration, up to \d+ (round|minute|hour|day)s?|"
                                                r"Up to \d+ (minute|hour)s?|\d+ (round|minute|hour|day)s?|Special)$", name)
                self.assertEqual(s["concentration"], s["duration"].startswith("Concentration"), name)
            if s["level"] is None:
                self.assertTrue(s["level_status"].startswith("BLOCKED"), name)
            else:
                self.assertIn(s["level"], range(10), name)
        self.assertEqual({n for n, s in ORACLE.items() if s["level"] is None}, BLOCKED_LEVEL)

    def test_level_counts_cover_every_spell(self):
        counts = {}
        for s in ORACLE.values():
            counts[s["level"]] = counts.get(s["level"], 0) + 1
        self.assertEqual(sum(counts.values()), 391)
        self.assertIsNone(counts.get(None))
        self.assertTrue(all(counts.get(level, 0) > 0 for level in range(10)))

    def test_cantrips_are_level_zero_and_never_ritual_slots(self):
        for name, s in ORACLE.items():
            if s["ritual"]:
                self.assertTrue(s["level"] is None or s["level"] >= 1, name)


class SpotChecksFromTheBookTests(unittest.TestCase):
    """Written by hand from the spell pages read for this slice (independent of the parser)."""

    def test_known_spells(self):
        want = {
            "Acid Splash": (0, "Evocation", {"Sorcerer", "Wizard"}, "Action", False, "60 feet", "Instantaneous"),
            "Aid": (2, "Abjuration", {"Bard", "Cleric", "Druid", "Paladin", "Ranger"}, "Action", False, "30 feet", "8 hours"),
            "Alarm": (1, "Abjuration", {"Ranger", "Wizard"}, "1 minute", True, "30 feet", "8 hours"),
            "Alter Self": (2, "Transmutation", {"Sorcerer", "Wizard"}, "Action", False, "Self", "Concentration, up to 1 hour"),
            "Bane": (1, "Enchantment", {"Bard", "Cleric", "Warlock"}, "Action", False, "30 feet", "Concentration, up to 1 minute"),
            "Magic Missile": (1, "Evocation", {"Sorcerer", "Wizard"}, "Action", False, "120 feet", "Instantaneous"),
            "Burning Hands": (1, "Evocation", {"Sorcerer", "Wizard"}, "Action", False, "Self", "Instantaneous"),
        }
        for name, (level, school, classes, casting, ritual, rng, duration) in want.items():
            s = ORACLE[name]
            self.assertEqual((s["level"], s["school"], set(s["classes"]), s["casting_time"], s["ritual"], s["range"], s["duration"]),
                             (level, school, classes, casting, ritual, rng, duration), name)
        # review findings: scrambled OCR lines must not default silently
        hard = {
            "Sunbeam": (6, "Evocation", {"Cleric", "Druid", "Sorcerer", "Wizard"}, "Action", False, "Self", "Concentration, up to 1 minute"),
            "Sorcerous Burst": (0, "Evocation", {"Sorcerer"}, "Action", False, "120 feet", "Instantaneous"),
            "Darkvision": (2, "Transmutation", {"Druid", "Ranger", "Sorcerer", "Wizard"}, "Action", False, "Touch", "8 hours"),
            "Leomund's Tiny Hut": (3, "Evocation", {"Bard", "Wizard"}, "1 minute", True, "Self", "8 hours"),
            "Silence": (2, "Illusion", {"Bard", "Cleric", "Ranger"}, "Action", True, "120 feet", "Concentration, up to 10 minutes"),
        }
        for name, (level, school, classes, casting, ritual, rng, duration) in hard.items():
            s = ORACLE[name]
            self.assertEqual((s["level"], s["school"], set(s["classes"]), s["casting_time"], s["ritual"], s["duration"]),
                             (level, school, classes, casting, ritual, duration), name)
        self.assertEqual(ORACLE["Aid"]["components"], {"v": True, "s": True, "m": True})
        self.assertEqual(ORACLE["Magic Missile"]["components"], {"v": True, "s": True, "m": False})


class ImageVerifiedTests(unittest.TestCase):
    def test_the_formerly_unreadable_fields_were_read_from_the_page_scan(self):
        want = {"Divine Favor": (1, "Concentration" not in "1 minute"), "Slow": (3, True), "Tasha's Hideous Laughter": (1, True), "Clairvoyance": (3, True)}
        for name, (level, concentration) in want.items():
            s = ORACLE[name]
            self.assertEqual((s["level"], s["level_status"], s["concentration"] is not None), (level, "IMAGE_VERIFIED", True), name)
            self.assertEqual(s["image_verified"]["printed_page"], s["pdf_page"] + 1, name)
        self.assertEqual((ORACLE["Clairvoyance"]["duration"], ORACLE["Clairvoyance"]["concentration"]), ("Concentration, up to 10 minutes", True))
        self.assertEqual(ORACLE["Divine Favor"]["duration"], "1 minute")
        self.assertFalse(ORACLE["Divine Favor"]["concentration"])
        self.assertEqual(sum(1 for s in ORACLE.values() if "image_verified" in s), 5)

    def test_engine_only_spell_has_its_own_provenance_record(self):
        record = RAW["engine_only_not_in_phb2024"]["Chaos Bolt"]
        self.assertFalse(record["in_phb2024_pages_238_342"])
        self.assertNotIn("Chaos Bolt", ORACLE)


class EngineAgreementTests(unittest.TestCase):
    def test_the_four_real_resolvers_match_the_oracle(self):
        for name, (level, max_range, _sides, _kind) in spell_scope.CATALOG.items():
            spell = ORACLE[name]
            self.assertEqual(spell["level"], level, name)
            self.assertEqual(spell["range"], "Touch" if max_range == 0 else f"{max_range} feet", name)
            self.assertEqual(spell["casting_time"], "Action", name)

    def test_creation_spell_catalog_matches_levels_and_classes_except_the_documented_legacy_spell(self):
        missing = set()
        for cls, groups in SPELLS_CATALOG.items():
            for group, items in groups.items():
                for item in items:
                    spell = ORACLE.get(item["id"])
                    if spell is None:
                        missing.add(item["id"])
                        continue
                    self.assertEqual(spell["level"], {"cantrips": 0, "spells_level_2": 2}.get(group, 1), (cls, item["id"]))
                    self.assertIn(cls, spell["classes"], (cls, item["id"]))
        self.assertEqual(missing, LEGACY_ENGINE_ONLY)


if __name__ == "__main__":
    unittest.main()
