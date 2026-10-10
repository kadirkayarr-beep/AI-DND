"""Two-call arbiter. Emergence is lowest priority and never takes narration's slot.

Priority: intent when required, then narration of the committed result,
then one emergence proposal. Mechanics never spend a call.
"""

from __future__ import annotations

PROPOSE = "propose"
DEFER = "defer"


def ceiling():
    """The adapter owns the cap. The arbiter only reads it."""
    from api import ollama_adapter
    return ollama_adapter.MAX_MODEL_CALLS_PER_TURN


def decide(*, calls_used, narration_needed, intent_pending=False, incident_action=False):
    """Return PROPOSE only when a slot is free after reserving later priorities."""
    if type(calls_used) is not int or calls_used < 0:
        return DEFER
    if incident_action:
        return DEFER
    remaining = ceiling() - calls_used
    reserved = (1 if intent_pending else 0) + (1 if narration_needed else 0)
    return PROPOSE if remaining - reserved >= 1 else DEFER


def calls_used():
    """Calls already spent this turn, read from the adapter's own counter."""
    try:
        from api import ollama_adapter
    except Exception:
        return None
    calls = ollama_adapter._MODEL_CALLS.get()
    return None if calls is None else len(calls)
