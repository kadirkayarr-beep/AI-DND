"""Trusted admission boundary. Does not load a production pack."""

from __future__ import annotations

import unittest

from api.lore_authority.freeze_admission import (
    PINNED_SHA256,
    load_freeze_evidence,
    load_pinned_snapshot,
    parse_json_object,
)
from api.tests.guard_bound import EVIDENCE_READ, guard_bound


class AdmissionBoundaryTests(unittest.TestCase):
    @guard_bound(EVIDENCE_READ)
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
