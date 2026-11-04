"""One counter trade with whoever serves: the price, the purse, the goods and the stock move together or not at all.

Python owns it. What the speaker is told a thing costs comes from the same table this charges. Talk never
moves coin or goods here: a line that wants something only opens an offer, and the trade is one typed
'/item shop_buy <npc_id> <key> <count> <seq> <total_cp>' line, committed on a copy and swapped in whole. The
coin itself moves only through the one economic owner (economic_actions.apply_resolution).
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
TIP_KEPT = "Bahşiş geçmedi; kesende kaldı."  # the goods were confirmed alone while the offer carried a tip (D1)


class TradeRefused(equipment_economy.EquipmentError):
    """A refusal that changed nothing; quote is the fresh offer when there is one to show."""

    def __init__(self, reason: str, quote: dict[str, Any] | None = None):
        super().__init__(reason)
        self.quote = quote


def _words(entry: tuple[str, str, int]) -> set[str]:
    key, label, _ = entry
    return {key, *(word for word in living_world.normalize_text(label).split() if len(word) >= 4)}


_SOFTENED = {"p": "b", "k": "g", "t": "d"}  # Turkish voices a final stop before a vowel: şarap -> şarabı


def _named(word: str) -> str:
    """The word as said, with its last stop softened before a suffix vowel: 'yemek' also hears 'yemeği'."""
    soft = _SOFTENED.get(word[-1])
    tail = f"(?:{re.escape(word[-1])}|{soft}(?=[aeiou]))" if soft else re.escape(word[-1])
    return rf"\b{re.escape(word[:-1])}{tail}(?![zd])"


def priced_in(text: Any) -> tuple[str, str, int] | None:
    """The thing on the list the words name, by its key or a word of the label the speaker says: 'biraz' is no beer."""
    folded = living_world.normalize_text(text)
    return next((entry for entry in PRICES
                 if any(re.search(_named(word), folded) for word in _words(entry))), None)


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
    return [{"key": key, "label": label, "unit_cp": max(0, price - _cut(npc, key)), "stock": _stock(npc, key),
             "discount_cp": min(price, _cut(npc, key))}
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


def counter(world: dict[str, Any]) -> dict[str, Any]:
    """What the counter here shows the panel: whoever serves, the list, the purse and the offer number.

    Reading it writes nothing. The gold, silver and copper split is for the eye only; the trade counts copper.
    """
    import scheduled_events
    import world_reactions
    total = purse_cp(world)
    result: dict[str, Any] = {"status": "unavailable", "reason": None, "vendor": None, "lines": [],
                              "purse": {"total_cp": total, "gp": total // 100, "sp": total % 100 // 10, "cp": total % 10},
                              "seq": seq(world)}
    here = world.get("location")
    npc = next((npc for npc in scheduled_events.visible_npcs(world)
                if npc.get("location") == here and is_vendor(world, npc)), None)
    death = world.get("death_state") or {}
    if npc is None:
        result["reason"] = "no_vendor"
    elif (world.get("combat") or {}).get("active") or death.get("dead") or death.get("terminal"):
        result["reason"] = "not_now"
    elif not equipment_economy.npc_can_act(npc):
        result["reason"] = "vendor_unavailable"
    elif world_reactions.refuses(world, npc):
        result["reason"] = "vendor_refuses"
    else:
        result.update(status="ready", lines=goods(world, npc))
    if npc is not None:
        result["vendor"] = {"npc_id": str(npc.get("id")), "name": living_world.public_npc_name(npc)}
    return result


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


def _this_offer(world: dict[str, Any], npc_id: str, key: str, fresh: dict[str, Any]) -> dict[str, Any] | None:
    """The counter's open offer when it is this very one: the same person, the same goods, no trade settled since."""
    opened = (world.get("flags") or {}).get("counter_offer_v1")
    if (not isinstance(opened, dict) or opened.get("npc_id") != npc_id or opened.get("key") != key
            or opened.get("seq") != fresh["seq"]):
        return None
    return opened


def _recorded_tip(world: dict[str, Any], npc_id: str, key: str, fresh: dict[str, Any]) -> int:
    """The tip this very offer carries as Python wrote it (`bold_acts._with_tender`), whether or not it can be paid."""
    opened = _this_offer(world, npc_id, key, fresh)
    tip = opened.get("tip_cp") if opened is not None else None
    return tip if type(tip) is int and tip >= 1 else 0


def _tip(world: dict[str, Any], npc_id: str, key: str, count: int, fresh: dict[str, Any]) -> int:
    """The tip this sale may pay with the goods, or 0 (design §11 D1).

    Only the very offer's own tip: the same person, goods and offer number, one of the goods, a tip of at least 1,
    the coin held out being the price and the tip, and the purse holding both. A tip the person declined today is
    not paid (§3b; the goods alone still are). Reads the world and writes nothing.
    """
    import economic_actions
    tip = _recorded_tip(world, npc_id, key, fresh)
    if not tip or type(count) is not int or count != 1:
        return 0
    paid = fresh["total_cp"] + tip
    tender = _this_offer(world, npc_id, key, fresh).get("tender_cp")
    if type(tender) is not int or tender != paid or paid > fresh["purse_cp"]:
        return 0
    if economic_actions.declined(world, npc_id, "tip", day=economic_actions.game_day(world)):
        return 0
    return tip


