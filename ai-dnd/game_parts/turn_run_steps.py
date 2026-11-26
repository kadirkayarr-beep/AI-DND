import combat_lifecycle
import talk_mode
import re
import typing
import interaction_adventure
import talk_front
import local_dialogue
import living_world
import game


def _rpt_scene_parent_living(*, action_result, player_input, scene_parent):
    if (
        scene_parent is None
        and living_world.is_anchored_structure_inquiry(player_input)
    ):
        action_result["direct_response"] = (
            "Yakında inceleyebileceğin belirgin bir bina görünmüyor."
        )


def _rpt_action_result_status(*, action_result, finish_turn, player_input):
    if action_result.get("status") == "unresolved":
        return finish_turn(
            action_result,
            action_result.get("direct_response") or game._natural_unresolved_action_response(player_input, action_result),
            is_final=True,
            safety_handling="python_scene_response",
        )
    return game._TURN_FALL_THROUGH


def _rpt_lore_gate_interaction(*, combat, experimental_dialogue_session, interaction_mode, lore_gate, npc_dialogue_route, npc_target, player_input, world_state):
    if (lore_gate and interaction_mode != "ask_dm" and not combat["active"]
            and game._people_speak_for_themselves(world_state)
            and not game._ASKS_DISTANCE.search(local_dialogue.normalize_text(player_input))):
        # Asked aloud with someone standing there, the town's talk is theirs to answer, not the street's.
        here = game._conversation_npcs()
        npc_target = game._explicit_addressee(player_input, here) or npc_target or game.most_plausible_addressee(here, player_input)
        if isinstance(npc_target, dict):
            lore_gate = False
            npc_dialogue_route = experimental_dialogue_session = True
    return experimental_dialogue_session, lore_gate, npc_dialogue_route, npc_target


def _rpt_lore_gate_answerable(*, answerable_personal_kind, experimental_dialogue_session, lore_context, lore_safety_input, npc_place_recommendation, player_input, world_state, world_subject_question):
    lore_gate = answerable_personal_kind is None and not experimental_dialogue_session and (
        (
            not npc_place_recommendation
            and (world_subject_question or local_dialogue.is_world_subject_question(player_input))
        )
        or game._player_question_has_unverified_lore_claim(
            lore_safety_input, lore_context, world_state
        )
    )
    return lore_gate


def _rpt_experimental_dialogue_npc(*, canonical_profile_question, experimental_unverified_claim, front_talk, interaction_mode, npc_dialogue_route, npc_target):
    experimental_dialogue_session = npc_dialogue_route and (
        # BM Task 3: the model read a plain talk line to this person: they answer by speech, even asked of the DM
        (isinstance(npc_target, dict) and not talk_front.old_owner_allowed(front_talk, "personal"))
        or (interaction_mode != "ask_dm"
            and (game._npc_speech_enabled() or experimental_unverified_claim or not canonical_profile_question))
    )
    return experimental_dialogue_session


def _rpt_canonical_profile_question(*, npc_target, player_input, profile_focus):
    canonical_profile_question = (
        local_dialogue.personal_question_kind(player_input)
        in interaction_adventure.PROFILE_FIELD_BY_MEANING.values()
        or (game._is_short_followup(player_input) and profile_focus
            and profile_focus.get("predicate") in interaction_adventure.PROFILE_FIELD_BY_MEANING.values())
    ) and not local_dialogue.has_multiple_dialogue_clauses(player_input, npc_target)
    return canonical_profile_question


def _rpt_shop_request_import(*, finish_turn, shop_request):
    if shop_request:
        import shop_creation

        action_result = shop_creation.resolve_explicit_request(game._session())
        return finish_turn(
            action_result, action_result["direct_response"],
            is_final=not action_result["success"],
        )
    return game._TURN_FALL_THROUGH


def _rpt_interaction_hint_information(*, interaction_hint, npc_target, player_input, target_id, world_state):
    if (
        interaction_hint in {"information", "generate"} and target_id is None
        and (interaction_hint == "generate" or local_dialogue.personal_question_kind(player_input) == "local_work")
        and game._town_in_play(world_state)
    ):
        # Whoever is here answers from what they know; no proposal is needed to find a town's work.
        interaction_hint = None
        if npc_target is None:
            npc_target = game.most_plausible_addressee(game._conversation_npcs(), player_input)
    return interaction_hint, npc_target


