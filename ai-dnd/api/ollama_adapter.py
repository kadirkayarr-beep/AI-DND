"""Authenticated server-side Ollama client binding for the frozen engine."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

import game
from api.world_metadata import validate_world_metadata


MODEL_NAME = "qwen3:8b"
MAX_MODEL_CALLS_PER_TURN = 2
# Successful tavern narration has completed in about 25s. A hung call was
# still inside the client at the smoke's 240s HTTP limit. 90s fails closed
# first and leaves the turn lock.
PROVIDER_TIMEOUT_SECONDS = 90
_MODEL_FAILURES: ContextVar[list[str] | None] = ContextVar(
    "ai_dnd_api_model_failures", default=None
)
_MODEL_CALLS: ContextVar[list[str] | None] = ContextVar(
    "ai_dnd_api_model_calls", default=None
)
_WORLD_METADATA_PROVIDER: ContextVar[
    Callable[[], Mapping[str, str]] | None
] = ContextVar("ai_dnd_api_world_metadata_provider", default=None)
_logger = logging.getLogger("ai_dnd.api.ollama")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    _logger.addHandler(_handler)
_logger.propagate = False


class OllamaUnavailableError(RuntimeError):
    def __init__(self, error_type: str = "Unavailable"):
        self.error_type = error_type
        super().__init__("Ollama service unavailable.")


class RequiredModelUnavailableError(RuntimeError):
    def __init__(self):
        super().__init__("Required model unavailable.")


@contextmanager
def canonical_world_metadata_context(
    provider: Callable[[], Mapping[str, str]],
) -> Iterator[None]:
    """Bind Python-owned metadata to model calls for this turn only."""
    token = _WORLD_METADATA_PROVIDER.set(provider)
    try:
        yield
    finally:
        _WORLD_METADATA_PROVIDER.reset(token)


def _attach_world_metadata(kwargs: dict[str, Any]) -> dict[str, Any]:
    provider = _WORLD_METADATA_PROVIDER.get()
    messages = kwargs.get("messages")
    if provider is None or not isinstance(messages, list):
        return kwargs

    metadata = validate_world_metadata(provider())
    context = (
        "SERVER-VALIDATED CANONICAL WORLD METADATA (read-only):\n"
        f"environment={metadata['environment']}; "
        f"time_of_day={metadata['time_of_day']}; "
        f"weather={metadata['weather']}.\n"
        "Describe the current atmosphere consistently with these values. "
        "Narration or proposed lore must not change them; Python remains authoritative."
    )
    prepared = [
        dict(message) if isinstance(message, Mapping) else message
        for message in messages
    ]
    system_message = next(
        (
            message
            for message in prepared
            if isinstance(message, dict) and message.get("role") == "system"
        ),
        None,
    )
    if system_message is None:
        prepared.insert(0, {"role": "system", "content": context})
    else:
        existing = system_message.get("content")
        system_message["content"] = (
            f"{existing}\n\n{context}" if isinstance(existing, str) else context
        )
    result = dict(kwargs)
    result["messages"] = prepared
    return result


class AuthenticatedOllamaAdapter:
    """Binds one authenticated Ollama client without changing game.py."""

    def __init__(self, client: Any):
        self._client = client

    @classmethod
    def from_environment(cls) -> AuthenticatedOllamaAdapter | None:
        host = os.environ.get("OLLAMA_HOST")
        token = os.environ.get("OLLAMA_PROXY_TOKEN")
        if not host or not token:
            return None
        try:
            import ollama

            client = ollama.Client(
                host=host,
                headers={"Authorization": f"Bearer {token}"},
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
        except Exception as error:
            _logger.error(
                "Authenticated Ollama client initialization failed (error_type=%s)",
                type(error).__name__,
            )
            return None
        return cls(client)

    def install_for_engine(self) -> None:
        # The engine calls the ollama module directly. Bind its calls once at API
        # startup; never pass credentials or client objects through HTTP.
        game.ollama.list = self._client.list
        game.ollama.chat = self.chat

    @contextmanager
    def engine_binding(self) -> Iterator[None]:
        """Temporarily install an adapter, restoring callbacks even on failure.

        Offline fixtures use this scope with unittest.enterContext so setup
        failures and nested adapter replacements cannot leak to another test.
        Production startup still uses the permanent install_for_engine binding.
        """
        target = game.ollama
        previous_list, previous_chat = target.list, target.chat
        try:
            self.install_for_engine()
            yield
        finally:
            target.list, target.chat = previous_list, previous_chat

    @staticmethod
    def _model_names(response: Any) -> list[str]:
        if isinstance(response, dict):
            models = response.get("models", [])
        else:
            models = getattr(response, "models", [])
        names: list[str] = []
        for model in models or []:
            if isinstance(model, dict):
                name = model.get("model") or model.get("name")
            else:
                name = getattr(model, "model", None) or getattr(model, "name", None)
            if isinstance(name, str):
                names.append(name)
        return names

    def ensure_required_model(self) -> None:
        try:
            response = self._client.list()
        except Exception as error:
            raise OllamaUnavailableError(type(error).__name__) from None
        if not any(
            name == MODEL_NAME or name.startswith(f"{MODEL_NAME}-")
            for name in self._model_names(response)
        ):
            raise RequiredModelUnavailableError()

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        requested_model = kwargs.get("model")
        if requested_model != MODEL_NAME:
            failures = _MODEL_FAILURES.get()
            if failures is not None:
                failures.append("UnexpectedModel")
            raise RuntimeError("Unexpected model configured.")

        calls = _MODEL_CALLS.get()
        if calls is not None:
            if len(calls) >= MAX_MODEL_CALLS_PER_TURN:
                raise RuntimeError("Model call budget exhausted.")
            calls.append(MODEL_NAME)
        _logger.info("Ollama chat request started (model=%s)", MODEL_NAME)
        try:
            return self._client.chat(*args, **_attach_world_metadata(kwargs))
        except Exception as error:
            failures = _MODEL_FAILURES.get()
            if failures is not None:
                failures.append(type(error).__name__)
            # game.py safely catches model errors; keep its server log sanitized.
            raise RuntimeError("Ollama request failed.") from None

    @contextmanager
    def capture_model_calls(self) -> Iterator[list[str]]:
        calls: list[str] = []
        token = _MODEL_CALLS.set(calls)
        try:
            yield calls
        finally:
            _MODEL_CALLS.reset(token)

    @contextmanager
    def capture_model_failures(self) -> Iterator[list[str]]:
        failures: list[str] = []
        token = _MODEL_FAILURES.set(failures)
        try:
            yield failures
        finally:
            _MODEL_FAILURES.reset(token)