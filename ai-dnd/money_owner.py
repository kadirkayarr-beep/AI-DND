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

A room or goods decision is carried out before the reply by the room card or the counter (`bold_acts`), which take the
coin held out as tender only through `claim`: one turn's coin goes to one operation, once. After the person answered,
`open_card_after_reply` opens the one card the decision names (a gift or a tip card) and nothing else; the card
itself, and the coin it may move on confirmation, are `economic_actions`'.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

DealKind = Literal["goods", "room", "tip", "gift", "paid_before", "none"]
DecisionKind = Literal["goods", "room", "tip", "gift", "paid_before", "unclear", "bribe"]
_DEALS = ("goods", "room", "tip", "gift", "paid_before")

COIN_LEFT_BEHIND = "Uzattığın para kimseye geçmedi; o kişi geride kaldı, para kesende."
# The only decisions whose card opens after the reply, and the card's purpose: a Hediye card, a Bahşiş card.
_CARD_AFTER_REPLY = {"gift": "gift", "tip": "tip"}
# Coin held out for these waits for the player's confirmation of a card or the counter; a past payment, a bribe
# (the guard's own card) and unclear coin do not.
WAITS_FOR_CONFIRMATION = frozenset({"goods", "room", "gift", "tip"})


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


def forget_turn(session: Any) -> None:
    """A turn that runs no front reading (a check turn) starts with no decision, answer or note of an earlier line.

    `front_proposal.begin` resets the same fields for every turn that reads the line.
    """
    session._coin_decision = None
    session._coin_answer = None
    session._coin_answer_for = None
    session._coin_answer_npc = None
    session._coin_claimed = False
    session._turn_notes = []


def claim(session: Any, purpose: Literal["room", "goods"]) -> int | None:
    """The coin held out this turn, handed once to the one operation the decision names (D5); None otherwise.

    Only a `room` or `goods` decision has an operation that takes coin as tender (the room card, the counter's offer).
    The first claim for the decision's own purpose takes the coin and marks it claimed (`session._coin_claimed`);
    a second claim, a claim for another purpose and a claim with no decision get None. An offer asked for with no coin
    in hand (D29) is claimed with no tender.
    """
    decision = current(session)
    if decision is None or decision.kind != purpose or getattr(session, "_coin_claimed", False):
        return None
    session._coin_claimed = True
    return decision.amount_cp if decision.amount_cp > 0 else None


def blocks_money_moves(session: Any) -> bool:
    """Coin is leaving the player's hand this turn: no shift is worked and no wage is drawn on the same line (D4)."""
    decision = current(session)
    return decision is not None and decision.amount_cp > 0


def unclear_note(amount_cp: int) -> str:
    """This turn's note for coin held out with no meaning the engine could check (D29): nothing changed hands."""
    return f"oyuncu {amount_cp} bakır gösterdi, ne için olduğu belli değil; para el değiştirmedi"


def _tell(result: dict[str, Any], text: str) -> None:
    result["narration"] = f"{result.get('narration') or ''} {text}".strip()


def _note(session: Any, npc_id: str | None, text: str) -> None:
    """A note for this turn only, as an (npc_id | None, text) pair: the person's view reads its own (D28)."""
    notes = getattr(session, "_turn_notes", None)
    if not isinstance(notes, list):
        notes = session._turn_notes = []
    notes.append((npc_id, text))


def parts_for(world: dict, session: Any, npc_id: str) -> list[str]:
    """Only the engine's current decision and this recipient's open offers."""
    import economic_actions
    import bold_acts
    parts = set()
    decision = current(session)
    if decision is not None and decision.npc_id == npc_id:
        if decision.kind == "goods" and decision.goods_key:
            parts.add("goods:" + decision.goods_key)
            if decision.tip_cp > 0:
                parts.add("tip")
        elif decision.kind in ("room", "gift", "tip"):
            parts.add(decision.kind)
    npc = economic_actions._npc(world, npc_id)
    counter = bold_acts.offer_still_open(world, npc)
    if counter is not None:
        parts.add("goods:" + counter["key"])
        if any(type(counter.get(key)) is int and counter[key] > 0 for key in ("tip_cp", "tip_after_cp")):
            parts.add("tip")
    for record in economic_actions.offer_records(world).values():
        offer = economic_actions.offer_from_record(record)
        if offer is None or offer.status != "prepared" or offer.proposal.recipient_id != npc_id:
            continue
        purpose = offer.proposal.purpose
        if purpose == "purchase" and offer.proposal.item_id:
            parts.add("goods:" + offer.proposal.item_id)
        elif purpose in ("room", "gift", "tip"):
            parts.add(purpose)
        if purpose in ("purchase", "room", "gift", "tip") and any(line.kind == "tip" for line in offer.lines):
            parts.add("tip")
    return sorted(parts)


