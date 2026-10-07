"""One read path over the three player-knowledge stores.

The stores stay separate. Callers that show or narrate what the player
knows use this projection instead of rebuilding it from raw fields.
"""

from __future__ import annotations

from typing import Any

import living_world

from .models import BindingStatus, CampaignLoreState, ClaimType, VisibilityScope
from .registry import LoreRegistry


def read_player_knowledge(
    lore_state: CampaignLoreState | None,
    world: Any,
    registry: LoreRegistry,
) -> dict[str, Any]:
    state = lore_state or CampaignLoreState.legacy_unbound()
    return {
        "known_facts": _known_facts(state, registry),
        "people": _people(world),
        "adventure_evidence": _adventure_evidence(world),
        "known_factions": _known_factions(state, registry),
    }


def read_public_npc_label(npc: Any) -> str:
    return living_world.public_npc_name(npc)


def _known_facts(state: CampaignLoreState, registry: LoreRegistry) -> list[dict[str, str]]:
    if state.binding_status is not BindingStatus.BOUND:
        return []
    facts: list[dict[str, str]] = []
    for fact_id in state.player_known_fact_ids:
        fact = registry.fact(fact_id)
        if fact is None or fact.visibility is VisibilityScope.DM_SECRET:
            continue
        if fact.claim_type is ClaimType.ADVENTURE_POSSIBILITY:
            continue
        text = _public_fact_text(fact, registry)
        if text is None:
            continue
        subject = registry.entity(fact.subject_id)
        facts.append({
            "fact_id": fact.fact_id,
            "title": subject.canonical_name if subject is not None else fact.subject_id,
            "text": text,
        })
    return facts


def _public_fact_text(fact: Any, registry: LoreRegistry) -> str | None:
    value = fact.object_id_or_value
    if isinstance(value, str):
        named = registry.entity(value)
        shown = named.canonical_name if named is not None else None
        if shown is None and ":" in value:
            return None
        value_text = shown or value
    elif isinstance(value, bool):
        value_text = "evet" if value else "hayır"
    else:
        value_text = str(value)
    subject = registry.entity(fact.subject_id)
    subject_name = subject.canonical_name if subject is not None else fact.subject_id
    if fact.predicate in {"current_lord_id", "current_lord"}:
        return f"{subject_name} kentinin güncel lordu {value_text}."
    if fact.predicate == "current_year_name":
        return f"Şu anki yıl {value_text}."
    return f"{subject_name}: {value_text}."


def _people(world: Any) -> list[dict[str, Any]]:
    if not isinstance(world, dict):
        return []
    people: list[dict[str, Any]] = []
    for npc in world.get("npcs", []):
        if not isinstance(npc, dict) or not isinstance(npc.get("id"), str):
            continue
        people.append({
            "id": npc["id"],
            "label": living_world.public_npc_name(npc),
            "role_label": living_world.public_npc_role(npc) or "",
            "name_known": living_world.npc_name_known_to_player(npc),
            "location_id": npc.get("location") if isinstance(npc.get("location"), str) else None,
            "status": npc.get("status") if isinstance(npc.get("status"), str) else None,
        })
    return people


def _adventure_evidence(world: Any) -> list[Any]:
    if not isinstance(world, dict):
        return []
    evidence = world.get("player_knowledge", [])
    if not isinstance(evidence, list):
        return []
    return list(evidence)


def _known_factions(state: CampaignLoreState, registry: LoreRegistry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in state.faction_standings:
        if not row.known_to_player:
            continue
        entity = registry.entity(row.faction_id)
        rows.append({
            "faction_id": row.faction_id,
            "title": entity.canonical_name if entity is not None else row.faction_id,
            "standing": row.standing,
            "local_presence": row.local_presence,
        })
    return rows
