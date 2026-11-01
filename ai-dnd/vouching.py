"""A house or a barracks does not open up to a stranger: someone has to speak for you.

There is no quest for this and no refusal. Which kinds of people can speak for the
player is drawn from the campaign seed out of content/world/catalog/mapping.json, so
one character gets in through the harbour and another through the temple. Without a
word the person is wary and says where a word would have to come from; a town where
nobody could give one keeps its door as it always was.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

import living_world
import local_places
import name_catalog
import relationships
import world_threads

SPEAKERS = 2  # how many kinds of place can speak for you in one campaign
_LOG = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _table() -> dict[str, Any]:
    try:
        return json.loads((name_catalog.CATALOG_DIR / "mapping.json").read_text(encoding="utf-8")).get("vouch_from") or {}
    except (OSError, ValueError):
        _LOG.warning("The vouching table could not be read.")
        return {}


def _kind_of(world: dict[str, Any], thread: dict[str, Any]) -> Any:
    return (world.get("locations", {}).get(thread.get("place_id")) or {}).get("place_kind")


def chosen_kinds(world: dict[str, Any], thread: dict[str, Any], kind: Any = None) -> list[str]:
    """The kinds of place whose people can speak for you at this kind of door, the same all campaign."""
    kind = kind or _kind_of(world, thread)
    seed = living_world._campaign_seed(world)
    return sorted(_table().get(kind) or (), key=lambda each: world_threads._rank(seed, "vouch", kind, each))[:SPEAKERS]


def _places(world: dict[str, Any], thread: dict[str, Any]) -> list[dict[str, Any]]:
    kinds = chosen_kinds(world, thread)
    return [record for record in world.get("locations", {}).values() if isinstance(record, dict)
            and record.get("parent_location_id") == thread.get("settlement_id") and record.get("place_kind") in kinds]


def _with_work(world: dict[str, Any], places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A word is earned by work done there: a place with nothing to do has no word to give."""
    busy = {thread.get("place_id") for thread in world_threads.owned(world)}
    return [record for record in places if record["id"] in busy]


def needs_word(world: dict[str, Any], thread: dict[str, Any], npc: dict[str, Any]) -> bool:
    """Nobody here has said anything for the player yet, and somebody could."""
    places = _places(world, thread)
    if not places or relationships.score(world, npc.get("id")) >= 1:
        return False
    ids = {record["id"] for record in places}
    return bool(_with_work(world, places)) and not any(
        isinstance(person, dict) and person.get("place_role_of") in ids
        and relationships.score(world, person.get("id")) >= 1 for person in world.get("npcs", []))


