"""Tier 1 experience from the 2024 Player's Handbook.

Python owns the total, the level, and the hit-point gain. Narration and the
client cannot grant experience. Levels stop at 5; experience past that
threshold is kept and does not open level 6.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Mapping, Sequence

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

# Experience Points by Challenge Rating (SRD 5.2.1). CR 0 pays 10 here because every person we put in a fight
# has an effective attack.
XP_BY_CR = {"0": 10, "1/8": 25, "1/4": 50, "1/2": 100, "1": 200, "2": 450, "3": 700, "4": 1100, "5": 1800}
# masa kuralı: stat bloğu olmayan kişi en yakın SRD bloğu (Guard / Commoner), Kadir kararı 4
PERSON_KIND_CR = {"armed": "1/8", "strong": "0", "plain": "0"}

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


def reward_for(npc: Mapping[str, Any], person_kind: str | None) -> int:
    """What a beaten creature pays: a server-set ``xp_reward``, else its stat block's Challenge Rating, else its kind.

    Only the server (or a test) writes ``xp_reward`` and ``monster_stat_block``; nothing the model proposes reaches them.
    """
    reward = npc.get("xp_reward")
    if type(reward) is int and 1 <= reward <= MAX_GRANT:
        return reward
    block = npc.get("monster_stat_block")
    if isinstance(block, Mapping):
        rating = block.get("challenge_rating")
        if isinstance(rating, str) and rating in XP_BY_CR:
            return XP_BY_CR[rating]
    rating = PERSON_KIND_CR.get(person_kind) if isinstance(person_kind, str) else None
    return XP_BY_CR[rating] if rating is not None else 0


def apply_xp_grants(character: dict[str, Any], world: dict[str, Any], grants: Sequence[tuple[str, int]]):
    """Pay several awards at once: all of them or none (``None``, nothing changed).

    Every id must fit the receipt pattern and appear once in the list; every amount is 1..MAX_GRANT; the total and the
    receipt count stay inside their caps. Ids the world already paid are dropped quietly and the rest are paid; when
    none is left the answer is ``None``. The summary has the keys ``apply_xp`` gives.
    """
    if not isinstance(character, dict) or not isinstance(world, dict) or isinstance(grants, (str, bytes)):
        return None
    try:
        grants = list(grants)
    except TypeError:
        return None
    seen: set[str] = set()
    for grant in grants:
        if not isinstance(grant, (tuple, list)) or len(grant) != 2:
            return None
        event_id, amount = grant
        if not isinstance(event_id, str) or _AWARD_ID.fullmatch(event_id) is None or event_id in seen:
            return None
        if type(amount) is not int or amount <= 0 or amount > MAX_GRANT:
            return None
        seen.add(event_id)
    held = world.get("xp_awarded_event_ids")
    held = held if isinstance(held, list) else []
    held_set = set(held)
    fresh = [(event_id, amount) for event_id, amount in grants if event_id not in held_set]
    if not fresh or len(held) + len(fresh) > MAX_AWARD_IDS:
        return None
    total = sum(amount for _, amount in fresh)
    current_xp = character.get("xp")
    if type(current_xp) is not int or current_xp < 0:
        current_xp = 0
    new_xp = current_xp + total
    if new_xp > MAX_STORED_XP:
        return None
    summary = _apply_numeric_level(character, level_for_xp(new_xp))  # raises before any write if the class is unknown
    _award_ids(world).extend(event_id for event_id, _ in fresh)
    character["xp"] = new_xp  # the character is written last
    return {**summary, "xp_gained": total}


def _foe_award_id(npc_id: str) -> str:
    event_id = f"combat:foe:{npc_id}"
    if len(event_id) > 187 or _AWARD_ID.fullmatch(event_id) is None:  # the receipt pattern allows 180 chars after 'combat:'
        event_id = f"combat:foe:sha256:{hashlib.sha256(npc_id.encode('utf-8')).hexdigest()}"
    return event_id


def award_defeated_combat(combat: Mapping[str, Any], world: dict[str, Any], character: dict[str, Any], *,
                          person_kind: Callable[[Mapping[str, Any]], str] | None = None):
    """Pay every beaten foe of an ended encounter in one all-or-nothing grant, once per creature for the campaign.

    The caller must still have the participant list. Leaving, or the player falling unconscious, is not this
    function's job and pays nothing.
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
    grants: list[tuple[str, int]] = []
    listed: set[str] = set()
    for participant_id in participants:
        if not isinstance(participant_id, str) or participant_id == "player" or participant_id in listed:
            continue
        npc = by_id.get(participant_id)
        if not isinstance(npc, dict) or not _is_defeated(npc):
            continue
        reward = reward_for(npc, person_kind(npc) if person_kind else None)
        if reward <= 0:
            continue
        listed.add(participant_id)
        grants.append((_foe_award_id(participant_id), reward))
    if not grants:
        return None
    return apply_xp_grants(character, world, grants)


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
