"""Manual sign-off for sanitized Playable Living World V1 smoke evidence."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any


MODEL_NAME = "qwen3:8b"
MAX_MODEL_CALLS_PER_TURN = 2
MAX_ORDINARY_FALLBACKS = 2
MAX_EVIDENCE_FILE_BYTES = 16 * 1024 * 1024
ATTESTATION_FILENAME = "manual-review-attestation.json"
NARRATION_REVIEW_FILENAME = "narration-review.json"
SOURCE_EVIDENCE_FILENAMES = (
    "api-audit.jsonl",
    "resume-comparison.json",
    "summary.json",
    "turn-evidence.jsonl",
)
EXPECTED_PENDING_ERROR = (
    "36-turn mechanics completed, but release evidence is incomplete; "
    "mechanical/manual PASS is not claimed."
)
_REPORT_ID_RE = re.compile(r"\d+-[a-f0-9]{8}\Z")
_TRANSIENT_FIELDS = frozenset({
    "input", "player_input", "message", "user_message",
    "narration", "prompt", "completion", "model_prompt",
    "model_completion", "raw_prompt", "raw_completion",
    "memory", "memory_text", "raw_memory", "raw_memory_text",
    "messages", "conversation", "chat_history", "history",
    "request_body", "response_body",
    "private_text", "private_prompt", "private_memory",
    "hidden_memory", "hidden_memories", "withheld_lore",
    "auth_data", "authorization", "secret", "credentials",
})
_RESUME_SUMMARY_FIELDS = {
    "restart_state_equal": "equal_state",
    "restart_lore_equal": "equal_lore",
    "restart_memory_equal": "equal_memory",
    "restart_history_equal": "equal_history",
    "restart_combat_history_equal": "equal_combat_history",
}


class ReviewFinalizationError(ValueError):
    """Raised when smoke evidence cannot safely receive manual sign-off."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _decode_json(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ReviewFinalizationError(
            "A required sanitized evidence file is malformed."
        ) from None


def _decode_jsonl(data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ReviewFinalizationError(
            "A required sanitized evidence file is malformed."
        ) from None
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise ReviewFinalizationError(
            "A required sanitized evidence file is malformed."
        )
    rows: list[dict[str, Any]] = []
    for line in lines:
        value = _decode_json(line.encode("utf-8"))
        if not isinstance(value, dict):
            raise ReviewFinalizationError(
                "A required sanitized evidence file is malformed."
            )
        rows.append(value)
    return rows


def _contains_transient_field(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            isinstance(key, str)
            and (
                key.casefold() in _TRANSIENT_FIELDS
                or _contains_transient_field(item)
            )
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_transient_field(item) for item in value)
    return False


def _resolve_report_dir(
    report_arg: str | Path,
    reports_root: str | Path,
) -> tuple[Path, Path]:
    try:
        root = Path(reports_root).resolve(strict=True)
    except OSError:
        raise ReviewFinalizationError(
            "The smoke report directory is unavailable."
        ) from None
    supplied = Path(report_arg).expanduser()
    if supplied.is_absolute():
        candidate = supplied
    elif len(supplied.parts) == 1:
        candidate = root / supplied
    elif supplied.parts[:2] == (
        "reports", "playable-living-world-v1-smokes",
    ):
        candidate = root.parent.parent / supplied
    elif supplied.parts[:3] == (
        "ai-dnd", "reports", "playable-living-world-v1-smokes",
    ):
        candidate = root.parent.parent.parent / supplied
    else:
        candidate = Path.cwd() / supplied
    try:
        if candidate.is_symlink():
            raise ReviewFinalizationError(
                "The smoke report path is not a valid report directory."
            )
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise ReviewFinalizationError(
            "The smoke report directory is unavailable."
        ) from None
    if (
        resolved.parent != root
        or not resolved.is_dir()
        or not _REPORT_ID_RE.fullmatch(resolved.name)
    ):
        raise ReviewFinalizationError(
            "The smoke report path is not a valid report directory."
        )
    return root, resolved


def _read_source_files(
    report_dir: Path,
    *,
    narration_review_required: bool = False,
) -> dict[str, bytes]:
    source: dict[str, bytes] = {}
    filenames = list(SOURCE_EVIDENCE_FILENAMES)
    if narration_review_required:
        filenames.append(NARRATION_REVIEW_FILENAME)
    for filename in filenames:
        path = report_dir / filename
        try:
            info = path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_size > MAX_EVIDENCE_FILE_BYTES
            ):
                raise ReviewFinalizationError(
                    "A required sanitized evidence file is unavailable."
                )
            source[filename] = path.read_bytes()
        except OSError:
            raise ReviewFinalizationError(
                "A required sanitized evidence file is unavailable."
            ) from None
    return source


