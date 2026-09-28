"""Validation and session restoration around the engine's existing save format."""

from __future__ import annotations

import json
import os
import random
from copy import deepcopy
from typing import Any

import game

from api.campaign_journal import (
    empty_campaign_journal,
    validate_campaign_journal,
)
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignValidationError,
)
from api.world_metadata import (
    set_session_world_metadata,
    validate_world_metadata,
    world_metadata_for_state,
)


CAMPAIGN_FORMAT = "ai-dnd-campaign"
CAMPAIGN_FORMAT_VERSION = 1
_SENSITIVE_ENV_KEYS = ("OLLAMA_HOST", "OLLAMA_PROXY_TOKEN", "SESSION_SECRET")


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_strings(child)


def ensure_no_configured_secrets(value: Any) -> None:
    """Reject persistence of exact configured Ollama connection values."""
    configured = [
        os.environ[key]
        for key in _SENSITIVE_ENV_KEYS
        if os.environ.get(key)
    ]
    if any(secret in text for text in _walk_strings(value) for secret in configured):
        raise CampaignValidationError(
            "Sensitive connection data cannot be stored in a campaign."
        )


def _ensure_json_safe(value: Any, error_type: type[Exception]) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise error_type("Campaign data is not valid JSON.") from None


def _validate_engine_save(engine_save: Any, error_type: type[Exception]) -> None:
    if not isinstance(engine_save, dict):
        raise error_type("Campaign engine state is invalid.")
    try:
        # Reuse the canonical engine validator; do not create a parallel state
        # format or change the frozen game module.
        game._validate_save_payload(engine_save)
    except Exception:
        raise error_type("Campaign engine state failed validation.") from None

    world = engine_save.get("world_state")
    if not isinstance(world, dict):
        raise error_type("Campaign world state is invalid.")
    if not isinstance(world.get("location"), str):
        raise error_type("Campaign location is invalid.")
    if not isinstance(world.get("flags"), dict):
        raise error_type("Campaign session metadata is invalid.")
    if not isinstance(world.get("combat"), dict):
        raise error_type("Campaign combat state is invalid.")

    combat = world["combat"]
    if "active" in combat and type(combat["active"]) is not bool:
        raise error_type("Campaign combat state is invalid.")
    if "round" in combat and type(combat["round"]) is not int:
        raise error_type("Campaign combat state is invalid.")
    if "initiative_order" in combat and not isinstance(combat["initiative_order"], list):
        raise error_type("Campaign combat state is invalid.")
    if "current_turn_index" in combat and type(combat["current_turn_index"]) is not int:
        raise error_type("Campaign combat state is invalid.")
    if "participants" in combat and not isinstance(combat["participants"], list):
        raise error_type("Campaign combat state is invalid.")

    for npc in world.get("npcs", []):
        if not isinstance(npc, dict):
            raise error_type("Campaign NPC data is invalid.")
        memory = npc.get("memory", [])
        if not isinstance(memory, list):
            raise error_type("Campaign NPC memory is invalid.")
        for entry in memory:
            if isinstance(entry, str):
                continue
            if (
                not isinstance(entry, dict)
                or entry.get("speaker") not in ("player", "npc")
                or not isinstance(entry.get("text"), str)
            ):
                raise error_type("Campaign NPC memory is invalid.")

    _ensure_json_safe(engine_save, error_type)


def _tuple_tree(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuple_tree(item) for item in value)
    return value


def _validate_rng_state(value: Any, error_type: type[Exception]) -> None:
    _ensure_json_safe(value, error_type)
    try:
        random.Random().setstate(_tuple_tree(value))
    except Exception:
        raise error_type("Campaign random state is invalid.") from None


