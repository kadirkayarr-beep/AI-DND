"""Disposable real-Qwen 36-turn smoke for Playable Living World V1.

This is intentionally separate from the historical canon smoke reports.  It
starts a real API subprocess against a newly-created temporary SQLite file,
plays exactly 24 turns, restarts the process, resumes the same campaign, and
plays turns 25--36.  No engine fixtures or model/parser mocks are used.

Run from ``ai-dnd`` with::

    python -m api.tests.live_playable_living_world_v1_smoke

The script is a release-gate harness, not a deterministic unit test.  Missing
model credentials, unavailable generated scene entities, or an unmet normal
play invariant are reported as FAIL/BLOCKED rather than hidden.
"""

from __future__ import annotations

import ast
import copy
import contextvars
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid

import httpx

from api.tests.playable_living_world_v1_review import (
    ReviewFinalizationError,
    finalize_review,
)


_REQUEST_TELEMETRY: contextvars.ContextVar[list[dict[str, Any]] | None] = (
    contextvars.ContextVar("playable_v1_request_telemetry", default=None)
)
_VALIDATION_OUTPUT_CALLS: contextvars.ContextVar[dict[int, int] | None] = (
    contextvars.ContextVar("playable_v1_validation_output_calls", default=None)
)


def _numeric(response: Any, name: str) -> int | None:
    value = response.get(name) if isinstance(response, dict) else getattr(response, name, None)
    return value if type(value) is int and value >= 0 else None


def _proposal_count(source: Any, field: str) -> int | None:
    if not isinstance(source, dict):
        return None
    if field not in source:
        return 0
    value = source.get(field)
    return len(value) if isinstance(value, list) else None


def _proposal_key_hash(salt: str, category: str, key: Any) -> str:
    value = key if isinstance(key, str) and key else "missing"
    digest = hashlib.sha256(
        f"{salt}\x00{category}\x00{value}".encode("utf-8")
    ).hexdigest()
    return digest[:16]


def _safety_scope(handling: Any) -> str:
    return {
        "accepted": "none",
        "repaired": "single_trigger_sentence_removed",
        "python_fallback": "whole_response_replacement",
        "python_memory_response": "whole_response_deterministic_memory",
        "python_memory_fallback": "whole_response_memory_contradiction_fallback",
        "python_scene_response": "direct_scene_response",
    }.get(handling, "unavailable")


def _is_fallback_candidate(safety: Any) -> bool:
    if not isinstance(safety, dict):
        return False
    tier = safety.get("tier")
    if tier == "tier_2_repair":
        return True
    if tier != "tier_3_fallback":
        return False
    # Direct engine-owned scene and memory responses are expected outcomes,
    # not narration-safety fallbacks, despite sharing the generic tier label.
    return safety.get("handling") not in {
        "python_scene_response",
        "python_memory_response",
    }


def _telemetry() -> list[dict[str, Any]] | None:
    return _REQUEST_TELEMETRY.get()


_SMOKE_DIAGNOSTIC_PATH: Path | None = None
_REPLAY_CHECKPOINT_FORMAT = "ai-dnd-smoke-replay-checkpoint"
_REPLAY_CHECKPOINT_VERSION = 1


class SmokeReplayError(ValueError):
    """A replay checkpoint is missing, canonical, or not a disposable copy."""


def _redact_diagnostic_text(value: str) -> str:
    """Drop connection secrets from diagnostic text. Keep the error type only."""
    lowered = value.casefold()
    if any(marker in lowered for marker in ("bearer ", "token=", "ollama_proxy", "authorization")):
        return "sensitive detail redacted"
    return value


def _redact_diagnostic_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_diagnostic_text(value)
    if isinstance(value, list):
        return [_redact_diagnostic_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _redact_diagnostic_value(item)
            for key, item in value.items()
        }
    return value


