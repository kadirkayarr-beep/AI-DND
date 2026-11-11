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
import re
from pathlib import Path
from typing import Any

import living_world
import tr_case
import local_places

KEY = "world_threads_v1"
SCHEMA_VERSION = 1
DATA_PATH = Path(__file__).resolve().parents[1] / "content" / "world" / "town_threads.json"
ANSWERS_PATH = DATA_PATH.with_name("offer_answers.json")
MAX_ACTIVE = 8
MAX_HISTORY = 8
MAX_LOG = 6
WARY_PERCENT = 20
WANT_PERCENT = 55  # how often one thread that fits what the character is after is moved up the town's list
MAX_WANTS = 2
WANT_PERCENT = 55  # how often one thread that fits what the character is after is moved up the town's list
MAX_WANTS = 2
MAX_SETTLEMENTS = 4
MAX_SEEDED_PLACES = 5  # the rest of the settlement's places stay for the player to find
MIN_OPEN = 2
MAX_PUBLIC_LINE = 120
MAX_OWNER_LINE = 160
HOUR = 3600
DAY = 86400
OFFER_HOURS = 24  # an offer nobody answers is taken back by this long after it was made
DECLINE_HOURS = 6  # a turned-down job stays takeable this long
PUBLIC = ("open", "heard")  # what the street talks about
OWNED = (*PUBLIC, "offered", "accepted", "declined")  # what its owner still holds
CLOSABLE_BY_TIME = (*PUBLIC, "offered", "declined")
TERMINAL = ("filled_by_other", "expired", "done", "failed", "abandoned", "fired")
STATUSES = (*OWNED, *TERMINAL)
# The only moves a thread may make. A mention never reopens anything.
TRANSITIONS = {
    "open": {"heard", "offered", "filled_by_other", "expired", "fired"},
    "heard": {"offered", "filled_by_other", "expired", "fired"},
    "offered": {"accepted", "declined", "expired", "fired"},
    "declined": {"accepted", "filled_by_other", "expired", "fired"},
    "accepted": {"done", "failed", "expired", "abandoned"},
}
_OPTIONAL_INTS = ("offered_turn", "offered_at", "declined_turn", "accepted_at", "accepted_turn", "starts_at", "work_until",
                  "days_worked", "shift_seconds", "shift_until", "last_paid_day_index", "paid_cp",
                  "outcome_known_turn", "offer_line_turn", "fires_at", "xp_due")
_OPTIONAL_TEXTS = ("owner_npc_id", "recipient_npc_id", "quest_id", "item_noun", "filled_by_npc_id", "filled_by_name",
                   "offer_line", "job_line", "letter_line")
_LOG = logging.getLogger(__name__)
_catalog_cache: dict[str, Any] | None = None
_answers_cache: dict[str, Any] | None = None


def catalog() -> dict[str, Any]:
    """The kinds of work a town can have; an unreadable file means none, never a stopped turn."""
    global _catalog_cache
    if _catalog_cache is None:
        try:
            import thread_catalog
            data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            templates = [item for item in (*data.get("templates", []), *thread_catalog.load())
                         if _usable(item) and _can_be_done(item)]
            _catalog_cache = {**data, "templates": templates}
        except (OSError, ValueError, TypeError, AttributeError):
            _LOG.warning("World thread kinds could not be read.")
            _catalog_cache = {"templates": []}
    return _catalog_cache


def _folded(phrase: Any) -> str:
    return " ".join(living_world.normalize_text(phrase).split())


def answer_table() -> dict[str, Any]:
    """Word lists for answering an offer: the candidate data plus the town file's short forms."""
    global _answers_cache
    if _answers_cache is None:
        extra = catalog().get("offer_answers") or {}
        try:
            data = json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _LOG.warning("The offer answer words could not be read.")
            data = {}
        lists = {
            "accept": [e["expression"] for e in data.get("kabul", [])] + list(extra.get("accept", ())),
            "decline": [e["expression"] for e in data.get("ret", [])] + list(extra.get("decline", ())),
            "withdraw": [e["expression"] for e in data.get("vazgeçme", [])] + list(extra.get("withdraw", ())),
            "unclear": [e["expression"] for e in data.get("belirsizler", [])] + list(extra.get("hedges", ())),
        }
        table: dict[str, Any] = {name: frozenset(_folded(item) for item in items) for name, items in lists.items()}
        for name, items in extra.items():
            if name not in lists:
                table[name] = frozenset(_folded(item) for item in items)
        _answers_cache = table
    return _answers_cache


def _usable(item: Any) -> bool:
    return (
        isinstance(item, dict) and isinstance(item.get("id"), str)
        and item.get("type") in {"hiring", "errand", "trouble"}
        and bool(item.get("public_lines")) and bool(item.get("owner_lines"))
        and bool(item.get("place_kinds"))
        and all(kind in local_places.PLACE_KINDS for kind in item["place_kinds"])
        and all(kind in local_places.PLACE_KINDS for kind in item.get("target_place_kinds") or ())
    )


def _can_be_done(item: dict[str, Any]) -> bool:
    """A hired job that needs a second place has no real work behind it yet, so nobody offers it."""
    return item["type"] != "hiring" or not item.get("target_place_kinds")


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
            "threads": [], "history": [], "happenings": []}


def view(world: dict[str, Any]) -> dict[str, Any] | None:
    state = world.get(KEY)
    return state if isinstance(state, dict) and state.get("version") == SCHEMA_VERSION else None


def _with_status(world, statuses, settlement_id):
    state = view(world)
    return [
        thread for thread in (state["threads"] if state else [])
        if thread.get("status") in statuses
        and (settlement_id is None or thread.get("settlement_id") == settlement_id)
    ]


def active(world: dict[str, Any], settlement_id: str | None = None) -> list[dict[str, Any]]:
    """What is still public: the street's talk, not a job someone has been offered."""
    return _with_status(world, PUBLIC, settlement_id)


def owned(world: dict[str, Any], settlement_id: str | None = None) -> list[dict[str, Any]]:
    """Everything an owner still holds, public or not."""
    return _with_status(world, OWNED, settlement_id)


def by_id(world: dict[str, Any], thread_id: Any) -> dict[str, Any] | None:
    """The live record. A clock step replaces the state, so nothing is held across one."""
    state = view(world)
    return next((t for t in (*state["threads"], *state["history"], *state.get("links", ()))
                 if t.get("thread_id") == thread_id), None) if state else None


def job_lines(*path: str) -> Any:
    found: Any = catalog().get("job_lines") or {}
    for part in path:
        found = found.get(part) if isinstance(found, dict) else None
    return found


def pay_basis(thread: dict[str, Any]) -> str | None:
    """How the spoken pay is counted; an old save read it from the kind of work."""
    terms = thread.get("terms") or {}
    if terms.get("pay_basis"):
        return terms["pay_basis"]
    if thread.get("type") == "errand":
        return "per_trip"
    if thread.get("type") != "hiring":
        return None
    template = next((t for t in catalog().get("templates", []) if t["id"] == thread.get("template_id")), None)
    return (template or {}).get("pay_basis", "total")


def _reserve_resident(world: dict[str, Any], record: dict[str, Any]) -> str:
    """The one person of a place, named now so every later line means the same person."""
    npc = local_places.resident_of(world, record["id"])
    if npc is not None:
        return living_world.public_npc_name(npc)
    if not record.get("resident_name"):
        role = record.get("resident_role") or local_places.PLACE_KINDS[record["place_kind"]]["role"]
        record["resident_name"] = living_world.stable_local_name(world, record["id"], role)
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


def _open_thread(world, state, template, settlement_id, *, create, now, place=None, avoid=(), tied=False):
    """One new thread. place: this very place. avoid: anywhere but these. tied: it grows out of something already talked of."""
    import world_happenings
    seed = living_world._campaign_seed(world)
    number = state["next_number"]
    identity = f"{settlement_id}\x00{template['id']}\x00{number}"
    # Half the time a new thread ties into a place the town already talks about,
    # so some campaigns get a tight knot of places and others a loose scatter.
    linked = tied or bool(_rank(seed, identity, "link") % 2)
    place = place or _place_for(world, state, seed, settlement_id, template["place_kinds"],
                                salt=f"{identity}:place", avoid=avoid, create=create)
    if place is None or world_happenings.barred(state, place["id"], template["type"], now):
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
    words = job_lines("text") or {}
    deadline = words.get("deadline_errand") if template["type"] == "errand" else (
        _fill(words.get("deadline_hiring", ""), days=days) if template["type"] == "hiring" and days else None)
    thread = {
        "thread_id": f"thread_{number:03d}", "template_id": template["id"], "type": template["type"],
        "status": "open", "settlement_id": settlement_id, "place_id": place["id"], "owner_name": owner,
        "target_place_id": target["id"] if target else None, "recipient_name": recipient,
        "terms": {"pay": pay, "work_days": days,
                  "pay_basis": template.get("pay_basis") or {"errand": "per_trip", "hiring": "total"}.get(template["type"]),
                  "pay_timing": {"errand": "on_delivery", "hiring": "end_of_day"}.get(template["type"]),
                  "deadline_text": deadline},
        "public_line": public, "owner_line": private,
        "opened_at": now, "expires_at": now + hours * HOUR, "heard_turn": None, "closed_at": None,
    }
    if template["type"] == "trouble":
        thread["fires_at"] = thread["expires_at"]  # a trouble comes to something; it does not lapse first
    if template.get("night_only"):
        thread["night_only"] = True
    if template.get("item_noun"):
        thread["item_noun"] = template["item_noun"]
    if template.get("status_lines"):
        thread["status_lines"] = template["status_lines"]
    state["next_number"] = number + 1
    state["threads"].append(thread)
    return thread


def want_table() -> dict[str, Any]:
    """The things a character can be after; the only ids a reading can name."""
    import name_catalog
    try:
        return json.loads((name_catalog.CATALOG_DIR / "mapping.json").read_text(encoding="utf-8")).get("player_wants") or {}
    except (OSError, ValueError):
        _LOG.warning("The list of what a character can be after could not be read.")
        return {}


def wants_of(world: dict[str, Any]) -> list[str]:
    wants = (world.get("flags") or {}).get("player_wants")
    return list(wants) if isinstance(wants, list) else []


