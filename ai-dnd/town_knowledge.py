"""What one person of a town knows and will say about it.

Read-only over saved campaign data: places, the public face of world threads, and
for a thread's owner its terms. Everything is decided by Python and is the same
every time for the same person: who knows what comes from a hash of the campaign
seed, the person and the item, so people differ and nobody changes their story.
Some people know little, some will not talk to a stranger at all.

The result goes into the speech prompt as plain lines the model voices; it decides
nothing. A truth label or another person's terms never enter it, and a future outcome
enters only as this owner's own plan, never as something that has happened.
What the model then named is matched back to these listed items by id, so "oraya"
reaches a real place without any new phrase pattern.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from typing import Any

import living_world
import local_places
import name_catalog
import npc_statements
import relationships
import world_threads

MAX_ITEMS = 5
MAX_BYTES = 600
GONE_WINDOW = 86400
CLOSED_PERCENT = 15  # people who will not discuss the town with a stranger
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
    return [t for t in world_threads.owned(world) if place_id and t.get("place_id") == place_id]


def is_closed_mouthed(world: dict[str, Any], npc: dict[str, Any]) -> bool:
    """The same person always answers the same way; someone with work to give does talk."""
    return (not owned_threads(world, npc) and not world_threads.recent_closed(world, npc)
            and _percent(world, npc.get("id"), "closed") < CLOSED_PERCENT)


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
    lines = world_threads.catalog().get("gone_lines") or {}
    for thread in state["history"]:
        place = world.get("locations", {}).get(thread["place_id"])
        line = lines.get(thread["status"])
        if (
            line and isinstance(place, dict)
            and thread["settlement_id"] == settlement_id and now - (thread.get("closed_at") or 0) < GONE_WINDOW
            and _percent(world, npc.get("id"), thread["thread_id"]) < share
        ):
            gone.append({"kind": "news", "text": line.replace("{place}", place["name"]).replace(
                "{who}", thread.get("filled_by_name") or "başkası"),
                         "location_id": thread["place_id"], "thread_id": thread["thread_id"]})
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
    for thread in world_threads.owned(world):
        for who, place_id in ((thread.get("owner_name"), thread.get("place_id")),
                              (thread.get("recipient_name"), thread.get("target_place_id"))):
            if who and wanted and npc_statements.fold(who) == wanted:
                place = world.get("locations", {}).get(place_id)
                return place if isinstance(place, dict) else None
    return None


def _name_of(world: dict[str, Any], place_id: Any) -> str:
    place = world.get("locations", {}).get(place_id)
    return place.get("name", "") if isinstance(place, dict) else ""


def _brush_off_place(world: dict[str, Any], npc: dict[str, Any]) -> str:
    """The one place this person sends people to, always the same; no details come with it."""
    threads = world_threads.active(world, _settlement(world))
    if not threads:
        return ""
    chosen = min(threads, key=lambda thread: _percent(world, npc.get("id"), "send", thread["thread_id"]))
    return _name_of(world, chosen["place_id"])


def _tone(world, npc):
    score = relationships.score(world, npc.get("id"))
    shared = world_threads.job_lines("shared") or {}
    return shared.get("cold", "") if score <= -1 else shared.get("warm", "") if score >= 1 else ""


def _offerable(world, npc):
    """The one job this person could put to the player now; none while another is running."""
    jobs = world_threads.jobs_of(world, npc)
    if any(thread["status"] in {"offered", "accepted"} for thread in jobs):
        return None
    return next((t for t in jobs if t["status"] in world_threads.PUBLIC), None)


def _lines_for(world, thread, npc, decision):
    shared = world_threads.job_lines("shared") or {}
    status = thread["status"]
    if decision == "busy":
        return [shared.get("busy", "")]
    if decision == "withdraw_unclear":
        return [shared.get("withdraw_unclear", "")]
    if decision == "come_at_night":
        return [shared.get("come_at_night", "")]
    if decision == "questioning_terms":
        return [world_threads._fill(shared.get("questioning_terms", ""), pay_text=world_threads.pay_text(thread),
                                    timing_text=world_threads.timing_text(thread))]
    if status == "expired" and thread.get("accepted_at") is not None:
        return [world_threads.status_line(world, thread, "called_off")]
    if status in {"accepted", "declined", "done", "failed", "abandoned"} or (
            status == "expired" and thread.get("declined_turn") is None):
        line = world_threads.status_line(world, thread, status)
        extra = []
        if status == "accepted" and thread.get("type") == "errand":
            extra.append(_parcel_line(world, thread))
        if status == "declined" and shared.get("repeat_decline") != line:
            extra.append(shared.get("repeat_decline", ""))
        return [line, *extra]
    if status == "filled_by_other":
        return [world_threads.status_line(world, thread, "filled")]
    if status == "expired" and thread.get("declined_turn") is not None:
        return [world_threads.status_line(world, thread, "declined_unfilled")]
    if status == "offered":
        return [shared.get("unclear", "")]
    return []


def _parcel_line(world, thread):
    noun = thread.get("item_noun") or "paket"
    from adventure import dialogue_jobs
    held = dialogue_jobs.holds_parcel(world, thread)
    return f"{noun.capitalize()} şu an {'oyuncunun elinde' if held else 'sende, henüz vermedin'}."


def _job_note(world, npc, decision):
    """Where this person's work stands, for them to say. Python decided all of it already."""
    shared = world_threads.job_lines("shared") or {}
    awaited = world_threads.deliveries_to(world, npc)
    if awaited:
        noun = awaited[0].get("item_noun") or "paket"
        return " " + world_threads._fill(shared.get("awaiting", ""), item=noun, owner=awaited[0].get("owner_name") or "")
    late = world_threads.late_parcels(world, npc)
    for thread in late:
        if thread.get("recipient_npc_id") == npc.get("id"):
            return " " + world_threads._fill(shared.get("too_late", ""), item=thread.get("item_noun") or "paket",
                                             owner=thread.get("owner_name") or "")
    received = world_threads.delivered_to(world, npc)
    if received:
        noun = received[-1].get("item_noun") or "paket"
        return (f" Karşındaki kişi {received[-1].get('owner_name') or 'birinin'} gönderdiği {noun} sana teslim etti; "
                "bunu biliyorsun, inkâr etme.")
    if not isinstance(npc, dict) or not npc.get("place_role_of"):
        return shared.get("no_job", "")
    decided = world_threads.by_id(world, (decision or {}).get("thread_id"))
    jobs = world_threads.jobs_of(world, npc)
    if decided is not None and decided["status"] in world_threads.PUBLIC:
        decided = None  # talked about, not yet offered: the note below covers it
    chosen = decided or next((t for t in jobs if t["status"] in {"accepted", "offered", "declined"}), None)
    tone = _tone(world, npc)
    lines = []
    if chosen is not None:
        lines = _lines_for(world, chosen, npc, (decision or {}).get("decision"))
    elif (past := world_threads.recent_closed(world, npc)):
        lines = _lines_for(world, past[0], npc, None)
    available = _offerable(world, npc)
    if available is not None and chosen is None:
        mood = world_threads.owner_mood(world, available, npc)
        if mood == "no":
            lines.append(shared.get("unwilling", ""))
        elif mood == "wary":
            lines.append(shared.get("wary_stranger", ""))
        else:
            lines.append(
                f"Bu senin kendi işin: {available['owner_line']} Sorulursa ücreti ve süreyi aynen söyle; "
                "kabul edip etmemek onun kararı. Peşin para verme."
            )
    if late:
        lines.append(world_threads._fill(shared.get("parcel_out", ""), item=late[0].get("item_noun") or "paket"))
    for thread in owned_threads(world, npc):
        if thread.get("type") == "trouble":
            lines.append(f"Bu senin kendi meselen: {thread['owner_line']} {shared.get('trouble', '')}")
            break
    if not lines:
        lines.append(shared.get("no_job", ""))
    return " " + " ".join(line for line in lines if line) + tone


