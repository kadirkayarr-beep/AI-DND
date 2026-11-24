import living_world
import refusals
import timed_gameplay
import combat_lifecycle
import money_owner
import game


def _fx_inventory_reply(*, before, inventory_reply, result):
    if inventory_reply:
        if "envanterden yere taşındı" in inventory_reply:
            reply = "Kılıç envanterinden çıkar ve yerde durur."
        elif "Yerdeki Kılıç envantere alındı" in inventory_reply:
            reply = "Yerdeki Kılıç yerden alınır ve yeniden envanterine eklenir."
        elif "Yerde alınabilecek" in inventory_reply:
            reply = "Yerde alabileceğin bir kılıç yok."
        else:
            reply = "Kılıç envanterinde değil; yerde duruyor."
        result.update({
            "action": "inventory",
            "status": "resolved",
            "direct_response": reply,
            "state_changes": game._changed_state_fields(before),
        })
        return result
    return game._TURN_FALL_THROUGH


def _fx_skill_check(*, before, check_evidence, check_feature, difficulty, intent, intent_type, npc_target, player_input, result, skill):
    if skill in game.SKILLS:
        dc = game.DIFFICULTY_DC.get(difficulty, game.DIFFICULTY_DC["medium"])
        ability = "strength" if check_feature == 'primal_knowledge' else game.SKILLS[skill]
        trait_state = game._species_trait_state()
        check_result = game.perform_skill_check(
            skill,
            dc,
            game._session().character["modifiers"],
            game._session().character["proficient_skills"],
            game._session().character["proficiency_bonus"],
            expertise_skills=game._session().character.get("expertise_skills", ()),
            **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {}),
            advantage=(
                ability == "strength"
                and trait_state.get("large_form_turns_remaining", 0) > 0
            ),
        )
        game.apply_check_outcome_to_world_state(player_input, check_result)
        haggle_note = money_owner.haggle(game._session(), npc_target or game._active_interlocutor(), check_result,
                                         negotiation=intent.get("price_negotiation"), player_input=player_input)
        if haggle_note:
            result["haggle_note"] = haggle_note
        outcome = game._skill_result_category(check_result.get("result"))
        result.update({
            "action": "skill_check",
            "intent": intent_type,
            "skill": check_result["skill"],
            "ability": check_result["ability"],
            "dice": check_result["dice"],
            # Advantage from the character itself (Remarkable Athlete) rolls two dice too: the answer must carry both.
            **({"dice_rolls": check_result["dice_rolls"]}
               if check_feature is not None or check_result["advantage"] != check_result["disadvantage"] else {}),
            **({"tactical_mind_roll": check_result["tactical_mind_roll"]} if check_feature == "tactical_mind" else {}),
            "modifier": check_result["modifier"],
            "proficiency_bonus": check_result["proficiency_bonus"],
            "expertise": check_result["expertise"],
            "advantage": check_result["advantage"],
            "disadvantage": check_result["disadvantage"],
            "action_id": check_result["resolution"].get("action_id"),
            "resolution_id": check_result["resolution"].get("resolution_id"),
            "resolution": check_result["resolution"],
            "total": check_result["total"],
            "dc": check_result["dc"],
            "outcome": outcome,
            "success": outcome == "success",
            "status": "resolved",
            "state_changes": game._changed_state_fields(before),
            "target_type": "door" if ("kapı" in player_input.casefold() or "kilit" in player_input.casefold()) else None,
        })
        if check_result["skill"] in {"Perception", "Investigation", "Survival"}:
            findings = game._inspection_findings(player_input, outcome)
            if findings:
                # LR00-P2: the receipt names what was looked at and what was
                # (or was not) found; narration must agree with it.
                result["inspection"] = findings
        game._print_skill_result(check_result, difficulty)
        return result
    return game._TURN_FALL_THROUGH


