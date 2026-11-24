"""Read-only spell preparation route moved out of api.main.create_app (D-531 stage 1): same path, model and order."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException

from api.schemas import SpellPrepareViewResponse


def register_spell_read_routes(
    application: FastAPI,
    *,
    get_record: Callable[[str], Any],
    require_current: Callable[[Any], None],
) -> None:
    @application.get("/api/game/sessions/{session_id}/spellcasting/prepare", response_model=SpellPrepareViewResponse,
                     operation_id="getGameSessionSpellPreparation")
    def read_spell_preparation(session_id: str) -> dict[str, Any]:
        """4C.2: the preparation window, its limit and candidates. Writes nothing."""
        import spell_preparation
        record = get_record(session_id)
        with record.turn_lock:
            record = get_record(session_id)
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            require_current(record)
            try:
                view = spell_preparation.view(record.game_session)
            except (ValueError, KeyError, TypeError):  # the POST route's guard: an unreadable saved state is a 409, never a 500
                raise HTTPException(status_code=409, detail={
                    "code": "prepare_unavailable", "message": "Kayıtlı büyü durumu okunamadı."}) from None
            return SpellPrepareViewResponse.model_validate({"session_id": session_id, **view}).model_dump(mode="json")
