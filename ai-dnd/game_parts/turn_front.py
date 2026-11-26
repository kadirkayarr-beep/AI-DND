import game
import action_economy
import adventure.play as adventure_play
import combat_lifecycle
import contextlib
import copy
import held_weapon
import interaction_adventure
import json
import living_world
import logging
import money_owner
import monster_sense
import re
import refusals
import sys
import timed_gameplay
import weapon_attack
import equipment_economy
import talk_mode
import tr_case
from core_resolution import resolution_action_scope


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

    _exit = game._fx_door_inspection(player_input=player_input, result=result)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._fx_negated_attack(intent_type=intent_type, player_input=player_input, result=result)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
    _exit = game._fx_query(npc_target=npc_target, player_input=player_input, query_type=query_type, result=result)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._fx_travel(before=before, combat_was_active=combat_was_active, intent=intent, intent_type=intent_type, result=result, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
    skill = game._fx_check_skill(deterministic=deterministic, explore_type=explore_type, intent_type=intent_type, player_input=player_input, skill=skill)
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
    _exit = game._fx_skill_check(before=before, check_evidence=check_evidence, check_feature=check_feature, difficulty=difficulty, intent=intent, intent_type=intent_type, npc_target=npc_target, player_input=player_input, result=result, skill=skill)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
    _exit = game._fx_inventory_reply(before=before, inventory_reply=inventory_reply, result=result)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
        _exit = game._fx_attack_ambiguous_target(before=before, result=result, target_npc=target_npc)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
        _exit = game._fx_attack_no_target(before=before, npc_target=npc_target, result=result, target_id=target_id, target_npc=target_npc)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
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
        _exit = game._fx_attack_started(before=before, enemy_actions=enemy_actions, result=result, started=started, target_npc=target_npc, world_state=world_state)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
        combat = game.ensure_combat_state()
        _exit = game._fx_attack_out_of_turn(before=before, combat=combat, result=result)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
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
        combat = game._fx_attack_combat_end(enemy_actions=enemy_actions, result=result)
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

def _the_place_meant(session, world, settlement, kind, person_place, player_input):
    """The place record the line means and no question, or no record and the question that asks which place (D-299)."""
    import local_places
    record = person_place or local_places.named_in(world, settlement, player_input)
    if record is not None:
        return record, None
    same_kind = local_places.places_of_kind(world, settlement, kind)
    if len(same_kind) > 1 and any(place.get("rumoured") for place in same_kind):
        # D-299: a heard place carries the generic word as an alias too, so the word names one place only when
        # the town holds one; with a heard place beside it, the player is asked.
        names = [str(place.get("name") or place["id"]) for place in same_kind]
        narration = (f"Burada birden çok yer var: {', '.join(names[:-1])} ve {names[-1]}. "
                     "Hangisine gidiyorsun?")
        session.messages.extend([{"role": "user", "content": player_input},
                                 {"role": "assistant", "content": narration}])  # as grounded_action._bookkeeping
        return None, {
            "messages": session.messages, "narration": narration, "model_calls": 0,
            "action_result": {"action": "travel", "status": "clarification", "success": False,
                              "candidates": [place["id"] for place in same_kind], "state_changes": [],
                              "direct_response": narration},
        }
    return (same_kind[0] if same_kind else None), None


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
    record, which_asked = game._the_place_meant(session, world, settlement, kind, person_place, player_input)
    if which_asked is not None:
        return which_asked
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
    session._speech_repair_calls = 0  # D-332: the repair call counts into this turn's model calls only; a flag-off turn has no begin()

def _tell_the_coin(result):
    """After the reply, the money owner opens the one card this turn's decision names; coin is never a silent gift.

    It writes no coin. The coin in hand and the counter's hold on it end here, whatever the owner did.
    """
    session = game._session()
    try:
        pending = getattr(session, "_spoken_coin_proposal", None)
        if pending is not None:
            person = next((n for n in game.active_npcs() if n.get("id") == pending.recipient_id), None)
            if person is not None:
                game._record_spoken_coin_response(person, None)  # a deterministic reply supplies no semantic acceptance
        spoken = getattr(session, "_spoken_coin_result", None)
        session._spoken_coin_result = None
        declined = getattr(session, "_coin_answer", None) == "declines"
        # The person's spoken answer about the coin and the card this turn's decision names (D1) come first: a spoken
        # decline is written per part and closes what it covers, with its own line.
        opened = money_owner.open_card_after_reply(session, result)
        if spoken is not None and isinstance(result, dict):
            # The validated gift or tip was put to this person; the card (or the refusal) is the engine's word.
            if not declined:
                result["narration"] = f"{result.get('narration') or ''} {spoken.public_message}".strip()
            result.setdefault("action_result", {}).update(status=spoken.status, success=spoken.status == "prepared",
                                                          reason_code=spoken.reason_code)
        hint = getattr(session, "_coin_rest_hint", "")
        if hint and isinstance(result, dict) and any(
                getattr(told, "reason_code", None) == "npc_consent_required"
                for told in (opened, None if declined else spoken)):
            # D-208: a walk's second part refused for want of the person's word says the coin can be held out again.
            result["narration"] = f"{result.get('narration') or ''} {hint}".strip()
        if pending is None and spoken is None:
            # Asked for a room or goods while talking: after the answer's own money fields, and only with no money
            # moved or decided this turn (one consumer); the card or offer still waits for the player's confirmation.
            money_owner.ask_after_reply(session, result, getattr(session, "_asks_for", None))
        note = (result.get("action_result") or {}).get("haggle_note")
        if isinstance(note, str) and note:
            result["narration"] = f"{result.get('narration') or ''} {note}".strip()
    finally:
        session._asks_for = None
        session._coin_rest_hint = ""
        session._coin_paid = None
        session._counter_held = None
        session._coin_answer = None
        session._coin_answer_for = None
        session._coin_answer_npc = None

def _the_rest_of_the_line(result, messages, action_id, session_id, place_before):
    """"Bira ver, soylu arayan var mı": the owner did the first part, so the person gets the second, as a paid word does.

    "Hana gidiyorum, odayı soruyorum": a walk that got there takes the rest along, read as a line of its own at the
    place walked to; a walk that stopped short (a locked door) drops it."""
    session = game._session()
    rest = getattr(session, "_front_rest", "")
    action_result = result.get("action_result") if isinstance(result, dict) else None
    from api import ollama_adapter
    read = getattr(session, "_front_read", None) or {}
    walk = isinstance(action_result, dict) and game._a_walk(read, action_result)
    walked = walk and game._walked_there(read, action_result, place_before)
    if (not rest or not isinstance(action_result, dict) or session.world_state.get("combat", {}).get("active")
            or (walk and not walked)  # stopped short: nobody the rest was for is here
            or (session.world_state.get("location") != place_before and not walked)  # the one asked is left behind
            or (walked and (getattr(session, "_front_coin", 0) or getattr(session, "_coin_paid", None)))  # coin read once
            or action_result.get("action") in {"dialogue", "query", "lodging", "shop_inquiry"}  # a room taken has answered its own price
            or action_result.get("status") in {"experimental_attributed_speech", "clarification"}
            or not ollama_adapter.model_calls_left(third=True)):  # D-419 (S20 a): the rest may take the third call
        return result
    own_act = walked or read.get("kind") in game._OWN_ACTS
    hearer = None
    if own_act:
        named = game._addressed_in(rest, or_the_talk=False)
        if isinstance(named, dict) and named.get("id") in {npc.get("id") for npc in game._conversation_npcs()}:
            # "yemeği yiyorum, Marek'e şehri soruyorum": the second part names someone here, so it is said to them
            # (the say path keeps the turn's second call for their answer), not read again.
            own_act, hearer = False, named
    if not own_act and hearer is None:
        here = game._conversation_npcs()
        hearer = next((npc for npc in here if npc.get("id") == read.get("id")), None) or game._active_interlocutor() or (
            here[0] if len(here) == 1 else None)
        if not isinstance(hearer, dict):
            return result
    session._front_rest = ""
    flags = session.world_state.setdefault("flags", {})
    turn = flags.get("turn_index", 0)
    if own_act:
        # "Yemeği yiyorum ve şarabı içiyorum": the first part was the player's own doing, so the second is no word to
        # whoever stands there; it is read as a line of its own (the turn's second call) and done by its own owner.
        session._front_reply = session._front_read = None
        session._front_ahead = False
        with ollama_adapter.third_call():
            said = game._dispatch_player_turn(rest, messages, None, None, action_id, session_id, None, None)
        session._front_rest = ""  # the second part has no second part of its own
    else:
        # A rest that hands coin is read like any say line that names coin (the front step opens its card): the gate
        # is left open for it, so a person named by name gets the card a role gets and no coin is paid without one.
        import front_proposal
        coin_rest = front_proposal.names_coin(rest)
        session._thread_gate_done = not coin_rest
        if coin_rest:
            session._front_reply = session._front_read = None  # the walk's reading is spent: the coin line is read afresh
            session._front_ahead = False
        try:
            with ollama_adapter.third_call():
                said = game._dispatch_player_turn(rest, messages, hearer["id"], None, action_id, session_id, None, "say")
        finally:
            session._thread_gate_done = False
    import front_proposal
    if walked and front_proposal.names_coin(rest):
        # D-208 (Kadir, option D): the person's answer on arrival carries no word on the coin, so a refusal for want
        # of consent stands and says the coin can be held out again now that the player is there.
        inside = session.world_state.get("location") != place_before
        session._coin_rest_hint = f"{'İçerideyken parayı' if inside else 'Parayı'} yeniden uzatabilirsin."
    if flags.get("turn_index", 0) > turn:
        flags["turn_index"] = turn  # one line is one turn: the second part stands under the first part's index
    line = said.get("narration") or ""
    if hearer is not None and game._is_stock(line):
        line = game._person_fallback(session.world_state, hearer, rest)
    first_line = (result.get("narration") or "").strip()
    result["narration"] = first_line if line.strip() == first_line else f"{first_line} {line}".strip()
    # Both parts are one turn: what each proved is handed on together, under that one turn's index.
    first, last = result.get("_engine_event_evidence"), said.get("_engine_event_evidence")
    if last and not first and action_result.get("quest_outcomes"):
        # a first part with no evidence of its own (a delivery) still proved its outcomes in the action result
        first = {"quest_outcomes": copy.deepcopy(action_result["quest_outcomes"]), "procedural_entity_ids": []}
    if first and last:
        last["quest_outcomes"] = [*first["quest_outcomes"], *last["quest_outcomes"]]
        last["procedural_entity_ids"] = sorted({*first["procedural_entity_ids"], *last["procedural_entity_ids"]})
    if last:
        result["_engine_event_evidence"] = last
    kept = result.get("_engine_event_evidence")
    if kept:
        kept.update(turn_index=turn, action_id=f"turn:{turn}")
    return result

def _stock_hearer_asked(result, player_input, target_id):
    """Whoever a stock line is asked of again: no one when the reading named someone nobody here is (D-419 keeps that line in Python's hands)."""
    if getattr(game._session(), "_named_word", None):
        return None
    return game._stock_hearer(result, player_input, target_id)

def _person_answers_stock(result, player_input, messages, target_id, interaction_mode, action_id, session_id, snapshot):
    """The one door every owner's text leaves by: a stock line never answers a person, and no person says one.

    A stock line changed nothing, so the line can simply go to the person if the turn still has a model call.
    With none left the person answers from what Python has for them.
    """
    session = game._session()
    text = result.get("narration") if isinstance(result, dict) else None
    if (not isinstance(text, str) or not game._only_stock(text)
            or session.world_state.get("combat", {}).get("active")):
        return result
    hearer = _stock_hearer_asked(result, player_input, target_id)
    if hearer is None:
        return result
    action_result = result.get("action_result") if isinstance(result.get("action_result"), dict) else {}
    from api import ollama_adapter
    if (snapshot is not None and interaction_mode != "say" and ollama_adapter.model_calls_left(third=True)  # D-419 (S20 a)
            and not action_result.get("state_changes")):
        person = hearer["id"]
        session._restore_runtime_snapshot(snapshot)
        session._thread_gate_done = True
        try:
            with ollama_adapter.third_call():
                result = game._dispatch_player_turn(player_input, messages, person, None, action_id, session_id, None, "say")
        finally:
            session._thread_gate_done = False
        text = result.get("narration")
        if not game._is_stock(text):
            return result
        hearer = next((npc for npc in game._conversation_npcs() if npc.get("id") == person), hearer)
    line = game._person_fallback(session.world_state, hearer, player_input)
    result["narration"] = line
    action_result = result.get("action_result") if isinstance(result.get("action_result"), dict) else {}
    if action_result.get("direct_response"):
        action_result["direct_response"] = line
    for row in reversed(session.messages):
        if row.get("role") == "assistant":
            if row.get("content") == text:
                row["content"] = line
            break
    return result

def _last_call():
    """One cry into the dark per campaign: rare, in Python's hands, never promised."""
    session = game._session()
    state = game.ensure_death_state()
    roll = game.roll_d20()
    # masa kuralı (SRD'de yok): Kadir kararı 2 — the 5% answer (only a natural 20) is a table rule, not a published one
    answered = roll == 20
    state["last_call"] = {"roll": roll, "answered": answered}
    if not answered:
        return "Sesin karanlığa karışıyor; cevap gelmiyor. Öldün. " + game._death_closing(), "player_dead"
    session.world_state["player_combat_status"] = "unconscious"
    state.update(dead=False, terminal=False, successes=0, failures=0, prone=True, last_resolution=None)
    game.heal_player(1)
    return ("Sesin karanlıkta yankılanıyor ve bir şey karşılık veriyor. Ciğerlerine yakıcı bir hava doluyor; "
            "gözlerini açıyorsun. Yerdesin ama nefes alıyorsun."), "player_rescued"

def combat_refusal_turn(error):
    """A plain line that a fight will not allow is answered in the fight, never in English."""
    narration = refusals.text_for(error.code)
    refusals.note(game._session(), error.code)
    return {
        "messages": game._session().messages,
        "narration": narration,
        "model_calls": 0,
        "action_result": {
            "action": "narrative", "status": "fight_refused", "success": False,
            "state_changes": [], "direct_response": narration,
        },
    }

def _approach_turn(target_id):
    """A walk toward someone named in a fight: combat movement Python measures, told in the engine's own words.
    None when the one named is not in the fight (the old travel rule answers)."""
    r = combat_lifecycle.approach(game._session(), target_id, named=True)
    if r.status == "not_a_participant":
        return None
    game._session()._walk_off = None  # the walk the words said is this one: toward someone in the fight
    if r.status == "which":
        narration = refusals.text_for("which_enemy", names=combat_lifecycle.asked_names(r.names))
        refusals.note(game._session(), "which_enemy", names=combat_lifecycle.asked_names(r.names))
    elif r.status == "short":
        narration = refusals.text_for("approach_short", left=r.left_ft)
        refusals.note(game._session(), "approach_short", left=r.left_ft)
    else:
        narration = f"{r.moved_ft} fit ilerlersin; {r.names[0]} artık yanında." if r.moved_ft else f"{r.names[0]} zaten yanında."
    return {
        "action": "combat_move", "status": {"which": "clarification", "short": "partial"}.get(r.status, "resolved"),
        "success": r.status == "moved", "target_id": r.target_id, "moved_ft": r.moved_ft,
        "state_changes": ["combat"] if r.moved_ft else [], "direct_response": narration,
    }

def player_cannot_act_turn():
    """A dead player's line is answered in the world, never as a server error."""
    state = game.ensure_death_state()
    if state["dead"] or game._session().world_state.get("player_combat_status") == "dead":
        if state["terminal"] or state.get("last_call") is not None:
            narration, status = f"Kıpırtısız yatıyorsun; öldün. {game._death_closing()}", "player_dead"
        else:
            narration, status = game._last_call()
    else:
        narration = ("Bilincin kapalı, kanın durdu; ne konuşabiliyor ne kıpırdayabiliyorsun. "
                     "Dünya sensiz akıyor; beklersen gözlerini açarsın.")
        status = "player_unconscious"
    return {
        "messages": game._session().messages,
        "narration": narration,
        "model_calls": 0,
        "action_result": {
            "action": "narrative", "status": status, "success": False,
            "state_changes": [], "direct_response": narration,
            **({"healing": 1, "heal_source": "death_save"} if status == "player_rescued" else {}),
        },
    }

def _reads_as_address(player_input):
    """Spoken at someone: a question, a greeting or a name at the head of the line."""
    return "?" in player_input or game.is_npc_dialogue_input(player_input) or "," in player_input[:40]

def _addressed_in(player_input, *, or_the_talk=True):
    """Who the line names, or else (or_the_talk) who the talk is with. Finding them here starts no conversation."""
    world_state = game._session().world_state
    world_state.setdefault("flags", {})
    saved = talk_mode.snapshot(world_state)
    found = game.resolve_npc_reference(player_input, force_dialogue=True, allow_active_fallback=False)
    talk_mode.restore(world_state, saved)
    return found.get("npc") or (game._active_interlocutor() if or_the_talk else None)

def _front_recovery(player_input, listed):
    """D-240: the front reading came back unusable. Two lines need no model: a plain yes to the one offer that is open
    (the offer gate then checks it again against the line), and a plain walk out of town. Both go the way a read line
    would; anything less clear stays with the old chain."""
    import front_proposal
    import grounded_action
    import world_threads
    session = game._session()
    world = session.world_state
    if getattr(session, "_attack_asked", False) or getattr(session, "_heavy_asked", None):
        return None  # a question put to the player is waiting for its answer
    offers = listed["offers"]
    offer = next((row for row in offers if row["person_id"] == listed["speaking_with"]), None) or (
        offers[0] if len(offers) == 1 else None)
    if offer is not None:
        said = living_world.normalize_text(player_input).split()
        named_elsewhere = any(
            len(part) >= 3 and any(word.startswith(part[:4]) for word in said)
            for row in offers if row is not offer
            for part in (*living_world.normalize_text(next((p["name"] for p in listed["people"] if p["id"] == row["person_id"]), "")).split(),
                         *living_world.normalize_text(row.get("item") or "").split()))
        if named_elsewhere:
            return None  # the line names another open offer's owner or thing: not for the one spoken to
        person = next((npc for npc in game.active_npcs() if npc.get("id") == offer["person_id"]), None)
        thread = world_threads.by_id(world, offer["id"])
        if (person is not None and thread is not None and thread.get("status") == "offered"
                and world_threads.says_yes_in_a_longer_line(player_input, person, thread)):
            return {"kind": "offer_answer", "id": offer["id"], "person_id": offer["person_id"], "answer": "accept",
                    "recovered": True}
    if grounded_action.walks_out_of_town(session, player_input):
        return {"kind": "go_to", "id": front_proposal.WAY_OUT, "inside": False}
    return None

def _front_step(player_input, target_id, interaction_mode, combat_action, check_feature):
    """Roadmap step 5: the model reads a free line once; Python checks its ids. None leaves the old chain."""
    import front_proposal
    session = game._session()
    world = session.world_state
    if (not front_proposal.enabled() or getattr(session, "_front_reply", None) is not None
            or getattr(session, "_thread_gate_done", False)):
        return None
    fighting = world.get("combat", {}).get("active")
    import dragonborn_breath
    if fighting and (combat_action is not None or combat_lifecycle.is_attack_decision(session, player_input)
                     or dragonborn_breath.named(session, str(player_input))  # D-233: the breath is the engine's
                     or combat_lifecycle.is_flight(session, player_input)
                     or combat_lifecycle.is_standing_down(session, player_input)):
        return None  # a fight's own words need no reading
    # Said to a chosen person, a line is read when a clause hands coin now (D1), or when it is said to whoever serves
    # here so a room or an order can name its bound recipient without coin (D0); a say line to anyone else that names
    # no coin spends no model call. Either way the line stays with the person the player chose.
    typed_economic = interaction_mode == "say" and target_id is not None
    said_coin = (typed_economic and combat_action is None
                 and check_feature is None and not fighting and isinstance(player_input, str)
                 and front_proposal.names_coin(player_input))
    # In a fight, a line about the one chosen there that the fight's own words did not hear is read for a blow only
    # ('tatar yayımı bacağına doğrultup ateş ediyorum'); anything else it says still goes the old way.
    fought = (fighting and target_id is not None and interaction_mode not in {"say", "ask_dm"}
              and target_id in world.get("combat", {}).get("participants", []))
    # BM Task 1: a line said in conversation is read once, with or without a chosen person (talk_front decides which).
    import talk_front
    reads = talk_front.reads_say_line(session, player_input, target_id, interaction_mode, combat_action, check_feature)
    if (combat_action is not None or check_feature is not None
            or (interaction_mode in {"say", "ask_dm"} and not reads)
            or (target_id is not None and not typed_economic and not fought and not reads)):
        front_proposal.note(session, "skipped:typed")
        return None
    journey = world.get("journey")
    if journey and journey.get("status") != "ARRIVED":
        front_proposal.note(session, "skipped:journey")
        return None
    if not isinstance(player_input, str) or not player_input.strip() or player_input.strip().startswith("/"):
        front_proposal.note(session, "skipped:command" if isinstance(player_input, str) and player_input.strip() else "skipped:empty")  # D-245
        return None
    if adventure_play.inside_hideout(world):
        front_proposal.note(session, "skipped:hideout")  # the town's lists are not what is around the player here
        return None
    try:
        listed = front_proposal.listing(session)
    except Exception:  # broad: the old classifier chain is a whole fallback, so a broken list never fails the turn
        logging.getLogger("game_parts.turn_front").warning("Front list could not be built; the old chain reads the line", exc_info=True)
        front_proposal.note(session, "fallback:no_list")  # the old chain still has its own classifier call
        if reads:  # ... except for a conversation line: the speech call answers, so no classifier call is spent
            session._front_reply = {"intent": "unknown", "classifier_unusable": True}
            session._front_reply_called = False  # G10: held, but no provider was asked for it
        return None
    hint = interaction_adventure.hint(player_input, True)
    addressed = None
    if hint and typed_economic:  # in say mode the line is for the person chosen, whoever its words name
        addressed = next((npc for npc in game.active_npcs() if npc.get("id") == target_id), None)
    elif hint:
        addressed = game._addressed_in(player_input)
    # one reading answers for the whole turn, so it carries whatever proposal the line may need (a yes plays the stored one)
    reply = front_proposal.read_once(session, player_input, lambda: game.parse_player_intent(
        player_input, front_list=listed, recent_scene_narration=game._recent_player_visible_narration(),
        interaction_context=interaction_adventure.context(world, addressed, player_input) if hint else None,
        operation_hint=hint, require_conversation=hint == "information" and addressed is not None,
        allow_local_person_proposal=game.should_generate_npcs(player_input),
        allow_scene_detail_proposals=game._scene_detail_proposals_allowed(player_input, world, interaction_mode)))
    held = {key: value for key, value in reply.items() if key != "front"}
    session._front_reply = held
    if "front" not in reply:
        answered = len(reply) > 1  # a dead provider leaves only the bare unknown intent
        label = ("fallback:unusable" if reply.get("classifier_unusable")
                 else "fallback:no_front" if answered else "fallback:failed")
        recovered = (None if fighting or typed_economic or reads or label == "fallback:no_front"
                     else game._front_recovery(player_input, listed))
        if recovered is not None:
            front_proposal.note(session, f"{label}:{recovered['kind']}", reached=answered)
            recovered["recovered_from"] = label  # the gate may still overrule: the label then goes back
            return recovered
        front_proposal.note(session, label, reached=answered)
        game._coin_without_a_reading(player_input, target_id, listed)
        return None
    raw_front = reply.get("front")
    session._front_kind = raw_front.get("kind") if isinstance(raw_front, dict) else None  # D-094: speech stays speech
    if reads:
        session._front_talk = front_proposal.talk_reading(raw_front, listed, target_id)  # what the old owners ask
        if not typed_economic:  # said with no one chosen, or asked of the DM: the reading is held, the old chain goes on
            front_proposal.note(session, "typed:talk_read", reached=True)
            return None
    session._front_economic_none = True  # only the validated owner may prepare room/gift cards in a front-enabled turn
    economic = front_proposal.economic_route(reply, listed, target_id=target_id if typed_economic else None,
                                             line=player_input)
    if economic is not None:
        if fighting:
            front_proposal.note(session, "skipped:combat", reached=True)
            return None
        session._front_coin = front_proposal.coin_in(
            reply, player_input, moves=economic["purpose"] in ("gift", "tip")) if economic["valid"] else 0
        session._front_economic_front = raw_front  # the owner route reads the model's `deal` from it, if it gave one
        front_proposal.note(session, "front:economic", reached=True)
        return economic
    if said_coin:  # the line stays with the person the player chose; of the reading only its coin and deal count
        session._front_coin = front_proposal.coin_in(reply, player_input)
        route = {"kind": "speak_to", "id": target_id}
        front_proposal.note(session, "front:speak_to", reached=True)
        game._hand_over_coin(route, listed, raw_front)
        return route
    if typed_economic:
        front_proposal.note(session, "typed:no_economic", reached=True)
        person = raw_front.get("person_id") if isinstance(raw_front, dict) else None
        if (isinstance(raw_front, dict) and raw_front.get("kind") == "speak_to" and isinstance(person, str)
                and person != front_proposal.NONE and person in front_proposal._ids(listed["people"])
                and (target_id is None or target_id == person)):
            session._front_coin = front_proposal.coin_in(reply, player_input)  # evidence only; no tender/card
            route = {"kind": "speak_to", "id": person}
            deal = money_owner.read_deal(raw_front, listed)
            if deal is not None and (deal.kind == "room" or (deal.kind == "goods" and deal.goods_key)):
                # The model's own listed room or goods deal still stands when it read no economic intent: only the
                # money owner's decision opens its offer, and no coin moves (an offer asked for is no coin held out).
                game._hand_over_coin(route, listed, raw_front)
            return route
        return None  # typed speech never enters general movement/strike/person-repair routes
    import world_happenings
    import world_threads
    session._front_deed = front_proposal.deed_in(reply)
    session._front_check = "" if fighting else front_proposal.check_in(reply, player_input)  # D-094
    session._front_found = front_proposal.found_in(reply, player_input)
    session._front_rest = front_proposal.rest_in(reply, player_input)
    world_threads.note_want(world, front_proposal.want_in(reply, listed))
    threatened = front_proposal.threat_in(reply, listed)
    if threatened and not fighting and not game._heavy_allowed("threat", player_input, person_id=threatened):
        # D-109: a hurt tie is asked about first; nothing moves this turn (the dispatcher shows the question)
        front_proposal.note(session, "front:heavy_asked", reached=True)
        return {"kind": "heavy_asked", "what": "threat", "id": threatened, "deed": None, "said": str(player_input)}
    if threatened:
        world_happenings.threatened(world, world_threads._npc(world, threatened))
    if front_proposal.unclear_persuasion(session, raw_front) and not game._heavy_allowed("check", player_input, deed="Persuasion"):
        return front_proposal.persuasion_asked(session, player_input)  # D-177: maybe a plain hello; the roll is asked first
    session._front_coin = front_proposal.coin_in(reply, player_input)
    route = front_proposal.validate(reply, listed)
    if route == {"kind": "unclear"} and isinstance(raw_front, dict) and raw_front.get("kind") in {"take", "hand_over"}:
        route = {"kind": "unclear", "dropped": True}  # a take or hand-over that named nobody listed: no old word reader
    if (fighting and route is None and isinstance(raw_front, dict) and raw_front.get("kind") == "go_to"
            and raw_front.get("person_id") in world.get("combat", {}).get("participants", [])
            and raw_front.get("person_id") != "player"):
        # going to someone in the fight is a walk toward them: the reply's other half carries it as combat movement
        session._front_approach = raw_front["person_id"]
        held.update(intent="travel", action="approach", target={"type": "npc", "reference": ""})
    if fighting and (route is None or route["kind"] not in {"strike", "wield"}
                     or (fought and route["kind"] == "strike" and route["id"] != target_id)):
        return None  # in a fight the reading is only asked for a blow the fight's own words did not hear, or a draw
    word = front_proposal.person_word_in(reply)
    if word and (route is None or route["kind"] in {"speak_to", "talk_around"}):
        described = game._narrated_person(word, player_input, listed)
        if described is not None:
            route = {"kind": "speak_to", "id": described["id"]}
            game._session()._set_scene_active_npc(described, world.get("flags", {}).get("turn_index", 0))
        else:
            session._named_word = word
            if route is not None and route["kind"] == "speak_to":
                route = {"kind": "talk_around"}  # the repair gave the line to whoever was at hand; the reading named another
    import grounded_action
    if route is None or route["kind"] in {"speak_to", "talk_around", "unclear", "attempt"}:
        to_talk = grounded_action.walk_to_talk(session, player_input)
        if to_talk is not None:  # "Javrek ile konuşmaya gidiyorum": the one named is at their place, not here
            route = {"kind": "go_to", "id": to_talk, "inside": True}
    if route is not None and route["kind"] in {"look", "sit"}:
        out = grounded_action.walks_out(session, player_input)
        if out is not None:  # "dışarı çıkıp etrafa bakıyorum": the walk out is done, not only told
            route = {"kind": "go_to", "id": out, "inside": False}
    if route is None:
        front_proposal.note(session, "fallback:invalid", reached=True)
        if (isinstance(raw_front, dict) and raw_front.get("kind") == "go_to"
                and interaction_mode not in {"say", "ask_dm"}
                and not timed_gameplay.names_a_route(world, player_input)):  # a timed road is walked by its owner
            return front_proposal.beyond_list(raw_front, listed, world, player_input)  # E5: a walk to nowhere listed fails; one after a person follows
        return None
    import grounded_action
    import npc_speech_boundary
    if route["kind"] == "strike":
        if game._blow_stands(player_input):
            # Hurting the wrong person cannot be taken back: the words pick who, and with no name the one at hand.
            named = [npc["id"] for npc in combat_lifecycle.pointed_targets(session, player_input)]
            at_hand = listed["speaking_with"] if listed["speaking_with"] in [row["id"] for row in listed["people"]] else None
            if fought:
                route["id"] = target_id  # the opponent chosen in the fight stays the one struck (checked above)
            elif named:
                route["id"] = route["id"] if route["id"] in named else named[0]
            elif at_hand:
                route["id"] = at_hand
            spoken = living_world._text_outside_quotes(str(player_input))
            if (fighting and not route.get("with") and not game._has_explicit_attack_verb(spoken)
                    and not game._BLOW_WORDS.search(game._normalize_turkish_typos(spoken))
                    and not weapon_attack.names_a_move(session, spoken)):
                # In a fight the reading found a blow, but the words name no blow, no weapon of theirs and no move
                # the engine reads (a trip): the real moves are asked for and nothing rolls (as for an asked blow).
                route = {"kind": "which_move", "id": route["id"]}
            elif game._blow_in_the_words(player_input, route["id"]):
                session._front_strike = route
            elif npc_speech_boundary.player_supplied_quote(player_input):
                route = {"kind": "speak_to", "id": route["id"]}  # the blow is only in what they said
            else:  # the reading alone cannot start a fight: the player says whether this is one
                route = {"kind": "blow_asked", "id": route["id"], "with": route.get("with") or ""}
        else:  # a threat or a question about a blow: words, and they are for that person
            route = {"kind": "speak_to", "id": route["id"]}
    hearer = listed["speaking_with"] or (listed["people"][0]["id"] if len(listed["people"]) == 1 else None)
    if route["kind"] in {"attempt", "unclear", "look"} and hearer and not combat_lifecycle.is_attack_decision(
            session, player_input) and (
            grounded_action.hands_on_a_body(player_input)
            or (not route.get("thing") and npc_speech_boundary.player_supplied_quote(player_input))):
        route = {"kind": "speak_to", "id": hearer}  # a body in the line, or words in quotes: this is for the person here
    if route["kind"] in {"speak_to", "talk_around", "look", "attempt", "unclear"} and grounded_action.offered_walk(
            session, player_input) is not None:
        route = {"kind": "go_to", "id": None, "inside": False}  # "tamam geçiyorum": a yes to the way just shown
    if route["kind"] in {"talk_around", "wield"}:
        # the same reply's other half may not walk it after all (a drawn weapon is narrated, never classified again)
        held.update(intent="narrative", action="narrative", target={"type": "none", "reference": ""})
    elif (route["kind"] in {"attempt", "look", "unclear"} and held.get("intent") == "inventory"
          and (game._model_query_type_is_plausible(player_input) or equipment_economy._natural_inventory_query(player_input))):
        route = {"kind": "bag"}  # the label alone also fits moving a thing, and those lines have owners of their own
    if route["kind"] == "go_to" and route.get("id") == front_proposal.WAY_OUT and not grounded_action.leaves_town(
            session, player_input):
        route = {"kind": "attempt"}  # a tavern, a courtyard, a house's gate, the hills: a walk in town the list did not hold
    if (route["kind"] in {"attempt", "unclear", "look", "go_to", "talk_around"} and route.get("id") != front_proposal.WAY_OUT
            and grounded_action.heads_on_past_the_town(session, player_input)):
        route = {"kind": "go_to", "id": front_proposal.WAY_OUT, "inside": False}  # a small model takes this for a stroll
    if route["kind"] in {"sit", "attempt", "look", "unclear"} and timed_gameplay.names_a_stretch(world, player_input):
        route = {"kind": "wait"}  # 'akşama kadar', 'iki saat': whatever else the line does, it lets that time go by
    front_proposal.note(session, f"front:{route['kind']}", reached=True)
    game._hand_over_coin(route, listed, reply.get("front"))
    if route["kind"] == "look":
        held["intent"] = "observe"
    session._front_thing = route.get("thing")
    return route

def _defer_spoken_coin_offer(route):
    """Only an admitted gift/tip can ask this bound person before the card is shown."""
    session = game._session()
    amount = getattr(session, "_front_coin", 0)
    if (not route.get("valid") or route.get("purpose") not in ("gift", "tip")
            or type(amount) is not int or amount <= 0 or session.world_state.get("combat", {}).get("active")):
        return False
    person = next((n for n in game.active_npcs() if n.get("id") == route.get("id")), None)
    import equipment_economy
    import bold_acts
    import economic_actions
    if (person is None or not equipment_economy.npc_can_act(person)
            or economic_actions._held_deed(session.world_state, person) is not None
            or bold_acts.offer_still_open(session.world_state, person) is not None):
        return False
    session._spoken_coin_proposal = economic_actions.turn_proposal(route["purpose"], person["id"], amount_cp=amount)
    return True

def _record_spoken_coin_response(npc, response):
    session = game._session()
    proposal = getattr(session, "_spoken_coin_proposal", None)
    if proposal is None or proposal.recipient_id != npc.get("id"):
        return
    session._spoken_coin_proposal = None
    import economic_actions
    economic_actions.record_coin_response(session.world_state, npc, proposal.amount_cp, response,
                                          source_action_id=game.turn_source_key(session), purpose=proposal.purpose)
    session._spoken_coin_result = economic_actions.prepare_from_turn(session, proposal)

def _economic_listing(session, person):
    """The little list `_hand_over_coin` reads for a validated purpose route: this person and the goods they sell."""
    import front_proposal
    return {"people": [{"id": person["id"]}], "speaking_with": person["id"],
            "goods": front_proposal._goods_here(session.world_state, person, [person])}

def _front_economic_offer(route, player_input):
    """A current semantic purpose selects an existing engine owner, never a price or a debit."""
    import bold_acts
    import economic_actions
    session = game._session()
    session._coin_paid = None
    session._counter_held = None
    if session.world_state.get("combat", {}).get("active"):
        line = economic_actions._CLARIFY["combat_active"]
        return {"messages": session.messages, "narration": line, "model_calls": 0,
                "action_result": {"action": "narrative", "status": "clarification", "success": False,
                                  "reason_code": "combat_active", "state_changes": [], "direct_response": line}}
    person = next((npc for npc in game.active_npcs() if npc.get("id") == route.get("id")), None)
    if not route.get("valid") or person is None:
        result = bold_acts._reply(session, economic_actions._CLARIFY["npc_unknown"], "narrative", "clarification", None, [], reason_code="npc_unknown")
        result["action_result"]["success"] = False
        return result
    import equipment_economy
    if not equipment_economy.npc_can_act(person):
        line = economic_actions._CLARIFY["npc_not_here"]
        return {"messages": session.messages, "narration": line, "model_calls": 0,
                "action_result": {"action": "narrative", "status": "clarification", "success": False,
                                  "reason_code": "npc_not_here", "state_changes": [], "direct_response": line}}
    purpose = route["purpose"]
    coin = getattr(session, "_front_coin", 0)
    amount = coin if type(coin) is int and coin > 0 else None
    if purpose == "purchase":
        import shop_trade
        session._front_economic_none = True  # purchase stays with its counter, never room/gift guessing
        session._purchase_said = True  # whoever answers this line pays the player nothing for it (town_knowledge)
        if not shop_trade.is_vendor(session.world_state, person):
            return None  # someone who sells nothing answers the line in their own words; no card, no coin moves
        counter = shop_trade.counter(session.world_state)
        if (counter.get("vendor") or {}).get("npc_id") != person["id"] or counter["status"] != "ready":
            reason = "npc_refuses" if counter["reason"] == "vendor_refuses" else "shop_not_now" if counter["reason"] == "not_now" else "shop_unavailable"
            result = bold_acts._reply(session, economic_actions._CLARIFY.get(reason, economic_actions._CLARIFY["shop_unavailable"]), "narrative", "clarification", None, [], reason_code=reason)
            result["action_result"]["success"] = False
            return result
        game._hand_over_coin({"kind": "speak_to", "id": person["id"]}, game._economic_listing(session, person),
                        getattr(session, "_front_economic_front", None), owner_routed=True)
        if getattr(session, "_bribe_held_out", 0):
            return None  # the existing law owner has priority even for a serving guard
        decision = money_owner.current(session)
        if decision is not None and decision.kind == "room":
            purpose = "room"  # the money owner checked the room's price and purse: the room card owns this line
    if purpose == "purchase":
        if decision is not None and decision.kind != "goods":
            # The model's own `deal` disagrees with the purchase it also read: nothing opens (a card of another kind
            # is never the fallback), the coin stays in the purse, and the line says why.
            session._coin_paid = None
            return game._purchase_refused(session, person, amount, player_input)
        wanted = shop_trade.priced_in(bold_acts.fold(session, player_input))
        if wanted is not None:
            offered = bold_acts.shop_offer(session, player_input, person, requested=True)
        else:
            offered = bold_acts.standing_offer(session, person) if amount is not None else None
        session._coin_paid = None
        if offered is not None:
            if route.get("keep_change") and offered["action_result"]["status"] == "offer_open":
                opened = (session.world_state.get("flags") or {}).get("counter_offer_v1") or {}
                prepared = shop_trade.prepare_keep_change(session, person["id"], str(opened.get("key")), amount)
                result = bold_acts._reply(session, prepared.public_message, "narrative", prepared.status, None, [],
                                          reason_code=prepared.reason_code)
                result["action_result"]["success"] = prepared.status == "prepared"
                return result
            return offered
        return game._purchase_refused(session, person, amount, player_input)
    import world_reactions
    guard = world_reactions.arrester(session.world_state)
    if amount is not None and purpose in {"gift", "tip"} and guard is not None and guard.get("id") == person.get("id"):
        game._hand_over_coin({"kind": "speak_to", "id": person["id"]}, game._economic_listing(session, person),
                        getattr(session, "_front_economic_front", None), owner_routed=True)
        return None  # the existing law owner alone prepares/pauses/escalates a bribe
    if amount is not None and purpose in {"gift", "tip"} and bold_acts.offer_still_open(session.world_state, person):
        session._coin_paid = (amount, person, session.world_state.get("location"))
        standing = bold_acts.standing_offer(session, person)
        session._coin_paid = None
        if standing is not None:
            return standing
        result = bold_acts._reply(session, economic_actions._CLARIFY["shop_not_now"], "narrative", "clarification", None, [], reason_code="shop_not_now")
        result["action_result"]["success"] = False
        return result
    if purpose in {"room", "room_quote"}:
        if not bold_acts._SERVER.search(bold_acts.fold(session, str(person.get("role", "")))):
            return None  # no room to give or quote here: the line goes on to speak_to, not to the GIVE clarification
        if purpose == "room_quote":
            result = bold_acts.room_quote(session, person)
            action = result["action_result"]
            action.update(success=action["status"] == "quoted", reason_code="npc_refuses" if action["status"] == "refused" else None)
            return result
        if amount is not None:
            session._coin_paid = (amount, person, session.world_state.get("location"))
        room = bold_acts.take_room(session, player_input, server=person, requested=True)
        result = bold_acts._room_reply(session, room)
        result["action_result"].update(success=room["status"] in {"held", "offered"}, reason_code=room.get("reason_code"))
        return result
    prepared = economic_actions.prepare_from_turn(session, economic_actions.turn_proposal(
        purpose, person["id"], amount_cp=amount))
    result = bold_acts._reply(session, prepared.public_message, "narrative", prepared.status, None, [], reason_code=prepared.reason_code)
    result["action_result"]["success"] = prepared.status == "prepared"
    return result

def _purchase_refused(session, person, amount, player_input):
    """Why a purchase reading opens nothing, from the engine's own facts, in order: coin held out beyond the purse; a
    room asked for while one is held here; coin short of the price of what was asked for (the room, or goods this
    counter sells, by the reading's deal or the line's words); goods the line names off this counter's list; and
    otherwise only that what was wanted was not understood, with what this counter does sell."""
    import bold_acts
    import economic_actions
    import money_owner
    import refusals
    import shop_trade
    world = session.world_state
    deal = money_owner.read_deal(getattr(session, "_front_economic_front", None), game._economic_listing(session, person))
    room = deal is not None and deal.kind == "room"
    named = shop_trade.priced_in(player_input) if shop_trade.sells(world, person, player_input) else None
    key = deal.goods_key if deal is not None and deal.kind == "goods" and deal.goods_key else named and named[0]
    good = next((line for line in shop_trade.goods(world, person) if line["key"] == key), None)
    wanted = ("Gecelik oda", bold_acts.room_price(world, person)) if room else (
        (tr_case.upper_first(good["label"]), good["unit_cp"]) if good is not None else None)
    if amount is not None and amount > shop_trade.purse_cp(world):
        reason, line = "purse_below_base", economic_actions._CLARIFY["purse_below_base"]
    elif room and economic_actions._room_right(world) is not None:
        reason, line = "room_already_held", economic_actions._CLARIFY["room_already_held"]
    elif amount is not None and wanted is not None and amount < wanted[1]:
        reason = "coin_below_price"
        facts = {"item": wanted[0], "price": wanted[1], "coin": amount}
        line = refusals.text_for(reason, **facts)
        refusals.note(session, reason, npc_id=person.get("id"), **facts)
    else:
        off_list = shop_trade.priced_in(player_input) if named is None else None
        code = "not_sold_here" if off_list is not None else "goods_unclear"
        facts = {"have": bold_acts.on_the_counter(world, person), "item": off_list[1] if off_list else ""}
        reason = "not_sold_here" if off_list is not None else "no_stock_or_service"
        line = refusals.text_for(code, **facts)
        refusals.note(session, code, npc_id=person.get("id"), **facts)
    result = bold_acts._reply(session, line, "narrative", "clarification", None, [], reason_code=reason)
    result["action_result"]["success"] = False
    return result

def _hand_over_coin(route, listed, front=None, *, owner_routed=False):
    """Coin the reading saw held out: nothing is paid by it. It waits, with who it was for and where, for a card.

    `_coin_paid` is (amount, person, place_id): the room or the counter the decision names takes it as tender
    (`money_owner.claim`); otherwise the card after the reply is the decision's, never a gift by default. During an
    arrest it is the guard's to weigh only when it was held out to that guard or to nobody the reading could name; coin
    for someone else (the innkeeper) is no bribe.
    `front` is the reading itself: the money owner's decision for this turn is written from its `deal` and the coin,
    also when the deal came with no coin (D29: asking for a room or goods opens an offer and hands nothing over).
    `owner_routed` is a purpose route `front_proposal.economic_route` admitted: without a `deal` it writes no decision.
    """
    import bold_acts
    import money_owner
    session = game._session()
    session._counter_held = None
    amount = getattr(session, "_front_coin", 0)
    deal = money_owner.read_deal(front, listed)
    if (not amount and deal is None) or route["kind"] in {"strike", "blow_asked", "which_move"}:
        return
    import world_reactions
    taker = route.get("id") if route["kind"] == "speak_to" else route.get("person_id")
    taker = taker or listed["speaking_with"] or (listed["people"][0]["id"] if len(listed["people"]) == 1 else None)
    person = next((npc for npc in game.active_npcs() if npc.get("id") == taker), None)
    guard = world_reactions.arrester(session.world_state)
    if not (owner_routed and deal is None):
        # A purpose route the engine already validated (D0) with no deal from the model keeps the coin without a
        # decision: it is then a counter tender or a room's, read from the route, and never a structural guess.
        session._coin_decision = money_owner.decide(session.world_state, person=person, amount_cp=amount, deal=deal,
                                                    arrester=guard)
    if not amount:
        return  # an offer asked for with no coin in hand: the decision alone, nothing waits for a card
    if guard is not None and (person is None or person.get("id") == guard.get("id")):
        session._bribe_held_out = amount  # whether this coin moves is the guard's to decide
        return
    held_out = (amount, person, session.world_state.get("location"))
    decided = money_owner.current(session)
    if (bold_acts.offer_still_open(session.world_state, person) is not None
            and (decided.kind == "goods" if decided is not None else owner_routed)):
        # Coin the decision gives the counter is no gift: the counter trade alone takes it. Coin it gives a room, a
        # gift or a tip is theirs, never the open offer's tender (one amount, one operation: D5).
        session._counter_held = person
        session._coin_paid = held_out  # read by that offer as its tender, and never turned into a gift
        return
    session._coin_paid = held_out  # the decided card's tender or amount; never "now theirs" before it is confirmed

def _coin_without_a_reading(player_input, target_id, listed):
    """Owner rule G11 ("Eski kural karar versin", 2026-11-19): the reading gave no front, but coin the line's own words
    hold out now still gets the money owner's structural decision (no deal) and, after the reply, its note or card; it
    never vanishes silently. The figure is the words' own (none named, no coin). It is for the person chosen, else
    the one the line names, else whoever serves here when the line names one who serves ('hancıya'), else the one the
    talk is with; nobody found is the structural rule's own case (`_hand_over_coin`: the arresting guard weighs it).
    An unclear decision that names nobody is not kept: the coin stays in hand with no decision and is read as it is
    with no reading (`bold_acts.held_out_coin`): the room or the counter the words ask for takes it as tender or
    tells it back, else who it is for is asked (`money_owner.open_card_after_reply`). Nor a room decision when the
    words ask for no bed (a beer, a tip), nor, outside an arrest and a fight, an unclear one when they ask for a bed
    (D-402) or name a thing whoever serves here sells (D-429: a beer paid below its price opens the counter). A tip,
    plain coin or coin for talk to whoever serves keeps its unclear decision and note, as in a fight (R11)."""
    import bold_acts
    import front_proposal
    import money_owner
    import shop_trade
    import world_reactions
    session = game._session()
    amount = front_proposal.coin_in(None, player_input, moves=True)  # `moves`: the words' figure stands with no reading
    if not amount:
        return
    session._front_coin = amount
    if target_id is not None:
        person = next((npc for npc in game.active_npcs() if npc.get("id") == target_id), None)
    else:
        person = game._addressed_in(player_input, or_the_talk=False)
        if person is None and shop_trade.SERVER.search(
                living_world.normalize_text(living_world._text_outside_quotes(player_input))):
            person = bold_acts._server_here(session)
        person = person or game._active_interlocutor()
    game._hand_over_coin({"kind": "speak_to", "id": person["id"]} if person is not None else {"kind": "attempt"}, listed)
    decided = money_owner.current(session)
    folded = bold_acts.fold(session, player_input)
    bed = bool(bold_acts._ROOM.search(folded) and bold_acts._wants_the_bed(folded))
    calm = (world_reactions.arrester(session.world_state) is None
            and not (session.world_state.get("combat") or {}).get("active"))
    if decided is not None and ((decided.kind == "room" and not bed) or (decided.kind == "unclear" and (
            decided.npc_id is None
            or (calm and (bed or shop_trade.sells(session.world_state, person, player_input)))))):
        # No room asked for (a beer ordered, a tip): the structural room is a guess the words do not make. A bed asked
        # for outside an arrest is the room card's, as with the flag off (D-402); coin for a thing whoever serves sells
        # is their counter's to read (D-429). The coin stays in hand, undecided
        session._coin_decision = None

def _blow_stands(player_input):
    """The reading may name a blow; the words still decide that one is landing now, outside any quote."""
    import bold_acts
    import grounded_action
    spoken = living_world._text_outside_quotes(str(player_input))
    # 'itemez miyim? ... yumruğumu çakıyorum': a question asked before the blow is no question about the blow
    told = " ".join(part for part in re.split(r"(?<=[?.!])\s+", spoken) if not part.rstrip().endswith("?"))
    text = game._normalize_turkish_typos(told)
    return bool(text.strip()) and not ("?" in told or bold_acts._ASKS.search(text) or game._ENDS_IN_SPEECH.search(text)
                or game._NO_BLOW_NOW.search(text) or any(grounded_action._CONDITION_WORD.match(t) for t in text.split()))

def _blow_in_the_words(player_input, target_id):
    """A reading picks who; whether it starts a fight needs the player's own words, or a fight already there."""
    spoken = living_world._text_outside_quotes(str(player_input))
    target = next((npc for npc in game.active_npcs() if npc.get("id") == target_id), None)
    combat = game._session().world_state.get("combat", {})
    fought = bool(combat.get("active")) and target_id in combat.get("participants", [])
    return bool((isinstance(target, dict) and target.get("hostile")) or fought or game._has_explicit_attack_verb(spoken)
                or game._BLOW_WORDS.search(game._normalize_turkish_typos(spoken)))

def _ask_about_the_blow(person_id, player_input="", with_word=""):
    """Asked in the world, for this sitting only; the next line is the answer. A yes makes the asked line's blow."""
    session = game._session()
    who = next((npc for npc in game.active_npcs() if npc.get("id") == person_id), None)
    session._attack_asked = True
    session._blow_asked = person_id
    session._blow_asked_line = {"said": str(player_input or ""), "with": with_word or ""}
    line = f"{living_world.public_npc_name(who)} ile kavga mı başlatıyorsun?"
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "narrative", "status": "clarification", "success": False,
                              "outcome": "unconfirmed_blow", "state_changes": [], "direct_response": line}}

