"""Explicit server-only local model selection; never downloads. Only the 12B has a fallback (LOCAL_FALLBACK_MODELS)."""
import os
from typing import Literal, get_args

LocalModelName = Literal[
    "qwen3:8b",
    "qwen3.5:4b-q4_K_M",
    "qwen3.5:9b-q4_K_M",
    "gemma4-fast",
    "gemma4-12b-dm",
]
# Library default: what a bare AuthenticatedOllamaAdapter(client) selects. Test
# fixtures list this tag, so it stays put.
DEFAULT_LOCAL_MODEL: LocalModelName = "qwen3:8b"
# What the running game selects when AI_DND_OLLAMA_MODEL is not set. Two blind
# pilots at an 8K window with think off preferred Gemma (Oct 2026). Neither passed
# the formal no-hard-error gate, so this is a default, not an acceptance.
# `gemma4-fast` is the owner's Ollama model made from gemma4:e4b (Q4_K_M) with a Modelfile:
# num_ctx 16384, num_gpu 99, num_batch 512 and a draft model for speculative decoding.
# `gemma4-12b-dm` is the owner's Ollama model made from Gemma 4 12B IT (IQ3_M GGUF) with a Modelfile:
# num_ctx 12288, num_gpu 99, temperature 0.7, top_p 0.9. In the owner's DM test (Nov 2026) it kept the dice rule,
# NPC names and the scene better than the E4B, so it plays now; it needs about 7.1 GB of the 8 GB card.
PRODUCTION_LOCAL_MODEL: LocalModelName = "gemma4-12b-dm"
# When the selected model cannot be loaded (not installed, out of VRAM) the call goes to this one, and the log says so.
LOCAL_FALLBACK_MODELS: dict[str, LocalModelName] = {"gemma4-12b-dm": "gemma4-fast"}
SUPPORTED_LOCAL_MODELS = get_args(LocalModelName)


def validate_local_model(value: str) -> LocalModelName:
    if value not in SUPPORTED_LOCAL_MODELS:
        # Do not echo arbitrary configuration into logs or public errors.
        raise ValueError("Unsupported local model configuration.")
    return value


def selected_local_model() -> LocalModelName:
    """The model this server process plays with; raises on an unsupported value."""
    return validate_local_model(os.environ.get("AI_DND_OLLAMA_MODEL", PRODUCTION_LOCAL_MODEL))
