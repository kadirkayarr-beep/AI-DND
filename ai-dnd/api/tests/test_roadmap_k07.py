"""K07 (slice 1): basic numeric character rules are bound to a source-backed oracle, one leaf per rule.

K07 is a work package, not one test: the leaves listed in content/manifest/rule-oracles.json are covered here; every family
under `open_leaves` stays OPEN and is never reported complete. Expected values are hand-written from the cited PHB 2024 lines.
"""
from __future__ import annotations

import unittest

import rule_oracles

ORACLES = rule_oracles.load_oracles()


class NumericRuleOracleTests(unittest.TestCase):
    def test_numeric_rules_match_source_oracles(self):
        leaf_rule_ids = {leaf["leaf_id"] for leaf in ORACLES["leaves"]}
        results = {}
        for leaf in ORACLES["leaves"]:
            for case in leaf["cases"]:
                case_id = f"{leaf['leaf_id']}#{case['id']}"
                results[case_id] = rule_oracles.evaluate_rule_case(case_id, ORACLES)
        obs = {
            "source_rule_ids": leaf_rule_ids,
            "leaf_rule_ids": set(rule_oracles.DISPATCH),
            "numeric_results": {key: value["actual"] for key, value in results.items()},
            "independent_rule_oracles": {key: value["expected"] for key, value in results.items()},
            "unsupported_rules_declared_complete": [
                rule for rule in ORACLES["open_leaves"] if rule.get("status") != "OPEN"],
        }
        self.assertEqual(obs["source_rule_ids"], obs["leaf_rule_ids"])
        self.assertEqual(obs["numeric_results"], obs["independent_rule_oracles"])
        self.assertEqual(obs["unsupported_rules_declared_complete"], [])

    def test_every_leaf_carries_a_boundary_case_and_a_source_page(self):
        for leaf in ORACLES["leaves"]:
            kinds = {case["kind"] for case in leaf["cases"]}
            self.assertIn("boundary", kinds, f"{leaf['leaf_id']} needs a boundary case")
            self.assertTrue(leaf["source_ref"]["pdf_page"], leaf["leaf_id"])

    def test_the_ability_modifier_oracle_is_the_published_table_not_a_formula(self):
        table = [(1, 1, -5), (2, 3, -4), (4, 5, -3), (6, 7, -2), (8, 9, -1), (10, 11, 0), (12, 13, 1), (14, 15, 2),
                 (16, 17, 3), (18, 19, 4), (20, 21, 5), (22, 23, 6), (24, 25, 7), (26, 27, 8), (28, 29, 9), (30, 30, 10)]
        import game
        from api import dnd_2024_rules
        for low, high, modifier in table:
            for score in range(low, high + 1):
                with self.subTest(score=score):
                    self.assertEqual(game.get_modifier(score), modifier)
                    self.assertEqual(dnd_2024_rules.get_modifier(score), modifier)

    def test_a_wrong_expectation_is_detected_not_absorbed(self):
        broken = {**ORACLES, "leaves": [
            dict(leaf, cases=[dict(case, expected=(case["expected"] + 1) if isinstance(case["expected"], int) else case["expected"])
                              for case in leaf["cases"]]) for leaf in ORACLES["leaves"]]}
        self.assertFalse(rule_oracles.evaluate_rule_case("K07.ability_modifier#01", broken)["match"])

    def test_an_open_rule_family_cannot_be_evaluated_as_if_it_passed(self):
        with self.assertRaises(rule_oracles.OpenRule):
            rule_oracles.evaluate_rule_case("K07.proficiency_bonus_by_level#01", ORACLES)


if __name__ == "__main__":
    unittest.main()
