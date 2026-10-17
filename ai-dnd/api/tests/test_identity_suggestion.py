"""Bounded identity suggestions stay off the turn model counter."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path

os.environ["AI_DND_DISABLE_DEFAULT_APP"] = "1"

import httpx

import game
from api.auth import FixedAuthenticator
from api.identity_suggestion import IdentitySuggestionRequest, IdentitySuggestionService
from api.main import create_app
from api.ollama_adapter import AuthenticatedOllamaAdapter, _MODEL_CALLS
from api.persistence.campaign_store import CampaignStore
from api.session_manager import SessionManager
from api.tests.auth_fixture import TEST_PLAYER


PROTECTED_DATABASES = {
    Path(r"C:\Users\Kadir\Desktop\AI - DND\ai-dnd\saves\campaigns.sqlite3").resolve(),
    Path(
        r"C:\Users\Kadir\Desktop\AI - DND\ai-dnd\docs\evidence"
        r"\door-live-231b6cd-20261016\isolated-campaigns.sqlite3"
    ).resolve(),
}


class RecordingProvider:
    def __init__(self, text="Sakin ve ölçülü bir taslak.", *, delay=None):
        self.text = text
        self.delay = delay
        self.prompts = []
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Identity suggestion must not use the turn model.")

    def __call__(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        self.started.set()
        if self.delay is not None:
            self.delay.wait(30)
        return self.text


def request(**overrides):
    body = {
        "draft_id": "draft-1",
        "field": "personality",
        "request_id": "request-1",
        "input_revision": 2,
        "current_text": "Sakin.",
        "locked": False,
    }
    body.update(overrides)
    return IdentitySuggestionRequest.model_validate(body)


class IdentitySuggestionTests(unittest.TestCase):
    def test_same_request_id_is_one_job_and_ignores_the_turn_counter(self):
        provider = RecordingProvider()
        service = IdentitySuggestionService(provider, timeout_seconds=2)
        token = _MODEL_CALLS.set([])
        try:
            first = service.submit(request())
            second = service.submit(request(current_text="Elle değişti.", input_revision=3))
            self.assertEqual(first.request_id, second.request_id)
            deadline = threading.Event()
            for _ in range(50):
                job = service.get("request-1")
                if job and job.status == "ready":
                    break
                deadline.wait(0.02)
            job = service.get("request-1")
            self.assertEqual(job.status, "ready")
            self.assertEqual(job.suggestion, "Sakin ve ölçülü bir taslak.")
            self.assertEqual(job.input_revision, 2)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(_MODEL_CALLS.get(), [])
        finally:
            _MODEL_CALLS.reset(token)

    def test_locked_field_is_not_a_target_but_can_be_context(self):
        provider = RecordingProvider("Yeni kişilik taslağı.")
        service = IdentitySuggestionService(provider, timeout_seconds=2)
        locked = service.submit(request(field="appearance", locked=True, request_id="locked"))
        self.assertEqual(locked.status, "rejected")
        self.assertEqual(locked.code, "field_locked")
        self.assertEqual(provider.calls, 0)
        service.submit(request(
            request_id="context",
            context_fields=[{
                "field": "appearance",
                "text": "Sol yanakta ince bir iz.",
                "locked": True,
                "allow_as_context": True,
            }],
        ))
        for _ in range(50):
            if service.get("context").status == "ready":
                break
            threading.Event().wait(0.02)
        prompt = service.prompt_for("context")
        self.assertIn("Sol yanakta ince bir iz.", prompt)
        self.assertIn("değiştirilmez", prompt)
        self.assertNotIn("current_hp", prompt)
        self.assertEqual(provider.calls, 1)

    def test_stale_revision_and_budget_do_not_call_the_provider(self):
        provider = RecordingProvider()
        service = IdentitySuggestionService(provider, budget=1, timeout_seconds=2)
        service.submit(request(request_id="new", input_revision=4))
        stale = service.submit(request(request_id="old", input_revision=3))
        extra = service.submit(request(request_id="extra", input_revision=5))
        self.assertEqual(stale.code, "stale_revision")
        self.assertEqual(extra.code, "budget_exhausted")
        for _ in range(50):
            if provider.calls == 1:
                break
            threading.Event().wait(0.02)
        self.assertEqual(provider.calls, 1)

    def test_timeout_queries_the_same_job_and_does_not_retry(self):
        hold = threading.Event()
        provider = RecordingProvider(delay=hold)
        service = IdentitySuggestionService(provider, timeout_seconds=0.05)
        service.submit(request())
        self.assertTrue(provider.started.wait(2))
        for _ in range(50):
            job = service.get("request-1")
            if job and job.status == "timed_out":
                break
            threading.Event().wait(0.02)
        self.assertEqual(service.get("request-1").status, "timed_out")
        hold.set()
        threading.Event().wait(0.05)
        self.assertEqual(service.get("request-1").status, "timed_out")
        self.assertEqual(provider.calls, 1)

    def test_http_job_uses_a_temp_database_and_not_the_turn_adapter(self):
        provider = RecordingProvider("HTTP taslağı.")
        suggestions = IdentitySuggestionService(provider, timeout_seconds=2)
        engine = RecordingProvider()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "campaigns.sqlite3"
            self.assertNotIn(database.resolve(), PROTECTED_DATABASES)
            store = CampaignStore(database, bound_principal=TEST_PLAYER)
            manager = SessionManager(
                session_factory=lambda: game.create_session(seed=17017),
                campaign_store=store,
            )
            adapter = AuthenticatedOllamaAdapter(engine)
            with adapter.engine_binding():
                app = create_app(
                    session_manager=manager,
                    ollama_adapter=adapter,
                    authenticator=FixedAuthenticator(TEST_PLAYER),
                    identity_suggestions=suggestions,
                )
                transport = httpx.ASGITransport(app=app)

                async def exchange():
                    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                        created = await client.post("/api/game/character-identity-suggestions", json={
                            "draft_id": "draft-http",
                            "field": "origin",
                            "request_id": "http-1",
                            "input_revision": 1,
                            "current_text": "Kuzey köyü",
                        })
                        self.assertEqual(created.status_code, 200, created.text)
                        repeated = await client.post("/api/character-identity-suggestions", json={
                            "draft_id": "draft-http",
                            "field": "origin",
                            "request_id": "http-1",
                            "input_revision": 9,
                            "current_text": "başka",
                        })
                        self.assertEqual(repeated.json()["input_revision"], 1)
                        job = None
                        for _ in range(50):
                            status = await client.get("/api/game/character-identity-suggestions/http-1")
                            self.assertEqual(status.status_code, 200, status.text)
                            job = status.json()
                            if job["status"] == "ready":
                                break
                        self.assertEqual(job["suggestion"], "HTTP taslağı.")

                asyncio.run(exchange())
                self.assertEqual(engine.calls, 0)
                self.assertEqual(provider.calls, 1)
