"""Test-side archiving of live action receipts into verified tombstones.

The production writer was removed (D-536). The archive is still read by
`get_turn_action`, `get_campaign` and the open-intent check; tests that need
archived rows put them there directly, as the removed writer did.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from api.persistence import receipt_archive

_LIVE = (
    "SELECT action_id, request_hash, response_json, base_revision, "
    "committed_revision, created_at FROM campaign_turn_actions "
    "WHERE campaign_id = ? AND committed_revision IS NOT NULL "
    "ORDER BY committed_revision, rowid"
)
_STORY_ROW = (
    "SELECT sequence FROM campaign_history "
    "WHERE campaign_id = ? AND created_at = ? AND narration = ?"
)
_ARCHIVE = (
    "INSERT INTO campaign_turn_actions_archive (campaign_id, action_id, "
    "request_hash, result_digest, base_revision, committed_revision, "
    "turn_index, narration_digest, skill_json, archived_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def archive_receipts(db_path: str, campaign_id: str, keep_latest: int = 0) -> int:
    """Archive every committed receipt but the newest `keep_latest`; count them."""
    with closing(sqlite3.connect(db_path)) as db:
        rows = db.execute(_LIVE, (campaign_id,)).fetchall()
        older = rows[: len(rows) - keep_latest]
        for row in older:
            action_id, request_hash, text, base, committed, created_at = row
            narration = json.loads(text).get("narration")
            skill = json.loads(text).get("skill_check_result")
            story = db.execute(_STORY_ROW, (campaign_id, created_at, narration))
            sequences = story.fetchall()
            db.execute(_ARCHIVE, (
                campaign_id, action_id, request_hash,
                receipt_archive.text_digest(text), base, committed,
                sequences[0][0] if len(sequences) == 1 else None,
                receipt_archive.text_digest(narration)
                if isinstance(narration, str) else None,
                json.dumps(skill, ensure_ascii=False, separators=(",", ":"))
                if isinstance(skill, dict) else None,
                "2026-11-26T00:00:00+00:00",
            ))
            db.execute(
                "DELETE FROM campaign_turn_actions "
                "WHERE campaign_id = ? AND action_id = ?",
                (campaign_id, action_id),
            )
        db.commit()
    return len(older)
