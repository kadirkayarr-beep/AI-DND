import re
import talk_front
import timed_gameplay
import scheduled_events
import copy
import talk_mode
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


def _tx_explicit_sword_drop(*, combat, finish_turn, interaction_mode, player_input, resolve_intent, target_id):
    # Concrete possession changes outrank an abstract 'abandon' proposal.
    # Restrict this bypass to unambiguous present-tense commands; all other
    # equipment operations remain with the existing Python inventory owner.
    if (interaction_mode not in {"say", "ask_dm"}
            and target_id is None and not combat["active"]
            and game._explicit_sword_drop(player_input)):
        action_result = resolve_intent({"intent": "inventory"}, player_input)
        return finish_turn(
            action_result,
            action_result.get("direct_response") or game._fallback_for_action_result(
                player_input, action_result
            ),
            is_final=True,
        )
    return game._TURN_FALL_THROUGH


def _tx_attack_decision(*, finish_turn, held_plan, interaction_mode, npc_target, player_input, quest_world_before, resolve_intent, target_id):
    # An explicit hostile decision is already mechanically meaningful input.
    # Do not let a model reinterpret it as dialogue or an NPC interaction.
    # Target resolution above and resolve_intent() remain the existing combat
    # owners; this is only deterministic routing precedence.
    if (
        interaction_mode not in {"say", "ask_dm"}
        and held_plan is None  # a blow inside clauses held for the reading is still part of the plan
        and combat_lifecycle.is_attack_decision(game._session(), player_input)
    ):
        # The turn's own reading may name the weapon (Task 14's `weapon_word`): it goes only to the catalog (gear).
        read = getattr(game._session(), "_front_reply", None)
        word = read.get("weapon_word") if isinstance(read, dict) else None
        action_result = resolve_intent(
            {"intent": "attack", **({"weapon_word": word.strip()[:40]} if isinstance(word, str) and word.strip() else {})},
            player_input,
            npc_target=npc_target,
            target_id=target_id,
        )
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


def _tx_location_query(*, finish_turn, interaction_mode, npc_target, player_input):
    # An active conversation is not authority over the player's location.
    # Resolve only recognized location queries here; NPC dialogue, interaction
    # proposals and world-lore questions retain their existing routing.
    if (
        game._detect_query_type(player_input, npc_target) == "location"
        and not (npc_target and interaction_mode == "say")
    ):
        query_response = game._handle_query(player_input, "location", npc_target)
        action_result = {
            "action": "query",
            "status": "answered_from_campaign_state",
            "success": True,
            "query_type": "location",
            "state_changes": [],
            "direct_response": query_response,
        }
        return finish_turn(
            action_result, query_response,
            safety_handling="python_scene_response",
        )
    return game._TURN_FALL_THROUGH


def _tx_name_topic(*, finish_turn, npc_target, player_input, topic_name):
    if topic_name:
        answer = (
            f'{living_world.public_npc_name(npc_target)}, “{topic_name} derler,” diye yanıt verir.'
            if npc_target else f"Adı {topic_name}."
        )
        if npc_target:
            game.record_npc_interaction(npc_target, answer, player_input, npc_target)
        return finish_turn(
            {
                "action": "dialogue" if npc_target else "query",
                "status": "answered_smalltalk" if npc_target else "answered_from_campaign_state",
                "success": True,
                "npc_id": npc_target.get("id") if npc_target else None,
                "state_changes": [],
            },
            answer,
            safety_handling="python_scene_response",
        )
    return game._TURN_FALL_THROUGH


def _tx_attack_hint_no_target(*, combat, flags, interaction_mode, npc_target, player_input, selected_npc_target, world_state, world_subject_question):
    if not combat["active"] and (
        interaction_mode == "say"
        or not world_subject_question
        or local_dialogue.is_local_dialogue_input(player_input)
        or (game._npc_speech_enabled() and interaction_mode in {None, "do", "say"}
            and game.is_npc_dialogue_input(player_input))
        or game._is_spoken_to(player_input, selected_npc_target)
    ):
        npc_target = selected_npc_target
        if npc_target is not None:
            talk_mode.open(world_state, npc_target["id"], turn=flags.get("turn_index", 0))
    return npc_target