def note_want(world: dict[str, Any], want: Any) -> None:
    """A listed goal the character has; a new one pushes out the oldest."""
    if want not in want_table():
        return
    wants = [held for held in wants_of(world) if held != want]
    world.setdefault("flags", {})["player_wants"] = [*wants, want][-MAX_WANTS:]


def serves(template: dict[str, Any], wants: Any) -> bool:
    """This kind of work lies in the direction of what the character is after."""
    table = want_table()
    return any((template.get("group") in (table.get(want) or {}).get("groups", ())) if template.get("group")
               else bool(set(template.get("place_kinds") or ()) & set((table.get(want) or {}).get("place_kinds", ())))
               for want in wants)


def _leaning(world, *salt) -> str | None:
    """A tilt, drawn from the seed: some of the time one fitting kind of work comes up the list, and nothing else changes."""
    wants = wants_of(world)
    seed = living_world._campaign_seed(world)
    if not wants or _rank(seed, "want", *salt) % 100 >= WANT_PERCENT:
        return None
    fitting = [t["id"] for t in catalog()["templates"] if serves(t, wants)]
    return min(fitting, key=lambda identity: _rank(seed, "want", identity, *salt), default=None)


def _seed_settlement(world, state, settlement_id):
    seed = living_world._campaign_seed(world)
    leaning = _leaning(world, settlement_id)
    templates = sorted(catalog()["templates"], key=lambda item: (
        item["id"] != leaning, _rank(seed, settlement_id, "order", item["id"])))
    wanted = 3 + _rank(seed, settlement_id, "count") % 2
    types: dict[str, int] = {}
    opened = 0
    for template in templates:
        if opened >= wanted:
            break
        if types.get(template["type"], 0) >= 2:
            continue  # never a town of one sort of need
        if _open_thread(world, state, template, settlement_id, create=True, now=_now(world)):
            types[template["type"]] = types.get(template["type"], 0) + 1
            opened += 1
    state["seeded"].append(settlement_id)


def ensure(world: dict[str, Any]) -> dict[str, Any] | None:
    """Seed this settlement's threads once. Old saves gain them here; a failure changes nothing."""
    state = view(world)
    if state is not None:
        state.setdefault("happenings", [])
    settlement_id = local_places.settlement_of(world, world.get("location"))
    if not settlement_id or not living_world._campaign_seed(world):
        return state
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
    """The next thing a walker could catch wind of: something the player has not heard yet."""
    state = view(world)
    if state is None:
        return None
    seen = state.setdefault("overheard", [])
    thread = next((t for t in active(world, settlement_id)
                   if t["status"] == "open" and t["thread_id"] not in seen
                   and local_places.resident_of(world, t["place_id"]) is None), None)
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


def _npc(world, npc_id):
    return next((n for n in world.get("npcs", []) if isinstance(n, dict) and n.get("id") == npc_id), None)


def owner_of(world: dict[str, Any], thread: dict[str, Any]) -> dict[str, Any] | None:
    """The person behind the work, once they exist; the place's role survives them walking off."""
    return _npc(world, thread.get("owner_npc_id")) or next(
        (n for n in world.get("npcs", []) if isinstance(n, dict) and n.get("place_role_of") == thread.get("place_id")),
        None,
    )


def recipient_of(world: dict[str, Any], thread: dict[str, Any]) -> dict[str, Any] | None:
    place_id = thread.get("target_place_id")
    return _npc(world, thread.get("recipient_npc_id")) or (next(
        (n for n in world.get("npcs", []) if isinstance(n, dict) and n.get("place_role_of") == place_id),
        None,
    ) if place_id else None)


def _dead(npc):
    return isinstance(npc, dict) and npc.get("combat_status") == "dead"


def _route_lost(world, thread):
    """The work no longer has anywhere to happen. Nobody is blamed for that."""
    places = world.get("locations", {})
    target = thread.get("target_place_id")
    if thread.get("place_id") not in places or (target and target not in places):
        return True
    routes = world.get("blocked_travel_routes", {})
    blocked = routes.get(thread.get("settlement_id"), {}) if isinstance(routes, dict) else {}
    return bool(target and isinstance(blocked, dict) and blocked.get(target))


def _broken(thread):
    """An accepted record a later step could not trust."""
    return any(
        thread.get(name) is not None and type(thread.get(name)) is not int for name in _OPTIONAL_INTS
    ) or (thread.get("type") in WORKED and type(thread.get("work_until")) is not int)


def _clean(thread):
    """Drop whatever made a closed record unreadable; the close itself is what matters."""
    for name in _OPTIONAL_INTS:
        if thread.get(name) is not None and type(thread.get(name)) is not int:
            thread.pop(name, None)


def _taker(world, thread, seed):
    """Who got the job: somebody real in this town, never a name out of nowhere."""
    settlement = thread.get("settlement_id")
    owner = owner_of(world, thread)
    people = sorted(
        (n for n in world.get("npcs", []) if isinstance(n, dict) and n is not owner and not _dead(n)
         and n.get("current_hp", 1) > 0 and isinstance(n.get("id"), str) and n.get("location")
         and local_places.settlement_of(world, n["location"]) == settlement),
        key=lambda n: _rank(seed, thread["thread_id"], "taker", n["id"]),
    )
    if people:
        return people[0]["id"], living_world.public_npc_name(people[0])
    places = sorted(
        (r for r in world.get("locations", {}).values() if isinstance(r, dict)
         and r.get("parent_location_id") == settlement and r.get("place_kind") in local_places.PLACE_KINDS
         and r.get("id") != thread.get("place_id")),
        key=lambda r: _rank(seed, thread["thread_id"], "taker", r["id"]),
    )
    if places:
        return None, _reserve_resident(world, places[0])
    return None, living_world.stable_local_name(world, f"{thread['thread_id']}:taker", "işçi")


def fires_at(thread):
    """The moment this trouble comes to something; None for anything else, and once it has."""
    moment = thread.get("fires_at")
    return moment if thread.get("type") == "trouble" and type(moment) is int else None


def _due(thread):
    """When time alone closes this thread; None while nothing is waiting on the clock."""
    status = thread.get("status")
    if status in CLOSABLE_BY_TIME and fires_at(thread) is not None:
        return fires_at(thread)
    if status == "offered":
        made = thread.get("offered_at")
        limit = made + OFFER_HOURS * HOUR if type(made) is int else thread["expires_at"]
        return min(thread["expires_at"], limit)
    if status in CLOSABLE_BY_TIME:
        return thread["expires_at"]
    return None


def _time_outcome(world, thread, now, seed):
    """The status the clock moves this thread to, and when; None leaves it alone."""
    due = _due(thread)
    if due is not None:
        if now < due:
            return None
        if fires_at(thread) is not None:
            return "fired", due
        if thread["status"] == "offered":
            return "expired", due
        if thread["status"] == "declined":
            taken = _rank(seed, thread["thread_id"], "taken_declined") % 100 < 90
        else:
            taken = _rank(seed, thread["thread_id"], "taken") % 100 < 60
        return ("filled_by_other" if taken else "expired"), due
    if thread.get("status") != "accepted":
        return None
    if _broken(thread):
        return "expired", now
    if thread.get("shift_until") is not None:
        return None  # the player is at work right now
    if _dead(owner_of(world, thread)) or _dead(recipient_of(world, thread)) or _route_lost(world, thread):
        return "expired", now
    until = thread.get("work_until")
    if thread.get("type") in WORKED and now > until and thread.get("days_worked", 0) < (thread["terms"].get("work_days") or 0):
        return "failed", until
    return None


def _close_due(world, state, now):
    import world_happenings
    seed = living_world._campaign_seed(world)
    closing = sorted(
        ((found, thread) for thread in state["threads"]
         if not parked(thread) and (found := _time_outcome(world, thread, now, seed)) is not None),
        key=lambda pair: pair[0][1],
    )
    effects = []
    for (status, due), thread in closing:
        if not transition(thread, status):
            continue
        _clean(thread)
        thread["closed_at"] = min(now, due)
        if status == "filled_by_other":
            thread["filled_by_npc_id"], thread["filled_by_name"] = _taker(world, thread, seed)
        effects.append((thread["thread_id"], status))
    state["threads"], closed = _split_closed(state["threads"])
    state["history"].extend(closed)
    effects += world_happenings.fire_due(world, state, now)
    _trim_history(state, world)
    return effects


def _split_closed(threads):
    return [t for t in threads if t["status"] not in TERMINAL], [t for t in threads if t["status"] in TERMINAL]


def _unpaid(world, thread):
    """A finished job whose experience the turn has not paid yet (no ``job:`` receipt): it must not be trimmed away."""
    if world is None or thread.get("xp_due") is None:
        return False
    import xp
    held = world.get("xp_awarded_event_ids")
    return not (isinstance(held, list) and xp._job_award_id(thread["thread_id"]) in held)


def _trim_history(state, world=None):
    """Old closings go; one the player had a hand in stays until they have learned how it ended, and was paid for it."""
    waiting = [t for t in state["history"] if fires_at(t) is not None
               or (t.get("offered_at") is not None and t.get("outcome_known_turn") is None) or _unpaid(world, t)]
    known = [t for t in state["history"] if not any(t is w for w in waiting)]
    keep = {id(t) for t in (*known[-MAX_HISTORY:], *waiting[-MAX_HISTORY:])}
    state["history"] = [t for t in state["history"] if id(t) in keep]


_QUEST_OUTCOME = {"COMPLETED": "done", "FAILED": "failed", "ABANDONED": "abandoned"}


