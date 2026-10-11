"""Lore-drift flags. The engine records a mismatch. It does not rewrite canon."""

from __future__ import annotations

from incidents import profiles


def flag(world, record, reason):
    """Append one audit-only flag. World canon is unchanged."""
    if not isinstance(reason, str) or not reason:
        return None
    flags = world.setdefault("lore_drift_flags", [])
    if not isinstance(flags, list):
        world["lore_drift_flags"] = []
        flags = world["lore_drift_flags"]
    entry = {
        "incident_id": record.get("incident_id") if isinstance(record, dict) else None,
        "reason": reason[:160],
    }
    flags.append(entry)
    del flags[:-32]
    return entry


def profile_conflict(world, location_id, claimed_profile_id):
    """A proposal cannot enlarge permissions by naming a book or city profile."""
    active = profiles.resolve(world, location_id)
    if active is None or active["profile_id"] != claimed_profile_id:
        return flag(world, {"incident_id": None}, "profile_conflict")
    return None
