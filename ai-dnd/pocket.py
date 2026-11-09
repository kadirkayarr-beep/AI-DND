"""What the player puts in the bag or throws away by hand: the line's result reaches the save, with no model call.

Only what the screen just showed can be taken, as a plain thing with no worth. Coin never comes this way.
"""

from __future__ import annotations

import re
from typing import Any

import equipment_economy
import living_world
import tr_case
import shop_trade
import world_threads

_INTO_THE_BAG = re.compile(r"\b(?:cebe|cebime|cebine|cantama|cantaya|cantamiza|heybeme|heybeye|torbama|torbaya)\b")
_PUTS_IT_THERE = re.compile(r"\b(?:ali(?:p|yorum)|at(?:iyorum|ip|tim|ayim)|koy\w*|sok\w*|topl\w*|tik\w*)\b")
_TOSSES = re.compile(r"(?:firlat|yirt|yak|at)(?:iyorum|ip|tim|ayim)")
_PHRASE_NOUNS = frozenset({"goz", "adim", "imza", "tur", "bakis", "kahkaha", "laf", "nara", "tekme"})  # 'göz atmak' throws nothing
_LIT_NOT_BURNT = ("mesale", "fener", "mum", "lamba", "kandil")
_ON_THE_WAY_TO_THE_VERB = ("a", "e", "ip", "up")  # 'denize', 'buruşturup'
_WORTH = ("altin", "gumus", "bakir", "para", "sikke", "mucevher", "elmas", "yakut", "zumrut", "hazine", "kese")
_NOT_FOUND = (*_WORTH, "anahtar")  # a key the screen showed can be picked up, but a finding does not invent one
_AS_OBJECT = ("i", "u", "yi", "yu", "ni", "nu", "le", "la", "yle", "yla")  # 'parşömeni', 'parşömenle': a thing the line acts on
_NOT_THINGS = frozenset({
    "alip", "aliyorum", "atiyorum", "koyuyorum", "sokuyorum", "topluyorum", "toplayip", "iyilerini", "icinde", "icine",
    "birkac", "biraz", "tane", "hepsini", "ondan", "bunlari", "sunlari", "onlari", "yarar", "neyse", "varsa",
})
_UNDER = re.compile(r"altin(?:a|da|dan|daki)")  # 'masanın altında' is no gold
_SHOWN_TURNS = 8
_DENIED = re.compile(r"\b(?:yok|degil)\b|m[iu]yor")  # 'yok', 'değil', 'görünmüyor': said as not there
_TOLD_TO_YOU = ("sun", "sin", "din", "dun")  # 'alıyorsun', 'aldın': the sentence says the player did it
EMPTY_HANDED = "Uzanıyorsun ama eline geçen bir şey yok."
_THING_WORD = re.compile(r"[^\W\d_]{4,}")
_SEVERAL = re.compile(r"\s*,\s*|\s+(?:ve|ile)\s+")  # a reading can name two things in its one word


def names_worth(text: Any) -> bool:
    return any(word.startswith(_NOT_FOUND) and not _UNDER.fullmatch(word) for word in living_world.normalize_text(text).split())


def told_as_there(text: str) -> str:
    """What the screen itself says is there: no quoted words, whoever said them, and no sentence that denies it."""
    sentences = re.split(r"(?<=[.!?…])\s+|\n+", living_world._text_outside_quotes(text))
    return " ".join(part for part in sentences if not _DENIED.search(living_world.normalize_text(part)))


def _shown(session) -> list[str]:
    """The words of the last few things the screen said, in order."""
    said = [item.get("content") for item in reversed(session.messages)
            if isinstance(item, dict) and item.get("role") == "assistant" and isinstance(item.get("content"), str)]
    told = [text for text in getattr(session, "recent_dm_narrations", ()) if isinstance(text, str)]  # the narrator's turns live here
    return _THING_WORD.findall(told_as_there("\n".join([*told[-_SHOWN_TURNS:], *reversed(said[:_SHOWN_TURNS])])))


def _fixed_here(world: dict[str, Any]) -> tuple[str, ...]:
    """What the scene is made of cannot go in a bag: 'tezgâhtaki şeyi alıyorum' takes no counter."""
    names = [word for feature in living_world.visible_features(world, world.get("location"))
             for word in living_world.normalize_text(feature.get("name")).split() if len(word) >= 4]
    return tuple(world_threads._stem(word).rstrip("aeiou") for word in names)  # 'tezgâhı' is what 'tezgâhtaki' stands on


