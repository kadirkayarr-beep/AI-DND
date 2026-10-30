"""Monk 1-5 feature rules on the existing owners; it holds rules and one small state record, not a budget or a resource system.

Values only (PHB 2024 PDF 100/101/102 class features, PDF 106 Warrior of the Open Hand).
`character["monk_state"]` = {"focus_spent", "metabolism_spent", "deflect"} is additive, like `hit_dice`: a save without it spent
nothing, and a counter (not a remaining value) makes table growth add points without refilling them.
Everything follows the APPLIED Monk level; a level granted by XP alone changes nothing here.
"""
from __future__ import annotations

import logging
from typing import Any

import character_progression as core
from api.dnd_2024_rules import CharacterCreationError, get_equipment_armor_and_shield

logger = logging.getLogger(__name__)

KEY = "monk_state"
SUBCLASS = "open_hand"
PROOF = "worn_armor_v1"
DEFLECT_MODES = ("off", "reduce", "redirect")
_FIELDS = {"focus_spent", "metabolism_spent", "deflect"}
FOCUS_LEVEL = 2
OPEN_HAND_LEVEL = 3
_DEFAULT = {"focus_spent": 0, "metabolism_spent": False, "deflect": "reduce"}


def monk_level(character: Any) -> int | None:
    """The applied Monk level, or None when this is not a verified Monk 1-5 (at 3+ the subclass choice must be retained)."""
    if not isinstance(character, dict) or character.get("class") != "Monk":
        return None
    applied, raw = character.get("progression_level", 1), character.get("level")
    if type(applied) is not int or type(raw) is not int or not 1 <= applied <= 5 or not applied <= raw <= 20:
        return None
    if applied >= OPEN_HAND_LEVEL and character.get("subclass_id") != SUBCLASS:
        return None
    return applied


def _cell(level: int, column: str) -> Any:
    try:
        return core.table("Monk")["levels"][str(level)][column]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Invalid Monk table value: {column}.") from error


def martial_arts_die(level: int) -> int:
    value = _cell(level, "martial_arts_die")
    if type(value) is not int or value < 2:
        raise ValueError("Invalid Martial Arts table value.")
    return value


def focus_maximum(level: int) -> int:
    value = _cell(level, "focus_points")
    if value is None:
        return 0
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Focus Points table value.")
    return value


def _movement_cell(level: int) -> int:
    value = _cell(level, "unarmored_movement_ft")
    if value is None:
        return 0
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Unarmored Movement table value.")
    return value


def validate_saved(player: dict[str, Any]) -> None:
    """Runs for every class on every save: the record exists only on a verified Monk, with counts its applied level allows."""
    if KEY not in player:
        return
    level, state = monk_level(player), player[KEY]
    if (level is None or type(state) is not dict or set(state) != _FIELDS
            or type(state["focus_spent"]) is not int or not 0 <= state["focus_spent"] <= focus_maximum(level)
            or type(state["metabolism_spent"]) is not bool or (state["metabolism_spent"] and level < FOCUS_LEVEL)
            or state["deflect"] not in DEFLECT_MODES):
        raise ValueError("Kayıt Monk durum alanı geçersiz.")


def state_of(character: dict[str, Any]) -> dict[str, Any]:
    return {**_DEFAULT, **(character.get(KEY) or {})}


def rest_recovery(session: Any, kind: str) -> None:
    """PDF 101: a finished Short or Long Rest regains all Focus Points; Uncanny Metabolism returns on a Long Rest. No record, nothing to do."""
    character = session.character
    if KEY not in character:
        return
    state = state_of(character)
    state["focus_spent"] = 0
    if kind == "long_rest":
        state["metabolism_spent"] = False
    character[KEY] = state


def initialize(session: Any, *, known_unarmored: bool) -> None:
    """Creation owner only: the same known-unarmored fact Barbarian's Rage owner records. Never adopted on load."""
    import barbarian_rage
    import equipment_economy
    if session.character.get("class") == "Monk" and known_unarmored and barbarian_rage._format(session) in (4, 5, 6):
        equipment_economy.initialize_unarmored_proof(session)


def unarmored(world: Any) -> bool:
    """Not wearing armor or wielding a Shield. The engine has no route to don either after creation, so the creation proof decides;
    a save without it (older than this slice) is read from what it carries, each time, and never written back."""
    if not isinstance(world, dict):
        return False
    proof = world.get(PROOF)
    if isinstance(proof, dict):
        return proof.get("armor_id") is None
    items = [item.get("name") if isinstance(item, dict) else item for item in world.get("inventory", [])]
    try:
        armor, shield = get_equipment_armor_and_shield([item for item in items if isinstance(item, str)])
    except CharacterCreationError:
        return False
    return armor is None and not shield


def monk_weapon(weapon: dict[str, Any]) -> bool:
    """PDF 100: Simple Melee weapons and Martial Melee weapons that have the Light property."""
    return weapon.get("kind") == "melee" and (weapon.get("category") == "simple"
                                              or (weapon.get("category") == "martial" and "light" in weapon.get("properties", [])))


def movement_bonus_ft(character: Any, world: Any) -> int:
    level = monk_level(character)
    return _movement_cell(level) if level is not None and unarmored(world) else 0


def martial_arts_ready(session: Any) -> bool:
    import weapon_attack as attacks
    data = session.character
    return (monk_level(data) is not None and unarmored(session.world_state)
            and all(monk_weapon(weapon) for weapon in attacks._held_weapon_profiles(session, "player", data)))


def disclosure(level: int) -> dict[str, list[str]]:
    supported = [f"Martial Arts die 1d{martial_arts_die(level)}"]
    pending = ["Other Monk subclasses and higher-level features remain unsupported"]
    return {"supported": supported, "pending": pending}


def projection(session: Any) -> dict[str, Any] | None:
    """The public block. Invalid saved state hides the controls, as Rage does, and leaves a log line; any other fault is a real error."""
    character = session.character
    try:
        level = monk_level(character)
        if level is None:
            return None
        validate_saved(character)
        state = state_of(character)
        maximum = focus_maximum(level)
        return {
            "martial_arts_die": martial_arts_die(level),
            "martial_arts_ready": martial_arts_ready(session),
            "movement_bonus_ft": movement_bonus_ft(character, session.world_state),
            "focus": None if level < FOCUS_LEVEL else {"points_remaining": maximum - state["focus_spent"], "max_points": maximum},
        }
    except ValueError as error:
        logger.warning("Monk controls hidden: %s", error)
        return None
