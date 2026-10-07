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
INDEX_FILE = PACK_DIRECTORY / "pack_index.json"
EXTRACTION_FILE = PACK_DIRECTORY / "neverwinter_the_north_v1.extraction.json"
REVIEW_FILE = PACK_DIRECTORY / "neverwinter_the_north_v1.review.json"
CATALOG_FILE = PACK_DIRECTORY / "installed_region_catalog.json"
_VERIFIED_COVERAGE = frozenset({"VERIFIED", "VERIFIED_PARTIAL"})


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot load authorized lore data: {path.name}.") from error


def load_pack_index() -> list[dict[str, Any]]:
    """Reviewed pack list. A second region is another row, not another engine."""
    payload = _read_json(INDEX_FILE)
    packs = payload.get("packs") if isinstance(payload, dict) else None
    if not isinstance(packs, list) or not packs:
        raise ValueError("The lore pack index is invalid.")
    seen: set[str] = set()
    for entry in packs:
        if not isinstance(entry, dict):
            raise ValueError("A lore pack index row is invalid.")
        pack_id = entry.get("pack_id")
        coverage = entry.get("coverage_status")
        if not isinstance(pack_id, str) or pack_id in seen or not isinstance(coverage, str):
            raise ValueError("A lore pack index row is invalid.")
        seen.add(pack_id)
        if coverage in _VERIFIED_COVERAGE:
            if not isinstance(entry.get("extraction"), str) or not isinstance(entry.get("review"), str):
                raise ValueError("A verified lore pack is missing its files.")
        elif coverage != "INCOMPLETE":
            raise ValueError("A lore pack coverage status is invalid.")
    return packs


def registry_for_pack(pack_id: str) -> LoreRegistry:
    """Load one indexed pack. An incomplete pack answers unknown."""
    from .registry import default_lore_registry

    for entry in load_pack_index():
        if entry["pack_id"] != pack_id:
            continue
        if entry["coverage_status"] not in _VERIFIED_COVERAGE:
            return default_lore_registry()
        return _load_reviewed_files(
            PACK_DIRECTORY / entry["extraction"],
            PACK_DIRECTORY / entry["review"],
        )[2]
    raise ValueError("The requested lore pack is not indexed.")


def _load_reviewed_files(
    extraction_file: Path,
    review_file: Path,
) -> tuple[IngestionPack, IngestionPack, LoreRegistry]:
    """Return the unreviewed pack, the reviewed pack, and its registry."""
    extraction = _read_json(extraction_file)
    if (
        not isinstance(extraction, dict)
        or set(extraction) != {"extraction_status", "engine_review_status", "pack"}
        or extraction.get("extraction_status") != "REVIEW_REQUIRED"
        or extraction.get("engine_review_status") != "UNREVIEWED_EXTRACTED"
    ):
        raise ValueError("The official lore extraction is not review-gated.")
    extracted_pack = validate_ingestion_pack(extraction["pack"])

    review_log = _read_json(review_file)
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
    return extracted_pack, reviewed_pack, registry


def load_production_pack() -> tuple[
    IngestionPack,
    IngestionPack,
    LoreRegistry,
    CampaignStartCatalog,
]:
    """Return unreviewed extraction, reviewed pack, registry, and start catalog."""
    indexed = load_pack_index()
    verified = [entry for entry in indexed if entry["coverage_status"] in _VERIFIED_COVERAGE]
    if not verified:
        raise ValueError("The lore pack index has no verified pack.")
    primary = verified[0]
    extracted_pack, reviewed_pack, registry = _load_reviewed_files(
        PACK_DIRECTORY / primary["extraction"],
        PACK_DIRECTORY / primary["review"],
    )
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