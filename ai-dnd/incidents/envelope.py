"""Reality Envelope and canon stamp.

Python builds the envelope before any model call. The stamp covers only the
state domains the envelope read, so unrelated writes leave it unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json

from incidents import state as emergence_state
from incidents import versions
from incidents.models import OPEN_LIFECYCLES, REWARD_CLASSES

MAX_ENVELOPE_BYTES = 32_768
CLOCK_BUCKET_SECONDS = 3600
TIER_CEILING_MAX = 4

ENVELOPE_FIELDS = frozenset({
    "envelope_version", "campaign_id", "trigger_id", "trigger_kind",
    "location_id", "parent_location_id", "clock_bucket", "profile_id",
    "tier_ceiling", "reward_ceiling", "threat_band",
    "allowed_categories", "allowed_roles", "allowed_subscene_kinds",
    "allowed_entity_ids", "allowed_faction_ids", "faction_rank_ceiling",
    "allowed_creature_ids", "protected_names", "hidden_context",
    "known_fact_ids", "decisions", "expiry_seconds", "stamp_inputs", "canon_stamp",
})


class EnvelopeError(ValueError):
    """The envelope cannot be built. No model call may follow."""


def _hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def envelope_hash(envelope):
    return _hash(envelope)


def clock_bucket(world):
    return emergence_state.clock(world) // CLOCK_BUCKET_SECONDS


def _npcs_at(world, location_id):
    return [
        npc for npc in world.get("npcs", [])
        if isinstance(npc, dict) and npc.get("location") == location_id
        and isinstance(npc.get("id"), str)
        and npc.get("combat_status") not in ("dead", "defeated")
    ]


def _identity(npc):
    return {"id": npc.get("id"), "name": npc.get("name"), "role": npc.get("role")}


def _occupancy(world, location_id):
    rows = world.get("incidents", {})
    if not isinstance(rows, dict):
        raise EnvelopeError("Incident state is invalid.")
    return sorted(
        [incident_id, row.get("lifecycle")]
        for incident_id, row in rows.items()
        if isinstance(row, dict) and row.get("location_id") == location_id
        and row.get("lifecycle") in OPEN_LIFECYCLES
    )


def known_fact_ids(world, location_id):
    """Facade-known incident facts for incidents anchored here."""
    local = {
        incident_id for incident_id, row in world.get("incidents", {}).items()
        if isinstance(row, dict) and row.get("location_id") == location_id
    }
    known = []
    for entry in world.get("player_knowledge", []):
        if not isinstance(entry, str) or not entry.startswith("incident:"):
            continue
        parts = entry.split(":", 2)
        if len(parts) == 3 and parts[1] in local:
            known.append(entry)
    return sorted(set(known))


def _faction_reads(lore_state, faction_ids):
    rows = {}
    for row in getattr(lore_state, "faction_standings", ()) or ():
        if row.faction_id in faction_ids:
            rows[row.faction_id] = row.standing
    return {faction_id: rows.get(faction_id, 0) for faction_id in sorted(faction_ids)}


def compute_stamp(world, spec, lore_state=None):
    """Hash of only the precondition domains named in ``spec``."""
    location_id = spec["location_id"]
    record = world.get("locations", {}).get(location_id)
    parent = record.get("parent_location_id") if isinstance(record, dict) else None
    cast = _npcs_at(world, location_id)
    named = {npc["id"]: npc for npc in world.get("npcs", []) if isinstance(npc, dict) and "id" in npc}
    domains = {
        "scene": [location_id, parent, isinstance(record, dict)],
        "cast": sorted(npc["id"] for npc in cast),
        "identities": [_identity(named[item]) if item in named else None for item in spec["entity_ids"]],
        "occupancy": _occupancy(world, location_id),
        "factions": _faction_reads(lore_state, spec["faction_ids"]),
        "known": known_fact_ids(world, location_id),
        "horizon": [spec["trigger_kind"], spec["clock_bucket"]],
        "combat_outcome": spec.get("combat_outcome_id"),
    }
    if spec.get("include_rewards"):
        current = emergence_state.read(world)
        domains["rewards"] = {
            "budget": current["budget"],
            "paid": sorted(current["paid_signatures"]),
        }
    return _hash(domains)


def base_spec(world, *, trigger_kind, location_id, combat_outcome_id=None):
    return {
        "location_id": location_id,
        "entity_ids": sorted(npc["id"] for npc in _npcs_at(world, location_id)),
        "faction_ids": [],
        "trigger_kind": trigger_kind,
        "clock_bucket": clock_bucket(world),
        "combat_outcome_id": combat_outcome_id,
        "include_rewards": False,
    }


def trigger_id_for(world, *, trigger_kind, location_id, combat_outcome_id=None, lore_state=None):
    """Stable trigger id. Harmless writes outside the domains keep it the same."""
    spec = base_spec(
        world, trigger_kind=trigger_kind, location_id=location_id,
        combat_outcome_id=combat_outcome_id,
    )
    digest = _hash([trigger_kind, location_id, spec["clock_bucket"], compute_stamp(world, spec, lore_state)])
    return f"trg:{trigger_kind}:{digest[:32]}"


def build(
    world,
    *,
    campaign_id,
    trigger_id,
    trigger_kind,
    location_id,
    profile,
    decisions,
    hidden_context=None,
    faction_ids=(),
    combat_outcome_id=None,
    lore_state=None,
):
    """Build the envelope. Player text is never an input."""
    if location_id not in world.get("locations", {}):
        raise EnvelopeError("The trigger location is not a verified location.")
    reward_ceiling = decisions.get("reward_class", "none")
    if reward_ceiling not in REWARD_CLASSES:
        raise EnvelopeError("Reward ceiling is invalid.")
    tier_ceiling = min(int(profile["tier_ceiling"]), TIER_CEILING_MAX)
    spec = base_spec(
        world, trigger_kind=trigger_kind, location_id=location_id,
        combat_outcome_id=combat_outcome_id,
    )
    spec["faction_ids"] = sorted(set(faction_ids) & set(profile.get("faction_ids", ())))
    spec["include_rewards"] = reward_ceiling != "none"
    record = world["locations"][location_id]
    envelope = {
        "envelope_version": versions.ENVELOPE_VERSION,
        "campaign_id": campaign_id,
        "trigger_id": trigger_id,
        "trigger_kind": trigger_kind,
        "location_id": location_id,
        "parent_location_id": record.get("parent_location_id") if isinstance(record, dict) else None,
        "clock_bucket": spec["clock_bucket"],
        "profile_id": profile["profile_id"],
        "tier_ceiling": tier_ceiling,
        "reward_ceiling": reward_ceiling,
        "threat_band": profile.get("threat_band", "low"),
        "allowed_categories": sorted(profile["categories"]),
        "allowed_roles": sorted(profile["roles"]),
        "allowed_subscene_kinds": sorted(profile["subscene_kinds"]),
        "allowed_entity_ids": list(spec["entity_ids"]),
        "allowed_faction_ids": list(spec["faction_ids"]),
        "faction_rank_ceiling": profile.get("faction_rank_ceiling", "associate"),
        "allowed_creature_ids": sorted(profile.get("creature_ids", ())),
        "protected_names": sorted(profile.get("protected_names", ())),
        "hidden_context": copy.deepcopy(hidden_context or {}),
        "known_fact_ids": known_fact_ids(world, location_id),
        "decisions": copy.deepcopy(decisions),
        "expiry_seconds": list(profile.get("expiry_seconds", (1800, 21600))),
        "stamp_inputs": spec,
        "canon_stamp": compute_stamp(world, spec, lore_state),
    }
    size = len(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
    if size > MAX_ENVELOPE_BYTES:
        raise EnvelopeError("The envelope is too large.")
    return envelope


def is_stale(world, envelope, lore_state=None):
    return compute_stamp(world, envelope["stamp_inputs"], lore_state) != envelope["canon_stamp"]
