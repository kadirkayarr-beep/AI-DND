"""Quest accept/cancel routes moved out of api.main.create_app (D-531 stage 2): same paths, order, locks, save and rollback."""
from __future__ import annotations

from typing import Any
from fastapi import FastAPI, HTTPException
from api import failure_policy
import adventure.projection as adventure_projection
from api.persistence.campaign_models import (
    CampaignError,
    CampaignNotActiveError,
    CampaignNotFoundError,
    CampaignStaleError,
    SaveLanded,
)
from api.schemas import (
    QuestCommandResult,
    QuestState,
)
from api.serializers import (
    redact_sensitive_values,
    serialize_session_state,
)


def register_quest_routes(
    application: FastAPI,
    *,
    get_record: Any,
    require_current: Any,
    refuse_while_action_open: Any,
    campaign_http_exception: Any,
    manager: Any,
    _capture_session: Any,
    _rollback_session: Any,
    _logger: Any,
) -> None:
    def _quest_command(session_id: str, quest_id: str, command: str) -> dict[str, Any]:
        record = get_record(session_id)
        with record.turn_lock:
            record = get_record(session_id)
            refuse_while_action_open(record)
            require_current(record)
            session = record.game_session
            snapshot = _capture_session(session)
            lore_before = record.lore_authority
            token_before = getattr(session, "_campaign_persistence_version", None)
            if getattr(session, "campaign_lore_state", None) is not None:
                # D-189: a committed turn moves only the record's lore and a resume reloads it, so a copy left on the
                # session can be older; the command starts it from the record, like play_turn, before reading it below.
                session.campaign_lore_state = record.lore_authority

            def put_back() -> None:
                record.lore_authority = lore_before
                _rollback_session(record, session, snapshot)

            try:
                result = getattr(session, f"{command}_quest")(quest_id)
            except ValueError as error:
                put_back()
                raise HTTPException(
                    status_code=404,
                    detail={"code": "quest_unavailable", "message": str(error)},
                ) from None
            try:
                lore_for_view = getattr(session, "campaign_lore_state", None) or record.lore_authority
                if lore_for_view is not None:
                    record.lore_authority = lore_for_view
                state = serialize_session_state(session, record.journal, record.lore_authority)
                quest_payload = result["quest"]
                if quest_payload.get("record_kind") == "dynamic":
                    quest_payload = adventure_projection.command_view(quest_payload)
                public_quest = QuestState.model_validate(
                    {
                    "quest_id": quest_payload["quest_id"],
                    "title": quest_payload["title"],
                    "description": quest_payload["description"],
                    "status": quest_payload["status"],
                    "giver_npc_id": quest_payload.get("giver_npc_id"),
                    "objectives": [
                        {
                            "objective_id": item["objective_id"],
                            "description": item["description"],
                            "status": item["status"],
                            "progress": item.get("progress", 0),
                            "required_count": item.get("required_count", 1),
                        }
                        for item in quest_payload["objectives"]
                    ],
                    }
                )
                response = QuestCommandResult(
                    session_id=session_id,
                    state=state,
                    quest=public_quest,
                    outcome=result["transition"],
                )
                # Built before the save, so nothing after a commit can fail and put the live game back.
                payload = redact_sensitive_values(response.model_dump())
            except CampaignError as error:
                put_back()
                raise campaign_http_exception(error) from None
            except Exception:
                put_back()
                raise
            if record.campaign_id is None:
                return payload
            try:
                manager.save_campaign_locked(record)
            except Exception as error:
                # Stale, unknown and closed campaigns are refused inside the transaction before anything is written.
                certain = isinstance(error, (CampaignStaleError, CampaignNotFoundError, CampaignNotActiveError))
                landed = SaveLanded.NOT_LANDED if certain else manager.campaign_save_landed(record, token_before)
                if landed is SaveLanded.UNKNOWN:
                    # Committed or not cannot be told; rolling back could split memory from storage (R05/R06).
                    record.usable = False
                    _logger.critical("Quest save failed and could not be reconciled; session closed")
                    decision = failure_policy.classify_failure(
                        failure_policy.ActionPhase.RECONCILIATION, "unknown", error,
                    )
                    raise HTTPException(
                        status_code=decision.status_code, detail=decision.detail(commit_status="outcome_unknown"),
                    ) from None
                if landed is SaveLanded.LANDED:
                    # The database holds exactly this result: the live game stays on it and the answer is the truth.
                    _logger.error("Quest save committed but was not acknowledged (error_type=%s)", type(error).__name__)
                    return payload
                put_back()
                if isinstance(error, CampaignError):
                    raise campaign_http_exception(error) from None
                raise
            return payload

    @application.post(
        "/api/game/sessions/{session_id}/quests/{quest_id}/accept",
        response_model=QuestCommandResult,
    )
    @application.post(
        "/api/sessions/{session_id}/quests/{quest_id}/accept",
        response_model=QuestCommandResult,
    )
    def accept_quest(session_id: str, quest_id: str) -> dict[str, Any]:
        return _quest_command(session_id, quest_id, "accept")

    @application.post(
        "/api/game/sessions/{session_id}/quests/{quest_id}/cancel",
        response_model=QuestCommandResult,
    )
    @application.post(
        "/api/sessions/{session_id}/quests/{quest_id}/cancel",
        response_model=QuestCommandResult,
    )
    def cancel_quest(session_id: str, quest_id: str) -> dict[str, Any]:
        return _quest_command(session_id, quest_id, "cancel")
