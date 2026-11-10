"""The town answers what the player did, through people who could know and nothing else.

`bold_acts` keeps the ledger of deeds. This file reads that ledger against the
campaign clock: a body is found, a post is filled, news walks from place to
place, guards look for someone they have a description of. Everything is rolled
from the campaign seed with no model call, and the player learns of it only by
standing where it can be seen or heard.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import living_world

HOUR = 3600
DAY = 86400

# Hours a body lies before someone passes, by the kind of place; a street is busier than a graveyard.
FOUND_AFTER_HOURS = {
    "default": (6, 24), "street": (3, 8), "market": (3, 6), "barracks": (4, 12), "temple": (4, 12),
    "harbor": (4, 12), "archive": (12, 36), "library": (8, 24), "graveyard": (24, 72),
}
TAKEN_AFTER_SECONDS = 4 * HOUR
POST_FILLED_AFTER_HOURS = (12, 36)
STAIN_SECONDS = 7 * DAY
INQUIRY_SECONDS = DAY  # how long whoever keeps the peace stays at the place
SEARCH_EVERY_SECONDS = 4 * HOUR
MAX_SEARCHES = 3
SEARCH_BONUS = 2
MAX_LINES_PER_TURN = 2
MAX_WAITING_LINES = 6

# How far each kind of news walks. A hop is one step along the town's real doors and streets.
NEWS = {
    "killing": {"hops": 3, "hop_hours": 6, "talk": "“{text}, duydun mu?”", "refuse": True, "guards": True},
    "arson": {"hops": 3, "hop_hours": 4, "talk": "“{place} yanmış, duydun mu?”", "refuse": True, "guards": True},
    "theft": {"hops": 1, "hop_hours": 8, "talk": "“Ortalıkta el uzatan biri varmış, duydun mu?”", "refuse": True},
    "theft_unseen": {"hops": 1, "hop_hours": 8, "talk": "“{text}, duydun mu?”"},
    "assault": {"hops": 1, "hop_hours": 8, "talk": "“Biri {text}, duydun mu?”"},
    "broken_promise": {"hops": 1, "hop_hours": 8, "talk": "“Biri {text}, duydun mu?”"},
}
_TALKING = (
    "{who} alçak sesle konuşuyor: {talk}",
    "{who} başını yaklaştırıp fısıldıyor: {talk}",
    "{who} kimseye bakmadan söyleniyor: {talk}",
)
_CHALLENGES = (
    "{who} yolunu kesip seni baştan aşağı süzüyor. “Dur bakalım. Anlatılan kişiye benziyorsun; konuşmamız lazım.”",
    "{who} eli kabzasında yanına geliyor. “Dur bakalım. Birkaç sorum olacak, nerede olduğunu anlat.”",
)
_ARRESTS = (
    "{who} elini omzuna koyuyor. “Tanıklar seni tarif etti: {text}. Silahını bırak, karakola yürüyoruz.”",
    "{who} önüne geçip yolunu kapatıyor. “{Text}, seni gören var. Karakola geliyorsun; zorluk çıkarma.”",
)
_LET_GO = "{who} bir süre yüzüne bakıyor, sonra başını sallıyor. “Peki. Şimdilik yoluna bak; ama gözüm üstünde.”"
_RESISTED ="{who} silahını çekiyor. “Yeter. Sözle gelmiyorsan zorla götürürüm.”"
_GOT_AWAY = "Arkandan bağırışlar yükseliyor ama {who} izini kaybediyor; şimdilik sıyrıldın."
_CAUGHT_UP = "{who} arkandan yetişip yolunu kesiyor, silahı elinde. “Kaçamazsın!”"
_TOOK_THE_BRIBE = "{who} parayı avucunda tartıp cebine atıyor. “Seni görmedim.” Arkasını dönüp gidiyor; {amount} bakır kesenden çıktı."
_REFUSED_THE_BRIBE = "{who} elini itiyor. “Beni satın alamazsın. Karakola, dedim.”"
_TAKEN_IN = "{who} seni karakola götürüyor. Geceyi demir parmaklıklar ardında geçiriyorsun; sabah {fine} bakır ceza kesilip salıveriliyorsun."
FINE_CP = 500
# The arrest said what it wants: hands up, weapon down, walk along. A reading of giving up stands on these words.
_GIVES_IN = re.compile(
    r"\b(?:teslim\w*|tutukl\w*|ellerimi|karakola|tamam|peki|kabul\w*)\b|\b\w+\s+(?:yere\s+)?(?:birak|indir|uzat)\w*"
)
_WONT = re.compile(r"\b\w+m[iu]yor\w*|\b\w+(?:mayacag|meyeceg)\w*|\b(?!tamam\b)\w+m[ae]m\b")
HELD_SECONDS = 8 * HOUR
ARREST_PATIENCE = 2  # the turns of talk an arrest will stand before it turns to force
_FINDER_LINE = "{who} içeri adım atıyor, cesedi görüp donup kalıyor; sonra sana bakıp geri geri çıkıyor."
_TAKEN_LINE = "Birkaç kişi gelip cesedi bir örtüye sarıyor ve sessizce götürüyor."
_STAIN_LINE = "Yerde ovulmuş ama tam çıkmamış koyu bir kan lekesi var."
_NEW_POST_LINE = "Burayı artık {who} tutuyor; öncekinin eşyaları hâlâ bir köşede duruyor."
_NEW_POST_ARRIVAL = "{who} içeri girip etrafa bakınıyor; besbelli boşalan yerin yeni sahibi o."
_SEARCH_LINE = "Sokağın ucunda bir muhafız gelip geçenleri durdurup birini soruyor."
_WATCH_ROLE = "Muhafız"
_WATCH_ARRIVES = "{who} içeri girip yere uzun uzun bakıyor, sonra gözlerini sana çeviriyor."
_WATCH_AT_WORK = "{who} yerdeki izlerin başında durmuş, olanı anlamaya çalışıyor."
_COLD_LINE = "{who} seni görünce yüzünü çevirip işine dönüyor."
_REFUSAL = "{who} sana bakıp başını iki yana sallıyor. “Sana satacak bir şeyim yok. Çık git.”"


def _who(npc: dict[str, Any]) -> str:
    return living_world.turkish_initial_upper(living_world.public_npc_name(npc))


def _mid_sentence(name: Any) -> str:
    """'Bir nöbetçi çavuş' as it reads inside a sentence; a proper name stays as it is."""
    text = str(name)
    return "bir " + text[4:] if text.startswith("Bir ") else text


def _deeds(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [deed for deed in world.get("flags", {}).get("deeds", [])
            if isinstance(deed, dict) and isinstance(deed.get("at"), int)]


def _now(world: dict[str, Any]) -> int:
    return int((world.get("campaign_time") or {}).get("elapsed_seconds", 0) or 0)


def _alive(world: dict[str, Any]) -> list[dict[str, Any]]:
    return [npc for npc in world.get("npcs", []) if isinstance(npc, dict) and isinstance(npc.get("id"), str)
            and npc.get("combat_status") != "dead" and not npc.get("hidden")]


def _npc(world: dict[str, Any], npc_id: Any) -> dict[str, Any] | None:
    return next((npc for npc in world.get("npcs", []) if isinstance(npc, dict) and npc.get("id") == npc_id), None)


def _digest(world: dict[str, Any], *salt: Any) -> int:
    seed = living_world._campaign_seed(world)
    text = "\x00".join(str(part) for part in (seed, "world-reaction", *salt))
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


def _between(world: dict[str, Any], low: int, high: int, *salt: Any) -> int:
    return low + _digest(world, *salt) % (high - low + 1)


def _d20(world: dict[str, Any], *salt: Any) -> int:
    return _between(world, 1, 20, "d20", *salt)


def _settlement(world: dict[str, Any], location: Any) -> str | None:
    import local_places
    return local_places.settlement_of(world, location)


def _wrongful(world: dict[str, Any], deed: dict[str, Any]) -> bool:
    """Killing an enemy who came at the player is no crime; killing someone they went for is."""
    if deed.get("kind") != "killing":
        return True
    body = _npc(world, deed.get("victim_id"))
    return body is None or not body.get("hostile") or any(
        other.get("kind") == "assault" and other.get("victim_id") == body.get("id") for other in _deeds(world))


def found_delay(world: dict[str, Any], deed: dict[str, Any]) -> int:
    """Seconds until someone passes this body; the same for one campaign every time it is asked."""
    place = world.get("locations", {}).get(deed.get("location"))
    kind = place.get("place_kind") if isinstance(place, dict) else None
    if kind is None and _settlement(world, deed.get("location")) == deed.get("location"):
        kind = "street"
    low, high = FOUND_AFTER_HOURS.get(kind, FOUND_AFTER_HOURS["default"])
    return _between(world, low * HOUR, high * HOUR, "found", deed.get("victim_id"), deed.get("at"))


def _wait_line(world: dict[str, Any], place: Any, line: str) -> None:
    waiting = world.setdefault("flags", {}).setdefault("reaction_lines", [])
    waiting.append({"place": place, "line": line})
    del waiting[:-MAX_WAITING_LINES]


def _someone_knows_at_once(world: dict[str, Any], deed: dict[str, Any]) -> bool:
    import bold_acts
    return any(bold_acts.identifies(deed, npc["id"]) for npc in _alive(world))


def _find_body(world: dict[str, Any], deed: dict[str, Any], now: int) -> None:
    place = deed.get("location")
    here = [npc for npc in _alive(world) if npc.get("location") == place]
    town = _settlement(world, place)
    passers = here or sorted((npc for npc in _alive(world) if town and _settlement(world, npc.get("location")) == town),
                             key=lambda npc: npc["id"])
    due = deed["at"] + found_delay(world, deed)
    if now < due or not passers:
        return
    finder = passers[_digest(world, "finder", deed.get("victim_id"), deed["at"]) % len(passers)]
    deed.update(found_at=due, found_by=finder["id"])
    deed.setdefault("heard", []).append(finder["id"])
    if world.get("location") == place:  # the player is standing over it when they walk in
        deed.setdefault("seen_near", []).append(finder["id"])
        _wait_line(world, place, _FINDER_LINE.format(who=_who(finder)))


def _discover(world: dict[str, Any], deed: dict[str, Any], now: int) -> None:
    import bold_acts
    kind = deed.get("kind")
    if kind in {"killing", "arson"} and _someone_knows_at_once(world, deed):
        deed["found_at"] = deed["at"]
    elif kind == "killing":
        _find_body(world, deed, now)
    elif kind == "arson":
        fire = next((fire for fire in bold_acts._fires(world) if fire["location"] == deed.get("location")), None)
        if fire is not None and fire["stage"] >= 1:  # smoke is seen by whoever looks up
            deed["found_at"] = fire["lit_at"] + bold_acts._FIRE_STAGES[1][0]
    elif kind == "theft_unseen":
        victim = _npc(world, deed.get("victim_id"))
        noticed = deed["at"] + bold_acts.NEARBY_SECONDS
        if victim is not None and victim.get("combat_status") != "dead" and now >= noticed:
            deed["found_at"] = noticed
    elif kind in NEWS:
        deed["found_at"] = deed["at"]


def carried_off(world: dict[str, Any]) -> set[Any]:
    """The dead someone has already come for; the ledger keeps this, the person's own record stays as it fell."""
    return {deed.get("victim_id") for deed in _deeds(world) if "taken_at" in deed}


