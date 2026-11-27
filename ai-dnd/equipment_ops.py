"""The typed `/item` operations (D-501): one function per operation, found by `apply` from the operation's name.

`equipment_economy._apply` is the one door. Every name below is read from `equipment_economy` at call time, as the
long function did before it was split, so a patched `pay`, `move` or `lookup` still reaches every operation."""
import equipment_economy as economy

DONE = "Eşya işlemi Python tarafından atomik olarak tamamlandı."


def _market(world, _inventory, _args):
    import equipment_native as native
    shop = native.market(world)
    return f'İşlem noktası: {shop["id"]}; NPC: {shop["shopkeeper_id"]}. /item list'


def _request(world, inventory, args):
    import equipment_native as native
    npc = economy.npc_at(world, args[1])
    item = native.authorize_request(world, npc, args[0])
    economy.consent(npc, item, "receive", "player")
    economy.move(world, item, npc["inventory"], inventory, npc["id"])
    return f'{item["name"]} [{item["item_id"]}] açık rızayla devredildi.'


def _work(world, _inventory, args):
    import equipment_native as native
    npc = economy.npc_at(world, args[0])
    identity = native.offer_work(world, npc, f"/item work {args[0]}")
    return f'İş kaydı: {identity}. NPC ile konuş; tamamlandıktan sonra /item reward {identity}. Ayrılmış ödül: 100 CP.'


def _talk(world, _inventory, args):
    import equipment_native as native
    return native.talk(world, economy.npc_at(world, args[0]), " ".join(args[1:]))


def _loot(world, inventory, args):
    import equipment_native as native
    source, actor = native.loot_source(world, args[0])
    item = economy.one(source, args[1])
    economy.move(world, item, source, inventory, actor)
    return f'{item["name"]} [{item["item_id"]}] mevcut kaynaktan alındı.'


def _list(world, inventory, _args):
    import equipment_native as native
    lines = [f'{i["name"]} [{i["item_id"]}]' for i in inventory]
    wallet = world.get("currency", {}).get("player")
    lines.append(f"Bakiye: {wallet} CP değer birimi." if wallet is not None
                 else "Kesende sayabileceğin bir para yok.")
    ground = world.get("ground_items_by_location", {}).get(world["location"], [])
    lines.extend(f'Yerde: {i["name"]} [{i["item_id"]}] — /item take {i["item_id"]}'
                 for i in ground)
    for feature_id, shelf in (world.get("surface_items") or {}).items():
        try:
            surface = economy._surface_feature(world, feature_id)
        except economy.EquipmentError:
            continue
        lines.extend(f'{surface["name"]}: {i["name"]} [{i["item_id"]}] — /item take {i["item_id"]}'
                     for i in shelf if isinstance(i, dict))
    for shop in world.get("shops", []):
        if shop.get("location") != world["location"]:
            continue
        try:
            npc = economy.npc_at(world, shop.get("shopkeeper_id"))
        except economy.EquipmentError:
            continue
        offers = shop.get("item_offers_cp", {})
        for item in npc.get("inventory", []):
            if isinstance(offers, dict) and item["item_id"] in offers:
                cost = economy.price(item)
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
        except economy.EquipmentError:
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


def _place(world, inventory, args):
    item = economy.one(inventory, args[0])
    feature = economy._surface_feature(world, args[1])
    shelf = world.setdefault("surface_items", {}).setdefault(feature["id"], [])
    if len(shelf) >= economy.SURFACE_ITEM_LIMIT:
        economy.fail("surface_full")
    economy.move(world, item, inventory, shelf, "player")
    return f'{item["name"]} [{item["item_id"]}] şuraya bırakıldı: {feature["name"]}.'


def _mark(world, _inventory, args):
    feature = economy._surface_feature(world, args[0])
    text = " ".join(args[1:]).strip()
    if not economy._valid_mark_text(text):
        economy.fail("invalid_mark_text")
    entries = world.setdefault("feature_marks", {}).setdefault(feature["id"], [])
    if len(entries) >= economy.SURFACE_MARK_LIMIT:
        economy.fail("mark_limit_reached")
    used = {m["mark_id"] for ms in world["feature_marks"].values() for m in ms}
    # Monotonic: a removed mark's id is never handed to a newer mark.
    number = world.get("feature_mark_sequence", 0) + 1
    while f"mark_{number:03d}" in used:
        number += 1
    world["feature_mark_sequence"] = number
    entries.append({"mark_id": f"mark_{number:03d}", "text": text,
                    "turn": world.get("flags", {}).get("turn_index", 0)})
    return f'İz kaydedildi: {feature["name"]}.'


