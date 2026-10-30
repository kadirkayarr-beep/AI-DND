"""C03: every PHB 2024 feat has its prerequisite, repeatability and ability-score rule enforced, from a source oracle.

`content/rules/phb2024/feats.json` holds facts and pages read from the book (no book text). `feat_rules` answers who may take
a feat (`eligible_feats`, `feat_status`) and computes the ability increase a feat gives (`apply_feat_choice`, pure: it returns
a delta and never mutates the character). The expectations in the explicit tests below were written from the book text
independently of the oracle, so the oracle cannot just agree with itself. The other benefits of a feat (what it lets a character
DO) are not implemented here; every delta lists them under `effects_pending`, and the C03 leaves for them stay open.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import feat_rules
from api.dnd_2024_rules import ORIGIN_FEATS

ROOT = Path(__file__).resolve().parents[3]
ORACLE = json.loads((ROOT / "content" / "rules" / "phb2024" / "feats.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / "content" / "manifest" / "phb2024.json").read_text(encoding="utf-8"))
MANIFEST_FEATS = {r["name"]: r for r in MANIFEST["rows"] if r["category"] == "feat"}


def hero(cls="Fighter", level=4, **scores):
    base = {"strength": 10, "dexterity": 10, "constitution": 10, "intelligence": 10, "wisdom": 10, "charisma": 10}
    base.update(scores)
    return {"class": cls, "level": level, "feats": [], **base}


def eligible(character, feat, source="class_asi"):
    return feat in feat_rules.eligible_feats(character, source)


class CatalogTests(unittest.TestCase):
    def test_every_feat_has_prerequisite_and_use_evidence(self):
        names = set(ORACLE["feats"])
        obs = {
            "manifest_feats_missing_from_oracle": sorted(set(MANIFEST_FEATS) - names),
            "oracle_feats_not_in_manifest": sorted(names - set(MANIFEST_FEATS)),
            "category_counts": {c: sum(1 for f in ORACLE["feats"].values() if f["category"] == c)
                                for c in ("origin", "general", "fighting_style", "epic_boon")},
            "feats_without_asi_or_prerequisite_decision": sorted(
                n for n, f in ORACLE["feats"].items()
                if f["category"] in ("general", "epic_boon") and f["asi"] is None),
            "resolver_origin_feats_missing": sorted(
                set(ORIGIN_FEATS) - {n for n, f in ORACLE["feats"].items() if f["category"] == "origin"}),
            "repeatable": sorted(n for n, f in ORACLE["feats"].items() if f["repeatable"]),
        }
        assert obs["manifest_feats_missing_from_oracle"] == [] and obs["oracle_feats_not_in_manifest"] == []
        assert obs["category_counts"] == {"origin": 10, "general": 43, "fighting_style": 10, "epic_boon": 12}
        assert obs["feats_without_asi_or_prerequisite_decision"] == []
        assert obs["resolver_origin_feats_missing"] == []
        assert obs["repeatable"] == ["Ability Score Improvement", "Elemental Adept", "Magic Initiate", "Skilled"]
        # every feat answers the eligibility question for a bare character without raising, and says why when it refuses
        bare = hero("Wizard", 1)
        for name in ORACLE["feats"]:
            status = feat_rules.feat_status(bare, name, "class_asi")
            self.assertIn("eligible", status, name)
            if not status["eligible"]:
                self.assertTrue(status["reasons"], f"{name} refuses without a reason")

    def test_pages_match_the_manifest(self):
        for name, feat in ORACLE["feats"].items():
            self.assertEqual(feat["pdf_page"], MANIFEST_FEATS[name]["source"]["pdf_page"], name)


class PrerequisiteTests(unittest.TestCase):
    """Expectations transcribed from the book, one rule each."""

    def test_general_feats_need_level_4(self):
        self.assertFalse(eligible(hero("Fighter", 3, charisma=20), "Actor"))
        self.assertTrue(eligible(hero("Fighter", 4, charisma=13), "Actor"))
        self.assertTrue(eligible(hero("Fighter", 4), "Durable"))
        self.assertFalse(eligible(hero("Fighter", 3), "Durable"))

    def test_ability_minimums_are_13_and_respect_either_or(self):
        self.assertFalse(eligible(hero(charisma=12), "Actor"))
        self.assertTrue(eligible(hero(charisma=13), "Actor"))
        self.assertTrue(eligible(hero(strength=13), "Athlete"))
        self.assertTrue(eligible(hero(dexterity=13), "Athlete"))
        self.assertFalse(eligible(hero(strength=12, dexterity=12), "Athlete"))
        self.assertTrue(eligible(hero(intelligence=13), "Ritual Caster"))
        self.assertTrue(eligible(hero(wisdom=13), "Ritual Caster"))
        self.assertFalse(eligible(hero(strength=18), "Sharpshooter"), "Sharpshooter wants Dexterity, not Strength")
        self.assertTrue(eligible(hero(dexterity=13), "Sharpshooter"))

    def test_armor_training_prerequisites_follow_the_chain(self):
        wizard, fighter = hero("Wizard", 4), hero("Fighter", 4)
        self.assertFalse(eligible(wizard, "Moderately Armored"), "needs Light armor training")
        self.assertTrue(eligible(fighter, "Moderately Armored"))
        self.assertFalse(eligible(wizard, "Heavily Armored"), "needs Medium armor training")
        self.assertTrue(eligible(fighter, "Heavily Armored"))
        self.assertTrue(eligible(fighter, "Heavy Armor Master"))
        self.assertFalse(eligible(hero("Cleric", 4), "Heavy Armor Master"), "a cleric has no Heavy training")
        self.assertTrue(eligible(hero("Cleric", 4), "Shield Master"), "a cleric trains with shields")
        self.assertFalse(eligible(wizard, "Shield Master"))
        # a feat that grants training satisfies the next prerequisite
        trained = {**wizard, "feats": ["Lightly Armored"]}
        self.assertTrue(eligible(trained, "Moderately Armored"))
        self.assertTrue(eligible(trained, "Shield Master"), "Lightly Armored grants Shield training")
        self.assertFalse(eligible(trained, "Heavily Armored"), "Medium training is still missing")

    def test_spellcasting_prerequisites(self):
        for feat in ("Elemental Adept", "Spell Sniper", "War Caster"):
            self.assertTrue(eligible(hero("Wizard", 4), feat), feat)
            self.assertTrue(eligible(hero("Warlock", 4), feat), f"{feat}: Pact Magic counts")
            self.assertFalse(eligible(hero("Fighter", 4), feat), feat)

    def test_fighting_style_feats_need_the_feature(self):
        self.assertTrue(eligible(hero("Fighter", 1), "Archery", "fighting_style"))
        self.assertFalse(eligible(hero("Wizard", 4), "Archery", "fighting_style"))
        # PHB p.198: an ASI level offers "another feat for which you qualify"; no category restriction beyond the prerequisites
        self.assertTrue(eligible(hero("Fighter", 4), "Archery", "class_asi"))
        self.assertFalse(eligible(hero("Wizard", 4), "Archery", "class_asi"), "no Fighting Style feature")
        self.assertTrue(eligible(hero("Wizard", 4), "Alert", "class_asi"), "an Origin feat is open at an ASI level")
    def test_epic_boons_need_level_19(self):
        self.assertFalse(eligible(hero("Fighter", 18), "Boon of Fate"))
        self.assertTrue(eligible(hero("Fighter", 19), "Boon of Fate"))
        self.assertFalse(eligible(hero("Fighter", 19), "Boon of Spell Recall"), "needs a Spellcasting feature")
        self.assertTrue(eligible(hero("Wizard", 19), "Boon of Spell Recall"))

    def test_origin_feats_have_no_prerequisite_and_come_from_origin_sources(self):
        self.assertTrue(eligible(hero("Wizard", 1), "Alert", "background"))
        self.assertTrue(eligible(hero("Wizard", 1), "Tough", "species"))
        self.assertFalse(eligible(hero("Wizard", 1), "Actor", "background"), "a background gives an Origin feat only")

    def test_a_feat_can_be_taken_once_unless_it_is_repeatable(self):
        had = {**hero("Fighter", 8), "feats": ["Durable"], "origin_feats": ["Alert"]}
        self.assertFalse(eligible(had, "Durable"))
        self.assertFalse(eligible(had, "Alert", "background"))
        self.assertTrue(eligible({**had, "feats": ["Ability Score Improvement"]}, "Ability Score Improvement"))
        self.assertTrue(eligible({**had, "origin_feats": ["Magic Initiate"]}, "Magic Initiate", "background"))
        wizard = {**hero("Wizard", 8), "feats": ["Elemental Adept"]}
        self.assertTrue(eligible(wizard, "Elemental Adept"), "Elemental Adept is repeatable")
        self.assertFalse(eligible({**hero("Wizard", 8), "feats": ["War Caster"]}, "War Caster"))


class AbilityIncreaseTests(unittest.TestCase):
    def test_the_ability_score_improvement_feat(self):
        sheet = hero("Fighter", 4, strength=18, dexterity=14)
        plus2 = feat_rules.apply_feat_choice(sheet, "Ability Score Improvement", {"increase": {"strength": 2}})
        self.assertEqual((plus2["status"], plus2["changes"]), ("applied", [{"ability": "strength", "from": 18, "to": 20}]))
        two = feat_rules.apply_feat_choice(sheet, "Ability Score Improvement", {"increase": {"strength": 1, "dexterity": 1}})
        self.assertEqual({c["ability"]: c["to"] for c in two["changes"]}, {"strength": 19, "dexterity": 15})
        self.assertEqual(sheet["strength"], 18, "the character is never mutated by the delta")
        over = feat_rules.apply_feat_choice(hero(strength=19), "Ability Score Improvement", {"increase": {"strength": 2}})
        self.assertEqual(over["status"], "rejected", "no score above 20")
        for bad in ({"strength": 3}, {"strength": 1, "dexterity": 2}, {"strength": 1, "dexterity": 1, "wisdom": 1}, {}, {"luck": 2}):
            self.assertEqual(feat_rules.apply_feat_choice(sheet, "Ability Score Improvement", {"increase": bad})["status"],
                             "rejected", bad)

    def test_a_feats_own_increase_is_one_point_from_its_list(self):
        sheet = hero("Fighter", 4, strength=15, dexterity=14)
        ok = feat_rules.apply_feat_choice(sheet, "Athlete", {"ability": "dexterity"})
        self.assertEqual(ok["changes"], [{"ability": "dexterity", "from": 14, "to": 15}])
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Athlete", {"ability": "intelligence"})["status"], "rejected")
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Athlete", {})["status"], "rejected", "a choice feat needs its choice")
        single = feat_rules.apply_feat_choice(hero(strength=13), "Great Weapon Master", {})
        self.assertEqual(single["changes"], [{"ability": "strength", "from": 13, "to": 14}], "a one-ability feat needs no choice")
        capped = feat_rules.apply_feat_choice(hero(strength=20), "Great Weapon Master", {})
        self.assertEqual((capped["status"], capped["changes"]), ("applied", []), "already at the cap: nothing increases")

    def test_epic_boons_cap_at_30(self):
        sheet = hero("Fighter", 19, strength=29)
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Boon of Fate", {"ability": "strength"})["changes"],
                         [{"ability": "strength", "from": 29, "to": 30}])
        self.assertEqual(feat_rules.apply_feat_choice({**sheet, "strength": 30}, "Boon of Fate", {"ability": "strength"})["changes"], [])
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Boon of Irresistible Offense", {"ability": "wisdom"})["status"], "rejected")

    def test_resilient_only_for_an_ability_without_save_proficiency(self):
        fighter = hero("Fighter", 4)  # Fighters are proficient in Strength and Constitution saves
        self.assertEqual(feat_rules.apply_feat_choice(fighter, "Resilient", {"ability": "constitution"})["status"], "rejected")
        ok = feat_rules.apply_feat_choice(fighter, "Resilient", {"ability": "wisdom"})
        self.assertEqual(ok["status"], "applied")
        self.assertIn("wisdom", ok["grants_save_proficiency"])

    def test_every_feat_returns_a_delta_and_names_the_effects_that_are_not_implemented(self):
        sheet = hero("Wizard", 19, strength=14, dexterity=14, constitution=14, intelligence=16, wisdom=14, charisma=14)
        for name, feat in ORACLE["feats"].items():
            choice = {}
            if feat["asi"] and len(feat["asi"]["abilities"]) > 1:
                choice = {"ability": feat["asi"]["abilities"][0]}
            if name == "Ability Score Improvement":
                choice = {"increase": {"strength": 2}}
            if name == "Resilient":
                choice = {"ability": "strength"}
            delta = feat_rules.apply_feat_choice(sheet, name, choice)
            self.assertIn(delta["status"], {"applied", "rejected"}, name)
            self.assertIn("effects_pending", delta, name)
            if delta["status"] == "applied" and name != "Ability Score Improvement":
                self.assertTrue(delta["effects_pending"], f"{name}: benefits beyond the increase are named as pending")
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Not A Feat", {})["status"], "rejected")

    def test_a_valid_choice_is_really_applied_for_known_feats(self):
        sheet = hero("Wizard", 19, strength=14, dexterity=14, constitution=14, intelligence=16, wisdom=14, charisma=14)
        for name, choice in {"Alert": {}, "Lucky": {}, "Skilled": {}, "Boon of Fate": {"ability": "wisdom"}, "War Caster": {"ability": "wisdom"}, "Magic Initiate": {},
                             "Resilient": {"ability": "strength"}, "Ability Score Improvement": {"increase": {"strength": 2}}}.items():
            delta = feat_rules.apply_feat_choice(sheet, name, choice)
            self.assertEqual(delta["status"], "applied", f"{name}: {delta}")


class ReviewHardeningTests(unittest.TestCase):
    """Findings of the independent C03 review: malformed input fails closed, nothing is mutated, boundaries are pinned."""

    def test_malformed_increase_values_are_rejected_not_raised(self):
        sheet = hero("Fighter", 4, strength=10, dexterity=10)
        for bad in ({"strength": 1, "dexterity": "x"}, {"strength": True, "dexterity": True}, {"strength": 2.0}, {"luck": 2}, [], None):
            delta = feat_rules.apply_feat_choice(sheet, "Ability Score Improvement", {"increase": bad})
            self.assertEqual((delta["status"], delta["reason"]), ("rejected", "invalid_increase"), bad)

    def test_a_bare_string_of_feats_is_one_feat_not_characters(self):
        sheet = {**hero("Fighter", 4), "feats": "Alert"}
        self.assertEqual(feat_rules.held_feats(sheet), ["Alert"])
        self.assertIn("already_taken", feat_rules.feat_status(sheet, "Alert", "any")["reasons"])
        sheet["feats"] = None
        self.assertEqual(feat_rules.held_feats(sheet), [])
        sheet.pop("feats")
        self.assertTrue(feat_rules.feat_status(sheet, "Alert", "any")["eligible"])

    def test_the_character_and_the_catalog_are_not_mutated(self):
        import copy
        sheet = {**hero("Fighter", 4), "feats": ["Alert"]}
        before = copy.deepcopy(sheet)
        feat_rules.apply_feat_choice(sheet, "Ability Score Improvement", {"increase": {"strength": 2}})
        feat_rules.apply_feat_choice(sheet, "Skilled", {})
        self.assertEqual(sheet, before)
        feat_rules.catalog()["Alert"]["level"] = 99
        self.assertTrue(feat_rules.feat_status(hero("Fighter", 4), "Alert", "any")["eligible"])

    def test_unknown_source_and_ineligible_choice_are_refused_with_reasons(self):
        self.assertEqual(feat_rules.feat_status(hero(), "Alert", "typo")["reasons"], ["unknown_source"])
        delta = feat_rules.apply_feat_choice(hero("Fighter", 3), "Grappler", {"source": "any"})
        self.assertEqual((delta["status"], delta["reason"]), ("rejected", "not_eligible"))
        self.assertIn("level_4_required", delta["reasons"])
        self.assertIn("ability_strength_or_dexterity_13_required", delta["reasons"])
        self.assertTrue(feat_rules.feat_status(hero("Fighter", 1), "Alert", "any")["eligible"])

    def test_repeatable_feats_apply_twice_but_others_do_not(self):
        sheet = {**hero("Fighter", 4), "feats": ["Skilled", "Alert"]}
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Skilled", {})["status"], "applied")
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Alert", {})["reason"], "not_eligible")

    def test_ability_boundaries_are_pinned(self):
        near = hero("Fighter", 4, strength=19, dexterity=20)
        self.assertEqual(feat_rules.apply_feat_choice(near, "Ability Score Improvement", {"increase": {"strength": 2}})["reason"], "exceeds_cap")
        self.assertEqual(feat_rules.apply_feat_choice(near, "Ability Score Improvement", {"increase": {"strength": 1, "dexterity": 1}})["reason"], "exceeds_cap")
        self.assertEqual(feat_rules.apply_feat_choice(near, "Ability Score Improvement", {"increase": {"strength": 1, "constitution": 1}})["status"], "applied")
        # a feat's own fixed +1 clamps at the cap instead of refusing
        maxed = hero("Fighter", 4, strength=20)
        delta = feat_rules.apply_feat_choice(maxed, "Grappler", {"ability": "strength"})
        self.assertEqual((delta["status"], delta["changes"]), ("applied", []))
        # Resilient: a save proficiency granted through the character sheet also blocks the choice
        sheet = {**hero("Wizard", 4), "saving_throw_proficiencies": ["strength"]}
        self.assertEqual(feat_rules.apply_feat_choice(sheet, "Resilient", {"ability": "strength"})["reason"], "already_proficient_in_that_save")

    def test_class_feature_prerequisites_fail_closed_until_the_class_system_exists(self):
        # Pact Magic is not the Spellcasting feature (Boon of Spell Recall); half-casters and subclass casters need an explicit entry
        self.assertFalse(eligible(hero("Warlock", 19), "Boon of Spell Recall"))
        self.assertTrue(eligible({**hero("Warlock", 19), "features": ["Spellcasting"]}, "Boon of Spell Recall"))
        self.assertTrue(eligible(hero("Warlock", 4), "War Caster"), "War Caster accepts Pact Magic")
        self.assertFalse(eligible(hero("Paladin", 4), "Archery", "fighting_style"), "no Fighting Style entry in the class resolver")
        self.assertTrue(eligible({**hero("Paladin", 4), "features": ["Fighting Style"]}, "Archery", "fighting_style"))

    def test_prerequisite_table_written_independently_of_the_oracle(self):
        # (feat, category, level, ability minimum or None, repeatable) read from the PHB feat list, not from feats.json
        table = [("Alert", "origin", None, None, False), ("Skilled", "origin", None, None, True), ("Grappler", "general", 4, 13, False),
                 ("Keen Mind", "general", 4, 13, False), ("Speedy", "general", 4, 13, False), ("Poisoner", "general", 4, None, False),
                 ("Elemental Adept", "general", 4, None, True), ("Archery", "fighting_style", None, None, False),
                 ("Boon of Fate", "epic_boon", 19, None, False), ("Ability Score Improvement", "general", 4, None, True)]
        for name, category, level, minimum, repeatable in table:
            feat = ORACLE["feats"][name]
            got = (feat["category"], feat["level"], (feat["ability_min"] or {}).get("min"), feat["repeatable"])
            self.assertEqual(got, (category, level, minimum, repeatable), name)


if __name__ == "__main__":
    unittest.main()