def _tx_attack_target_missing(*, finish_turn, target_id):
    if not isinstance(target_id, str) or not target_id:
        result = {
            "action": "attack",
            "status": "resolved",
            "success": False,
            "outcome": "invalid_target",
            "direct_response": "Seçtiğin kişi ya da şey artık burada görünmüyor.",
            "state_changes": [],
        }
        return finish_turn(result, result["direct_response"])
    return game._TURN_FALL_THROUGH


def _tx_planned_direct(*, finish_turn, planned_direct, player_input, quest_world_before, scene_plan, world_state):
    if isinstance(planned_direct, dict) and interaction_adventure.hint(player_input) != "plan":
        action_result = copy.deepcopy(planned_direct)
        if (
            "campaign_time" in world_state
            and scene_plan.get("action") in {"look", "presence"}
            and not (
                isinstance(world_state.get("journey"), dict)
                and world_state["journey"]["status"] != "ARRIVED"
            )
        ):
            now = world_state["campaign_time"]["elapsed_seconds"]
            observed = scheduled_events.process_events(
                world_state, now, now,
                observation={"kind": "look", "location_id": world_state["location"]},
            )
            if observed:
                action_result["direct_response"] = (
                    action_result.get("direct_response", "") + " "
                    + " ".join(event["summary"] for event in observed)
                ).strip()
        quest_transitions = game._session().evaluate_quest_events(
            quest_world_before, action_result
        )
        if quest_transitions:
            action_result["quest_outcomes"] = quest_transitions
        fallback_text = action_result.get("direct_response", "Çevredeki hareketliliği gözlüyorsun.")
        current_loc = world_state.get("location")
        locations = world_state.get("locations", {}) if isinstance(world_state.get("locations"), dict) else {}
        loc_record = (
            locations.get(current_loc, {})
            if isinstance(locations, dict)
            else {}
        )
        resolved_loc = (
            game.resolve_location_reference(current_loc)
            if not loc_record and isinstance(current_loc, str)
            else current_loc
        )
        if resolved_loc and resolved_loc != current_loc and isinstance(locations, dict):
            loc_record = locations.get(resolved_loc, {}) or loc_record

        current_kind = living_world.scene_kind(world_state, current_loc)
        resolved_kind = living_world.scene_kind(world_state, resolved_loc) if resolved_loc else "quiet"
        loc_type = str(loc_record.get("type", "")).casefold()
        loc_name = str(loc_record.get("name", "")).casefold()
        is_non_city = (
            current_kind in ("tavern", "wilderness", "building")
            or resolved_kind in ("tavern", "wilderness", "building")
            or loc_type in ("tavern", "wilderness", "forest", "inn", "building", "dungeon", "cave")
            or current_loc in ("tavern", "forest")
            or (isinstance(resolved_loc, str) and resolved_loc in ("tavern", "forest"))
            or bool(living_world._TAVERN_RE.search(loc_name))
        )

        anchor_id = (
            living_world.location_anchor_id(world_state, current_loc)
            or living_world.location_anchor_id(world_state, resolved_loc)
            if isinstance(locations, dict)
            else None
        )
        anchor_record = (
            locations.get(anchor_id, {})
            if isinstance(locations, dict) and anchor_id
            else {}
        )
        anchor_kind = living_world.scene_kind(world_state, anchor_id) if anchor_id else "quiet"
        world_meta = getattr(game._session(), "world_metadata", None)
        env_meta = world_meta.get("environment") if isinstance(world_meta, dict) else None

        is_city_scene = not is_non_city and (
            current_kind == "city"
            or resolved_kind == "city"
            or anchor_kind == "city"
            or game._is_canonical_city_id(current_loc)
            or game._is_canonical_city_id(resolved_loc)
            or game._is_canonical_city_id(anchor_id)
            or game._is_canonical_city_id(loc_record.get("id"))
            or game._is_canonical_city_id(loc_record.get("canonical_entity_id"))
            or game._is_canonical_city_id(loc_record.get("lore_entity_id"))
            or (
                isinstance(loc_record, dict)
                and loc_record.get("type") in (
                    "city", "town", "village", "settlement", "şehir", "district",
                    "street", "square", "market", "kasaba", "köy", "cadde", "sokak",
                    "meydan", "mahalle"
                )
            )
            or (
                isinstance(anchor_record, dict)
                and anchor_record.get("type") in (
                    "city", "town", "village", "settlement", "şehir", "district", "kasaba", "köy"
                )
            )
            or env_meta in ("city", "village", "town")
        )
        if (
            action_result.get("action") == "explore"
            and action_result.get("explore_type") == "observe"
            and action_result.get("status") == "observed"
            and action_result.get("direct_response")
        ):
            return finish_turn(
                action_result,
                fallback_text,
                quest_transitions,
                safety_handling="python_scene_response",
            )
        if action_result.get("action") == "explore" and not (scene_plan.get("action") == "look" and is_city_scene):
            return finish_turn(action_result, fallback_text, quest_transitions)
        if scene_plan.get("action") == "look" and game._look_scene_changed():
            action_result["scene_look"] = True
            return finish_turn(action_result, fallback_text, quest_transitions)
        return finish_turn(
            action_result,
            fallback_text,
            quest_transitions,
            safety_handling="python_scene_response",
        )
    return game._TURN_FALL_THROUGH


