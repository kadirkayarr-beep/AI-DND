"""Durable generation attempts. Operational receipts, never campaign canon.

One (campaign_id, trigger_id) gets at most one model proposal. The claim is
insert-first; a loser reads the existing row and does not call the model.
"""

from __future__ import annotations

import copy
import hashlib
import threading
import uuid
from dataclasses import dataclass

import emergence_audit
from incidents import envelope as envelope_owner
from incidents import gate as gate_owner
from incidents import untrusted, versions
from incidents.proposal import MAX_PROPOSAL_BYTES

TERMINAL = ("accepted", "rejected", "stale", "no_proposal")
OPEN = ("claiming", "proposal_stored")

# One token per process. A crashed process never comes back with it.
PROCESS_TOKEN = uuid.uuid4().hex


def new_row(campaign_id, envelope, *, model_id):
    return {
        "campaign_id": campaign_id,
        "trigger_id": envelope["trigger_id"],
        "attempt_id": "att." + uuid.uuid4().hex,
        "owner_token": PROCESS_TOKEN,
        "canon_stamp": envelope["canon_stamp"],
        "model_id": model_id,
        "prompt_contract_version": versions.PROMPT_CONTRACT_VERSION,
        "envelope_version": envelope["envelope_version"],
        "envelope_hash": envelope_owner.envelope_hash(envelope),
        "proposal_schema_version": versions.PROPOSAL_SCHEMA_VERSION,
        "gate_policy_version": versions.GATE_POLICY_VERSION,
        "incident_schema_version": versions.INCIDENT_SCHEMA_VERSION,
    }


class MemoryAttemptStore:
    """Same contract as the SQLite table, for sessions without a campaign row."""

    def __init__(self):
        self._rows = {}
        self._lock = threading.Lock()

    def claim(self, row):
        key = (row["campaign_id"], row["trigger_id"])
        with self._lock:
            if key in self._rows:
                return False, copy.deepcopy(self._rows[key])
            stored = dict(
                row, status="claiming", proposal_json=None, proposal_hash=None,
                incident_id=None, gate_outcome=None, rejection_reason=None,
                model_call_count=0, created_at=None, completed_at=None,
            )
            self._rows[key] = stored
            return True, copy.deepcopy(stored)

    def update(self, campaign_id, trigger_id, owner_token, expected, fields):
        with self._lock:
            row = self._rows.get((campaign_id, trigger_id))
            if row is None or row["owner_token"] != owner_token or row["status"] not in expected:
                return False
            row.update(copy.deepcopy(fields))
            return True

    def get(self, campaign_id, trigger_id):
        with self._lock:
            row = self._rows.get((campaign_id, trigger_id))
            return copy.deepcopy(row) if row else None

    def compact(self, campaign_id):
        count = 0
        with self._lock:
            for (owner, _), row in self._rows.items():
                if owner == campaign_id and row["status"] in TERMINAL and row["proposal_json"] is not None \
                        and row["proposal_hash"] is not None:
                    row["proposal_json"] = None
                    count += 1
        return count

    # A memory store has no autosave transaction, so accept finishes directly.
    def finish_accepted(self, pending):
        return self.update(
            pending["campaign_id"], pending["trigger_id"], pending["owner_token"],
            ("proposal_stored",),
            {"status": "accepted", "incident_id": pending["incident_id"],
             "gate_outcome": pending["gate_outcome"]},
        )


class SqliteAttemptStore:
    """Adapter over the one SQLite owner, campaign_store."""

    def __init__(self, campaign_store):
        self._store = campaign_store

    def claim(self, row):
        return self._store.claim_emergence_attempt(row)

    def update(self, campaign_id, trigger_id, owner_token, expected, fields):
        return self._store.update_emergence_attempt(campaign_id, trigger_id, owner_token, tuple(expected), fields)

    def get(self, campaign_id, trigger_id):
        return self._store.get_emergence_attempt(campaign_id, trigger_id)

    def compact(self, campaign_id):
        return self._store.compact_emergence_attempts(campaign_id)

    # Accepted rows finish inside save_campaign so a failed autosave leaves the
    # row at proposal_stored, and a retry replays the stored proposal.
    def finish_accepted(self, pending):
        return None


@dataclass
class AttemptOutcome:
    status: str
    model_calls: int
    gate_result: gate_owner.GateResult | None = None
    reason: str | None = None
    pending_finish: dict | None = None
    row: dict | None = None


