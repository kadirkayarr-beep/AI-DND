"""POST level-up route moved out of api.main.create_app (D-531 stage 2): same paths, receipts, save and rollback."""
from __future__ import annotations

from api.routes_level_up import level_up_projection
import copy
import hashlib
import json
from typing import Any
from fastapi import FastAPI, HTTPException
from api.persistence.campaign_models import (
    CampaignError,
)
from api.persistence.campaign_store import CampaignStore
from api.serializers import (
    redact_sensitive_values,
    serialize_session_state,
)
from api.schemas import LevelUpApplyRequest, LevelUpCommandResult


def register_level_up_apply_routes(
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
    _store_refusal: Any,
) -> None:
    @application.post("/api/game/sessions/{session_id}/level-up", response_model=LevelUpCommandResult,
                      operation_id="applyGameSessionLevelUp")
    @application.post("/api/sessions/{session_id}/level-up", response_model=LevelUpCommandResult,
                      include_in_schema=False)
    def apply_earned_level_up(session_id: str, request: LevelUpApplyRequest) -> dict[str, Any]:
        import character_progression as progression
        record = get_record(session_id)
        if record.campaign_id is None:
            raise HTTPException(status_code=409, detail={"code": "campaign_persistence_required"})
        action_id = str(request.action_id)
        request_hash = hashlib.sha256(json.dumps(
            {"command": "level_up", **request.model_dump(mode="json", exclude={"action_id"})},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()

        def refusal(status_code: int, code: str) -> HTTPException:
            detail = {"code": code, "message": "Seviye seçimi uygulanmadı.", "not_applied": True}
            durable = _store_refusal(manager, record, action_id, request_hash, status_code, detail)
            if not durable:
                detail.pop("not_applied")
            return HTTPException(status_code=status_code, detail=detail)

        try:
            claim = manager.claim_action_intent(record, action_id, request_hash)
        except CampaignError as error:
            raise campaign_http_exception(error) from None
        if claim["outcome"] == "hash_conflict":
            raise HTTPException(status_code=409, detail={"code": "action_id_conflict"})
        if claim["outcome"] == "conflict":
            error = refusal(409, "unresolved_action")
            error.detail["unresolved_action_id"] = claim["unresolved_action_id"]
            raise error
        with record.turn_lock:
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            ensure_usable(record)
            try:
                previous = manager.get_turn_action(record, action_id)
                if previous is not None:
                    if previous["request_hash"] != request_hash:
                        raise HTTPException(status_code=409, detail={"code": "action_id_conflict"})
                    return replay_action_response(previous["response"], LevelUpCommandResult, session_id)
                refused = manager.get_refused_action(record, action_id)
                if refused is not None:
                    if refused["request_hash"] not in (request_hash, CampaignStore.ABANDONED_REQUEST_HASH):
                        raise HTTPException(status_code=409, detail={"code": "action_id_conflict"})
                    raise HTTPException(status_code=refused["status_code"], detail=refused["detail"])
                manager.assert_current(record)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            if str(request.campaign_id) != record.campaign_id:
                raise refusal(409, "level_up_campaign_mismatch")
            public = level_up_projection(record, session_id)
            if request.expected_revision != public["revision"]:
                raise refusal(409, "level_up_preview_stale")
            if public["status"] != "ready":
                raise refusal(409, public["reason"] or "level_up_unavailable")
            if request.target_level != public["target_level"]:
                raise refusal(409, "level_up_preview_stale")
            session = record.game_session
            preview = progression.preview_level_up(session, request.target_level)
            choices = request.choices.model_dump(mode="json")
            if request.target_level in (3, 4, 5):
                from api.schemas import (BarbarianLevel2Choices, BarbarianLevel3Choices, FighterLevel3Choices, MonkLevel3Choices, PaladinLevel3Choices, RogueLevel3Choices, SorcererLevel3Choices,
                                         BarbarianLevel4Choices, LevelUpChoices, LevelUpFiveChoices, PaladinLevel4Choices, PaladinLevel5Choices,
                                         ClericLevel3Choices, ClericLevel4Choices, WizardLevel3Choices, WizardLevel4Choices, WizardSpellbookChoices)
                expected_choices = {
                    3: {"Barbarian": BarbarianLevel3Choices, "Fighter": FighterLevel3Choices, "Monk": MonkLevel3Choices, "Paladin": PaladinLevel3Choices, "Rogue": RogueLevel3Choices, "Sorcerer": SorcererLevel3Choices,
                        "Wizard": WizardLevel3Choices, "Cleric": ClericLevel3Choices},
                    4: {"Barbarian": BarbarianLevel4Choices, "Fighter": BarbarianLevel4Choices, "Monk": BarbarianLevel4Choices, "Paladin": PaladinLevel4Choices, "Rogue": BarbarianLevel4Choices, "Sorcerer": LevelUpChoices,
                        "Wizard": WizardLevel4Choices, "Cleric": ClericLevel4Choices},
                    # Barbarian 5 has no choices: the same empty strict object as Barbarian 2 (no new schema).
                    5: {"Barbarian": BarbarianLevel2Choices, "Fighter": BarbarianLevel2Choices, "Monk": BarbarianLevel2Choices, "Paladin": PaladinLevel5Choices, "Rogue": BarbarianLevel2Choices, "Sorcerer": LevelUpFiveChoices,
                        "Wizard": WizardSpellbookChoices, "Cleric": BarbarianLevel2Choices},
                }[request.target_level][session.character["class"]]
                if not isinstance(request.choices, expected_choices):
                    raise refusal(409, "level_up_choice_class_mismatch")
            # Validate before entering the mutation transaction; failures are durable refusals.
            problem = progression._check_choices(session, preview, choices)
            if problem:
                raise refusal(409, problem)
            snapshot = _capture_session(session)
            had_format = "_persisted_engine_format" in session.__dict__
            previous_format = copy.deepcopy(session.__dict__.get("_persisted_engine_format"))
            response_payload = None
            try:
                result = progression.apply_level_choices(session, preview, choices)
                if result["status"] != "applied":
                    raise ValueError("Validated level choices could not be applied.")
                response_payload = redact_sensitive_values(LevelUpCommandResult(
                    session_id=session_id, action_id=action_id,
                    state=serialize_session_state(session, record.journal, record.lore_authority), result=result,
                ).model_dump(mode="json"))
                manager.save_campaign_locked(record, turn_action_receipt={
                    "action_id": action_id, "request_hash": request_hash, "response": response_payload,
                    "public_state": serialize_session_state(session, record.journal, record.lore_authority),
                })
            except Exception as error:
                _raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, response_payload, error,
                    adopt=lambda: setattr(record, "undo_checkpoint", None),
                )
                if had_format:
                    session._persisted_engine_format = previous_format
                else:
                    session.__dict__.pop("_persisted_engine_format", None)
                _rollback_session(record, session, snapshot)
                if isinstance(error, CampaignError):
                    raise campaign_http_exception(error) from None
                raise HTTPException(status_code=500, detail={"code": "level_up_failed", "message": "Seviye seçimi güvenle kaydedilemedi."}) from None
            record.undo_checkpoint = None
            return response_payload
