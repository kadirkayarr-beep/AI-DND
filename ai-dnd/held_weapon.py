"""Held-weapon identity for the existing attack roll.

The attack still resolves in the combat owner. This module only answers which
inventory item is in hand, including the package longsword name.
"""

from __future__ import annotations

from typing import Any


SWORD = "Kılıç"
_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})
SWORD_ALIASES = frozenset({
    "kilic", "kilici", "kilicimla", "uzun kilic", "uzun kilici",
    "longsword", "long sword",
})


def _fold(value: str) -> str:
    return value.casefold().replace("\u0307", "").translate(_FOLD)


def _labels(item: Any) -> list[str]:
    if isinstance(item, str) and item.strip():
        return [item.strip()]
    if isinstance(item, dict):
        labels = []
        for key in ("item_id", "weapon_id", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                labels.append(value.strip())
        return labels
    return []


def _is_sword(item: Any) -> bool:
    return any(_fold(label) in SWORD_ALIASES for label in _labels(item))


def _identity(item: Any) -> str | None:
    if isinstance(item, dict):
        item_id = item.get("item_id")
        if isinstance(item_id, str) and item_id.strip():
            return item_id.strip()
    if isinstance(item, str) and item.strip():
        return item.strip()
    return None


def _matches(item: Any, identity: str) -> bool:
    return _identity(item) == identity


def sword_record(item: Any) -> dict[str, str]:
    """Stable sword record. An existing item_id is kept."""
    if isinstance(item, dict) and _identity(item) and _is_sword(item):
        name = item.get("name") if isinstance(item.get("name"), str) and item["name"].strip() else "Kılıç"
        weapon_id = item.get("weapon_id") if isinstance(item.get("weapon_id"), str) else "longsword"
        return {"item_id": _identity(item), "weapon_id": weapon_id, "name": name.strip()}
    name = item.strip() if isinstance(item, str) and item.strip() else "Kılıç"
    return {"item_id": "sword-" + _fold(name).replace(" ", "-"), "weapon_id": "longsword", "name": name}


def has_sword(items: Any) -> bool:
    return isinstance(items, list) and any(_is_sword(item) for item in items)


def held_sword(world: dict[str, Any]) -> Any:
    """The sword in hand, or the first sword when no hand record exists."""
    inventory = world.get("inventory") if isinstance(world, dict) else None
    if not isinstance(inventory, list):
        return None
    equipment = world.get("equipment") if isinstance(world, dict) else None
    if isinstance(equipment, dict) and isinstance(equipment.get("main_hand"), str):
        held = equipment["main_hand"]
        for item in inventory:
            if _matches(item, held) and _is_sword(item):
                return item
        return None
    for item in inventory:
        if _is_sword(item):
            return item
    return None


def release_hand(world: dict[str, Any], item: Any) -> None:
    equipment = world.get("equipment") if isinstance(world, dict) else None
    if isinstance(equipment, dict) and equipment.get("main_hand") == _identity(item):
        equipment["main_hand"] = None


def validate_saved(world: dict[str, Any]) -> None:
    if not isinstance(world, dict) or "equipment" not in world:
        return
    equipment = world.get("equipment")
    inventory = world.get("inventory")
    if (
        not isinstance(equipment, dict)
        or set(equipment) != {"main_hand", "off_hand"}
        or not isinstance(inventory, list)
        or (equipment["off_hand"] is not None and not isinstance(equipment["off_hand"], str))
    ):
        raise ValueError("Tutulan silah kaydı geçersiz.")
    held = equipment["main_hand"]
    if held is None:
        return
    if not isinstance(held, str) or not held.strip():
        raise ValueError("Tutulan silah kaydı geçersiz.")
    matches = [item for item in inventory if _matches(item, held)]
    if len(matches) != 1 or not _is_sword(matches[0]):
        raise ValueError("Tutulan silah kaydı geçersiz.")


def attack_weapon_name(world: dict[str, Any]) -> str | None:
    """Return the canonical sword name, or None when the held item is not one."""
    if not isinstance(world, dict) or not isinstance(world.get("inventory"), list):
        return None
    inventory = world["inventory"]
    if "equipment" not in world:
        return SWORD if any(_is_sword(item) for item in inventory) else None
    equipment = world.get("equipment")
    if not isinstance(equipment, dict) or set(equipment) != {"main_hand", "off_hand"}:
        return None
    held = equipment.get("main_hand")
    if not isinstance(held, str) or not held.strip():
        return None
    matches = [item for item in inventory if _matches(item, held)]
    if len(matches) != 1 or not _is_sword(matches[0]):
        return None
    return SWORD


def resolve_turn(session: Any, message: str) -> dict[str, Any] | None:
    if not isinstance(message, str):
        return None
    parts = message.strip().split()
    if not parts or parts[0] != "/equip":
        return None
    world = session.world_state
    inventory = world.get("inventory")
    if not isinstance(inventory, list):
        return {
            "action": "equip",
            "status": "resolved",
            "success": False,
            "direct_response": "Envanter okunamıyor.",
            "state_changes": [],
        }
    if parts == ["/equip", "clear"]:
        world["equipment"] = {"main_hand": None, "off_hand": None}
        return {
            "action": "equip",
            "status": "resolved",
            "success": True,
            "direct_response": "Elini boşalttın.",
            "state_changes": ["world_state.equipment"],
        }
    if len(parts) < 2:
        return {
            "action": "equip",
            "status": "resolved",
            "success": False,
            "direct_response": "Hangi silahı eline aldığını belirt.",
            "state_changes": [],
        }
    token = " ".join(parts[1:])
    folded = _fold(token)
    matches = [
        item for item in inventory
        if _is_sword(item) and any(_fold(label) == folded or label == token for label in _labels(item))
    ]
    if len(matches) != 1:
        return {
            "action": "equip",
            "status": "resolved",
            "success": False,
            "direct_response": "Elindeki silahı tek bir envanter kaydıyla belirt.",
            "state_changes": [],
        }
    record = sword_record(matches[0])
    index = inventory.index(matches[0])
    inventory[index] = record
    identity = record["item_id"]
    world["equipment"] = {"main_hand": identity, "off_hand": None}
    return {
        "action": "equip",
        "status": "resolved",
        "success": True,
        "direct_response": "Kılıcı eline aldın.",
        "state_changes": ["world_state.equipment"],
        "main_hand": identity,
    }
