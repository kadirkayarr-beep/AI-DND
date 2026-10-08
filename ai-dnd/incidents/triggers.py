"""Python-only triggers and the silence-first selector.

A trigger is an authoritative scene event. The selector decides from the
seeded stream whether anything happens; an ordinary inn is often quiet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from incidents import envelope as envelope_owner
from incidents import horizon, rng
from incidents.models import OPEN_LIFECYCLES

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
    if location_changed or (
        isinstance(action_result, dict) and action_result.get("action") == "travel"
        and action_result.get("success") is True
    ):
        return {"kind": "arrival", "location_id": here}
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
    return Selection(trigger=dict(trigger), trigger_id=trigger_id, decisions=decisions)
