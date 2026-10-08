"""The only writer of dynamic adventure state."""

from __future__ import annotations

import copy

from adventure.models import (
    STATES,
    TERMINAL_OUTCOMES,
    is_legacy_quest,
    validate_dynamic_saved_quest,
)

LEGAL = {
    "AVAILABLE": frozenset({"DISCOVERED"}),
    "DISCOVERED": frozenset({"ACTIVE", "ABANDONED", "FAILED"}),
    "ACTIVE": frozenset({"BLOCKED", "COMPLETED", "FAILED", "ABANDONED"}),
    "BLOCKED": frozenset({"ACTIVE", "FAILED", "ABANDONED"}),
    "COMPLETED": frozenset(),
    "FAILED": frozenset(),
    "ABANDONED": frozenset(),
}


class TransitionError(ValueError):
    """A caller asked for a state change the adventure owner refuses."""


def transition(quest, new_state, turn, outcome=None):
    """Return a new row in `new_state`. The input row is left unchanged.

    Legacy rows are refused here so a read, save, or cancel cannot promote
    them into a dynamic adventure.
    """
    if is_legacy_quest(quest):
        raise TransitionError("Eski görev dinamik maceraya dönüşmez.")
    if new_state not in STATES:
        raise TransitionError("Geçersiz macera geçişi.")
    try:
        validate_dynamic_saved_quest(quest, set())
    except ValueError as error:
        raise TransitionError("Geçersiz macera kaydı.") from error
    if new_state not in LEGAL[quest["status"]]:
        raise TransitionError("Geçersiz macera geçişi.")
    if type(turn) is not int or turn < quest["updated_turn"]:
        raise TransitionError("Geçersiz macera geçişi.")
    updated = copy.deepcopy(quest)
    updated["status"] = new_state
    updated["updated_turn"] = turn
    if new_state == "ACTIVE" and updated["accepted_turn"] is None:
        updated["accepted_turn"] = turn
    if new_state in TERMINAL_OUTCOMES:
        if outcome not in TERMINAL_OUTCOMES[new_state]:
            raise TransitionError("Geçersiz macera sonucu.")
        updated["outcome"] = outcome
    elif outcome is not None:
        raise TransitionError("Geçersiz macera sonucu.")
    else:
        updated["outcome"] = None
    validate_dynamic_saved_quest(updated, set())
    return updated
