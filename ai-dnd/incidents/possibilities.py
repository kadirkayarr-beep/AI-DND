"""Incident evidence may mint one adventure possibility. It is not a quest."""

from __future__ import annotations

from api.lore_authority.campaign_state import (
    EngineActionEvidence,
    adventure_possibility_id,
    record_adventure_possibility,
)
from api.lore_authority.models import BindingStatus


def fact_id_for(incident_id):
    return adventure_possibility_id(incident_id)


def offer(lore_state, world, record, *, authorized, evidence, source_action_id, turn_index):
    """Python, not Qwen, decides. The incident stays off ``world['quests']``."""
    if not authorized or lore_state is None:
        return lore_state
    if getattr(lore_state, "binding_status", None) is not BindingStatus.BOUND:
        return lore_state
    if not isinstance(record, dict) or not isinstance(record.get("incident_id"), str):
        return lore_state
    incident_id = record["incident_id"]
    if incident_id not in world.get("incidents", {}):
        return lore_state
    rumor = record.get("premise")
    if not isinstance(rumor, str) or not rumor.strip():
        return lore_state
    before = list(world.get("quests", []))
    try:
        updated = record_adventure_possibility(
            lore_state,
            incident_id,
            rumor,
            evidence=evidence,
            source_action_id=source_action_id,
            turn_index=turn_index,
        )
    except ValueError:
        return lore_state
    if world.get("quests", []) != before:
        world["quests"] = before
        return lore_state
    return updated
