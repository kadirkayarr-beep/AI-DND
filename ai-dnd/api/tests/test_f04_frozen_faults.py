"""Offline execution of corpus.json offline_fault_rows D01-D06.

Only disposable SQLite stores, ASGITransport and injected providers are used.
Each evidence filename is exclusively created under a new test-run directory.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import os
from pathlib import Path
import random
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing, contextmanager
from functools import wraps
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import game
from api.auth import FixedAuthenticator
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER
from api.tests import live_playable_living_world_v1_smoke as diagnostics


def plain(value):
    def convert(item):
        if isinstance(item, set):
            return sorted(item)
        raise TypeError(type(item).__name__)
    return json.loads(json.dumps(value, ensure_ascii=False, default=convert))


def evidence(root, name, value):
    with (Path(root) / name).open("x", encoding="utf-8") as handle:
        json.dump(plain(value), handle, ensure_ascii=False, indent=2)


class NetworkForbidden(BaseException):
    """Cannot be swallowed by an engine's ordinary provider error fallback."""


@contextmanager
def no_network():
    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append("network_connection_attempt")
        raise NetworkForbidden("Real network/model transport forbidden in frozen F04 tests")
    with ExitStack() as stack:
        for owner, name in (
            (socket, "create_connection"), (socket, "getaddrinfo"),
            (socket.socket, "connect"), (socket.socket, "connect_ex"),
            (httpx.HTTPTransport, "handle_request"),
            (httpx.AsyncHTTPTransport, "handle_async_request"),
        ):
            stack.enter_context(patch.object(owner, name, forbidden))
        yield attempts
    if attempts:
        raise AssertionError(f"Forbidden network attempts: {len(attempts)}")


class ObservedAdapter(AuthenticatedOllamaAdapter):
    def __init__(self, client):
        super().__init__(client)
        self.failure_scopes = []
        self.call_scopes = []

    @contextmanager
    def capture_model_failures(self):
        with super().capture_model_failures() as failures:
            try:
                yield failures
            finally:
                self.failure_scopes.append([
                    {"error_type": str(f), "phase": getattr(f, "phase", None)}
                    for f in failures
                ])

    @contextmanager
    def capture_model_calls(self):
        with super().capture_model_calls() as calls:
            try:
                yield calls
            finally:
                self.call_scopes.append(list(calls))


class ScriptedProvider:
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = []
        self.list_calls = 0
        self.before_call = None

    def list(self):
        self.list_calls += 1
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls.append(plain({"args": args, "kwargs": kwargs}))
        index = len(self.calls) - 1
        if index >= len(self.scripts):
            raise NetworkForbidden("Unexpected extra synthetic provider attempt")
        if self.before_call:
            self.before_call(index, kwargs)
        value = self.scripts[index]
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            value = value(index, kwargs)
        return SimpleNamespace(message=SimpleNamespace(
            content=json.dumps(value, ensure_ascii=False)))


def narration(text, updates=None):
    return {"narration": text, "world_updates": updates or {}, "lore_claims": []}