def read_answer(session: Any, packet: Any, npc_id: str, parts: list[str]) -> None:
    packet = packet if isinstance(packet, dict) else {}
    answer = packet.get("coin_answer")
    part = packet.get("coin_answer_for")
    session._coin_answer = answer if isinstance(answer, str) and answer in ("takes", "declines", "none") else None
    session._coin_answer_for = part if isinstance(part, str) and part in parts else "unclear"
    session._coin_answer_npc = npc_id

def open_card_after_reply(session: Any, result: dict[str, Any], coin_answer: str | None = None,
                          coin_answer_for: str | None = None) -> None:
    """After the person answered, the card this turn's decision names opens for the coin held out, and no other.

    A gift decision opens a Hediye card and a tip decision a Bahşiş card; neither moves coin before it is confirmed.
    Goods, room, a past payment and a bribe open nothing here: the counter, the room card and the guard's card are
    their own owners'. An unclear decision opens no card and no word path (D29); the coin is noted for this turn.
    Coin with no decision of its own opens nothing: never a silent gift. Coin a room or the counter read this line
    is theirs; coin whose taker was left behind a change of place is told back in the purse; coin held out to nobody
    named asks who.

    The coin in hand is `session._coin_paid` (amount, person, place), written with the decision and taken off the
    hand by the room or the counter that reads it; the caller clears it after this call. A decision opens a card only
    for that coin (same person, same amount), so one left from another line never does. `coin_answer` and
    `coin_answer_for` are the person's spoken answer about the coin, read from plan Task 10 on.
    """
    import economic_actions
    held = getattr(session, "_coin_paid", None)
    action = result.get("action_result") if isinstance(result, dict) else None
    answer = coin_answer if coin_answer is not None else getattr(session, "_coin_answer", None)
    part = coin_answer_for if coin_answer_for is not None else getattr(session, "_coin_answer_for", None)
    speaker = getattr(session, "_coin_answer_npc", None)
    npc = economic_actions._npc(session.world_state, speaker) if isinstance(speaker, str) else None
    if (isinstance(action, dict) and action.get("npc_id") == speaker and npc is not None
            and economic_actions._is_here(session.world_state, npc)):
        if answer == "declines":
            import bold_acts
            import living_world
            declined_part = part if part != "unclear" and economic_actions._is_part(part) else "*"
            decision = current(session)
            amount = decision.amount_cp if decision is not None and decision.npc_id == speaker else 0
            economic_actions.record_decline(session.world_state, speaker, declined_part, amount,
                day=economic_actions.game_day(session.world_state),
                turn=session.world_state.get("flags", {}).get("turn_index", 0))
            bold_acts.close_declined_counter(session.world_state, speaker, declined_part)
            note = f"{living_world.turkish_initial_upper(living_world.public_npc_name(npc))} az önce parayı geri çevirdi."
            _note(session, speaker, note)
            _tell(result, note)
            return  # a capped/unwritten no must not open a card either
        if answer == "takes" and part not in (None, "unclear", "*"):
            economic_actions.clear_decline(session.world_state, speaker, part)
    if not held or not isinstance(action, dict):
        return
    amount, person, place = held
    if action.get("coin_seen_by") or action.get("action") == "shop_offer":
        return  # the room or the counter offer read this coin; only its own card or trade can take it
    if place != session.world_state.get("location"):
        _tell(result, COIN_LEFT_BEHIND)
        return
    recipient = person.get("id") if isinstance(person, dict) else None
    recipient = recipient if isinstance(recipient, str) and recipient else None
    decision = current(session)
    ours = decision is not None and decision.npc_id == recipient and decision.amount_cp == amount
    if ours and decision.kind == "unclear" and decision.amount_cp > 0:
        _note(session, recipient, unclear_note(decision.amount_cp))
    if recipient is None:
        _tell(result, economic_actions._CLARIFY["npc_unknown"])
        return
    purpose = _CARD_AFTER_REPLY.get(decision.kind) if ours else None
    if purpose is None:
        return  # only the decision names a card; held-out coin is never a gift by default
    prepared = economic_actions.prepare_from_turn(
        session, economic_actions.turn_proposal(purpose, recipient, amount_cp=decision.amount_cp))
    _tell(result, prepared.public_message)


