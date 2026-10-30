"""Barbarian progression: earned and starting levels 1-5 with the selected Berserker path.

Shared helpers are read through `core.` at call time: this module loads while character_progression is still loading, and
tests patch names on character_progression (`table`, `validate_saved`, ...), so those patches must reach this code.
"""
from __future__ import annotations

from typing import Any

import character_progression as core
from class_progression.base import ClassProgression


FAST_MOVEMENT_FT = 10  # Barbarian Fast Movement, features table level 5 (+10 ft Speed)
EXTRA_ATTACK_ATTACKS = 2  # Barbarian Extra Attack, features table level 5 (two attacks instead of one)


def barbarian_level_five_applied(character: Any) -> bool:
    """The only source of level-5 Barbarian features: applied level 5 of the selected Berserker.

    Cheap on purpose (Speed and attack allowance read it often); the retained choices behind it are admitted by `validate_saved`
    on every save, restore and level-up, so a numeric XP level 5 or a forged field never reaches here with a valid state.
    """
    return (isinstance(character, dict) and character.get("class") == "Barbarian"
            and type(character.get("level")) is int and type(character.get("progression_level")) is int
            and character["progression_level"] == 5 and character["level"] >= 5
            and character.get("subclass_id") == "berserker")


def fast_movement_bonus_ft(character: Any, world: Any) -> int:
    """Fast Movement: +10 ft Speed while not wearing Heavy armor.

    The engine has no general worn-armor owner. The only retained fact is the Barbarian `worn_armor_v1` proof: `armor_id` None is
    the verified unarmored state. A named suit is read from the existing PHB armor table (Heavy => no bonus); a missing proof or an
    unknown armor cannot be verified as non-Heavy, so no bonus is granted (honest under-grant, never an invented armor state).
    """
    if not barbarian_level_five_applied(character) or not isinstance(world, dict):
        return 0
    proof = world.get("worn_armor_v1")
    if type(proof) is not dict or "armor_id" not in proof:
        return 0
    armor = proof["armor_id"]
    if armor is None:
        return FAST_MOVEMENT_FT
    if type(armor) is not str:
        return 0
    from api.dnd_2024_rules import ARMOR_CLASS_RULES, ARMOR_NAME_ALIASES
    rule = ARMOR_CLASS_RULES.get(ARMOR_NAME_ALIASES.get(armor, armor))
    return FAST_MOVEMENT_FT if rule is not None and rule["category"] in ("light", "medium") else 0


class Barbarian(ClassProgression):
    name = "Barbarian"
    supported_level = 5
    selected_asi = True

    def disclosure(self, level, *, rage_adopted=None, **_):
        supported, pending = [], []
        if rage_adopted is False:
            pending.append("Rage unavailable: this saved character has no verified unarmored Rage state; legacy state is not automatically adopted")
        else:
            supported.append(f"Rage: known-unarmored Barbarian {'1–2' if level <= 2 else '1–3' if level == 3 else '1–4' if level == 4 else '1–5'} combat Bonus activation/extension, supported attack/check/save/resistance routes and rest recovery; verified adopted state required")
        pending.append("Weapon Mastery: selections and effects remain pending (C10/C04)")
        pending.append("General armor changes and broader Unarmored Defense routes remain unsupported")
        if level >= 4:
            supported.append("Selected level4 ordinary non-DEX Ability Score Improvement supported")
            pending.append("CON modifier-changing ASI requires canonical unarmored AC (10 + DEX + CON modifiers); shield or unexplained AC extras remain unsupported for those choices")
            pending.append("Level4 third Weapon Mastery selection and effects remain pending (C10/C04)")
        if level >= 2:
            supported.extend(["Reckless Attack: explicit first own-turn attack choice and canonical advantage window supported",
                              "Danger Sense: weapon/unarmed Dexterity-save route supported"])
            pending.append("Danger Sense: other save routes remain pending (C10)")
        if level >= 3:
            supported.extend(["Selected Berserker Frenzy: first eligible own-turn Strength hit after Reckless while raging; 2d6 extra damage",
                              "Primal Knowledge: one additional class skill proficiency supported",
                              "Primal Knowledge: explicit optional Strength for selected untargeted immediate Acrobatics, Intimidation, Perception, Stealth or Survival checks while Rage is active"])
            pending.append("Primal Knowledge: Strength substitution in targeted commands, timed tasks, tracking, travel, active combat and model-only check routes remains unsupported (engine scope, not a PHB restriction)")
            pending.append("Other Barbarian subclasses and higher-level features remain unsupported")
        if level >= 5:
            supported.extend(["Extra Attack: an applied level-5 Barbarian makes two attacks instead of one when taking the Attack action on their own turn (existing attacks-per-Action allowance)",
                              "Fast Movement: +10 ft Speed while the verified unarmored state is retained (the bonus never applies in Heavy armor)"])
            pending.extend(["Fast Movement: general worn-armor tracking is unavailable; without the verified unarmored state no bonus is granted",
                            "Other extra-Action attack grants keep their own attack limit; Extra Attack does not raise them"])
        return {"supported": supported, "pending": pending}

    def adoption(self, world):
        return {"rage_adopted": "rage_v1" in world}

    def attacks_per_attack_action(self, character):
        return EXTRA_ATTACK_ATTACKS if barbarian_level_five_applied(character) else 1

    def speed_bonus_ft(self, character, world):
        return fast_movement_bonus_ft(character, world)


HANDLER = Barbarian()
