"""Explicit, JSON-safe projections of canonical engine state."""

from __future__ import annotations

import copy
import equipment_economy
import os
import uuid
from collections.abc import Mapping
from typing import Any

import game
import living_world
import campaign_time
import scheduled_events
import timed_gameplay
import exploration
import interaction_adventure
from pydantic import ValidationError
from api.schemas import (
    CombatHistoryEntry,
    CombatStateProjection,
    CombatTurnResult,
    DeathStateProjection,
    SkillCheckResult,
)
from api.world_metadata import world_metadata_for_state
from api.campaign_journal import empty_campaign_journal


_PLAYER_FIELDS = (
    "name",
    "race",
    "species",
    "giant_ancestry",
    "species_trait_state",
    "speed_ft",
    "class",
    "background",
    "alignment",
    "origin",
    "appearance",
    "personality",
    "backstory",
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
    "proficient_skills",
    "expertise_skills",
    "origin_feat",
    "species_bonus_feat",
    "species_bonus_skills",
    "origin_feats",
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
    "tags",
    "shop_id",
    "max_hp",
    "current_hp",
    "armor_class",
    "combat_status",
)
_SHOP_FIELDS = (
    "id",
    "name",
    "description",
    "location",
    "tags",
    "shopkeeper_id",
)
_FEATURE_FIELDS = ("id", "location", "name", "description")
_DOOR_FIELDS = (
    "id",
    "name",
    "location",
    "description",
    "open",
    "locked",
    "broken",
)
_LOCATION_FIELDS = (
    "id", "name", "type", "description", "parent_location_id", "exit_location_id"
)
_COMBAT_ATTACK_FIELDS = (
    "action",
    "status",
    "success",
    "outcome",
    "actor",
    "actor_name",
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
    "damage_type",
    "attack_rolls",
    "disadvantage",
    "hp_damage",
    "temporary_hp_before",
    "temporary_hp_absorbed",
    "temporary_hp_after",
    "species_effects",
    "action_id",
    "resolution_id",
    "critical_state",
    "resolution",
    "death_save",
    "death_resolution",
)
_COMBAT_TURN_FIELDS = (
    *_COMBAT_ATTACK_FIELDS,
    "combat_id",
    "combat_status",
    "round",
    "current_turn_index",
    "combat_started",
    "combat_ended",
    "end_reason",
    "current_actor_id",
    "turn_owner",
    "economy_steps",
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




def _public_combat_name(identity: Any, fallback: Any, world_state: Any) -> Any:
    if identity == "player":
        return fallback
    if not isinstance(identity, str) or not isinstance(world_state, Mapping):
        return fallback
    npc = next((
        item for item in world_state.get("npcs", [])
        if isinstance(item, Mapping) and item.get("id") == identity
    ), None)
    return living_world.public_npc_name(npc) if npc is not None else fallback


def _sanitize_combat_names(projected: dict[str, Any], world_state: Any) -> dict[str, Any]:
    if not isinstance(projected, dict):
        return projected
    for key, value in projected.items():
        if isinstance(value, dict):
            _sanitize_combat_names(value, world_state)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _sanitize_combat_names(item, world_state)
    actor_id = projected.get("actor_id") or projected.get("actor")
    target_id = projected.get("target_id") or projected.get("target")
    if "actor_name" in projected:
        projected["actor_name"] = _public_combat_name(actor_id, projected.get("actor_name"), world_state)
    if "target_name" in projected:
        projected["target_name"] = _public_combat_name(target_id, projected.get("target_name"), world_state)
    return projected


def serialize_combat_result(action_result: Any, session: Any = None) -> dict[str, Any] | None:
    """Expose only Python-owned combat outcome fields to the browser."""
    if not isinstance(action_result, Mapping) or action_result.get("action") not in {
        "attack",
        "death_save",
        "action_economy",
    }:
        return None
    if not action_result.get("combat_started") and not action_result.get("enemy_actions") and action_result.get("outcome") in {
        "invalid_target", "no_target", "no_weapon", "out_of_turn", "target_mismatch",
        "ambiguous_target", "missing_target", "attack_negated",
    }:
        return None  # Rejection/clarification is not a canonical combat result.

    world_state = getattr(session, "world_state", None)
    projected = _sanitize_combat_names(
        _project_fields(action_result, _COMBAT_TURN_FIELDS), world_state
    )
    enemy_action = action_result.get("enemy_action")
    if isinstance(enemy_action, Mapping):
        projected["enemy_action"] = _sanitize_combat_names(
            _project_fields(enemy_action, _COMBAT_ATTACK_FIELDS), world_state
        )
    enemy_actions = action_result.get("enemy_actions")
    if isinstance(enemy_actions, list):
        projected["enemy_actions"] = [
            _sanitize_combat_names(
                _project_fields(item, _COMBAT_ATTACK_FIELDS), world_state
            )
            for item in enemy_actions
            if isinstance(item, Mapping)
        ]
    try:
        validated = CombatTurnResult.model_validate(projected, strict=True)
    except ValidationError:
        raise CombatResultSerializationError(
            "Invalid combat result."
        ) from None
    return validated.model_dump(exclude_unset=True)


def serialize_combat_state(value: Any, world_state: Any = None) -> dict[str, Any]:
    """Expose only the public scheduler fields and canonical combatant status."""
    combat = value if isinstance(value, Mapping) else {}
    current_actor_id = combat.get("current_actor_id")
    participants = combat.get("participants")
    records = combat.get("participant_records")
    projected = {
        "active": combat.get("active", False),
        "combat_id": combat.get("combat_id"),
        "status": combat.get(
            "status",
            "active" if combat.get("active") is True else "ended",
        ),
        "round": combat.get("round", 0),
        "initiative_order": copy.deepcopy(combat.get("initiative_order", [])),
        "current_turn_index": combat.get("current_turn_index", 0),
        "current_actor_id": current_actor_id,
        "turn_owner": current_actor_id,
        "participants": copy.deepcopy(
            participants if isinstance(participants, list) else []
        ),
        "participant_records": [
            {
                **(lambda item: {
                    **item,
                    "name": _public_combat_name(
                        record.get("id"), item.get("name"), world_state
                    ),
                })(_project_fields(
                    record,
                    (
                        "id",
                        "kind",
                        "name",
                        "current_hp",
                        "max_hp",
                        "armor_class",
                        "status",
                        "primary_action_available",
                    ),
                )),
                "is_current_actor": record.get("id") == current_actor_id,
            }
            for record in (records if isinstance(records, list) else [])
            if isinstance(record, Mapping)
        ],
        "target_id": combat.get("target_id"),
        "end_reason": combat.get("end_reason"),
    }
    try:
        validated = CombatStateProjection.model_validate(projected, strict=True)
    except ValidationError:
        raise ValueError("Invalid combat state projection.") from None
    return validated.model_dump()


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
    advantage = action_result.get("advantage", False)
    disadvantage = action_result.get("disadvantage", False)
    expertise = action_result.get("expertise", False)
    dice_rolls = action_result.get("dice_rolls", [d20])
    resolution = action_result.get("resolution")

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
    expertise_skills = character.get("expertise_skills", ())
    if not isinstance(expertise_skills, (list, tuple, set)):
        raise SkillCheckResultSerializationError("Invalid skill-check result.")
    expected_expertise = proficient and skill in expertise_skills
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
        character_proficiency_bonus * (2 if expected_expertise else 1)
        if proficient
        else 0
    )
    tool = action_result.get("tool")
    if tool is not None:
        import equipment_economy
        if (tool != "Thieves' Tools" or skill != "Sleight of Hand"
                or not any(equipment_economy.label(i) == tool for i in session.world_state["inventory"])):
            raise SkillCheckResultSerializationError("Invalid tool check.")
        if tool in character.get("proficient_tools", []) and not proficient:
            expected_proficiency_modifier = character_proficiency_bonus
    import weapon_attack
    total_modifier = ability_modifier + proficiency_modifier - 2 * weapon_attack.exhaustion(character)
    if (
        d20 < 1
        or d20 > 20
        or proficiency_modifier < 0
        or proficiency_modifier != expected_proficiency_modifier
        or total != d20 + total_modifier
        or expertise is not expected_expertise
        or type(advantage) is not bool
        or type(disadvantage) is not bool
        or not isinstance(dice_rolls, list)
        or any(type(roll) is not int or not 1 <= roll <= 20 for roll in dice_rolls)
        or (
            (advantage != disadvantage)
            and (
                len(dice_rolls) != 2
                or (max(dice_rolls) if advantage else min(dice_rolls)) != d20
            )
        )
        or (
            (advantage == disadvantage)
            and (len(dice_rolls) != 1 or dice_rolls[0] != d20)
        )
        or (
            resolution is not None
            and (
                not isinstance(resolution, Mapping)
                or resolution.get("resolution_type") != "skill_check"
                or resolution.get("selected_roll") != d20
                or resolution.get("total") != total
            )
        )
    ):
        raise SkillCheckResultSerializationError("Invalid skill-check result.")

    try:
        projected_values = dict(
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
        if advantage != disadvantage:
            projected_values["d20_rolls"] = dice_rolls
        if "advantage" in action_result:
            projected_values["advantage"] = advantage
        if "disadvantage" in action_result:
            projected_values["disadvantage"] = disadvantage
        if "expertise" in action_result:
            projected_values["expertise"] = expertise
        if isinstance(resolution, Mapping):
            for field in ("action_id", "resolution_id"):
                if resolution.get(field) is not None:
                    projected_values[field] = resolution[field]
        projected = SkillCheckResult(**projected_values)
    except ValidationError:
        raise SkillCheckResultSerializationError(
            "Invalid skill-check result."
        ) from None
    return projected.model_dump(exclude_none=True)


def serialize_session_state(
    session: Any,
    journal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project the engine snapshot without exposing prompts or private internals."""
    import bounded_encounter
    bounded_state = bounded_encounter.public_projection(session) if isinstance(session, game.GameSession) else None
    snapshot = session.serialize_game_state()
    player = snapshot.get("player", {})
    world = snapshot.get("world_state", {})
    flags = world.get("flags", {})

    raw_locations = world.get("locations", {})
    known_location_ids = exploration.known_locations(world)
    visible_npcs = [
        projected
        for npc in exploration.player_entities(world, scheduled_events.visible_npcs(world))
        if (projected := living_world.public_npc_projection(npc)) is not None
    ]
    visible_world = {
        **world,
        "features": exploration.player_entities(world, world.get("features", [])),
        "shops": exploration.player_entities(world, world.get("shops", [])),
        "doors": exploration.visible_doors(world),
        "npcs": visible_npcs,
    }
    locations = {
        str(location_id): _project_fields(record, _LOCATION_FIELDS)
        for location_id, record in raw_locations.items()
        if isinstance(raw_locations, Mapping)
        and isinstance(record, Mapping)
        and location_id in known_location_ids
    } if isinstance(raw_locations, Mapping) else {}
    world_metadata = world_metadata_for_state(
        world,
        getattr(session, "world_metadata", None),
    )
    character = _project_fields(player, _PLAYER_FIELDS)
    expertise_skills = player.get("expertise_skills")
    character["expertise_skills"] = (
        list(expertise_skills)
        if isinstance(expertise_skills, (list, tuple))
        else []
    )
    character["species"] = player.get("species", player.get("race"))
    character["giant_ancestry"] = player.get("giant_ancestry")
    trait_state = player.get("species_trait_state")
    character["species_trait_state"] = copy.deepcopy(
        trait_state
        if isinstance(trait_state, Mapping)
        else (
            game._new_species_trait_state(
                character["species"], player.get("proficiency_bonus", 2)
            )
            if character["species"] in game.SPECIES_WITH_TRAIT_STATE
            else None
        )
    )
    character["speed_ft"] = player.get(
        "speed_ft", 35 if character["species"] == "Goliath" else 30
    )
    character["origin_feat"] = player.get("origin_feat")
    character["species_bonus_feat"] = player.get("species_bonus_feat")
    species_bonus_skills = player.get("species_bonus_skills")
    character["species_bonus_skills"] = (
        list(species_bonus_skills)
        if isinstance(species_bonus_skills, (list, tuple))
        else []
    )
    origin_feats = player.get("origin_feats")
    character["origin_feats"] = (
        list(origin_feats)
        if isinstance(origin_feats, (list, tuple))
        else ([character["origin_feat"]] if character["origin_feat"] else [])
    )
    raw_death_state = world.get("death_state", {})
    raw_death_state = (
        raw_death_state if isinstance(raw_death_state, Mapping) else {}
    )
    player_status = world.get("player_combat_status", "active")
    death_status = (
        "dead"
        if raw_death_state.get("dead") is True or player_status == "dead"
        else "stable"
        if raw_death_state.get("stable") is True
        else "unconscious"
        if player_status == "unconscious"
        else "active"
    )
    projected_death_state = {
        "mode": raw_death_state.get("mode", "NORMAL"),
        "status": death_status,
        "successes": raw_death_state.get("successes", 0),
        "failures": raw_death_state.get("failures", 0),
        "stable": raw_death_state.get("stable", False),
        "dead": raw_death_state.get("dead", False),
        "terminal": raw_death_state.get("terminal", False),
        "prone": raw_death_state.get("prone", False),
        "last_death_save": copy.deepcopy(
            raw_death_state.get("last_death_save_result")
        ),
        "last_resolution": copy.deepcopy(
            raw_death_state.get("last_resolution")
        ),
    }
    try:
        death_state = DeathStateProjection.model_validate(
            projected_death_state, strict=True
        ).model_dump(exclude_none=True)
    except ValidationError:
        raise ValueError("Invalid death state projection.") from None
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
        "campaign_time": campaign_time.public_time(world),
        "known_scheduled_events": scheduled_events.public_events(world),
        "pending_event_decisions": scheduled_events.public_pending(world),
        "journey": timed_gameplay.public_journey(world),
        "expedition": timed_gameplay.public_expedition(session, snapshot=snapshot),
        "scene": living_world.public_scene_projection(
            visible_world, flags.get("turn_index", 0)
        ),
        "world": world_metadata,
        "journal": copy.deepcopy(
            journal if journal is not None else empty_campaign_journal()
        ),
        "locations": locations,
        "character": character,
        "inventory": equipment_economy.public_inventory(world),
        "spellcasting": (
            {key: copy.deepcopy(world["spellcasting_v1"][key])
             for key in ("cantrips", "prepared", "slots", "slot_turn")}
            if world.get("spellcasting_v1") is not None else None
        ),
        "npcs": _project_list(visible_world["npcs"], _NPC_FIELDS),
        "shops": _project_list([living_world.public_shop_projection(world, shop) for shop in exploration.player_entities(world, world.get("shops", []))], _SHOP_FIELDS),
        "features": _project_list(exploration.player_entities(world, world.get("features", [])), _FEATURE_FIELDS),
        "doors": _project_list(exploration.visible_doors(world), _DOOR_FIELDS),
        "combat": {
            **serialize_combat_state(world.get("combat", {}), world),
            "action_economy": game.action_economy.projection(session)
            if isinstance(session, game.GameSession) and world.get("combat", {}).get("active") else None,
        },
        "player_combat_status": copy.deepcopy(
            world.get("player_combat_status", "active")
        ),
        "death_state": death_state,
        "turn_index": copy.deepcopy(flags.get("turn_index", 0)),
        "quests": quest_state,
        "quest_offers": offers,
        "adventure": interaction_adventure.public(world),
        "exploration": exploration.public_projection(world),
        **({"bounded_encounter": bounded_state} if bounded_state is not None else {}),
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
