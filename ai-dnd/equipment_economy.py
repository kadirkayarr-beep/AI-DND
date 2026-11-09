"""Transactions over the existing Python possession containers, not a second inventory."""
from __future__ import annotations

import copy
import re
import shlex
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from weapon_catalog import lookup

COIN_VALUES = {"cp": 1, "sp": 10, "ep": 50, "gp": 100, "pp": 1000}

# A refused counter trade tells the player in Turkish, as the shop panel does; the engine code stays in the outcome.
_COUNTER_REFUSALS = {
    "offer_stale": "Fiyat değişti, yeniden onayla.",
    "price_changed": "Fiyat değişti, yeniden onayla.",
    "insufficient_funds": "Kesende bu kadar para yok.",
    "out_of_stock": "Tezgâhta o kadar kalmamış.",
}


class EquipmentError(ValueError):
    pass


class _CardNotPrepared(Exception):
    """The item card was refused or asked about: the turn ends unsuccessful with the card's own words."""


@dataclass(frozen=True)
class ItemCardRequest:
    """`_apply`'s give asks for a card instead of moving a valued or held item; only `execute` reads it."""
    proposal: Any  # economic_actions.EconomicProposal, purpose "item_gift"


def fail(reason):
    raise EquipmentError(reason)


def label(item):
    return item.get("name", "") if isinstance(item, dict) else item


def labels(items):
    return [label(item) for item in items]


def containers(world):
    yield "player", world.get("inventory", [])
    for npc in world.get("npcs", []):
        if isinstance(npc, dict) and "inventory" in npc:
            yield npc.get("id"), npc["inventory"]
    for location, items in world.get("ground_items_by_location", {}).items():
        yield f"ground:{location}", items
    for box in world.get("containers", []):
        if isinstance(box, dict) and "contents" in box:
            yield f'container:{box.get("id")}', box["contents"]
    surfaces = world.get("surface_items", {})
    if isinstance(surfaces, dict):
        for feature_id, items in surfaces.items():
            yield f"surface:{feature_id}", items
    if world.get("ground_items"):
        yield "legacy_ground", world["ground_items"]


SURFACE_ITEM_LIMIT = 8
SURFACE_MARK_LIMIT = 4
SURFACE_MARK_TEXT_LIMIT = 120


def _surface_feature(world, feature_id):
    """A surface is a visible feature of the player's current location."""
    import living_world
    for feature in living_world.visible_features(world, world.get("location")):
        if feature.get("id") == feature_id:
            return feature
    fail("surface_not_available")


def _surface_holding(world, item_id):
    """Feature id of a visible surface that holds this item, else None."""
    for feature_id, items in (world.get("surface_items") or {}).items():
        if any(isinstance(i, dict) and i.get("item_id") == item_id for i in items):
            try:
                _surface_feature(world, feature_id)
            except EquipmentError:
                continue
            return feature_id
    return None


def _valid_mark_text(text):
    return (isinstance(text, str) and bool(text.strip())
            and len(text) <= SURFACE_MARK_TEXT_LIMIT
            and len(text.splitlines()) == 1 and text.isprintable())


def _prune_surfaces(world):
    surfaces = world.get("surface_items")
    if isinstance(surfaces, dict):
        for feature_id in [k for k, v in surfaces.items() if not v]:
            del surfaces[feature_id]


def _validate_surfaces(world):
    feature_ids = {f.get("id") for f in world.get("features", []) if isinstance(f, dict)}
    surfaces = world.get("surface_items", {})
    if not isinstance(surfaces, dict):
        fail("invalid_surface_items")
    for feature_id, items in surfaces.items():
        if (feature_id not in feature_ids or not isinstance(items, list) or not items
                or len(items) > SURFACE_ITEM_LIMIT
                or any(not isinstance(i, dict) for i in items)):
            fail("invalid_surface_items")
    marks = world.get("feature_marks", {})
    if not isinstance(marks, dict):
        fail("invalid_feature_marks")
    seen = set()
    for feature_id, entries in marks.items():
        if (feature_id not in feature_ids or not isinstance(entries, list) or not entries
                or len(entries) > SURFACE_MARK_LIMIT):
            fail("invalid_feature_marks")
        for mark in entries:
            if (not isinstance(mark, dict) or set(mark) != {"mark_id", "text", "turn"}
                    or not isinstance(mark["mark_id"], str) or mark["mark_id"] in seen
                    or not _valid_mark_text(mark["text"])
                    or type(mark["turn"]) is not int or mark["turn"] < 0):
                fail("invalid_feature_marks")
            seen.add(mark["mark_id"])
    sequence = world.get("feature_mark_sequence", 0)
    if type(sequence) is not int or sequence < 0:
        fail("invalid_feature_marks")