def _take_body(world: dict[str, Any], deed: dict[str, Any], now: int) -> None:
    body = _npc(world, deed.get("victim_id"))
    if (deed.get("kind") != "killing" or "taken_at" in deed or body is None or body.get("combat_status") != "dead"
            or now < deed["found_at"] + TAKEN_AFTER_SECONDS):
        return
    deed["taken_at"] = deed["found_at"] + TAKEN_AFTER_SECONDS
    if world.get("location") == body.get("location"):
        _wait_line(world, body.get("location"), _TAKEN_LINE)


def _open_post(world: dict[str, Any], deed: dict[str, Any], now: int) -> None:
    body = _npc(world, deed.get("victim_id"))
    place = body.get("place_role_of") if isinstance(body, dict) and body.get("combat_status") == "dead" else None
    record = world.get("locations", {}).get(place)
    if deed.get("kind") != "killing" or not isinstance(record, dict) or record.get("place_kind") is None:
        return
    low, high = POST_FILLED_AFTER_HOURS
    if now < deed["found_at"] + _between(world, low * HOUR, high * HOUR, "post", place, deed["at"]):
        return
    import local_places
    role = local_places.PLACE_KINDS[record["place_kind"]]["role"]
    body["was_role_of"] = body.pop("place_role_of")
    record.update(resident_name=living_world.stable_local_name(world, f"{place}:after:{body['id']}", role),
                  resident_known=False)
    deed["post"] = place


