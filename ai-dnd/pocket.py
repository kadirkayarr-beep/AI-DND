"""What the player puts in the bag or throws away by hand: the line's result reaches the save, with no model call.

Only what the screen just showed can be taken, as a plain thing with no worth. Coin never comes this way.
"""

from __future__ import annotations

import re
from typing import Any

import equipment_economy
import living_world
import world_threads

_INTO_THE_BAG = re.compile(r"\b(?:cebe|cebime|cebine|cantama|cantaya|cantamiza|heybeme|heybeye|torbama|torbaya)\b")
_TOSSES = re.compile(r"\b(?:firlat\w*|yirt(?:iyorum|ip|tim|ayim)|yak(?:iyorum|ip|tim|ayim)|at(?:iyorum|ip|tim|ayim))\b")
_WORTH = ("altin", "gumus", "bakir", "para", "sikke", "mucevher", "elmas", "yakut", "zumrut", "hazine", "kese")
_NOT_THINGS = frozenset({
    "alip", "aliyorum", "atiyorum", "koyuyorum", "sokuyorum", "topluyorum", "toplayip", "iyilerini", "icinde", "icine",
    "birkac", "biraz", "tane", "hepsini", "ondan", "bunlari", "sunlari", "onlari", "yarar", "neyse", "varsa",
})
_SHOWN_TURNS = 4
_THING_WORD = re.compile(r"[^\W\d_]{4,}")


def _shown(session) -> list[str]:
    """The words of the last few things the screen said, in order."""
    said = [item.get("content") for item in reversed(session.messages)
            if isinstance(item, dict) and item.get("role") == "assistant" and isinstance(item.get("content"), str)]
    return _THING_WORD.findall(" ".join(reversed(said[:_SHOWN_TURNS])))


def _thing_in(words: list[str], shown: list[str]) -> str | None:
    """The thing named both on the screen and in the line: two words if it has two."""
    wanted = [word for word in words if word not in _NOT_THINGS and not _INTO_THE_BAG.fullmatch(word)]

    def said(raw: str) -> bool:
        stem = living_world.normalize_text(raw)
        return stem not in _NOT_THINGS and any(word.startswith(stem) for word in wanted)

    for first, second in zip(shown, shown[1:]):
        if said(first) and said(second):
            return f"{first} {second}"
    return next((word for word in shown if said(word)), None)


def _take(session, text: str, words: list[str]) -> dict[str, Any]:
    world = session.world_state
    shown = _shown(session)
    thing = None if any(word.startswith(_WORTH) for word in words) else _thing_in(words, shown)
    if thing is None:
        line = "Burada çantana atabileceğin öyle bir şey görmüyorsun."
    else:
        name = thing[:1].upper() + thing[1:].casefold()
        equipment_economy.grant_plain(world, name)
        line = f"{name} çantana giriyor."
    flags = world.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    session.messages.extend([{"role": "user", "content": text}, {"role": "assistant", "content": line}])
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "pocket", "status": "resolved", "success": thing is not None,
                              "state_changes": ["inventory"] if thing else [], "direct_response": line}}


def _toss(session, words: list[str]) -> None:
    """Thrown away is gone: the narrator tells it, the bag has already lost it."""
    world = session.world_state
    held = set((world.get("equipment") or {}).values())
    for item in list(world.get("inventory", [])):
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or item.get("item_id") in held:
            continue
        stem = world_threads._stem(living_world.normalize_text(name).split()[0]) if name.strip() else ""
        if len(stem) < 3 or not any(word.startswith(stem) for word in words):
            continue
        world["inventory"].remove(item)
        quest = str(item.get("item_id") or "").removeprefix("parcel:")
        for thread in (world_threads.view(world) or {"threads": []})["threads"]:
            if thread.get("quest_id") == quest:
                thread["parcel_gone"] = True
        return


def resolve(session, text: Any) -> dict[str, Any] | None:
    world = session.world_state
    if (not isinstance(text, str) or "?" in text or world.get("combat", {}).get("active")
            or session.character.get("current_hp", 0) <= 0):
        return None
    folded = living_world.normalize_text(text)
    words = folded.split()
    if _INTO_THE_BAG.search(folded):
        return _take(session, text, words)
    if _TOSSES.search(folded):
        _toss(session, words)
    return None
