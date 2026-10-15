"""Transactional SQLite registry for single-instance persistent campaigns."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import uuid
from typing import Any, Iterator

import game

from api.auth import AuthenticationError, Principal, current_principal
from api.campaign_journal import empty_campaign_journal
from api.lore_authority.models import CampaignLoreState
from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignIdConflictError,
    CampaignNotFoundError,
    CampaignStorageError,
    CampaignStaleError,
    CampaignValidationError,
    StoredCampaign,
)
from api.persistence.campaign_validation import (
    CAMPAIGN_FORMAT_VERSION,
    serialize_combat_history_entry,
    serialize_campaign_payload,
    serialize_history_entry,
    validate_combat_history_entry,
    validate_campaign_payload,
    validate_history_entry,
)


_DATABASE_SCHEMA_VERSION = 6
MAX_COMBAT_HISTORY_ENTRIES = 50

# Operational generation receipts. Not campaign canon. The primary key is the
# cross-process guarantee that one trigger gets at most one proposal attempt.
_EMERGENCE_ATTEMPT_COLUMNS = (
    "campaign_id", "trigger_id", "attempt_id", "status", "owner_token",
    "canon_stamp", "proposal_json", "proposal_hash", "incident_id",
    "gate_outcome", "rejection_reason", "model_id", "prompt_contract_version",
    "envelope_version", "envelope_hash", "proposal_schema_version",
    "gate_policy_version", "incident_schema_version", "model_call_count",
    "created_at", "completed_at",
)
_EMERGENCE_ATTEMPTS_TABLE = """
    CREATE TABLE IF NOT EXISTS campaign_emergence_attempts (
        campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        trigger_id TEXT NOT NULL,
        attempt_id TEXT NOT NULL,
        status TEXT NOT NULL,
        owner_token TEXT NOT NULL,
        canon_stamp TEXT NOT NULL,
        proposal_json TEXT,
        proposal_hash TEXT,
        incident_id TEXT,
        gate_outcome TEXT,
        rejection_reason TEXT,
        model_id TEXT NOT NULL,
        prompt_contract_version INTEGER NOT NULL,
        envelope_version INTEGER NOT NULL,
        envelope_hash TEXT NOT NULL,
        proposal_schema_version INTEGER NOT NULL,
        gate_policy_version INTEGER NOT NULL,
        incident_schema_version INTEGER NOT NULL,
        model_call_count INTEGER NOT NULL CHECK (model_call_count BETWEEN 0 AND 1),
        created_at TEXT NOT NULL,
        completed_at TEXT,
        PRIMARY KEY (campaign_id, trigger_id)
    )
