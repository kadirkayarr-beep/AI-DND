"""Validated, provenance-bearing data contracts for the Lore Authority.

The official registry is static application data. Campaign lore state contains
only references and campaign-owned facts; it must never duplicate source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


MAX_ID_LENGTH = 128
MAX_NAME_LENGTH = 160
MAX_REFERENCE_LENGTH = 240
# Separate from source references. Covers the longest admitted claim (409)
# without raising citation limits. The 12 KiB retrieval cap still wins.
MAX_FACT_VALUE_LENGTH = 1024
MAX_NOTE_LENGTH = 280
MAX_CAMPAIGN_FACT_IDS = 2_000
MAX_CAMPAIGN_OVERRIDES = 500
MAX_PROCEDURAL_REFERENCES = 1_000
MAX_NPCS_WITH_KNOWLEDGE = 500
MAX_FACTS_PER_NPC = 500
MAX_FACTION_ROWS = 64
LORE_PAYLOAD_VERSION = 2

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,127}$")


class LoreLayer(str, Enum):
    OFFICIAL_SETTING_CANON = "OFFICIAL_SETTING_CANON"
    CAMPAIGN_CANON = "CAMPAIGN_CANON"
    PROCEDURAL_LOCAL_FICTION = "PROCEDURAL_LOCAL_FICTION"
    NARRATIVE_TEXTURE = "NARRATIVE_TEXTURE"


class SourceTier(str, Enum):
    TIER_1_CURRENT_CORE = "TIER_1_CURRENT_CORE"
    TIER_2_OFFICIAL_5E = "TIER_2_OFFICIAL_5E"
    TIER_3_OLDER_OFFICIAL = "TIER_3_OLDER_OFFICIAL"
    TIER_4_OFFICIAL_FICTION_GAMES = "TIER_4_OFFICIAL_FICTION_GAMES"
    TIER_5_PROCEDURAL = "TIER_5_PROCEDURAL"
    LEGACY_OFFICIAL = "LEGACY_OFFICIAL"
    TEST_FIXTURE = "TEST_FIXTURE"
    OWNER_APPROVED_CONTINUITY = "OWNER_APPROVED_CONTINUITY"

    @property
    def rank(self) -> int:
        if self is SourceTier.OWNER_APPROVED_CONTINUITY:
            raise ValueError("Owner continuity is outside official source ranking.")
        return {
            SourceTier.TIER_1_CURRENT_CORE: 1,
            SourceTier.TIER_2_OFFICIAL_5E: 2,
            SourceTier.TIER_3_OLDER_OFFICIAL: 3,
            SourceTier.LEGACY_OFFICIAL: 3,
            SourceTier.TIER_4_OFFICIAL_FICTION_GAMES: 4,
            SourceTier.TIER_5_PROCEDURAL: 5,
            SourceTier.TEST_FIXTURE: 99,
        }[self]


class ClaimType(str, Enum):
    OBJECTIVE_CANON_FACT = "OBJECTIVE_CANON_FACT"
    CANONICAL_PUBLIC_BELIEF = "CANONICAL_PUBLIC_BELIEF"
    CANONICAL_RUMOR = "CANONICAL_RUMOR"
    CANONICAL_LEGEND = "CANONICAL_LEGEND"
    HISTORICAL_FACT = "HISTORICAL_FACT"
    SECRET_DM_LEVEL_FACT = "SECRET_DM_LEVEL_FACT"
    PROCEDURAL_FACT = "PROCEDURAL_FACT"
    NARRATIVE_TEXTURE = "NARRATIVE_TEXTURE"
    CANONICAL_LOCAL_BELIEF = "CANONICAL_LOCAL_BELIEF"
    ADVENTURE_POSSIBILITY = "ADVENTURE_POSSIBILITY"


class VisibilityScope(str, Enum):
    COMMON_KNOWLEDGE = "COMMON_KNOWLEDGE"
    REGIONAL_KNOWLEDGE = "REGIONAL_KNOWLEDGE"
    SPECIALIST_KNOWLEDGE = "SPECIALIST_KNOWLEDGE"
    DISCOVERABLE_SECRET = "DISCOVERABLE_SECRET"
    DM_SECRET = "DM_SECRET"


class EntityType(str, Enum):
    WORLD = "WORLD"
    CONTINENT = "CONTINENT"
    REGION = "REGION"
    KINGDOM_NATION = "KINGDOM_NATION"
    CITY = "CITY"
    TOWN = "TOWN"
    VILLAGE = "VILLAGE"
    DISTRICT = "DISTRICT"
    LANDMARK = "LANDMARK"
    ROAD_ROUTE = "ROAD_ROUTE"
    WILDERNESS = "WILDERNESS"
    FOREST = "FOREST"
    MOUNTAIN_RANGE = "MOUNTAIN_RANGE"
    RIVER = "RIVER"
    SEA = "SEA"
    ISLAND = "ISLAND"
    INN_TAVERN = "INN_TAVERN"
    TEMPLE = "TEMPLE"
    FACTION = "FACTION"
    DEITY = "DEITY"
    RELIGION_CHURCH = "RELIGION_CHURCH"
    PLANE = "PLANE"
    CANONICAL_NPC = "CANONICAL_NPC"
    HISTORICAL_EVENT = "HISTORICAL_EVENT"
    CULTURE_PEOPLE = "CULTURE_PEOPLE"


PLACE_ENTITY_TYPES = frozenset({
    EntityType.CONTINENT,
    EntityType.REGION,
    EntityType.KINGDOM_NATION,
    EntityType.CITY,
    EntityType.TOWN,
    EntityType.VILLAGE,
    EntityType.DISTRICT,
    EntityType.LANDMARK,
    EntityType.ROAD_ROUTE,
    EntityType.WILDERNESS,
    EntityType.FOREST,
    EntityType.MOUNTAIN_RANGE,
    EntityType.RIVER,
    EntityType.SEA,
    EntityType.ISLAND,
    EntityType.INN_TAVERN,
    EntityType.TEMPLE,
})


def is_setting_place(entity: "LoreEntity | None") -> bool:
    """True when the entity can be a current setting location."""
    return entity is not None and entity.entity_type in PLACE_ENTITY_TYPES


class Relationship(str, Enum):
    LOCATED_IN = "located_in"
    PART_OF = "part_of"
    NEAR = "near"
    NORTH_OF = "north_of"
    SOUTH_OF = "south_of"
    EAST_OF = "east_of"
    WEST_OF = "west_of"
    CONNECTED_TO = "connected_to"
    ROAD_TO = "road_to"
    RIVER_THROUGH = "river_through"
    COASTAL_TO = "coastal_to"
    DISTRICT_OF = "district_of"
    COMMANDS = "commands"
    DIRECTS = "directs"
    DISTINCT_OFFICE = "distinct_office"
    ENTRANCE_TO = "entrance_to"
    HEADQUARTERED_AT = "headquartered_at"
    HOLDS_OFFICE = "holds_office"
    LEADS = "leads"
    MEETS_IN = "meets_in"
    OUTSIDE_ROUTINE_PATROL = "outside_routine_patrol"
    PORT_ON = "port_on"
    RULES_BESIDE = "rules_beside"
    WATCH_PRECEDES_IN_UPPER_CITY = "watch_precedes_in_upper_city"


class ReviewStatus(str, Enum):
    UNREVIEWED_EXTRACTED = "UNREVIEWED_EXTRACTED"
    VERIFIED_CANON = "VERIFIED_CANON"
    TEST_ONLY = "TEST_ONLY"


class BindingStatus(str, Enum):
    LEGACY_UNBOUND = "LEGACY_UNBOUND"
    LEGACY_PROCEDURAL_WORLD = "LEGACY_PROCEDURAL_WORLD"
    BOUND = "BOUND"


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN_UNLOADED = "UNKNOWN_UNLOADED"
    CANON_CONFLICT_UNRESOLVED = "CANON_CONFLICT_UNRESOLVED"
    CONTRADICTED = "CONTRADICTED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"


def _strict_mapping(
    value: Any,
    *,
    required: set[str],
    optional: set[str] | None = None,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    optional = optional or set()
    keys = set(value)
    if keys - required - optional or required - keys:
        raise ValueError(f"{label} fields are invalid.")
    return value


def _text(value: Any, label: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{label} is invalid.")
    if not allow_empty and not value.strip():
        raise ValueError(f"{label} is invalid.")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise ValueError(f"{label} contains control characters.")
    return value.strip()


def _id(value: Any, label: str) -> str:
    parsed = _text(value, label, MAX_ID_LENGTH)
    if not _ID_RE.fullmatch(parsed):
        raise ValueError(f"{label} is invalid.")
    return parsed


def _enum(enum_type: type[Enum], value: Any, label: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} is invalid.") from None


def _official_tier(value: Any, label: str) -> SourceTier:
    """Pack JSON may not install owner continuity as an official source."""
    parsed = _enum(SourceTier, value, label)
    if parsed is SourceTier.OWNER_APPROVED_CONTINUITY:
        raise ValueError(f"{label} cannot use owner continuity as an official source.")
    return parsed


def _optional_text(value: Any, label: str, limit: int) -> str | None:
    if value is None:
        return None
    return _text(value, label, limit)


def _string_list(value: Any, label: str, *, maximum: int = 64) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} is invalid.")
    items = tuple(_text(item, label, MAX_NAME_LENGTH) for item in value)
    if len({item.casefold() for item in items}) != len(items):
        raise ValueError(f"{label} contains duplicates.")
    return items


@dataclass(frozen=True)
class SourceManifest:
    source_id: str
    title: str
    publisher: str
    publication_year: int | None
    edition_family: str
    source_tier: SourceTier
    setting: str
    region_scope: str | None
    authority_status: str
    owner_access_status: str
    notes: str

    @classmethod
    def from_mapping(cls, value: Any) -> "SourceManifest":
        data = _strict_mapping(
            value,
            required={
                "source_id",
                "title",
                "publisher",
                "publication_year",
                "edition_family",
                "source_tier",
                "setting",
                "region_scope",
                "authority_status",
                "owner_access_status",
                "notes",
            },
            label="Source manifest entry",
        )
        year = data["publication_year"]
        if year is not None and (type(year) is not int or not 0 <= year <= 9999):
            raise ValueError("Source publication_year is invalid.")
        return cls(
            source_id=_id(data["source_id"], "Source source_id"),
            title=_text(data["title"], "Source title", MAX_NAME_LENGTH),
            publisher=_text(data["publisher"], "Source publisher", MAX_NAME_LENGTH),
            publication_year=year,
            edition_family=_text(
                data["edition_family"], "Source edition_family", MAX_NAME_LENGTH
            ),
            source_tier=_official_tier(data["source_tier"], "Source source_tier"),
            setting=_text(data["setting"], "Source setting", MAX_NAME_LENGTH),
            region_scope=_optional_text(
                data["region_scope"], "Source region_scope", MAX_NAME_LENGTH
            ),
            authority_status=_text(
                data["authority_status"], "Source authority_status", 64
            ),
            owner_access_status=_text(
                data["owner_access_status"], "Source owner_access_status", 64
            ),
            notes=_text(data["notes"], "Source notes", MAX_NOTE_LENGTH, allow_empty=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "publisher": self.publisher,
            "publication_year": self.publication_year,
            "edition_family": self.edition_family,
            "source_tier": self.source_tier.value,
            "setting": self.setting,
            "region_scope": self.region_scope,
            "authority_status": self.authority_status,
            "owner_access_status": self.owner_access_status,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LoreEntity:
    entity_id: str
    entity_type: EntityType
    canonical_name: str
    aliases: tuple[str, ...]
    setting: str
    region_scope: str | None
    source_id: str
    source_reference: str
    authority_tier: SourceTier
    review_status: ReviewStatus
    valid_from: str | None = None
    valid_until: str | None = None
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: Any) -> "LoreEntity":
        data = _strict_mapping(
            value,
            required={
                "entity_id",
                "entity_type",
                "canonical_name",
                "aliases",
                "setting",
                "region_scope",
                "source_id",
                "source_reference",
                "authority_tier",
                "review_status",
                "valid_from",
                "valid_until",
                "notes",
            },
            label="Lore entity",
        )
        return cls(
            entity_id=_id(data["entity_id"], "Entity entity_id"),
            entity_type=_enum(EntityType, data["entity_type"], "Entity entity_type"),
            canonical_name=_text(
                data["canonical_name"], "Entity canonical_name", MAX_NAME_LENGTH
            ),
            aliases=_string_list(data["aliases"], "Entity aliases"),
            setting=_text(data["setting"], "Entity setting", MAX_NAME_LENGTH),
            region_scope=_optional_text(
                data["region_scope"], "Entity region_scope", MAX_NAME_LENGTH
            ),
            source_id=_id(data["source_id"], "Entity source_id"),
            source_reference=_text(
                data["source_reference"], "Entity source_reference", MAX_REFERENCE_LENGTH
            ),
            authority_tier=_official_tier(data["authority_tier"], "Entity authority_tier"),
            review_status=_enum(
                ReviewStatus, data["review_status"], "Entity review_status"
            ),
            valid_from=_optional_text(data["valid_from"], "Entity valid_from", 80),
            valid_until=_optional_text(data["valid_until"], "Entity valid_until", 80),
            notes=_text(data["notes"], "Entity notes", MAX_NOTE_LENGTH, allow_empty=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type.value,
            "canonical_name": self.canonical_name,
            "aliases": list(self.aliases),
            "setting": self.setting,
            "region_scope": self.region_scope,
            "source_id": self.source_id,
            "source_reference": self.source_reference,
            "authority_tier": self.authority_tier.value,
            "review_status": self.review_status.value,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LoreFact:
    fact_id: str
    subject_id: str
    predicate: str
    object_id_or_value: str | int | bool
    claim_type: ClaimType
    authority_tier: SourceTier
    source_id: str
    source_reference: str
    valid_from: str | None
    valid_until: str | None
    visibility: VisibilityScope
    region_scope: str | None
    notes: str
    reality_layer: LoreLayer
    review_status: ReviewStatus
    temporal_scope: str | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> "LoreFact":
        data = _strict_mapping(
            value,
            required={
                "fact_id",
                "subject_id",
                "predicate",
                "object_id_or_value",
                "claim_type",
                "authority_tier",
                "source_id",
                "source_reference",
                "valid_from",
                "valid_until",
                "visibility",
                "region_scope",
                "notes",
                "reality_layer",
                "review_status",
            },
            optional={"temporal_scope"},
            label="Lore fact",
        )
        value_field = data["object_id_or_value"]
        if type(value_field) not in {str, int, bool}:
            raise ValueError("Lore fact object_id_or_value must be a scalar.")
        if isinstance(value_field, str):
            value_field = _text(
                value_field, "Lore fact object_id_or_value", MAX_FACT_VALUE_LENGTH
            )
        predicate = _text(data["predicate"], "Lore fact predicate", 100)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", predicate):
            raise ValueError("Lore fact predicate is invalid.")
        return cls(
            fact_id=_id(data["fact_id"], "Lore fact fact_id"),
            subject_id=_id(data["subject_id"], "Lore fact subject_id"),
            predicate=predicate,
            object_id_or_value=value_field,
            claim_type=_enum(ClaimType, data["claim_type"], "Lore fact claim_type"),
            authority_tier=_official_tier(data["authority_tier"], "Lore fact authority_tier"),
            source_id=_id(data["source_id"], "Lore fact source_id"),
            source_reference=_text(
                data["source_reference"], "Lore fact source_reference", MAX_REFERENCE_LENGTH
            ),
            valid_from=_optional_text(data["valid_from"], "Lore fact valid_from", 80),
            valid_until=_optional_text(data["valid_until"], "Lore fact valid_until", 80),
            visibility=_enum(VisibilityScope, data["visibility"], "Lore fact visibility"),
            region_scope=_optional_text(
                data["region_scope"], "Lore fact region_scope", MAX_NAME_LENGTH
            ),
            notes=_text(data["notes"], "Lore fact notes", MAX_NOTE_LENGTH, allow_empty=True),
            reality_layer=_enum(
                LoreLayer, data["reality_layer"], "Lore fact reality_layer"
            ),
            review_status=_enum(
                ReviewStatus, data["review_status"], "Lore fact review_status"
            ),
            temporal_scope=_optional_text(
                data.get("temporal_scope"), "Lore fact temporal_scope", 80
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_id_or_value": self.object_id_or_value,
            "claim_type": self.claim_type.value,
            "authority_tier": self.authority_tier.value,
            "source_id": self.source_id,
            "source_reference": self.source_reference,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "visibility": self.visibility.value,
            "region_scope": self.region_scope,
            "notes": self.notes,
            "reality_layer": self.reality_layer.value,
            "review_status": self.review_status.value,
            "temporal_scope": self.temporal_scope,
        }


@dataclass(frozen=True)
class LoreEdge:
    edge_id: str
    subject_id: str
    predicate: Relationship
    object_id: str
    source_id: str
    source_reference: str
    authority_tier: SourceTier
    review_status: ReviewStatus
    valid_from: str | None = None
    valid_until: str | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> "LoreEdge":
        data = _strict_mapping(
            value,
            required={
                "edge_id",
                "subject_id",
                "predicate",
                "object_id",
                "source_id",
                "source_reference",
                "authority_tier",
                "review_status",
                "valid_from",
                "valid_until",
            },
            label="Lore graph edge",
        )
        return cls(
            edge_id=_id(data["edge_id"], "Edge edge_id"),
            subject_id=_id(data["subject_id"], "Edge subject_id"),
            predicate=_enum(Relationship, data["predicate"], "Edge predicate"),
            object_id=_id(data["object_id"], "Edge object_id"),
            source_id=_id(data["source_id"], "Edge source_id"),
            source_reference=_text(
                data["source_reference"], "Edge source_reference", MAX_REFERENCE_LENGTH
            ),
            authority_tier=_enum(
                SourceTier, data["authority_tier"], "Edge authority_tier"
            ),
            review_status=_enum(
                ReviewStatus, data["review_status"], "Edge review_status"
            ),
            valid_from=_optional_text(data["valid_from"], "Edge valid_from", 80),
            valid_until=_optional_text(data["valid_until"], "Edge valid_until", 80),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate.value,
            "object_id": self.object_id,
            "source_id": self.source_id,
            "source_reference": self.source_reference,
            "authority_tier": self.authority_tier.value,
            "review_status": self.review_status.value,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
        }


@dataclass(frozen=True)
class CampaignCanonOverride:
    override_id: str
    subject_id: str
    predicate: str
    object_id_or_value: str | int | bool
    source_action_id: str
    created_turn: int
    notes: str = ""

    @classmethod
    def from_mapping(cls, value: Any) -> "CampaignCanonOverride":
        data = _strict_mapping(
            value,
            required={
                "override_id",
                "subject_id",
                "predicate",
                "object_id_or_value",
                "source_action_id",
                "created_turn",
                "notes",
            },
            label="Campaign canon override",
        )
        object_value = data["object_id_or_value"]
        if type(object_value) not in {str, int, bool}:
            raise ValueError("Campaign override value must be a scalar.")
        if isinstance(object_value, str):
            object_value = _text(
                object_value, "Campaign override object_id_or_value", MAX_REFERENCE_LENGTH
            )
        turn = data["created_turn"]
        if type(turn) is not int or turn < 0:
            raise ValueError("Campaign override created_turn is invalid.")
        predicate = _text(data["predicate"], "Campaign override predicate", 100)
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", predicate):
            raise ValueError("Campaign override predicate is invalid.")
        return cls(
            override_id=_id(data["override_id"], "Override override_id"),
            subject_id=_id(data["subject_id"], "Override subject_id"),
            predicate=predicate,
            object_id_or_value=object_value,
            source_action_id=_id(data["source_action_id"], "Override source_action_id"),
            created_turn=turn,
            notes=_text(data["notes"], "Override notes", MAX_NOTE_LENGTH, allow_empty=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "override_id": self.override_id,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "object_id_or_value": self.object_id_or_value,
            "source_action_id": self.source_action_id,
            "created_turn": self.created_turn,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class FactionStanding:
    """Campaign-local standing. Hidden rows are not a public fact."""

    faction_id: str
    standing: int
    known_to_player: bool
    local_presence: bool
    source_action_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "faction_id": self.faction_id,
            "standing": self.standing,
            "known_to_player": self.known_to_player,
            "local_presence": self.local_presence,
            "source_action_id": self.source_action_id,
        }


@dataclass(frozen=True)
class CampaignLoreState:
    """Small campaign-owned references; never contains static sourcebook lore."""

    binding_status: BindingStatus = BindingStatus.LEGACY_UNBOUND
    setting_profile: str | None = None
    world_id: str | None = None
    epoch_id: str | None = None
    region_id: str | None = None
    current_location_entity_id: str | None = None
    region_pack_id: str | None = None
    starting_location_entity_id: str | None = None
    player_known_fact_ids: tuple[str, ...] = ()
    npc_known_fact_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    campaign_overrides: tuple[CampaignCanonOverride, ...] = ()
    procedural_entity_refs: tuple[str, ...] = ()
    lore_discoveries: tuple[str, ...] = ()
    faction_standings: tuple[FactionStanding, ...] = ()
    adventure_possibility_ids: tuple[str, ...] = ()
    lore_payload_version: int = 1

    @classmethod
    def legacy_unbound(cls) -> "CampaignLoreState":
        return cls()

    @classmethod
    def from_mapping(cls, value: Any | None) -> "CampaignLoreState":
        if value is None:
            return cls.legacy_unbound()
        data = _strict_mapping(
            value,
            required={
                "binding_status",
                "setting_profile",
                "world_id",
                "epoch_id",
                "region_id",
                "current_location_entity_id",
                "player_known_fact_ids",
                "npc_known_fact_ids",
                "campaign_overrides",
                "procedural_entity_refs",
                "lore_discoveries",
            },
            optional={
                "region_pack_id",
                "starting_location_entity_id",
                "faction_standings",
                "adventure_possibility_ids",
                "lore_payload_version",
            },
            label="Campaign Lore Authority state",
        )
        status = _enum(
            BindingStatus, data["binding_status"], "Campaign lore binding_status"
        )
        profile = _optional_text(
            data["setting_profile"], "Campaign lore setting_profile", MAX_NAME_LENGTH
        )
        world_id = None if data["world_id"] is None else _id(data["world_id"], "Campaign world_id")
        epoch_id = None if data["epoch_id"] is None else _id(data["epoch_id"], "Campaign epoch_id")
        region_id = None if data["region_id"] is None else _id(data["region_id"], "Campaign region_id")
        location_id = (
            None
            if data["current_location_entity_id"] is None
            else _id(data["current_location_entity_id"], "Campaign current_location_entity_id")
        )
        region_pack_id = (
            None
            if data.get("region_pack_id") is None
            else _id(data["region_pack_id"], "Campaign region_pack_id")
        )
        starting_location_id = (
            None
            if data.get("starting_location_entity_id") is None
            else _id(
                data["starting_location_entity_id"],
                "Campaign starting_location_entity_id",
            )
        )
        if status is BindingStatus.BOUND and starting_location_id is None:
            starting_location_id = location_id
        player_ids = _campaign_id_list(
            data["player_known_fact_ids"],
            "Campaign player_known_fact_ids",
            MAX_CAMPAIGN_FACT_IDS,
        )
        raw_npc_ids = data["npc_known_fact_ids"]
        if not isinstance(raw_npc_ids, Mapping) or len(raw_npc_ids) > MAX_NPCS_WITH_KNOWLEDGE:
            raise ValueError("Campaign npc_known_fact_ids is invalid.")
        npc_ids: list[tuple[str, tuple[str, ...]]] = []
        for npc_id, fact_ids in raw_npc_ids.items():
            npc_ids.append(
                (
                    _id(npc_id, "Campaign knowledge NPC ID"),
                    _campaign_id_list(
                        fact_ids,
                        "Campaign NPC-known fact IDs",
                        MAX_FACTS_PER_NPC,
                    ),
                )
            )
        if len({npc_id for npc_id, _ in npc_ids}) != len(npc_ids):
            raise ValueError("Campaign NPC knowledge contains duplicate IDs.")
        raw_overrides = data["campaign_overrides"]
        if not isinstance(raw_overrides, list) or len(raw_overrides) > MAX_CAMPAIGN_OVERRIDES:
            raise ValueError("Campaign campaign_overrides is invalid.")
        overrides = tuple(CampaignCanonOverride.from_mapping(item) for item in raw_overrides)
        if len({item.override_id for item in overrides}) != len(overrides):
            raise ValueError("Campaign overrides contain duplicate IDs.")
        procedural_refs = _campaign_id_list(
            data["procedural_entity_refs"],
            "Campaign procedural_entity_refs",
            MAX_PROCEDURAL_REFERENCES,
        )
        discoveries = _campaign_id_list(
            data["lore_discoveries"],
            "Campaign lore_discoveries",
            MAX_CAMPAIGN_FACT_IDS,
        )
        faction_standings = _faction_standings(data.get("faction_standings", []))
        possibility_ids = _campaign_id_list(
            data.get("adventure_possibility_ids", []),
            "Campaign adventure_possibility_ids",
            MAX_CAMPAIGN_FACT_IDS,
        )
        payload_version = data.get("lore_payload_version", 1)
        if type(payload_version) is not int or payload_version not in {1, LORE_PAYLOAD_VERSION}:
            raise ValueError("Campaign lore payload version is invalid.")
        if faction_standings and payload_version < LORE_PAYLOAD_VERSION:
            payload_version = LORE_PAYLOAD_VERSION
        if status is BindingStatus.BOUND and not all(
            (profile, world_id, epoch_id, region_id, location_id)
        ):
            raise ValueError("A bound campaign requires a complete explicit lore binding.")
        if status is not BindingStatus.BOUND and any(
            (
                profile,
                world_id,
                epoch_id,
                region_id,
                location_id,
                region_pack_id,
                starting_location_id,
            )
        ):
            raise ValueError("A legacy campaign cannot have a canon location binding.")
        return cls(
            binding_status=status,
            setting_profile=profile,
            world_id=world_id,
            epoch_id=epoch_id,
            region_id=region_id,
            current_location_entity_id=location_id,
            region_pack_id=region_pack_id,
            starting_location_entity_id=starting_location_id,
            player_known_fact_ids=player_ids,
            npc_known_fact_ids=tuple(sorted(npc_ids)),
            campaign_overrides=overrides,
            procedural_entity_refs=procedural_refs,
            lore_discoveries=discoveries,
            faction_standings=faction_standings,
            adventure_possibility_ids=possibility_ids,
            lore_payload_version=payload_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_status": self.binding_status.value,
            "setting_profile": self.setting_profile,
            "world_id": self.world_id,
            "epoch_id": self.epoch_id,
            "region_id": self.region_id,
            "current_location_entity_id": self.current_location_entity_id,
            "region_pack_id": self.region_pack_id,
            "starting_location_entity_id": self.starting_location_entity_id,
            "player_known_fact_ids": list(self.player_known_fact_ids),
            "npc_known_fact_ids": {
                npc_id: list(fact_ids) for npc_id, fact_ids in self.npc_known_fact_ids
            },
            "campaign_overrides": [item.to_dict() for item in self.campaign_overrides],
            "procedural_entity_refs": list(self.procedural_entity_refs),
            "lore_discoveries": list(self.lore_discoveries),
            "faction_standings": [item.to_dict() for item in self.faction_standings],
            "adventure_possibility_ids": list(self.adventure_possibility_ids),
            "lore_payload_version": self.lore_payload_version,
        }


def _faction_standings(value: Any) -> tuple[FactionStanding, ...]:
    if not isinstance(value, list) or len(value) > MAX_FACTION_ROWS:
        raise ValueError("Campaign faction_standings is invalid.")
    rows: list[FactionStanding] = []
    seen: set[str] = set()
    for item in value:
        data = _strict_mapping(
            item,
            required={
                "faction_id",
                "standing",
                "known_to_player",
                "local_presence",
                "source_action_id",
            },
            label="Faction standing",
        )
        standing = data["standing"]
        if type(standing) is not int or not -5 <= standing <= 5:
            raise ValueError("Faction standing is invalid.")
        if type(data["known_to_player"]) is not bool or type(data["local_presence"]) is not bool:
            raise ValueError("Faction visibility is invalid.")
        faction_id = _id(data["faction_id"], "Faction faction_id")
        if faction_id in seen:
            raise ValueError("Campaign faction_standings contains duplicate IDs.")
        seen.add(faction_id)
        rows.append(FactionStanding(
            faction_id=faction_id,
            standing=standing,
            known_to_player=data["known_to_player"],
            local_presence=data["local_presence"],
            source_action_id=_id(data["source_action_id"], "Faction source_action_id"),
        ))
    return tuple(rows)


def _campaign_id_list(value: Any, label: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} is invalid.")
    ids = tuple(_id(item, label) for item in value)
    if len(set(ids)) != len(ids):
        raise ValueError(f"{label} contains duplicate IDs.")
    return ids


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OwnerContinuityRecord:
    """Owner-approved continuity kept outside official sources and campaign canon.

    Construction records a decision. It does not load a pack, grant knowledge,
    or authorize narration.
    """

    decision_id: str
    provenance_kind: str
    approved_statement: str
    subject: str
    predicate: str
    year: int
    scope: str
    decision_document_digest: str

    def __post_init__(self) -> None:
        if self.provenance_kind != SourceTier.OWNER_APPROVED_CONTINUITY.value:
            raise ValueError("Owner continuity provenance is invalid.")
        if type(self.year) is not int or not 0 <= self.year <= 9999:
            raise ValueError("Owner continuity year is invalid.")
        digest = self.decision_document_digest
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ValueError("Owner decision digest is invalid.")
        object.__setattr__(self, "decision_id", _id(self.decision_id, "Owner decision_id"))
        object.__setattr__(
            self,
            "approved_statement",
            _text(self.approved_statement, "Owner approved_statement", MAX_FACT_VALUE_LENGTH),
        )
        object.__setattr__(self, "subject", _text(self.subject, "Owner subject", MAX_NAME_LENGTH))
        object.__setattr__(
            self, "predicate", _text(self.predicate, "Owner predicate", MAX_NAME_LENGTH)
        )
        object.__setattr__(self, "scope", _text(self.scope, "Owner scope", MAX_NOTE_LENGTH))

    @property
    def runtime_enabled(self) -> bool:
        return False

    @property
    def official_source_fact(self) -> bool:
        return False