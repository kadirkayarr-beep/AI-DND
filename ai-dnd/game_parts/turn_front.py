import game
import action_economy
import adventure.play as adventure_play
import combat_lifecycle
import copy
import held_weapon
import interaction_adventure
import json
import living_world
import money_owner
import monster_sense
import re
import refusals
import sys
import timed_gameplay
import weapon_attack


def _has_session():
    return game._ACTIVE_SESSION.get(None) is not None

def _carry_out_thread_turn(session, world, gate, person, player_input):
    """Write what was decided. Each writer leaves nothing behind if it cannot finish."""
    from adventure import dialogue_jobs
    import world_threads
    import money_owner
    thread = world_threads.by_id(world, gate["thread_id"])
    decision = gate["decision"]
    if decision in {"work", "pay"} and money_owner.blocks_money_moves(session):
        # D4: coin leaving the player's hand is never a shift or a wage drawn; the line is said to the person
        gate["decision"] = None
        session._thread_turn = gate
        return gate
    if decision == "pay":
        due, why = world_threads.wage_due(world, thread)
        amount, finished = world_threads.pay_day(world, thread) if due else (0, False)
        gate.update(decision="paid" if amount else f"pay_{why}", paid_cp=amount,
                    paid_line=world_threads.paid_line(amount, finished) if amount else None)
        session._thread_turn = gate
        return gate
    if decision == "give":
        gate["reply"] = dialogue_jobs.deliver(session, thread, person, player_input)
        return gate
    if decision == "give_late":
        gate["reply"] = dialogue_jobs.deliver_late(session, thread, person, player_input)
        return gate
    if decision == "lapsed":
        gate["reply"] = dialogue_jobs.lapsed_reply(session, thread, person, player_input)
        return gate
    if decision == "matter":
        world_threads.settle_matter(world, thread, person)
        gate.update(decision="matter_settled", paid_line=(world_threads.job_lines("text") or {}).get("matter_done"))
        session._thread_turn = gate
        return gate
    if decision == "take_up":
        import world_happenings
        world_happenings.put_forward(world, thread, person, thread["owner_line"])
        decision = gate["decision"] = "accepted"
    reading = world_threads.read_answer(player_input, person, thread)
    errand = thread.get("type") == "errand"
    if decision == "accepted" and errand:
        if not dialogue_jobs.accept_thread_job(session, thread, person):
            gate["decision"] = "busy"
    elif decision == "abandoned" and errand and thread.get("quest_id"):
        dialogue_jobs.abandon_thread_job(session, thread, person)
    elif decision in {"accepted", "declined", "abandoned"}:
        turn = int(world.get("flags", {}).get("turn_index", 0) or 0)
        if not world_threads.apply_decision(world, thread, decision, turn):
            gate["decision"] = None
    thread = world_threads.by_id(world, gate["thread_id"])
    if decision == "abandoned" and reading["move"]:
        return None  # the job is over and the walk is still a walk
    if world_threads.worked_on_the_spot(thread) and thread.get("status") == "accepted" and (
            gate["decision"] == "work" or (gate["decision"] == "accepted" and (reading["start"] or gate.get("works")))
    ) and not money_owner.blocks_money_moves(session):  # §0 (4): a yes with coin held out is written, no shift starts
        if world_threads.can_start_now(world, thread):
            gate["reply"] = world_threads.work_turn(session, thread["thread_id"], player_input)
            return gate
        gate["decision"] = "come_at_night"
    if gate["decision"] == "accepted" and thread.get("type") == "trouble" and thread.get("status") == "accepted":
        gate["paid_line"] = world_threads.what_it_takes(world, thread)
    in_hand = errand and thread.get("status") == "accepted" and gate["decision"] in {"accepted", "take"}
    if in_hand and reading["move"] and dialogue_jobs.holds_parcel(world, thread):
        return None  # parcel in hand and walking off: that is simply the walk
    if in_hand and (reading["take"] or reading["move"] or gate.get("takes")) and not dialogue_jobs.holds_parcel(world, thread):
        action = dialogue_jobs.hand_over(session, thread, person)
        if action and reading["move"]:
            gate["moving"] = dialogue_jobs.shown_line(world, thread, "taken")
        elif action and not reading["question"]:
            gate["reply"] = dialogue_jobs.take_reply(session, thread, player_input, action)
    elif in_hand and gate["decision"] == "accepted" and not dialogue_jobs.holds_parcel(world, thread):
        # The word and the thing go together: whoever said yes is holding it, and the person still says their word.
        if dialogue_jobs.hand_over(session, thread, person):
            gate["paid_line"] = dialogue_jobs.shown_line(world, thread, "taken")
    session._thread_turn = gate
    return gate

