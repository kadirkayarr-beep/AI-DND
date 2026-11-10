"""Monk progression: earned and starting levels 1-5 with the selected Warrior of the Open Hand. Effects live in monk_features.

Facts are read from content/rules/phb2024/classes/monk.json. Shared helpers are read through `core.` at call time, because this
module loads while character_progression is still loading and tests patch names there (`table`, `validate_saved`, ...).
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
import monk_features as features
from class_progression import noncaster
from class_progression.base import ClassProgression
from weapon_catalog import WEAPONS

OPEN_HAND_SOURCE_KEY = "phb2024:subclass:monk:warrior-of-the-open-hand"
SUBCLASS_LEVEL = 3
FIRST_ASI_LEVEL = 4
LAST_LEVEL = 5
# Exact source rows through level 5 (Monk Features table, PDF 101): features, Proficiency Bonus, Martial Arts die, Focus Points, Unarmored Movement.
SOURCE_ROWS = {1: (["Martial Arts", "Unarmored Defense"], 2, 6, None, None),
               2: (["Monk's Focus", "Unarmored Movement", "Uncanny Metabolism"], 2, 6, 2, 10),
               3: (["Deflect Attacks", "Monk Subclass"], 2, 6, 3, 10),
               4: (["Ability Score Improvement", "Slow Fall"], 2, 6, 4, 10),
               5: (["Extra Attack", "Stunning Strike"], 3, 8, 5, 10)}
# Core traits, PDF 100: Simple weapons and Martial weapons that have the Light property.
WEAPON_GRANT = ("simple", *dict.fromkeys(weapon["weapon_id"] for weapon in WEAPONS.values()
                                         if weapon["category"] == "martial" and "light" in weapon["properties"]))


def _cell_ok(value: Any, wanted: int | None) -> bool:
    return value is None if wanted is None else type(value) is int and value == wanted


def _row_ok(row: Any, level: int) -> bool:
    """Exact source row: ints only (no bool), no caster keys; anything else hides the level."""
    features_row, bonus, die, focus, movement = SOURCE_ROWS[level]
    return (isinstance(row, dict) and row.get("features") == features_row
            and type(row.get("proficiency_bonus")) is int and row["proficiency_bonus"] == bonus
            and type(row.get("martial_arts_die")) is int and row["martial_arts_die"] == die
            and "focus_points" in row and _cell_ok(row["focus_points"], focus)
            and "unarmored_movement_ft" in row and _cell_ok(row["unarmored_movement_ft"], movement)
            and not any(key in row for key in ("slots", "cantrips", "prepared_spells")))


def _subclass_options() -> list[dict[str, str]] | None:
    source = core.table("Monk")
    entry = source.get("subclass_options", {}).get(OPEN_HAND_SOURCE_KEY) if isinstance(source, dict) else None
    name = entry.get("name") if isinstance(entry, dict) else None
    return [{"id": features.SUBCLASS, "name": name}] if type(name) is str and name else None


def _scope(level: int) -> dict[str, list[str]]:
    pending = core.progression_effects_pending("Monk", level)
    return {"effects_supported": core.progression_disclosure("Monk", level)["supported"],
            "effects_pending": pending + ([core.HIGHER_START_EQUIPMENT_PENDING] if level >= FIRST_ASI_LEVEL else [])}


def monk_starting_creation_options() -> dict[str, Any] | None:
    """Detached capability offered one verified row at a time: a bad row hides that level and everything above it."""
    source = core.table("Monk")
    levels = source.get("levels") if isinstance(source, dict) else None
    if (core._supported_level("Monk") < 2 or not isinstance(levels, dict)
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


def _canonical_ac(character: dict[str, Any]) -> int:
    return 10 + (character["dexterity"] - 10) // 2 + (character["wisdom"] - 10) // 2


def _wisdom_modifier_rises(option: dict[str, Any], character: dict[str, Any]) -> bool:
    amount = option["increase"].get("wisdom", 0)
    return (character["wisdom"] + amount - 10) // 2 != (character["wisdom"] - 10) // 2


def _asi_options(session) -> list[dict[str, Any]]:
    """A choice that moves the Wisdom modifier needs the canonical Unarmored Defense total, or AC could not follow it honestly."""
    character = session.character
    ac = character.get("armor_class")
    if type(ac) is not int or ac < 0:
        return []
    return [option for option in core.supported_asi_choices(character, session.world_state)
            if core._project_selected_asi_hp(character, FIRST_ASI_LEVEL, {"increase": option["increase"]})["status"] == "projected"
            and (not _wisdom_modifier_rises(option, character) or ac == _canonical_ac(character))]


def _prerequisite(session, target_level: int) -> str | None:
    character = session.character
    if "progression_level" in character and type(character["progression_level"]) is not int:
        return "previous_monk_state_invalid"
    if character.get("progression_level", 1) != target_level - 1:
        return "previous_level_choices_required"
    try:
        core.validate_saved(character, session.world_state)
        if target_level == FIRST_ASI_LEVEL:
            core._validate_con_caches(character)
            return noncaster.asi_consistency_problem(character, _asi_options(session))
    except (ValueError, KeyError, TypeError):
        return "previous_monk_state_invalid"
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


class Monk(ClassProgression):
    name = "Monk"
    supported_level = LAST_LEVEL
    selected_asi = True
    extra_attack_level = 5
    class_weapon_proficiencies = WEAPON_GRANT

    def progression_path_verified(self, character):
        return character.get("subclass_id") == features.SUBCLASS

    def validate_class_fields(self, player):
        features.validate_saved(player)

    def validate_state(self, player, world):
        progression = player.get("progression_level")
        if (any(key in world for key in ("spellcasting_v1", "sorcery_points_v1", "rage_v1")) or player.get("metamagic")
                or ("subclass_id" in player and (type(progression) is not int or progression < SUBCLASS_LEVEL
                                                 or player["subclass_id"] != features.SUBCLASS))):
            raise ValueError("Kayıt Monk için kazanılmamış büyü, Rage veya alt sınıf durumu içeriyor.")

    def validate_applied(self, player, world, applied):
        if (applied >= SUBCLASS_LEVEL) != ("subclass_id" in player):
            raise ValueError("Kayıt Monk alt sınıfı uygulanmış seviyeyle uyuşmuyor.")

    def validate_asi_storage(self, player, *, saved):
        context = core._score_context(player, saved=saved)
        prior = context["base_scores"]["wisdom"] + context["background_bonuses"].get("wisdom", 0)
        modifier_changed = (player["wisdom"] - 10) // 2 != (prior - 10) // 2
        ac = player.get("armor_class")
        if type(ac) is not int or ac < 0 or (modifier_changed and ac != _canonical_ac(player)):
            raise ValueError("Invalid selected Monk ASI armor class.")

    def disclosure(self, level, **_):
        return features.disclosure(level)

    def speed_bonus_ft(self, character, world):
        return features.movement_bonus_ft(character, world)

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
            return "selected_monk_subclass_required"
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
            return noncaster.apply_asi_step(session, preview, choices, armor_class_ability="wisdom")
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
        required = f"monk_level_{level}_choices_required"
        if type(level_choices) is not dict or set(level_choices) != wanted or any(type(v) is not dict for v in level_choices.values()):
            raise ValueError(required)
        shapes = {"2": set(), "3": {"subclass_id"}, "4": {"asi"}, "5": set()}
        if any(set(value) != shapes[key] for key, value in level_choices.items()):
            raise ValueError(required)


HANDLER = Monk()