def _thing_in(words: list[str], shown: list[str], fixed: tuple[str, ...] = ()) -> str | None:
    """The thing named both on the screen and in the line: two words if it has two."""
    wanted = [word for word in words if word not in _NOT_THINGS and not _INTO_THE_BAG.fullmatch(word)]
    wanted = [word for word in wanted if not any(word.startswith(stem) for stem in fixed)]

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
    thing = None if any(word.startswith(_WORTH) for word in words) else _thing_in(words, shown, _fixed_here(world))
    if thing is None:
        return None  # nothing here to put away: whoever else this line is for still reads it
    got = _pick_up(session, tr_case.upper_first(thing[:1] + thing[1:].casefold()))
    if not got:
        return None
    taken = [got]
    for other in _also_taken(session, words):
        other = _pick_up(session, tr_case.upper_first(other[:1] + other[1:].casefold()))
        if other:
            taken.append(other)
    return _receipt(session, text, f"{' ve '.join(taken)} çantana giriyor.")


def _stem(word: Any) -> str:
    folded = living_world.normalize_text(word).split()
    return world_threads._stem(folded[-1]) if folded else ""


def _bare(word: str) -> str:
    """A thing's plain name even when the model copied it as the line said it: 'keseyi', 'defteri'."""
    word = word.strip()
    folded = living_world.normalize_text(word)
    if len(folded) >= 5 and folded.endswith(("yi", "yu")):
        return word[:-2]
    return word[:-1] if len(folded) >= 6 and folded[-1] in "iu" and folded[-2] not in "aeiou" else word


def _also_taken(session, words: list[str]) -> list[str]:
    """Whatever else this line takes that the screen showed: 'parşömenle anahtarı alıyorum' is two things."""
    world = session.world_state
    fixed = _fixed_here(world)
    names = []
    for shown in dict.fromkeys(_shown(session)):
        other = living_world.normalize_text(shown)
        if (len(other) < 4 or other.startswith(_WORTH) or other.startswith(fixed) or other in _NOT_THINGS
                or shown in names or _named_in_bag(world, other)):
            continue
        if other.startswith(_people_here(session)):
            continue
        if any(w.startswith(other) and w not in _NOT_THINGS and w.removeprefix(other) in _AS_OBJECT
               and _taken_by_its_verb(words, at) for at, w in enumerate(words)):
            names.append(shown)
    return names


_A_VERB = re.compile(r"\w+(?:yor(?:um|uz)|[iu]p|d[iu]m|t[iu]m|[ae]y[iı]m)")


def _taken_by_its_verb(words: list[str], at: int) -> bool:
    """The next verb after the thing is a taking one: 'anahtarı alıyorum', never 'kapıyı kapatıyorum'."""
    verb = next((word for word in words[at + 1:] if _A_VERB.fullmatch(word)), None)
    return verb is not None and _PUTS_IT_THERE.fullmatch(verb) is not None


def _people_here(session) -> tuple[str, ...]:
    """A person the screen named is no thing to put in a bag."""
    names = [living_world.normalize_text(npc.get("name")) for npc in session.active_npcs() if isinstance(npc, dict)]
    return tuple(word for name in names for word in name.split() if len(word) >= 3) or ("\x00",)


def take_named(session, text: str, word: str) -> dict[str, Any] | None:
    """The front reading says the line takes this. It is real if the line names it and the screen showed it."""
    world = session.world_state
    words = living_world.normalize_text(text).split()
    if not word:
        return None if any(w.startswith(_WORTH) for w in words) else _take(session, text, words)
    taken = [name for name in (_take_one(session, words, part) for part in _SEVERAL.split(word)) if name]
    for other in _also_taken(session, words):
        other = _pick_up(session, tr_case.upper_first(other[:1] + other[1:].casefold()))
        if other:
            taken.append(other)
    return _receipt(session, text, f"{' ve '.join(taken)} çantana giriyor.") if taken else None


def _take_one(session, words: list[str], word: str) -> str | None:
    """One thing the reading named: in the line and on the screen, or it stays where it is."""
    world = session.world_state
    word = _bare(word)
    stem = _stem(word)
    if (len(stem) < 3 or stem.startswith(_WORTH) or not any(w.startswith(stem) for w in words)
            or not any(living_world.normalize_text(w).startswith(stem) for w in _shown(session))):
        return None
    name = tr_case.upper_first(word[:1] + word[1:].casefold())
    return None if _named_in_bag(world, stem) else _pick_up(session, name)


