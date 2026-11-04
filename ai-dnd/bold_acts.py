"""What a free hand does when no other owner takes it: stealing and setting fires.

The dice and the state stay in Python and the attempt always happens: it can
fail, it can be seen, but it is never turned down. What people saw is kept in
one short ledger, so the next person who hears of it can act on it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

import living_world
import relationships
import shop_trade

logger = logging.getLogger(__name__)

MAX_DEEDS = 24
_STEAL = re.compile(
    r"\b(?:asir\w*|yurut\w*|yagmal\w*|calacag\w*|kapip\b|kistir\w*|el at\w*|arakl\w*|"
    r"keserek al\w*|kesip al\w*|cekip al\w*|sessizce cek\w*|indirip\b.*\bsakl\w*|cal(?:iyorum|ip|ayim|dim))"
)
# "Zili çalıyorum", "kapıyı çalıyorum", "flüt çalıyorum" are not theft.
_NOT_STOLEN = re.compile(
    r"\b(?:(?:zil|kapi|flut|ud|davul|gong|tokmak|sarki|keman|lavta|melodi|kopuz|saz)\w*|can[ia]?)\b.*\bcal(?:iyorum|ip)"
)
_ASKS = re.compile(r"\b(?:mi|mu|ne olur)\W*$")  # the owner leaves the question mark out
_DISTRACTED = re.compile(r"\w+(?:ken|[iu]nc[ae])\b")  # 'bakarken', 'dönünce': the eye is elsewhere
_ARSON = re.compile(r"\b(?:ates\w*\s+ver\w*|ates\w*\s+yak\w*|tutustur\w*|alev\w*\s+ver\w*|\w+\s+yakiyorum|\w+\s+yakacagim)")
_THINGS = (
    ("elma", "Elma"), ("ekmek", "Ekmek"), ("kalkan", "Kalkan"), ("defter", "Defter"),
    ("paket", "Paket"), ("anahtar", "Anahtar"), ("bicak", "Bıçak"), ("hancer", "Hançer"),
    ("sise", "Şişe"), ("yuzuk", "Yüzük"), ("kolye", "Kolye"), ("kitap", "Kitap"), ("mektup", "Mektup"),
)
_CAUGHT = (
    "{n} bileğini yakalıyor. “Elini çek! Bir daha görürsem bu kadar nazik olmam.”",
    "{n} bir anda dönüp sana bakıyor. “Ne yaptığını sanıyorsun sen?”",
    "{n} elini tokatlıyor. “Hırsız mısın, deli mi? Defol!”",
)
_NOTHING_THERE = (
    "Karıştırıp bakıyorsun; alınacak değerde bir şey çıkmıyor.",
    "Elini attığın yerden işe yarar bir şey çıkmıyor; elin boş dönüyor.",
    "Yokluyorsun ama para eden bir şey bulamıyorsun.",
)


def fold(session, text: str) -> str:
    return session._normalize_turkish_typos(text)


def is_theft(session, text: Any) -> bool:
    if not isinstance(text, str) or "?" in text:
        return False
    folded = fold(session, text)
    return bool(_STEAL.search(folded)) and not _NOT_STOLEN.search(folded)


def is_arson(session, text: Any) -> bool:
    return isinstance(text, str) and "?" not in text and bool(_ARSON.search(fold(session, text)))


def deeds(world: dict[str, Any]) -> list[dict[str, Any]]:
    return world.setdefault("flags", {}).setdefault("deeds", [])


def _now(world: dict[str, Any]) -> int:
    return int((world.get("campaign_time") or {}).get("elapsed_seconds", 0) or 0)


def remember(session, kind: str, text: str, *, victim_id: str | None = None, seen: bool = True) -> dict[str, Any]:
    """What was done, and who was standing there to see it.

    `witnesses` saw the player do it and `told` heard it from the player's own mouth: both
    can point at the player. `heard` only knows that it happened.
    """
    world = session.world_state
    witnesses = [npc["id"] for npc in session.active_npcs() if isinstance(npc.get("id"), str)] if seen else []
    ledger = deeds(world)
    deed = {
        "kind": kind, "text": text[:160], "location": world.get("location"), "victim_id": victim_id,
        "witnesses": witnesses, "turn": int(world.get("flags", {}).get("turn_index", 0) or 0),
        "at": _now(world), "heard": [], "told": [],
    }
    ledger.append(deed)
    del ledger[:-MAX_DEEDS]
    return deed


def _is_armed(npc: dict[str, Any]) -> bool:
    import game
    return bool(game._ARMED_ROLE.search(game._normalize_turkish_typos(str(npc.get("role", "")))))


def identifies(deed: dict[str, Any], npc_id: Any) -> bool:
    """This person can point at the player for it: they saw it or were told by the player."""
    return npc_id in deed.get("witnesses", []) or npc_id in deed.get("told", [])


def knows(deed: dict[str, Any], npc_id: Any) -> bool:
    return identifies(deed, npc_id) or npc_id in deed.get("heard", [])


NEARBY_SECONDS = 600  # people standing together have talked within minutes
TO_THE_POST_SECONDS = 3600  # someone who knows has walked to whoever keeps the peace


def _carry_news(world: dict[str, Any], now: int) -> None:
    """News moves only from a living person who has it: to whoever stands with them, then to the guards."""
    import local_places
    alive = [npc for npc in world.get("npcs", []) if isinstance(npc, dict)
             and npc.get("combat_status") != "dead" and isinstance(npc.get("id"), str)]
    for deed in world.get("flags", {}).get("deeds", []):
        if not isinstance(deed, dict) or not isinstance(deed.get("at"), int):
            continue
        carriers = [npc for npc in alive if knows(deed, npc["id"])]
        if not carriers:
            continue
        age = now - deed.get("found_at", deed["at"])
        towns = {local_places.settlement_of(world, npc.get("location")) for npc in carriers} - {None}
        for npc in alive:
            if knows(deed, npc["id"]):
                continue
            together = age >= NEARBY_SECONDS and any(c.get("location") == npc.get("location") for c in carriers)
            reported = (age >= TO_THE_POST_SECONDS and deed.get("kind") in {"killing", "arson"} and _is_armed(npc)
                        and local_places.settlement_of(world, npc.get("location")) in towns)
            if together or reported:
                deed.setdefault("heard", []).append(npc["id"])


def on_time(world: dict[str, Any], now: int) -> None:
    """The clock moved: fires go on and news moves. Only the clock calls this."""
    import world_reactions
    _tend_fires(world, now)
    world_reactions.discover(world, now)
    _carry_news(world, now)
    world_reactions.spread(world, now)


_FIRE_STAGES = (
    (0, "Tüten ateş", "Dumanı sokağa yayılan, yeni tutuşmuş bir ateş.", None),
    (600, "Yayılan yangın", "Alevler duvarları yalıyor; içerisi duman dolu.",
     "Pencerelerinden kalın bir duman taşıyor, içeride alevler yükseliyor."),
    (3600, "Yanmış kalıntılar", "Kararmış kirişler ve hâlâ sıcak kül.",
     "Kararmış kirişler, sıcak kül ve keskin bir yanık kokusu; burası artık kullanılmaz hâlde."),
)


def _way_out(world: dict[str, Any], location: Any) -> str | None:
    here = world.get("locations", {}).get(location)
    out = (here.get("exit_location_id") or here.get("parent_location_id")) if isinstance(here, dict) else None
    return out if isinstance(out, str) and out in world.get("locations", {}) else None


def _fires(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [fire for fire in world.get("flags", {}).get("fires", []) if isinstance(fire, dict)]


def _fire_feature(world: dict[str, Any], fire: dict[str, Any]) -> dict[str, Any] | None:
    return next((feature for feature in world.get("features", [])
                 if isinstance(feature, dict) and feature.get("id") == fire.get("feature_id")), None)


def _tend_fires(world: dict[str, Any], now: int) -> None:
    for fire in _fires(world):
        stage = max(index for index, row in enumerate(_FIRE_STAGES) if now - fire["lit_at"] >= row[0])
        if stage <= fire["stage"]:
            continue
        fire["stage"] = stage
        feature = _fire_feature(world, fire)
        out = _way_out(world, fire["location"])
        if out is None:  # in the open a fire has nothing to take: it burns down and stops
            if feature is not None and stage == len(_FIRE_STAGES) - 1:
                feature.update(name="Sönmüş ateş", description="Kararmış bir leke ve soğuyan kül.")
            continue
        _, name, description, place_text = _FIRE_STAGES[stage]
        if feature is not None:
            feature.update(name=name, description=description)
        world["locations"][fire["location"]]["description"] = place_text
        for npc in world.get("npcs", []):
            if isinstance(npc, dict) and npc.get("location") == fire["location"] and npc.get("combat_status") != "dead":
                npc["location"] = out


def _place_name(world: dict[str, Any], location: Any) -> str:
    place = world.get("locations", {}).get(location)
    return str(place.get("name") or "") if isinstance(place, dict) else ""


def fire_line(world: dict[str, Any]) -> str:
    """What a fire looks like from where the player stands; empty when none can be seen."""
    here = world.get("location")
    lines = []
    for fire in _fires(world):
        out = _way_out(world, fire["location"])
        if out is None or here not in (fire["location"], out):
            continue
        name = _place_name(world, fire["location"])
        if fire["stage"] == 0:
            lines.append(f"{name} tarafından ince bir duman yükseliyor.")
        elif fire["stage"] == 1:
            lines.append(f"{name} yanıyor; kalın duman göğe tırmanıyor, insanlar kapıdan uzaklaşıyor.")
        else:
            lines.append(f"{name} yanıp kül olmuş; geriye kararmış kirişler kalmış.")
    return " ".join(lines)


def is_burnt_or_burning(world: dict[str, Any], location: Any) -> bool:
    return any(fire["location"] == location and fire["stage"] >= 1 and _way_out(world, location) for fire in _fires(world))


def place_marks(world: dict[str, Any], location: Any) -> list[str]:
    """What has changed here that the player would see walking in; each shows once."""
    now = _now(world)
    people = {npc.get("id"): npc for npc in world.get("npcs", []) if isinstance(npc, dict)
              and npc.get("location") == location and npc.get("combat_status") != "dead"}
    marks = []
    for deed in world.get("flags", {}).get("deeds", []):
        if (isinstance(deed, dict) and deed.get("kind") == "theft_unseen" and not deed.get("shown")
                and deed.get("victim_id") in people and now - deed.get("at", now) >= NEARBY_SECONDS):
            deed["shown"] = True
            who = living_world.public_npc_name(people[deed["victim_id"]])
            item = str(deed.get("item") or "").casefold()
            marks.append(f"{who} ortalıkta {item} arıyor; yüzü asık." if item
                         else f"{who} durup kesesini yokluyor; yüzü asık, gözleri çevrede dolaşıyor.")
    if any(fire["location"] == location and fire["stage"] == 0 for fire in _fires(world)):
        marks.append("Yaktığın ateş köşede hâlâ için için tütüyor; duman tavana yayılıyor.")
    import world_reactions
    return marks + world_reactions.place_marks(world, location, people)


def _fire_note(world: dict[str, Any], npc: dict[str, Any]) -> str:
    import local_places
    notes = []
    for fire in _fires(world):
        out = _way_out(world, fire["location"])
        name = _place_name(world, fire["location"])
        if out is None or not name:
            continue
        if fire["stage"] < 2 and npc.get("location") in (fire["location"], out):
            notes.append(f" {name} tarafından duman yükseliyor, sen de görüyorsun.")
        elif fire["stage"] >= 2 and (local_places.settlement_of(world, npc.get("location"))
                                     == local_places.settlement_of(world, fire["location"])):
            notes.append(f" {name} yanıp kül oldu, bunu herkes biliyor.")
    return "".join(notes)


def _loss_note(world: dict[str, Any], npc: dict[str, Any], ledger: list[dict[str, Any]]) -> str:
    now = _now(world)
    missing = [deed for deed in ledger if deed.get("kind") == "theft_unseen" and deed.get("victim_id") == npc.get("id")
               and now - deed.get("at", now) >= NEARBY_SECONDS]
    if not missing:
        return ""
    item = str(missing[-1].get("item") or "").casefold()
    if item:
        return f" Bir süre önce {item} eksildiğini fark ettin; kimin aldığını bilmiyorsun. Görürsen tanırsın."
    return " Bir süre önce kesenin hafiflediğini fark ettin; kimin aldığını bilmiyorsun."


def speech_note(world: dict[str, Any], npc: dict[str, Any]) -> str:
    """What this person knows of what the player did, for their next line."""
    ledger = [deed for deed in world.get("flags", {}).get("deeds", []) if isinstance(deed, dict)]
    npc_id = npc.get("id")
    done_to_them = [deed for deed in ledger if deed.get("kind") == "assault" and deed.get("victim_id") == npc_id]
    seen = [deed["text"] for deed in ledger if npc_id in deed.get("witnesses", []) and deed not in done_to_them]
    told = [deed["text"] for deed in ledger if npc_id in deed.get("told", [])
            and npc_id not in deed.get("witnesses", [])]
    heard = [deed.get("rumour", deed["text"]) for deed in ledger
             if npc_id in deed.get("heard", []) and not identifies(deed, npc_id)]
    note = ""
    if done_to_them:
        struck = "sana vurup seni bayılttı" if any(deed.get("knocked_out") for deed in done_to_them) else "sana saldırdı"
        hurt = " Canın hâlâ yanıyor." if npc.get("current_hp", 1) < npc.get("max_hp", 0) else ""
        note = f" Karşındaki kişi {struck}; bunu sen yaşadın, unutmadın.{hurt} Bunu inkâr etme, ona göre davran."
    if seen:
        note += " Karşındaki kişinin şunları yaptığını kendi gözünle gördün: " + "; ".join(seen[-3:]) + \
            ". Ona buna göre davran; görmezden gelme."
    if told:
        note += " Karşındaki kişi sana kendi ağzıyla şunları söyledi: " + "; ".join(told[-3:]) + \
            ". Bunu unutmadın; duymamış gibi davranma."
    if heard:
        note += " Kentte şu konuşuluyor: " + heard[-1] + ". Kimin yaptığını bilmiyorsun."
        if _is_armed(npc):
            note += " Kan izi taşıyan ya da bunu söyleyen biri görürsen üstüne gidersin."
    import world_reactions
    return note + _loss_note(world, npc, ledger) + _fire_note(world, npc) + world_reactions.speech_note(world, npc)


_OWN_DEEDS = (
    (("killing",), re.compile(r"\b(?:oldurdum|geberttim|bogazladim|katil\w*\s+(?:benim|ben)\b|ben\w*\s+katil\w*)")),
    (("arson",), re.compile(r"\b(?:yaktim|kundakladim|tutusturdum|ates\w*\s+verdim)\b")),
    (("theft", "theft_unseen"), re.compile(r"\b(?:caldim|asirdim|yurttum|arakladim)\b")),
)


_ASKING = re.compile(r"\b(?:kimi|neyi|neden|niye|mi|mu|misin|musun)\b")  # "kimi öldürdüm biliyor musun" admits nothing


def _deed_meant(session, text: str, kinds: tuple[str, ...]) -> dict[str, Any] | None:
    """The real deed the words mean: the one naming its victim, else the latest, unless they name someone else."""
    world = session.world_state
    folded = fold(session, text)
    mine = [deed for deed in world.get("flags", {}).get("deeds", [])
            if isinstance(deed, dict) and deed.get("kind") in kinds]
    named = {npc.get("id") for npc in world.get("npcs", []) if isinstance(npc, dict)
             and session._entity_reference_in_text(npc.get("name", ""), folded)}
    if named:
        return next((deed for deed in reversed(mine) if deed.get("victim_id") in named), None)
    return mine[-1] if mine else None


def hear_confession(session, text: Any) -> bool:
    """The player said aloud that they did it: those here now have it from the player's own mouth.

    Only the knowing changes here. The line goes on to whoever answers it.
    """
    if not isinstance(text, str) or "?" in text:
        return False
    hearers = [npc["id"] for npc in session.active_npcs() if isinstance(npc.get("id"), str)]
    folded = fold(session, text)
    said = [kinds for kinds, pattern in _OWN_DEEDS if pattern.search(folded)]
    if not hearers or not said or _ASKING.search(folded):
        return False
    for kinds in said:
        deed = _deed_meant(session, text, kinds) or remember(session, "claim", f"“{text[:120]}”", seen=False)
        deed["told"] = sorted({*deed.get("told", []), *hearers})
    return True


def attacked(session, npc: dict[str, Any]) -> None:
    """Going for someone who meant no harm is a deed; a fight with an enemy is not."""
    if not npc.get("hostile"):
        world = session.world_state
        remember(session, "assault", f"{living_world.public_npc_name(npc)} üzerine yürüdü", victim_id=npc.get("id"))
        relationships.note(world, npc["id"], -3, f"attacked:{world.get('flags', {}).get('turn_index', 0)}")


def put_down(world: dict[str, Any], npc: dict[str, Any]) -> None:
    """The blow that knocked them out belongs to the assault they will remember."""
    for deed in reversed(deeds(world)):
        if deed.get("kind") == "assault" and deed.get("victim_id") == npc.get("id"):
            deed["knocked_out"] = True
            return


def killed(session, npc: dict[str, Any]) -> None:
    """Remember a death; who saw it answers when the turn is over."""
    world = session.world_state
    remember(session, "killing", f"{living_world.public_npc_name(npc)} öldürüldü", victim_id=npc.get("id"))
    world.setdefault("flags", {})["fresh_killing"] = True


def answer_to_killing(session, result: Any) -> None:
    """Those who saw it run or draw; the room does not go on pouring beer."""
    world = session.world_state
    flags = world.setdefault("flags", {})
    if not flags.pop("fresh_killing", None) or not isinstance(result, dict) or world.get("combat", {}).get("active"):
        return
    if session.character.get("current_hp", 0) <= 0:
        return
    import game
    present = session.active_npcs()
    armed = [npc for npc in present if game._ARMED_ROLE.search(fold(session, str(npc.get("role", ""))))]
    way_out = _way_out(world, world.get("location"))
    lines = []
    if armed:
        guard = armed[0]
        guard["hostile"] = True
        session.start_combat(guard)
        lines.append(f"{living_world.public_npc_name(guard)} silahını çekip üstüne yürüyor: “Dur orada, katil!”")
    for npc in present:
        if npc not in armed and way_out is not None:
            npc["location"] = way_out
            lines.append(f"{living_world.public_npc_name(npc)} bağırarak kapıya koşuyor.")
    if lines:
        result["narration"] = " ".join([str(result.get("narration") or ""), *lines]).strip()


LOST_SIGHT_TURNS = 4


def remembers(world: dict[str, Any], npc: Any) -> bool:
    """This person saw or was told something the player did, so a question about it is not a false claim."""
    npc_id = npc.get("id") if isinstance(npc, dict) else None
    return any(isinstance(deed, dict) and identifies(deed, npc_id)
               for deed in world.get("flags", {}).get("deeds", []))


def answer_to_known_doer(session, result: Any) -> None:
    """A guard who saw it, or heard it from the player's own mouth, goes for them on sight."""
    world = session.world_state
    if (not isinstance(result, dict) or world.get("combat", {}).get("active")
            or session.character.get("current_hp", 0) <= 0):
        return
    turn = int(world.get("flags", {}).get("turn_index", 0) or 0)
    outcome = result.get("action_result") if isinstance(result.get("action_result"), dict) else {}
    if outcome.get("action") == "flee":  # the player got away: whoever was here has lost them for a while
        for npc in session.active_npcs():
            npc["lost_sight_turn"] = turn
        return
    grave = [deed for deed in world.get("flags", {}).get("deeds", [])
             if isinstance(deed, dict) and deed.get("kind") in {"killing", "arson"}]
    guard = next((npc for npc in session.active_npcs()
                  if _is_armed(npc) and turn - npc.get("lost_sight_turn", -LOST_SIGHT_TURNS) >= LOST_SIGHT_TURNS
                  and any(identifies(deed, npc.get("id")) for deed in grave)), None)
    if guard is None:
        return
    guard["hostile"] = True
    session.start_combat(guard)
    named = "katil" if any(deed["kind"] == "killing" and identifies(deed, guard.get("id")) for deed in grave) else "kundakçı"
    line = f"{living_world.public_npc_name(guard)} silahını çekip üstüne yürüyor: “Dur orada, {named}!”"
    result["narration"] = " ".join([str(result.get("narration") or ""), line]).strip()