def _rpt_target_id_combat(*, combat, npc_target, player_input, target_id, world_state):
    if target_id is None and not combat["active"] and game._turns_to_someone_else(player_input):
        others = [npc for npc in game._conversation_npcs()
                  if not isinstance(npc_target, dict) or npc.get("id") != npc_target.get("id")]
        if others:
            npc_target = game.most_plausible_addressee(others, player_input)
            game._set_scene_active_npc(npc_target, world_state.get("flags", {}).get("turn_index", 0))
    return npc_target


def _rpt_character_reply_action(*, character_reply, finish_turn):
    # Character-sheet facts are Python-owned even during an NPC conversation.
    # Keep combat on its existing path and leave real disclosures/memory
    # questions to the dialogue owner when no supported self-query matches.
    if character_reply:
        action_result = {
            "action": "character_query",
            "status": "answered_from_campaign_state",
            "success": True,
            "state_changes": [],
            "direct_response": character_reply,
        }
        return finish_turn(action_result, character_reply)
    return game._TURN_FALL_THROUGH


def _rpt_topic_name_topic(*, interaction_mode, player_input, world_state):
    topic_name = (
        game._topic_place_name(world_state)
        if (local_dialogue.asks_the_name_of_a_topic(player_input) and interaction_mode != "ask_dm"
            # BM Task 2: a plain-talk reading means the person answers by speech; the name line is the fallback
            and talk_front.old_owner_allowed(talk_front.current(game._session()), "place_name"))
        else None
    )
    return topic_name


def _rpt_local_dialogue_local(*, player_input, world_state):
    if not local_dialogue.is_local_dialogue_input(player_input):
        live_focus = interaction_adventure.current_conversation_focus(world_state)
        if live_focus:
            normalized_input = living_world.normalize_text(player_input)
            for location_id, location in world_state.get("locations", {}).items():
                name = location.get("name") if isinstance(location, dict) else None
                normalized_name = living_world.normalize_text(name or "")
                if (
                    location_id != live_focus.get("scene_id")
                    and normalized_name
                    and re.search(
                        rf"(?<!\w){re.escape(normalized_name)}(?!\w)",
                        normalized_input,
                    )
                ):
                    interaction_adventure.retire_conversation_focus(world_state)
                    break


def _rpt_interaction_mode_say(*, finish_turn, interaction_mode, npc_target):
    if interaction_mode == "say" and npc_target is None:
        result = {
            "action": "dialogue", "status": "clarification", "success": False,
            "state_changes": [],
        }
        nobody = "Burada konuşabileceğin kimse yok." if not game.active_npcs() else None
        return finish_turn(result, nobody or "Kiminle konuşmak istiyorsun?", is_final=True)
    return game._TURN_FALL_THROUGH


def _rpt_walked_up_walked(*, action_id, interaction_mode, messages, said_after, walked_up):
    if (isinstance(walked_up, dict) and walked_up.get("action") == "approach"
            and walked_up.get("status") == "completed" and said_after
            and interaction_mode not in {"say", "ask_dm"}):
        spoken = game._run_player_turn_internal(
            said_after, messages, walked_up.get("target_id"), None, "say", action_id
        )
        spoken["narration"] = f"{walked_up['direct_response']} {spoken['narration']}"
        return spoken
    return game._TURN_FALL_THROUGH


def _rpt_planned_direct_planned(*, interaction_mode, planned_direct, player_input, scene_plan, world_state):
    if (
        isinstance(planned_direct, dict)
        and planned_direct.get("action") == "explore"
        and planned_direct.get("status") == "observed"
        and game._scene_observation_proposal_turn(
            player_input, world_state, interaction_mode
        )
    ):
        scene_plan = {**scene_plan, "direct_result": None}
    return scene_plan


def _rpt_scene_plan_scene(*, interaction_mode, player_input, scene_plan, target_id):
    scene_plan = (
        scene_plan
        if isinstance(scene_plan, dict)
        else game.plan_living_world_turn(
            player_input,
            target_id=target_id,
            interaction_mode=interaction_mode,
        )
    )
    return scene_plan


def _rpt_local_npc_place(*, interaction_mode, player_input, target_id, world_state):
    local_npc_place_request = (
        interaction_mode != "ask_dm"
        and local_dialogue.is_local_place_recommendation_request(player_input)
        and game._has_active_local_npc_focus_for_place_request(
            world_state, target_id=target_id
        )
    )
    return local_npc_place_request


