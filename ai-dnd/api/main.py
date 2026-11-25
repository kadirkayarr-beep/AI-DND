"""HTTP adapter that delegates every game turn to the frozen Python engine."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import logging
import os
import sys

import front_proposal
import game
import refusals
from dataclasses import replace
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from api import action_contract, failure_policy, runtime_recovery
from api.auth import (
    AuthenticationError,
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
    apply_campaign_override,
    apply_committed_world_canon,
    is_setting_place,
)
from api.ollama_adapter import (
    AuthenticatedOllamaAdapter,
    MODEL_NAME,
    OllamaUnavailableError,
    RequiredModelUnavailableError,
    canonical_world_metadata_context,
    turn_call_cap,
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
    SaveLanded,
)
from api.local_play import LocalPlayAuthenticator
from api.persistence.campaign_store import CampaignStore, StartupCampaignStore
from api.routes_catalog import register_catalog_routes
from api.routes_economic import economic_step
from api.routes_quests import register_quest_routes
from api.routes_species import register_species_routes
from api.routes_spells_write import register_spell_prepare_routes
from api.routes_level_up_apply import register_level_up_apply_routes
from api.routes_level_up import register_level_up_read_routes
from api.routes_spells_read import register_spell_read_routes
from api.routes_undo import register_undo_routes
from api.schemas import (
    AmbientEventActionRequest,
    AmbientEventCommandResult,
    AmbientEventResult,
    CampaignCreateRequest,
    CampaignDetailResponse,
    CampaignSessionResponse,
    CampaignSummary,
    HealthResponse,
    LevelUpResult,
    SessionResponse,
    TurnOutcome,
    TurnRequest,
    TurnResponse,
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
from api.schemas import ActionIdPath
from api.session_manager import SessionManager, TransientReplyDroppedError, UnknownSessionError
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
# The economic_action field (S1a) is owned by the card path (A3), and every turn coin writer now goes through the one
# economic owner (A4), so the gate is open. Closed, a request carrying it is refused before any intent, lock or turn.
ECONOMIC_ACTIONS_ENABLED = True


def _capture_session(session: Any) -> dict[str, Any]:
    return {
        "save": copy.deepcopy(session.serialize_game_state()),
        "runtime": session._capture_runtime_snapshot(),
    }


def _restore_session(session: Any, snapshot: dict[str, Any]) -> None:
    session._restore_runtime_snapshot(snapshot["runtime"])


def _store_refusal(
    manager: Any, record: Any, action_id: str, request_hash: str, status_code: int, detail: dict[str, Any],
    what: str = "Refusal record",
) -> bool:
    """True only when the refusal is durably stored; a failed store is logged and makes no never-applied claim."""
    try:
        return manager.record_refused_action(record, action_id, request_hash, status_code, detail)
    except Exception:
        _logger.error(f"{what} could not be saved; no never-applied claim is made.", exc_info=True)
        return False


def _commit_already_durable(
    manager: Any, record: Any, action_id: str, request_hash: str, response_payload: dict[str, Any],
) -> SaveLanded:
    """After a failed autosave: LANDED only if THIS action's receipt is durably stored with this exact result.

    A lost commit acknowledgement leaves the database on the new revision. Rolling the live runtime back then would
    split memory from storage, so the runtime stays on the committed state and the caller answers "unconfirmed",
    never success and never "not applied". If the lookup itself fails the answer is UNKNOWN: the caller must not
    guess in either direction.
    """
    try:
        stored = manager.get_turn_action(record, action_id)
    except CampaignError:
        return SaveLanded.UNKNOWN
    except Exception:
        _logger.error("Could not read back the action receipt after a failed save; answering unknown.", exc_info=True)
        return SaveLanded.UNKNOWN
    landed = stored is not None and stored["request_hash"] == request_hash and (
        action_contract.result_digest(stored["response"]) == action_contract.result_digest(response_payload))
    return SaveLanded.LANDED if landed else SaveLanded.NOT_LANDED


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
    if durable is SaveLanded.UNKNOWN:
        # Neither "committed" nor "rolled back" can be claimed, and rolling the runtime back could split it from storage.
        # The safe stance is the quarantine: the session closes, durable truth is what a restart resumes (R05/R06).
        record.usable = False
        _logger.critical("Campaign autosave failed and its receipt could not be reconciled; session closed")
        decision = failure_policy.classify_failure(failure_policy.ActionPhase.RECONCILIATION, "unknown", error)
        raise HTTPException(status_code=decision.status_code, detail=decision.detail(commit_status="outcome_unknown")) from None
    if durable is SaveLanded.NOT_LANDED:
        return
    if adopt is not None:
        adopt()
    _logger.error("Campaign autosave committed but was not acknowledged (error_type=%s)", type(error).__name__)
    decision = failure_policy.classify_failure(failure_policy.ActionPhase.COMMIT_UNKNOWN, "unknown", error)
    raise HTTPException(
        status_code=decision.status_code,
        detail=decision.detail(commit_status="committed_unconfirmed"),
    ) from None


def _adopt_undo_checkpoint(record: Any, build: Any) -> None:
    """D-110: after a commit whose acknowledgement was lost, the committed move is the live one-step undo target.

    Built as on the success path. If it cannot be built the move is simply not undoable (as on the ambient route, D-103);
    the older point is dropped either way, because it no longer describes the live state.
    """
    try:
        record.undo_checkpoint = build()
    except Exception as error:
        record.undo_checkpoint = None
        _logger.error("Undo point after an unacknowledged commit could not be built (error_type=%s)", type(error).__name__)


def _final_death(session: Any) -> bool:
    """D-112: an Ironman death is final; no undo may bring the hero back, whichever turn set the undo point.

    D-178 (Kadir): "PERMADEATH'te ölüm kesin; ölüm turu Geri Al ile geri alınamaz." The same holds for a real death.
    """
    world = getattr(session, "world_state", None)
    death = world.get("death_state") if isinstance(world, dict) else None
    return isinstance(death, dict) and (
        death.get("terminal") is True
        or (death.get("mode") in ("IRONMAN", "PERMADEATH") and death.get("dead") is True)
    )


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


def _put_back_turn(record: Any, session: Any, snapshot: dict[str, Any], lore: Any, metadata: Any, journal: Any,
                   memory: Any) -> None:
    """A play-turn refusal before commit: the verified session rollback, then every turn-owned field, in this order."""
    _rollback_session(record, session, snapshot)
    session.campaign_lore_state = lore
    session.world_metadata = metadata
    record.journal = journal
    record.narrative_memory = memory
    record.lore_authority = lore


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
        reason=short(action_result.get("reason"), 48)
        if action_result.get("action") in {"equipment_transaction", "shop_offer"} else None,
        healing=action_result.get("healing") if action_result.get("action") == "narrative" else None,
        heal_source=action_result.get("heal_source") if action_result.get("action") == "narrative" else None,
    )


def _state_fingerprint(session: Any) -> str:
    # C11: the stored cards are left out, so preparing, cancelling or a confirm that consumed nothing never makes
    # the last turn's undo stale. The public projections (economic_offer, wallet) are not in the save at all.
    saved = copy.deepcopy(session.serialize_game_state())
    flags = (saved.get("world_state") or {}).get("flags") if isinstance(saved, dict) else None
    if isinstance(flags, dict):
        flags.pop("economic_offers", None)
    return hashlib.sha256(json.dumps(
        saved, sort_keys=True, ensure_ascii=False, default=str,
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
        # Only an adapter built from the environment warms the local model (in the background, once).
        warm_up = getattr(adapter, "warm_up_in_background", None)
        if callable(warm_up):
            warm_up()
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

    def refuse_while_action_open(record: Any) -> None:
        # D-107: the turn and level-up routes refuse a new action while another is open; every other game write
        # must too, so an open move retried later never runs on a world changed after it was accepted. Called under
        # turn_lock, after receipt replay and before any engine work. Nothing is stored: a retry runs once it is settled.
        try:
            open_action = manager.unresolved_action(record)
        except CampaignError as error:
            raise campaign_http_exception(error) from None
        if open_action is not None:
            raise HTTPException(status_code=409, detail={
                "code": "unresolved_action",
                "message": "An earlier action of this campaign is still unresolved.",
                "unresolved_action_id": open_action["action_id"],
            })

    @application.get("/api/game/health", response_model=HealthResponse, response_model_exclude_none=True)
    @application.get("/api/health", response_model=HealthResponse, response_model_exclude_none=True)
    def health(response: Response) -> HealthResponse:
        response.headers["X-AI-DND-Instance"] = str(os.getpid())
        spend_warning = getattr(adapter, "spend_warning", None)
        return HealthResponse(
            model=adapter.model_name if adapter is not None else MODEL_NAME,
            model_chain=getattr(adapter, "model_chain", None),
            spend_warning=spend_warning() if callable(spend_warning) else None,
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

    register_catalog_routes(application)

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
            try:
                receipt = manager.get_turn_action(record, action_id) or {}
            except TransientReplyDroppedError:
                receipt = {}  # D-152: applied long ago, its reply no longer kept; only a retried turn is refused
            stored = receipt.get("response")
            payload["response"] = None
            # D-162: an Undo receipt also fits TurnResponse (extra keys are ignored), but it is another command kind.
            if isinstance(stored, dict) and "undone_action_id" not in stored:
                try:
                    payload["response"] = replay_action_response(stored, TurnResponse, session_id)
                except HTTPException:
                    payload["response"] = None  # a receipt of another command kind: applied, but not a turn reply
            # D-110: whether this move is still the live one-step undo target, so a screen that lost the reply keeps
            # its undo. A hint only: the undo route checks the checkpoint and its fingerprint again under the lock.
            checkpoint = getattr(record, "undo_checkpoint", None)
            payload["undo_available"] = (
                isinstance(checkpoint, dict) and checkpoint.get("action_id") == action_id
                and not _final_death(record.game_session)
            )
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
    def read_action_status(session_id: str, action_id: ActionIdPath) -> dict[str, Any]:
        action_id = str(action_id)
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
    def abandon_action(session_id: str, action_id: ActionIdPath) -> dict[str, Any]:
        """Player-initiated close of an action id; the answer comes from the stored receipt or refusal only."""
        action_id = str(action_id)
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
        if request.economic_action is not None and not ECONOMIC_ACTIONS_ENABLED:
            raise HTTPException(status_code=409, detail={
                "code": "economic_actions_disabled",
                "message": "Economic actions are not open yet; nothing was applied.",
            })
        active_adapter = application.state.ollama_adapter
        action_id = str(request.action_id)
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
        if request.economic_action is not None:
            hash_payload["economic_action"] = request.economic_action.model_dump(mode="json")
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
                durable = _store_refusal(manager, record, action_id, request_hash, 409, detail)
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

            # D-119: the opening step the attack check assumed; a refusal before the turn's snapshot takes it back.
            opening: dict[str, Any] | None = None

            def take_back_opening() -> None:
                if opening is not None:
                    opening.pop("distance_ft", None)

            def refuse_before_commit(status_code: int, code: str, message: str) -> HTTPException:
                """Close this action id for good after a refusal raised before any effect.

                The not_applied claim is made only when the refusal record is durably stored under the turn
                lock; otherwise the same refusal is returned without that claim.
                """
                take_back_opening()
                detail = {"code": code, "message": message, "not_applied": True}
                public_message = refusals.REFUSAL_TEXT.get(code) if status_code == 400 or code == "engine_error" else None
                if public_message:
                    detail["public_message"] = refusals.text_for(code)  # the player's Turkish line; `message` stays
                durable = _store_refusal(manager, record, action_id, request_hash, status_code, detail)
                if not durable:
                    detail = {"code": code, "message": message}
                    if public_message:
                        detail["public_message"] = refusals.text_for(code)
                return HTTPException(status_code=status_code, detail=detail)

            def refuse_model_failure(code: str, message: str = MODEL_FAILURE_MESSAGE) -> HTTPException:
                """Answer a model failure on a turn that applied nothing, and let the campaign go on.

                The failure says nothing about the campaign, so it does not hold later moves: any new id runs. The browser
                closes its move on not_applied and retries with a new id, so this id is closed for good (D-106): a late
                copy replays this refusal instead of running a second turn. The not_applied claim needs a verified
                rollback and a durable refusal record.
                """
                take_back_opening()
                detail = {"code": code, "message": message, "not_applied": True}
                durable = getattr(record, "usable", True) and _store_refusal(
                    manager, record, action_id, request_hash, 503, detail, what="Model-failure refusal",
                )
                if not durable:
                    detail = {"code": code, "message": message}
                return HTTPException(status_code=503, detail=detail)

            try:
                manager.assert_current(record)
            except CampaignError as error:
                # An intent that was claimed earlier stays open (it may be running in another session); only the same
                # id with the same payload, or the player's server-proven abandon, closes it.
                raise campaign_http_exception(error) from None
            if request.economic_action is not None:
                # The card's own path: no free-text turn, no model, one commit with this action's receipt.
                return economic_step(record, session, session_id, request, action_id, request_hash,
                                     refuse_before_commit, manager=manager, api_main=sys.modules[__name__])
            if isinstance(session, game.GameSession):
                try:
                    opening = combat_lifecycle.validate_request(
                        session,
                        request.message if effective_mode in {None, "do"} else "",
                        request.target_id if effective_mode in {None, "do"} else None,
                        combat_id=request.combat_id,
                        combat_round=request.combat_round, combat_turn_index=request.combat_turn_index,
                    )
                except combat_lifecycle.CombatRequestError as error:
                    # Walking off mid-fight is a plain line: the turn answers it in the fight.
                    if error.code != "combat_travel" or request.combat_action is not None:
                        raise refuse_before_commit(error.status_code, error.code, str(error)) from None
                except ValueError:
                    raise refuse_before_commit(409, "invalid_combat_state", "Combat state is invalid.") from None
            # D-256: anything unexpected before the snapshot takes the opening step back too (a refusal already did).
            try:
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
                             or exploration.native_request(request.message, session)
                             or combat_lifecycle.surrender_yes(session, request.message))
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
            except BaseException:
                take_back_opening()
                raise

            # D-119: the snapshot is the state before the opening step, so every rollback takes the step back too.
            take_back_opening()
            snapshot = _capture_session(session)
            if opening is not None:
                opening["distance_ft"] = 5
                opening = None
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
                calls_before_turn: list[str] = []
                if (
                    isinstance(session, game.GameSession) and front_proposal.enabled()
                    and not slot_conversion and request.combat_action is None
                    and request.check_feature is None
                ):
                    # The reading stands before the planner and counts against this turn's cap.
                    with active_adapter.capture_model_calls() as calls_before_turn, \
                            active_adapter.capture_model_failures() as reading_failures:
                        session.front_read_ahead(
                            narrative_player_message,
                            target_id=effective_target_id,
                            interaction_mode=effective_mode,
                        )
                    if reading_failures:
                        # Owner rule G6 ("Tekrar dene"): a provider outage during the reading spends no line.
                        restore_turn_snapshot()
                        _logger.warning("Front reading failed (error_type=%s)", reading_failures[0])
                        raise refuse_model_failure("ollama_unavailable") from None
                # Exact resource-only conversion has no scene/reference authority.
                # Its display label or a retained UI target must not focus an NPC,
                # materialize a place, or alter an existing conversation first.
                # The planner's own entry (an inn walked into by name) may tell its arrival with a model call:
                # it is counted in the same window as the front reading, so the turn's cap holds.
                with active_adapter.capture_model_calls() as planner_calls:
                    planner_calls.extend(calls_before_turn)
                    scene_plan = None if slot_conversion else session.plan_living_world_turn(
                        narrative_player_message,
                        **plan_kwargs,
                    )
                calls_before_turn = planner_calls
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
                                model_calls.extend(calls_before_turn)
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
                                    except combat_lifecycle.CombatRequestError as error:
                                        if (request.combat_action is not None or effective_mode not in {None, "do"}
                                                or request.message.lstrip().startswith("/")
                                                or not session.world_state.get("combat", {}).get("active")):
                                            raise  # typed commands and door rules keep their typed refusal
                                        restore_turn_snapshot()
                                        result = session.combat_refusal_turn(error)
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
                if isinstance(session, game.GameSession):
                    # The reading ahead of the turn may have failed before the turn could clear its own coin fields,
                    # or before the turn could close the reading itself; a later turn must not pick either up.
                    game._clear_turn_transients(session)
                    front_proposal.end(session)

            engine_evidence = (
                result.pop("_engine_event_evidence", None)
                if isinstance(result, dict)
                else None
            )
            # Who wrote this turn's narration, as the engine reported it; saved beside the history row. A turn
            # the engine reports nothing for stays unrecorded (None): nothing is guessed here.
            engine_telemetry = engine_evidence.get("telemetry") if isinstance(engine_evidence, dict) else None
            narration_source = engine_telemetry.get("narration_source") if isinstance(engine_telemetry, dict) else None
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

            if len(model_calls) > turn_call_cap(model_calls):
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
                _put_back_turn(record, session, snapshot, lore_authority_snapshot, metadata_snapshot,
                               journal_snapshot, narrative_memory_snapshot)
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
                _put_back_turn(record, session, snapshot, lore_authority_snapshot, metadata_snapshot,
                               journal_snapshot, narrative_memory_snapshot)
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
                _put_back_turn(record, session, snapshot, lore_authority_snapshot, metadata_snapshot,
                               journal_snapshot, narrative_memory_snapshot)
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
            try:
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
            except Exception as error:
                # Nothing is saved yet: the answer could not be built, so the turn is put back whole (B1).
                _put_back_turn(record, session, snapshot, lore_authority_snapshot, metadata_snapshot,
                               journal_snapshot, narrative_memory_snapshot)
                _logger.error("Turn response could not be built (error_type=%s)", type(error).__name__)
                raise refuse_before_commit(500, "engine_error", "The turn response could not be built safely.") from None
            record.lore_authority = staged_lore_authority

            def undo_point() -> dict[str, Any]:
                return {
                    "action_id": action_id,
                    "player_message": request.message,
                    "snapshot": snapshot,
                    "journal": journal_snapshot,
                    "narrative_memory": narrative_memory_snapshot,
                    "lore_authority": lore_authority_snapshot,
                    "world_metadata": metadata_snapshot,
                    "post_turn_fingerprint": _state_fingerprint(session),
                }

            def adopt_committed_turn() -> None:
                manager.adopt_committed_turn(record, staged_narrative_memory, combat_history_entry)
                if isinstance(session, game.GameSession):  # D-110: the committed turn keeps its one-step undo
                    _adopt_undo_checkpoint(record, undo_point)

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
                    narration_source=narration_source,
                )
            except CampaignError as error:
                _raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, response_payload, error,
                    adopt=adopt_committed_turn,
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
                    adopt=adopt_committed_turn,
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
                record.undo_checkpoint = undo_point()
            return response_payload

    register_undo_routes(
        application,
        get_record=get_record,
        ensure_usable=ensure_usable,
        manager=manager,
        campaign_http_exception=campaign_http_exception,
        replay_action_response=replay_action_response,
        refuse_while_action_open=refuse_while_action_open,
        require_current=require_current,
        api_main=sys.modules[__name__],
    )

    register_quest_routes(
        application,
        get_record=get_record,
        require_current=require_current,
        refuse_while_action_open=refuse_while_action_open,
        campaign_http_exception=campaign_http_exception,
        manager=manager,
        _capture_session=_capture_session,
        _rollback_session=_rollback_session,
        _logger=_logger,
    )

    register_species_routes(
        application,
        get_record=get_record,
        require_current=require_current,
        ensure_usable=ensure_usable,
        refuse_while_action_open=refuse_while_action_open,
        replay_action_response=replay_action_response,
        campaign_http_exception=campaign_http_exception,
        manager=manager,
        _capture_session=_capture_session,
        _rollback_session=_rollback_session,
        _raise_if_commit_unconfirmed=_raise_if_commit_unconfirmed,
    )

    register_spell_read_routes(application, get_record=get_record, require_current=require_current)

    register_spell_prepare_routes(
        application,
        get_record=get_record,
        require_current=require_current,
        ensure_usable=ensure_usable,
        refuse_while_action_open=refuse_while_action_open,
        replay_action_response=replay_action_response,
        campaign_http_exception=campaign_http_exception,
        manager=manager,
        _capture_session=_capture_session,
        _rollback_session=_rollback_session,
        _raise_if_commit_unconfirmed=_raise_if_commit_unconfirmed,
    )

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
                message: str | None = None,
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
                        message=message,
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
            refuse_while_action_open(record)

            snapshot = _capture_session(session)
            journal_snapshot = copy.deepcopy(record.journal)
            memory_snapshot = copy.deepcopy(record.narrative_memory)
            metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
            lore_snapshot = record.lore_authority
            token_before = getattr(session, "_campaign_persistence_version", None)

            def put_back() -> None:
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

            def refuse_unsaved(error: Exception) -> None:
                put_back()
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
                        # The panel's line for a refused click; nothing changed, so the last turn's undo stands.
                        message=refusals.text_for(transition.get("reason_code"))
                        if status == "REJECTED" else None,
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
                turn_entry = {
                    "player_message": transition["player_message"],
                    "narration": transition["narration"],
                    "narration_source": "deterministic_system",  # ambient_actions builds this line itself
                }
            except Exception as error:
                refuse_unsaved(error)
            try:
                manager.save_campaign_locked(record, turn_action_receipt={
                    "action_id": action_id, "request_hash": request_hash,
                    "response": {"action_id": action_id, "ambient_event_response": response_payload},
                }, turn_entry=turn_entry)
            except Exception as error:
                # D-103: as in the quest route, a save that raised may still have committed. Rolling back under a
                # stored receipt and history row would split the live game from storage, so ask storage first.
                certain = isinstance(error, (CampaignStaleError, CampaignNotFoundError, CampaignNotActiveError))
                landed = SaveLanded.NOT_LANDED if certain else manager.campaign_save_landed(record, token_before)
                if landed is SaveLanded.UNKNOWN:
                    record.usable = False
                    _logger.critical("Ambient-event save failed and could not be reconciled; session closed")
                    decision = failure_policy.classify_failure(
                        failure_policy.ActionPhase.RECONCILIATION, "unknown", error,
                    )
                    raise HTTPException(
                        status_code=decision.status_code, detail=decision.detail(commit_status="outcome_unknown"),
                    ) from None
                if landed is SaveLanded.NOT_LANDED:
                    refuse_unsaved(error)
                _logger.error(
                    "Ambient-event save committed but was not acknowledged (error_type=%s)", type(error).__name__,
                )
            # D-103: everything below runs after the commit and never rolls the live game back. If the checkpoint
            # cannot be built the click is simply not undoable; a retry with this id replays the stored receipt.
            # V5: a joined event is undone like a typed turn, with the same fields as the turn route.
            _adopt_undo_checkpoint(record, lambda: {
                "action_id": action_id,
                "player_message": transition["player_message"],
                "snapshot": snapshot,
                "journal": journal_snapshot,
                "narrative_memory": memory_snapshot,
                "lore_authority": lore_snapshot,
                "world_metadata": metadata_snapshot,
                "post_turn_fingerprint": _state_fingerprint(session),
            })
            return response_payload

    register_level_up_read_routes(application, get_record=get_record, require_current=require_current)

    register_level_up_apply_routes(
        application,
        get_record=get_record,
        require_current=require_current,
        ensure_usable=ensure_usable,
        refuse_while_action_open=refuse_while_action_open,
        replay_action_response=replay_action_response,
        campaign_http_exception=campaign_http_exception,
        manager=manager,
        _capture_session=_capture_session,
        _rollback_session=_rollback_session,
        _raise_if_commit_unconfirmed=_raise_if_commit_unconfirmed,
        _store_refusal=_store_refusal,
    )

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
