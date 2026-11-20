import game
import campaign_time
import interaction_adventure
import json
import living_world


def ensure_campaign_clock():
    """Initialize only after Python has a registered current world scene."""
    world = game._session().world_state
    if world.get("location") in world.get("locations", {}):
        return campaign_time.initialize(world)
    return None

def _living_world_prompt_context(scene_plan=None, npc_target=None, player_input=None):
    world_state = game._session().world_state
    location_id = world_state.get("location")
    if location_id not in world_state.get("locations", {}):
        return ""
    turn_index = world_state.get("flags", {}).get("turn_index", 0)
    scene = living_world.ensure_scene_record(
        world_state, location_id, turn_index
    )
    state = living_world.ensure_scene_state(world_state)
    references = [
        {
            "id": item.get("id"),
            "lifecycle": item.get("lifecycle"),
            "description": item.get("description"),
        }
        for item in scene.get("referents", [])
        if isinstance(item, dict)
        and item.get("lifecycle") == "presented"
    ]
    conversation_focus = (
        interaction_adventure.current_conversation_focus(
            world_state, npc_target
        )
        if isinstance(npc_target, dict)
        else None
    )
    accepted_profile = None
    content = {
        "where_now": living_world.place_in_plain_words(world_state),
        "location_id": location_id,
        "location_name": game.location_display_name(location_id),
        "lore_anchor_id": (
            scene_plan.get("lore_location_id")
            if isinstance(scene_plan, dict)
            else living_world.location_anchor_id(world_state, location_id)
        ),
        "revision": scene.get("revision", 0),
        "player_position": state.get("player_position", {}),
        "active_npc_target": (
            {
                "id": npc_target.get("id"),
                "name": living_world.public_npc_name(npc_target),
                "role": living_world.public_npc_role(npc_target),
            }
            if isinstance(npc_target, dict)
            else None
        ),
        "conversation_focus": conversation_focus,
        "accepted_npc_profile": accepted_profile,
        "visible_npcs": [
            {
                "id": npc.get("id"),
                "name": living_world.public_npc_name(npc),
                "role": living_world.public_npc_role(npc),
            }
            for npc in game._scene_names(location_id)[:6]
        ],
        "features": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "kind": item.get("kind"),
                "description": item.get("description"),
                "aliases": item.get("aliases", []),
            }
            for item in living_world.visible_features(world_state, location_id)[:16]
            if isinstance(item, dict)
        ],
        "background_referents": references[:4],
        "recent_beat": scene.get("last_beat"),
    }
    if scene.get("last_beat"):
        content["recent_beat_actors"] = (
            "recent_beat içindekiler adsız yabancılar; bu olayı visible_npcs listesindeki kimseye yükleme."
        )
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))

def _observe_anchored_structure(player_input, interaction_mode=None):
    """Report a known building from stored records. Do not invent a part."""
    if not living_world.affirmative_structure_inspection(
        player_input, interaction_mode
    ):
        return None
    world_state = game._session().world_state
    current = world_state.get("location")
    current_location = world_state.get("locations", {}).get(current)
    if (
        isinstance(current_location, dict)
        and current_location.get("scene_kind") == "tavern"
        and isinstance(current_location.get("parent_location_id"), str)
    ):
        tavern = current_location
        feature_location = current_location["parent_location_id"]
    else:
        tavern = game._resolve_explicit_local_scene_parent(current, player_input)
        feature_location = current
    if not isinstance(tavern, dict):
        if living_world.affirmative_structure_inspection(
            player_input, interaction_mode
        ):
            return None
        return {
            "action": "inspect",
            "status": "not_detailed",
            "success": True,
            "state_changes": [],
            "direct_response": "Yakında inceleyebileceğin belirgin bir bina görünmüyor.",
        }
    visible, hidden = game._anchored_structure_features(
        player_input, feature_location, tavern.get("id")
    )
    if len(visible) == 1:
        feature = visible[0]
        return {
            "action": "inspect",
            "status": "observed",
            "success": True,
            "target_id": feature.get("id"),
            "state_changes": [],
            "direct_response": (
                f"{feature.get('name', 'Bu ayrıntı')}: "
                f"{feature.get('description', 'belirgin bir değişiklik yok.')}"
            ),
        }
    if len(visible) > 1:
        return {
            "action": "inspect",
            "status": "clarification",
            "success": False,
            "target_id": tavern.get("id"),
            "state_changes": [],
            "direct_response": "Hangi parçayı incelemek istediğini belirtir misin?",
        }
    if hidden:
        return {
            "action": "inspect",
            "status": "not_visible",
            "success": False,
            "target_id": tavern.get("id"),
            "state_changes": [],
            "direct_response": "Bu bakış görünür bir parça seçmiyor.",
        }
    if game._scene_detail_proposals_allowed(player_input, world_state, interaction_mode):
        return None
    door = game._venue_door_for(tavern.get("id"))
    sentences = [f"{tavern.get('name', 'Bina')} binasına bakıyorsun."]
    if isinstance(door, dict) and door.get("hidden") is not True:
        sentences.append(game._tavern_door_notice(tavern["id"]))
        sentences.append("Bu bakışın seçtiği diğer parça henüz ayrıntılandırılmamış.")
    else:
        sentences.append("Bu bakışın seçtiği parça henüz ayrıntılandırılmamış.")
    return {
        "action": "inspect",
        "status": "not_detailed",
        "success": True,
        "target_id": tavern.get("id"),
        "state_changes": [],
        "direct_response": " ".join(sentences),
    }

def resolve_scene_seating(action_input):
    """Seat the player at one visible seat here, or say why that is not possible.

    Single owner of the sit decision for the direct scene action and for the
    compound grounded action. Hidden or undiscovered features are not
    candidates (``living_world.visible_features`` is the visibility owner) and
    their names are never disclosed.
    """
    world_state = game._session().world_state
    current = world_state.get("location")
    visible = living_world.visible_features(world_state, current)
    visible_ids = {feature.get("id") for feature in visible}
    features = [
        feature for feature in game._scene_feature_match(action_input, current)
        if feature.get("id") in visible_ids
    ]
    seats = [
        feature for feature in visible
        if feature.get("kind") in ("furnishing", "seat", "table", "bench")
    ]
    target = features[0] if len(features) == 1 else (seats[0] if seats else None)
    if len(features) > 1:
        return {
            "action": "sit",
            "status": "clarification",
            "success": False,
            "state_changes": [],
            "direct_response": "Birden fazla uygun yer var; hangi masaya oturmak istediğini belirtir misin?",
        }
    if target:
        living_world.set_player_position(world_state, current, "seated", target.get("id"))
        target_name = str(target.get("name") or "seçtiğin yer").strip()
        return {
            "action": "sit",
            "status": "completed",
            "success": True,
            "target_id": target.get("id"),
            "target_name": target.get("name"),
            "state_changes": [],
            "direct_response": (
                f"“{target_name}” yakınında uygun bir yere oturup "
                "yerleşiyorsun."
            ),
        }
    return {
        "action": "sit",
        "status": "unresolved",
        "success": False,
        "state_changes": [],
        "direct_response": "Oturabileceğin uygun bir yer göremiyorsun.",
    }
