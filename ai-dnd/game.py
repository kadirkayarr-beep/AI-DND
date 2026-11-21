if __name__ == "__main__":
    import game
    from game_parts import terminal
    raise SystemExit(terminal.run(input_fn=input, print_fn=print))
import ollama
import random
import json
import re
import unicodedata
import collections
import copy
import equipment_economy
import refusals
import tr_case
import tr_names
from pathlib import Path
import hashlib
import os
import tempfile
import contextlib
import contextvars
import functools
import sys
import types
from uuid import uuid4
from quest_catalog import catalog as quest_catalog, find_quest
import adventure
import adventure.director as adventure_director
import adventure.play as adventure_play
import incidents.hooks as incident_hooks
import incidents.projection as incident_projection
import living_world
import local_dialogue
import local_exploration
import held_weapon
import monster_sense
import name_catalog
import campaign_time
import scheduled_events
import timed_gameplay
import combat_lifecycle
import action_economy
import initiative
import weapon_attack
import effect_targeting
import attributed_claims
import effect_lifecycle
import event_order
import interaction_adventure
import money_owner
import talk_front
import npc_statements
import talk_mode
from weapon_catalog import WEAPONS
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from api.dnd_2024_rules import get_expertise_choice_count
from api.core_resolution import (
    resolution_action_scope,
    resolve_attack_roll,
    resolve_death_save,
    resolve_saving_throw,
    resolve_skill_check,
)

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


from game_parts.text_rules_a import ollama_response_content, ollama_reply_was_cut, _ASKS_SOMETHING, _just_served, _THIRD_PERSON_REPORT, _SECOND_PERSON_SAID, _SAID_IT_AGAIN, _ENDS_IN_SPEECH, is_ordinary_environment_look, npc_ambiguity_response, _NEGATED_VERB_SUFFIX, _affirmative_door_verb, _SKILL_CHECK_WORD, _SKILL_ENDING, _ABILITY_WORD, _OPEN_SCARE, _COVER_WORD, _COVER, _OWN_THING_HIDDEN, _READING_CHECKS, _COMMON_SENTENCE_OPENERS, _QUESTION_CUE_RE, clean_dm_response, _hand_names_something, _ARMED_ROLE, _STRONG_ROLE, _PERSON_FIGHT, _clean_world_text, _scene_texts_for_referents, _ENGLISH_STOP_WORDS, _reads_english, _SAVE_ABILITY_TR, _unarmed_save_text, _FALL_LINE, _REWOUND_LINE, _PROPOSAL_MARKER_RE, _INTERNAL_MARK_RE, _strip_proposal_markers, _normalize_interaction_mode, _GUARD_ROLE, _GUARD_WORD, _GENERIC_PERSON, _is_guard, _serves_at_a_counter, _topic_place_name, _LOCATED_PERSON, _IN_REACH_WORDS, _COUNTER_WORDS, _COUNTER_ROLE, _drop_repeated_sentences




# ---------------------------------------------------------
# ZAR SİSTEMİ
# ---------------------------------------------------------

from game_parts.character_rules import roll_d20


from game_parts.character_rules import get_modifier, roll_stat, choose_option, create_random_character, assign_stats, choose_skill_proficiencies, calculate_hp, calculate_ac, _perform_skill_check, _new_species_trait_state, _new_persisted_species_trait_state, initialize_species_trait_state, calculate_attack_bonus, roll_attack, roll_damage, _species_trait_state, roll_initiative, roll_initiative_npc, roll_initiative_player




# ---------------------------------------------------------
# IRKLAR
# ---------------------------------------------------------

from game_parts.tables import RACES, RACE_FEATURES, CLASSES, CLASS_FEATURES, CLASS_HIT_DICE, SKILLS, CLASS_SKILL_OPTIONS, DIFFICULTY_DC, RANDOM_NAMES, GIANT_ANCESTRY_IDS, CELESTIAL_REVELATION_FORMS, INNER_RADIANCE_SPEC, NECROTIC_SHROUD_SPEC, SPECIES_WITH_TRAIT_STATE, _ABILITY_NAMES, _ORIGIN_TEXT_KEYS, _ORIGIN_LIST_KEYS, _ORIGIN_SCORE_KEYS, DEATH_MODES, CHECK_FEATURES


# ---------------------------------------------------------
# IRK ÖZELLİKLERİ
# ---------------------------------------------------------



# ---------------------------------------------------------
# SINIFLAR
# ---------------------------------------------------------



# ---------------------------------------------------------
# SINIF ÖZELLİKLERİ
# ---------------------------------------------------------



# ---------------------------------------------------------
# HIT DICE
# ---------------------------------------------------------



# ---------------------------------------------------------
# SILAHLAR
# ---------------------------------------------------------

# ---------------------------------------------------------
# SKILLER
# ---------------------------------------------------------



# ---------------------------------------------------------
# SINIF SKILL SEÇENEKLERİ
# ---------------------------------------------------------



# ---------------------------------------------------------
# ZORLUKLAR
# ---------------------------------------------------------



# ---------------------------------------------------------
# SEÇİM FONKSİYONU
# ---------------------------------------------------------



# ---------------------------------------------------------
# RANDOM KARAKTER İSİMLERİ
# ---------------------------------------------------------





# ---------------------------------------------------------
# STAT DAĞITIMI
# ---------------------------------------------------------



# ---------------------------------------------------------
# SKILL PROFICIENCY SEÇİMİ
# ---------------------------------------------------------



# ---------------------------------------------------------
# HP
# ---------------------------------------------------------



# ---------------------------------------------------------
# AC
# ---------------------------------------------------------



# ---------------------------------------------------------
# SKILL CHECK
# ---------------------------------------------------------

from game_parts.character_rules import perform_skill_check




# ---------------------------------------------------------
# AI EYLEM ANALİZİ
# ---------------------------------------------------------

from game_parts.intent import is_dialogue_or_emotion, _is_negated_dialogue_action, _reads_as_question, _people_speak_for_themselves, _asked_of_the_one_at_hand, is_npc_dialogue_input, _is_conversation_start_input, _is_local_place_question, _unverified_past_event_assertion, _report_of_someone_else, is_npc_historical_claim, _reported_npc_claim_followed_by_player_inspection, named_skill, open_scare_try, _stealth_skill, _word_check_for_action, known_player_action_narration, known_character_answer, _model_query_type_is_plausible, _detect_query_type, _detect_explore_type, _query_location_candidates, resolve_python_world_action, analyze_player_action, _travel_destination_reference_in_text, _intent_scene_npc_candidates, _recent_player_visible_narration, _validated_scene_npc_id, _named_word_of, _validated_local_person_proposal, _scene_detail_proposals_allowed, _scene_observation_proposal_turn, _local_person_request_key, _experimental_speech_final_line, _local_place_recommendation_guidance, IntentInfrastructureError, _has_travel_language, _travel_completion, _normalize_turkish_location






















from game_parts.dialogue import _claimed_completed_outcome, _conversation_npcs, _active_interlocutor, _clear_active_interlocutor, _is_end_conversation_request, _without_place_names, _words_fit_person, most_plausible_addressee, _absent_described_person, _absent_person_text, _settle_address, _word_for_nobody_here, resolve_npc_reference, _interaction_proposal_applies, _grounded_item_request_proposal, _explicit_addressee, _is_spoken_to, _is_short_conversation_continuation, _is_object_inspection, _is_door_inspection_request, record_npc_interaction, _remember_owner_locked_tavern_focus, _remember_accepted_profile_focus, npc_memory_supports_claim, npc_memory_supporting_entry, _STOCK_SAID, _stock_said, _stock, _is_stock, _only_stock, _without_lines_already_said, historical_claim_denial, named_by_sight, _npc_speech_enabled, _experimental_recent_exchanges, _speech_answer_rules, _remember_experimental_npc_speech, _clean_npc_speech, _render_experimental_npc_speech, _npc_speech_is_claim_refusal, _npc_name_stance, _town_note, _has_spoken_to_player, _job_talk_with, _offer_terms_shown, _nobody_here, _thread_person, _physical_line, _job_gate, _town_in_play, _named_elsewhere_line, _town_fallback, _person_fallback, _experimental_npc_dialogue_context




























from game_parts.coin import _SOMEONE_ELSES_PURSE, _SHOP_ECONOMY_PATTERN, _SHOP_TRANSACTION_REQUEST_PATTERN, _SHOP_ENTITY_QUERY_PATTERN, _SHOP_CREATION_ACTION_PATTERN, _is_shopkeeper_role, _runs_a_shop, _campaign_has_shopkeeper, _explicit_campaign_shop_request, _shop_economy_request, _explicit_campaign_shop_negative_request, _shop_presence_question, generate_shop_id, validate_shop_proposal, create_shop_from_proposal, COIN_LEFT_BEHIND






from game_parts.intent import deterministic_check_for_action, _handle_query, parse_player_intent, normalize_intent, update_world_state_from_player, execute_intent

























# ---------------------------------------------------------
# AI DUNGEON MASTER CEVABI
# ---------------------------------------------------------




recent_dm_narrations = []
world_state = {
    "campaign_id": None,
    "location": "Henüz belirlenmedi",
    "locations": {
        "tavern": {
            "id": "tavern", "name": "Taverna", "type": "building",
            "aliases": ["taverna", "tavernaya", "tavernada", "meyhane", "meyhaneye", "meyhanede"],
            "description": "",
        },
        "forest": {
            "id": "forest", "name": "Orman", "type": "wilderness",
            "aliases": ["orman", "ormana", "ormanda"],
            "description": "",
        },
        "castle": {
            "id": "castle", "name": "Kale", "type": "building",
            "aliases": ["kale", "kaleye", "kalede"],
            "description": "",
        },
    },
    "next_location_number": 1,
    "heard_rumours": [],
    "npcs": [],
    "shops": [],
    "next_shop_number": 1,
    "inventory": ["Macera çantası", "Kılıç"],
    "equipment": {"main_hand": "longsword", "off_hand": None},
    "ground_items_by_location": {},
    "ground_items": [],
    "doors": [],
    "containers": [],
    "features": [],
    "scene_state": living_world.initial_scene_state(),
    "events": [],
    "flags": {**talk_mode.fresh(), "turn_index": 0, "pending_destination": None},
    "next_npc_number": 1,
    equipment_economy.GEAR_WRITTEN: True,  # D-231: every person of a new world gets their gear when made
    equipment_economy.PURSE_WRITTEN: True,  # D-207: and their purse
    "combat": {
        "schema_version": 3,
        "active": False,
        "status": "ended",
        "combat_id": None,
        "round": 0,
        "initiative_order": [],
        "current_turn_index": 0,
        "current_actor_id": None,
        "participants": [],
        "participant_records": [],
        "actions_used": [],
        "target_id": None,
        "end_reason": None,
    },
    "player_combat_status": "active",
    "death_state": {
        "mode": "NORMAL",
        "successes": 0,
        "failures": 0,
        "stable": False,
        "dead": False,
        "terminal": False,
        "prone": False,
        "last_death_save_turn_key": None,
        "last_death_save_result": None,
        "last_resolution": None,
        "combat_checkpoint": None,
        "recovery": None,
        "noncombat_next_save_at": None,
        "noncombat_episode_id": None,
    },
    "player_knowledge": [],
    "quests": [],
    "quest_processed_event_ids": [],
}
INITIAL_WORLD_STATE = copy.deepcopy(world_state)
from game_parts.savefile import SAVE_FORMAT_VERSION, _SUPPORTED_SAVE_VERSIONS, _validate_species_trait_state, _origin_choices_valid, _origin_choices_for_save, _PERSISTED_PLAYER_CONDITION_FIELDS, _validate_player_condition_state, _validate_player_weapon_proficiencies, _player_state_for_save, serialize_game_state, _validate_combat_v3_payload, _validate_long_rest_history, _validate_saved_multilevel_slots, _validate_save_payload, save_game, _repair_dilim1_fields, _known_happenings, _repair_dilim2_fields


# K01: PHB 2024 (D&D 5e - Players Handbook 2024.pdf, PDF page 185, Aasimar > Celestial Revelation > Necrotic Shroud):
# "Creatures other than your allies within 10 feet of you must succeed on a Charisma saving throw ... or have the Frightened condition".
# K02: "each creature within 10 feet of you takes Radiant damage" (same page, Inner Radiance); allies are not excluded.
# K04: the recorded order of simultaneous due items (technical decision record, see event_order.py).
RULE_ORDER = event_order.DEFAULT_RULE_ORDER






























from game_parts.combat_flow import long_rest_gap_seconds, _death_state_defaults, ensure_death_state, PlayerCannotAct, require_player_can_act, stabilize_player, attempt_player_stabilization, heal_player, set_player_max_hp, apply_npc_damage, _capture_combat_death_checkpoint, _restore_combat_death_checkpoint, _finalize_player_death, _apply_player_damage, _combat_defaults, _combat_record_for_actor, _migrate_legacy_combat_state, _sync_combat_participant_records, ensure_combat_state, person_fight_kind, _person_fight, ensure_npc_enemy_stats, ensure_npc_combat_stats, resolve_combat_target, _set_temporary_hit_points, grant_temporary_hit_points, _species_bonus_action, _species_player_turn_id, _apply_species_on_hit_effects, _finish_species_player_turn
















from game_parts.savefile import load_game


from game_parts.places import _tavern_door_notice, _venue_door_id, _venue_door_for, _venue_entry_door, _locked_door_refusal, _mark_lock_seen, _lock_known_to_player, _current_door, _normalize_ground_items, location_features, feature_descriptions, active_npcs, _clean_world_text_list, _has_unregistered_person_name, validate_npc_proposal, create_local_feature, _valid_local_feature_parent_id, _legacy_hidden_feature_name_collision, _local_detail_claims_unsupported_mechanics, _feature_proposal_conflicts_with_canonical_door, location_display_name, _location_alias_values, _reference_token_matches, _entity_reference_in_text, resolve_location_reference, _location_reference_in_text, normalize_location_id, validate_location_proposal, _local_place_recommendation_options, _local_place_access, _attributed_place_note, _ground_local_place_recommendation_reply, _ground_local_place_recommendation_stage, _explicit_sword_drop, update_inventory_from_player, apply_check_outcome_to_world_state, _names_current_local_exit, _engine_location_parent, _existing_local_tavern, _resolve_explicit_local_scene_parent, _scene_detail_parent, _anchored_structure_features, _ensure_local_tavern
















from game_parts.narration import _narration_fact_packet, _repair_internal_marks, _filter_unaccepted_proposal_mentions, _drop_absent_counter_sentences, _narrator_fact_view, create_location_from_proposal, _current_npc_name, _quiet_place_line, _generic_no_change_response, _natural_unresolved_action_response, _unseen_speaker_repaired, should_generate_npcs, should_generate_features, _rejected_lore_narration, _feature_refs_are_visible, _ensure_venue_window, _bound_on_a_named_word, _found_on_a_pass, _inspection_findings, _repair_attributed_speech, _narration_contradicts_supported_name_memory
























































from game_parts.places import generate_npc_id, create_npc_from_ai, clean_location_description, commit_location_change, _ensure_location_entities, _commit_travel_action, _ensure_local_merchant, _scene_presence_text, _promote_scene_referent, _adventure_travel_reply










































































from game_parts.combat_flow import resolve_species_trait_action, resolve_attack, register_attack_hook, _combat_participant_can_act, _mark_combat_action_used, _resolve_player_death_turn, _spares_the_fallen, _combat_end_if_decided, _resolve_enemy_turns_until_player, find_weapon_in_inventory, start_combat, _start_combat_with_initiative, resolve_enemy_attack, _reduce_attack_damage_to_player, _storm_thunder_reaction, _apply_attack_damage_to_player, end_combat, _begin_combat_actor_turn, join_combat_participants, remove_combat_participant, register_initiative_hook, advance_combat_turn, _combat_snapshot, _finish_combat_result






















































from game_parts.combat_flow import _public_combatant_label, _combat_narration, _enemy_exchange_text, _death_closing, _death_save_line, _down_outside_combat_turn, _death_resolution_from_actions












from game_parts.narration import validate_world_updates, _bind_world_update_mentions, merge_world_updates, _narrator_shop_record, build_world_context, _stands_by_their_words, _fallback_narration, _dm_response_schema_for_turn












from game_parts.lore import _filter_unsupported_lore_paragraphs, _empty_lore_authority_context, _prepare_lore_authority_context, _is_registered_lore_name, _has_unregistered_narrative_entity, _stage_within_the_street, _shown_stage_direction, _unverified_lore_response, _names_the_district_here, _narration_has_unsupported_lore_claim, _repair_unsupported_lore_narration, _scene_has_registered_craft_role, _supported_lore_question_response, _player_question_has_unverified_lore_claim






































from game_parts.text_rules_a import _is_plain_person_reference, _ADDRESSEE_OPERATIONS, _OFFER_OPERATIONS, _OFFER_MARKER, _fold_keep_punctuation, _ADDRESS_VERB, _SPEAKING_VERB, _CONTINUATION_TERMS, _OBJECT_INSPECTION, _claim_keywords, _format_npc_memory, _CLAIM_DENIAL_LINES, _SPEECH_REPEAT_LINES, _lines_already_said, speech_repeat_line, _NARRATOR_PROFILE_FIELDS, _narrator_visible_profile, _bodies_here_context, _untrusted_player_block, _extract_json_object, _NPC_SPEECH_LOG_KEY, _NPC_SPEECH_KEEP, _MENTIONS_PROMPT_RULE, _VOICED_PROMPT_RULE, _rumour_lane_on, _voiced_keys, _CLAIM_REJECTION_RE, _CLAIM_ACCEPTANCE_RE, _SPEECH_CUT_RE, _SPEECH_META_RE, _strip_pictographs, _REAL_WORLD_FAITH, _without_real_world_faith, _is_explicit_name_led_gesture_line, _clean_npc_stage_direction, _compose_experimental_npc_speech, _without_label_variant, _npc_speech_rejects_claim, _CLAIM_PLAIN_DENIAL_RE, _npc_speech_grants_claim, _spoken_name_answer, _SPEECH_ANSWER_RULES, _job_news_line, _turns_to_someone_else, _elsewhere_line, _overheard_work, _ASKS_WHO_YOU_ARE, _accept_named_job, _REFUSED_MOVE_RULE, _bag_note, _dm_prompt_note, _claim_denial_quotes, _has_private_profile_value, _FOLLOWUP_WORDS, _is_short_followup, _experimental_speech_recap, _normalize_turkish_typos, _mechanical_outcome, _GENERIC_NO_CHANGE_RESPONSE, _GENERIC_NO_CHANGE_RESPONSES, _INTERNAL_PLAYER_FACING_RE, _is_internal_player_facing_text, _narration_scene_type




from game_parts.dialogue import _npc_answers_to, _offer_talk_with, _job_fallback, _coin_persuasion, _show_coin_roll, _settle_spoken_commitment, _with_only_backed_money, _experimental_speech_note









































































































from game_parts.living_world_turn import ensure_campaign_clock, _living_world_prompt_context, _observe_anchored_structure, resolve_scene_seating


def advance_campaign_time(seconds, reason, source=None, observation=None):
    world = _session().world_state
    if type(seconds) is not int or not 0 <= seconds <= campaign_time.DAY * 365:
        raise ValueError("Resolved gameplay duration is invalid.")
    source = source or f"turn:{world.get('flags', {}).get('turn_index', 0)}"
    if "campaign_time" not in world:
        return campaign_time.advance(world, seconds, reason, source, observation=observation)
    before = campaign_time.public_time(world)
    event_order.require_complete(RULE_ORDER)  # K04: never discover a gap after the clock has already moved
    remaining, elapsed, known, death_results, effect_events = seconds, 0, [], [], []
    while True:
        death = ensure_death_state()
        now = world["campaign_time"]["elapsed_seconds"]
        zero = _session().character["current_hp"] == 0 and not death["dead"]
        if zero and death["stable"] and death["recovery"] is None and remaining:
            stabilize_player()
        noncombat = zero and not death["stable"] and not world.get("combat", {}).get("active")
        if noncombat and death["noncombat_next_save_at"] is None and remaining:
            death["noncombat_next_save_at"] = now + 6
        if noncombat and death["noncombat_episode_id"] is None and remaining:
            death["noncombat_episode_id"] = str(uuid4())
        deadline = (death["recovery"]["at"] if zero and death["stable"] and death["recovery"]
                    else death["noncombat_next_save_at"] if noncombat else None)
        step = remaining if deadline is None else min(remaining, max(0, deadline - now))
        supplies = world.get("supplies_policy", {}).get("enabled", False)
        if supplies:
            midnight = campaign_time.DAY - (world["campaign_time"]["start_second"] + now) % campaign_time.DAY
            step = min(step, midnight)
        result = campaign_time.advance(
            world, step, reason, source,
            observation=None if zero or world.get("player_combat_status") == "unconscious" else observation,
        )
        elapsed += result["elapsed_seconds"]
        remaining -= result["elapsed_seconds"]
        known.extend(result["player_known_events"])
        # K03: timed effects consume the ACTUAL elapsed seconds of this step, once per (source, step start).
        def settle_effects(elapsed_step=result["elapsed_seconds"], step_start=now):
            effect_events.extend(effect_lifecycle.advance_effects(
                _session(), elapsed_step, f"{source}@{step_start}",
                "round" if reason == "combat_round" else "clock"))

        # K04: when the death/recovery timer is due at the same moment, the recorded rule order decides which runs first.
        step_end = world["campaign_time"]["elapsed_seconds"]
        due_kind = (None if deadline is None or step_end < deadline
                    else "regeneration" if death["stable"] else "death")
        effects_first = due_kind is None or event_order.order_due_events(
            [{"event_id": "effects", "kind": "effect_expiry", "at": step_end},
             {"event_id": "death-timer", "kind": due_kind, "at": step_end}], RULE_ORDER,
        )[0]["event_id"] == "effects"
        if effects_first:
            settle_effects()
        if supplies:
            import equipment_economy
            condition_death = equipment_economy.process_supply_days(_session(), now)
            if condition_death:
                death_results.extend(condition_death["death_results"])
                if not effects_first:
                    settle_effects()  # the step's time has passed; deferred effects must still consume it
                return dict(result, elapsed_seconds=elapsed, requested_seconds=seconds,
                            remaining_seconds=remaining, player_known_events=known,
                            death_results=death_results, condition_death=True, interrupted=True,
                            effect_events=effect_events)
        now = world["campaign_time"]["elapsed_seconds"]
        if deadline is not None and now >= deadline:
            if death["stable"]:
                heal_player(1)
                death_results.append({"action": "stable_recovery", "current_hp": 1})
            else:
                save = _resolve_player_death_turn(
                    noncombat_key=f"noncombat:{death['noncombat_episode_id']}:{deadline}"
                )
                death_results.append({"action": "death_save", "death_save": save})
                death = ensure_death_state()
                if save and save.get("death_resolution", {}).get("rolled_back"):
                    return dict(result, elapsed_seconds=0, requested_seconds=seconds,
                                remaining_seconds=seconds, death_results=death_results,
                                player_known_events=[], after=campaign_time.public_time(world),
                                effect_events=effect_events)
                if _session().character["current_hp"] == 0 and not death["dead"] and not death["stable"]:
                    death["noncombat_next_save_at"] = deadline + 6
        if not effects_first:
            settle_effects()
        if remaining == 0 or result["interrupted"] or ensure_death_state()["dead"]:
            break
    adventure_play.settle_session(_session())
    return dict(result, elapsed_seconds=elapsed, requested_seconds=seconds,
                remaining_seconds=remaining, before=before, player_known_events=known,
                death_results=death_results, effect_events=effect_events)




from game_parts.schemas import INTENT_TYPES, SKILL_INTENT_TO_SKILL, INTENT_SCHEMA, SCENE_DETAIL_KIND_ALLOWLIST, NPC_SCHEMA, LOCATION_SCHEMA, WORLD_UPDATE_SCHEMA, DM_RESPONSE_SCHEMA, NARRATOR_VOICE, system_prompt


# SECURITY: LLM01/LLM07 (Prompt Injection, prompt-construction layer; System Prompt Leakage)
# Level: B (Moderate) | Pattern: system_prompt_template (untrusted delimiter)
# Applied by: llm-secure-patterns v1.0.0 / System Prompt Design | 2026-10-22
# Behavioral hint to the model, not an enforced boundary. The player's text is
# shown verbatim (never edited), so a faithful quote of it still equals the
# original input that interaction_adventure.resolve_conversation compares with.
# The boundary id is a digest of that exact text, so the text cannot contain its
# own matching closing tag; look-alike tags inside it stay inert text.






















from game_parts.schemas import _EXPERIMENTAL_NPC_SPEECH_SCHEMA
from game_parts.schemas import _EXPERIMENTAL_NPC_SPEECH_OPTIONS


def _speech_debug_trail(record):
    """Append one JSON line per speech turn to the file named by AI_DND_SPEECH_DEBUG.

    Off unless the variable is set. It exists because a saved turn keeps only the
    shown text: when a stock line appears, this trail says what the model really
    returned and which rule replaced it. Local file only; never raises into a turn.
    """
    path = os.environ.get("AI_DND_SPEECH_DEBUG", "").strip()
    if not path or path.lower() in ("0", "off"):
        return
    try:
        import datetime as _datetime
        entry = {"at": _datetime.datetime.now(_datetime.timezone.utc).isoformat(), **record}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        return




























































def _has_session():
    return _ACTIVE_SESSION.get(None) is not None














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
    session = _session()
    world = session.world_state
    if interaction_mode == "ask_dm" or world_threads.view(world) is None or world.get("combat", {}).get("active"):
        return None
    journey = world.get("journey")
    if journey and journey.get("status") != "ARRIVED":
        return None
    saved = None
    try:
        person = _thread_person(player_input, target_id)
        gate = _job_gate(world, person, player_input)
        if gate is None:
            # Money asked of someone with no job to their name is still said to them, and they answer it.
            spoken_to = isinstance(person, dict) and world_threads.asks_for_pay(player_input) and not _physical_line(player_input)
            return {"decision": None, "npc_id": person["id"]} if spoken_to else None
        # A validated payment utterance is not a work action. Explicit front work has its own writer.
        coin = getattr(session, "_front_coin", 0)
        if (gate["decision"] == "work" and isinstance(front, dict) and front.get("kind") == "speak_to"
                and type(coin) is int and coin > 0):
            return None
        if (gate["decision"] is None and not gate.get("yes_heard") and interaction_mode != "say"
                and _physical_line(player_input)):
            return None
        session.require_player_can_act()
        saved = session._capture_runtime_snapshot()
        return _carry_out_thread_turn(session, world, gate, person, player_input)
    except PlayerCannotAct:
        raise
    except Exception:
        town_knowledge.log_failure()
        if saved is not None:  # D-011: a writer that broke half way leaves no coin, hour or item of it behind
            session._restore_runtime_snapshot(saved)  # in place: the turn above still holds these very dicts
        session._thread_turn = None
        return None














































































from game_parts.intent import validate_intent, _names_present_creature, _has_explicit_attack_verb, _is_explicitly_negated_attack, primal_knowledge_check_admission

































