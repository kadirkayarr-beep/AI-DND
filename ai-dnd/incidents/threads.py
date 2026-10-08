"""Campaign thread index. Ids only. Depth-capped. Not a canon store."""

from __future__ import annotations

import hashlib

KEY = "incident_threads"
MAX_DEPTH = 4
MAX_THREADS = 32
_FIELDS = frozenset({"thread_id", "incident_ids", "depth"})


def empty():
    return []


def validate(raw):
    if not isinstance(raw, list) or len(raw) > MAX_THREADS:
        raise ValueError("Olay iplik listesi geçersiz.")
    seen = set()
    for row in raw:
        if not isinstance(row, dict) or set(row) != _FIELDS:
            raise ValueError("Olay ipliği geçersiz.")
        thread_id = row["thread_id"]
        ids = row["incident_ids"]
        depth = row["depth"]
        if (
            not isinstance(thread_id, str) or not thread_id or thread_id in seen
            or not isinstance(ids, list) or not ids or len(ids) > MAX_DEPTH
            or any(not isinstance(item, str) or not item for item in ids)
            or len(ids) != len(set(ids))
            or type(depth) is not int or depth != len(ids) or depth > MAX_DEPTH
        ):
            raise ValueError("Olay ipliği geçersiz.")
        seen.add(thread_id)
    return raw


def read(world):
    raw = world.get(KEY)
    if raw is None:
        return empty()
    return validate(list(raw))


def ensure(world):
    if KEY not in world:
        world[KEY] = empty()
    validate(world[KEY])
    return world[KEY]


def attach(world, incident_id, parent_incident_id=None):
    """Index ``incident_id``. Depth at the cap starts a new thread."""
    if not isinstance(incident_id, str) or not incident_id:
        return None
    rows = ensure(world)
    for row in rows:
        if incident_id in row["incident_ids"]:
            return row["thread_id"]
    parent = None
    if isinstance(parent_incident_id, str):
        parent = next((row for row in rows if parent_incident_id in row["incident_ids"]), None)
    if parent is not None and parent["depth"] < MAX_DEPTH:
        parent["incident_ids"].append(incident_id)
        parent["depth"] = len(parent["incident_ids"])
        thread_id = parent["thread_id"]
    else:
        if len(rows) >= MAX_THREADS:
            return None
        digest = hashlib.sha256(incident_id.encode("utf-8")).hexdigest()[:16]
        thread_id = f"thr.{digest}"
        rows.append({"thread_id": thread_id, "incident_ids": [incident_id], "depth": 1})
    record = world.get("incidents", {}).get(incident_id)
    if isinstance(record, dict):
        record["thread_id"] = thread_id
    return thread_id
