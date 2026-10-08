"""Promote incident passersby through the living-world NPC owner.

Passersby live only on the incident. A real interaction writes one NPC row
via ``create_npc_from_ai``. Canon names are rejected. Promoted ids survive TTL.
"""

from __future__ import annotations

from incidents import commit

PROTECTED_LAYERS = frozenset({"CANONICAL_SOURCE", "OFFICIAL_SETTING_CANON"})
PROTECTED_ENTITY_TYPES = frozenset({
    "CANONICAL_NPC", "DEITY", "RELIGION_CHURCH", "FACTION",
    "CITY", "DISTRICT", "KINGDOM_NATION",
})


class PromotionError(ValueError):
    """The passerby cannot become an NPC row."""


def _registry():
    try:
        from api.lore_authority import PRODUCTION_REGISTRY
        from api.lore_authority.models import EntityType
    except Exception:
        return None, None
    return PRODUCTION_REGISTRY, EntityType


def _canon_name(name):
    if not isinstance(name, str) or not name.strip():
        return False
    folded = name.casefold()
    if "neverember" in folded:
        return True
    registry, entity_type = _registry()
    if registry is None:
        return False
    for entity_id in registry.resolve_entity(name).entity_ids:
        entity = registry.entity(entity_id)
        if entity is None:
            continue
        value = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)
        if value in PROTECTED_ENTITY_TYPES:
            return True
        if entity_type is not None and entity.entity_type in {
            entity_type.CANONICAL_NPC, entity_type.DEITY,
        }:
            return True
    return False


def _existing_named(world, name, location_id):
    folded = name.casefold()
    for npc in world.get("npcs", []):
        if not isinstance(npc, dict):
            continue
        if npc.get("name", "").casefold() != folded:
            continue
        if npc.get("reality_layer") in PROTECTED_LAYERS:
            return npc, True
        if npc.get("location") == location_id:
            return npc, False
    return None, False


def _bind(session):
    import game
    if session is None:
        return None
    return game._ACTIVE_SESSION.set(session)


def promote(world, record, person_id, *, session=None):
    """Turn one passerby into a living-world NPC. Idempotent on the person row."""
    person = record["details"]["people"].get(person_id)
    if person is None:
        raise PromotionError("unknown_person")
    if person["state"] == "promoted" and person["npc_id"]:
        for npc in world.get("npcs", []):
            if isinstance(npc, dict) and npc.get("id") == person["npc_id"]:
                return npc
        raise PromotionError("missing_npc")

    import game
    import living_world
    token = _bind(session)

    location_id = record["location_id"]
    wanted = person["name"]
    if not wanted or _canon_name(wanted):
        wanted = living_world.stable_local_name(world, location_id, person["role"] or "Yolcu")
    existing, protected = _existing_named(world, wanted, location_id)
    if protected:
        wanted = living_world.stable_local_name(world, location_id, person["role"] or "Yolcu")
        existing = None
    if existing is not None and existing.get("id") != person.get("npc_id"):
        if existing.get("role", "").casefold() == person["role"].casefold():
            wanted = living_world.stable_local_name(world, location_id, person["role"] or "Yolcu")

    try:
        npc = game.create_npc_from_ai({
            "name": wanted,
            "role": person["role"],
            "location": location_id,
            "appearance": person["label"],
            "personality": ", ".join(person["traits"]),
            "relationship": "neutral",
            "backstory": person["backstory"] or "",
        })
    finally:
        if token is not None:
            game._ACTIVE_SESSION.reset(token)
    if npc is None:
        raise PromotionError("npc_owner_refused")
    person["state"] = "promoted"
    person["npc_id"] = npc["id"]
    person["name"] = npc["name"]
    if record["lifecycle"] == "PRESENT":
        commit.engage(world, record["incident_id"])
    return npc


def apply_action(world, action_result, *, session=None):
    if not isinstance(action_result, dict) or action_result.get("success") is not True:
        return None
    incident_id = action_result.get("incident_id")
    person_id = action_result.get("person_id")
    if not incident_id or not person_id:
        return None
    if action_result.get("action") not in {"dialogue", "interaction", "talk"}:
        return None
    record = world.get("incidents", {}).get(incident_id)
    if record is None:
        return None
    try:
        return promote(world, record, person_id, session=session)
    except PromotionError:
        return None
