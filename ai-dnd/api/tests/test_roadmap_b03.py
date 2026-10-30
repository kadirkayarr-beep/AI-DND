"""B03 failure-triage contract; reads retained evidence only, no game/model/server calls."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest


REPO = Path(__file__).resolve().parents[3]
ACCEPTANCE = REPO / "docs" / "acceptance"
CONTRACT = ACCEPTANCE / "failure-contracts.json"
EVIDENCE = ACCEPTANCE / "evidence"
RUN_ONE = EVIDENCE / "b03-anchors-78b3803"
RUN_TWO = EVIDENCE / "b03-anchors-78b3803-v2"
PARENT_RUN = EVIDENCE / "b03-parent-cb40a59"
OLD_DOUBLE_OUTPUT = EVIDENCE / "b03-diagnostics" / "b03-diag-old-double.output.log"
SOURCE_SHA = "78b380384e70832156d2d9aa2785192bbbbdb74b"
sys.path.insert(0, str(REPO / "tools" / "acceptance"))
import evidence as ledger_owner
import failure_contract as owner


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_run(directory):
    return json.loads((directory / "run.json").read_text(encoding="utf-8"))


def failing_rows(run):
    return {row["id"]: row for row in run["per_test"] if row["outcome"] in ("failure", "error")}


class RoadmapB03Tests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.rows = self.contract["rows"]
        self.run = load_run(RUN_TWO)

    def observe(self):
        """Test-local observations measured from the retained contract, never from the audit report."""
        profile = [row for row in self.rows if row["plan_cause_class"] == "schema_double"]
        return {
            "failed_methods": len({row["method_id"] for row in self.rows}),
            "failed_assertions": len(self.rows),
            "profile_double_methods": len({row["method_id"] for row in profile}),
            "profile_double_assertions": len(profile),
        }

    def methods_by_status(self):
        by_method = {row["method_id"]: row["evidence_status"] for row in self.rows}
        counts = {}
        for status in by_method.values():
            counts[status] = counts.get(status, 0) + 1
        return counts

    def test_triage_requires_contract_and_cause(self):
        obs = self.observe()
        assert obs["failed_methods"] == 11
        assert obs["failed_assertions"] == 13
        assert obs["profile_double_methods"] == 7
        assert obs["profile_double_assertions"] == 9

        owners = {}
        for row in self.rows:
            owners.setdefault(row["owner_task"], set()).add(row["method_id"])
        self.assertEqual({task: len(methods) for task, methods in owners.items()},
                         {"W02": 7, "W03": 1, "W04": 2, "W05": 1})
        for row in self.rows:
            self.assertEqual(owner.validate_failure_contract(row), [], row["assertion_id"])

        for field in ("cause_class", "approved_behavior", "before_evidence", "owner_task"):
            broken = copy.deepcopy(self.rows[0])
            del broken[field]
            self.assertTrue(any(field in error for error in owner.validate_failure_contract(broken)), field)

    def test_contract_refuses_unproven_or_expectation_changing_rows(self):
        confirmed = next(row for row in self.rows if row["evidence_status"] == "CONFIRMED_BY_DIAGNOSTIC")
        unresolved = next(row for row in self.rows if row["cause_class"] == "unresolved")
        evidence = confirmed["before_evidence"]
        cases = {
            "expectation_changed": (confirmed, {"expectation_changed": True}),
            "cause_class": (confirmed, {"cause_class": "flaky"}),
            "owner_task": (confirmed, {"owner_task": "W99"}),
            "evidence_status": (confirmed, {"evidence_status": "CONFIRMED"}),
            "approved_behavior_blank": (confirmed, {"approved_behavior": "   "}),
            "approved_behavior_uncited": (confirmed, {"approved_behavior": "NPC answers correctly."}),
            "diagnostic": (confirmed, {"diagnostic": ""}),
            "bad_digest": (confirmed, {"before_evidence": {**evidence, "run_json_sha256": "abc"}}),
            "not_isolated": (confirmed, {"before_evidence": {**evidence, "isolated": False}}),
            "refs_empty": (confirmed, {"approved_behavior_refs": []}),
            "refs_unknown": (confirmed, {"approved_behavior_refs": ["§99"]}),
            "refs_unknown_but_quoted": (confirmed, {"approved_behavior_refs": ["§99"],
                                                    "approved_behavior": "Design Rev2 §99"}),
            "ref_not_in_text": (confirmed, {"approved_behavior_refs": ["§16.7", "S12"],
                                            "approved_behavior": "Design Rev2 §16.7 only"}),
            "parent_outcome": (confirmed, {"parent_outcome": "maybe"}),
            "double_claim_without_artifact": (confirmed, {"before_evidence": {**evidence, "diagnostic_artifacts": []}}),
            "double_claim_without_status": (confirmed, {"evidence_status": "REPRODUCED_CAUSE_NOT_VERIFIED"}),
            "double_claim_not_sufficient": (confirmed, {"double_change_sufficient": False}),
            "unresolved_claims_sufficient": (unresolved, {"double_change_sufficient": True}),
            "unresolved_claims_measured": (unresolved, {"cause_class_basis": "measured_by_double_swap"}),
            "unresolved_with_confirmed_status": (unresolved, {"evidence_status": "CONFIRMED_BY_DIAGNOSTIC"}),
        }
        for name, (base, change) in cases.items():
            self.assertTrue(owner.validate_failure_contract({**base, **change}), name)

    def test_preexisting_claim_needs_a_failing_parent_and_artifacts(self):
        preexisting = next(row for row in self.rows if row["evidence_status"] == "PREEXISTING_NOT_DOUBLE")
        self.assertNotEqual(preexisting["parent_outcome"], "pass")
        self.assertTrue(owner.validate_failure_contract({**preexisting, "parent_outcome": "pass"}))
        self.assertTrue(owner.validate_failure_contract(
            {**preexisting, "before_evidence": {**preexisting["before_evidence"], "diagnostic_artifacts": []}}))

    def test_contract_rows_are_rederived_from_the_retained_runs(self):
        self.assertEqual(self.run["source_start"]["revision"], SOURCE_SHA)
        self.assertFalse(self.run["source_changed_during_run"])
        failing = failing_rows(self.run)
        self.assertEqual({row["method_id"] for row in self.rows}, set(failing))
        expected_ids = []
        for method, row in failing.items():
            events = [e for e in row["events"] if e["outcome"] in ("failure", "error")]
            for index, event in enumerate(events, 1):
                file_name, line, last, digest = owner.derive_assertion(event)
                expected_ids.append((method, f"{method}#{index}@{file_name}:{line}", last[:200], digest))
        stored = [(row["method_id"], row["assertion_id"], row["assertion_error"], row["assertion_trace_sha256"])
                  for row in self.rows]
        self.assertEqual(sorted(stored), sorted(expected_ids))
        for row in self.rows:
            self.assertEqual(row["before_evidence"]["run_json_sha256"], sha256(RUN_TWO / "run.json"))
            self.assertEqual(row["before_evidence"]["output_log_sha256"], sha256(RUN_TWO / "output.log"))
        normalized = ledger_owner.normalize_harness_run(self.run, RUN_TWO / "output.log")
        ledger = ledger_owner.deduplicate_results(normalized["results"])
        self.assertEqual(ledger["statuses"].get("FAIL"), 11)
        self.assertEqual(ledger["executions"], self.contract["measured"]["executed_methods"])

    def test_second_run_reproduces_the_first_run(self):
        first, second = failing_rows(load_run(RUN_ONE)), failing_rows(self.run)
        self.assertEqual(set(first), set(second))
        for method in first:
            self.assertEqual(owner.failure_signature(first[method]), owner.failure_signature(second[method]), method)
        self.assertTrue(self.contract["measured"]["reproduced_in_second_run"])

    def test_retained_files_match_their_recorded_digests(self):
        self.assertEqual(owner.verify_retained_files(self.contract, ACCEPTANCE), [])
        tampered = copy.deepcopy(self.contract)
        some_path = next(iter(tampered["evidence_files"]))
        tampered["evidence_files"][some_path] = "0" * 64
        self.assertTrue(owner.verify_retained_files(tampered, ACCEPTANCE))
        tampered["evidence_files"]["evidence/does-not-exist.txt"] = "0" * 64
        self.assertTrue(any("does-not-exist" in error for error in owner.verify_retained_files(tampered, ACCEPTANCE)))
        for artifact in ("b03-diagnostics/b03-diag-old-double.output.log",
                         "b03-diagnostics/b03-diag-v2.output.log", "b03-diagnostics/b03-trace.output.log"):
            self.assertIn("evidence/" + artifact, self.contract["evidence_files"])

    def test_parent_comparison_is_recomputed_from_the_retained_parent_run(self):
        head, parent = failing_rows(self.run), failing_rows(load_run(PARENT_RUN))
        by_method = {row["method_id"].replace("api.tests.", ""): row["parent_outcome"] for row in self.rows}
        for method, head_row in head.items():
            if method not in parent:
                expected = "pass"
            elif owner.failure_signature(parent[method]) == owner.failure_signature(head_row):
                expected = "same_signature_fail"
            else:
                expected = "different_signature_fail"
            self.assertEqual(by_method[method.replace("api.tests.", "")], expected, method)
        self.assertEqual(len(parent), self.contract["measured"]["parent_failed_methods"])
        self.assertEqual(len(parent), 35)
        self.assertEqual(len(set(parent) - set(head)), self.contract["measured"]["parent_only_failures_repaired_by_83c6ebd"])
        new_at_head = {row["method_id"] for row in self.rows if row["parent_outcome"] == "pass"}
        self.assertEqual(new_at_head, {
            "api.tests.test_campaign_api.CampaignApiTests."
            "test_conversation_proposal_rejection_and_valid_unknown_are_distinct",
            "api.tests.test_campaign_api.CampaignApiTests."
            "test_missing_conversation_fields_reject_without_retry_or_focus_change"})

    def test_double_swap_output_supports_each_evidence_status(self):
        pattern = re.compile(r"^(test_[a-z0-9_]+): (\d+) -> (\d+)\s*$", re.MULTILINE)
        swap = {name: (int(before), int(after))
                for name, before, after in pattern.findall(OLD_DOUBLE_OUTPUT.read_text(encoding="utf-8"))}
        self.assertEqual(len(swap), 7)
        for row in self.rows:
            if row["plan_cause_class"] != "schema_double":
                continue
            before, after = swap[row["method_id"].rsplit(".", 1)[-1]]
            self.assertGreater(before, 0)
            if row["evidence_status"] == "CONFIRMED_BY_DIAGNOSTIC":
                self.assertEqual(after, 0, row["method_id"])
            else:
                self.assertEqual(row["evidence_status"], "PREEXISTING_NOT_DOUBLE")
                self.assertGreater(after, 0, row["method_id"])

    def test_plan_class_is_reported_as_only_partially_confirmed(self):
        self.assertEqual(self.methods_by_status(), {"CONFIRMED_BY_DIAGNOSTIC": 3, "PREEXISTING_NOT_DOUBLE": 4,
                                                    "REPRODUCED_CAUSE_NOT_VERIFIED": 4})
        for row in self.rows:
            claimed_double = row["cause_class"] == "test_fixture_double"
            self.assertEqual(claimed_double, row["evidence_status"] == "CONFIRMED_BY_DIAGNOSTIC")
            self.assertEqual(row["double_change_sufficient"], claimed_double)
        self.assertEqual(self.contract["triage_status"], "PLAN_CLASS_PARTIALLY_CONFIRMED")
        self.assertEqual(owner.triage_summary(self.rows), self.contract["triage_status"])
        confirmed = [{**self.rows[0], "evidence_status": "CONFIRMED_BY_DIAGNOSTIC"}]
        self.assertEqual(owner.triage_summary(confirmed), "PLAN_CLASS_CONFIRMED")
        self.assertEqual(owner.triage_summary([]), "PLAN_CLASS_NOT_CONFIRMED")

    def test_history_is_append_only(self):
        first = [{"entry": 1, "action": "initial_triage", "rows": 13}]
        second = [*first, {"entry": 2, "action": "reclassify", "rows": 13}]
        self.assertEqual(owner.validate_history(first, second), [])
        self.assertEqual(owner.validate_history(first, first), [])
        self.assertTrue(owner.validate_history(second, first))
        self.assertTrue(owner.validate_history(first, [{**first[0], "rows": 12}]))
        self.assertTrue(owner.validate_history(first, [{"entry": 2}, *first]))
        history = self.contract["history"]
        self.assertEqual([entry["entry"] for entry in history], [1, 2])
        previous = json.loads((EVIDENCE / "b03-triage-history" / "failure-contracts.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(owner.validate_history(previous["history"], history), [])
        self.assertEqual(history[1]["previous_contract_sha256"],
                         sha256(EVIDENCE / "b03-triage-history" / "failure-contracts.v1.json"))


if __name__ == "__main__":
    unittest.main()
