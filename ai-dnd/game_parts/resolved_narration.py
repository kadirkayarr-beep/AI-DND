import re
import talk_mode
import incidents.hooks as incident_hooks
import game

def _narrate_resolved_turn(resolved_turn: "ResolvedTurn", player_input, messages, target_id):  # noqa: F821
    if messages is None:
        messages = resolved_turn.messages or game._session().messages

    npc_target = resolved_turn.npc_target
    if npc_target is None and isinstance(resolved_turn.action_result, dict):
        npc_id = resolved_turn.action_result.get("npc_id")
        if npc_id:
            for npc in game._session().world_state.get("npcs", []):
                if isinstance(npc, dict) and npc.get("id") == npc_id:
                    npc_target = npc
                    break

    lore_context = resolved_turn.lore_context
    if lore_context is None:
        injected = getattr(game._session(), "lore_authority_context", None)
        lore_context = game._prepare_lore_authority_context(injected)

    narration_only = not (
        resolved_turn.allow_new_npcs
        or resolved_turn.allow_new_features
        or resolved_turn.allow_new_shops
        or resolved_turn.allow_new_locations
    )
    emergence = incident_hooks.before_narration(
        game._session(), action_result=resolved_turn.action_result, player_text=player_input,
        location_changed=bool(resolved_turn.expected_location_change),
    )
    narration_model_calls = 1
    from api.model_phase import resolved_narration_scope
    proposes_place = game._may_propose_local_place(resolved_turn, player_input)
    packet = game._rn_build_packet(lore_context=lore_context, messages=messages, narration_only=narration_only, npc_target=npc_target, player_input=player_input, proposes_place=proposes_place, resolved_narration_scope=resolved_narration_scope, resolved_turn=resolved_turn)
    packet = packet if isinstance(packet, dict) else {}
    if proposes_place:
        resolved_turn.action_result["verified_world_updates"] = {
            "create_locations": game._accepted_local_place(packet, resolved_turn.action_result),
        }
        packet["world_updates"] = {}

    rejected_scene_detail_proposal = False
    rejected_scene_detail_proposal = game._rn_rejected_scene_detail(packet=packet, rejected_scene_detail_proposal=rejected_scene_detail_proposal, resolved_turn=resolved_turn)

    proposal_snapshot = game._world_snapshot()
    if packet.get("valid_response") and any((packet.get("world_updates") or {}).values()):
        packet["valid_response"] = False
        packet["narration"] = resolved_turn.fallback_response
        packet["fallback_reason_code"] = "MODEL_WORLD_PROPOSAL_REJECTED"
    game._rn_not_narration_only(narration_only=narration_only, packet=packet, player_input=player_input, proposal_snapshot=proposal_snapshot, proposes_place=proposes_place, resolved_turn=resolved_turn)

    # A narration-only turn cannot propose, so a marker there names nothing new;
    # the sentence stays and only the marker goes.
    packet["narration"] = game._repair_internal_marks(packet.get("narration"))
    claims = packet.get("lore_claims", [])
    if (narration_only and not claims and resolved_turn.npc_target is None
            and isinstance(packet.get("narration"), str)):
        # The narration-only prompt asks for no citations; a narration that only
        # restates public official facts is bound to them here instead.
        from api.lore_authority.claim_authorization import exact_narration_evidence_ids
        exact_ids = exact_narration_evidence_ids(packet["narration"], lore_context)
        if exact_ids:
            claims = exact_ids
            packet["lore_claims"] = exact_ids
    lore_unsupported = not game._lore_claims_are_supported(claims, lore_context)
    lore_unsupported = game._rn_lore_unsupported(claims=claims, lore_context=lore_context, lore_unsupported=lore_unsupported, packet=packet)
    if lore_unsupported:
        packet["valid_response"] = False
        packet["fallback_reason_code"] = "UNVERIFIED_LORE_CLAIM"

    if (resolved_turn.action_result.get("action") == "shop_setup"
            and resolved_turn.action_result.get("status") == "created"
            and packet.get("narration") != resolved_turn.action_result.get("direct_response")):
        packet["valid_response"] = False
        packet["fallback_reason_code"] = packet.get("fallback_reason_code") or "UNGROUNDED_SHOP_SCENE"
        packet["narration"] = resolved_turn.action_result["direct_response"]

    import resolved_presentation
    bounded_check = resolved_presentation.bounded_rebuilding_check(
        resolved_turn.action_result, player_input, lore_context
    )
    if bounded_check and packet.get("narration") != bounded_check:
        packet["valid_response"] = False
        packet["fallback_reason_code"] = packet.get("fallback_reason_code") or "UNGROUNDED_RESOLVED_CHECK"
        packet["narration"] = bounded_check
        resolved_turn.fallback_response = bounded_check

    fallback_code = packet.get("fallback_reason_code") or resolved_turn.safety_reason_code
    finalized_narration = game._rn_finalize(fallback_code=fallback_code, narration_only=narration_only, npc_target=npc_target, packet=packet, player_input=player_input, resolved_turn=resolved_turn, target_id=target_id)
    if resolved_turn.action_result.get("action") == "narrative_spell" and isinstance(packet.get("item_claims"), list):
        # D-067: the cast moved nothing, so a thing the narrator says changed hands is never committed: its sentence
        # leaves first (the rest of the line stays), and a line that was all claim is the Python line.
        import pocket
        for claim in packet["item_claims"]:
            finalized_narration = pocket.without_claim(game._session().world_state, claim, finalized_narration)
        finalized_narration = finalized_narration or resolved_turn.fallback_response
    import spell_effects
    if (resolved_turn.action_result.get("action") == "narrative_spell"
            and spell_effects.claims_state_change(finalized_narration)):
        # 4C.5: the engine wrote only the spell fact; a line claiming coin, an item, healing or damage is not shown.
        packet["valid_response"] = False
        packet["fallback_reason_code"] = "NARRATIVE_SPELL_STATE_CLAIM"
        finalized_narration = resolved_turn.fallback_response
    finalized_narration = game._rn_money_claim_guard(finalized_narration=finalized_narration, npc_target=npc_target, packet=packet, player_input=player_input, resolved_turn=resolved_turn)
    if rejected_scene_detail_proposal:
        finalized_narration = resolved_turn.fallback_response
    if (
        resolved_turn.action_result.get("scene_look")
        and getattr(game._session(), "last_narration_safety", {}).get("handling") not in ("accepted", "repaired")
    ):
        finalized_narration = resolved_turn.fallback_response
    finalized_narration = game._keep_people_in_look(finalized_narration, resolved_turn.action_result)
    finalized_narration = game._states_the_failed_check(finalized_narration, resolved_turn.action_result, player_input)
    if game._narration_scene_type(resolved_turn.action_result) != "conversation":
        finalized_narration = game._singular_narrator(finalized_narration)

    final_dict = resolved_turn.raw_result
    final_dict["narration"] = finalized_narration

    safety_diag = getattr(game._session(), "last_narration_safety", {}) or {}
    validation_result = safety_diag.get("handling", "accepted")
    fallback_reason = safety_diag.get("reason_code") or packet.get("fallback_reason_code")

    shown_player_line = packet.get("player_line")
    game._rn_scene_detail_check(final_dict=final_dict, packet=packet, player_input=player_input, rejected_scene_detail_proposal=rejected_scene_detail_proposal, shown_player_line=shown_player_line, validation_result=validation_result)

    if validation_result in ("python_memory_response", "python_memory_fallback"):
        narration_source = "python_memory_response"
    elif validation_result in ("accepted", "repaired") and packet.get("valid_response", True) and packet.get("narration"):
        narration_source = "qwen"
    else:
        narration_source = "deterministic_fallback"

    if narration_source == "qwen":
        game._keep_town_portrait(resolved_turn.action_result, finalized_narration)

    intent_calls = resolved_turn.intent_model_calls
    total_calls = intent_calls + narration_model_calls + emergence["model_calls"]

    game._rn_engine_event_evidence(fallback_reason=fallback_reason, final_dict=final_dict, intent_calls=intent_calls, narration_model_calls=narration_model_calls, narration_source=narration_source, resolved_turn=resolved_turn, total_calls=total_calls, validation_result=validation_result)

    return final_dict


