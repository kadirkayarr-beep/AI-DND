"""World threads: someone in town needs something, whether or not the player comes.

A thread is a small saved record: a real place, a real named person, public words
anyone may have heard, and terms only its owner speaks. Python owns all of it; the
model only voices lines handed to it and decides nothing.

Kinds are data (content/world/town_threads.json, plus the authored catalog read
through thread_catalog.py). Every campaign draws its own
number, mix and wiring of places from its seed, so two campaigns differ in shape
as well as in names. Nothing here is written for one character or one story.

State lives under world[KEY], seeded lazily the first time it is needed, so an old
save simply gains it. Offer window, work days and pay stay separate: time passing
closes an unanswered offer, it never counts as work or pays anyone.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import living_world
import local_places

KEY = "world_threads_v1"
SCHEMA_VERSION = 1
DATA_PATH = Path(__file__).resolve().parents[1] / "content" / "world" / "town_threads.json"
MAX_ACTIVE = 8
MAX_HISTORY = 8
MAX_SETTLEMENTS = 4
MAX_SEEDED_PLACES = 5  # the rest of the settlement's places stay for the player to find
MIN_OPEN = 2
MAX_PUBLIC_LINE = 120
MAX_OWNER_LINE = 160
HOUR = 3600
ACTIVE = ("open", "heard")
TERMINAL = ("filled_by_other", "expired")
STATUSES = (*ACTIVE, *TERMINAL)
# The only moves a thread may make. A mention never reopens anything.
TRANSITIONS = {"open": {"heard", *TERMINAL}, "heard": set(TERMINAL)}
_LOG = logging.getLogger(__name__)
_catalog_cache: dict[str, Any] | None = None


def catalog() -> dict[str, Any]:
    """The kinds of work a town can have; an unreadable file means none, never a stopped turn."""
    global _catalog_cache
    if _catalog_cache is None:
        try:
            import thread_catalog
            data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            templates = [item for item in (*data.get("templates", []), *thread_catalog.load()) if _usable(item)]
            _catalog_cache = {**data, "templates": templates}
        except (OSError, ValueError, TypeError, AttributeError):
            _LOG.warning("World thread kinds could not be read.")
            _catalog_cache = {"templates": []}
    return _catalog_cache


def _usable(item: Any) -> bool:
    return (
        isinstance(item, dict) and isinstance(item.get("id"), str)
        and item.get("type") in {"hiring", "errand", "trouble"}
        and bool(item.get("public_lines")) and bool(item.get("owner_lines"))
        and bool(item.get("place_kinds"))
        and all(kind in local_places.PLACE_KINDS for kind in item["place_kinds"])
        and all(kind in local_places.PLACE_KINDS for kind in item.get("target_place_kinds") or ())
    )


def _rank(seed: str, *parts: Any) -> int:
    material = "\x00".join((seed, *map(str, parts)))
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:4], "big")


def _between(seed: str, bounds: Any, *parts: Any) -> int | None:
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        return None
    low, high = bounds
    return low + _rank(seed, *parts) % (high - low + 1)


def _now(world: dict[str, Any]) -> int:
    clock = world.get("campaign_time")
    elapsed = clock.get("elapsed_seconds") if isinstance(clock, dict) else 0
    return elapsed if type(elapsed) is int else 0


def _new_state() -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "seeded": [], "next_number": 1, "last_tick": 0,
            "threads": [], "history": []}


def view(world: dict[str, Any]) -> dict[str, Any] | None:
    state = world.get(KEY)
    return state if isinstance(state, dict) and state.get("version") == SCHEMA_VERSION else None


def active(world: dict[str, Any], settlement_id: str | None = None) -> list[dict[str, Any]]:
    state = view(world)
    return [
        thread for thread in (state["threads"] if state else [])
        if thread.get("status") in ACTIVE
        and (settlement_id is None or thread.get("settlement_id") == settlement_id)
    ]


def _reserve_resident(world: dict[str, Any], record: dict[str, Any]) -> str:
    """The one person of a place, named now so every later line means the same person."""
    npc = local_places.resident_of(world, record["id"])
    if npc is not None:
        return living_world.public_npc_name(npc)
    if not record.get("resident_name"):
        spec = local_places.PLACE_KINDS[record["place_kind"]]
        record["resident_name"] = living_world.stable_local_name(world, record["id"], spec["role"])
        aliases = record.setdefault("aliases", [])
        if record["resident_name"] not in aliases:
            aliases.append(record["resident_name"])
    return record["resident_name"]


def _used_places(state: dict[str, Any], settlement_id: str) -> list[str]:
    found: list[str] = []
    for thread in state["threads"]:
        if thread.get("settlement_id") == settlement_id:
            found += [p for p in (thread.get("place_id"), thread.get("target_place_id")) if p and p not in found]
    return found


def _place_for(world, state, seed, settlement_id, kinds, *, salt, avoid=(), create=True, reuse_first=False):
    """A real place of one of these kinds: an existing one, or a new one when allowed."""
    ordered = sorted(kinds, key=lambda kind: _rank(seed, settlement_id, salt, kind))
    records = world.get("locations", {})
    if reuse_first:
        for place_id in _used_places(state, settlement_id):
            record = records.get(place_id)
            if isinstance(record, dict) and record.get("place_kind") in kinds and place_id not in avoid:
                return record
    local = sum(1 for r in records.values() if isinstance(r, dict)
                and r.get("parent_location_id") == settlement_id and r.get("place_kind"))
    if create and local < MAX_SEEDED_PLACES:
        for kind in ordered:
            if local_places.find_local_place(world, settlement_id, kind) is None:
                record = local_places.create_local_place(world, settlement_id, kind)
                if record is not None:
                    record["provenance"] = {"source": "world_thread"}
                    return record
    for kind in ordered:
        record = local_places.find_local_place(world, settlement_id, kind)
        if record is not None and record["id"] not in avoid:
            return record
    return None


def _fill(line: str, **slots: Any) -> str:
    text = line
    for name, value in slots.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def _open_thread(world, state, template, settlement_id, *, create):
    seed = living_world._campaign_seed(world)
    number = state["next_number"]
    identity = f"{settlement_id}\x00{template['id']}\x00{number}"
    # Half the time a new thread ties into a place the town already talks about,
    # so some campaigns get a tight knot of places and others a loose scatter.
    linked = bool(_rank(seed, identity, "link") % 2)
    place = _place_for(world, state, seed, settlement_id, template["place_kinds"],
                       salt=f"{identity}:place", create=create)
    if place is None:
        return None
    target = None
    if template.get("target_place_kinds"):
        target = _place_for(world, state, seed, settlement_id, template["target_place_kinds"],
                            salt=f"{identity}:target", avoid={place["id"]}, create=create, reuse_first=linked)
        if target is None:
            return None
    owner = _reserve_resident(world, place)
    recipient = _reserve_resident(world, target) if target else None
    pay = _between(seed, template.get("pay"), identity, "pay")
    days = _between(seed, template.get("work_days"), identity, "days")
    spec = local_places.PLACE_KINDS[place["place_kind"]]
    issue = local_places._pick(world, place["id"], spec["issues"], "issue")[1]
    slots = dict(place=place["name"], owner=owner, target=target["name"] if target else "",
                 recipient=recipient or "", pay="" if pay is None else pay, days="" if days is None else days,
                 issue=issue)
    lines = template["public_lines"]
    public = _fill(lines[_rank(seed, identity, "public") % len(lines)], **slots)
    terms = template["owner_lines"]
    private = _fill(terms[_rank(seed, identity, "owner") % len(terms)], **slots)
    if len(public) > MAX_PUBLIC_LINE or len(private) > MAX_OWNER_LINE:
        return None  # measured once the names are in; a line is never cut into a new meaning
    hours = _between(seed, template.get("offer_hours"), identity, "offer") or 24
    now = _now(world)
    thread = {
        "thread_id": f"thread_{number:03d}", "template_id": template["id"], "type": template["type"],
        "status": "open", "settlement_id": settlement_id, "place_id": place["id"], "owner_name": owner,
        "target_place_id": target["id"] if target else None, "recipient_name": recipient,
        "terms": {"pay": pay, "work_days": days},
        "public_line": public, "owner_line": private,
        "opened_at": now, "expires_at": now + hours * HOUR, "heard_turn": None, "closed_at": None,
    }
    state["next_number"] = number + 1
    state["threads"].append(thread)
    return thread


def _seed_settlement(world, state, settlement_id):
    seed = living_world._campaign_seed(world)
    templates = sorted(catalog()["templates"], key=lambda item: _rank(seed, settlement_id, "order", item["id"]))
    wanted = 3 + _rank(seed, settlement_id, "count") % 2
    types: dict[str, int] = {}
    opened = 0
    for template in templates:
        if opened >= wanted:
            break
        if types.get(template["type"], 0) >= 2:
            continue  # never a town of one sort of need
        if _open_thread(world, state, template, settlement_id, create=True):
            types[template["type"]] = types.get(template["type"], 0) + 1
            opened += 1
    state["seeded"].append(settlement_id)


def ensure(world: dict[str, Any]) -> dict[str, Any] | None:
    """Seed this settlement's threads once. Old saves gain them here; a failure changes nothing."""
    settlement_id = local_places.settlement_of(world, world.get("location"))
    if not settlement_id or not living_world._campaign_seed(world):
        return view(world)
    state = view(world)
    if state is not None and (settlement_id in state["seeded"] or len(state["seeded"]) >= MAX_SETTLEMENTS):
        return state
    if not catalog()["templates"]:
        return state
    kept_places = copy.deepcopy(world.get("locations"))
    kept_number = world.get("next_location_number")
    had_state = KEY in world
    previous = copy.deepcopy(world.get(KEY))
    try:
        fresh = state if state is not None else _new_state()
        world[KEY] = fresh
        _seed_settlement(world, fresh, settlement_id)
        validate(fresh)
        return fresh
    except Exception:
        _LOG.exception("World threads could not be seeded.")
        world["locations"] = kept_places
        if kept_number is None:
            world.pop("next_location_number", None)
        else:
            world["next_location_number"] = kept_number
        if had_state:
            world[KEY] = previous
        else:
            world.pop(KEY, None)
        return view(world)


