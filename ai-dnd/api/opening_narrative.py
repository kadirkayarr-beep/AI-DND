"""Deterministic, campaign-persistent first-scene presentation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from functools import lru_cache
from typing import Any

import campaign_time
import living_world
import local_places
import tr_case
import name_catalog
import world_threads
from api.world_metadata import world_metadata_for_state

_LOG = logging.getLogger(__name__)


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


# Used only when a world has no clock to read an hour from.
_HOUR_OF_PERIOD = {"dawn": 7, "day": 13, "evening": 18, "night": 22}


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    try:
        mapping = json.loads((name_catalog.CATALOG_DIR / "mapping.json").read_text(encoding="utf-8"))
        lines = json.loads((name_catalog.CATALOG_DIR / "opening_lines.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _LOG.warning("The opening lines could not be read.")
        return {}
    tags = dict(mapping["openings"]["scene_tags"])
    place_tags = {kind: tag for tag, kinds in mapping.get("place_tags", {}).items() for kind in kinds}
    return {"rules": mapping["openings"], "scene_tags": tags, "place_tags": place_tags, "items": lines["items"]}


def _line_fits(item: dict[str, Any], tag: str, hour: int, weather: Any, rules: dict[str, Any]) -> bool:
    return (
        tag in item["location_types"]
        and any(window["start_hour"] <= hour < window["end_hour"] for window in item["time_windows"])
        and set(item["required_bindings"]) <= set(rules["bound_slots"])
        and (weather == "clear" or item["id"] not in rules["clear_sky_only"])
    )


def catalog_line(world: dict[str, Any], location_id: str, weather: Any, time_of_day: str = "day", salt: Any = None) -> str | None:
    """One first line for this place and hour, drawn by the campaign seed (and the salt, when given), or None when none fits."""
    data = _catalog()
    place = world.get("locations", {}).get(location_id)
    if not data or not isinstance(place, dict):
        return None
    tag = data["place_tags"].get(place.get("place_kind")) or data["scene_tags"].get(
        living_world.scene_kind(world, location_id))
    clock = campaign_time.public_time(world) if world.get("campaign_time") else None
    hour = clock["hour"] if clock else _HOUR_OF_PERIOD.get(time_of_day, 13)
    items = [item for item in data["items"] if tag and _line_fits(item, tag, hour, weather, data["rules"])]
    if not items:
        return None
    digest = hashlib.sha256(f"{living_world._campaign_seed(world)}\x00{location_id}\x00opening{'' if salt is None else chr(0) + str(salt)}".encode("utf-8")).digest()
    text = items[int.from_bytes(digest[:4], "big") % len(items)]["opening_template"]
    for slot in data["rules"]["bound_slots"]:
        text = text.replace("{" + slot + "}", place["name"])
    return text


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
    home = _CITY_SPELLINGS.get(key) or " ".join(tr_case.upper_first(word) for word in origin.split())
    return None if key == re.sub(r"[^a-z]", "", location_name.casefold()) else home


def opening_hook(world: dict[str, Any], settlement_id: str) -> list[str]:
    """The town's first word for a new campaign: one piece of street talk about real work, kept as heard (the journal
    shows it as a trail), and the one later nudge an idle player gets (world_reactions). Never calls the model."""
    world.setdefault("flags", {})["opening_nudge"] = {"due_turn": 8, "done": False}
    world_threads.ensure(world)
    talk = world_threads.street_talk(world, settlement_id)
    place = (world.get("locations") or {}).get(talk["place_id"]) if talk else None
    if not isinstance(place, dict):
        return []  # nothing going on: nothing is made up
    import grounded_action
    import town_knowledge
    town_knowledge.hear_of(world, talk)  # heard, its names given, and the place bound as just said ("oraya")
    grounded_action.note_last(world, talk["place_id"])
    return [f"Kalabalıktan bir söz kulağına çalınıyor: {talk['public_line']}"]


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

    # A happening the player can join when this place has one; the old quiet kind otherwise.
    event = living_world.select_and_record_ambient_event(
        world_state,
        location_id,
        0,
        allowed_types={"BLUE"},
    ) or living_world.select_and_record_ambient_event(
        world_state,
        location_id,
        0,
        allowed_types={"GREEN"},
    )
    if event is None:
        raise ValueError("No context-compatible ambient opening event exists.")
    if event["event_type"] == "BLUE":
        living_world.place_scene_event(world_state, location_id, 0, event)

    tone = _tone(character, metadata)
    time_opener = _TIME_OPENERS[metadata["time_of_day"]]
    weather_line = _WEATHER_LINES[metadata["weather"]]
    line = catalog_line(world_state, location_id, metadata["weather"], metadata["time_of_day"])
    if line:
        where = "" if location["name"] in line else f"{location['name']}."
        sky = "" if metadata["weather"] == "clear" else weather_line
        parts = [where, line, sky, event["text"]]
    else:
        parts = [f"{time_opener} {location['name']}.", weather_line, event["text"]]
    home = _home_elsewhere(character.get("origin"), location["name"])
    if home:
        parts.append(f"{home} uzakta kaldı.")
    settlement_id = local_places.settlement_of(world_state, location_id)
    if settlement_id:
        parts += opening_hook(world_state, settlement_id)
    text = " ".join(part for part in parts if part)
    return living_world.set_scene_opening(
        world_state,
        location_id,
        text,
        tone,
        event,
    )