def serialize_campaign_payload(
    session: Any,
    journal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep the engine save intact and persist API-owned RNG/world metadata."""
    try:
        engine_save = session.serialize_game_state()
        rng_state = session.rng.getstate()
    except Exception:
        raise CampaignValidationError("The current campaign state is unavailable.") from None

    _validate_engine_save(engine_save, CampaignValidationError)
    serializable_rng = json.loads(
        json.dumps(rng_state, ensure_ascii=False, allow_nan=False)
    )
    world_metadata = world_metadata_for_state(
        engine_save.get("world_state", {}),
        getattr(session, "world_metadata", None),
    )
    journal_payload = journal if journal is not None else empty_campaign_journal()
    validate_campaign_journal(journal_payload, CampaignValidationError)
    payload = {
        "format": CAMPAIGN_FORMAT,
        "version": CAMPAIGN_FORMAT_VERSION,
        "engine_save": engine_save,
        "rng_state": serializable_rng,
        "world_metadata": world_metadata,
        "journal": journal_payload,
    }
    validate_campaign_payload(payload, CampaignValidationError)
    ensure_no_configured_secrets(payload)
    return payload


def validate_campaign_payload(
    payload: Any,
    error_type: type[Exception] = CampaignCorruptError,
) -> None:
    if not isinstance(payload, dict):
        raise error_type("Campaign save is not a JSON object.")
    if payload.get("format") != CAMPAIGN_FORMAT:
        raise error_type("Campaign save format is unsupported.")
    if payload.get("version") != CAMPAIGN_FORMAT_VERSION:
        raise error_type("Campaign save version is unsupported.")
    required_fields = {"format", "version", "engine_save", "rng_state"}
    allowed_fields = required_fields | {"world_metadata", "journal"}
    if not required_fields.issubset(payload) or not set(payload).issubset(
        allowed_fields
    ):
        raise error_type("Campaign save fields are invalid.")

    _validate_engine_save(payload["engine_save"], error_type)
    _validate_rng_state(payload["rng_state"], error_type)
    if "world_metadata" in payload:
        validate_world_metadata(payload["world_metadata"], error_type)
    if "journal" in payload:
        validate_campaign_journal(payload["journal"], error_type)
    ensure_no_configured_secrets(payload)


def serialize_history_entry(
    player_message: str,
    narration: str,
) -> dict[str, str]:
    entry = {
        "player_message": player_message,
        "narration": narration,
    }
    if (
        not isinstance(player_message, str)
        or not player_message.strip()
        or len(player_message) > 4000
        or not isinstance(narration, str)
        or not narration.strip()
    ):
        raise CampaignValidationError("Campaign history entry is invalid.")
    ensure_no_configured_secrets(entry)
    return entry


def validate_history_entry(entry: Any) -> dict[str, str]:
    if (
        not isinstance(entry, dict)
        or set(entry) != {"player_message", "narration", "created_at"}
        or not isinstance(entry.get("player_message"), str)
        or not entry["player_message"].strip()
        or len(entry["player_message"]) > 4000
        or not isinstance(entry.get("narration"), str)
        or not entry["narration"].strip()
        or not isinstance(entry.get("created_at"), str)
        or not entry["created_at"].strip()
    ):
        raise CampaignCorruptError("Campaign history is invalid.")
    ensure_no_configured_secrets(entry)
    return {
        "player_message": entry["player_message"],
        "narration": entry["narration"],
        "created_at": entry["created_at"],
    }


def restore_campaign_session(session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Restore through the engine loader without serializing prompt text."""
    validate_campaign_payload(payload)
    import json
    import tempfile
    from pathlib import Path

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(
                payload["engine_save"],
                handle,
                ensure_ascii=False,
                allow_nan=False,
            )
            temporary_path = Path(handle.name)
        session.load_game(temporary_path)
        session.rng.setstate(_tuple_tree(payload["rng_state"]))
        set_session_world_metadata(
            session,
            payload.get("world_metadata"),
        )
        journal = deepcopy(
            payload.get("journal", empty_campaign_journal())
        )
    except Exception:
        raise CampaignCorruptError(
            "Campaign could not be restored safely."
        ) from None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return journal