"""Bounded local exploration.

Python owns the authored trail, what the player has found, and whether a
travel decision has been accepted. Narration cannot create a route, a trap,
or a ration.
"""

from __future__ import annotations

import re
from typing import Any


CATALOG_ID = "patika_v1"
KEY = "local_exploration_v1"
CAMP = "patika_camp"
ENTRY = "patika_entry"
HALL = "patika_hall"
VAULT = "patika_vault"
ROOM_IDS = (CAMP, ENTRY, HALL, VAULT)
LEG_SECONDS = {"fast": 5400, "normal": 7200, "slow": 9000}
SUPPLY_DAY = 28800
RATION = "Erzak"

LOCATIONS = {
    CAMP: {"name": "Patika Kampı", "type": "wilderness", "description": "Taş patikanın başındaki dinlenme yeri."},
    ENTRY: {"name": "Taş Eşik", "type": "dungeon", "description": "Meşe kapının önündeki eski giriş."},
    HALL: {"name": "Sessiz Salon", "type": "dungeon", "description": "Moloz yığınının ve taş kaldıracın durduğu salon."},
    VAULT: {"name": "Eski Mahzen", "type": "dungeon", "description": "Duvarında bir yol işareti olan küçük mahzen."},
}
DOORS = {
    "door_oak": {"name": "Meşe Kapı", "location": ENTRY, "locked": True},
    "door_vault": {"name": "Mahzen Kapısı", "location": HALL, "locked": False},
    "door_secret": {"name": "Gizli Taş Kapı", "location": ENTRY, "locked": True},
}
EXITS = {
    "entry_hall": {"from": ENTRY, "to": HALL, "name": "Salon geçidi", "door_id": "door_oak", "trap_id": "trap_wire"},
    "hall_entry": {"from": HALL, "to": ENTRY, "name": "Giriş geçidi", "door_id": "door_oak"},
    "hall_vault": {"from": HALL, "to": VAULT, "name": "Mahzen geçidi", "door_id": "door_vault", "hazard_id": "hazard_rubble"},
    "vault_hall": {"from": VAULT, "to": HALL, "name": "Salon dönüşü", "door_id": "door_vault"},
    "entry_secret": {"from": ENTRY, "to": VAULT, "name": "Gizli geçit", "door_id": "door_secret", "discovery_id": "secret_passage"},
    "vault_secret": {"from": VAULT, "to": ENTRY, "name": "Gizli dönüş", "door_id": "door_secret", "discovery_id": "secret_passage"},
}
ROUTES = {CAMP: (ENTRY,)}
DISCOVERIES = {
    "secret_passage": {"location": ENTRY, "name": "Gizli Geçit"},
    "trap_wire": {"location": ENTRY, "name": "Gerili Tel"},
    "vault_marker": {"location": VAULT, "name": "Yol İşareti"},
}
TRAPS = {"trap_wire": {"location": ENTRY, "name": "Gerili Tel", "damage": 2}}
HAZARDS = {"hazard_rubble": {"location": HALL, "name": "Gevşek Moloz"}}
LEVER = {"id": "lever", "location": HALL, "hazard_id": "hazard_rubble", "name": "Taş Kaldıraç"}
TRAP_STATES = frozenset({"hidden", "detected", "disarmed", "triggered"})
HAZARD_STATES = frozenset({"active", "neutralized"})


def _reply(text: str, action: str, *, success: bool = True, **extra: Any) -> dict[str, Any]:
    result = {
        "action": action,
        "status": "resolved",
        "success": success,
        "direct_response": text,
        "state_changes": [f"world_state.{KEY}"],
    }
    result.update(extra)
    return result


def _fail(text: str, action: str = "exploration") -> dict[str, Any]:
    return _reply(text, action, success=False, state_changes=[])


def _combat_active(session: Any) -> bool:
    combat = session.world_state.get("combat")
    return isinstance(combat, dict) and combat.get("active") is True


def _state(world: dict[str, Any]) -> dict[str, Any] | None:
    value = world.get(KEY)
    return value if isinstance(value, dict) else None


