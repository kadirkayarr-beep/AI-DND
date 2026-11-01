"""What a free hand does when no other owner takes it: stealing and setting fires.

The dice and the state stay in Python and the attempt always happens: it can
fail, it can be seen, but it is never turned down. What people saw is kept in
one short ledger, so the next person who hears of it can act on it.
"""

from __future__ import annotations

import re
from typing import Any

import living_world
import relationships

MAX_DEEDS = 24
_STEAL = re.compile(
    r"\b(?:asir\w*|yurut\w*|yagmal\w*|calacag\w*|kapip\b|kistir\w*|el at\w*|arakl\w*|"
    r"keserek al\w*|kesip al\w*|cekip al\w*|sessizce cek\w*|indirip\b.*\bsakl\w*|cal(?:iyorum|ip|ayim|dim))"
)
# "Zili çalıyorum", "kapıyı çalıyorum", "flüt çalıyorum" are not theft.
_NOT_STOLEN = re.compile(
    r"\b(?:(?:zil|kapi|flut|ud|davul|gong|tokmak|sarki|keman|lavta|melodi|kopuz|saz)\w*|can[ia]?)\b.*\bcal(?:iyorum|ip)"
)
_DISTRACTED = re.compile(r"\w+(?:ken|arken|erken)\b")
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
    seen = [deed["text"] for deed in ledger if npc_id in deed.get("witnesses", [])]
    told = [deed["text"] for deed in ledger if npc_id in deed.get("told", [])
            and npc_id not in deed.get("witnesses", [])]
    heard = [deed.get("rumour", deed["text"]) for deed in ledger
             if npc_id in deed.get("heard", []) and not identifies(deed, npc_id)]
    note = ""
    if seen:
        note = " Karşındaki kişinin şunları yaptığını kendi gözünle gördün: " + "; ".join(seen[-3:]) + \
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
        remember(session, "assault", f"{living_world.public_npc_name(npc)} üzerine yürüdü", victim_id=npc.get("id"))


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
        result.update(success=check["result"] == "BAŞARILI", skill=check.get("skill"), dc=check.get("dc"),
                      roll=check.get("roll"), total=check.get("total"), check_result=check["result"])
    else:
        result["success"] = True
    return {"messages": session.messages, "narration": narration, "model_calls": 0, "action_result": result}


def _steal(session, text: str) -> dict[str, Any]:
    folded = fold(session, text)
    victim = _hand_to_whom(session, text)
    import game
    armed = victim is not None and game._ARMED_ROLE.search(fold(session, str(victim.get("role", ""))))
    dc = (10 if _DISTRACTED.search(folded) or victim is None else 13) + (2 if armed else 0)
    check = _check(session, "Sleight of Hand", dc)
    world = session.world_state
    thing = _thing_named(folded)
    if check["result"] != "BAŞARILI":
        if victim is None:
            return _reply(session, "Elin tam uzanacakken duraksıyorsun; bu sefer fırsat geçip gidiyor.",
                          "theft", "failed", check, [])
        relationships.note(world, victim["id"], -3, f"caught_stealing:{world.get('flags', {}).get('turn_index', 0)}")
        remember(session, "theft", "seni soymaya kalktı", victim_id=victim["id"])["rumour"] = (
            f"{living_world.public_npc_name(victim)} soyulmak istenmiş")
        return _reply(session, _pick_line(session, victim), "theft", "caught", check,
                      ["relationships"], npc_id=victim["id"])
    if thing is None and victim is not None:
        coins = session.rng.randint(5, 40)
        wallets = world.setdefault("currency", {})
        wallets["player"] = wallets.get("player", 0) + coins
        remember(session, "theft_unseen", f"{living_world.public_npc_name(victim)} soyuldu",
                 victim_id=victim["id"], seen=False)
        narration = f"Parmakların sessizce işini görüyor: kesende {coins} bakır daha var. Kimse fark etmedi."
        return _reply(session, narration, "theft", "stolen", check, ["currency"], coins_cp=coins)
    label = thing or "Küçük bir ganimet"
    world.setdefault("inventory", []).append(label)
    if victim is not None:
        remember(session, "theft_unseen", f"{living_world.public_npc_name(victim)} elinden {label.lower()} eksildi",
                 victim_id=victim["id"], seen=False)["item"] = label
    narration = f"Elin hızlı: {label.lower()} artık sende, kimse bakmıyor."
    return _reply(session, narration, "theft", "stolen", check, ["player.inventory"], item=label)


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
_PRICES = (("bira", "bira", 4), ("sarap", "şarap", 20), ("yemek", "tabak yemek", 30))
_BUY = re.compile(r"\b(?:alayim|alirim|aliyorum|ver|versene|getir|getirsene|istiyorum|isterim)\b")
_SERVER = re.compile(r"\b(?:barmen|hanci|meyhaneci|garson|satici|asci)")


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
_ROOM_ASK = re.compile(r"\b(?:tut\w*|kirala\w*|ver\w*|alayim|alirim|aliyorum|istiyorum|isterim)\b")
_ROOM_PRICE = 50  # a modest inn stay, 5 silver a night
_ROOM_DAY = 24 * 3600


