"""Cloud models in front of the local one, for the owner's local play only.

Off unless AI_DND_MODEL_CHAIN names providers. The adapter hands every engine
call here; a provider that fails is skipped inside that same call and the local
model answers last with its own options. Only the existing prompt leaves this
machine. Keys stay in this process: never logged, returned, saved or put in an
error, and Gemini's goes in a header, never the URL.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

GEMINI_MODEL = "gemini-3.5-flash-lite"
HAIKU_MODEL = "claude-haiku-5-5"
_DEFAULT_MAX_TOKENS = 1000
# Haiku's structured output rejects these keywords; Python still checks the reply.
_HAIKU_UNSUPPORTED = frozenset({"minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "pattern"})


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


def _map_children(schema: dict[str, Any], convert: Any) -> dict[str, Any]:
    result = dict(schema)
    if "properties" in result:
        result["properties"] = {name: convert(child) for name, child in result["properties"].items()}
    if "items" in result:
        result["items"] = convert(result["items"])
    return result


def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = _map_children(schema, _gemini_schema)
    result.pop("additionalProperties", None)
    kinds = result.get("type")
    if isinstance(kinds, list):
        result["type"] = next(kind for kind in kinds if kind != "null")
        if "null" in kinds:
            result["nullable"] = True
    return result


def _haiku_schema(schema: dict[str, Any]) -> dict[str, Any]:
    result = _map_children(schema, _haiku_schema)
    for keyword in _HAIKU_UNSUPPORTED:
        result.pop(keyword, None)
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
    if schema is not None:
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