def validate_saved(world: dict[str, Any]) -> None:
    if isinstance(world, dict) and KEY in world:
        validate(world)


def validate(world: dict[str, Any]) -> None:
    state = world.get(KEY)
    if not isinstance(state, dict) or state.get("catalog_id") != CATALOG_ID:
        raise ValueError("Yerel keşif kaydı geçersiz.")
    if state.get("origin") not in world.get("locations", {}) or state.get("origin") in ROOM_IDS:
        raise ValueError("Yerel keşif kaydı geçersiz.")
    known = state.get("known")
    discoveries = state.get("discoveries")
    if (
        not isinstance(known, list)
        or not isinstance(discoveries, list)
        or any(not isinstance(item, str) or item not in ROOM_IDS for item in known)
        or len(set(known)) != len(known)
        or CAMP not in known
        or any(item not in DISCOVERIES for item in discoveries)
        or len(set(discoveries)) != len(discoveries)
    ):
        raise ValueError("Yerel keşif kaydı geçersiz.")
    traps = state.get("trap_states")
    hazards = state.get("hazard_states")
    if (
        not isinstance(traps, dict)
        or set(traps) != set(TRAPS)
        or any(value not in TRAP_STATES for value in traps.values())
        or not isinstance(hazards, dict)
        or set(hazards) != set(HAZARDS)
        or any(value not in HAZARD_STATES for value in hazards.values())
    ):
        raise ValueError("Yerel keşif kaydı geçersiz.")
    _validate_world_doors(world, state)
    attempts = state.get("search_attempts")
    journey = state.get("journey")
    pace = state.get("pace")
    if (
        not isinstance(attempts, dict)
        or any(
            room not in ROOM_IDS or type(count) is not int or not 0 <= count <= 2
            for room, count in attempts.items()
        )
        or pace not in LEG_SECONDS
        or type(state.get("elapsed_seconds")) is not int
        or type(state.get("supplied_seconds")) is not int
        or state["elapsed_seconds"] < 0
        or state["supplied_seconds"] < 0
        or state["supplied_seconds"] > state["elapsed_seconds"]
        or type(state.get("supplies_enabled")) is not bool
        or type(state.get("supplies_short")) is not bool
    ):
        raise ValueError("Yerel keşif kaydı geçersiz.")
    if journey is not None and (
        not isinstance(journey, dict)
        or set(journey) != {"origin", "destination", "status"}
        or journey["origin"] not in ROOM_IDS
        or journey["destination"] not in ROOM_IDS
        or journey["status"] not in {"pending", "stopped"}
        or journey["destination"] not in ROUTES.get(journey["origin"], ())
    ):
        raise ValueError("Yerel keşif kaydı geçersiz.")
    if traps["trap_wire"] != "hidden" and "trap_wire" not in discoveries:
        raise ValueError("Yerel keşif kaydı geçersiz.")


def _expected_door_ids(state: dict[str, Any]) -> set[str]:
    doors = {"door_oak", "door_vault"}
    if "secret_passage" in state.get("discoveries", []):
        doors.add("door_secret")
    return doors


def _validate_world_doors(world: dict[str, Any], state: dict[str, Any]) -> None:
    catalog_doors = [
        door for door in world.get("doors", [])
        if isinstance(door, dict) and door.get("id") in DOORS
    ]
    found = {door.get("id") for door in catalog_doors}
    if found != _expected_door_ids(state):
        raise ValueError("Yerel keşif kaydı geçersiz.")
    for door in catalog_doors:
        definition = DOORS[door["id"]]
        if (
            door.get("location") != definition["location"]
            or door.get("name") != definition["name"]
            or type(door.get("locked")) is not bool
            or type(door.get("open")) is not bool
            or type(door.get("broken")) is not bool
            or (door["locked"] and door["open"])
        ):
            raise ValueError("Yerel keşif kaydı geçersiz.")


def _world_door(world: dict[str, Any], door_id: str) -> dict[str, Any] | None:
    for door in world.get("doors", []):
        if isinstance(door, dict) and door.get("id") == door_id:
            return door
    return None


