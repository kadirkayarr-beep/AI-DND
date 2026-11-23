import game
import action_economy
import adventure.play as adventure_play
from api.core_resolution import (
    resolution_action_scope,
)
import combat_lifecycle
import contextlib
import copy
from dataclasses import dataclass
import equipment_economy
import initiative
import interaction_adventure
import living_world
import local_dialogue
import money_owner
import re
import timed_gameplay
from typing import Optional, List, Dict, Any
import held_weapon
import monster_sense
import campaign_time
import incidents.hooks as incident_hooks
import json
import scheduled_events
import sys
import talk_front
import talk_mode


@dataclass
class ResolvedTurn:
    """Structure to hold resolved game state before narration."""
    action_result: Dict[str, Any]
    fallback_response: str
    raw_result: Dict[str, Any]
    requires_narration: bool = True
    safety_reason_code: Optional[str] = None
    safety_handling: str = "accepted"
    quest_outcomes: Optional[List[Dict[str, Any]]] = None
    npc_target: Optional[Dict[str, Any]] = None
    target_id: Optional[str] = None
    lore_context: Optional[Dict[str, Any]] = None
    intent_source: str = "deterministic"
    intent_model_calls: int = 0
    messages: Optional[List[Dict[str, Any]]] = None
    allow_new_npcs: bool = False
    allow_new_features: bool = False
    allow_new_locations: bool = False
    allow_new_shops: bool = False
    expected_location_change: bool = False
    scene_plan: Optional[Dict[str, Any]] = None
    quest_world_before: Optional[Dict[str, Any]] = None

DEBUG_MODE = False

class TurnResolved(Exception):
    def __init__(self, raw_result, resolved_turn):
        self.raw_result = raw_result
        self.resolved_turn = resolved_turn

def turn_source_key(session):
    """The key of the turn now running, shared by every card it prepares and by its own change of place.

    It is set once at the start of `_run_player_turn` (the action id, or a fresh `turn:` key) and is the same in and
    out of the action's resolution scope; outside a turn it is None, and then no card is spared by a move.
    """
    return getattr(session, "_economic_turn_key", None)

def run_player_turn(
    player_input, messages=None, target_id=None, scene_plan=None,
    action_id=None, session_id=None, combat_action=None, interaction_mode=None,
    check_feature=None, check_evidence=None,
):
    session = game._session()
    try:
        return game._run_player_turn_owned(player_input, messages, target_id, scene_plan, action_id, session_id,
                                      combat_action, interaction_mode, check_feature, check_evidence)
    finally:
        game._clear_turn_transients(session)

def _run_player_turn_owned(
    player_input, messages, target_id, scene_plan, action_id, session_id, combat_action, interaction_mode,
    check_feature, check_evidence,
):
    if check_feature is None:
        import front_proposal
        front_on = front_proposal.enabled()
        result = None
        session = game._session()
        if front_on and not getattr(session, "_front_ahead", False):
            front_proposal.begin(session, typed=(combat_action is not None or target_id is not None
                                                 or interaction_mode in {"say", "ask_dm"}))
        try:
            result = game._run_player_turn(player_input, messages, target_id, scene_plan, action_id,
                                      session_id, combat_action, interaction_mode)
            return result
        finally:
            if front_on:
                front_proposal.end(session)
                front_proposal.log_turn(session, result)
    money_owner.forget_turn(game._session())  # no reading begins a check turn; an earlier line's coin is not this one's
    game._session()._front_talk = None  # ... nor an earlier line's talk reading (read-ahead may have set one)
    if type(check_feature) is not str or check_feature not in game.CHECK_FEATURES:
        raise combat_lifecycle.CombatRequestError('invalid_check_feature', 'Unknown check feature.', 400)
    if check_evidence is not None and type(check_evidence) is not list:
        raise ValueError('Check evidence must be a caller-owned list.')
    game.primal_knowledge_check_admission(player_input, interaction_mode=interaction_mode,
                                     combat_action=combat_action, scene_plan=scene_plan, target_id=target_id,
                                     check_feature=check_feature)
    snapshot = game._session()._capture_runtime_snapshot()
    evidence = []
    try:
        result = game._run_player_turn(player_input, messages, target_id, scene_plan, action_id,
                                  session_id, combat_action, interaction_mode,
                                  check_feature=check_feature, check_evidence=evidence)
        if result.get('action_result', {}).get('action') != 'skill_check' or len(evidence) != 1:
            raise game._immediate_check_refusal(check_feature, 'No supported immediate check was resolved.')
    except game.IntentInfrastructureError as error:
        # Preserve the API's retryable 503 path, not a permanent feature refusal.
        game._session()._restore_runtime_snapshot(snapshot)
        return game._intent_infrastructure_result(error)
    except Exception:
        game._session()._restore_runtime_snapshot(snapshot)
        raise
    if check_evidence is not None:
        check_evidence.extend(evidence)
    return result

def _run_player_turn(
    player_input,
    messages=None,
    target_id=None,
    scene_plan=None,
    action_id=None,
    session_id=None,
    combat_action=None,
    interaction_mode=None,
    check_feature=None,
    check_evidence=None,
):
    """One turn under one economic source key (A4): the action id, or a fresh `turn:` key for a turn without one.

    The key is set only when none is set yet, so a nested run uses the outer one, and only the run that set it
    clears it. Cards prepared anywhere in this run, in or out of the resolution scope, carry it.
    """
    import secrets
    session = game._session()
    owns_key = not getattr(session, "_economic_turn_key", None)
    if owns_key:
        session._economic_turn_key = action_id or f"turn:{secrets.token_hex(8)}"
    try:
        return game._run_player_turn_keyed(player_input, messages, target_id, scene_plan, action_id, session_id,
                                      combat_action, interaction_mode, check_feature, check_evidence)
    finally:
        if owns_key:
            session._economic_turn_key = None

def _run_player_turn_keyed(
    player_input,
    messages=None,
    target_id=None,
    scene_plan=None,
    action_id=None,
    session_id=None,
    combat_action=None,
    interaction_mode=None,
    check_feature=None,
    check_evidence=None,
):
    game._session()._adventure_player_text = player_input if isinstance(player_input, str) else ""
    game._session()._asks_for = None  # what the person was asked for in this turn's conversation, set by the speech answer
    import fallen
    fallen.wake(game._session())
    before = copy.deepcopy(game._session().world_state)
    before_hp = game._session().character.get("current_hp")
    messages_before = len(game._session().messages)
    try:
        runtime_snapshot = game._session()._capture_runtime_snapshot()
    except AttributeError:
        # A test die without getstate cannot be snapshotted; the API restores its own.
        runtime_snapshot = None
    turn_index_before = game._session().world_state.get("flags", {}).get("turn_index", 0)
    place_before = game._session().world_state.get("location")
    try:
        result = game._dispatch_player_turn(
            player_input,
            messages,
            target_id,
            scene_plan,
            action_id,
            session_id,
            combat_action,
            interaction_mode,
            **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {}),
        )
        import bold_acts
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            game._sleep_after_walk(result, player_input, place_before, scene_plan)
            result = game._person_answers_stock(result, player_input, messages, target_id, interaction_mode,
                                           action_id, session_id, runtime_snapshot)
            result = game._the_rest_of_the_line(result, messages, action_id, session_id, place_before)
            game._tell_the_coin(result)
            bold_acts.answer_to_killing(game._session(), result)
            bold_acts.answer_to_known_doer(game._session(), result)
            import world_reactions
            world_reactions.answer(game._session(), result)
            import fallen
            fallen.wake(game._session())  # the next look sees who got up while this turn's time passed
    except game.IntentInfrastructureError as error:
        if check_feature is not None:
            # The outer opt-in owner restores its earlier snapshot and formats
            # this typed failure. No arbitrary status dictionary bypasses proof.
            raise
        # The classifier could not run: nothing was decided, so nothing is kept.
        if runtime_snapshot is not None:
            game._session()._restore_runtime_snapshot(runtime_snapshot)
        else:
            game._session().world_state.setdefault("flags", {})["turn_index"] = turn_index_before
        return game._intent_infrastructure_result(error)
    import dialogue_runtime
    dialogue_runtime.observe_turn(game._session(), before, before_hp, result, player_input, action_id)
    action_result = result.get("action_result") if isinstance(result, dict) else None
    resolution = (
        action_result.get("resolution")
        if isinstance(action_result, dict)
        else None
    )
    source_action_id = (
        action_id
        or (action_result.get("action_id") if isinstance(action_result, dict) else None)
        or (
            resolution.get("action_id")
            if isinstance(resolution, dict)
            else None
        )
    )
    living_world.record_entry_target_reference(
        game._session().world_state,
        action_result=action_result,
        source_action_id=source_action_id,
        source_turn_index=game._session().world_state.get("flags", {}).get("turn_index", 0),
        source_location_id=before.get("location"),
    )
    if (
        isinstance(action_result, dict)
        and action_result.get("action") in {"action_economy", "attack", "death_save"}
        and not action_result.get("quest_outcomes")
    ):
        transitions = game._session().evaluate_quest_events(before, action_result)
        if transitions:
            action_result["quest_outcomes"] = transitions
            evidence = result.get("_engine_event_evidence")
            if isinstance(evidence, dict):
                evidence["quest_outcomes"] = copy.deepcopy(transitions)
    # Direct locked-owner routes bypass finish_turn; consume their resolved clock
    # and outcomes here without altering their mechanics or call budget.
    if not result.pop("_interaction_consumed", False) and not (
        isinstance(action_result, dict)
        and (
            action_result.get("status") in {
                "experimental_attributed_speech",
                "unaccepted_experimental_action",
            }
            or action_result.get("experimental") is True
        )
    ):
        interaction_adventure.consume(
            game._session(), result.get("action_result", {}), before, player_input
        )
    import xp
    if xp.job_grants_due(game._session().world_state):
        # A job finished in this turn (by any route, direct ones included) is paid here, before the turn is answered.
        # A grant that cannot be recorded is forfeited (B1): the job keeps its close and its wage, and its thread is
        # marked so no later turn owes it again.
        game._session()._forfeit_unrecordable_xp(xp.award_finished_jobs, game._session().world_state, game._session().character)
        xp.forfeit_jobs(game._session().world_state, xp.job_grants_due(game._session().world_state))
    if isinstance(result, dict) and isinstance(action_result, dict):
        game._session()._publish_level_up(action_result)
        local_dialogue.remember_native_reply(
            game._session().world_state, action_result, player_input, result.get("narration")
        )
        # D-061: a forfeited award's line ("<X> XP kaydedilemedi: <neden>.") goes the same way as the award line.
        lines = [xp.award_line(action_result["level_up"])] if isinstance(action_result.get("level_up"), dict) else []
        lines += game._session()._take_xp_unrecorded()
        if lines:
            # After every narration check (and after a person's reply is remembered): Python's own line from the
            # award's facts, in the reply and in this turn's assistant message (no model call, no number from the model).
            line = " ".join(lines)
            result["narration"] = f"{result.get('narration') or ''} {line}".strip()
            for row in reversed(game._session().messages[messages_before:]):
                if isinstance(row, dict) and row.get("role") == "assistant":
                    row["content"] = f"{row.get('content') or ''} {line}".strip()
                    break
    return result

