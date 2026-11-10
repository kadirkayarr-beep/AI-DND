"""The undo as the player reads it: the undo sentence and the read-time undo flags of the story history.

Pure, standard library only. Nothing here is saved: `campaign_store.get_campaign` derives the flags on every read
from the committed receipts (decision 31), so the strict `campaign_history` format never changes. A row is an undo
only when an undo receipt proves it (decision 36): the player may type the marker text, and it stays their words.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

# The player line the undo route writes into the history (main.py imports this; it is the only spelling).
UNDO_HISTORY_MARKER = "↶ Son turu geri al"

# The player line a joined ambient event writes into the history (ambient_actions.JOIN_LINE; a test keeps them equal).
AMBIENT_JOIN_LINE = "Yanlarına gidiyorum."

_UNDO_TAIL = "Dünya o turdan önceki hâline döndü; sıradaki hamle senin."


def _purse_sentence(purse_delta_cp: int | None) -> str:
    """How the purse moved back (after the undo minus before it); nothing when it did not move."""
    if type(purse_delta_cp) is not int or purse_delta_cp == 0:
        return ""
    if purse_delta_cp > 0:
        return f"Kesene {purse_delta_cp} bakır geri döndü. "
    return f"Kesenden {-purse_delta_cp} bakır geri alındı. "


def undo_narration(player_message: str, purse_delta_cp: int | None = None, turn_label: str | None = None) -> str:
    """The undo sentence. A slash command (or nothing) is never quoted: the player never reads a raw command.

    `turn_label` names a turn whose player words are fixed (a card's "Teklifi onayla"): the engine's own summary.
    """
    label = str(turn_label or "").strip().rstrip(".")
    quoted = label or str(player_message or "").strip()
    purse = _purse_sentence(purse_delta_cp)
    if not quoted or quoted.startswith("/"):
        return f"Son tur geri alındı; o turda olanlar yaşanmamış sayılıyor. {purse}{_UNDO_TAIL}"
    if len(quoted) > 120:
        quoted = quoted[:117] + "..."
    return f"Son tur geri alındı: “{quoted}” ve sonuçları yaşanmamış sayılıyor. {purse}{_UNDO_TAIL}"


def _single(indexes: list[int]) -> int | None:
    return indexes[0] if len(indexes) == 1 else None


def undo_links(rows: list[dict[str, Any]], receipts: list[dict[str, Any]]) -> dict[int, int | None]:
    """Map each receipt-proven undo row to the row it undid, or to None when that turn cannot be proven.

    `rows` are the history rows in sequence order ({player_message, narration, created_at}); `receipts` are the
    live receipts in commit order ({action_id, created_at, response}; `response` is the decoded receipt or None).
    A row and its receipt are written in one transaction with the same `created_at` and the same narration, and
    `created_at` has one-second resolution, so every match must have exactly one candidate. Nothing is guessed:
    there is no "the row before the undo" rule, and an ambiguous or doubled link marks no turn as undone.
    """
    claims: dict[int, list[dict[str, Any]]] = {}
    for undo in receipts:
        response = undo.get("response")
        if not isinstance(response, dict) or not isinstance(response.get("undone_action_id"), str):
            continue
        marker = _single([
            index for index, row in enumerate(rows)
            if row.get("player_message") == UNDO_HISTORY_MARKER
            and row.get("created_at") == undo.get("created_at")
            and row.get("narration") == response.get("narration")
        ])
        if marker is not None:
            claims.setdefault(marker, []).append(response)
    links: dict[int, int | None] = {}
    for marker, responses in claims.items():
        if len(responses) != 1:
            continue  # two undo receipts claim one row: that row is not proven
        targets = [receipt for receipt in receipts if receipt.get("action_id") == responses[0]["undone_action_id"]]
        target = targets[0] if len(targets) == 1 else None
        target_response = target.get("response") if target is not None else None
        turn = None
        if isinstance(target_response, dict) and "ambient_event_response" in target_response:
            # A click's receipt keeps no narration (its format is kept byte for byte): its row is the one the click
            # wrote in the same transaction, the join line at the receipt's own time.
            turn = _single([
                index for index, row in enumerate(rows[:marker])
                if row.get("player_message") == AMBIENT_JOIN_LINE
                and row.get("created_at") == target.get("created_at")
            ])
        elif isinstance(target_response, dict):
            turn = _single([
                index for index, row in enumerate(rows[:marker])
                if row.get("player_message") != UNDO_HISTORY_MARKER
                and row.get("created_at") == target.get("created_at")
                and row.get("narration") == target_response.get("narration")
            ])
        links[marker] = turn
    # Two proven undos naming one turn (a double target): neither is resolved by guess.
    counts = Counter(turn for turn in links.values() if turn is not None)
    return {marker: (None if turn is not None and counts[turn] > 1 else turn) for marker, turn in links.items()}


def mark_undone(history: list[dict[str, Any]], links: dict[int, int | None]) -> list[dict[str, Any]]:
    """A copy of `history` with the read-time flags: `undo_note` on proven undo rows (and `undo_target_unknown` when
    the undone turn is not proven), `undone` on the proven undone turns. Every other row is copied unchanged."""
    undone = {turn for turn in links.values() if turn is not None}
    marked = []
    for index, entry in enumerate(history):
        copied = dict(entry)
        if index in links:
            copied["undo_note"] = True
            if links[index] is None:
                copied["undo_target_unknown"] = True
        if index in undone:
            copied["undone"] = True
        marked.append(copied)
    return marked
