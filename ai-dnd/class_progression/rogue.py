"""Rogue progression: earned and starting levels 1-5 with the selected Assassin path. Effects live in rogue_features.

Facts are read from content/rules/phb2024/classes/rogue.json. Shared helpers are read through `core.` at call time, because this
module loads while character_progression is still loading and tests patch names there (`table`, `validate_saved`, ...).
"""
from __future__ import annotations

import copy
from typing import Any

import character_progression as core
import rogue_features as features
from class_progression import noncaster
from class_progression.base import ClassProgression

ASSASSIN_SOURCE_KEY = "phb2024:subclass:rogue:assassin"
SUBCLASS_LEVEL = 3
FIRST_ASI_LEVEL = 4
LAST_LEVEL = 5
ASSASSIN_TOOLS = ("Disguise Kit", "Poisoner's Kit")
# Exact source rows through level 5 (Rogue Features table, PDF 129): features, Proficiency Bonus, Sneak Attack d6.
SOURCE_ROWS = {1: (["Expertise", "Sneak Attack", "Thieves' Cant", "Weapon Mastery"], 2, 1),
               2: (["Cunning Action"], 2, 1),
               3: (["Rogue Subclass", "Steady Aim"], 2, 2),
               4: (["Ability Score Improvement"], 2, 2),
               5: (["Cunning Strike", "Uncanny Dodge"], 3, 3)}


def _row_ok(row: Any, level: int) -> bool:
    """Exact source row: ints only (no bool), no caster keys; anything else hides the level."""
    features_row, bonus, dice = SOURCE_ROWS[level]
    return (isinstance(row, dict) and row.get("features") == features_row
            and type(row.get("proficiency_bonus")) is int and row["proficiency_bonus"] == bonus
            and type(row.get("sneak_attack_dice")) is int and row["sneak_attack_dice"] == dice
            and type(row.get("sneak_attack_die")) is int and row["sneak_attack_die"] == features.SNEAK_DIE
            and not any(key in row for key in ("slots", "cantrips", "prepared_spells")))


def _subclass_options() -> list[dict[str, str]] | None:
    source = core.table("Rogue")
    entry = source.get("subclass_options", {}).get(ASSASSIN_SOURCE_KEY) if isinstance(source, dict) else None
    name = entry.get("name") if isinstance(entry, dict) else None
    return [{"id": features.SUBCLASS, "name": name}] if type(name) is str and name else None


def _scope(level: int) -> dict[str, list[str]]:
    pending = core.progression_effects_pending("Rogue", level)
    return {"effects_supported": core.progression_disclosure("Rogue", level)["supported"],
            "effects_pending": pending + ([core.HIGHER_START_EQUIPMENT_PENDING] if level >= FIRST_ASI_LEVEL else [])}


