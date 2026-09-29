"""Immutable official-lore registry, deterministic resolution, and retrieval."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .models import (
    BindingStatus,
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


MAX_RETRIEVED_FACTS = 64
MAX_CONTEXT_BYTES = 12 * 1024
MAX_CANDIDATES = 400


@dataclass(frozen=True)
class EntityResolution:
    status: ResolutionStatus
    query: str
    entity_ids: tuple[str, ...]


@dataclass(frozen=True)
class ConflictResolution:
    status: ResolutionStatus
    selected_fact_id: str | None
    conflicting_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class LoreClaimValidation:
    status: ResolutionStatus
    matching_fact_ids: tuple[str, ...]
    expected_values: tuple[str | int | bool, ...]


def normalize_name(value: str) -> str:
    """Normalize for exact alias matching only; never fuzzy-match canon names."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _authorized_source(source: SourceManifest) -> bool:
    return (
        source.source_tier is not SourceTier.TIER_5_PROCEDURAL
        and source.source_tier is not SourceTier.TEST_FIXTURE
        and source.authority_status.casefold() == "verified"
        and source.owner_access_status.casefold() == "authorized"
    )


def _require_unique(items: Iterable[Any], field: str, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        item_id = getattr(item, field)
        if item_id in result:
            raise ValueError(f"Duplicate {label} ID: {item_id}.")
        result[item_id] = item
    return result


class LoreRegistry:
    """Read-only index of sourced, reviewed facts and relationships.

    Production registries accept only verified facts from an explicitly
    authorized source. Test fixtures can be enabled in tests, but are never
    loaded by the application registry.
    """

    def __init__(
        self,
        *,
        sources: Sequence[SourceManifest] = (),
        entities: Sequence[LoreEntity] = (),
        edges: Sequence[LoreEdge] = (),
        facts: Sequence[LoreFact] = (),
        allow_test_fixtures: bool = False,
    ) -> None:
        source_map = _require_unique(sources, "source_id", "source")
        entity_map = _require_unique(entities, "entity_id", "entity")
        edge_map = _require_unique(edges, "edge_id", "edge")
        fact_map = _require_unique(facts, "fact_id", "fact")

        for entity in entities:
            _validate_provenance(
                source_map,
                entity.source_id,
                entity.authority_tier,
                entity.review_status,
                allow_test_fixtures=allow_test_fixtures,
                label=f"entity {entity.entity_id}",
            )
        for edge in edges:
            _validate_provenance(
                source_map,
                edge.source_id,
                edge.authority_tier,
                edge.review_status,
                allow_test_fixtures=allow_test_fixtures,
                label=f"edge {edge.edge_id}",
            )
            if edge.subject_id not in entity_map or edge.object_id not in entity_map:
                raise ValueError(f"Edge {edge.edge_id} references an unknown entity.")
        for fact in facts:
            _validate_provenance(
                source_map,
                fact.source_id,
                fact.authority_tier,
                fact.review_status,
                allow_test_fixtures=allow_test_fixtures,
                label=f"fact {fact.fact_id}",
            )
            if fact.subject_id not in entity_map:
                raise ValueError(f"Fact {fact.fact_id} references an unknown subject.")
            if fact.reality_layer is not LoreLayer.OFFICIAL_SETTING_CANON:
                if not allow_test_fixtures:
                    raise ValueError(
                        f"Non-official fact {fact.fact_id} cannot enter the static registry."
                    )
            if (
                fact.claim_type
                in {
                    ClaimType.PROCEDURAL_FACT,
                    ClaimType.NARRATIVE_TEXTURE,
                }
                and not allow_test_fixtures
            ):
                raise ValueError(
                    f"Procedural or narrative fact {fact.fact_id} cannot enter the static registry."
                )

        self._sources: Mapping[str, SourceManifest] = MappingProxyType(source_map)
        self._entities: Mapping[str, LoreEntity] = MappingProxyType(entity_map)
        self._edges: Mapping[str, LoreEdge] = MappingProxyType(edge_map)
        self._facts: Mapping[str, LoreFact] = MappingProxyType(fact_map)
        self._allow_test_fixtures = allow_test_fixtures
        self._aliases = self._build_alias_index(entity_map.values())
        self._outgoing_edges = self._build_edge_index(edges)
        self._incoming_edges = self._build_incoming_edge_index(edges)
        self._facts_by_subject = self._build_fact_index(facts)
        self._facts_by_region = self._build_region_index(facts)

    @classmethod
    def empty(cls) -> "LoreRegistry":
        """The production registry starts empty until authorized data is loaded."""
        return cls()

    @property
    def source_count(self) -> int:
        return len(self._sources)

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    @property
    def fact_count(self) -> int:
        return len(self._facts)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def entity(self, entity_id: str) -> LoreEntity | None:
        return self._entities.get(entity_id)

    def fact(self, fact_id: str) -> LoreFact | None:
        return self._facts.get(fact_id)

    def facts(self) -> tuple[LoreFact, ...]:
        return tuple(self._facts[key] for key in sorted(self._facts))

    def sources(self) -> tuple[SourceManifest, ...]:
        return tuple(self._sources[key] for key in sorted(self._sources))

    def resolve_entity(self, name_or_id: str, *, region_scope: str | None = None) -> EntityResolution:
        query = name_or_id.strip()
        if not query:
            return EntityResolution(ResolutionStatus.UNKNOWN_UNLOADED, query, ())
        if query in self._entities:
            candidates = (query,)
        else:
            candidates = self._aliases.get(normalize_name(query), ())
        if region_scope:
            scoped = tuple(
                entity_id
                for entity_id in candidates
                if self._entities[entity_id].region_scope in {None, region_scope}
            )
            if scoped:
                candidates = scoped
        if len(candidates) == 1:
            status = ResolutionStatus.RESOLVED
        elif len(candidates) > 1:
            status = ResolutionStatus.AMBIGUOUS
        else:
            status = ResolutionStatus.UNKNOWN_UNLOADED
        return EntityResolution(status, query, tuple(sorted(candidates)))

    def related_edges(
        self,
        entity_id: str,
        *,
        predicates: set[Relationship] | None = None,
    ) -> tuple[LoreEdge, ...]:
        if entity_id not in self._entities:
            return ()
        edges = self._outgoing_edges.get(entity_id, ())
        return tuple(
            edge for edge in edges if predicates is None or edge.predicate in predicates
        )

    def geography_ancestors(self, entity_ids: Iterable[str]) -> frozenset[str]:
        """Return only explicitly sourced parent/location relations."""
        allowed = {
            Relationship.PART_OF,
            Relationship.LOCATED_IN,
            Relationship.DISTRICT_OF,
        }
        found = set(entity_ids)
        pending = list(found)
        while pending:
            current = pending.pop()
            for edge in self._outgoing_edges.get(current, ()):
                if edge.predicate not in allowed or edge.object_id in found:
                    continue
                found.add(edge.object_id)
                pending.append(edge.object_id)
        return frozenset(found)

    def resolve_conflict(self, facts: Sequence[LoreFact]) -> ConflictResolution:
        if not facts:
            return ConflictResolution(ResolutionStatus.UNKNOWN_UNLOADED, None, ())
        values = {fact.object_id_or_value for fact in facts}
        ordered = sorted(facts, key=lambda fact: (fact.authority_tier.rank, fact.fact_id))
        if len(values) == 1:
            return ConflictResolution(
                ResolutionStatus.RESOLVED,
                ordered[0].fact_id,
                tuple(fact.fact_id for fact in ordered),
            )
        best_rank = ordered[0].authority_tier.rank
        highest = [fact for fact in ordered if fact.authority_tier.rank == best_rank]
        highest_values = {fact.object_id_or_value for fact in highest}
        if len(highest_values) != 1:
            return ConflictResolution(
                ResolutionStatus.CANON_CONFLICT_UNRESOLVED,
                None,
                tuple(fact.fact_id for fact in ordered),
            )
        selected_value = next(iter(highest_values))
        winner = min(
            (fact for fact in highest if fact.object_id_or_value == selected_value),
            key=lambda fact: fact.fact_id,
        )
        return ConflictResolution(
            ResolutionStatus.RESOLVED,
            winner.fact_id,
            tuple(fact.fact_id for fact in ordered),
        )

    def validate_lore_claim(
        self,
        *,
        subject_id: str,
        predicate: str,
        object_id_or_value: str | int | bool,
        player_known_fact_ids: Iterable[str] = (),
        region_ids: Iterable[str] = (),
    ) -> LoreClaimValidation:
        known = set(player_known_fact_ids)
        regions = set(region_ids)
        candidates = [
            fact
            for fact in self._facts_by_subject.get(subject_id, ())
            if fact.predicate == predicate
            and fact.reality_layer is LoreLayer.OFFICIAL_SETTING_CANON
            and _visible_to_player(fact, known, regions)
        ]
        if not candidates:
            return LoreClaimValidation(ResolutionStatus.UNKNOWN_UNLOADED, (), ())
        resolution = self.resolve_conflict(candidates)
        if resolution.status is ResolutionStatus.CANON_CONFLICT_UNRESOLVED:
            return LoreClaimValidation(
                ResolutionStatus.CANON_CONFLICT_UNRESOLVED,
                resolution.conflicting_fact_ids,
                (),
            )
        selected = self._facts[resolution.selected_fact_id]  # type: ignore[index]
        status = (
            ResolutionStatus.RESOLVED
            if selected.object_id_or_value == object_id_or_value
            else ResolutionStatus.CONTRADICTED
        )
        return LoreClaimValidation(
            status,
            (selected.fact_id,),
            (selected.object_id_or_value,),
        )

    def get_player_known_lore(
        self,
        known_fact_ids: Iterable[str],
        *,
        region_ids: Iterable[str] = (),
    ) -> tuple[LoreFact, ...]:
        known = set(known_fact_ids)
        regions = set(region_ids)
        return tuple(
            self._facts[fact_id]
            for fact_id in sorted(known)
            if fact_id in self._facts
            and _visible_to_player(self._facts[fact_id], known, regions)
            and self._facts[fact_id].visibility is not VisibilityScope.DM_SECRET
        )

    def retrieve_lore_context(
        self,
        *,
        current_location_id: str | None = None,
        mentioned_entity_ids: Iterable[str] = (),
        present_npc_ids: Iterable[str] = (),
        active_quest_fact_ids: Iterable[str] = (),
        campaign_state: CampaignLoreState | None = None,
        target_npc_id: str | None = None,
        include_dm_secrets: bool = False,
        max_facts: int = MAX_RETRIEVED_FACTS,
        max_bytes: int = MAX_CONTEXT_BYTES,
    ) -> dict[str, Any]:
        if not 1 <= max_facts <= MAX_RETRIEVED_FACTS:
            raise ValueError("max_facts is outside the supported range.")
        if not 256 <= max_bytes <= MAX_CONTEXT_BYTES:
            raise ValueError("max_bytes is outside the supported range.")
        state = campaign_state or CampaignLoreState.legacy_unbound()
        mentioned_ids = set(mentioned_entity_ids)
        quest_fact_ids = set(active_quest_fact_ids)
        explicit_ids = set(mentioned_ids)
        if current_location_id:
            explicit_ids.add(current_location_id)
        present_ids = set(present_npc_ids)
        if target_npc_id:
            present_ids.add(target_npc_id)
        all_context_ids = explicit_ids | present_ids
        region_ids = self.geography_ancestors(
            item for item in (state.region_id, current_location_id) if item
        )
        geography_ids = set(self.geography_ancestors(all_context_ids))
        for entity_id in tuple(geography_ids):
            for edge in self._incoming_edges.get(entity_id, ()):
                if edge.predicate in {
                    Relationship.PART_OF,
                    Relationship.LOCATED_IN,
                    Relationship.DISTRICT_OF,
                }:
                    geography_ids.add(edge.subject_id)
        candidates: dict[str, tuple[int, LoreFact]] = {}
        for entity_id in all_context_ids:
            for fact in self._facts_by_subject.get(entity_id, ()):
                rank = _retrieval_rank(
                    fact,
                    current_location_id=current_location_id,
                    mentioned=entity_id in mentioned_ids,
                    present_npc=entity_id in present_ids,
                    quest=fact.fact_id in quest_fact_ids,
                )
                if rank is not None:
                    candidates[fact.fact_id] = (rank, fact)
        for entity_id in geography_ids - explicit_ids:
            for fact in self._facts_by_subject.get(entity_id, ()):
                if fact.reality_layer is LoreLayer.OFFICIAL_SETTING_CANON:
                    candidates[fact.fact_id] = (2, fact)
        for fact_id in quest_fact_ids:
            fact = self._facts.get(fact_id)
            if fact is not None:
                candidates.setdefault(fact.fact_id, (6, fact))
        for region_id in region_ids:
            for fact in self._facts_by_region.get(region_id, ()):
                candidates.setdefault(fact.fact_id, (7, fact))
        if len(candidates) > MAX_CANDIDATES:
            candidates = dict(
                sorted(candidates.items(), key=lambda item: (item[1][0], item[0]))[
                    :MAX_CANDIDATES
                ]
            )

        campaign_known = set(state.player_known_fact_ids)
        npc_known = dict(state.npc_known_fact_ids).get(target_npc_id or "", ())
        for fact_id in campaign_known:
            fact = self._facts.get(fact_id)
            if fact is not None and fact.subject_id in (geography_ids | all_context_ids):
                candidates.setdefault(fact_id, (4, fact))
        for fact_id in npc_known:
            fact = self._facts.get(fact_id)
            if fact is not None and fact.subject_id in (geography_ids | all_context_ids):
                candidates.setdefault(fact_id, (4, fact))
        allowed: list[tuple[int, LoreFact]] = []
        withheld_secret_count = 0
        for rank, fact in candidates.values():
            if fact.visibility is VisibilityScope.DM_SECRET and not include_dm_secrets:
                withheld_secret_count += 1
                continue
            if fact.visibility is VisibilityScope.DISCOVERABLE_SECRET:
                if fact.fact_id not in campaign_known and fact.fact_id not in npc_known:
                    withheld_secret_count += 1
                    continue
            if fact.visibility is VisibilityScope.SPECIALIST_KNOWLEDGE:
                if (
                    fact.fact_id not in campaign_known
                    and fact.fact_id not in npc_known
                    and not include_dm_secrets
                ):
                    continue
            if fact.visibility is VisibilityScope.REGIONAL_KNOWLEDGE:
                if fact.region_scope not in region_ids and fact.fact_id not in campaign_known:
                    continue
            allowed.append((rank, fact))

        grouped: dict[tuple[str, str, str | None, str | None], list[LoreFact]] = {}
        for _, fact in allowed:
            key = (fact.subject_id, fact.predicate, fact.valid_from, fact.valid_until)
            grouped.setdefault(key, []).append(fact)
        selected: list[tuple[int, LoreFact]] = []
        unresolved_conflicts: list[dict[str, Any]] = []
        for group in grouped.values():
            resolution = self.resolve_conflict(group)
            if resolution.status is ResolutionStatus.CANON_CONFLICT_UNRESOLVED:
                unresolved_conflicts.append(
                    {
                        "subject_id": group[0].subject_id,
                        "predicate": group[0].predicate,
                        "fact_ids": list(resolution.conflicting_fact_ids),
                    }
                )
                continue
            if resolution.selected_fact_id:
                fact = self._facts[resolution.selected_fact_id]
                rank = min(
                    priority
                    for priority, item in allowed
                    if item.subject_id == fact.subject_id
                    and item.predicate == fact.predicate
                    and item.valid_from == fact.valid_from
                    and item.valid_until == fact.valid_until
                )
                selected.append((rank, fact))
        selected.sort(key=lambda item: (item[0], item[1].fact_id))
        selected = selected[:max_facts]

        official = [fact.to_dict() for _, fact in selected]
        player_known = [
            fact.to_dict()
            for fact in self.get_player_known_lore(
                campaign_known,
                region_ids=region_ids,
            )
            if fact.fact_id in {item.fact_id for _, item in selected}
        ]
        relevant_subjects = geography_ids | all_context_ids
        npc_known_ids = set(npc_known)
        npc_known_facts = [
            self._facts[fact_id].to_dict()
            for fact_id in sorted(npc_known_ids)
            if fact_id in self._facts
            and self._facts[fact_id].subject_id in relevant_subjects
            and self._facts[fact_id].visibility is not VisibilityScope.DM_SECRET
        ]
        relevant_overrides = [
            item.to_dict()
            for item in state.campaign_overrides
            if item.subject_id in relevant_subjects
        ][-40:]
        relevant_procedural = [
            {"entity_id": entity_id, "authority": "PROCEDURAL_LOCAL_FICTION"}
            for entity_id in state.procedural_entity_refs
            if entity_id in relevant_subjects
        ][:40]
        unknown_ids = sorted(
            entity_id
            for entity_id in all_context_ids
            if entity_id not in self._entities
        )[:32]
        packet: dict[str, Any] = {
            "authority_boundary": {
                "official_lore_is_not_campaign_history": True,
                "campaign_state_is_not_official_canon": True,
                "procedural_content_never_promotes_to_official": True,
                "narrative_texture_is_not_world_fact": True,
                "unknown_or_unloaded_must_remain_unknown": True,
            },
            "sections": {
                "official_forgotten_realms_lore": official,
                "campaign_canon": relevant_overrides,
                "player_known_lore": player_known,
                "npc_known_lore": npc_known_facts,
                "procedural_local_content": relevant_procedural,
                "unknown_or_unloaded": [
                    {
                        "entity_id": entity_id,
                        "status": ResolutionStatus.UNKNOWN_UNLOADED.value,
                    }
                    for entity_id in unknown_ids
                ],
            },
            "diagnostics": {
                "registry_fact_count": self.fact_count,
                "selected_fact_count": len(official),
                "withheld_secret_count": withheld_secret_count,
                "unresolved_conflicts": unresolved_conflicts,
                "coverage_status": (
                    "SOURCE_INGESTION_REQUIRED_FOR_FULL_COVERAGE"
                    if self.fact_count == 0
                    else "PARTIAL"
                ),
                "binding_status": state.binding_status.value,
            },
        }
        _trim_packet(packet, max_bytes)
        return packet

    def source_coverage(self) -> dict[str, Any]:
        categories = {
            "geography": {
                EntityType.WORLD,
                EntityType.CONTINENT,
                EntityType.REGION,
                EntityType.KINGDOM_NATION,
                EntityType.CITY,
                EntityType.TOWN,
                EntityType.VILLAGE,
                EntityType.DISTRICT,
                EntityType.ROAD_ROUTE,
                EntityType.WILDERNESS,
                EntityType.FOREST,
                EntityType.MOUNTAIN_RANGE,
                EntityType.RIVER,
                EntityType.SEA,
                EntityType.ISLAND,
            },
            "settlements": {
                EntityType.CITY,
                EntityType.TOWN,
                EntityType.VILLAGE,
            },
            "factions": {EntityType.FACTION},
            "religion": {EntityType.DEITY, EntityType.RELIGION_CHURCH},
            "cosmology": {EntityType.PLANE},
            "venues": {EntityType.INN_TAVERN, EntityType.TEMPLE, EntityType.LANDMARK},
            "canonical_npcs": {EntityType.CANONICAL_NPC},
            "historical_events": {EntityType.HISTORICAL_EVENT},
        }
        status = "SOURCE_INGESTION_REQUIRED_FOR_FULL_COVERAGE"
        if self.fact_count:
            status = "PARTIAL"
        return {
            "status": status,
            "source_count": self.source_count,
            "entity_count": self.entity_count,
            "fact_count": self.fact_count,
            "edge_count": self.edge_count,
            "categories": {
                category: (
                    "UNLOADED"
                    if not any(
                        entity.entity_type in entity_types
                        for entity in self._entities.values()
                    )
                    else "PARTIAL"
                )
                for category, entity_types in categories.items()
            },
            "authorized_sources_only": True,
            "model_memory_used_as_source": False,
        }

    @staticmethod
    def _build_alias_index(
        entities: Iterable[LoreEntity],
    ) -> Mapping[str, tuple[str, ...]]:
        index: dict[str, set[str]] = {}
        for entity in entities:
            for name in (entity.canonical_name, *entity.aliases):
                index.setdefault(normalize_name(name), set()).add(entity.entity_id)
        return MappingProxyType(
            {name: tuple(sorted(ids)) for name, ids in index.items()}
        )

    @staticmethod
    def _build_edge_index(
        edges: Sequence[LoreEdge],
    ) -> Mapping[str, tuple[LoreEdge, ...]]:
        index: dict[str, list[LoreEdge]] = {}
        for edge in edges:
            index.setdefault(edge.subject_id, []).append(edge)
        return MappingProxyType(
            {
                entity_id: tuple(sorted(items, key=lambda edge: edge.edge_id))
                for entity_id, items in index.items()
            }
        )

    @staticmethod
    def _build_incoming_edge_index(
        edges: Sequence[LoreEdge],
    ) -> Mapping[str, tuple[LoreEdge, ...]]:
        index: dict[str, list[LoreEdge]] = {}
        for edge in edges:
            index.setdefault(edge.object_id, []).append(edge)
        return MappingProxyType(
            {
                entity_id: tuple(sorted(items, key=lambda edge: edge.edge_id))
                for entity_id, items in index.items()
            }
        )

    @staticmethod
    def _build_fact_index(
        facts: Sequence[LoreFact],
    ) -> Mapping[str, tuple[LoreFact, ...]]:
        index: dict[str, list[LoreFact]] = {}
        for fact in facts:
            index.setdefault(fact.subject_id, []).append(fact)
        return MappingProxyType(
            {
                entity_id: tuple(sorted(items, key=lambda fact: fact.fact_id))
                for entity_id, items in index.items()
            }
        )

    @staticmethod
    def _build_region_index(
        facts: Sequence[LoreFact],
    ) -> Mapping[str, tuple[LoreFact, ...]]:
        index: dict[str, list[LoreFact]] = {}
        for fact in facts:
            if fact.region_scope:
                index.setdefault(fact.region_scope, []).append(fact)
        return MappingProxyType(
            {
                region_id: tuple(sorted(items, key=lambda fact: fact.fact_id))
                for region_id, items in index.items()
            }
        )


def _validate_provenance(
    sources: Mapping[str, SourceManifest],
    source_id: str,
    authority_tier: SourceTier,
    review_status: ReviewStatus,
    *,
    allow_test_fixtures: bool,
    label: str,
) -> None:
    source = sources.get(source_id)
    if source is None:
        raise ValueError(f"{label} has no registered provenance source.")
    if source.source_tier is not authority_tier:
        raise ValueError(f"{label} authority tier does not match its source.")
    if allow_test_fixtures and review_status is ReviewStatus.TEST_ONLY:
        if source.source_tier is not SourceTier.TEST_FIXTURE:
            raise ValueError(f"{label} test provenance is invalid.")
        return
    if review_status is not ReviewStatus.VERIFIED_CANON:
        raise ValueError(f"{label} is not reviewed as verified canon.")
    if not _authorized_source(source):
        raise ValueError(f"{label} source is not verified and owner-authorized.")


def _visible_to_player(
    fact: LoreFact,
    known_fact_ids: set[str],
    region_ids: set[str],
) -> bool:
    if fact.visibility is VisibilityScope.DM_SECRET:
        return False
    if fact.visibility is VisibilityScope.COMMON_KNOWLEDGE:
        return True
    if fact.visibility is VisibilityScope.REGIONAL_KNOWLEDGE:
        return fact.region_scope in region_ids or fact.fact_id in known_fact_ids
    return fact.fact_id in known_fact_ids


def _retrieval_rank(
    fact: LoreFact,
    *,
    current_location_id: str | None,
    mentioned: bool,
    present_npc: bool,
    quest: bool,
) -> int | None:
    if fact.reality_layer is not LoreLayer.OFFICIAL_SETTING_CANON:
        return None
    if fact.subject_id == current_location_id:
        return 0
    if mentioned:
        return 1
    if present_npc:
        return 3
    if quest:
        return 5
    return None


def _trim_packet(packet: dict[str, Any], max_bytes: int) -> None:
    """Bound context size by dropping lowest-priority official fact entries."""
    sections = packet["sections"]
    while len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > max_bytes:
        removed = False
        for key in (
            "procedural_local_content",
            "npc_known_lore",
            "campaign_canon",
            "player_known_lore",
            "official_forgotten_realms_lore",
            "unknown_or_unloaded",
        ):
            if sections[key]:
                sections[key].pop()
                removed = True
                break
        if not removed:
            raise ValueError("Lore context packet exceeds its byte budget.")
        packet["diagnostics"]["selected_fact_count"] = len(
            sections["official_forgotten_realms_lore"]
        )


def default_lore_registry() -> LoreRegistry:
    """Return the intentionally empty production registry.

    No authorized official source pack is present in the project. Keeping this
    registry empty is safer than treating model recall as provenance.
    """
    return LoreRegistry.empty()


def resolve_entity(
    registry: LoreRegistry,
    name_or_id: str,
    *,
    region_scope: str | None = None,
) -> EntityResolution:
    return registry.resolve_entity(name_or_id, region_scope=region_scope)


def retrieve_lore_context(
    registry: LoreRegistry,
    **kwargs: Any,
) -> dict[str, Any]:
    return registry.retrieve_lore_context(**kwargs)


def validate_lore_claim(registry: LoreRegistry, **kwargs: Any) -> LoreClaimValidation:
    return registry.validate_lore_claim(**kwargs)


def get_player_known_lore(
    registry: LoreRegistry,
    known_fact_ids: Iterable[str],
    *,
    region_ids: Iterable[str] = (),
) -> tuple[LoreFact, ...]:
    return registry.get_player_known_lore(known_fact_ids, region_ids=region_ids)