"""
_EMERGENCE_TERMINAL = ("accepted", "rejected", "stale", "no_proposal")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_uuid4(campaign_id: str) -> bool:
    try:
        parsed = uuid.UUID(campaign_id)
    except (ValueError, TypeError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == campaign_id.lower()


_SCHEMA_MIGRATION_ENV = "AI_DND_ALLOW_SCHEMA_MIGRATION"


def default_campaign_db_path() -> Path:
    configured = os.environ.get("AI_DND_CAMPAIGN_DB")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(game.__file__).resolve().parent / path
        return path.resolve()
    return (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3")


def _read_user_version(path: Path) -> int | None:
    """Read schema version without creating a file or changing journal mode."""
    if not path.exists():
        return None
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        raise CampaignStorageError("Campaign database could not be opened safely.") from None
    try:
        row = connection.execute("PRAGMA user_version").fetchone()
        return int(row[0])
    except (sqlite3.Error, TypeError, ValueError):
        raise CampaignStorageError("Campaign database could not be opened safely.") from None
    finally:
        connection.close()


_OWNED_SQL = (
    "ownership_state = 'owned' AND owner_issuer = ? AND owner_subject = ?"
)


class CampaignStore:
    """Stores canonical engine saves and safe campaign metadata transactionally."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        bound_principal: Principal | None = None,
        allow_schema_migration: bool = False,
    ):
        if bound_principal is not None and type(bound_principal) is not Principal:
            raise AuthenticationError("No server authenticator is configured.")
        self.bound_principal = bound_principal
        self._allow_schema_migration = allow_schema_migration is True
        self.path = Path(path).expanduser().resolve() if path else default_campaign_db_path()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except CampaignStorageError:
            raise
        except (OSError, sqlite3.Error):
            raise CampaignStorageError("Campaign storage is unavailable.") from None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=20.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 20000")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        existing = _read_user_version(self.path)
        if existing is not None and existing > _DATABASE_SCHEMA_VERSION:
            raise CampaignStorageError(
                "Campaign database version is newer than this server supports."
            )
        if (
            existing is not None
            and existing < _DATABASE_SCHEMA_VERSION
            and not self._allow_schema_migration
        ):
            raise CampaignStorageError(
                "Campaign database schema requires explicit migration approval."
            )
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version > _DATABASE_SCHEMA_VERSION:
                raise CampaignStorageError(
                    "Campaign database version is newer than this server supports."
                )
            if current_version == 0:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS campaigns (
                        campaign_id TEXT PRIMARY KEY NOT NULL,
                        name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_played_at TEXT NOT NULL,
                        campaign_version INTEGER NOT NULL,
                        save_version INTEGER NOT NULL,
                        engine_hash TEXT NOT NULL,
                        character_name TEXT NOT NULL,
                        character_race TEXT NOT NULL,
                        character_class TEXT NOT NULL,
                        character_level INTEGER NOT NULL,
                        location TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS campaign_history (
                        campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id)
                            ON DELETE CASCADE,
                        sequence INTEGER NOT NULL,
                        player_message TEXT NOT NULL,
                        narration TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (campaign_id, sequence)
                    );
                    PRAGMA user_version = 1;
                    """
                )
                current_version = 1
            if current_version == 1:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        CREATE TABLE campaign_combat_history (
                            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id)
                                ON DELETE CASCADE,
                            sequence INTEGER NOT NULL CHECK (sequence > 0),
                            event_id TEXT NOT NULL,
                            turn_index INTEGER NOT NULL CHECK (turn_index >= 0),
                            result_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            PRIMARY KEY (campaign_id, sequence),
                            UNIQUE (campaign_id, event_id)
                        )
                        """
                    )
                    connection.execute("PRAGMA user_version = 2")
                    connection.commit()
                    current_version = 2
                except Exception:
                    connection.rollback()
                    raise
            if current_version == 2:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS campaign_turn_actions (
                            campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id)
                                ON DELETE CASCADE,
                            action_id TEXT NOT NULL,
                            request_hash TEXT NOT NULL,
                            response_json TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            PRIMARY KEY (campaign_id, action_id)
                        )
                        """
                    )
                    connection.execute("PRAGMA user_version = 3")
                    connection.commit()
                    current_version = 3
                except Exception:
                    connection.rollback()
                    raise
            if current_version == 3:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    # A different opener may have migrated while we waited for the lock.
                    if int(connection.execute("PRAGMA user_version").fetchone()[0]) == 3:
                        columns = {row["name"] for row in connection.execute("PRAGMA table_info(campaigns)")}
                        if "revision" not in columns:
                            connection.execute(
                                "ALTER TABLE campaigns ADD COLUMN revision INTEGER NOT NULL DEFAULT 0"
                            )
                        connection.execute("PRAGMA user_version = 4")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version == 4:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    if int(connection.execute("PRAGMA user_version").fetchone()[0]) == 4:
                        connection.execute(_EMERGENCE_ATTEMPTS_TABLE)
                        connection.execute("PRAGMA user_version = 5")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version == 5:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    # Re-read after taking the write lock. Another opener may
                    # already have added the columns. Never assign an owner.
                    if int(connection.execute("PRAGMA user_version").fetchone()[0]) == 5:
                        columns = {
                            row["name"]
                            for row in connection.execute("PRAGMA table_info(campaigns)")
                        }
                        if "owner_issuer" not in columns:
                            connection.execute(
                                "ALTER TABLE campaigns ADD COLUMN owner_issuer TEXT"
                            )
                        if "owner_subject" not in columns:
                            connection.execute(
                                "ALTER TABLE campaigns ADD COLUMN owner_subject TEXT"
                            )
                        if "ownership_state" not in columns:
                            connection.execute(
                                "ALTER TABLE campaigns ADD COLUMN ownership_state "
                                "TEXT NOT NULL DEFAULT 'unowned'"
                            )
                        connection.execute("PRAGMA user_version = 6")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            self._validate_schema(connection)
            # Reserve identities that old event APIs kept in canonical journals.
            # Do this before a later bounded journal trim can discard provenance.
            connection.execute("BEGIN IMMEDIATE")
            try:
                for row in connection.execute("SELECT campaign_id, payload_json FROM campaigns").fetchall():
                    try:
                        payload = json.loads(row["payload_json"])
                    except (json.JSONDecodeError, TypeError):
                        # A corrupt campaign must not prevent unrelated ones opening.
                        continue
                    journal = payload.get("journal", {}) if isinstance(payload, dict) else {}
                    if isinstance(journal, dict) and isinstance(journal.get("notable_events", []), list):
                        self._reserve_legacy_events(connection, str(row["campaign_id"]), journal)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        except CampaignStorageError:
            raise
        except (sqlite3.Error, TypeError, ValueError):
            raise CampaignStorageError("Campaign database could not be opened safely.") from None
        finally:
            connection.close()

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        expected = {
            "campaign_id", "name", "created_at", "updated_at", "last_played_at",
            "campaign_version", "save_version", "engine_hash", "character_name",
            "character_race", "character_class", "character_level", "location",
            "payload_json", "revision",
            "owner_issuer", "owner_subject", "ownership_state",
        }
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(campaigns)").fetchall()
        }
        history_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(campaign_history)").fetchall()
        }
        combat_history_columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(campaign_combat_history)"
            ).fetchall()
        }
        turn_action_columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(campaign_turn_actions)"
            ).fetchall()
        }
        if not expected.issubset(columns) or not {
            "campaign_id", "sequence", "player_message", "narration", "created_at"
        }.issubset(history_columns) or not {
            "campaign_id", "sequence", "event_id", "turn_index", "result_json",
            "created_at",
        }.issubset(combat_history_columns):
            raise CampaignStorageError("Campaign database schema is incomplete.")
        if not {
            "campaign_id", "action_id", "request_hash", "response_json", "created_at"
        }.issubset(turn_action_columns):
            raise CampaignStorageError("Campaign database schema is incomplete.")
        attempt_columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(campaign_emergence_attempts)"
            ).fetchall()
        }
        if not set(_EMERGENCE_ATTEMPT_COLUMNS).issubset(attempt_columns):
            raise CampaignStorageError("Campaign database schema is incomplete.")

    @staticmethod
    def _reserve_legacy_events(connection: sqlite3.Connection, campaign_id: str,
                               journal: dict[str, Any]) -> None:
        candidates = {}
        for event in journal.get("notable_events", []):
            if not isinstance(event, dict):
                continue
            prior = event.get("event_result")
            if event.get("event_type") != "ambient_event_outcome" or not isinstance(prior, dict):
                continue
            action_id = prior.get("action_id")
            if not _is_uuid4(action_id):
                continue
            if not all(isinstance(prior.get(k), str) for k in ("event_instance_id", "action")):
                request = {"unverifiable_legacy_id": action_id}
            else:
                request = {"command": "ambient_event", "event_instance_id": prior["event_instance_id"],
                           "action": prior["action"]}
            digest = hashlib.sha256(json.dumps(
                request, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            if action_id in candidates and candidates[action_id][0] != digest:
                digest = hashlib.sha256(("ambiguous_legacy_id:" + action_id).encode()).hexdigest()
            candidates[action_id] = (digest, {"action_id": action_id, "legacy_ambient_result": {
                "transition_id": prior.get("transition_id"), "canonical_event_id": event.get("event_id"),
            }})
        for action_id, (digest, response) in candidates.items():
            connection.execute(
                """INSERT OR IGNORE INTO campaign_turn_actions
                   (campaign_id, action_id, request_hash, response_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (campaign_id, action_id, digest, json.dumps(response, ensure_ascii=False,
                                                          separators=(",", ":"), allow_nan=False), _now()),
            )

    @staticmethod
    def _engine_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        engine_save = payload["engine_save"]
        player = engine_save["player"]
        world = engine_save["world_state"]
        return {
            "save_version": int(engine_save["version"]),
            "character_name": str(player["name"]),
            "character_race": str(player["race"]),
            "character_class": str(player["class"]),
            "character_level": int(player["level"]),
            "location": str(world["location"]),
        }

    @staticmethod
    def _engine_hash() -> str:
        try:
            return hashlib.sha256(Path(game.__file__).resolve().read_bytes()).hexdigest()
        except OSError:
            raise CampaignStorageError("Campaign engine metadata is unavailable.") from None

    @staticmethod
    def _metadata(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "campaign_id": str(row["campaign_id"]),
            "name": str(row["name"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_played_at": str(row["last_played_at"]),
            "save_version": int(row["save_version"]),
            "character_name": str(row["character_name"]),
            "character_race": str(row["character_race"]),
            "character_class": str(row["character_class"]),
            "character_level": int(row["character_level"]),
            "location": str(row["location"]),
            "revision": int(row["revision"]),
        }

    @staticmethod
    def _validate_campaign_id(campaign_id: str) -> None:
        if not _is_uuid4(campaign_id):
            raise CampaignNotFoundError("Campaign not found.")

    def _owner_pair(self, principal: Principal | None) -> tuple[str, str]:
        """Explicit principal, then this request, then a test store binding."""
        resolved = principal if type(principal) is Principal else None
        if resolved is None:
            active = current_principal()
            if type(active) is Principal:
                resolved = active
        if resolved is None and type(self.bound_principal) is Principal:
            resolved = self.bound_principal
        if type(resolved) is not Principal:
            raise AuthenticationError("No server authenticator is configured.")
        return resolved.issuer, resolved.subject

    def assert_current(self, campaign_id: str, session: Any,
                       connection: sqlite3.Connection | None = None,
                       principal: Principal | None = None) -> None:
        """Check the server-owned load token, again inside the write transaction."""
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(principal)
        own_connection = connection is None
        connection = connection or self._connect()
        try:
            row = connection.execute(
                f"SELECT revision FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                (campaign_id, issuer, subject),
            ).fetchone()
            if row is None:
                raise CampaignNotFoundError("Campaign not found.")
            token = getattr(session, "_campaign_persistence_version", None)
            world_id = session.world_state.get("campaign_id")
            if token != (campaign_id, int(row["revision"])) or world_id not in (None, campaign_id):
                raise CampaignStaleError("Campaign changed; resume it before submitting a new action.")
        except sqlite3.Error:
            raise CampaignStorageError("Campaign revision could not be checked safely.") from None
        finally:
            if own_connection:
                connection.close()

    def create_campaign(
        self,
        campaign_id: str,
        name: str,
        session: Any,
        journal: dict[str, Any] | None = None,
        narrative_memory: dict[str, Any] | None = None,
        lore_authority: CampaignLoreState | dict[str, Any] | None = None,
        principal: Principal | None = None,
    ) -> dict[str, Any]:
        self._validate_campaign_id(campaign_id)
        payload = serialize_campaign_payload(
            session,
            journal,
            narrative_memory,
            lore_authority,
        )
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise CampaignValidationError("Campaign name is invalid.")
        from api.persistence.campaign_validation import ensure_no_configured_secrets

        safe_name = name.strip()
        ensure_no_configured_secrets(safe_name)
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        details = self._engine_metadata(payload)
        issuer, subject = self._owner_pair(principal)
        now = _now()
        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO campaigns (
                        campaign_id, name, created_at, updated_at, last_played_at,
                        campaign_version, save_version, engine_hash, character_name,
                        character_race, character_class, character_level, location,
                        payload_json, owner_issuer, owner_subject, ownership_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'owned')
                    """,
                    (
                        campaign_id, safe_name, now, now, now,
                        CAMPAIGN_FORMAT_VERSION, details["save_version"],
                        self._engine_hash(), details["character_name"],
                        details["character_race"], details["character_class"],
                        details["character_level"], details["location"], payload_json,
                        issuer, subject,
                    ),
                )
                row = connection.execute(
                    f"SELECT * FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                    (campaign_id, issuer, subject),
                ).fetchone()
                metadata = self._metadata(row)
            session._campaign_persistence_version = (campaign_id, metadata["revision"])
            return metadata
        except sqlite3.IntegrityError:
            raise CampaignIdConflictError("Campaign identifier already exists.") from None
        except CampaignValidationError:
            raise
        except CampaignIdConflictError:
            raise
        except (sqlite3.Error, OSError, TypeError, ValueError):
            raise CampaignStorageError("Campaign could not be created safely.") from None

    def save_campaign(
        self,
        campaign_id: str,
        session: Any,
        turn_entry: dict[str, str] | None = None,
        journal: dict[str, Any] | None = None,
        combat_history_entry: dict[str, Any] | None = None,
        narrative_memory: dict[str, Any] | None = None,
        lore_authority: CampaignLoreState | dict[str, Any] | None = None,
        turn_action_receipt: dict[str, Any] | None = None,
        emergence_attempt: dict[str, Any] | None = None,
        principal: Principal | None = None,
    ) -> dict[str, Any]:
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(principal)
        if journal is None or narrative_memory is None or lore_authority is None:
            current = self.get_campaign(campaign_id, principal=principal)
            if journal is None:
                journal = current.payload.get("journal", empty_campaign_journal())
            if narrative_memory is None:
                narrative_memory = current.payload.get("narrative_memory")
            if lore_authority is None:
                lore_authority = current.payload.get("lore_authority")
        payload = serialize_campaign_payload(
            session,
            journal,
            narrative_memory,
            lore_authority,
        )
        if turn_entry is not None:
            turn_entry = serialize_history_entry(
                turn_entry.get("player_message"),
                turn_entry.get("narration"),
            )
        if combat_history_entry is not None:
            combat_history_entry = serialize_combat_history_entry(
                combat_history_entry
            )
        action_json = None
        if turn_action_receipt is not None:
            action_id = turn_action_receipt.get("action_id")
            request_hash = turn_action_receipt.get("request_hash")
            response = turn_action_receipt.get("response")
            if (
                not isinstance(action_id, str)
                or not _is_uuid4(action_id)
                or not isinstance(request_hash, str)
                or len(request_hash) != 64
                or any(char not in "0123456789abcdef" for char in request_hash)
                or not isinstance(response, dict)
                or response.get("action_id") != action_id
            ):
                raise CampaignValidationError("Turn action receipt is invalid.")
            try:
                action_json = json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            except (TypeError, ValueError):
                raise CampaignValidationError(
                    "Turn action receipt is invalid."
                ) from None
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        details = self._engine_metadata(payload)
        now = _now()
        try:
            with self._transaction() as connection:
                existing = connection.execute(
                    f"SELECT name FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                    (campaign_id, issuer, subject),
                ).fetchone()
                if existing is None:
                    raise CampaignNotFoundError("Campaign not found.")
                self.assert_current(campaign_id, session, connection, principal)
                if turn_action_receipt is not None:
                    prior_action = connection.execute(
                        """
                        SELECT request_hash FROM campaign_turn_actions
                        WHERE campaign_id = ? AND action_id = ?
                        """,
                        (campaign_id, turn_action_receipt["action_id"]),
                    ).fetchone()
                    if prior_action is not None:
                        raise CampaignValidationError(
                            "Turn action has already been committed."
                        )
                connection.execute(
                    """
                    UPDATE campaigns SET
                        updated_at = ?, last_played_at = ?,
                        campaign_version = ?, save_version = ?, engine_hash = ?,
                        character_name = ?, character_race = ?, character_class = ?,
                        character_level = ?, location = ?, payload_json = ?,
                        revision = revision + 1
                    WHERE campaign_id = ? AND ownership_state = 'owned'
                        AND owner_issuer = ? AND owner_subject = ?
                    """,
                    (
                        now, now, CAMPAIGN_FORMAT_VERSION, details["save_version"],
                        self._engine_hash(), details["character_name"],
                        details["character_race"], details["character_class"],
                        details["character_level"], details["location"], payload_json,
                        campaign_id, issuer, subject,
                    ),
                )
                if connection.execute("SELECT changes()").fetchone()[0] != 1:
                    raise CampaignNotFoundError("Campaign not found.")
                if turn_entry is not None:
                    next_sequence = int(
                        connection.execute(
                            """
                            SELECT COALESCE(MAX(sequence), 0) + 1
                            FROM campaign_history WHERE campaign_id = ?
                            """,
                            (campaign_id,),
                        ).fetchone()[0]
                    )
                    connection.execute(
                        """
                        INSERT INTO campaign_history (
                            campaign_id, sequence, player_message, narration, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            campaign_id,
                            next_sequence,
                            turn_entry["player_message"],
                            turn_entry["narration"],
                            now,
                        ),
                    )
                if combat_history_entry is not None:
                    next_sequence = int(
                        connection.execute(
                            """
                            SELECT COALESCE(MAX(sequence), 0) + 1
                            FROM campaign_combat_history WHERE campaign_id = ?
                            """,
                            (campaign_id,),
                        ).fetchone()[0]
                    )
                    result_json = json.dumps(
                        combat_history_entry["result"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    connection.execute(
                        """
                        INSERT INTO campaign_combat_history (
                            campaign_id, sequence, event_id, turn_index,
                            result_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            campaign_id,
                            next_sequence,
                            combat_history_entry["event_id"],
                            combat_history_entry["turn_index"],
                            result_json,
                            now,
                        ),
                    )
                if emergence_attempt is not None:
                    self._finish_attempt(connection, campaign_id, emergence_attempt, now)
                if turn_action_receipt is not None and action_json is not None:
                    connection.execute(
                        """
                        INSERT INTO campaign_turn_actions (
                            campaign_id, action_id, request_hash, response_json, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            campaign_id,
                            turn_action_receipt["action_id"],
                            turn_action_receipt["request_hash"],
                            action_json,
                            now,
                        ),
                    )
                connection.execute(
                    """
                    DELETE FROM campaign_combat_history
                    WHERE campaign_id = ? AND sequence NOT IN (
                        SELECT sequence FROM campaign_combat_history
                        WHERE campaign_id = ?
                        ORDER BY sequence DESC
                        LIMIT ?
                    )
                    """,
                    (
                        campaign_id,
                        campaign_id,
                        MAX_COMBAT_HISTORY_ENTRIES,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM campaigns WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()
                metadata = self._metadata(row)
            session._campaign_persistence_version = (campaign_id, metadata["revision"])
            return metadata
        except CampaignNotFoundError:
            raise
        except CampaignValidationError:
            raise
        except (sqlite3.Error, OSError, TypeError, ValueError):
            raise CampaignStorageError("Campaign could not be saved safely.") from None

    @staticmethod
    def _attempt_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return None if row is None else {key: row[key] for key in _EMERGENCE_ATTEMPT_COLUMNS}

    def claim_emergence_attempt(self, row: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Insert-first claim. The loser reads the row that already exists."""
        self._validate_campaign_id(row["campaign_id"])
        values = dict(row, status="claiming", created_at=_now(), completed_at=None,
                      proposal_json=None, proposal_hash=None, incident_id=None,
                      gate_outcome=None, rejection_reason=None, model_call_count=0)
        try:
            with self._transaction() as connection:
                owned = connection.execute(
                    f"SELECT 1 FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                    (row["campaign_id"], *self._owner_pair(None)),
                ).fetchone()
                if owned is None:
                    raise CampaignNotFoundError("Campaign not found.")
                try:
                    connection.execute(
                        f"INSERT INTO campaign_emergence_attempts ({', '.join(_EMERGENCE_ATTEMPT_COLUMNS)}) "
                        f"VALUES ({', '.join('?' for _ in _EMERGENCE_ATTEMPT_COLUMNS)})",
                        tuple(values[key] for key in _EMERGENCE_ATTEMPT_COLUMNS),
                    )
                    won = True
                except sqlite3.IntegrityError:
                    won = False
                current = self._attempt_row(connection.execute(
                    "SELECT * FROM campaign_emergence_attempts WHERE campaign_id = ? AND trigger_id = ?",
                    (row["campaign_id"], row["trigger_id"]),
                ).fetchone())
        except sqlite3.Error:
            raise CampaignStorageError("Emergence attempt could not be claimed.") from None
        if current is None:
            raise CampaignStorageError("Emergence attempt could not be claimed.")
        return won, current

    def update_emergence_attempt(
        self, campaign_id: str, trigger_id: str, owner_token: str,
        expected: tuple[str, ...], fields: dict[str, Any],
    ) -> bool:
        """Owner-only move. Terminal rows never move again."""
        self._validate_campaign_id(campaign_id)
        allowed = {"status", "owner_token", "proposal_json", "proposal_hash", "incident_id",
                   "gate_outcome", "rejection_reason", "model_call_count", "completed_at"}
        if not set(fields).issubset(allowed) or any(status in _EMERGENCE_TERMINAL for status in expected):
            raise CampaignValidationError("Emergence attempt update is invalid.")
        if fields.get("status") in _EMERGENCE_TERMINAL:
            fields = dict(fields, completed_at=_now())
        assignments = ", ".join(f"{key} = ?" for key in fields)
        issuer, subject = self._owner_pair(None)
        try:
            with self._transaction() as connection:
                owned = connection.execute(
                    f"SELECT 1 FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                    (campaign_id, issuer, subject),
                ).fetchone()
                if owned is None:
                    raise CampaignNotFoundError("Campaign not found.")
                cursor = connection.execute(
                    f"UPDATE campaign_emergence_attempts SET {assignments} "
                    f"WHERE campaign_id = ? AND trigger_id = ? AND owner_token = ? "
                    f"AND status IN ({', '.join('?' for _ in expected)})",
                    (*fields.values(), campaign_id, trigger_id, owner_token, *expected),
                )
                return cursor.rowcount == 1
        except sqlite3.Error:
            raise CampaignStorageError("Emergence attempt could not be updated.") from None

    @staticmethod
    def _finish_attempt(connection, campaign_id, attempt, now) -> None:
        cursor = connection.execute(
            """
            UPDATE campaign_emergence_attempts
            SET status = 'accepted', incident_id = ?, gate_outcome = ?, completed_at = ?
            WHERE campaign_id = ? AND trigger_id = ? AND owner_token = ?
              AND status = 'proposal_stored'
            """,
            (attempt["incident_id"], attempt["gate_outcome"], now, campaign_id,
             attempt["trigger_id"], attempt["owner_token"]),
        )
        if cursor.rowcount != 1:
            raise CampaignValidationError("Emergence attempt is no longer owned by this turn.")

    def get_emergence_attempt(self, campaign_id: str, trigger_id: str) -> dict[str, Any] | None:
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(None)
        connection = self._connect()
        try:
            return self._attempt_row(connection.execute(
                """
                SELECT attempts.*
                FROM campaign_emergence_attempts AS attempts
                JOIN campaigns ON campaigns.campaign_id = attempts.campaign_id
                WHERE attempts.campaign_id = ? AND attempts.trigger_id = ?
                  AND campaigns.ownership_state = 'owned'
                  AND campaigns.owner_issuer = ? AND campaigns.owner_subject = ?
                """,
                (campaign_id, trigger_id, issuer, subject),
            ).fetchone())
        except sqlite3.Error:
            raise CampaignStorageError("Emergence attempt could not be read.") from None
        finally:
            connection.close()

    def compact_emergence_attempts(self, campaign_id: str) -> int:
        """Drop raw proposal bytes on terminal rows. Keys and hashes stay."""
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(None)
        try:
            with self._transaction() as connection:
                owned = connection.execute(
                    f"SELECT 1 FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                    (campaign_id, issuer, subject),
                ).fetchone()
                if owned is None:
                    raise CampaignNotFoundError("Campaign not found.")
                cursor = connection.execute(
                    f"UPDATE campaign_emergence_attempts SET proposal_json = NULL "
                    f"WHERE campaign_id = ? AND proposal_json IS NOT NULL AND proposal_hash IS NOT NULL "
                    f"AND status IN ({', '.join('?' for _ in _EMERGENCE_TERMINAL)})",
                    (campaign_id, *_EMERGENCE_TERMINAL),
                )
                return cursor.rowcount
        except sqlite3.Error:
            raise CampaignStorageError("Emergence attempts could not be compacted.") from None

    def get_turn_action(
        self,
        campaign_id: str,
        action_id: str,
        principal: Principal | None = None,
    ) -> dict[str, Any] | None:
        self._validate_campaign_id(campaign_id)
        if not _is_uuid4(action_id):
            raise CampaignValidationError("Turn action ID is invalid.")
        issuer, subject = self._owner_pair(principal)
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT actions.request_hash, actions.response_json
                FROM campaign_turn_actions AS actions
                JOIN campaigns ON campaigns.campaign_id = actions.campaign_id
                WHERE actions.campaign_id = ? AND actions.action_id = ?
                  AND campaigns.ownership_state = 'owned'
                  AND campaigns.owner_issuer = ?
                  AND campaigns.owner_subject = ?
                """,
                (campaign_id, action_id, issuer, subject),
            ).fetchone()
            if row is None:
                return None
            response = json.loads(str(row["response_json"]))
            request_hash = str(row["request_hash"])
            if (
                not isinstance(response, dict)
                or response.get("action_id") != action_id
                or len(request_hash) != 64
                or any(char not in "0123456789abcdef" for char in request_hash)
            ):
                raise CampaignCorruptError("Campaign action receipt is invalid.")
            return {"request_hash": request_hash, "response": response}
        except CampaignCorruptError:
            raise
        except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError):
            raise CampaignStorageError(
                "Campaign action receipt could not be loaded safely."
            ) from None
        finally:
            connection.close()

    def mark_played(self, campaign_id: str, principal: Principal | None = None) -> dict[str, Any]:
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(principal)
        now = _now()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    f"UPDATE campaigns SET last_played_at = ? WHERE campaign_id = ? AND {_OWNED_SQL}",
                    (now, campaign_id, issuer, subject),
                )
                if cursor.rowcount != 1:
                    raise CampaignNotFoundError("Campaign not found.")
                row = connection.execute(
                    "SELECT * FROM campaigns WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()
                return self._metadata(row)
        except CampaignNotFoundError:
            raise
        except sqlite3.Error:
            raise CampaignStorageError("Campaign could not be opened safely.") from None

    def list_campaigns(self, principal: Principal | None = None) -> list[dict[str, Any]]:
        issuer, subject = self._owner_pair(principal)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT * FROM campaigns
                WHERE {_OWNED_SQL}
                ORDER BY last_played_at DESC, created_at DESC
                """,
                (issuer, subject),
            ).fetchall()
            return [self._metadata(row) for row in rows]
        except sqlite3.Error:
            raise CampaignStorageError("Campaign list is unavailable.") from None
        finally:
            connection.close()

    def campaign_exists(self, campaign_id: str, principal: Principal | None = None) -> bool:
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(principal)
        connection = self._connect()
        try:
            return connection.execute(
                f"SELECT 1 FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                (campaign_id, issuer, subject),
            ).fetchone() is not None
        except sqlite3.Error:
            raise CampaignStorageError("Campaign availability could not be checked.") from None
        finally:
            connection.close()

    def delete_campaign(self, campaign_id: str, principal: Principal | None = None) -> bool:
        """Atomic registry delete; existing FK cascades own history and receipts."""
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(principal)
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    f"DELETE FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                    (campaign_id, issuer, subject),
                )
                return cursor.rowcount == 1
        except sqlite3.Error:
            raise CampaignStorageError("Campaign could not be deleted safely.") from None

    def get_campaign(self, campaign_id: str, principal: Principal | None = None) -> StoredCampaign:
        self._validate_campaign_id(campaign_id)
        issuer, subject = self._owner_pair(principal)
        connection = self._connect()
        try:
            # Payload and dependent history must come from one committed snapshot.
            connection.execute("BEGIN")
            row = connection.execute(
                f"SELECT * FROM campaigns WHERE campaign_id = ? AND {_OWNED_SQL}",
                (campaign_id, issuer, subject),
            ).fetchone()
            if row is None:
                raise CampaignNotFoundError("Campaign not found.")
            try:
                if int(row["campaign_version"]) != CAMPAIGN_FORMAT_VERSION:
                    raise CampaignCorruptError("Campaign version is unsupported.")
                payload = json.loads(str(row["payload_json"]))
                validate_campaign_payload(payload)
                if int(row["save_version"]) != int(payload["engine_save"]["version"]):
                    raise CampaignCorruptError("Campaign save version metadata is inconsistent.")
                engine_metadata = self._engine_metadata(payload)
                for field in (
                    "character_name",
                    "character_race",
                    "character_class",
                    "character_level",
                    "location",
                ):
                    if row[field] != engine_metadata[field]:
                        raise CampaignCorruptError("Campaign metadata is inconsistent.")
                history_rows = connection.execute(
                    """
                    SELECT sequence, player_message, narration, created_at
                    FROM campaign_history WHERE campaign_id = ?
                    ORDER BY sequence ASC
                    """,
                    (campaign_id,),
                ).fetchall()
                history = [
                    validate_history_entry({
                        "player_message": history_row["player_message"],
                        "narration": history_row["narration"],
                        "created_at": history_row["created_at"],
                    })
                    for history_row in history_rows
                ]
                # Read-only projection of already committed, Python-validated skill
                # outcomes. Do not change the strict campaign_history save format.
                # Bind by BOTH resolved turn number and accepted narration; never
                # attach a receipt to unrelated or ambiguous older history.
                from api.schemas import SkillCheckResult
                skill_rows = connection.execute(
                    """
                    SELECT action_id, request_hash, response_json
                    FROM campaign_turn_actions
                    WHERE campaign_id = ?
                    ORDER BY rowid ASC
                    """,
                    (campaign_id,),
                ).fetchall()
                accepted = {}
                ambiguous = set()
                existing = {
                    history_row["sequence"]: history_row
                    for history_row in history_rows
                }
                for receipt_row in skill_rows:
                    try:
                        # Only the committed receipt for this campaign/turn may
                        # annotate history; a different or damaged identity is
                        # not evidence for a player-visible skill result.
                        request_hash = receipt_row["request_hash"]
                        if (not isinstance(request_hash, str)
                                or len(request_hash) != 64
                                or any(c not in "0123456789abcdef" for c in request_hash)):
                            continue
                        receipt = json.loads(str(receipt_row["response_json"]))
                        if not isinstance(receipt, dict) or receipt.get("action_id") != receipt_row["action_id"]:
                            continue
                        skill = receipt.get("skill_check_result")
                        if not isinstance(skill, dict) or skill.get("action_id") != receipt_row["action_id"]:
                            continue
                        state = receipt.get("state")
                        turn_number = state.get("turn_index") if isinstance(state, dict) else None
                        matched_history_row = existing.get(turn_number) if type(turn_number) is int else None
                        if matched_history_row is None or receipt.get("narration") != matched_history_row["narration"]:
                            continue
                        validated = SkillCheckResult.model_validate(skill).model_dump(exclude_none=True)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                    if turn_number in accepted:
                        ambiguous.add(turn_number)
                    else:
                        accepted[turn_number] = validated
                for index, history_row in enumerate(history_rows):
                    if history_row["sequence"] in accepted and history_row["sequence"] not in ambiguous:
                        history[index]["skill_check_result"] = accepted[history_row["sequence"]]
                combat_rows = connection.execute(
                    """
                    SELECT sequence, event_id, turn_index, result_json, created_at
                    FROM campaign_combat_history
                    WHERE campaign_id = ?
                    ORDER BY sequence ASC
                    """,
                    (campaign_id,),
                ).fetchall()
                if len(combat_rows) > MAX_COMBAT_HISTORY_ENTRIES:
                    raise CampaignCorruptError(
                        "Campaign combat history exceeds the supported limit."
                    )
                combat_history = []
                for combat_row in combat_rows:
                    if (
                        type(combat_row["sequence"]) is not int
                        or combat_row["sequence"] < 1
                        or not isinstance(combat_row["created_at"], str)
                        or not combat_row["created_at"].strip()
                    ):
                        raise CampaignCorruptError(
                            "Campaign combat history is invalid."
                        )
                    combat_history.append(
                        validate_combat_history_entry(
                            {
                                "event_id": str(combat_row["event_id"]),
                                "turn_index": combat_row["turn_index"],
                                "result": json.loads(
                                    str(combat_row["result_json"])
                                ),
                            }
                        )
                    )
            except CampaignCorruptError:
                raise
            except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                raise CampaignCorruptError(
                    "Campaign save could not be validated safely."
                ) from None
            return StoredCampaign(
                metadata=self._metadata(row),
                payload=payload,
                history=history,
                combat_history=combat_history,
            )
        except (CampaignNotFoundError, CampaignCorruptError, AuthenticationError):
            raise
        except sqlite3.Error:
            raise CampaignStorageError("Campaign could not be loaded safely.") from None
        finally:
            connection.close()


class StartupCampaignStore:
    """Opens configured storage on first use.

    Importing the API does not construct a CampaignStore. A missing
    AI_DND_CAMPAIGN_DB setting fails closed. An older schema is not
    upgraded unless AI_DND_ALLOW_SCHEMA_MIGRATION=1.
    """

    def __init__(self) -> None:
        self._store: CampaignStore | None = None
        self._lock = threading.Lock()
        self.bound_principal = None

    def _open(self) -> CampaignStore:
        if self._store is not None:
            return self._store
        with self._lock:
            if self._store is not None:
                return self._store
            configured = os.environ.get("AI_DND_CAMPAIGN_DB", "")
            if type(configured) is not str or configured.strip() == "":
                raise CampaignStorageError("Campaign database is not configured.")
            self._store = CampaignStore(
                configured,
                allow_schema_migration=os.environ.get(_SCHEMA_MIGRATION_ENV) == "1",
            )
            return self._store

    def __getattr__(self, name: str) -> Any:
        return getattr(self._open(), name)
