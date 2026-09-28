"""Validated HTTP request and response models for the AI-DND API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    engine: Literal["AI-DND"] = "AI-DND"
    model: Literal["qwen3:8b"] = "qwen3:8b"


class SessionResponse(BaseModel):
    session_id: str
    state: dict[str, Any]


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be empty.")
        return value


class TurnResponse(BaseModel):
    session_id: str
    narration: str
    state: dict[str, Any]


class CampaignCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def campaign_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Campaign name must not be blank.")
        return cleaned


class CampaignSummary(BaseModel):
    campaign_id: str
    name: str
    created_at: str
    updated_at: str
    last_played_at: str
    save_version: int
    character_name: str
    character_race: str
    character_class: str
    character_level: int
    location: str


class CampaignHistoryEntry(BaseModel):
    player_message: str
    narration: str
    created_at: str


class CampaignDetailResponse(BaseModel):
    campaign: CampaignSummary
    state: dict[str, Any]
    history: list[CampaignHistoryEntry]


class CampaignSessionResponse(BaseModel):
    campaign_id: str
    session_id: str
    name: str
    state: dict[str, Any]
    history: list[CampaignHistoryEntry]