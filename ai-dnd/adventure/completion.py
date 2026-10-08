"""Primary success ignores optional objectives. Secrets stay hidden until revealed."""

from __future__ import annotations


def required(quest):
    return [
        item for item in quest.get("objectives", [])
        if isinstance(item, dict) and item.get("optional") is not True
    ]


def primary_success(quest):
    rows = required(quest)
    return bool(rows) and all(item.get("graph_state") == "COMPLETE" for item in rows)


def secret_descriptions(quest):
    """Generator-only secrets. The journal must not list these."""
    return [
        item.get("description")
        for item in quest.get("objectives", [])
        if isinstance(item, dict) and item.get("visibility") == "hidden"
    ]
