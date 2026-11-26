"""Session-creation and campaign list/create/get/delete/resume/save routes moved out of api.main.create_app (D-531 stage 5):
same paths, order, bodies and error mapping.

api.main's serialize_session_state is read through the passed `api_main` module at call time, as the closure did,
so a patch on api.main still reaches these routes.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from api.character_creation import CharacterCreationError
from api.lore_authority import InvalidCampaignStartError
from api.persistence.campaign_models import CampaignError
from api.schemas import (
    CampaignCreateRequest,
    CampaignDetailResponse,
    CampaignSessionResponse,
    CampaignSummary,
    SessionResponse,
)
from api.serializers import redact_sensitive_values


def register_campaign_routes(application: FastAPI, *, manager: Any, campaign_http_exception: Any, api_main: Any) -> None:
    @application.post("/api/game/sessions", response_model=SessionResponse)
    def create_session() -> SessionResponse:
        session_id, record = manager.create()
        state = api_main.serialize_session_state(
            record.game_session,
            record.journal,
            record.lore_authority,
        )
        return SessionResponse(
            session_id=session_id,
            state=redact_sensitive_values(state),
        )

    @application.get(
        "/api/campaigns",
        response_model=list[CampaignSummary],
    )
    @application.get(
        "/api/game/campaigns",
        response_model=list[CampaignSummary],
    )
    def list_campaigns() -> list[dict[str, Any]]:
        try:
            return redact_sensitive_values(manager.list_campaigns())
        except CampaignError as error:
            raise campaign_http_exception(error) from None

    @application.post(
        "/api/campaigns",
        response_model=CampaignSessionResponse,
    )
    @application.post(
        "/api/game/campaigns",
        response_model=CampaignSessionResponse,
    )
    def create_campaign(request: CampaignCreateRequest) -> dict[str, Any]:
        try:
            campaign_id, session_id, record, metadata = manager.create_campaign(
                request.name,
                character=(
                    request.character.model_dump(by_alias=True, exclude_none=True)
                    if request.character is not None
                    else None
                ),
                campaign_start=(
                    request.campaign_start.model_dump()
                    if request.campaign_start is not None
                    else None
                ),
                death_mode=request.death_mode,
            )
            return redact_sensitive_values(
                {
                    "campaign_id": campaign_id,
                    "session_id": session_id,
                    "name": metadata["name"],
                    "state": api_main.serialize_session_state(
                        record.game_session,
                        record.journal,
                        record.lore_authority,
                    ),
                    "history": [],
                    "combat_history": [],
                }
            )
        except CharacterCreationError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_character", "message": str(error)},
            ) from None
        except InvalidCampaignStartError:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_campaign_start",
                    "message": "The selected campaign start is not available.",
                },
            ) from None
        except CampaignError as error:
            raise campaign_http_exception(error) from None

    @application.get(
        "/api/campaigns/{campaign_id}",
        response_model=CampaignDetailResponse,
    )
    @application.get(
        "/api/game/campaigns/{campaign_id}",
        response_model=CampaignDetailResponse,
    )
    def get_campaign(campaign_id: str) -> dict[str, Any]:
        try:
            return redact_sensitive_values(manager.get_campaign_detail(campaign_id))
        except CampaignError as error:
            raise campaign_http_exception(error) from None

    @application.delete("/api/campaigns/{campaign_id}")
    @application.delete("/api/game/campaigns/{campaign_id}")
    def delete_campaign(campaign_id: str) -> dict[str, Any]:
        try:
            return manager.delete_campaign(campaign_id)
        except CampaignError as error:
            raise campaign_http_exception(error) from None

    @application.post(
        "/api/campaigns/{campaign_id}/resume",
        response_model=CampaignSessionResponse,
    )
    @application.post(
        "/api/game/campaigns/{campaign_id}/resume",
        response_model=CampaignSessionResponse,
    )
    def resume_campaign(campaign_id: str) -> dict[str, Any]:
        try:
            session_id, record, metadata, history, state = manager.resume_campaign(
                campaign_id
            )
            return redact_sensitive_values(
                {
                    "campaign_id": campaign_id,
                    "session_id": session_id,
                    "name": metadata["name"],
                    "state": state,
                    "history": history,
                    "combat_history": record.combat_history,
                }
            )
        except CampaignError as error:
            raise campaign_http_exception(error) from None

    @application.post(
        "/api/campaigns/{campaign_id}/save",
        response_model=CampaignSummary,
    )
    @application.post(
        "/api/game/campaigns/{campaign_id}/save",
        response_model=CampaignSummary,
    )
    def save_campaign(campaign_id: str) -> dict[str, Any]:
        try:
            return redact_sensitive_values(manager.save_campaign(campaign_id))
        except CampaignError as error:
            raise campaign_http_exception(error) from None