@lru_cache(maxsize=1)
def _role_profiles() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        mapping = json.loads((name_catalog.CATALOG_DIR / "mapping.json").read_text(encoding="utf-8"))
        roles = json.loads((name_catalog.CATALOG_DIR / "npc_roles.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _LOG.warning("The role profiles could not be read.")
        return {}, {}
    return mapping["role_profiles"]["roles"], {item["id"]: item for item in roles["items"]}


def role_note(world: dict[str, Any], npc: dict[str, Any]) -> str:
    """What this person's work lets them know and what it does not. Bounds speech, adds no fact."""
    table, profiles = _role_profiles()
    chosen = table.get(npc_statements.fold(npc.get("role") or ""))
    if not chosen:
        return ""
    profile = profiles[chosen[_percent(world, npc.get("id"), "role") % len(chosen)]]
    return (f" İşin gereği bildiğin konular: {'; '.join(profile['known_topics'])}."
            f" Bilmediğin konular: {'; '.join(profile['unknown_topics'][:2])}."
            " Bunlar sorulursa bilmediğini söyle; ayrıntı uydurma.")


def speech_note(world: dict[str, Any], npc: Any, decision: dict[str, Any] | None = None) -> str:
    """Plain lines for this person's prompt; empty when the town is not in play here."""
    if not isinstance(npc, dict) or world_threads.view(world) is None or not _settlement(world):
        return ""
    job = _job_note(world, npc, decision)
    if job and not job.startswith(" "):
        job = " " + job
    if is_closed_mouthed(world, npc):
        # Unhelpful is a character; a whole street with nothing to say is the dead end that stopped play.
        place = _brush_off_place(world, npc)
        return (
            " Kentte olan biteni yabancılarla konuşmak istemiyorsun: sorulursa kendi tavrınla kısa kes."
            + (f" En fazla, başından savmak için {place} tarafına sormasını söyleyebilirsin; ne olduğunu anlatma."
               if place else "")
            + " Başka kimseyi ve hiçbir başka yeri adıyla anma."
            + job
            + role_note(world, npc)
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
    lines.append(job)
    lines.append(role_note(world, npc))
    return "".join(lines)


def asks_about_work(player_text: Any, thread: dict[str, Any]) -> bool:
    """'Bana iş ver', 'adam arıyormuşsun': the player brought up work, however they put it."""
    import local_dialogue
    if local_dialogue.personal_question_kind(player_text) == "local_work":
        return True
    table = world_threads.answer_table()
    words = world_threads._folded(player_text).split()
    return bool(set(words) & table.get("work_terms", frozenset()))


def _shows_terms(thread, text):
    terms = thread.get("terms") or {}
    return world_threads.figure_before(text, terms.get("pay"), "bakir") and (
        not terms.get("work_days") or world_threads.figure_before(text, terms.get("work_days"), ("gun", "gece")))


def terms_to_add(world: dict[str, Any], npc: Any, player_text: Any, reply: Any) -> str | None:
    """The owner's terms, when they were asked for the work and the reply left the figures out."""
    thread = _offerable(world, npc) if isinstance(npc, dict) else None
    if (thread is None or not isinstance(reply, str) or _shows_terms(thread, reply)
            or world_threads.owner_mood(world, thread, npc) != "yes" or not asks_about_work(player_text, thread)):
        return None
    return thread["owner_line"]


def _open_offer(world, npc, shown_text, turn, job_talk, offer_talk):
    """An offer exists once its real terms were on screen: Python's own line, or the figures on a turn about work."""
    line = shown_text.strip()[:400]
    for thread in world_threads.jobs_of(world, npc):
        if thread["status"] == "accepted" and job_talk:
            thread["job_line"] = line
        elif thread["status"] in {"offered", "declined"} and (
                offer_talk or _shows_terms(thread, shown_text) or world_threads.stays_on_the_offer(shown_text, thread)):
            thread.update(offer_line=line, offer_line_turn=turn)
    thread = _offerable(world, npc)
    if thread is None or not (thread["owner_line"] in shown_text or (job_talk and _shows_terms(thread, shown_text))):
        return
    if world_threads.owner_mood(world, thread, npc, this_exchange=1) == "yes":
        world_threads.mark_offered(world, thread, npc, shown_text, turn)


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


def _tells_outcome(item, thread, words):
    """The reply says how it ended: the news itself, who took it, or its own words. A place named alone says nothing."""
    listed = (world_threads.catalog().get("gone_words") or {}).get(thread["status"]) or ()
    who = npc_statements.fold(thread.get("filled_by_name"))
    return (npc_statements.fold(item["text"]) in words or bool(who and who in words)
            or bool({npc_statements.fold(word) for word in listed} & set(words.split())))


def note_mention(world: dict[str, Any], npc: Any, shown_text: Any, *, job_talk: bool = False,
                 offer_talk: bool = False) -> None:
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
                thread = world_threads.by_id(world, item["thread_id"])
                if thread is None:
                    continue
                if item["kind"] == "news":
                    if _tells_outcome(item, thread, words):
                        world_threads.learn_outcome(world, thread)
                else:
                    world_threads.mark_heard(thread, turn)
        _open_offer(world, npc, shown_text, turn, job_talk, offer_talk)
        if job_talk:
            for thread in world_threads.recent_closed(world, npc):
                world_threads.learn_outcome(world, thread)
        world_threads.note_heard_names(world, words)
        # A place said outright is what "oraya" means; a person only stands in for theirs.
        place_id = spoken[0] if spoken else (hits[0]["location_id"] if hits else None)
        if place_id:
            npc_statements.bind_said_place(world, npc, place_id, _name_of(world, place_id))
    except Exception:
        _LOG.exception("A town mention could not be tied to its record.")
