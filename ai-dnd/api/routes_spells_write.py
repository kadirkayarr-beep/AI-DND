"""POST spellcasting/prepare route moved out of api.main.create_app (D-531 stage 2): same path, receipts, rollback."""
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
    SpellPrepareCommandResult,
    SpellPrepareRequest,
    SpellPrepareResult,
)
from api.serializers import (
    redact_sensitive_values,
    serialize_session_state,
)


def register_spell_prepare_routes(
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
    @application.post("/api/game/sessions/{session_id}/spellcasting/prepare", response_model=SpellPrepareCommandResult,
                      operation_id="prepareGameSessionSpells")
    def prepare_spells(session_id: str, request: SpellPrepareRequest) -> dict[str, Any]:
        """4C.2: save the player's preparation list (same receipt, replay and rollback contract as species actions)."""
        import spell_preparation
        record = get_record(session_id)
        action_id = str(request.action_id)
        # D-039: an absent spellbook stays out of the hash, so receipts saved before the field existed still replay.
        request_hash = hashlib.sha256(json.dumps(
            {"command": "spell_prepare", **request.model_dump(
                mode="json", exclude={"action_id", *(("spellbook",) if request.spellbook is None else ())})},
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
                return replay_action_response(previous["response"], SpellPrepareCommandResult, session_id)
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

            def restore_command():
                _rollback_session(record, session, snapshot)
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = memory_snapshot
                record.lore_authority = lore_snapshot

            response_payload = None
            try:
                try:
                    window = spell_preparation.view(session)
                except (ValueError, KeyError, TypeError):
                    raise HTTPException(status_code=409, detail={
                        "code": "prepare_unavailable", "message": "Kayıtlı büyü durumu okunamadı."}) from None
                if request.spellbook is not None:
                    # D-039: the one-time spellbook choice of an old save's Wizard, on its own (never with a list or close).
                    if request.prepared is not None or request.close:
                        raise HTTPException(status_code=409, detail={
                            "code": "prepare_request_mixed",
                            "message": "Büyü kitabı seçimi tek başına gönderilir; hazırlık listesi ondan sonra kaydedilir."})
                    result = spell_preparation.choose_spellbook(session, list(request.spellbook))
                elif window["blocked_reason"] == "spellbook_missing":
                    raise HTTPException(status_code=409, detail={
                        "code": "prepare_spellbook_missing",
                        "message": "Büyü kitabın kayıtta yok; bu eski kayıt büyü seçimlerini taşımıyor."})
                elif not window["supported"]:
                    raise HTTPException(status_code=409, detail={
                        "code": "prepare_not_supported", "message": "Bu sınıf büyü hazırlamaz."})
                elif not window["open"]:
                    raise HTTPException(status_code=409, detail={
                        "code": "prepare_window_closed",
                        "message": "Büyü hazırlamak için uzun dinlenmeyi yeni bitirmiş ya da yeni bir seviyeye geçmiş olmalısın."})
                else:
                    prepared = None if request.prepared is None else list(request.prepared)
                    result = spell_preparation.prepare(session, prepared, close=request.close)
                response = SpellPrepareCommandResult(
                    session_id=session_id, action_id=action_id,
                    state=serialize_session_state(session, record.journal, record.lore_authority),
                    result=SpellPrepareResult.model_validate(result),
                )
                response_payload = redact_sensitive_values(response.model_dump(mode="json"))
                if result["status"] == "too_many":
                    return response_payload  # a question: nothing changed, so nothing is saved and no receipt is kept
                manager.autosave_turn(
                    record, "spell_prepare", result["message"],
                    turn_action_receipt={"action_id": action_id, "request_hash": request_hash,
                                         "response": response_payload},
                    narration_source="deterministic_system",  # spell_preparation's own result message
                )
                return response_payload
            except HTTPException:
                restore_command()
                raise
            except ValueError as error:
                restore_command()
                raise HTTPException(status_code=409, detail={
                    "code": getattr(error, "code", "prepare_unavailable"), "message": str(error)}) from None
            except CampaignError as error:
                _raise_if_commit_unconfirmed(manager, record, action_id, request_hash, response_payload, error)
                restore_command()
                if isinstance(error, CampaignStaleError):
                    # Same as species actions: the winning receipt may only become visible at save time.
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
