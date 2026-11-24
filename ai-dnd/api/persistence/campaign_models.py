"""Shared errors and value objects for persistent campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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


class CampaignStaleError(CampaignError):
    """A runtime copy no longer owns the current committed campaign revision."""


class CampaignValidationError(CampaignError):
    """The current session could not be serialized as a safe campaign."""


class CampaignIdConflictError(CampaignError):
    """A generated campaign identifier already exists."""


class InvalidDeathModeError(CampaignError, ValueError):
    """A new campaign asked for a death mode the game does not have (still a ValueError for older callers)."""


class SaveLanded(Enum):
    """What a read-back says about a campaign save that raised."""

    LANDED = "landed"  # storage holds exactly this result: the live game stays on it
    NOT_LANDED = "not_landed"  # storage is still on the old revision: a rollback is safe
    UNKNOWN = "unknown"  # it cannot be told: nobody may guess, the session closes


@dataclass(frozen=True)
class StoredCampaign:
    metadata: dict[str, Any]
    payload: dict[str, Any]
    history: list[dict[str, str]]
    combat_history: list[dict[str, Any]]