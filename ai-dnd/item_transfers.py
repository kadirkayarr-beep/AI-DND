"""Ordinary items change hands only from where they really are; a valued or held one needs a card (C9, K5).

A transfer never makes an item: it moves one existing instance from its real owner (the player, an NPC, the
ground here or a surface here) to another, on a copy first and then the same steps on the live world. A held item
leaves the hand through `equipment_economy.clear_equipment`; armor and a shield never move this way. The one
transfer is recorded in the economic ledger under its operation id. The one maker is `pick_up_told`: a worthless
thing this scene's narration showed, made once and taken by such a transfer. No network, model or database call is made.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal

import equipment_economy
import economic_actions
from economic_actions import AssetDelta, EconomicState


@dataclass(frozen=True)
class ItemTransferResult:
    operation_id: str
    status: Literal["applied", "refused"]
    reason_code: str | None
    item_id: str
    source_id: str
    recipient_id: str
    count: int
    asset_deltas: list[AssetDelta]
    public_summary: str


def is_coin_label(item: Any) -> bool:
    """"8 Altın" written in the pack is money, counted by the purse's own rule, never an item to hand over."""
    import bold_acts
    probe = {"currency": {}, "inventory": [copy.deepcopy(item)]}
    bold_acts.settle_coin_labels(probe)
    return not probe["inventory"]


def item_needs_card(world: dict[str, Any], item: dict[str, Any] | str) -> bool:
    """A priced, magic, counter-priced or held item goes only with a card; a plain thing with no worth does not.

    Read on a materialized copy. A catalog price that cannot be read (other than an out-of-scope magic item, which
    always needs a card) counts as no catalog price: the counter's price list and the hands then decide.
    """
    import shop_trade
    import weapon_catalog
    candidate = copy.deepcopy(world)
    try:
        equipment_economy.materialize(candidate)
    except equipment_economy.EquipmentError:
        pass
    if isinstance(item, str):
        weapon = weapon_catalog.lookup(item)
        record: dict[str, Any] = {"name": item, **({"weapon_id": weapon["weapon_id"]} if weapon else {})}
    elif isinstance(item, dict):
        identity = item.get("item_id")
        record = next((found for _, items in equipment_economy.containers(candidate) for found in items
                       if identity and isinstance(found, dict) and found.get("item_id") == identity), item)
    else:
        return False
    try:
        if equipment_economy.price(record) > 0:
            return True
    except equipment_economy.EquipmentError as error:
        if str(error) == "magic_item_out_of_scope":
            return True
    priced = shop_trade.priced_in(record.get("name"))
    if priced is not None and priced[2] > 0:
        return True
    hands = candidate.get("equipment") if isinstance(candidate.get("equipment"), dict) else {}
    held = {hands.get("main_hand"), hands.get("off_hand")} - {None}
    return bool(record.get("item_id") in held or (not record.get("item_id") and record.get("name") in held))


def _owner_list(world: dict[str, Any], owner_id: str, *, create: bool) -> list[Any] | None:
    """The real container of this owner; the ground and a surface only where the player stands."""
    if owner_id == "player":
        return world.setdefault("inventory", []) if create else world.get("inventory")
    if owner_id.startswith("ground:"):
        place = owner_id.removeprefix("ground:")
        if place != world.get("location"):
            return None
        grounds = world.setdefault("ground_items_by_location", {}) if create else world.get(
            "ground_items_by_location") or {}
        return grounds.setdefault(place, []) if create else grounds.get(place)
    if owner_id.startswith("surface:"):
        feature_id = owner_id.removeprefix("surface:")
        equipment_economy._surface_feature(world, feature_id)
        shelves = world.setdefault("surface_items", {}) if create else world.get("surface_items") or {}
        return shelves.setdefault(feature_id, []) if create else shelves.get(feature_id)
    npcs = [npc for npc in world.get("npcs", []) if isinstance(npc, dict) and npc.get("id") == owner_id]
    if len(npcs) != 1:
        return None
    return npcs[0].setdefault("inventory", []) if create else npcs[0].get("inventory")


def _count(items: list[Any], name: str) -> int:
    return sum(1 for item in items if str(equipment_economy.label(item)) == name)


