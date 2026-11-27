"""Receipt archive (R08): verified idempotency tombstones that replace old full receipts.

An archived action keeps exactly what makes a retry safe and a history card reproducible: the action id, the request
hash, the digest of the original reply, the revision step, and the small player-visible skill result bound to its
history turn. The full reply is dropped. A retry of an archived id is refused as "already applied"; it is never
re-executed and never treated as a new action. There is no blind TTL deletion: only rows already committed at an
older revision are archived, and a row that cannot be verified is left exactly where it is.
"""
from __future__ import annotations

import hashlib
from typing import Any

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
