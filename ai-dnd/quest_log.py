"""The one read-only view of the player's quest records (Dilim 2, Task 6).

The top-bar counter, the journal and the API's old quest fields all read this: a row is one record of
``world.quests`` (a town errand's dynamic row included) with the people and place it names, shown under public
names only. Nothing here writes."""

from __future__ import annotations

import copy
from typing import Any, NamedTuple

import living_world
import world_threads

MAX_CARD_LINES = 2
MAX_RUMORS = 6

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


def view(world: dict[str, Any], lore_state: Any = None) -> dict[str, Any]:
    sections: dict[str, list[dict[str, Any]]] = {"active": [], "offered": [], "done": [], "let_go": []}
    for record in _records(world):
        if record.section is not None:
            sections[record.section].append(record.row)
    return {**sections, "trails": [], "rumors": _rumors(world, lore_state), "active_count": len(sections["active"])}


def card_lines(world: dict[str, Any], *, npc: Any = None) -> list[str]:
    """For the narrator: the running jobs ("görevlerin: başlık (kime, nerede)"); with ``npc``, only theirs."""
    lines = []
    for record in _records(world):
        if record.section != "active":
            continue
        if isinstance(npc, dict) and npc.get("id") not in (record.giver_id, record.recipient_id):
            continue
        row = record.row
        where = ", ".join(part for part in (row["recipient"] or row["giver"], row["place"]) if part)
        lines.append(f"görevlerin: {row['title']}" + (f" ({where})" if where else ""))
    return lines[:MAX_CARD_LINES]
