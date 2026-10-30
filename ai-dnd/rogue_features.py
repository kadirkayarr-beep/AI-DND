"""Rogue 1-5 feature effects on the existing owners; it holds rules, not a budget or a resource system.

Values only (PHB 2024 PDF 128 Sneak Attack, PDF 129 Cunning Action, Steady Aim, Cunning Strike, PDF 130 Withdraw, Uncanny Dodge, PDF 133
Assassin). Every number follows the APPLIED Rogue level; a level granted by XP alone changes nothing here.
"""
from __future__ import annotations

import logging
from typing import Any

import character_progression as core
from combat_lifecycle import CombatRequestError
from weapon_catalog import WEAPONS

logger = logging.getLogger(__name__)

SUBCLASS = "assassin"
SUBCLASS_LEVEL = 3
SNEAK_DIE = 6
UNCANNY_OFF = "uncanny_dodge_off"  # present only when the player turned Uncanny Dodge off, so older saves need nothing
CUNNING_ACTION_LEVEL = 2
STEADY_AIM_LEVEL = 3
CUNNING_STRIKE_LEVEL = 5
UNCANNY_DODGE_LEVEL = 5
# Simple weapons, and Martial weapons that have the Finesse or Light property.
CLASS_WEAPONS = ("simple", *sorted({weapon["weapon_id"] for weapon in WEAPONS.values() if weapon["category"] == "martial"
                                    and {"finesse", "light"} & set(weapon["properties"])}))


def rogue_level(character: Any) -> int | None:
    """The applied Rogue level, or None when this is not a verified Rogue 1-5 (at 3+ the Assassin choice must be retained)."""
    if not isinstance(character, dict) or character.get("class") != "Rogue":
        return None
    applied, raw = character.get("progression_level", 1), character.get("level")
    if type(applied) is not int or type(raw) is not int or not 1 <= applied <= 5 or not applied <= raw <= 20:
        return None
    if applied >= SUBCLASS_LEVEL and character.get("subclass_id") != SUBCLASS:
        return None
    return applied


def sneak_dice(level: int) -> int:
    try:
        value = core.table("Rogue")["levels"][str(level)]["sneak_attack_dice"]
    except (KeyError, TypeError) as error:
        raise ValueError("Invalid Sneak Attack table value.") from error
    if type(value) is not int or value < 1:
        raise ValueError("Invalid Sneak Attack table value.")
    return value


def carries(session: Any, item: str) -> bool:
    import equipment_economy
    return item in equipment_economy.labels(session.world_state.get("inventory", []))


def validate_saved(player: dict[str, Any]) -> None:
    """Runs for every class on every save: the field exists only on a verified Rogue with the feature applied."""
    if UNCANNY_OFF not in player:
        return
    level = rogue_level(player)
    if level is None or level < UNCANNY_DODGE_LEVEL or player[UNCANNY_OFF] is not True:
        raise ValueError("Kayıt Uncanny Dodge alanı geçersiz.")


def validate_world(player: dict[str, Any], world: dict[str, Any]) -> None:
    """Rogue records inside combat state; other classes never read them."""


def projection_of(session: Any) -> dict[str, Any]:
    level = rogue_level(session.character)
    return {"steady_aim": False, "uncanny_dodge": None, "level": level}