def _move(world: dict[str, Any], *, item_id: str, source_id: str, recipient_id: str,
          operation_id: str) -> list[AssetDelta]:
    equipment_economy.materialize(world)
    source = _owner_list(world, source_id, create=False)
    if not isinstance(source, list):
        equipment_economy.fail("item_source_unknown")
    item = equipment_economy.one([entry for entry in source if isinstance(entry, dict)], item_id)
    if equipment_economy.is_armor_or_shield(item):
        equipment_economy.fail("armor_owner_required")
    if is_coin_label(item):
        equipment_economy.fail("coin_is_money")
    destination = _owner_list(world, recipient_id, create=True)
    if not isinstance(destination, list) or destination is source:
        equipment_economy.fail("item_recipient_unknown")
    name = str(item["name"])
    source_before, recipient_before = _count(source, name), _count(destination, name)
    actor = source_id if source_id == "player" or not source_id.startswith(("ground:", "surface:")) else "ground"
    equipment_economy.clear_equipment(world, actor, item)
    source.remove(item)
    destination.append(item)
    equipment_economy._prune_surfaces(world)
    flags = world.setdefault("flags", {})
    operations = flags.setdefault("economic_ledger", {}).setdefault("operations", {})
    operations[operation_id] = {"purpose": "item_transfer", "item_id": item_id, "source_id": source_id,
                                "recipient_id": recipient_id, "net_debit_cp": 0,
                                "turn_index": flags.get("turn_index", 0)}
    economic_actions.trim_operations(operations)
    return [AssetDelta(owner_id=source_id, asset_kind="item", asset_id=name, before=source_before,
                       after=source_before - 1),
            AssetDelta(owner_id=recipient_id, asset_kind="item", asset_id=name, before=recipient_before,
                       after=recipient_before + 1)]


def transfer_existing_item(state: EconomicState, *, item_id: str, source_id: str, recipient_id: str, count: int,
                           operation_id: str) -> ItemTransferResult:
    """Move one existing item from its real owner, or nothing at all. It never makes an item."""
    world = state.world

    def refused(reason: str) -> ItemTransferResult:
        return ItemTransferResult(operation_id=operation_id, status="refused", reason_code=reason, item_id=item_id,
                                  source_id=source_id, recipient_id=recipient_id, count=count, asset_deltas=[],
                                  public_summary="Eşya yerinden oynamadı.")

    if not all(isinstance(value, str) and value for value in (item_id, source_id, recipient_id, operation_id)):
        return refused("invalid_transfer")
    if type(count) is not int or count != 1:
        return refused("stack_quantity_unsupported")
    if source_id == recipient_id:
        return refused("item_recipient_unknown")
    ledger = (world.get("flags") or {}).get("economic_ledger")
    if isinstance(ledger, dict) and operation_id in (ledger.get("operations") or {}):
        return refused("operation_id_reused")
    candidate = copy.deepcopy(world)
    try:
        deltas = _move(candidate, item_id=item_id, source_id=source_id, recipient_id=recipient_id,
                       operation_id=operation_id)
        equipment_economy.validate_world(candidate)
    except equipment_economy.EquipmentError as error:
        return refused(str(error))
    _move(world, item_id=item_id, source_id=source_id, recipient_id=recipient_id, operation_id=operation_id)
    return ItemTransferResult(operation_id=operation_id, status="applied", reason_code=None, item_id=item_id,
                              source_id=source_id, recipient_id=recipient_id, count=count, asset_deltas=deltas,
                              public_summary=f"{deltas[0].asset_id} el değiştirdi.")


def transfer_now(world: dict[str, Any], *, item_id: str, source_id: str, recipient_id: str) -> ItemTransferResult:
    """A transfer with the ledger's next `item_transfer` id; the live counter moves only when the item does."""
    import economic_actions
    seq = ((world.get("flags") or {}).get("economic_ledger") or {}).get("operation_seq", 0)
    peek = {"flags": {"economic_ledger": {"operation_seq": seq}}}
    operation_id = economic_actions.operation_id_for(peek, "item_transfer")
    result = transfer_existing_item(EconomicState(world=world, character=None), item_id=item_id, source_id=source_id,
                                    recipient_id=recipient_id, count=1, operation_id=operation_id)
    if result.status == "applied":
        world.setdefault("flags", {}).setdefault("economic_ledger", {})["operation_seq"] = (
            peek["flags"]["economic_ledger"]["operation_seq"])
    return result


