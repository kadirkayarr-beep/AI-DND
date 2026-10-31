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
import local_places

KEY = "world_threads_v1"
SCHEMA_VERSION = 1
DATA_PATH = Path(__file__).resolve().parents[1] / "content" / "world" / "town_threads.json"
ANSWERS_PATH = DATA_PATH.with_name("offer_answers.json")
MAX_ACTIVE = 8
MAX_HISTORY = 8
MAX_LOG = 6
WARY_PERCENT = 20
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
TERMINAL = ("filled_by_other", "expired", "done", "failed", "abandoned")
STATUSES = (*OWNED, *TERMINAL)
# The only moves a thread may make. A mention never reopens anything.
TRANSITIONS = {
    "open": {"heard", "offered", "filled_by_other", "expired"},
    "heard": {"offered", "filled_by_other", "expired"},
    "offered": {"accepted", "declined", "expired"},
    "declined": {"accepted", "filled_by_other", "expired"},
    "accepted": {"done", "failed", "expired", "abandoned"},
}
_OPTIONAL_INTS = ("offered_turn", "offered_at", "declined_turn", "accepted_at", "starts_at", "work_until",
                  "days_worked", "shift_seconds", "shift_until", "last_paid_day_index", "paid_cp",
                  "outcome_known_turn")
_OPTIONAL_TEXTS = ("owner_npc_id", "recipient_npc_id", "quest_id", "item_noun", "filled_by_npc_id", "filled_by_name",
                   "offer_line")
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
            "threads": [], "history": []}


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
    return next((t for t in (*state["threads"], *state["history"]) if t.get("thread_id") == thread_id), None) if state else None


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
    if template.get("night_only"):
        thread["night_only"] = True
    if template.get("item_noun"):
        thread["item_noun"] = template["item_noun"]
    if template.get("status_lines"):
        thread["status_lines"] = template["status_lines"]
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
    ) or (thread.get("type") == "hiring" and type(thread.get("work_until")) is not int)


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


def _due(thread):
    """When time alone closes this thread; None while nothing is waiting on the clock."""
    status = thread.get("status")
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
    if thread.get("type") == "hiring" and now > until and thread.get("days_worked", 0) < (thread["terms"].get("work_days") or 0):
        return "failed", until
    return None


