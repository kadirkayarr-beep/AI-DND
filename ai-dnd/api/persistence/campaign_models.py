"""Shared errors and value objects for persistent campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CampaignError(Exception):
    """Base class for safe, user-facing campaign failures."""


class CampaignNotFoundError(CampaignError):
    """A campaign identifier is invalid or is not present in the registry."""


class CampaignNotActiveError(CampaignError):
    """A campaign has no current in-memory session to save."""


class CampaignCorruptError(CampaignError):
    """A saved campaign failed integrity or version validation."""


class CampaignStorageError(CampaignError):
    """Persistent storage could not complete an operation."""


class CampaignValidationError(CampaignError):
    """The current session could not be serialized as a safe campaign."""


class CampaignIdConflictError(CampaignError):
    """A generated campaign identifier already exists."""


@dataclass(frozen=True)
class StoredCampaign:
    metadata: dict[str, Any]
    payload: dict[str, Any]
    history: list[dict[str, str]]
    combat_history: list[dict[str, Any]]