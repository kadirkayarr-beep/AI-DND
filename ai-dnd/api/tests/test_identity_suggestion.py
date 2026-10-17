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


class OwnedService(IdentitySuggestionService):
    def submit(self, request, owner=TEST_PLAYER):
        return super().submit(request, owner)

    def get(self, request_id, owner=TEST_PLAYER):
        return super().get(request_id, owner)

    def prompt_for(self, request_id, owner=TEST_PLAYER):
        return super().prompt_for(request_id, owner)


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
        service = OwnedService(provider, timeout_seconds=2)
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
        service = OwnedService(provider, timeout_seconds=2)
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
        service = OwnedService(provider, budget=1, timeout_seconds=2)
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
        service = OwnedService(provider, timeout_seconds=0.05)
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
        suggestions = OwnedService(provider, timeout_seconds=2)
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


class CrossUserProvider:
    def __init__(self):
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def __call__(self, prompt):
        with self._lock:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.started.set()
        try:
            if "MARKER-A" in prompt:
                return "SUGGESTION-A"
            if "MARKER-B" in prompt:
                return "SUGGESTION-B"
            return "SUGGESTION"
        finally:
            with self._lock:
                self.active -= 1


def _app(principal, suggestions, database):
    store = CampaignStore(database, bound_principal=principal)
    manager = SessionManager(
        session_factory=lambda: game.create_session(seed=17017),
        campaign_store=store,
    )
    return create_app(
        session_manager=manager,
        ollama_adapter=None,
        authenticator=FixedAuthenticator(principal),
        identity_suggestions=suggestions,
    )


