import local_dialogue
import interaction_adventure
import money_owner
import living_world
import game


def _ts_speech_money(*, action_result, attributed_speech, invalid_spoken_stage_direction, model_raw_narration, name_stance, npc_statements, npc_target, player_input, raw_intent, raw_spoken, raw_stage, recognised, settled_money, valid_speech_packet, world_state):
    if valid_speech_packet:
        money_owner.read_answer(game._session(), raw_intent, npc_target["id"],
            money_owner.parts_for(world_state, game._session(), npc_target["id"]))
        asked = raw_intent.get("asks_for")
        if isinstance(asked, str) and asked in money_owner.askable(world_state, npc_target):
            game._session()._asks_for = (npc_target["id"], asked)  # opened after the reply, if at all
        import npc_speech_boundary
        cleaned_spoken = game._clean_npc_speech(
            npc_speech_boundary.normalize_bound_speech_label(
                raw_spoken, npc_target,
                visible=any(n.get("id") == npc_target.get("id")
                            for n in game._conversation_npcs()),
            )
        )
        if cleaned_spoken.strip():
            cleaned_spoken = game._ground_local_place_recommendation_reply(
                cleaned_spoken,
                npc_target,
                world_state,
                player_input,
            )
        cleaned_stage = game._clean_npc_stage_direction(raw_stage)
        cleaned_stage = game._ground_local_place_recommendation_stage(
            cleaned_stage,
            npc_target,
            world_state,
            player_input,
        )
        cleaned_spoken = npc_speech_boundary.strip_player_echo(
            cleaned_spoken, player_input
        )
        cleaned_spoken = npc_speech_boundary.drop_ungrounded_prop_sentences(
            cleaned_spoken,
            [
                {
                    "name": feature.get("name"),
                    "description": feature.get("description"),
                    "aliases": feature.get("aliases") or [],
                }
                for feature in living_world.visible_features(world_state)
                if isinstance(feature, dict)
            ],
        )
        cleaned_spoken = npc_speech_boundary.without_no_name_claim(cleaned_spoken)
        cleaned_spoken = npc_speech_boundary.without_false_presence(
            world_state, cleaned_spoken, world_state.get("location")
        )
        cleaned_stage = npc_speech_boundary.strip_player_quote(
            cleaned_stage, player_input
        )
        cleaned_stage = game._shown_stage_direction(cleaned_stage, world_state)
        if game._is_explicit_name_led_gesture_line(cleaned_spoken, npc_target):
            cleaned_spoken = ""
            invalid_spoken_stage_direction = True
        cleaned_spoken = game._without_lines_already_said(
            cleaned_spoken, npc_target, world_state, player_input
        )
        if recognised:  # re-review R1, RR2-1: recognition backs no added event, said or shown
            if cleaned_spoken.strip():
                cleaned_spoken = npc_statements.only_what_recognition_backs(
                    world_state, npc_target, player_input, cleaned_spoken)
            if cleaned_stage.strip():
                cleaned_stage = npc_statements.only_what_recognition_backs(
                    world_state, npc_target, player_input, cleaned_stage, stage=True)
        settled_money = game._settle_spoken_commitment(
            world_state, npc_target, player_input, raw_intent.get("commitment"), cleaned_spoken,
            threat=raw_intent.get("threat"), persuade=game._coin_persuasion(action_result), stage=cleaned_stage,
        )
        cleaned_spoken = settled_money["spoken"]
        cleaned_stage = settled_money["stage"]  # D-264: a coin ask cleans the gesture as it cleans the line
        if getattr(game._session(), "_empty_handed", False):
            cleaned_stage = ""  # nothing was held out, so no gesture takes it
        elif settled_money.get("unbacked"):
            import pocket
            cleaned_stage = pocket.without_said(cleaned_stage, settled_money["unbacked"])
        if name_stance == "reveal" and cleaned_spoken.strip():
            cleaned_spoken = game._spoken_name_answer(cleaned_spoken, npc_target)
        attributed_speech = {
            # These authority fields are stamped by Python, never
            # accepted from the model response.
            "source": "experimental_attributed_speech",
            "speaker_id": npc_target["id"],
            "spoken_text": cleaned_spoken,
            "stage_direction": cleaned_stage,
        }
        # W03: a known lock may be recalled by a SEPARATE narrator note; it never replaces the NPC's line.
        place_note = game._attributed_place_note(cleaned_spoken, npc_target, world_state, player_input)
        if place_note:
            attributed_speech["narrator_note"] = place_note
        raw_narration = game._compose_experimental_npc_speech(
            attributed_speech
        )
        model_raw_narration = {
            "spoken_text": raw_spoken,
            "stage_direction": raw_stage,
        }
    else:
        # All schema/shape failures share one explicit fallback
        # class; they are not mislabeled as an empty model answer.
        raw_narration = None
    return attributed_speech, invalid_spoken_stage_direction, model_raw_narration, raw_narration, settled_money


