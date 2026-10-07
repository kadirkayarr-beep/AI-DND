"""Bounded monster sense: one authored traveler, a route, and a stat block.

The snapshot never includes hit points. Distance comes only from authored
pairs. This is not a pathfinding or monster-tactics engine.
"""

from __future__ import annotations

import copy
from typing import Any


KEY = "bounded_sense_v1"
SCENARIO_ID = "courtyard_traveler_v1"
STATBLOCK_ID = "authored_traveler_v1"
NPC_ID = "npc_traveler"
NODES = ("near", "far")
MELEE_REACH_FT = 5
PAIRS = {
    ("near", "far"): {"distance_ft": 30, "visible": True},
    ("far", "near"): {"distance_ft": 30, "visible": True},
    ("near", "near"): {"distance_ft": 5, "visible": True},
    ("far", "far"): {"distance_ft": 5, "visible": True},
}
STATBLOCK = {
    "statblock_id": STATBLOCK_ID,
    "name": "Yolcu",
    "armor_class": 10,
    "hit_points": 4,
    "speed_ft": 30,
    "attack": {"name": "Sopa", "attack_bonus": 2, "damage_die": 4, "damage_dice": 1, "damage_type": "bludgeoning"},
}


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


def _fail(text: str, action: str = "sense") -> dict[str, Any]:
    return _reply(text, action, success=False, state_changes=[])


def validate_saved(world: dict[str, Any]) -> None:
    if isinstance(world, dict) and KEY in world:
        validate(world)


def validate(world: dict[str, Any]) -> None:
    state = world.get(KEY)
    if (
        not isinstance(state, dict)
        or set(state) != {"scenario_id", "version", "location_id", "npc_id", "player_node", "npc_node"}
        or state.get("scenario_id") != SCENARIO_ID
        or state.get("version") != 1
        or not isinstance(state.get("location_id"), str)
        or state.get("npc_id") != NPC_ID
        or state.get("player_node") not in NODES
        or state.get("npc_node") not in NODES
    ):
        raise ValueError("Canavar algı kaydı geçersiz.")
    npc = next(
        (item for item in world.get("npcs", []) if isinstance(item, dict) and item.get("id") == NPC_ID),
        None,
    )
    block = None if npc is None else npc.get("statblock")
    if (
        npc is None
        or npc.get("location") != state["location_id"]
        or not isinstance(block, dict)
        or block.get("statblock_id") != STATBLOCK_ID
        or block.get("armor_class") != STATBLOCK["armor_class"]
        or block.get("hit_points") != STATBLOCK["hit_points"]
        or "current_hp" in block
    ):
        raise ValueError("Canavar algı kaydı geçersiz.")


def _blinded(session: Any) -> bool:
    character = session.character if isinstance(session.character, dict) else {}
    conditions = character.get("conditions", [])
    return isinstance(conditions, list) and "blinded" in conditions


def observable_pair(session: Any) -> dict[str, Any] | None:
    """The same authored pair that /sense and the melee gate both read."""
    world = session.world_state if isinstance(getattr(session, "world_state", None), dict) else {}
    state = world.get(KEY)
    if not isinstance(state, dict):
        return None
    if _blinded(session) or world.get("location") != state.get("location_id"):
        return None
    npc = next(
        (item for item in world.get("npcs", []) if isinstance(item, dict) and item.get("id") == NPC_ID),
        None,
    )
    if npc is None or npc.get("hidden") is True:
        return None
    pair = PAIRS.get((state.get("player_node"), state.get("npc_node")))
    if not isinstance(pair, dict) or pair.get("visible") is not True:
        return None
    return pair


def blocks_melee(session: Any, target_id: str, weapon: dict[str, Any] | None) -> bool:
    world = getattr(session, "world_state", None)
    if target_id != NPC_ID or not isinstance(world, dict) or KEY not in world:
        return False
    reach = MELEE_REACH_FT
    if isinstance(weapon, dict) and "range_ft" in weapon:
        reach = weapon["range_ft"]
    if type(reach) is not int or isinstance(reach, bool) or reach > MELEE_REACH_FT:
        return False
    pair = observable_pair(session)
    if pair is None:
        return True
    return pair["distance_ft"] > MELEE_REACH_FT


