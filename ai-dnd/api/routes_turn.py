"""The play-turn route, moved out of api.main.create_app (D-531 stage 4): same paths, lock, order, receipts and bodies.

`play_turn` owns the turn lock and every handler whose reach spans more than one step; the steps below run inside
it in the old order and share the old locals through one `TurnRun`. Every helper, function or constant that api.main
defines or imports from an api module is read through the passed `api_main` module at call time, as the closure did,
so a patch on api.main still reaches the turn.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException

import combat_lifecycle
import front_proposal
import game
import living_world
import refusals
from api import failure_policy
from api.lore_authority import CampaignLoreState
from api.ollama_adapter import OllamaUnavailableError, RequiredModelUnavailableError
from api.persistence.campaign_models import CampaignError, CampaignStaleError
from api.persistence.campaign_store import CampaignStore
from api.schemas import LevelUpResult, TurnRequest, TurnResponse
from api.serializers import CombatResultSerializationError, SkillCheckResultSerializationError


@dataclass
class TurnRun:
    """The locals one /turn request shares between its steps (they were play_turn's closure locals)."""

    main: Any
    manager: Any
    record: Any
    session: Any
    session_id: str
    request: TurnRequest
    action_id: str
    request_hash: str
    effective_mode: str | None
    active_adapter: Any
    # D-119: the opening step the attack check assumed; a refusal before the turn's snapshot takes it back.
    opening: dict[str, Any] | None = None
    check_evidence: list[Any] | None = None
    slot_conversion: Any = False
    snapshot: dict[str, Any] = field(default_factory=dict)
    metadata_snapshot: Any = None
    journal_snapshot: Any = None
    narrative_memory_snapshot: Any = None
    lore_authority_snapshot: Any = None
    narrative_player_message: Any = None
    effective_target_id: Any = None
    scene_plan: Any = None
    calls_before_turn: list[Any] = field(default_factory=list)
    narrative_frame: Any = None
    model_calls: list[Any] = field(default_factory=list)
    model_failures: list[Any] = field(default_factory=list)
    result: Any = None
    engine_evidence: Any = None
    narration_source: Any = None
    narration: Any = None
    action_result: Any = None
    death_rolled_back: bool = False
    staged_lore_authority: Any = None
    staged_narrative_memory: Any = None
    combat_history_entry: Any = None
    response_payload: Any = None

    def take_back_opening(self) -> None:
        if self.opening is not None:
            self.opening.pop("distance_ft", None)

    def refuse_before_commit(self, status_code: int, code: str, message: str) -> HTTPException:
        """Close this action id for good after a refusal raised before any effect.

        The not_applied claim is made only when the refusal record is durably stored under the turn
        lock; otherwise the same refusal is returned without that claim.
        """
        self.take_back_opening()
        detail = {"code": code, "message": message, "not_applied": True}
        public_message = refusals.REFUSAL_TEXT.get(code) if status_code == 400 or code == "engine_error" else None
        if public_message:
            detail["public_message"] = refusals.text_for(code)  # the player's Turkish line; `message` stays
        durable = self.main._store_refusal(self.manager, self.record, self.action_id, self.request_hash, status_code,
                                           detail)
        if not durable:
            detail = {"code": code, "message": message}
            if public_message:
                detail["public_message"] = refusals.text_for(code)
        return HTTPException(status_code=status_code, detail=detail)

    def refuse_model_failure(self, code: str, message: str | None = None) -> HTTPException:
        """Answer a model failure on a turn that applied nothing, and let the campaign go on.

        The failure says nothing about the campaign, so it does not hold later moves: any new id runs. The browser
        closes its move on not_applied and retries with a new id, so this id is closed for good (D-106): a late
        copy replays this refusal instead of running a second turn. The not_applied claim needs a verified
        rollback and a durable refusal record. No message means api.main's MODEL_FAILURE_MESSAGE.
        """
        if message is None:
            message = self.main.MODEL_FAILURE_MESSAGE
        self.take_back_opening()
        front_proposal.log_refused(self.session)  # D-408: a refused line shows in the play measurement
        detail = {"code": code, "message": message, "not_applied": True}
        durable = getattr(self.record, "usable", True) and self.main._store_refusal(
            self.manager, self.record, self.action_id, self.request_hash, 503, detail, what="Model-failure refusal",
        )
        if not durable:
            detail = {"code": code, "message": message}
        return HTTPException(status_code=503, detail=detail)

    def restore_turn_snapshot(self) -> None:
        # Checkpoint restoration can replace these separately-owned
        # values before an engine/model failure rejects the turn.
        try:
            self.main._rollback_session(self.record, self.session, self.snapshot)
            self.session.world_metadata = copy.deepcopy(self.metadata_snapshot)
            self.record.journal = copy.deepcopy(self.journal_snapshot)
            self.record.narrative_memory = copy.deepcopy(
                self.narrative_memory_snapshot
            )
            self.record.lore_authority = self.lore_authority_snapshot
            self.session.campaign_lore_state = self.lore_authority_snapshot
        except HTTPException:
            raise
        except Exception as restore_error:
            self.record.usable = False
            self.main._logger.critical(
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

    def put_back(self) -> None:
        self.main._put_back_turn(self.record, self.session, self.snapshot, self.lore_authority_snapshot,
                                 self.metadata_snapshot, self.journal_snapshot, self.narrative_memory_snapshot)

    def undo_point(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "player_message": self.request.message,
            "snapshot": self.snapshot,
            "journal": self.journal_snapshot,
            "narrative_memory": self.narrative_memory_snapshot,
            "lore_authority": self.lore_authority_snapshot,
            "world_metadata": self.metadata_snapshot,
            "post_turn_fingerprint": self.main._state_fingerprint(self.session),
        }

    def adopt_committed_turn(self) -> None:
        self.manager.adopt_committed_turn(self.record, self.staged_narrative_memory, self.combat_history_entry)
        if isinstance(self.session, game.GameSession):  # D-110: the committed turn keeps its one-step undo
            self.main._adopt_undo_checkpoint(self.record, self.undo_point)


def register_turn_routes(application: FastAPI, *, get_record: Any, ensure_usable: Any, manager: Any,
                         campaign_http_exception: Any, replay_action_response: Any, adapter: Any,
                         api_main: Any) -> None:
    @application.post(
        "/api/game/sessions/{session_id}/turn",
        response_model=TurnResponse,
    )
    def play_turn(session_id: str, request: TurnRequest) -> TurnResponse:
        record = get_record(session_id)
        run = _claim_turn(record, session_id, request, application=application, manager=manager,
                          campaign_http_exception=campaign_http_exception, api_main=api_main)
        session = run.session
        with record.turn_lock:
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            # A request that queued behind a failing one must not run on a runtime that failure just quarantined (R05).
            ensure_usable(record)
            replay = _replay_stored_answer(run, campaign_http_exception, replay_action_response)
            if replay is not None:
                return replay
            try:
                manager.assert_current(record)
            except CampaignError as error:
                # An intent that was claimed earlier stays open (it may be running in another session); only the same
                # id with the same payload, or the player's server-proven abandon, closes it.
                raise campaign_http_exception(error) from None
            if request.economic_action is not None:
                # The card's own path: no free-text turn, no model, one commit with this action's receipt.
                return api_main.economic_step(record, session, session_id, request, run.action_id, run.request_hash,
                                              run.refuse_before_commit, manager=manager, api_main=api_main)
            _validate_combat_request(run)
            # D-256: anything unexpected before the snapshot takes the opening step back too (a refusal already did).
            try:
                _preflight(run, adapter)
            except BaseException:
                run.take_back_opening()
                raise
            _take_snapshot(run)
            previous_lore_context = getattr(
                session, "lore_authority_context", None
            )
            try:
                _plan_turn(run)
                _run_engine(run)
            except Exception as error:
                try:
                    run.restore_turn_snapshot()
                except HTTPException:
                    raise
                except Exception as restore_error:
                    record.usable = False
                    api_main._logger.critical(
                        "Session rollback failed (error_type=%s); session closed",
                        type(restore_error).__name__,
                    )
                if isinstance(error, HTTPException):
                    raise
                api_main._logger.error(
                    "Engine turn failed (error_type=%s, rolled_back=true)",
                    type(error).__name__,
                    exc_info=True,
                )
                from dialogue_runtime import DialogueResponseError, DialogueProviderError
                if isinstance(error, DialogueProviderError):
                    raise run.refuse_model_failure("ollama_unavailable") from None
                if isinstance(error, DialogueResponseError):
                    raise run.refuse_model_failure("invalid_dialogue_response") from None
                # The snapshot was restored above (a failed restore raised session_restore_failed
                # and never reaches here), so these refusals are "certainly never applied".
                if isinstance(error, combat_lifecycle.CombatRequestError):
                    raise run.refuse_before_commit(error.status_code, error.code, str(error)) from None
                raise run.refuse_before_commit(500, "engine_error", "The game turn could not be completed.") from None
            finally:
                session.lore_authority_context = previous_lore_context
                if isinstance(session, game.GameSession):
                    # The reading ahead of the turn may have failed before the turn could clear its own coin fields,
                    # or before the turn could close the reading itself; a later turn must not pick either up.
                    game._clear_turn_transients(session)
                    front_proposal.end(session)

            _check_engine_answer(run)
            _stage_lore_and_memory(run)
            _build_response(run)
            _autosave(run, campaign_http_exception)
            _log_completed_turn(run, adapter)
            if isinstance(session, game.GameSession):
                # LR00-P7: remember exactly how the world looked before this
                # turn, and how it looks now, so one explicit undo can restore
                # it only if nothing else has changed since.
                record.undo_checkpoint = run.undo_point()
            return run.response_payload


def _claim_turn(record: Any, session_id: str, request: TurnRequest, *, application: FastAPI, manager: Any,
                campaign_http_exception: Any, api_main: Any) -> TurnRun:
    """Hash the request and claim its action id before the turn lock is awaited."""
    if request.economic_action is not None and not api_main.ECONOMIC_ACTIONS_ENABLED:
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
            durable = api_main._store_refusal(manager, record, action_id, request_hash, 409, detail)
            if not durable:
                detail.pop("not_applied")
            raise HTTPException(status_code=409, detail=detail)
    return TurnRun(main=api_main, manager=manager, record=record, session=session, session_id=session_id,
                   request=request, action_id=action_id, request_hash=request_hash, effective_mode=effective_mode,
                   active_adapter=active_adapter)


def _replay_stored_answer(run: TurnRun, campaign_http_exception: Any, replay_action_response: Any) -> Any:
    """The stored answer of an id already used: its receipt (None when there is none), or its refusal raised again."""
    manager, record, action_id, request_hash = run.manager, run.record, run.action_id, run.request_hash
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
            previous_action["response"], TurnResponse, run.session_id,
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
    return None


def _validate_combat_request(run: TurnRun) -> None:
    """The combat request check; it may assume an opening step that every later refusal takes back (D-119)."""
    session, request, effective_mode = run.session, run.request, run.effective_mode
    if isinstance(session, game.GameSession):
        try:
            run.opening = combat_lifecycle.validate_request(
                session,
                request.message if effective_mode in {None, "do"} else "",
                request.target_id if effective_mode in {None, "do"} else None,
                combat_id=request.combat_id,
                combat_round=request.combat_round, combat_turn_index=request.combat_turn_index,
            )
        except combat_lifecycle.CombatRequestError as error:
            # Walking off mid-fight is a plain line: the turn answers it in the fight.
            if error.code != "combat_travel" or request.combat_action is not None:
                raise run.refuse_before_commit(error.status_code, error.code, str(error)) from None
        except ValueError:
            raise run.refuse_before_commit(409, "invalid_combat_state", "Combat state is invalid.") from None


def _preflight(run: TurnRun, adapter: Any) -> None:
    """Opt-in check admission, the mechanical-turn choice and the model preflight; nothing is changed yet."""
    import authored_dungeon
    import bounded_encounter
    import exploration
    session, request, effective_mode = run.session, run.request, run.effective_mode
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
            raise run.refuse_before_commit(error.status_code, error.code, str(error)) from None
    run.check_evidence = [] if request.check_feature is not None else None
    import spell_scope
    import sorcery_points
    run.slot_conversion = isinstance(session, game.GameSession) and sorcery_points.native_conversion_request(
        request.combat_action.model_dump(exclude_none=True) if request.combat_action else None,
    )
    if isinstance(session, game.GameSession) and (
        session.character.get("current_hp", 1) <= 0
        or run.slot_conversion
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
        run.active_adapter = bounded_encounter.MechanicalTurnContext(run.active_adapter)
    if run.active_adapter is None:
        raise run.refuse_model_failure("ollama_unavailable")
    try:
        run.active_adapter.ensure_required_model()
    except OllamaUnavailableError as error:
        run.main._logger.warning(
            "Ollama preflight failed (error_type=%s)",
            error.error_type,
        )
        raise run.refuse_model_failure("ollama_unavailable") from None
    except RequiredModelUnavailableError:
        selected_model = adapter.model_name if adapter is not None else run.main.MODEL_NAME
        run.main._logger.warning("Required model %s is unavailable.", selected_model)
        # Saying it again cannot help a model that is not installed, so this one stays a plain, truthful setup message.
        raise run.refuse_model_failure(
            "model_unavailable", f"Required model {selected_model} is unavailable.",
        ) from None


def _take_snapshot(run: TurnRun) -> None:
    """The turn's rollback point, taken before the opening step (D-119), and the turn-owned field copies."""
    import bounded_encounter
    session, record = run.session, run.record
    # D-119: the snapshot is the state before the opening step, so every rollback takes the step back too.
    run.take_back_opening()
    run.snapshot = run.main._capture_session(session)
    if run.opening is not None:
        run.opening["distance_ft"] = 5
        run.opening = None
    # Runtime capability only; never serialized into campaign state.
    session._exploration_narration_available = (
        isinstance(run.active_adapter, bounded_encounter.MechanicalTurnContext)
        and run.active_adapter.adapter is not None
    )
    run.metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
    run.journal_snapshot = copy.deepcopy(record.journal)
    run.narrative_memory_snapshot = copy.deepcopy(
        record.narrative_memory
    )
    run.lore_authority_snapshot = getattr(
        record,
        "lore_authority",
        CampaignLoreState.legacy_unbound(),
    )
    run.narrative_player_message = run.main.redact_sensitive_values(
        run.request.message
    )


def _plan_turn(run: TurnRun) -> None:
    """Ambient context, the front reading (flag on), the scene planner and the turn's lore context."""
    main, session, record, request = run.main, run.session, run.record, run.request
    effective_mode, active_adapter = run.effective_mode, run.active_adapter
    if record.campaign_id is not None:
        living_world.set_ambient_context(
            session.world_state,
            main.world_metadata_for_state(
                session.world_state,
                getattr(session, "world_metadata", None),
            ),
            session.character,
            record.campaign_id,
        )
    run.effective_target_id = (
        None
        if effective_mode == "ask_dm" or run.slot_conversion
        else request.target_id
    )
    plan_kwargs = {"target_id": run.effective_target_id}
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
        and not run.slot_conversion and request.combat_action is None
        and request.check_feature is None
    ):
        # The reading stands before the planner and counts against this turn's cap.
        with active_adapter.capture_model_calls() as calls_before_turn, \
                active_adapter.capture_model_failures() as reading_failures:
            session.front_read_ahead(
                run.narrative_player_message,
                target_id=run.effective_target_id,
                interaction_mode=effective_mode,
            )
        if reading_failures:
            # Owner rule G6 ("Tekrar dene"): a provider outage during the reading spends no line.
            run.restore_turn_snapshot()
            main._logger.warning("Front reading failed (error_type=%s)", reading_failures[0])
            raise run.refuse_model_failure("ollama_unavailable") from None
    # Exact resource-only conversion has no scene/reference authority.
    # Its display label or a retained UI target must not focus an NPC,
    # materialize a place, or alter an existing conversation first.
    # The planner's own entry (an inn walked into by name) may tell its arrival with a model call:
    # it is counted in the same window as the front reading, so the turn's cap holds.
    with active_adapter.capture_model_calls() as planner_calls:
        planner_calls.extend(calls_before_turn)
        run.scene_plan = None if run.slot_conversion else session.plan_living_world_turn(
            run.narrative_player_message,
            **plan_kwargs,
        )
    run.calls_before_turn = planner_calls
    lore_context = main._lore_context_for_turn(
        record,
        session,
        run.narrative_player_message,
        run.effective_target_id,
        scene_plan=run.scene_plan,
    )
    lore_diagnostics = lore_context.get("diagnostics", {})
    main._logger.info(
        "Lore retrieval turn=%s selected_fact_count=%s selected_fact_ids=%s",
        session.world_state.get("flags", {}).get("turn_index", 0) + 1,
        lore_diagnostics.get("selected_fact_count", 0),
        lore_diagnostics.get("selected_fact_ids", []),
    )
    session.lore_authority_context = lore_context
    session.campaign_lore_state = run.lore_authority_snapshot


def _run_engine(run: TurnRun) -> None:
    """The engine turn inside the narrative frame, the canonical metadata and the turn's model-call window."""
    main, session, request, active_adapter = run.main, run.session, run.request, run.active_adapter
    with main.narrative_turn_context(
        run.record.narrative_memory,
        run.narrative_player_message,
        journal=run.record.journal,
    ) as narrative_frame:
        run.narrative_frame = narrative_frame
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
            with main.canonical_world_metadata_context(
                lambda: main.world_metadata_for_state(
                    session.world_state,
                    getattr(session, "world_metadata", None),
                )
            ):
                with active_adapter.capture_model_calls() as model_calls:
                    run.model_calls = model_calls
                    model_calls.extend(run.calls_before_turn)
                    with active_adapter.capture_model_failures() as model_failures:
                        run.model_failures = model_failures
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
                        run_kwargs = _engine_kwargs(run, run_parameters)
                        try:
                            run.result = run_turn(request.message, **run_kwargs)
                        except game.PlayerCannotAct:
                            run.restore_turn_snapshot()
                            run.result = session.player_cannot_act_turn()
                        except combat_lifecycle.CombatRequestError as error:
                            if (request.combat_action is not None or run.effective_mode not in {None, "do"}
                                    or request.message.lstrip().startswith("/")
                                    or not session.world_state.get("combat", {}).get("active")):
                                raise  # typed commands and door rules keep their typed refusal
                            run.restore_turn_snapshot()
                            run.result = session.combat_refusal_turn(error)
        finally:
            if previous_claims is missing_claims:
                delattr(session, "_supported_player_claims")
            else:
                session._supported_player_claims = previous_claims


def _engine_kwargs(run: TurnRun, run_parameters: Any) -> dict[str, Any]:
    """The keyword arguments the engine's run_player_turn accepts for this request."""
    request = run.request
    run_kwargs = {}
    if request.check_feature is not None:
        run_kwargs.update(check_feature=request.check_feature, check_evidence=run.check_evidence)
    if request.combat_action is not None:
        run_kwargs["combat_action"] = request.combat_action.model_dump(exclude_none=True)
    if "scene_plan" in run_parameters:
        run_kwargs["scene_plan"] = run.scene_plan
    if (
        "interaction_mode" in run_parameters
        and run.effective_mode is not None
    ):
        run_kwargs["interaction_mode"] = run.effective_mode
    if "action_id" in run_parameters:
        run_kwargs["action_id"] = run.action_id
    if "session_id" in run_parameters:
        run_kwargs["session_id"] = run.session_id
    if run.effective_target_id is not None:
        run_kwargs["target_id"] = run.effective_target_id
    return run_kwargs


def _check_engine_answer(run: TurnRun) -> None:
    """Engine evidence, model failures, the call cap, the narration and intent infrastructure failures."""
    main, session, result = run.main, run.session, run.result
    run.engine_evidence = (
        result.pop("_engine_event_evidence", None)
        if isinstance(result, dict)
        else None
    )
    engine_evidence = run.engine_evidence
    # Who wrote this turn's narration, as the engine reported it; saved beside the history row. A turn
    # the engine reports nothing for stays unrecorded (None): nothing is guessed here.
    engine_telemetry = engine_evidence.get("telemetry") if isinstance(engine_evidence, dict) else None
    run.narration_source = engine_telemetry.get("narration_source") if isinstance(engine_telemetry, dict) else None
    if isinstance(engine_evidence, dict):
        # The API's rollback snapshot is the commit boundary. Derive
        # entity additions from those exact before/after states so
        # pre-planner materialization is included in the receipt.
        run.engine_evidence = {
            **engine_evidence,
            "procedural_entity_ids": sorted(
                main._procedural_entity_refs(session.world_state)
                - main._procedural_entity_refs(
                    run.snapshot["save"].get("world_state", {})
                )
            ),
        }

    from model_phase import only_resolved_narration_failures

    model_failures = run.model_failures
    if only_resolved_narration_failures(model_failures):
        main._logger.warning(
            "Resolved narration unavailable; deterministic fallback retained (phases=%s)",
            [failure.phase for failure in model_failures],
        )
    elif model_failures:
        run.restore_turn_snapshot()
        main._logger.warning(
            "Ollama chat failed (error_type=%s)",
            model_failures[0],
        )
        raise run.refuse_model_failure("ollama_unavailable") from None

    if len(run.model_calls) > main.turn_call_cap(run.model_calls):
        run.restore_turn_snapshot()
        main._logger.error("Engine exceeded the per-turn model-call limit.")
        raise run.refuse_before_commit(500, "engine_error", "The game turn exceeded its model-call limit.") from None

    run.narration = result.get("narration") if isinstance(result, dict) else None
    if not isinstance(run.narration, str) or not run.narration.strip():
        run.restore_turn_snapshot()
        main._logger.error("Engine returned an invalid turn result.")
        raise run.refuse_before_commit(500, "engine_error", "The game turn returned an invalid response.") from None

    action_result = run.action_result = (
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
        run.restore_turn_snapshot()
        main._logger.warning(
            "Intent infrastructure failure (code=%s, rolled_back=true)",
            code,
        )
        raise run.refuse_model_failure(code)


def _contains_death_rollback(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    resolution = value.get("death_resolution")
    if isinstance(resolution, dict) and resolution.get("rolled_back") is True:
        return True
    for nested_key in ("death_save", "enemy_action"):
        if _contains_death_rollback(value.get(nested_key)):
            return True
    nested_actions = value.get("enemy_actions")
    return isinstance(nested_actions, list) and any(
        _contains_death_rollback(item) for item in nested_actions
    )


def _stage_lore_and_memory(run: TurnRun) -> None:
    """The world metadata, the staged lore authority and the staged narrative memory; nothing is saved yet."""
    main, session, record, action_result = run.main, run.session, run.record, run.action_result
    run.death_rolled_back = death_rolled_back = _contains_death_rollback(action_result)
    if not death_rolled_back:
        main.set_session_world_metadata(session, run.metadata_snapshot)
    try:
        run.staged_lore_authority = (
            record.lore_authority
            if death_rolled_back
            else main._stage_engine_lore_state(
                getattr(session, "campaign_lore_state", None) or run.lore_authority_snapshot,
                run.engine_evidence,
                action_result,
                run.snapshot["save"].get("world_state", {}),
                session.world_state,
            )
        )
    except Exception as error:
        run.put_back()
        main._logger.error(
            "Engine lore evidence failed validation (error_type=%s)",
            type(error).__name__,
        )
        raise run.refuse_before_commit(500, "engine_error", "Campaign lore evidence could not be verified.") from None
    try:
        run.staged_narrative_memory = (
            copy.deepcopy(record.narrative_memory)
            if death_rolled_back
            else main.update_narrative_memory(
                record.narrative_memory,
                player_message=run.narrative_player_message,
                narration=main.redact_sensitive_values(run.narration),
                action_result=action_result,
                world_state_before=run.snapshot["save"].get(
                    "world_state",
                    {},
                ),
                world_state_after=session.world_state,
                world_metadata=main.world_metadata_for_state(
                    session.world_state,
                    getattr(session, "world_metadata", None),
                ),
            )
        )
    except Exception as error:
        run.put_back()
        main._logger.error(
            "Narrative continuity update failed (error_type=%s)",
            type(error).__name__,
        )
        raise run.refuse_before_commit(500, "narrative_memory_error", "Campaign continuity could not be updated safely.") from None


def _build_response(run: TurnRun) -> None:
    """The result cards, the journal, the state and the response receipt; the record lore is staged last."""
    main, session, record, request, action_result = run.main, run.session, run.record, run.request, run.action_result
    try:
        skill_check_result = main.serialize_skill_check_result(
            action_result,
            session,
            **({"check_evidence": run.check_evidence} if request.check_feature is not None else {}),
        )
        combat_result = main.serialize_combat_result(action_result, session)
        run.combat_history_entry = main.serialize_combat_history_entry(
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
        if not run.death_rolled_back:
            record.journal = main.update_campaign_journal(
                record.journal,
                run.snapshot["save"],
                session.serialize_game_state(),
                action_result,
                main.world_metadata_for_state(
                    session.world_state,
                    getattr(session, "world_metadata", None),
                ),
                presence_location_id=presence_location_id,
            )
        state = main.serialize_session_state(
            session,
            record.journal,
            run.staged_lore_authority,
        )
    except Exception as error:
        run.put_back()
        if isinstance(error, SkillCheckResultSerializationError):
            main._logger.error(
                "Engine returned an invalid skill-check result."
            )
            raise run.refuse_before_commit(500, "engine_error", "The skill-check result could not be verified safely.") from None
        if isinstance(error, CombatResultSerializationError):
            main._logger.error(
                "Engine returned an invalid combat result or history entry."
            )
            raise run.refuse_before_commit(500, "engine_error", "The combat result could not be verified safely.") from None
        main._logger.error(
            "Campaign journal update failed (error_type=%s)",
            type(error).__name__,
        )
        raise run.refuse_before_commit(500, "journal_error", "The campaign journal could not be updated safely.") from None
    try:
        response = TurnResponse(
            session_id=run.session_id,
            action_id=run.action_id,
            narration=run.narration,
            state=state,
            combat_result=combat_result,
            combat_history_entry=run.combat_history_entry,
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
            turn_outcome=main._turn_outcome(action_result),
        )
        run.response_payload = main.redact_sensitive_values(
            response.model_dump(mode="json")
        )
    except Exception as error:
        # Nothing is saved yet: the answer could not be built, so the turn is put back whole (B1).
        run.put_back()
        main._logger.error("Turn response could not be built (error_type=%s)", type(error).__name__)
        raise run.refuse_before_commit(500, "engine_error", "The turn response could not be built safely.") from None
    record.lore_authority = run.staged_lore_authority


def _autosave(run: TurnRun, campaign_http_exception: Any) -> None:
    """The one commit with this action's receipt; a failed save puts the whole turn back."""
    main, manager, record, action_id, request_hash = run.main, run.manager, run.record, run.action_id, run.request_hash
    try:
        manager.autosave_turn(
            record,
            run.request.message,
            run.narration,
            combat_history_entry=run.combat_history_entry,
            narrative_memory=run.staged_narrative_memory,
            turn_action_receipt={
                "action_id": action_id,
                "request_hash": request_hash,
                "response": run.response_payload,
            },
            narration_source=run.narration_source,
        )
    except CampaignError as error:
        main._raise_if_commit_unconfirmed(
            manager, record, action_id, request_hash, run.response_payload, error,
            adopt=run.adopt_committed_turn,
        )
        record.lore_authority = run.lore_authority_snapshot
        run.put_back()
        main._logger.error(
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
        main._raise_if_commit_unconfirmed(
            manager, record, action_id, request_hash, run.response_payload, error,
            adopt=run.adopt_committed_turn,
        )
        record.lore_authority = run.lore_authority_snapshot
        run.put_back()
        main._logger.error(
            "Campaign autosave failed (error_type=%s)",
            type(error).__name__,
        )
        # Same product rule as above (retry with the same id stays possible), so no never-applied claim here.
        decision = failure_policy.classify_failure(
            failure_policy.ActionPhase.RESOLVED_UNCOMMITTED, "rolled_back", error,
        )
        raise HTTPException(status_code=decision.status_code, detail=decision.detail()) from None


def _log_completed_turn(run: TurnRun, adapter: Any) -> None:
    """The committed turn's diagnostics lines."""
    main, action_result, model_calls, frame = run.main, run.action_result, run.model_calls, run.narrative_frame
    safety_code = (
        action_result.get("infrastructure_code")
        or action_result.get("status")
        if isinstance(action_result, dict)
        else "unavailable"
    )
    main._logger.info(
        "Turn diagnostics (model_calls=%d, safety_code=%s, rolled_back=false)",
        len(model_calls),
        safety_code,
    )
    if getattr(adapter, "model_chain", None):
        main._logger.info("Turn providers (answered=%s)", ",".join(model_calls))
    main._logger.info(
        "Game turn completed (model=%s, model_calls=%d, narrative_scene=%s, narrative_tokens=%s, narrative_estimated_total=%s, narrative_budget=%s/%s, narrative_context_bytes=%s, narrative_selected=%s, narrative_ambiguities=%d)",
        adapter.model_name if adapter is not None else main.MODEL_NAME,
        len(model_calls),
        frame.diagnostics.get("scene_type", "unavailable"),
        frame.diagnostics.get("estimated_tokens", "unavailable"),
        frame.diagnostics.get(
            "estimated_total_tokens",
            "unavailable",
        ),
        frame.diagnostics.get(
            "max_estimated_total_tokens",
            "unavailable",
        ),
        frame.diagnostics.get(
            "model_context_window_tokens",
            "unavailable",
        ),
        frame.diagnostics.get("packet_characters", "unavailable"),
        frame.diagnostics.get("selected_counts", {}),
        len(frame.diagnostics.get("ambiguities", [])),
    )