def _pick_line(session, npc: dict[str, Any]) -> str:
    name = living_world.public_npc_name(npc)
    return session.rng.choice(_CAUGHT).format(n=name)


def _check(session, skill: str, dc: int) -> dict[str, Any]:
    character = session.character
    return session.perform_skill_check(
        skill, dc, character["modifiers"], character.get("proficient_skills") or [],
        character.get("proficiency_bonus") or 2,
        expertise_skills=character.get("expertise_skills") or (),
    )


def _thing_named(folded: str) -> str | None:
    return next((label for stem, label in _THINGS if stem in folded), None)


def _hand_to_whom(session, text: str) -> dict[str, Any] | None:
    import combat_lifecycle
    people = combat_lifecycle.pointed_targets(session, text)
    if len(people) == 1:
        return people[0]
    world = session.world_state
    flags = world.get("flags", {})
    present = session.active_npcs()
    active = next((npc for npc in present if npc.get("id") == flags.get("active_npc_id")), None)
    if active is not None:
        return active
    return present[0] if len(present) == 1 else None


def _reply(session, narration: str, action: str, status: str, check: dict[str, Any] | None,
           changes: list[str], **extra: Any) -> dict[str, Any]:
    world = session.world_state
    flags = world.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    result = {"action": action, "status": status, "state_changes": changes, "direct_response": narration, **extra}
    if check is not None:
        import game
        result = {**check, **result}  # the whole roll, so the player sees the dice like any other check
        result.update(outcome=game._skill_result_category(check["result"]),
                      success=check["result"] == "BAŞARILI", skill=check.get("skill"), dc=check.get("dc"),
                      roll=check.get("roll"), total=check.get("total"), check_result=check["result"])
    else:
        result["success"] = True
    return {"messages": session.messages, "narration": narration, "model_calls": 0, "action_result": result}


