"""Python-authoritative d20 resolution primitives.

The core consumes trusted modifiers and targets and returns a structured result.
It does not read or mutate campaign state; gameplay systems own those decisions.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator


class ResolutionInputError(ValueError):
    """Raised when a caller supplies an invalid authoritative resolution input."""


@dataclass
class _ActionScope:
    action_id: str
    session_id: str | None
    counters: dict[str, int] = field(default_factory=dict)


_ACTIVE_ACTION: ContextVar[_ActionScope | None] = ContextVar(
    "ai_dnd_core_resolution_action",
    default=None,
)
_ABILITIES = {
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
}


@contextmanager
def resolution_action_scope(
    action_id: str,
    session_id: str | None = None,
) -> Iterator[None]:
    """Give each resolution in one player action a stable, typed child ID."""
    if not isinstance(action_id, str) or not action_id.strip():
        raise ResolutionInputError("Action ID must be a non-empty string.")
    if session_id is not None and (
        not isinstance(session_id, str) or not session_id.strip()
    ):
        raise ResolutionInputError("Session ID must be a non-empty string.")
    token = _ACTIVE_ACTION.set(_ActionScope(action_id, session_id))
    try:
        yield
    finally:
        _ACTIVE_ACTION.reset(token)


def resolution_identity(
    resolution_type: str,
    *,
    action_id: str | None = None,
    resolution_id: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Return a stable action/resolution identity for the active turn scope."""
    scope = _ACTIVE_ACTION.get()
    if action_id is None and scope is not None:
        action_id = scope.action_id
    elif scope is not None and action_id != scope.action_id:
        raise ResolutionInputError("Resolution action ID does not match its scope.")

    if resolution_id is None and scope is not None:
        count = scope.counters.get(resolution_type, 0) + 1
        scope.counters[resolution_type] = count
        resolution_id = f"{scope.action_id}:{resolution_type}:{count}"
    if action_id is not None and (
        not isinstance(action_id, str) or not action_id.strip()
    ):
        raise ResolutionInputError("Action ID must be a non-empty string.")
    if resolution_id is not None and (
        not isinstance(resolution_id, str) or not resolution_id.strip()
    ):
        raise ResolutionInputError("Resolution ID must be a non-empty string.")
    return action_id, resolution_id, scope.session_id if scope else None