def _rn_engine_event_evidence(*, fallback_reason, final_dict, intent_calls, narration_model_calls, narration_source, resolved_turn, total_calls, validation_result):
    if "_engine_event_evidence" in final_dict:
        before_set = final_dict["_engine_event_evidence"].pop("_procedural_ids_before", set())
        final_dict["_engine_event_evidence"]["procedural_entity_ids"] = sorted(
            game._current_procedural_entity_ids() - before_set
        )
        final_dict["_engine_event_evidence"]["telemetry"] = {
            "intent_model_calls": intent_calls,
            "narration_model_calls": narration_model_calls,
            "total_model_calls": total_calls,
            "intent_source": resolved_turn.intent_source,
            "narration_source": narration_source,
            "fallback_reason": fallback_reason,
            "narration_validation_result": validation_result,
            "resolved_action_type": (
                resolved_turn.action_result.get("action", "unknown")
                if isinstance(resolved_turn.action_result, dict)
                else "unknown"
            ),
        }


def _rn_scene_detail_check(*, final_dict, packet, player_input, rejected_scene_detail_proposal, shown_player_line, validation_result):
    if (
        shown_player_line
        and packet.get("valid_response")
        and packet.get("narration")
        and not rejected_scene_detail_proposal
        and validation_result in ("accepted", "repaired")
    ):
        # The player's own words are a separate, attributed segment, never NPC speech.
        import npc_speech_boundary
        body = npc_speech_boundary.strip_player_quote(
            final_dict["narration"], player_input
        )
        final_dict["narration"] = (
            f"Sen: “{shown_player_line}”\n\n{body}".strip()
            if body else f"Sen: “{shown_player_line}”"
        )


