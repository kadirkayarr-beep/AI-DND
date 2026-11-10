"""The weapon in the player's hand and which weapon an attack uses (Dilim 2, Task 14; item 39).

D&D 2024: a weapon can be drawn as part of the attack. An empty hand draws the first weapon in the bag (melee first),
a weapon the player does not own is a punch, and nothing at all is a punch too. This module only reads the hands and
the bag and decides; the hand itself changes only through the existing atomic owner, `equipment_rules`.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal

import character_progression
import equipment_economy
import equipment_rules
from weapon_catalog import lookup


@dataclass(frozen=True)
class GearResult:
    status: Literal["drawn", "already_held", "not_a_weapon", "not_in_bag", "refused",
                    "donned", "not_down", "no_shield", "hands_full", "no_action"]
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


def settle_shield(world, character) -> int:
    """A shield put down by a two-handed weapon (`world["shield_down"]`, written by `equipment_economy`) takes its
    Armor Class share off the character once; the share is recorded and returned. Anything else returns 0."""
    down = world.get("shield_down")
    if not isinstance(down, dict) or down.get("ac_bonus") is not None:
        return 0
    share = character_progression.shield_share(character)
    character["armor_class"] -= share
    down["ac_bonus"] = share
    return share


def don_shield(world, character, *, session=None) -> GearResult:
    """Put the shield a two-handed weapon made `settle_shield` put down back on the arm, in one step (Dilim 4A, Task 5):
    the Armor Class share returns to the character and the record `world["shield_down"]` is cleared together. A creation
    shield has no hand entry, so `equipment` does not change. Anything but a clean "donned" changes nothing: the whole
    result is checked on a copy first and the live world and character are written last. In a fight (`session` given,
    combat active) it is the Utilize action, spent once; none left is "no_action" and nothing changes."""
    down = world.get("shield_down")
    bonus = down.get("ac_bonus") if isinstance(down, dict) else None
    if type(bonus) is not int or bonus < 0:
        return GearResult("not_down", None)  # no shield put down, or its share was never taken off
    shield = next((item for item in _bag(world) if item.get("item_id") == down.get("item_id")), None)
    if shield is None:
        return GearResult("no_shield", None)  # the recorded shield is not in the bag any more
    hands = world.get("equipment") or {}
    main = hands.get("main_hand")
    weapon = wielded(world)
    if hands.get("off_hand") is not None or (main is not None and (weapon is None or any(
            word in _data(weapon).get("properties", []) for word in ("two_handed", "two-handed")))):
        return GearResult("hands_full", shield)  # a two-handed weapon (or a hand not read) leaves no arm for it
    candidate_world, candidate = copy.deepcopy(world), copy.deepcopy(character)
    del candidate_world["shield_down"]
    candidate["armor_class"] += bonus
    if (candidate.get("armor_origin") is not None
            and character_progression._verified_armor_origin(candidate, candidate_world) is None):
        return GearResult("not_down", None)  # the total would not follow its origin: the save would not load
    if session is not None and world.get("combat", {}).get("active"):
        import action_economy
        try:
            action_economy.consume_action(session, "player", "utilize")  # validates first; raises before any change
        except action_economy.CombatRequestError:
            return GearResult("no_action", shield)
    del world["shield_down"]
    character["armor_class"] += bonus  # the character last
    return GearResult("donned", shield)


def draw(world, item_id, *, character=None) -> GearResult:
    """Take a bag weapon into the main hand through `equipment_rules` (a two-handed one frees the off hand and puts
    the shield down: with `character` given, its Armor Class falls by the shield's share)."""
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
        delta = equipment_rules.resolve_item_use(candidate, main, {"use": "unequip", "hand": "main_hand"})
        if delta["status"] != "applied":
            return GearResult("refused", item)  # the owner will not free the hand: nothing changes
    delta = equipment_rules.resolve_item_use(candidate, item_id, {"use": "equip", "hand": "main_hand"})
    if delta["status"] != "applied":
        return GearResult("refused", item)  # a bag weapon the owner will not put in hand: nothing changes
    # Only what changed is written back, so a caller holding a live record of the world (the turn resources in
    # `world["combat"]`) keeps writing to the world itself.
    for key in [key for key in world if key not in candidate]:
        del world[key]
    for key, value in candidate.items():
        if key not in world or world[key] != value:
            world[key] = value
    if character is not None:
        settle_shield(world, character)
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


def attack_weapon(world, requested_item_id=None, *, requested_name=None, melee=True, character=None) -> GearChoice:
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
    result = draw(world, item["item_id"], character=character)
    if result.status != "drawn":  # the owner would not change the hand: a punch, the hands as they were
        return GearChoice("unarmed", None, None, None)
    return GearChoice("drawn", result.item, _data(result.item), None)