def apply_scheduled_surface_effect(world, effect, location_id, event_id):
    """One approved small table event (called only by scheduled_events._occur).

    Everything is checked before anything is mutated, so a refused effect leaves
    the world untouched. The acting NPC must be present and alive in the event's
    location and the feature must belong to it. Only that NPC gets a
    `witnessed:<event_id>` note; the player gets nothing. Returns True if applied.
    """
    import relationships
    npc = next((n for n in world.get("npcs", [])
                if isinstance(n, dict) and n.get("id") == effect["npc_id"]), None)
    feature = next((f for f in world.get("features", [])
                    if isinstance(f, dict) and f.get("id") == effect["feature_id"]), None)
    if (npc is None or feature is None or npc.get("location") != location_id
            or feature.get("location") != location_id or not npc_can_act(npc)):
        return False
    reason = f"witnessed:{event_id}"
    try:
        # Prove the note will fit BEFORE anything moves, so a refusal is clean.
        relationships.note({"relationships": copy.deepcopy(world.get("relationships") or {})},
                           npc["id"], 0, reason)
    except ValueError:
        return False
    feature_id = effect["feature_id"]
    if effect["kind"] == "mark_remove":
        marks = (world.get("feature_marks") or {}).get(feature_id) or []
        target = next((m for m in marks if m.get("mark_id") == effect["mark_id"]), None)
        if target is None:
            return False
        marks.remove(target)
        if not marks:
            del world["feature_marks"][feature_id]
    else:
        shelf = (world.get("surface_items") or {}).get(feature_id) or []
        item = next((i for i in shelf if isinstance(i, dict) and i.get("item_id") == effect["item_id"]), None)
        if item is None or "inventory" in npc and not isinstance(npc["inventory"], list):
            return False
        move(world, item, shelf, npc.setdefault("inventory", []), "ground")
        _prune_surfaces(world)
    relationships.note(world, npc["id"], 0, reason)
    return True


def resolve_table_absence(world, location_id, event_id):
    """Apply one armed absence: the oldest mark, otherwise the first item.

    The acting NPC is the first one who can still act in this place. Returns
    False before any mutation when nobody can act or the table is already clear.
    """
    npc = next((record for record in world.get("npcs", [])
                if isinstance(record, dict) and record.get("location") == location_id
                and npc_can_act(record)), None)
    if npc is None:
        return False
    features = [feature for feature in world.get("features", [])
                if isinstance(feature, dict) and feature.get("location") == location_id
                and isinstance(feature.get("id"), str)]
    marks = []
    for feature in features:
        for mark in (world.get("feature_marks") or {}).get(feature["id"]) or []:
            if isinstance(mark, dict) and isinstance(mark.get("mark_id"), str):
                turn = mark.get("turn", 0)
                marks.append((turn if type(turn) is int else 0, mark["mark_id"], feature["id"]))
    if marks:
        _, mark_id, feature_id = min(marks)
        return apply_scheduled_surface_effect(world, {
            "kind": "mark_remove", "feature_id": feature_id,
            "mark_id": mark_id, "npc_id": npc["id"],
        }, location_id, event_id)
    for feature in sorted(features, key=lambda record: record["id"]):
        item = next((record for record in (world.get("surface_items") or {}).get(feature["id"]) or []
                     if isinstance(record, dict) and isinstance(record.get("item_id"), str)), None)
        if item is not None:
            return apply_scheduled_surface_effect(world, {
                "kind": "surface_item_custody", "feature_id": feature["id"],
                "item_id": item["item_id"], "npc_id": npc["id"],
            }, location_id, event_id)
    return False


def item_transfers(before, after):
    def locations(world):
        found = {}
        for owner, items in containers(world):
            for item in items:
                if isinstance(item, dict) and item.get("item_id"):
                    found[item["item_id"]] = (owner, item.get("name", ""))
        return found

    old, new = locations(before), locations(after)
    transfers = []
    for identity, (owner, name) in new.items():
        previous = old.get(identity)
        if owner == "player" and (previous is None or previous[0] != owner):
            transfers.append({
                "item_id": identity,
                "name": name,
                "from": previous[0] if previous else "catalog",
                "to": owner,
            })
    return transfers


def validate_world(world):
    """Accept legacy strings but never duplicate canonical instance identities."""
    policy = world.get("supplies_policy", {"enabled": False})
    if not isinstance(policy, dict) or set(policy) != {"enabled"} or type(policy["enabled"]) is not bool:
        fail("invalid_supplies_policy")
    accounting = world.get("supplies_accounting")
    if accounting is not None and (
        not isinstance(accounting, dict) or set(accounting) != {"last_day", "missing"}
        or type(accounting["last_day"]) is not int or accounting["last_day"] < 0
        or not isinstance(accounting["missing"], list)
        or any(x not in {"food", "water"} for x in accounting["missing"])
        or len(set(accounting["missing"])) != len(accounting["missing"])
    ):
        fail("invalid_supplies_accounting")
    ids = set()
    for _, items in containers(world):
        if not isinstance(items, list):
            fail("invalid_inventory")
        for item in items:
            if isinstance(item, str):
                continue
            if not isinstance(item, dict):
                fail("invalid_item")
            identity, name = item.get("item_id"), item.get("name")
            if (not isinstance(identity, str) or not identity.strip()
                    or not isinstance(name, str) or not name.strip()
                    or len(identity) > 128 or len(name) > 200):
                fail("invalid_item_identity")
            if type(item.get("quantity", 1)) is not int or item.get("quantity", 1) != 1:
                fail("stack_quantity_unsupported")
            if identity in ids:
                fail("duplicate_item_identity")
            ids.add(identity)
    if type(world.get("item_sequence", 0)) is not int or world.get("item_sequence", 0) < 0:
        fail("invalid_item_sequence")
    wallets = world.get("currency", {})
    if not isinstance(wallets, dict):
        fail("invalid_currency")
    actors = {"player", *(n.get("id") for n in world.get("npcs", [])
                         if isinstance(n, dict) and isinstance(n.get("id"), str))}
    for actor, amount in wallets.items():
        if actor not in actors or type(amount) is not int or amount < 0:
            fail("invalid_currency")
    claimed = world.get("claimed_item_rewards", [])
    if (not isinstance(claimed, list) or any(not isinstance(x, str) for x in claimed)
            or len(set(claimed)) != len(claimed)):
        fail("invalid_reward_receipts")
    _validate_surfaces(world)