def snapshot(session: Any) -> dict[str, Any]:
    """Observable facts only. Hit points stay on the creature record."""
    pair = observable_pair(session)
    if pair is None:
        return {"targets": []}
    return {"targets": [{
        "id": NPC_ID,
        "name": STATBLOCK["name"],
        "distance_ft": pair["distance_ft"],
        "statblock_id": STATBLOCK_ID,
    }]}


def _begin(session: Any) -> dict[str, Any]:
    world = session.world_state
    combat = world.get("combat")
    if isinstance(combat, dict) and combat.get("active") is True:
        return _fail("Önce çatışmayı çöz.", "encounter")
    if KEY in world:
        return _fail("Bu karşılaşma zaten başladı.", "encounter")
    location = world.get("location")
    if not isinstance(location, str) or not location:
        return _fail("Karşılaşma bir konuma bağlı olmalı.", "encounter")
    if any(isinstance(item, dict) and item.get("id") == NPC_ID for item in world.get("npcs", [])):
        return _fail("Bu yolcu zaten sahnede.", "encounter")
    npc = {
        "id": NPC_ID,
        "name": STATBLOCK["name"],
        "role": "traveler",
        "location": location,
        "hostile": True,
        "combat_role": "enemy",
        "combat_status": "active",
        "armor_class": STATBLOCK["armor_class"],
        "max_hp": STATBLOCK["hit_points"],
        "current_hp": STATBLOCK["hit_points"],
        "attack_bonus": STATBLOCK["attack"]["attack_bonus"],
        "damage_die": STATBLOCK["attack"]["damage_die"],
        "damage_dice": STATBLOCK["attack"]["damage_dice"],
        "damage_modifier": 0,
        "hidden": False,
        "reality_layer": "PROCEDURAL_LOCAL_FICTION",
        "statblock": copy.deepcopy(STATBLOCK),
        "memory": [],
    }
    world.setdefault("npcs", []).append(npc)
    world[KEY] = {
        "scenario_id": SCENARIO_ID,
        "version": 1,
        "location_id": location,
        "npc_id": NPC_ID,
        "player_node": "near",
        "npc_node": "far",
    }
    validate(world)
    return _reply("Avluda bir yolcu var. Senden uzakta duruyor.", "encounter")


def resolve_turn(session: Any, message: str) -> dict[str, Any] | None:
    if not isinstance(message, str):
        return None
    parts = message.strip().split()
    if not parts or parts[0] not in {"/sense", "/encounter"}:
        return None
    world = session.world_state
    if parts == ["/encounter", "begin"]:
        return _begin(session)
    if KEY not in world:
        return _fail("Önce avlu karşılaşmasını başlat.", "encounter" if parts[0] == "/encounter" else "sense")
    validate(world)
    if parts == ["/sense"]:
        view = snapshot(session)
        if not view["targets"]:
            return _reply("Seçebildiğin bir yaratık yok.", "sense", success=False, snapshot=view)
        target = view["targets"][0]
        return _reply(
            f"{target['name']} görünüyor. Mesafe {target['distance_ft']} ayak.",
            "sense",
            snapshot=view,
        )
    if parts == ["/encounter", "route"]:
        state = world[KEY]
        pair = PAIRS[(state["player_node"], state["npc_node"])]
        return _reply(
            f"Yazılı rota {pair['distance_ft']} ayak. Görüş: {'açık' if pair['visible'] else 'kapalı'}.",
            "encounter",
            route=dict(pair),
        )
    if len(parts) == 3 and parts[:2] == ["/encounter", "move"] and parts[2] in NODES:
        world[KEY]["player_node"] = parts[2]
        pair = PAIRS[(parts[2], world[KEY]["npc_node"])]
        return _reply(f"Konumun değişti. Mesafe {pair['distance_ft']} ayak.", "encounter", route=dict(pair))
    return _fail("Algı, rota veya yakın/uzak konum komutunu kullan.", "encounter")
