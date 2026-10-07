"""Tier 1 experience from the 2024 Player's Handbook.

Python owns the total, the level, and the hit-point gain. Narration and the
client cannot grant experience. Levels stop at 4; experience past that
threshold is kept and does not open Tier 2.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from quest_catalog import find_quest


MAX_LEVEL = 4
PROFICIENCY_BONUS = 2
MAX_GRANT = 100_000
MAX_STORED_XP = 1_000_000_000
MAX_AWARD_IDS = 500

# Character Advancement table, levels 1–4. Level 5 (6,500 XP, proficiency +3)
# is the start of Tier 2 and is intentionally not applied.
LEVEL_THRESHOLDS = (
    (1, 0),
    (2, 300),
    (3, 900),
    (4, 2700),
)

# Fixed Hit Points by Class, added on each level after 1.
FIXED_HP_BY_CLASS = {
    "Barbarian": 7,
    "Fighter": 6,
    "Paladin": 6,
    "Ranger": 6,
    "Bard": 5,
    "Cleric": 5,
    "Druid": 5,
    "Monk": 5,
    "Rogue": 5,
    "Warlock": 5,
    "Sorcerer": 4,
    "Wizard": 4,
}

_AWARD_ID = re.compile(r"^(quest|combat):\S{1,180}$")
_DEFEATED = frozenset({"unconscious", "defeated", "dead"})


def level_for_xp(xp: int) -> int:
    """Return the Tier 1 level for a stored experience total."""
    level = 1
    for candidate, threshold in LEVEL_THRESHOLDS:
        if xp >= threshold:
            level = candidate
    return level


def _constitution_modifier(character: Mapping[str, Any]) -> int:
    score = character.get("constitution")
    if type(score) is int:
        return (score - 10) // 2
    modifier = character.get("constitution_mod")
    if type(modifier) is int:
        return modifier
    return 0


def hit_point_gain(character: Mapping[str, Any]) -> int:
    """Fixed class value plus Constitution, minimum 1, then species and feat."""
    class_name = character.get("class")
    fixed = FIXED_HP_BY_CLASS.get(class_name)
    if fixed is None:
        raise ValueError("Level-up hit points require a known class.")
    gain = max(1, fixed + _constitution_modifier(character))
    if character.get("species") == "Dwarf" or character.get("race") == "Dwarf":
        gain += 1
    if character.get("origin_feat") == "Tough":
        gain += 2
    return gain


def _award_ids(world: dict[str, Any]) -> list[str]:
    ids = world.get("xp_awarded_event_ids")
    if not isinstance(ids, list):
        ids = []
        world["xp_awarded_event_ids"] = ids
    return ids


def apply_xp(character: dict[str, Any], world: dict[str, Any], amount: int, event_id: str):
    """Grant one experience award and apply every crossed level through 4.

    Returns a summary, or None when the event was already paid or the amount
    is not a positive server grant. The award id is recorded only after the
    character can accept the grant.
    """
    if not isinstance(character, dict) or not isinstance(world, dict):
        return None
    if not isinstance(event_id, str) or _AWARD_ID.fullmatch(event_id) is None:
        return None
    ids = _award_ids(world)
    if event_id in ids or len(ids) >= MAX_AWARD_IDS:
        return None
    if type(amount) is not int or amount <= 0 or amount > MAX_GRANT:
        return None

    previous = character.get("level")
    if type(previous) is not int or previous < 1:
        previous = 1
    previous = min(previous, MAX_LEVEL)
    current_xp = character.get("xp")
    if type(current_xp) is not int or current_xp < 0:
        current_xp = 0
    new_xp = current_xp + amount
    if new_xp > MAX_STORED_XP:
        return None

    target = level_for_xp(new_xp)
    level = previous
    gains: list[int] = []
    while level < target and level < MAX_LEVEL:
        gains.append(hit_point_gain(character))
        level += 1

    ids.append(event_id)
    character["xp"] = new_xp
    hit_points_gained = 0
    max_hp = character.get("max_hp")
    current_hp = character.get("current_hp")
    if type(max_hp) is not int:
        max_hp = 0
    if type(current_hp) is not int:
        current_hp = 0
    for gain in gains:
        max_hp += gain
        current_hp += gain
        hit_points_gained += gain
    character["max_hp"] = max_hp
    character["current_hp"] = current_hp
    character["level"] = level
    character["proficiency_bonus"] = PROFICIENCY_BONUS
    return {
        "previous_level": previous,
        "new_level": level,
        "xp_gained": amount,
        "hit_points_gained": hit_points_gained,
    }


def _is_defeated(npc: Mapping[str, Any]) -> bool:
    if npc.get("combat_status") in _DEFEATED:
        return True
    current_hp = npc.get("current_hp")
    return type(current_hp) is int and current_hp <= 0


def award_defeated_combat(combat: Mapping[str, Any], world: dict[str, Any], character: dict[str, Any]):
    """Pay server-authored creature rewards when an encounter ends in defeat.

    The caller must still have the participant list. Leaving, or the player
    falling unconscious, is not this function's job and pays nothing.
    """
    if not isinstance(combat, dict) or not isinstance(world, dict):
        return None
    participants = combat.get("participants")
    npcs = world.get("npcs")
    if not isinstance(participants, list) or not isinstance(npcs, list):
        return None
    by_id = {
        npc.get("id"): npc
        for npc in npcs
        if isinstance(npc, dict) and isinstance(npc.get("id"), str)
    }
    rewarded: list[str] = []
    total = 0
    for participant_id in participants:
        if not isinstance(participant_id, str) or participant_id == "player":
            continue
        npc = by_id.get(participant_id)
        if not isinstance(npc, dict) or not _is_defeated(npc):
            continue
        reward = npc.get("xp_reward")
        if type(reward) is not int or reward <= 0 or reward > MAX_GRANT:
            continue
        total += reward
        rewarded.append(participant_id)
    if total <= 0:
        return None
    flags = world.get("flags")
    turn = flags.get("turn_index", 0) if isinstance(flags, dict) else 0
    if type(turn) is not int or turn < 0:
        turn = 0
    event_id = f"combat:{turn}:{','.join(sorted(rewarded))}"
    return apply_xp(character, world, total, event_id)


def award_completed_quest(world: dict[str, Any], character: dict[str, Any], quest_id: str):
    """Pay the catalog's xp field once when that quest first completes."""
    if not isinstance(quest_id, str) or not quest_id.strip():
        return None
    definition = find_quest(quest_id)
    if definition is None:
        return None
    amount = definition.get("xp")
    if type(amount) is not int or amount <= 0 or amount > MAX_GRANT:
        return None
    return apply_xp(character, world, amount, f"quest:{quest_id}")


