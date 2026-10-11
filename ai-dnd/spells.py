"""Bounded Spells V1 mechanics.

Python owns whether a known spell can be cast, what it rolls, and whether a
slot is spent. This registry is not the character-creation flavor catalog.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from api.dnd_2024_rules import CLASS_DEFINITIONS, SPELLS_CATALOG


SPELLS = {
    "Fire Bolt": {
        "id": "Fire Bolt",
        "level": 0,
        "min_level": 1,
        "classes": ("Wizard", "Sorcerer"),
        "kind": "spell_attack",
        "damage_die": 10,
        "damage_dice": 1,
        "uses_slot": False,
        "aliases": ("fire bolt", "ates oku", "atesoku"),
    },
    "Sacred Flame": {
        "id": "Sacred Flame",
        "level": 0,
        "min_level": 1,
        "classes": ("Cleric",),
        "kind": "saving_throw",
        "save_ability": "dexterity",
        "damage_die": 8,
        "damage_dice": 1,
        "uses_slot": False,
        "aliases": ("sacred flame", "kutsal alev"),
    },
    "Magic Missile": {
        "id": "Magic Missile",
        "level": 1,
        "min_level": 1,
        "classes": ("Wizard", "Sorcerer"),
        "kind": "automatic",
        "missile_count": 3,
        "missile_die": 4,
        "missile_bonus": 1,
        "uses_slot": True,
        "aliases": ("magic missile", "sihirli fuze", "sihirli fuzeler"),
    },
    "Cure Wounds": {
        "id": "Cure Wounds",
        "level": 1,
        "min_level": 1,
        "classes": ("Cleric", "Druid"),
        "kind": "healing",
        "heal_die": 8,
        "heal_dice": 2,
        "uses_slot": True,
        "aliases": ("cure wounds", "yara iyilestirme"),
    },
}

_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "i": "i",
    "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
    "â": "a", "î": "i", "û": "u",
})
_CAST_VERB = re.compile(
    r"\b(?:cast|buyu\s+yap\w*|buyusu\w*)\b",
)
_SELF_TARGET = re.compile(r"\b(?:kendime|kendimi|myself)\b")


def fold_text(value: str) -> str:
    text = str(value).casefold().replace("\u0307", "")
    return text.translate(_FOLD)


def initial_slots(character_class: str) -> dict[str, int]:
    """Level-1 slots granted at character creation. Non-casters get zero."""
    definition = CLASS_DEFINITIONS.get(character_class) or {}
    raw = definition.get("spell_slots") or {}
    count = raw.get("1", raw.get(1, 0))
    if type(count) is not int or isinstance(count, bool):
        count = 0
    return {"1": max(0, count)}


def empty_spell_state() -> dict[str, Any]:
    return {
        "cantrips": [],
        "spells": [],
        "spell_slots_remaining": {"1": 0},
    }


def remaining_slots(character: dict[str, Any]) -> int:
    slots = character.get("spell_slots_remaining")
    if not isinstance(slots, dict):
        return 0
    count = slots.get("1", 0)
    if type(count) is not int or isinstance(count, bool) or count < 0:
        return 0
    return count


def validate_saved_spell_fields(player: dict[str, Any]) -> None:
    """Reject a version-4 player record whose spell fields are not canonical."""
    for key in ("cantrips", "spells"):
        values = player.get(key)
        if (
            not isinstance(values, list)
            or any(
                not isinstance(item, str) or not item.strip() or len(item) > 80
                for item in values
            )
            or len(values) != len(set(values))
        ):
            raise ValueError("Kayıt büyü listesi geçersiz.")
    slots = player.get("spell_slots_remaining")
    if (
        not isinstance(slots, dict)
        or set(slots) != {"1"}
        or type(slots.get("1")) is not int
        or isinstance(slots.get("1"), bool)
        or not 0 <= slots["1"] <= 20
    ):
        raise ValueError("Kayıt büyü yuvası geçersiz.")


def casting_profile(character: dict[str, Any]) -> dict[str, Any] | None:
    definition = CLASS_DEFINITIONS.get(str(character.get("class", ""))) or {}
    ability = definition.get("spellcasting_ability")
    if not isinstance(ability, str):
        return None
    modifier = character.get(f"{ability}_mod")
    if type(modifier) is not int or isinstance(modifier, bool):
        modifiers = character.get("modifiers")
        if isinstance(modifiers, dict) and type(modifiers.get(ability)) is int:
            modifier = modifiers[ability]
        else:
            modifier = 0
    proficiency = character.get("proficiency_bonus", 0)
    if type(proficiency) is not int or isinstance(proficiency, bool):
        proficiency = 0
    return {
        "ability": ability,
        "modifier": modifier,
        "attack_bonus": proficiency + modifier,
        "save_dc": 8 + proficiency + modifier,
    }


def _unsupported_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for groups in SPELLS_CATALOG.values():
        if not isinstance(groups, dict):
            continue
        for entries in groups.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                spell_id = entry.get("id")
                if not isinstance(spell_id, str) or spell_id in SPELLS:
                    continue
                aliases[fold_text(spell_id)] = spell_id
                label = entry.get("name_tr")
                if isinstance(label, str) and label.strip():
                    short = label.split("(", 1)[0].strip()
                    if short:
                        aliases.setdefault(fold_text(short), spell_id)
    return aliases


_UNSUPPORTED = _unsupported_aliases()
_V1_ALIASES = sorted(
    (
        (fold_text(alias), spell_id)
        for spell_id, spell in SPELLS.items()
        for alias in (spell_id, *spell["aliases"])
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)
_UNSUPPORTED_ALIASES = sorted(_UNSUPPORTED.items(), key=lambda item: len(item[0]), reverse=True)


def _alias_in_text(folded: str, alias: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", folded) is not None


def classify_cast_phrase(player_input: str) -> dict[str, str] | None:
    """Return a cast classification when the player used a casting verb.

    A match is deterministic. The model must not relabel it as a weapon attack.
    """
    folded = fold_text(player_input)
    if not _CAST_VERB.search(folded):
        return None
    for alias, spell_id in _V1_ALIASES:
        if _alias_in_text(folded, alias):
            return {"kind": "v1", "spell_id": spell_id}
    for alias, spell_id in _UNSUPPORTED_ALIASES:
        if _alias_in_text(folded, alias):
            return {"kind": "unsupported", "spell_id": spell_id}
    return {"kind": "unknown", "spell_id": ""}


def targets_self(player_input: str) -> bool:
    return _SELF_TARGET.search(fold_text(player_input)) is not None


def legality(character: dict[str, Any], spell_id: str) -> str | None:
    """Return a rejection outcome, or None when the spell may be resolved."""
    spell = SPELLS[spell_id]
    known_key = "cantrips" if spell["level"] == 0 else "spells"
    known = character.get(known_key)
    if not isinstance(known, list) or spell_id not in known:
        return "not_known"
    if character.get("class") not in spell["classes"]:
        return "invalid_class"
    level = character.get("level", 1)
    if type(level) is not int or isinstance(level, bool) or level < spell["min_level"]:
        return "invalid_level"
    if spell["uses_slot"] and remaining_slots(character) < 1:
        return "no_slot"
    return None


def spend_slot(character: dict[str, Any]) -> None:
    slots = character.setdefault("spell_slots_remaining", {"1": 0})
    slots["1"] = remaining_slots(character) - 1


def roll_dice(roll: Callable[[int], int], sides: int, count: int) -> int:
    return sum(roll(sides) for _ in range(count))
