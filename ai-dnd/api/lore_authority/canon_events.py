"""Campaign canon written only from committed engine results."""

from __future__ import annotations

from typing import Any

from .campaign_state import EngineActionEvidence, apply_campaign_override, record_player_discovery
from .models import BindingStatus, CampaignCanonOverride, CampaignLoreState
from .registry import LoreRegistry


def apply_committed_world_canon(
    state: CampaignLoreState,
    *,
    evidence: EngineActionEvidence,
    before_world: Any,
    after_world: Any,
    action_result: Any,
    registry: LoreRegistry,
) -> CampaignLoreState:
    """Record deaths, closed routes, and fact discoveries from engine state.

    Player or model prose is ignored. The same action writes each row once.
    """
    if state.binding_status is not BindingStatus.BOUND:
        return state
    updated = _record_deaths(state, evidence, before_world, after_world)
    updated = _record_closed_routes(updated, evidence, before_world, after_world)
    return _record_discoveries(updated, evidence, action_result, registry)


def _record_deaths(
    state: CampaignLoreState,
    evidence: EngineActionEvidence,
    before_world: Any,
    after_world: Any,
) -> CampaignLoreState:
    before = _npcs(before_world)
    updated = state
    for npc_id, npc in _npcs(after_world).items():
        if not _is_dead(npc) or _is_dead(before.get(npc_id, {})):
            continue
        updated = _add_override(
            updated,
            evidence,
            override_id=f"death:{npc_id}",
            subject_id=npc_id,
            predicate="life_status",
            object_id_or_value="dead",
            notes="Python-confirmed death.",
        )
    return updated


def _record_closed_routes(
    state: CampaignLoreState,
    evidence: EngineActionEvidence,
    before_world: Any,
    after_world: Any,
) -> CampaignLoreState:
    updated = state
    for origin, destination in sorted(_blocked_routes(after_world) - _blocked_routes(before_world)):
        updated = _add_override(
            updated,
            evidence,
            override_id=f"route:{origin}:{destination}",
            subject_id=f"route:{origin}:{destination}",
            predicate="route_status",
            object_id_or_value="closed",
            notes="Python-confirmed route closure.",
        )
    return updated


def _record_discoveries(
    state: CampaignLoreState,
    evidence: EngineActionEvidence,
    action_result: Any,
    registry: LoreRegistry,
) -> CampaignLoreState:
    if not isinstance(action_result, dict):
        return state
    fact_ids = action_result.get("discovered_fact_ids", [])
    if not isinstance(fact_ids, list):
        return state
    updated = state
    for fact_id in fact_ids:
        if not isinstance(fact_id, str):
            raise ValueError("Discovered fact id is invalid.")
        updated = record_player_discovery(
            updated,
            fact_id,
            registry=registry,
            evidence=evidence,
            source_action_id=evidence.action_id,
            turn_index=evidence.turn_index,
        )
    return updated


def _add_override(
    state: CampaignLoreState,
    evidence: EngineActionEvidence,
    *,
    override_id: str,
    subject_id: str,
    predicate: str,
    object_id_or_value: str,
    notes: str,
) -> CampaignLoreState:
    if any(item.override_id == override_id for item in state.campaign_overrides):
        return state
    override = CampaignCanonOverride.from_mapping({
        "override_id": override_id,
        "subject_id": subject_id,
        "predicate": predicate,
        "object_id_or_value": object_id_or_value,
        "source_action_id": evidence.action_id,
        "created_turn": evidence.turn_index,
        "notes": notes,
    })
    return apply_campaign_override(state, override, evidence=evidence)


def _npcs(world: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(world, dict):
        return {}
    found: dict[str, dict[str, Any]] = {}
    for npc in world.get("npcs", []):
        if isinstance(npc, dict) and isinstance(npc.get("id"), str):
            found[npc["id"]] = npc
    return found


def _is_dead(npc: dict[str, Any]) -> bool:
    return npc.get("status") == "dead" or npc.get("condition") == "dead"


def _blocked_routes(world: Any) -> set[tuple[str, str]]:
    if not isinstance(world, dict):
        return set()
    routes = world.get("blocked_travel_routes")
    if not isinstance(routes, dict):
        return set()
    blocked: set[tuple[str, str]] = set()
    for origin, destinations in routes.items():
        if not isinstance(origin, str) or not isinstance(destinations, dict):
            continue
        for destination, closed in destinations.items():
            if isinstance(destination, str) and closed is True:
                blocked.add((origin, destination))
    return blocked