def _drop(world, inventory, args):
    ground = world.setdefault("ground_items_by_location", {}).setdefault(world["location"], [])
    item = economy.one(inventory, args[0])
    economy.move(world, item, inventory, ground, "player")
    economy._prune_surfaces(world)
    return DONE


def _take(world, inventory, args):
    ground = world.setdefault("ground_items_by_location", {}).setdefault(world["location"], [])
    source = ground
    if not any(isinstance(i, dict) and i.get("item_id") == args[0] for i in ground):
        holder = economy._surface_holding(world, args[0])
        if holder is not None:
            source = world["surface_items"][holder]
    item = economy.one(source, args[0])
    economy.move(world, item, source, inventory, "ground")
    economy._prune_surfaces(world)
    return DONE


def _equip(world, inventory, args):
    item, hand = economy.one(inventory, args[0]), args[1]
    weapon = economy.lookup(item.get("weapon_id"))
    if hand not in {"main_hand", "off_hand"} or weapon is None:
        economy.fail("unsupported_equipment")
    two_handed = "two_handed" in weapon.get("properties", []) or "two-handed" in weapon.get("properties", [])
    if two_handed and hand != "main_hand":
        economy.fail("two_handed_owner_required")
    hands = world.setdefault("equipment", {"main_hand": None, "off_hand": None})
    economy.canonical_hands(world, "player", world)
    if two_handed:
        # The shield goes away with the off hand; it stays in the bag. Its Armor Class share is settled against
        # the character by `gear.settle_shield` (Dilim 3, Task 16).
        shield = economy._shield_in_hand(world, hands)
        if shield is not None:
            world["shield_down"] = {"item_id": shield["item_id"], "ac_bonus": None}
        hands["off_hand"] = None  # a two-handed weapon is held in both hands (Dilim 2, Task 14)
    if hands[hand] is not None or item["item_id"] in hands.values():
        economy.fail("hand_occupied")
    hands[hand] = item["item_id"]
    if None not in hands.values():
        # D-116/D-184: a creation shield has no hand entry but holds one; a weapon in each hand puts it down,
        # as a two-handed weapon does, and `gear.settle_shield` takes its Armor Class share off.
        shield = economy._shield_in_hand(world, hands)
        if shield is not None and shield["item_id"] not in hands.values():
            world["shield_down"] = {"item_id": shield["item_id"], "ac_bonus": None}
    return DONE


def _unequip(world, _inventory, args):
    hands = world.get("equipment")
    if not isinstance(hands, dict) or args[0] not in {"main_hand", "off_hand"}:
        economy.fail("equipment_unknown")
    held = hands.get(args[0])
    if held is not None and any(word in str(held).casefold() for word in ("shield", "kalkan")):
        economy.fail("armor_owner_required")
    economy.canonical_hands(world, "player", world)
    hands[args[0]] = None
    return DONE


def _give(world, inventory, args):
    import economic_actions
    import item_transfers
    npc = economy.npc_at(world, args[1])
    item = economy.one(inventory, args[0])
    if economy.is_armor_or_shield(item):
        economy.fail("armor_owner_required")
    if item_transfers.is_coin_label(item):
        economy.fail("coin_is_money")  # written coin is money: it goes with a coin card, never as an item
    if not economy.has_consent(npc, item, "give", npc["id"]):
        economy.fail("npc_consent_required")  # read here, consumed only by the transfer itself
    if item_transfers.item_needs_card(world, item):
        return economy.ItemCardRequest(proposal=economic_actions.EconomicProposal(
            purpose="item_gift", recipient_id=npc["id"], source_id="player", item_id=item["item_id"], count=1,
            amount_cp=None, tip_cp=0, tender_cp=None, dependency="base_required", source_action_id="",
            text_span=None))
    economy.consent(npc, item, "give", npc["id"])
    moved = item_transfers.transfer_existing_item(
        economic_actions.EconomicState(world=world, character=None), item_id=item["item_id"], source_id="player",
        recipient_id=npc["id"], count=1, operation_id=economic_actions.operation_id_for(world, "item_transfer"))
    if moved.status != "applied":
        economy.fail(moved.reason_code or "item_transfer_refused")
    return DONE