def _steal_dc(session, folded: str, watcher: dict[str, Any] | None) -> int:
    """No one there or a turned back is the easy roll, a face looking at you the middling one; a guard is one step more."""
    import game
    easy, medium, hard = (game.DIFFICULTY_DC[name] for name in ("easy", "medium", "hard"))
    if watcher is None:
        return easy
    armed = game._ARMED_ROLE.search(fold(session, str(watcher.get("role", ""))))
    if _DISTRACTED.search(folded):
        return medium if armed else easy
    return hard if armed else medium


TILL_REFILLS_SECONDS = 24 * 3600


def _coin_to_take(world: dict[str, Any], person: dict[str, Any] | None) -> bool:
    """Coin is someone's: a person at hand, or the till of a place with a door, once a day. Open ground holds none."""
    if person is not None:
        return True
    import local_places
    here, now = world.get("location"), _now(world)
    indoors = _way_out(world, here) is not None and local_places.settlement_of(world, here) != here
    return indoors and not any(
        deed.get("till") and deed.get("location") == here and now - deed.get("at", now) < TILL_REFILLS_SECONDS
        for deed in deeds(world))


def _steal(session, text: str) -> dict[str, Any]:
    folded = fold(session, text)
    victim = _hand_to_whom(session, text)
    present = session.active_npcs()
    watcher = victim or (present[0] if present else None)  # with several in the room, somebody sees the hand
    check = _check(session, "Sleight of Hand", _steal_dc(session, folded, watcher))
    world = session.world_state
    thing = _thing_named(folded)
    if check["result"] != "BAŞARILI":
        if watcher is None:
            return _reply(session, session.rng.choice(_NOTHING_THERE), "theft", "failed", check, [])
        relationships.note(world, watcher["id"], -3, f"caught_stealing:{world.get('flags', {}).get('turn_index', 0)}")
        remember(session, "theft", "seni soymaya kalktı", victim_id=watcher["id"])["rumour"] = (
            f"{living_world.public_npc_name(watcher)} soyulmak istenmiş")
        return _reply(session, _pick_line(session, watcher), "theft", "caught", check,
                      ["relationships"], npc_id=watcher["id"])
    if thing is None and not _coin_to_take(world, victim or watcher):
        return _reply(session, session.rng.choice(_NOTHING_THERE), "theft", "empty", check, [])
    if thing is None:
        coins = session.rng.randint(5, 40)
        wallets = world.setdefault("currency", {})
        wallets["player"] = wallets.get("player", 0) + coins
        if victim is not None:
            remember(session, "theft_unseen", f"{living_world.public_npc_name(victim)} soyuldu",
                     victim_id=victim["id"], seen=False)
        else:
            remember(session, "theft_unseen", f"{_place_name(world, world.get('location'))} içinden para eksildi",
                     seen=False)["till"] = True
        narration = f"Parmakların sessizce işini görüyor: kesende {coins} bakır daha var. Kimse fark etmedi."
        return _reply(session, narration, "theft", "stolen", check, ["currency"], coins_cp=coins)
    world.setdefault("inventory", []).append(thing)
    if victim is not None:
        remember(session, "theft_unseen", f"{living_world.public_npc_name(victim)} elinden {thing.lower()} eksildi",
                 victim_id=victim["id"], seen=False)["item"] = thing
    narration = f"Elin hızlı: {thing.lower()} artık sende, kimse bakmıyor."
    return _reply(session, narration, "theft", "stolen", check, ["player.inventory"], item=thing)


