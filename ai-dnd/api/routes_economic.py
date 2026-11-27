"""The economic card step of the play turn, moved out of api.main.create_app (D-531 stage 3).

Not a route of its own: play_turn calls it under the turn lock. Same order of rollback, receipt, autosave and Undo
point. api.main's own helpers, its logger and serialize_session_state are read through the passed `api_main` module
at call time, as the closure did, so a patch on api.main still reaches this step.
"""
from __future__ import annotations

import copy
from typing import Any

from fastapi import HTTPException

import game
import turn_close
from api import failure_policy
from api.schemas import PublicEconomicResolution, TurnOutcome, TurnRequest, TurnResponse
from api.serializers import redact_sensitive_values


def economic_step(record: Any, session: Any, session_id: str, request: TurnRequest, action_id: str,
                  request_hash: str, refuse_before_commit: Any, *, manager: Any, api_main: Any) -> dict[str, Any]:
    """Prepare, cancel or confirm a card under the turn lock, committed once with this action's receipt (A3).

    Prepare and cancel are not turns: the undo checkpoint stays. A confirm is a turn only when it consumes the
    card (applied, or refused on money, tender or the check): then the turn counter moves and the checkpoint is
    this action. A confirm that consumes nothing (not prepared, wrong digest, stale) writes only the receipt
    and, when stale, the card's own cancelled status, which the undo fingerprint leaves out (C11).
    """
    import dataclasses
    import bold_acts
    import economic_actions
    if not isinstance(session, game.GameSession):
        raise refuse_before_commit(409, "economic_unavailable", "Economic actions need a game session.")
    action = request.economic_action.root
    world = session.world_state
    snapshot = api_main._capture_session(session)
    journal_snapshot = copy.deepcopy(record.journal)
    memory_snapshot = copy.deepcopy(record.narrative_memory)
    metadata_snapshot = copy.deepcopy(getattr(session, "world_metadata", None))
    lore_snapshot = record.lore_authority
    checkpoint = getattr(record, "undo_checkpoint", None)
    protect = checkpoint.get("action_id") if isinstance(checkpoint, dict) else None
    state = economic_actions.EconomicState(world=world, character=session.character)
    consumed = False
    resolution = None
    outcome: dict[str, Any] = {"action": f"economic_{action.kind}"}

    def put_back() -> None:
        api_main._rollback_session(record, session, snapshot)

    if action.kind in {"prepare", "confirm"}:
        # The same guard the free-text turn uses: a dead or unconscious player opens and pays nothing.
        try:
            session.require_player_can_act()
        except game.PlayerCannotAct as error:
            put_back()
            raise refuse_before_commit(409, "player_cannot_act", str(error)) from None
        except Exception as error:
            put_back()
            api_main._logger.error("Economic action could not check the player (error_type=%s)", type(error).__name__)
            raise refuse_before_commit(500, "engine_error", "The economic action could not be completed.") from None
    try:
        if action.kind == "prepare":
            fields = action.proposal
            proposal = economic_actions.EconomicProposal(
                purpose=fields.purpose, recipient_id=fields.recipient_id, source_id=fields.source_id,
                item_id=fields.item_id, count=fields.count, amount_cp=fields.amount_cp, tip_cp=fields.tip_cp,
                tender_cp=fields.tender_cp, dependency=fields.dependency, source_action_id=action_id,
                text_span=(economic_actions.TextSpan(start=fields.text_span.start, end=fields.text_span.end)
                           if fields.text_span is not None else None))
            prepared = economic_actions.prepare_from_panel(
                state, proposal, campaign_id=str(record.campaign_id or session_id), actor_id="player",
                turn_index=world.get("flags", {}).get("turn_index", 0), protect_action_id=protect)
            narration = prepared.public_message
            outcome.update(status=prepared.status, reason=prepared.reason_code)
        elif action.kind == "cancel":
            closed = economic_actions.cancel_offer(world, offer_id=action.offer_id)
            economic_actions.prune_offer_records(world, protect_action_id=protect)
            narration = "Teklif iptal edildi; hiçbir şey ödenmedi." if closed else "İptal edilecek açık bir teklif yok."
            outcome.update(status="cancelled" if closed else "not_open")
        else:
            operation_id = f"offer:{action_id}"
            resolution = economic_actions.confirm_offer(
                state, offer_id=action.offer_id, confirmation_digest=action.confirmation_digest,
                operation_id=operation_id,
                check=lambda skill, dc: bold_acts._check(session, skill, dc)["result"])
            stored = economic_actions.offer_records(world).get(action.offer_id)
            consumed = (isinstance(stored, dict) and stored.get("status") == "consumed"
                        and stored.get("operation_id") == operation_id)
            if consumed:
                stored["consumed_action_id"] = action_id
                turn_close.advance(world)  # the same counter every turn moves
                economic_actions.prune_offer_records(world, protect_action_id=action_id)
            narration = resolution.public_summary
            outcome.update(status=resolution.status, reason=resolution.reason_code)
    except economic_actions.EconomicReceiptError as error:
        put_back()
        api_main._logger.error("Economic receipt refused the confirm (reason=%s)", error.reason)
        raise refuse_before_commit(409, "economic_receipt_refused",
                                   "The economic result did not match its offer; nothing was applied.") from None
    except HTTPException:
        raise
    except Exception as error:
        put_back()
        api_main._logger.error("Economic action failed (error_type=%s)", type(error).__name__)
        raise refuse_before_commit(500, "engine_error", "The economic action could not be completed.") from None
    try:
        public = (economic_actions.public_resolution(state, resolution) if resolution is not None else None)
        response = TurnResponse(
            session_id=session_id, action_id=action_id, narration=narration,
            state=api_main.serialize_session_state(session, record.journal, record.lore_authority),
            turn_outcome=TurnOutcome(**outcome),
            economic_resolution=(PublicEconomicResolution.model_validate(dataclasses.asdict(public))
                                 if public is not None else None),
        )
        response_payload = redact_sensitive_values(response.model_dump(mode="json"))
    except Exception as error:
        put_back()
        api_main._logger.error("Economic response could not be built (error_type=%s)", type(error).__name__)
        raise refuse_before_commit(500, "engine_error", "The economic response could not be built safely.") from None

    def undo_point() -> dict[str, Any]:
        return {
            "action_id": action_id,
            "player_message": request.message,
            "turn_label": narration,  # the card's fixed words name nothing; the undo quotes the engine's summary
            "snapshot": snapshot,
            "journal": journal_snapshot,
            "narrative_memory": memory_snapshot,
            "lore_authority": lore_snapshot,
            "world_metadata": metadata_snapshot,
            "post_turn_fingerprint": api_main._state_fingerprint(session),
        }

    def adopt_committed_payment() -> None:
        manager.adopt_committed_turn(record, None, None)
        if consumed:  # D-110: a committed payment keeps its one-step undo when its acknowledgement was lost
            api_main._adopt_undo_checkpoint(record, undo_point)

    try:
        manager.autosave_turn(
            record, request.message, narration,
            turn_action_receipt={"action_id": action_id, "request_hash": request_hash,
                                 "response": response_payload},
            narration_source="deterministic_system",  # every card line is economic_actions' own text
        )
    except Exception as error:
        api_main._raise_if_commit_unconfirmed(
            manager, record, action_id, request_hash, response_payload, error,
            adopt=adopt_committed_payment,
        )
        put_back()
        api_main._logger.error("Economic autosave failed (error_type=%s)", type(error).__name__)
        decision = failure_policy.classify_failure(
            failure_policy.ActionPhase.RESOLVED_UNCOMMITTED, "rolled_back", error,
        )
        raise HTTPException(status_code=decision.status_code, detail=decision.detail()) from None
    if consumed:
        record.undo_checkpoint = undo_point()
    return response_payload
