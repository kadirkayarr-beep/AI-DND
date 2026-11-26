"""Ambient-event action route moved out of api.main.create_app (D-531 stage 5): same path, order, lock, receipt, save and rollback.

api.main's helpers and serializers are read through the passed `api_main` module at call time, as the closure did,
so a patch on api.main still reaches this route. The one lock-held body is cut into steps that share an AmbientRun;
the order of the steps, every rollback and every refusal are as they were in the single function.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException

import refusals
from api import failure_policy
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignError,
    CampaignNotActiveError,
    CampaignNotFoundError,
    CampaignStaleError,
    SaveLanded,
)
from api.schemas import AmbientEventActionRequest, AmbientEventCommandResult, AmbientEventResult
from api.serializers import redact_sensitive_values


@dataclass
class AmbientRun:
    api_main: Any
    manager: Any
    record: Any
    session_id: str
    request: AmbientEventActionRequest
    event_instance_key: str
    action_id: str
    request_hash: str
    session: Any = None
    snapshot: Any = None
    journal_snapshot: Any = None
    memory_snapshot: Any = None
    metadata_snapshot: Any = None
    lore_snapshot: Any = None
    token_before: Any = None
    transition: dict[str, Any] = field(default_factory=dict)
    response_payload: Any = None
    turn_entry: Any = None

    def response_for(
        self,
        status: str,
        reason_code: str | None = None,
        transition_id: str | None = None,
        canonical_event_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        response = AmbientEventCommandResult(
            session_id=self.session_id,
            state=self.api_main.serialize_session_state(self.session, self.record.journal, self.record.lore_authority),
            result=AmbientEventResult(
                event_instance_id=self.event_instance_key,
                action_id=self.action_id,
                status=status,
                reason_code=reason_code,
                transition_id=transition_id,
                canonical_event_id=canonical_event_id,
                message=message,
            ),
        )
        return redact_sensitive_values(response.model_dump())

    def put_back(self) -> None:
        # R05: a restore that fails or cannot be verified quarantines the session; it is never just logged.
        closed: HTTPException | None = None
        try:
            self.api_main._rollback_session(self.record, self.session, self.snapshot)
        except HTTPException as quarantine:
            closed = quarantine
        finally:
            self.record.journal = self.journal_snapshot
        if closed is not None:
            raise closed from None

    def refuse_unsaved(self, error: Exception) -> None:
        self.put_back()
        self.api_main._logger.error(
            "Ambient-event result could not be persisted (error_type=%s)",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "event_persistence_error",
                "message": "The event result could not be saved safely.",
            },
        ) from None


def register_ambient_routes(application: FastAPI, *, get_record: Any, require_current: Any, refuse_while_action_open: Any,
                            campaign_http_exception: Any, action_archived_error: Any, manager: Any,
                            api_main: Any) -> None:
    @application.post(
        "/api/game/sessions/{session_id}/ambient-events/"
        "{event_instance_id}/actions",
        response_model=AmbientEventCommandResult,
    )
    def resolve_ambient_event_action(
        session_id: str,
        event_instance_id: UUID,
        request: AmbientEventActionRequest,
    ) -> dict[str, Any]:
        record = get_record(session_id)
        with record.turn_lock:
            record = get_record(session_id)
            event_instance_key = str(event_instance_id)
            run = AmbientRun(
                api_main=api_main, manager=manager, record=record, session_id=session_id, request=request,
                event_instance_key=event_instance_key, action_id=str(request.action_id),
                request_hash=hashlib.sha256(json.dumps(
                    {"command": "ambient_event", "event_instance_id": event_instance_key,
                     "action": request.action},
                    sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                ).encode("utf-8")).hexdigest(),
                session=record.game_session,
            )
            replayed = _replay_stored_receipt(run, campaign_http_exception, action_archived_error)
            if replayed is not None:
                return replayed
            require_current(record)
            replayed = _replay_from_journal(run)
            if replayed is not None:
                return replayed
            if record.campaign_id is None:
                return run.response_for("REJECTED", "campaign_persistence_required")
            refuse_while_action_open(record)
            _take_snapshots(run)
            refused = _resolve(run)
            if refused is not None:
                return refused
            _save(run)
            return _adopt_undo_point(run)


def _replay_stored_receipt(run: AmbientRun, campaign_http_exception: Any, action_archived_error: Any) -> dict[str, Any] | None:
    """The receipt of this action id, if one is stored: a conflict, a replay, or a refusal that the stored reply is unusable."""
    try:
        previous = run.manager.get_turn_action(run.record, run.action_id)
    except CampaignError as error:
        raise campaign_http_exception(error) from None
    if previous is None:
        return None
    if previous["request_hash"] != run.request_hash:
        return run.response_for("REJECTED", "action_id_conflict")
    if previous.get("archived"):
        raise action_archived_error()
    try:
        if "legacy_ambient_result" in previous:
            prior = previous["legacy_ambient_result"]
        elif "legacy_ambient_result" in previous["response"]:
            prior = previous["response"]["legacy_ambient_result"]
        else:
            saved = AmbientEventCommandResult.model_validate(
                previous["response"]["ambient_event_response"], strict=True,
            )
            if (
                saved.result.action_id != run.action_id
                or saved.result.event_instance_id != run.event_instance_key
            ):
                raise ValueError("Ambient event response identity mismatch.")
            prior = saved.result.model_dump()
        # Legacy receipts reserve identity without a complete HTTP
        # response. Only validate the fields used by this projection.
        if not isinstance(prior, dict) or any(
            prior.get(key) is not None and (
                not isinstance(prior[key], str) or len(prior[key]) > limit
            )
            for key, limit in (
                ("transition_id", 160), ("canonical_event_id", 36),
            )
        ):
            raise ValueError("Invalid ambient event projection.")
    except (KeyError, TypeError, ValueError):
        raise campaign_http_exception(
            CampaignCorruptError("Campaign ambient event response is invalid.")
        ) from None
    # Preserve the locked event owner's ALREADY_APPLIED projection.
    return run.response_for("ALREADY_APPLIED", "event_already_resolved",
                            prior.get("transition_id"), prior.get("canonical_event_id"))


def _replay_from_journal(run: AmbientRun) -> dict[str, Any] | None:
    """An action id or event that the journal already holds: a conflict or ALREADY_APPLIED with the canonical event."""
    for event in reversed(run.record.journal.get("notable_events", [])):
        prior = event.get("event_result")
        if isinstance(prior, dict) and prior.get("action_id") == run.action_id and (
            prior.get("event_instance_id") != run.event_instance_key
            or prior.get("action") != run.request.action
        ):
            return run.response_for("REJECTED", "action_id_conflict")
        if (
            event.get("event_type") != "ambient_event_outcome"
            or not isinstance(prior, dict)
            or prior.get("event_instance_id") != run.event_instance_key
        ):
            continue
        if (
            prior.get("action_id") == run.action_id
            and prior.get("action") != run.request.action
        ):
            return run.response_for(
                "REJECTED",
                "action_id_conflict",
                canonical_event_id=event.get("event_id"),
            )
        return run.response_for(
            "ALREADY_APPLIED",
            "event_already_resolved",
            transition_id=prior.get("transition_id"),
            canonical_event_id=event.get("event_id"),
        )
    return None


def _take_snapshots(run: AmbientRun) -> None:
    record, session = run.record, run.session
    run.snapshot = run.api_main._capture_session(session)
    run.journal_snapshot = copy.deepcopy(record.journal)
    run.memory_snapshot = copy.deepcopy(record.narrative_memory)
    run.metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
    run.lore_snapshot = record.lore_authority
    run.token_before = getattr(session, "_campaign_persistence_version", None)


def _resolve(run: AmbientRun) -> dict[str, Any] | None:
    """The engine's click and the journal and response built from it; a refused click is returned, an applied one is staged."""
    api_main, record, session = run.api_main, run.record, run.session
    try:
        transition = session.resolve_ambient_event_action(
            run.event_instance_key,
            run.action_id,
            run.request.action,
        )
        run.transition = transition
        status = transition.get("status")
        transition_id = transition.get("transition_id")
        if status != "APPLIED":
            api_main._rollback_session(record, session, run.snapshot)
            record.journal = run.journal_snapshot
            canonical_event_id = None
            if status == "ALREADY_APPLIED" and isinstance(
                transition_id, str
            ):
                canonical_event_id = next(
                    (
                        item.get("event_id")
                        for item in reversed(
                            record.journal.get("notable_events", [])
                        )
                        if item.get("event_type") == "npc_met"
                        and item.get("related_npc_id") == transition_id
                    ),
                    None,
                )
            return run.response_for(
                status,
                transition.get("reason_code"),
                transition_id=transition_id,
                canonical_event_id=canonical_event_id,
                # The panel's line for a refused click; nothing changed, so the last turn's undo stands.
                message=refusals.text_for(transition.get("reason_code"))
                if status == "REJECTED" else None,
            )

        after_save = session.serialize_game_state()
        record.journal = api_main.update_campaign_journal(
            record.journal,
            run.snapshot["save"],
            after_save,
            {
                "action": "interact",
                "npc_id": transition_id,
                "target_id": transition_id,
            },
            api_main.world_metadata_for_state(
                session.world_state,
                getattr(session, "world_metadata", None),
            ),
        )
        record.journal, canonical_event = api_main.append_ambient_event_outcome(
            record.journal,
            after_save["world_state"],
            event_instance_id=run.event_instance_key,
            action_id=run.action_id,
            transition_id=transition_id,
        )
        response = AmbientEventCommandResult(
            session_id=run.session_id,
            state=api_main.serialize_session_state(session, record.journal, record.lore_authority),
            result=AmbientEventResult(
                event_instance_id=run.event_instance_key,
                action_id=run.action_id,
                status="APPLIED",
                reason_code=transition.get("reason_code"),
                transition_id=transition_id,
                canonical_event_id=canonical_event["event_id"],
            ),
        )
        run.response_payload = redact_sensitive_values(response.model_dump())
        # Without a history row a click left a receipt and no line of story.
        run.turn_entry = {
            "player_message": transition["player_message"],
            "narration": transition["narration"],
            "narration_source": "deterministic_system",  # ambient_actions builds this line itself
        }
    except Exception as error:
        run.refuse_unsaved(error)
    return None


