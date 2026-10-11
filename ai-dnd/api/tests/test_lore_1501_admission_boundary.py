"""Trusted admission boundary. Does not load a production pack."""

from __future__ import annotations

import unittest
from dataclasses import replace

from api.lore_authority.freeze_admission import (
    PINNED_SHA256,
    AdmittedRecord,
    TrustedProjection,
    admit_public_batch,
    load_freeze_evidence,
    load_pinned_snapshot,
    parse_json_object,
    projection_is_transform_ready,
)


class AdmissionBoundaryTests(unittest.TestCase):
    def test_pinned_snapshot_is_deeply_immutable_and_covers_every_pin(self):
        snapshot = load_pinned_snapshot()
        self.assertEqual(snapshot.evidence.integrity_errors, ())
        self.assertEqual(len(snapshot.permitted_claims), 95)
        self.assertEqual(set(PINNED_SHA256), set(PINNED_SHA256))
        with self.assertRaises(TypeError):
            snapshot.evidence.records["WD22-F-001"]["claim"] = "changed"

    def test_reduced_pin_set_admits_nothing(self):
        path, digest = next(iter(PINNED_SHA256.items()))
        evidence = load_freeze_evidence(expected_sha256={path: digest})
        self.assertTrue(evidence.integrity_errors)

    def test_duplicate_json_key_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_json_object(b'{"a": 1, "a": 2}', "sample.json")

    def test_public_batch_rejects_a_forged_projection(self):
        batch = admit_public_batch()
        self.assertEqual(batch.rejections, ())
        self.assertEqual(batch.integrity_errors, ())
        self.assertFalse(batch.production_authorized)
        self.assertEqual(len(batch.projections), 95)
        forged_record = AdmittedRecord(
            record_id="WD22-F-001",
            claim=batch.projections[0].record.claim,
            knowledge="public",
            applicability_1501="current_1501_candidate",
            inclusion_status="included_full",
            sources=batch.projections[0].record.sources,
            player_knowledge="not_granted",
            source_review_status="UNREVIEWED",
            source_production_status="DRAFT",
            production_authorized=False,
        )
        self.assertFalse(projection_is_transform_ready(forged_record, batch))
        forged = TrustedProjection(
            record=replace(batch.projections[0].record, claim=batch.projections[0].record.claim + " extra"),
            structure=batch.projections[0].structure,
            evidence_bundle_digest=batch.digest,
            batch_token=batch.token,
        )
        self.assertFalse(projection_is_transform_ready(forged, batch))
        with self.assertRaises(RuntimeError):
            type(batch)(
                batch.digest,
                batch.token,
                batch.projections[:-1] + (forged,),
                (),
                (),
                False,
            )

    def test_structure_comes_from_the_pinned_record(self):
        batch = admit_public_batch()
        by_id = {item.record.record_id: item for item in batch.projections}
        partial = by_id["WD22-F-015"]
        self.assertNotIn("abolish", partial.record.claim.casefold())
        self.assertIsNone(partial.structure.reviewed_mapping_id)
        self.assertEqual(partial.structure.kind, "fact")
        edge = next(item for item in batch.projections if item.structure.kind == "edge")
        self.assertTrue(edge.structure.relationship_type)
        self.assertTrue(edge.structure.source_entity_id)
        self.assertTrue(edge.structure.target_entity_id)