def _heavy_allowed(what, player_input, *, person_id=None, deed=None):
    """D-109: the asked crime or threat was answered yes, and this is the very line that was asked about."""
    confirmed = getattr(game._session(), "_heavy_confirmed", None)
    return (isinstance(confirmed, dict) and confirmed.get("said") == str(player_input)
            and [what, person_id, deed] in confirmed.get("allowed", []))

def _ask_before_the_heavy(asked):
    """D-109 (Kadir kararı 2026-11-15): a crime or a hurt tie is asked about first, in one short line; nothing moves.
    Asked for this sitting only, as "kavga mı başlatıyorsun?" is; a yes plays the asked line again (see
    ``_answered_heavy_question``). Eating and drinking are never asked: Undo takes those back."""
    session = game._session()
    held = {"what": asked.get("what"), "id": asked.get("id"), "deed": asked.get("deed"), "said": asked.get("said")}
    last = getattr(session, "_front_last_reading", None)
    if isinstance(last, tuple) and last[0] == asked.get("said"):
        held["reading"] = last[1]  # D-263: the yes plays this reading again, no second model call
    session._heavy_asked = held
    if asked["what"] == "threat":
        who = next((npc for npc in game.active_npcs() if npc.get("id") == asked.get("id")), None)
        name = living_world.public_npc_name(who) if who is not None else "o kişi"
        line = f"Bu, {name} ile aranı bozar. Gerçekten tehdit ediyor musun? (evet/hayır)"
    elif asked.get("deed") == "steal_look":  # D-224 review: the line looked; the reading alone said theft
        line = "Yalnız bakmakla kalmayıp çalmaya mı çalışıyorsun? Bu bir suç olarak kayda geçer. (evet/hayır)"
    elif asked["what"] == "check":  # D-177
        line = "Bu bir ikna denemesi mi? Zar atılır ve sonuç ona göre olur. (evet/hayır)"
    else:
        act = "çalıyor" if asked.get("deed") == "steal" else "ateşe veriyor"
        line = f"Bu bir suç olarak kayda geçer. Gerçekten {act} musun? (evet/hayır)"
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "narrative", "status": "clarification", "success": False,
                              "outcome": f"unconfirmed_{asked['what']}", "state_changes": [], "direct_response": line}}