def _tx_enemy_turns(*, combat, finish_turn, world_state):
    if combat["active"] and combat["current_actor_id"] != "player":
        enemy_actions = game._resolve_enemy_turns_until_player()
        combat = game.ensure_combat_state()
        ended = not combat["active"]
        action_result = {
            "action": "attack",
            "success": False,
            "status": "resolved",
            "outcome": (
                "player_unconscious"
                if world_state.get("player_combat_status") == "unconscious"
                else "enemy_turn_resolved"
            ),
            "enemy_actions": enemy_actions,
            "enemy_action": enemy_actions[0] if enemy_actions else None,
            "combat_ended": ended,
            "end_reason": combat.get("end_reason") if ended else None,
            "current_actor_id": combat.get("current_actor_id"),
            "turn_owner": combat.get("current_actor_id"),
            "direct_response": (
                "Rakibin sırası tamamlandı; verdiğin hamle kullanılmadı. "
                "Şimdi kendi hamleni yeniden gönderebilirsin."
                if not ended
                else "Rakibin sırası tamamlandı ve karakterin çatışmada ilerleyemiyor."
            ),
        }
        return finish_turn(action_result, action_result["direct_response"])
    return game._TURN_FALL_THROUGH


def _tx_player_down(*, combat, finish_turn):
    if (
        combat["active"]
        and combat["current_actor_id"] == "player"
        and game._session().character.get("current_hp", 0) <= 0
    ):
        death = game.ensure_death_state()
        if death["stable"]:
            game._mark_combat_action_used("player")
            enemy_actions = []
            if not game._combat_end_if_decided():
                advanced, _, _ = game.advance_combat_turn()
                if advanced:
                    enemy_actions = game._resolve_enemy_turns_until_player()
            combat = game.ensure_combat_state()
            action_result = {
                "action": "attack",
                "success": False,
                "status": "resolved",
                "outcome": "player_unconscious",
                "enemy_actions": enemy_actions,
                "enemy_action": enemy_actions[0] if enemy_actions else None,
                "combat_ended": not combat["active"],
                "end_reason": combat.get("end_reason"),
                "direct_response": " ".join(
                    (f"Bilincin kapalı, kanın durdu; çatışma sensiz sürüyor. {game._enemy_exchange_text(enemy_actions)}").split()
                ),
            }
            resolution = game._death_resolution_from_actions(enemy_actions)
            if resolution:
                action_result["death_resolution"] = resolution
            return finish_turn(
                action_result, action_result["direct_response"], is_final=True
            )

        save_result = game._resolve_player_death_turn()
        if save_result is not None:
            enemy_actions = []
            combat = game.ensure_combat_state()
            # Match the scheduler's newly-stable boundary: preserve this
            # player slot rather than starting another enemy cycle.
            if game.ensure_death_state()["stable"]:
                game._combat_end_if_decided()
            elif save_result["outcome"] != "revived" and combat["active"] and combat["current_actor_id"] == "player":
                game._mark_combat_action_used("player")
                if not game._combat_end_if_decided():
                    advanced, _, _ = game.advance_combat_turn()
                    if advanced:
                        enemy_actions = game._resolve_enemy_turns_until_player()
            combat = game.ensure_combat_state()
            resolution = (
                save_result.get("death_resolution")
                or game._death_resolution_from_actions(enemy_actions)
            )
            action_result = {
                "action": "death_save",
                "success": save_result["outcome"] in (
                    "success",
                    "stable",
                    "revived",
                ),
                "status": "resolved",
                "outcome": save_result["outcome"],
                "death_save": save_result,
                "enemy_actions": enemy_actions,
                "enemy_action": enemy_actions[0] if enemy_actions else None,
                "combat_ended": not combat["active"],
                "end_reason": combat.get("end_reason"),
                "direct_response": game._death_save_line(save_result, enemy_actions, resolution),
            }
            if resolution:
                action_result["death_resolution"] = resolution
            return finish_turn(
                action_result, action_result["direct_response"], is_final=True
            )
    return game._TURN_FALL_THROUGH


