"""Canonical identity for created entities (W10): id + source event + location; a name is never identity.

`admit_entity` sends a proposal through the existing NPC creation owner (`session.create_npc_from_ai`, which keeps its own
validation, capacity and same-name/same-role rules) and stamps the result with the event that caused it. The request key is
derived from campaign + source event, so admitting the same event twice returns the same entity. `entity_key` is
`<campaign_id>:<canonical id>`: two campaigns that both hold a "Marek" (both may even be `npc_001`) never share a key, and
`resolve_entity` only resolves keys of the campaign the world belongs to.
"""
from __future__ import annotations

import hashlib
from typing import Any


def admit_entity(proposal: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Admit one NPC proposal. `context`: {"session", "campaign_id", "source_event_id"}."""
    session = context["session"]
    campaign_id = str(context["campaign_id"])
    source_event_id = str(context["source_event_id"])
    request_key = hashlib.sha256(f"{campaign_id}|{source_event_id}".encode("utf-8")).hexdigest()
    npc = session.create_npc_from_ai(proposal, request_key=request_key)
    if not isinstance(npc, dict):
        return {"admitted": False, "reason": "proposal_rejected", "source_event_id": source_event_id}
    npc.setdefault("source_event_id", source_event_id)
    npc.setdefault("campaign_id", campaign_id)
    world = session.world_state
    world.setdefault("flags", {}).setdefault("campaign_id", campaign_id)
    return {
        "admitted": True, "kind": "npc", "entity_id": npc["id"], "source_event_id": npc["source_event_id"],
        "location_id": npc.get("location"), "campaign_id": npc["campaign_id"],
        "entity_key": f"{npc['campaign_id']}:{npc['id']}",
    }


def resolve_entity(world_state: dict[str, Any], entity_key: str) -> dict[str, Any] | None:
    """Return the NPC record for a campaign-scoped key, or None (another campaign, unknown id, or a display name)."""
    if not isinstance(entity_key, str) or ":" not in entity_key:
        return None
    campaign_id, _, entity_id = entity_key.rpartition(":")
    for npc in world_state.get("npcs", []):
        if (isinstance(npc, dict) and npc.get("id") == entity_id and npc.get("campaign_id") == campaign_id):
            return npc
    return None