def _flush_diagnostic(event: dict[str, Any]) -> None:
    """Append one sanitized diagnostic line before a call can hang."""
    path = _SMOKE_DIAGNOSTIC_PATH
    if path is None:
        return
    safe = _sanitize_persistent_value(_redact_diagnostic_value(event))
    if not isinstance(safe, dict):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(safe, ensure_ascii=False, allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _message_request_shape(messages: Any) -> tuple[int | None, int | None]:
    if not isinstance(messages, list):
        return None, None
    try:
        encoded = json.dumps(messages, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return None, len(messages)
    return len(encoded), len(messages)


def _call_role(messages: Any) -> str:
    if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
        return "unavailable"
    content = messages[0].get("content")
    if (
        messages[0].get("role") == "system"
        and isinstance(content, str)
        and content.startswith("You are a small D&D intent parser")
    ):
        return "intent"
    if messages[0].get("role") == "system" and isinstance(content, str):
        return "narration"
    return "unavailable"


def _schema_narration_only(schema: Any) -> bool | None:
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None
    world_updates = properties.get("world_updates")
    lore_claims = properties.get("lore_claims")
    if not isinstance(world_updates, dict) or not isinstance(lore_claims, dict):
        return None
    fields = world_updates.get("properties")
    if not isinstance(fields, dict):
        return None
    watched = (
        "create_locations", "create_npcs", "update_npcs",
        "create_features", "events", "create_shops",
    )
    if any(name not in fields or not isinstance(fields[name], dict) for name in watched):
        return None
    if type(lore_claims.get("maxItems")) is not int:
        return None
    limited = all(fields[name].get("maxItems") == 0 for name in watched)
    return limited and lore_claims.get("maxItems") == 0


def _active_scene_type(game: Any) -> str | None:
    session = game._ACTIVE_SESSION.get()
    world = getattr(session, "world_state", None) if session is not None else None
    if not isinstance(world, dict):
        return None
    try:
        import living_world
        kind = living_world.scene_kind(world, world.get("location"))
    except Exception:
        return None
    return kind if isinstance(kind, str) else None


def _selected_context_counts(game: Any) -> dict[str, int] | None:
    session = game._ACTIVE_SESSION.get()
    context = getattr(session, "lore_authority_context", None) if session is not None else None
    if not isinstance(context, dict):
        return None
    sections = context.get("sections")
    if not isinstance(sections, dict):
        return None
    counts: dict[str, int] = {}
    for key, value in sections.items():
        if not isinstance(key, str) or not isinstance(value, list):
            return None
        counts[key] = len(value)
    return counts


def build_replay_checkpoint(record: Any) -> dict[str, Any]:
    """Capture disposable session state. This is not a shareable sanitized report."""
    from api.persistence.campaign_validation import (
        ensure_no_configured_secrets,
        serialize_campaign_payload,
    )

    session = record.game_session
    payload = serialize_campaign_payload(
        session,
        record.journal,
        record.narrative_memory,
        record.lore_authority,
    )
    messages = getattr(session, "messages", None)
    if not isinstance(messages, list):
        raise SmokeReplayError("Replay checkpoint is missing conversation messages.")
    checkpoint = {
        "format": _REPLAY_CHECKPOINT_FORMAT,
        "version": _REPLAY_CHECKPOINT_VERSION,
        "campaign_payload": payload,
        "messages": copy.deepcopy(messages),
        "combat_history": copy.deepcopy(getattr(record, "combat_history", [])),
    }
    ensure_no_configured_secrets(checkpoint)
    return checkpoint


def private_replay_directory(report_root: Path) -> Path:
    """Keep raw checkpoints outside the sanitized smoke report directory."""
    parent = report_root.parent
    if parent.name.endswith("-smokes"):
        private_parent = parent.parent / (
            parent.name.removesuffix("-smokes") + "-private-replay"
        )
    else:
        private_parent = parent / "private-replay"
    return private_parent / report_root.name


def write_replay_checkpoint(record: Any, directory: Path) -> Path:
    checkpoint = build_replay_checkpoint(record)
    directory.mkdir(parents=True, exist_ok=True)
    world = record.game_session.world_state
    flags = world.get("flags", {}) if isinstance(world, dict) else {}
    turn_index = flags.get("turn_index") if isinstance(flags, dict) else None
    name = f"after-turn-{turn_index}.json" if type(turn_index) is int else "after-turn-unknown.json"
    path = directory / name
    text = json.dumps(checkpoint, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def load_replay_checkpoint_copy(path: Path) -> tuple[dict[str, Any], Path]:
    """Load a copy. Canonical engine and campaign saves are refused."""
    raw_text = path.read_text(encoding="utf-8")
    raw = json.loads(raw_text)
    if not isinstance(raw, dict) or raw.get("format") != _REPLAY_CHECKPOINT_FORMAT:
        raise SmokeReplayError("Replay refused a canonical or unknown save.")
    if raw.get("version") != _REPLAY_CHECKPOINT_VERSION:
        raise SmokeReplayError("Replay checkpoint version is unsupported.")
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", delete=False,
    )
    copy_path = Path(handle.name)
    try:
        handle.write(raw_text)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    loaded = json.loads(copy_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise SmokeReplayError("Replay checkpoint copy is unusable.")
    return loaded, copy_path


def restore_replay_checkpoint(session: Any, loaded: dict[str, Any]) -> dict[str, Any]:
    from api.persistence.campaign_validation import restore_campaign_session

    payload = loaded.get("campaign_payload")
    messages = loaded.get("messages")
    if not isinstance(payload, dict) or not isinstance(messages, list):
        raise SmokeReplayError("Replay checkpoint is missing session state.")
    journal = restore_campaign_session(session, payload)
    session.messages = copy.deepcopy(messages)
    return {
        "journal": journal,
        "narrative_memory": copy.deepcopy(payload.get("narrative_memory")),
        "lore_authority": copy.deepcopy(payload.get("lore_authority")),
        "combat_history": copy.deepcopy(loaded.get("combat_history")),
        "rng_state": copy.deepcopy(payload.get("rng_state")),
        "messages": session.messages,
    }


def write_failure_evidence(report_root: Path, event: dict[str, Any]) -> Path:
    """Record a failure without replacing an earlier stage record."""
    path = report_root / "failure-evidence.json"
    safe = _sanitize_persistent_value(_redact_diagnostic_value(event))
    if not isinstance(safe, dict):
        safe = {"event": "failure", "phase": "unavailable"}
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            existing = loaded
    if not existing:
        merged = safe
    else:
        merged = dict(existing)
        supplements = [
            item for item in merged.get("supplements", [])
            if isinstance(item, dict)
        ]
        same_stage = (
            safe.get("event") == existing.get("event")
            and safe.get("phase") == existing.get("phase")
        )
        if not same_stage:
            supplements.append({
                key: value for key, value in safe.items() if key != "rollback"
            })
        merged["supplements"] = supplements
        if safe.get("rollback") == "observed" or existing.get("rollback") is None:
            merged["rollback"] = safe.get("rollback")
        if "rollback_comparison" in safe:
            merged["rollback_comparison"] = safe["rollback_comparison"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def probe_rollback_status(
    base: str,
    session_id: str,
    expected_turn_index: int | None,
) -> dict[str, Any]:
    """Read turn identity if the isolated API answers. A hung turn stays unverified."""
    unverified = {"rollback": "rollback doğrulanamadı"}
    if not base or not session_id:
        return unverified
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{base}/api/sessions/{session_id}/state")
    except Exception:
        return unverified
    if response.status_code != 200:
        return unverified
    try:
        payload = response.json()
    except Exception:
        return unverified
    if not isinstance(payload, dict):
        return unverified
    observed = payload.get("turn_index")
    location = payload.get("location")
    scene = payload.get("scene")
    scene_kind = scene.get("kind") if isinstance(scene, dict) else None
    return {
        "rollback": "observed",
        "rollback_comparison": {
            "observed_turn_index": observed if type(observed) is int else None,
            "expected_turn_index": expected_turn_index,
            "location_id": location if isinstance(location, str) else None,
            "scene_kind": scene_kind if isinstance(scene_kind, str) else None,
            "turn_index_unchanged": (
                observed == expected_turn_index
                if type(observed) is int and type(expected_turn_index) is int
                else None
            ),
        },
    }


def capture_isolated_failure(
    report_root: Path,
    handle: Any,
    *,
    base: str,
    session_id: str,
    evidence_rows: list[dict[str, Any]],
) -> None:
    """Save sanitized logs and a rollback probe before the isolated API stops."""
    if handle is not None:
        try:
            handle.seek(0)
            raw_log = handle.read().decode("utf-8", errors="replace")
            (report_root / "isolated-api.log").write_text(
                sanitize_isolated_log(raw_log),
                encoding="utf-8",
            )
        except Exception:
            write_failure_evidence(report_root, {
                "event": "isolated_log",
                "phase": "unavailable",
            })
    expected_turn_index = None
    if evidence_rows and isinstance(evidence_rows[-1], dict):
        diff = evidence_rows[-1].get("state_diff")
        after = diff.get("after") if isinstance(diff, dict) else None
        index = after.get("turn_index") if isinstance(after, dict) else None
        if type(index) is int:
            expected_turn_index = index
    probe = probe_rollback_status(base, session_id, expected_turn_index)
    write_failure_evidence(report_root, {
        "event": "rollback_probe",
        "phase": "finished" if probe.get("rollback") == "observed" else "unavailable",
        **probe,
    })


def sanitize_isolated_log(text: str) -> str:
    redacted = _redact_diagnostic_text(text)
    if redacted == "sensitive detail redacted":
        return redacted
    return "\n".join(line for line in text.splitlines() if line.strip())


def measured_turn(
    client: Any,
    base: str,
    session_id: str,
    message: str,
    target_id: str | None,
    report_root: Path,
    label: str,
) -> dict[str, Any]:
    """Time the smoke HTTP turn. The 240s client timeout stays unchanged."""
    global _SMOKE_DIAGNOSTIC_PATH
    previous = _SMOKE_DIAGNOSTIC_PATH
    _SMOKE_DIAGNOSTIC_PATH = report_root / "diagnostic-events.jsonl"
    started = time.monotonic()
    _flush_diagnostic({
        "event": "parent_http",
        "phase": "started",
        "label": label,
        "timeout_layer": "smoke_http_client",
        "timeout_seconds": 240,
    })
    try:
        result = _turn(client, base, session_id, message, target_id)
    except Exception as error:
        _flush_diagnostic({
            "event": "parent_http",
            "phase": "failed",
            "label": label,
            "error_type": type(error).__name__,
            "elapsed_seconds": time.monotonic() - started,
            "timeout_layer": "smoke_http_client" if isinstance(error, httpx.TimeoutException) else None,
            "rollback": "rollback doğrulanamadı",
        })
        write_failure_evidence(report_root, {
            "event": "parent_http",
            "phase": "failed",
            "label": label,
            "error_type": type(error).__name__,
            "elapsed_seconds": time.monotonic() - started,
            "timeout_layer": "smoke_http_client" if isinstance(error, httpx.TimeoutException) else None,
            "rollback": "rollback doğrulanamadı",
        })
        raise
    else:
        _flush_diagnostic({
            "event": "parent_http",
            "phase": "finished",
            "label": label,
            "elapsed_seconds": time.monotonic() - started,
            "timeout_layer": "smoke_http_client",
        })
        return result
    finally:
        _SMOKE_DIAGNOSTIC_PATH = previous


def _install_telemetry(game: Any) -> None:
    """Install transparent wrappers only inside the isolated API subprocess."""
    from api.ollama_adapter import PROVIDER_TIMEOUT_SECONDS

    if getattr(game, "_playable_v1_telemetry_installed", False):
        return
    original_chat = game.ollama.chat
    original_validate = game.validate_world_updates
    original_bind = game._bind_world_update_mentions
    original_run_turn = game.run_player_turn
    proposal_hash_salt = os.environ.get("AI_DND_SMOKE_EVIDENCE_SALT")
    if not proposal_hash_salt:
        proposal_hash_salt = uuid.uuid4().hex

    def chat_wrapper(*args: Any, **kwargs: Any) -> Any:
        # Exactly one original invocation; no request/response text is retained.
        messages = kwargs.get("messages")
        if messages is None and args:
            messages = args[1] if len(args) > 1 else args[0]
        role = _call_role(messages)
        request_bytes, message_count = _message_request_shape(messages)
        calls = _telemetry()
        attempt_index = 1
        if calls is not None:
            attempt_index += sum(1 for row in calls if row.get("kind") == "model_attempt")
        narration_only = _schema_narration_only(kwargs.get("format")) if role == "narration" else None
        attempt = {
            "event": "model_call",
            "phase": "started",
            "call_role": role,
            "attempt_index": attempt_index,
            "request_utf8_bytes": request_bytes,
            "message_count": message_count,
            "scene_type": _active_scene_type(game),
            "narration_only": narration_only,
            "selected_context_counts": _selected_context_counts(game),
            "provider_timeout_seconds": PROVIDER_TIMEOUT_SECONDS,
        }
        if calls is not None:
            calls.append({
                "kind": "model_attempt",
                "call_role": role,
                "attempt_index": attempt_index,
                "phase": "started",
            })
        started = time.monotonic()
        _flush_diagnostic(attempt)
        try:
            response = original_chat(*args, **kwargs)
        except Exception as error:
            _flush_diagnostic({
                "event": "model_call",
                "phase": "failed",
                "call_role": role,
                "attempt_index": attempt_index,
                "error_type": type(error).__name__,
                "elapsed_seconds": time.monotonic() - started,
                "prompt_eval_count": None,
                "eval_count": None,
            })
            raise
        prompt_eval_count = _numeric(response, "prompt_eval_count")
        eval_count = _numeric(response, "eval_count")
        _flush_diagnostic({
            "event": "model_call",
            "phase": "finished",
            "call_role": role,
            "attempt_index": attempt_index,
            "elapsed_seconds": time.monotonic() - started,
            "prompt_eval_count": prompt_eval_count,
            "eval_count": eval_count,
        })
        if calls is not None:
            calls.append({
                "kind": "model",
                "prompt_eval_count": prompt_eval_count,
                "eval_count": eval_count,
            })
        return response

    def validate_wrapper(updates: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_validate(updates, *args, **kwargs)
        calls = _telemetry()
        if calls is not None:
            validation_call_index = sum(
                1 for row in calls if row.get("kind") == "proposal_validation_call"
            )
            output_calls = _VALIDATION_OUTPUT_CALLS.get()
            if output_calls is not None:
                output_calls[id(result)] = validation_call_index
            flags = {
                "npcs": bool(kwargs.get("allow_new_npcs", False)),
                "features": bool(kwargs.get("allow_new_features", False)),
                "locations": bool(kwargs.get("allow_new_locations", False)),
                "shops": bool(kwargs.get("allow_new_shops", False)),
            }
            # Positional flags follow updates, allow_new_npcs, features, locations, shops.
            if len(args) >= 1:
                flags["npcs"] = bool(args[0])
            if len(args) >= 2:
                flags["features"] = bool(args[1])
            if len(args) >= 3:
                flags["locations"] = bool(args[2])
            if len(args) >= 4:
                flags["shops"] = bool(args[3])
            raw_counts = {
                category: _proposal_count(
                    updates, f"create_{category}"
                )
                for category in ("locations", "npcs", "features", "shops")
            }
            raw_counts["update_npcs"] = _proposal_count(updates, "update_npcs")
            raw_counts["events"] = _proposal_count(updates, "events")
            calls.append({
                "kind": "proposal_validation_call",
                "call_index": validation_call_index,
                "raw_category_counts": raw_counts,
                "scope": "validator_output_membership",
            })
            for category in ("locations", "npcs", "features", "shops"):
                field = f"create_{category}"
                raw_items = updates.get(field, []) if isinstance(updates, dict) else []
                if not isinstance(raw_items, list):
                    continue
                for index, proposal in enumerate(raw_items):
                    raw_key = (
                        proposal.get("proposal_key")
                        if isinstance(proposal, dict) else None
                    )
                    prefix = field[7]
                    fallback_key = f"{prefix}{index + 1}"
                    hash_key = (
                        raw_key if isinstance(raw_key, str) else fallback_key
                    )
                    candidate_key = (
                        game._clean_world_text(raw_key, 16)
                        if isinstance(proposal, dict) else None
                    )
                    key = (
                        candidate_key
                        if isinstance(candidate_key, str) and re.fullmatch(
                            rf"{prefix}[1-9]\d?", candidate_key
                        )
                        else fallback_key
                    )
                    validated_items = (
                        result.get(field, []) if isinstance(result, dict) else None
                    )
                    accepted = (
                        isinstance(validated_items, list)
                        and any(
                            isinstance(item, dict)
                            and item.get("proposal_key") == key
                            for item in validated_items
                        )
                    )
                    calls.append({
                        "kind": "proposal",
                        "category": category,
                        "proposal_key_hash": _proposal_key_hash(
                            proposal_hash_salt, category, hash_key
                        ),
                        "validation_pass_index": index,
                        "validator": "category_disabled" if not flags[category]
                        else "returned_by_validator" if accepted
                        else "not_returned_by_validator",
                        "validator_reason": (
                            "category_flag_disabled" if not flags[category]
                            else "returned_by_validator" if accepted
                            else "not_returned_by_validator"
                        ),
                        "reason_specificity": (
                            "category_flag" if not flags[category]
                            else "validator_output_membership; internal_rule_unavailable"
                        ),
                        "validation_call_index": validation_call_index,
                        "scope": "validator_output_membership",
                    })
            raw_updates = updates.get("update_npcs", []) if isinstance(updates, dict) else []
            validated_updates = (
                result.get("update_npcs", []) if isinstance(result, dict) else None
            )
            if isinstance(raw_updates, list):
                for index, proposal in enumerate(raw_updates):
                    key = proposal.get("id") if isinstance(proposal, dict) else None
                    accepted = isinstance(validated_updates, list) and any(
                        isinstance(item, dict) and item.get("id") == key
                        for item in validated_updates
                    )
                    calls.append({
                        "kind": "proposal",
                        "category": "update_npcs",
                        "proposal_key_hash": _proposal_key_hash(
                            proposal_hash_salt,
                            "update_npcs",
                            key if isinstance(key, str) else f"update_npc_{index + 1}",
                        ),
                        "validation_pass_index": index,
                        "validator": "returned_by_validator" if accepted
                        else "not_returned_by_validator",
                        "validator_reason": (
                            "returned_by_validator" if accepted
                            else "not_returned_by_validator"
                        ),
                        "reason_specificity": (
                            "validator_output_membership; internal_rule_unavailable"
                        ),
                        "validation_call_index": validation_call_index,
                        "scope": "validator_output_membership",
                    })
            raw_events = updates.get("events", []) if isinstance(updates, dict) else []
            validated_events = (
                result.get("events", []) if isinstance(result, dict) else None
            )
            if isinstance(raw_events, list):
                for index, event in enumerate(raw_events):
                    accepted = (
                        isinstance(event, str)
                        and isinstance(validated_events, list)
                        and event in validated_events
                    )
                    calls.append({
                        "kind": "proposal",
                        "category": "events",
                        "proposal_key_hash": _proposal_key_hash(
                            proposal_hash_salt, "events", f"e{index + 1}"
                        ),
                        "validation_pass_index": index,
                        "validator": "returned_by_validator" if accepted
                        else "not_returned_by_validator",
                        "validator_reason": (
                            "returned_by_validator" if accepted
                            else "not_returned_by_validator"
                        ),
                        "reason_specificity": (
                            "validator_output_membership; internal_rule_unavailable"
                        ),
                        "validation_call_index": validation_call_index,
                        "scope": "validator_output_membership",
                    })
        return result

    def bind_wrapper(raw: Any, locations: Any, validated: Any, world_state: Any) -> Any:
        result = original_bind(raw, locations, validated, world_state)
        calls = _telemetry()
        if calls is not None:
            accepted_available = (
                isinstance(result, tuple) and isinstance(result[0], set)
            )
            accepted = result[0] if accepted_available else set()
            output_calls = _VALIDATION_OUTPUT_CALLS.get() or {}
            validation_call_indices = {
                "locations": output_calls.get(id(locations)),
                "npcs": output_calls.get(id(validated)),
                "features": output_calls.get(id(validated)),
                "shops": output_calls.get(id(validated)),
            }
            binding_call_index = sum(
                1 for row in calls if row.get("kind") == "mention_binding_call"
            )
            categories = ("locations", "npcs", "features", "shops")
            raw_counts = {
                category: _proposal_count(
                    raw, f"create_{category}"
                )
                for category in categories
            }
            calls.append({
                "kind": "mention_binding_call",
                "call_index": binding_call_index,
                "validation_call_indices": validation_call_indices,
                "raw_category_counts": raw_counts,
                "accepted_key_set_available": accepted_available,
                "scope": "accepted_key_membership",
            })
            if isinstance(raw, dict):
                for category in categories:
                    field = f"create_{category}"
                    items = raw.get(field, [])
                    if not isinstance(items, list):
                        continue
                    validation_call_index = validation_call_indices.get(category)
                    validated_source = locations if category == "locations" else validated
                    validated_items = (
                        validated_source.get(field, [])
                        if isinstance(validated_source, dict) else None
                    )
                    validated_available = isinstance(validated_items, list)
                    if not validated_available:
                        validated_items = []
                    for index, proposal in enumerate(items):
                        raw_key = (
                            proposal.get("proposal_key")
                            if isinstance(proposal, dict) else None
                        )
                        prefix = field[7]
                        hash_key = (
                            raw_key if isinstance(raw_key, str)
                            else f"{prefix}{index + 1}"
                        )
                        key = hash_key
                        if not re.fullmatch(
                            rf"{prefix}[1-9]\d?", key
                        ):
                            key = f"{prefix}{index + 1}"
                        was_validated = validated_available and any(
                            isinstance(item, dict)
                            and item.get("proposal_key") == key
                            for item in validated_items
                        )
                        if not accepted_available:
                            binding_reason = "binding_result_unavailable"
                        elif not validated_available:
                            binding_reason = "validation_output_unavailable"
                        elif key in accepted:
                            binding_reason = "accepted_key_membership"
                        elif was_validated:
                            binding_reason = "present_in_validation_output_not_accepted"
                        else:
                            binding_reason = "not_returned_in_validation_output"
                        calls.append({
                            "kind": "mention_binding",
                            "category": category,
                            "proposal_key_hash": _proposal_key_hash(
                                proposal_hash_salt, category, hash_key
                            ),
                            "validation_pass_index": index,
                            "mention_binding": binding_reason,
                            "reason": binding_reason,
                            "validation_call_index": validation_call_index,
                            "binding_call_index": binding_call_index,
                            "validation_output_source": (
                                "location_update_output" if category == "locations"
                                else "world_update_validator_output"
                            ),
                            "scope": "validation_and_binding_output_membership",
                        })
        return result

    def session_run_turn(
        self: Any, message: Any, messages: Any = None,
        target_id: Any = None, scene_plan: Any = None,
    ) -> Any:
        calls = _telemetry()
        if calls is not None:
            calls.append({"kind": "turn_wrapper_seen"})
        self.last_narration_safety = None
        _flush_diagnostic({"event": "engine", "phase": "started"})
        engine_started = time.monotonic()
        try:
            result = original_run_turn(
                message, messages=messages, target_id=target_id,
                scene_plan=scene_plan, session=self,
            )
        except Exception as error:
            _flush_diagnostic({
                "event": "engine",
                "phase": "failed",
                "error_type": type(error).__name__,
                "elapsed_seconds": time.monotonic() - engine_started,
            })
            raise
        action = result.get("action_result") if isinstance(result, dict) else {}
        action = action if isinstance(action, dict) else {}
        _flush_diagnostic({
            "event": "engine",
            "phase": "finished",
            "elapsed_seconds": time.monotonic() - engine_started,
            "resolved_action": action.get("action") if isinstance(action.get("action"), str) else None,
            "resolved_status": action.get("status") if isinstance(action.get("status"), str) else None,
        })
        if calls is not None and isinstance(result, dict):
            calls.append({
                "kind": "action_result",
                "action_result": {
                    key: value for key, value in action.items()
                    if key in {
                        "action", "status", "success", "target_id",
                        "target_type", "skill", "outcome", "npc_id",
                    }
                },
            })
        return result

    game.ollama.chat = chat_wrapper
    game.validate_world_updates = validate_wrapper
    game._bind_world_update_mentions = bind_wrapper
    game.GameSession.run_player_turn = session_run_turn
    game._playable_v1_telemetry_installed = True


AI_DND_DIR = Path(__file__).resolve().parents[2]
MODEL_NAME = "qwen3:8b"
MAX_MODEL_CALLS_PER_TURN = 2
BUDGET_EXEMPT_TURN_IDS = frozenset({27, 30, 31, 32, 33})
START_SELECTION = {
    "setting_id": "forgotten_realms",
    "region_pack_id": "fr:pack:the_north:neverwinter:v1",
    "region_id": "fr:region:the_north",
    "starting_location_id": "fr:city:neverwinter",
}
EXPECTED_LABELS = (
    "city look", "city presence", "approach and greet first local",
    "ask first local name", "disclose player name", "ordinary small talk",
    "discover local tavern", "enter discovered tavern", "tavern look",
    "tavern presence", "approach bartender", "ask bartender name",
    "bartender small talk", "sit at presented table", "inspect harmless feature",
    "notice background referent", "promote background referent",
    "follow up promoted referent", "leave tavern", "observe street",
    "approach displayed guard", "ordinary guard question",
    "return to same tavern", "recall tavern continuity",
    "return to starting city", "recall original turn-5 local",
    "false recall challenge", "discover ordinary local merchant",
    "approach and converse merchant", "unsupported purchase", "loaded canon question",
    "unsupported route challenge", "invented ruler/deity challenge",
    "ordinary recovery", "supported perception investigation",
    "return to tavern for final continuity check",
)
GROUP_ACTION_SEQUENCES = (
    EXPECTED_LABELS[0:6],
    EXPECTED_LABELS[6:12],
    EXPECTED_LABELS[12:18],
    EXPECTED_LABELS[18:24],
    EXPECTED_LABELS[24:30],
    EXPECTED_LABELS[30:36],
)


class SmokeFailure(RuntimeError):
    pass


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _projection(state: Any) -> dict[str, Any]:
    """Public, secret-free state projection suitable for evidence/comparison."""
    if not isinstance(state, dict):
        return {}

    def records(items: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        result = [
            {field: item.get(field) for field in fields}
            for item in items if isinstance(item, dict)
        ]
        return sorted(result, key=lambda item: str(item.get("id") or ""))

    scene_state = state.get("scene_state")
    raw_scene = state.get("scene")
    if not isinstance(raw_scene, dict):
        scenes = scene_state.get("scenes", {}) if isinstance(scene_state, dict) else {}
        raw_scene = scenes.get(state.get("location"), {}) if isinstance(scenes, dict) else {}
    if not isinstance(raw_scene, dict):
        raw_scene = {}
    position = raw_scene.get("player_position")
    if not isinstance(position, dict) and isinstance(scene_state, dict):
        position = scene_state.get("player_position")
    position = position if isinstance(position, dict) else {}
    referents = raw_scene.get("referents", [])
    if not isinstance(referents, list):
        referents = []
    safe_referents = []
    for ref in referents:
        if not isinstance(ref, dict):
            continue
        aliases = ref.get("addressable_alias")
        if not aliases:
            aliases = ref.get("aliases")
        alias = aliases[0] if isinstance(aliases, list) and aliases else aliases
        safe_referents.append({
            "id": ref.get("id"),
            "kind": ref.get("kind"),
            "source_turn": ref.get("source_turn"),
            "lifecycle": ref.get("lifecycle"),
            "promoted_npc_id": ref.get("promoted_npc_id"),
            "addressable_alias": alias if isinstance(alias, str) and alias else None,
        })
    safe_referents.sort(key=lambda item: str(item.get("id") or ""))
    safe_scene = {
        key: raw_scene.get(key)
        for key in ("id", "location_id", "parent_location_id", "kind",
                    "visit_revision", "activity_revision")
    }
    safe_scene["player_position"] = {
        key: position.get(key) for key in ("location_id", "kind", "target_id")
    }
    safe_scene["referents"] = safe_referents
    turn_index = state.get("turn_index")
    if type(turn_index) is not int and isinstance(state.get("flags"), dict):
        turn_index = state["flags"].get("turn_index")
    locations = state.get("locations")
    if isinstance(locations, dict):
        locations = [
            dict(value, id=str(location_id))
            for location_id, value in locations.items() if isinstance(value, dict)
        ]
    return {
        "location": state.get("location"),
        "turn_index": turn_index,
        "locations": [
            {
                "id": str(item.get("id")),
                "name": item.get("name"),
                "parent_location_id": item.get("parent_location_id"),
                "reality_layer": item.get("reality_layer"),
            }
            for item in sorted(
                (item for item in locations if isinstance(item, dict)),
                key=lambda item: str(item.get("id") or ""),
            )
        ] if isinstance(locations, list) else [],
        "npcs": records(
            state.get("npcs"), ("id", "name", "role", "location", "shop_id",
                                "reality_layer", "tags"),
        ),
        "shops": records(
            state.get("shops"), ("id", "name", "location", "shopkeeper_id",
                                 "reality_layer", "tags"),
        ),
        "features": records(
            state.get("features"), ("id", "name", "location", "reality_layer"),
        ),
        "scene": safe_scene,
        "inventory": copy.deepcopy(state.get("inventory", [])),
        "currency": state.get("currency"),
    }


def _campaign_projection_without_turn_index(state: Any) -> dict[str, Any]:
    """Compare campaign content while allowing the expected turn advance."""
    projection = _projection(state)
    projection.pop("turn_index", None)
    return projection


def _difference_paths(left: Any, right: Any, path: str = "") -> list[str]:
    """Describe structural differences without writing state values to reports."""
    if type(left) is not type(right):
        return [path or "$"]
    if isinstance(left, dict):
        differences = []
        for key in sorted(set(left) | set(right), key=str):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                differences.append(child_path)
            else:
                differences.extend(
                    _difference_paths(left[key], right[key], child_path)
                )
        return differences
    if isinstance(left, list):
        differences = []
        if len(left) != len(right):
            differences.append(f"{path}.length" if path else "length")
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            differences.extend(
                _difference_paths(left_item, right_item, f"{path}[{index}]")
            )
        return differences
    return [] if left == right else [path or "$"]


def _lore(record: Any) -> dict[str, Any]:
    value = getattr(record, "lore_authority", None)
    if value is None:
        return {}
    data = value.to_dict()
    safe = {key: data.get(key) for key in (
        "binding_status", "world_id", "epoch_id", "region_id",
        "current_location_entity_id", "region_pack_id",
        "starting_location_entity_id", "player_known_fact_ids",
        "npc_known_fact_ids", "procedural_entity_refs", "lore_discoveries",
    )}
    overrides = data.get("campaign_overrides")
    safe["campaign_overrides"] = (
        [
            {
                key: item.get(key)
                for key in (
                    "override_id", "subject_id", "predicate",
                    "source_action_id", "created_turn",
                )
            }
            for item in overrides if isinstance(item, dict)
        ]
        if isinstance(overrides, list) else "unavailable"
    )
    return safe


def _ids(state: dict[str, Any], kind: str) -> set[str]:
    values = state.get(kind, [])
    if kind == "locations" and isinstance(values, dict):
        return {str(key) for key in values}
    if kind == "locations" and isinstance(values, list):
        return {str(item.get("id")) for item in values if isinstance(item, dict)}
    if not isinstance(values, list):
        return set()
    return {str(item["id"]) for item in values
            if isinstance(item, dict) and isinstance(item.get("id"), str)}


def _record_by_id(state: dict[str, Any], kind: str, ident: str) -> dict[str, Any]:
    values = state.get(kind, [])
    if isinstance(values, dict):
        value = values.get(ident)
        return value if isinstance(value, dict) else {}
    return next((value for value in values if isinstance(value, dict)
                 and value.get("id") == ident), {})


def _parse_logs(messages: list[str]) -> tuple[int | None, str | None, list[str] | None]:
    calls = model = facts = None
    for message in messages:
        if "Lore retrieval " in message:
            match = re.search(r"selected_fact_ids=(\[[^\]]*\])", message)
            if match:
                try:
                    value = ast.literal_eval(match.group(1))
                    if isinstance(value, list) and all(isinstance(x, str) for x in value):
                        facts = value
                except (SyntaxError, ValueError):
                    pass
        if "Game turn completed (" in message:
            found = re.search(r"model_calls=(\d+)", message)
            if found:
                calls = int(found.group(1))
            found = re.search(r"model=([^, )]+)", message)
            if found:
                model = found.group(1)
    return calls, model, facts


_TRANSIENT_REPORT_FIELDS = frozenset({
    "input", "player_input", "message", "user_message",
    "narration", "prompt", "completion", "model_prompt",
    "model_completion", "raw_prompt", "raw_completion",
    "memory", "memory_text", "raw_memory", "raw_memory_text",
    "messages", "conversation", "chat_history", "history",
    "request_body", "response_body",
})


def _sanitize_persistent_value(value: Any) -> Any:
    """Recursively remove user/model prose and raw memory from saved evidence."""
    if isinstance(value, dict):
        return {
            key: _sanitize_persistent_value(item)
            for key, item in value.items()
            if not isinstance(key, str)
            or key.casefold() not in _TRANSIENT_REPORT_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_persistent_value(item) for item in value]
    return value


def _append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(
            _sanitize_persistent_value(row),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n")
        handle.flush()


def _persisted_turn(row: dict[str, Any]) -> dict[str, Any]:
    """Return the recursive safe projection used by persistent turn reports."""
    sanitized = _sanitize_persistent_value(row)
    return sanitized if isinstance(sanitized, dict) else {}


def _restore_replay_session(manager: Any, checkpoint: Path, evidence: Path) -> None:
    """Load a disposable replay copy into the isolated API. Canonical saves are refused."""
    from api.lore_authority.models import CampaignLoreState
    from api.narrative_memory import empty_narrative_memory

    loaded, copy_path = load_replay_checkpoint_copy(checkpoint)
    try:
        session_id, record = manager.create()
        restored = restore_replay_checkpoint(record.game_session, loaded)
        journal = restored.get("journal")
        if isinstance(journal, dict):
            record.journal = journal
        memory = restored.get("narrative_memory")
        record.narrative_memory = (
            memory if isinstance(memory, dict) else empty_narrative_memory()
        )
        lore = restored.get("lore_authority")
        if isinstance(lore, dict):
            record.lore_authority = CampaignLoreState.from_mapping(lore)
        combat = restored.get("combat_history")
        record.combat_history = combat if isinstance(combat, list) else []
        evidence.with_name("replay-session.json").write_text(
            json.dumps({"session_id": session_id}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    finally:
        copy_path.unlink(missing_ok=True)


def _serve(
    port: int,
    database: Path,
    evidence: Path,
    checkpoint: Path | None = None,
) -> None:
    global _SMOKE_DIAGNOSTIC_PATH
    os.environ["AI_DND_CAMPAIGN_DB"] = str(database)
    from api.main import app
    import game
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import Response

    capture = _Capture()
    logger = logging.getLogger("ai_dnd.api")
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)
    manager = app.state.session_manager
    _SMOKE_DIAGNOSTIC_PATH = evidence.with_name("diagnostic-events.jsonl")
    _install_telemetry(game)
    adapter = getattr(app.state, "ollama_adapter", None)
    if adapter is not None and callable(getattr(adapter, "ensure_required_model", None)):
        original_preflight = adapter.ensure_required_model

        def preflight_wrapper() -> Any:
            _flush_diagnostic({
                "event": "preflight",
                "phase": "started",
                "counted_as_generation": False,
            })
            started_at = time.monotonic()
            try:
                result = original_preflight()
            except Exception as error:
                _flush_diagnostic({
                    "event": "preflight",
                    "phase": "failed",
                    "error_type": type(error).__name__,
                    "elapsed_seconds": time.monotonic() - started_at,
                    "counted_as_generation": False,
                })
                raise
            _flush_diagnostic({
                "event": "preflight",
                "phase": "finished",
                "elapsed_seconds": time.monotonic() - started_at,
                "counted_as_generation": False,
            })
            return result

        adapter.ensure_required_model = preflight_wrapper

    def memory_snapshot_refs(world_state: dict[str, Any]) -> list[str]:
        """Return coarse per-snapshot ordinals, not persistent memory IDs."""
        return sorted([
            f"{npc.get('id')}:{index}"
            for npc in world_state.get("npcs", [])
            if isinstance(npc, dict)
            for index, entry in enumerate(npc.get("memory", []))
            if isinstance(entry, dict) and npc.get("id")
        ])

    class AuditMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            match = re.fullmatch(r"/api/(?:game/)?sessions/([^/]+)/turn",
                                 request.url.path)
            resume_match = re.fullmatch(r"/api/campaigns/([^/]+)/resume",
                                        request.url.path)
            start = len(capture.messages)
            telemetry_rows: list[dict[str, Any]] = []
            token = _REQUEST_TELEMETRY.set(telemetry_rows)
            validation_outputs_token = _VALIDATION_OUTPUT_CALLS.set({})
            entered = time.monotonic()
            if match:
                _flush_diagnostic({
                    "event": "api_turn",
                    "phase": "started",
                    "session_id": match.group(1),
                })
            try:
                response = await call_next(request)
            except Exception as error:
                if match:
                    _flush_diagnostic({
                        "event": "api_turn",
                        "phase": "failed",
                        "error_type": type(error).__name__,
                        "elapsed_seconds": time.monotonic() - entered,
                    })
                raise
            finally:
                _VALIDATION_OUTPUT_CALLS.reset(validation_outputs_token)
                _REQUEST_TELEMETRY.reset(token)
            if resume_match and response.status_code < 400:
                body = b"".join([chunk async for chunk in response.body_iterator])
                try:
                    payload = json.loads(body.decode("utf-8"))
                    resumed_id = payload.get("session_id")
                    record = manager.get(resumed_id) if isinstance(resumed_id, str) else None
                    if record is not None:
                             _append(evidence, {
                            "event": "resume",
                            "campaign_id": resume_match.group(1),
                            "session_id": resumed_id,
                            "state": _projection(record.game_session.world_state),
                            "lore": _lore(record),
                            "memory_snapshot_refs": memory_snapshot_refs(
                                record.game_session.world_state
                            ),
                        "player_disclosure_memory_refs": sorted(
                            ref for ref in memory_snapshot_refs(
                                record.game_session.world_state
                            )
                            if any(
                                isinstance(entry, dict)
                                and entry.get("speaker") == "player"
                                and f"{npc.get('id')}:{index}" == ref
                                and re.search(r"\bArven\b", str(entry.get("text", "")),
                                              re.IGNORECASE)
                                for npc in record.game_session.world_state.get("npcs", [])
                                if isinstance(npc, dict)
                                for index, entry in enumerate(npc.get("memory", []))
                            )
                        ),
                        })
                finally:
                    response = Response(
                        content=body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )
            if match and response.status_code >= 400:
                _flush_diagnostic({
                    "event": "api_turn",
                    "phase": "failed",
                    "http_status": response.status_code,
                    "elapsed_seconds": time.monotonic() - entered,
                })
            if match and response.status_code < 400:
                _flush_diagnostic({
                    "event": "api_turn",
                    "phase": "finished",
                    "elapsed_seconds": time.monotonic() - entered,
                })
                record = manager.get(match.group(1))
                session = record.game_session
                try:
                    checkpoint_path = write_replay_checkpoint(
                        record, private_replay_directory(evidence.parent),
                    )
                    checkpoint_turn = checkpoint_path.stem.removeprefix("after-turn-")
                    _flush_diagnostic({
                        "event": "replay_checkpoint",
                        "phase": "finished",
                        "storage": "private_replay",
                        "turn_index": (
                            int(checkpoint_turn)
                            if checkpoint_turn.isdecimal() else None
                        ),
                    })
                except Exception as error:
                    _flush_diagnostic({
                        "event": "replay_checkpoint",
                        "phase": "failed",
                        "error_type": type(error).__name__,
                    })
                calls, model, facts = _parse_logs(capture.messages[start:])
                safety = getattr(session, "last_narration_safety", {})
                safety = safety if isinstance(safety, dict) else {}
                disclosure_memory_ids = [
                    f"{npc.get('id')}:{index}"
                    for npc in session.world_state.get("npcs", [])
                    if isinstance(npc, dict)
                    for index, entry in enumerate(npc.get("memory", []))
                    if isinstance(entry, dict)
                    and entry.get("speaker") == "player"
                    and re.search(r"\bArven\b", str(entry.get("text", "")),
                                  re.IGNORECASE)
                    and npc.get("id")
                ]
                all_memory_refs = memory_snapshot_refs(session.world_state)
                disclosure_memory_ids = sorted(set(disclosure_memory_ids))
                prompt_counts = [
                    row["prompt_eval_count"] for row in telemetry_rows
                    if row.get("kind") == "model"
                    and type(row.get("prompt_eval_count")) is int
                ]
                eval_counts = [
                    row["eval_count"] for row in telemetry_rows
                    if row.get("kind") == "model"
                    and type(row.get("eval_count")) is int
                ]
                observed_model_calls = len(
                    [row for row in telemetry_rows if row.get("kind") == "model"]
                )
                validation_rows = [
                    row for row in telemetry_rows if row.get("kind") == "proposal"
                ]
                validation_calls = [
                    row for row in telemetry_rows
                    if row.get("kind") == "proposal_validation_call"
                ]
                binding_calls = [
                    row for row in telemetry_rows
                    if row.get("kind") == "mention_binding_call"
                ]
                validation_count_fields = (
                    "locations", "npcs", "features", "shops", "update_npcs", "events"
                )
                binding_count_fields = ("locations", "npcs", "features", "shops")
                validation_trace_complete = all(
                    isinstance(call.get("raw_category_counts"), dict)
                    and all(
                        type(call["raw_category_counts"].get(field)) is int
                        and call["raw_category_counts"][field] >= 0
                        for field in validation_count_fields
                    )
                    for call in validation_calls
                )
                binding_trace_complete = all(
                    isinstance(call.get("raw_category_counts"), dict)
                    and all(
                        type(call["raw_category_counts"].get(field)) is int
                        and call["raw_category_counts"][field] >= 0
                        for field in binding_count_fields
                    )
                    and call.get("accepted_key_set_available") is True
                    and isinstance(call.get("validation_call_indices"), dict)
                    and all(
                        type(call["validation_call_indices"].get(field)) is int
                        and 0 <= call["validation_call_indices"][field]
                        < len(validation_calls)
                        for field in binding_count_fields
                    )
                    for call in binding_calls
                )
                validation_indices_complete = [
                    row.get("call_index") for row in validation_calls
                ] == list(range(len(validation_calls)))
                binding_indices_complete = [
                    row.get("call_index") for row in binding_calls
                ] == list(range(len(binding_calls)))
                stage_counts = {
                    stage: sum(
                        1 for item in validation_rows
                        if item.get("validator") == stage
                    )
                    for stage in (
                        "returned_by_validator", "not_returned_by_validator",
                        "category_disabled",
                    )
                }
                category_counts = {
                    category: sum(1 for item in validation_rows
                                  if item.get("category") == category)
                    for category in ("locations", "npcs", "features", "shops",
                                     "update_npcs", "events")
                }
                raw_proposal_count = (
                    sum(
                        sum(call["raw_category_counts"].values())
                        for call in validation_calls
                    )
                    if validation_trace_complete else None
                )
                proposal_trace_status = (
                    "telemetry_incomplete"
                    if not validation_trace_complete
                    or not binding_trace_complete
                    or not validation_indices_complete
                    or not binding_indices_complete
                    else "validator_not_invoked" if not validation_calls
                    else "invoked_no_proposals" if raw_proposal_count == 0
                    else "invoked_with_proposals"
                )
                action_result_row = next(
                    (
                        row for row in telemetry_rows
                        if row.get("kind") == "action_result"
                    ),
                    None,
                )
                telemetry_context_seen = any(
                    row.get("kind") == "turn_wrapper_seen" for row in telemetry_rows
                )
                safety_handling = safety.get("handling")
                safety_scope = _safety_scope(safety_handling)
                safety_reason_code = safety.get("reason_code")
                if not isinstance(safety_reason_code, str) or not safety_reason_code:
                    safety_reason_code = (
                        "NO_SAFETY_TRIGGER"
                        if safety_handling in {"accepted", "python_scene_response"}
                        else None
                    )
                _append(evidence, {
                    "session_id": match.group(1),
                    "turn_index": session.world_state.get("flags", {}).get("turn_index"),
                    "request_telemetry_context_seen": telemetry_context_seen,
                    "action_result_capture_seen": (
                        isinstance(action_result_row, dict)
                        and isinstance(action_result_row.get("action_result"), dict)
                    ),
                    "model": model,
                    "model_calls": calls,
                    "observed_model_calls": observed_model_calls,
                    "proposal_validation_calls": len(validation_calls),
                    "proposal_validation_call_indices": [
                        row.get("call_index") for row in validation_calls
                    ],
                    "proposal_binding_calls": len(binding_calls),
                    "proposal_binding_call_indices": [
                        row.get("call_index") for row in binding_calls
                    ],
                    "proposal_trace_status": proposal_trace_status,
                    "proposal_category_counts": category_counts,
                    "proposal_stage_counts": stage_counts,
                    "events": {
                        "proposed": (
                            sum(
                                call["raw_category_counts"]["events"]
                                for call in validation_calls
                            )
                            if validation_trace_complete else None
                        ),
                        "returned_by_validator": sum(
                            1 for item in validation_rows
                            if item.get("category") == "events"
                            and item.get("validator") == "returned_by_validator"
                        ),
                        "not_returned_by_validator": sum(
                            1 for item in validation_rows
                            if item.get("category") == "events"
                            and item.get("validator") == "not_returned_by_validator"
                        ),
                    },
                    "token_usage": {
                        "prompt_eval_count": sum(prompt_counts)
                        if len(prompt_counts) == len(
                            [row for row in telemetry_rows if row.get("kind") == "model"]
                        ) else "unavailable",
                        "eval_count": sum(eval_counts)
                        if len(eval_counts) == len(
                            [row for row in telemetry_rows if row.get("kind") == "model"]
                        ) else "unavailable",
                    },
                    "proposal_diagnostics": (
                        [
                            row for row in telemetry_rows
                            if row.get("kind") in {
                                "proposal", "mention_binding", "mention_binding_call",
                                "proposal_validation_call",
                            }
                        ]
                        or [{
                            "kind": "proposal_summary",
                            "status": "validator_not_invoked",
                        }]
                    ),
                    "action_result": (
                        action_result_row.get("action_result")
                        if isinstance(action_result_row, dict) else None
                    ),
                    "retrieved_fact_ids": facts if facts is not None else [],
                    "player_disclosure_memory_refs": disclosure_memory_ids,
                    "memory_snapshot_refs": all_memory_refs,
                    "safety": {
                        "tier": safety.get("tier") or "unavailable",
                        "handling": safety_handling or "unavailable",
                        "reason_code": safety_reason_code,
                        "trigger_span": (
                            str(safety.get("trigger_span"))[:160]
                            if safety.get("trigger_span") else None
                        ),
                        "scope": safety_scope,
                        "scope_basis": "engine_handling",
                        "scene_type": safety.get("scene_type"),
                    },
                    "state": _projection(session.world_state),
                    "lore": _lore(record),
                })
            return response

    app.add_middleware(AuditMiddleware)
    if checkpoint is not None:
        _restore_replay_session(manager, checkpoint, evidence)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning",
                access_log=False)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start(port: int, database: Path, evidence: Path,
           evidence_salt: str) -> tuple[subprocess.Popen[bytes], Any]:
    environment = os.environ.copy()
    environment["AI_DND_CAMPAIGN_DB"] = str(database)
    environment["AI_DND_SMOKE_EVIDENCE_SALT"] = evidence_salt
    handle = tempfile.TemporaryFile(mode="w+b")
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "api.tests.live_playable_living_world_v1_smoke",
             "--serve", str(port), str(database), str(evidence)],
            cwd=AI_DND_DIR, env=environment, stdout=handle,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        handle.close()
        raise
    return process, handle


def _ready(process: subprocess.Popen[bytes], base: str) -> dict[str, Any]:
    deadline = time.monotonic() + 45
    with httpx.Client(timeout=2) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                response = client.get(f"{base}/api/health")
                if response.status_code == 200:
                    return response.json()
            except httpx.HTTPError:
                time.sleep(0.25)
            time.sleep(0.25)
    raise SmokeFailure("Isolated API did not become healthy; startup details redacted.")


def _stop(process: subprocess.Popen[bytes], handle: Any) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    handle.close()


def _turn(client: httpx.Client, base: str, session_id: str, message: str,
          target_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    if target_id:
        payload["target_id"] = target_id
    response = client.post(f"{base}/api/sessions/{session_id}/turn",
                           json=payload, timeout=240)
    if response.status_code != 200:
        raise SmokeFailure(f"Turn failed HTTP {response.status_code}; response redacted.")
    return response.json()


def _latest(path: Path) -> dict[str, Any]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise SmokeFailure("No sanitized turn evidence was recorded.")
    value = json.loads(lines[-1])
    if not isinstance(value, dict):
        raise SmokeFailure("Turn evidence is not an object.")
    return value


def _latest_event(path: Path, event: str) -> dict[str, Any]:
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line:
            continue
        value = json.loads(line)
        if isinstance(value, dict) and value.get("event") == event:
            return value
    raise SmokeFailure(f"No sanitized {event} audit event was recorded.")


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _proposal_trace_gaps(row: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    diagnostics = row.get("proposal_decisions")
    if not isinstance(diagnostics, list):
        return ["proposal decision diagnostics unavailable"]
    if any(not isinstance(item, dict) for item in diagnostics):
        return ["malformed proposal decision telemetry"]

    validation_rows = [
        item for item in diagnostics
        if item.get("kind") == "proposal_validation_call"
    ]
    binding_calls = [
        item for item in diagnostics if item.get("kind") == "mention_binding_call"
    ]
    proposals = [item for item in diagnostics if item.get("kind") == "proposal"]
    bindings = [item for item in diagnostics if item.get("kind") == "mention_binding"]
    known_kinds = {
        "proposal_validation_call", "mention_binding_call",
        "proposal", "mention_binding", "proposal_summary",
    }
    if any(item.get("kind") not in known_kinds for item in diagnostics):
        gaps.append("unrecognized proposal telemetry record")
    if "proposal_summary" in [item.get("kind") for item in diagnostics]:
        if (
            len(diagnostics) != 1
            or row.get("proposal_trace_status") != "validator_not_invoked"
        ):
            gaps.append("validator-not-invoked summary conflicts with proposal trace")

    expected_validation_indices = list(range(len(validation_rows)))
    expected_binding_indices = list(range(len(binding_calls)))
    if (
        type(row.get("proposal_validation_calls")) is not int
        or row.get("proposal_validation_calls") != len(validation_rows)
        or row.get("proposal_validation_call_indices") != expected_validation_indices
    ):
        gaps.append("proposal validation call indices/count are inconsistent")
    if (
        type(row.get("proposal_binding_calls")) is not int
        or row.get("proposal_binding_calls") != len(binding_calls)
        or row.get("proposal_binding_call_indices") != expected_binding_indices
    ):
        gaps.append("proposal binding call indices/count are inconsistent")
    if row.get("proposal_trace_status") not in {
        "validator_not_invoked", "invoked_no_proposals", "invoked_with_proposals",
    }:
        gaps.append("proposal trace status is incomplete")

    validation_by_index: dict[int, dict[str, Any]] = {}
    binding_by_index: dict[int, dict[str, Any]] = {}
    validation_categories = (
        "locations", "npcs", "features", "shops", "update_npcs", "events"
    )
    binding_categories = ("locations", "npcs", "features", "shops")
    for item in validation_rows:
        call_index = item.get("call_index")
        counts = item.get("raw_category_counts")
        if (
            type(call_index) is not int
            or call_index in validation_by_index
            or not isinstance(counts, dict)
            or item.get("scope") != "validator_output_membership"
            or any(
                type(counts.get(category)) is not int
                or counts[category] < 0
                for category in validation_categories
            )
        ):
            gaps.append("proposal validation call fields are incomplete")
            continue
        validation_by_index[call_index] = item

    for item in binding_calls:
        call_index = item.get("call_index")
        validation_indices = item.get("validation_call_indices")
        counts = item.get("raw_category_counts")
        if (
            type(call_index) is not int
            or call_index in binding_by_index
            or not isinstance(validation_indices, dict)
            or any(
                type(validation_indices.get(category)) is not int
                or validation_indices[category] not in validation_by_index
                for category in binding_categories
            )
            or not isinstance(counts, dict)
            or any(
                type(counts.get(category)) is not int
                or counts[category] < 0
                for category in binding_categories
            )
            or item.get("accepted_key_set_available") is not True
            or item.get("scope") != "accepted_key_membership"
        ):
            gaps.append("proposal binding call fields are incomplete or unlinked")
            continue
        binding_by_index[call_index] = item
        if any(
            counts[category] != validation_by_index[
                validation_indices[category]
            ]["raw_category_counts"][category]
            for category in binding_categories
        ):
            gaps.append("proposal binding counts do not match their validator outputs")

    proposal_by_trace_index: dict[tuple[str, int, int], dict[str, Any]] = {}
    for item in proposals:
        category = item.get("category")
        validator_status = item.get("validator")
        validator_reason = item.get("validator_reason")
        expected_reasons = {
            "category_disabled": "category_flag_disabled",
            "returned_by_validator": "returned_by_validator",
            "not_returned_by_validator": "not_returned_by_validator",
        }
        expected_specificities = {
            "category_disabled": "category_flag",
            "returned_by_validator": (
                "validator_output_membership; internal_rule_unavailable"
            ),
            "not_returned_by_validator": (
                "validator_output_membership; internal_rule_unavailable"
            ),
        }
        validation_index = item.get("validation_call_index")
        pass_index = item.get("validation_pass_index")
        digest = item.get("proposal_key_hash")
        if (
            "proposal_key" in item
            or category not in validation_categories
            or not isinstance(validator_status, str)
            or validator_status not in expected_reasons
            or validator_reason != expected_reasons.get(validator_status)
            or (
                category in {"update_npcs", "events"}
                and validator_status == "category_disabled"
            )
            or type(validation_index) is not int
            or validation_index not in validation_by_index
            or type(pass_index) is not int
            or pass_index < 0
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{16}", digest)
            or item.get("reason_specificity")
            != expected_specificities.get(validator_status)
            or item.get("scope") != "validator_output_membership"
        ):
            gaps.append("proposal category/hash/reason association unavailable")
            continue
        trace_index = (category, validation_index, pass_index)
        if trace_index in proposal_by_trace_index:
            gaps.append("duplicate proposal validation trace index")
        proposal_by_trace_index[trace_index] = item

    category_counts = row.get("proposal_category_counts")
    if (
        not isinstance(category_counts, dict)
        or any(
            type(category_counts.get(category)) is not int
            or category_counts[category] != sum(
                1 for item in proposals if item.get("category") == category
            )
            for category in validation_categories
        )
    ):
        gaps.append("proposal category totals do not match proposal diagnostics")

    binding_by_trace_index: dict[tuple[str, int, int], dict[str, Any]] = {}
    valid_binding_reasons = {
        "accepted_key_membership",
        "present_in_validation_output_not_accepted",
        "not_returned_in_validation_output",
    }
    for item in bindings:
        category = item.get("category")
        validation_index = item.get("validation_call_index")
        binding_index = item.get("binding_call_index")
        pass_index = item.get("validation_pass_index")
        digest = item.get("proposal_key_hash")
        trace_index = (
            (category, validation_index, pass_index)
            if isinstance(category, str)
            and type(validation_index) is int
            and type(pass_index) is int
            else None
        )
        validator_item = (
            proposal_by_trace_index.get(trace_index)
            if trace_index is not None else None
        )
        binding_call = (
            binding_by_index.get(binding_index)
            if type(binding_index) is int else None
        )
        expected_validation_source = (
            "location_update_output" if category == "locations"
            else "world_update_validator_output"
        )
        if (
            "proposal_key" in item
            or category not in binding_categories
            or type(validation_index) is not int
            or validation_index not in validation_by_index
            or type(binding_index) is not int
            or binding_index not in binding_by_index
            or binding_call is None
            or binding_call.get("validation_call_indices", {}).get(category)
            != validation_index
            or type(pass_index) is not int
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{16}", digest)
            or item.get("reason") not in valid_binding_reasons
            or item.get("mention_binding") != item.get("reason")
            or item.get("validation_output_source") != expected_validation_source
            or item.get("scope") != "validation_and_binding_output_membership"
            or validator_item is None
            or validator_item.get("proposal_key_hash") != digest
            or (
                validator_item.get("validator") == "returned_by_validator"
                and item.get("reason") not in {
                    "accepted_key_membership",
                    "present_in_validation_output_not_accepted",
                }
            )
            or (
                validator_item.get("validator") != "returned_by_validator"
                and item.get("reason") != "not_returned_in_validation_output"
            )
        ):
            gaps.append("proposal mention-binding outcome is incomplete or unlinked")
            continue
        if trace_index in binding_by_trace_index:
            gaps.append("duplicate proposal mention-binding trace index")
        binding_by_trace_index[trace_index] = item

    for call_index, call in validation_by_index.items():
        counts = call["raw_category_counts"]
        for category in validation_categories:
            expected = counts[category]
            observed_indices = [
                item.get("validation_pass_index") for item in proposals
                if item.get("category") == category
                and item.get("validation_call_index") == call_index
            ]
            if (
                len(observed_indices) != expected
                or any(type(index) is not int for index in observed_indices)
                or sorted(
                    index for index in observed_indices if type(index) is int
                ) != list(range(expected))
            ):
                gaps.append("proposal rows do not match raw validator proposal counts")
                break
        for category in binding_categories:
            source_calls = [
                binding_call for binding_call in binding_calls
                if binding_call.get("validation_call_indices", {}).get(category)
                == call_index
            ]
            accepted_proposals = [
                item for item in proposals
                if item.get("category") == category
                and item.get("validation_call_index") == call_index
                and item.get("validator") == "returned_by_validator"
            ]
            if accepted_proposals and not source_calls:
                gaps.append(
                    "accepted create proposal validator output has no binding call"
                )
            for binding_call in source_calls:
                expected = binding_call["raw_category_counts"][category]
                observed_indices = [
                    item.get("validation_pass_index") for item in bindings
                    if item.get("category") == category
                    and item.get("validation_call_index") == call_index
                    and item.get("binding_call_index")
                    == binding_call.get("call_index")
                ]
                if (
                    expected != counts[category]
                    or len(observed_indices) != expected
                    or any(type(index) is not int for index in observed_indices)
                    or sorted(
                        index for index in observed_indices
                        if type(index) is int
                    ) != list(range(expected))
                ):
                    gaps.append(
                        "proposal binding rows do not match source validator output"
                    )
                    break

    if validation_rows and len(validation_by_index) == len(validation_rows):
        raw_total = sum(
            sum(call["raw_category_counts"][category]
                for category in validation_categories)
            for call in validation_by_index.values()
        )
        expected_status = (
            "invoked_no_proposals" if raw_total == 0
            else "invoked_with_proposals"
        )
        if row.get("proposal_trace_status") != expected_status:
            gaps.append("proposal trace status conflicts with raw validator counts")
    elif not validation_rows and row.get("proposal_trace_status") != "validator_not_invoked":
        gaps.append("validator call absence is not classified accurately")

    events = row.get("events")
    if (
        not isinstance(events, dict)
        or any(type(events.get(field)) is not int
               for field in (
                   "proposed", "returned_by_validator",
                   "not_returned_by_validator",
               ))
        or events.get("returned_by_validator", 0)
        + events.get("not_returned_by_validator", 0)
        != events.get("proposed")
    ):
        gaps.append("event proposal counts are incomplete or inconsistent")
    elif events.get("proposed") != sum(
        item["raw_category_counts"]["events"] for item in validation_rows
        if isinstance(item.get("raw_category_counts"), dict)
        and type(item["raw_category_counts"].get("events")) is int
    ):
        gaps.append("event proposals do not match validator trace counts")

    return list(dict.fromkeys(gaps))


def _assert_npc_target(turn: dict[str, Any], target_id: str, label: str) -> None:
    """Require the isolated engine result to preserve the submitted target."""
    action = turn.get("action_result")
    _require(isinstance(action, dict), f"{label}: action result telemetry unavailable.")
    _require(action.get("target_id") == target_id or action.get("npc_id") == target_id,
             f"{label}: isolated engine result lost the submitted target.")


def _one_npc(state: dict[str, Any], location: str,
             *, role: str | None = None, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded = exclude or set()
    values = [x for x in state.get("npcs", []) if isinstance(x, dict)
              and x.get("location") == location and x.get("id") not in excluded]
    if role:
        wanted = {role.casefold()}
        if role.casefold() == "merchant":
            wanted.update({"tüccar", "tacir", "satıcı", "esnaf"})
        matching = [x for x in values if str(x.get("role", "")).casefold() in wanted]
        if matching:
            values = matching
    _require(values, f"Required dynamic NPC unavailable: {role or 'local'}")
    # A city scene may legitimately present more than one person.  Choose
    # only from returned public records; never synthesize or guess a name.
    values.sort(key=lambda item: str(item.get("id", "")))
    return values[0]


def _one_feature(state: dict[str, Any], location: str) -> dict[str, Any]:
    values = [x for x in state.get("features", []) if isinstance(x, dict)
              and x.get("location") == location]
    _require(values, "Required dynamic feature unavailable.")
    values.sort(key=lambda item: str(item.get("id", "")))
    return values[0]


def run_smoke() -> dict[str, Any]:
    if any(len(group) != 6 for group in GROUP_ACTION_SEQUENCES):
        raise SmokeFailure("Every release-gate action group must contain exactly six turns.")
    evidence_rows: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "status": "FAIL", "model": MODEL_NAME,
        "campaign_database": "temporary_disposable", "turns": evidence_rows,
        "token_usage": "unavailable",
        "telemetry_implementation": (
            "isolated subprocess wrappers call original game.ollama.chat, "
            "validate_world_updates, and _bind_world_update_mentions exactly once; "
            "only numeric model counts and sanitized proposal diagnostics are retained"
        ),
        "evidence_incomplete": [],
        "budget_exempt_turn_ids": sorted(BUDGET_EXEMPT_TURN_IDS),
    }
    report_parent = AI_DND_DIR / "reports" / "playable-living-world-v1-smokes"
    report_root = report_parent / f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
    try:
        report_root.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise SmokeFailure(
            f"Could not create unique sanitized report directory: {error}"
        ) from None
    audit = report_root / "api-audit.jsonl"
    turn_evidence = report_root / "turn-evidence.jsonl"
    result["report_path"] = str(report_root)
    evidence_salt = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="ai-dnd-playable-v1-") as directory:
        root = Path(directory)
        database = root / "campaigns.sqlite3"
        port, base = _port(), ""
        base = f"http://127.0.0.1:{port}"
        process: subprocess.Popen[bytes] | None = None
        handle: Any = None
        session_id = ""
        unplanned_fallbacks = 0

        def play(client: httpx.Client, sid: str, message: str,
                 label: str, target: str | None = None) -> dict[str, Any]:
            nonlocal unplanned_fallbacks
            group_index, group_offset = divmod(len(evidence_rows), 6)
            _require(group_index < len(GROUP_ACTION_SEQUENCES),
                     "More than six action groups were attempted.")
            expected = GROUP_ACTION_SEQUENCES[group_index][group_offset]
            _require(label == expected,
                     f"Action sequence shifted: expected {expected}, got {label}.")
            before = last_state[0]
            try:
                turn = measured_turn(
                    client, base, sid, message, target, report_root, label,
                )
            except SmokeFailure as error:
                _append(turn_evidence, {
                    "turn": len(evidence_rows) + 1, "label": label,
                    "failure": "turn_http_error",
                    "error_type": type(error).__name__,
                })
                raise
            try:
                row = _latest(audit)
            except SmokeFailure as error:
                _append(turn_evidence, {
                    "turn": len(evidence_rows) + 1, "label": label,
                    "failure": "missing_server_audit",
                    "error_type": type(error).__name__,
                })
                evidence_rows.append({
                    "turn": len(evidence_rows) + 1,
                    "label": label,
                    "narration": turn.get("narration"),
                    "failure": "missing_server_audit",
                })
                result["turns"] = evidence_rows
                raise
            turn_number = len(evidence_rows) + 1
            action_result = row.get("action_result")
            turn["action_result"] = action_result
            state = row.get("state", {})
            state = state if isinstance(state, dict) else {}
            narration = turn.get("narration")
            early_safety = row.get("safety")
            early_safety = early_safety if isinstance(early_safety, dict) else {}
            early_tier = early_safety.get("tier")
            early_scope = early_safety.get("scope")
            early_fallback = _is_fallback_candidate(early_safety)
            early_budget_exempt = turn_number in BUDGET_EXEMPT_TURN_IDS
            early_row = {
                "turn": turn_number, "label": label,
                "target_id": target,
                "request_telemetry_context_seen": row.get(
                    "request_telemetry_context_seen"
                ),
                "action_result_capture_seen": row.get("action_result_capture_seen"),
                "resolved_action": (
                    action_result.get("action") if isinstance(action_result, dict) else None
                ),
                "action_result_source": "isolated_session_engine_telemetry",
                "action_result": action_result,
                "skill_check_result": turn.get("skill_check_result"),
                "location_id": state.get("location"),
                "entity_ids": {key: sorted(_ids(state, key))
                               for key in ("npcs", "features", "shops", "locations")},
                "state_diff": {
                    "before": _projection(before), "after": _projection(state),
                },
                "retrieved_fact_ids": row.get("retrieved_fact_ids", []),
                "memory_snapshot_refs": row.get("memory_snapshot_refs", []),
                "player_disclosure_memory_refs": row.get(
                    "player_disclosure_memory_refs", []
                ),
                "created_ids": sorted(
                    f"{kind}:{ident}"
                    for kind in ("npcs", "features", "shops", "locations")
                    for ident in (_ids(state, kind) - _ids(before, kind))
                ),
                "reused_ids": sorted(
                    f"{kind}:{ident}"
                    for kind in ("npcs", "features", "shops", "locations")
                    for ident in (_ids(state, kind) & _ids(before, kind))
                ),
                "promoted_ids": sorted(
                    str(ref.get("promoted_npc_id"))
                    for ref in (state.get("scene", {}).get("referents", [])
                                if isinstance(state.get("scene"), dict) else [])
                    if isinstance(ref, dict)
                    and ref.get("lifecycle") == "promoted"
                    and ref.get("promoted_npc_id")
                ),
                "proposal_decisions": row.get("proposal_diagnostics", []),
                "proposal_validation_calls": row.get("proposal_validation_calls", 0),
                "proposal_validation_call_indices": row.get(
                    "proposal_validation_call_indices", []
                ),
                "proposal_binding_calls": row.get("proposal_binding_calls"),
                "proposal_binding_call_indices": row.get(
                    "proposal_binding_call_indices", []
                ),
                "proposal_trace_status": row.get(
                    "proposal_trace_status", "unavailable"
                ),
                "proposal_category_counts": row.get("proposal_category_counts", {}),
                "proposal_stage_counts": row.get("proposal_stage_counts", {}),
                "proposal_reason_specificity": (
                    "validator/binding output membership only; internal cause unavailable"
                ),
                "events": row.get("events", {}),
                "model_calls": row.get("model_calls"),
                "observed_model_calls": row.get("observed_model_calls"),
                "model_call_count_matches": (
                    row.get("observed_model_calls") == row.get("model_calls")
                ),
                "token_usage": row.get("token_usage", "unavailable"),
                "safety": row.get("safety", {}),
                "safety_classification": (
                    f"{early_safety.get('handling')}:{early_safety.get('reason_code')}"
                    if isinstance(early_safety.get("handling"), str)
                    and isinstance(early_safety.get("reason_code"), str)
                    else "unavailable"
                ),
                "safety_tier": early_tier,
                "safety_reason": early_safety.get("reason_code"),
                "safety_handling": early_safety.get("handling"),
                "safety_scope": early_scope,
                "safety_scene_type": early_safety.get("scene_type"),
                "budget_exempt": early_budget_exempt,
                "fallback_budget_counted": early_fallback and not early_budget_exempt,
                "narration": narration,
            }
            _append(turn_evidence, _persisted_turn(early_row))
            evidence_rows.append(early_row)
            result["turns"] = evidence_rows
            last_state[0] = copy.deepcopy(state)
            _require(row.get("session_id") == sid, f"{label}: wrong session evidence.")
            _require(
                row.get("request_telemetry_context_seen") is True,
                f"{label}: request telemetry context sentinel missing.",
            )
            _require(
                row.get("action_result_capture_seen") is True
                and isinstance(action_result, dict)
                and isinstance(action_result.get("action"), str)
                and bool(action_result.get("action")),
                f"{label}: engine action result/resolved action unavailable.",
            )
            _require(row.get("model") == MODEL_NAME and
                     type(row.get("model_calls")) is int and
                     row.get("observed_model_calls") == row.get("model_calls") and
                     0 <= row["model_calls"] <= MAX_MODEL_CALLS_PER_TURN,
                     f"{label}: model identity/call limit failed.")
            fallback_candidate = early_fallback
            safety_tier = early_tier
            if fallback_candidate:
                _require(isinstance(early_safety.get("reason_code"), str),
                         f"{label}: safety repair/fallback reason unavailable.")
            _require(
                isinstance(early_safety.get("tier"), str)
                and isinstance(early_safety.get("handling"), str)
                and isinstance(early_safety.get("reason_code"), str)
                and isinstance(early_scope, str)
                and early_scope != "unavailable",
                f"{label}: safety tier/handling/reason/scope classification unavailable.",
            )
            budget_exempt = early_budget_exempt
            if fallback_candidate and not budget_exempt:
                unplanned_fallbacks += 1
                _require(unplanned_fallbacks <= 2,
                         "More than two fallback candidates in ordinary play.")
            http_state = turn.get("state", {})
            _require(isinstance(http_state, dict), f"{label}: missing public state.")
            _require(isinstance(row.get("state"), dict),
                     f"{label}: missing sanitized audit state.")
            _require(
                isinstance(narration, str) and narration.strip()
                and "traceback" not in narration.casefold()
                and "debug fallback" not in narration.casefold(),
                f"{label}: empty/debug fallback narration.",
            )
            return turn

        last_state: list[dict[str, Any]] = [{}]
        try:
            process, handle = _start(
                port, database, audit, evidence_salt
            )
            health = _ready(process, base)
            _require(health.get("model") == MODEL_NAME, "Health model is not qwen3:8b.")
            with httpx.Client(timeout=20) as client:
                created_response = client.post(
                    f"{base}/api/campaigns",
                    json={"name": f"Playable V1 {uuid.uuid4().hex[:8]}",
                          "campaign_start": START_SELECTION},
                )
                _require(created_response.status_code == 200,
                         f"Campaign creation failed: {created_response.status_code}")
                created = created_response.json()
                campaign_id, session_id = created["campaign_id"], created["session_id"]
                _require(isinstance(created.get("state"), dict),
                         "Campaign creation omitted public state.")
                last_state[0] = _projection(created["state"])
                _require(last_state[0].get("location") == "fr:city:neverwinter",
                         "Campaign did not start in Neverwinter.")

                # 1--6: first city scene and the first dynamic local.
                play(client, session_id, "Etrafıma bakıyorum.", "city look")
                state = evidence_rows[-1]["state_diff"]["after"]
                city = state["location"]
                local = _one_npc(state, city)
                play(client, session_id, "Burada kimler var?", "city presence")
                local_approach = play(client, session_id, f"{local['name']} kişisine yaklaşıyorum; "
                     "merhaba, nasılsın?", "approach and greet first local", local["id"])
                _assert_npc_target(local_approach, local["id"], "first local approach")
                local_name = play(client, session_id, "Adın ne?", "ask first local name", local["id"])
                _assert_npc_target(local_name, local["id"], "first local name")
                local_disclosure = play(client, session_id,
                     "Benim adım Arven; kendimi sana tanıtıyorum, bunu hatırla.",
                     "disclose player name", local["id"])
                _assert_npc_target(local_disclosure, local["id"], "first local disclosure")
                _require(
                    "arven" in str(local_disclosure.get("narration", "")).casefold()
                    and (local_disclosure.get("action_result") or {}).get("status")
                    == "player_name_disclosed",
                    "First NPC Arven disclosure evidence/output was not captured.",
                )
                _require(
                    any(ref.startswith(f"{local['id']}:")
                        for ref in evidence_rows[-1]["player_disclosure_memory_refs"]),
                    "Turn 5 lacked original-local disclosure memory evidence.",
                )
                local_smalltalk = play(client, session_id, "Bugün burada neler oluyor?",
                     "ordinary small talk", local["id"])
                _assert_npc_target(local_smalltalk, local["id"], "first local small talk")

                # 7--12: normal tavern discovery and entry.
                play(client, session_id,
                     "Yakınlarda bir yerel taverna veya han arıyorum.",
                     "discover local tavern")
                state = evidence_rows[-1]["state_diff"]["after"]
                locations = state.get("locations", [])
                _require(isinstance(locations, list),
                         "Location records were not projected.")
                children = [
                    item for item in locations
                    if item.get("id") != "fr:city:neverwinter"
                    and item.get("parent_location_id") == "fr:city:neverwinter"
                    and item.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
                ]
                _require(children, "No procedural local tavern child appeared.")
                tavern = next(
                    (item for item in children
                     if "tavern" in str(item.get("name", "")).casefold()
                     or "han" in str(item.get("name", "")).casefold()),
                    None,
                )
                _require(tavern is not None,
                         "Generated procedural child is not a tavern.")
                tavern_id = tavern["id"]
                tavern_name = tavern.get("name", tavern_id)
                play(client, session_id, f"{tavern_name} içine giriyorum.",
                     "enter discovered tavern")
                _require(
                    evidence_rows[-1]["state_diff"]["after"]["location"] == tavern_id,
                    "Direct tavern entry did not enter the discovered child.",
                )
                play(client, session_id, "İçeriye ve çevreme bakıyorum.", "tavern look")
                state = evidence_rows[-1]["state_diff"]["after"]
                bartender = _one_npc(state, tavern_id, role="Barmen")
                play(client, session_id, "Burada kimler var?", "tavern presence")
                bartender_approach = play(client, session_id, f"{bartender['name']} kişisine yaklaşıyorum.",
                     "approach bartender", bartender["id"])
                _assert_npc_target(bartender_approach, bartender["id"], "bartender approach")
                bartender_name = play(client, session_id, "Adın ne?", "ask bartender name", bartender["id"])
                _assert_npc_target(bartender_name, bartender["id"], "bartender name")

                # 13--18: persistent feature and addressable background referent.
                bartender_smalltalk = play(client, session_id, "Bugün günün nasıl gidiyor?",
                     "bartender small talk", bartender["id"])
                _assert_npc_target(bartender_smalltalk, bartender["id"], "bartender small talk")
                feature = _one_feature(evidence_rows[-1]["state_diff"]["after"], tavern_id)
                play(client, session_id, f"{feature['name']} yanına oturuyorum.",
                     "sit at presented table", feature["id"])
                sit_action = evidence_rows[-1]["state_diff"]["after"].get(
                    "scene", {}).get("player_position", {})
                _require(sit_action.get("target_id") == feature["id"],
                         "Sit did not resolve the submitted table feature target.")
                inspected = play(
                    client, session_id,
                    f"{feature['name']} üzerindeki ayrıntıyı inceliyorum.",
                    "inspect harmless feature", feature["id"],
                )
                inspected_action = inspected.get("action_result") or {}
                _require(
                    inspected_action.get("action") == "inspect"
                    and inspected_action.get("target_id") == feature["id"],
                    "Inspect action did not resolve the selected public feature.",
                )
                referents = evidence_rows[-1]["state_diff"]["after"].get(
                    "scene", {}).get("referents", [])
                _require(referents, "No dynamic background referent was presented.")
                referent = next((x for x in referents if x.get("lifecycle") == "presented"), None)
                _require(referent is not None, "Background referent was not addressable.")
                alias = referent.get("addressable_alias")
                _require(isinstance(alias, str) and alias.strip(),
                         "Background referent had no public addressable alias.")
                play(client, session_id, f"{alias} etkinliğine dikkat ediyorum.",
                     "notice background referent")
                play(client, session_id, f"{alias} kişisine yaklaşıyorum.",
                     "promote background referent")
                promoted_state = evidence_rows[-1]["state_diff"]["after"]
                promoted = next(
                    (ref for ref in promoted_state["scene"]["referents"]
                     if ref.get("id") == referent["id"]),
                    None,
                )
                _require(promoted and promoted.get("lifecycle") == "promoted"
                         and promoted.get("promoted_npc_id"),
                         "Background referent did not reach promoted lifecycle.")
                promoted_npc_id = promoted["promoted_npc_id"]
                follow = play(client, session_id, "Onunla kısa bir selamlaşıyorum.",
                              "follow up promoted referent", promoted_npc_id)
                follow_state = evidence_rows[-1]["state_diff"]["after"]
                follow_scene = follow_state["scene"]
                follow_refs = [ref for ref in follow_scene["referents"]
                               if ref.get("id") == referent["id"]]
                _require(follow_refs and follow_refs[0].get("promoted_npc_id")
                         == promoted_npc_id,
                         "Promoted referent follow-up lost its stable target.")

                # 19--24: anchored street, guard, return and pre-restart snapshot.
                play(client, session_id, "Tavernadan çıkıp bağlı sokağa çıkıyorum.",
                     "leave tavern")
                street = evidence_rows[-1]["state_diff"]["after"]["location"]
                play(client, session_id, "Sokakta şu anda ne oluyor, etrafıma bakıyorum.",
                     "observe street")
                state = evidence_rows[-1]["state_diff"]["after"]
                guard = _one_npc(state, street, role="Muhafız")
                guard_approach = play(client, session_id, f"{guard['name']} kişisine yaklaşıyorum.",
                     "approach displayed guard", guard["id"])
                _assert_npc_target(guard_approach, guard["id"], "guard approach")
                guard_question = play(client, session_id, "Bugün yol ve güvenlik nasıl?",
                     "ordinary guard question", guard["id"])
                _assert_npc_target(guard_question, guard["id"], "guard question")
                play(client, session_id, f"{tavern_name} içine giriyorum.",
                     "return to same tavern")
                return_state = evidence_rows[-1]["state_diff"]["after"]
                _require(return_state.get("location") == tavern_id,
                         "Return did not reach the exact discovered tavern.")
                _require(
                    any(npc.get("id") == bartender["id"]
                        and npc.get("location") == tavern_id
                        for npc in return_state.get("npcs", []))
                    and any(feature_item.get("id") == feature["id"]
                            and feature_item.get("location") == tavern_id
                            for feature_item in return_state.get("features", [])),
                    "Returned tavern did not retain bartender/feature IDs.",
                )
                continuity = play(client, session_id,
                     f"{bartender['name']} kişisini ve {feature['name']} masasını hatırlıyor musun?",
                     "recall tavern continuity", bartender["id"])
                _assert_npc_target(continuity, bartender["id"], "tavern continuity")
                _require(len(evidence_rows) == 24, "Pre-restart turn count is not 24.")
                before_restart = copy.deepcopy(evidence_rows[-1]["state_diff"]["after"])
                _require(
                    before_restart.get("location") == tavern_id,
                    "Pre-restart player location is not the discovered tavern.",
                )
                tavern_record = _record_by_id(
                    before_restart, "locations", tavern_id
                )
                starting_city_id = city
                _require(
                    tavern_record.get("parent_location_id") == starting_city_id,
                    "Discovered tavern is not attached to the starting city.",
                )
                starting_city = _record_by_id(
                    before_restart, "locations", starting_city_id
                )
                starting_city_name = starting_city.get("name", starting_city_id)
                starting_table_id = feature["id"]
                starting_table_name = feature.get("name", starting_table_id)
                before_audit = _latest(audit)
                before_lore = before_audit.get("lore")
                before_memory_refs = before_audit.get("memory_snapshot_refs", [])
                before_disclosure_memory_refs = before_audit.get(
                    "player_disclosure_memory_refs", []
                )
                detail_before_response = client.get(
                    f"{base}/api/campaigns/{campaign_id}", timeout=20
                )
                _require(detail_before_response.status_code == 200,
                         "Could not read the pre-restart campaign snapshot.")
                detail_before = detail_before_response.json()
                _stop(process, handle)
                process = handle = None

                process, handle = _start(
                    port, database, audit, evidence_salt,
                )
                health = _ready(process, base)
                _require(health.get("model") == MODEL_NAME, "Restarted model is not qwen3:8b.")
                resumed_response = client.post(f"{base}/api/campaigns/{campaign_id}/resume")
                _require(resumed_response.status_code == 200, "Campaign resume failed.")
                resumed = resumed_response.json()
                session_id = resumed["session_id"]
                resumed_state = resumed["state"]
                _require(session_id != created["session_id"],
                         "Resume did not create a new session ID.")
                detail_after_response = client.get(
                    f"{base}/api/campaigns/{campaign_id}", timeout=20
                )
                _require(detail_after_response.status_code == 200,
                         "Could not read the post-restart campaign snapshot.")
                detail_after = detail_after_response.json()
                _require(resumed.get("campaign_id") == campaign_id
                         and detail_after.get("campaign", {}).get("name")
                         == detail_before.get("campaign", {}).get("name"),
                         "Campaign identity/name changed across API restart.")
                resume_audit = _latest_event(audit, "resume")
                before_public_state = detail_before.get("state")
                equal_public_state = resumed_state == before_public_state
                before_public_projection = _projection(before_public_state)
                resumed_projection = _projection(resumed_state)
                equal_sanitized_state = (
                    resumed_projection == before_public_projection
                )
                equal_resume_state = resume_audit.get("state") == before_restart
                equal_resume_lore = resume_audit.get("lore") == before_lore
                equal_resume_memory = (
                    resume_audit.get("memory_snapshot_refs", []) == before_memory_refs
                    and resume_audit.get("player_disclosure_memory_refs", [])
                    == before_disclosure_memory_refs
                )
                equal_resume_history = resumed.get("history") == detail_before.get("history")
                equal_resume_combat = (
                    resumed.get("combat_history") == detail_before.get("combat_history")
                )
                _append(report_root / "resume-comparison.json", {
                    "campaign_id": campaign_id, "old_session_id": created["session_id"],
                    "new_session_id": session_id,
                    "equal_public_state": equal_public_state,
                    "equal_sanitized_state": equal_sanitized_state,
                    "sanitized_state_mismatch_paths": (
                        _difference_paths(
                            resumed_projection, before_public_projection
                        )
                        if not equal_sanitized_state else []
                    ),
                    "equal_state": equal_resume_state,
                    "equal_lore": equal_resume_lore,
                    "equal_memory": equal_resume_memory,
                    "equal_history": equal_resume_history,
                    "equal_combat_history": equal_resume_combat,
                    "history_count": len(resumed.get("history", [])),
                    "combat_history_count": len(resumed.get("combat_history", [])),
                })
                _require(equal_public_state,
                         "Full public campaign state changed across API restart.")
                _require(equal_sanitized_state,
                         "Sanitized state/IDs changed across API restart.")
                _require(equal_resume_history,
                         "Campaign history changed across API restart.")
                _require(equal_resume_combat,
                         "Combat history changed across API restart.")
                _require(resume_audit.get("session_id") == session_id
                         and equal_resume_state and equal_resume_lore
                         and equal_resume_memory,
                         "Fresh resume audit changed sanitized state or lore binding.")

                # 25--30: return, local recall, false recall, merchant, limitation.
                play(client, session_id,
                     f"{tavern_name} içindeki {starting_table_name} masasından "
                     f"{starting_city_name} şehrine dönüyorum.",
                     "return to starting city")
                _require(evidence_rows[-1]["state_diff"]["after"].get("location")
                         == starting_city_id,
                         "Turn 25 did not return to the starting city.")
                original_local = _record_by_id(
                    before_restart, "npcs", local["id"]
                )
                _require(original_local.get("id") == local["id"],
                         "Original turn-5 local was not retained.")
                local_recall = play(
                    client, session_id,
                    f"{original_local['name']} kişisine benim adımı hatırlıyor musun diye soruyorum.",
                    "recall original turn-5 local", original_local["id"])
                _assert_npc_target(local_recall, original_local["id"],
                                   "original local recall")
                local_recall_text = str(local_recall.get("narration", "")).casefold()
                _require("arven" in local_recall_text,
                         "Original local recall did not contain Arven.")
                _require(
                    any(ref.startswith(f"{original_local['id']}:")
                        for ref in evidence_rows[-1]["player_disclosure_memory_refs"]),
                    "Turn 26 lacked original-local disclosure memory evidence.",
                )
                restarted_audit_lore = _latest(audit).get("lore")
                _require(
                    isinstance(restarted_audit_lore, dict)
                    and restarted_audit_lore.get("binding_status")
                    == before_lore.get("binding_status")
                    and restarted_audit_lore.get("world_id") == before_lore.get("world_id")
                    and restarted_audit_lore.get("region_id") == before_lore.get("region_id")
                    and set(restarted_audit_lore.get("procedural_entity_refs", []))
                    >= set(before_lore.get("procedural_entity_refs", [])),
                    "Restarted API audit did not preserve lore/procedural ID binding.",
                )
                other = _one_npc(evidence_rows[-1]["state_diff"]["after"],
                                 starting_city_id, exclude={original_local["id"]})
                false_recall = play(client, session_id,
                     f"{other['name']} kişisine benim adımı daha önce söylemiş miydim diye soruyorum.",
                     "false recall challenge", other["id"])
                _assert_npc_target(false_recall, other["id"], "false recall")
                false_text = str(false_recall.get("narration", "")).casefold()
                _require(
                    "arven" not in false_text,
                    "Distinct NPC falsely claimed to remember Arven.",
                )
                other_after = evidence_rows[-1]["state_diff"]["after"]
                _require(
                    not any(ref.startswith(f"{other['id']}:")
                            for ref in evidence_rows[-1]["player_disclosure_memory_refs"]),
                    "False recall created a disclosure ref for the distinct NPC.",
                )
                _require(
                    not any(
                        "merchant" in str(npc.get("role", "")).casefold()
                        or "tüccar" in str(npc.get("role", "")).casefold()
                        for npc in other_after.get("npcs", [])
                    ) and not other_after.get("shops"),
                    "Merchant appeared before the required ordinary search turn.",
                )
                play(client, session_id, "Burada sıradan bir yerel tüccar bulabilir miyim?",
                     "discover ordinary local merchant")
                state = evidence_rows[-1]["state_diff"]["after"]
                merchant = _one_npc(state, state["location"], role="merchant")
                merchant_conversation = play(
                    client, session_id, f"{merchant['name']} kişisine yaklaşıp işinin nasıl "
                    "gittiğini soruyorum.", "approach and converse merchant", merchant["id"])
                _assert_npc_target(merchant_conversation, merchant["id"],
                                   "merchant approach and conversation")
                before_purchase = _projection(last_state[0])
                play(client, session_id,
                     f"{merchant['name']} kişisinden desteklenmeyen bir ürünü satın almak istiyorum.",
                     "unsupported purchase", merchant["id"])
                _require(_projection(evidence_rows[-1]["state_diff"]["after"])["inventory"]
                         == before_purchase["inventory"],
                         "Unsupported purchase changed inventory.")
                after_purchase = evidence_rows[-1]["state_diff"]["after"]
                _require(after_purchase["shops"] == before_purchase["shops"]
                         and after_purchase["currency"] == before_purchase["currency"]
                         and after_purchase["npcs"] == before_purchase["npcs"],
                         "Unsupported purchase changed shop or currency state.")

                # 31--36: loaded canon, refusal/recovery, supported check and revisit.
                loaded = play(
                    client, session_id,
                    "What is Dagult Neverember's current role in Neverwinter?",
                    "loaded canon question",
                )
                _require(evidence_rows[-1]["retrieved_fact_ids"],
                         "Loaded canon question did not retrieve a fact ID.")
                loaded_text = str(loaded.get("narration", "")).casefold()
                _require(
                    "dagult neverember" in loaded_text
                    and "neverwinter" in loaded_text
                    and ("lord" in loaded_text or "current" in loaded_text),
                    "Loaded canon narration did not ground the retrieved current-role fact.",
                )
                before_challenge = _campaign_projection_without_turn_index(
                    evidence_rows[-1]["state_diff"]["after"]
                )
                play(client, session_id,
                     "Neverwinterdan resmi bir güzergahın kesin mesafesini söyle.",
                     "unsupported route challenge")
                route_safety = evidence_rows[-1].get("safety", {})
                _require(
                    route_safety.get("reason_code") == "UNVERIFIED_LORE_CLAIM"
                    and route_safety.get("handling") == "python_fallback",
                    "Unsupported route challenge was not stopped by the lore guard.",
                )
                _require(_campaign_projection_without_turn_index(
                             evidence_rows[-1]["state_diff"]["after"])
                         == before_challenge,
                         "Unsupported route challenge mutated campaign state.")
                play(client, session_id,
                     "Uydurduğum Kral Vharion ve Velmoryx adlı tanrı Forgotten Realms "
                     "kanonunda mı?",
                     "invented ruler/deity challenge")
                _require(_campaign_projection_without_turn_index(
                             evidence_rows[-1]["state_diff"]["after"])
                         == before_challenge,
                         "Invented deity challenge mutated campaign state.")
                recovery = play(client, session_id,
                     "Tekrar etrafıma bakıyorum; reddin ardından "
                     "sıradan dünyayı anlat.", "ordinary recovery")
                _require(
                    recovery.get("narration")
                    and not any(term in str(recovery.get("narration")).casefold()
                                for term in ("cannot answer", "bilmiyorum", "uydurma")),
                    "Turn 34 did not recover with ordinary playable narration.",
                )
                skill_turn = play(
                    client, session_id,
                    f"Investigation becerimi kullanarak {feature['name']} "
                    "ayrıntılarını araştırıyorum.",
                    "supported perception investigation",
                )
                skill_action = skill_turn.get("skill_check_result") or {}
                _require(
                    all(skill_action.get(key) is not None for key in
                        ("skill", "ability", "d20", "total", "dc", "outcome"))
                    and skill_action.get("skill") in {"Perception", "Investigation"}
                    and (skill_turn.get("action_result") or {}).get("action") == "skill_check",
                    "Turn 35 did not return a structured Perception/Investigation result.",
                )
                play(
                    client,
                    session_id,
                    f"{tavern['name']} içine giriyorum.",
                    "return to tavern for final continuity check",
                )
                final_state = evidence_rows[-1]["state_diff"]["after"]
                _require(final_state.get("location") == tavern_id
                         and any(npc.get("id") == bartender["id"]
                                 and npc.get("location") == tavern_id
                                 for npc in final_state.get("npcs", []))
                         and any(item.get("id") == feature["id"]
                                 and item.get("location") == tavern_id
                                 for item in final_state.get("features", [])),
                          "Final return did not reach the original tavern with its original NPC and feature IDs.")
                _require(len(evidence_rows) == 36, "Smoke did not complete 36 turns.")
                result.update(
                    status="REVIEW_PENDING",
                    campaign_id=campaign_id,
                    restart_state_equal=equal_resume_state,
                    restart_lore_equal=equal_resume_lore,
                    restart_memory_equal=equal_resume_memory,
                    restart_history_equal=equal_resume_history,
                    restart_combat_history_equal=equal_resume_combat,
                    pre_challenge_state=before_challenge,
                    error="36-turn mechanics completed, but release evidence is incomplete; "
                          "mechanical/manual PASS is not claimed.",
                )
        except SmokeFailure as error:
            result.update(status="BLOCKED / LIVE PLAYABILITY UNVERIFIED",
                          error=str(error))
        except Exception as error:
            result.update(
                status="BLOCKED / LIVE PLAYABILITY UNVERIFIED",
                error=f"{type(error).__name__}: {error}",
            )
        finally:
            if str(result.get("status", "")).startswith("BLOCKED"):
                capture_isolated_failure(
                    report_root,
                    handle,
                    base=base,
                    session_id=session_id,
                    evidence_rows=evidence_rows,
                )
            if process is not None:
                _stop(process, handle)
        result["evidence_lifecycle"] = (
            "sanitized evidence is append-only outside the temporary database directory"
        )
        gaps: list[str] = []
        usage_values = [
            row.get("token_usage") for row in evidence_rows
            if isinstance(row.get("token_usage"), dict)
        ]
        if len(usage_values) == len(evidence_rows) and usage_values:
            result["token_usage"] = {
                "prompt_eval_count": sum(item["prompt_eval_count"] for item in usage_values
                                         if type(item.get("prompt_eval_count")) is int),
                "eval_count": sum(item["eval_count"] for item in usage_values
                                  if type(item.get("eval_count")) is int),
                "scope": "aggregate of per-turn isolated telemetry",
            }
        for row in evidence_rows:
            usage = row.get("token_usage")
            if not isinstance(usage, dict) or not all(
                type(usage.get(key)) is int for key in ("prompt_eval_count", "eval_count")
            ):
                gaps.append("numeric token telemetry missing on one or more turns")
                break
        for turn_row in evidence_rows:
            if turn_row.get("request_telemetry_context_seen") is not True:
                gaps.append("request telemetry context sentinel missing")
            action_result = turn_row.get("action_result")
            if (
                turn_row.get("action_result_capture_seen") is not True
                or not isinstance(action_result, dict)
                or not isinstance(action_result.get("action"), str)
                or not action_result.get("action")
                or turn_row.get("resolved_action") != action_result.get("action")
            ):
                gaps.append("engine action result/resolved action missing")
            gaps.extend(_proposal_trace_gaps(turn_row))
            safety = turn_row.get("safety")
            safety = safety if isinstance(safety, dict) else {}
            if not all(
                isinstance(safety.get(field), str) and safety.get(field)
                for field in ("tier", "handling", "reason_code", "scope")
            ) or safety.get("scope") == "unavailable":
                gaps.append("safety tier/handling/reason/scope incomplete")
        gaps = list(dict.fromkeys(gaps))
        result["evidence_incomplete"] = gaps
        result["review_status"] = "pending_human_review"
        result["narration_retention"] = (
            "omitted from persistent reports; transient CLI output only with "
            "--review-narrations"
        )
        result["ordinary_fallback_candidate_count"] = unplanned_fallbacks
        if gaps:
            result["status"] = "BLOCKED / EVIDENCE_INCOMPLETE"
            result["error"] = "; ".join(gaps)
        persisted_result = dict(result)
        persisted_result["turns"] = [
            _persisted_turn(row) for row in evidence_rows
        ]
        (report_root / "summary.json").write_text(
            json.dumps(
                _sanitize_persistent_value(persisted_result),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
    return result


def run_checkpoint_replay(
    checkpoint: Path,
    message: str,
    label: str,
    report_root: Path,
) -> dict[str, Any]:
    """Play one turn from a copy of a disposable checkpoint. The source file stays unchanged."""
    source_bytes = checkpoint.read_bytes()
    _loaded, copy_path = load_replay_checkpoint_copy(checkpoint)
    flags = (
        _loaded.get("campaign_payload", {})
        .get("engine_save", {})
        .get("world_state", {})
        .get("flags", {})
    )
    expected_turn = flags.get("turn_index") if isinstance(flags, dict) else None
    expected_turn = expected_turn if type(expected_turn) is int else None
    report_root.mkdir(parents=True, exist_ok=False)
    evidence = report_root / "api-audit.jsonl"
    port = _port()
    base = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment["AI_DND_SMOKE_EVIDENCE_SALT"] = uuid.uuid4().hex
    global _SMOKE_DIAGNOSTIC_PATH
    process: subprocess.Popen[bytes] | None = None
    handle: Any = None
    session_id = ""
    failure: BaseException | None = None
    turn: dict[str, Any] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="ai-dnd-replay-") as directory:
            database = Path(directory) / "campaigns.sqlite3"
            environment["AI_DND_CAMPAIGN_DB"] = str(database)
            try:
                handle = tempfile.TemporaryFile(mode="w+b")
                process = subprocess.Popen(
                    [
                        sys.executable, "-m",
                        "api.tests.live_playable_living_world_v1_smoke",
                        "--serve", str(port), str(database), str(evidence),
                        str(copy_path),
                    ],
                    cwd=AI_DND_DIR, env=environment, stdout=handle,
                    stderr=subprocess.STDOUT,
                )
                _ready(process, base)
                session_file = report_root / "replay-session.json"
                session_id = json.loads(
                    session_file.read_text(encoding="utf-8")
                )["session_id"]
                with httpx.Client() as client:
                    try:
                        turn = measured_turn(
                            client, base, session_id, message, None,
                            report_root, label,
                        )
                    except Exception as error:
                        failure = error
                if failure is not None:
                    capture_isolated_failure(
                        report_root,
                        handle,
                        base=base,
                        session_id=session_id,
                        evidence_rows=[{
                            "state_diff": {"after": {"turn_index": expected_turn}},
                        }] if expected_turn is not None else [],
                    )
                else:
                    previous = _SMOKE_DIAGNOSTIC_PATH
                    _SMOKE_DIAGNOSTIC_PATH = report_root / "diagnostic-events.jsonl"
                    try:
                        _flush_diagnostic({
                            "event": "rollback_probe",
                            **probe_rollback_status(base, session_id, expected_turn),
                        })
                    finally:
                        _SMOKE_DIAGNOSTIC_PATH = previous
            finally:
                if process is not None and handle is not None:
                    _stop(process, handle)
                elif handle is not None:
                    handle.close()
    finally:
        copy_path.unlink(missing_ok=True)
    if checkpoint.read_bytes() != source_bytes:
        raise SmokeReplayError("Replay changed the source checkpoint.")
    return {
        "report_path": str(report_root),
        "completed": failure is None,
        "error_type": type(failure).__name__ if failure is not None else None,
        "turn_returned": isinstance(turn, dict),
    }


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--serve":
        checkpoint = Path(sys.argv[5]) if len(sys.argv) >= 6 else None
        _serve(int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), checkpoint)
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "--finalize-review":
        arguments = sys.argv[2:]
        if (
            not arguments
            or len(arguments) > 2
            or any(argument != "--approve" for argument in arguments[1:])
            or arguments[1:].count("--approve") > 1
        ):
            print(json.dumps({
                "execution_status": "UNVERIFIED",
                "objective_validation_result": "NOT_RUN",
                "manual_review_status": "NOT_APPROVED",
                "final_gate_status": "BLOCKED",
                "error": (
                    "Usage: --finalize-review <report-dir> [--approve]"
                ),
            }, ensure_ascii=False))
            return 2
        try:
            result = finalize_review(
                arguments[0],
                approve="--approve" in arguments[1:],
                reports_root=(
                    AI_DND_DIR / "reports" / "playable-living-world-v1-smokes"
                ),
                expected_labels=EXPECTED_LABELS,
                budget_exempt_turn_ids=BUDGET_EXEMPT_TURN_IDS,
                proposal_trace_validator=_proposal_trace_gaps,
            )
        except ReviewFinalizationError as error:
            print(json.dumps({
                "execution_status": "UNVERIFIED",
                "objective_validation_result": "FAIL",
                "manual_review_status": "NOT_APPROVED",
                "final_gate_status": "BLOCKED",
                "error": str(error),
            }, ensure_ascii=False))
            return 1
        except Exception:
            print(json.dumps({
                "execution_status": "UNVERIFIED",
                "objective_validation_result": "FAIL",
                "manual_review_status": "NOT_APPROVED",
                "final_gate_status": "BLOCKED",
                "error": "The smoke report could not be finalized safely.",
            }, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("final_gate_status") == "PASS" else 1
    review_narrations = "--review-narrations" in sys.argv[1:]
    try:
        result = run_smoke()
    except Exception as error:
        result = {
            "status": "BLOCKED / REPORT_CREATION_FAILURE",
            "model": MODEL_NAME,
            "campaign_database": "temporary_disposable",
            "review_status": "pending_human_review",
            "error": f"{type(error).__name__}: details redacted",
            "evidence_incomplete": [
                "No sanitized report could be created; no live result is claimed."
            ],
        }
    if review_narrations:
        print("TRANSIENT NARRATION REVIEW (not written to report files)")
        for row in result.get("turns", []):
            narration = row.get("narration") if isinstance(row, dict) else None
            if isinstance(narration, str):
                print(json.dumps({
                    "turn": row.get("turn"),
                    "label": row.get("label"),
                    "narration": narration,
                }, ensure_ascii=False))
    printable = dict(result)
    if isinstance(result.get("turns"), list):
        printable["turns"] = [
            _persisted_turn(row) if isinstance(row, dict) else row
            for row in result["turns"]
        ]
    print(json.dumps(
        _sanitize_persistent_value(printable),
        ensure_ascii=False,
        indent=2,
    ))
    # This harness intentionally cannot claim a release pass while required
    # telemetry fields remain unavailable.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())