def _rpt_character_current_hp(*, entry_combat, world_state):
    if (
        typing.cast("game.GameSession", game._session()).character.get("current_hp", 0) <= 0  # the engine always has a session
        or world_state.get("player_combat_status") == "unconscious"
    ) and not (
        entry_combat["active"]
        and entry_combat["current_actor_id"] == "player"
    ):
        raise game.PlayerCannotAct("Bilinçsiz karakter eylem gerçekleştiremez.")


def _rpt_scene_detail_proposals(*, action_result, allow_new_features, scene_detail_proposals, scene_parent):
    if isinstance(scene_detail_proposals, list) and scene_detail_proposals:
        parent_id = scene_parent.get("id") if isinstance(scene_parent, dict) else None
        bound_proposals = [
            proposal for proposal in scene_detail_proposals[:1]
            if isinstance(proposal, dict)
            and proposal.get("parent_id") == parent_id
        ]
        action_result["scene_detail_proposal_submitted"] = bool(
            scene_detail_proposals
        )
        action_result["verified_world_updates"] = game.validate_world_updates(
            {"create_features": bound_proposals},
            allow_new_features=allow_new_features,
            allowed_feature_kinds=game.SCENE_DETAIL_KIND_ALLOWLIST,
        )


def _rpt_speech_debug_trail(*, experimental_unverified_claim, invalid_or_empty, model_raw_narration, npc_target, player_input, raw_intent, raw_narration, text, text_before_finalize, unverified_history_echo):
    game._speech_debug_trail({
        "player": player_input,
        "npc_id": npc_target.get("id"),
        "npc_name": living_world.public_npc_name(npc_target),
        "model_raw": model_raw_narration,
        "cleaned": raw_narration,
        "invalid_or_empty": invalid_or_empty,
        "unverified_claim_in_prompt": experimental_unverified_claim,
        "history_echo": unverified_history_echo,
        "model_world_updates": bool(raw_intent.get("world_updates")),
        "model_lore_claims": bool(raw_intent.get("lore_claims")),
        "safe_narration": (
            None if invalid_or_empty
            else interaction_adventure.safe_narration(text_before_finalize)
        ),
        "before_finalize": text_before_finalize,
        "finalize_changed_text": text != text_before_finalize,
        "safety": getattr(game._session(), "last_narration_safety", None),
        "shown": (
            text if text.casefold().startswith(
                living_world.public_npc_name(npc_target).casefold())
            else f"{living_world.public_npc_name(npc_target)}, “{text}”"
        ),
    })


def _rpt_speech_checks_name(*, attributed_speech, invalid_or_empty, kept, python_town_response, raw_intent, said, stock_swapped, text, text_before_finalize, unverified_history_echo):
    speech_checks = [name for name, fired in (
        ("invalid_or_empty", invalid_or_empty),
        ("spoken_trimmed", attributed_speech is not None and kept != said),
        ("history_echo", unverified_history_echo),
        ("world_updates", bool(raw_intent.get("world_updates"))),
        ("lore_claims", bool(raw_intent.get("lore_claims"))),
        ("unsafe", not invalid_or_empty and not interaction_adventure.safe_narration(text_before_finalize)),
        ("python_town_lead", python_town_response is not None),
        ("finalize_changed", text != text_before_finalize and not stock_swapped),
        ("stock_swapped", stock_swapped),
    ) if fired]
    return speech_checks


def _rpt_compound_speech_npc(*, compound_speech, finish_turn, npc_target, player_input, safe_name, world_state):
    if not compound_speech:
        npc_name = living_world.public_npc_name(npc_target)
        reply = local_dialogue.introduction_reply(world_state, npc_target, safe_name)
        narration = f'{npc_name}: “{reply}”'
        # A single utterance may introduce the player AND ask who the
        # addressee is. Both answers come from verified Python state.
        if game._detect_query_type(player_input, npc_target) == "npc_identity":
            identity_reply = game._handle_query(player_input, "npc_identity", npc_target)
            if identity_reply:
                narration += " " + identity_reply
        action_result = {
            "action": "dialogue",
            "status": "player_name_disclosed",
            "success": True,
            "npc_id": npc_target["id"],
            "state_changes": ["npcs.memory"],
        }
        game.record_npc_interaction(
            npc_target, narration, player_input, npc_target
        )
        if local_dialogue.explicit_player_name_disclosure(player_input) != safe_name:
            # The words said were not the name as written; keep it spelled right.
            local_dialogue.remember_explicit_player_name(npc_target, safe_name)
        return finish_turn(
            action_result,
            narration,
            safety_reason_code="NPC_MEMORY_EXPLICIT_PLAYER_NAME",
            safety_handling="python_memory_response",
        )
    return game._TURN_FALL_THROUGH


