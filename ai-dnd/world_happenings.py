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
OUTCOMES = ("visit", "closed", "lost")
RECENT_SECONDS = 2 * world_threads.DAY  # how long it stays what people talk about
HAPPENED = "happened"  # in the clock's list of effects: the ledger gained a row for this thread


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


def _outcome_of(seed: str, thread: dict[str, Any]) -> str:
    return OUTCOMES[world_threads._rank(seed, thread["thread_id"], "fired") % len(OUTCOMES)]


def _line_for(world: dict[str, Any], seed: str, thread: dict[str, Any], lines: Any) -> str:
    """The first line that fits once the place's name is in; a long name gets a short one, never a cut."""
    place = world.get("locations", {}).get(thread["place_id"]) or {}
    lines = list(lines or ())
    start = world_threads._rank(seed, thread["thread_id"], "line") % max(len(lines), 1)
    for line in (*lines[start:], *lines[:start]):
        filled = world_threads.sentence(world_threads._fill(line, place=place.get("name", "")))
        if fits(filled):
            return filled
    return world_threads.job_lines("trouble", "fired_short") or ""


def fire_due(world: dict[str, Any], state: dict[str, Any], now: int) -> list[tuple[str, str]]:
    """Every closed trouble whose moment has come. Called with the state in hand, inside the clock's step."""
    seed = world_threads.living_world._campaign_seed(world)
    due = sorted((t for t in state["history"] if (world_threads.fires_at(t) or now + 1) <= now),
                 key=world_threads.fires_at)
    effects = []
    for thread in due:
        at = thread.pop("fires_at")
        kind = _outcome_of(seed, thread)
        line = _line_for(world, seed, thread, world_threads.job_lines("trouble", "fired_lines", kind))
        write(state, thread, kind, at, line, known=world.get("location") == thread["place_id"])
        effects.append((thread["thread_id"], HAPPENED))
    return effects


def _row_of(state: dict[str, Any], thread: dict[str, Any]) -> dict[str, Any] | None:
    return next((row for row in reversed(state.get(KEY) or []) if row["thread_id"] == thread.get("thread_id")), None)


def line_of(state: dict[str, Any], thread: dict[str, Any]) -> str | None:
    row = _row_of(state, thread)
    return row["line"] if row else None


def show(world: dict[str, Any], thread: dict[str, Any]) -> None:
    """The player was standing there: it is simply what they see next."""
    import world_reactions
    state = world_threads.view(world)
    row = _row_of(state, thread) if state else None
    if row and row["known_to_player"] and world.get("location") == row["place_id"]:
        world_reactions._wait_line(world, row["place_id"], row["line"])


def learned(world: dict[str, Any], thread: dict[str, Any]) -> None:
    state = world_threads.view(world)
    row = _row_of(state, thread) if state else None
    if row:
        row["known_to_player"] = True


def arrival_line(world: dict[str, Any], place_id: Any) -> str | None:
    """Coming back: what happened here while you were away, once."""
    state = world_threads.view(world)
    for row in reversed((state or {}).get(KEY) or []):
        if row["place_id"] == place_id and not row["known_to_player"]:
            thread = world_threads.by_id(world, row["thread_id"])
            row["known_to_player"] = True
            if thread is not None:
                world_threads.learn_outcome(world, thread)
            return row["line"]
    return None


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