def _rn_money_claim_guard(*, finalized_narration, npc_target, packet, player_input, resolved_turn):
    if game._narrated_money_can_lie(resolved_turn.action_result) and isinstance(packet.get("item_claims"), list):
        # Settled on the line the player will read: a sentence the safety pass took leaves no item behind.
        import pocket
        import town_knowledge
        try:
            for claim in packet["item_claims"][:2]:
                finalized_narration = pocket.settle_claim(game._session(), claim, finalized_narration, npc_target,
                                                          line=player_input)[0]
        except Exception:
            town_knowledge.log_failure()
        finalized_narration = finalized_narration or pocket.EMPTY_HANDED
    return finalized_narration


def _rn_finalize(*, fallback_code, narration_only, npc_target, packet, player_input, resolved_turn, target_id):
    finalized_narration = game.finalize_narration(
        packet.get("narration"),
        player_input,
        npc_target=npc_target,
        action_result=resolved_turn.action_result,
        fallback_reason_code=fallback_code,
        target_id=target_id or resolved_turn.target_id,
        resolved_fallback_response=(
            resolved_turn.fallback_response if narration_only else None
        ),
    )
    return finalized_narration


def _rn_lore_unsupported(*, claims, lore_context, lore_unsupported, packet):
    if not lore_unsupported and game._narration_has_unsupported_lore_claim(
        packet.get("narration"), claims, lore_context, game._session().world_state,
    ):
        # Repair before replacing: keep every sentence the guard accepts.
        repaired_lore = game._repair_unsupported_lore_narration(
            packet.get("narration"), claims, lore_context, game._session().world_state,
        )
        if repaired_lore:
            packet["narration"] = repaired_lore
        else:
            lore_unsupported = True
    return lore_unsupported


