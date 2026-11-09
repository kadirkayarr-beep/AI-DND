"""The one read-only view of the player's quest records (Dilim 2, Task 6).

The top-bar counter, the journal and the API's old quest fields all read this: a row is one record of
``world.quests`` (a town errand's dynamic row included) with the people and place it names, shown under public
names only. Nothing here writes."""

from __future__ import annotations

import copy
from typing import Any, NamedTuple

import living_world
import world_happenings
import world_threads

MAX_CARD_LINES = 2
MAX_RUMORS = 6
MAX_TRAILS = 6

# raw status of the record -> the view's section; a dynamic record keeps its upper-case words, an older one its own
_DYNAMIC = {"ACTIVE": "active", "BLOCKED": "active", "DISCOVERED": "offered",
            "COMPLETED": "done", "FAILED": "let_go", "ABANDONED": "let_go"}
_OLDER = {"accepted": "active", "completed": "done", "cancelled": "let_go"}


class _Record(NamedTuple):
    section: str | None
    row: dict[str, Any]
    quest: dict[str, Any]
    giver_id: Any
    recipient_id: Any


def _npc(world: dict[str, Any], npc_id: Any) -> dict[str, Any] | None:
    return next((n for n in world.get("npcs", []) if isinstance(n, dict) and n.get("id") == npc_id), None) if npc_id else None


def _name(world: dict[str, Any], npc_id: Any) -> str | None:
    npc = _npc(world, npc_id)
    return living_world.public_npc_name(npc) if npc is not None else None


def _thread_of(world: dict[str, Any], quest_id: Any) -> dict[str, Any] | None:
    state = world_threads.view(world)
    if state is None or not isinstance(quest_id, str):
        return None
    return next((t for t in (*state["threads"], *state["history"]) if t.get("quest_id") == quest_id), None)


def _result(thread: dict[str, Any] | None) -> str | None:
    """What the engine wrote when the job ended: its own paid line, the broken-seal half pay, or the late hand-over."""
    if thread is None:
        return None
    if thread.get("delivered_late"):
        return "geç teslim"
    paid = thread.get("paid_cp")
    if thread.get("status") != "done" or type(paid) is not int:
        return None
    return f"mühür kırıktı: {paid} bakır" if thread.get("seal_broken") is True else f"{paid} bakır ödendi"


def _objectives(quest: dict[str, Any], dynamic: bool) -> list[str]:
    if dynamic:
        return [objective["description"] for objective in quest.get("objectives", [])
                if objective.get("visibility") == "known" and objective.get("graph_state") != "HIDDEN"]
    return [str(objective["description"]) for objective in quest.get("objectives", [])
            if isinstance(objective, dict) and objective.get("description")]


def _records(world: dict[str, Any]) -> list[_Record]:
    found = []
    for quest in world.get("quests", []):
        if not isinstance(quest, dict):
            continue
        dynamic = quest.get("record_kind") == "dynamic"
        section = (_DYNAMIC if dynamic else _OLDER).get(quest.get("status"))
        thread = _thread_of(world, quest.get("quest_id")) if dynamic else None
        giver_id = quest.get("giver_npc_id") or (thread or {}).get("owner_npc_id")
        recipient_id = (thread or {}).get("recipient_npc_id")
        place_id = (thread or {}).get("target_place_id")
        place = (world.get("locations") or {}).get(place_id) if place_id else None
        row = {
            "quest_id": quest.get("quest_id"),
            "title": quest.get("title"),
            "summary": quest.get("description"),
            "giver": _name(world, giver_id),
            "recipient": _name(world, recipient_id),
            "place": place.get("name") if isinstance(place, dict) else None,
            "status": section or "other",
            "objectives": _objectives(quest, dynamic),
            "result": _result(thread) if section in {"done", "let_go"} else None,
            "record_kind": quest.get("record_kind"),
            "raw_status": quest.get("status"),
        }
        found.append(_Record(section, row, quest, giver_id, recipient_id))
    return found


