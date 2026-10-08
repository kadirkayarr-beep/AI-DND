"""Incident rewards. Python sets amounts and catalog identity.

Narrated gold is not a payout. Magic items have no catalog here, so they
are refused. A paid signature is consumed once.
"""

from __future__ import annotations

import equipment_economy
from incidents import budgets, commit
from incidents.models import REWARD_CLASSES

COIN_CP = {
    "none": 0,
    "trinket": 0,
    "coin_small": 40,
    "coin_modest": 150,
    "mundane_item": 0,
    "rare_find": 0,
}
MUNDANE_CATALOG = "club"


class RewardError(ValueError):
    """The reward cannot be paid."""


def _wallet_source(world, amount):
    wallets = world.setdefault("currency", {})
    wallets["incident_source"] = wallets.get("incident_source", 0) + amount
    return "incident_source"


def grant(world, record, *, catalog_id=None):
    """Pay the incident's normalized reward class once."""
    reward_class = record["reward_class"]
    if reward_class not in REWARD_CLASSES:
        raise RewardError("unknown_class")
    location_id = record["location_id"]
    trigger_kind = (record["trigger_id"].split(":")[1] if record["trigger_id"].startswith("trg:") else "arrival")
    if not budgets.allowed(
        world, location_id=location_id, reward_class=reward_class, trigger_kind=trigger_kind,
    ):
        return None
    paid = None
    coin = COIN_CP.get(reward_class, 0)
    if reward_class in {"coin_small", "coin_modest"}:
        source = _wallet_source(world, coin)
        equipment_economy.pay(
            world, source, "player", coin, reward_id=record["incident_id"],
        )
        wallets = world.get("currency", {})
        if wallets.get(source) == 0:
            wallets.pop(source, None)
        paid = {"kind": "coin", "amount_cp": coin}
    elif reward_class in {"trinket", "mundane_item"}:
        label = "keepsake"
        if record["details"]["props"]:
            label = next(iter(record["details"]["props"].values()))["label"]
        item = equipment_economy.grant_named_item(world, label)
        paid = {"kind": "item", "item_id": item["item_id"]}
    elif reward_class == "rare_find":
        identity = catalog_id or MUNDANE_CATALOG
        try:
            item = equipment_economy.grant_catalog_item(world, identity)
        except equipment_economy.EquipmentError as error:
            raise RewardError("magic_item") from error
        paid = {"kind": "catalog", "item_id": item["item_id"]}
    budgets.consume(
        world, location_id=location_id, reward_class=reward_class,
        trigger_kind=trigger_kind, coin_cp=coin,
    )
    if record["lifecycle"] == "PRESENT":
        commit.engage(world, record["incident_id"])
    return paid


def reject_magic(world, catalog_id):
    """E21: a magic catalog identity never becomes an item."""
    try:
        equipment_economy.grant_catalog_item(world, catalog_id)
    except equipment_economy.EquipmentError:
        return True
    return False


def apply_action(world, action_result):
    if not isinstance(action_result, dict) or action_result.get("success") is not True:
        return None
    if action_result.get("action") not in {"claim_reward", "resolve"}:
        return None
    record = world.get("incidents", {}).get(action_result.get("incident_id"))
    if record is None:
        return None
    try:
        return grant(world, record, catalog_id=action_result.get("catalog_id"))
    except RewardError:
        return None
