"""The weapon in the player's hand and which weapon an attack uses (Dilim 2, Task 14; item 39).

D&D 2024: a weapon can be drawn as part of the attack. An empty hand draws the first weapon in the bag (melee first),
a weapon the player does not own is a punch, and nothing at all is a punch too. This module only reads the hands and
the bag and decides; the hand itself changes only through the existing atomic owner, `equipment_rules`.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal

import equipment_economy
import equipment_rules
from weapon_catalog import lookup


@dataclass(frozen=True)
class GearResult:
    status: Literal["drawn", "already_held", "not_a_weapon", "not_in_bag"]
    item: dict | None


@dataclass(frozen=True)
class GearChoice:
    kind: Literal["held", "drawn", "unarmed"]
    item: dict | None
    data: dict | None
    missing: str | None   # the catalog label of a weapon asked for but not owned


def label(data: dict) -> str:
    """The name the player sees (today's rule: the longsword is "Kılıç")."""
    return "Kılıç" if data["weapon_id"] == "longsword" else data["name"]


def _data(item) -> dict | None:
    return lookup(item.get("weapon_id") or item.get("name")) if isinstance(item, dict) else None


def _bag(world) -> list[dict]:
    """Bag entries as records; an old unmaterialized name is read as a record without an item_id."""
    return [item if isinstance(item, dict) else {"name": item}
            for item in world.get("inventory") or [] if isinstance(item, (dict, str))]


def _hand_item(world, value) -> dict | None:
    """The owned weapon a hand value names: its item_id, or an old catalog alias one owned weapon matches."""
    if not isinstance(value, str):
        return None
    bag = [item for item in _bag(world) if _data(item)]
    alias = lookup(value)
    matches = ([item for item in bag if item.get("item_id") == value]
               or [item for item in bag if alias and _data(item)["weapon_id"] == alias["weapon_id"]])
    return matches[0] if len(matches) == 1 else None


def wielded(world) -> dict | None:
    """The weapon record in the main hand."""
    return _hand_item(world, (world.get("equipment") or {}).get("main_hand"))


def holds(world, data) -> bool:
    """Is this catalog weapon already in either hand (so an attack with it draws nothing)?"""
    return any(item is not None and _data(item)["weapon_id"] == data["weapon_id"]
               for item in map(lambda value: _hand_item(world, value), (world.get("equipment") or {}).values()))


def weapons_in_bag(world) -> list[dict]:
    """Catalog weapons in bag order, leaving out what is already in a hand."""
    in_hand = [_hand_item(world, value) for value in (world.get("equipment") or {}).values()]
    return [item for item in _bag(world) if _data(item) and item not in in_hand]


def draw(world, item_id) -> GearResult:
    """Take a bag weapon into the main hand through `equipment_rules` (a two-handed one frees the off hand)."""
    item = next((item for item in _bag(world) if item_id is not None and item.get("item_id") == item_id), None)
    if item is None:
        return GearResult("not_in_bag", None)
    if _data(item) is None:
        return GearResult("not_a_weapon", item)
    held = wielded(world)
    if held is not None and held.get("item_id") == item_id:
        return GearResult("already_held", item)
    candidate = copy.deepcopy(world)
    main = (candidate.get("equipment") or {}).get("main_hand")
    if main is not None:  # what was in hand goes back to the bag
        equipment_rules.resolve_item_use(candidate, main, {"use": "unequip", "hand": "main_hand"})
    delta = equipment_rules.resolve_item_use(candidate, item_id, {"use": "equip", "hand": "main_hand"})
    if delta["status"] != "applied":
        raise ValueError(delta["reason"])  # a bag weapon the owner will not put in hand: no state gear can repair
    world.clear()
    world.update(candidate)
    return GearResult("drawn", next(i for i in _bag(world) if i.get("item_id") == item_id))


def not_owned(world, requested_item_id=None, *, requested_name=None) -> str | None:
    """The label of a weapon asked for (by id, or by the model's word given to the catalog) that the player lacks."""
    if requested_item_id is not None:
        if any(item.get("item_id") == requested_item_id and _data(item) for item in _bag(world)):
            return None
        wanted = lookup(requested_item_id)
        return label(wanted) if wanted else None
    wanted = lookup(requested_name) if requested_name else None
    if wanted is None or any(_data(item)["weapon_id"] == wanted["weapon_id"] for item in _bag(world) if _data(item)):
        return None
    return label(wanted)


def attack_weapon(world, requested_item_id=None, *, requested_name=None, melee=True) -> GearChoice:
    """The asked-for weapon (drawn if needed), else the one in hand, else the first bag weapon drawn, else a punch."""
    missing = not_owned(world, requested_item_id, requested_name=requested_name)
    if missing is not None:
        return GearChoice("unarmed", None, None, missing)
    held = wielded(world)
    wanted = lookup(requested_name) if requested_name and requested_item_id is None else None
    asked = [item for item in ([held] if held else []) + weapons_in_bag(world)
             if (requested_item_id is not None and item.get("item_id") == requested_item_id)
             or (wanted and _data(item)["weapon_id"] == wanted["weapon_id"])]
    bag = sorted(weapons_in_bag(world), key=lambda item: (_data(item)["kind"] == "melee") != melee)
    item = asked[0] if asked else held or (bag[0] if bag else None)
    if item is None:
        return GearChoice("unarmed", None, None, None)
    if item == held:
        return GearChoice("held", held, _data(held), None)
    if item.get("item_id") is None:  # an old name in the bag: the owner's lazy migration gives it an item id first
        index = next(i for i, entry in enumerate(world["inventory"]) if entry == item["name"])
        equipment_economy.materialize(world)
        item = world["inventory"][index]
    result = draw(world, item["item_id"])
    return GearChoice("drawn", result.item, _data(result.item), None)
