"""In-memory registry for opaque, isolated game sessions."""

from __future__ import annotations

import threading
import uuid
import copy
from dataclasses import dataclass, field
from typing import Any, Callable

import game

from api.campaign_journal import (
    create_initial_campaign_journal,
    empty_campaign_journal,
)
from api.character_creation import configure_character
from api.lore_authority.models import CampaignLoreState
from api.persistence.campaign_models import (
    CampaignNotActiveError,
    CampaignStorageError,
)
from api.persistence.campaign_serializer import restore_stored_campaign
from api.persistence.campaign_store import (
    MAX_COMBAT_HISTORY_ENTRIES,
    CampaignStore,
)
from api.narrative_memory import (
    empty_narrative_memory,
    validate_narrative_memory,
)
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
    combat_history: list[dict[str, Any]] = field(default_factory=list)
    narrative_memory: dict[str, Any] = field(default_factory=empty_narrative_memory)
    lore_authority: CampaignLoreState = field(
        default_factory=CampaignLoreState.legacy_unbound
    )


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
        narrative_memory = empty_narrative_memory()
        # No authorized starter pack or owner-approved launch location is
        # installed yet, so do not silently bind this campaign to canon.
        lore_authority = CampaignLoreState.legacy_unbound()
        campaign_id = str(uuid.uuid4())
        campaign_name = name or f"{session.character['name']} — Yeni Macera"
        metadata = store.create_campaign(
            campaign_id,
            campaign_name,
            session,
            journal=journal,
            narrative_memory=narrative_memory,
            lore_authority=lore_authority,
        )
        with self._registry_lock:
            session_id = self._new_session_id_locked()
            record = ManagedSession(
                game_session=session,
                campaign_id=campaign_id,
                journal=journal,
                narrative_memory=narrative_memory,
                lore_authority=lore_authority,
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
            "combat_history": stored.combat_history,
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
            lore_authority = CampaignLoreState.from_mapping(
                stored.payload.get("lore_authority")
            )
            with self._registry_lock:
                active_id = self._campaign_sessions.get(campaign_id)
                record = self._sessions.get(active_id) if active_id else None
                if record is None:
                    session_id = self._new_session_id_locked()
                    record = ManagedSession(
                        game_session=session,
                        campaign_id=campaign_id,
                        journal=journal,
                        narrative_memory=validate_narrative_memory(
                            stored.payload.get(
                                "narrative_memory",
                                empty_narrative_memory(),
                            )
                        ),
                        lore_authority=lore_authority,
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
                stored.payload.get("engine_save", {}).get("version")
                != game.SAVE_FORMAT_VERSION
                or
                "world_metadata" not in stored.payload
                or "journal" not in stored.payload
                or "narrative_memory" not in stored.payload
                or "lore_authority" not in stored.payload
            )
            record.lore_authority = CampaignLoreState.from_mapping(
                stored.payload.get("lore_authority")
            )
            record.narrative_memory = validate_narrative_memory(
                stored.payload.get(
                    "narrative_memory",
                    empty_narrative_memory(),
                )
            )
            if needs_migration:
                if "world_metadata" not in stored.payload:
                    set_session_world_metadata(
                        record.game_session,
                        getattr(record.game_session, "world_metadata", None),
                    )
                if "journal" not in stored.payload:
                    record.journal = empty_campaign_journal()
                if "narrative_memory" not in stored.payload:
                    record.narrative_memory = empty_narrative_memory()
                store.save_campaign(
                    campaign_id,
                    record.game_session,
                    journal=record.journal,
                    narrative_memory=record.narrative_memory,
                    lore_authority=record.lore_authority,
                )
                stored = store.get_campaign(campaign_id)
            metadata = store.mark_played(campaign_id)
            state = serialize_session_state(record.game_session, record.journal)
            record.combat_history = copy.deepcopy(stored.combat_history)
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
                narrative_memory=record.narrative_memory,
                lore_authority=record.lore_authority,
            )

    def save_campaign_locked(self, record: ManagedSession) -> dict[str, Any]:
        """Persist a campaign when the caller already holds its turn lock."""
        if record.campaign_id is None:
            raise CampaignNotActiveError("Campaign has no active session.")
        set_session_world_metadata(
            record.game_session,
            getattr(record.game_session, "world_metadata", None),
        )
        return self._require_campaign_store().save_campaign(
            record.campaign_id,
            record.game_session,
            journal=record.journal,
            narrative_memory=record.narrative_memory,
            lore_authority=record.lore_authority,
        )

    def autosave_turn(
        self,
        record: ManagedSession,
        player_message: str,
        narration: str,
        combat_history_entry: dict[str, Any] | None = None,
        narrative_memory: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Persist a successful turn; caller holds record.turn_lock."""
        candidate_memory = validate_narrative_memory(
            narrative_memory
            if narrative_memory is not None
            else record.narrative_memory
        )
        if record.campaign_id is None:
            record.narrative_memory = candidate_memory
            self._remember_combat_entry(record, combat_history_entry)
            return None
        set_session_world_metadata(
            record.game_session,
            getattr(record.game_session, "world_metadata", None),
        )
        metadata = self._require_campaign_store().save_campaign(
            record.campaign_id,
            record.game_session,
            turn_entry={
                "player_message": player_message,
                "narration": narration,
            },
            journal=record.journal,
            combat_history_entry=combat_history_entry,
            narrative_memory=candidate_memory,
            lore_authority=record.lore_authority,
        )
        record.narrative_memory = candidate_memory
        self._remember_combat_entry(record, combat_history_entry)
        return metadata

    @staticmethod
    def _remember_combat_entry(
        record: ManagedSession,
        entry: dict[str, Any] | None,
    ) -> None:
        if entry is None:
            return
        if any(
            existing.get("event_id") == entry["event_id"]
            for existing in record.combat_history
        ):
            return
        record.combat_history = (
            [*record.combat_history, copy.deepcopy(entry)]
        )[-MAX_COMBAT_HISTORY_ENTRIES:]

    def _require_campaign_store(self) -> CampaignStore:
        if self._campaign_store is None:
            raise CampaignStorageError("Campaign persistence is unavailable.")
        return self._campaign_store