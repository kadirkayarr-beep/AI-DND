"""What a town's troubles came to: a small ledger of things that happened without the player.

These are not deeds. `bold_acts.deeds` is what the player did and what guards answer
for; a shop closing has nothing to do with that, so it lives here, inside the world
thread state, and is kept and rolled back with it. Python writes every line and the
model only voices it.
"""

from __future__ import annotations

from typing import Any

import local_places
import talk_mode
import world_threads

KEY = "happenings"
MAX_HAPPENINGS = 16
MAX_LINE_BYTES = 90
KINDS = ("visit", "closed", "lost", "averted", "delivered")
OUTCOMES = ("visit", "closed", "lost")
RECENT_SECONDS = 2 * world_threads.DAY  # how long it stays what people talk about
CLOSED_SECONDS = 2 * world_threads.DAY
# What each ending starts, first that can be opened: (kind of thread, at the same place).
FOLLOW_ON = {
    "visit": (("trouble", True), ("trouble", False)),
    "lost": (("errand", False), ("trouble", False)),
    "closed": (("errand", False), ("trouble", False)),
    "delivered": (("trouble", False), ("errand", False)),
}
SECOND_CHANCE_SECONDS = 6 * world_threads.HOUR
LINKS = "links"  # words said aloud that come due: kept beside the threads, closed by the same clock
MAX_LINKS = 4
LINK_HOURS = (6, 20)
CALLER = "caller"  # someone comes to the player
GUARDED = "guarded"  # someone the player threatened gets ready
LINK_KINDS = (CALLER, GUARDED)
LINK_ROW = {CALLER: "visit", GUARDED: "closed"}
CALLER_STAYS_SECONDS = 1800  # said their piece and on the way back; nobody waits about a room for hours
CALLER_TALK_TURNS = 2  # they will take a reply or two, then they go
LET_GO = ("abandoned", "expired", "failed")
HAPPENED = "happened"  # in the clock's list of effects: the ledger gained a row for this thread


def ledger(state: dict[str, Any]) -> list[dict[str, Any]]:
    """An old save simply gains the list."""
    return state.setdefault(KEY, [])


def fits(line: str) -> bool:
    return len(line.encode("utf-8")) <= MAX_LINE_BYTES


def write(state: dict[str, Any], thread: dict[str, Any], kind: str, at: int, line: str, *,
          known: bool = False, next_thread_id: str | None = None) -> dict[str, Any]:
    row = {"thread_id": thread["thread_id"], "kind": kind, "at": at, "place_id": thread["place_id"],
           "line": line, "known_to_player": known, "next_thread_id": next_thread_id}
    rows = ledger(state)
    rows.append(row)
    del rows[:-MAX_HAPPENINGS]
    return row


def validate(rows: Any) -> None:
    """Absent is fine: that is a save from before the ledger."""
    if rows is None:
        return
    if not isinstance(rows, list) or len(rows) > MAX_HAPPENINGS:
        raise ValueError("World thread state is invalid.")
    for row in rows:
        if (
            not isinstance(row, dict) or row.get("kind") not in KINDS
            or not isinstance(row.get("thread_id"), str) or not isinstance(row.get("place_id"), str)
            or type(row.get("at")) is not int or type(row.get("known_to_player")) is not bool
            or not isinstance(row.get("line"), str) or not fits(row["line"])
            or not (row.get("next_thread_id") is None or isinstance(row.get("next_thread_id"), str))
        ):
            raise ValueError("World thread record is invalid.")


def _outcome_of(seed: str, thread: dict[str, Any]) -> str:
    return OUTCOMES[world_threads._rank(seed, thread["thread_id"], "fired") % len(OUTCOMES)]


def _line_for(world: dict[str, Any], seed: str, thread: dict[str, Any], lines: Any) -> str:
    """The first line that fits once the place's name is in; a long name gets a short one, never a cut."""
    place = world.get("locations", {}).get(thread["place_id"]) or {}
    lines = list(lines or ())
    start = world_threads._rank(seed, thread["thread_id"], "line") % max(len(lines), 1)
    for line in (*lines[start:], *lines[:start]):
        filled = world_threads.sentence(world_threads._fill(line, place=place.get("name", "")))
        if fits(filled):
            return filled
    return world_threads.job_lines("trouble", "fired_short") or ""