def _dispatch_player_turn(
    player_input, messages=None, target_id=None, scene_plan=None,
    action_id=None, session_id=None, combat_action=None, interaction_mode=None,
    check_feature=None, check_evidence=None,
):
    interaction_mode = game._normalize_interaction_mode(interaction_mode)
    if not getattr(game._session(), "_thread_gate_done", False):
        game._session()._thread_turn = None
    if game.ensure_death_state()["dead"]:
        raise game.PlayerCannotAct("Ölü karakter eylem gerçekleştiremez.")
    if game._session().character.get("current_hp", 0) <= 0:
        # A body on the ground has no moves left: whatever is typed or clicked is this turn's save.
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            return game._run_player_turn_internal(player_input, messages, target_id, {"direct_result": None},
                                             "do", action_id)
    game._reopen_public_doors()
    player_input = combat_lifecycle.answered_attack_question(game._session(), player_input)
    player_input = game._answered_heavy_question(player_input)  # D-109
    ahead = getattr(game._session(), "_front_read", None) if getattr(game._session(), "_front_ahead", False) else None
    if isinstance(ahead, dict) and ahead.get("kind") == "heavy_asked":
        return game._ask_before_the_heavy(ahead)  # D-109: read ahead of the turn; asked before any owner answers
    surrender_answer = (combat_lifecycle.answered_surrender_question(game._session(), player_input)
                        if combat_action is None else None)
    if surrender_answer is not None:
        player_input, combat_action, target_id = surrender_answer  # the asked blow, at the asked foe only
    if getattr(game._session(), "_which_move", None):
        return game._ask_which_move(game._session()._which_move)
    owner_reply = game._owner_module_reply(player_input, interaction_mode)
    if owner_reply is not None:
        return {
            "messages": game._session().messages,
            "narration": owner_reply.get("direct_response") or "",
            "model_calls": 0,
            "action_result": owner_reply,
        }
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
    read = getattr(game._session(), "_front_read", None) if getattr(game._session(), "_front_ahead", False) else None
    import front_proposal
    if (front_proposal.enabled() and not getattr(game._session(), "_front_ahead", False)
            and not getattr(game._session(), "_front_strike", None)):
        read = game._front_step(player_input, target_id, interaction_mode, combat_action, check_feature)
        game._session()._front_read = read
        game._session()._front_ahead = True
    if read is not None and read.get("kind") == "heavy_asked":
        return game._ask_before_the_heavy(read)  # D-109: asked, nothing moved
    if getattr(game._session(), "_front_strike", None):
        target_id, interaction_mode = game._session()._front_strike["id"], "do"
    elif (target_id is not None and combat_action is None
          and not game._session().world_state.get("combat", {}).get("active")):
        import bold_acts
        if bold_acts.is_act_not_talk(game._session(), player_input):
            # D-172: with the person chosen by the talk button, a scare or a look-over is still an act on them, not a
            # line to them; it takes the same route as without the button, so the dice and the narrator answer.
            interaction_mode, target_id = "do", None
    import spell_effects
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"}
            and not getattr(game._session(), "_front_strike", None) and spell_effects.named(player_input) is not None):
        # 4C.5: a narrative spell (or one not in the engine yet) is the spell owner's, never a walk, a knock or an item
        # move; the engine answers it inside the turn and the narrator tells the fact.
        return game._dispatch_turn_body(player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                                   session_id, check_feature, check_evidence)
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
    confessed = False
    if (combat_action is None and interaction_mode != "ask_dm"
            and not game._session().world_state.get("combat", {}).get("active")):
        import bold_acts
        confessed = bold_acts.hear_confession(game._session(), player_input)
    if read is not None and read.get("kind") == "economic":
        economic_result = None
        if not confessed:
            with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
                economic_result = None if game._defer_spoken_coin_offer(read) else game._front_economic_offer(read, player_input)
        if economic_result is not None:
            return economic_result
        read = {"kind": "speak_to", "id": read["id"]}
        game._session()._front_read = read
        interaction_mode, target_id = "say", read["id"]  # law/confession delegation keeps the bound hearer
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"} and not confessed
            and not game._session().world_state.get("combat", {}).get("active")):
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            deed = getattr(game._session(), "_front_deed", None)
            bold = bold_acts.resolve(
                game._session(), player_input, deed,
                # D-109: a crime is asked about first, whether the reading or the old words (no reading) found it
                ask=lambda act: None if game._heavy_allowed("deed", player_input, deed=act)
                else game._ask_before_the_heavy({"what": "deed", "id": None, "deed": act, "said": str(player_input)}))
        if bold is not None:
            return bold
    elif (combat_action is None and interaction_mode == "say" and isinstance(player_input, str)
          and not player_input.lstrip().startswith("/") and not game._session().world_state.get("combat", {}).get("active")):
        # Said straight to whoever serves, a want on the list opens the same counter offer: speech never sells.
        import bold_acts
        import shop_trade
        hearer = next((npc for npc in game.active_npcs() if npc.get("id") == target_id), None) if target_id else None
        if target_id is None or shop_trade.is_vendor(game._session().world_state, hearer):
            offered = bold_acts.shop_offer(game._session(), player_input, hearer)
            if offered is not None:
                return offered
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
    # D-095: "muhafızın kesesi var mı diye inceliyorum" is about someone else's purse; never answer with the player's
    if read is not None and read["kind"] == "bag" and not game._SOMEONE_ELSES_PURSE.search(
            game._normalize_turkish_typos(living_world._text_outside_quotes(player_input))):
        listed = equipment_economy.execute(game._session(), "çantamda ne var")
        if listed is not None:

            return listed
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
            paper_read = bound_text.read_turn(game._session(), player_input, looked_at,
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
    front = read if getattr(game._session(), "_front_ahead", False) else game._front_step(
        player_input, target_id, interaction_mode, combat_action, check_feature)
    if front is not None and front["kind"] == "blow_asked":
        return game._ask_about_the_blow(front["id"], player_input, front.get("with"))
    if front is not None and front["kind"] == "which_move":
        return game._ask_which_move(front["id"])
    held_for = getattr(game._session(), "_counter_held", None)
    game._session()._counter_held = None
    if held_for is not None:
        import bold_acts
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            standing = bold_acts.standing_offer(game._session(), held_for)
        if standing is not None:
            return standing
        game._session()._coin_paid = None  # coin held out for an open offer is never a gift, even when the offer closed
    if front is not None and front["kind"] == "speak_to":
        import bold_acts
        if target_id is not None or not bold_acts.is_act_not_talk(game._session(), player_input):  # D-098, D-099: an act
            interaction_mode, target_id = "say", front["id"]
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"} and target_id is None and front is None
            and game._ENDS_IN_SPEECH.search(game._normalize_turkish_typos(player_input))):
        hearer = game._active_interlocutor()  # "dedim sana" is said to the one already being talked to
        if hearer is not None:
            interaction_mode, target_id = "say", hearer["id"]
    gate = None
    if (combat_action is None and not getattr(game._session(), "_thread_gate_done", False)
            and not getattr(game._session(), "_front_strike", None)):  # a blow stood behind is no answer to an offer
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            gate = (None if front is not None and (front.get("dropped") or front["kind"] == "wield"
                                                   or game._take_names_a_job(front))
                    else game._front_offer_gate(front, player_input) if front is not None and front["kind"] == "offer_answer"
                    else game._front_consume(front, player_input) if front is not None and front["kind"] == "consume"
                    else game._front_hand_over(front, player_input) if front is not None and front["kind"] == "hand_over"
                    else game._front_work(front, player_input) if front is not None and front["kind"] == "work"
                    else game._thread_gate(player_input, target_id, interaction_mode, front=front))
        if front is not None and front.get("recovered_from") and front["kind"] == "offer_answer" and not (
                gate is not None and gate.get("decision") == "accepted"):
            import front_proposal
            front_proposal.note(game._session(), front["recovered_from"])  # the gate did not take the yes: no recovery to claim
        if gate is not None and gate.get("reply") is not None:
            return gate["reply"]
        if gate is not None and gate.get("paid_line"):
            game._session()._thread_gate_done = True  # the coin moved; the person still says their word, by any route
            try:
                said = game._dispatch_player_turn(
                    player_input, messages, gate["npc_id"], scene_plan, action_id, session_id, combat_action,
                    "say", check_feature, check_evidence,
                )
            finally:
                game._session()._thread_gate_done = False
            said["narration"] = f"{said.get('narration') or ''} {gate['paid_line']}".strip()
            return said
        if gate is not None and gate.get("moving"):
            game._session()._thread_turn = None
            game._session()._thread_gate_done = True  # the line goes on as the walk it also was
            try:
                walked = game._dispatch_player_turn(
                    player_input, messages, target_id, scene_plan, action_id, session_id, combat_action,
                    interaction_mode, check_feature, check_evidence,
                )
            finally:
                game._session()._thread_gate_done = False
            walked["narration"] = f"{gate['moving']} {walked.get('narration') or ''}".strip()
            return walked
        if gate is not None:
            interaction_mode, target_id = "say", gate["npc_id"]
    routed = game._front_route_turn(front, gate, player_input, interaction_mode, action_id, session_id)
    if routed is not None:
        return routed
    if combat_action is None:
        import dialogue_runtime
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            free_dialogue = dialogue_runtime.resolve_turn(
                game._session(), player_input, interaction_mode=interaction_mode,
                target_id=target_id, action_id=action_id,
            )
        if free_dialogue is not None:
            return free_dialogue
    if combat_action is None and interaction_mode in {"say", "ask_dm"}:
        if (
            interaction_mode == "ask_dm"
            and equipment_economy._natural_inventory_query(player_input)
        ):
            equipment_result = equipment_economy.execute(game._session(), player_input)
            if equipment_result is not None:
                return equipment_result
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
    import exploration
    if (combat_action is None and game._session().character.get("current_hp", 0) > 0
            and exploration.native_request(player_input, game._session())):
        with resolution_action_scope(action_id, session_id):
            exploration_result = exploration.resolve_command(game._session(), player_input)
        if exploration_result is not None:
            return exploration_result
    import authored_dungeon
    if combat_action is None:
        dungeon_result = authored_dungeon.resolve_command(game._session(), player_input)
        if dungeon_result is not None:
            return dungeon_result
    planning = (combat_action is None
                and not game._session().world_state.get("combat", {}).get("active")
                and not getattr(game._session(), "_front_strike", None)
                and interaction_adventure.compound_plan(player_input) is not None)
    if (combat_action is None and not planning
            and not combat_lifecycle.is_attack_decision(game._session(), player_input)):
        equipment_result = equipment_economy.execute(game._session(), player_input)
        if equipment_result is not None:
            return equipment_result
    import spell_scope
    spell_command = (spell_scope.natural_command(player_input, target_id)
                     if combat_action is None and not planning else None)
    if spell_command is not None:
        surrender_question = combat_lifecycle.surrendered_strike_question(
            game._session(), player_input, target_id, spell_command)  # a harmful spell is asked like a blow (D-036)
        if surrender_question is not None:
            return surrender_question
        return action_economy.execute(game._session(), spell_command, action_id, session_id)
    import bounded_encounter
    if not planning:
        bounded_encounter.refresh(game._session())
    native = (bounded_encounter.resolve_command(game._session(), player_input)
              if combat_action is None and not planning else None)
    if native is not None:
        return native
    import monster_combat
    if combat_action is None and game._session().world_state.get("combat", {}).get("active"):
        with initiative.atomic(game._session()):
            proposal_result = monster_combat.player_response(game._session(), player_input, target_id)
            if proposal_result is not None:
                return proposal_result
    if combat_action is None and combat_lifecycle.is_standing_down(game._session(), player_input):
        with resolution_action_scope(action_id, session_id):
            settled = combat_lifecycle.stand_down(game._session(), action_id, session_id)
        if settled is not None:
            return settled
    if combat_action is None and combat_lifecycle.is_flight(game._session(), player_input):
        with resolution_action_scope(action_id, session_id):
            fled = combat_lifecycle.flee(game._session(), action_id, session_id)
        if fled is not None:
            return fled
    command = combat_action or (None if planning else
                               action_economy.natural_command(game._session(), player_input, target_id))
    surrender_question = combat_lifecycle.surrendered_strike_question(game._session(), player_input, target_id, command)
    if surrender_question is not None:
        return surrender_question
    if command:
        return action_economy.execute(game._session(), command, action_id, session_id)
    if action_economy.pending_reaction(game._session()):
        raise combat_lifecycle.CombatRequestError("reaction_pending", "Resolve or decline the reaction opportunity.", 400)
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
    game._session()._walk_off = None
    try:
        combat_lifecycle.validate_request(game._session(), player_input, target_id)
    except combat_lifecycle.CombatRequestError as error:
        if error.code != "combat_travel":
            raise
        # held for the turn's reading: a walk toward someone in the fight is combat movement (_approach_turn takes it);
        # any other reading of the line is refused as walking off, as before
        game._session()._walk_off = error
    try:
        result = game._dispatch_turn_body(player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                                     session_id, check_feature, check_evidence)
        walk, game._session()._walk_off = game._session()._walk_off, None
    except BaseException:
        game._session()._walk_off = None
        raise
    if walk is not None:
        raise walk
    return result