def _thread_gate(player_input, target_id, interaction_mode, *, front=None):
    """A line about someone's work is decided here, before any phrase owner reads it.

    Python reads the player's own words and writes the state; the model only voices the
    result. Works the same in the UI's default mode and in say mode. Nothing here fails a turn.
    """
    import town_knowledge
    import world_threads
    session = game._session()
    world = session.world_state
    if interaction_mode == "ask_dm" or world_threads.view(world) is None or world.get("combat", {}).get("active"):
        return None
    journey = world.get("journey")
    if journey and journey.get("status") != "ARRIVED":
        return None
    saved = None
    try:
        person = game._thread_person(player_input, target_id)
        gate = game._job_gate(world, person, player_input)
        if gate is None:
            # Money asked of someone with no job to their name is still said to them, and they answer it.
            spoken_to = isinstance(person, dict) and world_threads.asks_for_pay(player_input) and not game._physical_line(player_input)
            return {"decision": None, "npc_id": person["id"]} if spoken_to else None
        # A validated payment utterance is not a work action. Explicit front work has its own writer.
        coin = getattr(session, "_front_coin", 0)
        if (gate["decision"] == "work" and isinstance(front, dict) and front.get("kind") == "speak_to"
                and type(coin) is int and coin > 0):
            return None
        if (gate["decision"] is None and not gate.get("yes_heard") and interaction_mode != "say"
                and game._physical_line(player_input)):
            return None
        session.require_player_can_act()
        saved = session._capture_runtime_snapshot()
        return game._carry_out_thread_turn(session, world, gate, person, player_input)
    except game.PlayerCannotAct:
        raise
    except Exception:
        town_knowledge.log_failure()
        if saved is not None:  # D-011: a writer that broke half way leaves no coin, hour or item of it behind
            session._restore_runtime_snapshot(saved)  # in place: the turn above still holds these very dicts
        session._thread_turn = None
        return None

def _world_snapshot():
    world_state = game._session().world_state
    game._normalize_ground_items()
    return {
        "combat": json.dumps(world_state.get("combat", {}), sort_keys=True),
        "player_current_hp": game._session().character["current_hp"],
        "player_max_hp": game._session().character["max_hp"],
        "player_combat_status": world_state.get("player_combat_status"),
        "location": world_state.get("location"),
        "inventory": tuple(world_state.get("inventory", [])),
        "ground_items": tuple(world_state.get("ground_items", [])),
        "ground_items_by_location": {k: tuple(v) for k, v in world_state.get("ground_items_by_location", {}).items()},
        "doors": tuple(sorted(
            (door.get("name"), door.get("location"), door.get("open"), door.get("locked"), door.get("broken"))
            for door in world_state.get("doors", [])
        )),
        "player_hidden": world_state.get("flags", {}).get("player_hidden"),
        "pending_destination": world_state.get("flags", {}).get("pending_destination"),
        "locations": tuple(sorted(
            (location_id, location.get("name", ""), tuple(location.get("aliases", [])))
            for location_id, location in world_state.get("locations", {}).items()
        )),
        "npcs": tuple(json.dumps(npc, ensure_ascii=False, sort_keys=True) for npc in world_state.get("npcs", [])),
        "shops": tuple(json.dumps(shop, ensure_ascii=False, sort_keys=True) for shop in world_state.get("shops", [])),
        "features": tuple(json.dumps(feature, ensure_ascii=False, sort_keys=True) for feature in world_state.get("features", [])),
        "events": tuple(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in world_state.get("events", [])),
    }

def _changed_state_fields(before):
    after = game._world_snapshot()
    fields = {
        "combat": "world.combat",
        "player_current_hp": "player.current_hp",
        "player_max_hp": "player.max_hp",
        "player_combat_status": "player.combat_status",
        "location": "player.location",
        "inventory": "player.inventory",
        "ground_items": "ground_items",
        "ground_items_by_location": "ground_items",
        "doors": "doors",
        "player_hidden": "flags.player_hidden",
        "pending_destination": "flags.pending_destination",
        "locations": "world.locations",
        "npcs": "world.npcs",
        "shops": "world.shops",
        "features": "world.features",
        "events": "world.events",
    }
    return [fields[key] for key in fields if before.get(key) != after.get(key)]

