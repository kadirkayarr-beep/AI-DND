"""OpenRouter image call for the character portrait (portrait P1, Task 2).

The key comes from the environment only and goes to https://openrouter.ai only: no redirects, no proxy or netrc from
the environment. Error bodies are never echoed (codes only), a url found in a response is never fetched, and only
PNG/JPEG/WEBP bytes within MAX_IMAGE_BYTES are accepted. Logs carry model id, status number, outcome and seconds."""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/images"
PRIMARY_MODEL = "black-forest-labs/flux-3-image-klein"
BACKUP_MODEL = "black-forest-labs/flux.2-klein-4b"
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_ATTEMPTS = 3
CALL_TIMEOUT_SECONDS = 60
CONNECT_TIMEOUT_SECONDS = 5
TOTAL_DEADLINE_SECONDS = 90
MAX_RETRY_WAIT_SECONDS = 10
DEFAULT_RETRY_WAIT_SECONDS = 2
KEY_ENV = "OPENROUTER_API_KEY"

_MAX_B64_CHARS = (MAX_IMAGE_BYTES * 4) // 3 + 16
_MAX_BODY_BYTES = _MAX_B64_CHARS + 64 * 1024  # base64 payload plus JSON envelope
_MODELS = (PRIMARY_MODEL, PRIMARY_MODEL, BACKUP_MODEL)
_REFUSAL_WORDS = ("safety", "content_filter", "moderation", "content policy", "prohibited")
_DATA_URL = re.compile(r"data:image/(png|jpeg|webp);base64,(.*)", re.DOTALL)
_logger = logging.getLogger("ai_dnd.api.portrait")


class ImageRejected(Exception):
    """A response image failed validation; the reason is a short fixed word, never response content."""


@dataclass(frozen=True)
class Attempt:
    model: str
    status: int | None
    outcome: Literal["image", "refused", "failed"]
    seconds: float
    usd: float | None


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    kind: str
    model: str
    attempts: tuple[Attempt, ...]


class PortraitClientError(Exception):
    def __init__(self, code: str, attempts: tuple[Attempt, ...] = ()):
        super().__init__(code)
        self.code = code
        self.attempts = attempts


def image_kind(data: bytes) -> Literal["png", "jpeg", "webp"] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def decode_image(value: str) -> tuple[bytes, str]:
    if not isinstance(value, str):
        raise ImageRejected("not_text")
    declared = None
    payload = value
    if value.startswith("data:"):
        match = _DATA_URL.fullmatch(value)
        if not match:
            raise ImageRejected("data_url")
        declared, payload = match.group(1), match.group(2)
    if not payload or len(payload) > _MAX_B64_CHARS:
        raise ImageRejected("size")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ImageRejected("base64") from None
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageRejected("size")
    kind = image_kind(data)
    if kind is None or (declared is not None and declared != kind):
        raise ImageRejected("type")
    return data, kind


def _retry_wait(response: httpx.Response) -> float:
    try:
        wait = float(response.headers.get("Retry-After", DEFAULT_RETRY_WAIT_SECONDS))
    except ValueError:
        return DEFAULT_RETRY_WAIT_SECONDS
    if wait != wait or wait < 0:
        return DEFAULT_RETRY_WAIT_SECONDS
    return min(wait, MAX_RETRY_WAIT_SECONDS)


def _read_capped(response: httpx.Response) -> bytes | None:
    """The body, or None when it is larger than any acceptable answer (read stops there)."""
    chunks, total = [], 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > _MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _parse(body: bytes) -> tuple[dict | None, float | None]:
    try:
        parsed = json.loads(body)
    except ValueError:
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    usage = parsed.get("usage")
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0 or cost != cost:
        cost = None
    return parsed, (float(cost) if cost is not None else None)


def _image_value(parsed: dict) -> str | None:
    items = parsed.get("data")
    first = items[0] if isinstance(items, list) and items else None
    if not isinstance(first, dict):
        return None
    for field in ("b64_json", "url"):
        if isinstance(first.get(field), str):
            return first[field]
    return None


@dataclass
class _Outcome:
    status: int | None
    kind: Literal["image", "refused", "failed"]
    retry: bool = False
    wait: float = 0.0
    usd: float | None = None
    image: tuple[bytes, str] | None = None


class PortraitClient:
    def __init__(self, key: str, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic):
        self.__key = key
        # No redirects and no proxy or netrc from the environment: the key goes to its own host only.
        self._http = httpx.Client(transport=transport, trust_env=False, follow_redirects=False)
        self._sleep = sleep
        self._monotonic = monotonic

    def __repr__(self) -> str:
        return "PortraitClient()"

    def generate(self, prompt: str) -> ImageResult:
        started = self._monotonic()
        attempts: list[Attempt] = []
        for index, model in enumerate(_MODELS[:MAX_ATTEMPTS]):
            remaining = TOTAL_DEADLINE_SECONDS - (self._monotonic() - started)
            if remaining <= 0:
                break
            call_start = self._monotonic()
            outcome = self._call(model, prompt, min(CALL_TIMEOUT_SECONDS, remaining))
            seconds = self._monotonic() - call_start
            attempts.append(Attempt(model, outcome.status, outcome.kind, seconds, outcome.usd))
            _logger.info("Portrait attempt (model=%s, status=%s, outcome=%s, seconds=%.2f)",
                         model, outcome.status, outcome.kind, seconds)
            if outcome.kind == "image" and outcome.image:
                return ImageResult(outcome.image[0], outcome.image[1], model, tuple(attempts))
            if outcome.kind == "refused":
                raise PortraitClientError("portrait_service_refused", tuple(attempts))
            if not outcome.retry or index + 1 >= MAX_ATTEMPTS:
                break
            if TOTAL_DEADLINE_SECONDS - (self._monotonic() - started) <= outcome.wait:
                break
            self._sleep(outcome.wait)
        raise PortraitClientError("portrait_service_failed", tuple(attempts))

    def _call(self, model: str, prompt: str, limit: float) -> _Outcome:
        headers = {"Authorization": "Bearer " + self.__key, "HTTP-Referer": "http://localhost", "X-Title": "ai-dnd"}
        body = {"model": model, "prompt": prompt, "aspect_ratio": "1:1", "n": 1}
        timeout = httpx.Timeout(limit, connect=min(CONNECT_TIMEOUT_SECONDS, limit))
        try:
            with self._http.stream("POST", OPENROUTER_URL, json=body, headers=headers, timeout=timeout) as response:
                status = response.status_code
                wait = _retry_wait(response)
                raw = _read_capped(response)
        except httpx.TransportError:
            return _Outcome(None, "failed", retry=True, wait=DEFAULT_RETRY_WAIT_SECONDS)
        if status == 429 or status >= 500:
            return _Outcome(status, "failed", retry=True, wait=wait)
        if raw is None:
            return _Outcome(status, "failed")
        refused = any(word in raw.decode("utf-8", "replace").lower() for word in _REFUSAL_WORDS)
        if status in (400, 403, 422):
            return _Outcome(status, "refused" if refused else "failed")
        if status != 200:
            return _Outcome(status, "failed")
        parsed, usd = _parse(raw)
        value = _image_value(parsed) if parsed else None
        if value is None:
            return _Outcome(status, "refused" if refused else "failed", usd=usd)
        try:
            return _Outcome(status, "image", usd=usd, image=decode_image(value))
        except ImageRejected:
            return _Outcome(status, "failed", usd=usd)


def client_from_environment() -> PortraitClient | None:
    key = os.environ.get(KEY_ENV, "").strip()
    return PortraitClient(key) if key else None
