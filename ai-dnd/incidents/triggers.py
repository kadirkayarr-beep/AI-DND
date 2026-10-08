"""Python-only triggers and the silence-first selector.

A trigger is an authoritative scene event. The selector decides from the
seeded stream whether anything happens; an ordinary inn is often quiet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from incidents import categories, envelope as envelope_owner
from incidents import horizon, rng
from incidents.models import OPEN_LIFECYCLES

_WILDERNESS_TYPES = frozenset({"wilderness", "forest", "road", "route"})
_REST_ACTIONS = frozenset({"rest", "short_rest", "long_rest"})

_LOOK_AROUND = re.compile(
    r"(etraf\w*|çevre\w*|ortal\w*)\s+(ne\s+oluyor|ne\s+var|bak\w*|göz\w*|dinl\w*|incel\w*)"
    r"|neler\s+oluyor|what\s+is\s+happening|look\s+around",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Selection:
    trigger: dict
    trigger_id: str
    decisions: dict


def detect(world, *, action_result, player_text, location_changed):
    """Return one in-horizon trigger dict or None. Narration is never a trigger."""
    here = world.get("location")
    if not isinstance(here, str):
        return None
    from incidents.bridge import aftermath_seed
    aftermath = aftermath_seed(action_result)
    if aftermath is not None:
        return {
            "kind": "aftermath",
            "location_id": here,
            "source_location_id": here,
            "source_event_id": aftermath["source_event_id"],
        }
    record = world.get("locations", {}).get(here, {})
    loc_type = record.get("type") if isinstance(record, dict) else None
    if location_changed or (
        isinstance(action_result, dict) and action_result.get("action") == "travel"
        and action_result.get("success") is True
    ):
        if loc_type in _WILDERNESS_TYPES or here == "forest":
            return {"kind": "travel_segment", "location_id": here}
        return {"kind": "arrival", "location_id": here}
    if isinstance(action_result, dict) and action_result.get("action") in _REST_ACTIONS:
        return {"kind": "rest", "location_id": here}
    if isinstance(player_text, str) and _LOOK_AROUND.search(player_text):
        return {"kind": "look_around", "location_id": here}
    return None


def occupied(world, location_id):
    return any(
        isinstance(row, dict) and row.get("location_id") == location_id
        and row.get("lifecycle") in OPEN_LIFECYCLES
        for row in world.get("incidents", {}).values()
    )


def select(world, *, campaign_id, trigger, profile, lore_state=None, combat_outcome_id=None):
    """Silence first, then horizon and density. Returns a Selection or None."""
    if not horizon.in_horizon(world, trigger) or profile is None:
        return None
    if occupied(world, trigger["location_id"]):
        return None
    trigger_id = envelope_owner.trigger_id_for(
        world, trigger_kind=trigger["kind"], location_id=trigger["location_id"],
        combat_outcome_id=combat_outcome_id, lore_state=lore_state,
    )
    decisions = rng.decide(
        campaign_id, trigger_id,
        silence_rate=profile["silence_rate"],
        category_weights=tuple(profile["category_weights"]),
        reward_weights=tuple(profile["reward_weights"]),
    )
    if decisions["silent"]:
        return None
    if not categories.motif_allowed(world, decisions["category"]):
        return None
    return Selection(trigger=dict(trigger), trigger_id=trigger_id, decisions=decisions)