def _execute_intent_internal(intent, player_input, npc_target=None, target_id=None, *, check_feature=None, check_evidence=None):
    """Central Python rule engine: validate intent effects and return a structured result."""
    world_state = game._session().world_state
    intent = intent if isinstance(intent, dict) else {"intent": "unknown"}
    intent_type = intent.get("intent", "unknown")
    if intent_type == "travel" and game.ensure_combat_state()["active"]:
        target = intent.get("target") if isinstance(intent.get("target"), dict) else {}
        approached = None
        if not combat_lifecycle.is_attack_decision(game._session(), player_input) and target.get("type") == "npc":
            npc_id = target.get("npc_id") if isinstance(target.get("npc_id"), str) and target["npc_id"].strip() else None
            approached = game._approach_turn(npc_id or getattr(game._session(), "_front_approach", None))
        if approached is not None:
            return approached
        if combat_lifecycle.is_attack_decision(game._session(), player_input):
            intent_type = "attack"
            intent = {**intent, "intent": "attack"}
        elif (combat_lifecycle.walks_off(game._session(), player_input)
              or combat_lifecycle.walks_on_own_feet(game._session(), player_input)):
            raise combat_lifecycle.CombatRequestError("combat_travel", "Normal travel cannot leave active combat.", 400)
        else:  # "çık git konaktan" is said to the other one: the player stays, and the line is words in the fight
            intent_type = "narrative"
            intent = {**intent, "intent": "narrative"}
    if (intent_type in {"attack", "combat"} and not game._is_explicitly_negated_attack(player_input)
            and not combat_lifecycle.is_attack_decision(game._session(), player_input)
            and not combat_lifecycle.quoted_or_conditional_not_attack(game._session(), player_input)):
        # The model heard a fight the player's words do not start ("gerekirse kafa
        # kırarım"). Python owns combat, so the line stays what it is: words.
        intent_type = "narrative"
        intent = {**intent, "intent": "narrative"}
    before = game._world_snapshot()
    result = {
        "action": intent_type,
        "success": True,
        "status": "resolved",
        "state_changes": [],
    }
    if intent_type in {"attack", "combat"} and combat_lifecycle.quoted_or_conditional_not_attack(game._session(), player_input):
        result.update(
            action="narrative",
            success=None,
            status="not_executed",
            outcome="reported_not_attack",
            state_changes=[],
        )
        return result

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

    combat_was_active = bool(game.ensure_combat_state()["active"])
    if intent_type in {"attack", "combat"} and (game._session().character["current_hp"] <= 0 or world_state["player_combat_status"] == "unconscious"):
        result.update(action="attack", success=False, outcome="player_unconscious",
                      direct_response="Bilincin kapalı; saldırı yapamazsın.")
        return game._finish_combat_result(result, before)
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

    character_reply = game.known_character_answer(player_input)
    if character_reply:
        result.update({"action": "character_query", "direct_response": character_reply})
        return result

    # Handle identity/location/presence queries
    model_query_type = (
        intent.get("query_type") if game._model_query_type_is_plausible(player_input) else None
    )
    query_type = game._detect_query_type(player_input, npc_target) or model_query_type
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

    if intent_type == "observe":
        intent_type = "explore"
    explore_type = intent.get("explore_type", "observe") if intent_type == "explore" else None
    if intent_type == "explore":
        result.update({"action": "explore", "explore_type": explore_type, "status": "resolved", "success": True})

    if intent_type == "dialogue" and npc_target:
        result.update({
            "npc_id": npc_target.get("id"),
            "npc_name": living_world.public_npc_name(npc_target),
        })

    deterministic = game.deterministic_check_for_action(player_input)
    skill = None
    difficulty = "medium"
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
    # A grounded request to bargain is an engine Persuasion attempt even when phrased as ordinary speech.
    # Missing/unclear proposals leave the original action and its existing skill routing untouched.
    negotiation = money_owner.price_negotiation(world_state, intent.get("price_negotiation"), player_input)
    if (skill is None and negotiation is not None and isinstance(npc_target, dict)
            and negotiation["npc_id"] == npc_target.get("id")):
        skill = "Persuasion"
    if skill == "Stealth":
        skill = game._stealth_skill(player_input)  # D-094, D-171, D-176: hiding needs cover; hiding a thing is no hide
        if skill is None:
            world_state.setdefault("flags", {})["player_hidden"] = False
            result.update({
                "action": "world_interaction",
                "status": "resolved",
                "direct_response": "Açıkta, gün ışığında saklanacak bir yer yok; seni görebiliyorlar.",
                "state_changes": game._changed_state_fields(before),
            })
            return result
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

    if intent_type == "explore":
        # Looking at a named door, window or detail reveals what is plainly
        # visible without a roll (LR00-P2: no needless check for open facts).
        findings = game._inspection_findings(player_input, "success", rolled=False)
        if findings:
            findings["auto_visible"] = True
            result["inspection"] = findings
        return result

    # Words said to a person claim nothing about the world: "ben buradayım" is no statement to correct.
    python_reply = None if intent_type == "dialogue" else game.resolve_python_world_action(player_input)
    if isinstance(python_reply, dict):
        result.update(python_reply)
        return result
    if python_reply:
        result.update({
            "action": "world_interaction",
            "status": "resolved",
            "direct_response": python_reply,
            "state_changes": game._changed_state_fields(before),
        })
        return result

    inventory_reply = game.update_inventory_from_player(player_input)
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

    fixed_reply = game.known_player_action_narration(player_input)
    if fixed_reply:
        result.update({"action": "narrative", "direct_response": fixed_reply, "state_changes": []})
        return result

    if intent_type in {"attack", "combat"}:
        combat = game.ensure_combat_state()
        result["action"] = "attack"
        if combat["active"] and combat["current_actor_id"] != "player":
            result.update(
                success=False, status="out_of_turn", outcome="out_of_turn",
                current_actor_id=combat["current_actor_id"],
                turn_owner=combat["current_actor_id"],
                direct_response="Bu hamle için sıra sende değil.",
            )
            return game._finish_combat_result(result, before)
        if combat["active"]:
            action_economy.action_slot(game._session(), "player", "attack")

        import gear
        weapon_id, attack_choice = weapon_attack.natural_choice(game._session(), player_input)
        # The model's word for the weapon (intent or front reading) goes only to the catalog: one not owned is a punch.
        asked = intent.get("weapon_word") or (getattr(game._session(), "_front_strike", None) or {}).get("with")
        missing = gear.not_owned(world_state, requested_name=asked) if asked else None
        if missing:
            weapon_id = "unarmed"
        weapon_name, weapon_data = game.find_weapon_in_inventory(weapon_id)
        if weapon_id == "unarmed":
            weapon_name, weapon_data = "unarmed", None
        weapon_line = (refusals.text_for("weapon_not_owned", weapon=missing) if missing
                       else f"Çantandan çektiğin {weapon_name} ile vuruyorsun."
                       if isinstance(weapon_data, dict) and not gear.holds(world_state, weapon_data) else None)
        if not weapon_name:
            fallback_name = held_weapon.attack_weapon_name(world_state)
            if fallback_name:
                weapon_name, weapon_data = game.find_weapon_in_inventory(fallback_name)
        if not weapon_name:
            result.update(success=False, outcome="no_weapon",
                          direct_response="Envanterinde saldırmak için kullanabileceğin bir kılıç yok.")
            return game._finish_combat_result(result, before)
        target_npc = game.resolve_combat_target(
            player_input,
            npc_target,
            target_id=target_id,
        )
        if not target_npc and target_id is None:
            targets = combat_lifecycle._attack_targets(game._session(), player_input, None)
            if (combat_lifecycle._single_valid_target(game._session(), targets)
                    and not game._entity_reference_in_text(targets[0].get("name", ""), game._normalize_turkish_typos(player_input))):
                target_npc = targets[0]  # one person here: the blow needs no name, but a guessed hidden name is asked about
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
        if combat["active"] and target_npc["id"] not in combat["participants"]:
            result.update(success=False, outcome="target_mismatch",
                          target_id=target_npc["id"],
                          direct_response="Bu kişi mevcut çatışmanın katılımcısı değil.")
            return game._finish_combat_result(result, before)
        game.ensure_npc_enemy_stats(target_npc)
        if (target_npc["combat_status"] not in {"active", "unconscious"}
            or (not combat["active"] and target_npc["current_hp"] <= 0)):
            result.update(success=False, outcome="invalid_target", target_id=target_npc["id"],
                          direct_response="Bu hedef savaşabilecek durumda değil.")
            return game._finish_combat_result(result, before)
        melee_weapon = weapon_data if isinstance(weapon_data, dict) else {"range_ft": 5}
        sense_pair = monster_sense.observable_pair(game._session())
        if sense_pair is not None and target_npc["id"] == monster_sense.NPC_ID:
            target_npc["distance_ft"] = sense_pair["distance_ft"]
        if monster_sense.blocks_melee(game._session(), target_npc["id"], melee_weapon):
            pair = monster_sense.observable_pair(game._session())
            result.update(
                success=False,
                outcome="out_of_reach",
                distance_ft=None if pair is None else pair["distance_ft"],
                direct_response="Hedef yakın dövüş menzilinin dışında.",
            )
            return game._finish_combat_result(result, before)
        started = not combat["active"]
        enemy_actions = []
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
        combat = game.ensure_combat_state()
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
        combat["target_id"] = target_npc["id"]
        result = game.resolve_attack(player_input, weapon_name, weapon_data, target_npc,
                                attack_choice=attack_choice)
        if weapon_line:
            result["weapon_line"] = weapon_line
        if missing:
            refusals.note(game._session(), "weapon_not_owned", weapon=missing)  # half done: the narrator hears it too
        result["combat_started"] = started
        if result.get("outcome") in ("invalid_target", "no_target"):
            result["combat_started"] = started
            if enemy_actions:
                result["enemy_actions"] = enemy_actions
                result["enemy_action"] = enemy_actions[0]
            return game._finish_combat_result(result, before)

        game._mark_combat_action_used("player")
        if action_economy.holding(game._session()):
            game._combat_end_if_decided()
            return game._finish_combat_result(result, before)
        turn_effects = game._finish_species_player_turn()
        if turn_effects:
            result["species_effects"] = [
                *result.get("species_effects", []),
                *turn_effects,
            ]
        combat = game.ensure_combat_state()
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
        combat = game.ensure_combat_state()
        if enemy_actions:
            result["enemy_actions"] = enemy_actions
            result["enemy_action"] = enemy_actions[0]
        result["current_actor_id"] = combat["current_actor_id"]
        result["turn_owner"] = combat["current_actor_id"]
        result["target_id"] = target_npc["id"]
        return game._finish_combat_result(result, before)

    elif intent_type in {"rest", "use_item"}:
        # Drinking, sitting down, catching a breath: the narrator tells the
        # attempt, Python changes nothing. Nobody fills in a form to lie down.
        result.update({"action": "narrative", "success": False, "status": "attempted", "state_changes": []})
    elif intent_type in {"interact", "door"}:
        # LR00 fix: no owner acted on this. Saying "resolved" here produced
        # "Çevrede şimdilik belirgin bir değişiklik olmuyor" for a lockpicking
        # attempt. A door or lock act with no target is told what is here; any
        # other attempt is an event in the world, so the narrator describes it.
        import grounded_action
        parsed = grounded_action.plan(game._session(), player_input)
        if intent_type == "door" or any(step.get("part") or step.get("ambiguous") for step in parsed["steps"]):
            result.update({
                "action": intent_type,
                "success": False,
                "status": "unresolved",
                "state_changes": [],
                "direct_response": grounded_action.clarification_text(game._session()),
            })
        else:
            result.update({"action": "narrative", "success": False, "status": "attempted", "state_changes": []})
    else:
        result.update({"action": "dialogue" if intent_type == "dialogue" else intent_type, "state_changes": []})
    return result

