import talk_mode
import interaction_adventure
import scheduled_events
import campaign_time
import copy
import incidents.hooks as incident_hooks
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


def _finish_turn(*, action_result, narration, quest_outcomes, safety_reason_code, safety_handling, record_safety, is_final, active_conversation_before, allow_new_features, allow_new_locations, allow_new_npcs, allow_new_shops, conversation_resolution, conversation_state_before, entry_actor, entry_identity, expected_location_change, intent_source, lore_context, messages, narration_model_calls, narration_source, npc_target, player_input, procedural_entity_ids, procedural_ids_before, quest_world_before, scene_plan, target_id, told_intent_calls, turn_index, world_state):
    interaction_adventure.get(world_state)
    if narration is None and isinstance(action_result, dict):
        # A recorded goal carries no sentence of its own: the narrator tells it, and this line stands only if it cannot.
        narration = game._natural_unresolved_action_response(player_input, action_result)
        is_final = False
    game._tf_first_guard(action_result=action_result, active_conversation_before=active_conversation_before, conversation_resolution=conversation_resolution, conversation_state_before=conversation_state_before, world_state=world_state)
    is_experimental = game._tf_is_experimental(action_result=action_result)
    interaction_consumed = is_experimental
    interaction_consumed, narration = game._tf_interaction_consumed(action_result=action_result, interaction_consumed=interaction_consumed, is_experimental=is_experimental, narration=narration, player_input=player_input, quest_world_before=quest_world_before, world_state=world_state)
    game._tf_attack_events(action_result=action_result, entry_actor=entry_actor, entry_identity=entry_identity)
    game._tf_campaign_time(action_result=action_result, quest_world_before=quest_world_before, world_state=world_state)
    narration = game._tf_internal_text_fallback(action_result=action_result, narration=narration, player_input=player_input)
    if record_safety:
        game._record_narration_safety(
            {
                "reason_code": safety_reason_code,
                "trigger_span": None,
                "scene_type": game._narration_scene_type(action_result),
            },
            safety_handling,
        )
    if (
        isinstance(conversation_resolution, dict)
        and conversation_resolution.get("topic_relation") == "topic_change"
        and not conversation_resolution.get("answer_field")
        and isinstance(action_result, dict)
        and not is_experimental
    ):
        interaction_adventure.retire_conversation_focus(world_state)
    if (
        isinstance(action_result, dict)
        and isinstance(npc_target, dict)
        and isinstance(npc_target.get("id"), str)
        and action_result.get("action") != "character_query"
    ):
        action_result.setdefault("npc_id", npc_target["id"])
    if isinstance(action_result, dict) and isinstance(scene_plan, dict):
        action_result["state_changes"] = list(dict.fromkeys(
            list(action_result.get("state_changes", []))
            + list(scene_plan.get("state_changes", []))
        ))
    result = {"action_result": action_result, "narration": narration,
              "_interaction_consumed": interaction_consumed}
    game._tf_engine_event_evidence(procedural_entity_ids=procedural_entity_ids, procedural_ids_before=procedural_ids_before, quest_outcomes=quest_outcomes, result=result, turn_index=turn_index)

    def _incident_before_skipped_narration():
        # Look, rest, and a completed move can be answered without a narrator.
        # The incident owner still sees that authoritative action. A later
        # narrated turn uses the existing door in _narrate_resolved_turn.
        if not isinstance(action_result, dict):
            return
        emergence = incident_hooks.before_narration(
            game._session(),
            action_result=action_result,
            player_text=player_input,
            location_changed=world_state.get("location") != quest_world_before.get("location"),
        )
        spent = emergence.get("model_calls") if isinstance(emergence, dict) else 0
        if type(spent) is int and spent > 0:
            nonlocal narration_model_calls
            narration_model_calls += spent

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

    status = action_result.get("status") if isinstance(action_result, dict) else None
    action = action_result.get("action") if isinstance(action_result, dict) else None

    system_deterministic = False
    system_deterministic = game._tf_system_deterministic_flag(action=action, action_result=action_result, safety_handling=safety_handling, status=status, system_deterministic=system_deterministic)

    _exit = game._tf_system_deterministic_exit(_incident_before_skipped_narration=_incident_before_skipped_narration, action_result=action_result, intent_source=intent_source, result=result, safety_handling=safety_handling, safety_reason_code=safety_reason_code, system_deterministic=system_deterministic, told_intent_calls=told_intent_calls)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    resolved = game._tf_build_resolved_turn(action_result=action_result, allow_new_features=allow_new_features, allow_new_locations=allow_new_locations, allow_new_npcs=allow_new_npcs, allow_new_shops=allow_new_shops, expected_location_change=expected_location_change, intent_source=intent_source, lore_context=lore_context, messages=messages, narration=narration, npc_target=npc_target, quest_outcomes=quest_outcomes, quest_world_before=quest_world_before, result=result, safety_handling=safety_handling, safety_reason_code=safety_reason_code, scene_plan=scene_plan, target_id=target_id, told_intent_calls=told_intent_calls)
    raise game.TurnResolved(result, resolved)