def _tx_timed_sequence(*, finish_turn, interaction_mode, player_input, scene_plan, sleeping, world_state):
    if ("campaign_time" in world_state and not game.ensure_combat_state()["active"]
            and interaction_mode not in {"say", "ask_dm"}):
        # A stated sequence containing "wait" is a plan, not permission to run
        # its first step before the plan has been interpreted and confirmed.
        # A discovered venue entry is already committed by the scene owner.
        # "giriyorum" is also travel grammar; do not let that clock steal the entry.
        scene_direct = (
            scene_plan.get("direct_result")
            if isinstance(scene_plan, dict)
            else None
        )
        # Local entry and a completed return to its parent are already
        # committed. Do not let route travel replace them.
        local_scene_move = (
            isinstance(scene_direct, dict)
            and (
                scene_direct.get("action") == "enter"
                or (
                    scene_direct.get("action") == "exit"
                    and scene_direct.get("status") == "completed"
                )
            )
        )
        timed_result = (
            None
            if (interaction_adventure.hint(player_input) == "plan" and not sleeping) or local_scene_move
            else timed_gameplay.resolve_input(game._session(), player_input)
        )
        if timed_result is not None:
            return finish_turn(
                timed_result, timed_result["direct_response"], is_final=True
            )
    return game._TURN_FALL_THROUGH


def _tx_procedural_ids_before(*, procedural_entity_ids, scene_plan):
    if (
        isinstance(scene_plan, dict)
        and "procedural_entity_ids_before" in scene_plan
    ):
        # An empty set is a valid pre-materialization snapshot on a new scene.
        procedural_ids_before = set(
            scene_plan["procedural_entity_ids_before"]
        )
    else:
        procedural_ids_before = procedural_entity_ids()
    return procedural_ids_before


def _tx_smalltalk_response(*, action_id, experimental_dialogue_session, finish_turn, front_talk, interaction_mode, npc_target, player_input, smalltalk_response):
    if (
        smalltalk_response
        and isinstance(npc_target, dict)
        # BM Task 3: a plain-talk reading means the person answers by speech; these fixed lines are the fallback
        and talk_front.old_owner_allowed(
            front_talk, "personal" if local_dialogue.personal_answer(npc_target, player_input) else "small_talk")
        and (
            not experimental_dialogue_session
            or (interaction_mode != "say" and not local_dialogue.has_multiple_dialogue_clauses(
                player_input, npc_target
            ))
        )
    ):
        personal = (
            local_dialogue.personal_answer(npc_target, player_input)
            if isinstance(npc_target, dict)
            else None
        )
        conversation_start = game._is_conversation_start_input(player_input)
        action_result = {
            "action": "dialogue",
            "status": (
                "answered_personal_question" if personal
                else "conversation_started" if conversation_start
                else "answered_smalltalk"
            ),
            "success": True,
            "npc_id": npc_target["id"],
            **({
                "reality_category": personal[1]
            } if personal else {}),
            "state_changes": [],
        }
        game.record_npc_interaction(
            npc_target, smalltalk_response, player_input, npc_target
        )
        game._remember_owner_locked_tavern_focus(
            player_input, npc_target, action_id
        )
        if (
            personal
            or conversation_start
            or living_world.is_tavern_search(player_input)
            or game._is_local_place_question(player_input)
        ):
            return finish_turn(
                action_result,
                smalltalk_response,
                safety_handling="python_scene_response",
            )
        return finish_turn(
            action_result,
            smalltalk_response,
        )
    return game._TURN_FALL_THROUGH


