"""Undo route moved out of api.main.create_app (D-531 stage 3): same paths, order, lock, receipt and rollback.

api.main's own helpers and serialize_session_state are read through the passed `api_main` module at call time,
as the closure did, so a patch on api.main still reaches this route.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from fastapi import FastAPI, HTTPException

import game
from api.history_view import UNDO_HISTORY_MARKER, undo_narration
from api.persistence.campaign_models import CampaignError
from api.persistence.campaign_store import CampaignStore
from api.schemas import TurnUndoRequest, TurnUndoResponse
from api.serializers import redact_sensitive_values


def register_undo_routes(application: FastAPI, *, get_record: Any, ensure_usable: Any, manager: Any,
                         campaign_http_exception: Any, replay_action_response: Any,
                         refuse_while_action_open: Any, require_current: Any, api_main: Any) -> None:
    @application.post(
        "/api/game/sessions/{session_id}/undo",
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
            # D-127: an id closed for good (abandon or an earlier refusal) never undoes anything later.
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
            refuse_while_action_open(record)
            require_current(record)
            session = record.game_session
            checkpoint = getattr(record, "undo_checkpoint", None)
            if not isinstance(checkpoint, dict) or checkpoint.get("action_id") != target_action_id:
                raise HTTPException(status_code=409, detail={
                    "code": "undo_unavailable",
                    "message": "Geri alınabilecek bir son tur yok.",
                })
            if api_main._final_death(session):
                raise HTTPException(status_code=409, detail={
                    "code": "undo_final_death",
                    "message": "Ironman ölümü kesindir; geri alınamaz."
                    if session.world_state["death_state"].get("mode") == "IRONMAN"
                    else "Gerçek ölüm kesindir; geri alınamaz.",
                })
            if api_main._state_fingerprint(session) != checkpoint["post_turn_fingerprint"]:
                record.undo_checkpoint = None
                raise HTTPException(status_code=409, detail={
                    "code": "undo_stale",
                    "message": "Son turdan sonra başka bir değişiklik oldu; o tur artık geri alınamaz.",
                })
            current = api_main._capture_session(session)
            current_metadata = copy.deepcopy(getattr(session, "world_metadata", None))
            current_journal = copy.deepcopy(record.journal)
            current_memory = copy.deepcopy(record.narrative_memory)
            current_lore = record.lore_authority
            payload = None
            import economic_actions
            # C11/D2: the cards as they are now; only the one the undone action consumed opens again.
            current_offers = copy.deepcopy(economic_actions.offer_records(session.world_state))
            # Read only, for the sentence: the purse the player sees before and after the very same restore.
            purse_now = economic_actions.wallet_total_cp(session.world_state)
            try:
                api_main._restore_session(session, checkpoint["snapshot"])
                # D-211: the undone turn answered (or dropped) the surrendered-foe question; Undo never reopens it, so
                # the same blow sent again is asked about again, never struck unasked.
                session._surrender_strike_asked = None
                # D-211 review: the same for "kavga mı başlatıyorsun?" (its flags ride the same snapshot).
                session._attack_asked, session._blow_asked, session._blow_asked_line = False, None, None
                session._heavy_asked = session._heavy_confirmed = None  # D-109: and the crime/threat question and its yes
                if isinstance(session, game.GameSession):
                    economic_actions.reconcile_offers_after_undo(
                        session.world_state, current_offers, undone_action_id=target_action_id,
                    )
                session.world_metadata = copy.deepcopy(checkpoint["world_metadata"])
                record.journal = copy.deepcopy(checkpoint["journal"])
                record.narrative_memory = copy.deepcopy(checkpoint["narrative_memory"])
                record.lore_authority = checkpoint["lore_authority"]
                session.campaign_lore_state = checkpoint["lore_authority"]
                narration = undo_narration(
                    str(checkpoint.get("player_message") or ""),
                    purse_delta_cp=economic_actions.wallet_total_cp(session.world_state) - purse_now,
                    turn_label=checkpoint.get("turn_label"),
                )
                state = api_main.serialize_session_state(session, record.journal, record.lore_authority)
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
                    UNDO_HISTORY_MARKER,
                    narration,
                    narrative_memory=record.narrative_memory,
                    turn_action_receipt={
                        "action_id": action_id,
                        "request_hash": request_hash,
                        "response": payload,
                    },
                    narration_source="deterministic_system",  # undo_narration is a fixed Python sentence
                )
            except CampaignError as error:
                api_main._raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, payload, error,
                    adopt=lambda: setattr(record, "undo_checkpoint", None),
                )
                api_main._rollback_session(record, session, current)
                session.world_metadata = current_metadata
                record.journal = current_journal
                record.narrative_memory = current_memory
                record.lore_authority = current_lore
                session.campaign_lore_state = current_lore
                raise campaign_http_exception(error) from None
            except Exception as error:
                api_main._raise_if_commit_unconfirmed(
                    manager, record, action_id, request_hash, payload, error,
                    adopt=lambda: setattr(record, "undo_checkpoint", None),
                )
                api_main._rollback_session(record, session, current)
                session.world_metadata = current_metadata
                record.journal = current_journal
                record.narrative_memory = current_memory
                record.lore_authority = current_lore
                session.campaign_lore_state = current_lore
                raise
            # One step only: a second undo needs a new completed turn first.
            record.undo_checkpoint = None
            return payload
