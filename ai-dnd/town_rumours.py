"""What people only half know about a town's troubles.

A rumour is drawn from an open trouble's own record, never from a separate list, so
it always stands on something real. It is true or false by the campaign seed. A true
one repeats what the street says; a false one has the right place and nobody in it,
so no real person is ever blamed and nobody can be made to own up to it. Whether it
is true stays here: the prompt gets only the words.
"""

from __future__ import annotations

from typing import Any

import living_world
import npc_statements
import world_threads

HEARD_PERCENT = 50  # of the people who have not got the trouble itself


def is_true(world: dict[str, Any], thread: dict[str, Any]) -> bool:
    return world_threads._rank(living_world._campaign_seed(world), thread["thread_id"], "rumour") % 2 == 0


def _words_of(world: dict[str, Any], thread: dict[str, Any]) -> str | None:
    if is_true(world, thread):
        return thread["public_line"]
    lines = world_threads.catalog().get("rumour_lines") or []
    place = world.get("locations", {}).get(thread["place_id"]) or {}
    if not lines or not place.get("name"):
        return None
    line = lines[world_threads._rank(living_world._campaign_seed(world), thread["thread_id"], "rumour_line") % len(lines)]
    return world_threads.sentence(world_threads._fill(line, place=place["name"]))


def rumour_for(world: dict[str, Any], npc: dict[str, Any], settlement_id: str, percent: Any, listed: Any) -> list[dict[str, Any]]:
    """The one rumour this person carries, if any: of a trouble they do not already list, and not one of their own."""
    troubles = [t for t in world_threads.active(world, settlement_id) if t["type"] == "trouble"
                and t["thread_id"] not in listed and t["place_id"] != npc.get("place_role_of")
                and percent(npc.get("id"), "rumour", t["thread_id"]) < HEARD_PERCENT]
    troubles.sort(key=lambda t: percent(npc.get("id"), "rumour_order", t["thread_id"]))
    for thread in troubles:
        words = _words_of(world, thread)
        if words:
            return [{"kind": "rumour", "text": words, "location_id": thread["place_id"], "thread_id": thread["thread_id"]}]
    return []


def was_voiced(world: dict[str, Any], item: dict[str, Any], words: str) -> bool:
    """The reply really passed this on: at least half its own words, a place named alone does not count."""
    place = world.get("locations", {}).get(item["location_id"]) or {}
    own = npc_statements.fold(item["text"]).replace(npc_statements.fold(place.get("name", "")), " ").split()
    said = set(words.split())
    return bool(own) and sum(word in said for word in own) * 2 >= len(own)
