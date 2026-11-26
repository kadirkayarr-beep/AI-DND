import game
import action_economy
from core_resolution import (
    resolution_action_scope,
)
import combat_lifecycle
import contextlib
import copy
from dataclasses import dataclass
import interaction_adventure
import living_world
import local_dialogue
import money_owner
import re
import timed_gameplay
from typing import Optional, List, Dict, Any
import held_weapon
import monster_sense
import json
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
    _exit = game._dpt_fallen_turn(action_id=action_id, messages=messages, player_input=player_input, session_id=session_id, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
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
    _exit = game._dpt_owner_reply(owner_reply=owner_reply)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    interaction_mode, target_id = game._td_combat_mode(combat_action=combat_action, interaction_mode=interaction_mode, player_input=player_input, target_id=target_id)
    _exit = game._td_end_conversation(combat_action=combat_action, interaction_mode=interaction_mode, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    read = getattr(game._session(), "_front_read", None) if getattr(game._session(), "_front_ahead", False) else None
    import front_proposal
    read = game._dpt_front_step_read(check_feature=check_feature, combat_action=combat_action, front_proposal=front_proposal, interaction_mode=interaction_mode, player_input=player_input, read=read, target_id=target_id)
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
    _exit = game._dpt_narrative_spell(action_id=action_id, check_evidence=check_evidence, check_feature=check_feature, combat_action=combat_action, interaction_mode=interaction_mode, messages=messages, player_input=player_input, scene_plan=scene_plan, session_id=session_id, spell_effects=spell_effects, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    _exit = game._td_fallen_address(combat_action=combat_action, player_input=player_input, read=read)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
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
    _exit = game._td_strike_fallen(combat_action=combat_action, interaction_mode=interaction_mode, player_input=player_input, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    _exit = game._dpt_bag_read(player_input=player_input, read=read)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    _exit = game._td_parcel_board(combat_action=combat_action, interaction_mode=interaction_mode, player_input=player_input, read=read)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
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
    interaction_mode, target_id = game._dpt_ends_in_speech(combat_action=combat_action, front=front, interaction_mode=interaction_mode, player_input=player_input, target_id=target_id)
    gate = None
    if (combat_action is None and not getattr(game._session(), "_thread_gate_done", False)
            and not getattr(game._session(), "_front_strike", None)):  # a blow stood behind is no answer to an offer
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            gate = game._dpt_front_gate(front=front, interaction_mode=interaction_mode, player_input=player_input, target_id=target_id)
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
    _exit = game._dpt_free_dialogue(action_id=action_id, combat_action=combat_action, interaction_mode=interaction_mode, player_input=player_input, session_id=session_id, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    if combat_action is None and interaction_mode in {"say", "ask_dm"}:
        _exit = game._dpt_natural_inventory_query(interaction_mode=interaction_mode, player_input=player_input)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
        _exit = game._dpt_run_without_action_id(action_id=action_id, check_evidence=check_evidence, check_feature=check_feature, interaction_mode=interaction_mode, messages=messages, player_input=player_input, scene_plan=scene_plan, target_id=target_id)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
        _exit = game._dpt_run_in_action_scope(action_id=action_id, check_evidence=check_evidence, check_feature=check_feature, interaction_mode=interaction_mode, messages=messages, player_input=player_input, scene_plan=scene_plan, session_id=session_id, target_id=target_id)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit

    _exit = game._dpt_out_of_combat_commands(action_id=action_id, combat_action=combat_action, front=front, interaction_mode=interaction_mode, messages=messages, player_input=player_input, session_id=session_id, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    import exploration
    _exit = game._dpt_native_exploration_command(action_id=action_id, combat_action=combat_action, exploration=exploration, player_input=player_input, session_id=session_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    import authored_dungeon
    if combat_action is None:
        dungeon_result = authored_dungeon.resolve_command(game._session(), player_input)
        if dungeon_result is not None:
            return dungeon_result
    planning = (combat_action is None
                and not game._session().world_state.get("combat", {}).get("active")
                and not getattr(game._session(), "_front_strike", None)
                and interaction_adventure.compound_plan(player_input) is not None)
    _exit = game._dpt_equipment_economy(combat_action=combat_action, planning=planning, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    import spell_scope
    spell_command = (spell_scope.natural_command(player_input, target_id)
                     if combat_action is None and not planning else None)
    _exit = game._dpt_surrendered_spell_question(action_id=action_id, player_input=player_input, session_id=session_id, spell_command=spell_command, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    import bounded_encounter
    if not planning:
        bounded_encounter.refresh(game._session())
    native = (bounded_encounter.resolve_command(game._session(), player_input)
              if combat_action is None and not planning else None)
    if native is not None:
        return native
    import monster_combat
    _exit = game._dpt_active_combat_response(combat_action=combat_action, monster_combat=monster_combat, player_input=player_input, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    _exit = game._dpt_stand_down(action_id=action_id, combat_action=combat_action, player_input=player_input, session_id=session_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    _exit = game._dpt_flight(action_id=action_id, combat_action=combat_action, player_input=player_input, session_id=session_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    command = combat_action or (None if planning else
                               action_economy.natural_command(game._session(), player_input, target_id))
    surrender_question = combat_lifecycle.surrendered_strike_question(game._session(), player_input, target_id, command)
    if surrender_question is not None:
        return surrender_question
    if command:
        return action_economy.execute(game._session(), command, action_id, session_id)
    if action_economy.pending_reaction(game._session()):
        raise combat_lifecycle.CombatRequestError("reaction_pending", "Resolve or decline the reaction opportunity.", 400)
    _exit = game._td_scene_plan_direct(action_id=action_id, combat_action=combat_action, front=front, interaction_mode=interaction_mode, messages=messages, player_input=player_input, scene_plan=scene_plan, session_id=session_id, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
    game._session()._walk_off = None
    game._dpt_validate_combat_request(player_input=player_input, target_id=target_id)
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
    game._rpt_character_current_hp(entry_combat=entry_combat, world_state=world_state)
    local_npc_place_request = game._rpt_local_npc_place(interaction_mode=interaction_mode, player_input=player_input, target_id=target_id, world_state=world_state)
    world_subject_question = game._rpt_world_subject_question(interaction_mode=interaction_mode, local_npc_place_request=local_npc_place_request, player_input=player_input)
    scene_exploration_question = living_world.is_exploratory_structure_question(
        player_input, interaction_mode
    )
    if messages is None:
        messages = game._session().messages
    scene_plan = game._rpt_scene_plan_scene(interaction_mode=interaction_mode, player_input=player_input, scene_plan=scene_plan, target_id=target_id)
    planned_direct = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
    scene_plan = game._rpt_planned_direct_planned(interaction_mode=interaction_mode, planned_direct=planned_direct, player_input=player_input, scene_plan=scene_plan, world_state=world_state)
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
        return game._procedural_entity_ids(world_state)

    procedural_ids_before = game._tx_procedural_ids_before(procedural_entity_ids=procedural_entity_ids, scene_plan=scene_plan)

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
        return game._finish_turn(
            action_result=action_result,
            narration=narration,
            quest_outcomes=quest_outcomes,
            safety_reason_code=safety_reason_code,
            safety_handling=safety_handling,
            record_safety=record_safety,
            is_final=is_final,
            active_conversation_before=active_conversation_before,
            allow_new_features=allow_new_features,
            allow_new_locations=allow_new_locations,
            allow_new_npcs=allow_new_npcs,
            allow_new_shops=allow_new_shops,
            conversation_resolution=conversation_resolution,
            conversation_state_before=conversation_state_before,
            entry_actor=entry_actor,
            entry_identity=entry_identity,
            expected_location_change=expected_location_change,
            intent_source=intent_source,
            lore_context=lore_context,
            messages=messages,
            narration_model_calls=narration_model_calls,
            narration_source=narration_source,
            npc_target=npc_target,
            player_input=player_input,
            procedural_entity_ids=procedural_entity_ids,
            procedural_ids_before=procedural_ids_before,
            quest_world_before=quest_world_before,
            scene_plan=scene_plan,
            target_id=target_id,
            told_intent_calls=told_intent_calls,
            turn_index=turn_index,
            world_state=world_state,
        )

    import spell_effects
    spell_reading = (spell_effects.named(player_input)
                     if interaction_mode not in {"say", "ask_dm"} and isinstance(player_input, str)
                     and game._session().character.get("current_hp", 0) > 0 else None)  # a body on the ground saves
    _exit = game._rpt_spell_reading_engine(finish_turn=finish_turn, spell_effects=spell_effects, spell_reading=spell_reading)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    def finish_conversation_rejection(target):
        return game._finish_conversation_rejection(
            finish_turn=finish_turn, player_input=player_input, target=target,
        )

    def finish_conversation_resolution(resolution, target):
        return game._finish_conversation_resolution(
            action_id=action_id, finish_turn=finish_turn, player_input=player_input,
            resolution=resolution, target=target,
        )

    walked_up = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
    said_after = game._said_after_approach(player_input)
    _exit = game._rpt_walked_up_walked(action_id=action_id, interaction_mode=interaction_mode, messages=messages, said_after=said_after, walked_up=walked_up)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit
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
        _exit = game._rpt_person_living_world(action_id=action_id, messages=messages, person=person, request=request, world_state=world_state)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
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
    scene_plan = game._tg_scene_plan(held_plan=held_plan, interaction_mode=interaction_mode, player_input=player_input, scene_plan=scene_plan, target_id=target_id)
    _exit = game._tx_timed_sequence(finish_turn=finish_turn, interaction_mode=interaction_mode, player_input=player_input, scene_plan=scene_plan, sleeping=sleeping, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    combat = game.ensure_combat_state()
    _exit = game._tx_player_down(combat=combat, finish_turn=finish_turn)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tx_enemy_turns(combat=combat, finish_turn=finish_turn, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    planned_direct = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
    _exit = game._tx_planned_direct(finish_turn=finish_turn, planned_direct=planned_direct, player_input=player_input, quest_world_before=quest_world_before, scene_plan=scene_plan, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    character_reply = game._rpt_character_reply_known(combat=combat, interaction_mode=interaction_mode, player_input=player_input)
    focused_npc_before_targeting = game._active_interlocutor()
    if target_id is not None:
        _exit = game._tx_attack_target_missing(finish_turn=finish_turn, target_id=target_id)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
        npc_target = None
        selected_npc_target = next(
            (npc for npc in (game._conversation_npcs() if interaction_mode == "say" else game.active_npcs())
             if isinstance(npc, dict) and npc.get("id") == target_id), None,
        ) if not combat["active"] else None
        npc_target = game._tx_attack_hint_no_target(combat=combat, flags=flags, interaction_mode=interaction_mode, npc_target=npc_target, player_input=player_input, selected_npc_target=selected_npc_target, world_state=world_state, world_subject_question=world_subject_question)
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
            preparsed_scene_intent = game._rpt_preparsed_scene_intent_2(check_feature=check_feature, interaction_mode=interaction_mode, player_input=player_input, world_state=world_state)
            scene_preparse_model_calls = 1
            intent_model_calls = scene_preparse_model_calls
            intent_source = "model"
            classifier_unusable = bool(preparsed_scene_intent.get("classifier_unusable"))
            selected_npc = game._validated_scene_npc_id(
                preparsed_scene_intent, player_input
            )
            if selected_npc is None and game._named_word_of(preparsed_scene_intent):
                game._session()._named_word = game._named_word_of(preparsed_scene_intent)
            npc_resolution, selected_npc = game._rpt_selected_npc_canonical(npc_resolution=npc_resolution, selected_npc=selected_npc)
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
            deferred_referent = game._rpt_deferred_referent_next(current_location=current_location, deferred_referent_id=deferred_referent_id, world_state=world_state)
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
            _exit = game._rpt_interaction_mode_say_2(finish_turn=finish_turn, held_plan=held_plan, interaction_mode=interaction_mode, player_input=player_input, resolve_intent=resolve_intent)
            if _exit is not game._TURN_FALL_THROUGH:
                return _exit
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
        preparsed_scene_intent = game._rpt_preparsed_scene_intent(check_feature=check_feature, interaction_mode=interaction_mode, player_input=player_input, world_state=world_state)
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
        and isinstance(preparsed_scene_intent, dict)
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
                accepted_npc = game._rpt_accepted_npc_create_2(local_proposal=local_proposal, request_key=request_key, world_state=world_state)
            _exit = game._rpt_accepted_npc_created(accepted_npc=accepted_npc, existing_ids=existing_ids, finish_turn=finish_turn, flags=flags, local_proposal=local_proposal, world_state=world_state)
            if _exit is not game._TURN_FALL_THROUGH:
                return _exit
            result = game._rpt_result_action_dialogue()
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

    _exit = game._rpt_interaction_mode_say(finish_turn=finish_turn, interaction_mode=interaction_mode, npc_target=npc_target)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    game._rpt_local_dialogue_local(player_input=player_input, world_state=world_state)

    topic_name = game._rpt_topic_name_topic(interaction_mode=interaction_mode, player_input=player_input, world_state=world_state)
    _exit = game._tx_name_topic(finish_turn=finish_turn, npc_target=npc_target, player_input=player_input, topic_name=topic_name)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tx_location_query(finish_turn=finish_turn, interaction_mode=interaction_mode, npc_target=npc_target, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._rpt_character_reply_action(character_reply=character_reply, finish_turn=finish_turn)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tx_attack_decision(finish_turn=finish_turn, held_plan=held_plan, interaction_mode=interaction_mode, npc_target=npc_target, player_input=player_input, quest_world_before=quest_world_before, resolve_intent=resolve_intent, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tx_explicit_sword_drop(combat=combat, finish_turn=finish_turn, interaction_mode=interaction_mode, player_input=player_input, resolve_intent=resolve_intent, target_id=target_id)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    thread_talk = game._job_talk_with(npc_target)
    interaction_hint = game._rpt_interaction_hint_interaction(interaction_mode=interaction_mode, npc_target=npc_target, player_input=player_input, thread_talk=thread_talk)
    if interaction_hint == "plan" and (getattr(game._session(), "_front_read", None) or {}).get("kind") == "speak_to":
        interaction_hint = None  # two clauses said to a person are no plan to keep: they answer them
    npc_target = game._rpt_target_id_combat(combat=combat, npc_target=npc_target, player_input=player_input, target_id=target_id, world_state=world_state)
    interaction_hint, npc_target = game._rpt_interaction_hint_information(interaction_hint=interaction_hint, npc_target=npc_target, player_input=player_input, target_id=target_id, world_state=world_state)
    raw = None
    answer_in_person = False
    classifier_unusable, intent_model_calls, intent_source, raw = game._tg_hint_intent(check_feature=check_feature, classifier_unusable=classifier_unusable, combat=combat, intent_model_calls=intent_model_calls, intent_source=intent_source, interaction_hint=interaction_hint, npc_target=npc_target, player_input=player_input, raw=raw, scene_preparse_model_calls=scene_preparse_model_calls, world_state=world_state)
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
        conversation_rejected, conversation_resolution = game._rpt_conversation_resolution_conversation(interaction_hint=interaction_hint, npc_target=npc_target, player_input=player_input, raw=raw, world_state=world_state)
        # A reading the classifier got wrong is no reason for a person to stop being one: they answer the line.
        # A promise or a condition must never be recorded on a reading that failed; the turn's one reading was
        # not built for this proposal alone, so with it the person still answers and nothing is recorded.
        answer_in_person = (conversation_rejected and isinstance(npc_target, dict)
                            and (getattr(game._session(), "_front_reply", None) is not None
                                 or (interaction_hint in {"information", "generate"}
                                     and game._people_speak_for_themselves(world_state))))
        if conversation_rejected and not answer_in_person:
            return finish_conversation_rejection(npc_target)
        action_result = game._rpt_action_result_status_3(answer_in_person=answer_in_person, interaction_hint=interaction_hint, npc_target=npc_target, player_input=player_input, raw=raw)
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
        _exit = game._rpt_answer_person_return(action_result=action_result, answer_in_person=answer_in_person, finish_turn=finish_turn, narrated_without_model=narrated_without_model)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit

    shop_request = (interaction_mode not in {"say", "ask_dm"}
                    and target_id is None and game._explicit_campaign_shop_request(player_input))
    current_shop_count = sum(
        1 for shop in world_state.get("shops", [])
        if isinstance(shop, dict) and shop.get("location") == world_state.get("location")
    )
    _exit = game._tg_shop_request_exit(current_shop_count=current_shop_count, finish_turn=finish_turn, shop_request=shop_request, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._rpt_shop_request_import(finish_turn=finish_turn, shop_request=shop_request)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tg_shop_exit_a(finish_turn=finish_turn, interaction_mode=interaction_mode, player_input=player_input, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tg_shop_exit_b(finish_turn=finish_turn, interaction_mode=interaction_mode, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tg_shop_presence_exit(finish_turn=finish_turn, npc_target=npc_target, player_input=player_input, target_id=target_id, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tx_historical_name_query(finish_turn=finish_turn, npc_target=npc_target, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
            compound_speech = game._rpt_compound_speech_talk(npc_target=npc_target, player_input=player_input, safe_name=safe_name)
            if compound_speech and game._known_player_name(npc_target) != safe_name and not talk_front.old_owner_allowed(
                    talk_front.current(game._session()), "name_disclosure"):
                intro_fallback_name = safe_name
            if compound_speech:
                local_dialogue.remember_explicit_player_name(npc_target, safe_name)
            if compound_speech and game._detect_query_type(player_input, npc_target) == "npc_identity":
                # The player requested this identity. Python decides disclosure;
                # the model receives the now-public name, not hidden identity.
                game._handle_query(player_input, "npc_identity", npc_target)
            _exit = game._rpt_compound_speech_npc(compound_speech=compound_speech, finish_turn=finish_turn, npc_target=npc_target, player_input=player_input, safe_name=safe_name, world_state=world_state)
            if _exit is not game._TURN_FALL_THROUGH:
                return _exit

    _exit = game._tx_npc_query(finish_turn=finish_turn, npc_target=npc_target, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    _exit = game._tx_quest_availability(finish_turn=finish_turn, interaction_mode=interaction_mode, player_input=player_input, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    work_answer = game._rpt_work_answer_shop(interaction_mode=interaction_mode, player_input=player_input, shop_request=shop_request)
    _exit = game._tx_work_answer(finish_turn=finish_turn, npc_target=npc_target, work_answer=work_answer, world_state=world_state)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
        supported_entry = game._rpt_ledger_status_supported(ledger=ledger, npc_statements=npc_statements, player_input=player_input, supported_entry=supported_entry)
        import npc_told
        about = npc_statements.claim_about(player_input)
        if about != "npc_words":
            supported_entry = None  # legacy conversation text is not selected personal memory
            if (isinstance(npc_target, dict) and claimed_npc is npc_target
                    and npc_target.get("location") == world_state.get("location")):
                told_support = npc_told.supports(world_state, npc_target["id"], player_input, about=about)
        spoken_reference = game._rpt_spoken_reference_bool(about=about, claimed_npc=claimed_npc, ledger=ledger, npc_target=npc_target, player_input=player_input, world_state=world_state)
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
            action_result = game._rpt_action_result_action(claimed_npc=claimed_npc, response=response)
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

    supported_lore_response = game._rpt_supported_lore_response(lore_context=lore_context, player_input=player_input, world_state=world_state)
    _exit = game._tx_supported_lore_response(finish_turn=finish_turn, lore_context=lore_context, supported_lore_response=supported_lore_response)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    npc_place_recommendation = game._rpt_npc_place_recommendation(interaction_mode=interaction_mode, npc_target=npc_target, player_input=player_input)
    npc_dialogue_route = game._tx_npc_dialogue_route(answer_in_person=answer_in_person, experimental_unverified_claim=experimental_unverified_claim, interaction_mode=interaction_mode, npc_place_recommendation=npc_place_recommendation, npc_target=npc_target, player_input=player_input, spoken_reference=spoken_reference)
    profile_focus = interaction_adventure.current_conversation_focus(world_state, npc_target)
    canonical_profile_question = game._rpt_canonical_profile_question(npc_target=npc_target, player_input=player_input, profile_focus=profile_focus)
    experimental_dialogue_session = game._rpt_experimental_dialogue_npc(canonical_profile_question=canonical_profile_question, experimental_unverified_claim=experimental_unverified_claim, front_talk=front_talk, interaction_mode=interaction_mode, npc_dialogue_route=npc_dialogue_route, npc_target=npc_target)
    lore_safety_input = player_input
    lore_safety_input = game._tx_place_recommendation_safety_input(lore_safety_input=lore_safety_input, npc_place_recommendation=npc_place_recommendation, npc_target=npc_target, player_input=player_input)
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
    lore_gate = game._rpt_lore_gate_answerable(answerable_personal_kind=answerable_personal_kind, experimental_dialogue_session=experimental_dialogue_session, lore_context=lore_context, lore_safety_input=lore_safety_input, npc_place_recommendation=npc_place_recommendation, player_input=player_input, world_state=world_state, world_subject_question=world_subject_question)
    experimental_dialogue_session, lore_gate, npc_dialogue_route, npc_target = game._rpt_lore_gate_interaction(combat=combat, experimental_dialogue_session=experimental_dialogue_session, interaction_mode=interaction_mode, lore_gate=lore_gate, npc_dialogue_route=npc_dialogue_route, npc_target=npc_target, player_input=player_input, world_state=world_state)
    _exit = game._tx_lore_gate(finish_turn=finish_turn, lore_gate=lore_gate, npc_target=npc_target, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    smalltalk_response = game._direct_npc_smalltalk_response(player_input, npc_target)
    _exit = game._tx_smalltalk_response(action_id=action_id, experimental_dialogue_session=experimental_dialogue_session, finish_turn=finish_turn, front_talk=front_talk, interaction_mode=interaction_mode, npc_target=npc_target, player_input=player_input, smalltalk_response=smalltalk_response)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
        raw_intent = game._ts_parse_intent(experimental_npc_dialogue=experimental_npc_dialogue, experimental_unverified_claim=experimental_unverified_claim, name_stance=name_stance, npc_target=npc_target, player_input=player_input, world_state=world_state)
        conversation_rejected, conversation_resolution = game._ts_conversation_check(experimental_npc_dialogue=experimental_npc_dialogue, interaction_mode=interaction_mode, npc_target=npc_target, player_input=player_input, raw_intent=raw_intent, world_state=world_state)
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
        _exit = game._ts_witness_exit(finish_turn=finish_turn, npc_target=npc_target, player_input=player_input, raw_intent=raw_intent, witness_attempt=witness_attempt, witness_recall=witness_recall, world_state=world_state)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
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
        _exit = game._ts_personal_answer_exit(conversation_resolution=conversation_resolution, experimental_npc_dialogue=experimental_npc_dialogue, finish_conversation_resolution=finish_conversation_resolution, finish_turn=finish_turn, npc_target=npc_target)
        if _exit is not game._TURN_FALL_THROUGH:
            return _exit
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
                valid_speech_packet = game._ts_speech_packet(raw_intent=raw_intent, raw_spoken=raw_spoken, raw_stage=raw_stage)
                attributed_speech, invalid_spoken_stage_direction, model_raw_narration, raw_narration, settled_money = game._ts_speech_money(action_result=action_result, attributed_speech=attributed_speech, invalid_spoken_stage_direction=invalid_spoken_stage_direction, model_raw_narration=model_raw_narration, name_stance=name_stance, npc_statements=npc_statements, npc_target=npc_target, player_input=player_input, raw_intent=raw_intent, raw_spoken=raw_spoken, raw_stage=raw_stage, recognised=recognised, settled_money=settled_money, valid_speech_packet=valid_speech_packet, world_state=world_state)
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
            python_town_response, text = game._ts_town_response(experimental_unverified_claim=experimental_unverified_claim, invalid_or_empty=invalid_or_empty, npc_target=npc_target, player_input=player_input, python_town_response=python_town_response, raw_intent=raw_intent, text=text, unverified_history_echo=unverified_history_echo, world_state=world_state)

            text_before_finalize = text
            text = game._ts_finalize_text(action_result=action_result, attributed_speech=attributed_speech, invalid_spoken_stage_direction=invalid_spoken_stage_direction, npc_target=npc_target, player_input=player_input, python_town_response=python_town_response, text=text, unverified_history_echo=unverified_history_echo)
            after = game._rpt_after_speech_after(action_result=action_result, attributed_speech=attributed_speech, experimental_npc_dialogue=experimental_npc_dialogue, experimental_unverified_claim=experimental_unverified_claim, narration_source=narration_source, npc_target=npc_target, player_input=player_input, python_town_response=python_town_response, text=text, world_state=world_state)
            text, python_town_response, narration_source = after["text"], after["python_town_response"], after["narration_source"]
            final_safety_reason_code, final_safety_handling, stock_swapped = after["reason_code"], after["handling"], after["stock_swapped"]
            speech_checks = None
            if experimental_npc_dialogue:
                # D-252: the names of the checks that changed or replaced this reply, for the route log. Never words.
                kept = attributed_speech["spoken_text"].strip() if attributed_speech else ""
                said = raw_spoken.strip() if isinstance(raw_spoken, str) else ""
                speech_checks = game._rpt_speech_checks_name(attributed_speech=attributed_speech, invalid_or_empty=invalid_or_empty, kept=kept, python_town_response=python_town_response, raw_intent=raw_intent, said=said, stock_swapped=stock_swapped, text=text, text_before_finalize=text_before_finalize, unverified_history_echo=unverified_history_echo)
                if final_safety_reason_code:
                    speech_checks.append(f"safety:{str(final_safety_reason_code)[:40]}")
                game._rpt_speech_debug_trail(experimental_unverified_claim=experimental_unverified_claim, invalid_or_empty=invalid_or_empty, model_raw_narration=model_raw_narration, npc_target=npc_target, player_input=player_input, raw_intent=raw_intent, raw_narration=raw_narration, text=text, text_before_finalize=text_before_finalize, unverified_history_echo=unverified_history_echo)
            accepted_model_speech = game._rpt_accepted_model_speech(attributed_speech=attributed_speech, experimental_npc_dialogue=experimental_npc_dialogue, invalid_or_empty=invalid_or_empty, text=text, unverified_history_echo=unverified_history_echo)
            turned_down_what_was_paid = (
                accepted_model_speech and settled_money.get("moved")
                and game._npc_speech_rejects_claim(attributed_speech["spoken_text"])
            )
            accepted_model_speech, text = game._rpt_turned_down_what(accepted_model_speech=accepted_model_speech, attributed_speech=attributed_speech, npc_target=npc_target, player_input=player_input, settled_money=settled_money, speech_checks=speech_checks, text=text, turned_down_what_was_paid=turned_down_what_was_paid, world_state=world_state)
            if speech_checks is not None:
                game._session()._speech_checks = speech_checks
            if experimental_unverified_claim:
                action_result.update(status="unverified", success=False)
            text = game._ts_accepted_text(accepted_model_speech=accepted_model_speech, action_result=action_result, attributed_speech=attributed_speech, experimental_npc_dialogue=experimental_npc_dialogue, final_safety_handling=final_safety_handling, npc_target=npc_target, player_input=player_input, profile_focus=profile_focus, stock_swapped=stock_swapped, text=text, text_before_finalize=text_before_finalize, world_state=world_state)

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
            game._ts_price_reply_commit(action_result=action_result, negotiation=negotiation, npc_target=npc_target, player_input=player_input, price_reply_accepted=price_reply_accepted, resolve_intent=resolve_intent, target_id=target_id)
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
            game._validate_interaction_conversation(
                player_input,
                world_state,
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
            _exit = game._rpt_action_result_status_2(action_result=action_result, finish_turn=finish_turn, npc_target=npc_target)
            if _exit is not game._TURN_FALL_THROUGH:
                return _exit
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
    action_result = game._tg_shop_action_result(npc_target=npc_target, player_input=player_input, resolve_intent=resolve_intent, shop_request=shop_request, target_id=target_id, validated_intent=validated_intent)
    if DEBUG_MODE:
        print("[RULE ENGINE]")
        print(json.dumps({key: value for key, value in action_result.items() if key != "direct_response"}, ensure_ascii=False, indent=2))

    _exit = game._rpt_action_result_status(action_result=action_result, finish_turn=finish_turn, player_input=player_input)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    if action_result.get("action") == "combat_move":
        return finish_turn(action_result, action_result["direct_response"], is_final=True)  # the engine tells it

    _exit = game._tg_attack_findings_exit(action_result=action_result, finish_turn=finish_turn, quest_world_before=quest_world_before)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

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
        game._rpt_action_result_verified(action_result=action_result, early_bound=early_bound, early_changed=early_changed, player_input=player_input, shop_request=shop_request)
        if action_result["verified_world_updates"].get("create_features"):
            findings = None
    _exit = game._tg_findings_text_exit(action_result=action_result, findings=findings, finish_turn=finish_turn, quest_world_before=quest_world_before)
    if _exit is not game._TURN_FALL_THROUGH:
        return _exit

    proposed_entry = action_result.get("action") == "travel" and action_result.get("completion") == "completed"
    allow_new_locations = bool(action_result.get("proposal_required"))
    expected_location_change = proposed_entry or world_state.get("location") != previous_location
    allow_new_npcs = game._rpt_allow_new_npcs(expected_location_change=expected_location_change, player_input=player_input, shop_request=shop_request)
    allow_new_features = game._rpt_allow_new_features(expected_location_change=expected_location_change, player_input=player_input, shop_request=shop_request)
    scene_parent = game._scene_detail_parent(
        world_state.get("location"), player_input
    )
    game._rpt_scene_parent_living(action_result=action_result, player_input=player_input, scene_parent=scene_parent)
    if isinstance(raw_intent, dict):
        scene_detail_proposals = raw_intent.get("scene_detail_proposals")
        game._rpt_scene_detail_proposals(action_result=action_result, allow_new_features=allow_new_features, scene_detail_proposals=scene_detail_proposals, scene_parent=scene_parent)
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
