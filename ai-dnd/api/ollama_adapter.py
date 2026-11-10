"""Authenticated server-side Ollama client binding for the frozen engine."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

import ollama

import game
from api import model_chain
from api.usage_ledger import UsageLedger
from api.model_phase import ModelFailure, in_classifier_call, in_front_call
from api.local_model_config import (
    DEFAULT_LOCAL_MODEL,
    LOCAL_FALLBACK_MODELS,
    LocalModelName,
    selected_local_model,
    validate_local_model,
)
from api.world_metadata import validate_world_metadata


# Engine logical tag: the fixed string game.py sends. The adapter checks it and
# substitutes the actual selected local model (DEFAULT_LOCAL_MODEL by default).
MODEL_NAME = "qwen3:8b"
MAX_MODEL_CALLS_PER_TURN = 2
# Ollama defaults to a 4096-token window and silently truncates (done_reason=length);
# live 9b prompts reach ~4100 tokens before the reply.
CONTEXT_WINDOW_TOKENS = 16384
# The 12B needs about 7.2 GB of the 8 GB card at 8K and the driver's system-memory fallback is off, so a bigger
# window fails to load; any other value would also make Ollama load the model again. Callers cannot change it.
_FIXED_CONTEXT_WINDOWS = {"gemma4-12b-dm": 8192}
# The local prompt is cut to leave the reply at least this much of the window (the call's num_predict when larger).
LOCAL_REPLY_RESERVE_TOKENS = 600
# After the 12B could not be loaded, its fallback answers for this long before the 12B is tried again,
# so a full card does not swap models on every call.
LOCAL_FALLBACK_REST_SECONDS = 600
# Owner's rules for the local model's prose (Nov 2026). Local path only: the cloud models' prompt stays as it is.
LOCAL_STYLE_RULES = (
    "YEREL ANLATIM KURALLARI: Kısa ve yalın cümleler kur. NPC ve yer adları Türkçe olsun. "
    "Parantez içinde İngilizce terim yazma; kural adlarını Türkçe yaz. "
    'Oyuncuya baştan sona "sen" diye hitap et.'
)
# The narration prompt's history block: its "- " lines, oldest first, are what the local budget cuts.
_HISTORY_HEADER = "RECENT NARRATION ("
_HISTORY_HINT = "\nSon anlatım “"
_NEXT_SECTION = re.compile(r"\n\n(?=[A-ZÇĞİÖŞÜ]{4,}[A-ZÇĞİÖŞÜ ]*[ (:])")
_HISTORY_ITEM = re.compile(r"\n(?=- )")
# The model stays loaded while a game session is open (Ollama unloads after 5 minutes by default, and the
# next call then waits for a cold load that can outlast a short client timeout).
LOCAL_KEEP_ALIVE = "30m"
# Ollama runs one request at a time here (OLLAMA_NUM_PARALLEL=1, one loaded model): local calls queue.
_LOCAL_CALL_LOCK = threading.Lock()
# Rough Turkish estimate for the prompt-size warning: one token per three characters. Not a tokenizer count.
_CHARS_PER_TOKEN = 3
_DEFAULT_REPLY_TOKENS = 700
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
_TURN_USAGE: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "ai_dnd_api_turn_usage", default=None
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


def local_context_window(model: str) -> int:
    """The num_ctx every local call to this model carries."""
    return _FIXED_CONTEXT_WINDOWS.get(model, CONTEXT_WINDOW_TOKENS)


def _characters(messages: list[Any]) -> int:
    return sum(len(str(message.get("content", ""))) for message in messages if isinstance(message, Mapping))


def _with_local_rules(messages: list[Any]) -> list[Any]:
    """A copy whose first system text ends with the local style rules; no system text, no rules."""
    result = list(messages)
    for index, message in enumerate(result):
        if isinstance(message, Mapping) and message.get("role") == "system" and isinstance(message.get("content"), str):
            result[index] = {**message, "content": f"{message['content']}\n\n{LOCAL_STYLE_RULES}"}
            break
    return result


def _fit_history(messages: list[Any], window: int, reply_tokens: int) -> list[Any]:
    """Drop the oldest history lines until prompt plus reply fit the window (about 3 characters a token).

    Only the narration's RECENT NARRATION lines go, never its newest one: the rules, world state, Python result and
    the player's message stay whole. A prompt still too big afterwards is left to the size warning.
    """
    over = _characters(messages) - (window - reply_tokens) * _CHARS_PER_TOKEN
    if over <= 0:
        return messages
    for index, message in enumerate(messages):
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str) or _HISTORY_HEADER not in content:
            continue
        start = content.find("\n", content.index(_HISTORY_HEADER)) + 1
        if start == 0:
            break
        section = _NEXT_SECTION.search(content, start)
        end = section.start() if section else len(content)
        block = content[start:end]
        hint_at = block.find(_HISTORY_HINT)
        items_text, hint = (block[:hint_at], block[hint_at:]) if hint_at >= 0 else (block, "")
        items = _HISTORY_ITEM.split(items_text)
        dropped = 0
        while over > 0 and len(items) > 1 and items[0].startswith("- "):
            over -= len(items.pop(0)) + 1
            dropped += 1
        if not dropped:
            break
        _logger.info("Local prompt history cut to fit the window (dropped_lines=%d, window=%d)", dropped, window)
        fitted = list(messages)
        fitted[index] = {**message, "content": content[:start] + "\n".join(items) + hint + content[end:]}
        return fitted
    return messages


def _warn_if_prompt_too_big(call: Mapping[str, Any]) -> None:
    """Ollama silently cuts a prompt that does not fit its window from the front, and the game then forgets."""
    options = call.get("options") or {}
    window = options.get("num_ctx") or CONTEXT_WINDOW_TOKENS
    reply = options.get("num_predict") or _DEFAULT_REPLY_TOKENS
    characters = sum(len(str(message.get("content", ""))) for message in call.get("messages") or [] if isinstance(message, Mapping))
    estimate = characters // _CHARS_PER_TOKEN
    if estimate + reply > window:
        _logger.warning(
            "Prompt may not fit the context window (estimated_prompt_tokens=%d, reply_tokens=%d, window=%d)",
            estimate, reply, window,
        )


def _warn_if_window_filled(response: Any, call: Mapping[str, Any]) -> None:
    window = (call.get("options") or {}).get("num_ctx") or CONTEXT_WINDOW_TOKENS
    used = _spent(response, "prompt_eval_count") + _spent(response, "eval_count")
    if used >= window:
        _logger.warning("Reply filled the context window (used_tokens=%d, window=%d); older text may have been cut", used, window)


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


def begin_turn_usage() -> None:
    """A new turn's count. The list is shared, so the planner's reading and the turn proper add to one count."""
    _TURN_USAGE.set([])


def _spent(response: Any, name: str) -> int:
    value = response.get(name) if isinstance(response, dict) else getattr(response, name, None)
    return value if isinstance(value, int) else 0


def note_usage(provider: str, response: Any = None, *, failed: bool = False) -> None:
    usage = _TURN_USAGE.get()
    if usage is not None:
        usage.append({"provider": provider, "failed": failed,
                      "input_tokens": _spent(response, "prompt_eval_count"),
                      "output_tokens": _spent(response, "eval_count")})


def usage_summary() -> dict[str, Any]:
    """This turn's calls and tokens, whole and by provider. Counts and provider names only."""
    rows = _TURN_USAGE.get() or []
    answered = [row for row in rows if not row["failed"]]
    providers = [{"provider": name, "calls": len(mine),
                  "input_tokens": sum(row["input_tokens"] for row in mine),
                  "output_tokens": sum(row["output_tokens"] for row in mine)}
                 for name in dict.fromkeys(row["provider"] for row in answered)
                 for mine in ([row for row in answered if row["provider"] == name],)]
    return {"calls": len(answered), "failed": len(rows) - len(answered),
            "input_tokens": sum(row["input_tokens"] for row in answered),
            "output_tokens": sum(row["output_tokens"] for row in answered), "providers": providers}


