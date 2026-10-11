"""Deterministic staged transform. Not a production pack loader."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .freeze_admission import TrustedBatch, projection_is_transform_ready
from .freeze_mapping import attach_cities, build_mapping_spec, mapping_digest
from .models import (
    MAX_FACT_VALUE_LENGTH,
    ClaimType,
    LoreFact,
    LoreLayer,
    ReviewStatus,
    SourceTier,
    VisibilityScope,
)


@dataclass(frozen=True)
class StagedFact:
    fact: LoreFact
    extraction_id: str
    payload_digest: str


@dataclass(frozen=True)
class StagedWithheld:
    extraction_id: str
    disposition: str
    reason: str


@dataclass(frozen=True)
class StagedPack:
    evidence_bundle_digest: str
    mapping_digest: str
    facts: tuple[StagedFact, ...]
    withheld: tuple[StagedWithheld, ...]
    production_authorized: bool = False

    def __post_init__(self) -> None:
        if self.production_authorized:
            raise RuntimeError("A staged freeze pack cannot authorize production.")


def _payload_digest(fact: LoreFact) -> str:
    encoded = json.dumps(fact.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cities_from_snapshot(batch: TrustedBatch) -> dict[str, str]:
    from .freeze_admission import load_pinned_snapshot

    snapshot = load_pinned_snapshot()
    cities: dict[str, str] = {}
    for item in batch.projections:
        city = snapshot.evidence.records[item.record.record_id].get("city")
        if isinstance(city, str):
            cities[item.record.record_id] = city
    return cities


def transform_admitted_batch(
    batch: TrustedBatch,
    mapping_spec: dict[str, Any] | None = None,
    *,
    only_ids: tuple[str, ...] | None = None,
) -> StagedPack:
    if batch.integrity_errors or batch.rejections or batch.production_authorized:
        raise ValueError("Transform refused an untrusted batch.")
    for item in batch.projections:
        if not projection_is_transform_ready(item, batch):
            raise ValueError("Transform refused a projection that is not batch-bound.")
    spec = mapping_spec if mapping_spec is not None else attach_cities(
        build_mapping_spec(batch),
        _cities_from_snapshot(batch),
    )
    if spec.get("mapping_digest") != mapping_digest(spec):
        raise ValueError("Mapping digest does not match the specification.")
    if spec.get("evidence_bundle_digest") != batch.digest:
        raise ValueError("Mapping is bound to a different evidence bundle.")
    rows = {row["extraction_id"]: row for row in spec["records"]}
    if len(rows) != len(spec["records"]) or set(rows) != {item.record.record_id for item in batch.projections}:
        raise ValueError("Mapping does not cover the trusted batch.")
    selected = set(only_ids) if only_ids is not None else set(rows)
    unknown = selected - set(rows)
    if unknown:
        raise ValueError("Mapping is missing a requested record.")
    facts: list[StagedFact] = []
    withheld: list[StagedWithheld] = []
    for item in batch.projections:
        record_id = item.record.record_id
        if record_id not in selected:
            continue
        row = rows[record_id]
        if row["permitted_claim"] != item.record.claim or row.get("lossy"):
            raise ValueError("Mapping claim does not match the trusted projection.")
        disposition = row["disposition"]
        if disposition == "mention_only":
            withheld.append(StagedWithheld(record_id, disposition, "name_mention_is_not_a_runtime_entity"))
            continue
        if disposition == "blocked_endpoint":
            withheld.append(StagedWithheld(record_id, disposition, "endpoint_is_not_a_runtime_entity"))
            continue
        if disposition != "runtime_fact":
            raise ValueError("Mapping disposition is unresolved.")
        claim = item.record.claim
        if len(claim) > MAX_FACT_VALUE_LENGTH:
            raise ValueError("Admitted claim exceeds the fact value limit.")
        subject = row.get("runtime_subject_id")
        predicate = row.get("runtime_predicate")
        if not isinstance(subject, str) or not isinstance(predicate, str):
            raise ValueError("Fact mapping is missing a subject or predicate.")
        if item.structure.kind != "fact":
            raise ValueError("A non-fact record was mapped as a runtime fact.")
        fact = LoreFact(
            fact_id=record_id,
            subject_id=subject,
            predicate=predicate,
            object_id_or_value=claim,
            claim_type=ClaimType.OBJECTIVE_CANON_FACT,
            authority_tier=SourceTier.TIER_1_CURRENT_CORE,
            source_id="source:fr-2025-freeze-staged",
            source_reference="pinned 2025 freeze citation",
            valid_from=None,
            valid_until=None,
            visibility=VisibilityScope.COMMON_KNOWLEDGE,
            region_scope=None,
            notes="",
            reality_layer=LoreLayer.OFFICIAL_SETTING_CANON,
            review_status=ReviewStatus.UNREVIEWED_EXTRACTED,
            temporal_scope="CURRENT_AT_1501_DR",
        )
        if EXCLUDED_SENTENCE in fact.object_id_or_value and record_id == "WD22-F-015":
            raise ValueError("Partial claim lost its scope.")
        facts.append(StagedFact(fact, record_id, _payload_digest(fact)))
    return StagedPack(batch.digest, spec["mapping_digest"], tuple(facts), tuple(withheld), False)


EXCLUDED_SENTENCE = "Castle Ward's absence from that sentence does not abolish it."