def discover(world: dict[str, Any], now: int) -> None:
    """The clock moved: what was hidden is found, the dead are carried off, a post falls open."""
    for deed in _deeds(world):
        if not _wrongful(world, deed):
            continue  # an enemy who came at the player and fell: nobody asks after it
        if "found_at" not in deed:
            _discover(world, deed, now)
        if "found_at" in deed:
            _take_body(world, deed, now)
            _open_post(world, deed, now)


def _neighbours(world: dict[str, Any], location: Any) -> list[str]:
    """Places one door or street away, inside the same town."""
    locations = world.get("locations", {})
    here = locations.get(location)
    if not isinstance(here, dict):
        return []
    near = {here.get("parent_location_id"), here.get("exit_location_id")}
    near |= {key for key, record in locations.items() if isinstance(record, dict)
             and location in (record.get("parent_location_id"), record.get("exit_location_id"))}
    town = _settlement(world, location)
    return sorted(key for key in near - {location, None}
                  if key in locations and town is not None and _settlement(world, key) == town)


def _walk_news(world: dict[str, Any], deed: dict[str, Any], rule: dict[str, Any], now: int) -> None:
    import bold_acts
    reach = deed.setdefault("reach", {})
    sources = {deed.get("location")}
    sources |= {npc.get("location") for npc in _alive(world)
                if bold_acts.identifies(deed, npc["id"]) or npc["id"] == deed.get("found_by")}
    for place in sorted(p for p in sources if isinstance(p, str)):
        reach.setdefault(place, [deed["found_at"], rule["hops"]])
    hop = rule["hop_hours"] * HOUR
    moved = True
    while moved:
        moved = False
        for place, (at, left) in list(reach.items()):
            if left <= 0 or now - at < hop:
                continue
            for next_place in _neighbours(world, place):
                if next_place not in reach:
                    reach[next_place] = [at + hop, left - 1]
                    moved = True
    for npc in _alive(world):
        arrived = reach.get(npc.get("location"))
        if (arrived and now - arrived[0] >= bold_acts.NEARBY_SECONDS and npc["id"] != deed.get("victim_id")
                and not bold_acts.knows(deed, npc["id"])):
            deed.setdefault("heard", []).append(npc["id"])


