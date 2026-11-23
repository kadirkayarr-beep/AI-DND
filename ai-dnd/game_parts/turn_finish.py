import talk_mode
import interaction_adventure
import scheduled_events
import campaign_time
import copy
import game


def _tf_build_resolved_turn(*, action_result, allow_new_features, allow_new_locations, allow_new_npcs, allow_new_shops, expected_location_change, intent_source, lore_context, messages, narration, npc_target, quest_outcomes, quest_world_before, result, safety_handling, safety_reason_code, scene_plan, target_id, told_intent_calls):
    resolved = game.ResolvedTurn(
        action_result=action_result,
        fallback_response=narration,
        raw_result=result,
        requires_narration=True,
        safety_reason_code=safety_reason_code,
        safety_handling=safety_handling,
        quest_outcomes=quest_outcomes,
        npc_target=npc_target,
        target_id=target_id,
        lore_context=lore_context,
        intent_source=intent_source,
        intent_model_calls=told_intent_calls(),
        messages=messages,
        allow_new_npcs=allow_new_npcs,
        allow_new_features=allow_new_features,
        allow_new_locations=allow_new_locations,
        allow_new_shops=allow_new_shops,
        expected_location_change=expected_location_change,
        scene_plan=scene_plan,
        quest_world_before=quest_world_before,
    )
    return resolved


def _tf_system_deterministic_exit(*, _incident_before_skipped_narration, action_result, intent_source, result, safety_handling, safety_reason_code, system_deterministic, told_intent_calls):
    if system_deterministic:
        _incident_before_skipped_narration()
        result["_engine_event_evidence"].pop("_procedural_ids_before", None)
        narration_src = "deterministic_system"
        if safety_handling in ("python_memory_response", "python_memory_fallback"):
            narration_src = "python_memory_response"
        elif safety_reason_code:
            narration_src = "deterministic_fallback"

        result["_engine_event_evidence"]["telemetry"] = {
            "intent_model_calls": told_intent_calls(),
            "narration_model_calls": 0,
            "total_model_calls": told_intent_calls(),
            "intent_source": intent_source,
            "narration_source": narration_src,
            "fallback_reason": safety_reason_code,
            "narration_validation_result": safety_handling if safety_reason_code else "accepted",
            "resolved_action_type": action_result.get("action", "unknown") if isinstance(action_result, dict) else "unknown",
        }
        return result
    return game._TURN_FALL_THROUGH


def _tf_system_deterministic_flag(*, action, action_result, safety_handling, status, system_deterministic):
    if status in (
        "invalid_target", "limit_reached", "unsupported",
        "explicitly_declined", "unsupported_combat_action",
        "player_unconscious", "unverified", "clarification",
        "answered_from_npc_memory", "answered_from_campaign_state",
        "answered_from_loaded_lore",
    ):
        system_deterministic = True
    elif action in (
        "shop_economy",
        "shop_inquiry",
        "character_query",
        "death_save",
    ):
        system_deterministic = True
    elif action == "query" and action_result.get("direct_response"):
        system_deterministic = True
    elif status == "not_executed" and action_result.get("direct_response"):
        system_deterministic = True  # no blow ran, so no narrator gets to land one
    elif safety_handling in ("python_memory_response", "python_scene_response"):
        system_deterministic = True
    return system_deterministic


def _tf_engine_event_evidence(*, procedural_entity_ids, procedural_ids_before, quest_outcomes, result, turn_index):
    result["_engine_event_evidence"] = {
        "authority": "python_engine",
        "action_id": f"turn:{turn_index}",
        "turn_index": turn_index,
        "quest_outcomes": copy.deepcopy(quest_outcomes or []),
        "procedural_entity_ids": sorted(
            procedural_entity_ids() - procedural_ids_before
        ),
        "_procedural_ids_before": procedural_ids_before,
    }


def _tf_internal_text_fallback(*, action_result, narration, player_input):
    if game._is_internal_player_facing_text(narration):
        narration = game._natural_unresolved_action_response(
            player_input, action_result
        )
        if (
            isinstance(action_result, dict)
            and game._is_internal_player_facing_text(
                action_result.get("direct_response")
            )
        ):
            action_result["direct_response"] = narration
    return narration


