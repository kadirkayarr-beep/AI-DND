"""Catalog words bound to real records: what a passed look shows, what a paper says, how a shift looks.

Three files in content/world hold candidate text and nothing else. Choosing from them changes nothing: a row is
no object, clue, paper, job, coin or hour. A choice is kept only by keep(), called by the owner of the look or the
reading, and from then on that thing shows the same words. A row with a slot is used only when a real public
thread fills it, and keeping it is the player hearing of that thread, through the same writers a notice board uses.
Rows, rules and links never reach the narrator; only the bound text the player was shown does.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

import living_world

KEY = "bound_text_v1"
SCHEMA_VERSION = 1
_DIR = Path(__file__).resolve().parents[1] / "content" / "world"
DETAIL_LIMIT = 160
_LOG = logging.getLogger(__name__)
_tables: dict[str, list[dict[str, Any]]] = {}
_rules_cache: dict[str, Any] | None = None
_SLOT = re.compile(r"\{(\w+)\}")


def items(name: str) -> list[dict[str, Any]]:
    """The rows of one catalog; an unreadable file means none, never a stopped turn."""
    if name not in _tables:
        try:
            rows = json.loads((_DIR / f"{name}.json").read_text(encoding="utf-8"))["items"]
        except (OSError, ValueError, KeyError, TypeError):
            _LOG.warning("A text catalog could not be read.")
            rows = []
        _tables[name] = rows
    return _tables[name]


def rules() -> dict[str, Any]:
    global _rules_cache
    if _rules_cache is None:
        try:
            _rules_cache = json.loads((_DIR / "catalog" / "mapping.json").read_text(encoding="utf-8"))["bound_text"]
        except (OSError, ValueError, KeyError, TypeError):
            _LOG.warning("The text binding table could not be read.")
            _rules_cache = {}
    return _rules_cache


def _rank(world: dict[str, Any], *parts: Any) -> int:
    material = "\x00".join([living_world._campaign_seed(world), *(str(part) for part in parts)])
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:4], "big")


def place_tags(world: dict[str, Any], location_id: Any) -> list[str]:
    """What kind of place this record really is, in the catalog's words."""
    record = world.get("locations", {}).get(location_id)
    kind = (record.get("place_kind") if isinstance(record, dict) else None) or living_world.scene_kind(world, location_id)
    return list(rules().get("place_tags", {}).get(kind, ()))


def object_tag(*labels: Any) -> str | None:
    """What kind of thing a saved name or the reader's plain word says it is; None when no row can fit it."""
    text = " " + " ".join(living_world.normalize_text(label) for label in labels if isinstance(label, str))
    return next((tag for tag, stems in rules().get("object_words", {}).items()
                 if any(f" {stem}" in text for stem in stems)), None)


def _state(world: dict[str, Any]) -> dict[str, Any] | None:
    state = world.get(KEY)
    return state if isinstance(state, dict) and state.get("schema_version") == SCHEMA_VERSION else None


def seen(world: dict[str, Any], key: str) -> dict[str, Any] | None:
    """The words this thing already showed. Looking again recalls them and yields nothing new."""
    state = _state(world)
    return state["things"].get(key) if state else None


def _links(world: dict[str, Any]) -> list[dict[str, Any]]:
    """Public threads of this town nobody has pointed at yet: only these can fill a slot, and each only once."""
    import town_knowledge
    import world_threads
    state = _state(world)
    used = {row.get("thread_id") for row in state["things"].values()} if state else set()
    here = world.get("location")
    settlement = town_knowledge._settlement(world)
    links = []
    for thread in world_threads.active(world, settlement) if settlement else ():
        place = world.get("locations", {}).get(thread.get("place_id"))
        if thread["thread_id"] in used or not isinstance(place, dict) or place.get("hidden") or thread.get("place_id") == here:
            continue
        name = str(place.get("name") or "")
        owner = world_threads.owner_of(world, thread)
        known = (isinstance(owner, dict) and owner.get("location") != here and owner.get("name")
                 and living_world.npc_name_known_to_player(owner))
        links.append({"thread_id": thread["thread_id"], "yer": name,
                      **({"is": f"{name} işi"} if thread["type"] != "trouble" else {}),
                      **({"kisi": owner["name"]} if known else {})})
    return links


def _bound(row: dict[str, Any], links: list[dict[str, Any]], limit: int) -> dict[str, Any] | None:
    """The row with every slot filled from one real thread, or None. A name too long leaves the row out, never cut."""
    slots = row.get("slots") or []
    if not slots:
        return {"id": row["id"], "text": row["text"]} if len(row["text"]) <= limit else None
    for link in links:
        if all(slot in link for slot in slots):
            text = _SLOT.sub(lambda found: link[found.group(1)], row["text"])
            if len(text) <= limit:
                return {"id": row["id"], "text": text, "thread_id": link["thread_id"]}
    return None


def _first_fit(world: dict[str, Any], key: str, rows: Iterable[dict[str, Any]], limit: int) -> dict[str, Any] | None:
    """A seeded order, rows that lead somewhere before rows that do not; no row twice in one campaign."""
    state = _state(world)
    used = {row.get("id") for row in state["things"].values()} if state else set()
    fresh = sorted((row for row in rows if row["id"] not in used), key=lambda row: _rank(world, key, row["id"]))
    links = sorted(_links(world), key=lambda link: _rank(world, key, link["thread_id"]))
    for row in sorted(fresh, key=lambda row: not row.get("slots")):
        chosen = _bound(row, links, limit)
        if chosen is not None:
            return chosen
    return None


def choose_detail(world: dict[str, Any], key: str, tags: list[str], tag: str | None) -> dict[str, Any] | None:
    """The detail that fits this real thing in this real place. Writes nothing."""
    if tag is None:
        return None
    skipped = set(rules().get("needs_a_seen_sample", ()))
    return _first_fit(world, key, (row for row in items("scene_details")
                                   if row["id"] not in skipped and tag in row["object_tags"]
                                   and set(row["place_tags"]) & set(tags)), DETAIL_LIMIT)


def detail_of(world: dict[str, Any], key: str, tag: str | None, passed: bool) -> str | None:
    """The detail of this real thing: what it showed before, or on a pass what fits it and its place."""
    import world_threads
    kept = seen(world, key)
    if kept is not None:
        return kept["text"]
    if not passed or tag is None:
        return None
    world_threads.ensure(world)
    choice = choose_detail(world, key, place_tags(world, world.get("location")), tag)
    if choice is None:
        return None
    keep(world, key, choice)
    return choice["text"]


def keep(world: dict[str, Any], key: str, choice: dict[str, Any], **extra: Any) -> None:
    """The one writer: this thing now shows these words, and a thread they name has been heard of."""
    import town_knowledge
    import world_threads
    state = _state(world)
    if state is None:
        state = world[KEY] = {"schema_version": SCHEMA_VERSION, "things": {}}
    state["things"][key] = {**choice, **extra}
    thread = world_threads.by_id(world, choice.get("thread_id"))
    if thread is not None:
        town_knowledge.hear_of(world, thread)
