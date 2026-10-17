"""Bounded character-identity drafts.

These jobs are not turns. They do not write a campaign, do not change the
game model, and do not use the turn model-call counter.
"""

from __future__ import annotations

import os
import threading
from queue import Queue
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

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
BUDGET_PER_DRAFT = 4
SuggestionProvider = Callable[[str], str]


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
    def __init__(self, request: IdentitySuggestionRequest, status: str, code: str | None = None):
        self.request_id = request.request_id
        self.draft_id = request.draft_id
        self.field = request.field
        self.input_revision = request.input_revision
        self.status = status
        self.suggestion: str | None = None
        self.code = code
        self.prompt = ""

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
        budget: int = BUDGET_PER_DRAFT,
        timeout_seconds: float = 40,
    ):
        self._provider = provider or local_ollama_provider
        self._budget_limit = budget
        self._timeout = timeout_seconds
        self._jobs: dict[str, _Job] = {}
        self._spent: dict[str, int] = {}
        self._seen: dict[tuple[str, str], int] = {}
        self._prompts: dict[str, str] = {}
        self._provider_calls = 0
        self._lock = threading.Lock()
        self._queue: Queue[str] = Queue()
        self._worker: threading.Thread | None = None

    @property
    def provider_calls(self) -> int:
        with self._lock:
            return self._provider_calls

    def prompt_for(self, request_id: str) -> str:
        with self._lock:
            return self._prompts.get(request_id, "")

    def submit(self, request: IdentitySuggestionRequest) -> IdentitySuggestionJob:
        with self._lock:
            existing = self._jobs.get(request.request_id)
            if existing is not None:
                return existing.public()
            job = self._decide(request)
            self._jobs[request.request_id] = job
            if job.status == "queued":
                self._prompts[request.request_id] = job.prompt
                self._queue.put(request.request_id)
                self._ensure_worker()
            return job.public()

    def get(self, request_id: str) -> IdentitySuggestionJob | None:
        if not isinstance(request_id, str) or not request_id or len(request_id) > 80:
            return None
        with self._lock:
            job = self._jobs.get(request_id)
            return None if job is None else job.public()

    def _decide(self, request: IdentitySuggestionRequest) -> _Job:
        if request.field not in LIMITS:
            return _Job(request, "rejected", "invalid_field")
        if len(request.current_text) > LIMITS[request.field]:
            return _Job(request, "rejected", "invalid_text")
        if request.locked:
            self._seen[(request.draft_id, request.field)] = max(
                self._seen.get((request.draft_id, request.field), 0),
                request.input_revision,
            )
            return _Job(request, "rejected", "field_locked")
        seen = self._seen.get((request.draft_id, request.field))
        if seen is not None and request.input_revision < seen:
            return _Job(request, "rejected", "stale_revision")
        spent = self._spent.get(request.draft_id, 0)
        if spent >= self._budget_limit:
            return _Job(request, "rejected", "budget_exhausted")
        self._spent[request.draft_id] = spent + 1
        self._seen[(request.draft_id, request.field)] = request.input_revision
        job = _Job(request, "queued")
        job.prompt = _prompt(request)
        return job

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run, name="identity-suggestion", daemon=True)
        self._worker.start()

    def _run(self) -> None:
        while True:
            request_id = self._queue.get()
            with self._lock:
                job = self._jobs.get(request_id)
                if job is None or job.status != "queued":
                    continue
                job.status = "running"
                prompt = job.prompt
            holder: dict[str, object] = {}

            def invoke() -> None:
                try:
                    holder["text"] = self._provider(prompt)
                except Exception:
                    holder["error"] = True

            worker = threading.Thread(target=invoke, daemon=True)
            worker.start()
            worker.join(self._timeout)
            with self._lock:
                job = self._jobs[request_id]
                self._provider_calls += 1
                if job.status != "running":
                    continue
                if worker.is_alive() or holder.get("error"):
                    job.status = "timed_out" if worker.is_alive() else "failed"
                    job.code = "timeout" if worker.is_alive() else "provider_failed"
                    job.suggestion = None
                    continue
                text = _clean(holder.get("text"), job.field)
                if not text:
                    job.status = "failed"
                    job.code = "empty_suggestion"
                    job.suggestion = None
                    continue
                job.status = "ready"
                job.suggestion = text
                job.code = None
