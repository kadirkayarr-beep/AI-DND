"""Bounded character-identity drafts.

These jobs are not turns. They do not write a campaign, do not change the
game model, and do not use the turn model-call counter.

Limits, all configurable on the service:
- budget: new request ids per verified owner, shared by every draft id
- max_queue: jobs waiting to run; a full queue returns queue_full
- max_in_flight: provider calls running at once; a timed-out call is not
  treated as cancelled and its late result cannot land on another job
- max_stored: retained jobs and tombstones. The same cap bounds seen revisions
  and retired request ids. Queued or running jobs are kept.
- A locked rejection does not record a seen revision.
- Owner budget is charged only when a job is queued. Expiry and tombstone
  retirement do not refund it.
- retention_seconds: how long a finished request id returns the same job.
  After that the id stays expired for the same duration and is not regenerated.
  Removing the tombstone keeps that id expired until the retired-id cap drops
  it. Traffic does not move the tombstone deadline. A status read never starts
  a provider call.
- A queued job older than retention expires without a provider call, even
  while another provider call is still in flight. That expiry drops the
  physical queue entry as well as the logical slot. max_in_flight stays in force.
"""

from __future__ import annotations

import os
import threading
import time
from queue import Empty, Queue
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from api.auth import Principal
from api.ollama_adapter import MODEL_NAME


FIELDS = ("origin", "appearance", "personality", "backstory")
LABELS = {
    "origin": "Köken",
    "appearance": "Görünüş",
    "personality": "Kişilik",
    "backstory": "Geçmiş",
}
LIMITS = {
    "origin": 240,
    "appearance": 500,
    "personality": 500,
    "backstory": 1000,
}
BUDGET_PER_OWNER = 4
MAX_QUEUE = 8
MAX_IN_FLIGHT = 1
MAX_STORED = 32
RETENTION_SECONDS = 900
SuggestionProvider = Callable[[str], str]
OwnerKey = tuple[str, str]


class IdentityContextField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    text: str = Field(default="", max_length=1000)
    locked: bool = False
    allow_as_context: bool = False


class IdentitySuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: str = Field(min_length=1, max_length=80)
    field: str
    request_id: str = Field(min_length=1, max_length=80)
    input_revision: int = Field(ge=0, le=100000)
    current_text: str = Field(default="", max_length=1000)
    locked: bool = False
    name: str | None = Field(default=None, max_length=80)
    species: str | None = Field(default=None, max_length=40)
    character_class: str | None = Field(default=None, max_length=40)
    context_fields: list[IdentityContextField] = Field(default_factory=list, max_length=4)


class IdentitySuggestionJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    draft_id: str
    field: str
    input_revision: int
    status: str
    suggestion: str | None = None
    code: str | None = None


class _Job:
    def __init__(self, request: IdentitySuggestionRequest, owner: OwnerKey, status: str, code: str | None = None):
        self.owner = owner
        self.request_id = request.request_id
        self.draft_id = request.draft_id
        self.field = request.field
        self.input_revision = request.input_revision
        self.status = status
        self.suggestion: str | None = None
        self.code = code
        self.prompt = ""
        self.admitted_at = 0.0
        self.expires_at: float | None = None
        self.tombstone_until: float | None = None
        self.holds_queue_slot = False

    def public(self) -> IdentitySuggestionJob:
        return IdentitySuggestionJob(
            request_id=self.request_id,
            draft_id=self.draft_id,
            field=self.field,
            input_revision=self.input_revision,
            status=self.status,
            suggestion=self.suggestion,
            code=self.code,
        )


