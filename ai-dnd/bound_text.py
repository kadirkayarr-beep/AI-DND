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
PAPER_LIMIT = 300
PAPER_LINE = "Kâğıtta şunlar yazıyor: “{words}”"
_PAPER_SLOTS = frozenset({"is", "yer"})  # a name on a paper needs a real tie between two people, and none is saved
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


def choose_paper(world: dict[str, Any], key: str, kinds: list[str], *, public: bool = False) -> dict[str, Any] | None:
    """What a real paper of these kinds says. Writes nothing."""
    return _first_fit(world, key, (row for row in items("written_texts")
                                   if row["kind"] in kinds and set(row["slots"]) <= _PAPER_SLOTS
                                   and (row["public"] or not public)), PAPER_LIMIT)


def _paper_kinds(name: Any) -> list[str]:
    table = rules().get("paper_kinds", {})
    words = living_world.normalize_text(name).split()
    return next((kinds for stem, kinds in table.items() if any(word.startswith(stem) for word in words)), [])


def _means(name: str, words: list[str]) -> bool:
    """The line names this paper: any word of its name, whatever ending the line gave it."""
    stems = {word[:4] for word in living_world.normalize_text(name).split() if len(word) >= 3}
    return any(word.startswith(stem) for word in words for stem in stems)


def _paper_meant(world: dict[str, Any], words: list[str]) -> tuple[str, list[str]] | None:
    """A paper in the bag or lying right here that these words name. Reading one takes really reaching it."""
    held = set((world.get("equipment") or {}).values())
    for item in world.get("inventory", []):
        name = item.get("name") if isinstance(item, dict) else None
        item_id = str(item.get("item_id") or "") if isinstance(item, dict) else ""
        if (isinstance(name, str) and item_id and item_id not in held and not item_id.startswith("parcel:")
                and _paper_kinds(name) and _means(name, words)):
            return f"item:{item_id}", _paper_kinds(name)
    for feature in world.get("features", []):
        if (isinstance(feature, dict) and feature.get("location") == world.get("location") and not feature.get("hidden")
                and not feature.get("text") and _paper_kinds(feature.get("name")) and _means(str(feature.get("name")), words)):
            return f"feature:{feature.get('id')}", _paper_kinds(feature.get("name"))
    return None


def paper_words(world: dict[str, Any], text: Any, looked_at: str = "") -> str | None:
    """The screen line for the paper this line reads, or None. looked_at is the thing a look was read as being on."""
    import world_threads
    from adventure import dialogue_jobs
    if not isinstance(text, str) or world.get("combat", {}).get("active"):
        return None
    folded = living_world.normalize_text(text)
    reads = ("?" not in text and dialogue_jobs._READING.search(folded)) or dialogue_jobs._ASKS_WHAT_IT_SAYS.search(folded)
    if not reads and not looked_at:
        return None
    paper = _paper_meant(world, folded.split() if reads else living_world.normalize_text(looked_at).split())
    if paper is None:
        return None
    kept = seen(world, paper[0])
    if kept is None:
        world_threads.ensure(world)
        kept = choose_paper(world, paper[0], paper[1])
        if kept is None:
            return None
        keep(world, paper[0], kept)
    return PAPER_LINE.format(words=kept["text"])


def read_turn(session: Any, text: Any, looked_at: str = "") -> dict[str, Any] | None:
    """Reading a paper is its own turn: Python's words, and nothing else about the world moves."""
    shown = paper_words(session.world_state, text, looked_at)
    if shown is None:
        return None
    flags = session.world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    session.messages.extend([{"role": "user", "content": text}, {"role": "assistant", "content": shown}])
    return {"messages": session.messages, "narration": shown, "model_calls": 0,
            "action_result": {"action": "read_paper", "status": "resolved", "success": True,
                              "state_changes": [], "direct_response": shown}}


def notice_of(world: dict[str, Any], settlement_id: Any) -> str | None:
    """The public notice on this town's board, chosen once."""
    key = f"board:{settlement_id}"
    kept = seen(world, key)
    if kept is None:
        kept = choose_paper(world, key, ["ilan"], public=True)
        if kept is None:
            return None
        keep(world, key, kept)
    return kept["text"]


def work_line(world: dict[str, Any], thread: dict[str, Any], seconds: int, day: int) -> str | None:
    """A moment of the work really done, in the place it was done. It tells nothing of pay, the end or the hours."""
    if not seconds or thread.get("status") not in {"accepted", "done"}:
        return None
    kind = rules().get("work_kinds", {}).get(thread.get("template_id"))
    tags = set(place_tags(world, thread.get("place_id")))
    rows = [row for row in items("work_lines") if row["work_kind"] == kind and tags & set(row["place_tags"])]
    scale = "kisa" if seconds < 4 * 3600 else "yarim_gun" if seconds < 8 * 3600 else "tam_gun"
    rows = [row for row in rows if row["time_phrase"] == scale] or rows
    if not rows:
        return None
    return rows[(_rank(world, thread.get("thread_id"), "shift") + day) % len(rows)]["text"]


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
