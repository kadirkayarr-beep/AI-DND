"""Explicit server-only local model selection; never downloads or falls back."""
from typing import Literal, get_args

LocalModelName = Literal[
    "qwen3:8b",
    "qwen3.5:4b-q4_K_M",
    "qwen3.5:9b-q4_K_M",
]
DEFAULT_LOCAL_MODEL: LocalModelName = "qwen3:8b"
SUPPORTED_LOCAL_MODELS = get_args(LocalModelName)


def validate_local_model(value: str) -> LocalModelName:
    if value not in SUPPORTED_LOCAL_MODELS:
        # Do not echo arbitrary configuration into logs or public errors.
        raise ValueError("Unsupported local model configuration.")
    return value