def sync_equipment_identities(world):
    """Rewrite unique catalog/name hand aliases to owned item_id after migration.

    Does not equip empty hands from inventory. Ambiguous aliases stay unchanged
    so later owners can reject unresolved identity instead of guessing.
    """
    owners = [("player", world)]
    for npc in world.get("npcs", []):
        if isinstance(npc, dict) and isinstance(npc.get("id"), str):
            owners.append((npc["id"], npc))
    for actor, owner in owners:
        hands = owner.get("equipment")
        if hands is None:
            continue
        if not isinstance(hands, dict) or set(hands) != {"main_hand", "off_hand"}:
            fail("invalid_equipment")
        items = world["inventory"] if actor == "player" else owner.get("inventory", [])
        if not isinstance(items, list):
            continue
        for hand, held in list(hands.items()):
            if held is None:
                continue
            if any(isinstance(item, dict) and item.get("item_id") == held for item in items):
                continue
            weapon = lookup(held)
            matches = [
                item for item in items
                if isinstance(item, dict)
                and (
                    item.get("name") == held
                    or (weapon is not None and item.get("weapon_id") == weapon["weapon_id"])
                )
            ]
            if len(matches) == 1:
                hands[hand] = matches[0]["item_id"]


def materialize(world):
    """Lazy compatible migration; called only inside the atomic transaction."""
    validate_world(world)
    if world.get("ground_items"):
        location = world["location"]
        world.setdefault("ground_items_by_location", {}).setdefault(location, []).extend(
            world["ground_items"])
        world["ground_items"] = []
    reserved = {i["item_id"] for _, items in containers(world)
                for i in items if isinstance(i, dict)}
    sequence = world.get("item_sequence", 0)
    for _, items in containers(world):
        for index, item in enumerate(items):
            if isinstance(item, dict):
                continue
            while True:
                sequence += 1
                identity = f"item_{sequence:06d}"
                if identity not in reserved:
                    break
            record = {"item_id": identity, "name": item}
            weapon = lookup(item)
            if weapon:
                record["weapon_id"] = weapon["weapon_id"]
            items[index] = record
            reserved.add(identity)
    world["item_sequence"] = sequence
    sync_equipment_identities(world)
    validate_world(world)


def one(items, identity):
    found = [i for i in items if i.get("item_id") == identity]
    if len(found) != 1:
        fail("item_not_owned")
    return found[0]


def supply_kind(item):
    """Only explicit canonical units; never infer a filled container."""
    if isinstance(item, dict) and item.get("resource_type") in {"food", "water"}:
        return item["resource_type"]
    return {"Rations (1 day)": "food", "Water (1 gallon)": "water"}.get(label(item))


def consume_daily_supplies(session, *, day=None):
    world = session.world_state
    if not world.get("supplies_policy", {}).get("enabled", False):
        return {}
    if day is not None and day <= world.get("supplies_accounting", {}).get("last_day", -1):
        return {}
    materialize(world)
    inventory = world["inventory"]
    consumed, missing = [], []
    for kind in ("food", "water"):
        item = next((i for i in inventory if supply_kind(i) == kind), None)
        if item:
            inventory.remove(item)
            consumed.append(item["item_id"])
        else:
            missing.append(kind)
    # A whole missing daily unit is an environmental deprivation, not damage
    # fabricated by narration. The existing condition owner owns its effect.
    import weapon_attack
    from api.core_resolution import resolve_saving_throw
    for kind in missing:
        if kind == "water":
            levels = 2 if weapon_attack.exhaustion(session.character) else 1
            for _ in range(levels):
                fatal = weapon_attack.exhaustion(session.character) == 5
                deaths = []
                weapon_attack.add_exhaustion(session, "dehydration", deaths=deaths)
                if fatal:
                    return {"consumed": consumed, "missing": missing, "condition_death": True,
                            "death_results": deaths}
        else:
            player = session.character
            check = resolve_saving_throw(
                roll_fn=lambda: session.rng.randint(1, 20),
                ability="constitution", dc=10,
                ability_modifier=weapon_attack.saving_bonus(player, "constitution")[0],
                circumstantial_modifier=weapon_attack.saving_bonus(player, "constitution")[1])
            if check["outcome"] != "SUCCESS":
                fatal = weapon_attack.exhaustion(session.character) == 5
                deaths = []
                weapon_attack.add_exhaustion(session, "malnutrition", deaths=deaths)
                if fatal:
                    return {"consumed": consumed, "missing": missing, "condition_death": True,
                            "death_results": deaths}
    if day is not None:
        world["supplies_accounting"] = {"last_day": day, "missing": missing}
    return {"consumed": consumed, "missing": missing}


def process_supply_days(session, before_elapsed):
    time = session.world_state.get("campaign_time")
    if time is None or not session.world_state.get("supplies_policy", {}).get("enabled", False):
        return
    import campaign_time
    before_day = (time["start_second"] + before_elapsed) // campaign_time.DAY
    after_day = (time["start_second"] + time["elapsed_seconds"]) // campaign_time.DAY
    for day in range(before_day + 1, after_day + 1):
        result = consume_daily_supplies(session, day=day)
        if result.get("condition_death"):
            return result
    return {}


