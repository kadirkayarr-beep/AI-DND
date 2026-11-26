import initiative
import adventure.play as adventure_play
import action_economy
import living_world
import interaction_adventure
import combat_lifecycle
import equipment_economy
from core_resolution import (
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


def _dpt_validate_combat_request(*, player_input, target_id):
    try:
        combat_lifecycle.validate_request(game._session(), player_input, target_id)
    except combat_lifecycle.CombatRequestError as error:
        if error.code != "combat_travel":
            raise
        # held for the turn's reading: a walk toward someone in the fight is combat movement (_approach_turn takes it);
        # any other reading of the line is refused as walking off, as before
        game._session()._walk_off = error


def _dpt_surrendered_spell_question(*, action_id, player_input, session_id, spell_command, target_id):
    if spell_command is not None:
        surrender_question = combat_lifecycle.surrendered_strike_question(
            game._session(), player_input, target_id, spell_command)  # a harmful spell is asked like a blow (D-036)
        if surrender_question is not None:
            return surrender_question
        return action_economy.execute(game._session(), spell_command, action_id, session_id)
    return game._TURN_FALL_THROUGH


def _dpt_native_exploration_command(*, action_id, combat_action, exploration, player_input, session_id):
    if (combat_action is None and game._session().character.get("current_hp", 0) > 0
            and exploration.native_request(player_input, game._session())):
        with resolution_action_scope(action_id, session_id):
            exploration_result = exploration.resolve_command(game._session(), player_input)
        if exploration_result is not None:
            return exploration_result
    return game._TURN_FALL_THROUGH


def _dpt_out_of_combat_commands(*, action_id, combat_action, front, interaction_mode, messages, player_input, session_id, target_id):
    if (
        combat_action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not game._session().world_state.get("combat", {}).get("active")
    ):
        hideout = adventure_play.resolve_dungeon_turn(game._session(), player_input, game._hideout_check)
        if hideout is not None:
            return hideout
        # Read as talk, a look or sitting down: the words of a line walk nowhere. The route log shows these lost all traffic.
        talk = front is not None and front["kind"] in {"talk_around", "look", "sit"}
        # D-123: the quest shortcut's rolls (a check, the road's Survival) belong to this turn like any journey's.
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            scene = None if talk else game._adventure_scene_turn(player_input)
        if scene is not None:
            return scene
        # LR00 fix: read a local physical action once, bind it to a real target
        # and let its owner resolve it (grounded_action). None = older owners.
        import grounded_action
        if not talk and not game._scene_observation_proposal_turn(
            player_input, game._session().world_state, interaction_mode
        ) and not (
            living_world.is_anchored_structure_inquiry(player_input)
            and living_world.affirmative_structure_inspection(
                player_input, interaction_mode
            )
        ):
            with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
                grounded = grounded_action.resolve_turn(
                    game._session(), player_input, interaction_mode=interaction_mode, target_id=target_id,
                )
            if grounded is not None:
                return game._spoken_rest_of_turn(grounded, player_input, messages, action_id, session_id)
        local_place = None if talk else game._local_place_turn(player_input)
        if local_place is not None:
            return local_place
        # BM Task 8: a reading that named something (a place, a person, a thing) belongs to that owner; the everyday
        # words run only when there was no reading, or it said unclear / attempt.
        everyday = (game._everyday_action_turn(player_input)
                    if front is None or front["kind"] in {"unclear", "attempt"} else None)
        if everyday is not None:
            return everyday
    return game._TURN_FALL_THROUGH


def _dpt_free_dialogue(*, action_id, combat_action, interaction_mode, player_input, session_id, target_id):
    if combat_action is None:
        import dialogue_runtime
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            free_dialogue = dialogue_runtime.resolve_turn(
                game._session(), player_input, interaction_mode=interaction_mode,
                target_id=target_id, action_id=action_id,
            )
        if free_dialogue is not None:
            return free_dialogue
    return game._TURN_FALL_THROUGH


def _dpt_bag_read(*, player_input, read):
    # D-095: "muhafızın kesesi var mı diye inceliyorum" is about someone else's purse; never answer with the player's
    if read is not None and read["kind"] == "bag" and not game._SOMEONE_ELSES_PURSE.search(
            game._normalize_turkish_typos(living_world._text_outside_quotes(player_input))):
        listed = equipment_economy.execute(game._session(), "çantamda ne var")
        if listed is not None:

            return listed
    return game._TURN_FALL_THROUGH


def _dpt_narrative_spell(*, action_id, check_evidence, check_feature, combat_action, interaction_mode, messages, player_input, scene_plan, session_id, spell_effects, target_id):
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"}
            and not getattr(game._session(), "_front_strike", None) and spell_effects.named(player_input) is not None):
        # 4C.5: a narrative spell (or one not in the engine yet) is the spell owner's, never a walk, a knock or an item
        # move; the engine answers it inside the turn and the narrator tells the fact.
        return game._dispatch_turn_body(player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                                   session_id, check_feature, check_evidence)
    return game._TURN_FALL_THROUGH


