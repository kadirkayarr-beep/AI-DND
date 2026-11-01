"""What a town's troubles came to: a small ledger of things that happened without the player.

These are not deeds. `bold_acts.deeds` is what the player did and what guards answer
for; a shop closing has nothing to do with that, so it lives here, inside the world
thread state, and is kept and rolled back with it. Python writes every line and the
model only voices it.
"""

from __future__ import annotations

from typing import Any

import world_threads

KEY = "happenings"
MAX_HAPPENINGS = 16
MAX_LINE_BYTES = 90
KINDS = ("visit", "closed", "lost", "averted")
RECENT_SECONDS = 2 * world_threads.DAY  # how long it stays what people talk about


def ledger(state: dict[str, Any]) -> list[dict[str, Any]]:
    """An old save simply gains the list."""
    return state.setdefault(KEY, [])


def fits(line: str) -> bool:
    return len(line.encode("utf-8")) <= MAX_LINE_BYTES


def write(state: dict[str, Any], thread: dict[str, Any], kind: str, at: int, line: str, *,
          known: bool = False, next_thread_id: str | None = None) -> dict[str, Any]:
    row = {"thread_id": thread["thread_id"], "kind": kind, "at": at, "place_id": thread["place_id"],
           "line": line, "known_to_player": known, "next_thread_id": next_thread_id}
    rows = ledger(state)
    rows.append(row)
    del rows[:-MAX_HAPPENINGS]
    return row


def validate(rows: Any) -> None:
    """Absent is fine: that is a save from before the ledger."""
    if rows is None:
        return
    if not isinstance(rows, list) or len(rows) > MAX_HAPPENINGS:
        raise ValueError("World thread state is invalid.")
    for row in rows:
        if (
            not isinstance(row, dict) or row.get("kind") not in KINDS
            or not isinstance(row.get("thread_id"), str) or not isinstance(row.get("place_id"), str)
            or type(row.get("at")) is not int or type(row.get("known_to_player")) is not bool
            or not isinstance(row.get("line"), str) or not fits(row["line"])
            or not (row.get("next_thread_id") is None or isinstance(row.get("next_thread_id"), str))
        ):
            raise ValueError("World thread record is invalid.")


def _within_reach(world: dict[str, Any], npc: dict[str, Any], place_id: str) -> bool:
    import world_reactions
    here = npc.get("location")
    return place_id == here or place_id in world_reactions._neighbours(world, here)


def reachable(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """What this person could have heard by now: their own place or the one next door, newest first."""
    state = world_threads.view(world)
    if state is None or not isinstance(npc, dict):
        return []
    now = world_threads._now(world)
    return [row for row in reversed(state.get(KEY) or [])
            if now - row["at"] < RECENT_SECONDS and _within_reach(world, npc, row["place_id"])]


def speech_line(world: dict[str, Any], npc: Any, listed: Any = frozenset()) -> str:
    """One labelled sentence, and only if it is not already among what this person lists."""
    for row in reachable(world, npc):
        if row["thread_id"] not in listed:
            return " " + world_threads._fill(world_threads.job_lines("shared", "heard_happening") or "", heard=row["line"])
    return ""