def take_room(session, text: str) -> dict[str, Any] | None:
    """A night's room is paid to whoever serves here; a refusal leaves the player on their feet."""
    folded = fold(session, text)
    server = next((npc for npc in session.active_npcs()
                   if _SERVER.search(fold(session, str(npc.get("role", ""))))), None)
    if server is None or not (_ROOM.search(folded) and _ROOM_ASK.search(folded)):
        return None
    world = session.world_state
    who = living_world.public_npc_name(server)
    import world_reactions
    if world_reactions.refuses(world, server):
        return {"line": world_reactions.refusal_line(server), "paid": 0, "room": False}
    now = world.get("campaign_time", {}).get("elapsed_seconds", 0)
    held = world.setdefault("flags", {}).get("inn_room")
    if isinstance(held, dict) and held.get("place") == world.get("location") and now < held.get("until", 0):
        return {"line": f"{who} başıyla merdivenleri gösteriyor. “Odan yukarıda, duruyor.”", "paid": 0, "room": True}
    settle_coin_labels(world)
    wallets = world.setdefault("currency", {})
    if wallets.get("player", 0) < _ROOM_PRICE:
        return {"line": f"{who} kesene bakıp başını sallıyor. “Parası yoksa oda da yok.”", "paid": 0, "room": False}
    wallets["player"] -= _ROOM_PRICE
    session._set_scene_active_npc(server, world["flags"].get("turn_index", 0))
    world["flags"]["inn_room"] = {"place": world.get("location"), "until": now + _ROOM_DAY}
    return {"line": f"{who} başıyla merdivenleri gösteriyor; {_ROOM_PRICE} bakır kesenden tezgâha geçiyor.",
            "paid": _ROOM_PRICE, "room": True}


def _buy(session, text: str) -> dict[str, Any] | None:
    folded = fold(session, text)
    if not re.search(r"\b(?:gid|git|gir|gec|yuru|yaklas)\w*", folded):
        room = take_room(session, text)
        if room is not None:
            return _reply(session, room["line"], "lodging", "rented" if room["room"] else "no_money", None,
                          ["currency"] if room["paid"] else [], price_cp=room["paid"])
    wanted = next((item for item in _PRICES if item[0] in folded), None)
    server = next((npc for npc in session.active_npcs()
                   if _SERVER.search(fold(session, str(npc.get("role", ""))))), None)
    walking = re.search(r"\b(?:gid|git|gir|gec|yuru|yaklas)\w*", folded)  # the order follows the walk
    if wanted is None or server is None or walking or not _BUY.search(folded):
        return None
    world = session.world_state
    import world_reactions
    if world_reactions.refuses(world, server):
        return _reply(session, world_reactions.refusal_line(server), "purchase", "refused", None, [])
    settle_coin_labels(world)
    wallets = world.setdefault("currency", {})
    _, label, price = wanted
    who = living_world.public_npc_name(server)
    if wallets.get("player", 0) < price:
        return _reply(session, f"{who} kesene bakıp başını sallıyor. “Parası yoksa {label} da yok.”",
                      "purchase", "no_money", None, [])
    wallets["player"] -= price
    session._set_scene_active_npc(server, world.get("flags", {}).get("turn_index", 0))
    world["flags"]["served_turn"] = world["flags"].get("turn_index", 0)
    return _reply(session, f"{who} önüne bir {label} bırakıyor; {price} bakır kesenden tezgâha geçiyor.",
                  "purchase", "bought", None, ["currency"], price_cp=price)


def resolve(session, text: Any) -> dict[str, Any] | None:
    if isinstance(text, str) and "?" not in text:
        settled = _search_body(session, text) or _buy(session, text)
        if settled is not None:
            return settled
    if is_theft(session, text):
        return _steal(session, text)
    if is_arson(session, text):
        return _burn(session)
    return None
