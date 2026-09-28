"""In-memory registry for opaque, isolated game sessions."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import game

from api.campaign_journal import (
    create_initial_campaign_journal,
    empty_campaign_journal,
)
from api.character_creation import configure_character
from api.persistence.campaign_models import (
    CampaignNotActiveError,
    CampaignStorageError,
)
from api.persistence.campaign_serializer import restore_stored_campaign
from api.persistence.campaign_store import CampaignStore
from api.serializers import serialize_session_state
from api.world_metadata import set_session_world_metadata


class UnknownSessionError(LookupError):
    """Raised when an API request refers to a session that is not registered."""


@dataclass
class ManagedSession:
    game_session: Any
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    campaign_id: str | None = None
    journal: dict[str, Any] = field(default_factory=empty_campaign_journal)


class SessionManager:
    """Owns session objects; callers receive records, never client-controlled state."""

    def __init__(
        self,
        session_factory: Callable[[], Any] | None = None,
        campaign_store: CampaignStore | None = None,
    ):
        self._session_factory = session_factory or game.create_session
        self._campaign_store = campaign_store
        self._sessions: dict[str, ManagedSession] = {}
        self._campaign_sessions: dict[str, str] = {}
        self._registry_lock = threading.RLock()

    def _new_session_id_locked(self) -> str:
        session_id = str(uuid.uuid4())
        while session_id in self._sessions:
            session_id = str(uuid.uuid4())
        return session_id

    def create(self) -> tuple[str, ManagedSession]:
        session = self._session_factory()
        set_session_world_metadata(session)
        with self._registry_lock:
            session_id = self._new_session_id_locked()
            record = ManagedSession(game_session=session)
            self._sessions[session_id] = record
        return session_id, record

    def create_campaign(
        self,
        name: str | None = None,
        character: dict[str, Any] | None = None,
    ) -> tuple[str, str, ManagedSession, dict[str, Any]]:
        store = self._require_campaign_store()
        session = self._session_factory()
        if character is not None:
            configure_character(session, **character)
        set_session_world_metadata(session)
        journal = create_initial_campaign_journal(
            session.world_state,
            getattr(session, "world_metadata", None),
        )
        campaign_id = str(uuid.uuid4())
        campaign_name = name or f"{session.character['name']} — Yeni Macera"
        metadata = store.create_campaign(
            campaign_id,
            campaign_name,
            session,
            journal=journal,
        )
        with self._registry_lock:
            session_id = self._new_session_id_locked()
            record = ManagedSession(
                game_session=session,
                campaign_id=campaign_id,
                journal=journal,
            )
            self._sessions[session_id] = record
            self._campaign_sessions[campaign_id] = session_id
        return campaign_id, session_id, record, metadata

    def get(self, session_id: str) -> ManagedSession:
        with self._registry_lock:
            record = self._sessions.get(session_id)
        if record is None:
            raise UnknownSessionError(session_id)
        return record

    def list_campaigns(self) -> list[dict[str, Any]]:
        return self._require_campaign_store().list_campaigns()

    def get_campaign_detail(self, campaign_id: str) -> dict[str, Any]:
        stored = self._require_campaign_store().get_campaign(campaign_id)
        session = self._session_factory()
        journal = restore_stored_campaign(session, stored)
        return {
            "campaign": stored.metadata,
            "state": serialize_session_state(session, journal),
            "history": stored.history,
        }

    def resume_campaign(
        self,
        campaign_id: str,
    ) -> tuple[
        str,
        ManagedSession,
        dict[str, Any],
        list[dict[str, str]],
        dict[str, Any],
    ]:
        store = self._require_campaign_store()

        with self._registry_lock:
            active_id = self._campaign_sessions.get(campaign_id)
            record = self._sessions.get(active_id) if active_id else None
        if record is None:
            stored = store.get_campaign(campaign_id)
            session = self._session_factory()
            journal = restore_stored_campaign(session, stored)
            with self._registry_lock:
                active_id = self._campaign_sessions.get(campaign_id)
                record = self._sessions.get(active_id) if active_id else None
                if record is None:
                    session_id = self._new_session_id_locked()
                    record = ManagedSession(
                        game_session=session,
                        campaign_id=campaign_id,
                        journal=journal,
                    )
                    self._sessions[session_id] = record
                    self._campaign_sessions[campaign_id] = session_id
                else:
                    session_id = active_id
        else:
            session_id = active_id

        if session_id is None or record is None:
            raise CampaignStorageError("Campaign runtime could not be created.")
        with record.turn_lock:
            stored = store.get_campaign(campaign_id)
            needs_migration = (
                "world_metadata" not in stored.payload
                or "journal" not in stored.payload
            )
            if needs_migration:
                if "world_metadata" not in stored.payload:
                    set_session_world_metadata(
                        record.game_session,
                        getattr(record.game_session, "world_metadata", None),
                    )
                if "journal" not in stored.payload:
                    record.journal = empty_campaign_journal()
                store.save_campaign(
                    campaign_id,
                    record.game_session,
                    journal=record.journal,
                )
                stored = store.get_campaign(campaign_id)
            metadata = store.mark_played(campaign_id)
            state = serialize_session_state(record.game_session, record.journal)
        return session_id, record, metadata, stored.history, state

    def save_campaign(self, campaign_id: str) -> dict[str, Any]:
        store = self._require_campaign_store()
        with self._registry_lock:
            session_id = self._campaign_sessions.get(campaign_id)
            record = self._sessions.get(session_id) if session_id else None
        if record is None:
            raise CampaignNotActiveError("Campaign has no active session.")
        with record.turn_lock:
            set_session_world_metadata(
                record.game_session,
                getattr(record.game_session, "world_metadata", None),
            )
            return store.save_campaign(
                campaign_id,
                record.game_session,
                journal=record.journal,
            )

    def autosave_turn(
        self,
        record: ManagedSession,
        player_message: str,
        narration: str,
    ) -> dict[str, Any] | None:
        """Persist a successful turn; caller holds record.turn_lock."""
        if record.campaign_id is None:
            return None
        set_session_world_metadata(
            record.game_session,
            getattr(record.game_session, "world_metadata", None),
        )
        return self._require_campaign_store().save_campaign(
            record.campaign_id,
            record.game_session,
            turn_entry={
                "player_message": player_message,
                "narration": narration,
            },
            journal=record.journal,
        )

    def _require_campaign_store(self) -> CampaignStore:
        if self._campaign_store is None:
            raise CampaignStorageError("Campaign persistence is unavailable.")
        return self._campaign_store