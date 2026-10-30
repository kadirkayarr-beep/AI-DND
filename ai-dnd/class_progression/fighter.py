"""Fighter progression: earned and starting levels 1-5 with the selected Champion path. Effects live in fighter_features.

Facts are read from content/rules/phb2024/classes/fighter.json. Shared helpers are read through `core.` at call time, because this
module loads while character_progression is still loading and tests patch names there (`table`, `validate_saved`, ...).
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
import fighter_features as features
from class_progression import noncaster
from class_progression.base import ClassProgression

CHAMPION_SOURCE_KEY = "phb2024:subclass:fighter:champion"
SUBCLASS_LEVEL = 3
FIRST_ASI_LEVEL = 4
LAST_LEVEL = 5
MASTERY_PENDING = "Weapon Mastery: selections and effects remain pending (C10/C04)"
# Exact source rows through level 5 (Fighter Features table, PDF 91): features, Proficiency Bonus, Second Wind, Weapon Mastery.
SOURCE_ROWS = {1: (["Fighting Style", "Second Wind", "Weapon Mastery"], 2, 2, 3),
               2: (["Action Surge (one use)", "Tactical Mind"], 2, 2, 3),
               3: (["Fighter Subclass"], 2, 2, 3),
               4: (["Ability Score Improvement"], 2, 3, 4),
               5: (["Extra Attack", "Tactical Shift"], 3, 3, 4)}


def _row_ok(row: Any, level: int) -> bool:
    """Exact source row: ints only (no bool), no caster keys; anything else hides the level."""
    features_row, bonus, wind, mastery = SOURCE_ROWS[level]
    return (isinstance(row, dict) and row.get("features") == features_row
            and type(row.get("proficiency_bonus")) is int and row["proficiency_bonus"] == bonus
            and type(row.get("second_wind")) is int and row["second_wind"] == wind
            and type(row.get("weapon_mastery")) is int and row["weapon_mastery"] == mastery
            and not any(key in row for key in ("slots", "cantrips", "prepared_spells")))


def _subclass_options() -> list[dict[str, str]] | None:
    source = core.table("Fighter")
    entry = source.get("subclass_options", {}).get(CHAMPION_SOURCE_KEY) if isinstance(source, dict) else None
    name = entry.get("name") if isinstance(entry, dict) else None
    return [{"id": features.SUBCLASS, "name": name}] if type(name) is str and name else None


def _scope(level: int) -> dict[str, list[str]]:
    pending = core.progression_effects_pending("Fighter", level)
    return {"effects_supported": core.progression_disclosure("Fighter", level)["supported"],
            "effects_pending": pending + ([core.HIGHER_START_EQUIPMENT_PENDING] if level >= FIRST_ASI_LEVEL else [])}


def fighter_starting_creation_options() -> dict[str, Any] | None:
    """Detached capability offered one verified row at a time: a bad row hides that level and everything above it."""
    source = core.table("Fighter")
    levels = source.get("levels") if isinstance(source, dict) else None
    if (core._supported_level("Fighter") < 2 or not isinstance(levels, dict)
            or not _row_ok(levels.get("1"), 1) or not _row_ok(levels.get("2"), 2)):
        return None
    result: dict[str, Any] = {"supported_starting_levels": [1, 2], "level_2": {"choices": {}, **_scope(2)}}
    subclasses = _subclass_options()
    if not subclasses or not _row_ok(levels.get("3"), 3):
        return result
    result["supported_starting_levels"].append(3)
    result["level_3"] = {"subclass_options": subclasses, **_scope(3)}
    asi = core.supported_asi_choices()
    if not asi or not _row_ok(levels.get("4"), 4):
        return result
    result["supported_starting_levels"].append(4)
    result["level_4"] = {"supported_asi_choices": asi, **_scope(4)}
    if _row_ok(levels.get("5"), 5):
        result["supported_starting_levels"].append(5)
        result["level_5"] = _scope(5)
    return result


def _asi_options(session) -> list[dict[str, Any]]:
    character = session.character
    return [option for option in core.supported_asi_choices(character)
            if core._project_selected_asi_hp(character, FIRST_ASI_LEVEL, {"increase": option["increase"]})["status"] == "projected"]


def _prerequisite(session, target_level: int) -> str | None:
    character = session.character
    if "progression_level" in character and type(character["progression_level"]) is not int:
        return "previous_fighter_state_invalid"
    if character.get("progression_level", 1) != target_level - 1:
        return "previous_level_choices_required"
    try:
        core.validate_saved(character, session.world_state)
        if target_level == FIRST_ASI_LEVEL:
            core._validate_con_caches(character)
            return noncaster.asi_consistency_problem(character, _asi_options(session))
    except (ValueError, KeyError, TypeError):
        return "previous_fighter_state_invalid"
    return None


def _apply_three(session, preview):
    snapshot = session._capture_runtime_snapshot()
    gain = 0 if preview["hit_points"]["already_applied"] else preview["hit_points"]["gain"]
    try:
        character = copy.deepcopy(session.character)
        character["max_hp"] += gain
        if character["current_hp"] > 0:
            character["current_hp"] += gain
        character.update(level=max(SUBCLASS_LEVEL, character["level"]), progression_level=SUBCLASS_LEVEL, subclass_id=features.SUBCLASS)
        character["proficiency_bonus"] = core.proficiency_bonus_for_level(character["level"])
        session.character.clear()
        session.character.update(character)
        combat = session.world_state.get("combat", {})
        if combat.get("active"):
            session._sync_combat_participant_records(combat)
        core.validate_saved(session.character, session.world_state)
        session._player_state_for_save()
    except Exception:
        session._restore_runtime_snapshot(snapshot)
        return core._reject("resulting_state_invalid")
    return {"status": "applied", "reason": None, "changes": [
        {"kind": "level", "from": 2, "to": 3}, {"kind": "hit_points", "gain": gain}, {"kind": "subclass", "id": features.SUBCLASS}],
        "effects_pending": list(preview["effects_pending"])}


class Fighter(ClassProgression):
    name = "Fighter"
    supported_level = LAST_LEVEL
    selected_asi = True
    extra_attack_level = 5

    def progression_path_verified(self, character):
        return character.get("subclass_id") == features.SUBCLASS

    def validate_class_fields(self, player):
        features.validate_saved(player)

    def validate_state(self, player, world):
        progression = player.get("progression_level")
        if (any(key in world for key in ("spellcasting_v1", "sorcery_points_v1", "rage_v1")) or player.get("metamagic")
                or ("subclass_id" in player and (type(progression) is not int or progression < SUBCLASS_LEVEL
                                                 or player["subclass_id"] != features.SUBCLASS))):
            raise ValueError("Kayıt Fighter için kazanılmamış büyü, Rage veya alt sınıf durumu içeriyor.")

    def validate_applied(self, player, world, applied):
        if (applied >= SUBCLASS_LEVEL) != ("subclass_id" in player):
            raise ValueError("Kayıt Fighter alt sınıfı uygulanmış seviyeyle uyuşmuyor.")

    def disclosure(self, level, **_):
        supported = [
            f"Second Wind: {features.second_wind_maximum(level)} uses, Bonus Action on your own combat turn or outside combat, "
            f"1d10 + Fighter level Hit Points; one use back on a Short Rest, all on a Long Rest",
            "Fighting Style: Archery, Defense, Dueling, Great Weapon Fighting and Two-Weapon Fighting apply; Defense is the creation Armor Class total",
        ]
        pending = [
            MASTERY_PENDING,
            "Fighting Style: replacing the feat on a Fighter level, Protection (a kept legacy choice has no effect) and the feats not offered remain pending",
            "Dueling: a thrown Melee weapon keeps the bonus; the source sets no melee attack limit, but this is a reading, not stated",
            "Fighter equipment packages are the existing catalog lists, not yet the PHB packages",
            "Weapon proficiency: a Fighter created before this change keeps its stored proficiency list; it is not inferred on load",
        ]
        if level >= 2:
            supported.append("Action Surge: one additional non-Magic action on your own combat turn, one use back on a Short or Long Rest")
            supported.append("Tactical Mind: shares the Second Wind uses; chosen before an immediate untargeted Do check, a failed check adds 1d10 and only a check that then succeeds spends the use")
            pending.append("Tactical Mind: choosing after seeing the failure, combat checks, targeted, timed and model-only check routes remain unsupported (engine scope, not a PHB restriction)")
        if level >= 3:
            supported.extend(["Selected Champion Improved Critical: a weapon or Unarmed Strike attack roll of 19 that hits is a Critical Hit",
                              "Selected Champion Remarkable Athlete: Advantage on Initiative and Strength (Athletics) checks"])
            pending.extend(["Improved Critical: a 19 must still meet the target's Armor Class; only a 20 is stated to hit regardless",
                            "Remarkable Athlete: the half-Speed move after a Critical Hit remains pending",
                            "Other Fighter subclasses and higher-level features remain unsupported"])
        if level >= 4:
            supported.append("Selected level4 ordinary non-DEX Ability Score Improvement supported")
            pending.append("Level4 fourth Weapon Mastery selection and effects remain pending (C10/C04)")
            pending.append("DEX Ability Score Improvement and other feats remain unsupported")
        if level >= 5:
            supported.extend(["Extra Attack: an applied level-5 Fighter makes two attacks instead of one when taking the Attack action on their own turn, including an Attack action taken with Action Surge",
                              "Tactical Shift: Second Wind with a Bonus Action can move up to half your Speed in the same step"])
            pending.append("Tactical Shift: the engine has no Opportunity Attacks against the player's movement, so 'without provoking' has no separate effect")
        return {"supported": supported, "pending": pending}

    def level_prerequisite(self, session, target_level):
        return _prerequisite(session, target_level)

    def choices_required(self, character, current, target_level, prior, goal):
        if target_level == SUBCLASS_LEVEL:
            return {"subclass_id": 1}
        return {"asi": 1} if target_level == FIRST_ASI_LEVEL else {}

    def preview_options(self, session, target_level):
        if target_level == SUBCLASS_LEVEL:
            return {"subclass_options": _subclass_options() or []}
        if target_level == FIRST_ASI_LEVEL:
            return {"supported_asi_choices": _asi_options(session)}
        return {}

    def check_choices(self, session, preview, choices):
        required = preview["choices_required"]
        if set(choices) != set(required):
            return "choices_required"
        if preview["to_level"] == SUBCLASS_LEVEL and not any(option["id"] == choices["subclass_id"] for option in preview["subclass_options"]):
            return "selected_fighter_subclass_required"
        if "asi" in required:
            asi = choices["asi"]
            if (type(asi) is not dict or set(asi) != {"feat", "increase"} or asi["feat"] != "Ability Score Improvement"
                    or not core._supported_asi_increase(asi["increase"])):
                return "selected_asi_not_supported"
            if asi not in _asi_options(session):
                return "asi_choice_not_eligible"
        return None

    def apply_level(self, session, preview, choices):
        target = preview["to_level"]
        if target == SUBCLASS_LEVEL:
            return _apply_three(session, preview)
        if target == FIRST_ASI_LEVEL:
            return noncaster.apply_asi_step(session, preview, choices)
        if target == LAST_LEVEL:
            return noncaster.apply_earned_final_step(session, preview)
        return noncaster.apply_plain_step(session, preview)

    def prepare_rest(self, session):
        features.validate_saved(session.character)

    def rest_recovery(self, session, kind):
        features.rest_recovery(session, kind)

    def validate_start_choices(self, level, level_choices):
        if level > LAST_LEVEL:
            raise ValueError("progression_level_not_supported")
        wanted = {str(n) for n in range(2, level + 1)}
        required = f"fighter_level_{level}_choices_required"
        if type(level_choices) is not dict or set(level_choices) != wanted or any(type(v) is not dict for v in level_choices.values()):
            raise ValueError(required)
        shapes = {"2": set(), "3": {"subclass_id"}, "4": {"asi"}, "5": set()}
        if any(set(value) != shapes[key] for key, value in level_choices.items()):
            raise ValueError(required)


HANDLER = Fighter()
