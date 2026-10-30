"""B02 unique-method ledger contract; synthetic data only, no game/model/server calls."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools" / "acceptance"))
import evidence as owner

SOURCE_SHA = "78b380384e70832156d2d9aa2785192bbbbdb74b"


def audit_shaped_results():
    """Synthetic ledger shaped like the 26 Oct 2026 audit counts (not a re-run of it).

    2825 first executions, 52 repeats of passing methods and 5 later passes that
    close earlier network-blocked failures: 2882 executions in total.
    """
    final = (["FAIL"] * 11) + (["SKIP"] * 2) + ["BLOCKED"] + (["PASS"] * 2811)
    ids = [f"api.tests.test_synthetic.Case.test_{index:04d}" for index in range(len(final))]
    closing = ids[-5:]
    results = []
    for method_id, status in zip(ids, final):
        first = "FAIL" if method_id in closing else status
        results.append({"id": method_id, "status": first})
    results.extend({"id": method_id, "status": "PASS"} for method_id in ids[20:72])
    results.extend({"id": method_id, "status": "PASS"} for method_id in closing)
    return results, closing


def valid_record(**overrides):
    record = {
        "sourceSHA": SOURCE_SHA,
        "treeState": {"clean": True, "changed_paths": []},
        "runtimeSHA": "UNKNOWN",
        "os": "Windows",
        "runtime": "Python 3.14.2",
        "model": None,
        "column": "unit",
        "command": "python -m unittest api.tests.test_roadmap_b02 -v",
        "cwd": "ai-dnd",
        "exitCode": 0,
        "testID": "api.tests.test_roadmap_b02.RoadmapB02Tests.test_x",
        "status": "PASS",
        "fixtureOwner": None,
        "mock": False,
        "realDependencies": ["python"],
        "rawDigest": hashlib.sha256(b"raw").hexdigest(),
        "artifactDigest": None,
        "startedAt": "2026-10-26T10:00:00Z",
        "endedAt": "2026-10-26T10:00:01Z",
        "reviewer": None,
    }
    record.update(overrides)
    return record


class RoadmapB02Tests(unittest.TestCase):
    def observe(self):
        """Test-local observations measured from the real owner, never from a copy of it."""
        results, _ = audit_shaped_results()
        ledger = owner.deduplicate_results(results)
        columns = owner.summarize_columns([
            valid_record(column="browser", mock=True, fixtureOwner="fetch-mock",
                         realDependencies=[], status="PASS"),
        ])
        return {
            "executions": ledger["executions"],
            "unique_methods": ledger["unique_methods"],
            "statuses": ledger["statuses"],
            "lint_status": columns["lint"]["status"],
            "browser_provenance": columns["browser"]["provenance"],
        }

    def test_unique_method_ledger_preserves_status(self):
        obs = self.observe()
        assert obs["executions"] == 2882
        assert obs["unique_methods"] == 2825
        assert obs["statuses"] == {"PASS": 2811, "FAIL": 11, "SKIP": 2, "BLOCKED": 1}
        assert obs["lint_status"] == "UNCONFIGURED"
        self.assertEqual(obs["browser_provenance"], "FIXTURE")

    def test_same_qualified_id_twice_is_one_method(self):
        ledger = owner.deduplicate_results([
            {"id": "pkg.Case.test_a", "status": "PASS"},
            {"id": "pkg.Case.test_a", "status": "PASS"},
        ])
        self.assertEqual((ledger["executions"], ledger["unique_methods"]), (2, 1))
        self.assertEqual(ledger["statuses"], {"PASS": 1})
        self.assertEqual(ledger["conflicts"], [])

    def test_closed_failure_is_visible_and_later_failure_is_not_masked(self):
        results, closing = audit_shaped_results()
        ledger = owner.deduplicate_results(results)
        self.assertEqual(sorted(ledger["conflicts"]), sorted(closing))
        self.assertEqual(ledger["methods"][closing[0]]["statuses"], ["FAIL", "PASS"])
        regressed = owner.deduplicate_results([
            {"id": "pkg.Case.test_b", "status": "PASS"},
            {"id": "pkg.Case.test_b", "status": "FAIL"},
        ])
        self.assertEqual(regressed["statuses"], {"FAIL": 1})
        self.assertEqual(regressed["conflicts"], ["pkg.Case.test_b"])

    def test_expected_denial_marker_never_hides_a_failure(self):
        ledger = owner.deduplicate_results([
            {"id": "pkg.Case.test_c", "status": "FAIL", "expected_denial": True},
        ])
        self.assertEqual(ledger["statuses"], {"FAIL": 1})

    def test_unknown_status_or_missing_id_is_rejected(self):
        with self.assertRaises(ValueError):
            owner.deduplicate_results([{"id": "pkg.Case.test_d", "status": "OK"}])
        with self.assertRaises(ValueError):
            owner.deduplicate_results([{"id": "", "status": "PASS"}])

    def test_harness_outcomes_are_normalized_and_raw_evidence_is_kept(self):
        run = {"exit_status": 1, "per_test": [
            {"id": "pkg.Case.test_a", "outcome": "pass"},
            {"id": "pkg.Case.test_b", "outcome": "failure"},
            {"id": "pkg.Case.test_c", "outcome": "error"},
            {"id": "pkg.Case.test_d", "outcome": "skip"},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "output.log"
            log.write_bytes(b"raw harness output\n")
            normalized = owner.normalize_harness_run(run, log)
        self.assertEqual([row["status"] for row in normalized["results"]],
                         ["PASS", "FAIL", "FAIL", "SKIP"])
        self.assertEqual(normalized["exit_status"], 1)
        self.assertEqual(normalized["raw_log_sha256"],
                         hashlib.sha256(b"raw harness output\n").hexdigest())
        for outcome in ("expected_failure", "unexpected_success", "running"):
            with self.assertRaises(ValueError):
                owner.normalize_harness_run(
                    {"exit_status": 0, "per_test": [{"id": "pkg.Case.test_e", "outcome": outcome}]},
                    None)

    def test_columns_are_separate_and_missing_ones_are_not_pass(self):
        columns = owner.summarize_columns([valid_record(column="unit")])
        self.assertEqual(set(columns), set(owner.COLUMNS))
        self.assertEqual(columns["unit"], {"status": "PASS", "provenance": "REAL"})
        self.assertEqual(columns["lint"]["status"], "UNCONFIGURED")
        for name in set(owner.COLUMNS) - {"unit", "lint"}:
            self.assertEqual(columns[name]["status"], "NOT_RUN", name)

    def test_mixed_provenance_and_worst_status_in_a_column(self):
        columns = owner.summarize_columns([
            valid_record(column="http", status="PASS"),
            valid_record(column="http", status="FAIL", exitCode=1, mock=True,
                         fixtureOwner="fake"),
        ])
        self.assertEqual(columns["http"], {"status": "FAIL", "provenance": "MIXED"})

    def test_record_evidence_appends_valid_records_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(owner.record_evidence(valid_record(), root))
            owner.record_evidence(valid_record(testID="second"), root)
            lines = (root / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line)["testID"] for line in lines],
                             ["api.tests.test_roadmap_b02.RoadmapB02Tests.test_x", "second"])
            for bad in (
                valid_record(status="PASS", exitCode=1),
                valid_record(status="PASS", exitCode=None),
                valid_record(status="MAYBE"),
                valid_record(column="telepathy"),
                valid_record(sourceSHA="abc"),
                valid_record(runtimeSHA="f" * 40),
            ):
                with self.assertRaises(ValueError, msg=bad):
                    owner.record_evidence(bad, root)
            partial = valid_record()
            del partial["command"]
            with self.assertRaises(ValueError):
                owner.record_evidence(partial, root)
            self.assertEqual(
                len((root / "evidence.jsonl").read_text(encoding="utf-8").splitlines()), 2)

    def test_fixture_record_may_differ_from_runtime_but_is_not_real_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            record = valid_record(column="browser", mock=True, fixtureOwner="fetch-mock",
                                  runtimeSHA="f" * 40, realDependencies=[])
            owner.record_evidence(record, Path(directory))
        self.assertEqual(owner.provenance(record), "FIXTURE")
        self.assertFalse(owner.satisfies_real_acceptance(record))
        real = valid_record(column="http", runtimeSHA=SOURCE_SHA)
        self.assertTrue(owner.satisfies_real_acceptance(real))
        self.assertFalse(owner.satisfies_real_acceptance(valid_record(column="http")))

    def test_real_acceptance_needs_dependencies_reviewer_and_model(self):
        human = valid_record(column="human_acceptance", runtimeSHA=SOURCE_SHA, reviewer="Kadir")
        self.assertTrue(owner.satisfies_real_acceptance(human))
        self.assertFalse(owner.satisfies_real_acceptance({**human, "reviewer": None}))
        model = valid_record(column="model", runtimeSHA=SOURCE_SHA,
                             model={"artifact": "synthetic-model", "settings": {}})
        self.assertTrue(owner.satisfies_real_acceptance(model))
        self.assertFalse(owner.satisfies_real_acceptance({**model, "model": None}))
        self.assertEqual(owner.provenance({"mock": False, "fixtureOwner": ""}), "FIXTURE")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):  # real evidence must name what was real
                owner.record_evidence({**human, "realDependencies": []}, Path(directory))
            with self.assertRaises(ValueError):  # empty owner string is not "no fixture"
                owner.record_evidence({**human, "fixtureOwner": ""}, Path(directory))

    def test_unknown_real_dependencies_can_be_recorded_only_as_not_proven(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for status in ("BLOCKED", "NOT_RUN", "SKIP", "UNCONFIGURED"):
                owner.record_evidence(
                    valid_record(status=status, exitCode=None, realDependencies=[]), root)
            for status, code in (("PASS", 0), ("FAIL", 1)):
                with self.assertRaises(ValueError, msg=status):
                    owner.record_evidence(
                        valid_record(status=status, exitCode=code, realDependencies=[]), root)
            self.assertEqual(
                len((root / "evidence.jsonl").read_text(encoding="utf-8").splitlines()), 4)
        blocked = valid_record(column="http", status="BLOCKED", exitCode=None,
                               realDependencies=[], runtimeSHA=SOURCE_SHA)
        self.assertFalse(owner.satisfies_real_acceptance(blocked))

    def test_malformed_suite_event_is_a_value_error(self):
        with self.assertRaises(ValueError):
            owner.normalize_harness_run({
                "exit_status": 0, "per_test": [{"id": "pkg.Case.test_a", "outcome": "pass"}],
                "suite_events": ["setUpClass failed"]}, None)

    def test_columns_never_merge_different_sources(self):
        with self.assertRaises(ValueError):
            owner.summarize_columns([
                valid_record(column="http", sourceSHA="a" * 40),
                valid_record(column="http"),
            ])

    def test_incomplete_or_inconsistent_harness_runs_are_not_clean(self):
        passing = [{"id": "pkg.Case.test_a", "outcome": "pass"}]
        for run in ({"exit_status": 1},
                    {"exit_status": 1, "per_test": passing},
                    {"exit_status": None, "per_test": passing},
                    {"exit_status": 0, "per_test": []}):
            with self.assertRaises(ValueError, msg=run):
                owner.normalize_harness_run(run, None)
        broken = owner.normalize_harness_run({
            "exit_status": 1, "per_test": passing,
            "suite_events": [{"id": "pkg.Case.setUpClass", "outcome": "error"}]}, None)
        self.assertEqual([(row["id"], row["status"]) for row in broken["results"]],
                         [("pkg.Case.test_a", "PASS"), ("pkg.Case.setUpClass", "FAIL")])

    def test_failure_is_closed_only_by_a_later_pass(self):
        def final(*statuses):
            return owner.deduplicate_results(
                [{"id": "pkg.Case.test_f", "status": status} for status in statuses])
        self.assertEqual(final("FAIL", "SKIP")["statuses"], {"FAIL": 1})
        self.assertEqual(final("BLOCKED", "SKIP")["statuses"], {"BLOCKED": 1})
        self.assertEqual(final("FAIL", "BLOCKED")["statuses"], {"FAIL": 1})
        closed = final("FAIL", "PASS")
        self.assertEqual(closed["statuses"], {"PASS": 1})
        self.assertEqual(closed["closed_failures"], ["pkg.Case.test_f"])
        self.assertEqual(final("PASS", "SKIP")["statuses"], {"SKIP": 1})
        self.assertEqual(final("PASS", "PASS")["closed_failures"], [])

    def test_record_types_and_unknown_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for bad in (valid_record(model="x"), valid_record(realDependencies=[1]),
                        valid_record(fixtureOwner=5), valid_record(reviewer=7),
                        {**valid_record(), "note": "extra"}):
                with self.assertRaises(ValueError, msg=bad):
                    owner.record_evidence(bad, root)
            self.assertFalse((root / "evidence.jsonl").exists())

    def test_schema_file_matches_owner_vocabulary(self):
        schema = json.loads((REPO / "docs" / "acceptance" / "evidence.schema.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), set(owner.REQUIRED_FIELDS))
        self.assertEqual(schema["properties"]["status"]["enum"], list(owner.STATUSES))
        self.assertEqual(schema["properties"]["column"]["enum"], list(owner.COLUMNS))
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["properties"]["sourceSHA"]["pattern"], f"^{owner.SHA1.pattern}$")
        self.assertEqual(schema["properties"]["rawDigest"]["pattern"], f"^{owner.SHA256.pattern}$")


if __name__ == "__main__":
    unittest.main()
