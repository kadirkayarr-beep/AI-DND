"""Read-only catalog routes moved out of api.main.create_app (D-531 stage 1): same paths, models and order."""
from __future__ import annotations

from typing import Any

import game
from fastapi import FastAPI

from api.dnd_2024_rules import get_character_creation_catalog
from api.lore_authority import PRODUCTION_START_CATALOG
from api.schemas import CampaignStartOptionsResponse, CharacterCreationCatalogResponse, CharacterCreationOptions


def register_catalog_routes(application: FastAPI) -> None:
    @application.get(
        "/api/game/character-options",
        response_model=CharacterCreationOptions,
    )
    @application.get(
        "/api/character-options",
        response_model=CharacterCreationOptions,
    )
    def character_creation_options() -> dict[str, list[str]]:
        return {"races": list(game.RACES), "classes": list(game.CLASSES)}

    @application.get(
        "/api/game/character-creation-catalog",
        response_model=CharacterCreationCatalogResponse,
    )
    @application.get(
        "/api/character-creation-catalog",
        response_model=CharacterCreationCatalogResponse,
    )
    def character_creation_catalog() -> dict[str, Any]:
        return get_character_creation_catalog()

    @application.get(
        "/api/game/campaign-start-options",
        response_model=CampaignStartOptionsResponse,
    )
    @application.get(
        "/api/campaign-start-options",
        response_model=CampaignStartOptionsResponse,
    )
    def campaign_start_options() -> dict[str, Any]:
        return PRODUCTION_START_CATALOG.to_response()
