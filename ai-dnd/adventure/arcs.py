"""Bounded adventure arcs. At most five links. No recursive generation."""

from __future__ import annotations

MAX_LINKS = 5
KEY = "adventure_arcs"
_FIELDS = frozenset({"arc_id", "quest_ids", "depth"})


def empty():
    return []


def validate(raw):
    if not isinstance(raw, list) or len(raw) > 16:
        raise ValueError("Macera yayı geçersiz.")
    seen = set()
    for row in raw:
        if not isinstance(row, dict) or set(row) != _FIELDS:
            raise ValueError("Macera yayı geçersiz.")
        if (
            not isinstance(row["arc_id"], str) or not row["arc_id"] or row["arc_id"] in seen
            or not isinstance(row["quest_ids"], list)
            or not row["quest_ids"]
            or len(row["quest_ids"]) > MAX_LINKS
            or type(row["depth"]) is not int
            or row["depth"] != len(row["quest_ids"])
        ):
            raise ValueError("Macera yayı geçersiz.")
        seen.add(row["arc_id"])
    return raw


def extend(world, arc_id, quest_id):
    """Append one quest id. A sixth link is refused."""
    if not isinstance(arc_id, str) or not isinstance(quest_id, str):
        return None
    rows = world.setdefault(KEY, empty())
    validate(rows)
    row = next((item for item in rows if item["arc_id"] == arc_id), None)
    if row is None:
        row = {"arc_id": arc_id, "quest_ids": [], "depth": 0}
        rows.append(row)
    if quest_id in row["quest_ids"]:
        return row
    if row["depth"] >= MAX_LINKS:
        return None
    row["quest_ids"].append(quest_id)
    row["depth"] = len(row["quest_ids"])
    return row