def _publish_door(world: dict[str, Any], door_id: str) -> dict[str, Any]:
    existing = _world_door(world, door_id)
    if existing is not None:
        return existing
    definition = DOORS[door_id]
    record = {
        "id": door_id,
        "name": definition["name"],
        "location": definition["location"],
        "description": definition["name"] + ".",
        "locked": definition["locked"],
        "open": False,
        "broken": False,
    }
    world.setdefault("doors", []).append(record)
    return record


def _visible_doors(world: dict[str, Any]) -> list[dict[str, Any]]:
    location = world.get("location")
    return [
        door for door in world.get("doors", [])
        if isinstance(door, dict)
        and door.get("id") in DOORS
        and door.get("location") == location
    ]


def _install(world: dict[str, Any]) -> None:
    locations = world.setdefault("locations", {})
    for identity, data in LOCATIONS.items():
        locations.setdefault(identity, {
            "id": identity,
            "name": data["name"],
            "type": data["type"],
            "description": data["description"],
            "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        })


def _initial(origin: str) -> dict[str, Any]:
    return {
        "catalog_id": CATALOG_ID,
        "origin": origin,
        "known": [CAMP],
        "discoveries": [],
        "trap_states": {identity: "hidden" for identity in TRAPS},
        "hazard_states": {identity: "active" for identity in HAZARDS},
        "search_attempts": {},
        "elapsed_seconds": 0,
        "supplied_seconds": 0,
        "supplies_enabled": False,
        "supplies_short": False,
        "pace": "normal",
        "journey": None,
    }


def _visible_exit(world: dict[str, Any], definition: dict[str, Any]) -> bool:
    discovery = definition.get("discovery_id")
    if discovery and discovery not in world[KEY]["discoveries"]:
        return False
    return definition["from"] == world.get("location")


def describe(world: dict[str, Any]) -> str:
    state = _state(world)
    if state is None:
        return "Taş patikanın yerel macerasını seçebilirsin."
    names = [item["name"] for item in EXITS.values() if _visible_exit(world, item)]
    if world.get("location") == CAMP:
        names = ["Taş patika"] + names
    if not names:
        return "Buradan görünen bir geçit yok."
    return "Buradan görünen geçitler: " + ", ".join(names) + "."


_SKILL_ABILITY = {"Perception": "wisdom", "Sleight of Hand": "dexterity"}


def _check(session: Any, skill: str, dc: int) -> dict[str, Any]:
    """Same bonus rule as perform_skill_check, rolled on the session generator."""
    character = session.character if isinstance(session.character, dict) else {}
    ability = _SKILL_ABILITY[skill]
    modifiers = character.get("modifiers") if isinstance(character.get("modifiers"), dict) else {}
    modifier = modifiers.get(ability, character.get(f"{ability}_mod", 0))
    if type(modifier) is not int or isinstance(modifier, bool):
        modifier = 0
    proficient = skill in character.get("proficient_skills", [])
    proficiency = character.get("proficiency_bonus", 0)
    if type(proficiency) is not int or isinstance(proficiency, bool) or proficiency < 0:
        proficiency = 0
    bonus = proficiency if proficient else 0
    roll = session.rng.randint(1, 20)
    total = roll + modifier + bonus
    success = roll == 20 or (roll != 1 and total >= dc)
    return {
        "skill": skill,
        "roll": roll,
        "modifier": modifier,
        "proficiency_bonus": bonus,
        "total": total,
        "dc": dc,
        "success": success,
    }


def _incapacitated(session: Any) -> bool:
    character = session.character if isinstance(session.character, dict) else {}
    current = character.get("current_hp", 1)
    status = session.world_state.get("player_combat_status")
    return (type(current) is int and current <= 0) or status == "unconscious"


def _hurt(session: Any, damage: int) -> None:
    character = session.character
    current = character.get("current_hp", 0)
    if type(current) is not int or isinstance(current, bool):
        return
    after = max(0, current - damage)
    character["current_hp"] = after
    if after == 0:
        session.world_state["player_combat_status"] = "unconscious"


def _consume_ration(world: dict[str, Any]) -> bool:
    inventory = world.get("inventory")
    if not isinstance(inventory, list) or RATION not in inventory:
        return False
    inventory.remove(RATION)
    return True


def _apply_supplies(world: dict[str, Any], state: dict[str, Any]) -> None:
    if not state["supplies_enabled"]:
        return
    while state["elapsed_seconds"] - state["supplied_seconds"] >= SUPPLY_DAY:
        state["supplied_seconds"] += SUPPLY_DAY
        if not _consume_ration(world):
            state["supplies_short"] = True


def _arrive(session: Any) -> dict[str, Any]:
    world = session.world_state
    state = world[KEY]
    journey = state["journey"]
    destination = journey["destination"]
    world["location"] = destination
    if destination not in state["known"]:
        state["known"].append(destination)
    state["elapsed_seconds"] += LEG_SECONDS[state["pace"]]
    _apply_supplies(world, state)
    state["journey"] = None
    place = LOCATIONS[destination]["name"]
    text = f"{place} konumuna vardın."
    if state["supplies_short"]:
        text += " Erzakın bu yol için yetmedi."
    return _reply(text, "travel")


def _decision(session: Any, choice: str) -> dict[str, Any]:
    state = session.world_state[KEY]
    journey = state.get("journey")
    if not isinstance(journey, dict) or journey.get("status") not in {"pending", "stopped"}:
        return _fail("Bekleyen bir yolculuk kararı yok.", "travel")
    if choice == "continue":
        if journey.get("status") != "pending" or session.world_state.get("location") != journey.get("origin"):
            return _fail("Devam etmek için yola çıktığın yerde bekleyen bir karar olmalı.", "travel")
        return _arrive(session)
    if choice == "stop":
        if journey.get("status") != "pending":
            return _fail("Durdurulacak bekleyen bir yolculuk yok.", "travel")
        state["journey"]["status"] = "stopped"
        return _reply("Yolculuğu durdurdun. Olduğun yerde kaldın.", "travel")
    state["journey"] = None
    return _reply("Yolculuktan vazgeçtin. Olduğun yerde kaldın.", "travel")


def _trigger_trap(session: Any) -> str:
    state = session.world_state[KEY]
    if "trap_wire" not in state["discoveries"]:
        state["discoveries"].append("trap_wire")
    state["trap_states"]["trap_wire"] = "triggered"
    damage = TRAPS["trap_wire"]["damage"]
    _hurt(session, damage)
    return f"Gerili tel boşandı ve {damage} delici hasar aldın."


def _traverse(session: Any, exit_id: str) -> dict[str, Any]:
    world = session.world_state
    definition = EXITS.get(exit_id)
    if definition is None or not _visible_exit(world, definition):
        return _fail("Buradan bu geçide gidemezsin.")
    state = world[KEY]
    door_id = definition.get("door_id")
    if door_id:
        door = _world_door(world, door_id)
        if door is None or door["locked"] or not door["open"]:
            return _fail(DOORS[door_id]["name"] + " kapalı.")
    hazard_id = definition.get("hazard_id")
    if hazard_id and state["hazard_states"][hazard_id] == "active":
        return _fail(HAZARDS[hazard_id]["name"] + " geçidi kapatıyor.")
    trap_id = definition.get("trap_id")
    note = ""
    if trap_id and state["trap_states"][trap_id] in {"hidden", "detected"}:
        note = " " + _trigger_trap(session)
        return _reply("Geçit tuzak yüzünden kapanmadı, ama ilerleyemedin." + note, "exploration", success=False)
    world["location"] = definition["to"]
    if definition["to"] not in state["known"]:
        state["known"].append(definition["to"])
    return _reply(LOCATIONS[definition["to"]]["name"] + " içine geçtin." + note, "exploration")


def _door(session: Any, door_id: str, operation: str) -> dict[str, Any]:
    world = session.world_state
    definition = DOORS.get(door_id)
    if definition is None or definition["location"] != world.get("location"):
        return _fail("Bu kapı burada değil.")
    door = _world_door(world, door_id)
    if door is None:
        return _fail("Bu kapı burada değil.")
    if operation == "unlock":
        if not door["locked"]:
            return _reply(definition["name"] + " zaten kilitli değil.", "exploration")
        check = _check(session, "Sleight of Hand", 15)
        if not check["success"]:
            return _reply(definition["name"] + " kilidi açılmadı.", "exploration", success=False, check=check)
        door["locked"] = False
        door["open"] = True
        return _reply(definition["name"] + " kilidini açtın.", "exploration", check=check)
    if operation == "open":
        if door["locked"]:
            return _fail(definition["name"] + " kilitli.")
        door["open"] = True
        return _reply(definition["name"] + " açıldı.", "exploration")
    if operation == "close":
        door["open"] = False
        return _reply(definition["name"] + " kapandı.", "exploration")
    return _fail("Bu kapı için açık, kapalı veya kilit aç komutunu kullan.")


def _search(session: Any) -> dict[str, Any]:
    world = session.world_state
    state = world[KEY]
    location = world.get("location")
    attempts = state["search_attempts"].get(location, 0)
    if attempts >= 2:
        return _fail("Bu odayı daha fazla aramak yeni bir şey göstermiyor.")
    check = _check(session, "Perception", 15)
    state["search_attempts"][location] = attempts + 1
    if not check["success"]:
        return _reply("Aradın, ama yeni bir ipucu çıkmadı.", "exploration", success=False, check=check)
    pending = [
        identity for identity, clue in DISCOVERIES.items()
        if clue["location"] == location and identity not in state["discoveries"]
    ]
    if not pending:
        return _reply("Burada bulunacak başka bir ipucu kalmadı.", "exploration", check=check)
    found = pending[0]
    state["discoveries"].append(found)
    if found == "trap_wire":
        state["trap_states"]["trap_wire"] = "detected"
    if found == "secret_passage":
        _publish_door(world, "door_secret")
    return _reply(DISCOVERIES[found]["name"] + " dikkatini çekti.", "exploration", check=check)


def _begin(session: Any) -> dict[str, Any]:
    world = session.world_state
    if _state(world) is not None:
        return _fail("Bu macera zaten seçili.")
    origin = world.get("location")
    locations = world.get("locations")
    if not isinstance(origin, str) or not isinstance(locations, dict) or origin not in locations or origin in ROOM_IDS:
        return _fail("Patika, bilinen bir yerleşimden başlamalı.")
    _install(world)
    world[KEY] = _initial(origin)
    world["location"] = CAMP
    _publish_door(world, "door_oak")
    _publish_door(world, "door_vault")
    validate(world)
    return _reply("Taş patikanın kampına geçtin. İleriye tek bir patika görünüyor.", "exploration")


_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def _fold(value: str) -> str:
    return value.casefold().replace("\u0307", "").translate(_FOLD)


def _natural_door(session: Any, message: str) -> dict[str, Any] | None:
    world = session.world_state if isinstance(getattr(session, "world_state", None), dict) else None
    if world is None or _state(world) is None:
        return None
    if "?" in message:
        return None
    folded = _fold(message)
    if "kapi" not in folded and "kilit" not in folded:
        return None
    if _incapacitated(session):
        return _fail("Bilincin kapalı; bu hamleyi yapamazsın.")
    if _combat_active(session):
        return _fail("Önce çatışmayı çöz.")
    if re.search(r"\b(?:kilit\w*)\b", folded) and re.search(r"\bac\w*", folded):
        operation = "unlock"
    elif re.search(r"\bkapat\w*", folded):
        operation = "close"
    elif re.search(r"\bac\w*", folded):
        operation = "open"
    else:
        return None
    visible = _visible_doors(world)
    named = [door for door in visible if _fold(str(door.get("name", ""))) in folded]
    if len(named) == 1:
        return _door(session, named[0]["id"], operation)
    if not named and len(visible) == 1:
        return _door(session, visible[0]["id"], operation)
    if not named and len(visible) > 1:
        return _fail("Hangi kapıyı seçtiğini belirt.")
    return None


def resolve_turn(session: Any, message: str) -> dict[str, Any] | None:
    if not isinstance(message, str):
        return None
    natural = _natural_door(session, message)
    if natural is not None:
        return natural
    parts = message.strip().split()
    if not parts or parts[0] not in {"/explore", "/travel"}:
        return None
    if _incapacitated(session):
        return _fail("Bilincin kapalı; bu hamleyi yapamazsın.")
    if _combat_active(session):
        return _fail("Önce çatışmayı çöz.", "travel" if parts[0] == "/travel" else "exploration")
    world = session.world_state
    if parts == ["/explore", "begin"]:
        return _begin(session)
    if _state(world) is None:
        return _fail("Önce taş patikanın macerasını seç.")
    validate(world)
    if parts == ["/explore", "look"] or parts == ["/travel", "pace"]:
        text = describe(world)
        if parts[0] == "/travel":
            text = {"fast": "Hızlı", "normal": "Normal", "slow": "Yavaş"}[world[KEY]["pace"]] + " tempo seçili. " + text
        return _reply(text, "exploration" if parts[0] == "/explore" else "travel")
    if len(parts) == 3 and parts[:2] == ["/travel", "pace"] and parts[2] in LEG_SECONDS:
        world[KEY]["pace"] = parts[2]
        label = {"fast": "Hızlı", "normal": "Normal", "slow": "Yavaş"}[parts[2]]
        return _reply(label + " tempoyu seçtin.", "travel")
    if len(parts) == 3 and parts[:2] == ["/travel", "supplies"] and parts[2] in {"enabled", "disabled"}:
        world[KEY]["supplies_enabled"] = parts[2] == "enabled"
        return _reply("Erzak takibi " + ("açık." if parts[2] == "enabled" else "kapalı."), "travel")
    if len(parts) == 3 and parts[:2] == ["/travel", "go"]:
        origin = world.get("location")
        destination = parts[2]
        if destination not in ROUTES.get(origin, ()):
            return _fail("Buradan bu konuma bilinen bir rota yok.", "travel")
        if world[KEY].get("journey"):
            return _fail("Önce bekleyen yolculuk kararını ver.", "travel")
        world[KEY]["journey"] = {"origin": origin, "destination": destination, "status": "pending"}
        return _reply(
            "Yola çıkmak üzeresin. Devam, dur veya geri dön.",
            "travel",
            journey=dict(world[KEY]["journey"]),
        )
    if parts in (["/travel", "continue"], ["/explore", "decision", "continue"]):
        return _decision(session, "continue")
    if parts in (["/travel", "stop"], ["/explore", "decision", "stop"]):
        return _decision(session, "stop")
    if parts in (["/travel", "return"], ["/explore", "decision", "return"]):
        return _decision(session, "return")
    if parts == ["/explore", "search"]:
        return _search(session)
    if len(parts) == 3 and parts[:2] == ["/explore", "exit"]:
        return _traverse(session, parts[2])
    if len(parts) == 4 and parts[:2] == ["/explore", "door"]:
        return _door(session, parts[2], parts[3])
    if parts == ["/explore", "trap", "trap_wire", "disarm"]:
        state = world[KEY]
        if state["trap_states"]["trap_wire"] != "detected" or world.get("location") != ENTRY:
            return _fail("Burada etkisiz hale getirebileceğin görünen bir tuzak yok.")
        check = _check(session, "Sleight of Hand", 15)
        if not check["success"]:
            return _reply("Teli etkisiz hale getiremedin.", "exploration", success=False, check=check)
        state["trap_states"]["trap_wire"] = "disarmed"
        return _reply("Gerili teli etkisiz hale getirdin.", "exploration", check=check)
    if parts == ["/explore", "interact", "lever"]:
        if world.get("location") != HALL:
            return _fail("Bu kaldıraç burada değil.")
        world[KEY]["hazard_states"]["hazard_rubble"] = "neutralized"
        return _reply("Kaldıraç molozu kenara çekti.", "exploration")
    return _fail("Ne yapmak istediğini ve hangi geçidi seçtiğini belirt.")
