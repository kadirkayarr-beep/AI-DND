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
_PUTS_IT_THERE = re.compile(r"\b(?:ali(?:p|yorum)|at(?:iyorum|ip|tim|ayim)|koy\w*|sok\w*|topl\w*|tik\w*)\b")
_TOSSES = re.compile(r"(?:firlat|yirt|yak|at)(?:iyorum|ip|tim|ayim)")
_PHRASE_NOUNS = frozenset({"goz", "adim", "imza", "tur", "bakis", "kahkaha", "laf", "nara", "tekme"})  # 'göz atmak' throws nothing
_LIT_NOT_BURNT = ("mesale", "fener", "mum", "lamba", "kandil")
_ON_THE_WAY_TO_THE_VERB = ("a", "e", "ip", "up")  # 'denize', 'buruşturup'
_WORTH = ("altin", "gumus", "bakir", "para", "sikke", "mucevher", "elmas", "yakut", "zumrut", "hazine", "kese")
_NOT_THINGS = frozenset({
    "alip", "aliyorum", "atiyorum", "koyuyorum", "sokuyorum", "topluyorum", "toplayip", "iyilerini", "icinde", "icine",
    "birkac", "biraz", "tane", "hepsini", "ondan", "bunlari", "sunlari", "onlari", "yarar", "neyse", "varsa",
})
_SHOWN_TURNS = 8
_PLAYERS_OWN_WORDS = re.compile(r"Sen: “[^”]*”")
_TOLD_TO_YOU = ("sun", "sin", "din", "dun")  # 'alıyorsun', 'aldın': the sentence says the player did it
_EMPTY_HANDED = "Uzanıyorsun ama eline geçen bir şey yok."
_THING_WORD = re.compile(r"[^\W\d_]{4,}")


def _shown(session) -> list[str]:
    """The words of the last few things the screen said, in order."""
    said = [item.get("content") for item in reversed(session.messages)
            if isinstance(item, dict) and item.get("role") == "assistant" and isinstance(item.get("content"), str)]
    return _THING_WORD.findall(_PLAYERS_OWN_WORDS.sub(" ", " ".join(reversed(said[:_SHOWN_TURNS]))))


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


def _take(session, text: str, words: list[str]) -> dict[str, Any] | None:
    world = session.world_state
    shown = _shown(session)
    thing = None if any(word.startswith(_WORTH) for word in words) else _thing_in(words, shown)
    if thing is None:
        return None  # nothing here to put away: whoever else this line is for still reads it
    name = thing[:1].upper() + thing[1:].casefold()
    equipment_economy.grant_plain(world, name)
    return _receipt(session, text, f"{name} çantana giriyor.")


def _stem(word: Any) -> str:
    folded = living_world.normalize_text(word).split()
    return world_threads._stem(folded[-1]) if folded else ""


def take_named(session, text: str, word: str) -> dict[str, Any] | None:
    """The front reading says the line takes this. It is real if the line names it and the screen showed it."""
    world = session.world_state
    words = living_world.normalize_text(text).split()
    if not word:
        return None if any(w.startswith(_WORTH) for w in words) else _take(session, text, words)
    stem = _stem(word)
    if (len(stem) < 3 or stem.startswith(_WORTH) or not any(w.startswith(stem) for w in words)
            or not any(living_world.normalize_text(w).startswith(stem) for w in _shown(session))):
        return None
    name = word[:1].upper() + word[1:].casefold()
    if any(_stem(item.get("name") if isinstance(item, dict) else item) == stem for item in world.get("inventory", [])):
        return None
    equipment_economy.grant_plain(world, name)
    return _receipt(session, text, f"{name} çantana giriyor.")


def asked_for(text: str, word: str) -> tuple[str, ...]:
    """What a line that took nothing was after: the model's word, or the line's own longer words."""
    if word:
        return (_stem(word),)
    return tuple(w for w in living_world.normalize_text(text).split() if len(w) >= 4 and w not in _NOT_THINGS)