NARRATED_PICKUPS = "narrated_pickups"  # flags: 'place:stem' of each told thing already made, so a mention makes one
_NARRATED_KEPT = 64


def pick_up_told(world: dict[str, Any], name: str, *, stem: str) -> str | None:
    """A worthless thing the narrator showed here and nobody holds: made once on the ground here, then moved to
    the player by one item transfer. The caller has read that this scene's narration names it and the line takes it.

    Coin, a coin label, armor, a weapon, a priced or magic thing, one already held or lying anywhere, a second take
    of the same mention, or a take in a fight makes nothing (Kadir, 2026-11-03).
    """
    import living_world
    place = world.get("location")
    if (not isinstance(place, str) or not place or (world.get("combat") or {}).get("active")
            or not isinstance(name, str) or not name.strip() or len(name.strip()) > 200 or not stem):
        return None
    name = name.strip()
    if is_coin_label(name) or equipment_economy.is_armor_or_shield(name) or item_needs_card(world, name):
        return None
    mention = f"{place}:{stem}"
    if mention in (((world.get("flags") or {}).get(NARRATED_PICKUPS)) or []):
        return None
    candidate = copy.deepcopy(world)
    try:
        equipment_economy.materialize(candidate)
    except equipment_economy.EquipmentError:
        return None
    if any(any(word.startswith(stem) for word in living_world.normalize_text(equipment_economy.label(item)).split())
           for _, items in equipment_economy.containers(candidate) for item in items or []):
        return None
    if _make_and_take(candidate, name, place, mention) is None:
        return None
    return _make_and_take(world, name, place, mention)


def _make_and_take(world: dict[str, Any], name: str, place: str, mention: str) -> str | None:
    """The one told thing laid where the player stands and moved to the bag by `transfer_now`, or nothing at all."""
    equipment_economy.materialize(world)
    reserved = {item.get("item_id") for _, items in equipment_economy.containers(world)
                for item in items if isinstance(item, dict)}
    before = world.get("item_sequence", 0)
    sequence = before if type(before) is int and before >= 0 else 0
    while True:
        sequence += 1
        item_id = f"item_{sequence:06d}"
        if item_id not in reserved:
            break
    grounds = world.setdefault("ground_items_by_location", {})
    had_ground = place in grounds
    ground = grounds.setdefault(place, [])
    record = {"item_id": item_id, "name": name, "source": "narrated_scene", "source_place_id": place}
    ground.append(record)
    world["item_sequence"] = sequence
    moved = transfer_now(world, item_id=item_id, source_id=f"ground:{place}", recipient_id="player")
    if moved.status != "applied":
        if record in ground:
            ground.remove(record)
        world["item_sequence"] = before
        if not had_ground and not ground:
            del grounds[place]
        return None
    if not had_ground and not ground:
        del grounds[place]
    made = world.setdefault("flags", {}).setdefault(NARRATED_PICKUPS, [])
    made.append(mention)
    del made[:-_NARRATED_KEPT]
    return name


def real_thing_here(world: dict[str, Any], stem: str) -> tuple[str, dict[str, Any]] | None:
    """An existing thing on the ground or a surface where the player stands whose name the stem names."""
    import living_world
    if not stem:
        return None
    place = world.get("location")
    found: list[tuple[str, dict[str, Any]]] = []
    for item in ((world.get("ground_items_by_location") or {}).get(place) or []):
        found.append((f"ground:{place}", item))
    for feature_id, items in (world.get("surface_items") or {}).items():
        try:
            equipment_economy._surface_feature(world, feature_id)
        except equipment_economy.EquipmentError:
            continue
        found.extend((f"surface:{feature_id}", item) for item in items or [])
    for owner, item in found:
        if any(word.startswith(stem) for word in living_world.normalize_text(equipment_economy.label(item)).split()):
            if isinstance(item, dict):
                return owner, item
            equipment_economy.materialize(world)  # an old save's plain string gets its id before it moves
            return real_thing_here(world, stem)
    return None
