"""Anti-farming budgets. Operational state, not canon.

Tavern re-entry does not mint a second gold incident. A rare find already
paid in the window is blocked. A new trigger after the cooldown may fire.
"""

from __future__ import annotations

from incidents import state as emergence_state
from incidents.models import REWARD_CLASSES

LOCATION_COOLDOWN = 3600
CLASS_COOLDOWN = {
    "none": 0,
    "trinket": 1800,
    "coin_small": 3600,
    "coin_modest": 7200,
    "mundane_item": 7200,
    "rare_find": 86400,
}
RARE_MAX_PER_WINDOW = 1
COIN_BUDGET_WINDOW = 86400
COIN_BUDGET_CP = 400


def signature(location_id, reward_class, trigger_kind):
    return f"{location_id}:{reward_class}:{trigger_kind}"


def _until(state, key, now):
    return int(state["cooldowns"].get(key, 0)) > now


def allowed(world, *, location_id, reward_class, trigger_kind):
    if reward_class not in REWARD_CLASSES or reward_class == "none":
        return True
    now = emergence_state.clock(world)
    state = emergence_state.read(world)
    sig = signature(location_id, reward_class, trigger_kind)
    if sig in state["paid_signatures"]:
        return False
    if _until(state, f"loc:{location_id}", now):
        return False
    if _until(state, f"class:{reward_class}", now):
        return False
    if reward_class == "rare_find":
        if state["budget"].get(f"rare:{now // CLASS_COOLDOWN['rare_find']}", 0) >= RARE_MAX_PER_WINDOW:
            return False
    if reward_class in {"coin_small", "coin_modest"}:
        bucket = f"coin:{now // COIN_BUDGET_WINDOW}"
        if state["budget"].get(bucket, 0) >= COIN_BUDGET_CP:
            return False
    return True


def consume(world, *, location_id, reward_class, trigger_kind, coin_cp=0):
    if reward_class == "none":
        return
    now = emergence_state.clock(world)
    state = emergence_state.ensure(world)
    sig = signature(location_id, reward_class, trigger_kind)
    if sig not in state["paid_signatures"]:
        state["paid_signatures"] = (state["paid_signatures"] + [sig])[-512:]
    state["cooldowns"][f"loc:{location_id}"] = now + LOCATION_COOLDOWN
    wait = CLASS_COOLDOWN.get(reward_class, LOCATION_COOLDOWN)
    if wait:
        state["cooldowns"][f"class:{reward_class}"] = now + wait
    if reward_class == "rare_find":
        key = f"rare:{now // CLASS_COOLDOWN['rare_find']}"
        state["budget"][key] = state["budget"].get(key, 0) + 1
    if coin_cp:
        key = f"coin:{now // COIN_BUDGET_WINDOW}"
        state["budget"][key] = state["budget"].get(key, 0) + int(coin_cp)


def recent_weight(world, reward_class):
    """Lower weight for a class still on cooldown. Used by later selectors."""
    if reward_class == "none":
        return 1
    now = emergence_state.clock(world)
    state = emergence_state.read(world)
    return 0 if _until(state, f"class:{reward_class}", now) else 1
