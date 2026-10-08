"""Canonical incident records on world["incidents"].

This module validates durable records and loads them. It does not generate
incidents, call a model, or repair a bad save.
"""

from __future__ import annotations

import copy
import re

INCIDENT_FIELDS = frozenset({
    "incident_id",
    "category",
    "tier",
    "lifecycle",
    "premise",
    "entity_refs",
    "prop_refs",
    "subscene_ref",
    "hooks",
    "reward_class",
    "hidden_fact_ids",
    "trigger_id",
    "expiry_clock",
    "thread_id",
    "incident_schema_version",
    "envelope_version",
    "proposal_schema_version",
    "gate_policy_version",
})

LIFECYCLES = frozenset({
    "PRESENT",
    "ENGAGED",
    "RESOLVED",
    "IGNORED",
    "EXPIRED",
})

DURABLE_TIERS = frozenset({1, 2, 3, 4})

# The only contract tuple this model can read. Migration dispatch is later.
CONTRACT_VERSION = 1

_VERSION_FIELDS = (
    "incident_schema_version",
    "envelope_version",
    "proposal_schema_version",
    "gate_policy_version",
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_LIST_FIELDS = ("entity_refs", "prop_refs", "hidden_fact_ids", "hooks")
_LIST_LIMIT = 16


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
        checked = _incident(key, record, seen)
        loaded[checked["incident_id"]] = checked
    return loaded


def _incident(key, record, seen):
    if not isinstance(key, str) or not isinstance(record, dict):
        fail()
    if set(record) != INCIDENT_FIELDS:
        fail()
    incident_id = record.get("incident_id")
    if incident_id != key or incident_id in seen or _ID.fullmatch(incident_id or "") is None:
        fail()
    seen.add(incident_id)
    if _TOKEN.fullmatch(record.get("category") or "") is None:
        fail()
    tier = record.get("tier")
    if type(tier) is not int or tier not in DURABLE_TIERS:
        fail()
    if record.get("lifecycle") not in LIFECYCLES:
        fail()
    premise = record.get("premise")
    if not isinstance(premise, str) or not premise.strip() or len(premise) > 2000:
        fail()
    for field in _LIST_FIELDS:
        _id_list(record.get(field), tokens=field == "hooks")
    _optional_id(record.get("subscene_ref"))
    if _TOKEN.fullmatch(record.get("reward_class") or "") is None:
        fail()
    if _ID.fullmatch(record.get("trigger_id") or "") is None:
        fail()
    expiry = record.get("expiry_clock")
    if expiry is not None and (type(expiry) is not int or expiry < 0):
        fail()
    _optional_id(record.get("thread_id"))
    for field in _VERSION_FIELDS:
        if type(record.get(field)) is not int or record[field] != CONTRACT_VERSION:
            fail()
    return copy.deepcopy(record)


def _optional_id(value):
    if value is not None and _ID.fullmatch(value if isinstance(value, str) else "") is None:
        fail()


def _id_list(value, *, tokens):
    if not isinstance(value, list) or len(value) > _LIST_LIMIT:
        fail()
    seen = set()
    pattern = _TOKEN if tokens else _ID
    for item in value:
        if not isinstance(item, str) or pattern.fullmatch(item) is None or item in seen:
            fail()
        seen.add(item)