def _tx_lore_gate(*, finish_turn, lore_gate, npc_target, player_input):
    if lore_gate:
        action_result = {
            "action": "dialogue",
            "status": "unverified",
            "success": False,
            "state_changes": [],
        }
        return finish_turn(
            action_result,
            game._unverified_lore_response(player_input, npc_target),
            safety_reason_code="UNVERIFIED_LORE_CLAIM",
            safety_handling="python_fallback",
        )
    return game._TURN_FALL_THROUGH


def _tx_place_recommendation_safety_input(*, lore_safety_input, npc_place_recommendation, npc_target, player_input):
    if npc_place_recommendation:
        # A resolved, visible addressee is not an unsupported lore entity.
        # Remove only that person/role from the lore scan; other named claims
        # in the same request remain subject to the ordinary fail-closed gate.
        lore_safety_input = game._lore_guard_text(player_input)
        for reference in (
            living_world.public_npc_name(npc_target),
            living_world.public_npc_role(npc_target),
        ):
            normalized_reference = game._lore_guard_text(reference or "")
            if normalized_reference:
                lore_safety_input = re.sub(
                    rf"(?<![a-z0-9]){re.escape(normalized_reference)}"
                    rf"[a-z0-9]*(?![a-z0-9])",
                    " ",
                    lore_safety_input,
                )
    return lore_safety_input


def _tx_npc_dialogue_route(*, answer_in_person, experimental_unverified_claim, interaction_mode, npc_place_recommendation, npc_target, player_input, spoken_reference):
    # Resolve dialogue ownership once, before the topical gate. The UI's
    # default do mode must not block a turn the speech owner would handle.
    npc_dialogue_route = bool(npc_target and (
        interaction_mode == "say"
        or spoken_reference
        or experimental_unverified_claim
        or answer_in_person
        or game._report_of_someone_else(player_input, npc_target)
        or npc_place_recommendation
        or game.is_npc_dialogue_input(player_input)
        or local_dialogue.personal_question_kind(player_input) == "local_work"  # "burada ... var mı" also reads as a look
        or game._is_short_conversation_continuation(player_input)
        or game._is_spoken_to(player_input, npc_target)
        or game._asked_of_the_one_at_hand(player_input, npc_target)
    ))
    return npc_dialogue_route


def _tx_supported_lore_response(*, finish_turn, lore_context, supported_lore_response):
    if supported_lore_response:
        diagnostics = lore_context.get("diagnostics", {}) if isinstance(lore_context, dict) else {}
        selected_ids = diagnostics.get("selected_fact_ids", []) if isinstance(diagnostics, dict) else []
        action_result = {
            "action": "dialogue",
            "status": "answered_from_loaded_lore",
            "success": True,
            "state_changes": [],
            "discovered_fact_ids": game._spoken_lore_fact_ids(
                lore_context, supported_lore_response, selected_ids,
            ),
        }
        return finish_turn(action_result, supported_lore_response)
    return game._TURN_FALL_THROUGH


def _tx_work_answer(*, finish_turn, npc_target, work_answer, world_state):
    # A person who is here answers for themselves on the speech path.
    if work_answer and not isinstance(npc_target, dict):
        response = game._overheard_work(world_state) or work_answer[0]
        action_result = {
            "action": "local_inquiry",
            "status": "answered_without_offer",
            "success": True,
            "reality_category": work_answer[1],
            "state_changes": [],
        }
        return finish_turn(
            action_result,
            response,
            safety_handling="python_scene_response",
        )
    return game._TURN_FALL_THROUGH


