"""What one person of a town knows and will say about it.

Read-only over saved campaign data: places, the public face of world threads, and
for a thread's owner its terms. Everything is decided by Python and is the same
every time for the same person: who knows what comes from a hash of the campaign
seed, the person and the item, so people differ and nobody changes their story.
Some people know little, some will not talk to a stranger at all.

The result goes into the speech prompt as plain lines the model voices; it decides
nothing. A truth label, a future outcome or another person's terms never enter it.
What the model then named is matched back to these listed items by id, so "oraya"
reaches a real place without any new phrase pattern.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import living_world
import local_places
import npc_statements
import world_threads

MAX_ITEMS = 5
MAX_BYTES = 600
GONE_WINDOW = 86400
CLOSED_PERCENT = 25  # people who will not discuss the town with a stranger
_LOG = logging.getLogger(__name__)


def log_failure() -> None:
    _LOG.exception("Town knowledge could not be read.")


def _percent(world: dict[str, Any], *parts: Any) -> int:
    seed = living_world._campaign_seed(world)
    digest = hashlib.sha256("\x00".join((seed, *map(str, parts))).encode("utf-8")).digest()
    return digest[0] * 100 // 256


def _settlement(world: dict[str, Any]) -> str | None:
    return local_places.settlement_of(world, world.get("location"))


def _coverage(npc: dict[str, Any]) -> int:
    coverage = world_threads.catalog().get("coverage") or {}
    role = npc_statements.fold(npc.get("role") or "")
    for word, percent in (coverage.get("roles") or {}).items():
        if word in role:
            return percent
    return coverage.get("default", 35)


def owned_threads(world: dict[str, Any], npc: dict[str, Any]) -> list[dict[str, Any]]:
    place_id = npc.get("place_role_of")
    return [t for t in world_threads.active(world) if place_id and t.get("place_id") == place_id]


def is_closed_mouthed(world: dict[str, Any], npc: dict[str, Any]) -> bool:
    """The same person always answers the same way; someone with work to give does talk."""
    return not owned_threads(world, npc) and _percent(world, npc.get("id"), "closed") < CLOSED_PERCENT


def _places(world, settlement_id, npc):
    seen = npc.get("location")
    share = world_threads.catalog().get("place_coverage", 80)
    for place_id, record in world.get("locations", {}).items():
        if (
            not isinstance(record, dict) or record.get("parent_location_id") != settlement_id
            or record.get("hidden") or place_id == seen or not isinstance(record.get("name"), str)
        ):
            continue
        spec = local_places.PLACE_KINDS.get(record.get("place_kind"))
        noun = spec["noun"] if spec else ("han" if record.get("scene_kind") == "tavern" else None)
        if noun and _percent(world, npc.get("id"), place_id) < share:
            yield {"kind": "place", "text": f"{record['name']} ({noun})", "location_id": place_id, "thread_id": None}


def public_knowledge(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """At most five short things this person knows, within 600 bytes. Writes nothing."""
    settlement_id = _settlement(world)
    state = world_threads.view(world)
    if not isinstance(npc, dict) or not settlement_id or state is None or is_closed_mouthed(world, npc):
        return []
    share = _coverage(npc)
    threads = []
    for thread in world_threads.active(world, settlement_id):
        own = thread["place_id"] == npc.get("place_role_of") or thread["place_id"] == npc.get("location")
        if own or _percent(world, npc.get("id"), thread["thread_id"]) < share:
            threads.append({"kind": "thread", "text": thread["public_line"], "location_id": thread["place_id"],
                            "thread_id": thread["thread_id"]})
    threads.sort(key=lambda item: _percent(world, npc.get("id"), "order", item["thread_id"]))
    gone = []
    now = world_threads._now(world)
    line = world_threads.catalog().get("gone_line")
    for thread in state["history"]:
        place = world.get("locations", {}).get(thread["place_id"])
        if (
            line and isinstance(place, dict) and thread["status"] == "filled_by_other"
            and thread["settlement_id"] == settlement_id and now - (thread.get("closed_at") or 0) < GONE_WINDOW
            and _percent(world, npc.get("id"), thread["thread_id"]) < share
        ):
            gone.append({"kind": "news", "text": line.replace("{place}", place["name"]),
                         "location_id": thread["place_id"], "thread_id": None})
    known, size = [], 0
    for item in (*threads, *gone, *_places(world, settlement_id, npc)):
        cost = len(item["text"].encode("utf-8"))
        if len(known) < MAX_ITEMS and size + cost <= MAX_BYTES:
            known.append(item)
            size += cost
    return known


def place_of_person(world: dict[str, Any], name: Any) -> dict[str, Any] | None:
    """Where a person the threads name can be found, by their reserved name."""
    wanted = npc_statements.fold(name)
    for thread in world_threads.active(world):
        for who, place_id in ((thread.get("owner_name"), thread.get("place_id")),
                              (thread.get("recipient_name"), thread.get("target_place_id"))):
            if who and wanted and npc_statements.fold(who) == wanted:
                place = world.get("locations", {}).get(place_id)
                return place if isinstance(place, dict) else None
    return None


def _name_of(world: dict[str, Any], place_id: Any) -> str:
    place = world.get("locations", {}).get(place_id)
    return place.get("name", "") if isinstance(place, dict) else ""


def speech_note(world: dict[str, Any], npc: Any) -> str:
    """Plain lines for this person's prompt; empty when the town is not in play here."""
    if not isinstance(npc, dict) or world_threads.view(world) is None or not _settlement(world):
        return ""
    if is_closed_mouthed(world, npc):
        return (
            " Kentte olan biteni yabancılarla konuşmak istemiyorsun: sorulursa kendi tavrınla geçiştir, "
            "kimseyi ve hiçbir yeri adıyla anma."
        )
    known = public_knowledge(world, npc)
    lines = []
    if known:
        listed = " / ".join(item["text"] for item in known)
        lines.append(
            f" Kentte duyduğun ve bildiğin şeyler: {listed}. Sana iş, olan biten ya da bir yer sorulursa "
            "bunlardan uygun olanı kendi sözlerinle aktar; yer ve kişi adlarını aynen kullan, kesin bilmediğini "
            "duyduğun kadarıyla söyle. Sorulmadıkça sayıp dökme."
        )
    else:
        lines.append(" Kentte iş veya olan bitene dair bir şey duymadın; sorulursa bilmediğini söyle.")
    lines.append(" Bunların dışında kişi, yer veya iş adı uydurma.")
    for thread in owned_threads(world, npc)[:1]:
        lines.append(
            f" Bu senin kendi meselen: {thread['owner_line']} Sorulursa bunu kendi ağzınla anlat; "
            "söz verme, anlaşma yapma, para verme."
        )
    return "".join(lines)


