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