def dynamic_records(world: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every dynamic record as (row, the stored record): the adventure journal's cards, hints and timeline start here."""
    return [(record.row, record.quest) for record in _records(world) if record.row["record_kind"] == "dynamic"]


def legacy_quests(world: dict[str, Any]) -> list[dict[str, Any]]:
    """The API's old ``quests`` field: the records that are not dynamic, with their lower-case statuses."""
    return [
        {
            "quest_id": quest.get("quest_id"),
            "title": quest.get("title"),
            "description": quest.get("description"),
            "status": quest.get("status"),
            "giver_npc_id": quest.get("giver_npc_id"),
            "objectives": [
                {
                    "objective_id": objective.get("objective_id"),
                    "description": objective.get("description"),
                    "status": objective.get("status"),
                    "progress": objective.get("progress", 0),
                    "required_count": objective.get("required_count", 1),
                }
                for objective in copy.deepcopy(quest.get("objectives", []))
            ],
        }
        for record in _records(world)
        if record.section is not None and record.row["record_kind"] != "dynamic"
        for quest in (record.quest,)
    ]


def _rumors(world: dict[str, Any], lore_state: Any) -> list[dict[str, str]]:
    from adventure.projection import _heard_rumors

    found = [{"label": "Söylenti", "text": text} for text in _heard_rumors(world, lore_state)]
    for row, quest in dynamic_records(world):
        for objective in quest.get("objectives", []):
            if (objective.get("type") == "discover_clue" and objective.get("graph_state") == "COMPLETE"
                    and objective.get("visibility") == "known"):
                found.append({"label": "İpucu", "text": objective.get("description") or ""})
    return found[:MAX_RUMORS]


def _live(world: dict[str, Any], record_id: Any) -> dict[str, Any] | None:
    """A job or a link still open: a trail to anything closed or gone is no trail."""
    state = world_threads.view(world)
    if state is None:
        return None
    return next((r for r in (*state["threads"], *state.get(world_happenings.LINKS, ()))
                 if r.get("thread_id") == record_id), None)


def _followed(world: dict[str, Any], record: dict[str, Any]) -> bool:
    """The record the trail points at has come before the player: put to them or taken on, its own line shown, or they
    walked up to its place after it began (the place's ``seen_at``, written by every arrival). Computed, never kept."""
    if record.get("status") in {"offered", "accepted", "done"}:
        return True
    row = world_happenings._row_of(world_threads.view(world) or {}, record)
    if row is not None and row["known_to_player"]:
        return True
    place = (world.get("locations") or {}).get(record.get("place_id")) or {}
    seen, opened = place.get("seen_at"), record.get("opened_at")
    return type(seen) is int and type(opened) is int and seen > opened


def _trail(world: dict[str, Any], *, key: str, at: int, what: Any, record: dict[str, Any], source: str,
           from_id: Any) -> dict[str, Any] | None:
    place = (world.get("locations") or {}).get(record.get("place_id"))
    if not isinstance(what, str) or not what or not isinstance(place, dict) or not place.get("name"):
        return None
    owner = _npc(world, record.get("owner_npc_id"))
    return {"id": key, "what": what, "where": place["name"],
            "who": living_world.public_npc_name(owner) if owner is not None else None,
            "source": source, "followed": _followed(world, record),
            "_at": at, "_from_thread_id": from_id, "_to_thread_id": record["thread_id"]}


def _players_job(thread: Any) -> bool:
    return isinstance(thread, dict) and thread.get("offered_at") is not None


def _trail_rows(world: dict[str, Any]) -> list[dict[str, Any]]:
    """Every trail with its inner fields (when, from which record, to which), newest first, at most ``MAX_TRAILS``."""
    state = world_threads.view(world)
    if state is None:
        return []
    found = []
    for row in state.get(world_happenings.KEY) or []:  # (1) a known happening that opened a job still open
        target = _live(world, row["next_thread_id"]) if row["known_to_player"] else None
        if target is not None:
            found.append(_trail(world, key=f"{row['kind']}:{row['thread_id']}:{row['at']}", at=row["at"],
                                what=row["line"], record=target, source="teslim" if row["kind"] == "delivered" else "haber",
                                from_id=row["thread_id"]))
    for letter in (*state["threads"], *state["history"]):  # (2) a letter read: the trouble at its far end
        trouble = world_happenings._trouble_at_end_of(world, letter) if letter.get("letter_line") else None
        if trouble is not None:
            found.append(_trail(world, key=f"letter:{letter['thread_id']}", at=trouble["opened_at"],
                                what=trouble["public_line"], record=trouble, source="mektup",
                                from_id=letter["thread_id"]))
    for link in world_happenings.links(state):  # (3) word sent about the player's own job, that the player knows of
        about = world_threads.by_id(world, link.get("about_thread_id"))
        caller = _npc(world, link.get("caller_id"))
        if _players_job(about) and (caller is not None or link.get("tone") == "warned"):
            found.append(_trail(world, key=f"link:{link['thread_id']}", at=link["opened_at"],
                                what=(caller or {}).get("message") or world_happenings._link_matter(world, link),
                                record=link, source="haber", from_id=about["thread_id"]))
    found = [trail for trail in found if trail is not None]
    pointed = {trail["_to_thread_id"] for trail in found}
    for thread in state["threads"]:  # (4) work the player heard of that is still going begging; it falls once taken
        if (thread.get("status") == "heard" and type(thread.get("heard_turn")) is int
                and thread["thread_id"] not in pointed):  # a record another trail already points at is not twice
            found.append(_trail(world, key=f"duyulan:{thread.get('place_id')}:{thread.get('opened_at')}",
                                at=thread.get("opened_at") or 0, what=thread.get("public_line"), record=thread,
                                source="duyulan", from_id=None))
    found = [trail for trail in found if trail is not None]
    found.sort(key=lambda trail: trail["_at"], reverse=True)
    return found[:MAX_TRAILS]


def trails(world: dict[str, Any]) -> list[dict[str, Any]]:
    """The trails the player can follow: each points at a live record the engine opened; none is ever made up."""
    return [{key: value for key, value in trail.items() if not key.startswith("_")} for trail in _trail_rows(world)]


def view(world: dict[str, Any], lore_state: Any = None) -> dict[str, Any]:
    sections: dict[str, list[dict[str, Any]]] = {"active": [], "offered": [], "done": [], "let_go": []}
    for record in _records(world):
        if record.section is not None:
            sections[record.section].append(record.row)
    return {**sections, "trails": trails(world), "rumors": _rumors(world, lore_state),
            "active_count": len(sections["active"])}


def _in_trail(world: dict[str, Any], trail: dict[str, Any], npc_id: Any) -> bool:
    """A person hears of a trail only through a job they are in (tasarım karar 61): a place is not knowledge."""
    if npc_id is None:
        return False
    ends = (trail["_from_thread_id"],) if trail["source"] == "mektup" else (trail["_from_thread_id"], trail["_to_thread_id"])
    for record_id in ends:
        record = world_threads.by_id(world, record_id) or {}
        if npc_id in (record.get("owner_npc_id"), record.get("recipient_npc_id")):
            return True
    return False


def card_lines(world: dict[str, Any], *, npc: Any = None) -> list[str]:
    """For the narrator: the running jobs ("görevlerin: başlık (kime, nerede)") and the trails ("izler: ne → nerede");
    with ``npc``, only the jobs and trails that person is in."""
    lines = []
    for record in _records(world):
        if record.section != "active":
            continue
        if isinstance(npc, dict) and npc.get("id") not in (record.giver_id, record.recipient_id):
            continue
        row = record.row
        where = ", ".join(part for part in (row["recipient"] or row["giver"], row["place"]) if part)
        lines.append(f"görevlerin: {row['title']}" + (f" ({where})" if where else ""))
    trail_lines = [f"izler: {trail['what']} → {trail['where']}" for trail in _trail_rows(world)
                   if not isinstance(npc, dict) or _in_trail(world, trail, npc.get("id"))]
    return lines[:MAX_CARD_LINES] + trail_lines[:MAX_CARD_LINES]
