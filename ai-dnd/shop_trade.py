"""One counter trade with whoever serves: the price, the purse, the goods and the stock move together or not at all.

Python owns it. What the speaker is told a thing costs comes from the same table this charges. Talk never
moves coin or goods here: a line that wants something only opens an offer, and the trade is one typed
'/item shop_buy <npc_id> <key> <count> <seq> <total_cp>' line, committed on a copy and swapped in whole.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import equipment_economy
import living_world

# key (as typed and folded), label (as told and as the item's name), unit price in copper
PRICES = (("bira", "bira", 4), ("sarap", "şarap", 20), ("yemek", "tabak yemek", 30))
SERVER = re.compile(r"\b(?:barmen|hanci|meyhaneci|garson|satici|asci)")
DEFAULT_STOCK = 12  # read when the vendor's own count was never written; written only by a trade
LEDGER_CAP = 20
KEY = "shop_trades_v1"


class TradeRefused(equipment_economy.EquipmentError):
    """A refusal that changed nothing; quote is the fresh offer when there is one to show."""

    def __init__(self, reason: str, quote: dict[str, Any] | None = None):
        super().__init__(reason)
        self.quote = quote


def _words(entry: tuple[str, str, int]) -> set[str]:
    key, label, _ = entry
    return {key, *(word for word in living_world.normalize_text(label).split() if len(word) >= 4)}


def priced_in(text: Any) -> tuple[str, str, int] | None:
    """The thing on the list the words name, by its key or a word of the label the speaker says: 'biraz' is no beer."""
    folded = living_world.normalize_text(text)
    return next((entry for entry in PRICES
                 if any(re.search(rf"\b{re.escape(word)}(?![zd])", folded) for word in _words(entry))), None)


def is_priced(text: Any) -> bool:
    return priced_in(text) is not None


def is_vendor(world: dict[str, Any], npc: Any) -> bool:
    """Whoever serves sells the list; nobody else does."""
    return isinstance(npc, dict) and bool(SERVER.search(living_world.normalize_text(npc.get("role"))))


def seq(world: dict[str, Any]) -> int:
    value = (world.get(KEY) or {}).get("seq", 0)
    return value if type(value) is int and value >= 0 else 0


def _cut(npc: dict[str, Any], key: str) -> int:
    """The discount hook: a later owner of haggling may write it; nothing here does."""
    cuts = npc.get("price_cut_cp_v1")
    value = cuts.get(key, 0) if isinstance(cuts, dict) else 0
    return value if type(value) is int and value > 0 else 0


def _stock(npc: dict[str, Any], key: str) -> int:
    wares = npc.get("wares_v1")
    entry = wares.get(key) if isinstance(wares, dict) else None
    value = entry.get("stock") if isinstance(entry, dict) else None
    return value if type(value) is int and value >= 0 else DEFAULT_STOCK


def goods(world: dict[str, Any], npc: Any) -> list[dict[str, Any]]:
    if not is_vendor(world, npc):
        return []
    return [{"key": key, "label": label, "unit_cp": max(0, price - _cut(npc, key)), "stock": _stock(npc, key)}
            for key, label, price in PRICES]


def purse_cp(world: dict[str, Any]) -> int:
    """The purse in copper, with gold still written in the pack counted as the first spend will settle it."""
    held = (world.get("currency") or {}).get("player", 0)
    held = held if type(held) is int else 0
    for item in world.get("inventory", []):
        match = re.fullmatch(r"(\d+) (?:Altın|GP)", str(item.get("name") if isinstance(item, dict) else item))
        held += int(match.group(1)) * 100 if match else 0
    return held


def _npc(world: dict[str, Any], npc_id: str) -> dict[str, Any] | None:
    return next((npc for npc in world.get("npcs", []) if isinstance(npc, dict) and npc.get("id") == npc_id), None)


def quote(world: dict[str, Any], npc_id: str, key: str, count: int) -> dict[str, Any] | None:
    """What the counter offers now. Reading it writes nothing."""
    npc = _npc(world, npc_id)
    line = next((line for line in goods(world, npc) if line["key"] == key), None)
    if line is None:
        return None
    count = count if type(count) is int else 0
    total = line["unit_cp"] * max(count, 0)
    purse = purse_cp(world)
    return {"npc_id": npc_id, "key": key, "label": line["label"], "count": count, "unit_cp": line["unit_cp"],
            "total_cp": total, "stock": line["stock"], "purse_cp": purse, "seq": seq(world),
            "can_pay": type(purse) is int and purse >= total}


def commit(world: dict[str, Any], npc_id: str, key: str, count: int, offer_seq: int, confirmed_total_cp: int) -> str:
    """The one writer of a counter sale. Raises TradeRefused (world untouched) or returns the line to show."""
    import bold_acts
    import world_reactions
    candidate = copy.deepcopy(world)
    bold_acts.settle_coin_labels(candidate)
    npc = _npc(candidate, npc_id)
    if npc is None:
        raise TradeRefused("npc_unknown")
    if npc.get("location") != candidate.get("location") or not equipment_economy.npc_can_act(npc):
        raise TradeRefused("npc_unavailable")
    if not is_vendor(candidate, npc):
        raise TradeRefused("not_a_vendor")
    fresh = quote(candidate, npc_id, key, count)
    if fresh is None:
        raise TradeRefused("goods_unknown")
    if offer_seq != fresh["seq"]:
        raise TradeRefused("offer_stale", fresh)
    if type(count) is not int or count < 1:
        raise TradeRefused("invalid_count", fresh)
    if confirmed_total_cp != fresh["total_cp"]:
        raise TradeRefused("price_changed", fresh)
    if count > fresh["stock"]:
        raise TradeRefused("out_of_stock", fresh)
    if world_reactions.refuses(candidate, npc):
        raise TradeRefused("vendor_refuses", fresh)
    if not fresh["can_pay"]:
        raise TradeRefused("insufficient_funds", fresh)
    total = fresh["total_cp"]
    equipment_economy.pay(candidate, "player", npc_id, total)  # the whole price, once; no change is made
    name = fresh["label"][:1].upper() + fresh["label"][1:]
    for _ in range(count):
        equipment_economy.grant_named_item(candidate, name)
    npc.setdefault("wares_v1", {})[key] = {"stock": fresh["stock"] - count}
    flags = candidate.setdefault("flags", {})
    turn = flags.get("turn_index", 0)
    record = candidate.setdefault(KEY, {})
    record["seq"] = fresh["seq"] + 1
    ledger = [*(record.get("ledger") or [])[-(LEDGER_CAP - 1):],
              {"seq": record["seq"], "npc_id": npc_id, "key": key, "count": count, "total_cp": total, "turn_index": turn}]
    record["ledger"] = ledger
    flags["served_turn"] = turn
    equipment_economy.validate_world(candidate)
    world.clear()
    world.update(candidate)
    who = living_world.public_npc_name(npc)
    return f"{who} önüne {count} {fresh['label']} bırakıyor; {total} bakır kesenden tezgâha geçiyor."


def commit_typed(world: dict[str, Any], args: list[str]) -> str:
    """'/item shop_buy <npc_id> <key> <count> <seq> <total_cp>'."""
    if len(args) != 5:
        equipment_economy.fail("invalid_item_command")
    npc_id, key, *numbers = args
    if not all(re.fullmatch(r"\d{1,9}", number) for number in numbers):
        equipment_economy.fail("invalid_item_command")
    count, offer_seq, total = (int(number) for number in numbers)
    return commit(world, npc_id, key, count, offer_seq, total)
