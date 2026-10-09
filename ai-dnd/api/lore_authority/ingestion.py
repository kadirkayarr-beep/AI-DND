"""Strict, data-only lore-pack validation and explicit human review helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .models import (
    ClaimType,
    LoreEdge,
    LoreEntity,
    LoreFact,
    LoreLayer,
    ReviewStatus,
    SourceManifest,
    SourceTier,
)
from .registry import LoreRegistry


MAX_PACK_BYTES = 2 * 1024 * 1024
MAX_SOURCES = 200
MAX_ENTITIES = 25_000
MAX_EDGES = 50_000
MAX_FACTS = 100_000


@dataclass(frozen=True)
class IngestionPack:
    schema_version: int
    sources: tuple[SourceManifest, ...]
    entities: tuple[LoreEntity, ...]
    edges: tuple[LoreEdge, ...]
    facts: tuple[LoreFact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sources": [item.to_dict() for item in self.sources],
            "entities": [item.to_dict() for item in self.entities],
            "edges": [item.to_dict() for item in self.edges],
            "facts": [item.to_dict() for item in self.facts],
        }


def validate_ingestion_pack(value: Any) -> IngestionPack:
    """Validate a JSON-shaped facts pack without promoting any fact to canon."""
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "sources",
        "entities",
        "edges",
        "facts",
    }:
        raise ValueError("Lore ingestion pack fields are invalid.")
    if value["schema_version"] != 1 or type(value["schema_version"]) is not int:
        raise ValueError("Lore ingestion pack schema_version is invalid.")
    try:
        size = len(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Lore ingestion pack is not valid JSON data.") from None
    if size > MAX_PACK_BYTES:
        raise ValueError("Lore ingestion pack is too large.")

    sources = _parse_list(value["sources"], "sources", MAX_SOURCES, SourceManifest.from_mapping)
    entities = _parse_list(value["entities"], "entities", MAX_ENTITIES, LoreEntity.from_mapping)
    edges = _parse_list(value["edges"], "edges", MAX_EDGES, LoreEdge.from_mapping)
    facts = _parse_list(value["facts"], "facts", MAX_FACTS, LoreFact.from_mapping)
    source_map = _unique_map(sources, "source_id", "source")
    entity_map = _unique_map(entities, "entity_id", "entity")
    _unique_map(edges, "edge_id", "edge")
    _unique_map(facts, "fact_id", "fact")

    for source in sources:
        if source.source_tier in {SourceTier.TIER_5_PROCEDURAL, SourceTier.TEST_FIXTURE}:
            raise ValueError("Procedural and test sources cannot enter the official lore pack.")
    for entity in entities:
        _must_remain_unreviewed(entity.review_status, f"entity {entity.entity_id}")
        _check_source(source_map, entity.source_id, entity.authority_tier, entity.entity_id)
    for edge in edges:
        _must_remain_unreviewed(edge.review_status, f"edge {edge.edge_id}")
        _check_source(source_map, edge.source_id, edge.authority_tier, edge.edge_id)
        if edge.subject_id not in entity_map or edge.object_id not in entity_map:
            raise ValueError(f"Edge {edge.edge_id} references an unknown entity.")
    for fact in facts:
        _must_remain_unreviewed(fact.review_status, f"fact {fact.fact_id}")
        _check_source(source_map, fact.source_id, fact.authority_tier, fact.fact_id)
        if fact.subject_id not in entity_map:
            raise ValueError(f"Fact {fact.fact_id} references an unknown subject.")
        if fact.reality_layer is not LoreLayer.OFFICIAL_SETTING_CANON:
            raise ValueError(
                f"Non-official fact {fact.fact_id} cannot enter the official lore pack."
            )
        if fact.claim_type in {ClaimType.PROCEDURAL_FACT, ClaimType.NARRATIVE_TEXTURE}:
            raise ValueError(
                f"Procedural or narrative fact {fact.fact_id} cannot enter the official lore pack."
            )
    return IngestionPack(1, sources, entities, edges, facts)


def review_item(
    pack: IngestionPack,
    *,
    item_type: str,
    item_id: str,
    reviewer_id: str,
    review_note: str,
) -> IngestionPack:
    """Promote one extracted record only through an explicit human review call."""
    reviewer_id = _nonempty_text(reviewer_id, "reviewer_id", 128)
    review_note = _nonempty_text(review_note, "review_note", 280)
    collections = {
        "entity": ("entities", pack.entities, "entity_id"),
        "edge": ("edges", pack.edges, "edge_id"),
        "fact": ("facts", pack.facts, "fact_id"),
    }
    if item_type not in collections:
        raise ValueError("Lore review item_type is invalid.")
    field_name, records, id_field = collections[item_type]
    source_map = _unique_map(pack.sources, "source_id", "source")
    replaced_records: list[Any] = []
    found = False
    for record in records:
        if getattr(record, id_field) != item_id:
            replaced_records.append(record)
            continue
        found = True
        if record.review_status is not ReviewStatus.UNREVIEWED_EXTRACTED:
            raise ValueError("Only unreviewed extracted lore can be reviewed.")
        source = source_map[record.source_id]
        if (
            source.authority_status.casefold() != "verified"
            or source.owner_access_status.casefold() != "authorized"
        ):
            raise ValueError("Source authority and owner access must be verified first.")
        # Reviewer identity and note are required for an auditable, deliberate
        # promotion. The note is not added to public lore or source prose.
        _ = (reviewer_id, review_note)
        replaced_records.append(replace(record, review_status=ReviewStatus.VERIFIED_CANON))
    if not found:
        raise ValueError("Lore review item was not found.")
    updated = {
        "sources": pack.sources,
        "entities": pack.entities,
        "edges": pack.edges,
        "facts": pack.facts,
    }
    updated[field_name] = tuple(replaced_records)
    return IngestionPack(
        pack.schema_version,
        updated["sources"],
        updated["entities"],
        updated["edges"],
        updated["facts"],
    )


def build_reviewed_registry(pack: IngestionPack) -> LoreRegistry:
    """Build an immutable registry from human-reviewed records only."""
    return LoreRegistry(
        sources=pack.sources,
        entities=tuple(
            item for item in pack.entities
            if item.review_status is ReviewStatus.VERIFIED_CANON
        ),
        edges=tuple(
            item for item in pack.edges
            if item.review_status is ReviewStatus.VERIFIED_CANON
        ),
        facts=tuple(
            item for item in pack.facts
            if item.review_status is ReviewStatus.VERIFIED_CANON
        ),
    )


def _parse_list(value: Any, label: str, maximum: int, parser: Any) -> tuple[Any, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"Lore ingestion {label} are invalid.")
    return tuple(parser(item) for item in value)


def _unique_map(items: tuple[Any, ...], field: str, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        item_id = getattr(item, field)
        if item_id in result:
            raise ValueError(f"Duplicate {label} ID: {item_id}.")
        result[item_id] = item
    return result


def _check_source(
    sources: Mapping[str, SourceManifest],
    source_id: str,
    authority_tier: SourceTier,
    record_id: str,
) -> None:
    source = sources.get(source_id)
    if source is None:
        raise ValueError(f"Lore record {record_id} has no registered source.")
    if (
        authority_tier is SourceTier.OWNER_APPROVED_CONTINUITY
        or source.source_tier is SourceTier.OWNER_APPROVED_CONTINUITY
    ):
        raise ValueError("Owner continuity cannot enter an official lore pack.")
    if source.source_tier is not authority_tier:
        raise ValueError(f"Lore record {record_id} source tier is inconsistent.")


def _must_remain_unreviewed(status: ReviewStatus, label: str) -> None:
    if status is not ReviewStatus.UNREVIEWED_EXTRACTED:
        raise ValueError(f"Imported {label} cannot self-assert verified canon.")


def _nonempty_text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} is invalid.")
    return value.strip()