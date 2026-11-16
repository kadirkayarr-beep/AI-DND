"""Places and trails an NPC names in speech: recorded as heard rumours, never as quests, rewards or money."""
from __future__ import annotations

import os
import re
from typing import Any

import local_places
import npc_statements
import town_knowledge

MAX_RUMOURED_PER_SETTLEMENT = 24
MAX_HEARD = 64
MAX_NAME = 60
MAX_ABOUT = 120
_NAME_SHAPE = re.compile(r"[\w .’'-]+", flags=re.UNICODE)


def lane_enabled() -> bool:
    return os.environ.get("AI_DND_RUMOUR_LANE", "1").strip().casefold() not in {"0", "off"}


def base_name(text: str) -> str:
    """'Eski Mahzen'de' -> 'Eski Mahzen': a lowercase Turkish suffix ending a word after an apostrophe goes; D'Arcy stays."""
    cleaned = re.sub(r"['’][a-zçğıöşü]{1,6}(?=[\s.,!?;:]|$)", "", str(text))
    return " ".join(cleaned.split())


def _rumoured_places(world: dict[str, Any], settlement_id: str) -> list[dict[str, Any]]:
    return [
        record for record in world.get("locations", {}).values()
        if isinstance(record, dict) and record.get("rumoured") and record.get("parent_location_id") == settlement_id
    ]


def _evict_oldest_unvisited(world: dict[str, Any], rumours: list[dict[str, Any]], settlement_id: str) -> bool:
    unvisited = [record for record in _rumoured_places(world, settlement_id) if not record.get("visited")]
    if not unvisited:
        return False
    oldest = min(unvisited, key=lambda record: int((record.get("provenance") or {}).get("turn", 0) or 0))
    del world["locations"][oldest["id"]]
    for entry in rumours:
        if entry.get("place_id") == oldest["id"]:
            entry["place_id"] = None
    return True


def _next_id(rumours: list[dict[str, Any]]) -> str:
    numbers = [int(entry["id"][7:]) for entry in rumours
               if isinstance(entry.get("id"), str) and entry["id"][7:].isdigit()]
    return f"rumour_{max(numbers, default=0) + 1:03d}"


def said_in(text: Any, name: Any) -> bool:
    """True when the folded base name occurs in the folded spoken text: a person names only what they said aloud."""
    if not isinstance(text, str) or not isinstance(name, str):
        return False
    folded = npc_statements.fold(base_name(name))
    return bool(folded) and folded in npc_statements.fold(text)


def _exact_place(world: dict[str, Any], settlement_id: str, folded: str) -> str | None:
    """A place of this settlement (or the settlement itself) whose name or alias equals the name exactly."""
    for place_id, record in world.get("locations", {}).items():
        if not isinstance(record, dict) or (place_id != settlement_id and record.get("parent_location_id") != settlement_id):
            continue
        aliases = record.get("aliases")
        names = [record.get("name"), *(aliases if isinstance(aliases, list) else [])]
        if folded in {npc_statements.fold(item) for item in names if isinstance(item, str)}:
            return place_id
    return None


def record_mention(game: Any, world: dict[str, Any], npc: dict[str, Any], mention: Any, turn: int) -> dict[str, Any] | None:
    """Store what an NPC said about a place or trail; None when rejected or the lane is off. Never raises on bad input."""
    if not lane_enabled() or not isinstance(mention, dict) or not isinstance(npc, dict):
        return None
    kind = mention.get("kind")
    if kind not in ("place", "trail"):
        return None
    raw_name = mention.get("name")
    if not isinstance(raw_name, str):
        return None
    name = base_name(raw_name)
    if not name or len(name) > MAX_NAME or not _NAME_SHAPE.fullmatch(name) or "_" in name:
        return None
    folded = npc_statements.fold(name)
    for other in world.get("npcs", []):
        if isinstance(other, dict) and folded in {npc_statements.fold(other.get("name")),
                                                    npc_statements.fold(other.get("public_name"))}:
            return None
    about = mention.get("about")
    about = " ".join(about.split())[:MAX_ABOUT] if isinstance(about, str) else ""
    proposal = game.validate_location_proposal({"name": name, "type": "building", "description": about})
    about = town_knowledge.without_unbacked_money(proposal["description"]) if proposal else ""
    settlement_id = local_places.settlement_of(world, npc.get("location"))
    if not settlement_id:
        return None
    place_kind = mention.get("place_kind")
    locations = world.get("locations")
    if not isinstance(locations, dict):
        return None
    rumours = world.get("heard_rumours")
    if not isinstance(rumours, list):
        rumours = []
    place_id = None
    if kind == "place":
        linked = _exact_place(world, settlement_id, folded)
        if linked:
            place_id = linked
        elif place_kind not in local_places.PLACE_KINDS:
            return None
    for entry in rumours:
        if entry.get("settlement_id") == settlement_id and npc_statements.fold(str(entry.get("text", "")).partition(": ")[0]) == folded:
            return entry
    if kind == "place" and place_id is None:
        if len(_rumoured_places(world, settlement_id)) >= MAX_RUMOURED_PER_SETTLEMENT:
            _evict_oldest_unvisited(world, rumours, settlement_id)
        known = set(locations)
        record = local_places.create_local_place(world, settlement_id, place_kind, name=name, rumoured=True)
        if record is not None:
            if record["id"] not in known:
                record["rumoured"] = True
                record["provenance"] = {"source": "npc_rumour", "said_by": npc.get("id"), "turn": turn}
                if about:
                    record["description"] = about
            place_id = record["id"]
    entry = {
        "id": _next_id(rumours),
        "text": f"{name}: {about}" if about else name,
        "said_by": npc.get("id"),
        "place_id": place_id,
        "settlement_id": settlement_id,
        "turn": turn,
    }
    rumours.append(entry)
    world["heard_rumours"] = rumours
    del rumours[:-MAX_HEARD]
    return entry


def heard_in_speech(world: dict[str, Any], settlement_id: str, reference: str) -> str | None:
    """The NPC of this settlement who said the name aloud (recent speech log), else None. Off when the lane is off."""
    if not lane_enabled() or not isinstance(world, dict) or not isinstance(settlement_id, str) or not settlement_id:
        return None
    log = world.get("npc_speech_log")
    if not isinstance(log, dict) or not isinstance(reference, str):
        return None
    for npc in world.get("npcs", []):
        if not isinstance(npc, dict) or local_places.settlement_of(world, npc.get("location")) != settlement_id:
            continue
        entries = log.get(npc.get("id"))
        if isinstance(entries, list) and any(isinstance(entry, dict) and said_in(entry.get("npc"), reference)
                                             for entry in entries):
            return npc["id"]
    return None
