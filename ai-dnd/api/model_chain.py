"""Cloud models in front of the local one, for the owner's local play only.

Off unless api.local_play starts it and AI_DND_MODEL_CHAIN names providers, so a
setting left in a window never reaches another process. The adapter hands every engine
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
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import ollama

from api import usage_ledger

GEMINI_MODEL = "gemini-3.5-flash-lite"
HAIKU_MODEL = "claude-haiku-5-5"
CHAIN_SETTING = "AI_DND_MODEL_CHAIN"
LOCAL_NAME = "gemma"
SPEND_FILE_NAME = "model-chain-spend.json"
_GEMINI_KEY_FILE = ".aidnd-gemini-key"
_ANTHROPIC_KEY_FILE = ".aidnd-anthropic-key"
CONNECT_TIMEOUT_SECONDS = 3
CALL_TIMEOUT_SECONDS = 20
# All cloud providers together, so the local model always starts in time. The slowest good
# answer measured was under 4 s, and two walks plus the adapter's 90 s stay inside the 240 s turn limit.
CLOUD_WALK_SECONDS = 25
DEFAULT_COOLDOWN_SECONDS = 60
# No monthly dollar cap since the owner lifted it on 2026-11-03; the ledger still counts tokens and still fails closed if unreadable.
# Gemini's free daily quota resets at midnight Pacific, which is 07:00 or 08:00 UTC.
_QUOTA_RESET_HOUR_UTC = 8
_DAILY_QUOTA = re.compile(r"per.?day|daily", re.IGNORECASE)
_DEFAULT_MAX_TOKENS = 1000
# Haiku's structured output rejects these keywords; Python still checks the reply.
_HAIKU_UNSUPPORTED = frozenset({
    "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "pattern", "default", "title",
})
# Only the compiler above refuses limits. A schema in the prompt keeps them, because nothing else tells Haiku.
_PROMPT_SCHEMA_NOISE = frozenset({"default", "title"})
_HAIKU_JSON_REQUIREMENT = "Return one JSON object only, with no code fence, matching this JSON schema: "
_GEMINI_UNSUPPORTED = frozenset({"$defs", "additionalProperties", "const", "default", "title"})
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_KINDS = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
_logger = logging.getLogger("ai_dnd.api.ollama")


@dataclass(frozen=True)
class ChainAttempt:
    """One provider try inside a chat call, for an optional observer. Tokens are zero when the try was skipped."""

    provider: str
    outcome: Literal["answered", "skipped"]
    reason: str | None
    seconds: float
    input_tokens: int
    output_tokens: int
    thought_tokens: int


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


def _haiku_schema(schema: dict[str, Any], dropped: frozenset[str] = _HAIKU_UNSUPPORTED) -> dict[str, Any]:
    result = {key: value for key, value in schema.items() if key not in dropped}
    for key in ("properties", "$defs"):
        if key in result:
            result[key] = {name: _haiku_schema(child, dropped) for name, child in result[key].items()}
    if "items" in result:
        result["items"] = _haiku_schema(result["items"], dropped)
    if "anyOf" in result:
        result["anyOf"] = [_haiku_schema(branch, dropped) for branch in result["anyOf"]]
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
        prompt_schema = json.dumps(_haiku_schema(schema, _PROMPT_SCHEMA_NOISE), ensure_ascii=False)
        system = f"{system}\n\n{_HAIKU_JSON_REQUIREMENT}{prompt_schema}".strip()
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
            return True

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


class _Unfit(Exception):
    """A reply no repair can bring inside the call's schema."""


def _is_kind(value: Any, kind: str) -> bool:
    if kind == "null":
        return value is None
    if isinstance(value, bool):
        return kind == "boolean"
    return isinstance(value, _KINDS[kind])