def _answered_heavy_question(player_input):
    """D-109: a yes to the asked crime or threat is the asked line, now allowed; anything else forgets the question."""
    session = game._session()
    asked, session._heavy_asked = getattr(session, "_heavy_asked", None), None
    given, session._heavy_confirmed = getattr(session, "_heavy_confirmed", None), None
    if isinstance(asked, dict) and combat_lifecycle._says_yes(session, player_input):
        # D-109 review: a second question on the same line keeps the first yes (else the two would ask in turn forever);
        # the threat played again is not a second threat: its tie is made once while it is coming (world_happenings.tie)
        kept = given.get("allowed", []) if isinstance(given, dict) and given.get("said") == asked["said"] else []
        confirmed = {"said": asked["said"], "allowed": [*kept, [asked["what"], asked["id"], asked["deed"]]]}
        if isinstance(asked.get("reading"), dict):
            confirmed["reading"] = asked["reading"]
        session._heavy_confirmed = confirmed
        return asked["said"]
    return player_input

def _ask_which_move(person_id):
    """A yes to a blow whose words name no move the engine has (a trip): the real moves are offered, nothing rolls."""
    session = game._session()
    session._which_move = None
    who = next((npc for npc in game.active_npcs() if npc.get("id") == person_id), None)
    session._attack_asked = True  # the answer is read before any reading runs ahead (front_read_ahead)
    session._blow_asked = person_id
    session._blow_asked_line = {"said": "", "with": "", "choose": True}
    line = (f"Bu hamlenin oyunda bir karşılığı yok. {living_world.public_npc_name(who)} ile ne yapıyorsun: "
            "itip yere mi düşürüyorsun ('itiyorum', Shove), yoksa yumruk mu atıyorsun?")
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "narrative", "status": "clarification", "success": False,
                              "outcome": "unmapped_move", "state_changes": [], "direct_response": line}}