def _hideout_check(skill, dc):
    """Dice stay with the existing check owner. The hideout only hears success."""
    character = game._session().character
    result = game.perform_skill_check(
        skill,
        dc,
        character["modifiers"],
        character.get("proficient_skills") or [],
        character.get("proficiency_bonus") or 2,
        expertise_skills=character.get("expertise_skills") or (),
    )
    return result["result"] == "BAŞARILI"

def _adventure_scene_turn(player_input):
    """Resolve a quest check or a known place change before the model narrates it."""
    session = game._session()
    world = session.world_state
    if not any(
        isinstance(quest, dict)
        and quest.get("record_kind") == "dynamic"
        and quest.get("status") == "ACTIVE"
        for quest in world.get("quests", [])
    ):
        return None
    if adventure_play.inside_hideout(world):
        return None
    if not isinstance(player_input, str):
        return None
    prepared = player_input.replace("İ", "i").replace("I", "ı")
    check = game.deterministic_check_for_action(prepared)
    if isinstance(check, dict) and check.get("skill") == "Investigation":
        return game._adventure_check_reply(session, "Investigation")
    folded = player_input.casefold()
    if not re.search(r"\b(?:gidiyorum|git|donuyorum|dönüyorum)\b", folded):
        return None
    for word in ("orman", "taverna", "kale", "neverwinter"):
        if word in folded:
            destination = game.resolve_location_reference(word)
            if (
                isinstance(destination, str)
                and destination != world.get("location")
                and destination in world.get("locations", {})
            ):
                return game._adventure_travel_reply(session, destination)
    return None