def _ts_speech_packet(*, raw_intent, raw_spoken, raw_stage):
    # Older narration-only packets and model-supplied authority
    # fields are rejected, not silently reinterpreted.
    valid_speech_packet = (
        isinstance(raw_intent, dict)
        and set(raw_intent).issubset({
            "spoken_text",
            "stage_direction",
            "coin_answer",
            "coin_answer_for",
            "asks_for",
            "remember_player_line",
            "mentions",
            "voiced",
            "witness_recall",
            "price_negotiation",
            "commitment",
            "threat",
            # The intent pre-parser can merge its recognized,
            # untrusted envelope into the narration packet.
            "intent",
            "action",
            "target",
            "completion",
            "confidence",
            "interaction",
            "world_updates",
            "lore_claims",
        })
        and "narration" not in raw_intent
        and "source" not in raw_intent
        and "speaker_id" not in raw_intent
        and isinstance(raw_spoken, str)
        and isinstance(raw_stage, str)
        and len(raw_spoken) <= 600
        and len(raw_stage) <= 600
    )
    return valid_speech_packet


def _ts_witness_exit(*, finish_turn, npc_target, player_input, raw_intent, witness_attempt, witness_recall, world_state):
    if witness_attempt:
        witnessed_text = witness_recall.answer(
            world_state, npc_target, player_input, raw_intent.get("witness_recall"), about="memory")
        name = living_world.public_npc_name(npc_target)
        if witnessed_text is not None:
            response = f'{name}, "Alıntıladığın olay: {witnessed_text}" diye gördüğü olayı hatırlatır.'
            action_result = {"action": "dialogue", "status": "answered_from_witnessed_deed",
                             "success": True, "npc_id": npc_target["id"], "state_changes": []}
            game.record_npc_interaction(npc_target, response, player_input, npc_target)
        else:
            response = f'{name}, "Hangi olaydan söz ettiğini biraz açar mısın?" diye sorar.'
            action_result = {"action": "dialogue", "status": "unverified",
                             "success": False, "npc_id": npc_target["id"], "state_changes": []}
            # Clarification is not a new canonical memory or witness source.
        return finish_turn(action_result, response, safety_handling="python_scene_response")
    return game._TURN_FALL_THROUGH


def _ts_conversation_check(*, experimental_npc_dialogue, interaction_mode, npc_target, player_input, raw_intent, world_state):
    conversation_resolution, conversation_rejected = (
        game._validate_interaction_conversation(
            player_input,
            world_state,
            raw_intent,
            npc_target,
            required=(
                interaction_mode == "say"
                and npc_target is not None
                and not experimental_npc_dialogue
                and not game._grounded_item_request_proposal(
                    raw_intent, npc_target, player_input
                )
            ),
        )
    )
    return conversation_rejected, conversation_resolution


def _ts_parse_intent(*, experimental_npc_dialogue, experimental_unverified_claim, name_stance, npc_target, player_input, world_state):
    raw_intent = game.parse_player_intent(
        player_input,
        interaction_context=(
            game._experimental_npc_dialogue_context(
                world_state, npc_target,
                unverified_claim=experimental_unverified_claim,
                followup=game._is_short_followup(player_input),
                personal_context=(
                    local_dialogue.personal_question_kind(player_input)
                    != "local_work"
                ),
            )
            if experimental_npc_dialogue
            else interaction_adventure.context(
                world_state, npc_target, player_input
            )
        ),
        dialogue_narration=not experimental_npc_dialogue,
        experimental_npc_dialogue=experimental_npc_dialogue,
        speech_note=(
            game._experimental_speech_note(world_state, npc_target, name_stance, player_input)
            if experimental_npc_dialogue else ""
        ),
    )
    return raw_intent