def sync_from_quests(world: dict[str, Any], state: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """A job's journal row decided: the thread follows, once, with no clock needed."""
    state = state or view(world)
    if state is None:
        return []
    effects = []
    quests = {q.get("quest_id"): q for q in world.get("quests", []) if isinstance(q, dict)}
    for thread in state["threads"]:
        status = _QUEST_OUTCOME.get((quests.get(thread.get("quest_id")) or {}).get("status"))
        if thread.get("status") == "accepted" and status and not parked(thread) and transition(thread, status):
            thread["closed_at"] = _now(world)
            effects.append((thread["thread_id"], status))
    if effects:
        state["threads"], closed = _split_closed(state["threads"])
        state["history"].extend(closed)
        _trim_history(state, world)
        _apply_effects(world, effects)
    return effects


_RELATION = {"done": 1, "abandoned": -1, "failed": -1}
_CLOSE_SUMMARY = {"done": "İş tamamlandı", "failed": "İş yarım kaldı", "abandoned": "İş bırakıldı",
                  "expired": "Teklif kapandı", "filled_by_other": "İş başkasına geçti", "fired": "Dert başa geldi"}


def note_event(world: dict[str, Any], thread: dict[str, Any], kind: str, summary: str,
               *, npc: Any = None, player_known: bool = True) -> None:
    """A job's mark in the shared log. The record is the thread; a lost log line loses nothing."""
    import interaction_adventure
    try:
        interaction_adventure.note_town_event(world, f"thread_{kind}"[:64], f"{spoken_owner(world, thread) or 'İş'}: {summary}",
                                              npc=npc if isinstance(npc, dict) else None,
                                              location_id=thread.get("place_id") if thread.get("place_id") in world.get("locations", {}) else None,
                                              player_known=player_known)
    except Exception:
        _LOG.exception("A job could not be noted.")


def _apply_effects(world, effects):
    """What a close means beyond the thread. Runs only after the state itself is valid.
    A failing close is raised as that thread's own failure so the tick can hold back just it."""
    import world_happenings
    for thread_id, status in effects:
        thread = by_id(world, thread_id)
        if thread is None:
            continue
        if status == world_happenings.HAPPENED:
            world_happenings.show(world, thread)
            continue
        try:
            _close_effects(world, thread_id, thread, status)
        except Exception as exc:
            raise _CloseFailed(thread_id, exc) from exc


def _close_effects(world, thread_id, thread, status):
    import relationships
    import world_reactions
    from adventure import director
    from adventure.transitions import TransitionError
    import world_happenings
    thread.pop(CLOSE_FAILED, None)  # it closed: an earlier failed try no longer matters
    if status == "done" and thread.get("accepted_at") is not None and "xp_due" not in thread:
        import xp
        amount = xp.JOB_XP_BY_TYPE.get(thread.get("type"))
        if amount:  # what the player is owed for work they took on; paid once at the turn's end (xp.award_finished_jobs)
            thread["xp_due"] = amount
    world_happenings.on_close(world, thread, status)
    owner = owner_of(world, thread)
    if status in _RELATION and isinstance(owner, dict) and isinstance(owner.get("id"), str):
        relationships.note(world, owner["id"], _RELATION[status], f"thread:{thread_id}:{status}"[:160])
    world_reactions.promise_broken(world, thread, owner, status)
    if thread.get("offered_at") is not None:
        note_event(world, thread, status, _CLOSE_SUMMARY.get(status, status), npc=owner,
                   player_known=status in {"done", "abandoned"})
        if status in {"done", "abandoned"}:
            thread["outcome_known_turn"] = int((world.get("flags") or {}).get("turn_index", 0) or 0)
    quest_id = thread.get("quest_id")
    quest = next((q for q in world.get("quests", []) if isinstance(q, dict) and q.get("quest_id") == quest_id), None)
    if status == "expired" and quest is not None and quest.get("status") in {"DISCOVERED", "ACTIVE", "BLOCKED"}:
        try:
            director.abandon_dynamic(world, quest_id)
        except (TransitionError, ValueError):
            _LOG.warning("A job's journal row could not be closed.")


# Answering an offer. Word lists only, read clause by clause: a word counts when the
# clause is that word, never because it sits inside something longer.
_QUOTES = ('"', "“", "”", "«", "»", "‘", "’")
_SPLIT = re.compile(r"(\.\.\.|…|[.,;:!?]+)|\b(ama|fakat|ancak|lakin)\b", re.IGNORECASE)
_CONDITIONAL_ENDS = ("rsa", "rse", "rsam", "rsem", "rsan", "rsen", "ysa", "yse", "etsem", "olsa", "olsam",
                     "yapsam", "alsam", "versen", "verseydin")
_REPORTED = frozenset({"dedi", "demis", "dedim", "demistim", "dedin", "demedim", "yazmis", "soyledi", "soylemis"})
_DECISIONS = {"accept", "decline", "withdraw"}
_NUMBER_ONES = ("", "bir", "iki", "uc", "dort", "bes", "alti", "yedi", "sekiz", "dokuz")
_NUMBER_TENS = ("", "on", "yirmi", "otuz", "kirk", "elli", "altmis", "yetmis", "seksen", "doksan")


def _spoken_number(number: int) -> str:
    return " ".join(p for p in (_NUMBER_TENS[number // 10 % 10], _NUMBER_ONES[number % 10]) if p)


def figure_before(text: Any, number: Any, unit: str | tuple[str, ...]) -> bool:
    """The figure right before its unit: 'yirmi bakır', 'otuz sekiz bakıra', '20 bakır'. A lone 'on' is no figure."""
    if type(number) is not int:
        return False
    words = _folded(text).split()
    spoken = _spoken_number(number).split()

    def stands_alone(start):  # 'on iki gün' is not 'iki gün'
        return len(spoken) > 1 or start == 0 or words[start - 1] not in _NUMBER_TENS

    return any(word.startswith(unit) and spoken and (
        words[at - 1:at] == [str(number)]
        or (words[max(at - len(spoken), 0):at] == spoken and stands_alone(at - len(spoken))))
        for at, word in enumerate(words))


def _stem(word: str) -> str:
    """'mektup' also has to find 'mektubu', 'paket' 'paketi'."""
    return word[:-1] if word[-1:] in {"p", "c", "t", "k", "g"} and len(word) > 3 else word


def _item_stems(thread: dict[str, Any]) -> tuple[str, ...]:
    words = _folded(thread.get("item_noun")).split()
    return tuple(_stem(word) for word in words if len(word) > 2 and word != "bir")  # 'bir not': the article is no name


def _clauses(text: str) -> list[tuple[list[str], bool, bool]]:
    """(words, ends with a question mark, follows 'ama'), in order."""
    found, words, after_but = [], "", False
    position = 0

    def close(asked: bool) -> None:
        nonlocal words, after_but
        tokens = _folded(words).split()
        if tokens:
            found.append((tokens, asked, after_but))
            after_but = False
        words = ""

    for match in _SPLIT.finditer(text):
        words += text[position:match.start()]
        position = match.end()
        if match.group(2):
            close(False)
            after_but = True
        else:
            close("?" in match.group(1))
    words += text[position:]
    close(False)
    if after_but:  # 'olur ama' with nothing after it: the condition is still to come
        found.append((["ama"], False, True))
    return found


def _names_of(npc: Any) -> frozenset[str]:
    if not isinstance(npc, dict):
        return frozenset()
    return frozenset(word for key in ("name", "public_name", "role") for word in _folded(npc.get(key)).split())


def _has_phrase(tokens: list[str], phrases: frozenset[str]) -> bool:
    return any(" ".join(tokens[start:end]) in phrases
               for start in range(len(tokens)) for end in range(start + 1, min(start + 4, len(tokens)) + 1))


_HOURS_NAMED = ("sabaha", "ogleye", "aksama", "geceye")  # 'akşama kadar çalışıyorum' is work with an end to it


def _read_clause(tokens, asked, table, names, item_stems):
    """One clause's meaning, or 'other' when it is something else entirely."""
    is_item = lambda word: word in table["item_words"] or any(word.startswith(stem) for stem in item_stems)
    fillers = table["fillers"] | names
    trailing = fillers - table["accept"]  # 'kabul abi' keeps its 'kabul'
    body = list(tokens)
    while body and (body[0] in table["discourse"] or body[0] in names):
        body.pop(0)
    while body and body[-1] in trailing:
        body.pop()
    if body and body[-1] in table["own_say"]:  # 'tamam dedim' to the one in front of you is the answer itself
        body.pop()
        while body and body[-1] in trailing:
            body.pop()
    if not body:
        return "neutral"
    body = [word for index, word in enumerate(body) if index == 0 or word != body[index - 1]]
    phrase = " ".join(body)
    if phrase in table["unclear"] and _has_phrase(body, table["question_terms"]):
        return "terms"
    if phrase in table["unclear"] or (set(body) & _REPORTED):
        return "unclear"
    listed = any(phrase in table[meaning] for meaning in _DECISIONS)  # 'of course' is no 'olursa'
    if not listed and any(word.endswith(_CONDITIONAL_ENDS) for word in body):
        return "unclear"
    said = [word for word in body if word not in table["discourse"]]
    for meaning in ("decline", "withdraw", "accept"):
        if phrase in table[meaning] or (said and all(word in table[meaning] for word in said)):
            return "question" if asked else meaning
    if _has_phrase(body, table["question_terms"]):
        return "terms"
    if any(word in table["hedges"] for word in body):
        return "unclear"
    if asked or any(word in table["question_words"] for word in body) or _has_phrase(body, table["question_words"]):
        return "question"
    named = [word for word in body if word in table["reference"] or any(word.startswith(stem) for stem in item_stems)]
    rest = " ".join(word for word in body if word not in named and word not in table["this_words"])
    if named and rest:  # 'bu işten vazgeçtim', 'vazgeçtim bu işten': the job is named, whichever way round
        if rest in table["withdraw"] or (rest in table["decline"] and rest not in table["bare_answers"]):
            return "withdraw"
        if rest in table["decline"] or rest in table["accept"]:
            return "decline" if rest in table["decline"] else "accept"
    harmless = fillers | table["reference"] | table["item_words"]
    for size in range(len(body) - 1, 0, -1):
        head, rest = " ".join(body[:size]), body[size:]
        if all(word in harmless or is_item(word) for word in rest):
            for meaning in ("decline", "withdraw", "accept"):
                if head in table[meaning]:
                    return meaning
    bare_yes = {word for word in body[:2] if word in table["accept"]}
    plain = [word for word in body if word not in bare_yes and word not in fillers]
    if " ".join(plain) in table["accept"]:  # 'peki tamam işi alırım'
        return "accept"
    if plain and all(word in table["take"] or is_item(word) for word in plain) and any(word in table["take"] for word in plain):
        return "take"
    if " ".join(plain) in table["start"] and plain:
        return "start"
    numbers = {*_NUMBER_ONES, *_NUMBER_TENS, "saat", "saatlik", "gun", "gunluk", "kadar", *_HOURS_NAMED}
    timed = [word for word in plain if word not in numbers and not word.isdigit()]
    if timed and len(timed) < len(plain) and " ".join(timed) in table["start"]:
        return "start"
    if plain and any(word in table["give_verbs"] for word in plain[-1:]) and any(is_item(word) for word in plain):
        return "give"
    if plain and plain[-1] in table["move"]:
        return "move"
    if " ".join(plain) in table["move"] and plain:
        return "move"
    return "other"


def _only_the_real_pay(tokens: list[str], thread: dict[str, Any] | None) -> bool:
    """'On bakır' back at someone who said ten is the deal repeated, not a counter-offer."""
    pay = ((thread or {}).get("terms") or {}).get("pay")
    words = [word for word in tokens if not word.isdigit() and word not in _NUMBER_ONES and word not in _NUMBER_TENS]
    return type(pay) is int and figure_before(" ".join(tokens), pay, "bakir") and all(
        word.startswith("bakir") for word in words)


def _own_line(text: str, table: dict[str, Any]) -> str | None:
    """The line without its quotes when they are the player's own; None for anyone else's words."""
    if not any(mark in text for mark in _QUOTES):
        return text
    line = text.strip()
    close = max(line.rfind(mark) for mark in _QUOTES)
    inner = line[1:close]
    after = _folded(line[close + 1:]).split()
    if line[0] not in _QUOTES or close == 0 or any(mark in inner for mark in _QUOTES):
        return None
    return inner if all(word in table["own_say"] or word in table["fillers"] for word in after) else None


def _with_the_comma_put_back(tokens, asked, after_but, table):
    """'tamam gidiyorum', 'vazgeçtim gidiyorum': an answer and a walk, the comma left out."""
    answers = table["accept"] | table["decline"] | table["withdraw"]
    if len(tokens) > 1 and tokens[0] in answers and tokens[-1] in table["move"]:
        return [(tokens[:1], False, after_but), (tokens[1:], asked, False)]
    return [(tokens, asked, after_but)]


# Folded Turkish 'iş'/'işe' is 'is'/'ise': in an English clause ('Who is Haskula?') it is no word for the work.
_ENGLISH_MARKS = frozenset({"the", "who", "whom", "where", "what", "when", "how", "which", "you", "does", "do", "are",
                            "there", "this", "that", "it", "i"})


_TURKISH_LETTERS = re.compile("[çğıöşüÇĞİÖŞÜ]")


def _english_question(text: str) -> bool:
    """A line with no Turkish letter that asks ('Is he here?'): its 'is' is no 'iş'. Turkish typed without its
    letters ('is ne zaman?') loses the job word too: a miss, never a yes."""
    return "?" in text and not _TURKISH_LETTERS.search(text)


def _without_english_is(words: list[str], english: bool = False) -> list[str]:
    return [word for word in words if word not in {"is", "ise"}] if english or _ENGLISH_MARKS & set(words) else words


def _asks_about_the_job(tokens, table, names, thread, english=False):
    """A question tied to this work: it names the work, or asks what the speaker is to do."""
    words = [word for word in _without_english_is(tokens, english) if word not in table["fillers"] and word not in names]
    if not words or " ".join(tokens) in table["question_words"]:
        return True
    stems = _item_stems(thread or {})
    people = _folded((thread or {}).get("recipient_name")).split()
    if any(word in table["work_terms"] or word in table["reference"] or word in people
           or any(word.startswith(stem) for stem in stems) for word in words):
        return True
    last = words[-1]
    return last.endswith(tuple(table["first_person_ends"])) and not last.startswith(("mi", "mu"))


def _bare_answer(tokens, table, names):
    """Nothing but a word like 'peki' or 'yok', which can as well be the start of something else."""
    return all(word in table["bare_answers"] or word in names or word in table["discourse"]
               or (word in table["fillers"] and word not in table["accept"]) for word in tokens)


def read_answer(text: Any, npc: Any = None, thread: dict[str, Any] | None = None) -> dict[str, Any]:
    """What this line says about an offer, by the lists alone. Knows nothing of any offer."""
    reading = {"meaning": None, "terms": False, "question": False, "take": False, "give": False,
               "start": False, "move": False, "reference": False, "pointing": False}
    table = answer_table()
    if isinstance(text, str) and _TURKISH_LETTERS.search(text) and "sure" in table.get("accept", ()):
        # folded Turkish "süre" (duration) is "sure": in a line with a Turkish letter it is no English yes
        table = {**table, "accept": table["accept"] - {"sure"}}
    text = _own_line(text, table) if isinstance(text, str) and text.strip() and table else None
    if text is None:
        return reading
    whole = _folded(text)
    names = _names_of(npc)
    stems = _item_stems(thread or {})
    words = whole.split()
    english = _english_question(text)
    job_words = _without_english_is(words, english)
    reading["reference"] = any(word in table["reference"] or any(word.startswith(s) for s in stems) for word in job_words) or (
        _has_phrase(job_words, table["reference"]))
    reading["pointing"] = bool(set(words) & table["pointing"])
    reading["terms"] = False
    if whole in table["unclear"]:
        reading["terms"] = _has_phrase(words, table["question_terms"])
        return reading
    if "?" not in text:
        for meaning in ("decline", "withdraw", "accept"):
            if whole in table[meaning]:
                return {**reading, "meaning": meaning}
    clauses = [piece for clause in _clauses(text) for piece in _with_the_comma_put_back(*clause, table)]
    said = []
    for tokens, asked, after_but in clauses:
        kind = "neutral" if _only_the_real_pay(tokens, thread) else _read_clause(tokens, asked, table, names, stems)
        repaired = tokens[0] in table["repair"] or " ".join(tokens[:2]) in table["repair"]
        if repaired and said:
            said = []  # 'yok ya... neyse olur': the later word is the answer
        if after_but and kind not in {"question", "terms"}:
            kind = "unclear"  # 'olur ama...' with a condition is not yet a yes
        said.append((kind, tokens))
    kinds = [kind for kind, _ in said]
    decided = _DECISIONS & set(kinds)
    reading["question"] = "question" in kinds
    reading["take"], reading["give"] = "take" in kinds, "give" in kinds
    reading["start"], reading["move"] = "start" in kinds, "move" in kinds
    if "terms" in kinds:
        return {**reading, "terms": True}
    elsewhere = any(kind == "question" and not _asks_about_the_job(tokens, table, names, thread, english)
                    for kind, tokens in said)
    bare = all(_bare_answer(tokens, table, names) for kind, tokens in said if kind in _DECISIONS)
    if "unclear" in kinds or "other" in kinds or len(decided) > 1 or (elsewhere and bare):
        # 'sabah oldu, hadi başlayalım': other words beside it do not undo a plain start, only a no or a doubt does.
        start = "start" in kinds and "unclear" not in kinds and not (decided - {"accept"})
        return {**reading, "take": False, "give": False, "start": start, "move": False}
    if decided:
        return {**reading, "meaning": decided.pop()}
    return reading


def holds_a_yes(text: Any, npc: Any, thread: dict[str, Any], *, firm: bool = False) -> bool:
    """The player's own words carry a plain yes, with no no or condition beside it.

    For a line the lists cannot read whole: the model can point at the agreement, but
    only the player's words make it. firm asks for more than 'tamam' or 'peki', which
    can as well open something else, unless the line goes straight on to the work, so
    the words stand with no model behind them.
    """
    table = answer_table()
    text = _own_line(text, table) if isinstance(text, str) and text.strip() and table else None
    if text is None:
        return False
    names = _names_of(npc)
    clauses = _clauses(text)
    read = [_read_clause(tokens, asked, table, names, _item_stems(thread)) for tokens, asked, _ in clauses]
    if "accept" not in read or {"decline", "withdraw", "unclear"} & set(read) or any(after for _, _, after in clauses):
        return False
    if not firm or any(kind == "accept" and not _bare_answer(tokens, table, names)
                       for kind, (tokens, _, _) in zip(read, clauses)):
        return True
    ends = tuple(table["first_person_ends"])  # 'tamam, nereden başlayım': going straight on to the doing of it
    return any(kind != "accept" and any(word.endswith(ends) and word not in table["fillers"] for word in tokens)
               for kind, (tokens, _, _) in zip(read, clauses))


_REFUSED_DOING = re.compile(r"(?:m[aeiu]yor|mam$|mem$|mayacag|meyecek|meyecen|mayacan|amam$|emem$)")


def goes_to_the_work(text: Any, thread: dict[str, Any]) -> bool:
    """'Dediğin işi yapıyorum': the speaker names the work and is doing it, which is a yes in deed."""
    table = answer_table()
    ends = tuple(table["first_person_ends"])
    for piece in re.split(r"[,.;!]", str(text or "")):  # a 'not' elsewhere in the line says nothing about the work
        words = _folded(piece).split()
        if (_names_the_work(piece, thread, table) and any(word.endswith(ends) for word in words)
                and not any(_REFUSED_DOING.search(word) or word.endswith(_CONDITIONAL_ENDS) for word in words)):
            return True
    return False


def _says_later(text: Any, table: dict[str, Any]) -> bool:
    return bool(set(_folded(text).split()) & table["later_words"])


_I_WILL = re.compile(r"(?:ece[gk]|aca[gk])(?:im|iz)\b|\w[ri]cem\b|[ae]c[ae]m\b")  # 'vereceğim', 'vericem', 'alacam'


def says_later(text: Any) -> bool:
    return _says_later(text, answer_table()) or bool(_I_WILL.search(_folded(text)))


def does_the_work_now(text: Any, thread: dict[str, Any]) -> bool:
    """Going to the work and at it this moment: 'yapıyorum', 'yapayım'. 'Yarın yaparım' is a promise, and so is 'hallederim'."""
    table = answer_table()
    now = tuple(table["now_ends"])
    return goes_to_the_work(text, thread) and not _says_later(text, table) and any(
        word.endswith(now) for word in _folded(text).split())


def speaks_of_pay(text: Any) -> bool:
    """The player's line is about money at all: what a model's 'pay' or 'give' needs before coin moves."""
    table = answer_table()
    words = _folded(text).split() if isinstance(text, str) else []
    money = (*table.get("pay_money", ()), *table.get("pay_topic", ()))
    return asks_for_pay(text) or any(word.startswith(money) for word in words)


def asks_for_pay(text: Any) -> bool:
    """'Paramı ver', '25 bakırı alayım', 'ödeyecek misin': one clause holds the money and the asking."""
    table = answer_table()
    text = _own_line(text, table) if isinstance(text, str) and text.strip() and table else None
    if text is None:
        return False
    money = tuple(table["pay_money"])
    for tokens, _, _ in _clauses(text):
        if _has_phrase(tokens, table["pay_not_asking"]):
            continue
        if set(tokens) & table["pay_alone"]:
            return True
        if set(tokens) & table["pay_verbs"] and any(word.startswith(money) for word in tokens):
            return True
    return False


def _last_exchange(world, npc):
    log = (world.get("npc_speech_log") or {}).get(npc.get("id")) if isinstance(npc, dict) else None
    return log[-1] if isinstance(log, list) and log and isinstance(log[-1], dict) else None


def _names_the_work(text: Any, thread: dict[str, Any], table) -> bool:
    """The line's own words are about this job, with no reading of what it decides."""
    words = _folded(text).split()
    stems = _item_stems(thread)
    return bool(set(words) & (table["work_terms"] | table["reference"])) or _has_phrase(words, table["question_terms"]) or any(
        word.startswith(stem) for stem in stems for word in words)


def _closes_on_the_job(line: str, thread: dict[str, Any], table) -> bool:
    """The last words put the job to the player: a closer on its own, or a question naming the work."""
    sentence = re.split(r"[.!…?]+", line.rstrip(" .!…?"))[-1]
    words = _folded(re.split(r"[,;:]", sentence)[-1]).split()
    while words and words[-1] in table["fillers"]:
        words.pop()
    return (" ".join(words) in table["close_words"] or _names_the_work(sentence, thread, table)
            or figure_before(sentence, (thread.get("terms") or {}).get("pay"), "bakir"))


def stays_on_the_offer(line: str, thread: dict[str, Any]) -> bool:
    """A reply that keeps the job on the table: 'Ee, yapacak mısın?', not 'Akşam yemeğe gel.'"""
    return _closes_on_the_job(line, thread, answer_table())


def _asks_something_else(line: str, thread: dict[str, Any], table) -> bool:
    """The line ended on another question: 'olur' answers that one, not the job."""
    return line.rstrip().endswith("?") and not _closes_on_the_job(line, thread, table)


def answers_the_offer(world: dict[str, Any], thread: dict[str, Any], npc: Any) -> bool:
    """This person's last line to the player was this very offer, no turn has passed since, and it asked nothing else."""
    last = _last_exchange(world, npc)
    line = thread.get("offer_line")
    said = thread.get("offer_line_turn", thread.get("offered_turn"))
    turn = (world.get("flags") or {}).get("turn_index", 0)
    return (bool(last and line and last.get("npc") == line) and type(said) is int and said >= turn
            and not _asks_something_else(line, thread, answer_table()))


def _last_line_is_the_job(world: dict[str, Any], thread: dict[str, Any], npc: Any) -> bool:
    """A bare 'vazgeçtim' means the job only while the job is what this person was last talking about."""
    last = _last_exchange(world, npc)
    line = last.get("npc") if last else None
    return not line or line in {thread.get("offer_line"), thread.get("job_line")} or (
        _names_the_work(line, thread, answer_table()))


def lapsed_yes(world: dict[str, Any], thread: dict[str, Any], text: Any, npc: Any) -> bool:
    """A yes to an offer the clock took back, read as the very yes the open offer would have heard. Writes nothing."""
    if thread.get("status") != "expired" or thread.get("accepted_at") is not None:
        return False
    return bind_player_decision(world, {**thread, "status": "offered"}, text, npc) == "accepted"


def bind_player_decision(world: dict[str, Any], thread: dict[str, Any], text: Any, npc: Any) -> str | None:
    """Python's reading of the player's own words on this thread. Writes nothing."""
    status = thread.get("status")
    if status not in {"offered", "declined", "accepted"}:
        return None
    reading = read_answer(text, npc, thread)
    if status == "accepted":
        if reading["meaning"] != "withdraw":
            return None
        table = answer_table()
        said = [word for word in _folded(text).split() if word not in table["fillers"]]
        clear = reading["reference"] or len(said) > 1 or _last_line_is_the_job(world, thread, npc)
        return "abandoned" if clear else "withdraw_unclear"
    if reading["terms"] or (status == "offered" and asks_for_pay(text)):
        return "questioning_terms" if status == "offered" else None
    current = reading["reference"] or answers_the_offer(world, thread, npc)
    # 'bunu alayım' points at goods; only a line that names the job's item takes the job.
    takes = reading["take"] and (reading["reference"] or not reading["pointing"])
    yes = reading["meaning"] == "accept" or (reading["meaning"] is None and (takes or reading["start"]))
    if not current:
        return None
    yes = yes or (reading["meaning"] is None and holds_a_yes(text, npc, thread, firm=True))
    if status == "declined":
        return "accepted" if yes else None
    if yes:
        return "accepted"
    if reading["meaning"] in {"decline", "withdraw"}:
        return "declined"
    return None


def _log(thread: dict[str, Any], at: int, kind: str) -> None:
    thread["log"] = [*thread.get("log", []), {"at": at, "kind": kind}][-MAX_LOG:]


def owner_mood(world: dict[str, Any], thread: dict[str, Any], npc: Any, *, this_exchange: int = 0) -> str:
    """Will this person offer the work to this stranger: 'yes', 'wary' or 'no'. Python's call.

    this_exchange: statements already recorded for the reply being judged, which are not
    an earlier conversation.
    """
    import npc_statements
    import relationships
    import vouching
    if not isinstance(npc, dict):
        return "no"
    state = view(world) or {"history": []}
    place_id = npc.get("place_role_of")
    past = [t for t in state["history"] if t.get("place_id") == place_id and t.get("offered_at") is not None]
    if relationships.score(world, npc.get("id")) <= -1 and past and past[-1]["status"] in {"failed", "abandoned"}:
        return "no"
    if vouching.needs_word(world, thread, npc):
        return "wary"
    seed = living_world._campaign_seed(world)
    said = npc_statements.view(world)["statements"].get(npc.get("id")) or []
    if _rank(seed, thread["thread_id"], "wary") % 100 < WARY_PERCENT and len(said) <= this_exchange:
        return "wary"
    return "yes"


def mark_offered(world: dict[str, Any], thread: dict[str, Any], npc: dict[str, Any], shown: str, turn: int) -> bool:
    """The terms were really spoken: only now is there an offer to answer."""
    if not transition(thread, "offered"):
        return False
    terms = thread["terms"]
    now = _now(world)
    thread.update(owner_npc_id=npc.get("id"), offered_turn=turn, offered_at=now, offer_line=shown.strip()[:400],
                  offer_line_turn=turn,
                  offered_terms_shown={"pay": terms.get("pay"), "days": terms.get("work_days"),
                                       "pay_basis": pay_basis(thread), "pay_timing": terms.get("pay_timing"),
                                       "deadline_text": terms.get("deadline_text")})
    _log(thread, now, "offered")
    return True


def learn_outcome(world: dict[str, Any], thread: dict[str, Any]) -> None:
    """The player has now heard how this ended; only from here does it exist for them."""
    if thread.get("outcome_known_turn") is None:
        thread["outcome_known_turn"] = int((world.get("flags") or {}).get("turn_index", 0) or 0)
        if thread.get("offered_at") is not None:
            note_event(world, thread, "learned", _CLOSE_SUMMARY.get(thread.get("status"), "İş kapandı"),
                       npc=owner_of(world, thread))


def arrival_line(world: dict[str, Any], place_id: Any) -> str | None:
    """Walking up to a place you had a job at: how it ended, once. Only on arrival."""
    import world_happenings
    state = view(world)
    if state is None:
        return None
    seed = living_world._campaign_seed(world)
    place = world.get("locations", {}).get(place_id) or {}
    for thread in reversed(state["history"]):
        status = thread.get("status")
        lines = job_lines("arrival", status) or []
        if (thread.get("place_id") != place_id or not lines or thread.get("offered_at") is None
                or thread.get("outcome_known_turn") is not None):
            continue
        learn_outcome(world, thread)
        line = lines[_rank(seed, thread["thread_id"], "arrival", status) % len(lines)]
        shown = sentence(_fill(line, who=_mid_sentence(thread.get("filled_by_name") or "başkası"),
                               owner=spoken_owner(world, thread), place=place.get("name", "")))
        return " ".join(part for part in (shown, world_happenings.first_sight(world, thread)) if part)
    import town_knowledge
    return world_happenings.arrival_line(world, place_id) or town_knowledge.notice_at(world, place_id)


def accept_hired(world: dict[str, Any], thread: dict[str, Any], turn: int | None = None) -> bool:
    if not transition(thread, "accepted"):
        return False
    now = _now(world)
    turn = int((world.get("flags") or {}).get("turn_index", 0) or 0) if turn is None else turn
    days = thread["terms"].get("work_days") or 1
    thread.update(accepted_at=now, accepted_turn=turn, starts_at=now, work_until=now + (days + 1) * DAY, days_worked=0, shift_seconds=0, paid_cp=0)
    thread.pop("declined_turn", None)
    if thread.get("type") == "trouble":  # it is in someone's hands now; only they can let it go
        thread.pop("fires_at", None)
        thread["terms"]["work_days"] = days
    _log(thread, now, "accepted")
    note_event(world, thread, "accepted", f"Anlaşıldı: {pay_text(thread)}", npc=owner_of(world, thread))
    return True


def decline(world: dict[str, Any], thread: dict[str, Any], turn: int) -> bool:
    if not transition(thread, "declined"):
        return False
    now = _now(world)
    thread.update(declined_turn=turn, expires_at=min(thread["expires_at"], now + DECLINE_HOURS * HOUR))
    _log(thread, now, "declined")
    return True


JOBS = ("hiring", "errand", "trouble")
WORKED = ("hiring", "trouble")  # what is done on the spot, a shift at a time
RECENT_CLOSE = 48 * HOUR


def _speaks_of_work(text, reading, thread, table):
    return _names_the_work(text, thread, table) or reading["meaning"] is not None


def recent_closed(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """Jobs of this person that ended in the last two days, newest first; a trouble that came down on them counts unasked."""
    state = view(world)
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    if state is None or not place_id:
        return []
    now = _now(world)
    return [t for t in reversed(state["history"]) if t.get("place_id") == place_id and t.get("type") in JOBS
            and (t.get("offered_at") is not None or t.get("status") == "fired")
            and now - (t.get("closed_at") or 0) < RECENT_CLOSE]


def jobs_of(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """This person's own work, the one in hand first."""
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    order = {"accepted": 0, "offered": 1, "declined": 2}
    return sorted((t for t in owned(world) if place_id and t.get("place_id") == place_id and t.get("type") in JOBS),
                  key=lambda t: (order.get(t["status"], 3), t.get("type") == "trouble"))


def deliveries_to(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """Accepted errands that end with this person."""
    return [t for t in owned(world) if t.get("status") == "accepted" and t.get("type") == "errand"
            and isinstance(npc, dict) and t.get("recipient_npc_id") == npc.get("id")]


def delivered_to(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """Errands that really ended in this person's hands."""
    state = view(world)
    if state is None or not isinstance(npc, dict):
        return []
    return [t for t in state["history"] if (t.get("status") == "done" or t.get("delivered_late"))
            and t.get("type") == "errand" and t.get("recipient_npc_id") == npc.get("id")]


def late_parcels(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """Errands that closed with the parcel still in the player's hand, where this person is who it belongs with."""
    from adventure import dialogue_jobs
    import world_happenings
    state = view(world)
    if state is None or not isinstance(npc, dict):
        return []
    came_for = world_happenings.about_of(world, npc)
    return [t for t in reversed(state["history"]) if t.get("type") == "errand"
            and t.get("status") in {"failed", "expired", "abandoned"}
            and (npc.get("id") in {t.get("recipient_npc_id"), t.get("owner_npc_id")} or t["thread_id"] == came_for)
            and dialogue_jobs.holds_parcel(world, t)]


def parcel_thread(world: dict[str, Any], item_id: Any) -> dict[str, Any] | None:
    """The job a parcel in the bag belongs to, open or closed."""
    state = view(world)
    return next((t for t in (*state["threads"], *state["history"])
                 if t.get("quest_id") and item_id == f"parcel:{t['quest_id']}"), None) if state else None


def gives_item(text: Any, npc: Any, thread: dict[str, Any]) -> bool:
    """'Paketi getirdim', 'buyur paketini', 'teslim': a handing-over, said now and not asked about."""
    table = answer_table()
    text = _own_line(text, table) if isinstance(text, str) and text.strip() else None
    if text is None:
        return False
    stems = _item_stems(thread)
    names = _names_of(npc)
    verbs = table["give"] | table["give_verbs"]
    for tokens, asked, _ in _clauses(text):
        body = [word for word in tokens if word not in names and word not in table["fillers"]]
        if asked or not body:
            continue
        if " ".join(body) in table["give"] or all(word in table["give"] for word in body):
            return True
        item = any(word in table["item_words"] or any(word.startswith(s) for s in stems) for word in body)
        if item and any(word in verbs for word in body):
            return True
    return False


def _matter_stems(thread: dict[str, Any], table: dict[str, Any]) -> set[str]:
    """The words of this very matter, cut short enough to meet 'borçlu' in 'borcunu'."""
    common = tuple(table.get("matter_common", ()))
    said = _folded(f"{thread.get('owner_line')} {thread.get('public_line')}").split()
    return {word[:4] for word in said if len(word) > 3 and not word.startswith(common)}


def speaks_of_the_matter(line: Any, thread: dict[str, Any]) -> bool:
    """This line is about this trouble: it says so, or it uses the trouble's own words."""
    table = answer_table()
    words = _folded(line).split()
    stems = _matter_stems(thread, table)
    return any(word.startswith(tuple(table.get("matter_nouns", ()))) for word in words) or (
        len({word[:4] for word in words} & stems) >= 2)


def worked_on_the_spot(thread: dict[str, Any]) -> bool:
    """Done a shift at a time beside its owner. A trouble that sends the player to someone is not."""
    return thread.get("type") in WORKED and not (thread.get("type") == "trouble" and thread.get("target_place_id"))


def matters_with(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """Troubles the player took on that come down to speaking with this person."""
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    return [t for t in owned(world) if place_id and t.get("status") == "accepted" and t.get("type") == "trouble"
            and t.get("target_place_id") == place_id]


def raises_the_matter(world: dict[str, Any], text: Any, npc: Any, thread: dict[str, Any]) -> bool:
    """The player brought it up with them: the owner's name, the trouble, its own words, or a yes to them bringing it up."""
    table = answer_table()
    line = _own_line(text, table) if isinstance(text, str) and text.strip() and table else None
    if line is None:
        return False
    words = _folded(line).split()
    place = world.get("locations", {}).get(thread.get("target_place_id")) or {}
    theirs = {word[:4] for word in _folded(f"{thread.get('recipient_name')} {place.get('name')}").split()}
    stems = _matter_stems(thread, table) - theirs
    owner = _folded(thread.get("owner_name")).split()[:1]
    if any(_REFUSED_DOING.search(word) for word in words if word not in table["accept"]):
        return False
    return (any(word.startswith(tuple(table.get("matter_nouns", ()))) or word[:4] in stems for word in words)
            or bool(owner and any(word.startswith(owner[0]) for word in words))
            or (_just_told(world, thread, npc) and holds_a_yes(text, npc, thread)))


def settle_matter(world: dict[str, Any], thread: dict[str, Any], npc: dict[str, Any]) -> None:
    """Spoken with the one it came down to: the trouble is over, with no clock and no coin."""
    thread["recipient_npc_id"] = npc.get("id")
    _close_as_done(world, thread)
    validate(world[KEY])


def what_it_takes(world: dict[str, Any], thread: dict[str, Any]) -> str:
    """Said on the screen as a trouble is taken on, so the player knows what they just agreed to do."""
    words = job_lines("text") or {}
    if worked_on_the_spot(thread):
        return words.get("trouble_stays", "")
    place = world.get("locations", {}).get(thread.get("target_place_id")) or {}
    return _fill(words.get("trouble_goes", ""), recipient=spoken_recipient(world, thread), target=place.get("name", ""))


def _just_told(world: dict[str, Any], thread: dict[str, Any], npc: Any) -> bool:
    last = _last_exchange(world, npc)
    return bool(last and last.get("npc")) and speaks_of_the_matter(last["npc"], thread)


def _is_on_the_table(world: dict[str, Any], thread: dict[str, Any], npc: Any) -> bool:
    """The player knows of it: put to them, overheard, or just told."""
    return thread.get("status") in {"offered", "declined"} or thread.get("heard_turn") is not None or (
        _just_told(world, thread, npc))


def _plain_help(line: str, table: dict[str, Any]) -> bool:
    """One clause is an offer of help and nothing in the line asks, bargains or hedges around it."""
    clauses = _clauses(line)
    phrases = table.get("help", frozenset())
    if any(after for _, _, after in clauses) or _has_phrase(_folded(line).split(), table["question_terms"]):
        return False
    for tokens, asked, _ in clauses:
        found = [" ".join(tokens[start:end]) for start in range(len(tokens))
                 for end in range(start + 1, min(start + 4, len(tokens)) + 1) if " ".join(tokens[start:end]) in phrases]
        beside = set(tokens) - {word for phrase in found for word in phrase.split()}
        if found and not asked and not beside & (table["hedges"] | {"mi", "mu"}):
            return True
    return False


def offers_to_help(world: dict[str, Any], text: Any, npc: Any, thread: dict[str, Any]) -> bool:
    """'Derdini ben hallederim': a trouble needs no spoken terms to be taken on, only the word."""
    table = answer_table()
    line = _own_line(text, table) if isinstance(text, str) and text.strip() and table else None
    if line is None or thread.get("type") != "trouble" or thread.get("status") not in (*PUBLIC, "offered", "declined"):
        return False
    words = _folded(line).split()
    refused = any(_REFUSED_DOING.search(word) for word in words if word not in table["accept"])  # 'tamam' ends like 'yapamam'
    return (_plain_help(line, table) and not refused and _is_on_the_table(world, thread, npc)
            and not any(t.get("status") == "accepted" for t in jobs_of(world, npc))
            and owner_mood(world, thread, npc) != "no" and not _door_shut(world, thread, npc))


def _door_shut(world: dict[str, Any], thread: dict[str, Any], npc: Any) -> bool:
    import vouching
    return isinstance(npc, dict) and vouching.needs_word(world, thread, npc)


def steps_into(world: dict[str, Any], text: Any, npc: Any, thread: dict[str, Any]) -> bool:
    """The model named a trouble nobody offered: only the player's own words, or a yes to it just told, take it on."""
    return not _door_shut(world, thread, npc) and (
        holds_a_yes(text, npc, thread, firm=True) or offers_to_help(world, text, npc, thread)
        or goes_to_the_work(text, thread) or (_just_told(world, thread, npc) and holds_a_yes(text, npc, thread)))


def turn_gate(world: dict[str, Any], npc: Any, text: Any) -> dict[str, Any] | None:
    """What this line does to this person's work: a decision, talk about it, or nothing."""
    for thread in deliveries_to(world, npc):
        if gives_item(text, npc, thread):
            return {"thread_id": thread["thread_id"], "decision": "give", "npc_id": npc.get("id")}
    for thread in late_parcels(world, npc):
        if gives_item(text, npc, thread):
            return {"thread_id": thread["thread_id"], "decision": "give_late", "npc_id": npc.get("id")}
    for thread in matters_with(world, npc):
        if raises_the_matter(world, text, npc, thread):
            return {"thread_id": thread["thread_id"], "decision": "matter", "npc_id": npc.get("id")}
    mine = jobs_of(world, npc)
    closed = recent_closed(world, npc)
    if not (mine or closed) or answer_table() == {}:
        return None
    for thread in mine:
        if (thread["status"] == "accepted" and thread.get("type") in WORKED and read_answer(text, npc, thread)["start"]
                and not _says_later(text, answer_table())):
            # A trouble that is someone else's door has no shift: its owner says where it is.
            return {"thread_id": thread["thread_id"], "npc_id": npc.get("id"),
                    "decision": "work" if worked_on_the_spot(thread) else None}
        if thread["status"] == "accepted" and asks_for_pay(text):
            return {"thread_id": thread["thread_id"], "decision": "pay", "npc_id": npc.get("id")}
        if thread["status"] == "accepted" and thread.get("type") == "errand":
            reading = read_answer(text, npc, thread)
            if (reading["take"] or reading["move"]) and reading["meaning"] in {None, "accept"}:
                return {"thread_id": thread["thread_id"], "decision": "take", "npc_id": npc.get("id"),
                        "reading": reading}
        decision = bind_player_decision(world, thread, text, npc)
        if decision:
            return {"thread_id": thread["thread_id"], "decision": decision, "npc_id": npc.get("id")}
        if (thread["status"] == "accepted" and thread.get("type") in WORKED and "?" not in text
                and does_the_work_now(text, thread)):
            return {"thread_id": thread["thread_id"], "npc_id": npc.get("id"),
                    "decision": "work" if worked_on_the_spot(thread) else None}
        if offers_to_help(world, text, npc, thread):
            return {"thread_id": thread["thread_id"], "decision": "take_up", "npc_id": npc.get("id")}
    for thread in closed:
        if thread["status"] == "done" and asks_for_pay(text):
            return {"thread_id": thread["thread_id"], "decision": "pay", "npc_id": npc.get("id")}
        if lapsed_yes(world, thread, text, npc):
            return {"thread_id": thread["thread_id"], "decision": "lapsed", "npc_id": npc.get("id")}
    for thread in (*mine, *closed):
        reading = read_answer(text, npc, thread)
        about = _speaks_of_work(text, reading, thread, answer_table())
        short = len(_folded(text).split()) <= 4  # a word or two back at the owner, not a new subject
        offered = thread.get("status") == "offered" and answers_the_offer(world, thread, npc)
        heard_a_yes = offered and holds_a_yes(text, npc, thread)  # the person hears it, and says what came of it
        if about or (offered and short) or heard_a_yes:
            return {"thread_id": thread["thread_id"], "decision": None, "npc_id": npc.get("id"), "yes_heard": heard_a_yes,
                    "offer_talk": _names_the_work(text, thread, answer_table())}
    return None


def apply_decision(world: dict[str, Any], thread: dict[str, Any], decision: str, turn: int) -> bool:
    """Write what the player said. Money and goods stay with their own owners."""
    if decision == "accepted" and thread.get("type") in WORKED:
        return accept_hired(world, thread, turn)
    if decision == "declined":
        return decline(world, thread, turn)
    if decision == "abandoned":
        if not transition(thread, "abandoned"):
            return False
        now = _now(world)
        thread["closed_at"] = now
        _log(thread, now, "abandoned")
        state = view(world)
        state["threads"], closed = _split_closed(state["threads"])
        state["history"].extend(closed)
        _trim_history(state, world)
        _apply_effects(world, [(thread["thread_id"], "abandoned")])
        return True
    return False


def _in_the_night(world) -> bool:
    import campaign_time
    hour = (campaign_time.public_time(world) or {}).get("hour", 12)
    return hour >= 20 or hour < 6


def _day_wage(thread: dict[str, Any], *, worked: int | None = None) -> int:
    """This day's share. A total splits evenly; the last day takes what is left.

    worked: the day count including the day being paid; read from the thread when not given.
    """
    terms = thread["terms"]
    pay, days = terms.get("pay") or 0, terms.get("work_days") or 1
    if pay_basis(thread) == "daily":
        return pay
    if worked is None:
        worked = thread.get("days_worked", 0)  # already includes today
    return pay - (pay // days) * (days - 1) if worked >= days else pay // days


def _pay_wage(world, thread, amount, day):
    """The day's earned wage, once per day (A4): the one owner pays it from the day's pool, opened only for it.

    The owner's own purse is never assumed to hold it. Returns the resolution; a repeated day is `replayed`.
    """
    import economic_actions
    return economic_actions.settle_entitlement(
        economic_actions.EconomicState(world=world, character=None), event_id=f"wage:{thread['thread_id']}:{day}",
        payer_id=f"thread-pool:{thread['thread_id']}:{day}", recipient_id="player", amount_cp=amount)


def _credit_day(world: dict[str, Any], thread: dict[str, Any], day: int) -> tuple[int, bool]:
    """One day of the work paid, then counted, and the job closed if that was the last of it.

    The wage is worked out for the day being paid (days worked so far plus this one), paid once through the
    entitlement ledger, and only a new payment (or a day with no pay) moves the counters: a day already paid is
    neither counted nor paid again, and does not close the job early.
    """
    worked = thread.get("days_worked", 0) + 1
    amount = _day_wage(thread, worked=worked)
    if amount:
        paid = _pay_wage(world, thread, amount, day)
        if paid.status != "applied" or paid.replayed:
            return 0, False
    thread["days_worked"] = worked
    thread["last_paid_day_index"] = day
    thread["shift_seconds"] = 0
    if amount:
        thread["paid_cp"] = thread.get("paid_cp", 0) + amount
        note_event(world, thread, "paid", f"{amount} bakır ödendi", npc=owner_of(world, thread))
    if thread["days_worked"] < (thread["terms"].get("work_days") or 1):
        return amount, False
    return amount, _close_as_done(world, thread)


def _close_as_done(world: dict[str, Any], thread: dict[str, Any]) -> bool:
    if not transition(thread, "done"):
        return False
    now = _now(world)
    thread["closed_at"] = now
    _log(thread, now, "done")
    state = view(world)
    state["threads"], closed = _split_closed(state["threads"])
    state["history"].extend(closed)
    _trim_history(state, world)
    _apply_effects(world, [(thread["thread_id"], "done")])
    return True


def _today(world: dict[str, Any]) -> int:
    import campaign_time
    return campaign_time.public_time(world)["day_index"]


def wage_due(world: dict[str, Any], thread: dict[str, Any]) -> tuple[int, str | None]:
    """What asking for the money pays right now, or why it pays nothing.

    The hired hand's word is taken for one day at a time: the wage only moves once a day,
    never past the agreed total, and not to someone who shook on it a moment ago.
    """
    if thread.get("status") != "accepted":
        return 0, "settled" if thread.get("status") == "done" else None
    if thread.get("type") == "trouble":
        return 0, "no_pay"
    if thread.get("type") != "hiring":
        return 0, "on_delivery"
    if thread.get("last_paid_day_index") == _today(world):
        return 0, "paid_today"
    turn = int((world.get("flags") or {}).get("turn_index", 0) or 0)
    if turn - thread.get("accepted_turn", turn) < 2 and _now(world) - (thread.get("accepted_at") or 0) < HOUR:
        return 0, "not_yet"
    return _day_wage({**thread, "days_worked": thread.get("days_worked", 0) + 1}), None


def pay_day(world: dict[str, Any], thread: dict[str, Any]) -> tuple[int, bool]:
    """Pay what is due through the wallet: the amount, and whether that finished the job."""
    amount, _ = wage_due(world, thread)
    if not amount:
        return 0, False
    paid = _credit_day(world, thread, _today(world))
    validate(world[KEY])
    return paid


def paid_line(amount: int, finished: bool) -> str:
    words = job_lines("text") or {}
    return " ".join(line for line in (_fill(words.get("pay_counted", ""), amount=amount),
                                      words.get("shift_done", "") if finished else "") if line)


def _mid_sentence(label: str) -> str:
    return "bir " + label[4:] if label.startswith("Bir ") else label


def sentence(text: str) -> str:
    return tr_case.upper_first(text)


def spoken_owner(world: dict[str, Any], thread: dict[str, Any]) -> str:
    """The owner as the player knows them; a name not yet learned stays off the screen."""
    npc = owner_of(world, thread)
    return _mid_sentence(living_world.public_npc_name(npc) if isinstance(npc, dict) else (thread.get("owner_name") or ""))


def spoken_recipient(world: dict[str, Any], thread: dict[str, Any]) -> str:
    npc = recipient_of(world, thread)
    return _mid_sentence(living_world.public_npc_name(npc) if isinstance(npc, dict) else (thread.get("recipient_name") or ""))


def _shift_text(world, thread, *parts, short=False, worked=0):
    import bound_text
    lines = ([job_lines("text", "shift_some")] if short else job_lines("shift")) or []
    day = thread.get("days_worked", 0)
    seed = living_world._campaign_seed(world)
    place = world.get("locations", {}).get(thread.get("place_id")) or {}
    first = bound_text.work_line(world, thread, worked, day) or (
        lines[_rank(seed, thread["thread_id"], "shift", day) % len(lines)] if lines else "")
    return " ".join(p for p in (sentence(_fill(first, owner=spoken_owner(world, thread), place=place.get("name", ""))), *parts) if p)


def _shift_plan(world: dict[str, Any], thread: dict[str, Any], text: Any, hours: int) -> tuple[list[int], bool, bool]:
    """(the spans, one a day; cut short; whole days asked for). Never more days than the job has left, never a clock it did not say."""
    import campaign_time
    try:
        wanted = campaign_time.requested_duration(text) or 0
    except ValueError:
        wanted = 0
    if wanted >= DAY:
        left = (thread["terms"].get("work_days") or 1) - thread.get("days_worked", 0)
        return [hours * HOUR] * max(1, min(wanted // DAY, left)), False, True
    until = campaign_time.until_named_hour(world, _folded(text))
    if until is not None and until < DAY / 2:
        return [until], until < hours * HOUR, False
    return [wanted or hours * HOUR], bool(wanted) and wanted < hours * HOUR, False


def _one_shift(world, thread_id, seconds, hours, words):
    """One span of work: the clock really moves, then the record is read again by id. (copper, closed, why it paid nothing)"""
    import game
    thread = by_id(world, thread_id)
    day = _today(world)  # a shift belongs to the day it began
    thread["shift_until"] = _now(world) + seconds
    try:
        result = game.advance_campaign_time(seconds, "work_shift")
    finally:
        by_id(world, thread_id).pop("shift_until", None)
    thread = by_id(world, thread_id)
    thread["shift_seconds"] = thread.get("shift_seconds", 0) + result["elapsed_seconds"]
    if thread["status"] != "accepted":
        return result["elapsed_seconds"], 0, False, words.get("shift_short", "")
    if thread.get("last_paid_day_index") == day:
        thread["shift_seconds"] = 0  # a day already paid for: these hours count toward nothing
        return result["elapsed_seconds"], 0, False, words.get("shift_no_pay", "")
    if thread["shift_seconds"] < hours * HOUR:
        return result["elapsed_seconds"], 0, False, words.get("shift_short", "")
    amount, finished = _credit_day(world, thread, day)
    return result["elapsed_seconds"], amount, finished, ""


def work_turn(session: Any, thread_id: str, text: Any) -> dict[str, Any]:
    """The work the line asks for, a day at a time, with one day's pay for each day really worked.

    The clock step can replace the whole thread state, cut the shift short or kill the
    player, so what is credited is only what actually passed.
    """
    import campaign_time
    import game
    world = session.world_state
    thread = by_id(world, thread_id)
    words = job_lines("text") or {}
    hours = job_lines("shift_hours") or 8
    spans, short, whole_days = _shift_plan(world, thread, text, hours)
    before = copy.deepcopy(world)
    passed, paid, days_paid, finished, unpaid, worked = 0, 0, 0, False, "", 0
    for index, span in enumerate(spans):
        if index:  # the rest of the night between two days of it
            passed += game.advance_campaign_time(DAY - spans[index - 1], "work_shift")["elapsed_seconds"]
        elif whole_days and thread.get("last_paid_day_index") == _today(world):  # today is paid: the days start tomorrow
            passed += game.advance_campaign_time(campaign_time.until_morning(world), "work_shift")["elapsed_seconds"]
        worked, amount, finished, why = _one_shift(world, thread_id, span, hours, words)
        passed += worked
        paid += amount
        days_paid += bool(amount)
        unpaid = why
        thread = by_id(world, thread_id)
        if why or finished or thread["status"] != "accepted":
            break
    parts = [unpaid] if unpaid else []
    if paid:
        line = "shift_paid_days" if days_paid > 1 else "shift_paid"
        parts.append(_fill(words.get(line, ""), amount=paid, days=_spoken_number(days_paid)))
    elif not unpaid:
        parts.append(words.get("trouble_done", ""))
    if finished and paid:
        parts.append(_fill(words.get("shift_done", ""), owner=spoken_owner(world, thread)))
    validate(world[KEY])
    alive = session.character.get("current_hp", 0) > 0
    shown = _shift_text(world, thread, *parts, short=short, worked=worked if alive else 0)
    flags = world.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    action = {"action": "work", "status": "resolved", "success": True, "state_changes": ["campaign_time", "currency"],
              "elapsed_seconds": passed, "direct_response": shown}
    session.evaluate_quest_events(before, action)
    session.messages.extend([{"role": "user", "content": str(text)}, {"role": "assistant", "content": shown}])
    return {"messages": session.messages, "narration": shown, "model_calls": 0, "action_result": action}


def pay_text(thread: dict[str, Any]) -> str:
    words = job_lines("text") or {}
    pay = (thread.get("terms") or {}).get("pay")
    if pay is None:
        return words.get("pay_none", "")
    name = {"daily": "pay_daily", "total": "pay_total", "per_trip": "pay_delivery"}.get(pay_basis(thread), "pay_delivery")
    return _fill(words.get(name, "{pay} bakır"), pay=pay)


def timing_text(thread: dict[str, Any]) -> str:
    words = job_lines("text") or {}
    return words.get(f"timing_{(thread.get('terms') or {}).get('pay_timing')}", "")


def start_text(world: dict[str, Any], thread: dict[str, Any]) -> str:
    """Python's answer to 'when do I start'; the model only repeats it."""
    import campaign_time
    words = job_lines("text") or {}
    hour = (campaign_time.public_time(world) or {}).get("hour", 9)
    if thread.get("night_only"):
        return words.get("start_tonight", "")
    return words.get("start_today", "") if hour < 16 else words.get("start_tomorrow", "")


def can_start_now(world: dict[str, Any], thread: dict[str, Any]) -> bool:
    return not thread.get("night_only") or _in_the_night(world)


def status_line(world: dict[str, Any], thread: dict[str, Any], kind: str) -> str:
    """The plain fact of where this job stands, for this person to say in their own words."""
    own = thread.get("status_lines") if isinstance(thread.get("status_lines"), dict) else {}
    if kind == "accepted" and thread.get("type") == "trouble" and not worked_on_the_spot(thread):
        kind = "accepted_elsewhere"
    line = None if thread.get("accepted_at") is not None else own.get(kind)  # written for an offer nobody took
    if line:
        line = _fill(job_lines("shared", "own_plan") or "{plan}", plan=line)
    else:
        lines = job_lines(thread.get("type"), kind) or []
        if not lines:
            return ""
        line = lines[_rank(living_world._campaign_seed(world), thread["thread_id"], kind) % len(lines)]
    terms = thread.get("terms") or {}
    place = world.get("locations", {}).get(thread.get("target_place_id")) or {}
    noun = thread.get("item_noun") or ""
    return _fill(line, days=terms.get("work_days") or "", pay_text=pay_text(thread), timing_text=timing_text(thread),
                 start=start_text(world, thread), item=tr_case.upper_first(noun),
                 recipient=thread.get("recipient_name") or "", target=place.get("name", ""),
                 deadline_text=terms.get("deadline_text") or "", who=thread.get("filled_by_name") or "başkası")


def _replenish(world, state, now):
    seed = living_world._campaign_seed(world)
    for settlement_id in state["seeded"]:
        recent = {t.get("template_id") for t in [*state["history"], *state["threads"]]
                  if t.get("settlement_id") == settlement_id}
        mine = [t for t in state["threads"] if t.get("settlement_id") == settlement_id]
        last_type = mine[-1]["type"] if mine else None
        leaning = _leaning(world, settlement_id, now // 86400)
        order = sorted(catalog()["templates"], key=lambda item: (
            item["id"] != leaning, _rank(seed, settlement_id, "later", now // 86400, item["id"])))
        for template in order:
            if len(active(world, settlement_id)) >= MIN_OPEN or len(state["threads"]) >= MAX_ACTIVE:
                break
            if template["id"] in recent or template["type"] == last_type:
                continue
            if _open_thread(world, state, template, settlement_id, create=False, now=now):
                last_type = template["type"]


CLOSE_FAILED = "close_failed"
CLOSE_FAILURES_BEFORE_PARKING = 3


class _CloseFailed(Exception):
    """One thread's close effects could not land; carries which thread so only it is held back."""

    def __init__(self, thread_id: str, error: BaseException) -> None:
        super().__init__(thread_id)
        self.thread_id = thread_id
        self.error = error


def parked(thread: Any) -> bool:
    """A close that failed every time it was tried: the thread waits as it is and holds no one else up."""
    marker = thread.get(CLOSE_FAILED) if isinstance(thread, dict) else None
    return isinstance(marker, dict) and marker.get("parked") is True


def _note_close_failure(state, failure):
    """Count a failed close on the thread itself (the rolled-back record); the third in a row parks it."""
    thread = next((t for t in state["threads"] if t.get("thread_id") == failure.thread_id), None)
    if thread is None:
        return False
    marker = thread.get(CLOSE_FAILED) if isinstance(thread.get(CLOSE_FAILED), dict) else {}
    count = (marker.get("count") if type(marker.get("count")) is int else 0) + 1
    marker = {"count": count, "error": type(failure.error).__name__}
    if count >= CLOSE_FAILURES_BEFORE_PARKING:
        marker["parked"] = True
        _LOG.warning("A job's close failed %s times (%s); it is held back so the town can move on: %s",
                     count, marker["error"], failure.thread_id)
    thread[CLOSE_FAILED] = marker
    return marker.get("parked") is True


def _attempt_tick(world, state, now):
    work = copy.deepcopy(state)
    world[KEY] = work
    effects = _close_due(world, work, now)
    _replenish(world, work, now)
    work["last_tick"] = now
    validate(work)
    sync_from_quests(world, work)
    _apply_effects(world, effects)
    validate(work)


def tick(world: dict[str, Any], now: int) -> None:
    """Move the town along when campaign time passes. No model; the same moment twice does nothing."""
    state = view(world)
    if state is None or type(now) is not int or now <= state["last_tick"]:
        return
    # Kept only whole: a close and everything it means land together, or the town is as it was
    # and the next tick tries again. Saved places stay the same objects: callers hold them across a clock step.
    # A close that fails three times running is parked (its record keeps its status and says why), and the
    # step is tried once more without it, so one broken close never freezes every other thread.
    for _try in range(2):
        before = copy.deepcopy({key: value for key, value in world.items() if key != KEY})
        try:
            _attempt_tick(world, state, now)
            return
        except Exception as exc:
            _LOG.exception("World threads could not move on.")
            _put_back(world, before, keep=(KEY,))
            world[KEY] = state
            if not isinstance(exc, _CloseFailed) or not _note_close_failure(state, exc):
                return


_MISSING = object()


def _put_back(live: Any, saved: Any, keep: tuple[str, ...] = ()) -> None:
    """Undo a failed step in place, so a record a caller already holds is the one that comes back."""
    if isinstance(live, dict):
        for key in [key for key in live if key not in saved and key not in keep]:
            del live[key]
        for key, value in saved.items():
            current = live.get(key, _MISSING)
            if current is _MISSING or current != value:
                if type(current) is type(value) and isinstance(value, (dict, list)) and (
                        isinstance(value, dict) or len(current) == len(value)):
                    _put_back(current, value)
                else:
                    live[key] = value
        return
    for index, value in enumerate(saved):
        current = live[index]
        if current != value:
            if type(current) is type(value) and isinstance(value, (dict, list)) and (
                    isinstance(value, dict) or len(current) == len(value)):
                _put_back(current, value)
            else:
                live[index] = value


def validate(state: Any) -> None:
    if not isinstance(state, dict) or state.get("version") != SCHEMA_VERSION:
        raise ValueError("World thread state is invalid.")
    import world_happenings
    world_happenings.validate(state.get("happenings"))
    world_happenings._validate_links(state.get(world_happenings.LINKS))
    threads, history = state.get("threads"), state.get("history")
    if (
        not isinstance(threads, list) or not isinstance(history, list)
        or not isinstance(state.get("seeded"), list)
        or type(state.get("next_number")) is not int or type(state.get("last_tick")) is not int
        or len(threads) > MAX_ACTIVE or len(history) > MAX_HISTORY * 2
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
        if thread["status"] in TERMINAL and any(
                thread.get(name) is not None and type(thread.get(name)) is not int for name in _OPTIONAL_INTS):
            raise ValueError("World thread record is invalid.")
        if "xp_due" in thread and (type(thread["xp_due"]) is not int or not 0 < thread["xp_due"] <= 100_000
                                   or thread["status"] != "done"):  # owed only for a finished job, and never nothing
            raise ValueError("World thread record is invalid.")
        if any(thread.get(name) is not None and not isinstance(thread.get(name), str) for name in _OPTIONAL_TEXTS):
            raise ValueError("World thread record is invalid.")
