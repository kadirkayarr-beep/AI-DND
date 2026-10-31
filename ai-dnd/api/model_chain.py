"""Cloud models in front of the local one, for the owner's local play only.

Off unless AI_DND_MODEL_CHAIN names providers. The adapter hands every engine
call here; a provider that fails is skipped inside that same call and the local
model answers last with its own options. Only the existing prompt leaves this
machine. Keys stay in this process: never logged, returned, saved or put in an
error, and Gemini's goes in a header, never the URL.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import ollama

GEMINI_MODEL = "gemini-3.5-flash-lite"
HAIKU_MODEL = "claude-haiku-5-5"
CHAIN_SETTING = "AI_DND_MODEL_CHAIN"
LOCAL_NAME = "gemma"
SPEND_FILE_NAME = "model-chain-spend.json"
_GEMINI_KEY_FILE, _GEMINI_KEY_ENV = ".aidnd-gemini-key", "GEMINI_API_KEY"
_ANTHROPIC_KEY_FILE, _ANTHROPIC_KEY_ENV = ".aidnd-anthropic-key", "ANTHROPIC_API_KEY"
CALL_TIMEOUT_SECONDS = 20
DEFAULT_COOLDOWN_SECONDS = 60
HAIKU_MONTHLY_CAP_USD = 4.0
_HAIKU_INPUT_USD_PER_MILLION = 0.10
_HAIKU_OUTPUT_USD_PER_MILLION = 0.50
# Gemini's free daily quota resets at midnight Pacific, which is 07:00 or 08:00 UTC.
_QUOTA_RESET_HOUR_UTC = 8
_DAILY_QUOTA = re.compile(r"per.?day|daily", re.IGNORECASE)
_DEFAULT_MAX_TOKENS = 1000
# Haiku's structured output rejects these keywords; Python still checks the reply.
_HAIKU_UNSUPPORTED = frozenset({
    "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "pattern", "default", "title",
})
_HAIKU_JSON_REQUIREMENT = "Return one JSON object only, with no code fence, matching this JSON schema: "
_GEMINI_UNSUPPORTED = frozenset({"$defs", "additionalProperties", "const", "default", "title"})
_logger = logging.getLogger("ai_dnd.api.ollama")


@dataclass(frozen=True)
class Reply:
    text: str
    done_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0


def _prompt(call: Mapping[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    """The system text and the remaining turns: all that a provider ever receives."""
    system, turns = [], []
    for message in call.get("messages") or ():
        role, content = message.get("role"), str(message.get("content", ""))
        if role == "system":
            system.append(content)
        else:
            turns.append((role, content))
    return "\n\n".join(system), turns


def _max_tokens(call: Mapping[str, Any]) -> int:
    return (call.get("options") or {}).get("num_predict") or _DEFAULT_MAX_TOKENS


def _schema(call: Mapping[str, Any]) -> dict[str, Any] | None:
    schema = call.get("format")
    return schema if isinstance(schema, dict) else None


def _gemini_schema(schema: dict[str, Any], definitions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Gemini's schema has no references, constants or null type, so those become plain fields."""
    definitions = schema.get("$defs", {}) if definitions is None else definitions
    if "$ref" in schema:
        return _gemini_schema(definitions[schema["$ref"].rsplit("/", 1)[-1]], definitions)
    result = {key: value for key, value in schema.items() if key not in _GEMINI_UNSUPPORTED}
    if "const" in schema:
        result["enum"] = [schema["const"]]
    if "enum" in result:  # the game offers [""] when it has no ids; Gemini refuses an empty value
        result["enum"] = [value for value in result["enum"] if value != ""]
        if not result["enum"]:
            del result["enum"]
    if "properties" in result:
        result["properties"] = {name: _gemini_schema(child, definitions) for name, child in result["properties"].items()}
    if "items" in result:
        result["items"] = _gemini_schema(result["items"], definitions)
    branches = result.pop("anyOf", [])
    real = [_gemini_schema(branch, definitions) for branch in branches if branch.get("type") != "null"]
    if len(real) == 1:
        result.update(real[0])
    elif real:
        result["anyOf"] = real
    kinds = result.get("type")
    nullable = len(real) < len(branches) or kinds == "null" or (isinstance(kinds, list) and "null" in kinds)
    if isinstance(kinds, list):
        result["type"] = next(kind for kind in kinds if kind != "null")
    elif kinds == "null":
        result["type"] = "string"
    if nullable:
        result["nullable"] = True
    return result


def _haiku_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in schema.items() if key not in _HAIKU_UNSUPPORTED}
    for key in ("properties", "$defs"):
        if key in result:
            result[key] = {name: _haiku_schema(child) for name, child in result[key].items()}
    if "items" in result:
        result["items"] = _haiku_schema(result["items"])
    if "anyOf" in result:
        result["anyOf"] = [_haiku_schema(branch) for branch in result["anyOf"]]
    kinds = result.get("type")
    if kinds == "object" or (isinstance(kinds, list) and "object" in kinds):
        result["additionalProperties"] = False
    return result


