"""Forgotten Realms canon authority package.

The production registry is intentionally empty until authorized, reviewed
source data is supplied. Test fixtures must be opt-in and remain test-only.
"""

from .campaign_state import (
    EngineActionEvidence,
    apply_campaign_override,
    bind_campaign,
    grant_npc_knowledge,
    record_player_discovery,
)
from .ingestion import (
    IngestionPack,
    build_reviewed_registry,
    review_item,
    validate_ingestion_pack,
)
from .models import (
    BindingStatus,
    CampaignCanonOverride,
    CampaignLoreState,
    ClaimType,
    EntityType,
    LoreEdge,
    LoreEntity,
    LoreFact,
    LoreLayer,
    Relationship,
    ResolutionStatus,
    ReviewStatus,
    SourceManifest,
    SourceTier,
    VisibilityScope,
)
from .registry import (
    ConflictResolution,
    EntityResolution,
    LoreClaimValidation,
    LoreRegistry,
    default_lore_registry,
    get_player_known_lore,
    normalize_name,
    resolve_entity,
    retrieve_lore_context,
    validate_lore_claim,
)

PRODUCTION_REGISTRY = default_lore_registry()

__all__ = [
    "BindingStatus",
    "CampaignCanonOverride",
    "CampaignLoreState",
    "ClaimType",
    "ConflictResolution",
    "EngineActionEvidence",
    "EntityResolution",
    "EntityType",
    "IngestionPack",
    "LoreClaimValidation",
    "LoreEdge",
    "LoreEntity",
    "LoreFact",
    "LoreLayer",
    "LoreRegistry",
    "PRODUCTION_REGISTRY",
    "Relationship",
    "ResolutionStatus",
    "ReviewStatus",
    "SourceManifest",
    "SourceTier",
    "VisibilityScope",
    "apply_campaign_override",
    "bind_campaign",
    "build_reviewed_registry",
    "default_lore_registry",
    "get_player_known_lore",
    "grant_npc_knowledge",
    "normalize_name",
    "record_player_discovery",
    "resolve_entity",
    "retrieve_lore_context",
    "review_item",
    "validate_ingestion_pack",
    "validate_lore_claim",
]