"""Canonical, server-owned atmosphere metadata derived from the current world."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any, Type


ENVIRONMENTS = frozenset(
    {
        "tavern",
        "forest",
        "city",
        "village",
        "road",
        "wilderness",
        "dungeon",
        "cave",
        "castle",
        "temple",
        "ruins",
        "unknown",
    }
)
TIMES_OF_DAY = frozenset({"dawn", "day", "evening", "night"})
WEATHER_TYPES = frozenset({"clear", "rain", "fog", "snow", "storm", "unknown"})
DEFAULT_TIME_OF_DAY = "day"
DEFAULT_WEATHER = "clear"
_METADATA_FIELDS = {"environment", "time_of_day", "weather"}


class WorldMetadataError(ValueError):
    """Raised when persisted or server-owned world metadata is invalid."""


_ALIASES: dict[str, tuple[str, ...]] = {
    "tavern": ("tavern", "taverna", "han", "meyhane", "inn"),
    "forest": ("forest", "orman", "koru", "woods", "woodland"),
    "city": ("city", "sehir", "kent", "baskent", "capital"),
    "village": ("village", "koy", "mezra", "hamlet"),
    "road": ("road", "yol", "patika", "gecit", "trail", "path"),
    "wilderness": ("wilderness", "vahsi", "kir", "bozkir", "wilds"),
    "dungeon": ("dungeon", "zindan"),
    "cave": ("cave", "magara", "kovuk"),
    "castle": ("castle", "kale", "hisar", "fortress"),
    "temple": ("temple", "tapinak", "manastir"),
    "ruins": ("ruins", "harabe", "yikinti"),
}
_TYPE_FALLBACKS = {
    "outdoor": "wilderness",
    "open country": "wilderness",
    "wilderness": "wilderness",
    "trail": "road",
    "path": "road",
}


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed
        if not unicodedata.combining(character)
    ).replace("ı", "i")
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _canonical_match(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize(value)
    if normalized in ENVIRONMENTS:
        return normalized
    padded = f" {normalized} "
    for environment, aliases in _ALIASES.items():
        if any(f" {_normalize(alias)} " in padded for alias in aliases):
            return environment
    return None


def infer_environment(world_state: Any) -> str:
    """Infer a supported environment from explicit location metadata first."""
    if not isinstance(world_state, Mapping):
        return "unknown"
    location_id = world_state.get("location")
    locations = world_state.get("locations")
    location = (
        locations.get(location_id)
        if isinstance(locations, Mapping) and isinstance(location_id, str)
        else None
    )
    location = location if isinstance(location, Mapping) else {}

    explicit = _canonical_match(location.get("environment"))
    if explicit is not None:
        return explicit
    if isinstance(location_id, str) and _normalize(location_id) in ENVIRONMENTS:
        return _normalize(location_id)

    for candidate in (location.get("name"), location_id):
        match = _canonical_match(candidate)
        if match is not None:
            return match

    location_type = location.get("type")
    type_match = _canonical_match(location_type)
    if type_match is not None:
        return type_match
    if isinstance(location_type, str):
        return _TYPE_FALLBACKS.get(_normalize(location_type), "unknown")
    return "unknown"


def validate_world_metadata(
    value: Any,
    error_type: Type[Exception] = WorldMetadataError,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _METADATA_FIELDS:
        raise error_type("World metadata fields are invalid.")
    environment = value.get("environment")
    time_of_day = value.get("time_of_day")
    weather = value.get("weather")
    if not isinstance(environment, str) or environment not in ENVIRONMENTS:
        raise error_type("World environment is invalid.")
    if not isinstance(time_of_day, str) or time_of_day not in TIMES_OF_DAY:
        raise error_type("World time of day is invalid.")
    if not isinstance(weather, str) or weather not in WEATHER_TYPES:
        raise error_type("World weather is invalid.")
    return {
        "environment": str(environment),
        "time_of_day": str(time_of_day),
        "weather": str(weather),
    }


def world_metadata_for_state(
    world_state: Any,
    metadata: Any = None,
) -> dict[str, str]:
    """Return valid current metadata, deriving environment from Python location."""
    if metadata is None:
        time_of_day = DEFAULT_TIME_OF_DAY
        weather = DEFAULT_WEATHER
    else:
        validated = validate_world_metadata(metadata)
        time_of_day = validated["time_of_day"]
        weather = validated["weather"]
    from campaign_time import public_time
    clock = public_time(world_state) if isinstance(world_state, dict) else None
    if clock is not None:
        time_of_day = clock["time_of_day"]
    import local_adventure_catalog
    if (isinstance(world_state, dict) and world_state.get(local_adventure_catalog.KEY)
            and world_state.get("location") in local_adventure_catalog.LOCATIONS):
        weather = local_adventure_catalog.LOCATIONS[world_state["location"]]["weather"]
    return {
        "environment": infer_environment(world_state),
        "time_of_day": time_of_day,
        "weather": weather,
    }


def set_session_world_metadata(
    session: Any,
    metadata: Any = None,
) -> dict[str, str]:
    resolved = world_metadata_for_state(session.world_state, metadata)
    session.world_metadata = resolved
    return resolved


def session_world_metadata(session: Any) -> dict[str, str]:
    return world_metadata_for_state(
        session.world_state,
        getattr(session, "world_metadata", None),
    )