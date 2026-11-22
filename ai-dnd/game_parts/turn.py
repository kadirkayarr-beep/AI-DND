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
