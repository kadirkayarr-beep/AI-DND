"""HTTP adapter that delegates every game turn to the frozen Python engine."""

from __future__ import annotations

import copy
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import game
from api.campaign_journal import update_campaign_journal
from api.character_creation import CharacterCreationError
from api.ollama_adapter import (
    AuthenticatedOllamaAdapter,
    MODEL_NAME,
    OllamaUnavailableError,
    RequiredModelUnavailableError,
    canonical_world_metadata_context,
)
from api.narrative_director import (
    install_narrative_context_adapter,
    narrative_turn_context,
)
from api.narrative_memory import update_narrative_memory
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignError,
    CampaignNotActiveError,
    CampaignNotFoundError,
    CampaignStorageError,
)
from api.persistence.campaign_store import CampaignStore
from api.schemas import (
    CharacterCreationOptions,
    CampaignCreateRequest,
    CampaignDetailResponse,
    CampaignSessionResponse,
    CampaignSummary,
    HealthResponse,
    SessionResponse,
    TurnRequest,
    TurnResponse,
    QuestCommandResult,
    QuestState,
)
from api.serializers import (
    CombatResultSerializationError,
    SkillCheckResultSerializationError,
    redact_sensitive_values,
    serialize_combat_result,
    serialize_combat_history_entry,
    serialize_skill_check_result,
    serialize_session_state,
)
from api.session_manager import SessionManager, UnknownSessionError
from api.world_metadata import (
    set_session_world_metadata,
    world_metadata_for_state,
)


_logger = logging.getLogger("ai_dnd.api")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    _logger.addHandler(_handler)
_logger.propagate = False
_UNSET = object()


def _capture_session(session: Any) -> dict[str, Any]:
    return {
        "save": copy.deepcopy(session.serialize_game_state()),
        "messages": copy.deepcopy(session.messages),
        "rng_state": session.rng.getstate(),
    }


def _restore_session(session: Any, snapshot: dict[str, Any]) -> None:
    save_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(
                snapshot["save"],
                handle,
                ensure_ascii=False,
                allow_nan=False,
            )
            save_path = Path(handle.name)
        session.load_game(save_path)
        session.messages[:] = copy.deepcopy(snapshot["messages"])
        session.rng.setstate(snapshot["rng_state"])
    finally:
        if save_path is not None:
            save_path.unlink(missing_ok=True)