def _rpt_conversation_resolution_conversation(*, interaction_hint, npc_target, player_input, raw, world_state):
    conversation_resolution, conversation_rejected = (
        game._validate_interaction_conversation(
            player_input,
            world_state,
            raw,
            npc_target,
            required=(
                interaction_hint == "information" and npc_target is not None
            ),
        )
    )
    return conversation_rejected, conversation_resolution


def _rpt_accepted_npc_created(*, accepted_npc, existing_ids, finish_turn, flags, local_proposal, world_state):
    if accepted_npc is not None:
        created_now = accepted_npc.get("id") not in existing_ids
        talk_mode.open(world_state, accepted_npc["id"], turn=flags.get("turn_index", 0))
        status = "created_local_person" if created_now else "reused_local_person"
        text = (
            f"{local_proposal['appearance']} {local_proposal['role']} "
                    f"{'görünür hale geliyor' if created_now else 'yeniden dikkatini çekiyor'}."
        )
        return finish_turn(
            {
                "action": "dialogue",
                "status": status,
                "success": True,
                "npc_id": accepted_npc["id"],
                "state_changes": ["world.npcs"] if created_now else [],
            },
            text,
            safety_handling="python_scene_response",
            is_final=True,
        )
    return game._TURN_FALL_THROUGH


def _rpt_accepted_npc_create_2(*, local_proposal, request_key, world_state):
    accepted_npc = game.create_npc_from_ai(
        {
            "name": local_proposal["name"],
            "role": local_proposal["role"],
            "appearance": local_proposal["appearance"],
            "location": world_state.get("location"),
            "relationship": "neutral",
        },
        request_key=request_key,
    )
    return accepted_npc


def _rpt_preparsed_scene_intent(*, check_feature, interaction_mode, player_input, world_state):
    # A sole-NPC fallback is useful for "Merhaba", but must not override a
    # player-specified description of someone absent from the current scene.
    preparsed_scene_intent = game.parse_player_intent(
        player_input,
        interaction_context=interaction_adventure.context(
            world_state, None, player_input
        ),
        recent_scene_narration=game._recent_player_visible_narration(),
        allow_scene_detail_proposals=game._scene_detail_proposals_allowed(
            player_input, world_state, interaction_mode
        ),
            allow_local_person_proposal=game.should_generate_npcs(player_input),
            strict=check_feature is not None,
    )
    return preparsed_scene_intent


def _rpt_interaction_mode_say_2(*, finish_turn, held_plan, interaction_mode, player_input, resolve_intent):
    if (
        interaction_mode not in {"say", "ask_dm"}
        and held_plan is None  # a blow inside clauses held for the reading is still part of the plan
        and game._has_explicit_attack_verb(player_input)
    ):
        action_result = resolve_intent(
            {"intent": "attack"},
            player_input,
        )
        return finish_turn(
            action_result,
            action_result.get("direct_response")
            or "Hangi hedefe saldırmak istiyorsun?",
        )
    return game._TURN_FALL_THROUGH


def _rpt_deferred_referent_next(*, current_location, deferred_referent_id, world_state):
    deferred_referent = next(
        (
            ref for ref in (
                world_state.get("scene_state", {}).get("scenes", {})
                .get(current_location, {}).get("referents", [])
            )
            if isinstance(ref, dict) and ref.get("id") == deferred_referent_id
            and ref.get("lifecycle") == "presented"
        ),
        None,
    )
    return deferred_referent


def _rpt_selected_npc_canonical(*, npc_resolution, selected_npc):
    if selected_npc is not None:
        canonical_npc = next(
            (
                npc for npc in game.active_npcs()
                if npc.get("id") == selected_npc["id"]
            ),
            None,
        )
        if canonical_npc is not None:
            npc_resolution = {"status": "found", "npc": canonical_npc}
            selected_npc = canonical_npc
        if canonical_npc is None:
            selected_npc = None
    return npc_resolution, selected_npc


def _rpt_preparsed_scene_intent_2(*, check_feature, interaction_mode, player_input, world_state):
    preparsed_scene_intent = game.parse_player_intent(
        player_input,
        interaction_context=interaction_adventure.context(
            world_state, None, player_input
        ),
        recent_scene_narration=game._recent_player_visible_narration(),
        allow_scene_detail_proposals=game._scene_detail_proposals_allowed(
            player_input, world_state, interaction_mode
        ),
        allow_local_person_proposal=game.should_generate_npcs(player_input),
        strict=check_feature is not None,
    )
    return preparsed_scene_intent


