"""Durable NPC disposition. Not the living-world relationship string.

Incidents emit evidence. Companion eligibility reads this owner later.
"""

from __future__ import annotations

import copy

KEY = "relationships"
MIN_SCORE = -5
MAX_SCORE = 5
FIELDS = frozenset({"score", "events"})


def empty():
    return {}


def validate(raw):
    if not isinstance(raw, dict) or len(raw) > 256:
        raise ValueError("İlişki kaydı geçersiz.")
    for npc_id, row in raw.items():
        if not isinstance(npc_id, str) or not npc_id or not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("İlişki kaydı geçersiz.")
        if type(row["score"]) is not int or not MIN_SCORE <= row["score"] <= MAX_SCORE:
            raise ValueError("İlişki kaydı geçersiz.")
        events = row["events"]
        if not isinstance(events, list) or len(events) > 24 or any(
            not isinstance(item, str) or not item or len(item) > 160 for item in events
        ):
            raise ValueError("İlişki kaydı geçersiz.")


def read(world):
    raw = world.get(KEY)
    if raw is None:
        return empty()
    validate(raw)
    return copy.deepcopy(raw)


def score(world, npc_id):
    row = world.get(KEY, {}).get(npc_id)
    if not isinstance(row, dict):
        return 0
    return int(row.get("score", 0))


def note(world, npc_id, delta, reason):
    """Apply a bounded score change. Idempotent on the same reason string."""
    if not isinstance(npc_id, str) or not npc_id or type(delta) is not int:
        raise ValueError("İlişki kaydı geçersiz.")
    if not isinstance(reason, str) or not reason or len(reason) > 160:
        raise ValueError("İlişki kaydı geçersiz.")
    table = world.setdefault(KEY, empty())
    validate(table)
    row = table.setdefault(npc_id, {"score": 0, "events": []})
    if reason in row["events"]:
        return row["score"]
    row["score"] = min(MAX_SCORE, max(MIN_SCORE, row["score"] + delta))
    row["events"] = (row["events"] + [reason])[-24:]
    validate(table)
    return row["score"]