def _receive(world, inventory, args):
    npc = economy.npc_at(world, args[1])
    npc_items = npc.setdefault("inventory", [])
    item = economy.one(npc_items, args[0])
    economy.consent(npc, item, "receive", "player")
    economy.move(world, item, npc_items, inventory, npc["id"])
    return DONE


def _buy(world, inventory, args):
    shop, npc = economy.shop_at(world, args[1])
    npc_items = npc.setdefault("inventory", [])
    item = economy.one(npc_items, args[0])
    cost = economy.price(item)
    offers = shop.get("item_offers_cp", {})
    if not isinstance(offers, dict) or offers.get(item["item_id"]) != cost:
        economy.fail("stock_or_price_unavailable")
    economy.pay(world, "player", npc["id"], cost)
    del offers[item["item_id"]]
    economy.move(world, item, npc_items, inventory, npc["id"])
    return DONE


def _sell(world, inventory, args):
    shop, npc = economy.shop_at(world, args[1])
    npc_items = npc.setdefault("inventory", [])
    item = economy.one(inventory, args[0])
    cost = economy.price(item)
    if shop.get("buys_equipment") is not True:
        economy.fail("merchant_acceptance_required")
    # PHB half cost. Odd copper prices need a fractional-value owner.
    if cost % 2:
        economy.fail("fractional_price_unsupported")
    economy.pay(world, npc["id"], "player", cost // 2)
    economy.move(world, item, inventory, npc_items, "player")
    return DONE


def _shop_buy(world, _inventory, args):
    import shop_trade
    return shop_trade.commit_typed(world, args)


def _reward(world, inventory, args):
    identity = args[0]
    quests = world.get("quests", [])
    completed = any(q.get("quest_id", q.get("id")) == identity and q.get("status") == "completed"
                    for q in quests)
    completed = completed or any(t["thread_id"] == identity and t["status"] == "succeeded"
                                for t in world.get("interaction_adventure_v1", {}).get("threads", []))
    if not completed:
        economy.fail("quest_not_completed")
    claimed = world.setdefault("claimed_item_rewards", [])
    if identity in claimed:
        economy.fail("reward_already_claimed")
    reward = world.get("item_rewards", {}).get(identity)
    if not isinstance(reward, dict):
        economy.fail("reward_source_unavailable")
    npc = economy.npc_at(world, reward.get("source_npc_id"))
    ids = reward.get("item_ids", [])
    if not isinstance(ids, list) or len(set(ids)) != len(ids):
        economy.fail("invalid_reward")
    source = npc.get("inventory", [])
    items = [economy.one(source, i) for i in ids]
    amount = reward.get("currency_cp", 0)
    economy.pay(world, npc["id"], "player", amount, reward_id=identity)
    for item in items:
        economy.move(world, item, source, inventory, npc["id"])
    claimed.append(identity)
    return DONE


# operation -> (how many arguments, whether exactly that many or at least that many, function)
OPERATIONS = {
    "market": (0, True, _market), "request": (2, True, _request), "work": (1, True, _work),
    "talk": (2, False, _talk), "loot": (2, True, _loot), "list": (0, True, _list), "place": (2, True, _place),
    "mark": (2, False, _mark), "drop": (1, True, _drop), "take": (1, True, _take), "equip": (2, True, _equip),
    "unequip": (1, True, _unequip), "give": (2, True, _give), "receive": (2, True, _receive),
    "buy": (2, True, _buy), "sell": (2, True, _sell), "shop_buy": (0, False, _shop_buy),
    "reward": (1, True, _reward),
}


def apply(world, operation, args):
    economy.materialize(world)
    count, exact, operate = OPERATIONS.get(operation, (0, True, None))
    if operate is None or not (len(args) == count if exact else len(args) >= count):
        economy.fail("invalid_item_command")
    return operate(world, world["inventory"], args)
