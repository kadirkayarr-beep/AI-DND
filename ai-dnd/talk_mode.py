"""Talk mode: the one writer of the three conversation fields in ``world["flags"]`` (Dilim 2, tasarım §2.6).

Every open and close goes through here; the engine and the API read the conversation through ``current``, with one
list (``people_here``) and one filter (tasarım karar 18, 48, 49, 51, 62). Reading the fields elsewhere is free.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

FIELDS = ("active_npc_id", "active_npc_until_turn", "last_npc_id")
WINDOW_TURNS = 6
REASONS = ("ended", "combat", "walking", "rest", "moved", "death", "repair", "target_gone", "addressed_absent")
# Closing for these reasons also forgets the last person spoken to.
_FORGETS_LAST = frozenset({"rest", "moved", "death", "addressed_absent"})


def _flags(world: dict) -> dict:
    return world.setdefault("flags", {})


def open(world: dict, npc_id: str, *, turn: int, turns: int = WINDOW_TURNS) -> None:  # noqa: A001 - the plan's name
    """Talk with ``npc_id`` from now until ``turn + turns``."""
    flags = _flags(world)
    flags["last_npc_id"] = npc_id
    flags["active_npc_id"] = npc_id
    flags["active_npc_until_turn"] = turn + turns


def close(world: dict, reason: str) -> bool:
    """Write the closed values every time; True when someone was being talked to before the call."""
    if reason not in REASONS:
        raise ValueError(f"unknown talk mode close reason: {reason!r}")
    flags = _flags(world)
    was_open = bool(flags.get("active_npc_id"))
    flags["active_npc_id"] = None
    flags["active_npc_until_turn"] = -1
    if reason in _FORGETS_LAST:
        flags["last_npc_id"] = None
    return was_open


def fresh() -> dict:
    """The fields of a new world, a new dict each call."""
    return {"last_npc_id": None, "active_npc_id": None, "active_npc_until_turn": -1}


def snapshot(world: dict) -> dict:
    """The fields that are present, deep-copied (an absent field stays absent on restore)."""
    flags = world.get("flags") or {}
    return {key: copy.deepcopy(flags[key]) for key in FIELDS if key in flags}


def restore(world: dict, saved: dict) -> None:
    """Drop the three fields, then put back exactly what ``saved`` holds."""
    flags = _flags(world)
    for key in FIELDS:
        flags.pop(key, None)
    flags.update(copy.deepcopy(saved))


def people_here(world: dict) -> list[dict]:
    """Who the player can see here: the one list both the engine and the API read the conversation from."""
    import exploration
    import scheduled_events
    here = world.get("location")
    return exploration.player_entities(world, [npc for npc in scheduled_events.visible_npcs(world)
                                               if npc.get("location") == here])


def current(world: dict, people: list[dict] | None = None) -> dict | None:
    """The person being talked to now: no fight, inside the window, here, among the people, not dead or out cold."""
    if not isinstance(world, Mapping):
        return None
    combat = world.get("combat")
    if isinstance(combat, Mapping) and combat.get("active"):
        return None
    flags = world.get("flags", {})
    if not isinstance(flags, Mapping):
        return None
    active_id = flags.get("active_npc_id")
    if not isinstance(active_id, str) or not active_id:
        return None
    turn_index = flags.get("turn_index", 0)
    active_until = flags.get("active_npc_until_turn", -1)
    if type(turn_index) is not int or type(active_until) is not int or turn_index > active_until:
        return None
    here = world.get("location")
    return next((npc for npc in (people_here(world) if people is None else people)
                 if isinstance(npc, dict) and npc.get("id") == active_id and npc.get("location") == here
                 and npc.get("combat_status") not in {"dead", "unconscious"}), None)


@dataclass(frozen=True)
class Addressee:
    status: Literal["person", "nobody_here", "none_named"]
    npc: dict | None
    word: str | None


def addressee(world: dict, people: list[dict], *, target_id: str | None = None, named_id: str | None = None,
              named_word: str | None = None, active: str | None = None, last_id: str | None = None) -> Addressee:
    """Who a line is for. A target on the screen or a person the line names wins; a word for someone who is not among
    ``people`` means nobody is here (no talk opens); with no word at all, today's order: the active person, the last
    one spoken to, the one person here. ``active`` and ``last_id`` are what the caller has already checked."""
    def listed(npc_id):
        if not isinstance(npc_id, str) or not npc_id:
            return None
        return next((npc for npc in people if isinstance(npc, dict) and npc.get("id") == npc_id), None)

    found = listed(target_id) or listed(named_id)
    if found is not None:
        return Addressee("person", found, None)
    if isinstance(named_word, str) and named_word.strip():
        return Addressee("nobody_here", None, named_word.strip())
    found = listed(active) or listed(last_id)
    if found is None and len(people) == 1 and isinstance(people[0], dict):
        found = people[0]
    return Addressee("person", found, None) if found is not None else Addressee("none_named", None, None)
