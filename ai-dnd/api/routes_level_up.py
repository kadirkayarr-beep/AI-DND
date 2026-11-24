"""Read-only level-up and shop-counter routes moved out of api.main.create_app (D-531 stage 1).

level_up_projection stays importable because the apply route (still in create_app) reuses it.
"""
from __future__ import annotations

import copy
from typing import Any, Callable

from fastapi import FastAPI, HTTPException

from api.schemas import LevelUpPreviewResponse, ShopCounterResponse


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
    ceiling = {"Sorcerer": 5, "Barbarian": 5, "Cleric": 5, "Fighter": 5, "Monk": 5, "Paladin": 5, "Rogue": 5, "Wizard": 5}.get(cls, 2)
    valid_applied = type(applied) is int and 1 <= applied <= ceiling
    target = min(applied + 1, ceiling) if valid_applied else ceiling
    result = dict(session_id=session_id, campaign_id=record.campaign_id,
                  revision=token[1] if isinstance(token, tuple) and len(token) == 2 else None,
                  status="blocked", reason=None, target_level=target,
                  class_name=cls, from_level=applied if valid_applied else None)
    if record.campaign_id is None:
        result["reason"] = "campaign_persistence_required"
    elif cls not in {"Sorcerer", "Barbarian", "Cleric", "Fighter", "Monk", "Paladin", "Rogue", "Wizard"}:
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
                if cls in ("Wizard", "Cleric"):
                    result["cantrip_ids"] = preview.get("cantrip_ids", [])
                    if cls == "Wizard":
                        result["spellbook_spell_ids"] = preview.get("spellbook_spell_ids", [])
                if cls == "Paladin":
                    result["prepared_spell_ids"] = preview.get("prepared_spell_ids", [])
                    if target == 2:
                        result.update(fighting_style_options=preview.get("fighting_style_options"), cantrip_ids=preview.get("blessed_warrior_cantrip_ids", []))
    return LevelUpPreviewResponse.model_validate(result).model_dump(mode="json")


def register_level_up_read_routes(
    application: FastAPI,
    *,
    get_record: Callable[[str], Any],
    require_current: Callable[[Any], None],
) -> None:
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

    @application.get("/api/game/sessions/{session_id}/shop", response_model=ShopCounterResponse,
                     operation_id="getGameSessionShop", response_model_exclude_unset=True)
    def read_shop_counter(session_id: str) -> dict[str, Any]:
        """The counter's quote, read under the turn lock so it is never half a turn; it writes nothing."""
        import shop_trade
        record = get_record(session_id)
        with record.turn_lock:
            record = get_record(session_id)
            if record.revoked:
                raise HTTPException(status_code=404, detail={"code": "unknown_session", "message": "Session not found."})
            require_current(record)
            token = getattr(record.game_session, "_campaign_persistence_version", None)
            counter = shop_trade.counter(copy.deepcopy(record.game_session.world_state))
            return ShopCounterResponse.model_validate(dict(
                session_id=session_id, campaign_id=record.campaign_id,
                revision=token[1] if isinstance(token, tuple) and len(token) == 2 else None, **counter,
            )).model_dump(mode="json", exclude_unset=True)