def _ts_personal_answer_exit(*, conversation_resolution, experimental_npc_dialogue, finish_conversation_resolution, finish_turn, npc_target):
    if experimental_npc_dialogue:
        if conversation_resolution and conversation_resolution.get("answer_field"):
            value = conversation_resolution["answer_value"]
            name = living_world.public_npc_name(npc_target)
            action_result = {
                "action": "dialogue",
                "status": "answered_personal_question",
                "success": True,
                "npc_id": npc_target["id"],
                "reality_category": local_dialogue.PROCEDURAL_PERSONAL_FACT,
                "state_changes": [],
                "experimental": True,
            }
            return finish_turn(
                action_result,
                f'{name}, “{value.strip()}” diye yanıt verir.',
                safety_handling="python_scene_response",
            )
    else:
        conversation_outcome = finish_conversation_resolution(
            conversation_resolution, npc_target
        )
        if conversation_outcome is not None:
            return conversation_outcome
    return game._TURN_FALL_THROUGH


def _ts_price_reply_commit(*, action_result, negotiation, npc_target, player_input, price_reply_accepted, resolve_intent, target_id):
    if (price_reply_accepted and negotiation is not None
            and negotiation["npc_id"] == npc_target.get("id")):
        if action_result.get("action") == "skill_check":
            # A statement may already have rolled through deterministic social routing.
            # Reuse that authoritative outcome; never reroll or reapply its world effects.
            check = {"skill": action_result.get("skill"),
                     "result": "BAŞARILI" if action_result.get("outcome") == "success" else "BAŞARISIZ"}
            note = money_owner.haggle(game._session(), npc_target, check,
                                       negotiation=negotiation, player_input=player_input)
            if note:
                action_result["haggle_note"] = note
        else:
            price_result = resolve_intent({"intent": "persuasion", "price_negotiation": negotiation},
                                          player_input, npc_target=npc_target, target_id=target_id)
            if price_result.get("action") == "skill_check":
                action_result.update(price_result)


def _ts_accepted_text(*, accepted_model_speech, action_result, attributed_speech, experimental_npc_dialogue, final_safety_handling, npc_target, player_input, profile_focus, stock_swapped, text, text_before_finalize, world_state):
    if experimental_npc_dialogue:
        if accepted_model_speech:
            if not (game._is_short_followup(player_input) and profile_focus):
                interaction_adventure.retire_conversation_focus(world_state)
            text = game._render_experimental_npc_speech(
                attributed_speech, npc_target
            )
        else:
            name = living_world.public_npc_name(npc_target)
            if (action_result.get("action") == "skill_check" and final_safety_handling == "python_fallback"
                    and not stock_swapped and text != text_before_finalize and not text.casefold().startswith(name.casefold())):
                # The safety put the check's own narration in place of the reply ("İncelemen sonuç
                # vermedi"): that is the narrator's, not theirs. It stays as narration, outside any quote,
                # and the person answers in their own words (Task 34, review M3).
                own = game._person_fallback(world_state, npc_target, player_input)
                text = f"{text} {own if own.casefold().startswith(name.casefold()) else f'{name}, “{own}”'}"
            elif not text.casefold().startswith(name.casefold()):
                text = f'{name}, “{text}”'
    return text


def _ts_finalize_text(*, action_result, attributed_speech, invalid_spoken_stage_direction, npc_target, player_input, python_town_response, text, unverified_history_echo):
    text = game.finalize_narration(
        text, player_input, npc_target, action_result,
        fallback_reason_code=(
            "INVALID_NARRATION"
            if invalid_spoken_stage_direction
            else "UNVERIFIED_PLAYER_CLAIM_ECHO"
            if unverified_history_echo else None
        ),
        attributed_speech=attributed_speech,
        python_town_response=python_town_response,
    )
    return text


def _ts_town_response(*, experimental_unverified_claim, invalid_or_empty, npc_target, player_input, python_town_response, raw_intent, text, unverified_history_echo, world_state):
    if not invalid_or_empty and (
        unverified_history_echo
        or raw_intent.get("world_updates")
        or raw_intent.get("lore_claims")
        or not interaction_adventure.safe_narration(text)
    ):
        if experimental_unverified_claim:
            text = game.historical_claim_denial(npc_target, player_input)
        else:
            # D-249 F1: the person passes on a lead (job, town, place to ask) before any bare "I don't know".
            text = game._person_fallback(world_state, npc_target, player_input)
            if text != interaction_adventure.immersive_unknown(npc_target, player_input):
                python_town_response = text
    return python_town_response, text