def _dpt_owner_reply(*, owner_reply):
    if owner_reply is not None:
        return {
            "messages": game._session().messages,
            "narration": owner_reply.get("direct_response") or "",
            "model_calls": 0,
            "action_result": owner_reply,
        }
    return game._TURN_FALL_THROUGH


def _dpt_run_in_action_scope(*, action_id, check_evidence, check_feature, interaction_mode, messages, player_input, scene_plan, session_id, target_id):
    with resolution_action_scope(action_id, session_id):
        try:
            return game._run_player_turn_internal(
                player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {})
            )
        except game.TurnResolved as e:
            return game._narrate_resolved_turn(
                e.resolved_turn, player_input, messages, target_id
            )
    return game._TURN_FALL_THROUGH


def _dpt_run_without_action_id(*, action_id, check_evidence, check_feature, interaction_mode, messages, player_input, scene_plan, target_id):
    if action_id is None:
        try:
            return game._run_player_turn_internal(
                player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {})
            )
        except game.TurnResolved as e:
            return game._narrate_resolved_turn(
                e.resolved_turn, player_input, messages, target_id
            )
    return game._TURN_FALL_THROUGH


def _dpt_flight(*, action_id, combat_action, player_input, session_id):
    if combat_action is None and combat_lifecycle.is_flight(game._session(), player_input):
        with resolution_action_scope(action_id, session_id):
            fled = combat_lifecycle.flee(game._session(), action_id, session_id)
        if fled is not None:
            return fled
    return game._TURN_FALL_THROUGH


def _dpt_stand_down(*, action_id, combat_action, player_input, session_id):
    if combat_action is None and combat_lifecycle.is_standing_down(game._session(), player_input):
        with resolution_action_scope(action_id, session_id):
            settled = combat_lifecycle.stand_down(game._session(), action_id, session_id)
        if settled is not None:
            return settled
    return game._TURN_FALL_THROUGH


def _dpt_active_combat_response(*, combat_action, monster_combat, player_input, target_id):
    if combat_action is None and game._session().world_state.get("combat", {}).get("active"):
        with initiative.atomic(game._session()):
            proposal_result = monster_combat.player_response(game._session(), player_input, target_id)
            if proposal_result is not None:
                return proposal_result
    return game._TURN_FALL_THROUGH


def _dpt_equipment_economy(*, combat_action, planning, player_input):
    if (combat_action is None and not planning
            and not combat_lifecycle.is_attack_decision(game._session(), player_input)):
        equipment_result = equipment_economy.execute(game._session(), player_input)
        if equipment_result is not None:
            return equipment_result
    return game._TURN_FALL_THROUGH


def _dpt_ends_in_speech(*, combat_action, front, interaction_mode, player_input, target_id):
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"} and target_id is None and front is None
            and game._ENDS_IN_SPEECH.search(game._normalize_turkish_typos(player_input))):
        hearer = game._active_interlocutor()  # "dedim sana" is said to the one already being talked to
        if hearer is not None:
            interaction_mode, target_id = "say", hearer["id"]
    return interaction_mode, target_id


def _dpt_front_step_read(*, check_feature, combat_action, front_proposal, interaction_mode, player_input, read, target_id):
    if (front_proposal.enabled() and not getattr(game._session(), "_front_ahead", False)
            and not getattr(game._session(), "_front_strike", None)):
        read = game._front_step(player_input, target_id, interaction_mode, combat_action, check_feature)
        game._session()._front_read = read
        game._session()._front_ahead = True
    return read


def _dpt_fallen_turn(*, action_id, messages, player_input, session_id, target_id):
    if game._session().character.get("current_hp", 0) <= 0:
        # A body on the ground has no moves left: whatever is typed or clicked is this turn's save.
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            return game._run_player_turn_internal(player_input, messages, target_id, {"direct_result": None},
                                             "do", action_id)
    return game._TURN_FALL_THROUGH


def _dpt_natural_inventory_query(*, interaction_mode, player_input):
    if (
        interaction_mode == "ask_dm"
        and equipment_economy._natural_inventory_query(player_input)
    ):
        equipment_result = equipment_economy.execute(game._session(), player_input)
        if equipment_result is not None:
            return equipment_result
    return game._TURN_FALL_THROUGH


def _dpt_front_gate(*, front, interaction_mode, player_input, target_id):
    gate = (None if front is not None and (front.get("dropped") or front["kind"] == "wield"
                                           or game._take_names_a_job(front))
            else game._front_offer_gate(front, player_input) if front is not None and front["kind"] == "offer_answer"
            else game._front_consume(front, player_input) if front is not None and front["kind"] == "consume"
            else game._front_hand_over(front, player_input) if front is not None and front["kind"] == "hand_over"
            else game._front_work(front, player_input) if front is not None and front["kind"] == "work"
            else game._thread_gate(player_input, target_id, interaction_mode, front=front))
    return gate