def _burn(session) -> dict[str, Any]:
    check = _check(session, "Survival", 10)
    present = session.active_npcs()
    if check["result"] != "BAŞARILI":
        return _reply(session, "Kıvılcım bir türlü tutmuyor; elinde yalnız is kokusu kalıyor.",
                      "arson", "failed", check, [])
    world = session.world_state
    feature = session.create_local_feature({
        "name": _FIRE_STAGES[0][1], "description": _FIRE_STAGES[0][2], "location": world.get("location"),
    })
    if isinstance(feature, dict) and not any(fire["location"] == world.get("location") for fire in _fires(world)):
        world.setdefault("flags", {}).setdefault("fires", []).append(
            {"location": world.get("location"), "lit_at": _now(world), "stage": 0, "feature_id": feature.get("id")})
    remember(session, "arson", f"{_place_name(world, world.get('location'))} içinde ateş yaktı")
    narration = "Kıvılcım tutuyor; duman yükselmeye, ardından alev yalamaya başlıyor."
    if present:
        narration += f" {living_world.public_npc_name(present[0])} sana dönüp bağırıyor: “Deli misin sen?”"
    return _reply(session, narration, "arson", "lit", check, ["features"])


_POCKETS = re.compile(r"\b(?:ustunu|uzerini|cebini|ceplerini|kesesini)\b.*\b(?:ar\w*|al\w*|bak\w*|yokl\w*)|\bsoyuyorum\b")
_CORPSE = re.compile(r"\b(?:ceset\w*|cesed\w*|olunun|oluyu|oluye)\b")
_CORPSE_VERB = re.compile(r"\b(?:ar[ai]\w*|al\w*|bak\w*|yokl\w*|incele\w*|soy\w*|karistir\w*)")
_PRICES = shop_trade.PRICES  # one list, said and charged
_BUY = re.compile(r"\b(?:alayim|alirim|aliyorum|ver|versene|getir|getirsene|istiyorum|isterim)\b")
_SERVER = shop_trade.SERVER  # one rule for who serves


