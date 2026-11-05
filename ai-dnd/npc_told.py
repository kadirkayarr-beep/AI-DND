"""Player words addressed to one NPC: attributed memory, never world truth."""
from collections.abc import Mapping, Sequence
from typing import Literal
import logging

from npc_statements import fold

KEY = "npc_told_v1"
KEEP_PER_NPC = 40
MAX_NPCS = 32
MAX_CHARS = 600
VIEW_ROWS = 3
VIEW_CHARS = 200
VIEW_BYTES = 600
logger = logging.getLogger(__name__)


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    prefix = text[:limit]
    if text[limit].isspace():
        return prefix.rstrip()
    return prefix[:max((i for i, c in enumerate(prefix) if c.isspace()), default=0)].rstrip()


def _row(row):
    return (isinstance(row, Mapping) and type(row.get("turn")) is int
            and row["turn"] >= 0 and isinstance(row.get("text"), str)
            and bool(row["text"].strip())
            and ("cut" not in row or type(row["cut"]) is bool))


def _rows(world, npc_id):
    state = world.get(KEY)
    rows = state.get(npc_id) if isinstance(state, Mapping) else None
    return [row for row in rows if _row(row)] if isinstance(rows, list) else []


def repair(world: dict) -> list[str]:
    state = world.get(KEY)
    if KEY not in world:
        return []
    if not isinstance(state, dict):
        world[KEY] = {}
        return [KEY]
    changed = []
    for npc_id, rows in list(state.items()):
        clean = []
        if isinstance(npc_id, str) and npc_id and isinstance(rows, list):
            for row in rows:
                if not _row(row):
                    continue
                text = _cut(row["text"], MAX_CHARS)
                if not text.strip():
                    continue
                item = {"turn": row["turn"], "text": text}
                if row.get("cut") or len(row["text"]) > MAX_CHARS:
                    item["cut"] = True
                clean.append(item)
        clean = sorted(clean, key=lambda row: row["turn"])[-KEEP_PER_NPC:]
        if clean != rows or not clean:
            changed.append(str(npc_id))
            if clean:
                state[npc_id] = clean
            else:
                del state[npc_id]
    while len(state) > MAX_NPCS:
        oldest = min(state, key=lambda key: max(row["turn"] for row in state[key]))
        del state[oldest]
        changed.append(oldest)
        logger.info("npc_told dropped oldest NPC: %s", oldest)
    return list(dict.fromkeys(changed))


def remember(world: dict, npc_id: str, player_line: str, *, turn: int) -> bool:
    if (not isinstance(npc_id, str) or not npc_id or not isinstance(player_line, str)
            or not player_line.strip() or type(turn) is not int or turn < 0):
        return False
    text = _cut(player_line, MAX_CHARS)
    if not text.strip():
        return False
    repair(world)
    state = world.setdefault(KEY, {})
    row = {"turn": turn, "text": text}
    if len(player_line) > MAX_CHARS:
        row["cut"] = True
    state.setdefault(npc_id, []).append(row)
    repair(world)
    return True


def _stems(text):
    # Generic word segmentation and the existing fold, no vocabulary gate.
    words = "".join(c if c.isalpha() else " " for c in fold(text)).split()
    return {word[:5] for word in words if len(word) >= 4}


def _ranked(world, npc_id, text, *, uncut=False):
    stems = _stems(text)
    matches = []
    for index, row in enumerate(_rows(world, npc_id)):
        if uncut and (row.get("cut") or len(row["text"]) > MAX_CHARS):
            continue
        score = len(stems & _stems(row["text"]))
        if score:
            matches.append((score, row["turn"], index, row["text"]))
    return [entry[-1] for entry in sorted(matches, reverse=True)]


def relevant(world: Mapping, npc_id: str, text: str, limit: int = 3) -> list[str]:
    return _ranked(world, npc_id, text)[:max(0, min(limit, VIEW_ROWS))]


def context_rows(world: Mapping, npc_id: str, limit: int = 3) -> list[str]:
    rows = sorted(enumerate(_rows(world, npc_id)), key=lambda pair: (pair[1]["turn"], pair[0]), reverse=True)
    return [row["text"] for _, row in rows[:max(0, min(limit, VIEW_ROWS))]]


def supports(world: Mapping, npc_id: str, claim: str, *, about: Literal["own_words", "memory"]) -> list[str]:
    if about not in ("own_words", "memory"):
        return []
    return _ranked(world, npc_id, claim, uncut=True)


def view(rows: Sequence[str], *, header: str, max_bytes: int = 600, max_chars: int = 200) -> str:
    budget = max(0, min(max_bytes, VIEW_BYTES))
    width = max(0, min(max_chars, VIEW_CHARS) - 2)  # quote characters share the row budget
    suffix = "… (kısaltıldı; tamamı kayıtta)"
    lines = []
    for row in rows[:VIEW_ROWS]:
        text = row if len(row) <= width else _cut(row, max(0, width - len(suffix))) + suffix
        lines.append(f"«{text}»")
    dropped = max(0, len(rows) - VIEW_ROWS)
    while True:
        notice = [f"(kısaltıldı: {dropped} satır)"] if dropped else []
        text = "\n".join([header, *lines, *notice])
        if len(text.encode("utf-8")) <= budget:
            return text
        if lines:
            lines.pop()
            dropped += 1
            continue
        # A hostile/oversized header must not breach the transport budget.
        tail = "\n" + notice[0] if notice else ""
        room = max(0, budget - len(tail.encode("utf-8")))
        return (header.encode("utf-8")[:room].decode("utf-8", errors="ignore") + tail).encode("utf-8")[:budget].decode("utf-8", errors="ignore")
