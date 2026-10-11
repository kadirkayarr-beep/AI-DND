"""Incident to adventure bridge. The director still owns quest rows."""

from __future__ import annotations

from adventure import director
from adventure.models import empty_bindings
from incidents.possibilities import fact_id_for


def bind(world, record, lore_state, *, campaign_id=""):
    """Bind one heard possibility under existing MAX_OPEN rules."""
    if lore_state is None or not isinstance(record, dict):
        return None
    incident_id = record.get("incident_id")
    if not isinstance(incident_id, str):
        return None
    if fact_id_for(incident_id) not in getattr(lore_state, "adventure_possibility_ids", ()):
        return None
    location_id = record.get("location_id")
    if not isinstance(location_id, str):
        return None
    present = [
        npc["id"] for npc in world.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == location_id
        and isinstance(npc.get("id"), str)
    ]
    promoted = [
        person.get("npc_id")
        for person in record.get("details", {}).get("people", {}).values()
        if isinstance(person, dict) and person.get("state") == "promoted"
        and isinstance(person.get("npc_id"), str)
    ]
    ordered = list(dict.fromkeys(promoted + present))
    if len(ordered) < 2:
        return None
    bindings = empty_bindings()
    bindings["location_ids"] = [location_id]
    bindings["source_npc_id"] = ordered[0]
    bindings["target_npc_id"] = ordered[1]
    return director.refresh(
        world,
        reason="meaningful_discovery",
        trigger="incident_possibility",
        source_id=incident_id,
        bindings=bindings,
        rumor=record.get("premise") or "",
        evidence_id=incident_id,
        campaign_id=campaign_id,
    )


def aftermath_seed(action_result):
    """Return an aftermath trigger dict when a structured adventure closed."""
    if not isinstance(action_result, dict):
        return None
    status = action_result.get("adventure_status") or action_result.get("quest_status")
    quest_id = action_result.get("quest_id")
    if action_result.get("action") in {"adventure_completed", "adventure_failed"}:
        status = "COMPLETED" if action_result["action"] == "adventure_completed" else "FAILED"
        quest_id = quest_id or action_result.get("source_id")
    if status not in {"COMPLETED", "FAILED"} or not isinstance(quest_id, str) or not quest_id:
        return None
    return {"status": status, "source_event_id": quest_id}
