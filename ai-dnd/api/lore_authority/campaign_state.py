"""Campaign-scoped lore references and guarded state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from .models import (
    LORE_PAYLOAD_VERSION,
    MAX_CAMPAIGN_OVERRIDES,
    MAX_REFERENCE_LENGTH,
    BindingStatus,
    CampaignCanonOverride,
    CampaignLoreState,
    ClaimType,
    EntityType,
    FactionStanding,
    LoreFact,
    LoreLayer,
    ReviewStatus,
    SourceTier,
    VisibilityScope,
)

if TYPE_CHECKING:
    from .registry import LoreRegistry


@dataclass(frozen=True)
class EngineActionEvidence:
    """Evidence passed by the Python engine after a committed action."""

    action_id: str
    turn_index: int
    authority: str

    def is_valid_for(self, action_id: str, turn_index: int) -> bool:
        return (
            self.authority == "python_engine"
            and self.action_id == action_id
            and type(self.turn_index) is int
            and self.turn_index == turn_index
            and self.turn_index >= 0
        )


def bind_campaign(
    state: CampaignLoreState,
    *,
    setting_profile: str,
    world_id: str,
    epoch_id: str,
    region_id: str,
    starting_location_id: str,
    region_pack_id: str | None = None,
    registry: "LoreRegistry",
    owner_approved: bool,
) -> CampaignLoreState:
    """Bind only after explicit owner approval and verified source coverage."""
    if not owner_approved:
        raise ValueError("Campaign binding requires explicit owner approval.")
    world = registry.entity(world_id)
    region = registry.entity(region_id)
    location = registry.entity(starting_location_id)
    if world is None or world.entity_type is not EntityType.WORLD:
        raise ValueError("The selected world is not a verified registry entity.")
    if region is None or region.entity_type not in {
        EntityType.CONTINENT,
        EntityType.REGION,
        EntityType.KINGDOM_NATION,
    }:
        raise ValueError("The selected region is not a verified registry region.")
    if location is None or location.entity_type not in {
        EntityType.CITY,
        EntityType.TOWN,
        EntityType.VILLAGE,
        EntityType.DISTRICT,
        EntityType.LANDMARK,
        EntityType.INN_TAVERN,
        EntityType.TEMPLE,
    }:
        raise ValueError("The selected starting location is not a verified registry location.")
    if region_id not in registry.geography_ancestors({starting_location_id}):
        raise ValueError("The starting location has no sourced link to the selected region.")
    from dataclasses import replace

    return CampaignLoreState.from_mapping(
        replace(
            state,
            binding_status=BindingStatus.BOUND,
            setting_profile=setting_profile,
            world_id=world_id,
            epoch_id=epoch_id,
            region_id=region_id,
            current_location_entity_id=starting_location_id,
            region_pack_id=region_pack_id,
            starting_location_entity_id=starting_location_id,
        ).to_dict()
    )


def apply_campaign_override(
    state: CampaignLoreState,
    override: CampaignCanonOverride,
    *,
    evidence: EngineActionEvidence | None,
) -> CampaignLoreState:
    """Record campaign canon only after a matching engine-established event."""
    if state.binding_status is not BindingStatus.BOUND:
        raise ValueError("An unbound legacy campaign cannot create canon overrides.")
    if evidence is None or not evidence.is_valid_for(
        override.source_action_id, override.created_turn
    ):
        raise ValueError("Campaign override requires matching Python engine evidence.")
    if any(item.override_id == override.override_id for item in state.campaign_overrides):
        raise ValueError("Campaign override ID already exists.")
    if len(state.campaign_overrides) >= MAX_CAMPAIGN_OVERRIDES:
        raise ValueError("Campaign override limit reached.")
    from dataclasses import replace

    return replace(
        state,
        campaign_overrides=state.campaign_overrides + (override,),
    )


def record_player_discovery(
    state: CampaignLoreState,
    fact_id: str,
    *,
    registry: "LoreRegistry",
    evidence: EngineActionEvidence | None,
    source_action_id: str,
    turn_index: int,
) -> CampaignLoreState:
    """Persist a player-known reference after an engine-confirmed discovery."""
    if state.binding_status is not BindingStatus.BOUND:
        raise ValueError("An unbound legacy campaign cannot receive canon discovery.")
    if evidence is None or not evidence.is_valid_for(source_action_id, turn_index):
        raise ValueError("Lore discovery requires Python engine evidence.")
    fact = registry.fact(fact_id)
    if fact is None:
        raise ValueError("Discovered fact is not loaded in the verified registry.")
    if fact.visibility is VisibilityScope.DM_SECRET:
        raise ValueError("DM-only lore cannot be persisted as player knowledge.")
    if fact_id in state.player_known_fact_ids:
        return state
    from dataclasses import replace

    return replace(
        state,
        player_known_fact_ids=state.player_known_fact_ids + (fact_id,),
        lore_discoveries=state.lore_discoveries + (fact_id,),
    )


def adventure_possibility_id(quest_id: str) -> str:
    """Stable id for one heard rumor. Dots are not valid lore ids."""
    if not isinstance(quest_id, str) or not quest_id.strip():
        raise ValueError("Adventure possibility id is invalid.")
    safe = quest_id.replace(".", "-")
    return _validated_id(f"adv:possibility:{safe}", "Adventure possibility ID")


def record_adventure_possibility(
    state: CampaignLoreState,
    quest_id: str,
    rumor: str,
    *,
    evidence: EngineActionEvidence | None,
    source_action_id: str,
    turn_index: int,
) -> CampaignLoreState:
    """Record a heard rumor. It is not a campaign canon fact."""
    if state.binding_status is not BindingStatus.BOUND:
        raise ValueError("An unbound legacy campaign cannot hear an adventure rumor.")
    if evidence is None or not evidence.is_valid_for(source_action_id, turn_index):
        raise ValueError("Adventure rumor requires Python engine evidence.")
    if not isinstance(rumor, str) or not rumor.strip():
        raise ValueError("Adventure rumor is empty.")
    fact_id = adventure_possibility_id(quest_id)
    subject_id = _validated_id(f"adv:{quest_id.replace('.', '-')}", "Adventure subject ID")
    LoreFact.from_mapping({
        "fact_id": fact_id,
        "subject_id": subject_id,
        "predicate": "rumor_text",
        "object_id_or_value": rumor.strip()[:MAX_REFERENCE_LENGTH],
        "claim_type": ClaimType.ADVENTURE_POSSIBILITY.value,
        "authority_tier": SourceTier.TIER_5_PROCEDURAL.value,
        "source_id": "src:adventure-engine",
        "source_reference": "python-engine",
        "valid_from": None,
        "valid_until": None,
        "visibility": VisibilityScope.REGIONAL_KNOWLEDGE.value,
        "region_scope": None,
        "notes": "",
        "reality_layer": LoreLayer.PROCEDURAL_LOCAL_FICTION.value,
        "review_status": ReviewStatus.UNREVIEWED_EXTRACTED.value,
    })
    if fact_id in state.adventure_possibility_ids:
        return state
    if fact_id in state.player_known_fact_ids:
        raise ValueError("Adventure rumor cannot be stored as a campaign fact.")
    from dataclasses import replace

    return replace(
        state,
        adventure_possibility_ids=state.adventure_possibility_ids + (fact_id,),
    )


def grant_npc_knowledge(
    state: CampaignLoreState,
    npc_id: str,
    fact_ids: Iterable[str],
    *,
    registry: "LoreRegistry",
    evidence: EngineActionEvidence | None,
    source_action_id: str,
    turn_index: int,
) -> CampaignLoreState:
    """Grant knowledge by stable NPC ID; names are never identity keys."""
    if state.binding_status is not BindingStatus.BOUND:
        raise ValueError("An unbound legacy campaign cannot receive canon NPC knowledge.")
    if evidence is None or not evidence.is_valid_for(source_action_id, turn_index):
        raise ValueError("NPC lore knowledge requires matching Python engine evidence.")
    npc_id = _validated_id(npc_id, "NPC ID")
    selected = tuple(dict.fromkeys(_validated_id(item, "Fact ID") for item in fact_ids))
    existing = dict(state.npc_known_fact_ids)
    known = set(existing.get(npc_id, ()))
    for fact_id in selected:
        fact = registry.fact(fact_id)
        if fact is None:
            raise ValueError(f"NPC knowledge references unloaded lore: {fact_id}.")
        if fact.visibility is VisibilityScope.DM_SECRET:
            raise ValueError("DM-only lore cannot be granted as NPC knowledge.")
        known.add(fact_id)
    if len(known) > 500:
        raise ValueError("NPC lore knowledge limit reached.")
    existing[npc_id] = tuple(sorted(known))
    from dataclasses import replace

    return replace(
        state,
        npc_known_fact_ids=tuple(sorted(existing.items())),
    )


def apply_faction_standing(
    state: CampaignLoreState,
    *,
    faction_id: str,
    standing: int,
    known_to_player: bool,
    local_presence: bool,
    evidence: EngineActionEvidence | None,
    source_action_id: str,
    turn_index: int,
) -> CampaignLoreState:
    """Change standing only from a committed engine action."""
    if state.binding_status is not BindingStatus.BOUND:
        raise ValueError("An unbound legacy campaign cannot change faction standing.")
    if evidence is None or not evidence.is_valid_for(source_action_id, turn_index):
        raise ValueError("Faction standing requires matching Python engine evidence.")
    if any(
        row.faction_id == faction_id and row.source_action_id == source_action_id
        for row in state.faction_standings
    ):
        return state
    row = FactionStanding(
        faction_id=_validated_id(faction_id, "Faction ID"),
        standing=standing,
        known_to_player=known_to_player,
        local_presence=local_presence,
        source_action_id=_validated_id(source_action_id, "Faction action ID"),
    )
    FactionStanding_rows = _faction_rows_with(state, row)
    from dataclasses import replace

    return replace(
        state,
        faction_standings=FactionStanding_rows,
        lore_payload_version=LORE_PAYLOAD_VERSION,
    )


def _faction_rows_with(
    state: CampaignLoreState,
    row: FactionStanding,
) -> tuple[FactionStanding, ...]:
    if not -5 <= row.standing <= 5:
        raise ValueError("Faction standing is invalid.")
    kept = tuple(item for item in state.faction_standings if item.faction_id != row.faction_id)
    rows = kept + (row,)
    if len(rows) > 64:
        raise ValueError("Faction standing limit reached.")
    return rows


def _validated_id(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{label} is invalid.")
    return value