def _clean(text: object, field: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    limit = LIMITS[field]
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip()
    return cleaned


def _prompt(request: IdentitySuggestionRequest) -> str:
    lines = [
        f"Alan: {LABELS[request.field]}.",
        "Yalnız bu alan için kısa bir Türkçe taslak yaz.",
        "Başka bir alanın metnini değiştirme. HP, puan, zar veya eşya ekleme.",
    ]
    if request.name:
        lines.append(f"Ad: {request.name}")
    if request.species:
        lines.append(f"Tür: {request.species}")
    if request.character_class:
        lines.append(f"Sınıf: {request.character_class}")
    if request.current_text:
        lines.append(f"Oyuncunun mevcut metni: {request.current_text}")
    for item in request.context_fields:
        if item.field == request.field or item.field not in LABELS:
            continue
        if not item.allow_as_context:
            continue
        if len(item.text) > LIMITS[item.field]:
            continue
        lines.append(f"Bağlam ({LABELS[item.field]}, değiştirilmez): {item.text}")
    return "\n".join(lines)


def _owner_key(owner: Principal) -> OwnerKey:
    if type(owner) is not Principal:
        raise TypeError("Suggestion owner must be the verified server principal.")
    return (owner.issuer, owner.subject)


def local_ollama_provider(prompt: str) -> str:
    """One local chat. Credentials stay in the process environment."""
    import ollama

    host = os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    token = os.environ.get("OLLAMA_PROXY_TOKEN")
    client_options: dict[str, object] = {"host": host, "timeout": 45}
    if token:
        client_options["headers"] = {"Authorization": f"Bearer {token}"}
    client = ollama.Client(**client_options)
    response = client.chat(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "Tek kısa Türkçe karakter notu yaz. Mekanik ekleme.",
            },
            {"role": "user", "content": prompt},
        ],
        options={"num_predict": 60, "temperature": 0.3},
        think=False,
    )
    message = response.get("message") if isinstance(response, dict) else getattr(response, "message", None)
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    if not isinstance(content, str):
        raise RuntimeError("Empty suggestion.")
    return content