def price_negotiation_offers(world: dict) -> list[dict]:
    """Current, local price targets; opaque ids bind a proposal to an offer and its day."""
    import bold_acts
    import economic_actions as ea
    import shop_trade
    import world_reactions
    if ea._combat(world):
        return []
    day = ea.game_day(world)
    people = [npc for npc in world.get("npcs", []) if isinstance(npc, dict)
              and ea._is_here(world, npc) and shop_trade.is_vendor(world, npc)
              and not world_reactions.refuses(world, npc)]
    result = []
    for npc in people:
        for data in ea.offer_records(world).values():
            offer = ea.offer_from_record(data)
            if (offer is not None and offer.status == "prepared" and offer.proposal.purpose == "room"
                    and offer.proposal.recipient_id == npc.get("id")):
                result.append({"offer_id": f"room:{offer.offer_id}:{day}", "npc_id": npc["id"],
                               "kind": "room", "item": "room"})
        counter = bold_acts.offer_still_open(world, npc)
        if counter is not None and any(row[0] == counter.get("key") for row in shop_trade.PRICES):
            result.append({"offer_id": f"counter:{npc['id']}:{counter['key']}:{counter['seq']}:{counter['turn']}:{day}",
                           "npc_id": npc["id"], "kind": "goods", "item": counter["key"]})
    return result


def price_negotiation(world: dict, value: Any, player_input: str) -> dict | None:
    """Validate identity and verbatim evidence, never infer semantic intent from a word list."""
    if (not isinstance(value, dict) or set(value) != {"offer_id", "npc_id", "evidence_quote"}
            or not isinstance(player_input, str)):
        return None
    quote = value.get("evidence_quote")
    if not isinstance(quote, str) or not quote.strip() or len(quote) > 240 or quote not in player_input:
        return None
    if not any(row["offer_id"] == value.get("offer_id") and row["npc_id"] == value.get("npc_id")
               for row in price_negotiation_offers(world)):
        return None
    return dict(value)

def haggle(session: Any, npc: dict | None, check_result: Mapping, *,
           negotiation: Any = None, player_input: str = "") -> str | None:
    """An explicit price-negotiation proposal plus an engine check; no payment occurs."""
    import copy
    import bold_acts
    import economic_actions as ea
    import living_world
    import shop_trade
    import world_reactions
    world = session.world_state
    if (not isinstance(npc, dict) or not isinstance(check_result, Mapping)
            or check_result.get("skill") not in ("Persuasion", "Intimidation", "Deception")
            or not ea._is_here(world, npc) or ea._combat(world)
            or not shop_trade.is_vendor(world, npc)
            or world_reactions.refuses(world, npc)):
        return None
    admitted = price_negotiation(world, negotiation, player_input)
    if admitted is None or admitted["npc_id"] != npc.get("id"):
        return None
    chosen = next(row for row in price_negotiation_offers(world) if row["offer_id"] == admitted["offer_id"])
    room = next((offer for data in ea.offer_records(world).values()
                 if (offer := ea.offer_from_record(data)) is not None
                 and offer.status == "prepared" and offer.proposal.purpose == "room"
                 and offer.proposal.recipient_id == npc.get("id")
                 and chosen["offer_id"] == f"room:{offer.offer_id}:{ea.game_day(world)}"), None)
    counter = bold_acts.offer_still_open(world, npc)
    if room is not None:
        key, label, base = "room", "oda", bold_acts._ROOM_PRICE
        price = bold_acts.room_price(world, npc)
    elif counter is not None and chosen["kind"] == "goods" and chosen["item"] == counter.get("key"):
        entry = next((row for row in shop_trade.PRICES if row[0] == counter.get("key")), None)
        if entry is None:
            return None
        key, label, base = entry
        price = next(row["unit_cp"] for row in shop_trade.goods(world, npc) if row["key"] == key)
    else:
        return None
    if ea.declined(world, npc["id"], "room" if key == "room" else "goods:" + key, day=ea.game_day(world)):
        return None
    if check_result.get("result") != "BAŞARILI":
        return f"İkna tutmadı: fiyat aynı, {label} {price} bakır."
    old = {field: copy.deepcopy(npc[field]) for field in ("price_cut_cp_v1", "price_cut_day_v1") if field in npc}
    cut = shop_trade.apply_cut(world, npc, key, base)
    if cut is None:
        return None
    if room is not None:
        refreshed = ea.prepare_from_turn(session, replace(room.proposal, amount_cp=base - cut))
        if refreshed.status != "prepared":
            for field in ("price_cut_cp_v1", "price_cut_day_v1"):
                npc.pop(field, None)
            npc.update(old)
            return None
    else:
        counter["turn"] = world.get("flags", {}).get("turn_index", 0)
    who = living_world.public_npc_name(npc)
    return f"İkna başarılı: {who} indirim yapıyor, {label} artık {base - cut} bakır."