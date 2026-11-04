"""Economic offers: what the player proposes, what the engine accepts, and nothing moved while it is only a card.

Python owns it. A proposal (from the panel or a turn) is read against a copy of the world with the purse's
written coin labels settled, priced from the one server table (`shop_trade` goods, `bold_acts._ROOM_PRICE`),
and judged by the engine alone: whether the counterparty is here, can act, refuses the player, or is the guard
holding them (a bribe, decided later by a Persuasion check). Preparing writes nothing: no coin, goods, clock or
offer record. The API stores the offer in `world.flags.economic_offers` (A3); a turn's line stores it through
`prepare_from_turn` (A4).

A confirmed offer is resolved (`resolve_offer`, read only) and written by the one owner `apply_resolution`:
a settled copy first, the money receipt (`validate_economic_resolution`) on it, then the same steps on the live
dicts in place. Earned pay goes through `settle_entitlement`, once per event; an NPC's own give (`npc_gift`) and
the counter sale (`shop_trade.commit`, with `counter_purchase_offer`) are engine payments with no card, each with
its own `operation_id_for` id. Every coin a turn moves reaches the purses only through `apply_resolution`.

The API (A3) stores the card (`prepare_from_panel`), confirms it once (`confirm_offer`), cancels it, and after an
undo reopens only the card the undone action consumed (`reconcile_offers_after_undo`); closed cards are pruned.

A decline the NPC spoke is kept per part in `flags.money_declined` (`record_decline`): it cancels that NPC's open
cards of the part, opens none while it holds, and ends only by an explicit take (`clear_decline`) or a new game
day. Ledger operations carry a short `label` and the `payee_id`, read back by `recent_payments`.

No network, model or database call is made here.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import logging
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

MAX_CP = 999_999_999
MAX_COUNT = 999_999_999

Purpose = Literal["purchase", "room", "gift", "tip", "item_gift"]
Dependency = Literal["base_required", "all_or_none"]
_PURPOSES = ("purchase", "room", "gift", "tip", "item_gift")
_DEPENDENCIES = ("base_required", "all_or_none")
_KIND_OF = {"purchase": "goods", "room": "room", "gift": "gift", "tip": "tip", "item_gift": "item"}

_CLARIFY = {
    "invalid_proposal": "Bu teklif anlaşılmadı; tutarı ve kişiyi yeniden seçer misin?",
    "amount_required": "Ne kadar vermek istediğini yazar mısın?",
    "npc_unknown": "Kime vermek istediğini tam anlayamadım; kişiyi seçer misin?",
    "npc_not_here": "O kişi şu an burada değil.",
    "no_stock_or_service": "Bu şu an burada yok.",
    "combat_active": "Savaş sürerken alışveriş olmaz.",
    "shop_not_now": "Tezgâh şu an hizmet vermiyor.",
    "shop_unavailable": "Burada sana bunu verecek biri yok.",
    "purse_below_base": "Kesendeki para bunu karşılamıyor.",
    "client_price_mismatch": "Fiyat buradaki fiyatla uyuşmuyor; güncel fiyatı görüp yeniden seç.",
    "room_already_held": "Burada tuttuğun oda zaten duruyor.",
    "bribe_in_turn_only": "Rüşveti muhafıza sözle teklif et.",
    "purpose_not_offered_here": "Bu işlem buradan hazırlanmaz.",
    "item_not_owned": "Bu eşya şu an sende değil.",
}


@dataclass(frozen=True)
class EconomicState:
    world: dict[str, Any]
    character: dict[str, Any] | None


@dataclass(frozen=True)
class TextSpan:
    """Where in the player's line the proposal was read; traceability only, never authority."""
    start: int
    end: int


@dataclass(frozen=True)
class EconomicProposal:
    purpose: Purpose
    recipient_id: str
    source_id: str | None
    item_id: str | None
    count: int
    amount_cp: int | None
    tip_cp: int
    tender_cp: int | None
    dependency: Dependency
    source_action_id: str
    text_span: TextSpan | None


@dataclass(frozen=True)
class OfferLine:
    line_id: str
    kind: Literal["goods", "room", "gift", "tip", "item"]
    source_id: str | None
    item_id: str | None
    recipient_id: str
    count: int
    unit_cp: int
    total_cp: int
    optional: bool


@dataclass(frozen=True)
class CheckSpec:
    skill: Literal["Persuasion"]
    difficulty: Literal["easy", "medium", "hard"]


@dataclass(frozen=True)
class WorldEffect:
    kind: Literal["bribe_accepted"]
    npc_id: str


@dataclass(frozen=True)
class LineDecision:
    line_id: str
    status: Literal["accepted", "refused"]
    reason_code: str


@dataclass(frozen=True)
class AcceptanceRecord:
    record_id: str
    offer_id: str
    npc_id: str
    context_digest: str
    producer: Literal["engine"]
    check: CheckSpec | None
    line_decisions: list[LineDecision]


@dataclass(frozen=True)
class EconomicOffer:
    offer_id: str
    actor_id: str
    campaign_id: str
    place_id: str
    proposal: EconomicProposal
    lines: list[OfferLine]
    acceptance: AcceptanceRecord
    on_accept: list[WorldEffect]
    context_digest: str
    confirmation_digest: str
    status: Literal["prepared", "consumed", "cancelled"]
    operation_id: str | None
    prepared_turn: int
    consumed_action_id: str | None


@dataclass(frozen=True)
class PublicOfferLine:
    line_id: str
    label: str
    count: int
    unit_cp: int
    total_cp: int
    optional: bool


@dataclass(frozen=True)
class PublicEconomicOffer:
    """What the card shows: the label the player knows and the lines. No acceptance, check or refusal reason."""
    offer_id: str
    confirmation_digest: str
    counterparty_label: str
    lines: list[PublicOfferLine]
    dependency: Dependency
    max_total_cp: int
    tender_cp: int | None
    may_refuse: bool


@dataclass(frozen=True)
class PrepareResult:
    status: Literal["prepared", "refused", "clarification"]
    offer: EconomicOffer | None
    reason_code: str | None
    public_message: str


def new_offer_id() -> str:
    """Only the server makes an offer id, never from a counter that undo could bring back."""
    return secrets.token_hex(16)


def canonical_json(value: Any) -> str:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _settled(world: dict[str, Any]) -> dict[str, Any]:
    """A copy with "8 Altın" written in the pack counted into the purse; the live world is never normalised here."""
    import bold_acts
    candidate = copy.deepcopy(world)
    bold_acts.settle_coin_labels(candidate)
    return candidate


