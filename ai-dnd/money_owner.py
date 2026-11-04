"""What coin held out this turn means: one decision, made here and nowhere else.

The model proposes (the front reading's `deal`, `deal_goods` and `keep_change`), Python checks it against the
world and decides; no word is read here. The decision moves no coin and writes nothing: the purse, the ledger,
the receipts and the declines stay with `economic_actions` and `shop_trade`, and the cards they open read it.

Order (design §3a, §12 D29, §11 D15): no coin and no deal is no decision, and only then may the old word path
run. Coin to the guard making an arrest is a bribe whatever the deal. A fight makes every deal unclear. A model
deal is checked by its kind and, when it fails, is `unclear` from the model: it never falls to structure or to a
card of another kind. Only when the model gave no deal does held-out coin get a structural meaning (the open
counter offer's tender, else a room) and otherwise it is `unclear`. Coin never becomes a gift unless the model
said so. Opening an offer is not holding out coin: a goods or room deal with no coin still decides, with no tender.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

DealKind = Literal["goods", "room", "tip", "gift", "paid_before", "none"]
DecisionKind = Literal["goods", "room", "tip", "gift", "paid_before", "unclear", "bribe"]
_DEALS = ("goods", "room", "tip", "gift", "paid_before")


@dataclass(frozen=True)
class Deal:
    """The model's reading of what this line's money is for, kept only when its kind is one of ours."""
    kind: DealKind
    goods_key: str | None  # a listed goods key, on a goods deal only
    keep_change: bool      # "üstü kalsın", on a goods deal only


@dataclass(frozen=True)
class CoinDecision:
    kind: DecisionKind
    npc_id: str | None
    amount_cp: int            # coin held out this turn, 0 if none
    tip_cp: int               # Python's figure: only goods + keep_change, amount - unit price
    goods_key: str | None
    source: Literal["model", "structural"]
    place_id: str | None


_Meaning = tuple[DecisionKind, int, str | None]  # kind, tip_cp, goods_key
_UNCLEAR: _Meaning = ("unclear", 0, None)


def _listed_keys(listed: Any) -> set[str]:
    goods = listed.get("goods") if isinstance(listed, Mapping) else None
    entries = goods if isinstance(goods, list) else []
    return {entry["id"] for entry in entries if isinstance(entry, Mapping) and isinstance(entry.get("id"), str)}


def read_deal(front: Mapping[str, Any] | None, listed: Mapping[str, Any]) -> Deal | None:
    """The reading's deal, or None when it gave none ("none", missing or broken). Unlisted goods read as no goods."""
    kind = front.get("deal") if isinstance(front, Mapping) else None
    if not isinstance(kind, str) or kind not in _DEALS:
        return None
    if kind != "goods":
        return Deal(kind, None, False)
    wanted = front.get("deal_goods")
    goods_key = wanted if isinstance(wanted, str) and wanted in _listed_keys(listed) else None
    return Deal(kind, goods_key, front.get("keep_change") is True)


def _id_of(npc: Any) -> str | None:
    value = npc.get("id") if isinstance(npc, dict) else None
    return str(value) if value is not None else None


def _here(world: dict[str, Any], person: dict[str, Any] | None) -> bool:
    """Present as a card's own check sees it: the one NPC of that id, here and seen."""
    import economic_actions
    npc = economic_actions._npc(world, person.get("id")) if isinstance(person, dict) else None
    return npc is not None and economic_actions._is_here(world, npc)


def _unit_cp(world: dict[str, Any], person: dict[str, Any] | None, key: str | None) -> int | None:
    """What one of these goods costs at this person's counter now; None when they do not sell it."""
    import shop_trade
    return next((line["unit_cp"] for line in shop_trade.goods(world, person)
                 if key is not None and line["key"] == key), None)


def _can_host(world: dict[str, Any], person: dict[str, Any] | None) -> bool:
    """Whoever serves here may give a room, while the player holds none here tonight."""
    import economic_actions
    import shop_trade
    return shop_trade.is_vendor(world, person) and economic_actions._room_right(world) is None


