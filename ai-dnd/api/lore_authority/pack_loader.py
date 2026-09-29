"""Load the explicitly reviewed owner-provided Neverwinter source pack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .campaign_catalog import CampaignStartCatalog
from .ingestion import (
    IngestionPack,
    build_reviewed_registry,
    review_item,
    validate_ingestion_pack,
)
from .models import EntityType, ReviewStatus
from .registry import LoreRegistry


PACK_DIRECTORY = Path(__file__).resolve().parent / "packs"
EXTRACTION_FILE = PACK_DIRECTORY / "neverwinter_the_north_v1.extraction.json"
REVIEW_FILE = PACK_DIRECTORY / "neverwinter_the_north_v1.review.json"
CATALOG_FILE = PACK_DIRECTORY / "installed_region_catalog.json"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot load authorized lore data: {path.name}.") from error


def load_production_pack() -> tuple[
    IngestionPack,
    IngestionPack,
    LoreRegistry,
    CampaignStartCatalog,
]:
    """Return unreviewed extraction, reviewed pack, registry, and start catalog."""
    extraction = _read_json(EXTRACTION_FILE)
    if (
        not isinstance(extraction, dict)
        or set(extraction) != {"extraction_status", "engine_review_status", "pack"}
        or extraction.get("extraction_status") != "REVIEW_REQUIRED"
        or extraction.get("engine_review_status") != "UNREVIEWED_EXTRACTED"
    ):
        raise ValueError("The official lore extraction is not review-gated.")
    extracted_pack = validate_ingestion_pack(extraction["pack"])

    review_log = _read_json(REVIEW_FILE)
    if (
        not isinstance(review_log, dict)
        or set(review_log) != {"reviewer_id", "review_note", "items"}
        or not isinstance(review_log["items"], list)
    ):
        raise ValueError("The official lore review log is invalid.")
    reviewer_id = review_log["reviewer_id"]
    review_note = review_log["review_note"]
    if (
        not isinstance(reviewer_id, str)
        or not reviewer_id.strip()
        or not isinstance(review_note, str)
        or not review_note.strip()
    ):
        raise ValueError("The official lore review identity or note is invalid.")

    expected = {
        (kind, item_id)
        for kind, records, id_field in (
            ("entity", extracted_pack.entities, "entity_id"),
            ("edge", extracted_pack.edges, "edge_id"),
            ("fact", extracted_pack.facts, "fact_id"),
        )
        for item_id in (getattr(record, id_field) for record in records)
    }
    decisions: set[tuple[str, str]] = set()
    reviewed_pack = extracted_pack
    for decision in review_log["items"]:
        if not isinstance(decision, dict) or set(decision) != {"item_type", "item_id"}:
            raise ValueError("An official lore review decision is invalid.")
        key = (decision["item_type"], decision["item_id"])
        if key in decisions or key not in expected:
            raise ValueError("The official lore review log has duplicate or unknown items.")
        decisions.add(key)
        reviewed_pack = review_item(
            reviewed_pack,
            item_type=key[0],
            item_id=key[1],
            reviewer_id=reviewer_id,
            review_note=review_note,
        )
    if decisions != expected:
        raise ValueError("Every extracted lore record needs an explicit review decision.")

    for collection in (
        reviewed_pack.entities,
        reviewed_pack.edges,
        reviewed_pack.facts,
    ):
        if any(item.review_status is not ReviewStatus.VERIFIED_CANON for item in collection):
            raise ValueError("The reviewed lore pack contains unreviewed records.")
    registry = build_reviewed_registry(reviewed_pack)

    catalog = CampaignStartCatalog.from_mapping(_read_json(CATALOG_FILE))
    for pack in catalog.packs:
        world = registry.entity(pack.world_id)
        region = registry.entity(pack.region_id)
        if world is None or world.entity_type is not EntityType.WORLD:
            raise ValueError("A start option references an unloaded setting entity.")
        if region is None or region.entity_type is not EntityType.REGION:
            raise ValueError("A start option references an unloaded region entity.")
        for location in pack.starting_locations:
            entity = registry.entity(location.entity_id)
            if entity is None or pack.region_id not in registry.geography_ancestors(
                {location.entity_id}
            ):
                raise ValueError("A start option lacks verified regional geography.")
    return extracted_pack, reviewed_pack, registry, catalog


(
    EXTRACTED_PACK,
    REVIEWED_PACK,
    PRODUCTION_REGISTRY,
    PRODUCTION_START_CATALOG,
) = load_production_pack()