def _search_body(session, text: str) -> dict[str, Any] | None:
    import fallen
    folded = fold(session, text)
    corpse = bool(_CORPSE.search(folded) and _CORPSE_VERB.search(folded))
    if not corpse and not _POCKETS.search(folded):
        return None
    world = session.world_state
    bodies = fallen.here(world)
    named = fallen.named_in(session, text, bodies)
    if named is None:
        far = fallen.named_elsewhere(session, text)
        if far is not None:
            return _reply(session, fallen.lies_elsewhere(world, far), "loot", "body_elsewhere", None, [])
    if not bodies or (not corpse and named is None
                      and any(session.named_by_sight(npc, folded) for npc in session.active_npcs())):
        return None
    body = named or next((npc for npc in bodies if not npc.get("searched")), bodies[0])
    who = living_world.public_npc_name(body)
    if body.get("searched"):
        return _reply(session, f"{who} üzerinde alınacak başka bir şey kalmamış.", "loot", "already_searched", None, [])
    body["searched"] = True
    coins = session.rng.randint(0, 30)
    wallets = session.world_state.setdefault("currency", {})
    wallets["player"] = wallets.get("player", 0) + coins
    narration = (f"{who} üzerinde {coins} bakır buluyorsun; artık senin." if coins
                 else f"{who} üzerinde işe yarar bir şey çıkmıyor.")
    return _reply(session, narration, "loot", "searched", None, ["currency"], coins_cp=coins)


def settle_coin_labels(world: dict[str, Any]) -> None:
    """"8 Altın" written in the pack becomes real money the first time money is spent."""
    kept = []
    wallets = world.setdefault("currency", {})
    for item in world.get("inventory", []):
        name = item.get("name") if isinstance(item, dict) else item
        match = re.fullmatch(r"(\d+) (?:Altın|GP)", str(name))
        if match:
            wallets["player"] = wallets.get("player", 0) + int(match.group(1)) * 100
        else:
            kept.append(item)
    world["inventory"] = kept


_ROOM = re.compile(r"\boda(?:y[ai])?\b")
_WALKS = re.compile(r"\b(?!gece)(?:gid|git|gir|gec|yuru|yaklas)\w*")
_ROOM_ASK = re.compile(r"\b(?:tut\w*|kirala\w*|ver\w*|alayim|alirim|aliyorum|istiyorum|isterim)\b")
_PRICE_ASKED = re.compile(r"\b(?:ne kadar|kac\w*|fiyat\w*|var mi|var midir)\b")
_ROOM_PRICE = 50  # a modest inn stay, 5 silver a night


def room_price(world: dict[str, Any], npc: dict[str, Any] | None) -> int:
    """What a night's room costs with whoever serves here; the house price until a haggled cut is written."""
    return _ROOM_PRICE


