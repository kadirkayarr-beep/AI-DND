"""Settlement and scene profiles for the Reality Envelope.

A location without a reviewed profile generates nothing. Missing review is
not permission to invent. Waterdeep and Baldur's Gate stay off until the
owner signs their review files.
"""

from __future__ import annotations

from incidents.models import REWARD_CLASSES

_VERIFIED = frozenset({"VERIFIED", "VERIFIED_PARTIAL", "APPROVED"})
NEVERWINTER_PACK = "fr:pack:the_north:neverwinter:v1"
DISABLED = frozenset({"waterdeep.v1", "baldurs_gate.v1"})

_GENERIC_ROLES = ("cook", "merchant", "traveler", "guard", "laborer", "sailor", "hunter")
_GENERIC_KINDS = ("alley", "back_room", "cellar", "campsite", "dock_corner", "shed", "clearing")
_GENERIC_CATEGORIES = ("disturbance", "lost_property", "social", "urban_theft")
LIVE_FLAG = "emergence_live"


def _base(**overrides):
    profile = {
        "profile_id": "generic.tavern",
        "pack_id": None,
        "requires_review": False,
        "enabled": True,
        "tier_ceiling": 2,
        "threat_band": "low",
        "silence_rate": 0.65,
        "categories": list(_GENERIC_CATEGORIES),
        "category_weights": (("disturbance", 4), ("lost_property", 3), ("social", 2), ("urban_theft", 1)),
        "reward_weights": (("none", 8), ("trinket", 2), ("coin_small", 1)),
        "roles": list(_GENERIC_ROLES),
        "subscene_kinds": list(_GENERIC_KINDS),
        "faction_ids": (),
        "faction_rank_ceiling": "associate",
        "creature_ids": (),
        "home_settlement_ids": (),
        "protected_names": ("Dagult Neverember",),
        "expiry_seconds": (1800, 21600),
        "review_status": "GENERIC",
    }
    profile.update(overrides)
    return profile


PROFILES = {
    "neverwinter.v1": _base(
        profile_id="neverwinter.v1",
        pack_id=NEVERWINTER_PACK,
        requires_review=True,
        tier_ceiling=3,
        silence_rate=0.55,
        faction_ids=("fr:faction:lords_alliance",),
        faction_rank_ceiling="member",
        home_settlement_ids=("fr:city:neverwinter",),
        protected_names=("Dagult Neverember",),
        review_status="PENDING",
    ),
    "generic.tavern": _base(profile_id="generic.tavern", silence_rate=0.7),
    "generic.wilderness": _base(
        profile_id="generic.wilderness",
        categories=("disturbance", "wilderness", "travel"),
        category_weights=(("disturbance", 3), ("wilderness", 3), ("travel", 2)),
        roles=("hunter", "traveler", "laborer"),
        subscene_kinds=("campsite", "clearing", "shed"),
        silence_rate=0.6,
    ),
    "generic.road": _base(
        profile_id="generic.road",
        categories=("disturbance", "travel", "lost_property"),
        category_weights=(("travel", 3), ("disturbance", 2), ("lost_property", 2)),
        roles=("traveler", "merchant", "guard"),
        subscene_kinds=("campsite", "clearing"),
        silence_rate=0.6,
    ),
    "generic.camp": _base(
        profile_id="generic.camp",
        categories=("disturbance", "wilderness"),
        category_weights=(("disturbance", 3), ("wilderness", 2)),
        roles=("hunter", "traveler"),
        subscene_kinds=("campsite", "clearing"),
        silence_rate=0.55,
    ),
    "waterdeep.v1": _base(
        profile_id="waterdeep.v1", pack_id="fr:pack:waterdeep:v1",
        requires_review=True, enabled=False, review_status="UNREVIEWED",
    ),
    "baldurs_gate.v1": _base(
        profile_id="baldurs_gate.v1", pack_id="fr:pack:baldurs_gate:v1",
        requires_review=True, enabled=False, review_status="UNREVIEWED",
    ),
}


def _pack_coverage(pack_id):
    if not pack_id:
        return None
    try:
        from api.lore_authority.pack_loader import load_pack_index
    except Exception:
        return None
    for entry in load_pack_index():
        if entry.get("pack_id") == pack_id:
            return entry.get("coverage_status")
    return None


def generation_enabled(world):
    """Live Qwen proposals stay off until the campaign flag is set."""
    flags = world.get("flags") if isinstance(world, dict) else None
    return isinstance(flags, dict) and flags.get(LIVE_FLAG) is True


def _pack_entities():
    try:
        from api.lore_authority.pack_loader import REVIEWED_PACK
        from api.lore_authority.models import EntityType
    except Exception:
        return (), None
    return REVIEWED_PACK.entities, EntityType


def _names_from_pack(home_ids):
    """Canonical NPC, deity, and foreign-city names from the reviewed pack."""
    names = ["Dagult Neverember"]
    entities, entity_type = _pack_entities()
    if entity_type is None:
        return tuple(names)
    home = set(home_ids)
    for entity in entities:
        kind = entity.entity_type
        if kind in {entity_type.CANONICAL_NPC, entity_type.DEITY}:
            if entity.canonical_name not in names:
                names.append(entity.canonical_name)
        elif kind in {entity_type.CITY, entity_type.DISTRICT} and entity.entity_id not in home:
            if entity.canonical_name not in names:
                names.append(entity.canonical_name)
    return tuple(names)


def load(profile_id):
    """Return a copy of an enabled, reviewed profile, or None."""
    spec = PROFILES.get(profile_id)
    if spec is None or profile_id in DISABLED or not spec.get("enabled", True):
        return None
    if spec["requires_review"]:
        coverage = _pack_coverage(spec["pack_id"])
        if coverage not in _VERIFIED:
            return None
    loaded = dict(spec)
    loaded["protected_names"] = _names_from_pack(spec.get("home_settlement_ids", ()))
    loaded["review_status"] = _pack_coverage(spec["pack_id"]) or spec["review_status"]
    if loaded["reward_weights"]:
        for label, _weight in loaded["reward_weights"]:
            if label not in REWARD_CLASSES:
                return None
    return loaded


def resolve(world, location_id):
    """Return the active profile for ``location_id`` or None."""
    if location_id in {"waterdeep", "fr:city:waterdeep", "baldurs_gate", "fr:city:baldurs_gate"}:
        return None
    record = world.get("locations", {}).get(location_id, {})
    parent = record.get("parent_location_id") if isinstance(record, dict) else None
    settlement = record.get("settlement_id") if isinstance(record, dict) else None
    if location_id in {"neverwinter", "fr:city:neverwinter"} or parent in {
        "neverwinter", "fr:city:neverwinter",
    } or settlement in {"neverwinter", "fr:city:neverwinter"}:
        return load("neverwinter.v1")
    kind = record.get("scene_kind") if isinstance(record, dict) else None
    loc_type = record.get("type") if isinstance(record, dict) else None
    if location_id == "tavern" or kind in {"tavern", "inn"} or loc_type in {"tavern", "inn"}:
        return load("neverwinter.v1") or load("generic.tavern")
    if location_id == "forest" or kind in {"wilderness", "forest"} or loc_type in {"wilderness", "forest"}:
        return load("generic.wilderness")
    if kind in {"road", "route"} or loc_type == "road":
        return load("generic.road")
    if kind == "camp":
        return load("generic.camp")
    return None