def _tf_campaign_time(*, action_result, quest_world_before, world_state):
    if isinstance(action_result, dict) and "campaign_time" in world_state:
        previous_clock = quest_world_before.get("campaign_time", {})
        elapsed = world_state["campaign_time"]["elapsed_seconds"] - previous_clock.get(
            "elapsed_seconds", world_state["campaign_time"]["elapsed_seconds"]
        )
        action_result.setdefault("time_result", {
            "elapsed_seconds": max(0, elapsed),
            "after": campaign_time.public_time(world_state),
            "player_known_events": scheduled_events.public_events(world_state),
        })


def _tf_attack_events(*, action_result, entry_actor, entry_identity):
    if isinstance(action_result, dict) and action_result.get("action") in {"attack", "death_save"}:
        current = game.ensure_combat_state()
        identity = entry_identity or current.get("combat_id")
        if identity:
            action_result.setdefault("combat_id", identity)
            action_result.setdefault("actor", entry_actor if
                                     action_result.get("outcome") == "enemy_turn_resolved" else "player")
            action_result["combat_status"] = current["status"]
            action_result["round"] = current["round"]
            action_result["current_turn_index"] = current["current_turn_index"]
            action_result["current_actor_id"] = current["current_actor_id"]
            action_result["turn_owner"] = current["current_actor_id"]


def _tf_interaction_consumed(*, action_result, interaction_consumed, is_experimental, narration, player_input, quest_world_before, world_state):
    if (
        isinstance(action_result, dict)
        and action_result.get("status") != "awaiting_proposal"
        and not is_experimental
    ):
        interaction_adventure.consume(
            game._session(), action_result, quest_world_before, player_input
        )
        interaction_consumed = True
        if action_result.get("action") in {"query", "explore"}:
            beat = interaction_adventure.initiative_beat(world_state)
            if beat:
                action_result["npc_initiative"] = beat
                narration = narration + " " + beat["summary"]
    return interaction_consumed, narration


def _tf_is_experimental(*, action_result):
    is_experimental = (
        isinstance(action_result, dict)
        and (
            action_result.get("status") in {
                "experimental_attributed_speech",
                "unaccepted_experimental_action",
            }
            or action_result.get("experimental") is True
        )
    )
    return is_experimental


def _tf_first_guard(*, action_result, active_conversation_before, conversation_resolution, conversation_state_before, world_state):
    if (
        isinstance(action_result, dict)
        and action_result.get("status") == "proposal_rejected"
        and conversation_resolution is None
    ):
        world_state[interaction_adventure.KEY] = copy.deepcopy(
            conversation_state_before
        )
        talk_mode.restore(world_state, {key: value for key, value in active_conversation_before.items()
                                        if value is not None})


def _tf_final_skipped_exit(*, _incident_before_skipped_narration, action_result, intent_source, is_final, narration_model_calls, narration_source, procedural_entity_ids, procedural_ids_before, result, safety_handling, safety_reason_code, told_intent_calls):
    if is_final:
        _incident_before_skipped_narration()
        result["_engine_event_evidence"]["procedural_entity_ids"] = sorted(
            procedural_entity_ids() - procedural_ids_before
        )
        result["_engine_event_evidence"].pop("_procedural_ids_before", None)
        if "telemetry" not in result["_engine_event_evidence"]:
            result["_engine_event_evidence"]["telemetry"] = {
                "intent_model_calls": told_intent_calls(),
                "narration_model_calls": narration_model_calls,
                "total_model_calls": told_intent_calls() + narration_model_calls + getattr(game._session(), "_speech_repair_calls", 0),
                "intent_source": intent_source,
                "narration_source": narration_source,
                "fallback_reason": safety_reason_code,
                "narration_validation_result": safety_handling if safety_reason_code else "accepted",
                "resolved_action_type": action_result.get("action", "unknown") if isinstance(action_result, dict) else "unknown",
            }
        return result
    return game._TURN_FALL_THROUGH