def _narrated_person(word, player_input, listed):
    """Someone the last narration described is there to be spoken to: Python makes them real, once."""
    import pocket
    folded = living_world.normalize_text(word)
    stem = folded[:max(4, len(folded) - 1)]
    if len(folded) < 4:
        return None
    here = game._conversation_npcs()
    same = next((npc for npc in here if stem in living_world.normalize_text(npc.get("role"))), None)
    told = living_world.normalize_text(pocket.told_as_there(game._recent_player_visible_narration(limit=4000)))
    scene = living_world.normalize_text(" ".join(str(row["name"]) for row in [*listed["things"], *listed["places"]]))
    if same is not None or stem not in told or stem in scene:  # the screen itself vouches for them, whatever word the player uses
        return same
    label = word.strip().capitalize()
    return game.create_npc_from_ai({"name": label, "role": label, "appearance": f"Az önce gözüne çarpan {word.strip()}",
                               "location": game._session().world_state.get("location"), "relationship": "neutral"},
                              request_key=game._local_person_request_key(word))

def front_read_ahead(player_input, target_id=None, interaction_mode=None):
    """The planner moves the player on word lists before the turn proper, so the reading has to come first."""
    import front_proposal
    session = game._session()
    session._front_ahead = False
    session._counter_held = None  # only this turn's reading may hold coin back for an open offer
    if not getattr(session, "_heavy_asked", None):
        session._heavy_confirmed = None  # D-109 review: a yes is spent with its turn; this line was never asked
    if (not front_proposal.enabled() or session.character.get("current_hp", 0) <= 0 or game.ensure_death_state()["dead"]
            or getattr(session, "_attack_asked", False) or getattr(session, "_heavy_asked", None)
            or not isinstance(player_input, str)
            or combat_lifecycle.surrender_yes(session, player_input)  # G9: the engine's own question, Python's yes
            or game._is_end_conversation_request(player_input)):
        return None
    interaction_mode = game._normalize_interaction_mode(interaction_mode)
    front_proposal.begin(session, typed=target_id is not None or interaction_mode in {"say", "ask_dm"})
    session._front_ahead = True
    session._front_read = game._front_step(player_input, target_id, interaction_mode, None, None)
    return session._front_read

