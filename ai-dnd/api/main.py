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
from api.ollama_adapter import (
    AuthenticatedOllamaAdapter,
    OllamaUnavailableError,
    RequiredModelUnavailableError,
)
from api.schemas import HealthResponse, SessionResponse, TurnRequest, TurnResponse
from api.serializers import redact_sensitive_values, serialize_session_state
from api.session_manager import SessionManager, UnknownSessionError


_logger = logging.getLogger("ai_dnd.api")
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
    manager = session_manager or SessionManager()
    adapter = (
        AuthenticatedOllamaAdapter.from_environment()
        if ollama_adapter is _UNSET
        else ollama_adapter
    )
    if adapter is not None:
        adapter.install_for_engine()

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

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.post("/api/sessions", response_model=SessionResponse)
    def create_session() -> SessionResponse:
        session_id, record = manager.create()
        state = serialize_session_state(record.game_session)
        return SessionResponse(
            session_id=session_id,
            state=redact_sensitive_values(state),
        )

    @application.get(
        "/api/sessions/{session_id}/state",
        response_model=dict[str, Any],
    )
    def read_state(session_id: str) -> dict[str, Any]:
        record = get_record(session_id)
        with record.turn_lock:
            state = serialize_session_state(record.game_session)
        return redact_sensitive_values(state)

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
            try:
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

            response = TurnResponse(
                session_id=session_id,
                narration=narration,
                state=serialize_session_state(session),
            )
            return redact_sensitive_values(response.model_dump())

    return application


app = create_app()