def _cp(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_CP


def _npcs_with_id(world: dict[str, Any], npc_id: Any) -> list[dict[str, Any]]:
    return [npc for npc in world.get("npcs", []) if isinstance(npc, dict) and npc.get("id") == npc_id]


def _npc(world: dict[str, Any], npc_id: Any) -> dict[str, Any] | None:
    found = _npcs_with_id(world, npc_id)
    return found[0] if len(found) == 1 else None


def _is_here(world: dict[str, Any], npc: dict[str, Any]) -> bool:
    import scheduled_events
    return (not npc.get("hidden") and npc.get("location") == world.get("location")
            and any(seen is npc for seen in scheduled_events.visible_npcs(world)))


def _combat(world: dict[str, Any]) -> bool:
    return bool((world.get("combat") or {}).get("active"))


def _held_deed(world: dict[str, Any], npc: dict[str, Any] | None) -> dict[str, Any] | None:
    """The arrest this NPC is making, when they are the guard holding the player now."""
    import world_reactions
    if npc is None:
        return None
    guard = world_reactions.arrester(world)
    if guard is None or guard.get("id") != npc.get("id"):
        return None
    return world_reactions.holding(world, npc)


def _is_bribe(world: dict[str, Any], proposal: EconomicProposal, npc: dict[str, Any] | None) -> bool:
    return proposal.purpose == "gift" and _held_deed(world, npc) is not None


def _room_right(world: dict[str, Any]) -> dict[str, Any] | None:
    """The room the player holds here and now, if any."""
    held = (world.get("flags") or {}).get("inn_room")
    now = (world.get("campaign_time") or {}).get("elapsed_seconds", 0)
    if isinstance(held, dict) and held.get("place") == world.get("location") and now < held.get("until", 0):
        return {"place": held.get("place"), "until": held.get("until")}
    return None


def _difficulty(amount: int) -> Literal["easy", "medium", "hard"]:
    """The same thresholds the spoken bribe uses: more coin is an easier word."""
    return "easy" if amount >= 1000 else "medium" if amount >= 100 else "hard"


def _clarify(reason: str) -> PrepareResult:
    return PrepareResult(status="clarification", offer=None, reason_code=reason, public_message=_CLARIFY[reason])


def _well_formed(proposal: EconomicProposal) -> str | None:
    if proposal.purpose not in _PURPOSES or proposal.dependency not in _DEPENDENCIES:
        return "invalid_proposal"
    if not isinstance(proposal.recipient_id, str) or not proposal.recipient_id:
        return "npc_unknown"
    if not (type(proposal.count) is int and 1 <= proposal.count <= MAX_COUNT):
        return "invalid_proposal"
    if not _cp(proposal.tip_cp) or proposal.tender_cp is not None and not _cp(proposal.tender_cp):
        return "invalid_proposal"
    if proposal.amount_cp is not None and not _cp(proposal.amount_cp):
        return "invalid_proposal"
    if proposal.purpose in ("gift", "tip"):
        if proposal.count != 1 or proposal.tip_cp:
            return "invalid_proposal"
        if not proposal.amount_cp:
            return "amount_required"
    if proposal.purpose == "room" and proposal.count != 1:
        return "invalid_proposal"  # one night; a count is not quietly turned into another meaning
    if proposal.purpose == "item_gift":
        # One existing instance from the player's own pack: no coin, tip, tender or count rides along.
        if (not isinstance(proposal.item_id, str) or not proposal.item_id or proposal.count != 1 or proposal.tip_cp
                or proposal.amount_cp or proposal.tender_cp is not None or proposal.source_id not in (None, "player")):
            return "invalid_proposal"
    return None


def _held_item(world: dict[str, Any], item_id: Any) -> dict[str, Any] | None:
    """The one instance with this id in the player's pack, if it is really there."""
    found = [item for item in world.get("inventory", []) if isinstance(item, dict) and item.get("item_id") == item_id]
    return found[0] if len(found) == 1 else None


def _item_name(world: dict[str, Any], item_id: Any) -> str | None:
    import equipment_economy
    return next((str(item.get("name")) for _, items in equipment_economy.containers(world) for item in items
                 if isinstance(item, dict) and item.get("item_id") == item_id), None)


def _lines(world: dict[str, Any], proposal: EconomicProposal, npc: dict[str, Any]) -> list[OfferLine] | str:
    """The priced lines from the server's own tables, or the reason there are none."""
    import bold_acts
    import shop_trade
    npc_id = str(npc["id"])
    kind = _KIND_OF[proposal.purpose]
    if proposal.purpose == "purchase":
        line = next((line for line in shop_trade.goods(world, npc) if line["key"] == proposal.item_id), None)
        if line is None or proposal.count > line["stock"]:
            return "no_stock_or_service"
        base = OfferLine(line_id="goods:0", kind="goods", source_id=npc_id, item_id=line["key"], recipient_id=npc_id,
                         count=proposal.count, unit_cp=line["unit_cp"], total_cp=line["unit_cp"] * proposal.count,
                         optional=False)
    elif proposal.purpose == "item_gift":
        item = _held_item(world, proposal.item_id)
        if item is None:
            return "item_not_owned"
        base = OfferLine(line_id="item:0", kind="item", source_id="player", item_id=str(item["item_id"]),
                         recipient_id=npc_id, count=1, unit_cp=0, total_cp=0, optional=False)
    elif proposal.purpose == "room":
        price = bold_acts._ROOM_PRICE
        base = OfferLine(line_id="room:0", kind="room", source_id=npc_id, item_id=None,
                         recipient_id=f"sink:lodging:{world.get('location')}", count=1, unit_cp=price,
                         total_cp=price, optional=False)
    else:
        base = OfferLine(line_id=f"{kind}:0", kind=kind, source_id=None, item_id=None, recipient_id=npc_id, count=1,
                         unit_cp=proposal.amount_cp, total_cp=proposal.amount_cp, optional=False)
    if proposal.purpose in ("purchase", "room") and proposal.amount_cp is not None \
            and proposal.amount_cp != base.total_cp:
        return "client_price_mismatch"  # the server's price stands; a different client price is asked about
    lines = [base]
    if proposal.tip_cp:
        lines.append(OfferLine(line_id="tip:1", kind="tip", source_id=None, item_id=None, recipient_id=npc_id,
                               count=1, unit_cp=proposal.tip_cp, total_cp=proposal.tip_cp,
                               optional=proposal.dependency == "base_required"))
    return lines


def context_digest(state: EconomicState, proposal: EconomicProposal, lines: list[OfferLine]) -> str:
    """What the offer depends on: the counterparty, the place, combat, the line prices and stock, the room right.

    Another NPC changing leaves it as it was. For a bribe the arrest itself is read instead of `refuses`.
    """
    import equipment_economy
    import shop_trade
    import world_reactions
    world = _settled(state.world)
    npc = _npc(world, proposal.recipient_id)
    person: dict[str, Any] | None = None
    if npc is not None:
        person = {"id": npc.get("id"), "location": npc.get("location"), "here": _is_here(world, npc),
                  "can_act": equipment_economy.npc_can_act(npc)}
        deed = _held_deed(world, npc) if proposal.purpose == "gift" else None
        if deed is not None:
            hold = deed.get("hold") or {}
            person["hold"] = {"at": deed.get("at"), "guard": hold.get("guard"), "arrest": hold.get("arrest")}
        else:
            person["refuses"] = world_reactions.refuses(world, npc)
    priced = []
    for line in lines:
        entry = {"line_id": line.line_id, "kind": line.kind, "item_id": line.item_id, "recipient_id": line.recipient_id,
                 "count": line.count, "unit_cp": line.unit_cp, "total_cp": line.total_cp}
        if line.kind == "goods" and npc is not None:
            entry["stock"] = next((good["stock"] for good in shop_trade.goods(world, npc)
                                   if good["key"] == line.item_id), None)
        if line.kind == "item":
            item = _held_item(world, line.item_id)
            hands = world.get("equipment") if isinstance(world.get("equipment"), dict) else {}
            grants = (npc or {}).get("item_consents")
            entry["item"] = {"in_pack": item is not None, "name": (item or {}).get("name"),
                             "held": line.item_id in hands.values(),
                             "consent": grants.get(line.item_id) if isinstance(grants, dict) else None}
        priced.append(entry)
    facts = {"npc": person, "place": world.get("location"), "combat_active": _combat(world), "lines": priced}
    if proposal.purpose == "room":
        facts["inn_room"] = _room_right(world)
    return _sha(facts)


def _proposal_canon(proposal: EconomicProposal) -> dict[str, Any]:
    canon = dataclasses.asdict(proposal)
    canon.pop("text_span", None)
    return canon


def confirmation_digest(offer: EconomicOffer) -> str:
    """sha256 of what the player confirms; the text span is traceability and is left out."""
    return _sha({"offer_id": offer.offer_id, "actor_id": offer.actor_id, "campaign_id": offer.campaign_id,
                 "place_id": offer.place_id, "proposal": _proposal_canon(offer.proposal),
                 "lines": [dataclasses.asdict(line) for line in offer.lines],
                 "dependency": offer.proposal.dependency, "tender_cp": offer.proposal.tender_cp,
                 "context_digest": offer.context_digest})


# ---------------------------------------------------------------------------------------------------------------
# A spoken decline, kept per NPC and per part (Dilim 1, design §3b, D3, D25, D26). The model may only stop a card:
# while a decline holds, no card of that part opens for that NPC and the open ones were cancelled when it was said.
# It ends only by an explicit take of that part (`clear_decline`) or by a new game day; turns never end it.
# ---------------------------------------------------------------------------------------------------------------

DECLINE_CAP = 32  # NPCs with a decline on record; earlier days go first, today's never silently
Part = str  # "tip", "gift", "room", "goods:<key>" or "*" (a decline whose part is unclear)
_DECLINES = "money_declined"
_DAY_SECONDS = 86400
_LABEL_MAX = 40
_PART_OF_PURPOSE = {"gift": "gift", "tip": "tip", "room": "room"}  # the card purposes a decline can stop
_MONEY_CARD_PURPOSES = ("purchase", "room", "gift", "tip")


@dataclass(frozen=True)
class DeclineWrite:
    status: Literal["written", "decline_cap_full"]
    cancelled: int


def game_day(world: Mapping[str, Any]) -> int:
    """The whole days on the campaign clock; a missing or bad clock is day 0."""
    clock = world.get("campaign_time") if isinstance(world, Mapping) else None
    seconds = clock.get("elapsed_seconds") if isinstance(clock, Mapping) else None
    return seconds // _DAY_SECONDS if type(seconds) is int and seconds >= 0 else 0


def _is_part(part: Any) -> bool:
    return part in ("tip", "gift", "room", "*") or (
        isinstance(part, str) and part.startswith("goods:") and len(part) > len("goods:"))


def _decline_rows(world: Mapping[str, Any]) -> Mapping[str, Any]:
    flags = world.get("flags") if isinstance(world, Mapping) else None
    records = flags.get(_DECLINES) if isinstance(flags, Mapping) else None
    return records if isinstance(records, Mapping) else {}


def _decline_row(row: Any) -> bool:
    return (isinstance(row, dict) and _cp(row.get("amount_cp")) and type(row.get("day")) is int and row["day"] >= 0
            and type(row.get("turn")) is int and row["turn"] >= 0)


def _on_day(row: Any, day: int) -> bool:
    return isinstance(row, Mapping) and type(row.get("day")) is int and row.get("day") == day


def _latest(entry: Mapping[str, Any]) -> tuple[int, int]:
    """(day, turn) of this NPC's newest decline row, for dropping the oldest NPC first."""
    stamps = [(row["day"], row["turn"]) for row in entry.values()
              if isinstance(row, Mapping) and type(row.get("day")) is int and type(row.get("turn")) is int]
    return max(stamps) if stamps else (-1, -1)


def _covered_by(offer: EconomicOffer, npc_id: str, part: Part, *, any_line: bool = False) -> bool:
    """Whether a decline of this part by this NPC closes the card. A bribe stays the guard's Persuasion check.

    A tip riding on another card is only that card's tip line (D26): the card stays open and its tip is refused at
    confirmation, unless the card goes only as a whole. `any_line` closes every card carrying the part, for a
    decline that could not be written and so cannot refuse the line later.
    """
    if offer.proposal.recipient_id != npc_id or offer.acceptance.check is not None:
        return False
    if part == "*":
        return offer.proposal.purpose in _MONEY_CARD_PURPOSES
    if _PART_OF_PURPOSE.get(offer.proposal.purpose) == part:
        return True
    return part == "tip" and any(line.kind == "tip" and (any_line or not line.optional) for line in offer.lines)


def _tip_declined(world: Mapping[str, Any], npc_id: str, lines: list[OfferLine]) -> bool:
    """Whether a tip line rides on this card and the NPC declined the tip today."""
    return any(line.kind == "tip" for line in lines) and declined(world, npc_id, "tip", day=game_day(world))


def record_decline(world: dict[str, Any], npc_id: str, part: Part, amount_cp: int, *, day: int,
                   turn: int) -> DeclineWrite:
    """Write the decline and cancel that NPC's open cards of that part (all money cards for `*`).

    The counter's own offer is not touched here (`bold_acts` owns it). When the record is full, rows of earlier days
    go first, oldest first; when all of them are today's, nothing is written, `decline_cap_full` is returned and
    logged, and every open card carrying the declined part is cancelled: a cancel never moves money.
    A written tip decline leaves a card that only carries an optional tip open; its tip is refused at confirmation.
    """
    if not (isinstance(npc_id, str) and npc_id and _is_part(part) and _cp(amount_cp) and type(day) is int
            and day >= 0 and type(turn) is int and turn >= 0):
        raise ValueError("invalid_decline")
    flags = world.setdefault("flags", {})
    if not isinstance(flags.get(_DECLINES), dict):
        flags[_DECLINES] = {}
    records = flags[_DECLINES]
    making_room: list[str] = []
    if npc_id not in records and len(records) >= DECLINE_CAP:
        ended = sorted((_latest(entry) if isinstance(entry, Mapping) else (-1, -1), key)
                       for key, entry in records.items()
                       if not isinstance(entry, Mapping) or _latest(entry)[0] < day)
        needed = len(records) - DECLINE_CAP + 1
        if len(ended) < needed:
            logger.warning("decline_cap_full: %d NPCs declined today; the decline of %s (%s) is not written",
                           len(records), npc_id, part)
            # Unwritten, the decline cannot refuse a tip line at confirmation: every card carrying it closes now.
            cancelled = len(cancel_prepared(world, actor_id="player",
                                            predicate=lambda offer: _covered_by(offer, npc_id, part, any_line=True)))
            return DeclineWrite(status="decline_cap_full", cancelled=cancelled)
        making_room = [key for _, key in ended[:needed]]
    cancelled = len(cancel_prepared(world, actor_id="player",
                                    predicate=lambda offer: _covered_by(offer, npc_id, part)))
    for key in making_room:
        records.pop(key)
        logger.info("money_declined: the ended decline of %s made room", key)
    entry = records.get(npc_id)
    if not isinstance(entry, dict):
        entry = records[npc_id] = {}
    for ended_part in [key for key, row in entry.items() if not _on_day(row, day)]:
        entry.pop(ended_part)  # this NPC's declines of an earlier day have already ended
    entry[part] = {"amount_cp": amount_cp, "day": day, "turn": turn}
    return DeclineWrite(status="written", cancelled=cancelled)


def clear_decline(world: dict[str, Any], npc_id: str, part: Part) -> None:
    """An explicit take of this part: its row goes, and an unclear decline lets this part through."""
    records = (world.get("flags") or {}).get(_DECLINES)
    entry = records.get(npc_id) if isinstance(records, dict) else None
    if not isinstance(entry, dict):
        return
    entry.pop(part, None)
    general = entry.get("*")
    if part != "*" and isinstance(general, dict):
        taken = general.get("taken") if isinstance(general.get("taken"), list) else []
        general["taken"] = taken if part in taken else [*taken, part]
    if not entry:
        records.pop(npc_id)


def declined(world: Mapping[str, Any], npc_id: str, part: Part, *, day: int) -> bool:
    """Whether this NPC declined this part today: its own row, or an unclear decline this part was not taken from."""
    entry = _decline_rows(world).get(npc_id)
    if not isinstance(entry, Mapping):
        return False
    if _on_day(entry.get(part), day):
        return True
    general = entry.get("*")
    if part == "*" or not _on_day(general, day):
        return False
    taken = general.get("taken")
    return not (isinstance(taken, list) and part in taken)


def repair_declines(world: dict[str, Any]) -> list[str]:
    """Drop the malformed decline rows and, above the cap, the oldest NPCs (earlier days first). Returns each name."""
    flags = world.get("flags")
    if not isinstance(flags, dict) or _DECLINES not in flags:
        return []
    records = flags[_DECLINES]
    dropped: list[str] = []
    if not isinstance(records, dict):
        flags[_DECLINES] = {}
        dropped.append(_DECLINES)
    else:
        for npc_id in list(records):
            path = f"{_DECLINES}.{npc_id}"
            entry = records[npc_id]
            if not (isinstance(npc_id, str) and npc_id and isinstance(entry, dict) and entry):
                records.pop(npc_id)
                dropped.append(path)
                continue
            for part in list(entry):
                row = entry[part]
                if not (_is_part(part) and _decline_row(row)):
                    entry.pop(part)
                    dropped.append(f"{path}.{part}")
                    continue
                for key in [key for key in row if key not in ("amount_cp", "day", "turn", "taken")]:
                    row.pop(key)
                    dropped.append(f"{path}.{part}.{key}")
                if "taken" in row:
                    taken = row["taken"]
                    if part != "*":
                        row.pop("taken")
                        dropped.append(f"{path}.{part}.taken")
                    elif not (isinstance(taken, list) and all(_is_part(item) and item != "*" for item in taken)):
                        row["taken"] = []  # an unreadable list blocks every part again: money stays, never moves
                        dropped.append(f"{path}.{part}.taken")
            if not entry:
                records.pop(npc_id)
        excess = len(records) - DECLINE_CAP
        if excess > 0:
            for npc_id in sorted(records, key=lambda key: (_latest(records[key]), key))[:excess]:
                records.pop(npc_id)
                dropped.append(f"{_DECLINES}.{npc_id}")
    for name in dropped:
        logger.warning("repair_declines dropped %s", name)
    return dropped


def repair_ledger_labels(world: dict[str, Any]) -> list[str]:
    """Drop a malformed `label` or `payee_id` from ledger operations; the operation itself always stays."""
    flags = world.get("flags")
    ledger = flags.get("economic_ledger") if isinstance(flags, dict) else None
    operations = ledger.get("operations") if isinstance(ledger, dict) else None
    if not isinstance(operations, dict):
        return []
    dropped: list[str] = []
    for operation_id, record in operations.items():
        if not isinstance(record, dict):
            continue
        label = record.get("label")
        if "label" in record and not (isinstance(label, str) and 0 < len(label) <= _LABEL_MAX):
            record.pop("label")
            dropped.append(f"economic_ledger.operations.{operation_id}.label")
        payee = record.get("payee_id")
        if "payee_id" in record and not (isinstance(payee, str) and payee):
            record.pop("payee_id")
            dropped.append(f"economic_ledger.operations.{operation_id}.payee_id")
    for name in dropped:
        logger.warning("repair_ledger_labels dropped %s", name)
    return dropped


def recent_payments(world: Mapping[str, Any], limit: int = 3, payee_id: str | None = None) -> list[dict[str, Any]]:
    """The player's latest payments that moved coin (net debit above 0), newest first; only to `payee_id` if given.

    An NPC's give and earned pay are coin the player received, not paid, and are left out.
    """
    flags = world.get("flags") if isinstance(world, Mapping) else None
    ledger = flags.get("economic_ledger") if isinstance(flags, Mapping) else None
    operations = ledger.get("operations") if isinstance(ledger, Mapping) else None
    if not isinstance(operations, Mapping) or type(limit) is not int or limit <= 0:
        return []
    found: list[dict[str, Any]] = []
    for record in reversed(list(operations.values())):
        if not isinstance(record, Mapping) or record.get("purpose") not in _OFFER_PURPOSES:
            continue
        amount = record.get("net_debit_cp")
        if type(amount) is not int or amount <= 0:
            continue
        label, payee, turn = record.get("label"), record.get("payee_id"), record.get("turn_index")
        payee = payee if isinstance(payee, str) and payee else None
        if payee_id is not None and payee != payee_id:
            continue
        found.append({"label": label if isinstance(label, str) and label else None, "amount_cp": amount,
                      "payee_id": payee, "turn_index": turn if type(turn) is int else None})
        if len(found) == limit:
            break
    return found


def _receipt_fields(lines: list[OfferLine], payee_id: Any) -> dict[str, str]:
    """The ledger's short words for an operation: the base line's label and who was paid."""
    base = next((line for line in lines if not line.optional), lines[0] if lines else None)
    fields: dict[str, str] = {}
    if base is not None:
        fields["label"] = _line_label(base)[:_LABEL_MAX]
    if isinstance(payee_id, str) and payee_id:
        fields["payee_id"] = payee_id
    return fields


def derive_acceptance(state: EconomicState, *, offer_id: str, proposal: EconomicProposal,
                      lines: list[OfferLine]) -> AcceptanceRecord | PrepareResult:
    """The engine's word on the offer, before anything is recorded. A refusal opens no card.

    A decline the NPC spoke today stops a gift, tip or room card of that part (the bribe path comes first). A
    declined tip riding on another card refuses only its tip line; a card that goes only as a whole does not open.
    """
    import living_world
    import world_reactions
    world = _settled(state.world)
    npc = _npc(world, proposal.recipient_id)
    if npc is None:
        return _clarify("npc_unknown")
    npc_id = str(npc["id"])
    check = None
    tip_off = False
    if _is_bribe(world, proposal, npc):
        # The guard holding the player usually can tie them to the deed, so `refuses` is not asked here:
        # whether the coin is taken is the Persuasion check at confirmation, as the spoken bribe does today.
        check = CheckSpec(skill="Persuasion", difficulty=_difficulty(lines[0].total_cp))
    else:
        part = _PART_OF_PURPOSE.get(proposal.purpose)
        tip_off = _tip_declined(world, npc_id, lines)
        if (part is not None and declined(world, npc_id, part, day=game_day(world))) \
                or (tip_off and any(line.kind == "tip" and not line.optional for line in lines)):
            who = living_world.turkish_initial_upper(living_world.public_npc_name(npc))
            return PrepareResult(status="refused", offer=None, reason_code="npc_declined",
                                 public_message=f"{who} az önce parayı geri çevirdi.")
        if world_reactions.refuses(world, npc):
            return PrepareResult(status="refused", offer=None, reason_code="npc_refuses",
                                 public_message=world_reactions.refusal_line(npc))
    reason = "check_required" if check is not None else "engine_accepts"
    decisions = [LineDecision(line_id=line.line_id, status="refused", reason_code="npc_declined")
                 if tip_off and line.kind == "tip" else
                 LineDecision(line_id=line.line_id, status="accepted", reason_code=reason) for line in lines]
    return AcceptanceRecord(record_id=f"acceptance:{offer_id}", offer_id=offer_id, npc_id=npc_id,
                            context_digest=context_digest(state, proposal, lines), producer="engine", check=check,
                            line_decisions=decisions)


def _line_label(line: OfferLine) -> str:
    import shop_trade
    if line.kind == "goods":
        label = next((label for key, label, _ in shop_trade.PRICES if key == line.item_id), str(line.item_id))
        return label[:1].upper() + label[1:]
    return {"room": "Oda (bir gece)", "gift": "Hediye", "tip": "Bahşiş"}.get(line.kind, "Eşya")


def _public_label(world: dict[str, Any], line: OfferLine) -> str:
    """The card's words for a line; an item line names the player's own item."""
    if line.kind == "item":
        return _item_name(world, line.item_id) or _line_label(line)
    return _line_label(line)


def public_offer(state: EconomicState, offer: EconomicOffer) -> PublicEconomicOffer:
    import living_world
    npc = _npc(state.world, offer.proposal.recipient_id)
    return PublicEconomicOffer(
        offer_id=offer.offer_id, confirmation_digest=offer.confirmation_digest,
        counterparty_label=living_world.public_npc_name(npc),
        lines=[PublicOfferLine(line_id=line.line_id, label=_public_label(state.world, line), count=line.count,
                               unit_cp=line.unit_cp,
                               total_cp=line.total_cp, optional=line.optional) for line in offer.lines],
        dependency=offer.proposal.dependency, max_total_cp=sum(line.total_cp for line in offer.lines),
        tender_cp=offer.proposal.tender_cp, may_refuse=offer.acceptance.check is not None)


def prepare_offer(state: EconomicState, proposal: EconomicProposal, *, offer_id: str, campaign_id: str,
                  actor_id: str, turn_index: int) -> PrepareResult:
    """Read the proposal against a settled copy and return a card, a refusal or a question. Writes nothing."""
    import equipment_economy
    import living_world
    import shop_trade
    problem = _well_formed(proposal)
    if problem:
        return _clarify(problem)
    world = _settled(state.world)
    if _combat(world):
        return _clarify("combat_active")
    npc = _npc(world, proposal.recipient_id)
    if npc is None:
        return _clarify("npc_unknown")
    if not _is_here(world, npc):
        return _clarify("npc_not_here")
    if proposal.purpose in ("purchase", "room"):
        counter = shop_trade.counter(world)
        vendor = counter.get("vendor") or {}
        if vendor.get("npc_id") != str(npc.get("id")) or counter["reason"] in ("no_vendor", "vendor_unavailable"):
            return _clarify("shop_unavailable")
        if counter["reason"] == "not_now":
            return _clarify("shop_not_now")
        if proposal.purpose == "room" and _room_right(world) is not None:
            return _clarify("room_already_held")
    elif not equipment_economy.npc_can_act(npc):
        return _clarify("npc_not_here")
    if proposal.purpose == "item_gift":
        # The same rules as the transfer itself, read before any card: armor never moves, and the NPC's written
        # consent for this item is needed (read here, consumed only when the confirmed card moves the item).
        item = _held_item(world, proposal.item_id)
        if item is None:
            return _clarify("item_not_owned")
        if equipment_economy.is_armor_or_shield(item):
            return PrepareResult(status="refused", offer=None, reason_code="armor_owner_required",
                                 public_message="Zırh ve kalkan bu yoldan el değiştirmez.")
        if not equipment_economy.has_consent(npc, item, "give", str(npc["id"])):
            return PrepareResult(status="refused", offer=None, reason_code="npc_consent_required",
                                 public_message="Bunu almayı kabul ettiğine dair bir söz yok.")
    lines = _lines(world, proposal, npc)
    if isinstance(lines, str):
        return _clarify(lines)
    acceptance = derive_acceptance(state, offer_id=offer_id, proposal=proposal, lines=lines)
    if isinstance(acceptance, PrepareResult):
        return acceptance
    base = sum(line.total_cp for line in lines if not line.optional)
    purse = (world.get("currency") or {}).get("player", 0)
    if type(purse) is not int or purse < base:
        return _clarify("purse_below_base")
    on_accept = [WorldEffect(kind="bribe_accepted", npc_id=str(npc["id"]))] if acceptance.check is not None else []
    offer = EconomicOffer(offer_id=offer_id, actor_id=actor_id, campaign_id=campaign_id,
                          place_id=str(world.get("location")), proposal=proposal, lines=lines, acceptance=acceptance,
                          on_accept=on_accept, context_digest=acceptance.context_digest, confirmation_digest="",
                          status="prepared", operation_id=None, prepared_turn=turn_index, consumed_action_id=None)
    offer = dataclasses.replace(offer, confirmation_digest=confirmation_digest(offer))
    who = living_world.turkish_initial_upper(living_world.public_npc_name(npc))
    total = sum(line.total_cp for line in lines)
    if proposal.purpose == "item_gift":
        return PrepareResult(status="prepared", offer=offer, reason_code=None,
                             public_message=f"{who} için eşya teklifi hazır: {_item_name(world, proposal.item_id)}. "
                                            "Onaylarsan verilir.")
    return PrepareResult(status="prepared", offer=offer, reason_code=None,
                         public_message=f"{who} için teklif hazır: en çok {total} bakır. Onaylarsan işlem yapılır.")


# ---------------------------------------------------------------------------------------------------------------
# A2: resolution, the one applier and the money receipt.
# ---------------------------------------------------------------------------------------------------------------

LEDGER_OPERATIONS_CAP = 200  # money operations (every purpose but item_transfer)
LEDGER_ITEM_OPERATIONS_CAP = 200  # item_transfer operations, counted apart so they never push money out
LEDGER_ENTITLEMENTS_CAP = 400
UNDO_WINDOW_TURNS = 1  # the one turn undo can take back; an entitlement paid in it is never forgotten


def trim_operations(operations: dict[str, Any]) -> None:
    """Oldest first, each kind under its own cap: item moves and money operations never evict each other."""
    for items, cap in ((True, LEDGER_ITEM_OPERATIONS_CAP), (False, LEDGER_OPERATIONS_CAP)):
        keys = [key for key, record in operations.items()
                if (isinstance(record, dict) and record.get("purpose") == "item_transfer") is items]
        for key in keys[:max(0, len(keys) - cap)]:
            operations.pop(key)


def _trim_entitlements(ledger: dict[str, Any], turn: int) -> None:
    """Keep the newest LEDGER_ENTITLEMENTS_CAP paid events; one paid within the undo window always stays."""
    entitlements = ledger.get("entitlements")
    if not isinstance(entitlements, dict):
        return
    operations = ledger.get("operations") if isinstance(ledger.get("operations"), dict) else {}
    excess = len(entitlements) - LEDGER_ENTITLEMENTS_CAP
    for event_id, operation_id in list(entitlements.items()):
        if excess <= 0:
            break
        record = operations.get(operation_id)
        paid_turn = record.get("turn_index") if isinstance(record, dict) else None
        if type(paid_turn) is int and paid_turn >= turn - UNDO_WINDOW_TURNS:
            continue
        del entitlements[event_id]
        excess -= 1
_OFFER_PURPOSES = ("purchase", "room", "gift", "tip", "item_gift")
_ENGINE_PURPOSES = ("npc_gift", "entitlement")
_POOL_PREFIX = "thread-pool:"

_REFUSED_SUMMARY = {
    "no_money": "Kesendeki para yetmedi; hiçbir şey ödenmedi.",
    "tender_invalid": "Uzattığın para bu işe uymadı; hiçbir şey ödenmedi.",
    "check_failed": "Teklif kabul görmedi; para kesende kaldı.",
    "check_required": "Teklif henüz denenmedi; para kesende kaldı.",
    "stale": "Durum değişti; teklifin yenilenmesi gerekiyor. Hiçbir şey ödenmedi.",
}


class EconomicReceiptError(Exception):
    """A resolution that does not match its offer or the real before/after state; nothing was written."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AssetDelta:
    owner_id: str
    asset_kind: Literal["currency", "item", "stock", "sink"]
    asset_id: str
    before: int
    after: int


@dataclass(frozen=True)
class ServiceRight:
    """The projection of `flags.inn_room`; no second record is kept."""
    kind: Literal["room"]
    place_id: str
    holder_id: str
    valid_until: int


@dataclass(frozen=True)
class LineRefusal:
    line_id: str
    reason_code: str


@dataclass(frozen=True)
class EconomicResolution:
    operation_id: str
    offer_id: str | None
    purpose: Literal["purchase", "room", "gift", "tip", "item_gift", "npc_gift", "entitlement"]
    base_fingerprint: str
    status: Literal["applied", "refused"]
    reason_code: str | None
    lines: list[OfferLine]
    asset_deltas: list[AssetDelta]
    service_rights: list[ServiceRight]
    world_effects: list[WorldEffect]
    refusals: list[LineRefusal]
    public_summary: str
    tender_cp: int | None
    change_cp: int
    net_debit_cp: int
    replayed: bool = False  # only a repeated entitlement event; never public


@dataclass(frozen=True)
class EconomicFacts:
    balances: dict[str, int]
    stock: dict[str, int]
    items: dict[str, dict[str, int]]
    services: list[ServiceRight]
    sink_totals: dict[str, int]
    item_index: dict[str, list[str]] = dataclasses.field(default_factory=dict)  # item id -> [owner, name]


@dataclass(frozen=True)
class PublicLineRefusal:
    line_id: str
    reason_code: str


@dataclass(frozen=True)
class PublicEconomicResolution:
    """The player's receipt: no NPC purse, acceptance record or check difficulty."""
    operation_id: str
    offer_id: str | None
    status: Literal["applied", "refused"]
    reason_code: str | None
    lines: list[PublicOfferLine]
    refusals: list[PublicLineRefusal]
    tender_cp: int | None
    change_cp: int
    net_debit_cp: int
    public_summary: str


def _ledger(world: dict[str, Any]) -> dict[str, Any]:
    ledger = (world.get("flags") or {}).get("economic_ledger")
    return ledger if isinstance(ledger, dict) else {}


def _room_services(world: dict[str, Any]) -> list[ServiceRight]:
    held = (world.get("flags") or {}).get("inn_room")
    if not isinstance(held, dict):
        return []
    return [ServiceRight(kind="room", place_id=str(held.get("place")), holder_id="player",
                         valid_until=held.get("until", 0))]


def economic_facts(state: EconomicState) -> EconomicFacts:
    """What money, goods, stock and service rights the world holds, read as it is (the caller settles labels)."""
    import equipment_economy
    import shop_trade
    world = state.world
    balances = {str(owner): amount for owner, amount in (world.get("currency") or {}).items() if type(amount) is int}
    stock: dict[str, int] = {}
    for npc in world.get("npcs", []):
        if isinstance(npc, dict):
            for good in shop_trade.goods(world, npc):
                stock[f"{npc.get('id')}:{good['key']}"] = good["stock"]
    items: dict[str, dict[str, int]] = {}
    index: dict[str, list[str]] = {}
    for owner, listed in equipment_economy.containers(world):
        counts = items.setdefault(str(owner), {})
        for item in listed if isinstance(listed, list) else []:
            name = str(item.get("name") if isinstance(item, dict) else item)
            counts[name] = counts.get(name, 0) + 1
            if isinstance(item, dict) and isinstance(item.get("item_id"), str):
                index[item["item_id"]] = [str(owner), name]
    sinks = _ledger(world).get("sink_totals") or {}
    return EconomicFacts(balances=balances, stock=stock, items=items, services=_room_services(world),
                         sink_totals={str(key): value for key, value in sinks.items() if type(value) is int},
                         item_index=index)


def _fingerprint(settled_world: dict[str, Any]) -> str:
    return _sha(economic_facts(EconomicState(world=settled_world, character=None)))


def _payer(purpose: str, lines: list[OfferLine]) -> str | None:
    """The player pays every offer; an engine payment names its payer as the line's source."""
    if purpose in _OFFER_PURPOSES:
        return "player"
    return lines[0].source_id if lines else None


def _summary(status: str, reason: str | None, net: int, change: int, refusals: list[LineRefusal],
             item_name: str | None = None) -> str:
    if status != "applied":
        return _REFUSED_SUMMARY.get(str(reason), "İşlem gerçekleşmedi; hiçbir şey ödenmedi.")
    if item_name is not None:
        return f"{item_name} verildi."
    text = f"{net} bakır ödendi."
    if change:
        text += f" Para üstü {change} bakır."
    if refusals:
        text += " Bahşiş geçmedi; kesende kaldı."
    return text


def _refused(resolution: EconomicResolution, reason: str) -> EconomicResolution:
    """The same resolution with nothing moved, decided on the copy before the live world is touched."""
    return dataclasses.replace(
        resolution, status="refused", reason_code=reason, asset_deltas=[], service_rights=[], world_effects=[],
        refusals=[LineRefusal(line_id=line.line_id, reason_code=reason) for line in resolution.lines],
        change_cp=0, net_debit_cp=0, public_summary=_summary("refused", reason, 0, 0, []))


def resolve_offer(state: EconomicState, offer: EconomicOffer, *, operation_id: str,
                  check: Callable[[str, int], str] | None = None) -> EconomicResolution:
    """The candidate result of a confirmed offer on a settled copy. Reads only; the acceptance is the offer's own.

    `check(skill, dc)` rolls the offer's check and returns "BAŞARILI" or another result.
    """
    import bold_acts
    world = _settled(state.world)
    facts = economic_facts(EconomicState(world=world, character=None))
    proposal = offer.proposal
    lines = list(offer.lines)
    tender = proposal.tender_cp
    blank = EconomicResolution(
        operation_id=operation_id, offer_id=offer.offer_id, purpose=proposal.purpose, base_fingerprint=_sha(facts),
        status="refused", reason_code=None, lines=lines, asset_deltas=[], service_rights=[], world_effects=[],
        refusals=[], public_summary="", tender_cp=tender, change_cp=0, net_debit_cp=0)
    spec = offer.acceptance.check
    if spec is not None:
        if check is None:
            return _refused(blank, "check_required")
        import game
        if check(spec.skill, game.DIFFICULTY_DC[spec.difficulty]) != "BAŞARILI":
            return _refused(blank, "check_failed")
    purse = facts.balances.get("player", 0)
    if tender is not None and tender > purse:
        return _refused(blank, "tender_invalid")
    decisions = {decision.line_id: decision for decision in offer.acceptance.line_decisions}
    if spec is None and _tip_declined(world, proposal.recipient_id, lines):
        # A tip the NPC declined after the card opened is refused here; the rest of the card is left as it was.
        decisions.update({line.line_id: LineDecision(line_id=line.line_id, status="refused",
                                                     reason_code="npc_declined")
                          for line in lines if line.kind == "tip"})
    refusals: list[LineRefusal] = []
    accepted: list[OfferLine] = []
    for line in lines:
        decision = decisions.get(line.line_id)
        if decision is not None and decision.status == "accepted":
            accepted.append(line)
            continue
        reason = decision.reason_code if decision is not None else "no_decision"
        if not line.optional or proposal.dependency == "all_or_none":
            return _refused(blank, reason)  # the base, or anything in all-or-none, takes the whole offer down
        refusals.append(LineRefusal(line_id=line.line_id, reason_code=reason))
    if proposal.dependency == "all_or_none":
        total = sum(line.total_cp for line in accepted)
        if purse < total:
            return _refused(blank, "no_money")
        if tender is not None and tender < total:
            return _refused(blank, "tender_invalid")
    else:
        running = sum(line.total_cp for line in accepted if not line.optional)
        if purse < running:
            return _refused(blank, "no_money")
        if tender is not None and tender < running:
            return _refused(blank, "tender_invalid")
        kept = {line.line_id for line in accepted if not line.optional}
        for line in accepted:
            if not line.optional:
                continue
            if running + line.total_cp > purse:
                refusals.append(LineRefusal(line_id=line.line_id, reason_code="no_money"))
            elif tender is not None and running + line.total_cp > tender:
                refusals.append(LineRefusal(line_id=line.line_id, reason_code="tender_short"))
            else:
                kept.add(line.line_id)
                running += line.total_cp
        accepted = [line for line in accepted if line.line_id in kept]
        order = [line.line_id for line in lines]
        refusals.sort(key=lambda refusal: order.index(refusal.line_id))
    net = sum(line.total_cp for line in accepted)
    deltas = [AssetDelta(owner_id="player", asset_kind="currency", asset_id="cp", before=purse, after=purse - net)]
    credits: dict[str, int] = {}
    sinks: dict[str, int] = {}
    for line in accepted:
        bucket = sinks if line.recipient_id.startswith("sink:") else credits
        bucket[line.recipient_id] = bucket.get(line.recipient_id, 0) + line.total_cp
    for owner, amount in credits.items():
        held = facts.balances.get(owner, 0)
        deltas.append(AssetDelta(owner_id=owner, asset_kind="currency", asset_id="cp", before=held, after=held + amount))
    for sink_id, amount in sinks.items():
        held = facts.sink_totals.get(sink_id, 0)
        deltas.append(AssetDelta(owner_id=sink_id, asset_kind="sink", asset_id=sink_id, before=held,
                                 after=held + amount))
    item_name = None
    for line in accepted:
        if line.kind == "item":
            # The very instance the card names, still in the player's pack; it goes to the recipient, one of it.
            entry = facts.item_index.get(str(line.item_id))
            if entry is None or entry[0] != line.source_id:
                return _refused(blank, "item_not_owned")
            item_name = entry[1]
            for owner, step in ((str(line.source_id), -line.count), (line.recipient_id, line.count)):
                held = facts.items.get(owner, {}).get(item_name, 0)
                deltas.append(AssetDelta(owner_id=owner, asset_kind="item", asset_id=item_name, before=held,
                                         after=held + step))
        if line.kind == "goods":
            label = _line_label(line)
            held = facts.items.get("player", {}).get(label, 0)
            deltas.append(AssetDelta(owner_id="player", asset_kind="item", asset_id=label, before=held,
                                     after=held + line.count))
            left = facts.stock.get(f"{line.source_id}:{line.item_id}", 0)
            deltas.append(AssetDelta(owner_id=str(line.source_id), asset_kind="stock", asset_id=str(line.item_id),
                                     before=left, after=left - line.count))
    now = (world.get("campaign_time") or {}).get("elapsed_seconds", 0)
    rights = [ServiceRight(kind="room", place_id=offer.place_id, holder_id="player",
                           valid_until=now + bold_acts._ROOM_DAY) for line in accepted if line.kind == "room"]
    change = tender - net if tender is not None else 0
    return dataclasses.replace(
        blank, status="applied", asset_deltas=[delta for delta in deltas if delta.before != delta.after],
        service_rights=rights, world_effects=list(offer.on_accept), refusals=refusals, change_cp=change,
        net_debit_cp=net, public_summary=_summary("applied", None, net, change, refusals, item_name))


def apply_resolution(state: EconomicState, resolution: EconomicResolution, *,
                     confirmed_offer: EconomicOffer | None) -> EconomicResolution:
    """The one writer of a confirmed economic effect: a settled copy first, the receipt, then the live dicts in place.

    The copy and the live world go through the very same steps in the same order (label settling, the same `pay`
    calls, the room right, the world effect, the ledger); any failure ends on the copy and the live world stays as
    it was. Writing in place keeps the caller's thread, npc and deed references live. A purchase writes only its
    coin here; its goods and stock are the counter's own and are checked by the counter with the same receipt.
    """
    import bold_acts
    import equipment_economy
    import equipment_native
    import item_transfers
    import world_reactions
    world = state.world
    if resolution.operation_id in (_ledger(world).get("operations") or {}):
        raise EconomicReceiptError("operation_id_reused")
    if resolution.status != "applied":
        return resolution
    payer = _payer(resolution.purpose, resolution.lines)
    if not isinstance(payer, str) or not payer:
        raise EconomicReceiptError("payer_unknown")
    pooled = resolution.purpose == "entitlement" and payer.startswith(_POOL_PREFIX)
    money = [delta for delta in resolution.asset_deltas if delta.asset_kind in ("currency", "sink")]
    # An item gift moves its item here too, by the one sourced transfer; a purchase's goods stay the counter's own.
    item_lines = [line for line in resolution.lines if line.kind == "item"] if resolution.purpose == "item_gift" else []
    claimed_items = [delta for delta in resolution.asset_deltas if delta.asset_kind == "item"] if item_lines else []
    written = dataclasses.replace(resolution, asset_deltas=money)
    candidate = copy.deepcopy(world)
    before: EconomicFacts | None = None
    for target in (candidate, world):
        live = target is world
        try:
            bold_acts.settle_coin_labels(target)
            if not live:
                if _fingerprint(target) != resolution.base_fingerprint:
                    return _refused(resolution, "stale")
                before = economic_facts(EconomicState(world=target, character=None))
            wallets = target.setdefault("currency", {})
            flags = target.setdefault("flags", {})
            ledger = flags.setdefault("economic_ledger", {})
            sink_totals = ledger.setdefault("sink_totals", {})
            for delta in money:
                amount = delta.after - delta.before
                if delta.owner_id == payer:
                    continue  # the payer's debit is the sum of the credits below; the receipt checks it
                if delta.asset_kind == "sink":
                    if amount < 0:
                        raise EconomicReceiptError("sink_delta_negative")
                    if wallets.get(payer, 0) - equipment_native.reserved_funds(target, payer) < amount:
                        equipment_economy.fail("insufficient_funds")
                    wallets[payer] = wallets.get(payer, 0) - amount  # a sink: nobody is paid, the total is kept
                    sink_totals[delta.owner_id] = sink_totals.get(delta.owner_id, 0) + amount
                    continue
                if pooled:
                    wallets[payer] = wallets.get(payer, 0) + amount  # the day's pool, open only for this payment
                try:
                    equipment_economy.pay(target, payer, delta.owner_id, amount)
                finally:
                    if pooled:
                        wallets.pop(payer, None)
            for effect in resolution.world_effects:
                deed = world_reactions.holding(target, _npc(target, effect.npc_id))
                if effect.kind != "bribe_accepted" or deed is None:
                    raise EconomicReceiptError("world_effect_unavailable")
                deed.pop("hold")
            for right in resolution.service_rights:
                flags["inn_room"] = {"place": right.place_id, "until": right.valid_until}
            if resolution.status == "applied" and item_lines:
                moved_items: list[AssetDelta] = []
                for index, line in enumerate(item_lines):
                    npc = _npc(target, line.recipient_id)
                    item = _held_item(target, line.item_id)
                    if npc is None:
                        raise EconomicReceiptError("item_recipient_unknown")
                    if item is None:
                        equipment_economy.fail("item_not_owned")
                    equipment_economy.consent(npc, item, "give", line.recipient_id)  # consumed once, here
                    moved = item_transfers.transfer_existing_item(
                        EconomicState(world=target, character=None), item_id=str(line.item_id),
                        source_id=str(line.source_id), recipient_id=line.recipient_id, count=line.count,
                        operation_id=f"{resolution.operation_id}:item:{index}")
                    if moved.status != "applied":
                        equipment_economy.fail(moved.reason_code or "item_transfer_refused")
                    moved_items.extend(moved.asset_deltas)
                if not live:
                    if sorted(map(canonical_json, moved_items)) != sorted(map(canonical_json, claimed_items)):
                        raise EconomicReceiptError("item_delta_mismatch")
                    written = dataclasses.replace(resolution, asset_deltas=money + moved_items)
            operations = ledger.setdefault("operations", {})
            payee = (confirmed_offer.proposal.recipient_id if confirmed_offer is not None
                     else resolution.lines[0].recipient_id if resolution.lines else None)
            operations[resolution.operation_id] = {
                "offer_id": resolution.offer_id, "purpose": resolution.purpose,
                "net_debit_cp": resolution.net_debit_cp, "turn_index": flags.get("turn_index", 0),
                **_receipt_fields(resolution.lines, payee)}
            if resolution.purpose == "entitlement":
                event_id = resolution.operation_id.removeprefix("entitlement:")
                ledger.setdefault("entitlements", {})[event_id] = resolution.operation_id
                _trim_entitlements(ledger, flags.get("turn_index", 0))
            trim_operations(operations)
            if not live:
                equipment_economy.validate_world(target)
                validate_economic_resolution(before, economic_facts(EconomicState(world=target, character=None)),
                                             written, confirmed_offer=confirmed_offer)
        except equipment_economy.EquipmentError as error:
            if live:
                raise
            if str(error) == "insufficient_funds":
                return _refused(resolution, "no_money")
            raise EconomicReceiptError(str(error)) from error
    return resolution


def settle_entitlement(state: EconomicState, *, event_id: str, payer_id: str, recipient_id: str,
                       amount_cp: int) -> EconomicResolution:
    """Earned pay, once per event: the engine calls it, no model can. A repeated event pays nothing."""
    if not (isinstance(event_id, str) and event_id and isinstance(payer_id, str) and payer_id
            and isinstance(recipient_id, str) and recipient_id and type(amount_cp) is int
            and 0 < amount_cp <= MAX_CP):
        raise EconomicReceiptError("invalid_entitlement")
    line = OfferLine(line_id="entitlement:0", kind="gift", source_id=payer_id, item_id=None, recipient_id=recipient_id,
                     count=1, unit_cp=amount_cp, total_cp=amount_cp, optional=False)
    world = _settled(state.world)
    known = (_ledger(world).get("entitlements") or {}).get(event_id)
    if known is not None:
        return EconomicResolution(
            operation_id=known, offer_id=None, purpose="entitlement", base_fingerprint=_fingerprint(world),
            status="applied", reason_code=None, lines=[line], asset_deltas=[], service_rights=[], world_effects=[],
            refusals=[], public_summary="Bu iş günü zaten ödendi.", tender_cp=None, change_cp=0, net_debit_cp=0,
            replayed=True)
    facts = economic_facts(EconomicState(world=world, character=None))
    held = facts.balances.get(recipient_id, 0)
    deltas = [AssetDelta(owner_id=recipient_id, asset_kind="currency", asset_id="cp", before=held,
                         after=held + amount_cp)]
    if not payer_id.startswith(_POOL_PREFIX):
        source = facts.balances.get(payer_id, 0)
        deltas.append(AssetDelta(owner_id=payer_id, asset_kind="currency", asset_id="cp", before=source,
                                 after=source - amount_cp))
    resolution = EconomicResolution(
        operation_id=f"entitlement:{event_id}", offer_id=None, purpose="entitlement", base_fingerprint=_sha(facts),
        status="applied", reason_code=None, lines=[line], asset_deltas=deltas, service_rights=[], world_effects=[],
        refusals=[], public_summary=f"{amount_cp} bakır hak edildi ve ödendi.", tender_cp=None, change_cp=0,
        net_debit_cp=amount_cp, replayed=False)
    return apply_resolution(state, resolution, confirmed_offer=None)


def _reject(reason: str) -> None:
    raise EconomicReceiptError(reason)


def _changes(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after.get(key, 0) - before.get(key, 0) for key in {*before, *after}
            if after.get(key, 0) != before.get(key, 0)}


def _item_changes(before: dict[str, dict[str, int]], after: dict[str, dict[str, int]]) -> dict[tuple[str, str], int]:
    found = {}
    for owner in {*before, *after}:
        for name, moved in _changes(before.get(owner, {}), after.get(owner, {})).items():
            found[(owner, name)] = moved
    return found


def validate_economic_resolution(before: EconomicFacts, after: EconomicFacts, resolution: EconomicResolution, *,
                                 confirmed_offer: EconomicOffer | None) -> None:
    """The receipt: price, tender, change, recipient, goods, stock and room right against the offer and the state.

    A narration and a purse that agree on a wrong number still fail here: what should have moved is recomputed
    from the confirmed offer (or, for an engine payment, from its own lines), and what did move is read from the
    real before/after projection. Goods and stock are checked whenever the receipt claims them, and any goods or
    stock change it does not claim fails. Raises EconomicReceiptError on any mismatch.
    """
    lines = list(resolution.lines)
    for line in lines:
        if not (type(line.count) is int and line.count >= 1 and _cp(line.unit_cp) and _cp(line.total_cp)
                and line.unit_cp * line.count == line.total_cp):
            _reject("line_price")
    dependency = "base_required"
    if confirmed_offer is not None:
        if resolution.offer_id != confirmed_offer.offer_id or resolution.purpose != confirmed_offer.proposal.purpose:
            _reject("offer_mismatch")
        if lines != list(confirmed_offer.lines):
            _reject("line_mismatch")
        if resolution.tender_cp != confirmed_offer.proposal.tender_cp:
            _reject("tender_mismatch")
        dependency = confirmed_offer.proposal.dependency
    elif resolution.purpose not in _ENGINE_PURPOSES or resolution.tender_cp is not None:
        _reject("offer_required")
    line_ids = [line.line_id for line in lines]
    refused_ids = [refusal.line_id for refusal in resolution.refusals]
    if len(set(line_ids)) != len(line_ids) or not set(refused_ids) <= set(line_ids) \
            or len(set(refused_ids)) != len(refused_ids):
        _reject("refusal_mismatch")
    accepted: list[OfferLine] = []
    if resolution.status == "applied":
        accepted = [line for line in lines if line.line_id not in refused_ids]
        if not accepted or any(not line.optional for line in lines if line.line_id in refused_ids) \
                or dependency == "all_or_none" and refused_ids:
            _reject("dependency_broken")
        if confirmed_offer is not None:
            decided = {decision.line_id: decision.status for decision in confirmed_offer.acceptance.line_decisions}
            if any(decided.get(line.line_id) != "accepted" for line in accepted):
                _reject("acceptance_mismatch")
    elif resolution.status != "refused":
        _reject("status_unknown")
    net = sum(line.total_cp for line in accepted)
    if resolution.net_debit_cp != net:
        _reject("net_mismatch")
    tender = resolution.tender_cp
    change = 0
    if accepted and tender is not None:
        if not (net <= tender <= before.balances.get("player", 0)):
            _reject("tender_mismatch")
        change = tender - net
    if resolution.change_cp != change:
        _reject("change_mismatch")
    payer = _payer(resolution.purpose, lines)
    pooled = resolution.purpose == "entitlement" and isinstance(payer, str) and payer.startswith(_POOL_PREFIX)
    want_coin: dict[str, int] = {}
    want_sink: dict[str, int] = {}
    for line in accepted:
        if line.recipient_id == payer:
            _reject("payer_is_recipient")
        bucket = want_sink if line.recipient_id.startswith("sink:") else want_coin
        bucket[line.recipient_id] = bucket.get(line.recipient_id, 0) + line.total_cp
        if not pooled:
            want_coin[str(payer)] = want_coin.get(str(payer), 0) - line.total_cp
    want_coin = {owner: moved for owner, moved in want_coin.items() if moved}
    moved_coin = _changes(before.balances, after.balances)
    moved_sink = _changes(before.sink_totals, after.sink_totals)
    if moved_coin != want_coin:
        _reject("currency_mismatch")
    if moved_sink != want_sink:
        _reject("sink_mismatch")
    claimed: dict[tuple[str, str, str], int] = {}
    for delta in resolution.asset_deltas:
        if delta.asset_kind == "currency":
            seen = (before.balances.get(delta.owner_id, 0), after.balances.get(delta.owner_id, 0))
        elif delta.asset_kind == "sink":
            seen = (before.sink_totals.get(delta.owner_id, 0), after.sink_totals.get(delta.owner_id, 0))
        elif delta.asset_kind == "item":
            seen = (before.items.get(delta.owner_id, {}).get(delta.asset_id, 0),
                    after.items.get(delta.owner_id, {}).get(delta.asset_id, 0))
        elif delta.asset_kind == "stock":
            key = f"{delta.owner_id}:{delta.asset_id}"
            seen = (before.stock.get(key, 0), after.stock.get(key, 0))
        else:
            _reject("delta_kind")
        identity = (delta.asset_kind, delta.owner_id, delta.asset_id)
        if identity in claimed or (delta.before, delta.after) != seen:
            _reject("delta_mismatch")
        claimed[identity] = delta.after - delta.before
    if {owner for kind, owner, _ in claimed if kind == "currency"} != set(moved_coin) \
            or {owner for kind, owner, _ in claimed if kind == "sink"} != set(moved_sink):
        _reject("delta_unclaimed")
    claimed_items = {(owner, asset): moved for (kind, owner, asset), moved in claimed.items() if kind == "item"}
    claimed_stock = {f"{owner}:{asset}": moved for (kind, owner, asset), moved in claimed.items() if kind == "stock"}
    if _item_changes(before.items, after.items) != claimed_items or _changes(before.stock, after.stock) != claimed_stock:
        _reject("goods_mismatch")
    if claimed_items or claimed_stock or any(line.kind == "item" for line in accepted):
        want_items: dict[tuple[str, str], int] = {}
        want_stock: dict[str, int] = {}
        for line in accepted:
            if line.kind == "item":
                # The named instance itself left its source for the recipient: not just any item of its name.
                was, now = before.item_index.get(str(line.item_id)), after.item_index.get(str(line.item_id))
                if was is None or now is None or was != [str(line.source_id), was[1]] \
                        or now != [line.recipient_id, was[1]]:
                    _reject("item_mismatch")
                for owner, step in ((str(line.source_id), -line.count), (line.recipient_id, line.count)):
                    want_items[(owner, was[1])] = want_items.get((owner, was[1]), 0) + step
            if line.kind == "goods":
                label = _line_label(line)
                want_items[("player", label)] = want_items.get(("player", label), 0) + line.count
                key = f"{line.source_id}:{line.item_id}"
                want_stock[key] = want_stock.get(key, 0) - line.count
        if claimed_items != want_items or claimed_stock != want_stock:
            _reject("goods_mismatch")
    rooms = [line for line in accepted if line.kind == "room"]
    rights = list(resolution.service_rights)
    if rooms:
        place = confirmed_offer.place_id if confirmed_offer is not None else None
        if len(rooms) != 1 or len(rights) != 1 or rights[0].kind != "room" or rights[0].holder_id != "player" \
                or rights[0].place_id != place or type(rights[0].valid_until) is not int or after.services != rights:
            _reject("service_mismatch")
    elif rights or after.services != before.services:
        _reject("service_mismatch")
    expected_effects = list(confirmed_offer.on_accept) if confirmed_offer is not None and accepted else []
    if list(resolution.world_effects) != expected_effects:
        _reject("effect_mismatch")


# ---------------------------------------------------------------------------------------------------------------
# A3: the stored card, its confirmation, cancellation, undo and pruning.
# ---------------------------------------------------------------------------------------------------------------

OFFER_RECORDS_KEEP = 20
_PANEL_PURPOSES = ("gift", "tip", "room")  # a purchase is the counter's own; a valued item comes with /item give
_digest_of = confirmation_digest


def wallet_total_cp(world: dict[str, Any]) -> int:
    """The player's purse with written coin labels counted, from a copy: the live world is not normalised."""
    import bold_acts
    candidate = {"currency": copy.deepcopy(world.get("currency") or {}),
                 "inventory": copy.deepcopy(world.get("inventory") or [])}
    bold_acts.settle_coin_labels(candidate)
    total = candidate["currency"].get("player", 0)
    return total if type(total) is int else 0


def offer_records(world: dict[str, Any]) -> dict[str, Any]:
    """The stored cards, read only: an empty dict when there are none."""
    records = (world.get("flags") or {}).get("economic_offers")
    return records if isinstance(records, dict) else {}


def _writable_records(world: dict[str, Any]) -> dict[str, Any]:
    flags = world.setdefault("flags", {})
    if not isinstance(flags.get("economic_offers"), dict):
        flags["economic_offers"] = {}
    return flags["economic_offers"]


def offer_from_record(data: Any) -> EconomicOffer | None:
    """The stored dict back as an offer; anything malformed is no offer at all."""
    try:
        proposal = dict(data["proposal"])
        span = proposal.get("text_span")
        proposal["text_span"] = TextSpan(**span) if isinstance(span, dict) else None
        acceptance = dict(data["acceptance"])
        check = acceptance.get("check")
        acceptance["check"] = CheckSpec(**check) if isinstance(check, dict) else None
        acceptance["line_decisions"] = [LineDecision(**item) for item in acceptance["line_decisions"]]
        return EconomicOffer(**{
            **data, "proposal": EconomicProposal(**proposal), "lines": [OfferLine(**line) for line in data["lines"]],
            "acceptance": AcceptanceRecord(**acceptance),
            "on_accept": [WorldEffect(**effect) for effect in data["on_accept"]]})
    except (KeyError, TypeError, ValueError):
        return None


def prepared_offer(world: dict[str, Any], *, actor_id: str = "player") -> EconomicOffer | None:
    """The one open card of this actor (C12), the latest when an old save holds more."""
    found = [offer for data in offer_records(world).values()
             if (offer := offer_from_record(data)) is not None and offer.status == "prepared"
             and offer.actor_id == actor_id]
    return found[-1] if found else None


def cancel_offer(world: dict[str, Any], *, offer_id: str) -> bool:
    """Close one prepared card. Cancelling moves no coin, goods or time."""
    data = offer_records(world).get(offer_id)
    if not isinstance(data, dict) or data.get("status") != "prepared":
        return False
    data["status"] = "cancelled"
    return True


def cancel_prepared(world: dict[str, Any], *, actor_id: str, except_offer_id: str | None = None,
                    except_source_action_id: str | None = None,
                    predicate: Callable[[EconomicOffer], bool] | None = None) -> list[str]:
    """Cancel this actor's prepared cards, except the named one and those the named action prepared."""
    cancelled = []
    for offer_id, data in offer_records(world).items():
        offer = offer_from_record(data)
        if offer is None or offer.status != "prepared" or offer.actor_id != actor_id or offer_id == except_offer_id:
            continue
        if except_source_action_id is not None and offer.proposal.source_action_id == except_source_action_id:
            continue
        if predicate is not None and not predicate(offer):
            continue
        data["status"] = "cancelled"
        cancelled.append(offer_id)
    return cancelled


def prune_offer_records(world: dict[str, Any], *, keep: int = OFFER_RECORDS_KEEP,
                        protect_action_id: str | None = None) -> None:
    """Keep at most the last `keep` closed cards; a prepared one and the one the live checkpoint consumed stay."""
    records = offer_records(world)
    closed = [offer_id for offer_id, data in records.items()
              if isinstance(data, dict) and data.get("status") in ("consumed", "cancelled")
              and not (protect_action_id is not None and data.get("consumed_action_id") == protect_action_id)]
    for offer_id in closed[:max(len(closed) - keep, 0)]:
        records.pop(offer_id)


def prepare_from_panel(state: EconomicState, proposal: EconomicProposal, *, campaign_id: str, actor_id: str,
                       turn_index: int, protect_action_id: str | None = None) -> PrepareResult:
    """The API's prepare: the purpose and bribe gates, then `prepare_offer`, then the card is stored (C12).

    A refusal or a question stores nothing and closes no other card.
    """
    import world_reactions
    world = state.world
    if proposal.purpose not in _PANEL_PURPOSES:
        return _clarify("purpose_not_offered_here")  # O3: no second way to buy or hand over a valued item
    guard = world_reactions.arrester(world)
    if guard is not None and guard.get("id") == proposal.recipient_id and world_reactions.holding(world, guard):
        return _clarify("bribe_in_turn_only")  # O1: the bribe card opens only from the spoken turn
    records = offer_records(world)
    offer_id = new_offer_id()
    while offer_id in records:
        offer_id = new_offer_id()
    result = prepare_offer(state, proposal, offer_id=offer_id, campaign_id=campaign_id, actor_id=actor_id,
                           turn_index=turn_index)
    if result.status == "prepared" and result.offer is not None:
        cancel_prepared(world, actor_id=actor_id, except_offer_id=offer_id)
        _writable_records(world)[offer_id] = dataclasses.asdict(result.offer)
        prune_offer_records(world, protect_action_id=protect_action_id)
    return result


def _still_holds(state: EconomicState, offer: EconomicOffer) -> bool:
    """C3: the counterparty, the place, combat, the price and the stock read again; the purse is not (R5)."""
    import equipment_economy
    import shop_trade
    world = _settled(state.world)
    proposal = offer.proposal
    if _combat(world) or world.get("location") != offer.place_id:
        return False
    npc = _npc(world, proposal.recipient_id)
    if npc is None or not _is_here(world, npc):
        return False
    if proposal.purpose in ("purchase", "room"):
        counter = shop_trade.counter(world)
        vendor = counter.get("vendor") or {}
        if vendor.get("npc_id") != str(npc.get("id")) \
                or counter["reason"] in ("no_vendor", "vendor_unavailable", "not_now"):
            return False
    elif not equipment_economy.npc_can_act(npc):
        return False
    lines = _lines(world, proposal, npc)
    if isinstance(lines, str) or lines != list(offer.lines):
        return False
    return context_digest(state, proposal, lines) == offer.context_digest


def _unmoved(operation_id: str, offer_id: str, reason: str, offer: EconomicOffer | None) -> EconomicResolution:
    lines = list(offer.lines) if offer is not None else []
    summary = {"offer_not_prepared": "Bu teklif artık açık değil; hiçbir şey ödenmedi.",
               "digest_mismatch": "Onaylanan teklif bu kartla uyuşmuyor; hiçbir şey ödenmedi.",
               "stale": "Teklif değişti; yeni kart gerekir. Hiçbir şey ödenmedi."}[reason]
    return EconomicResolution(
        operation_id=operation_id, offer_id=offer_id, purpose=offer.proposal.purpose if offer is not None else "gift",
        base_fingerprint="", status="refused", reason_code=reason, lines=lines, asset_deltas=[], service_rights=[],
        world_effects=[], refusals=[LineRefusal(line_id=line.line_id, reason_code=reason) for line in lines],
        public_summary=summary, tender_cp=offer.proposal.tender_cp if offer is not None else None, change_cp=0,
        net_debit_cp=0)


def confirm_offer(state: EconomicState, *, offer_id: str, confirmation_digest: str, operation_id: str,
                  check: Callable[[str, int], str]) -> EconomicResolution:
    """Confirm exactly the stored card. Only a result that consumes it writes anything but the card's own status.

    A card that is not prepared, a digest that does not match, or a world that changed since (stale) moves nothing
    and settles no purse label; a stale card is cancelled. Any other result consumes the card: an applied one goes
    through `apply_resolution`, a refused one (no money, a failed check, a bad tender) settles the purse labels and
    is entered in the ledger so the same card cannot be tried again by a new action.
    """
    import bold_acts
    world = state.world
    data = offer_records(world).get(offer_id)
    offer = offer_from_record(data) if isinstance(data, dict) else None
    if offer is None or offer.status != "prepared" or offer.offer_id != offer_id:
        return _unmoved(operation_id, offer_id, "offer_not_prepared", None)
    if not (isinstance(confirmation_digest, str) and secrets.compare_digest(confirmation_digest,
                                                                         offer.confirmation_digest)
            and _digest_of(offer) == offer.confirmation_digest):
        return _unmoved(operation_id, offer_id, "digest_mismatch", offer)
    if not _still_holds(state, offer):
        data["status"] = "cancelled"
        return _unmoved(operation_id, offer_id, "stale", offer)
    resolution = resolve_offer(state, offer, operation_id=operation_id, check=check)
    if resolution.status == "applied":
        resolution = apply_resolution(state, resolution, confirmed_offer=offer)
        if resolution.status != "applied" and resolution.reason_code == "stale":
            data["status"] = "cancelled"  # the copy found the world moved; nothing was written to the live one
            return _unmoved(operation_id, offer_id, "stale", offer)
    if resolution.status != "applied":
        operations = world.setdefault("flags", {}).setdefault("economic_ledger", {}).setdefault("operations", {})
        if operation_id in operations:
            raise EconomicReceiptError("operation_id_reused")
        bold_acts.settle_coin_labels(world)  # C10: the consuming confirm keeps the settled purse
        operations[operation_id] = {"offer_id": offer_id, "purpose": offer.proposal.purpose, "net_debit_cp": 0,
                                    "turn_index": world["flags"].get("turn_index", 0),
                                    "reason_code": resolution.reason_code,
                                    **_receipt_fields(list(offer.lines), offer.proposal.recipient_id)}
        trim_operations(operations)
    data.update(status="consumed", operation_id=operation_id)
    return resolution


def reconcile_offers_after_undo(restored_world: dict[str, Any], current_offers: dict[str, dict], *,
                                undone_action_id: str) -> None:
    """After undo put the world back (C11, D2): only the card the undone action consumed is open again.

    A cancelled card stays cancelled, a card prepared after the target turn comes back cancelled, and a card the
    restored world holds open but the current one no longer has (cancelled, then pruned) is cancelled.
    """
    current = current_offers if isinstance(current_offers, dict) else {}
    if not current and not offer_records(restored_world):
        return  # no card on either side: the restored save stays byte for byte as it was
    restored = _writable_records(restored_world)
    for offer_id, data in current.items():
        if not isinstance(data, dict):
            continue
        entry = copy.deepcopy(data)
        if entry.get("status") == "consumed" and entry.get("consumed_action_id") == undone_action_id:
            entry.update(status="prepared", operation_id=None, consumed_action_id=None)
        elif offer_id not in restored and entry.get("status") == "prepared":
            entry["status"] = "cancelled"
        restored[offer_id] = entry
    for offer_id, data in restored.items():
        if offer_id not in current and isinstance(data, dict) and data.get("status") == "prepared":
            data["status"] = "cancelled"
    prune_offer_records(restored_world, protect_action_id=None)


# ---------------------------------------------------------------------------------------------------------------
# A4: the turn paths. A line prepares a card (`prepare_from_turn`); an engine payment without a card (an NPC's
# own give, the counter sale) takes a distinct operation id from the ledger's counter (`operation_id_for`).
# ---------------------------------------------------------------------------------------------------------------

def _active_action_id() -> str | None:
    from api.core_resolution import _ACTIVE_ACTION
    scope = _ACTIVE_ACTION.get()
    return scope.action_id if scope is not None else None


def operation_id_for(world: dict[str, Any], kind: str) -> str:
    """`<action or "unscoped">:economic:<kind>:<seq>`; the counter lives in the ledger and comes back with undo.

    Every call moves the counter, so two real payments of one action (even with the same NPC and amount) never
    share an id, however many times game.py opens the same action's scope.
    """
    ledger = world.setdefault("flags", {}).setdefault("economic_ledger", {})
    seq = ledger.get("operation_seq", 0)
    seq = (seq if type(seq) is int and seq >= 0 else 0) + 1
    ledger["operation_seq"] = seq
    return f"{_active_action_id() or 'unscoped'}:economic:{kind}:{seq}"


def prepared_by_action(world: dict[str, Any], *, source_action_id: str, purpose: str) -> dict[str, Any] | None:
    """The first card this action prepared for this purpose that is still open."""
    for data in offer_records(world).values():
        offer = offer_from_record(data)
        if (offer is not None and offer.status == "prepared" and offer.proposal.source_action_id == source_action_id
                and offer.proposal.purpose == purpose):
            return data
    return None


def turn_proposal(purpose: Purpose, recipient_id: str, *, amount_cp: int | None = None,
                  tender_cp: int | None = None) -> EconomicProposal:
    """A proposal read from a line; `prepare_from_turn` fills in the source action."""
    return EconomicProposal(purpose=purpose, recipient_id=recipient_id, source_id=None, item_id=None, count=1,
                            amount_cp=amount_cp, tip_cp=0, tender_cp=tender_cp, dependency="base_required",
                            source_action_id="", text_span=None)


def prepare_from_turn(session: Any, proposal: EconomicProposal) -> PrepareResult:
    """A card from a turn's line. Writes only the card's own record; no coin, goods or time move.

    The source action is the turn's key (`game.turn_source_key`), or a fresh `turn:` key for a call from outside a
    turn, so the card of this action is found again later in the same run and spared by its own change of place.
    A new card closes the player's other open cards (C12); a refusal or a question stores nothing.
    """
    import game
    world = session.world_state
    key = game.turn_source_key(session) or f"turn:{secrets.token_hex(8)}"
    proposal = dataclasses.replace(proposal, source_action_id=key)
    records = offer_records(world)
    offer_id = new_offer_id()
    while offer_id in records:
        offer_id = new_offer_id()
    flags = world.get("flags") or {}
    turn = flags.get("turn_index", 0)
    result = prepare_offer(EconomicState(world=world, character=getattr(session, "character", None)), proposal,
                           offer_id=offer_id, campaign_id=str(world.get("campaign_id") or "turn"), actor_id="player",
                           turn_index=turn if type(turn) is int else 0)
    if result.status == "prepared" and result.offer is not None:
        cancel_prepared(world, actor_id="player", except_offer_id=offer_id)
        _writable_records(world)[offer_id] = dataclasses.asdict(result.offer)
        # The newest consuming confirm is the only one the live undo checkpoint can point at: keep it from pruning.
        consumed = [data.get("consumed_action_id") for data in offer_records(world).values()
                    if isinstance(data, dict) and data.get("status") == "consumed" and data.get("consumed_action_id")]
        prune_offer_records(world, protect_action_id=consumed[-1] if consumed else None)
    return result


def npc_gift(state: EconomicState, *, npc_id: str, amount_cp: int) -> EconomicResolution:
    """An NPC hands the player coin from their own purse (C5): no card, since the player pays nothing.

    The NPC must be here and hold the amount; otherwise nothing moves. Applied once by the one owner.
    """
    world = state.world
    settled = _settled(world)
    facts = economic_facts(EconomicState(world=settled, character=None))
    line = OfferLine(line_id="npc_gift:0", kind="gift", source_id=str(npc_id), item_id=None, recipient_id="player",
                     count=1, unit_cp=amount_cp if _cp(amount_cp) else 0,
                     total_cp=amount_cp if _cp(amount_cp) else 0, optional=False)
    blank = EconomicResolution(
        operation_id="", offer_id=None, purpose="npc_gift", base_fingerprint=_sha(facts), status="refused",
        reason_code=None, lines=[line], asset_deltas=[], service_rights=[], world_effects=[], refusals=[],
        public_summary="", tender_cp=None, change_cp=0, net_debit_cp=0)
    npc = _npc(settled, npc_id)
    if not (type(amount_cp) is int and 0 < amount_cp <= MAX_CP):
        return dataclasses.replace(_refused(blank, "invalid_amount"), public_summary="")
    if npc is None or not _is_here(settled, npc):
        return dataclasses.replace(_refused(blank, "npc_not_here"), public_summary="")
    held = facts.balances.get(str(npc_id))
    if held is None or held < amount_cp:
        return dataclasses.replace(_refused(blank, "npc_purse_short"), public_summary="")
    mine = facts.balances.get("player", 0)
    # The id is drawn from a copy of the counter; the live counter moves only once the gift is applied, so a
    # refused or failed write leaves the live world exactly as it was.
    peek = {"flags": {"economic_ledger": {"operation_seq": _ledger(world).get("operation_seq", 0)}}}
    resolution = dataclasses.replace(
        blank, operation_id=operation_id_for(peek, "npc_gift"), status="applied",
        asset_deltas=[AssetDelta(owner_id="player", asset_kind="currency", asset_id="cp", before=mine,
                                 after=mine + amount_cp),
                      AssetDelta(owner_id=str(npc_id), asset_kind="currency", asset_id="cp", before=held,
                                 after=held - amount_cp)],
        net_debit_cp=amount_cp, public_summary=f"{amount_cp} bakır sana geçti.")
    applied = apply_resolution(state, resolution, confirmed_offer=None)
    if applied.status == "applied":
        world.setdefault("flags", {}).setdefault("economic_ledger", {})["operation_seq"] = (
            peek["flags"]["economic_ledger"]["operation_seq"])
    return applied


def counter_purchase_offer(world: dict[str, Any], *, npc_id: str, key: str, count: int, unit_cp: int,
                           tender_cp: int | None, tip_cp: int = 0) -> EconomicOffer:
    """The counter's own purchase, built in memory only: it is never stored and never confirmed from a card.

    `shop_trade.commit` has already checked the vendor, price, stock, refusal and purse; the engine accepts. A tip
    the counter's offer carries (`tip_cp`, Python's own figure, checked by `shop_trade._tip`) is one more line to the
    vendor, accepted by the engine too, so it is paid on the same receipt and never dropped as undecided (D8).
    """
    tip = tip_cp if type(tip_cp) is int and tip_cp > 0 else 0
    lines = [OfferLine(line_id="goods:0", kind="goods", source_id=npc_id, item_id=key, recipient_id=npc_id,
                       count=count, unit_cp=unit_cp, total_cp=unit_cp * count, optional=False)]
    decisions = [LineDecision(line_id="goods:0", status="accepted", reason_code="engine_accepts")]
    if tip:
        lines.append(OfferLine(line_id="tip:1", kind="tip", source_id=None, item_id=None, recipient_id=npc_id,
                               count=1, unit_cp=tip, total_cp=tip, optional=True))
        decisions.append(LineDecision(line_id="tip:1", status="accepted", reason_code="engine_accepts"))
    proposal = EconomicProposal(purpose="purchase", recipient_id=npc_id, source_id=npc_id, item_id=key, count=count,
                                amount_cp=None, tip_cp=tip, tender_cp=tender_cp, dependency="base_required",
                                source_action_id=_active_action_id() or "counter", text_span=None)
    offer_id = new_offer_id()
    acceptance = AcceptanceRecord(record_id=f"acceptance:{offer_id}", offer_id=offer_id, npc_id=npc_id,
                                  context_digest="", producer="engine", check=None, line_decisions=decisions)
    turn = (world.get("flags") or {}).get("turn_index", 0)
    offer = EconomicOffer(offer_id=offer_id, actor_id="player", campaign_id=str(world.get("campaign_id") or "turn"),
                          place_id=str(world.get("location")), proposal=proposal, lines=lines, acceptance=acceptance,
                          on_accept=[], context_digest="", confirmation_digest="", status="prepared",
                          operation_id=None, prepared_turn=turn if type(turn) is int else 0, consumed_action_id=None)
    return dataclasses.replace(offer, confirmation_digest=confirmation_digest(offer))


def public_resolution(state: EconomicState, resolution: EconomicResolution) -> PublicEconomicResolution:
    """The receipt the player may see: their own lines and money, never another purse or the inner acceptance."""
    return PublicEconomicResolution(
        operation_id=resolution.operation_id, offer_id=resolution.offer_id, status=resolution.status,
        reason_code=resolution.reason_code,
        lines=[PublicOfferLine(line_id=line.line_id, label=_line_label(line), count=line.count, unit_cp=line.unit_cp,
                               total_cp=line.total_cp, optional=line.optional) for line in resolution.lines],
        refusals=[PublicLineRefusal(line_id=refusal.line_id, reason_code=refusal.reason_code)
                  for refusal in resolution.refusals],
        tender_cp=resolution.tender_cp, change_cp=resolution.change_cp, net_debit_cp=resolution.net_debit_cp,
        public_summary=resolution.public_summary)
