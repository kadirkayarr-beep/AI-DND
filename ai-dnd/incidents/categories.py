"""Incident category families. Mechanics stay with existing owners.

Qwen may request a social or theft framing. Python chooses the DC, the
check, and whether gold moves. Narrated gambling winnings never pay.
"""

from __future__ import annotations

SOCIAL = "social"
URBAN_THEFT = "urban_theft"
LOST_PROPERTY = "lost_property"
TRAVEL = "travel"
WILDERNESS = "wilderness"
COMBAT = "combat"
GAMBLING = "gambling"
DISTURBANCE = "disturbance"

PYTHON_DCS = {
    "easy": 10,
    "medium": 15,
    "hard": 20,
}
SKILL_OWNERS = {
    "insight": "Insight",
    "perception": "Perception",
    "investigation": "Investigation",
    "persuasion": "Persuasion",
    "deception": "Deception",
    "intimidation": "Intimidation",
    "performance": "Performance",
    "stealth": "Stealth",
    "survival": "Survival",
    "athletics": "Athletics",
    "acrobatics": "Acrobatics",
    "sleight_of_hand": "Sleight of Hand",
}
CHECK_OWNERS = frozenset(SKILL_OWNERS) | {"tool", "spell"}

MOTIF_COOLDOWN = 3


def dc_for(band):
    """Python owns the number. The model does not."""
    return PYTHON_DCS.get(band, PYTHON_DCS["medium"])


def skill_for(token):
    return SKILL_OWNERS.get(token)


def gambling_pays(action_result):
    """Narrated winnings are not a payout."""
    if not isinstance(action_result, dict):
        return False
    if action_result.get("action") == "gambling" and action_result.get("source") == "narration":
        return False
    return False


def motif_allowed(world, motif):
    recent = world.get("emergence_state", {}).get("recent_categories", [])
    if not isinstance(recent, list):
        return True
    return recent[-MOTIF_COOLDOWN:].count(motif) < MOTIF_COOLDOWN


def combat_bind_allowed(envelope):
    return bool(envelope.get("allowed_creature_ids")) and envelope.get("threat_band") != "none"