def _tender(world: dict[str, Any], npc_id: str, key: str, count: int, fresh: dict[str, Any]) -> int | None:
    """Coin held out with the open offer counts as the sale's tender only when this is that very offer.

    Coin held out for the goods and a tip is the tipped sale's (`commit` takes it there); a sale of the goods alone
    takes none of it, so no part of a kept change is ever counted back as change (D1).
    """
    opened = _this_offer(world, npc_id, key, fresh)
    if opened is None or "tip_cp" in opened:
        return None
    tender = opened.get("tender_cp")
    if count != 1 or type(tender) is not int or not fresh["total_cp"] <= tender <= fresh["purse_cp"]:
        return None
    return tender


def commit(world: dict[str, Any], npc_id: str, key: str, count: int, offer_seq: int, confirmed_total_cp: int) -> str:
    """The counter sale: the price, purse, goods and stock checked here; the coin moved by the one economic owner.

    Everything is written on one candidate copy: the coin and the ledger by `economic_actions.apply_resolution`,
    then the goods, stock, sequence and served turn here, then the whole receipt (coin, goods and stock) is checked
    against the real before/after of the candidate, and only then is the candidate swapped in. Raises TradeRefused
    or EconomicReceiptError with the world untouched, or returns the line to show.

    The confirmed total decides what is paid, and nothing more is ever taken (design §11 D1): the price and the
    offer's tip (`_tip`) buy the goods and pay the tip on one receipt; the price alone buys the goods with no tip and
    no tender, and says the tip stayed in the purse when the offer carried one; the price and a tip that can no
    longer be paid is `tip_unavailable`; any other total is `price_changed`.
    """
    import bold_acts
    import economic_actions
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
    if economic_actions.declined(candidate, npc_id, "goods:" + key, day=economic_actions.game_day(candidate)):
        raise TradeRefused("npc_declined", fresh)
    if offer_seq != fresh["seq"]:
        raise TradeRefused("offer_stale", fresh)
    if type(count) is not int or count < 1:
        raise TradeRefused("invalid_count", fresh)
    recorded = _recorded_tip(candidate, npc_id, key, fresh)
    tip = _tip(candidate, npc_id, key, count, fresh)
    if tip and confirmed_total_cp == fresh["total_cp"] + tip:
        pass  # the goods and the tip, as the offer showed them
    elif confirmed_total_cp == fresh["total_cp"]:
        tip = 0  # the goods alone: the tip stays in the purse
    elif recorded and confirmed_total_cp == fresh["total_cp"] + recorded:
        raise TradeRefused("tip_unavailable", fresh)
    else:
        raise TradeRefused("price_changed", fresh)
    if count > fresh["stock"]:
        raise TradeRefused("out_of_stock", fresh)
    if world_reactions.refuses(candidate, npc):
        raise TradeRefused("vendor_refuses", fresh)
    if not fresh["can_pay"]:
        raise TradeRefused("insufficient_funds", fresh)
    total = fresh["total_cp"]
    candidate_before = copy.deepcopy(candidate)
    tender = total + tip if tip else _tender(candidate, npc_id, key, count, fresh)
    offer = economic_actions.counter_purchase_offer(candidate, npc_id=npc_id, key=key, count=count,
                                                    unit_cp=fresh["unit_cp"], tender_cp=tender, tip_cp=tip)
    state = economic_actions.EconomicState(world=candidate, character=None)
    resolution = economic_actions.resolve_offer(
        state, offer, operation_id=economic_actions.operation_id_for(candidate, "purchase"))
    if resolution.status == "applied":
        resolution = economic_actions.apply_resolution(state, resolution, confirmed_offer=offer)
    if resolution.status != "applied":
        raise TradeRefused("insufficient_funds" if resolution.reason_code in ("no_money", "tender_invalid")
                           else "offer_stale", fresh)
    if resolution.net_debit_cp != confirmed_total_cp:
        # A tip line the economic owner refused (it no longer fits, or it was declined) leaves the candidate unused:
        # the confirmed total is paid whole or not at all.
        raise TradeRefused("tip_unavailable" if tip else "price_changed", fresh)
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
    # Decision 12: the one receipt checks the coin, the goods and the stock together on the candidate.
    economic_actions.validate_economic_resolution(
        economic_actions.economic_facts(economic_actions.EconomicState(world=candidate_before, character=None)),
        economic_actions.economic_facts(state), resolution, confirmed_offer=offer)
    equipment_economy.validate_world(candidate)
    world.clear()
    world.update(candidate)
    who = living_world.public_npc_name(npc)
    if tip:
        return (f"{who} önüne {count} {fresh['label']} bırakıyor; "
                f"{total} bakır ve {tip} bakır bahşiş kesenden tezgâha geçiyor.")
    change = f" Uzattığın {resolution.tender_cp} bakırdan {resolution.change_cp} bakır para üstü sayılıyor." \
        if resolution.tender_cp is not None and resolution.change_cp else ""
    kept = f" {TIP_KEPT}" if recorded else ""
    return f"{who} önüne {count} {fresh['label']} bırakıyor; {total} bakır kesenden tezgâha geçiyor.{change}{kept}"


def commit_typed(world: dict[str, Any], args: list[str]) -> str:
    """'/item shop_buy <npc_id> <key> <count> <seq> <total_cp>'."""
    if len(args) != 5:
        equipment_economy.fail("invalid_item_command")
    npc_id, key, *numbers = args
    if not all(re.fullmatch(r"\d{1,9}", number) for number in numbers):
        equipment_economy.fail("invalid_item_command")
    count, offer_seq, total = (int(number) for number in numbers)
    return commit(world, npc_id, key, count, offer_seq, total)
