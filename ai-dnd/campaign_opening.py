"""Campaign opening plan (W11): lore is the starting ground, the player's choice is the rail.

`build_opening(preferences, authorized_lore, backstory)` only uses lore the caller has authorized; it invents none. It never
requires a tavern, a lost relative or a main quest, never reverts a campaign override to the lore baseline (the baseline is
copied, not mutated), withholds a backstory secret until its reveal turn, and returns a BLOCKED plan instead of guessing when the
lore version or the start location is not verified (the official future is never forced into the story).
"""
from __future__ import annotations

import copy
from typing import Any


def _blocked(reason: str) -> dict[str, Any]:
    return {"status": "BLOCKED", "reason": reason}


def _start_location(preferences: dict[str, Any], lore: dict[str, Any]) -> tuple[str | None, str | None]:
    locations = lore.get("locations") or {}
    requested = preferences.get("start_location_id")
    if requested is not None:
        record = locations.get(requested)
        if not isinstance(record, dict):
            return None, "start_location_not_verified"
        return (requested, None) if record.get("verified") is True else (None, "start_location_not_verified")
    for location_id, record in locations.items():
        if isinstance(record, dict) and record.get("verified") is True:
            return location_id, None
    return None, "no_verified_start_location"


def build_opening(preferences: dict[str, Any], authorized_lore: dict[str, Any], backstory: dict[str, Any]) -> dict[str, Any]:
    if authorized_lore.get("verified") is not True or not authorized_lore.get("version"):
        return _blocked("lore_version_unverified")
    mode = preferences.get("mode", "ai")
    if mode == "own" and not str(preferences.get("own_text") or "").strip():
        return _blocked("own_opening_empty")
    location_id, reason = _start_location(preferences, authorized_lore)
    if location_id is None:
        return _blocked(reason or "start_location_not_verified")
    location = authorized_lore["locations"][location_id]

    canon = {"facts": copy.deepcopy(authorized_lore.get("facts") or {})}
    overrides = (preferences.get("campaign_overrides") or {}).get("facts") or {}
    canon["facts"].update(copy.deepcopy(overrides))  # the campaign's own changes win over the baseline
    diverged = sorted(key for key, value in overrides.items() if (authorized_lore.get("facts") or {}).get(key) != value)

    turn = (lambda v: v if type(v) is int else 0)(preferences.get("current_turn"))
    secrets = (backstory or {}).get("secrets") or []
    revealed = [item["id"] for item in secrets if int(item.get("reveal_after_turn", 10 ** 9)) <= turn]
    withheld = [item["id"] for item in secrets if item["id"] not in revealed]
    links = []
    if preferences.get("link_backstory"):
        links = [item["id"] for item in (backstory or {}).get("public") or []]

    if mode == "own":
        opening_text = str(preferences["own_text"])
    else:
        opening_text = f"{location['name']} çevresinde yolculuğun başlıyor."
        if links:
            public = {item["id"]: item["text"] for item in backstory["public"]}
            opening_text += " " + " ".join(public[link] for link in links)
    return {
        "status": "ready", "mode": mode, "location_id": location_id, "opening_text": opening_text,
        "required_elements": [], "main_quest": None, "canon": canon, "diverged_keys": diverged,
        "backstory_links": links, "withheld_secret_ids": withheld, "revealed_secret_ids": revealed,
        "preview": {"location_name": location["name"], "accepted_entity_ids": [location_id],
                    "lore_version": authorized_lore["version"]},
    }