def _house_doors(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [door for door in world.get("doors", []) if isinstance(door, dict) and door.get("house_door")]


def _word_places(world: dict[str, Any], house: dict[str, Any]) -> list[dict[str, Any]]:
    """The places that could speak for the player at this house."""
    kinds = chosen_kinds(world, {}, house.get("place_kind"))
    return [record for record in world.get("locations", {}).values() if isinstance(record, dict)
            and record.get("parent_location_id") == house.get("parent_location_id") and record.get("place_kind") in kinds]


def _admits(world: dict[str, Any], door: dict[str, Any], house: dict[str, Any]) -> bool:
    """Work done for the house, someone's word, being sent for, or the day it receives."""
    keeper = local_places.resident_of(world, house.get("id"))
    ids = {record["id"] for record in _word_places(world, house)}
    return (bool(door.get("summoned")) or world_threads._now(world) >= door.get("opens_at", 0)
            or (isinstance(keeper, dict) and relationships.score(world, keeper.get("id")) >= 1)
            or any(isinstance(person, dict) and person.get("place_role_of") in ids
                   and relationships.score(world, person.get("id")) >= 1 for person in world.get("npcs", [])))


def open_doors(world: dict[str, Any]) -> list[str]:
    """Whatever earned the way in has happened: the door stops being locked, and someone standing there sees it."""
    lines = []
    for door in _house_doors(world):
        house = world.get("locations", {}).get(door.get("location")) or {}
        if door.get("locked") and _admits(world, door, house):
            door["locked"] = False
            keeper = local_places.resident_of(world, house.get("id"))
            if world.get("location") == house.get("id") and isinstance(keeper, dict):
                who = living_world.turkish_initial_upper(living_world.public_npc_name(keeper))
                lines.append(world_threads._fill(world_threads.job_lines("text", "house_opens") or "", who=who))
    return lines


def shut_line(world: dict[str, Any], door: dict[str, Any]) -> str | None:
    """Why this door stays shut, in the house's own words, with the ways round it. Never a figure."""
    if not door.get("house_door"):
        return None
    import world_happenings
    house = world.get("locations", {}).get(door.get("location")) or {}
    keeper = local_places.resident_of(world, house.get("id"))
    if not isinstance(keeper, dict) or keeper.get("combat_status") == "dead":
        return None  # nobody left to stand in the way: it is only a locked door now
    who = living_world.turkish_initial_upper(living_world.public_npc_name(keeper))
    return world_threads._fill(world_threads.job_lines("text", "house_shut") or "", who=who,
                               when=world_happenings._spoken_time(world, door.get("opens_at", 0)), how=_ways(world, house))


def _ways(world: dict[str, Any], house: dict[str, Any]) -> str:
    words = world_threads.job_lines("text") or {}
    places = _with_work(world, _word_places(world, house))
    if places:
        return world_threads._fill(words.get("house_way_word", ""), place=places[0].get("name", ""))
    return words.get("house_way_work", "")


def head_title(world: dict[str, Any], place_id: Any) -> str | None:
    """Who a house's seal really belongs to; a place with no inner room answers for itself."""
    room = local_places.inner_room_of(world, place_id)
    return local_places.PLACE_KINDS[room["place_kind"]]["role"].casefold() if room else None


def summoned(world: dict[str, Any], link: dict[str, Any]) -> None:
    """Being sent for is a way in."""
    room = local_places.inner_room_of(world, link.get("place_id"))
    for door in _house_doors(world):
        if room and door.get("id") == f"venue-door:{room['id']}":
            door["summoned"] = True


def house_note(world: dict[str, Any], npc: Any) -> str:
    """The keeper knows why the door is shut and how it opens; the one behind it knows who runs the house."""
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    place = world.get("locations", {}).get(place_id) or {}
    shared = world_threads.job_lines("shared") or {}
    if place.get("inner_of"):
        keeper = local_places.resident_of(world, place["inner_of"])
        work = [t["public_line"] for t in world_threads.owned(world) if t.get("place_id") == place["inner_of"]][:2]
        return " " + world_threads._fill(shared.get("house_head", ""), keeper=living_world.public_npc_name(keeper) if keeper else "kâhyan",
                                         work=" / ".join(work) or "yok")
    room = local_places.inner_room_of(world, place_id)
    door = next((d for d in _house_doors(world) if room and d.get("id") == f"venue-door:{room['id']}"), None)
    if door is None:
        return ""
    if not door.get("locked"):
        return " " + shared.get("house_open", "")
    import world_happenings
    return " " + world_threads._fill(shared.get("house_shut", ""), when=world_happenings._spoken_time(world, door.get("opens_at", 0)),
                                     how=_ways(world, place))


def wary_line(world: dict[str, Any], thread: dict[str, Any]) -> str | None:
    places = _with_work(world, _places(world, thread))
    if not places:
        return None
    return world_threads._fill(world_threads.job_lines("shared", "wary_vouch") or "", place=places[0].get("name", ""))


def speaker_note(world: dict[str, Any], npc: Any) -> str:
    """The one a door names knows what is asked of them: a word given, or one still to be earned here."""
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    record = world.get("locations", {}).get(place_id) or {}
    door = next((thread for thread in world_threads.owned(world)
                 if thread.get("settlement_id") == record.get("parent_location_id")
                 and record.get("place_kind") in chosen_kinds(world, thread)), None)
    if door is None:
        return ""
    given = relationships.score(world, npc.get("id")) >= 1
    if not given and not _with_work(world, [record]):
        return ""
    name = world.get("locations", {}).get(door["place_id"], {}).get("name", "")
    return " " + world_threads._fill(world_threads.job_lines("shared", "vouch_given" if given else "vouch_earned") or "", place=name)