def _shaped(value: Any, schema: Mapping[str, Any], definitions: Mapping[str, Any]) -> Any:
    """The value as the local model's grammar would have left it: cut to the limits, or _Unfit.

    No compiled format holds a cloud provider to these limits, and the game drops a whole
    reply over one extra item. Repairing here keeps the answer and needs no second call.
    """
    if "$ref" in schema:
        return _shaped(value, definitions[schema["$ref"].rsplit("/", 1)[-1]], definitions)
    if "anyOf" in schema:
        for branch in sorted(schema["anyOf"], key=lambda branch: branch.get("type") == "null"):
            try:
                return _shaped(value, branch, definitions)
            except _Unfit:
                continue
        raise _Unfit
    kinds = schema.get("type")
    kinds = [kinds] if isinstance(kinds, str) else kinds
    if kinds == ["null"]:
        return None
    if kinds and not any(_is_kind(value, kind) for kind in kinds):
        raise _Unfit
    if ("enum" in schema and value not in schema["enum"]) or ("const" in schema and value != schema["const"]):
        raise _Unfit
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise _Unfit
        return value[:schema.get("maxLength")]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise _Unfit
    if isinstance(value, list):
        kept = value[:schema.get("maxItems")]
        if len(kept) < schema.get("minItems", 0):
            raise _Unfit
        return [_shaped(item, schema.get("items", {}), definitions) for item in kept]
    if isinstance(value, dict):
        if any(name not in value for name in schema.get("required", ())):
            raise _Unfit
        properties = schema.get("properties", {})
        closed = schema.get("additionalProperties") is False
        return {
            name: _shaped(item, properties[name], definitions) if name in properties else item
            for name, item in value.items()
            if name in properties or not closed
        }
    return value


def _for_the_game(reply: Reply, call: Mapping[str, Any]) -> str | None:
    """The text the game should receive, or None when the next provider should answer."""
    text = reply.text
    if not text.strip():
        return None
    if not call.get("format"):
        return None if reply.done_reason == "length" else text
    fence = _FENCE.match(text)
    text = fence.group(1) if fence else text
    schema = _schema(call)
    try:
        parsed = json.loads(text)
        shaped = parsed if schema is None else _shaped(parsed, schema, schema.get("$defs", {}))
    except (ValueError, _Unfit):
        return None
    if not (isinstance(shaped, dict) and shaped):
        return None
    return text if shaped == parsed else json.dumps(shaped, ensure_ascii=False)


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
        observer: Callable[[ChainAttempt], None] | None = None,
    ):
        self._providers = providers
        self._now = now
        self._observer = observer
        self._resting_until: dict[str, datetime] = {}
        # No redirects and no proxy or netrc from the environment: a key goes to its own host only.
        self._http = httpx.Client(transport=transport, trust_env=False)

    def provider_names(self) -> list[str]:
        return [provider.name for provider in self._providers if self._may_spend(provider)]

    def model_names(self) -> list[str]:
        return [provider.model for provider in self._providers if self._may_spend(provider)]

    def can_answer(self) -> bool:
        return any(self._ready(provider) for provider in self._providers)

    @staticmethod
    def _may_spend(provider: Provider) -> bool:
        return provider.spend is None or provider.spend.allows_a_call()

    def _ready(self, provider: Provider) -> bool:
        until = self._resting_until.get(provider.name)
        if until is not None and self._now() < until:
            return False
        return self._may_spend(provider)

    def _rest(self, provider: Provider, text: str, retry_after: str | None) -> None:
        moment = self._now()
        if _DAILY_QUOTA.search(text):
            self._resting_until[provider.name] = _next_quota_day(moment)
            return
        seconds = _retry_after_seconds(retry_after, moment)
        self._resting_until[provider.name] = moment + timedelta(seconds=seconds)

    def _notify(self, attempt: ChainAttempt) -> None:
        """Tell the observer; whatever it does wrong never reaches the game call."""
        if self._observer is None:
            return
        try:
            self._observer(attempt)
        except Exception as error:
            _logger.warning("Model chain observer failed (error=%s)", type(error).__name__)

    def _post(self, provider: Provider, call: Mapping[str, Any], deadline: datetime) -> tuple[int, str, str | None]:
        """One request inside the time left. The deadline also stops a reply that trickles in."""
        limit = min(CALL_TIMEOUT_SECONDS, (deadline - self._now()).total_seconds())
        timeout = httpx.Timeout(limit, connect=min(CONNECT_TIMEOUT_SECONDS, limit))
        with self._http.stream(
            "POST", provider.url, headers=dict(provider.headers), json=provider.body(call), timeout=timeout,
        ) as response:
            body = bytearray()
            for chunk in response.iter_bytes():
                body += chunk
                if self._now() >= deadline:
                    raise httpx.ReadTimeout("The cloud walk ran out of time.")
            return response.status_code, body.decode("utf-8", "replace"), response.headers.get("Retry-After")

    def _ask(self, provider: Provider, call: Mapping[str, Any], deadline: datetime) -> Reply:
        status, text, retry_after = self._post(provider, call, deadline)
        if status == 429:
            self._rest(provider, text, retry_after)
            raise _Skipped("rate_limited")
        if status != 200:
            raise _Skipped(f"http_{status}")
        reply = provider.read(json.loads(text))
        if provider.spend is not None:
            provider.spend.add(reply)  # billed whether or not the game can use it
        text = _for_the_game(reply, call)
        if text is None:
            raise _Skipped("unusable_reply")
        return replace(reply, text=text)

    def chat(self, call: Mapping[str, Any], local: Callable[[], Any]) -> tuple[Any, str | None]:
        """One engine call: the response in Ollama's shape, and the cloud provider that answered it.

        The provider is None when the local model answered; its errors are the caller's.
        """
        deadline = self._now() + timedelta(seconds=CLOUD_WALK_SECONDS)
        for provider in self._providers:
            if not self._ready(provider):
                continue
            if self._now() >= deadline:
                break
            started = time.monotonic()
            try:
                reply = self._ask(provider, call, deadline)
            except Exception as error:
                if isinstance(error, httpx.TransportError):
                    # A dead route would cost this wait again on every call. A 5xx answers at once, so it rests nobody.
                    self._resting_until[provider.name] = self._now() + timedelta(seconds=DEFAULT_COOLDOWN_SECONDS)
                reason = error.reason if isinstance(error, _Skipped) else type(error).__name__
                seconds = time.monotonic() - started
                _logger.info("Model chain skipped (provider=%s, reason=%s, seconds=%.2f)",
                             provider.name, reason, seconds)
                self._notify(ChainAttempt(provider.name, "skipped", reason, seconds, 0, 0, 0))
                continue
            seconds = time.monotonic() - started
            _logger.info("Model chain answered (provider=%s, seconds=%.2f, thought_tokens=%d)",
                         provider.name, seconds, reply.thought_tokens)
            self._notify(ChainAttempt(
                provider.name, "answered", None, seconds,
                reply.input_tokens, reply.output_tokens, reply.thought_tokens,
            ))
            return ollama.ChatResponse(
                model=provider.model, done=True, done_reason=reply.done_reason,
                message=ollama.Message(role="assistant", content=reply.text),
                prompt_eval_count=reply.input_tokens, eval_count=reply.output_tokens,
            ), provider.name
        return local(), None


