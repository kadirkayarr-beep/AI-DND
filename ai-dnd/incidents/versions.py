"""Frozen generative contract versions.

An accepted incident keeps the versions that created it. Loading dispatches
on that tuple and never reruns the current envelope, proposal, or gate policy.
"""

from __future__ import annotations

import copy

VERSION_FIELDS = (
    "incident_schema_version",
    "envelope_version",
    "proposal_schema_version",
    "gate_policy_version",
)

INCIDENT_SCHEMA_VERSION = 1
ENVELOPE_VERSION = 1
PROPOSAL_SCHEMA_VERSION = 1
GATE_POLICY_VERSION = 1
PROMPT_CONTRACT_VERSION = 1


def current():
    """The tuple a newly accepted incident freezes."""
    return {
        "incident_schema_version": INCIDENT_SCHEMA_VERSION,
        "envelope_version": ENVELOPE_VERSION,
        "proposal_schema_version": PROPOSAL_SCHEMA_VERSION,
        "gate_policy_version": GATE_POLICY_VERSION,
    }


def _as_stored(record):
    return copy.deepcopy(record)


# Readers for every tuple this server understands. A later policy adds a new
# key here and, when the stored shape must grow, an additive migration that
# only fills defaulted fields. Premise, ids, reward class, hidden-fact ids,
# and lifecycle are never rewritten.
SUPPORTED = {
    (1, 1, 1, 1): _as_stored,
}


def version_tuple(record, fail):
    values = []
    for field in VERSION_FIELDS:
        value = record.get(field) if isinstance(record, dict) else None
        if type(value) is not int or value < 1:
            fail()
        values.append(value)
    return tuple(values)


def load_record(record, fail):
    """Return the record read by the loader for its frozen tuple."""
    loader = SUPPORTED.get(version_tuple(record, fail))
    if loader is None:
        fail()
    return loader(record)
