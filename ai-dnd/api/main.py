"""HTTP adapter that delegates every game turn to the frozen Python engine."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import logging
import os

import game
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from api import action_contract, failure_policy, runtime_recovery
from api.auth import (
    AuthenticationError,
    FailClosedAuthenticator,
    OidcAuthenticator,
    Principal,
    current_principal,
    SESSION_COOKIE,
    authenticate,
    bind_principal,
    clear_session_cookie,
    request_marker_present,
    reset_principal,
    select_authenticator,
)
from api.auth_diagnostics import enabled_for_request, safe_failure_category
import campaign_time
import combat_lifecycle
import scheduled_events
import living_world
import adventure.projection as adventure_projection
from api.clerk_auth import ClerkAuthenticator
from api.campaign_journal import (
    append_ambient_event_outcome,
    update_campaign_journal,
)
from api.character_creation import CharacterCreationError
from api.identity_suggestion import (
    IdentitySuggestionJob,
    IdentitySuggestionRequest,
    IdentitySuggestionService,
    chain_provider,
)
from api.lore_authority import (
    BindingStatus,
    CampaignCanonOverride,
    CampaignLoreState,
    EngineActionEvidence,
    InvalidCampaignStartError,
    PRODUCTION_REGISTRY,
    PRODUCTION_START_CATALOG,
    apply_campaign_override,
    apply_committed_world_canon,
    is_setting_place,
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
from api.local_play import LocalPlayAuthenticator
from api.persistence.campaign_store import CampaignStore, StartupCampaignStore
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
    LevelUpResult,
    SessionResponse,
    TurnOutcome,
    TurnRequest,
    TurnResponse,
    TurnUndoRequest,
    TurnUndoResponse,
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
from api.schemas import LevelUpApplyRequest, LevelUpPreviewResponse, LevelUpCommandResult
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
# What the player reads when a model failed and the turn was rolled back: a lost sentence, not a stuck game.
MODEL_FAILURE_MESSAGE = "Bunu tam yakalayamadım; bir daha, belki biraz farklı söyler misin?"


def _capture_session(session: Any) -> dict[str, Any]:
    return {
        "save": copy.deepcopy(session.serialize_game_state()),
        "runtime": session._capture_runtime_snapshot(),
    }


def _restore_session(session: Any, snapshot: dict[str, Any]) -> None:
    session._restore_runtime_snapshot(snapshot["runtime"])


def _commit_already_durable(
    manager: Any, record: Any, action_id: str, request_hash: str, response_payload: dict[str, Any],
) -> bool | None:
    """After a failed autosave: True only if THIS action's receipt is durably stored with this exact result.

    A lost commit acknowledgement leaves the database on the new revision. Rolling the live runtime back then would
    split memory from storage, so the runtime stays on the committed state and the caller answers "unconfirmed",
    never success and never "not applied". If the lookup itself fails the answer is UNKNOWN (None): the caller must not
    guess in either direction.
    """
    try:
        stored = manager.get_turn_action(record, action_id)
    except Exception:
        return None
    return (
        stored is not None
        and stored["request_hash"] == request_hash
        and action_contract.result_digest(stored["response"]) == action_contract.result_digest(response_payload)
    )


def _raise_if_commit_unconfirmed(
    manager: Any, record: Any, action_id: str, request_hash: str, response_payload: dict[str, Any] | None,
    error: Exception, adopt: Any = None,
) -> None:
    """Keep the live runtime on the committed revision when the database already holds this action's receipt.

    `adopt` brings the rest of the live record (narrative memory, history caches, undo checkpoint) to the stored state.
    """
    if response_payload is None or isinstance(error, CampaignStaleError):
        return  # Stale: the check runs inside the transaction before anything is written, provably not committed.
    durable = _commit_already_durable(manager, record, action_id, request_hash, response_payload)
    if durable is None:
        # Neither "committed" nor "rolled back" can be claimed, and rolling the runtime back could split it from storage.
        # The safe stance is the quarantine: the session closes, durable truth is what a restart resumes (R05/R06).
        record.usable = False
        _logger.critical("Campaign autosave failed and its receipt could not be reconciled; session closed")
        decision = failure_policy.classify_failure(failure_policy.ActionPhase.RECONCILIATION, "unknown", error)
        raise HTTPException(status_code=decision.status_code, detail=decision.detail(commit_status="outcome_unknown")) from None
    if not durable:
        return
    if adopt is not None:
        adopt()
    _logger.error("Campaign autosave committed but was not acknowledged (error_type=%s)", type(error).__name__)
    decision = failure_policy.classify_failure(failure_policy.ActionPhase.COMMIT_UNKNOWN, "unknown", error)
    raise HTTPException(
        status_code=decision.status_code,
        detail=decision.detail(commit_status="committed_unconfirmed"),
    ) from None


def _rollback_session(record: Any, session: Any, snapshot: dict[str, Any]) -> None:
    """Restore the pre-turn snapshot; close the session unless the restore is VERIFIED (R05).

    A restore that raises, or that returns without leaving the snapshot's state, is a double fault: the runtime may be
    dirty, so every route refuses it and nothing from it is ever saved. Only restore_trusted_runtime reopens it.
    """
    if not runtime_recovery.restore_trusted_runtime(
        record, snapshot, restore=lambda target, trusted: _restore_session(target, trusted),
    ):
        _logger.critical("Session restore could not be verified; session closed")
        decision = failure_policy.classify_failure(
            failure_policy.ActionPhase.RESOLVED_UNCOMMITTED, "quarantined", RuntimeError("restore not verified"),
        )
        raise HTTPException(status_code=decision.status_code, detail=decision.detail()) from None


def _turn_outcome(action_result: Any) -> TurnOutcome | None:
    """Player-safe receipt projection for the result card (LR00-P5)."""
    if not isinstance(action_result, dict):
        return None
    inspection = action_result.get("inspection") if isinstance(action_result.get("inspection"), dict) else {}
    place = action_result.get("local_place") if isinstance(action_result.get("local_place"), dict) else {}

    def short(value: Any, limit: int) -> str | None:
        return str(value)[:limit] if isinstance(value, str) and value.strip() else None

    return TurnOutcome(
        action=short(action_result.get("action"), 48),
        status=short(action_result.get("status"), 48),
        kind=short(action_result.get("kind") or place.get("kind") or inspection.get("target_kind"), 48),
        target_name=short(inspection.get("target_name") or action_result.get("target_name"), 120),
        found=inspection.get("found") if isinstance(inspection.get("found"), bool) else None,
        place_created=place.get("created") if isinstance(place.get("created"), bool) else None,
    )


def _state_fingerprint(session: Any) -> str:
    return hashlib.sha256(json.dumps(
        session.serialize_game_state(), sort_keys=True, ensure_ascii=False, default=str,
    ).encode("utf-8")).hexdigest()


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


def _campaign_lore_year(world: Any) -> int:
    """Use the campaign clock year, or the bound 1501 epoch when no clock exists."""
    public = campaign_time.public_time(world) if isinstance(world, dict) else None
    year = public.get("year") if isinstance(public, dict) else None
    if type(year) is int:
        return year
    return 1501


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
        return _with_player_adventure(
            registry.retrieve_lore_context(
                campaign_state=state,
                player_message=player_message,
                campaign_year=_campaign_lore_year(getattr(session, "world_state", None)),
            ),
            getattr(session, "world_state", None),
            state,
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
        or not is_setting_place(current_location)
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
    return _with_player_adventure(
        registry.retrieve_lore_context(
            current_location_id=current_location_id,
            player_message=player_message,
            mentioned_entity_ids=mentioned,
            present_npc_ids=present_npc_ids,
            active_quest_subject_ids=quest_subject_ids,
            campaign_state=state,
            target_npc_id=target_npc_id,
            include_dm_secrets=False,
            campaign_year=_campaign_lore_year(world),
        ),
        world,
        state,
    )


def _with_player_adventure(context, world, lore_state=None):
    """Attach the player-safe adventure slice without a new model call."""
    if not isinstance(context, dict):
        return context
    packet = adventure_projection.model_packet(
        world if isinstance(world, dict) else {},
        lore_state,
    )
    candidate = dict(context)
    candidate["player_adventure"] = packet
    encoded = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 12 * 1024:
        return context
    return candidate


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
        updated = apply_committed_world_canon(
            updated,
            evidence=action_evidence,
            before_world=before_world,
            after_world=after_world,
            action_result=action_result,
            registry=PRODUCTION_REGISTRY,
        )
    return CampaignLoreState.from_mapping(updated.to_dict())


def create_app(
    *,
    session_manager: SessionManager | None = None,
    ollama_adapter: AuthenticatedOllamaAdapter | None | object = _UNSET,
    authenticator: object = _UNSET,
    identity_suggestions: IdentitySuggestionService | None = None,
) -> FastAPI:
    manager = session_manager or SessionManager(campaign_store=StartupCampaignStore())
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
    if authenticator is _UNSET:
        authenticator = select_authenticator(os.environ)
    application.state.authenticator = authenticator
    application.state.ollama_adapter = adapter
    cloud_chain = getattr(adapter, "cloud_chain", None)
    application.state.identity_suggestions = identity_suggestions or IdentitySuggestionService(
        chain_provider(cloud_chain) if cloud_chain else None
    )

    @application.middleware("http")
    async def require_verified_principal(request: Any, call_next: Any) -> Any:
        path = request.url.path
        verifier = application.state.authenticator
        # Local play proves locality on every path, public ones included.
        local_play = type(verifier) is LocalPlayAuthenticator
        if not local_play and (not path.startswith("/api") or path in _PUBLIC_API_PATHS):
            return await call_next(request)
        try:
            if local_play:
                principal = verifier.authenticate_asgi(request.scope)
            elif type(verifier) is OidcAuthenticator:
                if (
                    request.method in {"POST", "PUT", "PATCH", "DELETE"}
                    and not request_marker_present(request.headers)
                ):
                    raise AuthenticationError("Authentication failed.")
                principal = verifier.authenticate(request.cookies.get(SESSION_COOKIE))
            elif type(verifier) is ClerkAuthenticator:
                # Verification and JWKS refresh run off the event loop. The
                # cache still allows only one in-flight fetch.
                principal = await asyncio.to_thread(
                    verifier.authenticate_asgi,
                    tuple(request.scope.get("headers", ())),
                    tuple(request.cookies.items()),
                )
            else:
                principal = authenticate(verifier)
        except AuthenticationError as error:
            if enabled_for_request(
                os.environ.get("AI_DND_AUTH_DIAGNOSTICS"),
                os.environ.get("AI_DND_AUTH_MODE"),
                request.scope.get("server"),
            ):
                _logger.warning(
                    "isolated_auth_rejected category=%s",
                    safe_failure_category(getattr(error, "diagnostic_category", None)),
                )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": {
                        "code": "authentication_required",
                        "message": "Kimlik doğrulaması gerekli.",
                    },
                },
            )
        token = bind_principal(principal)
        try:
            return await call_next(request)
        finally:
            reset_principal(token)

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

    def ensure_usable(record: Any) -> None:
        if not getattr(record, "usable", True):
            decision = failure_policy.classify_failure(
                failure_policy.ActionPhase.RESOLVED_UNCOMMITTED, "quarantined", RuntimeError("session closed"),
            )
            raise HTTPException(status_code=decision.status_code, detail=decision.detail())

    def get_record(session_id: str):
        try:
            record = manager.get(session_id)
        except UnknownSessionError:
            raise HTTPException(
                status_code=404,
                detail={"code": "unknown_session", "message": "Session not found."},
            ) from None
        ensure_usable(record)
        return record

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

    def action_archived_error() -> HTTPException:
        # R08: the action WAS applied; only its stored reply was archived. It is refused, never re-run, never treated as new.
        return HTTPException(status_code=409, detail={
            "code": "action_archived",
            "message": "This action was already applied; its stored reply was archived and it will not be run again.",
        })

    def replay_action_response(
        response: dict[str, Any] | None,
        response_model: type[BaseModel],
        session_id: str,
    ) -> dict[str, Any]:
        if response is None:
            raise action_archived_error()
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

    @application.get("/api/game/health", response_model=HealthResponse, response_model_exclude_none=True)
    @application.get("/api/health", response_model=HealthResponse, response_model_exclude_none=True)
    def health(response: Response) -> HealthResponse:
        response.headers["X-AI-DND-Instance"] = str(os.getpid())
        return HealthResponse(
            model=adapter.model_name if adapter is not None else MODEL_NAME,
            model_chain=getattr(adapter, "model_chain", None),
        )

    @application.post("/api/logout", status_code=204)
    @application.post("/api/game/logout", status_code=204)
    def logout(request: Request) -> Response:
        # This clears the legacy OIDC cookie only. A Clerk bearer token is not
        # revoked and remains valid until its own exp.
        if not request_marker_present(request.headers):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "authentication_required",
                    "message": "Kimlik doğrulaması gerekli.",
                },
            )
        response = Response(status_code=204)
        clear_session_cookie(response, secure=request.url.scheme == "https")
        return response

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

    suggestions = application.state.identity_suggestions

    @application.post(
        "/api/game/character-identity-suggestions",
        response_model=IdentitySuggestionJob,
    )
    @application.post(
        "/api/character-identity-suggestions",
        response_model=IdentitySuggestionJob,
    )
    def create_character_identity_suggestion(
        body: IdentitySuggestionRequest,
    ) -> IdentitySuggestionJob:
        return suggestions.submit(body, _suggestion_principal())

    @application.get(
        "/api/game/character-identity-suggestions/{request_id}",
        response_model=IdentitySuggestionJob,
    )
    @application.get(
        "/api/character-identity-suggestions/{request_id}",
        response_model=IdentitySuggestionJob,
    )
    def read_character_identity_suggestion(request_id: str) -> IdentitySuggestionJob:
        job = suggestions.get(request_id, _suggestion_principal())
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "suggestion_not_found",
                    "message": "Öneri işi bulunamadı.",
                },
            )
        return job

    @application.post("/api/game/sessions", response_model=SessionResponse)
    @application.post("/api/sessions", response_model=SessionResponse)
    def create_session() -> SessionResponse:
        session_id, record = manager.create()
        state = serialize_session_state(
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
                    "state": serialize_session_state(
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
                record.lore_authority,
            )
        return redact_sensitive_values(state)

    def action_status_payload(record: Any, session_id: str, action_id: str, state: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"action_id": action_id, "state": state}
        if state == "applied":
            receipt = manager.get_turn_action(record, action_id) or {}
            stored = receipt.get("response")
            payload["response"] = None
            if isinstance(stored, dict):
                try:
                    payload["response"] = replay_action_response(stored, TurnResponse, session_id)
                except HTTPException:
                    payload["response"] = None  # a receipt of another command kind: applied, but not a turn reply
        elif state == "not_applied":
            refused = manager.get_refused_action(record, action_id)
            payload["detail"] = refused["detail"] if refused else None
        elif state == "open":
            payload["processing"] = record.turn_lock.locked()
        return payload

    @application.get(
        "/api/game/sessions/{session_id}/actions/unresolved",
        response_model=dict[str, Any],
    )
    def read_unresolved_action(session_id: str) -> dict[str, Any]:
        record = get_record(session_id)
        if record.revoked:
            raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
        try:
            return {"unresolved": manager.unresolved_action(record)}
        except CampaignError as error:
            raise campaign_http_exception(error) from None

    @application.get(
        "/api/game/sessions/{session_id}/actions/{action_id}",
        response_model=dict[str, Any],
    )
    def read_action_status(session_id: str, action_id: str) -> dict[str, Any]:
        record = get_record(session_id)
        if record.revoked:
            raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
        try:
            return action_status_payload(record, session_id, action_id, manager.action_state(record, action_id))
        except CampaignError as error:
            raise campaign_http_exception(error) from None

    @application.post(
        "/api/game/sessions/{session_id}/actions/{action_id}/abandon",
        response_model=dict[str, Any],
    )
    def abandon_action(session_id: str, action_id: str) -> dict[str, Any]:
        """Player-initiated close of an action id; the answer comes from the stored receipt or refusal only."""
        record = get_record(session_id)
        if not record.turn_lock.acquire(timeout=2.0):
            # A turn of this session is running: its outcome is not known yet, so the identity is kept.
            return {"action_id": action_id, "state": "processing"}
        try:
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            try:
                result = manager.abandon_action(record, action_id)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            payload = action_status_payload(record, session_id, action_id, result["state"])
        finally:
            record.turn_lock.release()
        return payload

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
        effective_mode = "do" if request.combat_action is not None else request.interaction_mode
        hash_payload = {"message": request.message, "target_id": request.target_id}
        # Omitted modes keep the legacy hash used by saved turn receipts.
        if request.interaction_mode is not None:
            hash_payload["interaction_mode"] = request.interaction_mode
        if request.combat_action is not None:
            hash_payload["combat_action"] = request.combat_action.model_dump(exclude_none=True)
        if request.check_feature is not None:
            hash_payload["check_feature"] = request.check_feature
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
        if not record.revoked:
            # Before waiting for the turn lock: only one action per campaign may be unresolved at a time, and a
            # different id is refused atomically against the stored intents, not against browser memory.
            try:
                claim = manager.claim_action_intent(record, action_id, request_hash)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            if claim["outcome"] == "hash_conflict":
                raise HTTPException(status_code=409, detail={
                    "code": "action_id_conflict",
                    "message": "This action ID was already used for a different turn.",
                })
            if claim["outcome"] == "conflict":
                detail = {
                    "code": "unresolved_action",
                    "message": "An earlier action of this campaign is still unresolved.",
                    "unresolved_action_id": claim["unresolved_action_id"],
                    "not_applied": True,
                }
                try:
                    durable = manager.record_refused_action(record, action_id, request_hash, 409, detail)
                except Exception:
                    _logger.error("Refusal record could not be saved; no never-applied claim is made.", exc_info=True)
                    durable = False
                if not durable:
                    detail.pop("not_applied")
                raise HTTPException(status_code=409, detail=detail)
        with record.turn_lock:
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            # A request that queued behind a failing one must not run on a runtime that failure just quarantined (R05).
            ensure_usable(record)
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
            try:
                refused = manager.get_refused_action(record, action_id)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            if refused is not None:
                if refused["request_hash"] not in (request_hash, CampaignStore.ABANDONED_REQUEST_HASH):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "action_id_conflict",
                            "message": "This action ID was already used for a different turn.",
                        },
                    )
                raise HTTPException(status_code=refused["status_code"], detail=refused["detail"])

            def refuse_before_commit(status_code: int, code: str, message: str) -> HTTPException:
                """Close this action id for good after a refusal raised before any effect.

                The not_applied claim is made only when the refusal record is durably stored under the turn
                lock; otherwise the same refusal is returned without that claim.
                """
                detail = {"code": code, "message": message, "not_applied": True}
                try:
                    durable = manager.record_refused_action(record, action_id, request_hash, status_code, detail)
                except Exception:
                    _logger.error("Refusal record could not be saved; no never-applied claim is made.", exc_info=True)
                    durable = False
                if not durable:
                    detail = {"code": code, "message": message}
                return HTTPException(status_code=status_code, detail=detail)

            def refuse_model_failure(code: str, message: str = MODEL_FAILURE_MESSAGE) -> HTTPException:
                """Answer a model failure on a turn that applied nothing, and let the campaign go on.

                The failure says nothing about the campaign, so the open intent is released instead of holding every later
                move: any new id runs, and this same id may run again. The not_applied claim needs a verified rollback.
                """
                detail = {"code": code, "message": message}
                try:
                    if getattr(record, "usable", True) and manager.release_action_intent(record, action_id, request_hash):
                        detail["not_applied"] = True
                except Exception:
                    _logger.error("Action intent could not be released; no never-applied claim is made.", exc_info=True)
                return HTTPException(status_code=503, detail=detail)

            try:
                manager.assert_current(record)
            except CampaignError as error:
                # An intent that was claimed earlier stays open (it may be running in another session); only the same
                # id with the same payload, or the player's server-proven abandon, closes it.
                raise campaign_http_exception(error) from None
            if isinstance(session, game.GameSession):
                try:
                    combat_lifecycle.validate_request(
                        session,
                        request.message if effective_mode in {None, "do"} else "",
                        request.target_id if effective_mode in {None, "do"} else None,
                        combat_id=request.combat_id,
                        combat_round=request.combat_round, combat_turn_index=request.combat_turn_index,
                    )
                except combat_lifecycle.CombatRequestError as error:
                    raise refuse_before_commit(error.status_code, error.code, str(error)) from None
                except ValueError:
                    raise refuse_before_commit(409, "invalid_combat_state", "Combat state is invalid.") from None
            # Pure opt-in admission precedes adapter preflight and every mutating
            # scene/lore planner. Ordinary turns retain their existing order.
            if request.check_feature is not None:
                try:
                    session.primal_knowledge_check_admission(
                        request.message, interaction_mode=effective_mode,
                        combat_action=request.combat_action, target_id=request.target_id,
                        check_feature=request.check_feature,
                    )
                except combat_lifecycle.CombatRequestError as error:
                    raise refuse_before_commit(error.status_code, error.code, str(error)) from None
            check_evidence = [] if request.check_feature is not None else None
            import spell_scope
            import sorcery_points
            slot_conversion = isinstance(session, game.GameSession) and sorcery_points.native_conversion_request(
                request.combat_action.model_dump(exclude_none=True) if request.combat_action else None,
            )
            if isinstance(session, game.GameSession) and (
                session.character.get("current_hp", 1) <= 0
                or slot_conversion
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
                raise refuse_model_failure("ollama_unavailable")
            try:
                active_adapter.ensure_required_model()
            except OllamaUnavailableError as error:
                _logger.warning(
                    "Ollama preflight failed (error_type=%s)",
                    error.error_type,
                )
                raise refuse_model_failure("ollama_unavailable") from None
            except RequiredModelUnavailableError:
                selected_model = adapter.model_name if adapter is not None else MODEL_NAME
                _logger.warning("Required model %s is unavailable.", selected_model)
                # Saying it again cannot help a model that is not installed, so this one stays a plain, truthful setup message.
                raise refuse_model_failure(
                    "model_unavailable", f"Required model {selected_model} is unavailable.",
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
                try:
                    _rollback_session(record, session, snapshot)
                    session.world_metadata = copy.deepcopy(metadata_snapshot)
                    record.journal = copy.deepcopy(journal_snapshot)
                    record.narrative_memory = copy.deepcopy(
                        narrative_memory_snapshot
                    )
                    record.lore_authority = lore_authority_snapshot
                    session.campaign_lore_state = lore_authority_snapshot
                except HTTPException:
                    raise
                except Exception as restore_error:
                    record.usable = False
                    _logger.critical(
                        "Turn snapshot restore failed (error_type=%s); session closed",
                        type(restore_error).__name__,
                    )
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "session_restore_failed",
                            "message": "Oturum güvenli biçimde geri alınamadı ve kapatıldı.",
                        },
                    ) from None

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
                effective_target_id = (
                    None
                    if effective_mode == "ask_dm" or slot_conversion
                    else request.target_id
                )
                plan_kwargs = {"target_id": effective_target_id}
                if effective_mode is not None:
                    try:
                        plan_parameters = inspect.signature(
                            session.plan_living_world_turn
                        ).parameters
                    except (TypeError, ValueError):
                        plan_parameters = inspect.signature(
                            game.plan_living_world_turn
                        ).parameters
                    if "interaction_mode" in plan_parameters:
                        plan_kwargs["interaction_mode"] = effective_mode
                # Exact resource-only conversion has no scene/reference authority.
                # Its display label or a retained UI target must not focus an NPC,
                # materialize a place, or alter an existing conversation first.
                scene_plan = None if slot_conversion else session.plan_living_world_turn(
                    narrative_player_message,
                    **plan_kwargs,
                )
                lore_context = _lore_context_for_turn(
                    record,
                    session,
                    narrative_player_message,
                    effective_target_id,
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
                session.campaign_lore_state = lore_authority_snapshot
                with narrative_turn_context(
                    record.narrative_memory,
                    narrative_player_message,
                    journal=record.journal,
                ) as narrative_frame:
                    missing_claims = object()
                    previous_claims = getattr(
                        session, "_supported_player_claims", missing_claims
                    )
                    # This transient request context contains only player
                    # utterances already bound to stable NPC IDs in saved
                    # continuity. It is never part of the serialized session.
                    session._supported_player_claims = copy.deepcopy(
                        narrative_frame.selected_player_claims
                    )
                    try:
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
                                    if request.check_feature is not None:
                                        run_kwargs.update(check_feature=request.check_feature, check_evidence=check_evidence)
                                    if request.combat_action is not None:
                                        run_kwargs["combat_action"] = request.combat_action.model_dump(exclude_none=True)
                                    if "scene_plan" in run_parameters:
                                        run_kwargs["scene_plan"] = scene_plan
                                    if (
                                        "interaction_mode" in run_parameters
                                        and effective_mode is not None
                                    ):
                                        run_kwargs["interaction_mode"] = effective_mode
                                    if "action_id" in run_parameters:
                                        run_kwargs["action_id"] = action_id
                                    if "session_id" in run_parameters:
                                        run_kwargs["session_id"] = session_id
                                    if effective_target_id is not None:
                                        run_kwargs["target_id"] = effective_target_id
                                    try:
                                        result = run_turn(request.message, **run_kwargs)
                                    except game.PlayerCannotAct:
                                        restore_turn_snapshot()
                                        result = session.player_cannot_act_turn()
                    finally:
                        if previous_claims is missing_claims:
                            delattr(session, "_supported_player_claims")
                        else:
                            session._supported_player_claims = previous_claims
            except Exception as error:
                try:
                    restore_turn_snapshot()
                except HTTPException:
                    raise
                except Exception as restore_error:
                    record.usable = False
                    _logger.critical(
                        "Session rollback failed (error_type=%s); session closed",
                        type(restore_error).__name__,
                    )
                if isinstance(error, HTTPException):
                    raise
                _logger.error(
                    "Engine turn failed (error_type=%s, rolled_back=true)",
                    type(error).__name__,
                    exc_info=True,
                )
                from dialogue_runtime import DialogueResponseError, DialogueProviderError
                if isinstance(error, DialogueProviderError):
                    raise refuse_model_failure("ollama_unavailable") from None
                if isinstance(error, DialogueResponseError):
                    raise refuse_model_failure("invalid_dialogue_response") from None
                # The snapshot was restored above (a failed restore raised session_restore_failed
                # and never reaches here), so these refusals are "certainly never applied".
                if isinstance(error, combat_lifecycle.CombatRequestError):
                    raise refuse_before_commit(error.status_code, error.code, str(error)) from None
                raise refuse_before_commit(500, "engine_error", "The game turn could not be completed.") from None
            finally:
                session.lore_authority_context = previous_lore_context

            engine_evidence = (
                result.pop("_engine_event_evidence", None)
                if isinstance(result, dict)
                else None
            )
            if isinstance(engine_evidence, dict):
                # The API's rollback snapshot is the commit boundary. Derive
                # entity additions from those exact before/after states so
                # pre-planner materialization is included in the receipt.
                engine_evidence = {
                    **engine_evidence,
                    "procedural_entity_ids": sorted(
                        _procedural_entity_refs(session.world_state)
                        - _procedural_entity_refs(
                            snapshot["save"].get("world_state", {})
                        )
                    ),
                }

            from api.model_phase import only_resolved_narration_failures

            if only_resolved_narration_failures(model_failures):
                _logger.warning(
                    "Resolved narration unavailable; deterministic fallback retained (phases=%s)",
                    [failure.phase for failure in model_failures],
                )
            elif model_failures:
                restore_turn_snapshot()
                _logger.warning(
                    "Ollama chat failed (error_type=%s)",
                    model_failures[0],
                )
                raise refuse_model_failure("ollama_unavailable") from None

            if len(model_calls) > MAX_MODEL_CALLS_PER_TURN:
                restore_turn_snapshot()
                _logger.error("Engine exceeded the per-turn model-call limit.")
                raise refuse_before_commit(500, "engine_error", "The game turn exceeded its model-call limit.") from None

            narration = result.get("narration") if isinstance(result, dict) else None
            if not isinstance(narration, str) or not narration.strip():
                restore_turn_snapshot()
                _logger.error("Engine returned an invalid turn result.")
                raise refuse_before_commit(500, "engine_error", "The game turn returned an invalid response.") from None

            action_result = (
                result.get("action_result")
                if isinstance(result, dict)
                else None
            )
            if (
                isinstance(action_result, dict)
                and action_result.get("status") == "infrastructure_failure"
            ):
                code = action_result.get("infrastructure_code")
                if code not in {
                    "model_unavailable",
                    "intent_json_invalid",
                    "intent_timeout",
                }:
                    code = "model_unavailable"
                restore_turn_snapshot()
                _logger.warning(
                    "Intent infrastructure failure (code=%s, rolled_back=true)",
                    code,
                )
                raise refuse_model_failure(code)
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
                        getattr(session, "campaign_lore_state", None) or lore_authority_snapshot,
                        engine_evidence,
                        action_result,
                        snapshot["save"].get("world_state", {}),
                        session.world_state,
                    )
                )
            except Exception as error:
                _rollback_session(record, session, snapshot)
                session.campaign_lore_state = lore_authority_snapshot
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = narrative_memory_snapshot
                record.lore_authority = lore_authority_snapshot
                _logger.error(
                    "Engine lore evidence failed validation (error_type=%s)",
                    type(error).__name__,
                )
                raise refuse_before_commit(500, "engine_error", "Campaign lore evidence could not be verified.") from None
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
                _rollback_session(record, session, snapshot)
                session.campaign_lore_state = lore_authority_snapshot
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = narrative_memory_snapshot
                record.lore_authority = lore_authority_snapshot
                _logger.error(
                    "Narrative continuity update failed (error_type=%s)",
                    type(error).__name__,
                )
                raise refuse_before_commit(500, "narrative_memory_error", "Campaign continuity could not be updated safely.") from None
            try:
                skill_check_result = serialize_skill_check_result(
                    action_result,
                    session,
                    **({"check_evidence": check_evidence} if request.check_feature is not None else {}),
                )
                combat_result = serialize_combat_result(action_result, session)
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
                state = serialize_session_state(
                    session,
                    record.journal,
                    staged_lore_authority,
                )
            except Exception as error:
                _rollback_session(record, session, snapshot)
                session.campaign_lore_state = lore_authority_snapshot
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = narrative_memory_snapshot
                record.lore_authority = lore_authority_snapshot
                if isinstance(error, SkillCheckResultSerializationError):
                    _logger.error(
                        "Engine returned an invalid skill-check result."
                    )
                    raise refuse_before_commit(500, "engine_error", "The skill-check result could not be verified safely.") from None
                if isinstance(error, CombatResultSerializationError):
                    _logger.error(
                        "Engine returned an invalid combat result or history entry."
                    )
                    raise refuse_before_commit(500, "engine_error", "The combat result could not be verified safely.") from None
                _logger.error(
                    "Campaign journal update failed (error_type=%s)",
                    type(error).__name__,
                )
                raise refuse_before_commit(500, "journal_error", "The campaign journal could not be updated safely.") from None
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
                level_up=(
                    LevelUpResult.model_validate(action_result["level_up"])
                    if isinstance(action_result, dict) and action_result.get("level_up") is not None
                    else None
                ),
                turn_outcome=_turn_outcome(action_result),
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
                _raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, response_payload, error,
                    adopt=lambda: manager.adopt_committed_turn(record, staged_narrative_memory, combat_history_entry),
                )
                record.lore_authority = lore_authority_snapshot
                _rollback_session(record, session, snapshot)
                session.campaign_lore_state = lore_authority_snapshot
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = narrative_memory_snapshot
                record.lore_authority = lore_authority_snapshot
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
                # A storage failure after a complete rollback is deliberately NOT closed. Closing it would be provably safe
                # (the refusal blocks a later receipt insert in its own transaction), but the product contract, pinned by
                # many tests, is "retry with the same id commits once" (receipt replay if it did). So the id stays
                # unresolved: the same id is the safe retry, a different UUID is blocked until then, and the player's
                # server-proven abandon is the explicit way out. Cost: a transient disk error blocks other ids meanwhile.
                decision = failure_policy.classify_failure(
                    failure_policy.ActionPhase.RESOLVED_UNCOMMITTED, "rolled_back", error,
                )
                if decision.code in ("campaign_stale", "campaign_storage_unavailable"):
                    raise HTTPException(status_code=decision.status_code, detail=decision.detail()) from None
                raise campaign_http_exception(error) from None
            except Exception as error:
                _raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, response_payload, error,
                    adopt=lambda: manager.adopt_committed_turn(record, staged_narrative_memory, combat_history_entry),
                )
                record.lore_authority = lore_authority_snapshot
                _rollback_session(record, session, snapshot)
                session.campaign_lore_state = lore_authority_snapshot
                session.world_metadata = metadata_snapshot
                record.journal = journal_snapshot
                record.narrative_memory = narrative_memory_snapshot
                record.lore_authority = lore_authority_snapshot
                _logger.error(
                    "Campaign autosave failed (error_type=%s)",
                    type(error).__name__,
                )
                # Same product rule as above (retry with the same id stays possible), so no never-applied claim here.
                decision = failure_policy.classify_failure(
                    failure_policy.ActionPhase.RESOLVED_UNCOMMITTED, "rolled_back", error,
                )
                raise HTTPException(status_code=decision.status_code, detail=decision.detail()) from None

            safety_code = (
                action_result.get("infrastructure_code")
                or action_result.get("status")
                if isinstance(action_result, dict)
                else "unavailable"
            )
            _logger.info(
                "Turn diagnostics (model_calls=%d, safety_code=%s, rolled_back=false)",
                len(model_calls),
                safety_code,
            )
            if getattr(adapter, "model_chain", None):
                _logger.info("Turn providers (answered=%s)", ",".join(model_calls))
            _logger.info(
                "Game turn completed (model=%s, model_calls=%d, narrative_scene=%s, narrative_tokens=%s, narrative_estimated_total=%s, narrative_budget=%s/%s, narrative_context_bytes=%s, narrative_selected=%s, narrative_ambiguities=%d)",
                adapter.model_name if adapter is not None else MODEL_NAME,
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
            if isinstance(session, game.GameSession):
                # LR00-P7: remember exactly how the world looked before this
                # turn, and how it looks now, so one explicit undo can restore
                # it only if nothing else has changed since.
                record.undo_checkpoint = {
                    "action_id": action_id,
                    "player_message": request.message,
                    "snapshot": snapshot,
                    "journal": journal_snapshot,
                    "narrative_memory": narrative_memory_snapshot,
                    "lore_authority": lore_authority_snapshot,
                    "world_metadata": metadata_snapshot,
                    "post_turn_fingerprint": _state_fingerprint(session),
                }
            return response_payload

    @application.post(
        "/api/game/sessions/{session_id}/undo",
        response_model=TurnUndoResponse,
    )
    @application.post(
        "/api/sessions/{session_id}/undo",
        response_model=TurnUndoResponse,
    )
    def undo_last_turn(session_id: str, request: TurnUndoRequest) -> dict[str, Any]:
        """Undo the last completed turn and its effects; keep it as history evidence."""
        record = get_record(session_id)
        action_id = str(request.action_id)
        target_action_id = str(request.target_action_id)
        request_hash = hashlib.sha256(json.dumps(
            {"undo": target_action_id}, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        with record.turn_lock:
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            # A request that queued behind a failing one must not run on a runtime that failure just quarantined (R05).
            ensure_usable(record)
            try:
                previous = manager.get_turn_action(record, action_id)
            except CampaignError as error:
                raise campaign_http_exception(error) from None
            if previous is not None:
                if previous["request_hash"] != request_hash:
                    raise HTTPException(status_code=409, detail={
                        "code": "action_id_conflict",
                        "message": "This action ID was already used for a different action.",
                    })
                return replay_action_response(previous["response"], TurnUndoResponse, session_id)
            require_current(record)
            session = record.game_session
            checkpoint = getattr(record, "undo_checkpoint", None)
            if not isinstance(checkpoint, dict) or checkpoint.get("action_id") != target_action_id:
                raise HTTPException(status_code=409, detail={
                    "code": "undo_unavailable",
                    "message": "Geri alınabilecek bir son tur yok.",
                })
            if _state_fingerprint(session) != checkpoint["post_turn_fingerprint"]:
                record.undo_checkpoint = None
                raise HTTPException(status_code=409, detail={
                    "code": "undo_stale",
                    "message": "Son turdan sonra başka bir değişiklik oldu; o tur artık geri alınamaz.",
                })
            current = _capture_session(session)
            current_metadata = copy.deepcopy(getattr(session, "world_metadata", None))
            current_journal = copy.deepcopy(record.journal)
            current_memory = copy.deepcopy(record.narrative_memory)
            current_lore = record.lore_authority
            payload = None
            try:
                _restore_session(session, checkpoint["snapshot"])
                session.world_metadata = copy.deepcopy(checkpoint["world_metadata"])
                record.journal = copy.deepcopy(checkpoint["journal"])
                record.narrative_memory = copy.deepcopy(checkpoint["narrative_memory"])
                record.lore_authority = checkpoint["lore_authority"]
                session.campaign_lore_state = checkpoint["lore_authority"]
                quoted = str(checkpoint.get("player_message") or "").strip()
                if len(quoted) > 120:
                    quoted = quoted[:117] + "..."
                narration = (
                    f"Son tur geri alındı: “{quoted}” ve sonuçları yaşanmamış sayılıyor. "
                    "Dünya o turdan önceki hâline döndü; sıradaki hamle senin."
                )
                state = serialize_session_state(session, record.journal, record.lore_authority)
                response = TurnUndoResponse(
                    session_id=session_id,
                    action_id=action_id,
                    undone_action_id=target_action_id,
                    narration=narration,
                    state=state,
                )
                payload = redact_sensitive_values(response.model_dump(mode="json"))
                manager.autosave_turn(
                    record,
                    "↶ Son turu geri al",
                    narration,
                    narrative_memory=record.narrative_memory,
                    turn_action_receipt={
                        "action_id": action_id,
                        "request_hash": request_hash,
                        "response": payload,
                    },
                )
            except CampaignError as error:
                _raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, payload, error,
                    adopt=lambda: setattr(record, "undo_checkpoint", None),
                )
                _rollback_session(record, session, current)
                session.world_metadata = current_metadata
                record.journal = current_journal
                record.narrative_memory = current_memory
                record.lore_authority = current_lore
                session.campaign_lore_state = current_lore
                raise campaign_http_exception(error) from None
            except Exception as error:
                _raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, payload, error,
                    adopt=lambda: setattr(record, "undo_checkpoint", None),
                )
                _rollback_session(record, session, current)
                session.world_metadata = current_metadata
                record.journal = current_journal
                record.narrative_memory = current_memory
                record.lore_authority = current_lore
                session.campaign_lore_state = current_lore
                raise
            # One step only: a second undo needs a new completed turn first.
            record.undo_checkpoint = None
            return payload

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
                _rollback_session(record, session, snapshot)
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
                if record.campaign_id is not None:
                    manager.save_campaign_locked(record)
                return redact_sensitive_values(response.model_dump())
            except CampaignError as error:
                _rollback_session(record, session, snapshot)
                raise campaign_http_exception(error) from None
            except Exception:
                _rollback_session(record, session, snapshot)
                raise

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
                result = session.resolve_species_trait_action(
                    request.action,
                    form=request.form,
                    ancestry=request.ancestry,
                    armed=request.armed,
                    **({"healing_amount": request.healing_amount, "remove_poisoned": request.remove_poisoned}
                       if request.action == "lay_on_hands" else {}),
                )
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
                manager.save_campaign_locked(record, turn_action_receipt={
                    "action_id": action_id, "request_hash": request_hash,
                    "response": {"action_id": action_id, "ambient_event_response": response_payload},
                }, turn_entry={
                    "player_message": transition["player_message"],
                    "narration": transition["narration"],
                })
                return response_payload
            except Exception as error:
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

    def level_up_projection(record: Any, session_id: str) -> dict[str, Any]:
        """Public earned eligibility only; core/save choices ahead of XP remain legal."""
        import character_progression as progression
        import xp
        from api.dnd_2024_rules import SPELLS_CATALOG
        session = record.game_session
        character = session.character
        token = getattr(session, "_campaign_persistence_version", None)
        import spell_scope
        cls = character.get("class")
        applied = character.get("progression_level", 1)
        ceiling = {"Sorcerer": 5, "Barbarian": 5, "Fighter": 5, "Monk": 5, "Paladin": 5, "Rogue": 5}.get(cls, 2)
        valid_applied = type(applied) is int and 1 <= applied <= ceiling
        target = min(applied + 1, ceiling) if valid_applied else ceiling
        result = dict(session_id=session_id, campaign_id=record.campaign_id,
                      revision=token[1] if isinstance(token, tuple) and len(token) == 2 else None,
                      status="blocked", reason=None, target_level=target,
                      class_name=cls, from_level=applied if valid_applied else None)
        if record.campaign_id is None:
            result["reason"] = "campaign_persistence_required"
        elif cls not in {"Sorcerer", "Barbarian", "Fighter", "Monk", "Paladin", "Rogue"}:
            result["reason"] = "selected_progression_not_supported"
        elif not valid_applied:
            result["reason"] = "previous_progression_state_invalid"
        elif applied == ceiling:
            result["reason"] = "target_not_above_applied_level"
        elif (type(character.get("xp")) is not int or character["xp"] < dict(xp.LEVEL_THRESHOLDS)[target]
              or type(character.get("level")) is not int or not target <= character["level"] <= xp.MAX_LEVEL):
            result["reason"] = "level_not_earned"
        else:
            try:
                progression.validate_saved(character, session.world_state)
                if cls == "Sorcerer":
                    state = session.world_state.get("spellcasting_v1")
                    if type(state) is not dict:
                        raise ValueError("Prior spell state required")
                    spell_scope.validate(state, character)
                    cap = progression.capacity(character)
                    if (len(state["cantrips"]) != cap["cantrips"] or len(state["prepared"]) != cap["prepared_spells"]
                            or character.get("cantrips") != state["cantrips"] or character.get("spells") != state["prepared"]):
                        raise ValueError("Prior complete spell choices required")
                    # The world counter is authoritative; independently bound the lagging mirror.
                    spell_scope.validate({**state, "slots": character.get("spell_slots_remaining")}, character)
            except (ValueError, KeyError, TypeError):
                result["reason"] = "previous_progression_state_invalid"
                return LevelUpPreviewResponse.model_validate(result).model_dump(mode="json")
            preview = progression.preview_level_up(session, target)
            result.update(status=preview["status"], reason=preview["reason"])
            if preview["status"] == "ready":
                result.update(choices_required=preview["choices_required"], capacity=preview["capacity"],
                              effects_pending=preview["effects_pending"], effects_supported=preview.get("effects_supported", []))
                if cls == "Sorcerer":
                    metadata = progression.sorcerer_starting_creation_options()
                    if not metadata:
                        result.update(status="blocked", reason="progression_options_unavailable")
                    else:
                        options = metadata[f"level_{target}"]
                        result.update(
                            supported_asi_choices=preview.get("supported_asi_choices", []),
                            cantrip_ids=[s["id"] for s in SPELLS_CATALOG["Sorcerer"]["cantrips"] if target == 4 and s["id"] not in state["cantrips"]],
                            prepared_spell_ids=[identity for identity in options["prepared_spell_ids"] if identity not in state["prepared"]],
                            metamagic_options=[identity for identity in options.get("metamagic_options", []) if identity not in character.get("metamagic", [])],
                            subclass_options=options.get("subclass_options", []),
                        )
                else:
                    result["effects_supported"] = preview.get("effects_supported", [])
                    if target == 4:
                        result["supported_asi_choices"] = preview.get("supported_asi_choices", [])
                    if target == 3:
                        result["subclass_options"] = preview.get("subclass_options", [])
                        if cls == "Barbarian":
                            result["primal_knowledge_skill_options"] = preview.get("primal_knowledge_skill_options", [])
                    if cls == "Paladin":
                        result["prepared_spell_ids"] = preview.get("prepared_spell_ids", [])
                        if target == 2:
                            result.update(fighting_style_options=preview.get("fighting_style_options"), cantrip_ids=preview.get("blessed_warrior_cantrip_ids", []))
        return LevelUpPreviewResponse.model_validate(result).model_dump(mode="json")

    @application.get("/api/game/sessions/{session_id}/level-up", response_model=LevelUpPreviewResponse,
                     operation_id="getGameSessionLevelUp")
    @application.get("/api/sessions/{session_id}/level-up", response_model=LevelUpPreviewResponse,
                     include_in_schema=False)
    def preview_earned_level_up(session_id: str) -> dict[str, Any]:
        record = get_record(session_id)
        with record.turn_lock:
            record = get_record(session_id)
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            require_current(record)
            return level_up_projection(record, session_id)

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
            try:
                durable = manager.record_refused_action(record, action_id, request_hash, status_code, detail)
            except Exception:
                durable = False
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
                                         BarbarianLevel4Choices, LevelUpChoices, LevelUpFiveChoices, PaladinLevel4Choices, PaladinLevel5Choices)
                expected_choices = {
                    3: {"Barbarian": BarbarianLevel3Choices, "Fighter": FighterLevel3Choices, "Monk": MonkLevel3Choices, "Paladin": PaladinLevel3Choices, "Rogue": RogueLevel3Choices, "Sorcerer": SorcererLevel3Choices},
                    4: {"Barbarian": BarbarianLevel4Choices, "Fighter": BarbarianLevel4Choices, "Monk": BarbarianLevel4Choices, "Paladin": PaladinLevel4Choices, "Rogue": BarbarianLevel4Choices, "Sorcerer": LevelUpChoices},
                    # Barbarian 5 has no choices: the same empty strict object as Barbarian 2 (no new schema).
                    5: {"Barbarian": BarbarianLevel2Choices, "Fighter": BarbarianLevel2Choices, "Monk": BarbarianLevel2Choices, "Paladin": PaladinLevel5Choices, "Rogue": BarbarianLevel2Choices, "Sorcerer": LevelUpFiveChoices},
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

    return application


def _suggestion_principal() -> Principal:
    principal = current_principal()
    if type(principal) is not Principal:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "authentication_required",
                "message": "Kimlik doğrulaması gerekli.",
            },
        )
    return principal


_PUBLIC_API_PATHS = frozenset({
    "/api/health",
    "/api/game/health",
    "/api/character-options",
    "/api/game/character-options",
    "/api/character-creation-catalog",
    "/api/game/character-creation-catalog",
    "/api/campaign-start-options",
    "/api/game/campaign-start-options",
    "/api/logout",
    "/api/game/logout",
})


app = None if os.environ.get("AI_DND_DISABLE_DEFAULT_APP") == "1" else create_app()
