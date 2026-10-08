"""Player horizon. The generator never simulates distant places."""

from __future__ import annotations

TRIGGER_KINDS = frozenset({"arrival", "look_around", "rest", "travel_segment", "aftermath"})


def in_horizon(world, trigger):
    """True only for the current scene, segment, rest, or a nearby aftermath.

    Campaign time moving forward is not a trigger. Distant clocks belong to
    scheduled_events.
    """
    if not isinstance(trigger, dict) or trigger.get("kind") not in TRIGGER_KINDS:
        return False
    here = world.get("location")
    if not isinstance(here, str) or trigger.get("location_id") != here:
        return False
    if here not in world.get("locations", {}):
        return False
    if trigger["kind"] == "aftermath":
        return trigger.get("source_location_id") == here and bool(trigger.get("source_event_id"))
    return True
