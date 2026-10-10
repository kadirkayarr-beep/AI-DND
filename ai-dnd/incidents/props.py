"""Promote ephemeral scene props through equipment economy or local features.

Prose on the incident is never inventory. Taking or placing is Python-only.
Promoted refs survive incident TTL.
"""

from __future__ import annotations

import equipment_economy
from incidents import commit


class PropError(ValueError):
    """The prop cannot leave the scene as described."""


def _prop(record, prop_id):
    prop = record["details"]["props"].get(prop_id)
    if prop is None:
        raise PropError("unknown_prop")
    return prop


def take(world, record, prop_id, *, catalog_id=None):
    """Move a scene prop into player inventory. Idempotent once taken."""
    prop = _prop(record, prop_id)
    if prop["state"] == "taken" and prop["promoted_ref"]:
        return next(
            (item for item in world.get("inventory", [])
             if isinstance(item, dict) and item.get("item_id") == prop["promoted_ref"]),
            {"item_id": prop["promoted_ref"], "name": prop["label"]},
        )
    if prop["state"] != "scene":
        raise PropError("not_on_scene")
    if catalog_id:
        item = equipment_economy.grant_catalog_item(world, catalog_id)
    else:
        item = equipment_economy.grant_named_item(world, prop["label"])
    prop["state"] = "taken"
    prop["promoted_ref"] = item["item_id"]
    if record["lifecycle"] == "PRESENT":
        commit.engage(world, record["incident_id"])
    return item


def place(world, record, prop_id, *, session=None):
    """Keep the prop in the world as a local feature. Idempotent once placed."""
    prop = _prop(record, prop_id)
    if prop["state"] == "placed" and prop["promoted_ref"]:
        return next(
            (feature for feature in world.get("features", [])
             if isinstance(feature, dict) and feature.get("id") == prop["promoted_ref"]),
            None,
        )
    if prop["state"] != "scene":
        raise PropError("not_on_scene")
    import game
    token = game._ACTIVE_SESSION.set(session) if session is not None else None
    try:
        feature = game.create_local_feature({
            "name": prop["label"],
            "description": prop["appearance"],
            "location": record["location_id"],
            "kind": "prop",
            "aliases": [prop["label"]],
        })
    finally:
        if token is not None:
            game._ACTIVE_SESSION.reset(token)
    if feature is None:
        raise PropError("feature_owner_refused")
    prop["state"] = "placed"
    prop["promoted_ref"] = feature["id"]
    if record["lifecycle"] == "PRESENT":
        commit.engage(world, record["incident_id"])
    return feature


def apply_action(world, action_result, *, session=None):
    if not isinstance(action_result, dict) or action_result.get("success") is not True:
        return None
    incident_id = action_result.get("incident_id")
    prop_id = action_result.get("prop_id")
    if not incident_id or not prop_id:
        return None
    record = world.get("incidents", {}).get(incident_id)
    if record is None:
        return None
    try:
        if action_result.get("action") in {"take", "pickup"}:
            return take(world, record, prop_id, catalog_id=action_result.get("catalog_id"))
        if action_result.get("action") in {"place", "leave"}:
            return place(world, record, prop_id, session=session)
    except (PropError, equipment_economy.EquipmentError):
        return None
    return None
