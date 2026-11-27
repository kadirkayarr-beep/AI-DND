"""The one place a finished turn moves the counter and writes its history pair.

Every turn that ends moves flags["turn_index"] by exactly one and, when the turn
answers the player in words, adds the player line and the reply to the messages
as one pair. Undo restores both from its snapshot (D-581, D-502).
"""
from __future__ import annotations

from typing import Any


def advance(world_state: dict[str, Any]) -> int:
    """Move the turn counter by one and return the new index."""
    flags = world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    return flags["turn_index"]


def record_exchange(
    messages: list[dict[str, str]], player_line: str, reply: str,
) -> None:
    """Write the player line and the reply as one history pair."""
    messages.extend([
        {"role": "user", "content": player_line},
        {"role": "assistant", "content": reply},
    ])
