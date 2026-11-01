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
