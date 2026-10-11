"""Director V2 weighting. Scores are not campaign canon and are not saved."""

from __future__ import annotations

from adventure import templates
from adventure.director import _open_count, _recent, pacing_for

STYLE_SIGNALS = ("cautious", "direct", "curious")


def style_signal(world):
    """Derived from committed recent categories. Weighting only."""
    recent = _recent(world)
    if recent.count("combat") >= 2:
        return "direct"
    if recent.count("investigation") >= 2:
        return "curious"
    return "cautious"


def scores(world, lore_state=None):
    """Return template weights. Callers must not persist this table."""
    recent = _recent(world)
    incidents = world.get("incidents") or {}
    threads = world.get("incident_threads") or []
    open_incidents = sum(
        1 for row in incidents.values()
        if isinstance(row, dict) and row.get("lifecycle") in {"PRESENT", "ENGAGED"}
    )
    standing = 0
    if lore_state is not None:
        rows = getattr(lore_state, "faction_standings", ()) or ()
        standing = sum(getattr(row, "standing", 0) for row in rows[:4])
    level = world.get("flags", {}).get("turn_index", 0)
    fail_forward = sum(
        1 for quest in world.get("quests", [])
        if isinstance(quest, dict) and quest.get("follow_up_key")
    )
    table = {name: 1 for name in templates.TEMPLATES}
    if recent.count("combat") >= 2:
        table["BOUNTY"] += 3
        table["MONSTER_HUNT"] += 2
    if open_incidents:
        table["RECOVERY"] += 2
        table["URBAN_INVESTIGATION"] += 1
    if threads:
        table["DUNGEON_DELVE"] += min(2, len(threads))
    if standing > 0:
        table["FACTION_CONFLICT"] += 1
    if fail_forward:
        table["DELIVERY"] += 1
    if isinstance(level, int) and level > 20:
        table["SOCIAL_INTRIGUE"] += 1
    table["_pacing"] = pacing_for(world)
    table["_style"] = style_signal(world)
    table["_open_adventures"] = _open_count(world.get("quests", []))
    return table


def choose(world, lore_state=None):
    table = scores(world, lore_state)
    used = {
        item.get("template_id")
        for item in world.get("quests", [])
        if isinstance(item, dict)
    }
    ranked = sorted(
        (weight, name) for name, weight in table.items()
        if name in templates.TEMPLATES
    )
    ranked.reverse()
    for _weight, name in ranked:
        if name not in used:
            return name
    return ranked[0][1] if ranked else "MISSING_PERSON"
