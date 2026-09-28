"""Explicit, JSON-safe projections of canonical engine state."""

from __future__ import annotations

import copy
import os
from collections.abc import Mapping
from typing import Any

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