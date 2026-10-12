"""Import and startup must not open or migrate a campaign database implicitly."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import game
import httpx
from fastapi.testclient import TestClient

from api.auth import FailClosedAuthenticator, FixedAuthenticator, loopback_allowed, select_authenticator
from api.main import create_app
from api.persistence.campaign_models import CampaignStorageError
from api.persistence.campaign_store import (
    CampaignStore,
    _DATABASE_SCHEMA_VERSION,
    _EMERGENCE_ATTEMPTS_TABLE,
    _read_user_version,
)
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER


_LIVE = (Path(game.__file__).resolve().parent / "saves" / "campaigns.sqlite3").resolve()
_ROOT = Path(__file__).resolve().parents[2]
_ENV_KEYS = (
    "AI_DND_CAMPAIGN_DB",
    "AI_DND_ALLOW_SCHEMA_MIGRATION",
    "AI_DND_AUTH_MODE",
    "AI_DND_LISTEN_HOST",
    "AI_DND_LOOPBACK_ISSUER",
    "AI_DND_LOOPBACK_SUBJECT",
    "AI_DND_DISABLE_DEFAULT_APP",
)


def _temporary(directory: str) -> Path:
    path = (Path(directory) / "campaigns.sqlite3").resolve()
    if path == _LIVE:
        raise RuntimeError("Refusing to use the live campaign database.")
    return path


def _version_five(path: Path) -> None:
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
                campaign_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                player_message TEXT NOT NULL,
                narration TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, sequence)
            );
            CREATE TABLE campaign_combat_history (
                campaign_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, sequence)
            );
            CREATE TABLE campaign_turn_actions (
                campaign_id TEXT NOT NULL,
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
        connection.commit()
    finally:
        connection.close()


class StartupSafetyTests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_module_import_does_not_open_a_campaign_database(self):
        path = _temporary(self.directory.name)
        _version_five(path)
        before = path.read_bytes()
        env = os.environ.copy()
        for key in _ENV_KEYS:
            env.pop(key, None)
        env["AI_DND_CAMPAIGN_DB"] = str(path)
        completed = subprocess.run(
            [sys.executable, "-c", _IMPORT_PROBE],
            cwd=_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("import-closed", completed.stdout)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(Path(str(path) + "-wal").exists())
        self.assertEqual(_read_user_version(path), 5)

    def test_old_schema_is_unchanged_without_migration_approval(self):
        path = _temporary(self.directory.name)
        _version_five(path)
        before = path.read_bytes()
        with self.assertRaises(CampaignStorageError):
            CampaignStore(path)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(_read_user_version(path), 5)
        self.assertFalse(Path(str(path) + "-wal").exists())

        os.environ["AI_DND_CAMPAIGN_DB"] = str(path)
        app = create_app(ollama_adapter=None, authenticator=FixedAuthenticator(TEST_PLAYER))
        with TestClient(app) as client:
            response = client.get("/api/campaigns")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "campaign_storage_unavailable")
        self.assertIsNone(app.state.session_manager._campaign_store._store)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(_read_user_version(path), 5)

    def test_explicit_migration_approval_upgrades_a_temporary_database(self):
        path = _temporary(self.directory.name)
        _version_five(path)
        store = CampaignStore(path, allow_schema_migration=True)
        self.assertEqual(_read_user_version(path), _DATABASE_SCHEMA_VERSION)
        self.assertEqual(store.list_campaigns(principal=TEST_PLAYER), [])
        os.environ["AI_DND_CAMPAIGN_DB"] = str(path)
        app = create_app(ollama_adapter=None, authenticator=FixedAuthenticator(TEST_PLAYER))
        with TestClient(app) as client:
            response = client.get("/api/campaigns")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_missing_database_configuration_fails_closed(self):
        app = create_app(ollama_adapter=None, authenticator=FixedAuthenticator(TEST_PLAYER))
        with TestClient(app) as client:
            response = client.get("/api/campaigns")
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(app.state.session_manager._campaign_store._store)

    def test_new_temporary_database_still_initializes(self):
        path = _temporary(self.directory.name)
        CampaignStore(path, bound_principal=TEST_PLAYER)
        self.assertEqual(_read_user_version(path), _DATABASE_SCHEMA_VERSION)

    def test_bound_principal_does_not_become_the_production_authenticator(self):
        path = _temporary(self.directory.name)
        store = CampaignStore(path, bound_principal=TEST_PLAYER)
        store.create_campaign(
            str(uuid.uuid4()),
            "Owned",
            game.create_session(),
            principal=TEST_PLAYER,
        )
        app = create_app(
            session_manager=SessionManager(campaign_store=store),
            ollama_adapter=None,
        )
        self.assertIsInstance(app.state.authenticator, FailClosedAuthenticator)
        with TestClient(app) as client:
            response = client.get("/api/campaigns", headers={
                "Authorization": "Bearer client-token",
                "X-Replit-User-Id": TEST_PLAYER.subject,
            })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "authentication_required")
        self.assertEqual(len(store.list_campaigns(principal=TEST_PLAYER)), 1)

    def test_loopback_host_string_does_not_open_access(self):
        local = {
            "AI_DND_AUTH_MODE": "loopback",
            "AI_DND_LISTEN_HOST": "127.0.0.1",
            "AI_DND_LOOPBACK_ISSUER": "loopback-issuer",
            "AI_DND_LOOPBACK_SUBJECT": "loopback-player",
        }
        self.assertFalse(loopback_allowed(local, "127.0.0.1"))
        self.assertFalse(loopback_allowed(local, "0.0.0.0"))
        self.assertIsInstance(select_authenticator(local, "127.0.0.1"), FailClosedAuthenticator)
        self.assertIsInstance(select_authenticator(local, "0.0.0.0"), FailClosedAuthenticator)
        os.environ.update(local)
        path = _temporary(self.directory.name)
        store = CampaignStore(path, bound_principal=TEST_PLAYER)
        app = create_app(
            session_manager=SessionManager(campaign_store=store),
            ollama_adapter=None,
        )
        self.assertIsInstance(app.state.authenticator, FailClosedAuthenticator)
        with TestClient(app) as client:
            response = client.get("/api/campaigns")
        self.assertEqual(response.status_code, 401)


_IMPORT_PROBE = r"""
import os
import sqlite3

opened = []
real_connect = sqlite3.connect

def tracing_connect(*args, **kwargs):
    opened.append(args[0] if args else kwargs.get("database"))
    return real_connect(*args, **kwargs)

sqlite3.connect = tracing_connect
import api.main as main
store = main.app.state.session_manager._campaign_store
assert store._store is None
assert opened == [], opened
print("import-closed")
"""


class StartupHttpIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_authenticator_still_isolates_players(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = _temporary(directory.name)
        store = CampaignStore(path)
        app = create_app(
            session_manager=SessionManager(campaign_store=store),
            ollama_adapter=None,
            authenticator=FixedAuthenticator(TEST_PLAYER),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://isolated-testserver",
        ) as client:
            created = await client.post("/api/campaigns", json={"name": "Owned"})
            self.assertEqual(created.status_code, 200, created.text)
            anonymous = create_app(
                session_manager=SessionManager(campaign_store=store),
                ollama_adapter=None,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=anonymous),
                base_url="http://isolated-testserver",
            ) as other:
                denied = await other.get("/api/campaigns")
            self.assertEqual(denied.status_code, 401)


if __name__ == "__main__":
    unittest.main()
