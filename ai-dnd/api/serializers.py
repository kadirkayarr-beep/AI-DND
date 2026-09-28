"""Explicit, JSON-safe projections of canonical engine state."""

from __future__ import annotations

import copy
import os
import uuid
from collections.abc import Mapping
from typing import Any

import game
from pydantic import ValidationError
from api.schemas import CombatHistoryEntry, CombatTurnResult, SkillCheckResult
from api.world_metadata import world_metadata_for_state
from api.campaign_journal import empty_campaign_journal


_PLAYER_FIELDS = (
    "name",
    "race",
    "class",
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
    "proficient_skills",
    "level",
    "proficiency_bonus",
    "max_hp",
    "current_hp",
    "armor_class",
)
_NPC_FIELDS = (
    "id",
    "name",
    "role",
    "location",
    "appearance",
    "relationship",
    "max_hp",
    "current_hp",
    "armor_class",
    "combat_status",
)
_FEATURE_FIELDS = ("location", "name", "description")
_DOOR_FIELDS = (
    "id",
    "name",
    "location",
    "description",
    "open",
    "locked",
    "broken",
)
_LOCATION_FIELDS = ("id", "name", "type", "description")
_COMBAT_ATTACK_FIELDS = (
    "action",
    "status",
    "success",
    "outcome",
    "actor",
    "target",
    "target_id",
    "target_name",
    "weapon",
    "attack_roll",
    "attack_bonus",
    "attack_total",
    "target_ac",
    "critical",
    "damage",
    "target_hp_before",
    "target_hp_after",
    "target_status",
)
_COMBAT_TURN_FIELDS = (
    *_COMBAT_ATTACK_FIELDS,
    "combat_started",
    "combat_ended",
    "end_reason",
)


class SkillCheckResultSerializationError(ValueError):
    """Raised when a canonical engine skill-check result fails validation."""


class CombatResultSerializationError(ValueError):
    """Raised when a canonical engine combat result fails validation."""


def _project_fields(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        field: copy.deepcopy(value[field])
        for field in fields
        if field in value
    }


def _project_list(value: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        projected
        for item in value
        if (projected := _project_fields(item, fields))
    ]


def serialize_combat_result(action_result: Any) -> dict[str, Any] | None:
    """Expose only Python-owned combat outcome fields to the browser."""
    if not isinstance(action_result, Mapping) or action_result.get("action") != "attack":
        return None

    projected = _project_fields(action_result, _COMBAT_TURN_FIELDS)
    enemy_action = action_result.get("enemy_action")
    if isinstance(enemy_action, Mapping):
        projected["enemy_action"] = _project_fields(
            enemy_action,
            _COMBAT_ATTACK_FIELDS,
        )
    try:
        validated = CombatTurnResult.model_validate(projected, strict=True)
    except ValidationError:
        raise CombatResultSerializationError(
            "Invalid combat result."
        ) from None
    return validated.model_dump(exclude_unset=True)


def serialize_combat_history_entry(
    combat_result: dict[str, Any] | None,
    session: Any,
) -> dict[str, Any] | None:
    """Wrap a validated engine result in a stable server-generated event ID."""
    if combat_result is None:
        return None
    try:
        snapshot = session.serialize_game_state()
        flags = snapshot.get("world_state", {}).get("flags", {})
        turn_index = flags.get("turn_index")
        if type(turn_index) is not int or turn_index < 0:
            raise ValueError("Invalid canonical turn index.")
        entry = CombatHistoryEntry(
            event_id=str(uuid.uuid4()),
            turn_index=turn_index,
            result=combat_result,
        )
    except (AttributeError, TypeError, ValueError, ValidationError):
        raise CombatResultSerializationError(
            "Invalid combat history entry."
        ) from None
    return entry.model_dump(exclude_unset=True)