def model_calls_left() -> int | None:
    """Calls this turn may still make, or None outside a counted turn."""
    calls = _MODEL_CALLS.get()
    return None if calls is None else max(0, MAX_MODEL_CALLS_PER_TURN - len(calls))


class AuthenticatedOllamaAdapter:
    """Binds one authenticated Ollama client without changing game.py."""

    def __init__(
        self,
        client: Any,
        *,
        model_name: str = DEFAULT_LOCAL_MODEL,
        chain: model_chain.ModelChain | None = None,
    ):
        self._model_name = validate_local_model(model_name)
        self._client = client
        self._chain = chain
        # Measures the local model's calls (the chain's observer writes the cloud ones); None writes nothing.
        self.usage_ledger: UsageLedger | None = None
        self._warned_day: str | None = None  # the ledger day whose spend warning is already in the log
        # Only from_environment turns this on: the app then warms the local model once at start.
        self.warm_up_on_start = False
        self._warm_up_thread: threading.Thread | None = None
        self._now: Callable[[], float] = time.monotonic
        self._resting_until = 0.0  # the selected model is skipped for its fallback until then

    @property
    def model_name(self) -> LocalModelName:
        return self._model_name

    @property
    def cloud_chain(self) -> model_chain.ModelChain | None:
        return self._chain

    @property
    def model_chain(self) -> list[str] | None:
        """Every model that may answer, in order. None means the local model alone."""
        if self._chain is None:
            return None
        return [*self._chain.model_names(), self.model_name]

    @classmethod
    def from_environment(cls, *, use_cloud: bool = False) -> AuthenticatedOllamaAdapter | None:
        """use_cloud is for api.local_play alone, after it has proven a loopback bind."""
        host = os.environ.get("OLLAMA_HOST")
        token = os.environ.get("OLLAMA_PROXY_TOKEN")
        if not host or not token:
            return None
        model_name = selected_local_model()
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
        chain = model_chain.from_environment() if use_cloud else None
        adapter = cls(client, model_name=model_name, chain=chain)
        adapter.warm_up_on_start = True
        if use_cloud:
            # Local play measures Gemma too, with or without a cloud chain in front of it.
            adapter.usage_ledger = UsageLedger(model_chain._usage_path())
        return adapter

    def spend_warning(self) -> str | None:
        """The ledger's warning line once today's known cost is high, else None. It never raises.

        The line also goes to the log, once a ledger day (health reads it on every call).
        """
        if self.usage_ledger is None:
            return None
        try:
            text = self.usage_ledger.warning()
            if text is not None:
                day = self.usage_ledger.day()
                if day != self._warned_day:
                    self._warned_day = day
                    _logger.warning("%s", text)
            return text
        except Exception as error:  # noqa: BLE001 - a measuring aid must not break the caller
            _logger.warning("Usage ledger warning could not be read (%s).", type(error).__name__)
            return None

    def _note_local_call(self, response: Any, seconds: float) -> None:
        """Write the local model's call to the ledger; a ledger fault never reaches the turn."""
        if self.usage_ledger is None:
            return
        try:
            self.usage_ledger.record(
                "gemma", input_tokens=_spent(response, "prompt_eval_count"),
                output_tokens=_spent(response, "eval_count"), seconds=seconds, outcome="answered",
            )
        except Exception as error:  # noqa: BLE001
            _logger.warning("Usage ledger could not record a local call (%s).", type(error).__name__)

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
        if self._chain is not None and self._chain.can_answer():
            return  # the local model is last in line now; its failure counts only if a call reaches it
        try:
            response = self._client.list()
        except Exception as error:
            raise OllamaUnavailableError(type(error).__name__) from None
        # Ollama lists an untagged model as `<name>:latest`. A model with a fallback may play on the fallback.
        usable = [self.model_name, *([LOCAL_FALLBACK_MODELS[self.model_name]] if self.model_name in LOCAL_FALLBACK_MODELS else [])]
        wanted = {form for name in usable for form in (name, f"{name}:latest")}
        if not any(name in wanted for name in self._model_names(response)):
            raise RequiredModelUnavailableError()

    def _local_call(self, call: Mapping[str, Any], caller_options: Mapping[str, Any] | None,
                    model: str, *, style: bool) -> dict[str, Any]:
        """The request one local model receives: its window, the owner's rules and the history cut to fit."""
        window = local_context_window(model)
        options = {"num_ctx": window, **(caller_options or {})}
        if model in _FIXED_CONTEXT_WINDOWS:
            options["num_ctx"] = window
        local = {**call, "model": model, "options": options}
        messages = call.get("messages")
        if isinstance(messages, list):
            if style:
                messages = _with_local_rules(messages)
            reply = max(options.get("num_predict") or _DEFAULT_REPLY_TOKENS, LOCAL_REPLY_RESERVE_TOKENS)
            local["messages"] = _fit_history(messages, window, reply)
        return local

    def _send_local(self, args: tuple[Any, ...], call: Mapping[str, Any], caller_options: Mapping[str, Any] | None,
                    model: str, style: bool) -> Any:
        local = self._local_call(call, caller_options, model, style=style)
        _warn_if_prompt_too_big(local)
        response = self._client.chat(*args, **local)
        _warn_if_window_filled(response, local)
        return response

    def _ask_local_model(self, args: tuple[Any, ...], call: Mapping[str, Any],
                         caller_options: Mapping[str, Any] | None, *, style: bool) -> Any:
        """The selected model, or its fallback when Ollama answers that it cannot run it. Call under the local lock.

        Only an error Ollama itself returns (model missing, out of memory, load failure) switches models; a dead
        service or a timeout would fail the fallback the same way and only double the wait.
        """
        fallback = LOCAL_FALLBACK_MODELS.get(self.model_name)
        model = fallback if fallback is not None and self._now() < self._resting_until else self.model_name
        try:
            return self._send_local(args, call, caller_options, model, style)
        except ollama.ResponseError as error:
            if fallback is None or model == fallback:
                raise
            self._resting_until = self._now() + LOCAL_FALLBACK_REST_SECONDS
            _logger.warning(
                "Local model %s could not run (status_code=%s); falling back to %s for %d s",
                self.model_name, error.status_code, fallback, LOCAL_FALLBACK_REST_SECONDS,
            )
            return self._send_local(args, call, caller_options, fallback, style)

    def warm_up(self) -> None:
        """One tiny local request so the first real local answer does not wait for the model to load. Never raises."""
        call = {"messages": [{"role": "user", "content": "Merhaba"}], "think": False, "keep_alive": LOCAL_KEEP_ALIVE}
        started = time.monotonic()
        try:
            with _LOCAL_CALL_LOCK:
                self._ask_local_model((), call, {"num_predict": 1}, style=False)
        except Exception as error:  # noqa: BLE001 - a warm-up must not break startup
            _logger.warning("Local model warm-up failed (error_type=%s)", type(error).__name__)
            return
        _logger.info("Local model warm-up finished (model=%s, seconds=%.1f)", self.model_name, time.monotonic() - started)

    def warm_up_in_background(self) -> None:
        """Start the warm-up once, in the background, for an adapter built from the environment."""
        if not self.warm_up_on_start or self._warm_up_thread is not None:
            return
        self._warm_up_thread = threading.Thread(target=self.warm_up, name="ai-dnd-local-warm-up", daemon=True)
        self._warm_up_thread.start()

    def wait_for_warm_up(self, timeout: float | None = None) -> None:
        if self._warm_up_thread is not None:
            self._warm_up_thread.join(timeout)

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
            calls.append(self.model_name)
        _logger.info("Ollama chat request started (model=%s)", self.model_name)
        try:
            prepared = _attach_world_metadata(kwargs)
            # Ollama turns thinking on by itself for a model that has it, and the
            # engine reads only message content. Off is valid for every model.
            prepared = {"think": False, **prepared, "model": self.model_name}
            options = prepared.get("options")
            prepared["options"] = {"num_ctx": local_context_window(self.model_name), **(options or {})}
            prepared.setdefault("keep_alive", LOCAL_KEEP_ALIVE)
            local_seconds: list[float] = []
            # Classifier and front readings answer in a schema; the owner's prose rules are for narration.
            style = not (in_classifier_call() or in_front_call())

            def ask_local() -> Any:
                with _LOCAL_CALL_LOCK:  # the clock starts after the queue: only the model's own time is measured
                    started = time.monotonic()
                    local_response = self._ask_local_model(args, prepared, options, style=style)
                    local_seconds.append(time.monotonic() - started)
                return local_response

            if self._chain is None:
                response = ask_local()
                self._note_local_call(response, local_seconds[0])
                note_usage(self.model_name, response)
                return response
            response, provider = self._chain.chat(prepared, ask_local)
            if provider is None and local_seconds:
                self._note_local_call(response, local_seconds[0])
            if provider is not None and calls is not None:
                calls[-1] = provider
            note_usage(provider or self.model_name, response)
            return response
        except Exception as error:
            note_usage(self.model_name, failed=True)
            failures = _MODEL_FAILURES.get()
            if in_front_call() or (self._chain is not None and in_classifier_call()):
                # The owner's rule: the chain never fails a turn. The engine carries on with unknown intent.
                _logger.warning("Classifier unavailable; turn goes on (error_type=%s)", type(error).__name__)
            elif failures is not None:
                failures.append(ModelFailure(type(error).__name__))
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
