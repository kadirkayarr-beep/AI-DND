import living_world
import interaction_adventure
import combat_lifecycle
import equipment_economy
from api.core_resolution import (
    resolution_action_scope,
)
import contextlib
import game


def _td_scene_plan_direct(*, action_id, combat_action, front, interaction_mode, messages, player_input, scene_plan, session_id, target_id):
    if (
        combat_action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not game._session().world_state.get("combat", {}).get("active")
        # Only when the scene planner already ran and had no answer of its own.
        and isinstance(scene_plan, dict)
        and scene_plan.get("direct_result") is None
    ):
        # LR00 fix, second pass: no older owner took the turn. A local act whose
        # target the words alone could not bind gets one bounded model call that
        # may only pick listed candidate IDs; otherwise the full pipeline runs.
        import grounded_action
        if not (front is not None and front["kind"] in {"talk_around", "look", "sit"}) and not game._scene_observation_proposal_turn(
            player_input, game._session().world_state, interaction_mode
        ):
            with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
                grounded = grounded_action.resolve_turn(
                    game._session(), player_input, interaction_mode=interaction_mode,
                    target_id=target_id, phase="fallback",
                )
            if grounded is not None:
                return game._spoken_rest_of_turn(grounded, player_input, messages, action_id, session_id)
    return game._TURN_FALL_THROUGH


def _td_parcel_board(*, combat_action, interaction_mode, player_input, read):
    if combat_action is None and interaction_mode not in {"say", "ask_dm"}:
        from adventure import dialogue_jobs
        parcel_read = dialogue_jobs.read_parcel(game._session(), player_input)
        if parcel_read is not None:
            return parcel_read
        import town_knowledge
        # A line the reading gave to a person is said to them, whatever board it mentions.
        board = None if (read or {}).get("kind") == "speak_to" else town_knowledge.board_turn(game._session(), player_input)
        if board is not None:
            return board
        import bound_text
        if (read or {}).get("kind") != "take":  # 'alıp okuyorum': the taking owns it and reads on
            looked_at = (getattr(game._session(), "_front_found", None) or ("", ""))[1] if (read or {}).get("kind") == "look" else ""
            paper_read = bound_text.take_reading_turn(game._session(), player_input, looked_at,
                                                      to_someone=(read or {}).get("kind") == "speak_to")
            if paper_read is not None:
                return paper_read
        import pocket
        pocketed = pocket.resolve(game._session(), player_input)
        if pocketed is not None:
            return pocketed
        if equipment_economy._natural_inventory_query(player_input) and not game._has_explicit_attack_verb(player_input):
            listed = equipment_economy.execute(game._session(), player_input)  # the bag answers for itself, whoever stands near
            if listed is not None:
                return listed
    return game._TURN_FALL_THROUGH


def _td_strike_fallen(*, combat_action, interaction_mode, player_input, target_id):
    if combat_action is None and interaction_mode not in {"say", "ask_dm"}:
        struck = combat_lifecycle.strike_the_fallen(game._session(), player_input, target_id)
        if struck:
            return {
                "messages": game._session().messages,
                "narration": struck,
                "model_calls": 0,
                "action_result": {"action": "narrative", "status": "resolved", "success": True,
                                  "state_changes": ["npcs"], "direct_response": struck},
            }
        question = combat_lifecycle.unbound_attack_reply(game._session(), player_input, target_id)
        if question:
            game._session()._attack_asked = True  # for this sitting only; never saved
            return {
                "messages": game._session().messages,
                "narration": question,
                "model_calls": 0,
                "action_result": {
                    "action": "attack", "status": "clarification", "success": False,
                    "outcome": "missing_target", "state_changes": [],
                    "direct_response": question,
                },
            }
    return game._TURN_FALL_THROUGH


def _td_fallen_address(*, combat_action, player_input, read):
    if combat_action is None:
        import fallen
        body = fallen.addressed_body(game._session(), player_input) if not combat_lifecycle.is_attack_decision(game._session(), player_input) else None
        if (body is not None and game._reads_as_address(player_input)
                and (read is None or read["kind"] == "speak_to" or (read["kind"] == "economic" and read.get("valid")))):  # a line read as an act is no word to them
            line = fallen.silence(body)
            return {
                "messages": game._session().messages, "narration": line, "model_calls": 0,
                "action_result": {"action": "narrative", "status": "body_silent", "success": True,
                                  "state_changes": [], "direct_response": line},
            }
    return game._TURN_FALL_THROUGH


def _td_end_conversation(*, combat_action, interaction_mode, player_input):
    if (
        combat_action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not game._session().world_state.get("combat", {}).get("active")
        and game._is_end_conversation_request(player_input)
    ):
        game.require_player_can_act()
        active = game._active_interlocutor()
        game._clear_active_interlocutor("ended")
        interaction_adventure.retire_conversation_focus(game._session().world_state)
        if active is None:
            narration = "Şu anda sürdürdüğün bir konuşma yok."
            status = "no_effect"
        else:
            narration = f"{living_world.public_npc_name(active)} ile konuşmayı bitiriyorsun."
            status = "conversation_ended"
        return {
            "messages": game._session().messages,
            "narration": narration,
            "model_calls": 0,
            "action_result": {
                "action": "dialogue",
                "status": status,
                "success": True,
                "npc_id": active.get("id") if isinstance(active, dict) else None,
                "state_changes": ["conversation"] if active is not None else [],
            },
        }
    return game._TURN_FALL_THROUGH


def _td_combat_mode(*, combat_action, interaction_mode, player_input, target_id):
    if combat_action is not None:
        interaction_mode = "do"
    elif interaction_mode in {"say", "ask_dm"}:
        if game._session().world_state.get("combat", {}).get("active"):
            raise combat_lifecycle.CombatRequestError(
                "unsupported_interaction_mode", "Use an action during active combat.", 400
            )
        game.require_player_can_act()
        if interaction_mode == "ask_dm":
            target_id = None
        elif target_id is not None and isinstance(player_input, str) and not player_input.lstrip().startswith("/"):
            # Said to someone, a line that names another person standing here is said to them; the talk turns to them.
            named = game._addressed_in(player_input, or_the_talk=False)
            if (isinstance(named, dict) and named.get("id") not in {None, target_id}
                    and named.get("id") in {npc.get("id") for npc in game._conversation_npcs()}
                    and game._line_addresses(player_input, named)):
                target_id = named["id"]
    return interaction_mode, target_id