def _tx_quest_availability(*, finish_turn, interaction_mode, player_input, world_state):
    if (
        interaction_mode not in {"say", "ask_dm"}
        and local_dialogue.quest_availability_question(player_input)
    ):
        active_quests = [
            quest for quest in world_state.get("quests", [])
            if isinstance(quest, dict) and quest.get("status") == "accepted"
        ]
        offers = game._session().quest_offers()
        titles = []
        for quest in [*active_quests, *offers]:
            title = quest.get("title") if isinstance(quest, dict) else None
            if isinstance(title, str) and title.strip() and title.strip() not in titles:
                titles.append(title.strip())
        if titles:
            message = "Üstlenebileceğin işler şunlar: " + ", ".join(titles) + "."
        else:
            message = "Bu bölgede sana sunulmuş etkin bir görev yok."
        action_result = {
            "action": "quest_inquiry",
            "status": "answered_from_campaign_state",
            "success": True,
            "state_changes": [],
        }
        return finish_turn(action_result, message, is_final=True)
    return game._TURN_FALL_THROUGH


def _tx_npc_query(*, finish_turn, npc_target, player_input):
    if isinstance(npc_target, dict) and isinstance(npc_target.get("id"), str):
        query_type = game._detect_query_type(player_input, npc_target)
        if query_type == "npc_identity" and local_dialogue.is_identity_only_question(player_input, npc_target):
            query_response = game._handle_query(
                player_input, query_type, npc_target
            )
            if query_response:
                action_result = {
                    "action": "query",
                    "status": "answered_from_campaign_state",
                    "success": True,
                    "query_type": query_type,
                    "npc_id": npc_target["id"],
                    "state_changes": [],
                    "direct_response": query_response,
                }
                game.record_npc_interaction(
                    npc_target, query_response, player_input, npc_target
                )
                return finish_turn(
                    action_result,
                    query_response,
                    safety_handling="python_scene_response",
                )
    return game._TURN_FALL_THROUGH


def _tx_historical_name_query(*, finish_turn, npc_target, player_input):
    if (
        isinstance(npc_target, dict)
        and game._is_historical_player_name_query(player_input)
        and not game._explicit_player_name_disclosure(player_input)
    ):
        remembered_name = (
            game._historical_player_name_from_npc_memory(npc_target, player_input)
            or game._historical_player_name_from_claims(
                npc_target,
                player_input,
                getattr(game._session(), "_supported_player_claims", None),
            )
        )
        npc_name = living_world.public_npc_name(npc_target)
        is_hitap = bool(re.search(r"\b(?:ad[ıi]mla|ismimle)\s+hitap\b", game._normalize_turkish_typos(str(player_input).casefold())))
        if remembered_name:
            if is_hitap:
                response = f'{npc_name}, “Elbette, {remembered_name}. Sana adınla hitap edebilirim,” der.'
            else:
                response = f'{npc_name}, “Evet, adının {remembered_name} olduğunu hatırlıyorum,” der.'
        else:
            if is_hitap:
                response = f'{npc_name}, “Bana henüz adını söylemedin; adını bilmeden sana adınla hitap edemem,” der.'
            else:
                response = f'{npc_name}, “Bana henüz adını söylemedin; adını bilmiyorum,” der.'
        action_result = {
            "action": "dialogue",
            "status": "answered_from_npc_memory",
            "success": True,
            "npc_id": npc_target.get("id"),
            "reality_category": (
                local_dialogue.PROCEDURAL_PERSONAL_FACT
                if remembered_name
                else local_dialogue.CAMPAIGN_FACT
            ),
            "state_changes": [],
        }
        game.record_npc_interaction(
            npc_target, response, player_input, npc_target
        )
        return finish_turn(
            action_result,
            response,
            safety_reason_code=(
                "NPC_MEMORY_SUPPORTED_PLAYER_NAME"
                if remembered_name
                else "NPC_MEMORY_UNSUPPORTED_CLAIM"
            ),
            safety_handling="python_memory_response",
        )
    return game._TURN_FALL_THROUGH