def without_the_taking(narration: Any, stems: tuple[str, ...]) -> Any:
    """Repair: the sentences that say the player has what Python never gave them leave the line."""
    if not isinstance(narration, str) or not narration.strip() or not stems:
        return narration
    kept = [sentence for sentence in re.split(r"(?<=[.!?…])\s+", narration.strip()) if not _tells_it_taken(sentence, stems)]
    return " ".join(kept) or _EMPTY_HANDED


def _tells_it_taken(sentence: str, stems: tuple[str, ...]) -> bool:
    words = living_world.normalize_text(sentence).split()
    return any(word.startswith(stems) for word in words) and any(word.endswith(_TOLD_TO_YOU) for word in words)


def _receipt(session, text: str, line: str) -> dict[str, Any]:
    flags = session.world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    session.messages.extend([{"role": "user", "content": text}, {"role": "assistant", "content": line}])
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "pocket", "status": "resolved", "success": True,
                              "state_changes": ["inventory"], "direct_response": line}}


def _object_of(words: list[str], at: int, stem: str) -> bool:
    """The thing is what this verb acts on: 'mektubu denize atıyorum', never 'mektuba göz atıyorum'."""
    for back in range(at - 1, max(at - 4, -1), -1):
        word = words[back]
        if word.startswith(stem) and (word[-1] in "iu"):
            return True
        if word in _PHRASE_NOUNS or not (word == "bir" or word.endswith(_ON_THE_WAY_TO_THE_VERB)):
            return False
    return False


def _thrown_at(words: list[str], stem: str) -> int | None:
    for at, word in enumerate(words):
        if _TOSSES.fullmatch(word) and _object_of(words, at, stem) and not (
                word.startswith("yak") and stem.startswith(_LIT_NOT_BURNT)):
            return at
    return None


def _toss(session, text: str, words: list[str]) -> dict[str, Any] | None:
    """Thrown away is gone, and the screen says so: the bag has already lost it."""
    world = session.world_state
    held = set((world.get("equipment") or {}).values())
    for item in list(world.get("inventory", [])):
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or item.get("item_id") in held:
            continue
        stem = world_threads._stem(living_world.normalize_text(name).split()[0]) if name.strip() else ""
        at = _thrown_at(words, stem) if len(stem) >= 3 else None
        if at is None:
            continue
        quest = str(item.get("item_id") or "").removeprefix("parcel:")
        threads = [t for t in (world_threads.view(world) or {"threads": []})["threads"] if t.get("quest_id") == quest]
        if any(_only_set_down(world, thread, words, at) for thread in threads):
            return None  # whoever it belongs with is here: the person hears this line, the parcel stays a parcel
        world["inventory"].remove(item)
        for thread in threads:
            thread["parcel_gone"] = True
        return _receipt(session, text, f"{name} elinden çıkıyor; artık sende değil.")
    return None


def _only_set_down(world: dict[str, Any], thread: dict[str, Any], words: list[str], at: int) -> bool:
    """'At-' alone, or 'at-' in front of the person the parcel is for, does not throw an errand away."""
    if not words[at].startswith("at"):
        return False
    people = (world_threads.recipient_of(world, thread), world_threads.owner_of(world, thread))
    here = any(isinstance(npc, dict) and npc.get("location") == world.get("location") for npc in people)
    return here or not words[at - 1].endswith(("a", "e"))


def resolve(session, text: Any) -> dict[str, Any] | None:
    world = session.world_state
    if (not isinstance(text, str) or "?" in text or world.get("combat", {}).get("active")
            or session.character.get("current_hp", 0) <= 0):
        return None
    folded = living_world.normalize_text(text)
    words = folded.split()
    if _INTO_THE_BAG.search(folded) and _PUTS_IT_THERE.search(folded):
        return _take(session, text, words)
    return _toss(session, text, words)
