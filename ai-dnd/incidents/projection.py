"""Player-safe incident annotation. Not a quest, journal, or mission marker.

Only facts the awareness record marks known appear here. Lifecycle enums,
tiers, reward classes, hidden facts, and attempt metadata never do.
"""

from __future__ import annotations

from incidents import awareness
from incidents import state as emergence_state
from incidents.models import OPEN_LIFECYCLES

MAX_SCENE_INCIDENTS = 2
NOTICED_TEXT = "Yakınlarda bir şeyler oluyor."


def _open_here(world):
    here = world.get("location")
    now = emergence_state.clock(world)
    rows = world.get("incidents", {})
    if not isinstance(rows, dict):
        return []
    return sorted(
        (
            row for row in rows.values()
            if isinstance(row, dict) and row.get("location_id") == here
            and row.get("lifecycle") in OPEN_LIFECYCLES
            and (row.get("expiry_clock") is None or row["expiry_clock"] > now)
        ),
        key=lambda row: (row["created_clock"], row["incident_id"]),
    )


def affordances(record, known):
    """Labels built from visible people and props only."""
    labels = []
    details = record["details"]
    for person in details["people"].values():
        labels.append(f"Konuş: {person['label']}")
    for prop in details["props"].values():
        if prop["state"] == "scene":
            labels.append(f"İncele: {prop['label']}")
    if details["subscene"] is not None and details["subscene"]["promoted_location_id"] is None:
        labels.append(f"Bak: {details['subscene']['label']}")
    if known:
        labels.append("Uzak dur")
    return labels[:4]


def scene_annotation(world):
    """Return what the player may see about incidents at the current scene."""
    shown = []
    for row in _open_here(world):
        if not awareness.noticed(world, row["incident_id"]):
            continue
        known = set(awareness.known_fact_ids(world, row["incident_id"]))
        facts = [text for fact_id, text in row["details"]["facts"].items() if fact_id in known]
        details = row["details"]
        shown.append({
            "ref": row["incident_id"],
            "summary": facts[0] if facts else NOTICED_TEXT,
            "facts": facts[:4],
            "people": [person["label"] for person in details["people"].values()][:3],
            "props": [prop["label"] for prop in details["props"].values() if prop["state"] == "scene"][:3],
            "place": (
                details["subscene"]["label"]
                if details["subscene"] is not None and details["subscene"]["promoted_location_id"] is None
                else None
            ),
            "affordances": affordances(row, facts),
        })
        if len(shown) >= MAX_SCENE_INCIDENTS:
            break
    return shown
