"""Request-scoped injection of bounded continuity into the frozen narrator."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from api.narrative_memory import (
    build_narrative_context,
    validate_narrative_memory,
)


@dataclass
class NarrativeTurnContext:
    memory: dict[str, Any]
    player_message: str
    action_result: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


_active_turn: ContextVar[NarrativeTurnContext | None] = ContextVar(
    "ai_dnd_narrative_turn",
    default=None,
)


@contextmanager
def narrative_turn_context(
    memory: dict[str, Any],
    player_message: str,
) -> Iterator[NarrativeTurnContext]:
    """Bind a copy of campaign memory to this request/thread only."""
    frame = NarrativeTurnContext(
        memory=validate_narrative_memory(memory),
        player_message=player_message,
    )
    token = _active_turn.set(frame)
    try:
        yield frame
    finally:
        _active_turn.reset(token)


def install_narrative_context_adapter(game_module: Any) -> None:
    """Wrap the engine context builder without changing game.py or its state."""
    if getattr(game_module, "_narrative_context_adapter_installed", False):
        return

    original_build = getattr(game_module, "build_world_context", None)
    original_ask = getattr(game_module, "ask_dungeon_master", None)
    if not callable(original_build) or not callable(original_ask):
        raise RuntimeError("The engine narrator context hooks are unavailable.")

    def ask_with_action_context(*args: Any, **kwargs: Any) -> Any:
        frame = _active_turn.get()
        if frame is not None:
            action_result = kwargs.get("action_result")
            if action_result is None and len(args) > 6:
                action_result = args[6]
            frame.action_result = (
                action_result if isinstance(action_result, dict) else None
            )
        return original_ask(*args, **kwargs)

    def build_with_narrative_context(
        npc_target: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        canonical_context = original_build(npc_target, *args, **kwargs)
        frame = _active_turn.get()
        if frame is None or not isinstance(canonical_context, dict):
            return canonical_context

        packet, diagnostics = build_narrative_context(
            frame.memory,
            canonical_context,
            frame.player_message,
            frame.action_result,
        )
        frame.diagnostics = diagnostics
        enriched = dict(canonical_context)
        enriched["narrative_continuity"] = {
            "authority_boundary": packet.get("authority_boundary", {}),
            "scene_type": diagnostics.get("scene_type"),
            "relevant_continuity": packet.get("relevant_continuity", {}),
        }
        return enriched

    game_module.ask_dungeon_master = ask_with_action_context
    game_module.build_world_context = build_with_narrative_context
    game_module._narrative_context_adapter_installed = True