from game_parts.text_rules_b import _NARRATION_PERSISTENT_OBJECT_HEADS, _NARRATION_PERSISTENT_OBJECT_STATE, _registered_persistent_object_names, _HELD_SKIP, _PLAYER_MENTAL_STATE_PREFIXES, _PLAYER_MENTAL_STATE_CONTEXT_RE, _PLAYER_MENTAL_STATE_COPULA_RE, _PLAYER_MENTAL_STATE_EXPLICIT_SUBJECT_RE, _PLAYER_MENTAL_STATE_AFFECT_RE, _PLAYER_FEELING_RE, _is_figurative_key_transfer, _NARRATED_NAME_PATTERNS, _unseen_registered_names, _SPEAKING_NAME_PATTERNS, _unseen_speakers, _lore_claims_are_supported, _lore_guard_text, _lore_fact_records, _LORE_ENTITY_TITLE_RE, _LORE_PROPER_NAME_RE, _LORE_ENTITY_FOLLOWING_CUE_RE, _LORE_SENTENCE_START_WORDS, _GENERIC_SPEAKER_LABEL_RE, _is_generic_speaker_label, _LORE_UNSUPPORTED_DETAIL_PATTERNS, _LORE_RULER_TITLE_RE, _LORE_ENTITY_RELATION_RE, _LORE_ROUTE_DISTANCE_QUERY_RE, _UNVERIFIED_LORE_RESPONSE, _UNVERIFIED_DISTANCE_RESPONSE, _UNVERIFIED_RULER_RESPONSE, _INDOOR_DETAIL, _ASKS_DISTANCE, _salvage_plain_speech, _TERMINATOR_MASK, _split_sentences_keep_speech, _spoken_lore_fact_ids, _has_active_local_npc_focus_for_place_request




from game_parts.narration_safety import _unregistered_persistent_object_claim, _unregistered_held_object, _resolve_campaign_npc_reference, _unsupported_npc_history_or_relationship_claim, _unverified_player_mental_state_trigger, _authorized_item_transfer_matches, _is_explicitly_negated_transfer, _experimental_private_npc_disclosure, _unseen_self_introductions, _narration_is_unsafe, is_player_world_assertion, _record_narration_safety, _remove_trigger_sentence, _unsupported_available_quest_claim






























from game_parts.text_rules_a import _inside_speech, _SPEECH_SPAN_RE








from game_parts.narration_safety import _narration_safety_decision




















from game_parts.lore import _lore_entity_names

















































from game_parts.text_rules_b import _validated_player_line, _WINDOW_WORDS, _LOCK_WORDS, _TRACK_WORDS, _resolved_skill_result_narration, _TELLS_FAILURE, _UNMOVED, _QUOTE_CLOSER_RE, _QUOTE_OPENER_RE, _trim_dangling_quote, _dialogue_repair_has_attributed_answer, _skill_result_category, _print_skill_result, _ATTACK_VERB_PATTERN, _ATTACK_BLOW_PHRASE, _CHARGING_IN, _ATTACK_LOOKALIKE_TOKEN, _ATTACK_INSTRUMENT_TOKENS, _INANIMATE_HIT_OBJECT, _CREATURE_REFERENCE, _attack_verb_tokens, _immediate_check_refusal, _turkish_genitive_form, _asks_what_is_going_on, _is_bare_greeting, _is_scene_referent_activity_observation, _public_scene_person_text, _LOOK_OPENINGS, _CONVERSATION_OPENINGS, _OWN_ACTS, _WALKED_UP, _said_after_approach, _SAY_VERBS, _SAY_ENGLISH, _HAIL_FILLERS, _line_addresses, _PLANNER_STAYS_OUT, _NO_BLOW_NOW, _BLOW_WORDS, _word_root, _NOT_A_LOCAL_PLACE, _NARRATOR_PRONOUNS, _NARRATOR_PLURAL, _singular_narrator








from game_parts.narration import ask_dungeon_master, _finding_says_too_much, _states_the_failed_check, _fallback_for_action_result, _narrated_money_can_lie, finalize_narration




































from game_parts.dialogue import _is_player_name_inquiry_to_npc, _is_historical_player_name_query, _hero_first_name, _explicit_player_name_disclosure, _known_player_name, _historical_player_name_from_npc_memory, _historical_player_name_from_claims, _direct_npc_smalltalk_response, _conversation_opening_line, _stock_hearer, _said_to_someone_here




















# ---------------------------------------------------------
# OYUN BAŞLANGICI
# ---------------------------------------------------------

from game_parts.new_game import initialize_game


# ---------------------------------------------------------
# AI DUNGEON MASTER
# ---------------------------------------------------------




messages = [
    {
        "role": "system",
        "content": system_prompt
    }
]


DEBUG_MODE = False


