"""Apply a frozen reward plan through the owners that already grant it."""

from __future__ import annotations

import copy

import equipment_economy

REWARD_MARKER = "quest:{quest_id}:{outcome}"


def apply_plan(character, world, quest, lore_state=None):
    """Pay one branch's gold, item and standing once, under its marker. A failed owner call restores the snapshots.

    The branch's XP is not paid here: ``xp_due`` (0 when none) is paid last by the session's XP boundary under the
    same marker as its receipt, so an XP grant that cannot be recorded is forfeited alone (B1) and never takes the
    gold back or keeps the branch unpaid. A marker lost from a save whose receipt exists is put back and nothing is
    paid again: the receipt is only ever written after the rest of the branch.
    """
    if quest.get("record_kind") != "dynamic":
        return None
    outcome = quest.get("outcome")
    plan = quest.get("reward_plan") or {}
    branch = plan.get(outcome)
    if not isinstance(branch, dict):
        return None
    marker = REWARD_MARKER.format(quest_id=quest["quest_id"], outcome=outcome)
    if quest.get("reward_application_id") == marker:
        return {"replayed": True, "marker": marker, "xp_due": 0}
    receipts = world.get("xp_awarded_event_ids")
    if branch.get("xp", 0) > 0 and isinstance(receipts, list) and marker in receipts:
        quest["reward_application_id"] = marker  # B1: the branch was paid in full before its marker was lost
        return {"replayed": True, "marker": marker, "xp_due": 0}
    before_character = copy.deepcopy(character)
    before_world = copy.deepcopy(world)
    before_quest = copy.deepcopy(quest)
    try:
        gold = branch.get("gold", 0)
        if gold > 0:
            pool = f"adventure-pool:{quest['quest_id']}"
            wallets = world.setdefault("currency", {})
            wallets[pool] = wallets.get(pool, 0) + gold
            equipment_economy.pay(world, pool, "player", gold, reward_id=marker)
            wallets.pop(pool, None)
        item = branch.get("item")
        if isinstance(item, str) and item:
            equipment_economy.grant_catalog_item(world, item)
        quest["reward_application_id"] = marker
        faction = branch.get("faction")
        if isinstance(faction, dict):
            from api.lore_authority.campaign_state import (
                EngineActionEvidence,
                apply_faction_standing,
            )

            if lore_state is None:
                raise ValueError("Hizip ödülü için kampanya bağı yok.")
            turn = world.get("flags", {}).get("turn_index", 0)
            if type(turn) is not int:
                turn = 0
            lore_action = marker.replace(".", "-")
            lore_state = apply_faction_standing(
                lore_state,
                faction_id=faction["id"],
                standing=faction["standing"],
                known_to_player=True,
                local_presence=True,
                evidence=EngineActionEvidence(lore_action, turn, "python_engine"),
                source_action_id=lore_action,
                turn_index=turn,
            )
    except Exception:
        character.clear()
        character.update(before_character)
        world.clear()
        world.update(before_world)
        quest.clear()
        quest.update(before_quest)
        raise
    return {"replayed": False, "marker": marker, "lore_state": lore_state, "xp_due": branch.get("xp", 0)}