def _read_key(file_name: str) -> str:
    home = os.environ.get("USERPROFILE")
    if not home:
        return ""
    try:
        return (Path(home) / file_name).read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        return ""


def _spend_path() -> Path:
    """One file per user: the cap belongs to the key, not to a save folder."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AI-DND" / SPEND_FILE_NAME


def _usage_path() -> Path:
    """The usage log sits beside the spend file: one per user, shared by every save folder and process."""
    return _spend_path().with_name(usage_ledger.USAGE_FILE_NAME)


def ledger_observer(ledger: usage_ledger.UsageLedger) -> Callable[[ChainAttempt], None]:
    """An observer that writes every provider attempt to the usage ledger (which never raises)."""
    def observe(attempt: ChainAttempt) -> None:
        ledger.record(
            attempt.provider,
            input_tokens=attempt.input_tokens, output_tokens=attempt.output_tokens,
            thought_tokens=attempt.thought_tokens, seconds=attempt.seconds, outcome=attempt.outcome,
        )
    return observe


def from_environment() -> ModelChain | None:
    """The configured chain, or None for today's local-only game. Reads keys only when asked to."""
    names = [name.strip().lower() for name in os.environ.get(CHAIN_SETTING, "").split(",") if name.strip()]
    if not names:
        return None
    if LOCAL_NAME in names:
        names = names[:names.index(LOCAL_NAME)]
    providers = []
    for name in dict.fromkeys(names):
        if name == "gemini" and (key := _read_key(_GEMINI_KEY_FILE)):
            providers.append(gemini(key))
        elif name == "haiku" and (key := _read_key(_ANTHROPIC_KEY_FILE)):
            providers.append(haiku(key, HaikuSpend(_spend_path(), lambda: datetime.now().astimezone())))
    chain = None
    if providers:
        chain = ModelChain(providers, observer=ledger_observer(usage_ledger.UsageLedger(_usage_path())))
    _logger.info("Model chain providers on: %s", ",".join([*(chain.provider_names() if chain else ()), "local"]))
    return chain
