"""Timed effect lifecycle (K03): clock-driven expiry from the ACTUAL elapsed game time, once per source event.

Each timed species effect keeps its remaining seconds in an optional, versioned `effect_clock` inside the species trait
state (saves without it adapt from the legacy turn counter: 1 turn = 6 s). Two boundaries exist and never both consume
the same moment:
  * "clock": time that really passed (wait, rest, travel, ...). Consumed here, from `campaign_time`'s actual elapsed seconds.
  * "round": the 6 s combat-round tick. The turn-boundary owner (game._finish_species_player_turn) already counts that
    moment per player turn, so this module leaves it alone and only re-syncs seconds from the turn counter.
"""
from __future__ import annotations

ROUND_SECONDS = 6
# effect id -> (active-marker field, turn-counter field, duration in seconds at activation)
TIMED_EFFECTS = {
    "celestial_revelation": ("active_celestial_form", "celestial_revelation_turns_remaining", 60),
    "large_form": (None, "large_form_turns_remaining", 600),
}


def _clock(state: dict) -> dict:
    return state.setdefault("effect_clock", {"version": 1, "remaining_s": {}, "last_event": {}})


def validate_clock(value) -> None:
    if not isinstance(value, dict) or set(value) != {"version", "remaining_s", "last_event"} or value["version"] != 1:
        raise ValueError("Kayıt etki saati geçersiz.")
    if not isinstance(value["remaining_s"], dict) or not isinstance(value["last_event"], dict):
        raise ValueError("Kayıt etki saati geçersiz.")
    for key, seconds in value["remaining_s"].items():
        if key not in TIMED_EFFECTS or type(seconds) is not int or seconds < 0:
            raise ValueError("Kayıt etki süresi geçersiz.")
    if any(key not in TIMED_EFFECTS or not isinstance(event, str) for key, event in value["last_event"].items()):
        raise ValueError("Kayıt etki olayı geçersiz.")


def start_effect(state: dict, effect_id: str) -> None:
    clock = _clock(state)
    clock["remaining_s"][effect_id] = TIMED_EFFECTS[effect_id][2]
    clock["last_event"].pop(effect_id, None)


def sync_from_turns(state: dict) -> None:
    """After the turn-boundary owner counted a player turn, the remaining seconds follow its counter."""
    for effect_id, (_marker, turns_field, _seconds) in TIMED_EFFECTS.items():
        if state.get(turns_field, 0) > 0:
            _clock(state)["remaining_s"][effect_id] = state[turns_field] * ROUND_SECONDS


def _is_active(state: dict, effect_id: str) -> bool:
    marker, turns_field, _seconds = TIMED_EFFECTS[effect_id]
    return state.get(turns_field, 0) > 0 and (marker is None or state.get(marker) is not None)


def _expire(state: dict, effect_id: str) -> None:
    marker, turns_field, _seconds = TIMED_EFFECTS[effect_id]
    state[turns_field] = 0
    if marker:
        state[marker] = None
    clock = _clock(state)
    clock["remaining_s"].pop(effect_id, None)
    clock["last_event"].pop(effect_id, None)


def advance_effects(session: object, elapsed_s: int, source_event_id: str, boundary: str) -> list[dict]:
    if type(elapsed_s) is not int or elapsed_s < 0:
        raise ValueError("Elapsed seconds are invalid.")
    # Rage has a separate hard cap even during combat rounds; dispatch before
    # species-only early returns. The canonical clock already advanced.
    import barbarian_rage
    barbarian_rage.settle(session)
    state = (session.character.get("species_trait_state") or None)
    if state is None or boundary == "round" or elapsed_s == 0:
        return []  # a zero-length step consumes nothing and must not occupy its source key
    if session.world_state.get("combat", {}).get("active"):
        return []  # in combat the turn-boundary owner counts the effect; two owners would decrement twice
    clock = _clock(state)
    events = []
    for effect_id, (_marker, turns_field, _seconds) in TIMED_EFFECTS.items():
        if not _is_active(state, effect_id) or clock["last_event"].get(effect_id) == source_event_id:
            continue
        remaining = clock["remaining_s"].get(effect_id)
        if remaining is None:  # legacy save: adapt from the turn counter
            remaining = state[turns_field] * ROUND_SECONDS
        remaining -= elapsed_s
        if remaining <= 0:
            _expire(state, effect_id)
            events.append({"trait": effect_id, "expired": True, "elapsed_s": elapsed_s,
                           "source_event_id": source_event_id, "boundary": boundary})
            continue
        clock["remaining_s"][effect_id] = remaining
        clock["last_event"][effect_id] = source_event_id
        state[turns_field] = -(-remaining // ROUND_SECONDS)  # ceil: a started round still counts
    if not clock["remaining_s"] and not clock["last_event"]:
        state.pop("effect_clock", None)
    return events
