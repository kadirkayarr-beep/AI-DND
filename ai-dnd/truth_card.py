"""Read-only engine facts. NPC selection precedes formatting and byte budgeting."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import bold_acts
import economic_actions
import exits
import gear
import living_world
import item_use
import pocket
import quest_log
import shop_trade

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Line:
    name: str
    text: str
    priority: int = 0
    shorter: str | None = None
    keep: str = ""  # the line's own closing words, kept whole when its values are shortened


REFUSAL_NOTE = "olmadı notu"  # the name a dropped refusal note has in the "(kısaltıldı: …)" mark (tasarım §3e)
# Optional facts go in this order (tasarım karar 59); "son görev" is the last running-quest line, after the prices.
_OPTIONAL_ORDER = ("çıkışlar", "izler", "görevler", "ödemeler", "çanta", "fiyatlar", "son görev")


def _clip(text, size, *, words=False):
    if len(text.encode("utf-8")) <= size:
        return text
    if size < 3:
        return ""
    head = text.encode("utf-8")[:size - 3].decode("utf-8", errors="ignore")
    if words and " " in head:
        head = head.rsplit(" ", 1)[0]
    return head + "…"


def _shorten(row, size):
    """The line at most `size` bytes: its values are cut at a word, its own closing words stay whole."""
    if row.keep and row.text.endswith(row.keep):
        head = row.text[:-len(row.keep)]
        return _clip(head, max(0, size - len(row.keep.encode("utf-8"))), words=True) + row.keep
    return _clip(row.text, size, words=True)


def _note_rows(notes):
    """This turn's notes as the card's "bu tur" group: refusal notes first, each on its own line in the order they came,
    then the other notes on one line (tasarım §3e)."""
    refused = [note for note in notes if note.startswith("olmadı:")]
    plain = [note.removeprefix("bu tur: ") for note in notes if not note.startswith("olmadı:")]
    rows = [_Line(REFUSAL_NOTE, note, 2) for note in refused]
    if plain:
        rows.append(_Line("bu tur", "bu tur: " + "; ".join(plain), 2))
    return rows


def _quest_rows(card_lines):
    """The running quests and the trails (quest_log), both optional: of the quests one is left until the prices go."""
    quests = [line for line in card_lines if line.startswith("görevlerin:")]
    trails = [line for line in card_lines if line.startswith("izler:")]
    rows = []
    if quests:
        rows.append(_Line("görevler", "\n".join(quests), shorter=quests[0]))
    if trails:
        rows.append(_Line("izler", "\n".join(trails)))
    return rows


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
    for name in _OPTIONAL_ORDER:
        if len(text().encode("utf-8")) <= max_bytes:
            return text()
        for i, row in enumerate(lines):
            if name == "son görev" and row.name == "görevler" and row.priority == 0:
                lines[i] = replace(row, text="")
            elif row.name == name and row.priority == 0:
                lines[i] = replace(row, text=row.shorter or "")
    for i, row in enumerate(lines):
        size = 140 if row.name in ("bu tur", REFUSAL_NOTE) else 100  # a note keeps more of its words
        if row.priority and row.priority < 4 and len(row.text.encode("utf-8")) > size:
            if len(text().encode("utf-8")) <= max_bytes:
                break
            lines[i] = replace(row, text=_shorten(row, size))
            if row.name not in changed:
                changed.append(row.name)
    # Remaining optional details cannot displace mandatory facts.
    if len(text().encode("utf-8")) > max_bytes:
        lines = [row for row in lines if row.priority]
    # The person group goes first; of this turn's result the other notes, then the newest refusal, the first one last.
    group = [row for row in lines if row.priority == 2]
    order = ([row for row in lines if row.priority == 1] + [row for row in group if row.name != REFUSAL_NOTE]
             + [row for row in reversed(group) if row.name == REFUSAL_NOTE])
    for row in order:
        if len(text().encode("utf-8")) <= max_bytes:
            break
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


_NOT_MOVED = "; para henüz el değiştirmedi"


def _offer_line(text):
    """The active deal: a long name or label is shortened, its closing words that the money has not moved stay."""
    return _Line("açık teklif", text, 3, keep=_NOT_MOVED if text.endswith(_NOT_MOVED) else "")


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
    ammo = item_use.ammo_note(world)
    suffix = " " + ammo if ammo else ""
    held = gear.wielded(world)
    lines.extend([_Line("çanta", bag + suffix, shorter="çanta: " + (names[0] if names else "boş") + suffix),
                  _Line("oda", _room(world), 1),
                  _Line("elinde", f"elinde: {held.get('name')}" if held else "elin boş", 1),
                  _offer_line(_offers(world)), _payments(world)])
    lines.extend(_note_rows([note for _, note in this_turn]))
    lines.extend(_quest_rows(quest_log.card_lines(world)))
    seller = npc if shop_trade.is_vendor(world, npc) else None
    if seller is None:
        sellers = [n for n in world.get("npcs", []) if n.get("location") == world.get("location") and shop_trade.is_vendor(world, n)]
        seller = sellers[0] if len(sellers) == 1 else None
    prices = _prices(world, seller, scoped=False)
    if prices:
        lines.append(prices)
    way_out = exits.way_out_name(world, world.get("location"))
    lines.append(_Line("çıkışlar", f"çıkışlar: {way_out}" if way_out else "kayıtlı çıkış yok"))
    return _fit(lines, max_bytes)


def npc_view(world: dict, *, npc: dict, held_out_cp: int = 0, this_turn=(), max_bytes: int = 600) -> str:
    lines = [_Line("başlık", "SENİNLE OYUNCU ARASINDAKİ İŞLER (motor; salt okunur):", 4)]
    if held_out_cp > 0:
        lines.append(_Line("uzatılan para", f"oyuncunun sana uzattığı: {held_out_cp} bakır; para henüz el değiştirmedi", 3))
    lines.extend([_offer_line(_offers(world, npc)), _payments(world, npc)])
    if shop_trade.is_vendor(world, npc) and npc.get("location") == world.get("location") and economic_actions._room_right(world):
        lines.append(_Line("oda", _room(world), 1))
    lines.extend(_note_rows([note for npc_id, note in this_turn if npc_id is not None and npc_id == npc.get("id")]))
    if npc.get("id"):  # only that person's jobs and trails (tasarım karar 61); never the player's hand or bag (D28)
        lines.extend(_quest_rows(quest_log.card_lines(world, npc=npc)))
    prices = _prices(world, npc, scoped=True)
    if prices:
        lines.append(prices)
    elif not any(isinstance(shop, dict) and npc.get("id") and shop.get("shopkeeper_id") == npc.get("id")
                 for shop in world.get("shops", [])):
        # Owner decision F: no engine sale (the list or a shop's wares) and no making exists for this person, so a
        # "körüğü yakıyorum" promise has nothing behind it.
        lines.append(_Line("satış", "motorda sattığın ya da yaptığın bir şey yok", 1))
    return _fit(lines, max_bytes)