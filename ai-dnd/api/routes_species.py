"""Species-action routes moved out of api.main.create_app (D-531 stage 2): same paths, order, locks, receipts and rollback."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any
from fastapi import FastAPI, HTTPException
from api.persistence.campaign_models import (
    CampaignError,
    CampaignStaleError,
)
from api.persistence.campaign_store import CampaignStore
from api.schemas import (
    SpeciesTraitActionRequest,
    SpeciesTraitActionResult,
    SpeciesTraitCommandResult,
)
from api.serializers import (
    redact_sensitive_values,
    serialize_session_state,
)


def _run_species_action(record: Any, session: Any, request: SpeciesTraitActionRequest, session_lore_snapshot: Any) -> dict[str, Any]:
    """The engine call and its quest/award follow-ups, moved out of the route body unchanged (size lock)."""
    quest_before = copy.deepcopy(session.world_state)
    result = session.resolve_species_trait_action(
        request.action,
        form=request.form,
        ancestry=request.ancestry,
        armed=request.armed,
        **({"healing_amount": request.healing_amount, "remove_poisoned": request.remove_poisoned}
           if request.action == "lay_on_hands" else {}),
        **({"draconic_ancestry": request.draconic_ancestry} if request.action == "choose_draconic_ancestry"
           else {"shape": request.shape, "target_id": request.target_id} if request.action == "breath_weapon"
           else {}),
    )
    # D-105: a combat species action can end the turn and its damage (Inner Radiance) can drop a quest
    # target; like the play turn, the quest owner reads this command's own before/after world. The
    # panel command carries no player words, so last turn's text must not ask for work here.
    if (quest_before.get("combat") or {}).get("active") and isinstance(result.get("effects"), dict):
        session._adventure_player_text = ""
        # A reward's faction standing is written onto the session's lore copy; that copy can be missing
        # or older than the record's, so it starts from the record and the record takes the result.
        session.campaign_lore_state = record.lore_authority
        # D-187: a fight this command ended reaches the adventure hooks (aftermath offer, combat count).
        ended = ({"combat_ended": True, "end_reason": session.world_state["combat"].get("end_reason")}
                 if not session.world_state["combat"].get("active") else {})
        transitions = session.evaluate_quest_events(
            quest_before, {"action": "species_action", "species_action": request.action,
                           "status": "resolved", **ended},
        )
        record.lore_authority = session.campaign_lore_state
        # A session without a copy stays without one: a later turn moves only the record's lore, so a copy
        # left here would turn stale. A copy that was already there (hear, a paid reward, Undo, a rolled-back
        # turn) takes the new record lore: a quest command or the next turn reads it before the record.
        session.campaign_lore_state = None if session_lore_snapshot is None else record.lore_authority
        if transitions:
            result["effects"]["quest_outcomes"] = transitions
    # D-003: an award this command paid (a fight it ended, a bounty it closed) is announced by this
    # command and its history entry, not one turn late by the next play turn (whose Undo would repeat it).
    paid = session._publish_level_up({}).get("level_up")
    import xp
    lines = [xp.award_line(paid)] if paid is not None else []
    lines += session._take_xp_unrecorded()  # D-061: a forfeited award's line goes the same way
    if lines:
        result["message"] = f"{result['message']} {' '.join(lines)}"
    return result


def register_species_routes(
    application: FastAPI,
    *,
    get_record: Any,
    require_current: Any,
    ensure_usable: Any,
    refuse_while_action_open: Any,
    replay_action_response: Any,
    campaign_http_exception: Any,
    manager: Any,
    _capture_session: Any,
    _rollback_session: Any,
    _raise_if_commit_unconfirmed: Any,
) -> None:
    @application.post(
        "/api/game/sessions/{session_id}/species-actions",
        response_model=SpeciesTraitCommandResult,
    )
    def resolve_species_trait_action(
        session_id: str,
        request: SpeciesTraitActionRequest,
    ) -> dict[str, Any]:
        record = get_record(session_id)
        action_id = str(request.action_id)
        request_hash = hashlib.sha256(json.dumps(
            {"command": "species_action", **request.model_dump(mode="json", exclude={"action_id"} | {
                field for field in ("draconic_ancestry", "shape", "target_id") if getattr(request, field) is None})},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        with record.turn_lock:
            ensure_usable(record)
            session = record.game_session
            try:
                previous = manager.get_turn_action(record, action_id)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            get_record(session_id)
            if previous is not None:
                if previous["request_hash"] != request_hash:
                    raise HTTPException(status_code=409, detail={
                        "code": "action_id_conflict",
                        "message": "This action ID was already used for a different action.",
                    })
                return replay_action_response(
                    previous["response"], SpeciesTraitCommandResult, session_id,
                )
            # Same contract as play_turn, after receipt replay and before any engine work: a stored refusal (the
            # player's abandon writes one for any request body) answers instead of the engine; another body is a conflict.
            try:
                refused = manager.get_refused_action(record, action_id)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            if refused is not None:
                if refused["request_hash"] not in (request_hash, CampaignStore.ABANDONED_REQUEST_HASH):
                    raise HTTPException(status_code=409, detail={
                        "code": "action_id_conflict",
                        "message": "This action ID was already used for a different action.",
                    })
                raise HTTPException(status_code=refused["status_code"], detail=refused["detail"])
            refuse_while_action_open(record)
            require_current(record)
            snapshot = _capture_session(session)
            metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
            journal_snapshot = copy.deepcopy(record.journal)
            memory_snapshot = copy.deepcopy(record.narrative_memory)
            lore_snapshot = record.lore_authority
            session_lore_snapshot = getattr(session, "campaign_lore_state", None)

            def restore_command():
                _rollback_session(record, session, snapshot)
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = memory_snapshot
                record.lore_authority = lore_snapshot
                session.campaign_lore_state = session_lore_snapshot

            response_payload = None
            try:
                result = _run_species_action(record, session, request, session_lore_snapshot)
                response = SpeciesTraitCommandResult(
                    session_id=session_id,
                    action_id=action_id,
                    state=serialize_session_state(session, record.journal, record.lore_authority),
                    result=SpeciesTraitActionResult.model_validate(result),
                )
                response_payload = redact_sensitive_values(response.model_dump(mode="json"))
                manager.autosave_turn(
                    record, request.action, result["message"],
                    turn_action_receipt={
                        "action_id": action_id, "request_hash": request_hash,
                        "response": response_payload,
                    },
                    narration_source="deterministic_system",  # the engine's own result message
                )
                return response_payload
            except ValueError as error:
                restore_command()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "species_action_unavailable",
                        "message": str(error),
                    },
                ) from None
            except CampaignError as error:
                _raise_if_commit_unconfirmed(manager, record, action_id, request_hash, response_payload, error)
                restore_command()
                if isinstance(error, CampaignStaleError):
                    # The winning receipt may only become visible at save time.
                    # Classify changed commands after rolling back speculative
                    # mechanics; identical requests retain stale-save recovery.
                    try:
                        previous = manager.get_turn_action(record, action_id)
                    except CampaignError as receipt_error:
                        raise campaign_http_exception(receipt_error) from None
                    if previous is not None and previous["request_hash"] != request_hash:
                        raise HTTPException(status_code=409, detail={
                            "code": "action_id_conflict",
                            "message": "This action ID was already used for a different action.",
                        }) from None
                raise campaign_http_exception(error) from None
            except Exception as error:
                _raise_if_commit_unconfirmed(manager, record, action_id, request_hash, response_payload, error)
                restore_command()
                raise

    @application.post(
        "/api/sessions/{session_id}/species-actions",
        response_model=SpeciesTraitCommandResult,
    )
    def resolve_species_trait_action_compat(
        session_id: str,
        request: SpeciesTraitActionRequest,
    ) -> dict[str, Any]:
        return resolve_species_trait_action(session_id, request)
