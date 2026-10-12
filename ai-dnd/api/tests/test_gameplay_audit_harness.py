"""The offline audit must detect injected inconsistencies and use isolated sessions."""
import unittest

from scripts.gameplay_audit import classify, run_audit


class GameplayAuditHarnessTests(unittest.TestCase):
    def test_isolated_paraphrase_audit_passes(self):
        report = run_audit()
        self.assertEqual(report["total"], 5)
        self.assertEqual(report["passed"], 5)
        self.assertTrue(all(not case["findings"] for case in report["cases"]))
        self.assertTrue(all(case["model_calls"] <= 2 for case in report["cases"]))

    def test_misroute_and_false_narration_are_reported(self):
        findings = classify(
            {"kind": "drop"},
            {"inventory": ["Kılıç"], "ground": []},
            {"inventory": ["Kılıç"], "ground": []},
            "interaction",
            "Kılıç çantana geri döner.",
        )
        self.assertIn("ACTION_ROUTING_MISMATCH", findings)
        self.assertIn("INVENTORY_STATE_MISMATCH", findings)
        self.assertIn("GROUND_STATE_MISMATCH", findings)
        self.assertIn("NARRATION_STATE_CONTRADICTION", findings)


if __name__ == "__main__":
    unittest.main()
