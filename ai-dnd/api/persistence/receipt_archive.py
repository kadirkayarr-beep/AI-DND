"""Receipt archive (R08): verified idempotency tombstones that replace old full receipts.

An archived action keeps exactly what makes a retry safe and a history card reproducible: the action id, the request
hash, the digest of the original reply, the revision step, and the small player-visible skill result bound to its
history turn. The full reply is dropped. A retry of an archived id is refused as "already applied"; it is never
re-executed and never treated as a new action. There is no blind TTL deletion: only rows already committed at an
older revision are archived, and a row that cannot be verified is left exactly where it is.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

ARCHIVE_DDL = """
    CREATE TABLE IF NOT EXISTS campaign_turn_actions_archive (
        campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        action_id TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        result_digest TEXT NOT NULL,
        base_revision INTEGER,
        committed_revision INTEGER,
        turn_index INTEGER,
        narration_digest TEXT,
        skill_json TEXT,
        archived_at TEXT NOT NULL,
        PRIMARY KEY (campaign_id, action_id)
    )
"""
ARCHIVE_COLUMNS = {
    "campaign_id", "action_id", "request_hash", "result_digest", "base_revision", "committed_revision",
    "turn_index", "narration_digest", "skill_json", "archived_at",
}
_HEX = set("0123456789abcdef")


def is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tombstone_from_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build the tombstone for one stored receipt, or None if the row cannot be verified (it is then left untouched)."""
    try:
        response_text = str(row["response_json"])
        response = json.loads(response_text)
        action_id = row["action_id"]
        if not isinstance(response, dict) or response.get("action_id") != action_id or not is_sha256_hex(row["request_hash"]):
            return None
        digest = text_digest(response_text)
        if row["result_digest"] is not None and row["result_digest"] != digest:
            return None
        state = response.get("state")
        turn_index = state.get("turn_index") if isinstance(state, dict) else None
        narration = response.get("narration")
        skill = response.get("skill_check_result")
        keep_skill = isinstance(skill, dict) and skill.get("action_id") == action_id
        return {
            "request_hash": row["request_hash"],
            "result_digest": digest,
            "base_revision": row["base_revision"],
            "committed_revision": row["committed_revision"],
            "turn_index": turn_index if type(turn_index) is int else None,
            "narration_digest": text_digest(narration) if isinstance(narration, str) else None,
            "skill_json": json.dumps(skill, ensure_ascii=False, separators=(",", ":")) if keep_skill else None,
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def has_open_reaction(value: Any, depth: int = 0) -> bool:
    """True when the saved world still waits on a reaction; the receipt that opened it must stay whole."""
    if depth > 12:
        return False
    if isinstance(value, Mapping):
        if value.get("pending_reaction"):
            return True
        return any(has_open_reaction(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        return any(has_open_reaction(item, depth + 1) for item in value)
    return False