def _close_due(world, state, now):
    seed = living_world._campaign_seed(world)
    closing = sorted(
        ((found, thread) for thread in state["threads"]
         if (found := _time_outcome(world, thread, now, seed)) is not None),
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
    _trim_history(state)
    return effects


def _split_closed(threads):
    return [t for t in threads if t["status"] not in TERMINAL], [t for t in threads if t["status"] in TERMINAL]


def _trim_history(state):
    """Old closings go; one the player had a hand in stays until they have learned how it ended."""
    waiting = [t for t in state["history"] if t.get("offered_at") is not None and t.get("outcome_known_turn") is None]
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
        if thread.get("status") == "accepted" and status and transition(thread, status):
            thread["closed_at"] = _now(world)
            effects.append((thread["thread_id"], status))
    if effects:
        state["threads"], closed = _split_closed(state["threads"])
        state["history"].extend(closed)
        _trim_history(state)
        _apply_effects(world, effects)
    return effects


_RELATION = {"done": 1, "abandoned": -1, "failed": -1}


def _apply_effects(world, effects):
    """What a close means beyond the thread. Runs only after the state itself is valid."""
    import relationships
    from adventure import director
    from adventure.transitions import TransitionError
    for thread_id, status in effects:
        thread = by_id(world, thread_id)
        if thread is None:
            continue
        owner = owner_of(world, thread)
        if status in _RELATION and isinstance(owner, dict) and isinstance(owner.get("id"), str):
            relationships.note(world, owner["id"], _RELATION[status], f"thread:{thread_id}:{status}"[:160])
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


def names_number(text: Any, number: Any) -> bool:
    """The figure as said aloud: '38', 'otuz sekiz', 'otuz sekize'. No digit inside another number."""
    if type(number) is not int:
        return False
    words = _folded(text).split()
    if str(number) in words:
        return True
    wanted = _spoken_number(number).split()
    if not wanted:
        return False
    for start in range(len(words) - len(wanted) + 1):
        window = words[start:start + len(wanted)]
        short = len(wanted[-1]) < 4  # 'on' is not 'onu'
        ending = window[-1] == wanted[-1] or (not short and window[-1].startswith(wanted[-1])
                                              and len(window[-1]) <= len(wanted[-1]) + 2)
        if window[:-1] == wanted[:-1] and ending and (
                len(wanted) > 1 or start == 0 or words[start - 1] not in _NUMBER_TENS):
            return True
    return False


def _stem(word: str) -> str:
    """'mektup' also has to find 'mektubu', 'paket' 'paketi'."""
    return word[:-1] if word[-1:] in {"p", "c", "t", "k", "g"} and len(word) > 3 else word


def _item_stems(thread: dict[str, Any]) -> tuple[str, ...]:
    words = _folded(thread.get("item_noun")).split()
    return tuple(_stem(word) for word in words if len(word) > 2)


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
    return found


def _names_of(npc: Any) -> frozenset[str]:
    if not isinstance(npc, dict):
        return frozenset()
    return frozenset(word for key in ("name", "public_name", "role") for word in _folded(npc.get(key)).split())


def _has_phrase(tokens: list[str], phrases: frozenset[str]) -> bool:
    return any(" ".join(tokens[start:end]) in phrases
               for start in range(len(tokens)) for end in range(start + 1, min(start + 4, len(tokens)) + 1))


def _read_clause(tokens, asked, table, names, item_stems):
    """One clause's meaning, or 'other' when it is something else entirely."""
    is_item = lambda word: word in table["item_words"] or any(word.startswith(stem) for stem in item_stems)
    fillers = table["fillers"] | names
    body = list(tokens)
    while body and (body[0] in table["discourse"] or body[0] in names):
        body.pop(0)
    while body and body[-1] in fillers:
        body.pop()
    if not body:
        return "neutral"
    body = [word for index, word in enumerate(body) if index == 0 or word != body[index - 1]]
    phrase = " ".join(body)
    if phrase in table["unclear"] and _has_phrase(body, table["question_terms"]):
        return "terms"
    if phrase in table["unclear"] or (set(body) & _REPORTED):
        return "unclear"
    if any(word.endswith(_CONDITIONAL_ENDS) for word in body):
        return "unclear"
    for meaning in ("decline", "withdraw", "accept"):
        if phrase in table[meaning]:
            return "question" if asked else meaning
    if _has_phrase(body, table["question_terms"]):
        return "terms"
    if any(word in table["hedges"] for word in body):
        return "unclear"
    if asked or any(word in table["question_words"] for word in body) or _has_phrase(body, table["question_words"]):
        return "question"
    harmless = fillers | table["reference"] | table["item_words"]
    for size in range(len(body) - 1, 0, -1):
        head, rest = " ".join(body[:size]), body[size:]
        if all(word in harmless or is_item(word) for word in rest):
            for meaning in ("decline", "withdraw", "accept"):
                if head in table[meaning]:
                    return meaning
    bare_yes = {word for word in body[:2] if word in table["accept"]}
    plain = [word for word in body if word not in bare_yes and word not in fillers]
    if plain and all(word in table["take"] or is_item(word) for word in plain) and any(word in table["take"] for word in plain):
        return "take"
    if " ".join(plain) in table["start"] and plain:
        return "start"
    numbers = {*_NUMBER_ONES, *_NUMBER_TENS, "saat", "saatlik", "gun", "gunluk"}
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


def read_answer(text: Any, npc: Any = None, thread: dict[str, Any] | None = None) -> dict[str, Any]:
    """What this line says about an offer, by the lists alone. Knows nothing of any offer."""
    reading = {"meaning": None, "terms": False, "question": False, "take": False, "give": False,
               "start": False, "move": False, "reference": False}
    table = answer_table()
    if not isinstance(text, str) or not text.strip() or not table or any(mark in text for mark in _QUOTES):
        return reading
    whole = _folded(text)
    names = _names_of(npc)
    stems = _item_stems(thread or {})
    words = whole.split()
    reading["reference"] = any(word in table["reference"] or any(word.startswith(s) for s in stems) for word in words) or (
        _has_phrase(words, table["reference"]))
    reading["terms"] = False
    if whole in table["unclear"]:
        reading["terms"] = _has_phrase(words, table["question_terms"])
        return reading
    if "?" not in text:
        for meaning in ("decline", "withdraw", "accept"):
            if whole in table[meaning]:
                return {**reading, "meaning": meaning}
    clauses = _clauses(text)
    kinds = []
    for tokens, asked, after_but in clauses:
        kind = _read_clause(tokens, asked, table, names, stems)
        repaired = tokens[0] in table["repair"] or " ".join(tokens[:2]) in table["repair"]
        if repaired and kinds:
            kinds = []  # 'yok ya... neyse olur': the later word is the answer
        if after_but and kind not in {"question", "terms"}:
            kind = "unclear"  # 'olur ama...' with a condition is not yet a yes
        kinds.append(kind)
    decided = _DECISIONS & set(kinds)
    reading["question"] = "question" in kinds
    reading["take"], reading["give"] = "take" in kinds, "give" in kinds
    reading["start"], reading["move"] = "start" in kinds, "move" in kinds
    if "terms" in kinds:
        return {**reading, "terms": True}
    if "unclear" in kinds or "other" in kinds or len(decided) > 1:
        return {**reading, "take": False, "give": False, "start": False, "move": False}
    if decided:
        return {**reading, "meaning": decided.pop()}
    return reading


def _last_exchange(world, npc):
    log = (world.get("npc_speech_log") or {}).get(npc.get("id")) if isinstance(npc, dict) else None
    return log[-1] if isinstance(log, list) and log and isinstance(log[-1], dict) else None


def _asks_something_else(line: str, thread: dict[str, Any], table) -> bool:
    """The line ended on another question: 'olur' answers that one, not the job."""
    if not line.rstrip().endswith("?"):
        return False
    last = re.split(r"[.!…]+", line.rstrip())[-1]
    words = _folded(last).split()
    stems = _item_stems(thread)
    return not (
        _has_phrase(words, table["close_words"]) or any(word.startswith(s) for s in stems for word in words)
        or any(word.startswith(close) for close in table["close_words"] if " " not in close for word in words)
        or names_number(last, (thread.get("terms") or {}).get("pay"))
    )


def answers_the_offer(world: dict[str, Any], thread: dict[str, Any], npc: Any) -> bool:
    """This person's last line to the player was this very offer, and asked nothing else."""
    last = _last_exchange(world, npc)
    line = thread.get("offer_line")
    return bool(last and line and last.get("npc") == line) and not _asks_something_else(line, thread, answer_table())


def bind_player_decision(world: dict[str, Any], thread: dict[str, Any], text: Any, npc: Any) -> str | None:
    """Python's reading of the player's own words on this thread. Writes nothing."""
    status = thread.get("status")
    if status not in {"offered", "declined", "accepted"}:
        return None
    reading = read_answer(text, npc, thread)
    if status == "accepted":
        return "abandoned" if reading["meaning"] == "withdraw" else None
    if reading["terms"]:
        return "questioning_terms" if status == "offered" else None
    current = reading["reference"] or answers_the_offer(world, thread, npc)
    yes = reading["meaning"] == "accept" or (reading["meaning"] is None and (reading["take"] or reading["start"]))
    if not current:
        return None
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
    if not isinstance(npc, dict):
        return "no"
    state = view(world) or {"history": []}
    place_id = npc.get("place_role_of")
    past = [t for t in state["history"] if t.get("place_id") == place_id and t.get("offered_at") is not None]
    if relationships.score(world, npc.get("id")) <= -1 and past and past[-1]["status"] in {"failed", "abandoned"}:
        return "no"
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
                  offered_terms_shown={"pay": terms.get("pay"), "days": terms.get("work_days"),
                                       "pay_basis": pay_basis(thread), "pay_timing": terms.get("pay_timing"),
                                       "deadline_text": terms.get("deadline_text")})
    _log(thread, now, "offered")
    return True