def forage(session):
    """Find and transfer existing authored resources; never mint loot."""
    world = session.world_state
    if not world.get("supplies_policy", {}).get("enabled", False):
        return {"success": False, "direct_response": "Erzak takibi kapalı; kaynak üretilmedi."}
    materialize(world)
    ground = world.get("ground_items_by_location", {}).get(world["location"], [])
    candidates = [item for item in ground if supply_kind(item)]
    if not candidates:
        return {"success": False, "direct_response": "Yakında yiyecek ya da su bulabileceğin bir yer göremiyorsun."}
    advancement = session.advance_campaign_time(3600, "foraging")
    if advancement.get("interrupted"):
        return {"success": False, "time_result": advancement, "direct_response": "Erzak araman kesildi."}
    player = session.character
    check = session.perform_skill_check("Survival", 15, player["modifiers"],
                                       player["proficient_skills"], player["proficiency_bonus"])
    if check["resolution"]["outcome"] == "SUCCESS":
        for item in candidates:
            move(world, item, ground, world["inventory"], "ground")
    return {"success": check["resolution"]["outcome"] == "SUCCESS",
            "time_result": advancement, "direct_response": "Erzak arama girişimini tamamladın.", **check}


def npc_at(world, identity):
    found = [n for n in world.get("npcs", []) if n.get("id") == identity]
    if len(found) != 1:
        fail("npc_unknown")
    npc = found[0]
    if npc.get("location") != world["location"] or not npc_can_act(npc):
        fail("npc_unavailable")
    return npc


def npc_can_act(npc):
    """One liveness rule for trades and for scheduled table events."""
    return not (npc.get("alive") is False
                or npc.get("dead") or npc.get("current_hp", 1) <= 0
                or npc.get("state") in {"dead", "unconscious", "removed"}
                or npc.get("combat_status") in {"dead", "unconscious", "defeated"})


def is_armor_or_shield(item):
    """Armor or a shield: its owner is the creation's AC fact, so no item transfer may move it."""
    from api.dnd_2024_rules import ARMOR_NAME_ALIASES
    name = str(label(item) or "").casefold()
    return bool((isinstance(item, dict) and item.get("armor_id"))
                or any(alias.casefold() == name for alias in ARMOR_NAME_ALIASES)
                or any(word in name for word in ("armor", "zırh", "zirh", "shield", "kalkan")))


def _shield_in_hand(world, hands):
    """The player's shield still in use: the off-hand one, else the bag's (a creation shield has no hand entry).
    None once it was put down (`shield_down`) or when the bag holds none."""
    from api.dnd_2024_rules import SHIELD_ITEM_TOKENS
    if "shield_down" in world:
        return None
    bag = [item for item in world.get("inventory", []) if isinstance(item, dict)
           and any(token in label(item).casefold() for token in SHIELD_ITEM_TOKENS)]
    held = [item for item in bag if item["item_id"] == hands.get("off_hand")]
    return (held or bag or [None])[0]


def clear_equipment(world, actor, item):
    if actor == "ground":
        return
    if actor.startswith("corpse:"):
        matches = [n for n in world.get("npcs", []) if n.get("id") == actor[7:]]
        if len(matches) != 1:
            fail("loot_source_unknown")
        owner = matches[0]
    else:
        owner = world if actor == "player" else npc_at(world, actor)
    # Do not silently invalidate creation-owned armor AC/shield benefits.
    if is_armor_or_shield(item):
        fail("armor_owner_required")
    hands = owner.get("equipment")
    if isinstance(hands, dict):
        canonical_hands(world, actor, owner)
        identities = {item["item_id"]}
        for hand, held in hands.items():
            if held is not None and held in identities:
                hands[hand] = None


def canonical_hands(world, actor, owner):
    """Resolve old hand aliases only against unique actual owned instances."""
    hands = owner.get("equipment")
    if hands is None:
        return
    if not isinstance(hands, dict) or set(hands) != {"main_hand", "off_hand"}:
        fail("invalid_equipment")
    items = world["inventory"] if actor == "player" else owner.get("inventory", [])
    resolved = {}
    for hand, held in hands.items():
        if held is None:
            resolved[hand] = None
            continue
        weapon = lookup(held)
        exact = [i for i in items if i["item_id"] == held]
        matches = exact or [i for i in items if i["name"] == held
                            or weapon and i.get("weapon_id") == weapon["weapon_id"]]
        if len(matches) != 1:
            fail("equipment_identity_unresolved")
        resolved[hand] = matches[0]["item_id"]
    occupied = [x for x in resolved.values() if x is not None]
    if len(set(occupied)) != len(occupied):
        fail("duplicate_equipment")
    hands.update(resolved)


def remove_item(world: dict, item_id: str) -> dict:
    """Remove one owned, unequipped instance; failed validation changes nothing."""
    validate_world(world)
    item = next((row for row in world.get("inventory", [])
                 if isinstance(row, dict) and row.get("item_id") == item_id), None)
    if item is None:
        fail("item_not_owned")
    if is_armor_or_shield(item):
        fail("armor_owner_required")
    owner = {"inventory": [row for row in world.get("inventory", []) if isinstance(row, dict)],
             "equipment": copy.deepcopy(world.get("equipment"))}
    canonical_hands(owner, "player", owner)
    if item_id in (owner.get("equipment") or {}).values():
        fail("item_equipped")
    candidate = copy.deepcopy(world)
    removed = next(row for row in candidate["inventory"] if isinstance(row, dict) and row.get("item_id") == item_id)
    candidate["inventory"].remove(removed)
    validate_world(candidate)
    world["inventory"] = candidate["inventory"]
    return removed


def move(world, item, source, destination, source_actor):
    clear_equipment(world, source_actor, item)
    source.remove(item)
    destination.append(item)


def has_consent(npc, item, operation, recipient):
    """The NPC's written consent for exactly this item, operation and recipient; reading it consumes nothing."""
    grants = npc.get("item_consents", {})
    grant = grants.get(item["item_id"]) if isinstance(grants, dict) else None
    return isinstance(grant, dict) and grant == {"operation": operation, "recipient": recipient}


def consent(npc, item, operation, recipient):
    if not has_consent(npc, item, operation, recipient):
        fail("npc_consent_required")
    del npc["item_consents"][item["item_id"]]