def _save(run: AmbientRun) -> None:
    api_main, record = run.api_main, run.record
    try:
        run.manager.save_campaign_locked(record, turn_action_receipt={
            "action_id": run.action_id, "request_hash": run.request_hash,
            "response": {"action_id": run.action_id, "ambient_event_response": run.response_payload},
        }, turn_entry=run.turn_entry)
    except Exception as error:
        # D-103: as in the quest route, a save that raised may still have committed. Rolling back under a
        # stored receipt and history row would split the live game from storage, so ask storage first.
        certain = isinstance(error, (CampaignStaleError, CampaignNotFoundError, CampaignNotActiveError))
        landed = SaveLanded.NOT_LANDED if certain else run.manager.campaign_save_landed(record, run.token_before)
        if landed is SaveLanded.UNKNOWN:
            record.usable = False
            api_main._logger.critical("Ambient-event save failed and could not be reconciled; session closed")
            decision = failure_policy.classify_failure(
                failure_policy.ActionPhase.RECONCILIATION, "unknown", error,
            )
            raise HTTPException(
                status_code=decision.status_code, detail=decision.detail(commit_status="outcome_unknown"),
            ) from None
        if landed is SaveLanded.NOT_LANDED:
            run.refuse_unsaved(error)
        api_main._logger.error(
            "Ambient-event save committed but was not acknowledged (error_type=%s)", type(error).__name__,
        )


def _adopt_undo_point(run: AmbientRun) -> dict[str, Any]:
    """D-103: everything here runs after the commit and never rolls the live game back. If the checkpoint
    cannot be built the click is simply not undoable; a retry with this id replays the stored receipt.
    V5: a joined event is undone like a typed turn, with the same fields as the turn route."""
    api_main, session = run.api_main, run.session
    api_main._adopt_undo_checkpoint(run.record, lambda: {
        "action_id": run.action_id,
        "player_message": run.transition["player_message"],
        "snapshot": run.snapshot,
        "journal": run.journal_snapshot,
        "narrative_memory": run.memory_snapshot,
        "lore_authority": run.lore_snapshot,
        "world_metadata": run.metadata_snapshot,
        "post_turn_fingerprint": api_main._state_fingerprint(session),
    })
    return run.response_payload