def room_note(npc: dict[str, Any], text: Any) -> str:
    """Only when rooms are what is being talked of: otherwise whoever serves would sell a bed in every reply."""
    if not _SERVER.search(living_world.normalize_text(npc.get("role"))) or not _ROOM.search(living_world.normalize_text(text)):
        return ""
    return f"Burada kalacak oda verilir, gecelik {_ROOM_PRICE // 10} gümüş; oda yok deme."


def _priced_in(folded: str) -> tuple[str, str, int] | None:
    """The thing on the list the words name, as a word of its own: 'biraz' and 'birader' are no beer."""
    return shop_trade.priced_in(folded)


def price_note(npc: dict[str, Any], text: Any) -> str:
    """What whoever serves says a thing costs is what the purse will pay for it: one list, said and charged."""
    folded = living_world.normalize_text(text)
    if not _SERVER.search(living_world.normalize_text(npc.get("role"))) or not (
            _priced_in(folded) or _PRICE_ASKED.search(folded)):
        return ""
    prices = ", ".join(f"{line['label']} {line['unit_cp']} bakır" for line in shop_trade.goods(None, npc))
    return f"Burada fiyatlar şöyle: {prices}. Fiyat sorulursa bunları söyle, başka fiyat söyleme."
_ROOM_DAY = 24 * 3600


def _server_here(session) -> dict[str, Any] | None:
    return next((npc for npc in session.active_npcs() if _SERVER.search(fold(session, str(npc.get("role", ""))))), None)


def _wants_the_bed(folded: str) -> bool:
    import timed_gameplay
    return bool(_ROOM_ASK.search(folded) or timed_gameplay._SLEEPING.search(folded))


COIN_NOT_TENDERED = "Uzattığın para hesaba katılmadı; kesende kalıyor."


def held_out_coin(session, purpose: Literal["room", "goods"]) -> int | None:
    """Coin held out with this line for a room or the counter, taken off the hand so it can never turn into a gift card.

    Under this turn's money decision the coin is the decision's: only the operation it names gets it, once
    (`money_owner.claim`), and coin meant for something else stays in hand for its own owner. With no decision (no
    front reading) the coin in hand is read as before.
    """
    import money_owner
    if money_owner.current(session) is not None:
        coin = money_owner.claim(session, purpose)
        if coin is not None:
            session._coin_paid = None
            session._handed_note = None
        return coin
    paid = getattr(session, "_coin_paid", None)
    session._coin_paid = None
    session._handed_note = None
    if not paid:
        return None
    amount = paid[0]
    return amount if type(amount) is int and amount > 0 else None


def _tender_or_none(world: dict[str, Any], amount: int | None, price: int, purse: int) -> int | None:
    """C1: the coin held out pays the price when price <= coin <= purse; otherwise it is ignored with a note."""
    return amount if amount is not None and price <= amount <= purse else None


def take_room(session, text: str) -> dict[str, Any] | None:
    """A night's room asked for: whoever serves here opens the room card; nothing is paid by the words.

    The price is the house's own (_ROOM_PRICE) and, when the card is confirmed, it goes to nobody: the inn keeps no
    purse, the sink total is kept in the ledger (D5). A room the player already holds here is just shown; a refusal
    or a short purse opens no card. Coin held out with the line is the card's tender when it covers the price and
    the purse holds it, and is ignored with a note otherwise.

    Returns {"line", "paid": 0, "room", "status", "reason_code", "offer_id", "coin_seen"}; "room" is True only for a
    room already held (status "held").

    Under this turn's money decision the words are not read (design §12 D29), whoever calls this (the walk to bed
    in game._sleep_after_walk too): a `room` decision opens the card with the person it names, as `decided` does,
    and any other decision (gift, tip, a past payment, a bribe, unclear, goods) opens none.
    """
    import money_owner
    decision = money_owner.current(session)
    if decision is not None:
        server = _decision_server(session, decision) if decision.kind == "room" else None
        return None if server is None else _open_room(session, server)
    folded = fold(session, text)
    server = _server_here(session)
    if server is None or not (_ROOM.search(folded) and _wants_the_bed(folded)):
        return None
    return _open_room(session, server)


def _open_room(session, server: dict[str, Any]) -> dict[str, Any]:
    """The room card with whoever serves, as `take_room` describes it, whatever words asked for it."""
    import economic_actions
    import world_reactions
    world = session.world_state
    who = living_world.public_npc_name(server)
    coin = held_out_coin(session, "room")
    note = f" {COIN_NOT_TENDERED}" if coin is not None else ""
    answer = {"paid": 0, "room": False, "reason_code": None, "offer_id": None, "coin_seen": coin is not None}
    if world_reactions.refuses(world, server):
        return {**answer, "line": world_reactions.refusal_line(server) + note, "status": "refused",
                "reason_code": "npc_refuses"}
    now = world.get("campaign_time", {}).get("elapsed_seconds", 0)
    held = (world.get("flags") or {}).get("inn_room")
    if isinstance(held, dict) and held.get("place") == world.get("location") and now < held.get("until", 0):
        return {**answer, "line": f"{who} başıyla merdivenleri gösteriyor. “Odan yukarıda, duruyor.”{note}",
                "room": True, "status": "held"}
    tender = _tender_or_none(world, coin, _ROOM_PRICE, economic_actions.wallet_total_cp(world))
    if tender is not None:
        note = ""
    prepared = economic_actions.prepare_from_turn(
        session, economic_actions.turn_proposal("room", str(server.get("id")), tender_cp=tender))
    if prepared.status == "prepared" and prepared.offer is not None:
        session._set_scene_active_npc(server, world.get("flags", {}).get("turn_index", 0))
        paid_with = f" Uzattığın {tender} bakır bu kartın parası sayılıyor." if tender is not None else ""
        return {**answer, "status": "offered", "offer_id": prepared.offer.offer_id,
                "line": (f"{who} başıyla merdivenleri gösteriyor. “Gecelik {_ROOM_PRICE} bakır.” "
                         f"{prepared.public_message}{paid_with}{note}")}
    if prepared.reason_code == "purse_below_base":
        return {**answer, "status": "clarification", "reason_code": prepared.reason_code,
                "line": f"{who} kesene bakıp başını sallıyor. “Parası yoksa oda da yok.”{note}"}
    if prepared.status == "refused":
        return {**answer, "status": "refused", "reason_code": prepared.reason_code,
                "line": world_reactions.refusal_line(server) + note}
    return {**answer, "status": "clarification", "reason_code": prepared.reason_code,
            "line": prepared.public_message + note}


