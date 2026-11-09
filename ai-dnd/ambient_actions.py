"""One rule says whether the scene's ambient event can be joined (Dilim 3, Task 8).

`actionable` is that rule: the scene view (`living_world.public_scene_projection`) shows it and the click route
(`resolve`, behind `GameSession.resolve_ambient_event_action`) obeys it, so the panel never offers a click the engine
refuses. A refusal is the rule's reason; the HTTP route puts its Turkish line (`refusals.text_for`) on the answer.
"""
from __future__ import annotations

from typing import Any

import living_world


def _scene_event(world: dict[str, Any]) -> tuple[dict | None, dict | None, dict | None]:
    """The scene the player stands in, its ambient event and the event's referent (None where missing)."""
    scene_state = world.get("scene_state")
    scenes = scene_state.get("scenes") if isinstance(scene_state, dict) else None
    scene = scenes.get(world.get("location")) if isinstance(scenes, dict) else None
    event = scene.get("ambient_event") if isinstance(scene, dict) else None
    if not isinstance(event, dict):
        return scene, None, None
    referents = scene.get("referents")
    referent = next(
        (
            item for item in referents
            if isinstance(item, dict)
            and item.get("id") == event.get("referent_id")
            and item.get("event_instance_id") == event.get("instance_id")
        ),
        None,
    ) if isinstance(referents, list) else None
    return scene, event, referent


def actionable(world: dict[str, Any], current_hp: Any = None) -> dict[str, Any]:
    """Whether the engine would take a click on the scene's event right now, and if not, why (the first reason)."""
    _, event, referent = _scene_event(world)
    instance_id = event.get("instance_id") if isinstance(event, dict) else None
    result = {"event_instance_id": instance_id if isinstance(instance_id, str) else None,
              "can_interact": False, "reason": None}
    flags = world.get("flags")
    turn_index = flags.get("turn_index") if isinstance(flags, dict) else None
    combat = world.get("combat")
    if event is None:
        result["reason"] = "no_event"
    elif event.get("event_type") != "BLUE":
        result["reason"] = "event_not_interactive"
    elif referent is None:
        result["reason"] = "event_referent_missing"
    elif referent.get("lifecycle") == "promoted":
        result["reason"] = "event_already_resolved"
    elif (
        referent.get("lifecycle") != "presented"
        or type(turn_index) is not int
        or type(referent.get("expires_after_turn")) is not int
        or turn_index > referent["expires_after_turn"]
    ):
        result["reason"] = "event_expired"
    elif isinstance(combat, dict) and combat.get("active"):
        result["reason"] = "combat"
    elif (
        (type(current_hp) is int and current_hp <= 0)
        or world.get("player_combat_status") in ("unconscious", "dead")
    ):
        result["reason"] = "player_down"
    else:
        result["can_interact"] = True
    return result


def resolve(session: Any, event_instance_id: str, action_id: str, action: str) -> dict[str, Any]:
    """Resolve a click on the scene's event: the contract of `GameSession.resolve_ambient_event_action`."""
    session.require_player_can_act()
    result = {
        "event_instance_id": event_instance_id,
        "action_id": action_id,
        "status": "REJECTED",
        "reason_code": "event_unavailable",
        "transition_id": None,
    }
    world = session.world_state
    _, event, referent = _scene_event(world)
    if isinstance(event, dict) and event.get("instance_id") != event_instance_id:
        result["reason_code"] = "event_not_interactive"   # the scene holds another event now
        return result
    rule = actionable(world, session.character.get("current_hp"))
    if rule["reason"] == "event_already_resolved":
        promoted_npc_id = referent.get("promoted_npc_id")
        if isinstance(promoted_npc_id, str) and any(
            isinstance(item, dict) and item.get("id") == promoted_npc_id for item in world.get("npcs", [])
        ):
            result.update(status="ALREADY_APPLIED", reason_code="event_already_resolved",
                          transition_id=promoted_npc_id)
        else:
            result["reason_code"] = "promoted_npc_missing"
        return result
    if not rule["can_interact"]:
        result["reason_code"] = rule["reason"]
        return result
    if action == "observe":
        result.update(status="NO_EFFECT", reason_code="observation_only")
        return result
    if action != "interact":
        result["reason_code"] = "unsupported_action"
        return result

    location_id = world.get("location")
    turn_index = world["flags"]["turn_index"]
    npc = session._promote_scene_referent(referent, location_id)
    if not isinstance(npc, dict) or not isinstance(npc.get("id"), str):
        result["reason_code"] = "promotion_unavailable"
        return result
    session._set_scene_active_npc(npc, turn_index)
    if (
        referent.get("lifecycle") != "promoted"
        or referent.get("promoted_npc_id") != npc["id"]
        or not any(isinstance(item, dict) and item.get("id") == npc["id"] for item in world.get("npcs", []))
    ):
        raise ValueError("Ambient event promotion did not reach canonical state.")
    result.update(status="APPLIED", reason_code="referent_promoted", transition_id=npc["id"])
    # The click is a move in the story: it is told and kept like any turn.
    event_text = str(referent.get("description") or "").strip()
    result["player_message"] = "Yanlarına gidiyorum."
    result["narration"] = (
        f"{event_text} Yanlarına gidiyorsun; karşında {living_world.public_npc_name(npc)} var."
    ).strip()
    session.messages.extend([
        {"role": "user", "content": result["player_message"]},
        {"role": "assistant", "content": result["narration"]},
    ])
    return result
