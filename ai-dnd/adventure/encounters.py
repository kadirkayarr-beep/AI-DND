"""Bounded encounter recipes. Threat bands, not a party calculator."""

from __future__ import annotations

RECIPES = {
    "road_ambush": {
        "recipe_id": "road_ambush",
        "threat_band": "low",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["combat", "stealth"],
        "family": "road_ambush",
    },
    "wounded_traveler": {
        "recipe_id": "wounded_traveler",
        "threat_band": "low",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["social", "investigation"],
        "family": "wounded_traveler",
    },
    "dungeon_room": {
        "recipe_id": "dungeon_room",
        "threat_band": "moderate",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["combat", "stealth"],
        "family": "dungeon_room",
    },
    "patrol": {
        "recipe_id": "patrol",
        "threat_band": "low",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["combat", "stealth", "social"],
        "family": "patrol",
    },
    "beast_threat": {
        "recipe_id": "beast_threat",
        "threat_band": "high",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["combat", "stealth"],
        "family": "beast_threat",
    },
    "faction_checkpoint": {
        "recipe_id": "faction_checkpoint",
        "threat_band": "moderate",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["social", "stealth"],
        "family": "faction_checkpoint",
    },
    "merchant_trouble": {
        "recipe_id": "merchant_trouble",
        "threat_band": "low",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["social", "investigation"],
        "family": "merchant_trouble",
    },
    "environment_hazard": {
        "recipe_id": "environment_hazard",
        "threat_band": "low",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["environment", "stealth"],
        "family": "environment_hazard",
    },
    "adventure_resolution": {
        "recipe_id": "adventure_resolution",
        "threat_band": "moderate",
        "min_level": 1,
        "max_level": 4,
        "allowed_resolution_kinds": ["combat", "persuasion", "stealth"],
        "family": "adventure_resolution",
    },
}


def families():
    return tuple(recipe["family"] for recipe in RECIPES.values())


def bind(recipe_id, *, entities, location):
    """Return one recipe bound to entities that already exist. It creates none."""
    recipe = RECIPES.get(recipe_id)
    if recipe is None or not isinstance(location, str) or not location.strip():
        return None
    if not isinstance(entities, list) or any(not isinstance(item, str) for item in entities):
        return None
    return {
        "recipe_id": recipe["recipe_id"],
        "threat_band": recipe["threat_band"],
        "allowed_resolution_kinds": list(recipe["allowed_resolution_kinds"]),
        "entities": list(entities),
        "location": location,
    }


def select(level, recent_categories):
    """Prefer a non-combat recipe when recent encounters were combat-heavy."""
    if type(level) is not int or not 1 <= level <= 4:
        level = 1
    recent = [item for item in recent_categories if isinstance(item, str)]
    combat_heavy = recent.count("combat") >= 2
    ordered = ["wounded_traveler", "road_ambush", "dungeon_room"] if combat_heavy else [
        "road_ambush", "dungeon_room", "wounded_traveler",
    ]
    for recipe_id in ordered:
        recipe = RECIPES[recipe_id]
        if recipe["min_level"] <= level <= recipe["max_level"]:
            if recipe["threat_band"] == "high":
                continue
            return dict(recipe)
    return None
