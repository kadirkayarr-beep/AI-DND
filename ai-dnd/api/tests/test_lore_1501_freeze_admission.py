"""Admission guard for the 1501 freeze candidate. Not a production loader."""

from __future__ import annotations

import copy
import unittest
from dataclasses import asdict, fields, replace

from api.lore_authority.freeze_admission import (
    EXCLUDED_CASTLE_WARD_INFERENCE,
    PINNED_SHA256,
    V22_JSON,
    admit_record,
    canonical_proposal,
    load_freeze_evidence,
)
from api.lore_authority.models import LoreFact


class FreezeAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = load_freeze_evidence()

    def test_pinned_evidence_loads_and_admits_every_public_record(self):
        evidence = self.evidence
        self.assertEqual(evidence.integrity_errors, ())
        self.assertEqual(len(evidence.public_records), 95)
        self.assertTrue(evidence.restricted_ids.isdisjoint(evidence.public_records))
        for record_id in evidence.public_records:
            proposal = canonical_proposal(evidence, record_id)
            decision = admit_record(proposal, evidence)
            self.assertTrue(decision.admitted, decision.reasons)
            self.assertFalse(decision.production_authorized)
            self.assertEqual(decision.reasons, ())
            self.assertIsNotNone(decision.record)
            self.assertEqual(decision.record.claim, proposal["claim"])
            self.assertEqual(decision.record.player_knowledge, "not_granted")
            self.assertEqual(decision.record.source_review_status, "UNREVIEWED")
            self.assertFalse(decision.record.production_authorized)

    def test_restricted_record_is_rejected_when_relabeled_current_and_common(self):
        evidence = self.evidence
        record_id = "WD22-F-067"
        source = evidence.records[record_id]
        self.assertEqual(source["knowledge"], "restricted")
        self.assertEqual(source["applicability_1501"], "current_1501_candidate")
        decision = admit_record({
            "id": record_id,
            "claim": source["claim"],
            "knowledge": "public",
            "visibility": "COMMON_KNOWLEDGE",
            "temporal_scope": "CURRENT_AT_1501_DR",
            "applicability_1501": "current_1501_candidate",
            "sources": copy.deepcopy(evidence.public_records["WD22-F-001"]["sources"]),
        }, evidence)
        self.assertFalse(decision.admitted)
        self.assertIn("source_classification_not_public", decision.reasons)
        self.assertIn("not_in_public_freeze_manifest", decision.reasons)

    def test_supplemental_record_is_rejected_when_relabeled_current(self):
        evidence = self.evidence
        record_id = "WD22-F-002-1"
        source = evidence.records[record_id]
        self.assertEqual(source["applicability_1501"], "supplemental_unconfirmed_1501")
        decision = admit_record({
            "id": record_id,
            "claim": source["claim"],
            "knowledge": "public",
            "visibility": "COMMON_KNOWLEDGE",
            "temporal_scope": "CURRENT_AT_1501_DR",
            "applicability_1501": "current_1501_candidate",
            "sources": copy.deepcopy(evidence.public_records["WD22-F-001"]["sources"]),
        }, evidence)
        self.assertFalse(decision.admitted)
        self.assertIn("applicability_not_verified_current", decision.reasons)
        self.assertNotIn("source_classification_not_public", decision.reasons)

    def test_missing_source_applicability_is_not_replaced_by_runtime_scope(self):
        evidence = self.evidence
        record_id = "WD22-F-001"
        records = copy.deepcopy(dict(evidence.records))
        records[record_id]["applicability_1501"] = None
        damaged = replace(evidence, records=records)
        proposal = canonical_proposal(evidence, record_id)
        proposal["temporal_scope"] = "CURRENT_AT_1501_DR"
        proposal["visibility"] = "COMMON_KNOWLEDGE"
        decision = admit_record(proposal, damaged)
        self.assertFalse(decision.admitted)
        self.assertIn("missing_current_applicability", decision.reasons)

    def test_runtime_visibility_does_not_decide_a_verified_public_record(self):
        evidence = self.evidence
        proposal = canonical_proposal(evidence, "WD22-F-001")
        proposal["visibility"] = "DM_SECRET"
        proposal["temporal_scope"] = None
        decision = admit_record(proposal, evidence)
        self.assertTrue(decision.admitted, decision.reasons)
        self.assertFalse(decision.production_authorized)
        self.assertIsNotNone(decision.record)
        projected_fields = {item.name for item in fields(decision.record)}
        self.assertNotIn("visibility", projected_fields)
        self.assertNotIn("temporal_scope", projected_fields)
        self.assertNotEqual(decision.record.claim, "DM_SECRET")

    def test_altered_claim_text_is_rejected(self):
        evidence = self.evidence
        proposal = canonical_proposal(evidence, "WD22-F-001")
        proposal["claim"] = proposal["claim"] + " Unapproved addition."
        decision = admit_record(proposal, evidence)
        self.assertFalse(decision.admitted)
        self.assertIsNone(decision.record)
        self.assertIn("claim_mismatch", decision.reasons)

    def test_unknown_id_is_rejected(self):
        decision = admit_record({
            "id": "WD22-NO-SUCH",
            "claim": "A city that is not in the freeze.",
            "visibility": "COMMON_KNOWLEDGE",
            "temporal_scope": "CURRENT_AT_1501_DR",
            "sources": [{"source_title": "Missing", "source_sha256": "0" * 64, "pdf_pages": [1]}],
        }, self.evidence)
        self.assertFalse(decision.admitted)
        self.assertIn("not_in_public_freeze_manifest", decision.reasons)

    def test_f015_printed_ward_list_is_admitted(self):
        evidence = self.evidence
        proposal = canonical_proposal(evidence, "WD22-F-015")
        self.assertNotIn("Castle Ward", proposal["claim"])
        self.assertNotIn(EXCLUDED_CASTLE_WARD_INFERENCE, proposal["claim"])
        decision = admit_record(proposal, evidence)
        self.assertTrue(decision.admitted, decision.reasons)

    def test_f015_rejects_reintroduced_castle_ward_inference(self):
        evidence = self.evidence
        proposal = canonical_proposal(evidence, "WD22-F-015")
        proposal["claim"] = evidence.records["WD22-F-015"]["claim"]
        self.assertIn(EXCLUDED_CASTLE_WARD_INFERENCE, proposal["claim"])
        decision = admit_record(proposal, evidence)
        self.assertFalse(decision.admitted)
        self.assertIn("excluded_castle_ward_inference", decision.reasons)
        self.assertIn("claim_mismatch", decision.reasons)

    def test_owner_existence_sentence_is_not_admitted_as_the_2025_claim(self):
        evidence = self.evidence
        proposal = canonical_proposal(evidence, "WD22-F-015")
        proposal["claim"] = evidence.owner_statement
        proposal["decision_class"] = "OWNER-APPROVED CONTINUITY DECISION"
        decision = admit_record(proposal, evidence)
        self.assertFalse(decision.admitted)
        self.assertIn("owner_continuity_not_source_fact", decision.reasons)
        self.assertNotIn(evidence.owner_statement, evidence.records["WD22-F-015"]["claim"])

    def test_missing_sources_and_wrong_hash_fail_closed(self):
        evidence = self.evidence
        missing = canonical_proposal(evidence, "BG22-F-001")
        del missing["sources"]
        missing_decision = admit_record(missing, evidence)
        self.assertFalse(missing_decision.admitted)
        self.assertIn("missing_sources", missing_decision.reasons)

        wrong = canonical_proposal(evidence, "BG22-F-001")
        wrong["sources"][0]["source_sha256"] = "a" * 64
        wrong_decision = admit_record(wrong, evidence)
        self.assertFalse(wrong_decision.admitted)
        self.assertIn("source_hash_mismatch", wrong_decision.reasons)

    def test_hash_pin_mismatch_admits_nothing(self):
        pins = dict(PINNED_SHA256)
        pins[V22_JSON] = "0" * 64
        evidence = load_freeze_evidence(expected_sha256=pins)
        self.assertTrue(evidence.integrity_errors)
        decision = admit_record({
            "id": "WD22-F-001",
            "claim": "Waterdeep is named in the cited passage.",
            "visibility": "COMMON_KNOWLEDGE",
            "temporal_scope": "CURRENT_AT_1501_DR",
        }, evidence)
        self.assertFalse(decision.admitted)
        self.assertIn("freeze_integrity", decision.reasons)
        self.assertFalse(decision.production_authorized)

    def test_historical_record_is_not_promoted_by_a_current_label(self):
        evidence = self.evidence
        record_id = "WD22-F-004"
        source = evidence.records[record_id]
        self.assertEqual(source["applicability_1501"], "historical_setting")
        decision = admit_record({
            "id": record_id,
            "claim": source["claim"],
            "visibility": "COMMON_KNOWLEDGE",
            "temporal_scope": "CURRENT_AT_1501_DR",
            "applicability_1501": "current_1501_candidate",
        }, evidence)
        self.assertFalse(decision.admitted)
        self.assertIsNone(decision.record)
        self.assertIn("applicability_not_verified_current", decision.reasons)

    def test_tampered_runtime_metadata_cannot_enter_the_projection(self):
        evidence = self.evidence
        record_id = "WD22-F-001"
        proposal = canonical_proposal(evidence, record_id)
        permitted = proposal["claim"]
        proposal["visibility"] = "COMMON_KNOWLEDGE"
        proposal["temporal_scope"] = "CURRENT_AT_1501_DR"
        proposal["authority_tier"] = "TIER_1_CURRENT_CORE"
        proposal["review_status"] = "VERIFIED_CANON"
        proposal["provenance"] = "caller-supplied"
        decision = admit_record(proposal, evidence)
        self.assertTrue(decision.admitted, decision.reasons)
        projected = decision.record
        self.assertIsNotNone(projected)
        payload = asdict(projected)
        self.assertTrue({
            "visibility",
            "temporal_scope",
            "authority_tier",
            "provenance",
            "review_status",
        }.isdisjoint(payload))
        self.assertEqual(projected.claim, permitted)
        self.assertEqual(projected.knowledge, "public")
        self.assertEqual(projected.applicability_1501, "current_1501_candidate")
        self.assertEqual(projected.player_knowledge, "not_granted")
        self.assertEqual(projected.source_review_status, "UNREVIEWED")
        self.assertFalse(projected.production_authorized)
        proposal["claim"] = permitted + " laundered"
        proposal["sources"][0]["source_sha256"] = "b" * 64
        proposal["visibility"] = "DM_SECRET"
        self.assertEqual(projected.claim, permitted)
        self.assertNotEqual(projected.sources[0].source_sha256, "b" * 64)
        self.assertNotIn("DM_SECRET", payload.values())
        with self.assertRaises(ValueError):
            LoreFact.from_mapping(payload)

        tampered = canonical_proposal(evidence, record_id)
        tampered["claim"] = permitted + " Unapproved addition."
        tampered["visibility"] = "COMMON_KNOWLEDGE"
        tampered["temporal_scope"] = "CURRENT_AT_1501_DR"
        rejected = admit_record(tampered, evidence)
        self.assertFalse(rejected.admitted)
        self.assertIsNone(rejected.record)
        self.assertNotIn(tampered["claim"], rejected.reasons)

        owned = canonical_proposal(evidence, "WD22-F-015")
        owned["provenance"] = "OWNER-APPROVED CONTINUITY DECISION"
        owned["visibility"] = "COMMON_KNOWLEDGE"
        owned_decision = admit_record(owned, evidence)
        self.assertFalse(owned_decision.admitted)
        self.assertIsNone(owned_decision.record)
        self.assertIn("owner_continuity_not_source_fact", owned_decision.reasons)


if __name__ == "__main__":
    unittest.main()
