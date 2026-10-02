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
from api.lore_authority import (
    PRODUCTION_REGISTRY,
    PRODUCTION_START_CATALOG,
    bind_campaign,
)
from api.lore_authority.campaign_catalog import (
    CampaignStartCatalog,
    InvalidCampaignStartError,
)
from api.lore_authority.models import CampaignLoreState, EntityType
from api.lore_authority.registry import LoreRegistry
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
from api.opening_narrative import initialize_campaign_opening
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
        campaign_start_catalog: CampaignStartCatalog | None = None,
        lore_registry: LoreRegistry | None = None,
    ):
        self._session_factory = session_factory or game.create_session
        self._campaign_store = campaign_store
        self._campaign_start_catalog = (
            campaign_start_catalog or PRODUCTION_START_CATALOG
        )
        self._lore_registry = lore_registry or PRODUCTION_REGISTRY
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
        campaign_start: dict[str, str] | None = None,
    ) -> tuple[str, str, ManagedSession, dict[str, Any]]:
        store = self._require_campaign_store()
        session = self._session_factory()
        if character is not None:
            configure_character(session, **character)
        narrative_memory = empty_narrative_memory()
        lore_authority = CampaignLoreState.legacy_unbound()
        if campaign_start is not None:
            try:
                pack, location = self._campaign_start_catalog.resolve(
                    setting_id=campaign_start["setting_id"],
                    region_pack_id=campaign_start["region_pack_id"],
                    region_id=campaign_start["region_id"],
                    starting_location_id=campaign_start["starting_location_id"],
                )
                lore_authority = bind_campaign(
                    lore_authority,
                    setting_profile=pack.setting_id,
                    world_id=pack.world_id,
                    epoch_id=pack.epoch_id,
                    region_id=pack.region_id,
                    starting_location_id=location.entity_id,
                    region_pack_id=pack.region_pack_id,
                    registry=self._lore_registry,
                    owner_approved=True,
                )
                self._install_canonical_start_location(
                    session,
                    location.entity_id,
                )
            except (KeyError, ValueError):
                raise InvalidCampaignStartError(
                    "Campaign start selection is not an installed verified option."
                ) from None
        # Resolve environment and journal only after the selected place is active.
        set_session_world_metadata(session)
        journal = create_initial_campaign_journal(
            session.world_state,
            getattr(session, "world_metadata", None),
        )
        campaign_id = str(uuid.uuid4())
        initialize_campaign_opening(session, campaign_id)
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

    def _install_canonical_start_location(
        self,
        session: Any,
        entity_id: str,
    ) -> None:
        """Register a verified city in the engine's existing location map."""
        entity = self._lore_registry.entity(entity_id)
        if entity is None or entity.entity_type not in {
            EntityType.CITY,
            EntityType.TOWN,
            EntityType.VILLAGE,
            EntityType.DISTRICT,
            EntityType.LANDMARK,
            EntityType.INN_TAVERN,
            EntityType.TEMPLE,
        }:
            raise InvalidCampaignStartError(
                "Campaign start location is not a verified location entity."
            )
        world_state = getattr(session, "world_state", None)
        if not isinstance(world_state, dict):
            raise InvalidCampaignStartError(
                "The game session does not expose a compatible world state."
            )
        locations = world_state.get("locations")
        if not isinstance(locations, dict):
            raise InvalidCampaignStartError(
                "The game session location registry is invalid."
            )

        engine_location_types = {
            EntityType.CITY: "city",
            EntityType.TOWN: "town",
            EntityType.VILLAGE: "village",
            EntityType.DISTRICT: "city",
            EntityType.LANDMARK: "landmark",
            EntityType.INN_TAVERN: "tavern",
            EntityType.TEMPLE: "temple",
        }
        canonical_location = {
            "id": entity.entity_id,
            "name": entity.canonical_name,
            "type": engine_location_types[entity.entity_type],
            "aliases": list(entity.aliases),
            "description": "",
        }
        existing = locations.get(entity.entity_id)
        if existing is not None and existing != canonical_location:
            raise InvalidCampaignStartError(
                "The engine location conflicts with the verified catalog."
            )
        locations[entity.entity_id] = canonical_location
        world_state["location"] = entity.entity_id

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