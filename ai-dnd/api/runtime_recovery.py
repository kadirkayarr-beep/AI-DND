"""Verified restore of a trusted runtime snapshot (R05).

A session is usable only while its live runtime is known to equal a trusted snapshot. A restore that raises, or that
"succeeds" but leaves a state different from the snapshot, closes the session; nothing here guesses or repairs user
data. Recovery after that is a new process resuming durable truth (see SessionManager.resume_campaign).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def state_digest(state: Any) -> str:
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def restore_trusted_runtime(record: Any, snapshot: dict[str, Any], restore: Any = None) -> bool:
    """Restore `snapshot` into the record's session; True only if the result provably equals the snapshot.

    `record.usable` is set from that verification and nowhere else: a failed or unverifiable restore leaves it False.
    """
    session = record.game_session
    try:
        if restore is None:
            session._restore_runtime_snapshot(snapshot["runtime"])
        else:
            restore(session, snapshot)  # the caller's own restore seam (main._restore_session)
        verified = state_digest(session.serialize_game_state()) == state_digest(snapshot["save"])
        capture = getattr(session, "_capture_runtime_snapshot", None)
        if verified and callable(capture) and isinstance(snapshot.get("runtime"), dict):
            # The save omits dice, messages and pending XP; a restore that silently skipped them is not trusted.
            verified = state_digest(capture()) == state_digest(snapshot["runtime"])
    except Exception:
        verified = False
    record.usable = verified
    return verified