def _adventure_check_reply(session, skill):
    before = copy.deepcopy(session.world_state)
    passed = game._hideout_check(skill, game.DIFFICULTY_DC["medium"])
    flags = session.world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    evidence = {
        "action": "skill_check",
        "skill": skill,
        "success": passed,
        "status": "resolved",
        "action_id": f"adventure-check:{flags['turn_index']}:{skill}",
        "state_changes": [],
    }
    session.evaluate_quest_events(before, evidence)
    narration = "İncelemen yeni bir izi ortaya çıkardı." if passed else "Bu bakış yeni bir iz çıkarmadı."
    session.messages.extend([
        {"role": "user", "content": skill},
        {"role": "assistant", "content": narration},
    ])
    return {
        "messages": session.messages,
        "narration": narration,
        "model_calls": 0,
        "action_result": {
            "action": "adventure_check",
            "success": passed,
            "status": "resolved",
            "state_changes": [],
        },
    }

def _everyday_action_turn(player_input):
    """Knock, ring, read, follow, whistle: a small truthful result, no wall."""
    import everyday_actions

    session = game._session()
    world = session.world_state
    if session.character.get("current_hp", 0) <= 0:
        return None
    flags = world.setdefault("flags", {})
    import exploration

    # A named venue door already has a Python owner (exploration door_knock).
    if exploration._natural_venue_door_action(session, player_input) is not None:
        return None
    # "Kapıyı çalıyorum, cevap gelmezse pencereden bakıyorum, sonra ...": do
    # the first ordinary step now and keep the rest as a plan that waits for
    # the player - no step is silently dropped (OH1-03).
    compound = interaction_adventure.compound_plan(player_input)
    first_step = compound["steps"][0]["quote"] if compound else player_input
    outcome = everyday_actions.resolve(
        world, first_step, door=game._current_door(),
        reference=game._entity_reference_in_text, turn=int(flags.get("turn_index", 0)) + 1,
    )
    if (isinstance(outcome, dict) and outcome.get("kind") == "read" and outcome.get("item") is None
            and getattr(session, "_front_read", None) is not None):
        return None  # read as an act on what is at hand, it is no search of the bag for a book
    if outcome is None:
        return None
    narration = outcome["text"]
    if compound:
        recorded = interaction_adventure.resolve(session, player_input, compound)
        state = world.get(interaction_adventure.KEY)
        plan = state.get("plan") if isinstance(state, dict) else None
        if recorded.get("status") != "recorded" or not isinstance(plan, dict):
            return None
        if len(plan.get("steps", [])) > 1:
            plan["cursor"] = 1
            interaction_adventure.validate(state, world)
            pass  # The player remembers their own plan; the game does not read it back.
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    action_result = {
        "action": "everyday_action",
        "kind": outcome["kind"],
        "status": "resolved",
        "success": True,
        "state_changes": [],
        "direct_response": narration,
        **({"npc_id": outcome["npc_id"]} if outcome.get("npc_id") else {}),
        **({"target_id": outcome["door_id"]} if outcome.get("door_id") else {}),
    }
    session.messages.extend([
        {"role": "user", "content": player_input},
        {"role": "assistant", "content": narration},
    ])
    return {
        "messages": session.messages,
        "narration": narration,
        "model_calls": 0,
        "action_result": action_result,
    }