def fallback_line(world: dict[str, Any], npc: Any) -> str | None:
    """What this person says when no model reply could be used: a real lead, or nothing."""
    known = public_knowledge(world, npc)
    lead = next((item for item in known if item["kind"] == "thread"), None)
    if lead:
        return f"Duyduğuma göre {lead['text']}"
    place = next((item for item in known if item["kind"] == "place"), None)
    if place:
        return f"Bir şey duymadım ama {_name_of(world, place['location_id'])} tarafına bir sor."
    return None


def _spoken_places(world, settlement_id, words):
    """Saved places of this town named outright in a reply, first spoken first."""
    found = []
    for place_id, record in world.get("locations", {}).items():
        if isinstance(record, dict) and record.get("parent_location_id") == settlement_id:
            name = npc_statements.fold(record.get("name", ""))
            at = words.find(name) if name else -1
            if at >= 0:
                found.append((at, place_id))
    return [place_id for _, place_id in sorted(found)]


def _mentioned(world, known, words):
    """The listed items this reply speaks of: by person, or a noun only one item fits."""
    hits = []
    state = world_threads.view(world) or {"threads": []}
    threads = {t["thread_id"]: t for t in state["threads"]}
    for item in known:
        thread = threads.get(item["thread_id"])
        person = npc_statements.fold(thread.get("owner_name")) if thread else ""
        if person and any(word.startswith(person) for word in words.split()):
            hits.append(item)
    if hits:
        return hits
    by_kind: dict[Any, list[dict[str, Any]]] = {}
    for item in known:
        by_kind.setdefault(world.get("locations", {}).get(item["location_id"], {}).get("place_kind"), []).append(item)
    for kind, items in by_kind.items():
        spec = local_places.PLACE_KINDS.get(kind)
        if spec and len({i["location_id"] for i in items}) == 1 and any(
                word.startswith(stem) for stem in spec["stems"] for word in words.split()):
            hits += items[:1]
    return hits


def note_mention(world: dict[str, Any], npc: Any, shown_text: Any) -> None:
    """Tie what was just said to the real record it means, so the player can follow it."""
    if not isinstance(npc, dict) or not isinstance(shown_text, str):
        return
    try:
        if world_threads.view(world) is None:
            return
        words = npc_statements.fold(shown_text)
        known = public_knowledge(world, npc)
        spoken = _spoken_places(world, _settlement(world), words)
        hits = _mentioned(world, known, words)
        turn = int((world.get("flags") or {}).get("turn_index", 0) or 0)
        for item in known:  # only the thread this line is about, never another at the same place
            if item["thread_id"] and (item in hits or item["location_id"] in spoken):
                thread = next((t for t in world_threads.active(world) if t["thread_id"] == item["thread_id"]), None)
                if thread is not None:
                    world_threads.mark_heard(thread, turn)
        world_threads.note_heard_names(world, words)
        # A place said outright is what "oraya" means; a person only stands in for theirs.
        place_id = spoken[0] if spoken else (hits[0]["location_id"] if hits else None)
        if place_id:
            npc_statements.bind_said_place(world, npc, place_id, _name_of(world, place_id))
    except Exception:
        _LOG.exception("A town mention could not be tied to its record.")