def serialize_skill_check_result(
    action_result: Any,
    session: Any,
) -> dict[str, Any] | None:
    """Expose only a validated projection of a Python-owned skill check."""
    if not isinstance(action_result, Mapping) or action_result.get("action") != "skill_check":
        return None

    skill = action_result.get("skill")
    ability = action_result.get("ability")
    d20 = action_result.get("dice")
    ability_modifier = action_result.get("modifier")
    proficiency_modifier = action_result.get("proficiency_bonus")
    total = action_result.get("total")
    dc = action_result.get("dc")
    outcome = action_result.get("outcome")

    if not isinstance(skill, str) or skill not in game.SKILLS:
        raise SkillCheckResultSerializationError("Invalid skill-check result.")
    if ability != game.SKILLS[skill]:
        raise SkillCheckResultSerializationError("Invalid skill-check result.")
    if any(
        type(value) is not int
        for value in (d20, ability_modifier, proficiency_modifier, total, dc)
    ):
        raise SkillCheckResultSerializationError("Invalid skill-check result.")

    difficulty = next(
        (
            label
            for label, configured_dc in game.DIFFICULTY_DC.items()
            if configured_dc == dc
        ),
        None,
    )
    if difficulty is None:
        raise SkillCheckResultSerializationError("Invalid skill-check result.")

    character = getattr(session, "character", None)
    if not isinstance(character, Mapping):
        raise SkillCheckResultSerializationError("Invalid skill-check result.")
    proficient_skills = character.get("proficient_skills")
    if not isinstance(proficient_skills, (list, tuple)):
        raise SkillCheckResultSerializationError("Invalid skill-check result.")
    proficient = skill in proficient_skills
    character_proficiency_bonus = character.get("proficiency_bonus")
    modifiers = character.get("modifiers")
    if (
        type(character_proficiency_bonus) is not int
        or character_proficiency_bonus < 0
        or not isinstance(modifiers, Mapping)
        or modifiers.get(ability) != ability_modifier
    ):
        raise SkillCheckResultSerializationError("Invalid skill-check result.")

    expected_proficiency_modifier = (
        character_proficiency_bonus if proficient else 0
    )
    total_modifier = ability_modifier + proficiency_modifier
    if (
        d20 < 1
        or d20 > 20
        or proficiency_modifier < 0
        or proficiency_modifier != expected_proficiency_modifier
        or total != d20 + total_modifier
    ):
        raise SkillCheckResultSerializationError("Invalid skill-check result.")

    try:
        projected = SkillCheckResult(
            skill=skill,
            ability=ability,
            d20=d20,
            proficient=proficient,
            ability_modifier=ability_modifier,
            proficiency_modifier=proficiency_modifier,
            total_modifier=total_modifier,
            total=total,
            difficulty=difficulty,
            dc=dc,
            outcome=outcome,
        )
    except ValidationError:
        raise SkillCheckResultSerializationError(
            "Invalid skill-check result."
        ) from None
    return projected.model_dump()


def serialize_session_state(
    session: Any,
    journal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project the engine snapshot without exposing prompts or private internals."""
    snapshot = session.serialize_game_state()
    player = snapshot.get("player", {})
    world = snapshot.get("world_state", {})
    flags = world.get("flags", {})

    raw_locations = world.get("locations", {})
    locations = {
        str(location_id): _project_fields(record, _LOCATION_FIELDS)
        for location_id, record in raw_locations.items()
        if isinstance(raw_locations, Mapping)
        and isinstance(record, Mapping)
    } if isinstance(raw_locations, Mapping) else {}
    world_metadata = world_metadata_for_state(
        world,
        getattr(session, "world_metadata", None),
    )
    raw_quests = copy.deepcopy(world.get("quests", []))
    quest_state = [
        {
            "quest_id": item.get("quest_id"),
            "title": item.get("title"),
            "description": item.get("description"),
            "status": item.get("status"),
            "giver_npc_id": item.get("giver_npc_id"),
            "objectives": [
                {
                    "objective_id": objective.get("objective_id"),
                    "description": objective.get("description"),
                    "status": objective.get("status"),
                    "progress": objective.get("progress", 0),
                    "required_count": objective.get("required_count", 1),
                }
                for objective in item.get("objectives", [])
            ],
        }
        for item in raw_quests
        if isinstance(item, dict)
    ]
    offers = [
        {
            "quest_id": item["quest_id"],
            "title": item["title"],
            "description": item["description"],
            "giver_npc_id": item.get("giver_npc_id"),
            "objectives": [
                {
                    "objective_id": objective["objective_id"],
                    "description": objective["description"],
                    "kind": objective["type"],
                    "target": objective["target"],
                    "required_count": objective.get("required_count", 1),
                }
                for objective in item["objectives"]
            ],
        }
        for item in session.quest_offers()
    ]
    return {
        "location": copy.deepcopy(world.get("location")),
        "world": world_metadata,
        "journal": copy.deepcopy(
            journal if journal is not None else empty_campaign_journal()
        ),
        "locations": locations,
        "character": _project_fields(player, _PLAYER_FIELDS),
        "inventory": copy.deepcopy(world.get("inventory", [])),
        "npcs": _project_list(world.get("npcs"), _NPC_FIELDS),
        "features": _project_list(world.get("features"), _FEATURE_FIELDS),
        "doors": _project_list(world.get("doors"), _DOOR_FIELDS),
        "combat": copy.deepcopy(world.get("combat", {})),
        "player_combat_status": copy.deepcopy(
            world.get("player_combat_status", "active")
        ),
        "turn_index": copy.deepcopy(flags.get("turn_index", 0)),
        "quests": quest_state,
        "quest_offers": offers,
    }


def redact_sensitive_values(value: Any) -> Any:
    """Remove exact configured secret values from all API response strings."""
    secrets = [
        secret
        for secret in (
            os.environ.get("OLLAMA_HOST"),
            os.environ.get("OLLAMA_PROXY_TOKEN"),
        )
        if secret
    ]

    def redact(item: Any) -> Any:
        if isinstance(item, str):
            result = item
            for secret in secrets:
                result = result.replace(secret, "[redacted]")
            return result
        if isinstance(item, Mapping):
            return {
                redact(str(key)): redact(child)
                for key, child in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [redact(child) for child in item]
        return item

    return redact(value)