def accept_hired(world: dict[str, Any], thread: dict[str, Any]) -> bool:
    if not transition(thread, "accepted"):
        return False
    now = _now(world)
    days = thread["terms"].get("work_days") or 1
    thread.update(accepted_at=now, starts_at=now, work_until=now + (days + 1) * DAY, days_worked=0, shift_seconds=0,
                  paid_cp=0)
    thread.pop("declined_turn", None)
    _log(thread, now, "accepted")
    return True


def decline(world: dict[str, Any], thread: dict[str, Any], turn: int) -> bool:
    if not transition(thread, "declined"):
        return False
    now = _now(world)
    thread.update(declined_turn=turn, expires_at=min(thread["expires_at"], now + DECLINE_HOURS * HOUR))
    _log(thread, now, "declined")
    return True


JOBS = ("hiring", "errand")
RECENT_CLOSE = 48 * HOUR


def _speaks_of_work(text, reading, thread, table):
    words = _folded(text).split()
    stems = _item_stems(thread)
    return bool(set(words) & table["work_terms"]) or _has_phrase(words, table["question_terms"]) or any(
        word.startswith(stem) for stem in stems for word in words) or reading["meaning"] is not None


def recent_closed(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """Jobs of this person that ended in the last two days, newest first."""
    state = view(world)
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    if state is None or not place_id:
        return []
    now = _now(world)
    return [t for t in reversed(state["history"]) if t.get("place_id") == place_id and t.get("type") in JOBS
            and t.get("offered_at") is not None and now - (t.get("closed_at") or 0) < RECENT_CLOSE]


def jobs_of(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """This person's own work, the one in hand first."""
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    order = {"accepted": 0, "offered": 1, "declined": 2}
    return sorted((t for t in owned(world) if place_id and t.get("place_id") == place_id and t.get("type") in JOBS),
                  key=lambda t: order.get(t["status"], 3))


def deliveries_to(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """Accepted errands that end with this person."""
    return [t for t in owned(world) if t.get("status") == "accepted" and t.get("type") == "errand"
            and isinstance(npc, dict) and t.get("recipient_npc_id") == npc.get("id")]


def gives_item(text: Any, npc: Any, thread: dict[str, Any]) -> bool:
    """'Paketi getirdim', 'buyur paketini', 'teslim': a handing-over, said now and not asked about."""
    table = answer_table()
    if not isinstance(text, str) or any(mark in text for mark in _QUOTES):
        return False
    stems = _item_stems(thread)
    names = _names_of(npc)
    verbs = table["give"] | table["give_verbs"]
    for tokens, asked, _ in _clauses(text):
        body = [word for word in tokens if word not in names and word not in table["fillers"]]
        if asked or not body:
            continue
        if " ".join(body) in table["give"]:
            return True
        item = any(word in table["item_words"] or any(word.startswith(s) for s in stems) for word in body)
        if item and any(word in verbs for word in body):
            return True
    return False


def turn_gate(world: dict[str, Any], npc: Any, text: Any) -> dict[str, Any] | None:
    """What this line does to this person's work: a decision, talk about it, or nothing."""
    for thread in deliveries_to(world, npc):
        if gives_item(text, npc, thread):
            return {"thread_id": thread["thread_id"], "decision": "give", "npc_id": npc.get("id")}
    mine = jobs_of(world, npc)
    closed = recent_closed(world, npc)
    if not (mine or closed) or answer_table() == {}:
        return None
    for thread in mine:
        if thread["status"] == "accepted" and thread.get("type") == "errand":
            reading = read_answer(text, npc, thread)
            if reading["take"] or reading["move"]:
                return {"thread_id": thread["thread_id"], "decision": "take", "npc_id": npc.get("id"),
                        "reading": reading}
        decision = bind_player_decision(world, thread, text, npc)
        if decision:
            return {"thread_id": thread["thread_id"], "decision": decision, "npc_id": npc.get("id")}
    for thread in (*mine, *closed):
        reading = read_answer(text, npc, thread)
        about = _speaks_of_work(text, reading, thread, answer_table())
        current = thread.get("status") == "offered" and answers_the_offer(world, thread, npc)
        if about or current:
            return {"thread_id": thread["thread_id"], "decision": None, "npc_id": npc.get("id")}
    return None


def apply_decision(world: dict[str, Any], thread: dict[str, Any], decision: str, turn: int) -> bool:
    """Write what the player said. Money and goods stay with their own owners."""
    if decision == "accepted" and thread.get("type") == "hiring":
        return accept_hired(world, thread)
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
        _trim_history(state)
        _apply_effects(world, [(thread["thread_id"], "abandoned")])
        return True
    return False


def pay_text(thread: dict[str, Any]) -> str:
    words = job_lines("text") or {}
    pay = (thread.get("terms") or {}).get("pay")
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


def status_line(world: dict[str, Any], thread: dict[str, Any], kind: str) -> str:
    """The plain fact of where this job stands, for this person to say in their own words."""
    own = thread.get("status_lines") if isinstance(thread.get("status_lines"), dict) else {}
    line = own.get(kind)
    if not line:
        lines = job_lines(thread.get("type"), kind) or []
        if not lines:
            return ""
        line = lines[_rank(living_world._campaign_seed(world), thread["thread_id"], kind) % len(lines)]
    terms = thread.get("terms") or {}
    place = world.get("locations", {}).get(thread.get("target_place_id")) or {}
    noun = thread.get("item_noun") or ""
    return _fill(line, days=terms.get("work_days") or "", pay_text=pay_text(thread), timing_text=timing_text(thread),
                 start=start_text(world, thread), item=noun[:1].upper() + noun[1:],
                 recipient=thread.get("recipient_name") or "", target=place.get("name", ""),
                 deadline_text=terms.get("deadline_text") or "", who=thread.get("filled_by_name") or "başkası")


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
        effects = _close_due(world, work, now)
        _replenish(world, work, now)
        work["last_tick"] = now
        validate(work)
    except Exception:
        _LOG.exception("World threads could not move on.")
        world[KEY] = state
        return
    try:
        sync_from_quests(world, work)
        _apply_effects(world, effects)
        validate(work)
    except Exception:
        _LOG.exception("A closed world thread left something undone.")


def validate(state: Any) -> None:
    if not isinstance(state, dict) or state.get("version") != SCHEMA_VERSION:
        raise ValueError("World thread state is invalid.")
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
        if any(thread.get(name) is not None and not isinstance(thread.get(name), str) for name in _OPTIONAL_TEXTS):
            raise ValueError("World thread record is invalid.")