def create_app(
    *,
    session_manager: SessionManager | None = None,
    ollama_adapter: AuthenticatedOllamaAdapter | None | object = _UNSET,
) -> FastAPI:
    manager = session_manager or SessionManager(campaign_store=CampaignStore())
    adapter = (
        AuthenticatedOllamaAdapter.from_environment()
        if ollama_adapter is _UNSET
        else ollama_adapter
    )
    if adapter is not None:
        adapter.install_for_engine()
    install_narrative_context_adapter(game)

    application = FastAPI(
        title="AI-DND API",
        version="1.0.0",
        description="Thin HTTP adapter for the canonical Python AI-DND engine.",
    )
    application.state.session_manager = manager
    application.state.ollama_adapter = adapter

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Any,
        error: RequestValidationError,
    ) -> JSONResponse:
        # Pydantic's default error body includes submitted values. Omit them so
        # an accidental token in an extra field is never echoed to the client.
        safe_errors = [
            {
                "loc": [str(part) for part in item.get("loc", ())],
                "msg": str(item.get("msg", "Invalid request.")),
                "type": str(item.get("type", "validation_error")),
            }
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    def get_record(session_id: str):
        try:
            return manager.get(session_id)
        except UnknownSessionError:
            raise HTTPException(
                status_code=404,
                detail={"code": "unknown_session", "message": "Session not found."},
            ) from None

    def campaign_http_exception(error: CampaignError) -> HTTPException:
        if isinstance(error, CampaignNotFoundError):
            return HTTPException(
                status_code=404,
                detail={
                    "code": "campaign_not_found",
                    "message": "Bu macera kaydı bulunamadı.",
                },
            )
        if isinstance(error, CampaignCorruptError):
            return HTTPException(
                status_code=409,
                detail={
                    "code": "campaign_unavailable",
                    "message": "Bu macera kaydı güvenli biçimde yüklenemedi.",
                },
            )
        if isinstance(error, CampaignNotActiveError):
            return HTTPException(
                status_code=409,
                detail={
                    "code": "campaign_not_active",
                    "message": "Bu macera için açık bir oturum bulunamadı.",
                },
            )
        if isinstance(error, CampaignStorageError):
            return HTTPException(
                status_code=503,
                detail={
                    "code": "campaign_storage_unavailable",
                    "message": "Macera kaydı şu anda güvenli biçimde saklanamıyor.",
                },
            )
        return HTTPException(
            status_code=500,
            detail={
                "code": "campaign_error",
                "message": "Macera işlemi tamamlanamadı.",
            },
        )

    @application.get("/api/game/health", response_model=HealthResponse)
    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.get(
        "/api/game/character-options",
        response_model=CharacterCreationOptions,
    )
    @application.get(
        "/api/character-options",
        response_model=CharacterCreationOptions,
    )
    def character_creation_options() -> dict[str, list[str]]:
        return {"races": list(game.RACES), "classes": list(game.CLASSES)}

    @application.post("/api/game/sessions", response_model=SessionResponse)
    @application.post("/api/sessions", response_model=SessionResponse)
    def create_session() -> SessionResponse:
        session_id, record = manager.create()
        state = serialize_session_state(record.game_session, record.journal)
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
                    request.character.model_dump()
                    if request.character is not None
                    else None
                ),
            )
            return redact_sensitive_values(
                {
                    "campaign_id": campaign_id,
                    "session_id": session_id,
                    "name": metadata["name"],
                    "state": serialize_session_state(
                        record.game_session,
                        record.journal,
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

    @application.get(
        "/api/game/sessions/{session_id}/state",
        response_model=dict[str, Any],
    )
    @application.get(
        "/api/sessions/{session_id}/state",
        response_model=dict[str, Any],
    )
    def read_state(session_id: str) -> dict[str, Any]:
        record = get_record(session_id)
        with record.turn_lock:
            state = serialize_session_state(
                record.game_session,
                record.journal,
            )
        return redact_sensitive_values(state)

    @application.post(
        "/api/game/sessions/{session_id}/turn",
        response_model=TurnResponse,
    )
    @application.post(
        "/api/sessions/{session_id}/turn",
        response_model=TurnResponse,
    )
    def play_turn(session_id: str, request: TurnRequest) -> TurnResponse:
        record = get_record(session_id)
        active_adapter = application.state.ollama_adapter
        if active_adapter is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "ollama_unavailable",
                    "message": "Authenticated Ollama service is not configured.",
                },
            )

        session = record.game_session
        with record.turn_lock:
            try:
                active_adapter.ensure_required_model()
            except OllamaUnavailableError as error:
                _logger.warning(
                    "Ollama preflight failed (error_type=%s)",
                    error.error_type,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "ollama_unavailable",
                        "message": "Ollama service is unavailable.",
                    },
                ) from None
            except RequiredModelUnavailableError:
                _logger.warning("Required model qwen3:8b is unavailable.")
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "model_unavailable",
                        "message": "Required model qwen3:8b is unavailable.",
                    },
                ) from None

            snapshot = _capture_session(session)
            metadata_snapshot = dict(
                getattr(session, "world_metadata", {})
            )
            journal_snapshot = copy.deepcopy(record.journal)
            narrative_player_message = redact_sensitive_values(
                request.message
            )
            try:
                with narrative_turn_context(
                    record.narrative_memory,
                    narrative_player_message,
                ) as narrative_frame:
                    with canonical_world_metadata_context(
                        lambda: world_metadata_for_state(
                            session.world_state,
                            getattr(session, "world_metadata", None),
                        )
                    ):
                        with active_adapter.capture_model_calls() as model_calls:
                            with active_adapter.capture_model_failures() as model_failures:
                                result = session.run_player_turn(request.message)
            except Exception as error:
                try:
                    _restore_session(session, snapshot)
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed (error_type=%s)",
                        type(restore_error).__name__,
                    )
                _logger.error(
                    "Engine turn failed (error_type=%s)",
                    type(error).__name__,
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "engine_error",
                        "message": "The game turn could not be completed.",
                    },
                ) from None

            if model_failures:
                try:
                    _restore_session(session, snapshot)
                except Exception as error:
                    _logger.critical(
                        "Session rollback failed after model error (error_type=%s)",
                        type(error).__name__,
                    )
                _logger.warning(
                    "Ollama chat failed (error_type=%s)",
                    model_failures[0],
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "ollama_unavailable",
                        "message": "Ollama request failed; the turn was not committed.",
                    },
                ) from None

            if len(model_calls) > 2:
                try:
                    _restore_session(session, snapshot)
                except Exception as error:
                    _logger.critical(
                        "Session rollback failed after model-call limit (error_type=%s)",
                        type(error).__name__,
                    )
                _logger.error("Engine exceeded the per-turn model-call limit.")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "engine_error",
                        "message": "The game turn exceeded its model-call limit.",
                    },
                ) from None

            narration = result.get("narration") if isinstance(result, dict) else None
            if not isinstance(narration, str) or not narration.strip():
                try:
                    _restore_session(session, snapshot)
                except Exception as error:
                    _logger.critical(
                        "Session rollback failed after invalid engine result (error_type=%s)",
                        type(error).__name__,
                    )
                _logger.error("Engine returned an invalid turn result.")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "engine_error",
                        "message": "The game turn returned an invalid response.",
                    },
                ) from None

            set_session_world_metadata(session, metadata_snapshot)
            action_result = (
                result.get("action_result")
                if isinstance(result, dict)
                else None
            )
            try:
                staged_narrative_memory = update_narrative_memory(
                    record.narrative_memory,
                    player_message=narrative_player_message,
                    narration=redact_sensitive_values(narration),
                    action_result=action_result,
                    world_state_before=snapshot["save"].get(
                        "world_state",
                        {},
                    ),
                    world_state_after=session.world_state,
                    world_metadata=world_metadata_for_state(
                        session.world_state,
                        getattr(session, "world_metadata", None),
                    ),
                )
            except Exception as error:
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed after narrative-memory error (error_type=%s)",
                        type(restore_error).__name__,
                    )
                _logger.error(
                    "Narrative continuity update failed (error_type=%s)",
                    type(error).__name__,
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "narrative_memory_error",
                        "message": "Campaign continuity could not be updated safely.",
                    },
                ) from None
            try:
                skill_check_result = serialize_skill_check_result(
                    action_result,
                    session,
                )
                combat_result = serialize_combat_result(action_result)
                combat_history_entry = serialize_combat_history_entry(
                    combat_result,
                    session,
                )
                presence_location_id = None
                if (
                    isinstance(action_result, dict)
                    and action_result.get("action") == "query"
                    and action_result.get("query_type") == "presence"
                ):
                    resolve_location = getattr(
                        session,
                        "resolve_location_reference",
                        None,
                    )
                    requested_location = (
                        resolve_location(request.message)
                        if callable(resolve_location)
                        else None
                    )
                    presence_location_id = (
                        requested_location
                        or session.world_state.get("location")
                    )
                record.journal = update_campaign_journal(
                    record.journal,
                    snapshot["save"],
                    session.serialize_game_state(),
                    action_result,
                    world_metadata_for_state(
                        session.world_state,
                        getattr(session, "world_metadata", None),
                    ),
                    presence_location_id=presence_location_id,
                )
                state = serialize_session_state(session, record.journal)
            except Exception as error:
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed after journal update error (error_type=%s)",
                        type(restore_error).__name__,
                    )
                if isinstance(error, SkillCheckResultSerializationError):
                    _logger.error(
                        "Engine returned an invalid skill-check result."
                    )
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "code": "engine_error",
                            "message": "The skill-check result could not be verified safely.",
                        },
                    ) from None
                if isinstance(error, CombatResultSerializationError):
                    _logger.error(
                        "Engine returned an invalid combat result or history entry."
                    )
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "code": "engine_error",
                            "message": "The combat result could not be verified safely.",
                        },
                    ) from None
                _logger.error(
                    "Campaign journal update failed (error_type=%s)",
                    type(error).__name__,
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "journal_error",
                        "message": "The campaign journal could not be updated safely.",
                    },
                ) from None
            try:
                manager.autosave_turn(
                    record,
                    request.message,
                    narration,
                    combat_history_entry=combat_history_entry,
                    narrative_memory=staged_narrative_memory,
                )
            except CampaignError as error:
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed after persistence error (error_type=%s)",
                        type(restore_error).__name__,
                    )
                _logger.error(
                    "Campaign autosave failed (error_type=%s)",
                    type(error).__name__,
                )
                raise campaign_http_exception(error) from None

            _logger.info(
                "Game turn completed (model=%s, model_calls=%d, narrative_scene=%s, narrative_tokens=%s, narrative_estimated_total=%s, narrative_budget=%s/%s, narrative_context_bytes=%s, narrative_selected=%s, narrative_ambiguities=%d)",
                MODEL_NAME,
                len(model_calls),
                narrative_frame.diagnostics.get("scene_type", "unavailable"),
                narrative_frame.diagnostics.get("estimated_tokens", "unavailable"),
                narrative_frame.diagnostics.get(
                    "estimated_total_tokens",
                    "unavailable",
                ),
                narrative_frame.diagnostics.get(
                    "max_estimated_total_tokens",
                    "unavailable",
                ),
                narrative_frame.diagnostics.get(
                    "model_context_window_tokens",
                    "unavailable",
                ),
                narrative_frame.diagnostics.get("packet_characters", "unavailable"),
                narrative_frame.diagnostics.get("selected_counts", {}),
                len(narrative_frame.diagnostics.get("ambiguities", [])),
            )
            response = TurnResponse(
                session_id=session_id,
                narration=narration,
                state=state,
                combat_result=combat_result,
                combat_history_entry=combat_history_entry,
                skill_check_result=skill_check_result,
                quest_outcomes=(
                    action_result.get("quest_outcomes", [])
                    if isinstance(action_result, dict)
                    else []
                ),
            )
            return redact_sensitive_values(response.model_dump())

    def _quest_command(session_id: str, quest_id: str, command: str) -> dict[str, Any]:
        record = get_record(session_id)
        with record.turn_lock:
            session = record.game_session
            snapshot = _capture_session(session)
            try:
                result = getattr(session, f"{command}_quest")(quest_id)
            except ValueError as error:
                try:
                    _restore_session(session, snapshot)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=404,
                    detail={"code": "quest_unavailable", "message": str(error)},
                ) from None
            try:
                state = serialize_session_state(session, record.journal)
                public_quest = QuestState.model_validate(
                    {
                    "quest_id": result["quest"]["quest_id"],
                    "title": result["quest"]["title"],
                    "description": result["quest"]["description"],
                    "status": result["quest"]["status"],
                    "giver_npc_id": result["quest"].get("giver_npc_id"),
                    "objectives": [
                        {
                            "objective_id": item["objective_id"],
                            "description": item["description"],
                            "status": item["status"],
                            "progress": item.get("progress", 0),
                            "required_count": item.get("required_count", 1),
                        }
                        for item in result["quest"]["objectives"]
                    ],
                    }
                )
                response = QuestCommandResult(
                    session_id=session_id,
                    state=state,
                    quest=public_quest,
                    outcome=result["transition"],
                )
                if record.campaign_id is not None:
                    manager.save_campaign_locked(record)
                return redact_sensitive_values(response.model_dump())
            except CampaignError as error:
                try:
                    _restore_session(session, snapshot)
                except Exception:
                    pass
                raise campaign_http_exception(error) from None
            except Exception:
                try:
                    _restore_session(session, snapshot)
                except Exception:
                    pass
                raise

    @application.post(
        "/api/game/sessions/{session_id}/quests/{quest_id}/accept",
        response_model=QuestCommandResult,
    )
    def accept_quest(session_id: str, quest_id: str) -> dict[str, Any]:
        return _quest_command(session_id, quest_id, "accept")

    @application.post(
        "/api/game/sessions/{session_id}/quests/{quest_id}/cancel",
        response_model=QuestCommandResult,
    )
    def cancel_quest(session_id: str, quest_id: str) -> dict[str, Any]:
        return _quest_command(session_id, quest_id, "cancel")

    return application


app = create_app()