def _front_offer_gate(route, player_input):
    """A yes or no the model read on a listed offer goes through the same writers as one the word lists read."""
    import town_knowledge
    import world_threads
    session = game._session()
    world = session.world_state
    person = next((npc for npc in game.active_npcs() if npc.get("id") == route["person_id"]), None)
    thread = world_threads.by_id(world, route["id"])
    if person is None or thread is None or thread.get("status") != "offered":
        return None
    try:
        reading = world_threads.read_answer(player_input, person, thread)
        says_other = reading["meaning"] in ({"decline", "withdraw"} if route["answer"] == "accept" else {"accept"})
        if reading["terms"] or world_threads.asks_for_pay(player_input) or says_other or "?" in player_input:
            # The model's yes or no is overruled, so Python's own reading of the line decides the turn.
            return game._thread_gate(player_input, person["id"], "say") or {"decision": None, "npc_id": person["id"]}
        session.require_player_can_act()
        gate = {"thread_id": route["id"], "npc_id": person["id"], "takes": route.get("takes", False),
                "works": route.get("works", False),
                "decision": "accepted" if route["answer"] == "accept" else "declined"}
        return game._carry_out_thread_turn(session, world, gate, person, player_input)
    except game.PlayerCannotAct:
        raise
    except Exception:
        town_knowledge.log_failure()
        session._thread_turn = None
        return None

