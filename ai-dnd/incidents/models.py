"""Canonical incident records on world["incidents"].

This module validates durable records and loads them. It does not generate
incidents, call a model, or repair a bad save.
"""

from __future__ import annotations

import copy
import re

from incidents import versions

INCIDENT_FIELDS = frozenset({
    "incident_id",
    "category",
    "tier",
    "lifecycle",
    "location_id",
    "premise",
    "entity_refs",
    "prop_refs",
    "subscene_ref",
    "hooks",
    "reward_class",
    "hidden_fact_ids",
    "details",
    "trigger_id",
    "created_clock",
    "expiry_clock",
    "thread_id",
}) | frozenset(versions.VERSION_FIELDS)

LIFECYCLES = frozenset({
    "PRESENT",
    "ENGAGED",
    "RESOLVED",
    "IGNORED",
    "EXPIRED",
})
OPEN_LIFECYCLES = frozenset({"PRESENT", "ENGAGED"})

DURABLE_TIERS = frozenset({1, 2, 3, 4})

REWARD_CLASSES = ("none", "trinket", "coin_small", "coin_modest", "mundane_item", "rare_find")

PROP_STATES = frozenset({"scene", "taken", "placed"})
PERSON_STATES = frozenset({"passerby", "promoted"})

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_LIST_FIELDS = ("entity_refs", "prop_refs", "hidden_fact_ids", "hooks")
_LIST_LIMIT = 16
_SHORT = 80
_TEXT = 400


def fail():
    raise ValueError("Olay kaydı geçersiz.")


def empty_incidents():
    """A new incident map. Callers must not share the returned dict."""
    return {}


def load_incidents(world):
    """Return a deep copy of world["incidents"].

    A missing key is an empty map. A present but invalid value raises.
    The input world is left unchanged.
    """
    if not isinstance(world, dict):
        fail()
    if "incidents" not in world:
        return empty_incidents()
    raw = world["incidents"]
    if not isinstance(raw, dict):
        fail()
    loaded = empty_incidents()
    seen = set()
    for key, record in raw.items():
        checked = validate_incident(key, record, seen)
        loaded[checked["incident_id"]] = checked
    return loaded


def validate_incident(key, record, seen=None):
    """Fail closed unless ``record`` is one complete canonical incident."""
    seen = set() if seen is None else seen
    if not isinstance(key, str) or not isinstance(record, dict):
        fail()
    if set(record) != INCIDENT_FIELDS:
        fail()
    incident_id = record.get("incident_id")
    if incident_id != key or incident_id in seen or not is_id(incident_id):
        fail()
    loaded = versions.load_record(record, fail)
    seen.add(incident_id)
    if not is_token(loaded.get("category")):
        fail()
    tier = loaded.get("tier")
    if type(tier) is not int or tier not in DURABLE_TIERS:
        fail()
    if loaded.get("lifecycle") not in LIFECYCLES:
        fail()
    if not is_id(loaded.get("location_id")):
        fail()
    _text(loaded.get("premise"), 2000)
    for field in _LIST_FIELDS:
        _id_list(loaded.get(field), tokens=field == "hooks")
    _optional_id(loaded.get("subscene_ref"))
    if loaded.get("reward_class") not in REWARD_CLASSES:
        fail()
    if not is_id(loaded.get("trigger_id")):
        fail()
    created = loaded.get("created_clock")
    if type(created) is not int or created < 0:
        fail()
    expiry = loaded.get("expiry_clock")
    if expiry is not None and (type(expiry) is not int or expiry < created):
        fail()
    _optional_id(loaded.get("thread_id"))
    _details(loaded)
    return copy.deepcopy(loaded)


def is_id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def is_token(value):
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        fail()


def _optional_text(value, limit):
    if value is not None:
        _text(value, limit)


def _optional_id(value):
    if value is not None and not is_id(value):
        fail()


def _id_list(value, *, tokens):
    if not isinstance(value, list) or len(value) > _LIST_LIMIT:
        fail()
    seen = set()
    for item in value:
        if (not is_token(item) if tokens else not is_id(item)) or item in seen:
            fail()
        seen.add(item)


def _details(record):
    details = record.get("details")
    if not isinstance(details, dict) or set(details) != {"facts", "props", "subscene", "people"}:
        fail()
    facts = details["facts"]
    if not isinstance(facts, dict) or len(facts) > _LIST_LIMIT:
        fail()
    for fact_id, text in facts.items():
        if not is_id(fact_id):
            fail()
        _text(text, _TEXT)
    if not set(record["hidden_fact_ids"]).issubset(facts):
        fail()

    props = details["props"]
    if not isinstance(props, dict) or set(props) != set(record["prop_refs"]):
        fail()
    for prop in props.values():
        if not isinstance(prop, dict) or set(prop) != {"label", "appearance", "state", "promoted_ref"}:
            fail()
        _text(prop["label"], _SHORT)
        _text(prop["appearance"], _TEXT)
        if prop["state"] not in PROP_STATES:
            fail()
        _optional_id(prop["promoted_ref"])
        if (prop["state"] == "scene") != (prop["promoted_ref"] is None):
            fail()

    subscene = details["subscene"]
    if (subscene is None) != (record["subscene_ref"] is None):
        fail()
    if subscene is not None:
        if not isinstance(subscene, dict) or set(subscene) != {
            "label", "kind", "description", "promoted_location_id",
        }:
            fail()
        _text(subscene["label"], _SHORT)
        if not is_token(subscene["kind"]):
            fail()
        _text(subscene["description"], _TEXT)
        _optional_id(subscene["promoted_location_id"])

    people = details["people"]
    if not isinstance(people, dict) or len(people) > 6:
        fail()
    for person_id, person in people.items():
        if not is_id(person_id) or not isinstance(person, dict) or set(person) != {
            "label", "role", "name", "traits", "backstory", "state", "npc_id",
        }:
            fail()
        _text(person["label"], _SHORT)
        if not is_token(person["role"]):
            fail()
        _optional_text(person["name"], _SHORT)
        if not isinstance(person["traits"], list) or len(person["traits"]) > 4 or any(
            not is_token(item) for item in person["traits"]
        ):
            fail()
        _optional_text(person["backstory"], _TEXT)
        if person["state"] not in PERSON_STATES:
            fail()
        _optional_id(person["npc_id"])
        if (person["state"] == "promoted") != (person["npc_id"] is not None):
            fail()
