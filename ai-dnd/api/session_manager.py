"""In-memory registry for opaque, isolated game sessions."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import game

from api.character_creation import configure_character
from api.persistence.campaign_models import (
    CampaignNotActiveError,
    CampaignStorageError,
)
from api.persistence.campaign_serializer import restore_stored_campaign
from api.persistence.campaign_store import CampaignStore
from api.serializers import serialize_session_state


class UnknownSessionError(LookupError):
    """Raised when an API request refers to a session that is not registered."""


@dataclass
class ManagedSession:
    game_session: Any
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    campaign_id: str | None = None


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
        campaign_id = str(uuid.uuid4())
        campaign_name = name or f"{session.character['name']} — Yeni Macera"
        metadata = store.create_campaign(campaign_id, campaign_name, session)
        with self._registry_lock:
            session_id = self._new_session_id_locked()
            record = ManagedSession(game_session=session, campaign_id=campaign_id)
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
        restore_stored_campaign(session, stored)
        return {
            "campaign": stored.metadata,
            "state": serialize_session_state(session),
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
            restore_stored_campaign(session, stored)
            with self._registry_lock:
                active_id = self._campaign_sessions.get(campaign_id)
                record = self._sessions.get(active_id) if active_id else None
                if record is None:
                    session_id = self._new_session_id_locked()
                    record = ManagedSession(
                        game_session=session,
                        campaign_id=campaign_id,
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
            metadata = store.mark_played(campaign_id)
            state = serialize_session_state(record.game_session)
        return session_id, record, metadata, stored.history, state

    def save_campaign(self, campaign_id: str) -> dict[str, Any]:
        store = self._require_campaign_store()
        with self._registry_lock:
            session_id = self._campaign_sessions.get(campaign_id)
            record = self._sessions.get(session_id) if session_id else None
        if record is None:
            raise CampaignNotActiveError("Campaign has no active session.")
        with record.turn_lock:
            return store.save_campaign(campaign_id, record.game_session)

    def autosave_turn(
        self,
        record: ManagedSession,
        player_message: str,
        narration: str,
    ) -> dict[str, Any] | None:
        """Persist a successful turn; caller holds record.turn_lock."""
        if record.campaign_id is None:
            return None
        return self._require_campaign_store().save_campaign(
            record.campaign_id,
            record.game_session,
            turn_entry={
                "player_message": player_message,
                "narration": narration,
            },
        )

    def _require_campaign_store(self) -> CampaignStore:
        if self._campaign_store is None:
            raise CampaignStorageError("Campaign persistence is unavailable.")
        return self._campaign_store