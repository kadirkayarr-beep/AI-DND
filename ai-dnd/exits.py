"""The one owner of the way out of a place (Dilim 3, Task 4).

A building keeps its door: its saved exit (``exit_location_id``, else ``parent_location_id``). A town has no door of
its own; the first time someone has to run from its street, one side street is written for it, once, with a fixed id.
"Outside" is the outside of the building: from a room behind a door it is the street the house stands on. Readers
(the card, the place list) never write; only a flight (the player's or a witness's) may open the side street."""
from __future__ import annotations

from typing import Any

import living_world
import local_places

_BUILDING_KINDS = ("building", "tavern")


def _record(world: dict[str, Any], location_id: Any) -> dict[str, Any] | None:
    record = (world.get("locations") or {}).get(location_id)
    return record if isinstance(record, dict) else None


def _is_settlement(world: dict[str, Any], location_id: Any) -> bool:
    record = _record(world, location_id)
    return (record is not None and not record.get("parent_location_id")
            and local_places.settlement_of(world, location_id) == location_id)


def _side_street_id(settlement_id: str) -> str:
    return f"{settlement_id}:side_street"


def _saved_way_out(world: dict[str, Any], location_id: Any) -> str | None:
    record = _record(world, location_id)
    if record is None:
        return None
    out = record.get("exit_location_id") or record.get("parent_location_id")
    return out if isinstance(out, str) and out != location_id and _record(world, out) is not None else None


def side_street(world: dict[str, Any], settlement_id: str) -> dict[str, Any]:
    """The settlement's side street; written once if missing. Not a local place: no place cap counts it."""
    street_id = _side_street_id(settlement_id)
    locations = world.setdefault("locations", {})
    existing = locations.get(street_id)
    if isinstance(existing, dict):
        return existing
    record = {
        "id": street_id,
        "name": f"{_record(world, settlement_id)['name']} Ara Sokağı",
        "type": "street",
        "scene_kind": "city",
        "parent_location_id": settlement_id,
        "exit_location_id": settlement_id,
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "tags": ["campaign_local", "side_street"],
        "description": "Ana caddenin gerisinde, iki duvar arasında dar bir sokak.",
    }
    locations[street_id] = record
    return record


def way_out(world: dict[str, Any], location_id: Any, *, open_if_needed: bool = False) -> str | None:
    """The one neighbour a flight (the player's or a witness's) goes to; None when there is none."""
    if _is_settlement(world, location_id):
        if open_if_needed:
            return side_street(world, location_id)["id"]
        street_id = _side_street_id(location_id)
        return street_id if _record(world, street_id) is not None else None
    return _saved_way_out(world, location_id)


def way_out_name(world: dict[str, Any], location_id: Any) -> str | None:
    """The way out's name for readers; a town's side street not yet written is named as it would be."""
    if _is_settlement(world, location_id) and way_out(world, location_id) is None:
        return f"{_record(world, location_id)['name']} Ara Sokağı"
    out = way_out(world, location_id)
    return str(_record(world, out).get("name") or out) if out is not None else None


def outside(world: dict[str, Any], location_id: Any) -> str | None:
    """The outside of the building (K4): from a room behind a door, through every door to the street or open air.

    None for the settlement itself: "out" from its street is out of town, which is not this owner's walk."""
    if _is_settlement(world, location_id):
        return None
    seen = {location_id}
    out = way_out(world, location_id)
    while (out is not None and out not in seen and not _is_settlement(world, out)
           and living_world.scene_kind(world, out) in _BUILDING_KINDS):
        seen.add(out)
        further = way_out(world, out)
        if further is None or further in seen:
            break
        out = further
    return out