def _pick_up(session, name: str) -> str | None:
    """A real thing lying here that the screen showed, moved into the bag: the name of what was taken, or None.

    The words alone make nothing (C9): only an existing item on the ground or a surface where the player stands
    moves. What whoever serves here sells is bought at the counter, not picked up.
    """
    import item_transfers
    world = session.world_state
    if any(shop_trade.sells(world, npc, name) for npc in session.active_npcs()):
        return None
    found = item_transfers.real_thing_here(world, _stem(name))
    if found is None:
        return _pick_up_told(session, name)
    source, item = found
    moved = item_transfers.transfer_now(world, item_id=item["item_id"], source_id=source, recipient_id="player")
    return str(item["name"]) if moved.status == "applied" else None


def _told_here(session, name: str) -> bool:
    """This place's own narration names the thing, every word of it: the narrator's lines since the player came
    here (a move clears them), with no quoted words and no sentence that denies it."""
    told = [text for text in getattr(session, "recent_dm_narrations", ()) if isinstance(text, str)]
    said = [living_world.normalize_text(word) for word in _THING_WORD.findall(told_as_there("\n".join(told)))]
    parts = [world_threads._stem(part) for part in living_world.normalize_text(name).split()]
    return bool(parts) and all(len(part) >= 3 and any(word.startswith(part) for word in said) for part in parts)


def _told_held(session, stem: str) -> bool:
    """A sentence of this scene that names the thing also names someone here: 'Oren'in elinde kırık bir halka var'
    puts it in his hand, so a take line would take it from him unasked. Such a thing stays words."""
    people = _people_here(session)
    for text in getattr(session, "recent_dm_narrations", ()):
        if not isinstance(text, str):
            continue
        for sentence in re.split(r"(?<=[.!?…])\s+|\n+", living_world._text_outside_quotes(text)):
            words = living_world.normalize_text(sentence).split()
            if any(word.startswith(stem) for word in words) and any(word.startswith(people) for word in words):
                return True
    return False


def _pick_up_told(session, name: str) -> str | None:
    """No real thing lies here: a worthless one this scene's narration showed is made once and taken (Kadir,
    2026-11-03). A person, a part of the place, coin, a key or anything of worth stays words."""
    import item_transfers
    world = session.world_state
    stem = _stem(name)
    if (len(stem) < 3 or stem.startswith(_NOT_FOUND) or names_worth(name) or stem.startswith(_fixed_here(world))
            or stem.startswith(_people_here(session)) or not _told_here(session, name) or _told_held(session, stem)):
        return None
    return item_transfers.pick_up_told(world, name, stem=stem)


def asked_for(text: str, word: str) -> tuple[str, ...]:
    """What a line that took nothing was after: the model's word, or the line's own longer words."""
    if word:
        return (_stem(_bare(word)),)
    return tuple(w for w in living_world.normalize_text(text).split() if len(w) >= 4 and w not in _NOT_THINGS)


def not_in_bag(world: dict[str, Any], stems: Any) -> tuple[str, ...]:
    """A thing some other channel did put in the bag was taken: the line may say so."""
    return tuple(stem for stem in stems or () if not any(
        living_world.normalize_text(item.get("name") if isinstance(item, dict) else item).find(stem) >= 0
        for item in world.get("inventory", [])))


def without_the_taking(narration: Any, stems: tuple[str, ...]) -> Any:
    """Repair: the sentences that say the player has what Python never gave them leave the line."""
    if not isinstance(narration, str) or not narration.strip() or not stems:
        return narration
    kept = [sentence for sentence in re.split(r"(?<=[.!?…])\s+", narration.strip()) if not _tells_it_taken(sentence, stems)]
    return " ".join(kept) or EMPTY_HANDED


def _tells_it_taken(sentence: str, stems: tuple[str, ...]) -> bool:
    words = living_world.normalize_text(sentence).split()
    return any(word.startswith(stems) for word in words) and any(word.endswith(_TOLD_TO_YOU) for word in words)


def _says_it(text: str, stem: str) -> bool:
    return any(word.startswith(stem) for word in living_world.normalize_text(text).split())


def without_said(text: Any, stem: str) -> Any:
    """Repair: the sentences that name a thing nobody moved leave the line."""
    if not isinstance(text, str) or not text.strip() or not stem:
        return text
    return " ".join(part for part in re.split(r"(?<=[.!?…])\s+", text.strip()) if not _says_it(part, stem))


def _named_in_bag(world: dict[str, Any], stem: str) -> bool:
    """The bag holds a thing of this name. A case ending is no other thing: 'takimini' starts with the bag's 'takimi'."""
    for item in world.get("inventory", []):
        bag = _stem(item.get("name") if isinstance(item, dict) else item)
        if stem == bag or (len(bag) >= 4 and stem.startswith(bag)):
            return True
    return False


