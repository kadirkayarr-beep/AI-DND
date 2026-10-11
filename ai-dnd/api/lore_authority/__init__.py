"""Forgotten Realms canon authority package.

The production registry is built from the installed, explicitly reviewed
owner-provided source pack. Test fixtures remain opt-in and test-only.
"""

from .canon_events import apply_committed_world_canon
from .campaign_state import (
    EngineActionEvidence,
    apply_campaign_override,
    apply_faction_standing,
    bind_campaign,
    grant_npc_knowledge,
    record_player_discovery,
)
from .campaign_catalog import (
    CampaignStartCatalog,
    CampaignStartPack,
    InvalidCampaignStartError,
    StartingLocationOption,
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
    FactionStanding,
    ClaimType,
    EntityType,
    is_setting_place,
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
    fact_is_current,
    get_player_known_lore,
    normalize_name,
    resolve_entity,
    retrieve_lore_context,
    validate_lore_claim,
)
from .player_knowledge import read_player_knowledge, read_public_npc_label
from .pack_loader import (
    EXTRACTED_PACK,
    PRODUCTION_REGISTRY,
    PRODUCTION_START_CATALOG,
    REVIEWED_PACK,
    registry_for_pack,
)

__all__ = [
    "BindingStatus",
    "CampaignCanonOverride",
    "CampaignLoreState",
    "CampaignStartCatalog",
    "CampaignStartPack",
    "ClaimType",
    "ConflictResolution",
    "EngineActionEvidence",
    "EntityResolution",
    "EntityType",
    "IngestionPack",
    "InvalidCampaignStartError",
    "LoreClaimValidation",
    "LoreEdge",
    "LoreEntity",
    "LoreFact",
    "LoreLayer",
    "LoreRegistry",
    "PRODUCTION_REGISTRY",
    "PRODUCTION_START_CATALOG",
    "Relationship",
    "ResolutionStatus",
    "ReviewStatus",
    "SourceManifest",
    "SourceTier",
    "StartingLocationOption",
    "VisibilityScope",
    "EXTRACTED_PACK",
    "REVIEWED_PACK",
    "apply_campaign_override",
    "apply_committed_world_canon",
    "apply_faction_standing",
    "read_player_knowledge",
    "registry_for_pack",
    "bind_campaign",
    "build_reviewed_registry",
    "default_lore_registry",
    "fact_is_current",
    "get_player_known_lore",
    "is_setting_place",
    "grant_npc_knowledge",
    "normalize_name",
    "record_player_discovery",
    "resolve_entity",
    "retrieve_lore_context",
    "review_item",
    "validate_ingestion_pack",
    "validate_lore_claim",
]