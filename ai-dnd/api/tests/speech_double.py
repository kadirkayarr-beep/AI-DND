"""Schema-routing model double for dialogue tests (synthetic provider only).

The default NPC route asks for a structured speech packet (`spoken_text`,
`stage_direction`) instead of narrator prose. This double answers each request
by the schema it carries and refuses schemas it does not know, so a test cannot
pass by accident through an unexpected call.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable


def reply(payload: dict) -> dict:
    return {"message": {"content": json.dumps(payload, ensure_ascii=False)}}


def speech_packet(spoken_text: str, stage_direction: str = "") -> dict:
    return reply({"spoken_text": spoken_text, "stage_direction": stage_direction})


def bare_speech(labelled: str) -> str:
    """`Name: “line”` -> `line`; the product renders the label itself."""
    text = labelled.strip()
    text = re.sub(r"^[^:“\"]{1,40}:\s*[“\"]?", "", text)
    return re.sub(r"[”\"]\s*$", "", text)


def request_kind(kwargs: dict[str, Any]) -> str:
    """`intent`, `speech`, `narration`; anything else is an unexpected request."""
    schema = kwargs.get("format")
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if "intent" in properties:
        return "intent"
    if "spoken_text" in properties:
        return "speech"
    if "narration" in properties:
        return "narration"
    raise AssertionError(f"Unexpected model request schema: {sorted(properties)}")


def routed_chat(
    handlers: dict[str, Callable[[dict], dict] | dict],
    kinds: list[str] | None = None,
) -> Callable[..., dict]:
    """Return a `chat` stand-in. `handlers` maps a kind to a payload or a callable."""

    def chat(*args: Any, **kwargs: Any) -> dict:
        kind = request_kind(kwargs)
        if kinds is not None:
            kinds.append(kind)
        handler = handlers.get(kind)
        if handler is None:
            raise AssertionError(f"No handler for model request kind: {kind}")
        return handler(kwargs) if callable(handler) else handler

    return chat
