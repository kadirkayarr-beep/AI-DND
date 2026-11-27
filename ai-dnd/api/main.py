"""HTTP adapter that delegates every game turn to the frozen Python engine."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import sys

import game
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from api import action_contract, failure_policy, runtime_recovery
from api.auth import (
    AuthenticationError,
    FixedAuthenticator,
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
from api.campaign_errors import campaign_http_exception
import campaign_time
import combat_lifecycle  # noqa: F401 - kept for tests that patch api.main.combat_lifecycle.<attr>
import scheduled_events
import adventure.projection as adventure_projection
from api.clerk_auth import ClerkAuthenticator
from api.campaign_journal import (
    append_ambient_event_outcome,  # noqa: F401 - api.routes_ambient reads it here at call time
    update_campaign_journal,  # noqa: F401 - api.routes_ambient and api.routes_turn read it here at call time
)
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
    PRODUCTION_REGISTRY,
    apply_campaign_override,
    apply_committed_world_canon,
    is_setting_place,
)
from api.ollama_adapter import (
    AuthenticatedOllamaAdapter,
    MODEL_NAME,
    canonical_world_metadata_context,  # noqa: F401 - api.routes_turn reads it here at call time
    turn_call_cap,  # noqa: F401 - api.routes_turn reads it here at call time
)
from api.lore_authority.campaign_state import CANONICAL_LOCATION_TYPES
from api.narrative_director import (
    install_narrative_context_adapter,
    narrative_turn_context,  # noqa: F401 - api.routes_turn reads it here at call time
)
from api.narrative_memory import update_narrative_memory  # noqa: F401 - api.routes_turn reads it here at call time
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignError,
    CampaignStaleError,
    SaveLanded,
)
from api.local_play import LocalPlayAuthenticator
from api.persistence.campaign_store import StartupCampaignStore
from api.routes_ambient import register_ambient_routes
from api.routes_campaigns import register_campaign_routes
from api.routes_catalog import register_catalog_routes
from api.routes_economic import economic_step  # noqa: F401 - api.routes_turn reads it here at call time
from api.routes_quests import register_quest_routes
from api.routes_species import register_species_routes
from api.routes_spells_write import register_spell_prepare_routes
from api.routes_level_up_apply import register_level_up_apply_routes
from api.routes_level_up import level_up_projection, register_level_up_read_routes
from api.routes_spells_read import register_spell_read_routes
from api.routes_turn import register_turn_routes
from api.routes_undo import register_undo_routes
from api.schemas import (
    HealthResponse,
    TurnOutcome,
    TurnResponse,
)
from api.serializers import (
    redact_sensitive_values,
    serialize_combat_result,  # noqa: F401 - api.routes_turn reads it here at call time
    serialize_combat_history_entry,  # noqa: F401 - api.routes_turn reads it here at call time
    serialize_skill_check_result,  # noqa: F401 - api.routes_turn reads it here at call time
    serialize_session_state,
)
from api.schemas import ActionIdPath
from api.session_manager import SessionManager, TransientReplyDroppedError, UnknownSessionError
from api.world_metadata import (
    set_session_world_metadata,  # noqa: F401 - api.routes_turn reads it here at call time
    world_metadata_for_state,  # noqa: F401 - api.routes_ambient and api.routes_turn read it here at call time
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

    if authenticator is _UNSET:
        authenticator = select_authenticator(os.environ)
    # D-314: anything but local play, the fixed test authenticator and none (OIDC, Clerk, fail-closed) has no docs routes.
    hosted = authenticator is not None and type(authenticator) not in (LocalPlayAuthenticator, FixedAuthenticator)
    docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if hosted else {}
    application = FastAPI(
        title="AI-DND API",
        version="1.0.0",
        description="Thin HTTP adapter for the canonical Python AI-DND engine.",
        **docs,
    )
    application.state.session_manager = manager
    application.state.authenticator = authenticator
    application.state.ollama_adapter = adapter
    cloud_chain = getattr(adapter, "cloud_chain", None)
    application.state.identity_suggestions = identity_suggestions or IdentitySuggestionService(
        chain_provider(cloud_chain) if cloud_chain else None
    )

    @application.middleware("http")
    async def require_verified_principal(request: Any, call_next: Any) -> Any:
        # D-313: a body over the limit is refused by its declared length, unread.
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
            return JSONResponse(status_code=413, content={"detail": {
                "code": "request_too_large",
                "message": "The request body is too large.",
            }})
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
        model = adapter.model_name if adapter is not None else MODEL_NAME
        if hosted:  # D-314: no model chain, spend warning or process id for the public
            return HealthResponse(model=model)
        response.headers["X-AI-DND-Instance"] = str(os.getpid())
        spend_warning = getattr(adapter, "spend_warning", None)
        return HealthResponse(
            model=model,
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

    register_campaign_routes(
        application,
        manager=manager,
        campaign_http_exception=campaign_http_exception,
        api_main=sys.modules[__name__],
    )

    @application.get(
        "/api/game/sessions/{session_id}/state",
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

    register_turn_routes(
        application,
        get_record=get_record,
        ensure_usable=ensure_usable,
        manager=manager,
        campaign_http_exception=campaign_http_exception,
        replay_action_response=replay_action_response,
        adapter=adapter,
        api_main=sys.modules[__name__],
    )

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

    register_ambient_routes(
        application,
        get_record=get_record,
        require_current=require_current,
        refuse_while_action_open=refuse_while_action_open,
        campaign_http_exception=campaign_http_exception,
        action_archived_error=action_archived_error,
        manager=manager,
        api_main=sys.modules[__name__],
    )

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
        level_up_projection=level_up_projection,
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


MAX_REQUEST_BYTES = 256 * 1024

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
