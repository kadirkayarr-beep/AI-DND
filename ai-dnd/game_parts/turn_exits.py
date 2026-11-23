import combat_lifecycle
import interaction_adventure
import living_world
import local_dialogue
import game


def _procedural_entity_ids(world_state):
    ids = {
        str(entity.get("id", location_id))
        for location_id, entity in world_state.get("locations", {}).items()
        if isinstance(entity, dict)
        and entity.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
    }
    ids.update(
        str(npc["id"])
        for npc in world_state.get("npcs", [])
        if isinstance(npc, dict)
        and npc.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(npc.get("id"), str)
    )
    ids.update(
        str(shop["id"])
        for raw_shop in world_state.get("shops", [])
        if (shop := living_world.public_shop_projection(world_state, raw_shop)) is not None
        and shop.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(shop.get("id"), str)
    )
    return ids


def _validate_interaction_conversation(player_input, world_state, raw, target, required):
    interaction = (
        raw.get("interaction") if isinstance(raw, dict) else None
    )
    # A quoted note is not speech to the NPC. A bad conversation reading
    # must not replace the turn with an in-character refusal.
    if combat_lifecycle.quoted_report(game._session(), player_input):
        if isinstance(interaction, dict):
            interaction["conversation"] = None
        return None, False
    proposal_present = (
        isinstance(interaction, dict)
        and interaction.get("conversation") is not None
    )
    if not proposal_present:
        return None, bool(required)
    resolution = interaction_adventure.resolve_conversation(
        world_state, player_input, interaction, target
    )
    if resolution is None and not required and target is None:
        # With nobody addressed, an optional and unresolvable conversation
        # reading is ignored, not a veto: the model's own top-level intent
        # (inspect, walk, read...) still decides the turn. With an
        # addressee it still rejects, so a malformed packet can never
        # create a commitment or memory.
        return None, False
    return resolution, resolution is None


def _finish_conversation_rejection(*, finish_turn, player_input, target):
    action_result = {
        "action": "dialogue",
        "status": "proposal_rejected",
        "success": False,
        "state_changes": [],
    }
    return finish_turn(
        action_result,
        interaction_adventure.immersive_unknown(target, player_input),
        safety_reason_code="INVALID_CONVERSATION_PROPOSAL",
        safety_handling="python_fallback",
        is_final=True,
    )


def _finish_conversation_resolution(*, action_id, finish_turn, player_input, resolution, target):
    if resolution is None:
        return None
    if resolution.get("answer_field"):
        field = resolution["answer_field"]
        value = resolution["answer_value"]
        name = living_world.public_npc_name(target)
        text = f'{name}, “{value.strip()}” diye yanıt verir.'
        action_result = {
            "action": "dialogue",
            "status": "answered_personal_question",
            "success": True,
            "npc_id": target["id"],
            "reality_category": local_dialogue.PROCEDURAL_PERSONAL_FACT,
            "state_changes": [],
        }
        game.record_npc_interaction(target, text, player_input, target)
        game._remember_accepted_profile_focus(
            player_input, target, action_id, field=field
        )
        return finish_turn(
            action_result, text, safety_handling="python_scene_response"
        )
    if resolution.get("meaning") in {
        "unknown", "unclear", "cause", "lore", "identity",
    }:
        action_result = {
            "action": "dialogue",
            "status": "conversation_unknown",
            "success": False,
            "state_changes": [],
        }
        return finish_turn(
            action_result,
            interaction_adventure.immersive_unknown(target, player_input),
            safety_reason_code="UNVERIFIED_CONVERSATION_RESOLUTION",
            safety_handling="python_fallback",
            is_final=True,
        )
    return None