def gemini_body(call: Mapping[str, Any]) -> dict[str, Any]:
    system, turns = _prompt(call)
    # This model takes no budget of zero and has no "off" level. Minimal is its lowest.
    config: dict[str, Any] = {"maxOutputTokens": _max_tokens(call), "thinkingConfig": {"thinkingLevel": "minimal"}}
    temperature = (call.get("options") or {}).get("temperature")
    if temperature is not None:
        config["temperature"] = temperature
    if call.get("format"):
        config["responseMimeType"] = "application/json"
    schema = _schema(call)
    if schema is not None:
        config["responseSchema"] = _gemini_schema(schema)
    body: dict[str, Any] = {
        "contents": [
            {"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]}
            for role, text in turns
        ],
        "generationConfig": config,
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body


def haiku_body(call: Mapping[str, Any]) -> dict[str, Any]:
    system, turns = _prompt(call)
    # No temperature: Haiku 5.5 answers a non-default value with a 400.
    output: dict[str, Any] = {"effort": "low"}
    schema = _schema(call)
    if schema is not None and "$defs" in schema:
        # The classifier's envelope never compiled: 60 s without an answer, or "Schema is too complex".
        system = f"{system}\n\n{_HAIKU_JSON_REQUIREMENT}{json.dumps(_haiku_schema(schema), ensure_ascii=False)}".strip()
    elif schema is not None:
        output["format"] = {"type": "json_schema", "schema": _haiku_schema(schema)}
    body: dict[str, Any] = {
        "model": HAIKU_MODEL,
        "max_tokens": _max_tokens(call),
        "thinking": {"type": "disabled"},
        "output_config": output,
        "messages": [{"role": role, "content": text} for role, text in turns],
    }
    if system:
        body["system"] = system
    return body


def gemini_read(payload: Mapping[str, Any]) -> Reply:
    usage = payload.get("usageMetadata") or {}
    candidates = payload.get("candidates") or [{}]
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or ()
    return Reply(
        text="".join(part.get("text", "") for part in parts if not part.get("thought")),
        done_reason="length" if candidate.get("finishReason") == "MAX_TOKENS" else "stop",
        input_tokens=usage.get("promptTokenCount", 0),
        output_tokens=usage.get("candidatesTokenCount", 0),
        thought_tokens=usage.get("thoughtsTokenCount", 0),
    )


def haiku_read(payload: Mapping[str, Any]) -> Reply:
    usage = payload.get("usage") or {}
    stop = payload.get("stop_reason")
    blocks = payload.get("content") or ()
    return Reply(
        text="" if stop == "refusal" else "".join(block.get("text", "") for block in blocks if block.get("type") == "text"),
        done_reason="length" if stop == "max_tokens" else "stop",
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )


class HaikuSpend:
    """This calendar month's Haiku tokens in a local file. When in doubt it stops Haiku."""

    def __init__(self, path: Path, now: Callable[[], datetime]):
        self._path = path
        self._now = now
        self._lock = threading.Lock()
        self._save_failed = False

    def _month(self) -> str:
        return self._now().strftime("%Y-%m")

    def _load(self) -> tuple[int, int] | None:
        """Tokens so far this month; None when the file cannot be trusted."""
        try:
            saved = json.loads(self._path.read_text(encoding="utf-8"))
            month, tokens = saved["month"], (saved["input_tokens"], saved["output_tokens"])
        except FileNotFoundError:
            return 0, 0
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not all(type(count) is int for count in tokens):
            return None
        return tokens if month == self._month() else (0, 0)

    def allows_a_call(self) -> bool:
        with self._lock:
            tokens = self._load()
            if tokens is None or self._save_failed:
                return False
            usd = (tokens[0] * _HAIKU_INPUT_USD_PER_MILLION + tokens[1] * _HAIKU_OUTPUT_USD_PER_MILLION) / 1_000_000
            return usd < HAIKU_MONTHLY_CAP_USD

    def add(self, reply: Reply) -> None:
        with self._lock:
            tokens = self._load()
            if tokens is None:
                return
            saved = {"month": self._month(), "input_tokens": tokens[0] + reply.input_tokens,
                     "output_tokens": tokens[1] + reply.output_tokens}
            temporary = self._path.with_suffix(".tmp")
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(json.dumps(saved), encoding="utf-8")
                os.replace(temporary, self._path)
            except OSError:
                self._save_failed = True
                _logger.warning("Model chain could not save the Haiku count; Haiku stops for this run.")


@dataclass(frozen=True)
class Provider:
    name: str
    model: str
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: Callable[[Mapping[str, Any]], dict[str, Any]] = field(repr=False)
    read: Callable[[Mapping[str, Any]], Reply] = field(repr=False)
    spend: HaikuSpend | None = field(default=None, repr=False)


def gemini(key: str) -> Provider:
    return Provider(
        "gemini", GEMINI_MODEL,
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        {"x-goog-api-key": key}, gemini_body, gemini_read,
    )


def haiku(key: str, spend: HaikuSpend) -> Provider:
    return Provider(
        "haiku", HAIKU_MODEL, "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01"}, haiku_body, haiku_read, spend,
    )


class _Skipped(Exception):
    """A provider gave no usable answer. Carries a fixed reason, never provider text."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _usable(text: str, call: Mapping[str, Any]) -> bool:
    if not text.strip():
        return False
    if not call.get("format"):
        return True
    try:
        parsed = json.loads(text)
    except ValueError:
        return False
    return isinstance(parsed, dict) and bool(parsed)


def _retry_after_seconds(value: str | None, moment: datetime) -> float:
    if value is None:
        return DEFAULT_COOLDOWN_SECONDS
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(value) - moment).total_seconds())
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_SECONDS


def _next_quota_day(moment: datetime) -> datetime:
    reset = moment.astimezone(timezone.utc).replace(hour=_QUOTA_RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
    return reset if reset > moment else reset + timedelta(days=1)


class ModelChain:
    def __init__(
        self,
        providers: list[Provider],
        *,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ):
        self._providers = providers
        self._now = now
        self._resting_until: dict[str, datetime] = {}
        # No redirects and no proxy or netrc from the environment: a key goes to its own host only.
        self._http = httpx.Client(timeout=CALL_TIMEOUT_SECONDS, transport=transport, trust_env=False)

    def provider_names(self) -> list[str]:
        return [provider.name for provider in self._providers if self._may_spend(provider)]

    def model_names(self) -> list[str]:
        return [provider.model for provider in self._providers if self._may_spend(provider)]

    @staticmethod
    def _may_spend(provider: Provider) -> bool:
        return provider.spend is None or provider.spend.allows_a_call()

    def _ready(self, provider: Provider) -> bool:
        until = self._resting_until.get(provider.name)
        if until is not None and self._now() < until:
            return False
        return self._may_spend(provider)

    def _rest(self, provider: Provider, response: httpx.Response) -> None:
        moment = self._now()
        if _DAILY_QUOTA.search(response.text):
            self._resting_until[provider.name] = _next_quota_day(moment)
            return
        seconds = _retry_after_seconds(response.headers.get("Retry-After"), moment)
        self._resting_until[provider.name] = moment + timedelta(seconds=seconds)

    def _ask(self, provider: Provider, call: Mapping[str, Any]) -> Reply:
        response = self._http.post(provider.url, headers=dict(provider.headers), json=provider.body(call))
        if response.status_code == 429:
            self._rest(provider, response)
            raise _Skipped("rate_limited")
        if response.status_code != 200:
            raise _Skipped(f"http_{response.status_code}")
        reply = provider.read(response.json())
        if provider.spend is not None:
            provider.spend.add(reply)  # billed whether or not the game can use it
        if not _usable(reply.text, call):
            raise _Skipped("unusable_reply")
        return reply

    def chat(self, call: Mapping[str, Any], local: Callable[[], Any]) -> tuple[Any, str | None]:
        """One engine call: the response in Ollama's shape, and the cloud provider that answered it.

        The provider is None when the local model answered; its errors are the caller's.
        """
        for provider in self._providers:
            if not self._ready(provider):
                continue
            started = time.monotonic()
            try:
                reply = self._ask(provider, call)
            except Exception as error:
                reason = error.reason if isinstance(error, _Skipped) else type(error).__name__
                _logger.info("Model chain skipped (provider=%s, reason=%s, seconds=%.2f)",
                             provider.name, reason, time.monotonic() - started)
                continue
            _logger.info("Model chain answered (provider=%s, seconds=%.2f, thought_tokens=%d)",
                         provider.name, time.monotonic() - started, reply.thought_tokens)
            return ollama.ChatResponse(
                model=provider.model, done=True, done_reason=reply.done_reason,
                message=ollama.Message(role="assistant", content=reply.text),
                prompt_eval_count=reply.input_tokens, eval_count=reply.output_tokens,
            ), provider.name
        return local(), None


def _read_key(file_name: str, environment_name: str) -> str:
    home = os.environ.get("USERPROFILE")
    if home:
        try:
            key = (Path(home) / file_name).read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError):
            key = ""
        if key:
            return key
    return os.environ.get(environment_name, "").strip()


def _spend_path() -> Path:
    from api.persistence.campaign_store import default_campaign_db_path

    return default_campaign_db_path().parent / SPEND_FILE_NAME


def from_environment() -> ModelChain | None:
    """The configured chain, or None for today's local-only game. Reads keys only when asked to."""
    names = [name.strip().lower() for name in os.environ.get(CHAIN_SETTING, "").split(",") if name.strip()]
    if not names:
        return None
    if LOCAL_NAME in names:
        names = names[:names.index(LOCAL_NAME)]
    providers = []
    for name in dict.fromkeys(names):
        if name == "gemini" and (key := _read_key(_GEMINI_KEY_FILE, _GEMINI_KEY_ENV)):
            providers.append(gemini(key))
        elif name == "haiku" and (key := _read_key(_ANTHROPIC_KEY_FILE, _ANTHROPIC_KEY_ENV)):
            providers.append(haiku(key, HaikuSpend(_spend_path(), lambda: datetime.now().astimezone())))
    chain = ModelChain(providers) if providers else None
    _logger.info("Model chain providers on: %s", ",".join([*(chain.provider_names() if chain else ()), "local"]))
    return chain
