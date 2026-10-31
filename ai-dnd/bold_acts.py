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

MAX_DEEDS = 12
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


def remember(session, kind: str, text: str, *, victim_id: str | None = None) -> None:
    """What was done, and who was standing there to see it."""
    world = session.world_state
    witnesses = [npc["id"] for npc in session.active_npcs() if isinstance(npc.get("id"), str)]
    ledger = deeds(world)
    ledger.append({
        "kind": kind, "text": text[:160], "location": world.get("location"), "victim_id": victim_id,
        "witnesses": witnesses, "turn": int(world.get("flags", {}).get("turn_index", 0) or 0),
    })
    del ledger[:-MAX_DEEDS]


def speech_note(world: dict[str, Any], npc: dict[str, Any]) -> str:
    """What this person saw the player do, for their next line."""
    ledger = [deed for deed in world.get("flags", {}).get("deeds", []) if isinstance(deed, dict)]
    seen = [deed["text"] for deed in ledger if npc.get("id") in deed.get("witnesses", [])]
    note = ""
    if seen:
        note = " Karşındaki kişinin şunları yaptığını kendi gözünle gördün: " + "; ".join(seen[-3:]) + \
            ". Ona buna göre davran; görmezden gelme."
    import game
    heard = [deed["text"] for deed in ledger if deed.get("kind") == "killing"
             and npc.get("id") not in deed.get("witnesses", [])]
    if heard and game._ARMED_ROLE.search(game._normalize_turkish_typos(str(npc.get("role", "")))):
        note += " Kentte bir cinayet konuşuluyor: " + heard[-1] + \
            ". Kan izi taşıyan ya da bunu söyleyen biri görürsen üstüne gidersin."
    return note


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
    here = world.get("locations", {}).get(world.get("location"), {})
    way_out = here.get("exit_location_id") or here.get("parent_location_id") if isinstance(here, dict) else None
    lines = []
    if armed:
        guard = armed[0]
        guard["hostile"] = True
        session.start_combat(guard)
        lines.append(f"{living_world.public_npc_name(guard)} silahını çekip üstüne yürüyor: “Dur orada, katil!”")
    for npc in present:
        if npc not in armed and isinstance(way_out, str) and way_out in world.get("locations", {}):
            npc["location"] = way_out
            lines.append(f"{living_world.public_npc_name(npc)} bağırarak kapıya koşuyor.")
    if lines:
        result["narration"] = " ".join([str(result.get("narration") or ""), *lines]).strip()


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
        remember(session, "theft", "seni soymaya kalktı", victim_id=victim["id"])
        return _reply(session, _pick_line(session, victim), "theft", "caught", check,
                      ["relationships"], npc_id=victim["id"])
    if thing is None and victim is not None:
        coins = session.rng.randint(5, 40)
        wallets = world.setdefault("currency", {})
        wallets["player"] = wallets.get("player", 0) + coins
        narration = f"Parmakların sessizce işini görüyor: kesende {coins} bakır daha var. Kimse fark etmedi."
        return _reply(session, narration, "theft", "stolen", check, ["currency"], coins_cp=coins)
    label = thing or "Küçük bir ganimet"
    world.setdefault("inventory", []).append(label)
    narration = f"Elin hızlı: {label.lower()} artık sende, kimse bakmıyor."
    return _reply(session, narration, "theft", "stolen", check, ["player.inventory"], item=label)


def _burn(session) -> dict[str, Any]:
    check = _check(session, "Survival", 10)
    present = session.active_npcs()
    if check["result"] != "BAŞARILI":
        return _reply(session, "Kıvılcım bir türlü tutmuyor; elinde yalnız is kokusu kalıyor.",
                      "arson", "failed", check, [])
    session.create_local_feature({
        "name": "Tüten ateş", "description": "Dumanı sokağa yayılan, yeni tutuşmuş bir ateş.",
        "location": session.world_state.get("location"),
    })
    remember(session, "arson", "burada ateş yaktı")
    narration = "Kıvılcım tutuyor; duman yükselmeye, ardından alev yalamaya başlıyor."
    if present:
        narration += f" {living_world.public_npc_name(present[0])} sana dönüp bağırıyor: “Deli misin sen?”"
    return _reply(session, narration, "arson", "lit", check, ["features"])


_SEARCH_BODY = re.compile(r"\b(?:ustunu|cebini|ceplerini|cesedi|kesesini)\b.*\b(?:ar\w*|al\w*|bak\w*|yokl\w*)|\bsoyuyorum\b")
_PRICES = (("bira", "bira", 4), ("sarap", "şarap", 20), ("yemek", "tabak yemek", 30))
_BUY = re.compile(r"\b(?:alayim|alirim|aliyorum|ver|versene|getir|getirsene|istiyorum|isterim)\b")
_SERVER = re.compile(r"\b(?:barmen|hanci|meyhaneci|garson|satici|asci)")


def _search_body(session, text: str) -> dict[str, Any] | None:
    import fallen
    bodies = [npc for npc in fallen.here(session.world_state) if not npc.get("searched")]
    if not bodies or not _SEARCH_BODY.search(fold(session, text)):
        return None
    body = bodies[0]
    body["searched"] = True
    coins = session.rng.randint(0, 30)
    wallets = session.world_state.setdefault("currency", {})
    wallets["player"] = wallets.get("player", 0) + coins
    who = living_world.public_npc_name(body)
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


def _buy(session, text: str) -> dict[str, Any] | None:
    folded = fold(session, text)
    wanted = next((item for item in _PRICES if item[0] in folded), None)
    server = next((npc for npc in session.active_npcs()
                   if _SERVER.search(fold(session, str(npc.get("role", ""))))), None)
    if wanted is None or server is None or not _BUY.search(folded):
        return None
    world = session.world_state
    settle_coin_labels(world)
    wallets = world.setdefault("currency", {})
    _, label, price = wanted
    who = living_world.public_npc_name(server)
    if wallets.get("player", 0) < price:
        return _reply(session, f"{who} kesene bakıp başını sallıyor. “Parası yoksa {label} da yok.”",
                      "purchase", "no_money", None, [])
    wallets["player"] -= price
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