def validate_saved_advancement(player: Mapping[str, Any], world: Mapping[str, Any]) -> None:
    """Reject a version-5 save whose experience does not match its level."""
    xp = player.get("xp")
    if type(xp) is not int or xp < 0 or xp > MAX_STORED_XP:
        raise ValueError("Kayıt deneyim puanı geçersiz.")
    if player.get("level") != level_for_xp(xp) or player.get("level") > MAX_LEVEL:
        raise ValueError("Kayıt seviyesi deneyim puanıyla uyuşmuyor.")
    if player.get("proficiency_bonus") != PROFICIENCY_BONUS:
        raise ValueError("Kayıt ustalık bonusu geçersiz.")
    for key, limit in (("species", 40), ("origin_feat", 40)):
        if key not in player or player.get(key) is None:
            continue
        value = player.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError("Kayıt karakter özelliği geçersiz.")
    ids = world.get("xp_awarded_event_ids")
    if not isinstance(ids, list) or len(ids) > MAX_AWARD_IDS:
        raise ValueError("Kayıt deneyim olayları geçersiz.")
    seen: set[str] = set()
    for item in ids:
        if not isinstance(item, str) or item in seen or _AWARD_ID.fullmatch(item) is None:
            raise ValueError("Kayıt deneyim olayı geçersiz.")
        seen.add(item)