def rogue_starting_creation_options() -> dict[str, Any] | None:
    """Detached capability offered one verified row at a time: a bad row hides that level and everything above it."""
    source = core.table("Rogue")
    levels = source.get("levels") if isinstance(source, dict) else None
    if (core._supported_level("Rogue") < 2 or not isinstance(levels, dict)
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
    return [option for option in core.supported_asi_choices(character, session.world_state)
            if core._project_selected_asi_hp(character, FIRST_ASI_LEVEL, {"increase": option["increase"]})["status"] == "projected"]


def _prerequisite(session, target_level: int) -> str | None:
    character = session.character
    if "progression_level" in character and type(character["progression_level"]) is not int:
        return "previous_rogue_state_invalid"
    if character.get("progression_level", 1) != target_level - 1:
        return "previous_level_choices_required"
    try:
        core.validate_saved(character, session.world_state)
        if target_level == FIRST_ASI_LEVEL:
            core._validate_con_caches(character)
            return noncaster.asi_consistency_problem(character, _asi_options(session))
    except (ValueError, KeyError, TypeError):
        return "previous_rogue_state_invalid"
    return None


def _apply_three(session, preview):
    """Atomic level 3: unpaid Hit Points, the subclass and the Assassin's Tools (kit and proficiency, once each)."""
    snapshot = session._capture_runtime_snapshot()
    gain = 0 if preview["hit_points"]["already_applied"] else preview["hit_points"]["gain"]
    try:
        character = copy.deepcopy(session.character)
        character["max_hp"] += gain
        if character["current_hp"] > 0:
            character["current_hp"] += gain
        character.update(level=max(SUBCLASS_LEVEL, character["level"]), progression_level=SUBCLASS_LEVEL, subclass_id=features.SUBCLASS)
        character["proficiency_bonus"] = core.proficiency_bonus_for_level(character["level"])
        character["proficient_tools"] = list(dict.fromkeys([*character.get("proficient_tools", []), *ASSASSIN_TOOLS]))
        session.character.clear()
        session.character.update(character)
        inventory = session.world_state.setdefault("inventory", [])
        for kit in ASSASSIN_TOOLS:
            if not features.carries(session, kit):
                inventory.append(kit)
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


class Rogue(ClassProgression):
    name = "Rogue"
    supported_level = LAST_LEVEL
    selected_asi = True
    class_weapon_proficiencies = features.CLASS_WEAPONS

    def progression_path_verified(self, character):
        return character.get("subclass_id") == features.SUBCLASS

    def validate_class_fields(self, player):
        features.validate_saved(player)

    def validate_class_world(self, player, world):
        features.validate_world(player, world)

    def validate_state(self, player, world):
        progression = player.get("progression_level")
        if (any(key in world for key in ("spellcasting_v1", "sorcery_points_v1", "rage_v1")) or player.get("metamagic")
                or "fighter_uses" in player
                or ("subclass_id" in player and (type(progression) is not int or progression < SUBCLASS_LEVEL
                                                 or player["subclass_id"] != features.SUBCLASS))):
            raise ValueError("Kayıt Rogue için kazanılmamış büyü, Rage veya alt sınıf durumu içeriyor.")

    def validate_applied(self, player, world, applied):
        if (applied >= SUBCLASS_LEVEL) != ("subclass_id" in player):
            raise ValueError("Kayıt Rogue alt sınıfı uygulanmış seviyeyle uyuşmuyor.")

    def disclosure(self, level, **_):
        supported = [
            f"Sneak Attack: {features.sneak_dice(level)}d6 of the weapon's type, once per turn, on a Finesse or Ranged weapon hit with Advantage, "
            "or with an ally within 5 feet of the target and no Disadvantage; applied automatically to the first such hit of a turn",
            "Expertise: two proficient skills chosen at creation double the Proficiency Bonus",
            "Thieves' Cant and Thieves' Tools proficiency at creation",
            "Weapon proficiency: Simple weapons and Martial weapons with Finesse or Light",
        ]
        pending = [
            "Weapon Mastery: selections and effects remain pending (C10/C04)",
            "Thieves' Cant: the second language is the existing creation choice of two languages, not a separate class pick",
            "Rogue equipment packages are the existing catalog lists, not yet the PHB packages",
            "Sneak Attack: spell attack rolls never qualify and declining it is not offered",
        ]
        if level >= 2:
            supported.append("Cunning Action: Dash or Disengage as a Bonus Action on your own combat turn")
            pending.append("Cunning Action Hide remains pending: the engine has no line-of-sight, Heavily Obscured or Hide action owner")
            pending.append("Disengage: the engine has no Opportunity Attacks against the player's movement, so it spends the Bonus Action with no separate effect")
        if level >= 3:
            supported.extend([
                "Steady Aim: a Bonus Action before moving this turn gives Advantage on your next weapon attack roll this turn and sets your Speed to 0 until the turn ends",
                "Selected Assassin Assassinate: Advantage on Initiative; in the first round Advantage on attack rolls against a creature that has not taken a turn, and a Sneak Attack hit adds your Rogue level as damage of the weapon's type",
                "Selected Assassin's Tools: a Disguise Kit and a Poisoner's Kit with proficiency",
            ])
            pending.extend(["Steady Aim: a spell attack roll neither gains nor uses the Advantage",
                            "Disguise Kit and Poisoner's Kit have no craft or disguise routes yet",
                            "Other Rogue subclasses and higher-level features remain unsupported"])
        if level >= 4:
            supported.append("Selected level4 ordinary Ability Score Improvement supported, Dexterity included; a choice that moves the Dexterity modifier is refused only when the Armor Class total cannot be tied to its creation armor")
            pending.append("Other feats remain unsupported")
        if level >= 5:
            supported.extend([
                "Cunning Strike: one of Poison, Trip or Withdraw for 1d6 of the Sneak Attack, save DC 8 + DEX modifier + Proficiency Bonus; the Poison needs a carried Poisoner's Kit",
                "Uncanny Dodge: on by default, the Reaction halves (round down) the first attack that hits you from an attacker you can see; turn it off to keep the Reaction",
            ])
            pending.extend([
                "Cunning Strike is chosen before the attack roll, not after the hit; no die is paid when no Sneak Attack lands",
                "A readied Reaction attack can deal Sneak Attack but takes no Cunning Strike choice",
                "Cunning Strike on a Critical Hit: the die is forgone before the remaining dice are doubled; this is a reading, not stated",
                "Poison lasts at most the current combat; the minute is not tracked past its end",
                "Withdraw: the engine has no Opportunity Attacks against the player's movement, so 'without provoking' has no separate effect",
                "Uncanny Dodge is decided before the enemy turn, not at each hit, and never spends a Reaction held by Ready",
                "The turn text does not name Uncanny Dodge: the halved damage and the spent Reaction show in the numbers",
                "Cunning Strike Poison or Trip on a target already Poisoned or Prone applies nothing, and the die stays forgone",
                "Uncanny Dodge on a hit of several damage types: the total is halved before Resistance and the halved part leaves the types in listing order; this is a reading, not stated",
            ])
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
            return "selected_rogue_subclass_required"
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

    def validate_start_choices(self, level, level_choices):
        if level > LAST_LEVEL:
            raise ValueError("progression_level_not_supported")
        wanted = {str(n) for n in range(2, level + 1)}
        required = f"rogue_level_{level}_choices_required"
        if type(level_choices) is not dict or set(level_choices) != wanted or any(type(v) is not dict for v in level_choices.values()):
            raise ValueError(required)
        shapes = {"2": set(), "3": {"subclass_id"}, "4": {"asi"}, "5": set()}
        if any(set(value) != shapes[key] for key, value in level_choices.items()):
            raise ValueError(required)


HANDLER = Rogue()
