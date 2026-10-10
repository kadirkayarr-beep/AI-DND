"""One companion. Incident code cannot set this. Narration cannot create it."""

from __future__ import annotations

import copy

import relationships

KEY = "companions"
MAX_MEMBERS = 1
ELIGIBLE_SCORE = 4
_FIELDS = frozenset({"npc_id", "joined_turn", "source"})


def empty():
    return []


def validate(raw):
    if not isinstance(raw, list) or len(raw) > MAX_MEMBERS:
        raise ValueError("Yoldaş listesi geçersiz.")
    seen = set()
    for row in raw:
        if not isinstance(row, dict) or set(row) != _FIELDS:
            raise ValueError("Yoldaş kaydı geçersiz.")
        npc_id = row["npc_id"]
        if not isinstance(npc_id, str) or not npc_id or npc_id in seen:
            raise ValueError("Yoldaş kaydı geçersiz.")
        if type(row["joined_turn"]) is not int or row["joined_turn"] < 0:
            raise ValueError("Yoldaş kaydı geçersiz.")
        if row["source"] != "player_accepted":
            raise ValueError("Yoldaş kaydı geçersiz.")
        seen.add(npc_id)
    return raw


def eligible(world, npc_id):
    """Eligibility is a relationship threshold. It is not membership."""
    if not isinstance(npc_id, str):
        return False
    if not any(isinstance(npc, dict) and npc.get("id") == npc_id for npc in world.get("npcs", [])):
        return False
    return relationships.score(world, npc_id) >= ELIGIBLE_SCORE


def accept(world, npc_id, *, player_accepted, turn_index):
    """The player must accept. Narration and incidents cannot call this with False."""
    if player_accepted is not True:
        return None
    if not eligible(world, npc_id):
        return None
    members = world.setdefault(KEY, empty())
    validate(members)
    if any(row["npc_id"] == npc_id for row in members):
        return members[0]
    if len(members) >= MAX_MEMBERS:
        return None
    if type(turn_index) is not int or turn_index < 0:
        return None
    row = {"npc_id": npc_id, "joined_turn": turn_index, "source": "player_accepted"}
    members.append(row)
    return copy.deepcopy(row)