def _rpt_allow_new_features(*, expected_location_change, player_input, shop_request):
    allow_new_features = (
        not shop_request
        and game.should_generate_features(player_input, expected_location_change)
        and not game.is_player_world_assertion(player_input)
    )
    return allow_new_features


def _rpt_allow_new_npcs(*, expected_location_change, player_input, shop_request):
    allow_new_npcs = (
        not shop_request
        and game.should_generate_npcs(player_input, expected_location_change)
        and not game.is_player_world_assertion(player_input)
    )
    return allow_new_npcs


def _rpt_npc_place_recommendation(*, interaction_mode, npc_target, player_input):
    npc_place_recommendation = (
        isinstance(npc_target, dict)
        and interaction_mode != "ask_dm"
        and local_dialogue.is_local_place_recommendation_request(player_input)
    )
    return npc_place_recommendation


def _rpt_supported_lore_response(*, lore_context, player_input, world_state):
    supported_lore_response = game._supported_lore_question_response(
        player_input,
        lore_context,
        world_state,
    )
    return supported_lore_response


def _rpt_work_answer_shop(*, interaction_mode, player_input, shop_request):
    # A requested shop with an 'işleten' shopkeeper is not a job inquiry.
    work_answer = (
        None
        if shop_request or interaction_mode == "say"
        else local_dialogue.unaddressed_work_answer(player_input)
    )
    return work_answer


def _rpt_interaction_hint_interaction(*, interaction_mode, npc_target, player_input, thread_talk):
    interaction_hint = (
        None if interaction_mode == "ask_dm" or thread_talk
        or combat_lifecycle.quoted_report(game._session(), player_input)
        else interaction_adventure.hint(player_input, npc_target)
    )
    return interaction_hint


def _rpt_character_reply_known(*, combat, interaction_mode, player_input):
    # Character-sheet questions do not require an unambiguous NPC. Keep the
    # existing combat and explicit-target validation boundaries intact.
    character_reply = (
        game.known_character_answer(player_input)
        if not combat["active"] and interaction_mode != "say"
        else None
    )
    return character_reply


def _rpt_spell_reading_engine(*, finish_turn, spell_effects, spell_reading):
    if spell_reading is not None:
        # 4C.5: the engine decides and commits (a fact, or a truthful line that nothing was cast); a resolved fact goes
        # to the turn narrator (narration only, the line is its fallback), a refusal is told as it is.
        cast = spell_effects.resolve(game._session(), spell_reading)
        return finish_turn(cast["action_result"], cast["narration"])
    return game._TURN_FALL_THROUGH


def _rpt_world_subject_question(*, interaction_mode, local_npc_place_request, player_input):
    world_subject_question = (
        True if interaction_mode == "ask_dm"
        else False if interaction_mode == "say" or local_npc_place_request
        else local_dialogue.is_world_subject_question(player_input)
    )
    return world_subject_question


def _rpt_action_result_verified(*, action_result, early_bound, early_changed, player_input, shop_request):
    action_result["verified_world_updates"] = game.validate_world_updates(
        {"create_features": early_bound},
        allow_new_features=(not shop_request
                            and game.should_generate_features(player_input, early_changed)
                            and not game.is_player_world_assertion(player_input)),
        allowed_feature_kinds=game.SCENE_DETAIL_KIND_ALLOWLIST,
    )


def _rpt_action_result_status_2(*, action_result, finish_turn, npc_target):
    if action_result["status"] != "proposal_rejected" and not (
            action_result["status"] == "unbacked" and isinstance(npc_target, dict)):
        return finish_turn(
            action_result, action_result["direct_response"],
            is_final=action_result["status"] in {"no_effect", "answered", "blocked"},
        )
    return game._TURN_FALL_THROUGH


def _rpt_turned_down_what(*, accepted_model_speech, attributed_speech, npc_target, player_input, settled_money, speech_checks, text, turned_down_what_was_paid, world_state):
    if turned_down_what_was_paid or (
        accepted_model_speech and not game._with_only_backed_money(attributed_speech, settled_money)
    ):
        accepted_model_speech = False
        text = (game._job_fallback(world_state) or game._town_fallback(world_state, npc_target, player_input)
                or interaction_adventure.immersive_unknown(npc_target, player_input))
        speech_checks.append("unbacked_money")
    return accepted_model_speech, text


