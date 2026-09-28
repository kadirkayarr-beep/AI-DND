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

from api.persistence.campaign_models import (
    CampaignCorruptError,
    CampaignIdConflictError,
    CampaignNotFoundError,
    CampaignStorageError,
    CampaignValidationError,
    StoredCampaign,
)
from api.persistence.campaign_validation import (
    CAMPAIGN_FORMAT_VERSION,
    serialize_campaign_payload,
    serialize_history_entry,
    validate_campaign_payload,
    validate_history_entry,
)


_DATABASE_SCHEMA_VERSION = 1


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
            self._validate_schema(connection)
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
            "payload_json",
        }
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(campaigns)").fetchall()
        }
        history_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(campaign_history)").fetchall()
        }
        if not expected.issubset(columns) or not {
            "campaign_id", "sequence", "player_message", "narration", "created_at"
        }.issubset(history_columns):
            raise CampaignStorageError("Campaign database schema is incomplete.")

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
        }

    @staticmethod
    def _validate_campaign_id(campaign_id: str) -> None:
        if not _is_uuid4(campaign_id):
            raise CampaignNotFoundError("Campaign not found.")

    def create_campaign(
        self,
        campaign_id: str,
        name: str,
        session: Any,
    ) -> dict[str, Any]:
        self._validate_campaign_id(campaign_id)
        payload = serialize_campaign_payload(session)
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
                return self._metadata(row)
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
    ) -> dict[str, Any]:
        self._validate_campaign_id(campaign_id)
        payload = serialize_campaign_payload(session)
        if turn_entry is not None:
            turn_entry = serialize_history_entry(
                turn_entry.get("player_message"),
                turn_entry.get("narration"),
            )
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
                connection.execute(
                    """
                    UPDATE campaigns SET
                        updated_at = ?, last_played_at = ?,
                        campaign_version = ?, save_version = ?, engine_hash = ?,
                        character_name = ?, character_race = ?, character_class = ?,
                        character_level = ?, location = ?, payload_json = ?
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
                row = connection.execute(
                    "SELECT * FROM campaigns WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()
                return self._metadata(row)
        except CampaignNotFoundError:
            raise
        except CampaignValidationError:
            raise
        except (sqlite3.Error, OSError, TypeError, ValueError):
            raise CampaignStorageError("Campaign could not be saved safely.") from None

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

    def get_campaign(self, campaign_id: str) -> StoredCampaign:
        self._validate_campaign_id(campaign_id)
        connection = self._connect()
        try:
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
            )
        except (CampaignNotFoundError, CampaignCorruptError):
            raise
        except sqlite3.Error:
            raise CampaignStorageError("Campaign could not be loaded safely.") from None
        finally:
            connection.close()