def _give_description(world: dict[str, Any], deed: dict[str, Any], now: int) -> None:
    """Whoever can point at the player tells a guard in their town; hearsay gives a guard no face."""
    import bold_acts
    if now - deed["at"] < bold_acts.TO_THE_POST_SECONDS:
        return
    pointers = [npc for npc in _alive(world)
                if bold_acts.identifies(deed, npc["id"]) or npc["id"] in deed.get("seen_near", [])]
    towns = {_settlement(world, npc.get("location")) for npc in pointers} - {None}
    described = deed.setdefault("described", [])
    for npc in _alive(world):
        if (bold_acts._is_armed(npc) and npc["id"] in deed.get("heard", []) and npc["id"] not in described
                and _settlement(world, npc.get("location")) in towns):
            described.append(npc["id"])


def spread(world: dict[str, Any], now: int) -> None:
    for deed in _deeds(world):
        rule = NEWS.get(deed.get("kind"))
        if rule is None or "found_at" not in deed:
            continue
        _walk_news(world, deed, rule, now)
        if rule.get("guards"):
            _give_description(world, deed, now)


def promise_broken(world: dict[str, Any], thread: dict[str, Any], owner: Any, status: str) -> None:
    """Work the player took on came to nothing: the one who gave it knows, and says so."""
    import bold_acts
    if (status not in {"failed", "abandoned", "expired"} or thread.get("accepted_at") is None
            or not isinstance(owner, dict) or not isinstance(owner.get("id"), str)
            or owner.get("combat_status") == "dead"):
        return
    ledger = bold_acts.deeds(world)
    ledger.append({
        "kind": "broken_promise", "text": f"{living_world.public_npc_name(owner)} işini üstlenip yarım bıraktı",
        "location": owner.get("location"), "victim_id": owner["id"], "witnesses": [owner["id"]],
        "turn": int(world.get("flags", {}).get("turn_index", 0) or 0), "at": _now(world), "heard": [], "told": [],
    })
    del ledger[:-bold_acts.MAX_DEEDS]


def refuses(world: dict[str, Any], npc: dict[str, Any]) -> bool:
    """A person will not deal with someone they themselves can tie to a grave deed. Hearsay changes nothing here."""
    import bold_acts
    npc_id = npc.get("id")
    return any(NEWS.get(deed.get("kind"), {}).get("refuse") and _wrongful(world, deed)
               and (bold_acts.identifies(deed, npc_id) or npc_id in deed.get("seen_near", [])
                    or npc_id in deed.get("described", []))
               for deed in _deeds(world))


def refusal_line(npc: dict[str, Any]) -> str:
    return _REFUSAL.format(who=_who(npc))


def speech_note(world: dict[str, Any], npc: dict[str, Any]) -> str:
    npc_id = npc.get("id")
    note = ""
    if any(npc_id in deed.get("seen_near", []) for deed in _deeds(world)):
        note += " Karşındaki kişiyi cesedin yanında gördün; ne yaptığını bilmiyorsun ama aklından çıkmıyor."
    if any(npc_id in deed.get("described", []) for deed in _deeds(world)):
        note += (" Sana bir tarif verildi ve karşındaki kişi ona benziyor. Emin değilsin; "
                 "soru sor, nerede olduğunu öğrenmeye çalış.")
    if any((deed.get("hold") or {}).get("guard") == npc_id and (deed.get("hold") or {}).get("arrest")
           for deed in _deeds(world)):
        note += (" Karşındakini tutukluyorsun: karakola götüreceksin. Bundan vazgeçme, işin başından aşkın deme, "
                 "serbest bırakacağını söyleme; teslim olmasını iste.")
    return note


def place_marks(world: dict[str, Any], location: Any, people: dict[Any, dict[str, Any]]) -> list[str]:
    """What the player sees walking in; each shows once."""
    import local_places
    marks = []
    for deed in _deeds(world):
        if deed.get("post") == location and not deed.get("post_shown"):
            resident = local_places.resident_of(world, location)
            if resident is not None:
                deed["post_shown"] = True
                marks.append(_NEW_POST_LINE.format(who=_mid_sentence(living_world.public_npc_name(resident))))
        watch = people.get(deed.get("watch_id"))
        if deed.get("location") == location and watch is not None and not deed.get("watch_shown"):
            deed["watch_shown"] = True
            marks.append(_WATCH_AT_WORK.format(who=_who(watch)))
        if (deed.get("kind") == "broken_promise" and not deed.get("shown")
                and deed.get("victim_id") in people):
            deed["shown"] = True
            marks.append(_COLD_LINE.format(who=_who(people[deed["victim_id"]])))
    return marks