def _dispatch_turn_body(player_input, messages, target_id, scene_plan, interaction_mode, action_id, session_id,
                        check_feature, check_evidence):
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

def _spoken_rest_of_turn(grounded, player_input, messages, action_id, session_id):
    """"...tezgâha geçiyorum, bir bira istiyorum": after the walk the words reach the person."""
    import grounded_action
    request = grounded_action.spoken_request(player_input)
    result = grounded.get("action_result") or {}
    if not request or result.get("status") not in {"completed", "partial"}:
        return grounded
    flags = game._session().world_state.get("flags", {})
    present = game.active_npcs()
    npc = next(
        (candidate for candidate in present if candidate.get("id") == flags.get("active_npc_id")),
        None,
    ) or (game.most_plausible_addressee(present, request) if present else None)
    if not isinstance(npc, dict):
        return grounded
    with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
        try:
            spoken = game._run_player_turn_internal(request, messages, npc["id"], None, "say", action_id)
        except game.TurnResolved as resolved:
            spoken = game._narrate_resolved_turn(resolved.resolved_turn, request, messages, npc["id"])
    spoken["narration"] = f"{grounded['narration']} {spoken['narration']}"
    spoken["model_calls"] = spoken.get("model_calls", 0) + grounded.get("model_calls", 0)
    return spoken

def _current_procedural_entity_ids():
    world_state = game._session().world_state
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
        for shop in world_state.get("shops", [])
        if isinstance(shop, dict)
        and shop.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(shop.get("id"), str)
    )
    return ids

def _keep_town_portrait(action_result, narration):
    """D-249: the first model-written arrival at a settlement leaves its two opening lines on the record.

    Quoted speech and unbacked money go (same form limits as arrival_narration); never overwritten, never the Python line.
    """
    if not isinstance(action_result, dict) or action_result.get("action") != "travel" or not action_result.get("success"):
        return
    if action_result.get("status") != "completed" or not isinstance(narration, str):
        return
    import local_places
    world = game._session().world_state
    place = world.get("location")
    record = world.get("locations", {}).get(place)
    if not isinstance(record, dict) or record.get("town_portrait") or local_places.settlement_of(world, place) != place:
        return
    # First arrival only: a trip that began inside this settlement (or at an unknown place) is a return, not an arrival.
    start = action_result.get("previous_location")
    if not start or local_places.settlement_of(world, start) == place:
        return
    import town_knowledge
    from arrival_narration import _QUOTES
    # «…» and ‘…’ are speech too: written as “…” so the shared speech-span split and the quote check see them.
    narration = re.sub(r"«([^»]*)»|‘([^’]*)’", lambda span: f"“{span.group(1) or span.group(2)}”", narration)
    sentences = [part.strip() for part in game._split_sentences_keep_speech(narration.strip())
                 if part.strip() and not any(mark in part for mark in _QUOTES) and not town_knowledge.names_coin(part)]
    clean = town_knowledge.without_unbacked_money(" ".join(sentences)) or ""
    portrait = " ".join(game._split_sentences_keep_speech(clean)[:2]).strip()
    if portrait:
        record["town_portrait"] = portrait

def _owner_module_reply(player_input, interaction_mode):
    """Slash-owner commands stay on their modules. SAY and ASK_DM stay speech."""
    text = player_input.strip() if isinstance(player_input, str) else ""
    if interaction_mode in {"say", "ask_dm"} and not text.startswith("/"):
        return None
    session = game._session()
    world = session.world_state if isinstance(session.world_state, dict) else {}
    combat = world.get("combat")
    if (
        isinstance(combat, dict)
        and combat.get("active")
        and combat.get("current_actor_id") not in (None, "player")
    ):
        return None
    for owner in (monster_sense, held_weapon):
        reply = owner.resolve_turn(session, player_input)
        if reply is not None:
            return reply
    return None