_ROOM_RECEIPT = {"held": "rented", "offered": "offered", "refused": "refused"}


def _room_reply(session, room: dict[str, Any]) -> dict[str, Any]:
    """The receipt of a room line: a card asked for, a room held, a no. No coin moved, so none is in the changes."""
    status = _ROOM_RECEIPT.get(room["status"]) or ("no_money" if room.get("reason_code") == "purse_below_base"
                                                    else "clarification")
    reply = _reply(session, room["line"], "lodging", status, None, [], price_cp=0, offer_id=room.get("offer_id"))
    if room.get("coin_seen"):
        reply["action_result"]["coin_seen_by"] = "room"
    return reply


def _room_asked(session, text: str) -> dict[str, Any] | None:
    """'Oda ne kadar?' is answered with what a room really costs, by whoever serves; a bed asked for in the same line opens the room card."""
    folded = fold(session, text)
    server = _server_here(session)
    if server is None or not _ROOM.search(folded) or _WALKS.search(folded):  # 'odaya giriyorum' is a walk
        return None
    if _wants_the_bed(folded):
        return _room_reply(session, take_room(session, text))
    if "?" not in text and not _PRICE_ASKED.search(folded):
        return None
    import world_reactions
    if world_reactions.refuses(session.world_state, server):
        return _reply(session, world_reactions.refusal_line(server), "lodging", "refused", None, [])
    who = living_world.public_npc_name(server)
    return _reply(session, f"{who} başıyla merdivenleri gösteriyor. “Gecelik {_ROOM_PRICE // 10} gümüş; yukarıda boş oda var.”",
                  "lodging", "quoted", None, [], npc_id=server.get("id"))


def _buy(session, text: str) -> dict[str, Any] | None:
    folded = fold(session, text)
    if not _WALKS.search(folded):
        room = take_room(session, text)
        if room is not None:
            return _room_reply(session, room)
    return shop_offer(session, text)


def _coin_seen(reply: dict[str, Any], coin: int | None) -> dict[str, Any]:
    if coin is not None:
        reply["action_result"]["coin_seen_by"] = "purchase"
    return reply


def _with_tender(session, server: dict[str, Any], key: str, coin: int | None) -> dict[str, Any]:
    """Open the counter's offer; coin held out is its tender when price <= coin <= purse, and is ignored otherwise.

    When this turn's money decision bought these goods from this person and kept the change, the offer also carries
    the decision's tip (`tip_cp`, Python's own figure: the coin held out over the price; design §3b, §11 D1), and the
    line tells the price, the tip and the one total a confirmation pays. The tip is written only when the coin held
    out is exactly that total.
    """
    world = session.world_state
    quoted = shop_trade.quote(world, server["id"], key, 1)
    tender = _tender_or_none(world, coin, quoted["total_cp"], quoted["purse_cp"]) if quoted is not None else None
    tip = _decided_tip(session, server, key, tender, quoted)
    reply = _open_offer(session, server, key)
    if tender is not None:
        world["flags"]["counter_offer_v1"]["tender_cp"] = tender
    elif coin is not None:
        _say_too(reply, COIN_NOT_TENDERED)
    if tip:
        world["flags"]["counter_offer_v1"]["tip_cp"] = tip
        label = quoted["label"][:1].upper() + quoted["label"][1:]
        _say_too(reply, f"{label} {quoted['unit_cp']} bakır + bahşiş {tip} bakır = {tender} bakır; "
                        f"onaylarsan {tender} bakır geçer.")
    return _coin_seen(reply, coin)


def _say_too(reply: dict[str, Any], text: str) -> None:
    reply["narration"] = f"{reply['narration']} {text}"
    reply["action_result"]["direct_response"] = reply["narration"]


def _decided_tip(session, server: dict[str, Any], key: str, tender: int | None, quoted: dict[str, Any] | None) -> int:
    """The tip this turn's money decision kept for these goods with this person, when the coin held out is the price
    and that tip; 0 otherwise. The model never gives the figure: the money owner worked it out from the coin."""
    import money_owner
    decision = money_owner.current(session)
    if (decision is None or decision.kind != "goods" or decision.npc_id != str(server.get("id"))
            or decision.goods_key != key or quoted is None or tender is None):
        return 0
    tip = decision.tip_cp
    return tip if type(tip) is int and tip > 0 and tender == quoted["total_cp"] + tip else 0


_COUNTER_TIPS = ("tip_cp", "tip_after_cp")  # the panel-"yes" tip on the offer, and the panel-"no" waiting tip (D34)


def drop_counter_tip(world: dict[str, Any], npc_id: str) -> bool:
    """Take the tip off this person's counter offer (a tip they declined, design §3b item 1); True if one was there.

    Both the offer's own tip and a tip waiting for after the goods go. The goods' offer stays, and the coin it takes
    is the price: a tender above the price is brought down to it, so no part of the dropped tip is paid or counted.
    """
    opened = (world.get("flags") or {}).get("counter_offer_v1")
    if not isinstance(opened, dict) or opened.get("npc_id") != npc_id:
        return False
    dropped = [field for field in _COUNTER_TIPS if field in opened]
    for field in dropped:
        opened.pop(field)
    if not dropped or "tender_cp" not in opened:
        return bool(dropped)
    quoted = shop_trade.quote(world, str(npc_id), str(opened.get("key")), 1)
    tender = opened["tender_cp"]
    if quoted is None or type(tender) is not int:
        opened.pop("tender_cp")
    elif tender > quoted["total_cp"]:
        opened["tender_cp"] = quoted["total_cp"]
    return True