def scene_marks(world: dict[str, Any]) -> str:
    """What stays to be seen here, for any look at the place."""
    now, here = _now(world), world.get("location")
    stained = any(deed.get("location") == here and "taken_at" in deed and now - deed["taken_at"] < STAIN_SECONDS
                  for deed in _deeds(world))
    return _STAIN_LINE if stained else ""


def _due_lines(world: dict[str, Any]) -> list[str]:
    import world_happenings
    waiting = [row for row in world.get("flags", {}).pop("reaction_lines", []) if isinstance(row, dict)]
    here = [row for row in waiting if row.get("place") == world.get("location")]
    for row in waiting:
        if row not in here:
            world_happenings.unseen(world, row.get("line"))
    return [row["line"] for row in here]


def _send_guards_home(world: dict[str, Any], now: int) -> None:
    for npc in _alive(world):
        if "came_from" in npc and npc.get("location") != world.get("location") and now >= npc.get("back_at", 0):
            npc["location"] = npc.pop("came_from")
            npc.pop("back_at", None)


def _fill_post_here(session) -> list[str]:
    import local_places
    world = session.world_state
    lines = []
    for deed in _deeds(world):
        place = deed.get("post")
        if place is None or place != world.get("location") or local_places.resident_of(world, place) is not None:
            continue
        resident, _ = local_places.furnish(world, world["locations"][place], create_npc=session.create_npc_from_ai,
                                           create_feature=session.create_local_feature)
        if isinstance(resident, dict):
            deed["post_shown"] = True
            lines.append(_NEW_POST_ARRIVAL.format(who=_who(resident)))
    return lines


def _tell_successors(world: dict[str, Any]) -> None:
    import bold_acts
    import local_places
    for deed in _deeds(world):
        resident = local_places.resident_of(world, deed["post"]) if deed.get("post") else None
        if resident is not None and not bold_acts.knows(deed, resident.get("id")):
            deed.setdefault("heard", []).append(resident["id"])


def _keeper_of_the_peace(session, town: str) -> dict[str, Any] | None:
    """A guard of this town; when there is none left the town sends one, once."""
    import bold_acts
    world = session.world_state
    guard = next((npc for npc in _alive(world) if bold_acts._is_armed(npc)
                  and _settlement(world, npc.get("location")) == town), None)
    if guard is not None:
        return guard
    return session.create_npc_from_ai({
        "name": living_world.stable_local_name(world, f"{town}:watch", _WATCH_ROLE), "role": _WATCH_ROLE,
        "location": town, "relationship": "neutral",
        "appearance": "Yıpranmış deri zırhlı, dikkatli bakışlı biri.",
        "personality": "Ağır konuşur, gördüğünü tartar.",
    }, allow_other_location=True)


def _watch_comes(session, now: int) -> list[str]:
    """Word of a grave deed reaches the guards: one goes to the place. They know what, not who."""
    import bold_acts
    world = session.world_state
    for deed in _deeds(world):
        if (not NEWS.get(deed.get("kind"), {}).get("guards") or "found_at" not in deed or "watch_id" in deed
                or now < deed["found_at"] + bold_acts.TO_THE_POST_SECONDS):
            continue
        town = _settlement(world, deed.get("location"))
        guard = _keeper_of_the_peace(session, town) if town else None
        if not isinstance(guard, dict):
            continue
        deed["watch_id"] = guard["id"]
        if not bold_acts.knows(deed, guard["id"]):
            deed.setdefault("heard", []).append(guard["id"])
        back_at = deed["found_at"] + INQUIRY_SECONDS
        if now >= back_at or guard.get("location") == deed.get("location"):
            continue  # the looking was over before anyone in play could see it
        guard.update(came_from=guard.get("location"), back_at=back_at, location=deed.get("location"))
        if world.get("location") == deed.get("location"):
            deed["watch_shown"] = True
            deed.setdefault("seen_near", []).append(guard["id"])
            return [_WATCH_ARRIVES.format(who=_who(guard))]
    return []