def _line_gives(item_id, player_input):
    """The line names this thing, or it is the one thing there is to give."""
    import front_proposal
    import pocket
    world = game._session().world_state
    if game._NO_BLOW_NOW.search(game._normalize_turkish_typos(player_input)):
        return False  # 'vermiyorum': said, not done; the same reading the handed coin already uses
    bag = front_proposal._bag(world)
    stem = pocket._stem(next((row["name"] for row in bag if row["id"] == item_id), ""))
    return len(bag) == 1 or bool(stem and pocket._says_it(player_input, stem))

def _front_consume(route, player_input):
    """A listed item is consumed by its engine kind, never by the proposed prose."""
    import item_use
    import equipment_economy
    session = game._session()
    session.require_player_can_act()
    try:
        result = item_use.consume(session.world_state, route["item"])
    except equipment_economy.EquipmentError:
        return None
    if result.status != "consumed":
        return None
    if getattr(session, "_turn_notes", None) is None:
        session._turn_notes = []
    session._turn_notes.append((None, result.note))
    flags = session.world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    shown = result.note + "."
    session.messages.extend([{"role": "user", "content": player_input}, {"role": "assistant", "content": shown}])
    return {"reply": {"messages": session.messages, "narration": shown, "model_calls": 0,
                      "action_result": {"action": "consume", "status": "consumed", "success": True,
                                        "state_changes": ["inventory"], "direct_response": shown}}}