class IdentitySuggestionService:
    def __init__(
        self,
        provider: SuggestionProvider | None = None,
        *,
        budget: int = BUDGET_PER_OWNER,
        timeout_seconds: float = 40,
        max_queue: int = MAX_QUEUE,
        max_in_flight: int = MAX_IN_FLIGHT,
        max_stored: int = MAX_STORED,
        retention_seconds: float = RETENTION_SECONDS,
        clock: Callable[[], float] | None = None,
    ):
        self._provider = provider or local_ollama_provider
        self._budget_limit = budget
        self._timeout = timeout_seconds
        self._max_queue = max_queue
        self._max_in_flight = max_in_flight
        self._max_stored = max_stored
        self._retention = retention_seconds
        self._clock = clock or time.monotonic
        self._jobs: dict[tuple[OwnerKey, str], _Job] = {}
        self._spent: dict[OwnerKey, int] = {}
        self._seen: dict[tuple[OwnerKey, str, str], int] = {}
        self._retired: dict[tuple[OwnerKey, str], tuple[str, str, int]] = {}
        self._provider_calls = 0
        self._in_flight = 0
        self._waiting = 0
        self._lock = threading.Lock()
        self._queue: Queue[tuple[OwnerKey, str]] = Queue()
        self._worker: threading.Thread | None = None

    @property
    def provider_calls(self) -> int:
        with self._lock:
            return self._provider_calls

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def prompt_for(self, request_id: str, owner: Principal) -> str:
        key = (_owner_key(owner), request_id)
        with self._lock:
            job = self._jobs.get(key)
            return "" if job is None else job.prompt

    def submit(self, request: IdentitySuggestionRequest, owner: Principal) -> IdentitySuggestionJob:
        owner_key = _owner_key(owner)
        with self._lock:
            self._expire_queued_locked()
            self._expire_locked(owner_key, request.request_id)
            key = (owner_key, request.request_id)
            existing = self._jobs.get(key)
            if existing is not None:
                return existing.public()
            retired = self._retired.get(key)
            if retired is not None:
                return self._retired_public(request.request_id, retired)
            job = self._decide(request, owner_key)
            if job.status == "queued":
                job.holds_queue_slot = True
                self._queue.put((owner_key, request.request_id))
                self._waiting += 1
                self._ensure_worker()
            return job.public()

    def get(self, request_id: str, owner: Principal) -> IdentitySuggestionJob | None:
        if not isinstance(request_id, str) or not request_id or len(request_id) > 80:
            return None
        owner_key = _owner_key(owner)
        with self._lock:
            self._expire_queued_locked()
            self._expire_locked(owner_key, request_id)
            key = (owner_key, request_id)
            job = self._jobs.get(key)
            if job is not None:
                return job.public()
            retired = self._retired.get(key)
            return None if retired is None else self._retired_public(request_id, retired)

    def _decide(self, request: IdentitySuggestionRequest, owner_key: OwnerKey) -> _Job:
        key = (owner_key, request.request_id)
        if request.field not in LIMITS or len(request.current_text) > LIMITS[request.field]:
            return self._keep(key, request, owner_key, "rejected", "invalid_field" if request.field not in LIMITS else "invalid_text")
        if request.locked:
            return self._keep(key, request, owner_key, "rejected", "field_locked")
        seen_key = (owner_key, request.draft_id, request.field)
        seen = self._seen.get(seen_key)
        if seen is not None and request.input_revision < seen:
            return self._keep(key, request, owner_key, "rejected", "stale_revision")
        self._evict_locked()
        if len(self._jobs) >= self._max_stored:
            return self._unsaved(request, "rejected", "storage_full")
        if self._waiting >= self._max_queue:
            return self._keep(key, request, owner_key, "rejected", "queue_full")
        spent = self._spent.get(owner_key, 0)
        if spent >= self._budget_limit:
            return self._keep(key, request, owner_key, "rejected", "budget_exhausted")
        self._spent[owner_key] = spent + 1
        self._remember_seen(seen_key, request.input_revision)
        job = _Job(request, owner_key, "queued")
        job.prompt = _prompt(request)
        job.admitted_at = self._clock()
        self._jobs[key] = job
        return job

    def _keep(self, key, request, owner_key, status, code) -> _Job:
        self._evict_locked()
        job = _Job(request, owner_key, status, code)
        if len(self._jobs) >= self._max_stored and key not in self._jobs:
            return job
        self._stamp(job)
        self._jobs[key] = job
        return job

    def _unsaved(self, request, status, code) -> _Job:
        return _Job(request, ("", ""), status, code)

    def _stamp(self, job: _Job) -> None:
        now = self._clock()
        job.expires_at = now + self._retention
        job.tombstone_until = None

    def _remember_seen(self, seen_key: tuple[OwnerKey, str, str], revision: int) -> None:
        if seen_key in self._seen:
            self._seen.pop(seen_key)
        self._seen[seen_key] = revision
        while len(self._seen) > self._max_stored:
            self._seen.pop(next(iter(self._seen)))

    def _retired_public(self, request_id: str, retired: tuple[str, str, int]) -> IdentitySuggestionJob:
        draft_id, field, revision = retired
        return IdentitySuggestionJob(
            request_id=request_id,
            draft_id=draft_id,
            field=field,
            input_revision=revision,
            status="rejected",
            suggestion=None,
            code="expired",
        )

    def _remember_retired(self, key: tuple[OwnerKey, str], job: _Job) -> None:
        self._retired.pop(key, None)
        self._retired[key] = (job.draft_id, job.field, job.input_revision)
        while len(self._retired) > self._max_stored:
            self._retired.pop(next(iter(self._retired)))

    def _retire(self, key: tuple[OwnerKey, str], job: _Job) -> None:
        self._jobs.pop(key, None)
        self._remember_retired(key, job)

    def _become_tombstone(self, job: _Job, now: float) -> None:
        if job.tombstone_until is not None:
            return
        job.status = "rejected"
        job.code = "expired"
        job.suggestion = None
        job.prompt = ""
        job.tombstone_until = now + self._retention

    def _release_queue_slot(self, job: _Job) -> None:
        if not job.holds_queue_slot:
            return
        job.holds_queue_slot = False
        self._waiting = max(0, self._waiting - 1)

    def _expire_queued_locked(self) -> None:
        now = self._clock()
        expired = False
        for job in list(self._jobs.values()):
            if job.status != "queued" or now - job.admitted_at <= self._retention:
                continue
            self._release_queue_slot(job)
            self._become_tombstone(job, now)
            expired = True
        if expired:
            self._drop_unqueued_entries()

    def _drop_unqueued_entries(self) -> None:
        kept: list[tuple[OwnerKey, str]] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            owner_key, request_id = item
            job = self._jobs.get((owner_key, request_id))
            if job is not None and job.status == "queued":
                kept.append(item)
        for item in kept:
            self._queue.put(item)

    def _expire_locked(self, owner_key: OwnerKey, request_id: str) -> None:
        key = (owner_key, request_id)
        job = self._jobs.get(key)
        if job is None or job.status in {"queued", "running"}:
            return
        now = self._clock()
        if job.tombstone_until is not None:
            if now >= job.tombstone_until:
                self._retire(key, job)
            return
        if job.expires_at is not None and now >= job.expires_at:
            self._become_tombstone(job, now)

    def _evict_locked(self) -> None:
        now = self._clock()
        for key, job in list(self._jobs.items()):
            if job.status in {"queued", "running"}:
                continue
            if job.tombstone_until is not None:
                if now >= job.tombstone_until:
                    self._retire(key, job)
                continue
            if job.expires_at is not None and now >= job.expires_at:
                self._become_tombstone(job, now)

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run, name="identity-suggestion", daemon=True)
        self._worker.start()

    def _run(self) -> None:
        while True:
            owner_key, request_id = self._queue.get()
            with self._lock:
                job = self._jobs.get((owner_key, request_id))
                if job is not None:
                    self._release_queue_slot(job)
            self._execute(owner_key, request_id)

    def _execute(self, owner_key: OwnerKey, request_id: str) -> None:
        with self._lock:
            job = self._jobs.get((owner_key, request_id))
            if job is None or job.status != "queued":
                return
            if self._clock() - job.admitted_at > self._retention:
                self._become_tombstone(job, self._clock())
                return
            job.status = "running"
            prompt = job.prompt
            field = job.field
        outcome: dict[str, object] = {}

        def invoke(box: dict[str, object] = outcome, text: str = prompt) -> None:
            try:
                box["text"] = self._provider(text)
            except Exception:
                box["error"] = True

        worker = threading.Thread(target=invoke, daemon=True)
        with self._lock:
            self._in_flight += 1
        worker.start()
        worker.join(self._timeout)
        with self._lock:
            self._provider_calls += 1
            current = self._jobs.get((owner_key, request_id))
            if current is not None and current.status == "running":
                if worker.is_alive():
                    current.status = "timed_out"
                    current.code = "wait_expired"
                    current.suggestion = None
                elif outcome.get("error"):
                    current.status = "failed"
                    current.code = "provider_failed"
                    current.suggestion = None
                else:
                    cleaned = _clean(outcome.get("text"), field)
                    if not cleaned:
                        current.status = "failed"
                        current.code = "empty_suggestion"
                        current.suggestion = None
                    else:
                        current.status = "ready"
                        current.suggestion = cleaned
                        current.code = None
                self._stamp(current)
            at_cap = self._in_flight >= self._max_in_flight
        if worker.is_alive() and at_cap:
            worker.join()
        if worker.is_alive():
            def reap(thread: threading.Thread = worker) -> None:
                thread.join()
                with self._lock:
                    self._in_flight -= 1

            threading.Thread(target=reap, daemon=True).start()
        else:
            with self._lock:
                self._in_flight -= 1