def grant_catalog_item(world, identity):
    """Place one existing catalog weapon in the player inventory."""
    weapon = lookup(identity)
    if weapon is None or weapon.get("magic_attack_bonus") or weapon.get("magic_damage_bonus"):
        fail("reward_source_unavailable")
    materialize(world)
    sequence = world.get("item_sequence", 0)
    if type(sequence) is not int or sequence < 0:
        sequence = 0
    reserved = {
        item.get("item_id")
        for _, items in containers(world)
        for item in items
        if isinstance(item, dict)
    }
    while True:
        sequence += 1
        item_id = f"item_{sequence:06d}"
        if item_id not in reserved:
            break
    record = {"item_id": item_id, "name": weapon["name"], "weapon_id": weapon["weapon_id"]}
    world["inventory"].append(record)
    world["item_sequence"] = sequence
    validate_world(world)
    return record


def grant_named_item(world, name):
    """Place one non-magical named item. Catalog weapons keep their identity."""
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        fail("invalid_item_identity")
    weapon = lookup(name)
    if weapon is not None:
        return grant_catalog_item(world, weapon["weapon_id"])
    materialize(world)
    sequence = world.get("item_sequence", 0)
    if type(sequence) is not int or sequence < 0:
        sequence = 0
    reserved = {
        item.get("item_id")
        for _, items in containers(world)
        for item in items
        if isinstance(item, dict)
    }
    while True:
        sequence += 1
        item_id = f"item_{sequence:06d}"
        if item_id not in reserved:
            break
    record = {"item_id": item_id, "name": name.strip()}
    world["inventory"].append(record)
    world["item_sequence"] = sequence
    validate_world(world)
    return record


def pay(world, payer, recipient, amount, *, reward_id=None):
    if type(amount) is not int or amount < 0:
        fail("invalid_price")
    wallets = world.setdefault("currency", {})
    import equipment_native
    if wallets.get(payer, 0) - equipment_native.reserved_funds(world, payer, reward_id) < amount:
        fail("insufficient_funds")
    wallets[payer] = wallets.get(payer, 0) - amount
    wallets[recipient] = wallets.get(recipient, 0) + amount


def shop_at(world, identity):
    shops = [s for s in world.get("shops", []) if s.get("id") == identity]
    if len(shops) != 1 or shops[0].get("location") != world["location"]:
        fail("shop_unavailable")
    shop = shops[0]
    return shop, npc_at(world, shop.get("shopkeeper_id"))


def price(item):
    if (item.get("magical") or item.get("magic_item_id")
            or item.get("magic_attack_bonus") or item.get("magic_damage_bonus")):
        fail("magic_item_out_of_scope")
    weapon = lookup(item.get("weapon_id"))
    if not weapon:
        fail("price_source_unavailable")
    value = Decimal(str(weapon["cost_gp"])) * 100
    if value != value.to_integral_value() or value < 0:
        fail("invalid_catalog_price")
    return int(value)