def _rn_not_narration_only(*, narration_only, packet, player_input, proposal_snapshot, proposes_place, resolved_turn):
    if not narration_only:
        # Rejected narrator proposals must never become canonical world state.
        # Only updates verified by the action resolver may enter this path.
        raw_updates = (
            resolved_turn.action_result.get("verified_world_updates", {})
            if isinstance(resolved_turn.action_result.get("verified_world_updates"), dict)
            else {}
        )
        if resolved_turn.allow_new_shops:
            raw_updates = {"create_shops": raw_updates.get("create_shops", [])}
        is_assertion = game.is_player_world_assertion(player_input) and not resolved_turn.allow_new_shops

        # Location proposals are validated and committed before the player location changes.
        location_updates = game.validate_world_updates(
            raw_updates,
            allow_new_locations=resolved_turn.allow_new_locations and not is_assertion,
        )
        if resolved_turn.allow_new_locations and location_updates.get("create_locations"):
            import heard_rumours
            expected = heard_rumours.base_name(resolved_turn.action_result.get("target_reference", "")).casefold().strip(" .,!?:;\"'")
            expected_words = re.findall(r"[a-z0-9çğıöşü]+", expected)
            matching = []
            for proposal in location_updates["create_locations"]:
                candidates = [proposal.get("name", ""), *proposal.get("aliases", [])]
                candidate_words = [re.findall(r"[a-z0-9çğıöşü]+", candidate.casefold()) for candidate in candidates]
                exact_or_contained = any(
                    expected == " ".join(words)
                    or bool(expected_words and any(
                        words[index:index + len(expected_words)] == expected_words
                        for index in range(max(0, len(words) - len(expected_words) + 1))
                    ))
                    for words in candidate_words
                )
                if exact_or_contained:
                    original_name = proposal.get("name", "")
                    if original_name.casefold() != expected:
                        aliases = list(proposal.get("aliases", []))
                        if original_name and original_name not in aliases:
                            aliases.append(original_name)
                        proposal["aliases"] = aliases[:8]
                        proposal["name"] = resolved_turn.action_result.get("target_reference", original_name)
                    matching.append(proposal)
            location_updates["create_locations"] = matching[:1]
        if location_updates.get("create_locations"):
            game.merge_world_updates({"create_locations": location_updates["create_locations"]})
            if proposes_place:
                game._settle_local_place(resolved_turn.action_result)
        if resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "awaiting_proposal":
            game._commit_travel_action(resolved_turn.action_result)
            if (
                proposes_place
                and resolved_turn.action_result.get("status") not in ("failed", "intended")
                and game._session().world_state.get("location") != resolved_turn.action_result.get("target")
                and resolved_turn.action_result.get("direct_response")
            ):
                # Stopped on the way: the narrator wrote before the walk, so its arrival is untrue.
                packet["narration"] = resolved_turn.action_result["direct_response"]

        # Validate NPC/feature/shop proposals only after any accepted location exists.
        validated_updates = game.validate_world_updates(
            raw_updates,
            allow_new_npcs=resolved_turn.allow_new_npcs and not is_assertion,
            allow_new_features=resolved_turn.allow_new_features and not is_assertion,
            allow_new_shops=resolved_turn.allow_new_shops and not is_assertion,
        )
        if resolved_turn.allow_new_shops and not validated_updates.get("create_shops"):
            resolved_turn.action_result.update(
                success=False,
                status="proposal_rejected",
                direct_response=(
                    "Etrafına bakınıyorsun ama şu an kapısı açık bir dükkân "
                    "göremiyorsun."
                ),
            )
            packet["valid_response"] = False
            packet["narration"] = resolved_turn.action_result["direct_response"]
        else:
            created_npcs = game.merge_world_updates(validated_updates) if not is_assertion else []
            if resolved_turn.allow_new_shops and validated_updates.get("create_shops"):
                resolved_turn.action_result.update(success=True, status="created")
                resolved_turn.action_result.setdefault("state_changes", []).append("world.shops")
                packet["narration"] = (
                    "Bu kampanyada mevcut konumda tek bir yerel dükkân ve onu işleten "
                    "bir dükkâncı kaydedildi."
                )
                packet["lore_claims"] = []
            flags = game._session().world_state.setdefault("flags", {})
            if len(created_npcs) == 1:
                talk_mode.open(game._session().world_state, created_npcs[0].get("id"), turn=flags.get("turn_index", 0))

            accepted_proposal_keys, rejected_proposal_names = game._bind_world_update_mentions(
                raw_updates,
                location_updates,
                validated_updates,
                game._session().world_state,
            )
            if isinstance(packet.get("narration"), str):
                packet["narration"] = game._filter_unaccepted_proposal_mentions(
                    packet["narration"],
                    accepted_proposal_keys,
                    rejected_proposal_names,
                )

        if resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "failed":
            packet["valid_response"] = False
            packet["narration"] = game._fallback_for_action_result(player_input, resolved_turn.action_result)

        proposal_changes = game._changed_state_fields(proposal_snapshot)
        resolved_turn.action_result["state_changes"] = list(dict.fromkeys(
            resolved_turn.action_result.get("state_changes", []) + proposal_changes
        ))

        if resolved_turn.quest_world_before and resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "completed":
            post_travel_quests = game._session().evaluate_quest_events(
                resolved_turn.quest_world_before, resolved_turn.action_result
            )
            if post_travel_quests:
                resolved_turn.action_result["quest_outcomes"] = post_travel_quests


def _rn_rejected_scene_detail(*, packet, rejected_scene_detail_proposal, resolved_turn):
    if isinstance(resolved_turn.action_result, dict):
        verified_updates = resolved_turn.action_result.get(
            "verified_world_updates", {}
        )
        verified_features = (
            verified_updates.get("create_features", [])
            if isinstance(verified_updates, dict)
            else []
        )
        if (
            resolved_turn.action_result.get("scene_detail_proposal_submitted")
            and not verified_features
        ):
            rejected_scene_detail_proposal = True
            packet["valid_response"] = False
            packet["narration"] = resolved_turn.fallback_response
            packet["fallback_reason_code"] = "UNVERIFIED_SCENE_DETAIL_PROPOSAL"
    return rejected_scene_detail_proposal


def _rn_build_packet(*, lore_context, messages, narration_only, npc_target, player_input, proposes_place, resolved_narration_scope, resolved_turn):
    with resolved_narration_scope(narration_only):
        packet = game.ask_dungeon_master(
            messages,
            player_input,
            allow_new_npcs=resolved_turn.allow_new_npcs and not proposes_place,
            allow_new_features=resolved_turn.allow_new_features and not proposes_place,
            npc_target=npc_target,
            world_entry=resolved_turn.expected_location_change,
            action_result=resolved_turn.action_result,
            allow_new_locations=resolved_turn.allow_new_locations,
            return_details=True,
            allow_new_shops=resolved_turn.allow_new_shops,
            narration_only=not proposes_place,
            lore_context=lore_context,
            scene_plan=resolved_turn.scene_plan,
        )
    return packet
