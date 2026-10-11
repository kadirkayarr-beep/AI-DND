"""Canonical incident commit and lifecycle. Python writes; the model never does.

Commit runs inside the turn: the caller's autosave persists it, and a failed
autosave rolls the whole session back. The canon stamp is checked again here,
before any write.
"""

from __future__ import annotations

import copy
import hashlib

from incidents import awareness
from incidents import envelope as envelope_owner
from incidents import state as emergence_state
from incidents import versions
from incidents.models import OPEN_LIFECYCLES, validate_incident

MAX_CLOSED_EPHEMERAL = 32
MAX_RECENT_CATEGORIES = 12


class StaleCommit(RuntimeError):
    """The canon stamp moved. Nothing was written."""


def incident_id_for(campaign_id, trigger_id):
    digest = hashlib.sha256(f"{campaign_id}:{trigger_id}".encode("utf-8")).hexdigest()
    return "inc." + digest[:24]


def build_record(envelope, normalized, *, clock):
    incident_id = incident_id_for(envelope["campaign_id"], envelope["trigger_id"])
    facts = {}
    for index, text in enumerate(normalized["surface_facts"], 1):
        facts[f"f.s{index}"] = text
    hidden_ids = []
    for index, text in enumerate(normalized["hidden_facts"], 1):
        facts[f"f.h{index}"] = text
        hidden_ids.append(f"f.h{index}")
    props = {
        f"{incident_id}.p{index}": {
            "label": prop["label"], "appearance": prop["appearance"],
            "state": "scene", "promoted_ref": None,
        }
        for index, prop in enumerate(normalized["props"], 1)
    }
    people = {
        f"{incident_id}.n{index}": {
            "label": person["label"], "role": person["role"], "name": person["name"],
            "traits": list(person["traits"]), "backstory": person["backstory"],
            "state": "passerby", "npc_id": None,
        }
        for index, person in enumerate(normalized["people"], 1)
    }
    subscene = normalized["subscene"]
    record = {
        "incident_id": incident_id,
        "category": normalized["category"],
        "tier": min(normalized["persistence_tier"], envelope["tier_ceiling"]),
        "lifecycle": "PRESENT",
        "location_id": envelope["location_id"],
        "premise": normalized["premise"],
        "entity_refs": list(normalized["existing_refs"]),
        "prop_refs": list(props),
        "subscene_ref": f"{incident_id}.place" if subscene else None,
        "hooks": list(normalized["hooks"]),
        "reward_class": normalized["reward_class"],
        "hidden_fact_ids": hidden_ids,
        "details": {
            "facts": facts,
            "props": props,
            "subscene": None if not subscene else {
                "label": subscene["label"], "kind": subscene["kind"],
                "description": subscene["description"], "promoted_location_id": None,
            },
            "people": people,
        },
        "trigger_id": envelope["trigger_id"],
        "created_clock": clock,
        "expiry_clock": clock + int(normalized["expiry_seconds"]),
        "thread_id": None,
        **versions.current(),
    }
    return validate_incident(incident_id, record)


def commit(world, envelope, normalized, *, lore_state=None):
    """Write one accepted incident and return its id.

    A repeated commit of the same trigger returns the existing id unchanged.
    """
    incident_id = incident_id_for(envelope["campaign_id"], envelope["trigger_id"])
    rows = world.setdefault("incidents", {})
    if incident_id in rows:
        return incident_id
    if envelope_owner.is_stale(world, envelope, lore_state):
        raise StaleCommit(envelope["trigger_id"])
    record = build_record(envelope, normalized, clock=emergence_state.clock(world))
    rows[incident_id] = copy.deepcopy(record)
    state = emergence_state.ensure(world)
    state["recent_categories"] = (state["recent_categories"] + [record["category"]])[-MAX_RECENT_CATEGORIES:]
    if world.get("location") == record["location_id"]:
        awareness.witness(world, record)
    return incident_id


def _close(record, lifecycle):
    """Close an incident. Passersby, scene props, and an unpromoted place go."""
    record["lifecycle"] = lifecycle
    details = record["details"]
    details["people"] = {
        person_id: person for person_id, person in details["people"].items()
        if person["state"] == "promoted"
    }
    details["props"] = {
        prop_id: prop for prop_id, prop in details["props"].items()
        if prop["state"] != "scene"
    }
    record["prop_refs"] = [prop_id for prop_id in record["prop_refs"] if prop_id in details["props"]]
    subscene = details["subscene"]
    if subscene is not None and subscene["promoted_location_id"] is None:
        details["subscene"] = None
        record["subscene_ref"] = None


def advance(world, before_location=None):
    """Scene exit ignores what was left behind. The clock expires the rest.

    Returns the ids whose lifecycle changed.
    """
    rows = world.get("incidents")
    if not isinstance(rows, dict) or not rows:
        return []
    now = emergence_state.clock(world)
    here = world.get("location")
    changed = []
    for incident_id in sorted(rows):
        record = rows[incident_id]
        if record["lifecycle"] not in OPEN_LIFECYCLES:
            continue
        if record["expiry_clock"] is not None and record["expiry_clock"] <= now:
            _close(record, "EXPIRED")
            changed.append(incident_id)
        elif before_location == record["location_id"] and here != before_location:
            if record["lifecycle"] == "PRESENT":
                _close(record, "IGNORED")
                changed.append(incident_id)
            elif record["tier"] == 1:
                _close(record, "EXPIRED")
                changed.append(incident_id)
    _prune(rows)
    return changed


def engage(world, incident_id):
    record = world.get("incidents", {}).get(incident_id)
    if record is None or record["lifecycle"] != "PRESENT":
        return False
    record["lifecycle"] = "ENGAGED"
    return True


def resolve(world, incident_id):
    record = world.get("incidents", {}).get(incident_id)
    if record is None or record["lifecycle"] not in OPEN_LIFECYCLES:
        return False
    _close(record, "RESOLVED")
    return True


def _prune(rows):
    """Closed tier-1 fiction may vanish. Durable tiers stay as canon."""
    closed = sorted(
        (row for row in rows.values() if row["tier"] == 1 and row["lifecycle"] not in OPEN_LIFECYCLES),
        key=lambda row: (row["created_clock"], row["incident_id"]),
    )
    for row in closed[:max(0, len(closed) - MAX_CLOSED_EPHEMERAL)]:
        del rows[row["incident_id"]]