def already_in_bag(session, text: str, name: str) -> dict[str, Any]:
    """The line takes what the bag already holds: nothing is made, and the reply says so."""
    line = f"{name} zaten çantanda."
    session.messages.extend([{"role": "user", "content": text}, {"role": "assistant", "content": line}])
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "pocket", "status": "resolved", "success": False,
                              "state_changes": [], "direct_response": line}}


def _committed(session, item: str, stem: str, text: str, person: Any, line: Any) -> bool:
    """The claim comes true or stays false: the job's parcel from its owner, or a real plain thing with no worth.

    Someone's own hand may give a plain thing unasked, but only one that hand really holds; the narrator has no
    hand, so it only tells what the line did, with a real thing lying here. The words alone make nothing (C9).
    """
    import item_transfers
    from adventure import dialogue_jobs
    world = session.world_state
    if item.startswith("parcel:"):
        thread = world_threads.parcel_thread(world, item)
        return bool(thread and thread.get("status") == "accepted" and isinstance(person, dict)
                    and thread.get("owner_npc_id") == person.get("id")
                    and dialogue_jobs.hand_over(session, thread, person, own_turn=False))
    if _named_in_bag(world, stem):
        return True
    if (len(stem) < 2 or stem.startswith(_NOT_FOUND) or not _says_it(text, stem)
            or (line is not None and not _says_it(line, stem))):
        return False
    if isinstance(person, dict):
        held = next((entry for entry in person.get("inventory") or []
                     if isinstance(entry, dict) and isinstance(entry.get("item_id"), str)
                     and any(word.startswith(stem) for word in living_world.normalize_text(entry.get("name")).split())),
                    None)
        if held is None or item_transfers.item_needs_card(world, held):
            return False  # a thing of worth changes hands only by its own owner's way, never by a reply
        source = str(person.get("id"))
    else:
        found = item_transfers.real_thing_here(world, stem)
        if found is None:
            # Only the player's own taking line, never the narrator's say-so alone, picks up a thing told here.
            words = living_world.normalize_text(line).split() if isinstance(line, str) else []
            taken = any(word.startswith(stem) and _taken_by_its_verb(words, at) for at, word in enumerate(words))
            return taken and _pick_up_told(session, tr_case.upper_first(_bare(item)[:1] + _bare(item)[1:].casefold())) is not None
        source, held = found
    moved = item_transfers.transfer_now(world, item_id=held["item_id"], source_id=source, recipient_id="player")
    return moved.status == "applied"


def _a_sale(world: dict[str, Any], person: Any, claim: dict[str, Any], item: str, stem: str) -> bool:
    """Goods on the list, or goods with a price, from whoever serves: a sale, which only the counter trade makes.
    What the counter already sold is in the bag, and saying so is true."""
    return (not item.startswith("parcel:") and not _named_in_bag(world, stem) and shop_trade.is_vendor(world, person)
            and (shop_trade.sells(world, person, item) or bool(claim.get("amount_cp"))))


def settle_claim(session, claim: Any, text: Any, person: Any = None, *, line: Any = None) -> tuple[Any, str]:
    """What a reply says changed hands: (the line, what was taken off it). Python commits it or it goes.

    line is the player's own words, given for the narrator's claims: see _committed.
    """
    item = claim.get("item") if isinstance(claim, dict) else None
    if not isinstance(item, str) or not item.strip():
        return text, ""
    item = item.strip()
    world = session.world_state
    thread = world_threads.parcel_thread(world, item) if item.startswith("parcel:") else None
    named = next((entry.get("name") for entry in world.get("inventory", [])
                  if isinstance(entry, dict) and entry.get("item_id") == item), None)
    stem = _stem(thread.get("item_noun") if thread else named or item)
    if claim.get("to") != "person" and _a_sale(world, person, claim, item, stem):
        # Nothing changes hands; the words stay, since a price said is true ('bira dört bakır'), and the
        # stem goes back so the stage direction's handing over leaves.
        return text, stem
    if claim.get("to") != "person" and _committed(session, item, stem, text, person, line):
        return text, ""
    return without_said(text, stem), stem


def bag_names(world: dict[str, Any]) -> list[str]:
    """What the player really has, for the prompt, in the words of the bag."""
    names = [item.get("name") or item.get("weapon_id") if isinstance(item, dict) else item
             for item in world.get("inventory", [])]
    return [str(name) for name in names if name][:12]


def _receipt(session, text: str, line: str) -> dict[str, Any]:
    import bound_text
    read_out = bound_text.paper_words(session, text)  # 'alıp okuyorum': the taking made it readable
    line = f"{line} {read_out}" if read_out else line
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