def _hiding_score(session) -> int:
    character = session.character
    dexterity = (character.get("ability_scores") or {}).get("dexterity")
    return 10 + ((dexterity - 10) // 2 if type(dexterity) is int else 0)


def _lost_sight(world: dict[str, Any], npc: dict[str, Any]) -> bool:
    import bold_acts
    turn = int(world.get("flags", {}).get("turn_index", 0) or 0)
    return turn - npc.get("lost_sight_turn", -bold_acts.LOST_SIGHT_TURNS) < bold_acts.LOST_SIGHT_TURNS


def _search(session, now: int) -> list[str]:
    """One guard who has a description tries to find the player; a miss is only a man asking in the street."""
    world = session.world_state
    here = world.get("location")
    town = _settlement(world, here)
    journey = world.get("journey")
    if town is None or (journey and journey.get("status") != "ARRIVED"):
        return []
    for deed in _deeds(world):
        tried = deed.get("searches", 0)
        if deed.get("settled"):
            continue
        guards = [npc for npc in _alive(world) if npc["id"] in deed.get("described", [])
                  and _settlement(world, npc.get("location")) == town and not _lost_sight(world, npc)]
        if (not guards or tried >= MAX_SEARCHES or any(npc.get("location") == here for npc in guards)
                or now - deed.get("searched_at", -SEARCH_EVERY_SECONDS) < SEARCH_EVERY_SECONDS):
            continue
        deed.update(searches=tried + 1, searched_at=now)
        if _d20(world, "search", deed["at"], tried) + SEARCH_BONUS >= _hiding_score(session):
            guards[0].setdefault("came_from", guards[0].get("location"))
            guards[0].pop("back_at", None)
            guards[0]["location"] = here
            return []  # the guard is here now: the challenge below is what the player sees
        return [_SEARCH_LINE] if here == town else []
    return []


def _turn(world: dict[str, Any]) -> int:
    return int(world.get("flags", {}).get("turn_index", 0) or 0)


def holding(world: dict[str, Any], npc: Any) -> dict[str, Any] | None:
    """The deed this guard is arresting the player for, if they are."""
    npc_id = npc.get("id") if isinstance(npc, dict) else None
    return next((deed for deed in _deeds(world) if (deed.get("hold") or {}).get("guard") == npc_id
                 and deed["hold"].get("arrest")), None)


def arrester(world: dict[str, Any]) -> dict[str, Any] | None:
    return next((_npc(world, deed["hold"]["guard"]) for deed in _deeds(world)
                 if (deed.get("hold") or {}).get("arrest")), None)


def _force(session, guard: dict[str, Any], deed: dict[str, Any], line: str) -> list[str]:
    deed.pop("hold", None)
    guard["hostile"] = True
    session.start_combat(guard)
    return [line.format(who=_who(guard))]


def _flight(session, guard: dict[str, Any], deed: dict[str, Any]) -> list[str]:
    """The player walked out on a guard who had them. The legs decide."""
    import bold_acts
    world = session.world_state
    deed.pop("hold", None)
    if bold_acts._check(session, "Athletics", 15)["result"] == "BAŞARILI":
        guard["lost_sight_turn"] = _turn(world)
        return [_GOT_AWAY.format(who=_who(guard))]
    guard.setdefault("came_from", guard.get("location"))
    guard["location"] = world.get("location")
    deed["hold"] = {"guard": guard["id"], "place": world.get("location"), "turn": _turn(world)}
    return _force(session, guard, deed, _CAUGHT_UP)


def _answered(session, guard: dict[str, Any], result: Any) -> bool:
    """The player spoke to the guard who asked, this turn."""
    action = result.get("action_result") if isinstance(result, dict) else None
    return isinstance(action, dict) and action.get("npc_id") == guard.get("id") and action.get("action") == "dialogue"


def _talking_skill(session) -> str:
    return "Deception" if "Deception" in (session.character.get("proficient_skills") or ()) else "Persuasion"


def _press(session, result: Any = None) -> list[str]:
    """What follows the question: the answer is weighed, then a hand on the shoulder, then the player's choice."""
    import bold_acts
    import game
    world = session.world_state
    turn = _turn(world)
    for deed in _deeds(world):
        hold = deed.get("hold")
        if not hold or deed.get("settled"):
            continue
        guard = _npc(world, hold.get("guard"))
        if guard is None or guard.get("combat_status") == "dead":
            deed.pop("hold")
            continue
        if turn <= hold["turn"]:
            continue
        if world.get("location") != hold["place"]:
            return _flight(session, guard, deed)
        if not hold.get("arrest"):
            if _answered(session, guard, result) and bold_acts._check(
                    session, _talking_skill(session), game.DIFFICULTY_DC["medium"])["result"] == "BAŞARILI":
                deed.pop("hold")  # the answer held: this guard has asked and lets it go
                return [_LET_GO.format(who=_who(guard))]
            hold.update(arrest=True, turn=turn)
            session._set_scene_active_npc(guard, turn)
            text = str(deed.get("text") or "").rstrip(".")
            line = _ARRESTS[_digest(world, "arrest", guard["id"], deed["at"]) % len(_ARRESTS)]
            return [line.format(who=_who(guard), text=_mid_sentence(text), Text=text)]
        if turn - hold["turn"] >= ARREST_PATIENCE:
            return _force(session, guard, deed, _RESISTED)
    return []


_BRIBE_CARD = "{who} avucuna uzattığın {amount} bakıra bakıyor; bir şey demiyor."


def bribe(session, amount: int) -> tuple[list[str], Any]:
    """Coin held out to the guard making the arrest opens a bribe card; nothing changes hands now.

    The card's confirmation rolls the Persuasion word (more coin is an easier word) and only a success moves the
    coin and ends the hold (economic_actions). Returns the line to show and the PrepareResult, or ([], None) when
    nobody is holding the player; whether a card opened is read from the result's status alone.
    """
    import economic_actions
    world = session.world_state
    guard = arrester(world)
    deed = holding(world, guard)
    if guard is None or deed is None:
        return [], None
    prepared = economic_actions.prepare_from_turn(
        session, economic_actions.turn_proposal("gift", str(guard["id"]), amount_cp=amount))
    if prepared.status == "prepared":
        return [f"{_BRIBE_CARD.format(who=_who(guard), amount=amount)} {prepared.public_message}"], prepared
    return [prepared.public_message], prepared


def give_up(session) -> list[str]:
    """The player lets themselves be taken: a night held and a fine, and for this deed it is over."""
    import bold_acts
    import game
    import timed_gameplay
    world = session.world_state
    guard = arrester(world)
    deed = holding(world, guard)
    if guard is None or deed is None:
        return []
    deed.pop("hold")
    deed["settled"] = True
    post = guard.get("came_from") or guard.get("place_role_of") or guard.get("location")
    if post in world.get("locations", {}) and post != world.get("location") and game.commit_location_change(post):
        guard["location"] = post
        guard.pop("came_from", None)
        guard.pop("back_at", None)
    bold_acts.settle_coin_labels(world)
    wallets = world.setdefault("currency", {})
    fine = min(FINE_CP, wallets.get("player", 0))
    wallets["player"] = wallets.get("player", 0) - fine
    timed_gameplay._advance(session, HELD_SECONDS, "explicit_wait")
    return [_TAKEN_IN.format(who=_who(guard), fine=fine)]


def _challenge(session) -> list[str]:
    """A guard with a description stops the player and asks. What comes next is `_press`."""
    world = session.world_state
    for deed in _deeds(world):
        if deed.get("settled"):
            continue
        for npc in session.active_npcs():
            if npc.get("id") in deed.get("described", []) and npc["id"] not in deed.get("challenged", []):
                deed.setdefault("challenged", []).append(npc["id"])
                deed["hold"] = {"guard": npc["id"], "place": world.get("location"), "turn": _turn(world)}
                session._set_scene_active_npc(npc, world.get("flags", {}).get("turn_index", 0))
                line = _CHALLENGES[_digest(world, "challenge", npc["id"], deed["at"]) % len(_CHALLENGES)]
                return [line.format(who=_who(npc))]
    return []


def _told_by_worse(world: dict[str, Any], deed: dict[str, Any]) -> bool:
    """Nobody talks of a blow when the same person was killed by it."""
    return deed.get("kind") == "assault" and any(
        other.get("kind") == "killing" and other.get("victim_id") == deed.get("victim_id") for other in _deeds(world))


def _overheard(session) -> list[str]:
    """Someone here who has only the rumour talks of it; a witness does not gossip to the one they saw."""
    import bold_acts
    world = session.world_state
    for deed in reversed(_deeds(world)):
        rule = NEWS.get(deed.get("kind"))
        if (rule is None or deed.get("overheard") or _told_by_worse(world, deed)
                or deed.get("location") == world.get("location")):  # nobody asks "did you hear" where it happened
            continue
        speaker = next((npc for npc in session.active_npcs() if npc.get("id") in deed.get("heard", [])
                        and npc.get("id") not in deed.get("seen_near", [])
                        and not bold_acts.identifies(deed, npc.get("id"))), None)
        if speaker is None:
            continue
        deed["overheard"] = True
        text = deed.get("text", "")
        hearsay = deed.get("rumour") or text  # an older deed has no hearsay form
        talk = rule["talk"].format(text=_mid_sentence(hearsay) if rule["talk"].startswith("“Biri") else text,
                                   place=bold_acts._place_name(world, deed.get("location")))
        line = _TALKING[_digest(world, "talk", deed["at"], deed.get("kind")) % len(_TALKING)]
        return [line.format(who=_who(speaker), talk=talk)]
    return []


def _board_hint(world: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """Only on a turn with nothing else to tell, and never on the end of what someone just said."""
    import town_knowledge
    action = result.get("action_result") if isinstance(result.get("action_result"), dict) else {}
    if action.get("action") in {"dialogue", "local_inquiry"} or (world.get("flags") or {}).get("active_npc_id"):
        return []
    hint = town_knowledge.board_hint(world)
    return [hint] if hint else []


def _idle_since_opening(world: dict[str, Any]) -> bool:
    """Read from the record, never from words: still on the opening's own spot, no job put to them or taken, never
    spoken with anyone, no happening joined, no fight. Checked every turn, so a player who was busy once stays so."""
    import world_threads
    scenes = (world.get("scene_state") or {}).get("scenes") or {}
    here = scenes.get(world.get("location"))
    threads = (world_threads.view(world) or {}).get("threads", [])
    return (isinstance(here, dict) and isinstance(here.get("opening"), dict)
            and not any(thread.get("status") in {"offered", "accepted"} for thread in threads)
            and not (world.get("flags") or {}).get("last_npc_id")
            and not any(isinstance(referent, dict) and referent.get("lifecycle") == "promoted"
                        for scene in scenes.values() if isinstance(scene, dict)
                        for referent in scene.get("referents") or ())
            and not (world.get("combat") or {}).get("active"))


def _opening_nudge(world: dict[str, Any], *, may_speak: bool) -> list[str]:
    """Once, on a turn with nothing else to tell from the eighth on, a player still idle since the opening catches
    one more piece of town talk (else the board's line). Busy at any check, it is over: nobody insists. A campaign
    without the flag (a save from before it) never hears it."""
    nudge = (world.get("flags") or {}).get("opening_nudge")
    if not isinstance(nudge, dict) or nudge.get("done") is not False:
        return []
    if not _idle_since_opening(world):
        nudge["done"] = True
        return []
    if not may_speak or type(nudge.get("due_turn")) is not int or _turn(world) < nudge["due_turn"]:
        return []
    nudge["done"] = True
    import local_places
    import town_knowledge
    import world_threads
    settlement_id = local_places.settlement_of(world, world.get("location"))
    talk = world_threads.street_talk(world, settlement_id) if settlement_id else None
    place = (world.get("locations") or {}).get(talk["place_id"]) if talk else None
    if isinstance(place, dict):
        import grounded_action
        town_knowledge.hear_of(world, talk)  # heard, its names given, and the place bound as just said ("oraya")
        grounded_action.note_last(world, talk["place_id"])
        return [f"Yanından geçen iki kişinin konuşmasından bir söz yakalıyorsun: {talk['public_line']}"]
    hint = town_knowledge.board_hint(world)
    return [hint] if hint else []


def _gives_in(session) -> bool:
    """The reading says it is surrender; the fine, the night and the walk to the post need the player to have said so."""
    said = str(getattr(session, "_adventure_player_text", ""))
    line = living_world.normalize_text(said)
    return "?" not in said and bool(_GIVES_IN.search(line)) and not _WONT.search(line)


def _settle_the_law(session, result: Any = None) -> tuple[list[str], bool]:
    """Coin held out or hands held up to a guard making an arrest, as the turn's reading saw them.

    Returns (lines, law_done); when law_done is True the turn's escalation (`_press`, `_challenge`) is already
    settled here. O1: only the FIRST bribe card of a hold pauses that turn; the mark lives in the hold itself. A
    second bribe in the same hold runs `_press` first: if the guard's patience is spent the fight starts and no
    card is prepared at all. A refused bribe or a question (a short purse) pauses nothing.
    """
    world = session.world_state
    guard = arrester(world)
    if guard is None:
        return [], False
    amount = getattr(session, "_bribe_held_out", 0)
    session._bribe_held_out = 0
    if amount:
        deed = holding(world, guard)
        if deed is not None and deed["hold"].get("bribe_card_opened"):
            pressed = _press(session, result) or _challenge(session)
            if world.get("combat", {}).get("active"):
                return pressed, True
            lines, _ = bribe(session, amount)
            return pressed + lines, True
        lines, prepared = bribe(session, amount)
        if prepared is not None and prepared.status == "prepared":
            deed = holding(world, guard)
            if deed is not None:
                deed["hold"]["bribe_card_opened"] = True
            return lines, True
        return lines, False
    if getattr(session, "_front_deed", None) == "yield" and _gives_in(session):
        lines = give_up(session)
        return lines, bool(lines)
    return [], False


def answer(session, result: Any) -> None:
    """The end of a turn: what the player can perceive of all this joins the narration, a line or two at most."""
    world = session.world_state
    _opening_nudge(world, may_speak=False)  # a fight, a talk, a step away: the player is in something now
    if (not isinstance(result, dict) or world.get("combat", {}).get("active")
            or session.character.get("current_hp", 0) <= 0):
        return
    import vouching
    import world_happenings
    now = _now(world)
    _send_guards_home(world, now)
    lines = _due_lines(world) + _fill_post_here(session)
    lines += world_happenings.callers_leave(session, now)
    lines += world_happenings.caller_comes(session, now)
    lines += vouching.open_doors(world)
    _tell_successors(world)
    lines += _watch_comes(session, now)
    lines += _search(session, now)
    lines += _overheard(session)
    import economic_actions
    # A bribe card left open since an earlier turn is not this turn's word: it is closed before the law moves on.
    economic_actions.cancel_prepared(world, actor_id="player",
                                     predicate=lambda offer: any(effect.kind == "bribe_accepted"
                                                                 for effect in offer.on_accept))
    law_lines, law_done = _settle_the_law(session, result)
    law = law_lines if law_done else law_lines + (_press(session, result) or _challenge(session))
    if world.get("combat", {}).get("active"):
        lines = []  # the fight is what the turn is about now
    lines = ([*lines, *law][-MAX_LINES_PER_TURN:] or _opening_nudge(world, may_speak=True)
             or _board_hint(world, result))
    if lines:
        result["narration"] = " ".join([str(result.get("narration") or ""), *lines]).strip()