def _rpt_accepted_model_speech(*, attributed_speech, experimental_npc_dialogue, invalid_or_empty, text, unverified_history_echo):
    accepted_model_speech = (
        experimental_npc_dialogue
        and not invalid_or_empty
        and not unverified_history_echo
        and attributed_speech is not None
        and text == game._compose_experimental_npc_speech(attributed_speech)
    )
    return accepted_model_speech


def _rpt_after_speech_after(*, action_result, attributed_speech, experimental_npc_dialogue, experimental_unverified_claim, narration_source, npc_target, player_input, python_town_response, text, world_state):
    after = game._speech_after_check(
        text, world_state=world_state, npc_target=npc_target, player_input=player_input,
        action_result=action_result, experimental_npc_dialogue=experimental_npc_dialogue,
        experimental_unverified_claim=experimental_unverified_claim, narration_source=narration_source,
        python_town_response=python_town_response, attributed_speech=attributed_speech,
    )
    return after


def _rpt_action_result_action(*, claimed_npc, response):
    action_result = {
        "action": "dialogue",
        "status": "answered_from_npc_memory",
        "success": True,
        "npc_id": claimed_npc["id"],
        "state_changes": [],
        "direct_response": response,
    }
    return action_result


def _rpt_spoken_reference_bool(*, about, claimed_npc, ledger, npc_target, player_input, world_state):
    # A previous conversation alone cannot support a new quoted claim.
    # Only recorded speech support may
    # bypass the unsupported-history check.
    spoken_reference = bool(
        isinstance(npc_target, dict) and claimed_npc is npc_target
        and npc_target.get("location") == world_state.get("location")
        and ledger["status"] == "supported" and ledger.get("claim_kind") in (None, "said")
        and (about == "memory"  # "beni hatırlıyor musun?" to someone whose own words are recorded (Task 28)
             or about == "npc_words" and game._SECOND_PERSON_SAID.search(game._normalize_turkish_typos(player_input)))
    )
    return spoken_reference


def _rpt_ledger_status_supported(*, ledger, npc_statements, player_input, supported_entry):
    if ledger["status"] == "supported":
        supported_entry = f"“{ledger['quote']}”"
    elif ledger["status"] == "unsupported" or (
        supported_entry and not npc_statements.entry_supports_claim(supported_entry, player_input)
    ):
        supported_entry = None
    return supported_entry


def _rpt_compound_speech_talk(*, npc_target, player_input, safe_name):
    # Hearing the same name again is no moment for the greeting a second time.
    compound_speech = not talk_front.old_owner_allowed(  # BM Task 2: the name is stored below, speech voices it
        talk_front.current(game._session()), "name_disclosure") or game._known_player_name(npc_target) == safe_name or (
        local_dialogue.has_multiple_dialogue_clauses(player_input, npc_target)
        # E9: a question Python cannot answer goes to speech; "who are you" Python answers itself.
        and (game._npc_speech_enabled() or (interaction_adventure._asks(player_input)
                                       and game._detect_query_type(player_input, npc_target) != "npc_identity"))
    )
    return compound_speech


def _rpt_answer_person_return(*, action_result, answer_in_person, finish_turn, narrated_without_model):
    if not answer_in_person:
        return finish_turn(
            action_result, action_result["direct_response"],
            is_final=narrated_without_model or action_result["status"] in {
                "proposal_rejected", "no_effect", "answered", "blocked",
            },
        )
    return game._TURN_FALL_THROUGH


def _rpt_action_result_status_3(*, answer_in_person, interaction_hint, npc_target, player_input, raw):
    action_result = (
        {"status": "proposal_rejected"} if answer_in_person else interaction_adventure.resolve(
            game._session(), player_input, raw.get("interaction"), npc_target,
            fallback_operation=interaction_hint,
        )
    )
    return action_result


def _rpt_result_action_dialogue():
    result = {
        "action": "dialogue",
        "status": "proposal_rejected",
        "success": False,
        "state_changes": [],
    }
    return result


def _rpt_person_living_world(*, action_id, messages, person, request, world_state):
    if person is not None:
        living_world.set_player_position(
            world_state, world_state.get("location"), "standing", person["id"]
        )
        return game._run_player_turn_internal(
            request, messages, person["id"], None, "say", action_id
        )
    return game._TURN_FALL_THROUGH