def _world_snapshot():
    world_state = _session().world_state
    _normalize_ground_items()
    return {
        "combat": json.dumps(world_state.get("combat", {}), sort_keys=True),
        "player_current_hp": _session().character["current_hp"],
        "player_max_hp": _session().character["max_hp"],
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
    after = _world_snapshot()
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
    world_state = _session().world_state
    intent = intent if isinstance(intent, dict) else {"intent": "unknown"}
    intent_type = intent.get("intent", "unknown")
    if intent_type == "travel" and ensure_combat_state()["active"]:
        target = intent.get("target") if isinstance(intent.get("target"), dict) else {}
        approached = None
        if not combat_lifecycle.is_attack_decision(_session(), player_input) and target.get("type") == "npc":
            npc_id = target.get("npc_id") if isinstance(target.get("npc_id"), str) and target["npc_id"].strip() else None
            approached = _approach_turn(npc_id or getattr(_session(), "_front_approach", None))
        if approached is not None:
            return approached
        if combat_lifecycle.is_attack_decision(_session(), player_input):
            intent_type = "attack"
            intent = {**intent, "intent": "attack"}
        elif (combat_lifecycle.walks_off(_session(), player_input)
              or combat_lifecycle.walks_on_own_feet(_session(), player_input)):
            raise combat_lifecycle.CombatRequestError("combat_travel", "Normal travel cannot leave active combat.", 400)
        else:  # "çık git konaktan" is said to the other one: the player stays, and the line is words in the fight
            intent_type = "narrative"
            intent = {**intent, "intent": "narrative"}
    if (intent_type in {"attack", "combat"} and not _is_explicitly_negated_attack(player_input)
            and not combat_lifecycle.is_attack_decision(_session(), player_input)
            and not combat_lifecycle.quoted_or_conditional_not_attack(_session(), player_input)):
        # The model heard a fight the player's words do not start ("gerekirse kafa
        # kırarım"). Python owns combat, so the line stays what it is: words.
        intent_type = "narrative"
        intent = {**intent, "intent": "narrative"}
    before = _world_snapshot()
    result = {
        "action": intent_type,
        "success": True,
        "status": "resolved",
        "state_changes": [],
    }
    if intent_type in {"attack", "combat"} and combat_lifecycle.quoted_or_conditional_not_attack(_session(), player_input):
        result.update(
            action="narrative",
            success=None,
            status="not_executed",
            outcome="reported_not_attack",
            state_changes=[],
        )
        return result

    if _is_door_inspection_request(player_input) and _current_door() is None:
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
        and _is_explicitly_negated_attack(player_input)
    ):
        result.update(
            action="narrative",
            success=None,
            status="not_executed",
            outcome="negated_action",
            direct_response="Elin silahında kalıyor; kimseye vurmuyorsun.",
        )
        return result

    combat_was_active = bool(ensure_combat_state()["active"])
    if intent_type in {"attack", "combat"} and (_session().character["current_hp"] <= 0 or world_state["player_combat_status"] == "unconscious"):
        result.update(action="attack", success=False, outcome="player_unconscious",
                      direct_response="Bilincin kapalı; saldırı yapamazsın.")
        return _finish_combat_result(result, before)
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
        return _finish_combat_result(result, before)

    character_reply = known_character_answer(player_input)
    if character_reply:
        result.update({"action": "character_query", "direct_response": character_reply})
        return result

    # Handle identity/location/presence queries
    model_query_type = (
        intent.get("query_type") if _model_query_type_is_plausible(player_input) else None
    )
    query_type = _detect_query_type(player_input, npc_target) or model_query_type
    if query_type:
        query_response = _handle_query(player_input, query_type, npc_target)
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
        if ensure_combat_state()["active"]:
            raise combat_lifecycle.CombatRequestError("combat_travel", "Normal travel cannot leave active combat.", 400)
        reference = intent.get("target", {}).get("reference", "")
        pending = world_state.get("flags", {}).get("pending_destination")
        if (not reference or reference in ("orada", "oraya", "içeri")) and pending:
            reference = pending
        if not reference:
            result.update({"success": False, "status": "clarification", "direct_response": "Nereye gittiğini söylemedin."})
            return result
        previous = world_state.get("location")
        target_id = resolve_location_reference(reference)
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
                timed = timed_gameplay.start_travel(_session(), target_id)
                result.update(timed)
                return result
            changed = commit_location_change(target_id)
            if not changed and _venue_entry_door(world_state, previous, target_id):
                door = _venue_entry_door(world_state, previous, target_id)
                result.update({
                    "success": False,
                    "status": "blocked",
                    "direct_response": (
                        _locked_door_refusal(door)
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
            result.update(combat_ended=True, end_reason="location_changed", combat=_combat_snapshot())
            result["state_changes"] = _changed_state_fields(before)
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

    deterministic = deterministic_check_for_action(player_input)
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
            **SKILL_INTENT_TO_SKILL,
        }.get(intent_type)
        if intent_type == "explore" and explore_type in {"inspect", "search"}:
            inferred_skill = "Investigation"
        if inferred_skill and (
            not is_npc_dialogue_input(player_input)
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
        skill = _stealth_skill(player_input)  # D-094, D-171, D-176: hiding needs cover; hiding a thing is no hide
        if skill is None:
            world_state.setdefault("flags", {})["player_hidden"] = False
            result.update({
                "action": "world_interaction",
                "status": "resolved",
                "direct_response": "Açıkta, gün ışığında saklanacak bir yer yok; seni görebiliyorlar.",
                "state_changes": _changed_state_fields(before),
            })
            return result
    if skill in SKILLS:
        dc = DIFFICULTY_DC.get(difficulty, DIFFICULTY_DC["medium"])
        ability = "strength" if check_feature == 'primal_knowledge' else SKILLS[skill]
        trait_state = _species_trait_state()
        check_result = perform_skill_check(
            skill,
            dc,
            _session().character["modifiers"],
            _session().character["proficient_skills"],
            _session().character["proficiency_bonus"],
            expertise_skills=_session().character.get("expertise_skills", ()),
            **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {}),
            advantage=(
                ability == "strength"
                and trait_state.get("large_form_turns_remaining", 0) > 0
            ),
        )
        apply_check_outcome_to_world_state(player_input, check_result)
        haggle_note = money_owner.haggle(_session(), npc_target or _active_interlocutor(), check_result,
                                         negotiation=intent.get("price_negotiation"), player_input=player_input)
        if haggle_note:
            result["haggle_note"] = haggle_note
        outcome = _skill_result_category(check_result.get("result"))
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
            "state_changes": _changed_state_fields(before),
            "target_type": "door" if ("kapı" in player_input.casefold() or "kilit" in player_input.casefold()) else None,
        })
        if check_result["skill"] in {"Perception", "Investigation", "Survival"}:
            findings = _inspection_findings(player_input, outcome)
            if findings:
                # LR00-P2: the receipt names what was looked at and what was
                # (or was not) found; narration must agree with it.
                result["inspection"] = findings
        _print_skill_result(check_result, difficulty)
        return result

    if intent_type == "explore":
        # Looking at a named door, window or detail reveals what is plainly
        # visible without a roll (LR00-P2: no needless check for open facts).
        findings = _inspection_findings(player_input, "success", rolled=False)
        if findings:
            findings["auto_visible"] = True
            result["inspection"] = findings
        return result

    # Words said to a person claim nothing about the world: "ben buradayım" is no statement to correct.
    python_reply = None if intent_type == "dialogue" else resolve_python_world_action(player_input)
    if isinstance(python_reply, dict):
        result.update(python_reply)
        return result
    if python_reply:
        result.update({
            "action": "world_interaction",
            "status": "resolved",
            "direct_response": python_reply,
            "state_changes": _changed_state_fields(before),
        })
        return result

    inventory_reply = update_inventory_from_player(player_input)
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
            "state_changes": _changed_state_fields(before),
        })
        return result

    fixed_reply = known_player_action_narration(player_input)
    if fixed_reply:
        result.update({"action": "narrative", "direct_response": fixed_reply, "state_changes": []})
        return result

    if intent_type in {"attack", "combat"}:
        combat = ensure_combat_state()
        result["action"] = "attack"
        if combat["active"] and combat["current_actor_id"] != "player":
            result.update(
                success=False, status="out_of_turn", outcome="out_of_turn",
                current_actor_id=combat["current_actor_id"],
                turn_owner=combat["current_actor_id"],
                direct_response="Bu hamle için sıra sende değil.",
            )
            return _finish_combat_result(result, before)
        if combat["active"]:
            action_economy.action_slot(_session(), "player", "attack")

        import gear
        weapon_id, attack_choice = weapon_attack.natural_choice(_session(), player_input)
        # The model's word for the weapon (intent or front reading) goes only to the catalog: one not owned is a punch.
        asked = intent.get("weapon_word") or (getattr(_session(), "_front_strike", None) or {}).get("with")
        missing = gear.not_owned(world_state, requested_name=asked) if asked else None
        if missing:
            weapon_id = "unarmed"
        weapon_name, weapon_data = find_weapon_in_inventory(weapon_id)
        if weapon_id == "unarmed":
            weapon_name, weapon_data = "unarmed", None
        weapon_line = (refusals.text_for("weapon_not_owned", weapon=missing) if missing
                       else f"Çantandan çektiğin {weapon_name} ile vuruyorsun."
                       if isinstance(weapon_data, dict) and not gear.holds(world_state, weapon_data) else None)
        if not weapon_name:
            fallback_name = held_weapon.attack_weapon_name(world_state)
            if fallback_name:
                weapon_name, weapon_data = find_weapon_in_inventory(fallback_name)
        if not weapon_name:
            result.update(success=False, outcome="no_weapon",
                          direct_response="Envanterinde saldırmak için kullanabileceğin bir kılıç yok.")
            return _finish_combat_result(result, before)
        target_npc = resolve_combat_target(
            player_input,
            npc_target,
            target_id=target_id,
        )
        if not target_npc and target_id is None:
            targets = combat_lifecycle._attack_targets(_session(), player_input, None)
            if (combat_lifecycle._single_valid_target(_session(), targets)
                    and not _entity_reference_in_text(targets[0].get("name", ""), _normalize_turkish_typos(player_input))):
                target_npc = targets[0]  # one person here: the blow needs no name, but a guessed hidden name is asked about
        if target_npc == "ambiguous":
            candidate_names = [
                living_world.public_npc_name(npc)
                for npc in active_npcs()
                if isinstance(npc, dict)
            ]
            clarification = "Hangi hedefe saldırıyorsun?"
            if candidate_names:
                clarification += f" Yakında {living_world.public_scene_people(active_npcs()[:4])} var."
            result.update(success=False, status="clarification", outcome="ambiguous_target",
                          direct_response=clarification)
            return _finish_combat_result(result, before)
        if not target_npc:
            candidate_names = [
                living_world.public_npc_name(npc)
                for npc in active_npcs()
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
            return _finish_combat_result(result, before)
        if combat["active"] and target_npc["id"] not in combat["participants"]:
            result.update(success=False, outcome="target_mismatch",
                          target_id=target_npc["id"],
                          direct_response="Bu kişi mevcut çatışmanın katılımcısı değil.")
            return _finish_combat_result(result, before)
        ensure_npc_enemy_stats(target_npc)
        if (target_npc["combat_status"] not in {"active", "unconscious"}
            or (not combat["active"] and target_npc["current_hp"] <= 0)):
            result.update(success=False, outcome="invalid_target", target_id=target_npc["id"],
                          direct_response="Bu hedef savaşabilecek durumda değil.")
            return _finish_combat_result(result, before)
        melee_weapon = weapon_data if isinstance(weapon_data, dict) else {"range_ft": 5}
        sense_pair = monster_sense.observable_pair(_session())
        if sense_pair is not None and target_npc["id"] == monster_sense.NPC_ID:
            target_npc["distance_ft"] = sense_pair["distance_ft"]
        if monster_sense.blocks_melee(_session(), target_npc["id"], melee_weapon):
            pair = monster_sense.observable_pair(_session())
            result.update(
                success=False,
                outcome="out_of_reach",
                distance_ft=None if pair is None else pair["distance_ft"],
                direct_response="Hedef yakın dövüş menzilinin dışında.",
            )
            return _finish_combat_result(result, before)
        started = not combat["active"]
        enemy_actions = []
        if started:
            import bold_acts
            bold_acts.attacked(_session(), target_npc)
            start_result = start_combat(target_npc)
            result["combat_id"] = start_result["combat_id"]
            if start_result["current_actor_id"] != "player":
                # Won initiative: these come before the player's move (told first, not as counter-attacks).
                enemy_actions.extend({**action, "before_player": True}
                                     for action in _resolve_enemy_turns_until_player())
                if (
                    _session().character["current_hp"] <= 0
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
                    return _finish_combat_result(result, before)
        combat = ensure_combat_state()
        if combat["current_actor_id"] != "player":
            result.update(
                success=False,
                status="out_of_turn",
                outcome="out_of_turn",
                current_actor_id=combat["current_actor_id"],
                turn_owner=combat["current_actor_id"],
                direct_response="Bu hamle için sıra sende değil.",
            )
            return _finish_combat_result(result, before)
        combat["target_id"] = target_npc["id"]
        result = resolve_attack(player_input, weapon_name, weapon_data, target_npc,
                                attack_choice=attack_choice)
        if weapon_line:
            result["weapon_line"] = weapon_line
        if missing:
            refusals.note(_session(), "weapon_not_owned", weapon=missing)  # half done: the narrator hears it too
        result["combat_started"] = started
        if result.get("outcome") in ("invalid_target", "no_target"):
            result["combat_started"] = started
            if enemy_actions:
                result["enemy_actions"] = enemy_actions
                result["enemy_action"] = enemy_actions[0]
            return _finish_combat_result(result, before)

        _mark_combat_action_used("player")
        if action_economy.holding(_session()):
            _combat_end_if_decided()
            return _finish_combat_result(result, before)
        turn_effects = _finish_species_player_turn()
        if turn_effects:
            result["species_effects"] = [
                *result.get("species_effects", []),
                *turn_effects,
            ]
        combat = ensure_combat_state()
        if _combat_end_if_decided():
            combat = ensure_combat_state()
            result.update(
                combat_ended=True,
                end_reason=combat.get("end_reason"),
            )
        else:
            advanced, _, _ = advance_combat_turn()
            if advanced:
                enemy_actions.extend(_resolve_enemy_turns_until_player())
            combat = ensure_combat_state()
            if enemy_actions:
                result["enemy_actions"] = enemy_actions
                result["enemy_action"] = enemy_actions[0]
            if not combat["active"]:
                result.update(
                    combat_ended=True,
                    end_reason=combat.get("end_reason"),
                )
        combat = ensure_combat_state()
        if enemy_actions:
            result["enemy_actions"] = enemy_actions
            result["enemy_action"] = enemy_actions[0]
        result["current_actor_id"] = combat["current_actor_id"]
        result["turn_owner"] = combat["current_actor_id"]
        result["target_id"] = target_npc["id"]
        return _finish_combat_result(result, before)

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
        parsed = grounded_action.plan(_session(), player_input)
        if intent_type == "door" or any(step.get("part") or step.get("ambiguous") for step in parsed["steps"]):
            result.update({
                "action": intent_type,
                "success": False,
                "status": "unresolved",
                "state_changes": [],
                "direct_response": grounded_action.clarification_text(_session()),
            })
        else:
            result.update({"action": "narrative", "success": False, "status": "attempted", "state_changes": []})
    else:
        result.update({"action": "dialogue" if intent_type == "dialogue" else intent_type, "state_changes": []})
    return result
























from game_parts.places import _scene_feature_match, _scene_names, _variation_index, _look_opening, _scene_look_text, _look_scene_changed, _keep_people_in_look, _set_scene_active_npc, _reopen_public_doors, _a_walk, _walked_there, _may_propose_local_place, _accepted_local_place, _settle_local_place, _is_canonical_city_id








































def plan_living_world_turn(player_input, target_id=None, interaction_mode=None):
    """Resolve ordinary local actions and materialize before scoped lore lookup."""
    _reopen_public_doors()
    world_state = _session().world_state
    interaction_mode = _normalize_interaction_mode(interaction_mode)
    if (getattr(_session(), "_front_read", None) or {}).get("kind") in _PLANNER_STAYS_OUT:
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": _current_procedural_entity_ids()}
    anchored_structure = living_world.is_anchored_structure_inquiry(player_input)
    affirmative_anchored_inspection = (
        anchored_structure
        and living_world.affirmative_structure_inspection(
            player_input, interaction_mode
        )
    )
    # LR00 fix: a turn the grounded owner will take must not get this planner's
    # side effects first (a tavern created by a tavern search, a person made
    # the active interlocutor by an approach). The dry run writes nothing.
    import grounded_action
    if not affirmative_anchored_inspection and grounded_action.resolve_turn(
        _session(), player_input, interaction_mode=interaction_mode, target_id=target_id, dry_run=True,
    ):
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": _current_procedural_entity_ids()}
    exploratory_structure_question = living_world.is_exploratory_structure_question(
        player_input, interaction_mode
    )
    if anchored_structure and (
        interaction_mode in {"say", "ask_dm"}
        or (
            not exploratory_structure_question
            and not affirmative_anchored_inspection
        )
    ):
        return {
            "direct_result": {
                "action": "narrative",
                "status": "no_effect",
                "success": False,
                "state_changes": [],
                "direct_response": "Bu mesaj oyuncu tarafından açık bir inceleme olarak verilmedi; çevre ayrıntısı değiştirilmedi.",
            },
            "state_changes": [],
            "procedural_entity_ids_before": _current_procedural_entity_ids(),
        }
    if (not world_state.get("combat", {}).get("active")
            and interaction_adventure.hint(player_input) == "plan"):
        # Planning is not a scene visit, merchant discovery or clock consumer.
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": _current_procedural_entity_ids()}
    flags = world_state.setdefault("flags", {})
    turn_index = int(flags.get("turn_index", 0)) + 1
    before = _world_snapshot()
    procedural_before = {
        str(entity.get("id", key))
        for key, entity in world_state.get("locations", {}).items()
        if isinstance(entity, dict)
        and entity.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
    }
    procedural_before.update(
        npc["id"] for npc in world_state.get("npcs", [])
        if isinstance(npc, dict)
        and npc.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(npc.get("id"), str)
    )
    procedural_before.update(
        shop["id"] for shop in world_state.get("shops", [])
        if isinstance(shop, dict)
        and shop.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
        and isinstance(shop.get("id"), str)
    )

    current = world_state.get("location")
    ensure_campaign_clock()
    scene_intent = living_world.affirmative_scene_intent(player_input, interaction_mode)
    scene_exploration_question = exploratory_structure_question
    suppress_anchored_action = False
    if anchored_structure:
        if affirmative_anchored_inspection:
            scene_intent = ("inspect", player_input)
        elif not scene_exploration_question:
            scene_intent = None
            suppress_anchored_action = True
    # Keep action authority and target resolution in the same clause. A question
    # or declined verb elsewhere in the turn cannot authorize another actor.
    action_input = scene_intent[1] if scene_intent else player_input
    action = scene_intent[0] if scene_intent else living_world.classify_scene_action(player_input)
    if action == "sit" and (getattr(_session(), "_front_read", None) or {"kind": "sit"})["kind"] != "sit":
        action = None  # a line read as something else only has the word otur in it
    if scene_intent is None and action == "enter":
        action = None
    if interaction_mode == "say":
        action = None
    elif interaction_mode == "ask_dm" and action not in {"presence", "look"}:
        action = None
    if (action == "presence" and interaction_mode == "ask_dm"
            and (_front_say := talk_front.current(_session())) is not None
            and _front_say.get("asks") == "person" and talk_front.spoken_to(_front_say, active_npcs()) is not None):
        action = None  # D-326: "Çavuş, bu gece kim var?" is asked of the person the reading names, not a scene list
    if (
        action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not world_state.get("combat", {}).get("active")
        and _names_current_local_exit(action_input)
    ):
        action = "exit"
    inspect_action = bool(
        not suppress_anchored_action
        and
        interaction_mode not in {"say", "ask_dm"}
        and isinstance(action_input, str)
        and re.search(r"(?:incel\w*|gözden geçir\w*|inspect|examine)", action_input, re.IGNORECASE)
        and not re.search(r"(?:perception|investigation|algı kontrolü|araştırma kontrolü)", action_input, re.IGNORECASE)
    )
    if inspect_action:
        action = "inspect"
    elif suppress_anchored_action:
        action = None
    shop_request = (
        interaction_mode not in {"say", "ask_dm"}
        and target_id is None
        and _explicit_campaign_shop_request(player_input)
    )
    normalized_input = _normalize_turkish_typos(str(player_input))
    explicit_local_npc_reference = any(
        isinstance(npc, dict)
        and (
            (
                living_world.npc_name_known_to_player(npc)
                and _entity_reference_in_text(npc.get("name", ""), player_input)
            )
            or (
                living_world.npc_role_known_to_player(npc)
                and _entity_reference_in_text(npc.get("role", ""), player_input)
            )
        )
        for npc in active_npcs(current)
    )
    addressed_local_dialogue = bool(
        (
            interaction_mode == "say"
            and (target_id is not None or explicit_local_npc_reference)
        )
        or (
            (target_id is not None or explicit_local_npc_reference)
            and (
                is_npc_dialogue_input(player_input)
                or re.search(
                    r"\b(?:sor\w*|konus\w*|soyle\w*|de\w*|seslen\w*|hitap\s+et\w*)\b",
                    normalized_input,
                )
            )
        )
    )
    tavern_search = (
        interaction_mode not in {"say", "ask_dm"}
        and not shop_request
        and not addressed_local_dialogue
        and living_world.is_tavern_search(player_input)
        # LR00 fix: "başka bir han biliyor musun?" asks a person, it is not the
        # player searching the streets (the P6-style answer was always the
        # same inn).
        and not re.search(r"\b(?:biliyor|bilir|tanir|tanirsin|onerir|gosterir)\s*m[iu]s[iu]n\b", normalized_input)
        # "Bu çevrede bir han var mı?" with someone here is asked of them.
        and not (_reads_as_question(player_input) and active_npcs(current))
    )
    merchant_search = (
        interaction_mode not in {"say", "ask_dm"}
        and not shop_request
        and not addressed_local_dialogue
        and living_world.is_merchant_search(player_input)
    )
    scene_attention = bool(
        action
        or tavern_search
        or merchant_search
        or re.search(
            r"(?:barmen|muhafız|guard|bartender|kapıdaki|yolcu|ziyaretçi|"
            r"masa|bardak|ona|onunla|same table)",
            str(player_input),
            re.IGNORECASE,
        )
    )
    targetless_entry_reference = None
    entry_text = living_world._text_outside_quotes(action_input)
    if (
        action == "enter"
        and target_id is None
        and resolve_location_reference(entry_text) is None
        and not living_world.has_tavern_reference(entry_text)
    ):
        targetless_entry_reference = living_world.resolve_entry_target_reference(
            world_state,
            current_location_id=current,
            next_turn_index=turn_index,
        )
    combat = ensure_combat_state()
    if current in world_state.get("locations", {}) and (
        scheduled_events.pending_events(world_state)
        or
        campaign_time.names_duration(player_input)
        or timed_gameplay.explicit_wait_request(player_input)
        or timed_gameplay.clock.normalize(player_input).startswith(
            ("sabaha kadar", "yola devam", "yolculuga devam", "geri don")
        )
    ):
        # Do not perform an instant scene inspection before a bounded task.
        return {"direct_result": None, "state_changes": [],
                "procedural_entity_ids_before": procedural_before}
    if (
        scene_attention
        and action in {"look", "wait", "enter", "exit", "sit", "stand", "approach", "inspect"}
        and interaction_mode not in {"say", "ask_dm"}
        and scene_intent
        and not (merchant_search and any(
            isinstance(shop, dict) and shop.get("location") == current
            for shop in world_state.get("shops", [])
        ))
        and not combat.get("active")
        and current in world_state.get("locations", {})
        and not (
            targetless_entry_reference
            and _venue_entry_door(
                world_state, current, targetless_entry_reference["location_id"]
            )
        )
    ):
        scene = living_world.ensure_scene_record(world_state, current, turn_index)
        if scene.get("last_visit_turn") is None:
            living_world.record_scene_visit(world_state, current, turn_index)
        living_world.materialize_scene(
            world_state,
            current,
            turn_index,
            create_npc=create_npc_from_ai,
            create_feature=create_local_feature,
        )

    direct = None
    resolved_npc = None
    deferred_referent_id = None
    if (
        not combat.get("active")
        and living_world.is_anchored_structure_inquiry(action_input)
    ):
        direct = _observe_anchored_structure(action_input, interaction_mode)
    if not combat.get("active") and direct is None and tavern_search:
        root_location = current
        while _engine_location_parent(root_location):
            root_location = _engine_location_parent(root_location)
        tavern = _ensure_local_tavern(root_location)
        if tavern:
            grounded_action.note_last(world_state, tavern["id"])
            direct = {
                "action": "local_search",
                "status": "found",
                "success": True,
                "target_id": tavern["id"],
                "target_name": tavern["name"],
                "state_changes": [],
                "direct_response": (
                    f"Yakınlarda {tavern['name']} adlı küçük bir han buluyorsun. "
                    + _tavern_door_notice(tavern["id"])
                ),
            }

    if (
        not combat.get("active")
        and current in world_state.get("locations", {})
        and merchant_search
    ):
        merchant, shop = _ensure_local_merchant(current, create=False)
        if merchant and shop:
            _set_scene_active_npc(merchant, turn_index)
            direct = {
                "action": "local_search",
                "status": "found",
                "success": True,
                "target_id": merchant["id"],
                "shop_id": shop["id"],
                "state_changes": [],
                "direct_response": (
                    f"Yakında {living_world.public_shop_name(world_state, shop)} var. "
                    f"{living_world.public_npc_name(merchant)} başında duruyor."
                ),
            }
        elif direct is None:
            direct = {
                "action": "local_search",
                "status": "unavailable",
                "success": False,
                "state_changes": [],
                "direct_response": "Yakınlarda tüccara benzer kimseyi görmüyorsun.",
            }

    if not combat.get("active") and action == "enter":
        text = str(entry_text)
        candidate = None
        explicit_tavern_target = living_world.has_tavern_reference(text)
        named_candidate = resolve_location_reference(text)
        named_record = world_state.get("locations", {}).get(named_candidate, {})
        if target_id is not None:
            candidate = target_id
        elif (isinstance(named_record, dict)
              and named_record.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"):
            # An existing canonical destination wins over a generic venue noun.
            # Never substitute/create another inn for a named shop or locked door.
            candidate = named_candidate
        elif explicit_tavern_target:
            root_location = current
            while _engine_location_parent(root_location):
                root_location = _engine_location_parent(root_location)
            existing_tavern = _ensure_local_tavern(
                root_location, open_for_entry=True
            )
            candidate = existing_tavern.get("id") if existing_tavern else None
        if candidate is None:
            candidate = named_candidate
        if (
            candidate is None
            and target_id is None
            and not explicit_tavern_target
            and targetless_entry_reference
        ):
            candidate = targetless_entry_reference["location_id"]
        candidate_record = world_state.get("locations", {}).get(candidate, {})
        if (
            candidate
            and candidate != current
            and isinstance(candidate_record, dict)
            and candidate_record.get("reality_layer") == "PROCEDURAL_LOCAL_FICTION"
            and candidate_record.get("parent_location_id") == current
        ):
            entry = grounded_action.enter_existing_place(_session(), candidate, player_input)
            direct = {
                "action": "enter",
                "status": entry["status"],
                "success": entry["status"] == "completed",
                "target_id": candidate,
                "state_changes": [],
                "direct_response": entry["text"],
                **({"arrival_narration": entry["arrival_narration"]} if entry.get("arrival_narration") else {}),
            }
        elif (
            candidate == current
            and isinstance(candidate_record, dict)
            and direct is None
        ):
            direct = {
                "action": "enter",
                "status": "already_inside",
                "success": True,
                "target_id": candidate,
                "state_changes": [],
                "direct_response": (
                    "Zaten buradasın. "
                    + _scene_presence_text(candidate)
                ),
            }
        elif (
            direct is None
            and isinstance(world_state.get("locations", {}).get(current), dict)
            and world_state["locations"][current].get("scene_kind") == "tavern"
        ):
            current_record = world_state["locations"][current]
            direct = {
                "action": "enter",
                "status": "already_inside",
                "success": True,
                "target_id": current,
                "state_changes": [],
                "direct_response": (
                    "Zaten içeridesin. "
                    + _scene_presence_text(current)
                ),
            }
        elif direct is None and explicit_tavern_target:
            direct = {
                "action": "enter",
                "status": "unresolved",
                "success": False,
                "state_changes": [],
                "direct_response": "Girebileceğin belirgin bir yer göremiyorsun.",
            }

    if not combat.get("active") and action == "exit":
        current_record = world_state.get("locations", {}).get(current, {})
        parent = (
            current_record.get("exit_location_id")
            or current_record.get("parent_location_id")
            if isinstance(current_record, dict)
            else None
        )
        if isinstance(parent, str) and parent in world_state.get("locations", {}):
            commit_location_change(parent, turn_index=turn_index)
            direct = {
                "action": "exit",
                "status": "completed",
                "success": True,
                "target_id": parent,
                "state_changes": [],
                "direct_response": (
                    f"{location_display_name(parent)} tarafına çıkıyorsun. "
                    + _scene_presence_text(parent)
                ),
            }
        elif direct is None:
            direct = {
                "action": "exit",
                "status": "unresolved",
                "success": False,
                "state_changes": [],
                "direct_response": "Zaten dışarıdasın; sokak önünde uzanıyor.",
            }

    if not combat.get("active") and not direct:
        ref_resolution = living_world.resolve_scene_referent(
            world_state, str(action_input), turn_index
        )
        referent = ref_resolution.get("referent")
        if ref_resolution["status"] == "expired" and _active_interlocutor() is None:
            direct = {
                "action": "referent",
                "status": "expired",
                "success": False,
                "state_changes": [],
                "direct_response": (
                    "Az önce gördüğün kişi ortalıkta yok artık."
                ),
            }
        elif ref_resolution["status"] == "ambiguous":
            if _has_explicit_attack_verb(action_input):
                direct = {
                    "action": "attack",
                    "status": "clarification",
                    "success": False,
                    "outcome": "ambiguous_target",
                    "state_changes": [],
                    "direct_response": "Birden fazla kişi bu tarife uyuyor. Kime saldırmak istiyorsun?",
                }
            else:
                direct = {
                    "action": "referent",
                    "status": "clarification",
                    "success": False,
                    "state_changes": [],
                    "direct_response": "Birden fazla kişi bu tarife uyuyor. Hangisini kastettiğini biraz daha tarif eder misin?",
                }
        elif ref_resolution["status"] in ("found", "promoted") and referent and not any(
            _words_fit_person(npc, _normalize_turkish_typos(str(action_input))) for npc in active_npcs()
        ):
            # "Tezgâhtaki adam" is the barkeep who stands there, not a passer-by of the moment.
            if _is_scene_referent_activity_observation(action_input):
                description = referent.get("description")
                direct = {
                    "action": "explore",
                    "explore_type": "observe",
                    "status": "observed",
                    "success": True,
                    "target_id": referent.get("id"),
                    "state_changes": [],
                    "direct_response": (
                        description.strip()
                        if isinstance(description, str) and description.strip()
                        else "Belirgin bir değişiklik fark etmiyorsun."
                    ),
                }
            elif scene_intent and (
                action == "approach" or _has_explicit_attack_verb(action_input)
                or re.search(r"\b(?:konus\w*|seslen\w*|selam\w*|sor\w*|talk|speak|greet)\b", _normalize_turkish_typos(str(action_input)))
            ):
                if (
                    ref_resolution["status"] == "found"
                    and action != "approach"
                    and not _has_explicit_attack_verb(action_input)
                    and active_npcs()
                ):
                    # Greeting with someone visible here: the model's checked pick of
                    # that person wins over a word of the happening; the turn creates
                    # the happening's person only if the model names nobody.
                    deferred_referent_id = referent.get("id")
                else:
                    resolved_npc = _promote_scene_referent(referent, current)
                if resolved_npc:
                    _set_scene_active_npc(resolved_npc, turn_index)
                elif action == "approach" and not is_npc_dialogue_input(action_input):
                    direct = {
                        "action": "approach",
                        "status": "unavailable",
                        "success": False,
                        "state_changes": [],
                        "direct_response": "Kalabalıkta o kişiye yaklaşacak yer bulamıyorsun.",
                    }

    world_subject_question = (
        True if interaction_mode == "ask_dm"
        else False if interaction_mode == "say"
        else local_dialogue.is_world_subject_question(action_input)
    )
    if (
        not combat.get("active")
        and not direct
        and action != "presence"
        and action != "look"
        and not world_subject_question
        and not scene_exploration_question
        # A character-sheet question has no NPC subject to disambiguate.
        and not known_character_answer(action_input)
    ):
        if target_id is not None:
            resolved_npc = next(
                (
                    npc for npc in (_conversation_npcs() if interaction_mode == "say" else active_npcs())
                    if isinstance(npc, dict) and npc.get("id") == target_id
                ),
                None,
            )
        if resolved_npc is None and interaction_mode == "say" and target_id is not None:
            direct = {
                "action": "dialogue", "status": "clarification", "success": False,
                "state_changes": [],
                "direct_response": "Kiminle konu\u015fmak istiyorsun?",
            }
        # A deferred happening's person is decided by the turn's own resolver and the model.
        if resolved_npc is None and not direct and deferred_referent_id is None:
            npc_resolution = resolve_npc_reference(
                action_input, **({"force_dialogue": True} if interaction_mode == "say" else {})
            )
            if npc_resolution.get("status") == "ambiguous":
                if (
                    interaction_mode not in {"say", "ask_dm"}
                    and _has_explicit_attack_verb(action_input)
                ):
                    direct = {
                        "action": "attack",
                        "status": "clarification",
                        "success": False,
                        "outcome": "ambiguous_target",
                        "state_changes": [],
                        "direct_response": npc_ambiguity_response(npc_resolution),
                    }
                else:
                    npc_resolution = _settle_address(npc_resolution, action_input)
            if npc_resolution.get("status") == "found":
                resolved_npc = npc_resolution.get("npc")
            elif (
                action == "approach"
                and _GENERIC_PERSON.search(_normalize_turkish_typos(str(action_input)))
            ):
                # "Yakınımdaki birine yaklaşıyorum": any person will do, so pick one.
                resolved_npc = most_plausible_addressee(active_npcs(), action_input)
            elif action == "approach" and npc_resolution.get("absent"):
                direct = {
                    "action": "approach",
                    "status": "unavailable",
                    "success": False,
                    "state_changes": [],
                    "direct_response": _absent_person_text(npc_resolution["absent"]),
                }

    if not combat.get("active") and not direct:
        if action == "presence" and current in world_state.get("locations", {}):
            # "Who is here?" can be the first thing asked in a scene nobody has looked at yet.
            living_world.materialize_scene(
                world_state,
                current,
                turn_index,
                create_npc=create_npc_from_ai,
                create_feature=create_local_feature,
            )
            direct = {
                "action": "query",
                "query_type": "presence",
                "status": "answered_from_current_scene",
                "success": True,
                "state_changes": [],
                "direct_response": _scene_presence_text(current),
            }
        elif action == "look":
            look_location = (
                current
                if current in world_state.get("locations", {})
                else (resolve_location_reference(current) if isinstance(current, str) else None)
            )
            if look_location and look_location in world_state.get("locations", {}):
                direct = {
                    "action": "explore",
                    "status": "observed",
                    "success": True,
                    "state_changes": [],
                    "direct_response": (
                        living_world.visible_contents_text(world_state)
                        if living_world.is_visible_contents_query(player_input)
                        else _scene_look_text(look_location)
                    ),
                    **({"explore_type": "observe"}
                       if living_world.is_visible_contents_query(player_input) else {}),
                }
        elif action == "approach":
            import grounded_action
            speech_part = "?" in str(action_input) or grounded_action.spoken_request(
                action_input
            ) or re.search(
                r"\b(?:sor\w*|selam\w*|anlat\w*|soyle\w*|danis\w*)\b",
                _normalize_turkish_typos(str(action_input)),
            ) or re.search(
                # "Birine yaklaşıyorum. Selamlar, ismin nedir?": the rest speaks to that person.
                r"\b(?:ismin|adin|isminiz|adiniz|kimsin|kimsiniz|nasilsin|nerelisin|misin|musun)\b",
                _normalize_turkish_typos(str(player_input)),
            )
            if resolved_npc and speech_part:
                # "Marek'e yaklaşıp arşivi soruyorum": walking up is the first
                # half of one compound move; the question must not be dropped.
                _set_scene_active_npc(resolved_npc, turn_index)
                living_world.set_player_position(
                    world_state, current, "standing", resolved_npc["id"]
                )
                resolved_npc["distance_ft"] = 5
                direct = None
            elif resolved_npc:
                _set_scene_active_npc(resolved_npc, turn_index)
                # Approaching a visible NPC is a Python-owned local positioning fact.
                # Record conversation/melee proximity explicitly so a later hostile
                # decision can use the existing combat owner without guessing range.
                living_world.set_player_position(
                    world_state, current, "standing", resolved_npc["id"]
                )
                resolved_npc["distance_ft"] = 5
                direct = {
                    "action": "approach",
                    "status": "completed",
                    "success": True,
                    "target_id": resolved_npc["id"],
                    "target_name": living_world.public_npc_name(resolved_npc),
                    "state_changes": [],
                    "direct_response": (
                        f"{living_world.public_npc_name(resolved_npc)} seni fark edip "
                        "sana dönüyor."
                    ),
                }
            else:
                direct = {
                    "action": "approach",
                    "status": "clarification",
                    "success": False,
                    "state_changes": [],
                    # LR00 fix: a place, door or detail is as valid a target
                    # as a person; name all of them, not people only.
                    "direct_response": __import__("grounded_action").clarification_text(_session()),
                }
        elif action == "sit":
            direct = resolve_scene_seating(action_input)
        elif action == "stand":
            living_world.set_player_position(world_state, current, "standing")
            direct = {
                "action": "stand",
                "status": "completed",
                "success": True,
                "state_changes": [],
                "direct_response": "Ayağa kalkıyorsun.",
            }
        elif action == "wait":
            beat = living_world.note_wait(world_state, current, turn_index)
            direct = {
                "action": "wait",
                "status": "completed",
                "success": True,
                "state_changes": [],
                "direct_response": beat,
            }
        elif action == "inspect":
            selected_feature = next(
                (
                    feature for feature in world_state.get("features", [])
                    if isinstance(feature, dict)
                    and feature.get("id") == target_id
                    and feature.get("location") == current
                ),
                None,
            )
            features = (
                [selected_feature]
                if selected_feature is not None
                else _scene_feature_match(action_input, current)
            )
            if len(features) == 1:
                direct = {
                    "action": "inspect",
                    "status": "observed",
                    "success": True,
                    "target_id": features[0].get("id"),
                    "state_changes": [],
                    "direct_response": (
                        f"{features[0].get('name', 'Bu ayrıntı')}: "
                        f"{features[0].get('description', 'belirgin bir değişiklik yok.')}"
                    ),
                }
            elif len(features) > 1:
                direct = {
                    "action": "inspect",
                    "status": "clarification",
                    "success": False,
                    "state_changes": [],
                    "direct_response": "Hangi ayrıntıyı incelemek istediğini belirtir misin?",
                }

    current = world_state.get("location")
    lore_location_id = living_world.location_anchor_id(world_state, current)
    lore_state = getattr(_session(), "lore_authority_context", None)
    if lore_location_id is None and isinstance(lore_state, dict):
        lore_location_id = lore_state.get("current_location_id")
    changes = _changed_state_fields(before)
    if direct:
        direct["state_changes"] = list(dict.fromkeys(
            direct.get("state_changes", []) + changes
        ))
    return {
        "action": action,
        "direct_result": direct,
        "npc_target_id": resolved_npc.get("id") if isinstance(resolved_npc, dict) else None,
        "deferred_referent_id": deferred_referent_id if resolved_npc is None and not direct else None,
        "lore_location_id": lore_location_id,
        "state_changes": changes,
        "procedural_entity_ids_before": sorted(procedural_before),
    }


class TurnResolved(Exception):
    def __init__(self, raw_result, resolved_turn):
        self.raw_result = raw_result
        self.resolved_turn = resolved_turn


def _hideout_check(skill, dc):
    """Dice stay with the existing check owner. The hideout only hears success."""
    character = _session().character
    result = perform_skill_check(
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
    session = _session()
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
    check = deterministic_check_for_action(prepared)
    if isinstance(check, dict) and check.get("skill") == "Investigation":
        return _adventure_check_reply(session, "Investigation")
    folded = player_input.casefold()
    if not re.search(r"\b(?:gidiyorum|git|donuyorum|dönüyorum)\b", folded):
        return None
    for word in ("orman", "taverna", "kale", "neverwinter"):
        if word in folded:
            destination = resolve_location_reference(word)
            if (
                isinstance(destination, str)
                and destination != world.get("location")
                and destination in world.get("locations", {})
            ):
                return _adventure_travel_reply(session, destination)
    return None


def _adventure_check_reply(session, skill):
    before = copy.deepcopy(session.world_state)
    passed = _hideout_check(skill, DIFFICULTY_DC["medium"])
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

    session = _session()
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
        world, first_step, door=_current_door(),
        reference=_entity_reference_in_text, turn=int(flags.get("turn_index", 0)) + 1,
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

    session = _session()
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
    if not commit_location_change(record["id"], flags["turn_index"]):
        world.clear()
        world.update(before)
        return None
    if "campaign_time" in world:  # the walk takes what a walk takes, and the town moves on meanwhile
        import grounded_action
        advance_campaign_time(grounded_action.LOCAL_WALK_SECONDS, "exploration")
    npc, feature = local_places.furnish(
        world, record, create_npc=create_npc_from_ai, create_feature=create_local_feature,
    )
    import arrival_narration  # here, not at the top: arrival_narration imports game
    narration, told = arrival_narration.arrive(sys.modules[__name__], world, record, npc, feature, first_visit=created,
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
    session = _session()
    try:
        return _run_player_turn_owned(player_input, messages, target_id, scene_plan, action_id, session_id,
                                      combat_action, interaction_mode, check_feature, check_evidence)
    finally:
        _clear_turn_transients(session)


def _run_player_turn_owned(
    player_input, messages, target_id, scene_plan, action_id, session_id, combat_action, interaction_mode,
    check_feature, check_evidence,
):
    if check_feature is None:
        import front_proposal
        front_on = front_proposal.enabled()
        result = None
        session = _session()
        if front_on and not getattr(session, "_front_ahead", False):
            front_proposal.begin(session, typed=(combat_action is not None or target_id is not None
                                                 or interaction_mode in {"say", "ask_dm"}))
        try:
            result = _run_player_turn(player_input, messages, target_id, scene_plan, action_id,
                                      session_id, combat_action, interaction_mode)
            return result
        finally:
            if front_on:
                front_proposal.end(session)
                front_proposal.log_turn(session, result)
    money_owner.forget_turn(_session())  # no reading begins a check turn; an earlier line's coin is not this one's
    _session()._front_talk = None  # ... nor an earlier line's talk reading (read-ahead may have set one)
    if type(check_feature) is not str or check_feature not in CHECK_FEATURES:
        raise combat_lifecycle.CombatRequestError('invalid_check_feature', 'Unknown check feature.', 400)
    if check_evidence is not None and type(check_evidence) is not list:
        raise ValueError('Check evidence must be a caller-owned list.')
    primal_knowledge_check_admission(player_input, interaction_mode=interaction_mode,
                                     combat_action=combat_action, scene_plan=scene_plan, target_id=target_id,
                                     check_feature=check_feature)
    snapshot = _session()._capture_runtime_snapshot()
    evidence = []
    try:
        result = _run_player_turn(player_input, messages, target_id, scene_plan, action_id,
                                  session_id, combat_action, interaction_mode,
                                  check_feature=check_feature, check_evidence=evidence)
        if result.get('action_result', {}).get('action') != 'skill_check' or len(evidence) != 1:
            raise _immediate_check_refusal(check_feature, 'No supported immediate check was resolved.')
    except IntentInfrastructureError as error:
        # Preserve the API's retryable 503 path, not a permanent feature refusal.
        _session()._restore_runtime_snapshot(snapshot)
        return _intent_infrastructure_result(error)
    except Exception:
        _session()._restore_runtime_snapshot(snapshot)
        raise
    if check_evidence is not None:
        check_evidence.extend(evidence)
    return result




def _tell_the_coin(result):
    """After the reply, the money owner opens the one card this turn's decision names; coin is never a silent gift.

    It writes no coin. The coin in hand and the counter's hold on it end here, whatever the owner did.
    """
    session = _session()
    try:
        pending = getattr(session, "_spoken_coin_proposal", None)
        if pending is not None:
            person = next((n for n in active_npcs() if n.get("id") == pending.recipient_id), None)
            if person is not None:
                _record_spoken_coin_response(person, None)  # a deterministic reply supplies no semantic acceptance
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
    session = _session()
    owns_key = not getattr(session, "_economic_turn_key", None)
    if owns_key:
        session._economic_turn_key = action_id or f"turn:{secrets.token_hex(8)}"
    try:
        return _run_player_turn_keyed(player_input, messages, target_id, scene_plan, action_id, session_id,
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
    _session()._adventure_player_text = player_input if isinstance(player_input, str) else ""
    _session()._asks_for = None  # what the person was asked for in this turn's conversation, set by the speech answer
    import fallen
    fallen.wake(_session())
    before = copy.deepcopy(_session().world_state)
    before_hp = _session().character.get("current_hp")
    messages_before = len(_session().messages)
    try:
        runtime_snapshot = _session()._capture_runtime_snapshot()
    except AttributeError:
        # A test die without getstate cannot be snapshotted; the API restores its own.
        runtime_snapshot = None
    turn_index_before = _session().world_state.get("flags", {}).get("turn_index", 0)
    place_before = _session().world_state.get("location")
    try:
        result = _dispatch_player_turn(
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
            _sleep_after_walk(result, player_input, place_before, scene_plan)
            result = _person_answers_stock(result, player_input, messages, target_id, interaction_mode,
                                           action_id, session_id, runtime_snapshot)
            result = _the_rest_of_the_line(result, messages, action_id, session_id, place_before)
            _tell_the_coin(result)
            bold_acts.answer_to_killing(_session(), result)
            bold_acts.answer_to_known_doer(_session(), result)
            import world_reactions
            world_reactions.answer(_session(), result)
            import fallen
            fallen.wake(_session())  # the next look sees who got up while this turn's time passed
    except IntentInfrastructureError as error:
        if check_feature is not None:
            # The outer opt-in owner restores its earlier snapshot and formats
            # this typed failure. No arbitrary status dictionary bypasses proof.
            raise
        # The classifier could not run: nothing was decided, so nothing is kept.
        if runtime_snapshot is not None:
            _session()._restore_runtime_snapshot(runtime_snapshot)
        else:
            _session().world_state.setdefault("flags", {})["turn_index"] = turn_index_before
        return _intent_infrastructure_result(error)
    import dialogue_runtime
    dialogue_runtime.observe_turn(_session(), before, before_hp, result, player_input, action_id)
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
        _session().world_state,
        action_result=action_result,
        source_action_id=source_action_id,
        source_turn_index=_session().world_state.get("flags", {}).get("turn_index", 0),
        source_location_id=before.get("location"),
    )
    if (
        isinstance(action_result, dict)
        and action_result.get("action") in {"action_economy", "attack", "death_save"}
        and not action_result.get("quest_outcomes")
    ):
        transitions = _session().evaluate_quest_events(before, action_result)
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
            _session(), result.get("action_result", {}), before, player_input
        )
    import xp
    if xp.job_grants_due(_session().world_state):
        # A job finished in this turn (by any route, direct ones included) is paid here, before the turn is answered.
        # A grant that cannot be recorded is forfeited (B1): the job keeps its close and its wage, and its thread is
        # marked so no later turn owes it again.
        _session()._forfeit_unrecordable_xp(xp.award_finished_jobs, _session().world_state, _session().character)
        xp.forfeit_jobs(_session().world_state, xp.job_grants_due(_session().world_state))
    if isinstance(result, dict) and isinstance(action_result, dict):
        _session()._publish_level_up(action_result)
        local_dialogue.remember_native_reply(
            _session().world_state, action_result, player_input, result.get("narration")
        )
        # D-061: a forfeited award's line ("<X> XP kaydedilemedi: <neden>.") goes the same way as the award line.
        lines = [xp.award_line(action_result["level_up"])] if isinstance(action_result.get("level_up"), dict) else []
        lines += _session()._take_xp_unrecorded()
        if lines:
            # After every narration check (and after a person's reply is remembered): Python's own line from the
            # award's facts, in the reply and in this turn's assistant message (no model call, no number from the model).
            line = " ".join(lines)
            result["narration"] = f"{result.get('narration') or ''} {line}".strip()
            for row in reversed(_session().messages[messages_before:]):
                if isinstance(row, dict) and row.get("role") == "assistant":
                    row["content"] = f"{row.get('content') or ''} {line}".strip()
                    break
    return result








def _the_rest_of_the_line(result, messages, action_id, session_id, place_before):
    """"Bira ver, soylu arayan var mı": the owner did the first part, so the person gets the second, as a paid word does.

    "Hana gidiyorum, odayı soruyorum": a walk that got there takes the rest along, read as a line of its own at the
    place walked to; a walk that stopped short (a locked door) drops it."""
    session = _session()
    rest = getattr(session, "_front_rest", "")
    action_result = result.get("action_result") if isinstance(result, dict) else None
    from api import ollama_adapter
    read = getattr(session, "_front_read", None) or {}
    walk = isinstance(action_result, dict) and _a_walk(read, action_result)
    walked = walk and _walked_there(read, action_result, place_before)
    if (not rest or not isinstance(action_result, dict) or session.world_state.get("combat", {}).get("active")
            or (walk and not walked)  # stopped short: nobody the rest was for is here
            or (session.world_state.get("location") != place_before and not walked)  # the one asked is left behind
            or (walked and (getattr(session, "_front_coin", 0) or getattr(session, "_coin_paid", None)))  # coin read once
            or action_result.get("action") in {"dialogue", "query", "lodging", "shop_inquiry"}  # a room taken has answered its own price
            or action_result.get("status") in {"experimental_attributed_speech", "clarification"}
            or not ollama_adapter.model_calls_left()):
        return result
    own_act = walked or read.get("kind") in _OWN_ACTS
    hearer = None
    if own_act:
        named = _addressed_in(rest, or_the_talk=False)
        if isinstance(named, dict) and named.get("id") in {npc.get("id") for npc in _conversation_npcs()}:
            # "yemeği yiyorum, Marek'e şehri soruyorum": the second part names someone here, so it is said to them
            # (the say path keeps the turn's second call for their answer), not read again.
            own_act, hearer = False, named
    if not own_act and hearer is None:
        here = _conversation_npcs()
        hearer = next((npc for npc in here if npc.get("id") == read.get("id")), None) or _active_interlocutor() or (
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
        said = _dispatch_player_turn(rest, messages, None, None, action_id, session_id, None, None)
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
            said = _dispatch_player_turn(rest, messages, hearer["id"], None, action_id, session_id, None, "say")
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
    if hearer is not None and _is_stock(line):
        line = _person_fallback(session.world_state, hearer, rest)
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




def _person_answers_stock(result, player_input, messages, target_id, interaction_mode, action_id, session_id, snapshot):
    """The one door every owner's text leaves by: a stock line never answers a person, and no person says one.

    A stock line changed nothing, so the line can simply go to the person if the turn still has a model call.
    With none left the person answers from what Python has for them.
    """
    session = _session()
    text = result.get("narration") if isinstance(result, dict) else None
    if (not isinstance(text, str) or not _only_stock(text)
            or session.world_state.get("combat", {}).get("active")):
        return result
    hearer = _stock_hearer(result, player_input, target_id)
    if hearer is None:
        return result
    action_result = result.get("action_result") if isinstance(result.get("action_result"), dict) else {}
    from api import ollama_adapter
    if (snapshot is not None and interaction_mode != "say" and ollama_adapter.model_calls_left()
            and not action_result.get("state_changes")):
        person = hearer["id"]
        session._restore_runtime_snapshot(snapshot)
        session._thread_gate_done = True
        try:
            result = _dispatch_player_turn(player_input, messages, person, None, action_id, session_id, None, "say")
        finally:
            session._thread_gate_done = False
        text = result.get("narration")
        if not _is_stock(text):
            return result
        hearer = next((npc for npc in _conversation_npcs() if npc.get("id") == person), hearer)
    line = _person_fallback(session.world_state, hearer, player_input)
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
    session = _session()
    state = ensure_death_state()
    roll = roll_d20()
    # masa kuralı (SRD'de yok): Kadir kararı 2 — the 5% answer (only a natural 20) is a table rule, not a published one
    answered = roll == 20
    state["last_call"] = {"roll": roll, "answered": answered}
    if not answered:
        return "Sesin karanlığa karışıyor; cevap gelmiyor. Öldün. " + _death_closing(), "player_dead"
    session.world_state["player_combat_status"] = "unconscious"
    state.update(dead=False, terminal=False, successes=0, failures=0, prone=True, last_resolution=None)
    heal_player(1)
    return ("Sesin karanlıkta yankılanıyor ve bir şey karşılık veriyor. Ciğerlerine yakıcı bir hava doluyor; "
            "gözlerini açıyorsun. Yerdesin ama nefes alıyorsun."), "player_rescued"


def combat_refusal_turn(error):
    """A plain line that a fight will not allow is answered in the fight, never in English."""
    narration = refusals.text_for(error.code)
    refusals.note(_session(), error.code)
    return {
        "messages": _session().messages,
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
    r = combat_lifecycle.approach(_session(), target_id, named=True)
    if r.status == "not_a_participant":
        return None
    _session()._walk_off = None  # the walk the words said is this one: toward someone in the fight
    if r.status == "which":
        narration = refusals.text_for("which_enemy", names=combat_lifecycle.asked_names(r.names))
        refusals.note(_session(), "which_enemy", names=combat_lifecycle.asked_names(r.names))
    elif r.status == "short":
        narration = refusals.text_for("approach_short", left=r.left_ft)
        refusals.note(_session(), "approach_short", left=r.left_ft)
    else:
        narration = f"{r.moved_ft} fit ilerlersin; {r.names[0]} artık yanında." if r.moved_ft else f"{r.names[0]} zaten yanında."
    return {
        "action": "combat_move", "status": {"which": "clarification", "short": "partial"}.get(r.status, "resolved"),
        "success": r.status == "moved", "target_id": r.target_id, "moved_ft": r.moved_ft,
        "state_changes": ["combat"] if r.moved_ft else [], "direct_response": narration,
    }


def player_cannot_act_turn():
    """A dead player's line is answered in the world, never as a server error."""
    state = ensure_death_state()
    if state["dead"] or _session().world_state.get("player_combat_status") == "dead":
        if state["terminal"] or state.get("last_call") is not None:
            narration, status = f"Kıpırtısız yatıyorsun; öldün. {_death_closing()}", "player_dead"
        else:
            narration, status = _last_call()
    else:
        narration = ("Bilincin kapalı, kanın durdu; ne konuşabiliyor ne kıpırdayabiliyorsun. "
                     "Dünya sensiz akıyor; beklersen gözlerini açarsın.")
        status = "player_unconscious"
    return {
        "messages": _session().messages,
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
    return "?" in player_input or is_npc_dialogue_input(player_input) or "," in player_input[:40]






def _addressed_in(player_input, *, or_the_talk=True):
    """Who the line names, or else (or_the_talk) who the talk is with. Finding them here starts no conversation."""
    world_state = _session().world_state
    world_state.setdefault("flags", {})
    saved = talk_mode.snapshot(world_state)
    found = resolve_npc_reference(player_input, force_dialogue=True, allow_active_fallback=False)
    talk_mode.restore(world_state, saved)
    return found.get("npc") or (_active_interlocutor() if or_the_talk else None)


def _front_recovery(player_input, listed):
    """D-240: the front reading came back unusable. Two lines need no model: a plain yes to the one offer that is open
    (the offer gate then checks it again against the line), and a plain walk out of town. Both go the way a read line
    would; anything less clear stays with the old chain."""
    import front_proposal
    import grounded_action
    import world_threads
    session = _session()
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
        person = next((npc for npc in active_npcs() if npc.get("id") == offer["person_id"]), None)
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
    session = _session()
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
    import shop_trade
    typed_economic = interaction_mode == "say" and target_id is not None
    said_coin = (typed_economic and combat_action is None
                 and check_feature is None and not fighting and isinstance(player_input, str)
                 and front_proposal.names_coin(player_input))
    served = (typed_economic and combat_action is None and check_feature is None and not fighting
              and shop_trade.is_vendor(world, next((n for n in active_npcs() if n.get("id") == target_id), None)))
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
        front_proposal.note(session, "skipped:empty")
        return None
    if adventure_play.inside_hideout(world):
        front_proposal.note(session, "skipped:hideout")  # the town's lists are not what is around the player here
        return None
    from api.model_phase import front_call
    try:
        listed = front_proposal.listing(session)
    except Exception:
        front_proposal.note(session, "fallback:no_list")  # the old chain still has its own classifier call
        if reads:  # ... except for a conversation line: the speech call answers, so no classifier call is spent
            session._front_reply = {"intent": "unknown", "classifier_unusable": True}
            session._front_reply_called = False  # G10: held, but no provider was asked for it
        return None
    hint = interaction_adventure.hint(player_input, True)
    addressed = None
    if hint and typed_economic:  # in say mode the line is for the person chosen, whoever its words name
        addressed = next((npc for npc in active_npcs() if npc.get("id") == target_id), None)
    elif hint:
        addressed = _addressed_in(player_input)
    with front_call():  # one reading answers for the whole turn, so it carries whatever proposal the line may need
        reply = parse_player_intent(
            player_input, front_list=listed, recent_scene_narration=_recent_player_visible_narration(),
            interaction_context=interaction_adventure.context(world, addressed, player_input) if hint else None,
            operation_hint=hint, require_conversation=hint == "information" and addressed is not None,
            allow_local_person_proposal=should_generate_npcs(player_input),
            allow_scene_detail_proposals=_scene_detail_proposals_allowed(player_input, world, interaction_mode))
    held = {key: value for key, value in reply.items() if key != "front"}
    session._front_reply = held
    session._front_reply_called = True  # G10: this reply is the turn's one classifier call, however often it is reused
    if "front" not in reply:
        answered = len(reply) > 1  # a dead provider leaves only the bare unknown intent
        label = ("fallback:unusable" if reply.get("classifier_unusable")
                 else "fallback:no_front" if answered else "fallback:failed")
        recovered = (None if fighting or typed_economic or reads or label == "fallback:no_front"
                     else _front_recovery(player_input, listed))
        if recovered is not None:
            front_proposal.note(session, f"{label}:{recovered['kind']}", reached=answered)
            recovered["recovered_from"] = label  # the gate may still overrule: the label then goes back
            return recovered
        front_proposal.note(session, label, reached=answered)
        _coin_without_a_reading(player_input, target_id, listed)
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
        _hand_over_coin(route, listed, raw_front)
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
                _hand_over_coin(route, listed, raw_front)
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
    if threatened and not fighting and not _heavy_allowed("threat", player_input, person_id=threatened):
        # D-109: a hurt tie is asked about first; nothing moves this turn (the dispatcher shows the question)
        front_proposal.note(session, "front:heavy_asked", reached=True)
        return {"kind": "heavy_asked", "what": "threat", "id": threatened, "deed": None, "said": str(player_input)}
    if threatened:
        world_happenings.threatened(world, world_threads._npc(world, threatened))
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
        described = _narrated_person(word, player_input, listed)
        if described is not None:
            route = {"kind": "speak_to", "id": described["id"]}
            _session()._set_scene_active_npc(described, world.get("flags", {}).get("turn_index", 0))
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
            return {"kind": "walk_failed"}  # E5: a walk to nowhere listed is a failed walk, never a person to follow
        return None
    import grounded_action
    import npc_speech_boundary
    if route["kind"] == "strike":
        if _blow_stands(player_input):
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
            if (fighting and not route.get("with") and not _has_explicit_attack_verb(spoken)
                    and not _BLOW_WORDS.search(_normalize_turkish_typos(spoken))
                    and not weapon_attack.names_a_move(session, spoken)):
                # In a fight the reading found a blow, but the words name no blow, no weapon of theirs and no move
                # the engine reads (a trip): the real moves are asked for and nothing rolls (as for an asked blow).
                route = {"kind": "which_move", "id": route["id"]}
            elif _blow_in_the_words(player_input, route["id"]):
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
          and (_model_query_type_is_plausible(player_input) or equipment_economy._natural_inventory_query(player_input))):
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
    _hand_over_coin(route, listed, reply.get("front"))
    if route["kind"] == "look":
        held["intent"] = "observe"
    session._front_thing = route.get("thing")
    return route




def _defer_spoken_coin_offer(route):
    """Only an admitted gift/tip can ask this bound person before the card is shown."""
    session = _session()
    amount = getattr(session, "_front_coin", 0)
    if (not route.get("valid") or route.get("purpose") not in ("gift", "tip")
            or type(amount) is not int or amount <= 0 or session.world_state.get("combat", {}).get("active")):
        return False
    person = next((n for n in active_npcs() if n.get("id") == route.get("id")), None)
    import equipment_economy
    import bold_acts
    import economic_actions
    import world_reactions
    if (person is None or not equipment_economy.npc_can_act(person)
            or economic_actions._held_deed(session.world_state, person) is not None
            or bold_acts.offer_still_open(session.world_state, person) is not None):
        return False
    session._spoken_coin_proposal = economic_actions.turn_proposal(route["purpose"], person["id"], amount_cp=amount)
    return True


def _record_spoken_coin_response(npc, response):
    session = _session()
    proposal = getattr(session, "_spoken_coin_proposal", None)
    if proposal is None or proposal.recipient_id != npc.get("id"):
        return
    session._spoken_coin_proposal = None
    import economic_actions
    economic_actions.record_coin_response(session.world_state, npc, proposal.amount_cp, response,
                                          source_action_id=turn_source_key(session), purpose=proposal.purpose)
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
    session = _session()
    session._coin_paid = None
    session._counter_held = None
    if session.world_state.get("combat", {}).get("active"):
        line = economic_actions._CLARIFY["combat_active"]
        return {"messages": session.messages, "narration": line, "model_calls": 0,
                "action_result": {"action": "narrative", "status": "clarification", "success": False,
                                  "reason_code": "combat_active", "state_changes": [], "direct_response": line}}
    person = next((npc for npc in active_npcs() if npc.get("id") == route.get("id")), None)
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
        _hand_over_coin({"kind": "speak_to", "id": person["id"]}, _economic_listing(session, person),
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
            return _purchase_refused(session, person, amount, player_input)
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
        return _purchase_refused(session, person, amount, player_input)
    import world_reactions
    guard = world_reactions.arrester(session.world_state)
    if amount is not None and purpose in {"gift", "tip"} and guard is not None and guard.get("id") == person.get("id"):
        _hand_over_coin({"kind": "speak_to", "id": person["id"]}, _economic_listing(session, person),
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
            result = bold_acts._reply(session, economic_actions._CLARIFY["npc_unknown"], "narrative", "clarification", None, [], reason_code="npc_unknown")
            result["action_result"]["success"] = False
            return result
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
    deal = money_owner.read_deal(getattr(session, "_front_economic_front", None), _economic_listing(session, person))
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
    session = _session()
    session._counter_held = None
    amount = getattr(session, "_front_coin", 0)
    deal = money_owner.read_deal(front, listed)
    if (not amount and deal is None) or route["kind"] in {"strike", "blow_asked", "which_move"}:
        return
    import world_reactions
    taker = route.get("id") if route["kind"] == "speak_to" else route.get("person_id")
    taker = taker or listed["speaking_with"] or (listed["people"][0]["id"] if len(listed["people"]) == 1 else None)
    person = next((npc for npc in active_npcs() if npc.get("id") == taker), None)
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
    words ask for no bed (a beer, a tip), nor an unclear one when they ask for a bed outside an arrest (D-402)."""
    import bold_acts
    import front_proposal
    import money_owner
    import shop_trade
    import world_reactions
    session = _session()
    amount = front_proposal.coin_in(None, player_input, moves=True)  # `moves`: the words' figure stands with no reading
    if not amount:
        return
    session._front_coin = amount
    if target_id is not None:
        person = next((npc for npc in active_npcs() if npc.get("id") == target_id), None)
    else:
        person = _addressed_in(player_input, or_the_talk=False)
        if person is None and shop_trade.SERVER.search(
                living_world.normalize_text(living_world._text_outside_quotes(player_input))):
            person = bold_acts._server_here(session)
        person = person or _active_interlocutor()
    _hand_over_coin({"kind": "speak_to", "id": person["id"]} if person is not None else {"kind": "attempt"}, listed)
    decided = money_owner.current(session)
    folded = bold_acts.fold(session, player_input)
    bed = bool(bold_acts._ROOM.search(folded) and bold_acts._wants_the_bed(folded))
    if decided is not None and ((decided.kind == "room" and not bed) or (decided.kind == "unclear" and (
            decided.npc_id is None or (bed and world_reactions.arrester(session.world_state) is None)))):
        # No room asked for (a beer ordered, a tip): the structural room is a guess the words do not make. A bed asked
        # for outside an arrest is the room card's, as with the flag off (D-402). The coin stays in hand, undecided
        session._coin_decision = None


def _blow_stands(player_input):
    """The reading may name a blow; the words still decide that one is landing now, outside any quote."""
    import bold_acts
    import grounded_action
    spoken = living_world._text_outside_quotes(str(player_input))
    # 'itemez miyim? ... yumruğumu çakıyorum': a question asked before the blow is no question about the blow
    told = " ".join(part for part in re.split(r"(?<=[?.!])\s+", spoken) if not part.rstrip().endswith("?"))
    text = _normalize_turkish_typos(told)
    return bool(text.strip()) and not ("?" in told or bold_acts._ASKS.search(text) or _ENDS_IN_SPEECH.search(text)
                or _NO_BLOW_NOW.search(text) or any(grounded_action._CONDITION_WORD.match(t) for t in text.split()))




def _blow_in_the_words(player_input, target_id):
    """A reading picks who; whether it starts a fight needs the player's own words, or a fight already there."""
    spoken = living_world._text_outside_quotes(str(player_input))
    target = next((npc for npc in active_npcs() if npc.get("id") == target_id), None)
    combat = _session().world_state.get("combat", {})
    fought = bool(combat.get("active")) and target_id in combat.get("participants", [])
    return bool((isinstance(target, dict) and target.get("hostile")) or fought or _has_explicit_attack_verb(spoken)
                or _BLOW_WORDS.search(_normalize_turkish_typos(spoken)))


def _ask_about_the_blow(person_id, player_input="", with_word=""):
    """Asked in the world, for this sitting only; the next line is the answer. A yes makes the asked line's blow."""
    session = _session()
    who = next((npc for npc in active_npcs() if npc.get("id") == person_id), None)
    session._attack_asked = True
    session._blow_asked = person_id
    session._blow_asked_line = {"said": str(player_input or ""), "with": with_word or ""}
    line = f"{living_world.public_npc_name(who)} ile kavga mı başlatıyorsun?"
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "narrative", "status": "clarification", "success": False,
                              "outcome": "unconfirmed_blow", "state_changes": [], "direct_response": line}}


def _heavy_allowed(what, player_input, *, person_id=None, deed=None):
    """D-109: the asked crime or threat was answered yes, and this is the very line that was asked about."""
    confirmed = getattr(_session(), "_heavy_confirmed", None)
    return (isinstance(confirmed, dict) and confirmed.get("said") == str(player_input)
            and [what, person_id, deed] in confirmed.get("allowed", []))


def _ask_before_the_heavy(asked):
    """D-109 (Kadir kararı 2026-11-15): a crime or a hurt tie is asked about first, in one short line; nothing moves.
    Asked for this sitting only, as "kavga mı başlatıyorsun?" is; a yes plays the asked line again (see
    ``_answered_heavy_question``). Eating and drinking are never asked: Undo takes those back."""
    session = _session()
    session._heavy_asked = {key: asked.get(key) for key in ("what", "id", "deed", "said")}
    if asked["what"] == "threat":
        who = next((npc for npc in active_npcs() if npc.get("id") == asked.get("id")), None)
        name = living_world.public_npc_name(who) if who is not None else "o kişi"
        line = f"Bu, {name} ile aranı bozar. Gerçekten tehdit ediyor musun? (evet/hayır)"
    elif asked.get("deed") == "steal_look":  # D-224 review: the line looked; the reading alone said theft
        line = "Yalnız bakmakla kalmayıp çalmaya mı çalışıyorsun? Bu bir suç olarak kayda geçer. (evet/hayır)"
    else:
        act = "çalıyor" if asked.get("deed") == "steal" else "ateşe veriyor"
        line = f"Bu bir suç olarak kayda geçer. Gerçekten {act} musun? (evet/hayır)"
    return {"messages": session.messages, "narration": line, "model_calls": 0,
            "action_result": {"action": "narrative", "status": "clarification", "success": False,
                              "outcome": f"unconfirmed_{asked['what']}", "state_changes": [], "direct_response": line}}


def _answered_heavy_question(player_input):
    """D-109: a yes to the asked crime or threat is the asked line, now allowed; anything else forgets the question."""
    session = _session()
    asked, session._heavy_asked = getattr(session, "_heavy_asked", None), None
    given, session._heavy_confirmed = getattr(session, "_heavy_confirmed", None), None
    if isinstance(asked, dict) and combat_lifecycle._says_yes(session, player_input):
        # D-109 review: a second question on the same line keeps the first yes (else the two would ask in turn forever);
        # the threat played again is not a second threat: its tie is made once while it is coming (world_happenings.tie)
        kept = given.get("allowed", []) if isinstance(given, dict) and given.get("said") == asked["said"] else []
        session._heavy_confirmed = {"said": asked["said"],
                                    "allowed": [*kept, [asked["what"], asked["id"], asked["deed"]]]}
        return asked["said"]
    return player_input


def _ask_which_move(person_id):
    """A yes to a blow whose words name no move the engine has (a trip): the real moves are offered, nothing rolls."""
    session = _session()
    session._which_move = None
    who = next((npc for npc in active_npcs() if npc.get("id") == person_id), None)
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
    here = _conversation_npcs()
    same = next((npc for npc in here if stem in living_world.normalize_text(npc.get("role"))), None)
    told = living_world.normalize_text(pocket.told_as_there(_recent_player_visible_narration(limit=4000)))
    scene = living_world.normalize_text(" ".join(str(row["name"]) for row in [*listed["things"], *listed["places"]]))
    if same is not None or stem not in told or stem in scene:  # the screen itself vouches for them, whatever word the player uses
        return same
    label = word.strip().capitalize()
    return create_npc_from_ai({"name": label, "role": label, "appearance": f"Az önce gözüne çarpan {word.strip()}",
                               "location": _session().world_state.get("location"), "relationship": "neutral"},
                              request_key=_local_person_request_key(word))


def front_read_ahead(player_input, target_id=None, interaction_mode=None):
    """The planner moves the player on word lists before the turn proper, so the reading has to come first."""
    import front_proposal
    session = _session()
    session._front_ahead = False
    session._counter_held = None  # only this turn's reading may hold coin back for an open offer
    if not getattr(session, "_heavy_asked", None):
        session._heavy_confirmed = None  # D-109 review: a yes is spent with its turn; this line was never asked
    if (not front_proposal.enabled() or session.character.get("current_hp", 0) <= 0 or ensure_death_state()["dead"]
            or getattr(session, "_attack_asked", False) or getattr(session, "_heavy_asked", None)
            or not isinstance(player_input, str)
            or combat_lifecycle.surrender_yes(session, player_input)  # G9: the engine's own question, Python's yes
            or _is_end_conversation_request(player_input)):
        return None
    interaction_mode = _normalize_interaction_mode(interaction_mode)
    front_proposal.begin(session, typed=target_id is not None or interaction_mode in {"say", "ask_dm"})
    session._front_ahead = True
    session._front_read = _front_step(player_input, target_id, interaction_mode, None, None)
    return session._front_read


def _front_offer_gate(route, player_input):
    """A yes or no the model read on a listed offer goes through the same writers as one the word lists read."""
    import town_knowledge
    import world_threads
    session = _session()
    world = session.world_state
    person = next((npc for npc in active_npcs() if npc.get("id") == route["person_id"]), None)
    thread = world_threads.by_id(world, route["id"])
    if person is None or thread is None or thread.get("status") != "offered":
        return None
    try:
        reading = world_threads.read_answer(player_input, person, thread)
        says_other = reading["meaning"] in ({"decline", "withdraw"} if route["answer"] == "accept" else {"accept"})
        if reading["terms"] or world_threads.asks_for_pay(player_input) or says_other or "?" in player_input:
            # The model's yes or no is overruled, so Python's own reading of the line decides the turn.
            return _thread_gate(player_input, person["id"], "say") or {"decision": None, "npc_id": person["id"]}
        session.require_player_can_act()
        gate = {"thread_id": route["id"], "npc_id": person["id"], "takes": route.get("takes", False),
                "works": route.get("works", False),
                "decision": "accepted" if route["answer"] == "accept" else "declined"}
        return _carry_out_thread_turn(session, world, gate, person, player_input)
    except PlayerCannotAct:
        raise
    except Exception:
        town_knowledge.log_failure()
        session._thread_turn = None
        return None


def _line_gives(item_id, player_input):
    """The line names this thing, or it is the one thing there is to give."""
    import front_proposal
    import pocket
    world = _session().world_state
    if _NO_BLOW_NOW.search(_normalize_turkish_typos(player_input)):
        return False  # 'vermiyorum': said, not done; the same reading the handed coin already uses
    bag = front_proposal._bag(world)
    stem = pocket._stem(next((row["name"] for row in bag if row["id"] == item_id), ""))
    return len(bag) == 1 or bool(stem and pocket._says_it(player_input, stem))


def _front_consume(route, player_input):
    """A listed item is consumed by its engine kind, never by the proposed prose."""
    import item_use
    import equipment_economy
    session = _session()
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
    session = _session()
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
    return _names_no_parcel(world, person, item_id, player_input)


def _names_no_parcel(world, person, item_id, player_input):
    """No word of the line meets a parcel this person could take (see `_coin_not_parcel`)."""
    import world_threads
    from adventure import dialogue_jobs
    threads = ([world_threads.parcel_thread(world, item_id)] if item_id is not None
               else [job for job in [*world_threads.deliveries_to(world, person),
                                     *world_threads.late_parcels(world, person)]
                     if dialogue_jobs.holds_parcel(world, job)])
    table = world_threads.answer_table()
    roots = {_word_root(word) for word in set(table["item_words"]) - set(table["pointing"])}
    roots |= {_word_root(noun[-1]) for job in threads if job is not None
              for noun in [living_world.normalize_text(job.get("item_noun")).split()] if noun}
    words = living_world.normalize_text(living_world._text_outside_quotes(player_input)).split()
    return not any(word.startswith(root) for root in roots for word in words)


def _front_hand_over(route, player_input):
    """The model read a hand-over and named a listed thing. Python moves it; failing that the person hears the line."""
    import town_knowledge
    import world_threads
    from adventure import dialogue_jobs
    session = _session()
    world = session.world_state
    person = next((npc for npc in active_npcs() if npc.get("id") == route["person_id"]), None)
    if person is None:
        return None
    heard = {"decision": None, "npc_id": person["id"]}
    item_id = route["item"]
    if _coin_not_parcel(session, world, person, item_id, player_input):
        return heard  # D-239: a tip or coin that names no parcel is money for its card, never the job's delivery
    if world_threads.refuses_hand_over(player_input, lambda clause: not _names_no_parcel(world, person, item_id, clause)):
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
        return _thread_gate(player_input, person["id"], "say") or heard  # nothing named: the old reader, then their answer
    try:
        session.require_player_can_act()
        thread = due if item_id is None else world_threads.parcel_thread(world, item_id)
        if thread is None and not item_id.startswith("parcel:"):
            if _line_gives(item_id, player_input):  # a plain thing never comes back: it goes only if the line means it
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
        return _carry_out_thread_turn(session, world, {"thread_id": thread["thread_id"], "decision": decision,
                                                       "npc_id": person["id"]}, person, player_input)
    except PlayerCannotAct:
        raise
    except Exception:
        town_knowledge.log_failure()
        session._thread_turn = None
        return heard


def _front_work(route, player_input):
    """The model read work being done now. A promise or a question is still only words."""
    import town_knowledge
    import world_threads
    session = _session()
    world = session.world_state
    person = next((npc for npc in active_npcs() if npc.get("id") == route["person_id"]), None)
    thread = world_threads.by_id(world, route["id"])
    if person is None or thread is None or thread.get("status") != "accepted":
        return None
    if "?" in player_input or world_threads.says_later(player_input):
        return _thread_gate(player_input, person["id"], "say") or {"decision": None, "npc_id": person["id"]}
    try:
        session.require_player_can_act()
        return _carry_out_thread_turn(session, world, {"thread_id": route["id"], "decision": "work",
                                                       "npc_id": person["id"]}, person, player_input)
    except PlayerCannotAct:
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
    world = _session().world_state
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
    session = _session()
    world = session.world_state
    session.require_player_can_act()
    thread = world_threads.by_id(world, route["thread_id"]) if route.get("thread_id") else None
    person = next((npc for npc in active_npcs() if npc.get("id") == route.get("person_id")), None)

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
            giver = next((npc for npc in active_npcs() if npc.get("id") == job.get("owner_npc_id")), None)
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


def _dispatch_player_turn(
    player_input, messages=None, target_id=None, scene_plan=None,
    action_id=None, session_id=None, combat_action=None, interaction_mode=None,
    check_feature=None, check_evidence=None,
):
    interaction_mode = _normalize_interaction_mode(interaction_mode)
    if not getattr(_session(), "_thread_gate_done", False):
        _session()._thread_turn = None
    if ensure_death_state()["dead"]:
        raise PlayerCannotAct("Ölü karakter eylem gerçekleştiremez.")
    if _session().character.get("current_hp", 0) <= 0:
        # A body on the ground has no moves left: whatever is typed or clicked is this turn's save.
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            return _run_player_turn_internal(player_input, messages, target_id, {"direct_result": None},
                                             "do", action_id)
    _reopen_public_doors()
    player_input = combat_lifecycle.answered_attack_question(_session(), player_input)
    player_input = _answered_heavy_question(player_input)  # D-109
    ahead = getattr(_session(), "_front_read", None) if getattr(_session(), "_front_ahead", False) else None
    if isinstance(ahead, dict) and ahead.get("kind") == "heavy_asked":
        return _ask_before_the_heavy(ahead)  # D-109: read ahead of the turn; asked before any owner answers
    surrender_answer = (combat_lifecycle.answered_surrender_question(_session(), player_input)
                        if combat_action is None else None)
    if surrender_answer is not None:
        player_input, combat_action, target_id = surrender_answer  # the asked blow, at the asked foe only
    if getattr(_session(), "_which_move", None):
        return _ask_which_move(_session()._which_move)
    owner_reply = _owner_module_reply(player_input, interaction_mode)
    if owner_reply is not None:
        return {
            "messages": _session().messages,
            "narration": owner_reply.get("direct_response") or "",
            "model_calls": 0,
            "action_result": owner_reply,
        }
    if combat_action is not None:
        interaction_mode = "do"
    elif interaction_mode in {"say", "ask_dm"}:
        if _session().world_state.get("combat", {}).get("active"):
            raise combat_lifecycle.CombatRequestError(
                "unsupported_interaction_mode", "Use an action during active combat.", 400
            )
        require_player_can_act()
        if interaction_mode == "ask_dm":
            target_id = None
        elif target_id is not None and isinstance(player_input, str) and not player_input.lstrip().startswith("/"):
            # Said to someone, a line that names another person standing here is said to them; the talk turns to them.
            named = _addressed_in(player_input, or_the_talk=False)
            if (isinstance(named, dict) and named.get("id") not in {None, target_id}
                    and named.get("id") in {npc.get("id") for npc in _conversation_npcs()}
                    and _line_addresses(player_input, named)):
                target_id = named["id"]
    if (
        combat_action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not _session().world_state.get("combat", {}).get("active")
        and _is_end_conversation_request(player_input)
    ):
        require_player_can_act()
        active = _active_interlocutor()
        _clear_active_interlocutor("ended")
        interaction_adventure.retire_conversation_focus(_session().world_state)
        if active is None:
            narration = "Şu anda sürdürdüğün bir konuşma yok."
            status = "no_effect"
        else:
            narration = f"{living_world.public_npc_name(active)} ile konuşmayı bitiriyorsun."
            status = "conversation_ended"
        return {
            "messages": _session().messages,
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
    read = getattr(_session(), "_front_read", None) if getattr(_session(), "_front_ahead", False) else None
    import front_proposal
    if (front_proposal.enabled() and not getattr(_session(), "_front_ahead", False)
            and not getattr(_session(), "_front_strike", None)):
        read = _front_step(player_input, target_id, interaction_mode, combat_action, check_feature)
        _session()._front_read = read
        _session()._front_ahead = True
    if read is not None and read.get("kind") == "heavy_asked":
        return _ask_before_the_heavy(read)  # D-109: asked, nothing moved
    if getattr(_session(), "_front_strike", None):
        target_id, interaction_mode = _session()._front_strike["id"], "do"
    elif (target_id is not None and combat_action is None
          and not _session().world_state.get("combat", {}).get("active")):
        import bold_acts
        if bold_acts.is_act_not_talk(_session(), player_input):
            # D-172: with the person chosen by the talk button, a scare or a look-over is still an act on them, not a
            # line to them; it takes the same route as without the button, so the dice and the narrator answer.
            interaction_mode, target_id = "do", None
    import spell_effects
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"}
            and not getattr(_session(), "_front_strike", None) and spell_effects.named(player_input) is not None):
        # 4C.5: a narrative spell (or one not in the engine yet) is the spell owner's, never a walk, a knock or an item
        # move; the engine answers it inside the turn and the narrator tells the fact.
        return _dispatch_turn_body(player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                                   session_id, check_feature, check_evidence)
    if combat_action is None:
        import fallen
        body = fallen.addressed_body(_session(), player_input) if not combat_lifecycle.is_attack_decision(_session(), player_input) else None
        if (body is not None and _reads_as_address(player_input)
                and (read is None or read["kind"] == "speak_to" or (read["kind"] == "economic" and read.get("valid")))):  # a line read as an act is no word to them
            line = fallen.silence(body)
            return {
                "messages": _session().messages, "narration": line, "model_calls": 0,
                "action_result": {"action": "narrative", "status": "body_silent", "success": True,
                                  "state_changes": [], "direct_response": line},
            }
    confessed = False
    if (combat_action is None and interaction_mode != "ask_dm"
            and not _session().world_state.get("combat", {}).get("active")):
        import bold_acts
        confessed = bold_acts.hear_confession(_session(), player_input)
    if read is not None and read.get("kind") == "economic":
        economic_result = None
        if not confessed:
            with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
                economic_result = None if _defer_spoken_coin_offer(read) else _front_economic_offer(read, player_input)
        if economic_result is not None:
            return economic_result
        read = {"kind": "speak_to", "id": read["id"]}
        _session()._front_read = read
        interaction_mode, target_id = "say", read["id"]  # law/confession delegation keeps the bound hearer
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"} and not confessed
            and not _session().world_state.get("combat", {}).get("active")):
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            deed = getattr(_session(), "_front_deed", None)
            bold = bold_acts.resolve(
                _session(), player_input, deed,
                # D-109: a crime is asked about first, whether the reading or the old words (no reading) found it
                ask=lambda act: None if _heavy_allowed("deed", player_input, deed=act)
                else _ask_before_the_heavy({"what": "deed", "id": None, "deed": act, "said": str(player_input)}))
        if bold is not None:
            return bold
    elif (combat_action is None and interaction_mode == "say" and isinstance(player_input, str)
          and not player_input.lstrip().startswith("/") and not _session().world_state.get("combat", {}).get("active")):
        # Said straight to whoever serves, a want on the list opens the same counter offer: speech never sells.
        import bold_acts
        import shop_trade
        hearer = next((npc for npc in active_npcs() if npc.get("id") == target_id), None) if target_id else None
        if target_id is None or shop_trade.is_vendor(_session().world_state, hearer):
            offered = bold_acts.shop_offer(_session(), player_input, hearer)
            if offered is not None:
                return offered
    if combat_action is None and interaction_mode not in {"say", "ask_dm"}:
        struck = combat_lifecycle.strike_the_fallen(_session(), player_input, target_id)
        if struck:
            return {
                "messages": _session().messages,
                "narration": struck,
                "model_calls": 0,
                "action_result": {"action": "narrative", "status": "resolved", "success": True,
                                  "state_changes": ["npcs"], "direct_response": struck},
            }
        question = combat_lifecycle.unbound_attack_reply(_session(), player_input, target_id)
        if question:
            _session()._attack_asked = True  # for this sitting only; never saved
            return {
                "messages": _session().messages,
                "narration": question,
                "model_calls": 0,
                "action_result": {
                    "action": "attack", "status": "clarification", "success": False,
                    "outcome": "missing_target", "state_changes": [],
                    "direct_response": question,
                },
            }
    # D-095: "muhafızın kesesi var mı diye inceliyorum" is about someone else's purse; never answer with the player's
    if read is not None and read["kind"] == "bag" and not _SOMEONE_ELSES_PURSE.search(
            _normalize_turkish_typos(living_world._text_outside_quotes(player_input))):
        listed = equipment_economy.execute(_session(), "çantamda ne var")
        if listed is not None:

            return listed
    if combat_action is None and interaction_mode not in {"say", "ask_dm"}:
        from adventure import dialogue_jobs
        parcel_read = dialogue_jobs.read_parcel(_session(), player_input)
        if parcel_read is not None:
            return parcel_read
        import town_knowledge
        # A line the reading gave to a person is said to them, whatever board it mentions.
        board = None if (read or {}).get("kind") == "speak_to" else town_knowledge.board_turn(_session(), player_input)
        if board is not None:
            return board
        import bound_text
        if (read or {}).get("kind") != "take":  # 'alıp okuyorum': the taking owns it and reads on
            looked_at = (getattr(_session(), "_front_found", None) or ("", ""))[1] if (read or {}).get("kind") == "look" else ""
            paper_read = bound_text.read_turn(_session(), player_input, looked_at,
                                              to_someone=(read or {}).get("kind") == "speak_to")
            if paper_read is not None:
                return paper_read
        import pocket
        pocketed = pocket.resolve(_session(), player_input)
        if pocketed is not None:
            return pocketed
        if equipment_economy._natural_inventory_query(player_input) and not _has_explicit_attack_verb(player_input):
            listed = equipment_economy.execute(_session(), player_input)  # the bag answers for itself, whoever stands near
            if listed is not None:
                return listed
    front = read if getattr(_session(), "_front_ahead", False) else _front_step(
        player_input, target_id, interaction_mode, combat_action, check_feature)
    if front is not None and front["kind"] == "blow_asked":
        return _ask_about_the_blow(front["id"], player_input, front.get("with"))
    if front is not None and front["kind"] == "which_move":
        return _ask_which_move(front["id"])
    held_for = getattr(_session(), "_counter_held", None)
    _session()._counter_held = None
    if held_for is not None:
        import bold_acts
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            standing = bold_acts.standing_offer(_session(), held_for)
        if standing is not None:
            return standing
        _session()._coin_paid = None  # coin held out for an open offer is never a gift, even when the offer closed
    if front is not None and front["kind"] == "speak_to":
        import bold_acts
        if target_id is not None or not bold_acts.is_act_not_talk(_session(), player_input):  # D-098, D-099: an act
            interaction_mode, target_id = "say", front["id"]
    if (combat_action is None and interaction_mode not in {"say", "ask_dm"} and target_id is None and front is None
            and _ENDS_IN_SPEECH.search(_normalize_turkish_typos(player_input))):
        hearer = _active_interlocutor()  # "dedim sana" is said to the one already being talked to
        if hearer is not None:
            interaction_mode, target_id = "say", hearer["id"]
    gate = None
    if (combat_action is None and not getattr(_session(), "_thread_gate_done", False)
            and not getattr(_session(), "_front_strike", None)):  # a blow stood behind is no answer to an offer
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            gate = (None if front is not None and (front.get("dropped") or front["kind"] == "wield"
                                                   or _take_names_a_job(front))
                    else _front_offer_gate(front, player_input) if front is not None and front["kind"] == "offer_answer"
                    else _front_consume(front, player_input) if front is not None and front["kind"] == "consume"
                    else _front_hand_over(front, player_input) if front is not None and front["kind"] == "hand_over"
                    else _front_work(front, player_input) if front is not None and front["kind"] == "work"
                    else _thread_gate(player_input, target_id, interaction_mode, front=front))
        if front is not None and front.get("recovered_from") and front["kind"] == "offer_answer" and not (
                gate is not None and gate.get("decision") == "accepted"):
            import front_proposal
            front_proposal.note(_session(), front["recovered_from"])  # the gate did not take the yes: no recovery to claim
        if gate is not None and gate.get("reply") is not None:
            return gate["reply"]
        if gate is not None and gate.get("paid_line"):
            _session()._thread_gate_done = True  # the coin moved; the person still says their word, by any route
            try:
                said = _dispatch_player_turn(
                    player_input, messages, gate["npc_id"], scene_plan, action_id, session_id, combat_action,
                    "say", check_feature, check_evidence,
                )
            finally:
                _session()._thread_gate_done = False
            said["narration"] = f"{said.get('narration') or ''} {gate['paid_line']}".strip()
            return said
        if gate is not None and gate.get("moving"):
            _session()._thread_turn = None
            _session()._thread_gate_done = True  # the line goes on as the walk it also was
            try:
                walked = _dispatch_player_turn(
                    player_input, messages, target_id, scene_plan, action_id, session_id, combat_action,
                    interaction_mode, check_feature, check_evidence,
                )
            finally:
                _session()._thread_gate_done = False
            walked["narration"] = f"{gate['moving']} {walked.get('narration') or ''}".strip()
            return walked
        if gate is not None:
            interaction_mode, target_id = "say", gate["npc_id"]
    if front is not None and front["kind"] == "wield" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            _front_wield(front, player_input)  # the turn goes on to the narrator, who reads the hand and the note on the card
    if front is not None and front["kind"] == "take" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            taken = _front_take(front, player_input)
        if taken is not None:
            return taken
    if front is not None and front["kind"] == "wait" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        passed = timed_gameplay.pass_time(_session(), player_input)
        if passed is not None:
            flags = _session().world_state.setdefault("flags", {})
            flags["turn_index"] = flags.get("turn_index", 0) + 1
            return {"messages": _session().messages, "narration": passed["direct_response"], "model_calls": 0,
                    "action_result": passed}
    if front is not None and front["kind"] == "walk_failed" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        text = _fallback_for_action_result(player_input, {"action": "travel", "status": "failed"})
        flags = _session().world_state.setdefault("flags", {})
        flags["turn_index"] = flags.get("turn_index", 0) + 1
        return {"messages": _session().messages, "narration": text, "model_calls": 1,
                "action_result": {"action": "travel", "status": "failed", "success": False,
                                  "state_changes": [], "direct_response": text}}
    if front is not None and front["kind"] == "go_to" and gate is None and interaction_mode not in {"say", "ask_dm"}:
        import front_proposal
        import grounded_action
        road_warning = None
        if front["id"] == front_proposal.WAY_OUT:
            refused = grounded_action.road_goes_on(_session(), player_input)
            road_warning = (refused or {}).get("road_warning")
            if refused is not None and road_warning is None:
                return refused
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            walked = grounded_action.resolve_turn(_session(), player_input, listed_place=front)
        if walked is not None:
            if road_warning:
                walked["narration"] = f"{road_warning} {walked.get('narration') or ''}".strip()
            return walked
        front_proposal.note(_session(), "fallback:no_walk")
    if combat_action is None:
        import dialogue_runtime
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            free_dialogue = dialogue_runtime.resolve_turn(
                _session(), player_input, interaction_mode=interaction_mode,
                target_id=target_id, action_id=action_id,
            )
        if free_dialogue is not None:
            return free_dialogue
    if combat_action is None and interaction_mode in {"say", "ask_dm"}:
        if (
            interaction_mode == "ask_dm"
            and equipment_economy._natural_inventory_query(player_input)
        ):
            equipment_result = equipment_economy.execute(_session(), player_input)
            if equipment_result is not None:
                return equipment_result
        if action_id is None:
            try:
                return _run_player_turn_internal(
                    player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                    **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {})
                )
            except TurnResolved as e:
                return _narrate_resolved_turn(
                    e.resolved_turn, player_input, messages, target_id
                )
        with resolution_action_scope(action_id, session_id):
            try:
                return _run_player_turn_internal(
                    player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                    **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {})
                )
            except TurnResolved as e:
                return _narrate_resolved_turn(
                    e.resolved_turn, player_input, messages, target_id
                )

    if (
        combat_action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not _session().world_state.get("combat", {}).get("active")
    ):
        hideout = adventure_play.resolve_dungeon_turn(_session(), player_input, _hideout_check)
        if hideout is not None:
            return hideout
        # Read as talk, a look or sitting down: the words of a line walk nowhere. The route log shows these lost all traffic.
        talk = front is not None and front["kind"] in {"talk_around", "look", "sit"}
        # D-123: the quest shortcut's rolls (a check, the road's Survival) belong to this turn like any journey's.
        with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
            scene = None if talk else _adventure_scene_turn(player_input)
        if scene is not None:
            return scene
        # LR00 fix: read a local physical action once, bind it to a real target
        # and let its owner resolve it (grounded_action). None = older owners.
        import grounded_action
        if not talk and not _scene_observation_proposal_turn(
            player_input, _session().world_state, interaction_mode
        ) and not (
            living_world.is_anchored_structure_inquiry(player_input)
            and living_world.affirmative_structure_inspection(
                player_input, interaction_mode
            )
        ):
            with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
                grounded = grounded_action.resolve_turn(
                    _session(), player_input, interaction_mode=interaction_mode, target_id=target_id,
                )
            if grounded is not None:
                return _spoken_rest_of_turn(grounded, player_input, messages, action_id, session_id)
        local_place = None if talk else _local_place_turn(player_input)
        if local_place is not None:
            return local_place
        # BM Task 8: a reading that named something (a place, a person, a thing) belongs to that owner; the everyday
        # words run only when there was no reading, or it said unclear / attempt.
        everyday = (_everyday_action_turn(player_input)
                    if front is None or front["kind"] in {"unclear", "attempt"} else None)
        if everyday is not None:
            return everyday
    import exploration
    if (combat_action is None and _session().character.get("current_hp", 0) > 0
            and exploration.native_request(player_input, _session())):
        with resolution_action_scope(action_id, session_id):
            exploration_result = exploration.resolve_command(_session(), player_input)
        if exploration_result is not None:
            return exploration_result
    import authored_dungeon
    if combat_action is None:
        dungeon_result = authored_dungeon.resolve_command(_session(), player_input)
        if dungeon_result is not None:
            return dungeon_result
    planning = (combat_action is None
                and not _session().world_state.get("combat", {}).get("active")
                and not getattr(_session(), "_front_strike", None)
                and interaction_adventure.compound_plan(player_input) is not None)
    if (combat_action is None and not planning
            and not combat_lifecycle.is_attack_decision(_session(), player_input)):
        equipment_result = equipment_economy.execute(_session(), player_input)
        if equipment_result is not None:
            return equipment_result
    import spell_scope
    spell_command = (spell_scope.natural_command(player_input, target_id)
                     if combat_action is None and not planning else None)
    if spell_command is not None:
        surrender_question = combat_lifecycle.surrendered_strike_question(
            _session(), player_input, target_id, spell_command)  # a harmful spell is asked like a blow (D-036)
        if surrender_question is not None:
            return surrender_question
        return action_economy.execute(_session(), spell_command, action_id, session_id)
    import bounded_encounter
    if not planning:
        bounded_encounter.refresh(_session())
    native = (bounded_encounter.resolve_command(_session(), player_input)
              if combat_action is None and not planning else None)
    if native is not None:
        return native
    import monster_combat
    if combat_action is None and _session().world_state.get("combat", {}).get("active"):
        with initiative.atomic(_session()):
            proposal_result = monster_combat.player_response(_session(), player_input, target_id)
            if proposal_result is not None:
                return proposal_result
    if combat_action is None and combat_lifecycle.is_standing_down(_session(), player_input):
        with resolution_action_scope(action_id, session_id):
            settled = combat_lifecycle.stand_down(_session(), action_id, session_id)
        if settled is not None:
            return settled
    if combat_action is None and combat_lifecycle.is_flight(_session(), player_input):
        with resolution_action_scope(action_id, session_id):
            fled = combat_lifecycle.flee(_session(), action_id, session_id)
        if fled is not None:
            return fled
    command = combat_action or (None if planning else
                               action_economy.natural_command(_session(), player_input, target_id))
    surrender_question = combat_lifecycle.surrendered_strike_question(_session(), player_input, target_id, command)
    if surrender_question is not None:
        return surrender_question
    if command:
        return action_economy.execute(_session(), command, action_id, session_id)
    if action_economy.pending_reaction(_session()):
        raise combat_lifecycle.CombatRequestError("reaction_pending", "Resolve or decline the reaction opportunity.", 400)
    if (
        combat_action is None
        and interaction_mode not in {"say", "ask_dm"}
        and not _session().world_state.get("combat", {}).get("active")
        # Only when the scene planner already ran and had no answer of its own.
        and isinstance(scene_plan, dict)
        and scene_plan.get("direct_result") is None
    ):
        # LR00 fix, second pass: no older owner took the turn. A local act whose
        # target the words alone could not bind gets one bounded model call that
        # may only pick listed candidate IDs; otherwise the full pipeline runs.
        import grounded_action
        if not (front is not None and front["kind"] in {"talk_around", "look", "sit"}) and not _scene_observation_proposal_turn(
            player_input, _session().world_state, interaction_mode
        ):
            with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
                grounded = grounded_action.resolve_turn(
                    _session(), player_input, interaction_mode=interaction_mode,
                    target_id=target_id, phase="fallback",
                )
            if grounded is not None:
                return _spoken_rest_of_turn(grounded, player_input, messages, action_id, session_id)
    _session()._walk_off = None
    try:
        combat_lifecycle.validate_request(_session(), player_input, target_id)
    except combat_lifecycle.CombatRequestError as error:
        if error.code != "combat_travel":
            raise
        # held for the turn's reading: a walk toward someone in the fight is combat movement (_approach_turn takes it);
        # any other reading of the line is refused as walking off, as before
        _session()._walk_off = error
    try:
        result = _dispatch_turn_body(player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                                     session_id, check_feature, check_evidence)
        walk, _session()._walk_off = _session()._walk_off, None
    except BaseException:
        _session()._walk_off = None
        raise
    if walk is not None:
        raise walk
    return result


def _dispatch_turn_body(player_input, messages, target_id, scene_plan, interaction_mode, action_id, session_id,
                        check_feature, check_evidence):
    if action_id is None:
        try:
            return _run_player_turn_internal(
                player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                    **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {})
            )
        except TurnResolved as e:
            return _narrate_resolved_turn(
                e.resolved_turn, player_input, messages, target_id
            )
    with resolution_action_scope(action_id, session_id):
        try:
            return _run_player_turn_internal(
                player_input, messages, target_id, scene_plan, interaction_mode, action_id,
                    **({"check_feature": check_feature, "check_evidence": check_evidence} if check_feature is not None else {})
            )
        except TurnResolved as e:
            return _narrate_resolved_turn(
                e.resolved_turn, player_input, messages, target_id
            )


def _sleep_after_walk(walked, player_input, place_before, scene_plan=None):
    """"Hana gidip uyuyorum": the walk is only the first half of what was said."""
    world_state = _session().world_state
    planned = scene_plan.get("direct_result") if isinstance(scene_plan, dict) else None
    entered = isinstance(planned, dict) and planned.get("action") == "enter"  # the door was gone through before this turn ran
    if not isinstance(walked, dict) or world_state.get("combat", {}).get("active"):
        return
    moved = world_state.get("location") != place_before or entered
    receipt = walked.get("action_result") or {}
    if moved:
        import bold_acts
        import economic_actions
        key = turn_source_key(_session())
        if key and economic_actions.prepared_by_action(world_state, source_action_id=key, purpose="room"):
            return  # this line already opened the room card; no second card, and no sleep before it is confirmed
        room = bold_acts.take_room(_session(), player_input, walk_to_bed=True)
        if room is not None:
            _session()._front_rest = ""  # the room part of the line is answered here, not read again
            walked["narration"] = f"{walked.get('narration') or ''} {room['line']}".strip()
            if room["coin_seen"]:
                walked.setdefault("action_result", {})["coin_seen_by"] = "room"
            if not room["room"]:
                return  # a card opened (or a no): sleeping waits for a room really held
    elif (receipt.get("action"), receipt.get("status")) != ("lodging", "rented"):
        return
    if not timed_gameplay._SLEEPING.search(_normalize_turkish_typos(player_input)):
        return
    slept = timed_gameplay.resolve_input(_session(), player_input)
    if slept is not None:
        _session()._front_rest = ""  # the line's sleep is slept here, once
        walked["narration"] = f"{walked.get('narration') or ''} {slept['direct_response']}".strip()
        talk_mode.close(world_state, "rest")


def _spoken_rest_of_turn(grounded, player_input, messages, action_id, session_id):
    """"...tezgâha geçiyorum, bir bira istiyorum": after the walk the words reach the person."""
    import grounded_action
    request = grounded_action.spoken_request(player_input)
    result = grounded.get("action_result") or {}
    if not request or result.get("status") not in {"completed", "partial"}:
        return grounded
    flags = _session().world_state.get("flags", {})
    present = active_npcs()
    npc = next(
        (candidate for candidate in present if candidate.get("id") == flags.get("active_npc_id")),
        None,
    ) or (most_plausible_addressee(present, request) if present else None)
    if not isinstance(npc, dict):
        return grounded
    with (resolution_action_scope(action_id, session_id) if action_id else contextlib.nullcontext()):
        try:
            spoken = _run_player_turn_internal(request, messages, npc["id"], None, "say", action_id)
        except TurnResolved as resolved:
            spoken = _narrate_resolved_turn(resolved.resolved_turn, request, messages, npc["id"])
    spoken["narration"] = f"{grounded['narration']} {spoken['narration']}"
    spoken["model_calls"] = spoken.get("model_calls", 0) + grounded.get("model_calls", 0)
    return spoken


def _current_procedural_entity_ids():
    world_state = _session().world_state
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
    world = _session().world_state
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
    sentences = [part.strip() for part in _split_sentences_keep_speech(narration.strip())
                 if part.strip() and not any(mark in part for mark in _QUOTES) and not town_knowledge.names_coin(part)]
    clean = town_knowledge.without_unbacked_money(" ".join(sentences)) or ""
    portrait = " ".join(_split_sentences_keep_speech(clean)[:2]).strip()
    if portrait:
        record["town_portrait"] = portrait


def _narrate_resolved_turn(resolved_turn: ResolvedTurn, player_input, messages, target_id):
    if messages is None:
        messages = resolved_turn.messages or _session().messages

    npc_target = resolved_turn.npc_target
    if npc_target is None and isinstance(resolved_turn.action_result, dict):
        npc_id = resolved_turn.action_result.get("npc_id")
        if npc_id:
            for npc in _session().world_state.get("npcs", []):
                if isinstance(npc, dict) and npc.get("id") == npc_id:
                    npc_target = npc
                    break

    lore_context = resolved_turn.lore_context
    if lore_context is None:
        injected = getattr(_session(), "lore_authority_context", None)
        lore_context = _prepare_lore_authority_context(injected)

    narration_only = not (
        resolved_turn.allow_new_npcs
        or resolved_turn.allow_new_features
        or resolved_turn.allow_new_shops
        or resolved_turn.allow_new_locations
    )
    emergence = incident_hooks.before_narration(
        _session(), action_result=resolved_turn.action_result, player_text=player_input,
        location_changed=bool(resolved_turn.expected_location_change),
    )
    narration_model_calls = 1
    from api.model_phase import resolved_narration_scope
    proposes_place = _may_propose_local_place(resolved_turn, player_input)
    with resolved_narration_scope(narration_only):
        packet = ask_dungeon_master(
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
    packet = packet if isinstance(packet, dict) else {}
    if proposes_place:
        resolved_turn.action_result["verified_world_updates"] = {
            "create_locations": _accepted_local_place(packet, resolved_turn.action_result),
        }
        packet["world_updates"] = {}

    rejected_scene_detail_proposal = False
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

    proposal_snapshot = _world_snapshot()
    if packet.get("valid_response") and any((packet.get("world_updates") or {}).values()):
        packet["valid_response"] = False
        packet["narration"] = resolved_turn.fallback_response
        packet["fallback_reason_code"] = "MODEL_WORLD_PROPOSAL_REJECTED"
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
        is_assertion = is_player_world_assertion(player_input) and not resolved_turn.allow_new_shops

        # Location proposals are validated and committed before the player location changes.
        location_updates = validate_world_updates(
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
            merge_world_updates({"create_locations": location_updates["create_locations"]})
            if proposes_place:
                _settle_local_place(resolved_turn.action_result)
        if resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "awaiting_proposal":
            _commit_travel_action(resolved_turn.action_result)
            if (
                proposes_place
                and resolved_turn.action_result.get("status") not in ("failed", "intended")
                and _session().world_state.get("location") != resolved_turn.action_result.get("target")
                and resolved_turn.action_result.get("direct_response")
            ):
                # Stopped on the way: the narrator wrote before the walk, so its arrival is untrue.
                packet["narration"] = resolved_turn.action_result["direct_response"]

        # Validate NPC/feature/shop proposals only after any accepted location exists.
        validated_updates = validate_world_updates(
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
            created_npcs = merge_world_updates(validated_updates) if not is_assertion else []
            if resolved_turn.allow_new_shops and validated_updates.get("create_shops"):
                resolved_turn.action_result.update(success=True, status="created")
                resolved_turn.action_result.setdefault("state_changes", []).append("world.shops")
                packet["narration"] = (
                    "Bu kampanyada mevcut konumda tek bir yerel dükkân ve onu işleten "
                    "bir dükkâncı kaydedildi."
                )
                packet["lore_claims"] = []
            flags = _session().world_state.setdefault("flags", {})
            if len(created_npcs) == 1:
                talk_mode.open(_session().world_state, created_npcs[0].get("id"), turn=flags.get("turn_index", 0))

            accepted_proposal_keys, rejected_proposal_names = _bind_world_update_mentions(
                raw_updates,
                location_updates,
                validated_updates,
                _session().world_state,
            )
            if isinstance(packet.get("narration"), str):
                packet["narration"] = _filter_unaccepted_proposal_mentions(
                    packet["narration"],
                    accepted_proposal_keys,
                    rejected_proposal_names,
                )

        if resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "failed":
            packet["valid_response"] = False
            packet["narration"] = _fallback_for_action_result(player_input, resolved_turn.action_result)

        proposal_changes = _changed_state_fields(proposal_snapshot)
        resolved_turn.action_result["state_changes"] = list(dict.fromkeys(
            resolved_turn.action_result.get("state_changes", []) + proposal_changes
        ))

        if resolved_turn.quest_world_before and resolved_turn.action_result.get("action") == "travel" and resolved_turn.action_result.get("status") == "completed":
            post_travel_quests = _session().evaluate_quest_events(
                resolved_turn.quest_world_before, resolved_turn.action_result
            )
            if post_travel_quests:
                resolved_turn.action_result["quest_outcomes"] = post_travel_quests

    # A narration-only turn cannot propose, so a marker there names nothing new;
    # the sentence stays and only the marker goes.
    packet["narration"] = _repair_internal_marks(packet.get("narration"))
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
    lore_unsupported = not _lore_claims_are_supported(claims, lore_context)
    if not lore_unsupported and _narration_has_unsupported_lore_claim(
        packet.get("narration"), claims, lore_context, _session().world_state,
    ):
        # Repair before replacing: keep every sentence the guard accepts.
        repaired_lore = _repair_unsupported_lore_narration(
            packet.get("narration"), claims, lore_context, _session().world_state,
        )
        if repaired_lore:
            packet["narration"] = repaired_lore
        else:
            lore_unsupported = True
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
    finalized_narration = finalize_narration(
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
    if resolved_turn.action_result.get("action") == "narrative_spell" and isinstance(packet.get("item_claims"), list):
        # D-067: the cast moved nothing, so a thing the narrator says changed hands is never committed: its sentence
        # leaves first (the rest of the line stays), and a line that was all claim is the Python line.
        import pocket
        for claim in packet["item_claims"]:
            finalized_narration = pocket.without_claim(_session().world_state, claim, finalized_narration)
        finalized_narration = finalized_narration or resolved_turn.fallback_response
    import spell_effects
    if (resolved_turn.action_result.get("action") == "narrative_spell"
            and spell_effects.claims_state_change(finalized_narration)):
        # 4C.5: the engine wrote only the spell fact; a line claiming coin, an item, healing or damage is not shown.
        packet["valid_response"] = False
        packet["fallback_reason_code"] = "NARRATIVE_SPELL_STATE_CLAIM"
        finalized_narration = resolved_turn.fallback_response
    if _narrated_money_can_lie(resolved_turn.action_result) and isinstance(packet.get("item_claims"), list):
        # Settled on the line the player will read: a sentence the safety pass took leaves no item behind.
        import pocket
        import town_knowledge
        try:
            for claim in packet["item_claims"][:2]:
                finalized_narration = pocket.settle_claim(_session(), claim, finalized_narration, npc_target,
                                                          line=player_input)[0]
        except Exception:
            town_knowledge.log_failure()
        finalized_narration = finalized_narration or pocket.EMPTY_HANDED
    if rejected_scene_detail_proposal:
        finalized_narration = resolved_turn.fallback_response
    if (
        resolved_turn.action_result.get("scene_look")
        and getattr(_session(), "last_narration_safety", {}).get("handling") not in ("accepted", "repaired")
    ):
        finalized_narration = resolved_turn.fallback_response
    finalized_narration = _keep_people_in_look(finalized_narration, resolved_turn.action_result)
    finalized_narration = _states_the_failed_check(finalized_narration, resolved_turn.action_result, player_input)
    if _narration_scene_type(resolved_turn.action_result) != "conversation":
        finalized_narration = _singular_narrator(finalized_narration)

    final_dict = resolved_turn.raw_result
    final_dict["narration"] = finalized_narration

    safety_diag = getattr(_session(), "last_narration_safety", {}) or {}
    validation_result = safety_diag.get("handling", "accepted")
    fallback_reason = safety_diag.get("reason_code") or packet.get("fallback_reason_code")

    shown_player_line = packet.get("player_line")
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

    if validation_result in ("python_memory_response", "python_memory_fallback"):
        narration_source = "python_memory_response"
    elif validation_result in ("accepted", "repaired") and packet.get("valid_response", True) and packet.get("narration"):
        narration_source = "qwen"
    else:
        narration_source = "deterministic_fallback"

    if narration_source == "qwen":
        _keep_town_portrait(resolved_turn.action_result, finalized_narration)

    intent_calls = resolved_turn.intent_model_calls
    total_calls = intent_calls + narration_model_calls + emergence["model_calls"]

    if "_engine_event_evidence" in final_dict:
        before_set = final_dict["_engine_event_evidence"].pop("_procedural_ids_before", set())
        final_dict["_engine_event_evidence"]["procedural_entity_ids"] = sorted(
            _current_procedural_entity_ids() - before_set
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

    return final_dict






def _owner_module_reply(player_input, interaction_mode):
    """Slash-owner commands stay on their modules. SAY and ASK_DM stay speech."""
    text = player_input.strip() if isinstance(player_input, str) else ""
    if interaction_mode in {"say", "ask_dm"} and not text.startswith("/"):
        return None
    session = _session()
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
        return execute_intent(*args, **kwargs)

    interaction_mode = _normalize_interaction_mode(interaction_mode)
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
    held_reading = getattr(_session(), "_front_reply", None) is not None
    reading_calls = int(held_reading and getattr(_session(), "_front_reply_called", False))
    speech_intent_calls = 0

    def told_intent_calls():
        if not held_reading:
            return intent_model_calls
        return reading_calls + speech_intent_calls
    world_state = _session().world_state
    entry_death_state = ensure_death_state()
    entry_combat = ensure_combat_state()
    entry_identity = entry_combat.get("combat_id") if entry_combat["active"] else None
    entry_actor = entry_combat.get("current_actor_id")
    if entry_death_state["dead"]:
        raise PlayerCannotAct("Ölü karakter eylem gerçekleştiremez.")
    if _session().character.get("current_hp", 0) == 0 and not entry_combat["active"]:
        return _down_outside_combat_turn(player_input)
    if (
        _session().character.get("current_hp", 0) <= 0
        or world_state.get("player_combat_status") == "unconscious"
    ) and not (
        entry_combat["active"]
        and entry_combat["current_actor_id"] == "player"
    ):
        raise PlayerCannotAct("Bilinçsiz karakter eylem gerçekleştiremez.")
    local_npc_place_request = (
        interaction_mode != "ask_dm"
        and local_dialogue.is_local_place_recommendation_request(player_input)
        and _has_active_local_npc_focus_for_place_request(
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
        messages = _session().messages
    scene_plan = (
        scene_plan
        if isinstance(scene_plan, dict)
        else plan_living_world_turn(
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
        and _scene_observation_proposal_turn(
            player_input, world_state, interaction_mode
        )
    ):
        scene_plan = {**scene_plan, "direct_result": None}
    injected_lore_context = getattr(_session(), "lore_authority_context", None)
    lore_context = _prepare_lore_authority_context(injected_lore_context)
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
            narration = _natural_unresolved_action_response(player_input, action_result)
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
                _session(), action_result, quest_world_before, player_input
            )
            interaction_consumed = True
            if action_result.get("action") in {"query", "explore"}:
                beat = interaction_adventure.initiative_beat(world_state)
                if beat:
                    action_result["npc_initiative"] = beat
                    narration = narration + " " + beat["summary"]
        if isinstance(action_result, dict) and action_result.get("action") in {"attack", "death_save"}:
            current = ensure_combat_state()
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
        if _is_internal_player_facing_text(narration):
            narration = _natural_unresolved_action_response(
                player_input, action_result
            )
            if (
                isinstance(action_result, dict)
                and _is_internal_player_facing_text(
                    action_result.get("direct_response")
                )
            ):
                action_result["direct_response"] = narration
        if record_safety:
            _record_narration_safety(
                {
                    "reason_code": safety_reason_code,
                    "trigger_span": None,
                    "scene_type": _narration_scene_type(action_result),
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
                _session(),
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

        resolved = ResolvedTurn(
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
        raise TurnResolved(result, resolved)

    import spell_effects
    spell_reading = (spell_effects.named(player_input)
                     if interaction_mode not in {"say", "ask_dm"} and isinstance(player_input, str)
                     and _session().character.get("current_hp", 0) > 0 else None)  # a body on the ground saves
    if spell_reading is not None:
        # 4C.5: the engine decides and commits (a fact, or a truthful line that nothing was cast); a resolved fact goes
        # to the turn narrator (narration only, the line is its fallback), a refusal is told as it is.
        cast = spell_effects.resolve(_session(), spell_reading)
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
            record_npc_interaction(target, text, player_input, target)
            _remember_accepted_profile_focus(
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
        if combat_lifecycle.quoted_report(_session(), player_input):
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
    said_after = _said_after_approach(player_input)
    if (isinstance(walked_up, dict) and walked_up.get("action") == "approach"
            and walked_up.get("status") == "completed" and said_after
            and interaction_mode not in {"say", "ask_dm"}):
        spoken = _run_player_turn_internal(
            said_after, messages, walked_up.get("target_id"), None, "say", action_id
        )
        spoken["narration"] = f"{walked_up['direct_response']} {spoken['narration']}"
        return spoken
    sleeping = bool(timed_gameplay._SLEEPING.search(_normalize_turkish_typos(player_input))
                    or timed_gameplay.is_timed_wait(player_input))
    # A blow the reading found lands now, however many clauses lead up to it: it is no plan to keep.
    compound = (None if sleeping or getattr(_session(), "_front_strike", None)
                else interaction_adventure.compound_plan(player_input))
    # "Marek'in yanına gidiyorum, bir bira istiyorum": the second clause is said to him.
    import grounded_action
    request = grounded_action.spoken_request(player_input) if compound is not None else None
    if request and not entry_combat["active"] and interaction_mode not in {"say", "ask_dm"}:
        named = resolve_npc_reference(player_input)
        if named.get("status") == "found":
            _set_scene_active_npc(named["npc"], flags.get("turn_index", 0) + 1)
        person = next(
            (npc for npc in active_npcs() if npc.get("id") == flags.get("active_npc_id")), None
        )
        if person is not None:
            living_world.set_player_position(
                world_state, world_state.get("location"), "standing", person["id"]
            )
            return _run_player_turn_internal(
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
        action_result = interaction_adventure.resolve(_session(), player_input, compound)
        # Recording intentions is not executing them, but the player still gets
        # the attempt narrated; the prose cannot move anyone or change anything.
        fallback = action_result.pop("direct_response", "")
        return finish_turn(action_result, fallback)

    ensure_campaign_clock()
    if scene_plan is None and interaction_mode not in {"say", "ask_dm"} and held_plan is None:
        # The API plans first. Direct turns use the same local-entry owner. A held plan walks nowhere before its reading.
        if (
            living_world.classify_scene_action(player_input) == "enter"
            or _names_current_local_exit(player_input)
        ):
            scene_plan = plan_living_world_turn(
                player_input,
                target_id=target_id,
                interaction_mode=interaction_mode,
            )
    if ("campaign_time" in world_state and not ensure_combat_state()["active"]
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
            else timed_gameplay.resolve_input(_session(), player_input)
        )
        if timed_result is not None:
            return finish_turn(
                timed_result, timed_result["direct_response"], is_final=True
            )

    combat = ensure_combat_state()
    if (
        combat["active"]
        and combat["current_actor_id"] == "player"
        and _session().character.get("current_hp", 0) <= 0
    ):
        death = ensure_death_state()
        if death["stable"]:
            _mark_combat_action_used("player")
            enemy_actions = []
            if not _combat_end_if_decided():
                advanced, _, _ = advance_combat_turn()
                if advanced:
                    enemy_actions = _resolve_enemy_turns_until_player()
            combat = ensure_combat_state()
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
                    (f"Bilincin kapalı, kanın durdu; çatışma sensiz sürüyor. {_enemy_exchange_text(enemy_actions)}").split()
                ),
            }
            resolution = _death_resolution_from_actions(enemy_actions)
            if resolution:
                action_result["death_resolution"] = resolution
            return finish_turn(
                action_result, action_result["direct_response"], is_final=True
            )

        save_result = _resolve_player_death_turn()
        if save_result is not None:
            enemy_actions = []
            combat = ensure_combat_state()
            # Match the scheduler's newly-stable boundary: preserve this
            # player slot rather than starting another enemy cycle.
            if ensure_death_state()["stable"]:
                _combat_end_if_decided()
            elif save_result["outcome"] != "revived" and combat["active"] and combat["current_actor_id"] == "player":
                _mark_combat_action_used("player")
                if not _combat_end_if_decided():
                    advanced, _, _ = advance_combat_turn()
                    if advanced:
                        enemy_actions = _resolve_enemy_turns_until_player()
            combat = ensure_combat_state()
            resolution = (
                save_result.get("death_resolution")
                or _death_resolution_from_actions(enemy_actions)
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
                "direct_response": _death_save_line(save_result, enemy_actions, resolution),
            }
            if resolution:
                action_result["death_resolution"] = resolution
            return finish_turn(
                action_result, action_result["direct_response"], is_final=True
            )

    if combat["active"] and combat["current_actor_id"] != "player":
        enemy_actions = _resolve_enemy_turns_until_player()
        combat = ensure_combat_state()
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
        quest_transitions = _session().evaluate_quest_events(
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
            resolve_location_reference(current_loc)
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
        world_meta = getattr(_session(), "world_metadata", None)
        env_meta = world_meta.get("environment") if isinstance(world_meta, dict) else None

        is_city_scene = not is_non_city and (
            current_kind == "city"
            or resolved_kind == "city"
            or anchor_kind == "city"
            or _is_canonical_city_id(current_loc)
            or _is_canonical_city_id(resolved_loc)
            or _is_canonical_city_id(anchor_id)
            or _is_canonical_city_id(loc_record.get("id"))
            or _is_canonical_city_id(loc_record.get("canonical_entity_id"))
            or _is_canonical_city_id(loc_record.get("lore_entity_id"))
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
        if scene_plan.get("action") == "look" and _look_scene_changed():
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
        known_character_answer(player_input)
        if not combat["active"] and interaction_mode != "say"
        else None
    )
    focused_npc_before_targeting = _active_interlocutor()
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
            (npc for npc in (_conversation_npcs() if interaction_mode == "say" else active_npcs())
             if isinstance(npc, dict) and npc.get("id") == target_id), None,
        ) if not combat["active"] else None
        if not combat["active"] and (
            interaction_mode == "say"
            or not world_subject_question
            or local_dialogue.is_local_dialogue_input(player_input)
            or (_npc_speech_enabled() and interaction_mode in {None, "do", "say"}
                and is_npc_dialogue_input(player_input))
            or _is_spoken_to(player_input, selected_npc_target)
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
                    npc for npc in (_conversation_npcs() if interaction_mode == "say" else active_npcs())
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
            resolve_npc_reference(
                player_input,
                force_dialogue=True,
                allow_active_fallback=False,
            )
            if (interaction_mode == "say" or (interaction_mode in {None, "do"} and _npc_speech_enabled()))
            and (world_subject_question or scene_exploration_question)
            else {"status": "none", "npc": None}
        )
        if (interaction_mode != "say"
                and explicit_dialogue_resolution["status"] == "found"
                and not _is_spoken_to(player_input, explicit_dialogue_resolution["npc"])):
            explicit_dialogue_resolution = {"status": "none", "npc": None}
        if (
            explicit_dialogue_resolution["status"] == "none"
            and _npc_speech_enabled()
            and interaction_mode in {None, "do", "say"}
            and focused_npc_before_targeting is not None
            and is_npc_dialogue_input(player_input)
        ):
            focused_resolution = resolve_npc_reference(player_input, force_dialogue=True)
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
                and resolve_npc_reference(
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
                interaction_mode == "say" or is_npc_dialogue_input(player_input)
            )
            npc_resolution = resolve_npc_reference(
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
            and not _detect_query_type(player_input)
            and not known_character_answer(player_input)
            and not _is_player_name_inquiry_to_npc(player_input)
            and not local_dialogue.personal_question_kind(player_input)
            and interaction_mode != "ask_dm"
            and is_npc_dialogue_input(player_input)
            # The pre-parse can only pick a visible person or propose a local
            # one; with neither possible it cannot change this turn.
            and (
                _intent_scene_npc_candidates()
                or should_generate_npcs(player_input)
            )
        ):
            preparsed_scene_intent = parse_player_intent(
                player_input,
                interaction_context=interaction_adventure.context(
                    world_state, None, player_input
                ),
                recent_scene_narration=_recent_player_visible_narration(),
                allow_scene_detail_proposals=_scene_detail_proposals_allowed(
                    player_input, world_state, interaction_mode
                ),
                allow_local_person_proposal=should_generate_npcs(player_input),
                strict=check_feature is not None,
            )
            scene_preparse_model_calls = 1
            intent_model_calls = scene_preparse_model_calls
            intent_source = "model"
            classifier_unusable = bool(preparsed_scene_intent.get("classifier_unusable"))
            selected_npc = _validated_scene_npc_id(
                preparsed_scene_intent, player_input
            )
            if selected_npc is None and _named_word_of(preparsed_scene_intent):
                _session()._named_word = _named_word_of(preparsed_scene_intent)
            if selected_npc is not None:
                canonical_npc = next(
                    (
                        npc for npc in active_npcs()
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
            and not _validated_local_person_proposal(preparsed_scene_intent or {})
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
                _promote_scene_referent(deferred_referent, current_location)
                if deferred_referent is not None else None
            )
            if promoted_npc:
                _set_scene_active_npc(promoted_npc, flags.get("turn_index", 0))
                npc_resolution = {"status": "found", "npc": promoted_npc}
                # As when the planner promoted: a rejected proposal keeps this person's talk.
                active_conversation_before = talk_mode.snapshot(world_state)
        if (
            dialogue_fallback_deferred
            and npc_resolution.get("status") == "none"
            and interaction_mode != "ask_dm"
            and not _is_negated_dialogue_action(player_input)
            and not _validated_local_person_proposal(preparsed_scene_intent or {})
            and not local_dialogue.unresolved_named_address(
                player_input, _conversation_npcs()
            )
        ):
            # Preserve the existing "say hello to the only visible person"
            # behavior when the model did not resolve an explicit description.
            npc_resolution = resolve_npc_reference(
                player_input, force_dialogue=True, allow_active_fallback=True
            )
        if npc_resolution.get("nobody_here"):
            _nobody_here(npc_resolution["nobody_here"])
        if npc_resolution["status"] == "ambiguous" and not character_reply:
            if (
                interaction_mode not in {"say", "ask_dm"}
                and held_plan is None  # a blow inside clauses held for the reading is still part of the plan
                and _has_explicit_attack_verb(player_input)
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
            npc_resolution = _settle_address(npc_resolution, player_input)
        if npc_resolution.get("absent") and interaction_mode != "ask_dm" and not combat["active"]:
            return finish_turn(
                {"action": "dialogue", "status": "invalid_target", "success": False, "state_changes": []},
                _absent_person_text(npc_resolution["absent"]),
                is_final=True,
            )
        npc_target = npc_resolution.get("npc") if npc_resolution["status"] == "found" else None

    if (
        target_id is None
        and (
            interaction_mode == "say"
            or (interaction_mode in {None, "do"} and should_generate_npcs(player_input))
        )
        and npc_target is not None
        and preparsed_scene_intent is None
        and not (
            focused_npc_before_targeting is not None
            and npc_target.get("id") == focused_npc_before_targeting.get("id")
            and not should_generate_npcs(player_input)
        )
        and is_npc_dialogue_input(player_input)
        and not local_dialogue.personal_question_kind(player_input)
        and not resolve_npc_reference(
            player_input, force_dialogue=False, allow_active_fallback=False
        ).get("npc")
    ):
        # A sole-NPC fallback is useful for "Merhaba", but must not override a
        # player-specified description of someone absent from the current scene.
        preparsed_scene_intent = parse_player_intent(
            player_input,
            interaction_context=interaction_adventure.context(
                world_state, None, player_input
            ),
            recent_scene_narration=_recent_player_visible_narration(),
            allow_scene_detail_proposals=_scene_detail_proposals_allowed(
                player_input, world_state, interaction_mode
            ),
                allow_local_person_proposal=should_generate_npcs(player_input),
                strict=check_feature is not None,
        )
        scene_preparse_model_calls = 1
        intent_model_calls = scene_preparse_model_calls
        intent_source = "model"
        classifier_unusable = bool(preparsed_scene_intent.get("classifier_unusable"))
        named_word = _named_word_of(preparsed_scene_intent)
        if named_word and _validated_scene_npc_id(preparsed_scene_intent, player_input) is None:
            # The reading names someone who is not here: the fallback's person does not answer for them
            _session()._named_word = named_word
            _nobody_here(named_word)
            npc_target = None

    if (
        target_id is None
        and (
            npc_target is None
            or _validated_local_person_proposal(
                preparsed_scene_intent or {}
            )
        )
        and isinstance(locals().get("preparsed_scene_intent"), dict)
    ):
        local_proposal = _validated_local_person_proposal(
            preparsed_scene_intent
        )
        if local_proposal and should_generate_npcs(player_input):
            npc_target = None
            request_key = _local_person_request_key(player_input)
            existing_ids = {
                npc.get("id")
                for npc in world_state.get("npcs", [])
                if isinstance(npc, dict)
            }
            accepted_npc = None
            if not is_player_world_assertion(player_input):
                accepted_npc = create_npc_from_ai(
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

    unresolved_address = local_dialogue.unresolved_named_address(player_input, active_npcs())
    front_talk = talk_front.current(_session())
    named_reading = (talk_front.spoken_to(front_talk, active_npcs())
                     if unresolved_address and target_id is None and not combat["active"] else None)
    if named_reading is not None and not talk_front.old_owner_allowed(front_talk, "unknown_name"):
        npc_target = named_reading  # the reading names a listed person: the line is for them, speech answers
    elif unresolved_address and target_id is None and not combat["active"]:
        npc_target = None
        result = {"action": "dialogue", "status": "invalid_target", "success": False, "state_changes": []}
        return finish_turn(
            result,
            _elsewhere_line(world_state, unresolved_address)
            or f"Burada {unresolved_address} adıyla tanıdığın biri görünmüyor.",
            is_final=True,
        )
    if npc_target is None and interaction_mode == "ask_dm" and not combat["active"]:
        # BM Task 3: asked of the DM, a plain-talk reading that names a listed person is the line for them
        npc_target = talk_front.spoken_to(front_talk, active_npcs())

    # "Özpil nerede?", or Konuş with no one to say it to: a person the town named is somewhere real.
    asks_for_someone = interaction_mode == "say" or re.search(r"\bner(?:e)?de\b", _normalize_turkish_typos(player_input))
    elsewhere = (_named_elsewhere_line(world_state, player_input)
                 if npc_target is None and asks_for_someone and not combat["active"] else None)
    if elsewhere:
        result = {"action": "dialogue", "status": "invalid_target", "success": False, "state_changes": []}
        return finish_turn(result, elsewhere, is_final=True)

    if interaction_mode == "say" and npc_target is None:
        result = {
            "action": "dialogue", "status": "clarification", "success": False,
            "state_changes": [],
        }
        nobody = "Burada konuşabileceğin kimse yok." if not active_npcs() else None
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
        _topic_place_name(world_state)
        if (local_dialogue.asks_the_name_of_a_topic(player_input) and interaction_mode != "ask_dm"
            # BM Task 2: a plain-talk reading means the person answers by speech; the name line is the fallback
            and talk_front.old_owner_allowed(talk_front.current(_session()), "place_name"))
        else None
    )
    if topic_name:
        answer = (
            f'{living_world.public_npc_name(npc_target)}, “{topic_name} derler,” diye yanıt verir.'
            if npc_target else f"Adı {topic_name}."
        )
        if npc_target:
            record_npc_interaction(npc_target, answer, player_input, npc_target)
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
        _detect_query_type(player_input, npc_target) == "location"
        and not (npc_target and interaction_mode == "say")
    ):
        query_response = _handle_query(player_input, "location", npc_target)
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
        and combat_lifecycle.is_attack_decision(_session(), player_input)
    ):
        # The turn's own reading may name the weapon (Task 14's `weapon_word`): it goes only to the catalog (gear).
        read = getattr(_session(), "_front_reply", None)
        word = read.get("weapon_word") if isinstance(read, dict) else None
        action_result = resolve_intent(
            {"intent": "attack", **({"weapon_word": word.strip()[:40]} if isinstance(word, str) and word.strip() else {})},
            player_input,
            npc_target=npc_target,
            target_id=target_id,
        )
        quest_transitions = _session().evaluate_quest_events(
            quest_world_before, action_result
        )
        if quest_transitions:
            action_result["quest_outcomes"] = quest_transitions
        return finish_turn(
            action_result,
            _combat_narration(action_result),
            quest_transitions,
            is_final=True,
        )

    # Concrete possession changes outrank an abstract 'abandon' proposal.
    # Restrict this bypass to unambiguous present-tense commands; all other
    # equipment operations remain with the existing Python inventory owner.
    if (interaction_mode not in {"say", "ask_dm"}
            and target_id is None and not combat["active"]
            and _explicit_sword_drop(player_input)):
        action_result = resolve_intent({"intent": "inventory"}, player_input)
        return finish_turn(
            action_result,
            action_result.get("direct_response") or _fallback_for_action_result(
                player_input, action_result
            ),
            is_final=True,
        )

    thread_talk = _job_talk_with(npc_target)
    interaction_hint = (
        None if interaction_mode == "ask_dm" or thread_talk
        or combat_lifecycle.quoted_report(_session(), player_input)
        else interaction_adventure.hint(player_input, npc_target)
    )
    if interaction_hint == "plan" and (getattr(_session(), "_front_read", None) or {}).get("kind") == "speak_to":
        interaction_hint = None  # two clauses said to a person are no plan to keep: they answer them
    if target_id is None and not combat["active"] and _turns_to_someone_else(player_input):
        others = [npc for npc in _conversation_npcs()
                  if not isinstance(npc_target, dict) or npc.get("id") != npc_target.get("id")]
        if others:
            npc_target = most_plausible_addressee(others, player_input)
            _session()._set_scene_active_npc(npc_target, world_state.get("flags", {}).get("turn_index", 0))
    if (
        interaction_hint in {"information", "generate"} and target_id is None
        and (interaction_hint == "generate" or local_dialogue.personal_question_kind(player_input) == "local_work")
        and _town_in_play(world_state)
    ):
        # Whoever is here answers from what they know; no proposal is needed to find a town's work.
        interaction_hint = None
        if npc_target is None:
            npc_target = most_plausible_addressee(_conversation_npcs(), player_input)
    raw = None
    answer_in_person = False
    if interaction_hint and not combat["active"] and not classifier_unusable:
        intent_model_calls = scene_preparse_model_calls + 1
        intent_source = "interaction_proposal"
        raw = parse_player_intent(
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
        hearer = _said_to_someone_here(_session(), raw)
        if hearer is None:
            # Not said to anyone here: the clauses are the player's own plan, recorded as before. A reading already
            # spent is this turn's one call, so the plan's own line is told without a narrator call.
            intent_source = "python_compound_plan"
            action_result = interaction_adventure.resolve(_session(), player_input, held_plan)
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
                            and (getattr(_session(), "_front_reply", None) is not None
                                 or (interaction_hint in {"information", "generate"}
                                     and _people_speak_for_themselves(world_state))))
        if conversation_rejected and not answer_in_person:
            return finish_conversation_rejection(npc_target)
        action_result = (
            {"status": "proposal_rejected"} if answer_in_person else interaction_adventure.resolve(
                _session(), player_input, raw.get("interaction"), npc_target,
                fallback_operation=interaction_hint,
            )
        )
        if action_result.get("status") == "proposal_rejected" and _has_spoken_to_player(npc_target):
            # Someone mid-conversation answers for themselves; a stock "I know nothing" disowns their own words.
            answer_in_person = True
        if action_result.get("status") == "unbacked" and isinstance(npc_target, dict):
            answer_in_person = True  # D-249 F2: nothing backs the answer, so it is theirs to give, not a stock line
        if (action_result.get("status") in {"proposal_rejected", "no_effect"} and isinstance(npc_target, dict)
                and (getattr(_session(), "_front_read", None) or {}).get("kind") == "speak_to"):
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
                    and target_id is None and _explicit_campaign_shop_request(player_input))
    shop_count_before = len(world_state.get("shops", []))
    current_shop_count = sum(
        1 for shop in world_state.get("shops", [])
        if isinstance(shop, dict) and shop.get("location") == world_state.get("location")
    )
    if shop_request and (
        _campaign_has_shopkeeper()
        or len(world_state.get("shops", [])) >= 12
        or current_shop_count >= 3
        or len(world_state.get("npcs", [])) >= 60
        or len(active_npcs(world_state.get("location"))) >= 6
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

        action_result = shop_creation.resolve_explicit_request(_session())
        return finish_turn(
            action_result, action_result["direct_response"],
            is_final=not action_result["success"],
        )

    if (interaction_mode not in {"say", "ask_dm"}
            and world_state.get("shops") and _shop_economy_request(player_input)):
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
            and _explicit_campaign_shop_negative_request(player_input)):
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

    if (_shop_presence_question(player_input)
            and ((target_id is None and not isinstance(npc_target, dict)
                  and (getattr(_session(), "_front_read", None) or {}).get("kind") != "speak_to")
                 # asked of the one who keeps the shop here, the shop line is her answer (Review 11 A4)
                 or (isinstance(npc_target, dict) and npc_target.get("location") == world_state.get("location")
                     and _runs_a_shop(world_state, npc_target)
                     # BM Task 2: a plain-talk reading answers by speech; the list only when it asks for the shop
                     and talk_front.old_owner_allowed(talk_front.current(_session()), "shop_presence")))):
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
        and _is_historical_player_name_query(player_input)
        and not _explicit_player_name_disclosure(player_input)
    ):
        remembered_name = (
            _historical_player_name_from_npc_memory(npc_target, player_input)
            or _historical_player_name_from_claims(
                npc_target,
                player_input,
                getattr(_session(), "_supported_player_claims", None),
            )
        )
        npc_name = living_world.public_npc_name(npc_target)
        is_hitap = bool(re.search(r"\b(?:ad[ıi]mla|ismimle)\s+hitap\b", _normalize_turkish_typos(str(player_input).casefold())))
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
        record_npc_interaction(
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

    disclosed_name = _explicit_player_name_disclosure(player_input)
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
                talk_front.current(_session()), "name_disclosure") or _known_player_name(npc_target) == safe_name or (
                local_dialogue.has_multiple_dialogue_clauses(player_input, npc_target)
                # E9: a question Python cannot answer goes to speech; "who are you" Python answers itself.
                and (_npc_speech_enabled() or (interaction_adventure._asks(player_input)
                                               and _detect_query_type(player_input, npc_target) != "npc_identity"))
            )
            if compound_speech and _known_player_name(npc_target) != safe_name and not talk_front.old_owner_allowed(
                    talk_front.current(_session()), "name_disclosure"):
                intro_fallback_name = safe_name
            if compound_speech:
                local_dialogue.remember_explicit_player_name(npc_target, safe_name)
            if compound_speech and _detect_query_type(player_input, npc_target) == "npc_identity":
                # The player requested this identity. Python decides disclosure;
                # the model receives the now-public name, not hidden identity.
                _handle_query(player_input, "npc_identity", npc_target)
            if not compound_speech:
                npc_name = living_world.public_npc_name(npc_target)
                reply = local_dialogue.introduction_reply(world_state, npc_target, safe_name)
                narration = f'{npc_name}: “{reply}”'
                # A single utterance may introduce the player AND ask who the
                # addressee is. Both answers come from verified Python state.
                if _detect_query_type(player_input, npc_target) == "npc_identity":
                    identity_reply = _handle_query(player_input, "npc_identity", npc_target)
                    if identity_reply:
                        narration += " " + identity_reply
                action_result = {
                    "action": "dialogue",
                    "status": "player_name_disclosed",
                    "success": True,
                    "npc_id": npc_target["id"],
                    "state_changes": ["npcs.memory"],
                }
                record_npc_interaction(
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
        query_type = _detect_query_type(player_input, npc_target)
        if query_type == "npc_identity" and local_dialogue.is_identity_only_question(player_input, npc_target):
            query_response = _handle_query(
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
                record_npc_interaction(
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
        offers = _session().quest_offers()
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
        response = _overheard_work(world_state) or work_answer[0]
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
        and is_npc_historical_claim(player_input)
        and not _reported_npc_claim_followed_by_player_inspection(player_input)
        and not _report_of_someone_else(player_input, npc_target)
    ):
        named_npc = _resolve_campaign_npc_reference(player_input, world_state)
        claimed_npc = (named_npc if isinstance(named_npc, dict) and named_npc.get("location") != world_state.get("location")
                       else None) or npc_target or named_npc
        if npc_target is None and _has_spoken_to_player(claimed_npc) and (
                claimed_npc.get("location") == world_state.get("location")):
            npc_target = claimed_npc  # the claim is about what this person said, and they are standing here
        supported_entry = (
            npc_memory_supporting_entry(claimed_npc, player_input)
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
                 or about == "npc_words" and _SECOND_PERSON_SAID.search(_normalize_turkish_typos(player_input)))
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
            record_npc_interaction(claimed_npc, response, player_input, claimed_npc)
            return finish_turn(
                action_result,
                response,
                safety_reason_code="NPC_MEMORY_SUPPORTED_CLAIM",
                safety_handling="python_memory_response",
            )
        else:
            if claimed_npc and claimed_npc.get("location") == world_state.get("location"):
                response = historical_claim_denial(claimed_npc, player_input)
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
                record_npc_interaction(claimed_npc, response, player_input, claimed_npc)
            return finish_turn(
                action_result,
                response,
                safety_reason_code="NPC_MEMORY_UNSUPPORTED_CLAIM",
                safety_handling="python_memory_response",
            )

    supported_lore_response = _supported_lore_question_response(
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
            "discovered_fact_ids": _spoken_lore_fact_ids(
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
        or _report_of_someone_else(player_input, npc_target)
        or npc_place_recommendation
        or is_npc_dialogue_input(player_input)
        or local_dialogue.personal_question_kind(player_input) == "local_work"  # "burada ... var mı" also reads as a look
        or _is_short_conversation_continuation(player_input)
        or _is_spoken_to(player_input, npc_target)
        or _asked_of_the_one_at_hand(player_input, npc_target)
    ))
    profile_focus = interaction_adventure.current_conversation_focus(world_state, npc_target)
    canonical_profile_question = (
        local_dialogue.personal_question_kind(player_input)
        in interaction_adventure.PROFILE_FIELD_BY_MEANING.values()
        or (_is_short_followup(player_input) and profile_focus
            and profile_focus.get("predicate") in interaction_adventure.PROFILE_FIELD_BY_MEANING.values())
    ) and not local_dialogue.has_multiple_dialogue_clauses(player_input, npc_target)
    experimental_dialogue_session = npc_dialogue_route and (
        # BM Task 3: the model read a plain talk line to this person: they answer by speech, even asked of the DM
        (isinstance(npc_target, dict) and not talk_front.old_owner_allowed(front_talk, "personal"))
        or (interaction_mode != "ask_dm"
            and (_npc_speech_enabled() or experimental_unverified_claim or not canonical_profile_question))
    )
    lore_safety_input = player_input
    if npc_place_recommendation:
        # A resolved, visible addressee is not an unsupported lore entity.
        # Remove only that person/role from the lore scan; other named claims
        # in the same request remain subject to the ordinary fail-closed gate.
        lore_safety_input = _lore_guard_text(player_input)
        for reference in (
            living_world.public_npc_name(npc_target),
            living_world.public_npc_role(npc_target),
        ):
            normalized_reference = _lore_guard_text(reference or "")
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
        or _player_question_has_unverified_lore_claim(
            lore_safety_input, lore_context, world_state
        )
    )
    if (lore_gate and interaction_mode != "ask_dm" and not combat["active"]
            and _people_speak_for_themselves(world_state)
            and not _ASKS_DISTANCE.search(local_dialogue.normalize_text(player_input))):
        # Asked aloud with someone standing there, the town's talk is theirs to answer, not the street's.
        here = _conversation_npcs()
        npc_target = _explicit_addressee(player_input, here) or npc_target or most_plausible_addressee(here, player_input)
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
            _unverified_lore_response(player_input, npc_target),
            safety_reason_code="UNVERIFIED_LORE_CLAIM",
            safety_handling="python_fallback",
        )

    smalltalk_response = _direct_npc_smalltalk_response(player_input, npc_target)
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
        conversation_start = _is_conversation_start_input(player_input)
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
        record_npc_interaction(
            npc_target, smalltalk_response, player_input, npc_target
        )
        _remember_owner_locked_tavern_focus(
            player_input, npc_target, action_id
        )
        if (
            personal
            or conversation_start
            or living_world.is_tavern_search(player_input)
            or _is_local_place_question(player_input)
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
            _npc_name_stance(world_state, npc_target, player_input)
            if experimental_npc_dialogue else None
        )
        if name_stance == "reveal":
            npc_target["name_known_to_player"] = True
        raw_intent = parse_player_intent(
            player_input,
            interaction_context=(
                _experimental_npc_dialogue_context(
                    world_state, npc_target,
                    unverified_claim=experimental_unverified_claim,
                    followup=_is_short_followup(player_input),
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
                _experimental_speech_note(world_state, npc_target, name_stance, player_input)
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
                    and not _grounded_item_request_proposal(
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
            and is_npc_historical_claim(player_input)
            and npc_statements.claim_about(player_input) == "memory")
        # A profile/personal answer may take precedence, but cannot drop this veto.
        # Positive money answers gain no authority from a witness proposal.
        if witness_requested and raw_intent.get("coin_answer") == "declines":
            money_owner.read_answer(_session(), raw_intent, npc_target["id"],
                money_owner.parts_for(world_state, _session(), npc_target["id"]))
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
                record_npc_interaction(npc_target, response, player_input, npc_target)
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
            if _salvage_plain_speech(raw_intent):
                conversation_rejected = False
                conversation_resolution = None
            else:
                return finish_conversation_rejection(npc_target)
        if _interaction_proposal_applies(raw_intent, npc_target, player_input):
            if experimental_npc_dialogue:
                # The packet's speech stands; a proposal in it simply grants nothing.
                raw_intent = {**raw_intent, "interaction": None}
            else:
                action_result = interaction_adventure.resolve(
                    _session(), player_input, raw_intent["interaction"], npc_target,
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
                if told_support or spoken_reference or thread_talk or _report_of_someone_else(player_input, npc_target):
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
                    money_owner.read_answer(_session(), raw_intent, npc_target["id"],
                        money_owner.parts_for(world_state, _session(), npc_target["id"]))
                    asked = raw_intent.get("asks_for")
                    if isinstance(asked, str) and asked in money_owner.askable(world_state, npc_target):
                        _session()._asks_for = (npc_target["id"], asked)  # opened after the reply, if at all
                    import npc_speech_boundary
                    cleaned_spoken = _clean_npc_speech(
                        npc_speech_boundary.normalize_bound_speech_label(
                            raw_spoken, npc_target,
                            visible=any(n.get("id") == npc_target.get("id")
                                        for n in _conversation_npcs()),
                        )
                    )
                    if cleaned_spoken.strip():
                        cleaned_spoken = _ground_local_place_recommendation_reply(
                            cleaned_spoken,
                            npc_target,
                            world_state,
                            player_input,
                        )
                    cleaned_stage = _clean_npc_stage_direction(raw_stage)
                    cleaned_stage = _ground_local_place_recommendation_stage(
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
                    cleaned_stage = _shown_stage_direction(cleaned_stage, world_state)
                    if _is_explicit_name_led_gesture_line(cleaned_spoken, npc_target):
                        cleaned_spoken = ""
                        invalid_spoken_stage_direction = True
                    cleaned_spoken = _without_lines_already_said(
                        cleaned_spoken, npc_target, world_state, player_input
                    )
                    if recognised:  # re-review R1, RR2-1: recognition backs no added event, said or shown
                        if cleaned_spoken.strip():
                            cleaned_spoken = npc_statements.only_what_recognition_backs(
                                world_state, npc_target, player_input, cleaned_spoken)
                        if cleaned_stage.strip():
                            cleaned_stage = npc_statements.only_what_recognition_backs(
                                world_state, npc_target, player_input, cleaned_stage, stage=True)
                    settled_money = _settle_spoken_commitment(
                        world_state, npc_target, player_input, raw_intent.get("commitment"), cleaned_spoken,
                        threat=raw_intent.get("threat"), persuade=_coin_persuasion(action_result), stage=cleaned_stage,
                    )
                    cleaned_spoken = settled_money["spoken"]
                    cleaned_stage = settled_money["stage"]  # D-264: a coin ask cleans the gesture as it cleans the line
                    if getattr(_session(), "_empty_handed", False):
                        cleaned_stage = ""  # nothing was held out, so no gesture takes it
                    elif settled_money.get("unbacked"):
                        import pocket
                        cleaned_stage = pocket.without_said(cleaned_stage, settled_money["unbacked"])
                    if name_stance == "reveal" and cleaned_spoken.strip():
                        cleaned_spoken = _spoken_name_answer(cleaned_spoken, npc_target)
                    attributed_speech = {
                        # These authority fields are stamped by Python, never
                        # accepted from the model response.
                        "source": "experimental_attributed_speech",
                        "speaker_id": npc_target["id"],
                        "spoken_text": cleaned_spoken,
                        "stage_direction": cleaned_stage,
                    }
                    # W03: a known lock may be recalled by a SEPARATE narrator note; it never replaces the NPC's line.
                    place_note = _attributed_place_note(cleaned_spoken, npc_target, world_state, player_input)
                    if place_note:
                        attributed_speech["narrator_note"] = place_note
                    raw_narration = _compose_experimental_npc_speech(
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
                    text = _spoken_name_answer("", npc_target)
                elif intro_fallback_name:
                    text = local_dialogue.introduction_reply(world_state, npc_target, intro_fallback_name)
                else:
                    # D-325: what this person herself said is hers to repeat before any denial of the claim
                    import heard_rumours
                    own_rumour = heard_rumours.own_line(world_state, npc_target, player_input)
                    text = (_job_fallback(world_state) or own_rumour
                            or (experimental_unverified_claim and historical_claim_denial(npc_target, player_input)))
                    if own_rumour and text == own_rumour:
                        python_town_response = own_rumour
                        action_result["own_words"] = True  # what she told is hers: not an unrecorded claim, nothing granted
                    if not text:
                        town_reply = _town_fallback(world_state, npc_target, player_input)
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
                        not _npc_speech_is_claim_refusal(text)
                        # With no selected personal memory, an unrecognised factual
                        # answer is not evidence of refusal. Reuse the existing
                        # explicit refusal check; leave NPC-word ask-backs alone.
                        or (about != "npc_words" and not _npc_speech_rejects_claim(text))
                    )
                )
                if not invalid_or_empty and not unverified_history_echo:
                    action_result["own_words"] = True  # their own answer stands; nothing was granted
            else:
                unverified_history_echo = (
                    not invalid_or_empty
                    and not told_support
                    and _unverified_past_event_assertion(player_input)
                    and bool(_claim_keywords(text) & _claim_keywords(player_input))
                )
            if not invalid_or_empty and (
                unverified_history_echo
                or raw_intent.get("world_updates")
                or raw_intent.get("lore_claims")
                or not interaction_adventure.safe_narration(text)
            ):
                if experimental_unverified_claim:
                    text = historical_claim_denial(npc_target, player_input)
                else:
                    # D-249 F1: the person passes on a lead (job, town, place to ask) before any bare "I don't know".
                    text = _person_fallback(world_state, npc_target, player_input)
                    if text != interaction_adventure.immersive_unknown(npc_target, player_input):
                        python_town_response = text

            text_before_finalize = text
            text = finalize_narration(
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
            narration_safety = getattr(_session(), "last_narration_safety", None)
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
            stock_swapped = experimental_npc_dialogue and _is_stock(text)
            if stock_swapped:
                # A clear line never earns "say it again": the person answers from what Python has for them.
                text = _person_fallback(world_state, npc_target, player_input)
            elif (experimental_npc_dialogue and final_safety_handling == "python_fallback"
                    and not experimental_unverified_claim and action_result.get("action") != "skill_check"
                    and interaction_adventure._asks(player_input)):  # a greeting keeps the fallback's own answer
                # D-249 F1: a speech the safety check rejected is replaced by what the person has to say from Python
                # (job, town lead, place to ask), never by the stock "I don't know" the fallback wrote.
                text = _person_fallback(world_state, npc_target, player_input)
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
                _speech_debug_trail({
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
                    "safety": getattr(_session(), "last_narration_safety", None),
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
                and text == _compose_experimental_npc_speech(attributed_speech)
            )
            turned_down_what_was_paid = (
                accepted_model_speech and settled_money.get("moved")
                and _npc_speech_rejects_claim(attributed_speech["spoken_text"])
            )
            if turned_down_what_was_paid or (
                accepted_model_speech and not _with_only_backed_money(attributed_speech, settled_money)
            ):
                accepted_model_speech = False
                text = (_job_fallback(world_state) or _town_fallback(world_state, npc_target, player_input)
                        or interaction_adventure.immersive_unknown(npc_target, player_input))
                speech_checks.append("unbacked_money")
            if speech_checks is not None:
                _session()._speech_checks = speech_checks
            if experimental_unverified_claim:
                action_result.update(status="unverified", success=False)
            if experimental_npc_dialogue:
                if accepted_model_speech:
                    if not (_is_short_followup(player_input) and profile_focus):
                        interaction_adventure.retire_conversation_focus(world_state)
                    text = _render_experimental_npc_speech(
                        attributed_speech, npc_target
                    )
                else:
                    name = living_world.public_npc_name(npc_target)
                    if (action_result.get("action") == "skill_check" and final_safety_handling == "python_fallback"
                            and not stock_swapped and text != text_before_finalize and not text.casefold().startswith(name.casefold())):
                        # The safety put the check's own narration in place of the reply ("İncelemen sonuç
                        # vermedi"): that is the narrator's, not theirs. It stays as narration, outside any quote,
                        # and the person answers in their own words (Task 34, review M3).
                        own = _person_fallback(world_state, npc_target, player_input)
                        text = f"{text} {own if own.casefold().startswith(name.casefold()) else f'{name}, “{own}”'}"
                    elif not text.casefold().startswith(name.casefold()):
                        text = f'{name}, “{text}”'

            if experimental_npc_dialogue:
                # The person's own spoken answer about the coin (`coin_answer`, read for every accepted speech) is also
                # the semantic reply to a validated gift or tip put to them: takes accepts it, declines refuses it,
                # and anything else leaves the card without their consent (the line refused, nothing charged).
                coin_reply = ({"takes": "accept", "declines": "refuse"}.get(getattr(_session(), "_coin_answer", None))
                              if accepted_model_speech else None)
                _record_spoken_coin_response(npc_target, coin_reply)
                if accepted_model_speech and valid_speech_packet and _rumour_lane_on():
                    import heard_rumours
                    named = raw_intent.get("mentions")
                    named = named.get("name") if isinstance(named, dict) else None
                    # D-249: what the person named is stored by Python only, and only a name they said aloud;
                    # a bad mention is dropped without a trace.
                    if heard_rumours.said_in(attributed_speech["spoken_text"], named):
                        heard_rumours.record_mention(
                            sys.modules[__name__], _session().world_state, npc_target, raw_intent.get("mentions"),
                            _session().world_state.get("flags", {}).get("turn_index", 0))
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
                    terms = _offer_terms_shown(world_state, npc_target, player_input, text)
                    if terms:
                        # D-247: a stock "I don't know" never sits beside the job's own terms; the terms are the answer.
                        bare = text == interaction_adventure.immersive_unknown(npc_target, player_input)
                        text = f"{living_world.public_npc_name(npc_target)}, “{terms}”" if bare else f"{text} “{terms}”"
                    _remember_experimental_npc_speech(
                        npc_target["id"], player_input, text, remember=valid_speech_packet and raw_intent.get("remember_player_line") is True
                    )
                    if settled_money.get("note"):
                        text = f"{text} {settled_money['note']}"
                _show_coin_roll(action_result, settled_money.get("check"))  # D-166: the roll shows, reply used or not
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
                    note = money_owner.haggle(_session(), npc_target, check,
                                               negotiation=negotiation, player_input=player_input)
                    if note:
                        action_result["haggle_note"] = note
                else:
                    price_result = resolve_intent({"intent": "persuasion", "price_negotiation": negotiation},
                                                  player_input, npc_target=npc_target, target_id=target_id)
                    if price_result.get("action") == "skill_check":
                        action_result.update(price_result)
            _show_coin_roll(action_result, settled_money.get("check"))  # D-166: the coin ask's own roll shows
            if experimental_npc_dialogue:
                spoken = attributed_speech["spoken_text"] if accepted_model_speech else text
                terms = _offer_terms_shown(world_state, npc_target, player_input, spoken)
                if terms:
                    text, spoken = f"{text} “{terms}”", f"{spoken} {terms}"
                _remember_experimental_npc_speech(npc_target["id"], player_input, spoken,
                                                  remember=valid_speech_packet and raw_intent.get("remember_player_line") is True,
                                                  voiced=_voiced_keys(raw_intent) if accepted_model_speech and valid_speech_packet else None)
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
        if npc_target is not None and (_is_object_inspection(player_input)
                                       or (target_id is None and bold_acts.is_act_not_talk(_session(), player_input))):
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
            raw_intent = parse_player_intent(
                player_input,
                interaction_context=interaction_adventure.context(
                    world_state, npc_target, player_input
                ),
                # This generic intent path may resolve a bounded mechanics
                # request; conversation is validated after classification.
                require_conversation=False,
                allow_scene_detail_proposals=_scene_detail_proposals_allowed(
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
                    and not _grounded_item_request_proposal(
                        raw_intent, npc_target, player_input
                    )
                    # in a fight, a walk toward someone is combat movement, not words to them
                    and not (combat["active"] and isinstance(raw_intent, dict) and raw_intent.get("intent") == "travel")
                ),
            )
        )
        if conversation_rejected:
            if _salvage_plain_speech(raw_intent):
                conversation_rejected = False
                conversation_resolution = None
            else:
                return finish_conversation_rejection(npc_target)
        if _interaction_proposal_applies(raw_intent, npc_target, player_input):
            action_result = interaction_adventure.resolve(
                _session(), player_input, raw_intent["interaction"], npc_target,
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
        normalized_intent = normalize_intent(raw_intent, player_input)
        validated_intent = validate_intent(normalized_intent, player_input)
    walk = getattr(_session(), "_walk_off", None)
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
            action_result.get("direct_response") or _natural_unresolved_action_response(player_input, action_result),
            is_final=True,
            safety_handling="python_scene_response",
        )

    if action_result.get("action") == "combat_move":
        return finish_turn(action_result, action_result["direct_response"], is_final=True)  # the engine tells it

    if action_result.get("action") in {"attack", "death_save"}:
        # Reuse the existing mechanical renderer. Do not send a not-yet-saved
        # combat outcome to a model before the API receipt transaction succeeds.
        quest_transitions = _session().evaluate_quest_events(
            quest_world_before, action_result
        )
        if quest_transitions:
            action_result["quest_outcomes"] = quest_transitions
        return finish_turn(
            action_result,
            _combat_narration(action_result),
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
        early_parent = _scene_detail_parent(world_state.get("location"), player_input)
        early_parent_id = early_parent.get("id") if isinstance(early_parent, dict) else None
        early_bound = [proposal for proposal in raw_intent["scene_detail_proposals"][:1]
                       if isinstance(proposal, dict)
                       and proposal.get("parent_id") == early_parent_id]
        early_entry = action_result.get("action") == "travel" and action_result.get("completion") == "completed"
        early_changed = early_entry or world_state.get("location") != previous_location
        action_result["scene_detail_proposal_submitted"] = True
        action_result["verified_world_updates"] = validate_world_updates(
            {"create_features": early_bound},
            allow_new_features=(not shop_request
                                and should_generate_features(player_input, early_changed)
                                and not is_player_world_assertion(player_input)),
            allowed_feature_kinds=SCENE_DETAIL_KIND_ALLOWLIST,
        )
        if action_result["verified_world_updates"].get("create_features"):
            findings = None
    if isinstance(findings, dict) and isinstance(findings.get("text"), str) and findings["text"].strip():
        # LR00-P2: a target-bound finding IS the result. Live runs showed the
        # narrator inventing a figure behind closed shutters; the receipt's
        # own words are shown instead, with no second model call.
        quest_transitions = _session().evaluate_quest_events(
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
        and should_generate_npcs(player_input, expected_location_change)
        and not is_player_world_assertion(player_input)
    )
    allow_new_features = (
        not shop_request
        and should_generate_features(player_input, expected_location_change)
        and not is_player_world_assertion(player_input)
    )
    scene_parent = _scene_detail_parent(
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
            action_result["verified_world_updates"] = validate_world_updates(
                {"create_features": bound_proposals},
                allow_new_features=allow_new_features,
                allowed_feature_kinds=SCENE_DETAIL_KIND_ALLOWLIST,
            )
    allow_new_shops = bool(shop_request)

    quest_transitions = _session().evaluate_quest_events(
        quest_world_before, action_result
    )
    if quest_transitions:
        action_result["quest_outcomes"] = quest_transitions
    narration = action_result.get("direct_response") or _fallback_for_action_result(
        player_input, action_result
    )
    # An inventory transaction has already been resolved by Python. Do not
    # let a separate narrator reverse its direction or invent another transfer.
    return finish_turn(
        action_result, narration, quest_transitions,
        is_final=action_result.get("action") == "inventory",
    )


DEFAULT_SAVE_PATH = Path(__file__).resolve().parent / "saves" / "adventure.json"


def start_terminal_game(input_fn=input, print_fn=print, save_path=DEFAULT_SAVE_PATH):
    """Resume a default save, or start a new character when none is chosen."""
    save_path = Path(save_path).expanduser()
    if save_path.is_file():
        print_fn("Kayıtlı macera bulundu.")
        print_fn("1. Yeni karakter oluştur")
        print_fn("2. Kayıtlı maceraya devam et")
        while True:
            choice = input_fn("Seçimin: ").strip()
            if choice == "1":
                break
            if choice == "2":
                try:
                    load_game(save_path)
                except (OSError, ValueError, TypeError) as error:
                    print_fn(f"Kayıt yüklenemedi: {error}")
                    print_fn("Yeni karakter oluşturabilir veya oyundan çıkabilirsin.")
                    continue
                print_fn(f"Oyun yüklendi: {save_path}")
                return True
            if choice.casefold() in ("çık", "exit"):
                return False
            print_fn("Lütfen 1 veya 2 seç.")
    initialize_game(input_fn=input_fn, print_fn=print_fn)
    return True


# All mutable engine references above resolve through _session(). The wrapper
# below provides an explicit session= argument and propagates it to nested calls.
_PART_MODULES = ("game_parts.character_rules", "game_parts.coin", "game_parts.combat_flow", "game_parts.dialogue", "game_parts.intent", "game_parts.living_world_turn", "game_parts.lore", "game_parts.narration", "game_parts.narration_safety", "game_parts.new_game", "game_parts.places", "game_parts.savefile", "game_parts.text_rules_a", "game_parts.text_rules_b")
_ENGINE_FUNCTIONS = tuple(name for name, value in globals().items()
                          if isinstance(value, types.FunctionType)
                          and (value.__module__ == __name__ or value.__module__ in _PART_MODULES))
_CHARACTER_GLOBALS = {
    "character_name": "name", "character_race": "race",
    "character_class": "class",
    **{key: key for key in (
        "strength", "dexterity", "constitution", "intelligence", "wisdom",
        "charisma", "proficient_skills", "level", "proficiency_bonus",
        "max_hp", "current_hp", "armor_class", "strength_mod",
        "dexterity_mod", "constitution_mod", "intelligence_mod",
        "wisdom_mod", "charisma_mod", "modifiers",
    )},
}
_ACTIVE_SESSION = contextvars.ContextVar("ai_dnd_active_session", default=None)
_DEFAULT_SESSION = None
_ENGINE_NAMESPACE = globals()


def _restore_in_place(live, saved):
    """Make ``live`` equal ``saved`` while keeping every container both still hold the live object (B1 forfeit).

    ``saved`` is a private deep copy the caller gives up. Dicts lose keys ``saved`` lacks; lists are matched by position
    (surplus items dropped, missing ones appended); a value of another type is replaced.
    """
    if isinstance(live, dict):
        for key in [key for key in live if key not in saved]:
            del live[key]
        for key, value in saved.items():
            current = live.get(key)
            if key in live and type(current) is type(value) and isinstance(value, (dict, list)):
                _restore_in_place(current, value)
            else:
                live[key] = value
    else:
        del live[len(saved):]
        for index, value in enumerate(saved):
            if index >= len(live):
                live.append(value)
            elif type(live[index]) is type(value) and isinstance(value, (dict, list)):
                _restore_in_place(live[index], value)
            else:
                live[index] = value


class GameSession:
    """Independent player, world, narration history, conversation and dice."""

    def __init__(self, seed=None):
        self.character = {}
        self.world_state = copy.deepcopy(INITIAL_WORLD_STATE)
        self.recent_dm_narrations = []
        self.messages = [{"role": "system", "content": system_prompt}]
        self.rng = random.Random(seed)
        # Injected by the API for one request; never included in engine saves.
        self.lore_authority_context = None
        # Ephemeral diagnostics only; these are deliberately outside canonical
        # world state and are never returned in the player-facing turn payload.
        self.last_narration_safety = None
        self.last_arrival_narration = None
        self.narration_safety_history = []
        self._xp_level_up = None
        self._xp_unrecorded = []
        self._xp_unrecorded_awards = []  # this turn's forfeited awards: (receipt ids, amount shown) — one line each
        self._persisted_engine_format = SAVE_FORMAT_VERSION

    def _receive_xp_award(self, award_owner, *args, **kwargs):
        """Session adoption of an existing XP owner; no new reward or receipt policy.

        Sessionless callers may use xp.apply_xp for detached numeric work, but
        persistent sessions must use this boundary to atomically adopt format6.
        A campaign still on save format 1..3 moves to format 6 here too (its live
        spell fields are the canonical empty ones load_game set); the real save
        validator admits the result or the whole award is put back.
        """
        snapshot = self._capture_runtime_snapshot()
        had_format = "_persisted_engine_format" in self.__dict__
        old_format = copy.deepcopy(self.__dict__.get("_persisted_engine_format"))
        try:
            return self._admit_xp_award(award_owner, *args, **kwargs)
        except Exception:
            self._restore_runtime_snapshot(snapshot)
            if had_format:
                self._persisted_engine_format = old_format
            else:
                self.__dict__.pop("_persisted_engine_format", None)
            raise

    def _admit_xp_award(self, award_owner, *args, **kwargs):
        held = self.world_state.get("xp_awarded_event_ids")
        held = set(held) if isinstance(held, list) else set()
        format_before = getattr(self, "_persisted_engine_format", SAVE_FORMAT_VERSION)
        summary = award_owner(*args, **kwargs)
        crossing = (isinstance(summary, dict) and summary.get("xp_gained", 0) > 0
                    and summary.get("previous_level", 5) < 5 <= summary.get("new_level", 0))
        if crossing:
            written = [event_id for event_id in self.world_state.get("xp_awarded_event_ids", [])
                       if event_id not in held]  # this award's receipts: a retry of it is the same award (D-061)
        if crossing and format_before not in _SUPPORTED_SAVE_VERSIONS:
            import xp
            raise xp.UnrecordableXp(summary["xp_gained"], xp.REASON_OLD_SAVE, written)
        self._remember_xp_award(summary)
        if crossing:
            # Read through the real production admission owner before commit.
            try:
                self._validate_save_payload(self.serialize_game_state())
            except ValueError as error:
                import xp
                # D-061: the forfeit boundary checks the record before the award, so a refusal the award did not
                # cause is raised, not forfeited (``__cause__`` carries the admission's own error). Only a record
                # still on an older format is told it is an old save.
                reason = xp.REASON_CROSSING if format_before == 6 else xp.REASON_OLD_SAVE
                raise xp.UnrecordableXp(summary["xp_gained"], reason, written) from error
        return summary

    def _forfeit_unrecordable_xp(self, award_owner, *args, **kwargs):
        """B1 (D-001, D-013): the product's XP boundary. An award that cannot be recorded (a full receipt list, the XP
        cap, an unknown class at a level step, a level-5 crossing the save admission refuses) is put back and logged,
        and play goes on without it instead of being refused on every later turn. Returns the summary, or None.

        Character and world are put back to their exact earlier values *in place* (`_restore_in_place`): every nested
        container a caller holds (the fight being ended, the creature just knocked out, ``saving_throw_mods``) stays
        the live object, and whatever the award or the save check wrote (receipts, level, the save check's
        ``scene_state`` default-fill) is undone. The pending announcement and the save format are put back too. The RNG
        and the narration history are not touched by an award and are not restored.

        D-061: only a known refusal (``xp.UnrecordableXp``) is forfeited; it leaves one player line for this turn
        (``_take_xp_unrecorded``). Any other error is a bug: put back, raised, and the turn falls back whole. A level-5
        admission refusal counts as known only when the record before the award passes the same admission.
        """
        import xp
        character = copy.deepcopy(self.character)
        world = copy.deepcopy(self.world_state)
        pending = copy.deepcopy(self._xp_level_up)
        had_format = "_persisted_engine_format" in self.__dict__
        old_format = copy.deepcopy(self.__dict__.get("_persisted_engine_format"))

        def put_back(saved_character, saved_world):
            _restore_in_place(self.character, saved_character)
            _restore_in_place(self.world_state, saved_world)
            self._xp_level_up = copy.deepcopy(pending)
            if had_format:
                self._persisted_engine_format = old_format
            else:
                self.__dict__.pop("_persisted_engine_format", None)

        try:
            return self._admit_xp_award(award_owner, *args, **kwargs)
        except Exception as error:
            put_back(copy.deepcopy(character), copy.deepcopy(world))
            if not isinstance(error, xp.UnrecordableXp):
                raise
            if isinstance(error.__cause__, ValueError):
                try:
                    self._validate_save_payload(self.serialize_game_state())
                except ValueError:
                    put_back(character, world)
                    raise error.__cause__  # the record was refused before the award: not the award's doing
                put_back(character, world)  # the check's own default-fill (``scene_state``) goes back too
            import logging
            logging.getLogger(__name__).warning("An experience award could not be recorded and is forfeited (B1): %s",
                                                error)
            self._note_unrecorded_xp(error)
            return None

    def _note_unrecorded_xp(self, error):
        """One line per forfeited award this turn (D-061). An award tried again in the same turn (a creature knocked
        out, then counted again when the fight ends) adds no second line; a retry that also holds new receipts shows
        only the amount not shown yet."""
        import xp
        ids = set(error.event_ids)
        shown = list(getattr(self, "_xp_unrecorded_awards", []))
        if ids and ids <= {event_id for earlier, _ in shown for event_id in earlier}:
            return
        amount = error.amount - sum(earlier_amount for earlier, earlier_amount in shown if ids and set(earlier) <= ids)
        self._xp_unrecorded_awards = [*shown, (sorted(ids), amount)]
        self._xp_unrecorded = [*getattr(self, "_xp_unrecorded", []), str(xp.UnrecordableXp(amount, error.reason))]

    def _take_xp_unrecorded(self):
        """This turn's lines for forfeited awards ("<X> XP kaydedilemedi: <neden>."), then forget them (D-061)."""
        lines = list(getattr(self, "_xp_unrecorded", []))
        self._xp_unrecorded = []
        self._xp_unrecorded_awards = []
        return lines

    def _remember_xp_award(self, summary):
        """Fold another award into the single announcement for this turn."""
        if not isinstance(summary, dict):
            return
        if (type(summary.get("xp_gained")) is int and summary["xp_gained"] > 0
                and summary.get("previous_level", 5) < 5 <= summary.get("new_level", 0)):
            self._persisted_engine_format = 6
        pending = self._xp_level_up
        if not isinstance(pending, dict):
            self._xp_level_up = copy.deepcopy(summary)
            return
        self._xp_level_up = {
            "previous_level": pending["previous_level"],
            "new_level": summary["new_level"],
            "xp_gained": pending["xp_gained"] + summary["xp_gained"],
            "hit_points_gained": pending["hit_points_gained"] + summary["hit_points_gained"],
        }

    def _publish_level_up(self, result):
        """Move one pending level-up onto a turn result, then forget it."""
        pending = self._xp_level_up
        if not isinstance(result, dict) or not isinstance(pending, dict):
            return result
        result["level_up"] = copy.deepcopy(pending)
        self._xp_level_up = None
        return result

    def __getattr__(self, name):
        helper = _ENGINE_NAMESPACE.get(name)
        if callable(helper) and getattr(helper, "_session_bound", False):
            return functools.partial(helper, session=self)
        raise AttributeError(name)

    def _capture_runtime_snapshot(self):
        """Capture owned runtime state for rollback, not for save-file loading."""
        return {
            "character": copy.deepcopy(self.character),
            "world_state": copy.deepcopy(self.world_state),
            "recent_dm_narrations": copy.deepcopy(self.recent_dm_narrations),
            "messages": copy.deepcopy(self.messages),
            "rng_state": self.rng.getstate(),
            "xp_level_up": copy.deepcopy(self._xp_level_up),
            "xp_unrecorded": list(getattr(self, "_xp_unrecorded", [])),
            "xp_unrecorded_awards": copy.deepcopy(getattr(self, "_xp_unrecorded_awards", [])),
            "persisted_engine_format_present": "_persisted_engine_format" in self.__dict__,
            "persisted_engine_format": copy.deepcopy(self.__dict__.get("_persisted_engine_format")),
            # D-115: the open "kavga mı başlatıyorsun?" question goes back with the turn that asked it.
            "attack_question": (getattr(self, "_attack_asked", False), copy.deepcopy(getattr(self, "_blow_asked", None)),
                                copy.deepcopy(getattr(self, "_blow_asked_line", None))),
            # D-115: so does the surrendered-foe question ("Yine de vuruyor musun?").
            "surrender_question": copy.deepcopy(getattr(self, "_surrender_strike_asked", None)),
            # D-109: and the crime/threat question ("Gerçekten çalıyor musun?").
            "heavy_question": copy.deepcopy(getattr(self, "_heavy_asked", None)),
            "heavy_yes": copy.deepcopy(getattr(self, "_heavy_confirmed", None)),
        }

    def _restore_runtime_snapshot(self, snapshot):
        """Restore a trusted in-process capture exactly, without save migrations.

        A rejected request can start with inconsistent runtime markers. Rollback
        must preserve those markers, not validate or repair them. External JSON
        continues to enter exclusively through the validated load_game boundary.
        Keep containers in place for callers holding world/character references.
        """
        restored = copy.deepcopy(snapshot)
        self.rng.setstate(restored["rng_state"])
        self.character.clear()
        self.character.update(restored["character"])
        self.world_state.clear()
        self.world_state.update(restored["world_state"])
        self.recent_dm_narrations[:] = restored["recent_dm_narrations"]
        self.messages[:] = restored["messages"]
        self._xp_level_up = restored.get("xp_level_up")
        self._xp_unrecorded = restored.get("xp_unrecorded", [])
        self._xp_unrecorded_awards = restored.get("xp_unrecorded_awards", [])
        if restored.get("persisted_engine_format_present", False):
            self._persisted_engine_format = restored["persisted_engine_format"]
        else:
            self.__dict__.pop("_persisted_engine_format", None)
        self._attack_asked, self._blow_asked, self._blow_asked_line = restored.get("attack_question", (False, None, None))
        self._surrender_strike_asked = restored.get("surrender_question")
        self._heavy_asked = restored.get("heavy_question")
        self._heavy_confirmed = restored.get("heavy_yes")

    def resolve_ambient_event_action(
        self,
        event_instance_id: str,
        action_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Resolve a click on the scene's ambient event (the rule and the click live in `ambient_actions`)."""
        import ambient_actions
        return ambient_actions.resolve(self, event_instance_id, action_id, action)

    def quest_offers(self):
        world = self.world_state
        known_quests = {item.get("quest_id") for item in world.get("quests", [])}
        current_location = world.get("location")
        offers = []
        for definition in quest_catalog():
            if definition["quest_id"] in known_quests:
                continue
            condition = definition.get("offer_condition")
            if condition:
                if condition["type"] == "location_is":
                    if (
                        condition["target"] != current_location
                        or condition["target"] not in world.get("locations", {})
                    ):
                        continue
                elif condition["type"] == "npc_present":
                    if not any(
                        npc.get("id") == condition["target"]
                        and npc.get("location") == current_location
                        for npc in world.get("npcs", [])
                        if isinstance(npc, dict)
                    ):
                        continue
            offers.append({
                "quest_id": definition["quest_id"],
                "title": definition["title"],
                "description": definition["description"],
                "giver_npc_id": definition.get("giver_npc_id"),
                "objectives": [dict(item) for item in definition["objectives"]],
            })
        return offers

    def _quest_record(self, definition, turn_index, status="accepted"):
        return {
            "quest_id": definition["quest_id"],
            "title": definition["title"],
            "description": definition["description"],
            "giver_npc_id": definition.get("giver_npc_id"),
            "status": status,
            "objectives": [
                {
                    "objective_id": item["objective_id"],
                    "description": item["description"],
                    "type": item["type"],
                    "target": item["target"],
                    "status": "active" if status == "accepted" else "cancelled",
                    "required_count": item.get("required_count", 1),
                    "progress": 0,
                }
                for item in definition["objectives"]
            ],
            "created_turn": turn_index,
            "accepted_turn": turn_index if status == "accepted" else None,
            "updated_turn": turn_index,
        }

    def accept_quest(self, quest_id):
        self.require_player_can_act()
        existing = next((item for item in self.world_state["quests"]
                         if item.get("quest_id") == quest_id), None)
        if existing is not None and existing.get("record_kind") == "dynamic":
            return adventure_play.accept(self, quest_id)
        if existing is not None:
            return {"transition": None, "quest": copy.deepcopy(existing)}
        definition = next(
            (item for item in self.quest_offers() if item["quest_id"] == quest_id),
            None,
        )
        if definition is None:
            raise ValueError("Quest is not available.")
        turn = self.world_state.get("flags", {}).get("turn_index", 0)
        record = self._quest_record(definition, turn)
        self.world_state["quests"].append(record)
        return {"transition": self._quest_transition(
            "accepted", quest_id, None, f"command:accept:{quest_id}:{turn}", turn
        ), "quest": copy.deepcopy(record)}

    def cancel_quest(self, quest_id):
        self.require_player_can_act()
        existing = next((item for item in self.world_state["quests"]
                         if item.get("quest_id") == quest_id), None)
        if existing is not None and existing.get("record_kind") == "dynamic":
            from adventure import dialogue_jobs
            return dialogue_jobs.cancel_job(self, existing)
        if existing is None:
            definition = next(
                (item for item in self.quest_offers() if item["quest_id"] == quest_id),
                None,
            )
            if definition is None:
                raise ValueError("Quest is not available.")
            turn = self.world_state.get("flags", {}).get("turn_index", 0)
            preview = self._quest_record(definition, turn, status="cancelled")
            self.world_state["quests"].append(preview)
            return {"transition": self._quest_transition(
                "cancelled", quest_id, None, f"command:cancel:{quest_id}:{turn}", turn
            ), "quest": preview}
        if existing.get("status") == "cancelled":
            return {"transition": None, "quest": copy.deepcopy(existing)}
        if existing.get("status") == "completed":
            return {"transition": None, "quest": copy.deepcopy(existing)}
        turn = self.world_state.get("flags", {}).get("turn_index", 0)
        existing["status"] = "cancelled"
        existing["updated_turn"] = turn
        for objective in existing.get("objectives", []):
            if objective.get("status") == "active":
                objective["status"] = "cancelled"
        return {"transition": self._quest_transition(
            "cancelled", quest_id, None, f"command:cancel:{quest_id}:{turn}", turn
        ), "quest": copy.deepcopy(existing)}

    @staticmethod
    def _quest_transition(kind, quest_id, objective_id, source_id, turn):
        return {
            "event_id": f"quest:{kind}:{quest_id}:{source_id}",
            "quest_id": quest_id,
            "transition": kind,
            "objective_id": objective_id,
            "source_event_id": source_id,
            "turn_index": turn,
        }

    def evaluate_quest_events(self, before_world, action_result):
        """Consume only canonical before/after evidence; never narration."""
        if not isinstance(action_result, dict):
            return []
        world = self.world_state
        turn = world.get("flags", {}).get("turn_index", 0)
        events = []
        if (
            before_world.get("location") != world.get("location")
            and world.get("location") in world.get("locations", {})
        ):
            events.append(("visit_location", world.get("location"),
                           f"location:{turn}:{world.get('location')}"))
        before_npcs = {n.get("id"): n for n in before_world.get("npcs", [])
                       if isinstance(n, dict)}
        for npc in world.get("npcs", []):
            npc_id = npc.get("id")
            if not npc_id or npc_id not in before_npcs:
                continue
            was = before_npcs[npc_id]
            defeated = (npc.get("combat_status") in {"unconscious", "defeated", "dead"}
                        or npc.get("current_hp", 1) <= 0)
            previously = (was.get("combat_status") in {"unconscious", "defeated", "dead"}
                          or was.get("current_hp", 1) <= 0)
            if defeated and not previously:
                events.append(("defeat_entity", npc_id,
                               f"defeat:{turn}:{npc_id}"))
        before_items = equipment_economy.labels(before_world.get("inventory", []))
        after_items = equipment_economy.labels(world.get("inventory", []))
        for item in sorted(set(after_items) - set(before_items), key=str.casefold):
            if item == "Kılıç":
                events.append(("acquire_item", item, f"item:{turn}:{item}"))
        transitions = []
        processed = world.setdefault("quest_processed_event_ids", [])
        for kind, target, source_id in events:
            if source_id in processed:
                continue
            event_matched = False
            for quest in world.get("quests", []):
                if quest.get("status") != "accepted":
                    continue
                for objective in quest.get("objectives", []):
                    if objective.get("status") != "active" or objective.get("type") != kind:
                        continue
                    if objective.get("target") != target:
                        continue
                    required = objective.get("required_count", 1)
                    progress = objective.get("progress", 0) + 1
                    objective["progress"] = min(required, progress)
                    quest["updated_turn"] = turn
                    event_matched = True
                    if progress < required:
                        transitions.append(self._quest_transition(
                            "objective_progress", quest["quest_id"],
                            objective["objective_id"], source_id, turn
                        ))
                        continue
                    objective["status"] = "completed"
                    transitions.append(self._quest_transition(
                        "objective_completed", quest["quest_id"],
                        objective["objective_id"], source_id, turn
                    ))
                    if all(item.get("status") == "completed"
                           for item in quest["objectives"]):
                        quest["status"] = "completed"
                        import xp
                        self._forfeit_unrecordable_xp(  # D-060: a refused award is forfeited with a line, not a rejected turn
                            xp.award_completed_quest, world, self.character, quest["quest_id"]
                        )
                        transitions.append(self._quest_transition(
                            "completed", quest["quest_id"], None, source_id, turn
                        ))
            if event_matched:
                processed.append(source_id)
        transitions.extend(_dynamic_engine_transitions(
            adventure.apply_dynamic_evidence(world, before_world, action_result),
            world,
            before_world,
        ))
        adventure_play.after_turn(self, before_world, action_result)
        incident_hooks.after_turn(self, before_world, action_result)
        return transitions


def _dynamic_engine_transitions(notes, world, before_world=None):
    """Shape dynamic completions for the existing engine-evidence contract."""
    turn = world.get("flags", {}).get("turn_index", 0) if isinstance(world, dict) else 0
    if type(turn) is not int:
        turn = 0
    shaped = []
    touched = []
    for note in notes or []:
        if not isinstance(note, dict):
            continue
        quest_id = note.get("quest_id")
        objective_id = note.get("objective_id")
        if not isinstance(quest_id, str) or not isinstance(objective_id, str):
            continue
        shaped.append({
            "event_id": f"quest:objective_completed:{quest_id}:{objective_id}:{turn}",
            "quest_id": quest_id,
            "transition": "objective_completed",
            "objective_id": objective_id,
            "source_event_id": f"dynamic:{quest_id}:{objective_id}:{turn}",
            "turn_index": turn,
        })
        if quest_id not in touched:
            touched.append(quest_id)
    quests = world.get("quests", []) if isinstance(world, dict) else []
    before_status = {
        item.get("quest_id"): item.get("status")
        for item in (before_world.get("quests", []) if isinstance(before_world, dict) else [])
        if isinstance(item, dict)
    }
    for quest in quests:  # a job closed with no new step this turn (steps kept before acceptance, D-203)
        quest_id = quest.get("quest_id") if isinstance(quest, dict) else None
        if (isinstance(quest_id, str) and quest_id not in touched and quest.get("status") == "COMPLETED"
                and before_status.get(quest_id) not in {None, "COMPLETED"}):
            touched.append(quest_id)
    for quest_id in touched:
        quest = next(
            (
                item for item in quests
                if isinstance(item, dict) and item.get("quest_id") == quest_id
            ),
            None,
        )
        if not isinstance(quest, dict) or quest.get("status") != "COMPLETED":
            continue
        shaped.append({
            "event_id": f"quest:completed:{quest_id}:{turn}",
            "quest_id": quest_id,
            "transition": "completed",
            "objective_id": None,
            "source_event_id": f"dynamic:{quest_id}:completed:{turn}",
            "turn_index": turn,
        })
    return shaped


def _session():
    return _ACTIVE_SESSION.get() or _DEFAULT_SESSION


def _bind_session_engine():
    for name in _ENGINE_FUNCTIONS:
        implementation = _ENGINE_NAMESPACE[name]

        @functools.wraps(implementation)
        def bound(*args, __implementation=implementation, session=None, **kwargs):
            selected = session if session is not None else _session()
            if not isinstance(selected, GameSession):
                raise TypeError("session must be a GameSession")
            token = _ACTIVE_SESSION.set(selected)
            try:
                return __implementation(*args, **kwargs)
            finally:
                _ACTIVE_SESSION.reset(token)

        bound._session_bound = True
        _ENGINE_NAMESPACE[name] = bound


_DEFAULT_SESSION = GameSession()
_DEFAULT_SESSION.world_state = world_state
_DEFAULT_SESSION.recent_dm_narrations = recent_dm_narrations
_DEFAULT_SESSION.messages = messages
_bind_session_engine()
initialize_game(creation_choice="2", print_fn=lambda *args, **kwargs: None)


def create_session(seed=None):
    """Create an initialized, independent adventure; seed controls its dice."""
    session = GameSession(seed=seed)
    token = _ACTIVE_SESSION.set(session)
    try:
        initialize_game(creation_choice="2", print_fn=lambda *args, **kwargs: None)
    finally:
        _ACTIVE_SESSION.reset(token)
    return session


if __name__ != "__main__":
    class _GameModule(types.ModuleType):
        pass

    for _alias_name, _alias_key in _CHARACTER_GLOBALS.items():
        setattr(_GameModule, _alias_name, property(
            lambda module, key=_alias_key: _DEFAULT_SESSION.character[key],
            lambda module, value, key=_alias_key: _DEFAULT_SESSION.character.__setitem__(key, value)))
    del _alias_name, _alias_key

    # Imported modules retain live character aliases. Plain exec dictionaries
    # must use create_session() and explicit session-owned state instead.
    if isinstance(sys.modules.get(__name__), types.ModuleType) and sys.modules[__name__].__dict__ is globals():
        sys.modules[__name__].__class__ = _GameModule


# ---------------------------------------------------------
# MACERA
# ---------------------------------------------------------
