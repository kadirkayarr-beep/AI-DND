"""Deterministic, campaign-persistent first-scene presentation."""

from __future__ import annotations

import re
from typing import Any

import living_world
from api.world_metadata import world_metadata_for_state


_TIME_OPENERS = {
    "dawn": "Şafak sökerken",
    "day": "Gün ışığı altında",
    "evening": "Akşam yaklaşırken",
    "night": "Gece çökmüşken",
}
_WEATHER_LINES = {
    "clear": "Gökyüzü açık; çevrenin çizgileri belirgin.",
    "rain": "Yağmur taşlara ve çatılara düzenli aralıklarla vuruyor.",
    "fog": "Sis, uzaktaki ayrıntıları yumuşatıp sesleri öne çıkarıyor.",
    "snow": "Kar, açıkta kalan yüzeylerde ince bir tabaka bırakmış.",
    "storm": "Fırtına rüzgârı sokakların ve yapıların arasından geçiyor.",
    "unknown": "",
}
# Cities a player may type without their apostrophe or capitals.
_CITY_SPELLINGS = {
    "baldursgate": "Baldur's Gate", "neverwinter": "Neverwinter", "waterdeep": "Waterdeep",
    "luskan": "Luskan", "silverymoon": "Silverymoon", "phandalin": "Phandalin",
}


def _tone(character: dict[str, Any], metadata: dict[str, str]) -> str:
    time_of_day = metadata.get("time_of_day")
    weather = metadata.get("weather")
    personality = str(character.get("personality") or "").casefold()
    backstory = str(character.get("backstory") or "").casefold()
    if weather == "storm":
        return "gergin"
    if time_of_day == "night" or weather == "fog":
        return "gizemli"
    if any(word in personality for word in ("neşeli", "iyimser", "şakacı")):
        return "sıcak"
    if any(word in backstory for word in ("kayıp", "yas", "sürgün", "yalnız")):
        return "melankolik"
    if time_of_day == "day":
        return "canlı"
    return "sakin"


def _home_elsewhere(origin: Any, location_name: str) -> str | None:
    """The character's home as a person would write it, when it is not this place."""
    if not isinstance(origin, str) or not origin.strip():
        return None
    key = re.sub(r"[^a-z]", "", origin.casefold())
    home = _CITY_SPELLINGS.get(key) or " ".join(word[:1].upper() + word[1:] for word in origin.split())
    return None if key == re.sub(r"[^a-z]", "", location_name.casefold()) else home


def initialize_campaign_opening(
    session: Any,
    campaign_id: str,
) -> dict[str, Any] | None:
    """Create one opening for a registered location; never call the model."""
    world_state = session.world_state
    character = session.character
    metadata = world_metadata_for_state(
        world_state,
        getattr(session, "world_metadata", None),
    )
    living_world.set_ambient_context(
        world_state,
        metadata,
        character,
        campaign_id,
    )
    location_id = world_state.get("location")
    locations = world_state.get("locations", {})
    location = locations.get(location_id) if isinstance(locations, dict) else None
    if (
        not isinstance(location_id, str)
        or not isinstance(location, dict)
        or not isinstance(location.get("name"), str)
    ):
        # Older API callers can still create campaigns without a verified
        # start-catalog selection. Preserve that contract without inventing
        # a location name or ambient scene.
        return None

    event = living_world.select_and_record_ambient_event(
        world_state,
        location_id,
        0,
        allowed_types={"GREEN"},
    )
    if event is None:
        raise ValueError("No context-compatible ambient opening event exists.")

    tone = _tone(character, metadata)
    time_opener = _TIME_OPENERS[metadata["time_of_day"]]
    weather_line = _WEATHER_LINES[metadata["weather"]]
    parts = [f"{time_opener} {location['name']}.", weather_line, event["text"]]
    home = _home_elsewhere(character.get("origin"), location["name"])
    if home:
        parts.append(f"{home} uzakta kaldı.")
    text = " ".join(part for part in parts if part)
    return living_world.set_scene_opening(
        world_state,
        location_id,
        text,
        tone,
        event,
    )