def _fx_check_skill(*, deterministic, explore_type, intent_type, player_input, skill):
    if deterministic and deterministic.get("action_type") == "check":
        skill = deterministic.get("skill")
    else:
        inferred_skill = {
            "stealth": "Stealth",
            "perception": "Perception",
            "investigation": "Investigation",
            "search": "Investigation",
            **game.SKILL_INTENT_TO_SKILL,
        }.get(intent_type)
        if intent_type == "explore" and explore_type in {"inspect", "search"}:
            inferred_skill = "Investigation"
        if inferred_skill and (
            not game.is_npc_dialogue_input(player_input)
            or intent_type in {"perception", "investigation", "search", "stealth"}
        ):
            skill = inferred_skill
    return skill


def _fx_travel(*, before, combat_was_active, intent, intent_type, result, world_state):
    if intent_type == "travel":
        if game.ensure_combat_state()["active"]:
            raise combat_lifecycle.CombatRequestError("combat_travel", "Normal travel cannot leave active combat.", 400)
        reference = intent.get("target", {}).get("reference", "")
        pending = world_state.get("flags", {}).get("pending_destination")
        if (not reference or reference in ("orada", "oraya", "içeri")) and pending:
            reference = pending
        if not reference:
            result.update({"success": False, "status": "clarification", "direct_response": "Nereye gittiğini söylemedin."})
            return result
        previous = world_state.get("location")
        target_id = game.resolve_location_reference(reference)
        result.update({
            "action": "travel",
            "completion": intent.get("completion", "completed"),
            "target_reference": str(reference),
            "target": target_id,
            "previous_location": previous,
            "success": None,
            "status": "awaiting_proposal" if not target_id else "ready",
        })
        flags = world_state.setdefault("flags", {})
        if not target_id:
            # A changed target invalidates any older pending destination.
            flags["pending_destination"] = None
            result["proposal_required"] = True
        elif result["completion"] == "intended":
            flags["pending_destination"] = target_id
            result.update({"status": "intended", "state_changes": ["flags.pending_destination"]})
        else:
            if previous in world_state.get("locations", {}):
                timed = timed_gameplay.start_travel(game._session(), target_id)
                result.update(timed)
                return result
            changed = game.commit_location_change(target_id)
            if not changed and game._venue_entry_door(world_state, previous, target_id):
                door = game._venue_entry_door(world_state, previous, target_id)
                result.update({
                    "success": False,
                    "status": "blocked",
                    "direct_response": (
                        game._locked_door_refusal(door)
                    ),
                    "state_changes": [],
                })
                return result
            flags["pending_destination"] = None
            result.update({
                "success": True,
                "status": "completed",
                "new_location": target_id,
                "state_changes": (["player.location"] if changed else []) + ["flags.pending_destination"],
            })
        if combat_was_active and world_state.get("location") != previous:
            result.update(combat_ended=True, end_reason="location_changed", combat=game._combat_snapshot())
            result["state_changes"] = game._changed_state_fields(before)
        return result
    return game._TURN_FALL_THROUGH


def _fx_query(*, npc_target, player_input, query_type, result):
    if query_type:
        query_response = game._handle_query(player_input, query_type, npc_target)
        if query_response:
            result.update({"action": "query", "query_type": query_type, "direct_response": query_response})
            if (
                query_type == "npc_identity"
                and isinstance(npc_target, dict)
                and isinstance(npc_target.get("id"), str)
            ):
                result["npc_id"] = npc_target["id"]
            return result
    return game._TURN_FALL_THROUGH


def _fx_combat_interrupt(*, before, combat_was_active, intent_type, result):
    if combat_was_active and intent_type not in {
        "attack",
        "combat",
        "dialogue",
        "query",
        "unknown",
        "narrative",
    }:
        result.update(
            action="combat_action",
            success=False,
            status="unsupported",
            outcome="unsupported_combat_action",
            direct_response=refusals.text_for("unsupported_action"),
        )
        return game._finish_combat_result(result, before)
    return game._TURN_FALL_THROUGH


def _fx_negated_attack(*, intent_type, player_input, result):
    if (
        intent_type in {"attack", "combat"}
        and game._is_explicitly_negated_attack(player_input)
    ):
        result.update(
            action="narrative",
            success=None,
            status="not_executed",
            outcome="negated_action",
            direct_response="Elin silahında kalıyor; kimseye vurmuyorsun.",
        )
        return result
    return game._TURN_FALL_THROUGH


