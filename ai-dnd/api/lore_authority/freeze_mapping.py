"""Reviewed dispositions for the 95-record public freeze.

Entity mentions stay mention_only until a source record carries a reviewed
runtime type. This module does not invent offices, locations, or life status.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .freeze_admission import TrustedBatch
from .models import MAX_FACT_VALUE_LENGTH, MAX_REFERENCE_LENGTH


LONG_CLAIM_IDS = ("BG22-F-005", "BG22-F-010", "BG22-F-015")
LONG_CLAIM_DECISION = {
    "mode": "separate_fact_value_limit",
    "max_fact_value_length": MAX_FACT_VALUE_LENGTH,
    "max_reference_length": MAX_REFERENCE_LENGTH,
    "no_truncation": True,
    "records": list(LONG_CLAIM_IDS),
}
SUBJECT_IDS = {
    "waterdeep": "fr:city:waterdeep",
    "baldurs_gate": "fr:city:baldurs_gate",
    "shared": "fr:world:forgotten_realms",
}
VERTICAL_SLICE_IDS = (
    "WD22-F-015",
    "WD22-F-001",
    "WD22-E-001",
    "WD22-X-002",
    "BG22-F-005",
    "BG22-F-001",
    "FR22-F-001",
)


def _predicate(record_id: str) -> str:
    return record_id.lower().replace("-", "_")


def build_mapping_spec(batch: TrustedBatch) -> dict[str, Any]:
    if batch.integrity_errors or batch.rejections or not batch.projections:
        raise ValueError("Mapping requires a trusted public batch.")
    rows: list[dict[str, Any]] = []
    for item in batch.projections:
        record = item.record
        kind = item.structure.kind
        city = None
        if kind == "entity":
            disposition = "mention_only"
        elif kind == "fact":
            disposition = "runtime_fact"
        elif kind == "edge":
            disposition = "blocked_endpoint"
        else:
            disposition = "unresolved"
        row = {
            "extraction_id": record.record_id,
            "disposition": disposition,
            "permitted_claim": record.claim,
            "inclusion_status": record.inclusion_status,
            "kind": kind,
            "support_ids": list(item.structure.support_ids),
            "source_entity_id": item.structure.source_entity_id,
            "target_entity_id": item.structure.target_entity_id,
            "relationship_type": item.structure.relationship_type,
            "entity_type": None,
            "runtime_subject_id": None,
            "runtime_predicate": None,
            "lossy": False,
        }
        if disposition == "runtime_fact":
            row["runtime_predicate"] = _predicate(record.record_id)
        rows.append(row)
    spec = {
        "schema": "phase8-mapping-spec-v1",
        "evidence_bundle_digest": batch.digest,
        "long_claim_decision": LONG_CLAIM_DECISION,
        "subject_ids": SUBJECT_IDS,
        "subject_note": (
            "Subject ids are existing world identities used only inside an "
            "isolated staged registry. They are not freeze entities and they "
            "are not written into the Neverwinter pack."
        ),
        "vertical_slice_ids": list(VERTICAL_SLICE_IDS),
        "page_verified_ids": [],
        "turkish_renderings": {},
        "records": rows,
    }
    spec["mapping_digest"] = mapping_digest(spec)
    return spec


def mapping_digest(spec: dict[str, Any]) -> str:
    body = {key: value for key, value in spec.items() if key != "mapping_digest"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def attach_cities(spec: dict[str, Any], cities: dict[str, str]) -> dict[str, Any]:
    """Bind fact subjects from the pinned record city field."""
    updated = []
    for row in spec["records"]:
        copied = dict(row)
        city = cities.get(row["extraction_id"])
        if row["disposition"] == "runtime_fact":
            subject = SUBJECT_IDS.get(city or "")
            if subject is None:
                copied["disposition"] = "unresolved"
            else:
                copied["runtime_subject_id"] = subject
        updated.append(copied)
    spec = dict(spec)
    spec["records"] = updated
    spec["mapping_digest"] = mapping_digest(spec)
    return spec
