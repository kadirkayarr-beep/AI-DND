"""Economic offers: what the player proposes, what the engine accepts, and nothing moved while it is only a card.

Python owns it. A proposal (from the panel or a turn) is read against a copy of the world with the purse's
written coin labels settled, priced from the one server table (`shop_trade` goods, `bold_acts._ROOM_PRICE`),
and judged by the engine alone: whether the counterparty is here, can act, refuses the player, or is the guard
holding them (a bribe, decided later by a Persuasion check). Preparing writes nothing: no coin, goods, clock or
offer record. The API stores the offer in `world.flags.economic_offers` (A3); the turn paths are bound in A4.

No network, model or database call is made here.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any, Literal

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
    return None


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


def derive_acceptance(state: EconomicState, *, offer_id: str, proposal: EconomicProposal,
                      lines: list[OfferLine]) -> AcceptanceRecord | PrepareResult:
    """The engine's word on the offer, before anything is recorded. A refusal opens no card."""
    import world_reactions
    world = _settled(state.world)
    npc = _npc(world, proposal.recipient_id)
    if npc is None:
        return _clarify("npc_unknown")
    check = None
    if _is_bribe(world, proposal, npc):
        # The guard holding the player usually can tie them to the deed, so `refuses` is not asked here:
        # whether the coin is taken is the Persuasion check at confirmation, as the spoken bribe does today.
        check = CheckSpec(skill="Persuasion", difficulty=_difficulty(lines[0].total_cp))
    elif world_reactions.refuses(world, npc):
        return PrepareResult(status="refused", offer=None, reason_code="npc_refuses",
                             public_message=world_reactions.refusal_line(npc))
    reason = "check_required" if check is not None else "engine_accepts"
    return AcceptanceRecord(record_id=f"acceptance:{offer_id}", offer_id=offer_id, npc_id=str(npc["id"]),
                            context_digest=context_digest(state, proposal, lines), producer="engine", check=check,
                            line_decisions=[LineDecision(line_id=line.line_id, status="accepted", reason_code=reason)
                                            for line in lines])


def _line_label(line: OfferLine) -> str:
    import shop_trade
    if line.kind == "goods":
        label = next((label for key, label, _ in shop_trade.PRICES if key == line.item_id), str(line.item_id))
        return label[:1].upper() + label[1:]
    return {"room": "Oda (bir gece)", "gift": "Hediye", "tip": "Bahşiş"}.get(line.kind, "Eşya")


def public_offer(state: EconomicState, offer: EconomicOffer) -> PublicEconomicOffer:
    import living_world
    npc = _npc(state.world, offer.proposal.recipient_id)
    return PublicEconomicOffer(
        offer_id=offer.offer_id, confirmation_digest=offer.confirmation_digest,
        counterparty_label=living_world.public_npc_name(npc),
        lines=[PublicOfferLine(line_id=line.line_id, label=_line_label(line), count=line.count, unit_cp=line.unit_cp,
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
    if proposal.purpose == "item_gift":
        return _clarify("purpose_not_offered_here")  # the valued-item card comes with A5
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
    return PrepareResult(status="prepared", offer=offer, reason_code=None,
                         public_message=f"{who} için teklif hazır: en çok {total} bakır. Onaylarsan işlem denenir.")
