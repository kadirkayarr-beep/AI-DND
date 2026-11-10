"""Level steps shared by noncaster classes: atomic apply of an empty step and of the ordinary ASI, and the ASI readiness check.

A class supplies only what differs (Barbarian: its AC formula has a CON term). Shared helpers are read through `core.` at call time.
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core


def apply_plain_step(session, preview):
    """A level with no choice whose step may run ahead of XP: unpaid Hit Points, then the level; a refusal changes nothing."""
    import spell_scope
    character = session.character
    new_character = copy.deepcopy(character)
    to_level = preview["to_level"]
    changes = []
    if not preview["hit_points"]["already_applied"]:
        gain = preview["hit_points"]["gain"]
        new_character["max_hp"] += gain
        if new_character["current_hp"] > 0:
            new_character["current_hp"] += gain
        changes.append({"kind": "hit_points", "gain": gain})
    new_character["level"] = max(new_character["level"], to_level)
    new_character["progression_level"] = to_level
    new_character["proficiency_bonus"] = core.proficiency_bonus_for_level(new_character["level"])
    try:
        spell_scope.validate(session.world_state.get("spellcasting_v1"), new_character)
        core.validate_saved(new_character, session.world_state)
    except ValueError:
        return core._reject("resulting_state_invalid")
    character.clear()
    character.update(new_character)
    changes.append({"kind": "level", "from": preview["from_level"], "to": to_level})
    return {"status": "applied", "reason": None, "changes": changes, "effects_pending": list(preview["effects_pending"])}


def _capture_format(session):
    return "_persisted_engine_format" in session.__dict__, copy.deepcopy(session.__dict__.get("_persisted_engine_format"))


def _restore_format(session, captured):
    had_format, previous_format = captured
    if had_format:
        session._persisted_engine_format = previous_format
    else:
        session.__dict__.pop("_persisted_engine_format", None)


def apply_earned_final_step(session, preview):
    """Atomic level 5 with no choice: XP already paid Hit Points and Proficiency Bonus; no refill and no new resource."""
    snapshot = session._capture_runtime_snapshot()
    captured = _capture_format(session)
    try:
        character = copy.deepcopy(session.character)
        character["progression_level"] = 5
        session.character.clear()
        session.character.update(character)
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        core.validate_saved(session.character, session.world_state)
        session._validate_save_payload(session.serialize_game_state())
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        _restore_format(session, captured)
        return core._reject("resulting_state_invalid")
    return {"status": "applied", "reason": None, "changes": [{"kind": "level", "from": 4, "to": 5}],
            "effects_pending": list(preview["effects_pending"])}


def apply_asi_step(session, preview, choices, *, armor_class_ability=None):
    """Atomic ordinary ASI; no resource refill and no caster fabrication. `armor_class_ability` names the class AC formula's own term."""
    projection = core._project_selected_asi_hp(session.character, 4, {"increase": choices["asi"]["increase"]})
    if projection["status"] != "projected":
        return core._reject(projection["reason"])
    snapshot = session._capture_runtime_snapshot()
    captured = _capture_format(session)
    try:
        character = copy.deepcopy(session.character)
        old_ac_modifier = (character[armor_class_ability] - 10) // 2 if armor_class_ability else 0
        base = projection["unpaid_base_gain"]
        character["max_hp"] += base
        if character["current_hp"] > 0:
            character["current_hp"] += base
        character.update(level=max(4, character["level"]), progression_level=4,
                         asi_choices=core._selected_asi_record(choices["asi"]["increase"]))
        core._apply_asi_score_delta(character, projection["feat_delta"], session.world_state)
        ac_delta = character[armor_class_ability + "_mod"] - old_ac_modifier if armor_class_ability else 0
        if ac_delta:
            # Choice admission checked the old canonical total, never guesses
            # whether inventory armor/shields are worn or contributing extras.
            character["armor_class"] += ac_delta
        session.character.clear()
        session.character.update(character)
        session.set_player_max_hp(projection["resulting_maximum"])
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        core.validate_saved(session.character, session.world_state)
        # Full canonical serialized admission follows combat synchronization.
        session._validate_save_payload(session.serialize_game_state())
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        _restore_format(session, captured)
        return core._reject("resulting_state_invalid")
    return {"status": "applied", "reason": None,
            "changes": [{"kind": "level", "from": 3, "to": 4},
                        {"kind": "hit_points", "gain": base},
                        {"kind": "maximum_hit_points", "gain": projection["retroactive_max_gain"]},
                        {"kind": "asi", "feat_delta": projection["feat_delta"]}],
            "effects_pending": list(preview["effects_pending"])}


def asi_consistency_problem(character: dict[str, Any], options: list[dict[str, Any]]) -> str | None:
    """Refusal reason when no offered ASI can be stored consistently with the retained origin scores."""
    if not options:
        return "no_supported_asi_choices"
    increase = options[0]["increase"]
    projected = core._project_selected_asi_hp(character, 4, {"increase": increase})
    context = core._score_context(character, saved=False)
    for change in projected["feat_delta"]["changes"]:
        context["scores"][change["ability"]] = change["to"]
    context.update(level=max(character["level"], 4), applied_level=4, asi_choices=core._selected_asi_record(increase))
    check = core._check_detached_asi_consistency(**context)
    return None if check["consistent"] else check["reason"]