def _file_digests(source: dict[str, bytes]) -> dict[str, str]:
    return {
        filename: hashlib.sha256(source[filename]).hexdigest()
        for filename in source
    }


def _combined_digest(file_digests: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for filename in file_digests:
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digests[filename].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _state_records(state: Any, field: str) -> list[dict[str, Any]]:
    values = state.get(field) if isinstance(state, dict) else None
    return [item for item in values if isinstance(item, dict)] if isinstance(
        values, list
    ) else []


def _record_by_id(state: Any, field: str, identity: str) -> dict[str, Any]:
    return next(
        (
            item for item in _state_records(state, field)
            if item.get("id") == identity
        ),
        {},
    )


def _fallback_candidate(safety: Any) -> bool:
    if not isinstance(safety, dict):
        return False
    tier = safety.get("tier")
    if tier == "tier_2_repair":
        return True
    if tier != "tier_3_fallback":
        return False
    return safety.get("handling") not in {
        "python_scene_response",
        "python_memory_response",
    }


def _turn_index_without_expected_advance(state: Any) -> Any:
    if not isinstance(state, dict):
        return state
    result = dict(state)
    result.pop("turn_index", None)
    return result


def _validate_narration_review(
    report_dir: Path,
    source: dict[str, bytes],
    summary: dict[str, Any],
    turns: list[dict[str, Any]],
    expected_labels: Sequence[str],
) -> dict[str, Any]:
    review = _decode_json(source[NARRATION_REVIEW_FILENAME])
    run = review.get("run") if isinstance(review, dict) else None
    review_turns = review.get("turns") if isinstance(review, dict) else None
    if not isinstance(summary, dict):
        raise ReviewFinalizationError(
            "The narration-review evidence is missing or incomplete."
        )
    summary_reference = summary.get("narration_review_evidence")
    if (
        not isinstance(review, dict)
        or type(review.get("schema_version")) is not int
        or review.get("schema_version") != 1
        or not isinstance(run, dict)
        or run.get("report_id") != report_dir.name
        or not isinstance(run.get("git_sha"), str)
        or not run.get("git_sha")
        or not isinstance(run.get("git_branch"), str)
        or not run.get("git_branch")
        or run.get("model") != MODEL_NAME
        or run.get("status") != "finished"
        or type(run.get("expected_turn_count")) is not int
        or run.get("expected_turn_count") != len(expected_labels)
        or type(run.get("recorded_turn_count")) is not int
        or run.get("recorded_turn_count") != len(expected_labels)
        or run.get("evidence_complete") is not True
        or run.get("evidence_gaps") != []
        or not isinstance(review_turns, list)
        or len(review_turns) != len(expected_labels)
        or summary_reference
        != {
            "file": NARRATION_REVIEW_FILENAME,
            "expected_turn_count": len(expected_labels),
            "recorded_turn_count": len(expected_labels),
            "evidence_complete": True,
        }
    ):
        raise ReviewFinalizationError(
            "The narration-review evidence is missing or incomplete."
        )

    reported_calls = 0
    observed_calls = 0
    fallback_turns = 0
    for index, (review_row, turn, label) in enumerate(
        zip(review_turns, turns, expected_labels),
        1,
    ):
        action_result = turn.get("action_result")
        engine_telemetry = (
            review_row.get("engine_telemetry")
            if isinstance(review_row, dict)
            else None
        )
        if (
            not isinstance(review_row, dict)
            or review_row.get("turn") != index
            or review_row.get("label") != label
            or not isinstance(review_row.get("player_input"), str)
            or not review_row.get("player_input").strip()
            or not isinstance(review_row.get("narration"), str)
            or not review_row.get("narration").strip()
            or review_row.get("model") != MODEL_NAME
            or review_row.get("action")
            != (action_result.get("action") if isinstance(action_result, dict) else None)
            or review_row.get("request_target_id") != turn.get("target_id")
            or review_row.get("action_target_id")
            != (
                action_result.get("target_id")
                if isinstance(action_result, dict)
                else None
            )
            or type(review_row.get("model_calls")) is not int
            or review_row.get("model_calls") != turn.get("model_calls")
            or type(review_row.get("observed_model_calls")) is not int
            or review_row.get("observed_model_calls")
            != turn.get("observed_model_calls")
            or review_row.get("safety") != turn.get("safety")
            or review_row.get("evidence_complete") is not True
            or not isinstance(review_row.get("intent_source"), str)
            or not review_row.get("intent_source")
            or not isinstance(review_row.get("narration_source"), str)
            or not review_row.get("narration_source")
            or not isinstance(
                review_row.get("narration_validation_result"), str
            )
            or not review_row.get("narration_validation_result")
            or (
                review_row.get("fallback_reason") is not None
                and not isinstance(review_row.get("fallback_reason"), str)
            )
            or not isinstance(engine_telemetry, dict)
            or engine_telemetry.get("narration_source")
            != review_row.get("narration_source")
            or engine_telemetry.get("intent_source")
            != review_row.get("intent_source")
            or engine_telemetry.get("fallback_reason")
            != review_row.get("fallback_reason")
            or engine_telemetry.get("narration_validation_result")
            != review_row.get("narration_validation_result")
            or engine_telemetry.get("resolved_action_type")
            != review_row.get("resolved_action_type")
            or review_row.get("resolved_action_type")
            != review_row.get("action")
        ):
            raise ReviewFinalizationError(
                "The narration-review evidence conflicts with a sanitized turn."
            )

        call_fields = (
            "intent_model_calls",
            "narration_model_calls",
            "total_model_calls",
            "model_calls",
            "observed_model_calls",
        )
        if any(
            type(review_row.get(field)) is not int or review_row[field] < 0
            for field in call_fields
        ):
            raise ReviewFinalizationError(
                "The narration-review model-call evidence is incomplete."
            )
        if (
            review_row["intent_model_calls"]
            + review_row["narration_model_calls"]
            != review_row["total_model_calls"]
            or review_row["total_model_calls"] != review_row["model_calls"]
            or review_row["model_calls"] != review_row["observed_model_calls"]
            or any(
                engine_telemetry.get(field) != review_row.get(field)
                for field in (
                    "intent_model_calls",
                    "narration_model_calls",
                    "total_model_calls",
                )
            )
        ):
            raise ReviewFinalizationError(
                "The narration-review model-call evidence is inconsistent."
            )
        reported_calls += review_row["model_calls"]
        observed_calls += review_row["observed_model_calls"]
        fallback_turns += int(_fallback_candidate(review_row.get("safety")))

    if (
        type(run.get("model_calls_reported")) is not int
        or run.get("model_calls_reported") != reported_calls
        or type(run.get("model_calls_observed")) is not int
        or run.get("model_calls_observed") != observed_calls
        or type(run.get("fallback_turn_count")) is not int
        or run.get("fallback_turn_count") != fallback_turns
    ):
        raise ReviewFinalizationError(
            "The narration-review run counters are inconsistent."
        )
    return review


def _validate_objective_evidence(
    report_dir: Path,
    source: dict[str, bytes],
    *,
    expected_labels: Sequence[str],
    budget_exempt_turn_ids: Iterable[int],
    proposal_trace_validator: Callable[[dict[str, Any]], list[str]],
    expected_pending_error: str = EXPECTED_PENDING_ERROR,
    narration_review_required: bool = False,
) -> tuple[dict[str, bool], dict[str, Any]]:
    summary = _decode_json(source["summary.json"])
    resume = _decode_json(source["resume-comparison.json"])
    turns = _decode_jsonl(source["turn-evidence.jsonl"])
    audit = _decode_jsonl(source["api-audit.jsonl"])
    narration_review = (
        _validate_narration_review(
            report_dir,
            source,
            summary,
            turns,
            expected_labels,
        )
        if narration_review_required
        else None
    )
    parsed_sources = (summary, resume, turns, audit)
    if any(_contains_transient_field(item) for item in parsed_sources):
        raise ReviewFinalizationError(
            "The source report contains fields that are not allowed in sanitized evidence."
        )
    if not isinstance(summary, dict) or not isinstance(resume, dict):
        raise ReviewFinalizationError(
            "The smoke report does not contain complete objective evidence."
        )

    checks: dict[str, bool] = {}

    if (
        summary.get("status") != "REVIEW_PENDING"
        or summary.get("review_status") != "pending_human_review"
        or summary.get("error") != expected_pending_error
        or summary.get("campaign_database") != "temporary_disposable"
        or summary.get("model") != MODEL_NAME
    ):
        raise ReviewFinalizationError(
            "The source smoke run did not complete successfully."
        )
    if summary.get("evidence_incomplete") != []:
        raise ReviewFinalizationError(
            "The smoke report has required evidence gaps."
        )
    try:
        reported_path = Path(summary.get("report_path", "")).resolve(strict=True)
    except (OSError, TypeError, ValueError):
        raise ReviewFinalizationError(
            "The smoke report identity is inconsistent."
        ) from None
    if reported_path != report_dir:
        raise ReviewFinalizationError(
            "The smoke report identity is inconsistent."
        )
    checks["execution_complete"] = True
    checks["model_qwen3_8b"] = True
    checks["evidence_complete"] = True

    expected_labels = tuple(expected_labels)
    exempt_turns = frozenset(budget_exempt_turn_ids)
    expected_turn_count = len(expected_labels)
    if (
        expected_turn_count < 1
        or len(set(expected_labels)) != expected_turn_count
        or any(not isinstance(label, str) or not label for label in expected_labels)
        or (
            expected_turn_count == 36
            and sorted(exempt_turns) != [27, 30, 31, 32, 33]
        )
        or any(
            type(turn_id) is not int or not 1 <= turn_id <= expected_turn_count
            for turn_id in exempt_turns
        )
    ):
        raise ReviewFinalizationError(
            "The release-gate validator configuration is invalid."
        )
    summary_turns = summary.get("turns")
    if (
        not isinstance(summary_turns, list)
        or len(summary_turns) != expected_turn_count
        or len(turns) != expected_turn_count
        or summary_turns != turns
    ):
        raise ReviewFinalizationError(
            f"The smoke report does not contain exactly {expected_turn_count} consistent turns."
        )
    turn_by_label: dict[str, dict[str, Any]] = {}
    ordinary_fallbacks = 0
    for index, (row, expected_label) in enumerate(zip(turns, expected_labels), 1):
        if (
            row.get("turn") != index
            or row.get("label") != expected_label
            or "failure" in row
            or row.get("diagnostic_evidence_complete") is False
        ):
            raise ReviewFinalizationError(
                "The smoke run contains a missing, shifted, or failed turn."
            )
        if expected_label in turn_by_label:
            raise ReviewFinalizationError(
                "The smoke action sequence is inconsistent."
            )
        turn_by_label[expected_label] = row

        if (
            row.get("request_telemetry_context_seen") is not True
            or row.get("action_result_capture_seen") is not True
            or row.get("action_result_source")
            != "isolated_session_engine_telemetry"
        ):
            raise ReviewFinalizationError(
                "Required per-turn telemetry is incomplete."
            )
        action = row.get("action_result")
        if (
            not isinstance(action, dict)
            or not isinstance(action.get("action"), str)
            or not action.get("action")
            or row.get("resolved_action") != action.get("action")
        ):
            raise ReviewFinalizationError(
                "Required engine action evidence is incomplete."
            )
        calls = row.get("model_calls")
        observed_calls = row.get("observed_model_calls")
        if (
            type(calls) is not int
            or type(observed_calls) is not int
            or calls != observed_calls
            or not 0 <= calls <= MAX_MODEL_CALLS_PER_TURN
            or row.get("model_call_count_matches") is not True
        ):
            raise ReviewFinalizationError(
                "The model-call limit or telemetry comparison failed."
            )
        safety = row.get("safety")
        if (
            not isinstance(safety, dict)
            or not all(
                isinstance(safety.get(field), str) and safety.get(field)
                for field in ("tier", "handling", "reason_code", "scope")
            )
            or safety.get("scope") == "unavailable"
        ):
            raise ReviewFinalizationError(
                "Required safety classification evidence is incomplete."
            )
        try:
            proposal_gaps = proposal_trace_validator(row)
        except Exception:
            raise ReviewFinalizationError(
                "Proposal trace evidence is malformed."
            ) from None
        if not isinstance(proposal_gaps, list) or proposal_gaps:
            raise ReviewFinalizationError(
                "Proposal trace evidence has required gaps."
            )

        exempt = index in exempt_turns
        candidate = _fallback_candidate(safety)
        counted = candidate and not exempt
        if (
            row.get("budget_exempt") is not exempt
            or row.get("fallback_budget_counted") is not counted
        ):
            raise ReviewFinalizationError(
                "Fallback-budget evidence is inconsistent."
            )
        if counted:
            ordinary_fallbacks += 1

    if (
        summary.get("budget_exempt_turn_ids") != sorted(exempt_turns)
        or type(summary.get("ordinary_fallback_candidate_count")) is not int
        or summary.get("ordinary_fallback_candidate_count") != ordinary_fallbacks
        or ordinary_fallbacks > MAX_ORDINARY_FALLBACKS
    ):
        raise ReviewFinalizationError(
            "The ordinary fallback limit was exceeded or misreported."
        )
    checks["turns_and_telemetry"] = True
    checks["model_call_limit"] = True
    checks["ordinary_fallback_limit"] = True

    resume_flags = {
        "equal_public_state": True,
        "equal_sanitized_state": True,
        "equal_state": True,
        "equal_lore": True,
        "equal_memory": True,
        "equal_history": True,
        "equal_combat_history": True,
    }
    if (
        any(resume.get(field) is not True for field in resume_flags)
        or resume.get("sanitized_state_mismatch_paths") != []
        or not isinstance(resume.get("campaign_id"), str)
        or resume.get("campaign_id") != summary.get("campaign_id")
        or not isinstance(resume.get("new_session_id"), str)
        or not isinstance(resume.get("old_session_id"), str)
        or any(
            summary.get(summary_field) is not True
            or summary.get(summary_field) != resume.get(resume_field)
            for summary_field, resume_field in _RESUME_SUMMARY_FIELDS.items()
        )
    ):
        raise ReviewFinalizationError(
            "One or more restart/resume comparisons failed."
        )
    checks["resume_comparisons"] = True

    audit_by_turn: dict[int, dict[str, Any]] = {}
    resume_events: list[dict[str, Any]] = []
    for row in audit:
        turn_number = row.get("turn_index")
        if type(turn_number) is int:
            if turn_number in audit_by_turn:
                raise ReviewFinalizationError(
                    "The API audit contains duplicate turn evidence."
                )
            audit_by_turn[turn_number] = row
        elif row.get("event") == "resume":
            resume_events.append(row)
        else:
            raise ReviewFinalizationError(
                "The API audit contains an unrecognized non-turn record."
            )
    if (
        set(audit_by_turn) != set(range(1, expected_turn_count + 1))
        or len(resume_events) != 1
    ):
        raise ReviewFinalizationError(
            "The API audit is missing required turn or resume evidence."
        )
    for index, turn in enumerate(turns, 1):
        audit_row = audit_by_turn[index]
        if (
            audit_row.get("model") != MODEL_NAME
            or audit_row.get("model_calls") != turn.get("model_calls")
            or audit_row.get("observed_model_calls")
            != turn.get("observed_model_calls")
            or audit_row.get("action_result") != turn.get("action_result")
            or audit_row.get("safety") != turn.get("safety")
            or audit_row.get("state")
            != turn.get("state_diff", {}).get("after")
            or audit_row.get("request_telemetry_context_seen") is not True
            or audit_row.get("action_result_capture_seen") is not True
            or (
                narration_review_required
                and (
                    audit_row.get("narration_telemetry_capture_seen") is not True
                    or audit_row.get("narration_telemetry")
                    != narration_review["turns"][index - 1].get(
                        "engine_telemetry"
                    )
                )
            )
        ):
            raise ReviewFinalizationError(
                "The API audit conflicts with sanitized turn evidence."
            )
    resume_event = resume_events[0]
    resume_after_turn = summary.get("resume_after_turn", 24)
    if (
        type(resume_after_turn) is not int
        or not 1 <= resume_after_turn < expected_turn_count
        or resume.get("resume_after_turn", resume_after_turn) != resume_after_turn
        or resume_event.get("campaign_id") != summary.get("campaign_id")
        or resume_event.get("session_id") != resume.get("new_session_id")
        or resume_event.get("state")
        != turns[resume_after_turn - 1].get("state_diff", {}).get("after")
        or (
            "turn_index" in resume_event
            and resume_event.get("turn_index") != resume_after_turn
        )
    ):
        raise ReviewFinalizationError(
            "The API resume audit conflicts with resume evidence."
        )
    checks["api_audit_consistent"] = True

    route = turn_by_label.get("unsupported route challenge")
    route_action = route.get("action_result") if isinstance(route, dict) else None
    route_safety = route.get("safety") if isinstance(route, dict) else None
    route_diff = route.get("state_diff") if isinstance(route, dict) else None
    if (
        not isinstance(route_action, dict)
        or route_action.get("status") != "unverified"
        or route_action.get("success") is not False
        or not isinstance(route_safety, dict)
        or route_safety.get("reason_code") != "UNVERIFIED_LORE_CLAIM"
        or route_safety.get("handling") != "python_fallback"
        or not isinstance(route_diff, dict)
        or _turn_index_without_expected_advance(route_diff.get("before"))
        != _turn_index_without_expected_advance(route_diff.get("after"))
    ):
        raise ReviewFinalizationError(
            "The unsupported route-distance safety guard did not pass."
        )
    checks["route_distance_guard"] = True

    discovered = turn_by_label.get("discover local tavern")
    entered = turn_by_label.get("enter discovered tavern")
    asked_bartender = turn_by_label.get("ask bartender name")
    looked_at_tavern = turn_by_label.get("tavern look")
    sat_at_table = turn_by_label.get("sit at presented table")
    final_return = turn_by_label.get("return to tavern for final continuity check")
    discover_action = discovered.get("action_result") if isinstance(discovered, dict) else None
    enter_action = entered.get("action_result") if isinstance(entered, dict) else None
    name_action = (
        asked_bartender.get("action_result")
        if isinstance(asked_bartender, dict) else None
    )
    sit_action = sat_at_table.get("action_result") if isinstance(sat_at_table, dict) else None
    final_action = (
        final_return.get("action_result")
        if isinstance(final_return, dict) else None
    )
    if not all(
        isinstance(item, dict)
        for item in (discover_action, enter_action, name_action, sit_action, final_action)
    ):
        raise ReviewFinalizationError(
            "Original tavern continuity evidence is incomplete."
        )
    tavern_id = discover_action.get("target_id")
    bartender_id = name_action.get("npc_id")
    feature_id = sit_action.get("target_id")
    if not all(isinstance(identity, str) and identity for identity in (
        tavern_id, bartender_id, feature_id,
    )):
        raise ReviewFinalizationError(
            "Original tavern identity evidence is incomplete."
        )
    first_tavern_state = entered.get("state_diff", {}).get("after")
    looked_tavern_state = looked_at_tavern.get("state_diff", {}).get("after")
    sat_state = sat_at_table.get("state_diff", {}).get("after")
    final_state = final_return.get("state_diff", {}).get("after")
    location = _record_by_id(first_tavern_state, "locations", tavern_id)
    if (
        discover_action.get("action") != "local_search"
        or discover_action.get("success") is not True
        or f"locations:{tavern_id}" not in discovered.get("created_ids", [])
        or enter_action.get("action") != "enter"
        or enter_action.get("target_id") != tavern_id
        or enter_action.get("success") is not True
        or entered.get("location_id") != tavern_id
        or not location
        or _record_by_id(first_tavern_state, "npcs", bartender_id).get("location")
        != tavern_id
        or name_action.get("npc_id") != bartender_id
        or _record_by_id(looked_tavern_state, "features", feature_id).get("location")
        != tavern_id
        or sit_action.get("action") != "sit"
        or sit_action.get("success") is not True
        or _record_by_id(sat_state, "features", feature_id).get("location")
        != tavern_id
        or final_action.get("action") != "enter"
        or final_action.get("target_id") != tavern_id
        or final_action.get("success") is not True
        or final_return.get("location_id") != tavern_id
        or not isinstance(final_state, dict)
        or final_state.get("location") != tavern_id
        or _record_by_id(final_state, "npcs", bartender_id).get("location")
        != tavern_id
        or _record_by_id(final_state, "features", feature_id).get("location")
        != tavern_id
    ):
        raise ReviewFinalizationError(
            "The final tavern/NPC/feature identity continuity check failed."
        )
    checks["final_tavern_continuity"] = True
    checks["original_entity_identity_continuity"] = True

    parsed = {
        "summary": summary,
        "resume": resume,
        "turns": turns,
        "audit": audit,
    }
    if narration_review is not None:
        checks["narration_review_evidence"] = True
        parsed["narration_review"] = narration_review
    return checks, parsed


def _load_existing_attestation(
    path: Path,
    expected_fields: dict[str, Any],
) -> dict[str, Any] | None:
    if not path.exists() and not path.is_symlink():
        return None
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_size > 16 * 1024
        ):
            raise ReviewFinalizationError(
                "The existing manual-review attestation is invalid."
            )
        value = _decode_json(path.read_bytes())
    except OSError:
        raise ReviewFinalizationError(
            "The existing manual-review attestation is invalid."
        ) from None
    if not isinstance(value, dict):
        raise ReviewFinalizationError(
            "The existing manual-review attestation is invalid."
        )
    expected_keys = set(expected_fields) | {"review_timestamp_utc"}
    if set(value) != expected_keys or any(
        value.get(key) != expected
        for key, expected in expected_fields.items()
    ):
        raise ReviewFinalizationError(
            "The source report changed or conflicts with its existing attestation."
        )
    timestamp = value.get("review_timestamp_utc")
    if not isinstance(timestamp, str):
        raise ReviewFinalizationError(
            "The existing manual-review attestation is invalid."
        )
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise ReviewFinalizationError(
            "The existing manual-review attestation is invalid."
        ) from None
    if parsed_timestamp.tzinfo is None:
        raise ReviewFinalizationError(
            "The existing manual-review attestation is invalid."
        )
    return value


