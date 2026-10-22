"""Transactions over the existing Python possession containers, not a second inventory."""
from __future__ import annotations

import copy
import re
import shlex
from decimal import Decimal

from weapon_catalog import lookup

COIN_VALUES = {"cp": 1, "sp": 10, "ep": 50, "gp": 100, "pp": 1000}


class EquipmentError(ValueError):
    pass


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
    if world.get("ground_items"):
        yield "legacy_ground", world["ground_items"]


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
    if (npc.get("location") != world["location"] or npc.get("alive") is False
            or npc.get("dead") or npc.get("current_hp", 1) <= 0
            or npc.get("state") in {"dead", "unconscious", "removed"}
            or npc.get("combat_status") in {"dead", "unconscious", "defeated"}):
        fail("npc_unavailable")
    return npc


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
    from api.dnd_2024_rules import ARMOR_NAME_ALIASES
    name = item["name"].casefold()
    if (item.get("armor_id") or any(alias.casefold() == name for alias in ARMOR_NAME_ALIASES)
            or any(word in name for word in ("armor", "zırh", "zirh", "shield", "kalkan"))):
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


def move(world, item, source, destination, source_actor):
    clear_equipment(world, source_actor, item)
    source.remove(item)
    destination.append(item)


def consent(npc, item, operation, recipient):
    grants = npc.get("item_consents", {})
    grant = grants.get(item["item_id"]) if isinstance(grants, dict) else None
    if not isinstance(grant, dict) or grant != {
        "operation": operation, "recipient": recipient,
    }:
        fail("npc_consent_required")
    del grants[item["item_id"]]


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
    if operation in {"drop", "take"} and len(args) == 1:
        ground = world.setdefault("ground_items_by_location", {}).setdefault(world["location"], [])
        source, destination = (inventory, ground) if operation == "drop" else (ground, inventory)
        item = one(source, args[0])
        move(world, item, source, destination, "player" if operation == "drop" else "ground")
    elif operation == "equip" and len(args) == 2:
        item, hand = one(inventory, args[0]), args[1]
        weapon = lookup(item.get("weapon_id"))
        if hand not in {"main_hand", "off_hand"} or weapon is None:
            fail("unsupported_equipment")
        if "two_handed" in weapon.get("properties", []) or "two-handed" in weapon.get("properties", []):
            fail("two_handed_owner_required")
        hands = world.setdefault("equipment", {"main_hand": None, "off_hand": None})
        canonical_hands(world, "player", world)
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
    elif operation in {"give", "receive"} and len(args) == 2:
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
    lowered = text.casefold().strip()
    if not re.search(r"\benvanter(?:im|imde|imi|ime|imin)\b", lowered):
        return False
    return bool(re.search(
        r"\b(?:ne|neler|var|gözden\s+geçir\w*|gozden\s+gecir\w*|"
        r"bak\w*|göster\w*|goster\w*|listele\w*|kontrol\s+et\w*)\b",
        lowered,
    ))


def execute(session, text, *, advance_turn=True):
    """Return None for unrelated input; model output never enters this owner."""
    natural_list = _natural_inventory_query(text)
    if not natural_list and not text.strip().startswith("/item"):
        return None
    before = copy.deepcopy(session.world_state)
    success, reason = False, None
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
        validate_world(candidate)
        if natural_list:
            item_names = labels(candidate["inventory"])
            narration = (
                f"Envanterinde: {', '.join(item_names)}."
                if item_names else "Envanterin boş."
            )
        world.clear()
        world.update(candidate)
        if advance_turn and tokens[1] != "list":
            world["flags"]["turn_index"] = world["flags"].get("turn_index", 0) + 1
        success = True
    except (EquipmentError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc) if isinstance(exc, EquipmentError) else "invalid_economic_state"
        narration = f"Eşya işlemi reddedildi: {reason}. Dünya durumu değişmedi."
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
            "status": "resolved" if success else "rejected",
            "success": success, "reason": reason,
            "state_changes": ["player.inventory", "equipment", "economy"] if success and before != session.world_state else [],
            **({"item_transfers": item_transfers(before, session.world_state)}
               if success else {}),
        },
    }


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
