"""Transactional SQLite registry for single-instance persistent campaigns."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Iterator

import game

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


_DATABASE_SCHEMA_VERSION = 4
MAX_COMBAT_HISTORY_ENTRIES = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_uuid4(campaign_id: str) -> bool:
    try:
        parsed = uuid.UUID(campaign_id)
    except (ValueError, TypeError, AttributeError):
        return False
    return parsed.version == 4 and str(parsed) == campaign_id.lower()


def default_campaign_db_path() -> Path:
    configured = os.environ.get("AI_DND_CAMPAIGN_DB")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(game.__file__).resolve().parent / path
        return path.resolve()
    return (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3")


class CampaignStore:
    """Stores canonical engine saves and safe campaign metadata transactionally."""

    def __init__(self, path: str | Path | None = None):
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

    def assert_current(self, campaign_id: str, session: Any,
                       connection: sqlite3.Connection | None = None) -> None:
        """Check the server-owned load token, again inside the write transaction."""
        self._validate_campaign_id(campaign_id)
        own_connection = connection is None
        connection = connection or self._connect()
        try:
            row = connection.execute(
                "SELECT revision FROM campaigns WHERE campaign_id = ?", (campaign_id,)
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
        now = _now()
        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO campaigns (
                        campaign_id, name, created_at, updated_at, last_played_at,
                        campaign_version, save_version, engine_hash, character_name,
                        character_race, character_class, character_level, location,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        campaign_id, safe_name, now, now, now,
                        CAMPAIGN_FORMAT_VERSION, details["save_version"],
                        self._engine_hash(), details["character_name"],
                        details["character_race"], details["character_class"],
                        details["character_level"], details["location"], payload_json,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM campaigns WHERE campaign_id = ?",
                    (campaign_id,),
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
    ) -> dict[str, Any]:
        self._validate_campaign_id(campaign_id)
        if journal is None or narrative_memory is None or lore_authority is None:
            current = self.get_campaign(campaign_id)
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
                    "SELECT name FROM campaigns WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()
                if existing is None:
                    raise CampaignNotFoundError("Campaign not found.")
                self.assert_current(campaign_id, session, connection)
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
                    WHERE campaign_id = ?
                    """,
                    (
                        now, now, CAMPAIGN_FORMAT_VERSION, details["save_version"],
                        self._engine_hash(), details["character_name"],
                        details["character_race"], details["character_class"],
                        details["character_level"], details["location"], payload_json,
                        campaign_id,
                    ),
                )
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

    def get_turn_action(
        self,
        campaign_id: str,
        action_id: str,
    ) -> dict[str, Any] | None:
        self._validate_campaign_id(campaign_id)
        if not _is_uuid4(action_id):
            raise CampaignValidationError("Turn action ID is invalid.")
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT request_hash, response_json
                FROM campaign_turn_actions
                WHERE campaign_id = ? AND action_id = ?
                """,
                (campaign_id, action_id),
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

    def mark_played(self, campaign_id: str) -> dict[str, Any]:
        self._validate_campaign_id(campaign_id)
        now = _now()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    "UPDATE campaigns SET last_played_at = ? WHERE campaign_id = ?",
                    (now, campaign_id),
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

    def list_campaigns(self) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM campaigns
                ORDER BY last_played_at DESC, created_at DESC
                """
            ).fetchall()
            return [self._metadata(row) for row in rows]
        except sqlite3.Error:
            raise CampaignStorageError("Campaign list is unavailable.") from None
        finally:
            connection.close()

    def campaign_exists(self, campaign_id: str) -> bool:
        self._validate_campaign_id(campaign_id)
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT 1 FROM campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone() is not None
        except sqlite3.Error:
            raise CampaignStorageError("Campaign availability could not be checked.") from None
        finally:
            connection.close()

    def delete_campaign(self, campaign_id: str) -> bool:
        """Atomic registry delete; existing FK cascades own history and receipts."""
        self._validate_campaign_id(campaign_id)
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    "DELETE FROM campaigns WHERE campaign_id = ?", (campaign_id,)
                )
                return cursor.rowcount == 1
        except sqlite3.Error:
            raise CampaignStorageError("Campaign could not be deleted safely.") from None

    def get_campaign(self, campaign_id: str) -> StoredCampaign:
        self._validate_campaign_id(campaign_id)
        connection = self._connect()
        try:
            # Payload and dependent history must come from one committed snapshot.
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
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
                    SELECT player_message, narration, created_at
                    FROM campaign_history WHERE campaign_id = ?
                    ORDER BY sequence ASC
                    """,
                    (campaign_id,),
                ).fetchall()
                history = [
                    validate_history_entry(dict(history_row))
                    for history_row in history_rows
                ]
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
        except (CampaignNotFoundError, CampaignCorruptError):
            raise
        except sqlite3.Error:
            raise CampaignStorageError("Campaign could not be loaded safely.") from None
        finally:
            connection.close()