"""Operational emergence state on world["emergence_state"].

Budgets, cooldowns, and recent categories live here. They are Python-owned
weighting state. They are not incident canon and never reach the player.
"""

from __future__ import annotations

import copy

KEY = "emergence_state"
_FIELDS = frozenset({"budget", "cooldowns", "recent_categories", "paid_signatures"})


def empty():
    return {"budget": {}, "cooldowns": {}, "recent_categories": [], "paid_signatures": []}


def read(world):
    """Return a validated copy. Missing state means nothing happened yet."""
    raw = world.get(KEY)
    if raw is None:
        return empty()
    validate(raw)
    return copy.deepcopy(raw)


def ensure(world):
    if KEY not in world:
        world[KEY] = empty()
    validate(world[KEY])
    return world[KEY]


def validate(raw):
    if not isinstance(raw, dict) or set(raw) != _FIELDS:
        raise ValueError("Olay işletim durumu geçersiz.")
    for field in ("budget", "cooldowns"):
        table = raw[field]
        if not isinstance(table, dict) or len(table) > 256 or any(
            not isinstance(key, str) or type(value) is not int or value < 0
            for key, value in table.items()
        ):
            raise ValueError("Olay işletim durumu geçersiz.")
    for field, limit in (("recent_categories", 12), ("paid_signatures", 512)):
        items = raw[field]
        if not isinstance(items, list) or len(items) > limit or any(
            not isinstance(item, str) or not item or len(item) > 160 for item in items
        ):
            raise ValueError("Olay işletim durumu geçersiz.")


def clock(world):
    """Campaign seconds from the server clock. Never wall time."""
    state = world.get("campaign_time")
    if isinstance(state, dict) and type(state.get("elapsed_seconds")) is int:
        return state["elapsed_seconds"]
    return 0
