import living_world
import interaction_adventure
import talk_front
import game


def _tg_findings_text_exit(*, action_result, findings, finish_turn, quest_world_before):
    if isinstance(findings, dict) and isinstance(findings.get("text"), str) and findings["text"].strip():
        # LR00-P2: a target-bound finding IS the result. Live runs showed the
        # narrator inventing a figure behind closed shutters; the receipt's
        # own words are shown instead, with no second model call.
        quest_transitions = game._session().evaluate_quest_events(
            quest_world_before, action_result
        )
        if quest_transitions:
            action_result["quest_outcomes"] = quest_transitions
        return finish_turn(
            action_result,
            findings["text"],
            quest_transitions,
            is_final=True,
            safety_handling="python_scene_response",
        )
    return game._TURN_FALL_THROUGH


def _tg_attack_findings_exit(*, action_result, finish_turn, quest_world_before):
    if action_result.get("action") in {"attack", "death_save"}:
        # Reuse the existing mechanical renderer. Do not send a not-yet-saved
        # combat outcome to a model before the API receipt transaction succeeds.
        quest_transitions = game._session().evaluate_quest_events(
            quest_world_before, action_result
        )
        if quest_transitions:
            action_result["quest_outcomes"] = quest_transitions
        return finish_turn(
            action_result,
            game._combat_narration(action_result),
            quest_transitions,
            is_final=True,
        )
    return game._TURN_FALL_THROUGH


def _tg_shop_action_result(*, npc_target, player_input, resolve_intent, shop_request, target_id, validated_intent):
    if shop_request:
        action_result = {
            "action": "shop_setup",
            "status": "requested",
            "success": True,
            "state_changes": [],
        }
    elif target_id is None:
        action_result = resolve_intent(validated_intent, player_input, npc_target)
    else:
        action_result = resolve_intent(
            validated_intent,
            player_input,
            npc_target,
            target_id=target_id,
        )
    return action_result


def _tg_shop_presence_exit(*, finish_turn, npc_target, player_input, target_id, world_state):
    if (game._shop_presence_question(player_input)
            and ((target_id is None and not isinstance(npc_target, dict)
                  and (getattr(game._session(), "_front_read", None) or {}).get("kind") != "speak_to")
                 # asked of the one who keeps the shop here, the shop line is her answer (Review 11 A4)
                 or (isinstance(npc_target, dict) and npc_target.get("location") == world_state.get("location")
                     and game._runs_a_shop(world_state, npc_target)
                     # BM Task 2: a plain-talk reading answers by speech; the list only when it asks for the shop
                     and talk_front.old_owner_allowed(talk_front.current(game._session()), "shop_presence")))):
        message = talk_front.shop_presence_reply(world_state, npc_target)
        action_result = {
            "action": "shop_inquiry",
            "status": "answered_from_campaign_state",
            "success": True,
            "state_changes": [],
        }
        return finish_turn(action_result, message)
    return game._TURN_FALL_THROUGH


def _tg_shop_exit_b(*, finish_turn, interaction_mode, player_input):
    if (interaction_mode not in {"say", "ask_dm"}
            and game._explicit_campaign_shop_negative_request(player_input)):
        action_result = {
            "action": "shop_setup",
            "status": "explicitly_declined",
            "success": True,
            "state_changes": [],
        }
        message = (
            "Anlaşıldı; yeni bir dükkân ya da dükkâncı aramadan yoluna devam edebilirsin."
        )
        return finish_turn(
            action_result,
            message,
            safety_reason_code="SHOP_CREATION_EXPLICITLY_DECLINED",
            safety_handling="python_fallback",
        )
    return game._TURN_FALL_THROUGH


def _tg_shop_exit_a(*, finish_turn, interaction_mode, player_input, world_state):
    if (interaction_mode not in {"say", "ask_dm"}
            and world_state.get("shops") and game._shop_economy_request(player_input)):
        action_result = {
            "action": "shop_economy",
            "status": "unsupported",
            "success": False,
            "state_changes": [],
        }
        message = (
            "Dükkânda sana sunulmuş bir ürün ya da fiyat yok; bu yüzden alışveriş yapamıyorsun."
        )
        return finish_turn(
            action_result,
            message,
            safety_reason_code="SHOP_ECONOMY_NOT_SUPPORTED",
            safety_handling="python_fallback",
        )
    return game._TURN_FALL_THROUGH


def _tg_shop_request_exit(*, current_shop_count, finish_turn, shop_request, world_state):
    if shop_request and (
        game._campaign_has_shopkeeper()
        or len(world_state.get("shops", [])) >= 12
        or current_shop_count >= 3
        or len(world_state.get("npcs", [])) >= 60
        or len(game.active_npcs(world_state.get("location"))) >= 6
    ):
        action_result = {
            "action": "shop_setup",
            "status": "limit_reached",
            "success": False,
            "state_changes": [],
        }
        message = "Yeni bir dükkânla karşılaşmıyorsun; çevrendeki mevcut dükkânlara bakabilirsin."
        return finish_turn(action_result, message)
    return game._TURN_FALL_THROUGH


def _tg_hint_intent(*, check_feature, classifier_unusable, combat, intent_model_calls, intent_source, interaction_hint, npc_target, player_input, raw, scene_preparse_model_calls, world_state):
    if interaction_hint and not combat["active"] and not classifier_unusable:
        intent_model_calls = scene_preparse_model_calls + 1
        intent_source = "interaction_proposal"
        raw = game.parse_player_intent(
            player_input,
            interaction_context=interaction_adventure.context(
                world_state, npc_target, player_input
            ),
            operation_hint=interaction_hint,
            require_conversation=(
                interaction_hint == "information" and npc_target is not None
            ),
            strict=check_feature is not None,
        )
        if raw.get("classifier_unusable"):
            classifier_unusable = True
            raw = None
    return classifier_unusable, intent_model_calls, intent_source, raw


def _tg_scene_plan(*, held_plan, interaction_mode, player_input, scene_plan, target_id):
    if scene_plan is None and interaction_mode not in {"say", "ask_dm"} and held_plan is None:
        # The API plans first. Direct turns use the same local-entry owner. A held plan walks nowhere before its reading.
        if (
            living_world.classify_scene_action(player_input) == "enter"
            or game._names_current_local_exit(player_input)
        ):
            scene_plan = game.plan_living_world_turn(
                player_input,
                target_id=target_id,
                interaction_mode=interaction_mode,
            )
    return scene_plan
