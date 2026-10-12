"""Schema 5 to 6 ownership columns. Temporary SQLite only.

Opening this store migrates the given file. These tests never open the
live campaigns.sqlite3 database.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

import game
from api.persistence.campaign_store import CampaignStore, _EMERGENCE_ATTEMPTS_TABLE


from api.tests.auth_fixture import TEST_PLAYER
_LIVE_DATABASE = (
    Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3"
).resolve()
_STABLE_CAMPAIGN_COLUMNS = (
    "campaign_id", "name", "created_at", "updated_at", "last_played_at",
    "campaign_version", "save_version", "engine_hash", "character_name",
    "character_race", "character_class", "character_level", "location",
    "payload_json", "revision",
)
_RELATED_TABLES = (
    "campaign_history",
    "campaign_combat_history",
    "campaign_turn_actions",
    "campaign_emergence_attempts",
)


def _require_temporary(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == _LIVE_DATABASE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return resolved


def _payload(campaign_id: str) -> str:
    return json.dumps(
        {
            "version": 1,
            "engine_save": {
                "version": 4,
                "player": {"name": "Mira"},
                "world_state": {
                    "campaign_id": campaign_id,
                    "location": "tavern",
                    "npcs": [{"id": "keeper", "current_hp": 8}],
                },
            },
            "journal": {
                "notable_events": [{"event_type": "note", "event_id": "note-1"}],
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _create_version_five(path: Path) -> dict[str, str]:
    _require_temporary(path)
    first = str(uuid.uuid4())
    second = str(uuid.uuid4())
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE campaigns (
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
                payload_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE campaign_history (
                campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id)
                    ON DELETE CASCADE,
                sequence INTEGER NOT NULL,
                player_message TEXT NOT NULL,
                narration TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, sequence)
            );
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
            );
            CREATE TABLE campaign_turn_actions (
                campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id)
                    ON DELETE CASCADE,
                action_id TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, action_id)
            );
            PRAGMA user_version = 5;
            """
        )
        connection.execute(_EMERGENCE_ATTEMPTS_TABLE)
        payloads = {first: _payload(first), second: _payload(second)}
        for campaign_id, name in ((first, "First"), (second, "Second")):
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, name, created_at, updated_at, last_played_at,
                    campaign_version, save_version, engine_hash, character_name,
                    character_race, character_class, character_level, location,
                    payload_json, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id, name, "2026-01-01T00:00:00+00:00",
                    "2026-01-02T00:00:00+00:00", "2026-01-02T00:00:00+00:00",
                    1, 4, "engine-hash", "Mira", "Human", "Fighter", 1,
                    "tavern", payloads[campaign_id], 3,
                ),
            )
        connection.execute(
            """
            INSERT INTO campaign_history (
                campaign_id, sequence, player_message, narration, created_at
            ) VALUES (?, 1, ?, ?, ?)
            """,
            (first, "Kapıya bakıyorum.", "Kapı kapalı.", "2026-01-02T00:00:01+00:00"),
        )
        connection.execute(
            """
            INSERT INTO campaign_combat_history (
                campaign_id, sequence, event_id, turn_index, result_json, created_at
            ) VALUES (?, 1, ?, 0, ?, ?)
            """,
            (first, "event-1", '{"action":"attack"}', "2026-01-02T00:00:02+00:00"),
        )
        connection.execute(
            """
            INSERT INTO campaign_turn_actions (
                campaign_id, action_id, request_hash, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (first, str(uuid.uuid4()), "a" * 64, '{"status":"recorded"}',
             "2026-01-02T00:00:03+00:00"),
        )
        connection.execute(
            """
            INSERT INTO campaign_emergence_attempts (
                campaign_id, trigger_id, attempt_id, status, owner_token,
                canon_stamp, model_id, prompt_contract_version, envelope_version,
                envelope_hash, proposal_schema_version, gate_policy_version,
                incident_schema_version, model_call_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                first, "trigger-1", "attempt-1", "accepted", "attempt-lock-token",
                "canon-stamp", "qwen3:8b", 1, 1, "envelope-hash", 1, 1, 1, 0,
                "2026-01-02T00:00:04+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return payloads


def _rows(path: Path, sql: str) -> list[tuple]:
    connection = sqlite3.connect(path)
    try:
        return [tuple(row) for row in connection.execute(sql).fetchall()]
    finally:
        connection.close()


def _stable_snapshot(path: Path) -> dict[str, list[tuple]]:
    columns = ", ".join(_STABLE_CAMPAIGN_COLUMNS)
    snapshot = {
        "campaigns": _rows(
            path,
            f"SELECT {columns} FROM campaigns ORDER BY campaign_id",
        ),
    }
    for table in _RELATED_TABLES:
        snapshot[table] = _rows(path, f"SELECT * FROM {table} ORDER BY campaign_id")
    return snapshot


def _ownership(path: Path) -> list[tuple]:
    return _rows(
        path,
        """
        SELECT campaign_id, owner_issuer, owner_subject, ownership_state
        FROM campaigns
        ORDER BY campaign_id
        """,
    )


class CampaignOwnershipSchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = _require_temporary(Path(self.directory.name) / "campaigns.sqlite3")

    def test_version_five_rows_stay_unowned_and_byte_stable_across_reopen(self):
        payloads = _create_version_five(self.path)
        before = _stable_snapshot(self.path)
        self.assertEqual(len(before["campaigns"]), 2)
        self.assertEqual(len(before["campaign_history"]), 1)
        self.assertEqual(len(before["campaign_combat_history"]), 1)
        self.assertEqual(len(before["campaign_turn_actions"]), 1)
        self.assertEqual(len(before["campaign_emergence_attempts"]), 1)

        store = CampaignStore(
            self.path,
            bound_principal=TEST_PLAYER,
            allow_schema_migration=True,
        )
        self.assertEqual(store.path, self.path)
        self._assert_migrated(payloads, before)
        from api.tests.auth_fixture import PLAYER_A
        self.assertEqual(store.list_campaigns(principal=PLAYER_A), [])

        reopened = CampaignStore(self.path, bound_principal=TEST_PLAYER)
        self.assertEqual(reopened.path, self.path)
        self._assert_migrated(payloads, before)

        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA user_version = 5")
            connection.commit()
        finally:
            connection.close()
        CampaignStore(
            self.path,
            bound_principal=TEST_PLAYER,
            allow_schema_migration=True,
        )
        self._assert_migrated(payloads, before)
        names = _rows(self.path, "PRAGMA table_info(campaigns)")
        self.assertEqual(sum(row[1] == "ownership_state" for row in names), 1)

    def _assert_migrated(self, payloads: dict[str, str], before: dict[str, list[tuple]]) -> None:
        self.assertEqual(_rows(self.path, "PRAGMA user_version"), [(6,)])
        self.assertEqual(_stable_snapshot(self.path), before)
        self.assertEqual(
            [row[0] for row in _ownership(self.path)],
            sorted(payloads),
        )
        for campaign_id, issuer, subject, state in _ownership(self.path):
            self.assertIn(campaign_id, payloads)
            self.assertIsNone(issuer)
            self.assertIsNone(subject)
            self.assertEqual(state, "unowned")
            connection = sqlite3.connect(self.path)
            try:
                stored_payload = connection.execute(
                    "SELECT payload_json FROM campaigns WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(stored_payload, payloads[campaign_id])
            parsed = json.loads(stored_payload)
            world = parsed["engine_save"]["world_state"]
            self.assertTrue(
                {"owner_issuer", "owner_subject", "ownership_state"}.isdisjoint(parsed)
            )
            self.assertTrue(
                {"owner_issuer", "owner_subject", "ownership_state"}.isdisjoint(world)
            )