def links(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Reading writes nothing: an old save gains the list with its first link."""
    return state.get(LINKS) or []


def _validate_links(rows: Any) -> None:
    if rows is None:
        return
    if not isinstance(rows, list) or len(rows) > MAX_LINKS:
        raise ValueError("World thread state is invalid.")
    for row in rows:
        if (
            not isinstance(row, dict) or row.get("kind") not in LINK_KINDS or row.get("type") != "trouble"
            or not isinstance(row.get("thread_id"), str) or not isinstance(row.get("place_id"), str)
            or type(row.get("opened_at")) is not int
            or not (row.get("fires_at") is None or type(row["fires_at"]) is int)
        ):
            raise ValueError("World thread record is invalid.")


def _make_room(state: dict[str, Any]) -> bool:
    """The oldest link already played out goes; a town full of live ones takes no more."""
    rows = links(state)
    if len(rows) < MAX_LINKS:
        return True
    spent = next((row for row in rows if row.get("fires_at") is None and row.get("caller_id")), None) or next(
        (row for row in rows if row.get("fires_at") is None and row["kind"] == GUARDED), None)
    if spent is None:
        return False
    rows.remove(spent)
    return True


def tie(world: dict[str, Any], kind: str, tone: str, owner: Any, place_id: Any, *, about: Any = None) -> dict[str, Any] | None:
    """A moment for something said. The hours are the seed's: nobody's words can set them."""
    state = world_threads.view(world)
    settlement = local_places.settlement_of(world, place_id)
    if state is None or not settlement or place_id not in world.get("locations", {}):
        return None
    owner_id = owner.get("id") if isinstance(owner, dict) else None
    if any(row["kind"] == kind and row.get("owner_npc_id") == owner_id and row.get("about_thread_id") == about
           and (row.get("fires_at") is not None or not row.get("caller_id")) for row in links(state)):
        return None
    if not _make_room(state):
        return None
    number = state.get("next_link", 1)
    state["next_link"] = number + 1
    now = world_threads._now(world)
    seed = world_threads.living_world._campaign_seed(world)
    thread_id = f"link_{number:03d}"
    hours = world_threads._between(seed, LINK_HOURS, thread_id, kind, "hours")
    link = {"thread_id": thread_id, "type": "trouble", "kind": kind, "tone": tone, "status": "coming",
            "place_id": place_id, "settlement_id": settlement, "owner_npc_id": owner_id,
            "about_thread_id": about, "opened_at": now, "fires_at": now + hours * world_threads.HOUR}
    state.setdefault(LINKS, []).append(link)
    return link


def who_can_be_named(world: dict[str, Any], npc: Any) -> dict[str, list[dict[str, Any]]]:
    """What a threat from this person can be about, and who it can come from: real records only."""
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    own = [t for t in world_threads.owned(world) if place_id and t.get("place_id") == place_id]
    carried = [t for t in world_threads.owned(world) if t.get("status") == "accepted" and t not in own]
    jobs = [{"id": t["thread_id"], "name": t.get("item_noun") or t["public_line"][:48]}
            for t in (*own, *carried, *world_threads.recent_closed(world, npc))]
    here = [other for other in world.get("npcs", []) if isinstance(other, dict) and isinstance(npc, dict)
            and other.get("id") and other.get("combat_status") != "dead" and other.get("location") == npc.get("location")]
    people = [{"id": other["id"], "name": world_threads.living_world.public_npc_name(other)} for other in here]
    return {"jobs": jobs[:6], "people": people[:6]}


PLAYER_THREATENED = "warned"
OWN_THREAT = "warn"


def threat_said(world: dict[str, Any], npc: dict[str, Any], said: Any) -> dict[str, Any] | None:
    """The reply's threat field: what the speaker named from their list, or that the player threatened them. Nothing else counts."""
    said = said.split()[0] if isinstance(said, str) and said.strip() else None  # 'npc_001 (Bir kâhya)': the id is what counts
    if said == PLAYER_THREATENED:
        return threatened(world, npc)
    listed = who_can_be_named(world, npc)
    about = world_threads.by_id(world, said) if said in [row["id"] for row in listed["jobs"]] else None
    sender = world_threads._npc(world, said) if said in [row["id"] for row in listed["people"]] else None
    if about is None and sender is None and said != OWN_THREAT:
        return None
    owner = sender or (world_threads.owner_of(world, about) if about else None) or npc
    place = (about or {}).get("place_id") or owner.get("place_role_of") or owner.get("location")
    return tie(world, CALLER, "warned", owner, place, about=about["thread_id"] if about else None)


def threatened(world: dict[str, Any], npc: dict[str, Any]) -> dict[str, Any] | None:
    """The player threatened this person: they think less of the player now, and get ready by the clock."""
    import relationships
    link = tie(world, GUARDED, "guarded", npc, npc.get("place_role_of") or npc.get("location"))
    if link is not None:
        relationships.note(world, npc["id"], -1, f"threat:{link['thread_id']}"[:160])
    return link


def _fire_links(world: dict[str, Any], state: dict[str, Any], now: int, seed: str) -> list[tuple[str, str]]:
    effects = []
    due = sorted((row for row in links(state) if type(row.get("fires_at")) is int and row["fires_at"] <= now),
                 key=lambda row: row["fires_at"])
    for link in due:
        at = link.pop("fires_at")
        link["status"] = "due"
        kind = LINK_ROW[link["kind"]]
        lines = world_threads.job_lines("link", "lines", link["tone"])
        known = link["kind"] == GUARDED and world.get("location") == link["place_id"]
        row = write(state, link, kind, at, _line_for(world, seed, link, lines), known=known)
        row["next_thread_id"] = _follow_on(world, state, seed, link, kind, now)
        effects.append((link["thread_id"], HAPPENED))
    return effects


def fire_due(world: dict[str, Any], state: dict[str, Any], now: int) -> list[tuple[str, str]]:
    """Every closed trouble whose moment has come. Called with the state in hand, inside the clock's step."""
    seed = world_threads.living_world._campaign_seed(world)
    due = sorted((t for t in state["history"] if (world_threads.fires_at(t) or now + 1) <= now),
                 key=world_threads.fires_at)
    effects = []
    for thread in due:
        at = thread.pop("fires_at")
        kind = _outcome_of(seed, thread)
        line = _line_for(world, seed, thread, world_threads.job_lines("trouble", "fired_lines", kind))
        row = write(state, thread, kind, at, line, known=world.get("location") == thread["place_id"])
        row["next_thread_id"] = _follow_on(world, state, seed, thread, kind, now)
        effects.append((thread["thread_id"], HAPPENED))
    return effects + _fire_links(world, state, now, seed)


def barred(state: dict[str, Any], place_id: str, kind: str, now: int) -> bool:
    """A place that shut its doors takes nobody on for a while."""
    return kind == "hiring" and any(row["kind"] == "closed" and row["place_id"] == place_id and 0 <= now - row["at"] < CLOSED_SECONDS
                                    for row in state.get(KEY) or [])


def _follow_on(world: dict[str, Any], state: dict[str, Any], seed: str, thread: dict[str, Any], kind: str, now: int) -> str | None:
    """What this ending starts: one rule, read from the ending, and it may find nothing to start."""
    settlement = thread["settlement_id"]
    if len(state["threads"]) >= world_threads.MAX_ACTIVE or settlement not in state["seeded"]:
        return None
    record = world.get("locations", {}).get(thread["place_id"])
    talked_of = {t.get("template_id") for t in (*state["threads"], *state["history"])}
    choices = sorted((t for t in world_threads.catalog()["templates"] if t["id"] != thread.get("template_id")),
                     key=lambda t: (t["id"] in talked_of, world_threads._rank(seed, thread["thread_id"], "next", t["id"])))
    for wanted, same_place in FOLLOW_ON[kind]:
        for template in choices:
            if template["type"] != wanted or (same_place and not (
                    isinstance(record, dict) and record.get("place_kind") in template["place_kinds"])):
                continue
            where = {"place": record} if same_place else {"avoid": {thread["place_id"]}}
            opened = world_threads._open_thread(world, state, template, settlement, create=False, now=now, tied=True, **where)
            if opened:
                return opened["thread_id"]
    return None


def seal_broken(world: dict[str, Any], thread: dict[str, Any]) -> None:
    """Whoever sealed it hears of it, and sends someone: the clock starts with the seal, no threat needed."""
    tie(world, CALLER, "opened", world_threads.owner_of(world, thread), thread["place_id"], about=thread["thread_id"])


def _letter_closed(world: dict[str, Any], thread: dict[str, Any], status: str) -> None:
    """A delivered errand does not end at the door: its owner sends thanks. A sealed letter kept back is sent for;
    an opened seal sends no thanks (that word goes out when the seal breaks)."""
    from adventure import dialogue_jobs
    sealed = dialogue_jobs.sealed(thread)
    if sealed and thread.get("seal_broken"):
        return
    tone = ("delivered" if status == "done"
            else "kept" if sealed and status in LET_GO and dialogue_jobs.holds_parcel(world, thread) else None)
    if tone:
        tie(world, CALLER, tone, world_threads.owner_of(world, thread), thread["place_id"], about=thread["thread_id"])


def on_close(world: dict[str, Any], thread: dict[str, Any], status: str) -> None:
    """A trouble someone took on: seen through it is over; dropped, it comes back in a few hours."""
    state = world_threads.view(world)
    if state is not None and thread.get("type") == "errand":
        _letter_closed(world, thread, status)
        if status == "done":  # handed over: the player knows, and the town may take it further by the one rule
            seed = world_threads.living_world._campaign_seed(world)
            row = write(state, thread, "delivered", thread.get("closed_at") or world_threads._now(world),
                        _line_for(world, seed, thread, world_threads.job_lines("errand", "delivered_lines")), known=True)
            row["next_thread_id"] = _follow_on(world, state, seed, thread, "delivered", world_threads._now(world))
    if state is None or thread.get("type") != "trouble":
        return
    closed = thread.get("closed_at") or world_threads._now(world)
    if status == "done":
        seed = world_threads.living_world._campaign_seed(world)
        write(state, thread, "averted", closed, _line_for(world, seed, thread, world_threads.job_lines("trouble", "averted_lines")),
              known=True)
    elif status in LET_GO and thread.get("accepted_at") is not None:
        thread["fires_at"] = closed + SECOND_CHANCE_SECONDS


def put_forward(world: dict[str, Any], thread: dict[str, Any], npc: dict[str, Any], shown: str) -> None:
    """A public trouble someone just stepped into: the offer is made by the taking."""
    turn = int((world.get("flags") or {}).get("turn_index", 0) or 0)
    if thread.get("status") in world_threads.PUBLIC:
        world_threads.mark_offered(world, thread, npc, shown, turn)


def _trouble_at_end_of(world: dict[str, Any], thread: dict[str, Any]) -> dict[str, Any] | None:
    return next((t for t in world_threads.active(world) if t["type"] == "trouble"
                 and t["place_id"] == thread.get("target_place_id")), None)


def letter_matter(world: dict[str, Any], thread: dict[str, Any]) -> str | None:
    """What is really going on where this letter is bound: the words of the trouble there, if they fit a line."""
    trouble = _trouble_at_end_of(world, thread)
    if trouble is None:
        return None
    return next((line for line in (trouble["owner_line"], trouble["public_line"]) if fits(line)), None)


def letter_read(world: dict[str, Any], thread: dict[str, Any], words: str, turn: int) -> None:
    """The words stay what they were, and whoever read them now knows of the trouble they tell."""
    trouble = _trouble_at_end_of(world, thread)
    if trouble is not None and any(line in words for line in (trouble["owner_line"], trouble["public_line"])):
        world_threads.mark_heard(trouble, turn)
    thread["letter_line"] = words


def _row_of(state: dict[str, Any], thread: dict[str, Any]) -> dict[str, Any] | None:
    return next((row for row in reversed(state.get(KEY) or []) if row["thread_id"] == thread.get("thread_id")), None)


def line_of(state: dict[str, Any], thread: dict[str, Any]) -> str | None:
    row = _row_of(state, thread)
    return row["line"] if row else None


def show(world: dict[str, Any], thread: dict[str, Any]) -> None:
    """The player was standing there: it is simply what they see next."""
    import world_reactions
    state = world_threads.view(world)
    row = _row_of(state, thread) if state else None
    if row and row["known_to_player"] and world.get("location") == row["place_id"]:
        world_reactions._wait_line(world, row["place_id"], row["line"])


def unseen(world: dict[str, Any], line: Any) -> None:
    """The player had walked off before this line reached the screen: it waits for their return."""
    state = world_threads.view(world)
    for row in (state or {}).get(KEY) or []:
        if row["line"] == line:
            row["known_to_player"] = False


def learned(world: dict[str, Any], thread: dict[str, Any]) -> None:
    """Someone has just said this very line to the player."""
    state = world_threads.view(world)
    row = _row_of(state, thread) if state else None
    if row:
        row["known_to_player"] = True


def first_sight(world: dict[str, Any], thread: dict[str, Any]) -> str | None:
    """Its line, the once, for a screen already saying something else about this thread."""
    state = world_threads.view(world)
    row = _row_of(state, thread) if state else None
    if row is None or row["known_to_player"]:
        return None
    row["known_to_player"] = True
    return row["line"]


def arrival_line(world: dict[str, Any], place_id: Any) -> str | None:
    """Coming back: what happened here while you were away, once."""
    state = world_threads.view(world)
    for row in reversed((state or {}).get(KEY) or []):
        if row["place_id"] == place_id and not row["known_to_player"]:
            thread = world_threads.by_id(world, row["thread_id"])
            row["known_to_player"] = True
            if thread is not None:
                world_threads.learn_outcome(world, thread)
            return row["line"]
    return None


def _spoken_time(world: dict[str, Any], moment: int) -> str:
    """How far off, as a person says it. A figure is the one thing a small model will change."""
    import campaign_time
    hour = (campaign_time.public_time(world) or {}).get("hour", 12)
    ahead = hour + (moment - world_threads._now(world)) / world_threads.HOUR
    name = "when_today" if ahead < 20 else "when_tonight" if ahead < 30 else "when_tomorrow" if ahead < 48 else "when_later"
    return (world_threads.job_lines("text") or {}).get(name, "")


def own_words(thread: dict[str, Any]) -> str:
    """The trouble as its owner says it: their first sentence, not what the street says of them."""
    return thread["owner_line"].split(". ")[0].rstrip(" .")


def waiting_note(world: dict[str, Any], npc: Any) -> str:
    """This person's own trouble still on the clock: one sentence, in words."""
    place_id = npc.get("place_role_of") if isinstance(npc, dict) else None
    coming = [t for t in world_threads.owned(world) if place_id and t["place_id"] == place_id
              and world_threads.fires_at(t) is not None]
    if not coming:
        return ""
    thread = min(coming, key=world_threads.fires_at)
    line = world_threads.job_lines("shared", "waiting") or ""
    return " " + world_threads._fill(line, what=own_words(thread), when=_spoken_time(world, thread["fires_at"]))


def link_note(world: dict[str, Any], npc: Any) -> str:
    """What this person said or heard, while it is still on the clock, and who they are if they came about it."""
    state = world_threads.view(world)
    if state is None or not isinstance(npc, dict):
        return ""
    lines = world_threads.job_lines("link", "notes") or {}
    notes = []
    for link in links(state):
        if link.get("caller_id") == npc.get("id"):
            notes.append(world_threads._fill(lines.get(f"caller_{link['tone']}", ""), owner=_link_owner(world, link),
                                             what=_link_matter(world, link, spoken=True)))
            if npc.get("message"):
                notes.append(world_threads._fill(lines.get("caller_message", ""), message=npc["message"]))
            room = _summoning_room(world, link)
            if room is not None:
                notes.append(world_threads._fill(lines.get("summons", ""), owner=_link_owner(world, link),
                                                 place=room.get("name", "")))
        elif link.get("owner_npc_id") == npc.get("id") and link.get("fires_at") is not None:
            notes.append(world_threads._fill(lines.get(f"coming_{link['tone']}", ""), when=_spoken_time(world, link["fires_at"]),
                                             what=_link_matter(world, link)))
        elif _speaks_for(world, link, npc) and link["kind"] == CALLER:
            letter = (world_threads.by_id(world, link.get("about_thread_id")) or {}).get("letter_line")
            notes.append(world_threads._fill(lines.get("sent", ""), what=_link_matter(world, link),
                                             letter=world_threads._fill(lines.get("sent_letter", ""), words=letter) if letter else ""))
    return "".join(f" {note}" for note in notes if note)


def _speaks_for(world: dict[str, Any], link: dict[str, Any], npc: dict[str, Any]) -> bool:
    room = local_places.inner_room_of(world, link["place_id"])
    return link.get("owner_npc_id") == npc.get("id") or bool(room and npc.get("place_role_of") == room["id"])


def _of_the_house(world: dict[str, Any], link: dict[str, Any]) -> bool:
    """Whoever sent the caller speaks for the house it came from: its keeper, its master, or nobody named."""
    npc = world_threads._npc(world, link.get("owner_npc_id"))
    room = local_places.inner_room_of(world, link["place_id"])
    return npc is None or npc.get("place_role_of") in {link["place_id"], (room or {}).get("id")}


def _summoning_room(world: dict[str, Any], link: dict[str, Any]) -> dict[str, Any] | None:
    """The room behind the house's door the player is sent to; none when already in it or when the house sent nobody."""
    room = local_places.inner_room_of(world, link["place_id"])
    if room is None or world.get("location") == room["id"] or not _of_the_house(world, link):
        return None
    return room


def _link_owner(world: dict[str, Any], link: dict[str, Any]) -> str:
    import vouching
    title = vouching.head_title(world, link["place_id"]) if _of_the_house(world, link) else None
    if title:
        return title
    npc = world_threads._npc(world, link.get("owner_npc_id"))
    return world_threads._mid_sentence(world_threads.living_world.public_npc_name(npc)) if npc else (
        world_threads.job_lines("link", "someone") or "")


def _link_matter(world: dict[str, Any], link: dict[str, Any], *, spoken: bool = False) -> str:
    """What the link is about. Said aloud, a job's posting is no matter: the thing itself, or what was said."""
    about = world_threads.by_id(world, link.get("about_thread_id")) or {}
    posting = None if spoken else about.get("public_line")
    return (about.get("item_noun") or posting or world_threads.job_lines("link", "no_matter") or "").rstrip(" .")


def _settle_up(world: dict[str, Any], link: dict[str, Any]) -> None:
    """What the visit says about where the player stands with the one who sent it."""
    import relationships
    change = {"opened": -1, "kept": -1, "delivered": 1}.get(link["tone"])
    if change and link.get("owner_npc_id"):
        relationships.note(world, link["owner_npc_id"], change, f"sent:{link['thread_id']}:{link['tone']}"[:160])


def about_of(world: dict[str, Any], npc: Any) -> Any:
    """The thread this visitor came about, if they came about one."""
    link = world_threads.by_id(world, npc.get("caller_of")) if isinstance(npc, dict) and npc.get("caller_of") else None
    return (link or {}).get("about_thread_id")


def _callers_here(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [npc for npc in world.get("npcs", []) if isinstance(npc, dict) and npc.get("caller_of")
            and npc.get("location") == world.get("location") and npc.get("combat_status") != "dead"]


def _why_sent(world: dict[str, Any], link: dict[str, Any], words: dict[str, Any]) -> str:
    """What the ledger says the player did to the one who sent them; failing that, the matter named; failing that, the words."""
    why = words.get("why") or {}
    done = [deed for deed in world.get("flags", {}).get("deeds", [])
            if isinstance(deed, dict) and deed.get("victim_id") == link.get("owner_npc_id")]
    kind = done[-1].get("kind") if done else None
    if kind == "assault":
        return why.get("assault", "")
    if kind in {"theft", "theft_unseen"}:
        return why.get("theft", "")
    about = world_threads.by_id(world, link.get("about_thread_id")) or {}
    if about.get("item_noun"):  # a job's posting is no matter to hold against anyone: then it is what was said
        return world_threads._fill(why.get("about", ""), what=_link_matter(world, link, spoken=True))
    return why.get("said", "")


def _nth(link: dict[str, Any], lines: Any, seed: str) -> str:
    """Links are numbered, so one stock line never follows itself while the pool has another."""
    number = int(str(link["thread_id"]).rsplit("_", 1)[-1])
    return lines[(world_threads._rank(seed, "caller", "line") + number) % len(lines)] if lines else ""


def _message(world: dict[str, Any], link: dict[str, Any], words: dict[str, Any]) -> str:
    """What they were sent to say, made of the ledger entry that sent them."""
    seed = world_threads.living_world._campaign_seed(world)
    line = _nth(link, (words.get("messages") or {}).get(link["tone"]), seed)
    text = world_threads._fill(line, why=_why_sent(world, link, words), what=_link_matter(world, link, spoken=True))
    room = _summoning_room(world, link)
    if room is not None:
        text = f"{text} {world_threads._fill(words.get('summons', ''), place=room.get('name', ''))}"
    return text.strip()


def _caller_line(world: dict[str, Any], link: dict[str, Any], words: dict[str, Any]) -> str:
    return _nth(link, words.get(link["tone"]), world_threads.living_world._campaign_seed(world))


def callers_leave(session: Any, now: int) -> list[str]:
    """A messenger says what they came to say and goes back where they came from."""
    world = session.world_state
    flags = world.setdefault("flags", {})
    turn = int(flags.get("turn_index", 0) or 0)
    lines = []
    import equipment_economy
    for npc in _callers_here(world):
        # One knocked out or at 0 HP stays where they fell (the shared liveness rule).
        if npc.get("hostile") or "came_from" not in npc or not equipment_economy.npc_can_act(npc) or (
                turn < npc.get("leaves_turn", turn) and now < npc.get("back_at", now)):
            continue
        npc["location"] = npc.pop("came_from")
        npc.pop("back_at", None)
        if flags.get("active_npc_id") == npc.get("id"):
            talk_mode.close(world, "target_gone")
        words = world_threads.job_lines("link", "caller") or {}
        leaving = words.get("leaves") or ()
        who = world_threads.living_world.turkish_initial_upper(world_threads.living_world.public_npc_name(npc))
        if leaving:
            seed = world_threads.living_world._campaign_seed(world)
            lines.append(world_threads._fill(leaving[world_threads._rank(seed, npc["id"], "leaves") % len(leaving)], who=who))
    return lines


def caller_comes(session: Any, now: int) -> list[str]:
    """Someone sent has reached the player, wherever in that town they are. They are a real person from here on."""
    import vouching
    world = session.world_state
    state = world_threads.view(world)
    town = local_places.settlement_of(world, world.get("location"))
    if state is None or not town or _callers_here(world):  # one at a time: the next waits until this one has gone
        return []
    for link in links(state):
        if link["kind"] != CALLER or link.get("fires_at") is not None or link.get("caller_id") or link.get("settlement_id") != town:
            continue
        words = world_threads.job_lines("link", "caller") or {}
        npc = session.create_npc_from_ai({
            "name": world_threads.living_world.stable_local_name(world, link["thread_id"], words.get("role", "Ulak")),
            "role": words.get("role", "Ulak"), "location": world["location"], "relationship": "neutral",
            "appearance": words.get("appearance", ""), "personality": words.get("personality", ""),
        }, allow_other_location=True)
        if not isinstance(npc, dict):
            continue
        link.update(caller_id=npc["id"], status="arrived")
        if _of_the_house(world, link):
            vouching.summoned(world, link)
        message = _message(world, link, words)
        npc.update(caller_of=link["thread_id"], came_from=link["place_id"], back_at=now + CALLER_STAYS_SECONDS,
                   leaves_turn=int(world.get("flags", {}).get("turn_index", 0) or 0) + CALLER_TALK_TURNS, message=message)
        profile = npc.get("personal_profile")
        if isinstance(profile, dict):  # who they are is why they came, not a trade drawn for a stranger
            profile.update(occupation=world_threads._fill(words.get("occupation", ""), owner=_link_owner(world, link)),
                           current_activity=words.get("activity", ""),
                           immediate_goal=world_threads._fill(words.get("goal", ""), what=_link_matter(world, link, spoken=True)),
                           reason_for_being_here=world_threads._fill(words.get("reason", ""), owner=_link_owner(world, link)))
        row = _row_of(state, link)
        if row:
            row["known_to_player"] = True
        session._set_scene_active_npc(npc, world.get("flags", {}).get("turn_index", 0))
        _settle_up(world, link)
        who = world_threads.living_world.turkish_initial_upper(world_threads.living_world.public_npc_name(npc))
        owner = _link_owner(world, link)
        return [world_threads._fill(_caller_line(world, link, words), who=who, Owner=world_threads.sentence(owner),
                                    owner=owner, message=message)]
    return []


def _within_reach(world: dict[str, Any], npc: dict[str, Any], place_id: str) -> bool:
    import world_reactions
    here = npc.get("location")
    return place_id == here or place_id in world_reactions._neighbours(world, here)


def reachable(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    """What this person could have heard by now: their own place or the one next door, newest first."""
    state = world_threads.view(world)
    if state is None or not isinstance(npc, dict):
        return []
    now = world_threads._now(world)
    return [row for row in reversed(state.get(KEY) or [])
            if now - row["at"] < RECENT_SECONDS and _within_reach(world, npc, row["place_id"])]


def speech_line(world: dict[str, Any], npc: Any, listed: Any = frozenset()) -> str:
    """One labelled sentence, and only if it is not already among what this person lists."""
    for row in reachable(world, npc):
        if row["thread_id"] not in listed:
            return " " + world_threads._fill(world_threads.job_lines("shared", "heard_happening") or "", heard=row["line"])
    return ""
