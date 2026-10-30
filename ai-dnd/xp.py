"""Tier 1 experience from the 2024 Player's Handbook.

Python owns the total, the level, and the hit-point gain. Narration and the
client cannot grant experience. Levels stop at 5; experience past that
threshold is kept and does not open level 6.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from feat_rules import held_feats
from quest_catalog import find_quest


MAX_LEVEL = 5
MAX_GRANT = 100_000
MAX_STORED_XP = 1_000_000_000
MAX_AWARD_IDS = 10_000  # Bounded long-campaign receipts; old save IDs remain valid.

# Character Advancement table, levels 1–5; higher numeric levels remain pending.
LEVEL_THRESHOLDS = (
    (1, 0),
    (2, 300),
    (3, 900),
    (4, 2700),
    (5, 6500),
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


def proficiency_bonus_for(level: int) -> int:
    """The one Proficiency Bonus resolver (K07 leaf): kept here as a name for the XP/level code."""
    from api.dnd_2024_rules import proficiency_bonus_for_level
    return proficiency_bonus_for_level(level)


def level_for_xp(xp: int) -> int:
    """Return the bounded level for a stored experience total."""
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
    if "Tough" in held_feats(dict(character)):  # PHB 2024 Tough: +2 per level, however many records name it
        gain += 2
    return gain


def _award_ids(world: dict[str, Any]) -> list[str]:
    ids = world.get("xp_awarded_event_ids")
    if not isinstance(ids, list):
        ids = []
        world["xp_awarded_event_ids"] = ids
    return ids


def _apply_numeric_level(character: dict[str, Any], target: int) -> dict[str, int]:
    """Shared numeric owner for real XP and atomic high-level creation.

    Does not award XP, record an event, finalize creation HP, or grant class choices.
    Callers own transaction/admission. Never demotes an already higher raw level.
    """
    if type(target) is not int or not 1 <= target <= MAX_LEVEL:
        raise ValueError("Unsupported numeric advancement target.")
    previous = character.get("level")
    if type(previous) is not int or previous < 1:
        previous = 1
    stored_level = previous
    previous = min(previous, MAX_LEVEL)
    level = previous
    gains: list[int] = []
    while level < target and level < MAX_LEVEL:
        gains.append(hit_point_gain(character))
        level += 1

    hit_points_gained = 0
    max_hp = character.get("max_hp")
    current_hp = character.get("current_hp")
    if type(max_hp) is not int:
        max_hp = 0
    if type(current_hp) is not int:
        current_hp = 0
    for gain in gains:
        max_hp += gain
        if current_hp > 0:
            current_hp += gain
        hit_points_gained += gain
    character["max_hp"] = max_hp
    character["current_hp"] = current_hp
    level = max(level, min(stored_level, 20))  # XP never demotes a character created above the XP-earned cap (C06)
    character["level"] = level
    old_pb = proficiency_bonus_for(min(stored_level, 20))
    new_pb = proficiency_bonus_for(level)
    if new_pb != old_pb:
        from api.dnd_2024_rules import CLASS_DEFINITIONS
        definition = CLASS_DEFINITIONS.get(character.get("class"), {})
        saves = character.get("saving_throw_mods")
        if isinstance(saves, dict):
            for ability in definition.get("saving_throws", []):
                if type(saves.get(ability)) is int:
                    saves[ability] += new_pb - old_pb
        # Derived caches are not authorities. Clear present casting caches;
        # existing consumers recompute them from score and canonical PB.
        for key in ("spell_save_dc", "spell_attack_bonus"):
            character.pop(key, None)
        if "initiative" in character:
            character.pop("initiative")
    character["proficiency_bonus"] = new_pb
    return {"previous_level": min(stored_level, 20), "new_level": level,
            "hit_points_gained": hit_points_gained}


def apply_xp(character: dict[str, Any], world: dict[str, Any], amount: int, event_id: str):
    """Grant one experience award and apply every crossed level through 5.

    Returns a summary, or None when the event was already paid or the amount
    is not a positive server grant. The award id is recorded only after the
    character can accept the grant. ``hit_points_gained`` reports maximum-HP
    advancement, not guaranteed current-HP recovery: zero HP stays zero.
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

    current_xp = character.get("xp")
    if type(current_xp) is not int or current_xp < 0:
        current_xp = 0
    new_xp = current_xp + amount
    if new_xp > MAX_STORED_XP:
        return None
    summary = _apply_numeric_level(character, level_for_xp(new_xp))
    ids.append(event_id)
    character["xp"] = new_xp
    return {**summary, "xp_gained": amount}



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
    if len(event_id) > 187:  # The existing receipt validator allows 180 chars after 'combat:'.
        digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
        event_id = f"combat:sha256:{digest}"
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


def validate_saved_advancement(player: Mapping[str, Any], world: Mapping[str, Any], *, policy: int = 5) -> None:
    """Reject a version-5 save whose experience does not match its level."""
    if type(policy) is not int or policy not in (5, 6):
        raise ValueError("Unsupported saved XP policy.")
    xp = player.get("xp")
    if type(xp) is not int or xp < 0 or xp > MAX_STORED_XP:
        raise ValueError("Kayıt deneyim puanı geçersiz.")
    earned = min(level_for_xp(xp), 4) if policy == 5 else level_for_xp(xp)
    cap = 4 if policy == 5 else 5
    level, applied = player.get("level"), player.get("progression_level")
    if applied is None:
        if level != earned or level > cap:
            raise ValueError("Kayıt seviyesi deneyim puanıyla uyuşmuyor.")
        if player.get("proficiency_bonus") != proficiency_bonus_for(level):
            raise ValueError("Kayıt ustalık bonusu geçersiz.")
    else:  # C06: a level reached through applied class-table choices may be ahead of the XP-earned level, never behind it
        if type(level) is not int or type(applied) is not int or not earned <= level <= 20 or not 1 <= applied <= level:
            raise ValueError("Kayıt seviyesi deneyim puanıyla uyuşmuyor.")
        if player.get("proficiency_bonus") != proficiency_bonus_for(level):
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
