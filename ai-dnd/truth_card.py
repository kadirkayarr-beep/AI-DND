"""Read-only engine facts. NPC selection precedes formatting and byte budgeting."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import bold_acts
import economic_actions
import living_world
import pocket
import shop_trade

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Line:
    name: str
    text: str
    priority: int = 0
    shorter: str | None = None


def _clip(text, size, *, words=False):
    if len(text.encode("utf-8")) <= size:
        return text
    if size < 3:
        return ""
    head = text.encode("utf-8")[:size - 3].decode("utf-8", errors="ignore")
    if words and " " in head:
        head = head.rsplit(" ", 1)[0]
    return head + "…"


def _fit(lines, max_bytes):
    """Keep active operations last; name every shortened mandatory fact."""
    if max_bytes <= 0:
        return ""
    lines = list(lines)
    changed = []

    def text():
        body = "\n".join(row.text for row in lines if row.text)
        return body + ("\n(kısaltıldı: " + ", ".join(changed) + ")" if changed else "")

    # Optional facts shed detail in the design's fixed order.
    for name in ("çıkışlar", "ödemeler", "çanta", "fiyatlar"):
        if len(text().encode("utf-8")) <= max_bytes:
            return text()
        for i, row in enumerate(lines):
            if row.name == name and row.priority == 0:
                lines[i] = replace(row, text=row.shorter or "")
    for i, row in enumerate(lines):
        if row.priority and row.priority < 4 and len(row.text.encode("utf-8")) > 100:
            if len(text().encode("utf-8")) <= max_bytes:
                break
            lines[i] = replace(row, text=_clip(row.text, 100, words=True))
            changed.append(row.name)
    # Remaining optional details cannot displace mandatory facts.
    if len(text().encode("utf-8")) > max_bytes:
        lines = [row for row in lines if row.priority]
    for priority in (1, 2):
        for row in list(lines):
            if len(text().encode("utf-8")) <= max_bytes:
                break
            if row.priority == priority:
                lines.remove(row)
                if row.name not in changed:
                    changed.append(row.name)
    if len(text().encode("utf-8")) > max_bytes:
        active = [row for row in lines if row.priority == 3]
        for row in active:
            if row.name not in changed:
                changed.append(row.name)
        overhead = len(("\n(kısaltıldı: " + ", ".join(changed) + ")").encode("utf-8"))
        header = next((row for row in lines if row.priority == 4), None)
        available = max_bytes - overhead - (len(header.text.encode("utf-8")) + 1 if header else 0)
        each = max(0, (available - max(0, len(active) - 1)) // max(1, len(active)))
        lines = ([header] if header else []) + [replace(row, text=_clip(row.text, each)) for row in active]
    result = text()
    if changed:
        logger.warning("Truth card shortened: %s", ", ".join(changed))
    return _clip(result, max_bytes)


def _person(world, npc_id):
    return next((n for n in world.get("npcs", []) if isinstance(n, dict) and n.get("id") == npc_id), None)


def _place(world, place_id):
    return str((world.get("locations", {}).get(place_id) or {}).get("name") or "bulunulan yer")


def _room(world):
    held = (world.get("flags") or {}).get("inn_room")
    now = (world.get("campaign_time") or {}).get("elapsed_seconds", 0)
    if not isinstance(held, dict) or now >= held.get("until", 0):
        return "oda tutulmadı"
    total = (world.get("campaign_time") or {}).get("start_second", 0) + held["until"]
    day, second = divmod(total, 86400)
    return f"oda tutuldu: {_place(world, held['place'])}, gün {day + 1} {second // 3600:02}:00'a kadar"


def _offers(world, npc=None):
    found = []
    if npc is not None and not npc.get("id"):
        return "açık teklif yok"
    people = [npc] if npc is not None else world.get("npcs", [])
    for person in people:
        opened = bold_acts.offer_still_open(world, person)
        if not opened:
            continue
        goods = next((g for g in shop_trade.goods(world, person) if g["key"] == opened.get("key")), None)
        if goods:
            fresh = shop_trade.quote(world, person["id"], goods["key"], 1)
            amount = fresh["total_cp"] + shop_trade._tip(world, person["id"], goods["key"], 1, fresh)
            found.append((goods["label"], amount, person))
    for row in economic_actions.offer_records(world).values():
        if not isinstance(row, dict) or row.get("status") != "prepared" or row.get("place_id") != world.get("location"):
            continue
        recipient = (row.get("proposal") or {}).get("recipient_id")
        if npc is not None and recipient != npc.get("id"):
            continue
        offer = economic_actions.offer_from_record(row)
        if offer is None:
            continue
        for item in offer.lines:
            found.append((economic_actions._public_label(world, item), item.total_cp, _person(world, recipient)))
    if not found:
        return "açık teklif yok"
    parts = [f"{label} {amount} bakır" + (f", {living_world.public_npc_name(person)}" if npc is None else "")
             for label, amount, person in found]
    return "açık teklif: " + "; ".join(parts) + "; para henüz el değiştirmedi"


def _payments(world, npc=None):
    records = ([] if npc is not None and not npc.get("id") else
               economic_actions.recent_payments(world, 3, payee_id=npc.get("id") if npc is not None else None))
    parts = []
    for record in records:
        part = (f"{record['label']}, {record['amount_cp']} bakır" if record["label"]
                else f"ödeme {record['amount_cp']} bakır")
        if npc is None:
            part += f", {living_world.public_npc_name(_person(world, record['payee_id']))}'e"
        turn = record["turn_index"]
        if turn is not None:
            part += f", {max(0, (world.get('flags') or {}).get('turn_index', 0) - turn)} tur önce"
        parts.append(part)
    prefix = "sana ödendi: " if npc else "ödendi: "
    empty = "kayıtta sana ödeme yok" if npc else "kayıtta ödeme yok"
    return _Line("ödemeler", prefix + "; ".join(parts) if parts else empty,
                 shorter=prefix + parts[0] if parts else empty)


def _prices(world, npc, *, scoped):
    if not shop_trade.is_vendor(world, npc):
        return None
    goods = shop_trade.goods(world, npc)
    parts = [f"{g['label']} {g['unit_cp']} bakır" for g in goods]
    room = f"oda {bold_acts.room_price(world, npc)} bakır"
    parts.append(room)
    opened = bold_acts.offer_still_open(world, npc)
    short = [f"{g['label']} {g['unit_cp']} bakır" for g in goods if opened and g['key'] == opened.get('key')]
    prefix = "fiyatların (motorun; başka fiyat söyleme): " if scoped else "fiyatlar (motorun; başka fiyat söyleme): "
    return _Line("fiyatlar", prefix + ", ".join(parts), shorter=prefix + ", ".join(short + [room]))


def narrator_view(world: dict, *, npc: dict | None = None, this_turn=(), max_bytes: int = 600) -> str:
    lines = [_Line("başlık", "MOTOR GERÇEĞİ (salt okunur):", 4)]
    if npc:
        role = npc.get("role", "") if living_world.npc_role_known_to_player(npc) else ""
        lines.append(_Line("kişi", f"konuşulan: {living_world.public_npc_name(npc)} ({role})", 1))
    cp = shop_trade.purse_cp(world)
    lines.append(_Line("kese", f"kese: {cp} bakır ({cp // 100} altın {cp % 100 // 10} gümüş {cp % 10} bakır)", 1))
    names = pocket.bag_names(world)
    remaining = max(0, len(world.get("inventory", [])) - 8)
    bag = "çanta: " + (", ".join(names[:8]) or "boş") + (f" ve {remaining} eşya daha" if remaining else "")
    lines.extend([_Line("çanta", bag, shorter="çanta: " + (names[0] if names else "boş")),
                  _Line("oda", _room(world), 1), _Line("açık teklif", _offers(world), 3), _payments(world)])
    if this_turn:
        lines.append(_Line("bu tur", "bu tur: " + "; ".join(note for _, note in this_turn), 2))
    seller = npc if shop_trade.is_vendor(world, npc) else None
    if seller is None:
        sellers = [n for n in world.get("npcs", []) if n.get("location") == world.get("location") and shop_trade.is_vendor(world, n)]
        seller = sellers[0] if len(sellers) == 1 else None
    prices = _prices(world, seller, scoped=False)
    if prices:
        lines.append(prices)
    place = (world.get("locations") or {}).get(world.get("location")) or {}
    exits = list(dict.fromkeys(place[k] for k in ("exit_location_id", "parent_location_id") if place.get(k)))
    lines.append(_Line("çıkışlar", "çıkışlar: " + ", ".join(_place(world, key) for key in exits) if exits else "kayıtlı çıkış yok"))
    return _fit(lines, max_bytes)


def npc_view(world: dict, *, npc: dict, held_out_cp: int = 0, this_turn=(), max_bytes: int = 600) -> str:
    lines = [_Line("başlık", "SENİNLE OYUNCU ARASINDAKİ İŞLER (motor; salt okunur):", 4)]
    if held_out_cp > 0:
        lines.append(_Line("uzatılan para", f"oyuncunun sana uzattığı: {held_out_cp} bakır; para henüz el değiştirmedi", 3))
    lines.extend([_Line("açık teklif", _offers(world, npc), 3), _payments(world, npc)])
    if shop_trade.is_vendor(world, npc) and npc.get("location") == world.get("location") and economic_actions._room_right(world):
        lines.append(_Line("oda", _room(world), 1))
    notes = [note for npc_id, note in this_turn if npc_id is not None and npc_id == npc.get("id")]
    if notes:
        lines.append(_Line("bu tur", "bu tur: " + "; ".join(notes), 2))
    prices = _prices(world, npc, scoped=True)
    if prices:
        lines.append(prices)
    return _fit(lines, max_bytes)