def _finish(store, row, status, *, reason=None, gate_outcome=None, calls=None):
    fields = {"status": status, "rejection_reason": reason, "gate_outcome": gate_outcome}
    if calls is not None:
        fields["model_call_count"] = calls
    store.update(row["campaign_id"], row["trigger_id"], row["owner_token"], OPEN, fields)


def _audit(audit, row, outcome):
    if audit is None:
        return
    emergence_audit.record(audit, {
        "trigger_id": row["trigger_id"],
        "attempt_id": row["attempt_id"],
        "incident_id": row.get("incident_id"),
        "model_id": row["model_id"],
        "prompt_contract_version": row["prompt_contract_version"],
        "envelope_version": row["envelope_version"],
        "envelope_hash": row["envelope_hash"],
        "proposal_schema_version": row["proposal_schema_version"],
        "gate_policy_version": row["gate_policy_version"],
        "gate_outcome": outcome.gate_result.outcome if outcome.gate_result else None,
        "status": outcome.status,
        "rejection_reason": outcome.reason,
        "model_call_count": outcome.model_calls,
    })


def run(store, *, campaign_id, envelope, world, propose, model_id, player_text="",
        lore_state=None, audit=None):
    """One attempt for one trigger. ``propose(packet) -> str`` is called at most once.

    Returns ``ready`` with a gate result the caller may commit, or a quiet status.
    The caller writes canon. This function never does.
    """
    won, row = store.claim(new_row(campaign_id, envelope, model_id=model_id))
    calls = 0
    raw = None
    if not won:
        if row["status"] != "proposal_stored" or row["proposal_json"] is None:
            outcome = AttemptOutcome("consumed", 0, reason=row["status"], row=row)
            _audit(audit, row, outcome)
            return outcome
        # A stored proposal from a dead owner is replayed, never regenerated.
        if row["canon_stamp"] != envelope["canon_stamp"] or not store.update(
            campaign_id, row["trigger_id"], row["owner_token"], ("proposal_stored",),
            {"owner_token": PROCESS_TOKEN},
        ):
            outcome = AttemptOutcome("consumed", 0, reason="proposal_stored", row=row)
            _audit(audit, row, outcome)
            return outcome
        row["owner_token"] = PROCESS_TOKEN
        raw = row["proposal_json"]
    else:
        packet = untrusted.attach(envelope, player_text)
        try:
            calls = 1
            raw = propose(packet)
        except Exception:
            raw = None
        if not isinstance(raw, str):
            _finish(store, row, "no_proposal", reason="no_response", calls=calls)
            outcome = AttemptOutcome("no_proposal", calls, reason="no_response", row=row)
            _audit(audit, row, outcome)
            return outcome
        proposal_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if len(raw.encode("utf-8")) > MAX_PROPOSAL_BYTES:
            store.update(campaign_id, row["trigger_id"], row["owner_token"], OPEN,
                         {"proposal_hash": proposal_hash, "model_call_count": calls})
            _finish(store, row, "no_proposal", reason="oversize")
            outcome = AttemptOutcome("no_proposal", calls, reason="oversize", row=row)
            _audit(audit, row, outcome)
            return outcome
        store.update(campaign_id, row["trigger_id"], row["owner_token"], ("claiming",), {
            "status": "proposal_stored", "proposal_json": raw,
            "proposal_hash": proposal_hash, "model_call_count": calls,
        })

    if envelope_owner.is_stale(world, envelope, lore_state):
        _finish(store, row, "stale", reason="canon_stamp")
        outcome = AttemptOutcome("stale", calls, reason="canon_stamp", row=row)
        _audit(audit, row, outcome)
        return outcome
    result = gate_owner.evaluate(envelope, raw)
    if result.outcome == gate_owner.HARD_REJECT:
        _finish(store, row, "rejected", reason=result.reason, gate_outcome=result.outcome)
        outcome = AttemptOutcome("rejected", calls, gate_result=result, reason=result.reason, row=row)
        _audit(audit, row, outcome)
        return outcome
    outcome = AttemptOutcome(
        "ready", calls, gate_result=result, row=row,
        pending_finish={
            "campaign_id": campaign_id, "trigger_id": row["trigger_id"],
            "owner_token": row["owner_token"], "incident_id": None,
            "gate_outcome": result.outcome,
        },
    )
    _audit(audit, row, outcome)
    return outcome
