"""Authenticated server-side Ollama client binding for the frozen engine."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

import game


MODEL_NAME = "qwen3:8b"
_MODEL_FAILURES: ContextVar[list[str] | None] = ContextVar(
    "ai_dnd_api_model_failures", default=None
)
_MODEL_CALLS: ContextVar[list[str] | None] = ContextVar(
    "ai_dnd_api_model_calls", default=None
)
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
            calls.append(MODEL_NAME)
        _logger.info("Ollama chat request started (model=%s)", MODEL_NAME)
        try:
            return self._client.chat(*args, **kwargs)
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