def _local_place_turn(player_input):
    """LR00-P3 pilot: go to a named local place (archive, smithy, temple...).

    Creates it once inside the current settlement, with one local person, one
    detail and a small local matter; later visits and restarts reuse the saved
    records. Negated, conditional or question forms never move the player.
    """
    import local_places

    session = game._session()
    world = session.world_state
    current = world.get("location")
    settlement = local_places.settlement_of(world, current)
    if settlement is None or session.character.get("current_hp", 0) <= 0:
        return None
    person_place = local_places.resident_visit(world, settlement, player_input)
    named_place = local_places.visit_by_name(world, settlement, player_input)
    kind = (local_places.is_local_place_visit(player_input) or (person_place or {}).get("place_kind")
            or (named_place or {}).get("place_kind"))
    if kind is None:
        return None
    record = (person_place or local_places.named_in(world, settlement, player_input)
              or local_places.find_local_place(world, settlement, kind))
    if record is not None and record.get("id") == current:
        if local_places.goes_further_in(world, current, player_input):
            import grounded_action
            room = local_places.inner_room_of(world, current)
            return grounded_action.resolve_turn(session, player_input,
                                                listed_place={"id": room["id"], "inside": True, "whole_line": True})
        narration = f"Zaten {record['name']} içindesin."
        return {
            "messages": session.messages,
            "narration": narration,
            "model_calls": 0,
            "action_result": {
                "action": "travel", "status": "already_here", "success": True,
                "target_id": current, "state_changes": [], "direct_response": narration,
            },
        }
    before = copy.deepcopy(world)
    created = record is None
    if created:
        record = local_places.create_local_place(world, settlement, kind)
        if record is None:
            return None
        record["provenance"] = {
            "source": "player_pursuit",
            "mentioned_by_npc_id": local_places.mentioned_by(world, kind),
        }
    flags = world.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    if not game.commit_location_change(record["id"], flags["turn_index"]):
        world.clear()
        world.update(before)
        return None
    if "campaign_time" in world:  # the walk takes what a walk takes, and the town moves on meanwhile
        import grounded_action
        game.advance_campaign_time(grounded_action.LOCAL_WALK_SECONDS, "exploration")
    npc, feature = local_places.furnish(
        world, record, create_npc=game.create_npc_from_ai, create_feature=game.create_local_feature,
    )
    import arrival_narration  # here, not at the top: arrival_narration imports game
    narration, told = arrival_narration.arrive(sys.modules["game"], world, record, npc, feature, first_visit=created,
                                               player_input=player_input, messages=session.messages)
    action_result = {
        "action": "travel",
        "status": "resolved",
        "success": True,
        "target_id": record["id"],
        "state_changes": ["location", *(["locations", "npcs", "features"] if created else [])],
        "local_place": {
            "kind": kind,
            "created": created,
            "npc_id": npc.get("id") if isinstance(npc, dict) else None,
            "feature_id": feature.get("id") if isinstance(feature, dict) else None,
        },
        "arrival_narration": {"source": told["source"], "reason_code": told["reason_code"]},
        "direct_response": narration,
    }
    session.evaluate_quest_events(before, action_result)
    session.messages.extend([
        {"role": "user", "content": player_input},
        {"role": "assistant", "content": narration},
    ])
    return {
        "messages": session.messages,
        "narration": narration,
        "model_calls": told["calls"],
        "action_result": action_result,
    }

def _intent_infrastructure_result(error):
    """The existing retryable result, emitted only for a typed engine exception."""
    text = "Bu hamle tamamlanamadı; dünya durumu değişmedi."
    return {
        "narration": text,
        "action_result": {
            "action": "unknown",
            "status": "infrastructure_failure",
            "success": False,
            "state_changes": [],
            "infrastructure_code": error.code,
            "direct_response": text,
        },
    }

def _clear_turn_transients(session) -> None:
    """Coin a turn's reading saw in the hand belongs to that turn alone, whether it ended well or failed (B1).

    The turn's economic source key goes with it (A4): a card a later turn finds is never this turn's own.
    """
    session._handed_note = None
    session._given_now = None
    session._coin_paid = None
    session._front_coin = 0
    session._front_economic_none = False
    session._front_economic_front = None
    session._spoken_coin_proposal = None
    session._spoken_coin_result = None
    session._coin_rest_hint = ""
    session._bribe_held_out = 0
    session._counter_held = None
    session._economic_turn_key = None