class IdentitySuggestionIsolationTests(unittest.TestCase):
    def test_another_user_cannot_read_or_spend_the_same_ids(self):
        from api.tests.auth_fixture import PLAYER_A, PLAYER_B

        provider = CrossUserProvider()
        suggestions = OwnedService(provider, budget=1, timeout_seconds=2)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            database = Path(directory) / "campaigns.sqlite3"
            self.assertNotIn(database.resolve(), PROTECTED_DATABASES)
            app_a = _app(PLAYER_A, suggestions, database)
            app_b = _app(PLAYER_B, suggestions, database)

            async def exchange():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app_a),
                    base_url="http://testserver",
                ) as client_a, httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app_b),
                    base_url="http://testserver",
                ) as client_b:
                    created = await client_a.post("/api/game/character-identity-suggestions", json={
                        "draft_id": "shared-draft",
                        "field": "personality",
                        "request_id": "shared-request",
                        "input_revision": 1,
                        "current_text": "MARKER-A",
                        "owner": PLAYER_B.subject,
                    })
                    self.assertEqual(created.status_code, 422, created.text)
                    created = await client_a.post("/api/game/character-identity-suggestions", json={
                        "draft_id": "shared-draft",
                        "field": "personality",
                        "request_id": "shared-request",
                        "input_revision": 1,
                        "current_text": "MARKER-A",
                    })
                    self.assertEqual(created.status_code, 200, created.text)
                    for path in (
                        "/api/game/character-identity-suggestions/shared-request",
                        "/api/character-identity-suggestions/shared-request",
                    ):
                        hidden = await client_b.get(path)
                        self.assertEqual(hidden.status_code, 404, hidden.text)
                        self.assertNotIn("SUGGESTION-A", hidden.text)
                    stolen = await client_b.post("/api/character-identity-suggestions", json={
                        "draft_id": "shared-draft",
                        "field": "personality",
                        "request_id": "shared-request",
                        "input_revision": 1,
                        "current_text": "MARKER-B",
                    })
                    self.assertEqual(stolen.status_code, 200, stolen.text)
                    self.assertNotEqual(stolen.json()["suggestion"], "SUGGESTION-A")
                    exhausted = await client_a.post("/api/character-identity-suggestions", json={
                        "draft_id": "other-draft",
                        "field": "origin",
                        "request_id": "a-second",
                        "input_revision": 1,
                        "current_text": "MARKER-A",
                    })
                    self.assertEqual(exhausted.json()["code"], "budget_exhausted")
                    self.assertNotEqual(stolen.json()["code"], "budget_exhausted")
                    visible = await client_a.get("/api/character-identity-suggestions/shared-request")
                    self.assertEqual(visible.status_code, 200, visible.text)
                    self.assertEqual(visible.json()["suggestion"], "SUGGESTION-A")

            asyncio.run(exchange())
            self.assertLessEqual(provider.calls, 2)
            import sqlite3
            with sqlite3.connect(database) as connection:
                campaigns = connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
            self.assertEqual(campaigns, 0)

    def test_late_provider_error_does_not_change_the_next_job(self):
        entered = {"A": threading.Event(), "B": threading.Event()}
        release_a = threading.Event()
        raised = threading.Event()
        calls = {"n": 0}

        def call(prompt):
            calls["n"] += 1
            if "MARKER-A" in prompt:
                entered["A"].set()
                release_a.wait(3)
                raised.set()
                raise RuntimeError("late")
            entered["B"].set()
            raised.wait(3)
            return "B-OK"

        service = OwnedService(call, timeout_seconds=0.05, max_in_flight=2)
        service.submit(request(request_id="job-a", current_text="MARKER-A"))
        self.assertTrue(entered["A"].wait(2))
        for _ in range(40):
            if service.get("job-a").status == "timed_out":
                break
            threading.Event().wait(0.02)
        service.submit(request(request_id="job-b", current_text="MARKER-B", input_revision=3))
        self.assertTrue(entered["B"].wait(2))
        release_a.set()
        for _ in range(40):
            status = service.get("job-b").status
            if status not in {"queued", "running"}:
                break
            threading.Event().wait(0.02)
        self.assertEqual(service.get("job-b").status, "ready")
        self.assertEqual(service.get("job-b").suggestion, "B-OK")
        self.assertEqual(service.get("job-a").status, "timed_out")
        self.assertNotEqual(service.get("job-a").suggestion, "B-OK")
        self.assertEqual(calls["n"], 2)

    def test_late_results_keep_their_own_jobs_in_reverse_finish_order(self):
        entered = {"A": threading.Event(), "B": threading.Event()}
        release = {"A": threading.Event(), "B": threading.Event()}

        def call(prompt):
            if "MARKER-A" in prompt:
                entered["A"].set()
                release["B"].wait(3)
                return "A-LATE"
            entered["B"].set()
            release["A"].wait(3)
            return "B-FAST"

        service = OwnedService(call, timeout_seconds=0.05, max_in_flight=2)
        service.submit(request(request_id="job-a", current_text="MARKER-A"))
        self.assertTrue(entered["A"].wait(2))
        service.submit(request(request_id="job-b", current_text="MARKER-B", input_revision=4))
        self.assertTrue(entered["B"].wait(2))
        release["A"].set()
        for _ in range(40):
            if service.get("job-b").status == "ready":
                break
            threading.Event().wait(0.02)
        self.assertEqual(service.get("job-b").suggestion, "B-FAST")
        release["B"].set()
        threading.Event().wait(0.1)
        self.assertEqual(service.get("job-b").suggestion, "B-FAST")
        self.assertNotEqual(service.get("job-a").suggestion, "B-FAST")

    def test_new_drafts_cannot_pass_the_queue_or_owner_quota(self):
        hold = threading.Event()
        provider = RecordingProvider(delay=hold)
        service = OwnedService(
            provider,
            budget=2,
            timeout_seconds=0.05,
            max_queue=1,
            max_stored=4,
            retention_seconds=5,
        )
        first = service.submit(request(request_id="held", draft_id="draft-a", current_text="bir"))
        self.assertTrue(provider.started.wait(2))
        queued = service.submit(request(request_id="queued", draft_id="draft-b", input_revision=2))
        self.assertIn(queued.status, {"queued", "running"})
        blocked = service.submit(request(request_id="blocked", draft_id="draft-c", input_revision=3))
        self.assertEqual(blocked.code, "queue_full")
        self.assertNotEqual(blocked.status, "queued")
        self.assertEqual(provider.calls, 1)
        self.assertLessEqual(service.in_flight, 1)
        hold.set()

    def test_expired_id_is_not_regenerated_and_a_running_job_is_kept(self):
        now = {"t": 0.0}
        provider = RecordingProvider("kalan taslak")
        service = OwnedService(
            provider,
            retention_seconds=10,
            clock=lambda: now["t"],
            timeout_seconds=2,
        )
        service.submit(request(request_id="keep", current_text="bir"))
        for _ in range(40):
            if service.get("keep").status == "ready":
                break
            threading.Event().wait(0.02)
        self.assertEqual(service.get("keep").suggestion, "kalan taslak")
        self.assertEqual(provider.calls, 1)
        replay = service.submit(request(request_id="keep", current_text="baska"))
        self.assertEqual(replay.suggestion, "kalan taslak")
        self.assertEqual(provider.calls, 1)
        now["t"] = 11
        self.assertEqual(service.get("keep").code, "expired")
        again = service.submit(request(request_id="keep", current_text="yeniden"))
        self.assertEqual(again.code, "expired")
        self.assertEqual(provider.calls, 1)

        hold = threading.Event()
        blocker = RecordingProvider(delay=hold)
        limited = OwnedService(blocker, max_stored=1, timeout_seconds=2)
        limited.submit(request(request_id="active", current_text="surer"))
        self.assertTrue(blocker.started.wait(2))
        full = limited.submit(request(request_id="extra", draft_id="draft-2", input_revision=2))
        self.assertEqual(full.code, "storage_full")
        self.assertIn(limited.get("active").status, {"queued", "running"})
        self.assertEqual(blocker.calls, 1)
        hold.set()

    def test_locked_requests_do_not_record_seen_metadata(self):
        service = OwnedService(RecordingProvider(), budget=1, max_stored=4, timeout_seconds=2)
        for index in range(12):
            locked = service.submit(request(
                request_id=f"lock-{index}",
                draft_id=f"draft-{index}",
                locked=True,
                input_revision=index + 1,
            ))
            self.assertEqual(locked.code, "field_locked")
        self.assertEqual(len(service._seen), 0)
        self.assertLessEqual(len(service._jobs), 4)
        self.assertEqual(service.provider_calls, 0)

    def test_seen_metadata_stays_inside_the_storage_cap(self):
        now = {"t": 0.0}
        provider = RecordingProvider("kisa")
        service = OwnedService(
            provider,
            budget=6,
            max_stored=2,
            retention_seconds=10,
            clock=lambda: now["t"],
            timeout_seconds=2,
        )
        for index in range(2):
            service.submit(request(request_id=f"cap-{index}", draft_id=f"draft-{index}", input_revision=1))
        for index in range(2):
            self.assertEqual(_wait_job(service, f"cap-{index}").status, "ready")
        now["t"] = 11
        for index in range(2):
            self.assertEqual(service.get(f"cap-{index}").code, "expired")
        now["t"] = 21
        for index in range(2):
            service.get(f"cap-{index}")
        for index in range(2, 4):
            admitted = service.submit(request(
                request_id=f"cap-{index}",
                draft_id=f"draft-{index}",
                input_revision=1,
            ))
            self.assertIn(admitted.status, {"queued", "running", "ready"})
            self.assertEqual(_wait_job(service, f"cap-{index}").status, "ready")
        self.assertLessEqual(len(service._seen), 2)
        self.assertEqual(provider.calls, 4)

    def test_traffic_does_not_extend_tombstone_deadline(self):
        now = {"t": 0.0}
        provider = RecordingProvider("taslak")
        service = OwnedService(
            provider,
            budget=4,
            retention_seconds=10,
            clock=lambda: now["t"],
            timeout_seconds=2,
        )
        service.submit(request(request_id="old", current_text="bir"))
        self.assertEqual(_wait_job(service, "old").suggestion, "taslak")
        now["t"] = 11
        self.assertEqual(service.get("old").code, "expired")
        key = (("test-issuer", "test-player"), "old")
        self.assertEqual(service._jobs[key].tombstone_until, 21)
        now["t"] = 15
        service.submit(request(request_id="other", draft_id="draft-2", input_revision=3, current_text="iki"))
        self.assertEqual(service._jobs[key].tombstone_until, 21)
        now["t"] = 21
        retired = service.get("old")
        self.assertEqual(retired.code, "expired")
        self.assertIsNone(retired.suggestion)
        self.assertNotIn(key, service._jobs)
        self.assertLessEqual(provider.calls, 2)

    def test_queued_job_expires_while_a_provider_stays_stuck(self):
        now = {"t": 0.0}
        hold = threading.Event()
        provider = RecordingProvider(delay=hold)
        service = OwnedService(
            provider,
            budget=4,
            timeout_seconds=30,
            max_in_flight=1,
            max_queue=1,
            retention_seconds=10,
            clock=lambda: now["t"],
        )
        try:
            service.submit(request(request_id="stuck", current_text="A"))
            self.assertTrue(provider.started.wait(2))
            queued = service.submit(request(
                request_id="waiting",
                draft_id="draft-2",
                input_revision=2,
                current_text="B",
            ))
            self.assertEqual(queued.status, "queued")
            now["t"] = 11
            expired = service.get("waiting")
            self.assertEqual(expired.code, "expired")
            self.assertNotEqual(expired.status, "queued")
            self.assertEqual(provider.calls, 1)
            self.assertEqual(service.in_flight, 1)
            follow = service.submit(request(
                request_id="after",
                draft_id="draft-3",
                input_revision=3,
                current_text="C",
            ))
            self.assertNotEqual(follow.code, "queue_full")
            self.assertEqual(provider.calls, 1)
            self.assertEqual(service.in_flight, 1)
        finally:
            hold.set()

    def test_stuck_provider_ttl_cycles_keep_the_physical_queue_bounded(self):
        now = {"t": 0.0}
        hold = threading.Event()
        provider = RecordingProvider(delay=hold)
        service = OwnedService(
            provider,
            budget=20,
            timeout_seconds=30,
            max_in_flight=1,
            max_queue=1,
            max_stored=20,
            retention_seconds=10,
            clock=lambda: now["t"],
        )
        try:
            service.submit(request(request_id="stuck", current_text="A"))
            self.assertTrue(provider.started.wait(2))
            for index in range(8):
                now["t"] = float(index * 11)
                queued = service.submit(request(
                    request_id=f"wait-{index}",
                    draft_id=f"draft-{index}",
                    input_revision=index + 1,
                    current_text=f"Q{index}",
                ))
                self.assertEqual(queued.status, "queued")
                now["t"] = float(index * 11 + 11)
                expired = service.get(f"wait-{index}")
                self.assertEqual(expired.code, "expired")
                self.assertNotEqual(expired.status, "queued")
            self.assertLessEqual(service._queue.qsize(), 1)
            self.assertEqual(service.in_flight, 1)
            self.assertEqual(provider.calls, 1)
        finally:
            hold.set()

    def test_budget_outlives_retention_and_retired_id_does_not_regenerate(self):
        from api.tests.auth_fixture import PLAYER_B

        now = {"t": 0.0}
        provider = RecordingProvider("bir")
        service = OwnedService(
            provider,
            budget=1,
            retention_seconds=10,
            clock=lambda: now["t"],
            timeout_seconds=2,
        )
        service.submit(request(request_id="spent", current_text="A"))
        self.assertEqual(_wait_job(service, "spent").suggestion, "bir")
        self.assertEqual(provider.calls, 1)
        now["t"] = 11
        self.assertEqual(service.get("spent").code, "expired")
        now["t"] = 21
        retired = service.get("spent")
        self.assertEqual(retired.code, "expired")
        self.assertEqual(provider.calls, 1)
        replay = service.submit(request(request_id="spent", current_text="yeniden"))
        self.assertEqual(replay.code, "expired")
        self.assertNotEqual(replay.status, "queued")
        self.assertEqual(provider.calls, 1)
        fresh = service.submit(request(request_id="new-id", draft_id="draft-2", input_revision=2))
        self.assertEqual(fresh.code, "budget_exhausted")
        self.assertEqual(provider.calls, 1)
        other_user = service.submit(
            request(request_id="spent", draft_id="draft-b", current_text="MARKER-B"),
            PLAYER_B,
        )
        self.assertNotEqual(other_user.code, "budget_exhausted")
        self.assertNotEqual(other_user.code, "expired")
        self.assertIn(other_user.status, {"queued", "running", "ready"})


def _wait_job(service, request_id):
    for _ in range(50):
        job = service.get(request_id)
        if job and job.status not in {"queued", "running"}:
            return job
        threading.Event().wait(0.02)
    return service.get(request_id)