def _front_wield(route, player_input):
    """A bag weapon the reading named goes into the hand through `gear`; anything else changes nothing and the narrator
    hears that it did not happen. No weapon is looked for by the word (tasarım karar 33, 52). With a weapon already in
    hand, another one is taken only when the words name it: 'silahımı kaldırıp' is the one in hand (Dilim 3, Task 30).
    In a fight the draw is the turn's one free object interaction (Task 35)."""
    import action_economy
    import equipment_economy
    import gear
    import weapon_attack
    from api.dnd_2024_rules import SHIELD_ITEM_TOKENS
    from weapon_catalog import lookup
    session = game._session()
    session.require_player_can_act()
    world = session.world_state
    held = gear.wielded(world)
    item = next((i for i in world.get("inventory") or [] if isinstance(i, dict) and route.get("item")
                 and i.get("item_id") == route["item"]), None)
    data = lookup(item.get("weapon_id") or item.get("name")) if item is not None else None
    if (held is not None and data is not None and held.get("item_id") != item.get("item_id")
            and data["weapon_id"] not in weapon_attack.weapons_named(session, player_input)):
        return  # the words name no other weapon: the one in hand is the one meant, and nothing is drawn
    fighting = world.get("combat", {}).get("active")
    if fighting and world["combat"].get("current_actor_id") != "player":
        refusals.note(session, "out_of_turn")
        return
    down = world.get("shield_down")
    if route.get("item") and isinstance(down, dict) and down.get("item_id") == route["item"]:
        # The shield a two-handed weapon put down goes back on the arm in one step; in a fight it is a Utilize action,
        # not the free object interaction (Dilim 4A, Task 5).
        result = gear.don_shield(world, session.character, session=session)
        if getattr(session, "_turn_notes", None) is None:
            session._turn_notes = []
        if result.status == "donned":
            session._turn_notes.append((None, f"bu tur: {result.item['name']} koluna takıldı"))
        elif result.status == "hands_full":
            refusals.note(session, "invalid_hands")
        elif result.status == "no_action":
            refusals.note(session, "action_unavailable")
        else:  # not_down, no_shield: the record does not describe a shield that can go back on; nothing changed
            session._turn_notes.append((None, "olmadı: kalkan koluna takılamadı; hiçbir şey değişmedi"))
        return
    if item is not None and data is None and any(
            token in equipment_economy.label(item).casefold() for token in SHIELD_ITEM_TOKENS):
        if getattr(session, "_turn_notes", None) is None:
            session._turn_notes = []
        session._turn_notes.append((None, f"bu tur: {item['name']} için bir şey değişmedi"))  # not put down: no weapon lie
        return
    resources = action_economy.ensure(session).get("player", {}) if fighting else {}
    if resources.get("object_interaction"):
        refusals.note(session, "object_interaction_spent")
        return
    result = gear.draw(world, route["item"], character=session.character) if route.get("item") else None
    if result is not None and result.status in {"drawn", "already_held"}:
        if getattr(session, "_turn_notes", None) is None:
            session._turn_notes = []
        if fighting and result.status == "drawn":
            resources["object_interaction"] = True
        done = "eline alındı" if result.status == "drawn" else "zaten elinde"
        session._turn_notes.append((None, f"bu tur: {result.item['name']} {done}"))
        return
    if result is not None and result.status == "refused":  # in the bag, but the hand would not change: nothing did
        refusals.note(session, "invalid_hands")
        return
    have = ", ".join(str(item.get("name")) for item in gear.weapons_in_bag(world)) or "yok"
    refusals.note(session, "nothing_to_draw", have=have)

def _coin_not_parcel(session, world, person, item_id, player_input):
    """D-239: the line holds out coin, says money ('bahşiş', 'hediye', 'para'), or the reading gave it a money deal, and
    it names no parcel this person could take: no word of it meets the parcel's head noun ('duyurusu' of 'yol kapanışı
    duyurusu', never 'yol') or a parcel word ('mektup', 'paket', 'emanet'; 'bunu' only points)."""
    import front_proposal
    if (money_owner.current(session) is None and not front_proposal.names_coin(player_input)
            and not front_proposal.says_money(player_input)):
        return False
    if item_id is not None and not item_id.startswith("parcel:"):
        return False  # a plain thing from the bag goes only if the line means it (_line_gives)
    return game._names_no_parcel(world, person, item_id, player_input)

def _names_no_parcel(world, person, item_id, player_input):
    """No word of the line meets a parcel this person could take (see `_coin_not_parcel`)."""
    import world_threads
    from adventure import dialogue_jobs
    threads = ([world_threads.parcel_thread(world, item_id)] if item_id is not None
               else [job for job in [*world_threads.deliveries_to(world, person),
                                     *world_threads.late_parcels(world, person)]
                     if dialogue_jobs.holds_parcel(world, job)])
    table = world_threads.answer_table()
    roots = {game._word_root(word) for word in set(table["item_words"]) - set(table["pointing"])}
    roots |= {game._word_root(noun[-1]) for job in threads if job is not None
              for noun in [living_world.normalize_text(job.get("item_noun")).split()] if noun}
    words = living_world.normalize_text(living_world._text_outside_quotes(player_input)).split()
    return not any(word.startswith(root) for root in roots for word in words)

def _front_hand_over(route, player_input):
    """The model read a hand-over and named a listed thing. Python moves it; failing that the person hears the line."""
    import town_knowledge
    import world_threads
    from adventure import dialogue_jobs
    session = game._session()
    world = session.world_state
    person = next((npc for npc in game.active_npcs() if npc.get("id") == route["person_id"]), None)
    if person is None:
        return None
    heard = {"decision": None, "npc_id": person["id"]}
    item_id = route["item"]
    if game._coin_not_parcel(session, world, person, item_id, player_input):
        return heard  # D-239: a tip or coin that names no parcel is money for its card, never the job's delivery
    if world_threads.refuses_hand_over(player_input, lambda clause: not game._names_no_parcel(world, person, item_id, clause)):
        # D-276: 'takımı getirmedim', 'paketi vermiyorum': said, not done. Only a 'not' on the coin alone beside a plain
        # hand-over ('takımı getirdim, bahşiş vermiyorum') refuses no parcel. Nothing changes hands; the person hears so.
        refusals.note(session, "hand_over_refused", npc_id=person["id"])
        return heard
    asked ="?" in player_input or world_threads.says_later(player_input)
    due = dialogue_jobs.due_parcel(world, person) if item_id is None and not asked else None
    if item_id is None and not asked and due is None and any(
            dialogue_jobs.holds_parcel(world, job) for job in world_threads.deliveries_to(world, person)):
        # Two parcels for this person and the line names neither: nothing is handed, and the narrator hears why.
        refusals.note(session, "which_item_to_give", npc_id=person["id"])
        return heard
    if (item_id is None and due is None) or asked:
        session._empty_handed = item_id is None and not getattr(session, "_coin_paid", None)
        return game._thread_gate(player_input, person["id"], "say") or heard  # nothing named: the old reader, then their answer
    try:
        session.require_player_can_act()
        thread = due if item_id is None else world_threads.parcel_thread(world, item_id)
        if thread is None and not item_id.startswith("parcel:"):
            if game._line_gives(item_id, player_input):  # a plain thing never comes back: it goes only if the line means it
                given = dialogue_jobs.give_plain(world, item_id, person)
                if given is not None:
                    session._handed_note = given.get("name")
                    session._given_now = given.get("item_id")  # their reply this turn cannot hand it back (Task 33)
                return heard
            due = [job for job in [*world_threads.deliveries_to(world, person), *world_threads.late_parcels(world, person)]
                   if dialogue_jobs.holds_parcel(world, job)]
            thread = due[0] if len(due) == 1 else None  # 'al, bunu sana veriyorum' at the door it was sent to
        if thread is None:
            return heard
        decision = ("give" if thread in world_threads.deliveries_to(world, person)
                    else "give_late" if thread in world_threads.late_parcels(world, person) else None)
        if decision is None:
            return heard  # not theirs to take: it stays in hand and they say so
        return game._carry_out_thread_turn(session, world, {"thread_id": thread["thread_id"], "decision": decision,
                                                       "npc_id": person["id"]}, person, player_input)
    except game.PlayerCannotAct:
        raise
    except Exception:
        town_knowledge.log_failure()
        session._thread_turn = None
        return heard

