"""HTTP adapter that delegates every game turn to the frozen Python engine."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import game
from api.campaign_journal import update_campaign_journal
from api.character_creation import CharacterCreationError
from api.lore_authority import (
    BindingStatus,
    CampaignCanonOverride,
    CampaignLoreState,
    EngineActionEvidence,
    InvalidCampaignStartError,
    PRODUCTION_REGISTRY,
    PRODUCTION_START_CATALOG,
    apply_campaign_override,
)
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
    CampaignStartOptionsResponse,
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


def _lore_entity_reference(registry: Any, npc: Any) -> str | None:
    if not isinstance(npc, dict):
        return None
    for candidate in (npc.get("lore_entity_id"), npc.get("id")):
        if not isinstance(candidate, str):
            continue
        entity = registry.entity(candidate)
        if entity is not None and entity.entity_type.value == "CANONICAL_NPC":
            return candidate
    return None


def _lore_context_for_turn(
    record: Any,
    session: Any,
    player_message: str,
    target_id: str | None,
    registry: Any = PRODUCTION_REGISTRY,
) -> dict[str, Any]:
    state = getattr(record, "lore_authority", CampaignLoreState.legacy_unbound())
    if state.binding_status is not BindingStatus.BOUND:
        return registry.retrieve_lore_context(
            campaign_state=state,
            player_message=player_message,
        )

    world = session.world_state
    location = world.get("location")
    present_npc_ids = {
        entity_id
        for npc in world.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == location
        for entity_id in [_lore_entity_reference(registry, npc)]
        if entity_id is not None
    }
    target_npc_id = None
    if isinstance(target_id, str):
        target_npc = next(
            (
                npc for npc in world.get("npcs", [])
                if isinstance(npc, dict) and npc.get("id") == target_id
            ),
            None,
        )
        target_npc_id = _lore_entity_reference(registry, target_npc)
    mentioned = registry.mentioned_entity_ids(
        player_message,
        region_scope=state.region_id,
    )
    quest_subject_ids = {
        "quest:" + hashlib.sha256(quest_id.encode("utf-8")).hexdigest()[:32]
        for quest in world.get("quests", [])
        if isinstance(quest, dict)
        and isinstance(quest_id := quest.get("quest_id"), str)
        and quest_id
    }
    return registry.retrieve_lore_context(
        current_location_id=state.current_location_entity_id,
        player_message=player_message,
        mentioned_entity_ids=mentioned,
        present_npc_ids=present_npc_ids,
        active_quest_subject_ids=quest_subject_ids,
        campaign_state=state,
        target_npc_id=target_npc_id,
        include_dm_secrets=False,
    )


def _procedural_entity_refs(world_state: Any) -> set[str]:
    if not isinstance(world_state, dict):
        return set()
    refs = {
        str(entity.get("id", location_id))
        for location_id, entity in world_state.get("locations", {}).items()
        if isinstance(entity, dict)
        and entity.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
    }
    refs.update(
        npc["id"]
        for npc in world_state.get("npcs", [])
        if isinstance(npc, dict)
        and npc.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(npc.get("id"), str)
    )
    return refs


def _stage_engine_lore_state(
    state: CampaignLoreState,
    evidence: Any,
    action_result: Any,
    before_world: Any,
    after_world: Any,
) -> CampaignLoreState:
    if evidence is None:
        return state
    required_keys = {
        "authority",
        "action_id",
        "turn_index",
        "quest_outcomes",
        "procedural_entity_ids",
    }
    if not isinstance(evidence, dict) or set(evidence) != required_keys:
        raise ValueError("Engine lore evidence has an invalid shape.")
    turn_index = after_world.get("flags", {}).get("turn_index")
    action_id = f"turn:{turn_index}"
    if (
        evidence["authority"] != "python_engine"
        or type(turn_index) is not int
        or evidence["turn_index"] != turn_index
        or evidence["action_id"] != action_id
    ):
        raise ValueError("Engine lore evidence does not match the committed turn.")
    outcomes = evidence["quest_outcomes"]
    expected_outcomes = (
        action_result.get("quest_outcomes", [])
        if isinstance(action_result, dict)
        else []
    )
    if not isinstance(outcomes, list) or outcomes != expected_outcomes:
        raise ValueError("Engine quest evidence does not match the action result.")
    before_refs = _procedural_entity_refs(before_world)
    after_refs = _procedural_entity_refs(after_world)
    expected_refs = after_refs - before_refs
    supplied_refs = evidence["procedural_entity_ids"]
    if (
        not isinstance(supplied_refs, list)
        or any(not isinstance(item, str) for item in supplied_refs)
        or set(supplied_refs) != expected_refs
        or len(supplied_refs) != len(expected_refs)
    ):
        raise ValueError("Engine procedural-entity evidence does not match world state.")

    updated = state
    if expected_refs:
        updated = replace(
            updated,
            procedural_entity_refs=tuple(
                dict.fromkeys((*updated.procedural_entity_refs, *sorted(expected_refs)))
            ),
        )
    if updated.binding_status is BindingStatus.BOUND:
        action_evidence = EngineActionEvidence(
            action_id=action_id,
            turn_index=turn_index,
            authority="python_engine",
        )
        for outcome in outcomes:
            if (
                not isinstance(outcome, dict)
                or outcome.get("transition")
                not in {"objective_progress", "objective_completed", "completed"}
                or outcome.get("turn_index") != turn_index
                or not isinstance(outcome.get("quest_id"), str)
                or not isinstance(outcome.get("event_id"), str)
            ):
                raise ValueError("Engine quest transition is invalid.")
            event_digest = hashlib.sha256(
                outcome["event_id"].encode("utf-8")
            ).hexdigest()[:32]
            quest_digest = hashlib.sha256(
                outcome["quest_id"].encode("utf-8")
            ).hexdigest()[:32]
            override = CampaignCanonOverride.from_mapping({
                "override_id": f"quest_event:{event_digest}",
                "subject_id": f"quest:{quest_digest}",
                "predicate": "quest_transition",
                "object_id_or_value": outcome["transition"],
                "source_action_id": action_id,
                "created_turn": turn_index,
                "notes": (
                    f"Python-confirmed quest {outcome['quest_id']} "
                    f"transition: {outcome['transition']}."
                ),
            })
            updated = apply_campaign_override(
                updated,
                override,
                evidence=action_evidence,
            )
    return CampaignLoreState.from_mapping(updated.to_dict())


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

    @application.get(
        "/api/game/campaign-start-options",
        response_model=CampaignStartOptionsResponse,
    )
    @application.get(
        "/api/campaign-start-options",
        response_model=CampaignStartOptionsResponse,
    )
    def campaign_start_options() -> dict[str, Any]:
        return PRODUCTION_START_CATALOG.to_response()

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
                campaign_start=(
                    request.campaign_start.model_dump()
                    if request.campaign_start is not None
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
            lore_authority_snapshot = getattr(
                record,
                "lore_authority",
                CampaignLoreState.legacy_unbound(),
            )
            narrative_player_message = redact_sensitive_values(
                request.message
            )
            previous_lore_context = getattr(
                session, "lore_authority_context", None
            )
            try:
                lore_context = _lore_context_for_turn(
                    record,
                    session,
                    narrative_player_message,
                    request.target_id,
                )
                lore_diagnostics = lore_context.get("diagnostics", {})
                _logger.info(
                    "Lore retrieval turn=%s selected_fact_count=%s selected_fact_ids=%s",
                    session.world_state.get("flags", {}).get("turn_index", 0) + 1,
                    lore_diagnostics.get("selected_fact_count", 0),
                    lore_diagnostics.get("selected_fact_ids", []),
                )
                session.lore_authority_context = lore_context
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
                                if request.target_id is None:
                                    result = session.run_player_turn(request.message)
                                else:
                                    result = session.run_player_turn(
                                        request.message,
                                        target_id=request.target_id,
                                    )
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
            finally:
                session.lore_authority_context = previous_lore_context

            engine_evidence = (
                result.pop("_engine_event_evidence", None)
                if isinstance(result, dict)
                else None
            )

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
                staged_lore_authority = _stage_engine_lore_state(
                    lore_authority_snapshot,
                    engine_evidence,
                    action_result,
                    snapshot["save"].get("world_state", {}),
                    session.world_state,
                )
            except Exception as error:
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed after lore-evidence error (error_type=%s)",
                        type(restore_error).__name__,
                    )
                _logger.error(
                    "Engine lore evidence failed validation (error_type=%s)",
                    type(error).__name__,
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "engine_error",
                        "message": "Campaign lore evidence could not be verified.",
                    },
                ) from None
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
            record.lore_authority = staged_lore_authority
            try:
                manager.autosave_turn(
                    record,
                    request.message,
                    narration,
                    combat_history_entry=combat_history_entry,
                    narrative_memory=staged_narrative_memory,
                )
            except CampaignError as error:
                record.lore_authority = lore_authority_snapshot
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
            except Exception as error:
                record.lore_authority = lore_authority_snapshot
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed after unexpected persistence error (error_type=%s)",
                        type(restore_error).__name__,
                    )
                _logger.error(
                    "Campaign autosave failed (error_type=%s)",
                    type(error).__name__,
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "persistence_error",
                        "message": "The campaign turn could not be saved safely.",
                    },
                ) from None

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