def _int_value(name: str, value: Any, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ResolutionInputError(f"{name} is invalid.")
    return value


def _rolls(
    roll_fn: Callable[[], int],
    *,
    advantage: bool,
    disadvantage: bool,
) -> tuple[list[int], int, bool]:
    if type(advantage) is not bool or type(disadvantage) is not bool:
        raise ResolutionInputError("Advantage and disadvantage must be booleans.")
    cancelled = advantage and disadvantage
    use_advantage = advantage and not disadvantage
    use_disadvantage = disadvantage and not advantage
    rolls = [roll_fn()]
    if use_advantage or use_disadvantage:
        rolls.append(roll_fn())
    if any(type(roll) is not int or not 1 <= roll <= 20 for roll in rolls):
        raise ResolutionInputError("D20 roller returned a value outside 1–20.")
    selected = max(rolls) if use_advantage else min(rolls) if use_disadvantage else rolls[0]
    return rolls, selected, cancelled


def roll_d20(
    roll_fn: Callable[[], int],
    *,
    advantage: bool = False,
    disadvantage: bool = False,
) -> dict[str, Any]:
    """Roll one d20, or two for one effective advantage/disadvantage state."""
    rolls, selected, cancelled = _rolls(
        roll_fn,
        advantage=advantage,
        disadvantage=disadvantage,
    )
    return {
        "roll_type": "d20",
        "raw_rolls": rolls,
        "selected_roll": selected,
        "advantage": advantage,
        "disadvantage": disadvantage,
        "advantage_cancelled": cancelled,
    }


def _resolve_check(
    *,
    roll_fn: Callable[[], int],
    resolution_type: str,
    ability: str,
    ability_modifier: int,
    proficiency_modifier: int,
    circumstantial_modifier: int,
    dc: int,
    advantage: bool,
    disadvantage: bool,
    action_id: str | None,
    resolution_id: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ability not in _ABILITIES:
        raise ResolutionInputError("Ability is invalid.")
    ability_modifier = _int_value("Ability modifier", ability_modifier)
    proficiency_modifier = _int_value(
        "Proficiency modifier",
        proficiency_modifier,
        minimum=0,
    )
    circumstantial_modifier = _int_value(
        "Circumstantial modifier",
        circumstantial_modifier,
    )
    dc = _int_value("DC", dc, minimum=1)
    action_id, resolution_id, session_id = resolution_identity(
        resolution_type,
        action_id=action_id,
        resolution_id=resolution_id,
    )
    roll = roll_d20(
        roll_fn,
        advantage=advantage,
        disadvantage=disadvantage,
    )
    breakdown = {
        "ability_modifier": ability_modifier,
        "proficiency_modifier": proficiency_modifier,
        "circumstantial_modifier": circumstantial_modifier,
    }
    modifier = sum(breakdown.values())
    total = roll["selected_roll"] + modifier
    result = {
        "action_id": action_id,
        "session_id": session_id,
        "resolution_id": resolution_id,
        "resolution_type": resolution_type,
        **roll,
        "ability": ability,
        "modifier_breakdown": breakdown,
        "total_modifier": modifier,
        "total": total,
        "target_value": dc,
        "dc": dc,
        "outcome": "SUCCESS" if total >= dc else "FAILURE",
        "critical_state": None,
    }
    if extra:
        result.update(extra)
    return result


def resolve_ability_check(
    *,
    roll_fn: Callable[[], int],
    ability: str,
    dc: int,
    ability_modifier: int,
    proficiency_modifier: int = 0,
    circumstantial_modifier: int = 0,
    advantage: bool = False,
    disadvantage: bool = False,
    action_id: str | None = None,
    resolution_id: str | None = None,
) -> dict[str, Any]:
    return _resolve_check(
        roll_fn=roll_fn,
        resolution_type="ability_check",
        ability=ability,
        ability_modifier=ability_modifier,
        proficiency_modifier=proficiency_modifier,
        circumstantial_modifier=circumstantial_modifier,
        dc=dc,
        advantage=advantage,
        disadvantage=disadvantage,
        action_id=action_id,
        resolution_id=resolution_id,
    )


def resolve_skill_check(
    *,
    roll_fn: Callable[[], int],
    skill: str,
    ability: str,
    dc: int,
    ability_modifier: int,
    proficiency_modifier: int = 0,
    circumstantial_modifier: int = 0,
    proficient: bool = False,
    expertise: bool = False,
    advantage: bool = False,
    disadvantage: bool = False,
    action_id: str | None = None,
    resolution_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(skill, str) or not skill.strip():
        raise ResolutionInputError("Skill is invalid.")
    if type(proficient) is not bool or type(expertise) is not bool:
        raise ResolutionInputError("Skill proficiency flags must be booleans.")
    if expertise and not proficient:
        raise ResolutionInputError("Expertise requires proficiency.")
    result = _resolve_check(
        roll_fn=roll_fn,
        resolution_type="skill_check",
        ability=ability,
        ability_modifier=ability_modifier,
        proficiency_modifier=proficiency_modifier,
        circumstantial_modifier=circumstantial_modifier,
        dc=dc,
        advantage=advantage,
        disadvantage=disadvantage,
        action_id=action_id,
        resolution_id=resolution_id,
        extra={
            "skill": skill,
            "proficient": proficient,
            "expertise": expertise,
        },
    )
    return result


def resolve_saving_throw(
    *,
    roll_fn: Callable[[], int],
    ability: str,
    dc: int,
    ability_modifier: int,
    proficiency_modifier: int = 0,
    circumstantial_modifier: int = 0,
    advantage: bool = False,
    disadvantage: bool = False,
    action_id: str | None = None,
    resolution_id: str | None = None,
) -> dict[str, Any]:
    return _resolve_check(
        roll_fn=roll_fn,
        resolution_type="saving_throw",
        ability=ability,
        ability_modifier=ability_modifier,
        proficiency_modifier=proficiency_modifier,
        circumstantial_modifier=circumstantial_modifier,
        dc=dc,
        advantage=advantage,
        disadvantage=disadvantage,
        action_id=action_id,
        resolution_id=resolution_id,
    )


def resolve_attack_roll(
    *,
    roll_fn: Callable[[], int],
    attack_bonus: int,
    target_ac: int,
    advantage: bool = False,
    disadvantage: bool = False,
    action_id: str | None = None,
    resolution_id: str | None = None,
    actor_id: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    attack_bonus = _int_value("Attack bonus", attack_bonus)
    target_ac = _int_value("Target AC", target_ac, minimum=0)
    action_id, resolution_id, session_id = resolution_identity(
        "attack_roll",
        action_id=action_id,
        resolution_id=resolution_id,
    )
    roll = roll_d20(
        roll_fn,
        advantage=advantage,
        disadvantage=disadvantage,
    )
    selected = roll["selected_roll"]
    total = selected + attack_bonus
    if selected == 20:
        outcome = "CRITICAL_HIT"
        critical_state = "critical_hit"
    elif selected == 1:
        outcome = "MISS"
        critical_state = "automatic_miss"
    elif total >= target_ac:
        outcome = "HIT"
        critical_state = None
    else:
        outcome = "MISS"
        critical_state = None
    return {
        "action_id": action_id,
        "session_id": session_id,
        "resolution_id": resolution_id,
        "resolution_type": "attack_roll",
        **roll,
        "actor_id": actor_id,
        "target_id": target_id,
        "modifier_breakdown": {"attack_bonus": attack_bonus},
        "total_modifier": attack_bonus,
        "total": total,
        "target_value": target_ac,
        "target_ac": target_ac,
        "outcome": outcome,
        "critical_state": critical_state,
    }