def street_talk(world: dict[str, Any], settlement_id: str) -> dict[str, Any] | None:
    """The next thread a walker could catch wind of; each only once, the first never revisited."""
    state = view(world)
    if state is None:
        return None
    seen = state.setdefault("overheard", [])
    thread = next((t for t in active(world, settlement_id) if t["thread_id"] not in seen), None)
    if thread is not None:
        seen.append(thread["thread_id"])
        del seen[:-MAX_ACTIVE * 2]
    return thread


def note_heard_names(world: dict[str, Any], text: str) -> None:
    """Once a resident's name was said in the player's hearing, it is theirs to use."""
    words = living_world.normalize_text(text).split()
    for record in world.get("locations", {}).values():
        name = living_world.normalize_text(record.get("resident_name")) if isinstance(record, dict) else ""
        if name and any(word.startswith(name) for word in words):
            record["resident_known"] = True
            npc = local_places.resident_of(world, record["id"])
            if npc is not None:
                npc["name_known_to_player"] = True


def transition(thread: dict[str, Any], status: str) -> bool:
    """Move a thread only along a listed edge; anything else leaves it as it is."""
    if status not in TRANSITIONS.get(thread.get("status"), ()):
        return False
    thread["status"] = status
    return True


def mark_heard(thread: dict[str, Any], turn: int) -> None:
    if transition(thread, "heard"):
        thread["heard_turn"] = turn