def _tender_fits(world: dict[str, Any], price: int, amount: int) -> bool:
    """Coin held out pays a price only when price <= coin <= purse."""
    import shop_trade
    return price <= amount <= shop_trade.purse_cp(world)


def _checked(world: dict[str, Any], person: dict[str, Any] | None, amount: int, deal: Deal) -> _Meaning:
    """The model's deal held to its kind's rules; one that fails is unclear, never another card."""
    import bold_acts
    if deal.kind == "goods":
        unit = _unit_cp(world, person, deal.goods_key)
        if unit is not None and (amount == 0 or _tender_fits(world, unit, amount)):
            return "goods", amount - unit if deal.keep_change and amount > 0 else 0, deal.goods_key
    elif deal.kind == "room":
        if _can_host(world, person) and (
                amount == 0 or _tender_fits(world, bold_acts.room_price(world, person), amount)):
            return "room", 0, None
    elif deal.kind in ("gift", "tip"):
        if _here(world, person) and _tender_fits(world, 1, amount):
            return deal.kind, 0, None
    elif deal.kind == "paid_before":
        return "paid_before", 0, None
    return _UNCLEAR


def _structural(world: dict[str, Any], person: dict[str, Any] | None, amount: int) -> _Meaning:
    """No deal from the model: the coin is the open counter offer's tender, else a room's, else unclear."""
    import bold_acts
    opened = bold_acts.offer_still_open(world, person)
    unit = _unit_cp(world, person, opened.get("key")) if opened is not None else None
    if unit is not None and _tender_fits(world, unit, amount):
        return "goods", 0, opened["key"]
    if _can_host(world, person) and _tender_fits(world, bold_acts.room_price(world, person), amount):
        return "room", 0, None
    return _UNCLEAR


def decide(world: dict[str, Any], *, person: dict[str, Any] | None, amount_cp: int, deal: Deal | None,
           arrester: dict[str, Any] | None) -> CoinDecision | None:
    """The one meaning of this turn's coin; None only when no coin is held out and the model gave no deal.

    `person` is who the coin or the deal is for (None when nobody could be named); `arrester` is the guard making
    an arrest now, if any. Reads the world and writes nothing.
    """
    amount = amount_cp if type(amount_cp) is int and amount_cp > 0 else 0
    deal = deal if isinstance(deal, Deal) and deal.kind in _DEALS else None  # a "none" deal is no deal
    if amount == 0 and deal is None:
        return None
    place = world.get("location")
    place_id = place if isinstance(place, str) else None
    if arrester is not None and amount > 0 and (person is None or person.get("id") == arrester.get("id")):
        # D15: the guard weighs coin held out to them or to nobody named, whatever the deal says
        return CoinDecision("bribe", _id_of(arrester), amount, 0, None, "structural", place_id)
    source: Literal["model", "structural"] = "model" if deal is not None else "structural"
    if (world.get("combat") or {}).get("active"):
        kind, tip_cp, goods_key = _UNCLEAR  # R11: nothing is bought, given or rented in a fight
    elif deal is not None:
        kind, tip_cp, goods_key = _checked(world, person, amount, deal)
    else:
        kind, tip_cp, goods_key = _structural(world, person, amount)
    return CoinDecision(kind, _id_of(person), amount, tip_cp, goods_key, source, place_id)


def current(session: Any) -> CoinDecision | None:
    """This turn's decision, as the reading wrote it on the session (reset by `front_proposal.begin`)."""
    decision = getattr(session, "_coin_decision", None)
    return decision if isinstance(decision, CoinDecision) else None


def blocks_money_moves(session: Any) -> bool:
    """Coin is leaving the player's hand this turn: no shift is worked and no wage is drawn on the same line (D4)."""
    decision = current(session)
    return decision is not None and decision.amount_cp > 0