def _status_result(
    report_id: str,
    checks: dict[str, bool],
    digest: str,
    *,
    approved: bool,
    attestation_path: str | None,
) -> dict[str, Any]:
    return {
        "execution_status": "COMPLETE",
        "objective_validation_result": "PASS",
        "objective_validation_checks": checks,
        "manual_review_status": "APPROVED" if approved else "PENDING",
        "final_gate_status": "PASS" if approved else "REVIEW_PENDING",
        "report_id": report_id,
        "source_evidence_sha256": digest,
        "attestation_path": attestation_path,
    }


def finalize_review(
    report_arg: str | Path,
    *,
    approve: bool,
    reports_root: str | Path,
    expected_labels: Sequence[str],
    budget_exempt_turn_ids: Iterable[int],
    proposal_trace_validator: Callable[[dict[str, Any]], list[str]],
    expected_pending_error: str = EXPECTED_PENDING_ERROR,
    narration_review_required: bool = False,
) -> dict[str, Any]:
    """Validate an existing run and, only with explicit approval, attest it."""
    report_parent, report_dir = _resolve_report_dir(report_arg, reports_root)
    source = _read_source_files(
        report_dir,
        narration_review_required=narration_review_required,
    )
    checks, parsed = _validate_objective_evidence(
        report_dir,
        source,
        expected_labels=expected_labels,
        budget_exempt_turn_ids=budget_exempt_turn_ids,
        proposal_trace_validator=proposal_trace_validator,
        expected_pending_error=expected_pending_error,
        narration_review_required=narration_review_required,
    )
    file_digests = _file_digests(source)
    evidence_digest = _combined_digest(file_digests)
    attestation_path = report_dir / ATTESTATION_FILENAME
    relative_report_path = report_dir.relative_to(report_parent.parent.parent)
    expected_attestation = {
        "attestation_schema_version": 1,
        "source_report_id": report_dir.name,
        "source_report_path": relative_report_path.as_posix(),
        "source_summary_status": parsed["summary"]["status"],
        "source_evidence_sha256": evidence_digest,
        "source_file_sha256": file_digests,
        "execution_status": "COMPLETE",
        "objective_validation_result": "PASS",
        "objective_validation_checks": checks,
        "manual_review_status": "APPROVED",
        "reviewer_approved": True,
        "reviewed_turn_count": len(expected_labels),
        "final_gate_status": "PASS",
    }
    existing = _load_existing_attestation(attestation_path, expected_attestation)
    if existing is not None:
        return _status_result(
            report_dir.name,
            checks,
            evidence_digest,
            approved=True,
            attestation_path=relative_report_path.joinpath(
                ATTESTATION_FILENAME
            ).as_posix(),
        )
    if not approve:
        return _status_result(
            report_dir.name,
            checks,
            evidence_digest,
            approved=False,
            attestation_path=None,
        )

    if _file_digests(
        _read_source_files(
            report_dir,
            narration_review_required=narration_review_required,
        )
    ) != file_digests:
        raise ReviewFinalizationError(
            "The source report changed during manual-review finalization."
        )
    attestation = dict(expected_attestation)
    attestation["review_timestamp_utc"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    )
    serialized = json.dumps(
        attestation,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"
    try:
        with attestation_path.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        concurrent = _load_existing_attestation(
            attestation_path, expected_attestation
        )
        if concurrent is None:
            raise ReviewFinalizationError(
                "The manual-review attestation could not be created."
            ) from None
    except OSError:
        raise ReviewFinalizationError(
            "The manual-review attestation could not be created."
        ) from None
    return _status_result(
        report_dir.name,
        checks,
        evidence_digest,
        approved=True,
        attestation_path=relative_report_path.joinpath(
            ATTESTATION_FILENAME
        ).as_posix(),
    )