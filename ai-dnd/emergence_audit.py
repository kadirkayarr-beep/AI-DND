"""Emergence debug traces. Operational evidence only.

Never canon, never on GameState, and never the store for generation attempts.
Dropping an audit row does not reopen a trigger.
"""

from __future__ import annotations

import json

MAX_RECORDS = 200
MAX_TOTAL_BYTES = 256 * 1024
MAX_RECORD_BYTES = 4096

FIELDS = (
    "trigger_id", "attempt_id", "incident_id", "model_id",
    "prompt_contract_version", "envelope_version", "envelope_hash",
    "proposal_schema_version", "gate_policy_version", "gate_outcome",
    "status", "rejection_reason", "model_call_count",
)


def _size(entry):
    return len(json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def record(ring, entry):
    """Append metadata only, then drop the oldest rows past either cap."""
    kept = {key: entry.get(key) for key in FIELDS}
    if _size(kept) > MAX_RECORD_BYTES:
        kept = {key: kept[key] for key in ("trigger_id", "attempt_id", "status", "model_call_count")}
        kept["truncated"] = True
    ring.append(kept)
    while len(ring) > MAX_RECORDS:
        ring.pop(0)
    while ring and sum(_size(item) for item in ring) > MAX_TOTAL_BYTES:
        ring.pop(0)
    return kept


def ring_for(session):
    """Per-session ring. It is not saved and not projected."""
    ring = getattr(session, "emergence_audit", None)
    if not isinstance(ring, list):
        ring = []
        session.emergence_audit = ring
    return ring
