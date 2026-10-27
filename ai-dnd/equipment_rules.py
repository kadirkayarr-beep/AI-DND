"""C08: structured item use and transfer over the existing equipment owner (`equipment_economy`), not a second inventory.

`resolve_item_use` and `inventory_transfer` map a structured request onto the owner's own atomic operation (consent,
identity, hand and armor rules all stay there), commit only when the whole operation and `validate_world` succeed, and
return one delta shape: `{"status": "applied" | "rejected", "reason", "changes", "effects_pending"}`. A rejection leaves the
world byte-for-byte unchanged, so repeating an applied action is rejected (the item is no longer there) and has no second effect.

This is the use/transfer kernel only. It does not claim any PHB equipment entry is complete: catalog coverage belongs to C04.
`effects_pending` names the item when it is anything but a plain catalog weapon (its own effects are not modelled here).
"""
from __future__ import annotations

import copy
from typing import Any

import equipment_economy as economy

_PLAYER = "player"
_USES = {"equip", "unequip", "drop", "take", "place"}


def _delta(status: str, reason: str | None = None, changes: list[dict[str, Any]] | None = None,
           effects_pending: list[str] | None = None) -> dict[str, Any]:
    return {"status": status, "reason": reason, "changes": changes or [], "effects_pending": effects_pending or []}


def _locations(world: dict[str, Any]) -> dict[str, tuple[str, str]]:
    found = {}
    for owner, items in economy.containers(world):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("item_id"), str):
                found[item["item_id"]] = (owner, item.get("name", ""))
    return found


def _pending_effects(world: dict[str, Any], item_id: Any) -> list[str]:
    """Anything beyond a plain catalog weapon is moved/held only: its own effects are not modelled by this kernel."""
    for _, items in economy.containers(world):
        for item in items:
            if isinstance(item, dict) and item.get("item_id") == item_id:
                plain = item.get("weapon_id") and not (item.get("magical") or item.get("magic_item_id")
                                                       or item.get("magic_attack_bonus") or item.get("magic_damage_bonus"))
                return [] if plain else [f"effect_unmodelled:{item.get('name', item_id)}"]
    return []


def _commit(world: dict[str, Any], operation: str, args: list[str], item_id: Any = None) -> dict[str, Any]:
    """Run one owner operation on a candidate copy; replace the world only if everything validates."""
    candidate = copy.deepcopy(world)
    pending = _pending_effects(world, item_id)
    try:
        economy._apply(candidate, operation, args)
        economy.validate_world(candidate)
    except (economy.EquipmentError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc) if isinstance(exc, economy.EquipmentError) else "invalid_economic_state"
        return _delta("rejected", reason)
    before, after = _locations(world), _locations(candidate)
    changes = [{"kind": "item_transfer", "item_id": i, "name": after[i][1], "from": before[i][0] if i in before else "catalog",
                "to": after[i][0]} for i in after if before.get(i, (None,))[0] != after[i][0]]
    if not changes:  # equip / unequip change the hands, not the owner
        changes = [{"kind": "equipment", "operation": operation, "args": list(args)}]
    world.clear()
    world.update(candidate)
    return _delta("applied", None, changes, pending)


def _npc(identity: str) -> str:
    return identity[4:] if identity.startswith("npc:") else identity


def inventory_transfer(world: dict[str, Any], source_id: str, target_id: str, item_id: str, quantity: int = 1) -> dict[str, Any]:
    """Move one item between the player and an NPC (`npc:<id>` or the bare id; consent required), the ground, or a lootable owner."""
    if not all(isinstance(v, str) and v for v in (source_id, target_id, item_id)):
        return _delta("rejected", "invalid_transfer_request")
    if type(quantity) is not int or quantity != 1:
        return _delta("rejected", "stack_quantity_unsupported")
    if source_id == target_id:
        return _delta("rejected", "transfer_route_unsupported")
    if source_id == _PLAYER and target_id == "ground":
        return _commit(world, "drop", [item_id], item_id)
    if source_id == "ground" and target_id == _PLAYER:
        return _commit(world, "take", [item_id], item_id)
    if source_id == _PLAYER and not target_id.startswith(("surface:", "container:", "corpse:", "ground")):
        return _commit(world, "give", [item_id, _npc(target_id)], item_id)
    if target_id == _PLAYER and source_id.startswith("npc:"):
        return _commit(world, "receive", [item_id, _npc(source_id)], item_id)
    if target_id == _PLAYER:
        return _commit(world, "loot", [source_id, item_id], item_id)
    return _delta("rejected", "transfer_route_unsupported")


def resolve_item_use(world: dict[str, Any], item_id: str, choice: dict[str, Any]) -> dict[str, Any]:
    """Use an owned item the way the existing owner supports: equip/unequip a hand, drop, take, or place on a surface."""
    use = choice.get("use") if isinstance(choice, dict) else None
    if use not in _USES or not isinstance(item_id, str):
        return _delta("rejected", "unsupported_use")
    if use == "equip":
        return _commit(world, "equip", [item_id, str(choice.get("hand"))], item_id)
    if use == "unequip":
        return _commit(world, "unequip", [str(choice.get("hand"))], item_id)
    if use == "place":
        return _commit(world, "place", [item_id, str(choice.get("surface"))], item_id)
    return _commit(world, use, [item_id], item_id)