def _close_due(world, state, now):
    seed = living_world._campaign_seed(world)
    still = []
    for thread in state["threads"]:
        if thread["status"] in ACTIVE and now >= thread["expires_at"]:
            taken = _rank(seed, thread["thread_id"], "taken") % 100 < 60
            transition(thread, "filled_by_other" if taken else "expired")
            thread["closed_at"] = now
            state["history"].append(thread)
        else:
            still.append(thread)
    state["threads"] = still
    del state["history"][:-MAX_HISTORY]


def _replenish(world, state, now):
    seed = living_world._campaign_seed(world)
    for settlement_id in state["seeded"]:
        recent = {t.get("template_id") for t in [*state["history"], *state["threads"]]
                  if t.get("settlement_id") == settlement_id}
        mine = [t for t in state["threads"] if t.get("settlement_id") == settlement_id]
        last_type = mine[-1]["type"] if mine else None
        order = sorted(catalog()["templates"],
                       key=lambda item: _rank(seed, settlement_id, "later", now // 86400, item["id"]))
        for template in order:
            if len(active(world, settlement_id)) >= MIN_OPEN or len(state["threads"]) >= MAX_ACTIVE:
                break
            if template["id"] in recent or template["type"] == last_type:
                continue
            if _open_thread(world, state, template, settlement_id, create=False):
                last_type = template["type"]


def tick(world: dict[str, Any], now: int) -> None:
    """Move the town along when campaign time passes. No model; the same moment twice does nothing."""
    state = view(world)
    if state is None or type(now) is not int or now <= state["last_tick"]:
        return
    try:
        # Kept only whole. Saved places stay the same objects: callers hold them across a clock step.
        work = copy.deepcopy(state)
        world[KEY] = work
        _close_due(world, work, now)
        _replenish(world, work, now)
        work["last_tick"] = now
        validate(work)
    except Exception:
        _LOG.exception("World threads could not move on.")
        world[KEY] = state


def validate(state: Any) -> None:
    if not isinstance(state, dict) or state.get("version") != SCHEMA_VERSION:
        raise ValueError("World thread state is invalid.")
    threads, history = state.get("threads"), state.get("history")
    if (
        not isinstance(threads, list) or not isinstance(history, list)
        or not isinstance(state.get("seeded"), list)
        or type(state.get("next_number")) is not int or type(state.get("last_tick")) is not int
        or len(threads) > MAX_ACTIVE or len(history) > MAX_HISTORY
    ):
        raise ValueError("World thread state is invalid.")
    for thread in (*threads, *history):
        if (
            not isinstance(thread, dict) or thread.get("status") not in STATUSES
            or not isinstance(thread.get("thread_id"), str) or not isinstance(thread.get("place_id"), str)
            or not isinstance(thread.get("public_line"), str) or not isinstance(thread.get("owner_line"), str)
            or type(thread.get("expires_at")) is not int or type(thread.get("opened_at")) is not int
            or not isinstance(thread.get("terms"), dict)
        ):
            raise ValueError("World thread record is invalid.")
