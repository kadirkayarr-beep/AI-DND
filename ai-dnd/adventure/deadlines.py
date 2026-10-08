"""Adventure deadlines use the existing clock. Hidden offers do not expire."""

from __future__ import annotations

import scheduled_events


def arm(world, quest, *, duration_seconds=3600):
    """Start the player-facing window only after the player knows the adventure."""
    if quest.get("status") not in {"DISCOVERED", "ACTIVE"}:
        return None
    if quest.get("deadline"):
        return quest["deadline"]
    location_ids = quest.get("bindings", {}).get("location_ids") or []
    location_id = location_ids[0] if location_ids else world.get("location")
    if not isinstance(location_id, str) or location_id not in world.get("locations", {}):
        return None
    elapsed = world.get("campaign_time", {}).get("elapsed_seconds", 0)
    if type(elapsed) is not int:
        elapsed = 0
    event_id = f"adventure-deadline:{quest['quest_id']}"
    scheduled_events.register_event(
        world,
        event_id=event_id,
        window_start=elapsed,
        window_end=elapsed + duration_seconds,
        location_id=location_id,
        effects=(),
        summary="",
        behavior="NON_INTERRUPTIVE",
        visibility="hidden",
    )
    quest["deadline"] = event_id
    return event_id


def close_missed(world, quest):
    """A due remote window closes the adventure and reveals nothing new."""
    if quest.get("status") not in {"DISCOVERED", "ACTIVE", "BLOCKED"}:
        return False
    event_id = quest.get("deadline")
    if not isinstance(event_id, str):
        return False
    event = next(
        (item for item in world.get("scheduled_events", []) if item.get("event_id") == event_id),
        None,
    )
    if event is None or event.get("encounter_status") != "MISSED":
        return False
    from adventure.transitions import transition

    turn = world.get("flags", {}).get("turn_index", quest["updated_turn"])
    if not isinstance(turn, int) or turn < quest["updated_turn"]:
        turn = quest["updated_turn"]
    closed = transition(quest, "FAILED", turn, outcome="missed")
    hidden = [
        item["objective_id"]
        for item in quest.get("objectives", [])
        if item.get("graph_state") == "HIDDEN"
    ]
    quest.clear()
    quest.update(closed)
    still_hidden = [
        item["objective_id"]
        for item in quest.get("objectives", [])
        if item.get("graph_state") == "HIDDEN"
    ]
    return hidden == still_hidden
