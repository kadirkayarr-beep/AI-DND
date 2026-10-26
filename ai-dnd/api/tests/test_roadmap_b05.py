"""B05 historical crosswalk contract; reads the repository crosswalk only, no game/model/server calls."""
import hashlib
import json
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[3]
CROSSWALK = REPO / "docs" / "acceptance" / "historical-crosswalk.json"
sys.path.insert(0, str(REPO / "tools" / "acceptance"))
import historical_crosswalk as owner
import evidence as evidence_owner

OPPORTUNITIES = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "C1", "C2", "C3", "C4"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RoadmapB05Tests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(CROSSWALK.read_text(encoding="utf-8"))
        self.rows = self.doc["rows"]
        self.task_ids = set(self.doc["task_index_ids"])

    def observe(self):
        """Test-local observations measured from the real crosswalk and the real owner, never from a copy."""
        return {
            "lr_crosswalk": [r for r in self.rows if r["kind"] == "lr"],
            "g_crosswalk": [r for r in self.rows if r["kind"] == "g"],
            "research_opportunities": [r for r in self.rows if r["kind"] == "opportunity"],
            "historical_pass_closed_full_release": owner.historical_pass_closes_full_release(self.doc),
        }

    def test_historical_gate_never_closes_full_release(self):
        obs = self.observe()
        assert len(obs["lr_crosswalk"]) == 6
        assert len(obs["g_crosswalk"]) == 6
        assert len(obs["research_opportunities"]) == 16
        assert obs["historical_pass_closed_full_release"] is False
        self.assertEqual([r["historical_id"] for r in obs["lr_crosswalk"]], [f"LR0{n}" for n in range(6)])
        self.assertEqual([r["historical_id"] for r in obs["g_crosswalk"]], [f"G{n}" for n in range(1, 7)])
        self.assertEqual([r["historical_id"] for r in obs["research_opportunities"]], OPPORTUNITIES)
        for row in self.rows:
            self.assertIs(row["not_full_release"], True, row["historical_id"])
            self.assertNotEqual(row["status"], "PASS", row["historical_id"])
        self.assertIs(self.doc["historical_gates"]["closes_full_release"], False)
        self.assertEqual(self.doc["historical_gates"]["legacy_gate_count_reported"], 33)

    def test_closing_claims_are_refused_and_never_become_pass(self):
        index = [{"id": "B01"}, {"id": "B02"}]
        base = {"historical_id": "LRX", "kind": "lr", "target_spec": "B01–B02", "note": "x",
                "source_ref": {"file": "f.md"}, "source_title": "Title", "source_verification": "REPO_HEADING_VERIFIED"}
        with self.assertRaises(ValueError):
            owner.crosswalk_history([{**base, "closes_full_release": True}], index)
        passed = owner.crosswalk_history([{**base, "historical_status": "PASS", "historical_claims": {"gates_closed": 33}}], index)[0]
        self.assertEqual(passed["status"], "MAPPED")
        self.assertIs(passed["not_full_release"], True)
        self.assertEqual(passed["historical_claims"]["gates_closed"], 33)
        gates = {"closes_full_release": False}
        self.assertTrue(owner.historical_pass_closes_full_release({"rows": [{**passed, "not_full_release": False}], "historical_gates": gates}))
        self.assertTrue(owner.historical_pass_closes_full_release({"rows": [{**passed, "status": "PASS"}], "historical_gates": gates}))
        self.assertTrue(owner.historical_pass_closes_full_release({"rows": [passed], "historical_gates": {"closes_full_release": True}}))
        self.assertTrue(owner.historical_pass_closes_full_release({"rows": [passed]}))
        self.assertFalse(owner.historical_pass_closes_full_release({"rows": [passed], "historical_gates": gates}))

    def test_malformed_entries_and_weak_sources_are_not_promoted(self):
        index = [{"id": "B01"}, {"id": "B02"}, {"id": "C01"}]
        base = {"historical_id": "LRQ", "kind": "lr", "target_spec": "B01", "note": "n",
                "source_ref": {"file": "f"}, "source_title": "T", "source_verification": "REPO_HEADING_VERIFIED"}
        with self.assertRaises(ValueError):
            owner.crosswalk_history([{**base, "kind": "wish"}], index)
        with self.assertRaises(ValueError):
            owner.crosswalk_history([{**base, "kind": "opportunity", "is_scope_decision": True}], index)
        with self.assertRaises(ValueError):
            owner.expand_task_refs("B01–C03")
        row = owner.crosswalk_history([{**base, "not_full_release": False}], index)[0]
        self.assertIs(row["not_full_release"], True)
        weak = owner.crosswalk_history([{**base, "source_verification": "PLAN_PACKAGE_RECORD_ONLY"}], index)[0]
        self.assertEqual(weak["status"], "MAPPED_UNVERIFIED_SOURCE")
        opportunity = owner.crosswalk_history([{**base, "kind": "opportunity", "disposition": "uygulanır", "reason": "r"}], index)[0]
        self.assertIs(opportunity["is_scope_decision"], False)

    def test_unknown_source_stays_unknown_without_an_invented_title(self):
        index = [{"id": "B01"}]
        row = owner.crosswalk_history([{"historical_id": "LRZ", "kind": "lr", "target_spec": "B01", "note": "n",
                                        "source_ref": None, "source_title": "Invented Title"}], index)[0]
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertIsNone(row["source_title"])
        self.assertIsNone(row["source_ref"])
        self.assertIs(row["not_full_release"], True)

    def test_task_references_expand_and_must_exist(self):
        self.assertEqual(owner.expand_task_refs("B01–B03"), ["B01", "B02", "B03"])
        self.assertEqual(owner.expand_task_refs("B01-B03,D03"), ["B01", "B02", "B03", "D03"])
        self.assertEqual(len(owner.expand_task_refs("K01–K07,C01–C22,X01–X04")), 7 + 22 + 4)
        with self.assertRaises(ValueError):
            owner.expand_task_refs("B03–B01")
        with self.assertRaises(ValueError):
            owner.expand_task_refs("not a ref")
        missing = owner.crosswalk_history([{"historical_id": "LRY", "kind": "lr", "target_spec": "B01,Z99", "note": "n",
                                            "source_ref": {"file": "f"}, "source_title": "T", "source_verification": "REPO_HEADING_VERIFIED"}],
                                          [{"id": "B01"}])[0]
        self.assertEqual(missing["status"], "UNKNOWN_TARGET")
        self.assertEqual(missing["missing_targets"], ["Z99"])
        for row in self.rows:
            self.assertEqual(row["missing_targets"], [], row["historical_id"])
            self.assertTrue(row["target_tasks"], row["historical_id"])
            self.assertTrue(set(row["target_tasks"]) <= self.task_ids, row["historical_id"])
            self.assertEqual(row["target_tasks"], owner.expand_task_refs(row["target_spec"]), row["historical_id"])
        self.assertEqual(len(self.task_ids), 94)

    def test_lr_rows_are_anchored_in_the_repo_history_document(self):
        lr_rows = [r for r in self.rows if r["kind"] == "lr"]
        for row in lr_rows:
            self.assertEqual(row["status"], "MAPPED", row["historical_id"])
            self.assertEqual(row["source_verification"], "REPO_HEADING_VERIFIED")
            ref = row["source_ref"]
            path = REPO / ref["file"]
            self.assertEqual(sha256(path), ref["file_sha256"])
            line = path.read_text(encoding="utf-8").splitlines()[ref["line"] - 1]
            self.assertEqual(line.lstrip("# ").strip(), ref["heading"])
            self.assertIn(row["historical_id"], ref["heading"])
            self.assertEqual(row["source_title"], ref["heading"])
        titles = {r["historical_id"]: r["package_title"] for r in lr_rows}
        for key, expected in (("LR01", "The Open Road"), ("LR02", "Living Souls"), ("LR03", "Steel & Sorcery"),
                              ("LR04", "A World Alive"), ("LR05", "Beyond the Horizon")):
            self.assertEqual(titles[key], expected)
            self.assertIn(expected, next(r for r in lr_rows if r["historical_id"] == key)["source_title"])

    def test_g_rows_and_opportunities_are_labeled_package_record_only(self):
        for row in self.rows:
            if row["kind"] == "lr":
                continue
            self.assertEqual(row["status"], "MAPPED_UNVERIFIED_SOURCE", row["historical_id"])
            self.assertEqual(row["source_verification"], "PLAN_PACKAGE_RECORD_ONLY")
            self.assertTrue(row["source_title"].strip())
            self.assertTrue(row["source_ref"]["original_document"].strip())
            self.assertFalse(row["source_ref"]["original_opened_in_b05"])
        files = self.doc["source_package_files"]
        self.assertEqual(files["traceability/historical-crosswalk.json"], "a38b299cd0b7b9b53d4589cca35a639989e68c789d5e71642f04c54b8bc646e6")
        self.assertEqual(files["traceability/task-index.json"], "db4fe1da8c267449f8835cb6ce7a50bea4bf9edee7aa3970b6afbc5382c57dd5")

    def test_each_opportunity_carries_a_disposition_and_reason_and_is_not_a_scope_decision(self):
        allowed = {"uygulanır", "korunur", "kısmen_uygulanır_kısmen_sonraya_ayrılır", "sonraya_ayrılır"}
        for row in self.rows:
            if row["kind"] != "opportunity":
                continue
            self.assertIn(row["disposition"], allowed, row["historical_id"])
            self.assertTrue(row["reason"].strip(), row["historical_id"])
            self.assertIs(row["is_scope_decision"], False, row["historical_id"])
        partial = {r["historical_id"] for r in self.rows if r.get("disposition") == "kısmen_uygulanır_kısmen_sonraya_ayrılır"}
        self.assertEqual(partial, {"B2", "B3", "B6", "B7", "C1", "C4"})

    def test_research_tools_are_not_dependencies(self):
        boundary = self.doc["tool_boundary"]
        self.assertIs(boundary["tools_are_dependencies"], False)
        self.assertIs(boundary["automatic_install"], False)
        self.assertIs(boundary["personal_campaign_transfer"], False)
        for tool in ("Jina", "Open5e", "SRD", "Freesound", "DiceBear", "Openverse", "Groq", "Gemini"):
            self.assertIn(tool, boundary["named_tools"])
        for row in self.rows:
            self.assertFalse({"jina", "open5e", "groq", "gemini"} & {t.lower() for t in row["target_tasks"]})

    def test_links_to_b02_evidence_kinds_and_b04_scope_count_hold(self):
        manifest = json.loads((REPO / "content" / "manifest" / "phb2024.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["rows"]), 728)
        self.assertEqual(self.doc["linked_checks"]["b04_manifest_rows"], 728)
        self.assertEqual(self.doc["linked_checks"]["b02_evidence_columns"], list(evidence_owner.COLUMNS))
        targets_b04 = {r["historical_id"] for r in self.rows if "B04" in r["target_tasks"]}
        self.assertTrue({"B2", "B3", "C4"} <= targets_b04)
        self.assertNotIn("PASS", {r["status"] for r in self.rows})


if __name__ == "__main__":
    unittest.main()