def _apply(world, operation, args):
    materialize(world)
    inventory = world["inventory"]
    import equipment_native as native
    if operation == "market" and not args:
        shop = native.market(world)
        return f'İşlem noktası: {shop["id"]}; NPC: {shop["shopkeeper_id"]}. /item list'
    if operation == "request" and len(args) == 2:
        npc = npc_at(world, args[1])
        item = native.authorize_request(world, npc, args[0])
        consent(npc, item, "receive", "player")
        move(world, item, npc["inventory"], inventory, npc["id"])
        return f'{item["name"]} [{item["item_id"]}] açık rızayla devredildi.'
    if operation == "work" and len(args) == 1:
        npc = npc_at(world, args[0])
        identity = native.offer_work(world, npc, f"/item work {args[0]}")
        return f'İş kaydı: {identity}. NPC ile konuş; tamamlandıktan sonra /item reward {identity}. Ayrılmış ödül: 100 CP.'
    if operation == "talk" and len(args) >= 2:
        return native.talk(world, npc_at(world, args[0]), " ".join(args[1:]))
    if operation == "loot" and len(args) == 2:
        source, actor = native.loot_source(world, args[0])
        item = one(source, args[1])
        move(world, item, source, inventory, actor)
        return f'{item["name"]} [{item["item_id"]}] mevcut kaynaktan alındı.'
    if operation == "list" and not args:
        lines = [f'{i["name"]} [{i["item_id"]}]' for i in inventory]
        wallet = world.get("currency", {}).get("player")
        lines.append(f"Bakiye: {wallet} CP değer birimi." if wallet is not None
                     else "Kesende sayabileceğin bir para yok.")
        ground = world.get("ground_items_by_location", {}).get(world["location"], [])
        lines.extend(f'Yerde: {i["name"]} [{i["item_id"]}] — /item take {i["item_id"]}'
                     for i in ground)
        for feature_id, shelf in (world.get("surface_items") or {}).items():
            try:
                surface = _surface_feature(world, feature_id)
            except EquipmentError:
                continue
            lines.extend(f'{surface["name"]}: {i["name"]} [{i["item_id"]}] — /item take {i["item_id"]}'
                         for i in shelf if isinstance(i, dict))
        for shop in world.get("shops", []):
            if shop.get("location") != world["location"]:
                continue
            try:
                npc = npc_at(world, shop.get("shopkeeper_id"))
            except EquipmentError:
                continue
            offers = shop.get("item_offers_cp", {})
            for item in npc.get("inventory", []):
                if isinstance(offers, dict) and item["item_id"] in offers:
                    cost = price(item)
                    if offers[item["item_id"]] == cost:
                        lines.append(f'{item["name"]}: {cost} CP — /item buy {item["item_id"]} {shop["id"]}')
        for npc in world.get("npcs", []):
            if npc.get("location") != world["location"]:
                continue
            grants = npc.get("item_consents", {})
            for item in npc.get("inventory", []):
                policy = npc.get("item_release_policy", {}).get(item["item_id"])
                if policy == {"operation": "receive", "recipient": "player"}:
                    lines.append(f'{npc["name"]}: {item["name"]} [{item["item_id"]}] — /item request {item["item_id"]} {npc["id"]}')
                if isinstance(grants, dict) and grants.get(item["item_id"]) == {
                    "operation": "receive", "recipient": "player",
                }:
                    lines.append(f'{npc["name"]}: {item["name"]} — /item receive {item["item_id"]} {npc["id"]}')
        for owner in [*world.get("npcs", []), *world.get("containers", [])]:
            try:
                items, _ = native.loot_source(world, owner.get("id"))
            except EquipmentError:
                continue
            lines.extend(f'Loot: {i["name"]} [{i["item_id"]}] — /item loot {owner["id"]} {i["item_id"]}'
                         for i in items)
        for shop in world.get("shops", []):
            if shop.get("economy_origin") == native.ORIGIN and shop.get("location") == world["location"]:
                lines.append(f'İş: /item work {shop["shopkeeper_id"]}; konuşma: /item talk {shop["shopkeeper_id"]} Merhaba')
        for identity, reward in world.get("item_rewards", {}).items():
            if identity not in world.get("claimed_item_rewards", []):
                lines.append(f'Ödül kaydı: /item reward {identity} ({reward.get("currency_cp", 0)} CP; tamamlanma gerekli)')
        return "\n".join(lines)
    if operation == "place" and len(args) == 2:
        item = one(inventory, args[0])
        feature = _surface_feature(world, args[1])
        shelf = world.setdefault("surface_items", {}).setdefault(feature["id"], [])
        if len(shelf) >= SURFACE_ITEM_LIMIT:
            fail("surface_full")
        move(world, item, inventory, shelf, "player")
        return f'{item["name"]} [{item["item_id"]}] şuraya bırakıldı: {feature["name"]}.'
    if operation == "mark" and len(args) >= 2:
        feature = _surface_feature(world, args[0])
        text = " ".join(args[1:]).strip()
        if not _valid_mark_text(text):
            fail("invalid_mark_text")
        entries = world.setdefault("feature_marks", {}).setdefault(feature["id"], [])
        if len(entries) >= SURFACE_MARK_LIMIT:
            fail("mark_limit_reached")
        used = {m["mark_id"] for ms in world["feature_marks"].values() for m in ms}
        # Monotonic: a removed mark's id is never handed to a newer mark.
        number = world.get("feature_mark_sequence", 0) + 1
        while f"mark_{number:03d}" in used:
            number += 1
        world["feature_mark_sequence"] = number
        entries.append({"mark_id": f"mark_{number:03d}", "text": text,
                        "turn": world.get("flags", {}).get("turn_index", 0)})
        return f'İz kaydedildi: {feature["name"]}.'
    if operation in {"drop", "take"} and len(args) == 1:
        ground = world.setdefault("ground_items_by_location", {}).setdefault(world["location"], [])
        source, destination = (inventory, ground) if operation == "drop" else (ground, inventory)
        if operation == "take" and not any(
                isinstance(i, dict) and i.get("item_id") == args[0] for i in ground):
            holder = _surface_holding(world, args[0])
            if holder is not None:
                source = world["surface_items"][holder]
        item = one(source, args[0])
        move(world, item, source, destination, "player" if operation == "drop" else "ground")
        _prune_surfaces(world)
    elif operation == "equip" and len(args) == 2:
        item, hand = one(inventory, args[0]), args[1]
        weapon = lookup(item.get("weapon_id"))
        if hand not in {"main_hand", "off_hand"} or weapon is None:
            fail("unsupported_equipment")
        two_handed = "two_handed" in weapon.get("properties", []) or "two-handed" in weapon.get("properties", [])
        if two_handed and hand != "main_hand":
            fail("two_handed_owner_required")
        hands = world.setdefault("equipment", {"main_hand": None, "off_hand": None})
        canonical_hands(world, "player", world)
        if two_handed:
            # The shield goes away with the off hand; it stays in the bag. Its Armor Class share is settled against
            # the character by `gear.settle_shield` (Dilim 3, Task 16).
            shield = _shield_in_hand(world, hands)
            if shield is not None:
                world["shield_down"] = {"item_id": shield["item_id"], "ac_bonus": None}
            hands["off_hand"] = None  # a two-handed weapon is held in both hands (Dilim 2, Task 14)
        if hands[hand] is not None or item["item_id"] in hands.values():
            fail("hand_occupied")
        hands[hand] = item["item_id"]
    elif operation == "unequip" and len(args) == 1:
        hands = world.get("equipment")
        if not isinstance(hands, dict) or args[0] not in {"main_hand", "off_hand"}:
            fail("equipment_unknown")
        held = hands.get(args[0])
        if held is not None and any(word in str(held).casefold() for word in ("shield", "kalkan")):
            fail("armor_owner_required")
        canonical_hands(world, "player", world)
        hands[args[0]] = None
    elif operation == "give" and len(args) == 2:
        import economic_actions
        import item_transfers
        npc = npc_at(world, args[1])
        item = one(inventory, args[0])
        if is_armor_or_shield(item):
            fail("armor_owner_required")
        if item_transfers.is_coin_label(item):
            fail("coin_is_money")  # written coin is money: it goes with a coin card, never as an item
        if not has_consent(npc, item, "give", npc["id"]):
            fail("npc_consent_required")  # read here, consumed only by the transfer itself
        if item_transfers.item_needs_card(world, item):
            return ItemCardRequest(proposal=economic_actions.EconomicProposal(
                purpose="item_gift", recipient_id=npc["id"], source_id="player", item_id=item["item_id"], count=1,
                amount_cp=None, tip_cp=0, tender_cp=None, dependency="base_required", source_action_id="",
                text_span=None))
        consent(npc, item, "give", npc["id"])
        moved = item_transfers.transfer_existing_item(
            economic_actions.EconomicState(world=world, character=None), item_id=item["item_id"], source_id="player",
            recipient_id=npc["id"], count=1, operation_id=economic_actions.operation_id_for(world, "item_transfer"))
        if moved.status != "applied":
            fail(moved.reason_code or "item_transfer_refused")
    elif operation == "receive" and len(args) == 2:
        npc = npc_at(world, args[1])
        npc_items = npc.setdefault("inventory", [])
        source, destination = (inventory, npc_items) if operation == "give" else (npc_items, inventory)
        item = one(source, args[0])
        consent(npc, item, operation, npc["id"] if operation == "give" else "player")
        move(world, item, source, destination, "player" if operation == "give" else npc["id"])
    elif operation in {"buy", "sell"} and len(args) == 2:
        shop, npc = shop_at(world, args[1])
        npc_items = npc.setdefault("inventory", [])
        source, destination = (npc_items, inventory) if operation == "buy" else (inventory, npc_items)
        item = one(source, args[0])
        cost = price(item)
        if operation == "buy":
            offers = shop.get("item_offers_cp", {})
            if not isinstance(offers, dict) or offers.get(item["item_id"]) != cost:
                fail("stock_or_price_unavailable")
            pay(world, "player", npc["id"], cost)
            del offers[item["item_id"]]
        else:
            if shop.get("buys_equipment") is not True:
                fail("merchant_acceptance_required")
            # PHB half cost. Odd copper prices need a fractional-value owner.
            if cost % 2:
                fail("fractional_price_unsupported")
            pay(world, npc["id"], "player", cost // 2)
        move(world, item, source, destination, npc["id"] if operation == "buy" else "player")
    elif operation == "shop_buy":
        import shop_trade
        return shop_trade.commit_typed(world, args)
    elif operation == "reward" and len(args) == 1:
        identity = args[0]
        quests = world.get("quests", [])
        completed = any(q.get("quest_id", q.get("id")) == identity and q.get("status") == "completed"
                        for q in quests)
        completed = completed or any(t["thread_id"] == identity and t["status"] == "succeeded"
                                    for t in world.get("interaction_adventure_v1", {}).get("threads", []))
        if not completed:
            fail("quest_not_completed")
        claimed = world.setdefault("claimed_item_rewards", [])
        if identity in claimed:
            fail("reward_already_claimed")
        reward = world.get("item_rewards", {}).get(identity)
        if not isinstance(reward, dict):
            fail("reward_source_unavailable")
        npc = npc_at(world, reward.get("source_npc_id"))
        ids = reward.get("item_ids", [])
        if not isinstance(ids, list) or len(set(ids)) != len(ids):
            fail("invalid_reward")
        source = npc.get("inventory", [])
        items = [one(source, i) for i in ids]
        amount = reward.get("currency_cp", 0)
        pay(world, npc["id"], "player", amount, reward_id=identity)
        for item in items:
            move(world, item, source, inventory, npc["id"])
        claimed.append(identity)
    else:
        fail("invalid_item_command")
    return "Eşya işlemi Python tarafından atomik olarak tamamlandı."


def _natural_inventory_query(text):
    """Recognize only first-person inventory inspection; never expose another actor's inventory."""
    if not isinstance(text, str):
        return False
    import living_world
    lowered = living_world.normalize_text(text)  # the owner types without the dots
    if re.search(r"\b(?:cantam|ustum|uzerim|yanim|cebim|kesem|kese)(?:da|de)\b.{0,12}\bne(?:ler)?\s+var\b", lowered):
        return True  # "çantamda ne var", "üstümde ne var bakayım", "kesede ne var"
    if re.search(r"\b(?:cantam|kesem|cebim|heybem)(?:a|i|e)?\s+(?:bak|kontrol)\w*", lowered):
        return True  # "çantama bakıyorum", "keseme bakıyorum"
    if not re.search(r"\benvanter(?:im|imde|imi|ime|imin)\b", lowered):
        return False
    return bool(re.search(
        r"\b(?:ne|neler|var|gozden\s+gecir\w*|bak\w*|goster\w*|listele\w*|kontrol\s+et\w*)\b",
        lowered,
    ))


def execute(session, text, *, advance_turn=True):
    """Return None for unrelated input; model output never enters this owner."""
    natural_list = _natural_inventory_query(text)
    if not natural_list and not text.strip().startswith("/item"):
        return None
    before = copy.deepcopy(session.world_state)
    success, reason, fresh_offer, offered = False, None, None, False
    try:
        tokens = ["/item", "list"] if natural_list else shlex.split(text)
        if len(tokens) < 2 or tokens[0] != "/item":
            fail("invalid_item_command")
        world = session.world_state
        if (world.get("combat", {}).get("active") or session.character.get("current_hp", 0) <= 0
                or world.get("death_state", {}).get("terminal")
                or world.get("death_state", {}).get("dead")
                or world.get("combat", {}).get("pending_reaction")):
            fail("existing_action_owner_required")
        # Resolve a candidate copy so even nested caller-held containers do not
        # observe transient debits or consumed consent on a rejected transaction.
        candidate = copy.deepcopy(world)
        narration = _apply(candidate, tokens[1], tokens[2:])
        card_request = narration if isinstance(narration, ItemCardRequest) else None
        validate_world(candidate)
        if natural_list:
            item_names = labels(candidate["inventory"])
            narration = (
                f"Envanterinde: {', '.join(item_names)}."
                if item_names else "Envanterin boş."
            )
            wallet = candidate.get("currency", {}).get("player")
            if wallet:
                narration += f" Kesende {wallet // 100} altın {wallet % 100} bakır var."
        if tokens[1] == "list":
            import item_use
            note = item_use.ammo_note(candidate)
            if note:
                narration += " " + note
        original = dict(world)  # the untouched saved values: _apply only ever wrote to the candidate copy
        world.clear()
        world.update(candidate)
        import gear
        gear.settle_shield(world, session.character)  # a two-handed weapon taken in hand put the shield down
        if card_request is not None:
            # The valued or held item stays put: the card is prepared on the live world, and only a prepared card
            # counts as this turn. A refusal or a question leaves the turn where it was.
            import economic_actions
            prepared = economic_actions.prepare_from_turn(session, card_request.proposal)
            narration = prepared.public_message
            if prepared.status != "prepared":
                reason = prepared.reason_code
                # Nothing of the refused card may stay: no materialized stack, no spent item sequence.
                world.clear()
                world.update(original)
                raise _CardNotPrepared(reason)
            offered = True
        if advance_turn and tokens[1] != "list":
            world["flags"]["turn_index"] = world["flags"].get("turn_index", 0) + 1
        success = True
    except _CardNotPrepared:
        success = False
    except (EquipmentError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc) if isinstance(exc, EquipmentError) else "invalid_economic_state"
        fresh_offer = getattr(exc, "quote", None)  # a refused counter trade shows the offer as it stands now
        narration = ("Kavganın ortasında çantanı karıştıracak vaktin yok." if natural_list
                     else f"{_COUNTER_REFUSALS[reason]} Dünya durumu değişmedi." if reason in _COUNTER_REFUSALS
                     else f"Eşya işlemi reddedildi: {reason}. Dünya durumu değişmedi.")
    return {
        "messages": session.messages, "narration": narration, "model_calls": 0,
        "action_result": {
            "action": (
                "inventory" if success and natural_list
                else "dialogue" if success and tokens[1] == "talk"
                else "equipment_transaction"
            ),
            "npc_id": (
                tokens[3] if success and tokens[1] in {"request", "receive", "give"}
                else tokens[2] if success and tokens[1] == "talk"
                else tokens[2] if success and tokens[1] == "work"
                else None
            ),
            "status": "offered" if offered else "resolved" if success else "rejected",
            "success": success, "reason": reason,
            "state_changes": ["player.inventory", "equipment", "economy"] if success and before != session.world_state else [],
            **({"item_transfers": item_transfers(before, session.world_state)}
               if success else {}),
            **({"offer": fresh_offer} if isinstance(fresh_offer, dict) else {}),
        },
    }


def grant_plain(world, name):
    """A thing with a name and no worth, for a player who picked it up where the screen showed it.

    A name the catalog knows is gear, which only Python hands out: it stays out and the caller says False.
    """
    if any(lookup(word) for word in (name, *name.split())):
        return False
    materialize(world)
    world["inventory"].append(name)
    materialize(world)
    validate_world(world)
    return True


def public_inventory(world):
    """Preserve the API string-list contract; labels expose IDs and hand state."""
    hands = world.get("equipment", {})
    hands = hands if isinstance(hands, dict) else {}
    return [
        f'{i.get("name") or i.get("weapon_id", "Eşya")} [{i.get("item_id", "kimlik doğrulanmamış")}]'
        + (" (kuşanılmış)" if i.get("item_id") and i["item_id"] in hands.values() else "")
        if isinstance(i, dict) else i
        for i in world.get("inventory", [])
    ]


def legacy_sword_move(session, dropping):
    """Keep legacy phrasing functional after identity migration, using the same mover."""
    world = session.world_state
    before = copy.deepcopy(world)
    try:
        materialize(world)
        ground = world.setdefault("ground_items_by_location", {}).setdefault(world["location"], [])
        source, destination = (world["inventory"], ground) if dropping else (ground, world["inventory"])
        matches = [i for i in source if i["name"] == "Kılıç"]
        if len(matches) != 1:
            fail("item_ambiguous_or_missing")
        move(world, matches[0], source, destination, "player" if dropping else "ground")
        validate_world(world)
        return ("Python durumu: Kılıç envanterden yere taşındı." if dropping
                else "Python durumu: Yerdeki Kılıç envantere alındı.")
    except EquipmentError:
        world.clear()
        world.update(before)
        return "Python durumu: Eşya kimliğini belirtmelisin; envanter değişmedi."


def validate_worn_armor(world, character, engine_format):
    """Selected new-creation known-unarmored fact, not a general armor owner."""
    if 'worn_armor_v1' not in world:
        return
    proof = world['worn_armor_v1']
    if (type(engine_format) is not int or engine_format not in (4, 5, 6)
            or character.get('class') not in ('Barbarian', 'Monk')
            or type(proof) is not dict or set(proof) != {'version', 'armor_id'}
            or type(proof['version']) is not int or proof['version'] != 1
            or proof['armor_id'] is not None):
        fail('invalid_worn_armor_provenance')


def initialize_unarmored_proof(session):
    """Called only by verified new-character equipment selection, never load."""
    session.world_state['worn_armor_v1'] = {'version': 1, 'armor_id': None}