def _fx_door_inspection(*, player_input, result):
    if game._is_door_inspection_request(player_input) and game._current_door() is None:
        result.update({
            "action": "inspect",
            "success": False,
            "status": "unresolved",
            "target_type": "door",
            "target_id": None,
            "direct_response": (
                "İçeride inceleyebileceğin belirgin bir kapı göremiyorsun. "
                "İstersen başka bir ayrıntıya bakabilirsin."
            ),
        })
        return result
    return game._TURN_FALL_THROUGH


def _fx_attack_combat_end(*, enemy_actions, result):
    if game._combat_end_if_decided():
        combat = game.ensure_combat_state()
        result.update(
            combat_ended=True,
            end_reason=combat.get("end_reason"),
        )
    else:
        advanced, _, _ = game.advance_combat_turn()
        if advanced:
            enemy_actions.extend(game._resolve_enemy_turns_until_player())
        combat = game.ensure_combat_state()
        if enemy_actions:
            result["enemy_actions"] = enemy_actions
            result["enemy_action"] = enemy_actions[0]
        if not combat["active"]:
            result.update(
                combat_ended=True,
                end_reason=combat.get("end_reason"),
            )
    return combat


def _fx_attack_out_of_turn(*, before, combat, result):
    if combat["current_actor_id"] != "player":
        result.update(
            success=False,
            status="out_of_turn",
            outcome="out_of_turn",
            current_actor_id=combat["current_actor_id"],
            turn_owner=combat["current_actor_id"],
            direct_response="Bu hamle için sıra sende değil.",
        )
        return game._finish_combat_result(result, before)
    return game._TURN_FALL_THROUGH


def _fx_attack_started(*, before, enemy_actions, result, started, target_npc, world_state):
    if started:
        import bold_acts
        bold_acts.attacked(game._session(), target_npc)
        start_result = game.start_combat(target_npc)
        result["combat_id"] = start_result["combat_id"]
        if start_result["current_actor_id"] != "player":
            # Won initiative: these come before the player's move (told first, not as counter-attacks).
            enemy_actions.extend({**action, "before_player": True}
                                 for action in game._resolve_enemy_turns_until_player())
            if (
                game._session().character["current_hp"] <= 0
                or world_state["player_combat_status"] == "unconscious"
            ):
                result.update(
                    success=False,
                    status="resolved",
                    outcome="player_unconscious",
                    combat_started=True,
                    enemy_actions=enemy_actions,
                    enemy_action=enemy_actions[-1] if enemy_actions else None,
                    direct_response="Çatışma başladı; rakiplerin sırası önce geldi ve bilincini kaybettin.",
                )
                if enemy_actions:
                    result["enemy_action"] = enemy_actions[0]
                return game._finish_combat_result(result, before)
    return game._TURN_FALL_THROUGH


def _fx_attack_no_target(*, before, npc_target, result, target_id, target_npc):
    if not target_npc:
        candidate_names = [
            living_world.public_npc_name(npc)
            for npc in game.active_npcs()
            if isinstance(npc, dict)
        ]
        if candidate_names and target_id is None and npc_target is None:
            result.update(
                success=False,
                status="clarification",
                outcome="missing_target",
                direct_response=(
                    "Kime saldırmak istiyorsun? Yakındaki kişiler: "
                        f"{', '.join(candidate_names[:4])}."
                ),
            )
        else:
            result.update(
                success=False,
                outcome="no_target",
                direct_response="Bu sahnede saldırabileceğin bir hedef yok.",
            )
        return game._finish_combat_result(result, before)
    return game._TURN_FALL_THROUGH


def _fx_attack_ambiguous_target(*, before, result, target_npc):
    if target_npc == "ambiguous":
        candidate_names = [
            living_world.public_npc_name(npc)
            for npc in game.active_npcs()
            if isinstance(npc, dict)
        ]
        clarification = "Hangi hedefe saldırıyorsun?"
        if candidate_names:
            clarification += f" Yakında {living_world.public_scene_people(game.active_npcs()[:4])} var."
        result.update(success=False, status="clarification", outcome="ambiguous_target",
                      direct_response=clarification)
        return game._finish_combat_result(result, before)
    return game._TURN_FALL_THROUGH
