"""Dilim 4C Task 4a part 2: page-cited oracle leaves for the five first-cut spells and Concentration (data only).

The leaves sit in `content/manifest/rule-oracles.json` under `pending_leaves`: hand-written from the cited PHB 2024 page
scans, never read back from an engine. No resolver exists yet (4C.4b), so each pending rule is also an OPEN
`open_leaves` row and is never reported complete; when a resolver lands, its leaf moves to `leaves` with a DISPATCH entry.
These tests pin the data's shape and its agreement with the page-cited `spells.json` catalog row of the same spell.
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
    return {leaf["leaf_id"]: leaf for leaf in ORACLES.get("pending_leaves", [])}


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
                self.assertEqual(leaf["status"], "PENDING_RESOLVER")
                self.assertEqual(leaf["resolver_task"], "4C.4b")
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

    def test_pending_rules_stay_open_and_have_no_resolver_yet(self):
        open_rules = {row["rule"]: row for row in ORACLES["open_leaves"]}
        for leaf_id, leaf in pending().items():
            with self.subTest(leaf_id):
                self.assertEqual(open_rules[leaf["open_rule"]]["status"], "OPEN")
                self.assertNotIn(leaf_id, rule_oracles.DISPATCH)  # a resolver moves the leaf to `leaves` (4C.4b)
                self.assertNotIn(leaf_id, {covered["leaf_id"] for covered in ORACLES["leaves"]})
        for leaf in spell_leaves():
            self.assertNotIn(leaf["spell"]["name"], spell_scope.CATALOG)  # no resolver in 4C.4a


if __name__ == "__main__":
    unittest.main()
