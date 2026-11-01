"""What the campaign has on record for the narrator: read from the saved world, never stored.

Everything here is something the player did, was promised or found out. Nothing about what
other people know, what they think of the player, or work the player never heard of.
"""

from __future__ import annotations

import json
from typing import Any

import living_world
import npc_statements

MAX_BYTES = 900
MAX_LINE = 90
_DONE_BY_PLAYER = ("killing", "arson", "assault", "theft", "theft_unseen")
_QUEST_STATES = ("ACTIVE", "COMPLETED", "FAILED", "ABANDONED", "DISCOVERED")


def _line(text: Any) -> str:
    return " ".join(str(text).split())[:MAX_LINE]


def _place(world: dict[str, Any], location: Any) -> str:
    record = world.get("locations", {}).get(location)
    return str(record.get("name") or "") if isinstance(record, dict) else ""


def _deeds(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [deed for deed in world.get("flags", {}).get("deeds", []) if isinstance(deed, dict)]


def _did(world: dict[str, Any]) -> list[str]:
    lines = []
    for deed in _deeds(world):
        if deed.get("kind") in _DONE_BY_PLAYER:
            place = _place(world, deed.get("location"))
            lines.append(_line(f"{deed.get('text')} ({place})" if place else deed.get("text")))
    return lines[-6:]


def _said(world: dict[str, Any]) -> list[str]:
    lines = []
    for deed in _deeds(world):
        if deed.get("told"):
            lines.append(_line(f"Kendi ağzınla söyledin: {deed.get('text')}"))
    return lines[-3:]


def _promises(world: dict[str, Any]) -> list[str]:
    people = {npc.get("id"): npc for npc in world.get("npcs", []) if isinstance(npc, dict)}
    lines = []
    for promise in npc_statements.view(world).get("commitments", []):
        if promise.get("status") in {"open", "fulfilled", "broken"} and promise.get("npc_id") in people:
            who = living_world.public_npc_name(people[promise["npc_id"]])
            lines.append(_line(f"{who}: “{str(promise.get('quote', ''))[:60]}” ({promise['status']})"))
    return lines[-5:]


def _jobs(journal: dict[str, Any]) -> list[str]:
    return [_line(f"{quest.get('title')}: {quest.get('status')}") for quest in journal.get("quests", [])
            if isinstance(quest, dict) and quest.get("status") in _QUEST_STATES][-5:]


def _people(journal: dict[str, Any]) -> list[str]:
    known = [person for person in journal.get("known_npcs", []) if isinstance(person, dict)]
    return [_line(f"{person.get('name')} ({person['role']})" if person.get("role") else person.get("name"))
            for person in known[-8:]]


def _places(journal: dict[str, Any]) -> list[str]:
    return [_line(place.get("name")) for place in journal.get("discovered_locations", [])
            if isinstance(place, dict)][-6:]


def project(world: dict[str, Any], journal: dict[str, Any] | None) -> dict[str, list[str]]:
    """The same world gives the same record. Later sections are dropped first when it runs long."""
    journal = journal if isinstance(journal, dict) else {}
    sections = (
        ("did", _did(world)), ("said", _said(world)), ("promises", _promises(world)),
        ("jobs", _jobs(journal)), ("people", _people(journal)), ("places", _places(journal)),
    )
    ledger = {key: lines for key, lines in sections if lines}
    for key, _ in reversed(sections):
        while key in ledger and len(json.dumps(ledger, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
            ledger[key].pop(0)
            if not ledger[key]:
                del ledger[key]
    return ledger