def _run_player_turn_internal(
    player_input, messages=None, target_id=None, scene_plan=None,
    interaction_mode=None, action_id=None, check_feature=None, check_evidence=None,
):
    def resolve_intent(*args, **kwargs):
        if check_feature is not None:
            kwargs.update(check_feature=check_feature, check_evidence=check_evidence)
        return game.execute_intent(*args, **kwargs)

    interaction_mode = game._normalize_interaction_mode(interaction_mode)
    narration_model_calls = 0
    narration_source = "deterministic_system"
    """Intent → rules → validated updates → committed state → narration."""
    intent_model_calls = 0
    classifier_unusable = False
    intent_source = "deterministic"
    # A scene pre-parse is a real intent call: it counts toward the two-call
    # turn budget and is reused instead of asking the same question twice.
    scene_preparse_model_calls = 0
    preparsed_scene_intent = None
    # G10: with the front reading on, a reply held before this point was the turn's classifier call (when a provider
    # was asked for it). A step below that reuses the held reply spends no call, so telemetry tells exactly that
    # reading, once, whether or not a step reused it, plus the dialogue reply asked below (never answered by a held reply).
    held_reading = getattr(game._session(), "_front_reply", None) is not None
    reading_calls = int(held_reading and getattr(game._session(), "_front_reply_called", False))
    speech_intent_calls = 0

    def told_intent_calls():
        if not held_reading:
            return intent_model_calls
        return reading_calls + speech_intent_calls
    world_state = game._session().world_state
    entry_death_state = game.ensure_death_state()
    entry_combat = game.ensure_combat_state()
    entry_identity = entry_combat.get("combat_id") if entry_combat["active"] else None
    entry_actor = entry_combat.get("current_actor_id")
    if entry_death_state["dead"]:
        raise game.PlayerCannotAct("Ölü karakter eylem gerçekleştiremez.")
    if game._session().character.get("current_hp", 0) == 0 and not entry_combat["active"]:
        return game._down_outside_combat_turn(player_input)
    if (
        game._session().character.get("current_hp", 0) <= 0
        or world_state.get("player_combat_status") == "unconscious"
    ) and not (
        entry_combat["active"]
        and entry_combat["current_actor_id"] == "player"
    ):
        raise game.PlayerCannotAct("Bilinçsiz karakter eylem gerçekleştiremez.")
    local_npc_place_request = (
        interaction_mode != "ask_dm"
        and local_dialogue.is_local_place_recommendation_request(player_input)
        and game._has_active_local_npc_focus_for_place_request(
            world_state, target_id=target_id
        )
    )
    world_subject_question = (
        True if interaction_mode == "ask_dm"
        else False if interaction_mode == "say" or local_npc_place_request
        else local_dialogue.is_world_subject_question(player_input)
    )
    scene_exploration_question = living_world.is_exploratory_structure_question(
        player_input, interaction_mode
    )
    if messages is None:
        messages = game._session().messages
    scene_plan = (
        scene_plan
        if isinstance(scene_plan, dict)
        else game.plan_living_world_turn(
            player_input,
            target_id=target_id,
            interaction_mode=interaction_mode,
        )
    )
    planned_direct = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
    if (
        isinstance(planned_direct, dict)
        and planned_direct.get("action") == "explore"
        and planned_direct.get("status") == "observed"
        and game._scene_observation_proposal_turn(
            player_input, world_state, interaction_mode
        )
    ):
        scene_plan = {**scene_plan, "direct_result": None}
    injected_lore_context = getattr(game._session(), "lore_authority_context", None)
    lore_context = game._prepare_lore_authority_context(injected_lore_context)
    quest_world_before = copy.deepcopy(world_state)
    flags = world_state.setdefault("flags", {})
    flags["turn_index"] = flags.get("turn_index", 0) + 1
    turn_index = flags["turn_index"]
    npc_target = None
    allow_new_npcs = False
    allow_new_features = False
    allow_new_locations = False
    allow_new_shops = False
    expected_location_change = False
    conversation_resolution = None
    conversation_state_before = copy.deepcopy(
        interaction_adventure.get(world_state)
    )
    active_conversation_before = talk_mode.snapshot(world_state)

    def procedural_entity_ids():
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

    def finish_turn(
        action_result,
        narration,
        quest_outcomes=None,
        *,
        safety_reason_code=None,
        safety_handling="accepted",
        record_safety=True,
        is_final=False,
    ):
        interaction_adventure.get(world_state)
        if narration is None and isinstance(action_result, dict):
            # A recorded goal carries no sentence of its own: the narrator tells it, and this line stands only if it cannot.
            narration = game._natural_unresolved_action_response(player_input, action_result)
            is_final = False
        if (
            isinstance(action_result, dict)
            and action_result.get("status") == "proposal_rejected"
            and conversation_resolution is None
        ):
            world_state[interaction_adventure.KEY] = copy.deepcopy(
                conversation_state_before
            )
            talk_mode.restore(world_state, {key: value for key, value in active_conversation_before.items()
                                            if value is not None})
        is_experimental = (
            isinstance(action_result, dict)
            and (
                action_result.get("status") in {
                    "experimental_attributed_speech",
                    "unaccepted_experimental_action",
                }
                or action_result.get("experimental") is True
            )
        )
        interaction_consumed = is_experimental
        if (
            isinstance(action_result, dict)
            and action_result.get("status") != "awaiting_proposal"
            and not is_experimental
        ):
            interaction_adventure.consume(
                game._session(), action_result, quest_world_before, player_input
            )
            interaction_consumed = True
            if action_result.get("action") in {"query", "explore"}:
                beat = interaction_adventure.initiative_beat(world_state)
                if beat:
                    action_result["npc_initiative"] = beat
                    narration = narration + " " + beat["summary"]
        if isinstance(action_result, dict) and action_result.get("action") in {"attack", "death_save"}:
            current = game.ensure_combat_state()
            identity = entry_identity or current.get("combat_id")
            if identity:
                action_result.setdefault("combat_id", identity)
                action_result.setdefault("actor", entry_actor if
                                         action_result.get("outcome") == "enemy_turn_resolved" else "player")
                action_result["combat_status"] = current["status"]
                action_result["round"] = current["round"]
                action_result["current_turn_index"] = current["current_turn_index"]
                action_result["current_actor_id"] = current["current_actor_id"]
                action_result["turn_owner"] = current["current_actor_id"]
        if isinstance(action_result, dict) and "campaign_time" in world_state:
            previous_clock = quest_world_before.get("campaign_time", {})
            elapsed = world_state["campaign_time"]["elapsed_seconds"] - previous_clock.get(
                "elapsed_seconds", world_state["campaign_time"]["elapsed_seconds"]
            )
            action_result.setdefault("time_result", {
                "elapsed_seconds": max(0, elapsed),
                "after": campaign_time.public_time(world_state),
                "player_known_events": scheduled_events.public_events(world_state),
            })
        if game._is_internal_player_facing_text(narration):
            narration = game._natural_unresolved_action_response(
                player_input, action_result
            )
            if (
                isinstance(action_result, dict)
                and game._is_internal_player_facing_text(
                    action_result.get("direct_response")
                )
            ):
                action_result["direct_response"] = narration
        if record_safety:
            game._record_narration_safety(
                {
                    "reason_code": safety_reason_code,
                    "trigger_span": None,
                    "scene_type": game._narration_scene_type(action_result),
                },
                safety_handling,
            )
        if (
            isinstance(conversation_resolution, dict)
            and conversation_resolution.get("topic_relation") == "topic_change"
            and not conversation_resolution.get("answer_field")
            and isinstance(action_result, dict)
            and not is_experimental
        ):
            interaction_adventure.retire_conversation_focus(world_state)
        if (
            isinstance(action_result, dict)
            and isinstance(npc_target, dict)
            and isinstance(npc_target.get("id"), str)
            and action_result.get("action") != "character_query"
        ):
            action_result.setdefault("npc_id", npc_target["id"])
        if isinstance(action_result, dict) and isinstance(scene_plan, dict):
            action_result["state_changes"] = list(dict.fromkeys(
                list(action_result.get("state_changes", []))
                + list(scene_plan.get("state_changes", []))
            ))
        result = {"action_result": action_result, "narration": narration,
                  "_interaction_consumed": interaction_consumed}
        result["_engine_event_evidence"] = {
            "authority": "python_engine",
            "action_id": f"turn:{turn_index}",
            "turn_index": turn_index,
            "quest_outcomes": copy.deepcopy(quest_outcomes or []),
            "procedural_entity_ids": sorted(
                procedural_entity_ids() - procedural_ids_before
            ),
            "_procedural_ids_before": procedural_ids_before,
        }

        def _incident_before_skipped_narration():
            # Look, rest, and a completed move can be answered without a narrator.
            # The incident owner still sees that authoritative action. A later
            # narrated turn uses the existing door in _narrate_resolved_turn.
            if not isinstance(action_result, dict):
                return
            emergence = incident_hooks.before_narration(
                game._session(),
                action_result=action_result,
                player_text=player_input,
                location_changed=world_state.get("location") != quest_world_before.get("location"),
            )
            spent = emergence.get("model_calls") if isinstance(emergence, dict) else 0
            if type(spent) is int and spent > 0:
                nonlocal narration_model_calls
                narration_model_calls += spent

        if is_final:
            _incident_before_skipped_narration()
            result["_engine_event_evidence"]["procedural_entity_ids"] = sorted(
                procedural_entity_ids() - procedural_ids_before
            )
            result["_engine_event_evidence"].pop("_procedural_ids_before", None)
            if "telemetry" not in result["_engine_event_evidence"]:
                result["_engine_event_evidence"]["telemetry"] = {
                    "intent_model_calls": told_intent_calls(),
                    "narration_model_calls": narration_model_calls,
                    "total_model_calls": told_intent_calls() + narration_model_calls,
                    "intent_source": intent_source,
                    "narration_source": narration_source,
                    "fallback_reason": safety_reason_code,
                    "narration_validation_result": safety_handling if safety_reason_code else "accepted",
                    "resolved_action_type": action_result.get("action", "unknown") if isinstance(action_result, dict) else "unknown",
                }
            return result

        status = action_result.get("status") if isinstance(action_result, dict) else None
        action = action_result.get("action") if isinstance(action_result, dict) else None

        system_deterministic = False
        if status in (
            "invalid_target", "limit_reached", "unsupported",
            "explicitly_declined", "unsupported_combat_action",
            "player_unconscious", "unverified", "clarification",
            "answered_from_npc_memory", "answered_from_campaign_state",
            "answered_from_loaded_lore",
        ):
            system_deterministic = True
        elif action in (
            "shop_economy",
            "shop_inquiry",
            "character_query",
            "death_save",
        ):
            system_deterministic = True
        elif action == "query" and action_result.get("direct_response"):
            system_deterministic = True
        elif status == "not_executed" and action_result.get("direct_response"):
            system_deterministic = True  # no blow ran, so no narrator gets to land one
        elif safety_handling in ("python_memory_response", "python_scene_response"):
            system_deterministic = True

        if system_deterministic:
            _incident_before_skipped_narration()
            result["_engine_event_evidence"].pop("_procedural_ids_before", None)
            narration_src = "deterministic_system"
            if safety_handling in ("python_memory_response", "python_memory_fallback"):
                narration_src = "python_memory_response"
            elif safety_reason_code:
                narration_src = "deterministic_fallback"

            result["_engine_event_evidence"]["telemetry"] = {
                "intent_model_calls": told_intent_calls(),
                "narration_model_calls": 0,
                "total_model_calls": told_intent_calls(),
                "intent_source": intent_source,
                "narration_source": narration_src,
                "fallback_reason": safety_reason_code,
                "narration_validation_result": safety_handling if safety_reason_code else "accepted",
                "resolved_action_type": action_result.get("action", "unknown") if isinstance(action_result, dict) else "unknown",
            }
            return result

        resolved = game.ResolvedTurn(
            action_result=action_result,
            fallback_response=narration,
            raw_result=result,
            requires_narration=True,
            safety_reason_code=safety_reason_code,
            safety_handling=safety_handling,
            quest_outcomes=quest_outcomes,
            npc_target=npc_target,
            target_id=target_id,
            lore_context=lore_context,
            intent_source=intent_source,
            intent_model_calls=told_intent_calls(),
            messages=messages,
            allow_new_npcs=allow_new_npcs,
            allow_new_features=allow_new_features,
            allow_new_locations=allow_new_locations,
            allow_new_shops=allow_new_shops,
            expected_location_change=expected_location_change,
            scene_plan=scene_plan,
            quest_world_before=quest_world_before,
        )
        raise game.TurnResolved(result, resolved)

    import spell_effects
    spell_reading = (spell_effects.named(player_input)
                     if interaction_mode not in {"say", "ask_dm"} and isinstance(player_input, str)
                     and game._session().character.get("current_hp", 0) > 0 else None)  # a body on the ground saves
    if spell_reading is not None:
        # 4C.5: the engine decides and commits (a fact, or a truthful line that nothing was cast); a resolved fact goes
        # to the turn narrator (narration only, the line is its fallback), a refusal is told as it is.
        cast = spell_effects.resolve(game._session(), spell_reading)
        return finish_turn(cast["action_result"], cast["narration"])

    def finish_conversation_rejection(target):
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

    def finish_conversation_resolution(resolution, target):
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

    def validate_interaction_conversation(raw, target, required):
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

    walked_up = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
    said_after = game._said_after_approach(player_input)
    if (isinstance(walked_up, dict) and walked_up.get("action") == "approach"
            and walked_up.get("status") == "completed" and said_after
            and interaction_mode not in {"say", "ask_dm"}):
        spoken = game._run_player_turn_internal(
            said_after, messages, walked_up.get("target_id"), None, "say", action_id
        )
        spoken["narration"] = f"{walked_up['direct_response']} {spoken['narration']}"
        return spoken
    sleeping = bool(timed_gameplay._SLEEPING.search(game._normalize_turkish_typos(player_input))
                    or timed_gameplay.is_timed_wait(player_input))
    # A blow the reading found lands now, however many clauses lead up to it: it is no plan to keep.
    compound = (None if sleeping or getattr(game._session(), "_front_strike", None)
                else interaction_adventure.compound_plan(player_input))
    # "Marek'in yanına gidiyorum, bir bira istiyorum": the second clause is said to him.
    import grounded_action
    request = grounded_action.spoken_request(player_input) if compound is not None else None
    if request and not entry_combat["active"] and interaction_mode not in {"say", "ask_dm"}:
        named = game.resolve_npc_reference(player_input)
        if named.get("status") == "found":
            game._set_scene_active_npc(named["npc"], flags.get("turn_index", 0) + 1)
        person = next(
            (npc for npc in game.active_npcs() if npc.get("id") == flags.get("active_npc_id")), None
        )
        if person is not None:
            living_world.set_player_position(
                world_state, world_state.get("location"), "standing", person["id"]
            )
            return game._run_player_turn_internal(
                request, messages, person["id"], None, "say", action_id
            )
    # Talking with someone here, the clauses may be said to them: the turn's reading decides below, before any plan.
    held_plan = None
    if (compound is not None and not entry_combat["active"] and interaction_mode not in {"say", "ask_dm"}
            and talk_mode.current(world_state) is not None):
        held_plan, compound = compound, None
    if (compound is not None and not entry_combat["active"]
            and interaction_mode not in {"say", "ask_dm"}):
        # These steps are exact player spans, not model paraphrases. Recording
        # them does not require an addressee or permission to execute any step.
        intent_source = "python_compound_plan"
        action_result = interaction_adventure.resolve(game._session(), player_input, compound)
        # Recording intentions is not executing them, but the player still gets
        # the attempt narrated; the prose cannot move anyone or change anything.
        fallback = action_result.pop("direct_response", "")
        return finish_turn(action_result, fallback)

    game.ensure_campaign_clock()
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

    combat = game.ensure_combat_state()
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

    planned_direct = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
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

    # Character-sheet questions do not require an unambiguous NPC. Keep the
    # existing combat and explicit-target validation boundaries intact.
    character_reply = (
        game.known_character_answer(player_input)
        if not combat["active"] and interaction_mode != "say"
        else None
    )
    focused_npc_before_targeting = game._active_interlocutor()
    if target_id is not None:
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
        npc_target = None
        selected_npc_target = next(
            (npc for npc in (game._conversation_npcs() if interaction_mode == "say" else game.active_npcs())
             if isinstance(npc, dict) and npc.get("id") == target_id), None,
        ) if not combat["active"] else None
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
    else:
        planned_npc_id = (
            scene_plan.get("npc_target_id")
            if isinstance(scene_plan, dict)
            else None
        )
        npc_target = (
            next(
                (
                    npc for npc in (game._conversation_npcs() if interaction_mode == "say" else game.active_npcs())
                    if isinstance(npc, dict) and npc.get("id") == planned_npc_id
                ),
                None,
            )
            if not world_subject_question
            else None
        )
        if npc_target is not None:
            talk_mode.open(world_state, npc_target["id"], turn=flags.get("turn_index", 0))
        explicit_dialogue_resolution = (
            game.resolve_npc_reference(
                player_input,
                force_dialogue=True,
                allow_active_fallback=False,
            )
            if (interaction_mode == "say" or (interaction_mode in {None, "do"} and game._npc_speech_enabled()))
            and (world_subject_question or scene_exploration_question)
            else {"status": "none", "npc": None}
        )
        if (interaction_mode != "say"
                and explicit_dialogue_resolution["status"] == "found"
                and not game._is_spoken_to(player_input, explicit_dialogue_resolution["npc"])):
            explicit_dialogue_resolution = {"status": "none", "npc": None}
        if (
            explicit_dialogue_resolution["status"] == "none"
            and game._npc_speech_enabled()
            and interaction_mode in {None, "do", "say"}
            and focused_npc_before_targeting is not None
            and game.is_npc_dialogue_input(player_input)
        ):
            focused_resolution = game.resolve_npc_reference(player_input, force_dialogue=True)
            if (focused_resolution.get("status") == "found"
                    and focused_resolution["npc"].get("id") == focused_npc_before_targeting.get("id")):
                # An already validated, current interlocutor owns the follow-up.
                # A topic word must not discard it or spend a target-parser call.
                explicit_dialogue_resolution = focused_resolution
        if explicit_dialogue_resolution["status"] == "found":
            world_subject_question = False
            scene_exploration_question = False
        # "none" has three meanings here: a world/scene question deliberately
        # kept away from NPC routing, a non-dialogue action, or dialogue whose
        # sole-NPC fallback was postponed so the model may resolve a described
        # person. Only the last one may consult the model or apply the fallback.
        dialogue_fallback_deferred = False
        if explicit_dialogue_resolution["status"] == "found":
            npc_resolution = explicit_dialogue_resolution
        elif (
            (world_subject_question or scene_exploration_question)
            and not local_dialogue.is_local_dialogue_input(player_input)
            and not (
                local_dialogue.is_local_place_recommendation_request(player_input)
                and game.resolve_npc_reference(
                    player_input,
                    force_dialogue=True,
                    allow_active_fallback=False,
                ).get("status") == "found"
            )
        ):
            npc_resolution = {"status": "none", "npc": None}
        elif npc_target is not None:
            npc_resolution = {"status": "found", "npc": npc_target}
        else:
            dialogue_fallback_deferred = (
                interaction_mode == "say" or game.is_npc_dialogue_input(player_input)
            )
            npc_resolution = game.resolve_npc_reference(
                player_input,
                **(
                    {
                        "force_dialogue": True,
                        "allow_active_fallback": False,
                    }
                    if dialogue_fallback_deferred
                    else {}
                )
            )
        preparsed_scene_intent = None
        if (
            dialogue_fallback_deferred
            and npc_resolution.get("status") == "none"
            and not combat["active"]
            and not game._detect_query_type(player_input)
            and not game.known_character_answer(player_input)
            and not game._is_player_name_inquiry_to_npc(player_input)
            and not local_dialogue.personal_question_kind(player_input)
            and interaction_mode != "ask_dm"
            and game.is_npc_dialogue_input(player_input)
            # The pre-parse can only pick a visible person or propose a local
            # one; with neither possible it cannot change this turn.
            and (
                game._intent_scene_npc_candidates()
                or game.should_generate_npcs(player_input)
            )
        ):
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
            scene_preparse_model_calls = 1
            intent_model_calls = scene_preparse_model_calls
            intent_source = "model"
            classifier_unusable = bool(preparsed_scene_intent.get("classifier_unusable"))
            selected_npc = game._validated_scene_npc_id(
                preparsed_scene_intent, player_input
            )
            if selected_npc is None and game._named_word_of(preparsed_scene_intent):
                game._session()._named_word = game._named_word_of(preparsed_scene_intent)
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
            if selected_npc is not None:
                talk_mode.open(world_state, selected_npc["id"], turn=flags.get("turn_index", 0))
        deferred_referent_id = (
            scene_plan.get("deferred_referent_id") if isinstance(scene_plan, dict) else None
        )
        if (
            deferred_referent_id
            and npc_resolution.get("status") == "none"
            and not world_subject_question
            and not game._validated_local_person_proposal(preparsed_scene_intent or {})
        ):
            # The planner matched the happening's person but left the pick to the
            # model; it named nobody here, so that person is the one greeted.
            current_location = world_state.get("location")
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
            promoted_npc = (
                game._promote_scene_referent(deferred_referent, current_location)
                if deferred_referent is not None else None
            )
            if promoted_npc:
                game._set_scene_active_npc(promoted_npc, flags.get("turn_index", 0))
                npc_resolution = {"status": "found", "npc": promoted_npc}
                # As when the planner promoted: a rejected proposal keeps this person's talk.
                active_conversation_before = talk_mode.snapshot(world_state)
        if (
            dialogue_fallback_deferred
            and npc_resolution.get("status") == "none"
            and interaction_mode != "ask_dm"
            and not game._is_negated_dialogue_action(player_input)
            and not game._validated_local_person_proposal(preparsed_scene_intent or {})
            and not local_dialogue.unresolved_named_address(
                player_input, game._conversation_npcs()
            )
        ):
            # Preserve the existing "say hello to the only visible person"
            # behavior when the model did not resolve an explicit description.
            npc_resolution = game.resolve_npc_reference(
                player_input, force_dialogue=True, allow_active_fallback=True
            )
        if npc_resolution.get("nobody_here"):
            game._nobody_here(npc_resolution["nobody_here"])
        if npc_resolution["status"] == "ambiguous" and not character_reply:
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
            npc_resolution = game._settle_address(npc_resolution, player_input)
        if npc_resolution.get("absent") and interaction_mode != "ask_dm" and not combat["active"]:
            return finish_turn(
                {"action": "dialogue", "status": "invalid_target", "success": False, "state_changes": []},
                game._absent_person_text(npc_resolution["absent"]),
                is_final=True,
            )
        npc_target = npc_resolution.get("npc") if npc_resolution["status"] == "found" else None

    if (
        target_id is None
        and (
            interaction_mode == "say"
            or (interaction_mode in {None, "do"} and game.should_generate_npcs(player_input))
        )
        and npc_target is not None
        and preparsed_scene_intent is None
        and not (
            focused_npc_before_targeting is not None
            and npc_target.get("id") == focused_npc_before_targeting.get("id")
            and not game.should_generate_npcs(player_input)
        )
        and game.is_npc_dialogue_input(player_input)
        and not local_dialogue.personal_question_kind(player_input)
        and not game.resolve_npc_reference(
            player_input, force_dialogue=False, allow_active_fallback=False
        ).get("npc")
    ):
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
        scene_preparse_model_calls = 1
        intent_model_calls = scene_preparse_model_calls
        intent_source = "model"
        classifier_unusable = bool(preparsed_scene_intent.get("classifier_unusable"))
        named_word = game._named_word_of(preparsed_scene_intent)
        if named_word and game._validated_scene_npc_id(preparsed_scene_intent, player_input) is None:
            # The reading names someone who is not here: the fallback's person does not answer for them
            game._session()._named_word = named_word
            game._nobody_here(named_word)
            npc_target = None

    if (
        target_id is None
        and (
            npc_target is None
            or game._validated_local_person_proposal(
                preparsed_scene_intent or {}
            )
        )
        and isinstance(locals().get("preparsed_scene_intent"), dict)
    ):
        local_proposal = game._validated_local_person_proposal(
            preparsed_scene_intent
        )
        if local_proposal and game.should_generate_npcs(player_input):
            npc_target = None
            request_key = game._local_person_request_key(player_input)
            existing_ids = {
                npc.get("id")
                for npc in world_state.get("npcs", [])
                if isinstance(npc, dict)
            }
            accepted_npc = None
            if not game.is_player_world_assertion(player_input):
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
            result = {
                "action": "dialogue",
                "status": "proposal_rejected",
                "success": False,
                "state_changes": [],
            }
            text = "Öyle birini göremiyorsun."
            return finish_turn(
                result, text, safety_handling="python_fallback", is_final=True
            )

    unresolved_address = local_dialogue.unresolved_named_address(player_input, game.active_npcs())
    front_talk = talk_front.current(game._session())
    named_reading = (talk_front.spoken_to(front_talk, game.active_npcs())
                     if unresolved_address and target_id is None and not combat["active"] else None)
    if named_reading is not None and not talk_front.old_owner_allowed(front_talk, "unknown_name"):
        npc_target = named_reading  # the reading names a listed person: the line is for them, speech answers
    elif unresolved_address and target_id is None and not combat["active"]:
        npc_target = None
        result = {"action": "dialogue", "status": "invalid_target", "success": False, "state_changes": []}
        return finish_turn(
            result,
            game._elsewhere_line(world_state, unresolved_address)
            or f"Burada {unresolved_address} adıyla tanıdığın biri görünmüyor.",
            is_final=True,
        )
    if npc_target is None and interaction_mode == "ask_dm" and not combat["active"]:
        # BM Task 3: asked of the DM, a plain-talk reading that names a listed person is the line for them
        npc_target = talk_front.spoken_to(front_talk, game.active_npcs())

    # "Özpil nerede?", or Konuş with no one to say it to: a person the town named is somewhere real.
    asks_for_someone = interaction_mode == "say" or re.search(r"\bner(?:e)?de\b", game._normalize_turkish_typos(player_input))
    elsewhere = (game._named_elsewhere_line(world_state, player_input)
                 if npc_target is None and asks_for_someone and not combat["active"] else None)
    if elsewhere:
        result = {"action": "dialogue", "status": "invalid_target", "success": False, "state_changes": []}
        return finish_turn(result, elsewhere, is_final=True)

    if interaction_mode == "say" and npc_target is None:
        result = {
            "action": "dialogue", "status": "clarification", "success": False,
            "state_changes": [],
        }
        nobody = "Burada konuşabileceğin kimse yok." if not game.active_npcs() else None
        return finish_turn(result, nobody or "Kiminle konuşmak istiyorsun?", is_final=True)

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

    topic_name = (
        game._topic_place_name(world_state)
        if (local_dialogue.asks_the_name_of_a_topic(player_input) and interaction_mode != "ask_dm"
            # BM Task 2: a plain-talk reading means the person answers by speech; the name line is the fallback
            and talk_front.old_owner_allowed(talk_front.current(game._session()), "place_name"))
        else None
    )
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

    thread_talk = game._job_talk_with(npc_target)
    interaction_hint = (
        None if interaction_mode == "ask_dm" or thread_talk
        or combat_lifecycle.quoted_report(game._session(), player_input)
        else interaction_adventure.hint(player_input, npc_target)
    )
    if interaction_hint == "plan" and (getattr(game._session(), "_front_read", None) or {}).get("kind") == "speak_to":
        interaction_hint = None  # two clauses said to a person are no plan to keep: they answer them
    if target_id is None and not combat["active"] and game._turns_to_someone_else(player_input):
        others = [npc for npc in game._conversation_npcs()
                  if not isinstance(npc_target, dict) or npc.get("id") != npc_target.get("id")]
        if others:
            npc_target = game.most_plausible_addressee(others, player_input)
            game._session()._set_scene_active_npc(npc_target, world_state.get("flags", {}).get("turn_index", 0))
    if (
        interaction_hint in {"information", "generate"} and target_id is None
        and (interaction_hint == "generate" or local_dialogue.personal_question_kind(player_input) == "local_work")
        and game._town_in_play(world_state)
    ):
        # Whoever is here answers from what they know; no proposal is needed to find a town's work.
        interaction_hint = None
        if npc_target is None:
            npc_target = game.most_plausible_addressee(game._conversation_npcs(), player_input)
    raw = None
    answer_in_person = False
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
    if held_plan is not None:
        hearer = game._said_to_someone_here(game._session(), raw)
        if hearer is None:
            # Not said to anyone here: the clauses are the player's own plan, recorded as before. A reading already
            # spent is this turn's one call, so the plan's own line is told without a narrator call.
            intent_source = "python_compound_plan"
            action_result = interaction_adventure.resolve(game._session(), player_input, held_plan)
            return finish_turn(action_result, action_result.pop("direct_response", ""),
                               is_final=intent_model_calls > 0)
        # Said to that person: they answer it, and the answer's `asks_for` is read as for any line said to them.
        npc_target, raw, interaction_hint, answer_in_person = hearer, None, None, True
    if raw is not None:
        conversation_resolution, conversation_rejected = (
            validate_interaction_conversation(
                raw,
                npc_target,
                required=(
                    interaction_hint == "information" and npc_target is not None
                ),
            )
        )
        # A reading the classifier got wrong is no reason for a person to stop being one: they answer the line.
        # A promise or a condition must never be recorded on a reading that failed; the turn's one reading was
        # not built for this proposal alone, so with it the person still answers and nothing is recorded.
        answer_in_person = (conversation_rejected and isinstance(npc_target, dict)
                            and (getattr(game._session(), "_front_reply", None) is not None
                                 or (interaction_hint in {"information", "generate"}
                                     and game._people_speak_for_themselves(world_state))))
        if conversation_rejected and not answer_in_person:
            return finish_conversation_rejection(npc_target)
        action_result = (
            {"status": "proposal_rejected"} if answer_in_person else interaction_adventure.resolve(
                game._session(), player_input, raw.get("interaction"), npc_target,
                fallback_operation=interaction_hint,
            )
        )
        if action_result.get("status") == "proposal_rejected" and game._has_spoken_to_player(npc_target):
            # Someone mid-conversation answers for themselves; a stock "I know nothing" disowns their own words.
            answer_in_person = True
        if action_result.get("status") == "unbacked" and isinstance(npc_target, dict):
            answer_in_person = True  # D-249 F2: nothing backs the answer, so it is theirs to give, not a stock line
        if (action_result.get("status") in {"proposal_rejected", "no_effect"} and isinstance(npc_target, dict)
                and (getattr(game._session(), "_front_read", None) or {}).get("kind") == "speak_to"):
            answer_in_person = True  # the reading said this is for that person: a proposal with nothing in it changes no ear
        narrated_without_model = (
            scene_preparse_model_calls > 0
            and interaction_hint in {"promise", "goal"}
            and action_result.get("status") == "recorded"
        )
        if not answer_in_person:
            return finish_turn(
                action_result, action_result["direct_response"],
                is_final=narrated_without_model or action_result["status"] in {
                    "proposal_rejected", "no_effect", "answered", "blocked",
                },
            )

    shop_request = (interaction_mode not in {"say", "ask_dm"}
                    and target_id is None and game._explicit_campaign_shop_request(player_input))
    shop_count_before = len(world_state.get("shops", []))
    current_shop_count = sum(
        1 for shop in world_state.get("shops", [])
        if isinstance(shop, dict) and shop.get("location") == world_state.get("location")
    )
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

    if shop_request:
        import shop_creation

        action_result = shop_creation.resolve_explicit_request(game._session())
        return finish_turn(
            action_result, action_result["direct_response"],
            is_final=not action_result["success"],
        )

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

    disclosed_name = game._explicit_player_name_disclosure(player_input)
    intro_fallback_name = None  # BM Task 3: the name the speech call voices; the intro line if it gives no usable line
    if (
        disclosed_name
        and isinstance(npc_target, dict)
        and isinstance(npc_target.get("id"), str)
        and not combat["active"]
    ):
        safe_name = re.sub(
            r"[^A-Za-zÇĞİÖŞÜçğıöşü'’-]", "", disclosed_name
        ).strip("'’-")
        if safe_name:
            # Hearing the same name again is no moment for the greeting a second time.
            compound_speech = not talk_front.old_owner_allowed(  # BM Task 2: the name is stored below, speech voices it
                talk_front.current(game._session()), "name_disclosure") or game._known_player_name(npc_target) == safe_name or (
                local_dialogue.has_multiple_dialogue_clauses(player_input, npc_target)
                # E9: a question Python cannot answer goes to speech; "who are you" Python answers itself.
                and (game._npc_speech_enabled() or (interaction_adventure._asks(player_input)
                                               and game._detect_query_type(player_input, npc_target) != "npc_identity"))
            )
            if compound_speech and game._known_player_name(npc_target) != safe_name and not talk_front.old_owner_allowed(
                    talk_front.current(game._session()), "name_disclosure"):
                intro_fallback_name = safe_name
            if compound_speech:
                local_dialogue.remember_explicit_player_name(npc_target, safe_name)
            if compound_speech and game._detect_query_type(player_input, npc_target) == "npc_identity":
                # The player requested this identity. Python decides disclosure;
                # the model receives the now-public name, not hidden identity.
                game._handle_query(player_input, "npc_identity", npc_target)
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

    # A requested shop with an 'işleten' shopkeeper is not a job inquiry.
    work_answer = (
        None
        if shop_request or interaction_mode == "say"
        else local_dialogue.unaddressed_work_answer(player_input)
    )
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

    experimental_unverified_claim = False
    told_support = []
    spoken_reference = False
    recognised = False  # a recognition question backed by their words alone: the reply may add no event
    if (
        interaction_mode != "ask_dm"
        and not thread_talk
        and game.is_npc_historical_claim(player_input)
        and not game._reported_npc_claim_followed_by_player_inspection(player_input)
        and not game._report_of_someone_else(player_input, npc_target)
    ):
        named_npc = game._resolve_campaign_npc_reference(player_input, world_state)
        claimed_npc = (named_npc if isinstance(named_npc, dict) and named_npc.get("location") != world_state.get("location")
                       else None) or npc_target or named_npc
        if npc_target is None and game._has_spoken_to_player(claimed_npc) and (
                claimed_npc.get("location") == world_state.get("location")):
            npc_target = claimed_npc  # the claim is about what this person said, and they are standing here
        supported_entry = (
            game.npc_memory_supporting_entry(claimed_npc, player_input)
            if claimed_npc else None
        )
        # LR00 fix: a claim about what this NPC said or promised is backed
        # only by the NPC's own recorded words (npc_statements). A greeting
        # that shares a word with the claim is not support.
        import npc_statements
        ledger = npc_statements.claim_support(world_state, claimed_npc, player_input) if claimed_npc else {"status": "absent"}
        if ledger["status"] == "supported":
            supported_entry = f"“{ledger['quote']}”"
        elif ledger["status"] == "unsupported" or (
            supported_entry and not npc_statements.legacy_entry_supports(supported_entry, player_input)
        ):
            supported_entry = None
        import npc_told
        about = npc_statements.claim_about(player_input)
        if about != "npc_words":
            supported_entry = None  # legacy conversation text is not selected personal memory
            if (isinstance(npc_target, dict) and claimed_npc is npc_target
                    and npc_target.get("location") == world_state.get("location")):
                told_support = npc_told.supports(world_state, npc_target["id"], player_input, about=about)
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
        recognised = spoken_reference and about == "memory"
        # Unattributed NPC knowledge cannot independently verify past dialogue.
        # Only the speaker-aware memory path may support this response.
        if told_support:
            experimental_unverified_claim = False
        elif spoken_reference:
            pass
        elif (
            not supported_entry
            and claimed_npc
            and interaction_mode != "ask_dm"
            and isinstance(npc_target, dict)
            and claimed_npc.get("id") == npc_target.get("id")
            and claimed_npc.get("location") == world_state.get("location")
        ):
            # A person answers in character, in their own words. The
            # claim still cannot become a promise, payment or memory: the speech
            # schema carries no operation and the reply is checked below.
            experimental_unverified_claim = True
        elif supported_entry and claimed_npc:
            quote = re.search(r'["\u201c](.*?)["\u201d]', str(supported_entry))
            if quote:
                response = f'{living_world.public_npc_name(claimed_npc)}, "Evet, bunu söylemiştim: {quote.group(1)}" diye yanıt verir.'
            else:
                response = f'{living_world.public_npc_name(claimed_npc)}, "Evet, bunu daha önce konuştuğumuzu hatırlıyorum," diye yanıt verir.'
            action_result = {
                "action": "dialogue",
                "status": "answered_from_npc_memory",
                "success": True,
                "npc_id": claimed_npc["id"],
                "state_changes": [],
                "direct_response": response,
            }
            game.record_npc_interaction(claimed_npc, response, player_input, claimed_npc)
            return finish_turn(
                action_result,
                response,
                safety_reason_code="NPC_MEMORY_SUPPORTED_CLAIM",
                safety_handling="python_memory_response",
            )
        else:
            if claimed_npc and claimed_npc.get("location") == world_state.get("location"):
                response = game.historical_claim_denial(claimed_npc, player_input)
            elif claimed_npc:
                response = f"{living_world.public_npc_name(claimed_npc)} şu anda burada değil; ne dediğini ona sormadan öğrenemezsin."
            else:
                response = "Böyle bir konuşmayı kimin yaptığını kestiremiyorsun; yanındakilerden hiçbiri bunu üstlenmiyor."
            action_result = {
                "action": "dialogue",
                "status": "unverified",
                "success": False,
                "npc_id": claimed_npc.get("id") if claimed_npc else None,
                "state_changes": [],
                "direct_response": response,
            }
            if claimed_npc and claimed_npc.get("location") == world_state.get("location"):
                game.record_npc_interaction(claimed_npc, response, player_input, claimed_npc)
            return finish_turn(
                action_result,
                response,
                safety_reason_code="NPC_MEMORY_UNSUPPORTED_CLAIM",
                safety_handling="python_memory_response",
            )

    supported_lore_response = game._supported_lore_question_response(
        player_input,
        lore_context,
        world_state,
    )
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

    npc_place_recommendation = (
        isinstance(npc_target, dict)
        and interaction_mode != "ask_dm"
        and local_dialogue.is_local_place_recommendation_request(player_input)
    )
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
    profile_focus = interaction_adventure.current_conversation_focus(world_state, npc_target)
    canonical_profile_question = (
        local_dialogue.personal_question_kind(player_input)
        in interaction_adventure.PROFILE_FIELD_BY_MEANING.values()
        or (game._is_short_followup(player_input) and profile_focus
            and profile_focus.get("predicate") in interaction_adventure.PROFILE_FIELD_BY_MEANING.values())
    ) and not local_dialogue.has_multiple_dialogue_clauses(player_input, npc_target)
    experimental_dialogue_session = npc_dialogue_route and (
        # BM Task 3: the model read a plain talk line to this person: they answer by speech, even asked of the DM
        (isinstance(npc_target, dict) and not talk_front.old_owner_allowed(front_talk, "personal"))
        or (interaction_mode != "ask_dm"
            and (game._npc_speech_enabled() or experimental_unverified_claim or not canonical_profile_question))
    )
    lore_safety_input = player_input
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
    # A multi-part message may carry one plainly answerable personal question
    # ("Adın nedir? Bir de kralın planını söyler misin?"). Dropping the whole
    # turn at this gate loses that part; the personal/smalltalk and model
    # paths below still run with every narration safety check behind them.
    # This admission gate governs authoritative answers, not an already
    # resolved NPC's attributed speech. A topic word or an unknown name in a
    # question is not itself a world mutation. The speech path below accepts
    # no model operation/world updates and still validates identity, history,
    # transfers, player agency and the resulting narration before display.
    # Narrator and legacy authoritative paths retain the lore gate.
    answerable_personal_kind = (
        local_dialogue.personal_question_kind(player_input)
        if isinstance(npc_target, dict) else None
    )
    lore_gate = answerable_personal_kind is None and not experimental_dialogue_session and (
        (
            not npc_place_recommendation
            and (world_subject_question or local_dialogue.is_world_subject_question(player_input))
        )
        or game._player_question_has_unverified_lore_claim(
            lore_safety_input, lore_context, world_state
        )
    )
    if (lore_gate and interaction_mode != "ask_dm" and not combat["active"]
            and game._people_speak_for_themselves(world_state)
            and not game._ASKS_DISTANCE.search(local_dialogue.normalize_text(player_input))):
        # Asked aloud with someone standing there, the town's talk is theirs to answer, not the street's.
        here = game._conversation_npcs()
        npc_target = game._explicit_addressee(player_input, here) or npc_target or game.most_plausible_addressee(here, player_input)
        if isinstance(npc_target, dict):
            lore_gate = False
            npc_dialogue_route = experimental_dialogue_session = True
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

    smalltalk_response = game._direct_npc_smalltalk_response(player_input, npc_target)
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

    if shop_request:
        validated_intent = {"intent_type": "narrative"}
    elif npc_dialogue_route:
        # The UI's default mode is "do"; a named or followed-up NPC in that
        # mode must reach the same first-person speech path as "say".
        experimental_npc_dialogue = experimental_dialogue_session
        intent_model_calls = scene_preparse_model_calls + 1
        speech_intent_calls = 1  # G10: a dialogue reply is always asked, held reading or not
        intent_source = "interaction_proposal"
        # Python settles the name first, so the prompt and the label agree.
        name_stance = (
            game._npc_name_stance(world_state, npc_target, player_input)
            if experimental_npc_dialogue else None
        )
        if name_stance == "reveal":
            npc_target["name_known_to_player"] = True
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
        conversation_resolution, conversation_rejected = (
            validate_interaction_conversation(
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
        # A live source ID alone does not bind that event to this question.
        # Supported personal memory and validated profile answers keep their owner.
        import witness_recall
        import npc_statements
        witness_requested = (isinstance(raw_intent, dict) and "witness_recall" in raw_intent
            and game.is_npc_historical_claim(player_input)
            and npc_statements.claim_about(player_input) == "memory")
        # A profile/personal answer may take precedence, but cannot drop this veto.
        # Positive money answers gain no authority from a witness proposal.
        if witness_requested and raw_intent.get("coin_answer") == "declines":
            money_owner.read_answer(game._session(), raw_intent, npc_target["id"],
                money_owner.parts_for(world_state, game._session(), npc_target["id"]))
        witness_attempt = (witness_requested and not told_support
            and not (conversation_resolution and conversation_resolution.get("answer_field")))
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
        # An optional classifier can supply a validated canonical answer, but
        # cannot veto experimental speech. Its rejected data grants no authority.
        if (
            conversation_rejected
            and not experimental_npc_dialogue
            and not npc_place_recommendation
        ):
            if game._salvage_plain_speech(raw_intent):
                conversation_rejected = False
                conversation_resolution = None
            else:
                return finish_conversation_rejection(npc_target)
        if game._interaction_proposal_applies(raw_intent, npc_target, player_input):
            if experimental_npc_dialogue:
                # The packet's speech stands; a proposal in it simply grants nothing.
                raw_intent = {**raw_intent, "interaction": None}
            else:
                action_result = interaction_adventure.resolve(
                    game._session(), player_input, raw_intent["interaction"], npc_target,
                )
                if action_result["status"] != "proposal_rejected":
                    return finish_turn(
                        action_result, action_result["direct_response"],
                        is_final=action_result["status"] in {"no_effect", "answered", "blocked"},
                    )
                # A proposal Python cannot use is dropped; the line itself still gets a person's answer.
                raw_intent = {**raw_intent, "interaction": None}
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
        # A conversation-only response already used the single allowed narrator
        # call. Validate it as dialogue, without a retry or accepting its updates.
        if experimental_npc_dialogue or isinstance(raw_intent.get("narration"), str):
            # When a scene pre-parse selected the addressee, its provider call
            # remains an intent call; this response is an additional narration
            # call, not a replacement for the first one.
            intent_model_calls = scene_preparse_model_calls
            speech_intent_calls = 0
            intent_source = (
                "model" if scene_preparse_model_calls else "deterministic_dialogue"
            )
            narration_model_calls = 1
            narration_source = "qwen"
            action_result = resolve_intent(
                {"intent": "dialogue"}, player_input, npc_target=npc_target,
                target_id=target_id,
            )
            if experimental_npc_dialogue:
                action_result["npc_id"] = npc_target["id"]
                action_result["status"] = "experimental_attributed_speech"
                if told_support or spoken_reference or thread_talk or game._report_of_someone_else(player_input, npc_target):
                    action_result["own_words"] = True

            raw_narration = raw_intent.get("narration") if isinstance(raw_intent, dict) else None
            model_raw_narration = raw_narration
            attributed_speech = None
            invalid_spoken_stage_direction = False
            settled_money = {}
            if experimental_npc_dialogue:
                raw_spoken = raw_intent.get("spoken_text") if isinstance(raw_intent, dict) else None
                raw_stage = raw_intent.get("stage_direction") if isinstance(raw_intent, dict) else None
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
            invalid_or_empty = not isinstance(raw_narration, str) or not raw_narration.strip()
            if experimental_npc_dialogue and (
                attributed_speech is None
                or not attributed_speech["spoken_text"].strip()
            ):
                invalid_or_empty = True
            empty_model_narration = isinstance(raw_narration, str) and not raw_narration.strip()

            python_town_response = None
            if invalid_or_empty:
                if name_stance == "reveal":
                    text = game._spoken_name_answer("", npc_target)
                elif intro_fallback_name:
                    text = local_dialogue.introduction_reply(world_state, npc_target, intro_fallback_name)
                else:
                    # D-325: what this person herself said is hers to repeat before any denial of the claim
                    import heard_rumours
                    own_rumour = heard_rumours.own_line(world_state, npc_target, player_input)
                    text = (game._job_fallback(world_state) or own_rumour
                            or (experimental_unverified_claim and game.historical_claim_denial(npc_target, player_input)))
                    if own_rumour and text == own_rumour:
                        python_town_response = own_rumour
                        action_result["own_words"] = True  # what she told is hers: not an unrecorded claim, nothing granted
                    if not text:
                        town_reply = game._town_fallback(world_state, npc_target, player_input)
                        if isinstance(town_reply, str) and town_reply.strip():
                            text = python_town_response = town_reply
                        else:
                            text = interaction_adventure.immersive_unknown(npc_target, player_input)
            else:
                text = raw_narration

            if experimental_unverified_claim:
                # A reply may refuse the unrecorded claim or ask back in its own
                # words; only one that goes along with it is replaced.
                unverified_history_echo = (
                    not invalid_or_empty and (
                        not game._npc_speech_is_claim_refusal(text)
                        # With no selected personal memory, an unrecognised factual
                        # answer is not evidence of refusal. Reuse the existing
                        # explicit refusal check; leave NPC-word ask-backs alone.
                        or (about != "npc_words" and not game._npc_speech_rejects_claim(text))
                    )
                )
                if not invalid_or_empty and not unverified_history_echo:
                    action_result["own_words"] = True  # their own answer stands; nothing was granted
            else:
                unverified_history_echo = (
                    not invalid_or_empty
                    and not told_support
                    and game._unverified_past_event_assertion(player_input)
                    and bool(game._claim_keywords(text) & game._claim_keywords(player_input))
                )
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

            text_before_finalize = text
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
            narration_safety = getattr(game._session(), "last_narration_safety", None)
            narration_safety = (
                narration_safety if isinstance(narration_safety, dict) else {}
            )
            final_safety_reason_code = narration_safety.get("reason_code")
            final_safety_handling = narration_safety.get("handling", "accepted")
            if (
                final_safety_reason_code
                and final_safety_handling == "python_fallback"
            ):
                narration_source = "deterministic_fallback"
            stock_swapped = experimental_npc_dialogue and game._is_stock(text)
            if stock_swapped:
                # A clear line never earns "say it again": the person answers from what Python has for them.
                text = game._person_fallback(world_state, npc_target, player_input)
            elif (experimental_npc_dialogue and final_safety_handling == "python_fallback"
                    and not experimental_unverified_claim and action_result.get("action") != "skill_check"
                    and interaction_adventure._asks(player_input)):  # a greeting keeps the fallback's own answer
                # D-249 F1: a speech the safety check rejected is replaced by what the person has to say from Python
                # (job, town lead, place to ask), never by the stock "I don't know" the fallback wrote.
                text = game._person_fallback(world_state, npc_target, player_input)
                if text != interaction_adventure.immersive_unknown(npc_target, player_input):
                    python_town_response = text
            speech_checks = None
            if experimental_npc_dialogue:
                # D-252: the names of the checks that changed or replaced this reply, for the route log. Never words.
                kept = attributed_speech["spoken_text"].strip() if attributed_speech else ""
                said = raw_spoken.strip() if isinstance(raw_spoken, str) else ""
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
                if final_safety_reason_code:
                    speech_checks.append(f"safety:{str(final_safety_reason_code)[:40]}")
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
            accepted_model_speech = (
                experimental_npc_dialogue
                and not invalid_or_empty
                and not unverified_history_echo
                and attributed_speech is not None
                and text == game._compose_experimental_npc_speech(attributed_speech)
            )
            turned_down_what_was_paid = (
                accepted_model_speech and settled_money.get("moved")
                and game._npc_speech_rejects_claim(attributed_speech["spoken_text"])
            )
            if turned_down_what_was_paid or (
                accepted_model_speech and not game._with_only_backed_money(attributed_speech, settled_money)
            ):
                accepted_model_speech = False
                text = (game._job_fallback(world_state) or game._town_fallback(world_state, npc_target, player_input)
                        or interaction_adventure.immersive_unknown(npc_target, player_input))
                speech_checks.append("unbacked_money")
            if speech_checks is not None:
                game._session()._speech_checks = speech_checks
            if experimental_unverified_claim:
                action_result.update(status="unverified", success=False)
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

            if experimental_npc_dialogue:
                # The person's own spoken answer about the coin (`coin_answer`, read for every accepted speech) is also
                # the semantic reply to a validated gift or tip put to them: takes accepts it, declines refuses it,
                # and anything else leaves the card without their consent (the line refused, nothing charged).
                coin_reply = ({"takes": "accept", "declines": "refuse"}.get(getattr(game._session(), "_coin_answer", None))
                              if accepted_model_speech else None)
                game._record_spoken_coin_response(npc_target, coin_reply)
                if accepted_model_speech and valid_speech_packet and game._rumour_lane_on():
                    import heard_rumours
                    named = raw_intent.get("mentions")
                    named = named.get("name") if isinstance(named, dict) else None
                    # D-249: what the person named is stored by Python only, and only a name they said aloud;
                    # a bad mention is dropped without a trace.
                    if heard_rumours.said_in(attributed_speech["spoken_text"], named):
                        heard_rumours.record_mention(
                            sys.modules["game"], game._session().world_state, npc_target, raw_intent.get("mentions"),
                            game._session().world_state.get("flags", {}).get("turn_index", 0))
            if (
                empty_model_narration
                or unverified_history_echo
                or (
                    experimental_npc_dialogue
                    and invalid_or_empty
                )
            ):
                narration_source = "deterministic_fallback"
                if experimental_npc_dialogue:
                    terms = game._offer_terms_shown(world_state, npc_target, player_input, text)
                    if terms:
                        # D-247: a stock "I don't know" never sits beside the job's own terms; the terms are the answer.
                        bare = text == interaction_adventure.immersive_unknown(npc_target, player_input)
                        text = f"{living_world.public_npc_name(npc_target)}, “{terms}”" if bare else f"{text} “{terms}”"
                    game._remember_experimental_npc_speech(
                        npc_target["id"], player_input, text, remember=valid_speech_packet and raw_intent.get("remember_player_line") is True
                    )
                    if settled_money.get("note"):
                        text = f"{text} {settled_money['note']}"
                game._show_coin_roll(action_result, settled_money.get("check"))  # D-166: the roll shows, reply used or not
                return finish_turn(
                    action_result, text, is_final=True,
                    safety_reason_code=(
                        "INVALID_NARRATION" if invalid_spoken_stage_direction
                        else "EMPTY_NARRATION" if empty_model_narration
                        else "UNVERIFIED_PLAYER_CLAIM_ECHO" if unverified_history_echo
                        else "INVALID_NARRATION"
                    ),
                    safety_handling="python_fallback",
                )
            # Interpret the proposal carried by this same speech response; never make another model call.
            # Only an accepted reply can request a mechanic. The price owner still rechecks the live offer.
            negotiation = money_owner.price_negotiation(world_state, raw_intent.get("price_negotiation"), player_input)
            price_reply_accepted = (accepted_model_speech if experimental_npc_dialogue else
                                    not invalid_or_empty and not unverified_history_echo and text == raw_narration)
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
            game._show_coin_roll(action_result, settled_money.get("check"))  # D-166: the coin ask's own roll shows
            if experimental_npc_dialogue:
                spoken = attributed_speech["spoken_text"] if accepted_model_speech else text
                terms = game._offer_terms_shown(world_state, npc_target, player_input, spoken)
                if terms:
                    text, spoken = f"{text} “{terms}”", f"{spoken} {terms}"
                game._remember_experimental_npc_speech(npc_target["id"], player_input, spoken,
                                                  remember=valid_speech_packet and raw_intent.get("remember_player_line") is True,
                                                  voiced=game._voiced_keys(raw_intent) if accepted_model_speech and valid_speech_packet else None)
                if settled_money.get("note"):
                    text = f"{text} {settled_money['note']}"
            return finish_turn(
                action_result,
                text,
                is_final=True,
                safety_reason_code=final_safety_reason_code,
                safety_handling=final_safety_handling,
                record_safety=False,  # finalize_narration already recorded this verdict.
            )
        validated_intent = {"intent": "dialogue"}
    else:
        import bold_acts
        if npc_target is not None and (game._is_object_inspection(player_input)
                                       or (target_id is None and bold_acts.is_act_not_talk(game._session(), player_input))):
            # "Merak etme Sera, sadece kilide bakacağım": the act is looking at
            # the lock; a name in passing must not demand a conversation.
            # D-098, D-099: "muhafızı korkutmaya çalışıyorum", "muhafızın üstünü inceliyorum" are acts on them, not
            # words to them; the dice or the narrator answer, never a stock "I heard you".
            npc_target = None
        intent_source = "model"
        if classifier_unusable:
            raw_intent = {"intent": "unknown"}
        elif npc_target is None and isinstance(preparsed_scene_intent, dict):
            # The scene pre-parse already asked this exact question (no
            # addressee, same context and proposal permissions); asking again
            # would exceed the two-call turn budget without new information.
            raw_intent = preparsed_scene_intent
            intent_model_calls = scene_preparse_model_calls
        else:
            intent_model_calls = scene_preparse_model_calls + 1
            raw_intent = game.parse_player_intent(
                player_input,
                interaction_context=interaction_adventure.context(
                    world_state, npc_target, player_input
                ),
                # This generic intent path may resolve a bounded mechanics
                # request; conversation is validated after classification.
                require_conversation=False,
                allow_scene_detail_proposals=game._scene_detail_proposals_allowed(
                    player_input, world_state, interaction_mode
                ),
                strict=check_feature is not None,
            )
            classifier_unusable = bool(raw_intent.get("classifier_unusable"))
        if classifier_unusable:
            # This turn's reading is lost and nobody is being spoken to: the
            # narrator answers it as a free attempt, with no authority of its own.
            npc_target = None
            raw_intent = {
                "intent": "narrative", "action": "narrative",
                "target": {"type": "none", "reference": ""},
                "completion": "unclear", "confidence": 0.0,
            }
        conversation_resolution, conversation_rejected = (
            validate_interaction_conversation(
                raw_intent,
                npc_target,
                required=(
                    npc_target is not None
                    and not game._grounded_item_request_proposal(
                        raw_intent, npc_target, player_input
                    )
                    # in a fight, a walk toward someone is combat movement, not words to them
                    and not (combat["active"] and isinstance(raw_intent, dict) and raw_intent.get("intent") == "travel")
                ),
            )
        )
        if conversation_rejected:
            if game._salvage_plain_speech(raw_intent):
                conversation_rejected = False
                conversation_resolution = None
            else:
                return finish_conversation_rejection(npc_target)
        if game._interaction_proposal_applies(raw_intent, npc_target, player_input):
            action_result = interaction_adventure.resolve(
                game._session(), player_input, raw_intent["interaction"], npc_target,
            )
            if action_result["status"] != "proposal_rejected" and not (
                    action_result["status"] == "unbacked" and isinstance(npc_target, dict)):
                return finish_turn(
                    action_result, action_result["direct_response"],
                    is_final=action_result["status"] in {"no_effect", "answered", "blocked"},
                )
            # A proposal Python cannot use is dropped; the line itself still gets a person's answer.
            raw_intent = {**raw_intent, "interaction": None}
        if npc_target is not None:
            conversation_outcome = finish_conversation_resolution(
                conversation_resolution, npc_target
            )
            if conversation_outcome is not None:
                return conversation_outcome
        normalized_intent = game.normalize_intent(raw_intent, player_input)
        validated_intent = game.validate_intent(normalized_intent, player_input)
    walk = getattr(game._session(), "_walk_off", None)
    if walk is not None and not (validated_intent.get("intent") == "travel"
                                 and (validated_intent.get("target") or {}).get("type") == "npc"):
        raise walk  # the line walks off and the reading names nobody in the fight: refused before anything is told
    if DEBUG_MODE:
        print("[INTENT]")
        print(json.dumps(validated_intent, ensure_ascii=False, indent=2))

    previous_location = world_state.get("location")
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
    if DEBUG_MODE:
        print("[RULE ENGINE]")
        print(json.dumps({key: value for key, value in action_result.items() if key != "direct_response"}, ensure_ascii=False, indent=2))

    if action_result.get("status") == "unresolved":
        return finish_turn(
            action_result,
            action_result.get("direct_response") or game._natural_unresolved_action_response(player_input, action_result),
            is_final=True,
            safety_handling="python_scene_response",
        )

    if action_result.get("action") == "combat_move":
        return finish_turn(action_result, action_result["direct_response"], is_final=True)  # the engine tells it

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

    findings = action_result.get("inspection")
    if (isinstance(findings, dict) and findings.get("target_id") is None
            and isinstance(raw_intent, dict)
            and isinstance(raw_intent.get("scene_detail_proposals"), list)
            and raw_intent["scene_detail_proposals"]):
        # An unmatched named search is a miss only if the model proposed no
        # valid detail; an accepted proposal continues to the creation path.
        # The submitted/verified record is kept either way, as on that path.
        early_parent = game._scene_detail_parent(world_state.get("location"), player_input)
        early_parent_id = early_parent.get("id") if isinstance(early_parent, dict) else None
        early_bound = [proposal for proposal in raw_intent["scene_detail_proposals"][:1]
                       if isinstance(proposal, dict)
                       and proposal.get("parent_id") == early_parent_id]
        early_entry = action_result.get("action") == "travel" and action_result.get("completion") == "completed"
        early_changed = early_entry or world_state.get("location") != previous_location
        action_result["scene_detail_proposal_submitted"] = True
        action_result["verified_world_updates"] = game.validate_world_updates(
            {"create_features": early_bound},
            allow_new_features=(not shop_request
                                and game.should_generate_features(player_input, early_changed)
                                and not game.is_player_world_assertion(player_input)),
            allowed_feature_kinds=game.SCENE_DETAIL_KIND_ALLOWLIST,
        )
        if action_result["verified_world_updates"].get("create_features"):
            findings = None
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

    proposed_entry = action_result.get("action") == "travel" and action_result.get("completion") == "completed"
    allow_new_locations = bool(action_result.get("proposal_required"))
    expected_location_change = proposed_entry or world_state.get("location") != previous_location
    allow_new_npcs = (
        not shop_request
        and game.should_generate_npcs(player_input, expected_location_change)
        and not game.is_player_world_assertion(player_input)
    )
    allow_new_features = (
        not shop_request
        and game.should_generate_features(player_input, expected_location_change)
        and not game.is_player_world_assertion(player_input)
    )
    scene_parent = game._scene_detail_parent(
        world_state.get("location"), player_input
    )
    if (
        scene_parent is None
        and living_world.is_anchored_structure_inquiry(player_input)
    ):
        action_result["direct_response"] = (
            "Yakında inceleyebileceğin belirgin bir bina görünmüyor."
        )
    if isinstance(raw_intent, dict):
        scene_detail_proposals = raw_intent.get("scene_detail_proposals")
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
    allow_new_shops = bool(shop_request)

    quest_transitions = game._session().evaluate_quest_events(
        quest_world_before, action_result
    )
    if quest_transitions:
        action_result["quest_outcomes"] = quest_transitions
    narration = action_result.get("direct_response") or game._fallback_for_action_result(
        player_input, action_result
    )
    # An inventory transaction has already been resolved by Python. Do not
    # let a separate narrator reverse its direction or invent another transfer.
    return finish_turn(
        action_result, narration, quest_transitions,
        is_final=action_result.get("action") == "inventory",
    )
