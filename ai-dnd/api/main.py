"""HTTP adapter that delegates every game turn to the frozen Python engine."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import logging
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

import game
import combat_lifecycle
import scheduled_events
import living_world
from api.campaign_journal import (
    append_ambient_event_outcome,
    update_campaign_journal,
)
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
    MAX_MODEL_CALLS_PER_TURN,
    MODEL_NAME,
    OllamaUnavailableError,
    RequiredModelUnavailableError,
    canonical_world_metadata_context,
)
from api.lore_authority.campaign_state import CANONICAL_LOCATION_TYPES
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
    CampaignStaleError,
)
from api.persistence.campaign_store import CampaignStore
from api.dnd_2024_rules import get_character_creation_catalog
from api.schemas import (
    CharacterCreationOptions,
    CharacterCreationCatalogResponse,
    AmbientEventActionRequest,
    AmbientEventCommandResult,
    AmbientEventResult,
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
    SpeciesTraitActionRequest,
    SpeciesTraitActionResult,
    SpeciesTraitCommandResult,
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
    scene_plan: dict[str, Any] | None = None,
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
    planned_location = (
        scene_plan.get("lore_location_id")
        if isinstance(scene_plan, dict)
        else None
    )
    current_location_id = planned_location or state.current_location_entity_id
    current_location = registry.entity(current_location_id)
    if (
        current_location is None
        or current_location.entity_type not in CANONICAL_LOCATION_TYPES
    ):
        current_location_id = state.current_location_entity_id
    present_npc_ids = {
        entity_id
        for npc in scheduled_events.visible_npcs(world)
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
        current_location_id=current_location_id,
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
    refs.update(
        shop["id"]
        for shop in world_state.get("shops", [])
        if isinstance(shop, dict)
        and shop.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(shop.get("id"), str)
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
    if not isinstance(evidence, dict):
        raise ValueError("Engine lore evidence has an invalid shape.")
    evidence_keys = set(evidence)
    if "telemetry" in evidence_keys:
        if not isinstance(evidence["telemetry"], dict):
            raise ValueError("Engine lore evidence telemetry has an invalid shape.")
        evidence_keys = evidence_keys - {"telemetry"}
    if evidence_keys != required_keys:
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
        if isinstance(error, CampaignStaleError):
            return HTTPException(status_code=409, detail={
                "code": "campaign_stale", "message": str(error),
            })
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

    def replay_action_response(
        response: dict[str, Any],
        response_model: type[BaseModel],
        session_id: str,
    ) -> dict[str, Any]:
        # Validate the stored contract before replacing session identity: an
        # incomplete receipt must not be repaired or reach response serialization.
        try:
            response_model.model_validate(response, strict=True)
        except ValidationError:
            raise campaign_http_exception(
                CampaignCorruptError("Campaign action response is invalid.")
            ) from None
        replay = copy.deepcopy(response)
        replay["session_id"] = session_id
        return replay

    def require_current(record: Any) -> None:
        try:
            manager.assert_current(record)
        except CampaignError as error:
            raise campaign_http_exception(error) from None

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
        "/api/game/character-creation-catalog",
        response_model=CharacterCreationCatalogResponse,
    )
    @application.get(
        "/api/character-creation-catalog",
        response_model=CharacterCreationCatalogResponse,
    )
    def character_creation_catalog() -> dict[str, Any]:
        return get_character_creation_catalog()

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
                death_mode=request.death_mode,
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
            record = get_record(session_id)
            require_current(record)
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
        action_id = str(request.action_id or uuid4())
        hash_payload = {"message": request.message, "target_id": request.target_id}
        if request.combat_action is not None:
            hash_payload["combat_action"] = request.combat_action.model_dump(exclude_none=True)
        if request.combat_id is not None:
            hash_payload.update(combat_id=request.combat_id, combat_round=request.combat_round,
                                combat_turn_index=request.combat_turn_index)
        request_hash = hashlib.sha256(
            json.dumps(
                hash_payload,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        session = record.game_session
        import bounded_encounter
        import authored_dungeon
        import exploration
        with record.turn_lock:
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            try:
                previous_action = manager.get_turn_action(record, action_id)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            if previous_action is not None:
                if previous_action["request_hash"] != request_hash:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "action_id_conflict",
                            "message": "This action ID was already used for a different turn.",
                        },
                    )
                return replay_action_response(
                    previous_action["response"], TurnResponse, session_id,
                )
            require_current(record)
            if isinstance(session, game.GameSession):
                try:
                    combat_lifecycle.validate_request(
                        session, request.message, request.target_id, combat_id=request.combat_id,
                        combat_round=request.combat_round, combat_turn_index=request.combat_turn_index,
                    )
                except combat_lifecycle.CombatRequestError as error:
                    raise HTTPException(status_code=error.status_code,
                                        detail={"code": error.code, "message": str(error)}) from None
                except ValueError:
                    raise HTTPException(status_code=409, detail={
                        "code": "invalid_combat_state", "message": "Combat state is invalid."
                    }) from None
            import spell_scope
            if isinstance(session, game.GameSession) and (
                session.character.get("current_hp", 1) <= 0
                or spell_scope.explicit_request(
                    request.message,
                    request.combat_action.model_dump(exclude_none=True) if request.combat_action else None,
                )
                or bounded_encounter.native_request(
                    session, request.message,
                    request.combat_action.model_dump(exclude_none=True) if request.combat_action else None,
                )
                or (
                    request.combat_action is None
                    and (authored_dungeon.native_request(request.message, session)
                         or exploration.native_request(request.message, session))
                )
            ):
                active_adapter = bounded_encounter.MechanicalTurnContext(active_adapter)
            if active_adapter is None:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "ollama_unavailable",
                        "message": "Authenticated Ollama service is not configured.",
                    },
                )
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
            # Runtime capability only; never serialized into campaign state.
            session._exploration_narration_available = (
                isinstance(active_adapter, bounded_encounter.MechanicalTurnContext)
                and active_adapter.adapter is not None
            )
            metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
            journal_snapshot = copy.deepcopy(record.journal)
            narrative_memory_snapshot = copy.deepcopy(
                record.narrative_memory
            )
            lore_authority_snapshot = getattr(
                record,
                "lore_authority",
                CampaignLoreState.legacy_unbound(),
            )

            def restore_turn_snapshot() -> None:
                # Checkpoint restoration can replace these separately-owned
                # values before an engine/model failure rejects the turn.
                _restore_session(session, snapshot)
                session.world_metadata = copy.deepcopy(metadata_snapshot)
                record.journal = copy.deepcopy(journal_snapshot)
                record.narrative_memory = copy.deepcopy(narrative_memory_snapshot)
                record.lore_authority = lore_authority_snapshot

            narrative_player_message = redact_sensitive_values(
                request.message
            )
            previous_lore_context = getattr(
                session, "lore_authority_context", None
            )
            try:
                if record.campaign_id is not None:
                    living_world.set_ambient_context(
                        session.world_state,
                        world_metadata_for_state(
                            session.world_state,
                            getattr(session, "world_metadata", None),
                        ),
                        session.character,
                        record.campaign_id,
                    )
                scene_plan = session.plan_living_world_turn(
                    narrative_player_message,
                    target_id=request.target_id,
                )
                lore_context = _lore_context_for_turn(
                    record,
                    session,
                    narrative_player_message,
                    request.target_id,
                    scene_plan=scene_plan,
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
                                run_turn = session.run_player_turn
                                try:
                                    run_parameters = inspect.signature(
                                        run_turn
                                    ).parameters
                                except (TypeError, ValueError):
                                    if not isinstance(session, game.GameSession):
                                        raise
                                    # GameSession exposes session-bound engine
                                    # helpers as partials. Their wrapped
                                    # signatures omit the injected session kwarg,
                                    # so inspect.signature(partial) cannot bind it.
                                    run_parameters = inspect.signature(
                                        game.run_player_turn
                                    ).parameters
                                run_kwargs = {}
                                if request.combat_action is not None:
                                    run_kwargs["combat_action"] = request.combat_action.model_dump(exclude_none=True)
                                if "scene_plan" in run_parameters:
                                    run_kwargs["scene_plan"] = scene_plan
                                if "action_id" in run_parameters:
                                    run_kwargs["action_id"] = action_id
                                if "session_id" in run_parameters:
                                    run_kwargs["session_id"] = session_id
                                if request.target_id is not None:
                                    run_kwargs["target_id"] = request.target_id
                                result = run_turn(request.message, **run_kwargs)
            except Exception as error:
                try:
                    restore_turn_snapshot()
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed (error_type=%s)",
                        type(restore_error).__name__,
                    )
                _logger.error(
                    "Engine turn failed (error_type=%s)",
                    type(error).__name__,
                )
                if isinstance(error, combat_lifecycle.CombatRequestError):
                    raise HTTPException(status_code=error.status_code,
                                        detail={"code": error.code, "message": str(error)}) from None
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
                    restore_turn_snapshot()
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

            if len(model_calls) > MAX_MODEL_CALLS_PER_TURN:
                try:
                    restore_turn_snapshot()
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
                    restore_turn_snapshot()
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

            action_result = (
                result.get("action_result")
                if isinstance(result, dict)
                else None
            )
            def contains_death_rollback(value: Any) -> bool:
                if not isinstance(value, dict):
                    return False
                resolution = value.get("death_resolution")
                if isinstance(resolution, dict) and resolution.get("rolled_back") is True:
                    return True
                for nested_key in ("death_save", "enemy_action"):
                    if contains_death_rollback(value.get(nested_key)):
                        return True
                nested_actions = value.get("enemy_actions")
                return isinstance(nested_actions, list) and any(
                    contains_death_rollback(item) for item in nested_actions
                )

            death_rolled_back = contains_death_rollback(action_result)
            if not death_rolled_back:
                set_session_world_metadata(session, metadata_snapshot)
            try:
                staged_lore_authority = (
                    record.lore_authority
                    if death_rolled_back
                    else _stage_engine_lore_state(
                        lore_authority_snapshot,
                        engine_evidence,
                        action_result,
                        snapshot["save"].get("world_state", {}),
                        session.world_state,
                    )
                )
            except Exception as error:
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                    record.narrative_memory = narrative_memory_snapshot
                    record.lore_authority = lore_authority_snapshot
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
                staged_narrative_memory = (
                    copy.deepcopy(record.narrative_memory)
                    if death_rolled_back
                    else update_narrative_memory(
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
                )
            except Exception as error:
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                    record.narrative_memory = narrative_memory_snapshot
                    record.lore_authority = lore_authority_snapshot
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
                if not death_rolled_back:
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
                    record.narrative_memory = narrative_memory_snapshot
                    record.lore_authority = lore_authority_snapshot
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
            response = TurnResponse(
                session_id=session_id,
                action_id=action_id,
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
            response_payload = redact_sensitive_values(
                response.model_dump(mode="json")
            )
            try:
                manager.autosave_turn(
                    record,
                    request.message,
                    narration,
                    combat_history_entry=combat_history_entry,
                    narrative_memory=staged_narrative_memory,
                    turn_action_receipt={
                        "action_id": action_id,
                        "request_hash": request_hash,
                        "response": response_payload,
                    },
                )
            except CampaignError as error:
                record.lore_authority = lore_authority_snapshot
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                    record.narrative_memory = narrative_memory_snapshot
                    record.lore_authority = lore_authority_snapshot
                except Exception as restore_error:
                    _logger.critical(
                        "Session rollback failed after persistence error (error_type=%s)",
                        type(restore_error).__name__,
                    )
                _logger.error(
                    "Campaign autosave failed (error_type=%s)",
                    type(error).__name__,
                )
                if isinstance(error, CampaignStaleError):
                    # Another session may have committed this ID while our
                    # real turn was running. Validate its receipt only after
                    # rollback, preserving stale handling for other races.
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
                record.lore_authority = lore_authority_snapshot
                try:
                    _restore_session(session, snapshot)
                    session.world_metadata = metadata_snapshot
                    record.journal = journal_snapshot
                    record.narrative_memory = narrative_memory_snapshot
                    record.lore_authority = lore_authority_snapshot
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
            return response_payload

    def _quest_command(session_id: str, quest_id: str, command: str) -> dict[str, Any]:
        record = get_record(session_id)
        with record.turn_lock:
            record = get_record(session_id)
            require_current(record)
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

    @application.post(
        "/api/game/sessions/{session_id}/species-actions",
        response_model=SpeciesTraitCommandResult,
    )
    def resolve_species_trait_action(
        session_id: str,
        request: SpeciesTraitActionRequest,
    ) -> dict[str, Any]:
        record = get_record(session_id)
        action_id = str(request.action_id or uuid4())
        request_hash = hashlib.sha256(json.dumps(
            {"command": "species_action", **request.model_dump(mode="json", exclude={"action_id"})},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        with record.turn_lock:
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
            require_current(record)
            snapshot = _capture_session(session)
            metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
            journal_snapshot = copy.deepcopy(record.journal)
            memory_snapshot = copy.deepcopy(record.narrative_memory)
            lore_snapshot = record.lore_authority

            def restore_command():
                _restore_session(session, snapshot)
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = memory_snapshot
                record.lore_authority = lore_snapshot

            try:
                result = session.resolve_species_trait_action(
                    request.action,
                    form=request.form,
                    ancestry=request.ancestry,
                    armed=request.armed,
                )
                response = SpeciesTraitCommandResult(
                    session_id=session_id,
                    action_id=action_id,
                    state=serialize_session_state(session, record.journal),
                    result=SpeciesTraitActionResult.model_validate(result),
                )
                response_payload = redact_sensitive_values(response.model_dump(mode="json"))
                manager.autosave_turn(
                    record, request.action, result["message"],
                    turn_action_receipt={
                        "action_id": action_id, "request_hash": request_hash,
                        "response": response_payload,
                    },
                )
                return response_payload
            except ValueError as error:
                try:
                    restore_command()
                except Exception:
                    pass
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "species_action_unavailable",
                        "message": str(error),
                    },
                ) from None
            except CampaignError as error:
                try:
                    restore_command()
                except Exception:
                    pass
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
            except Exception:
                try:
                    restore_command()
                except Exception:
                    pass
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
            ) -> dict[str, Any]:
                response = AmbientEventCommandResult(
                    session_id=session_id,
                    state=serialize_session_state(session, record.journal),
                    result=AmbientEventResult(
                        event_instance_id=event_instance_key,
                        action_id=action_id,
                        status=status,
                        reason_code=reason_code,
                        transition_id=transition_id,
                        canonical_event_id=canonical_event_id,
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

            snapshot = _capture_session(session)
            journal_snapshot = copy.deepcopy(record.journal)
            try:
                transition = session.resolve_ambient_event_action(
                    event_instance_key,
                    action_id,
                    request.action,
                )
                status = transition.get("status")
                transition_id = transition.get("transition_id")
                if status != "APPLIED":
                    _restore_session(session, snapshot)
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
                    state=serialize_session_state(session, record.journal),
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
                manager.save_campaign_locked(record, turn_action_receipt={
                    "action_id": action_id, "request_hash": request_hash,
                    "response": {"action_id": action_id, "ambient_event_response": response_payload},
                })
                return response_payload
            except Exception as error:
                try:
                    _restore_session(session, snapshot)
                except Exception as restore_error:
                    _logger.critical(
                        "Ambient-event rollback failed (error_type=%s)",
                        type(restore_error).__name__,
                    )
                finally:
                    record.journal = journal_snapshot
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

    return application


app = create_app()