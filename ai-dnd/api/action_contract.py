"""Commit-boundary contract: one receipt describes exactly the state revision that carries it (R04).

A turn's result is committed as ONE SQLite transaction (state, history, receipt). This module is the check that
transaction consumes: the receipt's digest, revision step, event ids and dice evidence must agree with the state
bundle being written. A candidate that contradicts itself is refused whole; it is never repaired by dropping the
record or rolling the dice again.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


class CommitBundleError(ValueError):
    """The receipt and the state it claims to describe contradict each other."""


@dataclass(frozen=True)
class MutationReceipt:
    key: tuple[str, str]  # (campaign_id, action_id)
    base_revision: int
    committed_revision: int
    result_digest: str
    event_ids: tuple[str, ...]
    roll_ids: tuple[str, ...]
    elapsed_s: float


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def result_digest(response: Mapping[str, Any]) -> str:
    """Digest of the stored response text, the same bytes the receipt row keeps."""
    return hashlib.sha256(canonical_json(response).encode("utf-8")).hexdigest()


def event_ids_of(response: Mapping[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    entry = response.get("combat_history_entry")
    if isinstance(entry, Mapping) and isinstance(entry.get("event_id"), str):
        ids.append(entry["event_id"])
    outcomes = response.get("quest_outcomes")
    if isinstance(outcomes, list):
        ids.extend(item["event_id"] for item in outcomes if isinstance(item, Mapping) and isinstance(item.get("event_id"), str))
    return tuple(ids)


def roll_ids_of(response: Mapping[str, Any]) -> tuple[str, ...]:
    """The engine has no roll identity; the dice evidence itself is the identity (a re-roll changes it)."""
    ids = []
    for key in ("skill_check_result", "combat_result"):
        evidence = response.get(key)
        if isinstance(evidence, Mapping):
            ids.append(f"{key}:{hashlib.sha256(canonical_json(evidence).encode('utf-8')).hexdigest()[:16]}")
    return tuple(ids)


def committed_facts(public_state: Mapping[str, Any]) -> dict[str, Any]:
    """What the public projection shows a player losing or gaining: HP, items, clock, death and the turn counter.

    Money is world_state['currency'] and is not part of the public projection, so a receipt cannot contradict it;
    its all-or-nothing commit is the single transaction that also writes the payload (see the R04 integration test).
    """
    character = public_state.get("character") if isinstance(public_state.get("character"), Mapping) else {}
    death = public_state.get("death_state") if isinstance(public_state.get("death_state"), Mapping) else {}
    return {
        "hp": (character.get("current_hp"), character.get("max_hp")),
        "inventory": public_state.get("inventory"),
        "time": public_state.get("campaign_time"),
        "death": (death.get("status"), death.get("dead"), death.get("successes"), death.get("failures")),
        "turn_index": public_state.get("turn_index"),
    }


def build_receipt(
    campaign_id: str,
    action_id: str,
    response: Mapping[str, Any],
    base_revision: int,
    committed_revision: int,
    elapsed_s: float,
) -> MutationReceipt:
    return MutationReceipt(
        key=(campaign_id, action_id),
        base_revision=base_revision,
        committed_revision=committed_revision,
        result_digest=result_digest(response),
        event_ids=event_ids_of(response),
        roll_ids=roll_ids_of(response),
        elapsed_s=elapsed_s,
    )


def validate_commit_bundle(state: Mapping[str, Any], receipt: MutationReceipt) -> None:
    """Raise CommitBundleError unless receipt and state describe the same single revision.

    `state` is the state side of the bundle: `public_state` (projected from the live session at commit time),
    `response` (the receipt body) and `committed_event_ids` (event rows written in the same transaction).
    """
    response = state.get("response")
    public_state = state.get("public_state")
    if not isinstance(response, Mapping) or not isinstance(public_state, Mapping):
        raise CommitBundleError("Commit bundle is incomplete.")
    if receipt.committed_revision != receipt.base_revision + 1:
        raise CommitBundleError("Receipt does not describe exactly one new revision.")
    if result_digest(response) != receipt.result_digest:
        raise CommitBundleError("Receipt digest does not match the stored result.")
    receipt_state = response.get("state")
    if not isinstance(receipt_state, Mapping) or committed_facts(receipt_state) != committed_facts(public_state):
        raise CommitBundleError("Receipt state contradicts the state being committed.")
    if receipt.event_ids != event_ids_of(response):
        raise CommitBundleError("Receipt events do not match the result.")
    written = set(state.get("committed_event_ids") or ())
    if not set(receipt.event_ids).issubset(written):
        raise CommitBundleError("Receipt names an event that was not committed with it.")
    if receipt.roll_ids != roll_ids_of(response):
        raise CommitBundleError("Receipt dice evidence does not match the result.")
