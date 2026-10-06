"""Disposable 30-turn real-Qwen smoke for the Playable Living World V1.1 hotfix.

Run from ``ai-dnd`` with:

    python -m api.tests.live_playable_living_world_v1_1_smoke --review-narrations

The run uses a fresh SQLite database, restarts the isolated API after turn 15,
and persists only sanitized evidence. Narration is printed for review only when
the explicit flag is supplied; it is never written to the report.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid

import httpx

from api.tests import live_playable_living_world_v1_smoke as telemetry
from api.tests.playable_living_world_v1_review import (
    EXPECTED_PENDING_ERROR,
    ReviewFinalizationError,
    finalize_review,
)


MODEL_NAME = "qwen3:8b"
RESUME_AFTER_TURN = 15
EXPECTED_PENDING_ERROR_V11 = (
    "30-turn mechanics completed, but release evidence is incomplete; "
    "mechanical/manual PASS is not claimed."
)
EXPECTED_LABELS = (
    "city look",
    "city presence",
    "approach and greet first local",
    "ask first local name",
    "disclose player name",
    "ask local occupation",
    "ask local current activity",
    "ask local recent activity",
    "ask local origin",
    "ask local day",
    "local historical name recall",
    "discover local merchant",
    "ask merchant occupation",
    "unsupported route challenge",
    "local work query",
    "work acceptance without offer",
    "discover local tavern",
    "enter discovered tavern",
    "tavern look",
    "ask bartender name",
    "disclose name to bartender",
    "ask bartender daily activity",
    "sit at presented table",
    "observe tavern traveler",
    "approach tavern traveler",
    "follow up promoted traveler",
    "leave tavern",
    "return to same tavern",
    "active NPC world subject routing",
    "return to tavern for final continuity check",
)
BUDGET_EXEMPT_TURN_IDS = frozenset({14})
AI_DND_DIR = Path(__file__).resolve().parents[2]


class SmokeFailure(RuntimeError):
    pass


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _state_record(state: dict[str, Any], collection: str, ident: str) -> dict[str, Any]:
    return telemetry._record_by_id(state, collection, ident)


def _player_state(turn: dict[str, Any]) -> dict[str, Any]:
    value = turn.get("state_diff", {}).get("after")
    if not isinstance(value, dict):
        raise SmokeFailure("Turn did not expose a sanitized state snapshot.")
    return value


def _safe_error_code(error: BaseException) -> str:
    """Keep the exception type and a short diagnostic code, not player prose."""
    name = type(error).__name__
    text = " ".join(str(error).split())
    lowered = text.casefold()
    if "bearer " in lowered or "token=" in lowered or "ollama_proxy" in lowered:
        text = "sensitive detail redacted"
    if len(text) > 240:
        text = text[:240]
    return f"{name}: {text}" if text else name


def _failure_turn_label(
    error: BaseException | None,
    evidence_rows: list[dict[str, Any]],
) -> str | None:
    if isinstance(error, SmokeFailure):
        head = str(error).split(":", 1)[0].strip()
        if head in EXPECTED_LABELS:
            return head
    if len(evidence_rows) < len(EXPECTED_LABELS):
        return EXPECTED_LABELS[len(evidence_rows)]
    if evidence_rows:
        label = evidence_rows[-1].get("label")
        return label if isinstance(label, str) else None
    return None


def classify_validator_turn(row: dict[str, Any]) -> str:
    """validator_not_invoked is intentional when the trace says no validator ran."""
    if row.get("proposal_trace_status") != "validator_not_invoked":
        return "invoked"
    calls = row.get("proposal_validation_calls")
    decisions = row.get("proposal_decisions")
    if calls not in (0, None):
        return "silent_miss"
    if not decisions:
        return "intentional_skip"
    if (
        isinstance(decisions, list)
        and len(decisions) == 1
        and isinstance(decisions[0], dict)
        and decisions[0].get("kind") == "proposal_summary"
        and decisions[0].get("status") == "validator_not_invoked"
    ):
        return "intentional_skip"
    return "silent_miss"


def collect_evidence_gaps(evidence_rows: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    if len(evidence_rows) != len(EXPECTED_LABELS):
        gaps.append("30-turn action sequence incomplete")
    token_usage = [
        row.get("token_usage")
        for row in evidence_rows
        if isinstance(row.get("token_usage"), dict)
    ]
    if len(token_usage) != len(evidence_rows) or not token_usage:
        gaps.append("numeric token telemetry missing on one or more turns")
    for row in evidence_rows:
        if (
            row.get("request_telemetry_context_seen") is not True
            or row.get("action_result_capture_seen") is not True
            or row.get("resolved_action") != row.get("action_result", {}).get("action")
        ):
            gaps.append("engine action result/resolved action missing")
        gaps.extend(telemetry._proposal_trace_gaps(row))
        if not isinstance(row.get("safety"), dict) or row["safety"].get("scope") == "unavailable":
            gaps.append("safety classification incomplete")
        if classify_validator_turn(row) == "silent_miss":
            gaps.append("validator skip was not an intentional no-call")
    return list(dict.fromkeys(gaps))


def apply_smoke_summary(
    result: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    ordinary_fallbacks: int,
    failure: BaseException | None = None,
) -> dict[str, Any]:
    """Record the first failure and keep evidence gaps in a separate field."""
    gaps = collect_evidence_gaps(evidence_rows)
    token_usage = [
        row.get("token_usage")
        for row in evidence_rows
        if isinstance(row.get("token_usage"), dict)
    ]
    if len(token_usage) == len(evidence_rows) and token_usage:
        result["token_usage"] = {
            "prompt_eval_count": sum(
                int(item["prompt_eval_count"]) for item in token_usage
            ),
            "eval_count": sum(int(item["eval_count"]) for item in token_usage),
            "scope": "aggregate of per-turn isolated telemetry",
        }
    result["evidence_incomplete"] = gaps
    result["review_status"] = "pending_human_review"
    result["ordinary_fallback_candidate_count"] = ordinary_fallbacks
    result["ordinary_fallback_reason_codes"] = [
        row.get("safety_reason")
        for row in evidence_rows
        if row.get("fallback_budget_counted") and isinstance(row.get("safety_reason"), str)
    ]
    result["validator_not_invoked"] = [
        {
            "turn": row.get("turn"),
            "label": row.get("label"),
            "classification": classify_validator_turn(row),
        }
        for row in evidence_rows
        if row.get("proposal_trace_status") == "validator_not_invoked"
    ]
    if failure is not None:
        result["status"] = "BLOCKED / LIVE PLAYABILITY UNVERIFIED"
        result["error"] = _safe_error_code(failure)
        result["error_turn_label"] = _failure_turn_label(failure, evidence_rows)
        if gaps:
            result["evidence_gap_summary"] = "; ".join(gaps)
    elif gaps:
        result["status"] = "BLOCKED / EVIDENCE_INCOMPLETE"
        result["error"] = "; ".join(gaps)
    return result


def run_smoke() -> dict[str, Any]:
    evidence_rows: list[dict[str, Any]] = []
    report_parent = AI_DND_DIR / "reports" / "playable-living-world-v1-1-smokes"
    report_root = report_parent / f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
    report_root.mkdir(parents=True, exist_ok=False)
    audit_path = report_root / "api-audit.jsonl"
    turn_path = report_root / "turn-evidence.jsonl"
    salt = uuid.uuid4().hex
    result: dict[str, Any] = {
        "status": "BLOCKED / LIVE PLAYABILITY UNVERIFIED",
        "model": MODEL_NAME,
        "campaign_database": "temporary_disposable",
        "turns": evidence_rows,
        "report_path": str(report_root),
        "budget_exempt_turn_ids": sorted(BUDGET_EXEMPT_TURN_IDS),
        "evidence_incomplete": [],
    }

    with tempfile.TemporaryDirectory(prefix="ai-dnd-playable-v1-1-") as directory:
        database = Path(directory) / "campaigns.sqlite3"
        port = telemetry._port()
        base = f"http://127.0.0.1:{port}"
        process: subprocess.Popen[bytes] | None = None
        handle: Any = None
        last_state: list[dict[str, Any]] = [{}]
        ordinary_fallbacks = 0
        failure: BaseException | None = None
        campaign_id = ""
        session_id = ""
        tavern_id = ""
        tavern_name = ""
        bartender_id = ""
        feature_id = ""

        def play(
            client: httpx.Client,
            message: str,
            label: str,
            target_id: str | None = None,
        ) -> dict[str, Any]:
            nonlocal ordinary_fallbacks
            expected_index = len(evidence_rows)
            if expected_index >= len(EXPECTED_LABELS) or label != EXPECTED_LABELS[expected_index]:
                raise SmokeFailure("The V1.1 action sequence shifted.")

            turn = telemetry._turn(client, base, session_id, message, target_id)
            source = telemetry._latest(audit_path)
            action_result = source.get("action_result")
            state = source.get("state")
            if not isinstance(state, dict) or not isinstance(action_result, dict):
                raise SmokeFailure(f"{label}: engine evidence is incomplete.")
            before = copy.deepcopy(last_state[0])
            after = telemetry._projection(state)
            turn_number = expected_index + 1
            safety = source.get("safety")
            safety = safety if isinstance(safety, dict) else {}
            calls = source.get("model_calls")
            observed_calls = source.get("observed_model_calls")
            fallback = telemetry._is_fallback_candidate(safety)
            exempt = turn_number in BUDGET_EXEMPT_TURN_IDS
            if fallback and not exempt:
                ordinary_fallbacks += 1

            turn["action_result"] = action_result
            row = {
                "turn": turn_number,
                "label": label,
                "target_id": target_id,
                "request_telemetry_context_seen": source.get(
                    "request_telemetry_context_seen"
                ),
                "action_result_capture_seen": source.get(
                    "action_result_capture_seen"
                ),
                "action_result_source": "isolated_session_engine_telemetry",
                "resolved_action": action_result.get("action"),
                "action_result": action_result,
                "skill_check_result": turn.get("skill_check_result"),
                "location_id": after.get("location"),
                "entity_ids": {
                    key: sorted(telemetry._ids(after, key))
                    for key in ("npcs", "features", "shops", "locations")
                },
                "state_diff": {"before": before, "after": after},
                "retrieved_fact_ids": source.get("retrieved_fact_ids", []),
                "memory_snapshot_refs": source.get("memory_snapshot_refs", []),
                "player_disclosure_memory_refs": source.get(
                    "player_disclosure_memory_refs", []
                ),
                "created_ids": sorted(
                    f"{kind}:{ident}"
                    for kind in ("npcs", "features", "shops", "locations")
                    for ident in (
                        telemetry._ids(after, kind) - telemetry._ids(before, kind)
                    )
                ),
                "reused_ids": sorted(
                    f"{kind}:{ident}"
                    for kind in ("npcs", "features", "shops", "locations")
                    for ident in (
                        telemetry._ids(after, kind) & telemetry._ids(before, kind)
                    )
                ),
                "promoted_ids": sorted(
                    str(ref.get("promoted_npc_id"))
                    for ref in after.get("scene", {}).get("referents", [])
                    if isinstance(ref, dict) and ref.get("promoted_npc_id")
                ),
                "proposal_decisions": source.get("proposal_diagnostics", []),
                "proposal_validation_calls": source.get(
                    "proposal_validation_calls", 0
                ),
                "proposal_validation_call_indices": source.get(
                    "proposal_validation_call_indices", []
                ),
                "proposal_binding_calls": source.get("proposal_binding_calls"),
                "proposal_binding_call_indices": source.get(
                    "proposal_binding_call_indices", []
                ),
                "proposal_trace_status": source.get(
                    "proposal_trace_status", "unavailable"
                ),
                "proposal_category_counts": source.get(
                    "proposal_category_counts", {}
                ),
                "proposal_stage_counts": source.get("proposal_stage_counts", {}),
                "proposal_reason_specificity": (
                    "validator/binding output membership only; internal cause unavailable"
                ),
                "events": source.get("events", {}),
                "model_calls": calls,
                "observed_model_calls": observed_calls,
                "model_call_count_matches": calls == observed_calls,
                "token_usage": source.get("token_usage", "unavailable"),
                "safety": safety,
                "safety_classification": (
                    f"{safety.get('handling')}:{safety.get('reason_code')}"
                    if safety.get("handling") and safety.get("reason_code")
                    else "unavailable"
                ),
                "safety_tier": safety.get("tier"),
                "safety_reason": safety.get("reason_code"),
                "safety_handling": safety.get("handling"),
                "safety_scope": safety.get("scope"),
                "safety_scene_type": safety.get("scene_type"),
                "budget_exempt": exempt,
                "fallback_budget_counted": fallback and not exempt,
                "narration": turn.get("narration"),
            }
            _require(
                source.get("session_id") == session_id
                and source.get("request_telemetry_context_seen") is True
                and source.get("action_result_capture_seen") is True,
                f"{label}: request/action telemetry missing.",
            )
            _require(
                type(calls) is int
                and type(observed_calls) is int
                and calls == observed_calls
                and 0 <= calls <= 2,
                f"{label}: model call count failed.",
            )
            _require(
                all(
                    isinstance(safety.get(field), str) and safety.get(field)
                    for field in ("tier", "handling", "reason_code", "scope")
                )
                and safety.get("scope") != "unavailable",
                f"{label}: safety classification is incomplete.",
            )
            _require(
                isinstance(turn.get("narration"), str)
                and bool(turn["narration"].strip())
                and "traceback" not in turn["narration"].casefold()
                and "debug fallback" not in turn["narration"].casefold(),
                f"{label}: narration is empty or contains debug output.",
            )
            gaps = telemetry._proposal_trace_gaps(row)
            _require(not gaps, f"{label}: proposal evidence is incomplete.")
            _require(
                isinstance(row["token_usage"], dict)
                and all(
                    type(row["token_usage"].get(key)) is int
                    for key in ("prompt_eval_count", "eval_count")
                ),
                f"{label}: numeric token usage is unavailable.",
            )
            _require(ordinary_fallbacks <= 2, "Ordinary fallback budget exceeded.")
            evidence_rows.append(row)
            telemetry._append(turn_path, row)
            last_state[0] = copy.deepcopy(after)
            return turn

        try:
            process, handle = telemetry._start(port, database, audit_path, salt)
            health = telemetry._ready(process, base)
            _require(health.get("model") == MODEL_NAME, "Live model is not qwen3:8b.")
            with httpx.Client(timeout=240) as client:
                created_response = client.post(
                    f"{base}/api/campaigns",
                    json={
                        "name": f"Playable V1.1 {uuid.uuid4().hex[:8]}",
                        "campaign_start": telemetry.START_SELECTION,
                    },
                    timeout=30,
                )
                _require(created_response.status_code == 200, "Campaign creation failed.")
                created = created_response.json()
                campaign_id = created["campaign_id"]
                session_id = created["session_id"]
                last_state[0] = telemetry._projection(created["state"])
                _require(
                    last_state[0].get("location") == "fr:city:neverwinter",
                    "Campaign did not start in Neverwinter.",
                )

                play(client, "Şehirde etrafıma bakıyorum.", EXPECTED_LABELS[0])
                state = _player_state(evidence_rows[-1])
                city_id = state["location"]
                local = telemetry._one_npc(state, city_id)
                play(client, "Burada kimler var?", EXPECTED_LABELS[1])
                play(
                    client,
                    f"{local['name']} kişisine yaklaşıyorum; merhaba, nasılsın?",
                    EXPECTED_LABELS[2],
                    local["id"],
                )
                play(client, "Adın ne?", EXPECTED_LABELS[3])
                disclosure = play(
                    client,
                    "Benim adım Arven; kendimi sana tanıtıyorum.",
                    EXPECTED_LABELS[4],
                )
                _require(
                    (disclosure.get("action_result") or {}).get("status")
                    == "player_name_disclosed"
                    and "arven" in disclosure.get("narration", "").casefold(),
                    "First NPC did not receive the player-name disclosure.",
                )
                _require(
                    any(
                        ref.startswith(f"{local['id']}:")
                        for ref in evidence_rows[-1]["player_disclosure_memory_refs"]
                    ),
                    "NPC-bound name-disclosure memory evidence is missing.",
                )
                play(client, "Mesleğin nedir?", EXPECTED_LABELS[5])
                play(client, "Şu an ne yapıyorsun?", EXPECTED_LABELS[6])
                play(client, "Bugün ne yaptın?", EXPECTED_LABELS[7])
                play(client, "Nereden geliyorsun?", EXPECTED_LABELS[8])
                play(client, "Keyfin nasıl?", EXPECTED_LABELS[9])
                recalled = play(
                    client, "Adımı hatırlıyor musun?", EXPECTED_LABELS[10]
                )
                _require(
                    (recalled.get("action_result") or {}).get("status")
                    == "answered_from_npc_memory"
                    and "arven" in recalled.get("narration", "").casefold(),
                    "First NPC did not recall the name it heard.",
                )

                merchant_turn = play(
                    client,
                    "Buralarda bir tüccar var mı?",
                    EXPECTED_LABELS[11],
                )
                merchant_action = merchant_turn.get("action_result") or {}
                _require(
                    merchant_action.get("action") == "local_search"
                    and merchant_action.get("status") == "found",
                    "Nearby merchant search did not find a local merchant.",
                )
                merchant_state = _player_state(evidence_rows[-1])
                merchant = telemetry._record_by_id(
                    merchant_state, "npcs", merchant_action.get("target_id")
                )
                _require(merchant, "Merchant search did not register an NPC.")
                play(client, "Mesleğin ne?", EXPECTED_LABELS[12])
                route = play(
                    client,
                    "Neverwinter ile Phandalin arası kesin kaç mil?",
                    EXPECTED_LABELS[13],
                )
                _require(
                    (route.get("action_result") or {}).get("status") == "unverified",
                    "Unsupported route distance was not rejected.",
                )
                play(client, "Bu civarda iş var mı?", EXPECTED_LABELS[14])

                before_restart = copy.deepcopy(last_state[0])
                before_audit = telemetry._latest(audit_path)
                detail_before_response = client.get(
                    f"{base}/api/campaigns/{campaign_id}", timeout=30
                )
                _require(
                    detail_before_response.status_code == 200,
                    "Could not read pre-restart campaign state.",
                )
                detail_before = detail_before_response.json()
                _require(
                    len(evidence_rows) == RESUME_AFTER_TURN,
                    "Pre-restart turn count is incorrect.",
                )
                telemetry._stop(process, handle)
                process = handle = None

                process, handle = telemetry._start(port, database, audit_path, salt)
                health = telemetry._ready(process, base)
                _require(
                    health.get("model") == MODEL_NAME,
                    "Restarted API is not using qwen3:8b.",
                )
                resumed_response = client.post(
                    f"{base}/api/campaigns/{campaign_id}/resume", timeout=30
                )
                _require(resumed_response.status_code == 200, "Campaign resume failed.")
                resumed = resumed_response.json()
                old_session_id = session_id
                session_id = resumed["session_id"]
                _require(session_id != old_session_id, "Resume reused the old session.")
                resumed_state = resumed["state"]
                detail_after_response = client.get(
                    f"{base}/api/campaigns/{campaign_id}", timeout=30
                )
                _require(detail_after_response.status_code == 200, "Resume snapshot failed.")
                detail_after = detail_after_response.json()
                resume_audit = telemetry._latest_event(audit_path, "resume")
                equal_public_state = resumed_state == detail_before.get("state")
                equal_sanitized_state = (
                    telemetry._projection(resumed_state)
                    == telemetry._projection(detail_before.get("state"))
                )
                equal_resume_state = resume_audit.get("state") == before_restart
                equal_resume_lore = (
                    resume_audit.get("lore") == before_audit.get("lore")
                )
                equal_resume_memory = (
                    resume_audit.get("memory_snapshot_refs", [])
                    == before_audit.get("memory_snapshot_refs", [])
                    and resume_audit.get("player_disclosure_memory_refs", [])
                    == before_audit.get("player_disclosure_memory_refs", [])
                )
                equal_resume_history = (
                    resumed.get("history") == detail_before.get("history")
                )
                equal_resume_combat = (
                    resumed.get("combat_history")
                    == detail_before.get("combat_history")
                )
                resume_comparison = {
                    "campaign_id": campaign_id,
                    "old_session_id": old_session_id,
                    "new_session_id": session_id,
                    "resume_after_turn": RESUME_AFTER_TURN,
                    "equal_public_state": equal_public_state,
                    "equal_sanitized_state": equal_sanitized_state,
                    "sanitized_state_mismatch_paths": (
                        telemetry._difference_paths(
                            telemetry._projection(resumed_state),
                            telemetry._projection(detail_before.get("state")),
                        )
                        if not equal_sanitized_state
                        else []
                    ),
                    "equal_state": equal_resume_state,
                    "equal_lore": equal_resume_lore,
                    "equal_memory": equal_resume_memory,
                    "equal_history": equal_resume_history,
                    "equal_combat_history": equal_resume_combat,
                    "history_count": len(resumed.get("history", [])),
                    "combat_history_count": len(resumed.get("combat_history", [])),
                }
                telemetry._append(report_root / "resume-comparison.json", resume_comparison)
                _require(
                    all(
                        resume_comparison[key] is True
                        for key in (
                            "equal_public_state",
                            "equal_sanitized_state",
                            "equal_state",
                            "equal_lore",
                            "equal_memory",
                            "equal_history",
                            "equal_combat_history",
                        )
                    ),
                    "Campaign state, lore, memory, or history changed on resume.",
                )
                last_state[0] = telemetry._projection(resumed_state)

                play(
                    client,
                    "İşe başlamaya hazırım.",
                    EXPECTED_LABELS[15],
                )
                venue = play(
                    client,
                    "Yakınlarda oturup bir şeyler içebileceğim bir yer var mı?",
                    EXPECTED_LABELS[16],
                )
                venue_action = venue.get("action_result") or {}
                _require(
                    venue_action.get("action") == "local_search"
                    and venue_action.get("status") == "found",
                    "Nearby venue discovery did not return a location.",
                )
                tavern_id = str(venue_action.get("target_id") or "")
                state = _player_state(evidence_rows[-1])
                tavern = _state_record(state, "locations", tavern_id)
                tavern_name = str(tavern.get("name") or tavern_id)
                _require(tavern_id, "Venue discovery omitted the location ID.")
                _require(
                    f"locations:{tavern_id}" in evidence_rows[-1]["created_ids"],
                    "Venue discovery did not create the procedural location.",
                )

                entered = play(
                    client,
                    f"{tavern_name} içine giriyorum.",
                    EXPECTED_LABELS[17],
                )
                entered_action = entered.get("action_result") or {}
                _require(
                    entered_action.get("action") == "enter"
                    and entered_action.get("target_id") == tavern_id
                    and _player_state(evidence_rows[-1]).get("location") == tavern_id,
                    "Entering the found venue did not change the actual location.",
                )
                look = play(
                    client, "İçeriye ve çevreme bakıyorum.", EXPECTED_LABELS[18]
                )
                state = _player_state(evidence_rows[-1])
                bartender = telemetry._one_npc(state, tavern_id, role="Barmen")
                bartender_id = bartender["id"]
                feature = telemetry._one_feature(state, tavern_id)
                feature_id = feature["id"]
                name_turn = play(
                    client, "Adın ne?", EXPECTED_LABELS[19], bartender_id
                )
                _require(
                    (name_turn.get("action_result") or {}).get("npc_id")
                    == bartender_id,
                    "Bartender identity query was routed to another subject.",
                )
                disclosure = play(
                    client,
                    "Benim adım Elen.",
                    EXPECTED_LABELS[20],
                    bartender_id,
                )
                _require(
                    (disclosure.get("action_result") or {}).get("status")
                    == "player_name_disclosed",
                    "Bartender did not receive the second player-name disclosure.",
                )
                play(
                    client,
                    "Bugün günün nasıl gidiyor?",
                    EXPECTED_LABELS[21],
                    bartender_id,
                )
                play(
                    client,
                    f"{feature['name']} yanına oturuyorum.",
                    EXPECTED_LABELS[22],
                    feature_id,
                )

                scene = _player_state(evidence_rows[18]).get("scene", {})
                referents = scene.get("referents", []) if isinstance(scene, dict) else []
                referent = next(
                    (
                        item
                        for item in referents
                        if isinstance(item, dict)
                        and item.get("lifecycle") == "presented"
                        and item.get("addressable_alias")
                    ),
                    None,
                )
                _require(referent is not None, "Tavern scene has no addressable traveler.")
                alias = str(referent["addressable_alias"])
                observe = play(
                    client,
                    f"{alias} ne yapıyor?",
                    EXPECTED_LABELS[23],
                )
                _require(
                    (observe.get("action_result") or {}).get("status") == "observed",
                    "Traveler activity was not observed from the current scene.",
                )
                play(
                    client,
                    f"{alias} kişisine yaklaşıyorum.",
                    EXPECTED_LABELS[24],
                )
                promoted_state = _player_state(evidence_rows[-1])
                promoted = next(
                    (
                        item
                        for item in promoted_state.get("scene", {}).get("referents", [])
                        if item.get("id") == referent.get("id")
                    ),
                    None,
                )
                _require(
                    isinstance(promoted, dict)
                    and promoted.get("lifecycle") == "promoted"
                    and isinstance(promoted.get("promoted_npc_id"), str),
                    "Traveler referent was not promoted to a stable NPC.",
                )
                traveler_id = promoted["promoted_npc_id"]
                followed = play(
                    client,
                    "Onunla kısa bir selamlaşıyorum.",
                    EXPECTED_LABELS[25],
                )
                _require(
                    (followed.get("action_result") or {}).get("npc_id")
                    == traveler_id,
                    "Traveler follow-up lost the promoted NPC target.",
                )
                play(
                    client,
                    "Tavernadan çıkıp bağlı sokağa çıkıyorum.",
                    EXPECTED_LABELS[26],
                )
                returned = play(
                    client,
                    f"{tavern_name} içine giriyorum.",
                    EXPECTED_LABELS[27],
                )
                _require(
                    (returned.get("action_result") or {}).get("action") == "enter"
                    and _player_state(evidence_rows[-1]).get("location") == tavern_id,
                    "Returning to the discovered tavern did not reach it.",
                )
                world_question = play(
                    client,
                    "Bu şehrin hükümdarı kim?",
                    EXPECTED_LABELS[28],
                )
                world_action = world_question.get("action_result") or {}
                _require(
                    world_action.get("npc_id") is None
                    and world_action.get("status") != "clarification",
                    "World-subject question was routed to an NPC or ambiguous NPC clarification.",
                )
                final_return = play(
                    client,
                    f"{tavern_name} içine giriyorum.",
                    EXPECTED_LABELS[29],
                )
                final_state = _player_state(evidence_rows[-1])
                final_action = final_return.get("action_result") or {}
                _require(
                    final_action.get("action") == "enter"
                    and final_action.get("target_id") == tavern_id
                    and final_action.get("success") is True
                    and final_state.get("location") == tavern_id
                    and _state_record(final_state, "npcs", bartender_id).get(
                        "location"
                    )
                    == tavern_id
                    and _state_record(final_state, "features", feature_id).get(
                        "location"
                    )
                    == tavern_id,
                    "Final tavern/NPC/feature identity continuity failed.",
                )
                _require(len(evidence_rows) == len(EXPECTED_LABELS), "Smoke turn count failed.")

                result.update(
                    status="REVIEW_PENDING",
                    campaign_id=campaign_id,
                    resume_after_turn=RESUME_AFTER_TURN,
                    restart_state_equal=equal_resume_state,
                    restart_lore_equal=equal_resume_lore,
                    restart_memory_equal=equal_resume_memory,
                    restart_history_equal=equal_resume_history,
                    restart_combat_history_equal=equal_resume_combat,
                    error=EXPECTED_PENDING_ERROR_V11,
                )
        except Exception as error:
            failure = error
        finally:
            if process is not None:
                telemetry._stop(process, handle)

    apply_smoke_summary(result, evidence_rows, ordinary_fallbacks, failure)
    persisted = dict(result)
    persisted["turns"] = [telemetry._persisted_turn(row) for row in evidence_rows]
    (report_root / "summary.json").write_text(
        json.dumps(telemetry._sanitize_persistent_value(persisted), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    result["turns"] = evidence_rows
    return result


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--finalize-review":
        if len(args) not in (2, 3) or (len(args) == 3 and args[2] != "--approve"):
            print(json.dumps({"final_gate_status": "BLOCKED", "error": "Invalid review arguments."}))
            return 2
        try:
            result = finalize_review(
                args[1],
                approve=len(args) == 3,
                reports_root=AI_DND_DIR / "reports" / "playable-living-world-v1-1-smokes",
                expected_labels=EXPECTED_LABELS,
                budget_exempt_turn_ids=BUDGET_EXEMPT_TURN_IDS,
                proposal_trace_validator=telemetry._proposal_trace_gaps,
                expected_pending_error=EXPECTED_PENDING_ERROR_V11,
            )
        except ReviewFinalizationError as error:
            print(json.dumps({"final_gate_status": "BLOCKED", "error": str(error)}))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("final_gate_status") == "PASS" else 1

    result = run_smoke()
    if "--review-narrations" in args:
        print("TRANSIENT V1.1 NARRATION REVIEW (not written to report files)")
        for row in result.get("turns", []):
            print(
                json.dumps(
                    {
                        "turn": row.get("turn"),
                        "label": row.get("label"),
                        "narration": row.get("narration"),
                    },
                    ensure_ascii=False,
                )
            )
    printable = dict(result)
    printable["turns"] = [
        telemetry._persisted_turn(row) for row in result.get("turns", [])
    ]
    print(json.dumps(telemetry._sanitize_persistent_value(printable), ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "REVIEW_PENDING" else 1


if __name__ == "__main__":
    raise SystemExit(main())