def _front_work(route, player_input):
    """The model read work being done now. A promise or a question is still only words."""
    import town_knowledge
    import world_threads
    session = game._session()
    world = session.world_state
    person = next((npc for npc in game.active_npcs() if npc.get("id") == route["person_id"]), None)
    thread = world_threads.by_id(world, route["id"])
    if person is None or thread is None or thread.get("status") != "accepted":
        return None
    if "?" in player_input or world_threads.says_later(player_input):
        return game._thread_gate(player_input, person["id"], "say") or {"decision": None, "npc_id": person["id"]}
    try:
        session.require_player_can_act()
        return game._carry_out_thread_turn(session, world, {"thread_id": route["id"], "decision": "work",
                                                       "npc_id": person["id"]}, person, player_input)
    except game.PlayerCannotAct:
        raise
    except Exception:
        town_knowledge.log_failure()
        session._thread_turn = None
        return None

def _take_names_a_job(route):
    """A take that names a job's parcel (by the bag's id or by the job's own words) belongs to `_front_take`: the old
    word reader would answer a parcel already in the bag with the giver's speech."""
    import world_threads
    from adventure import dialogue_jobs
    if route.get("kind") != "take":
        return False
    world = game._session().world_state
    if route.get("item_id") and world_threads.parcel_thread(world, route["item_id"]) is not None:
        return True
    if route.get("word"):
        return dialogue_jobs.parcel_for_word(world, route["word"]).status != "none"
    jobs = [t for t in ((world_threads.view(world) or {}).get("threads") or [])
            if t.get("status") == "accepted" and t.get("quest_id")]
    return bool(jobs) and all(dialogue_jobs.already_in_hand(world, t) for t in jobs)  # nothing left to hand over

def _front_take(route, player_input):
    """A job's parcel, or a plain thing the screen showed; if neither, the prose may not say it was taken."""
    import pocket
    import town_knowledge
    import world_threads
    from adventure import dialogue_jobs
    session = game._session()
    world = session.world_state
    session.require_player_can_act()
    thread = world_threads.by_id(world, route["thread_id"]) if route.get("thread_id") else None
    person = next((npc for npc in game.active_npcs() if npc.get("id") == route.get("person_id")), None)

    def held(thread):
        """The parcel is in the bag: nothing is made and the job's own line says so."""
        return dialogue_jobs.already_reply(session, thread, player_input)

    try:
        item_id = route.get("item_id")
        if item_id:  # what the bag already holds is never made again
            bag_item = next((i for i in world.get("inventory", []) if isinstance(i, dict) and i.get("item_id") == item_id), None)
            held_job = world_threads.parcel_thread(world, item_id)
            if held_job is not None and dialogue_jobs.already_in_hand(world, held_job):
                return held(held_job)
            if bag_item is not None:
                return pocket.already_in_bag(session, player_input, str(bag_item.get("name") or "Eşya"))
        if thread is not None and person is not None:
            action = dialogue_jobs.hand_over(session, thread, person)
            return dialogue_jobs.take_reply(session, thread, player_input, action) if action else None
        match = dialogue_jobs.parcel_for_word(world, route.get("word") or "") if route.get("word") else None
        if match is not None and match.status == "one":
            job = match.thread
            if dialogue_jobs.already_in_hand(world, job):
                return held(job)
            giver = next((npc for npc in game.active_npcs() if npc.get("id") == job.get("owner_npc_id")), None)
            if giver is not None:
                action = dialogue_jobs.hand_over(session, job, giver)
                return dialogue_jobs.take_reply(session, job, player_input, action) if action else None
            refusals.note(session, "parcel_not_here", item=tr_case.upper_first(job.get("item_noun") or "paket"))
            taken = None
        elif match is not None and match.status == "many":
            refusals.note(session, "which_parcel")
            taken = None
        else:
            taken = pocket.take_named(session, player_input, route.get("word") or "")
    except Exception:
        town_knowledge.log_failure()
        taken = None
    if taken is None:
        session._nothing_taken = pocket.asked_for(player_input, route.get("word") or "")
    return taken

def _sleep_after_walk(walked, player_input, place_before, scene_plan=None):
    """"Hana gidip uyuyorum": the walk is only the first half of what was said."""
    world_state = game._session().world_state
    planned = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
    entered = isinstance(planned, dict) and planned.get("action") == "enter"  # the door was gone through before this turn ran
    if not isinstance(walked, dict) or world_state.get("combat", {}).get("active"):
        return
    moved = world_state.get("location") != place_before or entered
    receipt = walked.get("action_result") or {}
    if moved:
        import bold_acts
        import economic_actions
        key = game.turn_source_key(game._session())
        if key and economic_actions.prepared_by_action(world_state, source_action_id=key, purpose="room"):
            return  # this line already opened the room card; no second card, and no sleep before it is confirmed
        room = bold_acts.take_room(game._session(), player_input, walk_to_bed=True)
        if room is not None:
            game._session()._front_rest = ""  # the room part of the line is answered here, not read again
            walked["narration"] = f"{walked.get('narration') or ''} {room['line']}".strip()
            if room["coin_seen"]:
                walked.setdefault("action_result", {})["coin_seen_by"] = "room"
            if not room["room"]:
                return  # a card opened (or a no): sleeping waits for a room really held
    elif (receipt.get("action"), receipt.get("status")) != ("lodging", "rented"):
        return
    if not timed_gameplay._SLEEPING.search(game._normalize_turkish_typos(player_input)):
        return
    slept = timed_gameplay.resolve_input(game._session(), player_input)
    if slept is not None:
        game._session()._front_rest = ""  # the line's sleep is slept here, once
        walked["narration"] = f"{walked.get('narration') or ''} {slept['direct_response']}".strip()
        talk_mode.close(world_state, "rest")


def _front_route_turn(front, gate, player_input, interaction_mode, action_id, session_id):
    if front is not None and front["kind"] == "wield" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            game._front_wield(front, player_input)  # the turn goes on to the narrator, who reads the hand and the note on the card
    if front is not None and front["kind"] == "take" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            taken = game._front_take(front, player_input)
        if taken is not None:
            return taken
    if front is not None and front["kind"] == "wait" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        passed = timed_gameplay.pass_time(game._session(), player_input)
        if passed is not None:
            flags = game._session().world_state.setdefault("flags", {})
            flags["turn_index"] = flags.get("turn_index", 0) + 1
            return {"messages": game._session().messages, "narration": passed["direct_response"], "model_calls": 0,
                    "action_result": passed}
    if front is not None and front["kind"] == "walk_failed" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        text = game._fallback_for_action_result(player_input, {"action": "travel", "status": "failed"})
        flags = game._session().world_state.setdefault("flags", {})
        flags["turn_index"] = flags.get("turn_index", 0) + 1
        return {"messages": game._session().messages, "narration": text, "model_calls": 1,
                "action_result": {"action": "travel", "status": "failed", "success": False,
                                  "state_changes": [], "direct_response": text}}
    if front is not None and front["kind"] == "follow" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        import everyday_actions
        import front_proposal
        import grounded_action
        front_proposal.note(game._session(), "front:follow", reached=True)
        world = game._session().world_state
        flags = world.setdefault("flags", {})
        outcome = everyday_actions.follow_route(world, front, turn=int(flags.get("turn_index", 0)) + 1)
        if outcome["place_id"]:
            grounded_action.note_last(world, outcome["place_id"])  # "oraya" now means the door the figure went in by
        flags["turn_index"] = flags.get("turn_index", 0) + 1
        game._session().messages.extend([{"role": "user", "content": player_input},
                                         {"role": "assistant", "content": outcome["text"]}])
        return {"messages": game._session().messages, "narration": outcome["text"], "model_calls": 1,
                "action_result": {"action": "everyday_action", "kind": "follow", "status": "resolved",
                                  "success": True, "state_changes": [], "direct_response": outcome["text"],
                                  **({"npc_id": outcome["npc_id"]} if outcome["npc_id"] else {}),
                                  **({"place_id": outcome["place_id"]} if outcome["place_id"] else {})}}
    if front is not None and front["kind"] == "go_to" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        import front_proposal
        import grounded_action
        road_warning = None
        if front["id"] == front_proposal.WAY_OUT:
            refused = grounded_action.road_goes_on(game._session(), player_input)
            road_warning = (refused or {}).get("road_warning")
            if refused is not None and road_warning is None:
                return refused
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            walked = grounded_action.resolve_turn(game._session(), player_input, listed_place=front)
        if walked is not None:
            if road_warning:
                walked["narration"] = f"{road_warning} {walked.get('narration') or ''}".strip()
            return walked
        front_proposal.note(game._session(), "fallback:no_walk")
        place = (game._session().world_state.get("locations") or {}).get(front["id"])
        if isinstance(place, dict) and place.get("name") and not str(front["id"]).startswith(front_proposal.KIND_PREFIX):
            # "Hana nasıl giderim?": the place the reading named is what the answer is about, not a rumour
            game._session()._front_talk = {"asks": "place", "place_id": front["id"]}
    return None
