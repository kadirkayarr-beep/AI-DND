"""Ambient-event action route moved out of api.main.create_app (D-531 stage 2): same paths, receipts, save and Undo checkpoint."""
from __future__ import annotations

import copy
import hashlib
import json
import refusals
from typing import Any
from uuid import UUID
from fastapi import FastAPI, HTTPException
from api import failure_policy
from api.campaign_journal import (
    update_campaign_journal,
)
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignError,
    CampaignNotActiveError,
    CampaignNotFoundError,
    CampaignStaleError,
    SaveLanded,
)
from api.schemas import (
    AmbientEventActionRequest,
    AmbientEventCommandResult,
    AmbientEventResult,
)
from api.serializers import (
    redact_sensitive_values,
    serialize_session_state,
)
from api.world_metadata import (
    world_metadata_for_state,
)


def register_ambient_routes(
    application: FastAPI,
    *,
    get_record: Any,
    require_current: Any,
    ensure_usable: Any,
    refuse_while_action_open: Any,
    replay_action_response: Any,
    campaign_http_exception: Any,
    action_archived_error: Any,
    manager: Any,
    _capture_session: Any,
    _rollback_session: Any,
    _raise_if_commit_unconfirmed: Any,
    _adopt_undo_checkpoint: Any,
    _state_fingerprint: Any,
    _logger: Any,
    append_ambient_event_outcome: Any,
) -> None:
    @application.post(
        "/api/game/sessions/{session_id}/ambient-events/"
        "{event_instance_id}/actions",
        response_model=AmbientEventCommandResult,
    )
    @application.post(
        "/api/sessions/{session_id}/ambient-events/"
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
            session = record.game_session
            event_instance_key = str(event_instance_id)
            action_id = str(request.action_id)
            request_hash = hashlib.sha256(json.dumps(
                {"command": "ambient_event", "event_instance_id": event_instance_key,
                 "action": request.action},
                sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()

            def response_for(
                status: str,
                reason_code: str | None = None,
                transition_id: str | None = None,
                canonical_event_id: str | None = None,
                message: str | None = None,
            ) -> dict[str, Any]:
                response = AmbientEventCommandResult(
                    session_id=session_id,
                    state=serialize_session_state(session, record.journal, record.lore_authority),
                    result=AmbientEventResult(
                        event_instance_id=event_instance_key,
                        action_id=action_id,
                        status=status,
                        reason_code=reason_code,
                        transition_id=transition_id,
                        canonical_event_id=canonical_event_id,
                        message=message,
                    ),
                )
                return redact_sensitive_values(response.model_dump())

            try:
                previous = manager.get_turn_action(record, action_id)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            if previous is not None:
                if previous["request_hash"] != request_hash:
                    return response_for("REJECTED", "action_id_conflict")
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
                            saved.result.action_id != action_id
                            or saved.result.event_instance_id != event_instance_key
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
                return response_for("ALREADY_APPLIED", "event_already_resolved",
                                    prior.get("transition_id"), prior.get("canonical_event_id"))
            require_current(record)
            for event in reversed(record.journal.get("notable_events", [])):
                prior = event.get("event_result")
                if isinstance(prior, dict) and prior.get("action_id") == action_id and (
                    prior.get("event_instance_id") != event_instance_key
                    or prior.get("action") != request.action
                ):
                    return response_for("REJECTED", "action_id_conflict")
                if (
                    event.get("event_type") != "ambient_event_outcome"
                    or not isinstance(prior, dict)
                    or prior.get("event_instance_id") != event_instance_key
                ):
                    continue
                if (
                    prior.get("action_id") == action_id
                    and prior.get("action") != request.action
                ):
                    return response_for(
                        "REJECTED",
                        "action_id_conflict",
                        canonical_event_id=event.get("event_id"),
                    )
                return response_for(
                    "ALREADY_APPLIED",
                    "event_already_resolved",
                    transition_id=prior.get("transition_id"),
                    canonical_event_id=event.get("event_id"),
                )

            if record.campaign_id is None:
                return response_for("REJECTED", "campaign_persistence_required")
            refuse_while_action_open(record)

            snapshot = _capture_session(session)
            journal_snapshot = copy.deepcopy(record.journal)
            memory_snapshot = copy.deepcopy(record.narrative_memory)
            metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
            lore_snapshot = record.lore_authority
            token_before = getattr(session, "_campaign_persistence_version", None)

            def put_back() -> None:
                # R05: a restore that fails or cannot be verified quarantines the session; it is never just logged.
                closed: HTTPException | None = None
                try:
                    _rollback_session(record, session, snapshot)
                except HTTPException as quarantine:
                    closed = quarantine
                finally:
                    record.journal = journal_snapshot
                if closed is not None:
                    raise closed from None

            def refuse_unsaved(error: Exception) -> None:
                put_back()
                _logger.error(
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

            try:
                transition = session.resolve_ambient_event_action(
                    event_instance_key,
                    action_id,
                    request.action,
                )
                status = transition.get("status")
                transition_id = transition.get("transition_id")
                if status != "APPLIED":
                    _rollback_session(record, session, snapshot)
                    record.journal = journal_snapshot
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
                    return response_for(
                        status,
                        transition.get("reason_code"),
                        transition_id=transition_id,
                        canonical_event_id=canonical_event_id,
                        # The panel's line for a refused click; nothing changed, so the last turn's undo stands.
                        message=refusals.text_for(transition.get("reason_code"))
                        if status == "REJECTED" else None,
                    )

                after_save = session.serialize_game_state()
                record.journal = update_campaign_journal(
                    record.journal,
                    snapshot["save"],
                    after_save,
                    {
                        "action": "interact",
                        "npc_id": transition_id,
                        "target_id": transition_id,
                    },
                    world_metadata_for_state(
                        session.world_state,
                        getattr(session, "world_metadata", None),
                    ),
                )
                record.journal, canonical_event = append_ambient_event_outcome(
                    record.journal,
                    after_save["world_state"],
                    event_instance_id=event_instance_key,
                    action_id=action_id,
                    transition_id=transition_id,
                )
                response = AmbientEventCommandResult(
                    session_id=session_id,
                    state=serialize_session_state(session, record.journal, record.lore_authority),
                    result=AmbientEventResult(
                        event_instance_id=event_instance_key,
                        action_id=action_id,
                        status="APPLIED",
                        reason_code=transition.get("reason_code"),
                        transition_id=transition_id,
                        canonical_event_id=canonical_event["event_id"],
                    ),
                )
                response_payload = redact_sensitive_values(response.model_dump())
                # Without a history row a click left a receipt and no line of story.
                turn_entry = {
                    "player_message": transition["player_message"],
                    "narration": transition["narration"],
                    "narration_source": "deterministic_system",  # ambient_actions builds this line itself
                }
            except Exception as error:
                refuse_unsaved(error)
            try:
                manager.save_campaign_locked(record, turn_action_receipt={
                    "action_id": action_id, "request_hash": request_hash,
                    "response": {"action_id": action_id, "ambient_event_response": response_payload},
                }, turn_entry=turn_entry)
            except Exception as error:
                # D-103: as in the quest route, a save that raised may still have committed. Rolling back under a
                # stored receipt and history row would split the live game from storage, so ask storage first.
                certain = isinstance(error, (CampaignStaleError, CampaignNotFoundError, CampaignNotActiveError))
                landed = SaveLanded.NOT_LANDED if certain else manager.campaign_save_landed(record, token_before)
                if landed is SaveLanded.UNKNOWN:
                    record.usable = False
                    _logger.critical("Ambient-event save failed and could not be reconciled; session closed")
                    decision = failure_policy.classify_failure(
                        failure_policy.ActionPhase.RECONCILIATION, "unknown", error,
                    )
                    raise HTTPException(
                        status_code=decision.status_code, detail=decision.detail(commit_status="outcome_unknown"),
                    ) from None
                if landed is SaveLanded.NOT_LANDED:
                    refuse_unsaved(error)
                _logger.error(
                    "Ambient-event save committed but was not acknowledged (error_type=%s)", type(error).__name__,
                )
            # D-103: everything below runs after the commit and never rolls the live game back. If the checkpoint
            # cannot be built the click is simply not undoable; a retry with this id replays the stored receipt.
            # V5: a joined event is undone like a typed turn, with the same fields as the turn route.
            _adopt_undo_checkpoint(record, lambda: {
                "action_id": action_id,
                "player_message": transition["player_message"],
                "snapshot": snapshot,
                "journal": journal_snapshot,
                "narrative_memory": memory_snapshot,
                "lore_authority": lore_snapshot,
                "world_metadata": metadata_snapshot,
                "post_turn_fingerprint": _state_fingerprint(session),
            })
            return response_payload
