"""Bounded native producers for the existing equipment and interaction owners.

Campaign policy (not PHB lore): one local equipment counter per location,
10 GP working capital, catalog Dagger stock, one explicitly releasable Club,
and one funded 1 GP cooperation reward per counter. No resume-time seeding.
"""
from __future__ import annotations

import equipment_economy as economy
import interaction_adventure as interaction
from weapon_catalog import lookup

ORIGIN = "native_equipment_counter_v1"


def market(world):
    """Called by explicit player command, never by generated shop prose."""
    if world.get("location") not in world.get("locations", {}):
        economy.fail("location_unknown")
    existing = next((s for s in world.get("shops", [])
                     if s.get("location") == world["location"]
                     and s.get("economy_origin") == ORIGIN), None)
    if existing:
        return existing
    import game
    # Prefer an existing shopkeeper's actual possessions. Explicit existing
    # economics are authoritative; never overwrite their stock or cash.
    shop = next((s for s in world.get("shops", [])
                 if s.get("location") == world["location"]
                 and s.get("item_offers_cp") is None
                 and s.get("shopkeeper_id")
                 and any(n.get("id") == s["shopkeeper_id"] and n.get("role") == "Shopkeeper"
                         for n in world.get("npcs", []))), None)
    if shop is not None:
        npc = economy.npc_at(world, shop["shopkeeper_id"])
    else:
        # Reuse the validated Python shop/NPC owner on a candidate-bound session.
        session = game._session()
        old_world = session.world_state
        try:
            session.world_state = world
            created = session.create_shop_from_proposal({
                "name": "Equipment Counter", "description": "",
                "location": world["location"],
                "shopkeeper": {"name": "Equipment Merchant", "description": ""},
            })
        finally:
            session.world_state = old_world
        if not created:
            economy.fail("shop_owner_rejected")
        shop, npc = created["shop"], created["shopkeeper"]
    # No input from proposal prose is used for economics.
    npc.setdefault("inventory", []).extend([lookup("dagger")["name"], lookup("club")["name"]])
    economy.materialize(world)
    dagger, club = npc["inventory"][-2:]
    if "equipment" not in npc:
        npc["equipment"] = {"main_hand": club["item_id"], "off_hand": None}
    npc["item_release_policy"] = {
        club["item_id"]: {"operation": "receive", "recipient": "player"},
    }
    shop.update(economy_origin=ORIGIN,
                item_offers_cp={dagger["item_id"]: economy.price(dagger)},
                buys_equipment=True)
    world.setdefault("currency", {}).setdefault(npc["id"], 1000)
    return shop


def authorize_request(world, npc, reference):
    """Interaction-owned explicit decision; persuasion is deliberately absent."""
    items = npc.get("inventory", [])
    matches = [i for i in items if reference in {i["item_id"], i["name"]}
               or interaction.normalize(reference) == interaction.normalize(i["name"])]
    if len(matches) != 1:
        economy.fail("item_ambiguous_or_missing")
    item = matches[0]
    interaction.authorize_item_transfer(world, npc, item)
    return item


def offer_work(world, npc, quote):
    shop = next((s for s in world.get("shops", [])
                 if s.get("shopkeeper_id") == npc["id"]
                 and s.get("economy_origin") == ORIGIN), None)
    if shop is None or shop.get("work_thread_id"):
        economy.fail("native_work_unavailable")
    if world.get("currency", {}).get(npc["id"], 0) < 100:
        economy.fail("reward_funds_unavailable")
    state = interaction.get(world)
    if len(state["threads"]) >= interaction.MAX_THREADS:
        economy.fail("adventure_capacity")
    thread = interaction._new_thread(
        world, state, quote, npc,
        routes=[{"kind": "talk", "target": npc["id"]}],
    )
    interaction.validate(state, world)
    world[interaction.KEY] = state
    identity = thread["thread_id"]
    world.setdefault("item_rewards", {})[identity] = {
        "source_npc_id": npc["id"], "item_ids": [], "currency_cp": 100,
        "origin": ORIGIN,
    }
    shop["work_thread_id"] = identity
    return identity


def reserved_funds(world, actor, excluding=None):
    return sum(r["currency_cp"] for key, r in world.get("item_rewards", {}).items()
               if key != excluding and key not in world.get("claimed_item_rewards", [])
               and r.get("origin") == ORIGIN and r.get("source_npc_id") == actor)


def talk(world, npc, quote):
    if len(quote) > 400:
        economy.fail("dialogue_quote_too_long")
    return interaction.record_item_dialogue(world, npc, quote)


def loot_source(world, identity):
    npcs = [n for n in world.get("npcs", []) if n.get("id") == identity]
    if len(npcs) == 1:
        npc = npcs[0]
        if (npc.get("location") != world["location"]
                or not (npc.get("dead") or npc.get("alive") is False
                        or npc.get("combat_status") == "defeated"
                        or npc.get("state") == "dead")):
            economy.fail("loot_actor_not_defeated")
        return npc.get("inventory", []), f"corpse:{identity}"
    boxes = [c for c in world.get("containers", []) if c.get("id") == identity]
    if len(boxes) != 1:
        economy.fail("loot_source_unknown")
    box = boxes[0]
    if (box.get("location") != world["location"] or box.get("locked") is not False
            or not (box.get("opened") is True or box.get("state") == "open")):
        economy.fail("container_not_accessible")
    return box.get("contents", []), "ground"