def repair_counter_tip(world: dict[str, Any]) -> list[str]:
    """Drop a counter offer's tip that is not a whole number of copper of at least 1; the offer itself stays.

    Run on load (design §11 D7): a broken tip never fails the save, it is only left out, and each one is logged.
    """
    import economic_actions
    opened = (world.get("flags") or {}).get("counter_offer_v1") if isinstance(world, dict) else None
    if not isinstance(opened, dict):
        return []
    dropped = []
    for field in _COUNTER_TIPS:
        value = opened.get(field)
        if field in opened and not (type(value) is int and 1 <= value <= economic_actions.MAX_CP):
            opened.pop(field)
            dropped.append(f"counter_offer_v1.{field}")
    for name in dropped:
        logger.warning("repair_counter_tip dropped %s", name)
    return dropped


def shop_offer(session, text: str, server: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """A line that wants something on the list opens the counter's offer. Words move no coin and no goods:
    only the one counter trade (shop_trade.commit) does, at the price this offer shows.

    Under this turn's money decision the words are not read: the decision alone says which offer opens (`decided`),
    also for a line said straight to whoever serves."""
    import money_owner
    if money_owner.current(session) is not None:
        return decided(session)
    folded = fold(session, text)
    wanted = shop_trade.priced_in(folded)
    server = server if server is not None else _server_here(session)
    walking = _WALKS.search(folded)  # the order follows the walk
    if wanted is None or server is None or walking or "?" in text or not _BUY.search(folded):
        return None
    return _counter_offer(session, server, wanted[0])


def _counter_offer(session, server: dict[str, Any], key: str) -> dict[str, Any]:
    """The counter's offer for these goods with whoever serves, or their refusal; coin held out is read as tender."""
    world = session.world_state
    # Coin put down with the order is no payment: it stays in the purse, and nobody is told it changed hands.
    # It is read before it is cleared, as the offer's tender when it covers the price (C1).
    coin = held_out_coin(session, "goods")
    import world_reactions
    if world_reactions.refuses(world, server):
        return _coin_seen(_reply(session, world_reactions.refusal_line(server), "shop_offer", "refused", None, [],
                                 npc_id=server.get("id")), coin)
    return _with_tender(session, server, key, coin)


def decided(session) -> dict[str, Any] | None:
    """The offer this turn's money decision names, opened whatever the words say (design §12 D29).

    A `room` decision opens the room card with the person it names and a `goods` decision the counter's offer for
    those goods, whether the model or the engine's structure made it; the coin held out is their tender only through
    `money_owner.claim`, and with no coin they open with none. Any other decision (gift, tip, a past payment, a bribe,
    unclear) opens neither: None, and no word is read for it. None too when there is no decision.
    """
    import money_owner
    decision = money_owner.current(session)
    if decision is None or decision.kind not in ("room", "goods"):
        return None
    server = _decision_server(session, decision)
    if server is None:
        return None
    if decision.kind == "room":
        return _room_reply(session, _open_room(session, server))
    return _counter_offer(session, server, decision.goods_key)


def _decision_server(session, decision) -> dict[str, Any] | None:
    """The person a money decision names, when they are here."""
    return next((npc for npc in session.active_npcs() if npc.get("id") == decision.npc_id), None)


def offer_still_open(world: dict[str, Any], npc: Any) -> dict[str, Any] | None:
    """The offer this person opened a line or two ago, while no counter trade has settled since."""
    opened = (world.get("flags") or {}).get("counter_offer_v1")
    if not isinstance(opened, dict) or not isinstance(npc, dict) or opened.get("npc_id") != npc.get("id"):
        return None
    turn, number = opened.get("turn"), opened.get("seq")
    if type(turn) is not int or number != shop_trade.seq(world):
        return None
    return opened if 0 <= world.get("flags", {}).get("turn_index", 0) - turn <= 2 else None


def standing_offer(session, server: Any) -> dict[str, Any] | None:
    """Coin held out for an open offer pays nothing: the offer stands, read fresh, and only the counter trade takes it."""
    import world_reactions
    opened = offer_still_open(session.world_state, server)
    if (opened is None or not shop_trade.is_vendor(session.world_state, server)
            or world_reactions.refuses(session.world_state, server)):
        return None
    return _with_tender(session, server, opened["key"], held_out_coin(session, "goods"))


def _open_offer(session, server: dict[str, Any], key: str) -> dict[str, Any]:
    world = session.world_state
    offer = shop_trade.quote(world, server["id"], key, 1)
    session._set_scene_active_npc(server, world.get("flags", {}).get("turn_index", 0))
    world["flags"]["served_turn"] = world["flags"].get("turn_index", 0)  # 'duydun mu birşey' next is for them
    world["flags"]["counter_offer_v1"] = {"npc_id": server["id"], "key": key, "seq": offer["seq"],
                                          "turn": world["flags"]["served_turn"]}
    label = offer["label"]
    who = living_world.public_npc_name(server)
    line = f"{who} tezgâha dayanıyor. “{label[:1].upper()}{label[1:]} {offer['unit_cp']} bakır. Kaç tane?”"
    return _reply(session, line, "shop_offer", "offer_open", None, [], offer=offer, npc_id=server["id"])


def _can_be_done(session, text: Any) -> bool:
    """The reading names the deed; a line that only asks about it does nothing, whatever the reading says."""
    return isinstance(text, str) and "?" not in text and not _ASKS.search(fold(session, text))


def resolve(session, text: Any, deed: str | None = None) -> dict[str, Any] | None:
    """deed is what the front reading found, the empty text for nothing; None means no reading, so the words decide.

    A money decision this turn owns the room and the counter (design §12 D29): its room or goods offer opens whatever
    the words say, and any other decision skips both. The room and purchase words are read only with no decision.
    """
    import money_owner
    if isinstance(text, str) and text.lstrip().startswith("/"):
        return None  # a typed command has its own owner; the word lists never read it
    if isinstance(text, str):
        if money_owner.current(session) is not None:
            settled = decided(session) or (_search_body(session, text) if "?" not in text else None)
        else:
            settled = _room_asked(session, text) or ((_search_body(session, text) or _buy(session, text))
                                                     if "?" not in text else None)
        if settled is not None:
            return settled
    if is_theft(session, text) if deed is None else deed == "steal" and _can_be_done(session, text) and (
            not _NOT_STOLEN.search(fold(session, text))):
        return _steal(session, text)
    if is_arson(session, text) if deed is None else deed == "burn" and _can_be_done(session, text):
        return _burn(session)
    return None
