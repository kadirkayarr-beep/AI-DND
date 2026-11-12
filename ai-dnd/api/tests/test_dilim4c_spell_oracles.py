"""Dilim 4C Task 4a part 2 / 4b: page-cited oracle leaves for the five first-cut spells and Concentration.

The leaves were written in 4C.4a from the cited PHB 2024 page scans (never read back from an engine) and sat in
`pending_leaves` as OPEN rules. 4C.4b added the resolvers and moved each leaf to the covered K07 `leaves` with a
DISPATCH entry; no OPEN row is left for them. These tests pin the data's shape, its agreement with the page-cited
`spells.json` catalog row of the same spell, and that every case runs the real engine and matches.
(Rewritten in 4C.4b, equally strict: the "still OPEN, no resolver" tripwire became "covered, resolver runs, matches".)
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import rule_oracles
import spell_scope

ORACLES = rule_oracles.load_oracles()
SPELLS = json.loads((Path(rule_oracles.ORACLE_PATH).parents[1] / "rules" / "phb2024" / "spells.json")
                    .read_text(encoding="utf-8"))["spells"]
FIRST_CUT = {"Ray of Frost", "Shocking Grasp", "Toll the Dead", "Healing Word", "Bless"}


def pending():
    """The 4C first-cut leaves (name kept from 4C.4a): covered K07 leaves since 4C.4b."""
    return {leaf["leaf_id"]: leaf for leaf in ORACLES["leaves"] if leaf["leaf_id"].startswith("4C.")}


def spell_leaves():
    return [leaf for leaf in pending().values() if leaf["family"] == "spell"]


class PendingSpellOracleLeaves(unittest.TestCase):
    def test_the_five_first_cut_spells_and_concentration_have_a_leaf(self):
        self.assertEqual({leaf["spell"]["name"] for leaf in spell_leaves()}, FIRST_CUT)
        self.assertIn("4C.concentration", pending())

    def test_every_leaf_is_page_cited_from_the_scan_with_a_boundary_case(self):
        for leaf_id, leaf in pending().items():
            with self.subTest(leaf_id):
                ref = leaf["source_ref"]
                self.assertIsInstance(ref["pdf_page"], int)
                self.assertEqual(ref["printed_page"], ref["pdf_page"] + 1)
                self.assertIn("page scan image", ref["verified_from"])
                self.assertIn("boundary", {case["kind"] for case in leaf["cases"]})
                self.assertEqual(len({case["id"] for case in leaf["cases"]}), len(leaf["cases"]))
                self.assertEqual(leaf["resolved_in"], "4C.4b")
                self.assertNotIn("status", leaf)  # no PENDING/OPEN marker left on a covered leaf
                self.assertTrue(leaf["engine_resolvers"])
                self.assertNotIn("UNVERIFIED", json.dumps(leaf["cases"]))  # an unverified value never becomes a case

    def test_spell_leaves_agree_with_the_page_cited_catalog_row(self):
        for leaf in spell_leaves():
            spell = leaf["spell"]
            row = SPELLS[spell["name"]]
            with self.subTest(spell["name"]):
                self.assertEqual(leaf["source_ref"]["pdf_page"], row["pdf_page"])
                self.assertEqual(spell["level"], row["level"])
                self.assertEqual(spell["casting_time"], row["casting_time"])
                self.assertEqual(spell["concentration"], row["concentration"])
                self.assertEqual(spell["range"], row["range"])

    def test_cantrip_dice_follow_the_cited_upgrade_levels(self):
        for leaf in spell_leaves():
            spell = leaf["spell"]
            if spell["level"] != 0:
                continue
            self.assertEqual(spell["cantrip_upgrade"], {"5": 2, "11": 3, "17": 4}, spell["name"])
            for case in leaf["cases"]:
                level = case["input"].get("caster_level")
                rolled = case["input"].get("dice_rolled")
                if level is None or rolled is None:
                    continue
                dice = 1 + sum(level >= int(at) for at in spell["cantrip_upgrade"])
                with self.subTest(spell=spell["name"], case=case["id"]):
                    self.assertEqual(len(rolled), dice)

    def test_concentration_dc_cases_cover_the_floor_the_halving_and_the_cap(self):
        cases = pending()["4C.concentration"]["cases"]
        dcs = {case["input"]["damage"]: case["expected"]["dc"] for case in cases if case["input"].get("op") == "save_dc"}
        self.assertTrue({1, 21, 22, 23, 59, 60, 61} <= set(dcs))
        self.assertEqual(min(dcs.values()), 10)
        self.assertEqual(max(dcs.values()), 30)

    def test_covered_rules_run_the_engine_and_left_open_and_pending(self):
        self.assertEqual(len(pending()), 6)
        self.assertEqual(ORACLES["pending_leaves"], [])
        open_rules = {row["rule"] for row in ORACLES["open_leaves"]}
        for rule in ("spell_ray_of_frost", "spell_shocking_grasp", "spell_toll_the_dead", "spell_healing_word",
                     "spell_bless", "concentration"):
            self.assertNotIn(rule, open_rules)
        for leaf_id, leaf in pending().items():
            self.assertIn(leaf_id, rule_oracles.DISPATCH)
            for case in leaf["cases"]:
                with self.subTest(leaf=leaf_id, case=case["id"]):
                    result = rule_oracles.evaluate_rule_case(f"{leaf_id}#{case['id']}", ORACLES)
                    self.assertTrue(result["match"], result)
                    self.assertEqual(result["source_ref"]["pdf_page"], leaf["source_ref"]["pdf_page"])
        for leaf in spell_leaves():
            self.assertIn(leaf["spell"]["name"], spell_scope.CATALOG)  # the resolver is the spell owner's

    def test_a_wrong_expectation_in_a_spell_leaf_is_detected(self):
        broken = json.loads(json.dumps(ORACLES))
        leaf = next(leaf for leaf in broken["leaves"] if leaf["leaf_id"] == "4C.spell.toll_the_dead")
        leaf["cases"][1]["expected"]["die"] = 8  # the book's d12 for a wounded target, written wrong
        self.assertFalse(rule_oracles.evaluate_rule_case("4C.spell.toll_the_dead#02", broken)["match"])


if __name__ == "__main__":
    unittest.main()