class Fixture:
    def __init__(self, database, provider):
        self.store = CampaignStore(database, bound_principal=TEST_PLAYER)
        self.manager = SessionManager(
            session_factory=lambda: game.create_session(seed=42),
            campaign_store=self.store,
        )
        self.provider = provider
        self.adapter = ObservedAdapter(provider)
        self.engine_results = []

    def build_app(self):
        return create_app(session_manager=self.manager, ollama_adapter=self.adapter,
                          authenticator=FixedAuthenticator(TEST_PLAYER))

    async def create(self, client):
        response = await client.post("/api/game/campaigns", json={"name": "Synthetic frozen F04"})
        if response.status_code != 200:
            raise AssertionError((response.status_code, response.text))
        self.cid, self.sid = response.json()["campaign_id"], response.json()["session_id"]
        self.record = self.manager.get(self.sid)
        self.session = self.record.game_session
        self.session.lore_authority_context = game._empty_lore_authority_context()
        self.session.recent_dm_narrations = []
        self.capture()

    def capture(self):
        original = self.session.run_player_turn
        @wraps(original)
        def captured(*args, **kwargs):
            result = original(*args, **kwargs)
            self.engine_results.append(copy.deepcopy(result))
            return result
        self.session.run_player_turn = captured

    def tavern(self, npc=False, locked_door=False):
        world = self.session.world_state
        world["location"] = "tavern"
        world["locations"] = {
            "tavern": {"id": "tavern", "name": "Eski Han", "type": "tavern"},
            "forest": {"id": "forest", "name": "Orman", "type": "wilderness"},
        }
        world["npcs"] = []
        if npc:
            world["npcs"] = [{"id": "npc_barkeep", "name": "Hancı", "role": "Barkeep",
                              "location": "tavern", "relationship": "neutral",
                              "knowledge": [], "memory": []}]
            world["flags"].update(active_npc_id="npc_barkeep", active_npc_until_turn=20)
        world["doors"] = [{"name": "Han Kapısı", "location": "tavern", "description": "Tahta kapı.",
                           "locked": bool(locked_door), "open": False, "broken": False}]
        self.session.ensure_campaign_clock()

    def save(self):
        self.manager.save_campaign(self.cid, principal=TEST_PLAYER)

    def snapshot(self):
        with closing(sqlite3.connect(f"file:{self.store.path.as_posix()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = {table: [dict(r) for r in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
                    for table in ("campaign_turn_actions", "campaign_emergence_attempts")}
        r, s = self.record, self.session
        return plain({
            "engine_save": s.serialize_game_state(), "rng": s.rng.getstate(),
            "messages": s.messages, "world_metadata": s.world_metadata,
            "journal": r.journal, "narrative_memory": r.narrative_memory,
            "lore": r.lore_authority.to_dict(), "combat_history": r.combat_history,
            "receipts": r.turn_action_receipts,
            "persisted": dataclasses.asdict(self.store.get_campaign(self.cid)),
            "sql_rows": rows,
        })

    async def turn(self, client, message, action_id=None, **kwargs):
        body = {"message": message, "action_id": action_id or str(uuid4()), **kwargs}
        return await client.post(f"/api/game/sessions/{self.sid}/turn", json=body)


class FrozenFaultTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="f04-frozen-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        output = os.environ.get("F04_FAULT_EVIDENCE")
        self.output = (Path(output) if output else self.folder / "evidence") / self._testMethodName
        self.output.mkdir(parents=True, exist_ok=True)

    async def test_D01_pre_resolution_failure_rollback_and_diagnostics(self):
        original_error = TimeoutError("D01 synthetic provider exception")
        raw = ScriptedProvider([original_error, original_error])
        # Reuse the existing smoke's exact provider diagnostic wrapper, while
        # leaving the real game/session run-turn functions unmodified.
        hook_owner = SimpleNamespace(
            ollama=SimpleNamespace(chat=raw.chat),
            validate_world_updates=game.validate_world_updates,
            _bind_world_update_mentions=game._bind_world_update_mentions,
            run_player_turn=game.run_player_turn,
            GameSession=type("DiagnosticHookHolder", (), {}),
        )
        diagnostics._install_telemetry(hook_owner)
        propagated = []
        diagnostic_path = self.output / "provider-diagnostics.jsonl"
        def original_rethrow(*args, **kwargs):
            try:
                return hook_owner.ollama.chat(*args, **kwargs)
            except Exception as error:
                propagated.append(error)
                diagnostics.write_failure_evidence(self.output, {
                    "event": "model_attempt", "phase": "failed",
                    "error_type": type(error).__name__,
                })
                raise
        observed_client = SimpleNamespace(list=raw.list, chat=original_rethrow)
        fixture = Fixture(self.folder / "campaign.sqlite3", observed_client)
        rows = []
        with no_network() as network, fixture.adapter.engine_binding(), \
             patch.object(diagnostics, "_SMOKE_DIAGNOSTIC_PATH", diagnostic_path):
            token = diagnostics._REQUEST_TELEMETRY.set(rows)
            self.addCleanup(diagnostics._REQUEST_TELEMETRY.reset, token)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.build_app()),
                                         base_url="http://testserver", trust_env=False) as client:
                await fixture.create(client)
                fixture.tavern()
                fixture.save()
                before = fixture.snapshot()
                evidence(self.output, "before.json", before)
                def verify_started(index, kwargs):
                    entries = [json.loads(line) for line in diagnostic_path.read_text(encoding="utf-8").splitlines()]
                    self.assertEqual(entries[-1]["phase"], "started")
                    self.assertEqual(entries[-1]["attempt_index"], index + 1)
                raw.before_call = verify_started
                response = await fixture.turn(client, "Mor bir düşünceyi yüksek sesle kuruyorum.", interaction_mode="do")
                after = fixture.snapshot()
                evidence(self.output, "after.json", after)
                evidence(self.output, "http.json", {"status": response.status_code, "body": response.json()})
                evidence(self.output, "provider.json", {"calls": raw.calls, "failures": fixture.adapter.failure_scopes})
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(after, before)
                self.assertGreaterEqual(len(raw.calls), 1)
                self.assertLessEqual(len(raw.calls), 2)
                self.assertEqual(len(propagated), len(raw.calls))
                self.assertTrue(all(error is original_error for error in propagated))
                diagnostic_rows = [json.loads(line) for line in diagnostic_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual([r["phase"] for r in diagnostic_rows], [p for _ in raw.calls for p in ("started", "failed")])
                self.assertTrue(all(r.get("error_type") == "TimeoutError" for r in diagnostic_rows if r["phase"] == "failed"))
                failures = fixture.adapter.failure_scopes[-1]
                self.assertTrue(failures)
                self.assertEqual(failures[0], {"error_type": "TimeoutError", "phase": "unresolved"})
                # A later reporting failure must not replace the initial cause.
                first_failure = (self.output / "failure-evidence.json").read_bytes()
                diagnostics.write_failure_evidence(self.output, {
                    "event": "isolated_log", "phase": "failed", "error_type": "OSError"})
                self.assertEqual((self.output / "failure-evidence.json").read_bytes(), first_failure)
                self.assertEqual(network, [])
                evidence(self.output, "assertions.json", {
                    "scenario": "D01", "http_503": True, "full_snapshot_equal": True,
                    "snapshot_fields": sorted(before), "started_before_provider": True,
                    "diagnostic_phases": [r["phase"] for r in diagnostic_rows],
                    "first_error_identity_preserved_before_adapter": True,
                    "first_failure_evidence_preserved": True,
                    "synthetic_provider_attempts": len(raw.calls), "network_attempts": 0,
                })


if __name__ == "__main__":
    unittest.main()
