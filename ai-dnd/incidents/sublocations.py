"""Promote an ephemeral micro-location to a campaign-local child location.

The row shape matches existing parent_location_id records. This is not a
second geography system. Districts, cities, and temples are refused.
"""

from __future__ import annotations

from incidents import commit
from incidents.gate import _GEOGRAPHY

ALLOWED_KINDS = frozenset({
    "alley", "back_room", "cellar", "campsite", "dock_corner", "shed", "clearing",
})
FORBIDDEN_IDS = frozenset({
    "neverwinter", "waterdeep", "baldurs_gate", "baldur's_gate",
    "fr:city:neverwinter", "fr:city:waterdeep", "fr:city:baldurs_gate",
})
MAX_LOCATIONS = 80


class PlaceError(ValueError):
    """The descriptor cannot become a location row."""


def _next_id(world):
    locations = world.setdefault("locations", {})
    number = max(1, int(world.get("next_location_number", 1)))
    while f"location_{number:03d}" in locations:
        number += 1
    world["next_location_number"] = number + 1
    return f"location_{number:03d}"


def promote(world, record):
    """Write one child of the incident's verified location. Idempotent."""
    details = record["details"]
    subscene = details["subscene"]
    if subscene is None:
        raise PlaceError("no_subscene")
    existing_id = subscene.get("promoted_location_id")
    if existing_id:
        existing = world.get("locations", {}).get(existing_id)
        if not isinstance(existing, dict):
            raise PlaceError("missing_location")
        return existing
    kind = subscene["kind"]
    if kind not in ALLOWED_KINDS:
        raise PlaceError("geography")
    if _GEOGRAPHY.search(subscene["label"]) or _GEOGRAPHY.search(subscene["description"]):
        raise PlaceError("geography")
    parent_id = record["location_id"]
    locations = world.setdefault("locations", {})
    parent = locations.get(parent_id)
    if not isinstance(parent, dict):
        raise PlaceError("unknown_parent")
    if len(locations) >= MAX_LOCATIONS:
        raise PlaceError("location_cap")
    for row in locations.values():
        if (
            isinstance(row, dict)
            and row.get("parent_location_id") == parent_id
            and row.get("scene_kind") == kind
            and str(row.get("name", "")).casefold() == subscene["label"].casefold()
        ):
            subscene["promoted_location_id"] = row.get("id")
            if record["lifecycle"] == "PRESENT":
                commit.engage(world, record["incident_id"])
            return row
    location_id = _next_id(world)
    if location_id in FORBIDDEN_IDS or location_id in locations:
        raise PlaceError("canonical_id")
    row = {
        "id": location_id,
        "name": subscene["label"],
        "type": "site",
        "aliases": [subscene["label"], kind],
        "description": subscene["description"],
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "parent_location_id": parent_id,
        "exit_location_id": parent_id,
        "scene_kind": kind,
        "tags": ["campaign_local", "micro_location"],
    }
    locations[location_id] = row
    subscene["promoted_location_id"] = location_id
    if record["lifecycle"] == "PRESENT":
        commit.engage(world, record["incident_id"])
    return row


def apply_action(world, action_result):
    if not isinstance(action_result, dict) or action_result.get("success") is not True:
        return None
    if not action_result.get("enter_subscene"):
        return None
    record = world.get("incidents", {}).get(action_result.get("incident_id"))
    if record is None:
        return None
    try:
        return promote(world, record)
    except PlaceError:
        return None
